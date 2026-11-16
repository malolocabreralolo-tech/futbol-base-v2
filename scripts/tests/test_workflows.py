"""Regression tests for the GitHub Actions workflows (.github/workflows/).

Guards the CI contracts fixed on 2026-06-11:

1. update.yml runs BOTH test suites BEFORE committing. Bot pushes made with
   the default GITHUB_TOKEN never trigger other workflows (GitHub's
   anti-recursion), so tests.yml had not run since 2026-05-22 and a red
   pytest was invisible. Running the suites inside update.yml makes a red
   suite block the data commit and show up as a red run.
2. tests.yml has a daily schedule + workflow_dispatch as a safety net, and
   its node job runs the glob `scripts/tests/test_*.mjs` (contract C5) so
   new suites (e.g. test_sp2_modules.mjs) are picked up automatically.
3. Every workflow that runs scripts/generate_js.py stages ALL of its
   outputs: `data-*.js` glob (covers data-seasons.js, data-season-*.js,
   data-lineups-*.js, future files), plus index.html, sw.js
   (CACHE_NAME bump, contracts C3/C4) and futbolbase.db.
4. (17/10/2026) update.yml no tiene cron: lo lanza el reloj (reloj.yml, con
   scripts/reloj_pasadas.py), cada 15 min, con los permisos justos (también
   en el job) y solo sus disparadores, sin pip, y solo cuando toca
   (test_reloj_pasadas.py prueba la decisión). El guion del paso que decide
   se ejecuta con un gh de mentira: un fallo de gh lo deja en rojo y sin due.

5. (14/11/2026, fase 2B) update.yml publica el diagnóstico (solo
   data-health.json) también cuando fallan las pruebas, y pone el job en rojo
   después del commit si la pasada no fue sana (runHealth). El guion del paso
   de diagnóstico se ejecuta en un repositorio de mentira con su remoto.

Static YAML checks — no network, no workflow execution (except those two
step scripts, run locally with bash, a fake gh and a throwaway git remote).
"""
import json
import os
import re
import subprocess
from datetime import timedelta
from fnmatch import fnmatch
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WF_DIR = ROOT / ".github" / "workflows"

OWNED = ["update.yml", "tests.yml", "reloj.yml", "activar.yml"]

# Los workflows que hay: uno nuevo o uno que vuelve se piensa antes (¿escribe la base?, ¿va en cola?) y se apunta aquí.
WORKFLOWS = {"actas-federacion.yml", "activar.yml", "detalle-federacion.yml", "discover-fiflp.yml",
             "fetch-fiflp-islas.yml", "freno-fiflp.yml", "goleadores-federacion.yml", "probe-fiflp.yml",
             "reloj.yml", "tests.yml", "update.yml"}
# Lo que publica una pasada: quien lo sube tiene que hacer cola con el bot, o dos subidas se pisan la base.
PUBLICADO = ("futbolbase.db", "data-*.js", "index.html", "sw.js")


def _load(name):
    return yaml.safe_load((WF_DIR / name).read_text(encoding="utf-8"))


def _triggers(data):
    # PyYAML parses the bare `on:` key as boolean True.
    return data.get("on", data.get(True))


def _steps(data, job):
    return data["jobs"][job]["steps"]


def _runs(data, job):
    return [(s.get("run") or "") for s in _steps(data, job)]


# ------------------------------------------------------------------ generic

@pytest.mark.parametrize("name", OWNED)
def test_workflow_yaml_is_valid(name):
    data = _load(name)
    assert isinstance(data, dict) and "jobs" in data


def _all_runs(name):
    data = _load(name)
    return [step.get("run") or "" for job in data["jobs"].values() for step in job.get("steps", [])]


def _git_add_paths(run):
    """Las rutas de cada «git add» del guion, también las que pasan por una función suya que lo llama
    (add_if_exists f); una ruta en una variable no se resuelve."""
    wrappers = set(re.findall(r"(\w+)\s*\(\)\s*\{[^}]*\bgit add\b", run))
    paths = []
    for line in run.splitlines():
        if line.lstrip().startswith("#"):
            continue
        calls = [m.group(1) for m in re.finditer(r"\bgit add\s+([^;&|\n]*)", line)]
        calls += [m.group(1) for w in wrappers for m in re.finditer(rf"(?:^|[;&|]|\bdo\b|\bthen\b|\belse\b)\s*{w}\s+([^;&|\n]*)", line)]
        for args in calls:
            paths += [a.strip("'\"") for a in args.split() if not a.startswith(("2>", ">"))]
    return paths


def _publica(path):
    return path in (".", "-A", "--all", "-u") or any(fnmatch(path, pat) or fnmatch(pat, path) for pat in PUBLICADO)


def test_workflows_que_hay():
    assert {path.name for path in WF_DIR.glob("*.yml")} == WORKFLOWS
    assert not list(WF_DIR.glob("*.yaml"))


def test_solo_el_bot_escribe_la_base():
    """Solo el bot (update.yml) y la activación (activar.yml) suben la base o lo publicado, y los dos en el grupo
    update-data: así ninguna subida pisa la base de otra."""
    escriben = set()
    for path in sorted(WF_DIR.glob("*.yml")):
        if any(_publica(p) for run in _all_runs(path.name) for p in _git_add_paths(run)):
            escriben.add(path.name)
            assert (_load(path.name).get("concurrency") or {}).get("group") == "update-data", path.name
    assert escriben == {"update.yml", "activar.yml"}, escriben


def test_git_add_paths_sees_through_a_wrapper():
    run = 'add_if_exists() {\n  for f in "$@"; do [ -e "$f" ] && git add "$f"; done\n}\nadd_if_exists data-*.js sw.js\n'
    assert _publica("data-seasons.js") and not _publica("data-health.json")
    assert {"data-*.js", "sw.js"} <= set(_git_add_paths(run))
    assert _git_add_paths("git add 'scripts/x_*_raw.json' 2>/dev/null || true") == ["scripts/x_*_raw.json"]


def test_quien_sube_va_en_cola():
    """Todo el que empuja a main va en un grupo de concurrencia (no se adelanta a otra subida suya) y rebasa
    con --autostash, nunca con git stash: un stash pop que choca deja el árbol a medias y sube igual."""
    for path in sorted(WF_DIR.glob("*.yml")):
        runs = _all_runs(path.name)
        if not any(re.search(r"\bgit push\b", run) for run in runs):
            continue
        assert (_load(path.name).get("concurrency") or {}).get("group"), path.name
        assert not any(re.search(r"\bgit stash\b", run) for run in runs), path.name


@pytest.mark.parametrize("name", ["discover-fiflp.yml", "fetch-fiflp-islas.yml"])
def test_las_descargas_manuales_no_paran_al_bot(name):
    """discover-fiflp.yml y fetch-fiflp-islas.yml no escriben la base: van en su propio grupo, sin cancelar a
    nadie, y no en update-data (una descarga de hasta 180 min dejaría al bot sin pasadas, y con un solo hueco de
    espera por grupo se cancelarían entre sí); no pisan un push porque rebasan como el bot (tres intentos,
    --autostash, y un conflicto aborta en rojo)."""
    data = _load(name)
    assert data.get("concurrency") == {"group": "descargas-manuales", "cancel-in-progress": False}, name
    assert data["concurrency"]["group"] != "update-data", name
    push = next(run for run in _all_runs(name) if "git push" in run)
    assert "for intento in 1 2 3; do" in push, name
    assert "git pull --rebase --autostash origin main || { git rebase --abort;" in push, name


def test_islas_entradas_por_env():
    """Las entradas del dispatch van al guion por env:, nunca interpoladas en el run (una entrada con comillas
    o $() se ejecutaría como guion)."""
    for run in _all_runs("fetch-fiflp-islas.yml"):
        assert "${{ inputs." not in run, run


# --------------------------------------------------------------- update.yml

def test_update_runs_both_suites_before_commit():
    """Suites must run after the data refresh and before the commit step,
    so a red suite aborts the run (exit != 0) and nothing is published."""
    runs = _runs(_load("update.yml"), "update")
    pytest_idx = next(
        (i for i, r in enumerate(runs) if re.search(r"python3? -m pytest scripts/tests/", r)),
        None,
    )
    node_idx = next(
        (i for i, r in enumerate(runs) if "node --test scripts/tests/test_*.mjs" in r),
        None,
    )
    fetch_idx = next((i for i, r in enumerate(runs) if "fetch_futbolaspalmas" in r), None)
    commit_idx = next((i for i, r in enumerate(runs) if "git commit" in r), None)
    assert pytest_idx is not None, "update.yml must run pytest before committing"
    assert node_idx is not None, "update.yml must run node --test (glob) before committing"
    assert fetch_idx is not None and commit_idx is not None
    assert fetch_idx < pytest_idx < commit_idx, "pytest must run between fetch and commit"
    assert fetch_idx < node_idx < commit_idx, "node suite must run between fetch and commit"


def test_update_installs_test_dependencies():
    # pyyaml is needed by this very test file when CI runs pytest.
    runs = " ".join(_runs(_load("update.yml"), "update"))
    assert "pip install -r scripts/requirements-tests.txt" in runs
    assert "pip install -r scripts/requirements-bot.txt" in runs
    assert {"pytest", "pyyaml"} <= set(_requisitos("requirements-tests.txt"))


def test_update_has_concurrency_and_timeout():
    data = _load("update.yml")
    conc = data.get("concurrency")
    assert conc, "update.yml must declare a concurrency group"
    assert conc.get("group") == "update-data"
    assert conc.get("cancel-in-progress") is False
    # 45 desde 2026/27: los grupos de la federación se leen con navegador. 55 desde el 15/10/2026: el
    # plazo del bot pasa de 25 a 33 min (update_fiflp.DEADLINE_SECONDS: la federación sirve ~15 páginas
    # por IP y frena ~5 min, y el plazo se mide en vueltas), y el resto del job son 4-8 min más. 40 desde
    # el 16/10/2026: pasadas cortas (16 min de plazo; una espera del freno por pasada), cada 2 h (desde el
    # 17/10/2026 las lanza reloj.yml: cada 2 h, y cada hora en las ventanas de partidos).
    assert data["jobs"]["update"].get("timeout-minutes") == 40


