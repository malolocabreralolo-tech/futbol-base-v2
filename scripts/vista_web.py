"""vista_web.py — La base que ve la web: una copia sin las categorías que la web aún no enseña.

Infantil, cadete y juvenil (parte E) entran en la base en cuanto el director las activa y su carril las lee,
pero la web no las enseña hasta su parte (E2: categorias.EN_WEB). El generador (generate_js) tiene unas 40
consultas, muchas sin filtro de categoría (las fichas, el buscador, el ranking, las temporadas, el historial,
«Datos y fuentes»…), y la web no sabe pintar una categoría que no conoce. Filtrar en cada consulta sería una
garantía que depende de no olvidar ninguna (ni la próxima que se escriba); una copia de la base de la que se
han borrado esas filas no depende de nada: el generador trabaja como si el bot nunca las hubiera leído.

    copia_web(conn, categorias=None) -> sqlite3.Connection

Con `categorias` None, categorias.EN_WEB leído al llamar (las pruebas lo parchean). Si la base no tiene
ningún grupo de otra categoría, devuelve LA MISMA conexión: cero coste hasta el primer paso del director. Si
los tiene, una copia en memoria (conn.backup) de la que se han borrado, en una transacción:

  - esos grupos y todo lo que cuelga de ellos: cualquier tabla con columna group_id (standings,
    standings_detail, scorers, fiflp_groups, fiflp_full_pending, detalle_groups, fp_ligas…);
  - sus partidos y todo lo que cuelga de ellos: cualquier tabla con columna match_id (appearances,
    match_events, match_staff_all, goals, fp_matches…), y lo que cuelga a su vez de esas filas por clave
    ajena (fp_goals de fp_matches);
  - las fichas de la temporada (team_seasons) de los equipos que esa temporada solo salían en esos grupos,
    los equipos que solo salían en ellos y las identidades de acta (players) que solo salían en sus partidos
    (las suyas, como el que nunca las hubiera leído);
  - y las filas de categories de esas categorías.

Las tablas se descubren por sus columnas (group_id, match_id) y por PRAGMA foreign_key_list: una tabla nueva
que cuelgue de un grupo o de un partido entra sola. La base original no se toca.
"""
import sqlite3

# Dónde sale un equipo en una temporada: si ya no sale en ningún grupo que queda, su ficha de esa temporada
# (team_seasons) era solo de lo borrado.
_EQUIPO_EN_GRUPO = (("standings", "team_id"), ("standings_detail", "team_id"), ("scorers", "team_id"))
_EQUIPO_EN_PARTIDO = (("matches", "home_team_id"), ("matches", "away_team_id"), ("appearances", "team_id"),
                      ("match_events", "team_id"), ("match_staff_all", "team_id"))


def _categorias_web(categorias):
    if categorias is not None:
        return tuple(categorias)
    try:
        import categorias as C
    except ImportError:            # importado como scripts.vista_web
        from scripts import categorias as C
    return tuple(C.EN_WEB)


