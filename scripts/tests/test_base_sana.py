"""La comprobación de la base antes de subirla (scripts/base_sana.py): integridad, referencias, el WAL
volcado al fichero principal y el tamaño. Bases de mentira, creadas en cada prueba; nunca la del repositorio."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import base_sana  # noqa: E402
import source_health  # noqa: E402

MB = source_health.MB


def _base(path, filas=300):
    """Una base en WAL, como la del bot, con dos tablas ligadas por una clave ajena y varias páginas."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("CREATE TABLE madre(id INTEGER PRIMARY KEY, texto TEXT);"
                      "CREATE TABLE hija(id INTEGER PRIMARY KEY, madre_id INTEGER REFERENCES madre(id), texto TEXT);"
                      "CREATE INDEX hija_madre ON hija(madre_id);")
    con.executemany("INSERT INTO madre VALUES (?, ?)", [(i, f"madre {i} " * 20) for i in range(filas)])
    con.executemany("INSERT INTO hija VALUES (?, ?, ?)", [(i, i % filas, f"hija {i} " * 20) for i in range(filas)])
    con.commit()
    con.close()
    return Path(path)


def _wal(db):
    return Path(f"{db}-wal")


def test_base_buena_ok(tmp_path):
    db = _base(tmp_path / "futbolbase.db")
    antes = hashlib.sha1(db.read_bytes()).hexdigest()
    r = base_sana.comprobar(db)
    assert r == {"ok": True, "motivos": [], "bytes": db.stat().st_size, "aviso": False}
    assert hashlib.sha1(db.read_bytes()).hexdigest() == antes, "una base buena no cambia de bytes"
    assert not _wal(db).exists() or _wal(db).stat().st_size == 0


def test_referencia_rota_no_ok(tmp_path):
    db = _base(tmp_path / "futbolbase.db")
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO hija VALUES (100000, 999999, 'sin madre')")
    con.commit()
    con.close()
    r = base_sana.comprobar(db)
    assert r["ok"] is False
    assert r["motivos"] == ["la base de datos tiene referencias rotas: 1 filas"]


def _pisa_pagina(db, numero):
    """La página `numero` (desde 1) del fichero, con ceros."""
    con = sqlite3.connect(db)
    tam = con.execute("PRAGMA page_size").fetchone()[0]
    paginas = con.execute("PRAGMA page_count").fetchone()[0]
    con.close()
    assert numero <= paginas
    with open(db, "r+b") as f:
        f.seek((numero - 1) * tam)
        f.write(b"\0" * tam)


INTEGRIDAD = "la base de datos no pasa la comprobación de integridad: "


def test_fichero_danado_no_ok(tmp_path):
    db = _base(tmp_path / "futbolbase.db")
    _pisa_pagina(db, 3)
    r = base_sana.comprobar(db)
    assert r["ok"] is False
    assert len(r["motivos"]) == 1 and r["motivos"][0].startswith(INTEGRIDAD), r["motivos"]
    assert 0 < len(r["motivos"][0]) - len(INTEGRIDAD) <= 200


def test_fichero_que_no_es_sqlite_no_ok(tmp_path):
    db = tmp_path / "futbolbase.db"
    db.write_text("esto no es una base de datos\n" * 200, encoding="utf-8")
    r = base_sana.comprobar(db)
    assert r["ok"] is False
    assert len(r["motivos"]) == 1 and r["motivos"][0].startswith(INTEGRIDAD), r["motivos"]


VACIA = "la base de datos está vacía"


@pytest.mark.parametrize("caso", ["cero-bytes", "sin-tablas"])
def test_base_vacia_no_ok(tmp_path, caso):
    """Un fichero de 0 bytes o una base sin ninguna tabla pasan integrity_check (SQLite las ve sanas), pero subir
    eso borraría la web: no está bien."""
    db = tmp_path / "futbolbase.db"
    if caso == "cero-bytes":
        db.write_bytes(b"")
    else:
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA user_version = 1")
        con.commit()
        con.close()
    r = base_sana.comprobar(db)
    assert r["ok"] is False
    assert r["motivos"] == [VACIA]
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "base_sana.py"), "--db", str(db)],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.splitlines() == [VACIA], done.stdout


