"""El importador de actas y el bot con las identidades de acta de la fase 2C (docs/identidad.md).

Con id de la federación, la fila de ese id (nunca la de otro niño con el mismo nombre); sin id, la del
nombre en ese equipo y esa temporada. Cada pasada del bot recalcula las fichas después de importar y
podar, y antes de publicar. Nombres inventados."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
import import_fiflp_actas as I  # noqa: E402
import migrate_identidad as M  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402

quiet = lambda *a, **k: None  # noqa: E731

SEED = """
INSERT INTO seasons(id, name, start_year, end_year) VALUES (1, '2025-2026', 2025, 2026), (2, '2026-2027', 2026, 2027);
INSERT INTO categories(id, name) VALUES (1, 'PREBENJAMIN'), (2, 'BENJAMIN');
INSERT INTO groups(id, season_id, category_id, code, name, island) VALUES
  (1, 1, 1, 'PG1', 'Grupo 1', 'grancanaria'), (2, 2, 2, 'BGC1', 'Grupo 1', 'grancanaria'),
  (3, 2, 1, 'PG2', 'Grupo 2', 'grancanaria');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Inventado'), (2, 'Union Ficticia'), (3, 'Club Imaginario');
INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score) VALUES
  (1, 1, 'Jornada 1', '2025-10-04', 1, 2, 2, 1),
  (2, 1, 'Jornada 2', '2025-10-11', 1, 3, 1, 0),
  (3, 2, 'Jornada 1', '2026-10-03', 1, 2, 1, 1),
  (4, 3, 'Jornada 1', '2026-10-10', 3, 2, 0, 0);
