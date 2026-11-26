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
    import migrate_identidad
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
    for name in ("asegurar_esquema", "resolver_fichas"):
        monkeypatch.setattr(migrate_identidad, name, lambda conn: None)
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
    """Dos pasadas en rojo seguidas, `since` no cambia; la tercera, sana, vuelve a ok."""
    report = json.loads(bot_run(T0, ["m"]))
    assert report["runHealth"] == {"ok": False, "reasons": ["m"], "since": T0.isoformat(timespec="seconds")}
    later = T0 + timedelta(hours=2)
    report = json.loads(bot_run(later, ["m", "n"]))
    assert report["runHealth"] == {"ok": False, "reasons": ["m", "n"], "since": T0.isoformat(timespec="seconds")}
    assert report["checkedAt"] == later.isoformat(timespec="seconds")       # un cambio con significado
    report = json.loads(bot_run(T0 + timedelta(hours=4), []))
    assert report["runHealth"] == {"ok": True}


def test_a_run_without_the_federation_carries_the_previous_run_health(portal):
    """Sin federación (FIFLP_UPDATE sin poner) nadie llama a set_run_health."""
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


def test_finish_conserva_base(portal):
    """La clave `base` (el tamaño de la base desde AVISO_MB: base_sana.py --salud, source_health.set_base) la ponen
    y la quitan solo set_base: finish la arrastra tal cual, también con otra temporada, y no reescribe por ella."""
    run(OK, T0)
    source_health.set_base(85 * source_health.MB, True)
    with_base = source_health.REPORT_PATH.read_text()
    assert json.loads(with_base)["base"] == {"mb": 85, "limite": 100}
    assert run(OK, T0 + timedelta(hours=5)) == with_base, "una pasada sin cambios no reescribe por la base"
    report = json.loads(run([("A1", "error", "HTTP 500"), OK[1]], T0 + timedelta(hours=6)))
    assert report["groups"]["A1"]["status"] == "error"
    assert report["base"] == {"mb": 85, "limite": 100}
    source_health.begin("2026-2027")
    source_health.finish(now=T0 + timedelta(hours=7))
    assert json.loads(source_health.REPORT_PATH.read_text())["base"] == {"mb": 85, "limite": 100}
    source_health.set_base(40 * source_health.MB, False)
    assert "base" not in json.loads(run(OK, T0 + timedelta(hours=8)))


def test_set_base_con_pieza(portal):
    """Con la base en piezas (tarea 7), el aviso es de la pieza mayor: `pieza` dice cuál («comun» o una temporada).
    Sin ella, como siempre."""
    run(OK, T0)
    source_health.set_base(83 * source_health.MB, True, pieza="2025-2026")
    assert json.loads(source_health.REPORT_PATH.read_text())["base"] == {"mb": 83, "limite": 100, "pieza": "2025-2026"}
    source_health.set_base(83 * source_health.MB, True, pieza="comun")
    assert json.loads(source_health.REPORT_PATH.read_text())["base"] == {"mb": 83, "limite": 100, "pieza": "comun"}
    source_health.set_base(83 * source_health.MB, True)
    assert json.loads(source_health.REPORT_PATH.read_text())["base"] == {"mb": 83, "limite": 100}
    source_health.set_base(40 * source_health.MB, False, pieza="comun")
    assert "base" not in json.loads(source_health.REPORT_PATH.read_text())


DESCARGA_HOY = {"url": "https://github.com/malolocabreralolo-tech/futbol-base-v2/releases/download/base-completa/futbolbase.zip",
                "fecha": "2026-09-23", "bytes": 13_000_000}


def test_set_descarga(portal):
    """set_descarga pone `descarga` en el informe del disco sin tocar nada más, y no lo reescribe si no cambia."""
    text = run(OK, T0)
    source_health.set_descarga(DESCARGA_HOY)
    after = json.loads(source_health.REPORT_PATH.read_text())
    assert after.pop("descarga") == DESCARGA_HOY
    assert after == json.loads(text)
    mtime = source_health.REPORT_PATH.stat().st_mtime_ns
    source_health.set_descarga(dict(DESCARGA_HOY))
    assert source_health.REPORT_PATH.stat().st_mtime_ns == mtime
    otro = portal / "otro.json"
    source_health.set_descarga(DESCARGA_HOY, otro)
    assert json.loads(otro.read_text()) == {"descarga": DESCARGA_HOY}


