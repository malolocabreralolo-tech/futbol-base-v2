#!/usr/bin/env python3
"""
Generate all data-*.js files from the SQLite database.

Reads futbolbase.db and produces:
  - data-benjamin.js
  - data-prebenjamin.js
  - data-alevin.js, data-infantil.js, data-cadete.js y data-juvenil.js (cada categoría perezosa de la
    temporada en curso, LAZY; siempre, aunque vacíos)
  - data-history.js (solo benjamín y prebenjamín: es carga inicial)
  - data-matchdetail.js (sin infantil, cadete ni juvenil, que van en data-matchdetail-<clave>.js)
  - data-goleadores.js
  - data-seasons.js and data-season-<S>.js (the past seasons; cada categoría perezosa, aparte, en
    data-season-<S>-<clave>.js: docs/alevin.md)
  - data-lineups-<S>-<grupo>.js (one per group with actas)
  - data-jugadores-<k>.js (las fichas, 64 trozos), data-buscar-<xy>.js (el buscador de jugadores) y
    data-ranking.js con data-ranking-<año>.js (los mejores de cada año de nacimiento): de las mismas filas
data-shields.js is maintained by hand. data-matchdetail-keys.js, data-stats.js
and data-players-<S>.js are not generated: nobody reads them
(test_pygen_fixes.py::TestGeneratorOutputs keeps them out).

Also bumps the cache version (?v= + footer date in index.html, CACHE_NAME in
sw.js, always the same string) but ONLY if the content of some data-*.js
actually changed in this run, so no-op cron runs produce no diff.
"""

import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import date, datetime, timedelta

# _CLUB_SUFFIX (the canonical club-token list) lives in scripts/acta_reconciler.py.
# Make the import work whether generate_js.py is run as `python3
# scripts/generate_js.py` (sys.path[0] is scripts/) or imported as
# `scripts.generate_js` (project root in sys.path).
try:
    from scripts.acta_reconciler import _CLUB_SUFFIX
except ImportError:
    from acta_reconciler import _CLUB_SUFFIX

# Allow importing db.py from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT
from escritura import escribir_atomico  # noqa: E402
import precache  # noqa: E402


