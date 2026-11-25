"""TDD — el enlace de los niños de la liga de escuelas (MyGol) con las fichas de la federación
(scripts/enlace_mygol.py).

La regla, pura: nombres inventados, sin base ni red."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from enlace_mygol import MARGEN_JOVEN, Ficha, Nino, edad_compatible, enlazar  # noqa: E402

RAUL = "GOMEZ PEREZ, RAUL"


def nino(id, norm=RAUL, temporada=2024, categoria="prebenjamin", clubes=("viera",)):
    return Nino(id=id, norm=norm, temporada=temporada, categoria=categoria, clubes=frozenset(clubes))


def ficha(id, *nombres, anios=(2017,)):
    return Ficha(id=id, nombres=frozenset(nombres or (RAUL,)), anios=tuple(anios))


def test_edad_compatible():
    assert MARGEN_JOVEN == 1
    # Prebenjamín 2024: nacidos en 2017 o 2018, y un año por abajo (2019) también vale.
    assert edad_compatible((2018,), 2024, "prebenjamin")
    assert edad_compatible((2019,), 2024, "prebenjamin")
    assert not edad_compatible((2020,), 2024, "prebenjamin")
    assert not edad_compatible((2016,), 2024, "prebenjamin")
    assert edad_compatible((2016, 2017), 2024, "prebenjamin")
    assert edad_compatible((), 2024, "prebenjamin")              # sin año: no se puede descartar
    assert edad_compatible((2010,), 2024, None)                  # sin categoría, tampoco
    assert edad_compatible((2010,), 2024, "veteranos")


def test_enlaza_nombre_completo_unico():
    assert enlazar([nino(1)], [ficha(500)]) == {1: 500}


def test_un_apellido_no_se_enlaza():
    assert enlazar([nino(1, norm="GOMEZ, RAUL")], [ficha(500)]) == {}
    assert enlazar([nino(1, norm="GOMEZ, RAUL")], [ficha(500, "GOMEZ, RAUL")]) == {}


def test_dos_fichas_candidatas_no_se_enlaza():
    assert enlazar([nino(1)], [ficha(500), ficha(501)]) == {}
    # Aunque una de las dos sea de otra edad: dos fichas con el nombre ya son la duda.
    assert enlazar([nino(1)], [ficha(500), ficha(501, anios=(2010,))]) == {}


def test_edad_incompatible_no_se_enlaza():
    assert enlazar([nino(1)], [ficha(500, anios=(2014,))]) == {}
    assert enlazar([nino(1, temporada=2026, categoria="miniprebenjamin")], [ficha(500, anios=(2017,))]) == {}


def test_nombre_repetido_en_dos_clubes_no_se_enlaza():
    # Dos niños con el mismo nombre la misma temporada, en clubes que no tienen nada en común: dos niños.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"b"})], [ficha(500)]) == {}
    # El mismo club apuntado dos veces (sus equipos A y E): es el mismo niño, y los dos van a la ficha.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"a", "c"})], [ficha(500)]) == {1: 500, 2: 500}
    # El que se repite en otra temporada no estorba al de esta.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"b"}), nino(3, temporada=2025, categoria="benjamin")],
                   [ficha(500)]) == {3: 500}


def test_una_ficha_no_recibe_dos_ninos_de_la_misma_temporada():
    otro = "GOMEZ PEREZ, RAUL ANTONIO"
    f = ficha(500, RAUL, otro)                 # dos identidades de la federación, con dos nombres
    a, b = nino(1, clubes={"a"}), nino(2, norm=otro, clubes={"b"})
    assert enlazar([a, b], [f]) == {}
    # Con un club en común, sí (el mismo niño apuntado dos veces con dos grafías).
    assert enlazar([a, nino(2, norm=otro, clubes={"a"})], [f]) == {1: 500, 2: 500}
    # En temporadas distintas, también: un niño cambia de club de un año a otro.
    assert enlazar([a, nino(2, norm=otro, temporada=2025, categoria="benjamin", clubes={"b"})], [f]) \
        == {1: 500, 2: 500}


def test_el_mismo_nino_en_varias_temporadas():
    ninos = [nino(1, temporada=2023, categoria="miniprebenjamin"), nino(2, temporada=2024),
             nino(3, temporada=2025)]
    assert enlazar(ninos, [ficha(500, anios=(2018,))]) == {1: 500, 2: 500, 3: 500}


def test_el_orden_no_importa():
    ninos = [nino(1), nino(2, norm="SUAREZ DIAZ, IVAN"), nino(3, clubes={"a"}, temporada=2025),
             nino(4, clubes={"b"}, temporada=2025), nino(5, norm="MORALES RUIZ, HUGO", temporada=2023,
                                                         categoria="miniprebenjamin"),
             nino(6, norm="NAVARRO GIL, OSCAR", clubes={"x"}), nino(7, norm="NAVARRO GIL, OSCAR", clubes={"x", "y"})]
    fichas = [ficha(500), ficha(501, "SUAREZ DIAZ, IVAN"), ficha(502, "MORALES RUIZ, HUGO", anios=(2018, 2019)),
              ficha(503, "NAVARRO GIL, OSCAR", anios=())]
    esperado = enlazar(ninos, fichas)
    assert esperado == {1: 500, 2: 501, 5: 502, 6: 503, 7: 503}
    azar = random.Random(7)
    for _ in range(20):
        n, f = ninos[:], fichas[:]
        azar.shuffle(n)
        azar.shuffle(f)
        assert enlazar(n, f) == esperado
        assert list(enlazar(n, f)) == list(esperado)        # también el orden de las claves


def test_un_id_en_dos_torneos():
    # El mismo id de MyGol en el prebenjamín y en el benjamín de 2024 (juega con los mayores): los dos cuadran.
    pre, ben = nino(1), nino(1, categoria="benjamin")
    assert enlazar([pre, ben], [ficha(500, anios=(2017,))]) == {1: 500}
    # Si en uno de los dos la edad no cuadra, el id no se enlaza (el enlace es del id, no del torneo).
    assert enlazar([pre, nino(1, categoria="miniprebenjamin")], [ficha(500, anios=(2017,))]) == {}


def test_el_nombre_de_una_identidad_secundaria_vale():
    # La principal de la ficha es «GOMEZ PEREZ, RAUL ANTONIO»; el acta de otra temporada (unida) dice «RAUL».
    f = ficha(500, "GOMEZ PEREZ, RAUL ANTONIO", RAUL)
    assert enlazar([nino(1)], [f]) == {1: 500}


# ------------------------------------------------------------------ con base: los enlaces en mygol_enlaces

import json  # noqa: E402
import sqlite3  # noqa: E402

import pytest  # noqa: E402

import enlace_mygol as E  # noqa: E402
import generate_js as G  # noqa: E402
import import_mygol  # noqa: E402
from db import SCHEMA  # noqa: E402
from migrate_actas_schema import migrate as migrate_actas  # noqa: E402
from migrate_identidad import asegurar_esquema  # noqa: E402

DB_PATH = ROOT / "futbolbase.db"
quiet = lambda *a, **k: None  # noqa: E731

# La federación: benjamín en 2025-26 (grupo 1) y en 2026-27 (grupo 2).
SEED = """
INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES
  (1, '2025-2026', 2025, 2026, 0), (2, '2026-2027', 2026, 2027, 1);
