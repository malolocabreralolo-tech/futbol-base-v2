"""La base de verdad partida y vuelta a montar (scripts/piezas.py): montar∘partir es la identidad con todas sus
filas. Solo con PIEZAS_REAL=1 (tarda unos segundos y necesita la base del repositorio). La base de la raíz se
copia a tmp_path sin abrirla: nunca se escribe."""
import os
import shutil
from pathlib import Path

import pytest

import piezas

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "futbolbase.db"

pytestmark = pytest.mark.skipif(os.environ.get("PIEZAS_REAL") != "1",
                                reason="solo con PIEZAS_REAL=1 (parte y monta la base de verdad, en una copia)")


@pytest.fixture(scope="module")
def copia(tmp_path_factory):
    if not REAL.is_file():
        pytest.fail("PIEZAS_REAL=1 y no está futbolbase.db en la raíz")
    carpeta = tmp_path_factory.mktemp("real")
    destino = carpeta / "w.db"
    shutil.copyfile(REAL, destino)
    # Lo que quedara sin volcar en el -wal de la raíz es parte de la base: va con ella.
    wal = Path(f"{REAL}-wal")
    if wal.is_file() and wal.stat().st_size:
        shutil.copyfile(wal, Path(f"{destino}-wal"))
    return destino


def test_la_base_real_se_parte_y_se_monta_igual(copia):
    base = copia.parent / "base"
    r = piezas.partir(copia, base)
    assert r["cambiadas"] == {} and r["borradas"] == [] and r["intactas"] == []
    assert piezas.COMUN in r["creadas"] and len(r["creadas"]) > 1
    montada = copia.parent / "m.db"
    filas = piezas.montar(base, montada)
    assert filas["appearances"] > 0
    assert piezas.comparar(copia, montada) == []
    mayor = max(p.stat().st_size for p in base.glob("*.db"))
    assert mayor < piezas.AVISO_MB * piezas.MB


def test_la_base_real_no_cambia_al_volver_a_partir(copia):
    base = copia.parent / "base"
    if not (base / piezas.MANIFIESTO).exists():
        piezas.partir(copia, base)
    antes = {p.name: p.read_bytes() for p in base.iterdir()}
    r = piezas.partir(copia, base)
    assert r["creadas"] == [] and r["cambiadas"] == {} and r["borradas"] == []
    assert sorted(r["intactas"]) == sorted(p for p in antes if p.endswith(".db"))
    assert {p.name: p.read_bytes() for p in base.iterdir()} == antes
