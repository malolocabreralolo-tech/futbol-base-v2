"""Grupos nuevos de competiciones que la web ya sigue.

check_competitions ve las competiciones nuevas, no los grupos nuevos de una que ya se sigue (un «Grupo 25»
añadido, o una fase nueva publicada como grupos de la misma competición). Por eso cada calendario que el
bot ya carga (NFG_CmpJornada con CodCompeticion y CodGrupo) se mira también por su desplegable de grupos
(select[name="grupo"]), sin pedir nada más (update_fiflp.group_select), y al final de la pasada
update_fiflp.new_groups compara lo visto con los grupos de la temporada (las URL de `groups`) y lo deja en
data-health.json (newGroups, source_health.set_new_groups), que enseña «Datos y fuentes». No se sabe de
antemano si esa página trae el desplegable: run.groupSelects dice en cuántos calendarios se vio. Sin red:
la federación simulada de test_bot_freno (con fiflp_carga.Federacion de verdad).
"""
from datetime import date, datetime, timedelta, timezone
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_health  # noqa: E402
import update_fiflp as U  # noqa: E402
from scripts.tests import test_bot_freno as B  # noqa: E402

bot = B.bot                     # la pasada con data-health.json de verdad (test_bot_freno)
TODAY = B.TODAY
KNOWN = {("900", str(n)) for n in range(1, 11)}         # los diez grupos de la base de test_bot_freno


# ── Qué es nuevo (update_fiflp.new_groups) ───────────────────────────────────

def test_a_group_the_season_does_not_have_is_new_and_a_known_one_is_not():
    seen = {"900": {str(n): f"GRUPO {n}" for n in range(1, 12)}}
    assert U.new_groups(seen, KNOWN, today=TODAY, names={"900": "BENJAMIN PRIMERA FASE GC"}) == [
        {"competition": "900", "competitionName": "BENJAMIN PRIMERA FASE GC", "id": "11", "name": "GRUPO 11",
         "firstSeen": "2026-10-15"}]
    assert U.new_groups({"900": {str(n): f"GRUPO {n}" for n in range(1, 11)}}, KNOWN, today=TODAY) == []


def test_first_seen_is_kept_and_the_list_is_sorted():
    seen = {"901": {"7": "GRUPO 2", "5": "GRUPO 1"}, "900": {"25": " GRUPO  25 ", "11": "GRUPO 11", "3": "GRUPO 3"}}
    known = KNOWN | {("901", "4")}
    previous = [{"competition": "900", "competitionName": "X", "id": "25", "name": "GRUPO 25", "firstSeen": "2026-10-01"}]
    got = U.new_groups(seen, known, previous, TODAY, names={"900": "BENJAMIN", "901": "ALEVIN"})
    assert [(g["competition"], g["id"], g["name"], g["firstSeen"]) for g in got] == [
        ("900", "11", "GRUPO 11", "2026-10-15"), ("900", "25", "GRUPO 25", "2026-10-01"),
        ("901", "5", "GRUPO 1", "2026-10-15"), ("901", "7", "GRUPO 2", "2026-10-15")]
    assert {g["competitionName"] for g in got if g["competition"] == "900"} == {"BENJAMIN"}
    # Sin nombres de la base, el de antes; sin ninguno, el id de la competición.
    assert U.new_groups(seen, known, previous, TODAY)[1]["competitionName"] == "X"
    assert U.new_groups(seen, known, previous, TODAY)[0]["competitionName"] == "900"


def test_a_competition_whose_dropdown_was_not_read_keeps_its_new_groups_unless_activated():
    previous = [{"competition": "900", "competitionName": "B", "id": "25", "name": "GRUPO 25", "firstSeen": "2026-10-01"},
                {"competition": "900", "competitionName": "B", "id": "26", "name": "GRUPO 26", "firstSeen": "2026-10-01"}]
    assert U.new_groups({}, KNOWN, previous, TODAY) == previous
    # Leído y ya sin el 26: fuera; el 25 sigue, con su firstSeen.
    assert U.new_groups({"900": {"1": "GRUPO 1", "25": "GRUPO 25"}}, KNOWN, previous, TODAY) == previous[:1]
    # Activado (ya en la base): fuera, aunque esta pasada no lea ese desplegable.
    assert U.new_groups({}, KNOWN | {("900", "25")}, previous, TODAY) == previous[1:]
    # Lo que no es un grupo de verdad (sin id numérico, sin nombre, de una competición que la web no sigue), fuera.
    assert U.new_groups({"900": {"": "GRUPO", "x": "GRUPO X", "12": ""}, "777": {"1": "GRUPO 1"}}, KNOWN,
                        [None, "x", {"competition": "900"}], TODAY) == []