def test_the_federation_budget_fits_in_the_update_job():
    """El plazo del bot (update_fiflp.DEADLINE_SECONDS), el resto del job (4-8 min: preparación, app,
    importaciones, generate_js, pruebas y commit) y lo que puede pasarse la última página (empezada justo
    antes del plazo: sus tres intentos de hasta 30 s y sus esperas de 15 y 30 s, ~2 min) caben en el
    timeout de update.yml con margen: si sube el plazo sin subir el timeout, esto falla."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import update_fiflp
    timeout = _load("update.yml")["jobs"]["update"]["timeout-minutes"]
    worst = update_fiflp.DEADLINE_SECONDS / 60 + 8 + 2.25
    assert worst + 10 <= timeout, (worst, timeout)
    # El final del plazo en el que no empieza ningún grupo, en proporción (run_passes no da más de un cuarto).
    assert update_fiflp.RESERVE_SECONDS <= update_fiflp.DEADLINE_SECONDS / 4


def test_update_has_no_schedule_the_clock_launches_it():
    """Desde el 17/10/2026 update.yml no tiene cron: su '23 */2 * * *' casi no llegaba (5 de 13 en ~26 h) y lo
    lanza el reloj (reloj.yml) con workflow_dispatch, que también usan las tandas y quien lo lance a mano. Un
    cron aquí volvería a sumar ejecuciones fuera del reloj (y GITHUB_RUN_NUMBER, del que sale la rotación).
    Una sola pasada a la vez: la concurrency las pone en fila, sin cancelar ninguna."""
    data = _load("update.yml")
    trig = _triggers(data)
    assert "schedule" not in trig, "el reloj (reloj.yml) es el único reloj del bot"
    assert "workflow_dispatch" in trig
    assert data["concurrency"] == {"group": "update-data", "cancel-in-progress": False}


def _reloj_job():
    data = _load("reloj.yml")
    assert list(data["jobs"]) == ["reloj"]
    return data, data["jobs"]["reloj"]


def test_the_clock_ticks_every_15_minutes_off_the_hour():
    """El reloj (17/10/2026): un tick cada 15 min, nunca a en punto ni a y media (GitHub retrasa o pierde más
    esos), cada hora del día: si GitHub pierde uno, el siguiente lanza la pasada que toque. Y a mano."""
    data, _ = _reloj_job()
    assert data["name"] == "Reloj de las pasadas"
    trig = _triggers(data)
    assert set(trig) == {"schedule", "workflow_dispatch"}, "solo el tick y a mano (con actions: write)"
    crons = [e.get("cron") for e in (trig.get("schedule") or [])]
    assert len(crons) == 1
    minute, *rest = crons[0].split()
    minutes = sorted(int(m) for m in minute.split(","))
    assert rest == ["*", "*", "*", "*"], crons
    assert not {0, 30} & set(minutes), minutes
    steps = [b - a for a, b in zip(minutes, minutes[1:] + [minutes[0] + 60])]
    assert len(minutes) >= 4 and max(steps) <= 15, minutes


def test_the_clock_has_minimal_permissions_and_is_light():
    """Solo lee y lanza workflows (actions: write) y lee el repositorio (contents: read), nada más; un job
    corto, uno cada vez (dos ticks juntos, en fila y sin cancelarse), con un checkout disperso de su guion,
    sin credenciales guardadas, con el python3 del sistema y sin pip ni setup-python."""
    data, job = _reloj_job()
    assert data["permissions"] == {"actions": "write", "contents": "read"}
    assert "permissions" not in job, "los del job sustituirían a los del workflow"
    assert data["concurrency"]["cancel-in-progress"] is False and data["concurrency"]["group"]
    assert data["concurrency"]["group"] != "update-data", "no comparte fila con las pasadas"
    assert job["runs-on"] == "ubuntu-24.04" and job.get("timeout-minutes", 99) <= 10
    uses = [st["uses"] for st in job["steps"] if "uses" in st]
    assert uses == ["actions/checkout@v5"], uses
    checkout = next(st for st in job["steps"] if "uses" in st)
    assert checkout["with"]["sparse-checkout"].split() == ["scripts/reloj_pasadas.py"]
    assert checkout["with"].get("sparse-checkout-cone-mode") is False
    assert checkout["with"].get("persist-credentials") is False
    runs = " ".join(st.get("run") or "" for st in job["steps"])
    assert not re.search(r"\bpip3?\b", runs) and "setup-python" not in runs
    for st in job["steps"]:
        assert "${{" not in (st.get("run") or ""), "nada interpolado en el guion"


def test_the_clock_launches_update_on_main_only_when_due():
    """El paso que decide lee las ejecuciones de update.yml con gh y se las pasa a reloj_pasadas.py (que
    escribe due en $GITHUB_OUTPUT), con pipefail: un fallo de gh tumba el job a la vista y no lanza nada. El
    que lanza, solo si toca, y sobre main (como las tandas: el GITHUB_TOKEN sí puede lanzar workflow_dispatch)."""
    _, job = _reloj_job()
    steps = job["steps"]
    decide = next(st for st in steps if "reloj_pasadas.py" in (st.get("run") or ""))
    launch = next(st for st in steps if "gh workflow run" in (st.get("run") or ""))
    assert steps.index(decide) < steps.index(launch)
    assert "set -euo pipefail" in decide["run"]
    assert re.search(r"gh run list [^\n]*--workflow update\.yml", decide["run"])
    fields = re.search(r"--json (\S+)", decide["run"]).group(1).split(",")
    assert {"status", "createdAt", "startedAt"} <= set(fields), "startedAt: un relanzamiento cuenta desde que se relanza"
    assert "||" not in decide["run"], "un fallo de gh no se cambia por otra cosa: el job, en rojo"
    assert "python3 scripts/reloj_pasadas.py <" in decide["run"]
    assert decide["env"]["GH_TOKEN"] == "${{ github.token }}" and decide.get("id")
    assert not decide.get("continue-on-error")
    assert launch["if"] == f"steps.{decide['id']}.outputs.due == 'true'"
    assert "gh workflow run update.yml --ref main" in launch["run"]
    assert launch["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert [st for st in steps if "gh workflow run" in (st.get("run") or "")] == [launch]


def _run_decide_step(tmp_path, gh_script):
    """El guion del paso que decide de reloj.yml, con bash y un gh de mentira (`gh_script`, su cuerpo), desde
    la raíz del repositorio: (código de salida, lo que escribió en $GITHUB_OUTPUT o None, la salida)."""
    _, job = _reloj_job()
    decide = next(st for st in job["steps"] if "reloj_pasadas.py" in (st.get("run") or ""))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/bash\n" + gh_script + "\n", encoding="utf-8")
    gh.chmod(0o755)
    out = tmp_path / "salida"
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "RUNNER_TEMP": str(tmp_path),
           "GITHUB_OUTPUT": str(out), "GITHUB_REPOSITORY": "dueño/futbol-base", "GH_TOKEN": "x"}
    done = subprocess.run(["bash", "-c", decide["run"]], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=60)
    return done.returncode, (out.read_text() if out.exists() else None), done.stdout + done.stderr


def test_a_gh_failure_fails_the_clock_and_launches_nothing(tmp_path):
    """El guion de verdad del paso que decide: con un gh que falla (sin red, sin permisos, la API caída), sale
    en rojo y sin due, así que el paso que lanza no corre (con un `|| echo '[]'`, «no hay ninguna» y una pasada
    en cada tick). Con un gh que responde, decide y escribe due."""
    code, out, log = _run_decide_step(tmp_path / "falla", 'echo "HTTP 502: Bad Gateway" >&2; exit 1')
    assert code != 0 and out is None, (code, out, log)
    code, out, log = _run_decide_step(tmp_path / "basura", 'echo "<html>no es la lista</html>"')
    assert code != 0 and out is None, (code, out, log)
    code, out, log = _run_decide_step(tmp_path / "vacia", 'echo "[]"')
    assert code == 0 and out == "due=true\n", (code, out, log)


def test_every_workflow_that_launches_the_bot_is_named_where_the_bot_is():
    """Quien lanza update.yml sube GITHUB_RUN_NUMBER (el orden de cada pasada) y, para parar las pasadas, hay
    que desactivarlo: los comentarios de update.yml y de reloj.yml los nombran a todos (el reloj, que lo
    lanza, y las tandas de la federación que lo lanzan al subir sus raw)."""
    launchers = sorted(f.name for f in WF_DIR.glob("*.yml")
                       if "gh workflow run update.yml" in f.read_text(encoding="utf-8"))
    assert "reloj.yml" in launchers and "detalle-federacion.yml" in launchers, launchers
    for name in ("update.yml", "reloj.yml"):
        head = "\n".join(line for line in (WF_DIR / name).read_text(encoding="utf-8").splitlines()
                         if line.lstrip().startswith("#"))
        missing = [f for f in launchers if f != name and f not in head]
        assert not missing, (name, missing)


def test_how_to_wake_the_clock_after_60_days_is_written_down():
    """En un repositorio público GitHub desactiva los workflows con schedule tras 60 días sin actividad, sin
    nada en rojo: reloj.yml, docs/federacion.md y el arranque de temporada dicen cómo verlo y reactivarlo (en
    verano de 2026 hubo 43 días sin commits)."""
    for path in (WF_DIR / "reloj.yml", ROOT / "docs" / "federacion.md", ROOT / "docs" / "temporada-nueva.md"):
        text = path.read_text(encoding="utf-8")
        assert "gh workflow enable reloj.yml" in text and "disabled_inactivity" in text, path.name
        assert "60 días" in text, path.name


def test_the_clock_cadence_is_the_bots_and_a_pass_fits_in_the_shortest_one():
    """La cadencia base del reloj es la del bot (update_fiflp.PASS_EVERY: de ella salen la frescura de los
    prioritarios, sus turnos y la franja de run_number), con la misma zona horaria que la base; y el job
    entero de update.yml (su timeout) cabe en la cadencia más corta, la de las ventanas, menos la holgura."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import reloj_pasadas
    import update_fiflp
    assert reloj_pasadas.BASE == update_fiflp.PASS_EVERY
    assert reloj_pasadas.HOT_AFTER == update_fiflp.HOT_AFTER
    assert reloj_pasadas.LOCAL_ZONE == update_fiflp.LOCAL_ZONE
    timeout = _load("update.yml")["jobs"]["update"]["timeout-minutes"]
    assert timedelta(minutes=timeout) < reloj_pasadas.WINDOW - reloj_pasadas.SLACK


def test_two_passes_in_a_row_do_not_step_on_each_other():
    """Con una pasada cada 1-2 h (y las tandas de la federación lanzando el bot), dos pasadas seguidas no se
    pisan: la concurrency update-data las pone en fila (sin cancelar la que corre); cada una parte del main de
    cuando arranca (checkout ref: main), con la base y data-health.json que subió la anterior; y al subir,
    si main se ha movido (una tanda sube su raw), se rebasa con --autostash y se reintenta, también el
    diagnóstico de una pasada fallida (hasta el 16/10/2026, un git push a secas que fallaba si main se
    movía). Un conflicto aborta el rebase y se deja para la pasada siguiente."""
    data = _load("update.yml")
    steps = _steps(data, "update")
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "main"
    for name in ("Commit y push si hay cambios", DIAGNOSTICO):
        run = next(s for s in steps if s.get("name") == name)["run"]
        assert "for intento in 1 2 3" in run and "git pull --rebase --autostash origin main" in run, name
        assert "git rebase --abort" in run, name


