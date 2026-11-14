"""data-health.json no debe generar un commit por ejecución solo porque cambie
la hora de comprobación: se reescribe si cambia algo con significado (estado o
mensaje de un grupo, versión de los datos publicados, temporada) o si la última
comprobación publicada tiene más de un día (latido)."""
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_health  # noqa: E402

T0 = datetime(2026, 9, 23, 3, 35, tzinfo=timezone.utc)


@pytest.fixture
def portal(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(
        '<script src="./data-seasons.js?v=20260909h"></script>'
        '<footer>Última actualización: 26/07/2026</footer>')
    monkeypatch.setattr(source_health, "ROOT", tmp_path)
    monkeypatch.setattr(source_health, "REPORT_PATH", tmp_path / "data-health.json")
    return tmp_path


def run(groups, now):
    source_health.begin("2025-2026")
    for code, status, message in groups:
        source_health.record(code, f"https://example.test/{code}", status, message, now=now)
    source_health.finish(now=now)
    return source_health.REPORT_PATH.read_text()


OK = [("A1", "ok", "11 equipos; 0 encuentros disponibles"), ("PG2", "ok", "15 equipos")]


def test_first_report_is_written(portal):
    text = run(OK, T0)
    report = json.loads(text)
    assert report["checkedAt"] == T0.isoformat(timespec="seconds")
    assert report["dataVersion"] == "20260909h"


def test_same_content_within_a_day_keeps_the_file_byte_identical(portal):
    first = run(OK, T0)
    assert run(OK, T0 + timedelta(hours=5)) == first
    assert run(OK, T0 + timedelta(hours=23, minutes=59)) == first


def test_heartbeat_rewrites_after_a_day(portal):
    run(OK, T0)
    later = T0 + timedelta(hours=24)
    report = json.loads(run(OK, later))
    assert report["checkedAt"] == later.isoformat(timespec="seconds")


def test_status_change_is_published_immediately(portal):
    run(OK, T0)
    report = json.loads(run([("A1", "error", "HTTP 500"), OK[1]], T0 + timedelta(hours=5)))
    assert report["groups"]["A1"]["status"] == "error"
    assert report["summary"]["error"] == 1


def test_message_change_is_published_immediately(portal):
    run(OK, T0)
    report = json.loads(run([("A1", "ok", "11 equipos; 3 encuentros disponibles"), OK[1]],
                            T0 + timedelta(hours=5)))
    assert report["groups"]["A1"]["message"].startswith("11 equipos; 3")


def test_new_published_data_version_is_published(portal):
    run(OK, T0)
    index = portal / "index.html"
    index.write_text(index.read_text().replace("20260909h", "20260923a"))
    report = json.loads(run(OK, T0 + timedelta(hours=5)))
    assert report["dataVersion"] == "20260923a"
    assert report["checkedAt"] == (T0 + timedelta(hours=5)).isoformat(timespec="seconds")


def test_unreadable_previous_report_is_replaced(portal):
    source_health.REPORT_PATH.write_text("{roto")
    report = json.loads(run(OK, T0))
    assert report["groups"]["A1"]["status"] == "ok"


def test_previous_checks_are_only_those_of_the_same_season(portal):
    run(OK, T0)
    source_health.begin("2025-2026")
    assert source_health.previous_groups()["A1"]["checkedAt"] == T0.isoformat(timespec="seconds")
    source_health.begin("2026-2027")
    assert source_health.previous_groups() == {}


def test_a_group_left_for_the_next_pass_keeps_its_last_check(portal):
    """Rotación del bot de la federación, grupos cerrados que descansan y categorías que este workflow
    no lee (update_fiflp.run_passes, FIFLP_CATS): sin comprobarse en esta pasada, su entrada sigue
    como estaba, sin marcarla como error."""
    first = json.loads(run(OK, T0))
    source_health.begin("2025-2026")
    source_health.record("PG2", "https://example.test/PG2", "ok", "16 equipos", now=T0 + timedelta(hours=5))
    source_health.carry("A1")
    source_health.carry("NUEVO")                     # sin comprobación anterior: no aparece
    source_health.finish(now=T0 + timedelta(hours=5))
    report = json.loads(source_health.REPORT_PATH.read_text())
    assert report["groups"]["A1"] == first["groups"]["A1"]
    assert report["groups"]["PG2"]["message"] == "16 equipos"
    assert "NUEVO" not in report["groups"] and report["summary"]["error"] == 0


def test_run_notes_alone_do_not_rewrite_the_report(portal):
    first = run(OK, T0)
    source_health.begin("2025-2026")
    for code, status, message in OK:
        source_health.record(code, f"https://example.test/{code}", status, message, now=T0 + timedelta(hours=5))
    source_health.note_run({"deferred": ["A1"], "seconds": 1200})
    source_health.finish(now=T0 + timedelta(hours=5))
    assert source_health.REPORT_PATH.read_text() == first


def test_meaningful_view_ignores_only_timestamps():
    a = {"season": "x", "checkedAt": "1", "groups": {"A1": {"status": "ok", "checkedAt": "1"}}}
    b = {"season": "x", "checkedAt": "2", "groups": {"A1": {"status": "ok", "checkedAt": "2"}}}
    c = {"season": "x", "checkedAt": "2", "groups": {"A1": {"status": "error", "checkedAt": "2"}}}
    assert source_health.meaningful(a) == source_health.meaningful(b)
    assert source_health.meaningful(a) != source_health.meaningful(c)


def test_a_failed_run_publishes_its_errors_but_not_its_good_checks(portal):
    """update.yml, si el paso del bot falla («Publicar diagnóstico si la fuente o las pruebas fallan»), sube
    solo data-health.json, sin la base ni los datos: las comprobaciones correctas de esa ejecución no se publican
    (vuelven a la anterior; sin ella, nada), y los errores sí (el diagnóstico). La hora de un prioritario
    (publish_time) tampoco: con ella la pasada siguiente lo daba por leído (update_fiflp.plan_groups) y no
    lo releía hasta ~6 h, con sus datos perdidos."""
    first = json.loads(run(OK + [("B1", "ok", "8 equipos")], T0))
    later = T0 + timedelta(hours=2)
    for failed in (True, False):
        source_health.REPORT_PATH.write_text(json.dumps(first))
        source_health.begin("2025-2026")
        source_health.record("A1", "https://example.test/A1", "ok", "11 equipos; 3 encuentros", now=later,
                             publish_time=True)
        source_health.record("PG2", "https://example.test/PG2", "error", "HTTP 500", now=later)
        source_health.record("NUEVO", "https://example.test/NUEVO", "ok", "6 equipos", now=later)
        source_health.record("B1", "https://example.test/otro", "ok", "8 equipos", now=later)
        source_health.finish(now=later, failed=failed)
        report = json.loads(source_health.REPORT_PATH.read_text())
        assert report["groups"]["PG2"]["status"] == "error"
        if failed:
            assert report["groups"]["A1"] == first["groups"]["A1"]
            assert "NUEVO" not in report["groups"] and "B1" not in report["groups"]
            assert report["summary"] == {"ok": 1, "rejected": 0, "error": 1}
        else:
            assert report["groups"]["A1"]["checkedAt"] == later.isoformat(timespec="seconds")
            assert report["groups"]["NUEVO"]["status"] == "ok"


def test_the_bot_run_tells_finish_whether_it_failed(portal, monkeypatch):
    """fetch_futbolaspalmas.main pasa failed=True a source_health.finish si algo falla tras comprobar (p. ej.
    generate_js), y False si acaba bien."""
    import fetch_futbolaspalmas as FB
    import generate_js
    import migrate_categories
    import migrate_compactar
    import migrate_team_names
    import update_fiflp

    class Conn:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass
    for name, module in (("migrate", migrate_categories), ("migrate", migrate_compactar),
                         ("migrate", migrate_team_names)):
        monkeypatch.setattr(module, name, lambda conn: None)
    monkeypatch.setattr(FB, "get_connection", Conn)
    monkeypatch.setattr(FB, "init_db", lambda conn: None)
    monkeypatch.setattr(FB, "active_season", lambda conn: (1, "2025-2026"))
    monkeypatch.setattr(FB, "FILES", [])
    monkeypatch.setattr(FB, "update_fp_app", lambda conn, name: None)
    monkeypatch.setattr(FB, "import_past_seasons", lambda conn: None)
    monkeypatch.setenv("FIFLP_UPDATE", "1")
    monkeypatch.setattr(update_fiflp, "update_groups", lambda conn, season_id: source_health.record(
        "A1", "https://example.test/A1", "ok", "leído", publish_time=True))
    seen = []
    monkeypatch.setattr(source_health, "finish", lambda now=None, failed=False: seen.append(failed))

    def boom():
        raise RuntimeError("generate_js roto")
    monkeypatch.setattr(generate_js, "main", boom)
    with pytest.raises(RuntimeError):
        FB.main()
    monkeypatch.setattr(generate_js, "main", lambda: None)
    FB.main()
    assert seen == [True, False]


# ── runHealth: el veredicto de la pasada del bot de la federación (pasada_sana) ──

def bot_run(now, reasons=None, failed=False, season="2025-2026"):
    """Una ejecución con federación (set_run_health con `reasons`) o sin ella (reasons None)."""
    source_health.begin(season)
    for code, status, message in OK:
        source_health.record(code, f"https://example.test/{code}", status, message, now=now)
    if reasons is not None:
        source_health.set_run_health(reasons, now=now)
    source_health.finish(now=now, failed=failed)
    return source_health.REPORT_PATH.read_text()


def test_a_healthy_pass_is_ok_and_a_second_one_does_not_rewrite_the_report(portal):
    first = bot_run(T0, [])
    assert json.loads(first)["runHealth"] == {"ok": True}
    assert bot_run(T0 + timedelta(hours=5), []) == first


def test_a_red_pass_keeps_its_since_until_a_healthy_one(portal):
    """Review Focus 4: dos pasadas en rojo seguidas, `since` no cambia; la tercera, sana, vuelve a ok."""
    report = json.loads(bot_run(T0, ["m"]))
    assert report["runHealth"] == {"ok": False, "reasons": ["m"], "since": T0.isoformat(timespec="seconds")}
    later = T0 + timedelta(hours=2)
    report = json.loads(bot_run(later, ["m", "n"]))
    assert report["runHealth"] == {"ok": False, "reasons": ["m", "n"], "since": T0.isoformat(timespec="seconds")}
    assert report["checkedAt"] == later.isoformat(timespec="seconds")       # un cambio con significado
    report = json.loads(bot_run(T0 + timedelta(hours=4), []))
    assert report["runHealth"] == {"ok": True}


def test_a_run_without_the_federation_carries_the_previous_run_health(portal):
    """Review Focus 3: sin federación (FIFLP_UPDATE sin poner) nadie llama a set_run_health."""
    red = json.loads(bot_run(T0, ["m"]))["runHealth"]
    assert json.loads(bot_run(T0 + timedelta(days=2)))["runHealth"] == red
    bot_run(T0 + timedelta(days=3), [])
    assert json.loads(bot_run(T0 + timedelta(days=5)))["runHealth"] == {"ok": True}


def test_another_season_does_not_carry_the_run_health(portal):
    bot_run(T0, ["m"])
    assert "runHealth" not in json.loads(bot_run(T0 + timedelta(hours=1), season="2026-2027"))
    report = json.loads(bot_run(T0 + timedelta(hours=2), ["m"], season="2027-2028"))
    assert report["runHealth"]["since"] == (T0 + timedelta(hours=2)).isoformat(timespec="seconds")


def test_a_failed_run_is_red_unless_it_already_was(portal):
    report = json.loads(bot_run(T0, [], failed=True))
    assert report["runHealth"] == {"ok": False, "reasons": ["la pasada se interrumpió antes de terminar"],
                                   "since": T0.isoformat(timespec="seconds")}
    report = json.loads(bot_run(T0 + timedelta(hours=1), ["m"], failed=True))
    assert report["runHealth"] == {"ok": False, "reasons": ["m"], "since": T0.isoformat(timespec="seconds")}


def test_run_health_is_not_volatile():
    assert "runHealth" not in source_health.VOLATILE
    assert source_health.meaningful({"runHealth": {"ok": True}}) != source_health.meaningful({"runHealth": {
        "ok": False, "reasons": ["m"], "since": "x"}})


def test_the_verdict_order_exits_with_1_only_when_red(portal, capsys):
    path = source_health.REPORT_PATH
    assert source_health.main(["veredicto"]) == 0                   # sin informe
    path.write_text(json.dumps({"season": "2025-2026", "groups": {}}))
    assert source_health.main(["veredicto"]) == 0                   # sin runHealth
    path.write_text(json.dumps({"runHealth": {"ok": True}}))
    assert source_health.main(["veredicto"]) == 0
    path.write_text(json.dumps({"runHealth": {"ok": False, "reasons": ["m", "n"], "since": "x"}}))
    capsys.readouterr()
    assert source_health.main(["veredicto"]) == 1
    out = capsys.readouterr().out
    assert "m" in out and "n" in out


def test_the_mark_order_turns_the_report_red_without_touching_anything_else(portal):
    bot_run(T0, [])
    before = json.loads(source_health.REPORT_PATH.read_text())
    assert source_health.main(["marcar", "fallaron las pruebas"]) == 0
    after = json.loads(source_health.REPORT_PATH.read_text())
    health = after.pop("runHealth")
    assert health["ok"] is False and health["reasons"] == ["fallaron las pruebas"] and health["since"]
    before.pop("runHealth")
    assert after == before                       # ni groups ni checkedAt
    assert source_health.main(["veredicto"]) == 1


def test_the_mark_order_on_a_red_report_adds_its_reason_and_keeps_since(portal):
    bot_run(T0, ["m"])
    assert source_health.main(["marcar", "x"]) == 0
    assert source_health.main(["marcar", "x"]) == 0
    health = json.loads(source_health.REPORT_PATH.read_text())["runHealth"]
    assert health == {"ok": False, "reasons": ["m", "x"], "since": T0.isoformat(timespec="seconds")}


def test_the_orders_run_from_the_command_line():
    import subprocess
    script = Path(source_health.__file__)
    done = subprocess.run([sys.executable, str(script), "no-existe"], capture_output=True, text=True)
    assert done.returncode == 2 and "veredicto" in done.stderr


# ── drySince: la racha de pasadas secas (Ronda de arreglo 1 de la fase 2B) ──

def dry_run(now, reasons=(), dry=True, failed=False):
    source_health.begin("2025-2026")
    for code, status, message in OK:
        source_health.record(code, f"https://example.test/{code}", status, message, now=now)
    source_health.set_run_health(list(reasons), now=now, dry=dry)
    source_health.finish(now=now, failed=failed)
    return source_health.REPORT_PATH.read_text()


def test_the_first_dry_pass_writes_dry_since_and_the_next_ones_do_not_rewrite(portal):
    bot_run(T0, [])
    later = T0 + timedelta(hours=1)
    first = dry_run(later)
    assert json.loads(first)["runHealth"] == {"ok": True, "drySince": later.isoformat(timespec="seconds")}
    source_health.begin("2025-2026")
    assert source_health.dry_since() == later.isoformat(timespec="seconds")
    assert dry_run(T0 + timedelta(hours=3)) == first                   # misma racha: no se reescribe
    assert json.loads(dry_run(T0 + timedelta(hours=4), dry=False))["runHealth"] == {"ok": True}


def test_a_red_dry_pass_has_since_and_dry_since(portal):
    dry_run(T0)
    later = T0 + timedelta(hours=7)
    health = json.loads(dry_run(later, ["la federación no sirve ningún grupo desde hace 7 h"]))["runHealth"]
    assert health == {"ok": False, "reasons": ["la federación no sirve ningún grupo desde hace 7 h"],
                      "since": later.isoformat(timespec="seconds"), "drySince": T0.isoformat(timespec="seconds")}


def test_dry_since_is_carried_without_the_federation_and_by_the_orders(portal):
    dry_run(T0)
    stamp = T0.isoformat(timespec="seconds")
    assert json.loads(bot_run(T0 + timedelta(days=2)))["runHealth"] == {"ok": True, "drySince": stamp}
    assert source_health.main(["marcar", "x"]) == 0
    health = json.loads(source_health.REPORT_PATH.read_text())["runHealth"]
    assert health["ok"] is False and health["reasons"] == ["x"] and health["drySince"] == stamp


def test_a_failed_run_keeps_the_dry_streak(portal):
    """Una ejecución que falla tras una pasada seca: en rojo por la interrupción, con la racha como estaba."""
    health = json.loads(dry_run(T0, failed=True))["runHealth"]
    assert health["reasons"] == [source_health.INTERRUPTED] and health["drySince"] == T0.isoformat(timespec="seconds")


def test_dry_since_is_none_without_a_streak_or_with_another_season(portal):
    source_health.begin("2025-2026")
    assert source_health.dry_since() is None
    dry_run(T0)
    source_health.begin("2026-2027")
    assert source_health.dry_since() is None
