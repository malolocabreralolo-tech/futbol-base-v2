"""La base en piezas (scripts/piezas.py): montar∘partir tiene que ser la identidad, fila a fila y con las mismas
identidades (clave, id o rowid), y partir solo toca las piezas que cambian. Bases de mentira con el esquema de
verdad (db.init_db + migrate_actas_schema), creadas en cada prueba en tmp_path; nunca la del repositorio.
Nombres inventados."""
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import db
import migrate_actas_schema
import piezas
from piezas import PESADAS, PiezasError, comparar, montar, partir, verificar

SCRIPTS = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- la base de mentira

def _jugador(conn, n):
    """Un jugador inventado: «PRUEBA 007, NOMBRE»."""
    nombre = f"PRUEBA {n:03d}, NOMBRE"
    conn.execute("INSERT OR IGNORE INTO players (id, full_name, norm_name) VALUES (?, ?, ?)",
                 (n, nombre, nombre.lower()))
    return n


def _acta(conn, gid, jornada, local, visitante):
    """Un partido con acta: ocho apariciones, cuatro sucesos (un cambio con pair_id mutuo) y cuatro del cuerpo
    técnico (el árbitro sin equipo y un delegado con ord negativo, como los de migrate_compactar)."""
    mid = conn.execute(
        "INSERT INTO matches (group_id, jornada, date, home_team_id, away_team_id, home_score, away_score, "
        "venue, cod_acta) VALUES (?, ?, '2025-10-04', ?, ?, 2, 1, 'CAMPO DE PRUEBA 1', ?)",
        (gid, jornada, local, visitante, 900000 + gid * 100 + int(jornada))).lastrowid
    for equipo in (local, visitante):
        for k in range(4):
            pid = _jugador(conn, equipo * 10 + k)
            conn.execute("INSERT INTO appearances (match_id, team_id, player_id, dorsal, role, goals, ord) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (mid, equipo, pid, k + 1, "starter" if k < 3 else "sub", int(k == 0), k))
    gol = conn.execute("INSERT INTO match_events (match_id, team_id, player_id, kind, minute, goal_type) "
                       "VALUES (?, ?, ?, 'goal', 12, 'normal')", (mid, local, local * 10)).lastrowid
    sale = conn.execute("INSERT INTO match_events (match_id, team_id, player_id, kind, minute) "
                        "VALUES (?, ?, ?, 'sub_out', 30)", (mid, local, local * 10 + 1)).lastrowid
    entra = conn.execute("INSERT INTO match_events (match_id, team_id, player_id, kind, minute, pair_id) "
                         "VALUES (?, ?, ?, 'sub_in', 30, ?)", (mid, local, local * 10 + 3, sale)).lastrowid
    conn.execute("UPDATE match_events SET pair_id = ? WHERE id = ?", (entra, sale))
    conn.execute("INSERT INTO match_events (match_id, team_id, player_id, kind, minute) "
                 "VALUES (?, ?, ?, 'yellow', 40)", (mid, visitante, visitante * 10 + 2))
    assert gol
    conn.executemany("INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (?, ?, ?, ?, ?)", [
        (mid, None, "Árbitro/a Principal", "ARBITRO INVENTADO, UNO", 0),
        (mid, local, "Entrenador", "ENTRENADOR INVENTADO, DOS", 0),
        (mid, visitante, "Entrenador", "ENTRENADOR INVENTADO, TRES", 0),
        (mid, local, "DEL. Campo", "DELEGADO INVENTADO, CUATRO", -1),
    ])
    conn.execute("INSERT INTO goals (match_id, minute, player_name, side, type) VALUES (?, 12, ?, 'h', 'normal')",
                 (mid, f"PRUEBA {local * 10:03d}, NOMBRE"))
    return mid


def _temporada(conn, nombre, actas, equipos, categoria):
    sid = conn.execute("INSERT INTO seasons (name, start_year, end_year) VALUES (?, ?, ?)",
                       (nombre, int(nombre[:4]), int(nombre[5:]))).lastrowid
    grupos = [conn.execute("INSERT INTO groups (season_id, category_id, code, name) VALUES (?, ?, ?, ?)",
                           (sid, categoria, f"G{k}", f"GRUPO {k}")).lastrowid for k in (1, 2)]
    for gid in grupos:
        for posicion, equipo in enumerate(equipos, 1):
            conn.execute("INSERT INTO standings (group_id, team_id, position, points) VALUES (?, ?, ?, ?)",
                         (gid, equipo, posicion, 10 - posicion))
        conn.execute("INSERT INTO scorers (group_id, player_name, team_id, goals, games) VALUES (?, ?, ?, 3, 2)",
                     (gid, f"PRUEBA {equipos[0] * 10:03d}, NOMBRE", equipos[0]))
    for k in range(actas):
        local, visitante = equipos[k % 4], equipos[(k + 1) % 4]
        _acta(conn, grupos[k % 2], str(k + 1), local, visitante)
    # Un partido sin acta (aún no jugado): en comun.db, sin filas pesadas.
    conn.execute("INSERT INTO matches (group_id, jornada, home_team_id, away_team_id) VALUES (?, '99', ?, ?)",
                 (grupos[0], equipos[0], equipos[1]))
    return sid, grupos


def _base(path, temporadas=("2024-2025", "2025-2026"), actas=6):
    path = Path(path)
    conn = sqlite3.connect(path)
    db.init_db(conn)
    migrate_actas_schema.migrate(conn, log=lambda *a: None)
    # venues (la de migrate, como la real): name TEXT PRIMARY KEY, así que su identidad es el rowid.
    conn.executemany("INSERT INTO venues (name, norm, address, city, surface, kind, code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     [(f"CAMPO DE PRUEBA {k}", f"campo de prueba {k}", f"CALLE INVENTADA {k}", "CIUDAD",
                       "Césped artificial", "F7", 100 + k) for k in range(1, 7)])
    categoria = conn.execute("INSERT INTO categories (name) VALUES ('ALEVIN')").lastrowid
    equipos = [conn.execute("INSERT INTO teams (name) VALUES (?)", (f"EQUIPO INVENTADO {letra}",)).lastrowid
               for letra in "ABCD"]
    for nombre in temporadas:
        _temporada(conn, nombre, actas, equipos, categoria)
    conn.commit()
    conn.close()
    return path


