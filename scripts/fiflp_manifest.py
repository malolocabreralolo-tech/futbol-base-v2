#!/usr/bin/env python3
"""fiflp_manifest.py — Manifiesto de temporada (docs/temporada-nueva.md) a partir
del raw de la federación que deja fetch_fiflp_islas.py.

Los códigos y las fases siguen el convenio de 2025/26 para que la web, el
histórico entre temporadas y el cambio de fase de Mi equipo los traten igual:

    LIGA BENJAMIN GRAN CANARIA FASE PREVIA   -> FF1..   «Primera Fase GC»
    LIGA BENJAMIN ... FASE LIGA A|B|C        -> A1.. B1.. C1..  «Segunda Fase A|B|C»
    LIGA BENJAMIN DE LANZAROTE FASE 1|2      -> LZ1.. / LZS1..  «Lanzarote Fase 1|2»
    LIGA BENJAMIN ... FUERTEVENTURA 1ª|2ª    -> FV11.. / FV21.. «Fuerteventura Fase 1|2»
    LIGA BENJAMIN ... FASE LIGA X / SEGUNDA FASE X (cualquier letra) -> X1.. «Segunda Fase X»
    LIGA PREBENJAMIN DE GRAN CANARIA         -> PG1..   «Gran Canaria»
    LIGA PREBENJAMIN LANZAROTE|FUERTEVENTURA -> PLZ1.. / PFV1..
    COPA BENJAMÍN GRAN CANARIA (2026-27)     -> CGC1..  «Copa Gran Canaria» (nunca BC ni PCC: son
                                                la Copa de Campeones y synth_copa_campeones.py
                                                les reescribe la tabla)
    ... ELIMINATORIAS (de Gran Canaria)      -> EL1.. (benjamín), PEL1.. (prebenjamín),
                                                ALEL1.. (alevín)  «Eliminatorias» (copa en la web)

Infantil, cadete y juvenil, y el alevín de Lanzarote y Fuerteventura (scripts/convenio.py, comprobado
contra el catálogo entero: CATEGORÍA + NIVEL + ISLA + FASE + TIPO + número):

    LIGA <nivel> <CATEGORÍA> <isla>          -> <CAT><nivel><isla>1..  «<Nivel> <isla>» (INFPG1.. «Preferente GC»)
    LIGA <CATEGORÍA> <isla> (sin nivel)      -> <CAT>U<isla>1..        «<Isla>» (INFUL1.. «Lanzarote Fase 1»)
    LIGA <CATEGORÍA> INTERINSULAR / DIVISION DE HONOR / AUTONOMICA -> JUVI1.., JUVH1.., CADA1.. (isla interinsular)
    COPA [CABILDO|DELEGACION|CAMPEONES] …    -> <liga>C1.. / <liga>CD1.. / <CAT>U<isla>CK1..  «Copa …»
    FASE DE ASCENSO A …                      -> <destino>A1..   «Fase de Ascenso a …»
    ELIMINATORIAS DE ASCENSO A … / ELIMINATORIAS COPA … -> <destino o copa>E1..  «Eliminatorias …»
    FINAL / SEMIFINAL …                      -> <liga o copa>F1.. / S1..  «Final Liga …», «Final Copa …»
    LIGA ALEVIN LANZAROTE|FUERTEVENTURA …    -> ALUL1.., AL1L1.., ALPL1.., ALUF1.. (solo con
                                                categorias.ALEVIN_ISLAS; si no, no se publica)

Alevín de Gran Canaria (docs/alevin.md; todos los códigos empiezan por AL):

    LIGA ALEVIN GRAN CANARIA FASE PREVIA     -> AL1..   «Primera Fase GC»
    LIGA ALEVIN ... FASE LIGA X / SEGUNDA FASE X -> ALX1.. «Segunda Fase X»
    LIGA ALEVIN GRAN CANARIA FASE X / LIGA X     -> ALX1.. «Segunda Fase X» (también benjamín: X1..)
    COPA CAMPEONES ALEVÍN (… FASE X)         -> ALCC1.. (ALCCX1..) «Copa de Campeones (X)»
    CLAUSURA ALEVÍN                          -> ALCL1   «Clausura Alevín»

Una competición que no encaje aborta: mejor parar que inventar una fase que la
web clasificaría como «otra-…». También alevín de Lanzarote o Fuerteventura y
fútbol sala (categorias.category_of), que no se publican, y una competición de las
categorías nuevas sin convenio (convenio.SinConvenio: «competición sin convenio de código: …»).

    python3 scripts/fiflp_manifest.py scripts/fiflp_islas_22_raw.json 2026-2027 \\
        --team "Las Mesas" --cat prebenjamin > temporada-2026-2027.json
"""
import argparse
import json
import re
import sys
import unicodedata

