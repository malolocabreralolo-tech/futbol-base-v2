"""TDD — el descargador de la liga de escuelas de MyGol (scripts/fetch_mygol.py).

Sin red: una API de mentira sirve las respuestas de tests/fixtures/mygol/ (recortadas de las reales y
con los nombres de los niños cambiados por inventados) y cuenta lo que se le pide."""
import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_mygol as M  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "mygol"
HOY = date(2027, 3, 1)          # todos los partidos de la fixture, de hace más de 21 días


def fixture(nombre):
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


LISTA_96 = fixture("matches_fortournament_96.json")
PARTIDO = fixture("matches_14750.json")
IDS_96 = sorted(m["id"] for j in LISTA_96 for m in j.get("matches") or [])


class ApiFalsa:
    """Sirve la lista del torneo 96 y, de cada partido suyo, el de la fixture con su id y sus equipos."""

    def __init__(self, fallan=()):
        self.peticiones = 0
        self.pedidas = []
        self.fallan = set(fallan)       # rutas que siempre fallan ("*" = todos los partidos)

    def get(self, path):
        self.peticiones += 1
        self.pedidas.append(path)
        if path in self.fallan or ("*" in self.fallan and path.startswith("/matches/") and "fortournament" not in path):
            raise M.ApiError(f"{path}: 503")
        if path == "/matches/fortournament/96":
            return copy.deepcopy(LISTA_96)
        if path.startswith("/matches/fortournament/"):
            raise M.ApiError(f"{path}: 400")
        mid = int(path.rsplit("/", 1)[1])
        entrada = next((m for j in LISTA_96 for m in j.get("matches") or [] if m["id"] == mid), None)
        if entrada is None:
            raise M.ApiError(f"{path}: 404")
        p = copy.deepcopy(PARTIDO)
        p["id"] = mid
        p["idHomeTeam"] = p["homeTeam"]["id"] = entrada["idHomeTeam"]
        p["idVisitorTeam"] = p["visitorTeam"]["id"] = entrada["idVisitorTeam"]
        p["homeTeam"]["name"] = NOMBRES.get(entrada["idHomeTeam"], f"EQUIPO {entrada['idHomeTeam']}")
        p["visitorTeam"]["name"] = NOMBRES.get(entrada["idVisitorTeam"], f"EQUIPO {entrada['idVisitorTeam']}")
        p["startTime"], p["status"], p["field"] = entrada["startTime"], entrada["status"], entrada["field"]
        p["day"] = {"id": entrada["idDay"], "name": next(j["name"] for j in LISTA_96 if j["id"] == entrada["idDay"])}
        return p


NOMBRES = {PARTIDO["homeTeam"]["id"]: PARTIDO["homeTeam"]["name"],
           PARTIDO["visitorTeam"]["id"]: PARTIDO["visitorTeam"]["name"]}


def tabla(raiz, torneos=None):
    torneos = torneos or {"96": {"temporada": "2026-2027", "categoria": "benjamin",
                                 "nombre": "BENJAMIN ESCUELA 2026/2027"}}
    (raiz / "mygol_torneos.json").write_text(json.dumps(torneos, ensure_ascii=False), encoding="utf-8")


def original(raiz, temporada="2026-2027"):
    return json.loads((raiz / f"mygol_{temporada}_raw.json").read_text(encoding="utf-8"))


def pedidos_de_partido(api):
    return [int(p.rsplit("/", 1)[1]) for p in api.pedidas if "fortournament" not in p]


def test_partidos_del_torneo():
    partidos = M.partidos_del_torneo(LISTA_96)
    assert sorted(partidos) == IDS_96 and len(partidos) == 16
    assert partidos[14750] == {"jornada": "Jornada 1", "fecha": "2026-10-24T09:00:00", "estado": 5,
                               "local": 1371, "visitante": 1364, "campo": "BARRIO ATL."}
    assert partidos[14748]["campo"] == "LAS TORRES 1"
    segunda = [p for p in partidos.values() if p["jornada"] == "Jornada 2"]
    assert len(segunda) == 8 and {p["estado"] for p in segunda} == {1}
    assert all("jugadores" not in p and "leido" not in p for p in partidos.values())


