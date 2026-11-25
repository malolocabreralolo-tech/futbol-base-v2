# Ampliación, parte G: descargas del histórico que respetan el freno — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el histórico de la federación (alevín de Gran Canaria de 2019-20 a 2025-26 y, después, lo que traigan las partes E y F) se baje con las mismas esperas y la misma detección del freno que el bot, sin dar nunca por leída una página vacía, en un solo carril que para solo y en verde cuando la federación no sirve, y que lo bajado se pruebe sobre una copia de la base antes de que el bot lo importe.

**Depende de:** se construye sobre la rama `freno` (árbol `/home/manolo/claude/futbol-base-v2-bot`, encargo `.superpowers/sdd/freno/task-1-brief.md`), **ya publicada en `main`** antes de empezar la tarea 1. De ella se usa, sin rehacerlo: `Federacion` distingue la página vacía con la federación sirviendo otra (página muerta: sin espera, `Federacion.dead` + 1) del freno de verdad; `fiflp_carga.nube()` y `Federacion(cloud=…)`; y un runner al que la federación no sirve desde la primera página fuera de Azure acaba al momento (`Federacion.refused_runner`). Si al empezar la rama `freno` no está en `main`, se para y se avisa: este plan no la sustituye.

**Lo medido que manda** (`docs/freno-2026-11.md` de esa rama, 840 registros de pasadas): el cupo de octubre (15 páginas por IP, ~5 min de bloqueo) no se ve desde el 21/10; en runners de **Azure** la federación sirve ~124-138 páginas por pasada de 16 min, sin freno, a todas horas (~500 páginas por hora); desde el 13/11 cerca de la mitad de los jobs de GitHub corren en **AWS**, y a AWS la federación le contesta vacío desde la primera petición, siempre (183 de 183). Lo que paraba las pasadas de v2 desde el 21/11 eran páginas muertas tomadas por freno.

**Architecture:** Los tres descargadores por tandas (`fetch_fiflp_goleadores.py`, `fetch_fiflp_detalle.py`, `fetch_fiflp_actas.py`) leen a través de `fiflp_carga.Federacion` (la del bot arreglada en la rama `freno`, con un tope de peticiones por ejecución y un motivo de parada) y llevan lo pendiente de forma explícita en sus ficheros: lo cortado por el plazo, el tope o el freno queda pendiente; una página muerta gasta un intento y, con tres, queda «no disponible en la federación». Lo que bajan va a una carpeta en cuarentena (`scripts/historico/`) que el bot no mira; un solo workflow nuevo, `historico.yml`, decide en cada ejecución qué toca (`scripts/historico.py`: bajar lo barato primero, probar una temporada ya bajada sobre una copia con todas las suites, o nada), y solo lo probado en verde pasa a `scripts/`, donde el bot lo importa como hoy. Sustituye a `actas-federacion.yml`, `goleadores-federacion.yml` y `detalle-federacion.yml`.

**Tech Stack:** Python 3.11 en Actions (3.12 en el PC) solo con la biblioteca estándar; Playwright 1.65.2 solo dentro de los `main()` de los descargadores; pytest 9.2.0 y pyyaml 6.0.3; GitHub Actions (`ubuntu-24.04`, `actions/checkout@v5`, `actions/setup-python@v6`, `actions/setup-node@v5`) y `gh`.

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (parte G y decisión 5). Lo medido: `docs/ampliacion-mapa.md`, secciones 2 y 3. Cómo lee el bot y el freno: `docs/federacion.md` («El freno de la federación», «La espera del freno», «Rellenar temporadas pasadas»). El canal de alevín: `docs/alevin.md` («Histórico», «Las actas de alevín, en su propio raw»).

**Lo ya guardado.** Medido el 25/11/2026 en este árbol: ninguna entrada de `scripts/fiflp_goleadores_*_raw.json`, `scripts/fiflp_detalle_*_raw.json` ni `scripts/fiflp_campos_raw.json` tiene `fetched` posterior al 13/10/2026 (la más nueva, del 8/10), y la última tanda de actas es del 7/10. El freno empezó el 14/10: no hay nada mal guardado que remarcar como pendiente, y este plan no tiene tarea para ello.

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-descargas`, rama `descargas`. No se toca la versión 1 (`/home/manolo/claude/futbol-base`) ni ningún otro árbol.
- Nunca una petición a fiflp.com (ni a otra web) desde el PC ni en las pruebas: páginas y federación falsas (`scripts/tests/federacion_falsa.py`, tarea 1), relojes inyectados.
- No se lanzan workflows (`gh workflow run`), no se hace `git push` ni `git stash`.
- No se ejecutan `scripts/publicar.py`, `scripts/generate_js.py` ni `scripts/fetch_futbolaspalmas.py` (tampoco con `--solo-historico`) sobre el árbol: nada que escriba `futbolbase.db` o `data-*.js`. Las pruebas usan copias y carpetas temporales.
- Ningún nombre real de niño en código, pruebas, documentos ni mensajes de commit: nombres inventados o claves.
- La base solo la escribe el bot (`update.yml` y `activar.yml`, grupo `update-data`). El carril del histórico nunca sube `futbolbase.db`, `data-*.js`, `index.html` ni `sw.js` (lo vigila `test_workflows.test_solo_el_bot_escribe_la_base`).
- Un fallo del histórico nunca deja al bot en vivo sin publicar: lo que está en `scripts/historico/` el bot no lo ve, y a `scripts/` solo pasa lo probado en verde.
- El bot en vivo no cambia: `fiflp_carga.Federacion` sin los parámetros nuevos se comporta exactamente como la de la rama `freno`; `test_fiflp_carga.py`, `test_bot_freno.py` y `test_bot_pasada_corta.py` siguen en verde sin tocarlos.
- No se intenta saltar el freno ni el rechazo a AWS: una ejecución del carril cada vez, un navegador, `FIFLP_MIN_INTERVAL` (7 s) entre peticiones; ni proxies, ni IPs en paralelo, ni cambio de identidad (cada descargador conserva su User-Agent), y **no se relanza una ejecución porque cayó en un runner rechazado** (`RELANZAR_SI_RUNNER_RECHAZADO = 0`: es una decisión del dueño, pendiente). Nunca el correo del dueño en cabeceras ni en el User-Agent.
- Si aparece el freno de verdad (una página vacía con la federación sin servir otra, o un 503/429), en el carril o en el bot en vivo, el carril no lee nada más ese día.
- Las pruebas de Python corren sin Playwright (`test_workflows.test_python_tests_run_without_playwright`): se importa solo dentro de `main()`.
- Estilo: el del fichero que se toca (comentarios y docstrings en español que explican el porqué; mensajes del registro en español; escritura atómica con `escritura.escribir_atomico`; entradas de los workflows por `env:`, nunca interpoladas en un `run:`).
- Cada commit acaba con las dos líneas `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.

## Review Focus

- **Una página muerta** (vacía siempre, con la federación sirviendo las demás: lo que paraba a v2 desde el 21/11): ni espera ni para la ejecución ni se da por leída; gasta un intento por ejecución y, tras `MAX_INTENTOS` (3), queda «no disponible en la federación», fuera de lo pendiente, y el trabajo puede acabar. Pruebas: tarea 2 `test_una_pagina_vacia_siempre_acaba_no_disponible_tras_tres_ejecuciones` y tarea 3 `test_una_jornada_que_viene_vacia_siempre_acaba_no_disponible`.
- **Un runner que la federación no sirve** (AWS): la ejecución acaba en menos de dos minutos sin leer nada, no marca nada como intentado ni pendiente de más, no gasta el tope del día, no se relanza (con `RELANZAR_SI_RUNNER_RECHAZADO = 0`) y la retoma el disparo siguiente. Pruebas: tarea 2 `test_un_runner_rechazado_no_toca_nada`, tarea 6 `test_un_runner_rechazado_no_se_relanza`.
- **Un corte a mitad de un trabajo** (el plazo, el tope del día o el freno de verdad; un grupo del detalle con 25 jornadas cortado en la 12.ª): lo leído se guarda, lo que falta queda escrito como pendiente y la ejecución siguiente pide solo eso; el trabajo no pasa a «completo». Pruebas: tarea 3 `test_un_corte_a_mitad_de_la_enumeracion_deja_las_jornadas_pendientes` y tarea 2 `test_el_calendario_de_un_grupo_se_reanuda_por_la_jornada_que_falta`.
- **Dos ejecuciones del carril en cola** (el disparo programado y un relanzamiento, o un encargo a mano): GitHub guarda una sola en espera por grupo y cancela la otra; como cada ejecución saca su trabajo de los ficheros de `scripts/historico/`, no se pierde nada, nunca corren dos, y el encargo queda escrito en su propio job antes de que el carril haga cola. Prueba: tarea 7 `test_el_encargo_no_se_pierde_si_cancelan_el_carril`.
- **Una temporada bajada rompe una prueba, hace crecer la base de más o tarda en importarse**: la prueba sobre la copia sale en rojo, no se promueve nada, el bot sigue publicando, el trabajo queda «fallo» con su motivo y no se repite solo. Pruebas: tarea 5 `test_veredicto`, tarea 6 `test_una_prueba_en_rojo_no_se_repite_sola`.

(Las ventanas de partidos, la medianoche y el cambio de hora tienen sus pruebas en la tarea 6: `test_hasta`, `test_cupo_de_hoy`.)

---

### Task 1: La lectura de las tandas: tope, motivo de parada y resumen

**Files:**
- Modify: `scripts/fiflp_carga.py` (`Federacion.__init__`, `_request`, `goto`; constantes y funciones nuevas; el final del docstring del módulo, que dice que las tandas siguen con `fetch_fiflp_2425`)
- Create: `scripts/tests/federacion_falsa.py` (no empieza por `test_`: pytest no la recoge)
- Test: `scripts/tests/test_fiflp_carga.py` (añadir), `scripts/tests/test_federacion_falsa.py` (nuevo)

