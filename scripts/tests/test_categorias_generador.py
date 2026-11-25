"""generate_js por categorías perezosas (parte E2, tarea 1): alevín, infantil, cadete y juvenil, cada una en su
fichero (generate_js.LAZY), con la forma de lo de alevín (docs/alevin.md §4 y §5).

  - data-<clave>.js (temporada en curso) SIEMPRE, aunque esté vacío, con <GRUPOS>, <S>_STATS, HISTORY_<S>,
    GOL_<S>, ESTADOS_<S>, EQUIPOS_<S> y, solo en las nuevas, CAMPOS_<S> (los campos que no están en el CAMPOS de
    data-history.js).
  - La carga inicial no gana nada: data-history.js sigue con benjamín y prebenjamín (y sus campos, con los de
    alevín, como hoy); MATCH_DETAIL, sin las nuevas, que van en data-matchdetail-<clave>.js.
  - Temporadas pasadas: data-season-<S>-<clave>.js, solo si la temporada tiene grupos de esa categoría.

Base sintética (nombres inventados), con categorias.EN_WEB parcheado con las seis salvo donde se dice; la última,
sobre una copia de la base real (salta sin futbolbase.db).
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402

DB_PATH = ROOT / "futbolbase.db"
SEIS = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")


def const(text, name):
    m = re.search(rf"^const {name}=(.*?);$", text, re.M)
    assert m, f"sin const {name}"
    return json.loads(m.group(1))


def entradas(detail):
    """Las entradas de un MATCH_DETAIL (las de una clave repetida, todas)."""
    return [e for v in detail.values() for e in (v["list"] if v.get("dup") else [v])]


def site(tmp_path, cadete_pasado=True):
    """2026-27 en curso con FF1 (benjamín), AL1 (alevín) e INFPG1 (infantil); 2025-26 cerrada con FF1 y, si se
    pide, CADNG1 (cadete). «Club Uno» juega en las tres de 2026-27; «Club Infantil», solo en infantil (y su
    campo, «CAMPO INFANTIL», solo sale en sus partidos); «Club Cadete», solo en el cadete de 2025-26."""
    from migrate_actas_schema import migrate
    import import_fp_app
    import import_fiflp_detalle
    db = tmp_path / "fb.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    migrate(conn)
    import_fp_app.migrate(conn)
    import_fiflp_detalle.migrate(conn)
    conn.executescript("""
      INSERT INTO seasons(id,name,start_year,end_year,is_current) VALUES (1,'2026-2027',2026,2027,1),
                                                                         (2,'2025-2026',2025,2026,0);
      INSERT INTO categories(id,name) VALUES (1,'BENJAMIN'),(2,'PREBENJAMIN'),(3,'ALEVIN'),(4,'INFANTIL'),
                                             (5,'CADETE');
      INSERT INTO teams(id,name) VALUES (1,'Club Uno'),(2,'Club Dos'),(3,'Club Alevin'),(4,'Club Infantil'),
                                        (5,'Club Cadete');
      INSERT INTO groups(id,season_id,category_id,code,name,full_name,phase,island,url,current_jornada) VALUES
        (1,1,1,'FF1','Grupo 1','BENJAMIN PRIMERA FASE GC - GRUPO 1','Primera Fase GC','grancanaria','u','Jornada 1'),
        (2,1,3,'AL1','Grupo 1','ALEVIN PRIMERA FASE GC - GRUPO 1','Primera Fase GC','grancanaria','u','Jornada 1'),
        (3,1,4,'INFPG1','Grupo 1','LIGA INFANTIL PREFERENTE DE GRAN CANARIA - GRUPO 1','Preferente GC',
         'grancanaria','u','Jornada 1'),
        (4,2,1,'FF1','Grupo 1','BENJAMIN PRIMERA FASE GC - GRUPO 1','Primera Fase GC','grancanaria','','Jornada 1');
      INSERT INTO venues(name,norm,address,city,surface,kind,code) VALUES
        ('CAMPO','CAMPO','Calle 1','Arucas','Césped','F7',1),
        ('CAMPO INFANTIL','CAMPO INFANTIL','Calle 2','Moya','Tierra','F11',2);
    """)
    rows = [(1, 1, 2, "2026-10-03", "CAMPO"), (2, 1, 3, "2026-10-04", "CAMPO"),
            (3, 4, 1, "2026-10-04", "CAMPO INFANTIL"), (4, 1, 2, "2025-10-04", "CAMPO")]
    if cadete_pasado:
        conn.execute("""INSERT INTO groups(id,season_id,category_id,code,name,full_name,phase,island,url,current_jornada)
                        VALUES (5,2,5,'CADNG1','Grupo 1','LIGA CADETE INSULAR GRAN CANARIA - GRUPO 1','Insular GC',
                                'grancanaria','','Jornada 1')""")
        rows.append((5, 5, 1, "2025-10-05", "CAMPO"))
    for gid, home, away, day, venue in rows:
        for pos, tid in enumerate((home, away), 1):
            conn.execute("""INSERT INTO standings(group_id,team_id,position,points,played,won,drawn,lost,gf,gc,gd)
                            VALUES (?,?,?,?,1,?,0,?,?,?,?)""",
                         (gid, tid, pos, 3 if pos == 1 else 0, int(pos == 1), int(pos == 2),
                          2 if pos == 1 else 1, 1 if pos == 1 else 2, 1 if pos == 1 else -1))
        mid = conn.execute("""INSERT INTO matches(group_id,jornada,date,time,home_team_id,away_team_id,home_score,
                              away_score,venue) VALUES (?,'Jornada 1',?,'10:00',?,?,2,1,?)""",
                           (gid, day, home, away, venue)).lastrowid
        conn.execute("INSERT INTO scorers(group_id,player_name,team_id,goals,games) VALUES (?,'PRUEBA, UNO',?,2,1)",
                     (gid, home))
        for minute, side in ((10, "h"), (20, "h"), (30, "a")):
            conn.execute("INSERT INTO goals(match_id,minute,player_name,side,type) VALUES (?,?,'PRUEBA, UNO',?,'r')",
                         (mid, minute, side))
        conn.execute("""INSERT INTO fp_matches(fp_id,liga_id,match_id,estado,motivo_aplazado)
                        VALUES (?,1,?,'aplazado','lluvia')""", (mid, mid))
    conn.execute("INSERT INTO fp_ligas(liga_id,season_id,group_id,name) VALUES (1,1,NULL,'x')")
    conn.execute("""INSERT INTO team_seasons(team_id,season_id,shirt,venue_name) VALUES
                    (1,1,'Amarilla','CAMPO'),(2,1,'Roja','CAMPO'),(4,1,'Verde','CAMPO INFANTIL')""")
    conn.commit()
    conn.close()
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text('<script src="./data-seasons.js?v=20260101"></script>\n', encoding="utf-8")
    (root / "sw.js").write_text("const CACHE_NAME = 'futbolbase2-v20260101';\n", encoding="utf-8")
    return db, root


@pytest.fixture
def seis(monkeypatch):
    """categorias.EN_WEB con las seis (como lo dejará la tarea 8)."""
    import categorias
    monkeypatch.setattr(categorias, "EN_WEB", SEIS)


def generate(monkeypatch, db, root):
    import generate_js
    monkeypatch.setattr(generate_js, "PROJECT_ROOT", str(root))
    monkeypatch.setattr(generate_js, "get_connection", lambda: sqlite3.connect(str(db)))
    generate_js.main()
    return {p.name: p.read_text(encoding="utf-8") for p in root.glob("data-*.js")}


def test_el_registro():
    import generate_js
    assert generate_js.LAZY == {"ALEVIN": ("alevin", "ALEVIN", "ALEV"), "INFANTIL": ("infantil", "INFANTIL", "INF"),
                                "CADETE": ("cadete", "CADETE", "CAD"), "JUVENIL": ("juvenil", "JUVENIL", "JUV")}
    assert generate_js.EAGER_CATEGORIES == ("BENJAMIN", "PREBENJAMIN")


def test_data_infantil(tmp_path, monkeypatch, seis):
    import generate_js
    db, root = site(tmp_path)
    text = generate_js.generate_lazy_js(sqlite3.connect(str(db)), "INFANTIL")
    assert text.startswith("const INFANTIL=[")
    assert re.findall(r"^const (\w+)=", text, re.M) == [
        "INFANTIL", "INF_STATS", "HISTORY_INF", "GOL_INF", "ESTADOS_INF", "EQUIPOS_INF", "CAMPOS_INF"]
    files = generate(monkeypatch, db, root)
    assert files["data-infantil.js"] == text
    infantil, benjamin = const(text, "INFANTIL"), const(files["data-benjamin.js"], "BENJAMIN")
    assert [g["id"] for g in infantil] == ["INFPG1"] and set(infantil[0]) == set(benjamin[0])
    assert const(text, "INF_STATS") == {"groups": 1, "teams": 2}
    assert list(const(text, "HISTORY_INF")) == ["INFPG1"]
    assert "INFPG1" not in const(files["data-history.js"], "HISTORY")
    gol = const(text, "GOL_INF")
    assert [g["id"] for g in gol] == ["INFPG1"] and gol[0]["g"].startswith("INFANTIL ")
    assert list(const(text, "ESTADOS_INF")) == ["INFPG1"]
    assert sorted(const(text, "EQUIPOS_INF")) == ["Club Infantil", "Club Uno"]
    assert list(const(text, "CAMPOS_INF")) == ["CAMPO INFANTIL"]
    # Cadete y juvenil, sin grupos esta temporada: sus ficheros, vacíos.
    assert const(files["data-cadete.js"], "CADETE") == [] and const(files["data-juvenil.js"], "JUVENIL") == []
    # Alevín, como siempre: sin CAMPOS_ALEV.
    assert re.findall(r"^const (\w+)=", files["data-alevin.js"], re.M) == [
        "ALEVIN", "ALEV_STATS", "HISTORY_ALEV", "GOL_ALEV", "ESTADOS_ALEV", "EQUIPOS_ALEV"]
    assert generate_js.generate_alevin_js(sqlite3.connect(str(db))) == files["data-alevin.js"]


def test_la_carga_inicial_no_gana_nada(tmp_path, monkeypatch, seis):
    files = generate(monkeypatch, *site(tmp_path))
    history = files["data-history.js"]
    equipos = const(history, "EQUIPOS")
    assert "Club Infantil" not in equipos, "solo juega en infantil"
    assert "Club Uno" in equipos, "juega en benjamín (y en infantil)"
    assert "Club Alevin" not in equipos, "solo juega en alevín, como hoy"
    assert sorted(const(history, "CAMPOS")) == ["CAMPO"], "el campo de infantil va en CAMPOS_INF"
    assert sorted(const(history, "HISTORY")) == ["FF1"] and sorted(const(history, "ESTADOS")) == ["FF1"]
    detail = const(files["data-matchdetail.js"], "MATCH_DETAIL")
    assert {e["gr"] for e in entradas(detail)} == {"FF1", "AL1"}, "sin infantil ni cadete"
    inf = const(files["data-matchdetail-infantil.js"], "MATCH_DETAIL_INF")
    assert {e["gr"] for e in entradas(inf)} == {"INFPG1"}
    cad = const(files["data-matchdetail-cadete.js"], "MATCH_DETAIL_CAD")
    assert {(e["s"], e["gr"]) for e in entradas(cad)} == {("2025-2026", "CADNG1")}
    assert const(files["data-matchdetail-juvenil.js"], "MATCH_DETAIL_JUV") == {}
    assert "data-matchdetail-alevin.js" not in files, "alevín sigue en MATCH_DETAIL"
    for name in ("data-history.js", "data-benjamin.js", "data-prebenjamin.js", "data-goleadores.js",
                 "data-seasons.js", "data-season-2025-2026.js"):
        assert "INFPG1" not in files[name] and "CADNG1" not in files[name], name
        assert "Club Infantil" not in files[name] and "Club Cadete" not in files[name], name


def test_temporada_pasada_de_cadete(tmp_path, monkeypatch, seis):
    db, root = site(tmp_path)
    files = generate(monkeypatch, db, root)
    cadete = const(files["data-season-2025-2026-cadete.js"], "SEASON_2025_2026_CADETE")
    past = const(files["data-season-2025-2026.js"], "SEASON_2025_2026")
    assert cadete["name"] == "2025-2026" and [g["id"] for g in cadete["cadete"]] == ["CADNG1"]
    assert set(cadete["cadete"][0]) == set(past["benjamin"][0])
    assert [g["id"] for g in cadete["gol"]["cadete"]] == ["CADNG1"]
    assert "cadete" not in past and "alevin" not in past
    assert not any(n.startswith("data-season-2025-2026-") and n != "data-season-2025-2026-cadete.js" for n in files)
    import precache
    assert precache.temporadas(root) == ["data-season-2025-2026.js"]
    # Sin el grupo de cadete, el fichero no sale, y el de antes se borra.
    (tmp_path / "sin").mkdir()
    db2, root2 = site(tmp_path / "sin", cadete_pasado=False)
    (root2 / "data-season-2025-2026-cadete.js").write_text("const SEASON_2025_2026_CADETE={};\n", encoding="utf-8")
    files2 = generate(monkeypatch, db2, root2)
    assert "data-season-2025-2026-cadete.js" not in files2


def test_archive_lazy_con_alevin_es_archive_alevin(tmp_path, seis):
    import generate_js
    db, _ = site(tmp_path)
    conn = sqlite3.connect(str(db))
    assert generate_js.archive_lazy(conn, 2, "2025-2026", "ALEVIN") is None
    cadete = generate_js.archive_lazy(conn, 2, "2025-2026", "CADETE")
    assert list(cadete)[:2] == ["name", "cadete"]
    assert generate_js.archive_lazy(conn, 2, "2025-2026", "JUVENIL") is None


def test_con_en_web_de_hoy_salen_vacios(tmp_path, monkeypatch):
    import categorias
    assert "INFANTIL" not in categorias.EN_WEB, "esta prueba mira el EN_WEB de hoy"
    import generate_js
    db, root = site(tmp_path)
    files = generate(monkeypatch, db, root)
    assert files["data-infantil.js"] == (
        'const INFANTIL=[];\nconst INF_STATS={"groups":0,"teams":0};\nconst HISTORY_INF={};\nconst GOL_INF=[];\n'
        'const ESTADOS_INF={};\nconst EQUIPOS_INF={};\nconst CAMPOS_INF={};\n')
    assert const(files["data-matchdetail-infantil.js"], "MATCH_DETAIL_INF") == {}
    assert const(files["data-matchdetail-cadete.js"], "MATCH_DETAIL_CAD") == {}
    assert "data-season-2025-2026-cadete.js" not in files
    # Y sin la copia filtrada (la conexión tal cual), lo mismo: la función mira EN_WEB al llamarla.
    conn = sqlite3.connect(str(db))
    assert generate_js.generate_lazy_js(conn, "INFANTIL") == files["data-infantil.js"]
    assert generate_js.archive_lazy(conn, 2, "2025-2026", "CADETE") is None
    assert "INFPG1" not in files["data-history.js"] and "Club Infantil" not in files["data-history.js"]


def test_el_ascenso_es_copa():
    from generate_js import _is_league_group
    assert _is_league_group("CADIA1", "Fase de Ascenso a Interinsular") is False
    assert _is_league_group("JUVILE1", "Eliminatorias de Ascenso a Interinsular Lanzarote") is False
    assert _is_league_group("JUVHA1", "Fase de Ascenso a División de Honor") is False
    assert _is_league_group("CADI1", "Interinsular") is True
    assert _is_league_group("INFPGFO1", "Preferente GC Fase Oro") is True
    assert _is_league_group("CADNGC1", "Copa Insular GC") is False


def _generate_alevin_js_de_antes(conn):
    """generate_alevin_js tal como era antes de la tarea 1 (commit 86c744de), con las funciones de ayuda de
    hoy: lo que tiene que seguir dando generate_lazy_js(conn, "ALEVIN")."""
    import generate_js as G
    js = G.generate_category_js(conn, "ALEVIN", "ALEVIN", "ALEV_STATS")
    history, _ = G.history_map(conn, ("ALEVIN",))
    row = conn.execute("SELECT id FROM seasons WHERE is_current = 1").fetchone()
    teams = ({t for t, cats in G.teams_by_category(conn, row[0]).items() if "ALEVIN" in cats} if row else set())
    js += "const HISTORY_ALEV=" + G.js_val(history) + ";\n"
    js += "const GOL_ALEV=" + G.js_val(G.goleadores_entries(conn, "ALEVIN")) + ";\n"
    js += "const ESTADOS_ALEV=" + G.js_val(G.match_states_map(conn, row[0], ("ALEVIN",)) if row else {}) + ";\n"
    js += "const EQUIPOS_ALEV=" + G.js_val(G.team_info_map(conn, row[0], keep=lambda t: t in teams) if row else {}) + ";\n"
    return js


def test_alevin_igual_byte_a_byte(tmp_path):
    """Sobre una copia de la base real (la de hoy o la de después: la copia que ve la web), data-alevin.js es lo
    que daba el generador de antes, y es el fichero publicado si el árbol lo trae al día con su base."""
    if not DB_PATH.exists():
        pytest.skip("futbolbase.db no está")
    import generate_js
    import vista_web
    copia = tmp_path / "fb.db"
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(str(copia))
    src.backup(dst)
    src.close()
    conn = vista_web.copia_web(dst)
    assert generate_js.generate_lazy_js(conn, "ALEVIN") == _generate_alevin_js_de_antes(conn)
    if conn is not dst:
        conn.close()
    dst.close()


def test_data_seasons_dice_sus_perezosas(tmp_path, monkeypatch, seis):
    """data-seasons.js dice qué perezosas tiene cada temporada (`lazy`, en el orden de LAZY), para que la web pida
    solo esas (la Trayectoria, Explorar de una temporada pasada…), y solo cuando alguna no es alevín: así, con la
    base de hoy, sale igual byte a byte."""
    files = generate(monkeypatch, *site(tmp_path))
    seasons = const(files["data-seasons.js"], "SEASONS")
    assert [(s["name"], s.get("lazy")) for s in seasons] == [("2026-2027", ["alevin", "infantil"]), ("2025-2026", ["cadete"])]
    assert list(seasons[0]) == ["name", "current", "detail", "lazy"], "detrás de lo de siempre"
    # Con el EN_WEB de hoy (o sin grupos de las nuevas), ninguna `lazy`: alevín solo no la escribe.
    import categorias
    monkeypatch.setattr(categorias, "EN_WEB", ("BENJAMIN", "PREBENJAMIN", "ALEVIN"))
    (tmp_path / "hoy").mkdir()
    files = generate(monkeypatch, *site(tmp_path / "hoy"))
    assert all("lazy" not in s for s in const(files["data-seasons.js"], "SEASONS"))
    assert '"lazy"' not in files["data-seasons.js"]


def test_data_seasons_de_la_base_real(tmp_path):
    """Sobre una copia de la base real (la de hoy o la de después: la copia que ve la web): cada temporada lleva
    `lazy` si y solo si tiene grupos de infantil, cadete o juvenil, y entonces con todas sus perezosas."""
    if not DB_PATH.exists():
        pytest.skip("futbolbase.db no está")
    import generate_js
    import vista_web
    copia = tmp_path / "fb.db"
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(str(copia))
    src.backup(dst)
    src.close()
    conn = vista_web.copia_web(dst)
    lean, _ = generate_js.generate_seasons_js(conn, {})
    seasons = json.loads(lean[len("const SEASONS="):-2])
    tiene = {}
    for name, cat in conn.execute("""SELECT DISTINCT s.name, upper(c.name) FROM groups g JOIN seasons s ON s.id=g.season_id
                                     JOIN categories c ON c.id=g.category_id"""):
        if cat in generate_js.LAZY:
            tiene.setdefault(name, set()).add(generate_js.LAZY[cat][0])
    for s in seasons:
        suyas = [v[0] for v in generate_js.LAZY.values() if v[0] in tiene.get(s["name"], set())]
        assert s.get("lazy") == (suyas if set(suyas) - {"alevin"} else None), s["name"]
    if conn is not dst:
        conn.close()
    dst.close()
