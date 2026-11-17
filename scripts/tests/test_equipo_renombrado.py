"""merge_renamed_teams: la federación renombra a un equipo a mitad de temporada, la lectura de una jornada ya
jugada no encuentra su partido (el rival tiene otro nombre) y lo entra otra vez. Los dos partidos llevan el
mismo enlace al acta (fiflp_acta): el bot se la pasaba de uno a otro en cada lectura del grupo. La función
junta al equipo del nombre viejo en el de la clasificación, solo en ese grupo. Equipos y datos, inventados."""
import sqlite3

import pytest

from db import SCHEMA, get_or_create_team
import update_fiflp as U

ACTA = 900005
J5 = "Jornada 5"


def _db():
    from migrate_actas_schema import migrate
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("INSERT INTO seasons(name,start_year,end_year,is_current) VALUES('2026-2027',2026,2027,1)")
    conn.execute("INSERT INTO categories(name) VALUES('BENJAMIN')")
    for code in ("BX1", "BX2"):
        conn.execute("INSERT INTO groups(season_id, category_id, code, name) VALUES(1, 1, ?, ?)", (code, code))
    conn.commit()
    return conn


def _gid(conn, code):
    return conn.execute("SELECT id FROM groups WHERE code=?", (code,)).fetchone()[0]


def _t(conn, name):
    return get_or_create_team(conn, name)


def _match(conn, gid, jornada, home, away, hs=None, as_=None, fiflp_acta=None, cod_acta=None):
    cur = conn.execute(
        """INSERT INTO matches(group_id, jornada, date, home_team_id, away_team_id, home_score, away_score,
                               fiflp_acta, cod_acta) VALUES (?,?,?,?,?,?,?,?,?)""",
        (gid, jornada, "2026-10-24", _t(conn, home), _t(conn, away), hs, as_, fiflp_acta, cod_acta))
    return cur.lastrowid


_PLAYER = [0]


def _acta_children(conn, mid, home, away):
    """Lo que cuelga de un acta importada: 17 apariciones (9 y 8), 5 sucesos (un cambio, con su pareja) y 6
    del cuerpo técnico (el árbitro, sin equipo)."""
    h, a = _t(conn, home), _t(conn, away)
    pids = []
    for i in range(17):
        _PLAYER[0] += 1
        pid = _PLAYER[0]
        conn.execute("INSERT INTO players(id, full_name, norm_name) VALUES (?,?,?)",
                     (pid, f"Jugador {pid}", f"jugador {pid}"))
        team = h if i < 9 else a
        conn.execute("""INSERT INTO appearances(match_id, team_id, player_id, dorsal, role, ord)
                        VALUES (?,?,?,?,?,?)""", (mid, team, pid, i + 1, "starter" if i % 9 < 7 else "sub", i))
        pids.append((pid, team))
    for pid, team in (pids[0], pids[9], pids[10]):
        conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute, goal_type) "
                     "VALUES (?,?,?,'goal',10,'normal')", (mid, team, pid))
    out = conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute) "
                       "VALUES (?,?,?,'sub_out',30)", (mid, h, pids[1][0])).lastrowid
    conn.execute("INSERT INTO match_events(match_id, team_id, player_id, kind, minute, pair_id) "
                 "VALUES (?,?,?,'sub_in',30,?)", (mid, h, pids[7][0], out))
    staff = [(None, "Árbitro/a Principal"), (h, "Entrenador"), (h, "DEL. Equipo"), (h, "DEL. Campo"),
             (a, "Entrenador"), (a, "DEL. Equipo")]
    for i, (team, role) in enumerate(staff):
        conn.execute("INSERT INTO match_staff_all(match_id, team_id, role, name, ord) VALUES (?,?,?,?,?)",
                     (mid, team, role, f"Persona {mid}-{i}", i))


def _standings(conn, gid, names):
    for pos, name in enumerate(names, 1):
        conn.execute("INSERT INTO standings(group_id, team_id, position, points, played) VALUES (?,?,?,?,?)",
                     (gid, _t(conn, name), pos, 0, 5))


