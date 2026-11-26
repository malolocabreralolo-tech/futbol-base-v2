#!/usr/bin/env python3
"""reloj_pasadas.py — ¿Toca lanzar una pasada del bot (update.yml)? Lo decide el reloj (reloj.yml): cada
~15 min le pasa por la entrada las últimas ejecuciones de update.yml (el JSON de
`gh run list --workflow update.yml --json number,event,status,conclusion,createdAt,startedAt`) y, si toca,
lanza `gh workflow run update.yml --ref main`.

Por qué un reloj y no el cron de update.yml: GitHub pierde o retrasa los cron (más los de las :00), y un
`'23 */2 * * *'` ha llegado a disparar 5 veces de las 13 que tocaban en un día: una pasada cada 4-6 h. Con
un tick cada 15 min y la decisión hecha aquí, perder uno solo retrasa la pasada hasta el siguiente.

Cuándo toca (due): nunca con una ejecución de update.yml sin acabar (en cola, en marcha, esperando…: status
distinto de «completed»), que la siguiente se pondría en fila detrás (concurrency update-data) y otra más
cancelaría la pendiente, gastando un número de pasada sin pasada (update_fiflp.run_number). Si no, cuando no
hay ninguna o desde que empezó la última (cualquier evento: el reloj, una tanda de actas, goleadores o
detalle, una a mano; y cualquier resultado, también fallida o cancelada) han pasado `interval(now)` menos
SLACK. «Empezó»: la más tardía de su createdAt y su startedAt (run_time). Relanzar una ejecución (Re-run)
conserva su createdAt y cambia su startedAt (con solo createdAt, una creada a las 10:08 y relanzada a las
11:30 contaría como de las 10:08, y el tick de las 11:52 lanzaría otra pasada detrás); sin startedAt (o
vacío), la de creación. El relanzamiento de una de hace más de 20 ejecuciones
(--limit de reloj.yml) no se ve: como mucho, una pasada de más en fila detrás de él. Los intervalos:
  - 60 min (WINDOW) en las VENTANAS DE PARTIDOS, hora de Canarias (Atlantic/Canary, con su cambio de
    hora): viernes de 18:00 a 24:00 y sábado y domingo de 10:00 a 24:00. Es cuando se juega: en 2026-27,
    casi dos tercios de los partidos el sábado (sobre todo a las 9 y las 10), casi un cuarto el viernes por
    la tarde (de las 17 a las 19), la mayor parte del resto el domingo por la mañana y entre semana, casi
    ninguno; los de los equipos prioritarios, igual. Cada ventana empieza una hora después de los
    primeros saques (FIRST_KICKOFF + HOT_AFTER): antes, el bot no tiene ningún resultado que buscar
    (update_fiflp.hot_reason calienta un prioritario desde el saque + HOT_AFTER, 60 min);
  - 120 min (BASE) fuera de ellas: update_fiflp.PASS_EVERY, la cadencia base, de la que salen sus turnos,
    priority_slot, los cerrados y los extras (en las ventanas solo se adelantan: van por número de pasada).
SLACK (10 min): un tick que GitHub adelanta o retrasa unos minutos no hace perder una pasada entera (sin él,
una creada a las 10:08 haría esperar a la de las 11:08 hasta el tick de las 11:22).

Sin la base de zonas horarias del sistema (ZoneInfoNotFoundError: en ubuntu-24.04 viene, pero el reloj no
instala tzdata) no hay ventanas: una pasada cada BASE, con un aviso (::warning::) y sin dejar el job en rojo,
que como update.yml no tiene cron, sin reloj no habría ninguna pasada.

El carril de las categorías mayores (due_carril; docs/categorias-mayores.md, «El carril»): infantil, cadete y
juvenil los lee update.yml llamado desde carril-mayores.yml (workflow_call), que tiene su propio número de
pasada (GITHUB_RUN_NUMBER es el del llamante): no gasta números del bot, del que sale su rotación, y por eso sus
ejecuciones no están en la lista de update.yml y la decisión del bot no las cuenta como pasadas (si contaran,
cada una retrasaría hasta 2 h la siguiente del bot). Solo con la variable del repositorio CARRIL_MAYORES a 1
(reloj.yml pasa entonces --carril y --activar; sin ella, ni lista de más ni lanza: due_carril=false). Toca si:
  - no es una ventana de partidos ni falta menos de ANTES_DE_VENTANA (1 h) para que empiece una (el viernes,
    desde las 17:00; el sábado y el domingo, desde las 9:00): el carril no le quita sitio al bot cuando se juega;
    sin la base de zonas horarias, nunca (no se sabe dónde caen);
  - no hay ninguna ejecución sin acabar del bot, del carril, de la activación (activar.yml) ni del histórico
    (historico.yml): los que escriben la base comparten el grupo de concurrencia update-data, GitHub guarda una
    sola ejecución en espera por grupo (una más nueva cancela la que esperaba) y el histórico puede tardar
    horas (y al promover lanza el bot);
  - la última pasada del bot empezó hace entre CARRIL_DESDE y CARRIL_HASTA (25-75 min): ya acabó (~24 min) y
    la siguiente toca a los 110-120, así que el carril (~24 min) acaba antes y no la retrasa;
  - la última del carril empezó hace CARRIL_CADA menos SLACK (3 h 50 min) o más, o no hay ninguna;
  - y no toca la del bot (due): si toca, gana ella.
Como solo cabe en el hueco tras una pasada del bot, y fuera de las ventanas el bot pasa cada 2 h, el carril puede
ir cada 2 h o cada 4 h, no entre medias: cada 4 h, 6 al día de lunes a jueves, 5 el viernes (de 0 a 17 h), 3 el
sábado y el domingo (de 0 a 9 h): 35 a la semana. ~45 grupos × ~4 páginas son ~180 páginas por vuelta (~1,3
pasadas en Azure, ~137 páginas cada una); con la mitad de los runners en AWS (no leen nada), 17-18 pasadas útiles
a la semana, ~2.400 páginas para ~1.500 que hacen falta: margen de 1,6. Con más de 60 grupos, CARRIL_CADA a 2 h
(12 de lunes a jueves, una tras cada pasada del bot); con menos de 25, se puede subir a 6 h.
Y la del bot, con el carril encendido: además de lo de arriba, no toca con una ejecución del carril sin acabar
(`otros`): haría cola tras él en update-data, y otra más en cola cancelaría la que espera. Las acabadas no
cuentan. Con eso, las horas de arranque de las pasadas del bot son las mismas con el carril y sin él
(test_reloj_pasadas.test_semana_con_carril).

El carril del histórico (due_historico; docs/federacion.md, «El carril del histórico»): historico.yml lo lanza el
reloj desde el 25/11/2026, siempre (con o sin CARRIL_MAYORES), en un paso aparte y al final (reloj.yml). Su cron
('47 */3 * * *') GitHub lo perdía como el de update.yml: el 25/11/2026 no llegaron ni el de las 18:47 ni el de las
21:47 UTC, y el carril se quedó parado hasta que se lanzó a mano. Toca si:
  - no es una ventana de partidos: el carril no lee en ellas (historico.hasta), y lanzarlo sería una ejecución que no
    hace nada; sin la base de zonas horarias, nunca (el carril tampoco corre a ciegas);
  - no hay ninguna ejecución sin acabar del histórico (su grupo, historico-federacion, guarda una sola en espera: una
    más nueva cancelaría la que espera, la del paso «Siguiente» con la que se encadena), ni del bot, del carril de
    las mayores o de la activación (`otros`): no arranca con otro leyendo la federación a la vez, ni le quita el
    hueco a una pasada que está en cola;
  - la última del histórico (cualquier evento: el reloj, la que el carril lanza tras de sí, una a mano; y cualquier
    resultado) empezó hace HISTORICO_CADA menos SLACK (1 h 20 min) o más, o no hay ninguna. Tras una ejecución
    servida que no acabó en el freno el carril se relanza solo (paso «Siguiente»), así que el reloj retoma la cadena
    cuando se para (un runner rechazado, el tope del día, el freno). Un intento cada hora y media (≤ 16 al día) desde
    el 26/11/2026; antes, cada 3 h: ese día la federación frenaba a las ~150 páginas, cada ejecución en Azure leía
    300 en 41 min (150, el freno, su espera de 5 min, 150 más, el segundo freno y fin) y, con la mitad de los runners
    en AWS, cada 3 h daban ~1.200 páginas al día entre semana (el histórico entero, ~85.000, en meses). No es
    relanzar para esquivar el freno: cada ejecución lo respeta (lo espera una vez y para), entre una y otra pasa más
    de una hora, cuando el bloqueo (minutos) hace mucho que acabó, y el tope del día (historico.PAGINAS_DIA, 2.000)
    sigue siendo el límite de todo;
  - y en este tick el reloj no lanza ni la pasada del bot ni la del carril (reloj.yml: el paso ni corre): van antes.
Las horas de las pasadas del bot y del carril son las mismas con el histórico y sin él
(test_reloj_pasadas.test_semana_con_historico); con el reloj del PC (test_semana_con_el_reloj_del_pc), el bot no le
espera nunca (el histórico va en otro grupo de concurrencia y puede coincidir con él, a propósito), nunca coincide
con el carril de las mayores, y el carril pasa de 34 a 30-33 pasadas a la semana (un histórico de 41 min le ocupa
a veces su hueco).

Puro y sin dependencias (solo la biblioteca estándar): el reloj corre con el python3 del sistema, sin pip ni
el resto del repositorio (checkout disperso de este fichero). Lo prueban test_reloj_pasadas.py y, el
workflow, test_workflows.py.

Uso: gh run list ... --json ... | python3 scripts/reloj_pasadas.py [--now 2026-10-17T10:00:00Z]
         [--carril carril.json --activar activar.json [--activar historico.json …]]
Escribe la decisión en la salida y, si existe $GITHUB_OUTPUT, «due=true» o «due=false» en él, y «due_carril=…»
(sin --carril, false). --carril es el fichero con las ejecuciones de carril-mayores.yml y cada --activar uno con
las de activar.yml o historico.yml (el mismo JSON de gh run list): van juntos. Una entrada que no es la lista de
ejecuciones (un fallo de gh), en cualquiera de ellos, sale con error y sin escribir nada: el job falla a la
vista y no lanza nada (tampoco la pasada del bot: no se sabría si el carril está en marcha).

El histórico, otro modo (sin leer la entrada estándar, y sin --carril ni --activar):
     python3 scripts/reloj_pasadas.py [--now …] --historico historico.json --otros pasadas.json [--otros …]
--historico, las ejecuciones de historico.yml; cada --otros (uno al menos), las de update.yml, carril-mayores.yml o
activar.yml. Escribe «Carril del histórico: …» y, en $GITHUB_OUTPUT, solo «due_historico=true» o «…=false»; con
una lista que no se lee, lo mismo que arriba (error, sin escribir nada: el paso, en rojo, no lanza nada).
"""
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from zoneinfo import ZoneInfo

