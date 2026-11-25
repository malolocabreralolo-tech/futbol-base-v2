"""Competiciones nuevas de la federación: el bot las ve solo y las apunta.

Sin esto, la Segunda Fase de benjamín y «LIGA BENJAMIN F-7 DE FUERTEVENTURA 1ª FASE» (54977017) se
escaparían: nada miraría el desplegable de competiciones. En cada pasada, update_fiflp.check_competitions
lee ese desplegable de la temporada en curso (el mismo JS que discover_fiflp_comps.py), se queda con
benjamín, prebenjamín y alevín de Gran Canaria (sin fútbol sala ni alevín de Lanzarote y Fuerteventura),
quita las que la temporada ya tiene y las ignoradas, y lo apunta en data-health.json (newCompetitions),
que enseña «Datos y fuentes». Sin aviso fuera de la web: no hay issue por competición. Sin red: el
catálogo de 2026-27 congelado en fixtures/ (el vivo lo cambia discover-fiflp.yml y estas pruebas corren
en el bot antes de publicar).
"""
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
import source_health  # noqa: E402
import update_fiflp as U  # noqa: E402

TODAY = date(2026, 10, 14)
CATALOG = json.loads((ROOT / "scripts" / "tests" / "fixtures" / "fiflp_comps_catalog.json").read_text(encoding="utf-8"))["2026-2027"]["all"]
FIFLP = ("https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22"
         "&CodCompeticion={comp}&CodGrupo={group}")


# ── Qué categoría es una competición ─────────────────────────────────────────

@pytest.mark.parametrize("name, cat", [
    ("LIGA BENJAMIN F-7 DE FUERTEVENTURA 1ª FASE", "BENJAMIN"),
    ("LIGA BENJAMIN F7 GRAN CANARIA FASE LIGA F", "BENJAMIN"),
    ("Liga Benjamín de Lanzarote Fase 2", "BENJAMIN"),
    ("LIGA PREBENJAMIN DE GRAN CANARIA", "PREBENJAMIN"),
    ("COPA CAMPEONES PREBENJAMIN", "PREBENJAMIN"),
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA", "ALEVIN"),
    ("COPA CAMPEONES ALEVÍN", "ALEVIN"),
    ("copa de campeones categoria alevin fase a", "ALEVIN"),
    # Alevín solo de Gran Canaria; nunca fútbol sala. Infantil se conoce, pero no se activa (abajo).
    ("LIGA ALEVIN LANZAROTE FASE 1", None),
    ("LIGA ALEVIN FUERTEVENTURA F7 1ª FASE", None),
    ("LIGA PRIMERA BENJAMIN FUTBOL SALA GRAN CANARIA", None),
    ("LIGA BENJAMIN LPFS", None),
    ("LIGA INFANTIL PREFERENTE DE GRAN CANARIA", "INFANTIL"),
    ("MINI COPA DE NAVIDAD", None),
    ("", None),
])
def test_category_of_a_federation_competition(name, cat):
    assert U.category_of(name) == cat


# ── Qué es nuevo ───────────────────────────────────────────────────────────────

KNOWN = {"54976988", "54976982", "54977022"}       # FF1-24, LZ1-5 y PG1-4 de 2026-27
# Lo que el congelado del 25/11/2026 tiene de 2026-27 y KNOWN no, en el orden del catálogo: el alevín de
# Gran Canaria (la Fase Previa y la Segunda Fase), la Segunda Fase y la copa de benjamín de Gran Canaria,
# el benjamín de Fuerteventura y el prebenjamín de Lanzarote y Fuerteventura.
NUEVAS_2627 = ["54976940", "54977110", "55335268", "54977117", "54977125", "55335271", "55335272",
               "54977143", "54977148", "54977153", "55337393", "55337394", "55337395", "54977017",
               "55331982", "54977161", "54977026"]


def test_the_2026_27_catalog_has_fuerteventura_benjamin_and_gran_canaria_alevin_pending():
    fresh = U.new_competitions(CATALOG, KNOWN, today=TODAY, ignored={})
    assert [c["id"] for c in fresh] == NUEVAS_2627
    names = {c["id"]: c["name"] for c in fresh}
    assert names["54976940"] == "LIGA ALEVIN GRAN CANARIA FASE PREVIA"
    assert names["54977017"] == "LIGA BENJAMIN F-7 DE FUERTEVENTURA 1ª FASE"
    assert {c["firstSeen"] for c in fresh} == {"2026-10-14"}


