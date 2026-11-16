"""La migración a identidades de acta (migrate_identidad): cada aparición a su identidad de acta según el
original, sin perder ni borrar nada, y las fichas por encima (docs/identidad.md).

Sobre una base pequeña montada aquí con el importador de verdad (_import_one) con el
_get_or_create_player anterior a las identidades (_pegado_por_nombre, que pega por el nombre las
apariciones sin id a la fila de otro niño, como hizo con la base real) y unos originales escritos en una
carpeta temporal. Nombres inventados."""
import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
import import_fiflp_actas as I  # noqa: E402
import migrate_identidad as M  # noqa: E402
from identidad import clave_publica  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402

quiet = lambda *a, **k: None  # noqa: E731

SEED = """
INSERT INTO seasons(id, name, start_year, end_year) VALUES (1, '2023-2024', 2023, 2024), (2, '2025-2026', 2025, 2026),
  (3, '2026-2027', 2026, 2027);
INSERT INTO categories(id, name) VALUES (1, 'BENJAMIN'), (2, 'PREBENJAMIN');
INSERT INTO groups(id, season_id, category_id, code, name, island) VALUES
  (1, 1, 1, 'BGC1', 'Grupo 1', 'grancanaria'), (2, 2, 2, 'PG1', 'Grupo 1', 'grancanaria'),
  (3, 3, 2, 'PG1', 'Grupo 1', 'grancanaria'), (4, 3, 1, 'BGC1', 'Grupo 1', 'grancanaria'),
  (5, 3, 2, 'PFV1', 'Grupo 1', 'fuerteventura');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Club Tres'), (4, 'Union Cuatro');
"""


def base():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    conn.executescript(SEED)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def partido(conn, mid, gid, local, visitante, fecha, cod=None):
    conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score,"
                 " cod_acta) VALUES (?,?,?,?,?,?,1,0,?)", (mid, gid, f"Jornada {mid}", fecha, local, visitante, cod))


def acta(local=(), visitante=(), sucesos=()):
    """local/visitante: [(dorsal, nombre, fiflp_id o None)]; sucesos: [(lado, nombre, tipo)]."""
    def lado(js):
        return [{"dorsal": d, "name": n, "role": "starter", "fiflp_id": f} for d, n, f in js]
    return {"header": {}, "lineups": {"home": lado(local), "away": lado(visitante)},
            "events": [{"kind": k, "side": s, "player_name": n, "minute": 10 + i, "goal_type": "normal"}
                       for i, (s, n, k) in enumerate(sucesos)]}


def _pegado_por_nombre(conn, name, fiflp_id=None, team_id=None, season_id=None, ordinal=1):
    """El _get_or_create_player anterior a las identidades (tal cual, sin la comprobación de la columna
    fiflp_id): por el id y, si no, por el nombre normalizado en toda la base, adoptando la fila sin id si
    el nombre lleva coma. El equipo, la temporada y el ordinal no los usaba."""
    norm = I._norm_player(name)
    with_id = fiflp_id is not None
    if with_id:
        r = conn.execute("SELECT id FROM players WHERE fiflp_id=?", (fiflp_id,)).fetchone()
        if r:
            return r[0]
    r = conn.execute("SELECT id, " + ("fiflp_id" if with_id else "NULL") +
                     " FROM players WHERE norm_name=?", (norm,)).fetchone()
    adopt = r and r[1] is None and (not with_id or "," in name)
    if r and (not with_id or r[1] == fiflp_id or adopt):
        if with_id and r[1] is None:
            conn.execute("UPDATE players SET fiflp_id=? WHERE id=?", (fiflp_id, r[0]))
        return r[0]
    if r:
        norm = f"{norm}#{fiflp_id}"
    if with_id:
        return conn.execute("INSERT INTO players(full_name, norm_name, fiflp_id) VALUES(?, ?, ?)",
                            (name, norm, fiflp_id)).lastrowid
    return conn.execute("INSERT INTO players(full_name, norm_name) VALUES(?, ?)", (name, norm)).lastrowid


@contextlib.contextmanager
def importador_de_antes():
    """_import_one con el _get_or_create_player de antes: lo que había en la base al migrar."""
    nuevo = I._get_or_create_player
    I._get_or_create_player = _pegado_por_nombre
    try:
        yield
    finally:
        I._get_or_create_player = nuevo


def importa(conn, mid, gid, local, visitante, fecha, cod, a, raws=None, base_acta=None):
    """Un partido con su acta importada como lo hizo el importador anterior a las identidades; el original va a
    `raws` (por temporada)."""
    partido(conn, mid, gid, local, visitante, fecha, cod)
    with importador_de_antes():
        I._import_one(conn, cod, base_acta or a, mid)
    conn.commit()
    if raws is not None:
        raws[cod] = a


def escribe_raws(carpeta, raws, temporada="2025-2026"):
    (carpeta / f"fiflp_actas_{temporada}_raw.json").write_text(
        json.dumps({str(k): v for k, v in raws.items()}), encoding="utf-8")


def fila(conn, pid):
    return conn.execute("SELECT id, norm_name, fiflp_id, team_id, season_id, ordinal, ficha_id, union_por "
                        "FROM players WHERE id=?", (pid,)).fetchone()


def de_quien(conn, mid, tid):
    """{nombre normalizado de la fila: (norm_name, fiflp_id)} de las apariciones de un equipo en un partido."""
    return {M.nombre_base(n): (n, f) for n, f in conn.execute(
        "SELECT p.norm_name, p.fiflp_id FROM appearances a JOIN players p ON p.id=a.player_id "
        "WHERE a.match_id=? AND a.team_id=?", (mid, tid))}


