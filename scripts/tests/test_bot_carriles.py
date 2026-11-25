"""El bot por carriles (parte E1, tarea 7): el de siempre (prebenjamín, benjamín y alevín, update.yml con
FIFLP_CATS vacía) y el de las mayores (infantil, cadete y juvenil: update.yml llamado desde carril-mayores.yml
con FIFLP_CATS=infantil,cadete,juvenil). Sin red: federaciones y páginas falsas.

Lo que se prueba:
  - el orden de una pasada del carril de mayores: la rotación de siempre (cuatro turnos, intercalados por
    categoría) con sus niveles (4, 5 y 6), nunca con los del carril principal (el principal, en el mismo orden
    que antes: test_bot_rotacion.test_plan_principal_igual_que_antes);
  - la salud de cada carril va aparte en data-health.json: una pasada del carril de mayores seca, cortada o en
    un runner que la federación no sirve (AWS) no toca runHealth ni run del bot de siempre, ni al revés, y las
    dos conservan las comprobaciones de los grupos del otro carril;
  - los extras de una vez al día: el carril de mayores solo hace las fichas de sus equipos (las competiciones
    nuevas y el directorio de campos siguen siendo del bot de siempre);
  - el veredicto y la marca de update.yml (source_health.py veredicto / marcar), los del carril del job.
"""
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from categorias import CARRILES  # noqa: E402
from db import SCHEMA  # noqa: E402
from migrate_actas_schema import migrate  # noqa: E402
import source_health  # noqa: E402
import update_fiflp as U  # noqa: E402

TODAY = date(2026, 11, 24)
NOW = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)          # un martes de madrugada (4:00 en Canarias)
MAYORES_ENV = "infantil,cadete,juvenil"
# Códigos de la tabla del convenio: 14 de infantil, 17 de cadete y 10 de juvenil.
INF = ([f"INFPG{i}" for i in range(1, 7)] + [f"INF1G{i}" for i in range(1, 6)] + ["INFUL1", "INFUL2", "INFUF1"])
CAD = ([f"CADNG{i}" for i in range(1, 7)] + [f"CADPG{i}" for i in range(1, 5)] + ["CADI1", "CADI2", "CADI3",
       "CADNL1", "CADNL2", "CADPL1", "CADNF1"])
JUV = [f"JUV2G{i}" for i in range(1, 5)] + ["JUV1G1", "JUV1G2", "JUVPG1", "JUVPG2", "JUVI1", "JUVPL1"]
PRINCIPAL = [("FF1", "BENJAMIN"), ("FF2", "BENJAMIN"), ("PG1", "PREBENJAMIN"), ("AL1", "ALEVIN"), ("AL2", "ALEVIN")]


def url(gid):
    return ("https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22"
            f"&CodCompeticion=900&CodGrupo={gid}")