def js_val(v):
    """Convert a Python value to a JS-compatible JSON value."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(js_val(x) for x in v) + "]"
    if isinstance(v, dict):
        items = ",".join(f"{json.dumps(k, ensure_ascii=False)}:{js_val(val)}" for k, val in v.items())
        return "{" + items + "}"
    return json.dumps(v, ensure_ascii=False)


MAX_SANE_SCORE = 50


def sanitize_score(score, context=""):
    """Defense in depth: a goal count outside [0, MAX_SANE_SCORE] is corrupt
    source data (e.g. the 2024-25 away_score=41736 IDs), never a real score.
    Emit it as null and warn on stderr so the corrupt row is visible in CI logs
    without poisoning the published data files."""
    if score is None:
        return None
    if 0 <= score <= MAX_SANE_SCORE:
        return score
    print(
        f"  WARNING: marcador fuera de rango ({score}) {context} — emitido como null",
        file=sys.stderr,
    )
    return None


def normalize_for_teams_mapping(s):
    """Normalizer for the club key: db.get_or_create_team and, in the browser,
    src/state.js normalizeForTeamsMapping.

    Same pipeline as acta_reconciler.normalize_team_name (lowercase -> NFKD
    accent-strip -> quotes/punctuation removed -> club tokens stripped via the
    shared _CLUB_SUFFIX list -> whitespace collapsed) EXCEPT it KEEPS the
    trailing filial letter, so 'UD Atalaya' -> 'atalaya' and 'UD Atalaya B' ->
    'atalaya b' get distinct keys instead of last-wins colliding.

    MIRROR: src/state.js normalizeForTeamsMapping must implement exactly the
    same pipeline — keep both sides in sync.
    """
    if not s:
        return ""
    # Comillas/puntuación -> espacio ANTES del pase ascii-ignore: las comillas
    # curvas no son descomponibles a ascii, así que codificar primero se las
    # tragaría sin dejar separador y divergiría del espejo JS
    # ('VET“C”' -> 'vetc' en vez de 'vet c').
    s = re.sub(r'["\'‘’“”]', " ", s)
    s = re.sub(r"[.,;:]", " ", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = _CLUB_SUFFIX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_groups_for_category(conn, category_name):
    """Return groups for the given category in the current season, ordered by code."""
    rows = conn.execute(
        """SELECT g.id, g.code, g.name, g.full_name, g.phase, g.island, g.url, g.current_jornada
           FROM groups g
           JOIN categories c ON g.category_id = c.id
           JOIN seasons s ON g.season_id = s.id
           WHERE c.name = ? AND s.is_current = 1
           ORDER BY g.code""",
        (category_name,),
    ).fetchall()
    return rows


# Las categorías de la carga inicial (data-benjamin.js, data-prebenjamin.js y data-history.js). Alevín
# va aparte, en ficheros que la web pide cuando los necesita (data-alevin.js y data-season-<S>-alevin.js,
# docs/alevin.md): sus 32 grupos harían crecer la carga inicial sin avisar.
EAGER_CATEGORIES = ("BENJAMIN", "PREBENJAMIN")
ALEVIN = "ALEVIN"
# Las categorías perezosas: categoría de la base → (clave de la web y del fichero, constante de sus grupos,
# sufijo de las demás constantes). Alevín, como siempre (data-alevin.js con ALEVIN, ALEV_STATS, HISTORY_ALEV…;
# nombres que la web ya lee y que no cambian); infantil, cadete y juvenil (parte E), igual, cada una en SU
# fichero: una familia que sigue a un niño de infantil no baja cadete ni juvenil (~0,5 MB cada una al acabar la
# temporada), y la portada no baja ninguna.
LAZY = {"ALEVIN": ("alevin", "ALEVIN", "ALEV"), "INFANTIL": ("infantil", "INFANTIL", "INF"),
        "CADETE": ("cadete", "CADETE", "CAD"), "JUVENIL": ("juvenil", "JUVENIL", "JUV")}
# Las de la parte E: sus campos (CAMPOS_<S>) y la cronología de sus partidos (data-matchdetail-<clave>.js) van
# en sus ficheros. Los de alevín siguen donde estaban (CAMPOS de data-history.js y MATCH_DETAIL), como los
# publica hoy: así ni la carga inicial ni data-matchdetail.js crecen con fútbol 11, y alevín sale igual.
NUEVAS = ("INFANTIL", "CADETE", "JUVENIL")


def _en_web():
    """Las categorías que enseña la web (categorias.EN_WEB, leída al llamar: las pruebas la parchean)."""
    import categorias
    return tuple(categorias.EN_WEB)


def teams_by_category(conn, season_id):
    """{equipo: {categorías en las que juega la temporada}} (clasificación y calendario)."""
    out = {}
    for name, cat in conn.execute(
            """SELECT t.name, upper(c.name) FROM standings st JOIN teams t ON t.id=st.team_id
                 JOIN groups g ON g.id=st.group_id JOIN categories c ON c.id=g.category_id WHERE g.season_id=?
               UNION
               SELECT t.name, upper(c.name) FROM matches m JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id)
                 JOIN groups g ON g.id=m.group_id JOIN categories c ON c.id=g.category_id WHERE g.season_id=?""",
            (season_id, season_id)):
        out.setdefault(name, set()).add(cat)
    return out


def _lazy_only(conn, season_id):
    """Los equipos que esa temporada solo juegan en categorías perezosas (LAZY): fuera de lo de benjamín y
    prebenjamín. El club que juega en benjamín y en juvenil (la misma fila de teams) se queda."""
    return {t for t, cats in teams_by_category(conn, season_id).items() if cats <= set(LAZY)}


def _new_only(conn, season_id):
    """Los equipos que esa temporada solo juegan en infantil, cadete o juvenil (NUEVAS): sus campos no van en el
    CAMPOS de data-history.js."""
    return {t for t, cats in teams_by_category(conn, season_id).items() if cats <= set(NUEVAS)}


def _in_category(conn, season_id, category):
    """Los equipos que esa temporada juegan en esa categoría (también en otra)."""
    return {t for t, cats in teams_by_category(conn, season_id).items() if category in cats}


def _match_key(home, away, hs, as_):
    """Match lookup key, identical to the frontend's
    (render.js / miequipo.js / modals.js: `home|away|hs-as`). Scores are
    sanitized (out-of-range -> None) and rendered JS-style ('null', not Python
    'None') so the ⚽ badge / lineup lookup matches on both sides."""
    def _js(v):
        v = sanitize_score(v)
        return "null" if v is None else str(v)
    return f"{home}|{away}|{_js(hs)}-{_js(as_)}"


_ROUND_RANK = (
    ("dieciseisavos", 1), ("octavos", 2), ("cuartos", 3),
    ("semifinal", 4), ("final", 5),  # "semifinal" also matches "semifinales"
)


def _jornada_sort_key(j):
    """Sort key for jornadas. Knockout rounds ("( Cuartos )"/"( Semifinales )"/
    "( Final )", optionally date-prefixed) order by progression (bracket reads
    Cuartos → Semifinales → Final), NOT by the day number or alphabetically.
    Regular jornadas ("Jornada 5", "Ronda 2", "5") order by their number."""
    s = str(j)
    sl = s.lower()
    dm = re.search(r"(\d{2})-(\d{2})-(\d{4})", s)
    datekey = (int(dm.group(3)), int(dm.group(2)), int(dm.group(1))) if dm else (0, 0, 0)
    for name, rank in _ROUND_RANK:
        if name in sl:
            return (datekey, rank)
    rest = re.sub(r"\d{2}-\d{2}-\d{4}", "", s)
    m = re.search(r"\d+", rest)
    return (datekey, int(m.group()) if m else 0)


def get_standings(conn, group_id):
    """Return standings for a group as list of [pos, team, pts, J, G, E, P, GF, GC, DF]."""
    rows = conn.execute(
        """SELECT s.position, t.name, s.points, s.played, s.won, s.drawn, s.lost,
                  s.gf, s.gc, s.gd
           FROM standings s
           JOIN teams t ON s.team_id = t.id
           WHERE s.group_id = ?
           ORDER BY s.position""",
        (group_id,),
    ).fetchall()
    return [list(r) for r in rows]


def _group_results(conn, group_id):
    """[(local, visitante, goles local, goles visitante)] de los partidos de un grupo, en orden de id,
    con los marcadores saneados (fuera de rango -> None, el partido cuenta como no jugado)."""
    rows = conn.execute(
        """SELECT h.name, a.name, m.home_score, m.away_score
           FROM matches m
           JOIN teams h ON m.home_team_id = h.id
           JOIN teams a ON m.away_team_id = a.id
           WHERE m.group_id = ?
           ORDER BY m.id""",
        (group_id,),
    ).fetchall()
    out = []
    for home, away, hs, as_ in rows:
        ctx = f"en {home} vs {away} (grupo {group_id})"
        out.append((home, away, sanitize_score(hs, ctx), sanitize_score(as_, ctx)))
    return out


def _table_from_results(results):
    """La tabla [pos, equipo, pts, J, G, E, P, GF, GC, DF] de unos resultados de _group_results."""
    table = {}

    def _entry(team):
        return table.setdefault(team, {"pts": 0, "j": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0})

    for home, away, hs, as_ in results:
        th, ta = _entry(home), _entry(away)
        if hs is None or as_ is None:
            continue
        th["j"] += 1
        ta["j"] += 1
        th["gf"] += hs
        th["gc"] += as_
        ta["gf"] += as_
        ta["gc"] += hs
        if hs > as_:
            th["g"] += 1
            th["pts"] += 3
            ta["p"] += 1
        elif hs < as_:
            ta["g"] += 1
            ta["pts"] += 3
            th["p"] += 1
        else:
            th["e"] += 1
            ta["e"] += 1
            th["pts"] += 1
            ta["pts"] += 1

    ordered = sorted(
        table.items(),
        key=lambda kv: (-kv[1]["pts"], -(kv[1]["gf"] - kv[1]["gc"]), -kv[1]["gf"], kv[0]),
    )
    return [
        [i + 1, name, st["pts"], st["j"], st["g"], st["e"], st["p"],
         st["gf"], st["gc"], st["gf"] - st["gc"]]
        for i, (name, st) in enumerate(ordered)
    ]


def compute_standings_from_matches(conn, group_id):
    """Recompute a league table from the matches of a group.

    Rows in the canonical standings format [pos, team, pts, J, G, E, P, GF,
    GC, DF]; 3/1/0 points; order pts desc, DF desc, GF desc, name asc.
    Teams appearing only in unplayed fixtures still get a zeroed row.
    Out-of-range scores are ignored (match treated as unplayed)."""
    return _table_from_results(_group_results(conn, group_id))


def retired_outside_table(stored, results):
    """Los retirados que la clasificación oficial ya no lista: equipos del calendario que no están en
    `stored` y que nunca han competido (sin resultados, o todos sus partidos con resultado son derrotas
    sin goles a favor: los 0-1 y 0-3 administrativos, a veces con acta). La federación los quita de su
    tabla y deja sus partidos en el calendario (AL11, AL15, AL20, AL31 y AL32 de 2026-27). Es la regla de
    la web (model.retiredTeams); sin tabla o sin ningún resultado en el grupo, nadie."""
    listed = {r[1] for r in stored}
    played = [r for r in results if r[2] is not None and r[3] is not None]
    if not listed or not played:
        return set()
    outside = {t for home, away, _, _ in results for t in (home, away) if t not in listed}
    competed = set()
    for home, away, hs, as_ in played:
        if not (hs == 0 and as_ > 0):
            competed.add(home)
        if not (as_ == 0 and hs > 0):
            competed.add(away)
    return outside - competed


def _is_league_group(code, phase):
    """True for regular league groups. Knockouts (Copa de Campeones, whose
    standings are synthesized by synth_copa_campeones.py with its own ranking
    semantics) must never be recomputed as a league table."""
    if "copa" in (phase or "").lower():
        return False
    # Finales, semifinales («Semifinal Liga Primera Lanzarote»), torneos de cierre o clausura y
    # eliminatorias (EL, PEL, ALEL: docs/alevin.md) (isCupGroup de src/state.js). Y las fases de ascenso
    # de infantil, cadete y juvenil («Fase de Ascenso a Interinsular», CADIA…; las «Eliminatorias de Ascenso
    # a …» ya caen en lo de antes): se juegan a eliminatoria o en liguillas cortas con su propio orden, y la
    # parte E las trata como copas (decisión 3).
    if re.match(r"(semi)?final\b|torneo\b|clausura\b|eliminatoria|fase de ascenso\b",
                (phase or "").lower()):
        return False
    if (code or "").upper().startswith(("PCC", "BC")):
        return False
    return True


# Real-world sanctions seen in the source deduct 3 (occasionally 6) points;
# the corruptions seen in the source are of another size, like -49 (Valkyrias Bec.: 0 vs 49) and
# -12 (Lanzarote B: 7 vs 19). A deviation beyond this tolerance, on a row whose
# W/D/L is self-consistent, is a mis-scraped points column, not a sanction.
_SANCTION_TOLERANCE = 6


def _repair_incoherent_points(stored):
    """Repair rows whose points are arithmetically impossible.

    The source occasionally mis-scrapes ONLY the points column (anti-scrape
    obfuscation defeats the parse and it defaults to a wrong number). When a
    row is otherwise self-consistent (``played == won + drawn + lost``, so
    ``3*won + drawn`` is trustworthy) but its points deviate beyond a plausible
    sanction, rewrite just that field and re-rank — keeping every other column.

    Crucially this does NOT recompute the table from ``matches``: the stored
    table can be MORE complete than the fixtures (it carries the final round
    and walkover losses that never appear as matches), so a full recompute
    would regress the other teams. Returns ``(rows, changed)``."""
    repaired = False
    out = []
    for row in stored:
        pos, name, pts, j, g, e, p, gf, gc, gd = row
        expected = 3 * g + e
        if j == g + e + p and abs(pts - expected) > _SANCTION_TOLERANCE:
            pts = expected
            repaired = True
        out.append([pos, name, pts, j, g, e, p, gf, gc, gd])
    if not repaired:
        return stored, False
    # canonical order: pts desc, DF desc, GF desc, name asc
    out.sort(key=lambda r: (-r[2], -r[9], -r[7], r[1]))
    for i, r in enumerate(out):
        r[0] = i + 1
    return out, True


def get_effective_standings(conn, group_id, code=None, phase=None):
    """Standings for a CURRENT-season group, recomputed from matches when the
    stored table went stale (the source kept publishing results after it
    stopped publishing standings — e.g. frozen since ~25/04 while results ran
    to J29). If the stored table is up to date it wins, because the official
    one may carry sanctions a recompute can't know about. When the stored table
    is complete but a row's points are impossible (a mis-scraped points
    column), only that field is repaired (see _repair_incoherent_points).

    A team the official table no longer lists because it retired (retired_outside_table: in the
    calendar with only administrative 0-1/0-3 losses, or no results) has no row: each of its results
    is ONE played J, the rival's, as the federation counts them (AL15, AL20 and AL32 of 2026-27: J 11 =
    2 × 3 real + 5 administrative). Only when the stored table shows that it annuls them all (stored J
    == 2 × real) do they not count. So a table one round behind is still caught (AL15 with its J3 played
    and the table of J2: 15 > 11), and a federation that counts only part of them reads as stale and is
    recomputed (the web says so: standingsKind «reconstructed»), never the other way round. A
    recomputed table never brings the retired row back."""
    stored = get_standings(conn, group_id)
    if not stored or not _is_league_group(code, phase):
        return stored
    results = _group_results(conn, group_id)
    retired = retired_outside_table(stored, results)
    stored_j = sum((r[3] or 0) for r in stored)
    played = [(home, away) for home, away, hs, as_ in results if hs is not None and as_ is not None]
    real = sum(1 for home, away in played if home not in retired and away not in retired)
    administrative = len(played) - real
    computed_j = 2 * real if stored_j == 2 * real else 2 * real + administrative
    if computed_j > stored_j:
        print(
            f"  WARNING: standings desfasados en grupo {code or group_id} "
            f"(J almacenada {stored_j} < J jugada {computed_j}) — recalculados desde matches",
            file=sys.stderr,
        )
        # Como la federación: sin la fila del retirado y con los resultados administrativos de los demás.
        computed = [r for r in _table_from_results(results) if r[1] not in retired]
        for i, r in enumerate(computed):
            r[0] = i + 1
        return computed
    repaired, changed = _repair_incoherent_points(stored)
    if changed:
        print(
            f"  WARNING: puntos incoherentes en grupo {code or group_id} "
            f"— reparados desde 3·G+E (resto de la tabla intacto)",
            file=sys.stderr,
        )
    return repaired


def points_order(rows, per_game=False):
    """La clasificación por puntos y luego diferencia de goles (docs/decisiones.md). La federación ordena
    las de prebenjamín (per_game) por puntos por partido (pts/J, 0 sin partidos; su columna pts/pj,
    parse_standings de fetch_fiflp.py), y con J desiguales eso no es el orden por puntos: en PG2 de 2026-27,
    Santa Brígida (3 puntos en 1 J) por encima de Las Mesas Hu. (6 en 2) y, aunque los puntos bajen, AD
    Huracán (3 en 1, DF +6) por encima de Glaucus (3 en 2, DF +7). Esas, y cualquiera con una fila con menos
    puntos que otra de debajo, van por puntos y, a igualdad de puntos con distintos pts/J (J distintas y
    puntos ≠ 0: ahí la federación ha desempatado por pts/J), por DF y GF; sin los goles de alguna fila (una
    tabla resumida, las de 10 y 11 celdas), solo por puntos. El orden es estable y, con los mismos puntos
    por partido (mismas J, o 0 puntos), el de la federación, que desempata por lo que la web no sabe (PG2 de
    2025-26: La Garita por encima de RC Victoria, 58 puntos en 28 J los dos y peor DF; puede ser el
    enfrentamiento directo), y por eso tampoco el nombre. Una de benjamín o alevín ya por puntos no se toca,
    ni sus empates: la federación las ordena por puntos (AL15 y AL26 de 2026-27, a igualdad de puntos,
    arriba el de más J y mejor DF); una sin los puntos de alguna fila, tampoco. Devuelve (filas,
    reordenada), renumeradas y reordenada solo si cambia el orden, sin cambiar `rows`."""
    pts = [r[2] for r in rows]
    if any(p is None for p in pts) or (not per_game and all(a >= b for a, b in zip(pts, pts[1:]))):
        return rows, False
    goals = all(r[7] is not None and r[9] is not None for r in rows)
    # Los empates a puntos entre equipos con distintos pts/J (J distintas, puntos ≠ 0): por DF y GF.
    tied = {p for p in set(pts) if goals and p != 0 and len({r[3] for r in rows if r[2] == p}) > 1}
    order = sorted(range(len(rows)),
                   key=lambda i: (-pts[i], -rows[i][9], -rows[i][7]) if pts[i] in tied else (-pts[i],))
    if order == list(range(len(rows))):
        return rows, False
    out = [list(rows[i]) for i in order]
    for i, r in enumerate(out):
        r[0] = i + 1
    return out, True


def get_current_jornada_matches(conn, group_id, current_jornada):
    """Return matches for the current jornada as [date, time, home, away, hs, as, venue]."""
    if not current_jornada:
        return []
    rows = conn.execute(
        """SELECT m.date, m.time, h.name, a.name, m.home_score, m.away_score, m.venue
           FROM matches m
           JOIN teams h ON m.home_team_id = h.id
           JOIN teams a ON m.away_team_id = a.id
           WHERE m.group_id = ? AND m.jornada = ?
           ORDER BY m.date, m.time, h.name""",
        (group_id, current_jornada),
    ).fetchall()
    out = []
    for r in rows:
        r = list(r)
        ctx = f"en {r[2]} vs {r[3]} ({r[0]})"
        r[4] = sanitize_score(r[4], ctx)
        r[5] = sanitize_score(r[5], ctx)
        out.append(r)
    return out


def generate_category_js(conn, category_name, var_name, stats_var):
    """Generate the JS content for a category (BENJAMIN, PREBENJAMIN or one of LAZY)."""
    groups = get_groups_for_category(conn, category_name)
    result = []
    total_teams = 0

    for gid, code, name, full_name, phase, island, url, current_jornada in groups:
        stored = get_standings(conn, gid)
        standings = get_effective_standings(conn, gid, code, phase)
        # La procedencia, antes de ordenar por puntos: reordenada, la oficial sigue siendo la oficial.
        kind = "source" if standings == stored else (
            "reconstructed" if sum(r[3] for r in standings) > sum(r[3] for r in stored) else "corrected")
        # Las ligas, por puntos (points_order; las de prebenjamín, que la federación ordena por puntos
        # por partido, también sus empates); las copas, con el orden de su fuente (_is_league_group).
        reordered = False
        if _is_league_group(code, phase):
            standings, reordered = points_order(standings, per_game=category_name.upper() == "PREBENJAMIN")
        matches = get_current_jornada_matches(conn, gid, current_jornada)
        total_teams += len(standings)

        group_obj = {
            "id": code,
            "name": name,
            "fullName": full_name,
            "phase": phase,
            "island": island,
            "url": url,
            "jornada": current_jornada,
            "standings": standings,
            "matches": matches,
            "standingsKind": kind,
        }
        # Solo si la web ha cambiado el orden de la tabla (la Tabla lo dice: src/screen-tabla.js).
        if reordered:
            group_obj["reordered"] = True
        # La clasificación detallada de la federación (casa/fuera y sanciones) y qué significa cada
        # puesto (app de futbolaspalmas), solo si los hay.
        detail = standings_detail_map(conn, gid)
        if detail:
            group_obj["detail"] = detail
        zones = zones_of(conn, gid, len(standings))
        if zones:
            group_obj["zones"] = zones
        result.append(group_obj)

    js = f"const {var_name}=" + js_val(result) + ";\n"
    js += f"const {stats_var}=" + js_val({"groups": len(groups), "teams": total_teams}) + ";\n"
    return js


def history_map(conn, categories):
    """({código de grupo: {jornada: [[fecha, local, visitante, gl, gv, null, hora, campo]]}}, partidos)
    de los grupos de la temporada actual de esas categorías."""
    marks = ",".join("?" * len(categories))
    groups = conn.execute(
        f"""SELECT g.id, g.code FROM groups g
           JOIN seasons s ON g.season_id = s.id
           JOIN categories c ON c.id = g.category_id
           WHERE s.is_current = 1 AND upper(c.name) IN ({marks})
           ORDER BY g.code""", tuple(categories),
    ).fetchall()

    history = {}
    total_matches = 0

    for gid, code in groups:
        # Get all matches for this group, ordered by jornada number then date
        rows = conn.execute(
            """SELECT m.jornada, m.date, h.name, a.name, m.home_score, m.away_score, m.time, m.venue
               FROM matches m
               JOIN teams h ON m.home_team_id = h.id
               JOIN teams a ON m.away_team_id = a.id
               WHERE m.group_id = ?
               ORDER BY m.jornada, m.date, m.time, h.name""",
            (gid,),
        ).fetchall()

        jornadas = {}
        for jornada, dt, home, away, hs, as_, kickoff, venue in rows:
            if jornada not in jornadas:
                jornadas[jornada] = []
            ctx = f"en {home} vs {away} ({dt})"
            jornadas[jornada].append(
                [dt, home, away, sanitize_score(hs, ctx), sanitize_score(as_, ctx), None, kickoff, venue]
            )
            total_matches += 1

        # Sort jornadas by progression (knockout rounds) or number (leagues)
        sorted_jornadas = dict(sorted(jornadas.items(), key=lambda x: _jornada_sort_key(x[0])))
        history[code] = sorted_jornadas
    return history, total_matches


def generate_history_js(conn):
    """Generate data-history.js with ALL matches of benjamín and prebenjamín (EAGER_CATEGORIES)
    grouped by group code and jornada; alevín va en data-alevin.js (HISTORY_ALEV)."""
    history, total_matches = history_map(conn, EAGER_CATEGORIES)
    # El directorio de campos va con el calendario (CAMPOS, para «Cómo llegar»):
    # un fichero inmediato nuevo rompería la primera apertura sin red con el SW
    # anterior, que no lo tiene y devolvería index.html en su lugar. De toda la
    # temporada, alevín incluido (data-alevin.js no lleva campos); los de infantil,
    # cadete y juvenil, no: van en su fichero (CAMPOS_<S>), y la carga inicial no crece.
    js = "const HISTORY=" + js_val(history) + ";\n" + generate_campos_js(conn) + "\n"
    js += f"const HIST_MATCHES={total_matches};"
    # Y con ellos, por la misma razón, la ficha de cada equipo de la temporada (equipación y campo,
    # EQUIPOS) y el estado de los partidos que da la app de futbolaspalmas (ESTADOS). Sin los
    # equipos que solo juegan en categorías perezosas ni sus partidos (EQUIPOS_<S>, ESTADOS_<S>).
    row = conn.execute("SELECT id FROM seasons WHERE is_current = 1").fetchone()
    only = _lazy_only(conn, row[0]) if row else set()
    js += "\nconst EQUIPOS=" + js_val(team_info_map(conn, row[0], keep=lambda t: t not in only) if row else {}) + ";"
    js += "\nconst ESTADOS=" + js_val(match_states_map(conn, row[0], EAGER_CATEGORIES) if row else {}) + ";"
    js += "\nconst COBERTURA=" + js_val(coverage_summary(conn)) + ";"
    return js


def generate_lazy_js(conn, category):
    """data-<clave>.js: una categoría perezosa (LAZY) de la temporada en curso, con la forma de lo de
    benjamín y en este orden (docs/alevin.md §4): <GRUPOS> y <S>_STATS (como BENJAMIN y BENJ_STATS),
    HISTORY_<S> (HISTORY), GOL_<S> (GOL_BENJ), ESTADOS_<S> (ESTADOS), EQUIPOS_<S> (EQUIPOS, de los equipos
    que juegan en ella) y, solo en las NUEVAS, CAMPOS_<S> (los campos de sus partidos y de sus equipos que no
    están en el CAMPOS de data-history.js, con su forma). Siempre, aunque esté vacío (también si la categoría
    no está en categorias.EN_WEB): la web lo pide sin saber si hay."""
    _clave, grupos, s = LAZY[category]
    row = conn.execute("SELECT id FROM seasons WHERE is_current = 1").fetchone()
    if category not in _en_web():
        row = None                    # no se enseña: como una temporada sin grupos de ella
        js = f"const {grupos}=" + js_val([]) + ";\n"
        js += f"const {s}_STATS=" + js_val({"groups": 0, "teams": 0}) + ";\n"
        history, gol = {}, []
    else:
        js = generate_category_js(conn, category, grupos, f"{s}_STATS")
        history, _ = history_map(conn, (category,))
        gol = goleadores_entries(conn, category)
    teams = _in_category(conn, row[0], category) if row else set()
    js += f"const HISTORY_{s}=" + js_val(history) + ";\n"
    js += f"const GOL_{s}=" + js_val(gol) + ";\n"
    js += f"const ESTADOS_{s}=" + js_val(match_states_map(conn, row[0], (category,)) if row else {}) + ";\n"
    js += f"const EQUIPOS_{s}=" + js_val(team_info_map(conn, row[0], keep=lambda t: t in teams) if row else {}) + ";\n"
    if category in NUEVAS:
        campos = {}
        if row:
            eager = set(_eager_campos(conn, row[0]))
            campos = {k: v for k, v in campos_entries(conn, season_venue_names(
                conn, row[0], (category,), keep=lambda t: t in teams)).items() if k not in eager}
        js += f"const CAMPOS_{s}=" + js_val(campos) + ";\n"
    return js


def generate_alevin_js(conn):
    """data-alevin.js (docs/alevin.md §4): generate_lazy_js de alevín. Se queda por las pruebas y los
    scripts que la llaman."""
    return generate_lazy_js(conn, ALEVIN)


def coverage_summary(conn):
    """Lo que guarda la base, para «Fuentes»: por temporada [nombre, grupos, partidos, con
    resultado, con acta, jugadores con alineación (fichas, no identidades de acta), goles con autor];
    equipos con ficha (equipación y campo), campos con coordenadas y el tamaño de la base en MB (de 5
    en 5, para que no cambie en cada pasada del bot)."""
    seasons = []
    ficha = "COALESCE(p.ficha_id, p.id)" if _has_table(conn, "players") and any(
        r[1] == "ficha_id" for r in conn.execute("PRAGMA table_info(players)")) else "a.player_id"
    for sid, name in conn.execute("SELECT id, name FROM seasons ORDER BY start_year DESC"):
        groups, matches, played, actas = conn.execute(
            """SELECT count(DISTINCT g.id), count(m.id), count(m.home_score), count(m.cod_acta)
               FROM groups g LEFT JOIN matches m ON m.group_id = g.id WHERE g.season_id = ?""", (sid,)).fetchone()
        # Jugadores = fichas: las identidades de acta de un mismo niño cuentan una vez.
        players = conn.execute(
            f"""SELECT count(DISTINCT {ficha}) FROM appearances a JOIN players p ON p.id = a.player_id
                JOIN matches m ON m.id = a.match_id
                JOIN groups g ON g.id = m.group_id WHERE g.season_id = ?""", (sid,)).fetchone()[0] \
            if _has_table(conn, "appearances") else 0
        # Por partido, la fuente que más goles con autor da (el acta o la cronología del portal): las dos
        # cuentan los mismos goles.
        events = ("(SELECT match_id, count(*) AS n FROM match_events WHERE kind = 'goal' GROUP BY match_id)"
                  if _has_table(conn, "match_events") else "(SELECT NULL AS match_id, 0 AS n)")
        goals = conn.execute(
            f"""SELECT coalesce(sum(max(coalesce(e.n, 0), coalesce(x.n, 0))), 0)
                FROM matches m JOIN groups g ON g.id = m.group_id
                LEFT JOIN {events} e ON e.match_id = m.id
                LEFT JOIN (SELECT match_id, count(*) AS n FROM goals GROUP BY match_id) x ON x.match_id = m.id
                WHERE g.season_id = ?""", (sid,)).fetchone()[0]
        seasons.append([name, groups, matches, played, actas, players, goals])
    teams = conn.execute("SELECT count(DISTINCT team_id) FROM team_seasons").fetchone()[0] \
        if _has_table(conn, "team_seasons") else 0
    venues = conn.execute("SELECT count(*) FROM venue_details WHERE lat IS NOT NULL").fetchone()[0] \
        if _has_table(conn, "venue_details") else 0
    db = os.path.join(PROJECT_ROOT, "futbolbase.db")
    size = int(5 * round(os.path.getsize(db) / 1024 / 1024 / 5)) if os.path.exists(db) else None
    return {"temporadas": seasons, "equipos": teams, "campos": venues, "mb": size}


def _keyed_or_dup(pairs):
    """[(clave, entrada), …] → {clave: entrada}; si dos o más partidos producen
    la misma clave `local|visitante|gl-gv`, {clave: {"dup": True, "list":
    [entrada, …]}} en el orden recibido. Nunca sobrescribe: si no, ganaría el
    último partido y el otro desaparecería sin aviso (la clave
    'CD Calero|La Garita|1-11' la comparten un partido de FF15 y otro de PG2).
    Una entrada dup no lleva .g/.home: la interfaz actual lee undefined y no
    pinta nada, en vez de los datos de otro partido."""
    buckets = {}
    for key, entry in pairs:
        buckets.setdefault(key, []).append(entry)
    return {k: v[0] if len(v) == 1 else {"dup": True, "list": v}
            for k, v in buckets.items()}


def _category_filter(category):
    """(condición SQL, parámetros) sobre la categoría `c` del grupo (por LEFT JOIN): con
    `category`, solo los suyos; sin ella, los de data-matchdetail.js, todos menos los de las NUEVAS (los de un
    grupo sin categoría se quedan, como siempre)."""
    if category:
        return "upper(c.name) = ?", (category,)
    return f"(c.name IS NULL OR upper(c.name) NOT IN ({','.join('?' * len(NUEVAS))}))", NUEVAS


def _match_details(conn, category=None):
    """{clave: {s, gr, g}} (o dup) con la cronología de goles de TODAS las
    temporadas. s = temporada y gr = código de grupo, para que la interfaz
    distinga dos partidos con la misma clave. Sin `category`, los de
    data-matchdetail.js (todas menos infantil, cadete y juvenil); con una de
    NUEVAS, los de su data-matchdetail-<clave>.js."""
    where, args = _category_filter(category)
    rows = conn.execute(
        f"""SELECT DISTINCT m.id, h.name, a.name, m.home_score, m.away_score,
                  s.name, gr.code
           FROM matches m
           JOIN teams h ON m.home_team_id = h.id
           JOIN teams a ON m.away_team_id = a.id
           JOIN groups gr ON gr.id = m.group_id
           LEFT JOIN categories c ON c.id = gr.category_id
           JOIN seasons s ON s.id = gr.season_id
           JOIN goals g ON g.match_id = m.id
           WHERE {where}
           ORDER BY m.id""", args,
    ).fetchall()

    pairs = []
    for match_id, home, away, hs, as_, season, code in rows:
        goals = conn.execute(
            """SELECT minute, player_name, running_score, side, type
               FROM goals WHERE match_id = ? ORDER BY minute, id""",
            (match_id,),
        ).fetchall()
        pairs.append((_match_key(home, away, hs, as_),
                      {"s": season, "gr": code, "g": [list(g) for g in goals]}))
    return _keyed_or_dup(pairs + _fp_goal_entries(conn, category))


def _running(goals):
    """[[minuto, nombre, marcador parcial, lado, tipo]] con el parcial, si todos los goles tienen
    minuto (orden estable por minuto); si no, sin parcial."""
    if any(g[0] is None for g in goals):
        return [[g[0], g[1], None, g[3], g[4]] for g in goals]
    h = a = 0
    out = []
    for g in sorted(goals, key=lambda g: g[0]):
        h, a = (h + 1, a) if g[3] == "h" else (h, a + 1)
        out.append([g[0], g[1], f"{h}-{a}", g[3], g[4]])
    return out


def _fp_goal_entries(conn, category=None):
    """[(clave, entrada)] de MATCH_DETAIL con los goleadores de la app de futbolaspalmas (fp_goals),
    para los partidos sin cronología de futbolaspalmas del portal antiguo (goals) cuyos goles en la
    app cuadran con el marcador: sin acta, los de la app; con un acta que tiene goles sin nombre
    (niños que la federación no publica), la cronología del acta con esos nombres de pila puestos
    por lado y minuto. Un acta con todos los nombres manda: no sale aquí. `category`, como en _match_details."""
    if not (_has_table(conn, "fp_goals") and _has_table(conn, "fp_matches")):
        return []
    where, args = _category_filter(category)
    rows = conn.execute(
        f"""SELECT m.id, h.name, a.name, m.home_score, m.away_score, s.name, g.code, f.fp_id, m.cod_acta,
                  m.home_team_id
           FROM fp_matches f JOIN matches m ON m.id = f.match_id JOIN groups g ON g.id = m.group_id
           LEFT JOIN categories c ON c.id = g.category_id
           JOIN seasons s ON s.id = g.season_id
           JOIN teams h ON h.id = m.home_team_id JOIN teams a ON a.id = m.away_team_id
           WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM goals x WHERE x.match_id = m.id)
             AND {where}
           ORDER BY m.id""", args).fetchall()
    pairs = []
    for mid, home, away, hs, as_, season, code, fp_id, cod, home_id in rows:
        fp = conn.execute("SELECT side, minute, name FROM fp_goals WHERE fp_id = ? ORDER BY ord", (fp_id,)).fetchall()
        if not fp or (sum(g[0] == "h" for g in fp), sum(g[0] == "a" for g in fp)) != (hs, as_):
            continue
        merged = None
        if cod:
            evs = conn.execute(
                """SELECT e.team_id, e.minute, p.full_name, e.goal_type FROM match_events e
                   JOIN players p ON p.id = e.player_id
                   WHERE e.match_id = ? AND e.kind = 'goal' ORDER BY COALESCE(e.minute, 9999), e.id""",
                (mid,)).fetchall()
            if all(name for _, _, name, _ in evs):
                continue                      # el acta trae todos los nombres
            if len(evs) == hs + as_:
                free = list(fp)
                merged = []
                for team_id, minute, name, gt in evs:
                    side = "h" if team_id == home_id else "a"
                    if gt == "own":
                        side = "a" if side == "h" else "h"
                    if not name:
                        pick = next((g for g in free if g[0] == side and g[1] == minute), None) \
                            or next((g for g in free if g[0] == side), None)
                        if pick:
                            free.remove(pick)
                            name = pick[2]
                    merged.append([minute, name or None, None, side, "o" if gt == "own" else "r"])
        if merged is None:
            merged = [[minute, name, None, side, "r"] for side, minute, name in fp]
        pairs.append((_match_key(home, away, hs, as_),
                      {"s": season, "gr": code, "g": _running(merged), "src": "fp"}))
    return pairs


def generate_matchdetail_js(conn, details=None):
    """Generate data-matchdetail.js with goal details per match. `details`: las entradas de
    _match_details ya calculadas (main las comparte con data-seasons.js)."""
    header = (
        "// data-matchdetail.js — generado por scripts/generate_js.py\n"
        "// NO editar manualmente — usar scripts/update.sh para regenerar\n\n"
    )
    details = _match_details(conn) if details is None else details
    js = header + "const MATCH_DETAIL=" + js_val(details) + ";"
    return js


def generate_matchdetail_lazy_js(conn, category):
    """data-matchdetail-<clave>.js de una categoría de NUEVAS: const MATCH_DETAIL_<S>=…; con la forma de
    MATCH_DETAIL (las claves repetidas, dentro de la categoría). Siempre, aunque vacío ({}), también si la
    categoría no está en categorias.EN_WEB. Aparte porque sus actas de fútbol 11 harían crecer
    data-matchdetail.js para todos."""
    clave, _grupos, s = LAZY[category]
    header = (
        f"// data-matchdetail-{clave}.js — generado por scripts/generate_js.py\n"
        "// NO editar manualmente — usar scripts/update.sh para regenerar\n\n"
    )
    details = _match_details(conn, category) if category in _en_web() else {}
    return header + f"const MATCH_DETAIL_{s}=" + js_val(details) + ";"


def detail_seasons(details):
    """Las temporadas con alguna entrada en MATCH_DETAIL (las de una clave repetida, todas)."""
    return {entry["s"] for value in details.values()
            for entry in (value["list"] if value.get("dup") else [value])}


def _season_const_suffix(season_name):
    return season_name.replace("-", "_")


def lineups_const(season_name, code):
    """Nombre de la constante de data-lineups-<S>-<grupo>.js: LINEUPS_<YYYY_YYYY>_<grupo>."""
    return f"LINEUPS_{_season_const_suffix(season_name)}_{code}"


def lineups_entries(conn, season_name, code=None, claves=None):
    """[(clave, entrada)] de las actas de la temporada (o de un grupo): la clave es
       "<home>|<away>|<hs>-<as>" y la entrada { s, gr, cod, home:[...], away:[...],
       events:[...], coachH, coachA, ref, delH?, delA? } (s = temporada, gr = código
       del grupo, cod = matches.cod_acta). Cada jugador y el autor de cada suceso llevan "id" (y el que
       entra en un cambio, "id2") con la clave de SU ficha, si se publica (claves_de_ficha, que se puede
       pasar ya hecha en `claves` para no rehacerla grupo a grupo)."""
    season_id = conn.execute("SELECT id FROM seasons WHERE name=?", (season_name,)).fetchone()
    if not season_id:
        return []
    rows = conn.execute("""
      SELECT m.id, t1.name, t2.name, m.home_score, m.away_score, g.code, m.cod_acta
        FROM matches m JOIN groups g ON g.id=m.group_id
        JOIN teams t1 ON t1.id=m.home_team_id JOIN teams t2 ON t2.id=m.away_team_id
       WHERE g.season_id=? AND m.cod_acta IS NOT NULL AND (? IS NULL OR g.code=?)
       ORDER BY m.id""", (season_id[0], code, code)).fetchall()
    if claves is None:
        claves = claves_de_ficha(conn)
    has_all = _has_table(conn, "match_staff_all")
    # Los empatados en rol y dorsal, en el orden del acta: appearances.ord (el id de la fila en una
    # base de antes de migrate_compactar).
    tiebreak = "a.ord" if any(r[1] == "ord" for r in conn.execute("PRAGMA table_info(appearances)")) else "a.id"
    pairs = []
    for mid, h, a, hs, asc, code, cod in rows:
        key = _match_key(h, a, hs, asc)
        apps = conn.execute(f"""
          SELECT a.team_id, p.full_name, a.dorsal, a.role, a.goals, a.yellow, a.red, p.id
            FROM appearances a JOIN players p ON p.id=a.player_id
           WHERE a.match_id=? ORDER BY a.role DESC, a.dorsal, {tiebreak}""", (mid,)).fetchall()
        home_team_id = conn.execute("SELECT home_team_id FROM matches WHERE id=?", (mid,)).fetchone()[0]

        def player(r):
            # id: la clave de su ficha (data-jugadores), la misma en todas sus actas.
            out = {"n": r[1], "dn": r[2], "r": r[3], "g": r[4], "y": r[5], "rd": r[6]}
            if r[7] in claves:
                out["id"] = _id_publico(claves[r[7]])
            return out

        def with_id(ev, pid, field="id"):
            if pid in claves:
                ev[field] = _id_publico(claves[pid])
            return ev
        home = [player(r) for r in apps if r[0] == home_team_id]
        away = [player(r) for r in apps if r[0] != home_team_id]
        evs = conn.execute("""
          SELECT e.id, e.kind, e.team_id, p.full_name, e.minute, e.goal_type, e.pair_id, e.player_id
            FROM match_events e JOIN players p ON p.id=e.player_id
           WHERE e.match_id=? ORDER BY COALESCE(e.minute,9999), e.id""", (mid,)).fetchall()
        events = []
        handled = set()  # event ids already emitted as half of a sub pair
        for eid, kind, tid, name, mn, gt, pid, who in evs:
            side = "h" if tid == home_team_id else "a"
            if kind in ("sub_in", "sub_out") and pid:
                if eid in handled:
                    continue
                # pair ids are MUTUAL (out.pair_id = in.id and vice versa,
                # see import_fiflp_actas.py), so the partner is the event
                # whose id == pid — never this event itself.
                pair = next((e for e in evs if e[0] == pid), None)
                pair_name = pair[3] if pair else None
                pair_who = pair[7] if pair else None
                ev = {"t": "sub", "s": side, "m": mn,
                      "n": name if kind == "sub_out" else pair_name,
                      "n2": name if kind == "sub_in" else pair_name}
                with_id(ev, who if kind == "sub_out" else pair_who)
                with_id(ev, who if kind == "sub_in" else pair_who, "id2")
                events.append(ev)
                handled.add(eid)
                handled.add(pid)
            elif kind in ("sub_in", "sub_out"):
                events.append(with_id({"t": kind, "s": side, "n": name, "m": mn}, who))
            elif kind == "goal":
                # Un gol en propia puerta suma al rival: el lado del gol es el
                # contrario al del jugador que lo marca.
                if gt == "own":
                    side = "a" if side == "h" else "h"
                events.append(with_id({"t": "goal", "s": side, "n": name, "m": mn, "gt": gt}, who))
            else:
                events.append(with_id({"t": kind, "s": side, "n": name, "m": mn}, who))
        ref = conn.execute("SELECT name FROM match_staff WHERE match_id=? AND kind='referee'", (mid,)).fetchone()
        ch = conn.execute("SELECT name FROM match_staff WHERE match_id=? AND kind='coach' AND team_id=?", (mid, home_team_id)).fetchone()
        ca = conn.execute("SELECT name FROM match_staff WHERE match_id=? AND kind='coach' AND team_id!=?", (mid, home_team_id)).fetchone()
        entry = {"s": season_name, "gr": code, "cod": cod,
                 "home": home, "away": away, "events": events,
                 "coachH": ch[0] if ch else None,
                 "coachA": ca[0] if ca else None,
                 "ref":    ref[0] if ref else None}
        # Todo el cuerpo técnico de cada equipo y los árbitros, con el cargo del acta (match_staff_all; las
        # filas de ord negativo no son del acta: solo constaban en la antigua tabla match_staff).
        if has_all:
            rows_s = conn.execute("""SELECT team_id, role, name FROM match_staff_all WHERE match_id=? AND ord >= 0
                                     ORDER BY ord""", (mid,)).fetchall()
            for key_s, test in (("stH", lambda t: t == home_team_id),
                                ("stA", lambda t: t is not None and t != home_team_id),
                                ("refs", lambda t: t is None)):
                found = [[role, name] for t, role, name in rows_s if test(t)]
                if found:
                    entry[key_s] = found
        # Delegados (de campo y de equipo) del acta de la federación, si los hay.
        for side_key, cmp in (("delH", "="), ("delA", "!=")):
            rows_d = conn.execute(f"""SELECT kind, name FROM match_staff WHERE match_id=?
                                      AND kind IN ('delegate_field','delegate_team') AND team_id{cmp}?""",
                                  (mid, home_team_id)).fetchall()
            if rows_d:
                entry[side_key] = {("campo" if k == "delegate_field" else "equipo"): n for k, n in rows_d}
        pairs.append((key, entry))
    return pairs


def generate_lineups_js(conn, season_name, code, claves=None):
    """data-lineups-<S>-<grupo>.js: las actas de UN grupo de la temporada.
       const LINEUPS_<YYYY_YYYY>_<grupo> = { "<home>|<away>|<hs>-<as>": { s, gr, cod, ... } };
       Una clave que comparten dos o más partidos del grupo es
       { dup: true, list: [ {s, gr, cod, home, ...}, ... ] }.
       Por grupo y no por temporada: una temporada entera con todas sus actas
       pesa ~10 MB, y la ficha de un equipo o un partido solo necesita su grupo."""
    obj = _keyed_or_dup(lineups_entries(conn, season_name, code, claves))
    return ("// Auto-generated by scripts/generate_js.py — do not edit\n"
            "const " + lineups_const(season_name, code) + " = " + json.dumps(obj, ensure_ascii=False) + ";\n")


LINEUPS_FILE = re.compile(r"^data-lineups-(\d{4}-\d{4})-([A-Za-z0-9]+)\.js$")


def lineups_files(conn):
    """{fichero: contenido} de los data-lineups-<S>-<grupo>.js: uno por grupo con
       alguna acta."""
    out = {}
    claves = claves_de_ficha(conn)          # una vez, no grupo a grupo
    for sname, code in conn.execute("""
        SELECT DISTINCT s.name, g.code FROM matches m JOIN groups g ON g.id=m.group_id
          JOIN seasons s ON s.id=g.season_id
         WHERE m.cod_acta IS NOT NULL ORDER BY s.name, g.code""").fetchall():
        out[f"data-lineups-{sname}-{code}.js"] = generate_lineups_js(conn, sname, code, claves)
    return out


def write_lineups(conn, root=None):
    """Escribe los data-lineups-<S>-<grupo>.js y borra los que ya no tocan: los
       de un grupo que ya no tiene actas y los antiguos, de temporada entera
       (data-lineups-<S>.js)."""
    root = root or PROJECT_ROOT
    files = lineups_files(conn)
    for name in sorted(os.listdir(root)):
        if name.startswith("data-lineups-") and name.endswith(".js") and name not in files:
            os.remove(os.path.join(root, name))
            print(f"  {name}: borrado")
    for name, content in files.items():
        escribir_atomico(os.path.join(root, name), content)
    print(f"  {len(files)} ficheros data-lineups-<S>-<grupo>.js")
    return files


# La ficha de cada niño (docs/identidad.md: una o varias identidades de acta con una principal):
# 64 ficheros, el de su clave pública (identidad.trozo), para que abrir una ficha no baje todas. Eran 16; con
# las categorías nuevas habrá unas seis veces más fichas, y con 16 cada trozo pasaría del megabyte (hoy, con
# 64, ~80 KB cada uno).
# Cambiar el número no cambia ninguna clave, solo el fichero en el que va cada una (src/state.js, igual).
JUGADORES_SHARDS = 64
# union_por → el motivo corto de una fila unida en data-jugadores (la ficha lo dice en esa línea).
_MOTIVO = {"equipo": "e", "club": "c", "nombre": "n"}


def _orden_clave(k):
    """Las numéricas primero, por su valor; después las 'n…'."""
    return (0, int(k), "") if k.isdigit() else (1, 0, k)


def _fichas(conn):
    """Las identidades de acta con su clave pública y su ficha, para publicar:
    {"clave": {player_id: clave de la identidad}, "ficha": {player_id: id de la principal},
     "por": {player_id: union_por}, "publicadas": {id de la principal} (fichas con alguna aparición)}.
    Sin las columnas de las fichas (una base sin migrar: migrate_identidad.py), cada fila es su ficha y
    solo las de fiflp_id tienen clave. El gol «sin nombre publicado» y las filas sin id ni equipo no tienen.
    Una identidad sin id nunca deja su ficha sin publicar: sin clave guardada y con el equipo o la
    temporada borrados, la de su equipo y temporada más frecuentes en sus apariciones; y si ni así, la
    ficha sale con la clave de otra identidad suya."""
    from identidad import clave_publica          # aquí: identidad.py importa generate_js
    from migrate_identidad import equipo_de_sus_apariciones, nombre_base
    cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    if "fiflp_id" not in cols:
        return {"clave": {}, "ficha": {}, "por": {}, "publicadas": set(), "nombre": {}}
    c2 = {"ficha_id", "union_por", "team_id", "season_id", "ordinal"} <= cols
    sel = ("p.ficha_id, p.union_por, p.team_id, t.name, s.start_year, p.ordinal" if c2
           else "NULL, NULL, NULL, NULL, NULL, NULL")
    sel += ", p.clave" if "clave" in cols else ", NULL"
    join = ("LEFT JOIN teams t ON t.id = p.team_id LEFT JOIN seasons s ON s.id = p.season_id" if c2 else "")
    filas = conn.execute(f"SELECT p.id, p.norm_name, p.fiflp_id, {sel} FROM players p {join}").fetchall()
    existe = {r[0] for r in filas}
    clave, ficha, por, nombre = {}, {}, {}, {}
    sin_equipo = {}             # player_id -> nombre con su ordinal: el equipo o la temporada ya no existen
    for pid, norm_name, fid, ficha_id, union_por, team_id, equipo, anio, ordinal, guardada in filas:
        base = nombre_base(norm_name)
        nombre[pid] = base
        ficha[pid] = ficha_id if ficha_id in existe else pid
        if ficha[pid] != pid:
            por[pid] = union_por
        if fid is not None:
            clave[pid] = str(int(fid))
        elif guardada:
            # La guardada al crear la identidad (migrate_identidad.poner_claves): no cambia si el equipo
            # cambia de nombre o de fila.
            clave[pid] = guardada
        elif base and not base.startswith("#") and (team_id is not None or equipo is not None):
            norm = base + (f"#{ordinal}" if ordinal and ordinal > 1 else "")
            if equipo is not None and anio is not None:
                clave[pid] = clave_publica(None, norm, equipo, anio)
            else:
                sin_equipo[pid] = norm
    for pid, (equipo, anio) in equipo_de_sus_apariciones(conn, sin_equipo).items():
        clave[pid] = clave_publica(None, sin_equipo[pid], equipo, anio)
    # Una principal que sigue sin clave: la de otra identidad de su ficha (la numérica menor, si hay).
    sin_clave = {ficha[pid] for pid in ficha if ficha[pid] not in clave}
    if sin_clave:
        for pid in sorted(ficha):
            p = ficha[pid]
            if p in sin_clave and pid in clave and (p not in clave or _orden_clave(clave[pid]) < _orden_clave(clave[p])):
                clave[p] = clave[pid]
    con_apariciones = {pid for (pid,) in conn.execute("SELECT DISTINCT player_id FROM appearances")} \
        if _has_table(conn, "appearances") else set()
    publicadas = {ficha[pid] for pid in con_apariciones if pid in ficha and ficha[pid] in clave}
    return {"clave": clave, "ficha": ficha, "por": por, "publicadas": publicadas, "nombre": nombre}


def claves_de_ficha(conn, fichas=None):
    """{player_id: clave de SU ficha} de las identidades cuya ficha se publica en data-jugadores (lo que
    llevan las alineaciones y los sucesos en "id"); las demás, sin clave."""
    f = fichas or _fichas(conn)
    return {pid: f["clave"][p] for pid, p in f["ficha"].items() if p in f["publicadas"]}


def _id_publico(clave):
    """La clave como va en "id" de las alineaciones: un número si es un id de la federación (como hasta
    ahora) y el texto 'n…' si no."""
    return int(clave) if clave and clave.isdigit() else clave


def _season_day(text, start_year):
    """'AAAA-MM-DD', 'DD-MM-AAAA' o 'DD/MM' (sin año: de julio a diciembre, el año de inicio de la
    temporada) → 'AAAA-MM-DD', o None."""
    text = (text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return text
    m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?", text)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = int(m.group(3)) if m.group(3) else (start_year if month >= 7 else start_year + 1)
    return f"{year:04d}-{month:02d}-{day:02d}"


# El año de nacimiento confirmado por una fuente pública, que manda sobre el estimado (docs/ranking.md). Lo
# mantiene una persona a mano: {"<clave>": {"anio": 2010, "fuente": "texto"}}. Empieza vacío.
ANIOS_CONFIRMADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anios_confirmados.json")


def anios_confirmados(path=None):
    """{clave: año} de scripts/anios_confirmados.json (o de `path`). Un fichero que falta o vacío es {}. Uno
    con algo que no sea {clave: {"anio": entero, ...}} es un ValueError con lo que falla: nunca se publica un
    año mal escrito como confirmado. _datos_fichas lo recoge, avisa y sigue sin ninguno (el bot no se para)."""
    path = path or ANIOS_CONFIRMADOS
    try:
        with open(path, encoding="utf-8") as fh:
            texto = fh.read()
    except FileNotFoundError:
        return {}
    if not texto.strip():
        return {}
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: no es JSON ({e})") from e
    if not isinstance(datos, dict):
        raise ValueError(f"{path}: tiene que ser un objeto {{clave: {{\"anio\": año, \"fuente\": texto}}}}")
    out = {}
    for clave, valor in datos.items():
        anio = valor.get("anio") if isinstance(valor, dict) else None
        # bool es un int en Python: true no es un año.
        if not isinstance(anio, int) or isinstance(anio, bool):
            raise ValueError(f"{path}: la clave {clave!r} no tiene un \"anio\" entero: {valor!r}")
        out[str(clave)] = anio
    return out


def _rival_y_puesto(conn):
    """Lo que el ranking necesita de las temporadas y de las tablas de los grupos, sacado de los partidos
    (para lo que encaja cada equipo y su puesto, solo los que tienen marcador; uno fuera de
    [0, MAX_SANE_SCORE] es un dato roto y no cuenta). Devuelve
    ([(partido, equipo, peso de un gol de ese equipo en ese partido), ...], {(grupo, equipo): percentil},
     {(temporada, categoría, equipo): su mejor letra de Segunda Fase}), con las ids de las tablas.

    El peso (ranking.peso_rival) es el de su rival, con lo que el rival encaja en TODA su temporada de esa
    categoría (primera fase, eliminatorias, segunda fase y copas juntas) y con prudencia
    (ranking.encajados_prudente), frente a la media de la temporada y la categoría (sus goles entre dos veces
    sus partidos); redondeado a 4 cifras y solo si no es 1. El percentil es del grupo: entre los equipos con
    MIN_PARTIDOS_EQUIPO partidos o más en él, por puntos por partido (a igualdad, diferencia de goles por
    partido y el id del equipo, para que sea determinista), 1 el primero y 0 el último, lineal por puesto;
    sin percentil los de menos partidos y los de un grupo con menos de dos equipos que cuenten. La mejor
    letra: la más alta (A antes que B) de los grupos «Segunda Fase X» de esa temporada y categoría en los que
    está el equipo, por su clasificación o por sus partidos, jugados o no (ranking.fase_que_cuenta)."""
    import ranking as R
    tabla = {}                       # (grupo, equipo) → [partidos, a favor, en contra, puntos]
    temporada = {}                   # (temporada, categoría, equipo) → [partidos, en contra]
    goles, jugados = {}, {}          # (temporada, categoría) → goles y partidos con marcador
    partidos = conn.execute("""SELECT m.id, m.group_id, g.season_id, g.category_id, m.home_team_id,
                                      m.away_team_id, m.home_score, m.away_score
                                 FROM matches m JOIN groups g ON g.id = m.group_id ORDER BY m.id""").fetchall()
    for _mid, gid, sid, cid, local, visitante, gl, gv in partidos:
        if local == visitante or gl is None or gv is None:
            continue
        if not (0 <= gl <= MAX_SANE_SCORE and 0 <= gv <= MAX_SANE_SCORE):
            continue
        goles[(sid, cid)] = goles.get((sid, cid), 0) + gl + gv
        jugados[(sid, cid)] = jugados.get((sid, cid), 0) + 1
        for equipo, a_favor, en_contra in ((local, gl, gv), (visitante, gv, gl)):
            fila = tabla.setdefault((gid, equipo), [0, 0, 0, 0])
            fila[0] += 1
            fila[1] += a_favor
            fila[2] += en_contra
            fila[3] += 3 if a_favor > en_contra else 1 if a_favor == en_contra else 0
            suya = temporada.setdefault((sid, cid, equipo), [0, 0])
            suya[0] += 1
            suya[1] += en_contra
    media = {k: goles[k] / (2 * n) for k, n in jugados.items()}
    por_grupo = {}
    for (gid, equipo), (pj, gf, gc, pts) in tabla.items():
        if pj >= R.MIN_PARTIDOS_EQUIPO:
            por_grupo.setdefault(gid, []).append((-pts / pj, -(gf - gc) / pj, equipo))
    percentil = {}
    for gid, equipos in por_grupo.items():
        if len(equipos) < 2:
            continue
        equipos.sort()
        for puesto, (_, _, equipo) in enumerate(equipos, 1):
            percentil[(gid, equipo)] = 1 - (puesto - 1) / (len(equipos) - 1)
    pesos = []
    for mid, _gid, sid, cid, local, visitante, _, _ in partidos:
        if local == visitante:
            continue
        m = media.get((sid, cid))
        for equipo, rival in ((local, visitante), (visitante, local)):
            pj, en_contra = temporada.get((sid, cid, rival), (0, 0))
            peso = round(R.peso_rival(R.encajados_prudente(en_contra, pj, m), m), 4)
            if peso != 1.0:
                pesos.append((mid, equipo, peso))
    # La mejor letra de Segunda Fase de cada equipo: esta temporada los grupos de la Segunda Fase ya tienen
    # equipos y calendario aunque casi no se haya jugado, así que valen la clasificación y los partidos.
    letra = {gid: (sid, cid, R.letra_segunda_fase(fase))
             for gid, sid, cid, fase in conn.execute("SELECT id, season_id, category_id, phase FROM groups")}
    letra = {gid: v for gid, v in letra.items() if v[2]}
    en_grupo = set()
    for _mid, gid, _sid, _cid, local, visitante, _, _ in partidos:
        if gid in letra:
            en_grupo |= {(gid, local), (gid, visitante)}
    if _has_table(conn, "standings"):
        en_grupo |= {(gid, t) for gid, t in conn.execute("SELECT group_id, team_id FROM standings")
                     if gid in letra}
    mejor = {}
    for gid, equipo in en_grupo:
        sid, cid, x = letra[gid]
        k = (sid, cid, equipo)
        if k not in mejor or x < mejor[k]:
            mejor[k] = x
    return pesos, percentil, mejor


# La liga de escuelas (MyGol, docs/mygol.md) en las fichas: lo que se lee de las tablas mygol_* para cada ficha
# enlazada (mygol_enlaces, que rehace enlace_mygol en cada pasada).
_TABLAS_ESCUELA = ("mygol_enlaces", "mygol_participaciones", "mygol_partidos", "mygol_torneos", "mygol_equipos")


def _escuela(conn, publicadas):
    """{principal: [[temporada, equipo, categoría, jornadas], ...]} de las fichas publicadas con algún niño de
    MyGol enlazado: una fila por temporada y equipo (y categoría, por si un nombre de equipo se repite en dos
    torneos), en ese orden. El equipo, con los espacios de más quitados; la temporada, «2024-2025»; la
    categoría en minúsculas o None; las jornadas, los partidos en los que consta que jugó (0: estaba en la
    plantilla y no consta ninguno).

    Nunca para al generador: sin las tablas, con un enlace a una identidad que ya no es la principal de una
    ficha publicada (la ficha sale sin él) o con unas tablas que no se entienden (se avisa y no sale ninguna
    escuela), las fichas salen como sin la liga de escuelas."""
    if not all(_has_table(conn, t) for t in _TABLAS_ESCUELA):
        return {}
    try:
        filas = conn.execute("""
            SELECT l.player_id, t.temporada, e.nombre, t.categoria,
                   COUNT(DISTINCT CASE WHEN p.jugo = 1 THEN p.partido_id END)
              FROM mygol_enlaces l JOIN mygol_participaciones p ON p.jugador_id = l.jugador_id
              JOIN mygol_partidos m ON m.id = p.partido_id JOIN mygol_torneos t ON t.id = m.torneo_id
              LEFT JOIN mygol_equipos e ON e.id = p.equipo_id
             GROUP BY l.player_id, t.temporada, p.equipo_id""").fetchall()
    except sqlite3.Error as e:
        print(f"  ! MyGol: la liga de escuelas no se lee ({type(e).__name__}: {e}): las fichas salen sin ella")
        return {}
    juntas = {}
    for principal, temporada, equipo, categoria, jornadas in filas:
        if principal not in publicadas or not re.fullmatch(r"\d{4}-\d{4}", str(temporada or "")):
            continue
        clave = (temporada, " ".join(str(equipo or "").split()), categoria.lower() if categoria else None)
        # El mismo niño apuntado dos veces en un equipo (dos ids de MyGol): las jornadas de los dos, sumadas.
        juntas[(principal, clave)] = juntas.get((principal, clave), 0) + jornadas
    out = {}
    for (principal, (temporada, equipo, categoria)), jornadas in sorted(
            juntas.items(), key=lambda kv: (kv[0][0], kv[0][1][0], kv[0][1][1], kv[0][1][2] or "")):
        out.setdefault(principal, []).append([temporada, equipo, categoria, jornadas])
    return out


def _datos_fichas(conn, confirmados=None):
    """Lo que comparten jugadores_files, buscar_files y ranking_files, sacado de una sola pasada por las
    apariciones (la consulta grande): main() lo calcula una vez y se lo pasa a las tres; cada una, llamada
    sola, lo calcula ella. None si la base no tiene las identidades (sin players.fiflp_id).

    "filas": {principal: [(clave de orden, fila publicada, grupo, fila del ranking), ...]} en orden de
    temporada y de primer día del grupo (a igualdad, la de la principal antes); la fila del ranking es
    (año de inicio, categoría en minúsculas, fase, partidos, titular, goles, goles por rival, isla,
    percentil, temporada, equipo): las nueve primeras, una ranking.Fila. La fase es la que cuenta para el
    nivel (ranking.fase_que_cuenta, con la mejor letra de Segunda Fase de su equipo); la de la ficha ("g")
    sigue siendo la del grupo. Los goles por rival, la suma aparición a aparición de sus goles por el peso
    de su rival en ese partido (_rival_y_puesto), con 4 cifras.
    "anios": {principal: (años, confirmado)}, los de nacimiento.estimar con todas sus filas (y sus
    temporadas de escuela) o el confirmado (anios_confirmados, o `confirmados` si se pasa) de su clave o de uno
    de sus alias.
    "escuela": {principal: [[temporada, equipo, categoría, jornadas], ...]}, la liga de escuelas de las fichas
    enlazadas con MyGol (_escuela)."""
    if not any(r[1] == "fiflp_id" for r in conn.execute("PRAGMA table_info(players)")):
        return None
    import ranking as R
    from nacimiento import estimar
    f = _fichas(conn)
    clave, ficha, publicadas = f["clave"], f["ficha"], f["publicadas"]
    # El primer día de cada grupo (las fechas vienen en tres formatos).
    first_day = {}
    for gid, day, start in conn.execute("""SELECT m.group_id, m.date, s.start_year FROM matches m
                                             JOIN groups g ON g.id=m.group_id JOIN seasons s ON s.id=g.season_id"""):
        iso = _season_day(day, start)
        if iso and (gid not in first_day or iso < first_day[gid]):
            first_day[gid] = iso
    # El peso de cada gol por su rival va en una tabla temporal, para sumarlo en la misma consulta grande
    # (aparición a aparición en Python serían 400.000 vueltas). Sin fila, el gol vale 1.
    pesos, percentil, mejor = _rival_y_puesto(conn)
    abierta = conn.in_transaction            # lo que el que llama tuviera a medias no se confirma aquí
    conn.execute("DROP TABLE IF EXISTS temp._peso_rival")
    conn.execute("CREATE TEMP TABLE _peso_rival (match_id INTEGER, team_id INTEGER, peso REAL, "
                 "PRIMARY KEY (match_id, team_id))")
    conn.executemany("INSERT INTO temp._peso_rival VALUES (?, ?, ?)", pesos)
    rows = conn.execute("""
        SELECT p.id, s.name, s.start_year, g.id, g.code, t.name, COUNT(*),
               SUM(a.role='starter'), SUM(a.goals), SUM(a.yellow), SUM(a.red),
               LOWER(c.name), g.name, g.phase, g.island, a.team_id, SUM(a.goals * COALESCE(w.peso, 1.0)),
               g.season_id, g.category_id
          FROM appearances a JOIN players p ON p.id=a.player_id
          JOIN matches m ON m.id=a.match_id JOIN groups g ON g.id=m.group_id
          JOIN seasons s ON s.id=g.season_id JOIN teams t ON t.id=a.team_id
          JOIN categories c ON c.id=g.category_id
          LEFT JOIN temp._peso_rival w ON w.match_id=a.match_id AND w.team_id=a.team_id
         GROUP BY p.id, g.id, a.team_id""").fetchall()
    conn.execute("DROP TABLE temp._peso_rival")
    if not abierta and conn.in_transaction:
        conn.commit()
    # Por ficha: sus filas en orden de temporada y primer día del grupo; a igualdad, la de la principal antes.
    por_ficha = {}
    for (pid, season, year, gid, code, team, pj, tit, goals, yellow, red, cat, gname, phase, island,
         team_id, por_rival, sid, cid) in rows:
        principal = ficha.get(pid)
        if principal not in publicadas:
            continue
        motivo = [] if principal == pid else [1, _MOTIVO.get(f["por"].get(pid))] if f["por"].get(pid) in _MOTIVO else [1]
        por_ficha.setdefault(principal, []).append(
            ((year, first_day.get(gid, "9999"), code, team, len(motivo), motivo),
             [season, code, team, pj, tit, goals, yellow, red, *motivo], (season, code, cat, gname, phase, island),
             (year, cat, R.fase_que_cuenta(phase, mejor.get((sid, cid, team_id))), pj, tit, goals,
              round(por_rival or 0.0, 4), island, percentil.get((gid, team_id)), season, team)))
    for filas in por_ficha.values():
        filas.sort(key=lambda x: x[0])
    miembros = {}
    for pid, principal in ficha.items():
        miembros.setdefault(principal, []).append(pid)
    # El año de nacimiento. Una observación por temporada y categoría (las de todas sus identidades juntas,
    # como las ve la ficha); el confirmado manda: el de la clave de la ficha y, si no, el del primero de sus
    # alias que lo tenga.
    if confirmados is None:
        # Un fichero mal escrito no para al bot (la web dejaría de actualizarse): se avisa y se publica sin
        # ningún año confirmado (todo o nada: con una entrada mala no se fía de las demás).
        try:
            confirmados = anios_confirmados()
        except (ValueError, OSError) as e:
            print(f"  ! anios_confirmados.json no se entiende ({e}): se publica sin años confirmados")
            confirmados = {}
    escuela = _escuela(conn, publicadas)
    anios = {}
    for principal, filas in por_ficha.items():
        k = clave[principal]
        otras = sorted((clave[m] for m in miembros[principal] if m in clave and clave[m] != k), key=_orden_clave)
        anio = next((confirmados[c] for c in [k, *otras] if c in confirmados), None)
        if anio is not None:
            anios[principal] = ((anio,), True)
            continue
        partidos = {}
        for year, cat, _phase, pj, *_ in (r for *_, r in filas):
            partidos[(year, cat)] = partidos.get((year, cat), 0) + pj
        obs = [(y, c, p) for (y, c), p in partidos.items()]
        # La escuela, una observación aparte por temporada y categoría conocida (sus equipos juntos), con sus
        # jornadas; una temporada en la plantilla sin ninguna jugada apuntada cuenta con el peso mínimo. Las
        # federadas no cambian: con dos años solo en la federación, la escuela suele decidir el bueno.
        de_escuela = {}
        for temporada, _equipo, categoria, jornadas in escuela.get(principal, []):
            if categoria:
                k = (int(temporada[:4]), categoria)
                de_escuela[k] = de_escuela.get(k, 0) + jornadas
        obs += [(y, c, max(1, j)) for (y, c), j in de_escuela.items()]
        anios[principal] = (estimar(obs), False)
    return {"fichas": f, "filas": por_ficha, "miembros": miembros, "anios": anios, "escuela": escuela,
            "nombres": dict(conn.execute("SELECT id, full_name FROM players")),
            # El último equipo y la temporada de cada ficha (lo que dicen "h" y el buscador).
            "ultimo": {p: (filas[-1][1][2], filas[-1][1][0]) for p, filas in por_ficha.items()}}


def jugadores_files(conn, datos=None):
    """{fichero: contenido} de los data-jugadores-<k>.js: const JUGADORES_<k> =
       {"p": {"<clave>": {"n": nombre, "c": [fila, ...], "y"?: [año, ...], "yc"?: 1,
                          "e"?: [[temporada, equipo, categoría, jornadas], ...], "s"?: 1,
                          "h"?: [[clave, equipo, temporada], ...], "al"?: [alias, ...]}},
        "a": {"<alias>": "<clave>"},
        "g": {"<temporada>/<grupo>": [categoría, nombre, fase, isla]}}.
       Una entrada por ficha con alguna aparición, en el trozo de su clave (la de su principal), con las
       apariciones de todas sus identidades: una fila [temporada, grupo, equipo, partidos, titular, goles,
       amarillas, rojas] por identidad, grupo y equipo, en orden de temporada y de primer partido del grupo;
       la de una identidad unida lleva además 1 y el motivo ("e" equipo, "c" club, "n" nombre) y no se suma
       a la de la principal. "y": los años de nacimiento posibles, de uno a tres y en orden (sin la clave si
       no se puede estimar; con la escuela, si la tiene); "yc": 1, el año es confirmado (anios_confirmados).
       "e": la liga de escuelas (MyGol) de una ficha enlazada por el nombre (_escuela), una fila por temporada
       y equipo; sin enlace, la ficha no la lleva. "s": 1, ninguna identidad
       con id; "h", las otras fichas con el mismo nombre normalizado (su último equipo y temporada); "al",
       sus alias. Cada alias (la clave de una identidad no principal con aparición o suceso) va en "a" del
       trozo DEL ALIAS, para abrirlo sin saber la clave.
       "g": de cada grupo, lo que la app necesita para nombrarlo (model.groupLabel)."""
    datos = _datos_fichas(conn) if datos is None else datos
    if datos is None:
        return {}
    from identidad import trozo
    f, por_ficha, miembros, ultimo = datos["fichas"], datos["filas"], datos["miembros"], datos["ultimo"]
    clave, publicadas, names = f["clave"], f["publicadas"], datos["nombres"]
    fids = {pid for (pid,) in conn.execute("SELECT id FROM players WHERE fiflp_id IS NOT NULL")}
    con_algo = {pid for (pid,) in conn.execute("SELECT DISTINCT player_id FROM appearances")}
    if _has_table(conn, "match_events"):
        con_algo |= {pid for (pid,) in conn.execute("SELECT DISTINCT player_id FROM match_events")}
    # Las otras fichas con el mismo nombre normalizado (el de la principal): [clave, último equipo, temporada].
    por_nombre = {}
    for principal in publicadas:
        por_nombre.setdefault(f["nombre"][principal], []).append(principal)

    shards = [{"p": {}, "a": {}, "g": {}} for _ in range(JUGADORES_SHARDS)]
    for principal in sorted(por_ficha, key=lambda p: _orden_clave(clave[p])):
        k = clave[principal]
        shard = shards[trozo(k, JUGADORES_SHARDS)]
        entry = {"n": names[principal], "c": [fila for _, fila, _, _ in por_ficha[principal]]}
        anios, confirmado = datos["anios"][principal]
        if anios:
            entry["y"] = list(anios)
            if confirmado:
                entry["yc"] = 1
        if principal in datos.get("escuela", {}):
            entry["e"] = datos["escuela"][principal]
        for season, code, cat, gname, phase, island in (g for _, _, g, _ in por_ficha[principal]):
            shard["g"].setdefault(f"{season}/{code}", [cat, gname, phase, island])
        if not any(m in fids for m in miembros[principal]):
            entry["s"] = 1
        # La más reciente primero; a igualdad, por clave.
        otras = sorted(sorted((p for p in por_nombre[f["nombre"][principal]] if p != principal and p in ultimo),
                              key=lambda p: _orden_clave(clave[p])), key=lambda p: ultimo[p][1], reverse=True)
        if otras:
            entry["h"] = [[clave[p], *ultimo[p]] for p in otras]
        # Sin la clave de la ficha: si la principal no tenía, lleva la de otra de sus identidades (_fichas).
        alias = sorted((clave[m] for m in miembros[principal]
                        if m != principal and m in clave and m in con_algo and clave[m] != k), key=_orden_clave)
        if alias:
            entry["al"] = alias
            for a in alias:
                shards[trozo(a, JUGADORES_SHARDS)]["a"][a] = k
        shard["p"][k] = entry
    return {f"data-jugadores-{k}.js": f"const JUGADORES_{k} = "
            + json.dumps(shard, ensure_ascii=False, separators=(",", ":")) + ";\n"
            for k, shard in enumerate(shards)}


def write_jugadores(conn, root=None, datos=None):
    root = root or PROJECT_ROOT
    files = jugadores_files(conn, datos)
    for name, content in files.items():
        escribir_atomico(os.path.join(root, name), content)
    total = sum(len(c) for c in files.values())
    print(f"  {len(files)} ficheros data-jugadores-<k>.js, {total:,} bytes")
    return files


# El buscador de jugadores (Explorar): un fichero por las dos primeras letras de cada palabra del nombre, que
# la web pide al escribir (no van en la portada ni en el precache). La web normaliza lo que se escribe igual
# (src/, playerSearchPrefix): sin tildes, en minúsculas y partiendo por lo que no es una letra.
_PARTICULAS = frozenset({"de", "del", "la", "las", "los", "y", "da", "do"})


def _palabras(nombre):
    """Las palabras de un nombre, sin tildes (ñ → n) y en minúsculas; lo que no es una letra de la a a la z
    las separa. Como la web (NFD y fuera las marcas)."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", nombre or "")
                if not unicodedata.category(ch).startswith("M")).lower()
    return [w for w in re.split(r"[^a-z]+", s) if w]