def test_jugadores_del_partido():
    p = copy.deepcopy(PARTIDO)
    p["visitorPlayers"][1]["dayResultSummary"]["gamesPlayed"] = 0      # convocado que no jugó
    jugadores, equipos = M.jugadores_del_partido(p)
    assert equipos == {"1371": "C.F.UNIÓN VIERA B", "1364": "UD LAS PALMAS A"}
    assert set(jugadores) == {"1371", "1364"}
    local = jugadores["1371"]
    assert [j[0] for j in local] == sorted(j[0] for j in local) and len(local) == 18
    assert local[0] == [10284, "Nombre1", "Apellido1 Apellido2", 1]
    assert local[-1][0] == 11252                     # en la respuesta va antes que 11165: aquí, en orden de id
    sin_resumen = {j[0]: j[3] for j in local}
    assert sin_resumen[10291] == 0 and sin_resumen[11252] == 0      # sin dayResultSummary: no jugó
    visitante = {j[0]: j[3] for j in jugadores["1364"]}
    assert visitante[10192] == 0 and visitante[10191] == 1 and visitante[10193] == 0
    assert len(visitante) == 15


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormido = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormido.append(round(s, 6))
        self.t += s


def test_pausa_entre_peticiones():
    reloj = Reloj()

    def abrir(url):
        reloj.t += 0.3                    # lo que tarda en contestar
        return 200, b"[]"

    api = M.Api(abrir=abrir, dormir=reloj.dormir, reloj=reloj)
    assert api.get("/seasons") == [] and reloj.dormido == []
    api.get("/seasons")
    assert reloj.dormido == [pytest.approx(M.PAUSA - 0.3)]
    reloj.t += 5                          # si ya pasó la pausa, no duerme
    api.get("/seasons")
    assert len(reloj.dormido) == 1 and api.peticiones == 3


def test_reintentos_y_4xx():
    llamadas = []

    def abrir_503(url):
        llamadas.append(url)
        return 503, b"busy"

    api = M.Api(abrir=abrir_503, dormir=lambda s: None)
    with pytest.raises(M.ApiError):
        api.get("/matches/1")
    assert len(llamadas) == 3 and api.peticiones == 3          # la primera y dos reintentos

    respuestas = [OSError("red"), (502, b""), (200, b'{"id": 7}')]

    def abrir_se_recupera(url):
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    api = M.Api(abrir=abrir_se_recupera, dormir=lambda s: None)
    assert api.get("/matches/7") == {"id": 7} and api.peticiones == 3

    llamadas.clear()

    def abrir_400(url):
        llamadas.append(url)
        return 400, b'"Error.TournamentNotVisible"'

    api = M.Api(abrir=abrir_400, dormir=lambda s: None)
    with pytest.raises(M.ApiError):
        api.get("/tournaments/33")
    assert len(llamadas) == 1 and llamadas[0] == M.BASE + "/tournaments/33"


def test_reanuda_sin_repetir(tmp_path):
    tabla(tmp_path)
    api = ApiFalsa()
    M.descargar(["2026-2027"], api, HOY, raiz=tmp_path, max_peticiones=6, registro=lambda *a: None)
    leidos = pedidos_de_partido(api)
    assert leidos == IDS_96[:5]
    a_medias = original(tmp_path)
    assert sum("leido" in p for p in a_medias["torneos"]["96"]["partidos"].values()) == 5

    api = ApiFalsa()
    res = M.descargar(["2026-2027"], api, HOY, raiz=tmp_path, registro=lambda *a: None)
    assert pedidos_de_partido(api) == IDS_96[5:]
    assert res == {"peticiones": 12, "leidos": 11, "pendientes": 0, "fallos": 0}
    entero = original(tmp_path)["torneos"]["96"]
    assert all(p["leido"] == HOY.isoformat() and set(p["jugadores"]) == {str(p["local"]), str(p["visitante"])}
               for p in entero["partidos"].values())
    assert entero["equipos"]["1371"] == "C.F.UNIÓN VIERA B"
    assert entero["categoria"] == "benjamin" and entero["nombre"] == "BENJAMIN ESCUELA 2026/2027"


