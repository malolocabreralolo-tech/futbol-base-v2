"""Lo que el generador publica de más sobre las fichas: el año de nacimiento estimado ("y", y "yc" si es
confirmado) en data-jugadores-<k>.js (ahora 64 trozos), el índice para buscar por nombre (data-buscar-<xy>.js)
y el ranking por año de nacimiento (data-ranking.js y data-ranking-<año>.js).

Sobre una base pequeña montada aquí (la de db.SCHEMA con las columnas de las fichas) y, si está, sobre una
copia de la base real. Nombres inventados."""
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
import generate_js as G  # noqa: E402
from identidad import trozo  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402
from migrate_identidad import asegurar_esquema  # noqa: E402

quiet = lambda *a, **k: None  # noqa: E731
DB_PATH = ROOT / "futbolbase.db"

# Temporadas (id → nombre, año de inicio), la 2026-27 la de ahora; un grupo por temporada y categoría.
SEED = """
INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES
  (1, '2025-2026', 2025, 2026, 0), (2, '2026-2027', 2026, 2027, 1);
INSERT INTO categories(id, name) VALUES (1, 'PREBENJAMIN'), (2, 'BENJAMIN'), (4, 'ALEVIN');
INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
  (1, 1, 2, 'BG1', 'Grupo 1', 'Gran Canaria', 'grancanaria'),
  (2, 2, 2, 'BG2', 'Grupo 2', 'Gran Canaria', 'grancanaria'),
  (3, 2, 4, 'AG1', 'Grupo 1', 'Gran Canaria', 'grancanaria');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Club Tres');
"""
_ANIO = {1: 2025, 2: 2026, 3: 2026}

# Jugadores inventados: (id, nombre, fiflp_id, [(grupo, equipo, partidos, goles), ...]).
RAUL = (1, "GOMEZ PEREZ, RAUL", 1001, [(1, 1, 8, 6), (2, 1, 4, 3)])          # 2017: dos temporadas
IVAN = (2, "SUAREZ DIAZ, IVAN", 1002, [(1, 2, 8, 2), (2, 2, 4, 1)])          # 2017, menos goles
HUGO = (3, "MORALES RUIZ, HUGO", 1003, [(2, 3, 12, 8)])                      # una temporada: 2017 o 2018
OSCAR = (4, "NAVARRO GIL, OSCAR", 1004, [(1, 3, 10, 2), (2, 3, 2, 0)])       # 2017, 2 partidos este año


def base(*jugadores):
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    asegurar_esquema(conn)
    conn.executescript(SEED)
    siguiente = {}                  # grupo → la próxima jornada libre (un partido por aparición)
    for pid, nombre, fid, filas in jugadores:
        conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (?, ?, ?, ?)",
                     (pid, nombre, nombre, fid))
        for gid, team, pj, goles in filas:
            for i in range(pj):
                j = siguiente.get(gid, 1)
                siguiente[gid] = j + 1
                dia = f"{j:02d}-10-{_ANIO[gid]}" if j <= 28 else f"{j - 28:02d}-11-{_ANIO[gid]}"
                mid = gid * 1000 + j
                conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                             "VALUES (?, ?, ?, ?, 1, 2)", (mid, gid, f"Jornada {j}", dia))
                # Los goles, en el primer partido; titular en todos.
                conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                             "VALUES (?, ?, ?, 7, 'starter', ?, 0)", (mid, team, pid, goles if i == 0 else 0))
    conn.commit()
    asegurar_esquema(conn)
    return conn


def _const(text, nombre):
    m = re.fullmatch(rf"const {nombre} = (.*);\n", text, re.S)
    assert m, text[:200]
    return json.loads(m.group(1))


def fichas(files):
    """{clave: entrada} de todos los data-jugadores-<k>.js."""
    out = {}
    for name, text in files.items():
        k = int(re.fullmatch(r"data-jugadores-(\d+)\.js", name).group(1))
        out.update(_const(text, f"JUGADORES_{k}")["p"])
    return out


def ranking(files, anio=None):
    if anio is None:
        return _const(files["data-ranking.js"], "RANKING")
    return _const(files[f"data-ranking-{anio}.js"], f"RANKING_{anio}")


def test_anio_en_la_ficha():
    p = fichas(G.jugadores_files(base(RAUL, HUGO)))
    assert p["1001"]["y"] == [2017] and "yc" not in p["1001"]
    assert p["1003"]["y"] == [2017, 2018] and "yc" not in p["1003"]


def test_anio_confirmado_manda(monkeypatch):
    monkeypatch.setattr(G, "anios_confirmados", lambda path=None: {"1001": 2016})
    p = fichas(G.jugadores_files(base(RAUL, HUGO)))
    assert p["1001"]["y"] == [2016] and p["1001"]["yc"] == 1
    assert p["1003"]["y"] == [2017, 2018] and "yc" not in p["1003"]
    # También si la clave confirmada es la de un alias de la ficha: el mismo niño sin id, unida por nombre.
    conn = base(RAUL)
    conn.execute("INSERT INTO players(id, full_name, norm_name, ficha_id, union_por, team_id, season_id) "
                 "VALUES (9, 'GOMEZ PEREZ, RAUL', 'GOMEZ PEREZ, RAUL@1.1', 1, 'nombre', 1, 1)")
    conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                 "VALUES (9001, 1, 'Jornada 90', '30-11-2025', 1, 2)")
    conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) "
                 "VALUES (9001, 1, 9, 7, 'sub', 0)")
    conn.commit()
    asegurar_esquema(conn)
    alias = conn.execute("SELECT clave FROM players WHERE id = 9").fetchone()[0]
    assert alias and alias.startswith("n")
    monkeypatch.setattr(G, "anios_confirmados", lambda path=None: {alias: 2016})
    raul = fichas(G.jugadores_files(conn))["1001"]
    assert raul["al"] == [alias] and raul["y"] == [2016] and raul["yc"] == 1


