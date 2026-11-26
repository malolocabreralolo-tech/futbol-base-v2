"""El detalle de la federación (2026-10): clasificación con casa/fuera y sanciones,
directorio de equipos (equipación, campo, escudo) y ficha de campo, leídos de
muestras reales (fixtures/detalle/), y el raspador reanudable que los guarda."""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_fiflp_detalle as D
from fiflp_detalle import parse_campo, parse_clasificacion, parse_directorio

FIX = Path(__file__).parent / "fixtures" / "detalle"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_clasificacion_detallada_trae_casa_fuera_sancion_y_codigo_de_equipo():
    rows = parse_clasificacion(read("clasificacion_2526_A2.html"))
    assert len(rows) == 12
    mesas = next(r for r in rows if r["codequipo"] == 62744)
    assert mesas["team"] == 'MESAS HURACAN, U.D. LAS "A"'
    assert (mesas["pos"], mesas["pts"]) == (4, 43)
    assert mesas["home"] == {"j": 11, "g": 7, "e": 0, "p": 4}
    assert mesas["away"] == {"j": 11, "g": 7, "e": 1, "p": 3}
    assert (mesas["j"], mesas["g"], mesas["e"], mesas["p"]) == (22, 14, 1, 7)
    assert (mesas["gf"], mesas["gc"], mesas["sanction"]) == (137, 72, 0)
    assert mesas["form"] == "PGGPG"
    # Las filas salen en el orden de la tabla y con todos los puestos.
    assert [r["pos"] for r in rows] == list(range(1, 13))
    assert sum(r["home"]["j"] + r["away"]["j"] for r in rows) == 12 * 22


def test_clasificacion_de_una_jornada_temprana():
    rows = parse_clasificacion(read("clasificacion_2627_FF.html"))
    assert rows and all(r["codequipo"] for r in rows)
    lider = rows[0]
    assert lider["home"]["j"] + lider["away"]["j"] == lider["j"]


def test_la_resumida_sirve_si_no_hay_detallada():
    html = read("clasificacion_2526_A2.html")
    # Sin la tabla detallada (la primera), queda la resumida: sin casa/fuera.
    first = html.find("<table")
    second = html.find("<table", html.find("</table>", first))
    rows = parse_clasificacion(html[second:])
    assert len(rows) == 12
    assert "home" not in rows[0] and rows[0]["j"] == 22 and rows[0]["gf"] is None


def test_directorio_da_equipacion_campo_y_escudo_sin_contacto():
    teams = parse_directorio(read("directorio_2526_A2.html"))
    assert len(teams) == 12
    by_code = {t["codequipo"]: t for t in teams}
    udlp = by_code[31950]
    assert udlp["team"] == "PALMAS, U.D. LAS"
    assert (udlp["shirt"], udlp["shorts"], udlp["socks"]) == ("AMARILLA", "AZUL", "AZULES")
    assert (udlp["venue_code"], udlp["venue"]) == (75, "ANEXO GRAN CANARIA F8")
    assert udlp["surface"] == "Hierba Artificial (HA)"
    assert udlp["crest"].startswith("/pnfg/pimg/Clubes/")
    mesas = by_code[62744]
    assert mesas["shirt"] == "BLANCA CON FRANJA ROJA" and mesas["crest"] is None
    # Ni teléfonos, ni direcciones, ni personas: solo las claves de arriba.
    allowed = {"codequipo", "team", "crest", "shirt", "shorts", "socks", "venue_code", "venue", "surface"}
    assert all(set(t) == allowed for t in teams)
    blob = json.dumps(teams, ensure_ascii=False)
    assert "609111162" not in blob and "Penáguilas" not in blob and "Juan Francisco" not in blob


def test_ficha_de_campo():
    campo = parse_campo(read("campo_75.html"))
    assert campo["code"] == 75 and campo["name"] == "ANEXO GRAN CANARIA F8"
    assert (campo["lat"], campo["lon"]) == (28.102428, -15.4544136)
    assert campo["address"] == "C. Fondos de Segura, s/n"
    assert (campo["city"], campo["postal_code"]) == ("Las Palmas de Gran Canaria", "35019")
    assert campo["surface"] == "Hierba Artificial"
    assert campo["fenced"] is False and campo["internet"] is False
    assert "PALMAS, U.D. LAS (BEN)" in campo["teams"] and campo["training"] == []
    assert campo["photo"] is None