def test_the_competition_name_comes_from_the_groups_of_the_base():
    conn = B.season()
    conn.execute("UPDATE groups SET full_name='BENJAMIN PRIMERA FASE GC - GRUPO ' || id, phase='Primera Fase GC'")
    assert U.season_groups(conn, 1) == KNOWN
    assert U.competition_names(conn, 1) == {"900": "BENJAMIN PRIMERA FASE GC"}
    conn.execute("UPDATE groups SET full_name=NULL")
    assert U.competition_names(conn, 1) == {"900": "Primera Fase GC"}


# ── El desplegable de cada calendario (update_fiflp.group_select) ────────────

class Listed(B.Federation):
    """La federación de test_bot_freno cuyo calendario de cada grupo (NFG_CmpJornada con CodGrupo) trae el
    desplegable de grupos de la competición 900: los diez de la base y `extra` [(CodGrupo, nombre)]. Con
    `listed=None`, sin desplegable de grupos (lo que se sabe hasta ahora de esa página)."""

    def __init__(self, clock, listed=tuple(range(1, 11)), extra=(), **kw):
        super().__init__(clock, **kw)
        self.listed = None if listed is None else [(str(n), f"GRUPO {n}") for n in listed] + list(extra)
        self.reads = 0

    def page(self):
        page = B.Page(self)
        plain = page.evaluate

        def evaluate(js, *a):
            if 'select[name="grupo"]' in js:
                self.reads += 1
                if self.listed is None or "NFG_CmpJornada" not in page.url or "CodGrupo=" not in page.url:
                    return []
                return [{"value": value, "text": text} for value, text in self.listed]
            return plain(js, *a)
        page.evaluate = evaluate
        return page


def test_a_calendar_with_one_group_more_gives_new_groups_without_asking_any_page_more(bot, capsys, monkeypatch):
    data, web, F, log = bot(capsys, web=Listed, extra=[("25", "GRUPO 25")])
    assert data["newGroups"] == [{"competition": "900", "competitionName": "900", "id": "25", "name": "GRUPO 25",
                                  "firstSeen": "2026-10-15"}]
    assert data["run"]["groupSelects"] == {"seen": len(B.ALL), "of": len(B.ALL)}
    assert web.reads == len(B.ALL)
    assert "Grupos nuevos en la federación: 900, GRUPO 25 (25)" in log
    # Las mismas páginas que sin leer el desplegable (group_select sin hacer nada): ninguna de más.
    monkeypatch.setattr(U, "group_select", lambda page, comp, selects: None)
    plain, plain_web, plain_F, _ = bot(capsys, web=Listed, extra=[("25", "GRUPO 25")])
    assert [u for _, u in web.starts] == [u for _, u in plain_web.starts]
    assert F.pages == plain_F.pages and data["run"]["pages"] == plain["run"]["pages"]
    assert "newGroups" not in plain and "groupSelects" not in plain["run"]


