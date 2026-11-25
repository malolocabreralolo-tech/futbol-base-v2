"""La federación de mentira con la que se prueban las tandas del histórico (federacion_falsa.py).

Tiene que comportarse como la de verdad en lo que se ha medido (docs/freno-2026-11.md y el docstring de
fiflp_carga): el cupo de octubre (15 documentos por IP y después vacías ~5 min), el runner de AWS al que no
sirve nada desde la primera petición, la página muerta (vacía siempre mientras las demás cargan), la que no
existe (un 404) y los desplegables que leen los descargadores, en las cuatro formas en que los leen. Si no, las
pruebas de las tareas siguientes probarían contra otra federación."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fiflp_carga as C  # noqa: E402
import fiflp_render  # noqa: E402
from federacion_falsa import FRENO_HTML, FederacionFalsa, Pagina, RaspadorFalso, Reloj  # noqa: E402

BASE = "https://www.fiflp.com/pnfg/NPcd"
COMP = f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21&CodCompeticion=9"


def urls(n):
    return [f"{COMP}&CodGrupo=1&CodJornada={k}" for k in range(1, n + 1)]


def vacia(f, page, url):
    """Pide `url` en la página falsa y dice si vino vacía (lo que mira fiflp_carga._empty)."""
    page.goto(url)
    return page.evaluate(C.EMPTY_JS)


def test_el_reloj():
    r = Reloj()
    assert r.clock() == 1000.0 and r.wall().isoformat() == "2026-11-25T03:00:00+00:00"
    r.sleep(90)
    assert r.clock() == 1090.0 and r.dormido == [90] and r.wall().isoformat() == "2026-11-25T03:01:30+00:00"


def test_la_federacion_falsa_frena_como_la_medida():
    """Las 15 primeras cargan, la 16.ª viene vacía (EMPTY_JS da True) y, mientras dura el bloqueo (300 s desde
    la primera vacía), todo vacío; después, otro cupo. Otra ejecución (otra IP: .ip_nueva()), otras 15 al
    momento, aunque la de antes siguiera bloqueada."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=15, bloqueos=(300,))
    page = f.page()
    assert [vacia(f, page, u) for u in urls(16)] == [False] * 15 + [True]
    empezo = f.reloj.t - f.coste                                  # la primera vacía
    assert page.content() == FRENO_HTML
    f.reloj.sleep(empezo + 299 - f.reloj.t)
    assert vacia(f, page, urls(1)[0])                             # a los 299 s, sigue
    assert f.reloj.t >= empezo + 300                              # (y ese sondeo, 2 s)
    assert [vacia(f, page, u) for u in urls(16)] == [False] * 15 + [True]          # pasados los 300 s, otro cupo
    f.ip_nueva()
    assert [vacia(f, page, u) for u in urls(16)] == [False] * 15 + [True]
    assert len(f.pedidas) == 16 + 1 + 16 + 16 and f.pedidas[:16] == urls(16)


def test_los_bloqueos_escalan_y_uno_puede_no_acabar():
    """El siguiente de `bloqueos` en cada bloqueo de la misma IP (el último, para los demás); None, no vuelve."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=2, bloqueos=(10, None))
    page = f.page()
    assert [vacia(f, page, u) for u in urls(3)] == [False, False, True]
    f.reloj.sleep(10)
    assert [vacia(f, page, u) for u in urls(3)] == [False, False, True]
    f.reloj.sleep(10 ** 6)
    assert vacia(f, page, urls(1)[0])
    f.ip_nueva()
    assert not vacia(f, page, urls(1)[0])


def test_sin_cupo_sirve_todo():
    """Lo de hoy en Azure (desde el 21/10): ~124-138 páginas por pasada, sin freno."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj())
    page = f.page()
    assert not any(vacia(f, page, u) for u in urls(300))
    assert f.reloj.t == 1000.0 + 300 * f.coste                   # cada carga, `coste` s
    fed = f.fed(deadline=1000.0 + 10 ** 6)
    assert all(fed.goto(page, u) for u in urls(20)) and fed.served == 20 and fed.parada is None


def test_rechaza_todo_desde_la_primera():
    """El runner de AWS: vacío desde la primera petición, siempre, con otra IP también; y la Federacion de la
    falsa, en esa nube, acaba al momento (refused_runner)."""
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), nube="aws", rechaza=True)
    page = f.page()
    assert all(vacia(f, page, u) for u in urls(5))
    f.ip_nueva()
    assert vacia(f, page, urls(1)[0])
    fed = f.fed(deadline=1000.0 + 3600)
    assert fed.cloud == "aws" and not fed.goto(page, urls(1)[0]) and fed.refused_runner and fed.pauses == 0


def test_una_pagina_muerta_viene_vacia_y_las_demas_no():
    muerta = urls(3)[1]
    f = FederacionFalsa(lambda url: Pagina(html="") if url == muerta else Pagina(), Reloj())
    page = f.page()
    assert [vacia(f, page, u) for u in urls(3) + [muerta]] == [False, True, False, True]
    page.goto(muerta)
    assert page.content() == FRENO_HTML                          # el navegador la pinta como la del freno
    # Y la Federacion la cuenta como muerta: pregunta por la última que cargó, que sí carga.
    fed = f.fed(deadline=1000.0 + 3600)
    assert [fed.goto(page, u) for u in urls(3)] == [True, False, True] and fed.dead == 1 and fed.brakes == 0