def test_anios_confirmados_lee_el_fichero(tmp_path):
    assert G.anios_confirmados(tmp_path / "no-esta.json") == {}
    vacio = tmp_path / "vacio.json"
    vacio.write_text("{}\n", encoding="utf-8")
    assert G.anios_confirmados(vacio) == {}
    vacio.write_text("\n", encoding="utf-8")
    assert G.anios_confirmados(vacio) == {}
    bueno = tmp_path / "bueno.json"
    bueno.write_text(json.dumps({"1001": {"anio": 2016, "fuente": "lo dice su club"}}), encoding="utf-8")
    assert G.anios_confirmados(bueno) == {"1001": 2016}
    for malo in ('[]', '{"1001": 2016}', '{"1001": {"anio": "2016"}}', '{"1001": {"fuente": "x"}}',
                 '{"1001": {"anio": true}}', '{"1001": '):
        bueno.write_text(malo, encoding="utf-8")
        with pytest.raises(ValueError):
            G.anios_confirmados(bueno)
    # El del repositorio existe y se lee.
    assert G.anios_confirmados() == {} or all(isinstance(v, int) for v in G.anios_confirmados().values())


def test_un_fichero_de_anios_mal_escrito_no_para_la_pasada(tmp_path, monkeypatch, capsys):
    # Todo o nada: con una entrada mala tampoco valen las buenas. Se avisa y se publica sin confirmados.
    malo = tmp_path / "anios_confirmados.json"
    malo.write_text('{"1001": {"anio": 2016}, "1003": {"anio": "2017"}}', encoding="utf-8")
    monkeypatch.setattr(G, "ANIOS_CONFIRMADOS", str(malo))
    with pytest.raises(ValueError):
        G.anios_confirmados()
    p = fichas(G.jugadores_files(base(RAUL, HUGO)))
    assert p["1001"]["y"] == [2017] and not any("yc" in e for e in p.values())
    salida = capsys.readouterr().out
    assert "  ! anios_confirmados.json no se entiende (" in salida
    assert "): se publica sin años confirmados" in salida
    # Y si no es JSON, igual.
    malo.write_text('{"1001": ', encoding="utf-8")
    assert "yc" not in fichas(G.jugadores_files(base(RAUL)))["1001"]
    assert "no se entiende" in capsys.readouterr().out


def test_sesenta_y_cuatro_trozos():
    files = G.jugadores_files(base(RAUL, HUGO))
    assert G.JUGADORES_SHARDS == 64
    assert sorted(files) == sorted(f"data-jugadores-{k}.js" for k in range(64))
    assert 1001 % 64 == 41
    assert "1001" in _const(files["data-jugadores-41.js"], "JUGADORES_41")["p"]
    assert trozo("1003", 64) == 43 and "1003" in _const(files["data-jugadores-43.js"], "JUGADORES_43")["p"]


def test_prefijos_de():
    assert G.prefijos_de("GARCÍA PÉREZ, JOSÉ ÁNGEL") == ["ga", "pe", "jo", "an"]
    assert G.prefijos_de("DE LA CRUZ O'NEILL, IÑAKI") == ["cr", "ne", "in"]
    assert G.prefijos_de("A., X") == []
    # Cada prefijo una vez, en el orden en que sale; las partículas no cuentan.
    assert G.prefijos_de("PEREZ PEÑA, PEDRO DEL PINO") == ["pe", "pi"]
    assert G.prefijos_de("LOS SANTOS Y DO DA LAS, LU") == ["sa", "lu"]


def test_buscar_files():
    files = G.buscar_files(base(RAUL, HUGO))
    raul = ["1001", "GOMEZ PEREZ, RAUL", "Atletico Uno", "2026-2027", [2017]]
    for xy in ("go", "pe", "ra"):
        text = files[f"data-buscar-{xy}.js"]
        assert text.startswith(f"const BUSCAR_{xy.upper()} = [")
        assert raul in _const(text, f"BUSCAR_{xy.upper()}")
    hugo = ["1003", "MORALES RUIZ, HUGO", "Club Tres", "2026-2027", [2017, 2018]]
    assert sorted(files) == sorted(f"data-buscar-{xy}.js" for xy in ("go", "pe", "ra", "mo", "ru", "hu"))
    assert _const(files["data-buscar-ru.js"], "BUSCAR_RU") == [hugo]
    # Por orden de clave.
    conn = base(RAUL, HUGO, (5, "GOMEZ RUIZ, ANA", 999, [(2, 2, 1, 0)]))
    go = _const(G.buscar_files(conn)["data-buscar-go.js"], "BUSCAR_GO")
    assert [e[0] for e in go] == ["999", "1001"]


def test_ranking_files():
    files = G.ranking_files(base(RAUL, IVAN))
    assert ranking(files) == {"temporada": "2026-2027", "anios": {"2017": [2, 2]}}
    assert sorted(files) == ["data-ranking-2017.js", "data-ranking.js"]
    r = ranking(files, 2017)
    assert [e[0] for e in r["t"]] == ["1001", "1002"] and [e[0] for e in r["h"]] == ["1001", "1002"]
    t, h = r["t"][0], r["h"][0]
    # [clave, nombre, equipo, categoría, partidos, titular, goles, índice, dudoso]
    assert t[:7] == ["1001", "GOMEZ PEREZ, RAUL", "Atletico Uno", "benjamin", 4, 4, 3] and t[8] == 0
    assert h[:7] == ["1001", "GOMEZ PEREZ, RAUL", "Atletico Uno", "benjamin", 12, 12, 9] and h[8] == 0
    assert t[7] > r["t"][1][7] and h[7] > r["h"][1][7]
    # Con menos de 3 partidos esta temporada no sale en «t» (sí en «h», con 12).
    files = G.ranking_files(base(RAUL, IVAN, OSCAR))
    r = ranking(files, 2017)
    assert "1004" not in [e[0] for e in r["t"]] and "1004" in [e[0] for e in r["h"]]
    assert ranking(files)["anios"] == {"2017": [2, 3]}


