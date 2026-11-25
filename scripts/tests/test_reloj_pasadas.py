"""El reloj de las pasadas (reloj.yml, scripts/reloj_pasadas.py): cada ~15 min decide si lanza una
pasada del bot (update.yml). Una cada 2 h (update_fiflp.PASS_EVERY) y una cada hora en las ventanas de partidos,
hora de Canarias (viernes de 18 a 24 y sábado y domingo de 10 a 24, con su cambio de hora: el 25/10/2026 a las
02:00 vuelve a UTC+0), con 10 min de holgura; nunca con una ejecución de update.yml sin acabar. Sin red: la
entrada es el JSON de `gh run list`. El workflow, en test_workflows.py; con el bot, la semana simulada de
test_bot_pasada_corta.py (test_with_the_clock_…)."""
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import zoneinfo
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reloj_pasadas as R  # noqa: E402

H1, H2 = timedelta(minutes=60), timedelta(minutes=120)


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def run(created, status="completed", conclusion="success", event="workflow_dispatch", number=1, started=None):
    out = {"number": number, "event": event, "status": status, "conclusion": conclusion if status == "completed" else "",
           "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if started is not None:
        out["startedAt"] = started.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


# ── Las ventanas ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("moment, expected", [
    # Octubre de 2026, hasta el 25: hora de verano de Canarias (UTC+1).
    ("2026-10-15T19:00", H2),       # jueves, 20:00: entre semana, nunca
    ("2026-10-16T09:00", H2),       # viernes, 10:00
    ("2026-10-16T16:59", H2),       # viernes, 17:59
    ("2026-10-16T17:00", H1),       # viernes, 18:00
    ("2026-10-16T22:59", H1),       # viernes, 23:59
    ("2026-10-16T23:00", H2),       # sábado, 00:00
    ("2026-10-17T08:59", H2),       # sábado, 09:59
    ("2026-10-17T09:00", H1),       # sábado, 10:00
    ("2026-10-17T15:30", H1),       # sábado, 16:30
    ("2026-10-17T22:59", H1),       # sábado, 23:59
    ("2026-10-17T23:00", H2),       # domingo, 00:00
    ("2026-10-18T08:59", H2),       # domingo, 09:59
    ("2026-10-18T09:00", H1),       # domingo, 10:00
    ("2026-10-18T22:59", H1),       # domingo, 23:59
    ("2026-10-18T23:00", H2),       # lunes, 00:00
    ("2026-10-19T11:00", H2),       # lunes, 12:00
])
def test_the_windows_in_canary_time(moment, expected):
    assert R.interval(utc(moment)) == expected, R.local_time(utc(moment))


@pytest.mark.parametrize("moment, expected", [
    # El 25/10/2026 a las 02:00 de Canarias (01:00 UTC) vuelve a ser las 01:00: desde ahí, UTC+0.
    ("2026-10-24T08:59", H2),       # sábado 24, 09:59 (UTC+1)
    ("2026-10-24T09:00", H1),       # sábado 24, 10:00 (UTC+1)
    ("2026-10-25T00:30", H2),       # domingo 25, 01:30 (la primera vez, UTC+1)
    ("2026-10-25T01:30", H2),       # domingo 25, 01:30 (la segunda, UTC+0)
    ("2026-10-25T09:00", H2),       # domingo 25, 09:00 (con UTC+1 serían las 10:00: dentro, mal)
    ("2026-10-25T09:59", H2),       # domingo 25, 09:59
    ("2026-10-25T10:00", H1),       # domingo 25, 10:00
    ("2026-10-25T23:59", H1),       # domingo 25, 23:59
    ("2026-10-26T00:00", H2),       # lunes 26, 00:00
    ("2026-10-30T17:59", H2),       # viernes 30, 17:59 (UTC+0)
    ("2026-10-30T18:00", H1),       # viernes 30, 18:00
    # Y el de marzo: el 28/3/2027 a las 01:00 de Canarias (01:00 UTC) pasan a ser las 02:00 (UTC+1).
    ("2027-03-27T09:59", H2),       # sábado 27, 09:59 (UTC+0)
    ("2027-03-27T10:00", H1),       # sábado 27, 10:00
    ("2027-03-28T08:59", H2),       # domingo 28, 09:59 (UTC+1)
    ("2027-03-28T09:00", H1),       # domingo 28, 10:00
])
def test_the_windows_follow_the_change_of_time(moment, expected):
    assert R.interval(utc(moment)) == expected, R.local_time(utc(moment))


