"""Cuándo está lista una página de la federación y cuánto espera el bot entre una y otra (fiflp_carga.py).

La carga espera a lo que el lector necesita (las hojas de estilo de la federación, de las que salen las
cifras que lee el aplanado, y el desplegable que rellena su JS), con tope, y la pausa es corta y
configurable (FIFLP_DELAY): con esperas fijas, cada página costaría ~6,8 s y 33 grupos serían 19 min.
Sin red: una página falsa o un servidor local con Chromium (si no está, esas pruebas se saltan).
"""
from datetime import datetime, timedelta, timezone
import http.server
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fiflp_carga as C  # noqa: E402
from federacion_falsa import FederacionFalsa, Pagina, Reloj  # noqa: E402

BASE = "https://www.fiflp.com/pnfg/NPcd"
GROUP = f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22&CodCompeticion=54976988&CodGrupo=55234218"


# ── La pausa entre peticiones ─────────────────────────────────────────────────

def test_the_delay_is_shorter_by_default_and_set_by_environment():
    assert C.delay_range({}) == (1.0, 1.5)
    assert C.delay_range({"FIFLP_DELAY": "2-3.5"}) == (2.0, 3.5)
    assert C.delay_range({"FIFLP_DELAY": "1.2"}) == (1.2, 1.2)
    assert C.delay_range({"FIFLP_DELAY": " 0,8 - 1,1 "}) == (0.8, 1.1)
    # Un valor que no se entiende, al revés o negativo no deja al bot sin pausa: el de siempre.
    for wrong in ("deprisa", "3-1", "-1", ""):
        assert C.delay_range({"FIFLP_DELAY": wrong}) == (1.0, 1.5), wrong


def test_the_ready_cap_is_set_by_environment_and_never_unbounded():
    assert C.ready_timeout_ms({}) == 5000
    assert C.ready_timeout_ms({"FIFLP_READY_MS": "3000"}) == 3000
    for wrong in ("0", "-5", "rápido", ""):                 # 0, para Playwright, es esperar sin tope
        assert C.ready_timeout_ms({"FIFLP_READY_MS": wrong}) == 5000, wrong


def test_pause_sleeps_a_jittered_time_within_the_range():
    slept = []
    C.pause(rng=lambda a, b: (a + b) / 2, sleep=slept.append, env={"FIFLP_DELAY": "1-2"})
    C.pause(extra=2, rng=lambda a, b: a, sleep=slept.append, env={})
    assert slept == [1.5, 3.0]


# ── Qué necesita cada página ──────────────────────────────────────────────────

def test_ready_selector_waits_for_the_dropdown_the_reader_uses():
    opt = ' option:not([value=""]):not([value="0"])'
    assert C.ready_selector(GROUP) == 'select[name="jornada"]' + opt
    assert C.ready_selector(GROUP + "&CodJornada=3") == 'select[name="jornada"]' + opt
    assert C.ready_selector(f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22&CodCompeticion=1") == 'select[name="grupo"]' + opt
    assert C.ready_selector(f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22") == 'select[name="competicion"]' + opt
    # El resto llega entero en el HTML: basta con sus hojas de estilo.
    for page in ("NFG_VisClasificacion?codjornada=99", "NFG_CmpPartido?CodActa=1", "NFG_CMP_Goleadores?x=1",
                 "NFG_LstCampos?NPcd_Page=1", "NFG_VisCampos?Codigo_Campo=75"):
        assert C.ready_selector(f"{BASE}/{page}") is None


class Response:
    def __init__(self, status):
        self.status = status


class FakePage:
    """goto que falla `fails` veces (o responde con los estados de `statuses`); registra lo que espera."""
    def __init__(self, fails=0, ready=True, statuses=(), empties=0):
        self.fails, self.ready, self.gotos, self.waits = fails, ready, [], []
        self.statuses = list(statuses)
        self.empties = empties          # cargas seguidas que la federación sirve vacías

    def evaluate(self, js, *a):
        if js == C.EMPTY_JS:
            empty = self.empties > 0
            self.empties -= empty
            return empty
        return None

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append((url, wait_until))
        if self.fails:
            self.fails -= 1
            raise TimeoutError("503")
        return Response(self.statuses.pop(0)) if self.statuses else None

    def wait_for_function(self, js, arg=None, timeout=None, polling=None):
        self.waits.append((arg, timeout))
        if not self.ready:
            raise TimeoutError("sin desplegable")

    def wait_for_timeout(self, ms):
        raise AssertionError("nada de esperas fijas")


def test_goto_waits_for_the_page_state_not_a_fixed_time():
    page = FakePage()
    assert C.goto(page, GROUP, ready_ms=4000, log=lambda *_: None)
    assert page.gotos == [(GROUP, "domcontentloaded")]
    (selector, hosts), timeout = page.waits[0]
    assert selector.startswith('select[name="jornada"]') and timeout == 4000
    assert "fiflp.com" in hosts
    # Si lo que espera no llega a tiempo, la página vale igual: los lectores ya saben qué hacer.
    assert C.goto(FakePage(ready=False), GROUP, ready_ms=10, log=lambda *_: None)


def test_goto_retries_with_backoff_but_never_past_the_deadline():
    slept = []
    page = FakePage(fails=1)
    assert C.goto(page, GROUP, sleep=slept.append, log=lambda *_: None)
    assert slept == [15] and len(page.gotos) == 2
    # Sin plazo para la espera siguiente, se rinde: la página queda para la próxima pasada.
    slept.clear()
    page = FakePage(fails=5)
    assert not C.goto(page, GROUP, deadline=time.monotonic() + 10, sleep=slept.append, log=lambda *_: None)
    assert slept == [] and len(page.gotos) == 1
    # Tres intentos como mucho, y sin esperar después del último.
    slept.clear()
    page = FakePage(fails=5)
    assert not C.goto(page, GROUP, sleep=slept.append, log=lambda *_: None)
    assert slept == [15, 30] and len(page.gotos) == 3


def test_an_error_status_is_a_page_that_did_not_load():
    """page.goto no lanza con un 503 o un 429: la página de error de la federación (un bloqueo, una
    caída) no es una página cargada. Se reintenta con las mismas esperas y, si sigue, no carga: el
    acta no gasta un intento y el bot puede cortar la pasada."""
    slept, said = [], []
    page = FakePage(statuses=[503, 200])
    assert C.goto(page, GROUP, sleep=slept.append, log=said.append)
    assert slept == [15] and len(page.gotos) == 2 and "503" in said[0]
    for status in (503, 429, 500, 403, 404):
        slept.clear()
        page = FakePage(statuses=[status] * 3)
        assert not C.goto(page, GROUP, sleep=slept.append, log=lambda *_: None), status
        assert slept == [15, 30] and len(page.gotos) == 3 and page.waits == []
    # Lo demás es una página: un 200 o sin respuesta. Un 4xx no lo es: un 403 a todo daría páginas vacías
    # leídas y una pasada en verde.
    for statuses in ([200], []):
        assert C.goto(FakePage(statuses=statuses), GROUP, sleep=slept.append, log=lambda *_: None)


def test_an_empty_page_is_the_federation_braking_and_not_a_loaded_page():
    """Tras unas 20 páginas seguidas a buen ritmo, la federación sirve un 200 con
    «<html><head></head><body></body></html>». Una página vacía no carga (si el bot la tomara por
    cargada, grupos enteros darían «no sirvió las jornadas»), y NI UN REINTENTO: la misma página 10 s
    después sale vacía (el bloqueo dura ~5 min). Federacion espera el freno; goto solo lo dice (why)."""
    slept, said, why = [], [], []
    page = FakePage(empties=1)
    assert not C.goto(page, GROUP, sleep=slept.append, log=said.append, why=why)
    assert slept == [] and len(page.gotos) == 1 and page.waits == [] and said == []
    assert why == [C.EMPTY]
    assert not hasattr(C, "EMPTY_WAIT")


def test_the_bot_adapter_keeps_a_minimum_interval_between_requests():
    """El ritmo que la federación tolera: el de antes de octubre (~6,8 s por página, unas 9 por
    minuto), no el de las esperas recortadas (~5,2 s, 11-12 por minuto), que la hizo frenar."""
    import fetch_fiflp_2425 as F
    now, slept = [100.0], []
    clock = lambda: now[0]
    def sleep(s):
        slept.append(round(s, 2))
        now[0] += s
    fed = C.Federacion(F, interval=7.0, clock=clock, sleep=sleep)
    page = FakePage()
    fed.goto(page, GROUP)                 # la primera, sin esperar
    now[0] += 2.0                         # el lector y la pausa gastan 2 s
    fed.goto(page, GROUP)
    now[0] += 9.0                         # más que el intervalo: sin esperar
    fed.goto(page, GROUP)
    assert slept == [5.0] and fed.pages == 3


def test_the_minimum_interval_is_set_by_environment():
    assert C.min_interval({}) == C.DEFAULT_INTERVAL >= 6.5
    assert C.min_interval({"FIFLP_MIN_INTERVAL": "8,5"}) == 8.5
    for bad in ("", "x", "-1"):
        assert C.min_interval({"FIFLP_MIN_INTERVAL": bad}) == C.DEFAULT_INTERVAL


def test_the_bot_adapter_knows_when_the_federation_stops_serving(monkeypatch):
    """Federacion cuenta las páginas seguidas que no cargan (cada una tras sus reintentos): con
    BLOCKED_AFTER, blocked; una que carga lo deshace. Sin pausas largas (max_pauses=0, FIFLP_BRAKE_PAUSES=0);
    con ellas, test_a_streak_of_error_pages_pauses_before_blocking."""
    import fetch_fiflp_2425 as F
    monkeypatch.setattr(C, "goto", lambda page, url, **kw: page.statuses.pop(0) == 200)
    fed = C.Federacion(F, interval=0, max_pauses=0, log=lambda *_: None)
    page = FakePage(statuses=[503, 503, 200] + [503] * C.BLOCKED_AFTER)
    for _ in range(3):
        fed.goto(page, GROUP)
        assert not fed.blocked
    for n in range(C.BLOCKED_AFTER):
        fed.goto(page, GROUP)
    assert fed.blocked and fed.failures == C.BLOCKED_AFTER and fed.pages == 3 + C.BLOCKED_AFTER
    assert fed.served == 1 and fed.pauses == 0
    # Bloqueada, no se le pide nada más.
    assert not fed.goto(page, GROUP) and fed.pages == 3 + C.BLOCKED_AFTER


# ── El freno: la espera y los sondeos de la misma página ─────────────────────

@pytest.fixture(autouse=True)
def _brake_defaults(monkeypatch):
    """Las pruebas, con la espera del freno por defecto, aunque el entorno traiga otra."""
    for name in ("FIFLP_BRAKE_PAUSE_MIN", "FIFLP_BRAKE_PROBE_S", "FIFLP_BRAKE_MAX_MIN", "FIFLP_BRAKE_PAUSES",
                 "FIFLP_MIN_INTERVAL"):
        monkeypatch.delenv(name, raising=False)


class Brake:
    """La federación frena entre `start` y `end` (en el reloj falso; end None: no se pasa) y sirve vacías
    sus páginas. Las URLs de `dead`, vacías siempre (páginas muertas: la federación sirve las demás). Cada
    carga cuesta `cost` s. Apunta cuándo empezó cada petición y cuánto durmió el bot."""

    def __init__(self, start=0.0, end=None, cost=2.0, now=1000.0, dead=()):
        self.start, self.end, self.cost, self.t, self.dead = start, end, cost, now, set(dead)
        self.starts, self.slept, self.said = [], [], []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 2))
        self.t += s

    def braking(self):
        return self.t >= self.start and (self.end is None or self.t < self.end)

    def page(self):
        brake = self

        class Page(FakePage):
            def goto(self, url, wait_until=None, timeout=None):
                brake.starts.append(brake.t)
                self.served_empty = brake.braking() or url in brake.dead
                brake.t += brake.cost
                return super().goto(url, wait_until, timeout)

            def evaluate(self, js, *a):
                return self.served_empty if js == C.EMPTY_JS else None
        return Page()

    def fed(self, **kw):
        import fetch_fiflp_2425 as F
        kw.setdefault("interval", 7.0)
        return C.Federacion(F, clock=self.clock, sleep=self.sleep, log=self.said.append,
                            wall=lambda: datetime(2026, 10, 15, 3, 29, tzinfo=timezone.utc)
                            + timedelta(seconds=self.t - 1000), **kw)


