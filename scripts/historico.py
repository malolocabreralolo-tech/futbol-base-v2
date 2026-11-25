#!/usr/bin/env python3
"""historico.py — El carril del histórico: qué baja de la federación cada ejecución de historico.yml, con qué
tope, y qué se prueba antes de pasarlo al bot.

El problema. Hasta noviembre de 2026 las tandas del histórico (fetch_fiflp_goleadores, _detalle, _actas, cada una
con su workflow) daban por leída una página vacía: con el freno de la federación (desde el 14/10) habrían guardado
grupos y jornadas vacíos como buenos (docs/ampliacion-mapa.md, sección 2). Lo medido (docs/freno-2026-11.md, 840
registros de pasadas): en los runners de GitHub en Azure la federación sirve ~124-138 páginas por pasada de 16
min, sin freno, a todas horas (~500 por hora); a los de AWS (cerca de la mitad de los jobs desde el 13/11) les
contesta vacío desde la primera petición, siempre; y hay páginas que vienen vacías siempre aunque la federación
sirva las demás (páginas muertas: lo que paraba las pasadas de v2 desde el 21/11). Los descargadores ya leen como
el bot (fiflp_carga.para_tanda) y llevan lo pendiente en sus ficheros; este módulo decide, en cada ejecución del
carril, qué toca.

Las reglas del carril, y el porqué de cada número:
  - UNA ejecución cada vez (historico.yml: concurrencia historico-federacion, sin cancelar): un solo runner, un
    navegador y FIFLP_MIN_INTERVAL (7 s) entre peticiones, como el bot. Ni IPs en paralelo ni proxies;
  - FUERA DE LAS VENTANAS DE PARTIDOS (las de reloj_pasadas: viernes de 18 a 24 y sábado y domingo de 10 a 24,
    hora de Canarias), que son del bot en vivo; cada ejecución acaba MARGEN_VENTANA (20 min) antes de la
    siguiente, y no empieza si le quedan menos de MINIMO_EJECUCION (10 min). Como mucho MINUTOS_EJECUCION (300):
    con la instalación y la subida cabe en el job de 350;
  - PAGINAS_DIA (2.000) páginas al día, hora de Canarias, para empezar: es lo que el bot leía a diario sin
    problemas del 21/10 al 13/11 (1.240-2.720; v1 y v2 juntas, ~3.700 el 14/11 sin consecuencias). En Azure son
    ~4 h de lectura, que caben fuera de las ventanas cualquier día y en una sola ejecución, y bajan el alevín de
    Gran Canaria de siete temporadas en unos 9-10 días. La rampa la sube a mano quien dirige
    (HISTORICO_PAGINAS_DIA, variable del repositorio): 2.000 → 3.000 → 4.000, cada escalón tras tres días seguidos
    sin ninguno en `dias_frenados` y con las pasadas del bot igual de servidas; de 4.000 no se pasa sin medir;
  - EL DÍA PARADO POR EL FRENO DE VERDAD: si en una ejecución la federación frena (una vacía sin servir otra, o un
    503/429; `frenos` del resumen, no solo `parada`: un freno cortado por el tope da parada «tope»), o si el último
    data-health.json del día dice que el bot en vivo lo ha esperado en Azure (freno_del_bot), no se lee nada más
    ese día; al día siguiente, el tope entero;
  - RELANZAR solo si la federación sirvió (fiflp_carga.RELANZAR_MIN, 60 páginas: con menos, algo iba mal) y
    nunca por caer en un runner que la federación no sirve (RELANZAR_SI_RUNNER_RECHAZADO = 0): relanzar hasta que
    toque Azure es esquivar un bloqueo, y lo decide el dueño. Lo retoma el disparo programado (cada 3 h: con la
    mitad de los runners en AWS, alguno de los ≤ 8 disparos del día cae en Azure, y uno solo llega al tope);
  - LA CUARENTENA Y LA PRUEBA: lo bajado va a scripts/historico/ (cuarentena.py), que el bot no mira. Un trabajo
    completo se prueba sobre una copia (prueba_historico.py: importar sin red, la base sana y todas las suites),
    una temporada cada vez y con MARGEN_PRUEBA (60 min) antes de la ventana siguiente (la importación del bot en
    su pasada siguiente no puede caer en ella); solo lo verde pasa a scripts/ (promovido) y lo importa el bot. Lo
    rojo queda «fallo» con su motivo y no se repite solo (reintentar): solo vuelve a probarse si la cuarentena
    trae otro contenido que el probado (las huellas de cada prueba), y entonces solo, para no arrastrar a nadie.

Los ficheros del carril (en carpeta(): HISTORICO_CARPETA o cuarentena.CARPETA):
  plan.json    el encargo (solo lo escribe el job del encargo: encargar, parar, reanudar, reintentar);
  estado.json  lo que lleva hecho (solo lo escribe el carril): el día, los días frenados, cada trabajo
               (pendiente, completo, fallo, promovido), las ejecuciones y las pruebas. De aquí leerá «Datos y
               fuentes» (no de data-health.json, que reescribe el bot: dos escritores chocarían al rebasar).

  python3 scripts/historico.py siguiente | descargar --accion F --resumen F | registrar --accion F [--resumen F]
                               | registrar --prueba F --trabajos a,b --promover RESULTADO
                               | encargar --temporadas 21,20 --categorias alevin --trabajos goleadores,actas
                                 --calendario '' | parar | reanudar | reintentar | estado [--linea]
  (todas con --now FECHA_ISO, para las pruebas).
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# scripts/ (sus módulos) y la raíz (fetch_fiflp_actas importa scripts.acta_parser): lo ejecuta el python del
# runner sin pip ni PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import actas_lotes  # noqa: E402
import cuarentena  # noqa: E402
import reloj_pasadas  # noqa: E402
from categorias import DB_NAME, DEFAULT_CATEGORIES, parse_categories  # noqa: E402
from cuarentena import FAMILIA, ficheros  # noqa: E402
from escritura import escribir_atomico  # noqa: E402
from fetch_fiflp_actas import SEASON_NAME, catalog_comps  # noqa: E402
from fiflp_carga import RELANZAR_MIN  # noqa: E402
from fiflp_manifest import NO_ES_LIGA, fold, segunda_fase  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
RAIZ = SCRIPTS.parent

PAGINAS_DIA = 2000
MINUTOS_EJECUCION = 300
MARGEN_VENTANA = timedelta(minutes=20)
MINIMO_EJECUCION = timedelta(minutes=10)
MARGEN_PRUEBA = timedelta(minutes=60)
# Relanzamientos seguidos tras caer en un runner que la federación no sirve: 0, ninguno. Relanzar hasta que toque
# Azure es esquivar un bloqueo que la federación aplica a AWS, y lo decide el dueño: si dice que sí, se cambia este
# número y nada más.
RELANZAR_SI_RUNNER_RECHAZADO = 0
# En este orden: lo barato que más dice de cada niño (clasificación y goleadores) primero; las actas, que dan a
# todos los niños con su identificador, después; el detalle (la ficha de los equipos, que no hace falta para las
# trayectorias), detrás; y las dos fases que reescriben un fichero ya promovido (cuarentena.FAMILIA), al final.
TRABAJOS = ("goleadores", "actas", "detalle", "calendario", "escudos")
ESTADOS = ("pendiente", "completo", "fallo", "promovido")
# La temporada en curso: sus goleadores y su calendario los lee el bot; el carril, solo sus actas y su detalle.
EN_CURSO = "22"
# Los registros de estado.json, con tope (es un fichero del repositorio, se sube en cada ejecución).
MAX_EJECUCIONES = 100
MAX_PRUEBAS = 50
MAX_DIAS_FRENADOS = 60
# El catálogo de competiciones ({temporada: {"all": [...]}}): None, el del repositorio. Las pruebas ponen el
# congelado (el vivo lo cambia discover-fiflp.yml).
CATALOGO = None

NOMBRE_CATEGORIA = {"benjamin": "benjamín", "prebenjamin": "prebenjamín", "alevin": "alevín"}
PARADAS = {"tope": "tope del día", "freno": "freno de verdad", "plazo": "plazo", "navegador": "navegador cerrado",
           "runner": "runner rechazado", None: "sin cortes"}


# ── La carpeta y sus ficheros ────────────────────────────────────────────────

def carpeta():
    """La carpeta del carril: HISTORICO_CARPETA (las pruebas) o la cuarentena (scripts/historico)."""
    return Path(os.environ.get("HISTORICO_CARPETA") or cuarentena.CARPETA)


def _leer_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _escribir_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(path, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def estado_vacio():
    return {"formato": 1, "dia": {"fecha": None, "paginas": 0, "freno": None}, "dias_frenados": [],
            "trabajos": {}, "ejecuciones": [], "pruebas": []}


def leer_plan():
    """El encargo (plan.json), o None si no hay o no se entiende: sin encargo no se baja nada."""
    plan = _leer_json(carpeta() / "plan.json")
    return plan if isinstance(plan, dict) and plan.get("temporadas") else None


def leer_estado():
    """El estado (estado.json); sin él, o si no se entiende, el vacío (todo pendiente)."""
    estado = _leer_json(carpeta() / "estado.json")
    if not isinstance(estado, dict):
        return estado_vacio()
    return {**estado_vacio(), **estado}


def guardar_estado(estado):
    _escribir_json(carpeta() / "estado.json", estado)


def guardar_plan(plan):
    _escribir_json(carpeta() / "plan.json", plan)


# ── El reloj y el tope ───────────────────────────────────────────────────────

def _utc(moment):
    return reloj_pasadas._utc(moment).astimezone(timezone.utc)


def _iso(moment):
    return _utc(moment).isoformat(timespec="seconds")


def _instante(texto):
    try:
        return _utc(datetime.fromisoformat(str(texto).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _local(moment):
    """La hora de Canarias, o la UTC si no está la base de zonas horarias (solo para fechas y textos: sin ella el
    carril no baja nada, hasta)."""
    return reloj_pasadas.local_time(moment) or _utc(moment)


def fecha_de(moment):
    """El día de Canarias de un instante («2026-11-25»): el del tope y el del freno."""
    return _local(moment).date().isoformat()


def hasta(now):
    """El fin del plazo de una ejecución que empieza `now`: None en una ventana de partidos, sin la hora de Canarias
    (el carril no corre a ciegas) o si al inicio de la ventana siguiente menos MARGEN_VENTANA le quedan menos de
    MINIMO_EJECUCION; si no, lo primero de ese límite y now + MINUTOS_EJECUCION."""
    now = _utc(now)
    local = reloj_pasadas.local_time(now)
    if local is None or reloj_pasadas.window(now):
        return None
    zona = local.tzinfo
    inicio = None
    for dias in range(8):
        dia = (local + timedelta(days=dias)).date()
        hora = reloj_pasadas.WINDOWS.get(dia.weekday())
        if hora is None:
            continue
        candidato = datetime(dia.year, dia.month, dia.day, hora, tzinfo=zona)
        if candidato > local:
            inicio = candidato
            break
    limite = _utc(inicio) - MARGEN_VENTANA
    if limite - now < MINIMO_EJECUCION:
        return None
    return min(limite, now + timedelta(minutes=MINUTOS_EJECUCION))


def paginas_dia(env=None):
    """El tope de páginas del día: HISTORICO_PAGINAS_DIA (la variable del repositorio: la rampa) o PAGINAS_DIA. Lo
    que no se entiende (también vacío: la variable sin poner), el de siempre."""
    texto = str((os.environ if env is None else env).get("HISTORICO_PAGINAS_DIA") or "").strip()
    return int(texto) if texto.isdigit() else PAGINAS_DIA


def cupo_hoy(estado, now, env=None):
    """Las páginas que quedan hoy (Canarias): el tope menos las del día de estado["dia"] si es hoy; nunca negativo."""
    dia = estado.get("dia") or {}
    usadas = int(dia.get("paginas") or 0) if dia.get("fecha") == fecha_de(now) else 0
    return max(0, paginas_dia(env) - usadas)


def freno_del_bot(salud, now):
    """¿El bot en vivo ha esperado hoy el freno en Azure? Con el data-health.json publicado: su checkedAt es de hoy
    en Canarias y su `run` tiene pauses >= 1, cloud "azure" y no refusedRunner (un runner de AWS no es el freno: es
    la federación que no sirve a AWS). Sin fichero, sin `run` o con algo que no se entiende, False: no se para por
    un dato que no se lee."""
    try:
        run = salud.get("run")
        visto = _instante(salud.get("checkedAt"))
        if not isinstance(run, dict) or visto is None or fecha_de(visto) != fecha_de(now):
            return False
        return int(run.get("pauses") or 0) >= 1 and run.get("cloud") == "azure" and not run.get("refusedRunner")
    except (AttributeError, TypeError, ValueError):
        return False


def _freno_hoy(estado, now):
    dia = estado.get("dia") or {}
    return bool(dia.get("freno")) and dia.get("fecha") == fecha_de(now)


# ── Los trabajos ─────────────────────────────────────────────────────────────

_CODIGO = {nombre: codigo for codigo, nombre in SEASON_NAME.items()}


def trabajo(tipo, codigo, lote=None):
    """La clave de un trabajo: «goleadores:2025-2026», «actas:2025-2026:alevin» («siempre», el de benjamín y
    prebenjamín) o «campos»."""
    if tipo == "campos":
        return "campos"
    nombre = SEASON_NAME[str(codigo)]
    if tipo == "actas":
        return f"actas:{nombre}:{lote or 'siempre'}"
    return f"{tipo}:{nombre}"


def _tipo(clave):
    """El tipo de TRABAJOS de una clave: «campos» va con el detalle (lo baja la misma ejecución)."""
    tipo = clave.split(":")[0]
    return "detalle" if tipo == "campos" else tipo


def _temporada(clave):
    """El nombre de la temporada de una clave («2025-2026»), o None («campos»)."""
    partes = clave.split(":")
    return partes[1] if len(partes) > 1 else None


def _lotes(categorias):
    """{lote de actas: [categorías de la web]} de las categorías del plan, en el orden de actas_lotes.LOTES («» es
    el de siempre)."""
    out = {}
    for lote in actas_lotes.lotes_of([DB_NAME[c] for c in categorias]):
        out[lote] = [c for c in categorias if actas_lotes.lote_of(DB_NAME[c]) == lote]
    return out


def trabajos_del_plan(plan):
    """Las claves de los trabajos del encargo, en el orden de TRABAJOS y, dentro, del de plan["temporadas"]. Las
    actas, una por lote de sus categorías; el calendario, solo de las temporadas de plan["calendario"]; «campos»,
    detrás del detalle (las fichas de los campos de sus directorios)."""
    temporadas = list(plan.get("temporadas") or [])
    pedidos = set(plan.get("trabajos") or [])
    out = []
    for tipo in TRABAJOS:
        if tipo == "calendario":
            out += [trabajo(tipo, t) for t in temporadas if t in (plan.get("calendario") or [])]
            continue
        if tipo not in pedidos:
            continue
        for t in temporadas:
            if tipo == "actas":
                out += [trabajo(tipo, t, lote) for lote in _lotes(plan.get("categorias") or [])]
            else:
                out.append(trabajo(tipo, t))
        if tipo == "detalle":
            out.append("campos")
    return out


def _estado_de(estado, clave):
    return ((estado.get("trabajos") or {}).get(clave) or {}).get("estado") or "pendiente"


def _listo(estado, clave, claves):
    """Una fase de un fichero (cuarentena.FAMILIA: escudos y calendario) solo empieza con la anterior del mismo
    fichero promovida: si no, escribiría en la copia de la cuarentena de la anterior antes de probarla. Si la
    anterior no es del encargo ni se ha tocado nunca, sobre lo publicado."""
    anterior = FAMILIA.get(clave.split(":")[0])
    if anterior is None:
        return True
    previa = f"{anterior}:{_temporada(clave)}"
    if _estado_de(estado, previa) == "promovido":
        return True
    return previa not in claves and previa not in (estado.get("trabajos") or {})


def _ultima_prueba(estado, clave):
    pruebas = [p for p in estado.get("pruebas") or [] if clave in (p.get("trabajos") or [])]
    return pruebas[-1] if pruebas else None


def _suelto(estado, clave):
    """¿Su última prueba salió en rojo? Entonces se prueba solo (siguiente): en la prueba que falló iba con otros
    y no se sabe cuál rompía."""
    prueba = _ultima_prueba(estado, clave)
    return bool(prueba) and not prueba.get("verde")


def _a_probar(plan, estado, clave):
    """Completo (sin probar), o «fallo» con su prueba anterior a plan["reintentar_desde"] (reintentar)."""
    est = _estado_de(estado, clave)
    if est == "completo":
        return True
    desde = _instante(plan.get("reintentar_desde"))
    if est != "fallo" or desde is None:
        return False
    prueba = _ultima_prueba(estado, clave)
    hecha = _instante(prueba.get("at")) if prueba else None
    return hecha is None or hecha < desde


def _catalogo():
    if CATALOGO is not None:
        return CATALOGO
    return _leer_json(SCRIPTS / "fiflp_comps_catalog.json") or {}


def rango_competicion(nombre):
    """De más nivel (0) a menos: «PREFERENTE» 0; una Segunda Fase con letra 1 + su posición (A 1, B 2…); otra liga
    (Primera, Fase Previa) 30; lo demás (copas, Campeones, Clausura, eliminatorias, finales) 40. Las actas de las
    ligas de más nivel, primero: si el carril se para a medias, lo que queda es lo que menos dice."""
    n = " ".join(fold(nombre).split())
    if "PREFERENTE" in n:
        return 0
    letra = segunda_fase(n)
    if letra:
        return 1 + ord(letra) - ord("A")
    if re.search(r"\bLIGA\b", n) and not NO_ES_LIGA.search(n):
        return 30
    return 40


def orden_competiciones(comps):
    """Los ids de [(id, nombre)], de más nivel a menos (rango_competicion) y, a igual rango, en su orden."""
    return [c for _, _, c in sorted((rango_competicion(nombre), i, str(c)) for i, (c, nombre) in enumerate(comps))]


def _comps_del_lote(codigo, lote, categorias):
    """Todas las competiciones del catálogo del lote, en orden_competiciones: a las actas se les pasa siempre la
    lista entera del lote (lo pendiente de una tanda cuenta solo las suyas: con una parcial, podría darla por
    completa). Sin catálogo de esa temporada, [] (la tanda las descubre en la web)."""
    cats = tuple(DB_NAME[c] for c in categorias) if lote else DEFAULT_CATEGORIES
    catalogo = _catalogo()
    ids = catalog_comps(codigo, cats, catalog=catalogo)
    nombres = {str(c["id"]): c["name"] for c in (catalogo.get(SEASON_NAME[codigo]) or {}).get("all", [])}
    return orden_competiciones([(i, nombres.get(str(i), "")) for i in ids])


# ── Qué toca ─────────────────────────────────────────────────────────────────

def _nada(motivo):
    return {"accion": "nada", "motivo": motivo}


def siguiente(plan, estado, now, env=None, salud=None):
    """Qué hace la ejecución que empieza `now` (ver el docstring del módulo): nada (con su motivo), probar los
    trabajos completos de una temporada, o descargar el primer tipo de TRABAJOS con algo pendiente y listo."""
    now = _utc(now)
    if not plan:
        return _nada("sin encargo")
    if plan.get("parado"):
        return _nada("parado")
    fin = hasta(now)
    if fin is None:
        return _nada("ventana de partidos")
    claves = trabajos_del_plan(plan)
    if fin - now >= MARGEN_PRUEBA:
        # Una temporada cada vez: si su prueba falla, solo esa se queda fuera. Los campos, con la que toque. Lo
        # que ya falló una prueba (vuelve a probarse porque cambió o por reintentar), solo y al final: si volviera
        # a romper, no se llevaría a «fallo» lo que se prueba con ello.
        probar = [k for k in claves if _a_probar(plan, estado, k)]
        juntos = [k for k in probar if not _suelto(estado, k)]
        campos = ["campos"] if "campos" in juntos else []
        for t in plan.get("temporadas") or []:
            nombre = SEASON_NAME[t]
            suyos = [k for k in juntos if _temporada(k) == nombre]
            if suyos:
                return {"accion": "probar", "trabajos": suyos + campos}
        if campos:
            return {"accion": "probar", "trabajos": campos}
        sueltos = [k for k in probar if _suelto(estado, k)]
        if sueltos:
            return {"accion": "probar", "trabajos": sueltos[:1]}
    cupo = cupo_hoy(estado, now, env)
    if cupo == 0:
        return _nada("tope del día")
    if _freno_hoy(estado, now) or freno_del_bot(salud, now):
        return _nada("freno de verdad hoy")
    pendientes = [k for k in claves if _estado_de(estado, k) == "pendiente" and _listo(estado, k, claves)]
    for tipo in TRABAJOS:
        suyos = [k for k in pendientes if _tipo(k) == tipo]
        if not suyos:
            continue
        categorias = list(plan.get("categorias") or [])
        lote, comps = None, []
        if tipo == "actas":
            suyos = suyos[:1]                     # la primera temporada y lote pendientes
            _, nombre, lote = suyos[0].split(":")
            temporadas = [_CODIGO[nombre]]
            categorias = _lotes(categorias)["" if lote == "siempre" else lote]
            comps = _comps_del_lote(temporadas[0], "" if lote == "siempre" else lote, categorias)
        else:
            temporadas = [_CODIGO[_temporada(k)] for k in suyos if _temporada(k)]
            if not temporadas:
                # Solo quedan las fichas de los campos: una temporada del encargo para la página de competiciones
                # con la que empieza la ejecución (fiflp_carga.preparar); sus grupos ya están hechos.
                temporadas = [plan["temporadas"][0]]
        return {"accion": "descargar", "trabajo": tipo, "temporadas": temporadas, "categorias": categorias,
                "lote": lote, "comps": comps, "partes": suyos, "minutos": (fin - now).total_seconds() / 60,
                "paginas": cupo, "hasta": _iso(fin), "inicio": _iso(now), "dia": fecha_de(now)}
    return _nada("terminado")


def _relativa(path):
    """La carpeta para la orden del descargador (que corre con cwd en la raíz): relativa a la raíz si está dentro
    (scripts/historico), absoluta si no (las pruebas)."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(RAIZ))
    except ValueError:
        return str(path)