def test_begin_conserva_la_descarga(portal):
    """La descarga del día (scripts/descarga.py apuntar, una vez al día) la pone solo set_descarga: cada pasada la
    arrastra tal cual (también con otra temporada), sin reescribir el informe por ella; marcar, también."""
    run(OK, T0)
    source_health.set_descarga(DESCARGA_HOY)
    with_it = source_health.REPORT_PATH.read_text()
    assert run(OK, T0 + timedelta(hours=5)) == with_it, "una pasada sin cambios no reescribe por la descarga"
    report = json.loads(run([("A1", "error", "HTTP 500"), OK[1]], T0 + timedelta(hours=6)))
    assert report["descarga"] == DESCARGA_HOY
    source_health.begin("2026-2027")
    source_health.finish(now=T0 + timedelta(hours=7))
    assert json.loads(source_health.REPORT_PATH.read_text())["descarga"] == DESCARGA_HOY
    assert source_health.main(["marcar", "las pruebas fallaron"]) == 0
    assert json.loads(source_health.REPORT_PATH.read_text())["descarga"] == DESCARGA_HOY


def test_the_mark_order_keeps_base(portal):
    run(OK, T0)
    source_health.set_base(85 * source_health.MB, True)
    assert source_health.main(["marcar", "la base de datos no pasó la comprobación"]) == 0
    assert json.loads(source_health.REPORT_PATH.read_text())["base"] == {"mb": 85, "limite": 100}


PEND_NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
PEND_REPORT = {"season": "2026-2027", "groups": {},
               "newCompetitions": [{"id": "55400001", "name": "LIGA BENJAMIN SEGUNDA FASE A", "firstSeen": "2026-11-14"}],
               "newGroups": [{"competition": "54976988", "competitionName": "X", "id": "25", "name": "GRUPO 25"},
                             {"competition": "54976988", "id": "26", "name": "GRUPO 26"}, {"competition": "", "id": "1"}]}


def pending(capsys, report, now=PEND_NOW):
    source_health.REPORT_PATH.write_text(json.dumps(report))
    capsys.readouterr()
    code = source_health.main(["pendiente"], now=now)
    return code, capsys.readouterr().out


def test_the_pending_order_prints_what_activar_yml_would_activate(portal, capsys):
    """update.yml lanza activar.yml solo si hay competiciones o grupos nuevos (sale con 0 e imprime
    sus competiciones, sin repetir); con 1 si no hay nada que lanzar."""
    code, out = pending(capsys, PEND_REPORT)
    assert code == 0 and out == "54976988,55400001\n"
    assert pending(capsys, {"season": "2026-2027", "groups": {}}) == (1, "")
    assert pending(capsys, {"newCompetitions": "x", "newGroups": [None, {"competition": "abc"}]}) == (1, "")
    source_health.REPORT_PATH.unlink()
    assert source_health.main(["pendiente"], now=PEND_NOW) == 1      # sin informe


BEN, SEG = "54976988", "55400001"
DESCARGA = "la descarga no está completa: faltan 3 grupos"
CONVENIO = "sin convenio de código: LIGA X"


def tried(failed, hours, attempts=1, ids=(BEN, SEG)):
    """PEND_REPORT con la activation de un intento de hace `hours` h sobre `ids`, con `failed` [(id, motivo)]."""
    return {**PEND_REPORT, "activation": {
        "at": (PEND_NOW - timedelta(hours=hours)).isoformat(), "activated": [], "tried": list(ids),
        "attempts": attempts, "failed": [{"competition": c, "name": c, "reason": r} for c, r in failed]}}


def test_the_pending_order_launches_what_was_never_tried_at_once(portal, capsys):
    """Lo pendiente que activar.yml no ha intentado (no está en activation.tried) se lanza
    ya, aunque lo demás se intentara hace un minuto."""
    assert pending(capsys, tried([(SEG, CONVENIO)], 0.01, ids=[SEG])) == (0, "54976988,55400001\n")
    assert pending(capsys, {**PEND_REPORT, "activation": "x"}) == (0, "54976988,55400001\n")


def test_the_pending_order_alternates_download_attempts_with_the_passes_up_to_8(portal, capsys):
    """Una descarga incompleta (todos los fallos de lo pendiente, de descarga) se reanuda en la pasada siguiente,
    sin esperar, hasta 8 intentos (activation.attempts); con 8, como un fallo que no se arregla solo: 24 h."""
    both = [(BEN, DESCARGA), (SEG, DESCARGA)]
    assert pending(capsys, tried(both, 0.01, attempts=7)) == (0, "54976988,55400001\n")
    assert pending(capsys, tried(both, 0.01, attempts=8)) == (1, "")
    assert pending(capsys, tried(both, 23.9, attempts=8)) == (1, "")
    assert pending(capsys, tried(both, 24, attempts=8)) == (0, "54976988,55400001\n")
    no_count = tried(both, 0.01)
    del no_count["activation"]["attempts"]                            # de antes de contar: el primero
    assert pending(capsys, no_count) == (0, "54976988,55400001\n")