def pid_de(conn, norm_name):
    return conn.execute("SELECT id FROM players WHERE norm_name=?", (norm_name,)).fetchone()[0]


@pytest.fixture
def mundo(tmp_path):
    """La base con los casos de la migración. Devuelve (conn, carpeta de los originales)."""
    conn = base()
    raws = {}
    # 2023-24, benjamín, con id: los niños de siempre.
    importa(conn, 1, 1, 1, 2, "2023-10-07", 1001, acta(
        [(5, "PEREZ PEREZ, ANA", 501), (7, "LOPEZ RUIZ, PEDRO", 502)],
        [(9, "GIL GIL, LUIS", 503), (4, "BRAVO LEON, OMAR", 902)]), raws)
    # 2025-26, liga prebenjamín de GC: sin ids. «PEREZ PEREZ, ANA» es otra niña (en 2023-24 era benjamín);
    # el importador la pega a la fila 501 por el nombre.
    importa(conn, 2, 2, 3, 1, "2025-10-04", 1002, acta(
        [(4, "PEREZ PEREZ, ANA", None), (6, "MORA DIAZ, EVA", None)], [(9, "GIL GIL, LUIS", None)],
        [("home", "MORA DIAZ, EVA", "goal"), ("away", "GIL GIL, LUIS", "yellow")]), raws)
    # 2026-27, benjamín, con id: EVA del año anterior, ya con id (adopta la fila sin id: lleva coma).
    importa(conn, 3, 4, 3, 2, "2026-10-03", 1003, acta([(10, "MORA DIAZ, EVA", 601)], [(2, "VERA, TEO", 602)]), raws)
    # 2023-24: el original dice 801, pero la base lo tiene en la fila de 802 (el id de la fila está mal).
    importa(conn, 5, 1, 1, 2, "2023-11-04", 1005, acta([(3, "ROJAS VEGA, IRIS", 801)], [(1, "SOTO, BEA", 803)]),
            raws, base_acta=acta([(3, "ROJAS VEGA, IRIS", 802)], [(1, "SOTO, BEA", 803)]))
    # 2023-24: un goleador que no está en la alineación (OMAR: el importador lo pega a la fila 902) y otro
    # escrito con tilde que sí está (RAUL).
    importa(conn, 8, 1, 2, 1, "2023-11-11", 1008, acta(
        [(11, "CANO, RAUL", 901)], [(5, "PEREZ PEREZ, ANA", 501)],
        [("home", "CANO, RAUL", "goal"), ("home", "BRAVO LEON, OMAR", "goal"), ("home", "CANÓ, RAUL", "yellow")]),
        raws)
    # Un acta del original que no tiene partido en la base.
    raws[9999] = acta([(1, "NADIE, NADA", None)])
    # 2026-27, sin original: un niño viejo sin id (fila global) en dos equipos, y un niño con id en
    # Fuerteventura (se queda), y la liga prebenjamín de GC (sin id aunque la fila lo tenga).
    conn.execute("INSERT INTO players(id, full_name, norm_name) VALUES (300, 'TORRES, NOA', 'TORRES, NOA')")
    conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (301, 'LEON, ARI', 'LEON, ARI', 1001)")
    partido(conn, 6, 4, 2, 3, "2026-10-10", 1006)
    partido(conn, 7, 4, 4, 1, "2026-10-17", 1007)
    partido(conn, 10, 5, 1, 2, "2026-10-24", 1010)
    partido(conn, 11, 3, 3, 4, "2026-10-31", 1011)
    conn.executemany("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) VALUES (?,?,?,?,'starter',?)",
                     [(6, 2, 300, 8, 0), (7, 4, 300, 8, 0), (10, 1, 301, 3, 0), (11, 3, 301, 3, 0)])
    conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES (7, 4, 300, 'goal', 5)")
    conn.commit()
    escribe_raws(tmp_path, raws)
    return conn, tmp_path


def test_el_esquema_es_idempotente():
    # La tabla players anterior a las identidades (migrate_actas_schema ya trae las columnas nuevas).
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, norm_name TEXT NOT NULL "
                 "UNIQUE, fiflp_id INTEGER)")
    assert M.asegurar_esquema(conn) is True
    assert M.asegurar_esquema(conn) is False
    cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    assert {"ficha_id", "union_por", "team_id", "season_id", "ordinal", "clave"} <= cols
    indices = {r[1] for r in conn.execute("PRAGMA index_list(players)")}
    assert {"idx_players_fiflp", "idx_players_sin_id", "idx_players_ficha", "idx_players_clave"} <= indices


def test_el_esquema_guarda_la_clave_de_las_identidades_sin_id_que_no_la_tienen():
    """La clave pública de una identidad sin id se calcula una vez, con el nombre del equipo de ese momento,
    y se guarda (players.clave); las que tienen id no la llevan (su clave es el id)."""
    conn = base()
    conn.executemany("INSERT INTO players(id, full_name, norm_name, fiflp_id, team_id, season_id, ordinal) "
                     "VALUES (?,?,?,?,?,?,?)", [(1, "SOL, ANA", "SOL, ANA@3.2", None, 3, 2, None),
                                                (2, "SOL, ANA", "SOL, ANA@3.2#2", None, 3, 2, 2),
                                                (3, "SOL, ANA", "SOL, ANA", 777, None, None, None)])
    conn.commit()
    M.asegurar_esquema(conn)
    claves = dict(conn.execute("SELECT id, clave FROM players"))
    assert claves == {1: clave_publica(None, "SOL, ANA", "Club Tres", 2025),
                      2: clave_publica(None, "SOL, ANA#2", "Club Tres", 2025), 3: None}
    # Ya guardada, no se recalcula: renombrar el equipo no la cambia.
    conn.execute("UPDATE teams SET name='Club Tres Renombrado' WHERE id=3")
    conn.commit()
    M.asegurar_esquema(conn)
    assert dict(conn.execute("SELECT id, clave FROM players")) == claves