def test_ficha_vacia_o_sin_coordenadas():
    assert parse_campo("<html><head></head><body></body></html>") is None
    html = read("campo_75.html").replace("loc:28.102428+-15.4544136", "loc:0+0")
    assert parse_campo(html)["lat"] is None


# ── El raspador, con una web falsa ────────────────────────────────────────────

class FakePage:
    """Sirve el HTML de cada tipo de página; el desplegable de grupos por evaluate."""

    def __init__(self, web):
        self.web, self.url, self.visits = web, "", []

    def content(self):
        for key, html in self.web.items():
            if key in self.url:
                return html
        return "<html></html>"

    def evaluate(self, script, *args):
        if 'select[name="grupo"]' in script:
            return [["G1", "GRUPO 1"], ["G2", "GRUPO 2"]]
        if 'select[name="competicion"]' in script:
            return [{"id": "52", "name": "LIGA PREFERENTE BENJAMIN F-8 GRAN CANARIA"},
                    {"id": "92", "name": "LIGA PRIMERA BENJAMIN FUTBOL SALA GRAN CANARIA"},
                    {"id": "50", "name": "LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA"}]
        return []

    def wait_for_timeout(self, ms):
        pass


class FakeF:
    BASE = "https://fed"

    def __init__(self, page, fail=()):
        self.page, self.fail = page, fail

    def goto(self, page, url):
        page.url = url
        page.visits.append(url)
        return not any(f in url for f in self.fail)

    def delay(self):
        pass


def web():
    return {"NFG_VisClasificacion": read("clasificacion_2526_A2.html"),
            "NFG_LstDirectorioEquipos": read("directorio_2526_A2.html"),
            "NFG_VisCampos": read("campo_75.html")}


def test_raspador_guarda_cada_grupo_y_reanuda(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "HERE", tmp_path)
    monkeypatch.setattr(D, "CAMPOS_RAW", tmp_path / "fiflp_campos_raw.json")
    monkeypatch.setattr(D, "DB_PATH", tmp_path / "no-hay-base.db")
    page = FakePage(web())
    F = FakeF(page)
    # 2016-17 no está en el catálogo: las competiciones se leen de la web (sin sala ni alevín).
    assert D.run_groups(page, F, ["12"], set(), time.monotonic() + 60, log=lambda *a: None)
    raw = json.loads((tmp_path / "fiflp_detalle_2016-2017_raw.json").read_text())
    assert raw["_comps"] == [["52", "LIGA PREFERENTE BENJAMIN F-8 GRAN CANARIA"]]
    assert set(k for k in raw if not k.startswith("_")) == {"52:G1", "52:G2"}
    g1 = raw["52:G1"]
    assert g1["ok"] and len(g1["clasificacion"]) == 12 and len(g1["directorio"]) == 12
    assert g1["grupo_name"] == "GRUPO 1" and "jornadas" not in g1
    # Una segunda tanda no vuelve a pedir nada de lo ya leído.
    page.visits.clear()
    assert D.run_groups(page, F, ["12"], set(), time.monotonic() + 60, log=lambda *a: None)
    assert page.visits == []
    # Los campos: los de los directorios.
    assert D.run_campos(page, F, time.monotonic() + 60, log=lambda *a: None)
    campos = json.loads((tmp_path / "fiflp_campos_raw.json").read_text())
    assert campos["75"]["ok"] and campos["75"]["lat"] == 28.102428
    assert "148" in campos      # el de Las Mesas (Pepe Gonçalvez), aunque la web falsa sirva otra ficha


def test_un_grupo_que_no_carga_se_reintenta_en_la_siguiente_tanda(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "HERE", tmp_path)
    page = FakePage(web())
    D.run_groups(page, FakeF(page, fail=("CodGrupo=G2", "Sch_CodGrupo=G2")), ["12"], set(),
                 time.monotonic() + 60, log=lambda *a: None)
    raw = json.loads((tmp_path / "fiflp_detalle_2016-2017_raw.json").read_text())
    assert raw["52:G1"]["ok"] and not raw["52:G2"]["ok"]
    page.visits.clear()
    D.run_groups(page, FakeF(page), ["12"], set(), time.monotonic() + 60, log=lambda *a: None)
    assert all("G2" in v for v in page.visits) and page.visits
    raw = json.loads((tmp_path / "fiflp_detalle_2016-2017_raw.json").read_text())
    assert raw["52:G2"]["ok"]


