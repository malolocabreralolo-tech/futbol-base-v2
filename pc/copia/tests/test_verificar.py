import os
import sqlite3
from pathlib import Path

from conftest import crear_base
from copia.verificar import TABLAS, comprobar


def _modificar(db: Path, sql: str) -> None:
    con = sqlite3.connect(db)
    try:
        con.executescript(sql)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


def test_base_sana(tmp_path):
    r = comprobar(crear_base(tmp_path / "a.db"))
    assert r.ok and r.motivos == ()
    assert r.recuentos["matches"] == 40 and set(r.recuentos) == set(TABLAS)


def test_vigila_los_cuerpos_tecnicos(tmp_path):       # match_staff_all, parte de las actas
    assert len(TABLAS) == 10 and "match_staff_all" in TABLAS
    db = crear_base(tmp_path / "a.db")
    assert comprobar(db).recuentos["match_staff_all"] == 1
    _modificar(db, "DELETE FROM match_staff_all")
    assert "match_staff_all está vacía" in comprobar(db).motivos
    _modificar(db, "DROP TABLE match_staff_all")
    assert "falta la tabla match_staff_all" in comprobar(db).motivos
    assert "mengua: match_staff_all 100 → 1" in comprobar(crear_base(tmp_path / "b.db"), anterior={"match_staff_all": 100}).motivos


def test_no_deja_ficheros_al_lado(tmp_path):
    comprobar(crear_base(tmp_path / "a.db"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.db"]


def test_corrupta(tmp_path):          # bytes 4096-8192 a 0xff
    db = crear_base(tmp_path / "a.db")
    datos = bytearray(db.read_bytes())
    datos[4096:8192] = b"\xff" * 4096
    db.write_bytes(bytes(datos))
    r = comprobar(db)
    assert not r.ok and r.motivos[0].startswith(("integridad:", "no se puede abrir:"))


def test_truncada(tmp_path):          # recortada a 1000 bytes
    db = crear_base(tmp_path / "a.db")
    os.truncate(db, 1000)
    r = comprobar(db)
    assert not r.ok and r.recuentos == {}
    assert len(r.motivos) == 1 and r.motivos[0].startswith("no se puede abrir: ")


def test_no_es_sqlite(tmp_path):      # un fichero de texto
    db = tmp_path / "a.db"
    db.write_text("esto no es una base de datos\n", encoding="utf-8")
    r = comprobar(db)
    assert not r.ok and r.recuentos == {}
    assert len(r.motivos) == 1 and r.motivos[0].startswith("no se puede abrir: ")


def test_falta_tabla(tmp_path):       # DROP TABLE scorers
    db = crear_base(tmp_path / "a.db")
    _modificar(db, "DROP TABLE scorers")
    r = comprobar(db)
    assert not r.ok and "falta la tabla scorers" in r.motivos
    assert "scorers" not in r.recuentos and r.recuentos["matches"] == 40


def test_tabla_vacia(tmp_path):       # DELETE FROM goals
    db = crear_base(tmp_path / "a.db")
    _modificar(db, "DELETE FROM goals")
    r = comprobar(db)
    assert not r.ok and "goals está vacía" in r.motivos
    assert r.recuentos["goals"] == 0


def test_clave_foranea(tmp_path):     # un partido con group_id=999999 metido con foreign_keys=OFF
    db = crear_base(tmp_path / "a.db")
    _modificar(db, "PRAGMA foreign_keys=OFF; INSERT INTO matches (group_id) VALUES (999999)")
    r = comprobar(db)
    assert not r.ok and "claves foráneas: 1 filas" in r.motivos


def test_mengua(tmp_path):
    r = comprobar(crear_base(tmp_path / "a.db", partidos=40), anterior={"matches": 100})
    assert not r.ok and "mengua: matches 100 → 40" in r.motivos


def test_mengua_en_el_margen(tmp_path):
    assert comprobar(crear_base(tmp_path / "a.db", partidos=98), anterior={"matches": 100}).ok
    assert not comprobar(crear_base(tmp_path / "b.db", partidos=97), anterior={"matches": 100}).ok


def test_varios_motivos_a_la_vez(tmp_path):
    db = crear_base(tmp_path / "a.db", partidos=40)
    _modificar(db, "DROP TABLE scorers; DELETE FROM goals; PRAGMA foreign_keys=OFF; INSERT INTO matches (group_id) VALUES (999999)")
    r = comprobar(db, anterior={"matches": 100, "players": 50})
    assert not r.ok and r.motivos == (
        "claves foráneas: 1 filas",
        "goals está vacía",
        "falta la tabla scorers",
        "mengua: matches 100 → 41",
        "mengua: players 50 → 1",
    )


def test_ignora_lo_anterior_de_tablas_que_no_se_vigilan(tmp_path):
    r = comprobar(crear_base(tmp_path / "a.db"), anterior={"matches": 40, "otra": 1000, "match_staff": 500})
    assert r.ok and r.motivos == () and set(r.recuentos) == set(TABLAS)


def test_crecer_no_es_mengua(tmp_path):
    assert comprobar(crear_base(tmp_path / "a.db"), anterior={"matches": 10}).ok
