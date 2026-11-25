"""reconstruir.py: qué parte de la base se rehace desde los originales guardados, comprobado sobre una copia.

Las rápidas, con una base mínima (la Maspalomas Cup importada de su original en una base vacía). Las lentas
(RECONSTRUIR=1, su paso propio en tests.yml), sobre la base de verdad: tardan minutos y el bot no puede
pagarlos en cada pasada."""
import hashlib
import importlib
import os
import re
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import reconstruir  # noqa: E402

LENTAS = pytest.mark.skipif(os.environ.get("RECONSTRUIR") != "1",
                            reason="sobre la base de verdad, minutos: RECONSTRUIR=1 (paso propio de tests.yml)")


def _sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def _base_con_torneos(path):
    """Una base vacía con el torneo importado de su original de verdad (scripts/maspalomas_cup_*_raw.json)."""
    from db import get_connection, init_db
    import import_torneos
    conn = get_connection(str(path))
    init_db(conn)
    import_torneos.import_changed_torneos(conn, folder=str(ROOT / "scripts"), log=lambda *a: None)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


def _torneos():
    return next(d for d in reconstruir.DOMINIOS if d.nombre == "torneos")


def test_los_dominios_del_minimo_son_rehacibles():
    rehacibles = {d.nombre for d in reconstruir.DOMINIOS if d.rehacible}
    assert {"app", "torneos", "actas_bot"} <= rehacibles
    assert {d.nombre for d in reconstruir.DOMINIOS} == {
        "app", "torneos", "actas_bot", "actas", "goleadores", "detalle", "portal", "mygol"}
    for d in reconstruir.DOMINIOS:
        assert d.tablas and d.originales, d.nombre
        assert all(list(ROOT.glob(g)) for g in d.originales), d.nombre
        assert d.rehacible or d.motivo, f"{d.nombre}: un dominio que no se rehace dice por qué"


def test_comprobar_no_toca_la_base(tmp_path):
    db = _base_con_torneos(tmp_path / "base.db")
    antes = _sha1(db)
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[_torneos()])
    assert _sha1(db) == antes
    assert not (tmp_path / "base.db-wal").exists() or (tmp_path / "base.db-wal").stat().st_size == 0
    assert out["torneos"]["igual"] is True, out
    assert out["torneos"]["filas"] > 0 and out["torneos"]["distintas"] == 0


def test_un_dominio_que_difiere_lo_dice(tmp_path):
    db = tmp_path / "base.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [("a", 1), ("b", 2), ("c", 3)])
    conn.commit()
    conn.close()

    def rehacer(conn, carpeta):
        conn.executemany("INSERT INTO t VALUES (?, ?)", [("a", 1), ("b", 20), ("c", 3)])

    prueba = reconstruir.Dominio(
        "prueba", ("t",), ("scripts/maspalomas_cup_*_raw.json",), True,
        borrar=lambda conn: conn.execute("DELETE FROM t"), rehacer=rehacer,
        consultas=(reconstruir.Consulta("t", "SELECT k, v FROM t", ("k",)),))
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[prueba])["prueba"]
    assert out["igual"] is False
    assert out["distintas"] == 1
    assert out["filas"] == 3
    assert "t" in out["detalle"]


def test_un_dominio_que_falla_no_sale_igual(tmp_path):
    db = tmp_path / "base.db"
    sqlite3.connect(db).close()

    def rehacer(conn, carpeta):
        raise RuntimeError("roto")

    prueba = reconstruir.Dominio("prueba", ("t",), ("scripts/maspalomas_cup_*_raw.json",), True,
                                 borrar=lambda conn: None, rehacer=rehacer, consultas=())
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[prueba])["prueba"]
    assert out["igual"] is False and "roto" in out["detalle"]


def test_un_dominio_que_escribe_fuera_de_la_copia_no_sale_igual(tmp_path):
    """Lo que un importador reescribe en scripts/ o junto a la base lo dice la comprobación (por contenido)."""
    root = tmp_path / "raiz"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "original.json").write_text("{}", encoding="utf-8")
    db = tmp_path / "base.db"
    sqlite3.connect(db).close()

    def igual(conn, carpeta):
        Path(carpeta, "original.json").write_text("{}", encoding="utf-8")     # mismo contenido: no cuenta

    def escribe(conn, carpeta):
        Path(carpeta, "original.json").write_text('{"x": 1}', encoding="utf-8")

    hacer = lambda nombre, rehacer: reconstruir.Dominio(nombre, ("t",), ("scripts/original.json",), True,
                                                        borrar=lambda conn: None, rehacer=rehacer, consultas=())
    out = reconstruir.comprobar(str(db), str(root), dominios=[hacer("igual", igual), hacer("escribe", escribe)])
    assert out["igual"]["igual"] is True, out
    assert out["escribe"]["igual"] is False and "scripts/original.json" in out["escribe"]["detalle"], out