def test_each_window_starts_an_hour_after_the_first_kickoffs():
    """La base de 2026-27: el viernes, los primeros a las 17 (238 partidos); el sábado y el domingo, a las 9
    (620 y 105). El bot no busca un resultado hasta el saque + HOT_AFTER (update_fiflp.hot_reason)."""
    assert R.FIRST_KICKOFF == {4: 17, 5: 9, 6: 9}
    assert R.WINDOWS == {4: 18, 5: 10, 6: 10}
    assert (R.BASE, R.WINDOW, R.SLACK) == (H2, H1, timedelta(minutes=10))
    assert R.window(utc("2026-10-17T09:00")) == "sábado de 10:00 a 24:00"
    assert R.window(utc("2026-10-16T17:00")) == "viernes de 18:00 a 24:00"
    assert R.window(utc("2026-10-15T17:00")) is None


# ── ¿Toca? ────────────────────────────────────────────────────────────────────

SAT = utc("2026-10-17T12:00")       # sábado, 13:00 en Canarias: cada hora
TUE = utc("2026-10-20T12:00")       # martes, 13:00: cada 2 h


def test_with_no_runs_it_is_due():
    assert R.due(SAT, []) and R.due(TUE, [])


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending", "requested", "action_required"])
def test_never_with_a_run_not_finished(status):
    """En cola, en marcha, esperando…: la siguiente se pondría en fila (concurrency update-data) y otra más
    cancelaría la pendiente, gastando un número de pasada sin pasada. Aunque sea de hace horas."""
    runs = [run(SAT - timedelta(hours=5), status=status, number=2), run(SAT - timedelta(hours=7), number=1)]
    ok, why = R.decide(SAT, runs)
    assert not ok and status in why


@pytest.mark.parametrize("now, minutes, expected", [
    (SAT, 49, False), (SAT, 49 + 59 / 60, False), (SAT, 50, True), (SAT, 75, True),
    (TUE, 60, False), (TUE, 109 + 59 / 60, False), (TUE, 110, True), (TUE, 300, True),
])
def test_the_interval_less_the_slack_since_the_last_one_was_created(now, minutes, expected):
    """Desde la creación de la última: el intervalo de ahora menos 10 min de holgura (un tick que llega unos
    minutos antes no deja pasar otra hora)."""
    assert R.due(now, [run(now - timedelta(minutes=minutes))]) is expected


def test_the_last_one_of_any_event_and_result_counts_whatever_the_order():
    """La creada más tarde, aunque gh las dé en otro orden, la lance quien la lance (el reloj, una tanda, a
    mano) y acabe como acabe (también fallida o cancelada)."""
    runs = [run(SAT - timedelta(minutes=200), event="schedule", number=1),
            run(SAT - timedelta(minutes=20), conclusion="failure", number=3),
            run(SAT - timedelta(minutes=90), conclusion="cancelled", number=2)]
    assert not R.due(SAT, runs)
    assert R.due(SAT, runs[:1] + runs[2:])
    ok, why = R.decide(SAT, runs)
    assert "la 3 (workflow_dispatch, failure)" in why and "hace 20 min" in why


def test_entering_a_window_the_next_pass_comes_sooner():
    """A las 17:59 del viernes, una creada hace 70 min aún no toca (110); a las 18:00, sí (50)."""
    friday = utc("2026-10-16T17:00")               # 18:00 en Canarias
    assert not R.due(friday - timedelta(minutes=1), [run(friday - timedelta(minutes=71))])
    assert R.due(friday, [run(friday - timedelta(minutes=70))])


