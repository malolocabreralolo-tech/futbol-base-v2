"""TDD — el importador de la liga de escuelas de MyGol (scripts/import_mygol.py).

Base en memoria y originales inventados en tmp_path (ningún nombre de verdad)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import import_mygol as I  # noqa: E402

TABLAS = ("mygol_torneos", "mygol_equipos", "mygol_jugadores", "mygol_partidos", "mygol_participaciones")


def partido(pid_local=1, pid_visitante=2, jornada="Jornada 1", fecha="2026-10-24T09:00:00", estado=5,
            jugadores=None, leido="2026-11-25"):
    p = {"jornada": jornada, "fecha": fecha, "estado": estado, "local": pid_local, "visitante": pid_visitante,
         "campo": "CAMPO 1"}
    if jugadores is not None:
        p["jugadores"] = jugadores
        p["leido"] = leido
    return p


def original_2627():
    return {"temporada": "2026-2027", "torneos": {"96": {
        "categoria": "benjamin", "nombre": "BENJAMIN ESCUELA 2026/2027",
        "equipos": {"1": "EQUIPO UNO A", "2": "EQUIPO DOS"},
        "partidos": {
            "100": partido(jugadores={"1": [[10, "Nombre1", "Apellido1 Apellido2", 1],
                                            [11, "Nombre2", "Apellido2 Apellido3", 0]],
                                      "2": [[20, "Nombre3", "Apellido3 Apellido4", 1]]}),
            "101": partido(2, 1, "Jornada 2", "2026-11-07T10:00:00", 1),          # aún sin leer
        }}}}


def original_2526():
    return {"temporada": "2025-2026", "torneos": {"86": {
        "categoria": "benjamin", "nombre": "Benjamín Escuela 2025/2026",
        "equipos": {"5": "EQUIPO CINCO"},
        "partidos": {"50": partido(5, 6, fecha="2026-03-15T11:00:00",
                                   jugadores={"5": [[30, "Nombre4", "Apellido4 Apellido5", 1]], "6": []})}}}}


def escribir(carpeta, raw):
    path = Path(carpeta) / f"mygol_{raw['temporada']}_raw.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def filas(conn, tabla):
    return conn.execute(f"SELECT * FROM {tabla} ORDER BY 1, 2").fetchall()


def todo(conn):
    return {t: filas(conn, t) for t in TABLAS}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def test_importa(tmp_path, conn):
    escribir(tmp_path, original_2526())
    escribir(tmp_path, original_2627())
    rutas = I.raws(tmp_path)
    assert [p.name for p in rutas] == ["mygol_2025-2026_raw.json", "mygol_2026-2027_raw.json"]
    cuentas = I.importar(conn, rutas)
    assert cuentas == {"mygol_torneos": 2, "mygol_equipos": 3, "mygol_jugadores": 4, "mygol_partidos": 3,
                       "mygol_participaciones": 4}
    assert conn.execute("SELECT * FROM mygol_torneos WHERE id = 96").fetchone() == (
        96, "2026-2027", "benjamin", "BENJAMIN ESCUELA 2026/2027")
    assert conn.execute("SELECT * FROM mygol_equipos WHERE id = 1").fetchone() == (1, "EQUIPO UNO A")
    assert conn.execute("SELECT * FROM mygol_jugadores WHERE id = 10").fetchone() == (
        10, "Nombre1", "Apellido1 Apellido2", "APELLIDO1 APELLIDO2, NOMBRE1")
    assert conn.execute("SELECT * FROM mygol_partidos WHERE id = 100").fetchone() == (
        100, 96, "Jornada 1", "2026-10-24T09:00:00", 5, 1, 2, "CAMPO 1")
    assert filas(conn, "mygol_participaciones")[:3] == [(50, 30, 5, 1), (100, 10, 1, 1), (100, 11, 1, 0)]


def test_partido_sin_leer_entra_sin_participaciones(tmp_path, conn):
    escribir(tmp_path, original_2627())
    I.importar(conn, I.raws(tmp_path))
    assert conn.execute("SELECT * FROM mygol_partidos WHERE id = 101").fetchone() == (
        101, 96, "Jornada 2", "2026-11-07T10:00:00", 1, 2, 1, "CAMPO 1")
    assert conn.execute("SELECT count(*) FROM mygol_participaciones WHERE partido_id = 101").fetchone() == (0,)


def test_categoria_sin_decidir(tmp_path, conn):
    raw = original_2526()
    raw["torneos"]["86"]["categoria"] = None
    escribir(tmp_path, raw)
    I.importar(conn, I.raws(tmp_path))
    assert conn.execute("SELECT categoria FROM mygol_torneos WHERE id = 86").fetchone() == (None,)


def test_la_tabla_de_torneos_manda(tmp_path, conn):
    """La categoría que se decide después en mygol_torneos.json entra sin volver a bajar la temporada."""
    raw = original_2526()
    raw["torneos"]["86"]["categoria"] = None
    escribir(tmp_path, raw)
    tabla = tmp_path / "mygol_torneos.json"
    tabla.write_text(json.dumps({"86": {"temporada": "2025-2026", "categoria": "benjamin", "nombre": "B 25/26"}}),
                     encoding="utf-8")
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=lambda *a: None) is True
    assert conn.execute("SELECT * FROM mygol_torneos").fetchall() == [(86, "2025-2026", "benjamin", "B 25/26")]
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=lambda *a: None) is False
    tabla.write_text(json.dumps({"86": {"temporada": "2025-2026", "categoria": "alevin", "nombre": "B 25/26"}}),
                     encoding="utf-8")
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=lambda *a: None) is True
    assert conn.execute("SELECT categoria FROM mygol_torneos").fetchone() == ("alevin",)


def test_nombres_raros(tmp_path, conn):
    raw = original_2627()
    raw["torneos"]["96"]["partidos"]["100"]["jugadores"] = {
        "1": [[10, "Nombre1", "", 1],                              # sin apellidos
              [11, "  Nombre2   Compuesto ", "  Apellido5    Apellido6  ", 1],   # espacios de más
              [12, "ñómbre", "ápellido ültimo", 0]],              # minúsculas con tildes
        "2": [[13, "", "Apellido7", 1]]}                           # sin nombre de pila
    escribir(tmp_path, raw)
    I.importar(conn, I.raws(tmp_path))
    norm = dict(conn.execute("SELECT id, norm FROM mygol_jugadores"))
    assert norm == {10: "NOMBRE1", 11: "APELLIDO5 APELLIDO6, NOMBRE2 COMPUESTO",
                    12: "APELLIDO ULTIMO, NOMBRE", 13: "APELLIDO7"}
    # Lo que se guarda como nombre y apellidos es lo del original, tal cual.
    assert conn.execute("SELECT nombre, apellidos FROM mygol_jugadores WHERE id = 11").fetchone() == (
        "  Nombre2   Compuesto ", "  Apellido5    Apellido6  ")


def test_idempotente(tmp_path, conn):
    escribir(tmp_path, original_2526())
    escribir(tmp_path, original_2627())
    I.importar(conn, I.raws(tmp_path))
    primera = todo(conn)
    I.importar(conn, I.raws(tmp_path))
    assert todo(conn) == primera


def test_refleja_lo_que_desaparece(tmp_path, conn):
    escribir(tmp_path, original_2627())
    I.importar(conn, I.raws(tmp_path))
    assert conn.execute("SELECT count(*) FROM mygol_participaciones WHERE partido_id = 100").fetchone() == (3,)
    raw = original_2627()
    del raw["torneos"]["96"]["partidos"]["100"]
    escribir(tmp_path, raw)
    I.importar(conn, I.raws(tmp_path))
    assert conn.execute("SELECT id FROM mygol_partidos").fetchall() == [(101,)]
    assert conn.execute("SELECT count(*) FROM mygol_participaciones").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM mygol_jugadores").fetchone() == (0,)


def test_nombre_mas_reciente(tmp_path, conn):
    # Un equipo con dos nombres en dos originales: el de la temporada más reciente.
    viejo = original_2526()
    viejo["torneos"]["86"]["equipos"]["1"] = "EQUIPO UNO (NOMBRE VIEJO)"
    escribir(tmp_path, viejo)
    # Un jugador con dos nombres dentro de una temporada: el del partido más reciente, lea en el orden que lea.
    raw = original_2627()
    partidos = raw["torneos"]["96"]["partidos"]
    partidos["102"] = partido(fecha="2026-11-21T09:00:00",
                              jugadores={"1": [[10, "Nombre1", "Apellido1 Corregido", 1]], "2": []})
    partidos["99"] = partido(fecha="2026-11-14T09:00:00",          # id menor, fecha intermedia
                              jugadores={"1": [[10, "Nombre1", "Apellido1 Intermedio", 1]], "2": []})
    escribir(tmp_path, raw)
    I.importar(conn, I.raws(tmp_path))
    assert conn.execute("SELECT nombre FROM mygol_equipos WHERE id = 1").fetchone() == ("EQUIPO UNO A",)
    assert conn.execute("SELECT apellidos, norm FROM mygol_jugadores WHERE id = 10").fetchone() == (
        "Apellido1 Corregido", "APELLIDO1 CORREGIDO, NOMBRE1")


def test_transaccion(tmp_path, conn):
    escribir(tmp_path, original_2627())
    I.importar(conn, I.raws(tmp_path))
    antes = todo(conn)
    malo = original_2627()
    malo["torneos"]["96"]["partidos"]["100"]["jugadores"]["1"].append([12, "Nombre9"])     # fila incompleta
    escribir(tmp_path, malo)
    with pytest.raises(ValueError) as e:
        I.importar(conn, I.raws(tmp_path))
    assert "100" in str(e.value) and "Nombre9" not in str(e.value)       # dice el partido, no el nombre
    assert todo(conn) == antes
    # El mismo partido en dos torneos: tampoco.
    doble = original_2627()
    doble["torneos"]["97"] = {"categoria": "miniprebenjamin", "nombre": "M", "equipos": {},
                              "partidos": {"100": partido()}}
    escribir(tmp_path, doble)
    with pytest.raises(ValueError):
        I.importar(conn, I.raws(tmp_path))
    assert todo(conn) == antes
    # Y uno que solo falla al escribir, a mitad (después de vaciar y rellenar las otras tablas).
    otro = original_2627()
    otro["torneos"]["96"]["equipos"]["3"] = "EQUIPO TRES"
    escribir(tmp_path, otro)
    conn.execute("""CREATE TRIGGER falla BEFORE INSERT ON mygol_participaciones
                    BEGIN SELECT RAISE(ABORT, 'falla a mitad'); END""")
    with pytest.raises(sqlite3.DatabaseError):
        I.importar(conn, I.raws(tmp_path))
    conn.execute("DROP TRIGGER falla")
    assert todo(conn) == antes


def test_importar_si_cambia(tmp_path, conn):
    path = escribir(tmp_path, original_2627())
    mensajes = []
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=mensajes.append) is True
    assert conn.execute("SELECT count(*) FROM mygol_partidos").fetchone() == (2,)
    assert any("mygol" in m.lower() for m in mensajes)
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=mensajes.append) is False
    path.write_bytes(path.read_bytes() + b" ")                       # un byte más
    assert I.importar_si_cambia(conn, raiz=tmp_path, registro=mensajes.append) is True
    assert conn.execute("SELECT path FROM raw_imports").fetchall() == [("mygol",)]
    assert I.huella(I.raws(tmp_path)) != I.huella([])


def test_sin_originales(tmp_path, conn):
    assert I.raws(tmp_path) == []
    I.importar_si_cambia(conn, raiz=tmp_path, registro=lambda *a: None)
    assert all(filas(conn, t) == [] for t in TABLAS)
    assert I.importar(conn, []) == {t: 0 for t in TABLAS}


def test_la_tabla_de_torneos_del_repositorio():
    """La tabla revisada a mano (scripts/mygol_torneos.json): todos los torneos con su categoría decidida, y
    todas las categorías con su ventana de nacimiento (nacimiento.VENTANA), que es lo que cuenta para el año."""
    from nacimiento import VENTANA
    tabla = json.loads((ROOT / "scripts" / "mygol_torneos.json").read_text(encoding="utf-8"))
    assert [t for t, fila in tabla.items() if fila.get("categoria") is None] == []
    assert {fila["categoria"] for fila in tabla.values()} <= set(VENTANA)
    decididos = {"32": "miniprebenjamin", "33": "prebenjamin", "34": "benjamin",
                 "51": "benjamin", "52": "prebenjamin", "53": "miniprebenjamin"}
    assert {t: tabla[t]["categoria"] for t in decididos} == decididos
    assert tabla["32"]["nombre"] == "Miniprebenjamín Escuela 2022/2023"
    assert tabla["51"]["nombre"] == "Benjamín Escuela 2023/2024"
