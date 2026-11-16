#!/usr/bin/env python3
"""La frescura que da el planificador del bot (update_fiflp.plan_groups), medida con las simulaciones de las
pruebas: test_bot_pasada_corta.py (la semana, las tres semanas, la semana con el reloj que pierde ticks y con
el reloj perfecto) y test_bot_rotacion.py (la rotación con el modelo de calibración y con el cupo medido).
De cada escenario saca, como números, lo mismo que esas pruebas comparan con sus umbrales, con el nombre de
la prueba de la que sale; y dos escenarios que ninguna prueba monta, con la misma maquinaria y tres semanas:
una de cada cinco pasadas, seca (la federación frena desde la primera página), y el estado que pasa de una
pasada a otra (las comprobaciones de data-health.json, lo que plan_groups lee de `checks`), perdido cada 12.

No es una prueba (no entra en la suite: tarda minutos). Sirve para comparar otro planificador con el de hoy:
medir(planificar=otro) lo instala en lugar de plan_groups mientras dura la medida.

Uso, desde la raíz del repositorio:
  python3 scripts/tests/frescura_planificador.py                    # la tabla, con las semillas 7, 11 y 23
  python3 scripts/tests/frescura_planificador.py --json             # los números, en JSON
  python3 scripts/tests/frescura_planificador.py --semillas 7 --escenarios semana tres_semanas
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import contextlib
from datetime import timedelta
import itertools
import json
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))
import fiflp_names  # noqa: E402
import reloj_pasadas as R  # noqa: E402
import source_health  # noqa: E402
import test_bot_pasada_corta as T  # noqa: E402
import test_bot_rotacion as TR  # noqa: E402
import update_fiflp as U  # noqa: E402

SEMILLAS = (7, 11, 23)
SECA_CADA = 5            # una de cada cinco pasadas, seca
ESTADO_CADA = 12         # el estado entre pasadas, perdido cada 12 (un día a una cada 2 h)
CORTA = "test_bot_pasada_corta"
ROT = "test_bot_rotacion"


# ── El entorno de las pruebas ─────────────────────────────────────────────────

def _con(planificar, trabajo):
    """trabajo(tmp, mp) con lo que conftest.py pone a cada prueba (sin la tabla de nombres revisados y con los
    originales de las actas fuera de scripts/) y, si hay, `planificar` en lugar de plan_groups: run_passes lo
    busca en el módulo en cada pasada. Lo que imprime el bot, fuera (en las pruebas lo captura pytest). Todo se
    deshace al acabar."""
    mp = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(prefix="frescura-") as d:
        tmp = Path(d)
        try:
            mp.setattr(fiflp_names, "FED_NAMES_PATH", str(tmp / "sin-tabla.json"))
            fiflp_names.fed_alias.cache_clear()
            mp.setenv("ACTAS_BOT_DIR", str(tmp / "actas_bot"))
            if planificar is not None:
                mp.setattr(U, "plan_groups", planificar)
            with open(os.devnull, "w") as nada, contextlib.redirect_stdout(nada):
                return trabajo(tmp, mp)
        finally:
            mp.undo()
            fiflp_names.fed_alias.cache_clear()


def _reloj(semilla):
    """La semilla de los ticks del reloj: la de la prueba (1) con la temporada de la prueba (7); si no, la misma
    que la temporada, para que la variación entre semillas recoja también la de GitHub."""
    return 1 if semilla == 7 else semilla


# ── Las medidas de test_bot_pasada_corta ──────────────────────────────────────

def _freno(passes):
    """test_no_pass_waits_for_the_900_s_block (y lo mismo en el reloj)."""
    return {"pausas_max": max(p["pauses"] for p in passes),
            "espera_freno_max_s": round(max(p["paused"] for p in passes)),
            "pasadas_espera_900": sum(p["paused"] >= 600 for p in passes),
            "bloqueos_max": max(p["blocks"] for p in passes),
            "paginas_pasado_plazo": sum(t > p["deadline"] for p in passes for t, _, _ in p["requests"]),
            "minutos_pasada_max": round(max((p["end"] - p["now"]).total_seconds() for p in passes) / 60, 1)}


def _tarde(passes, season):
    """Los partidos de los prioritarios que no se leen en la primera pasada que empieza con el resultado."""
    return sum(d is None or d > 0 for _, _, d in T.priority_latency(passes, season))


def _errores(passes, s):
    """test_a_brake_is_never_an_error_…: grupos (por pasada) que quedan como error sin ser de los heredados."""
    return {"errores_por_freno": sum(1 for p in passes for c, g in p["checked"].items()
                                     if g["status"] != "ok" and c not in T.ERRORED),
            "errores_final": s["errors_end"]}


def _semana(passes, season, conn):
    s = T.summary(passes, season, conn)
    return {**_freno(passes),
            "prioritarios_hueco_max_h": round(max(T.priority_gaps(passes, season).values()), 2),
            "prioritarios_tarde": _tarde(passes, season),
            **_errores(passes, s),
            "paginas_utiles_dia": s["served_per_day"]}


def _completo(passes, season):
    """test_how_long_each_open_group_takes_to_be_read_complete: días hasta estar completo (complete_gaps)."""
    gaps = T.complete_gaps(passes, season)
    others = sorted(g for c, g in gaps.items() if c not in T.MINE)
    worst = max(gaps.values())
    return {"prioritarios_completo_max_d": round(max(gaps[c] for c in T.MINE), 2),
            "grupos_sin_lectura": sum(not v for v in T.reads(passes, season).values()),
            "maximo_abierto": sum(gaps[c] >= worst for c in T.open_complete_gaps(passes, season)),
            "completo_max_d": round(worst, 2),
            "completo_mediana_d": round(statistics.median(gaps.values()), 2),
            # El percentil 70 de rango: ≤ 5 días si y solo si siete de cada diez lo están (lo que afirma la prueba).
            "otros_p70_d": round(others[math.ceil(0.7 * len(others)) - 1], 2),
            "otros_en_5d": round(sum(g <= 5 for g in others) / len(others), 3)}


def _agotadas(conn):
    return conn.execute("""SELECT count(*) FROM matches WHERE fiflp_acta IS NOT NULL AND acta_tries >= ?
                           AND (cod_acta IS NULL OR cod_acta <> fiflp_acta)""", (U.MAX_ACTA_TRIES,)).fetchone()[0]


def semana(tmp, mp, semilla):
    passes, season, conn = T.simulate(tmp, mp, seed=semilla)
    return _semana(passes, season, conn)


def tres_semanas(tmp, mp, semilla):
    passes, season, conn = T.simulate(tmp, mp, days=T.LONG_DAYS, seed=semilla)
    return _completo(passes, season)


def reloj(tmp, mp, semilla):
    """test_with_the_clock_one_pass_an_hour_on_match_days_and_nothing_breaks."""
    passes, season, conn = T.simulate(tmp, mp, seed=semilla, times=T.clock_times(seed=_reloj(semilla)))
    s = T.summary(passes, season, conn)
    freno = _freno(passes)
    freno.pop("minutos_pasada_max")           # la prueba del reloj no lo mira
    try:
        minutes = T.priority_minutes(passes, season)
    except StopIteration:               # un partido suyo que no se leyó nunca: sin minutos que dar
        minutes = None
    return {"pasadas": len(passes), "pasadas_en_ventanas": sum(1 for p in passes if R.window(p["now"])),
            **freno, **_errores(passes, s),
            "prioritarios_tarde": _tarde(passes, season),
            "prioritarios_min_mediana": round(statistics.median(minutes), 1) if minutes else None,
            "prioritarios_min_max": round(max(minutes), 1) if minutes else None,
            "prioritarios_hueco_max_h": round(max(T.priority_gaps(passes, season).values()), 2),
            "paginas_utiles_dia": s["served_per_day"],
            "actas_agotadas": _agotadas(conn), "actas_pendientes_final": s["pending_actas_end"]}


def reloj_perfecto(tmp, mp, semilla):
    """test_with_a_perfect_clock_the_actas_of_las_mesas_do_not_wait_for_the_end_of_the_window."""
    passes, season, conn = T.simulate(tmp, mp, seed=semilla, times=T.clock_times(loss=0, delay=0))
    hours = T.mine_acta_hours(passes, season)
    read = [h for _, _, h in hours if h is not None]
    return {"actas_prioritarios": len(hours), "actas_prioritarios_sin_leer": len(hours) - len(read),
            "actas_prioritarios_horas_max": round(max(read), 2) if read else None,
            "actas_agotadas": _agotadas(conn)}


# ── Los dos escenarios nuevos ─────────────────────────────────────────────────

def _web_seca(cada):
    """La federación de test_bot_pasada_corta con una de cada `cada` pasadas seca: esa pasada no tiene cupo y
    frena desde la primera página (espera el primer bloqueo y, al pasar, vuelve a frenar: el segundo freno la
    acaba). simulate crea una Web por pasada."""
    cuenta = itertools.count()

    class WebSeca(T.Web):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            if next(cuenta) % cada == cada - 1:
                self.per_ip = 0
    return WebSeca


def perder_estado():
    """Lo que el planificador de hoy recibe de la pasada anterior, perdido: las comprobaciones por grupo de
    data-health.json (status y checkedAt: stale, hot_reason, el orden de los prioritarios, los cerrados que
    descansan, retry_actas y scorers_due). La base sigue (sus actas e intentos son datos, no turnos)."""
    path = source_health.REPORT_PATH
    report = json.loads(path.read_text())
    report.pop("groups", None)
    path.write_text(json.dumps(report))


def _begin_sin_estado(cada):
    """source_health.begin, que simulate llama al empezar cada pasada, perdiendo antes el estado (perder_estado)
    en las pasadas `cada`, 2·`cada`…"""
    original, cuenta = source_health.begin, itertools.count()

    def begin(season):
        n = next(cuenta)
        if n and n % cada == 0:
            perder_estado()
        original(season)
    return begin


def _tres_semanas_con(passes, season, conn):
    """Los dos escenarios nuevos: lo de la semana y lo de las tres semanas, sobre las tres semanas."""
    return {**_semana(passes, season, conn), **_completo(passes, season)}


def seca(tmp, mp, semilla):
    mp.setattr(T, "Web", _web_seca(SECA_CADA))
    return _tres_semanas_con(*T.simulate(tmp, mp, days=T.LONG_DAYS, seed=semilla))


def estado_perdido(tmp, mp, semilla):
    mp.setattr(source_health, "begin", _begin_sin_estado(ESTADO_CADA))
    return _tres_semanas_con(*T.simulate(tmp, mp, days=T.LONG_DAYS, seed=semilla))


# ── test_bot_rotacion ─────────────────────────────────────────────────────────

CLOSED = [f"FF{i}" for i in range(1, 25) if i != 5]


def _rotacion(passes, everyone, closed=(), page=TR.PAGE):
    """Lo que afirma test_bot_rotacion.check, como números."""
    out = {"pasadas_pasado_plazo": sum(p["last_start"] > TR.BUDGET or p["end"] > TR.BUDGET + page for p in passes),
           "pasadas_sin_prioritarios": sum(not (set(TR.MINE) <= p["first"] and set(TR.MINE) <= p["scorers"])
                                           for p in passes if not p["lost"])}
    if not any(p["lost"] for p in passes):
        whole = {"ok": len(everyone), "rejected": 0, "error": 0}
        out["pasadas_no_todo_ok"] = sum(p["report"]["summary"] != whole for p in passes)
    open_groups = everyone - set(closed)
    out["hueco_abiertos"] = max(TR.gaps(passes, "first", c) for c in open_groups)
    out["hueco_goleadores"] = max(TR.gaps(passes, "scorers", c) for c in open_groups)
    if closed:
        out["hueco_cerrados"] = max(TR.gaps(passes, "first", c) for c in closed)
    return out


def _rot_81(commits):
    def run(tmp, mp, semilla):
        passes, everyone = TR.simulate(tmp, mp, commits)
        return {**_rotacion(passes, everyone), "grupos": len(everyone),
                "pasadas_sin_aplazados": sum(not p["run"]["deferred"] for p in passes),
                "goleadores_max_grupos": max(len(p["scorers"]) for p in passes)}
    return run


def _rot_cerrados(commits):
    def run(tmp, mp, semilla):
        passes, everyone = TR.simulate(tmp, mp, commits, closed=CLOSED)
        return {**_rotacion(passes, everyone, CLOSED),
                "cerrados_fuera_de_epoca": sum(
                    [sum(c in p["first"] for p in passes[e:e + 4]) for e in range(0, TR.PASSES, 4)] != [1] * 6
                    for c in CLOSED)}
    return run


def _rot_saltos(numbers, page):
    def run(tmp, mp, semilla):
        passes, everyone = TR.simulate(tmp, mp, commits=False, numbers=numbers, page=page)
        return {**_rotacion(passes, everyone, page=page), "pg3_goleadores": sum("PG3" in p["scorers"] for p in passes)}
    return run


def _rot_lentas(commits, page):
    def run(tmp, mp, semilla):
        passes, everyone = TR.simulate(tmp, mp, commits, page=page)
        return {**_rotacion(passes, everyone, page=page), "grupos_max_pasada": max(len(p["first"]) for p in passes)}
    return run


def _rot_cortes(extra, page):
    def run(tmp, mp, semilla):
        passes, everyone = TR.simulate(tmp, mp, commits=False, page=page, extra=extra)
        return {**_rotacion(passes, everyone, page=page),
                "pasadas_con_aplazados": sum(bool(p["run"]["deferred"]) for p in passes)}
    return run


def _rot_perdida(phase, page, closed=()):
    def run(tmp, mp, semilla):
        lost = {i for i in range(28) if i % 4 == phase}
        passes, everyone = TR.simulate(tmp, mp, commits=False, closed=closed, numbers=range(1000, 1028), page=page,
                                       lost=lost)
        return _rotacion(passes, everyone, closed, page)
    return run


def _rot_cupo(commits, rounds, days):
    """test_with_the_measured_quota_every_group_is_read_within_days (TR.quota_run)."""
    def run(tmp, mp, semilla):
        rows, reads, others, mine, passes = TR.quota_run(tmp, mp, commits, rounds, days)
        out = {"pasadas_pasado_plazo": sum(r["late"] > 0 for r in rows),
               "pasadas_con_error": sum(r["errors"] > 0 for r in rows),
               "pasadas_mal_freno": sum(not (r["pauses"] == 1 and r["served"] <= 2 * r["per_ip"] + 1) for r in rows)}
        if commits:
            out["prioritarios_hueco_pasadas"] = max(max(b - a for a, b in zip(m, m[1:]))
                                                    for m in ([-1] + got + [passes] for got in mine.values()))
            out["prioritarios_en_todas"] = sum(len(got) >= passes for got in mine.values())
            out["otros_media"] = round(statistics.mean(others[3:]), 2)
            out["otros_min"] = min(others[3:])
            out["nunca_leidos"] = sum(not n for n in reads.values())
            out["niveles_leidos"] = len({TR.level(c) for c, n in reads.items() if n and c not in TR.MINE})
        else:
            out["fijos_en_todas"] = sum(len(mine[c]) == passes for c in ("PG2", "B2", "FF5"))
        return out
    return run


# ── Escenarios y umbrales ─────────────────────────────────────────────────────

# {escenario: (función(tmp, mp, semilla) -> {magnitud: número}, prueba de la que sale)}
ESCENARIOS = {
    "semana": (semana, f"{CORTA}: week"),
    "tres_semanas": (tres_semanas, f"{CORTA}: three_weeks"),
    "reloj": (reloj, f"{CORTA}: clock_week"),
    "reloj_perfecto": (reloj_perfecto, f"{CORTA}: perfect_clock_week"),
    "seca_1_de_5": (seca, "nuevo (tres semanas)"),
    "estado_perdido_12": (estado_perdido, "nuevo (tres semanas)"),
}


def _check(most=3, most_closed=5, **extra):
    """Los umbrales de test_bot_rotacion.check (`most`, `most_closed`) y los propios de cada prueba."""
    return {"pasadas_pasado_plazo": ("==", 0), "pasadas_sin_prioritarios": ("==", 0),
            "pasadas_no_todo_ok": ("==", 0), "hueco_abiertos": ("<=", most), "hueco_goleadores": ("<=", most),
            "hueco_cerrados": ("<=", most_closed), **extra}


_CUPO = {"pasadas_pasado_plazo": ("==", 0), "pasadas_con_error": ("==", 0), "pasadas_mal_freno": ("==", 0)}
_CUPO_COMMITS = {**_CUPO, "prioritarios_hueco_pasadas": ("<=", 3), "prioritarios_en_todas": ("==", 0),
                 "otros_media": (">=", 2), "otros_min": (">=", 1), "nunca_leidos": ("==", 0),
                 "niveles_leidos": ("==", 3)}
_SIN_SALTOS = [n for n in range(2000, 2040) if n % 3 != 1][:TR.PASSES]
_81 = dict(grupos=("==", 81), pasadas_sin_aplazados=("==", 0), goleadores_max_grupos=("<", 81))
_PG3 = dict(pg3_goleadores=(">=", TR.PASSES // 4))
# {escenario: (función, prueba, umbrales)}: los parámetros de cada prueba, los suyos.
_ROT = {
    "81[con-commits]": (_rot_81(True), "test_81_open_groups_rotate_within_four_passes", _check(**_81)),
    "81[sin-commits]": (_rot_81(False), "test_81_open_groups_rotate_within_four_passes", _check(**_81)),
    **{f"cerrados[{n}]": (_rot_cerrados(c), "test_with_the_first_phase_closed_…",
                          _check(cerrados_fuera_de_epoca=("==", 0)))
       for n, c in (("con-commits", True), ("sin-commits", False))},
    **{f"salto[{n}]": (_rot_saltos(numbers, page), "test_a_cancelled_run_skips_a_number_…", _check(most, **_PG3))
       for n, numbers, page, most in (
           ("un-salto", [n for n in range(3000, 3030) if n != 3005][:TR.PASSES], TR.PAGE, 2),
           ("uno-de-cada-tres", _SIN_SALTOS, TR.PAGE, 2), ("uno-de-cada-tres-4s", _SIN_SALTOS, 4.0, 4),
           ("uno-de-cada-tres-5s", _SIN_SALTOS, 5.0, 4),
           ("uno-de-cada-dos-4s", list(range(4000, 4000 + 2 * TR.PASSES, 2)), 4.0, 3))},
    **{f"lentas[{n}]": (_rot_lentas(c, page), "test_with_slow_pages_the_turns_still_fit",
                        _check(grupos_max_pasada=("<", 40)))
       for n, c, page in (("con-commits", True, 5.5), ("sin-commits", False, 6.0))},
    **{f"cortes[{n}]": (_rot_cortes(extra, page), "test_slower_pages_cut_a_different_part_…",
                        _check(most, **({"pasadas_con_aplazados": (">=", 1)} if most > 3 else {})))
       for n, extra, page, most in (("8pag-5.3s", 1, 5.3, 3), ("7pag-6.5s", 0, 6.5, 7), ("7pag-6.8s", 0, 6.8, 7),
                                    ("8pag-5.5s", 1, 5.5, 7), ("8pag-6.0s", 1, 6.0, 7))},
    **{f"perdida[{n}-{phase}]": (_rot_perdida(phase, page), "test_a_pass_lost_every_day_at_the_same_hour_…",
                                 _check(most))
       for n, page, most in (("3s", TR.PAGE, 3), ("4s", 4.0, 7)) for phase in range(4)},
    **{f"perdida-cerrados[{phase}]": (_rot_perdida(phase, TR.PAGE, CLOSED),
                                      "test_a_pass_lost_every_day_does_not_starve_the_closed_…", _check(3, 7))
       for phase in range(4)},
    **{f"cupo[{n}]": (_rot_cupo(c, rounds, days), "test_with_the_measured_quota_…",
                      _CUPO_COMMITS if c else {**_CUPO, "fijos_en_todas": ("==", 3)})
       for n, c, rounds, days in (("con-commits-4pag", True, 2, 7), ("con-commits-5pag", True, 3, 7),
                                  ("sin-commits-4pag", False, 2, 2), ("sin-commits-5pag", False, 3, 2))},
}
ESCENARIOS.update({f"rotacion/{k}": (fn, f"{ROT}: {test}") for k, (fn, test, _) in _ROT.items()})

DEADLINE_MIN = U.DEADLINE_SECONDS / 60
_SEMANA = {
    "pausas_max": ("<=", 1, "test_no_pass_waits_for_the_900_s_block"),
    "espera_freno_max_s": ("<", 600, "test_no_pass_waits_for_the_900_s_block"),
    "pasadas_espera_900": ("==", 0, "test_no_pass_waits_for_the_900_s_block"),
    "bloqueos_max": ("<=", 2, "test_no_pass_waits_for_the_900_s_block"),
    "paginas_pasado_plazo": ("==", 0, "test_no_pass_waits_for_the_900_s_block"),
    "minutos_pasada_max": ("<=", DEADLINE_MIN + 1, "test_no_pass_waits_for_the_900_s_block"),
    "prioritarios_hueco_max_h": ("<=", 6 + U.DEADLINE_SECONDS / 3600,
                                 "test_every_priority_group_is_read_every_six_hours_…"),
    "prioritarios_tarde": ("==", 0, "test_every_priority_group_is_read_every_six_hours_…"),
    "errores_por_freno": ("==", 0, "test_a_brake_is_never_an_error_…"),
    "errores_final": ("==", 0, "test_a_brake_is_never_an_error_…"),
    "paginas_utiles_dia": (">=", 330, "test_more_useful_pages_per_day"),
}
_COMPLETO = {m: (op, v, "test_how_long_each_open_group_takes_to_be_read_complete") for m, op, v in (
    ("prioritarios_completo_max_d", "<=", 1), ("grupos_sin_lectura", "==", 0), ("maximo_abierto", "==", 0),
    ("completo_max_d", "<=", 8), ("completo_mediana_d", "<=", 4.5), ("otros_p70_d", "<=", 5),
    ("otros_en_5d", ">=", 0.7))}
_RELOJ_T = "test_with_the_clock_one_pass_an_hour_…"
_PERFECTO_T = "test_with_a_perfect_clock_the_actas_…"
# {escenario: {magnitud: (operador, umbral, prueba)}}. Los escenarios nuevos no tienen prueba: llevan, como
# referencia, los umbrales de la semana y de las tres semanas (lo que el plan pide no empeorar).
UMBRALES = {
    "semana": _SEMANA,
    "tres_semanas": _COMPLETO,
    "reloj": {"pasadas": (">=", 75, _RELOJ_T), "pasadas_en_ventanas": (">=", 20, _RELOJ_T),
              **{m: (op, v, _RELOJ_T) for m, (op, v, _) in _SEMANA.items() if m != "minutos_pasada_max"},
              "prioritarios_min_mediana": ("<=", 60, _RELOJ_T), "prioritarios_min_max": ("<=", 150, _RELOJ_T),
              "prioritarios_hueco_max_h": ("<=", (U.PRIORITY_MAX_AGE + timedelta(hours=2)) / timedelta(hours=1),
                                           _RELOJ_T),
              "actas_agotadas": ("==", 0, _RELOJ_T), "actas_pendientes_final": ("<=", 5, _RELOJ_T)},
    "reloj_perfecto": {"actas_prioritarios": ("==", len(T.MINE), _PERFECTO_T),
                       "actas_prioritarios_sin_leer": ("==", 0, _PERFECTO_T),
                       "actas_prioritarios_horas_max": ("<=", 8, _PERFECTO_T),
                       "actas_agotadas": ("==", 0, _PERFECTO_T)},
    "seca_1_de_5": {m: (op, v, "referencia: " + t) for m, (op, v, t) in {**_SEMANA, **_COMPLETO}.items()},
    "estado_perdido_12": {m: (op, v, "referencia: " + t) for m, (op, v, t) in {**_SEMANA, **_COMPLETO}.items()},
}


UMBRALES.update({f"rotacion/{k}": {m: (op, v, test) for m, (op, v) in umbrales.items()}
                 for k, (_, test, umbrales) in _ROT.items()})


def cumple(valor, op, umbral):
    if valor is None:
        return False
    return {"<=": valor <= umbral, "<": valor < umbral, ">=": valor >= umbral, "==": valor == umbral}[op]


# ── La medida ─────────────────────────────────────────────────────────────────

def medir(planificar=None, semilla=7, escenarios=None):
    """{escenario: {magnitud: número}}. `planificar`: la función que ordena los grupos de una pasada (None = la
    de hoy, update_fiflp.plan_groups); se instala con monkeypatch mientras dura la medida. `escenarios`: los
    nombres de ESCENARIOS que medir (None: todos). La semilla es la de la temporada simulada (y la del reloj:
    _reloj); test_bot_rotacion no tiene azar."""
    nombres = list(ESCENARIOS) if escenarios is None else list(escenarios)
    return {n: _con(planificar, lambda tmp, mp, fn=ESCENARIOS[n][0]: fn(tmp, mp, semilla)) for n in nombres}


def _uno(args):
    nombre, semilla = args
    return nombre, semilla, medir(None, semilla, [nombre])[nombre]


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def tabla(por_semilla, semillas):
    """Una fila por magnitud: escenario, magnitud, valor con la primera semilla, umbral, ¿lo cumple con todas
    las semillas?, el mínimo y el máximo entre semillas, y la prueba de la que sale (en los escenarios nuevos,
    «referencia»: ninguna prueba lo afirma)."""
    primera = semillas[0]
    filas = [("escenario", "magnitud", f"s{primera}", "umbral", "ok", "min–max", "prueba")]
    for nombre in por_semilla[primera]:
        for magnitud, valor in por_semilla[primera][nombre].items():
            op, umbral, prueba = UMBRALES.get(nombre, {}).get(magnitud, (None, None, ESCENARIOS[nombre][1]))
            valores = [por_semilla[s][nombre][magnitud] for s in semillas]
            numeros = [v for v in valores if v is not None]
            rango = f"{_fmt(min(numeros))}–{_fmt(max(numeros))}" if numeros else "—"
            ok = "" if op is None else ("sí" if all(cumple(v, op, umbral) for v in valores) else "NO")
            filas.append((nombre, magnitud, _fmt(valor), "" if op is None else f"{op} {_fmt(round(umbral, 3))}",
                          ok, rango, prueba))
    anchos = [max(len(f[i]) for f in filas) for i in range(len(filas[0]))]
    return "\n".join("  ".join(c.ljust(a) for c, a in zip(f, anchos)).rstrip() for f in filas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="los números en JSON, sin tabla")
    ap.add_argument("--semillas", type=int, nargs="+", default=list(SEMILLAS))
    ap.add_argument("--escenarios", nargs="+", choices=list(ESCENARIOS), default=list(ESCENARIOS))
    args = ap.parse_args(argv)
    inicio = time.monotonic()
    trabajos = [(n, s) for s in args.semillas for n in args.escenarios]
    # Un proceso por escenario y semilla: cada uno con su propio monkeypatch, sin estado compartido.
    por_semilla = {s: {} for s in args.semillas}
    with ProcessPoolExecutor(max_workers=min(len(trabajos), os.cpu_count() or 1)) as pool:
        for nombre, semilla, numeros in pool.map(_uno, trabajos):
            por_semilla[semilla][nombre] = numeros
    # El orden de los escenarios, el pedido.
    por_semilla = {s: {n: por_semilla[s][n] for n in args.escenarios} for s in args.semillas}
    if args.json:
        print(json.dumps({str(s): v for s, v in por_semilla.items()}, ensure_ascii=False, indent=1))
    else:
        print(tabla(por_semilla, args.semillas))
        print(f"\n{len(trabajos)} medidas en {time.monotonic() - inicio:.0f} s", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
