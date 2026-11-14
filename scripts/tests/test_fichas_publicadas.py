"""La web publica una ficha por FICHA (fase 2C, tarea 5): data-jugadores-<k>.js con la clave pública de la
principal, alias en el trozo del alias, la marca de cada fila unida y las otras fichas del mismo nombre; las
alineaciones y los sucesos con la clave de la ficha de cada jugador; la cobertura cuenta fichas.

Sobre una base pequeña montada aquí con ficha_id y union_por ya puestos (lo que dejaría resolver_fichas).
Nombres inventados."""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
import generate_js as G  # noqa: E402
from identidad import clave_publica, trozo  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402
from migrate_identidad import asegurar_esquema  # noqa: E402

quiet = lambda *a, **k: None  # noqa: E731

SEED = """
INSERT INTO seasons(id, name, start_year, end_year) VALUES (1, '2024-2025', 2024, 2025), (2, '2025-2026', 2025, 2026);
INSERT INTO categories(id, name) VALUES (1, 'PREBENJAMIN'), (2, 'BENJAMIN');
INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
  (1, 1, 1, 'PG1', 'Grupo 1', 'Gran Canaria', 'grancanaria'), (2, 2, 2, 'BG1', 'Grupo 1', 'Gran Canaria', 'grancanaria');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Club Tres');
INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score, cod_acta) VALUES
  (1, 1, 'Jornada 1', '05-10-2024', 1, 2, 2, 1, 1001),
  (2, 1, 'Jornada 2', '09-11-2024', 2, 1, 0, 0, 1002),
  (3, 2, 'Jornada 1', '04-10-2025', 1, 3, 3, 1, 1003);
-- 1: con id, la principal. 2: el mismo niño sin id la temporada anterior (U2, 'nombre'). 3: un id de un solo
-- uso en el mismo equipo y temporada (U0, 'equipo'). 4 y 5: dos niños sin id con el mismo nombre en dos
-- equipos (dos fichas). 6: solo marca un gol (sin alineación). 7: el gol sin nombre publicado. 8: con id y sin
-- nada. 9: el segundo «SANCHEZ, PABLO» de una alineación (ordinal 2).
INSERT INTO players(id, full_name, norm_name, fiflp_id, ficha_id, union_por, team_id, season_id, ordinal) VALUES
  (1, 'PEREZ LOPEZ, ANA', 'PEREZ LOPEZ, ANA', 500017, NULL, NULL, NULL, NULL, NULL),
  (2, 'PEREZ LOPEZ, ANA', 'PEREZ LOPEZ, ANA@1.1', NULL, 1, 'nombre', 1, 1, NULL),
  (3, 'PEREZ LOPEZ, ANA', 'PEREZ LOPEZ, ANA#500033', 500033, 1, 'equipo', NULL, NULL, NULL),
  (4, 'RUIZ, LEO', 'RUIZ, LEO@2.1', NULL, NULL, NULL, 2, 1, NULL),
  (5, 'RUIZ, LEO', 'RUIZ, LEO@3.2', NULL, NULL, NULL, 3, 2, NULL),
  (6, 'GOMEZ, LUIS', 'GOMEZ, LUIS@3.2', NULL, NULL, NULL, 3, 2, NULL),
  (7, '', '#SIN NOMBRE PUBLICADO', NULL, NULL, NULL, NULL, NULL, NULL),
  (8, 'DIAZ, SOFIA', 'DIAZ, SOFIA', 500050, NULL, NULL, NULL, NULL, NULL),
  (9, 'SANCHEZ, PABLO', 'SANCHEZ, PABLO@2.1#2', NULL, NULL, NULL, 2, 1, 2);
INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, yellow, red, ord) VALUES
  (1, 1, 2, 7, 'starter', 2, 0, 0, 0), (1, 2, 4, 9, 'starter', 1, 1, 0, 1), (1, 2, 9, 10, 'sub', 0, 0, 0, 2),
  (2, 1, 2, 7, 'starter', 0, 0, 0, 0), (2, 2, 4, 9, 'sub', 0, 0, 0, 1),
  (3, 1, 1, 7, 'starter', 2, 0, 0, 0), (3, 1, 3, 14, 'sub', 1, 0, 0, 1), (3, 3, 5, 4, 'starter', 0, 1, 0, 2);
INSERT INTO match_events(id, match_id, team_id, player_id, kind, minute, goal_type, pair_id) VALUES
  (1, 3, 1, 1, 'goal', 5, 'normal', NULL), (2, 3, 1, 1, 'sub_out', 30, NULL, 3), (3, 3, 1, 3, 'sub_in', 30, NULL, 2),
  (4, 3, 3, 6, 'goal', 33, 'normal', NULL), (5, 3, 1, 7, 'goal', 40, 'normal', NULL),
  (6, 3, 3, 5, 'yellow', 41, NULL, NULL), (7, 3, 1, 3, 'goal', 44, 'penalty', NULL), (8, 3, 1, 1, 'goal', 50, 'normal', NULL);
"""