def test_a_rerun_counts_from_when_it_was_relaunched():
    """Relanzar una ejecución (Re-run) conserva su createdAt y cambia su startedAt:
    la 1120, creada el sábado 24/10 a las 10:08 de Canarias, falla y se relanza a las 11:30. En el tick de las
    11:52, con solo createdAt, «se creó hace 104 min» y el reloj lanzaba otra pasada ~20 min después de
    acabar el relanzamiento (y el relanzamiento repite el número: el mismo turno). Cuenta desde las 11:30."""
    created, rerun = utc("2026-10-24T09:08"), utc("2026-10-24T10:30")
    runs = [run(created, number=1120, started=rerun), run(created - timedelta(hours=2), number=1119)]
    ok, why = R.decide(utc("2026-10-24T10:52"), runs)
    assert not ok and "la 1120" in why and "se relanzó hace 22 min" in why, why
    assert not R.due(rerun + timedelta(minutes=49), runs) and R.due(rerun + timedelta(minutes=50), runs)
    # En la cola o en marcha, el relanzamiento no deja lanzar otra (su status ya no es completed).
    assert not R.due(utc("2026-10-24T12:00"), [run(created, status="in_progress", number=1120, started=rerun)])


def test_without_startedat_it_counts_from_its_creation():
    """En el primer intento startedAt es su creación (o casi); sin él, vacío o null (otra versión de gh), la
    creación. Uno que no se lee: mejor un job en rojo."""
    at = SAT - timedelta(minutes=55)
    for started in (at, at + timedelta(seconds=20)):
        ok, why = R.decide(SAT, [run(at, started=started)])
        assert ok and "se creó hace" in why, why
    for started in (None, ""):
        bare = run(at)
        bare["startedAt"] = started
        assert R.due(SAT, [bare]) and R.run_time(bare) == R.created_at(bare)
    for bad in ("ayer", 17, ["2026-10-17T10:00:00Z"]):
        wrong = run(at)
        wrong["startedAt"] = bad
        with pytest.raises(ValueError):
            R.decide(SAT, [wrong])


def test_a_run_created_in_the_future_is_not_due():
    """Un reloj que va por detrás del de GitHub no lanza otra encima."""
    ok, why = R.decide(SAT, [run(SAT + timedelta(minutes=5))])
    assert not ok and "después de ahora" in why


@pytest.mark.parametrize("bad", [{}, None, "x", [1], [{"createdAt": "2026-10-17T10:00:00Z"}],
                                 [{"status": "completed"}], [{"status": "completed", "createdAt": "ayer"}]])
def test_an_input_that_is_not_the_list_of_runs_is_an_error(bad):
    """Mejor un job en rojo que un reloj que decide sobre otra cosa."""
    with pytest.raises(ValueError):
        R.decide(SAT, bad)


# ── La línea de órdenes (el paso de reloj.yml) ────────────────────────────────

def test_the_command_line_prints_the_decision_and_writes_due(tmp_path, capsys):
    out = tmp_path / "salida"
    runs = json.dumps([run(SAT - timedelta(minutes=55), number=1118)])
    assert R.main(["--now", "2026-10-17T12:00:00Z"], io.StringIO(runs), {"GITHUB_OUTPUT": str(out)}) == 0
    assert R.main(["--now", "2026-10-17T12:00:00+00:00"], io.StringIO("[]"), {"GITHUB_OUTPUT": str(out)}) == 0
    assert R.main(["--now", "2026-10-20T12:00:00Z"], io.StringIO(runs.replace("2026-10-17", "2026-10-20")),
                  {"GITHUB_OUTPUT": str(out)}) == 0
    # due_carril=false sin --carril (el carril, apagado): el paso que lo lanza no corre.
    assert out.read_text() == "due=true\ndue_carril=false\n" * 2 + "due=false\ndue_carril=false\n"
    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith("17/10/2026 13:00 en Canarias, ventana de partidos (sábado de 10:00 a 24:00)")
    assert "Toca: la última, la 1118" in printed[0]
    assert "fuera de las ventanas de partidos: una pasada cada 120 min. No toca" in printed[2]


def test_the_command_line_fails_without_writing_anything(tmp_path, capsys):
    """Un fallo de gh (lo que deja en el fichero no es la lista): sale con error, sin due (el paso de lanzar no
    corre) y con el motivo a la vista."""
    out = tmp_path / "salida"
    for text in ("", "no es json", '{"message": "Bad credentials"}'):
        assert R.main(["--now", "2026-10-17T12:00:00Z"], io.StringIO(text), {"GITHUB_OUTPUT": str(out)}) == 1
    assert not out.exists()
    assert "no se lanza nada" in capsys.readouterr().err
    assert R.main(["--otra"], io.StringIO("[]"), {}) == 2