def test_sin_fichero_no_ok_y_no_lo_crea(tmp_path):
    db = tmp_path / "futbolbase.db"
    r = base_sana.comprobar(db)
    assert r["ok"] is False and r["motivos"][0].startswith(INTEGRIDAD), r["motivos"]
    assert not db.exists()


def test_vuelca_el_wal(tmp_path):
    """Una escritura confirmada que sigue en el -wal (la conexión no se ha cerrado): git no sube el -wal
    (.gitignore), así que comprobar la vuelca al fichero principal."""
    db = _base(tmp_path / "futbolbase.db")
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("INSERT INTO madre VALUES (5000, 'sin volcar')")
    con.commit()
    try:
        assert _wal(db).stat().st_size > 0
        r = base_sana.comprobar(db)
        assert r["ok"] is True, r["motivos"]
        assert not _wal(db).exists() or _wal(db).stat().st_size == 0
        # El fichero principal solo, como lo sube git: ya trae la fila.
        solo = tmp_path / "solo.db"
        solo.write_bytes(db.read_bytes())
        otra = sqlite3.connect(solo)
        assert otra.execute("SELECT texto FROM madre WHERE id = 5000").fetchone() == ("sin volcar",)
        otra.close()
    finally:
        con.close()


def test_un_lector_que_no_suelta_deja_datos_sin_volcar(tmp_path):
    """Si otra conexión tiene una lectura abierta, el volcado no puede acabar: lo dice, sin excepción."""
    db = _base(tmp_path / "futbolbase.db")
    escritor = sqlite3.connect(db, isolation_level=None)
    lector = sqlite3.connect(db, isolation_level=None)
    try:
        lector.execute("BEGIN")
        lector.execute("SELECT count(*) FROM madre").fetchone()
        escritor.execute("INSERT INTO madre VALUES (5000, 'sin volcar')")
        r = base_sana.comprobar(db)
        assert r["ok"] is False
        assert "quedan datos sin volcar a la base (-wal)" in r["motivos"], r["motivos"]
    finally:
        lector.close()
        escritor.close()


def test_aviso_y_parada_por_tamano(tmp_path, monkeypatch):
    db = _base(tmp_path / "futbolbase.db")
    size = db.stat().st_size
    monkeypatch.setattr(base_sana, "AVISO_MB", (size + 1) / MB)
    monkeypatch.setattr(base_sana, "PARADA_MB", (size + 2) / MB)
    r = base_sana.comprobar(db)
    assert (r["ok"], r["aviso"], r["motivos"]) == (True, False, [])
    monkeypatch.setattr(base_sana, "AVISO_MB", (size - 1) / MB)
    r = base_sana.comprobar(db)
    assert (r["ok"], r["aviso"], r["motivos"]) == (True, True, [])
    monkeypatch.setattr(base_sana, "PARADA_MB", (size - 1) / MB)
    monkeypatch.setattr(base_sana, "AVISO_MB", (size - 2) / MB)
    r = base_sana.comprobar(db)
    assert r["ok"] is False and r["aviso"] is True
    assert r["motivos"] == [f"la base de datos ocupa {size // MB} MB y GitHub no admite más de 100"]


def test_los_umbrales():
    """GitHub rechaza ficheros de 100 MB: se para antes, y se avisa bastante antes."""
    assert (base_sana.AVISO_MB, base_sana.PARADA_MB, source_health.GITHUB_MB) == (80, 95, 100)
    assert MB == 1024 * 1024