def test_dos_filas_no_comparten_clave():
    """Un equipo que hoy se llama como se llamaba otro cuando se creó una identidad: la nueva lleva la clave
    del nombre con '|<id>' (y el índice único lo garantiza)."""
    conn = base()
    conn.execute("INSERT INTO players(id, full_name, norm_name, team_id, season_id) VALUES "
                 "(1, 'SOL, ANA', 'SOL, ANA@1.2', 1, 2)")
    M.poner_claves(conn)
    conn.execute("UPDATE teams SET name='Atletico Viejo' WHERE id=1")
    conn.execute("UPDATE teams SET name='Atletico Uno' WHERE id=2")
    conn.execute("INSERT INTO players(id, full_name, norm_name, team_id, season_id) VALUES "
                 "(2, 'SOL, ANA', 'SOL, ANA@2.2', 2, 2)")
    assert M.poner_claves(conn, [2]) == 1
    claves = dict(conn.execute("SELECT id, clave FROM players"))
    assert claves[1] == clave_publica(None, "SOL, ANA", "Atletico Uno", 2025)
    assert claves[2] == clave_publica(None, "SOL, ANA|2", "Atletico Uno", 2025) != claves[1]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE players SET clave=? WHERE id=2", (claves[1],))


def test_la_migracion_deja_todas_las_identidades_sin_id_con_su_clave(mundo):
    conn, raws = mundo
    M.migrate(conn, str(raws), log=quiet)
    filas = conn.execute("SELECT p.norm_name, p.ordinal, p.clave, t.name, s.start_year FROM players p "
                         "JOIN teams t ON t.id=p.team_id JOIN seasons s ON s.id=p.season_id "
                         "WHERE p.fiflp_id IS NULL").fetchall()
    assert len(filas) >= 5
    for norm_name, ordinal, guardada, equipo, anio in filas:
        nombre = M.nombre_base(norm_name) + (f"#{ordinal}" if ordinal and ordinal > 1 else "")
        assert guardada == clave_publica(None, nombre, equipo, anio)
    assert conn.execute("SELECT count(*) FROM players WHERE fiflp_id IS NOT NULL AND clave IS NOT NULL").fetchone()[0] == 0


def test_nombre_base_y_norm_sin_id():
    assert M.norm_sin_id("ANA", 3, 2) == "ANA@3.2"
    assert M.norm_sin_id("ANA", 3, 2, 1) == "ANA@3.2"
    assert M.norm_sin_id("ANA", 3, 2, 2) == "ANA@3.2#2"
    for n in ("ANA", "ANA#501", "ANA@3.2", "ANA@3.2#2"):
        assert M.nombre_base(n) == "ANA"
    assert M.nombre_base("#SIN NOMBRE PUBLICADO") == "#SIN NOMBRE PUBLICADO"


def test_separa_exactamente_lo_que_el_original_dice_que_vino_sin_id(mundo):
    conn, raws = mundo
    ana = pid_de(conn, "PEREZ PEREZ, ANA")
    assert len(M.perfil(conn, ana)) == 2            # pegada: benjamín 2023-24 y prebenjamín 2025-26
    r = M.migrate(conn, str(raws), log=quiet)
    # La fila 501 queda limpia: solo lo suyo (benjamín 2023-24, dos partidos).
    assert [(s, c) for s, c, *_ in M.perfil(conn, ana)] == [("2023-2024", "BENJAMIN")]
    assert M.perfil(conn, ana)[0][4] == 1 + 1
    # Las tres del partido 2 van a identidades sin id de su equipo y temporada.
    assert de_quien(conn, 2, 3) == {"PEREZ PEREZ, ANA": ("PEREZ PEREZ, ANA@3.2", None),
                                    "MORA DIAZ, EVA": ("MORA DIAZ, EVA@3.2", None)}
    assert de_quien(conn, 2, 1) == {"GIL GIL, LUIS": ("GIL GIL, LUIS@1.2", None)}
    nueva = fila(conn, pid_de(conn, "PEREZ PEREZ, ANA@3.2"))
    assert nueva[2:6] == (None, 3, 2, None)
    assert conn.execute("SELECT full_name FROM players WHERE id=?", (nueva[0],)).fetchone()[0] == "PEREZ PEREZ, ANA"
    # Los sucesos van con su aparición.
    eva_sin = pid_de(conn, "MORA DIAZ, EVA@3.2")
    assert conn.execute("SELECT kind FROM match_events WHERE match_id=2 AND team_id=3").fetchall() == [("goal",)]
    assert conn.execute("SELECT player_id FROM match_events WHERE match_id=2 AND team_id=3").fetchone()[0] == eva_sin
    assert conn.execute("SELECT goals FROM appearances WHERE match_id=2 AND player_id=?", (eva_sin,)).fetchone()[0] == 1
    assert r["separar"]["apariciones separadas"] >= 3


