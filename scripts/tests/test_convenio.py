"""El convenio de códigos de infantil, cadete, juvenil y el alevín de Lanzarote y Fuerteventura
(scripts/convenio.py), comprobado contra el catálogo ENTERO de la federación, no contra ejemplos.

Dos grupos con el mismo código en una temporada pisarían sus data-lineups, su HISTORY y su
comprobación: por eso la prueba recorre todas las competiciones de 2016-17 a 2026-27 del catálogo
congelado (fixtures/: el vivo lo cambia discover-fiflp.yml y estas pruebas corren en el bot antes
de publicar) y exige que ningún prefijo se repita en la temporada ni choque con los de benjamín,
prebenjamín o alevín de Gran Canaria, y que la tabla del plan
(docs/superpowers/plans/2026-11-25-ampliacion-e1-categorias-datos.md, «El convenio de códigos»)
salga tal cual (fixtures/convenio_mayores.json).
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import categorias  # noqa: E402
import fiflp_manifest as M  # noqa: E402
import import_fiflp_grupos as G  # noqa: E402
from convenio import SinConvenio, aplica, convenio, eliminatoria_de_liga  # noqa: E402

FIXTURES = ROOT / "scripts" / "tests" / "fixtures"
CATALOG = json.loads((ROOT / "scripts" / "tests" / "fixtures" / "fiflp_comps_catalog.json").read_text(encoding="utf-8"))
TABLA = json.loads((FIXTURES / "convenio_mayores.json").read_text(encoding="utf-8"))
DESEMPATE = "ELIMINATORIA DESEMPATE CADETE INSULAR"
# Los prefijos que hoy leen otra cosa por startswith (la isla: import_fiflp_grupos.ISLAND_OF_PREFIX; las
# copas de la web: isCupGroup en src/state.js) o por el final (model.js, …KO).
FAMILIAS = ("LZ", "FV", "CLZ", "CFV", "PLZ", "PFV", "PCC", "BC", "MCP", "MCB")


def _simple(nombre):
    return " ".join(nombre.split())


def test_la_tabla_entera():
    assert len(TABLA) == 138
    for nombre, fila in TABLA.items():
        assert tuple(convenio(nombre)) == tuple(fila), nombre


def _de_hoy(nombre):
    """El prefijo de hoy de una competición de benjamín, prebenjamín o alevín de Gran Canaria (el del
    manifiesto o el de las temporadas pasadas), o None si ninguno le da código."""
    out = set()
    try:
        out.add(M.comp_meta(nombre)[0])
    except ValueError:
        pass
    meta = G.meta_by_name(nombre)
    if meta:
        out.add(meta[0])
    return out


def test_el_catalogo_entero_sin_choques():
    sin = []
    for temporada in sorted(CATALOG):
        if not "2016-2017" <= temporada <= "2026-2027":
            continue
        prefijos, ligas, de_hoy = {}, [], set()
        for comp in CATALOG[temporada].get("all", []):
            nombre = comp["name"]
            plegado = categorias._fold(nombre)
            # Lo de siempre (con los códigos de siempre): el alevín de Lanzarote y Fuerteventura no, aunque desde
            # el paso D6 (ALEVIN_ISLAS) sea alevín: sus códigos son los del convenio, los de abajo.
            if (categorias.category_of(nombre) in ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
                    and not categorias.es_alevin_de_islas(nombre)):
                de_hoy |= _de_hoy(nombre)
            if not aplica(nombre) or re.search(r"SALA|\bFS\b|FEMENIN", plegado):
                continue
            try:
                c = convenio(nombre)
            except SinConvenio as motivo:
                sin.append((temporada, _simple(nombre), str(motivo)))
                continue
            assert c.prefijo not in prefijos, (temporada, nombre, prefijos.get(c.prefijo))
            prefijos[c.prefijo] = nombre
            if c.tipo == "liga":
                ligas.append(c)
            p = c.prefijo
            assert re.fullmatch(r"(?:INF|CAD|JUV)[A-Z0-9]{1,14}|AL[A-Z0-9]{2,15}", p), p
            assert len(p) <= 17 and p[-1].isalpha(), p
            assert not p.startswith(FAMILIAS) and not p.endswith("KO"), p
            if p.startswith("AL"):
                assert not re.fullmatch(r"AL(?:[A-Z]|P|CC[A-Z]?|CL|EL)", p), p
        choques = set(prefijos) & de_hoy
        assert not choques, (temporada, choques)
        for liga in ligas:
            eliminatoria = eliminatoria_de_liga(liga).prefijo
            assert eliminatoria not in prefijos and eliminatoria not in de_hoy, (temporada, eliminatoria)
    assert sin == [("2026-2027", DESEMPATE, "tipo de competición sin convenio")]


def test_cuantos_cubre():
    """De 2019-20 a 2026-27, 139 nombres distintos (con los espacios simplificados) de las categorías
    nuevas que se publicarían: 138 con convenio (la tabla) y el desempate sin él."""
    nombres = set()
    for temporada, datos in CATALOG.items():
        if temporada < "2019-2020":
            continue
        for comp in datos.get("all", []):
            plegado = categorias._fold(comp["name"])
            if aplica(comp["name"]) and not re.search(r"SALA|\bFS\b|FEMENIN", plegado):
                nombres.add(_simple(comp["name"]))
    assert len(nombres) == 139
    assert nombres - set(TABLA) == {DESEMPATE}


@pytest.mark.parametrize("nombre, motivo", [
    (DESEMPATE, "tipo de competición sin convenio"),
    ("LIGA INFANTIL TERCERA FASE GRAN CANARIA", "fase desconocida"),
    ("LIGA CADETE PREFERENTE INTERINSULAR", "dos niveles en el nombre"),
    ("COPA JUVENIL FUTBOL SALA", "no se publica"),
    ("LIGA INFANTIL FEMENINA", "no se publica"),
    ("FINAL FASE DE ASCENSO A JUVENIL INTERINSULAR", "final de algo que no es liga ni copa"),
    ("LIGA ALEVIN GRAN CANARIA FASE PREVIA", "sin categoría"),
    ("TORNEO CADETE GRAN CANARIA", "tipo de competición sin convenio"),
])
def test_sin_convenio_y_sus_motivos(nombre, motivo):
    with pytest.raises(SinConvenio) as error:
        convenio(nombre)
    assert str(error.value) == motivo


def test_aplica():
    assert aplica("LIGA ALEVIN GRAN CANARIA FASE PREVIA") is False
    assert aplica("LIGA BENJAMIN DE LANZAROTE FASE 1") is False
    assert aplica("LIGA ALEVIN LANZAROTE FASE 1") is True          # valga lo que valga ALEVIN_ISLAS
    assert aplica("COPA JUVENIL FUTBOL SALA") is True               # aplica, aunque no se publica
    assert aplica("FINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTILL") is True


def test_eliminatoria_de_liga():
    assert eliminatoria_de_liga(convenio("LIGA INFANTIL PREFERENTE DE GRAN CANARIA")) == \
        ("INFPGEL", "Eliminatorias Preferente GC", "grancanaria", "eliminatorias")


def _grupo(comp_id, comp_name, group_id, group_name):
    return {"competition_id": comp_id, "competition_name": comp_name, "group_id": group_id,
            "group_name": group_name, "standings": [{"team": "A", "pos": 1}],
            "jornadas": [{"num": "1", "date": "03-10-2026", "matches": []}]}


def test_manifiesto_de_las_categorias_nuevas():
    infantil, juvenil = "LIGA INFANTIL PREFERENTE DE GRAN CANARIA", "LIGA JUVENIL INTERINSULAR"
    raw = [_grupo("54976908", infantil, "101", "GRUPO 2"), _grupo("54976908", infantil, "100", "GRUPO 1"),
           _grupo("54976878", juvenil, "200", "GRUPO 1"),
           _grupo("54976908", infantil, "102", "ELIMINATORIA DE PRIMEROS")]
    groups = {g["id"]: g for g in M.build(raw, "2026-2027", "22")}
    assert set(groups) == {"INFPG1", "INFPG2", "JUVI1", "INFPGEL1"}
    assert {k: (g["cat"], g["phase"], g["island"]) for k, g in groups.items()} == {
        "INFPG1": ("infantil", "Preferente GC", "grancanaria"),
        "INFPG2": ("infantil", "Preferente GC", "grancanaria"),
        "JUVI1": ("juvenil", "Interinsular", "interinsular"),
        "INFPGEL1": ("infantil", "Eliminatorias Preferente GC", "grancanaria")}
    assert groups["INFPG1"]["fullName"] == "INFANTIL PREFERENTE GC - GRUPO 1"
    assert "CodCompeticion=54976908&CodGrupo=100" in groups["INFPG1"]["url"]
    # La eliminatoria, numerada tras las que la temporada ya tiene con su prefijo.
    assert [g["id"] for g in M.build(raw, "2026-2027", "22", taken={"INFPGEL1"}) if "EL" in g["id"]] == ["INFPGEL2"]
    with pytest.raises(ValueError, match="código repetido: INFPG1"):
        M.build(raw, "2026-2027", "22", taken={"INFPG1"})
    with pytest.raises(ValueError, match=f"competición sin convenio de código: {DESEMPATE}"):
        M.build([_grupo("55133947", DESEMPATE, "300", "GRUPO 1")], "2026-2027", "22")


def test_el_alevin_de_gran_canaria_no_se_mueve():
    assert M.comp_meta("LIGA ALEVIN GRAN CANARIA FASE PREVIA") == ("AL", "Primera Fase GC")
    assert M.comp_meta("LIGA ALEVIN GRAN CANARIA FASE F") == ("ALF", "Segunda Fase F")
    assert M.comp_meta("COPA CAMPEONES ALEVÍN") == ("ALCC", "Copa de Campeones")
    # Todos los de benjamín, prebenjamín y alevín de Gran Canaria del congelado, lo de antes de esta tarea
    # (fixtures/convenio_anterior.json: comp_meta y la isla que build sacaba del prefijo; null, sin código).
    antes = json.loads((FIXTURES / "convenio_anterior.json").read_text(encoding="utf-8"))
    assert antes
    for nombre, esperado in antes.items():
        if esperado is None:
            with pytest.raises(ValueError):
                M.meta(nombre)
        else:
            assert list(M.meta(nombre)) == esperado, nombre


def test_meta_by_name_de_las_nuevas(monkeypatch, categorias_de_antes):
    assert G.meta_by_name("LIGA PRIMERA INFANTIL DE LANZAROTE") == ("INF1L", "Primera Lanzarote", "lanzarote")
    assert G.meta_by_name(DESEMPATE) is None
    alevin = "LIGA PRIMERA ALEVIN F-8 DE LANZAROTE"
    assert G.meta_by_name(alevin) is None                          # ALEVIN_ISLAS a False: fuera
    monkeypatch.setattr(categorias, "ALEVIN_ISLAS", True)
    assert G.meta_by_name(alevin) == ("AL1L", "Primera Lanzarote", "lanzarote")


def test_comp_meta_de_temporadas_pasadas_lee_el_nombre_de_las_nuevas(categorias_de_antes):
    """import_fiflp_grupos.comp_meta (los grupos de una temporada pasada que se crean del raw de
    goleadores) lee el nombre de las categorías nuevas en cualquier temporada, como el de alevín: no
    tienen hermanos de futbolaspalmas ni EXTRA_META."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    assert G.comp_meta(conn, "1", [], "LIGA JUVENIL PREFERENTE DE GRAN CANARIA") == \
        ("JUVPG", "Preferente GC", "grancanaria")
    assert G.comp_meta(conn, "1", [], DESEMPATE) is None
    assert G.comp_meta(conn, "1", [], "LIGA ALEVIN LANZAROTE FASE 1") is None     # sin la marca, fuera