"""


def base():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    conn.executescript(SEED)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def acta(local=(), visitante=(), sucesos=()):
    """local/visitante: [(dorsal, nombre, fiflp_id o None)]; sucesos: [(lado, nombre, tipo)]."""
    def lado(js):
        return [{"dorsal": d, "name": n, "role": "starter" if d is not None else "sub", "fiflp_id": f}
                for d, n, f in js]
    return {"header": {}, "lineups": {"home": lado(local), "away": lado(visitante)},
            "events": [{"kind": k, "side": s, "player_name": n, "minute": 10 + i, "goal_type": "normal"}
                       for i, (s, n, k) in enumerate(sucesos)]}


def importa(conn, mid, a):
    assert I._import_one(conn, 7000 + mid, a, mid)
    conn.commit()


def fila(conn, pid):
    return conn.execute("SELECT norm_name, fiflp_id, team_id, season_id, ordinal FROM players WHERE id=?",
                        (pid,)).fetchone()


def de_partido(conn, mid, tid):
    """[(dorsal, norm_name, fiflp_id, goles)] de las apariciones de un equipo en un partido, por dorsal."""
    return conn.execute(
        "SELECT a.dorsal, p.norm_name, p.fiflp_id, a.goals FROM appearances a JOIN players p ON p.id=a.player_id "
        "WHERE a.match_id=? AND a.team_id=? ORDER BY a.dorsal IS NULL, a.dorsal, a.ord", (mid, tid)).fetchall()


# ── _get_or_create_player ────────────────────────────────────────────────

def test_con_id_es_la_fila_de_ese_id_y_nunca_adopta_ni_devuelve_la_de_otro():
    conn = base()
    vieja = conn.execute("INSERT INTO players(full_name, norm_name) VALUES ('PEREZ, ANA', 'PEREZ, ANA')").lastrowid
    ana = I._get_or_create_player(conn, "PEREZ, ANA", 777)
    assert ana != vieja                                  # se acabó «adoptar» la fila sin id
    assert fila(conn, vieja) == ("PEREZ, ANA", None, None, None, None)
    assert fila(conn, ana) == ("PEREZ, ANA#777", 777, None, None, None)
    assert I._get_or_create_player(conn, "PÉREZ, ana", 777) == ana      # otra grafía, el mismo id
    assert I._get_or_create_player(conn, "OTRO NOMBRE, X", 777) == ana   # manda el id, no el nombre
    otra = I._get_or_create_player(conn, "PEREZ, ANA", 888)
    assert otra not in (ana, vieja) and fila(conn, otra)[:2] == ("PEREZ, ANA#888", 888)
    # Con id, el equipo y la temporada no cuentan: es la misma fila en cualquier equipo y año.
    assert I._get_or_create_player(conn, "PEREZ, ANA", 888, 1, 1) == otra


def test_sin_id_es_la_fila_de_su_nombre_equipo_y_temporada():
    conn = base()
    con_id = I._get_or_create_player(conn, "GARCIA, LUCIA", 900)
    vieja = conn.execute("INSERT INTO players(full_name, norm_name) VALUES ('GARCIA LOPEZ, LUCIA', "
                         "'GARCIA LOPEZ, LUCIA')").lastrowid
    a = I._get_or_create_player(conn, "GARCIA, LUCIA", None, 1, 1)
    assert a != con_id
    assert fila(conn, a) == ("GARCIA, LUCIA@1.1", None, 1, 1, None)
    assert I._get_or_create_player(conn, "GARCÍA,  lucia", None, 1, 1) == a
    assert I._get_or_create_player(conn, "GARCIA, LUCIA", None, 2, 1) not in (a, con_id)     # otro equipo
    assert I._get_or_create_player(conn, "GARCIA, LUCIA", None, 1, 2) not in (a, con_id)     # otra temporada
    segunda = I._get_or_create_player(conn, "GARCIA, LUCIA", None, 1, 1, 2)
    assert fila(conn, segunda) == ("GARCIA, LUCIA@1.1#2", None, 1, 1, 2)
    assert I._get_or_create_player(conn, "GARCIA LOPEZ, LUCIA", None, 1, 1) != vieja        # ni la fila vieja


def test_sin_id_y_sin_equipo_o_temporada_es_un_error_claro():
    conn = base()
    for equipo, temporada in ((None, None), (1, None), (None, 1)):
        with pytest.raises(ValueError, match="equipo y temporada"):
            I._get_or_create_player(conn, "LUCAS", None, equipo, temporada)
    assert conn.execute("SELECT count(*) FROM players").fetchone()[0] == 0


def test_la_base_de_las_actas_trae_las_columnas_de_las_identidades():
    cols = {r[1] for r in base().execute("PRAGMA table_info(players)")}
    assert {"ficha_id", "union_por", "team_id", "season_id", "ordinal"} <= cols


# ── _import_one ──────────────────────────────────────────────────────────

def test_dos_homonimos_sin_id_en_la_misma_alineacion_no_se_pierde_ninguno():
    """Review Focus 3. Antes las tres apariciones iban a la misma fila y la segunda reventaba la clave
    primaria de appearances (sqlite3.IntegrityError: el acta no se importaba). Ahora, el dorsal más bajo
    es la identidad normal, y los siguientes llevan ordinal (sin dorsal, detrás)."""
    conn = base()
    a = acta([(9, "SUAREZ, DANIEL", None), (None, "suarez, daniel", None), (4, "SUÁREZ, DANIEL", None),
              (7, "SUAREZ, DANIEL", 4321)],
             [(9, "SUAREZ, DANIEL", None)])
    importa(conn, 1, a)
    assert de_partido(conn, 1, 1) == [(4, "SUAREZ, DANIEL@1.1", None, 0), (7, "SUAREZ, DANIEL", 4321, 0),
                                      (9, "SUAREZ, DANIEL@1.1#2", None, 0), (None, "SUAREZ, DANIEL@1.1#3", None, 0)]
    assert de_partido(conn, 1, 2) == [(9, "SUAREZ, DANIEL@2.1", None, 0)]   # otro equipo, otra identidad
    assert conn.execute("SELECT count(*) FROM appearances").fetchone()[0] == 5
    # El que no tiene ordinal lo guarda vacío, como la migración; los demás, su número.
    assert conn.execute("SELECT norm_name, ordinal FROM players WHERE team_id=1 ORDER BY id").fetchall() == [
        ("SUAREZ, DANIEL@1.1#2", 2), ("SUAREZ, DANIEL@1.1#3", 3), ("SUAREZ, DANIEL@1.1", None)]


def test_el_goleador_que_no_esta_en_la_alineacion_es_de_su_equipo_y_temporada():
    """Trampa 11 del mapa: antes se buscaba sin id por el nombre en toda la base (se pegaba al niño con id
    de otro equipo). Ahora: si en la alineación de su lado hay uno con el mismo nombre normalizado, es él;
    si no, la identidad sin id de su equipo y temporada."""
    conn = base()
    importa(conn, 2, acta([(3, "MARTIN, HUGO", None)], [(5, "MARTIN RUIZ, HUGO", 5000)]))
    otro = I._get_or_create_player(conn, "MARTIN RUIZ, HUGO", 5000)
    importa(conn, 1, acta([(7, "LÓPEZ, IKER", 6000), (8, "VEGA, LEO", None)], [(1, "SOSA, MIA", None)],
                          [("home", "LOPEZ, IKER", "goal"),         # solo cambian tildes: el de la alineación
                           ("home", "vega, leo", "goal"),           # solo cambian mayúsculas: el de la alineación
                           ("home", "MARTIN RUIZ, HUGO", "goal"),   # no está: sin id de su equipo y temporada
                           ("home", "MARTIN, HUGO", "goal")]))      # no está aquí, sí en otro partido del equipo
    assert de_partido(conn, 1, 1) == [(7, "LOPEZ, IKER", 6000, 1), (8, "VEGA, LEO@1.1", None, 1),
                                      (None, "MARTIN RUIZ, HUGO@1.1", None, 1), (None, "MARTIN, HUGO@1.1", None, 1)]
    assert conn.execute("SELECT count(*) FROM appearances WHERE player_id=?", (otro,)).fetchone()[0] == 1
    # El que solo sale en los sucesos es la misma identidad que la del mismo nombre en otro partido del equipo.
    hugo = conn.execute("SELECT id FROM players WHERE norm_name='MARTIN, HUGO@1.1'").fetchone()[0]
    assert conn.execute("SELECT count(*) FROM appearances WHERE player_id=?", (hugo,)).fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM match_events WHERE match_id=1").fetchone()[0] == 4


def test_un_suceso_de_un_nombre_con_homonimos_en_la_alineacion_no_crea_a_nadie():
    """Decisión: con dos de la alineación con ese nombre (salvo tildes o mayúsculas) no se sabe cuál fue;
    va al último de ellos, como cuando el nombre es exactamente igual (lo de siempre), sin aparición nueva."""
    conn = base()
    importa(conn, 1, acta([(4, "SOSA, PAU", None), (6, "SOSA, PAU", 61)], [], [("home", "SOSÁ, PAU", "goal")]))
    assert de_partido(conn, 1, 1) == [(4, "SOSA, PAU@1.1", None, 0), (6, "SOSA, PAU", 61, 1)]
    assert conn.execute("SELECT count(*) FROM players").fetchone()[0] == 2


def foto(conn):
    return (conn.execute("SELECT * FROM players ORDER BY id").fetchall(),
            conn.execute("SELECT match_id, team_id, player_id, dorsal, goals FROM appearances ORDER BY 1, 2, 3").fetchall(),
            conn.execute("SELECT match_id, team_id, player_id, kind, minute FROM match_events ORDER BY 1, 2, 3, 4, 5").fetchall())


ACTAS = {
    1: acta([(4, "SUAREZ, DANIEL", None), (9, "SUAREZ, DANIEL", None), (10, "ROMERO DIAZ, NOA", None)],
            [(2, "LUCAS", None)], [("home", "SUAREZ, DANIEL", "goal"), ("home", "BRITO, ALMA", "goal")]),
    2: acta([(10, "ROMERO DIAZ, NOA", None), (3, "LUCAS", None)], [(5, "LUCAS", None)]),
    3: acta([(10, "ROMERO DIAZ, NOA", 81), (3, "LUCAS", 82)], [(2, "LUCAS", None)],
            [("away", "BRITO, ALMA", "yellow")]),
    4: acta([(5, "LUCAS", None)], [(1, "GIL VERA, TEO", None)]),
}


def pasada(conn):
    """Lo que hace el bot con las actas: importar, podar y resolver las fichas."""
    for mid, a in ACTAS.items():
        importa(conn, mid, a)
    I.prune_players(conn, log=quiet)
    M.resolver_fichas(conn, log=quiet)


def test_reimportar_las_actas_deja_las_mismas_identidades_y_las_mismas_fichas():
    """Review Focus 1, de punta a punta, dos veces seguidas: _import_one borra y reescribe."""
    conn = base()
    pasada(conn)
    primera = foto(conn)
    # Hay uniones de verdad (si no, la prueba no prueba nada): NOA sin id en 2025-26 y con id en 2026-27.
    noa = conn.execute("SELECT id FROM players WHERE fiflp_id=81").fetchone()[0]
    assert conn.execute("SELECT union_por FROM players WHERE ficha_id=?", (noa,)).fetchall() == [("nombre",)]
    assert conn.execute("SELECT count(*) FROM players WHERE ficha_id IS NOT NULL").fetchone()[0] >= 2
    for _ in range(2):
        for mid, a in ACTAS.items():
            importa(conn, mid, a)
        # Reimportar no deja ninguna fila nueva ni ninguna sin uso.
        assert foto(conn)[0] == primera[0]
        assert I.prune_players(conn, log=quiet) == 0
        assert M.resolver_fichas(conn, log=quiet)["cambiadas"] == 0
        assert foto(conn) == primera


def test_reimportar_un_acta_ya_migrada_no_crea_identidades_nuevas(tmp_path):
    """Lo que dejó la migración (dos DANIEL por dorsal, un goleador sin id) es lo mismo que crea el
    importador: releer el acta no deja huérfanas."""
    conn = base()
    M.asegurar_esquema(conn)
    conn.executemany("INSERT INTO players(id, full_name, norm_name, team_id, season_id, ordinal) VALUES (?,?,?,?,?,?)",
                     [(50, "SUAREZ, DANIEL", "SUAREZ, DANIEL@1.1", 1, 1, None),
                      (51, "SUAREZ, DANIEL", "SUAREZ, DANIEL@1.1#2", 1, 1, 2),
                      (52, "BRITO, ALMA", "BRITO, ALMA@1.1", 1, 1, None)])
    conn.commit()
    importa(conn, 1, ACTAS[1])
    assert conn.execute("SELECT count(*) FROM players WHERE team_id=1").fetchone()[0] == 4    # + ROMERO DIAZ, NOA
    assert dict(conn.execute("SELECT dorsal, player_id FROM appearances WHERE match_id=1 AND team_id=1 AND "
                             "player_id IN (50, 51, 52)")) == {4: 50, 9: 51, None: 52}


# ── prune_players ────────────────────────────────────────────────────────

def test_prune_no_borra_una_fila_a_la_que_apunta_otra():
    """Review Focus 5: ninguna ficha_id apunta a una fila que no existe."""
    conn = base()
    pasada(conn)
    noa = conn.execute("SELECT id FROM players WHERE fiflp_id=81").fetchone()[0]
    # El acta del partido 3 se rehace sin NOA: la principal de su ficha se queda sin apariciones.
    importa(conn, 3, acta([(3, "LUCAS", 82)], [(2, "LUCAS", None)], [("away", "BRITO, ALMA", "yellow")]))
    vacia = conn.execute("INSERT INTO players(full_name, norm_name) VALUES ('VIEJA, FILA', 'VIEJA, FILA')").lastrowid
    assert I.prune_players(conn, log=quiet) == 1                       # la vacía sí, la principal no
    assert conn.execute("SELECT 1 FROM players WHERE id=?", (vacia,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM players WHERE id=?", (noa,)).fetchone() is not None
    huerfanas = ("SELECT count(*) FROM players p WHERE p.ficha_id IS NOT NULL AND NOT EXISTS "
                 "(SELECT 1 FROM players q WHERE q.id = p.ficha_id)")
    assert conn.execute(huerfanas).fetchone()[0] == 0
    # La pasada siguiente: resolver la deja suelta y entonces sí se poda.
    M.resolver_fichas(conn, log=quiet)
    assert conn.execute("SELECT count(*) FROM players WHERE ficha_id=?", (noa,)).fetchone()[0] == 0
    assert I.prune_players(conn, log=quiet) == 1
    assert conn.execute(huerfanas).fetchone()[0] == 0


# ── La pasada del bot ────────────────────────────────────────────────────

@pytest.fixture
def bot(tmp_path, monkeypatch):
    """fetch_futbolaspalmas.main con todo de mentira; apunta en `pasos` el orden de lo que llama."""
    import fetch_futbolaspalmas as FB
    import generate_js
    import migrate_categories
    import migrate_compactar
    import migrate_team_names
    import source_health
    import update_fiflp

    pasos = []

    class Conn:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass
    for module in (migrate_categories, migrate_compactar, migrate_team_names):
        monkeypatch.setattr(module, "migrate", lambda conn: None)
    monkeypatch.setattr(M, "asegurar_esquema", lambda conn: pasos.append("esquema"))
    monkeypatch.setattr(M, "resolver_fichas", lambda conn: pasos.append("fichas"))
    monkeypatch.setattr(FB, "get_connection", Conn)
    monkeypatch.setattr(FB, "init_db", lambda conn: None)
    monkeypatch.setattr(FB, "active_season", lambda conn: (1, "2026-2027"))
    monkeypatch.setattr(FB, "FILES", [])
    monkeypatch.setattr(FB, "update_fp_app", lambda conn, name: pasos.append("app"))
    monkeypatch.setattr(FB, "import_past_seasons", lambda conn: pasos.append("pasadas y poda"))
    monkeypatch.setenv("FIFLP_UPDATE", "1")
    monkeypatch.setattr(update_fiflp, "update_groups", lambda conn, season_id: pasos.append("federación"))
    monkeypatch.setattr(generate_js, "main", lambda: pasos.append("publicar"))
    monkeypatch.setattr(source_health, "begin", lambda season: None)
    terminadas = []
    monkeypatch.setattr(source_health, "finish", lambda now=None, failed=False: terminadas.append(failed))
    return FB, pasos, terminadas, monkeypatch


def test_la_pasada_resuelve_las_fichas_tras_importar_y_podar_y_antes_de_publicar(bot):
    FB, pasos, terminadas, _ = bot
    FB.main()
    assert pasos == ["esquema", "federación", "app", "pasadas y poda", "fichas", "publicar"]
    assert terminadas == [False]


def test_un_fallo_al_resolver_las_fichas_para_la_pasada_sin_publicar(bot):
    FB, pasos, terminadas, monkeypatch = bot

    def roto(conn):
        raise RuntimeError("resolver_fichas roto")
    monkeypatch.setattr(M, "resolver_fichas", roto)
    with pytest.raises(RuntimeError, match="resolver_fichas roto"):
        FB.main()
    assert "publicar" not in pasos and terminadas == [True]


def test_la_poda_es_lo_ultimo_de_las_temporadas_pasadas():
    """resolver_fichas va después de import_past_seasons porque la poda es su último paso."""
    text = (ROOT / "scripts" / "fetch_futbolaspalmas.py").read_text(encoding="utf-8")
    cuerpo = text[text.index("def import_past_seasons"):text.index("def main():")]
    pasos = cuerpo[cuerpo.index("steps = ["):cuerpo.index("migrate(conn)")]
    assert pasos.rstrip().rstrip("]").rstrip().endswith("prune_players)")
