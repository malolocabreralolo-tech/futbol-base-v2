#!/usr/bin/env python3
"""medir_identidad.py — ¿Se puede unir por nombre dentro de un club? La medida de la regla U1.

Solo lectura (los originales de las actas y la base, abierta inmutable). Toma los originales de
2019-20 a 2023-24, cuando todas las ligas (también prebenjamín) traían el id de la federación, y hace
como si los jugadores con id no lo trajeran: cada (nombre, equipo, temporada) sería una identidad sin
id. De los pares que uniría U1 (mismo nombre, mismo club, temporadas consecutivas, compatibles)
cuenta cuántos son el mismo niño (el mismo id, o el mismo niño tras U0, también la de los cortos) y
cuántos no, con nombres completos (dos apellidos), de un apellido y sin coma aparte. Con una precisión
de los sin coma del 95 % o más en los pares de uno a uno (como une U1), `unir_cortos_en_club` es True
(docs/identidad.md); los de coma, completos o de un apellido, se unen siempre. Mide también la U0 de
club (mismo nombre con coma, club y temporada, equipos distintos): con una precisión de los completos
del 95 % o más, U0_CLUB_COMPLETOS es True, y U0_CLUB_UN_APELLIDO si además la de un apellido lo es.

Los equipos son los de la base (el acta por su CodActa, `matches.cod_acta`): con los nombres de la
federación ('ATLETICO HURACAN "A", A.D. A') la letra de filial no sale y cada filial parecería otro club.

    python3 scripts/medir_identidad.py [--db futbolbase.db]
    python3 scripts/medir_identidad.py --entre-categorias [--db <copia>]

--entre-categorias (para el paso E2-D2 de la parte E2, docs/categorias-mayores.md, «En la web»): con la base tal
cual (solo lectura, sin los originales), resuelve las fichas en memoria dos veces, con el EN_WEB de antes
(prebenjamín, benjamín y alevín) y con el de después (las seis), y cuenta cuántas fichas une el resolvedor entre una
categoría de antes y una nueva, por regla (docs/identidad.md: el mismo identificador, que no es una regla; U0 de
equipo, de club y U1, U2), cuántas fichas de antes pierden o juntan identidades, cuántos pares de fichas del mismo
nombre (una de antes y una solo de las nuevas, del mismo club) no se unen por la edad o por otra cosa, y los
segundos del resolvedor. No escribe nada (ni la base ni players.ficha_id). Imprime cifras, nunca nombres.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categorias import category_of  # noqa: E402
from identidad import (NIVEL, Identidad, club, compatibles, nombre_completo, nombre_con_coma,  # noqa: E402
                       normalizar, resolver, resumen_u0_cortos)

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
        tipo = "completos" if nombre_completo(norm) else "un apellido" if nombre_con_coma(norm) else "sin coma"
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


def pares_club(filas, nino):
    """La medida de la U0 de club: {'completos'|'un apellido': Counter}. Pares de (nombre con coma, equipo,
    temporada) con el mismo nombre, el mismo club y la misma temporada y equipos distintos, que caben: cada
    niño de uno con cada niño del otro, mismo o distinto; 'cubos un niño' / 'cubos varios': los cubos con
    dos o más equipos, con un solo niño o con varios."""
    fechas, en = defaultdict(list), defaultdict(set)
    for fid, norm, anio, nivel, equipo, fecha in filas:
        if nombre_con_coma(norm):
            fechas[(norm, equipo, anio, nivel)].append(fecha)
            en[(norm, equipo, anio, nivel)].add(nino[fid])
    cubos = defaultdict(list)
    for norm, equipo, anio, nivel in fechas:
        cubos[(norm, club(equipo), anio)].append((equipo, nivel))
    out = defaultdict(Counter)
    for (norm, c, anio), unidades in sorted(cubos.items()):
        if not c or len({e for e, _ in unidades}) < 2:
            continue
        tipo = "completos" if nombre_completo(norm) else "un apellido"
        unidades.sort()
        for k, (ea, na) in enumerate(unidades):
            for eb, nb in unidades[k + 1:]:
                if ea == eb:
                    continue
                if not compatibles([_vista(anio, na, ea, fechas[(norm, ea, anio, na)])],
                                   [_vista(anio, nb, eb, fechas[(norm, eb, anio, nb)])]):
                    out[tipo]["no caben"] += 1
                    continue
                for x in en[(norm, ea, anio, na)]:
                    for y in en[(norm, eb, anio, nb)]:
                        out[tipo]["mismo" if x == y else "distinto"] += 1
        ninos_cubo = set().union(*(en[(norm, e, anio, n)] for e, n in unidades))
        out[tipo]["cubos un niño" if len(ninos_cubo) == 1 else "cubos varios"] += 1
    return out


def informe_club(medida_club):
    """Las líneas de la U0 de club y si cada tipo pasa del umbral."""
    lineas, pasa = ["U0 de club (mismo nombre, club y temporada, equipos distintos):"], {}
    lineas.append(f"  {'nombres':<11} {'pares':>7} {'mismo':>7} {'distinto':>8} {'no caben':>8} {'cubos 1 niño':>12} "
                  f"{'cubos varios':>12} {'precisión':>9}")
    for tipo in ("completos", "un apellido"):
        c = medida_club[tipo]
        total = c["mismo"] + c["distinto"]
        p = c["mismo"] / total if total else 0.0
        pasa[tipo] = p >= UMBRAL
        lineas.append(f"  {tipo:<11} {total:>7} {c['mismo']:>7} {c['distinto']:>8} {c['no caben']:>8} "
                      f"{c['cubos un niño']:>12} {c['cubos varios']:>12} {100 * p:>8.1f}%")
    lineas.append(f"  → U0_CLUB_COMPLETOS = {pasa['completos']}, "
                  f"U0_CLUB_UN_APELLIDO = {pasa['completos'] and pasa['un apellido']}")
    return "\n".join(lineas), pasa


def informe(cuenta, nino, medida, cubos=None):
    lineas = [f"Originales: {', '.join(TEMPORADAS)} (equipos de la base, por CodActa)."]
    for clave in ("actas", "actas de una categoría que no se publica", "actas sin partido en la base",
                  "apariciones", "apariciones sin id", "apariciones con id"):
        lineas.append(f"  {clave}: {cuenta[clave]}")
    lineas.append(f"  ids de la federación: {len(nino)}; niños tras U0: {len(set(nino.values()))}")
    if cubos is not None:
        lineas.append(f"  cubos de U0 sin coma: {cubos['una asentada']} con una asentada (se unen), "
                      f"{cubos['dos o más asentadas']} con dos o más (no se unen), "
                      f"{cubos['ninguna asentada']} sin ninguna (no se unen)")
    precision = {}
    for manera in ("todos", "uno a uno"):
        lineas.append(f"Pares {manera}:")
        lineas.append(f"  {'nombres':<11} {'pares':>7} {'mismo':>7} {'distinto':>8} {'mezcla':>6} {'precisión':>9}")
        for tipo in ("completos", "un apellido", "sin coma"):
            c = medida[(manera, tipo)]
            total = sum(c.values())
            p = c["mismo"] / total if total else 0.0
            precision[(manera, tipo)] = p
            lineas.append(f"  {tipo:<11} {total:>7} {c['mismo']:>7} {c['distinto']:>8} {c['mezcla']:>6} "
                          f"{100 * p:>8.1f}%")
    # Decide la de uno a uno (es como une U1) de los nombres sin coma: los que tienen coma se unen siempre.
    decision = precision[("uno a uno", "sin coma")] >= UMBRAL
    lineas.append(f"Precisión sin coma (uno a uno) {100 * precision[('uno a uno', 'sin coma')]:.1f} % "
                  f"{'≥' if decision else '<'} {100 * UMBRAL:.0f} % → unir_cortos_en_club = {decision}")
    return "\n".join(lineas), decision


# ---------------------------------------------------------------------------
# --entre-categorias: lo que une el resolvedor al ampliar EN_WEB (paso E2-D2)
# ---------------------------------------------------------------------------

EN_WEB_DE_ANTES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
EN_WEB_SEIS = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")


def _resolver_con(conn, categorias):
    """(identidades, {id: (principal, union_por)}, segundos de resolver) con las vistas de esas categorías, como
    migrate_identidad.resolver_fichas pero sin escribir (ni realinear: la base ya es la de una pasada)."""
    import time
    import migrate_identidad as M
    from identidad import UNIR_CORTOS_EN_CLUB
    t0 = time.monotonic()
    ids = M.identidades(conn, categorias)
    juntas = M.pares_juntas(conn, categorias)
    apartadas = M.leer_separadas(conn, log=lambda *a: None)
    t1 = time.monotonic()
    fichas = resolver(ids, UNIR_CORTOS_EN_CLUB, juntas=juntas, separadas=apartadas)
    return ids, fichas, (t1 - t0, time.monotonic() - t1)


def entre_categorias(db):
    """Lo de --entre-categorias (ver el docstring del módulo), como {clave: cifra}."""
    from identidad import NIVELES_NUEVOS, _base, _nombre, club as club_de
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ids3, f3, s3 = _resolver_con(conn, EN_WEB_DE_ANTES)
        ids6, f6, s6 = _resolver_con(conn, EN_WEB_SEIS)
    finally:
        conn.close()
    por_id = {i.id: i for i in ids6}
    vieja = {i.id: any(v[1] not in NIVELES_NUEVOS for v in i.vistas) for i in ids6}
    nueva = {i.id: any(v[1] in NIVELES_NUEVOS for v in i.vistas) for i in ids6}
    miembros6 = defaultdict(list)
    for k, (p, _) in f6.items():
        miembros6[p].append(k)
    out = Counter()
    out["identidades con el EN_WEB de antes"] = len(ids3)
    out["identidades con el de después"] = len(ids6)
    out["fichas con el EN_WEB de antes"] = len({p for p, _ in f3.values()})
    out["fichas con el de después"] = len(miembros6)
    out["segundos de las vistas y el resolvedor, antes"] = f"{s3[0]:.1f} + {s3[1]:.1f}"
    out["segundos de las vistas y el resolvedor, después"] = f"{s6[0]:.1f} + {s6[1]:.1f}"
    for clave in ("fichas entre categorías", "  por el mismo identificador (la misma fila)",
                  "  por U0 (mismo nombre, equipo y temporada)", "  por U0 de club o U1 (mismo club)",
                  "  por U2 (candidata única)", "  por una regla sin identificador", "fichas de antes que se parten",
                  "fichas de después que juntan dos de antes", "pares del mismo nombre y club que no se unen por la edad",
                  "pares del mismo nombre y club que no se unen por otra cosa"):
        out[clave] = 0
    for p, ks in miembros6.items():
        if not (any(vieja[k] for k in ks) and any(nueva[k] for k in ks)):
            continue
        out["fichas entre categorías"] += 1
        lado = vieja[p]                                  # el de la principal: con algo de antes, o solo de las nuevas
        if any(vieja[k] and nueva[k] for k in ks):
            out["  por el mismo identificador (la misma fila)"] += 1
        reglas = {f6[k][1] for k in ks if k != p and vieja[k] != lado and not (vieja[k] and nueva[k])}
        for regla, texto in (("equipo", "U0 (mismo nombre, equipo y temporada)"),
                             ("club", "U0 de club o U1 (mismo club)"), ("nombre", "U2 (candidata única)")):
            if regla in reglas:
                out[f"  por {texto}"] += 1
        if reglas:
            out["  por una regla sin identificador"] += 1
    # Las fichas de antes que el de después cambia: pierden identidades (se parten) o se juntan con otra de antes.
    miembros3 = defaultdict(list)
    for k, (p, _) in f3.items():
        miembros3[p].append(k)
    for p, ks in miembros3.items():
        destinos = {f6[k][0] for k in ks if k in f6}
        if len(destinos) > 1:
            out["fichas de antes que se parten"] += 1
    for p, ks in miembros6.items():
        if len({f3[k][0] for k in ks if k in f3}) > 1:
            out["fichas de después que juntan dos de antes"] += 1
    # Pares de fichas del mismo nombre con coma y del mismo club, una con algo de antes y otra solo de las nuevas,
    # que no se unen: por la edad (sus intervalos no se cruzan) o por otra cosa (ids, uno a uno, candidata única).
    from identidad import nombre_con_coma
    por_nombre = defaultdict(set)
    for p, ks in miembros6.items():
        for k in ks:
            if nombre_con_coma(_base(_nombre(por_id[k]))):
                por_nombre[_base(_nombre(por_id[k]))].add(p)
    for nombre, fichas in por_nombre.items():
        viejas = [p for p in fichas if any(vieja[k] for k in miembros6[p])]
        nuevas = [p for p in fichas if not any(vieja[k] for k in miembros6[p])]
        for a in viejas:
            va = [v for k in miembros6[a] for v in por_id[k].vistas]
            clubes_a = {club_de(v[2] or "") for v in va}
            for b in nuevas:
                vb = [v for k in miembros6[b] for v in por_id[k].vistas]
                if not clubes_a & {club_de(v[2] or "") for v in vb}:
                    continue
                if compatibles(va, vb):
                    out["pares del mismo nombre y club que no se unen por otra cosa"] += 1
                else:
                    out["pares del mismo nombre y club que no se unen por la edad"] += 1
    return dict(out)


def informe_entre_categorias(db, medida):
    lineas = [f"Entre categorías ({db}): EN_WEB de antes ({', '.join(EN_WEB_DE_ANTES)}) y de después (las seis)."]
    total = medida.get("fichas con el de después", 0) or 1
    for clave, valor in medida.items():
        lineas.append(f"  {clave}: {valor}")
    sin_id = medida.get("  por una regla sin identificador", 0)
    lineas.append(f"  fichas unidas entre categorías por una regla sin identificador: {100 * sin_id / total:.2f} % "
                  f"de las fichas (el paso E2-D2 se para si pasa del 2 %)")
    return "\n".join(lineas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=os.path.join(os.path.dirname(SCRIPTS), "futbolbase.db"))
    ap.add_argument("--entre-categorias", action="store_true",
                    help="lo que une el resolvedor al ampliar EN_WEB (paso E2-D2): solo lee la base")
    args = ap.parse_args(argv)
    if args.entre_categorias:
        print(informe_entre_categorias(args.db, entre_categorias(args.db)))
        return
    filas, cuenta = apariciones(args.db)
    nino = ninos(filas)
    texto, _ = informe(cuenta, nino, pares(filas, nino), resumen_u0_cortos(identidades_con_id(filas)))
    print(texto)
    print(informe_club(pares_club(filas, nino))[0])


if __name__ == "__main__":
    main()