def test_los_recuentos_son_identicos_y_no_se_borra_ninguna_fila(mundo):
    conn, raws = mundo
    antes = M.recuentos(conn)
    ids_antes = {pid for (pid,) in conn.execute("SELECT id FROM players")}
    r = M.migrate(conn, str(raws), log=quiet)
    despues = M.recuentos(conn)
    for t in M.TABLAS:
        if t != "players":
            assert antes[t] == despues[t], t
    assert ids_antes <= {pid for (pid,) in conn.execute("SELECT id FROM players")}
    assert r["antes"] == antes and r["despues"] == despues
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_es_idempotente(mundo):
    conn, raws = mundo
    M.migrate(conn, str(raws), log=quiet)
    foto = lambda: (conn.execute("SELECT * FROM players ORDER BY id").fetchall(),  # noqa: E731
                    conn.execute("SELECT match_id, team_id, player_id FROM appearances ORDER BY 1,2,3").fetchall(),
                    conn.execute("SELECT id, player_id FROM match_events ORDER BY id").fetchall())
    primera = foto()
    r2 = M.migrate(conn, str(raws), log=quiet)
    assert foto() == primera
    assert r2["movidas"] == [] and r2["fichas"]["cambiadas"] == 0
    assert r2["antes"] == r2["despues"]


def test_corrige_el_id_de_la_fila_por_el_del_original(mundo):
    conn, raws = mundo
    r = M.migrate(conn, str(raws), log=quiet)
    norm, fid = de_quien(conn, 5, 1)["ROJAS VEGA, IRIS"]
    assert fid == 801 and norm == "ROJAS VEGA, IRIS#801"      # el nombre ya era de la fila 802
    assert r["separar"]["corregidas por identificador"] == 1
    # La fila 802 se conserva, vacía.
    vieja = conn.execute("SELECT id FROM players WHERE fiflp_id=802").fetchone()[0]
    assert M.perfil(conn, vieja) == []


def test_el_goleador_que_no_esta_en_la_alineacion_va_sin_id(mundo):
    conn, raws = mundo
    omar = conn.execute("SELECT id FROM players WHERE fiflp_id=902").fetchone()[0]
    raul = conn.execute("SELECT id FROM players WHERE fiflp_id=901").fetchone()[0]
    M.migrate(conn, str(raws), log=quiet)
    # OMAR (con id 902 en otro partido) marcó sin estar en la alineación: no es la fila 902.
    norm, fid = de_quien(conn, 8, 2)["BRAVO LEON, OMAR"]
    assert (norm, fid) == ("BRAVO LEON, OMAR@2.1", None)
    sin = pid_de(conn, norm)
    assert conn.execute("SELECT count(*) FROM match_events WHERE match_id=8 AND player_id=?", (sin,)).fetchone()[0] == 1
    assert [(s, c) for s, c, *_ in M.perfil(conn, omar)] == [("2023-2024", "BENJAMIN")]
    # «CANÓ, RAUL» es el único de la alineación con ese nombre normalizado: es él.
    assert conn.execute("SELECT count(*) FROM match_events WHERE match_id=8 AND player_id=?", (raul,)).fetchone()[0] == 2


def test_sin_original_la_liga_prebenjamin_gc_va_sin_id_y_lo_demas_respeta_la_fila(mundo):
    conn, raws = mundo
    M.migrate(conn, str(raws), log=quiet)
    # El niño de Fuerteventura con id se queda; en la liga prebenjamín de GC, sin id.
    assert de_quien(conn, 10, 1) == {"LEON, ARI": ("LEON, ARI", 1001)}
    assert de_quien(conn, 11, 3) == {"LEON, ARI": ("LEON, ARI@3.3", None)}
    # La fila vieja sin id se reparte por equipo y temporada; se conserva, vacía. Su gol va con ella.
    assert de_quien(conn, 6, 2) == {"TORRES, NOA": ("TORRES, NOA@2.3", None)}
    assert de_quien(conn, 7, 4) == {"TORRES, NOA": ("TORRES, NOA@4.3", None)}
    assert M.perfil(conn, 300) == []
    assert conn.execute("SELECT player_id FROM match_events WHERE match_id=7").fetchone()[0] == pid_de(conn, "TORRES, NOA@4.3")


def test_lo_que_no_casa_se_cuenta_y_no_se_toca(mundo):
    conn, raws = mundo
    r = M.migrate(conn, str(raws), log=quiet)
    assert r["separar"]["actas del original sin partido en la base"] == 1
    assert r["originales"]["actas"] == 6


def test_las_fichas_unen_lo_compatible_y_los_punteros_son_buenos(mundo):
    conn, raws = mundo
    r = M.migrate(conn, str(raws), log=quiet)
    # EVA sin id (prebenjamín 2025-26) y con id (benjamín 2026-27), del mismo club: U1 (antes que U2, que
    # también la uniría: es la única otra ficha con su nombre).
    eva_sin, eva = pid_de(conn, "MORA DIAZ, EVA@3.2"), conn.execute(
        "SELECT id FROM players WHERE fiflp_id=601").fetchone()[0]
    assert fila(conn, eva_sin)[6:] == (eva, "club")
    assert fila(conn, eva)[6:] == (None, None)
    # ANA sin id (prebenjamín 2025-26) no se une a la ANA con id (benjamín 2023-24): imposible por edad.
    assert fila(conn, pid_de(conn, "PEREZ PEREZ, ANA@3.2"))[6] is None
    # Ninguna ficha_id apunta a una fila que no existe ni a una secundaria.
    assert M.comprobar(conn)["punteros malos"] == 0
    assert r["fichas"]["uniones"].get("club", 0) >= 1
    assert M.medida_fichas(conn)["cuenta"].get("imposibles por edad", 0) == 0


def test_antes_de_migrar_la_fila_pegada_es_imposible_por_edad(mundo):
    conn, _ = mundo
    antes = M.medida_fichas(conn)["cuenta"]
    assert antes["imposibles por edad"] >= 1           # ANA y LUIS: benjamín 2023-24 y prebenjamín 2025-26


