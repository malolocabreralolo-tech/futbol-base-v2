"""El enumerador de actas de temporadas pasadas va por URL directa (2026-10):
elegir grupo con select_option sobre el formulario OCULTO de FIFLP daba timeout
en todos los grupos salvo el primero. Desde noviembre de 2026 (parte G) lee como el
bot (fiflp_carga.Federacion) y apunta lo que le falta jornada a jornada en el estado
(formato 2): un corte a mitad deja pendiente justo lo que no leyó, una página muerta
gasta un intento por ejecución y, con tres, queda no disponible; y las actas se leen
con un solo navegador, competición a competición. Sin red: la federación de mentira
(federacion_falsa.py), con dos competiciones (900 y 901) de dos grupos de cuatro
jornadas y dos actas por jornada."""
import json
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import scripts.fetch_fiflp_actas as A

CATALOGO = json.loads((ROOT / "scripts" / "tests" / "fixtures" / "fiflp_comps_catalog.json").read_text(encoding="utf-8"))


def test_backfill_takes_the_catalog_competitions_without_futsal_and_rereads_old_actas():
    comps = A.catalog_comps("21", catalog=CATALOGO)                # el congelado, no el de discover-fiflp.yml
    assert "54422888" in comps and "54976641" in comps            # liga prebenjamín y Clausura Benjamín
    assert "54422904" not in comps                                # LIGA BENJAMIN FUTBOL SALA
    assert A.catalog_comps("99", catalog=CATALOGO) == []
    assert A.needs_rescrape({"header": {}, "lineups": {}})        # lector de mayo: sin «consistent»
    assert not A.needs_rescrape({"header": {}, "consistent": True})


def test_an_acta_that_cannot_be_flattened_is_not_asked_for_again():
    """Un acta que, releída con el lector aplanado, sigue sin aplanarse queda marcada: cada tanda la
    volvía a pedir y la cadena no paraba nunca."""
    old = {"header": {"season": "2023/2024"}}
    assert A.needs_rescrape(old)
    assert not A.needs_rescrape({**old, "rescrape_failed": True})
    assert not A.needs_rescrape({**old, "consistent": True})


# ── La federación de mentira ──────────────────────────────────────────────────

from federacion_falsa import FederacionFalsa, Pagina, Reloj  # noqa: E402

BASE = "https://www.fiflp.com/pnfg/NPcd"
ACTA_HTML = (ROOT / "scripts" / "tests" / "fixtures" / "acta_flat_2526_tamaraceite_huracan.html").read_text(encoding="utf-8")
GRUPOS = [("G1", "GRUPO 1"), ("G2", "GRUPO 2")]


def actas_de(comp, grupo, jornada):
    """Los códigos de las dos actas de una jornada: 900 G1 jornada 3 → 900131 y 900132."""
    return [f"{comp}{grupo[1]}{jornada}{k}" for k in (1, 2)]


def todas(comp):
    return {cod for g, _ in GRUPOS for j in range(1, 5) for cod in actas_de(comp, g, j)}


def sitio_actas(muertas=()):
    """La web: la de competiciones de la temporada, cada competición con sus dos grupos, cada grupo con sus
    cuatro jornadas, cada jornada con dos enlaces a actas (y uno a una previa, que no es un acta) y cada acta.
    `muertas`, URLs (o trozos) que vienen vacías siempre."""
    def sitio(url):
        if any(m in url for m in muertas):
            return Pagina(html="")
        if "NFG_CmpPartido" in url:
            return Pagina(html=ACTA_HTML)
        if "NFG_CmpJornada" not in url:
            return None
        m = re.search(r"CodCompeticion=(\d+)(?:&CodGrupo=(G\d))?(?:&CodJornada=(\d+))?$", url)
        if not m:
            return Pagina(opciones={"competicion": [("900", "LIGA BENJAMIN X"), ("901", "LIGA BENJAMIN Y")]})
        comp, grupo, jornada = m.groups()
        if jornada:
            links = "".join(f'<a href="/pnfg/NPcd/NFG_CmpPartido?cod_primaria=1000120&amp;CodActa={cod}">acta</a>'
                            for cod in actas_de(comp, grupo, jornada))
            return Pagina(html=f'<html><body>{links}<a href="/pnfg/NPcd/NFG_CmpPrevio?CodActa=999">previa</a>'
                               "</body></html>")
        if grupo:
            return Pagina(opciones={"jornada": [(str(n), f"{n} - 0{n}-10-2025") for n in range(1, 5)]})
        return Pagina(opciones={"grupo": GRUPOS})
    return sitio