def argumentos(accion, resumen):
    """La orden del descargador de la acción (sin el intérprete), con --carpeta (la cuarentena), --max-minutes (el
    plazo, entero por abajo), --max-paginas (lo que queda del día) y --resumen. Las categorías van siempre: las
    actas de alevín sin ellas pararían («la cadena es del lote alevín y las categorías del de siempre»)."""
    tipo = accion["trabajo"]
    temporadas = ",".join(accion["temporadas"])
    categorias = ",".join(accion["categorias"])
    if tipo == "actas":
        args = ["scripts/fetch_fiflp_actas.py", "--temporada", accion["temporadas"][0], "--categorias", categorias,
                "--lote", accion["lote"], "--comps", ",".join(accion.get("comps") or [])]
    elif tipo in ("goleadores", "escudos"):
        args = ["scripts/fetch_fiflp_goleadores.py", "--temporadas", temporadas, "--categorias", categorias,
                "--sin-escudos" if tipo == "goleadores" else "--escudos"]
    elif tipo == "detalle":
        args = ["scripts/fetch_fiflp_detalle.py", "--temporadas", temporadas, "--categorias", categorias,
                "--jornadas", ""]
    elif tipo == "calendario":
        args = ["scripts/fetch_fiflp_detalle.py", "--temporadas", temporadas, "--categorias", categorias,
                "--jornadas", temporadas, "--sin-campos"]
    else:
        raise ValueError(f"trabajo desconocido: {tipo}")
    return args + ["--carpeta", _relativa(carpeta()), "--max-minutes", str(math.floor(accion["minutos"])),
                   "--max-paginas", str(accion["paginas"]), "--resumen", str(resumen)]


