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

Alevín, solo de Gran Canaria (docs/alevin.md; todos los códigos empiezan por AL):

    LIGA ALEVIN GRAN CANARIA FASE PREVIA     -> AL1..   «Primera Fase GC»
    LIGA ALEVIN ... FASE LIGA X / SEGUNDA FASE X -> ALX1.. «Segunda Fase X»
    LIGA ALEVIN GRAN CANARIA FASE X / LIGA X     -> ALX1.. «Segunda Fase X» (también benjamín: X1..)
    COPA CAMPEONES ALEVÍN (… FASE X)         -> ALCC1.. (ALCCX1..) «Copa de Campeones (X)»
    CLAUSURA ALEVÍN                          -> ALCL1   «Clausura Alevín»

Una competición que no encaje aborta: mejor parar que inventar una fase que la
web clasificaría como «otra-…». También alevín de Lanzarote o Fuerteventura y
fútbol sala (categorias.category_of), que no se publican.

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


# Las categorías con convenio de código aquí. Infantil, cadete y juvenil se conocen (categorias.category_of)
# pero aún no tienen el suyo: sin esto caerían en el de benjamín («LIGA INFANTIL LANZAROTE FASE 1» → LZ1,
# el código de un grupo de benjamín).
CON_CONVENIO = ("benjamin", "prebenjamin", "alevin")


def category(name):
    """'benjamin', 'prebenjamin' o 'alevin' de una competición; ValueError si no se publica."""
    from categorias import category_of
    cat = category_of(name)
    if not cat:
        raise ValueError(f"no se publica (fútbol sala, alevín de otra isla o sin categoría): {name}")
    if cat.lower() not in CON_CONVENIO:
        raise ValueError(f"competición sin convenio de código: {name}")
    return cat.lower()


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


def comp_meta(name):
    """(prefijo de código, fase publicada) de una competición de FIFLP."""
    n = fold(name)
    if "SALA" in n:
        raise ValueError(f"fútbol sala no se publica: {name}")
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
    elim = {}
    for g in sorted((g for g in raw if eliminatoria_de_liga(g)), key=lambda g: int(str(g["group_id"]))):
        prefix = ELIMINATORIAS[category(g["competition_name"])]
        used = [int(m.group(1)) for c in seen | set(elim.values()) for m in [re.fullmatch(rf"{prefix}(\d+)", c)] if m]
        elim[id(g)] = f"{prefix}{max(used, default=0) + 1}"
    rows = []
    for g in raw:
        if id(g) in elim:
            code = elim[id(g)]
            prefix, phase, n = code.rstrip("0123456789"), "Eliminatorias", int(code[len(code.rstrip("0123456789")):])
        else:
            (prefix, phase), n = comp_meta(g["competition_name"]), group_number(g["group_name"])
            code = f"{prefix}{n}"
        rows.append((prefix, phase, n, code, g))
    for prefix, phase, n, code, g in sorted(rows, key=lambda r: r[:3]):
        if code in seen:
            raise ValueError(f"código repetido: {code}")
        seen.add(code)
        cat = category(g["competition_name"])
        island = ("lanzarote" if prefix in ("LZ", "LZS", "PLZ") else
                  "fuerteventura" if prefix in ("FV1", "FV2", "PFV") else "grancanaria")
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


def eliminatoria_de_liga(g):
    """¿Es `g` (un grupo del raw) un grupo de eliminatoria publicado dentro de una liga? (Como en la Fase
    Previa de benjamín y la de alevín: «Eliminatoria de Primeros y Segundos» y «… de Terceros y
    Cuartos».) Llevan el código y la fase de las eliminatorias de su categoría (EL, PEL, ALEL; «Eliminatorias»),
    solo en Gran Canaria: en Lanzarote o Fuerteventura, ValueError, como sus competiciones de eliminatorias."""
    comp = fold(g["competition_name"])
    if "ELIMINATORIA" not in fold(g.get("group_name")) or COPA_O_ELIMINATORIA.search(comp):
        return False
    comp_meta(g["competition_name"])                 # la competición, con convenio
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
    ap.add_argument("--cat", default="prebenjamin", choices=["benjamin", "prebenjamin", "alevin"])
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