**Interfaces:**
- Consumes (rama `freno`): `Federacion.dead`, `Federacion.cloud`, `Federacion.refused_runner`, `nube(leer=None) -> str`, `Federacion(..., cloud=None)`, y que `_goto` y `_wait_brake` pregunten `_serving` antes de dar una vacía por freno.
- Produces:
  - `RELANZAR_MIN = 60` — páginas servidas en una ejecución por debajo de las cuales no se relanza en seguida: en Azure, sin freno, una ejecución lee ~500 por hora; con menos de 60 (unos 7 min de lectura) algo iba mal (el freno, un runner rechazado, una caída) y se deja al disparo siguiente.
  - `MAX_INTENTOS = 3` — ejecuciones (cada una con su runner y su IP) en que una página no carga aunque la federación sirve otras, antes de dejarla «no disponible en la federación». Tres y no los cuatro de las actas del bot: el bot reintenta en pasadas de horas para dar tiempo a que la federación complete un acta recién jugada; en temporadas cerradas no hay nada que esperar, y tres IPs distintas con la misma página muerta bastan.
  - `ESPERAS_TANDA = 0` y `esperas_tanda(env=None) -> int` (`HISTORICO_ESPERAS`; lo que no se entiende, 0) — las esperas del freno por ejecución de una tanda. Cero: con el freno de verdad el carril para la ejecución y el día (tarea 6), no lo espera; la detección es la del bot (la vacía solo es freno si la federación tampoco sirve otra).
  - `Federacion(..., max_pages: int | None = None)` — tope de peticiones (`pages`, sondeos y comprobaciones de `_serving` incluidos) de la ejecución; `None`, sin tope (el bot). Ninguna petición pasa del tope: `_request` lo mira como el plazo (no pide, pone `topped = True` y devuelve `None`), también dentro de una espera o de `_serving`, y lo dice en el registro: «se llega al tope de N peticiones de esta ejecución: nada más».
  - `Federacion.topped: bool` y la propiedad `Federacion.parada -> str | None`: `"navegador"` si `closed`; si no, `"runner"` si `refused_runner`; si no, `"tope"` si `topped`; si no, `"freno"` si `halted`; si no, `"plazo"` si ya pasó `deadline`; si no, `None`.
  - `Federacion.resumen() -> dict` — `{"pedidas": pages, "servidas": served, "muertas": dead, "esperas": pauses, "reanudadas": resumed, "frenos": brakes, "frenos_tras": list(brake_after), "parada": parada, "nube": cloud, "runner_rechazado": refused_runner, "segundos_en_espera": round(paused)}`.
  - `para_tanda(scraper, minutos: float, max_pages: int | None, log=print, clock=time.monotonic, sleep=time.sleep, wall=None, cloud=None, env=None) -> Federacion` — `deadline = clock() + minutos * 60`; `max_pages` 0 o `None` es sin tope; `max_pauses = esperas_tanda(env)`; intervalo, sondeos y tope por freno, los del bot (`min_interval()`, `brake_*()`).
  - `parada_de(F) -> str | None` — `getattr(F, "parada", None)`: los lectores lo usan igual con una `Federacion` que con los `FakeF` de las pruebas de hoy (sin `parada`: `None`).
  - `guardar_resumen(path: str | Path | None, fed: Federacion, partes: dict) -> None` — con `path` `None`, nada; si no, escribe de forma atómica `{**fed.resumen(), "partes": partes, "escrito": "<ISO UTC>"}` (JSON con `indent=1` y `sort_keys=True`). `partes` es `{clave de trabajo: {"completo": bool, "pendientes": int, "no_disponible": int}}`; las claves las fija la tarea 6 («goleadores:2025-2026», «actas:2025-2026:alevin»…).
  - `scripts/tests/federacion_falsa.py`:
    - `Reloj(t=1000.0)` con `clock()`, `sleep(s)` (suma a `t` y apunta en `dormido`) y `wall()` (`datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc) + (t − 1000) s`).
    - `Pagina(html="<html><body>x</body></html>", opciones: dict[str, list[tuple[str, str]]] = {}, datos=None)` — `opciones` por nombre de desplegable (`"competicion"`, `"grupo"`, `"jornada"`) → `[(valor, texto)]`; `datos`, lo que dan `parse_standings` y `parse_matches` del raspador falso.
    - `FederacionFalsa(sitio: Callable[[str], Pagina | None], reloj: Reloj, cupo: int | None = None, bloqueos: tuple[float | None, ...] = (300,), coste: float = 2.0, nube: str = "azure", rechaza: bool = False)` — sin `cupo`, sirve todo (lo de hoy en Azure); con él, `cupo` documentos por «IP» y después vacías durante el siguiente de `bloqueos` (segundos desde la primera vacía; `None`, no vuelve), como `Quota` de `test_fiflp_carga.py`: el freno de verdad; con `rechaza=True` (y `nube="aws"`), todo vacío desde la primera; una `Pagina(html="")` es una página muerta (vacía siempre, la federación sirve las demás); `sitio(url)` `None` es una página que no existe (responde 404). `.page()` da la página falsa; `.pedidas` (las URL, en orden); `.dicho` (el registro); `.fed(**kw)` da una `fiflp_carga.Federacion` con `RaspadorFalso`, `interval=7.0`, `cloud=nube` y el reloj; `.ip_nueva()` vuelve a empezar el cupo (otra ejecución).
    - La página falsa responde a `goto` (avanza el reloj `coste` s), a `evaluate` con `EMPTY_JS` (vacía si frena o si el `html` es `""`), con `FLATTEN_JS` (`0`), con `CRESTS_JS` (`{}`) y con los guiones de desplegable según su forma: los que acaban en `.map(o => o.value)` → lista de valores; `[o.value, o.text…]` → pares; `({value: o.value, text…})` → `{"value", "text"}`; `({id: o.value, name…})` → `{"id", "name"}`; a `content()` (el `html`, o el de la página del freno), `wait_for_function`, `wait_for_timeout(ms)` (avanza el reloj), `query_selector_all` (`[]`), `frames` (`[]`) e `is_closed()` (`False`).
    - `RaspadorFalso` con `BASE = "https://www.fiflp.com/pnfg/NPcd"`, `parse_standings(page)` y `parse_matches(page)`: los `datos` de la `Pagina` que está cargada (o `[]`).

- [ ] **Step 1: Escribir las pruebas que fallan** en `scripts/tests/test_fiflp_carga.py`, con la federación falsa (las cuentas exactas de peticiones de un freno dependen de cómo la rama `freno` comprueba la otra página: aquí no se fijan):

```python
from federacion_falsa import FederacionFalsa, Pagina, Reloj

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
    C.guardar_resumen(tmp_path / "r.json", fed, {"goleadores:2025-2026": {"completo": False, "pendientes": 3, "no_disponible": 0}})
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert data["muertas"] == 1 and data["partes"]["goleadores:2025-2026"]["pendientes"] == 3 and "escrito" in data
    C.guardar_resumen(None, fed, {})                           # sin ruta, nada (y no lanza)

def test_para_tanda():
    import fetch_fiflp_2425 as F
    fed = C.para_tanda(F, 30, 0, clock=lambda: 100.0, cloud="azure", env={})
    assert fed.deadline == 1900.0 and fed.max_pages is None and fed.max_pauses == 0
    assert (fed.interval, fed.cap_seconds) == (C.DEFAULT_INTERVAL, C.BRAKE_CAP)
    assert C.para_tanda(F, 30, 2000, cloud="azure", env={"HISTORICO_ESPERAS": "1"}).max_pauses == 1
    assert C.para_tanda(F, 30, 2000, cloud="azure", env={"HISTORICO_ESPERAS": "mucho"}).max_pauses == 0
    assert C.para_tanda(F, 30, 2000, cloud="azure", env={}).max_pages == 2000

def test_el_bot_sigue_sin_tope():
    import fetch_fiflp_2425 as F
    fed = C.Federacion(F, cloud="azure")
    assert fed.max_pages is None and not fed.topped and fed.parada is None and fed.max_pauses == C.BRAKE_PAUSES
    assert C.parada_de(object()) is None and C.parada_de(fed) is None
```

  En `test_a_closed_browser_is_not_the_federation_braking`, añadir `assert fed.parada == "navegador"`. En `scripts/tests/test_federacion_falsa.py`: `test_la_federacion_falsa_frena_como_la_medida` (con `cupo=15`, las 15 primeras cargan y la 16.ª da `True` con `EMPTY_JS`; tras `bloqueos[0]` s vuelve a servir; con `.ip_nueva()`, otras 15), `test_sin_cupo_sirve_todo`, `test_rechaza_todo_desde_la_primera`, `test_una_pagina_muerta_viene_vacia_y_las_demas_no`, `test_una_pagina_que_no_existe_responde_404` y `test_los_desplegables_en_sus_cuatro_formas`.

- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_carga.py scripts/tests/test_federacion_falsa.py` — Expected: FAIL (`unexpected keyword argument 'max_pages'`, `No module named 'federacion_falsa'`).
- [ ] **Step 3: Implementar** lo de Interfaces. El docstring del módulo pasa a decir que las tandas del histórico leen con `para_tanda` (la detección del bot, sin esperas por defecto y con un tope de peticiones por ejecución) y que solo `fetch_fiflp_islas` (la activación, temporada en curso) sigue con el paso de `fetch_fiflp_2425`.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_carga.py scripts/tests/test_federacion_falsa.py scripts/tests/test_bot_freno.py scripts/tests/test_bot_pasada_corta.py scripts/tests/test_fiflp_fresca.py` — Expected: todo en verde (los de antes, sin tocarlos).
- [ ] **Step 5: Commit.** Asunto: «Federación: tope de peticiones, motivo de parada y resumen para las tandas».

---

### Task 2: Goleadores y detalle, con la lectura del bot y lo pendiente escrito

**Files:**
- Modify: `scripts/fetch_fiflp_goleadores.py` (`done`, `scrape_group`, `scrape_crests`, `run`, `main`)
- Modify: `scripts/fetch_fiflp_detalle.py` (`group_done`, `scrape_group`, `_jornadas`, `run_groups`, `run_campos`, `main`)
- Modify: `.github/workflows/detalle-federacion.yml` (solo la condición de «Siguiente tanda»; el fichero se borra en la tarea 7)
- Test: `scripts/tests/test_fiflp_goleadores.py`, `scripts/tests/test_fiflp_detalle.py`, `scripts/tests/test_workflows.py` (añadir)

**Interfaces:**
- Consumes: `fiflp_carga.para_tanda`, `parada_de`, `guardar_resumen`, `MAX_INTENTOS`, `RELANZAR_MIN`; `federacion_falsa` (pruebas).
- Produces:
  - Regla común: tras un `F.goto` que da `False`, si `parada_de(F)` no es `None` (el freno de verdad, el tope, el plazo, el navegador o un runner rechazado) **no se escribe nada de esa entrada** (se queda la de antes, si la había), no se suma ningún intento, se guarda lo ya leído y la ejecución acaba. Si es `None` (una página muerta, con `F.dead` + 1, o una que no existe: la federación sirve otras y esta no), la entrada queda con `"ok": false` y `"intentos"` + 1 (como mucho uno por ejecución); con `MAX_INTENTOS`, además `"no_disponible": true` («no disponible en la federación»), que cuenta como hecha y que los importadores ya saltan (miran `ok`). Una entrada `ok` nunca se reescribe con datos vacíos.
  - Goleadores: `done(entry) -> bool` es `ok` o `no_disponible`. `scrape_group(page, F, season, comp, grupo) -> tuple[list, list, bool]` da `ok` solo si cargaron **las dos** páginas (clasificación y goleadores; hoy basta la segunda). `scrape_crests(page, F, season, comp, grupo, teams) -> tuple[dict, bool]` (escudos, ¿sin parada?): `entry["crests"]` solo se pone si no hubo parada.
  - Goleadores: la lista de grupos de cada competición se guarda al leerla en `fiflp_goleadores_<S>_grupos.json` (junto al raw; `{"grupos": {comp: [[valor, texto]]}, "intentos": {comp: n}}`; ningún importador lo lee: los patrones de `reconstruir.py` y de los importadores son estrictos) y la página de la competición no se vuelve a pedir. Una que carga sin grupos suma `intentos`; con `MAX_INTENTOS`, `[]` (sin grupos, hecha).
  - Goleadores: `run(page, F, seasons, deadline, log=print, crests_only=False, categories=None, escudos=True, partes=None) -> bool` — el `bool` de hoy («completo»); con `escudos=False` no pide jornadas para los escudos; `partes` (un dict) se rellena con `{"goleadores:<S>" (o "escudos:<S>" con crests_only): {"completo", "pendientes", "no_disponible"}}` de cada temporada pedida, contando como pendientes las competiciones sin lista de grupos y los grupos sin hacer (con `crests_only`, los hechos sin `crests`) de las categorías pedidas.
  - Detalle: `group_done(entry, jornadas) -> bool` — `no_disponible`, o `ok` y (sin jornadas pedidas, o `"jornadas"` en la entrada). `scrape_group(page, F, season, comp, grupo, jornadas, previo=None, log=print) -> dict | None` — la entrada nueva (sobre `previo`) o `None` si no hay nada que escribir: con `previo` `ok` no vuelve a pedir clasificación ni directorio; las jornadas leídas se guardan en `"jornadas_leidas"` (`{etiqueta: partidos}`) y la siguiente ejecución pide el calendario y solo las que faltan; con todas, `"jornadas"` y se quita `"jornadas_leidas"`. Los intentos de una competición sin grupos, en `data["_intentos"][comp]` (el importador del detalle salta las claves con «_»).
  - Detalle: `run_groups(page, F, seasons, jornadas_seasons, deadline, log=print, categories=None, partes=None) -> bool` (partes `"detalle:<S>"`, o `"calendario:<S>"` si la temporada está en `jornadas_seasons`) y `run_campos(page, F, deadline, log=print, partes=None) -> bool` (parte `"campos"`); una ficha de campo que carga sin datos, `intentos` y `no_disponible` igual.
  - Los dos `main()`: lectura con `para_tanda(fetch_fiflp_2425, args.max_minutes, args.max_paginas)` (la nube, la de `nube()`); opciones nuevas `--max-paginas N` (0, sin tope), `--resumen RUTA` (`guardar_resumen` tras cada grupo guardado y al acabar) y, en goleadores, `--sin-escudos`. Última línea: «Completo.», «Frenada: N páginas servidas, la federación no sirve; se sigue en otra ejecución.» (parada `freno` o `runner`) o «Incompleto: relanzar para seguir.». Siempre salen con 0 salvo una excepción.
  - `detalle-federacion.yml`, «Siguiente tanda»: relanza solo si el registro tiene `^Incompleto\.` (con «Frenada.» ya no se relanza contra el freno mientras exista este workflow).