def _con(path):
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def _ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _contar(path, sql, params=()):
    conn = _ro(path)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _partidos_con_acta(conn, temporada):
    return [r[0] for r in conn.execute(
        "SELECT m.id FROM matches m JOIN groups g ON g.id = m.group_id JOIN seasons s ON s.id = g.season_id "
        "WHERE s.name = ? AND m.cod_acta IS NOT NULL ORDER BY m.id", (temporada,))]


def _grupos(conn, temporada):
    return [r[0] for r in conn.execute(
        "SELECT g.id FROM groups g JOIN seasons s ON s.id = g.season_id WHERE s.name = ? ORDER BY g.id",
        (temporada,))]


def _cambiar_un_gol(w, temporada):
    conn = _con(w)
    mid = _partidos_con_acta(conn, temporada)[0]
    conn.execute("UPDATE appearances SET goals = goals + 1 WHERE match_id = ? AND ord = 1 "
                 "AND team_id = (SELECT home_team_id FROM matches WHERE id = ?)", (mid, mid))
    conn.close()


def _foto(carpeta):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(carpeta).iterdir()}


def _manifiesto(carpeta):
    return json.loads((Path(carpeta) / "piezas.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- las pruebas del brief

def test_montar_partir_es_la_identidad(tmp_path):
    w = _base(tmp_path / "w.db"); partir(w, tmp_path / "base")
    montar(tmp_path / "base", tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []
    assert sorted(p.name for p in (tmp_path / "base").iterdir()) == [
        "actas-2024-2025.db", "actas-2025-2026.db", "comun.db", "piezas.json"]


def _elegir(conn, rnd, sql):
    """Una fila al azar, con el azar de la prueba (no el de SQLite): cada semilla repite sus cambios."""
    filas = conn.execute(sql).fetchall()
    return rnd.choice(filas) if filas else None


def _cambio_al_azar(conn, rnd, paso):
    """Uno de los cambios que hace el bot (y alguno que no): filas de las tres pesadas, de matches, scorers y
    venues; un partido que pasa a un grupo de otra temporada; una temporada nueva con su grupo y un acta."""
    temporadas = [r[0] for r in conn.execute("SELECT name FROM seasons ORDER BY name")]
    con_acta = [r[0] for r in conn.execute("SELECT DISTINCT match_id FROM appearances ORDER BY match_id")]
    op = rnd.choice(["ins_ap", "upd_ap", "del_ap", "ins_ev", "upd_ev", "del_ev", "ins_st", "upd_st", "del_st",
                     "ins_m", "upd_m", "del_m", "scorers", "venues", "mover", "temporada"])
    ap = "SELECT match_id, team_id, player_id FROM appearances ORDER BY 1, 2, 3"
    if op == "ins_ap" and con_acta:
        conn.execute("INSERT OR IGNORE INTO appearances (match_id, team_id, player_id, dorsal, role, ord) "
                     "VALUES (?, 1, ?, 20, 'sub', 20)", (rnd.choice(con_acta), _jugador(conn, 500 + paso)))
    elif op == "upd_ap" and (clave := _elegir(conn, rnd, ap)):
        conn.execute("UPDATE appearances SET dorsal = coalesce(dorsal, 0) + 1, yellow = 1 "
                     "WHERE match_id = ? AND team_id = ? AND player_id = ?", clave)
    elif op == "del_ap" and (clave := _elegir(conn, rnd, ap)):
        conn.execute("DELETE FROM appearances WHERE match_id = ? AND team_id = ? AND player_id = ?", clave)
    elif op == "ins_ev" and con_acta:
        conn.execute("INSERT INTO match_events (match_id, team_id, player_id, kind, minute) VALUES (?, 2, 20, "
                     "'red', ?)", (rnd.choice(con_acta), rnd.randint(1, 50)))
    elif op == "upd_ev" and (fila := _elegir(conn, rnd, "SELECT id FROM match_events ORDER BY id")):
        conn.execute("UPDATE match_events SET minute = coalesce(minute, 0) + 1 WHERE id = ?", fila)
    elif op == "del_ev" and (fila := _elegir(conn, rnd, "SELECT id FROM match_events WHERE pair_id IS NULL "
                                                        "ORDER BY id")):
        conn.execute("DELETE FROM match_events WHERE id = ?", fila)
    elif op == "ins_st" and con_acta:
        conn.execute("INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (?, NULL, "
                     "'Asistente', 'ASISTENTE INVENTADO, CINCO', 3)", (rnd.choice(con_acta),))
    elif op == "upd_st" and (fila := _elegir(conn, rnd, "SELECT rowid FROM match_staff_all ORDER BY 1")):
        conn.execute("UPDATE match_staff_all SET name = name || ' B' WHERE rowid = ?", fila)
    elif op == "del_st" and (fila := _elegir(conn, rnd, "SELECT rowid FROM match_staff_all ORDER BY 1")):
        conn.execute("DELETE FROM match_staff_all WHERE rowid = ?", fila)
    elif op == "ins_m":
        gid = rnd.choice(_grupos(conn, rnd.choice(temporadas)))
        conn.execute("INSERT INTO matches (group_id, jornada, home_team_id, away_team_id) VALUES (?, ?, 3, 4)",
                     (gid, f"N{paso}"))
    elif op == "upd_m" and (fila := _elegir(conn, rnd, "SELECT id FROM matches ORDER BY id")):
        conn.execute("UPDATE matches SET home_score = coalesce(home_score, 0) + 1 WHERE id = ?", fila)
    elif op == "del_m" and con_acta:
        mid = rnd.choice(con_acta)
        for tabla in ("appearances", "match_events", "match_staff_all", "goals"):
            conn.execute(f"DELETE FROM {tabla} WHERE match_id = ?", (mid,))
        conn.execute("DELETE FROM matches WHERE id = ?", (mid,))
    elif op == "scorers":
        sub = rnd.choice(["ins", "upd", "del"])
        fila = _elegir(conn, rnd, "SELECT id FROM scorers ORDER BY id")
        if sub == "ins":
            gid = rnd.choice(_grupos(conn, rnd.choice(temporadas)))
            conn.execute("INSERT OR IGNORE INTO scorers (group_id, player_name, team_id, goals) VALUES (?, ?, 2, 1)",
                         (gid, f"PRUEBA {600 + paso:03d}, NOMBRE"))
        elif sub == "upd" and fila:
            conn.execute("UPDATE scorers SET goals = coalesce(goals, 0) + 1 WHERE id = ?", fila)
        elif fila:
            conn.execute("DELETE FROM scorers WHERE id = ?", fila)
    elif op == "venues":
        sub = rnd.choice(["ins", "upd", "del"])
        fila = _elegir(conn, rnd, "SELECT rowid FROM venues ORDER BY 1")
        if sub == "ins":
            conn.execute("INSERT INTO venues (name, norm) VALUES (?, ?)", (f"CAMPO NUEVO {paso}", f"campo nuevo {paso}"))
        elif sub == "upd" and fila:
            conn.execute("UPDATE venues SET city = 'OTRA CIUDAD' WHERE rowid = ?", fila)
        elif fila:
            conn.execute("DELETE FROM venues WHERE rowid = ?", fila)
    elif op == "mover" and con_acta:
        mid = rnd.choice(con_acta)
        actual = conn.execute("SELECT g.season_id FROM matches m JOIN groups g ON g.id = m.group_id WHERE m.id = ?",
                              (mid,)).fetchone()[0]
        otros = [r[0] for r in conn.execute("SELECT id FROM groups WHERE season_id <> ? ORDER BY id", (actual,))]
        if otros:
            conn.execute("UPDATE matches SET group_id = ?, jornada = ? WHERE id = ?",
                         (rnd.choice(otros), f"M{paso}", mid))
    elif op == "temporada":
        anio = 2026 + paso
        nombre = f"{anio}-{anio + 1}"
        sid = conn.execute("INSERT INTO seasons (name, start_year, end_year) VALUES (?, ?, ?)",
                           (nombre, anio, anio + 1)).lastrowid
        gid = conn.execute("INSERT INTO groups (season_id, category_id, code) VALUES (?, 1, 'G1')", (sid,)).lastrowid
        _acta(conn, gid, "1", 1, 2)
    return op


@pytest.mark.parametrize("semilla", range(20))
def test_propiedad_con_cambios_al_azar(tmp_path, semilla):
    rnd = random.Random(semilla)
    w = _base(tmp_path / "w.db", actas=4)
    base = tmp_path / "base"
    partir(w, base)
    for paso in range(15):
        conn = _con(w)
        _cambio_al_azar(conn, rnd, paso)
        conn.close()
        partir(w, base)
        montada = tmp_path / f"m{paso}.db"
        montar(base, montada)
        assert comparar(w, montada) == [], f"semilla {semilla}, paso {paso}"


def test_partir_no_toca_las_piezas_sin_cambios(tmp_path):
    w = _base(tmp_path / "w.db"); partir(w, tmp_path / "base")
    antes = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "base").iterdir()}
    r = partir(w, tmp_path / "base")
    assert r["cambiadas"] == {} and r["creadas"] == [] and r["borradas"] == []
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "base").iterdir()} == antes
    _cambiar_un_gol(w, "2025-2026")
    r = partir(w, tmp_path / "base")
    assert set(r["cambiadas"]) == {"actas-2025-2026.db"}
    assert (tmp_path / "base/actas-2024-2025.db").read_bytes() == antes["actas-2024-2025.db"][0]
    assert (tmp_path / "base/comun.db").read_bytes() == antes["comun.db"][0]