FIFLP_URL = ("https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120"
             "&CodTemporada={season}&CodCompeticion={comp}&CodGrupo={group}")


def fold(text):
    return "".join(ch for ch in unicodedata.normalize("NFD", text or "")
                   if unicodedata.category(ch) != "Mn").upper()


ELIMINATORIAS = {"benjamin": "EL", "prebenjamin": "PEL", "alevin": "ALEL"}
# 'FASE LIGA C' (2025-26) o 'SEGUNDA FASE F': la letra de la Segunda Fase, cualquiera (2026-27 tendrá F).
SEGUNDA_FASE = re.compile(r"\b(?:FASE LIGA|SEGUNDA FASE|2. FASE)\s+([A-Z])\b")
# 'LIGA ALEVIN GRAN CANARIA FASE A' o '… LIGA B': la Segunda Fase con el nombre corto, la letra al final.
SEGUNDA_FASE_CORTA = re.compile(r"\b(?:FASE|LIGA) ([A-Z])$")
# Lo que acaba igual pero no es la liga de la Segunda Fase (la Copa de Campeones de alevín usa «FASE X»).
NO_ES_LIGA = re.compile(r"\b(?:COPA|TORNEO|CAMPEONES|CLAUSURA|CIERRE|ELIMINATORIAS?|FINAL|SEMIFINAL(?:ES)?)\b")
# El nombre entero (sin tildes ni espacios de más): otra copa de Gran Canaria (de campeones, final…) aborta.
COPA_GRAN_CANARIA = re.compile(r"COPA BENJAMIN (?:DE )?GRAN CANARIA")


def segunda_fase(n):
    """La letra de la Segunda Fase de un nombre ya sin tildes, o None: «FASE LIGA X», «SEGUNDA FASE X» o,
    en una liga, el nombre acabado en «FASE X» o «LIGA X»."""
    m = SEGUNDA_FASE.search(n)
    if m:
        return m.group(1)
    n = " ".join(n.split())
    if re.search(r"\bLIGA\b", n) and not NO_ES_LIGA.search(n):
        m = SEGUNDA_FASE_CORTA.search(n)
        if m:
            return m.group(1)
    return None


def category(name):
    """La clave de la web de la categoría de una competición ('benjamin', 'prebenjamin', 'alevin',
    'infantil', 'cadete' o 'juvenil'); ValueError si no se publica."""
    from categorias import category_of
    cat = category_of(name)
    if not cat:
        raise ValueError(f"no se publica (fútbol sala, alevín de otra isla o sin categoría): {name}")
    return cat.lower()


def _convenio_nuevo(name):
    """El Convenio de scripts/convenio.py de una competición de las categorías nuevas (infantil, cadete,
    juvenil o alevín de Lanzarote y Fuerteventura), o None si es de las de siempre. Sin convenio,
    ValueError con el texto que espera activar_auto.SIN_CONVENIO."""
    import convenio
    if not convenio.aplica(name):
        return None
    try:
        return convenio.convenio(name)
    except convenio.SinConvenio:
        raise ValueError(f"competición sin convenio de código: {name}") from None