# ── Lo que deja cada ejecución ───────────────────────────────────────────────

def _frenar_dia(estado, fecha, quien):
    dia = estado["dia"]
    if dia.get("fecha") != fecha:
        estado["dia"] = dia = {"fecha": fecha, "paginas": 0, "freno": None}
    if not dia.get("freno"):
        dia["freno"] = quien
    if fecha not in estado["dias_frenados"]:
        estado["dias_frenados"] = (estado["dias_frenados"] + [fecha])[-MAX_DIAS_FRENADOS:]


def apuntar_freno_del_bot(estado, salud, now):
    """El estado con el día de hoy parado por el bot en vivo (freno_del_bot), o None si no hay nada que apuntar
    (no frenó, o hoy ya está parado). Así `dias_frenados`, lo que mira la rampa, tiene también los días en que el
    carril no leyó nada por el freno que vio el bot."""
    if not freno_del_bot(salud, now) or _freno_hoy(estado, now):
        return None
    estado = copy.deepcopy(estado)
    _frenar_dia(estado, fecha_de(now), "bot")
    return estado


def _cambiado(previo, actuales):
    """¿Hay en la cuarentena algo distinto de lo que se probó? `actuales`, {nombre: sha1 o None} de los ficheros
    del trabajo en la cuarentena ahora (None: no está); previo["huellas"], los de su última prueba (registrar_prueba).
    Un fichero que no está en la cuarentena no es nada nuevo (tras promover, sale de ella; tras una prueba en rojo,
    se queda con lo mismo). Sin huellas guardadas no se sabe qué se probó: nada nuevo (no se reprueba a ciegas)."""
    guardadas = previo.get("huellas")
    if not isinstance(guardadas, dict):
        return False
    return any(h is not None and h != guardadas.get(n) for n, h in (actuales or {}).items())


