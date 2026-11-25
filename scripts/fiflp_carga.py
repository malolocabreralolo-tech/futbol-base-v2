"""fiflp_carga.py — Cuándo está lista una página de la federación y cuánto espera el bot entre una y otra.

Con esperas fijas (2,5 s tras cada carga y una pausa de 2-3,5 s, las de fetch_fiflp_2425.goto) la
pasada no cabe en el job con todos los grupos de la temporada. Aquí:
  - la carga espera a lo que el lector necesita, con tope (FIFLP_READY_MS, 5 s por defecto): las
    hojas de estilo de la federación (de ellas salen las cifras que pintan los ::before y que
    materializa el aplanado, fiflp_render.FLATTEN_JS) y, en las páginas cuyo desplegable rellena su
    JS (jornadas, grupos, competiciones), una opción de verdad. Lo demás llega entero en el HTML,
    que ya está leído al acabar domcontentloaded. Si lo esperado no llega, se sigue igual: los
    lectores saben qué hacer con una página vacía;
  - la pausa entre peticiones, educada pero menor: FIFLP_DELAY segundos («1-1.5» por defecto, con
    jitter);
  - una página de error de la federación (un 5xx, como el 503 de Apache cuando bloquea, o un 4xx, como
    un 429 o un 403) no es una página cargada: se reintenta como una que no carga y, con BLOCKED_AFTER seguidas, el bot
    deja de pedirle más en esa pasada (Federacion.blocked). Un 503 o un 429 («no disponible»,
    «demasiadas peticiones») es además señal del freno, como una página vacía: la federación, no la
    página. Un 500 (u otro 5xx), un 403 (u otro 4xx) o un corte de conexión, no: puede ser la URL;
  - el RITMO: entre dos peticiones, al menos FIFLP_MIN_INTERVAL segundos (DEFAULT_INTERVAL, 7), por
    rápido que cargue cada página. Por cortesía: el freno no depende del ritmo (abajo);
  - si el navegador se cierra (Chromium caído), no es la federación: ni reintentos ni esperas, y nada
    más en esa pasada (Federacion.closed);
  - lo que se REPITE va a la red (fiflp_render.goto): la federación da sus documentos con
    «Cache-Control: private, max-age=300», y con la caché HTTP la misma URL antes de 5 min saldría de
    la caché sin pedirle nada. Toda URL que el navegador ya pidió (los reintentos de goto, la otra página
    de Federacion._serving, los sondeos del freno, la recarga del calendario y la clasificación otra vez
    de update_fiflp.scrape_group) pide su documento a la red; los scripts y las hojas, de la caché.

EL FRENO (medido con freno-fiflp.yml, scripts/freno_experimento.py: tres runners de GitHub
a la vez, cada uno con su IP, pidiendo documentos distintos con la caché y fiflp_launch_args):
  - la federación sirve ~15 DOCUMENTOS POR IP y después una página VACÍA (un 200 con «content-length: 0»
    de Apache, que el navegador pinta como «<html><head></head><body></body></html>»; la normal llega con
    «Cache-Control: private, max-age=300» y por trozos) durante ~2-6 min, casi siempre ~5:
      a 7 s por página: 15 páginas, vuelve a los 304 s; 16, vuelve a los 364 s; 17 (y seguía 242 s después);
      a 15 s: 15, vuelve a los 304 s; 15, vuelve a los 122 s; 15 (y seguía 181 s después);
      a 30 s: 15 (7,5 min), vuelve a los 303 s; y 20 sin frenar hasta acabar el plazo;
  - EL RITMO NO IMPORTA (15 páginas a 7, a 15 y a 30 s): el cupo es de páginas. En pasadas reales frena
    tras ~10-12 páginas, y ralentizar al reanudar no sirve de nada;
  - la misma página 10 s después, vacía; y en un CONTEXTO NUEVO (otra sesión, otras cookies, la misma IP),
    vacía: el cupo es POR IP, no por sesión. No se intenta saltarlo (ni varias IPs, ni proxies, ni
    runners en paralelo, ni otra identidad): se trabaja DENTRO del cupo;
  - un sondeo de una página cada 60 s durante el bloqueo no lo alarga (vuelve a ~300 s igual).
Por eso (Federacion):
  - una página vacía es el freno a la primera, SIN reintento (uno a los 60 s sale vacío siempre: un
    minuto perdido, y una petición), si la federación tampoco sirve OTRA página (_serving: la última que
    cargó o, sin ninguna aún, la de competiciones de la temporada). Si la sirve, no es el freno: es esta
    página, que no carga (una página muerta: `dead`), sin espera ni señal del freno, y la pasada sigue.
    Desde el 21/11/2026 hay actas cuya página sale vacía siempre; tomadas por el freno, cada pasada se
    quedaba sondeándolas 9-12 min (docs/freno-2026-11.md);
  - la ESPERA del freno: FIFLP_BRAKE_PAUSE_MIN (4) minutos sin pedir nada y después LA MISMA página cada
    FIFLP_BRAKE_PROBE_S (60) segundos (un sondeo: una sola petición, al documento de la red y no al de la
    caché, porque la URL se repite; si no carga, vacía o no, también la otra página: si esa carga, la
    federación ya sirve y esta página no, y la espera acaba), hasta que sirva; cada uno, si cabe en el
    plazo con BRAKE_ROOM para leer algo después. Con un tope por freno, FIFLP_BRAKE_MAX_MIN (20) minutos
    desde la página vacía: si no vuelve, nada más en esa pasada (`blocked`). Con lo medido (~5 min)
    vuelve en el 2.º o el 3.º sondeo (a los ~300 o ~360 s); el de 122 s, en el 1.º; y el tope deja 17
    sondeos (en una pasada real un freno seguía a los 11 min);
  - UNA espera por pasada (BRAKE_PAUSES = 1, FIFLP_BRAKE_PAUSES): el segundo freno acaba la pasada. En
    pasadas reales el bloqueo ESCALA dentro de una pasada (el 1.º ~300 s, el 2.º ~900 s, el 3.º más que el
    plazo) y cada ejecución de GitHub, con su IP nueva, vuelve a empezar con ~5 min: esperar el 2.º son
    15 min por ~15 páginas, y una pasada nueva (cada 2 h, y cada hora en las ventanas de partidos:
    reloj.yml) las da con 5. Así cada pasada son ~15 páginas, la espera de ~5 min, ~15 más y nada
    después, en ~9 min (update_fiflp.DEADLINE_SECONDS, 16, es para una pasada sin freno). Con 0, ninguna
    espera (al frenar se acaba la pasada), y con «sin», sin tope;
  - SIN RALENTIZAR al reanudar: el cupo no es de ritmo, y cada segundo de más es tiempo de plazo
    perdido;
  - EL RUNNER RECHAZADO (desde el 13/11/2026, docs/freno-2026-11.md): GitHub pone cerca de la mitad de los
    jobs en AWS, y la federación les sirve vacío desde la primera petición, siempre (183 de 183; en Azure,
    0 de 187), días después y con cualquier IP de AWS: no es un cupo y no se pasa esperando. Si frena antes
    de servir ninguna página en la pasada y el runner no es de Azure (nube(): el fabricante de la
    máquina), ni la espera ni los sondeos: nada más en esa pasada (`refused_runner`). No se relanza la
    pasada para que caiga en Azure: sería esquivar el bloqueo (decisión del dueño, pendiente);
  - lo demás, igual: un freno no es un error (update_fiflp.run_passes), un 503 o un 429 es señal del
    freno sin más (sin preguntar por otra página), una racha de URLs muertas mientras la federación sirve
    otra página no lo es (también cuenta en `dead`), el navegador cerrado tampoco, y ninguna página empieza
    pasado el plazo, contando la espera del intervalo;
  - el coste: en un freno de verdad, una petición más al frenar y una más por sondeo (la otra página). El
    experimento de octubre midió que los sondeos no alargan el bloqueo.
No cambia cómo se aplana ni cómo se lee el HTML: solo cuándo. Lo usa el bot (update_fiflp,
Federacion).

LAS TANDAS DEL HISTÓRICO (fetch_fiflp_actas, _goleadores, _detalle: las temporadas pasadas) leen con
para_tanda: la misma Federacion y la misma detección que el bot (una página vacía solo es el freno si la
federación tampoco sirve otra; si la sirve, es una página muerta), pero sin esperas por defecto (ESPERAS_TANDA:
con el freno de verdad la tanda para, no lo espera) y con un TOPE de peticiones por ejecución (`max_pages`,
`topped`). Al acabar, la Federacion dice por qué paró (`parada`: el navegador, el runner rechazado, el tope,
el freno o el plazo) y da su resumen (guardar_resumen: el carril del histórico decide con él qué hace
después). Hasta noviembre de 2026 leían con el paso de fetch_fiflp_2425 y daban por buena una página vacía;
solo fetch_fiflp_islas (la activación de la temporada en curso) sigue con ese paso, sin prisa.
"""
from datetime import datetime, timedelta, timezone
import json
import os
import random
import re
import time