DIAGNOSTICO = "Publicar diagnóstico si la fuente o las pruebas fallan"
MOTIVO_PRUEBAS = "las pruebas fallaron: los datos de esta pasada no se publicaron"


def _update_step(name):
    steps = _steps(_load("update.yml"), "update")
    return steps, next(s for s in steps if s.get("name") == name)


def test_update_suites_have_ids_for_the_diagnosis():
    """El paso de diagnóstico mira si fallaron las pruebas (steps.pytest y steps.node): sus ids, y solo tras
    una base sana (que solo se comprueba tras un scrape bueno)."""
    for name, step_id in (("Tests Python (bloquean el commit si fallan)", "pytest"),
                          ("Tests Node (bloquean el commit si fallan)", "node")):
        _, step = _update_step(name)
        assert step.get("id") == step_id, name
        assert step.get("if") == "steps.base.outcome == 'success'", name


BASE_SANA = "Base sana (bloquea el commit si falla)"
MOTIVO_BASE = "la base de datos no pasó la comprobación: los datos de esta pasada no se publicaron"


def test_update_comprueba_la_base_antes_de_las_pruebas():
    """Fase 4: la base se comprueba (base_sana.py: integridad, referencias, WAL volcado y tamaño) después de la
    lectura y antes de las pruebas y del commit; si falla, ni pruebas ni commit (sin continue-on-error), y el
    diagnóstico lo publica con su motivo."""
    steps, step = _update_step(BASE_SANA)
    names = [s.get("name") for s in steps]
    ids = [s.get("id") for s in steps]
    assert step.get("id") == "base"
    assert step.get("if") == "steps.scrape.outcome == 'success'"
    assert step["run"].strip() == "python3 scripts/base_sana.py --salud"
    assert not step.get("continue-on-error")
    assert ids.index("scrape") < ids.index("base") < ids.index("pytest") < ids.index("node") \
        < names.index("Commit y push si hay cambios") < names.index(DIAGNOSTICO)
    _, diag = _update_step(DIAGNOSTICO)
    assert "steps.base.outcome == 'failure'" in diag["if"]
    assert "${{ steps.base.outcome }}" in (diag.get("env") or {}).values(), "el resultado de la base, por env"
    commit = next(s for s in steps if s.get("name") == "Commit y push si hay cambios")
    assert commit["if"] == "success() && steps.scrape.outcome == 'success'", "una base mala lo deja sin commit"


def test_update_publishes_the_diagnosis_when_the_source_or_the_tests_fail():
    """Fase 2B (14/11/2026): hasta entonces, con pruebas en rojo no se publicaba nada, tampoco el diagnóstico.
    Corre si falló el scrape o una de las suites (no si solo falló el push de los datos: un conflicto se
    rehace en la pasada siguiente). Si fallaron las pruebas, parte del data-health.json publicado (el de
    esta pasada da por leído lo que no se publica) y lo marca en rojo; solo sube ese fichero y acaba en
    rojo."""
    steps, step = _update_step(DIAGNOSTICO)
    assert not any(s.get("name") == "Publicar diagnóstico si la fuente falla" for s in steps)
    assert step["if"] == ("${{ !cancelled() && (steps.scrape.outcome == 'failure' || "
                          "steps.pytest.outcome == 'failure' || steps.node.outcome == 'failure' || "
                          "steps.base.outcome == 'failure') }}")
    commit = next(s for s in steps if s.get("name") == "Commit y push si hay cambios")
    assert steps.index(commit) < steps.index(step)
    assert "${{ steps.scrape.outcome }}" in (step.get("env") or {}).values(), "el resultado del scrape, por env"
    run = step["run"]
    assert "${{" not in run
    restore = run.index("git checkout HEAD -- data-health.json")
    assert restore < run.index(f'python3 scripts/source_health.py marcar "{MOTIVO_PRUEBAS}"')
    assert re.findall(r"git add .*", run) == ["git add data-health.json"], "nunca otro fichero"
    assert 'git commit -m "Estado de las fuentes' in run
    assert [l.strip() for l in run.strip().splitlines()][-1] == "exit 1"


def _run_diagnosis_step(tmp_path, scrape_outcome):
    """El guion de verdad del paso de diagnóstico, con bash, en un clon de un repositorio de mentira (con su
    remoto) que tiene un data-health.json publicado y un source_health.py de mentira que hace de `marcar`.
    La pasada deja data-health.json y un data-x.js cambiados sin subir. Devuelve (código de salida, el
    data-health.json del remoto, los ficheros del último commit del remoto, la salida)."""
    _, step = _update_step(DIAGNOSTICO)
    tmp_path.mkdir(parents=True)
    git_env ={**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
    (tmp_path / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n[user]\n\tname = t\n\temail = t@t\n")

    def git(*args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, env=git_env, check=True, capture_output=True,
                              text=True).stdout

    remote, work = tmp_path / "remoto.git", tmp_path / "clon"
    git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(work), cwd=tmp_path)
    (work / "scripts").mkdir()
    (work / "scripts" / "source_health.py").write_text(
        "import json, sys\n"
        "assert sys.argv[1] == 'marcar'\n"
        "d = json.load(open('data-health.json'))\n"
        "d['runHealth'] = {'ok': False, 'reasons': [sys.argv[2]]}\n"
        "json.dump(d, open('data-health.json', 'w'))\n", encoding="utf-8")
    (work / "data-health.json").write_text('{"publicado": true}', encoding="utf-8")
    (work / "data-x.js").write_text("publicado", encoding="utf-8")
    git("add", ".", cwd=work)
    git("commit", "-m", "publicado", cwd=work)
    git("push", "origin", "main", cwd=work)
    (work / "data-health.json").write_text('{"de esta pasada": true}', encoding="utf-8")
    (work / "data-x.js").write_text("de esta pasada", encoding="utf-8")
    env = {**git_env, **_diagnosis_env(step, scrape_outcome, "success" if scrape_outcome == "success" else "skipped")}
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env=env, capture_output=True, text=True,
                          timeout=60)
    published = json.loads(git("show", "main:data-health.json", cwd=remote))
    files = git("show", "--name-only", "--format=", "main", cwd=remote).split()
    return done.returncode, published, files, done.stdout + done.stderr


def _diagnosis_env(step, scrape_outcome, base_outcome):
    """El env: del paso de diagnóstico con lo que GitHub interpolaría en él."""
    outcomes = {"${{ steps.scrape.outcome }}": scrape_outcome, "${{ steps.base.outcome }}": base_outcome}
    env = {k: outcomes.get(v, v) for k, v in (step.get("env") or {}).items()}
    assert not any("${{" in v for v in env.values()), env
    return env


def test_guion_de_diagnostico_con_base_mala(tmp_path):
    """Foco 1 de la revisión de la fase 4: una pasada cuya base no pasa la comprobación no publica ni datos ni
    base, y la portada lo dice. Los guiones de verdad de «Base sana» y del diagnóstico, uno tras otro, con
    base_sana.py y source_health.py de verdad (copiados con lo que importan), en un clon de un repositorio de
    mentira con su remoto: la pasada deja la base con una página pisada, un data-x.js y su data-health.json."""
    import shutil
    import sqlite3
    _, base_step = _update_step(BASE_SANA)
    _, step = _update_step(DIAGNOSTICO)
    db_fixture = tmp_path / "base.db"
    con = sqlite3.connect(db_fixture)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, texto TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"fila {i} " * 30) for i in range(300)])
    con.commit()
    page_size = con.execute("PRAGMA page_size").fetchone()[0]
    con.close()
    published_db = db_fixture.read_bytes()
    git, remote, work, env = _repo(tmp_path / "repo", {"data-x.js": "publicado", "data-health.json": json.dumps(
        {"version": 1, "season": "2026-2027", "runHealth": {"ok": True}, "groups": {}})})
    (work / "scripts").mkdir()
    for name in ("base_sana.py", "source_health.py", "portal_config.py", "escritura.py"):
        shutil.copy2(ROOT / "scripts" / name, work / "scripts" / name)
    (work / "futbolbase.db").write_bytes(published_db)
    git("add", ".", cwd=work)
    git("commit", "-m", "los guiones y la base", cwd=work)
    git("push", "origin", "main", cwd=work)
    # La pasada: datos nuevos, su informe y la base con la página 3 pisada con ceros.
    (work / "data-x.js").write_text("de esta pasada", encoding="utf-8")
    (work / "data-health.json").write_text('{"de esta pasada": true}', encoding="utf-8")
    with open(work / "futbolbase.db", "r+b") as f:
        f.seek(2 * page_size)
        f.write(b"\0" * page_size)
    done = subprocess.run(["bash", "-e", "-c", base_step["run"]], cwd=work, env=env, capture_output=True, text=True,
                          timeout=120)
    log = done.stdout + done.stderr
    assert done.returncode == 1, log
    assert "la base de datos no pasa la comprobación de integridad: " in done.stdout, log
    assert json.loads((work / "data-health.json").read_text()) == {"de esta pasada": True}, "--salud no lo toca"
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env={**env, **_diagnosis_env(step, "success", "failure")},
                          capture_output=True, text=True, timeout=60)
    log += done.stdout + done.stderr
    assert done.returncode == 1, log
    assert _last_commit(git, remote) == ["data-health.json"], log
    published = json.loads(git("show", "main:data-health.json", cwd=remote))
    health = published.pop("runHealth")
    assert health["ok"] is False and health["reasons"] == [MOTIVO_BASE] and health["since"], log
    assert published == {"version": 1, "season": "2026-2027", "groups": {}}, log
    assert git("show", "main:data-x.js", cwd=remote) == "publicado"
    blob = subprocess.run(["git", "show", "main:futbolbase.db"], cwd=remote, env=env, capture_output=True, check=True)
    assert blob.stdout == published_db, "la base mala no se sube"


def test_the_diagnosis_after_failed_tests_publishes_the_published_report_in_red(tmp_path):
    """Con las pruebas en rojo: el data-health.json publicado (no el de esta pasada), con runHealth en rojo
    por las pruebas, y nada más; el job, en rojo. Con el scrape en rojo, el de esta pasada, como antes."""
    code, published, files, log = _run_diagnosis_step(tmp_path / "pruebas", "success")
    assert code == 1, log
    assert published == {"publicado": True, "runHealth": {"ok": False, "reasons": [MOTIVO_PRUEBAS]}}, log
    assert files == ["data-health.json"], log
    code, published, files, log = _run_diagnosis_step(tmp_path / "fuente", "failure")
    assert code == 1, log
    assert published == {"de esta pasada": True}, log
    assert files == ["data-health.json"], log


