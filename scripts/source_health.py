"""Publish source-check timestamps separately from changes to sporting data."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from categorias import carril_actual
from escritura import escribir_atomico
from portal_config import load_config

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data-health.json"
# Sin cambios con significado, el informe solo se reescribe una vez al día:
# reescribirlo en cada ejecución (cada ~5 h) generaba un commit y un despliegue
# de Pages solo para mover la hora de comprobación.
HEARTBEAT = timedelta(hours=24)
# Lo que cambia en cada pasada sin que un visitante vea nada distinto: la hora de la comprobación y
# las notas de la pasada del bot de la federación (rotación, grupos que descansan, tiempos). Las notas de los
# otros carriles (carriles.<carril>.run), también: CARRIL_VOLATILE.
VOLATILE = ("checkedAt", "run")
CARRIL_VOLATILE = ("run",)
# Los carriles del bot (categorias.CARRILES, parte E1). El principal, el de siempre, guarda su veredicto y sus
# notas donde siempre (runHealth y run: la web, el histórico y las alarmas los leen ahí); los demás, cada uno en
# carriles.<carril> = {"runHealth": …, "run": …}, con la misma forma. Así una pasada del carril de mayores seca,
# cortada o en un runner que la federación no sirve (AWS) no pone drySince ni un rojo en lo del bot de siempre,
# ni al revés; y mientras un carril no ha corrido nunca, su clave no existe (el informe del bot de siempre tiene
# la forma de antes).
PRINCIPAL = "principal"
# Y en cada grupo: la hora de su comprobación.
GROUP_VOLATILE = ("checkedAt",)
# El motivo de runHealth de una ejecución que falla tras la pasada (finish(failed=True)).
INTERRUPTED = "la pasada se interrumpió antes de terminar"
_report = None
_previous = None
# Los grupos cuya hora de comprobación se publica aunque no cambie nada más (record(publish_time=True)): los
# prioritarios del bot de la federación, a los que les vuelve a tocar según ella (update_fiflp.plan_groups).
_timed = set()


def _stamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _read_previous():
    try:
        return json.loads(REPORT_PATH.read_text())
    except (OSError, ValueError):
        return {}


def begin(season):
    global _report, _previous, _timed
    _previous = _read_previous()
    _timed = set()
    _report = {"version": 1, "season": season, "groups": {},
               "nextSeason": _previous.get("nextSeason", {"name": load_config()["nextSeason"], "status": "pending"})}
    _carry_new()
    _carry_run_health()
    _carry_carriles(_carril())
    _carry_activation()
    _carry_base()


def _carril():
    """El carril de esta ejecución (categorias.carril_actual, por FIFLP_CATS). Unas categorías que mezclan
    carriles son del principal aquí, como antes de los carriles: update_fiflp.update_groups para con
    ValueError, y la ejecución fallida se marca donde siempre."""
    try:
        return carril_actual()
    except ValueError:
        return PRINCIPAL


def _lane(report, carril, create=True):
    """La parte de `report` de un carril: el informe mismo para el principal (runHealth y run) o
    report["carriles"][carril] (creada con `create`; sin ella, {} si no la hay)."""
    if carril == PRINCIPAL:
        return report
    if not create:
        lanes = report.get("carriles") if isinstance(report, dict) else None
        lane = lanes.get(carril) if isinstance(lanes, dict) else None
        return lane if isinstance(lane, dict) else {}
    lanes = report.setdefault("carriles", {})
    return lanes.setdefault(carril, {})


def _same_season():
    return bool(_report and _previous and _previous.get("season") == _report["season"])


# Lo nuevo de la federación que la web aún no tiene: las competiciones (update_fiflp.check_competitions) y
# los grupos nuevos de las que ya sigue (update_fiflp.new_groups). Con significado: reescriben el informe.
NEW_KEYS = ("newCompetitions", "newGroups")


def _carry_new():
    """Las competiciones y los grupos nuevos siguen hasta que el bot vuelva a leer su desplegable (sin
    federación en esta pasada o si falla la lectura, se quedan); con otra temporada, fuera."""
    for key in NEW_KEYS:
        items = _previous.get(key) if _same_season() else None
        if isinstance(items, list) and items:
            _report[key] = items


def _carry_run_health():
    """El veredicto de la última pasada sigue mientras nadie lo cambie: una ejecución sin federación
    (FIFLP_UPDATE sin poner) no lo juzga. Con otra temporada, fuera."""
    health = _previous.get("runHealth") if _same_season() else None
    if isinstance(health, dict):
        _report["runHealth"] = dict(health)


def _carry_carriles(current):
    """Lo de los otros carriles sigue tal cual: su veredicto y sus notas (carriles.<carril>, y el `run` del
    principal en una pasada de otro carril), que solo los cambia una pasada de ese carril. El `run` del carril de
    esta pasada no se arrastra, como el del principal hasta ahora: lo pone su note_run. Con otra temporada,
    fuera, como runHealth."""
    if not _same_season():
        return
    lanes = _previous.get("carriles")
    out = {}
    for name, entry in (lanes.items() if isinstance(lanes, dict) else ()):
        if isinstance(entry, dict):
            keep = {k: v for k, v in entry.items() if not (name == current and k == "run")}
            if keep:
                out[name] = keep
    if out:
        _report["carriles"] = out
    if current != PRINCIPAL and isinstance(_previous.get("run"), dict):
        _report["run"] = _previous["run"]


def _carry_activation():
    """La última activación automática (activar_auto.py, que la escribe en el fichero del disco) sigue tal
    cual entre pasadas: lo que no se pudo cargar se ve en «Datos y fuentes» y su `tried` frena los
    reintentos. Con otra temporada, fuera."""
    activation = _previous.get("activation") if _same_season() else None
    if isinstance(activation, dict):
        _report["activation"] = activation


def _carry_base():
    """El tamaño de la base (`base`, de set_base) sigue tal cual: solo set_base lo pone y lo quita, y la base no
    cambia de tamaño con la temporada."""
    base = _previous.get("base")
    if isinstance(base, dict):
        _report["base"] = base


# El aviso de tamaño de la base (base_sana.py --salud): en MiB, como GitHub, que no admite ficheros de 100.
MB = 1024 * 1024
GITHUB_MB = 100


def set_base(bytes_, aviso, path=None):
    """Con aviso, `base: {"mb": <entero>, "limite": 100}` en el informe del disco (`path`; sin él, REPORT_PATH);
    sin aviso, quita la clave. No toca nada más ni reescribe el fichero si no cambia."""
    path = Path(path) if path is not None else REPORT_PATH
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    if aviso:
        new = {**report, "base": {"mb": int(bytes_) // MB, "limite": GITHUB_MB}}
    else:
        new = {k: v for k, v in report.items() if k != "base"}
    if new == report:
        return
    escribir_atomico(path, json.dumps(new, ensure_ascii=False, indent=2) + "\n")


def _red(previous, reasons, now=None):
    """runHealth en rojo con `reasons`; `since`, el de `previous` si ya estaba en rojo (cuándo empezó)."""
    since = previous.get("since") if isinstance(previous, dict) and previous.get("ok") is False else None
    return {"ok": False, "reasons": list(reasons), "since": since or _stamp(now)}


def _previous_health(carril=PRINCIPAL):
    """El runHealth de `carril` en el informe anterior de la misma temporada, o None."""
    health = _lane(_previous or {}, carril, create=False).get("runHealth") if _same_season() else None
    return health if isinstance(health, dict) else None


def dry_since(carril=PRINCIPAL):
    """Desde cuándo dura la racha de pasadas secas (pasada_sana.seca) de `carril`, según el informe anterior de
    la misma temporada: su runHealth.drySince, o None."""
    health = _previous_health(carril)
    since = health.get("drySince") if isinstance(health, dict) else None
    return since if isinstance(since, str) and since else None


def set_run_health(reasons, now=None, dry=False, carril=PRINCIPAL):
    """El veredicto de la pasada del bot de la federación (pasada_sana.veredicto: sin motivos, sana), en la parte
    de `carril` (runHealth el principal; carriles.<carril>.runHealth los demás). Sana, sin hora: una pasada sana
    tras otra sana no reescribe el informe (runHealth no es VOLATILE). Con `dry` (una pasada seca), drySince: el
    de la racha en curso de ese carril o, en la primera, ahora; la primera seca reescribe el informe, las
    siguientes de la racha no, y la primera que lee algo lo quita."""
    if _report is None:
        return
    previous = _previous_health(carril)
    health = _red(previous, reasons, now) if reasons else {"ok": True}
    if dry:
        health["drySince"] = dry_since(carril) or _stamp(now)
    _lane(_report, carril)["runHealth"] = health


def new_competitions():
    """[{id, name, firstSeen}]: las competiciones de la federación que la temporada no tiene."""
    return list((_report or {}).get("newCompetitions") or [])


def set_new_competitions(items):
    """Las que acaba de ver update_fiflp.check_competitions (vacía: ninguna)."""
    if _report is None:
        return
    if items:
        _report["newCompetitions"] = list(items)
    else:
        _report.pop("newCompetitions", None)


def new_groups():
    """[{competition, competitionName, id, name, firstSeen}]: los grupos de la federación de competiciones
    que la temporada ya sigue y que la temporada no tiene."""
    return list((_report or {}).get("newGroups") or [])


def set_new_groups(items):
    """Los que acaba de calcular update_fiflp.new_groups al final de la pasada (vacía: ninguno)."""
    if _report is None:
        return
    if items:
        _report["newGroups"] = list(items)
    else:
        _report.pop("newGroups", None)


def previous_groups():
    """Las comprobaciones publicadas de la temporada en curso ({código: entrada}): el bot de la
    federación vuelve a mirar un grupo cerrado cuya última comprobación falló o que no tiene ninguna
    (update_fiflp.plan_groups). Su orden no depende de ellas: no siempre se suben."""
    groups = (_previous or {}).get("groups") if _same_season() else None
    return dict(groups) if isinstance(groups, dict) else {}


def record(code, url, status, message="", now=None, publish_time=False):
    """La comprobación de un grupo. Su hora (checkedAt) no reescribe el informe por sí sola (VOLATILE), salvo
    con `publish_time`: los prioritarios del bot de la federación, a los que les vuelve a tocar según la hora
    de su última comprobación publicada (update_fiflp.plan_groups; sin publicarla, la pasada siguiente los
    leería otra vez, en cada pasada)."""
    if _report is None:
        return
    _report["groups"][code] = {
        "url": url, "status": status, "message": str(message)[:350],
        "checkedAt": _stamp(now),
    }
    if publish_time:
        _timed.add(code)


def carry(code, url=None):
    """El grupo no se comprobó en esta pasada (rotación del bot de la federación, un cerrado que
    descansa, o de una categoría que este workflow no lee: FIFLP_CATS): su última comprobación sigue
    como estaba, sin marcarlo como error. Sin comprobación anterior en la temporada (o, con `url`,
    con otra URL: otro grupo con el mismo código), nada: todavía no sale."""
    if _report is None:
        return
    entry = previous_groups().get(code)
    if isinstance(entry, dict) and (url is None or entry.get("url") == url):
        _report["groups"][code] = dict(entry)


def note_run(info, carril=PRINCIPAL):
    """Las notas de la pasada del bot, en la parte de `carril` (run; carriles.<carril>.run). Volátiles
    (VOLATILE, CARRIL_VOLATILE): no reescriben el informe por sí solas."""
    if _report is not None:
        _lane(_report, carril)["run"] = info


def meaningful(report):
    """The report without its check timestamps: what a visitor would see change."""
    view = {k: v for k, v in report.items() if k not in VOLATILE}
    if isinstance(view.get("carriles"), dict):
        view["carriles"] = {name: ({k: v for k, v in entry.items() if k not in CARRIL_VOLATILE}
                                   if isinstance(entry, dict) else entry)
                            for name, entry in view["carriles"].items()}
    view["groups"] = {code: {k: v for k, v in (group or {}).items() if k not in GROUP_VOLATILE}
                      for code, group in (report.get("groups") or {}).items()}
    return view


def _is_recent(report, now):
    try:
        checked = datetime.fromisoformat(report["checkedAt"])
    except (KeyError, TypeError, ValueError):
        return False
    return now - checked < HEARTBEAT


def _discard_checks():
    """Las comprobaciones correctas de una ejecución que falla, fuera: cada grupo «ok» vuelve a su entrada
    anterior (como carry; sin ella, o con otra URL, sin entrada). update.yml no publica los datos de una
    ejecución fallida («Publicar diagnóstico si la fuente o las pruebas fallan»: solo data-health.json, sin
    la base), así que su «ok» con la hora nueva diría leído lo que no se ha publicado; y la hora de los
    prioritarios (_timed) decide cuándo les toca (update_fiflp.plan_groups): con ella, la pasada siguiente
    los daría por al día y no los releería hasta su turno (hasta ~6 h). Los errores y los rechazos se
    quedan: son el diagnóstico."""
    previous = previous_groups()
    for code, entry in list(_report["groups"].items()):
        if not isinstance(entry, dict) or entry.get("status") != "ok":
            continue
        before = previous.get(code)
        if isinstance(before, dict) and before.get("url") == entry.get("url"):
            _report["groups"][code] = dict(before)
        else:
            del _report["groups"][code]
    _timed.clear()


def finish(now=None, failed=False):
    """Escribe data-health.json si cambia algo con significado, si cambia la hora de un prioritario (_timed)
    o si la última tiene más de un día (HEARTBEAT). Con `failed` (la ejecución falló: fetch_futbolaspalmas.main
    lo pasa desde su finally), sin sus comprobaciones correctas (_discard_checks)."""
    if _report is None:
        return
    now = now or datetime.now(timezone.utc)
    if failed:
        _discard_checks()
        # Lo publicado de una ejecución fallida es el diagnóstico: en rojo, si la pasada no lo estaba ya, la de
        # su carril (la de otro no se ha juzgado). La racha seca, como estaba: la interrupción no dice si la
        # federación sirve o no.
        carril = _carril()
        health = _lane(_report, carril, create=False).get("runHealth") or {}
        if health.get("ok") is not False:
            set_run_health([INTERRUPTED], now, carril=carril)
            if health.get("drySince"):
                _lane(_report, carril)["runHealth"]["drySince"] = health["drySince"]
    _report["checkedAt"] = _stamp(now)
    text = (ROOT / "index.html").read_text()
    match = re.search(r"Última actualización: (\d{2})/(\d{2})/(\d{4})", text)
    if match:
        day, month, year = match.groups()
        _report["lastDataChange"] = f"{year}-{month}-{day}"
    # La versión de los datos publicados (?v= que generate_js.py solo sube
    # cuando cambia algún data-*.js): si cambia, el informe acompaña al commit.
    version = re.search(r"data-seasons\.js\?v=([0-9a-z]+)", text)
    if version:
        _report["dataVersion"] = version.group(1)
    _report["summary"] = {status: sum(g["status"] == status for g in _report["groups"].values())
                          for status in ["ok", "rejected", "error"]}
    before = (_previous or {}).get("groups") or {}
    timed = any(_report["groups"].get(code, {}).get("checkedAt") != (before.get(code) or {}).get("checkedAt")
                for code in _timed)
    if not timed and meaningful(_report) == meaningful(_previous or {}) and _is_recent(_previous, now):
        return
    escribir_atomico(REPORT_PATH, json.dumps(_report, ensure_ascii=False, indent=2) + "\n")


# Cuándo vuelve a lanzar el bot activar.yml (update.yml, «Lanzar la activación si hay algo nuevo», con
# pending_activation). Una descarga incompleta, en la pasada siguiente, hasta MAX_ATTEMPTS intentos (cada uno
# descarga 20 min: pasadas e intentos se alternan); lo que no se arregla solo, una vez al día (RETRY_AFTER).
RETRY_AFTER = timedelta(hours=24)
MAX_ATTEMPTS = 8
# El principio de los motivos de descarga incompleta de activar_auto.py (DESCARGA): los únicos que se reanudan.
INCOMPLETE = "la descarga no está completa"


def _pending_ids(report):
    ids = set()
    for key, field in (("newCompetitions", "id"), ("newGroups", "competition")):
        items = report.get(key)
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get(field) or "").isdigit():
                ids.add(str(item[field]))
    return ids


def _old(activation, now):
    """¿El intento (activation.at) es de hace RETRY_AFTER o más? Sin una hora que valga no se sabe: sí."""
    try:
        at = datetime.fromisoformat(str(activation.get("at")))
        return (now or datetime.now(timezone.utc)) - at >= RETRY_AFTER
    except (TypeError, ValueError):
        return True


def pending_activation(report, now=None):
    """Las competiciones pendientes (ids de newCompetitions y newGroups, ordenados y sin repetir) si el bot tiene
    que lanzar activar.yml, o [] si no:
      - alguna no está en activation.tried: ya;
      - todas lo están y todos los fallos de las pendientes son de descarga incompleta: ya, si
        activation.attempts < MAX_ATTEMPTS (el intento siguiente reanuda la descarga);
      - si no (otro motivo, o MAX_ATTEMPTS intentos de descarga): cuando activation.at tenga RETRY_AFTER."""
    report = report if isinstance(report, dict) else {}
    ids = _pending_ids(report)
    if not ids:
        return []
    activation = report.get("activation")
    if not isinstance(activation, dict) or not isinstance(activation.get("tried"), list):
        return sorted(ids)
    if ids - {str(comp) for comp in activation["tried"]}:
        return sorted(ids)
    failed = activation.get("failed") if isinstance(activation.get("failed"), list) else []
    reasons = [str(f.get("reason") or "") for f in failed if isinstance(f, dict) and str(f.get("competition")) in ids]
    attempts = activation.get("attempts")
    attempts = attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else 0
    if reasons and all(r.startswith(INCOMPLETE) for r in reasons) and attempts < MAX_ATTEMPTS:
        return sorted(ids)
    return sorted(ids) if _old(activation, now) else []


def main(argv=None, now=None):
    """Las órdenes sobre data-health.json del disco (update.yml, después del commit):
      veredicto         sale con 1, e imprime los motivos, si la última pasada está en rojo (runHealth.ok
                        falso); con 0 si es sana o no hay veredicto;
      marcar "<motivo>" pone runHealth en rojo con ese motivo (con `since` y los motivos de antes si ya lo
                        estaba) y escribe el fichero, sin tocar nada más del informe;
    las dos, las del carril del job (FIFLP_CATS, categorias.carril_actual): con el de mayores, su
    carriles.mayores.runHealth, y nada del bot de siempre;
      pendiente         sale con 0, e imprime sus ids separados por comas, si update.yml tiene que lanzar
                        activar.yml para las competiciones y grupos nuevos (pending_activation); con 1 si no."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["pendiente"]:
        ids = pending_activation(_read_previous(), now)
        if ids:
            print(",".join(ids))
            return 0
        return 1
    if args == ["veredicto"]:
        health = _lane(_read_previous(), _carril(), create=False).get("runHealth")
        if isinstance(health, dict) and health.get("ok") is False:
            for reason in health.get("reasons") or ["sin motivo"]:
                print(f"Pasada en rojo: {reason}")
            return 1
        return 0
    if len(args) == 2 and args[0] == "marcar":
        report = _read_previous()
        lane = _lane(report, _carril())
        health = lane.get("runHealth")
        before = list(health.get("reasons") or []) if isinstance(health, dict) and health.get("ok") is False else []
        lane["runHealth"] = _red(health, before + [args[1]] if args[1] not in before else before)
        if isinstance(health, dict) and health.get("drySince"):
            lane["runHealth"]["drySince"] = health["drySince"]
        escribir_atomico(REPORT_PATH, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 0
    print('uso: source_health.py veredicto | marcar "<motivo>" | pendiente', file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