_UNA_FILA = {
    # (cambiar una columna que no es la identidad, insertar, borrar), siempre en 2025-26
    "appearances": (
        "UPDATE appearances SET dorsal = 77 WHERE match_id = :mid AND ord = 2 AND team_id = "
        "(SELECT home_team_id FROM matches WHERE id = :mid)",
        "INSERT INTO appearances (match_id, team_id, player_id, dorsal, role, ord) VALUES (:mid, 1, 999, 9, 'sub', 9)",
        "DELETE FROM appearances WHERE match_id = :mid AND ord = 3 AND team_id = "
        "(SELECT home_team_id FROM matches WHERE id = :mid)"),
    "match_events": (
        "UPDATE match_events SET minute = 44 WHERE id = (SELECT min(id) FROM match_events WHERE match_id = :mid)",
        "INSERT INTO match_events (match_id, team_id, player_id, kind, minute) VALUES (:mid, 1, 10, 'yellow', 50)",
        "DELETE FROM match_events WHERE id = (SELECT max(id) FROM match_events WHERE match_id = :mid)"),
    "match_staff_all": (
        "UPDATE match_staff_all SET name = 'OTRO NOMBRE INVENTADO' WHERE rowid = "
        "(SELECT min(rowid) FROM match_staff_all WHERE match_id = :mid)",
        "INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (:mid, 1, 'Asistente', 'X', 5)",
        "DELETE FROM match_staff_all WHERE rowid = (SELECT max(rowid) FROM match_staff_all WHERE match_id = :mid)"),
}