def registrar(estado, accion, resumen, now, salud=None, huellas=None):
    """El estado tras una descarga: suma las páginas pedidas al día de accion["dia"] (si es otro que el de
    estado["dia"], empieza uno nuevo), pasa cada parte del resumen a su trabajo (completo o pendiente) y apunta la
    ejecución. Un runner rechazado no cambia ningún trabajo ni gasta el tope del día. Si la federación frenó de
    verdad (parada «freno», o `frenos` > 0: un freno cortado por el tope da parada «tope»), el día queda parado
    («carril») y en dias_frenados; si el bot lo vio hoy (`salud`), también («bot»). Lo que ya estaba «fallo» o
    «promovido» y vuelve entero se queda como estaba (no se prueba otra vez solo), salvo que el contenido de alguno
    de sus ficheros en la cuarentena haya cambiado desde su prueba (`huellas(clave)`, {nombre: sha1 o None}, contra
    las que guardó registrar_prueba: _cambiado). No basta con que el fichero esté: tras una prueba en rojo se queda
    en la cuarentena, y un «fallo» volvería solo a «completo» y se probaría otra vez (los campos, que recorre cada
    descarga del detalle, arrastraban así a cada temporada). Sin resumen (el descargador no llegó a escribirlo), la
    ejecución con "pedidas": None y un aviso."""
    estado = copy.deepcopy(estado)
    estado.setdefault("trabajos", {})
    rechazado = bool(resumen and resumen.get("runner_rechazado"))
    if estado["dia"].get("fecha") != accion.get("dia"):
        estado["dia"] = {"fecha": accion.get("dia"), "paginas": 0, "freno": None}
    if resumen is None:
        print("  ! el descargador no dejó su resumen: la ejecución se apunta sin cuentas")
    elif not rechazado:
        estado["dia"]["paginas"] = int(estado["dia"].get("paginas") or 0) + int(resumen.get("pedidas") or 0)
        for clave, parte in (resumen.get("partes") or {}).items():
            previo = estado["trabajos"].get(clave) or {}
            antes = previo.get("estado")
            nuevo = "completo" if parte.get("completo") else "pendiente"
            if nuevo == "completo" and antes in ("fallo", "promovido") and \
                    not _cambiado(previo, huellas(clave) if huellas else {}):
                nuevo = antes
            # Sobre lo de antes: las huellas de su última prueba no se pierden con una descarga.
            estado["trabajos"][clave] = {**previo, "estado": nuevo, "pendientes": int(parte.get("pendientes") or 0),
                                         "no_disponible": int(parte.get("no_disponible") or 0),
                                         "actualizado": _iso(now)}
        if resumen.get("parada") == "freno" or int(resumen.get("frenos") or 0) > 0:
            _frenar_dia(estado, accion.get("dia"), "carril")
    r = resumen or {}
    estado["ejecuciones"] = (estado["ejecuciones"] + [{
        "inicio": accion.get("inicio"), "fin": _iso(now), "accion": accion.get("accion"),
        "trabajo": accion.get("trabajo"), "temporadas": accion.get("temporadas"), "lote": accion.get("lote"),
        "paginas": accion.get("paginas"), "pedidas": r.get("pedidas") if resumen else None,
        "servidas": r.get("servidas"), "muertas": r.get("muertas"), "esperas": r.get("esperas"),
        "frenos": r.get("frenos"), "frenos_tras": r.get("frenos_tras"), "parada": r.get("parada"),
        "nube": r.get("nube"), "runner_rechazado": rechazado, "relanzada": False}])[-MAX_EJECUCIONES:]
    apuntado = apuntar_freno_del_bot(estado, salud, now)
    return apuntado or estado