def nueva_enumeracion():
    return {"grupos": None, "pendientes": {}}


def enumerar(f, comp="900", ledger=None, index=None, intentos=None, no_disponible=None, **kw):
    f.pedidas.clear()
    F = f.fed(deadline=f.reloj.t + 3600, max_pauses=0, **kw)
    ledger = nueva_enumeracion() if ledger is None else ledger
    index = {} if index is None else index
    intentos = {} if intentos is None else intentos
    no_disponible = [] if no_disponible is None else no_disponible
    res = A.enumerar(f.page(), F, "21", comp, ledger, index, intentos, no_disponible, log=lambda *a: None)
    return res, F, ledger, index, intentos, no_disponible


def test_cada_grupo_y_jornada_se_pide_por_su_url():
    f = FederacionFalsa(sitio_actas(), Reloj())
    res, F, ledger, index, intentos, nd = enumerar(f)
    assert res == "completa" and set(index) == todas("900")                      # sin la previa
    assert index["900131"] == {"comp_id": "900", "grupo": "G1", "jornada": "3"}
    assert ledger == {"grupos": [["G1", "GRUPO 1"], ["G2", "GRUPO 2"]], "pendientes": {}}
    base = f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21&CodCompeticion=900"
    assert f.pedidas == [base] + [u for g, _ in GRUPOS for u in
                                  [f"{base}&CodGrupo={g}"] + [f"{base}&CodGrupo={g}&CodJornada={j}" for j in range(1, 5)]]
    assert intentos == {} and nd == [] and F.parada is None
    # Completa, no se vuelve a pedir nada.
    res, F, *_ = enumerar(f, ledger=ledger, index=index)
    assert res == "completa" and f.pedidas == []


def test_solo_los_grupos_pedidos(monkeypatch):
    monkeypatch.setattr(A, "GROUP_FILTER", ["900:GRUPO 2"])
    f = FederacionFalsa(sitio_actas(), Reloj())
    res, F, ledger, index, *_ = enumerar(f)
    assert {e["grupo"] for e in index.values()} == {"G2"} and not any("CodGrupo=G1" in u for u in f.pedidas)
    # El grupo 1 sigue pendiente (no se pidió): la competición no está completa.
    assert res == "pendiente" and ledger["pendientes"] == {"G1": None}
    monkeypatch.setattr(A, "GROUP_FILTER", ["99999:GRUPO 2"])          # de otra competición: nada
    res, F, ledger, index, *_ = enumerar(FederacionFalsa(sitio_actas(), Reloj()))
    assert index == {} and res == "pendiente"


@pytest.mark.parametrize("tope", [False, True])
def test_un_corte_a_mitad_de_la_enumeracion_deja_las_jornadas_pendientes(tanda, tope):
    """Tras la competición, el calendario y las cuatro jornadas del grupo 1, el calendario del grupo 2 viene
    vacío (el freno de verdad; o, con max_pages=6, el tope): el índice tiene las ocho actas del grupo 1 y el
    grupo 2 queda pendiente sin lista de jornadas. La ejecución siguiente pide solo lo del grupo 2 y las actas."""
    f = FederacionFalsa(sitio_actas(), Reloj()) if tope else FederacionFalsa(sitio_actas(), Reloj(), cupo=6,
                                                                              bloqueos=(None,))
    tanda.run(f, "--comps", "900", **({"max_pages": 6} if tope else {}))
    index, status = tanda.index(), tanda.status()
    assert set(index) == {c for c in todas("900") if c[3] == "1"}
    assert status["enumeracion"]["900"] == {"grupos": [["G1", "GRUPO 1"], ["G2", "GRUPO 2"]], "pendientes": {"G2": None}}
    assert status["grupos_por_leer"] == 1 and status["pending"] >= 1
    assert status["parada"] == ("tope" if tope else "freno") and status["intentos"] == {}
    assert tanda.raw() == {}                                     # ninguna acta: el corte llegó antes
    f.ip_nueva()
    tanda.run(f, "--comps", "900")
    assert all("CodGrupo=G2" in u or "NFG_CmpPartido" in u for u in f.pedidas), f.pedidas
    status = tanda.status()
    assert status["enumeracion"]["900"]["pendientes"] == {} and set(tanda.index()) == todas("900")
    if tope:                                                     # sin tope: todo
        assert status["pending"] == 0 and status["parada"] is None and set(tanda.raw()) == todas("900")
    else:                                                        # el cupo de la IP nueva: el grupo 2 y un acta
        assert len(tanda.raw()) == 1 and status["actas_por_leer"] == 15 and status["parada"] == "freno"


