"""Las categorías de la base y de la federación (scripts/categorias.py y la migración
scripts/migrate_categories.py), con alevín de Gran Canaria como tercera categoría.

Todo lo que importa de la federación decide la categoría de una competición con
categorias.category_of, una sola para todos los importadores: lo que no es prebenjamín no puede acabar
en benjamín, alevín incluido.
"""
import json
import sqlite3
from pathlib import Path

import pytest

import categorias
from categorias import category_of, parse_categories, DB_NAME

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name, expected", [
    # Benjamín y prebenjamín, con y sin tildes ni guiones.
    ("LIGA BENJAMIN GRAN CANARIA FASE PREVIA", "BENJAMIN"),
    ("LIGA BENJAMÍN F7 GRAN CANARIA FASE LIGA A", "BENJAMIN"),
    ("COPA CABILDO DE LANZAROTE PREFERENTE BENJAMIN FUTBOL-8", "BENJAMIN"),
    ("LIGA BENJAMIN F-7 DE FUERTEVENTURA 1ª FASE", "BENJAMIN"),
    ("LIGA PREBENJAMIN DE GRAN CANARIA", "PREBENJAMIN"),
    ("TORNEO PRE-BENJAMIN CIERRE TEMPORADA", "PREBENJAMIN"),
    ("torneo pre-benjamin cierre temporada fuerteventura-lanzarote", "PREBENJAMIN"),
    ("COPA CAMPEONES PREBENJAMIN", "PREBENJAMIN"),
    # Alevín de Gran Canaria, en todos los formatos del catálogo.
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA", "ALEVIN"),
    ("LIGA ALEVIN F8 GRAN CANARIA SEGUNDA FASE A", "ALEVIN"),
    ("LIGA PREFERENTE ALEVIN F-8 GRAN CANARIA", "ALEVIN"),
    ("copa de campeones categoria alevin fase c", "ALEVIN"),
    ("CLAUSURA ALEVÍN", "ALEVIN"),
    ("COPA CAMPEONES ALEVÍN", "ALEVIN"),
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA (GRUPO 7)", "ALEVIN"),       # cabecera de un acta
    ("Liga Alevin Gran Canaria Grupo 12", "ALEVIN"),                     # liga de la app
    # Fuera: alevín de Lanzarote y Fuerteventura, fútbol sala y lo que no dice la categoría.
    ("LIGA ALEVIN LANZAROTE FASE 1", None),
    ("LIGA ALEVIN FUERTEVENTURA F7 1ª FASE", None),
    ("LIGA PREFERENTE ALEVIN F-8 DE LANZAROTE", None),
    ("COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8", None),
    ("LIGA ALEVIN FUTBOL SALA GRAN CANARIA", None),
    ("LIGA BENJAMÍN FUTBOL SALA GRAN CANARIA 2ªFASE", None),
    ("LIGA PREBENJAMIN FUTBOL SALA GRAN CANARIA (LPFS)", None),
    ("COPA FÚTBOL SALA PREBENJAMÍN", None),
    ("MINI COPA JOSÉ ANTONIO RUIZ CABALLERO", None),
    # Infantil, cadete y juvenil se conocen (parte E): category_of las nombra, pero ni el bot las activa
    # (ACTIVABLES) ni las lee el carril de siempre (CARRILES) ni las ve la web (EN_WEB).
    ("LIGA INFANTIL PREFERENTE DE GRAN CANARIA", "INFANTIL"),
    ("LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", "CADETE"),
    ("LIGA DIVISION DE HONOR JUVENIL GRUPO 6", "JUVENIL"),
    ("FINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTILL", "INFANTIL"),   # así en el catálogo (2024-25)
    ("LIGA PRIMERA INFANTIL DE GRAN CANARIA (GRUPO 3)", "INFANTIL"),     # cabecera de un acta
    ("LIGA INFANTIL FASE 1", "INFANTIL"),                                # «FASE» no es «FS»
    # Su sala, su fútbol femenino y un nombre con dos categorías, fuera.
    ("copa juvenil isla de gran canaria fs", None),
    ("LIGA INFANTIL F.S. LANZAROTE", None),
    ("LIGA INFANTIL FUTBOL SALA GRAN CANARIA", None),
    ("CAMPEONATO DE CANARIAS DE FÚTBOL SALA CADETE", None),
    ("COPA FEMENINA LANZAROTE", None),
    ("LIGA INFANTIL FEMENINA", None),
    ("COPA ALEVIN E INFANTIL", None),
    ("", None),
    (None, None),
])
def test_category_of(name, expected, categorias_de_antes):
    assert category_of(name) == expected