def test_plazo_agotado_para_sin_perder_lo_leido(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "HERE", tmp_path)
    page = FakePage(web())
    assert D.run_groups(page, FakeF(page), ["12"], set(), time.monotonic() - 1, log=lambda *a: None) is False


# ── Con la lectura del bot (fiflp_carga.Federacion) sobre la federación de mentira ──
# Temporada 12 (2016-2017), una competición 900 con un grupo G1 de cinco jornadas (sus partidos, los datos del
# raspador falso). Sin esperas del freno (HISTORICO_ESPERAS=0): la espera del carril, en test_fiflp_carga y en las
# de las actas y los goleadores.

from federacion_falsa import FederacionFalsa, Pagina, Reloj  # noqa: E402

JORNADAS = [(str(10 + n), f"{n} - {day}-10-2016") for n, day in ((1, "01"), (2, "08"), (3, "15"), (4, "22"), (5, "29"))]


def partido(n):
    return [{"home": f"Equipo {n}A", "away": f"Equipo {n}B", "hs": 1, "as": 0, "date": ""}]


def sitio_detalle(muertas=()):
    def sitio(url):
        if any(m in url for m in muertas):
            return Pagina(html="")
        if "NFG_VisClasificacion" in url:
            return Pagina(html=read("clasificacion_2526_A2.html"))
        if "NFG_LstDirectorioEquipos" in url:
            return Pagina(html=read("directorio_2526_A2.html"))
        if "NFG_VisCampos" in url:
            return Pagina(html=read("campo_75.html"))
        if "NFG_CmpJornada" in url and "CodJornada=" in url:
            n = int(url.rsplit("CodJornada=", 1)[1]) - 10
            return Pagina(datos=partido(n))
        if "NFG_CmpJornada" in url and "CodGrupo=" in url:
            return Pagina(opciones={"jornada": JORNADAS})
        if "NFG_CmpJornada" in url:
            return Pagina(opciones={"grupo": [("G1", "GRUPO 1")]})
        return None
    return sitio


@pytest.fixture
def fed_detalle(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "HERE", tmp_path)
    monkeypatch.setattr(D, "CAMPOS_RAW", tmp_path / "fiflp_campos_raw.json")
    monkeypatch.setattr(D, "DB_PATH", tmp_path / "no-hay-base.db")
    monkeypatch.setattr(D, "catalog_comps", lambda code, categories=None: [("900", "LIGA BENJAMIN X")])
    return tmp_path / "fiflp_detalle_2016-2017_raw.json"


def correr(f, jornadas=("12",), campos=False):
    f.ip_nueva()
    f.pedidas.clear()
    F = f.fed(deadline=f.reloj.t + 3600, max_pauses=0)
    partes = {}
    if campos:
        ok = D.run_campos(f.page(), F, time.monotonic() + 600, log=lambda *a: None, partes=partes)
    else:
        ok = D.run_groups(f.page(), F, ["12"], set(jornadas), time.monotonic() + 600, log=lambda *a: None,
                          partes=partes)
    return ok, F, partes



def test_el_calendario_de_un_grupo_se_reanuda_por_la_jornada_que_falta(fed_detalle):
    # La competición, la clasificación, el directorio, el calendario y dos jornadas: la 3.ª, frenada.
    f = FederacionFalsa(sitio_detalle(), Reloj(), cupo=6, bloqueos=(None,))
    ok, F, partes = correr(f)
    g1 = json.loads(fed_detalle.read_text())["900:G1"]
    assert not ok and F.parada == "freno"
    assert g1["ok"] and len(g1["clasificacion"]) == 12 and len(g1["directorio"]) == 12
    assert sorted(g1["jornadas_leidas"]) == ["Jornada 1", "Jornada 2"] and "jornadas" not in g1
    assert g1["jornadas_leidas"]["Jornada 2"][0]["home"] == "Equipo 2A" and "intentos" not in g1
    assert partes == {"calendario:2016-2017": {"completo": False, "pendientes": 1, "no_disponible": 0}}
    f = FederacionFalsa(sitio_detalle(), Reloj())
    ok, F, partes = correr(f)
    assert [u.split("NPcd")[1] for u in f.pedidas] == [
        "/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=12&CodCompeticion=900&CodGrupo=G1"] + [
        f"/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=12&CodCompeticion=900&CodGrupo=G1&CodJornada={v}"
        for v in ("13", "14", "15")]
    g1 = json.loads(fed_detalle.read_text())["900:G1"]
    assert ok and sorted(g1["jornadas"]) == [f"Jornada {n}" for n in range(1, 6)] and "jornadas_leidas" not in g1
    assert g1["jornadas"]["Jornada 1"][0]["date"] == "2016-10-01"
    assert partes == {"calendario:2016-2017": {"completo": True, "pendientes": 0, "no_disponible": 0}}