def test_una_jornada_que_viene_vacia_siempre_acaba_no_disponible(tanda):
    f = FederacionFalsa(sitio_actas(muertas=("CodCompeticion=900&CodGrupo=G1&CodJornada=3",)), Reloj())
    for n in (1, 2, 3):
        f.ip_nueva()
        tanda.run(f, "--comps", "900,901")
        status = tanda.status()
        if n < 3:
            assert status["intentos"] == {"jornada:900:G1:3": n} and status["no_disponible"] == []
            assert status["jornadas_por_leer"] == 1 and status["pending"] == 1
            assert status["enumeracion"]["900"]["pendientes"] == {"G1": ["3"]}
    assert "jornada:900:G1:3" in status["no_disponible"] and status["pending"] == 0 and status["intentos"] == {}
    assert status["enumeracion"]["900"]["pendientes"] == {} and status["parada"] is None
    assert set(tanda.raw()) == (todas("900") - set(actas_de("900", "G1", 3))) | todas("901")
    f.ip_nueva()
    tanda.run(f, "--comps", "900,901")
    assert f.pedidas == []


def test_las_actas_van_en_el_orden_de_las_competiciones_con_un_navegador(tanda):
    f = FederacionFalsa(sitio_actas(), Reloj())
    tanda.run(f, "--comps", "901,900")
    actas = [re.search(r"CodActa=(\d+)", u).group(1) for u in f.pedidas if "NFG_CmpPartido" in u]
    assert sorted(actas) == sorted(todas("900") | todas("901"))
    ultima_901 = max(i for i, c in enumerate(actas) if c.startswith("901"))
    primera_900 = min(i for i, c in enumerate(actas) if c.startswith("900"))
    assert ultima_901 < primera_900
    # La competición 900 se enumera después de leer las actas de la 901.
    primera_900_enum = min(i for i, u in enumerate(f.pedidas) if "CodCompeticion=900" in u)
    assert max(i for i, u in enumerate(f.pedidas) if "CodActa=901" in u) < primera_900_enum
    assert tanda.launches == 1 and tanda.pages == 1


def test_un_acta_frenada_no_se_guarda_y_queda_pendiente(tanda):
    # La competición, sus dos calendarios y sus ocho jornadas (11 páginas), dos actas y el freno.
    f = FederacionFalsa(sitio_actas(), Reloj(), cupo=13, bloqueos=(None,))
    tanda.run(f, "--comps", "900")
    status, raw = tanda.status(), tanda.raw()
    assert len(raw) == 2 and status["parada"] == "freno" and status["intentos"] == {}
    assert status["actas_por_leer"] == 14 and status["pending"] == 14 and status["fetched"] == 2
    assert status["enumeracion"]["900"]["pendientes"] == {}


def test_un_acta_muerta_gasta_un_intento_y_se_siguen_leyendo_las_demas(tanda):
    """Seis actas (los tres primeros grupos de jornadas de la 900, con --max-actas 6): una, vacía siempre."""
    muerta = actas_de("900", "G1", 2)[0]
    f = FederacionFalsa(sitio_actas(muertas=(f"CodActa={muerta}&",)), Reloj())
    tanda.run(f, "--comps", "900", "--max-actas", "6")
    status, raw = tanda.status(), tanda.raw()
    assert len(raw) == 5 and muerta not in raw and status["intentos"] == {f"acta:{muerta}": 1}
    assert status["parada"] is None and status["no_disponible"] == []
    # Tres ejecuciones: no disponible, fuera de lo pendiente.
    for _ in range(2):
        f.ip_nueva()
        tanda.run(f, "--comps", "900")
    status = tanda.status()
    assert f"acta:{muerta}" in status["no_disponible"] and status["pending"] == 0 and len(tanda.raw()) == 15


