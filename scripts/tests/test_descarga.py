"""La base completa para descargar (scripts/descarga.py): ¿toca rehacerla hoy?, el ZIP con la base tal cual y su
apunte en data-health.json. Bases e informes de mentira, en tmp_path; nunca la base ni el informe del repositorio."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import descarga  # noqa: E402
import piezas  # noqa: E402

HOY = date(2026, 11, 25)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_constantes():
    assert descarga.TAG == "base-completa"
    assert descarga.ASSET == "futbolbase.zip"
    assert descarga.URL == ("https://github.com/malolocabreralolo-tech/futbol-base-v2/releases/download/"
                            "base-completa/futbolbase.zip")


def test_toca(tmp_path):
    informe = tmp_path / "data-health.json"
    assert descarga.toca(informe, HOY) is True, "sin informe"
    informe.write_text("no es json")
    assert descarga.toca(informe, HOY) is True, "un informe que no se lee"
    informe.write_text(json.dumps({"version": 1, "groups": {}}))
    assert descarga.toca(informe, HOY) is True, "sin descarga"
    informe.write_text(json.dumps({"descarga": {"url": descarga.URL, "fecha": "2026-11-24", "bytes": 5}}))
    assert descarga.toca(informe, HOY) is True, "la de ayer"
    informe.write_text(json.dumps({"descarga": "2026-11-25"}))
    assert descarga.toca(informe, HOY) is True, "una descarga que no se entiende"
    informe.write_text(json.dumps({"descarga": {"url": descarga.URL, "fecha": "2026-11-25", "bytes": 5}}))
    assert descarga.toca(informe, HOY) is False, "la de hoy"


def _base_en_wal(path):
    """Una base en WAL, como la del bot, con filas que siguen en el -wal (la conexión, abierta: al cerrarla SQLite
    lo volcaría), una tabla sin INTEGER PRIMARY KEY con huecos en sus rowid (los que un VACUUM renumera) y su
    user_version. Devuelve la conexión abierta."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.executescript("CREATE TABLE equipos(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);"
                      "CREATE TABLE goles(partido INTEGER NOT NULL, lado TEXT CHECK(lado IN ('h','a')), nombre TEXT);"
                      "CREATE INDEX goles_partido ON goles(partido);"
                      "PRAGMA user_version=7;")
    con.executemany("INSERT INTO equipos(nombre) VALUES (?)", [(f"EQUIPO {i}",) for i in range(50)])
    con.executemany("INSERT INTO goles VALUES (?, ?, ?)", [(i, "h", "GOMEZ PEREZ, RAUL") for i in range(400)])
    con.execute("DELETE FROM goles WHERE partido < 100")
    con.execute("DELETE FROM equipos WHERE id > 45")
    con.commit()
    return con


def test_preparar(tmp_path):
    original = tmp_path / "futbolbase.db"
    con = _base_en_wal(original)
    try:
        assert Path(f"{original}-wal").stat().st_size > 0, "la prueba quiere filas en el -wal"
        antes = _sha(original)
        zip_path = tmp_path / "salida" / "futbolbase.zip"
        zip_path.parent.mkdir()
        n = descarga.preparar(original, zip_path)
        assert n == zip_path.stat().st_size > 0
        assert _sha(original) == antes, "la base no se escribe"
        with zipfile.ZipFile(zip_path) as z:
            assert z.namelist() == ["futbolbase.db"]
            info = z.getinfo("futbolbase.db")
            assert info.compress_type == zipfile.ZIP_DEFLATED
            z.extract("futbolbase.db", tmp_path / "fuera")
        fuera = tmp_path / "fuera" / "futbolbase.db"
        cabecera = fuera.read_bytes()[:100]
        assert cabecera[18] == 1 and cabecera[19] == 1, "en modo DELETE: se abre en cualquier sitio"
        # Se abre en solo lectura sin -wal ni -shm, y es la base entera (con lo que estaba en el -wal).
        abierta = sqlite3.connect(f"file:{fuera}?mode=ro", uri=True)
        try:
            assert abierta.execute("SELECT count(*) FROM goles").fetchone() == (300,)
            assert abierta.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        finally:
            abierta.close()
        assert piezas.comparar(original, fuera) == []
        # Ni temporales junto al ZIP ni junto a la base.
        assert sorted(p.name for p in zip_path.parent.iterdir()) == ["futbolbase.zip"]
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    finally:
        con.close()


