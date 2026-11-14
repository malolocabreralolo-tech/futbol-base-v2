"""Publish source-check timestamps separately from changes to sporting data."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from portal_config import load_config

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data-health.json"
# Sin cambios con significado, el informe solo se reescribe una vez al día:
# reescribirlo en cada ejecución (cada ~5 h) generaba un commit y un despliegue
# de Pages solo para mover la hora de comprobación.
HEARTBEAT = timedelta(hours=24)
# Lo que cambia en cada pasada sin que un visitante vea nada distinto: la hora de la comprobación y
# las notas de la pasada del bot de la federación (rotación, grupos que descansan, tiempos).
VOLATILE = ("checkedAt", "run")
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
    _carry_activation()


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


def _carry_activation():
    """La última activación automática (activar_auto.py, que la escribe en el fichero del disco) sigue tal
    cual entre pasadas: lo que no se pudo cargar se ve en «Datos y fuentes» y su `tried` frena los
    reintentos. Con otra temporada, fuera."""
    activation = _previous.get("activation") if _same_season() else None
    if isinstance(activation, dict):
        _report["activation"] = activation


def _red(previous, reasons, now=None):
    """runHealth en rojo con `reasons`; `since`, el de `previous` si ya estaba en rojo (cuándo empezó)."""
    since = previous.get("since") if isinstance(previous, dict) and previous.get("ok") is False else None
    return {"ok": False, "reasons": list(reasons), "since": since or _stamp(now)}


def dry_since():
    """Desde cuándo dura la racha de pasadas secas (pasada_sana.seca), según el informe anterior de la misma
    temporada: su runHealth.drySince, o None."""
    health = (_previous or {}).get("runHealth") if _same_season() else None
    since = health.get("drySince") if isinstance(health, dict) else None
    return since if isinstance(since, str) and since else None


def set_run_health(reasons, now=None, dry=False):
    """El veredicto de la pasada del bot de la federación (pasada_sana.veredicto: sin motivos, sana). Sana,
    sin hora: una pasada sana tras otra sana no reescribe el informe (runHealth no es VOLATILE). Con `dry`
    (una pasada seca), drySince: el de la racha en curso o, en la primera, ahora; la primera seca reescribe
    el informe, las siguientes de la racha no, y la primera que lee algo lo quita."""
    if _report is None:
        return
    previous = (_previous or {}).get("runHealth") if _same_season() else None
    health = _red(previous, reasons, now) if reasons else {"ok": True}
    if dry:
        health["drySince"] = dry_since() or _stamp(now)
    _report["runHealth"] = health


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


def note_run(info):
    """Las notas de la pasada del bot (VOLATILE: no reescriben el informe por sí solas)."""
    if _report is not None:
        _report["run"] = info


def meaningful(report):
    """The report without its check timestamps: what a visitor would see change."""
    view = {k: v for k, v in report.items() if k not in VOLATILE}
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
    los daba por al día y no los releía hasta su turno (hasta ~6 h; antes del 16/10/2026 se releían en
    todas). Los errores y los rechazos se quedan: son el diagnóstico."""
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
        # Lo publicado de una ejecución fallida es el diagnóstico: en rojo, si la pasada no lo estaba ya.
        # La racha seca, como estaba: la interrupción no dice si la federación sirve o no.
        health = _report.get("runHealth") or {}
        if health.get("ok") is not False:
            set_run_health([INTERRUPTED], now)
            if health.get("drySince"):
                _report["runHealth"]["drySince"] = health["drySince"]
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
    REPORT_PATH.write_text(json.dumps(_report, ensure_ascii=False, indent=2) + "\n")


# Lo que activar.yml ya intentó (activation.tried) no se vuelve a lanzar desde el bot hasta pasado este rato:
# una activación que falla por algo que no se arregla solo no se relanza en cada pasada.
RETRY_AFTER = timedelta(hours=6)


def pending_activation(report, now=None):
    """Las competiciones (ids, ordenados y sin repetir) de newCompetitions y newGroups que activar.yml tendría
    que intentar: las que no están en activation.tried de un intento de hace menos de RETRY_AFTER."""
    report = report if isinstance(report, dict) else {}
    ids = set()
    for key, field in (("newCompetitions", "id"), ("newGroups", "competition")):
        items = report.get(key)
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get(field) or "").isdigit():
                ids.add(str(item[field]))
    activation = report.get("activation")
    if isinstance(activation, dict) and isinstance(activation.get("tried"), list):
        try:
            at = datetime.fromisoformat(str(activation.get("at")))
            recent = (now or datetime.now(timezone.utc)) - at < RETRY_AFTER
        except (TypeError, ValueError):
            recent = False                  # sin una hora que valga no se sabe cuándo fue: no frena
        if recent:
            ids -= {str(comp) for comp in activation["tried"]}
    return sorted(ids)


def main(argv=None, now=None):
    """Las órdenes sobre data-health.json del disco (update.yml, después del commit):
      veredicto         sale con 1, e imprime los motivos, si la última pasada está en rojo (runHealth.ok
                        falso); con 0 si es sana o no hay veredicto;
      marcar "<motivo>" pone runHealth en rojo con ese motivo (con `since` y los motivos de antes si ya lo
                        estaba) y escribe el fichero, sin tocar nada más del informe;
      pendiente         sale con 0, e imprime sus ids separados por comas, si hay competiciones o grupos
                        nuevos que activar.yml no haya intentado en las últimas 6 h (pending_activation);
                        con 1 si no hay nada que lanzar."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["pendiente"]:
        ids = pending_activation(_read_previous(), now)
        if ids:
            print(",".join(ids))
            return 0
        return 1
    if args == ["veredicto"]:
        health = _read_previous().get("runHealth")
        if isinstance(health, dict) and health.get("ok") is False:
            for reason in health.get("reasons") or ["sin motivo"]:
                print(f"Pasada en rojo: {reason}")
            return 1
        return 0
    if len(args) == 2 and args[0] == "marcar":
        report = _read_previous()
        health = report.get("runHealth")
        before = list(health.get("reasons") or []) if isinstance(health, dict) and health.get("ok") is False else []
        report["runHealth"] = _red(health, before + [args[1]] if args[1] not in before else before)
        if isinstance(health, dict) and health.get("drySince"):
            report["runHealth"]["drySince"] = health["drySince"]
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 0
    print('uso: source_health.py veredicto | marcar "<motivo>" | pendiente', file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