def test_category_of_whole_catalog(categorias_de_antes):
    """Cada competición del catálogo de la federación: nada de sala, nada de alevín fuera de Gran
    Canaria, y ningún benjamín tomado por prebenjamín ni al revés. El congelado en fixtures/: el
    vivo lo cambia discover-fiflp.yml y esta prueba corre en el bot antes de publicar."""
    catalog = json.loads((ROOT / "scripts" / "tests" / "fixtures" / "fiflp_comps_catalog.json").read_text(encoding="utf-8"))
    import re
    from categorias import _fold
    seen = {cat: 0 for cat in DB_NAME.values()}
    distintos = {"INFANTIL": set(), "CADETE": set(), "JUVENIL": set()}
    for season_name, season in catalog.items():
        for comp in season.get("all", []):
            cat = category_of(comp["name"])
            upper = _fold(comp["name"])
            fuera = re.search(r"SALA|\bFS\b|FEMENIN", upper)
            if fuera or "LPFS" in upper:
                assert cat is None, comp
            if cat == "ALEVIN":
                assert "LANZAROTE" not in upper and "FUERTEVENTURA" not in upper, comp
            if cat:
                seen[cat] += 1
            # De 2019-20 a 2026-27, todo lo de las categorías nuevas que se publicaría tiene su categoría.
            if season_name >= "2019-2020" and not fuera:
                for mayor in distintos:
                    if mayor in upper.replace("INFANTILL", "INFANTIL"):
                        assert cat == mayor, comp
                        distintos[mayor].add(re.sub(r"\s+", " ", comp["name"]).strip())
    assert all(seen.values()), seen
    # Los nombres distintos de 2019-20 a 2026-27 (la tabla del convenio, scripts/convenio.py).
    assert {k: len(v) for k, v in distintos.items()} == {"INFANTIL": 35, "CADETE": 47, "JUVENIL": 32}
    # 2026-27: la Fase Previa alevín de Gran Canaria entra; las de Lanzarote y Fuerteventura, no.
    names = {c["id"]: category_of(c["name"]) for c in catalog["2026-2027"]["all"]}
    assert names["54976940"] == "ALEVIN" and names["54976933"] is None and names["54976977"] is None


def test_alevin_de_islas_con_la_marca(monkeypatch, categorias_de_antes):
    """El alevín de Lanzarote y Fuerteventura se reconoce, pero sigue fuera mientras ALEVIN_ISLAS sea False
    (el paso D6 del director): reconocerlo no puede meterlo en el encargo alevín del histórico en marcha."""
    from categorias import excluded, es_alevin_de_islas
    nombre = "LIGA ALEVIN LANZAROTE FASE 1"
    assert category_of(nombre) is None and excluded(nombre) is True and es_alevin_de_islas(nombre) is True
    monkeypatch.setattr(categorias, "ALEVIN_ISLAS", True)
    assert category_of(nombre) == "ALEVIN"
    assert excluded(nombre) is False
    assert es_alevin_de_islas(nombre) is True
    assert category_of("LIGA ALEVIN GRAN CANARIA FASE PREVIA") == "ALEVIN"
    assert es_alevin_de_islas("LIGA ALEVIN GRAN CANARIA FASE PREVIA") is False
    # Su sala, nunca.
    assert category_of("LIGA ALEVIN FUTBOL SALA LANZAROTE") is None