def test_ranking_sin_temporada_en_curso():
    conn = base(RAUL)
    conn.execute("UPDATE seasons SET is_current = 0")
    files = G.ranking_files(conn)
    assert ranking(files) == {"temporada": None, "anios": {"2017": [0, 1]}}
    assert ranking(files, 2017)["t"] == []


def test_dudoso_sale_en_sus_dos_anios():
    files = G.ranking_files(base(RAUL, HUGO))
    en = {anio: {e[0]: e for e in ranking(files, anio)["h"]} for anio in (2017, 2018)}
    assert en[2017]["1003"][8] == 1 and en[2018]["1003"][8] == 1
    assert en[2018]["1003"][7] > en[2017]["1003"][7]          # factor_edad: en 2018 es de los pequeños
    assert "1001" not in en[2018] and en[2017]["1001"][8] == 0
    t = {anio: [e[0] for e in ranking(files, anio)["t"]] for anio in (2017, 2018)}
    assert "1003" in t[2017] and "1003" in t[2018]
    assert ranking(files)["anios"] == {"2017": [2, 2], "2018": [1, 1]}


def test_ranking_orden_y_tope(monkeypatch):
    # A igualdad de índice, más goles primero; a igualdad de goles, por clave. Como mucho TOPE.
    jugadores = [(10 + i, f"APELLIDO{chr(65 + i)} OTRO, NOMBRE", 2000 - i, [(1, 1, 8, 2), (2, 1, 4, 1)])
                 for i in range(4)]
    import ranking as R
    monkeypatch.setattr(R, "TOPE", 3)
    r = ranking(G.ranking_files(base(*jugadores)), 2017)
    assert [e[0] for e in r["h"]] == ["1997", "1998", "1999"]


# Una liga de cuatro equipos (grupo 4, benjamín 2026-27), una vuelta, con los marcadores a mano:
#   M1 Atletico Uno 4-0 Deportivo Dos     M4 Deportivo Dos 0-2 Club Tres
#   M2 Atletico Uno 2-1 Club Tres         M5 Deportivo Dos 1-1 Union Cuatro
#   M3 Atletico Uno 3-1 Union Cuatro      M6 Club Tres 0-0 Union Cuatro
# Y una copa (grupo 5) de dos partidos: M7 Atletico Uno 5-0 Deportivo Dos y M8 Deportivo Dos 0-3 Atletico Uno.
# La tabla de la liga (el percentil es del grupo: solo la liga, todos con 3 partidos):
#   equipo          PJ  GF  GC  Pts  Pts/PJ  percentil
#   Atletico Uno     3   9   2   9   3,00    1
#   Club Tres        3   3   2   4   1,33    0,6667
#   Union Cuatro     3   2   4   2   0,67    0,3333
#   Deportivo Dos    3   1   7   1   0,33    0
# El rival se mide con toda su temporada de benjamín (liga y copa), con PRUDENCIA_RIVAL = 4 partidos a la
# media: 23 goles en 8 partidos, 23 / (2 × 8) = 1,4375 encajados por equipo y partido.
#   equipo          PJ  GC  encajados prudentes            peso de un gol contra él
#   Atletico Uno     5   2  (2 + 4 × 1,4375) / 9 = 0,8611   1,4375 / 0,8611 = 1,669 → 1,5
#   Club Tres        3   2  (2 + 5,75) / 7 = 1,1071         1,2984
#   Union Cuatro     3   4  (4 + 5,75) / 7 = 1,3929         1,0321
#   Deportivo Dos    5  15  (15 + 5,75) / 9 = 2,3056        0,6235
# En la copa nadie llega a 3 partidos: sin percentil (pero el rival pesa, con su temporada).
LIGA = [(1, 1, 2, 4, 0), (2, 1, 3, 2, 1), (3, 1, 4, 3, 1), (4, 2, 3, 0, 2), (5, 2, 4, 1, 1), (6, 3, 4, 0, 0)]
COPA = [(7, 1, 2, 5, 0), (8, 2, 1, 0, 3)]
# (player_id, nombre, fiflp_id, equipo, {partido: goles}): juega todos los partidos de su equipo.
EN_LA_LIGA = [
    (1, "GOMEZ PEREZ, RAUL", 1001, 1, {1: 2, 2: 1, 7: 2}),      # 2 al colista, 1 a Club Tres; 2 en la copa
    (2, "SUAREZ DIAZ, IVAN", 1002, 2, {5: 1}),                  # 1 a Union Cuatro
    (3, "MORALES RUIZ, HUGO", 1003, 3, {4: 2}),                 # 2 al colista
    (4, "NAVARRO GIL, OSCAR", 1004, 4, {3: 2}),                 # 2 al líder
]


def base_liga(segunda_a=False):
    """La liga y la copa de arriba. Con `segunda_a`, además un grupo «Segunda Fase A» de esa temporada en
    cuya clasificación está Atletico Uno (sin ningún partido jugado)."""
    conn = base()
    conn.executescript("""
      INSERT INTO teams(id, name) VALUES (4, 'Union Cuatro');
      INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
        (4, 2, 2, 'BG4', 'Grupo 4', 'Primera Fase GC', 'grancanaria'),
        (5, 2, 2, 'CP1', 'Copa', 'Copa Gran Canaria', 'grancanaria');""")
    if segunda_a:
        conn.executescript("""
          INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
            (6, 2, 2, 'A1', 'Grupo 1', 'Segunda Fase A', 'grancanaria');
          INSERT INTO standings(group_id, team_id, position, points, played) VALUES (6, 1, 1, 0, 0);""")
    for grupo, partidos in ((4, LIGA), (5, COPA)):
        for n, local, visitante, gl, gv in partidos:
            conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, "
                         "away_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (n, grupo, f"Jornada {n}", f"{n:02d}-10-2026", local, visitante, gl, gv))
    partidos = {n: (local, visitante) for n, local, visitante, _, _ in LIGA + COPA}
    for pid, nombre, fid, equipo, goles in EN_LA_LIGA:
        conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (?, ?, ?, ?)",
                     (pid, nombre, nombre, fid))
        for n, (local, visitante) in partidos.items():
            if equipo in (local, visitante):
                conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                             "VALUES (?, ?, ?, 7, 'starter', ?, 0)", (n, equipo, pid, goles.get(n, 0)))
    conn.commit()
    asegurar_esquema(conn)
    return conn