def test_sin_red_durante_la_comprobacion(tmp_path):
    """Ningún importador sale a la red mientras se comprueba: un socket o un navegador lanzan, y el dominio
    que lo intenta no sale igual. Con un nombre que no resuelve (.invalid) y una IP de documentación: si el
    corte se rompiera, la prueba falla sin llegar a nadie."""
    with reconstruir.sin_red():
        with pytest.raises(reconstruir.SinRed):
            socket.create_connection(("federacion.invalid", 443), timeout=1)
        with pytest.raises(reconstruir.SinRed), socket.socket() as s:
            s.settimeout(1)
            s.connect(("192.0.2.1", 9))
        with pytest.raises(Exception):
            import urllib.request
            urllib.request.urlopen("https://federacion.invalid/", timeout=1)
        # El navegador, también sin Playwright instalado (el job de CI no lo tiene): lo que importe un lector.
        navegador = importlib.import_module("playwright.sync_api")
        with pytest.raises(reconstruir.SinRed):
            navegador.sync_playwright()
    assert socket.socket.connect is not reconstruir._prohibido     # restaurado al salir

    db = tmp_path / "base.db"
    sqlite3.connect(db).close()

    def rehacer(conn, carpeta):
        socket.create_connection(("federacion.invalid", 443), timeout=1)

    prueba = reconstruir.Dominio("prueba", ("t",), ("scripts/maspalomas_cup_*_raw.json",), True,
                                 borrar=lambda conn: None, rehacer=rehacer, consultas=())
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[prueba])["prueba"]
    assert out["igual"] is False and "red" in out["detalle"]


def test_cli_sale_con_1_si_un_rehacible_difiere(tmp_path):
    db = _base_con_torneos(tmp_path / "base.db")
    cmd = [sys.executable, str(ROOT / "scripts" / "reconstruir.py"), "--comprobar", "--dominio", "torneos",
           "--db", str(db)]
    bien = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert bien.returncode == 0, bien.stdout + bien.stderr
    assert re.search(r"torneos\s.*igual", bien.stdout), bien.stdout

    conn = sqlite3.connect(db)
    conn.execute("UPDATE tournament_matches SET home_score = coalesce(home_score, 0) + 7 "
                 "WHERE id = (SELECT min(id) FROM tournament_matches)")
    conn.commit()
    conn.close()
    mal = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert mal.returncode == 1, mal.stdout + mal.stderr
    assert re.search(r"torneos\s.*DISTINTO", mal.stdout), mal.stdout
    assert "1 distintas" in mal.stdout, mal.stdout


def test_un_aviso_del_rehacer_hace_que_no_salga_igual(tmp_path):
    """Lo que el rehacer apunta como aviso (temp._avisos) sale en el detalle y el dominio no sale igual, aunque
    las filas comparadas coincidan."""
    db = tmp_path / "base.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (k TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    def rehacer(conn, carpeta):
        reconstruir._avisar(conn, "aviso de prueba")

    prueba = reconstruir.Dominio("prueba", ("t",), ("scripts/maspalomas_cup_*_raw.json",), True,
                                 borrar=lambda conn: None, rehacer=rehacer,
                                 consultas=(reconstruir.Consulta("t", "SELECT k FROM t", ("k",)),))
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[prueba])["prueba"]
    assert out["igual"] is False and "aviso de prueba" in out["detalle"], out


# Un acta mínima, con jugadores inventados: lo justo para que update_fiflp.apply_acta la acepte.
_ACTA = {"consistent": True, "events": [], "staff": {},
         "header": {"home_team": "Equipo Norte", "away_team": "Equipo Sur", "home_score": 1, "away_score": 4},
         "lineups": {"home": [{"name": "JUGADOR UNO", "dorsal": 1, "role": "starter", "fiflp_id": 9001}],
                     "away": [{"name": "JUGADOR DOS", "dorsal": 2, "role": "starter", "fiflp_id": 9002}]}}


