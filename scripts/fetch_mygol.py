#!/usr/bin/env python3
"""fetch_mygol.py — La liga de escuelas de MyGol (tusligascanarias.mygol.es), en un original por temporada.

La liga de escuelas (miniprebenjamín, prebenjamín, benjamín y, desde 2025-26, alevín) no pasa por la
federación: la lleva la organización ACADEE en la plataforma MyGol, con una API JSON pública:
  /matches/fortournament/<id>   las jornadas de un torneo, cada una con sus partidos (equipos, fecha,
                                estado, campo). Contesta también con los torneos ocultos (los de
                                temporadas pasadas), que en /tournaments/<id> dan 400.
  /matches/<id>                 un partido: los nombres de los dos equipos y la plantilla de cada uno
                                (id del jugador, nombre y apellidos) con
                                `dayResultSummary.gamesPlayed`: si el niño jugó esa jornada.
No hay marcadores ni goles (las escuelas no los publican) ni fecha de nacimiento (sale 0001-01-01).
El id del jugador (y `idUser`) es propio de cada temporada: MyGol crea las fichas de nuevo cada año, y
el mismo niño tiene otro id al siguiente. Entre temporadas solo se le puede seguir por nombre y apellidos.

De qué temporada y categoría es cada torneo no lo dice la API de los ocultos: lo dice una tabla revisada
a mano, scripts/mygol_torneos.json. Un torneo que no está en ella no se pide nunca.

Original: scripts/mygol_<temporada>_raw.json
  {"temporada": S, "torneos": {id: {categoria, nombre, equipos: {id: nombre},
                                    partidos: {id: {jornada, fecha, estado, local, visitante, campo,
                                                    jugadores: {equipo: [[id, nombre, apellidos, jugó]]},
                                                    leido}}}}}
Un partido sin leer no lleva `jugadores` ni `leido`. Un partido leído con fecha de hace más de 21 días ya
no cambia y no se vuelve a pedir: la descarga se puede cortar (--max-peticiones, fallos) y reanudar. Uno con
fecha a más de 14 días vista tampoco se pide todavía.

Cortesía con MyGol: una petición cada PAUSA segundos como mínimo, de una en una; dos reintentos ante un
fallo de red o un 5xx; parar tras MAX_FALLOS fallos seguidos guardando lo ya bajado. Las cabeceras, las
de un navegador: nada que identifique a nadie.

  python3 scripts/fetch_mygol.py --en-curso | --todas | --temporadas 2022-2023,2023-2024 [--max-peticiones N]
  python3 scripts/fetch_mygol.py --descubrir [--hasta 120]     (lista los torneos con partidos; no escribe)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from escritura import escribir_atomico  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE = "https://tusligascanarias.mygol.es/api"
PAUSA = 2.0
MAX_FALLOS = 5
REINTENTOS = 2
DIAS_QUE_CAMBIAN = 21          # un partido de hace menos (o futuro) aún puede cambiar: se vuelve a pedir
DIAS_DE_ANTELACION = 14        # un partido a más de estos días vista aún no se pide
GUARDAR_CADA = 25              # partidos leídos entre dos guardados del original
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
DESCANSO = -1                  # el «equipo» de la jornada de descanso en las listas de MyGol
# El orden de las claves que no son ids, para que el original no baile de una ejecución a otra.
ORDEN = ("temporada", "torneos", "categoria", "nombre", "equipos", "partidos",
         "jornada", "fecha", "estado", "local", "visitante", "campo", "jugadores", "leido")


class ApiError(Exception):
    """Una petición que no dio un JSON: un 4xx, o un 5xx / fallo de red tras los reintentos."""


def _abrir(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Api:
    """Las peticiones a MyGol, de una en una y con PAUSA segundos entre el inicio de dos.

    `abrir(url) -> (estado HTTP, cuerpo)` hace la petición (lanza OSError si falla la red); `dormir` y
    `reloj`, los del tiempo: las pruebas ponen los suyos. `peticiones` cuenta todas, reintentos incluidos."""

    def __init__(self, abrir=None, dormir=None, reloj=None, base=BASE, pausa=PAUSA):
        self.abrir = abrir or _abrir
        self.dormir = dormir or time.sleep
        self.reloj = reloj or time.monotonic
        self.base = base
        self.pausa = pausa
        self.peticiones = 0
        self.correctas = 0
        self._ultima = None

    def _espera(self):
        if self._ultima is not None:
            falta = self._ultima + self.pausa - self.reloj()
            if falta > 0:
                self.dormir(falta)
        self._ultima = self.reloj()

    def get(self, path):
        url = self.base + path
        motivo = ""
        for intento in range(REINTENTOS + 1):
            if intento:
                self.dormir(self.pausa * intento)      # un servidor que falla, más despacio todavía
            self._espera()
            self.peticiones += 1
            try:
                estado, cuerpo = self.abrir(url)
            except OSError as e:
                motivo = f"red: {e}"
                continue
            if 500 <= estado < 600:
                motivo = f"HTTP {estado}"
                continue
            if estado >= 400:
                raise ApiError(f"{path}: HTTP {estado} {cuerpo[:80]!r}")
            try:
                datos = json.loads(cuerpo.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as e:
                raise ApiError(f"{path}: no es JSON ({e})") from e
            self.correctas += 1
            return datos
        raise ApiError(f"{path}: {motivo} ({REINTENTOS + 1} intentos)")


def _fecha(texto):
    """La fecha de un partido, o None si MyGol no la ha puesto (0001-01-01 y 1901-01-01)."""
    try:
        d = date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None
    return d if d.year > 1901 else None


def partidos_del_torneo(jornadas_json):
    """De /matches/fortournament/<id> a {id: {jornada, fecha, estado, local, visitante, campo}}.
    Los «partidos» contra el descanso (equipo -1) no son partidos: fuera."""
    out = {}
    for jornada in jornadas_json or []:
        for m in jornada.get("matches") or []:
            if DESCANSO in (m.get("idHomeTeam"), m.get("idVisitorTeam")):
                continue
            out[int(m["id"])] = {"jornada": jornada.get("name"), "fecha": m.get("startTime"),
                                 "estado": m.get("status"), "local": m.get("idHomeTeam"),
                                 "visitante": m.get("idVisitorTeam"),
                                 "campo": (m.get("field") or {}).get("name")}
    return out


def jugadores_del_partido(partido_json):
    """De /matches/<id>: ({equipo: [[id, nombre, apellidos, jugó]] en orden de id}, {equipo: nombre}).
    `jugó` es 1 si dayResultSummary.gamesPlayed >= 1; sin dayResultSummary, 0 (convocado, no jugó)."""
    jugadores, equipos = {}, {}
    for lado in ("home", "visitor"):
        equipo = partido_json.get(f"{lado}Team") or {}
        eid = equipo.get("id") or partido_json.get(f"id{lado.capitalize()}Team")
        if eid is None:
            continue
        if equipo.get("name"):
            equipos[str(eid)] = equipo["name"]
        filas = []
        for p in partido_json.get(f"{lado}Players") or []:
            jugados = (p.get("dayResultSummary") or {}).get("gamesPlayed") or 0
            filas.append([int(p["id"]), p.get("name") or "", p.get("surname") or "", 1 if jugados >= 1 else 0])
        jugadores[str(eid)] = sorted(filas, key=lambda f: f[0])
    return jugadores, equipos


def pendientes(torneo, hoy):
    """Los partidos que hay que pedir, en orden de id: los que no se han leído nunca y los que aún pueden
    cambiar (fecha en los últimos 21 días o en el futuro). Uno con fecha a más de 14 días vista, no: su
    plantilla ya llegará cuando se acerque (cada semana se pedirían todos los futuros para nada)."""
    desde = hoy - timedelta(days=DIAS_QUE_CAMBIAN)
    hasta = hoy + timedelta(days=DIAS_DE_ANTELACION)
    out = []
    for pid, p in (torneo.get("partidos") or {}).items():
        f = _fecha(p.get("fecha"))
        if f is not None and f > hasta:
            continue
        if "leido" not in p or (f is not None and f >= desde):
            out.append(int(pid))
    return sorted(out)


# ---- el original ----

def _es_id(clave):
    return clave.lstrip("-").isdigit()


def _ordenado(obj):
    """Las claves que son ids, en orden numérico; las demás, en el orden de ORDEN."""
    if isinstance(obj, dict):
        if obj and all(_es_id(k) for k in obj):
            claves = sorted(obj, key=int)
        else:
            claves = sorted(obj, key=lambda k: (ORDEN.index(k) if k in ORDEN else len(ORDEN), k))
        return {k: _ordenado(obj[k]) for k in claves}
    if isinstance(obj, list):
        return [_ordenado(x) for x in obj]
    return obj


def _json(x):
    return json.dumps(x, ensure_ascii=False)


def serializar(raw):
    """El texto del original: un torneo por bloque y un partido por línea, para que un cambio en un
    partido sea una línea del diff."""
    raw = _ordenado(raw)
    lineas = ["{"]
    claves = list(raw)
    for i, k in enumerate(claves):
        coma = "," if i < len(claves) - 1 else ""
        if k != "torneos":
            lineas.append(f" {_json(k)}: {_json(raw[k])}{coma}")
            continue
        torneos = raw["torneos"]
        if not torneos:
            lineas.append(f' "torneos": {{}}{coma}')
            continue
        lineas.append(' "torneos": {')
        tids = list(torneos)
        for a, tid in enumerate(tids):
            t = torneos[tid]
            lineas.append(f"  {_json(tid)}: {{")
            campos = list(t)
            for b, c in enumerate(campos):
                coma_c = "," if b < len(campos) - 1 else ""
                v = t[c]
                if c in ("equipos", "partidos") and isinstance(v, dict) and v:
                    lineas.append(f"   {_json(c)}: {{")
                    ids = list(v)
                    for n, x in enumerate(ids):
                        lineas.append(f"    {_json(x)}: {_json(v[x])}{',' if n < len(ids) - 1 else ''}")
                    lineas.append(f"   }}{coma_c}")
                else:
                    lineas.append(f"   {_json(c)}: {_json(v)}{coma_c}")
            lineas.append(f"  }}{',' if a < len(tids) - 1 else ''}")
        lineas.append(f" }}{coma}")
    lineas.append("}")
    return "\n".join(lineas) + "\n"


def escribir_original(path, raw):
    escribir_atomico(path, serializar(raw))


def _guardar(path, raw):
    """El original, solo si cambia; uno nuevo sin ningún partido (todo falló) no se escribe."""
    texto = serializar(raw)
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") == texto:
            return
    elif not any(t.get("partidos") for t in raw["torneos"].values()):
        return
    escribir_atomico(path, texto)


def raw_path(temporada, raiz=None):
    return Path(raiz or HERE) / f"mygol_{temporada}_raw.json"


def leer_tabla(raiz=None):
    path = Path(raiz or HERE) / "mygol_torneos.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _leer_original(temporada, raiz):
    path = raw_path(temporada, raiz)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = {}
    raw["temporada"] = temporada
    raw.setdefault("torneos", {})
    return raw


def _mezclar_lista(torneo, nuevos, registro, tid):
    """Lo que dice la lista, encima de lo guardado (sin perder `jugadores` ni `leido`). Un partido que la
    lista ya no trae se va del original, salvo que la lista venga vacía (eso se parece más a un fallo de
    MyGol que a un torneo sin partidos)."""
    viejos = torneo.setdefault("partidos", {})
    if not nuevos:
        if viejos:
            registro(f"  ! torneo {tid}: la lista de partidos viene vacía; se deja lo guardado")
        return
    quitados = set(viejos) - {str(pid) for pid in nuevos}
    for pid in quitados:
        del viejos[pid]
    if quitados:
        registro(f"  torneo {tid}: {len(quitados)} partidos que ya no están en MyGol, fuera")
    for pid, p in nuevos.items():
        viejos[str(pid)] = {**viejos.get(str(pid), {}), **p}


def _leer_partido(torneo, pid, datos, hoy):
    jugadores, equipos = jugadores_del_partido(datos)
    p = torneo["partidos"].setdefault(str(pid), {})
    dia = (datos.get("day") or {}).get("name")
    for clave, valor in (("jornada", dia), ("fecha", datos.get("startTime")), ("estado", datos.get("status")),
                         ("local", datos.get("idHomeTeam") or (datos.get("homeTeam") or {}).get("id")),
                         ("visitante", datos.get("idVisitorTeam") or (datos.get("visitorTeam") or {}).get("id")),
                         ("campo", (datos.get("field") or {}).get("name"))):
        if valor is not None:
            p[clave] = valor
    p["jugadores"] = jugadores
    p["leido"] = hoy.isoformat()
    torneo.setdefault("equipos", {}).update(equipos)


def descargar(temporadas, api, hoy, raiz=None, max_peticiones=None, registro=print):
    """Baja los torneos de la tabla de esas temporadas: de cada uno, su lista de partidos y después cada
    partido pendiente. Guarda el original de la temporada cada GUARDAR_CADA partidos leídos y al acabar.
    Para al llegar a `max_peticiones` o tras MAX_FALLOS fallos seguidos.
    Devuelve {"peticiones", "leidos", "pendientes", "fallos"}."""
    tabla = leer_tabla(raiz)
    inicio = api.peticiones
    leidos = fallos = seguidos = 0
    parar = None
    originales = {}

    def queda_cupo():
        return max_peticiones is None or api.peticiones - inicio < max_peticiones

    def fallo(motivo):
        nonlocal fallos, seguidos, parar
        fallos += 1
        seguidos += 1
        registro(f"  ! {motivo}")
        if seguidos >= MAX_FALLOS:
            parar = f"{MAX_FALLOS} fallos seguidos"

    for temporada in temporadas:
        tids = sorted((t for t, v in tabla.items() if v.get("temporada") == temporada), key=int)
        if not tids:
            registro(f"MyGol {temporada}: ningún torneo en la tabla")
            continue
        raw = originales[temporada] = _leer_original(temporada, raiz)
        path = raw_path(temporada, raiz)
        sin_guardar = 0
        for tid in tids:
            if parar:
                break
            torneo = raw["torneos"].setdefault(tid, {})
            torneo["categoria"] = tabla[tid]["categoria"]
            torneo["nombre"] = tabla[tid]["nombre"]
            torneo.setdefault("equipos", {})
            torneo.setdefault("partidos", {})
            if not queda_cupo():
                parar = f"{max_peticiones} peticiones"
                break
            try:
                _mezclar_lista(torneo, partidos_del_torneo(api.get(f"/matches/fortournament/{tid}")), registro, tid)
                seguidos = 0
            except ApiError as e:
                fallo(f"torneo {tid}: {e}")
            if parar:
                break
            cola = pendientes(torneo, hoy)
            registro(f"MyGol {temporada} · torneo {tid} ({torneo['categoria']}): "
                     f"{len(torneo['partidos'])} partidos, {len(cola)} por leer")
            for pid in cola:
                if not queda_cupo():
                    parar = f"{max_peticiones} peticiones"
                    break
                try:
                    datos = api.get(f"/matches/{pid}")
                except ApiError as e:
                    fallo(f"partido {pid}: {e}")
                    if parar:
                        break
                    continue
                seguidos = 0
                _leer_partido(torneo, pid, datos, hoy)
                leidos += 1
                sin_guardar += 1
                if sin_guardar >= GUARDAR_CADA:
                    _guardar(path, raw)
                    sin_guardar = 0
        _guardar(path, raw)
        if parar:
            break

    quedan = 0
    for temporada in temporadas:
        raw = originales.get(temporada)
        if raw is None:
            if not any(v.get("temporada") == temporada for v in tabla.values()):
                continue
            raw = _leer_original(temporada, raiz)
        quedan += sum(len(pendientes(t, hoy)) for t in raw["torneos"].values())
    if parar:
        registro(f"MyGol: parado tras {parar}")
    res = {"peticiones": api.peticiones - inicio, "leidos": leidos, "pendientes": quedan, "fallos": fallos}
    registro(f"MyGol: {res['peticiones']} peticiones, {leidos} partidos leídos, {quedan} pendientes, "
             f"{fallos} fallos")
    return res


def descubrir(api, hasta, registro=print):
    """Recorre /matches/fortournament/<id> de 1 a `hasta` y devuelve, de cada torneo con partidos, id,
    jornadas, partidos, equipos, cuántos tienen marcador (los de escuela, ninguno) y fechas. Antes, una
    petición a /tournaments para poner nombre y temporada a los visibles. No escribe nada."""
    visibles = {}
    try:
        for t in api.get("/tournaments") or []:
            visibles[int(t["id"])] = t
    except ApiError as e:
        registro(f"  ! /tournaments: {e}")
    out = []
    seguidos = 0
    for tid in range(1, hasta + 1):
        try:
            jornadas = api.get(f"/matches/fortournament/{tid}")
            seguidos = 0
        except ApiError as e:
            if "HTTP 4" in str(e):           # un torneo que no existe: se sigue
                continue
            seguidos += 1
            registro(f"  ! torneo {tid}: {e}")
            if seguidos >= MAX_FALLOS:
                registro(f"MyGol: parado tras {MAX_FALLOS} fallos seguidos")
                break
            continue
        ms = [m for j in jornadas or [] for m in j.get("matches") or []]
        if not ms:
            continue
        fechas = sorted(f.isoformat() for f in (_fecha(m.get("startTime")) for m in ms) if f)
        equipos = {m.get("idHomeTeam") for m in ms} | {m.get("idVisitorTeam") for m in ms}
        equipos.discard(DESCANSO)
        v = visibles.get(tid) or {}
        fila = {"id": tid, "nombre": v.get("name"), "temporada_mygol": v.get("idSeason"),
                "jornadas": len(jornadas), "partidos": len(ms), "equipos": len(equipos),
                "con_marcador": sum(1 for m in ms if m.get("homeScore") or m.get("visitorScore")),
                "desde": fechas[0] if fechas else None, "hasta": fechas[-1] if fechas else None}
        out.append(fila)
        registro(f"  {tid}: {fila['partidos']} partidos, {fila['equipos']} equipos, "
                 f"{fila['con_marcador']} con marcador, {fila['desde']} → {fila['hasta']}"
                 + (f" · {fila['nombre']}" if fila["nombre"] else ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="La liga de escuelas de MyGol, en scripts/mygol_<S>_raw.json")
    que = ap.add_mutually_exclusive_group(required=True)
    que.add_argument("--temporadas", help="separadas por comas, como 2022-2023,2023-2024")
    que.add_argument("--en-curso", action="store_true", help="la temporada más reciente de mygol_torneos.json")
    que.add_argument("--todas", action="store_true", help="todas las de mygol_torneos.json")
    que.add_argument("--descubrir", action="store_true", help="lista los torneos con partidos; no escribe")
    ap.add_argument("--hasta", type=int, default=120, help="con --descubrir: hasta qué id de torneo")
    ap.add_argument("--max-peticiones", type=int, default=None)
    ap.add_argument("--hoy", default=None, help="AAAA-MM-DD (por defecto, hoy)")
    args = ap.parse_args(argv)
    api = Api()
    if args.descubrir:
        descubrir(api, args.hasta)
        return 0 if api.correctas else 1
    tabla = leer_tabla()
    todas = sorted({v["temporada"] for v in tabla.values()})
    if args.todas:
        temporadas = todas
    elif args.en_curso:
        temporadas = todas[-1:]
    else:
        temporadas = [s.strip() for s in args.temporadas.split(",") if s.strip()]
        desconocidas = [s for s in temporadas if s not in todas]
        if desconocidas:
            print(f"MyGol: sin torneos en la tabla para {', '.join(desconocidas)}")
    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()
    res = descargar(temporadas, api, hoy, max_peticiones=args.max_peticiones)
    if res["pendientes"]:
        print(f"MyGol: quedan {res['pendientes']} partidos pendientes; la próxima vez sigue por ahí")
    if res["peticiones"] and not api.correctas:
        print("MyGol: no se pudo leer nada")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