class Quota(Brake):
    """La federación MEDIDA (freno-fiflp.yml): sirve `per_ip` documentos y después vacías
    durante el siguiente de `lasts` (segundos desde la primera vacía; None, ya no vuelve en esa pasada).
    Los sondeos durante el bloqueo no lo alargan ni gastan del cupo siguiente; al pasar, otro cupo."""

    def __init__(self, per_ip=15, lasts=(300,), **kw):
        super().__init__(start=10 ** 9, **kw)
        self.per_ip, self.lasts, self.count, self.since, self.blocks = per_ip, list(lasts), 0, None, []

    def braking(self):
        if self.since is not None:
            lasts = self.lasts[min(len(self.blocks) - 1, len(self.lasts) - 1)]
            if lasts is None or self.t < self.since + lasts:
                return True
            self.since, self.count = None, 0
        if self.count >= self.per_ip:
            self.since = self.t
            self.blocks.append(self.t)
            return True
        self.count += 1
        return False


def pages(n, first=1):
    return [f"{GROUP}&CodJornada={k}" for k in range(first, first + n)]


def test_the_measured_brake_15_pages_and_5_minutes_resumes_with_probes_of_the_same_page():
    """Lo medido: 15 páginas, la 16.ª vacía y ~5 min de bloqueo. Sin reintento de la vacía; la última que
    cargó, vacía también (es el freno, no esta página); la espera de 4 min (FIFLP_BRAKE_PAUSE_MIN) y después
    LA MISMA página cada minuto (FIFLP_BRAKE_PROBE_S), y si sale vacía, la otra: a los 240 s, vacías; a los
    300, servida. Se sigue al mismo ritmo (7 s: el cupo es de páginas, no de ritmo) y la vuelta siguiente
    da otras 15. Sin tope de frenos (FIFLP_BRAKE_PAUSES=sin), el segundo también se espera; por defecto, no
    (la prueba siguiente)."""
    b = Quota(per_ip=15, lasts=(300, 300))
    fed, page = b.fed(deadline=1000.0 + 33 * 60, max_pauses=None), b.page()
    urls = pages(40)
    for url in urls[:15]:
        assert fed.goto(page, url)
    assert fed.goto(page, urls[15])                                         # vacía, y servida a los 300 s
    assert [u for u, _ in page.gotos].count(urls[15]) == 3                  # vacía, sondeo vacío, sondeo servido
    assert [u for u, _ in page.gotos][15:] == [urls[15], urls[14], urls[15], urls[14], urls[15]]   # y la otra
    # El intervalo hasta la otra; 4 min; el intervalo hasta la otra tras el 1.er sondeo; el minuto hasta el 2.º.
    assert b.slept[-4:] == [5.0, C.BRAKE_PAUSE, 5.0, C.BRAKE_PROBE - 9.0]
    assert fed.pauses == 1 and fed.resumed == 1 and fed.probes == 2 and fed.brake_after == [15] and fed.dead == 0
    assert fed.paused == C.BRAKE_PAUSE + C.BRAKE_PROBE - 9 and not fed.blocked and fed.unserved == 0
    assert fed.served == 16 and fed.failures == 0 and fed.interval == 7.0
    assert [s for s in b.said if "fren" in s or "servir" in s] == [
        "      la federación frena tras 15 páginas: espera de 4 min y después la misma página cada 60 s, "
        "hasta las 03:50 UTC como mucho",
        "      a los 240 s, sigue frenando",
        "      la federación vuelve a servir a los 300 s: se sigue"]
    # Al mismo ritmo, y otras 15 (la del sondeo es la primera) antes del freno siguiente.
    for url in urls[16:30]:
        assert fed.goto(page, url)
    assert b.starts[-1] - b.starts[-2] == 7.0
    assert fed.goto(page, urls[30]) and fed.pauses == 2 and fed.resumed == 2 and fed.brake_after == [15, 15]
    assert len(b.blocks) == 2


