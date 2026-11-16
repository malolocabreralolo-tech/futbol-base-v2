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
        "app", "torneos", "actas_bot", "actas", "goleadores", "detalle", "portal"}
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
    que lo intenta no sale igual."""
    with reconstruir.sin_red():
        with pytest.raises(reconstruir.SinRed):
            socket.create_connection(("www.fiflp.com", 443), timeout=1)
        with pytest.raises(reconstruir.SinRed):
            socket.socket().connect(("127.0.0.1", 9))
        with pytest.raises(Exception):
            import urllib.request
            urllib.request.urlopen("https://www.fiflp.com/", timeout=1)
        # El navegador, también sin Playwright instalado (el job de CI no lo tiene): lo que importe un lector.
        navegador = importlib.import_module("playwright.sync_api")
        with pytest.raises(reconstruir.SinRed):
            navegador.sync_playwright()
    assert socket.socket.connect is not reconstruir._prohibido     # restaurado al salir

    db = tmp_path / "base.db"
    sqlite3.connect(db).close()

    def rehacer(conn, carpeta):
        socket.create_connection(("www.fiflp.com", 443), timeout=1)

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
