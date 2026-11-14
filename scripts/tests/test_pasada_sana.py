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


# ── Jornada leída vacía (update_fiflp.update_group, JornadaVacia) ─────────────

import pytest  # noqa: E402

import update_fiflp as U  # noqa: E402
from scripts.tests import test_update_fiflp as T  # noqa: E402
from scripts.tests import test_bot_freno as B  # noqa: E402
from scripts.tests import test_alevin_activacion as A  # noqa: E402

bot = B.bot                     # la pasada 1103 con data-health.json de verdad (test_bot_freno)
quiet = lambda *_: None         # noqa: E731


def counts(conn, gid):
    return [conn.execute(f"SELECT count(*) FROM {table} WHERE group_id=?", (gid,)).fetchone()[0]
            for table in ("matches", "standings")]


def six_in_round_3(conn, gid, played=False):
    """La jornada 3 en la base con los 6 cruces de los tres equipos del grupo."""
    ids = [r[0] for r in conn.execute("SELECT id FROM teams WHERE name IN ('Las Mesas Hu.', 'Tablero', 'Arucas')")]
    for home in ids:
        for away in ids:
            if home != away:
                conn.execute("""INSERT INTO matches(group_id, jornada, date, home_team_id, away_team_id, home_score,
                                away_score) VALUES (?, 'Jornada 3', '2026-10-17', ?, ?, ?, ?)""",
                             (gid, home, away, 1 if played else None, 0 if played else None))
    conn.commit()


STANDINGS = T.table([(1, 'MESAS HURACAN, U.D. LAS "A"', 3, 1, 1, 0, 0, 3, 1),
                     (2, 'ARUCAS, C.F. "A"', 0, 0, 0, 0, 0, 0, 0), (3, 'TABLERO, C.D. "A"', 0, 1, 0, 0, 1, 1, 3)])


def test_a_round_read_empty_that_the_base_has_with_matches_writes_nothing():
    conn, gid = T.seeded()
    six_in_round_3(conn, gid)
    before = counts(conn, gid)
    with pytest.raises(U.JornadaVacia, match="la jornada 3 se leyó vacía y la base tiene 6 partidos"):
        U.update_group(conn, gid, "PG1", STANDINGS, {**T.scraped_round(3, 1), "Jornada 3": []}, log=quiet)
    conn.rollback()
    assert counts(conn, gid) == before
    assert conn.execute("SELECT home_score FROM matches WHERE jornada='Jornada 1'").fetchone()[0] is None


def test_a_round_emptied_because_its_unplayed_matches_moved_is_not_empty():
    """Review Focus 5: la federación movió los partidos sin jugar de la jornada 2 a la 5, leída en la misma
    llamada (test_update_fiflp.test_an_unplayed_match_moved_by_the_federation_changes_round)."""
    conn, gid = T.seeded()
    moved = {"Jornada 2": [], "Jornada 5": [{"home": 'ARUCAS, C.F. "A"', "away": 'MESAS HURACAN, U.D. LAS "A"',
                                             "hs": None, "as": None, "date": "2026-11-07", "time": "", "venue": ""}]}
    assert U.update_group(conn, gid, "PG1", [], moved, log=quiet)[0] == "ok"
    assert conn.execute("""SELECT jornada FROM matches m JOIN teams h ON h.id=home_team_id
                           WHERE h.name='Arucas'""").fetchall() == [("Jornada 5",)]


def test_a_played_match_cannot_have_moved_so_its_round_is_empty():
    conn, gid = T.seeded()
    conn.execute("UPDATE matches SET home_score=2, away_score=2 WHERE jornada='Jornada 2'")
    moved = {"Jornada 2": [], "Jornada 5": [{"home": 'ARUCAS, C.F. "A"', "away": 'MESAS HURACAN, U.D. LAS "A"',
                                             "hs": None, "as": None, "date": "2026-11-07", "time": "", "venue": ""}]}
    with pytest.raises(U.JornadaVacia, match="la jornada 2 se leyó vacía y la base tiene 1 partido$"):
        U.update_group(conn, gid, "PG1", [], moved, log=quiet)


def test_a_group_without_rounds_in_the_base_cannot_have_an_empty_round():
    """Review Focus 5: un grupo recién activado, sin jornadas en la base, en su primera pasada completa."""
    conn, gid = T.seeded()
    conn.execute("DELETE FROM matches")
    assert U.update_group(conn, gid, "PG1", [], {"Jornada 1": [], "Jornada 2": []}, log=quiet)[0] == "ok"


# ── Lo que run_passes da para el veredicto ───────────────────────────────────

@pytest.fixture
def passes(monkeypatch):
    """Lo que devuelve cada run_passes de la prueba (la del montaje de test_bot_freno, que no lo mira)."""
    seen = []
    real = U.run_passes
    monkeypatch.setattr(U, "run_passes", lambda *a, **k: seen.append(real(*a, **k)) or seen[-1])
    return seen


def judged(result):
    return veredicto(result["estados"], result["previstos"], result["vacias"])


def test_a_braked_pass_is_healthy(bot, capsys, passes):
    """Review Focus 1: el freno de la pasada 1103 que no se pasa: PG2 y FF5 leídos, AL4 sin servir y los
    demás, a otra pasada. Todos cuentan como previstos; el veredicto, sana."""
    data, web, F, log = bot(capsys, serve=B.SERVED_1103)
    result, = passes
    assert result == {"estados": {"PG2": "ok", "FF5": "ok"}, "previstos": len(B.ALL), "vacias": []}
    assert data["run"]["unserved"] == ["AL4"] and judged(result) == []