- [ ] **Step 1: Pruebas que fallan.** En `test_fiflp_goleadores.py`, con `FederacionFalsa` y `f.fed(max_pauses=0)` (como `para_tanda`; una competición `900` con los grupos `11` y `12`, la clasificación y los goleadores de `goleadores_2526_A2.html`):
  - `test_un_runner_rechazado_no_toca_nada` — con `rechaza=True` y `nube="aws"`: `F.parada == "runner"`, como mucho 2 peticiones, el raw y la lista de grupos no se crean (o salen con los mismos bytes si ya estaban) y la parte dice lo mismo que antes de la ejecución.
  - `test_goleadores_con_el_freno_no_dan_un_grupo_por_leido` — `cupo=3`, `bloqueos=(None,)`: el raw tiene `900:11` con `ok` y no tiene `900:12`; `partes == {"goleadores:2024-2025": {"completo": False, "pendientes": 1, "no_disponible": 0}}`; `run` da `False` y `F.parada == "freno"`.
  - `test_una_pagina_vacia_siempre_acaba_no_disponible_tras_tres_ejecuciones` — los goleadores de `12` vienen siempre vacíos y lo demás carga: tras la 1.ª y la 2.ª ejecución, `ok` `False` e `intentos` 1 y 2; tras la 3.ª, `no_disponible` `True` y la parte `{"completo": True, "pendientes": 0, "no_disponible": 1}`; una 4.ª no pide nada (`pedidas == []`).
  - `test_la_lista_de_grupos_no_se_vuelve_a_pedir` — con todo hecho, una ejecución más no pide ni la página de la competición.
  - `test_sin_escudos_no_pide_jornadas_y_los_escudos_van_despues` — con `escudos=False` ninguna URL pedida lleva `CodGrupo=` con `NFG_CmpJornada`; después, `crests_only=True` los pone; un freno a mitad deja ese grupo sin `crests`.
  - `test_the_scraper_saves_standings_and_scorers_and_resumes` sigue igual (su `FakeF` no tiene `parada`: el grupo que falla queda con `ok` `False`, ahora con `intentos` 1).
  En `test_fiflp_detalle.py`, con `FederacionFalsa`:
  - `test_el_calendario_de_un_grupo_se_reanuda_por_la_jornada_que_falta` — un grupo con 5 jornadas y `cupo` que corta tras la 2.ª: la entrada queda `ok` con clasificación y directorio, `jornadas_leidas` con 2 y sin `jornadas`; la siguiente pide el calendario y las jornadas 3-5 y nada más (ni clasificación ni directorio), y acaba con `jornadas` de 5 y sin `jornadas_leidas`.
  - `test_un_freno_no_pisa_un_grupo_ya_leido` — una entrada `ok` sin jornadas, pedidas sus jornadas, frenada en la primera página: la entrada sale idéntica.
  - `test_una_ficha_de_campo_vacia_acaba_no_disponible` — tres ejecuciones, `no_disponible`.
  - Las tres de hoy siguen igual (`test_plazo_agotado_para_sin_perder_lo_leido` sigue esperando `False`).
  En `test_workflows.py`: `test_el_detalle_no_se_relanza_frenado` (la condición de «Siguiente tanda» busca `^Incompleto\.`).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_goleadores.py scripts/tests/test_fiflp_detalle.py` — Expected: FAIL en las nuevas.
- [ ] **Step 3: Implementar** lo de Interfaces.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_goleadores.py scripts/tests/test_fiflp_detalle.py scripts/tests/test_alevin_descargas.py scripts/tests/test_workflows.py scripts/tests/test_fiflp_fresca.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Goleadores y detalle: la lectura del bot, y nunca un grupo vacío por leído».

---

### Task 3: Actas: la enumeración apuntada jornada a jornada y un solo navegador

**Files:**
- Modify: `scripts/actas_lotes.py` (`LOTE_DE_CATEGORIA`, `LOTES`, `RAW_FILE`, `lote_of`)
- Modify: `scripts/fetch_fiflp_actas.py` (`LOTE_ARG`, la enumeración, `fetch_and_parse_acta`, la lectura de actas, `chain_state`, el estado, `parse_args`, `main`)
- Modify: `scripts/import_fiflp_grupos.py` (`actas_complete`)
- Test: `scripts/tests/test_fiflp_actas_enumeration.py` (reescribir sus pruebas de enumeración y de lectura), `scripts/tests/test_actas_lotes.py` (añadir), `scripts/tests/test_fiflp_fresca.py` (`test_an_empty_acta_is_asked_again_fresh`)

**Interfaces:**
- Consumes: lo de la tarea 1.
- Produces:
  - `actas_lotes.LOTE_DE_CATEGORIA = {"ALEVIN": "alevin"}`; `LOTES = ("",) + valores sin repetir`; `RAW_FILE` se construye con `LOTES`; `lote_of(c)` es `LOTE_DE_CATEGORIA.get(c, "")`. `fetch_fiflp_actas.LOTE_ARG = {"siempre": "", **{l: l for l in LOTES if l}}`. **No se añaden lotes**: infantil, cadete y juvenil los añade la parte E (una línea cada uno y sus nombres en `categorias.py`); lo que se quita aquí son las suposiciones de «alevín o no» fuera de `actas_lotes` (y la del workflow, en la tarea 7). Un lote por categoría nueva porque un raw de fútbol 11 (~3.300 actas por categoría y temporada) ya ronda los 20-25 MB: dos juntos se acercarían al aviso de 50 MB de GitHub.
  - El estado de cada lote, **formato 2** (`fiflp_actas_<S>[_<lote>]_status.json`), escrito de forma atómica tras cada competición enumerada, cada 25 actas y al acabar:

    ```json
    {"formato": 2, "season": "2025-2026", "enumerated": 1950, "in_raw": 812, "fetched": 120,
     "pending": 1150, "actas_por_leer": 1138, "jornadas_por_leer": 12, "grupos_por_leer": 0, "unenumerated_comps": 0,
     "no_disponible": ["jornada:54976940:55234218:7", "acta:125790"], "intentos": {"acta:125801": 1},
     "enumeracion": {"54976940": {"grupos": [["55234218", "GRUPO 1"]], "pendientes": {"55234218": ["8", "9"]}}},
     "paginas": {"pedidas": 140, "servidas": 131}, "parada": "freno"}
    ```

    `pending` es la suma de `actas_por_leer`, `jornadas_por_leer`, `grupos_por_leer` y `unenumerated_comps` (las competiciones sin lista de grupos), sin lo que está en `no_disponible`. En `enumeracion`, `"grupos": null` es una competición sin lista; `pendientes[grupo]` `null`, un grupo sin lista de jornadas; un grupo sale de `pendientes` cuando todas sus jornadas están leídas; la competición está completa con `grupos` en lista y `pendientes` vacío. Las claves de `intentos` y `no_disponible`: `comp:C`, `grupo:C:G`, `jornada:C:G:J`, `acta:N`. Un estado **sin `formato`** (los de hoy) es el antiguo: una competición que ya está en el índice se da por enumerada, como hoy, salvo con `--reindex`.
  - `enumerar(page, F, season: str, comp_id: str, ledger: dict, index: dict, intentos: dict, no_disponible: list, log=print) -> str` — pide solo lo pendiente de `ledger` (la entrada de esa competición en `enumeracion`, que actualiza), añade al índice las actas de cada jornada leída y da `"completa"`, `"pendiente"` o `"parada"`. Una jornada que carga sin enlaces a actas está leída (una jornada sin actas existe: 2018-19 entera); la que no carga, la regla común de la tarea 2 con su clave. Sustituye a `enumerate_actas_main` y `enumerate_actas_cascade` (y a sus 20-60 s de espera entre intentos: lo que falta lo pide la ejecución siguiente).
  - `fetch_and_parse_acta(page, cod_acta, F, dump_fixture_for=None) -> dict | None` — una sola carga por `F.goto` (`None` si no carga): sin el bucle de reintentos de la vacía (8 y 12 s después, que con el freno de octubre salía vacía siempre): ahora decide `Federacion`, que la da por freno de verdad (parada) o por página muerta (`dead` + 1: un intento). Un acta que carga y sale vacía (`is_empty_acta`) no se guarda y suma `intentos`; con `MAX_INTENTOS`, a `no_disponible`.
  - `leer_actas(page, F, pending: list[dict], over, on_result, dump_fixture="") -> None` — sustituye a `fetch_parallel`: **un navegador**, en el orden de `pending`, hasta que `over()` o `parada_de(F)`. Con el intervalo de 7 s, un runner de Azure ya lee ~500 páginas por hora, más de lo que da el tope del día en una ejecución; dos navegadores se saltarían el intervalo (el doble de carga) sin que haga falta. Se quita la opción `--workers`.
  - `main()`: un navegador y una página para toda la ejecución; las competiciones en el orden de `--comps` (el carril las da de más nivel a menos: tarea 6); para cada una, `enumerar` y en seguida la lectura de sus actas pendientes, y después la siguiente; con `"parada"`, se guarda todo y se acaba. Opciones nuevas `--max-paginas`, `--resumen` (parte `"actas:<S>:<lote o siempre>"`).
  - `chain_state(season_code, lote="") -> dict` — con formato 2: `{"pending", "stuck", "lote", "parada", "servidas"}` con `stuck` 1 si `parada` no es `None` y `servidas < RELANZAR_MIN` (la cadena vieja de `actas-federacion.yml` deja de relanzarse contra el freno mientras exista); sin formato, lo de hoy.
  - `import_fiflp_grupos.actas_complete(folder, season)` — con formato 2, completa solo con `pending == 0` (la regla antigua «la última tanda no trajo ninguna» daba por completa una temporada frenada desde la primera página); sin formato, la de hoy (2016-17 a 2018-19 siguen dadas de alta).

- [ ] **Step 1: Pruebas que fallan.** En `test_fiflp_actas_enumeration.py`, con `FederacionFalsa` (competiciones `900` y `901`, dos grupos de cuatro jornadas, dos actas por jornada), sustituyendo a `test_every_group_and_round_is_read_by_url`, `test_only_the_requested_groups`, `test_an_empty_answer_is_retried_and_the_slow_strategies_never_run` y `test_actas_are_read_by_several_browsers_from_one_queue_until_the_deadline`:
  - `test_cada_grupo_y_jornada_se_pide_por_su_url` y `test_solo_los_grupos_pedidos` (lo mismo que las de hoy, con `enumerar`).
  - `test_un_corte_a_mitad_de_la_enumeracion_deja_las_jornadas_pendientes` — `cupo=6`, `bloqueos=(None,)` (el freno de verdad; con `max_pages=6` en vez del cupo, lo mismo con `parada == "tope"`): tras la competición, el calendario y las cuatro jornadas del grupo 1, el calendario del grupo 2 viene vacío; el índice tiene las 8 actas del grupo 1, `enumeracion["900"] == {"grupos": [["G1", "GRUPO 1"], ["G2", "GRUPO 2"]], "pendientes": {"G2": None}}`, `grupos_por_leer == 1`, `pending >= 1` y `parada == "freno"`. Con `.ip_nueva()`, la ejecución siguiente pide solo URLs del grupo 2 y las actas, y deja `pendientes == {}`.
  - `test_una_jornada_que_viene_vacia_siempre_acaba_no_disponible` — la jornada 3 del grupo 1 viene siempre vacía y lo demás carga: tras tres ejecuciones, `"jornada:900:G1:3" in no_disponible`, `pending == 0`; una cuarta no pide nada.
  - `test_las_actas_van_en_el_orden_de_las_competiciones_con_un_navegador` — con `--comps 901,900`, toda acta de `901` se pide antes que ninguna de `900`, y se abre una sola página.
  - `test_un_acta_frenada_no_se_guarda_y_queda_pendiente` — la vacía no entra en el raw, cuenta en `actas_por_leer`, no suma intento y `parada == "freno"`.
  - `test_un_acta_muerta_gasta_un_intento_y_se_siguen_leyendo_las_demas` — una de seis siempre vacía: las otras cinco entran en el raw, la muerta tiene `intentos["acta:N"] == 1` y `parada is None`.
  - `test_un_runner_rechazado_no_toca_el_estado` — con `rechaza=True`: ni el índice, ni el raw, ni los `intentos` cambian; `parada == "runner"`.
  - `test_el_estado_nuevo_lleva_todas_sus_claves` — las de arriba, exactas.
  En `test_actas_lotes.py`:
  - `test_un_estado_antiguo_sigue_valiendo` — el estado de 2018-19 del repositorio (`pending` 0, `fetched` 0, sin `formato`) da `actas_complete` y `chain_state` como hoy.
  - `test_un_estado_nuevo_solo_esta_completo_sin_nada_pendiente` — formato 2 con `fetched` 0, `unenumerated_comps` 0 y `pending` 4: `actas_complete` `False`; con `pending` 0, `True`.
  - `test_la_cadena_vieja_para_con_el_freno` — formato 2, `parada` `"freno"` y `servidas` 20: `stuck` 1; con 200: `stuck` 0.
  - `test_los_lotes_salen_de_una_tabla` — `LOTES == ("", "alevin")`, `lote_of("ALEVIN") == "alevin"`, `lote_of("BENJAMIN") == ""`, `LOTE_ARG == {"siempre": "", "alevin": "alevin"}`, y `RAW_FILE` reconoce los raws de cada lote de `LOTES`.
  En `test_fiflp_fresca.py`, `test_an_empty_acta_is_asked_again_fresh` pasa a comprobar que, con `fetch_and_parse_acta(page, 125790, F)` y una `Federacion`, la segunda lectura del mismo código en el mismo navegador va fresca (y la primera, no).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_actas_enumeration.py scripts/tests/test_actas_lotes.py` — Expected: FAIL en las nuevas.