@pytest.fixture
def health(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<script src="./data-seasons.js?v=20261015a"></script>')
    monkeypatch.setattr(source_health, "ROOT", tmp_path)
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    monkeypatch.setattr(source_health, "_report", None)
    return source_health.REPORT_PATH


def test_the_same_new_groups_do_not_rewrite_the_report_and_are_carried_between_passes(health):
    t0 = datetime(2026, 10, 15, 4, tzinfo=timezone.utc)
    seen = {"900": {"25": "GRUPO 25"}}
    source_health.begin("2026-2027")
    source_health.set_new_groups(U.new_groups(seen, KNOWN, source_health.new_groups(), TODAY))
    source_health.finish(now=t0)
    first = health.read_text()
    assert json.loads(first)["newGroups"][0]["id"] == "25"
    # Al día siguiente, lo mismo (firstSeen no cambia): el informe queda igual, sin commit.
    source_health.begin("2026-2027")
    source_health.set_new_groups(U.new_groups(seen, KNOWN, source_health.new_groups(), TODAY + timedelta(days=1)))
    source_health.finish(now=t0 + timedelta(hours=6))
    assert health.read_text() == first
    # Una ejecución sin federación (FIFLP_UPDATE sin poner) los arrastra tal cual.
    source_health.begin("2026-2027")
    assert source_health.new_groups() == json.loads(first)["newGroups"]
    source_health.finish(now=t0 + timedelta(hours=7))
    assert health.read_text() == first
    # Ninguno: fuera del informe; y con otra temporada, no se arrastran.
    source_health.begin("2026-2027")
    source_health.set_new_groups([])
    source_health.finish(now=t0 + timedelta(hours=8))
    assert "newGroups" not in json.loads(health.read_text())
    health.write_text(first)
    source_health.begin("2027-2028")
    assert source_health.new_groups() == []


def test_a_calendar_without_a_groups_dropdown_leaves_new_groups_as_they_were(bot, capsys):
    old = [{"competition": "900", "competitionName": "BENJAMIN", "id": "25", "name": "GRUPO 25", "firstSeen": "2026-10-01"}]
    data, web, F, log = bot(capsys, previous={**B.report(), "newGroups": old}, web=Listed, listed=None)
    assert data["newGroups"] == old
    assert data["run"]["groupSelects"] == {"seen": 0, "of": len(B.ALL)}


def test_a_group_gone_from_the_dropdown_is_removed(bot, capsys):
    old = [{"competition": "900", "competitionName": "BENJAMIN", "id": "25", "name": "GRUPO 25", "firstSeen": "2026-10-01"}]
    data, *_ = bot(capsys, previous={**B.report(), "newGroups": old}, web=Listed)
    assert "newGroups" not in data


def test_a_broken_groups_dropdown_never_stops_a_group(bot, capsys):
    class Broken(Listed):
        def page(self):
            page = super().page()
            plain = page.evaluate

            def evaluate(js, *a):
                if 'select[name="grupo"]' in js:
                    raise RuntimeError("desplegable raro")
                return plain(js, *a)
            page.evaluate = evaluate
            return page
    data, *_ = bot(capsys, web=Broken)
    assert data["summary"] == {"ok": len(B.ALL), "rejected": 0, "error": 0}
    assert data["run"]["groupSelects"] == {"seen": 0, "of": len(B.ALL)}


def test_the_groups_dropdown_is_read_before_the_calendar_is_flattened(monkeypatch):
    """flatten() quita lo oculto, y el formulario de la federación con sus desplegables puede estarlo
    (fetch_fiflp_actas: #portlet_search, display:none): se lee antes del diagnóstico del calendario."""
    from scripts.tests import test_bot_paginas as P
    order = []

    class Page(P.Page):
        def evaluate(self, js, *a):
            if 'select[name="grupo"]' in js:
                order.append("grupo")
                return [{"value": "7", "text": "GRUPO 7"}, {"value": "8", "text": "GRUPO 8"}, {"value": "0", "text": "--"}]
            return super().evaluate(js, *a)
    monkeypatch.setattr(U, "flatten", lambda page, selector=None: order.append("flatten") or 0)
    selects = {}
    today = date(2026, 10, 14)
    options = P.calendar()
    U.scrape_group(Page(options), P.Fed(), P.GROUP, P.stored(options, today), today, check={}, selects=selects)
    assert order[0] == "grupo" and order.count("grupo") == 1
    assert selects == {"seen": 1, "of": 1, "groups": {"900": {"7": "GRUPO 7", "8": "GRUPO 8"}}}
    # Sin `selects` (las tandas, las pruebas de antes), no se lee.
    order.clear()
    U.scrape_group(Page(options), P.Fed(), P.GROUP, P.stored(options, today), today)
    assert "grupo" not in order


@pytest.mark.parametrize("days", [1, 30])
def test_new_groups_keep_their_first_seen_day_after_day(days):
    previous = U.new_groups({"900": {"25": "GRUPO 25"}}, KNOWN, today=TODAY)
    assert U.new_groups({"900": {"25": "GRUPO 25"}}, KNOWN, previous, TODAY + timedelta(days=days)) == previous