class Forbidden(B.Federation):
    """La federación que sirve un 403 a todo."""

    def page(self):
        page = B.Page(self)
        plain = page.goto
        page.goto = lambda url, wait_until=None, timeout=None: plain(url, wait_until, timeout) and B.Response(403)
        return page


def test_a_pass_where_the_federation_forbids_everything_is_red(bot, capsys, passes):
    data, web, F, log = bot(capsys, web=Forbidden)
    result, = passes
    assert result["estados"] == {} and result["previstos"] == len(B.ALL) and result["vacias"] == []
    assert judged(result) == [f"la federación no sirvió ningún grupo (de {len(B.ALL)} previstos)"]
    assert "responde 403" in log


def test_a_pass_with_more_than_a_third_of_its_groups_in_error_is_red(bot, capsys, passes):
    dead = {"AL1", "FF1", "PG1", "FF2"}
    data, web, F, log = bot(capsys, dead=dead)
    result, = passes
    assert result["estados"] == {code: "error" if code in dead else "ok" for code in B.ALL}
    assert judged(result) == ["fallaron 4 de 10 grupos leídos: AL1, FF1, FF2, PG1"]


def test_an_empty_round_in_a_pass_is_an_error_and_writes_nothing(bot, capsys, passes):
    """La jornada 3 de FF1 llega vacía (el lector de prueba no trae partidos en ella) y la base la tiene con
    un partido sin jugar que no sale en otra jornada leída: FF1 en error, sin escribir su jornada 2."""
    conn = B.season()
    teams = dict(B.GROUPS[i][::2] for i in range(len(B.GROUPS)))["FF1"]
    ids = [conn.execute("SELECT id FROM teams WHERE name=?", (t,)).fetchone()[0] for t in teams]
    conn.execute("""INSERT INTO matches(group_id, jornada, date, home_team_id, away_team_id)
                    VALUES (?, 'Jornada 3', '2026-10-03', ?, ?)""", (B.ID["FF1"], ids[1], ids[0]))
    conn.commit()
    before = B.matches(conn, "FF1")
    data, web, F, log = bot(capsys, conn=conn)
    result, = passes
    assert result["vacias"] == ["FF1"] and result["estados"]["FF1"] == "error"
    assert data["groups"]["FF1"]["status"] == "error"
    assert "la jornada 3 se leyó vacía y la base tiene 1 partido" in data["groups"]["FF1"]["message"]
    assert B.matches(conn, "FF1") == before
    assert judged(result) == ["jornada leída vacía que la base tiene con partidos: FF1"]


# ── update_groups guarda el veredicto (source_health.set_run_health) ─────────

@pytest.fixture
def health(monkeypatch):
    seen = []
    monkeypatch.setattr(U, "flatten", lambda page, selector=None: 0)
    monkeypatch.setattr(U.source_health, "record", lambda *a, **k: None)
    monkeypatch.setattr(U.source_health, "carry", lambda *a, **k: None)
    monkeypatch.setattr(U.source_health, "set_run_health", lambda reasons, now=None: seen.append(reasons))
    return seen


def test_update_groups_saves_the_verdict_of_the_pass(monkeypatch, health, passes):
    monkeypatch.delenv("FIFLP_CATS", raising=False)
    monkeypatch.setattr(U, "_with_browser", lambda work, deadline=None: work(A._Page(), A._Fed()))
    U.update_groups(A._bot_base(), 1, today=A.date(2026, 10, 5))
    assert health == [[]] and set(passes[0]["estados"]) == {"FF1", "PG2", "AL1", "AL2", "AL3", "AL4", "AL5"}


def test_with_fiflp_cats_the_groups_of_other_categories_do_not_count(monkeypatch, health, passes):
    """Review Focus 2: FIFLP_CATS=prebenjamin. Los de las demás categorías (source_health.carry) no
    cuentan ni como leídos ni como previstos."""
    monkeypatch.setenv("FIFLP_CATS", "prebenjamin")
    monkeypatch.setattr(U, "_with_browser", lambda work, deadline=None: work(A._Page(), A._Fed()))
    U.update_groups(A._bot_base(), 1, today=A.date(2026, 10, 5))
    assert passes == [{"estados": {"PG2": "ok"}, "previstos": 1, "vacias": []}] and health == [[]]


def test_update_groups_saves_an_interrupted_pass(monkeypatch, health):
    """Sin navegador: todos los pendientes en error (como hasta ahora) y la pasada en rojo."""
    monkeypatch.delenv("FIFLP_CATS", raising=False)
    errors = []
    monkeypatch.setattr(U.source_health, "record", lambda code, url, status, *a, **k: errors.append((code, status)))

    def down(work, deadline=None):
        raise RuntimeError("sin navegador")
    monkeypatch.setattr(U, "_with_browser", down)
    U.update_groups(A._bot_base(), 1, today=A.date(2026, 10, 5))
    assert sorted(errors) == [(c, "error") for c in ("AL1", "AL2", "AL3", "AL4", "AL5", "FF1", "PG2")]
    assert health == [["la federación no se pudo consultar: sin navegador"]]