def test_dos_homonimos_sin_id_en_la_misma_alineacion_no_pierden_ninguna_aparicion(tmp_path):
    """Dos «DANIEL» sin id en un equipo y un partido. Con original: el de dorsal más bajo es
    la identidad normal y el otro lleva ordinal; sin original, igual por el dorsal."""
    conn = base()
    conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (40, 'DANIEL', 'DANIEL', 701),"
                 " (41, 'DANIEL', 'DANIEL#702', 702)")
    partido(conn, 1, 2, 3, 4, "2025-10-04", 2001)      # con original (liga prebenjamín 2025-26)
    partido(conn, 2, 3, 3, 4, "2026-10-04", 2002)      # sin original (2026-27)
    conn.executemany("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) VALUES (?,?,?,?,'starter',?)",
                     [(1, 3, 41, 3, 0), (1, 3, 40, 8, 1), (2, 3, 40, 2, 0), (2, 3, 41, 9, 1)])
    conn.executemany("INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES (?,?,?,'goal',?)",
                     [(1, 3, 40, 5), (2, 3, 41, 7)])
    conn.commit()
    escribe_raws(tmp_path, {2001: acta([(8, "DANIEL", None), (3, "DANIEL", None)])})
    antes = M.recuentos(conn)
    M.migrate(conn, str(tmp_path), log=quiet)
    assert M.recuentos(conn)["appearances"] == antes["appearances"]
    filas = dict(conn.execute("SELECT a.dorsal, p.norm_name FROM appearances a JOIN players p ON p.id=a.player_id "
                              "WHERE a.match_id=1").fetchall())
    assert filas == {3: "DANIEL@3.2", 8: "DANIEL@3.2#2"}
    filas = dict(conn.execute("SELECT a.dorsal, p.norm_name FROM appearances a JOIN players p ON p.id=a.player_id "
                              "WHERE a.match_id=2").fetchall())
    assert filas == {2: "DANIEL@3.3", 9: "DANIEL@3.3#2"}
    # El gol va con su aparición (dorsal 8 en el 1, dorsal 9 en el 2).
    assert conn.execute("SELECT p.norm_name FROM match_events e JOIN players p ON p.id=e.player_id "
                        "WHERE e.match_id=1").fetchone()[0] == "DANIEL@3.2#2"
    assert conn.execute("SELECT p.norm_name FROM match_events e JOIN players p ON p.id=e.player_id "
                        "WHERE e.match_id=2").fetchone()[0] == "DANIEL@3.3#2"
    assert fila(conn, pid_de(conn, "DANIEL@3.2#2"))[5] == 2
    # El ordinal no se une a nada (docs/identidad.md).
    assert fila(conn, pid_de(conn, "DANIEL@3.2#2"))[6] is None
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # Y la segunda vez no cambia nada.
    assert M.migrate(conn, str(tmp_path), log=quiet)["movidas"] == []


