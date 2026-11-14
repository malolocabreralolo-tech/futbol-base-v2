#!/usr/bin/env python3
"""medir_identidad.py — ¿Se puede unir por nombre dentro de un club? La medida de la regla U1.

Solo lectura (los originales de las actas y la base, abierta inmutable). Toma los originales de
2019-20 a 2023-24, cuando todas las ligas (también prebenjamín) traían el id de la federación, y hace
como si los jugadores con id no lo trajeran: cada (nombre, equipo, temporada) sería una identidad sin
id. De los pares que uniría U1 (mismo nombre, mismo club, temporadas consecutivas, compatibles)
cuenta cuántos son el mismo niño (el mismo id, o el mismo niño tras U0, también la de los cortos) y
cuántos no, con nombres completos y cortos aparte. Con una precisión de los cortos del 95 % o más en
los pares de uno a uno (como une U1), `unir_cortos_en_club` es True (docs/identidad.md).

Los equipos son los de la base (el acta por su CodActa, `matches.cod_acta`): con los nombres de la
federación ('ATLETICO HURACAN "A", A.D. A') la letra de filial no sale y cada filial parecería otro club.

    python3 scripts/medir_identidad.py [--db futbolbase.db]
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categorias import category_of  # noqa: E402
from identidad import (NIVEL, Identidad, club, compatibles, nombre_completo, normalizar, resolver,  # noqa: E402
                       resumen_u0_cortos)

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
TEMPORADAS = ["2019-2020", "2020-2021", "2021-2022", "2022-2023", "2023-2024"]
UMBRAL = 0.95


def _iso(fecha):
    """'07-11-2021' → '2021-11-07'; otra cosa, None (sin fecha no se descarta un cruce)."""
    partes = (fecha or "").split("-")
    if len(partes) == 3 and len(partes[2]) == 4:
        return f"{partes[2]}-{partes[1]}-{partes[0]}"
    return None


def apariciones(db):
    """[(fiflp_id, nombre normalizado, anio, nivel, equipo de la base, fecha ISO)] de los jugadores con id
    de las alineaciones, y un Counter con lo que se leyó y lo que se dejó fuera."""
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    equipos = {cod: (local, visitante) for cod, local, visitante in conn.execute(
        "SELECT m.cod_acta, th.name, ta.name FROM matches m JOIN teams th ON th.id = m.home_team_id "
        "JOIN teams ta ON ta.id = m.away_team_id WHERE m.cod_acta IS NOT NULL")}
    conn.close()
    filas, cuenta = [], Counter()
    for temporada in TEMPORADAS:
        anio = int(temporada[:4])
        with open(os.path.join(SCRIPTS, f"fiflp_actas_{temporada}_raw.json"), encoding="utf-8") as f:
            actas = json.load(f)
        for cod, acta in actas.items():
            cuenta["actas"] += 1
            nivel = NIVEL.get(category_of((acta.get("header") or {}).get("competition") or ""))
            if nivel is None:
                cuenta["actas de una categoría que no se publica"] += 1
                continue
            if int(cod) not in equipos:
                cuenta["actas sin partido en la base"] += 1
                continue
            fecha = _iso(acta["header"].get("date"))
            for lado, equipo in zip(("home", "away"), equipos[int(cod)]):
                for jugador in (acta.get("lineups") or {}).get(lado) or []:
                    cuenta["apariciones"] += 1
                    if not jugador.get("fiflp_id") or not (jugador.get("name") or "").strip():
                        cuenta["apariciones sin id"] += 1
                        continue
                    filas.append((int(jugador["fiflp_id"]), normalizar(jugador["name"]), anio, nivel, equipo,
                                  fecha))
    cuenta["apariciones con id"] = len(filas)
    return filas, cuenta


def _vista(anio, nivel, equipo, fechas):
    conocidas = sorted(f for f in fechas if f)
    return (anio, nivel, equipo, conocidas[0] if conocidas else None, conocidas[-1] if conocidas else None,
            len(fechas))


def identidades_con_id(filas):
    """Una Identidad por id de la federación, con el nombre que más lleva y sus vistas."""
    nombres, fechas = defaultdict(Counter), defaultdict(list)
    for fid, norm, anio, nivel, equipo, fecha in filas:
        nombres[fid][norm] += 1
        fechas[(fid, anio, nivel, equipo)].append(fecha)
    vistas = defaultdict(list)
    for (fid, anio, nivel, equipo), fs in fechas.items():
        vistas[fid].append(_vista(anio, nivel, equipo, fs))
    return [Identidad(id=fid, norm=min(nombres[fid].items(), key=lambda kv: (-kv[1], kv[0]))[0],
                      fiflp_id=fid, vistas=tuple(sorted(vistas[fid]))) for fid in nombres]


def ninos(filas):
    """{fiflp_id: niño} tras U0, la de los completos y la de los cortos: identidad.resolver sobre las
    identidades con id (con todas con id solo une U0)."""
    return {fid: p for fid, (p, _) in resolver(identidades_con_id(filas), unir_cortos_en_club=False).items()}


def pares(filas, nino):
    """Los pares de U1 contados de dos maneras, {(manera, 'completos'|'cortos'): Counter}.

    'todos': cada niño en un equipo y temporada con cada niño con su mismo nombre en el mismo club la
    temporada siguiente (si caben por edad); mismo niño o no.
    'uno a uno': lo que une de verdad identidad.resolver: la identidad sin id (nombre, equipo,
    temporada) cuando es la única de ese nombre en el club esa temporada y la siguiente. Es el mismo
    niño si las dos tienen los mismos niños y solo uno; distintos, si no comparten ninguno; mezcla, si no."""
    fechas, en = defaultdict(list), defaultdict(set)
    for fid, norm, anio, nivel, equipo, fecha in filas:
        fechas[(norm, equipo, anio, nivel)].append(fecha)
        en[(norm, equipo, anio, nivel)].add(nino[fid])
    lado = defaultdict(list)            # (nombre, club, anio) -> [(equipo, nivel)]
    for norm, equipo, anio, nivel in fechas:
        lado[(norm, club(equipo), anio)].append((equipo, nivel))
    out = defaultdict(Counter)
    for (norm, c, anio), aqui in sorted(lado.items()):
        despues = lado.get((norm, c, anio + 1))
        if not c or not despues:
            continue
        tipo = "completos" if nombre_completo(norm) else "cortos"
        for ea, na in aqui:
            for eb, nb in despues:
                va = _vista(anio, na, ea, fechas[(norm, ea, anio, na)])
                vb = _vista(anio + 1, nb, eb, fechas[(norm, eb, anio + 1, nb)])
                if not compatibles([va], [vb]):
                    continue
                ka, kb = en[(norm, ea, anio, na)], en[(norm, eb, anio + 1, nb)]
                for x in ka:
                    for y in kb:
                        out[("todos", tipo)]["mismo" if x == y else "distinto"] += 1
                if len(aqui) == 1 and len(despues) == 1:
                    caso = ("mismo" if ka == kb and len(ka) == 1 else "distinto" if not ka & kb else "mezcla")
                    out[("uno a uno", tipo)][caso] += 1
    return out


def informe(cuenta, nino, medida, cubos=None):
    lineas = [f"Originales: {', '.join(TEMPORADAS)} (equipos de la base, por CodActa)."]
    for clave in ("actas", "actas de una categoría que no se publica", "actas sin partido en la base",
                  "apariciones", "apariciones sin id", "apariciones con id"):
        lineas.append(f"  {clave}: {cuenta[clave]}")
    lineas.append(f"  ids de la federación: {len(nino)}; niños tras U0: {len(set(nino.values()))}")
    if cubos is not None:
        lineas.append(f"  cubos de U0 de cortos: {cubos['una asentada']} con una asentada (se unen), "
                      f"{cubos['dos o más asentadas']} con dos o más (no se unen), "
                      f"{cubos['ninguna asentada']} sin ninguna (no se unen)")
    precision = {}
    for manera in ("todos", "uno a uno"):
        lineas.append(f"Pares {manera}:")
        lineas.append(f"  {'nombres':<10} {'pares':>7} {'mismo':>7} {'distinto':>8} {'mezcla':>6} {'precisión':>9}")
        for tipo in ("completos", "cortos"):
            c = medida[(manera, tipo)]
            total = sum(c.values())
            p = c["mismo"] / total if total else 0.0
            precision[(manera, tipo)] = p
            lineas.append(f"  {tipo:<10} {total:>7} {c['mismo']:>7} {c['distinto']:>8} {c['mezcla']:>6} "
                          f"{100 * p:>8.1f}%")
    # Decide la de uno a uno: es como une U1.
    decision = precision[("uno a uno", "cortos")] >= UMBRAL
    lineas.append(f"Precisión de los cortos (uno a uno) {100 * precision[('uno a uno', 'cortos')]:.1f} % "
                  f"{'≥' if decision else '<'} {100 * UMBRAL:.0f} % → unir_cortos_en_club = {decision}")
    return "\n".join(lineas), decision


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=os.path.join(os.path.dirname(SCRIPTS), "futbolbase.db"))
    args = ap.parse_args(argv)
    filas, cuenta = apariciones(args.db)
    nino = ninos(filas)
    texto, _ = informe(cuenta, nino, pares(filas, nino), resumen_u0_cortos(identidades_con_id(filas)))
    print(texto)


if __name__ == "__main__":
    main()