def test_una_pagina_que_no_existe_responde_404():
    """`sitio(url)` None: la federación contesta 404 (una página de error con contenido, no vacía). Para goto,
    una página que no carga (con sus reintentos), no el freno."""
    f = FederacionFalsa(lambda url: None, Reloj())
    page = f.page()
    assert page.goto(urls(1)[0]).status == 404 and page.evaluate(C.EMPTY_JS) is False
    assert "404" in page.content()
    why = []
    assert not C.goto(page, urls(1)[0], sleep=f.reloj.sleep, log=lambda *_: None, why=why)
    assert why == ["responde 404"] * 3 and f.reloj.dormido == [15, 30]


def test_los_desplegables_en_sus_cuatro_formas():
    """Los guiones con los que los descargadores y el bot leen los desplegables, tal cual están en el código:
    valores (fetch_fiflp_actas._options), pares (las etiquetas de los grupos), {value, text} (JORNADAS_JS,
    fetch_fiflp_detalle._jornadas) e {id, name} (COMPETITIONS_JS, fetch_fiflp_detalle.live_comps). Sin el
    valor vacío ni el "0" cuando el guion los quita; durante el freno, nada (la página vacía no tiene
    desplegables)."""
    import fetch_fiflp_actas as A
    import fetch_fiflp_detalle as D
    import update_fiflp as U
    opciones = {"competicion": [("0", "Elija"), ("9", "Alevín Gran Canaria")],
                "grupo": [("", "--"), ("1", "Grupo 1"), ("2", "Grupo 2")],
                "jornada": [("0", "--"), ("11", "Jornada 1 (05-10-2019)"), ("12", "Jornada 2 (12-10-2019)")]}
    f = FederacionFalsa(lambda url: Pagina(opciones=opciones), Reloj(), cupo=1, bloqueos=(None,))
    page = f.page()
    page.goto(COMP)
    assert A._options(page, "grupo") == ["1", "2"] and A._options(page, "jornada") == ["11", "12"]
    assert page.evaluate("""() => Array.from(document.querySelectorAll('select[name="grupo"] option'))
            .map(o => [o.value, o.text.trim()])""") == [["", "--"], ["1", "Grupo 1"], ["2", "Grupo 2"]]
    assert D._grupos(page, None) == [["1", "Grupo 1"], ["2", "Grupo 2"]]
    assert page.evaluate(U.JORNADAS_JS) == [{"value": "11", "text": "Jornada 1 (05-10-2019)"},
                                            {"value": "12", "text": "Jornada 2 (12-10-2019)"}]
    assert page.evaluate(U.GRUPOS_JS) == [{"value": "1", "text": "Grupo 1"}, {"value": "2", "text": "Grupo 2"}]
    assert page.evaluate(U.COMPETITIONS_JS) == [{"id": "9", "name": "Alevín Gran Canaria"}]
    # El de fetch_fiflp_actas.discover_comps pone el texto en mayúsculas (toUpperCase).
    assert page.evaluate("""() => Array.from(document.querySelector('select[name="competicion"]').options)
            .filter(o => o.value && o.value !== '0')
            .map(o => ({value: o.value, text: o.text.trim().toUpperCase()}))""") == [
        {"value": "9", "text": "ALEVÍN GRAN CANARIA"}]
    # Frenada (el cupo, 1, ya se gastó): la vacía no tiene desplegables; los lectores esperan y siguen.
    page.goto(COMP)
    antes = f.reloj.t
    assert page.evaluate(U.JORNADAS_JS) == [] and A._options(page, "grupo") == []
    assert f.reloj.t == antes + 4 * 3.0                          # sus cuatro wait_for_timeout(3000)


def test_lo_demas_de_la_pagina_y_el_raspador():
    """Lo que los lectores piden a la página además de los desplegables (el aplanado, los escudos, el HTML, los
    marcos) y los lectores del raspador falso, con los `datos` de la página cargada."""
    from fetch_fiflp_goleadores import CRESTS_JS
    datos = [{"home": "Equipo A", "away": "Equipo B", "hs": 2, "as": 1}]
    f = FederacionFalsa(lambda url: Pagina(html="<html><body><p>hola</p></body></html>", datos=datos)
                        if "CodJornada" in url else Pagina(), Reloj())
    page = f.page()
    assert page.content() == FRENO_HTML and RaspadorFalso.parse_matches(page) == []   # aún nada cargado
    page.goto(urls(1)[0])
    assert page.content() == "<html><body><p>hola</p></body></html>"
    assert fiflp_render.flatten(page) == 0 and fiflp_render.flatten(page, "#x") == 0
    assert page.evaluate(CRESTS_JS) == {} and page.query_selector_all("table") == [] and page.frames == []
    assert page.is_closed() is False and page.wait_for_function("() => true") is True
    page.wait_for_timeout(2500)
    assert f.reloj.t == 1000.0 + f.coste + 2.5
    fed = f.fed()
    assert fed.BASE == BASE and fed.interval == 7.0 and fed.cloud == "azure"
    assert fed.parse_matches(page) == datos and fed.parse_standings(page) == datos
    assert fed.parse_matches(page) is not datos                   # una copia: un lector no cambia el sitio
    page.goto(COMP)
    assert fed.parse_matches(page) == []
    # El registro de la Federacion, en .dicho; su reloj, el de la falsa.
    fed = f.fed(deadline=999.0 + f.reloj.t, max_pages=1)
    fed.goto(page, urls(2)[1])
    fed.goto(page, urls(2)[0])
    assert f.dicho == ["      se llega al tope de 1 petición de esta ejecución: nada más"]