@pytest.mark.parametrize("tabla", PESADAS)
def test_una_fila_cambiada_anadida_o_borrada_llega_a_su_pieza(tmp_path, tabla):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    mid = _partidos_con_acta(conn, "2025-2026")[1]
    conn.close()
    if tabla == "appearances":
        conn = _con(w); _jugador(conn, 999); conn.close()
        partir(w, base)          # el jugador nuevo, en comun.db, antes de la vuelta de la prueba
    for sql, esperado in zip(_UNA_FILA[tabla], [(1, 1), (1, 0), (0, 1)]):
        conn = _con(w)
        assert conn.execute(sql, {"mid": mid}).rowcount == 1
        conn.close()
        r = partir(w, base)
        assert r["cambiadas"] == {"actas-2025-2026.db": esperado}, sql
        montar(base, tmp_path / "m.db")
        assert comparar(w, tmp_path / "m.db") == []


def test_un_partido_que_cambia_de_temporada_mueve_sus_filas(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    mid = _partidos_con_acta(conn, "2025-2026")[0]
    destino = _grupos(conn, "2024-2025")[0]
    n = conn.execute("SELECT count(*) FROM appearances WHERE match_id = ?", (mid,)).fetchone()[0]
    conn.execute("UPDATE matches SET group_id = ?, jornada = 'MOVIDO' WHERE id = ?", (destino, mid))
    conn.close()
    r = partir(w, base)
    assert set(r["cambiadas"]) == {"actas-2024-2025.db", "actas-2025-2026.db", "comun.db"}
    sql = "SELECT count(*) FROM appearances WHERE match_id = ?"
    assert _contar(base / "actas-2025-2026.db", sql, (mid,)) == 0
    assert _contar(base / "actas-2024-2025.db", sql, (mid,)) == n > 0
    montar(base, tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []


def test_una_temporada_nueva_crea_su_pieza_y_una_vacia_la_borra(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    sid, grupos = _temporada(conn, "2026-2027", 1, [1, 2, 3, 4], 1)
    conn.close()
    r = partir(w, base)
    assert r["creadas"] == ["actas-2026-2027.db"]
    assert "actas-2026-2027.db" in _manifiesto(base)["piezas"]
    conn = _con(w)
    for tabla in PESADAS:
        conn.execute(f"DELETE FROM {tabla} WHERE match_id IN (SELECT id FROM matches WHERE group_id IN (?, ?))",
                     grupos)
    conn.close()
    r = partir(w, base)
    assert r["borradas"] == ["actas-2026-2027.db"]
    assert not (base / "actas-2026-2027.db").exists()
    assert "actas-2026-2027.db" not in _manifiesto(base)["piezas"]
    montar(base, tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []


def test_tabla_nueva_va_a_la_comun_sin_tocar_las_temporadas(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    antes = _foto(base)
    conn = _con(w)
    conn.execute("CREATE TABLE mygol_prueba (id INTEGER PRIMARY KEY, nombre TEXT)")
    conn.executemany("INSERT INTO mygol_prueba (nombre) VALUES (?)", [("UNO",), ("DOS",)])
    conn.close()
    r = partir(w, base)
    assert set(r["cambiadas"]) == {"comun.db"} and r["creadas"] == [] and r["borradas"] == []
    for pieza in ("actas-2024-2025.db", "actas-2025-2026.db"):
        assert (base / pieza).read_bytes() == antes[pieza][0]
    assert _manifiesto(base)["piezas"]["comun.db"]["filas"]["mygol_prueba"] == 2
    montar(base, tmp_path / "m.db")
    assert _contar(tmp_path / "m.db", "SELECT count(*) FROM mygol_prueba") == 2
    assert comparar(w, tmp_path / "m.db") == []


def test_columna_nueva_en_una_pesada_rehace_las_temporadas(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    conn.execute("ALTER TABLE appearances ADD COLUMN minutos INTEGER")
    conn.execute("UPDATE appearances SET minutos = 40 WHERE ord = 0")
    conn.close()
    r = partir(w, base)
    assert {"actas-2024-2025.db", "actas-2025-2026.db"} <= set(r["cambiadas"])
    conn = _ro(base / "actas-2025-2026.db")
    assert "minutos" in [f[1] for f in conn.execute("PRAGMA table_info(appearances)")]
    conn.close()
    montar(base, tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []
    assert partir(w, base)["cambiadas"] == {}


def test_autoincremento_no_reutiliza_ids(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    conn = _con(w)
    alto = conn.execute("SELECT max(id) FROM matches").fetchone()[0]
    for tabla in PESADAS + ("goals",):
        conn.execute(f"DELETE FROM {tabla} WHERE match_id = ?", (alto,))
    conn.execute("DELETE FROM matches WHERE id = ?", (alto,))
    assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'matches'").fetchone()[0] == alto
    secuencia = conn.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name").fetchall()
    conn.close()
    partir(w, base)
    montar(base, tmp_path / "m.db")
    m = _con(tmp_path / "m.db")
    assert m.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name").fetchall() == secuencia
    nuevo = m.execute("INSERT INTO matches (group_id, jornada, home_team_id, away_team_id) VALUES (1, 'X', 1, 2)"
                      ).lastrowid
    m.close()
    assert nuevo > alto


def test_conserva_los_rowid(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"

    def huecos():
        conn = _con(w)
        for tabla in ("match_staff_all", "venues"):
            filas = [r[0] for r in conn.execute(f"SELECT rowid FROM {tabla} ORDER BY rowid")]
            medio = filas[len(filas) // 3: len(filas) // 3 + 2]
            conn.execute(f"DELETE FROM {tabla} WHERE rowid IN ({','.join('?' * len(medio))})", medio)
        conn.close()

    def iguales(montada):
        for tabla in ("match_staff_all", "venues"):
            sql = f"SELECT rowid, * FROM {tabla} ORDER BY rowid"
            a, b = _ro(w), _ro(montada)
            assert a.execute(sql).fetchall() == b.execute(sql).fetchall(), tabla
            a.close(); b.close()

    huecos()
    partir(w, base)                         # desde cero
    montar(base, tmp_path / "m1.db")
    iguales(tmp_path / "m1.db")
    huecos()
    partir(w, base)                         # en sitio
    montar(base, tmp_path / "m2.db")
    iguales(tmp_path / "m2.db")


def test_las_piezas_no_van_en_wal(tmp_path):
    w = _base(tmp_path / "w.db")
    conn = db.get_connection(str(w))        # WAL, como la del bot
    conn.execute("UPDATE matches SET venue = 'OTRO CAMPO' WHERE id = 1")
    conn.commit()
    base = tmp_path / "base"
    partir(w, base)
    conn.close()
    for pieza in base.glob("*.db"):
        assert pieza.read_bytes()[18:20] == b"\x01\x01", pieza.name
    montar(base, tmp_path / "m.db")
    assert (tmp_path / "m.db").read_bytes()[18:20] == b"\x02\x02"
    assert verificar(w, base)["ok"] is True
    # Una pieza que alguien pasa a WAL: no se sube.
    p = sqlite3.connect(base / "actas-2024-2025.db")
    p.execute("PRAGMA journal_mode=WAL")
    p.close()
    r = verificar(w, base)
    assert r["ok"] is False and any("actas-2024-2025.db" in m and "DELETE" in m for m in r["motivos"])
    # partir la rehace en modo DELETE (sin -wal ni -shm al lado) y ya se puede subir.
    assert set(partir(w, base)["cambiadas"]) == {"actas-2024-2025.db"}
    assert (base / "actas-2024-2025.db").read_bytes()[18:20] == b"\x01\x01"
    assert sorted(p.name for p in base.iterdir()) == [
        "actas-2024-2025.db", "actas-2025-2026.db", "comun.db", "piezas.json"]
    assert verificar(w, base)["ok"] is True


def test_montar_no_hereda_un_wal_viejo(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    destino = tmp_path / "m.db"
    destino.write_bytes(b"lo de antes")
    Path(f"{destino}-wal").write_bytes(b"0123456789")
    with pytest.raises(PiezasError, match="-wal"):
        montar(base, destino)
    assert destino.read_bytes() == b"lo de antes"
    Path(f"{destino}-wal").write_bytes(b"")
    Path(f"{destino}-shm").write_bytes(b"x" * 100)
    montar(base, destino)
    assert not Path(f"{destino}-wal").exists() and not Path(f"{destino}-shm").exists()
    assert comparar(w, destino) == []
    assert not list(tmp_path.glob(".m.db.*")), "sin temporales sueltos"


def test_montar_comprueba_el_manifiesto(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)

    def caso(nombre):
        copia = tmp_path / nombre
        shutil.copytree(base, copia)
        return copia

    falta = caso("falta")
    (falta / "actas-2024-2025.db").unlink()
    sobra = caso("sobra")
    shutil.copy(sobra / "actas-2024-2025.db", sobra / "actas-2019-2020.db")
    una_mas = caso("una_mas")
    p = sqlite3.connect(una_mas / "actas-2024-2025.db")
    p.execute("INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (1, 1, 'Asistente', 'X', 9)")
    p.commit()
    p.close()
    # Con los bytes del manifiesto puestos a los de la pieza: lo que salta es la cuenta de filas.
    man = _manifiesto(una_mas)
    man["piezas"]["actas-2024-2025.db"]["bytes"] = (una_mas / "actas-2024-2025.db").stat().st_size
    (una_mas / "piezas.json").write_text(json.dumps(man, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    for carpeta, texto in ((falta, "actas-2024-2025.db"), (sobra, "actas-2019-2020.db"),
                           (una_mas, "match_staff_all")):
        destino = tmp_path / f"m-{carpeta.name}.db"
        with pytest.raises(PiezasError, match=texto):
            montar(carpeta, destino)
        assert not destino.exists()
        assert not list(tmp_path.glob(f".{destino.name}.*"))


def test_montar_contra_un_fichero_distinto_no_toca_el_destino(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    destino = tmp_path / "m.db"
    montar(base, destino)
    antes = destino.read_bytes()
    otra = tmp_path / "otra.db"
    shutil.copy(w, otra)
    _cambiar_un_gol(otra, "2024-2025")
    with pytest.raises(PiezasError, match="no son iguales"):
        montar(base, destino, contra=otra)
    assert destino.read_bytes() == antes
    montar(base, destino, contra=w)
    assert comparar(w, destino) == []


def test_solo_comun(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    filas = montar(base, tmp_path / "m.db", solo_comun=True)
    for tabla in PESADAS:
        assert filas[tabla] == 0
        assert _contar(tmp_path / "m.db", f"SELECT count(*) FROM {tabla}") == 0
    a, b = _ro(w), _ro(tmp_path / "m.db")
    for (tabla,) in a.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT IN "
                              "('appearances', 'match_events', 'match_staff_all')").fetchall():
        assert piezas.huella(a, tabla) == piezas.huella(b, tabla), tabla
    assert piezas.esquema(a) == piezas.esquema(b)
    a.close(); b.close()


def test_filas_sin_temporada_no_se_parten(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    antes = _foto(base)
    conn = _con(w)
    conn.execute("INSERT INTO appearances (match_id, team_id, player_id, dorsal, role, ord) "
                 "VALUES (777777, 1, 10, 1, 'starter', 0)")
    conn.close()
    with pytest.raises(PiezasError, match=r"sin temporada.*777777"):
        partir(w, base)
    assert _foto(base) == antes


def test_un_trigger_no_se_admite(tmp_path):
    w = _base(tmp_path / "w.db")
    conn = _con(w)
    conn.execute("CREATE TRIGGER t_prueba AFTER INSERT ON goals BEGIN UPDATE matches SET venue = 'X' "
                 "WHERE id = NEW.match_id; END")
    conn.close()
    with pytest.raises(PiezasError, match="trigger"):
        partir(w, tmp_path / "base")


def _cambio_en_todas(w):
    _cambiar_un_gol(w, "2024-2025")
    _cambiar_un_gol(w, "2025-2026")
    conn = _con(w)
    conn.execute("UPDATE teams SET shield_filename = 'escudo-inventado.png' WHERE id = 1")
    conn.close()


def _partir_con_corte(w, base, corte):
    codigo = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import piezas; "
              "piezas.partir(Path(sys.argv[2]), Path(sys.argv[3]))")
    env = dict(os.environ, PIEZAS_CORTE_PRUEBA=corte)
    return subprocess.run([sys.executable, "-c", codigo, str(SCRIPTS), str(w), str(base)], env=env,
                          capture_output=True, text=True, timeout=120)


def test_corte_entre_dos_piezas(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    _cambio_en_todas(w)
    r = _partir_con_corte(w, base, "tras:1")
    assert r.returncode == 3, r.stderr
    assert verificar(w, base)["ok"] is False
    partir(w, base)
    assert verificar(w, base)["ok"] is True


def test_corte_dentro_de_una_pieza(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    _cambio_en_todas(w)
    r = _partir_con_corte(w, base, "dentro:1")
    assert r.returncode == 3, r.stderr
    assert [p.name for p in base.glob("*-journal")] == ["actas-2024-2025.db-journal"]
    v = verificar(w, base)
    assert v["ok"] is False and any("se cortó a medias" in m for m in v["motivos"])
    partir(w, base)
    assert not list(base.glob("*-journal"))
    assert verificar(w, base)["ok"] is True


def test_diario_caliente_se_deshace(tmp_path):
    """Un corte con la pieza ya a medio escribir (SQLite vuelca páginas antes del commit si no le caben en
    memoria): el diario está caliente y partir, al abrir la pieza, la devuelve a su último commit."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    pieza = base / "actas-2025-2026.db"
    codigo = ("import os, sqlite3, sys; c = sqlite3.connect(sys.argv[1], isolation_level=None); "
              "c.execute('PRAGMA cache_size = 1'); c.execute('BEGIN'); c.execute('DELETE FROM appearances'); "
              "c.execute('DELETE FROM match_staff_all'); os._exit(3)")
    r = subprocess.run([sys.executable, "-c", codigo, str(pieza)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 3, r.stderr
    diario = Path(f"{pieza}-journal")
    assert diario.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7"), "el diario tiene que estar caliente"
    assert verificar(w, base)["ok"] is False
    _cambiar_un_gol(w, "2025-2026")
    assert partir(w, base)["cambiadas"] == {"actas-2025-2026.db": (1, 1)}
    assert not diario.exists()
    assert verificar(w, base)["ok"] is True


def test_verificar_avisa_de_la_pieza_mayor(tmp_path, monkeypatch):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    tamanos = {p.name: p.stat().st_size for p in base.glob("*.db")}
    mayor = max(tamanos.items(), key=lambda kv: kv[1])
    r = verificar(w, base)
    assert r == {"ok": True, "motivos": [], "mayor": mayor, "total": sum(tamanos.values())}
    monkeypatch.setattr(piezas, "PARADA_MB", 0)
    r = verificar(w, base)
    assert r["ok"] is False and any(mayor[0] in m and "GitHub" in m for m in r["motivos"])


def test_una_pieza_que_desaparece_no_se_sube(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    (base / "actas-2024-2025.db").unlink()
    r = verificar(w, base)
    assert r["ok"] is False and any("actas-2024-2025.db" in m for m in r["motivos"])


def test_solo_biblioteca_estandar(tmp_path):
    codigo = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('piezas', sys.argv[1]); "
              "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.FORMATO)")
    r = subprocess.run([sys.executable, "-I", "-c", codigo, str(SCRIPTS / "piezas.py")], cwd=tmp_path,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1"


def test_cli(tmp_path, capsys):
    w = _base(tmp_path / "w.db"); d = tmp_path / "base"
    assert piezas.main(["partir", "--db", str(w), "--piezas", str(d)]) == 0
    assert capsys.readouterr().out.startswith("partida ")
    m = tmp_path / "m.db"
    assert piezas.main(["montar", "--db", str(m), "--piezas", str(d)]) == 0
    assert capsys.readouterr().out.startswith("montada ")
    assert piezas.main(["verificar", "--db", str(w), "--piezas", str(d)]) == 0
    assert capsys.readouterr().out.startswith("piezas iguales a la base: ")
    assert piezas.main(["comparar", "--db", str(w), "--piezas", str(d)]) == 0
    assert capsys.readouterr().out.strip() == "iguales"
    _cambiar_un_gol(w, "2025-2026")
    assert piezas.main(["partir", "--db", str(w), "--piezas", str(d)]) == 0
    salida = capsys.readouterr().out.splitlines()
    assert salida == [f"partida {w}: 0 creadas, 1 cambiadas, 0 borradas, 2 sin cambios",
                      "  actas-2025-2026.db: +1 -1"]
    pieza = d / "actas-2024-2025.db"
    datos = pieza.read_bytes()
    pieza.write_bytes(datos[: len(datos) // 2])
    otro = tmp_path / "otro.db"
    assert piezas.main(["montar", "--db", str(otro), "--piezas", str(d)]) == 1
    assert capsys.readouterr().out.strip()
    assert not otro.exists()


# ---------------------------------------------------------------- formas de perder una fila (además del brief)

def test_nombre_pieza():
    assert piezas.nombre_pieza("2025-2026") == "actas-2025-2026.db"
    for malo in ("2025/2026", "2025-26", "2025-2026\n", "../2025-2026", "２０２５-２０２６"):
        with pytest.raises(ValueError):
            piezas.nombre_pieza(malo)


def test_identidad_y_columnas(tmp_path):
    w = _base(tmp_path / "w.db")
    conn = _ro(w)
    assert piezas.identidad(conn, "appearances") == ["match_id", "team_id", "player_id"]
    assert piezas.identidad(conn, "match_events") == ["id"]
    assert piezas.identidad(conn, "matches") == ["id"]
    for tabla in ("match_staff_all", "venues"):
        assert piezas.identidad(conn, tabla) == ["rowid"]
    assert piezas.columnas(conn, "match_staff_all") == ["rowid", "match_id", "team_id", "role", "name", "ord"]
    assert piezas.columnas(conn, "appearances")[:4] == ["match_id", "team_id", "player_id", "dorsal"]
    conn.close()


def test_filas_iguales_salvo_el_rowid(tmp_path):
    """Dos filas del cuerpo técnico idénticas (la federación repite un cargo): sin el rowid en la comparación,
    EXCEPT y la huella las verían como una sola."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    mid = _partidos_con_acta(conn, "2025-2026")[0]
    fila = (mid, 1, "Entrenador", "REPETIDO INVENTADO", 7)
    conn.execute("INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (?, ?, ?, ?, ?)", fila)
    conn.close()
    assert partir(w, base)["cambiadas"] == {"actas-2025-2026.db": (1, 0)}
    conn = _con(w)
    conn.execute("INSERT INTO match_staff_all (match_id, team_id, role, name, ord) VALUES (?, ?, ?, ?, ?)", fila)
    conn.close()
    assert partir(w, base)["cambiadas"] == {"actas-2025-2026.db": (1, 0)}
    sql = "SELECT count(*) FROM match_staff_all WHERE name = 'REPETIDO INVENTADO'"
    assert _contar(base / "actas-2025-2026.db", sql) == 2
    montar(base, tmp_path / "m.db")
    assert _contar(tmp_path / "m.db", sql) == 2 and comparar(w, tmp_path / "m.db") == []
    conn = _con(w)
    conn.execute("DELETE FROM match_staff_all WHERE rowid = (SELECT max(rowid) FROM match_staff_all "
                 "WHERE name = 'REPETIDO INVENTADO')")
    conn.close()
    assert partir(w, base)["cambiadas"] == {"actas-2025-2026.db": (0, 1)}
    montar(base, tmp_path / "m2.db")
    assert _contar(tmp_path / "m2.db", sql) == 1 and comparar(w, tmp_path / "m2.db") == []


def test_valores_raros_sobreviven(tmp_path):
    """REAL que no son exactos en decimal, un entero y un real iguales en una columna sin tipo, textos con bytes
    que no son UTF-8 o con un NUL, un blob con los mismos bytes que un texto y una columna NOCASE: montar los
    devuelve iguales y partir ve cada cambio entre ellos (EXCEPT los daría por iguales)."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    conn = _con(w)
    conn.execute("CREATE TABLE rareza (id INTEGER PRIMARY KEY, r REAL, u, t TEXT COLLATE NOCASE, b BLOB)")
    conn.executemany("INSERT INTO rareza (r, u, t, b) VALUES (?, ?, ?, ?)", [
        (0.1 + 0.2, 1, "abc", b"abc"), (1e-310, 2.5, "A\x00B", None), (-1.5e300, "texto", None, b"\x00\xff"),
        (28.123456789012345, None, "ñandú", b"")])
    conn.execute("INSERT INTO rareza (r, u, t, b) VALUES (1.0, CAST(x'ff41' AS TEXT), CAST(x'c328' AS TEXT), x'ff41')")
    conn.execute("UPDATE match_staff_all SET name = CAST(x'4e4fff' AS TEXT) WHERE rowid = 1")
    conn.close()
    partir(w, base)
    montar(base, tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []
    cambios = [
        "UPDATE rareza SET u = 1.0 WHERE id = 1",                  # entero → real igual
        "UPDATE rareza SET t = 'ABC' WHERE id = 1",                # solo cambia la caja (NOCASE)
        "UPDATE rareza SET b = CAST(b AS TEXT) WHERE id = 1",      # blob → texto con los mismos bytes
        "UPDATE rareza SET r = 0.30000000000000004 + 1e-16 WHERE id = 1",
    ]
    for k, sql in enumerate(cambios):
        conn = _con(w)
        assert conn.execute(sql).rowcount == 1
        conn.close()
        assert partir(w, base)["cambiadas"] == {"comun.db": (1, 1)}, sql
        montar(base, tmp_path / f"m{k}.db")
        assert comparar(w, tmp_path / f"m{k}.db") == [], sql
    conn = _con(w)
    conn.execute("UPDATE match_staff_all SET name = CAST(x'4e4ffe' AS TEXT) WHERE rowid = 1")
    conn.close()
    assert partir(w, base)["cambiadas"] == {"actas-2024-2025.db": (1, 1)}


def test_comparar_ve_lo_que_except_no_ve(tmp_path):
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    for path, valor in ((a, 1), (b, 1.0)):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, u)")
        conn.execute("INSERT INTO t VALUES (1, ?)", (valor,))
        conn.commit()
        conn.close()
    assert comparar(a, b) == ["t: las mismas 1 filas, con otro contenido"]


def test_grupo_borrado_deja_filas_sin_temporada(tmp_path):
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    mid = _partidos_con_acta(conn, "2025-2026")[0]
    gid = conn.execute("SELECT group_id FROM matches WHERE id = ?", (mid,)).fetchone()[0]
    conn.execute("DELETE FROM groups WHERE id = ?", (gid,))
    conn.close()
    with pytest.raises(PiezasError, match=f"sin temporada.*{mid}"):
        partir(w, base)


def test_una_base_montada_solo_con_la_comun_no_se_parte(tmp_path):
    """Partir una base sin actas borraría todas las piezas de temporada."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    antes = _foto(base)
    m = tmp_path / "m.db"
    montar(base, m, solo_comun=True)
    with pytest.raises(PiezasError, match="solo con la parte común"):
        partir(m, base)
    Path(f"{m}.piezas").unlink()
    with pytest.raises(PiezasError, match="sin actas"):
        partir(m, base)
    assert _foto(base) == antes


def test_tabla_interna_no_se_admite(tmp_path):
    w = _base(tmp_path / "w.db")
    conn = _con(w)
    conn.execute("ANALYZE")
    conn.close()
    with pytest.raises(PiezasError, match="sqlite_stat1"):
        partir(w, tmp_path / "base")


def test_marca_de_las_piezas(tmp_path):
    import hashlib
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    sha = hashlib.sha256((base / "piezas.json").read_bytes()).hexdigest()
    assert Path(f"{w}.piezas").read_text(encoding="utf-8").strip() == sha
    montar(base, tmp_path / "m.db")
    assert Path(f"{tmp_path / 'm.db'}.piezas").read_text(encoding="utf-8").strip() == sha
    man = _manifiesto(base)
    assert man["formato"] == 1
    assert set(man["piezas"]["comun.db"]["filas"]) & set(PESADAS) == set()
    assert "sqlite_sequence" not in man["piezas"]["comun.db"]["filas"]
    assert set(man["piezas"]["actas-2025-2026.db"]["filas"]) == set(PESADAS)
    for nombre, pieza in man["piezas"].items():
        assert pieza["bytes"] == (base / nombre).stat().st_size


def test_restos_de_un_corte_se_limpian(tmp_path):
    """Un temporal de una pieza a medio rehacer (corte dentro del rehacer): partir lo quita y verificar no
    lo da por bueno mientras esté."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    resto = base / ".comun.db.abc123.tmp"
    resto.write_bytes(b"medio")
    r = verificar(w, base)
    assert r["ok"] is False and any(resto.name in m for m in r["motivos"])
    partir(w, base)
    assert not resto.exists()
    assert verificar(w, base)["ok"] is True


def test_una_identidad_en_dos_piezas_no_se_monta(tmp_path):
    """La misma fila (el mismo rowid) en dos piezas, como tras un corte a mitad de mover un partido: montar no
    se queda con una en silencio (ni INSERT OR IGNORE ni OR REPLACE), falla."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    origen, destino = base / "actas-2025-2026.db", base / "actas-2024-2025.db"
    p = sqlite3.connect(destino)
    p.execute("ATTACH DATABASE ? AS o", (str(origen),))
    p.execute("INSERT INTO main.match_staff_all (rowid, match_id, team_id, role, name, ord) "
              "SELECT rowid, match_id, team_id, role, name, ord FROM o.match_staff_all ORDER BY rowid LIMIT 1")
    p.commit()
    p.close()
    man = _manifiesto(base)
    man["piezas"]["actas-2024-2025.db"]["bytes"] = destino.stat().st_size
    man["piezas"]["actas-2024-2025.db"]["filas"]["match_staff_all"] += 1
    (base / "piezas.json").write_text(json.dumps(man, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
    with pytest.raises(PiezasError, match="UNIQUE"):
        montar(base, tmp_path / "m.db")
    assert not (tmp_path / "m.db").exists()


def test_corte_tras_mover_un_partido_no_monta_duplicados(tmp_path):
    """Un partido que pasa a una temporada anterior: la pieza de destino se escribe antes que la de origen. Un
    corte entre las dos deja sus filas en las dos; montar falla y partir otra vez lo arregla."""
    w = _base(tmp_path / "w.db"); base = tmp_path / "base"
    partir(w, base)
    conn = _con(w)
    mid = _partidos_con_acta(conn, "2025-2026")[0]
    conn.execute("UPDATE matches SET group_id = ?, jornada = 'MOVIDO' WHERE id = ?",
                 (_grupos(conn, "2024-2025")[0], mid))
    conn.close()
    r = _partir_con_corte(w, base, "tras:1")
    assert r.returncode == 3, r.stderr
    sql = "SELECT count(*) FROM appearances WHERE match_id = ?"
    assert _contar(base / "actas-2024-2025.db", sql, (mid,)) == _contar(base / "actas-2025-2026.db", sql, (mid,)) > 0
    with pytest.raises(PiezasError):
        montar(base, tmp_path / "m.db")
    assert verificar(w, base)["ok"] is False
    partir(w, base)
    assert _contar(base / "actas-2025-2026.db", sql, (mid,)) == 0
    assert verificar(w, base)["ok"] is True