import fiflp_render
from escritura import escribir_atomico
from fiflp_render import FIFLP_HOSTS

DEFAULT_DELAY = (1.0, 1.5)
DEFAULT_READY_MS = 5000
DEFAULT_INTERVAL = 7.0    # segundos entre el inicio de dos peticiones (FIFLP_MIN_INTERVAL)
EMPTY_JS = "() => !document.body || document.body.innerHTML.trim() === ''"
RETRY_WAITS = (15, 30)    # entre intentos de una página que no carga (tres intentos)
# Páginas seguidas que no cargan (cada una tras sus intentos): la federación bloquea o se ha caído, y
# el bot deja de pedirle más en esa pasada (Federacion.blocked), si la espera del freno no lo arregla.
# Salvo que, sin un 503 ni un 429 en ellas, la federación sirva otra página (Federacion._serving):
# entonces son URLs muertas, no la federación.
BLOCKED_AFTER = 3
# Los estados con los que la federación dice que no sirve (no la página): señal del freno, como una vacía.
BRAKE_STATUSES = (429, 503)
# La página de competiciones de la temporada, que existe siempre (update_fiflp.check_competitions): con
# ella, Federacion._serving prueba si la federación sirve cuando aún no ha cargado ninguna otra página.
CATALOG_URL = "/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}"
# La espera del freno (lo medido, en el docstring del módulo). La primera, sin pedir nada: el bloqueo
# dura ~5 min y casi nunca menos de 2, así que antes de 4 min un sondeo saldría vacío. Después, la misma
# página cada BRAKE_PROBE s: se pierde como mucho un minuto de cada freno. BRAKE_CAP, holgado (un freno se
# ha visto seguir a los 11 min y esperar solo cuesta un sondeo por minuto): si no ha vuelto, es otra cosa
# y la pasada acaba. BRAKE_PAUSES, uno: el bloqueo escala dentro de la pasada y la siguiente, con IP
# nueva, vuelve a empezar con ~5 min.
BRAKE_PAUSE = 4 * 60
BRAKE_PROBE = 60
BRAKE_PROBE_MIN = 30      # un sondeo más seguido no es educado (FIFLP_BRAKE_PROBE_S por debajo: el de siempre)
BRAKE_CAP = 20 * 60
BRAKE_PAUSES = 1
BRAKE_ROOM = 2 * 60       # tras la espera (y tras cada sondeo), antes del plazo: ~15 páginas a 7 s
DEFAULT = object()        # Federacion(max_pauses=…) sin darlo: brake_pauses() (None es «sin tope»)
# Los motivos de un intento fallido (goto, `why`) que Federacion mira: el freno (una página vacía, o un
# BRAKE_STATUSES) y el navegador cerrado (no la federación). Los demás, el texto del registro.
EMPTY = "vacía"
REFUSED = "rechazada"
CLOSED = "navegador cerrado"
# El fabricante de la máquina (nube): «Microsoft Corporation» en los runners de GitHub en Azure, «Amazon EC2»
# en los de AWS, a los que la federación no sirve desde el 13/11/2026 (docs/freno-2026-11.md).
SYS_VENDOR = "/sys/class/dmi/id/sys_vendor"
# Las tandas del histórico (para_tanda). RELANZAR_MIN: las páginas servidas en una ejecución por debajo de
# las cuales no se relanza en seguida. En Azure, sin freno, una ejecución lee ~500 por hora; con menos de 60
# (unos 7 min de lectura) algo iba mal (el freno, un runner rechazado, una caída) y se deja al disparo
# siguiente.
RELANZAR_MIN = 60
# Las ejecuciones (cada una con su runner y su IP) en que una página no carga aunque la federación sirve
# otras, antes de dejarla «no disponible en la federación». Tres y no los cuatro de las actas del bot: el bot
# reintenta en pasadas de horas para dar tiempo a que la federación complete un acta recién jugada; en
# temporadas cerradas no hay nada que esperar, y tres IPs distintas con la misma página muerta bastan.
MAX_INTENTOS = 3
# Las esperas del freno por ejecución de una tanda (HISTORICO_ESPERAS). Cero: con el freno de verdad el
# carril para la ejecución y el día, no lo espera; la detección es la del bot (la vacía solo es freno si la
# federación tampoco sirve otra).
ESPERAS_TANDA = 0