def test_activable(monkeypatch, categorias_de_antes):
    from categorias import activable
    assert activable("LIGA BENJAMIN GRAN CANARIA FASE PREVIA") is True
    assert activable("LIGA ALEVIN GRAN CANARIA FASE PREVIA") is True
    assert activable("LIGA INFANTIL PREFERENTE DE GRAN CANARIA") is False
    monkeypatch.setattr(categorias, "ACTIVABLES", ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL"))
    assert activable("LIGA INFANTIL PREFERENTE DE GRAN CANARIA") is True
    # El alevín de islas, no, aunque ALEVIN sea activable: con ALEVIN_ISLAS a False no tiene categoría.
    assert activable("LIGA ALEVIN LANZAROTE FASE 1") is False
    assert activable("LIGA INFANTIL FUTBOL SALA GRAN CANARIA") is False


def test_carriles():
    from categorias import carril_de, carril_actual, categorias_del_carril
    assert carril_de(("INFANTIL",)) == "mayores"
    assert carril_de(("BENJAMIN", "ALEVIN")) == "principal"
    with pytest.raises(ValueError, match="no se mezclan"):
        carril_de(("BENJAMIN", "CADETE"))
    with pytest.raises(ValueError):
        carril_de(())
    assert carril_actual({}) == "principal"
    assert carril_actual({"FIFLP_CATS": " "}) == "principal"
    assert carril_actual({"FIFLP_CATS": "infantil,cadete,juvenil"}) == "mayores"
    assert categorias_del_carril("mayores") == ("INFANTIL", "CADETE", "JUVENIL")
    assert categorias_del_carril("principal") == ("PREBENJAMIN", "BENJAMIN", "ALEVIN")
    with pytest.raises(KeyError):
        categorias_del_carril("otro")


def test_tandas():
    from categorias import sufijo_tanda, categorias_de_tanda
    assert sufijo_tanda("JUVENIL") == "juv"
    assert sufijo_tanda("BENJAMIN") == ""
    assert sufijo_tanda("PREBENJAMIN") == ""
    assert sufijo_tanda("ALEVIN") == "al"
    assert categorias_de_tanda("cad") == ("CADETE",)
    assert categorias_de_tanda("al") == ("ALEVIN",)
    assert categorias_de_tanda("") == ("BENJAMIN", "PREBENJAMIN")
    with pytest.raises(KeyError):
        categorias_de_tanda("xx")
    with pytest.raises(KeyError):
        sufijo_tanda("SENIOR")


def test_lo_que_se_activa_y_lo_que_se_ve_no_cambia():
    """Ninguna tarea de las partes E1 y E2 cambia ACTIVABLES, ALEVIN_ISLAS ni EN_WEB: lo hace el director, por pasos
    (D3-D6 y E2-D2). Esta es la ÚNICA prueba que comprueba lo que hay hoy en scripts/categorias.py, y la que cambia
    en cada uno de esos pasos, con la misma línea (docs/categorias-mayores.md, «Los pasos del director» y «En la
    web»): las demás fijan el mundo que suponen (conftest.fijar_categorias, categorias_de_antes, fijar_web) y no se
    tocan."""
    assert categorias.ACTIVABLES == ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL")
    assert categorias.EN_WEB == ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
    assert categorias.ALEVIN_ISLAS is False
    assert categorias.MAYORES == ("INFANTIL", "CADETE", "JUVENIL")
    assert categorias.DEFAULT_CATEGORIES == ("BENJAMIN", "PREBENJAMIN")


def test_parse_categories():
    assert parse_categories("benjamin,prebenjamin") == ("BENJAMIN", "PREBENJAMIN")
    assert parse_categories(" alevín ") == ("ALEVIN",)
    assert parse_categories("ALEVIN,benjamin,alevin") == ("ALEVIN", "BENJAMIN")
    assert parse_categories("") == ("BENJAMIN", "PREBENJAMIN")       # por defecto, las de siempre
    assert parse_categories(None) == ("BENJAMIN", "PREBENJAMIN")
    assert parse_categories("benjamin,cadete") == ("BENJAMIN", "CADETE")
    with pytest.raises(ValueError, match="senior") as err:
        parse_categories("benjamin,senior")
    assert all(key in str(err.value) for key in ("benjamin", "prebenjamin", "alevin", "infantil", "cadete", "juvenil"))
    assert DB_NAME == {"benjamin": "BENJAMIN", "prebenjamin": "PREBENJAMIN", "alevin": "ALEVIN",
                       "infantil": "INFANTIL", "cadete": "CADETE", "juvenil": "JUVENIL"}


# ── La tabla categories ──────────────────────────────────────────────────────

def _base(*names):
    from db import SCHEMA
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    for name in names:
        conn.execute("INSERT INTO categories(name) VALUES (?)", (name,))
    conn.execute("INSERT INTO seasons(name,start_year,end_year,is_current) VALUES('2026-2027',2026,2027,1)")
    conn.commit()
    return conn


def test_get_or_create_category_ignores_case_and_creates_in_upper_case():
    from db import get_or_create_category
    conn = _base("BENJAMIN", "PREBENJAMIN", "prebenjamin")
    assert get_or_create_category(conn, "prebenjamin") == 2      # la buena, no la duplicada
    assert get_or_create_category(conn, "Benjamin") == 1
    new = get_or_create_category(conn, "alevin")
    assert conn.execute("SELECT name FROM categories WHERE id=?", (new,)).fetchone() == ("ALEVIN",)
    assert get_or_create_category(conn, "ALEVIN") == new
    assert conn.execute("SELECT count(*) FROM categories").fetchone()[0] == 4


@pytest.mark.parametrize("en_web", ["antes", "seis"])
def test_migration_drops_the_orphan_lower_case_row_and_adds_alevin(fijar_web, en_web):
    # Con el EN_WEB de hoy y con el del paso E2-D2 (las seis): la migración no crea las mayores en ninguno.
    fijar_web(en_web)
    from migrate_categories import migrate
    conn = _base("BENJAMIN", "PREBENJAMIN", "prebenjamin")
    conn.execute("INSERT INTO groups(season_id,category_id,code) VALUES (1,1,'FF1'),(1,2,'PG1')")
    report = migrate(conn)
    assert sorted(r[0] for r in conn.execute("SELECT name FROM categories")) == ["ALEVIN", "BENJAMIN", "PREBENJAMIN"]
    assert report == {"dropped": ["prebenjamin"], "kept": [], "created": ["ALEVIN"]}
    # Las categorías nuevas no se crean aquí, tampoco cuando la web las enseña: las crea activate_season al activar
    # su primer grupo. Si la migración las creara, la primera pasada del bot (o la del paso E2-D2) cambiaría la base
    # sin motivo, y una quitada con quitar_categoria volvería en la pasada siguiente.
    assert not {"INFANTIL", "CADETE", "JUVENIL"} & {r[0] for r in conn.execute("SELECT name FROM categories")}
    # Idempotente: otra pasada no cambia nada.
    before = conn.execute("SELECT id, name FROM categories ORDER BY id").fetchall()
    assert migrate(conn) == {"dropped": [], "kept": [], "created": []}
    assert conn.execute("SELECT id, name FROM categories ORDER BY id").fetchall() == before


def test_migration_never_drops_a_referenced_row():
    from migrate_categories import migrate
    conn = _base("BENJAMIN", "PREBENJAMIN", "prebenjamin")
    conn.execute("INSERT INTO groups(season_id,category_id,code) VALUES (1,3,'X1')")
    report = migrate(conn)
    assert report["kept"] == ["prebenjamin"] and report["dropped"] == []
    assert conn.execute("SELECT count(*) FROM categories WHERE name='prebenjamin'").fetchone()[0] == 1


def test_migration_on_a_copy_of_the_real_base(tmp_path):
    """La base del repositorio tiene la fila 3 ('prebenjamin') sin ningún grupo: se va, y nada más."""
    from migrate_categories import migrate
    db = ROOT / "futbolbase.db"
    if not db.exists():
        pytest.skip("sin futbolbase.db")
    copy = tmp_path / "fb.db"
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(copy)
    src.backup(dst)
    src.close()
    groups = dst.execute("SELECT category_id, count(*) FROM groups GROUP BY category_id").fetchall()
    migrate(dst)
    # Con la base de hoy, las tres de siempre; con la de después de activar infantil, cadete o juvenil, también
    # las suyas (las crea activate_season).
    nombres = {r[1] for r in dst.execute("SELECT id, name FROM categories")}
    assert {"BENJAMIN", "PREBENJAMIN", "ALEVIN"} <= nombres <= set(DB_NAME.values())
    assert dst.execute("SELECT category_id, count(*) FROM groups GROUP BY category_id").fetchall() == groups
    dst.close()


def test_import_history_uses_the_upper_case_rows():
    import import_history
    conn = _base("BENJAMIN", "PREBENJAMIN")
    data = {"season": "2024-2025", "prebenjamin": {"groups": [
        {"name": "Grupo 1", "comp_id": 7, "standings": [{"team": "Moya", "pos": 1}], "jornadas": {}}]}}
    import_history.import_season(conn, data)
    assert [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY id")] == ["BENJAMIN", "PREBENJAMIN"]
    assert conn.execute("SELECT c.name FROM groups g JOIN categories c ON c.id=g.category_id").fetchone() == ("PREBENJAMIN",)


def test_activation_picks_the_upper_case_row_even_after_the_duplicate():
    """insert_groups buscaba con lower(name)=? y fetchone() sin orden: con 'PREBENJAMIN' y
    'prebenjamin' en la base, el grupo iba a la que saliera primero."""
    from activate_season import insert_groups
    conn = _base("BENJAMIN", "prebenjamin", "PREBENJAMIN")       # la duplicada, delante
    group = {"id": "PG1", "cat": "prebenjamin", "name": "Grupo 1", "phase": "Gran Canaria",
             "island": "grancanaria", "url": "https://www.fiflp.com/x?CodCompeticion=1&CodGrupo=2"}
    evidence = [{"group": group, "rounds": {"Jornada 1": [["2026-10-03", "Moya", "Gáldar", None, None, None, None]]},
                 "standings": [[1, "Gáldar", 0, 0, 0, 0, 0, 0, 0, 0], [2, "Moya", 0, 0, 0, 0, 0, 0, 0, 0]],
                 "current": "Jornada 1"}]
    with conn:
        insert_groups(conn, 1, evidence)
    assert conn.execute("SELECT c.name FROM groups g JOIN categories c ON c.id=g.category_id").fetchone() == ("PREBENJAMIN",)


def test_the_bot_runs_the_category_migration_at_start():
    text = (ROOT / "scripts" / "fetch_futbolaspalmas.py").read_text(encoding="utf-8")
    # La migración va en preparar_base (sacada de main para la prueba del histórico), lo primero tras init_db.
    preparar = text[text.index("def preparar_base(conn):"):text.index("def solo_historico(")]
    main = text[text.index("def main():"):]
    assert "migrate_categories(conn)" in preparar
    assert main.index("init_db(conn)") < main.index("preparar_base(conn)")


@pytest.mark.parametrize("name, expected", [
    ("LIGA ALEVIN FUTBOL SALA GRAN CANARIA", True),
    ("LIGA PREBENJAMIN FUTBOL SALA GRAN CANARIA (LPFS)", True),
    ("LIGA ALEVIN LANZAROTE FASE 1", True),
    ("COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8", True),
    ("LIGA BENJAMIN DE LANZAROTE FASE 1", False),
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA", False),
    ("MINI COPA JOSÉ ANTONIO RUIZ CABALLERO", False),      # no dice la categoría: no se sabe
    ("test", False),
    (None, False),
])
def test_excluded(name, expected, categorias_de_antes):
    from categorias import excluded
    assert excluded(name) is expected


def test_conocer_una_categoria_no_le_da_codigo_ni_lote_de_benjamin():
    """Infantil, cadete y juvenil nunca con lo de benjamín («LIGA PRIMERA INFANTIL DE LANZAROTE» saldría
    LZ1, un código de benjamín, y sus actas irían al raw de benjamín y prebenjamín): su código es el de su
    convenio (scripts/convenio.py) y sus actas, su lote."""
    import actas_lotes
    import fiflp_manifest
    import import_fiflp_grupos
    for name, prefijo, lote in (("LIGA PRIMERA INFANTIL DE LANZAROTE", "INF1L", "infantil"),
                                ("LIGA CADETE INSULAR DE LANZAROTE", "CADNL", "cadete"),
                                ("ELIMINATORIAS COPA CADETE PREFERENTE DE LANZAROTE", "CADPLCE", "cadete"),
                                ("LIGA JUVENIL PREFERENTE LANZAROTE", "JUVPL", "juvenil")):
        assert import_fiflp_grupos.meta_by_name(name)[0] == prefijo
        assert fiflp_manifest.comp_meta(name)[0] == prefijo
        assert actas_lotes.lote_of_name(name) == lote
    for cat in categorias.MAYORES:
        assert actas_lotes.lotes_of((cat,)) == (cat.lower(),)