LOCAL_ZONE = "Atlantic/Canary"          # la hora de los partidos (update_fiflp.LOCAL_ZONE)
BASE = timedelta(minutes=120)           # fuera de las ventanas (update_fiflp.PASS_EVERY)
WINDOW = timedelta(minutes=60)          # dentro de ellas
SLACK = timedelta(minutes=10)           # lo que puede adelantarse un tick sin perder la pasada
HOT_AFTER = timedelta(minutes=60)       # update_fiflp.HOT_AFTER: un partido de fútbol base dura ~1 h
# Los primeros saques de cada día con partidos (hora de Canarias; weekday: 4 viernes, 5 sábado, 6 domingo).
FIRST_KICKOFF = {4: 17, 5: 9, 6: 9}
# Las ventanas: desde una hora después de los primeros saques hasta las 24:00 de ese día.
WINDOWS = {day: hour + int(HOT_AFTER.total_seconds()) // 3600 for day, hour in FIRST_KICKOFF.items()}
DONE = "completed"                      # el único status de una ejecución acabada (gh run list)
DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
NO_ZONE = "sin ventanas de partidos"
RERUN = timedelta(minutes=1)            # un startedAt más tardío que esto tras su createdAt: un relanzamiento
# El carril de las categorías mayores (carril-mayores.yml, due_carril: arriba).
CARRIL_CADA = timedelta(hours=4)        # una pasada del carril cada 4 h (menos SLACK)
CARRIL_DESDE = timedelta(minutes=25)    # tras el arranque de una pasada del bot: ya ha acabado (~24 min)…
CARRIL_HASTA = timedelta(minutes=75)    # …y el carril (~24 min) acaba antes de la siguiente (110-120 min)
ANTES_DE_VENTANA = timedelta(hours=1)   # ni en una ventana de partidos ni a menos de 1 h de que empiece una
# El carril del histórico (historico.yml, due_historico: arriba).
HISTORICO_CADA = timedelta(minutes=90)  # un intento cada hora y media (menos SLACK); hasta el 26/11/2026, 3 h


def _utc(moment):
    """Un instante con zona (sin zona: UTC)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def local_time(now):
    """La hora de Canarias de un instante (con zona), o None sin la base de zonas horarias del sistema
    (ZoneInfoNotFoundError, un KeyError; o un fichero de zona que no se lee): sin ella no hay ventanas, y
    el reloj sigue con BASE (como update_fiflp.local_time, que cae a UTC)."""
    try:
        return _utc(now).astimezone(ZoneInfo(LOCAL_ZONE))
    except Exception:
        return None


def window(now):
    """La ventana de partidos en la que cae `now` («sábado de 10:00 a 24:00»), o None (también sin la hora de
    Canarias: local_time)."""
    local = local_time(now)
    if local is None:
        return None
    start = WINDOWS.get(local.weekday())
    if start is None or local.hour < start:
        return None
    return f"{DAYS[local.weekday()]} de {start:02d}:00 a 24:00"


def interval(now):
    """Cada cuánto toca una pasada a la hora `now`: WINDOW en las ventanas de partidos y BASE fuera."""
    return WINDOW if window(now) else BASE


def _moment(text):
    return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))


def created_at(run):
    """La hora de creación (UTC) de una ejecución de gh run list; ValueError si no la tiene o no se lee."""
    text = run.get("createdAt") if isinstance(run, dict) else None
    if not isinstance(text, str):
        raise ValueError(f"ejecución sin createdAt: {run!r}")
    return _moment(text)


def started_at(run):
    """La hora (UTC) a la que empezó su último intento (startedAt de gh run list; cambia al relanzarla), o None
    si no la trae (o vacía); ValueError si trae otra cosa."""
    text = run.get("startedAt") if isinstance(run, dict) else None
    if text is None or text == "":
        return None
    if not isinstance(text, str):
        raise ValueError(f"ejecución con un startedAt que no se lee: {run!r}")
    return _moment(text)


def run_time(run):
    """Desde cuándo cuenta una ejecución para el intervalo: la más tardía de su creación y su startedAt (en el
    primer intento, el mismo instante; en un relanzamiento, el del relanzamiento)."""
    return max(t for t in (created_at(run), started_at(run)) if t is not None)


def check_runs(runs):
    """Las ejecuciones tal cual, si son las de gh run list (una lista de objetos con status y createdAt); si
    no, ValueError: mejor un job en rojo que un reloj que decide sobre otra cosa."""
    if not isinstance(runs, list):
        raise ValueError(f"se esperaba la lista de ejecuciones de gh run list, no {type(runs).__name__}")
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("status"), str):
            raise ValueError(f"ejecución sin status: {run!r}")
        run_time(run)
    return runs


def decide(now, runs, otros=()):
    """(¿toca?, por qué) a la hora `now` (UTC), con las ejecuciones de update.yml `runs` (gh run list) y las del
    carril de las mayores `otros` (carril-mayores.yml: solo cuentan las que están sin acabar, que harían cola
    delante en update-data; las acabadas no son pasadas del bot)."""
    runs = check_runs(runs)
    otros = check_runs(list(otros))
    now = _utc(now)
    every = interval(now)
    where = window(now)
    local = local_time(now)
    each = f"una pasada cada {int(every.total_seconds() // 60)} min"
    if local is None:
        head = f"{now:%d/%m/%Y %H:%M} UTC, sin la hora de Canarias (no está la base de zonas horarias): {NO_ZONE}, {each}"
    elif where:
        head = f"{local:%d/%m/%Y %H:%M} en Canarias, ventana de partidos ({where}): {each}"
    else:
        head = f"{local:%d/%m/%Y %H:%M} en Canarias, fuera de las ventanas de partidos: {each}"
    busy = [r for r in runs if r["status"] != DONE]
    if busy:
        r = max(busy, key=run_time)
        return False, f"{head}. No toca: la {r.get('number', '?')} ({r.get('event', '?')}) está {r['status']}."
    lane = [r for r in otros if r["status"] != DONE]
    if lane:
        r = max(lane, key=run_time)
        return False, (f"{head}. No toca: el carril de las categorías mayores está sin acabar (la "
                       f"{r.get('number', '?')} de carril-mayores.yml está {r['status']}).")
    if not runs:
        return True, f"{head}. Toca: no hay ninguna ejecución de update.yml."
    last = max(runs, key=run_time)
    since = now - run_time(last)
    verb = "se relanzó" if run_time(last) - created_at(last) > RERUN else "se creó"
    when = (f"{verb} hace {int(since.total_seconds() // 60)} min" if since >= timedelta(0)
            else f"{verb} después de ahora (¿un reloj atrasado?)")
    ago = f"la última, la {last.get('number', '?')} ({last.get('event', '?')}, {last.get('conclusion') or '-'}), {when}"
    if since >= every - SLACK:
        return True, f"{head}. Toca: {ago}."
    return False, f"{head}. No toca: {ago} (toca a partir de los {int((every - SLACK).total_seconds() // 60)})."


def due(now, runs, otros=()):
    """¿Toca lanzar una pasada a la hora `now` (UTC)? (decide)"""
    return decide(now, runs, otros)[0]


def _minutes(delta):
    return int(delta.total_seconds() // 60)


def due_carril(now, principal, carril, activar):
    """(¿toca una pasada del carril de las mayores?, por qué) a la hora `now` (UTC), con las ejecuciones de
    update.yml (`principal`), de carril-mayores.yml (`carril`) y de activar.yml e historico.yml juntas
    (`activar`), todas de gh run list. Las reglas, arriba (cabecera del módulo)."""
    principal, carril, activar = check_runs(principal), check_runs(carril), check_runs(activar)
    now = _utc(now)
    local = local_time(now)
    if local is None:
        return False, "no toca: sin la hora de Canarias (no está la base de zonas horarias) no se saben las ventanas"
    where = window(now) or window(now + ANTES_DE_VENTANA)
    if where:
        return False, f"no toca: ventana de partidos ({where}) o a menos de {_minutes(ANTES_DE_VENTANA)} min de ella"
    for name, runs in (("update.yml", principal), ("carril-mayores.yml", carril), ("activar.yml o historico.yml", activar)):
        busy = [r for r in runs if r["status"] != DONE]
        if busy:
            r = max(busy, key=run_time)
            return False, f"no toca: la {r.get('number', '?')} de {name} está {r['status']}"
    if due(now, principal, carril):
        return False, "no toca: toca una pasada del bot (va primero)"
    if not principal:
        return False, "no toca: no hay ninguna pasada del bot tras la que entrar"
    last = max(principal, key=run_time)
    since = now - run_time(last)
    if not CARRIL_DESDE <= since <= CARRIL_HASTA:
        return False, (f"no toca: la última pasada del bot, la {last.get('number', '?')}, empezó hace "
                       f"{_minutes(since)} min (el carril entra entre los {_minutes(CARRIL_DESDE)} y los "
                       f"{_minutes(CARRIL_HASTA)})")
    if carril:
        mine = max(carril, key=run_time)
        ago = now - run_time(mine)
        if ago < CARRIL_CADA - SLACK:
            return False, (f"no toca: la última del carril, la {mine.get('number', '?')}, empezó hace "
                           f"{_minutes(ago)} min (toca a partir de los {_minutes(CARRIL_CADA - SLACK)})")
        tail = f"la última del carril, la {mine.get('number', '?')}, empezó hace {_minutes(ago)} min"
    else:
        tail = "no hay ninguna del carril"
    return True, (f"toca: la última pasada del bot, la {last.get('number', '?')}, empezó hace "
                  f"{_minutes(since)} min y {tail}")


def due_historico(now, historico, otros=()):
    """(¿toca lanzar el carril del histórico?, por qué) a la hora `now` (UTC), con las ejecuciones de historico.yml
    (`historico`) y las de update.yml, carril-mayores.yml y activar.yml juntas (`otros`), todas de gh run list. Las
    reglas, arriba (cabecera del módulo)."""
    # Una tupla (la de por defecto), como lista; cualquier otra cosa, a check_runs tal cual (un {} no es «ninguna»).
    historico, otros = check_runs(historico), check_runs(list(otros) if isinstance(otros, tuple) else otros)
    now = _utc(now)
    if local_time(now) is None:
        return False, ("no toca: sin la hora de Canarias (no está la base de zonas horarias) no se saben las "
                       "ventanas, y el carril no corre a ciegas")
    where = window(now)
    if where:
        return False, f"no toca: ventana de partidos ({where}), en la que el carril no lee"
    for name, runs in (("historico.yml", historico), ("update.yml, carril-mayores.yml o activar.yml", otros)):
        busy = [r for r in runs if r["status"] != DONE]
        if busy:
            r = max(busy, key=run_time)
            return False, f"no toca: la {r.get('number', '?')} de {name} está {r['status']}"
    if not historico:
        return True, "toca: no hay ninguna ejecución de historico.yml"
    last = max(historico, key=run_time)
    ago = now - run_time(last)
    mine = f"la última, la {last.get('number', '?')} ({last.get('event', '?')}, {last.get('conclusion') or '-'})"
    if ago < HISTORICO_CADA - SLACK:
        when = f"empezó hace {_minutes(ago)} min" if ago >= timedelta(0) else "empezó después de ahora (¿un reloj atrasado?)"
        return False, f"no toca: {mine} {when} (toca a partir de los {_minutes(HISTORICO_CADA - SLACK)})"
    return True, f"toca: {mine} empezó hace {_minutes(ago)} min"


USO = ("uso: reloj_pasadas.py [--now FECHA_ISO] [--carril carril.json --activar activar.json "
       "[--activar historico.json …]] < ejecuciones.json\n"
       "     reloj_pasadas.py [--now FECHA_ISO] --historico historico.json --otros pasadas.json [--otros …]")


def _args(argv):
    """{'now': texto o None, 'carril': fichero o None, 'activar': [ficheros], 'historico': fichero o None, 'otros':
    [ficheros]}, o None si no se entiende (sin argparse, que sale con SystemExit: main devuelve 2). --carril y
    --activar van juntos; --historico, con un --otros al menos y sin ninguno de los dos."""
    out = {"now": None, "carril": None, "activar": [], "historico": None, "otros": []}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag not in ("--now", "--carril", "--activar", "--historico", "--otros") or i + 1 >= len(argv):
            return None
        value = argv[i + 1]
        if flag in ("--activar", "--otros"):
            out[flag[2:]].append(value)
        elif out[flag[2:]] is not None:
            return None
        else:
            out[flag[2:]] = value
        i += 2
    if (out["carril"] is None) != (not out["activar"]):
        return None
    if (out["historico"] is None) != (not out["otros"]):
        return None
    if out["historico"] is not None and out["carril"] is not None:
        return None
    return out


def _read_runs(path):
    """Las ejecuciones de un fichero de gh run list; ValueError si no está o no se lee."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise ValueError(f"{path}: {e}") from e


def main(argv=None, stdin=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    args = _args(argv)
    if args is None:
        print(USO, file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    if args["now"] is not None:
        now = _utc(datetime.fromisoformat(args["now"].replace("Z", "+00:00")))
    if args["historico"] is not None:
        return _main_historico(now, args, env)
    lane = None
    try:
        runs = json.load(stdin or sys.stdin)
        if args["carril"] is not None:
            carril = _read_runs(args["carril"])
            activar = []
            for path in args["activar"]:          # activar.yml e historico.yml, juntas
                activar += check_runs(_read_runs(path))
            ok, why = decide(now, runs, carril)
            lane = due_carril(now, runs, carril, activar)
        else:
            ok, why = decide(now, runs)
    except ValueError as e:                     # json.JSONDecodeError también es un ValueError
        print(f"reloj_pasadas: no se puede decidir ({e}): no se lanza nada.", file=sys.stderr)
        return 1
    print(why)
    if lane is not None:
        print(f"Carril de las categorías mayores: {lane[1]}.")
    if local_time(now) is None:
        print(f"::warning::reloj_pasadas: no está la zona {LOCAL_ZONE} (la base de zonas horarias del sistema): "
              f"{NO_ZONE}, una pasada cada {int(BASE.total_seconds() // 60)} min.")
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"due={'true' if ok else 'false'}\n")
            f.write(f"due_carril={'true' if lane and lane[0] else 'false'}\n")
    return 0


def _main_historico(now, args, env):
    """El modo del histórico (el paso «¿Toca el histórico?» de reloj.yml): sin la entrada estándar; solo
    due_historico en $GITHUB_OUTPUT."""
    try:
        historico = _read_runs(args["historico"])
        otros = []
        for path in args["otros"]:              # update.yml, carril-mayores.yml y activar.yml, juntas
            otros += check_runs(_read_runs(path))
        ok, why = due_historico(now, historico, otros)
    except ValueError as e:                     # json.JSONDecodeError también es un ValueError
        print(f"reloj_pasadas: no se puede decidir ({e}): no se lanza nada.", file=sys.stderr)
        return 1
    print(f"Carril del histórico: {why}.")
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"due_historico={'true' if ok else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
