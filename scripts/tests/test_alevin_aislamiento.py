"""Alevín no se mezcla con benjamín (riesgo nº 1 de traer una tercera categoría), ni infantil,
cadete, juvenil o el alevín de Lanzarote con benjamín ni entre ellas.

Los clubes son los mismos en todas las categorías ('Arucas' juega en alevín, en benjamín, en
prebenjamín y en juvenil, con el mismo nombre en la base), así que todo lo que casa un grupo o un
partido por sus equipos podía llevar datos de otra categoría a un grupo de benjamín: un acta al
partido del mismo cruce y el mismo fin de semana, los goleadores o el detalle de un grupo
alevín al grupo de benjamín de los mismos clubes, una liga alevín de la app al grupo FF
con los mismos equipos. Cada prueba reproduce uno de esos choques con una base sintética, y las
que montan un grupo de otra categoría al lado del de benjamín lo hacen con cada una (el fixture
`caso`: alevín, infantil, cadete, juvenil y, con categorias.ALEVIN_ISLAS a True, el alevín de
Lanzarote frente al benjamín de Lanzarote).
"""
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from db import SCHEMA  # noqa: E402
from migrate_actas_schema import migrate  # noqa: E402

# Suponen el mundo de antes de los pasos D3-D6 del director (infantil, cadete y juvenil sin activar, el alevín de
# Lanzarote y Fuerteventura fuera): lo fijan ellas (conftest.categorias_de_antes) para que cada paso solo cambie
# categorias.py y test_categorias.test_lo_que_se_activa_y_lo_que_se_ve_no_cambia. Las que miran otro mundo lo ponen.
pytestmark = pytest.mark.usefixtures("categorias_de_antes")

TEAMS = ["Arucas", "Moya", "Gáldar", "Tablero", "Guía", "Firgas"]
FED = ["ARUCAS, C.F.", "MOYA, U.D.", "GALDAR, C.F.", 'TABLERO, C.D. "A"', "GUIA, U.D.", "FIRGAS, C.D."]
ALEVIN_COMP = "LIGA ALEVIN GRAN CANARIA FASE PREVIA"
BENJAMIN_COMP = "LIGA BENJAMIN GRAN CANARIA FASE PREVIA"
CATEGORIES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")


@dataclass(frozen=True)
class Benjamin:
    """El grupo de benjamín de los mismos clubes, de la isla del caso."""
    competicion: str
    codigo: str
    fase: str
    isla: str
    app: str            # el nombre de su liga en la app de futbolaspalmas


BEN_GC = Benjamin(BENJAMIN_COMP, "FF1", "Primera Fase GC", "grancanaria", "Liga Benjamín Gran Canaria Grupo 1")
BEN_LZ = Benjamin("LIGA BENJAMIN DE LANZAROTE FASE 1", "LZ1", "Lanzarote Fase 1", "lanzarote",
                  "Liga Benjamín Lanzarote Grupo 1")


@dataclass(frozen=True)
class Caso:
    """Una categoría que no es benjamín, con los mismos clubes que el grupo de benjamín de su isla. Lo
    que protegía alevín de benjamín tiene que proteger igual a infantil, cadete, juvenil y el alevín de
    Lanzarote (cuando se publique: categorias.ALEVIN_ISLAS) de benjamín y entre ellas."""
    id: str
    categoria: str
    competicion: str
    codigo: str          # su grupo en la base
    prefijo: str         # el de su código por su nombre (meta_by_name / el convenio)
    fase: str
    copa: tuple          # (una copa de la categoría, el código de su grupo, su fase)
    islas: bool = False  # con categorias.ALEVIN_ISLAS a True

    @property
    def benjamin(self):
        return BEN_LZ if self.islas else BEN_GC

    @property
    def app(self):
        return f"{self.competicion.title()} Grupo 3"


ALEVIN = Caso("alevin", "ALEVIN", ALEVIN_COMP, "AL3", "AL", "Primera Fase GC",
              ("COPA DE CAMPEONES ALEVIN GRAN CANARIA", "ALCC1", "Copa de Campeones"))
INFANTIL = Caso("infantil", "INFANTIL", "LIGA PRIMERA INFANTIL DE GRAN CANARIA", "INF1G3", "INF1G", "Primera GC",
                ("COPA CAMPEONES INFANTIL", "INFUGCK1", "Copa de Campeones"))
CADETE = Caso("cadete", "CADETE", "LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", "CADNG3", "CADNG", "Insular GC Fase 1",
              ("COPA FIFLP CADETE PRIMERA", "CAD1GC1", "Copa Primera GC"))
JUVENIL = Caso("juvenil", "JUVENIL", "LIGA SEGUNDA JUVENIL GRAN CANARIA", "JUV2G3", "JUV2G", "Segunda GC",
               ("COPA FIFLP JUVENIL TERRITORIAL", "JUVTC1", "Copa Territorial"))
