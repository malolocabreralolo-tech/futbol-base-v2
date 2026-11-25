"""La federación de mentira de las pruebas de las tandas del histórico (y de quien la quiera): un sitio falso
detrás de una página falsa de Playwright, con un reloj falso, que se comporta como la federación medida.

No empieza por «test_»: pytest no la recoge; las pruebas la importan (`from federacion_falsa import …`: conftest
pone esta carpeta en sys.path). Nunca pide nada a ninguna web.

Lo que imita (docs/freno-2026-11.md y el docstring de fiflp_carga):
  - el CUPO de octubre: `cupo` documentos por IP y después una página vacía (un 200 con el cuerpo vacío, que
    el navegador pinta como FRENO_HTML) durante el siguiente de `bloqueos` (segundos desde la primera vacía;
    None, ya no vuelve en esa ejecución); el bloqueo escala dentro de la misma IP (el 1.º, el 2.º… de
    `bloqueos`; pasados todos, el último). Los sondeos durante el bloqueo no lo alargan ni gastan del cupo
    siguiente. Como Quota de test_fiflp_carga. Sin `cupo`, sirve todo: lo de hoy en Azure (desde el 21/10);
  - el RUNNER RECHAZADO: con `rechaza=True` (y nube="aws": así lo ve Federacion), todo vacío desde la primera
    petición, siempre, también con otra IP;
  - la PÁGINA MUERTA: una Pagina(html="") viene vacía siempre, mientras la federación sirve las demás;
  - la que NO EXISTE: sitio(url) None responde 404 (una página de error con contenido: no vacía);
  - otra ejecución de GitHub, con su IP: .ip_nueva() vuelve a empezar el cupo y sus bloqueos.
Cada petición (page.goto) cuesta `coste` segundos del reloj; las esperas de Federacion (su `sleep`) y las de
los lectores (wait_for_timeout) también avanzan el reloj."""
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fiflp_carga  # noqa: E402
from fiflp_render import FLATTEN_JS  # noqa: E402

# Lo que el navegador pinta de una respuesta vacía (la del freno, la de una página muerta, about:blank).
FRENO_HTML = "<html><head></head><body></body></html>"
NO_EXISTE_HTML = "<html><head><title>404 Not Found</title></head><body><h1>Not Found</h1></body></html>"


class Reloj:
    """El reloj de la prueba: clock() para Federacion (y su plazo), sleep(s) suma `s` y lo apunta en `dormido`,
    wall() es la hora UTC (el 25/11/2026 a las 03:00 cuando t vale 1000)."""

    def __init__(self, t=1000.0):
        self.t = t
        self.dormido = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.dormido.append(round(s, 2))
        self.t += s

    def wall(self):
        return datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc) + timedelta(seconds=self.t - 1000)


@dataclass
class Pagina:
    """Una página del sitio falso. `html`, lo que da content() ("" es una página muerta: vacía siempre);
    `opciones`, por nombre de desplegable ("competicion", "grupo", "jornada"), sus [(valor, texto)] en orden;
    `datos`, lo que dan parse_standings y parse_matches del RaspadorFalso con ella cargada."""
    html: str = "<html><body>x</body></html>"
    opciones: dict = field(default_factory=dict)
    datos: object = None


class _Respuesta:
    def __init__(self, status):
        self.status = status


# Las formas en que los descargadores y el bot leen un desplegable (`o` es cada <option>). En orden: los pares
# y los objetos antes que los valores sueltos.
_PARES = re.compile(r"\[\s*o\.value\s*,\s*o\.text")
_VALOR_TEXTO = re.compile(r"\(\s*\{\s*value\s*:\s*o\.value\s*,\s*text\s*:")
_ID_NOMBRE = re.compile(r"\(\s*\{\s*id\s*:\s*o\.value\s*,\s*name\s*:")
_VALORES = re.compile(r"\.map\(\s*o\s*=>\s*o\.value\s*\)")
_SELECT = re.compile(r"""select\[name=["'](\w+)["']\]""")
_SIN_VACIOS = re.compile(r"""o\.value\s*&&\s*o\.value\s*!==\s*['"]0['"]""")