def test_un_freno_no_pisa_un_grupo_ya_leido(fed_detalle):
    f = FederacionFalsa(sitio_detalle(), Reloj())
    correr(f, jornadas=())                                      # leído sin jornadas
    antes = fed_detalle.read_bytes()
    assert "jornadas" not in json.loads(antes)["900:G1"]
    f = FederacionFalsa(sitio_detalle(), Reloj(), cupo=0, bloqueos=(None,))
    ok, F, partes = correr(f)                                   # pedidas sus jornadas, frenada en la primera
    assert not ok and F.parada == "freno" and fed_detalle.read_bytes() == antes
    assert partes["calendario:2016-2017"]["pendientes"] == 1


def test_un_grupo_cuya_clasificacion_viene_vacia_siempre_acaba_no_disponible(fed_detalle):
    f = FederacionFalsa(sitio_detalle(muertas=("NFG_VisClasificacion",)), Reloj())
    for n in (1, 2):
        ok, F, partes = correr(f, jornadas=())
        g1 = json.loads(fed_detalle.read_text())["900:G1"]
        assert g1["ok"] is False and g1["intentos"] == n and F.parada is None and F.dead == 1
    ok, F, partes = correr(f, jornadas=())
    assert json.loads(fed_detalle.read_text())["900:G1"]["no_disponible"] is True
    assert partes == {"detalle:2016-2017": {"completo": True, "pendientes": 0, "no_disponible": 1}}
    ok, F, partes = correr(f, jornadas=())
    assert f.pedidas == []


def test_una_jornada_muerta_gasta_intentos_y_no_da_el_calendario_por_entero(fed_detalle):
    """Una jornada que viene vacía siempre: el grupo queda leído (clasificación y directorio) con las otras
    jornadas en «jornadas_leidas», un intento por ejecución y, con tres, no disponible; nunca «jornadas»."""
    f = FederacionFalsa(sitio_detalle(muertas=("CodJornada=13",)), Reloj())
    for n in (1, 2, 3):
        ok, F, partes = correr(f)
        g1 = json.loads(fed_detalle.read_text())["900:G1"]
        assert g1["ok"] and g1["intentos"] == n and "jornadas" not in g1 and len(g1["jornadas_leidas"]) == 4
    assert g1["no_disponible"] is True and partes["calendario:2016-2017"]["completo"]
    ok, F, partes = correr(f)
    assert f.pedidas == []


def test_una_competicion_sin_grupos_gasta_intentos_en_el_raw(fed_detalle):
    f = FederacionFalsa(lambda url: Pagina() if "NFG_CmpJornada" in url else None, Reloj())
    for n in (1, 2):
        correr(f, jornadas=())
        raw = json.loads(fed_detalle.read_text())
        assert raw["_intentos"] == {"900": n} and "900" not in raw.get("_grupos", {})
    ok, F, partes = correr(f, jornadas=())
    raw = json.loads(fed_detalle.read_text())
    assert raw["_grupos"]["900"] == [] and partes["detalle:2016-2017"] == {"completo": True, "pendientes": 0,
                                                                          "no_disponible": 1}
    correr(f, jornadas=())
    assert f.pedidas == []


def test_una_ficha_de_campo_vacia_acaba_no_disponible(fed_detalle):
    (fed_detalle.parent / "fiflp_detalle_2016-2017_raw.json").write_text(json.dumps(
        {"900:G1": {"ok": True, "directorio": [{"venue_code": 75}, {"venue_code": 76}]}}), encoding="utf-8")
    campos = fed_detalle.parent / "fiflp_campos_raw.json"
    # La ficha 76 carga pero sin datos; la 75, bien.
    f = FederacionFalsa(lambda url: Pagina(html=read("campo_75.html")) if "Codigo_Campo=75" in url else Pagina(),
                        Reloj())
    for n in (1, 2):
        ok, F, partes = correr(f, campos=True)
        data = json.loads(campos.read_text())
        assert data["75"]["ok"] and data["76"] == {**data["76"], "ok": False, "intentos": n}
        assert "no_disponible" not in data["76"] and partes["campos"]["pendientes"] == 1
    ok, F, partes = correr(f, campos=True)
    assert json.loads(campos.read_text())["76"]["no_disponible"] is True
    assert partes == {"campos": {"completo": True, "pendientes": 0, "no_disponible": 1}}
    correr(f, campos=True)
    assert f.pedidas == []
    # Con el freno, la ficha ni se escribe (el cupo: la página de la temporada y la ficha 75).
    campos.unlink()
    f = FederacionFalsa(lambda url: Pagina(html=read("campo_75.html")), Reloj(), cupo=2, bloqueos=(None,))
    ok, F, partes = correr(f, campos=True)
    assert not ok and F.parada == "freno" and list(json.loads(campos.read_text())) == ["75"]