def _tablas(conn):
    return [n for (n,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columnas(conn, tabla):
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{tabla}")')}


def grupos_fuera(conn, categorias=None):
    """Los ids de los grupos cuya categoría no está en `categorias` (por defecto, categorias.EN_WEB). Un grupo
    sin categoría se queda: no es de otra categoría (y la web lo trata hoy como lo trata)."""
    cats = {c.upper() for c in _categorias_web(categorias)}
    return [gid for gid, nombre in conn.execute(
        "SELECT g.id, c.name FROM groups g JOIN categories c ON c.id = g.category_id ORDER BY g.id")
        if nombre is not None and nombre.upper() not in cats]


def _hijos(conn, tablas):
    """{tabla padre: [(tabla hija, columna de la hija, columna del padre)]} por PRAGMA foreign_key_list (sin las
    que se apuntan a sí mismas: match_events.pair_id empareja sucesos del mismo partido, que se van juntos)."""
    hijos = {}
    for t in tablas:
        for r in conn.execute(f'PRAGMA foreign_key_list("{t}")'):
            padre, desde, hacia = r[2], r[3], r[4] or "id"
            if padre != t:
                hijos.setdefault(padre, []).append((t, desde, hacia))
    return hijos


def _borra(conn, tabla, donde, args, hijos, hechas):
    """Borra de `tabla` las filas de `donde` y, antes, lo que cuelga de ellas por clave ajena (salvo las tablas
    que ya se vacían por su columna group_id o match_id: `hechas`)."""
    for hija, col, col_padre in hijos.get(tabla, ()):
        if hija in hechas:
            continue
        sub = f'SELECT "{col_padre}" FROM "{tabla}" WHERE {donde}'
        _borra(conn, hija, f'"{col}" IN ({sub})', args, hijos, hechas)
    conn.execute(f'DELETE FROM "{tabla}" WHERE {donde}', args)


def _quitar(conn, fuera, categorias):
    """Lo que hace copia_web sobre la copia, en una transacción."""
    tablas = _tablas(conn)
    hijos = _hijos(conn, tablas)
    conn.execute("CREATE TEMP TABLE _fuera_grupos (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO temp._fuera_grupos VALUES (?)", [(g,) for g in fuera])
    conn.execute("CREATE TEMP TABLE _fuera_partidos (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO temp._fuera_partidos SELECT id FROM matches WHERE group_id IN (SELECT id FROM temp._fuera_grupos)")
    # Lo que se mira después: las temporadas de esos grupos, sus equipos y las identidades de sus partidos.
    temporadas = [s for (s,) in conn.execute(
        "SELECT DISTINCT season_id FROM groups WHERE id IN (SELECT id FROM temp._fuera_grupos)")]
    equipos = set()
    for tabla, col in _EQUIPO_EN_GRUPO:
        if tabla in tablas and {"group_id", col} <= _columnas(conn, tabla):
            equipos |= {t for (t,) in conn.execute(
                f'SELECT DISTINCT "{col}" FROM "{tabla}" WHERE group_id IN (SELECT id FROM temp._fuera_grupos)')}
    for tabla, col in _EQUIPO_EN_PARTIDO:
        if tabla in tablas:
            campo = "id" if tabla == "matches" else "match_id"
            equipos |= {t for (t,) in conn.execute(
                f'SELECT DISTINCT "{col}" FROM "{tabla}" WHERE "{campo}" IN (SELECT id FROM temp._fuera_partidos)')}
    equipos.discard(None)
    identidades = set()
    for tabla in ("appearances", "match_events"):
        if tabla in tablas:
            identidades |= {p for (p,) in conn.execute(
                f'SELECT DISTINCT player_id FROM "{tabla}" WHERE match_id IN (SELECT id FROM temp._fuera_partidos)')}
    identidades.discard(None)

    # Lo que cuelga de un partido, después lo que cuelga de un grupo, después los partidos y los grupos.
    por_partido = [t for t in tablas if t != "matches" and "match_id" in _columnas(conn, t)]
    por_grupo = [t for t in tablas if t not in ("groups", "matches") and "group_id" in _columnas(conn, t)]
    hechas = set(por_partido) | set(por_grupo) | {"matches", "groups"}
    for t in por_partido:
        _borra(conn, t, "match_id IN (SELECT id FROM temp._fuera_partidos)", (), hijos, hechas)
    for t in por_grupo:
        _borra(conn, t, "group_id IN (SELECT id FROM temp._fuera_grupos)", (), hijos, hechas)
    _borra(conn, "matches", "id IN (SELECT id FROM temp._fuera_partidos)", (), hijos, hechas)
    _borra(conn, "groups", "id IN (SELECT id FROM temp._fuera_grupos)", (), hijos, hechas)

    # Las fichas de la temporada de los equipos que esa temporada ya no salen en ningún grupo.
    def sale(tid, sid):
        for tabla, col in _EQUIPO_EN_GRUPO:
            if tabla in tablas and conn.execute(
                    f'SELECT 1 FROM "{tabla}" x JOIN groups g ON g.id = x.group_id WHERE x."{col}"=? AND g.season_id=? '
                    'LIMIT 1', (tid, sid)).fetchone():
                return True
        for col in ("home_team_id", "away_team_id"):
            if conn.execute(f'SELECT 1 FROM matches m JOIN groups g ON g.id = m.group_id WHERE m."{col}"=? '
                            'AND g.season_id=? LIMIT 1', (tid, sid)).fetchone():
                return True
        return False

    if "team_seasons" in tablas:
        for tid in sorted(equipos):
            for sid in temporadas:
                if not sale(tid, sid):
                    _borra(conn, "team_seasons", "team_id=? AND season_id=?", (tid, sid), hijos, set())
    # Los equipos que ya no salen en nada: ni en un grupo ni en un partido, ni con ficha de ninguna temporada.
    # De una vez (una tabla temporal y un NOT IN por tabla): uno a uno, cada consulta recorre la tabla entera.
    restos = [(t, c) for t, c in _EQUIPO_EN_GRUPO + _EQUIPO_EN_PARTIDO + (("team_seasons", "team_id"),)
              if t in tablas]
    conn.execute("CREATE TEMP TABLE _fuera_equipos (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO temp._fuera_equipos VALUES (?)", [(t,) for t in sorted(equipos)])
    sigue = "".join(f' AND id NOT IN (SELECT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL)' for t, c in restos)
    conn.execute(f"DELETE FROM temp._fuera_equipos WHERE NOT (1{sigue})")
    _borra(conn, "teams", "id IN (SELECT id FROM temp._fuera_equipos)", (), hijos, {"players"})
    # Las identidades que solo salían en esos partidos (y que nadie más tiene por principal de su ficha).
    if "players" in tablas:
        conn.execute("CREATE TEMP TABLE _fuera_jugadores (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO temp._fuera_jugadores VALUES (?)", [(i,) for i in sorted(identidades)])
        sigue = "".join(f" AND id NOT IN (SELECT player_id FROM {t} WHERE player_id IS NOT NULL)"
                        for t in ("appearances", "match_events") if t in tablas)
        if "ficha_id" in _columnas(conn, "players"):
            sigue += " AND id NOT IN (SELECT ficha_id FROM players WHERE ficha_id IS NOT NULL)"
        conn.execute(f"DELETE FROM temp._fuera_jugadores WHERE NOT (1{sigue})")
        _borra(conn, "players", "id IN (SELECT id FROM temp._fuera_jugadores)", (), hijos, set())
        conn.execute("DROP TABLE temp._fuera_jugadores")
    conn.execute("DROP TABLE temp._fuera_equipos")
    # Y las categorías que ya no tienen ningún grupo.
    cats = {c.upper() for c in categorias}
    for cid, nombre in conn.execute("SELECT id, name FROM categories").fetchall():
        if (nombre or "").upper() not in cats and not conn.execute(
                "SELECT 1 FROM groups WHERE category_id=? LIMIT 1", (cid,)).fetchone():
            _borra(conn, "categories", "id=?", (cid,), hijos, set())
    conn.execute("DROP TABLE temp._fuera_grupos")
    conn.execute("DROP TABLE temp._fuera_partidos")


def copia_web(conn, categorias=None):
    """La base que ve la web (ver el docstring del módulo): `conn` tal cual si no tiene ningún grupo de una
    categoría fuera de `categorias` (por defecto categorias.EN_WEB); si no, una copia en memoria sin ellos."""
    cats = _categorias_web(categorias)
    fuera = grupos_fuera(conn, cats)
    if not fuera:
        return conn
    copia = sqlite3.connect(":memory:")
    conn.backup(copia)
    copia.row_factory = conn.row_factory
    copia.execute("PRAGMA foreign_keys=OFF")        # se borra en orden; así una fila vieja suelta no lo para
    copia.execute("BEGIN")
    try:
        _quitar(copia, fuera, cats)
        copia.commit()
    except BaseException:
        copia.rollback()
        copia.close()
        raise
    return copia