def prefijos_de(nombre):
    """Los prefijos de búsqueda de un nombre, cada uno una vez y en el orden en que salen: las dos primeras
    letras de cada palabra de dos letras o más que no sea una partícula (de, del, la, las, los, y, da, do)."""
    return list(dict.fromkeys(w[:2] for w in _palabras(nombre) if len(w) > 1 and w not in _PARTICULAS))


def buscar_files(conn, datos=None):
    """{fichero: contenido} de los data-buscar-<xy>.js: const BUSCAR_<XY> = [[clave, nombre, último equipo,
    última temporada, [años]], ...]; una ficha en el de cada prefijo distinto de su nombre (prefijos_de), en
    orden de clave. [años] es su "y" de data-jugadores ([] si no tiene). Solo los prefijos con alguna."""
    datos = _datos_fichas(conn) if datos is None else datos
    if datos is None:
        return {}
    clave, names = datos["fichas"]["clave"], datos["nombres"]
    por_prefijo = {}
    for principal in sorted(datos["filas"], key=lambda p: _orden_clave(clave[p])):
        nombre = names[principal]
        entrada = [clave[principal], nombre, *datos["ultimo"][principal], list(datos["anios"][principal][0])]
        for xy in prefijos_de(nombre):
            por_prefijo.setdefault(xy, []).append(entrada)
    return {f"data-buscar-{xy}.js": f"const BUSCAR_{xy.upper()} = "
            + json.dumps(entradas, ensure_ascii=False, separators=(",", ":")) + ";\n"
            for xy, entradas in sorted(por_prefijo.items())}