def test_by_default_a_pass_waits_for_the_first_brake_only():
    """Una espera por pasada (BRAKE_PAUSES = 1): el bloqueo escala dentro de la pasada (~300 s el 1.º, ~900 s
    el 2.º, más que el plazo el 3.º) y la pasada siguiente, con IP nueva, vuelve a empezar con ~5 min. Así:
    15 páginas, la espera del 1.º (vuelve a los 300 s), otras 15 y, en el 2.º freno, nada más en esta
    pasada (sin esperar sus 15 min). Esa página no se sirvió por el freno (unserved): el bot no la da por
    error."""
    b = Quota(per_ip=15, lasts=(300, 900, 2700))
    fed, page = b.fed(deadline=1000.0 + 16 * 60), b.page()
    loaded = [fed.goto(page, url) for url in pages(40)]
    assert loaded[:30] == [True] * 30 and not any(loaded[30:])     # 15 y 15 (la 16.ª, en el sondeo)
    assert fed.pauses == 1 and fed.resumed == 1 and fed.brake_after == [15, 15] and fed.halted and fed.blocked
    assert fed.unserved == 1 and fed.paused == C.BRAKE_PAUSE + C.BRAKE_PROBE - 9 and len(b.blocks) == 2
    # Las 30, la vacía, el sondeo vacío y la del 2.º, y la otra página tras cada una de las tres: nada más.
    assert len(page.gotos) == 30 + 3 + 3
    assert b.said[-1] == "      la federación frena otra vez, y ya se esperó 1 (FIFLP_BRAKE_PAUSES): nada más en esta pasada"
    assert b.t - 1000.0 < 9 * 60                            # ~9 min: 15 páginas, 5 min y 15 más


def test_a_brake_that_does_not_pass_within_its_cap_stops_the_pass():
    """Si a los 20 min (FIFLP_BRAKE_MAX_MIN) de la página vacía no ha vuelto a servir (el bloqueo más largo
    medido duró 364 s; se han visto de más de 11 min), nada más en esa pasada: blocked, y la página cuenta
    como no servida por el freno. Diecisiete sondeos (a los 240, 300… 1200 s desde la otra página, la de
    competiciones, que tampoco carga), dos peticiones cada uno (el sondeo y la otra); nada entre medias."""
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 33 * 60), b.page()
    assert not fed.goto(page, GROUP)
    assert len(page.gotos) == 2 + 2 * 17 and fed.probes == 17
    assert [u for u, _ in page.gotos] == [GROUP, CATALOG] * 18
    began = b.starts[1] + 2                                     # tras la otra página: la espera
    assert [round(t - began) for t in b.starts[2::2]] == list(range(240, 1201, 60))
    assert [t - p for p, t in zip(b.starts[2::2], b.starts[3::2])] == [7.0] * 17        # la otra, al ritmo
    assert b.slept == [5.0, 240] + [5.0, 51.0] * 16 + [5.0]
    assert fed.pauses == 1 and fed.resumed == 0 and fed.blocked and fed.halted and fed.dead == 0
    assert fed.unserved == 1 and fed.served == 0 and fed.brake_after == [0]
    assert b.said[-1] == "      la federación sigue frenando a los 1200 s (tope de 20 min por freno): nada más en esta pasada"
    assert not fed.goto(page, GROUP) and len(page.gotos) == 36               # nada más
    # Con otro tope, otros sondeos (FIFLP_BRAKE_MAX_MIN, cap_seconds).
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 33 * 60, cap_seconds=300), b.page()
    assert not fed.goto(page, GROUP) and fed.probes == 2


def test_several_brakes_in_a_pass_until_the_deadline():
    """Sin tope de frenos por pasada (FIFLP_BRAKE_PAUSES=sin, max_pauses None): con el cupo medido (15
    páginas y ~2-6 min), en los 33 min del plazo la federación frena varias veces y cada vez se sigue,
    hasta el plazo. Ninguna página empieza después. Cada vuelta, 15 páginas."""
    b = Quota(per_ip=15, lasts=(304, 364, 304, 122, 303, 300))       # lo medido, a 7 y a 15 s
    deadline = 1000.0 + 33 * 60
    fed, page = b.fed(deadline=deadline, max_pauses=None), b.page()
    loaded = [fed.goto(page, url) for url in pages(400)]
    assert all(t <= deadline for t in b.starts)
    assert fed.pauses >= 4 and fed.resumed >= fed.pauses - 1
    assert fed.brake_after[:fed.resumed + 1] == [15] * (fed.resumed + 1)
    assert sum(loaded) == fed.served >= 15 * (fed.resumed + 1)
    # Lo que falta, a otra pasada: o el plazo, o un freno sin sitio para su espera.
    assert fed.blocked or b.t > deadline


def test_the_brake_wait_is_only_taken_if_it_fits_before_the_deadline():
    """Tras la primera espera tiene que quedar BRAKE_ROOM (2 min) antes del plazo global para leer algo: si
    no, blocked sin esperar. Lo mismo con cada sondeo. Ninguna página empieza pasado el plazo."""
    for room, waited in ((C.BRAKE_ROOM - 1, False), (C.BRAKE_ROOM + 1, True)):
        b = Brake(start=1000.0)
        # El freno se ve a los 9 s (la vacía y, al ritmo, la otra página, que tampoco carga): el plazo deja
        # `room` tras una espera de 4 min.
        fed, page = b.fed(deadline=1000.0 + 9 + 240 + room), b.page()
        assert not fed.goto(page, GROUP)
        assert fed.blocked and fed.pauses == int(waited), room
        assert b.slept == ([5.0, 240, 5.0] if waited else [5.0]), room
        assert fed.probes == int(waited) and all(t <= fed.deadline for t in b.starts)
        if not waited:
            assert b.said[-1] == ("      la federación frena y no queda plazo para esperarla (4 min y 2 de margen): "
                                  "nada más en esta pasada")
        else:
            assert b.said[-1] == ("      la federación sigue frenando a los 240 s y no queda plazo para otro sondeo: "
                                  "nada más en esta pasada")
    # Pasado el plazo, ni se pide (y no cuenta como fallo de la federación).
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1010.0), b.page()
    assert fed.goto(page, GROUP)
    b.t = 1010.5
    assert not fed.goto(page, GROUP) and len(page.gotos) == 1 and fed.failures == 0 and not fed.blocked


def test_a_streak_of_error_pages_pauses_before_blocking():
    """Lo que antes acababa en blocked (BLOCKED_AFTER páginas seguidas sin cargar: un 503 tras otro, el
    Apache de la federación cuando bloquea) también hace la espera del freno antes de rendirse, en la
    página que la dejaría bloqueada; si el primer sondeo carga, sigue."""
    b = Brake(start=10 ** 9)
    fed = b.fed(deadline=1000.0 + 25 * 60)
    page = b.page()
    page.statuses = [503] * 3 * (C.BLOCKED_AFTER - 1) + [503] * 3 + [200]
    for n in range(C.BLOCKED_AFTER - 1):
        assert not fed.goto(page, GROUP) and fed.pauses == 0
    assert fed.goto(page, GROUP)
    assert fed.pauses == 1 and fed.resumed == 1 and fed.failures == 0 and not fed.blocked
    assert b.slept.count(C.BRAKE_PAUSE) == 1 and fed.probes == 1 and fed.unserved == 0