def base(principal=True, mayores=(INF, CAD, JUV)):
    """2026-27 con los grupos del carril principal (con `principal`) y los de las mayores, sin partidos."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.execute("INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2026-2027', 2026, 2027, 1)")
    rows = list(PRINCIPAL if principal else [])
    for codes, cat in zip(mayores, ("INFANTIL", "CADETE", "JUVENIL")):
        rows += [(c, cat) for c in codes]
    cats = {}
    for gid, (code, cat) in enumerate(rows, 1):
        if cat not in cats:
            cats[cat] = conn.execute("INSERT INTO categories(name) VALUES (?)", (cat,)).lastrowid
        conn.execute("INSERT INTO groups(id, season_id, category_id, code, url) VALUES (?, 1, ?, ?, ?)",
                     (gid, cats[cat], code, url(gid)))
    conn.commit()
    return conn


def categories(conn):
    return dict(conn.execute("SELECT g.code, c.name FROM groups g JOIN categories c ON c.id=g.category_id"))


# ── El orden del carril de mayores ───────────────────────────────────────────

def test_plan_del_carril():
    """En 4 números seguidos, cada grupo va en el tramo del turno exactamente una vez; cada pasada intercala
    las tres categorías (en los 12 primeros de cada orden, de las tres); ningún grupo de los niveles 1-3."""
    conn = base(principal=False)
    groups = U.fiflp_groups(conn, 1, CARRILES["mayores"])
    assert len(groups) == 41
    cat = categories(conn)
    checks = {c: {"url": u, "status": "ok", "checkedAt": (NOW - timedelta(hours=3)).isoformat()} for _, c, u in groups}
    by_level = {}
    for _, code, _ in groups:
        by_level.setdefault(U._level(cat[code], code), []).append(code)
    assert sorted(by_level) == [4, 5, 6]
    for start in (0, 4, 37, 1001):
        turns = []
        for number in range(start, start + 4):
            plan = U.plan_groups(conn, groups, checks, TODAY, number, priority=[], pinned=set(), env={}, now=NOW)
            order = [c for _, c, _ in plan.order]
            assert sorted(order) == sorted(c for _, c, _ in groups) and not plan.resting
            assert all(U._level(cat[c], c) in (4, 5, 6) for c in order)
            assert {cat[c] for c in order[:12]} == {"INFANTIL", "CADETE", "JUVENIL"}, (number, order[:12])
            size = sum(len(U.turn_blocks(codes)[number % U.ROTATION_PASSES]) for codes in by_level.values())
            turns += order[:size]
        assert sorted(turns) == sorted(c for _, c, _ in groups), start      # cada uno, una vez


def test_los_niveles():
    assert U.LEVELS == {"PREBENJAMIN": 1, "ALEVIN": 3, "INFANTIL": 4, "CADETE": 5, "JUVENIL": 6}
    assert U.LEVEL_ORDER == (3, 1, 2, 4, 5, 6)
    assert U.BACKFILL_ORDER == ("PREBENJAMIN", "BENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")
    assert [U._level(c, code) for c, code in (("BENJAMIN", "FF1"), ("ALEVIN", "ALUL1"), (None, "AL3"),
                                              ("INFANTIL", "INFPG1"), ("CADETE", "CADI1"), ("JUVENIL", "JUVH1"))] \
        == [2, 3, 3, 4, 5, 6]
    assert U.EXTRAS == {"principal": ("competiciones", "campos", "directorio"), "mayores": ("directorio",)}
    assert set(U.EXTRAS) == set(CARRILES)


def test_el_principal_nunca_tiene_niveles_de_mayores_ni_al_reves():
    conn = base()
    cat = categories(conn)
    for carril, levels in (("principal", {1, 2, 3}), ("mayores", {4, 5, 6})):
        groups = U.fiflp_groups(conn, 1, CARRILES[carril])
        assert {U._level(cat[c], c) for _, c, _ in groups} == levels


# ── La salud de cada carril, aparte ──────────────────────────────────────────

class _Page:
    url = ""

    def evaluate(self, script, *a):
        return [{"value": "1", "text": "1 - 21-11-2026"}] if 'select[name="jornada"]' in script else []

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return "<html></html>"


class _Aws:
    """La federación en un runner de AWS: nada desde la primera petición (fiflp_carga.Federacion la deja
    bloqueada con refused_runner al momento)."""
    BASE = "https://www.fiflp.com/pnfg/NPcd"
    cloud = "aws"

    def __init__(self):
        self.seen, self.brakes, self.refused_runner = [], 0, False

    @property
    def blocked(self):
        return self.refused_runner

    def goto(self, page, url):
        self.seen.append(url)
        self.brakes += 1
        self.refused_runner = True
        return False

    def delay(self, *a):
        pass


class _Serves:
    """La federación que sirve todo (una jornada con el descanso, sin clasificación)."""
    BASE = "https://www.fiflp.com/pnfg/NPcd"

    def __init__(self):
        self.seen = []

    def goto(self, page, url):
        self.seen.append(url)
        page.url = url
        return True

    def delay(self, *a):
        pass

    def parse_standings(self, page):
        return []

    def parse_matches(self, page):
        return [{"home": "DESCANSA", "away": "DESCANSA", "hs": None, "as": None, "date": "", "time": "", "venue": ""}]


@pytest.fixture
def informe(tmp_path, monkeypatch):
    """data-health.json de verdad en tmp_path: pasada(carril, fed, now) hace begin → update_groups → finish y
    devuelve el informe escrito."""
    (tmp_path / "index.html").write_text('<script src="./data-seasons.js?v=20261124a"></script>')
    monkeypatch.setattr(source_health, "ROOT", tmp_path)
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    monkeypatch.setattr(source_health, "_report", None)
    monkeypatch.setattr(source_health, "_previous", None)
    monkeypatch.setattr(U, "flatten", lambda page, selector=None: 0)
    monkeypatch.setenv("FIFLP_PRIORITY_TEAMS", "")
    monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)
    conn = base(mayores=(INF[:2], CAD[:2], JUV[:1]))

    def pasada(carril, fed, now, failed=False):
        if carril == "mayores":
            monkeypatch.setenv("FIFLP_CATS", MAYORES_ENV)
        else:
            monkeypatch.delenv("FIFLP_CATS", raising=False)
        source_health.begin("2026-2027")
        monkeypatch.setattr(U, "_with_browser", lambda work, deadline=None: work(_Page(), fed))
        U.update_groups(conn, 1, today=now.date(), now=now)
        source_health.finish(now=now, failed=failed)
        return json.loads(source_health.REPORT_PATH.read_text())

    groups = {c: {"url": u, "status": "ok", "message": "1 jornadas leídas",
                  "checkedAt": (NOW - timedelta(hours=5)).isoformat(timespec="seconds")}
              for _, c, u in U.fiflp_groups(conn, 1)}
    start = {"version": 1, "season": "2026-2027", "groups": groups,
             "nextSeason": {"name": "2027-2028", "status": "pending"}, "runHealth": {"ok": True},
             "run": {"pass": 1234, "groups": 5, "refreshed": 3, "cloud": "azure"},
             "checkedAt": (NOW - timedelta(hours=5)).isoformat(timespec="seconds"), "dataVersion": "20261124a",
             "summary": {"ok": len(groups), "rejected": 0, "error": 0}}
    source_health.REPORT_PATH.write_text(json.dumps(start))
    pasada.start, pasada.conn = start, conn
    return pasada


def test_el_carril_no_toca_la_salud_del_bot(informe):
    """Una pasada del carril de mayores seca (en un runner de AWS): carriles.mayores.runHealth con su drySince,
    y runHealth, run y las comprobaciones del bot de siempre como estaban. La siguiente del principal, seca
    también, empieza su propia racha; la del carril, 7 h después de la primera, se pone en rojo sola."""
    start = informe.start
    stamp = lambda t: t.isoformat(timespec="seconds")
    first = informe("mayores", _Aws(), NOW)
    assert first["runHealth"] == {"ok": True} and first["run"] == start["run"]
    assert first["carriles"]["mayores"]["runHealth"] == {"ok": True, "drySince": stamp(NOW)}
    run = first["carriles"]["mayores"]["run"]
    assert run["refusedRunner"] is True and run["groups"] == 5 and run["refreshed"] == 0
    assert first["groups"] == start["groups"]                 # todos conservan su comprobación
    assert set(first) - set(start) == {"carriles"}

    later = NOW + timedelta(hours=2)
    second = informe("principal", _Aws(), later)
    assert second["runHealth"] == {"ok": True, "drySince": stamp(later)}           # su propia racha
    assert second["carriles"]["mayores"] == first["carriles"]["mayores"]           # la del carril, intacta
    assert second["run"]["refusedRunner"] is True and second["run"]["groups"] == 5
    assert second["groups"] == start["groups"]

    third = informe("mayores", _Aws(), NOW + timedelta(hours=7))
    health = third["carriles"]["mayores"]["runHealth"]
    assert health["ok"] is False and health["drySince"] == stamp(NOW)
    assert health["reasons"] == ["la federación no sirve ningún grupo desde hace 7 h (de 5 previstos en esta pasada)"]
    assert third["runHealth"] == second["runHealth"] and third["run"] == second["run"]
    assert third["groups"] == start["groups"]


def test_un_bot_en_rojo_no_pone_en_rojo_el_carril(informe):
    """Al revés: el bot de siempre en rojo (7 h seco) no toca la racha del carril; una pasada del carril que
    lee bien quita la suya y no el rojo del bot, y lee y comprueba solo sus grupos."""
    stamp = lambda t: t.isoformat(timespec="seconds")
    informe("mayores", _Aws(), NOW)
    informe("principal", _Aws(), NOW)
    red = informe("principal", _Aws(), NOW + timedelta(hours=7))
    assert red["runHealth"]["ok"] is False and red["runHealth"]["drySince"] == stamp(NOW)
    assert red["carriles"]["mayores"]["runHealth"] == {"ok": True, "drySince": stamp(NOW)}
    fine = informe("mayores", _Serves(), NOW + timedelta(hours=8))
    assert fine["carriles"]["mayores"]["runHealth"] == {"ok": True}               # lee algo: fuera su racha
    assert fine["runHealth"] == red["runHealth"] and fine["run"] == red["run"]     # lo del bot, igual
    changed = {c for c, g in fine["groups"].items() if g != informe.start["groups"][c]}
    assert changed == set(INF[:2] + CAD[:2] + JUV[:1])                            # solo los suyos, leídos
    assert all(fine["groups"][c]["status"] == "ok" for c in changed)
    healed = informe("principal", _Serves(), NOW + timedelta(hours=9))
    assert healed["runHealth"] == {"ok": True} and healed["carriles"] == fine["carriles"]
    assert all(healed["groups"][c] == fine["groups"][c] for c in changed)          # los del carril, conservados


def test_una_pasada_cortada_del_carril_solo_marca_la_suya(informe):
    """Una ejecución del carril que falla tras leer (finish(failed=True)): «la pasada se interrumpió…» en su
    runHealth, no en el del bot; y al revés."""
    cut = informe("mayores", _Serves(), NOW, failed=True)
    assert cut["carriles"]["mayores"]["runHealth"]["reasons"] == [source_health.INTERRUPTED]
    assert cut["runHealth"] == {"ok": True}
    assert cut["groups"] == informe.start["groups"]                 # sus «ok», fuera: los de antes
    cut2 = informe("principal", _Serves(), NOW + timedelta(hours=1), failed=True)
    assert cut2["runHealth"]["reasons"] == [source_health.INTERRUPTED]
    assert cut2["carriles"]["mayores"] == cut["carriles"]["mayores"]


def test_sin_carril_de_mayores_el_informe_no_cambia_de_forma(informe):
    """Mientras no corra nunca el carril de mayores, ninguna clave nueva: el data-health.json del bot de
    siempre, con su forma de hoy."""
    report = informe("principal", _Serves(), NOW)
    assert "carriles" not in report
    assert set(report) == set(informe.start)
    assert report["runHealth"] == {"ok": True} and report["run"]["groups"] == 5


def test_las_notas_del_carril_no_reescriben_el_informe(tmp_path, monkeypatch):
    """carriles.<c>.run es volátil, como run: solo él cambiado, el informe no se reescribe."""
    previous = {"version": 1, "season": "2026-2027", "groups": {}, "runHealth": {"ok": True},
                "carriles": {"mayores": {"runHealth": {"ok": True}, "run": {"pass": 7}}},
                "checkedAt": NOW.isoformat(timespec="seconds")}
    report = json.loads(json.dumps(previous))
    report["carriles"]["mayores"]["run"] = {"pass": 8}
    report["checkedAt"] = (NOW + timedelta(hours=2)).isoformat(timespec="seconds")
    assert source_health.meaningful(report) == source_health.meaningful(previous)
    report["carriles"]["mayores"]["runHealth"] = {"ok": False, "reasons": ["x"], "since": "y"}
    assert source_health.meaningful(report) != source_health.meaningful(previous)


# ── Los extras de una vez al día ─────────────────────────────────────────────

@pytest.mark.parametrize("carril, hechos", [("principal", ["campos", "competiciones", "directorio"]),
                                            ("mayores", ["directorio"])])
def test_extras_del_carril(monkeypatch, carril, hechos):
    """Con el carril de mayores, check_competitions y update_campos no se llaman (ni cuentan como pendientes)
    y update_directorio sí; con el principal, los tres, como siempre."""
    monkeypatch.setattr(source_health, "_report", None)
    monkeypatch.setattr(U, "flatten", lambda page, selector=None: 0)
    calls = []
    monkeypatch.setattr(U, "check_competitions", lambda *a, **k: calls.append("competiciones"))
    monkeypatch.setattr(U, "missing_venues", lambda conn, sid: ["Campo que falta"])
    monkeypatch.setattr(U, "update_campos", lambda *a, **k: calls.append("campos") or 0)
    monkeypatch.setattr(U, "update_directorio", lambda *a, **k: calls.append("directorio") or (0, 0))
    notes = []
    monkeypatch.setattr(source_health, "note_run", lambda info, carril="principal": notes.append((info, carril)))
    conn = base()
    groups = U.fiflp_groups(conn, 1, CARRILES[carril])
    number = next(n for n in range(100) if U.extras_turn(n))
    fed = _Serves()
    U.run_passes(_Page(), fed, conn, 1, groups, TODAY, {c: u for _, c, u in groups}, number=number, now=NOW,
                 checks={}, extras=U.EXTRAS[carril], carril=carril)
    assert sorted(set(calls)) == hechos and calls.count("directorio") == 1
    assert notes[-1][1] == carril and notes[-1][0]["extras"] == hechos
    assert not any("NFG_LstCampos" in u for u in fed.seen)


# ── El veredicto y la marca, por carril ──────────────────────────────────────

def test_veredicto_por_carril(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    write = lambda report: source_health.REPORT_PATH.write_text(json.dumps(report))
    red = {"ok": False, "reasons": ["la federación no sirve ningún grupo desde hace 7 h"], "since": "2026-11-24T03:00:00+00:00"}

    write({"season": "2026-2027", "runHealth": {"ok": True}, "carriles": {"mayores": {"runHealth": red}}})
    monkeypatch.setenv("FIFLP_CATS", MAYORES_ENV)
    assert source_health.main(["veredicto"]) == 1
    assert "Pasada en rojo: la federación no sirve ningún grupo desde hace 7 h" in capsys.readouterr().out
    monkeypatch.delenv("FIFLP_CATS")
    assert source_health.main(["veredicto"]) == 0

    write({"season": "2026-2027", "runHealth": red, "carriles": {"mayores": {"runHealth": {"ok": True}}}})
    assert source_health.main(["veredicto"]) == 1
    monkeypatch.setenv("FIFLP_CATS", MAYORES_ENV)
    assert source_health.main(["veredicto"]) == 0
    # Sin veredicto del carril todavía (no ha corrido nunca): 0, aunque el del bot esté en rojo.
    write({"season": "2026-2027", "runHealth": red})
    assert source_health.main(["veredicto"]) == 0

    # marcar "x" con el carril de mayores: solo el suyo (con su drySince), nada más del informe.
    before = {"season": "2026-2027", "runHealth": {"ok": True, "drySince": "a"}, "groups": {"FF1": {"status": "ok"}},
              "carriles": {"mayores": {"runHealth": {"ok": True, "drySince": "b"}, "run": {"pass": 3}}}}
    write(before)
    assert source_health.main(["marcar", "x"]) == 0
    after = json.loads(source_health.REPORT_PATH.read_text())
    mark = after["carriles"]["mayores"]["runHealth"]
    assert mark["ok"] is False and mark["reasons"] == ["x"] and mark["drySince"] == "b" and mark["since"]
    assert {k: v for k, v in after.items() if k != "carriles"} == {k: v for k, v in before.items() if k != "carriles"}
    assert after["carriles"]["mayores"]["run"] == {"pass": 3}
    # Y el del bot, con el principal: el carril no se toca.
    monkeypatch.delenv("FIFLP_CATS")
    assert source_health.main(["marcar", "y"]) == 0
    again = json.loads(source_health.REPORT_PATH.read_text())
    assert again["runHealth"]["reasons"] == ["y"] and again["carriles"] == after["carriles"]
    # Un carril que nunca corrió, marcado: aparece con su rojo.
    write({"season": "2026-2027", "runHealth": {"ok": True}})
    monkeypatch.setenv("FIFLP_CATS", MAYORES_ENV)
    assert source_health.main(["marcar", "z"]) == 0
    fresh = json.loads(source_health.REPORT_PATH.read_text())
    assert fresh["runHealth"] == {"ok": True} and fresh["carriles"]["mayores"]["runHealth"]["reasons"] == ["z"]


def test_begin_arrastra_los_carriles_de_la_misma_temporada(tmp_path, monkeypatch):
    """begin arrastra carriles como runHealth: de la misma temporada, tal cual (menos el run del carril de la
    pasada, que pone su note_run); de otra, fuera. En una pasada del carril de mayores, el run del principal
    sigue (lo lee el carril del histórico: historico.freno_del_bot)."""
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    for name in ("_report", "_previous"):
        monkeypatch.setattr(source_health, name, None)        # y al acabar, como estaban
    lanes = {"mayores": {"runHealth": {"ok": True, "drySince": "a"}, "run": {"pass": 3}}}
    previous = {"version": 1, "season": "2026-2027", "groups": {}, "runHealth": {"ok": True}, "run": {"pass": 9},
                "carriles": lanes}
    source_health.REPORT_PATH.write_text(json.dumps(previous))
    monkeypatch.delenv("FIFLP_CATS", raising=False)
    source_health.begin("2026-2027")
    assert source_health._report["carriles"] == lanes and "run" not in source_health._report
    monkeypatch.setenv("FIFLP_CATS", MAYORES_ENV)
    source_health.begin("2026-2027")
    assert source_health._report["carriles"] == {"mayores": {"runHealth": {"ok": True, "drySince": "a"}}}
    assert source_health._report["run"] == {"pass": 9} and source_health.dry_since("mayores") == "a"
    assert source_health.dry_since() is None
    source_health.begin("2027-2028")
    assert "carriles" not in source_health._report and "run" not in source_health._report