ANA = "500017"
ANA_SIN_ID = clave_publica(None, "PEREZ LOPEZ, ANA", "Atletico Uno", 2024)
ANA_UN_USO = "500033"
LEO_DOS = clave_publica(None, "RUIZ, LEO", "Deportivo Dos", 2024)
LEO_TRES = clave_publica(None, "RUIZ, LEO", "Club Tres", 2025)
PABLO = clave_publica(None, "SANCHEZ, PABLO#2", "Deportivo Dos", 2024)
LUIS = clave_publica(None, "GOMEZ, LUIS", "Club Tres", 2025)


def base():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    asegurar_esquema(conn)
    conn.executescript(SEED)
    conn.commit()
    return conn


def trozos(files):
    out = {}
    for name, text in files.items():
        k = int(re.fullmatch(r"data-jugadores-(\d+)\.js", name).group(1))
        m = re.fullmatch(rf"const JUGADORES_{k} = (\{{.*\}});\n", text, re.S)
        out[k] = json.loads(m.group(1))
    return out


def ficha(shards, clave):
    return shards[trozo(clave)]["p"].get(clave)


def test_una_entrada_por_ficha_en_el_trozo_de_su_clave_con_todas_sus_apariciones():
    shards = trozos(G.jugadores_files(base()))
    assert sorted(shards) == list(range(16))
    claves = sorted(k for s in shards.values() for k in s["p"])
    assert claves == sorted([ANA, LEO_DOS, LEO_TRES, PABLO])
    for clave in claves:
        assert clave in shards[trozo(clave)]["p"]
    # Ana: su fila con id (u = 0, 8 valores) y las unidas, cada una con u = 1 y el motivo; las del mismo grupo y
    # equipo no se suman. En orden de temporada.
    ana = ficha(shards, ANA)
    assert ana["n"] == "PEREZ LOPEZ, ANA"
    assert ana["c"] == [
        ["2024-2025", "PG1", "Atletico Uno", 2, 2, 2, 0, 0, 1, "n"],
        ["2025-2026", "BG1", "Atletico Uno", 1, 1, 2, 0, 0],
        ["2025-2026", "BG1", "Atletico Uno", 1, 0, 1, 0, 0, 1, "e"],
    ]
    assert "s" not in ana and "h" not in ana
    assert sorted(ana["al"]) == sorted([ANA_SIN_ID, ANA_UN_USO])
    # Los grupos de sus filas, en el trozo de la ficha.
    assert shards[trozo(ANA)]["g"]["2024-2025/PG1"] == ["prebenjamin", "Grupo 1", "Gran Canaria", "grancanaria"]
    assert shards[trozo(ANA)]["g"]["2025-2026/BG1"] == ["benjamin", "Grupo 1", "Gran Canaria", "grancanaria"]


def test_cada_alias_en_el_trozo_del_alias_y_ninguna_clave_se_repite():
    shards = trozos(G.jugadores_files(base()))
    alias = {a: c for s in shards.values() for a, c in s["a"].items()}
    assert alias == {ANA_SIN_ID: ANA, ANA_UN_USO: ANA}
    assert shards[trozo(ANA_SIN_ID)]["a"][ANA_SIN_ID] == ANA
    assert shards[trozo(ANA_UN_USO)]["a"][ANA_UN_USO] == ANA
    fichas = [k for s in shards.values() for k in s["p"]]
    assert len(fichas) == len(set(fichas)) and not set(fichas) & set(alias)