def test_a_streak_of_dead_pages_while_another_page_loads_is_not_the_brake():
    """Dos URLs muertas seguidas (un 500 tras otro, cada una tras sus reintentos) también son tres páginas
    seguidas sin cargar, y no son el freno. Antes de la espera del freno, el bot vuelve a pedir la última
    página que cargó: si carga, la federación sirve; ni espera ni bloqueo, la racha se deshace y esta
    página no carga (su grupo, un error). Si esa tampoco carga, sí es el freno (o una caída): la espera, y
    en el sondeo lo mismo (si sirve otras y no esta, se sigue, al mismo ritmo)."""
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    good = GROUP + "&CodJornada=3"
    page.statuses = [200] + [500] * 3 * C.BLOCKED_AFTER + [200]
    assert fed.goto(page, good)
    for n in range(C.BLOCKED_AFTER):
        assert not fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos] == [good] + [GROUP] * 3 * C.BLOCKED_AFTER + [good]
    assert fed.pauses == 0 and fed.brakes == 0 and fed.brake_marks == [] and not fed.blocked
    assert fed.failures == 1 and fed.served == 2 and fed.unserved == 0 and C.BRAKE_PAUSE not in b.slept
    assert "      3 páginas seguidas sin cargar, pero la federación sirve otra: no es el freno, es esta página" in b.said
    page.statuses = [200]
    assert fed.goto(page, good) and fed.failures == 0
    # La otra tampoco carga: el freno (o una caída), la pausa; tras ella sirve otras y no esta: se sigue.
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    page.statuses = [200] + [500] * 3 * C.BLOCKED_AFTER + [500] + [500, 200]
    assert fed.goto(page, good)
    for n in range(C.BLOCKED_AFTER):
        assert not fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos][-4:] == [GROUP, good, GROUP, good]
    assert fed.pauses == 1 and fed.resumed == 1 and fed.brakes == 1 and fed.brake_marks == [1]
    assert not fed.blocked and fed.failures == 1 and fed.unserved == 0 and fed.interval == 7.0
    assert "      la federación vuelve a servir a los 240 s, pero no esta página: se sigue" in b.said


def test_with_no_page_loaded_yet_the_season_catalog_tells_dead_pages_from_the_brake():
    """Las dos URLs muertas, las primeras de la pasada: aún no ha cargado ninguna página que volver a pedir.
    El bot prueba la de competiciones de la temporada (CATALOG_URL, que existe siempre): si carga, no es el
    freno."""
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    catalog = BASE + "/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22"
    page.statuses = [500] * 3 * C.BLOCKED_AFTER + [200]
    for n in range(C.BLOCKED_AFTER):
        assert not fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos] == [GROUP] * 3 * C.BLOCKED_AFTER + [catalog]
    assert fed.pauses == 0 and fed.brakes == 0 and not fed.blocked and fed.failures == 1
    # Si esa tampoco carga, el freno (o una caída): la pausa.
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    page.statuses = [500] * 3 * C.BLOCKED_AFTER + [500, 200]
    for n in range(C.BLOCKED_AFTER - 1):
        assert not fed.goto(page, GROUP)
    assert fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos][-2:] == [catalog, GROUP] and fed.pauses == 1 and fed.brakes == 1


# ── Noviembre de 2026: una página vacía que no es el freno, y el runner al que no sirve ──
# (docs/freno-2026-11.md: actas de alevín cuya página sale vacía siempre, y los runners de AWS)

CATALOG = BASE + "/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22"


def test_pagina_vacia_con_federacion_sirviendo_no_es_freno():
    """Una página vacía siempre (un acta muerta) mientras las demás cargan: antes de darla por freno, la
    última que cargó. Si carga, no es el freno, es esta página: ni espera ni sondeos ni señal (`brakes`,
    `brake_marks`, `brake_after`), cuenta en `dead` y la pasada sigue. Peticiones: la vacía (sin reintentos,
    como hoy) y la otra. Sin ninguna cargada aún, la otra es la de competiciones de la temporada."""
    good, dead, after = GROUP + "&CodJornada=3", GROUP + "&CodJornada=4", GROUP + "&CodJornada=5"
    b = Brake(start=10 ** 9, dead={dead})
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    assert fed.goto(page, good)
    assert not fed.goto(page, dead)
    assert fed.dead == 1 and fed.brakes == 0 and fed.brake_marks == [] and fed.brake_after == []
    assert fed.pauses == 0 and fed.probes == 0 and fed.paused == 0 and not fed.halted and not fed.blocked
    assert fed.unserved == 0 and fed.served == 2 and C.BRAKE_PAUSE not in b.slept
    assert b.said == ["      página vacía, pero la federación sirve otra: no es el freno, es esta página"]
    assert fed.goto(page, after)                                        # la siguiente se pide y carga
    assert [u for u, _ in page.gotos] == [good, dead, good, after] and fed.failures == 0
    # La primera de la pasada: la de competiciones.
    b = Brake(start=10 ** 9, dead={dead})
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    assert not fed.goto(page, dead) and fed.dead == 1 and fed.brakes == 0 and fed.pauses == 0
    assert [u for u, _ in page.gotos] == [dead, CATALOG]


def test_pagina_vacia_y_la_otra_tambien_es_freno():
    """Todo vacío (el freno de octubre): la otra página tampoco carga, así que es el freno, como hoy: la
    espera de 4 min y los sondeos de la misma página, con una petición más por freno y por sondeo (la otra,
    al ritmo de siempre). Cuando vuelve a servir, se sigue."""
    good, url, after = GROUP + "&CodJornada=3", GROUP + "&CodJornada=4", GROUP + "&CodJornada=5"
    b = Brake(start=1003.0, end=1007.0 + 300)          # sirve la primera; frena desde la segunda ~5 min
    fed, page = b.fed(deadline=1000.0 + 33 * 60), b.page()
    assert fed.goto(page, good)
    assert fed.goto(page, url)                          # vacía; servida en el 2.º sondeo
    assert [u for u, _ in page.gotos] == [good, url, good, url, good, url]
    assert b.slept == [5.0, 5.0, C.BRAKE_PAUSE, 5.0, C.BRAKE_PROBE - 9.0]     # el ritmo, la otra, 4 min…
    assert fed.pauses == 1 and fed.resumed == 1 and fed.probes == 2 and fed.dead == 0
    assert fed.brakes == 1 and fed.brake_marks == [1] and fed.brake_after == [1] and not fed.halted
    assert fed.served == 2 and fed.failures == 0 and fed.unserved == 0
    assert [s for s in b.said if "fren" in s or "servir" in s] == [
        "      la federación frena tras 1 página: espera de 4 min y después la misma página cada 60 s, "
        "hasta las 03:49 UTC como mucho",
        "      a los 240 s, sigue frenando",
        "      la federación vuelve a servir a los 300 s: se sigue"]
    assert fed.goto(page, after)


def test_sondeo_vacio_pero_la_federacion_ya_sirve():
    """Un freno de verdad que se pasa durante la espera, en una página que además sale vacía siempre: el
    primer sondeo, vacío, pregunta por la otra página; carga, así que la espera acaba (vuelve a servir,
    pero no esta página) y esta cuenta en `dead`. Sin sondear hasta el tope."""
    good, url = GROUP + "&CodJornada=3", GROUP + "&CodJornada=4"
    b = Brake(start=1003.0, end=1003.0 + 200, dead={url})
    fed, page = b.fed(deadline=1000.0 + 33 * 60), b.page()
    assert fed.goto(page, good)
    assert not fed.goto(page, url)
    assert [u for u, _ in page.gotos] == [good, url, good, url, good]
    assert fed.pauses == 1 and fed.probes == 1 and fed.resumed == 1 and fed.dead == 1 and fed.brakes == 1
    assert not fed.halted and not fed.blocked and fed.failures == 1 and fed.unserved == 0
    assert "      la federación vuelve a servir a los 240 s, pero no esta página: se sigue" in b.said