def _fila_ranking(datos, pid, code):
    """La fila del ranking de la ficha `pid` en el grupo `code`: (año, categoría, fase, partidos, titular,
    goles, goles por rival, isla, percentil, temporada, equipo)."""
    return next(r for _, fila, _, r in datos["filas"][pid] if fila[1] == code)


def test_goles_por_rival_y_percentil():
    datos = G._datos_fichas(base_liga())
    raul = _fila_ranking(datos, 1, "BG4")
    # 2 goles a Deportivo Dos (0,6235) y 1 a Club Tres (1,2984).
    assert raul[5] == 3 and raul[6] == pytest.approx(2 * 0.6235 + 1.2984) and raul[7] == "grancanaria"
    assert raul[8] == 1.0 and raul[2] == "Primera Fase GC"
    ivan = _fila_ranking(datos, 2, "BG4")
    assert ivan[5] == 1 and ivan[6] == pytest.approx(1.0321) and ivan[8] == 0.0
    assert _fila_ranking(datos, 3, "BG4")[8] == pytest.approx(2 / 3)
    assert _fila_ranking(datos, 4, "BG4")[8] == pytest.approx(1 / 3)
    # La copa de dos partidos: sin percentil; sus 2 goles, a Deportivo Dos, pesan por su temporada entera.
    copa = _fila_ranking(datos, 1, "CP1")
    assert copa[3] == 2 and copa[5] == 2 and copa[6] == pytest.approx(2 * 0.6235) and copa[8] is None


def test_un_rival_sin_partidos_con_marcador_pesa_1():
    # La base de siempre no tiene marcadores: sin media de la temporada, todos los goles valen 1.
    datos = G._datos_fichas(base(RAUL, HUGO))
    assert all(r[6] == r[5] for fs in datos["filas"].values() for *_, r in fs)


def test_la_fase_buena_de_su_equipo():
    # Atletico Uno está en la Segunda Fase A (solo en su clasificación): los goles de Raul en la Primera Fase
    # cuentan como de la A (1,30). Los de Ivan, de Deportivo Dos, que no está en ninguna, como de la suya.
    import ranking as R
    conn = base_liga(segunda_a=True)
    datos = G._datos_fichas(conn)
    raul = _fila_ranking(datos, 1, "BG4")
    assert raul[2] == "Segunda Fase A" and R.nivel_fase(raul[2]) == 1.30
    assert _fila_ranking(datos, 1, "CP1")[2] == "Segunda Fase A"        # la copa, sin nivel propio, también
    assert _fila_ranking(datos, 2, "BG4")[2] == "Primera Fase GC"
    # Lo publicado de la ficha sigue con la fase de verdad del grupo.
    p = fichas(G.jugadores_files(conn, datos=datos))
    shard = _const(G.jugadores_files(conn)[f"data-jugadores-{trozo('1001', 64)}.js"], f"JUGADORES_{trozo('1001', 64)}")
    assert shard["g"]["2026-2027/BG4"][2] == "Primera Fase GC" and "1001" in p
    # Y el índice de Raul sube respecto a la base sin la Segunda Fase.
    antes = {e[0]: e[7] for e in ranking(G.ranking_files(base_liga()), 2017)["t"]}
    despues = {e[0]: e[7] for e in ranking(G.ranking_files(conn), 2017)["t"]}
    assert despues["1001"] > antes["1001"] and despues["1002"] == antes["1002"]


def test_el_rival_cambia_el_orden():
    # Hugo y Oscar: los dos con 3 partidos y 2 goles esta temporada en la liga (y nada más), del mismo año.
    # Con solo los goles empatarían y saldría primero el de clave menor (Hugo); Oscar los marcó al líder.
    r = ranking(G.ranking_files(base_liga()), 2017)
    t = {e[0]: e for e in r["t"]}
    assert t["1003"][4:7] == t["1004"][4:7] == [3, 3, 2]
    orden = [e[0] for e in r["t"]]
    assert orden.index("1004") < orden.index("1003") and t["1004"][7] > t["1003"][7]
    # Lo publicado no cambia de forma: los goles, los de verdad.
    assert all(len(e) == 9 and isinstance(e[6], int) for e in r["t"] + r["h"])


def test_write_borra_los_que_sobran(tmp_path):
    for name in ("data-buscar-zz.js", "data-ranking-1999.js", "data-ranking.js", "data-jugadores-3.js"):
        (tmp_path / name).write_text("const X = 1;\n", encoding="utf-8")
    conn = base(RAUL, HUGO)
    G.write_buscar(conn, root=str(tmp_path))
    G.write_ranking(conn, root=str(tmp_path))
    nombres = set(os.listdir(tmp_path))
    assert "data-buscar-zz.js" not in nombres and "data-ranking-1999.js" not in nombres
    assert {"data-ranking.js", "data-ranking-2017.js", "data-ranking-2018.js", "data-buscar-go.js",
            "data-jugadores-3.js"} <= nombres
    assert (tmp_path / "data-ranking.js").read_text(encoding="utf-8") == G.ranking_files(conn)["data-ranking.js"]


def test_main_hace_la_consulta_una_vez_y_escribe_despues_de_las_fichas():
    import inspect
    main = inspect.getsource(G.main)
    assert main.index("write_jugadores(") < main.index("write_buscar(") < main.index("write_ranking(")
    assert main.index("write_ranking(") < main.index("bump_if_changed(before_snapshot)")
    assert "_datos_fichas(conn)" in main