def _isla_de_prefijo(prefix):
    """La isla de un grupo de benjamín, prebenjamín o alevín de Gran Canaria por su prefijo (lo de antes del
    convenio de las categorías nuevas)."""
    return ("lanzarote" if prefix in ("LZ", "LZS", "PLZ") else
            "fuerteventura" if prefix in ("FV1", "FV2", "PFV") else "grancanaria")


def _alevin_meta(name, n):
    if "ELIMINATORIA" in n:
        return ELIMINATORIAS["alevin"], "Eliminatorias"
    if "CAMPEONES" in n:
        m = re.search(r"\bFASE ([A-Z])$", n)
        return ("ALCC" + m.group(1), f"Copa de Campeones {m.group(1)}") if m else ("ALCC", "Copa de Campeones")
    if "CLAUSURA" in n:
        return "ALCL", "Clausura Alevín"
    x = segunda_fase(n)
    if x:
        return "AL" + x, f"Segunda Fase {x}"
    if "FASE PREVIA" in n or "PRIMERA FASE" in n:
        return "AL", "Primera Fase GC"
    raise ValueError(f"competición sin convenio de código: {name}")


def meta(name):
    """(prefijo de código, fase publicada, isla) de una competición de FIFLP: la de scripts/convenio.py
    para infantil, cadete, juvenil y el alevín de Lanzarote y Fuerteventura (si se publica:
    categorias.ALEVIN_ISLAS); lo de siempre, con la isla por el prefijo, para las demás."""
    n = fold(name)
    if "SALA" in n:
        raise ValueError(f"fútbol sala no se publica: {name}")
    category(name)                               # lo que no se publica, fuera (también el alevín de islas)
    nuevo = _convenio_nuevo(name)
    if nuevo:
        return nuevo.prefijo, nuevo.fase, nuevo.isla
    prefix, phase = _meta_de_siempre(name, n)
    return prefix, phase, _isla_de_prefijo(prefix)


def comp_meta(name):
    """(prefijo de código, fase publicada) de una competición de FIFLP (meta, sin la isla)."""
    return meta(name)[:2]


def _meta_de_siempre(name, n):
    """(prefijo, fase) de benjamín, prebenjamín y alevín de Gran Canaria (`n`: el nombre sin tildes)."""
    cat = category(name)
    if cat == "alevin":
        return _alevin_meta(name, n)
    pre = cat == "prebenjamin"
    if "ELIMINATORIA" in n:
        # EL/PEL son las de Gran Canaria (docs/alevin.md §2): las de otra isla saldrían con la isla de
        # Gran Canaria y el mismo código que las suyas.
        if "LANZAROTE" in n or "FUERTEVENTURA" in n:
            raise ValueError(f"competición sin convenio de código: {name}")
        return ELIMINATORIAS[cat], "Eliminatorias"
    if "LANZAROTE" in n:
        if pre:
            return "PLZ", "Lanzarote"
        return ("LZS", "Lanzarote Fase 2") if re.search(r"FASE 2|2. FASE", n) else ("LZ", "Lanzarote Fase 1")
    if "FUERTEVENTURA" in n:
        if pre:
            return "PFV", "Fuerteventura"
        return ("FV2", "Fuerteventura Fase 2") if re.search(r"FASE 2|2. FASE", n) else ("FV1", "Fuerteventura Fase 1")
    if pre:
        # Solo la liga: la copa y el torneo de clausura no tienen convenio aquí (saldrían PG y chocarían
        # con PG1-4).
        if re.search(r"\b(COPA|CAMPEONES|CLAUSURA|CIERRE|TORNEO)\b", n):
            raise ValueError(f"competición sin convenio de código: {name}")
        return "PG", "Gran Canaria"
    if COPA_GRAN_CANARIA.fullmatch(" ".join(n.split())):
        return "CGC", "Copa Gran Canaria"
    x = segunda_fase(n)
    if x:
        return x, f"Segunda Fase {x}"
    if "FASE PREVIA" in n or "PRIMERA FASE" in n:
        return "FF", "Primera Fase GC"
    raise ValueError(f"competición sin convenio de código: {name}")