def registrar_prueba(estado, trabajos, veredicto, now, huellas=None):
    """El estado tras una prueba: verde, sus trabajos «promovido»; rojo, «fallo» (no se repite sola). La prueba,
    apuntada con su motivo y sus medidas. Con `huellas` (clave → {nombre: sha1 o None} de lo que se probó), cada
    trabajo guarda las suyas: registrar solo lo vuelve a «completo» si la cuarentena trae otra cosa (_cambiado)."""
    estado = copy.deepcopy(estado)
    estado.setdefault("trabajos", {})
    verde = bool(veredicto.get("verde"))
    for clave in trabajos:
        previo = estado["trabajos"].get(clave) or {"pendientes": 0, "no_disponible": 0}
        estado["trabajos"][clave] = {**previo, "estado": "promovido" if verde else "fallo", "actualizado": _iso(now)}
        if huellas:
            estado["trabajos"][clave]["huellas"] = huellas(clave)
    estado["pruebas"] = (estado["pruebas"] + [{
        "at": _iso(now), "trabajos": list(trabajos), "verde": verde, "motivo": veredicto.get("motivo") or "",
        "mb_antes": veredicto.get("mb_antes"), "mb_despues": veredicto.get("mb_despues"),
        "segundos": veredicto.get("segundos")}])[-MAX_PRUEBAS:]
    return estado