def _renamed(acta_on_old=False, listed=("Nuevo",)):
    """BX1: «Viejo» (el nombre de antes) juega las jornadas 1 (de visitante, con su acta), 2 (de local, con su
    acta) y 4; la 5, dos veces: Casa – Viejo y Casa –
    Nuevo, el mismo partido con el mismo enlace al acta y el mismo marcador. El acta importada (su código y lo
    que cuelga de ella) va en la de «Nuevo» o, con acta_on_old, en la de «Viejo». La clasificación, con
    «Nuevo» (o lo que diga `listed`)."""
    conn = _db()
    gid = _gid(conn, "BX1")
    j1 = _match(conn, gid, "Jornada 1", "Otro", "Viejo", 2, 1, 900001, 900001)
    j2 = _match(conn, gid, "Jornada 2", "Viejo", "Tercero", 0, 0, 900002, 900002)
    _acta_children(conn, j1, "Otro", "Viejo")
    _acta_children(conn, j2, "Viejo", "Tercero")
    _match(conn, gid, "Jornada 3", "Casa", "Otro", 3, 3, 900003, 900003)
    _match(conn, gid, "Jornada 4", "Viejo", "Cuarto", 5, 0, 900004, 900004)
    old = _match(conn, gid, J5, "Casa", "Viejo", 1, 4, ACTA, ACTA if acta_on_old else None)
    new = _match(conn, gid, J5, "Casa", "Nuevo", 1, 4, ACTA, None if acta_on_old else ACTA)
    _acta_children(conn, old if acta_on_old else new, "Casa", "Viejo" if acta_on_old else "Nuevo")
    _match(conn, gid, "Jornada 6", "Nuevo", "Casa")
    _standings(conn, gid, [n for n in ("Casa", "Otro", "Tercero", "Cuarto") + tuple(listed)])
    conn.commit()
    return conn, gid


def _quiet(*_):
    pass


def _j5(conn, gid):
    return conn.execute("""SELECT m.id, h.name, a.name, home_score, away_score, cod_acta, fiflp_acta FROM matches m
                           JOIN teams h ON h.id=home_team_id JOIN teams a ON a.id=away_team_id
                           WHERE group_id=? AND jornada=?""", (gid, J5)).fetchall()


def _children(conn, mid):
    return tuple(conn.execute(f"SELECT count(*) FROM {t} WHERE match_id=?", (mid,)).fetchone()[0]
                 for t in ("appearances", "match_events", "match_staff_all"))


def _with_team(conn, gid, name):
    return conn.execute("""SELECT jornada FROM matches WHERE group_id=? AND ? IN (home_team_id, away_team_id)
                           ORDER BY jornada""", (gid, _t(conn, name))).fetchall()


def _strays(conn, gid):
    """Filas hijas de los partidos del grupo con un equipo que no es ni el local ni el visitante."""
    return [r for t in ("appearances", "match_events", "match_staff_all") for r in conn.execute(
        f"""SELECT '{t}', m.jornada, x.team_id FROM {t} x JOIN matches m ON m.id=x.match_id WHERE m.group_id=?
            AND x.team_id IS NOT NULL AND x.team_id NOT IN (m.home_team_id, m.away_team_id)""", (gid,))]


def _sides(conn, gid, jornada, table="appearances"):
    """{(lado, equipo): filas} de lo que cuelga del acta de una jornada."""
    return dict(((side, name), n) for side, name, n in conn.execute(
        f"""SELECT CASE x.team_id WHEN m.home_team_id THEN 'local' ELSE 'visitante' END, t.name, count(*)
            FROM {table} x JOIN matches m ON m.id=x.match_id JOIN teams t ON t.id=x.team_id
            WHERE m.group_id=? AND m.jornada=? GROUP BY 1, 2""", (gid, jornada)))


def _dump(conn):
    return "\n".join(conn.iterdump())