def _borrar_sobrantes(root, empieza, files):
    """Borra los <empieza>*.js del árbol que esta pasada ya no publica (como write_lineups con los suyos)."""
    for name in sorted(os.listdir(root)):
        if name.startswith(empieza) and name.endswith(".js") and name not in files:
            os.remove(os.path.join(root, name))
            print(f"  {name}: borrado")


def write_buscar(conn, root=None, datos=None):
    """Escribe los data-buscar-<xy>.js y borra los de un prefijo que ya no tiene ninguna ficha."""
    root = root or PROJECT_ROOT
    files = buscar_files(conn, datos)
    _borrar_sobrantes(root, "data-buscar-", files)
    for name, content in files.items():
        escribir_atomico(os.path.join(root, name), content)
    total = sum(len(c.encode()) for c in files.values())
    print(f"  {len(files)} ficheros data-buscar-<xy>.js, {total:,} bytes")
    return files


def ranking_files(conn, datos=None):
    """{fichero: contenido} del ranking por año de nacimiento (ranking.py; docs/ranking.md):
    data-ranking.js, const RANKING = {"temporada": <la de seasons.is_current, o null>,
                                      "anios": {"<año>": [entradas en "t", entradas en "h"], ...}};
    y, de cada año con alguna entrada, data-ranking-<año>.js, const RANKING_<año> = {"t": [...], "h": [...]}.
    "t" es esta temporada (sus filas, con al menos MIN_TEMPORADA partidos) y "h" toda la trayectoria (al menos
    MIN_TRAYECTORIA). Cada entrada: [clave, nombre, equipo, categoría, partidos, titular, goles, índice,
    dudoso]: los goles, los de verdad (el índice, ranking.indice, los pondera por el rival, la liga y su
    isla, el equipo y la edad); equipo y categoría, los de la fila más reciente de las que cuentan; dudoso,
    1 si la ficha tiene más de un año posible (sale en el de cada uno, con el índice de ese año). Orden:
    índice y goles de mayor
    a menor y después la clave; como mucho TOPE por lista. data-ranking.js sale siempre que la base tenga
    las identidades (aunque sin años: la web lo pide para saber qué años hay); sin ellas, como las fichas,
    nada."""
    import ranking as R              # aquí, como identidad: los valores se leen al llamar
    from nacimiento import VENTANA
    datos = _datos_fichas(conn) if datos is None else datos
    if datos is None:
        return {}
    actual = conn.execute("SELECT name FROM seasons WHERE is_current = 1 ORDER BY start_year DESC").fetchone()
    temporada = actual[0] if actual else None
    listas = {}                      # año → {"t": [...], "h": [...]}
    clave, names = datos["fichas"]["clave"], datos["nombres"]
    filas = {p: [r for *_, r in fs] for p, fs in datos["filas"].items()}
    # La media de goles por partido de cada temporada y categoría, con las filas de todas las fichas.
    medias = R.medias_de(r[:9] for fs in filas.values() for r in fs)
    for principal, fs in filas.items():
        anios = datos["anios"][principal][0]
        # Las que cuentan para el índice (ranking.indice): categoría conocida y con media.
        cuentan = [r for r in fs if r[1] in VENTANA and medias.get((r[0], r[1]))]
        vistas = (("t", [r for r in cuentan if r[9] == temporada], R.MIN_TEMPORADA),
                  ("h", cuentan, R.MIN_TRAYECTORIA))
        for vista, rs, minimo in vistas:
            partidos = sum(r[3] for r in rs)
            if not rs or partidos < minimo:
                continue
            # La más reciente: la última en el orden de la ficha (temporada y primer día del grupo).
            reciente = rs[-1]
            for anio in anios:
                listas.setdefault(anio, {"t": [], "h": []})[vista].append(
                    [clave[principal], names[principal], reciente[10], reciente[1], partidos,
                     sum(r[4] for r in rs), sum(r[5] for r in rs),
                     R.indice((r[:9] for r in rs), anio, medias), 1 if len(anios) > 1 else 0])
    out = {}
    resumen = {}
    for anio in sorted(listas):
        vistas = listas[anio]
        for vista in vistas.values():
            vista.sort(key=lambda e: (-e[7], -e[6], _orden_clave(e[0])))
            del vista[R.TOPE:]
        resumen[str(anio)] = [len(vistas["t"]), len(vistas["h"])]
        out[f"data-ranking-{anio}.js"] = (f"const RANKING_{anio} = "
                                          + json.dumps(vistas, ensure_ascii=False, separators=(",", ":")) + ";\n")
    cabecera = {"temporada": temporada, "anios": resumen}
    out["data-ranking.js"] = "const RANKING = " + json.dumps(cabecera, ensure_ascii=False, separators=(",", ":")) + ";\n"
    return out