_OPTION = ' option:not([value=""]):not([value="0"])'

# ¿Listo? El elemento que necesita el lector (si hace falta) y las hojas de estilo de los hosts de
# la federación cargadas. Una hoja de otro host (no se resuelve: fiflp_render.fiflp_launch_args) no carga
# nunca: no se mira. Con la caché HTTP, las de la federación ya están desde la segunda página.
READY_JS = """([selector, hosts]) => {
  if (selector && !document.querySelector(selector)) return false;
  const ours = (url) => {
    let host = '';
    try { host = new URL(url, location.href).hostname.toLowerCase(); } catch (e) { return false; }
    return hosts.some((h) => host === h || host.endsWith('.' + h));
  };
  return Array.from(document.querySelectorAll('link[rel~="stylesheet"]'))
    .every((link) => !link.href || !ours(link.href) || link.sheet !== null);
}"""


def _env_number(text):
    return float(text.strip().replace(",", "."))


def _env_value(name, env=None):
    """El número de la variable `name` (con coma o punto decimal), o None si no está o no se entiende."""
    text = (os.environ if env is None else env).get(name, "")
    m = re.fullmatch(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*", text or "")
    return _env_number(m.group(1)) if m else None


def delay_range(env=None):
    """(mínimo, máximo) de la pausa entre peticiones: FIFLP_DELAY, «1-1.5» o «1.2» (fija). Un valor
    que no se entiende, al revés o negativo no deja al bot sin pausa: vale el de por defecto."""
    text = (os.environ if env is None else env).get("FIFLP_DELAY", "")
    m = re.fullmatch(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:-\s*([0-9]+(?:[.,][0-9]+)?)\s*)?", text or "")
    if not m:
        return DEFAULT_DELAY
    low = _env_number(m.group(1))
    high = _env_number(m.group(2)) if m.group(2) else low
    return (low, high) if 0 <= low <= high else DEFAULT_DELAY


def ready_timeout_ms(env=None):
    """El tope de la espera a que la página esté lista (FIFLP_READY_MS, en milisegundos). Nunca 0:
    para Playwright, 0 es esperar sin tope."""
    text = (os.environ if env is None else env).get("FIFLP_READY_MS", "").strip()
    return int(text) if text.isdigit() and int(text) > 0 else DEFAULT_READY_MS


def min_interval(env=None):
    """Los segundos mínimos entre el inicio de dos peticiones a la federación (FIFLP_MIN_INTERVAL). Un
    valor que no se entiende o negativo deja el de por defecto: nunca el bot sin freno."""
    value = _env_value("FIFLP_MIN_INTERVAL", env)
    return DEFAULT_INTERVAL if value is None else value


def brake_pause_seconds(env=None):
    """La primera espera cuando la federación frena, sin pedirle nada (FIFLP_BRAKE_PAUSE_MIN minutos; 4
    por defecto). Un valor que no se entiende
    o que no es positivo deja el de por defecto."""
    value = _env_value("FIFLP_BRAKE_PAUSE_MIN", env)
    return value * 60 if value else BRAKE_PAUSE


def brake_probe_seconds(env=None):
    """Cada cuánto, tras la primera espera, se vuelve a pedir la misma página (FIFLP_BRAKE_PROBE_S
    segundos; 60 por defecto). Menos de BRAKE_PROBE_MIN, o un valor que no se entiende, deja el de por
    defecto: un sondeo detrás de otro no es educado (y el bloqueo no se pasa antes)."""
    value = _env_value("FIFLP_BRAKE_PROBE_S", env)
    return value if value is not None and value >= BRAKE_PROBE_MIN else BRAKE_PROBE


def brake_cap_seconds(env=None):
    """El tope de cada freno, desde la página vacía (FIFLP_BRAKE_MAX_MIN minutos; 20 por defecto): si no
    vuelve a servir antes, nada más en esa pasada. Un valor que no se entiende o no positivo, el de
    por defecto."""
    value = _env_value("FIFLP_BRAKE_MAX_MIN", env)
    return value * 60 if value else BRAKE_CAP


def brake_pauses(env=None):
    """Cuántos frenos se esperan por pasada (FIFLP_BRAKE_PAUSES): por defecto uno (BRAKE_PAUSES: el
    segundo freno acaba la pasada). Con 0, ninguno: al frenar, la pasada se da por perdida; con «sin», sin
    tope (None: los que quepan en el plazo). Lo que no se entiende, el de por defecto."""
    text = (os.environ if env is None else env).get("FIFLP_BRAKE_PAUSES", "").strip().lower()
    if text == "sin":
        return None
    return int(text) if text.isdigit() else BRAKE_PAUSES


def esperas_tanda(env=None):
    """Cuántos frenos espera una ejecución de una tanda del histórico (HISTORICO_ESPERAS): por defecto
    ninguno (ESPERAS_TANDA). Lo que no se entiende, también ninguno: a diferencia del bot, el carril no
    tiene prisa por leer y lo prudente es parar."""
    text = (os.environ if env is None else env).get("HISTORICO_ESPERAS", "").strip()
    return int(text) if text.isdigit() else ESPERAS_TANDA


def nube(leer=None):
    """La nube de la máquina: "azure" si su fabricante (SYS_VENDOR) dice Microsoft, "aws" si dice Amazon y
    "otra" si es otra cosa o no se puede leer (en local, en un contenedor). `leer`, una función sin argumentos
    que da ese texto (las pruebas). Un diagnóstico: nunca falla."""
    def vendor():
        with open(SYS_VENDOR, encoding="utf-8", errors="replace") as f:
            return f.read()
    try:
        text = str((leer or vendor)() or "").lower()
    except Exception:
        return "otra"
    return "azure" if "microsoft" in text else "aws" if "amazon" in text else "otra"


def _empty(page):
    """¿La federación sirvió la página vacía (su freno)? Sin poder mirarla (las páginas de prueba), no."""
    try:
        return page.evaluate(EMPTY_JS) is True
    except Exception:
        return False


def pause(extra=0, rng=random.uniform, sleep=time.sleep, env=None):
    """La pausa entre dos peticiones a la federación (y `extra` segundos más)."""
    low, high = delay_range(env)
    sleep(rng(low, high) + extra)


def ready_selector(url):
    """Lo que el lector de esa página necesita que pinte el JS de la federación; None si nada."""
    if "NFG_CmpJornada" not in url:
        return None
    if "CodGrupo=" in url:
        return 'select[name="jornada"]' + _OPTION
    if "CodCompeticion=" in url:
        return 'select[name="grupo"]' + _OPTION
    return 'select[name="competicion"]' + _OPTION


def wait_ready(page, selector, timeout_ms, hosts=FIFLP_HOSTS):
    """Espera (con tope) a que la página esté lista. True si lo estaba; si no, se sigue igual."""
    try:
        page.wait_for_function(READY_JS, arg=[selector, list(hosts)], timeout=timeout_ms, polling=100)
        return True
    except Exception:
        return False


class _Closed(Exception):
    """El navegador se cerró en una petición de Federacion (la página, la de _serving o un sondeo del
    freno): Federacion.goto lo atiende en un solo sitio."""


def _closed(page, error):
    """¿Se cerró la página o el navegador (Chromium caído: «Target page, context or browser has been
    closed»)? Entonces el fallo no es de la federación."""
    try:
        if page.is_closed() is True:
            return True
    except Exception:                     # las páginas de prueba, sin is_closed
        pass
    return type(error).__name__ == "TargetClosedError" or "has been closed" in str(error)


def _refused(response):
    """¿La federación contestó con una página de error (un 503 de Apache cuando bloquea o se cae, un
    429 por ir deprisa, un 403 o un 404)? page.goto no lanza con ellas. Sin respuesta (las páginas de
    prueba), no. Cualquier 4xx: si no, un 403 a todo se leería como páginas vacías y la pasada acabaría
    en verde sin haber leído nada."""
    status = getattr(response, "status", None)
    return isinstance(status, int) and status >= 400


def goto(page, url, deadline=None, retries=3, ready_ms=None, hosts=FIFLP_HOSTS, sleep=time.sleep, log=print,
         clock=time.monotonic, why=None):
    """Carga `url` y espera a que esté lista para el lector (ready_selector y hojas de estilo). Hasta
    `retries` intentos, con 15 y 30 s entre ellos, nunca más allá de `deadline` (en `clock`): una página
    que no carga (o que la federación sirve con un 5xx o un 4xx) se deja para la próxima pasada. Una
    página VACÍA (el freno) no se reintenta: la misma página 10 s después sigue vacía y el bloqueo dura
    ~5 min; Federacion espera el freno. True si cargó. En `why` (una lista), el motivo de
    cada intento fallido: EMPTY o REFUSED si fue el freno (vacía, o un BRAKE_STATUSES), CLOSED si se
    cerró el navegador (sin más intentos: no es la federación); Federacion los usa para su espera.
    Cada carga, por fiflp_render.goto: desde el 2.º intento (la misma URL otra vez), y la 1.ª si el navegador
    ya la pidió antes, el documento va a la red y no a la caché HTTP (la federación los da con
    «Cache-Control: private, max-age=300»: si no, un sondeo del freno podría ser la vacía guardada)."""
    timeout_ms = ready_timeout_ms() if ready_ms is None else ready_ms
    for attempt in range(retries):
        status = None
        try:
            # El 2.º intento (y cualquier URL que el navegador ya pidió) va a la red, no a la caché HTTP:
            # sus documentos se guardan 5 min (fiflp_render.goto).
            response = fiflp_render.goto(page, url, wait_until="domcontentloaded", timeout=30000)
            status = getattr(response, "status", None)
            failure = f"responde {status}" if _refused(response) else None
            if failure is None and _empty(page):
                failure = "página vacía (la federación frena)"
        except Exception as error:
            if _closed(page, error):
                if why is not None:
                    why.append(CLOSED)
                return False
            failure = "no carga"
        if failure is None:
            wait_ready(page, ready_selector(url), timeout_ms, hosts)
            return True
        braking = failure.startswith("página vacía")
        if why is not None:
            why.append(EMPTY if braking else REFUSED if status in BRAKE_STATUSES else failure)
        # El freno dura minutos: ni un reintento (Federacion lo espera). Lo demás, con sus esperas cortas.
        if braking or attempt + 1 >= retries:
            return False
        wait = RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)]
        if deadline is not None and clock() + wait > deadline:
            return False
        log(f"      {failure} ({attempt + 1}/{retries}), se reintenta en {wait} s")
        sleep(wait)
    return False