def _assert_merged(conn, gid):
    rows = _j5(conn, gid)
    assert len(rows) == 1, rows
    mid, home, away, hs, as_, cod, fiflp = rows[0]
    assert (home, away, hs, as_, cod, fiflp) == ("Casa", "Nuevo", 1, 4, ACTA, ACTA)
    assert _children(conn, mid) == (17, 5, 6)
    assert _with_team(conn, gid, "Viejo") == []
    assert [j for (j,) in _with_team(conn, gid, "Nuevo")] == ["Jornada 1", "Jornada 2", "Jornada 4", J5, "Jornada 6"]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT 1 FROM teams WHERE name='Viejo'").fetchone(), "el equipo no se borra"
    # Las actas donde «Viejo» era visitante (J1) y local (J2), con lo suyo en «Nuevo» y en su lado.
    assert _strays(conn, gid) == []
    assert _sides(conn, gid, "Jornada 1") == {("local", "Otro"): 9, ("visitante", "Nuevo"): 8}
    assert _sides(conn, gid, "Jornada 2") == {("local", "Nuevo"): 9, ("visitante", "Tercero"): 8}
    assert _sides(conn, gid, "Jornada 2", "match_events") == {("local", "Nuevo"): 3, ("visitante", "Tercero"): 2}
    assert _sides(conn, gid, "Jornada 2", "match_staff_all") == {("local", "Nuevo"): 3, ("visitante", "Tercero"): 2}
    assert _sides(conn, gid, J5) == {("local", "Casa"): 9, ("visitante", "Nuevo"): 8}


def test_junta_el_partido_repetido():
    conn, gid = _renamed()
    lines = []
    assert U.merge_renamed_teams(conn, gid, log=lines.append) == 1
    _assert_merged(conn, gid)
    assert len(lines) == 1 and "Viejo" in lines[0] and "Nuevo" in lines[0] and lines[0].count("BX1") == 1


def test_el_acta_en_la_fila_vieja_se_conserva():
    conn, gid = _renamed(acta_on_old=True)
    old = conn.execute("SELECT id FROM matches WHERE cod_acta=?", (ACTA,)).fetchone()[0]
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 1
    _assert_merged(conn, gid)
    assert _j5(conn, gid)[0][0] == old, "se queda la fila que tiene el acta"


def test_es_idempotente():
    conn, gid = _renamed()
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 1
    conn.commit()
    before = _dump(conn)
    lines = []
    assert U.merge_renamed_teams(conn, gid, log=lines.append) == 0
    assert _dump(conn) == before
    assert lines == []


def test_no_toca_otros_grupos():
    conn, gid = _renamed()
    other = _gid(conn, "BX2")
    _acta_children(conn, _match(conn, other, "Jornada 1", "Viejo", "Ajeno", 2, 2, 910001, 910001), "Viejo", "Ajeno")
    _match(conn, other, "Jornada 2", "Ajeno", "Viejo")
    _standings(conn, other, ["Viejo", "Ajeno"])
    conn.commit()

    def children():
        return [conn.execute(f"""SELECT x.* FROM {t} x JOIN matches m ON m.id=x.match_id WHERE m.group_id=?
                                 ORDER BY 1, 2, 3""", (other,)).fetchall()
                for t in ("appearances", "match_events", "match_staff_all")]

    kids = children()
    assert _sides(conn, other, "Jornada 1") == {("local", "Viejo"): 9, ("visitante", "Ajeno"): 8}
    rows = lambda: conn.execute("SELECT * FROM matches WHERE group_id=? ORDER BY id", (other,)).fetchall()  # noqa: E731
    standings = lambda: conn.execute("SELECT * FROM standings WHERE group_id=? ORDER BY id", (other,)).fetchall()  # noqa: E731
    before, table = rows(), standings()
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 1
    _assert_merged(conn, gid)
    assert rows() == before and standings() == table and children() == kids
    assert _sides(conn, other, "Jornada 1") == {("local", "Viejo"): 9, ("visitante", "Ajeno"): 8}
    assert [j for (j,) in _with_team(conn, other, "Viejo")] == ["Jornada 1", "Jornada 2"]
    # Y en el otro grupo no hay nada que juntar.
    assert U.merge_renamed_teams(conn, other, log=_quiet) == 0