def test_una_temporada_sin_competiciones_en_la_web_acaba_sin_ninguna(tmp_path, monkeypatch):
    """Una temporada que el catálogo no tiene y cuya página no da competiciones: un intento por ejecución
    (en _intentos), sin guardar la lista vacía como leída; con tres, ninguna, y no se vuelve a pedir. Con el
    freno, ni el intento."""
    monkeypatch.setattr(D, "HERE", tmp_path)
    path = tmp_path / "fiflp_detalle_2016-2017_raw.json"
    f = FederacionFalsa(lambda url: Pagina(), Reloj(), cupo=0, bloqueos=(None,))
    ok, F, partes = correr(f, jornadas=())
    assert not ok and F.parada == "freno" and not path.exists()
    f = FederacionFalsa(lambda url: Pagina(), Reloj())
    for n in (1, 2):
        ok, F, partes = correr(f, jornadas=())
        raw = json.loads(path.read_text())
        assert raw["_intentos"] == {"_comps": n} and "_comps" not in raw
        assert partes["detalle:2016-2017"]["pendientes"] == 1
    ok, F, partes = correr(f, jornadas=())
    assert json.loads(path.read_text())["_comps"] == []
    assert partes == {"detalle:2016-2017": {"completo": True, "pendientes": 0, "no_disponible": 1}}
    correr(f, jornadas=())
    assert f.pedidas == []


def test_un_corte_en_cualquier_peticion_no_deja_nada_mal_leido(fed_detalle):
    """La pregunta de la parte G para el detalle: el corte (el freno de verdad) en cada petición posible (la
    lista de grupos, la clasificación, el directorio, el calendario, cada jornada) deja solo lo leído: ningún
    grupo sin `ok`, ningún intento gastado, «jornadas» solo con el calendario entero; y una ejecución sin
    freno después deja lo mismo que una entera sin cortes."""
    def sin_fecha(raw):
        return {k: ({c: v for c, v in e.items() if c != "fetched"} if isinstance(e, dict) and "ok" in e else e)
                for k, e in raw.items()}
    ok, F, partes = correr(FederacionFalsa(sitio_detalle(), Reloj()))
    entera, total = sin_fecha(json.loads(fed_detalle.read_text())), F.pages
    assert ok and total == 1 + 3 + 5
    for k in range(total):
        fed_detalle.unlink(missing_ok=True)
        ok, F, partes = correr(FederacionFalsa(sitio_detalle(), Reloj(), cupo=k, bloqueos=(None,)))
        assert not ok and F.parada == "freno", k
        raw = json.loads(fed_detalle.read_text()) if fed_detalle.exists() else {}
        g1 = raw.get("900:G1")
        if g1 is not None:
            assert g1["ok"] and "intentos" not in g1 and "jornadas" not in g1, k
            assert len(g1["clasificacion"]) == 12 and len(g1["directorio"]) == 12, k
        assert not partes["calendario:2016-2017"]["completo"], k
        ok, F, partes = correr(FederacionFalsa(sitio_detalle(), Reloj()))
        assert ok and sin_fecha(json.loads(fed_detalle.read_text())) == entera, k