def test_primera_pagina_vacia_fuera_de_azure_acaba_al_momento():
    """Los runners de GitHub en AWS: la federación les sirve vacío desde la primera petición, siempre (183 de
    183; en Azure, 0 de 187). Si frena antes de servir ninguna página en la pasada y el runner no es de
    Azure, nada que esperar: ni la espera ni los sondeos, `halted` y `refused_runner`. En Azure, o con
    alguna página ya servida, la espera de siempre."""
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 16 * 60, cloud="aws"), b.page()
    assert fed.cloud == "aws" and not fed.refused_runner
    assert not fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos] == [GROUP, CATALOG]        # la vacía y la otra: nada más
    assert fed.pauses == 0 and fed.probes == 0 and fed.paused == 0 and C.BRAKE_PAUSE not in b.slept
    assert fed.halted and fed.blocked and fed.refused_runner and fed.served == 0 and fed.dead == 0
    assert b.said[-1] == ("      la federación no sirve a este runner desde la primera página (nube: aws): nada "
                          "en esta pasada")
    assert not fed.goto(page, GROUP) and len(page.gotos) == 2
    # Tampoco en una máquina que no se sabe (ni Azure ni AWS).
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 16 * 60, cloud="otra"), b.page()
    assert not fed.goto(page, GROUP) and fed.refused_runner and fed.pauses == 0
    assert b.said[-1].endswith("(nube: otra): nada en esta pasada")
    # En Azure, la espera de hoy.
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 16 * 60, cloud="azure"), b.page()
    assert not fed.goto(page, GROUP)
    assert fed.pauses == 1 and fed.probes > 0 and C.BRAKE_PAUSE in b.slept and not fed.refused_runner
    # En AWS con una página ya servida antes del freno, también.
    b = Brake(start=1003.0)
    fed, page = b.fed(deadline=1000.0 + 16 * 60, cloud="aws"), b.page()
    assert fed.goto(page, GROUP + "&CodJornada=3") and not fed.goto(page, GROUP)
    assert fed.pauses == 1 and fed.probes > 0 and not fed.refused_runner


def test_nube(tmp_path, monkeypatch):
    """La nube del runner, por el fabricante de la máquina (/sys/class/dmi/id/sys_vendor): «Microsoft
    Corporation» en Azure, «Amazon EC2» en AWS; lo que no se lee o es otra cosa, «otra». Sin darla,
    Federacion la lee."""
    assert C.nube(lambda: "Microsoft Corporation\n") == "azure"
    assert C.nube(lambda: "Amazon EC2\n") == "aws"
    assert C.nube(lambda: "QEMU") == "otra"

    def unreadable():
        raise OSError("sin /sys")
    assert C.nube(unreadable) == "otra"
    vendor = tmp_path / "sys_vendor"
    vendor.write_text("Amazon EC2\n")
    monkeypatch.setattr(C, "SYS_VENDOR", str(vendor))
    assert C.nube() == "aws" and Brake().fed().cloud == "aws"
    monkeypatch.setattr(C, "SYS_VENDOR", str(tmp_path / "no-esta"))
    assert C.nube() == "otra"


def test_a_403_is_a_page_that_did_not_load_but_not_a_brake_signal():
    """Un 403 (o otro 4xx que no es el 429) no carga, con sus reintentos, como un 500: no es señal del freno
    (BRAKE_STATUSES no cambia), y tres seguidas sin cargar bloquean (BLOCKED_AFTER) si la federación no
    sirve otra página."""
    assert 403 not in C.BRAKE_STATUSES
    why = []
    assert not C.goto(FakePage(statuses=[403] * 3), GROUP, sleep=lambda s: None, log=lambda *_: None, why=why)
    assert why == ["responde 403"] * 3 and C.REFUSED not in why
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60, max_pauses=0), b.page()
    page.statuses = [403] * (3 * C.BLOCKED_AFTER + 1)       # cada una con sus 3 intentos, y la de competiciones
    for n in range(C.BLOCKED_AFTER - 1):
        assert not fed.goto(page, GROUP) and fed.brakes == 0 and not fed.blocked
    assert not fed.goto(page, GROUP)
    assert fed.blocked and fed.failures == C.BLOCKED_AFTER and fed.served == 0


def test_a_503_or_a_429_is_a_brake_signal_without_asking_another_page():
    """Un 503 o un 429 es la federación que no sirve («no disponible», «demasiadas peticiones»), no la página:
    señal del freno (`brakes`) en cada página que lo recibe, cargue o no tras sus reintentos, y la racha
    que forman hace la pausa sin probar otra página (su respuesta no distingue nada: el freno puede
    pasarse justo entonces). Un 500 no lo es: puede ser la URL."""
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    good = GROUP + "&CodJornada=3"
    page.statuses = [200, 503, 200, 429, 429, 429, 500, 500, 500]
    assert fed.goto(page, good) and fed.goto(page, GROUP)
    assert fed.brakes == 1 and fed.brake_marks == [1] and fed.pauses == 0
    assert not fed.goto(page, GROUP) and fed.brakes == 2 and fed.brake_marks == [1, 2]
    assert not fed.goto(page, GROUP) and fed.brakes == 2 and fed.failures == 2
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1000.0 + 25 * 60), b.page()
    page.statuses = [200] + [503] * 3 * C.BLOCKED_AFTER + [200]
    assert fed.goto(page, good)
    for n in range(C.BLOCKED_AFTER - 1):
        assert not fed.goto(page, GROUP)
    assert fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos] == [good] + [GROUP] * (3 * C.BLOCKED_AFTER + 1)       # sin probar otra
    assert fed.pauses == 1 and fed.resumed == 1 and fed.brakes == C.BLOCKED_AFTER


def test_no_page_starts_past_the_deadline_after_its_interval():
    """El plazo se mira cuando la página EMPEZARÍA, tras la espera del intervalo: con el plazo dentro de esa
    espera, no se pide, y no cuenta como fallo de la federación. Si se mirara antes de esperar, una
    página podría empezar hasta un intervalo (7 s, 14 tras frenar) pasado el plazo. La espera sí se hace: el
    bot ve el plazo agotado (clock() > deadline) y deja el resto para otra pasada."""
    b = Brake(start=10 ** 9)
    fed, page = b.fed(deadline=1005.0), b.page()
    assert fed.goto(page, GROUP)          # a las 1000; la página, 2 s
    b.t += 1                              # el lector y la pausa
    assert not fed.goto(page, GROUP)      # empezaría a las 1007
    assert b.starts == [1000.0] and fed.pages == 1 and fed.failures == 0 and not fed.blocked
    assert b.t > fed.deadline and fed.brakes == 0


def test_an_empty_page_is_a_brake_signal_even_if_it_loads_at_the_first_probe():
    """Cada página vacía es una señal del freno (`brakes`, y en `brake_marks` las páginas servidas hasta
    entonces), también si carga en el primer sondeo (un bloqueo corto, como el de 122 s medido): el bot
    (run_passes) no da por error un grupo cuya lectura la tuvo."""
    b = Brake(start=1000.0, end=1030.0)
    fed, page = b.fed(deadline=1000.0 + 33 * 60), b.page()
    assert fed.goto(page, GROUP)
    assert b.slept == [5.0, C.BRAKE_PAUSE] and fed.pauses == 1 and fed.resumed == 1 and fed.probes == 1
    assert fed.brakes == 1 and fed.brake_marks == [0] and fed.served == 1 and fed.unserved == 0


class TargetClosedError(Exception):
    """La de Playwright cuando la página o el navegador ya se cerraron (Chromium caído)."""


class ClosedPage(FakePage):
    """Una página que se cierra (el navegador cae) tras `serves` cargas."""
    def __init__(self, serves=0, **kw):
        super().__init__(**kw)
        self.serves = serves

    def is_closed(self):
        return len(self.gotos) >= self.serves

    def goto(self, url, wait_until=None, timeout=None):
        if self.is_closed():
            self.gotos.append((url, wait_until))
            raise TargetClosedError("Target page, context or browser has been closed")
        return super().goto(url, wait_until, timeout)