def write_ranking(conn, root=None, datos=None):
    """Escribe data-ranking.js y los data-ranking-<año>.js, y borra los de un año que ya no tiene entradas."""
    root = root or PROJECT_ROOT
    files = ranking_files(conn, datos)
    _borrar_sobrantes(root, "data-ranking-", files)
    for name, content in files.items():
        escribir_atomico(os.path.join(root, name), content)
    total = sum(len(c.encode()) for c in files.values())
    print(f"  {len(files)} ficheros data-ranking*.js, {total:,} bytes")
    return files


def generate_shields_js(conn):
    """Generate data-shields.js with team shield filenames."""
    rows = conn.execute(
        "SELECT name, shield_filename FROM teams WHERE shield_filename IS NOT NULL ORDER BY name"
    ).fetchall()

    shields = {}
    for name, filename in rows:
        shields[name] = filename

    return "const SHIELDS=" + js_val(shields) + ";\n"


def _goleadores_group_name(code, full_name, category_name):
    """
    Convert a group code + full_name into the goleadores display name.

    Benjamin examples:
      A1 + 'SEGUNDA FASE BENJAMIN A-G1' -> 'BENJAMIN SEGUNDA FASE A-G1'
      LZ1 + 'Benjamin Lanzarote Grupo 1' -> 'BENJAMIN PRIMERA LANZAROTE G1'
      FO + 'Benjamin Fuerteventura Liga Oro' -> 'BENJAMIN FUERTEVENTURA LIGA ORO'

    Prebenjamin examples:
      PG1 + 'PREBENJAMIN PRIMERA GRAN CANARIA G-1' -> 'PREBENJAMIN GC GRUPO 1'
    """
    upper = full_name.upper()

    if category_name in LAZY:
        # 'ALEVIN PRIMERA FASE GC - GRUPO 1' -> 'ALEVIN PRIMERA FASE GC - GRUPO 1'
        # 'LIGA INFANTIL PREFERENTE DE GRAN CANARIA - GRUPO 1' -> 'INFANTIL LIGA PREFERENTE DE GRAN CANARIA - GRUPO 1'
        # («INFANTILL», así en el catálogo de 2024-25, también se quita).
        word = r"\bINFANTILL?\b" if category_name == "INFANTIL" else rf"\b{category_name}\b"
        cleaned = re.sub(word + r"\s*", "", upper).strip()
        return f"{category_name} {cleaned}".strip()

    if category_name == "PREBENJAMIN":
        # 'PREBENJAMIN PRIMERA GRAN CANARIA G-N' -> 'PREBENJAMIN GC GRUPO N'
        m = re.search(r"G-?(\d+)", upper)
        if m:
            return f"PREBENJAMIN GC GRUPO {m.group(1)}"
        return upper

    # BENJAMIN
    if "FUERTEVENTURA" in upper:
        # 'Benjamin Fuerteventura Liga Oro' -> 'BENJAMIN FUERTEVENTURA LIGA ORO'
        cleaned = re.sub(r"\bBENJAMIN\b\s*", "", upper).strip()
        return f"BENJAMIN {cleaned}"

    if "LANZAROTE" in upper:
        # 'Benjamin Lanzarote Grupo N' -> 'BENJAMIN PRIMERA LANZAROTE GN'
        m = re.search(r"GRUPO\s*(\d+)", upper)
        if m:
            return f"BENJAMIN PRIMERA LANZAROTE G{m.group(1)}"
        cleaned = re.sub(r"\bBENJAMIN\b\s*", "", upper).strip()
        return f"BENJAMIN {cleaned}"

    # GC segunda fase: 'SEGUNDA FASE BENJAMIN X-GN' -> 'BENJAMIN SEGUNDA FASE X-GN'
    cleaned = re.sub(r"\bBENJAMIN\b\s*", "", upper).strip()
    return f"BENJAMIN {cleaned}"