def test_a_pass_in_red_turns_the_job_red_after_publishing():
    """Fase 2B: el veredicto de la pasada (runHealth) pone el job en rojo, pero después del commit: los
    datos de los grupos leídos bien ya están publicados. Solo si todo fue bien hasta ahí (si no, el job ya
    está en rojo)."""
    steps, step = _update_step("Pasada en rojo")
    assert step.get("if") == "success()"
    assert step["run"].strip() == "python3 scripts/source_health.py veredicto"
    for name in ("Commit y push si hay cambios", DIAGNOSTICO):
        assert steps.index(next(s for s in steps if s.get("name") == name)) < steps.index(step), name


def test_update_logs_the_federation_pass_as_it_goes():
    """El tiempo de cada grupo se mide en el log (plazo global y rotación de update_fiflp.py): sin
    búfer, cada línea sale con su hora y un corte por tiempo no se lleva el final del log."""
    steps = _steps(_load("update.yml"), "update")
    scrape = next(s for s in steps if "fetch_futbolaspalmas" in (s.get("run") or ""))
    assert scrape["env"].get("PYTHONUNBUFFERED") == "1"
    assert scrape["env"].get("FIFLP_UPDATE") == "1"


def test_update_admite_pasada_de_pocas_categorias():
    """A mano, una pasada puede leer solo algunas categorías (la entrada cats, que llega a FIFLP_CATS de
    update_fiflp.update_groups): así la primera de un repositorio nuevo es pequeña. El reloj y las tandas la
    lanzan sin entradas: vacía, se leen todas, como siempre. Y va por env, no interpolada en el guion."""
    data = _load("update.yml")
    entrada = _triggers(data)["workflow_dispatch"]["inputs"]["cats"]
    assert entrada["required"] is False and entrada["default"] == ""
    assert entrada["type"] == "string"
    paso = next(s for s in _steps(data, "update") if s.get("id") == "scrape")
    assert paso["env"]["FIFLP_CATS"] == "${{ inputs.cats }}"
    assert "${{" not in paso["run"], "la entrada va por env, no interpolada en el guion"


def test_update_prints_the_runner_ip_before_the_bot_and_never_fails():
    """Diagnóstico del freno de la federación (15/10/2026): la IP pública del runner en el log, antes del
    paso del bot, para cruzar frenos con IPs. Nunca para el job (continue-on-error, tope de 5 s y una
    alternativa si curl falla), sin secretos, sin variables ni nada interpolado."""
    steps = _steps(_load("update.yml"), "update")
    runs = [(s.get("run") or "") for s in steps]
    ip = next(i for i, r in enumerate(runs) if "api.ipify.org" in r)
    bot = next(i for i, r in enumerate(runs) if "fetch_futbolaspalmas" in r)
    step = steps[ip]
    assert ip < bot
    assert step.get("continue-on-error") is True and step.get("timeout-minutes", 99) <= 2
    assert "--max-time 5" in step["run"] and "||" in step["run"]
    assert "${{" not in step["run"] and not step.get("env") and "secrets" not in step["run"]


def test_update_no_abre_issues():
    """Sin aviso por issue de las competiciones nuevas (13/11/2026): el repositorio tiene las issues
    desactivadas, el paso (avisar_competiciones.py) fallaba en cada pasada tapado por continue-on-error y
    no se quieren avisos fuera de la web. Las nuevas siguen en newCompetitions de data-health.json, que
    enseña «Datos y fuentes» (update_fiflp.check_competitions)."""
    data = _load("update.yml")
    # actions: write desde la fase 2D (14/11/2026), solo para lanzar activar.yml (su paso, el único con GH_TOKEN).
    assert data["permissions"] == {"contents": "write", "actions": "write"}
    assert "permissions" not in data["jobs"]["update"], "los del job sustituirían a los del workflow"
    for step in _steps(data, "update"):
        assert "avisar_competiciones" not in (step.get("run") or ""), step.get("name")
        assert "gh issue" not in (step.get("run") or ""), step.get("name")
        assert "GH_TOKEN" not in (step.get("env") or {}) or step.get("name") == LANZAR, step.get("name")
    assert not (ROOT / "scripts" / "avisar_competiciones.py").exists()


def test_update_stages_all_generate_js_outputs():
    """generate_js.py (via fetch_futbolaspalmas.py) writes data-*.js,
    index.html (?v= bump) and sw.js (CACHE_NAME bump, C3/C4). The old
    explicit list silently dropped data-seasons.js and data-season-*.js."""
    runs = _runs(_load("update.yml"), "update")
    commit_run = next(r for r in runs if "git add" in r)
    for needed in ("data-*.js", "index.html", "sw.js", "futbolbase.db"):
        assert needed in commit_run, f"update.yml git add must stage {needed}"


def test_update_gates_db_commit_on_published_changes():
    """futbolbase.db churns every run (SQLite header) even when no data-*.js
    changes -> ~13/14 noise commits. The commit must be gated on the published
    artifacts: stage data-*.js/index.html/sw.js first, and only add the DB (and
    commit) when that set actually changed (review 2026-06-15, #3)."""
    runs = _runs(_load("update.yml"), "update")
    commit_run = next(r for r in runs if "git commit" in r)
    lines = commit_run.splitlines()
    pub_idx = next(
        i for i, l in enumerate(lines)
        if re.search(r"git add .*data-\*\.js.*index\.html.*sw\.js", l)
    )
    assert "futbolbase.db" not in lines[pub_idx], (
        "the first git add must NOT stage futbolbase.db (that is the churn we gate)"
    )
    gate_idx = next(i for i, l in enumerate(lines) if "git diff --cached --quiet" in l)
    db_idx = next(i for i, l in enumerate(lines) if re.search(r"git add .*futbolbase\.db", l))
    assert pub_idx < gate_idx < db_idx, (
        "futbolbase.db must be staged only inside the else branch, after the "
        "published-artifact gate"
    )


def _run_commit_step(tmp_path, actas_bot=True, data_changed=False):
    """El guion de verdad de «Commit y push si hay cambios», con bash, en un clon de un repositorio de mentira
    (con su remoto) con data-x.js, futbolbase.db y data-health.json publicados. La pasada cambia la base (sus
    bytes cambian siempre) y, si `actas_bot`, guarda un original nuevo (scripts/actas_bot_*.jsonl); si
    `data_changed`, también un dato publicado. Devuelve (código de salida, ficheros del último commit del
    remoto, la salida)."""
    _, step = _update_step("Commit y push si hay cambios")
    tmp_path.mkdir(parents=True)
    git_env = {**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
               "RUNNER_TEMP": str(tmp_path / "runner")}
    (tmp_path / "runner").mkdir()
    (tmp_path / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n[user]\n\tname = t\n\temail = t@t\n")

    def git(*args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, env=git_env, check=True, capture_output=True,
                              text=True).stdout

    remote, work = tmp_path / "remoto.git", tmp_path / "clon"
    git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(work), cwd=tmp_path)
    (work / "scripts").mkdir()
    for name, text in (("data-x.js", "publicado"), ("index.html", "i"), ("sw.js", "s"), ("futbolbase.db", "base"),
                       ("data-health.json", "{}")):
        (work / name).write_text(text, encoding="utf-8")
    git("add", ".", cwd=work)
    git("commit", "-m", "publicado", cwd=work)
    git("push", "origin", "main", cwd=work)
    (work / "futbolbase.db").write_text("base con otros bytes", encoding="utf-8")
    if actas_bot:
        (work / "scripts" / "actas_bot_2026-2027_benjamin.jsonl").write_text('{"cod_acta":1}\n', encoding="utf-8")
        (work / "scripts" / ".actas_bot_2026-2027_benjamin.jsonl.x.tmp").write_text("a medias", encoding="utf-8")
    if data_changed:
        (work / "data-x.js").write_text("de esta pasada", encoding="utf-8")
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env=git_env, capture_output=True, text=True,
                          timeout=60)
    files = git("show", "--name-only", "--format=", "main", cwd=remote).split()
    return done.returncode, files, done.stdout + done.stderr


def test_update_commits_the_bots_acta_originals_always_and_only_in_the_data_commit(tmp_path):
    """Fase 2C (14/11/2026): el bot guarda el original de cada acta que lee (scripts/actas_bot_*.jsonl,
    actas_bot.py). Se suben siempre, como data-health.json: una relectura de las ya importadas no cambia nada
    publicado (y la base no se sube), pero su original sí. Después de la puerta de la base (no la abren), solo
    en el paso «Commit y push si hay cambios» (el de diagnóstico sube solo data-health.json: arriba), y sin
    fallar si no hay ninguno."""
    _, step = _update_step("Commit y push si hay cambios")
    lines = step["run"].splitlines()
    gate = next(i for i, l in enumerate(lines) if "git diff --cached --quiet" in l)
    add = [i for i, l in enumerate(lines) if "actas_bot_" in l and "git add" in l]
    assert len(add) == 1 and add[0] > gate and "'scripts/actas_bot_*.jsonl'" in lines[add[0]]
    assert "|| true" in lines[add[0]], "sin ningún original, el git add no casa con nada y no debe fallar"
    code, files, log = _run_commit_step(tmp_path / "solo-originales")
    assert code == 0, log
    assert files == ["scripts/actas_bot_2026-2027_benjamin.jsonl"], log          # ni la base ni el temporal
    code, files, log = _run_commit_step(tmp_path / "con-datos", data_changed=True)
    assert code == 0, log
    assert sorted(files) == ["data-x.js", "futbolbase.db", "scripts/actas_bot_2026-2027_benjamin.jsonl"], log
    code, files, log = _run_commit_step(tmp_path / "sin-originales", actas_bot=False)
    assert code == 0 and files == ["data-health.json", "data-x.js", "futbolbase.db", "index.html", "sw.js"], log


def test_update_also_commits_the_db_when_the_bot_marks_it():
    """La base guarda estado del bot que no se publica (update_fiflp: la primera pasada completa de
    un grupo recién activado, fiflp_full_pending). Con la puerta de arriba se perdía en una pasada sin
    cambios publicados y la siguiente repetía la lectura completa: el bot deja FIFLP_DB_MARK (fuera
    del repositorio) y update.yml sube la base también entonces."""
    data = _load("update.yml")
    scrape = next(s for s in _steps(data, "update") if s.get("id") == "scrape")
    mark = scrape["env"]["FIFLP_DB_MARK"]
    assert mark.startswith("${{ runner.temp }}/"), "la marca, fuera del repositorio (nunca se comitea)"
    name = mark.split("/")[-1]
    commit_run = next(r for r in _runs(data, "update") if "git commit" in r)
    gate = next(l for l in commit_run.splitlines() if "git diff --cached --quiet" in l)
    assert f'[ -f "$RUNNER_TEMP/{name}" ]' in gate, gate