def test_base_real(tmp_path):
    """Sobre una copia de la base real, lo estructural (está en la puerta del bot: nada que el crecimiento normal
    de los datos vaya a romper): las tres terminan; cada ficha con filas de una categoría conocida tiene de uno
    a tres años; ninguna clave se pierde con 64 trozos y cada una está en el suyo; toda ficha con nombre
    buscable está en el buscador; el ranking es determinista y tiene algún año. Las cifras (tiempo, fichas con
    tres años, el fichero de búsqueda mayor) se imprimen, no se exigen."""
    from nacimiento import VENTANA
    if not DB_PATH.exists():
        pytest.skip("futbolbase.db no está")
    src = sqlite3.connect(str(DB_PATH))
    conn = sqlite3.connect(str(tmp_path / "fb.db"))
    src.backup(conn)
    src.close()
    t0 = time.monotonic()
    datos = G._datos_fichas(conn)
    jug = G.jugadores_files(conn, datos=datos)
    bus = G.buscar_files(conn, datos=datos)
    ran = G.ranking_files(conn, datos=datos)
    segundos = time.monotonic() - t0
    # Los años.
    p, grupos = {}, {}
    for name, text in jug.items():
        k = int(re.fullmatch(r"data-jugadores-(\d+)\.js", name).group(1))
        shard = _const(text, f"JUGADORES_{k}")
        for clave in shard["p"]:
            assert trozo(clave, 64) == k, clave
        for alias in shard["a"]:
            assert trozo(alias, 64) == k, alias
        p.update(shard["p"])
        grupos.update(shard["g"])
    conocidas = {k for k, e in p.items() if any(grupos[f"{c[0]}/{c[1]}"][0] in VENTANA for c in e["c"])}
    sin = [k for k in conocidas if not 1 <= len(p[k].get("y", [])) <= 3]
    assert sin == []
    # Ninguna clave se pierde: las mismas que las de las fichas publicadas.
    assert set(p) == set(G.claves_de_ficha(conn).values())
    # La búsqueda.
    en_buscar = {e[0] for name, t in bus.items()
                 for e in _const(t, "BUSCAR_" + name[len("data-buscar-"):-3].upper())}
    assert en_buscar == {k for k, e in p.items() if G.prefijos_de(e["n"])}
    # El ranking: los mismos bytes en otra pasada entera (determinista), y algún año con alguien.
    assert G.ranking_files(conn) == ran
    anios = ranking(ran)["anios"]
    assert anios and all(f"data-ranking-{anio}.js" in ran for anio in anios)
    mayor = max(bus, key=lambda n: len(bus[n].encode()))
    print(f"\n  base real: {segundos:.1f} s; {len(p)} fichas, {sum(len(e.get('y', [])) == 3 for e in p.values())} "
          f"con tres años; búsqueda mayor {mayor} {len(bus[mayor].encode()):,} B; años del ranking {sorted(anios)}")


# ------------------------------------------------------------------ la liga de escuelas (MyGol) en la ficha

def escuela(conn, torneos, enlaces):
    """Las tablas de MyGol a mano. `torneos`: {torneo: (temporada, categoría, {equipo: (nombre, {jugador:
    [jugó en cada partido, ...]})})}; `enlaces`: {jugador de MyGol: player_id}. Cada equipo juega sus
    partidos contra uno ficticio (el 999)."""
    import enlace_mygol
    import import_mygol
    import_mygol.crear_tablas(conn)
    partido = 1
    for tid, (temporada, categoria, equipos) in torneos.items():
        conn.execute("INSERT INTO mygol_torneos VALUES (?, ?, ?, ?)", (tid, temporada, categoria, f"T{tid}"))
        for eid, (nombre, jugadores) in equipos.items():
            conn.execute("INSERT INTO mygol_equipos VALUES (?, ?)", (eid, nombre))
            for j in range(max(len(v) for v in jugadores.values())):
                conn.execute("INSERT INTO mygol_partidos VALUES (?, ?, ?, ?, 5, ?, 999, 'CAMPO')",
                             (partido, tid, f"Jornada {j + 1}", f"{temporada[:4]}-10-{j + 1:02d}", eid))
                for jid, jugo in jugadores.items():
                    if j < len(jugo):
                        conn.execute("INSERT OR IGNORE INTO mygol_jugadores VALUES (?, 'Nombre', 'Apellido Otro', "
                                     "'APELLIDO OTRO, NOMBRE')", (jid,))
                        conn.execute("INSERT INTO mygol_participaciones VALUES (?, ?, ?, ?)",
                                     (partido, jid, eid, jugo[j]))
                partido += 1
    conn.execute(enlace_mygol.ESQUEMA)
    conn.executemany("INSERT INTO mygol_enlaces VALUES (?, ?)", sorted(enlaces.items()))
    conn.commit()
    return conn


# Hugo (benjamín 2026-27: 2017 o 2018): el miniprebenjamín de 2022-23 con un equipo, y en 2024-25 en dos
# equipos del prebenjamín (el «A» y el «E» de su club) y en uno sin ninguna jornada jugada apuntada.
TORNEOS_HUGO = {
    32: ("2022-2023", "miniprebenjamin", {1: ("CD UNO  A ", {50: [1, 1, 0, 1]})}),
    67: ("2024-2025", "prebenjamin", {2: ("CD UNO E", {51: [1, 0]}), 3: ("CD UNO A", {51: [1, 1, 1]}),
                                      4: ("ESCUELA TRES", {52: [0, 0]})}),
}