def test_dos_apariciones_que_se_cambian_la_fila(tmp_path):
    """Las dos «DANIEL» de un equipo ya separadas, pero al revés de lo que dice el dorsal del original: se
    cambian la fila sin chocar en la clave primaria de appearances, y cada gol va con su aparición."""
    conn = base()
    M.asegurar_esquema(conn)
    conn.execute("INSERT INTO players(id, full_name, norm_name, team_id, season_id, ordinal) VALUES "
                 "(50, 'DANIEL', 'DANIEL@3.2', 3, 2, NULL), (51, 'DANIEL', 'DANIEL@3.2#2', 3, 2, 2)")
    partido(conn, 1, 2, 3, 4, "2025-10-04", 3001)
    conn.executemany("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                     "VALUES (?,?,?,?,'starter',?,?)", [(1, 3, 50, 8, 1, 0), (1, 3, 51, 3, 0, 1)])
    conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES (1, 3, 50, 'goal', 3)")
    conn.commit()
    escribe_raws(tmp_path, {3001: acta([(3, "DANIEL", None), (8, "DANIEL", None)])})
    M.migrate(conn, str(tmp_path), log=quiet)
    assert dict(conn.execute("SELECT dorsal, player_id FROM appearances")) == {3: 50, 8: 51}
    assert conn.execute("SELECT player_id FROM match_events").fetchone()[0] == 51
    assert conn.execute("SELECT goals FROM appearances WHERE player_id=51").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_los_originales_del_bot_mandan_sobre_la_regla(tmp_path):
    """Sin original, la liga prebenjamín de GC va sin id; con el original del bot que trae el id, se queda.
    De un acta leída dos veces manda la última lectura."""
    conn = base()
    conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (60, 'LUZ, ARI', 'LUZ, ARI', 1001)")
    partido(conn, 1, 3, 3, 4, "2026-10-04", 4001)
    conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) VALUES (1, 3, 60, 5, 'starter', 0)")
    conn.commit()
    lineas = [{"acta": acta([(5, "LUZ, ARI", None)]), "cod_acta": 4001, "leida": "2026-11-01T10:00:00"},
              {"acta": acta([(5, "LUZ, ARI", 1001)]), "cod_acta": 4001, "leida": "2026-11-02T10:00:00"}]
    (tmp_path / "actas_bot_2026-2027_prebenjamin.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    escribe_raws(tmp_path, {4001: acta([(5, "LUZ, ARI", None)])}, "2026-2027")
    r = M.migrate(conn, str(tmp_path), log=quiet)
    assert de_quien(conn, 1, 3) == {"LUZ, ARI": ("LUZ, ARI", 1001)}
    assert r["originales"]["actas de los raws sustituidas por el original del bot"] == 1


def test_resolver_fichas_solo_escribe_lo_que_cambia_y_deshace_lo_que_ya_no_vale(mundo):
    conn, raws = mundo
    M.migrate(conn, str(raws), log=quiet)
    assert M.resolver_fichas(conn, log=quiet)["cambiadas"] == 0
    # Una fila sin apariciones con una ficha_id puesta a mano vuelve a quedar suelta.
    conn.execute("UPDATE players SET ficha_id=1, union_por='nombre' WHERE id=300")
    conn.commit()
    assert M.resolver_fichas(conn, log=quiet)["cambiadas"] == 1
    assert fila(conn, 300)[6:] == (None, None)


def test_el_informe_no_lleva_nombres_y_las_muestras_si(mundo):
    conn, raws = mundo
    antes = M.medida_fichas(conn)
    r = M.migrate(conn, str(raws), log=quiet)
    texto = M.informe(r, antes, M.medida_fichas(conn), M.ejemplos_d12(conn, {}, r["movidas"]), None,
                      M.comprobar(conn))
    nombres = {n for (n,) in conn.execute("SELECT full_name FROM players WHERE full_name <> ''")}
    partes = {w for n in nombres for w in n.replace(",", " ").split() if len(w) > 2}
    assert not [w for w in partes if w in texto]
    assert "MORA DIAZ, EVA" in M.muestras(conn, r["movidas"])


def test_iniciales():
    assert M.iniciales("HERRERA GIL, ANA") == "A. H. G."
    assert M.iniciales("LUCAS") == "L."


def test_una_aparicion_sin_dorsal_que_el_original_no_trae_es_un_goleador_sin_id(tmp_path):
    """El importador solo deja una aparición sin dorsal para quien sale en los sucesos y no en la alineación:
    si el original (otra lectura del acta) no la trae, es un goleador y va sin id. Una con dorsal que el
    original no trae se queda en su fila (la regla sin original)."""
    conn = base()
    conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (70, 'VIDAL, IKER', 'VIDAL, IKER', 77),"
                 " (71, 'PAZ, LIA', 'PAZ, LIA', 78), (72, 'RIO, MAR', 'RIO, MAR', 79)")
    partido(conn, 1, 1, 1, 2, "2023-10-04", 5001)
    conn.executemany("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                     "VALUES (?,?,?,?,?,?,?)", [(1, 1, 72, 2, "starter", 0, 0), (1, 1, 70, None, "sub", 1, 1),
                                               (1, 1, 71, 7, "starter", 0, 2)])
    conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES (1, 1, 70, 'goal', 9)")
    conn.commit()
    escribe_raws(tmp_path, {5001: acta([(2, "RIO, MAR", 79)])}, "2023-2024")
    r = M.migrate(conn, str(tmp_path), log=quiet)
    assert de_quien(conn, 1, 1) == {"RIO, MAR": ("RIO, MAR", 79), "VIDAL, IKER": ("VIDAL, IKER@1.1", None),
                                    "PAZ, LIA": ("PAZ, LIA", 78)}
    assert conn.execute("SELECT player_id FROM match_events").fetchone()[0] == pid_de(conn, "VIDAL, IKER@1.1")
    assert r["separar"]["apariciones sin dorsal que el original no trae (goleador: sin id)"] == 1
    assert r["separar"]["apariciones con dorsal que el original no trae (regla sin original)"] == 1


def test_las_uniones_de_club_y_temporada_no_cuentan_las_de_u1(mundo):
    # EVA se une por U1 (dos temporadas del club): 'club', pero no de la U0 de club.
    conn, raws = mundo
    M.migrate(conn, str(raws), log=quiet)
    eva_sin = pid_de(conn, "MORA DIAZ, EVA@3.2")
    assert fila(conn, eva_sin)[7] == "club"
    assert eva_sin not in M.uniones_de_club_y_temporada(conn)


# ── La identidad sin id sigue a sus apariciones (realinear) ─────────────────────────────────────────

def publicado(conn):
    """(claves de las fichas publicadas, partidos publicados en total) de data-jugadores."""
    import generate_js as G
    claves, partidos = set(), 0
    for texto in G.jugadores_files(conn).values():
        datos = json.loads(texto.split(" = ", 1)[1].rstrip(";\n"))
        claves |= set(datos["p"])
        partidos += sum(fila[3] for e in datos["p"].values() for fila in e["c"])
    return claves, partidos


def nuevo(conn, mid, gid, local, visitante, fecha, a=None, jornada=None):
    """Un partido y, si se da, su acta importada con el importador actual."""
    partido(conn, mid, gid, local, visitante, fecha, 8000 + mid if a else None)
    if jornada:
        conn.execute("UPDATE matches SET jornada=? WHERE id=?", (f"Jornada {jornada}", mid))
    if a:
        assert I._import_one(conn, 8000 + mid, a, mid)
    conn.commit()


def gemelos():
    """PG1 de 2025-26 con el mismo equipo entrado dos veces: «Retirado» (10, el bueno: J1-J3) y 'RETIRADO,
    C.D. "A"' (11, el gemelo: J2 y J3 repetidas), con las actas de J2 y J3 importadas bajo el gemelo. SOL
    juega con los dos (J1 en el bueno, J2 en el gemelo); MAR, solo en el gemelo."""
    conn = base()
    conn.execute("""INSERT INTO teams(id, name) VALUES (10, 'Retirado'), (11, 'RETIRADO, C.D. "A"')""")
    nuevo(conn, 21, 2, 10, 1, "2025-10-04", acta([(4, "SOL, ANA", None), (5, "LUZ, EVA", None)]), 1)
    nuevo(conn, 22, 2, 2, 10, "2025-10-11", jornada=2)
    nuevo(conn, 23, 2, 10, 2, "2025-10-18", jornada=3)
    nuevo(conn, 24, 2, 2, 11, "2025-10-11", acta((), [(4, "SOL, ANA", None), (7, "MAR, NOE", None)],
                                                  [("away", "MAR, NOE", "goal")]), 2)
    nuevo(conn, 25, 2, 11, 2, "2025-10-18", acta([(7, "MAR, NOE", None)]), 3)
    M.resolver_fichas(conn, log=quiet)
    return conn