class Federacion:
    """Lo que el bot usa del raspador de la federación (fetch_fiflp_2425: BASE y los lectores de
    clasificación y de jornada) con la carga y la pausa de aquí, para UNA pasada. `deadline` (en
    `clock`) es el plazo global del bot: ninguna página empieza después (contando la espera del
    intervalo: si no cabe, se espera igual y no se pide, y el bot ve el plazo agotado), y corta los
    reintentos de una página y la espera del freno. Entre el inicio de dos peticiones pasan al menos
    `interval` segundos (min_interval), también tras un freno (sin ralentizar: el cupo es de páginas).
    Cuenta:
      - `pages`, las peticiones (también los sondeos del freno y la de comprobar si sirve otra: el log
        del bot da el coste por página), y `served`, las páginas que cargaron;
      - `failures`, las seguidas que no cargan (con BLOCKED_AFTER, `blocked`: no pedirle más);
      - `dead`, las páginas que no cargan aunque la federación sirve otra (_serving): una vacía (sin un 503
        ni un 429) con la otra servida, la que cierra una racha de URLs muertas y la que el sondeo del
        freno no consigue cargar cuando la otra ya sí. No son el freno: ni señal ni espera. El bot
        (update_fiflp._read_actas) gasta así el intento de un acta muerta, que si no volvería la primera
        en cada pasada;
      - el freno: `brakes`, sus señales (cada página vacía o con un 503 o un 429, cargue o no tras sus
        reintentos, si la federación tampoco sirve otra página la vacía; y cada racha de BLOCKED_AFTER sin
        cargar en la que no sirve otra: _serving), y en `brake_marks` las páginas servidas (`served`) hasta
        cada una (el bot sabe así si un fallo anterior, sin servir nada entre medias, ya era el freno);
        `unserved`, las páginas que no sirvió por su freno;
      - la espera de cada freno (una página vacía, o la que dejaría a la federación `blocked`): `pauses`,
        los frenos esperados (cada uno, su primera espera de `pause_seconds` y sus sondeos cada
        `probe_seconds`, como mucho `cap_seconds` desde la página vacía; como mucho `max_pauses` por
        pasada, uno por defecto y None sin tope: brake_pause_seconds, brake_probe_seconds,
        brake_cap_seconds y brake_pauses); `resumed`, tras cuántos volvió a servir; `probes`, los sondeos; `brake_after`, las
        páginas servidas antes de cada freno, desde el anterior (el cupo, que el registro da también:
        «frena tras 15 páginas»); `paused`, los segundos esperando (no son coste de ninguna página ni de ningún grupo); y
        `halted`: frenó y no volvió (sin sitio en el plazo, pasado el tope o sin esperas), y no se le pide
        nada más (`blocked`);
      - `cloud`, la nube del runner (nube(), si no se da: "azure", "aws" u "otra"), y `refused_runner`: frenó
        antes de servir ninguna página en la pasada (`served` 0) en un runner que no es de Azure. Es la
        federación que no sirve a AWS (desde el 13/11/2026: siempre, desde la primera petición), no un
        cupo: sin la espera ni los sondeos, `halted`. En Azure, o con alguna página servida, la espera;
      - `closed`: el navegador se cerró (Chromium caído). No es el freno (ni señal ni espera): `halted`,
        y el bot da por error el grupo que se estaba leyendo;
      - `max_pages`, el tope de peticiones de la ejecución (las tandas del histórico, para_tanda; None, sin
        tope: el bot). Cuenta como `pages` (los sondeos y las comprobaciones de otra página también) y ninguna
        petición pasa de él, tampoco dentro de la espera del freno o de _serving: no se pide, `topped` y
        `blocked`. Si el tope corta la comprobación de otra página, la vacía no es ni el freno ni una muerta:
        no se sabe, y queda sin leer (lo pendiente de la tanda);
      - `parada`: por qué no se le pide nada más (o None, si aún se puede), y resumen(), las cuentas.
    Toda petición pasa por goto y fiflp_render.goto: una URL que el navegador ya pidió en la pasada (la otra
    página de _serving, los sondeos, lo que el bot vuelve a pedir) va a la red, no a la caché HTTP. Lo
    recuerda el navegador (su contexto), no esta clase: vale igual para cualquier lector."""

    def __init__(self, scraper, deadline=None, interval=None, clock=time.monotonic, sleep=time.sleep,
                 pause_seconds=None, max_pauses=DEFAULT, probe_seconds=None, cap_seconds=None, wall=None, log=print,
                 cloud=None, max_pages=None):
        self._scraper = scraper
        self.BASE = scraper.BASE
        self.deadline = deadline
        self.pages = self.served = self.failures = self.unserved = self.brakes = self.dead = 0
        self.cloud = nube() if cloud is None else cloud
        self.refused_runner = False
        self.brake_marks, self.brake_after = [], []
        self.interval = min_interval() if interval is None else interval
        self.pause_seconds = brake_pause_seconds() if pause_seconds is None else pause_seconds
        self.probe_seconds = brake_probe_seconds() if probe_seconds is None else probe_seconds
        self.cap_seconds = brake_cap_seconds() if cap_seconds is None else cap_seconds
        self.max_pauses = brake_pauses() if max_pauses is DEFAULT else max_pauses     # None: sin tope
        self.pauses = self.resumed = self.probes = 0
        self.paused = 0.0
        self.halted = self.closed = False
        self.max_pages = max_pages        # None: sin tope (el bot)
        self.topped = False
        self._clock, self._sleep, self._last = clock, sleep, None
        self._good = None                 # la última página que cargó (_serving)
        self._run = 0                     # las páginas servidas desde el último freno (su cupo)
        self._wall = wall or (lambda: datetime.now(timezone.utc))
        self._log = log

    @property
    def blocked(self):
        return self.halted or self.topped or self.failures >= BLOCKED_AFTER

    @property
    def parada(self):
        """Por qué no se le pide nada más a la federación en esta ejecución, o None si aún se puede: "navegador"
        (se cerró), "runner" (la federación no sirve a este runner), "tope" (el de peticiones), "freno" (frenó y
        no volvió, o no se esperó) o "plazo" (ya pasó). En ese orden: un freno cortado por el tope es el tope."""
        if self.closed:
            return "navegador"
        if self.refused_runner:
            return "runner"
        if self.topped:
            return "tope"
        if self.halted:
            return "freno"
        if self.deadline is not None and self._clock() > self.deadline:
            return "plazo"
        return None

    def resumen(self):
        """Las cuentas de la ejecución, para el resumen de una tanda (guardar_resumen)."""
        return {"pedidas": self.pages, "servidas": self.served, "muertas": self.dead, "esperas": self.pauses,
                "reanudadas": self.resumed, "frenos": self.brakes, "frenos_tras": list(self.brake_after),
                "parada": self.parada, "nube": self.cloud, "runner_rechazado": self.refused_runner,
                "segundos_en_espera": round(self.paused)}

    def _at_cap(self):
        """¿Se gastó ya el tope de peticiones de la ejecución (`max_pages`)? Entonces `topped`, y el registro lo
        dice (una vez). Sin tope (el bot), nunca."""
        if self.max_pages is None or self.pages < self.max_pages:
            return False
        if not self.topped:
            self.topped = True
            self._log(f"      se llega al tope de {self.max_pages} petici{'ón' if self.max_pages == 1 else 'ones'} "
                      "de esta ejecución: nada más")
        return True

    def _request(self, page, url, retries=3):
        """Una petición (con sus reintentos cortos: goto) al ritmo de `interval`. (¿cargó?, los motivos de
        sus intentos fallidos: goto `why`), o None si, tras la espera del intervalo, ya ha pasado el plazo:
        entonces ni se pide. Lo mismo, None, si ya se gastó el tope de peticiones (`max_pages`), mirado antes
        de la espera del intervalo: ninguna espera cambia el tope, y no se duerme para no pedir."""
        if self._at_cap():
            return None
        if self._last is not None:
            wait = self._last + self.interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        if self.deadline is not None and self._clock() > self.deadline:
            return None
        self._last = self._clock()
        self.pages += 1
        why = []
        loaded = goto(page, url, deadline=self.deadline, retries=retries, sleep=self._sleep, log=self._log,
                      clock=self._clock, why=why)
        if CLOSED in why:
            raise _Closed
        if loaded:
            self._good = url
        return loaded, why

    def _count_served(self):
        self.served += 1
        self._run += 1

    def _serving(self, page, url):
        """¿Sirve la federación otra página: la última que cargó o, si aún no ha cargado ninguna, la de
        competiciones de la temporada (CATALOG_URL, que existe siempre)? Distingue una página vacía que no
        es el freno, una racha de URLs muertas o un sondeo que sigue sin cargar cuando el freno ya pasó (sí:
        es esta página, `dead`) del freno o de una caída (no). Si la que falla es esa misma, no; tampoco sin
        ninguna cargada y sin temporada en la URL (un acta, la primera de la pasada)."""
        season = re.search(r"(?i)CodTemporada=(\d+)", url)
        other = self._good or (self.BASE + CATALOG_URL.format(season=season.group(1)) if season else None)
        if other is None or other == url:
            return False
        got = self._request(page, other, retries=1)
        if not got or not got[0]:
            return False
        self.failures = 0
        self._count_served()
        return True

    def _idle(self, seconds):
        """Espera `seconds` sin pedir nada (la del freno): cuenta en `paused`."""
        if seconds <= 0:
            return
        began = self._clock()
        self._sleep(seconds)
        self.paused += self._clock() - began

    def _wait_brake(self, page, url):
        """La espera de un freno en `url`: la primera, de `pause_seconds`, sin pedir nada; después, un sondeo
        (la misma página, una sola petición, fresca) cada `probe_seconds` hasta que sirva, mientras cada uno
        quepa con BRAKE_ROOM antes del plazo y no pase de `cap_seconds` desde ahora (la página vacía). Da
        (¿cargó esta página?, ¿volvió a servir?): vuelve a servir si carga esta o, si esta no (vacía o no),
        otra (_serving: la federación sirve y esta página no, que cuenta en `dead`). Hasta noviembre de 2026
        solo se preguntaba por otra si el sondeo no salía vacío: una página vacía siempre se sondeaba hasta el
        tope o el plazo. Sin ninguna página servida en la pasada y fuera de Azure (`cloud`), ni espera ni
        sondeos: el runner rechazado (`refused_runner`)."""
        n = self._run
        self.brake_after.append(n)
        if self.served == 0 and self.cloud != "azure":
            # La federación no sirve a los runners de AWS desde la primera petición, días después y con
            # cualquier IP (docs/freno-2026-11.md): esperar son 13 min y ~10 sondeos para nada.
            self.refused_runner = True
            self._log(f"      la federación no sirve a este runner desde la primera página (nube: {self.cloud}): "
                      "nada en esta pasada")
            return False, False
        if self.max_pauses is not None and self.pauses >= self.max_pauses:
            self._log("      la federación frena (sin esperas: FIFLP_BRAKE_PAUSES=0): nada más en esta pasada"
                      if not self.max_pauses else
                      f"      la federación frena otra vez, y ya se {'esperó' if self.pauses == 1 else 'esperaron'} "
                      f"{self.pauses} (FIFLP_BRAKE_PAUSES): nada más en esta pasada")
            return False, False
        if self._at_cap():
            # Sin una petición más (el tope de la tanda), ningún sondeo diría nada: la espera, para nada.
            return False, False
        began = self._clock()
        if self.deadline is not None and began + self.pause_seconds + BRAKE_ROOM > self.deadline:
            self._log(f"      la federación frena y no queda plazo para esperarla ({self.pause_seconds / 60:g} min y "
                      f"{BRAKE_ROOM / 60:g} de margen): nada más en esta pasada")
            return False, False
        self.pauses += 1
        until = self._wall() + timedelta(seconds=self.cap_seconds)
        self._log(f"      la federación frena tras {n} página{'' if n == 1 else 's'}: espera de "
                  f"{self.pause_seconds / 60:g} min y después la misma página cada {self.probe_seconds:g} s, "
                  f"hasta las {until:%H:%M} UTC como mucho")
        self._idle(self.pause_seconds)
        while True:
            got = self._request(page, url, retries=1)
            if got is None:                       # tras el intervalo, pasado el plazo (o el tope): ni se pidió
                if not self.topped:
                    self._log("      la federación sigue frenando y se acaba el plazo: nada más en esta pasada")
                return False, False
            self.probes += 1
            at = self._last                       # cuándo empezó el sondeo
            loaded = got[0]
            # Vacío o no, si no carga se pregunta por otra página: si esa carga, el freno ya pasó y es esta
            # página la que no carga (una muerta: vacía siempre). Sin preguntar, se sondearía hasta el tope.
            if loaded or self._serving(page, url):
                self.resumed += 1
                self.dead += not loaded
                self._run = 0 if loaded else 1       # la que cargó, la 1.ª de la vuelta (esta la cuenta _goto)
                self._log(f"      la federación vuelve a servir a los {at - began:.0f} s"
                          f"{'' if loaded else ', pero no esta página'}: se sigue")
                return loaded, True
            if self._at_cap():                    # el tope de la tanda: ni el sondeo siguiente ni su espera
                return False, False
            following = at + self.probe_seconds
            if following - began > self.cap_seconds:
                self._log(f"      la federación sigue frenando a los {at - began:.0f} s (tope de "
                          f"{self.cap_seconds / 60:g} min por freno): nada más en esta pasada")
                return False, False
            if self.deadline is not None and following + BRAKE_ROOM > self.deadline:
                self._log(f"      la federación sigue frenando a los {at - began:.0f} s y no queda plazo "
                          "para otro sondeo: nada más en esta pasada")
                return False, False
            self._log(f"      a los {at - began:.0f} s, sigue frenando")
            self._idle(following - self._clock())

    def goto(self, page, url):
        if self.halted or self.topped or (self.deadline is not None and self._clock() > self.deadline):
            return False                  # frenada sin remedio, en el tope o pasado el plazo: ni se pide
        try:
            return self._goto(page, url)
        except _Closed:                   # el navegador, no la federación: ni señal del freno ni espera
            self.closed = self.halted = True
            self.failures += 1
            self._log("      el navegador se ha cerrado: nada más en esta pasada")
            return False

    def _goto(self, page, url):
        got = self._request(page, url)
        if got is None:
            return False                  # tras el intervalo, pasado el plazo: ni se pide
        loaded, why = got
        empty, refused = EMPTY in why, REFUSED in why
        # Una página vacía (sin un 503 ni un 429, que son la federación sin más) solo es el freno si la
        # federación tampoco sirve otra página. Si la sirve, es esta la que no carga: una página muerta (las
        # actas de alevín vacías siempre desde el 21/11/2026), sin espera ni señal del freno; se sigue.
        if not loaded and empty and not refused and self._serving(page, url):
            empty = False
            self.dead += 1
            self._log("      página vacía, pero la federación sirve otra: no es el freno, es esta página")
        # El freno: una página vacía o con un 503 o un 429 (aunque cargue tras sus reintentos), o la que
        # dejaría a la federación bloqueada si no sirve otra página. Si la sirve, la racha es de URLs muertas
        # (dos grupos seguidos con la URL muerta, p. ej.): esta no carga y se sigue.
        signal = empty or refused
        streak = not loaded and self.failures + 1 >= BLOCKED_AFTER
        if streak and not signal and self._serving(page, url):
            streak = False
            self.dead += 1
            self._log(f"      {BLOCKED_AFTER} páginas seguidas sin cargar, pero la federación sirve otra: no es "
                      "el freno, es esta página")
        if self.topped:
            # El tope de la tanda cortó la comprobación de otra página: no se sabe si es el freno o esta
            # página. Ni señal ni muerta (una muerta gasta un intento de la tanda): queda sin leer, pendiente.
            return False
        if signal or streak:
            self.brakes += 1
            self.brake_marks.append(self.served)
        # En vez de rendirse, la espera del freno: la misma página hasta que vuelva a servir.
        braking = not loaded and (empty or streak)
        if braking:
            loaded, resumed = self._wait_brake(page, url)
            braking = not resumed
            self.halted = braking
        if loaded:
            self.failures = 0
            self._count_served()
        else:
            self.failures += 1
            self.unserved += braking
        return loaded

    def delay(self, extra=0):
        pause(extra)

    def __getattr__(self, name):          # parse_standings, parse_matches…: los del raspador
        return getattr(self._scraper, name)