ALEVIN_LZ = Caso("alevin-lanzarote", "ALEVIN", "LIGA ALEVIN LANZAROTE FASE 1", "ALUL1", "ALUL", "Lanzarote Fase 1",
                 ("COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8", "AL1LC1", "Copa Cabildo Primera Lanzarote"),
                 islas=True)
CASOS = (ALEVIN, INFANTIL, CADETE, JUVENIL, ALEVIN_LZ)


def _alevin_de_islas(monkeypatch):
    """categorias.ALEVIN_ISLAS a True en las dos copias del módulo (algunos importadores lo importan
    como scripts.categorias): lo que pondrá el director en su paso D6."""
    import categorias
    modules = [categorias]
    try:
        import scripts.categorias as other
        modules.append(other)
    except ImportError:
        pass
    for module in modules:
        monkeypatch.setattr(module, "ALEVIN_ISLAS", True)


@pytest.fixture(params=CASOS, ids=[c.id for c in CASOS])
def caso(request, monkeypatch):
    if request.param.islas:
        _alevin_de_islas(monkeypatch)
    return request.param


def _grupo(conn, gid, categoria, code, phase, island, start, url=None):
    """Un grupo con los seis clubes en su clasificación y, en la jornada 1 (3/10), Arucas–Moya 3-1 y
    Gáldar–Tablero 0-2."""
    cat = CATEGORIES.index(categoria) + 1
    conn.execute("""INSERT INTO groups(id,season_id,category_id,code,name,full_name,phase,island,url)
                    VALUES (?,1,?,?,'Grupo 1',?,?,?,?)""", (gid, cat, code, f"{code} GRUPO 1", phase, island, url))
    for pos, tid in enumerate(range(1, 7), 1):
        conn.execute("""INSERT INTO standings(group_id,team_id,position,points,played,won,drawn,lost,gf,gc,gd)
                        VALUES (?,?,?,0,0,0,0,0,0,0,0)""", (gid, tid, pos))
    conn.execute("""INSERT INTO matches(group_id,jornada,date,home_team_id,away_team_id,home_score,away_score)
                    VALUES (?,'Jornada 1',?,1,2,3,1)""", (gid, f"{start}-10-03"))
    conn.execute("""INSERT INTO matches(group_id,jornada,date,home_team_id,away_team_id,home_score,away_score)
                    VALUES (?,'Jornada 1',?,3,4,0,2)""", (gid, f"{start}-10-03"))