# ---------------------------------------------------------------- tests.yml

def test_tests_yml_is_named_tests():
    """El modo estricto de test_build_crests.py (sus 8 pruebas @LIVE, que se saltan dentro de un bot)
    depende de que este workflow se llame exactamente «Tests»: ver _strict() en test_build_crests.py. Si
    cambiara aquí sin cambiar allí, esas pruebas se saltarían en el CI sin avisar."""
    assert _load("tests.yml").get("name") == "Tests"


def test_tests_yml_has_schedule_and_dispatch():
    trig = _triggers(_load("tests.yml"))
    assert "workflow_dispatch" in trig, "tests.yml needs workflow_dispatch"
    crons = [e.get("cron") for e in (trig.get("schedule") or [])]
    assert "30 5 * * *" in crons, "tests.yml needs the daily 05:30 UTC safety-net cron"


def test_tests_yml_node_job_uses_glob():
    runs = " ".join(_runs(_load("tests.yml"), "node-tests"))
    assert "node --test scripts/tests/test_*.mjs" in runs, (
        "node job must use the test_*.mjs glob (contract C5) so new suites "
        "like test_sp2_modules.mjs run without wiring"
    )


def test_tests_yml_paths_cover_known_gaps():
    trig = _triggers(_load("tests.yml"))
    for event in ("push", "pull_request"):
        paths = trig[event]["paths"]
        assert "scripts/**.json" in paths, f"{event} paths must include scripts/**.json"
        assert ".github/workflows/update.yml" in paths, (
            f"{event} paths must include .github/workflows/update.yml"
        )
        assert ".github/workflows/reloj.yml" in paths, f"{event} paths must include .github/workflows/reloj.yml"
        # Rediseño «Acta»: desde el corte de B2 la hoja es acta.css; un PR que
        # solo la toque debe correr las pruebas de contraste y de CSS.
        assert "acta.css" in paths, f"{event} paths must include acta.css"


def test_tests_yml_paths_cover_docs_and_pc():
    """El bot pasa todas las pruebas antes de publicar, y algunas leen el README, los documentos (las órdenes
    de gh, en test_identidad_v2.mjs), el diseño de v2 y pc/: un cambio que solo toque eso tiene que lanzar
    tests.yml, o el primer rojo sería el de la pasada siguiente del bot, que dejaría de publicar."""
    trig = _triggers(_load("tests.yml"))
    for event in ("push", "pull_request"):
        paths = trig[event]["paths"]
        for wanted in ("README.md", "docs/*.md", "docs/superpowers/specs/**", "pc/**"):
            assert wanted in paths, f"{event} paths must include {wanted}"


def test_tests_yml_runs_the_pc_tests():
    """Las pruebas de las herramientas del PC (pc/copia y pc/reloj) corren en CI, con -W error, cada una como
    dice su README: la de la copia desde su carpeta, que es la que hace importable su paquete (copia)."""
    steps = _steps(_load("tests.yml"), "pc-tests")
    runs = [(step.get("working-directory"), step.get("run") or "") for step in steps]
    assert "pip install -r scripts/requirements-tests.txt" in " ".join(run for _, run in runs)
    assert ("pc/copia", "python3 -m pytest tests -q -W error") in runs, runs
    assert (None, "python3 -m pytest pc/reloj/tests -q -W error") in runs, runs


def test_tests_yml_comprueba_la_reconstruccion():
    """La prueba lenta de scripts/reconstruir.py (RECONSTRUIR=1, minutos sobre la base de verdad) va en un paso
    propio del job de Python de tests.yml, después de la suite; la suite que pasa el bot en cada pasada la salta
    (ni update.yml ni activar.yml ponen RECONSTRUIR)."""
    steps = _steps(_load("tests.yml"), "pytest")
    pasos = [i for i, step in enumerate(steps) if "test_reconstruir.py" in (step.get("run") or "")]
    assert len(pasos) == 1, [step.get("name") for step in steps]
    paso = steps[pasos[0]]
    assert str((paso.get("env") or {}).get("RECONSTRUIR")) == "1", paso
    assert paso["run"].strip() == "python3 -m pytest scripts/tests/test_reconstruir.py -q", paso["run"]
    suite = next(i for i, step in enumerate(steps) if (step.get("run") or "").strip() == "python -m pytest scripts/tests/ -v")
    assert suite < pasos[0]
    assert not [step for step in steps if step is not paso and "RECONSTRUIR" in repr(step)]
    for name in ("update.yml", "activar.yml"):
        assert "RECONSTRUIR" not in (WF_DIR / name).read_text(encoding="utf-8"), name


def test_tests_yml_render_smoke_intact():
    runs = " ".join(_runs(_load("tests.yml"), "render-smoke"))
    assert "node scripts/tests/render-smoke.mjs" in runs


def test_tests_yml_frescura_smoke():
    """La frescura tras una subida de datos (frescura-smoke.mjs, fase 3, O6) corre en CI, en un job con
    Playwright; publica sobre una copia con python3 (generate_js y precache.py) y sin esbuild."""
    runs = _runs(_load("tests.yml"), "render-smoke")
    assert "npm install --no-save --package-lock=false playwright@1.58.0" in runs
    assert "node scripts/tests/frescura-smoke.mjs" in runs
    assert not any("empaquetar" in run for run in runs)


def test_tests_yml_aislamiento_smoke_job():
    """v1 y v2 en el mismo origen, con sus SW de verdad (aislamiento-smoke.mjs): su propio job, con
    Playwright y Chrome como los demás smokes de navegador."""
    runs = _runs(_load("tests.yml"), "aislamiento-smoke")
    assert "npm install --no-save --package-lock=false playwright@1.58.0" in runs
    assert "node scripts/tests/aislamiento-smoke.mjs" in runs


def test_tests_yml_instala_esbuild_antes_de_las_suites():
    """Las pruebas que empaquetan de verdad (test_empaquetar.py, test_publicar.py) se saltan sin esbuild:
    en tests.yml lo instala el lockfile de scripts/empaquetar antes de cada suite, para que corran; el bot
    (update.yml) y la activación (activar.yml) nunca empaquetan, y no lo instalan."""
    data = _load("tests.yml")
    for job, suite in (("pytest", "python -m pytest scripts/tests/"), ("node-tests", "node --test scripts/tests/test_*.mjs")):
        runs = _runs(data, job)
        install = next((i for i, run in enumerate(runs) if run.strip() == "npm ci --prefix scripts/empaquetar"), None)
        tests = next((i for i, run in enumerate(runs) if suite in run), None)
        assert install is not None and tests is not None and install < tests, (job, runs)
        assert any(step.get("uses") == "actions/setup-node@v5" for step in _steps(data, job)), job
    for name in ("update.yml", "activar.yml"):
        assert "empaquetar" not in (WF_DIR / name).read_text(encoding="utf-8"), name
    trig = _triggers(data)
    for event in ("push", "pull_request"):
        for wanted in ("scripts/empaquetar/**", "dist/**"):
            assert wanted in trig[event]["paths"], f"{event} paths must include {wanted}"


def test_tests_yml_pasa_las_pruebas_de_publicacion_sin_esbuild_como_el_bot():
    """El bot (update.yml, activar.yml) pasa pytest sin esbuild y tests.yml, con él: una prueba que solo falla
    sin esbuild pasaba en verde en CI y paraba al bot (revisión final de la parte II, C1 y M7). Un paso, antes
    del npm ci de empaquetar, pasa sin esbuild las que dependen de si lo hay: las que importan codigo o
    publicar, y las del precache."""
    steps = _steps(_load("tests.yml"), "pytest")
    names = [step.get("name") for step in steps]
    assert "Pruebas de publicación sin esbuild (como el bot)" in names, names
    sin = names.index("Pruebas de publicación sin esbuild (como el bot)")
    install = next(i for i, step in enumerate(steps) if (step.get("run") or "").strip() == "npm ci --prefix scripts/empaquetar")
    assert sin < install, names
    pip = next(i for i, step in enumerate(steps) if "pip install -r scripts/requirements-tests.txt" in (step.get("run") or ""))
    assert pip < sin, names
    run = steps[sin]["run"]
    assert run.startswith("python3 -m pytest ") and "npm" not in run, run
    importan = sorted(path.name for path in (ROOT / "scripts" / "tests").glob("test_*.py")
                      if re.search(r"^\s*(?:import|from)\s+(?:codigo|publicar)\b", path.read_text(encoding="utf-8"), re.M))
    for name in sorted({*importan, "test_publicar.py", "test_empaquetar.py", "test_precache.py"}):
        assert f"scripts/tests/{name}" in run, name


def test_tests_yml_pytest_installs_pyyaml():
    runs = " ".join(_runs(_load("tests.yml"), "pytest"))
    assert "pip install -r scripts/requirements-tests.txt" in runs, runs
    assert "pyyaml" in _requisitos("requirements-tests.txt"), "test_workflows.py imports yaml"