def para_tanda(scraper, minutos, max_pages, log=print, clock=time.monotonic, sleep=time.sleep, wall=None, cloud=None,
               env=None):
    """La Federacion de una ejecución de una tanda del histórico: plazo de `minutos` desde ahora, tope de
    `max_pages` peticiones (0 o None, sin tope) y HISTORICO_ESPERAS esperas del freno (esperas_tanda: ninguna
    por defecto). El intervalo entre peticiones, los sondeos y el tope de cada freno, los del bot
    (min_interval, brake_*), del mismo entorno: la tanda lee al ritmo del bot, no más deprisa."""
    return Federacion(scraper, deadline=clock() + minutos * 60, interval=min_interval(env), clock=clock, sleep=sleep,
                      pause_seconds=brake_pause_seconds(env), max_pauses=esperas_tanda(env),
                      probe_seconds=brake_probe_seconds(env), cap_seconds=brake_cap_seconds(env), wall=wall, log=log,
                      cloud=cloud, max_pages=max_pages or None)


def parada_de(F):
    """Por qué paró la federación `F` (Federacion.parada), o None. Los lectores lo usan igual con una Federacion
    que con las federaciones falsas de las pruebas, que no la tienen."""
    return getattr(F, "parada", None)


def guardar_resumen(path, fed, partes):
    """Escribe en `path` (de forma atómica: el carril lo lee después) el resumen de la ejecución de una tanda:
    las cuentas de `fed` (Federacion.resumen), `partes` ({clave de trabajo: {"completo", "pendientes",
    "no_disponible"}}) y cuándo se escribió (en UTC, con el reloj de pared de `fed`). Sin `path`, nada."""
    if path is None:
        return
    escrito = fed._wall().astimezone(timezone.utc).isoformat(timespec="seconds")
    data = {**fed.resumen(), "partes": partes, "escrito": escrito}
    escribir_atomico(path, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def ultima_linea(F, completo):
    """La última línea del registro de una tanda, la que lee su workflow: «Completo.» (nada pendiente),
    «Frenada: …» (la federación no sirve: el freno de verdad o un runner rechazado; relanzar en seguida sería
    pedirle más a una federación que no sirve) o «Incompleto: relanzar para seguir.» (el plazo, el tope, el
    navegador, o lo pendiente de una página muerta, que gasta un intento por ejecución)."""
    if completo:
        return "Completo."
    if parada_de(F) in ("freno", "runner"):
        return (f"Frenada: {getattr(F, 'served', 0)} páginas servidas, la federación no sirve; se sigue en otra "
                "ejecución.")
    return "Incompleto: relanzar para seguir."


def un_intento(entry, previo):
    """`entry`, la entrada de una tanda cuya página no cargó aunque la federación servía otras (parada_de None:
    una página muerta o que no existe): `ok` False y un intento más que `previo` (la de antes; uno por ejecución,
    porque cada entrada se pide una vez en cada una) y, con MAX_INTENTOS, «no disponible en la federación»
    (`no_disponible`: cuenta como hecha, y los importadores la saltan porque miran `ok`). Si la federación paró,
    no se llama: la entrada se queda como estaba."""
    intentos = int((previo or {}).get("intentos") or 0) + 1
    entry.update(ok=entry.get("ok", False), intentos=intentos)
    if intentos >= MAX_INTENTOS:
        entry["no_disponible"] = True
    return entry


def preparar(page, F, season):
    """Antes de las páginas sin temporada en la URL (un acta, una ficha de campo) en una ejecución que aún no ha
    servido ninguna, la de competiciones de la temporada `season` (CATALOG_URL, que existe siempre): así, si la
    primera de ellas viene vacía, Federacion._serving tiene otra página que pedir y distingue una página muerta
    del freno. Sin ella, la primera acta muerta de una ejecución se tomaba por el freno y la ejecución acababa
    ahí, sin gastarle un intento, en todas las ejecuciones. Una petición por ejecución, y solo si hace falta.
    Da False si la federación no la sirvió (parada_de(F) dice por qué); True si ya había servido alguna."""
    if getattr(F, "served", 1):
        return True
    return F.goto(page, F.BASE + CATALOG_URL.format(season=season))