def test_una_tanda_que_empieza_por_un_acta_muerta_no_la_toma_por_el_freno(tanda):
    """Con la competición ya enumerada, la primera petición de la tanda es un acta, cuya URL no lleva la
    temporada: sin otra página servida, una vacía no se podría distinguir del freno y cada tanda acabaría ahí.
    Antes, la de competiciones de la temporada (fiflp_carga.preparar): la muerta gasta su intento y se siguen
    leyendo las demás."""
    muerta = actas_de("900", "G1", 1)[0]
    f = FederacionFalsa(sitio_actas(muertas=(f"CodActa={muerta}&",)), Reloj())
    tanda.run(f, "--comps", "900", "--max-actas", "1")           # enumera y pide solo la muerta
    assert tanda.status()["intentos"] == {f"acta:{muerta}": 1}
    f.ip_nueva()
    tanda.run(f, "--comps", "900")
    catalogo = f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21"
    assert f.pedidas[:2] == [catalogo, f"{BASE}/NFG_CmpPartido?cod_primaria=1000120&CodActa={muerta}&cod_acta={muerta}"]
    status = tanda.status()
    assert status["intentos"] == {f"acta:{muerta}": 2} and status["parada"] is None and len(tanda.raw()) == 15


def test_un_acta_que_carga_vacia_gasta_un_intento(tanda, monkeypatch):
    """Una página de acta que carga pero sin nada (is_empty_acta): no se guarda y suma un intento."""
    f = FederacionFalsa(lambda url: Pagina(html="<html><body><p>nada</p></body></html>")
                        if "CodActa=900111&" in url else sitio_actas()(url), Reloj())
    tanda.run(f, "--comps", "900")
    status = tanda.status()
    assert "900111" not in tanda.raw() and status["intentos"] == {"acta:900111": 1} and status["actas_por_leer"] == 1


def test_un_runner_rechazado_no_toca_el_estado(tanda):
    f = FederacionFalsa(sitio_actas(), Reloj(), cupo=13, bloqueos=(None,))
    tanda.run(f, "--comps", "900")
    antes = tanda.index(), tanda.raw(), tanda.status()
    aws = FederacionFalsa(sitio_actas(), Reloj(), nube="aws", rechaza=True)
    tanda.run(aws, "--comps", "900")
    status = tanda.status()
    assert (tanda.index(), tanda.raw()) == antes[:2] and status["intentos"] == antes[2]["intentos"]
    assert status["no_disponible"] == antes[2]["no_disponible"] and status["enumeracion"] == antes[2]["enumeracion"]
    assert status["parada"] == "runner" and status["pending"] == antes[2]["pending"] and len(aws.pedidas) <= 2
    assert A.chain_state("21")["stuck"] == 1                    # la cadena vieja no se relanza contra él


def test_el_estado_nuevo_lleva_todas_sus_claves(tanda, tmp_path):
    f = FederacionFalsa(sitio_actas(muertas=("CodGrupo=G2&CodJornada=4",)), Reloj())
    resumen = tmp_path / "resumen.json"
    tanda.run(f, "--comps", "900", "--resumen", str(resumen), "--max-paginas", "500")
    status = tanda.status()
    assert set(status) == {"formato", "season", "enumerated", "in_raw", "fetched", "pending", "actas_por_leer",
                           "jornadas_por_leer", "grupos_por_leer", "unenumerated_comps", "no_disponible",
                           "intentos", "motivos", "enumeracion", "paginas", "parada"}
    assert status["formato"] == 2 and status["season"] == "2025-2026"
    assert (status["enumerated"], status["in_raw"], status["fetched"]) == (14, 14, 14)
    assert (status["actas_por_leer"], status["jornadas_por_leer"], status["grupos_por_leer"],
            status["unenumerated_comps"], status["pending"]) == (0, 1, 0, 0, 1)
    assert status["intentos"] == {"jornada:900:G2:4": 1} and status["paginas"]["servidas"] > 0
    assert status["paginas"]["pedidas"] >= status["paginas"]["servidas"]
    data = json.loads(resumen.read_text())
    assert data["partes"] == {"actas:2025-2026:siempre": {"completo": False, "pendientes": 1, "no_disponible": 0}}
    assert data["muertas"] == 1