- [ ] **Step 3: Implementar** lo de Interfaces.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fiflp_actas_enumeration.py scripts/tests/test_actas_lotes.py scripts/tests/test_fiflp_fresca.py scripts/tests/test_fetch_fiflp_actas_smoke.py scripts/tests/test_alevin_descargas.py scripts/tests/test_fiflp_grupos.py scripts/tests/test_fiflp_actas_federacion.py scripts/tests/test_alevin_aislamiento.py scripts/tests/test_workflows.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Actas: la enumeración apuntada jornada a jornada, un navegador y la lectura del bot».

---

### Task 4: La cuarentena

**Files:**
- Create: `scripts/cuarentena.py`
- Modify: `scripts/fetch_fiflp_goleadores.py`, `scripts/fetch_fiflp_detalle.py` (también `venue_codes` y `CAMPOS_RAW`), `scripts/fetch_fiflp_actas.py` (`raw_path`, `index_path`, `status_path`, `load_raw`, `RawStore.other`): la opción `--carpeta`
- Test: `scripts/tests/test_cuarentena.py` (nuevo)

**Interfaces:**
- Produces:
  - `PRINCIPAL = Path(__file__).resolve().parent` (`scripts/`) y `CARPETA = PRINCIPAL / "historico"`. El bot no ve la cuarentena porque todos sus lectores miran solo el primer nivel de `scripts/` (`os.listdir` y `glob` sin `**`: `actas_lotes.raw_files`, `import_changed_*`, `escudos_federacion`, `reconstruir`) y reconocen sus ficheros por la huella de su contenido (`raw_imports`, las huellas de grupos, goleadores y detalle): un fichero que llega a `scripts/` se importa en la pasada siguiente, una vez.
  - `FAMILIA = {"escudos": "goleadores", "calendario": "detalle"}` — dos fases del mismo fichero.
  - `trabajo_de(nombre: str) -> str | None` — `fiflp_goleadores_<S>_raw.json` → `"goleadores:<S>"`; `fiflp_detalle_<S>_raw.json` → `"detalle:<S>"`; `fiflp_campos_raw.json` → `"campos"`; `fiflp_actas_<S>[_<lote>]_{raw,index,status}.json` → `"actas:<S>:<lote>"` con `siempre` para el lote `""`; cualquier otro (`fiflp_goleadores_<S>_grupos.json`, `plan.json`, `estado.json`), `None`: son del carril y no se promueven nunca.
  - `ficheros(trabajo: str) -> list[str]` — los nombres de un trabajo (las fases, por su `FAMILIA`); `ValueError` con un tipo o un lote que no existe.
  - `leer(nombre: str, carpeta: Path | None, principal: Path = PRINCIPAL) -> Path | None` — sin carpeta, el de `principal` si existe; con ella, el de la carpeta si existe, si no el de `principal` si existe, si no `None` (se empieza por la copia de lo publicado).
  - `escribir(nombre: str, carpeta: Path | None, principal: Path = PRINCIPAL) -> Path` — sin carpeta, en `principal`; con ella, en la carpeta (la crea).
  - `promover(trabajos: Iterable[str], carpeta: Path = CARPETA, principal: Path = PRINCIPAL) -> list[str]` — mueve (`os.replace`) a `principal` los ficheros de esos trabajos que estén en la carpeta y da sus nombres; `ValueError` con un trabajo desconocido (antes de mover nada).
  - `en_cuarentena(carpeta: Path = CARPETA) -> dict[str, list[str]]` — `{trabajo: [nombres]}` de lo que hay.
  - CLI: `python3 scripts/cuarentena.py promover --trabajos a,b [--raiz DIR] [--lista FICHERO]` (con `--raiz`, la carpeta y `principal` son `DIR/scripts/historico` y `DIR/scripts`; con `--lista`, escribe una ruta `scripts/<nombre>` por línea).
  - En los tres descargadores, un global de módulo `CARPETA: Path | None = None` que pone `main()` con `--carpeta DIR` (vacío por defecto). Con `None` todo es exactamente como hoy (las pruebas de hoy, que cambian `HERE` o `raw_path`, no cambian); con una carpeta, se lee con `leer` y se escribe con `escribir`, también el raw del otro lote que lee `RawStore` y los raws de detalle de los que `venue_codes` saca los campos (los de la carpeta mandan sobre los de `scripts/` del mismo nombre).

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_cuarentena.py`:

```python
import cuarentena as C

def test_trabajo_de_cada_fichero():
    assert C.trabajo_de("fiflp_goleadores_2025-2026_raw.json") == "goleadores:2025-2026"
    assert C.trabajo_de("fiflp_detalle_2019-2020_raw.json") == "detalle:2019-2020"
    assert C.trabajo_de("fiflp_campos_raw.json") == "campos"
    assert C.trabajo_de("fiflp_actas_2025-2026_alevin_status.json") == "actas:2025-2026:alevin"
    assert C.trabajo_de("fiflp_actas_2025-2026_index.json") == "actas:2025-2026:siempre"
    for nombre in ("fiflp_goleadores_2025-2026_grupos.json", "plan.json", "estado.json",
                   "actas_bot_2026-2027_alevin.jsonl", "fiflp_actas_unmatched.json"):
        assert C.trabajo_de(nombre) is None, nombre

def test_ficheros_de_cada_trabajo():
    assert C.ficheros("actas:2025-2026:alevin") == ["fiflp_actas_2025-2026_alevin_raw.json",
        "fiflp_actas_2025-2026_alevin_index.json", "fiflp_actas_2025-2026_alevin_status.json"]
    assert C.ficheros("escudos:2025-2026") == ["fiflp_goleadores_2025-2026_raw.json"]
    assert C.ficheros("calendario:2019-2020") == ["fiflp_detalle_2019-2020_raw.json"]
    with pytest.raises(ValueError):
        C.ficheros("actas:2025-2026:infantil")

def test_leer_prefiere_la_cuarentena_y_escribir_va_a_ella(tmp_path):
    principal, carpeta = tmp_path / "scripts", tmp_path / "scripts" / "historico"
    principal.mkdir()
    (principal / "fiflp_campos_raw.json").write_text("{}")
    assert C.leer("fiflp_campos_raw.json", carpeta, principal) == principal / "fiflp_campos_raw.json"
    assert C.leer("fiflp_campos_raw.json", None, principal) == principal / "fiflp_campos_raw.json"
    assert C.escribir("fiflp_campos_raw.json", carpeta, principal) == carpeta / "fiflp_campos_raw.json"
    (carpeta / "fiflp_campos_raw.json").write_text('{"75": {}}')
    assert C.leer("fiflp_campos_raw.json", carpeta, principal) == carpeta / "fiflp_campos_raw.json"
    assert C.leer("fiflp_detalle_2019-2020_raw.json", carpeta, principal) is None

def test_promover_solo_mueve_lo_de_sus_trabajos(tmp_path):
    # en la carpeta: goleadores 2025-26, actas alevín 2025-26 (raw, índice, estado), plan.json y la lista de grupos
    ...
    assert sorted(C.promover(["actas:2025-2026:alevin"], carpeta, principal)) == [
        "fiflp_actas_2025-2026_alevin_index.json", "fiflp_actas_2025-2026_alevin_raw.json",
        "fiflp_actas_2025-2026_alevin_status.json"]
    assert sorted(p.name for p in carpeta.iterdir()) == ["fiflp_goleadores_2025-2026_grupos.json",
        "fiflp_goleadores_2025-2026_raw.json", "plan.json"]
    with pytest.raises(ValueError):
        C.promover(["fotos:2025-2026"], carpeta, principal)
```

  Y `test_una_tanda_con_carpeta_no_toca_lo_publicado` (uno por descargador: goleadores, detalle y actas, con `FederacionFalsa` y `CARPETA` a una carpeta temporal): el fichero de `scripts/` falso sale con los mismos bytes, y el de la carpeta tiene lo que había más lo leído.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_cuarentena.py` — Expected: `No module named 'cuarentena'`.