def test_tras_juntar_los_gemelos_las_identidades_siguen_a_sus_apariciones():
    """(a) merge_twin_teams pasa las apariciones y los sucesos al equipo bueno y borra el gemelo sin mirar
    players: tras resolver_fichas, las mismas fichas y los mismos partidos publicados, y las identidades en
    el equipo bueno. MAR (todo en el gemelo) conserva su fila y su clave."""
    import update_fiflp as U
    conn = gemelos()
    antes = publicado(conn)
    mar = conn.execute("SELECT id, clave FROM players WHERE norm_name='MAR, NOE@11.2'").fetchone()
    assert len(antes[0]) == 3 and antes[1] == 5
    assert U.merge_twin_teams(conn, 2, log=quiet) == 1
    assert conn.execute("SELECT 1 FROM teams WHERE id=11").fetchone() is None
    r = M.resolver_fichas(conn, log=quiet)
    assert r["realinear"]["reubicadas"] == 1 and r["realinear"]["movidas"] == 1
    assert publicado(conn) == antes
    assert conn.execute("SELECT id, clave FROM players WHERE norm_name='MAR, NOE@10.2'").fetchone() == mar
    assert {t for (t,) in conn.execute("SELECT DISTINCT p.team_id FROM appearances a JOIN players p ON "
                                       "p.id=a.player_id")} == {10}
    assert {t for (t,) in conn.execute("SELECT DISTINCT p.team_id FROM match_events e JOIN players p ON "
                                       "p.id=e.player_id")} == {10}
    # SOL del gemelo pasa a la SOL del bueno (ya existía): sus dos partidos, en una identidad.
    sol = pid_de(conn, "SOL, ANA@10.2")
    assert conn.execute("SELECT count(*) FROM appearances WHERE player_id=?", (sol,)).fetchone()[0] == 2

    # (b) Dos actas nuevas en el equipo bueno: la misma identidad, la misma ficha, todo publicado.
    nuevo(conn, 26, 2, 10, 1, "2025-10-25", acta([(7, "MAR, NOE", None)]))
    nuevo(conn, 27, 2, 1, 10, "2025-11-01", acta((), [(7, "MAR, NOE", None)]))
    M.resolver_fichas(conn, log=quiet)
    claves, partidos = publicado(conn)
    assert claves == antes[0] and partidos == antes[1] + 2
    assert conn.execute("SELECT count(*) FROM appearances WHERE player_id=?", (mar[0],)).fetchone()[0] == 4


def test_un_movimiento_parcial_deja_dos_identidades_sin_perder_nada():
    """(c) Solo parte de las apariciones de una identidad cambian de equipo (un grupo de los dos que
    jugó): una identidad nueva en el otro equipo con lo movido, con su gol; la vieja, con lo demás."""
    conn = base()
    nuevo(conn, 31, 2, 3, 1, "2025-10-04", acta([(9, "PAZ, LIA", None)], (), [("home", "PAZ, LIA", "goal")]))
    nuevo(conn, 32, 2, 3, 2, "2025-10-11", acta([(9, "PAZ, LIA", None)]))
    M.resolver_fichas(conn, log=quiet)
    lia = pid_de(conn, "PAZ, LIA@3.2")
    antes = M.recuentos(conn)
    conn.execute("UPDATE matches SET home_team_id=4 WHERE id=31")
    for t in ("appearances", "match_events"):
        conn.execute(f"UPDATE {t} SET team_id=4 WHERE match_id=31 AND team_id=3")
    conn.commit()
    r = M.resolver_fichas(conn, log=quiet)["realinear"]
    assert (r["movidas"], r["creadas"], r["reubicadas"], r["choques"]) == (1, 1, 0, 0)
    otra = pid_de(conn, "PAZ, LIA@4.2")
    assert conn.execute("SELECT match_id FROM appearances WHERE player_id=?", (lia,)).fetchall() == [(32,)]
    assert conn.execute("SELECT match_id, goals FROM appearances WHERE player_id=?", (otra,)).fetchall() == [(31, 1)]
    assert conn.execute("SELECT player_id FROM match_events WHERE match_id=31").fetchall() == [(otra,)]
    assert conn.execute("SELECT team_id, season_id, clave FROM players WHERE id=?", (otra,)).fetchone() == (
        4, 2, clave_publica(None, "PAZ, LIA", "Union Cuatro", 2025))
    despues = M.recuentos(conn)
    assert {t: despues[t] for t in M.TABLAS if t != "players"} == {t: antes[t] for t in M.TABLAS if t != "players"}


def test_realinear_dos_veces_la_segunda_no_cambia_nada():
    """(d) Idempotente: con todo en su sitio no escribe nada."""
    import update_fiflp as U
    conn = gemelos()
    U.merge_twin_teams(conn, 2, log=quiet)
    assert M.realinear(conn, log=quiet)["reubicadas"] == 1
    foto = lambda: (conn.execute("SELECT * FROM players ORDER BY id").fetchall(),  # noqa: E731
                    conn.execute("SELECT * FROM appearances ORDER BY 1, 2, 3").fetchall(),
                    conn.execute("SELECT * FROM match_events ORDER BY id").fetchall())
    primera = foto()
    cambios = conn.total_changes
    r = M.realinear(conn, log=quiet)
    assert r == {"movidas": 0, "sucesos": 0, "reubicadas": 0, "creadas": 0, "choques": 0}
    assert foto() == primera and conn.total_changes == cambios