def test_la_escuela_en_la_ficha():
    conn = escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 3, 51: 3, 52: 3})
    p = fichas(G.jugadores_files(conn))
    # Una fila por temporada y equipo (los espacios de más, fuera), en orden de temporada y de equipo; las
    # jornadas, las que jugó (0: estaba en la plantilla y no consta ninguna jugada).
    assert p["1003"]["e"] == [["2022-2023", "CD UNO A", "miniprebenjamin", 3],
                              ["2024-2025", "CD UNO A", "prebenjamin", 3],
                              ["2024-2025", "CD UNO E", "prebenjamin", 1],
                              ["2024-2025", "ESCUELA TRES", "prebenjamin", 0]]
    assert "e" not in p["1001"]
    # Sin categoría (un torneo sin decidir), null.
    conn = escuela(base(HUGO), {32: ("2022-2023", None, {1: ("CD UNO A", {50: [1]})})}, {50: 3})
    assert fichas(G.jugadores_files(conn))["1003"]["e"] == [["2022-2023", "CD UNO A", None, 1]]


def test_la_escuela_afina_el_anio():
    # Hugo, solo con la federación: una temporada de benjamín (2026-27, 12 partidos) → 2017 o 2018.
    assert fichas(G.jugadores_files(base(HUGO)))["1003"]["y"] == [2017, 2018]
    # Con el prebenjamín de escuela de 2023-24 (ventana 2016-2017), 5 jornadas: las dos observaciones pesan 1
    # (12 y 5 partidos, PARTIDOS_PLENOS = 5). 2017 cabe en las dos: log 1 + log 1 = 0. 2018 es un año joven
    # para el prebenjamín de 2023: log 1 + log 0,25 = -1,386, por debajo del corte (-log 3 = -1,099). → 2017.
    t = {52: ("2023-2024", "prebenjamin", {1: ("CD UNO A", {50: [1] * 5})})}
    assert fichas(G.jugadores_files(escuela(base(HUGO), t, {50: 3})))["1003"]["y"] == [2017]
    # El miniprebenjamín de 2022-23 (2017-2018) no dice nada nuevo: sigue con los dos.
    t = {32: ("2022-2023", "miniprebenjamin", {1: ("CD UNO A", {50: [1] * 5})})}
    assert fichas(G.jugadores_files(escuela(base(HUGO), t, {50: 3})))["1003"]["y"] == [2017, 2018]
    # El miniprebenjamín de 2023-24 (2018-2019): 2017 es un año viejo, log 0,01 = -4,6 → 2018.
    t = {53: ("2023-2024", "miniprebenjamin", {1: ("CD UNO A", {50: [1] * 5})})}
    assert fichas(G.jugadores_files(escuela(base(HUGO), t, {50: 3})))["1003"]["y"] == [2018]
    # Una temporada «en la plantilla» (0 jornadas) cuenta como una jornada: peso 0,2 frente al 1 de la
    # federación, 2018 se queda en 0,2 × log 0,25 = -0,277, por encima del corte → los dos.
    t = {52: ("2023-2024", "prebenjamin", {1: ("CD UNO A", {50: [0, 0]})})}
    conn = escuela(base(HUGO), t, {50: 3})
    assert fichas(G.jugadores_files(conn))["1003"]["y"] == [2017, 2018]
    # Y sin categoría no cuenta.
    t = {52: ("2023-2024", None, {1: ("CD UNO A", {50: [1] * 5})})}
    assert fichas(G.jugadores_files(escuela(base(HUGO), t, {50: 3})))["1003"]["y"] == [2017, 2018]
    # El buscador y el ranking, con el mismo año.
    t = {52: ("2023-2024", "prebenjamin", {1: ("CD UNO A", {50: [1] * 5})})}
    conn = escuela(base(HUGO), t, {50: 3})
    assert _const(G.buscar_files(conn)["data-buscar-mo.js"], "BUSCAR_MO")[0][4] == [2017]
    assert ranking(G.ranking_files(conn))["anios"] == {"2017": [1, 1]}


def test_el_anio_confirmado_manda_sobre_la_escuela(monkeypatch):
    monkeypatch.setattr(G, "anios_confirmados", lambda path=None: {"1003": 2018})
    t = {52: ("2023-2024", "prebenjamin", {1: ("CD UNO A", {50: [1] * 5})})}
    p = fichas(G.jugadores_files(escuela(base(HUGO), t, {50: 3})))["1003"]
    assert p["y"] == [2018] and p["yc"] == 1 and p["e"] == [["2023-2024", "CD UNO A", "prebenjamin", 5]]


def _tres(conn):
    return G.jugadores_files(conn), G.buscar_files(conn), G.ranking_files(conn)


def test_sin_enlaces_sale_igual():
    import import_mygol
    antes = _tres(base(RAUL, HUGO))
    # La tabla de enlaces vacía (y las de MyGol llenas): lo mismo, byte a byte.
    assert _tres(escuela(base(RAUL, HUGO), TORNEOS_HUGO, {})) == antes
    # Las de MyGol sin la de enlaces: igual.
    conn = base(RAUL, HUGO)
    import_mygol.crear_tablas(conn)
    assert _tres(conn) == antes
    # Con enlaces a otra ficha (Hugo), la de Raul sale igual.
    con = _tres(escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 3}))
    assert fichas(con[0])["1001"] == fichas(antes[0])["1001"]
    assert [e for e in _const(con[1]["data-buscar-go.js"], "BUSCAR_GO")] == \
        _const(antes[1]["data-buscar-go.js"], "BUSCAR_GO")


def test_las_tablas_de_mygol_a_medias_no_paran_el_generador(capsys):
    """Un enlace a una identidad que ya no existe o que ya no es la principal de su ficha, y tablas de MyGol
    que faltan: la ficha sale sin escuela, nunca un error."""
    import import_mygol
    antes = _tres(base(RAUL, HUGO))
    conn = escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 777, 51: 777})
    assert _tres(conn) == antes
    # Una identidad unida a la ficha de Raul (no es su principal).
    conn = escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 9})
    conn.execute("INSERT INTO players(id, full_name, norm_name, ficha_id, union_por, team_id, season_id) "
                 "VALUES (9, 'GOMEZ PEREZ, RAUL', 'GOMEZ PEREZ, RAUL@1.1', 1, 'nombre', 1, 1)")
    conn.commit()
    assert "e" not in fichas(G.jugadores_files(conn))["1001"]
    # La de enlaces sin las demás.
    conn = escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 3})
    for t in import_mygol.TABLAS:
        conn.execute(f"DROP TABLE {t}")
    conn.commit()
    assert _tres(conn) == antes
    # Una tabla con otras columnas (de otra versión): se avisa y se publica sin escuelas.
    conn = escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 3})
    conn.execute("DROP TABLE mygol_partidos")
    conn.execute("CREATE TABLE mygol_partidos (otra INTEGER)")
    conn.commit()
    assert _tres(conn) == antes
    assert "  ! MyGol: la liga de escuelas no se lee (" in capsys.readouterr().out