def relanzar(resumen, despues, estado):
    """¿Se lanza otra ejecución en seguida? `despues`, siguiente() con el estado ya registrado: nunca si es nada;
    tras una prueba (resumen None), sí; tras un runner rechazado, solo si las ejecuciones rechazadas seguidas al
    final de estado["ejecuciones"] (esta incluida) son como mucho RELANZAR_SI_RUNNER_RECHAZADO (con 0, nunca); tras
    otra descarga, solo si la federación sirvió RELANZAR_MIN páginas. Si no, lo retoma el disparo programado."""
    if despues.get("accion") == "nada":
        return False
    if resumen is None:
        return True
    if resumen.get("runner_rechazado"):
        seguidas = 0
        for ejecucion in reversed(estado.get("ejecuciones") or []):
            if not ejecucion.get("runner_rechazado"):
                break
            seguidas += 1
        return seguidas <= RELANZAR_SI_RUNNER_RECHAZADO
    return int(resumen.get("servidas") or 0) >= RELANZAR_MIN


# ── El encargo ───────────────────────────────────────────────────────────────

def _lista(texto):
    return list(dict.fromkeys(p.strip() for p in str(texto or "").split(",") if p.strip()))


def encargar(plan, temporadas, categorias, trabajos, calendario, now):
    """El plan nuevo (sustituye al de antes; lo ya promovido en el estado no se vuelve a bajar). ValueError si una
    temporada no está en SEASON_NAME, una categoría no existe, un trabajo no está en TRABAJOS, la temporada en curso
    lleva otro trabajo que actas o detalle (sus goleadores y su calendario los lee el bot) o el calendario pide una
    temporada que no está en `temporadas`. Con benjamín o prebenjamín, las dos: comparten el lote de siempre."""
    temporadas, trabajos, calendario = _lista(temporadas), _lista(trabajos), _lista(calendario)
    if not temporadas:
        raise ValueError("sin temporadas")
    for t in temporadas:
        if t not in SEASON_NAME:
            raise ValueError(f"temporada desconocida: {t} (valen {', '.join(SEASON_NAME)})")
    if not trabajos:
        raise ValueError("sin trabajos")
    for tipo in trabajos:
        if tipo not in TRABAJOS:
            raise ValueError(f"trabajo desconocido: {tipo} (valen {', '.join(TRABAJOS)})")
    for t in calendario:
        if t not in temporadas:
            raise ValueError(f"el calendario de {t} no es de una temporada del encargo")
    if "calendario" in trabajos and not calendario:
        raise ValueError("el calendario se pide con sus temporadas (calendario)")
    if EN_CURSO in temporadas and (set(trabajos) - {"actas", "detalle"} or EN_CURSO in calendario):
        raise ValueError("de la temporada en curso solo actas o detalle: sus goleadores y su calendario los lee el bot")
    elegidas = {k for k, v in DB_NAME.items() if v in parse_categories(categorias)}
    if elegidas & {"benjamin", "prebenjamin"}:
        elegidas |= {"benjamin", "prebenjamin"}
    return {"formato": 1, "encargado": _iso(now), "temporadas": temporadas,
            "categorias": [c for c in DB_NAME if c in elegidas],
            "trabajos": [t for t in TRABAJOS if t in trabajos], "calendario": calendario, "parado": False,
            "reintentar_desde": None}


# ── Lo que se lee ────────────────────────────────────────────────────────────

def _miles(n):
    return f"{int(n):,}".replace(",", ".")


def _mb(x):
    return f"{float(x):.1f}".replace(".", ",")


def _corta(nombre):
    """«2025-2026» → «2025-26»."""
    return f"{nombre[:4]}-{nombre[-2:]}" if nombre and len(nombre) == 9 else str(nombre)


def _categorias_legibles(categorias):
    nombres = [NOMBRE_CATEGORIA.get(c, c) for c in categorias]
    return " y ".join(nombres) if len(nombres) == 2 else ", ".join(nombres)


def _lote_legible(lote):
    return "benjamín y prebenjamín" if lote in ("siempre", "", None) else NOMBRE_CATEGORIA.get(lote, lote)


def _etiqueta(clave):
    """«2025-26 · actas alevín», «campos»."""
    partes = clave.split(":")
    if partes[0] == "campos":
        return "campos"
    tipo = "actas " + _lote_legible(partes[2]) if partes[0] == "actas" else partes[0]
    return f"{_corta(partes[1])} · {tipo}"


def _hora(texto, formato):
    momento = _instante(texto)
    return f"{_local(momento):{formato}}" if momento else "?"


def _medidas(prueba):
    if prueba.get("mb_antes") is None or prueba.get("mb_despues") is None:
        return ""
    return (f"de {_mb(prueba['mb_antes'])} a {_mb(prueba['mb_despues'])} MB, "
            f"{float(prueba.get('segundos') or 0):.0f} s")


def _linea_trabajo(estado, clave):
    datos = (estado.get("trabajos") or {}).get(clave)
    est = _estado_de(estado, clave)
    if datos is None:
        return f"{_etiqueta(clave)}: pendiente."
    if est == "promovido":
        prueba = _ultima_prueba(estado, clave)
        if prueba and prueba.get("verde"):
            medidas = _medidas(prueba)
            cuando = f"probado el {_hora(prueba['at'], '%d/%m')} a las {_hora(prueba['at'], '%H:%M')}"
            return f"{_etiqueta(clave)}: en la base ({cuando}{': ' + medidas if medidas else ''})."
        return f"{_etiqueta(clave)}: en la base."
    if est == "fallo":
        prueba = _ultima_prueba(estado, clave)
        motivo = (prueba or {}).get("motivo") or "sin motivo apuntado"
        return f"{_etiqueta(clave)}: la prueba falló ({motivo}); no se reintenta sola."
    no_disp = int(datos.get("no_disponible") or 0)
    if est == "completo":
        return f"{_etiqueta(clave)}: bajado, por probar ({no_disp} no disponible{'' if no_disp == 1 else 's'})."
    return (f"{_etiqueta(clave)}: bajando (quedan {_miles(datos.get('pendientes') or 0)}; {no_disp} no "
            f"disponible{'' if no_disp == 1 else 's'}).")


