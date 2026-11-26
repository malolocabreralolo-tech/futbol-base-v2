"""La base que ve la web (scripts/vista_web.py): el generador trabaja sobre una copia sin las categorías que la
web aún no enseña (categorias.EN_WEB), y con la base de después de activar infantil, cadete y juvenil publica
exactamente lo mismo que con la de antes.

Las dos primeras, con una base sintética (nombres inventados); la tercera, con dos copias de la base real (salta
sin futbolbase.db) y la base de después de base_mayores.poblar."""
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402

DB_PATH = ROOT / "futbolbase.db"
quiet = lambda *a, **k: None  # noqa: E731


def base(con_infantil=True):
    """Benjamín (FF1) e infantil (INFPG1) de 2026-27. Equipos: 1 y 2 juegan en los dos; 3, solo en infantil. Un
    partido por grupo con su acta (dos apariciones y un gol), su clasificación, sus goleadores y la ficha de la
    temporada de los equipos 1 y 3. El jugador 10 juega en los dos (el mismo id de la federación); el 11, solo en
    infantil."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    from import_fiflp_detalle import migrate as detalle
    detalle(conn)
    conn.executescript("""
      INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2026-2027', 2026, 2027, 1);
      INSERT INTO categories(id, name) VALUES (1, 'BENJAMIN'), (2, 'PREBENJAMIN'), (4, 'ALEVIN'), (5, 'INFANTIL');
      INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Club Tres');
      INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
        (1, 1, 1, 'FF1', 'Grupo 1', 'Primera Fase GC', 'grancanaria');
      INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES
        (10, 'GOMEZ PEREZ, RAUL', 'GOMEZ PEREZ, RAUL', 9001), (11, 'SOTO VEGA, IKER', 'SOTO VEGA, IKER', 9002);
      INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score, cod_acta)
        VALUES (100, 1, 'Jornada 1', '2026-10-03', 1, 2, 1, 0, 5001);
      INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) VALUES (100, 1, 10, 7, 'starter', 1, 0);
      INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES (100, 1, 10, 'goal', 10);
      INSERT INTO standings(group_id, team_id, position, points, played, won, drawn, lost, gf, gc, gd) VALUES
        (1, 1, 1, 3, 1, 1, 0, 0, 1, 0, 1), (1, 2, 2, 0, 1, 0, 0, 1, 0, 1, -1);
      INSERT INTO scorers(group_id, player_name, team_id, goals, games) VALUES (1, 'GOMEZ PEREZ, RAUL', 1, 1, 1);
      INSERT INTO team_seasons(team_id, season_id, fiflp_name, shirt) VALUES (1, 1, 'UNO, ATLETICO', 'Roja');
    """)
    if con_infantil:
        conn.executescript("""
          INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
            (2, 1, 5, 'INFPG1', 'Grupo 1', 'Preferente GC', 'grancanaria');
          INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score, cod_acta)
            VALUES (200, 2, 'Jornada 1', '2026-10-04', 3, 1, 2, 1, 5002);
          INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) VALUES
            (200, 1, 10, 7, 'starter', 1, 0), (200, 3, 11, 9, 'starter', 2, 1);
          INSERT INTO match_events(match_id, team_id, player_id, kind, minute) VALUES
            (200, 3, 11, 'goal', 5), (200, 3, 11, 'goal', 30), (200, 1, 10, 'goal', 50);
          INSERT INTO match_staff_all(match_id, team_id, role, name, ord) VALUES (200, 3, 'Entrenador', 'X', 0);
          INSERT INTO goals(match_id, minute, player_name, running_score, side, type) VALUES (200, 5, 'SOTO VEGA, IKER', '1-0', 'h', 'r');
          INSERT INTO standings(group_id, team_id, position, points, played, won, drawn, lost, gf, gc, gd) VALUES
            (2, 3, 1, 3, 1, 1, 0, 0, 2, 1, 1), (2, 1, 2, 0, 1, 0, 0, 1, 1, 2, -1);
          INSERT INTO standings_detail(group_id, team_id) VALUES (2, 3);
          INSERT INTO scorers(group_id, player_name, team_id, goals, games) VALUES (2, 'SOTO VEGA, IKER', 3, 2, 1);
          INSERT INTO team_seasons(team_id, season_id, fiflp_name, shirt) VALUES (3, 1, 'TRES, CLUB', 'Azul');
          CREATE TABLE IF NOT EXISTS fiflp_full_pending (group_id INTEGER PRIMARY KEY, since TEXT);
          INSERT INTO fiflp_full_pending VALUES (2, '2026-10-01');
        """)
    conn.commit()
    return conn


def recuento(conn):
    return {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def test_sin_otras_categorias_es_la_misma_conexion():
    import vista_web
    conn = base(con_infantil=False)
    assert vista_web.copia_web(conn) is conn


def test_la_copia_no_tiene_lo_de_infantil(monkeypatch, fijar_web):
    import categorias
    import vista_web
    fijar_web("antes")                  # el EN_WEB de antes del paso E2-D2 (conftest.fijar_web)
    conn = base()
    antes = recuento(conn)
    copia = vista_web.copia_web(conn)
    assert copia is not conn
    assert recuento(conn) == antes                                        # la base no se toca
    q = lambda sql: copia.execute(sql).fetchall()  # noqa: E731
    assert q("SELECT code FROM groups") == [("FF1",)]
    assert q("SELECT id FROM matches") == [(100,)]
    assert q("SELECT match_id, player_id FROM appearances") == [(100, 10)]
    assert q("SELECT match_id FROM match_events") == [(100,)]
    assert q("SELECT count(*) FROM match_staff_all") == [(0,)] and q("SELECT count(*) FROM goals") == [(0,)]
    assert q("SELECT group_id FROM scorers") == [(1,)] and q("SELECT DISTINCT group_id FROM standings") == [(1,)]
    assert q("SELECT count(*) FROM standings_detail") == [(0,)] and q("SELECT count(*) FROM fiflp_full_pending") == [(0,)]
    # El equipo que solo jugaba en infantil ya no está; el de los dos conserva su ficha de la temporada.
    assert q("SELECT id FROM teams ORDER BY id") == [(1,), (2,)]
    assert q("SELECT team_id FROM team_seasons") == [(1,)]
    # El niño que solo jugaba en infantil, tampoco; el de los dos, con lo de benjamín.
    assert q("SELECT id FROM players ORDER BY id") == [(10,)]
    assert q("SELECT name FROM categories ORDER BY id") == [("BENJAMIN",), ("PREBENJAMIN",), ("ALEVIN",)]
    # Con infantil en la web (E2), la misma conexión.
    monkeypatch.setattr(categorias, "EN_WEB", categorias.EN_WEB + ("INFANTIL",))
    assert vista_web.copia_web(conn) is conn
    assert vista_web.copia_web(conn, categorias=("BENJAMIN",)) is not conn


# ── La base de después: el generador publica lo mismo ──────────────────────────────────────────────

_MB = re.compile(r'"mb":\d+')
_VERSION = re.compile(r"\?v=\d{8}[a-z]?|futbolbase2-v[0-9a-z]+|Última actualización: \d{2}/\d{2}/\d{4}")


def normalizado(texto):
    """Sin lo que depende del tamaño de la base: los MB de «Datos y fuentes» (COBERTURA) y la versión que sube
    cuando algo cambia (?v=, CACHE_NAME y la fecha del pie)."""
    return _VERSION.sub("V", _MB.sub('"mb":0', texto))


def sitio(tmp_path, nombre, origen):
    """Una raíz con index.html, sw.js, los data-*.js del árbol y una copia de la base `origen`."""
    raiz = tmp_path / nombre
    raiz.mkdir()
    for p in [ROOT / "index.html", ROOT / "sw.js"] + sorted(ROOT.glob("data-*.js")):
        shutil.copy2(p, raiz / p.name)
    db = raiz / "futbolbase.db"
    shutil.copyfile(origen, db)
    return raiz, db


def generar(raiz, db):
    """generate_js.main con su raíz y su base (que ya ha pasado por el final de una pasada: fichas y enlaces,
    base_mayores.bases_reales). Devuelve {fichero: texto} de lo que queda en la raíz."""
    import generate_js
    with pytest.MonkeyPatch.context() as m:
        m.setattr(generate_js, "PROJECT_ROOT", str(raiz))
        m.setattr(generate_js, "get_connection", lambda: sqlite3.connect(str(db)))
        generate_js.main()
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(raiz.iterdir())
            if p.is_file() and p.name != "futbolbase.db" and not p.name.startswith("futbolbase.db-")}


def generado(tmp_path, nombre, origen):
    """sitio y generar, de una vez (para paralelo.en_paralelo, que la manda por su nombre)."""
    return generar(*sitio(tmp_path, nombre, origen))


def test_generador_igual_con_y_sin_mayores(tmp_path, bases_reales, fijar_web):
    """Dos copias de la base real tras una pasada (conftest.bases_reales): A tal cual y B con infantil, cadete y
    juvenil activados y leídos (y niños de la base reutilizados: el mismo id, el mismo nombre y club sin id), cada
    una con sus fichas y sus enlaces. Lo que escribe el generador es igual byte a byte, salvo los MB de la base y la
    versión; y en B ningún data-*.js nombra un código de los grupos nuevos. Las dos generaciones (~50 s cada una
    con la base real), a la vez (paralelo.en_paralelo): cada una con su raíz y su base. Es lo que garantiza el EN_WEB
    de antes del paso E2-D2: lo fija la prueba (conftest.fijar_web; las dos bases, con sus fichas de ese EN_WEB),
    así que sigue valiendo cuando el director lo amplíe. Lo que cambia con el de después lo mira
    test_fichas_ampliadas.py."""
    from paralelo import en_paralelo
    fijar_web("antes")                  # los procesos de en_paralelo (fork) lo heredan
    hecho = bases_reales["hecho"]
    assert hecho["grupos"] and hecho["actas"] and hecho["jugadores_reutilizados"]
    # Los sin id del mismo nombre y club: siempre que la temporada tenga prebenjamines sin id (recién empezada, no).
    assert hecho["sin_id_reutilizados"] or not hecho["sin_id_disponibles"]
    assert hecho["sin_id_en_fila_ajena"] == 0
    a, b = en_paralelo((generado, (tmp_path, "a", bases_reales["resuelta"])),
                       (generado, (tmp_path, "b", bases_reales["mayores"])))
    assert sorted(a) == sorted(b)
    distintos = [n for n in a if normalizado(a[n]) != normalizado(b[n])]
    assert distintos == [], distintos
    codigos = re.compile(r"\b(?:" + "|".join(map(re.escape, hecho["grupos"])) + r")\b")
    assert [n for n, t in b.items() if n.startswith("data-") and codigos.search(t)] == []


def test_los_sin_id_de_las_mayores_no_caen_en_la_fila_de_un_pequeno(bases_reales):
    """En la base de después (conftest.bases_reales), los niños sin id de infantil que se llaman como un
    prebenjamín sin id del mismo club y temporada (base_mayores los pone a propósito) son OTRA identidad, con su
    categoría (migrate_identidad.norm_sin_id): ninguna identidad sin id tiene apariciones en una de las mayores y
    en otra categoría. Sin eso, sus partidos se mezclarían en la base desde la primera acta."""
    import base_mayores
    import migrate_identidad as M
    hecho = bases_reales["hecho"]
    if not hecho["sin_id_disponibles"]:
        pytest.skip("la temporada en curso aún no tiene prebenjamines sin id (recién empezada): no hay con quién "
                    "montar el caso")
    conn = sqlite3.connect(f"file:{bases_reales['mayores']}?mode=ro", uri=True)
    try:
        filas = conn.execute("SELECT norm_name, team_id, season_id FROM players "
                             "WHERE fiflp_id IS NULL AND team_id IS NOT NULL").fetchall()
        pequenos = {(M.nombre_base(n), t, s) for n, t, s in filas if M.categoria_de(n) is None}
        homonimos = [n for n, t, s in filas if M.categoria_de(n) and (M.nombre_base(n), t, s) in pequenos]
        assert len(homonimos) >= hecho["sin_id_reutilizados"] > 0
        assert base_mayores.sin_id_en_fila_ajena(conn) == 0
    finally:
        conn.close()