def test_una_ficha_muerta_al_empezar_no_es_el_freno(fed_detalle):
    """Una ejecución de solo campos: la URL de una ficha no lleva la temporada, así que antes de la primera, la
    de competiciones (fiflp_carga.preparar). Una ficha vacía siempre gasta su intento y las demás se leen."""
    (fed_detalle.parent / "fiflp_detalle_2016-2017_raw.json").write_text(json.dumps(
        {"900:G1": {"ok": True, "directorio": [{"venue_code": 75}, {"venue_code": 76}]}}), encoding="utf-8")
    f = FederacionFalsa(lambda url: Pagina(html="") if "Codigo_Campo=75" in url else
                        Pagina(html=read("campo_75.html")) if "NFG_VisCampos" in url else Pagina(), Reloj())
    ok, F, partes = correr(f, campos=True)
    data = json.loads((fed_detalle.parent / "fiflp_campos_raw.json").read_text())
    assert ok and F.parada is None and "CodTemporada=22" in f.pedidas[0]
    assert data["75"]["intentos"] == 1 and data["76"]["ok"]


def test_una_pagina_que_no_se_entiende_gasta_un_intento_como_una_muerta(fed_detalle, monkeypatch):
    """I3 de la revisión final: la clasificación del grupo carga, pero su contenido hace lanzar al intérprete.
    Antes la ejecución acababa con error en ese grupo cada vez; ahora gasta un intento como una página muerta y,
    con tres, «no disponible» con el tipo de la excepción (nunca su texto: puede llevar un nombre)."""
    real = D.parse_clasificacion

    def interprete(html):
        if "ROMPE" in html:
            raise ValueError("Nombre Inventado")
        return real(html)
    monkeypatch.setattr(D, "parse_clasificacion", interprete)
    sitio = sitio_detalle()
    f = FederacionFalsa(lambda url: Pagina(html="<html><body>ROMPE</body></html>") if "NFG_VisClasificacion" in url
                        else sitio(url), Reloj())
    for n in (1, 2, 3):
        ok, F, partes = correr(f, jornadas=())
        g1 = json.loads(fed_detalle.read_text())["900:G1"]
        assert ok and F.parada is None and g1["ok"] is False and g1["intentos"] == n and g1["motivo"] == "ValueError"
    assert g1["no_disponible"] is True and "Inventado" not in fed_detalle.read_text()
    assert partes == {"detalle:2016-2017": {"completo": True, "pendientes": 0, "no_disponible": 1}}


def test_una_jornada_que_no_se_entiende_gasta_un_intento_y_se_leen_las_demas(fed_detalle):
    """Una jornada del calendario cuyo contenido hace lanzar al intérprete (sus partidos no son partidos): como
    una jornada muerta, las demás se leen («jornadas_leidas»), el grupo gasta un intento por ejecución y, con
    tres, no disponible, con el motivo. La ejecución no acaba en rojo."""
    sitio = sitio_detalle()
    f = FederacionFalsa(lambda url: Pagina(datos=["no es un partido"]) if url.endswith("CodJornada=13")
                        else sitio(url), Reloj())
    for n in (1, 2, 3):
        ok, F, partes = correr(f)
        g1 = json.loads(fed_detalle.read_text())["900:G1"]
        assert ok and F.parada is None and g1["ok"] and g1["intentos"] == n and g1["motivo"] == "TypeError"
        assert "jornadas" not in g1 and sorted(g1["jornadas_leidas"]) == ["Jornada 1", "Jornada 2", "Jornada 4",
                                                                          "Jornada 5"]
    assert g1["no_disponible"] is True and partes["calendario:2016-2017"]["completo"]


def test_una_ficha_de_campo_que_no_se_entiende_acaba_no_disponible(fed_detalle, monkeypatch):
    (fed_detalle.parent / "fiflp_detalle_2016-2017_raw.json").write_text(json.dumps(
        {"900:G1": {"ok": True, "directorio": [{"venue_code": 75}, {"venue_code": 76}]}}), encoding="utf-8")
    campos = fed_detalle.parent / "fiflp_campos_raw.json"
    real = D.parse_campo

    def interprete(html):
        if "ROMPE" in html:
            raise KeyError("Nombre Inventado")
        return real(html)
    monkeypatch.setattr(D, "parse_campo", interprete)
    f = FederacionFalsa(lambda url: Pagina(html="<html><body>ROMPE</body></html>") if "Codigo_Campo=76" in url
                        else Pagina(html=read("campo_75.html")), Reloj())
    for n in (1, 2, 3):
        ok, F, partes = correr(f, campos=True)
        data = json.loads(campos.read_text())
        assert ok and data["75"]["ok"] and data["76"]["intentos"] == n and data["76"]["motivo"] == "KeyError"
    assert data["76"]["no_disponible"] is True and "Inventado" not in campos.read_text()
    assert partes == {"campos": {"completo": True, "pendientes": 0, "no_disponible": 1}}
