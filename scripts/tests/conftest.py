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


@pytest.fixture(autouse=True, scope="session")
def _sin_tope_del_historico():
    """Lo mismo con historico.yml: pone en el env del job el tope del día y las esperas del freno
    (HISTORICO_PAGINAS_DIA y HISTORICO_ESPERAS, de las variables del repositorio), y su paso de pruebas los
    hereda. Con el tope subido a 4.000 (26/11/2026), las pruebas que cuentan con el de siempre («de 2.000
    páginas») salieron rojas en la prueba del propio carril, y el encargo se quedó sin promover. Como en local:
    sin ellas; las que las miran las ponen ellas (monkeypatch.setenv o env=…)."""
    mp = pytest.MonkeyPatch()
    mp.delenv("HISTORICO_PAGINAS_DIA", raising=False)
    mp.delenv("HISTORICO_ESPERAS", raising=False)
    yield
    mp.undo()


@pytest.fixture(scope="session")
def bases_reales(tmp_path_factory):
    """La base real tras el final de una pasada, sin y con infantil, cadete y juvenil leídos (base_mayores.bases_reales:
    con el EN_WEB de antes del paso E2-D2 y, la de las mayores, también con el de después; lo fabricado, siempre sobre
    la base sin lo que el bot ya haya leído de las nuevas): una vez por sesión para las pruebas que las comparan.
    Salta sin futbolbase.db. Nadie las cambia: cada prueba copia la suya."""
    import base_mayores
    origen = Path(__file__).resolve().parents[2] / "futbolbase.db"
    if not origen.exists():
        pytest.skip("futbolbase.db no está")
    return base_mayores.bases_reales(origen, tmp_path_factory.mktemp("bases_reales"))


# El mundo que suponen las pruebas que miran qué activa el bot o qué ve la web: el de antes de los pasos D3-D6 del
# director (docs/categorias-mayores.md) y del paso E2-D2, con infantil, cadete y juvenil sin activar, el alevín de
# Lanzarote y Fuerteventura fuera y la web con prebenjamín, benjamín y alevín. Esas pruebas lo FIJAN ellas (fixture
# categorias_de_antes, o fijar_categorias) en vez de leer lo que diga scripts/categorias.py: así cada paso del
# director es de verdad una línea en categorias.py y una en la única prueba que comprueba lo que hay hoy
# (test_categorias.test_lo_que_se_activa_y_lo_que_se_ve_no_cambia), y la puerta de pruebas del bot no se pone en
# rojo por pruebas que suponían el mundo de antes. Lo que cambia de verdad con cada paso lo prueba prueba_mayores.py
# con el paso ya dado (--con-cambios). Una prueba que mire la base real o los data-*.js no puede fijar EN_WEB para
# lo que lee (lo escribió la pasada con el de categorias.py): tiene que valer con los dos, o fijarlo solo para lo
# que ella misma vuelve a calcular (las fichas de su copia, la web que ella genera).
ACTIVABLES_DE_ANTES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
ALEVIN_ISLAS_DE_ANTES = False
# EN_WEB de antes del paso E2-D2 y el de después (las seis): los de base_mayores, que también los fija (con_en_web)
# para lo que calcula en las bases compartidas.
from base_mayores import EN_WEB_DE_ANTES, EN_WEB_SEIS  # noqa: E402


def _modulos_categorias():
    """categorias y, si está cargada, su otra copia (scripts.categorias: algunos importadores cargan la segunda)."""
    import categorias
    return [categorias] + [m for m in (sys.modules.get("scripts.categorias"),) if m and m is not categorias]


def fijar_en_web(mp, en_web):
    """Solo categorias.EN_WEB, con el MonkeyPatch `mp`: «antes» (EN_WEB_DE_ANTES), «seis» (EN_WEB_SEIS) o una tupla.
    Los módulos que lo usan lo leen al llamar (vista_web, migrate_identidad, generate_js, enlace_mygol,
    migrate_categories): el parche les llega, también a los procesos de paralelo.en_paralelo (fork)."""
    valor = {"antes": EN_WEB_DE_ANTES, "seis": EN_WEB_SEIS}.get(en_web, en_web) if isinstance(en_web, str) else en_web
    for modulo in _modulos_categorias():
        mp.setattr(modulo, "EN_WEB", tuple(valor))


def fijar_categorias(mp, activables=ACTIVABLES_DE_ANTES, alevin_islas=ALEVIN_ISLAS_DE_ANTES, en_web=EN_WEB_DE_ANTES):
    """categorias.ACTIVABLES, categorias.ALEVIN_ISLAS y categorias.EN_WEB a lo que supone la prueba, con el
    MonkeyPatch `mp`, en las dos copias del módulo si las hay."""
    for modulo in _modulos_categorias():
        mp.setattr(modulo, "ACTIVABLES", tuple(activables))
        mp.setattr(modulo, "ALEVIN_ISLAS", alevin_islas)
    fijar_en_web(mp, en_web)


@pytest.fixture
def categorias_de_antes(monkeypatch):
    """ACTIVABLES, ALEVIN_ISLAS y EN_WEB como antes de los pasos D3-D6 y E2-D2, durante la prueba (ver arriba)."""
    fijar_categorias(monkeypatch)


@pytest.fixture
def fijar_web(monkeypatch):
    """fijar_web("antes") o fijar_web("seis"): categorias.EN_WEB durante la prueba, sin tocar lo demás. Para las
    que comprueban lo que hace la web (las fichas, el generador, la copia de la web) con el EN_WEB de hoy, con el
    del paso E2-D2 o con los dos (parametrizadas)."""
    return lambda en_web: fijar_en_web(monkeypatch, en_web)


@pytest.fixture(scope="module")
def categorias_de_antes_modulo():
    """Lo mismo para todo un módulo, también para sus fixtures de módulo (que se montan antes que las de cada
    prueba): pytestmark = pytest.mark.usefixtures("categorias_de_antes_modulo")."""
    mp = pytest.MonkeyPatch()
    fijar_categorias(mp)
    yield
    mp.undo()