@pytest.mark.parametrize("listed", [("Nuevo", "Viejo"), ()], ids=["los-dos", "ninguno"])
def test_ambiguo_no_toca_nada(listed):
    conn, gid = _renamed(listed=listed)
    before = _dump(conn)
    lines = []
    assert U.merge_renamed_teams(conn, gid, log=lines.append) == 0
    assert _dump(conn) == before
    assert len(lines) == 1
    assert lines[0].count("BX1") == 1
    assert str(_t(conn, "Viejo")) in lines[0] and str(_t(conn, "Nuevo")) in lines[0]


def test_dos_equipos_que_juegan_entre_si_no_se_juntan():
    """Un partido entre los dos nombres dice que son dos equipos: juntarlos lo dejaría contra sí mismo."""
    conn, gid = _renamed()
    _match(conn, gid, "Jornada 7", "Viejo", "Nuevo")
    conn.commit()
    before = _dump(conn)
    lines = []
    assert U.merge_renamed_teams(conn, gid, log=lines.append) == 0
    assert _dump(conn) == before
    assert len(lines) == 1 and lines[0].count("BX1") == 1
    assert str(_t(conn, "Viejo")) in lines[0] and str(_t(conn, "Nuevo")) in lines[0]


@pytest.mark.parametrize("actas", [(900005, 900006), (None, None)], ids=["otra-acta", "sin-enlace"])
def test_no_confunde_dos_partidos_distintos(actas):
    conn = _db()
    gid = _gid(conn, "BX1")
    _match(conn, gid, J5, "Casa", "Viejo", 1, 4, actas[0])
    _match(conn, gid, J5, "Casa", "Nuevo", 1, 4, actas[1])
    _standings(conn, gid, ["Casa", "Nuevo"])
    conn.commit()
    before = _dump(conn)
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 0
    assert _dump(conn) == before


def test_sin_marcador_no_se_toca():
    conn = _db()
    gid = _gid(conn, "BX1")
    _match(conn, gid, J5, "Casa", "Viejo", fiflp_acta=ACTA)
    _match(conn, gid, J5, "Casa", "Nuevo", fiflp_acta=ACTA)
    _standings(conn, gid, ["Casa", "Nuevo"])
    conn.commit()
    before = _dump(conn)
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 0
    assert _dump(conn) == before


def test_tras_write_round_con_el_rival_renombrado_queda_un_partido():
    """El camino del bot: la jornada 5 ya tiene su acta (en Casa – Viejo); la federación renombra a «Viejo»
    como «Nuevo» y la lectura de la jornada entra Casa – Nuevo otra vez, con el mismo enlace al acta, que
    queda pendiente. merge_renamed_teams deja uno, con el acta, y ya no hay acta que leer."""
    conn = _db()
    gid = _gid(conn, "BX1")
    _match(conn, gid, "Jornada 1", "Otro", "Viejo", 2, 1, 900001, 900001)
    old = _match(conn, gid, J5, "Casa", "Viejo", 1, 4, ACTA, ACTA)
    _acta_children(conn, old, "Casa", "Viejo")
    _standings(conn, gid, ["Casa", "Otro", "Nuevo"])
    conn.commit()
    U.write_round(conn, gid, J5, [{"home": "Casa", "away": "Nuevo", "hs": 1, "as": 4, "date": "2026-10-24",
                                   "time": "", "venue": "", "fiflp_acta": ACTA}], log=_quiet)
    assert len(_j5(conn, gid)) == 2, "write_round entra el partido otra vez"
    assert [r[1] for r in U.pending_actas(conn, gid)] == [ACTA]
    assert U.merge_renamed_teams(conn, gid, log=_quiet) == 1
    rows = _j5(conn, gid)
    assert [r[1:] for r in rows] == [("Casa", "Nuevo", 1, 4, ACTA, ACTA)]
    assert rows[0][0] == old and _children(conn, old) == (17, 5, 6)
    assert U.pending_actas(conn, gid) == []
    assert _with_team(conn, gid, "Viejo") == []
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # Otra lectura de la jornada ya encuentra su partido.
    U.write_round(conn, gid, J5, [{"home": "Casa", "away": "Nuevo", "hs": 1, "as": 4, "date": "2026-10-24",
                                   "time": "", "venue": "", "fiflp_acta": ACTA}], log=_quiet)
    assert len(_j5(conn, gid)) == 1