def base(benjamin=BEN_GC, otros=(), season="2026-2027", current=1):
    """Una temporada con el grupo de benjamín de `benjamin` (FF1, los seis clubes) y, detrás (ids 2, 3…),
    un grupo de cada caso de `otros` con los mismos clubes."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate(conn)
    start = int(season[:4])
    conn.execute("INSERT INTO seasons(id,name,start_year,end_year,is_current) VALUES (1,?,?,?,?)",
                 (season, start, start + 1, current))
    for i, name in enumerate(CATEGORIES, 1):
        conn.execute("INSERT INTO categories(id,name) VALUES (?,?)", (i, name))
    for i, t in enumerate(TEAMS, 1):
        conn.execute("INSERT INTO teams(id,name) VALUES (?,?)", (i, t))
    _grupo(conn, 1, "BENJAMIN", benjamin.codigo, benjamin.fase, benjamin.isla, start)
    for gid, otro in enumerate(otros, 2):
        _grupo(conn, gid, otro.categoria, otro.codigo, otro.fase, otro.benjamin.isla, start)
    conn.commit()
    return conn


def match_of(conn, code):
    return conn.execute("""SELECT m.id FROM matches m JOIN groups g ON g.id=m.group_id
                           WHERE g.code=? AND m.home_team_id=1""", (code,)).fetchone()[0]




# ── Actas: reconcile_acta ────────────────────────────────────────────────────

def header(comp, season="2026/2027"):
    return {"season": season, "jornada": "1", "date": "03-10-2026", "competition": f"{comp} (GRUPO 1)",
            "home_score": 3, "away_score": 1, "home_team": "ARUCAS, C.F.", "away_team": "MOYA, U.D."}


def test_an_alevin_acta_never_lands_on_the_benjamin_match_of_the_same_clubs(caso):
    from acta_reconciler import reconcile_acta
    conn = base(caso.benjamin)
    # Mismo cruce, misma fecha y mismo marcador: antes casaba con el partido de FF1.
    assert reconcile_acta(conn, header(caso.competicion)) is None
    assert reconcile_acta(conn, header(caso.benjamin.competicion)) == match_of(conn, caso.benjamin.codigo)


def test_with_both_groups_each_acta_goes_to_its_own_category(caso):
    from acta_reconciler import reconcile_acta
    conn = base(caso.benjamin, [caso])
    assert reconcile_acta(conn, header(caso.competicion)) == match_of(conn, caso.codigo)
    assert reconcile_acta(conn, header(caso.benjamin.competicion)) == match_of(conn, caso.benjamin.codigo)


def test_un_acta_de_otra_categoria_nueva_tampoco_casa():
    """Infantil y cadete con los mismos clubes el mismo día: cada acta, al partido de su categoría (y
    ninguna al de benjamín)."""
    from acta_reconciler import reconcile_acta
    conn = base(BEN_GC, [INFANTIL, CADETE])
    assert reconcile_acta(conn, header(CADETE.competicion)) == match_of(conn, CADETE.codigo)
    assert reconcile_acta(conn, header(INFANTIL.competicion)) == match_of(conn, INFANTIL.codigo)
    # Sin el grupo de su categoría, nunca el de la otra.
    conn = base(BEN_GC, [INFANTIL])
    assert reconcile_acta(conn, header(CADETE.competicion)) is None
    conn = base(BEN_GC, [CADETE])
    assert reconcile_acta(conn, header(INFANTIL.competicion)) is None


def test_an_acta_of_a_competition_that_is_not_published_is_not_reconciled():
    from acta_reconciler import reconcile_acta
    conn = base(BEN_GC, [ALEVIN])
    assert reconcile_acta(conn, header("LIGA ALEVIN LANZAROTE FASE 1")) is None
    assert reconcile_acta(conn, header("LIGA ALEVIN FUTBOL SALA GRAN CANARIA")) is None
    assert reconcile_acta(conn, header("COPA JUVENIL ISLA DE GRAN CANARIA FS")) is None
    # Sin competición en la cabecera (actas muy antiguas): como siempre, sin filtro.
    h = header(BENJAMIN_COMP)
    del h["competition"]
    assert reconcile_acta(conn, h) is None          # dos candidatos idénticos: ninguno
    conn2 = base()
    assert reconcile_acta(conn2, h) == match_of(conn2, "FF1")


def test_import_raw_keeps_alevin_actas_out_of_benjamin(tmp_path, monkeypatch, caso):
    """El camino del bot (import_changed_raws → import_raw): el acta de la otra categoría se queda sin casar."""
    import import_fiflp_actas as A
    monkeypatch.setattr(A, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))
    conn = base(caso.benjamin)
    acta = {"header": header(caso.competicion), "lineups": {"home": [], "away": []}, "events": [], "staff": {},
            "consistent": True, "cod_acta": 777, "enumeration": {"comp_id": "54976940", "grupo": "1", "jornada": "1"}}
    raw = tmp_path / "fiflp_actas_2026-2027_raw.json"
    raw.write_text(json.dumps({"777": acta}), encoding="utf-8")
    A.import_raw(conn, str(raw))
    assert conn.execute("SELECT count(*) FROM matches WHERE cod_acta=777").fetchone()[0] == 0


# ── App de futbolaspalmas: match_liga ────────────────────────────────────────

def liga(name):
    return {"name": name, "tabla": [{"nombre": t} for t in TEAMS]}


def test_an_alevin_league_of_the_app_does_not_match_the_ff_group_with_the_same_clubs(caso):
    from import_fp_app import match_liga
    conn = base(caso.benjamin)
    assert match_liga(conn, 1, liga(caso.app)) is None
    assert match_liga(conn, 1, liga(caso.benjamin.app)) == 1


def test_with_both_groups_each_league_of_the_app_goes_to_its_category(caso):
    from import_fp_app import match_liga
    conn = base(caso.benjamin, [caso])
    # Los dos grupos tienen los mismos equipos: cada liga de la app va a su categoría y la de benjamín no se
    # queda sin grupo.
    assert match_liga(conn, 1, liga(caso.benjamin.app)) == 1
    assert match_liga(conn, 1, liga(caso.app)) == 2
    if caso is ALEVIN:
        assert match_liga(conn, 1, liga("Liga Alevin Gran Canaria Grupo 5")) == 2
        assert match_liga(conn, 1, liga("Alevin eliminatorias Grupo 1")) == 2
        assert match_liga(conn, 1, liga("Liga Alevin Fuerteventura Grupo 1")) is None


# ── Goleadores y clasificaciones de la federación: match_group ──────────────

def entry(comp_name, comp="54976940", grupo="1", standings=True):
    return {"comp": comp, "grupo": grupo, "comp_name": comp_name, "grupo_name": "GRUPO 1", "ok": True,
            "standings": [{"pos": i + 1, "team": t, "pts": 0, "j": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0}
                          for i, t in enumerate(FED)] if standings else [],
            "scorers": [["GARCIA, LUIS", "ARUCAS, C.F.", 1, 2, 0], ["", "MOYA, U.D.", 1, 1, 0],
                        ["DIAZ, ANA", "GALDAR, C.F.", 1, 1, 0]]}


def test_scorers_of_an_alevin_group_never_match_the_benjamin_group_by_teams(caso):
    import import_fiflp_goleadores as G
    conn = base(caso.benjamin)
    assert G.match_group(conn, 1, {}, entry(caso.competicion)) is None
    assert G.match_group(conn, 1, {}, entry(caso.benjamin.competicion, comp="54976988")) == 1
    # Sin clasificación (una copa: solo los equipos de sus goleadores), tampoco.
    assert G.match_group(conn, 1, {}, entry(caso.copa[0], standings=False)) is None


def test_with_both_groups_scorers_go_to_their_category(caso):
    import import_fiflp_goleadores as G
    conn = base(caso.benjamin, [caso])
    assert G.match_group(conn, 1, {}, entry(caso.competicion)) == 2
    assert G.match_group(conn, 1, {}, entry(caso.benjamin.competicion, comp="54976988")) == 1


def test_by_actas_and_by_owner_never_cross_categories(caso):
    """Aunque un acta de otra categoría hubiera caído antes en FF1 (o fiflp_groups apuntara mal), el grupo
    de otra categoría no se acepta."""
    import import_fiflp_goleadores as G
    conn = base(caso.benjamin)
    for i, mid in enumerate([r[0] for r in conn.execute("SELECT id FROM matches WHERE group_id=1")], 1):
        conn.execute("UPDATE matches SET cod_acta=? WHERE id=?", (900 + i, mid))
    conn.execute("INSERT INTO matches(group_id,jornada,date,home_team_id,away_team_id,home_score,away_score,cod_acta)"
                 " VALUES (1,'Jornada 2','2026-10-10',5,6,1,1,903)")
    index = {str(c): {"comp_id": "54976940", "grupo": "1"} for c in (901, 902, 903)}
    assert G.by_actas(conn, index, "54976940", "1") == 1                  # el voto, tal cual
    assert G.match_group(conn, 1, index, entry(caso.competicion)) is None  # pero no es de su categoría
    conn.execute("CREATE TABLE IF NOT EXISTS fiflp_groups (group_id INTEGER PRIMARY KEY, season_id INTEGER NOT NULL,"
                 " comp TEXT NOT NULL, grupo TEXT NOT NULL)")
    conn.execute("INSERT INTO fiflp_groups VALUES (1, 1, '54976940', '1')")
    assert G.match_group(conn, 1, {}, entry(caso.competicion)) is None


def test_import_of_an_alevin_scorers_raw_leaves_benjamin_alone(tmp_path, caso):
    import import_fiflp_goleadores as G
    conn = base(caso.benjamin, season="2025-2026", current=0)
    conn.execute("INSERT INTO scorers(group_id,player_name,team_id,goals,games) VALUES (1,'PEREZ, JUAN',1,7,3)")
    conn.commit()
    path = tmp_path / "fiflp_goleadores_2025-2026_raw.json"
    path.write_text(json.dumps({"54422881:1": entry(caso.competicion, comp="54422881")}), encoding="utf-8")
    report = G.import_raw(conn, str(path))
    assert report["written"] == 0 and report["unmatched"] == 1
    assert conn.execute("SELECT player_name, goals FROM scorers").fetchall() == [("PEREZ, JUAN", 7)]


# ── Detalle de la federación ────────────────────────────────────────────────

def test_detail_of_an_alevin_group_is_not_written_into_benjamin(tmp_path, caso):
    import import_fiflp_detalle as D
    conn = base(caso.benjamin, season="2025-2026", current=0)
    D.migrate(conn)
    det = {"comp": "54422881", "grupo": "1", "comp_name": caso.competicion, "grupo_name": "GRUPO 1", "ok": True,
           "clasificacion": [{"pos": i + 1, "team": t, "pts": 0, "j": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0,
                              "codequipo": 100 + i, "home": [0, 0, 0, 0], "away": [0, 0, 0, 0]}
                             for i, t in enumerate(FED)],
           "directorio": [{"team": t, "codequipo": 100 + i, "shirt": "Roja"} for i, t in enumerate(FED)]}
    path = tmp_path / "fiflp_detalle_2025-2026_raw.json"
    path.write_text(json.dumps({"54422881:1": det}), encoding="utf-8")
    report = D.import_raw(conn, str(path))
    assert report["groups"] == 0
    assert conn.execute("SELECT count(*) FROM standings_detail").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM team_seasons").fetchone()[0] == 0


def test_el_calendario_de_infantil_en_una_temporada_pasada_y_nada_en_benjamin(tmp_path):
    """Infantil no tiene portal (como alevín): en una temporada pasada, su calendario es el de la
    federación. El de un grupo de «LIGA PRIMERA INFANTIL DE GRAN CANARIA» de 2025-26 se importa en su
    grupo y nada va al grupo de benjamín con los mismos clubes."""
    import import_fiflp_detalle as D
    conn = base(season="2025-2026", current=0)
    url = "https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21&CodCompeticion=999&CodGrupo=1"
    conn.execute("""INSERT INTO groups(id,season_id,category_id,code,name,full_name,phase,island,url)
                    VALUES (3,1,4,'INF1G1','Grupo 1','INFANTIL PRIMERA GC - GRUPO 1','Primera GC','grancanaria',?)""", (url,))
    for pos, tid in enumerate(range(1, 7), 1):
        conn.execute("""INSERT INTO standings(group_id,team_id,position,points,played,won,drawn,lost,gf,gc,gd)
                        VALUES (3,?,?,0,0,0,0,0,0,0,0)""", (tid, pos))
    conn.commit()
    D.migrate(conn)
    before = conn.execute("SELECT * FROM matches WHERE group_id=1 ORDER BY id").fetchall()
    det = {"comp": "999", "grupo": "1", "comp_name": "LIGA PRIMERA INFANTIL DE GRAN CANARIA", "grupo_name": "GRUPO 1",
           "ok": True, "clasificacion": [],
           "jornadas": {"Jornada 1": [{"home": "ARUCAS, C.F.", "away": "MOYA, U.D.", "hs": 5, "as": 0,
                                       "date": "2025-10-04", "time": "10:00", "venue": "CAMPO"}]}}
    path = tmp_path / "fiflp_detalle_2025-2026_raw.json"
    path.write_text(json.dumps({"999:1": det}), encoding="utf-8")
    # Sin la lista de temporadas con calendario (CALENDAR_SEASONS, que hoy lleva 2025-26): por la categoría.
    report = D.import_raw(conn, str(path), log=lambda *a: None, calendar_seasons=())
    assert report["groups"] == 1 and report["matches"] == 1
    assert conn.execute("SELECT home_score, away_score FROM matches WHERE group_id=3").fetchall() == [(5, 0)]
    assert conn.execute("SELECT * FROM matches WHERE group_id=1 ORDER BY id").fetchall() == before


def test_a_cup_of_an_archived_season_is_created_in_its_category_with_its_code(caso):
    """create_cup_group (finales y copas de las archivadas, desde su calendario): la copa alevín
    va a ALEVIN con su código ALCC1, no a BENJAMIN con BC1; la de cada categoría nueva, a la suya con
    el código de su convenio."""
    import import_fiflp_detalle as D
    conn = base(caso.benjamin, season="2018-2019", current=0)
    D.migrate(conn)
    name, code, phase = caso.copa
    det = {"comp": "398", "grupo": "1", "comp_name": name, "grupo_name": "GRUPO 1",
           "ok": True, "jornadas": {"Final": [{"home": "ARUCAS, C.F.", "away": "MOYA, U.D.", "hs": 2, "as": 1,
                                                "date": "2019-06-01", "time": "", "venue": ""}]}}
    assert D.create_cup_group(conn, 1, "2018-2019", det, log=lambda *a: None) == 1
    assert conn.execute("""SELECT g.code, c.name, g.phase FROM groups g JOIN categories c ON c.id=g.category_id
                           WHERE g.id<>1""").fetchall() == [(code, caso.categoria, phase)]


# ── Grupos de la federación que faltan: import_fiflp_grupos ─────────────────

@pytest.mark.parametrize("name, meta", [
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA", ("AL", "Primera Fase GC", "grancanaria")),
    ("LIGA PRIMERA ALEVIN F-8 GRAN CANARIA", ("AL", "Primera Fase GC", "grancanaria")),
    ("LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA", ("ALP", "Preferente GC", "grancanaria")),
    ("LIGA ALEVIN F8 GRAN CANARIA SEGUNDA FASE A", ("ALA", "Segunda Fase A", "grancanaria")),
    ("LIGA ALEVIN F7 GRAN CANARIA FASE LIGA C", ("ALC", "Segunda Fase C", "grancanaria")),
    ("LIGA ALEVIN GRAN CANARIA SEGUNDA FASE F", ("ALF", "Segunda Fase F", "grancanaria")),
    # El nombre corto de la Segunda Fase (2026-27), como en fiflp_manifest.comp_meta.
    ("LIGA ALEVIN GRAN CANARIA FASE A", ("ALA", "Segunda Fase A", "grancanaria")),
    ("LIGA ALEVIN GRAN CANARIA LIGA B", ("ALB", "Segunda Fase B", "grancanaria")),
    ("LIGA ALEVIN GRAN CANARIA FASE AB", None),
    ("COPA ALEVIN GRAN CANARIA FASE A", None),
    ("COPA DE CAMPEONES ALEVIN GRAN CANARIA", ("ALCC", "Copa de Campeones", "grancanaria")),
    ("COPA CAMPEONES ALEVÍN", ("ALCC", "Copa de Campeones", "grancanaria")),
    ("copa de campeones categoria alevin fase d", ("ALCCD", "Copa de Campeones D", "grancanaria")),
    ("CLAUSURA ALEVÍN", ("ALCL", "Clausura Alevín", "grancanaria")),
    ("ALEVIN ELIMINATORIAS", ("ALEL", "Eliminatorias", "grancanaria")),
    ("LIGA BENJAMIN GRAN CANARIA ELIMINATORIAS", ("EL", "Eliminatorias", "grancanaria")),
    ("ELIMINATORIAS PREBENJAMIN", ("PEL", "Eliminatorias", "grancanaria")),
    # Fuera: alevín de Lanzarote y Fuerteventura, sala, y finales alevín (sin convenio: ALF es la fase F).
    ("LIGA PREFERENTE ALEVIN F-8 DE LANZAROTE", None),
    ("LIGA ALEVIN F-8 FUERTEVENTURA", None),
    ("LIGA ALEVIN FUTBOL SALA GRAN CANARIA", None),
    ("FINAL LIGA PRIMERA ALEVIN GRAN CANARIA", None),
    # Eliminatorias de otras islas: EL/PEL son las de Gran Canaria (docs/alevin.md §2); sin convenio.
    ("ELIMINATORIAS LIGA BENJAMIN DE LANZAROTE", None),
    ("ELIMINATORIAS PREBENJAMIN FUERTEVENTURA", None),
    # Las categorías nuevas, con su convenio (scripts/convenio.py); nunca uno de benjamín ni de alevín.
    ("LIGA PRIMERA INFANTIL DE LANZAROTE", ("INF1L", "Primera Lanzarote", "lanzarote")),
    ("LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", ("CADNG", "Insular GC Fase 1", "grancanaria")),
    ("LIGA SEGUNDA JUVENIL GRAN CANARIA", ("JUV2G", "Segunda GC", "grancanaria")),
    ("COPA JUVENIL ISLA DE GRAN CANARIA FS", None),
    ("ELIMINATORIA DESEMPATE CADETE INSULAR", None),
])
def test_meta_by_name_alevin_codes_never_collide(name, meta):
    import import_fiflp_grupos as GR
    assert GR.meta_by_name(name) == meta


def test_the_benjamin_conventions_did_not_move():
    import import_fiflp_grupos as GR
    assert GR.meta_by_name("LIGA PRIMERA BENJAMIN F-8 GRAN CANARIA") == ("GC", "Primera Fase GC", "grancanaria")
    assert GR.meta_by_name("LIGA PREFERENTE BENJAMIN F-8 GRAN CANARIA") == ("BPGC", "Preferente GC", "grancanaria")
    assert GR.meta_by_name("COPA DE CAMPEONES BENJAMIN GRAN CANARIA") == ("BC", "Copa de Campeones", "grancanaria")
    assert GR.meta_by_name("LIGA PREBENJAMIN DE GRAN CANARIA") == ("PGC", "Primera Fase GC", "grancanaria")


def test_comp_meta_reads_the_name_of_alevin_competitions_also_outside_the_archive(caso):
    import import_fiflp_grupos as GR
    conn = base(caso.benjamin, season="2025-2026", current=0)
    isla = "lanzarote" if caso.islas else "grancanaria"
    assert GR.comp_meta(conn, "54422881", [], caso.competicion) == (caso.prefijo, caso.fase, isla)
    assert GR.comp_meta(conn, "54422885", [], BENJAMIN_COMP) is None       # benjamín 2021-26: nunca por nombre


def test_import_season_creates_the_alevin_group_in_its_category_beside_benjamin(tmp_path, caso):
    """Una temporada no archivada (2025-26) con un grupo de otra categoría en el raw de goleadores: se
    crea en su categoría, con su código, sin tocar el de benjamín."""
    import import_fiflp_grupos as GR
    conn = base(caso.benjamin, season="2025-2026", current=0)
    (tmp_path / "fiflp_goleadores_2025-2026_raw.json").write_text(
        json.dumps({"54422881:1": entry(caso.competicion, comp="54422881", grupo="1")}), encoding="utf-8")
    ff1 = conn.execute("SELECT count(*) FROM standings WHERE group_id=1").fetchone()[0]
    report = GR.import_season(conn, str(tmp_path), "2025-2026", log=lambda *a: None)
    assert report["created"] == 1, report
    assert conn.execute("""SELECT g.code, c.name, g.phase FROM groups g JOIN categories c ON c.id=g.category_id
                           WHERE g.id<>1""").fetchall() == [(f"{caso.prefijo}1", caso.categoria, caso.fase)]
    assert conn.execute("SELECT count(*) FROM standings WHERE group_id=1").fetchone()[0] == ff1


# ── Las actas huérfanas (import_fiflp_actas._purge_orphan_cod_actas) ─────────

def _acta(comp, season, cod, home="ARUCAS, C.F.", away="MOYA, U.D.", score=(3, 1)):
    h = {**header(comp, season.replace("-", "/")), "date": f"03-10-{season[:4]}", "home_team": home,
         "away_team": away, "home_score": score[0], "away_score": score[1]}
    return {"header": h, "lineups": {"home": [], "away": []}, "events": [], "staff": {}, "consistent": True,
            "cod_acta": cod, "enumeration": {"comp_id": "54976940", "grupo": "1", "jornada": "1"}}


@pytest.mark.parametrize("season, current", [("2026-2027", 1), ("2025-2026", 0)])
def test_an_alevin_raw_never_clears_the_actas_of_benjamin(tmp_path, monkeypatch, season, current, caso):
    """import_raw quitaba el cod_acta de todo partido de la temporada cuya acta no estuviera en el raw
    (el raw era «la cosecha completa»). Un raw de actas de alevín (actas-federacion.yml con
    categorias=alevin) habría borrado las de benjamín; y en la temporada en curso el bot importa actas
    cada pasada, así que el raw nunca está completo."""
    import import_fiflp_actas as A
    monkeypatch.setattr(A, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))
    conn = base(caso.benjamin, season=season, current=current)
    ff1 = match_of(conn, caso.benjamin.codigo)
    conn.execute("UPDATE matches SET cod_acta=500 WHERE id=?", (ff1,))
    conn.commit()
    raw = tmp_path / f"fiflp_actas_{season}_raw.json"
    raw.write_text(json.dumps({"777": _acta(caso.competicion, season, 777)}), encoding="utf-8")
    A.import_raw(conn, str(raw))
    assert conn.execute("SELECT cod_acta FROM matches WHERE id=?", (ff1,)).fetchone() == (500,)


def test_cada_raw_purga_solo_lo_suyo(tmp_path, monkeypatch):
    """El raw de actas de cadete de una temporada cerrada (su lote, fiflp_actas_<S>_cadete_raw.json) no
    deja sin acta a ningún partido de benjamín, alevín ni infantil; los de cadete cuya acta ya no está,
    sí, como siempre; y las que leyó el bot (cod_acta = fiflp_acta) sobreviven a un raw parcial de cadete."""
    import import_fiflp_actas as A
    monkeypatch.setattr(A, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))
    season = "2025-2026"
    raw = tmp_path / f"fiflp_actas_{season}_cadete_raw.json"
    raw.write_text(json.dumps({"778": _acta(CADETE.competicion, season, 778, "GALDAR, C.F.", 'TABLERO, C.D. "A"',
                                            (0, 2))}), encoding="utf-8")
    codes = ("FF1", ALEVIN.codigo, INFANTIL.codigo, CADETE.codigo)
    for bot in (False, True):
        conn = base(BEN_GC, [ALEVIN, INFANTIL, CADETE], season=season, current=0)
        mids = {code: match_of(conn, code) for code in codes}
        for i, code in enumerate(codes):
            conn.execute("UPDATE matches SET cod_acta=?, fiflp_acta=? WHERE id=?",
                         (500 + i, 500 + i if bot else None, mids[code]))
        conn.commit()
        A.import_raw(conn, str(raw))
        held = {code: conn.execute("SELECT cod_acta FROM matches WHERE id=?", (mid,)).fetchone()[0]
                for code, mid in mids.items()}
        assert held == {"FF1": 500, ALEVIN.codigo: 501, INFANTIL.codigo: 502,
                        CADETE.codigo: 503 if bot else None}, bot
        # Y el acta del raw, en el partido de su grupo de cadete.
        assert conn.execute("""SELECT g.code FROM matches m JOIN groups g ON g.id=m.group_id
                               WHERE m.cod_acta=778""").fetchall() == [(CADETE.codigo,)]


def test_a_complete_raw_of_a_closed_season_still_clears_its_orphans(tmp_path, monkeypatch):
    """Lo de siempre: en una temporada cerrada, un acta de benjamín que ya no está en el raw (de
    benjamín) se quita de su partido."""
    import import_fiflp_actas as A
    monkeypatch.setattr(A, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))
    conn = base(season="2025-2026", current=0)
    ff1 = match_of(conn, "FF1")
    conn.execute("UPDATE matches SET cod_acta=500 WHERE id=?", (ff1,))
    conn.commit()
    h = {**header(BENJAMIN_COMP, "2025/2026"), "date": "03-10-2025", "home_team": "GALDAR, C.F.",
         "away_team": 'TABLERO, C.D. "A"', "home_score": 0, "away_score": 2}
    acta = {"header": h, "lineups": {"home": [], "away": []}, "events": [], "staff": {}, "consistent": True,
            "cod_acta": 778, "enumeration": {"comp_id": "54422885", "grupo": "1", "jornada": "1"}}
    raw = tmp_path / "fiflp_actas_2025-2026_raw.json"
    raw.write_text(json.dumps({"778": acta}), encoding="utf-8")
    A.import_raw(conn, str(raw))
    assert conn.execute("SELECT cod_acta FROM matches WHERE id=?", (ff1,)).fetchone() == (None,)


def test_the_actas_read_by_the_bot_survive_a_partial_raw_once_the_season_is_archived(tmp_path, monkeypatch):
    """Desde 2026-27 el bot lee cada acta por el código que da la federación en la jornada (update_fiflp:
    cod_acta = fiflp_acta), sin raw. Cuando la temporada se archive (verano de 2027), un raw parcial de
    actas-federacion.yml (temporada=22, una tanda o una sola competición) que se reimporte (otro raw, o
    IMPORT_VERSION nueva) ya no es «la cosecha completa»: no deja sin acta a esos partidos."""
    import import_fiflp_actas as A
    monkeypatch.setattr(A, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))
    conn = base(season="2026-2027", current=0)               # 2026-27 ya archivada
    ff1 = match_of(conn, "FF1")
    conn.execute("UPDATE matches SET cod_acta=500, fiflp_acta=500 WHERE id=?", (ff1,))
    conn.execute("INSERT INTO match_staff_all(match_id, team_id, role, name, ord) VALUES (?, 1, 'Entrenador', 'X', 0)",
                 (ff1,))
    conn.commit()
    h = {**header(BENJAMIN_COMP), "home_team": "GALDAR, C.F.", "away_team": 'TABLERO, C.D. "A"',
         "home_score": 0, "away_score": 2}
    acta = {"header": h, "lineups": {"home": [], "away": []}, "events": [], "staff": {}, "consistent": True,
            "cod_acta": 778, "enumeration": {"comp_id": "54977017", "grupo": "1", "jornada": "1"}}
    raw = tmp_path / "fiflp_actas_2026-2027_raw.json"
    raw.write_text(json.dumps({"778": acta}), encoding="utf-8")
    report = A.import_raw(conn, str(raw))
    assert report["orphans_cleared"] == 0
    assert conn.execute("SELECT cod_acta FROM matches WHERE id=?", (ff1,)).fetchone() == (500,)
    assert conn.execute("SELECT count(*) FROM match_staff_all WHERE match_id=?", (ff1,)).fetchone() == (1,)
    # Un acta que vino de un raw (sin fiflp_acta, o con otro código) sigue purgándose como siempre.
    conn.execute("UPDATE matches SET fiflp_acta=501 WHERE id=?", (ff1,))
    conn.commit()
    assert A._purge_orphan_cod_actas(conn, {"778": acta}) == 1


def test_groups_of_the_current_season_only_come_from_the_activation(tmp_path, caso):
    """Con SEASON_NAME['22'] un raw de goleadores de 2026-27 es posible: sus grupos de otra categoría no
    se crean por aquí (sin URL de la federación, el bot no los pondría al día); se activan con
    activate_season."""
    import import_fiflp_grupos as GR
    conn = base(caso.benjamin)                               # 2026-2027, en curso
    (tmp_path / "fiflp_goleadores_2026-2027_raw.json").write_text(
        json.dumps({"54976940:1": entry(caso.competicion)}), encoding="utf-8")
    report = GR.import_season(conn, str(tmp_path), "2026-2027", log=lambda *a: None)
    assert report["created"] == 0
    assert conn.execute("SELECT count(*) FROM groups").fetchone()[0] == 1


def test_crests_of_an_alevin_group_never_go_to_the_benjamin_group(tmp_path, monkeypatch, caso):
    """escudos_federacion: los escudos de un grupo del raw de goleadores se casan con su grupo por
    match_group, de su categoría; sin grupo de esa categoría en la base, no da candidatos."""
    import escudos_federacion as E
    monkeypatch.setattr(E, "SHIELDS_PATH", tmp_path / "data-shields.js")
    (tmp_path / "data-shields.js").write_text("const SHIELDS={};\n", encoding="utf-8")
    conn = base(caso.benjamin, season="2025-2026", current=0)
    crests = {t: f"https://laspalmas.filesnovanet.es/pnfg/pimg/Clubes/{i}.png" for i, t in enumerate(FED)}
    raw = {"54422881:1": {**entry(caso.competicion, comp="54422881"), "crests": crests}}
    (tmp_path / "fiflp_goleadores_2025-2026_raw.json").write_text(json.dumps(raw), encoding="utf-8")
    assert E.candidates(conn, folder=tmp_path) == {}
    # El mismo grupo, de benjamín: sus escudos sí van a los equipos de FF1.
    raw = {"54422885:1": {**entry(caso.benjamin.competicion, comp="54422885"), "crests": crests}}
    (tmp_path / "fiflp_goleadores_2025-2026_raw.json").write_text(json.dumps(raw), encoding="utf-8")
    assert sorted(E.candidates(conn, folder=tmp_path)) == sorted(TEAMS)


# ── Los carriles del bot: update_fiflp.fiflp_groups ─────────────────────────

def test_los_carriles_no_se_cruzan():
    """Una base con un grupo de cada una de las seis categorías (con URL de la federación): el carril
    principal nunca trae uno de infantil, cadete o juvenil, y el de las mayores solo esos."""
    from categorias import CARRILES
    from update_fiflp import fiflp_groups
    conn = base(BEN_GC, [ALEVIN, INFANTIL, CADETE, JUVENIL])
    _grupo(conn, 9, "PREBENJAMIN", "PGC1", "Primera Fase GC", "grancanaria", 2026)
    conn.execute("UPDATE groups SET url='https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?CodGrupo=' || id")
    principal = {code for _, code, _ in fiflp_groups(conn, 1, CARRILES["principal"])}
    mayores = {code for _, code, _ in fiflp_groups(conn, 1, CARRILES["mayores"])}
    assert principal == {"FF1", "PGC1", ALEVIN.codigo}
    assert mayores == {INFANTIL.codigo, CADETE.codigo, JUVENIL.codigo}
    assert {code for _, code, _ in fiflp_groups(conn, 1)} == principal | mayores