def test_it_runs_alone_with_the_system_python(tmp_path):
    """reloj.yml solo baja este fichero (checkout disperso) y no instala nada: corre solo, sin el resto del
    repositorio, en modo aislado (-I: ni el directorio del guion en sys.path ni variables de Python)."""
    alone = tmp_path / "reloj_pasadas.py"
    shutil.copy(Path(R.__file__), alone)
    out = tmp_path / "salida"
    done = subprocess.run([sys.executable, "-I", str(alone), "--now", "2026-10-17T12:00:00Z"], input="[]", text=True,
                          capture_output=True, cwd=tmp_path, env={"GITHUB_OUTPUT": str(out)}, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "Toca: no hay ninguna ejecución de update.yml." in done.stdout
    assert out.read_text() == "due=true\ndue_carril=false\n"


# ── Sin la base de zonas horarias ─────────────────────────────────────────────

def test_without_the_time_zones_there_are_no_windows_but_the_clock_goes_on(monkeypatch, tmp_path, capsys):
    """Sin la zona Atlantic/Canary (ZoneInfoNotFoundError, un KeyError: la base de zonas del sistema no está y
    el reloj no instala tzdata), el reloj no sabe la hora de Canarias: sin ventanas, una pasada cada 2 h
    (BASE), con un aviso, y sin dejar el job en rojo (sin ello saldría con una traza, sin due,
    y como update.yml no tiene cron no habría ninguna pasada)."""
    def missing(key):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")
    monkeypatch.setattr(R, "ZoneInfo", missing)
    assert R.local_time(SAT) is None and R.window(SAT) is None and R.interval(SAT) == H2
    assert R.due(SAT, []) and not R.due(SAT, [run(SAT - timedelta(minutes=60))])
    assert R.due(SAT, [run(SAT - timedelta(minutes=110))])
    out = tmp_path / "salida"
    assert R.main(["--now", "2026-10-17T12:00:00Z"], io.StringIO("[]"), {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text() == "due=true\ndue_carril=false\n"
    printed = capsys.readouterr().out
    assert printed.startswith("17/10/2026 12:00 UTC, sin la hora de Canarias"), printed
    assert "::warning::reloj_pasadas: no está la zona Atlantic/Canary" in printed


@pytest.mark.skipif(importlib.util.find_spec("tzdata") is not None,
                    reason="con el paquete tzdata, zoneinfo no depende de la base del sistema")
def test_without_the_system_time_zones_the_script_still_decides(tmp_path):
    """Lo mismo de verdad: el guion solo, con PYTHONTZPATH en un directorio vacío (sin la base del sistema)."""
    alone = tmp_path / "reloj_pasadas.py"
    shutil.copy(Path(R.__file__), alone)
    empty = tmp_path / "zonas"
    empty.mkdir()
    out = tmp_path / "salida"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONTZPATH": str(empty), "GITHUB_OUTPUT": str(out)}
    done = subprocess.run([sys.executable, str(alone), "--now", "2026-10-17T12:00:00Z"], input="[]", text=True,
                          capture_output=True, cwd=tmp_path, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "::warning::" in done.stdout and out.read_text() == "due=true\ndue_carril=false\n"


# ── El carril de las categorías mayores (carril-mayores.yml) ──────────────────
#
# El reloj lo lanza solo con la variable CARRIL_MAYORES a 1 (reloj.yml), fuera de las ventanas de partidos y a
# más de 1 h de que empiece una, entre dos pasadas del bot (la última empezó hace 25-75 min), cada 4 h, y nunca con
# otra ejecución sin acabar: del bot, del carril, de la activación (activar.yml) o del histórico (historico.yml:
# GitHub guarda una sola ejecución en espera por grupo de concurrencia y el histórico puede tardar horas). Diciembre
# de 2026: Canarias en UTC+0, así que las horas de abajo son las de Canarias.

M = timedelta(minutes=1)


def bot_a_las(now, minutes, number=50):
    """La lista del bot con una sola pasada, empezada hace `minutes` y acabada."""
    return [run(now - minutes * M, number=number)]


def test_due_carril():
    tue = utc("2026-12-01T10:40")                           # martes, 10:40
    assert R.due_carril(tue, bot_a_las(tue, 30), [], [])[0]
    assert not R.due_carril(utc("2026-12-01T10:20"), bot_a_las(utc("2026-12-01T10:20"), 10), [], [])[0]
    assert not R.due_carril(utc("2026-12-01T11:30"), bot_a_las(utc("2026-12-01T11:30"), 80), [], [])[0]
    # Los bordes: desde los 25 min y hasta los 75 (incluidos).
    assert R.due_carril(tue, bot_a_las(tue, 25), [], [])[0] and R.due_carril(tue, bot_a_las(tue, 75), [], [])[0]
    assert not R.due_carril(tue, bot_a_las(tue, 24), [], [])[0] and not R.due_carril(tue, bot_a_las(tue, 76), [], [])[0]
    # La última del carril: hace 3 h 40 min, no; hace 3 h 55 min, sí (4 h menos la holgura de 10 min).
    ok, why = R.due_carril(tue, bot_a_las(tue, 30), [run(utc("2026-12-01T07:00"), number=7)], [])
    assert not ok and "la 7" in why, why
    assert R.due_carril(tue, bot_a_las(tue, 30), [run(utc("2026-12-01T06:45"), number=7)], [])[0]
    # Nada sin acabar: ni la activación, ni el histórico, ni el propio carril, ni el bot.
    ok, why = R.due_carril(tue, bot_a_las(tue, 30), [], [run(tue - 5 * M, status="in_progress", number=3)])
    assert not ok and "in_progress" in why, why
    for status in ("queued", "waiting", "pending"):
        assert not R.due_carril(tue, bot_a_las(tue, 30), [], [run(tue - 300 * M, status=status)])[0], status
    assert not R.due_carril(tue, bot_a_las(tue, 30), [run(tue - 300 * M, status="in_progress")], [])[0]
    assert not R.due_carril(tue, [run(tue - 30 * M, status="in_progress")], [], [])[0]
    # Las acabadas de la activación y del histórico no cuentan (ni su hora).
    assert R.due_carril(tue, bot_a_las(tue, 30), [], [run(tue - 5 * M, conclusion="failure")])[0]
    # Las ventanas: el viernes, desde las 17:00 (la ventana empieza a las 18:00); el sábado, desde las 9:00.
    fri = utc("2026-12-04T17:10")
    ok, why = R.due_carril(fri, bot_a_las(fri, 30), [], [])
    assert not ok and "ventana" in why, why
    assert R.due_carril(utc("2026-12-04T16:50"), bot_a_las(utc("2026-12-04T16:50"), 30), [], [])[0]
    for moment, expected in (("2026-12-05T08:40", True), ("2026-12-05T09:10", False), ("2026-12-05T12:00", False),
                             ("2026-12-06T08:59", True), ("2026-12-06T09:00", False), ("2026-12-06T23:30", False),
                             ("2026-12-07T00:10", True)):
        now = utc(moment)
        assert R.due_carril(now, bot_a_las(now, 30), [], [])[0] is expected, moment
    # Sin ninguna pasada del bot: no hay hueco que medir.
    assert not R.due_carril(tue, [], [], [])[0]


def test_due_carril_sin_zona_horaria_nunca(monkeypatch):
    """Sin la base de zonas horarias no se sabe dónde caen las ventanas: el carril no se lanza (el bot sigue, cada
    2 h: test_without_the_time_zones_…)."""
    def missing(key):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")
    monkeypatch.setattr(R, "ZoneInfo", missing)
    tue = utc("2026-12-01T10:40")
    ok, why = R.due_carril(tue, bot_a_las(tue, 30), [], [])
    assert not ok and "zonas horarias" in why, why


def test_due_carril_nunca_a_la_vez_que_el_bot(monkeypatch):
    """Si toca una pasada del bot, gana ella, aunque el hueco del carril también encajara."""
    monkeypatch.setattr(R, "CARRIL_HASTA", timedelta(minutes=200))
    tue = utc("2026-12-01T10:40")
    assert R.due(tue, bot_a_las(tue, 115))
    ok, why = R.due_carril(tue, bot_a_las(tue, 115), [], [])
    assert not ok and "pasada del bot" in why, why


def test_due_carril_valida_sus_listas():
    tue = utc("2026-12-01T10:40")
    for bad in ({}, None, [1], [{"status": "completed"}]):
        with pytest.raises(ValueError):
            R.due_carril(tue, bot_a_las(tue, 30), bad, [])
        with pytest.raises(ValueError):
            R.due_carril(tue, bot_a_las(tue, 30), [], bad)


def test_las_constantes_del_carril():
    assert R.CARRIL_CADA == timedelta(hours=4)
    assert (R.CARRIL_DESDE, R.CARRIL_HASTA) == (timedelta(minutes=25), timedelta(minutes=75))
    assert R.ANTES_DE_VENTANA == timedelta(hours=1)
    # El carril (~24 min) lanzado lo más tarde posible acaba antes de que toque la pasada siguiente del bot.
    assert R.CARRIL_HASTA + timedelta(minutes=24) < R.BASE - R.SLACK


def test_due_espera_al_carril():
    """Con el carril sin acabar, la pasada del bot espera (si no, haría cola tras él en update-data y otra
    más en cola cancelaría la que espera); acabado, toca como siempre."""
    for now in (TUE, SAT):
        runs = [run(now - 300 * M)]
        ok, why = R.decide(now, runs, [run(now - 10 * M, status="in_progress", number=4)])
        assert not ok and "carril" in why and "in_progress" in why, why
        assert not R.due(now, runs, [run(now - 10 * M, status="queued")])
        assert R.due(now, runs, [run(now - 10 * M)]) and R.due(now, runs)


def test_carril_no_comparte_numero_ni_reloj():
    """La decisión del bot solo mira las ejecuciones de update.yml: las del carril (carril-mayores.yml, con su
    propio número de pasada) acabadas no la cambian, por recientes que sean (si contaran, cada pasada del carril
    retrasaría hasta 2 h la siguiente del bot)."""
    for now in (TUE, SAT, utc("2026-12-01T10:40"), utc("2026-12-04T17:10")):
        for minutes in (10, 30, 49, 50, 75, 109, 110, 125, 300):
            runs = bot_a_las(now, minutes)
            for otros in ([run(now - 5 * M, number=900)], [run(now - k * M, number=900 + k) for k in (1, 20, 60, 200)]):
                assert R.due(now, runs, otros) == R.due(now, runs), (now, minutes)
                assert R.decide(now, runs, otros) == R.decide(now, runs)


DURA = timedelta(minutes=24)


def _semana(con_carril):
    """La semana del lunes 30/11 al domingo 6/12/2026 con el reloj: un tick a las :07, :22, :37 y :52 de cada hora,
    que lanza una pasada del bot si toca (due) y, si no, una del carril si toca (due_carril); cada una dura 24 min.
    Sin activar.yml ni histórico. Devuelve [(«bot»|«carril», inicio)]."""
    bot = [(utc("2026-11-29T23:07"), "bot")]                # la última del domingo 29, en su ventana
    hechas = list(bot)
    tick = utc("2026-11-30T00:07")
    end = utc("2026-12-07T00:00")

    def lista(kind, now):
        return [run(at, status="completed" if at + DURA <= now else "in_progress", number=i)
                for i, (at, k) in enumerate(hechas) if k == kind][-20:]

    while tick < end:
        for minute in (7, 22, 37, 52):
            now = tick.replace(minute=minute)
            principal, carril = lista("bot", now), lista("carril", now)
            if R.due(now, principal, carril if con_carril else ()):
                hechas.append((now, "bot"))
            elif con_carril and R.due_carril(now, principal, carril, [])[0]:
                hechas.append((now, "carril"))
        tick += timedelta(hours=1)
    return [(k, at) for at, k in hechas[1:]]


def test_semana_con_carril():
    sin, con = _semana(False), _semana(True)
    assert [at for k, at in con if k == "bot"] == [at for _, at in sin], "las pasadas del bot, a su hora de siempre"
    assert all(k == "bot" for k, _ in sin)
    # Nunca dos a la vez.
    starts = [at for _, at in con]
    assert starts == sorted(starts)
    assert all(b >= a + DURA for a, b in zip(starts, starts[1:]))
    carril = [at for k, at in con if k == "carril"]
    por_dia = {}
    for at in carril:
        por_dia[at.date()] = por_dia.get(at.date(), 0) + 1
        assert R.window(at) is None and R.window(at + R.ANTES_DE_VENTANA) is None, at
    dias = [utc("2026-11-30T00:00").date() + timedelta(days=d) for d in range(7)]
    assert [por_dia.get(d, 0) for d in dias[:4]] == [6, 6, 6, 6], por_dia          # de lunes a jueves
    assert por_dia.get(dias[4], 0) >= 4, por_dia                                     # viernes
    assert por_dia.get(dias[5], 0) == 3 and por_dia.get(dias[6], 0) == 3, por_dia   # sábado y domingo
    assert len(carril) >= 34


# ── La línea de órdenes con el carril ─────────────────────────────────────────

def _json(path, runs):
    path.write_text(json.dumps(runs), encoding="utf-8")
    return str(path)


def test_the_command_line_with_the_lane(tmp_path, capsys):
    """Con --carril y --activar (una o más listas: reloj.yml pasa la de activar.yml y la de historico.yml), escribe
    due y due_carril; sin ellas, due_carril=false y la misma decisión del bot."""
    out = tmp_path / "salida"
    tue = utc("2026-12-01T10:40")
    pasadas = json.dumps(bot_a_las(tue, 30, number=1200))
    carril = _json(tmp_path / "carril.json", [])
    activar = _json(tmp_path / "activar.json", [])
    historico = _json(tmp_path / "historico.json", [run(tue - 300 * M)])
    args = ["--now", "2026-12-01T10:40:00Z", "--carril", carril, "--activar", activar, "--activar", historico]
    assert R.main(args, io.StringIO(pasadas), {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text() == "due=false\ndue_carril=true\n"
    printed = capsys.readouterr().out.splitlines()
    assert "No toca" in printed[0] and printed[1].startswith("Carril de las categorías mayores: toca"), printed
    # El histórico en marcha: no toca.
    _json(tmp_path / "historico.json", [run(tue - 30 * M, status="in_progress")])
    out.unlink()
    assert R.main(args, io.StringIO(pasadas), {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text() == "due=false\ndue_carril=false\n"
    assert "Carril de las categorías mayores: no toca: la 1 de activar.yml o historico.yml está in_progress" \
        in capsys.readouterr().out
    # Sin el carril: lo de siempre, y due_carril=false.
    out.unlink()
    assert R.main(["--now", "2026-12-01T10:40:00Z"], io.StringIO(pasadas), {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text() == "due=false\ndue_carril=false\n"
    assert "Carril" not in capsys.readouterr().out
    # El carril sin acabar: tampoco la del bot, aunque toque.
    out.unlink()
    _json(tmp_path / "carril.json", [run(tue - 10 * M, status="in_progress")])
    late = json.dumps(bot_a_las(tue, 200))
    assert R.main(args, io.StringIO(late), {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text() == "due=false\ndue_carril=false\n"


def test_the_command_line_with_the_lane_fails_without_writing_anything(tmp_path, capsys):
    """Una lista del carril o de la activación que no se lee (un fallo de gh): en rojo y sin escribir nada; ni
    la pasada del bot se lanza (no se sabe si el carril está en marcha). --carril sin --activar, o al revés: uso."""
    out = tmp_path / "salida"
    pasadas = json.dumps(bot_a_las(TUE, 300))
    good = _json(tmp_path / "bien.json", [])
    bad = tmp_path / "mal.json"
    bad.write_text("no es json", encoding="utf-8")
    for args in (["--carril", str(bad), "--activar", good], ["--carril", good, "--activar", str(bad)],
                 ["--carril", str(tmp_path / "no-esta.json"), "--activar", good]):
        assert R.main(["--now", "2026-10-20T12:00:00Z", *args], io.StringIO(pasadas), {"GITHUB_OUTPUT": str(out)}) == 1
    assert not out.exists()
    assert "no se lanza nada" in capsys.readouterr().err
    for args in (["--carril", good], ["--activar", good], ["--carril"], ["--carril", good, "--activar"]):
        assert R.main(args, io.StringIO(pasadas), {"GITHUB_OUTPUT": str(out)}) == 2, args
    assert not out.exists()