- [ ] **Step 3: Implementar.** Cabecera de `cuarentena.py`: por qué existe (el bot importa solo cualquier raw que cambie, y un dato nuevo que rompa una prueba lo deja sin publicar nada) y por qué una carpeta y no una lista de temporadas retenidas (goleadores y detalle son un raw por temporada para todas las categorías: bajar el alevín de 2025-26 cambia el raw que el bot ya importa para benjamín).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_cuarentena.py scripts/tests/test_fiflp_goleadores.py scripts/tests/test_fiflp_detalle.py scripts/tests/test_fiflp_actas_enumeration.py scripts/tests/test_actas_lotes.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «La cuarentena del histórico: lo bajado no llega al bot hasta que se prueba».

---

### Task 5: La prueba sobre una copia

**Files:**
- Modify: `scripts/fetch_futbolaspalmas.py` (`preparar_base`, `solo_historico`, `main`, la opción `--solo-historico`)
- Create: `scripts/prueba_historico.py`
- Test: `scripts/tests/test_prueba_historico.py` (nuevo)

**Interfaces:**
- Produces:
  - `fetch_futbolaspalmas.preparar_base(conn) -> None` — lo que hace hoy `main()` antes de leer nada (`migrate_categories`, `migrate_compactar`, `migrate_identidad.asegurar_esquema` y `migrate_team_names` con su `try`), sacado tal cual; `main()` lo llama.
  - `fetch_futbolaspalmas.solo_historico(conn, log=print, generar=None) -> None` — `preparar_base`, `import_past_seasons(conn)`, `migrate_identidad.resolver_fichas(conn)` y `generar()` (por defecto `generate_js.main`): lo mismo que hará el bot con esos raws, **sin leer ninguna fuente** (ni `process_file`, ni `update_fiflp`, ni `update_fp_app`) y sin `source_health`. `python3 scripts/fetch_futbolaspalmas.py --solo-historico` lo ejecuta sobre la base de esa carpeta.
  - `prueba_historico.IMPORTACION_MAX_S = 600` (el job del bot dura 40 min y una pasada ~20-26: una importación de más de 10 min no cabe en la primera pasada que la haga) y `MB_MAX = base_sana.AVISO_MB` (80: desde ahí hace falta la parte D; el bot deja de subir a 95).
  - `prueba_historico.veredicto(mb_antes: float, mb_despues: float, segundos: float, pruebas: bool) -> dict` — `{"verde", "motivo", "mb_antes", "mb_despues", "segundos"}`; el primer motivo que se cumpla, con estos textos exactos: «las pruebas fallaron»; «la base pasaría a {mb_despues:.1f} MB (desde {MB_MAX} hace falta la parte D)»; «la importación tarda {segundos/60:.0f} min (más de {IMPORTACION_MAX_S/60:.0f}: no cabe en una pasada del bot)».
  - CLI: `python3 scripts/prueba_historico.py importar --raiz DIR --medida FICHERO` (ejecuta `DIR/scripts/fetch_futbolaspalmas.py --solo-historico` con `cwd=DIR`, mide los segundos y el tamaño de `DIR/futbolbase.db` antes y después y escribe `{"mb_antes", "mb_despues", "segundos", "codigo"}`; sale con el código de la importación) y `python3 scripts/prueba_historico.py veredicto --medida FICHERO --pruebas success|failure --salida FICHERO` (escribe el veredicto, pone `verde=true|false` en `$GITHUB_OUTPUT` y sale con 0).

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_prueba_historico.py`:

```python
def test_veredicto():
    assert P.veredicto(41.2, 48.9, 95, True) == {"verde": True, "motivo": "", "mb_antes": 41.2,
                                                 "mb_despues": 48.9, "segundos": 95}
    assert P.veredicto(41.2, 48.9, 95, False)["motivo"] == "las pruebas fallaron"
    assert P.veredicto(41.2, 80.0, 95, True)["motivo"] == "la base pasaría a 80.0 MB (desde 80 hace falta la parte D)"
    assert P.veredicto(41.2, 50.0, 900, True)["motivo"] == \
        "la importación tarda 15 min (más de 10: no cabe en una pasada del bot)"
    assert P.veredicto(41.2, 90.0, 900, False)["motivo"] == "las pruebas fallaron"     # el primero que se cumple
```

  - `test_solo_historico_no_lee_ninguna_fuente` — con `process_file`, `update_fp_app`, `update_fiflp.update_groups` y `source_health.begin` cambiados por funciones que fallan, y `preparar_base`, `import_past_seasons`, `resolver_fichas` y `generar` que apuntan su nombre: el orden es exactamente `["preparar_base", "import_past_seasons", "resolver_fichas", "generar"]`.
  - `test_main_prepara_la_base_igual` — `main()` llama a `preparar_base` antes que a `active_season` (con todo lo demás cambiado por funciones que apuntan).
  - `test_importar_mide_la_copia` — una raíz temporal cuyo `scripts/fetch_futbolaspalmas.py` es un guion de prueba que añade 1 MB a `futbolbase.db`: la medida dice `mb_despues - mb_antes == 1.0` (±0,01), `codigo` 0, y no se ha tocado el `futbolbase.db` del repositorio.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_prueba_historico.py` — Expected: FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_prueba_historico.py scripts/tests/test_base_sana.py scripts/tests/test_pasada_sana.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «La prueba del histórico: importar sin red sobre una copia y su veredicto».

---

### Task 6: El carril: el encargo, el estado y qué toca

**Files:**
- Create: `scripts/historico.py`
- Test: `scripts/tests/test_historico.py` (nuevo)