def group_number(group_name):
    m = re.search(r"(\d+)", group_name or "")
    return int(m.group(1)) if m else 1


def group_label(group_name):
    """El nombre del grupo en la web: «Grupo N» o, si la federación no lo numera, el suyo («Eliminatoria
    previa» de la Copa Benjamín; «Grupo 1» no dice nada de una copa)."""
    if re.search(r"\d", group_name or ""):
        return f"Grupo {group_number(group_name)}"
    return " ".join((group_name or "").split()) or "Grupo 1"


def build(raw, season, season_code, names=None, only=None, taken=()):
    """Grupos del manifiesto (sin defaultTeam). `only`: solo esos (CodCompeticion, CodGrupo) del raw (la
    activación automática, activar_auto.py: los grupos que la temporada aún no tiene), filtrados antes de
    ordenar para que otra competición del raw sin convenio no aborte; `taken`: los códigos que ya tiene la
    temporada, con los que un código nuevo no puede chocar («código repetido: …»)."""
    if only is not None:
        only = {(str(c), str(g)) for c, g in only}
        raw = [g for g in raw if (str(g.get("competition_id")), str(g.get("group_id"))) in only]
    groups, seen = [], set(taken)
    raw = [g for g in raw if g.get("jornadas") or g.get("standings")]     # sin calendario todavía: fuera
    # Los grupos de eliminatoria de una liga, numerados tras los de su prefijo que la temporada ya tiene, por
    # orden de CodGrupo: la federación no los numera.
    # Las de las categorías nuevas, con el prefijo de su liga más EL y su fase (convenio.eliminatoria_de_liga).
    elim = {}
    for g in sorted((g for g in raw if eliminatoria_de_liga(g)), key=lambda g: int(str(g["group_id"]))):
        prefix, phase, island = _eliminatoria(g["competition_name"])
        used = [int(m.group(1)) for c in seen | {e[0] for e in elim.values()}
                for m in [re.fullmatch(rf"{prefix}(\d+)", c)] if m]
        elim[id(g)] = (f"{prefix}{max(used, default=0) + 1}", phase, island)
    rows = []
    for g in raw:
        if id(g) in elim:
            code, phase, island = elim[id(g)]
            prefix, n = code.rstrip("0123456789"), int(code[len(code.rstrip("0123456789")):])
        else:
            (prefix, phase, island), n = meta(g["competition_name"]), group_number(g["group_name"])
            code = f"{prefix}{n}"
        rows.append((prefix, phase, n, code, island, g))
    for prefix, phase, n, code, island, g in sorted(rows, key=lambda r: r[:3]):
        if code in seen:
            raise ValueError(f"código repetido: {code}")
        seen.add(code)
        cat = category(g["competition_name"])
        label = " ".join(g["group_name"].split()) if id(g) in elim else group_label(g["group_name"])
        groups.append({
            "id": code, "cat": cat, "name": label, "phase": phase, "island": island,
            "fullName": (f"{cat.upper()} ELIMINATORIAS - {fold(label)}" if id(g) in elim
                         else f"{cat.upper()} {fold(phase)} - GRUPO {n}"),
            "url": FIFLP_URL.format(season=season_code, comp=g["competition_id"], group=g["group_id"]),
        })
    return groups


# Una competición que ya es una copa o una eliminatoria: sus grupos llevan el código de la competición
# («Eliminatoria previa» de la Copa Benjamín es CGC1), aunque se llamen «Eliminatoria…».
COPA_O_ELIMINATORIA = re.compile(r"\bCOPA\b|ELIMINATORIA")


def _eliminatoria(comp_name):
    """(prefijo, fase, isla) de los grupos de eliminatoria publicados dentro de una liga: en las categorías
    nuevas, los de su liga más EL (convenio.eliminatoria_de_liga: INFPGEL, «Eliminatorias Preferente GC»);
    en las de siempre, los de su categoría (EL, PEL, ALEL; «Eliminatorias»), de Gran Canaria."""
    import convenio
    nuevo = _convenio_nuevo(comp_name)
    if nuevo:
        return tuple(convenio.eliminatoria_de_liga(nuevo))[:3]
    return ELIMINATORIAS[category(comp_name)], "Eliminatorias", "grancanaria"