def _linea_ejecucion(e):
    inicio, fin = e.get("inicio"), e.get("fin")
    if e.get("runner_rechazado"):
        return (f"{_hora(inicio, '%d/%m')} a las {_hora(inicio, '%H:%M')}, runner rechazado (nube: "
                f"{e.get('nube') or '?'}), sin leer nada; se retoma en el próximo disparo (cada 3 h).")
    temporadas = ", ".join(_corta(SEASON_NAME.get(t, t)) for t in e.get("temporadas") or [])
    que = f"{e.get('trabajo')} {temporadas}" + (f" {_lote_legible(e.get('lote'))}" if e.get("lote") else "")
    cuando = f"{_hora(inicio, '%d/%m')} de {_hora(inicio, '%H:%M')} a {_hora(fin, '%H:%M')}"
    if e.get("pedidas") is None:
        return f"{cuando}, {que}: el descargador no dejó su resumen (falló)."
    muertas = int(e.get("muertas") or 0)
    de = f" de {_miles(e['paginas'])}" if e.get("paginas") is not None else ""
    return (f"{cuando}, {que}, {_miles(e.get('servidas') or 0)}{de} páginas servidas ({muertas} "
            f"muerta{'' if muertas == 1 else 's'}), {PARADAS.get(e.get('parada'), e.get('parada'))}.")


def _linea_prueba(p):
    nombres = sorted({_corta(_temporada(k)) for k in p.get("trabajos") or [] if _temporada(k)})
    que = ", ".join(nombres) or "campos"
    resultado = "verde" if p.get("verde") else f"rojo, {p.get('motivo') or 'sin motivo'}"
    medidas = _medidas(p)
    return (f"prueba del {_hora(p.get('at'), '%d/%m')} a las {_hora(p.get('at'), '%H:%M')} ({que}): {resultado}"
            f"{' (' + medidas + ')' if medidas else ''}.")


def linea(estado):
    """Lo último que hizo el carril, en una línea (el asunto del commit «histórico: …»): la última ejecución o la
    última prueba, la más reciente."""
    ejecucion = (estado.get("ejecuciones") or [None])[-1]
    prueba = (estado.get("pruebas") or [None])[-1]
    if ejecucion and (not prueba or (_instante(ejecucion.get("fin")) or datetime.min.replace(tzinfo=timezone.utc))
                      >= (_instante(prueba.get("at")) or datetime.min.replace(tzinfo=timezone.utc))):
        return _linea_ejecucion(ejecucion)
    if prueba:
        return _linea_prueba(prueba)
    return "sin ejecuciones."


def estado_legible(plan, estado, now, env=None):
    """El estado para el registro, el resumen del job y el dueño: el encargo, el día, cada trabajo y la última
    ejecución (y la última prueba)."""
    lineas = []
    if not plan:
        lineas.append("Sin encargo.")
    else:
        trabajos = ", ".join(plan.get("trabajos") or [])
        if plan.get("calendario"):
            trabajos += ", calendario de " + ", ".join(_corta(SEASON_NAME[t]) for t in plan["calendario"])
        lineas.append(f"Encargo del {_hora(plan.get('encargado'), '%d/%m/%Y')}: "
                      f"{_categorias_legibles(plan.get('categorias') or [])}; "
                      f"{', '.join(_corta(SEASON_NAME[t]) for t in plan.get('temporadas') or [])}; {trabajos}."
                      + (" Parado." if plan.get("parado") else ""))
    hoy = f"{_local(_utc(now)):%d/%m/%Y}"
    dia = estado.get("dia") or {}
    if _freno_hoy(estado, now):
        quien = "lo vio el bot en vivo" if dia.get("freno") == "bot" else "lo vio el carril"
        lineas.append(f"Hoy ({hoy}): parado por el freno de verdad ({quien}).")
    else:
        usadas = int(dia.get("paginas") or 0) if dia.get("fecha") == fecha_de(now) else 0
        lineas.append(f"Hoy ({hoy}): {_miles(usadas)} de {_miles(paginas_dia(env))} páginas.")
    if plan:
        lineas += [_linea_trabajo(estado, k) for k in trabajos_del_plan(plan)]
    if estado.get("ejecuciones"):
        lineas.append("Última ejecución: " + _linea_ejecucion(estado["ejecuciones"][-1]))
    if estado.get("pruebas"):
        lineas.append("Última " + _linea_prueba(estado["pruebas"][-1]))
    return "\n".join(lineas)


# ── La orden ─────────────────────────────────────────────────────────────────

def _salida(**valores):
    """Las salidas del paso ($GITHUB_OUTPUT), si lo hay."""
    destino = os.environ.get("GITHUB_OUTPUT")
    if not destino:
        return
    with open(destino, "a", encoding="utf-8") as f:
        for k, v in valores.items():
            f.write(f"{k}={v}\n")


def _sino(valor):
    return "true" if valor else "false"


def _sha1(path):
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _huellas(clave, publicado=False):
    """{nombre: sha1 o None} de los ficheros del trabajo en la cuarentena (None: no está). Con `publicado`, el de
    scripts/ (la carpeta de encima de la cuarentena) si en la cuarentena no está: lo que fue a la copia de la
    prueba, y lo que queda en scripts/ tras promover (registrar --prueba corre después de «Promover»)."""
    try:
        nombres = ficheros(clave)
    except ValueError:
        return {}
    out = {}
    for n in nombres:
        h = _sha1(carpeta() / n) if (carpeta() / n).exists() else None
        if h is None and publicado:
            h = _sha1(carpeta().parent / n)
        out[n] = h
    return out