def test_determinista_con_escuela():
    a = _tres(escuela(base(RAUL, HUGO), TORNEOS_HUGO, {50: 3, 51: 3, 52: 3}))
    b = _tres(escuela(base(RAUL, HUGO), TORNEOS_HUGO, {52: 3, 51: 3, 50: 3}))
    assert a == b


def test_base_real_con_escuela(tmp_path):
    """Sobre una copia de la base real con los originales de MyGol importados en la copia y los enlaces
    guardados: sin enlaces, los tres *_files salen con los mismos bytes que sin las tablas de MyGol; con
    ellos, ninguna ficha pasa de un año a tres. Las cifras (fichas que pasan de dos años a uno, fichas con
    escuela, cuántas la tienen antes de su primera temporada federada, segundos y bytes de más) se imprimen."""
    import enlace_mygol
    import import_mygol
    if not DB_PATH.exists():
        pytest.skip("futbolbase.db no está")
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn = sqlite3.connect(str(tmp_path / "fb.db"))
    src.backup(conn)
    src.close()
    t0 = time.monotonic()
    datos = G._datos_fichas(conn)
    t_antes = time.monotonic() - t0
    antes = (G.jugadores_files(conn, datos), G.buscar_files(conn, datos), G.ranking_files(conn, datos))
    import_mygol.importar(conn)
    conn.execute(enlace_mygol.ESQUEMA)
    conn.commit()
    assert _tres(conn) == antes                     # las tablas de MyGol llenas, sin enlaces: igual
    enlace_mygol.guardar_enlaces(conn, registro=quiet)
    t0 = time.monotonic()
    datos_e = G._datos_fichas(conn)
    t_despues = time.monotonic() - t0
    jug = G.jugadores_files(conn, datos_e)
    p0, p1 = fichas(antes[0]), fichas(jug)
    con_e = {k for k, e in p1.items() if "e" in e}
    assert con_e and set(p0) == set(p1)
    # Las fichas sin escuela, idénticas.
    assert all(p0[k] == p1[k] for k in p1 if k not in con_e)
    de_dos_a_uno = sum(1 for k in con_e if len(p0[k].get("y", [])) == 2 and len(p1[k].get("y", [])) == 1)
    de_uno_a_tres = [k for k in con_e if len(p0[k].get("y", [])) == 1 and len(p1[k].get("y", [])) == 3]
    assert de_uno_a_tres == []
    otros = sum(1 for k in con_e if p0[k].get("y") != p1[k].get("y") and not (
        len(p0[k].get("y", [])) == 2 and len(p1[k].get("y", [])) == 1 and set(p1[k]["y"]) <= set(p0[k]["y"])))
    # Antes de su primera temporada federada: alguna temporada de escuela anterior a la primera de "c".
    antes_fed = sum(1 for k in con_e if min(int(e[0][:4]) for e in p1[k]["e"]) < min(int(c[0][:4]) for c in p1[k]["c"]))
    bytes_mas = sum(len(t.encode()) for t in jug.values()) - sum(len(t.encode()) for t in antes[0].values())
    print(f"\n  base real con escuela: {len(con_e)} fichas con «e»; {antes_fed} con escuela antes de su primera "
          f"temporada federada; {de_dos_a_uno} pasan de dos años a uno; {otros} cambian de otra forma; "
          f"_datos_fichas {t_antes:.2f} s → {t_despues:.2f} s; data-jugadores {bytes_mas:+,} B")


# ------------------------------------------------------------------ infantil, cadete y juvenil (parte E2)

# Dos temporadas (2019-20 y la de ahora, 2026-27), las seis categorías y, en 2026-27, las ligas y las copas de
# cadete del convenio (scripts/convenio.py), una liga de Lanzarote con su copa en benjamín (como hoy) y lo mismo
# en alevín de Lanzarote (el alevín de islas, cuando entre). Códigos y nombres inventados.
SEED_E = """
INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES
  (1, '2019-2020', 2019, 2020, 0), (2, '2026-2027', 2026, 2027, 1);
INSERT INTO categories(id, name) VALUES (1, 'PREBENJAMIN'), (2, 'BENJAMIN'), (4, 'ALEVIN'), (5, 'INFANTIL'),
  (6, 'CADETE'), (7, 'JUVENIL');
INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
  (10, 2, 6, 'CADI1', 'Grupo 1', 'Interinsular', 'interinsular'),
  (11, 2, 6, 'CADULC1', 'Grupo 1', 'Copa Insular Lanzarote', 'lanzarote'),
  (12, 2, 6, 'CADNG1', 'Grupo 1', 'Insular GC', 'grancanaria'),
  (13, 2, 6, 'CADNGC1', 'Grupo 1', 'Copa Insular GC', 'grancanaria'),
  (14, 1, 2, 'BG1', 'Grupo 1', 'Primera Fase GC', 'grancanaria'),
  (15, 2, 2, 'BPL1', 'Grupo 1', 'Preferente Lanzarote', 'lanzarote'),
  (16, 2, 2, 'BCPL1', 'Grupo 1', 'Copa Cabildo Preferente Lanzarote', 'lanzarote'),
  (17, 2, 4, 'ALPL1', 'Grupo 1', 'Preferente Lanzarote', 'lanzarote'),
  (18, 2, 4, 'ALCPL1', 'Grupo 1', 'Copa Cabildo Preferente Lanzarote', 'lanzarote');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Rival Tres'), (4, 'Union Cuatro'),
  (5, 'Club Cinco');
"""
_ANIO_E = {gid: (2019 if gid == 14 else 2026) for gid in range(10, 19)}