def test_the_pending_order_waits_24_hours_for_what_does_not_fix_itself(portal, capsys):
    """Sin convenio, verificación, código repetido, pruebas, regenerar…: no se arregla relanzando; una vez al
    día. También si se mezcla con un fallo de descarga, o si lo intentado no dejó motivo."""
    for failed in ([(SEG, CONVENIO)], [(BEN, DESCARGA), (SEG, CONVENIO)], []):
        assert pending(capsys, tried(failed, 23.9)) == (1, ""), failed
        assert pending(capsys, tried(failed, 24)) == (0, "54976988,55400001\n"), failed
    assert pending(capsys, {**tried([(SEG, CONVENIO)], 1), "activation": {
        **tried([(SEG, CONVENIO)], 1)["activation"], "at": "ayer"}}) == (0, "54976988,55400001\n")   # sin hora: no frena
    # Los fallos de lo que ya no está pendiente no cuentan: solo queda BEN, por descarga.
    only_ben = {**tried([(BEN, DESCARGA), ("99", CONVENIO)], 0.01, ids=[BEN, "99"]), "newCompetitions": []}
    assert pending(capsys, only_ben) == (0, "54976988\n")


def test_the_download_reason_is_the_one_activar_auto_writes():
    import activar_auto
    assert activar_auto.DESCARGA == source_health.INCOMPLETE
    assert activar_auto.INCOMPLETA.startswith(source_health.INCOMPLETE)


def test_the_orders_run_from_the_command_line():
    import subprocess
    script = Path(source_health.__file__)
    done = subprocess.run([sys.executable, str(script), "no-existe"], capture_output=True, text=True)
    assert done.returncode == 2 and "veredicto" in done.stderr


# ── drySince: la racha de pasadas secas ──

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


# ── El runner rechazado: update.yml relanza la pasada (decisión del dueño del 26/11/2026) ──

def test_a_refused_runner_pass_always_writes_its_note(portal):
    """update.yml («Relanzar si el runner fue rechazado») sabe que ESTA pasada cayó en un runner que la federación no
    sirve por su nota en el data-health.json del espacio de trabajo (source_health.py rechazado, con su número). Una
    pasada seca más de la misma racha no reescribía el informe (la nota, `run`, es volátil): quedaba la nota de la
    anterior y la segunda rechazada seguida no se relanzaba (la mañana del 26/11/2026, la siguiente a la 201). Con
    refusedRunner en la nota de su carril, el informe se escribe siempre; sin él, como siempre."""
    bot_run(T0, [])
    first = dry_run(T0 + timedelta(hours=1))
    # Otra seca de la racha, sin rechazo (un freno desde la primera página en Azure): no se reescribe.
    source_health.begin("2025-2026")
    for code, status, message in OK:
        source_health.record(code, f"https://example.test/{code}", status, message, now=T0 + timedelta(hours=2))
    source_health.set_run_health([], now=T0 + timedelta(hours=2), dry=True)
    source_health.note_run({"pass": 202, "refreshed": 0, "cloud": "azure", "pauses": 1, "brakeAfter": [0]})
    source_health.finish(now=T0 + timedelta(hours=2))
    assert source_health.REPORT_PATH.read_text() == first
    # La misma, en un runner rechazado: se escribe, con su nota.
    source_health.begin("2025-2026")
    for code, status, message in OK:
        source_health.record(code, f"https://example.test/{code}", status, message, now=T0 + timedelta(hours=3))
    source_health.set_run_health([], now=T0 + timedelta(hours=3), dry=True)
    source_health.note_run({"pass": 203, "refreshed": 0, "cloud": "aws", "refusedRunner": True})
    source_health.finish(now=T0 + timedelta(hours=3))
    report = json.loads(source_health.REPORT_PATH.read_text())
    assert report["run"]["pass"] == 203 and report["run"]["refusedRunner"] is True
    assert report["runHealth"] == json.loads(first)["runHealth"]          # la racha, la misma
    assert source_health.main(["rechazado", "203"]) == 0