INSERT INTO categories(id, name) VALUES (1, 'PREBENJAMIN'), (2, 'BENJAMIN'), (4, 'ALEVIN');
INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
  (1, 1, 2, 'BG1', 'Grupo 1', 'Gran Canaria', 'grancanaria'),
  (2, 2, 2, 'BG2', 'Grupo 2', 'Gran Canaria', 'grancanaria');
INSERT INTO teams(id, name) VALUES (1, 'Atletico Uno'), (2, 'Deportivo Dos'), (3, 'Club Tres');
"""
_ANIO = {1: 2025, 2: 2026}
# (id, nombre, fiflp_id, [(grupo, equipo, partidos), ...]). Raul: 2017 (dos temporadas de benjamín). Hugo:
# 2017 o 2018 (una). Ivan, el mismo nombre que otra ficha de otro club: dos candidatas.
FED_RAUL = (1, "GOMEZ PEREZ, RAUL", 1001, [(1, 1, 8), (2, 1, 4)])
FED_HUGO = (3, "MORALES RUIZ, HUGO", 1003, [(2, 3, 6)])
FED_IVAN = (4, "SUAREZ DIAZ, IVAN", 1004, [(2, 2, 5)])
FED_IVAN_2 = (5, "SUAREZ DIAZ, IVAN", 1005, [(2, 3, 5)])


def base_federada(*jugadores):
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=quiet)
    asegurar_esquema(conn)
    conn.executescript(SEED)
    siguiente, usados = {}, set()
    for pid, nombre, fid, filas in jugadores:
        # Un homónimo con id lleva el suyo detrás (norm_name es único), como en la base de verdad.
        norm = nombre if nombre not in usados else f"{nombre}#{fid}"
        usados.add(nombre)
        conn.execute("INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (?, ?, ?, ?)",
                     (pid, nombre, norm, fid))
        for gid, team, pj in filas:
            for _ in range(pj):
                j = siguiente.get(gid, 1)
                siguiente[gid] = j + 1
                mid = gid * 1000 + j
                conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                             "VALUES (?, ?, ?, ?, 1, 2)", (mid, gid, f"Jornada {j}", f"{j:02d}-10-{_ANIO[gid]}"))
                conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                             "VALUES (?, ?, ?, 7, 'starter', 0, 0)", (mid, team, pid))
    conn.commit()
    asegurar_esquema(conn)
    return conn


# MyGol inventado: torneos de prebenjamín 2023-24 (52) y 2024-25 (67), y de miniprebenjamín 2022-23 (32).
TORNEOS = {"32": ("2022-2023", "miniprebenjamin"), "52": ("2023-2024", "prebenjamin"),
           "67": ("2024-2025", "prebenjamin")}


def originales(carpeta, plantillas):
    """Escribe los originales y la tabla de torneos en `carpeta`. `plantillas`: {torneo: {equipo: (nombre del
    equipo, [(id, nombre, apellidos, [jugó en cada partido, ...]), ...])}}. Cada equipo juega sus partidos
    contra uno ficticio (el 999), uno por cada valor de la lista."""
    por_temporada = {}
    tabla = {}
    pid = 1
    for tid, equipos in plantillas.items():
        temporada, categoria = TORNEOS[tid]
        tabla[tid] = {"temporada": temporada, "categoria": categoria, "nombre": f"Escuela {tid}"}
        torneo = {"categoria": categoria, "nombre": f"Escuela {tid}", "equipos": {"999": "RIVAL"}, "partidos": {}}
        for eid, (nombre_equipo, ninos) in equipos.items():
            torneo["equipos"][str(eid)] = nombre_equipo
            for j in range(max(len(jugo) for *_, jugo in ninos)):
                torneo["partidos"][str(pid)] = {
                    "jornada": f"Jornada {j + 1}", "fecha": f"{temporada[:4]}-10-{j + 1:02d}T10:00:00",
                    "estado": 5, "local": int(eid), "visitante": 999, "campo": "CAMPO", "leido": "2026-11-25",
                    "jugadores": {str(eid): [[i, n, a, jugo[j]] for i, n, a, jugo in ninos if j < len(jugo)],
                                  "999": []}}
                pid += 1
        por_temporada.setdefault(temporada, {})[tid] = torneo
    for temporada, torneos in por_temporada.items():
        (carpeta / f"mygol_{temporada}_raw.json").write_text(
            json.dumps({"temporada": temporada, "torneos": torneos}, ensure_ascii=False), encoding="utf-8")
    (carpeta / "mygol_torneos.json").write_text(json.dumps(tabla, ensure_ascii=False), encoding="utf-8")
    return carpeta


def importar(conn, carpeta):
    import_mygol.importar(conn, import_mygol.raws(carpeta), tabla=carpeta / "mygol_torneos.json")


# Raul en el prebenjamín de 2023-24 (con 2017 le cuadra: 2016-2017) y en el de 2024-25 (2017-2018); Hugo en
# el miniprebenjamín de 2022-23 (2017-2018); Ivan, con dos fichas; uno de un solo apellido, que no se enlaza.
PLANTILLAS = {
    "52": {10: ("CD UNO A", [(100, "Raul", "Gomez Perez", [1, 1, 0]), (101, "Pablo", "Gomez", [1, 1, 1])])},
    "67": {11: ("CD UNO B", [(200, "Raul", "Gómez Pérez", [1, 1])]),
           12: ("UD DOS", [(201, "Ivan", "Suarez Diaz", [1])])},
    "32": {13: ("CLUB TRES", [(300, "Hugo", "Morales Ruiz", [0, 0])])},
}


def base_con_escuela(tmp_path, plantillas=PLANTILLAS):
    conn = base_federada(FED_RAUL, FED_HUGO, FED_IVAN, FED_IVAN_2)
    importar(conn, originales(tmp_path, plantillas))
    return conn


def enlaces(conn):
    return conn.execute("SELECT jugador_id, player_id FROM mygol_enlaces ORDER BY 1").fetchall()


def _tablas(conn):
    return {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_ninos_y_fichas_de_la_base(tmp_path):
    conn = base_con_escuela(tmp_path)
    ninos = {n.id: n for n in E.ninos_de(conn)}
    assert ninos[100] == Nino(id=100, norm="GOMEZ PEREZ, RAUL", temporada=2023, categoria="prebenjamin",
                              clubes=frozenset({"uno"}))       # identidad.club: sin «CD» ni la letra
    assert ninos[200].norm == "GOMEZ PEREZ, RAUL" and ninos[200].temporada == 2024
    assert ninos[300].categoria == "miniprebenjamin" and ninos[300].clubes == frozenset({"tres"})
    fichas = {f.id: f for f in E.fichas_de(conn)}
    assert fichas[1] == Ficha(id=1, nombres=frozenset({"GOMEZ PEREZ, RAUL"}), anios=(2017,))
    assert fichas[3].anios == (2017, 2018)


def test_guardar_enlaces(tmp_path):
    conn = base_con_escuela(tmp_path)
    lineas = []
    assert E.guardar_enlaces(conn, registro=lineas.append) == 3
    # Raul, sus dos temporadas (con y sin tildes); Hugo. Ni Ivan (dos fichas) ni el de un apellido.
    assert enlaces(conn) == [(100, 1), (200, 1), (300, 3)]
    assert any("3 niños" in linea and "2 fichas" in linea for linea in lineas), lineas


def test_los_enlaces_se_rehacen_enteros(tmp_path):
    conn = base_con_escuela(tmp_path)
    # Raul tiene otra identidad (sin id, unida a su ficha por el nombre).
    conn.execute("INSERT INTO players(id, full_name, norm_name, ficha_id, union_por, team_id, season_id) "
                 "VALUES (9, 'GOMEZ PEREZ, RAUL', 'GOMEZ PEREZ, RAUL@1.1', 1, 'nombre', 1, 1)")
    conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                 "VALUES (9001, 1, 'Jornada 90', '30-11-2025', 1, 2)")
    conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord) VALUES (9001, 1, 9, 7, 'sub', 0)")
    conn.commit()
    asegurar_esquema(conn)
    E.guardar_enlaces(conn, registro=quiet)
    assert enlaces(conn) == [(100, 1), (200, 1), (300, 3)]
    # El resolvedor cambia la principal de la ficha: los enlaces la siguen.
    conn.execute("UPDATE players SET ficha_id = NULL, union_por = NULL WHERE id = 9")
    conn.execute("UPDATE players SET ficha_id = 9, union_por = 'nombre' WHERE id = 1")
    conn.commit()
    E.guardar_enlaces(conn, registro=quiet)
    assert enlaces(conn) == [(100, 9), (200, 9), (300, 3)]
    # Un niño que desaparece del original se lleva su enlace.
    sin_hugo = {k: v for k, v in PLANTILLAS.items() if k != "32"}
    for p in tmp_path.glob("mygol_*"):
        p.unlink()
    importar(conn, originales(tmp_path, sin_hugo))
    assert E.guardar_enlaces(conn, registro=quiet) == 2
    assert enlaces(conn) == [(100, 9), (200, 9)]


def test_no_escribe_si_no_cambia(tmp_path):
    conn = base_con_escuela(tmp_path)
    E.guardar_enlaces(conn, registro=quiet)
    antes = conn.total_changes
    assert E.guardar_enlaces(conn, registro=quiet) == 3
    assert conn.total_changes == antes and not conn.in_transaction


def test_sin_tablas_de_mygol(tmp_path):
    conn = base_federada(FED_RAUL)
    assert E.ninos_de(conn) == []
    assert E.guardar_enlaces(conn, registro=quiet) == 0
    assert "mygol_enlaces" not in _tablas(conn)
    # Vacías: ningún enlace (y la tabla, vacía).
    import_mygol.crear_tablas(conn)
    assert E.guardar_enlaces(conn, registro=quiet) == 0
    assert enlaces(conn) == []
    # Una base sin las identidades (sin players.fiflp_id): ninguna ficha.
    vieja = sqlite3.connect(":memory:")
    vieja.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT, norm_name TEXT)")
    assert E.fichas_de(vieja) == [] and E.guardar_enlaces(vieja, registro=quiet) == 0


def test_lo_de_fuera_de_la_web_no_mueve_los_enlaces(tmp_path, monkeypatch):
    """Hasta que la web enseñe infantil (parte E2), sus actas están en la base pero no mueven ningún enlace:
    Raul (1001) juega además en infantil de 2026-27 (su año, con eso, sería otro y su escuela no cuadraría) y
    un niño nuevo de infantil (2003) se llama como Hugo (sería una segunda ficha de su nombre)."""
    import categorias
    conn = base_con_escuela(tmp_path)
    E.guardar_enlaces(conn, registro=quiet)
    antes = enlaces(conn)
    assert antes == [(100, 1), (200, 1), (300, 3)]
    anios = {f.id: f.anios for f in E.fichas_de(conn)}
    conn.executescript("""
      INSERT INTO categories(id, name) VALUES (5, 'INFANTIL');
      INSERT INTO groups(id, season_id, category_id, code, name, phase, island) VALUES
        (3, 2, 5, 'INF1G1', 'Grupo 1', 'Primera GC', 'grancanaria');
      INSERT INTO players(id, full_name, norm_name, fiflp_id) VALUES (6, 'MORALES RUIZ, HUGO', 'MORALES RUIZ, HUGO#2003', 2003);
    """)
    for j in range(1, 11):
        conn.execute("INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id) "
                     "VALUES (?, 3, ?, ?, 1, 2)", (3000 + j, f"Jornada {j}", f"{j:02d}-11-2026"))
        conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                     "VALUES (?, 1, 1, 7, 'starter', 0, 0)", (3000 + j,))
        conn.execute("INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, goals, ord) "
                     "VALUES (?, 1, 6, 9, 'starter', 0, 1)", (3000 + j,))
    conn.commit()
    asegurar_esquema(conn)
    assert {f.id: f.anios for f in E.fichas_de(conn)} == anios
    E.guardar_enlaces(conn, registro=quiet)
    assert enlaces(conn) == antes
    # Con infantil en la web, sí: el año de Raul y la segunda ficha de Hugo cuentan.
    monkeypatch.setattr(categorias, "EN_WEB", categorias.EN_WEB + ("INFANTIL",))
    assert {f.id: f.anios for f in E.fichas_de(conn)}[1] != anios[1]
    E.guardar_enlaces(conn, registro=quiet)
    assert (300, 3) not in enlaces(conn)

def test_tablas_de_mygol_desaparecidas(tmp_path):
    """Si las tablas mygol_* ya no están (una base que vuelve atrás), los enlaces viejos no se quedan."""
    conn = base_con_escuela(tmp_path)
    E.guardar_enlaces(conn, registro=quiet)
    for t in import_mygol.TABLAS:
        conn.execute(f"DROP TABLE {t}")
    conn.commit()
    assert E.guardar_enlaces(conn, registro=quiet) == 0
    assert enlaces(conn) == []


def test_base_real(tmp_path):
    """Sobre una copia de la base real con los originales de verdad importados en la copia: las cifras que se
    midieron al decidir la regla (docs/mygol.md), con margen; ningún enlace a una identidad que no sea la
    principal de su ficha; ninguna ficha con dos niños de la misma temporada sin club en común. Y el año con
    el que se mira la edad es el que publica el generador sin la escuela."""
    if not DB_PATH.exists():
        pytest.skip("futbolbase.db no está")
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn = sqlite3.connect(str(tmp_path / "fb.db"))
    src.backup(conn)
    src.close()
    import_mygol.importar(conn)
    # La base de una pasada del bot ya trae sus enlaces (enlazar_mygol va antes de las pruebas): se quitan de la
    # copia, porque lo que se compara es el año SIN la escuela. guardar_enlaces, abajo, los rehace.
    conn.execute("DROP TABLE IF EXISTS mygol_enlaces")
    conn.commit()
    fichas = E.fichas_de(conn)
    datos = G._datos_fichas(conn, confirmados={})
    anios = {f.id: f.anios for f in fichas}
    assert all(anios[p] == a for p, (a, _) in datos["anios"].items())
    n = E.guardar_enlaces(conn, registro=quiet)
    filas = enlaces(conn)
    fichas_enlazadas = {p for _, p in filas}
    print(f"\n  base real: {n} niños de MyGol enlazados con {len(fichas_enlazadas)} fichas")
    assert 1400 <= n <= 1700 and 900 <= len(fichas_enlazadas) <= 1100
    principales = {p for (p,) in conn.execute("SELECT id FROM players WHERE ficha_id IS NULL")}
    assert fichas_enlazadas <= principales
    ninos = E.ninos_de(conn)
    por_ficha = {}
    for nino_ in ninos:
        if nino_.id in dict(filas):
            por_ficha.setdefault((dict(filas)[nino_.id], nino_.temporada), []).append(nino_)
    assert not [k for k, grupo in por_ficha.items() if E._choca(grupo)]