def test_new_competitions_solo_las_activables(monkeypatch):
    """Conocer una categoría no es activarla: hoy activar_auto activa sola cada competición que el bot
    apunta en newCompetitions, así que solo se apuntan las de categorias.ACTIVABLES. Si no, en cuanto
    category_of reconociera infantil, cadete y juvenil, sus 24 competiciones de 2026-27 se activarían a la
    vez (decisión 1 de la parte E)."""
    import categorias
    options = [{"id": "54976908", "name": "LIGA INFANTIL PREFERENTE DE GRAN CANARIA"},
               {"id": "55331982", "name": "COPA BENJAMÍN GRAN CANARIA"}]
    assert [c["id"] for c in U.new_competitions(options, set(), today=TODAY)] == ["55331982"]
    # Con lo ignorado de siempre (IGNORED_COMPETITIONS), igual.
    assert U.new_competitions(options, set(), today=TODAY) == \
        U.new_competitions(options, set(), today=TODAY, ignored=U.IGNORED_COMPETITIONS)
    # El paso del director (D3): infantil activable.
    monkeypatch.setattr(categorias, "ACTIVABLES", categorias.ACTIVABLES + ("INFANTIL",))
    assert [c["id"] for c in U.new_competitions(options, set(), today=TODAY)] == ["54976908", "55331982"]
    # Y del catálogo entero de 2026-27, con lo de hoy, ninguna de las categorías nuevas.
    monkeypatch.setattr(categorias, "ACTIVABLES", ("BENJAMIN", "PREBENJAMIN", "ALEVIN"))
    assert [c["id"] for c in U.new_competitions(CATALOG, KNOWN, today=TODAY, ignored={})] == NUEVAS_2627


def test_el_desempate_cadete_se_ignora_y_hoy_no_cambia_nada(monkeypatch):
    """La «ELIMINATORIA DESEMPATE CADETE INSULAR» (sin convenio de código) está en IGNORED_COMPETITIONS: desde que
    cadete sea activable (paso D4) no sale en newCompetitions, así que activar_auto no la intenta cada día ni deja
    el aviso de la portada encendido. Con lo activable de hoy, ignorarla no cambia nada."""
    import categorias
    assert "55133947" in U.IGNORED_COMPETITIONS
    assert any(c["id"] == "55133947" for c in CATALOG)
    monkeypatch.setattr(categorias, "ACTIVABLES", ("BENJAMIN", "PREBENJAMIN", "ALEVIN"))
    assert U.new_competitions(CATALOG, KNOWN, today=TODAY) == U.new_competitions(CATALOG, KNOWN, today=TODAY, ignored={})
    monkeypatch.setattr(categorias, "ACTIVABLES", ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "CADETE"))
    con = [c["id"] for c in U.new_competitions(CATALOG, KNOWN, today=TODAY, ignored={})]
    sin = [c["id"] for c in U.new_competitions(CATALOG, KNOWN, today=TODAY)]
    assert "55133947" in con and sin == [c for c in con if c != "55133947"]
    assert "54976894" in sin                                # la interinsular de cadete, sí


def test_ignored_and_known_competitions_are_left_out_and_first_seen_is_kept():
    previous = [{"id": "54977017", "name": "LIGA BENJAMIN F-7 DE FUERTEVENTURA 1ª FASE", "firstSeen": "2026-10-07"}]
    known = KNOWN | (set(NUEVAS_2627) - {"54977017", "54976940"})
    fresh = U.new_competitions(CATALOG, known, previous, TODAY, ignored={"54976940": "alevín, en su rama"})
    assert fresh == previous
    assert U.new_competitions(CATALOG, KNOWN | set(NUEVAS_2627), previous, TODAY, ignored={}) == []
    # Lo que no es una opción de verdad (sin id o sin nombre) no cuenta.
    assert U.new_competitions([{"id": "", "name": "LIGA BENJAMIN X"}, {"value": "1", "text": "1 - 03-10-2026"}],
                              set(), today=TODAY, ignored={}) == []


def season():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.executescript("""
      INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2025-2026', 2025, 2026, 0),
                                                                            (2, '2026-2027', 2026, 2027, 1);
      INSERT INTO categories(id, name) VALUES (1, 'BENJAMIN'), (2, 'PREBENJAMIN');""")
    for gid, (sid, cat, code, comp) in enumerate([(2, 1, "FF1", "54976988"), (2, 1, "LZ1", "54976982"),
                                                  (2, 2, "PG2", "54977022"), (1, 1, "FV11", "54977017")], 1):
        conn.execute("INSERT INTO groups(id, season_id, category_id, code, url) VALUES (?, ?, ?, ?, ?)",
                     (gid, sid, cat, code, FIFLP.format(comp=comp, group=gid)))
    return conn