# (id, nombre, fiflp_id, [(grupo, equipo, partidos, goles), ...]), como en base(): cada aparición, un partido
# de su equipo contra Rival Tres.
EN_INTERINSULAR = (21, "LOPEZ VEGA, JUAN", 2001, [(10, 1, 12, 10), (11, 1, 2, 3)])
EN_INSULAR = (22, "RUIZ SOSA, PABLO", 2002, [(12, 2, 12, 10), (13, 2, 2, 3)])
DE_BENJAMIN_A_CADETE = (23, "DIAZ GIL, MARIO", 2003, [(14, 1, 8, 5), (12, 2, 8, 2)])
BENJAMIN_LANZAROTE = (24, "SOSA LEON, HUGO", 2004, [(15, 4, 6, 3), (16, 4, 2, 1)])
ALEVIN_LANZAROTE = (25, "VEGA CRUZ, IVAN", 2005, [(17, 5, 6, 3), (18, 5, 2, 1)])


def base_e(*jugadores):
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    asegurar_esquema(conn)
    conn.executescript(SEED_E)
    siguiente = {}
    for pid, nombre, fid, filas in jugadores:
        conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (?, ?, ?, ?)",
                     (pid, nombre, nombre, fid))
        for gid, team, pj, goles in filas:
            for i in range(pj):
                j = siguiente.get(gid, 1)
                siguiente[gid] = j + 1
                dia = f"{j:02d}-10-{_ANIO_E[gid]}" if j <= 28 else f"{j - 28:02d}-11-{_ANIO_E[gid]}"
                mid = gid * 1000 + j
                conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                             "VALUES (?, ?, ?, ?, ?, 3)", (mid, gid, f"Jornada {j}", dia, team))
                conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                             "VALUES (?, ?, ?, 7, 'starter', ?, 0)", (mid, team, pid, goles if i == 0 else 0))
    conn.commit()
    asegurar_esquema(conn)
    return conn


@pytest.fixture
def seis(monkeypatch):
    """categorias.EN_WEB con las seis (la tarea 8): la copia de la web (vista_web) las deja."""
    import categorias
    import vista_web
    monkeypatch.setattr(categorias, "EN_WEB", tuple(categorias.DB_NAME.values()))
    return lambda conn: vista_web.copia_web(conn)


def test_ranking_de_cadete(seis):
    import ranking as R
    conn = seis(base_e(EN_INTERINSULAR, EN_INSULAR, BENJAMIN_LANZAROTE, ALEVIN_LANZAROTE))
    datos = G._datos_fichas(conn)
    # La copa de Lanzarote de un equipo de la Interinsular cuenta como la Interinsular (1,35); la suya, lo suyo.
    assert _fila_ranking(datos, 21, "CADI1")[2] == "Interinsular"
    copa = _fila_ranking(datos, 21, "CADULC1")
    assert copa[2] == "Interinsular" and R.nivel_fase(copa[2]) == 1.35 and copa[7] == "lanzarote"
    # La de Gran Canaria de un equipo de la Insular, como la Insular GC (0,90).
    copa = _fila_ranking(datos, 22, "CADNGC1")
    assert copa[2] == "Insular GC" and R.nivel_fase(copa[2]) == 0.90
    # El alevín de islas también; el benjamín de Lanzarote, como hoy: su copa se queda con la suya (1).
    assert _fila_ranking(datos, 25, "ALCPL1")[2] == "Preferente Lanzarote"
    assert _fila_ranking(datos, 24, "BCPL1")[2] == "Copa Cabildo Preferente Lanzarote"
    # Los mismos goles en los mismos partidos: delante el de la liga más difícil, en los dos años posibles.
    files = G.ranking_files(conn, datos)
    for anio in (2011, 2012):
        r = ranking(files, anio)
        assert [e[0] for e in r["t"]] == ["2001", "2002"]
        assert [e[3] for e in r["t"]] == ["cadete", "cadete"] and r["t"][0][7] > r["t"][1][7]
        assert r["t"][0][4:7] == r["t"][1][4:7] == [14, 14, 13]


def test_ficha_de_benjamin_a_cadete(seis):
    conn = seis(base_e(DE_BENJAMIN_A_CADETE))
    files = G.jugadores_files(conn)
    p = fichas(files)
    assert list(p) == ["2003"]
    mario = p["2003"]
    assert [(c[0], c[1]) for c in mario["c"]] == [("2019-2020", "BG1"), ("2026-2027", "CADNG1")]
    shard = _const(files[f"data-jugadores-{trozo('2003', 64)}.js"], f"JUGADORES_{trozo('2003', 64)}")
    assert {shard["g"][f"{c[0]}/{c[1]}"][0] for c in mario["c"]} == {"benjamin", "cadete"}
    # Benjamín en 2019-20 (2010 o 2011) y cadete en 2026-27 (2011 o 2012): 2011.
    assert mario["y"] == [2011] and "yc" not in mario
    assert _const(G.buscar_files(conn)["data-buscar-ma.js"], "BUSCAR_MA")[0][4] == [2011]
    # Con la EN_WEB de hoy la web no ve el cadete: la ficha, solo con benjamín.
    import categorias
    import vista_web
    hoy = vista_web.copia_web(base_e(DE_BENJAMIN_A_CADETE), ("BENJAMIN", "PREBENJAMIN", "ALEVIN"))
    assert [c[1] for c in fichas(G.jugadores_files(hoy))["2003"]["c"]] == ["BG1"]
    assert categorias.EN_WEB != ("BENJAMIN", "PREBENJAMIN", "ALEVIN")       # el parche de `seis` sigue puesto