def goleadores_entries(conn, cat_name, season_name=None):
    """[{id, g, s: [[jugador, equipo, goles, partidos]]}] de una categoría, de la
    temporada actual o de `season_name`. Los niños sin nombre publicado llevan la
    clave '#<grupo>-<n>' (el frontend dice «Sin nombre publicado»)."""
    if season_name is None:
        groups = get_groups_for_category(conn, cat_name)
    else:
        groups = conn.execute(
            """SELECT g.id, g.code, g.name, g.full_name, g.phase, g.island, g.url, g.current_jornada
               FROM groups g JOIN seasons s ON s.id=g.season_id JOIN categories c ON c.id=g.category_id
               WHERE s.name=? AND UPPER(c.name)=? ORDER BY g.code""", (season_name, cat_name)).fetchall()
    entries = []
    for gid, code, name, full_name, phase, island, url, current_jornada in groups:
        scorers = conn.execute(
            """SELECT s.player_name, t.name, s.goals, s.games
               FROM scorers s JOIN teams t ON s.team_id = t.id
               WHERE s.group_id = ? ORDER BY s.goals DESC, s.games ASC""", (gid,)).fetchall()
        rows, anon = [], 0
        for player, team, goals, games in scorers:
            if not player or player.startswith("#"):
                anon += 1
                player = f"#{code}-{anon}"
            rows.append([player, team, goals, games])
        if scorers:
            entries.append({"id": code, "g": _goleadores_group_name(code, full_name or "", cat_name), "s": rows})
    return entries