**Interfaces:**
- Consumes: `reloj_pasadas.WINDOWS`, `reloj_pasadas.local_time`; `fetch_fiflp_actas.SEASON_NAME`, `catalog_comps`, `catalog_names`; `actas_lotes.lotes_of`; `categorias.parse_categories`, `DEFAULT_CATEGORIES`; `fiflp_manifest.fold`, `segunda_fase`; `fiflp_carga.RELANZAR_MIN`; `cuarentena.FAMILIA`, `ficheros`. Como `fetch_fiflp_goleadores`, mete `scripts/` y la raíz en `sys.path` (lo ejecuta el python del runner sin pip ni `PYTHONPATH`).
- Produces:
  - Constantes: `PAGINAS_DIA = 2000`; `MINUTOS_EJECUCION = 300`; `MARGEN_VENTANA = timedelta(minutes=20)`; `MINIMO_EJECUCION = timedelta(minutes=10)`; `MARGEN_PRUEBA = timedelta(minutes=60)`; `RELANZAR_SI_RUNNER_RECHAZADO = 0` (relanzamientos seguidos tras caer en un runner que la federación no sirve: 0, ninguno; relanzar hasta que toque Azure es esquivar un bloqueo y lo decide el dueño: si dice que sí, se cambia este número y nada más); `TRABAJOS = ("goleadores", "actas", "detalle", "calendario", "escudos")` (ese es el orden: lo barato que más dice de cada niño —clasificación y goleadores— primero; las actas, que dan a todos los niños con su identificador, después; el detalle, la ficha de los equipos, que no hace falta para las trayectorias, detrás; y las dos fases que reescriben un fichero ya promovido, al final); `ESTADOS = ("pendiente", "completo", "fallo", "promovido")`.
  - **El tope diario: 2.000 páginas para empezar, y su rampa** (`HISTORICO_PAGINAS_DIA` en el entorno lo cambia; el workflow lo toma de la variable del repositorio del mismo nombre). Por qué 2.000: es lo que el bot ya leía a diario sin problemas (sin freno, del 21/10 al 13/11, entre 1.240 y 2.720 páginas al día; v1 y v2 juntas llegaron a ~3.700 el 14/11 sin consecuencias); en Azure la federación sirve ~500 páginas por hora, así que son ~4 h de lectura, que caben fuera de las ventanas cualquier día (el sábado y el domingo, de 0 a 9:40) y en una sola ejecución de `MINUTOS_EJECUCION`; y bajan el alevín de Gran Canaria de siete temporadas (unas 13.600 actas y ~4.000 páginas de calendarios y goleadores) en unos 9-10 días. **Subirlo** es cosa de quien dirige, a mano (`gh variable set`), en escalones de 2.000 → 3.000 → 4.000, cada uno tras tres días seguidos sin ningún día parado por el freno de verdad (en `estado.json`, `dias_frenados`) y con las pasadas del bot igual de servidas que antes; no se pasa de 4.000 sin volver a medir. **Se baja solo**: si en una ejecución del carril aparece el freno de verdad (`parada == "freno"`: una vacía con la federación sin servir otra, o un 503/429), o si el último `data-health.json` publicado ese día dice que el bot en vivo lo ha esperado en Azure (`run.pauses >= 1`, `run.cloud == "azure"` y sin `run.refusedRunner`), el carril no lee nada más ese día de Canarias; al día siguiente vuelve con el tope entero.
  - Ficheros del carril (en `carpeta()`: `HISTORICO_CARPETA` del entorno o `cuarentena.CARPETA`; las pruebas lo cambian):
    - `plan.json` (solo lo escribe el job del encargo): `{"formato": 1, "encargado": "<ISO>", "temporadas": ["21", "20"], "categorias": ["alevin"], "trabajos": ["goleadores", "actas"], "calendario": [], "parado": false, "reintentar_desde": null}` (`temporadas`, CodTemporada en el orden en que se bajan; `categorias`, claves de la web).
    - `estado.json` (solo lo escribe el carril): `{"formato": 1, "dia": {"fecha": "2026-11-25", "paginas": 340, "freno": null}, "dias_frenados": [], "trabajos": {"<clave>": {"estado": "pendiente", "pendientes": 1204, "no_disponible": 0, "actualizado": "<ISO>"}}, "ejecuciones": [como mucho 100], "pruebas": [como mucho 50]}`. Cada ejecución: `{"inicio", "fin", "accion", "trabajo", "temporadas", "pedidas", "servidas", "muertas", "esperas", "frenos_tras", "parada", "nube", "runner_rechazado", "relanzada"}`; `dia.freno` es `null`, `"carril"` o `"bot"`, y `dias_frenados` (las fechas, como mucho 60) es lo que mira la rampa; cada prueba: `{"at", "trabajos", "verde", "motivo", "mb_antes", "mb_despues", "segundos"}`. Es el sitio del que más adelante leerá «Datos y fuentes» (no `data-health.json`, que reescribe el bot en cada pasada: dos escritores chocarían al rebasar).
    - Claves de trabajo: `"<tipo>:<S>"` con `S` el nombre de la temporada (`"goleadores:2025-2026"`) y `"actas:<S>:<lote>"` (`siempre` o `alevin`), más `"campos"`. `trabajo(tipo: str, codigo: str, lote: str | None = None) -> str` las construye.
  - `estado_vacio() -> dict`; `leer_plan() -> dict | None`; `leer_estado() -> dict`; `guardar_estado(estado) -> None` (atómico).
  - `hasta(now: datetime) -> datetime | None` — el fin del plazo de una ejecución que empieza `now`: `None` en una ventana de partidos (las de `reloj_pasadas`: viernes de 18 a 24 y sábado y domingo de 10 a 24, hora de Canarias), sin la hora de Canarias (el carril no corre a ciegas) o si al inicio de la siguiente ventana menos `MARGEN_VENTANA` le quedan menos de `MINIMO_EJECUCION`; si no, lo primero de ese límite y `now + MINUTOS_EJECUCION`.
  - `cupo_hoy(estado: dict, now: datetime, env=None) -> int` — `PAGINAS_DIA` (o el del entorno) menos las páginas de `estado["dia"]` si su fecha es la de hoy en Canarias; nunca negativo.
  - `freno_del_bot(salud: dict | None, now: datetime) -> bool` — con el `data-health.json` publicado: su `checkedAt` es de hoy en Canarias y su `run` tiene `pauses >= 1`, `cloud == "azure"` y no `refusedRunner`. Sin fichero, sin `run` o con algo que no se entiende, `False` (no se para por un dato que no se lee).
  - `rango_competicion(nombre: str) -> int` y `orden_competiciones(comps: list[tuple[str, str]]) -> list[str]` — de más nivel a menos y, a igual rango, en el orden del catálogo: «PREFERENTE» 0; una Segunda Fase con letra (`fiflp_manifest.segunda_fase` sobre el nombre plegado) 1 + su posición (A 1, B 2…); otra liga (Primera, Fase Previa) 30; lo demás (copas, Campeones, Clausura, eliminatorias, finales) 40.
  - `trabajos_del_plan(plan: dict) -> list[str]` — las claves en el orden de `TRABAJOS` y, dentro, de `plan["temporadas"]`; `actas` sale una vez por lote de las categorías (`actas_lotes.lotes_of`); `calendario`, solo de las temporadas de `plan["calendario"]`.
  - `siguiente(plan: dict | None, estado: dict, now: datetime, env=None, salud=None) -> dict` (`salud`, el `data-health.json` del checkout; la CLI lo lee), por este orden:
    1. sin plan, o `parado`: `{"accion": "nada", "motivo": "sin encargo" | "parado"}`;
    2. en una ventana (o `hasta(now)` `None`): `nada`, motivo «ventana de partidos»;
    3. si `hasta(now) - now >= MARGEN_PRUEBA` y alguna temporada tiene trabajos «completo» (o «fallo» con su prueba anterior a `plan["reintentar_desde"]`): `{"accion": "probar", "trabajos": [...]}` con los de **una** temporada, la primera del plan que los tenga, más `"campos"` si está completo (una temporada cada vez: si falla, solo esa se queda fuera);
    4. con `cupo_hoy` 0: `nada`, «tope del día»; con `estado["dia"]["freno"]` de hoy o `freno_del_bot(salud, now)`: `nada`, «freno de verdad hoy»;
    5. el primer tipo de `TRABAJOS` con algún trabajo pendiente y listo (una fase de `FAMILIA` está lista solo con la anterior del mismo fichero `promovido`): `{"accion": "descargar", "trabajo": tipo, "temporadas": [...], "categorias": [...], "lote": str | None, "comps": [...], "partes": [...], "minutos": float, "paginas": int, "hasta": "<ISO>", "inicio": "<ISO>", "dia": "<fecha de Canarias>"}` — para `goleadores`, `detalle`, `calendario` y `escudos`, todas las temporadas del plan que lo tienen pendiente; para `actas`, la primera temporada y lote pendientes, con `comps` en `orden_competiciones` (las del catálogo de las categorías del lote: `DEFAULT_CATEGORIES` para el de siempre);
    6. si no queda nada: `nada`, «terminado».
  - `argumentos(accion: dict, resumen: str) -> list[str]` — la orden del descargador, con `--carpeta scripts/historico`, `--max-minutes` (entero por abajo de `minutos`), `--max-paginas` y `--resumen`: `goleadores` añade `--sin-escudos` y `escudos`, `--escudos`; `detalle`, `--jornadas ""`; `calendario`, `--jornadas <sus temporadas> --sin-campos`; `actas`, `--temporada --lote --comps`.
  - `registrar(estado: dict, accion: dict, resumen: dict | None, now: datetime) -> dict` — suma `resumen["pedidas"]` al día de `accion["dia"]` (si es otro que el de `estado["dia"]`, empieza uno nuevo), pasa cada parte a su trabajo (`completo` si `completo`, si no `pendiente`; un runner rechazado no cambia ninguna) y apunta la ejecución; con `parada == "freno"`, `dia.freno = "carril"` y la fecha en `dias_frenados`. Sin resumen (el descargador no llegó a escribirlo), la ejecución con `"pedidas": null` y un aviso en el registro.
  - `registrar_prueba(estado: dict, trabajos: list[str], veredicto: dict, now: datetime) -> dict` — verde: `promovido`; rojo: `fallo`; apunta la prueba.
  - `relanzar(resumen: dict | None, despues: dict, estado: dict) -> bool` — `despues` es `siguiente(...)` con el estado ya registrado: nunca si es `nada`; tras una prueba (`resumen` `None`), sí; tras un runner rechazado, solo si las ejecuciones rechazadas seguidas al final de `estado["ejecuciones"]` (esta incluida) son como mucho `RELANZAR_SI_RUNNER_RECHAZADO` (con 0, nunca); tras otra descarga, solo si `resumen["servidas"] >= RELANZAR_MIN`. Si no se relanza, lo retoma el disparo programado (cada 3 h: con la mitad de los runners en AWS, ≤ 8 disparos fuera de las ventanas bastan para que alguno caiga en Azure cada día, y una sola ejecución en Azure llega al tope).
  - `encargar(plan: dict | None, temporadas: str, categorias: str, trabajos: str, calendario: str, now: datetime) -> dict` — valida y da el plan nuevo; `ValueError` si una temporada no está en `SEASON_NAME`, una categoría no existe (`parse_categories`), un trabajo no está en `TRABAJOS`, la temporada en curso (`22`) lleva otro trabajo que `actas` o `detalle` (sus goleadores y su calendario los lee el bot), o el calendario pide una temporada que no está en `temporadas`. Con benjamín o prebenjamín, las dos (comparten el lote de siempre). Lo que ya estaba `promovido` en el estado no se vuelve a bajar.
  - `estado_legible(plan, estado, now) -> str` — para el registro, el resumen del job y el dueño; estas formas: «Encargo del 25/11/2026: alevín; 2025-26, 2024-25; goleadores, actas.», «Hoy (25/11/2026): 340 de 2.000 páginas.», «Hoy (25/11/2026): parado por el freno de verdad (lo vio el bot en vivo).», «2025-26 · goleadores: en la base (probado el 25/11 a las 10:40: de 41,2 a 43,0 MB, 95 s).», «2025-26 · actas alevín: bajando (quedan 1.204; 0 no disponibles).», «2024-25 · goleadores: pendiente.», «2023-24 · actas alevín: la prueba falló (las pruebas fallaron); no se reintenta sola.» «Última ejecución: 25/11 de 12:10 a 16:12, actas 2025-26 alevín, 1.985 de 2.000 páginas servidas (2 muertas), tope del día.» y «Última ejecución: 25/11 a las 18:47, runner rechazado (nube: aws), sin leer nada; se retoma en el próximo disparo (cada 3 h).». Con `--linea`, solo la última ejecución (el asunto del commit).
  - CLI (`--now ISO` en todas, para las pruebas): `siguiente` (imprime la acción y pone `accion` y `trabajos` en `$GITHUB_OUTPUT`); `descargar --accion F --resumen F` (vuelve a calcular `siguiente`, guarda la acción y ejecuta el descargador con `argumentos`, `cwd` la raíz y `PYTHONPATH` la raíz; sale con su código); `registrar --accion F [--resumen F]` y `registrar --prueba F --trabajos a,b` (guardan el estado y ponen `relanzar=true|false` y `promovido=true|false` en `$GITHUB_OUTPUT`); `encargar --temporadas --categorias --trabajos --calendario`; `parar`; `reanudar`; `reintentar` (pone `reintentar_desde`); `estado [--linea]`.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_historico.py`:

```python
from datetime import datetime, timezone
import historico as H

def T(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

MIERCOLES = T("2026-11-25T10:00:00Z")
PLAN = {"formato": 1, "encargado": "2026-11-25T09:00:00+00:00", "temporadas": ["21", "20"], "categorias": ["alevin"],
        "trabajos": ["goleadores", "actas"], "calendario": [], "parado": False, "reintentar_desde": None}

def test_hasta():
    assert H.hasta(MIERCOLES) == T("2026-11-25T15:00:00Z")                 # 300 min
    assert H.hasta(T("2026-11-27T15:00:00Z")) == T("2026-11-27T17:40:00Z")  # viernes: 20 min antes de las 18
    assert H.hasta(T("2026-11-27T17:35:00Z")) is None                       # le quedarían 5 min
    assert H.hasta(T("2026-11-28T12:00:00Z")) is None                       # sábado, en la ventana
    assert H.hasta(T("2026-11-28T05:00:00Z")) == T("2026-11-28T09:40:00Z")
    assert H.hasta(T("2026-11-29T23:30:00Z")) is None                       # domingo, hasta las 24
    assert H.hasta(T("2026-11-30T00:05:00Z")) == T("2026-11-30T05:05:00Z")
    assert H.hasta(T("2026-10-16T14:00:00Z")) == T("2026-10-16T16:40:00Z")  # horario de verano (UTC+1)

def test_hasta_sin_la_hora_de_canarias(monkeypatch):
    monkeypatch.setattr(H.reloj_pasadas, "local_time", lambda now: None)
    assert H.hasta(MIERCOLES) is None

def test_cupo_de_hoy():
    e = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 340, "freno": None}}
    assert H.cupo_hoy(e, MIERCOLES, env={}) == 1660
    assert H.cupo_hoy(e, T("2026-11-26T00:10:00Z"), env={}) == 2000
    assert H.cupo_hoy(e, MIERCOLES, env={"HISTORICO_PAGINAS_DIA": "200"}) == 0

def test_orden_competiciones():
    comps = [("1", "CLAUSURA ALEVÍN"), ("2", "LIGA ALEVIN GRAN CANARIA FASE PREVIA"),
             ("3", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA A"), ("4", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA C"),
             ("5", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA B"), ("6", "COPA CAMPEONES ALEVÍN")]
    assert H.orden_competiciones(comps) == ["3", "5", "4", "2", "1", "6"]
    assert H.orden_competiciones([("8", "LIGA PRIMERA ALEVIN F-8 GRAN CANARIA"),
                                  ("7", "LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA")]) == ["7", "8"]

def test_primero_los_goleadores_de_todas_las_temporadas():
    a = H.siguiente(PLAN, H.estado_vacio(), MIERCOLES, env={})
    assert (a["accion"], a["trabajo"], a["temporadas"], a["categorias"]) == ("descargar", "goleadores", ["21", "20"], ["alevin"])
    assert a["paginas"] == 2000 and a["hasta"] == "2026-11-25T15:00:00+00:00" and a["dia"] == "2026-11-25"
    assert a["partes"] == ["goleadores:2025-2026", "goleadores:2024-2025"]

def test_despues_las_actas_de_la_mas_reciente():
    e = H.estado_vacio()
    for k in ("goleadores:2025-2026", "goleadores:2024-2025"):
        e["trabajos"][k] = {"estado": "promovido", "pendientes": 0, "no_disponible": 0}
    a = H.siguiente(PLAN, e, MIERCOLES, env={})
    assert (a["trabajo"], a["temporadas"], a["lote"]) == ("actas", ["21"], "alevin")
    assert a["partes"] == ["actas:2025-2026:alevin"] and a["comps"][0] != a["comps"][-1]

def test_lo_completo_se_prueba_antes_de_seguir_bajando():
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "completo", "pendientes": 0, "no_disponible": 1}
    assert H.siguiente(PLAN, e, MIERCOLES, env={}) == {"accion": "probar", "trabajos": ["goleadores:2025-2026"]}
    # A 40 min de una ventana no se prueba (la importación del bot caería en ella): se sigue bajando otra cosa.
    a = H.siguiente(PLAN, e, T("2026-11-27T17:00:00Z"), env={})
    assert a["accion"] == "descargar" and a["temporadas"] == ["20"]

def test_una_prueba_en_rojo_no_se_repite_sola():
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "fallo", "pendientes": 0, "no_disponible": 0}
    e["pruebas"] = [{"at": "2026-11-25T08:00:00+00:00", "trabajos": ["goleadores:2025-2026"], "verde": False,
                     "motivo": "las pruebas fallaron"}]
    assert H.siguiente(PLAN, e, MIERCOLES, env={})["temporadas"] == ["20"]
    plan = {**PLAN, "reintentar_desde": "2026-11-25T09:30:00+00:00"}
    assert H.siguiente(plan, e, MIERCOLES, env={})["accion"] == "probar"