def test_cli_sale_con_1_y_dice_el_motivo(tmp_path):
    db = _base(tmp_path / "futbolbase.db")
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "base_sana.py"), "--db", str(db)],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    _pisa_pagina(db, 3)
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "base_sana.py"), "--db", str(db)],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 1, done.stdout + done.stderr
    lineas = done.stdout.splitlines()
    assert len(lineas) == 1 and lineas[0].startswith(INTEGRIDAD), done.stdout


def _sha(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def test_cli_con_salud_solo_escribe_si_la_base_esta_bien(tmp_path, monkeypatch):
    """--salud deja el tamaño en data-health.json (set_base) solo si la base está bien; mal, ni lo toca (de
    eso se encarga el paso de diagnóstico de update.yml)."""
    real = ROOT / "data-health.json"
    real_antes = _sha(real) if real.exists() else None
    report = tmp_path / "data-health.json"
    report.write_text(json.dumps({"version": 1, "runHealth": {"ok": True}}), encoding="utf-8")
    monkeypatch.setattr(source_health, "REPORT_PATH", report)
    db = _base(tmp_path / "futbolbase.db")
    size = db.stat().st_size
    monkeypatch.setattr(base_sana, "AVISO_MB", (size - 1) / MB)
    assert base_sana.main(["--db", str(db), "--salud"]) == 0
    assert json.loads(report.read_text())["base"] == {"mb": size // MB, "limite": 100}
    monkeypatch.setattr(base_sana, "AVISO_MB", 80)
    _pisa_pagina(db, 3)
    antes = report.read_text()
    assert base_sana.main(["--db", str(db), "--salud"]) == 1
    assert report.read_text() == antes, "con la base mal, --salud no toca el informe"
    _base(tmp_path / "otra.db")
    assert base_sana.main(["--db", str(tmp_path / "otra.db"), "--salud"]) == 0
    assert "base" not in json.loads(report.read_text())
    assert (_sha(real) if real.exists() else None) == real_antes, "nunca el data-health.json del repositorio"


def test_salud_escribe_y_quita_la_clave(tmp_path):
    report = tmp_path / "data-health.json"
    inicial = {"version": 1, "season": "2026-2027", "runHealth": {"ok": True}, "groups": {}}
    report.write_text(json.dumps(inicial), encoding="utf-8")
    viejo = 1_700_000_000_000_000_000

    source_health.set_base(85 * MB + 123, True, path=report)
    assert json.loads(report.read_text()) == {**inicial, "base": {"mb": 85, "limite": 100}}
    os.utime(report, ns=(viejo, viejo))
    source_health.set_base(85 * MB + 456, True, path=report)              # el mismo entero: sin cambio
    assert report.stat().st_mtime_ns == viejo, "sin cambio no reescribe"
    source_health.set_base(86 * MB, True, path=report)
    assert json.loads(report.read_text())["base"] == {"mb": 86, "limite": 100}

    source_health.set_base(40 * MB, False, path=report)
    assert json.loads(report.read_text()) == inicial
    os.utime(report, ns=(viejo, viejo))
    source_health.set_base(40 * MB, False, path=report)
    assert report.stat().st_mtime_ns == viejo, "sin la clave y sin aviso, no reescribe"


def test_salud_sin_informe(tmp_path):
    """Sin data-health.json: sin aviso no lo crea; con aviso, solo con la clave."""
    report = tmp_path / "data-health.json"
    source_health.set_base(40 * MB, False, path=report)
    assert not report.exists()
    source_health.set_base(81 * MB, True, path=report)
    assert json.loads(report.read_text()) == {"base": {"mb": 81, "limite": 100}}


def test_base_sana_no_escribe_por_su_cuenta():
    """Ni open() en escritura ni write_text: el informe lo escribe source_health.set_base (escribir_atomico)."""
    texto = (ROOT / "scripts" / "base_sana.py").read_text(encoding="utf-8")
    for prohibido in ("write_text", "write_bytes", "escribir_atomico", "open("):
        assert prohibido not in texto, prohibido