def _base_con_acta_del_bot(tmp_path, repetido):
    """Una base de 2026-27 con un partido de jornada 5 y su acta importada como la importa el bot (apply_acta), y
    su original en <raíz>/scripts/actas_bot_2026-2027_benjamin.jsonl. `repetido`: el mismo partido entrado otra
    vez con el rival con otro nombre y el mismo enlace al acta (fiflp_acta), sin acta, como lo deja el bot cuando
    la federación renombra un equipo de un partido ya jugado (FF13 de 2026-27, 17/11)."""
    import copy
    import json
    import migrate_actas_schema
    import migrate_compactar
    import migrate_identidad
    import update_fiflp
    from db import get_connection, init_db
    root = tmp_path / "raiz"
    (root / "scripts").mkdir(parents=True)
    linea = {"cod_acta": 111, "leida": "2026-11-17T11:43:59+00:00", "acta": _ACTA}
    (root / "scripts" / "actas_bot_2026-2027_benjamin.jsonl").write_text(
        json.dumps(linea, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    db = tmp_path / "base.db"
    conn = get_connection(str(db))
    init_db(conn)
    migrate_actas_schema.migrate(conn)
    migrate_compactar.migrate(conn)
    migrate_identidad.asegurar_esquema(conn)
    conn.execute("INSERT INTO seasons(name, start_year, end_year, is_current) VALUES ('2026-2027', 2026, 2027, 1)")
    conn.execute("INSERT INTO categories(name) VALUES ('BENJAMIN')")
    conn.execute("INSERT INTO groups(season_id, category_id, code) VALUES (1, 1, 'FF1')")
    conn.executemany("INSERT INTO teams(name) VALUES (?)", [("Equipo Norte",), ("Equipo Sur",), ("Otro Nombre",)])
    conn.execute("""INSERT INTO matches(group_id, jornada, date, home_team_id, away_team_id, home_score, away_score,
                    fiflp_acta) VALUES (1, 'Jornada 5', '2026-11-07', 1, 2, 1, 4, 111)""")
    if repetido:
        conn.execute("""INSERT INTO matches(group_id, jornada, date, home_team_id, away_team_id, home_score,
                        away_score, fiflp_acta) VALUES (1, 'Jornada 5', '2026-11-07', 1, 3, 1, 4, 111)""")
    assert update_fiflp.apply_acta(conn, 1, 111, copy.deepcopy(_ACTA), log=lambda *a: None)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return db, root


def _actas_bot():
    return next(d for d in reconstruir.DOMINIOS if d.nombre == "actas_bot")


def test_actas_bot_se_rehace_en_una_base_de_prueba(tmp_path):
    db, root = _base_con_acta_del_bot(tmp_path, repetido=False)
    out = reconstruir.comprobar(str(db), str(root), dominios=[_actas_bot()])["actas_bot"]
    assert out["igual"] is True and out["filas"] > 0, out


def test_actas_bot_con_el_partido_repetido_lo_dice(tmp_path):
    """Dos partidos de la temporada con el mismo enlace al acta: el original no casa con un solo partido, el acta
    no vuelve a entrar y la comprobación dice cuál es (por su código) y por qué."""
    db, root = _base_con_acta_del_bot(tmp_path, repetido=True)
    out = reconstruir.comprobar(str(db), str(root), dominios=[_actas_bot()])["actas_bot"]
    assert out["igual"] is False, out
    assert "acta 111" in out["detalle"] and "2 partidos" in out["detalle"], out["detalle"]


# ------------------------------------------------------------------ lentas, sobre la base de verdad

@LENTAS
def test_los_dominios_rehacibles_salen_iguales():
    db = ROOT / "futbolbase.db"
    antes = _sha1(db)
    out = reconstruir.comprobar(str(db), str(ROOT), dominios=[d for d in reconstruir.DOMINIOS if d.rehacible])
    assert _sha1(db) == antes
    malos = {k: v for k, v in out.items() if not v["igual"]}
    assert not malos, malos
    for nombre, r in out.items():
        assert r["filas"] > 0, nombre


@LENTAS
def test_el_documento_dice_lo_mismo():
    texto = (ROOT / "docs" / "reconstruccion.md").read_text(encoding="utf-8")
    # Las filas de la tabla de las partes: cuatro columnas, la primera el nombre del dominio y la última el veredicto.
    filas = dict(re.findall(r"^\|\s*`(\w+)`\s*\|[^|\n]*\|[^|\n]*\|\s*(Sí, comprobado|No)\s*\|\s*$", texto, re.M))
    assert set(filas) == {d.nombre for d in reconstruir.DOMINIOS}, filas
    assert {n for n, v in filas.items() if v == "Sí, comprobado"} == {d.nombre for d in reconstruir.DOMINIOS
                                                                     if d.rehacible}