def test_nada_cuando_no_toca():
    assert H.siguiente(None, H.estado_vacio(), MIERCOLES, env={})["motivo"] == "sin encargo"
    assert H.siguiente({**PLAN, "parado": True}, H.estado_vacio(), MIERCOLES, env={})["motivo"] == "parado"
    assert H.siguiente(PLAN, H.estado_vacio(), T("2026-11-28T12:00:00Z"), env={})["motivo"] == "ventana de partidos"
    lleno = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 2000, "freno": None}}
    assert H.siguiente(PLAN, lleno, MIERCOLES, env={})["motivo"] == "tope del día"
    hecho = H.estado_vacio()
    for k in H.trabajos_del_plan(PLAN):
        hecho["trabajos"][k] = {"estado": "promovido", "pendientes": 0, "no_disponible": 0}
    assert H.siguiente(PLAN, hecho, MIERCOLES, env={})["motivo"] == "terminado"

def test_las_fases_de_un_fichero_van_en_orden():
    plan = {**PLAN, "temporadas": ["21"], "trabajos": ["goleadores", "escudos"]}
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "fallo", "pendientes": 0, "no_disponible": 0}
    assert H.siguiente(plan, e, MIERCOLES, env={})["motivo"] == "terminado"       # escudos espera a goleadores
    e["trabajos"]["goleadores:2025-2026"]["estado"] = "promovido"
    assert H.siguiente(plan, e, MIERCOLES, env={})["trabajo"] == "escudos"

def test_relanzar_solo_si_la_federacion_sirvio():
    bajar, e = {"accion": "descargar"}, H.estado_vacio()
    assert not H.relanzar({"servidas": 30, "runner_rechazado": False}, bajar, e)
    assert H.relanzar({"servidas": 60, "runner_rechazado": False}, bajar, e)
    assert not H.relanzar({"servidas": 600, "runner_rechazado": False}, {"accion": "nada", "motivo": "tope del día"}, e)
    assert H.relanzar(None, bajar, e)                                             # tras una prueba

def test_un_runner_rechazado_no_se_relanza(monkeypatch):
    rechazado = {"servidas": 0, "runner_rechazado": True, "parada": "runner"}
    e = H.estado_vacio()
    e["ejecuciones"] = [{"runner_rechazado": True}]                               # la que se acaba de apuntar
    assert not H.relanzar(rechazado, {"accion": "descargar"}, e)
    monkeypatch.setattr(H, "RELANZAR_SI_RUNNER_RECHAZADO", 2)                     # si el dueño dice que sí
    assert H.relanzar(rechazado, {"accion": "descargar"}, e)
    e["ejecuciones"] = [{"runner_rechazado": True}] * 3
    assert not H.relanzar(rechazado, {"accion": "descargar"}, e)

def test_registrar_suma_el_dia_en_que_empezo_y_apunta_el_freno():
    e = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 340, "freno": None}}
    accion = {"accion": "descargar", "trabajo": "actas", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T23:30:00+00:00", "partes": ["actas:2025-2026:alevin"]}
    resumen = {"pedidas": 33, "servidas": 30, "muertas": 0, "esperas": 0, "frenos_tras": [30], "parada": "freno",
               "nube": "azure", "runner_rechazado": False,
               "partes": {"actas:2025-2026:alevin": {"completo": False, "pendientes": 1204, "no_disponible": 0}}}
    e = H.registrar(e, accion, resumen, T("2026-11-26T00:20:00Z"))
    assert e["dia"] == {"fecha": "2026-11-25", "paginas": 373, "freno": "carril"} and e["dias_frenados"] == ["2026-11-25"]
    assert e["trabajos"]["actas:2025-2026:alevin"]["estado"] == "pendiente"
    assert e["ejecuciones"][-1]["parada"] == "freno" and e["ejecuciones"][-1]["servidas"] == 30

def test_el_freno_de_verdad_para_el_dia():
    e = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 400, "freno": "carril"}}
    assert H.siguiente(PLAN, e, MIERCOLES, env={})["motivo"] == "freno de verdad hoy"
    assert H.siguiente(PLAN, e, T("2026-11-26T01:00:00Z"), env={})["accion"] == "descargar"     # otro día
    salud = {"checkedAt": "2026-11-25T09:21:28+00:00", "run": {"pauses": 1, "cloud": "azure"}}
    assert H.freno_del_bot(salud, MIERCOLES)
    assert H.siguiente(PLAN, H.estado_vacio(), MIERCOLES, env={}, salud=salud)["motivo"] == "freno de verdad hoy"
    assert not H.freno_del_bot({**salud, "run": {"pauses": 1, "cloud": "aws", "refusedRunner": True}}, MIERCOLES)
    assert not H.freno_del_bot({**salud, "checkedAt": "2026-11-24T22:00:00+00:00"}, MIERCOLES)
    assert not H.freno_del_bot(None, MIERCOLES) and not H.freno_del_bot({"run": "?"}, MIERCOLES)

def test_encargar_valida():
    p = H.encargar(None, "21,20", "alevín", "goleadores,actas", "", MIERCOLES)
    assert p == {**PLAN, "encargado": "2026-11-25T10:00:00+00:00"}
    for mal in (("23", "alevin", "actas", ""), ("21", "infantil", "actas", ""), ("21", "alevin", "fotos", ""),
                ("22", "alevin", "goleadores", ""), ("21", "alevin", "detalle", "20")):
        with pytest.raises(ValueError):
            H.encargar(None, *mal, MIERCOLES)
    assert H.encargar(None, "21", "benjamin", "actas", "", MIERCOLES)["categorias"] == ["benjamin", "prebenjamin"]
```

  Y además: `test_registrar_prueba` (verde → `promovido`; rojo → `fallo` y la prueba con su motivo), `test_argumentos_de_cada_trabajo` (las órdenes exactas de goleadores, escudos, detalle, calendario y actas, con `--carpeta scripts/historico`), `test_estado_legible` (las frases de arriba, con números inventados) y `test_la_orden_lee_y_escribe_en_su_carpeta` (con `HISTORICO_CARPETA` en una carpeta temporal y `GITHUB_OUTPUT` en un fichero: `encargar`, `siguiente --now` y `registrar` dejan `plan.json`, `estado.json` y las salidas `accion=descargar` y `relanzar=false`; nunca se toca `scripts/historico/` del repositorio).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_historico.py` — Expected: `No module named 'historico'`.
- [ ] **Step 3: Implementar.** Cabecera: el problema (las tandas daban por leída una página vacía; lo medido en `docs/freno-2026-11.md`: Azure sirve, AWS no, y las páginas muertas), las reglas del carril en una lista (una ejecución cada vez, fuera de las ventanas, 2.000 páginas al día y su rampa, el día parado por el freno de verdad, relanzar solo con 60 servidas y nunca por un runner rechazado, la cuarentena y la prueba) y el porqué de cada número.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_historico.py scripts/tests/test_reloj_pasadas.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «El carril del histórico: el encargo, el estado y qué toca en cada ejecución».

---

### Task 7: El workflow del carril

**Files:**
- Create: `.github/workflows/historico.yml`
- Delete: `.github/workflows/actas-federacion.yml`, `.github/workflows/goleadores-federacion.yml`, `.github/workflows/detalle-federacion.yml`
- Modify: `.github/workflows/update.yml` y `.github/workflows/reloj.yml` (solo los comentarios que nombran a quien lanza el bot)
- Test: `scripts/tests/test_workflows.py`; `scripts/tests/test_actas_lotes.py` (quitar `chain_lote`, `test_the_chain_of_each_lote_has_its_concurrency_group_and_tells_it_to_the_script`, `test_the_actas_workflow_uploads_only_the_files_of_its_lote`, `test_a_chain_with_categories_it_cannot_download_stops_and_skips_the_queue`, `test_the_next_tanda_follows_the_state_of_the_lote_of_the_chain`, `test_the_other_workflows_need_no_new_files`); `scripts/tests/test_alevin_descargas.py` (quitar `test_actas_workflow_has_2026_27_and_propagates_the_categories_to_every_dispatch` y `test_goleadores_and_detalle_workflows_take_and_chain_the_categories`)

**Interfaces:**
- Consumes: las órdenes de `historico.py` (tarea 6), `cuarentena.py promover` (tarea 4), `prueba_historico.py importar|veredicto` (tarea 5).
- Produces: `historico.yml` («Histórico de la federación (un solo carril)»):
  - Disparadores: `schedule` `'47 */3 * * *'` (cada 3 h, lejos de los ticks del reloj y de las horas en punto: con la mitad de los runners en AWS, alguno de los ≤ 8 disparos del día cae en Azure, y una ejecución en Azure llega al tope; la cadena de relanzamientos hace el resto) y `workflow_dispatch` con `accion` (choice `seguir`, `encargar`, `parar`, `reanudar`, `reintentar`; por defecto `seguir`), `temporadas` (`''`), `categorias` (`'alevin'`), `trabajos` (`'goleadores,actas,detalle,escudos'`) y `calendario` (`''`). Permisos `contents: write` y `actions: write`.
  - Job `encargo` (si `accion` no es `seguir`): concurrencia propia `historico-encargo` (sin cancelar), `checkout` de `main`, `python3 scripts/historico.py <accion> …` con las entradas por `env:`, y sube **solo** `scripts/historico/plan.json` (rebasando: `estado.json` es del carril, así que nunca chocan).
  - Job `carril`: `needs: encargo` con `if: ${{ always() && needs.encargo.result != 'failure' && needs.encargo.result != 'cancelled' }}`; **concurrencia `historico-federacion`, sin cancelar** (de job: una cancelación del carril en espera no se lleva el encargo, ya subido); `timeout-minutes: 350`; `runs-on: ubuntu-24.04`. Pasos, con estos nombres:
    1. «Checkout» (`ref: main`) y «Set up Python» (3.11).
    2. «¿Qué toca?» (`id: toca`): `python3 scripts/historico.py siguiente` y el estado legible en `$GITHUB_STEP_SUMMARY`; sin pip.
    3. Si `accion == 'descargar'`: «Instalar Playwright» (`requirements-bot.txt`, `playwright install chromium --with-deps`), «IP pública del runner» (como en `update.yml` de la rama `freno`: la IP y la nube, nunca para el job) y «Descargar» (`id: descargar`, `continue-on-error: true`, `timeout-minutes: 335`, `PYTHONUNBUFFERED: '1'`, `HISTORICO_PAGINAS_DIA: ${{ vars.HISTORICO_PAGINAS_DIA }}`, `HISTORICO_ESPERAS: ${{ vars.HISTORICO_ESPERAS }}`; un runner rechazado acaba aquí en uno o dos minutos): `python3 scripts/historico.py descargar --accion "$RUNNER_TEMP/accion.json" --resumen "$RUNNER_TEMP/resumen.json"`.
    4. Si `accion == 'probar'`: «Instalar dependencias de test» (`requirements-tests.txt`), «Set up Node» (22), «Preparar la copia» (`git worktree add --detach "$RUNNER_TEMP/prueba" HEAD` y `python3 scripts/cuarentena.py promover --raiz "$RUNNER_TEMP/prueba" --trabajos "$TRABAJOS"`), «Importar sin red» (`id: importar`, `continue-on-error: true`), «Base sana» (`id: base`), «Tests Python» (`id: pytest`) y «Tests Node» (`id: node`) con `working-directory: ${{ runner.temp }}/prueba`, cada uno solo si el anterior fue bien y con `continue-on-error: true`; «Veredicto» (`id: veredicto`, `if: ${{ !cancelled() }}`, con `--pruebas success` solo si los cuatro fueron `success`); «Promover» (si `steps.veredicto.outputs.verde == 'true'`): `python3 scripts/cuarentena.py promover --trabajos "$TRABAJOS" --lista "$RUNNER_TEMP/promovidos.txt"` en el checkout de verdad. La copia es otro árbol: lo que la importación y `generate_js` escriben allí no llega nunca al que se sube.
    5. «Registrar» (`id: registrar`, `if: always()` y acción distinta de `nada`): `historico.py registrar …` (la descarga o la prueba).
    6. «Subir» (`if: always()` y acción distinta de `nada`): `git add scripts/historico` y una línea `git add "$f"` por cada ruta de `promovidos.txt`; commit «histórico: <`historico.py estado --linea`>»; `for intento in 1 2 3` con `git push` y `git pull --rebase --autostash origin main || { git rebase --abort; …; exit 1; }`, como `update.yml`. Nunca `futbolbase.db`, `data-*.js`, `index.html` ni `sw.js`.
    7. «Importar y publicar (bot)» (si `steps.registrar.outputs.promovido == 'true'`): `gh workflow run update.yml --ref main || echo …` (el bot importa lo promovido en su pasada; las descargas ya no lo lanzan: no le dan nada que importar).
    8. «Siguiente» (`if: ${{ !cancelled() && steps.registrar.outputs.relanzar == 'true' }}`): `gh workflow run historico.yml --ref main` **sin entradas** (`seguir`).
    9. «En rojo si falló» (al final): `exit 1` si la descarga terminó con error (una excepción, no una parada) o si el veredicto fue rojo. Una parada por el freno, el plazo, el tope o un runner rechazado acaba en verde.