def test_python_tests_run_without_playwright():
    """El job pytest de tests.yml no instala Playwright (update.yml sí): una prueba que lo importa
    tal cual tumba el job (14/10/2026, test_bot_plazo). Las que necesitan navegador lo piden con
    pytest.importorskip, mejor dentro de la prueba o de un fixture, para no saltarse las demás."""
    runs = " ".join(_runs(_load("tests.yml"), "pytest"))
    assert "playwright" not in runs
    for path in sorted((ROOT / "scripts" / "tests").glob("test_*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not re.match(r"\s*(?:import|from)\s+playwright\b", line), f"{path.name}:{n}: {line.strip()}"


# Lo que se instala con pip va fijado en dos ficheros: con «lo último del día», una
# versión nueva de Playwright (y su Chromium) entraba en el bot sin que nadie la probara.
REQUISITOS = ROOT / "scripts"
PIP_DESDE_FICHERO = re.compile(r"pip3? install (?:--dry-run )?-r scripts/requirements-(?:tests|bot)\.txt")


def _requisitos(nombre):
    """{paquete: versión} de un fichero de requisitos, sin comentarios, líneas vacías ni `-r`."""
    fijados = {}
    for line in (REQUISITOS / nombre).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-r")):
            paquete, _, version = line.partition("==")
            fijados[paquete] = version
    return fijados


def test_requisitos_fijados():
    """Cada paquete con su versión exacta; solo lo que los workflows instalan por nombre (no es un fichero de
    bloqueo: las dependencias de cada uno las resuelve pip), y el del bot incluye el de las pruebas."""
    for nombre in ("requirements-tests.txt", "requirements-bot.txt"):
        for line in (REQUISITOS / nombre).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-r")):
                assert re.fullmatch(r"[a-z0-9_-]+==\d+(\.\d+)+", line), f"{nombre}: {line}"
    assert set(_requisitos("requirements-tests.txt")) == {"pytest", "pyyaml"}
    assert set(_requisitos("requirements-bot.txt")) == {"playwright"}
    bot = (REQUISITOS / "requirements-bot.txt").read_text(encoding="utf-8").splitlines()
    assert "-r requirements-tests.txt" in [line.strip() for line in bot]


def test_pip_solo_desde_los_ficheros():
    """Ningún workflow instala con pip un paquete por nombre: solo desde los ficheros de requisitos; y quien
    baja Chromium (playwright install) instala antes el Playwright fijado."""
    for name in sorted(WORKFLOWS):
        runs = _all_runs(name)
        for run in runs:
            for m in re.finditer(r"\bpip3?\s+install\b[^\n]*", run):
                assert PIP_DESDE_FICHERO.fullmatch(m.group(0).strip()), f"{name}: {m.group(0)}"
        texto = "\n".join(runs)
        if "playwright install" in texto:
            bot = texto.find("pip install -r scripts/requirements-bot.txt")
            assert 0 <= bot < texto.find("playwright install"), name


def test_ci_sin_playwright_de_python():
    """tests.yml instala las dependencias de las pruebas, no las del bot (sus pruebas corren sin Playwright de
    Python: test_python_tests_run_without_playwright); del fichero del bot solo comprueba que se resuelve."""
    data = _load("tests.yml")
    pytest_runs = _runs(data, "pytest")
    assert "pip install -r scripts/requirements-tests.txt" in pytest_runs
    assert "pip install -r scripts/requirements-tests.txt" in _runs(data, "pc-tests")
    for run in _all_runs("tests.yml"):
        for m in re.finditer(r"\bpip3?\s+install\b[^\n]*requirements-bot\.txt", run):
            assert "--dry-run" in m.group(0), m.group(0)
    steps = _steps(data, "pytest")
    names = [step.get("name") for step in steps]
    assert "Dependencias del bot instalables" in names, names
    paso = names.index("Dependencias del bot instalables")
    assert steps[paso]["run"].strip() == "pip install --dry-run -r scripts/requirements-bot.txt"
    instala = next(i for i, step in enumerate(steps) if "requirements-tests.txt" in (step.get("run") or ""))
    assert instala < paso, names
    trig = _triggers(data)
    for event in ("push", "pull_request"):
        assert "scripts/requirements-*.txt" in trig[event]["paths"], f"{event}: subir una versión corre las pruebas"


@pytest.mark.parametrize("name,job", [("update.yml", "update"), ("activar.yml", "activar")])
def test_node_fijado_en_el_bot(name, job):
    """El bot corre sus pruebas de Node con el Node 22 de setup-node, como tests.yml, y no con el que traiga
    la imagen del runner."""
    steps = _steps(_load(name), job)
    setup = [i for i, step in enumerate(steps) if str(step.get("uses", "")).startswith("actions/setup-node@")]
    assert len(setup) == 1, name
    assert steps[setup[0]]["with"]["node-version"] == "22", name
    node = next(i for i, step in enumerate(steps) if re.search(r"(?:^|\s)node\s", step.get("run") or ""))
    assert "node --test scripts/tests/test_*.mjs" in steps[node]["run"], (name, steps[node].get("name"))
    assert setup[0] < node, name


def test_tests_yml_paths_cover_fonts_icons_and_crests():
    """Un cambio que solo toque la fuente, los iconos o los escudos corre las
    pruebas que los miran (test_rediseno_assets, test_build_icons, test_build_crests y el precache de
    test_sw_fixes)."""
    trig = _triggers(_load("tests.yml"))
    for event in ("push", "pull_request"):
        paths = trig[event]["paths"]
        for wanted in ("fonts/**", "icons/**", "escudos/**"):
            assert wanted in paths, f"{event} paths must include {wanted}"


# La versión mayor más baja de cada acción que corre en Node 24, según sus notas de versión (plan B4,
# decisiones 12 y 55): checkout v5.0.0 («Update actions checkout to use node 24»), setup-python v6.0.0
# («Upgrade to node 24») y setup-node v5.0.0 («Upgrade action to use node24»). Otra acción, u otra
# versión, se comprueba antes en sus notas y se apunta aquí. En tests.yml y en update.yml, el bot, que
# empuja data-health.json varias veces al día y ejerce el cambio en horas; los demás workflows, en B5.
NODE24 = {"actions/checkout": "v5", "actions/setup-python": "v6", "actions/setup-node": "v5"}


@pytest.mark.parametrize("name", ["tests.yml", "update.yml", "reloj.yml", "activar.yml", "discover-fiflp.yml",
                                  "fetch-fiflp-islas.yml"])
def test_actions_run_on_node24(name):
    data = _load(name)
    uses = [step["uses"] for job in data["jobs"].values() for step in job["steps"] if "uses" in step]
    assert uses, f"{name} sin acciones"
    for ref in uses:
        action, _, version = ref.partition("@")
        assert NODE24.get(action) == version, f"{name}, {ref}: en Node 24 va {action}@{NODE24.get(action, '?')}"


# La imagen de los runners, fijada en todos los workflows (plan B4, decisión 55): ubuntu-latest pasa a
# Ubuntu 26 el 19/10/2026, y el bot, con el Python 3.11 de setup-python, podría quedarse sin él. Una
# imagen nueva se prueba antes y se cambia aquí y en los workflows a la vez.
def test_every_workflow_pins_its_runner_image():
    workflows = sorted(WF_DIR.glob("*.yml"))
    wrong = {f"{path.name} {job}": spec.get("runs-on")
             for path in workflows for job, spec in _load(path.name)["jobs"].items() if spec.get("runs-on") != "ubuntu-24.04"}
    assert workflows and wrong == {}, wrong


# ------------------------------------------------- update.yml (la subida)

def test_update_push_rebases_and_retries():
    """El bot tarda hasta ~30 min con las actas de la federación: un push ajeno a
    main en ese rato no debe tirar el trabajo (pasó el 3/10/2026: «rejected»)."""
    runs = _runs(_load("update.yml"), "update")
    commit_run = next(r for r in runs if "Actualización automática" in r and "git commit" in r)
    assert "git pull --rebase --autostash origin main" in commit_run, "con cambios sin subir, git no rebasa"
    assert "git rebase --abort" in commit_run


# ----------------------------------------------- goleadores-federacion.yml

def test_goleadores_federacion_only_commits_its_raws_even_when_cut():
    """Solo descarga y sube sus raw (la base la toca el bot al importarlos):
    con if: always() para no perder una descarga cortada, y push rebasando."""
    data = _load("goleadores-federacion.yml")
    steps = data["jobs"]["scrape"]["steps"]
    upload = next(s for s in steps if s.get("name") == "Subir los raw")
    assert upload.get("if") == "always()"
    assert "scripts/fiflp_goleadores_*_raw.json" in upload["run"]
    assert "futbolbase.db" not in upload["run"] and "data-*.js" not in upload["run"]
    assert "git pull --rebase origin main" in upload["run"]
    scrape = next(s for s in steps if "fetch_fiflp_goleadores.py" in s.get("run", ""))
    assert "$TEMPORADAS" in scrape["run"] and "${{" not in scrape["run"], "la entrada va por env, no interpolada"


def test_actas_federacion_chains_per_season_survives_a_timeout_and_stops_when_stuck():
    data = _load("actas-federacion.yml")
    assert "${{ inputs.temporada }}" in data["concurrency"]["group"], "una cadena por temporada"
    steps = data["jobs"]["scrape"]["steps"]
    scrape = next(s for s in steps if "fetch_fiflp_actas.py" in s.get("run", ""))
    assert scrape["env"].get("PYTHONUNBUFFERED") == "1", "sin búfer: el log no se pierde si se corta"
    nxt = next(s for s in steps if s.get("name") == "Siguiente tanda")
    assert nxt["if"] == "${{ !cancelled() }}"
    assert "fetched" in nxt["run"] and "unenumerated_comps" in nxt["run"]


def test_actas_federacion_no_cancela_una_tanda_en_marcha():
    """Una tanda lanzada mientras corre otra de su cadena espera: cancelarla tiraría horas de descarga."""
    assert _load("actas-federacion.yml")["concurrency"].get("cancel-in-progress") is False


def test_scrapes_launch_the_bot_to_import_what_they_uploaded():
    for name in ("actas-federacion.yml", "goleadores-federacion.yml"):
        data = _load(name)
        assert data["permissions"].get("actions") == "write", name
        step = next(s for s in data["jobs"]["scrape"]["steps"] if s.get("name") == "Importar y publicar (bot)")
        assert "gh workflow run update.yml" in step["run"] and step["if"] == "${{ !cancelled() }}", name


def test_the_bot_works_on_the_current_main_not_on_the_dispatch_commit():
    """Un workflow_dispatch en cola usa el commit del momento en que se lanzó; el bot, que sube la
    base, tiene que partir del main de cuando arranca."""
    steps = _load("update.yml")["jobs"]["update"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("ref") == "main"


# ------------------------------------------------------------ activar.yml
#
# Fase 2D (14/11/2026): activar.yml activa solo lo que el bot apuntó como nuevo (newCompetitions y newGroups
# de data-health.json): catálogo, descarga de lo pendiente, activar_auto.py, pruebas y subida. Lo lanza el bot
# (update.yml, «Lanzar la activación si hay algo nuevo», con source_health.py pendiente) o el dueño a mano;
# nunca se relanza a sí mismo: intentos cortos que se alternan con las pasadas. Los guiones
# de sus pasos se ejecutan con bash en repositorios de mentira con su remoto, con un gh de mentira que apunta
# lo que se le pide.

V2_REPO = "malolocabreralolo-tech/futbol-base-v2"
ACTIVAR_STEPS = ["Checkout", "Set up Python", "Set up Node", "Qué hay pendiente", "Instalar dependencias de test",
                 "Instalar Playwright (federación)", "Catálogo de la temporada", "Descargar lo pendiente",
                 "Subir lo descargado", "Activar", "Cambios en la web", "Base sana (bloquea el commit si falla)",
                 "Tests Python (bloquean el commit si fallan)",
                 "Tests Node (bloquean el commit si fallan)", "Subir la activación",
                 "Publicar el fallo si las pruebas fallan", "Activación en rojo"]
PENDING = "steps.pendientes.outputs.ids != ''"


def _activar():
    data = _load("activar.yml")
    assert list(data["jobs"]) == ["activar"]
    return data, data["jobs"]["activar"]


def _activar_step(name):
    _, job = _activar()
    return next(s for s in job["steps"] if s.get("name") == name)


def test_activar_is_dispatched_by_the_bot_or_by_hand_and_never_relaunches_itself():
    """Solo workflow_dispatch sin entradas (lo lanzan el bot y el dueño a mano). Ronda de arreglo 1: nunca se
    relanza a sí mismo (ni gh, ni actions: write): GitHub guarda una sola ejecución en espera por grupo de
    concurrencia y relanzarse cancelaría la pasada que espera; el intento siguiente lo lanza la pasada
    siguiente. Nada interpolado en los guiones."""
    data, job = _activar()
    trig = _triggers(data)
    assert set(trig) == {"workflow_dispatch"} and not trig["workflow_dispatch"], "sin entradas"
    text = (WF_DIR / "activar.yml").read_text(encoding="utf-8")
    runs = " ".join(step.get("run") or "" for step in job["steps"])
    assert "gh " not in runs and "GH_TOKEN" not in text and "inputs." not in text
    for step in job["steps"]:
        assert "${{" not in (step.get("run") or ""), step.get("name")


def test_activar_is_the_only_other_writer_of_the_db_and_works_on_main():
    """Un solo escritor de la base a la vez: el mismo grupo de concurrencia que update.yml, sin cancelar; parte
    del main de cuando arranca (en fila tras una pasada que acaba de subir la base); permiso para subir y
    nada más (no lanza workflows), solo en el workflow."""
    data, job = _activar()
    assert data["concurrency"] == {"group": "update-data", "cancel-in-progress": False}
    assert data["permissions"] == {"contents": "write"}
    assert "permissions" not in job
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "main"
    assert job["runs-on"] == "ubuntu-24.04"


def test_activar_steps_in_order():
    _, job = _activar()
    assert [s.get("name") for s in job["steps"]] == ACTIVAR_STEPS


def test_activar_does_nothing_when_nothing_is_pending():
    """Con SCRAPE_IDS vacío fetch_fiflp_islas.py lo bajaría TODO: sin pendientes no se instala, ni se descarga,
    ni se activa nada (y lo que viene después depende de que se activara) y el job acaba en verde."""
    _, job = _activar()
    by_name = {s["name"]: s for s in job["steps"]}
    for name in ACTIVAR_STEPS[4:10]:
        assert PENDING in by_name[name]["if"], name
    for name in ACTIVAR_STEPS[10:]:
        cond = by_name[name]["if"]
        assert "steps.activar.outcome" in cond or "steps.cambios.outputs.datos" in cond or "steps.pytest.outcome" in cond, name


def test_activar_reads_what_is_pending_and_the_tanda_without_hardcoding_it(tmp_path):
    """El guion de verdad del primer paso, sobre el repositorio (solo lee): los ids de activar_auto.py
    --pendientes y el CodTemporada de la temporada en curso (activar_auto.py --temporada), a GITHUB_OUTPUT."""
    step = _activar_step("Qué hay pendiente")
    assert step.get("id") == "pendientes"
    assert "python3 scripts/activar_auto.py --pendientes" in step["run"]
    assert "python3 scripts/activar_auto.py --temporada" in step["run"]
    out = tmp_path / "salida"
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=ROOT, env={**os.environ, "GITHUB_OUTPUT": str(out)},
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = out.read_text().splitlines()
    assert len(lines) == 2 and re.fullmatch(r"ids=[0-9,]*", lines[0]) and re.fullmatch(r"codigo=\d+", lines[1]), lines


def test_activar_refreshes_the_catalog_of_the_current_season_only():
    step = _activar_step("Catálogo de la temporada")
    assert step["run"].strip() == "python3 scripts/discover_fiflp_comps.py"
    assert step["env"]["DISCOVER_SEASONS"] == "${{ steps.pendientes.outputs.codigo }}"
    assert step.get("continue-on-error") is True, "sin catálogo nuevo se descarga con el que hay"
    assert step.get("timeout-minutes", 99) <= 15


def test_activar_downloads_both_tandas_in_short_attempts():
    """Una fase nueva son cientos de páginas y la federación frena: la descarga tiene plazo (ISLAS_HASTA,
    fetch_fiflp_islas.guardar_por_grupo guarda grupo a grupo y para al pasarlo) por debajo del timeout del
    paso, con margen para el último grupo, y nunca para el job (continue-on-error). Ronda de arreglo 1:
    intentos cortos (20 min de descarga, 30 el paso, 75 el job): un intento ocupa update-data poco más que una
    pasada. Las dos tandas de la temporada (benjamín y prebenjamín, alevín) con la misma lista: cada una filtra
    por su categoría."""
    _, job = _activar()
    step = _activar_step("Descargar lo pendiente")
    assert step.get("id") == "descarga" and step.get("continue-on-error") is True
    assert step["env"]["SCRAPE_IDS"] == "${{ steps.pendientes.outputs.ids }}"
    assert step["env"]["CODIGO"] == "${{ steps.pendientes.outputs.codigo }}"
    assert step["env"].get("PYTHONUNBUFFERED") == "1"
    run = step["run"]
    assert 'for TANDA in "$CODIGO" "${CODIGO}al"' in run
    assert 'ISLAS_SEASON="$TANDA" python3 scripts/fetch_fiflp_islas.py' in run
    minutes = int(re.search(r"ISLAS_HASTA=\$\(\( \$\(date \+%s\) \+ (\d+) \* 60 \)\)", run).group(1))
    assert (minutes, step["timeout-minutes"], job["timeout-minutes"]) == (20, 30, 75)
    # El job: la descarga entera, más preparación, catálogo, activación, pruebas y subidas (~30 min).
    assert step["timeout-minutes"] + 30 <= job["timeout-minutes"]


def _repo(tmp_path, files):
    """Un clon de un repositorio de mentira con su remoto y `files` publicados. Devuelve (git, remoto, clon,
    entorno)."""
    tmp_path.mkdir(parents=True)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
           "RUNNER_TEMP": str(tmp_path / "runner")}
    (tmp_path / "runner").mkdir()
    (tmp_path / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n[user]\n\tname = t\n\temail = t@t\n")

    def git(*args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout

    remote, work = tmp_path / "remoto.git", tmp_path / "clon"
    git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("clone", str(remote), str(work), cwd=tmp_path)
    for name, text in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text, encoding="utf-8")
    git("add", ".", cwd=work)
    git("commit", "-m", "publicado", cwd=work)
    git("push", "origin", "main", cwd=work)
    return git, remote, work, env


# El catálogo del repositorio de mentira (nunca se lee el vivo: test_catalogo_congelado.py, que busca su nombre).
FAKE_CATALOG = "scripts/fiflp_comps" + "_catalog.json"
PUBLISHED = {"data-x.js": "publicado", "index.html": "i", "sw.js": "s", "futbolbase.db": "base",
             "data-health.json": '{"publicado": true}', FAKE_CATALOG: "{}",
             "scripts/fiflp_islas_22_raw.json": "[]", "docs/temporadas/2026-2027.json": "{}"}


def _activation_run(work):
    """Lo que deja una activación en el árbol: la base, lo generado, un data-*.js nuevo, su manifiesto y
    data-health.json con el resultado."""
    for name, text in (("futbolbase.db", "base activada"), ("data-x.js", "activado"), ("data-y.js", "nuevo"),
                       ("index.html", "i2"), ("sw.js", "s2"), ("docs/temporadas/2026-2027-auto-20261114.json", "{}"),
                       ("data-health.json", '{"de esta ejecucion": true}')):
        (work / name).write_text(text, encoding="utf-8")


def _last_commit(git, remote):
    return sorted(git("show", "--name-only", "--format=", "main", cwd=remote).split())


def test_activar_uploads_what_it_downloaded_first_and_only_that(tmp_path):
    """Lo descargado (catálogo, raw y lista de grupos de la federación) se sube siempre, también tras un corte,
    antes de activar: el intento siguiente reanuda desde ahí. Nada de la base ni de lo publicado."""
    step = _activar_step("Subir lo descargado")
    assert step["if"] == "${{ !cancelled() && " + PENDING + " }}"
    git, remote, work, env = _repo(tmp_path / "descarga", PUBLISHED)
    (work / "scripts" / "fiflp_islas_22_raw.json").write_text('[{"grupo": 1}]')
    (work / "scripts" / "fiflp_islas_22_grupos.json").write_text('{"1": {}}')
    (work / FAKE_CATALOG).write_text('{"nuevo": 1}')
    (work / "futbolbase.db").write_text("otros bytes")
    (work / "data-health.json").write_text('{"otro": 1}')
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _last_commit(git, remote) == [FAKE_CATALOG, "scripts/fiflp_islas_22_grupos.json",
                                         "scripts/fiflp_islas_22_raw.json"]
    # Sin nada descargado (sin lista de grupos todavía, ni raw nuevo): nada que subir, y en verde.
    git2, remote2, work2, env2 = _repo(tmp_path / "nada", PUBLISHED)
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work2, env=env2, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and _last_commit(git2, remote2) == sorted(PUBLISHED), done.stdout + done.stderr
    for line in re.findall(r"git add .*", step["run"]):
        assert not re.search(r"futbolbase\.db|data-\*\.js|data-health\.json", line), line
    assert "git pull --rebase --autostash origin main" in step["run"] and "git rebase --abort" in step["run"]


def test_activar_runs_activar_auto_without_stopping_the_job():
    step = _activar_step("Activar")
    assert step.get("id") == "activar" and step.get("continue-on-error") is True
    assert step["run"].strip() == "python3 scripts/activar_auto.py"
    assert step["if"] == "${{ !cancelled() && " + PENDING + " }}"


def test_activar_runs_the_suites_only_when_the_web_changed(tmp_path):
    """Las suites, solo si la activación cambió lo publicado (data-*.js, index.html, sw.js o su manifiesto: la
    base cambia de bytes aunque no cambie nada, update.yml); el guion de verdad del paso que lo mira."""
    step = _activar_step("Cambios en la web")
    assert step.get("id") == "cambios"
    for name, step_id in (("Tests Python (bloquean el commit si fallan)", "pytest"),
                          ("Tests Node (bloquean el commit si fallan)", "node")):
        suite = _activar_step(name)
        assert suite.get("id") == step_id and suite["if"] == "steps.cambios.outputs.datos == 'true'", name
        assert not suite.get("continue-on-error")
    assert re.search(r"python3 -m pytest scripts/tests/", _activar_step("Tests Python (bloquean el commit si fallan)")["run"])
    assert "node --test scripts/tests/test_*.mjs" in _activar_step("Tests Node (bloquean el commit si fallan)")["run"]
    for case, change, expected in (("solo-base", "futbolbase.db", "false"), ("datos", "data-x.js", "true"),
                                   ("nuevo", "data-y.js", "true"),
                                   ("manifiesto", "docs/temporadas/2026-2027-auto-20261114.json", "true")):
        _, _, work, env = _repo(tmp_path / case, PUBLISHED)
        (work / change).write_text("cambiado", encoding="utf-8")
        (work / "data-health.json").write_text("{}", encoding="utf-8")
        out = tmp_path / case / "salida"
        done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env={**env, "GITHUB_OUTPUT": str(out)},
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0 and out.read_text() == f"datos={expected}\n", (case, done.stdout + done.stderr)


def test_activar_comprueba_la_base():
    """Fase 4: la base activada se comprueba (base_sana.py) antes de las suites, cuando se va a subir (cambió lo
    publicado); si no pasa, ni suites ni subida (sin continue-on-error: success() falso) y el mismo camino que
    con las suites en rojo («Publicar el fallo si las pruebas fallan»: la base y lo generado vuelven a lo
    publicado)."""
    _, job = _activar()
    names = [s["name"] for s in job["steps"]]
    step = _activar_step(BASE_SANA)
    assert step.get("id") == "base"
    assert step["if"] == "steps.cambios.outputs.datos == 'true'"
    assert step["run"].strip() == "python3 scripts/base_sana.py --salud"
    assert not step.get("continue-on-error")
    assert names.index("Cambios en la web") < names.index(BASE_SANA) \
        < names.index("Tests Python (bloquean el commit si fallan)") < names.index("Subir la activación") \
        < names.index("Publicar el fallo si las pruebas fallan")
    assert "steps.base.outcome == 'failure'" in _activar_step("Publicar el fallo si las pruebas fallan")["if"]
    assert _activar_step("Subir la activación")["if"].startswith("${{ success() && ")


def test_activar_commits_the_data_only_with_green_suites(tmp_path):
    """El commit de datos va después de las suites y solo con todo en verde (success(): una suite en rojo deja
    el job en rojo y el paso no corre). Con datos, la base, lo generado, el manifiesto y data-health.json; sin
    ellos (nada activado: todo falló), solo data-health.json (lo intentado y por qué: «Datos y fuentes» y el
    freno de 6 h), aunque la base haya cambiado de bytes."""
    _, job = _activar()
    names = [s["name"] for s in job["steps"]]
    step = _activar_step("Subir la activación")
    assert step["if"] == "${{ success() && steps.activar.outcome != 'skipped' }}"
    assert names.index("Tests Node (bloquean el commit si fallan)") < names.index("Subir la activación")
    assert step["env"]["DATOS"] == "${{ steps.cambios.outputs.datos }}"
    for datos, expected in (("true", ["data-health.json", "data-x.js", "data-y.js",
                                      "docs/temporadas/2026-2027-auto-20261114.json", "futbolbase.db", "index.html",
                                      "sw.js"]),
                            ("false", ["data-health.json"])):
        git, remote, work, env = _repo(tmp_path / datos, PUBLISHED)
        _activation_run(work)
        done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env={**env, "DATOS": datos},
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        assert _last_commit(git, remote) == expected, datos
    assert "for vez in 1 2 3" in step["run"] and "git pull --rebase --autostash origin main" in step["run"]
    assert "git rebase --abort" in step["run"]


FAKE_PRUEBAS = (
    "import json, sys\n"
    "assert sys.argv[1] == '--pruebas-fallaron'\n"
    "ejecucion = json.load(open(sys.argv[2]))\n"
    "d = json.load(open('data-health.json'))\n"
    "d['activation'] = {'failed': [{'reason': 'las pruebas fallaron tras activar'}], 'de': ejecucion}\n"
    "json.dump(d, open('data-health.json', 'w'))\n")


def test_when_the_suites_fail_after_activating_only_the_published_report_goes_up_in_red(tmp_path):
    """Las suites en rojo tras activar: la base y lo generado vuelven a lo publicado (también los nuevos fuera),
    y se sube solo data-health.json, el publicado, con lo intentado como fallido por las pruebas
    (activar_auto.py --pruebas-fallaron, con el informe de esta ejecución). El job, en rojo."""
    step = _activar_step("Publicar el fallo si las pruebas fallan")
    assert step["if"] == ("${{ !cancelled() && (steps.pytest.outcome == 'failure' || steps.node.outcome == 'failure' || "
                          "steps.base.outcome == 'failure') }}")
    git, remote, work, env = _repo(tmp_path / "pruebas", PUBLISHED)
    (work / "scripts" / "activar_auto.py").write_text(FAKE_PRUEBAS, encoding="utf-8")
    git("add", ".", cwd=work)
    git("commit", "-m", "el guion", cwd=work)
    git("push", "origin", "main", cwd=work)
    _activation_run(work)
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    log = done.stdout + done.stderr
    assert done.returncode == 1, log
    assert _last_commit(git, remote) == ["data-health.json"], log
    published = json.loads(git("show", "main:data-health.json", cwd=remote))
    assert published == {"publicado": True, "activation": {
        "failed": [{"reason": "las pruebas fallaron tras activar"}], "de": {"de esta ejecucion": True}}}, log
    for name in ("futbolbase.db", "data-x.js", "index.html", "sw.js"):
        assert (work / name).read_text() == PUBLISHED[name], name
    assert not (work / "data-y.js").exists() and not (work / "docs/temporadas/2026-2027-auto-20261114.json").exists()
    assert [l.strip() for l in step["run"].strip().splitlines()][-1] == "exit 1"
    assert re.findall(r"git add .*", step["run"]) == ["git add data-health.json"]


def test_activar_ends_in_red_when_something_could_not_be_activated():
    """Rojo al final si algo no se activó (activar_auto.py salió con 1), después de subir el resultado: lo que
    sí se activó ya está publicado."""
    _, job = _activar()
    step = job["steps"][-1]
    assert step["name"] == "Activación en rojo"
    assert step["if"] == "${{ !cancelled() && steps.activar.outcome == 'failure' }}"
    assert [l.strip() for l in step["run"].strip().splitlines()][-1] == "exit 1"


# ------------------------------------------ update.yml lanza activar.yml

LANZAR = "Lanzar la activación si hay algo nuevo"


def test_update_launches_activar_when_something_new_is_pending():
    """Al acabar una pasada sana, si hay competiciones o grupos nuevos y toca (source_health.py pendiente), lanza
    activar.yml sobre main (queda en fila: concurrency update-data); así pasadas e intentos se alternan. Un fallo
    al lanzarlo no pone la pasada en rojo: la pasada siguiente lo vuelve a mirar."""
    steps, step = _update_step(LANZAR)
    names = [s.get("name") for s in steps]
    assert names.index("Commit y push si hay cambios") < names.index(DIAGNOSTICO) < names.index(LANZAR) \
        < names.index("Pasada en rojo")
    assert step["if"] == "success()" and step.get("continue-on-error") is True
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "python3 scripts/source_health.py pendiente" in step["run"]
    assert f"gh workflow run activar.yml -R {V2_REPO} --ref main" in step["run"]
    assert "${{" not in step["run"]


def _run_launch(tmp_path, report, gh_exit=0):
    """El guion de verdad del paso que lanza, con el source_health.py de verdad (copiado con lo que importa:
    lee el data-health.json de la copia) y un gh de mentira. (código de salida, órdenes de gh, salida)."""
    import shutil
    _, step = _update_step(LANZAR)
    work = tmp_path / "arbol"
    (work / "scripts").mkdir(parents=True)
    for name in ("source_health.py", "portal_config.py", "escritura.py"):
        shutil.copy2(ROOT / "scripts" / name, work / "scripts" / name)
    (work / "data-health.json").write_text(json.dumps(report), encoding="utf-8")
    bin_dir, calls = tmp_path / "bin", tmp_path / "gh-llamadas"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(f'#!/bin/bash\necho "$*" >> "{calls}"\nexit {gh_exit}\n', encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "GH_TOKEN": "x"}
    done = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    return done.returncode, (calls.read_text().splitlines() if calls.exists() else []), done.stdout + done.stderr


def test_update_launch_step_runs_for_real(tmp_path):
    new = {"newCompetitions": [{"id": "55400001", "name": "LIGA X", "firstSeen": "2026-11-14"}]}
    code, calls, log = _run_launch(tmp_path / "nuevo", new)
    assert code == 0 and calls == [f"workflow run activar.yml -R {V2_REPO} --ref main"], log
    code, calls, log = _run_launch(tmp_path / "nada", {"groups": {}})
    assert code == 0 and calls == [], log
    from datetime import datetime, timezone
    def tried(reason, attempts):
        return {**new, "activation": {"at": datetime.now(timezone.utc).isoformat(), "tried": ["55400001"],
                                      "activated": [], "attempts": attempts,
                                      "failed": [{"competition": "55400001", "name": "LIGA X", "reason": reason}]}}
    # El intento siguiente de una descarga a medias, en esta misma pasada (hasta el 8.º); lo demás, a las 24 h.
    code, calls, log = _run_launch(tmp_path / "descarga-7", tried("la descarga no está completa: faltan 9 grupos", 7))
    assert code == 0 and calls == [f"workflow run activar.yml -R {V2_REPO} --ref main"], log
    code, calls, log = _run_launch(tmp_path / "descarga-8", tried("la descarga no está completa: faltan 9 grupos", 8))
    assert code == 0 and calls == [], log
    code, calls, log = _run_launch(tmp_path / "convenio", tried("sin convenio de código: LIGA X", 1))
    assert code == 0 and calls == [], log
    code, calls, log = _run_launch(tmp_path / "gh-falla", new, gh_exit=1)
    assert code != 0 and len(calls) == 1, log                 # en rojo el paso, no la pasada (continue-on-error)


def test_tests_yml_paths_cover_activar():
    trig = _triggers(_load("tests.yml"))
    for event in ("push", "pull_request"):
        assert ".github/workflows/activar.yml" in trig[event]["paths"], event


def test_how_to_stop_and_launch_activar_is_written_down():
    """docs/federacion.md dice cómo parar la activación automática (desactivar activar.yml) y cómo lanzarla a
    mano; y el arranque de temporada, que el camino manual sigue valiendo (parando también activar.yml)."""
    fed = (ROOT / "docs" / "federacion.md").read_text(encoding="utf-8")
    for order in (f"gh workflow disable activar.yml -R {V2_REPO}", f"gh workflow enable activar.yml -R {V2_REPO}",
                  f"gh workflow run activar.yml -R {V2_REPO}"):
        assert order in fed, order
    nueva = (ROOT / "docs" / "temporada-nueva.md").read_text(encoding="utf-8")
    assert f"gh workflow disable activar.yml -R {V2_REPO}" in nueva
    assert f"gh workflow enable activar.yml -R {V2_REPO}" in nueva
