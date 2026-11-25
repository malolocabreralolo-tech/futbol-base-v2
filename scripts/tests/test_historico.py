"""El carril del histórico (historico.py): qué toca en cada ejecución, el estado que deja y la orden que da a
cada descargador. Sin red ni navegador: relojes fijos (--now) y una carpeta temporal (HISTORICO_CARPETA); el
descargador de verdad no se ejecuta nunca (subprocess.run, cambiado)."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import historico as H  # noqa: E402

# El catálogo congelado, no el que cambia discover-fiflp.yml: estas pruebas corren en el bot antes de publicar.
CATALOGO = json.loads((ROOT / "scripts" / "tests" / "fixtures" / "fiflp_comps_catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _catalogo_congelado(monkeypatch):
    monkeypatch.setattr(H, "CATALOGO", CATALOGO)


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
    # La variable del repositorio sin poner llega vacía: el tope de siempre.
    assert H.cupo_hoy(e, MIERCOLES, env={"HISTORICO_PAGINAS_DIA": ""}) == 1660
    assert H.cupo_hoy(e, MIERCOLES, env={"HISTORICO_PAGINAS_DIA": "tres mil"}) == 1660


def test_orden_competiciones():
    comps = [("1", "CLAUSURA ALEVÍN"), ("2", "LIGA ALEVIN GRAN CANARIA FASE PREVIA"),
             ("3", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA A"), ("4", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA C"),
             ("5", "LIGA ALEVIN F7 GRAN CANARIA FASE LIGA B"), ("6", "COPA CAMPEONES ALEVÍN")]
    assert H.orden_competiciones(comps) == ["3", "5", "4", "2", "1", "6"]
    assert H.orden_competiciones([("8", "LIGA PRIMERA ALEVIN F-8 GRAN CANARIA"),
                                  ("7", "LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA")]) == ["7", "8"]
    assert H.rango_competicion("LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA") == 0
    assert H.rango_competicion("LIGA ALEVIN GRAN CANARIA FASE A") == 1
    assert H.rango_competicion("LIGA ALEVIN F8 GRAN CANARIA SEGUNDA FASE E") == 5
    assert H.rango_competicion("copa de campeones categoria alevin fase c") == 40


def test_primero_los_goleadores_de_todas_las_temporadas():
    a = H.siguiente(PLAN, H.estado_vacio(), MIERCOLES, env={})
    assert (a["accion"], a["trabajo"], a["temporadas"], a["categorias"]) == ("descargar", "goleadores", ["21", "20"], ["alevin"])
    assert a["paginas"] == 2000 and a["hasta"] == "2026-11-25T15:00:00+00:00" and a["dia"] == "2026-11-25"
    assert a["partes"] == ["goleadores:2025-2026", "goleadores:2024-2025"]
    assert a["minutos"] == 300 and a["inicio"] == "2026-11-25T10:00:00+00:00" and a["lote"] is None


def test_despues_las_actas_de_la_mas_reciente():
    e = H.estado_vacio()
    for k in ("goleadores:2025-2026", "goleadores:2024-2025"):
        e["trabajos"][k] = {"estado": "promovido", "pendientes": 0, "no_disponible": 0}
    a = H.siguiente(PLAN, e, MIERCOLES, env={})
    assert (a["trabajo"], a["temporadas"], a["lote"]) == ("actas", ["21"], "alevin")
    assert a["partes"] == ["actas:2025-2026:alevin"] and a["comps"][0] != a["comps"][-1]
    # Todas las del lote (lo pendiente de las actas cuenta solo las de la tanda), de más nivel a menos.
    assert a["comps"] == ["54422939", "54422940", "54422941", "54422881", "54976639", "54965212"]
    assert a["categorias"] == ["alevin"]


def test_lo_completo_se_prueba_antes_de_seguir_bajando():
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "completo", "pendientes": 0, "no_disponible": 1}
    assert H.siguiente(PLAN, e, MIERCOLES, env={}) == {"accion": "probar", "trabajos": ["goleadores:2025-2026"]}
    # A 40 min de una ventana no se prueba (la importación del bot caería en ella): se sigue bajando otra cosa.
    a = H.siguiente(PLAN, e, T("2026-11-27T17:00:00Z"), env={})
    assert a["accion"] == "descargar" and a["temporadas"] == ["20"]


def test_se_prueba_una_temporada_cada_vez_con_los_campos():
    plan = {**PLAN, "trabajos": ["goleadores", "detalle"]}
    e = H.estado_vacio()
    for k in ("goleadores:2024-2025", "detalle:2024-2025", "campos", "goleadores:2025-2026"):
        e["trabajos"][k] = {"estado": "completo", "pendientes": 0, "no_disponible": 0}
    assert H.siguiente(plan, e, MIERCOLES, env={}) == {"accion": "probar",
                                                       "trabajos": ["goleadores:2025-2026", "campos"]}
    e["trabajos"]["goleadores:2025-2026"]["estado"] = "promovido"
    assert H.siguiente(plan, e, MIERCOLES, env={})["trabajos"] == ["goleadores:2024-2025", "detalle:2024-2025",
                                                                   "campos"]


def test_una_prueba_en_rojo_no_se_repite_sola():
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "fallo", "pendientes": 0, "no_disponible": 0}
    e["pruebas"] = [{"at": "2026-11-25T08:00:00+00:00", "trabajos": ["goleadores:2025-2026"], "verde": False,
                     "motivo": "las pruebas fallaron"}]
    assert H.siguiente(PLAN, e, MIERCOLES, env={})["temporadas"] == ["20"]
    plan = {**PLAN, "reintentar_desde": "2026-11-25T09:30:00+00:00"}
    assert H.siguiente(plan, e, MIERCOLES, env={})["accion"] == "probar"
    # Una ejecución que vuelve a ver el fallo entero (nada nuevo que bajar) no lo pasa a «completo».
    accion = {"accion": "descargar", "trabajo": "goleadores", "temporadas": ["21", "20"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": ["goleadores:2024-2025"]}
    resumen = {"pedidas": 70, "servidas": 70, "muertas": 0, "esperas": 0, "frenos": 0, "frenos_tras": [],
               "parada": None, "nube": "azure", "runner_rechazado": False,
               "partes": {"goleadores:2025-2026": {"completo": True, "pendientes": 0, "no_disponible": 0}}}
    assert H.registrar(e, accion, resumen, MIERCOLES)["trabajos"]["goleadores:2025-2026"]["estado"] == "fallo"


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


def test_los_trabajos_del_plan():
    plan = {**PLAN, "categorias": ["benjamin", "prebenjamin", "alevin"], "trabajos": list(H.TRABAJOS),
            "calendario": ["20"]}
    assert H.trabajos_del_plan(plan) == [
        "goleadores:2025-2026", "goleadores:2024-2025",
        "actas:2025-2026:siempre", "actas:2025-2026:alevin", "actas:2024-2025:siempre", "actas:2024-2025:alevin",
        "detalle:2025-2026", "detalle:2024-2025", "campos",
        "calendario:2024-2025",
        "escudos:2025-2026", "escudos:2024-2025"]
    assert H.trabajo("goleadores", "21") == "goleadores:2025-2026"
    assert H.trabajo("actas", "20", "alevin") == "actas:2024-2025:alevin"
    assert H.trabajo("actas", "20", "") == "actas:2024-2025:siempre"


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


def test_un_runner_rechazado_no_gasta_el_dia_ni_toca_los_trabajos():
    e = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 340, "freno": None}}
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "pendiente", "pendientes": 40, "no_disponible": 0}
    accion = {"accion": "descargar", "trabajo": "goleadores", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": ["goleadores:2025-2026"], "paginas": 1660}
    resumen = {"pedidas": 2, "servidas": 0, "muertas": 0, "esperas": 0, "frenos": 1, "frenos_tras": [0],
               "parada": "runner", "nube": "aws", "runner_rechazado": True,
               "partes": {"goleadores:2025-2026": {"completo": False, "pendientes": 40, "no_disponible": 0}}}
    despues = H.registrar(e, accion, resumen, T("2026-11-25T10:02:00Z"))
    assert despues["dia"] == {"fecha": "2026-11-25", "paginas": 340, "freno": None}
    assert despues["dias_frenados"] == [] and despues["trabajos"] == e["trabajos"]
    assert despues["ejecuciones"][-1]["runner_rechazado"] and despues["ejecuciones"][-1]["nube"] == "aws"


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


def test_un_freno_cortado_por_el_tope_tambien_para_el_dia():
    """Federacion.parada da «tope» si el tope corta la comprobación de un freno: el día se para por `frenos`."""
    accion = {"accion": "descargar", "trabajo": "actas", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": ["actas:2025-2026:alevin"]}
    resumen = {"pedidas": 2000, "servidas": 1990, "muertas": 3, "esperas": 0, "frenos": 1, "frenos_tras": [],
               "parada": "tope", "nube": "azure", "runner_rechazado": False,
               "partes": {"actas:2025-2026:alevin": {"completo": False, "pendientes": 400, "no_disponible": 0}}}
    e = H.registrar(H.estado_vacio(), accion, resumen, T("2026-11-25T14:00:00Z"))
    assert e["dia"] == {"fecha": "2026-11-25", "paginas": 2000, "freno": "carril"}
    assert e["dias_frenados"] == ["2026-11-25"]


def test_registrar_sin_resumen_y_lo_completo():
    accion = {"accion": "descargar", "trabajo": "goleadores", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": ["goleadores:2025-2026"]}
    e = H.registrar(H.estado_vacio(), accion, None, T("2026-11-25T10:05:00Z"))
    assert e["ejecuciones"][-1]["pedidas"] is None and e["trabajos"] == {} and e["dia"]["paginas"] == 0
    resumen = {"pedidas": 120, "servidas": 118, "muertas": 2, "esperas": 0, "frenos": 0, "frenos_tras": [],
               "parada": None, "nube": "azure", "runner_rechazado": False,
               "partes": {"goleadores:2025-2026": {"completo": True, "pendientes": 0, "no_disponible": 1}}}
    e = H.registrar(e, accion, resumen, T("2026-11-25T10:30:00Z"))
    assert e["trabajos"]["goleadores:2025-2026"]["estado"] == "completo"
    assert e["trabajos"]["goleadores:2025-2026"]["no_disponible"] == 1
    assert e["dia"] == {"fecha": "2026-11-25", "paginas": 120, "freno": None} and len(e["ejecuciones"]) == 2
    # Lo promovido que se vuelve a ver entero se queda promovido; con un fichero nuevo en la cuarentena, a probar.
    e["trabajos"]["goleadores:2025-2026"]["estado"] = "promovido"
    assert H.registrar(e, accion, resumen, MIERCOLES)["trabajos"]["goleadores:2025-2026"]["estado"] == "promovido"
    otra = H.registrar(e, accion, resumen, MIERCOLES, en_carpeta=lambda k: True)
    assert otra["trabajos"]["goleadores:2025-2026"]["estado"] == "completo"


def test_registrar_lo_que_vio_el_bot():
    salud = {"checkedAt": "2026-11-25T09:21:28+00:00", "run": {"pauses": 1, "cloud": "azure"}}
    accion = {"accion": "descargar", "trabajo": "goleadores", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": ["goleadores:2025-2026"]}
    resumen = {"pedidas": 10, "servidas": 10, "muertas": 0, "esperas": 0, "frenos": 0, "frenos_tras": [],
               "parada": "plazo", "nube": "azure", "runner_rechazado": False, "partes": {}}
    e = H.registrar(H.estado_vacio(), accion, resumen, T("2026-11-25T10:30:00Z"), salud=salud)
    assert e["dia"]["freno"] == "bot" and e["dias_frenados"] == ["2026-11-25"]
    assert H.apuntar_freno_del_bot(H.estado_vacio(), salud, MIERCOLES)["dia"] == {
        "fecha": "2026-11-25", "paginas": 0, "freno": "bot"}
    assert H.apuntar_freno_del_bot(H.estado_vacio(), None, MIERCOLES) is None


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
    assert not H.freno_del_bot({**salud, "run": {"cloud": "azure"}}, MIERCOLES)


def test_encargar_valida():
    p = H.encargar(None, "21,20", "alevín", "goleadores,actas", "", MIERCOLES)
    assert p == {**PLAN, "encargado": "2026-11-25T10:00:00+00:00"}
    for mal in (("23", "alevin", "actas", ""), ("21", "infantil", "actas", ""), ("21", "alevin", "fotos", ""),
                ("22", "alevin", "goleadores", ""), ("21", "alevin", "detalle", "20"), ("", "alevin", "actas", ""),
                ("21", "alevin", "", ""), ("21", "alevin", "calendario", "")):
        with pytest.raises(ValueError):
            H.encargar(None, *mal, MIERCOLES)
    assert H.encargar(None, "21", "benjamin", "actas", "", MIERCOLES)["categorias"] == ["benjamin", "prebenjamin"]
    assert H.encargar(None, "22", "alevin", "actas,detalle", "", MIERCOLES)["trabajos"] == ["actas", "detalle"]
    p = H.encargar(None, "14,13", "benjamin,prebenjamin", "detalle", "13", MIERCOLES)
    assert p["calendario"] == ["13"] and p["trabajos"] == ["detalle"]


def test_argumentos_de_cada_trabajo():
    base = {"accion": "descargar", "temporadas": ["21", "20"], "categorias": ["alevin"], "lote": None, "comps": [],
            "minutos": 299.7, "paginas": 1660}
    cola = ["--carpeta", "scripts/historico", "--max-minutes", "299", "--max-paginas", "1660", "--resumen", "R.json"]
    assert H.argumentos({**base, "trabajo": "goleadores"}, "R.json") == [
        "scripts/fetch_fiflp_goleadores.py", "--temporadas", "21,20", "--categorias", "alevin", "--sin-escudos"] + cola
    assert H.argumentos({**base, "trabajo": "escudos"}, "R.json") == [
        "scripts/fetch_fiflp_goleadores.py", "--temporadas", "21,20", "--categorias", "alevin", "--escudos"] + cola
    assert H.argumentos({**base, "trabajo": "detalle"}, "R.json") == [
        "scripts/fetch_fiflp_detalle.py", "--temporadas", "21,20", "--categorias", "alevin", "--jornadas", ""] + cola
    assert H.argumentos({**base, "trabajo": "calendario", "temporadas": ["14", "13"],
                         "categorias": ["benjamin", "prebenjamin"]}, "R.json") == [
        "scripts/fetch_fiflp_detalle.py", "--temporadas", "14,13", "--categorias", "benjamin,prebenjamin",
        "--jornadas", "14,13", "--sin-campos"] + cola
    assert H.argumentos({**base, "trabajo": "actas", "temporadas": ["21"], "lote": "alevin",
                         "comps": ["54422939", "54422881"]}, "R.json") == [
        "scripts/fetch_fiflp_actas.py", "--temporada", "21", "--categorias", "alevin", "--lote", "alevin",
        "--comps", "54422939,54422881"] + cola
    assert H.argumentos({**base, "trabajo": "actas", "temporadas": ["20"], "lote": "siempre",
                         "categorias": ["benjamin", "prebenjamin"], "comps": ["1"]}, "R.json")[1:9] == [
        "--temporada", "20", "--categorias", "benjamin,prebenjamin", "--lote", "siempre", "--comps", "1"]


def test_la_orden_de_las_actas_la_aceptan_las_actas(monkeypatch):
    """Las actas de un lote que no es el de siempre necesitan sus categorías: sin ellas, la tanda para."""
    import fetch_fiflp_actas as A
    a = {"accion": "descargar", "trabajo": "actas", "temporadas": ["21"], "lote": "alevin", "categorias": ["alevin"],
         "comps": ["54422939", "54422881"], "minutos": 100, "paginas": 10}
    args = H.argumentos(a, "R.json")
    monkeypatch.setattr(sys, "argv", args)
    parsed = A.parse_args()
    cats = A._categorias().parse_categories(parsed.categorias)
    nombres = {c["id"]: c["name"] for c in CATALOGO["2025-2026"]["all"]}
    assert A.tanda_lote(parsed.temporada, cats, parsed.comps.split(","), names=nombres,
                        expected=A.LOTE_ARG[parsed.lote]) == "alevin"
    assert parsed.max_minutes == 100 and parsed.max_paginas == 10 and parsed.carpeta == "scripts/historico"


def test_registrar_prueba():
    e = H.estado_vacio()
    e["trabajos"]["goleadores:2025-2026"] = {"estado": "completo", "pendientes": 0, "no_disponible": 0}
    e["trabajos"]["campos"] = {"estado": "completo", "pendientes": 0, "no_disponible": 0}
    verde = {"verde": True, "motivo": "", "mb_antes": 41.2, "mb_despues": 43.0, "segundos": 95}
    v = H.registrar_prueba(e, ["goleadores:2025-2026", "campos"], verde, MIERCOLES)
    assert v["trabajos"]["goleadores:2025-2026"]["estado"] == "promovido" and v["trabajos"]["campos"]["estado"] == "promovido"
    assert v["pruebas"][-1] == {"at": "2026-11-25T10:00:00+00:00", "trabajos": ["goleadores:2025-2026", "campos"],
                                "verde": True, "motivo": "", "mb_antes": 41.2, "mb_despues": 43.0, "segundos": 95}
    rojo = {"verde": False, "motivo": "las pruebas fallaron", "mb_antes": 41.2, "mb_despues": 43.0, "segundos": 95}
    r = H.registrar_prueba(e, ["goleadores:2025-2026"], rojo, MIERCOLES)
    assert r["trabajos"]["goleadores:2025-2026"]["estado"] == "fallo"
    assert r["pruebas"][-1]["motivo"] == "las pruebas fallaron" and not r["pruebas"][-1]["verde"]
    assert e["trabajos"]["goleadores:2025-2026"]["estado"] == "completo"             # sin tocar el de antes


def test_los_registros_no_crecen_sin_tope():
    e = H.estado_vacio()
    accion = {"accion": "descargar", "trabajo": "goleadores", "temporadas": ["21"], "dia": "2026-11-25",
              "inicio": "2026-11-25T10:00:00+00:00", "partes": []}
    for _ in range(105):
        e = H.registrar(e, accion, None, MIERCOLES)
    for _ in range(55):
        e = H.registrar_prueba(e, [], {"verde": False, "motivo": "x"}, MIERCOLES)
    assert len(e["ejecuciones"]) == 100 and len(e["pruebas"]) == 50


def _estado_de_ejemplo():
    e = {**H.estado_vacio(), "dia": {"fecha": "2026-11-25", "paginas": 340, "freno": None}}
    e["trabajos"] = {
        "goleadores:2025-2026": {"estado": "promovido", "pendientes": 0, "no_disponible": 0},
        "actas:2025-2026:alevin": {"estado": "pendiente", "pendientes": 1204, "no_disponible": 0},
        "actas:2023-2024:alevin": {"estado": "fallo", "pendientes": 0, "no_disponible": 0},
    }
    e["pruebas"] = [
        {"at": "2026-11-25T10:40:00+00:00", "trabajos": ["goleadores:2025-2026"], "verde": True, "motivo": "",
         "mb_antes": 41.2, "mb_despues": 43.0, "segundos": 95},
        {"at": "2026-11-24T10:40:00+00:00", "trabajos": ["actas:2023-2024:alevin"], "verde": False,
         "motivo": "las pruebas fallaron", "mb_antes": 41.2, "mb_despues": 44.0, "segundos": 120}]
    e["ejecuciones"] = [{"inicio": "2026-11-25T12:10:00+00:00", "fin": "2026-11-25T16:12:00+00:00",
                         "accion": "descargar", "trabajo": "actas", "temporadas": ["21"], "lote": "alevin",
                         "paginas": 2000, "pedidas": 2000, "servidas": 1985, "muertas": 2, "esperas": 0, "frenos": 0,
                         "frenos_tras": [], "parada": "tope", "nube": "azure", "runner_rechazado": False,
                         "relanzada": False}]
    return e


def test_estado_legible():
    plan = {**PLAN, "temporadas": ["21", "20", "19"]}
    texto = H.estado_legible(plan, _estado_de_ejemplo(), T("2026-11-25T17:00:00Z"))
    for frase in ("Encargo del 25/11/2026: alevín; 2025-26, 2024-25, 2023-24; goleadores, actas.",
                  "Hoy (25/11/2026): 340 de 2.000 páginas.",
                  "2025-26 · goleadores: en la base (probado el 25/11 a las 10:40: de 41,2 a 43,0 MB, 95 s).",
                  "2025-26 · actas alevín: bajando (quedan 1.204; 0 no disponibles).",
                  "2024-25 · goleadores: pendiente.",
                  "2023-24 · actas alevín: la prueba falló (las pruebas fallaron); no se reintenta sola.",
                  "Última ejecución: 25/11 de 12:10 a 16:12, actas 2025-26 alevín, 1.985 de 2.000 páginas servidas "
                  "(2 muertas), tope del día."):
        assert frase in texto, (frase, texto)
    e = _estado_de_ejemplo()
    e["dia"]["freno"] = "bot"
    assert "Hoy (25/11/2026): parado por el freno de verdad (lo vio el bot en vivo)." in H.estado_legible(
        plan, e, T("2026-11-25T17:00:00Z"))
    e["ejecuciones"].append({"inicio": "2026-11-25T18:47:00+00:00", "fin": "2026-11-25T18:48:00+00:00",
                             "accion": "descargar", "trabajo": "actas", "temporadas": ["21"], "lote": "alevin",
                             "paginas": 2000, "pedidas": 1, "servidas": 0, "muertas": 0, "esperas": 0, "frenos": 1,
                             "frenos_tras": [0], "parada": "runner", "nube": "aws", "runner_rechazado": True,
                             "relanzada": False})
    texto = H.estado_legible(plan, e, T("2026-11-25T19:00:00Z"))
    linea = ("Última ejecución: 25/11 a las 18:47, runner rechazado (nube: aws), sin leer nada; se retoma en el "
             "próximo disparo (cada 3 h).")
    assert linea in texto
    assert H.linea(e) == linea.removeprefix("Última ejecución: ")
    assert H.estado_legible(None, H.estado_vacio(), MIERCOLES).startswith("Sin encargo.")


def _main(args, tmp_path, monkeypatch, now="2026-11-25T10:00:00Z"):
    salida = tmp_path / "salida"
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))
    antes = salida.read_text() if salida.exists() else ""
    code = H.main(args + ["--now", now])
    return code, salida.read_text()[len(antes):] if salida.exists() else ""


def test_la_orden_lee_y_escribe_en_su_carpeta(tmp_path, monkeypatch):
    del_repo = ROOT / "scripts" / "historico"
    habia = sorted(p.name for p in del_repo.iterdir()) if del_repo.is_dir() else None
    carpeta = tmp_path / "historico"
    monkeypatch.setenv("HISTORICO_CARPETA", str(carpeta))
    monkeypatch.setenv("HISTORICO_PAGINAS_DIA", "")
    salud = tmp_path / "salud.json"
    salud.write_text(json.dumps({"checkedAt": "2026-11-25T09:00:00+00:00", "run": {"pauses": 0, "cloud": "azure"}}))
    code, _ = _main(["encargar", "--temporadas", "21", "--categorias", "alevin", "--trabajos", "goleadores,actas",
                     "--calendario", ""], tmp_path, monkeypatch)
    assert code == 0 and json.loads((carpeta / "plan.json").read_text())["temporadas"] == ["21"]
    code, out = _main(["siguiente", "--salud", str(salud)], tmp_path, monkeypatch)
    assert code == 0 and "accion=descargar\n" in out and "trabajos=goleadores:2025-2026\n" in out

    llamadas = []

    def run(cmd, cwd=None, env=None):
        llamadas.append((cmd, cwd, env.get("PYTHONPATH")))
        resumen = cmd[cmd.index("--resumen") + 1]
        Path(resumen).write_text(json.dumps({
            "pedidas": 30, "servidas": 30, "muertas": 0, "esperas": 0, "frenos": 0, "frenos_tras": [],
            "parada": "plazo", "nube": "azure", "runner_rechazado": False,
            "partes": {"goleadores:2025-2026": {"completo": False, "pendientes": 12, "no_disponible": 0}}}))
        return type("Hecho", (), {"returncode": 0})()

    monkeypatch.setattr(H.subprocess, "run", run)
    accion, resumen = tmp_path / "accion.json", tmp_path / "resumen.json"
    resumen.write_text("{\"de otra ejecución\": 1}")
    code, _ = _main(["descargar", "--accion", str(accion), "--resumen", str(resumen), "--salud", str(salud)],
                    tmp_path, monkeypatch, now="2026-11-25T10:02:00Z")
    assert code == 0 and len(llamadas) == 1
    cmd, cwd, pythonpath = llamadas[0]
    assert cmd[0] == sys.executable and cmd[1] == "scripts/fetch_fiflp_goleadores.py"
    assert Path(cmd[cmd.index("--carpeta") + 1]).resolve() == carpeta.resolve()
    assert Path(cwd) == ROOT and pythonpath == str(ROOT)
    assert json.loads(accion.read_text())["inicio"] == "2026-11-25T10:02:00+00:00"
    code, out = _main(["registrar", "--accion", str(accion), "--resumen", str(resumen), "--salud", str(salud)],
                      tmp_path, monkeypatch, now="2026-11-25T10:20:00Z")
    assert code == 0 and "relanzar=false\n" in out and "promovido=false\n" in out
    estado = json.loads((carpeta / "estado.json").read_text())
    assert estado["dia"] == {"fecha": "2026-11-25", "paginas": 30, "freno": None}
    assert estado["trabajos"]["goleadores:2025-2026"]["estado"] == "pendiente"
    assert estado["ejecuciones"][-1]["relanzada"] is False
    code, _ = _main(["estado", "--linea"], tmp_path, monkeypatch)
    assert code == 0
    if habia is None:
        assert not del_repo.exists()
    else:
        assert sorted(p.name for p in del_repo.iterdir()) == habia


def test_la_orden_de_la_prueba_y_del_encargo(tmp_path, monkeypatch, capsys):
    carpeta = tmp_path / "historico"
    monkeypatch.setenv("HISTORICO_CARPETA", str(carpeta))
    salud = tmp_path / "no-esta.json"
    assert _main(["encargar", "--temporadas", "21", "--categorias", "alevin", "--trabajos", "goleadores",
                  "--calendario", ""], tmp_path, monkeypatch)[0] == 0
    estado = H.estado_vacio()
    estado["trabajos"]["goleadores:2025-2026"] = {"estado": "completo", "pendientes": 0, "no_disponible": 0}
    carpeta.joinpath("estado.json").write_text(json.dumps(estado))
    code, out = _main(["siguiente", "--salud", str(salud)], tmp_path, monkeypatch)
    assert "accion=probar\n" in out and "trabajos=goleadores:2025-2026\n" in out
    veredicto = tmp_path / "veredicto.json"
    veredicto.write_text(json.dumps({"verde": True, "motivo": "", "mb_antes": 41.2, "mb_despues": 43.0,
                                     "segundos": 95}))
    # Verde, pero sin poder pasarlo a scripts/: rojo, y no se da por promovido.
    code, out = _main(["registrar", "--prueba", str(veredicto), "--trabajos", "goleadores:2025-2026",
                       "--promover", "failure", "--salud", str(salud)], tmp_path, monkeypatch)
    assert "promovido=false\n" in out
    assert json.loads(carpeta.joinpath("estado.json").read_text())["trabajos"]["goleadores:2025-2026"]["estado"] == "fallo"
    carpeta.joinpath("estado.json").write_text(json.dumps(estado))
    code, out = _main(["registrar", "--prueba", str(veredicto), "--trabajos", "goleadores:2025-2026",
                       "--promover", "success", "--salud", str(salud)], tmp_path, monkeypatch)
    assert "promovido=true\n" in out and "relanzar=false\n" in out          # después no queda nada: terminado
    # Sin veredicto (la prueba no acabó): rojo, para no repetirla en bucle.
    carpeta.joinpath("estado.json").write_text(json.dumps(estado))
    code, out = _main(["registrar", "--prueba", str(tmp_path / "nada.json"), "--trabajos", "goleadores:2025-2026",
                       "--salud", str(salud)], tmp_path, monkeypatch)
    e = json.loads(carpeta.joinpath("estado.json").read_text())
    assert e["trabajos"]["goleadores:2025-2026"]["estado"] == "fallo" and "promovido=false\n" in out
    # Parar, reanudar y reintentar cambian solo el plan.
    for orden in ("parar", "reanudar", "reintentar"):
        assert _main([orden], tmp_path, monkeypatch)[0] == 0
    plan = json.loads(carpeta.joinpath("plan.json").read_text())
    assert plan["parado"] is False and plan["reintentar_desde"] == "2026-11-25T10:00:00+00:00"
    # Un encargo que no vale sale con error y deja el plan como estaba.
    assert _main(["encargar", "--temporadas", "23", "--categorias", "alevin", "--trabajos", "actas",
                  "--calendario", ""], tmp_path, monkeypatch)[0] != 0
    assert json.loads(carpeta.joinpath("plan.json").read_text()) == plan


def test_el_freno_del_bot_se_apunta_aunque_no_se_lea_nada(tmp_path, monkeypatch):
    carpeta = tmp_path / "historico"
    monkeypatch.setenv("HISTORICO_CARPETA", str(carpeta))
    salud = tmp_path / "salud.json"
    salud.write_text(json.dumps({"checkedAt": "2026-11-25T09:21:28+00:00", "run": {"pauses": 1, "cloud": "azure"}}))
    _main(["encargar", "--temporadas", "21", "--categorias", "alevin", "--trabajos", "goleadores",
           "--calendario", ""], tmp_path, monkeypatch)
    code, out = _main(["siguiente", "--salud", str(salud)], tmp_path, monkeypatch)
    assert "accion=nada\n" in out and "apuntado=true\n" in out
    estado = json.loads(carpeta.joinpath("estado.json").read_text())
    assert estado["dia"]["freno"] == "bot" and estado["dias_frenados"] == ["2026-11-25"]
    code, out = _main(["siguiente", "--salud", str(salud)], tmp_path, monkeypatch, now="2026-11-25T11:00:00Z")
    assert "accion=nada\n" in out and "apuntado=false\n" in out               # una vez al día