def test_sin_ningun_id_s_1_y_las_otras_fichas_del_mismo_nombre_con_su_ultimo_equipo():
    shards = trozos(G.jugadores_files(base()))
    dos, tres = ficha(shards, LEO_DOS), ficha(shards, LEO_TRES)
    assert dos["s"] == 1 and tres["s"] == 1
    assert dos["c"] == [["2024-2025", "PG1", "Deportivo Dos", 2, 1, 1, 1, 0]]
    assert dos["h"] == [[LEO_TRES, "Club Tres", "2025-2026"]]
    assert tres["h"] == [[LEO_DOS, "Deportivo Dos", "2024-2025"]]
    assert "al" not in dos
    # El ordinal es parte de su clave; un nombre sin homónimos no lleva «h».
    pablo = ficha(shards, PABLO)
    assert pablo == {"n": "SANCHEZ, PABLO", "c": [["2024-2025", "PG1", "Deportivo Dos", 1, 0, 0, 0, 0]], "s": 1}


def publicado(conn):
    """(claves de las fichas, alias, partidos publicados en total) de data-jugadores."""
    shards = trozos(G.jugadores_files(conn))
    fichas = {k: e for s in shards.values() for k, e in s["p"].items()}
    alias = {a: c for s in shards.values() for a, c in s["a"].items()}
    return set(fichas), alias, sum(fila[3] for e in fichas.values() for fila in e["c"])


def test_renombrar_un_equipo_no_cambia_ninguna_clave_publicada():
    """La clave de una identidad sin id se guarda al crearla (players.clave): activate_season.club_id
    renombra filas de teams y, si se calculara al publicar, los enlaces y los seguidos se romperían."""
    conn = base()
    asegurar_esquema(conn)          # las del SEED, sin clave guardada: se la pone con los nombres de hoy
    antes = publicado(conn)
    assert LEO_DOS in antes[0] and antes[1][ANA_SIN_ID] == ANA
    conn.execute("UPDATE teams SET name='Deportivo Dos Renombrado' WHERE id=2")
    conn.execute("UPDATE teams SET name='Atletico Uno Renombrado' WHERE id=1")
    conn.commit()
    assert publicado(conn) == antes


def test_una_fila_de_teams_borrada_no_deja_ninguna_ficha_sin_publicar():
    """Cinturón y tirantes de realinear: una identidad sin id que apunta a un equipo que ya no existe (sus
    apariciones, en otro) se sigue publicando. Con la clave guardada, igual que antes de borrarlo; sin ella,
    con el equipo y la temporada de sus apariciones (las mismas fichas y los mismos partidos)."""
    for guardar in (True, False):
        conn = base()
        conn.execute("INSERT INTO teams(id, name) VALUES (9, 'Club Tres Viejo')")
        conn.execute("UPDATE players SET team_id=9, norm_name='RUIZ, LEO@9.2' WHERE id=5")
        conn.commit()
        if guardar:
            asegurar_esquema(conn)
        antes = publicado(conn)
        conn.execute("DELETE FROM teams WHERE id=9")
        conn.commit()
        despues = publicado(conn)
        if guardar:
            assert despues == antes
        else:
            assert len(despues[0]) == len(antes[0]) and despues[2] == antes[2]
            assert LEO_TRES in despues[0]          # la de su equipo de verdad, «Club Tres»


def test_una_principal_sin_clave_publica_su_ficha_con_la_de_otra_identidad_suya():
    """Si ni con sus apariciones se le puede calcular la clave (la principal sin id, de un equipo que ya no
    existe y sin apariciones), la ficha sale con la clave de otra identidad suya, que no se repite como alias."""
    conn = base()
    conn.execute("INSERT INTO players(id, full_name, norm_name, team_id, season_id) VALUES "
                 "(20, 'MOYA, IRIS', 'MOYA, IRIS@99.1', 99, 1), (21, 'MOYA, IRIS', 'MOYA, IRIS@3.2', 3, 2)")
    conn.execute("UPDATE players SET ficha_id=20, union_por='club' WHERE id=21")
    conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) VALUES (3, 3, 21, 8, 'sub', 9)")
    conn.commit()
    shards = trozos(G.jugadores_files(conn))
    iris = clave_publica(None, "MOYA, IRIS", "Club Tres", 2025)
    entrada = ficha(shards, iris)
    assert entrada["c"] == [["2025-2026", "BG1", "Club Tres", 1, 0, 0, 0, 0, 1, "c"]]
    assert "al" not in entrada and iris not in shards[trozo(iris)]["a"]
    assert G.claves_de_ficha(conn)[21] == iris