def test_a_closed_browser_is_not_the_federation_braking():
    """Si Chromium cae (la página o el navegador cerrados), no es la federación: ni reintentos ni pausas
    largas, y nada más en esta pasada (`closed`, `blocked`): no son tres páginas «no carga» con sus esperas
    y tres pausas de 5 min («la federación frena») con sus grupos sin error, como un freno."""
    b = Brake(start=10 ** 9)
    fed = b.fed(deadline=1000.0 + 25 * 60)
    page = ClosedPage(serves=2)
    good = GROUP + "&CodJornada=3"
    assert fed.goto(page, good) and fed.goto(page, GROUP)
    assert not fed.goto(page, GROUP + "&CodJornada=4")
    assert fed.closed and fed.blocked and fed.pauses == 0 and fed.brakes == 0 and fed.unserved == 0
    assert len(page.gotos) == 3 and 15 not in b.slept and 300 not in b.slept
    assert "      el navegador se ha cerrado: nada más en esta pasada" in b.said
    assert not any("frena" in s for s in b.said)
    assert not fed.goto(page, GROUP) and len(page.gotos) == 3                # nada más
    assert fed.parada == "navegador"
    # También si se cierra al probar otra página (tras una racha de 500): sin pausa ni señal del freno.
    b = Brake(start=10 ** 9)
    fed = b.fed(deadline=1000.0 + 25 * 60)
    page = ClosedPage(serves=1 + 3 * C.BLOCKED_AFTER, statuses=[200] + [500] * 3 * C.BLOCKED_AFTER)
    assert fed.goto(page, good)
    for n in range(C.BLOCKED_AFTER):
        assert not fed.goto(page, GROUP)
    assert [u for u, _ in page.gotos][-1] == good and fed.closed and fed.pauses == 0 and fed.brakes == 0
    # goto, sin Federacion: tampoco reintenta (el motivo, CLOSED).
    why, slept = [], []
    assert not C.goto(ClosedPage(), GROUP, sleep=slept.append, log=lambda *_: None, why=why)
    assert why == [C.CLOSED] and slept == []


def test_the_brake_wait_is_set_by_environment(monkeypatch):
    """FIFLP_BRAKE_PAUSE_MIN, la primera espera (4 min); FIFLP_BRAKE_PROBE_S, cada cuánto el sondeo (60 s;
    menos de 30 no: no es educado); FIFLP_BRAKE_MAX_MIN, el tope de cada freno (20 min);
    FIFLP_BRAKE_PAUSES, cuántos frenos se esperan por pasada (uno por defecto; «sin», sin tope), y con 0,
    ninguno."""
    assert C.brake_pause_seconds({}) == C.BRAKE_PAUSE == 240
    assert C.brake_pause_seconds({"FIFLP_BRAKE_PAUSE_MIN": "7,5"}) == 450
    for bad in ("", "x", "-1", "0"):
        assert C.brake_pause_seconds({"FIFLP_BRAKE_PAUSE_MIN": bad}) == 240, bad
    assert C.brake_probe_seconds({}) == C.BRAKE_PROBE == 60
    assert C.brake_probe_seconds({"FIFLP_BRAKE_PROBE_S": "90"}) == 90
    for bad in ("", "x", "-1", "0", "10", "29,5"):
        assert C.brake_probe_seconds({"FIFLP_BRAKE_PROBE_S": bad}) == 60, bad
    assert C.brake_cap_seconds({}) == C.BRAKE_CAP == 1200
    assert C.brake_cap_seconds({"FIFLP_BRAKE_MAX_MIN": "12"}) == 720
    for bad in ("", "x", "-1", "0"):
        assert C.brake_cap_seconds({"FIFLP_BRAKE_MAX_MIN": bad}) == 1200, bad
    assert C.brake_pauses({}) == C.BRAKE_PAUSES == 1
    assert C.brake_pauses({"FIFLP_BRAKE_PAUSES": "0"}) == 0          # ninguno
    assert C.brake_pauses({"FIFLP_BRAKE_PAUSES": "5"}) == 5
    assert C.brake_pauses({"FIFLP_BRAKE_PAUSES": "sin"}) is None      # sin tope
    assert C.brake_pauses({"FIFLP_BRAKE_PAUSES": " Sin "}) is None
    for bad in ("x", "-1", "1.5", ""):
        assert C.brake_pauses({"FIFLP_BRAKE_PAUSES": bad}) == 1, bad
    assert Brake().fed(max_pauses=None).max_pauses is None and Brake().fed().max_pauses == 1
    # Sin esperas: una página vacía para la pasada, sin esperar nada.
    b = Brake(start=1000.0)
    fed, page = b.fed(deadline=1000.0 + 33 * 60, max_pauses=0), b.page()
    assert not fed.goto(page, GROUP) and fed.blocked and b.slept == [5.0] and fed.pauses == 0   # solo la otra
    assert b.said[-1] == "      la federación frena (sin esperas: FIFLP_BRAKE_PAUSES=0): nada más en esta pasada"
    # Con un tope de frenos: el primero se espera; el siguiente, ya no.
    b = Quota(per_ip=2, lasts=(300, 300))
    fed, page = b.fed(deadline=1000.0 + 33 * 60, max_pauses=1), b.page()
    assert all(fed.goto(page, url) for url in pages(4))
    assert not fed.goto(page, pages(1, 5)[0]) and fed.blocked and fed.pauses == 1
    assert b.said[-1] == "      la federación frena otra vez, y ya se esperó 1 (FIFLP_BRAKE_PAUSES): nada más en esta pasada"
    # Y desde el entorno, como en el bot.
    for name, value in {"FIFLP_BRAKE_PAUSE_MIN": "3", "FIFLP_BRAKE_PROBE_S": "45", "FIFLP_BRAKE_MAX_MIN": "8",
                        "FIFLP_BRAKE_PAUSES": "2"}.items():
        monkeypatch.setenv(name, value)
    fed = Brake().fed()
    assert (fed.pause_seconds, fed.probe_seconds, fed.cap_seconds, fed.max_pauses) == (180, 45, 480, 2)


def test_the_bot_adapter_keeps_the_readers_and_counts_pages(monkeypatch):
    import fetch_fiflp_2425 as F
    monkeypatch.setattr(C, "pause", lambda extra=0: None)
    fed = C.Federacion(F, deadline=time.monotonic() + 60, interval=0)
    assert fed.BASE == F.BASE
    assert fed.parse_standings is F.parse_standings and fed.parse_matches is F.parse_matches
    page = FakePage()
    assert fed.goto(page, GROUP)
    fed.delay()
    assert fed.pages == 1 and page.waits


# ── Las tandas del histórico: tope de peticiones, motivo de parada y resumen ──
# (la federación falsa de federacion_falsa.py: el cupo con sus bloqueos, la página muerta, el runner rechazado)

URL = "https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21&CodCompeticion=9&CodGrupo=1"


def jornadas(n):
    return [f"{URL}&CodJornada={k}" for k in range(1, n + 1)]


def test_una_tanda_para_en_su_tope_de_peticiones():
    f = FederacionFalsa(lambda url: Pagina(), Reloj())
    fed, page = f.fed(deadline=1000.0 + 3600, max_pages=5), f.page()
    assert [fed.goto(page, u) for u in jornadas(7)] == [True] * 5 + [False, False]
    assert len(f.pedidas) == 5 and fed.pages == 5 and fed.topped and fed.blocked and fed.parada == "tope"


def test_ninguna_peticion_pasa_del_tope_ni_en_un_freno():
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=3, bloqueos=(None,))
    fed, page = f.fed(deadline=1000.0 + 3600, max_pages=5, max_pauses=1), f.page()
    for u in jornadas(6):
        fed.goto(page, u)
    assert len(f.pedidas) <= 5 and fed.parada == "tope"