def test_las_competiciones_sin_enumerar_cuentan_como_pendientes(tanda):
    """Un corte en la primera competición: la segunda ni se pidió y está en unenumerated_comps."""
    f = FederacionFalsa(sitio_actas(), Reloj(), cupo=0, bloqueos=(None,))
    tanda.run(f, "--comps", "900,901")
    status = tanda.status()
    assert status["unenumerated_comps"] == 2 and status["pending"] == 2 and status["parada"] == "freno"
    assert status["enumeracion"] == {"900": {"grupos": None, "pendientes": {}},
                                     "901": {"grupos": None, "pendientes": {}}}


def test_un_estado_antiguo_da_por_enumeradas_las_competiciones_del_indice(tanda):
    """Con un estado sin `formato` (los de hoy), una competición que ya está en el índice no se vuelve a
    enumerar (como hasta ahora); con --reindex, sí."""
    (tanda.dir / "fiflp_actas_2025-2026_index.json").write_text(json.dumps(
        {"900111": {"comp_id": "900", "grupo": "G1", "jornada": "1"}}), encoding="utf-8")
    (tanda.dir / "fiflp_actas_2025-2026_status.json").write_text(json.dumps(
        {"season": "2025-2026", "enumerated": 1, "in_raw": 0, "pending": 1, "unenumerated_comps": 0, "fetched": 0}),
        encoding="utf-8")
    f = FederacionFalsa(sitio_actas(), Reloj())
    tanda.run(f, "--comps", "900")
    # Ni la competición ni sus grupos: solo la página de la temporada (fiflp_carga.preparar) y el acta.
    assert [u for u in f.pedidas if "NFG_CmpPartido" not in u] == [f"{BASE}/NFG_CmpJornada?cod_primaria=1000120"
                                                                    "&CodTemporada=21"]
    assert set(tanda.raw()) == {"900111"}
    status = tanda.status()
    assert status["formato"] == 2 and status["enumeracion"]["900"]["pendientes"] == {}
    tanda.run(f, "--comps", "900", "--reindex")
    assert set(tanda.index()) == todas("900")


def test_un_corte_en_cualquier_peticion_no_deja_nada_mal_leido(tanda):
    """La pregunta de la parte G para las actas: si la federación deja de servir en CUALQUIER petición (la de
    una competición, la de un grupo, cada jornada, cada acta), ¿qué queda escrito y qué pide la siguiente? Para
    cada corte k (el freno de verdad tras k páginas): ni un intento gastado ni nada no disponible, en el raw
    solo actas leídas enteras, lo pendiente sin cero, y la tanda siguiente, sin freno, deja lo mismo (índice,
    raw y estado de la enumeración) que una tanda entera sin cortes."""
    def foto():
        status = tanda.status()
        return (tanda.index(), {c: {k: v for k, v in a.items()} for c, a in tanda.raw().items()},
                status["enumeracion"], status["pending"], status["intentos"], status["no_disponible"])
    f = FederacionFalsa(sitio_actas(), Reloj())
    tanda.run(f, "--comps", "900")
    entera, total = foto(), len(f.pedidas)
    assert total == 1 + 2 * (1 + 4) + 16 and entera[3] == 0
    for k in range(total):
        for p in tanda.dir.glob("fiflp_actas_*.json"):
            p.unlink()
        f = FederacionFalsa(sitio_actas(), Reloj(), cupo=k, bloqueos=(None,))
        tanda.run(f, "--comps", "900")
        status = tanda.status()
        assert status["parada"] == "freno" and status["intentos"] == {} and status["no_disponible"] == [], k
        assert status["pending"] > 0 and all(a["header"]["home_team"] for a in tanda.raw().values()), k
        assert set(tanda.raw()) <= set(tanda.index()), k
        tanda.run(FederacionFalsa(sitio_actas(), Reloj()), "--comps", "900")
        assert foto() == entera, k