def test_sin_aparicion_no_hay_ficha_ni_el_gol_sin_nombre_tiene_clave():
    shards = trozos(G.jugadores_files(base()))
    todas = {k for s in shards.values() for k in [*s["p"], *s["a"]]}
    assert LUIS not in todas and "500050" not in todas
    assert not any("SIN NOMBRE" in json.dumps(s) for s in shards.values())


def test_las_alineaciones_y_los_sucesos_llevan_la_clave_de_la_ficha():
    entries = dict(G.lineups_entries(base(), "2024-2025"))
    e = entries["Atletico Uno|Deportivo Dos|2-1"]
    assert [(p["n"], p.get("id")) for p in e["home"]] == [("PEREZ LOPEZ, ANA", 500017)]
    assert [(p["n"], p.get("id")) for p in e["away"]] == [("SANCHEZ, PABLO", PABLO), ("RUIZ, LEO", LEO_DOS)]
    e = dict(G.lineups_entries(base(), "2025-2026"))["Atletico Uno|Club Tres|3-1"]
    assert [(p["n"], p.get("id")) for p in e["home"]] == [("PEREZ LOPEZ, ANA", 500017), ("PEREZ LOPEZ, ANA", 500017)]
    assert [p["id"] for p in e["away"]] == [LEO_TRES]
    assert e["events"] == [
        {"t": "goal", "s": "h", "n": "PEREZ LOPEZ, ANA", "m": 5, "gt": "normal", "id": 500017},
        {"t": "sub", "s": "h", "m": 30, "n": "PEREZ LOPEZ, ANA", "n2": "PEREZ LOPEZ, ANA", "id": 500017, "id2": 500017},
        # Solo marca (sin ficha: no está en ninguna alineación) y el gol sin nombre: sin clave.
        {"t": "goal", "s": "a", "n": "GOMEZ, LUIS", "m": 33, "gt": "normal"},
        {"t": "goal", "s": "h", "n": "", "m": 40, "gt": "normal"},
        {"t": "yellow", "s": "a", "n": "RUIZ, LEO", "m": 41, "id": LEO_TRES},
        {"t": "goal", "s": "h", "n": "PEREZ LOPEZ, ANA", "m": 44, "gt": "penalty", "id": 500017},
        {"t": "goal", "s": "h", "n": "PEREZ LOPEZ, ANA", "m": 50, "gt": "normal", "id": 500017},
    ]


def test_los_ficheros_de_alineaciones_dan_lo_mismo_que_lineups_entries():
    conn = base()
    files = G.lineups_files(conn)
    text = files["data-lineups-2025-2026-BG1.js"]
    obj = json.loads(re.search(r"= (\{.*\});\n$", text, re.S).group(1))
    assert obj == G._keyed_or_dup(G.lineups_entries(conn, "2025-2026", "BG1"))


def test_la_cobertura_cuenta_fichas_con_alineacion():
    # 2024-25: Ana (por su identidad sin id), Leo de Deportivo Dos y Pablo; 2025-26: Ana (dos identidades) y Leo
    # de Club Tres.
    temporadas = {t[0]: t[5] for t in G.coverage_summary(base())["temporadas"]}
    assert temporadas == {"2024-2025": 3, "2025-2026": 2}


def test_una_base_sin_las_columnas_de_la_ficha_publica_como_antes():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    seed = SEED.replace(", ficha_id, union_por, team_id, season_id, ordinal", "")
    seed = re.sub(r"(\(\d+, '[^']*', '[^']*', (?:\d+|NULL)), [^)]*\)", r"\1)", seed)
    conn.executescript(seed)
    shards = trozos(G.jugadores_files(conn))
    claves = sorted(k for s in shards.values() for k in s["p"])
    assert claves == ["500017", "500033"]
    assert ficha(shards, ANA)["c"] == [["2025-2026", "BG1", "Atletico Uno", 1, 1, 2, 0, 0]]
    assert all(s["a"] == {} for s in shards.values())
    e = dict(G.lineups_entries(conn, "2025-2026"))["Atletico Uno|Club Tres|3-1"]
    assert [p.get("id") for p in e["home"]] == [500033, 500017]     # el suplente primero, como siempre
    assert "id" not in e["away"][0]