def test_parada_dice_por_que_para():
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=15, bloqueos=(None,))
    fed, page = f.fed(deadline=1000.0 + 3600, max_pauses=0), f.page()
    assert fed.parada is None
    for u in jornadas(20):
        fed.goto(page, u)
    assert fed.parada == "freno" and fed.served == 15
    aws = FederacionFalsa(lambda url: Pagina(), Reloj(), nube="aws", rechaza=True)
    fed = aws.fed(deadline=1000.0 + 3600)
    assert not fed.goto(aws.page(), URL) and fed.parada == "runner" and len(aws.pedidas) <= 2
    tarde = FederacionFalsa(lambda url: Pagina(), Reloj())
    fed = tarde.fed(deadline=999.0)                            # el plazo ya pasó
    assert not fed.goto(tarde.page(), URL) and fed.parada == "plazo"


def test_una_pagina_muerta_no_para_la_tanda():
    muerta = jornadas(3)[1]
    f = FederacionFalsa(lambda url: Pagina(html="") if url == muerta else Pagina(), Reloj())
    fed, page = f.fed(deadline=1000.0 + 3600, max_pauses=0), f.page()
    assert [fed.goto(page, u) for u in jornadas(3)] == [True, False, True]
    assert fed.dead == 1 and fed.parada is None and fed.pauses == 0


def test_el_resumen_de_una_tanda(tmp_path):
    muerta = jornadas(8)[5]
    f = FederacionFalsa(lambda url: Pagina(html="") if url == muerta else Pagina(), Reloj())
    fed, page = f.fed(deadline=1000.0 + 3600), f.page()
    for u in jornadas(8):
        fed.goto(page, u)
    r = fed.resumen()
    assert r["muertas"] == 1 and r["servidas"] >= 7 and r["esperas"] == 0 and r["frenos"] == 0
    assert r["parada"] is None and r["nube"] == "azure" and r["runner_rechazado"] is False
    assert r["esperas_s"] == [] and r["esperas_sirvio"] == []
    C.guardar_resumen(tmp_path / "r.json", fed, {"goleadores:2025-2026": {"completo": False, "pendientes": 3, "no_disponible": 0}})
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert data["muertas"] == 1 and data["partes"]["goleadores:2025-2026"]["pendientes"] == 3 and "escrito" in data
    assert data["esperas_s"] == [] and data["esperas_sirvio"] == []
    C.guardar_resumen(None, fed, {})                           # sin ruta, nada (y no lanza)


def test_para_tanda():
    """Desde el 26/11/2026 una ejecución de una tanda espera UN freno, como el bot (ESPERAS_TANDA, 1); con
    HISTORICO_ESPERAS=0, ninguno. La variable del repositorio sin poner llega vacía: la de siempre. Lo que no se
    entiende, ninguna: lo prudente es pedir menos."""
    import fetch_fiflp_2425 as F
    fed = C.para_tanda(F, 30, 0, clock=lambda: 100.0, cloud="azure", env={})
    assert fed.deadline == 1900.0 and fed.max_pages is None and fed.max_pauses == C.ESPERAS_TANDA == 1
    assert (fed.interval, fed.cap_seconds, fed.pause_seconds) == (C.DEFAULT_INTERVAL, C.BRAKE_CAP, C.BRAKE_PAUSE)
    for valor, esperas in (("0", 0), ("1", 1), ("2", 2), ("", 1), (" ", 1), ("mucho", 0), ("-1", 0)):
        assert C.para_tanda(F, 30, 2000, cloud="azure", env={"HISTORICO_ESPERAS": valor}).max_pauses == esperas, valor
    assert C.para_tanda(F, 30, 2000, cloud="azure", env={}).max_pages == 2000


def _hasta_que_pare(fed, page, urls):
    """Pide `urls` en orden mientras la federación no pare (Federacion.parada): las que cargaron."""
    leidas = []
    for u in urls:
        if fed.parada is not None:
            break
        if fed.goto(page, u):
            leidas.append(u)
    return leidas


def test_una_tanda_espera_un_freno_y_acaba_en_el_segundo():
    """Lo medido el 26/11/2026 (la primera ejecución larga del carril en Azure): 150 páginas y el freno. Con el
    cupo de 150 por IP, el bloqueo de ~5 min y el segundo más largo (escala dentro de la misma IP): la tanda espera
    el primero (4 min sin pedir nada y un sondeo por minuto), vuelve a leer en cuanto sirve, y el segundo acaba la
    ejecución, sin esperarlo. El resumen dice cuánto duró la espera y si volvió a servir; lo que se da por leído es
    solo lo que cargó (la que frenó, en el sondeo)."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=150, bloqueos=(300, 900))
    fed, page = f.tanda(300, 2000), f.page()
    urls = jornadas(600)
    leidas = _hasta_que_pare(fed, page, urls)
    assert leidas == urls[:300] and fed.served == 300
    assert fed.pauses == 1 and fed.resumed == 1 and fed.brakes == 2 and fed.parada == "freno"
    assert f.reloj.dormido.count(C.BRAKE_PAUSE) == 1
    r = fed.resumen()
    assert r["frenos_tras"] == [150, 150] and r["esperas"] == 1 and r["reanudadas"] == 1
    # La vacía, la otra página (vacía: el freno), 4 min, un sondeo vacío y otro al minuto: a los 300 s sirve.
    assert r["esperas_s"] == [300] and r["esperas_sirvio"] == [True]
    assert r["parada"] == "freno" and r["servidas"] == 300
    assert "      la federación vuelve a servir a los 300 s: se sigue" in f.dicho


def test_una_tanda_sin_esperas_acaba_en_el_primer_freno():
    """HISTORICO_ESPERAS=0: ninguna espera; el primer freno acaba la ejecución (el día, lo decide el carril)."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=150, bloqueos=(300, 900))
    fed, page = f.tanda(300, 2000, env={"HISTORICO_ESPERAS": "0"}), f.page()
    assert _hasta_que_pare(fed, page, jornadas(600)) == jornadas(150)
    r = fed.resumen()
    assert r["frenos_tras"] == [150] and r["esperas"] == 0 and r["esperas_s"] == [] and r["esperas_sirvio"] == []
    assert r["parada"] == "freno" and C.BRAKE_PAUSE not in f.reloj.dormido


def test_una_espera_que_no_vuelve_dice_cuanto_espero():
    """Un bloqueo que no se pasa en el tope de cada freno (20 min): la ejecución acaba, y el resumen lo dice."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=150, bloqueos=(None,))
    fed, page = f.tanda(300, 2000), f.page()
    assert len(_hasta_que_pare(fed, page, jornadas(600))) == 150
    r = fed.resumen()
    # Hasta rendirse: el último sondeo cabe en el tope, y cuenta lo que tardan él y la otra página.
    assert r["esperas_sirvio"] == [False] and C.BRAKE_CAP - C.BRAKE_PROBE < r["esperas_s"][0] <= C.BRAKE_CAP + 15
    assert r["parada"] == "freno" and r["frenos_tras"] == [150]


def test_la_espera_de_una_tanda_no_se_come_el_plazo():
    """Una tanda que frena sin plazo para la espera y para leer después (BRAKE_ROOM) no la espera: acaba ya, y lo
    leído se guarda y se sube dentro del plazo de la ejecución (historico.hasta: 20 min antes de una ventana)."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=150, bloqueos=(300, 900))
    fed, page = f.tanda(20, 2000), f.page()                   # 150 páginas a 7 s son ~17,5 min
    assert len(_hasta_que_pare(fed, page, jornadas(600))) == 150
    assert fed.pauses == 0 and fed.parada == "freno" and C.BRAKE_PAUSE not in f.reloj.dormido
    assert f.reloj.t <= fed.deadline
    # Y con plazo, la espera y los sondeos acaban antes del plazo con sitio para leer (nunca después).
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=150, bloqueos=(None,))
    fed, page = f.tanda(30, 2000), f.page()
    _hasta_que_pare(fed, page, jornadas(600))
    assert fed.pauses == 1 and f.reloj.t <= fed.deadline - C.BRAKE_ROOM + C.BRAKE_PROBE