def generate_goleadores_js(conn):
    """Generate data-goleadores.js with top scorers per group (temporada actual).

    Reads from the `scorers` table: desde 2026-27, los goleadores de la
    federación (update_fiflp.update_goleadores); antes, los de futbolaspalmas.
    """
    return "\n".join(f"const {var_name}=" + js_val(goleadores_entries(conn, cat_name)) + ";"
                     for cat_name, var_name in [("BENJAMIN", "GOL_BENJ"), ("PREBENJAMIN", "GOL_PREBENJ")])


def venue_key(name):
    """Clave para casar el campo del calendario con el directorio de la
    federación: sin tildes ni signos, y sin el tipo de campo pegado al nombre
    ('Cirilo Lorenzo Alonso F-8' = 'CIRILO LORENZO ALONSO')."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"\(?\bF\s*-?\s*(?:7|8|11)\b\)?", " ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _eager_campos(conn, season_id):
    """Los campos del CAMPOS de data-history.js: los de los partidos y los equipos de la temporada, sin los de
    infantil, cadete y juvenil (NUEVAS: sus partidos y los equipos que solo juegan en ellas)."""
    only = _new_only(conn, season_id)
    return campos_entries(conn, season_venue_names(conn, season_id, keep=lambda t: t not in only,
                                                   exclude=NUEVAS))


def generate_campos_js(conn):
    """CAMPOS (en data-history.js) = {campo: [dirección, localidad, superficie, tipo(, latitud,
    longitud)]} de los partidos y los equipos de la temporada actual (directorio y fichas de campos
    de la federación, campos_entries), sin los que solo son de infantil, cadete o juvenil (CAMPOS_<S>)."""
    row = conn.execute("SELECT id FROM seasons WHERE is_current = 1").fetchone()
    out = _eager_campos(conn, row[0]) if row else {}
    return "const CAMPOS=" + js_val(out) + ";"


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def computed_table(conn, group_id, season_name):
    """¿Es la clasificación del grupo una calculada con sus partidos (import_wayback_portal)?"""
    if not _has_table(conn, "portal_groups"):
        return False
    from import_wayback_portal import COMPUTED_STANDINGS
    return season_name in COMPUTED_STANDINGS and conn.execute(
        "SELECT 1 FROM portal_groups WHERE group_id=? AND mode='group'", (group_id,)).fetchone() is not None


def standings_detail_map(conn, group_id):
    """{equipo: [Jc, Gc, Ec, Pc, Jf, Gf, Ef, Pf, sanción]} de la clasificación detallada de la
    federación (import_fiflp_detalle.py): partidos jugados, ganados, empatados y perdidos en casa y
    fuera, y los puntos de sanción. None si el grupo no la tiene."""
    if not _has_table(conn, "standings_detail"):
        return None
    rows = conn.execute(
        """SELECT t.name, d.home_played, d.home_won, d.home_drawn, d.home_lost,
                  d.away_played, d.away_won, d.away_drawn, d.away_lost, d.sanction
           FROM standings_detail d JOIN teams t ON t.id = d.team_id
           WHERE d.group_id = ? ORDER BY t.name""", (group_id,)).fetchall()
    return {r[0]: list(r[1:]) for r in rows} or None


def zones_of(conn, group_id, teams):
    """[[desde, hasta, tipo, texto]]: qué significa cada puesto de la tabla según la app de
    futbolaspalmas (fp_ligas). Ascenso, playoff, copa y promoción se cuentan desde arriba y el
    descenso desde abajo. None sin datos."""
    if not _has_table(conn, "fp_ligas"):
        return None
    row = conn.execute(
        """SELECT plazas_ascenso, texto_ascenso, plazas_playoff, texto_playoff, plazas_copa, texto_copa,
                  plazas_promocion, texto_promocion, plazas_descenso, texto_descenso
           FROM fp_ligas WHERE group_id = ? ORDER BY liga_id LIMIT 1""", (group_id,)).fetchone()
    if not row:
        return None
    out, pos = [], 1
    for kind, n, text in (("ascenso", row[0], row[1]), ("playoff", row[2], row[3]),
                          ("copa", row[4], row[5]), ("promocion", row[6], row[7])):
        if n and n > 0:
            out.append([pos, pos + n - 1, kind, (text or "").strip() or None])
            pos += n
    if row[8] and row[8] > 0 and teams:
        out.append([max(1, teams - row[8] + 1), teams, "descenso", (row[9] or "").strip() or None])
    return out or None


def team_info_map(conn, season_id, keep=None):
    """{equipo: [camiseta, pantalón, medias, campo, superficie, equipación de futbolaspalmas]} de la
    temporada: el directorio de la federación (team_seasons, import_fiflp_detalle.py) y la app de
    futbolaspalmas (fp_teams: el nombre de su dibujo, «2026-blanca-blanco-blancas.png»). `keep(equipo)`:
    solo los que cumplen (los de alevín, o todos menos los que solo juegan en alevín)."""
    out = {}
    if _has_table(conn, "team_seasons"):
        for name, shirt, shorts, socks, venue, surface in conn.execute(
                """SELECT t.name, ts.shirt, ts.shorts, ts.socks, ts.venue_name, ts.surface
                   FROM team_seasons ts JOIN teams t ON t.id = ts.team_id
                   WHERE ts.season_id = ? ORDER BY t.name""", (season_id,)):
            out[name] = [shirt, shorts, socks, venue, surface, None]
    if _has_table(conn, "fp_teams") and _has_table(conn, "fp_ligas"):
        for name, kit in conn.execute(
                """SELECT t.name, f.equipacion FROM fp_teams f JOIN fp_ligas l ON l.liga_id = f.liga_id
                   JOIN teams t ON t.id = f.team_id
                   WHERE l.season_id = ? AND f.equipacion IS NOT NULL AND f.equipacion <> ''
                   ORDER BY t.name, f.liga_id""", (season_id,)):
            out.setdefault(name, [None] * 6)[5] = kit
    return dict(sorted((k, v) for k, v in out.items() if keep is None or keep(k)))


# Estados de la app de futbolaspalmas que el marcador no dice.
FP_STATES = ("aplazado", "suspendido", "retirado", "anulado")


def match_states_map(conn, season_id, categories=None):
    """{código de grupo: {jornada: {"local|visitante": [estado, motivo, hora real de inicio]}}} de
    los partidos de la temporada (de esas categorías, si se dan) que la app de futbolaspalmas da
    aplazados, suspendidos, retirados o anulados, o con su hora real de inicio (HH:MM)."""
    if not _has_table(conn, "fp_matches"):
        return {}
    out = {}
    cats = tuple(categories or ())
    only = f" AND upper(c.name) IN ({','.join('?' * len(cats))})" if cats else ""
    rows = conn.execute(
        f"""SELECT g.code, m.jornada, h.name, a.name, f.estado, f.motivo_aplazado, f.hora_inicio
           FROM fp_matches f JOIN matches m ON m.id = f.match_id JOIN groups g ON g.id = m.group_id
           JOIN categories c ON c.id = g.category_id
           JOIN teams h ON h.id = m.home_team_id JOIN teams a ON a.id = m.away_team_id
           WHERE g.season_id = ?{only} ORDER BY g.code, m.jornada, h.name""", (season_id, *cats)).fetchall()
    for code, jornada, home, away, estado, motivo, inicio in rows:
        state = estado if estado in FP_STATES else None
        start = (inicio or "")[11:16] if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?", inicio or "") else None
        if not state and not start:
            continue
        out.setdefault(code, {}).setdefault(jornada, {})[f"{home}|{away}"] = [state, (motivo or "").strip() or None, start]
    return out


def campos_entries(conn, venue_names):
    """{campo: [dirección, localidad, superficie, tipo(, latitud, longitud)]} de los campos dados,
    del directorio de la federación (venues) y de sus fichas (venue_details: las coordenadas). Casa
    por venue_key y, si no, por un único campo del directorio que empiece igual; un campo que solo
    está en las fichas (el de un equipo), por su nombre."""
    has = _has_table(conn, "venues")
    directory = conn.execute("SELECT norm, address, city, surface, kind, code FROM venues").fetchall() if has else []
    details = {}
    if _has_table(conn, "venue_details"):
        details = {r[0]: r[1:] for r in conn.execute(
            "SELECT code, name, address, city, surface, lat, lon FROM venue_details")}
    by_key = {r[0]: r[1:] for r in directory}
    by_detail_name = {venue_key(v[0]): (code, v) for code, v in details.items() if v[0]}
    out = {}
    for venue in venue_names:
        key = venue_key(venue)
        info = by_key.get(key)
        if info is None and len(key) >= 6:
            near = [v for k, v in by_key.items() if k.startswith(key) or key.startswith(k)]
            info = near[0] if len(near) == 1 else None
        if info:
            entry, code = list(info[:4]), info[4]
        elif key in by_detail_name:
            code, d = by_detail_name[key]
            entry = [d[1], d[2], d[3], None]
        else:
            continue
        d = details.get(code)
        if d and d[4] is not None and d[5] is not None:
            entry += [round(d[4], 6), round(d[5], 6)]
        out[venue] = entry
    return out


def season_venue_names(conn, season_id, categories=None, keep=None, exclude=None):
    """Los campos de los partidos de la temporada y los de sus equipos (team_seasons). Con
    `categories`, solo los partidos de esas categorías; con `exclude`, sin los de esas; con
    `keep(equipo)`, solo los de esos equipos."""
    cats = tuple(categories or ())
    fuera = tuple(exclude or ())
    only = f" AND upper(c.name) IN ({','.join('?' * len(cats))})" if cats else ""
    only += f" AND upper(c.name) NOT IN ({','.join('?' * len(fuera))})" if fuera else ""
    names = {r[0] for r in conn.execute(
        f"""SELECT DISTINCT m.venue FROM matches m JOIN groups g ON g.id = m.group_id
           JOIN categories c ON c.id = g.category_id
           WHERE g.season_id = ? AND m.venue IS NOT NULL AND m.venue <> ''{only}""", (season_id, *cats, *fuera))}
    if _has_table(conn, "team_seasons"):
        names |= {venue for team, venue in conn.execute(
            """SELECT DISTINCT t.name, ts.venue_name FROM team_seasons ts LEFT JOIN teams t ON t.id = ts.team_id
               WHERE ts.season_id = ? AND ts.venue_name IS NOT NULL""", (season_id,))
                  if keep is None or keep(team)}
    return sorted(names)


def get_historical_jornadas(conn, group_id, include_details=False):
    """Return matches grouped by jornada num for historical groups.
    Format: {jornada_num: [[date, home, away, hs, as_], ...]}; with
    include_details, the 8 columns of HISTORY:
    [date, home, away, hs, as_, None, time, venue]. Every per-season file
    uses include_details.
    Only includes jornadas with at least one match.
    """
    rows = conn.execute(
        """SELECT m.jornada, m.date, h.name, a.name, m.home_score, m.away_score, m.time, m.venue
           FROM matches m
           JOIN teams h ON m.home_team_id = h.id
           JOIN teams a ON m.away_team_id = a.id
           WHERE m.group_id = ?
           ORDER BY m.jornada, m.date, m.time, h.name""",
        (group_id,),
    ).fetchall()

    jornadas = {}
    for jornada, dt, home, away, hs, as_, kickoff, venue in rows:
        ctx = f"en {home} vs {away} ({dt})"
        jornadas.setdefault(jornada, []).append(
            [dt, home, away, sanitize_score(hs, ctx), sanitize_score(as_, ctx)]
            + ([None, kickoff, venue] if include_details else [])
        )

    return dict(sorted(jornadas.items(), key=lambda x: _jornada_sort_key(x[0])))


def generate_seasons_js(conn, details=None):
    """Generate data-seasons.js with list of available seasons + historical data.

    Returns (js_string_for_lean_file, full_seasons_list_with_groups).

    The lean file (data-seasons.js) only contains [{name, current}] entries —
    enough for the season selector dropdown — y "detail": true en las temporadas con alguna
    entrada en data-matchdetail.js (detail_seasons de `details`, las mismas entradas que main
    escribe en ese fichero; sin ellas, se calculan), para que la web solo lo pida para ellas.
    Per-season group/match data is written to data-season-YYYY-YYYY.js by
    generate_per_season_files() and fetched lazily by src/state.js loadSeasonData() when the user switches
    to a historical season. This keeps initial page load small (was 484KB,
    now ~200B for season list).
    """
    seasons = conn.execute(
        "SELECT id, name, is_current FROM seasons ORDER BY start_year DESC"
    ).fetchall()

    # Lean version for the eager-loaded data-seasons.js
    with_detail = detail_seasons(_match_details(conn) if details is None else details)
    lean_list = [{"name": n, "current": bool(c), **({"detail": True} if n in with_detail else {})}
                 for _, n, c in seasons]

    # Full version (with group data) used by generate_per_season_files
    seasons_list = []
    for season_id, season_name, is_current in seasons:
        entry = {"name": season_name, "current": bool(is_current)}

        if not is_current:
            # Include historical standings data inline (for per-season files)
            for cat_name, cat_key in [("BENJAMIN", "benjamin"), ("PREBENJAMIN", "prebenjamin")]:
                entry[cat_key] = archive_groups(conn, season_id, season_name, cat_name)
            # Los goleadores de la temporada archivada, si la base los tiene
            # (2025-26: los de futbolaspalmas; desde 2026-27, los de la federación).
            gol = {cat_key: goleadores_entries(conn, cat_name, season_name)
                   for cat_name, cat_key in [("BENJAMIN", "benjamin"), ("PREBENJAMIN", "prebenjamin")]}
            if any(gol.values()):
                entry["gol"] = gol
            # La ficha de cada equipo (equipación y campo) y los campos de la temporada, con sus
            # coordenadas, si la base los tiene. Sin lo que solo es de las perezosas, que va en su fichero.
            only = _lazy_only(conn, season_id)
            equipos = team_info_map(conn, season_id, keep=lambda t: t not in only)
            if equipos:
                entry["equipos"] = equipos
            campos = campos_entries(conn, season_venue_names(conn, season_id, EAGER_CATEGORIES,
                                                             keep=lambda t: t not in only))
            if campos:
                entry["campos"] = campos
            # Cada categoría perezosa de la temporada, aparte (data-season-<S>-<clave>.js), si la tiene.
            lazy = {cat: archive_lazy(conn, season_id, season_name, cat) for cat in LAZY}
            entry["_lazy"] = {cat: v for cat, v in lazy.items() if v}

        seasons_list.append(entry)

    return "const SEASONS=" + js_val(lean_list) + ";\n", seasons_list


def archive_groups(conn, season_id, season_name, cat_name):
    """Los grupos de una categoría de una temporada pasada, con la forma de data-season-<S>.js."""
    groups = conn.execute(
        """SELECT g.id, g.code, g.name, g.full_name, g.phase, g.island, g.current_jornada
           FROM groups g JOIN categories c ON c.id = g.category_id
           WHERE g.season_id = ? AND UPPER(c.name) = ?
           ORDER BY g.code""",
        (season_id, cat_name),
    ).fetchall()

    groups_data = []
    for gid, code, name, full_name, phase, island, current_jornada in groups:
        standings = get_standings(conn, gid)
        hist_jornadas = get_historical_jornadas(conn, gid, include_details=True)
        group_obj = {
            "id": code,
            "name": name,
            "fullName": full_name,
            "phase": phase or island or "Gran Canaria",
            "island": island,
            "current_jornada": current_jornada,
            "standings": standings,
            "jornadas": hist_jornadas,
        }
        detail = standings_detail_map(conn, gid)
        if detail:
            group_obj["detail"] = detail
        # La clasificación calculada con los partidos (2014-15 del archivo del portal: la
        # archivada era de marzo-abril), para que la web no la llame oficial.
        if computed_table(conn, gid, season_name):
            group_obj["standingsKind"] = "reconstructed"
        groups_data.append(group_obj)
    return groups_data


def archive_lazy(conn, season_id, season_name, category):
    """{name, <clave>, gol?, equipos?, campos?} de una categoría perezosa (LAZY) de una temporada pasada
    (docs/alevin.md §5: la clave de la categoría con la forma de la clave benjamin de data-season-<S>.js), o
    None si esa temporada no tiene grupos de ella (o la categoría no está en categorias.EN_WEB)."""
    if category not in _en_web():
        return None
    clave = LAZY[category][0]
    groups = archive_groups(conn, season_id, season_name, category)
    if not groups:
        return None
    out = {"name": season_name, clave: groups}
    gol = goleadores_entries(conn, category, season_name)
    if gol:
        out["gol"] = {clave: gol}
    teams = _in_category(conn, season_id, category)
    equipos = team_info_map(conn, season_id, keep=lambda t: t in teams)
    if equipos:
        out["equipos"] = equipos
    campos = campos_entries(conn, season_venue_names(conn, season_id, (category,), keep=lambda t: t in teams))
    if campos:
        out["campos"] = campos
    return out


def archive_alevin(conn, season_id, season_name):
    """El alevín de una temporada pasada: archive_lazy de alevín."""
    return archive_lazy(conn, season_id, season_name, ALEVIN)


def generate_per_season_files(seasons_list):
    """Write data-season-YYYY-YYYY.js for each historical season.

    The app fetches these lazily via state.js loadSeasonData() — keeping them
    in sync with data-seasons.js prevents drift bugs (a group invisible
    because its per-season file lags behind the DB).
    """
    written = []
    for s in seasons_list:
        if s.get("current"):
            continue
        name = s["name"]  # "2021-2022"
        var_name = "SEASON_" + name.replace("-", "_")
        out_path = os.path.join(PROJECT_ROOT, f"data-season-{name}.js")
        lazy = s.get("_lazy") or {}
        s = {k: v for k, v in s.items() if k != "_lazy"}
        content = f"const {var_name}=" + js_val(s) + ";\n"
        escribir_atomico(out_path, content)
        written.append((name, len(content)))
        # Cada categoría perezosa, en su fichero (fuera del precache del SW: docs/alevin.md §5); el de una
        # temporada que ya no la tiene, fuera (la web trata su 404 como «sin esa categoría»).
        for cat, (clave, grupos, _s) in LAZY.items():
            path = os.path.join(PROJECT_ROOT, f"data-season-{name}-{clave}.js")
            if lazy.get(cat):
                escribir_atomico(path, f"const {var_name}_{grupos}=" + js_val(lazy[cat]) + ";\n")
                print(f"  data-season-{name}-{clave}.js: {os.path.getsize(path):,} bytes")
            elif os.path.exists(path):
                os.remove(path)
                print(f"  data-season-{name}-{clave}.js: borrado (la temporada no tiene {clave})")
    return written


def snapshot_data_files(root=None):
    """Content hash of every data-*.js under root, used to decide whether
    this run actually changed any published data."""
    root = root or PROJECT_ROOT
    snap = {}
    for path in sorted(glob.glob(os.path.join(root, "data-*.js"))):
        with open(path, "rb") as f:
            snap[os.path.basename(path)] = hashlib.sha256(f.read()).hexdigest()
    return snap


def version_after(current, today):
    """The version that follows `current` (YYYYMMDD[a-z], or None when there
    is none) on `today` (YYYYMMDD). Always strictly greater than `current` as
    text, which is the order of these strings, and with the same form:
    `today` if `current` is from an earlier day; if it is from today or a
    later day, its next letter (20261115 → 20261115b → 20261115c); after the
    z, the calendar day after its own, without a letter (20261115z →
    20261116). So the number is a day only as a starting point: on a busy
    day it can run ahead of the date. The bot (_next_version) and
    scripts/publicar.py share it."""
    if not current or current[:8] < today:
        return today
    day, letter = current[:8], current[8:]
    if not letter:
        return day + "b"
    if letter < "z":
        return day + chr(ord(letter) + 1)
    return (datetime.strptime(day, "%Y%m%d").date() + timedelta(days=1)).strftime("%Y%m%d")


def _next_version(index_content, today=None):
    """New cache-bust version string after the first ?v= of index.html
    (version_after). `today` (datetime.date) defaults to date.today(): the
    bot's clock, UTC on the GitHub runner."""
    today = (today or date.today()).strftime("%Y%m%d")
    existing = re.search(r"\?v=(\d{8}[a-z]?)", index_content)
    return version_after(existing.group(1) if existing else None, today)