def _huellas_probadas(clave):
    return _huellas(clave, publicado=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="El carril del histórico (historico.yml)")
    sub = ap.add_subparsers(dest="orden", required=True)
    salud_por_defecto = str(RAIZ / "data-health.json")
    ordenes = {}
    for nombre in ("siguiente", "descargar", "registrar", "encargar", "parar", "reanudar", "reintentar", "estado"):
        ordenes[nombre] = o = sub.add_parser(nombre)
        o.add_argument("--now", default="", help="la hora (ISO), para las pruebas")
        if nombre in ("siguiente", "descargar", "registrar"):
            o.add_argument("--salud", default=salud_por_defecto, help="el data-health.json publicado")
    ordenes["descargar"].add_argument("--accion", required=True)
    ordenes["descargar"].add_argument("--resumen", required=True)
    reg = ordenes["registrar"]
    reg.add_argument("--accion", default="")
    reg.add_argument("--resumen", default="")
    reg.add_argument("--prueba", default="", help="el veredicto de prueba_historico.py")
    reg.add_argument("--trabajos", default="")
    reg.add_argument("--promover", default="", help="cómo acabó el paso «Promover» (success si se promovió)")
    enc = ordenes["encargar"]
    for campo in ("temporadas", "categorias", "trabajos", "calendario"):
        enc.add_argument(f"--{campo}", default="")
    ordenes["estado"].add_argument("--linea", action="store_true", help="solo lo último (el asunto del commit)")
    args = ap.parse_args(argv)
    now = _instante(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        sys.exit(f"--now no se entiende: {args.now}")
    salud = _leer_json(args.salud) if getattr(args, "salud", None) else None

    if args.orden == "encargar":
        try:
            plan = encargar(leer_plan(), args.temporadas, args.categorias, args.trabajos, args.calendario, now)
        except ValueError as ex:
            print(f"El encargo no vale: {ex}", file=sys.stderr)
            return 1
        guardar_plan(plan)
        print(estado_legible(plan, leer_estado(), now))
        return 0
    if args.orden in ("parar", "reanudar", "reintentar"):
        plan = leer_plan()
        if plan is None:
            print("Sin encargo: nada que cambiar.")
            return 0
        if args.orden == "reintentar":
            plan["reintentar_desde"] = _iso(now)
        else:
            plan["parado"] = args.orden == "parar"
        guardar_plan(plan)
        print(estado_legible(plan, leer_estado(), now))
        return 0
    if args.orden == "estado":
        estado = leer_estado()
        print(linea(estado) if args.linea else estado_legible(leer_plan(), estado, now))
        return 0

    plan, estado = leer_plan(), leer_estado()
    if args.orden == "siguiente":
        accion = siguiente(plan, estado, now, salud=salud)
        # El freno del bot, apuntado en el día (y en dias_frenados, lo que mira la rampa) solo si es lo que para al
        # carril: terminado, sin encargo o en una ventana, no hay nada que apuntar (sería un commit al día, siempre).
        apuntado = apuntar_freno_del_bot(estado, salud, now) if accion.get("motivo") == "freno de verdad hoy" else None
        if apuntado is not None:
            guardar_estado(apuntado)
            estado = apuntado
        print(json.dumps(accion, ensure_ascii=False))
        print(estado_legible(plan, estado, now))
        trabajos = accion.get("trabajos") or accion.get("partes") or []
        _salida(accion=accion["accion"], trabajos=",".join(trabajos), motivo=accion.get("motivo", ""),
                apuntado=_sino(apuntado is not None))
        return 0
    if args.orden == "descargar":
        # Otra vez: desde «¿Qué toca?» ha pasado la instalación de Playwright, y el plazo cuenta desde ahora.
        accion = siguiente(plan, estado, now, salud=salud)
        _escribir_json(args.accion, accion)
        if accion["accion"] != "descargar":
            print(f"Nada que descargar: {json.dumps(accion, ensure_ascii=False)}")
            return 0
        Path(args.resumen).unlink(missing_ok=True)      # uno de otra ejecución no se toma por el de esta
        orden = [sys.executable] + argumentos(accion, args.resumen)
        print("Descarga: " + " ".join(orden[1:]), flush=True)
        hecho = subprocess.run(orden, cwd=RAIZ, env={**os.environ, "PYTHONPATH": str(RAIZ)})
        return hecho.returncode

    # registrar
    if args.prueba:
        trabajos = _lista(args.trabajos)
        veredicto = _leer_json(args.prueba)
        if not isinstance(veredicto, dict):
            # La prueba no acabó (cancelada, el plazo del job): rojo, para no repetirla en bucle.
            veredicto = {"verde": False, "motivo": "la prueba no acabó (sin veredicto)"}
        elif veredicto.get("verde") and args.promover != "success":
            veredicto = {**veredicto, "verde": False, "motivo": "no se pudo pasar a scripts/ (cuarentena.py promover)"}
        estado = registrar_prueba(estado, trabajos, veredicto, now, huellas=_huellas_probadas)
        rel = relanzar(None, siguiente(plan, estado, now, salud=salud), estado)
        guardar_estado(estado)
        print(estado_legible(plan, estado, now))
        _salida(relanzar=_sino(rel), promovido=_sino(veredicto.get("verde")))
        return 0
    accion = _leer_json(args.accion) if args.accion else None
    if not isinstance(accion, dict) or accion.get("accion") != "descargar":
        print("Nada que registrar (no se descargó nada).")
        _salida(relanzar="false", promovido="false")
        return 0
    resumen = _leer_json(args.resumen) if args.resumen else None
    resumen = resumen if isinstance(resumen, dict) else None
    estado = registrar(estado, accion, resumen, now, salud=salud, huellas=_huellas)
    # Sin resumen (el descargador falló), como una que no sirvió: no se relanza en seguida.
    rel = relanzar(resumen or {"servidas": 0, "runner_rechazado": False}, siguiente(plan, estado, now, salud=salud),
                   estado)
    estado["ejecuciones"][-1]["relanzada"] = rel
    guardar_estado(estado)
    print(estado_legible(plan, estado, now))
    _salida(relanzar=_sino(rel), promovido="false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
