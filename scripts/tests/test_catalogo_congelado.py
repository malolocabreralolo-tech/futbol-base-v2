"""Las pruebas no leen el catálogo de la federación que actualiza discover-fiflp.yml
(scripts/fiflp_comps_catalog.json), sino una copia congelada (fixtures/fiflp_comps_catalog.json).

Si leyeran el catálogo vivo, una competición nueva en la federación pondría pruebas en rojo: el bot
(update.yml) ejecuta las suites antes de publicar, así que se quedaría sin publicar datos hasta
activarla.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
VIVO = "fiflp_comps_catalog.json"


def test_ninguna_prueba_lee_el_catalogo_vivo():
    """El bot ejecuta estas pruebas antes de publicar: si leyeran el catálogo que actualiza
    discover-fiflp.yml, una competición nueva de la federación lo dejaría sin publicar."""
    culpables = []
    for ruta in sorted(TESTS.glob("test_*.py")):
        if ruta.name == "test_catalogo_congelado.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if VIVO in linea and "fixtures" not in linea:
                culpables.append(f"{ruta.name}:{n}")
    assert culpables == []


def test_las_pruebas_pasan_con_un_catalogo_vivo_distinto(tmp_path):
    """Con una competición inventada añadida al catálogo vivo, las suites del catálogo siguen en verde."""
    # Solo el código (scripts/ pesa 150 MB por los raws): los .py de scripts/ y de las pruebas, la
    # fixture, src/config.js (source_health lee la temporada) y los workflows que lee
    # test_alevin_descargas.py; el catálogo vivo, con la inventada.
    (tmp_path / "scripts" / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    for ruta in [*ROOT.glob("scripts/*.py"), *ROOT.glob("scripts/tests/*.py"), TESTS / "fixtures" / VIVO,
                 ROOT / "src" / "config.js"]:
        shutil.copy(ruta, tmp_path / ruta.relative_to(ROOT))
    shutil.copytree(ROOT / ".github" / "workflows", tmp_path / ".github" / "workflows")
    catalogo = json.loads((ROOT / "scripts" / VIVO).read_text(encoding="utf-8"))
    inventada = {"id": "99999999", "name": "LIGA BENJAMIN INVENTADA"}
    catalogo["2026-2027"]["all"].append(inventada)
    catalogo["2026-2027"]["relevant"].append(inventada)
    (tmp_path / "scripts" / VIVO).write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")

    env = {clave: valor for clave, valor in os.environ.items() if clave != "PYTHONPATH"}   # nada del árbol de verdad
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "scripts/tests/test_competiciones_nuevas.py", "scripts/tests/test_alevin_descargas.py"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]
    assert " passed" in run.stdout and "failed" not in run.stdout, run.stdout[-3000:]