- [ ] **Step 1: Pruebas que fallan** en `test_workflows.py` (sección «historico.yml»), con `WORKFLOWS` ya sin los tres y con `historico.yml`:
  - `test_historico_un_solo_carril` — `jobs.carril.concurrency == {"group": "historico-federacion", "cancel-in-progress": False}`; ningún otro workflow ejecuta `fetch_fiflp_actas.py`, `fetch_fiflp_goleadores.py` ni `fetch_fiflp_detalle.py`; el grupo no es `update-data`.
  - `test_el_encargo_no_se_pierde_si_cancelan_el_carril` — `jobs.encargo.concurrency.group == "historico-encargo"`, el encargo sube solo `scripts/historico/plan.json`, y `carril` depende de `encargo` con la condición exacta de arriba.
  - `test_historico_disparadores_y_entradas` — el cron, las cinco acciones y los valores por defecto; ninguna `${{ inputs.` dentro de un `run:`.
  - `test_historico_prueba_en_una_copia` — «Importar sin red», «Base sana», «Tests Python» y «Tests Node» llevan `working-directory: ${{ runner.temp }}/prueba`; «Promover» solo con el veredicto verde; «Preparar la copia» usa `git worktree add`.
  - `test_historico_sube_lo_bajado_aunque_se_corte` — «Registrar» y «Subir» con `always()`; la subida rebasa con `--autostash` y aborta un conflicto; sus `git add` no publican nada (`_publica`).
  - `test_historico_relanza_solo_cuando_toca` — ejecutando el guion de «Siguiente» con un `gh` de mentira que apunta sus llamadas: con `relanzar=true` lanza exactamente `gh workflow run historico.yml --ref main`, y la condición del paso pide `relanzar == 'true'`.
  - `test_historico_lanza_el_bot_solo_tras_promover`.
  - `test_historico_cabe` — `MINUTOS_EJECUCION + 30 <= 335 <= 350` (el paso «Descargar» y el job).
  - `test_historico_dice_la_nube` — «IP pública del runner» imprime `/sys/class/dmi/id/sys_vendor`, con `continue-on-error`.
  - `test_every_workflow_that_launches_the_bot_is_named_where_the_bot_is` pasa a exigir `historico.yml` (en vez de `detalle-federacion.yml`) entre los que lanzan el bot y en los comentarios de `update.yml` y `reloj.yml`.
  - `test_el_detalle_no_se_relanza_frenado` (tarea 2) se quita con su workflow.
  En `test_alevin_descargas.py`: `test_historico_toma_las_categorias` (la entrada `categorias`, por defecto `alevin`, llega a `historico.py` por `env:`).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_workflows.py scripts/tests/test_alevin_descargas.py` — Expected: FAIL (no existe `historico.yml`).
- [ ] **Step 3: Implementar** el workflow, borrar los tres y poner al día los comentarios de `update.yml` y `reloj.yml` (quién lanza el bot: el reloj, el carril del histórico al promover y la activación no; a mano).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: toda la suite de Python en verde (con sus `skipped` de siempre). Y `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/historico.yml'))"` sin error.
- [ ] **Step 5: Commit.** Asunto: «Un solo carril para el histórico (historico.yml) en lugar de las tres tandas».

---

### Task 8: Documentar y la primera prueba pequeña

**Files:**
- Modify: `docs/federacion.md` («La espera del freno»: su última frase; «Rellenar temporadas pasadas», «Las actas de alevín, en su propio raw» y «El detalle»: las órdenes de los workflows quitados), `docs/alevin.md` («Histórico» y «Las actas de alevín, en su propio raw»; y la orden de «Activar alevín de Gran Canaria 2026-27» que trae las actas antiguas con `actas-federacion.yml`), `docs/decisiones.md`
- Modify: los comentarios y docstrings que nombran `actas-federacion.yml`, `goleadores-federacion.yml` o `detalle-federacion.yml` en `scripts/*.py` y `scripts/tests/*.py` (los de la lista de `grep` de abajo)
- Test: `scripts/tests/test_workflows.py` (`test_como_lanzar_y_parar_el_historico_esta_escrito`)

- [ ] **Step 1: La prueba que falla:** `test_como_lanzar_y_parar_el_historico_esta_escrito` — `docs/federacion.md` contiene `gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar`, `-f accion=parar`, `python3 scripts/historico.py estado` y `gh workflow enable historico.yml`; `docs/alevin.md` contiene la orden de la primera prueba (abajo). Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_workflows.py -k historico_esta_escrito` — Expected: FAIL.
- [ ] **Step 2: `docs/federacion.md`**, sección nueva «El carril del histórico (`historico.yml`, desde la parte G)», en el tono del resto del documento: por qué (las tandas daban por leída una página vacía: el mapa, sección 2); cómo lee (la `Federacion` del bot con el arreglo de noviembre, `para_tanda`, sin esperas por defecto, el tope de peticiones; la página muerta, que gasta un intento; el runner rechazado, que acaba al momento y no se relanza, con `RELANZAR_SI_RUNNER_RECHAZADO` para cuando el dueño decida); lo pendiente explícito (`intentos`, `no_disponible` —«no disponible en la federación»—, el estado de actas en formato 2 y lo que significa `pending 0`); el orden (goleadores, actas de la más reciente a la más antigua y de la liga de más nivel a la de menos, detalle, calendario, escudos); las reglas (una ejecución cada vez, fuera de las ventanas, 2.000 páginas al día para empezar, la rampa a 3.000 y 4.000 y cuándo, el día parado por el freno de verdad del carril o del bot, relanzar con 60 servidas, el disparo cada 3 h); la cuarentena y la prueba (los estados `pendiente`, `completo`, `fallo`, `promovido`, el veredicto con sus tres motivos y cómo deshacer una promoción si aun así el bot se pone en rojo: revertir el commit «histórico: …» que la hizo, sin ninguna pasada en marcha, y la base de `main` sigue siendo la de antes porque el bot no sube nada en rojo); `scripts/historico/estado.json` y `python3 scripts/historico.py estado`; que GitHub lo desactiva tras 60 días sin actividad, como el reloj. Las órdenes:

```bash
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar -f temporadas=21,20 -f categorias=alevin -f trabajos=goleadores,actas
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main                    # una ejecución sin esperar al disparo
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=parar    # y -f accion=reanudar
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=reintentar   # vuelve a probar lo que falló
gh variable set HISTORICO_PAGINAS_DIA -R malolocabreralolo-tech/futbol-base-v2 --body 3000           # subir el tope (la rampa: tras tres días sin freno de verdad)
gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow historico.yml --limit 5
git pull && python3 scripts/historico.py estado
```

  Y, en «La espera del freno», la última frase pasa a decir que las tandas leen igual que el bot (y solo la activación sigue con `fetch_fiflp_2425`).
- [ ] **Step 3: `docs/alevin.md`, «Histórico»**: sustituir las tres órdenes por el carril y escribir **la primera prueba pequeña**, alevín de Gran Canaria 2025-26:

```bash
gh run list -R malolocabreralolo-tech/futbol-base-v2 --limit 5          # nada del histórico en marcha
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar -f temporadas=21 -f categorias=alevin -f trabajos=goleadores,actas
gh run watch -R malolocabreralolo-tech/futbol-base-v2
git pull && python3 scripts/historico.py estado
```

  Qué mirar, en este orden: en cada ejecución, su nube y sus páginas (en Azure, ~500 por hora; en AWS, «runner rechazado» en uno o dos minutos y nada más); «2025-26 · goleadores: en la base» con su prueba (de cuánto a cuánto crece la base y cuántos segundos tarda la importación); la pasada del bot siguiente a la promoción, en verde y con los grupos alevín de 2025-26 en «Temporadas anteriores»; las ejecuciones de actas (páginas servidas, frenadas o no) hasta «actas alevín: en la base»; y el tamaño de la base tras la promoción de las actas (lo previsto: unos 1,7 KB por acta, ~3-4 MB por temporada de alevín; si pasa de lo previsto o de 80 MB, parar y esperar a la parte D). Solo entonces, el resto: `-f accion=encargar -f temporadas=21,20,19,18,17,16,15 -f categorias=alevin -f trabajos=goleadores,actas,detalle,escudos` (lo ya promovido no se vuelve a bajar). La sección «Las actas de alevín, en su propio raw» deja de hablar de cadenas por lote: un solo carril, que lleva cada lote en su trabajo.
- [ ] **Step 4: `docs/decisiones.md`**, tres líneas: el histórico va por un solo carril con la lectura del bot, fuera de las ventanas, con 2.000 páginas al día para empezar y parado el día que aparece el freno de verdad, y sin relanzar por caer en un runner de AWS (decisión pendiente del dueño); lo bajado pasa por la cuarentena y una prueba sobre una copia antes de que el bot lo importe; `historico.yml` sustituye a las tres tandas.
- [ ] **Step 5: Comentarios.** Run: `grep -rnE "actas-federacion|goleadores-federacion|detalle-federacion" scripts .github docs/federacion.md docs/alevin.md docs/decisiones.md` — Expected: nada (los planes, el mapa y las revisiones con fecha se quedan como están: cuentan lo que había).
- [ ] **Step 6: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: toda la suite de Python en verde.
- [ ] **Step 7: Commit.** Asunto: «Documentación: el carril del histórico y la primera prueba con alevín 2025-26».