def eliminatoria_de_liga(g):
    """¿Es `g` (un grupo del raw) un grupo de eliminatoria publicado dentro de una liga? (Como en la Fase
    Previa de benjamín y la de alevín: «Eliminatoria de Primeros y Segundos» y «… de Terceros y
    Cuartos».) Llevan el código y la fase de las eliminatorias de su categoría (EL, PEL, ALEL; «Eliminatorias»),
    solo en Gran Canaria: en Lanzarote o Fuerteventura, ValueError, como sus competiciones de eliminatorias.
    En las categorías nuevas, el prefijo de su liga, que ya lleva la isla, más EL (_eliminatoria)."""
    comp = fold(g["competition_name"])
    if "ELIMINATORIA" not in fold(g.get("group_name")) or COPA_O_ELIMINATORIA.search(comp):
        return False
    meta(g["competition_name"])                      # la competición, con convenio
    if _convenio_nuevo(g["competition_name"]):
        return True
    if "LANZAROTE" in comp or "FUERTEVENTURA" in comp:
        raise ValueError(f"competición sin convenio de código: {g['competition_name']} / {' '.join(g['group_name'].split())}")
    return True


def find_team(raw, groups, needle, cat, names):
    """(groupId, nombre en la base) del equipo cuyo nombre contiene `needle`;
    el primer equipo del club (sin letra de filial B, C…)."""
    from import_fiflp_cups_2324 import clean_team_name
    by_url = {(g["competition_id"], g["group_id"]): g for g in raw}
    hits = []
    for group in (g for g in groups if g["cat"] == cat):
        comp = re.search(r"CodCompeticion=(\d+)", group["url"]).group(1)
        code = re.search(r"CodGrupo=(\d+)", group["url"]).group(1)
        entry = by_url[(comp, code)]
        teams = {clean_team_name(m[s]) for j in entry["jornadas"] for m in j["matches"] for s in ("home", "away")}
        teams |= {clean_team_name(r["team"]) for r in entry.get("standings") or []}
        for t in sorted(teams):
            shown = names.get(t, t)
            if fold(needle) in fold(shown) or fold(needle) in fold(t):
                hits.append((group["id"], shown, t))
    first = [h for h in hits if not re.search(r'["\s]([B-H])"?$', h[2]) and not re.search(r"\s[B-H]$", h[1])]
    if not first:
        raise ValueError(f"no aparece «{needle}» en {cat}")
    if len({(g, n) for g, n, _ in first}) > 1:
        raise ValueError(f"«{needle}» es ambiguo: {sorted({(g, n) for g, n, _ in first})}")
    return first[0][0], first[0][1]


def main():
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("season")
    ap.add_argument("--team", help="parte del nombre del equipo inicial (al activar una temporada)")
    ap.add_argument("--comps", default="", help="solo estas competiciones (ids separados por coma): fase nueva con --add")
    from categorias import DB_NAME
    ap.add_argument("--cat", default="prebenjamin", choices=list(DB_NAME))
    args = ap.parse_args()
    raw = json.load(open(args.raw, encoding="utf-8"))
    if args.comps:
        raw = [g for g in raw if str(g["competition_id"]) in args.comps.split(",")]
    from db import get_connection
    from activate_season import known_names
    conn = get_connection()
    try:
        names = known_names(raw, conn)
    finally:
        conn.close()
    start = int(args.season.split("-")[0])
    groups = build(raw, args.season, str(start - 2004))
    manifest = {"season": args.season, "groups": groups}
    if args.team:
        group_id, name = find_team(raw, groups, args.team, args.cat, names)
        manifest["defaultTeam"] = {"cat": args.cat, "groupId": group_id, "name": name}
    json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