def test_pendientes_por_fecha():
    hoy = date(2026, 11, 25)
    torneo = {"partidos": {
        "40": {"fecha": "2026-10-26T10:00:00", "leido": "2026-10-27"},   # hace 30 días, leído: no
        "30": {"fecha": "2026-11-20T10:00:00", "leido": "2026-11-21"},   # hace 5: sí (puede cambiar)
        "20": {"fecha": "2026-12-05T10:00:00", "leido": "2026-11-21"},   # futuro: sí
        "10": {"fecha": "2026-01-10T10:00:00"},                          # sin leer: sí
        "5": {"fecha": "0001-01-01T00:00:00", "leido": "2026-11-21"},    # sin fecha y leído: no
        "50": {"fecha": "2026-11-04T09:00:00", "leido": "2026-11-05"},   # hace 21 días justos: sí
        "60": {"fecha": "2026-12-09T10:00:00"},                          # a 14 días justos, sin leer: sí
        "70": {"fecha": "2026-12-10T10:00:00"},                          # a 15 días, sin leer: aún no
        "80": {"fecha": "2027-01-16T10:00:00", "leido": "2026-11-21"},   # muy lejos, leído: tampoco
        "90": {"fecha": "0001-01-01T00:00:00"},                          # sin fecha y sin leer: sí
    }}
    assert M.pendientes(torneo, hoy) == [10, 20, 30, 50, 60, 90]


def test_para_tras_cinco_fallos(tmp_path):
    tabla(tmp_path)
    M.descargar(["2026-2027"], ApiFalsa(), HOY, raiz=tmp_path, max_peticiones=4, registro=lambda *a: None)
    antes = original(tmp_path)
    api = ApiFalsa(fallan={"*"})
    res = M.descargar(["2026-2027"], api, HOY, raiz=tmp_path, registro=lambda *a: None)
    assert len(pedidos_de_partido(api)) == M.MAX_FALLOS
    assert res["fallos"] == M.MAX_FALLOS and res["leidos"] == 0 and res["pendientes"] == 13
    despues = original(tmp_path)
    assert despues == antes


def test_torneo_fuera_de_la_tabla(tmp_path):
    tabla(tmp_path)
    api = ApiFalsa()
    M.descargar(["2026-2027", "2022-2023"], api, HOY, raiz=tmp_path, registro=lambda *a: None)
    assert api.pedidas[0] == "/matches/fortournament/96"
    assert [p for p in api.pedidas if "fortournament" in p] == ["/matches/fortournament/96"]
    assert not (tmp_path / "mygol_2022-2023_raw.json").exists()
    assert list(original(tmp_path)["torneos"]) == ["96"]


def test_max_peticiones(tmp_path):
    tabla(tmp_path)
    api = ApiFalsa()
    mensajes = []
    res = M.descargar(["2026-2027"], api, HOY, raiz=tmp_path, max_peticiones=5, registro=mensajes.append)
    assert api.peticiones == 5
    assert res == {"peticiones": 5, "leidos": 4, "pendientes": 12, "fallos": 0}
    guardado = original(tmp_path)["torneos"]["96"]["partidos"]
    assert len(guardado) == 16 and sum("leido" in p for p in guardado.values()) == 4
    assert any("pendientes" in m for m in mensajes)


def test_original_estable(tmp_path):
    def raw(orden):
        partidos = {"10": {"jornada": "Jornada 2", "fecha": "2026-11-07T09:00:00", "estado": 1,
                           "local": 2, "visitante": 100, "campo": "CAMPO Ñ"},
                    "9": {"campo": None, "visitante": 2, "local": 100, "estado": 5,
                          "fecha": "2026-10-24T09:00:00", "jornada": "Jornada 1", "leido": "2026-11-25",
                          "jugadores": {"100": [[7, "Nombre1", "Apellido1", 1]], "2": [[3, "Nombre2", "", 0]]}}}
        torneos = {"100": {"categoria": "alevin", "nombre": "ALEVÍN", "equipos": {"100": "UNIÓN B", "2": "A"},
                           "partidos": partidos},
                   "85": {"nombre": "X", "categoria": "miniprebenjamin", "equipos": {}, "partidos": {}}}
        if orden:
            torneos = dict(reversed(list(torneos.items())))
            torneos["100"]["partidos"] = dict(reversed(list(partidos.items())))
        return {"torneos": torneos, "temporada": "2026-2027"}

    a, b = tmp_path / "a.json", tmp_path / "b.json"
    M.escribir_original(a, raw(False))
    M.escribir_original(b, raw(True))
    texto = a.read_bytes()
    assert texto == b.read_bytes()
    M.escribir_original(a, json.loads(texto))
    assert a.read_bytes() == texto
    s = texto.decode("utf-8")
    assert s.endswith("}\n") and "UNIÓN B" in s and "CAMPO Ñ" in s
    assert s.index('"85"') < s.index('"100"') and s.index('"9"') < s.index('"10"')
    assert json.loads(s)["torneos"]["100"]["partidos"]["9"]["jugadores"]["2"] == [[3, "Nombre2", "", 0]]