def bump_cache_version(root=None, touch_footer=True, version=None):
    """Bump ?v= (index.html) and CACHE_NAME (sw.js) to the SAME
    version string (the SW cache rotates with the data) and, with touch_footer, the footer date «Última
    actualización». The bot calls it without arguments, only when data
    content changed (bump_if_changed): the footer is the date of
    the data. scripts/publicar.py passes touch_footer=False and its own
    version: a release does not move that date. `version` keeps the bot's form, 8 digits and an optional letter
    (ValueError otherwise, and nothing is written)."""
    if version is not None and not re.fullmatch(r"\d{8}[a-z]?", version):
        raise ValueError(f"versión sin la forma del bot (AAAAMMDD y una letra opcional): {version!r}")
    root = root or PROJECT_ROOT
    index_path = os.path.join(root, "index.html")
    if not os.path.exists(index_path):
        print("  WARNING: index.html not found, skipping cache bump")
        return

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    version = version or _next_version(content)
    new_content = re.sub(r"\?v=\d{8}[a-z]?", f"?v={version}", content)
    if touch_footer:
        today_display = date.today().strftime("%d/%m/%Y")
        new_content = re.sub(
            r"Última actualización: \d{2}/\d{2}/\d{4}",
            f"Última actualización: {today_display}",
            new_content
        )
    if new_content != content:
        escribir_atomico(index_path, new_content)
        print(f"  index.html cache version bumped to ?v={version}")

    # Keep sw.js CACHE_NAME (first line, /futbolbase2-v[0-9a-z]+/) in sync
    # with the same version string so the SW cache rotates with the data.
    sw_path = os.path.join(root, "sw.js")
    if os.path.exists(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            sw = f.read()
        new_sw = re.sub(r"futbolbase2-v[0-9a-z]+", f"futbolbase2-v{version}", sw, count=1)
        if new_sw != sw:
            escribir_atomico(sw_path, new_sw)
            print(f"  sw.js CACHE_NAME bumped to futbolbase2-v{version}")
    else:
        print("  WARNING: sw.js not found, skipping CACHE_NAME bump")


def bump_if_changed(before_snapshot, root=None):
    """Compare the data-*.js snapshot taken BEFORE regeneration with the
    current tree; bump ?v=/footer/CACHE_NAME only if some content changed.
    Avoids the daily no-op commit that only touched index.html."""
    after = snapshot_data_files(root)
    if after == before_snapshot:
        print("  data-*.js sin cambios — no se bumpea ?v= / footer / CACHE_NAME (C4)")
        return False
    bump_cache_version(root)
    return True


def write_file(filename, content):
    """Write content to a file in the project root."""
    path = os.path.join(PROJECT_ROOT, filename)
    escribir_atomico(path, content)
    size = os.path.getsize(path)
    print(f"  {filename}: {size:,} bytes")


def main():
    base = get_connection()
    base.row_factory = None  # ensure tuples
    # Solo lo que la web enseña (categorias.EN_WEB): infantil, cadete y juvenil están en la base desde que su
    # carril los lee, pero no salen hasta su parte (E2). Sin ningún grupo de otra categoría es la misma conexión
    # (cero coste); si los hay, una copia en memoria sin ellos (scripts/vista_web.py). coverage_summary sigue
    # midiendo el fichero de verdad (PROJECT_ROOT/futbolbase.db).
    import vista_web
    conn = vista_web.copia_web(base)

    print("=== Generating JS data files from SQLite ===\n")

    # Hash all data-*.js BEFORE regenerating, to bump versions only if
    # some content actually changes during this run.
    before_snapshot = snapshot_data_files()

    print("1. data-benjamin.js")
    write_file("data-benjamin.js", generate_category_js(conn, "BENJAMIN", "BENJAMIN", "BENJ_STATS"))

    print("2. data-prebenjamin.js")
    write_file("data-prebenjamin.js", generate_category_js(conn, "PREBENJAMIN", "PREBENJAMIN", "PREBENJ_STATS"))

    # Las perezosas, siempre (vacías si no hay): no van en index.html; en el precache del SW, solo
    # data-alevin.js, opcional (scripts/precache.py).
    for cat, (clave, _grupos, _s) in LAZY.items():
        print(f"2b. data-{clave}.js")
        write_file(f"data-{clave}.js", generate_lazy_js(conn, cat))

    print("3. data-history.js")
    write_file("data-history.js", generate_history_js(conn))

    print("4. data-matchdetail.js")
    details = _match_details(conn)
    write_file("data-matchdetail.js", generate_matchdetail_js(conn, details))
    # La cronología de infantil, cadete y juvenil, cada una en el suyo (siempre, aunque vacío).
    for cat in NUEVAS:
        print(f"4b. data-matchdetail-{LAZY[cat][0]}.js")
        write_file(f"data-matchdetail-{LAZY[cat][0]}.js", generate_matchdetail_lazy_js(conn, cat))

    print("5. data-goleadores.js")
    write_file("data-goleadores.js", generate_goleadores_js(conn))

    print("6. data-shields.js  [skipped - maintained manually]")

    print("7. data-seasons.js")
    seasons_js, seasons_list = generate_seasons_js(conn, details)
    write_file("data-seasons.js", seasons_js)

    print("8. data-season-*.js (per-season lazy-loaded files)")
    written = generate_per_season_files(seasons_list)
    for name, sz in written:
        print(f"  data-season-{name}.js: {sz:,} bytes")

    # Actas: un data-lineups-<S>-<grupo>.js por grupo con alguna acta.
    print("\n9. data-lineups-<S>-<grupo>.js (actas)")
    write_lineups(conn)

    # Fichas de jugador: data-jugadores-<k>.js, y lo que sale de las mismas filas: el buscador y el ranking.
    # La consulta grande (todas las apariciones), una vez para los tres.
    datos = _datos_fichas(conn)
    print("\n9b. data-jugadores-<k>.js (fichas de jugador)")
    write_jugadores(conn, datos=datos)
    print("\n9c. data-buscar-<xy>.js (buscador de jugadores)")
    write_buscar(conn, datos=datos)
    print("\n9d. data-ranking.js y data-ranking-<año>.js (los mejores de cada año)")
    write_ranking(conn, datos=datos)

    print("\n10. Cache version (only if data changed — C4)")
    bump_if_changed(before_snapshot)

    # Después de subir la versión: la huella de index.html del manifiesto es la del index.html ya subido. En
    # todas las pasadas (solo escribe si cambia); en un árbol parcial no hace nada.
    print("\n11. sw.js: el manifiesto del precache")
    precache.escribir(PROJECT_ROOT)

    conn.close()
    if conn is not base:
        base.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