def test_the_season_competitions_come_from_its_group_urls():
    conn = season()
    assert U.season_competitions(conn, 2) == KNOWN          # la de 2025-26 no cuenta
    assert U.season_code(conn, 2) == "22"


class Page:
    def __init__(self, options):
        self.options, self.url = options, ""

    def evaluate(self, js, *a):
        assert 'select[name="competicion"]' in js
        return self.options


class Fed:
    BASE = "https://www.fiflp.com/pnfg/NPcd"

    def __init__(self, ok=True):
        self.ok, self.urls = ok, []

    def goto(self, page, url):
        self.urls.append(url)
        return self.ok

    def delay(self, *a):
        pass


@pytest.fixture
def health(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<script src="./data-seasons.js?v=20261014a"></script>')
    monkeypatch.setattr(source_health, "ROOT", tmp_path)
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    monkeypatch.setattr(source_health, "_report", None)
    return source_health.REPORT_PATH


def test_the_bot_reads_the_dropdown_once_and_writes_new_competitions(health):
    conn = season()
    source_health.begin("2026-2027")
    fed = Fed()
    fresh = U.check_competitions(Page(CATALOG), fed, conn, 2, TODAY, log=lambda *_: None)
    assert fed.urls == ["https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22"]
    assert [c["id"] for c in fresh] == NUEVAS_2627
    source_health.finish(now=datetime(2026, 10, 14, 4, tzinfo=timezone.utc))
    assert json.loads(health.read_text())["newCompetitions"] == fresh


def test_same_competitions_do_not_rewrite_the_report_and_a_failed_read_keeps_them(health):
    conn = season()
    t0 = datetime(2026, 10, 14, 4, tzinfo=timezone.utc)
    source_health.begin("2026-2027")
    U.check_competitions(Page(CATALOG), Fed(), conn, 2, TODAY, log=lambda *_: None)
    source_health.finish(now=t0)
    first = health.read_text()
    # Seis horas después, lo mismo (firstSeen no cambia): el informe queda igual, sin commit.
    source_health.begin("2026-2027")
    U.check_competitions(Page(CATALOG), Fed(), conn, 2, TODAY + timedelta(days=1), log=lambda *_: None)
    source_health.finish(now=t0 + timedelta(hours=6))
    assert health.read_text() == first
    # La federación no sirve la página o el desplegable sale vacío: se queda lo que había.
    for page, fed in ((Page(CATALOG), Fed(ok=False)), (Page([]), Fed())):
        source_health.begin("2026-2027")
        assert U.check_competitions(page, fed, conn, 2, TODAY, log=lambda *_: None) is None
        source_health.finish(now=t0 + timedelta(hours=7))
        assert health.read_text() == first
    # Ya activada en la web: deja de salir.
    conn.execute("UPDATE groups SET season_id=2 WHERE id=4")
    source_health.begin("2026-2027")
    fresh = U.check_competitions(Page(CATALOG), Fed(), conn, 2, TODAY, log=lambda *_: None)
    source_health.finish(now=t0 + timedelta(hours=8))
    assert [c["id"] for c in fresh] == [c for c in NUEVAS_2627 if c != "54977017"]
    assert [c["id"] for c in json.loads(health.read_text())["newCompetitions"]] == [c for c in NUEVAS_2627 if c != "54977017"]


def test_a_new_season_starts_without_the_old_ones(health):
    health.write_text(json.dumps({"season": "2025-2026", "groups": {},
                                  "newCompetitions": [{"id": "1", "name": "LIGA BENJAMIN X", "firstSeen": "2026-05-01"}]}))
    source_health.begin("2026-2027")
    assert source_health.new_competitions() == []
    health.write_text(json.dumps({"season": "2026-2027", "groups": {},
                                  "newCompetitions": [{"id": "1", "name": "LIGA BENJAMIN X", "firstSeen": "2026-10-01"}]}))
    source_health.begin("2026-2027")                 # sin pasar por la federación (FIFLP_UPDATE): se conservan
    assert [c["id"] for c in source_health.new_competitions()] == ["1"]