def test_ningun_prefijo_es_el_de_un_grupo_de_la_base():
    """Ningún prefijo del convenio (los de todo el catálogo) es el de un grupo de benjamín, prebenjamín o
    alevín de Gran Canaria que ya está en la base. Sobre una lectura de la base real: vale con la de hoy y
    con la de después de activar las categorías nuevas (sus grupos, con sus propios códigos, no cuentan)."""
    import sqlite3
    db = ROOT / "futbolbase.db"
    if not db.exists():
        pytest.skip("sin futbolbase.db")
    prefijos = set()
    for datos in CATALOG.values():
        for comp in datos.get("all", []):
            if aplica(comp["name"]):
                try:
                    c = convenio(comp["name"])
                except SinConvenio:
                    continue
                prefijos |= {c.prefijo, eliminatoria_de_liga(c).prefijo}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        codigos = conn.execute("""SELECT g.code FROM groups g JOIN categories c ON c.id = g.category_id
                                  WHERE upper(c.name) IN ('BENJAMIN', 'PREBENJAMIN')
                                     OR (upper(c.name) = 'ALEVIN' AND g.island = 'grancanaria')""").fetchall()
    finally:
        conn.close()
    assert codigos
    assert not {code for (code,) in codigos if re.sub(r"\d+$", "", code) in prefijos}