def test_el_bot_sigue_sin_tope():
    import fetch_fiflp_2425 as F
    fed = C.Federacion(F, cloud="azure")
    assert fed.max_pages is None and not fed.topped and fed.parada is None and fed.max_pauses == C.BRAKE_PAUSES
    assert C.parada_de(object()) is None and C.parada_de(fed) is None


def test_el_tope_se_dice_una_vez_en_el_registro():
    f = FederacionFalsa(lambda url: Pagina(), Reloj())
    fed, page = f.fed(deadline=1000.0 + 3600, max_pages=2), f.page()
    for u in jornadas(5):
        fed.goto(page, u)
    assert f.dicho.count("      se llega al tope de 2 peticiones de esta ejecución: nada más") == 1


def test_el_tope_en_la_comprobacion_de_otra_pagina_no_es_ni_freno_ni_muerta():
    """Si el tope llega justo cuando una página sale vacía, no se puede preguntar por otra: no se sabe si es
    el freno o esta página. Ni una cosa ni otra: queda sin leer (lo pendiente de la tanda) y para por el tope."""
    muerta = jornadas(3)[2]
    f = FederacionFalsa(lambda url: Pagina(html="") if url == muerta else Pagina(), Reloj())
    fed, page = f.fed(deadline=1000.0 + 3600, max_pages=3), f.page()
    assert [fed.goto(page, u) for u in jornadas(3)] == [True, True, False]
    assert f.pedidas == jornadas(3) and fed.dead == 0 and fed.brakes == 0 and fed.pauses == 0
    assert fed.parada == "tope" and C.BRAKE_PAUSE not in f.reloj.dormido


def test_el_tope_corta_la_espera_del_freno_sin_dormir_de_mas():
    """Con esperas (HISTORICO_ESPERAS) y un tope que llega durante los sondeos: el sondeo que no cabe ni se
    pide, la espera acaba en ese momento (sin otro minuto de espera para nada) y el registro dice el tope,
    no el plazo."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=2, bloqueos=(None,))
    fed, page = f.fed(deadline=1000.0 + 3600, max_pages=6, max_pauses=1), f.page()
    for u in jornadas(4):
        fed.goto(page, u)
    # 2 servidas, la vacía y la otra; tras 4 min, el sondeo y la otra (la 6.ª): sin esperar al siguiente sondeo.
    assert len(f.pedidas) == 6 and fed.pauses == 1 and fed.probes == 1 and fed.parada == "tope"
    assert f.reloj.dormido.count(C.BRAKE_PAUSE) == 1 and C.BRAKE_PROBE - 9.0 not in f.reloj.dormido
    assert not any("se acaba el plazo" in s for s in f.dicho)
    assert "      se llega al tope de 6 peticiones de esta ejecución: nada más" in f.dicho


def test_sin_tope_la_federacion_pide_lo_mismo_que_la_del_bot():
    """La norma: la Federacion del bot no cambia. Con el mismo cupo, la misma página muerta y el mismo plazo,
    sin max_pages y con max_pages=None, petición a petición lo mismo."""
    def correr(**kw):
        muerta = jornadas(30)[20]
        f = FederacionFalsa(lambda url: Pagina(html="") if url == muerta else Pagina(), Reloj(), cupo=15,
                            bloqueos=(300, 900))
        fed, page = f.fed(deadline=1000.0 + 16 * 60, **kw), f.page()
        return [fed.goto(page, u) for u in jornadas(30)], f.pedidas, f.reloj.dormido, f.dicho
    assert correr() == correr(max_pages=None)


# ── Con un navegador de verdad ────────────────────────────────────────────────

@pytest.fixture
def sync_api():
    """Playwright, si está (update.yml lo instala; tests.yml no): sin él solo se saltan estas pruebas,
    no las de arriba."""
    return pytest.importorskip("playwright.sync_api")


PAGE = """<!doctype html><html><head>
<link rel="stylesheet" href="/digits.css">
<link rel="stylesheet" href="http://localhost:{port}/never.css">
</head><body><p id="score"><i class="fa-7"></i> - <i class="fa-2"></i></p></body></html>"""
DIGITS = "".join(f'.fa-{d}::before{{content:"{d}"}}' for d in range(10))


@pytest.fixture
def server():
    """La hoja de las cifras tarda 1,2 s (como files.fiflp.com en un mal momento); otra, de un host
    que no es de la federación, no llega nunca (la publicidad bloqueada)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/digits.css":
                time.sleep(1.2)
                body, kind = DIGITS, "text/css"
            elif self.path == "/never.css":
                time.sleep(8)
                body, kind = "", "text/css"
            else:
                body, kind = PAGE.format(port=self.server.server_address[1]), "text/html"
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/acta"
    httpd.shutdown()


def _browser_page(p):
    try:
        browser = p.chromium.launch(headless=True)
    except Exception as e:                      # sin Chromium instalado
        pytest.skip(f"sin navegador: {e}")
    return browser, browser.new_page()


def test_the_page_is_flattened_only_after_the_federation_stylesheets(sync_api, server):
    from fiflp_render import flatten
    with sync_api.sync_playwright() as p:
        browser, page = _browser_page(p)
        try:
            start = time.monotonic()
            assert C.goto(page, server, ready_ms=5000, hosts=("127.0.0.1",), log=lambda *_: None)
            took = time.monotonic() - start
            flatten(page)
            score = page.inner_text("#score")
        finally:
            browser.close()
    # Las cifras salen de la hoja que tardaba; la que no es de la federación no se espera.
    assert score.replace(" ", "") == "7-2"
    assert 1.0 < took < 5.0


def test_the_exact_braking_page_in_a_real_browser_is_empty(sync_api):
    """La respuesta del freno, tal cual la guardó la sonda (probe-fiflp): 39 bytes."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><head></head><body></body></html>" if self.path == "/vacia" else b"<html><body><p>x</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(base + "/vacia")
            assert C._empty(page)
            page.goto(base + "/llena")
            assert not C._empty(page)
            browser.close()
    finally:
        httpd.shutdown()


def test_a_503_in_a_real_browser_is_not_a_loaded_page(sync_api):
    """Chromium no da error con un 503 de Apache (el bloqueo de la federación): se ve en el estado."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><head><title>503 Service Unavailable</title></head><body></body></html>"
            self.send_response(503)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    slept = []
    try:
        with sync_api.sync_playwright() as p:
            browser, page = _browser_page(p)
            try:
                loaded = C.goto(page, f"http://127.0.0.1:{httpd.server_address[1]}/NFG_CmpPartido?CodActa=1",
                                ready_ms=500, sleep=slept.append, log=lambda *_: None)
            finally:
                browser.close()
    finally:
        httpd.shutdown()
    assert not loaded and slept == [15, 30]


def test_a_closed_page_in_a_real_browser_is_not_a_page_that_does_not_load(sync_api):
    """Con Chromium de verdad: tras page.close(), goto lo ve (TargetClosedError, page.is_closed()) y no
    reintenta: no es la federación."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><body><p>x</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/NFG_CmpPartido?CodActa=1"
    why, slept = [], []
    try:
        with sync_api.sync_playwright() as p:
            browser, page = _browser_page(p)
            try:
                assert C.goto(page, url, ready_ms=500, sleep=slept.append, log=lambda *_: None)
                page.close()
                loaded = C.goto(page, url, ready_ms=500, sleep=slept.append, log=lambda *_: None, why=why)
            finally:
                browser.close()
    finally:
        httpd.shutdown()
    assert not loaded and why == [C.CLOSED] and slept == []


def test_a_stylesheet_that_never_loads_only_costs_the_cap(sync_api, server):
    with sync_api.sync_playwright() as p:
        browser, page = _browser_page(p)
        try:
            start = time.monotonic()
            # Ahora la hoja lenta «es» de la federación y no llega a tiempo: se sigue con el tope.
            assert C.goto(page, server, ready_ms=400, hosts=("127.0.0.1", "localhost"), log=lambda *_: None)
            took = time.monotonic() - start
        finally:
            browser.close()
    assert took < 3.0