class _PaginaFalsa:
    """Lo que los lectores usan de una página de Playwright, sobre el sitio de una FederacionFalsa."""

    def __init__(self, federacion):
        self._f = federacion
        self.cargada = None               # la Pagina servida en la última carga (None: vacía, 404 o nada aún)
        self._html = FRENO_HTML           # about:blank
        self._vacia = True

    # La carga: la única petición a la «federación».
    def goto(self, url, wait_until=None, timeout=None):
        f = self._f
        f.pedidas.append(url)
        pagina = f.sitio(url)
        frena = f._frena()
        f.reloj.t += f.coste
        self.cargada = None
        if frena:
            self._html, self._vacia, status = FRENO_HTML, True, 200
        elif pagina is None:
            self._html, self._vacia, status = NO_EXISTE_HTML, False, 404
        elif pagina.html == "":
            self._html, self._vacia, status = FRENO_HTML, True, 200
        else:
            self._html, self._vacia, status = pagina.html, False, 200
            self.cargada = pagina
        return _Respuesta(status)

    def evaluate(self, js, arg=None):
        if js == fiflp_carga.EMPTY_JS:
            return self._vacia
        if FLATTEN_JS in js:              # fiflp_render.flatten: nada que aplanar
            return 0
        if 'img[src*="/Clubes/"]' in js:  # fetch_fiflp_goleadores.CRESTS_JS: sin escudos
            return {}
        return self._desplegable(js)

    def _desplegable(self, js):
        """Un guion que lee un desplegable, en su forma: valores, pares, {value, text} o {id, name}. Sin el
        valor vacío ni el "0" si el guion los quita; con el texto en mayúsculas si lo pide (toUpperCase).
        Lo que no es ninguno de ellos, None (lo que da un guion que no devuelve nada)."""
        nombre = _SELECT.search(js)
        if nombre is None:
            return None
        opciones = list((self.cargada.opciones if self.cargada else {}).get(nombre.group(1), []))
        if _SIN_VACIOS.search(js):
            opciones = [(v, t) for v, t in opciones if v and v != "0"]
        mayus = ".toUpperCase()" in js
        opciones = [(str(v), t.strip().upper() if mayus else t.strip()) for v, t in opciones]
        if _PARES.search(js):
            return [[v, t] for v, t in opciones]
        if _VALOR_TEXTO.search(js):
            return [{"value": v, "text": t} for v, t in opciones]
        if _ID_NOMBRE.search(js):
            return [{"id": v, "name": t} for v, t in opciones]
        if _VALORES.search(js):
            return [v for v, _ in opciones]
        return None

    def content(self):
        return self._html

    def wait_for_function(self, js, arg=None, timeout=None, polling=None):
        return True

    def wait_for_load_state(self, state=None, timeout=None):
        return None

    def wait_for_timeout(self, ms):
        self._f.reloj.t += ms / 1000

    def query_selector(self, selector):
        return None

    def query_selector_all(self, selector):
        return []

    @property
    def frames(self):
        return []

    def is_closed(self):
        return False


class RaspadorFalso:
    """El raspador que Federacion envuelve (como fetch_fiflp_2425): su BASE y sus lectores, que dan los `datos`
    de la Pagina cargada (una copia; sin ninguna cargada, o vacía, [])."""
    BASE = "https://www.fiflp.com/pnfg/NPcd"

    @staticmethod
    def _datos(page):
        cargada = getattr(page, "cargada", None)
        datos = cargada.datos if cargada is not None else None
        return copy.deepcopy(datos) if datos is not None else []

    @staticmethod
    def parse_standings(page):
        return RaspadorFalso._datos(page)

    @staticmethod
    def parse_matches(page):
        return RaspadorFalso._datos(page)


class FederacionFalsa:
    """La federación de mentira: `sitio(url)` da la Pagina de cada URL (None: no existe). Lo que pidió cada
    página, en `pedidas` (las URL, en orden); el registro de las Federacion de .fed(), en `dicho`."""

    def __init__(self, sitio: Callable[[str], "Pagina | None"], reloj: Reloj, cupo: "int | None" = None,
                 bloqueos: "tuple[float | None, ...]" = (300,), coste: float = 2.0, nube: str = "azure",
                 rechaza: bool = False):
        self.sitio, self.reloj, self.cupo, self.bloqueos = sitio, reloj, cupo, tuple(bloqueos)
        self.coste, self.nube, self.rechaza = coste, nube, rechaza
        self.pedidas, self.dicho = [], []
        self.ip_nueva()

    def ip_nueva(self):
        """Otra ejecución (otro runner, otra IP): el cupo vuelve a empezar, y sus bloqueos también."""
        self._cuenta = 0                  # documentos servidos desde el último bloqueo
        self._desde = None                # cuándo empezó el bloqueo en curso
        self.bloqueados = []              # cuándo empezó cada bloqueo de esta IP

    def _frena(self):
        """¿Viene vacía la petición que empieza ahora (reloj.t)? Como Quota de test_fiflp_carga."""
        if self.rechaza:
            return True
        if self.cupo is None:
            return False
        t = self.reloj.t
        if self._desde is not None:
            dura = self.bloqueos[min(len(self.bloqueados), len(self.bloqueos)) - 1]
            if dura is None or t < self._desde + dura:
                return True
            self._desde, self._cuenta = None, 0
        if self._cuenta >= self.cupo:
            self._desde = t
            self.bloqueados.append(t)
            return True
        self._cuenta += 1
        return False

    def page(self):
        return _PaginaFalsa(self)

    def fed(self, **kw):
        """Una fiflp_carga.Federacion sobre esta federación: el RaspadorFalso, 7 s entre peticiones, la nube de
        la falsa, su reloj (clock, sleep y wall) y su registro (`dicho`). Lo demás, `kw`."""
        kw.setdefault("interval", 7.0)
        kw.setdefault("cloud", self.nube)
        kw.setdefault("log", self.dicho.append)
        fed = fiflp_carga.Federacion(RaspadorFalso(), clock=self.reloj.clock, sleep=self.reloj.sleep,
                                     wall=self.reloj.wall, **kw)
        # La pausa de cortesía de los lectores (Federacion.delay: FIFLP_DELAY, ~1,25 s con time.sleep de verdad),
        # en el reloj de la falsa y sin apuntarla en `dormido`: las pruebas no esperan de verdad, y lo dormido
        # sigue siendo solo lo que decide Federacion (el intervalo, el freno, los reintentos).
        def delay(extra=0):
            self.reloj.t += 1.25 + extra
        fed.delay = delay
        return fed