def test_a_refused_note_of_the_other_lane_does_not_force_the_write(portal, monkeypatch):
    """La nota que cuenta es la del carril de la pasada: en una del carril de las mayores, el `run` del bot de siempre
    (arrastrado tal cual) no reescribe el informe aunque diga refusedRunner."""
    source_health.begin("2025-2026")
    source_health.note_run({"pass": 9, "refusedRunner": True})
    source_health.finish(now=T0)
    first = source_health.REPORT_PATH.read_text()
    monkeypatch.setenv("FIFLP_CATS", "infantil,cadete,juvenil")
    source_health.begin("2025-2026")
    source_health.finish(now=T0 + timedelta(hours=1))
    assert source_health.REPORT_PATH.read_text() == first


def refused(capsys, report, number, lane=None, monkeypatch=None):
    """source_health.py rechazado <número> sobre `report` (None: sin informe), en el carril de `lane` (FIFLP_CATS):
    (código, salida estándar)."""
    if lane is not None:
        monkeypatch.setenv("FIFLP_CATS", lane)
    if report is None:
        source_health.REPORT_PATH.unlink(missing_ok=True)
    else:
        source_health.REPORT_PATH.write_text(report if isinstance(report, str) else json.dumps(report))
    capsys.readouterr()
    code = source_health.main(["rechazado", str(number)])
    return code, capsys.readouterr().out


REFUSED = {"pass": 201, "groups": 107, "refreshed": 0, "seconds": 9, "pages": 2, "blocked": True, "cloud": "aws",
           "refusedRunner": True}


def test_the_refused_order_in_the_main_lane(portal, capsys):
    """Sale con 0 (e imprime el carril) solo si la nota de la pasada del carril del job es la de ESTA (su número) y
    dice refusedRunner; con 1 si no o si no se sabe."""
    assert refused(capsys, {"run": REFUSED}, 201) == (0, "principal\n")
    assert refused(capsys, {"run": REFUSED}, 202)[0] == 1                 # la nota es de otra pasada
    leyo = {k: v for k, v in REFUSED.items() if k != "refusedRunner"} | {"refreshed": 30, "cloud": "azure"}
    assert refused(capsys, {"run": leyo}, 201)[0] == 1                    # leyó
    frenada = {"pass": 201, "refreshed": 0, "cloud": "azure", "pauses": 1, "brakeAfter": [0], "blocked": True}
    assert refused(capsys, {"run": frenada}, 201)[0] == 1                 # frenó de verdad, en Azure
    assert refused(capsys, {"run": {**REFUSED, "refusedRunner": "true"}}, 201)[0] == 1
    assert refused(capsys, {"run": {**REFUSED, "pass": "201"}}, 201)[0] == 1
    assert refused(capsys, {"groups": {}}, 201)[0] == 1                   # sin nota (falló antes de la federación)
    assert refused(capsys, {"run": "x"}, 201)[0] == 1
    assert refused(capsys, None, 201)[0] == 1                              # sin informe
    assert refused(capsys, "{roto", 201)[0] == 1
    assert refused(capsys, {"run": REFUSED}, "")[0] == 1                  # sin número de pasada: no se sabe
    assert refused(capsys, {"run": REFUSED}, "doscientos uno")[0] == 1
    # La del carril de las mayores no es la de esta pasada.
    assert refused(capsys, {"run": leyo, "carriles": {"mayores": {"run": REFUSED}}}, 201)[0] == 1


def test_the_refused_order_in_the_lane_of_the_older_categories(portal, capsys, monkeypatch):
    """En una pasada del carril de las mayores (FIFLP_CATS), la nota es carriles.mayores.run, con el número de
    carril-mayores.yml; el `run` del bot de siempre no cuenta."""
    mayores = "infantil,cadete,juvenil"
    report = {"run": {**REFUSED, "pass": 40}, "carriles": {"mayores": {"runHealth": {"ok": True}, "run": {
        **REFUSED, "pass": 12}}}}
    assert refused(capsys, report, 12, mayores, monkeypatch) == (0, "mayores\n")
    assert refused(capsys, report, 40, mayores, monkeypatch)[0] == 1
    leyo = {"pass": 12, "refreshed": 9, "cloud": "azure"}
    assert refused(capsys, {"run": {**REFUSED, "pass": 12}, "carriles": {"mayores": {"run": leyo}}}, 12, mayores,
                   monkeypatch)[0] == 1
    assert refused(capsys, {"run": {**REFUSED, "pass": 12}}, 12, mayores, monkeypatch)[0] == 1


def test_the_refused_order_needs_its_number():
    assert source_health.main(["rechazado"]) == 2
    assert source_health.main(["rechazado", "1", "2"]) == 2