def test_preparar_sin_base_no_deja_nada(tmp_path):
    zip_path = tmp_path / "futbolbase.zip"
    with pytest.raises(Exception):
        descarga.preparar(tmp_path / "no-esta.db", zip_path)
    assert not zip_path.exists()
    assert not (tmp_path / "no-esta.db").exists(), "no crea una base vacía"


def test_apuntar(tmp_path):
    informe = tmp_path / "data-health.json"
    antes = {"version": 1, "season": "2026-2027", "groups": {"A1": {"status": "ok"}}, "base": {"mb": 85, "limite": 100}}
    informe.write_text(json.dumps(antes))
    zip_path = tmp_path / "futbolbase.zip"
    zip_path.write_bytes(b"x" * 1234)
    descarga.apuntar(zip_path, informe, HOY)
    despues = json.loads(informe.read_text())
    assert despues.pop("descarga") == {"url": descarga.URL, "fecha": "2026-11-25", "bytes": 1234}
    assert despues == antes, "lo demás, igual"
    assert descarga.toca(informe, HOY) is False


def test_la_orden(tmp_path):
    """La orden del paso de update.yml: toca (0 si toca, 1 si no), preparar y apuntar, sobre el informe del
    repositorio de mentira (descarga.py y lo que importa, copiados)."""
    raiz = tmp_path / "repo"
    (raiz / "scripts").mkdir(parents=True)
    for nombre in ("descarga.py", "source_health.py", "escritura.py", "portal_config.py", "categorias.py"):
        (raiz / "scripts" / nombre).write_bytes((ROOT / "scripts" / nombre).read_bytes())
    original = raiz / "futbolbase.db"
    _base_en_wal(original).close()
    zip_path = tmp_path / "runner" / "futbolbase.zip"
    zip_path.parent.mkdir()

    def orden(*args):
        return subprocess.run([sys.executable, "scripts/descarga.py", *args], cwd=raiz, capture_output=True,
                              text=True, timeout=60)

    assert orden("toca").returncode == 0
    hecho = orden("preparar", str(zip_path))
    assert hecho.returncode == 0, hecho.stderr
    assert orden("apuntar", str(zip_path)).returncode == 0
    apunte = json.loads((raiz / "data-health.json").read_text())["descarga"]
    assert apunte["url"] == descarga.URL and apunte["bytes"] == zip_path.stat().st_size
    assert orden("toca").returncode == 1
    assert orden().returncode == 2


@pytest.mark.skipif(os.environ.get("PIEZAS_REAL") != "1",
                    reason="solo con PIEZAS_REAL=1 (como test_piezas_real.py: la base de verdad, en una copia)")
def test_la_base_real_se_descarga_entera(tmp_path):
    """Con la base de verdad, la descargada es la base fila a fila, rowid incluidos (VACUUM INTO renumeraba los de
    fp_goals). La de la raíz se copia sin abrirla: nunca se escribe."""
    real = ROOT / "futbolbase.db"
    if not real.is_file():
        pytest.fail("PIEZAS_REAL=1 y no está futbolbase.db en la raíz")
    copia = tmp_path / "w.db"
    shutil.copyfile(real, copia)
    wal = Path(f"{real}-wal")
    if wal.is_file() and wal.stat().st_size:
        shutil.copyfile(wal, Path(f"{copia}-wal"))
    zip_path = tmp_path / "futbolbase.zip"
    n = descarga.preparar(copia, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        assert z.namelist() == ["futbolbase.db"]
        z.extract("futbolbase.db", tmp_path / "fuera")
    assert piezas.comparar(copia, tmp_path / "fuera" / "futbolbase.db") == []
    assert n < copia.stat().st_size
