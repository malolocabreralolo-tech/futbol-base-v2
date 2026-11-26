#!/usr/bin/env python3
"""quitar_categoria.py — La marcha atrás de un paso del director (parte E1, D3-D6): saca de la base una
categoría nueva de una temporada, como si el bot nunca la hubiera activado ni leído.

    python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL            # ensayo: solo cuenta
    python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL --apply    # la quita
    python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria ALEVIN --isla lanzarote --apply
    python3 scripts/quitar_categoria.py ... --db <copia>                                       # otra base

Por defecto es un ENSAYO: hace el borrado en una transacción, cuenta lo que quitaría tabla a tabla y la deshace;
la base queda como estaba. Con --apply, lo mismo pero confirmando la transacción: o todo o nada. Para usarlo de
verdad, con el bot parado (reloj.yml desactivado: si no, una pasada podría estar escribiendo la base a la vez) y,
después, las suites en verde y el commit de la base (docs/superpowers/plans/2026-11-25-ampliacion-e1-categorias-
datos.md, «PASO DEL DIRECTOR»).

Solo acepta lo que puede haber entrado por un paso del director: infantil, cadete o juvenil (categorias.MAYORES;
con --isla, solo los de esa isla), o alevín con --isla lanzarote o fuerteventura (el paso D6). Cualquier otra
categoría (benjamín, prebenjamín, el alevín de Gran Canaria, una que no existe) sale con error sin tocar nada:
lo de siempre no tiene marcha atrás aquí, y borrarlo perdería datos que ningún importador devuelve.

Qué quita (vista_web.quitar_grupos, lo mismo que la copia de la web quita de su copia, aquí en la base que se le
da): los grupos de esa categoría (e isla) de la temporada y todo lo que cuelga de ellos y de sus partidos (toda
tabla con columna group_id o match_id, y lo que cuelga de esas filas por clave ajena: actas, apariciones,
sucesos, cuerpo técnico, goles, clasificaciones, goleadores, la lectura completa pendiente…); las fichas de la
temporada (team_seasons) de los equipos que esa temporada ya no salen en ningún grupo; los equipos que ya no
salen en nada; las identidades de acta (players) que solo salían en sus partidos; y la fila de categories si se
queda sin grupos. Un niño que ya estaba en la base (el de benjamín que la federación da con el mismo id en
cadete) conserva su fila: solo se le quitan las apariciones de lo borrado. Lo que no es de la categoría se queda,
aunque lo trajera su carril: el detalle de un campo (venue_details), que es del campo y no de la categoría.

Y, de infantil, cadete o juvenil entera (sin --isla), la huella en raw_imports del raw de actas de su lote en esa
temporada (scripts/fiflp_actas_<S>_<categoría>_raw.json, el que trae el carril del histórico): si se quedara, al
reactivarla import_changed_raws no volvería a importar esas actas (su huella no ha cambiado). Ese raw es solo de
esa categoría: en la base en la que nunca se activó, esa huella no estaría. Con --isla (el alevín de Lanzarote o
de Fuerteventura) no: su lote es el de alevín, compartido con el de Gran Canaria, y quitar su huella haría que la
pasada siguiente reimportara entero el alevín de Gran Canaria (docs/categorias-mayores.md dice qué hacer al
reactivarlo).

Y las fichas: si la categoría está en la web (categorias.EN_WEB, leído al llamar: el alevín de las islas siempre;
infantil, cadete y juvenil desde el paso E2-D2 de la parte E2), con --apply y ya quitada, las vuelve a resolver
(migrate_identidad.resolver_fichas) y rehace los enlaces de la liga de escuelas (enlace_mygol.guardar_enlaces), como
la pasada siguiente sin esa categoría: el resolvedor une fichas de una categoría a otra, y sin esto quedarían
uniones que solo sostenían sus partidos (y la base no sería la de nunca haberla activado). Entre las dos cosas, quita
las identidades que solo salían en sus partidos y no se borraron con ellos porque eran la principal de una ficha
(un cadete con id al que se había unido un benjamín sin id): resueltas otra vez, ya no lo son de nadie. Va después
del borrado, en su propia transacción: si fallara, el borrado ya está hecho y lo rehace la pasada siguiente, que
resuelve las fichas desde cero. Fuera de la web no hace falta: sus apariciones no cuentan para ninguna ficha ni
enlace (y sus identidades no son la principal de ninguna).
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import actas_lotes  # noqa: E402
import categorias  # noqa: E402
from categorias import MAYORES  # noqa: E402
import vista_web  # noqa: E402

# Las islas del alevín que entra en el paso D6 (categorias.ALEVIN_FUERA, en minúsculas como groups.island).
ISLAS_ALEVIN = ("lanzarote", "fuerteventura")


def _opciones(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--temporada", required=True, help="la temporada (2026-2027)")
    parser.add_argument("--categoria", required=True, help="INFANTIL, CADETE, JUVENIL o ALEVIN (con --isla)")
    parser.add_argument("--isla", choices=ISLAS_ALEVIN, help="solo los grupos de esa isla (con ALEVIN, obligatoria)")
    parser.add_argument("--apply", action="store_true", help="quitarlo de verdad (sin él, solo cuenta)")
    parser.add_argument("--db", type=Path, default=ROOT / "futbolbase.db", help="la base (por defecto, la del árbol)")
    args = parser.parse_args(argv)
    args.categoria = args.categoria.strip().upper()
    if args.categoria == "ALEVIN":
        if not args.isla:
            parser.error("ALEVIN solo con --isla lanzarote o fuerteventura: el de Gran Canaria es de siempre")
    elif args.categoria not in MAYORES:
        parser.error(f"{args.categoria}: solo se quita una categoría de un paso del director "
                     f"({', '.join(MAYORES)} o ALEVIN con --isla)")
    return args


def _recuentos(conn):
    return {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                     "ORDER BY name")}


def grupos(conn, temporada, categoria, isla=None):
    """[(id, código)] de los grupos de `categoria` (e `isla`) de `temporada`, por código."""
    rows = conn.execute(
        """SELECT g.id, g.code, coalesce(g.island, '') FROM groups g JOIN categories c ON c.id = g.category_id
           JOIN seasons s ON s.id = g.season_id WHERE s.name = ? AND upper(c.name) = ? ORDER BY g.code""",
        (temporada, categoria)).fetchall()
    return [(gid, code) for gid, code, island in rows if isla is None or island == isla]


def quitar(conn, temporada, categoria, isla=None, apply=False):
    """Quita (con `apply`) o cuenta (sin él: la transacción se deshace) los grupos de `categoria` (e `isla`) de
    `temporada` y lo que cuelga de ellos. Devuelve {"grupos": [códigos], "partidos": n, "actas": n, "filas":
    {tabla: filas quitadas}} y, si con `apply` ha vuelto a resolver las fichas (la categoría está en la web: ver el
    docstring del módulo), "fichas": lo que devolvió resolver_fichas. Con claves ajenas que quedaran colgando,
    ValueError y nada cambia."""
    if not conn.execute("SELECT 1 FROM seasons WHERE name=?", (temporada,)).fetchone():
        raise ValueError(f"la temporada {temporada} no está en la base")
    elegidos = grupos(conn, temporada, categoria, isla)
    ids = [gid for gid, _ in elegidos]
    out = {"grupos": [code for _, code in elegidos], "partidos": 0, "actas": 0, "filas": {}}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    out["partidos"], out["actas"] = conn.execute(
        f"SELECT count(*), count(cod_acta) FROM matches WHERE group_id IN ({marks})", ids).fetchone()
    # Las identidades de sus partidos: las que se queden sin nada tras resolver otra vez las fichas, fuera (abajo).
    suyas = {p for (p,) in conn.execute(
        f"""SELECT player_id FROM appearances WHERE match_id IN (SELECT id FROM matches WHERE group_id IN ({marks}))
            UNION SELECT player_id FROM match_events
             WHERE match_id IN (SELECT id FROM matches WHERE group_id IN ({marks}))""", ids + ids) if p is not None}
    # Las demás categorías que tienen filas en categories: la de la categoría quitada solo se borra si se queda
    # sin grupos (en ninguna temporada; el alevín de Gran Canaria, nunca).
    conservar = [n for (n,) in conn.execute("SELECT name FROM categories") if (n or "").upper() != categoria]
    if isla is not None:
        conservar.append(categoria)
    antes = _recuentos(conn)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")      # se borra en orden (vista_web); al final se comprueba que no cuelga nada
    conn.execute("BEGIN")
    try:
        vista_web.quitar_grupos(conn, ids, conservar)
        if isla is None and categoria in MAYORES and conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_imports'").fetchone():
            conn.execute("DELETE FROM raw_imports WHERE path=?",
                         (actas_lotes.file_name(temporada, "raw", actas_lotes.lote_of(categoria)),))
        colgando = conn.execute("PRAGMA foreign_key_check").fetchall()
        if colgando:
            raise ValueError(f"quedarían {len(colgando)} filas apuntando a lo borrado (la primera, en {colgando[0][0]})")
        despues = _recuentos(conn)
        out["filas"] = {t: antes[t] - despues.get(t, 0) for t in antes if antes[t] != despues.get(t, 0)}
        if apply:
            conn.commit()
        else:
            conn.rollback()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    if apply and categoria in categorias.EN_WEB:
        out["fichas"] = rehacer_fichas(conn, suyas)
        if out["fichas"]["sueltas_quitadas"]:
            out["filas"]["players"] = out["filas"].get("players", 0) + out["fichas"]["sueltas_quitadas"]
    return out


def rehacer_fichas(conn, suyas=()):
    """Lo que hace con las fichas la pasada siguiente: resolver_fichas (desde cero, con lo que queda en la base), y
    los enlaces de la liga de escuelas, que cuelgan de las fichas. Entre medias, de `suyas` (las identidades de los
    partidos quitados), las que se han quedado sin aparición ni suceso y ya no son la principal de nadie: las que el
    borrado dejó porque otra fila apuntaba a ellas (vista_web no borra la principal de una ficha). Devuelve lo de
    resolver_fichas, con "sueltas_quitadas"."""
    import enlace_mygol
    import migrate_identidad
    hecho = migrate_identidad.resolver_fichas(conn, log=lambda *a: None)
    sueltas = [(p,) for p in sorted(suyas) if not conn.execute(
        """SELECT 1 FROM appearances WHERE player_id=:p UNION ALL SELECT 1 FROM match_events WHERE player_id=:p
           UNION ALL SELECT 1 FROM players WHERE ficha_id=:p LIMIT 1""", {"p": p}).fetchone()]
    conn.execute("BEGIN")
    try:
        conn.executemany("DELETE FROM players WHERE id=?", sueltas)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    hecho["sueltas_quitadas"] = len(sueltas)
    enlace_mygol.guardar_enlaces(conn, registro=lambda *a: None)
    return hecho


def main(argv=None):
    args = _opciones(argv)
    if not args.db.exists():
        print(f"No existe la base {args.db}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(args.db)
    try:
        hecho = quitar(conn, args.temporada, args.categoria, args.isla, apply=args.apply)
    except ValueError as error:
        print(f"No se quita nada: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    que = f"{args.temporada} · {args.categoria}" + (f" de {args.isla}" if args.isla else "")
    if not hecho["grupos"]:
        print(f"{que}: ningún grupo; nada que quitar.")
        return 0
    filas = hecho["filas"]
    print(f"{que}: {len(hecho['grupos'])} grupos ({', '.join(hecho['grupos'])}), {hecho['partidos']} partidos, "
          f"{hecho['actas']} actas, {filas.get('appearances', 0)} apariciones, {filas.get('players', 0)} jugadores "
          f"sueltos (identidades solo de esos partidos), {filas.get('teams', 0)} equipos y "
          f"{filas.get('team_seasons', 0)} fichas de equipo")
    print("Filas por tabla: " + ", ".join(f"{t} {n}" for t, n in sorted(filas.items())))
    if "fichas" in hecho:
        f = hecho["fichas"]
        print(f"Fichas resueltas otra vez (la categoría está en la web): {f['identidades']} identidades → "
              f"{f['fichas']} fichas, {f['cambiadas']} filas cambiadas")
    print("Quitado." if args.apply else "Es un ensayo: la base no ha cambiado (con --apply, se quita).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