def test_con_la_espera_del_carril_un_freno_no_deja_nada_mal_leido(tanda, tmp_path):
    """Como la de arriba, con la Federacion del carril (para_tanda: espera UN freno por ejecución, desde el
    26/11/2026). Para cada cupo k, el freno tras k páginas, un bloqueo de 5 min y el segundo sin final: la tanda
    espera el primero, sigue leyendo donde frenó y acaba en el segundo. Nada vacío queda leído, ni un intento
    gastado; lo leído antes y después de la espera está en el raw; el resumen dice la espera y si volvió; y la
    tanda siguiente, sin freno, deja lo mismo que una entera sin cortes."""
    def foto():
        status = tanda.status()
        return (tanda.index(), tanda.raw(), status["enumeracion"], status["pending"], status["intentos"],
                status["no_disponible"])
    f = FederacionFalsa(sitio_actas(), Reloj())
    tanda.run(f, "--comps", "900")
    entera, total = foto(), len(f.pedidas)
    resumen = tmp_path / "resumen.json"
    for k in range(1, total // 2):
        for p in tanda.dir.glob("fiflp_actas_*.json"):
            p.unlink()
        f = FederacionFalsa(sitio_actas(), Reloj(), cupo=k, bloqueos=(300, None))
        tanda.run(f, "--comps", "900", "--resumen", str(resumen), como_el_carril=True)
        status, data = tanda.status(), json.loads(resumen.read_text())
        assert status["parada"] == "freno" and status["intentos"] == {} and status["no_disponible"] == [], k
        assert data["esperas"] == 1 and data["esperas_sirvio"] == [True] and data["esperas_s"] == [300], k
        assert data["frenos_tras"] == [k, k] and data["servidas"] == 2 * k, k
        assert status["pending"] > 0 and all(a["header"]["home_team"] for a in tanda.raw().values()), k
        assert set(tanda.raw()) <= set(tanda.index()), k
        # Lo leído en los dos tramos (sin la de competiciones de preparar, ni las que no son actas) está guardado.
        actas = {u.split("CodActa=")[1].split("&")[0] for u in f.pedidas if "NFG_CmpPartido" in u}
        assert set(tanda.raw()) <= actas, k
        tanda.run(FederacionFalsa(sitio_actas(), Reloj()), "--comps", "900")
        assert foto() == entera, k


def test_las_competiciones_de_la_web_sin_parada_y_con_ella(tanda, monkeypatch):
    """Una temporada que el catálogo no tiene (aquí, 2016-17 con el catálogo vacío): las competiciones, del
    desplegable de la web por la Federacion de la tanda (discover_comps con F). Si la federación no la sirve
    (un runner rechazado), no se escribe nada: ni índice, ni raw, ni estado."""
    monkeypatch.setattr(A, "_catalog_entry", lambda season, catalog=None: {})
    aws = FederacionFalsa(sitio_actas(), Reloj(), nube="aws", rechaza=True)
    resumen = tanda.dir / "resumen.json"
    tanda.run(aws, "--temporada", "12", "--resumen", str(resumen))
    assert not list(tanda.dir.glob("fiflp_actas_*")) and len(aws.pedidas) <= 2
    # Pero sí el resumen: el carril apunta las páginas y la parada (M7 de la revisión final).
    assert json.loads(resumen.read_text())["parada"] == "runner"
    f = FederacionFalsa(sitio_actas(), Reloj())
    tanda.run(f, "--temporada", "12")
    assert f.pedidas[0] == f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=12"
    status = json.loads((tanda.dir / "fiflp_actas_2016-2017_status.json").read_text(encoding="utf-8"))
    assert set(status["enumeracion"]) == {"900", "901"} and status["pending"] == 0


ROMPE = "<html><body>ROMPE</body></html>"


def test_un_acta_que_no_se_entiende_gasta_un_intento_como_una_muerta(tanda, monkeypatch):
    """I3 de la revisión final: dos actas que cargan pero cuyo contenido hace lanzar al intérprete (una dentro del
    lector, otra después, al mirar lo que dio). Antes, la segunda se saltaba sin apuntar nada: pendiente para
    siempre y la ejecución en verde. Ahora cada una gasta un intento como una muerta, las demás se leen y, con
    tres, «no disponible» con el tipo de la excepción (nunca su texto: puede llevar un nombre)."""
    real = A.parse_acta
    rotas = {"900111": "<html><body>ROMPE uno</body></html>", "900112": "<html><body>ROMPE dos</body></html>"}

    def interprete(html):
        if "ROMPE uno" in html:
            raise ValueError("Nombre Inventado")
        if "ROMPE dos" in html:
            return []                                          # no es un acta: falla al mirarla
        return real(html)
    monkeypatch.setattr(A, "parse_acta", interprete)
    sitio = sitio_actas()

    def web(url):
        cod = re.search(r"CodActa=(\d+)&", url)
        return Pagina(html=rotas[cod.group(1)]) if cod and cod.group(1) in rotas else sitio(url)
    f = FederacionFalsa(web, Reloj())
    for n in (1, 2, 3):
        f.ip_nueva()
        tanda.run(f, "--comps", "900")
        status = tanda.status()
        assert status["parada"] is None and len(tanda.raw()) == 14
        if n < 3:
            assert status["intentos"] == {"acta:900111": n, "acta:900112": n} and status["pending"] == 2
    assert {"acta:900111", "acta:900112"} <= set(status["no_disponible"]) and status["pending"] == 0
    assert status["motivos"] == {"acta:900111": "ValueError", "acta:900112": "AttributeError"}
    assert "Inventado" not in (tanda.dir / "fiflp_actas_2025-2026_status.json").read_text(encoding="utf-8")


def test_una_jornada_que_no_se_entiende_gasta_un_intento_como_una_muerta(tanda, monkeypatch):
    """Lo mismo en la enumeración: una jornada cuyo contenido hace lanzar al lector de sus enlaces. Antes la
    ejecución acababa con error en ella cada vez."""
    class Enlaces:
        def finditer(self, html):
            if "ROMPE" in html:
                raise RuntimeError("Nombre Inventado")
            return A.re.compile(r"NFG_CmpPartido[^\"'\s]*CodActa=(\d+)", A.re.IGNORECASE).finditer(html)
    monkeypatch.setattr(A, "ACTA_HREF", Enlaces())
    sitio = sitio_actas()
    f = FederacionFalsa(lambda url: Pagina(html=ROMPE) if url.endswith("CodCompeticion=900&CodGrupo=G1&CodJornada=3")
                        else sitio(url), Reloj())
    for n in (1, 2, 3):
        f.ip_nueva()
        tanda.run(f, "--comps", "900")
        status = tanda.status()
        assert status["parada"] is None
        if n < 3:
            assert status["intentos"] == {"jornada:900:G1:3": n} and status["jornadas_por_leer"] == 1
    assert "jornada:900:G1:3" in status["no_disponible"] and status["pending"] == 0
    assert status["motivos"] == {"jornada:900:G1:3": "RuntimeError"}
    assert set(tanda.raw()) == todas("900") - set(actas_de("900", "G1", 3))


# ── main, con un Playwright de mentira y la federación de mentira ──

@pytest.fixture
def tanda(tmp_path, monkeypatch):
    """main sin red: un Playwright de mentira cuya página es la de una FederacionFalsa (run(f, *argv)), los
    ficheros en tmp_path. Cuenta los navegadores y las páginas que abre."""
    state = types.SimpleNamespace(dir=tmp_path, launches=0, pages=0, f=None, kw={})

    class Browser:
        def new_context(self, **kw):
            return self

        def new_page(self):
            state.pages += 1
            return state.f.page()

        def close(self):
            pass

    class Playwright:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        @property
        def chromium(self):
            def launch(**kw):
                state.launches += 1
                return Browser()
            return types.SimpleNamespace(launch=launch)

    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: Playwright()
    pkg = types.ModuleType("playwright")
    pkg.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.setattr(A, "HERE", tmp_path)
    def federacion(minutos, max_paginas):
        tope = state.kw.get("max_pages", max_paginas or None)
        if state.kw.get("como_el_carril"):
            # La de verdad (fiflp_carga.para_tanda), con sus esperas del freno: una por ejecución desde el 26/11/2026.
            return state.f.tanda(minutos, tope)
        return state.f.fed(deadline=state.f.reloj.t + minutos * 60, max_pauses=0, max_pages=tope)
    monkeypatch.setattr(A, "federacion", federacion)

    def run(f, *argv, **kw):
        state.f, state.kw, state.launches, state.pages = f, kw, 0, 0
        f.pedidas.clear()
        monkeypatch.setattr(sys, "argv", ["fetch_fiflp_actas.py", "--temporada", "21", *argv])
        A.main()

    def load(kind):
        p = tmp_path / f"fiflp_actas_2025-2026_{kind}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    state.run = run
    state.index, state.raw, state.status = (lambda: load("index")), (lambda: load("raw")), (lambda: load("status"))
    return state
