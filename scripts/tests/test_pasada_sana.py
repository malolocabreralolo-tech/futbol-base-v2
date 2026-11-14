"""Pasada sana (fase 2B de v2): el bot de la federación no puede acabar en verde sin haber leído nada.

pasada_sana.veredicto juzga cada pasada (función pura: los estados de los grupos leídos y cuántos se
intentaron); update_fiflp le pasa lo de run_passes y lo guarda en data-health.json (source_health,
runHealth). Una jornada que llega vacía y la base tiene con partidos no se escribe (JornadaVacia). El
freno (grupos sin servir) y la rotación son funcionamiento normal: una pasada con freno que leyó bien
algunos grupos es sana. Sin red: las federaciones simuladas de test_bot_freno y test_alevin_activacion.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pasada_sana import veredicto  # noqa: E402


# ── El veredicto (pasada_sana.veredicto) ─────────────────────────────────────

def test_one_failure_in_three_is_not_more_than_a_third():
    assert veredicto({"A": "ok", "B": "ok", "C": "error"}, 3) == []


def test_more_than_a_third_failed_names_the_failed_groups():
    reasons = veredicto({"A": "ok", "B": "error", "C": "rejected", "D": "ok"}, 4)
    assert len(reasons) == 1 and reasons[0].startswith("fallaron 2 de 4 grupos leídos")
    assert "B" in reasons[0] and "C" in reasons[0] and "A" not in reasons[0].split(":", 1)[1]


def test_nothing_served_out_of_the_planned_groups():
    assert veredicto({}, 26) == ["la federación no sirvió ningún grupo (de 26 previstos)"]


def test_nothing_served_is_not_repeated_as_a_third_failed():
    assert veredicto({"A": "error"}, 5) == ["la federación no sirvió ningún grupo (de 5 previstos)"]


def test_nothing_to_read_is_healthy():
    assert veredicto({}, 0) == []


def test_a_braked_pass_that_read_one_group_is_healthy():
    assert veredicto({"A": "ok"}, 21) == []          # 1 leído y 20 sin servir por el freno


def test_an_empty_round_comes_first_and_the_third_rule_still_applies():
    reasons = veredicto({"A": "ok", "B": "error"}, 2, vacias=["B"])
    assert reasons[0] == "jornada leída vacía que la base tiene con partidos: B"
    assert reasons[1].startswith("fallaron 1 de 2 grupos leídos: B")


def test_an_interrupted_pass_comes_first_and_is_cut():
    reasons = veredicto({"A": "error"}, 1, interrumpida="x" * 500)
    assert reasons[0].startswith("la federación no se pudo consultar: ") and len(reasons[0]) <= 240


def test_the_codes_are_sorted_and_at_most_twelve():
    """15 grupos en error de 15: sin ningún «ok» manda «no sirvió ningún grupo», que no nombra códigos; la
    lista sale en la jornada vacía (los 15) y, con un grupo leído bien, en la del tercio."""
    estados = {f"AL{n}": "error" for n in range(15, 0, -1)}
    empty, nothing = veredicto(estados, 15, vacias=list(estados))
    assert empty == ("jornada leída vacía que la base tiene con partidos: "
                     + ", ".join(f"AL{n}" for n in range(1, 13)) + " y 3 más")
    assert nothing == "la federación no sirvió ningún grupo (de 15 previstos)"
    third, = veredicto({**estados, "PG1": "ok"}, 16)
    assert third == "fallaron 15 de 16 grupos leídos: " + ", ".join(f"AL{n}" for n in range(1, 13)) + " y 3 más"