def test_la_aparicion_que_chocaria_se_queda_donde_esta():
    """Si la identidad destino ya está en ese partido y equipo, la aparición que cambiaría se queda (como en
    separar) y se cuenta; no se pierde ninguna."""
    conn = base()
    nuevo(conn, 41, 2, 3, 4, "2025-10-04", acta([(9, "PAZ, LIA", None)], [(5, "PAZ, LIA", None)]))
    lia3, lia4 = pid_de(conn, "PAZ, LIA@3.2"), pid_de(conn, "PAZ, LIA@4.2")
    # Las dos acaban en el equipo 4 del mismo partido (una lectura que juntó los dos lados).
    conn.execute("UPDATE appearances SET team_id=4 WHERE match_id=41 AND player_id=?", (lia3,))
    conn.commit()
    r = M.realinear(conn, log=quiet)
    assert r["choques"] == 1 and r["movidas"] == 0
    assert dict(conn.execute("SELECT player_id, team_id FROM appearances WHERE match_id=41")) == {lia3: 4, lia4: 4}
    assert M.realinear(conn, log=quiet)["choques"] == 1


# ── Dos de la misma alineación no son el mismo niño ─────────────────────────────────────────────

def test_dos_con_id_del_mismo_nombre_en_el_mismo_partido_no_se_unen():
    """El caso real: dos ids del mismo nombre, equipo y temporada que jugaron el MISMO partido. Sin esa
    señal, U0 los unía; un tercer id de un solo uso del mismo nombre va a uno solo (el de más partidos)."""
    conn = base()
    nuevo(conn, 51, 2, 3, 4, "2025-10-04", acta([(4, "SOL, ANA", 501), (9, "SOL, ANA", 502)]))
    nuevo(conn, 52, 2, 3, 1, "2025-10-11", acta([(4, "SOL, ANA", 501)]))
    nuevo(conn, 53, 2, 3, 2, "2025-10-18", acta([(4, "SOL, ANA", 503)]))
    r = M.resolver_fichas(conn, log=quiet)
    assert r["juntas"] == 1
    a, b, c = (conn.execute("SELECT id FROM players WHERE fiflp_id=?", (f,)).fetchone()[0] for f in (501, 502, 503))
    assert fila(conn, a)[6:] == (None, None) and fila(conn, b)[6:] == (None, None)
    assert fila(conn, c)[6:] == (a, "equipo")
    assert M.pares_juntas(conn) == [(a, b)]
    assert M.resolver_fichas(conn, log=quiet)["cambiadas"] == 0


# ── Deshacer una unión a mano: scripts/identidad_separadas.json ─────────────────────────────────

def test_una_identidad_de_identidad_separadas_no_se_une_y_al_quitarla_vuelve(tmp_path):
    conn = base()
    nuevo(conn, 61, 2, 3, 4, "2025-10-04", acta([(4, "SOL, ANA", 501)]))
    nuevo(conn, 62, 2, 3, 1, "2025-10-11", acta([(4, "SOL, ANA", None)]))
    nuevo(conn, 63, 2, 3, 2, "2025-10-18", acta([(4, "SOL, ANA", 503)]))
    ruta = tmp_path / "identidad_separadas.json"
    con, uso = (conn.execute("SELECT id FROM players WHERE fiflp_id=?", (f,)).fetchone()[0] for f in (501, 503))
    sin, clave_sin = conn.execute("SELECT id, clave FROM players WHERE norm_name='SOL, ANA@3.2'").fetchone()
    M.resolver_fichas(conn, log=quiet, separadas=str(ruta))           # sin fichero: nada
    assert fila(conn, sin)[6:] == (con, "equipo") and fila(conn, uso)[6:] == (con, "equipo")
    ruta.write_text(json.dumps([clave_sin, "503"]), encoding="utf-8")
    r = M.resolver_fichas(conn, log=quiet, separadas=str(ruta))
    assert r["separadas"] == 2
    assert fila(conn, sin)[6:] == (None, None) and fila(conn, uso)[6:] == (None, None)
    assert M.resolver_fichas(conn, log=quiet, separadas=str(ruta))["cambiadas"] == 0     # aguanta la pasada
    ruta.write_text("[]", encoding="utf-8")
    M.resolver_fichas(conn, log=quiet, separadas=str(ruta))
    assert fila(conn, sin)[6:] == (con, "equipo") and fila(conn, uso)[6:] == (con, "equipo")


def test_una_clave_desconocida_en_identidad_separadas_se_ignora_con_un_aviso(tmp_path):
    conn = base()
    nuevo(conn, 61, 2, 3, 4, "2025-10-04", acta([(4, "SOL, ANA", 501)]))
    ruta = tmp_path / "identidad_separadas.json"
    ruta.write_text(json.dumps(["n0abc12345", "999999"]), encoding="utf-8")
    lineas = []
    r = M.resolver_fichas(conn, log=lineas.append, separadas=str(ruta))
    assert r["separadas"] == 0
    assert sum("n0abc12345" in x for x in lineas) == 1 and sum("999999" in x for x in lineas) == 1
    ruta.write_text("", encoding="utf-8")                              # vacío: nada
    assert M.resolver_fichas(conn, log=quiet, separadas=str(ruta))["separadas"] == 0


def test_el_fichero_de_separadas_del_repositorio_es_una_lista_de_claves():
    import re
    claves = json.loads((ROOT / "scripts" / "identidad_separadas.json").read_text(encoding="utf-8"))
    assert isinstance(claves, list)
    assert all(isinstance(c, str) and re.fullmatch(r"\d+|n[0-9a-z]{9}", c) for c in claves)
    assert len(claves) == len(set(claves))
