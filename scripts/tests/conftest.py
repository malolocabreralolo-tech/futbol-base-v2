"""Las pruebas no leen la tabla de nombres revisados del proyecto (scripts/fiflp_team_names.json):
describe la base de verdad, no las de prueba. La que la necesita pone la suya (test_fed_names.py).
Tampoco escriben los originales de las actas del bot (actas_bot) en scripts/: cada una, en su carpeta.
Esta carpeta va al final de sys.path para que las pruebas importen sus piezas comunes por su nombre (la
federación de mentira: `from federacion_falsa import …`); al final, para no tapar ningún módulo de scripts/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _sin_tabla_de_nombres(tmp_path_factory, monkeypatch):
    import fiflp_names
    modules = [fiflp_names] + [m for m in (sys.modules.get("scripts.fiflp_names"),) if m]
    for module in modules:
        monkeypatch.setattr(module, "FED_NAMES_PATH", str(tmp_path_factory.getbasetemp() / "sin-tabla.json"))
        module.fed_alias.cache_clear()
    yield
    for module in modules:
        module.fed_alias.cache_clear()


@pytest.fixture(autouse=True, scope="session")
def _originales_fuera_de_scripts(tmp_path_factory):
    """update_fiflp.import_actas guarda el original de cada acta que importa (actas_bot): en las pruebas,
    nunca en los actas_bot_*.jsonl de verdad. De sesión, para que lo vean también los fixtures de módulo (las
    semanas simuladas de test_bot_pasada_corta), que se montan antes que los de cada prueba."""
    mp = pytest.MonkeyPatch()
    mp.setenv("ACTAS_BOT_DIR", str(tmp_path_factory.mktemp("actas_bot_sesion")))
    yield
    mp.undo()


@pytest.fixture(autouse=True, scope="session")
def _runner_de_azure(tmp_path_factory):
    """fiflp_carga.Federacion, sin darle la nube, la lee de la máquina (nube: SYS_VENDOR), y fuera de Azure un
    freno en la primera página acaba la pasada sin esperarlo. Las pruebas no dependen de dónde corren (en
    local, «otra»; tests.yml cae en Azure o en AWS): todas, como en un runner de Azure, donde se midió el
    freno. Las que miran otra nube la dan (cloud=…) o cambian SYS_VENDOR. De sesión, como la de los
    originales: las semanas simuladas de los fixtures de módulo crean su Federacion antes que cada prueba."""
    import fiflp_carga
    vendor = tmp_path_factory.mktemp("dmi") / "sys_vendor"
    vendor.write_text("Microsoft Corporation\n")
    mp = pytest.MonkeyPatch()
    mp.setattr(fiflp_carga, "SYS_VENDOR", str(vendor))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _originales_aparte(_originales_fuera_de_scripts, tmp_path_factory, monkeypatch):
    """Y cada prueba, en su carpeta: lo que guarda una no lo ve la siguiente."""
    monkeypatch.setenv("ACTAS_BOT_DIR", str(tmp_path_factory.mktemp("actas_bot")))


@pytest.fixture(autouse=True, scope="session")
def _sin_carril_del_job():
    """update.yml pone FIFLP_CATS en el env del job (la ven todos sus pasos, también el de las pruebas): en una
    pasada del carril de las mayores llegaría aquí con infantil,cadete,juvenil, y una prueba que no la mira daría
    lo del carril y no lo de siempre (y la puerta de pruebas del carril, en rojo). Como en local: sin ella; las que
    la miran la ponen ellas (monkeypatch.setenv). De sesión, como las de arriba."""
    mp = pytest.MonkeyPatch()
    mp.delenv("FIFLP_CATS", raising=False)
    yield
    mp.undo()


@pytest.fixture(scope="session")
def bases_reales(tmp_path_factory):
    """La base real tras el final de una pasada, sin y con infantil, cadete y juvenil leídos (base_mayores.bases_reales):
    una vez por sesión para las pruebas que las comparan. Salta sin futbolbase.db. Nadie las cambia: cada prueba
    copia la suya."""
    import base_mayores
    origen = Path(__file__).resolve().parents[2] / "futbolbase.db"
    if not origen.exists():
        pytest.skip("futbolbase.db no está")
    return base_mayores.bases_reales(origen, tmp_path_factory.mktemp("bases_reales"))
