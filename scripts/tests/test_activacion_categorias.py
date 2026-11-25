"""La activación de las categorías nuevas (parte E1, tarea 8): las tandas de infantil, cadete y juvenil
(fetch_fiflp_islas con ISLAS_SEASON=22inf, 22cad, 22juv), qué tandas baja activar.yml (activar_auto.py --tandas),
la isla «interinsular» del convenio (solo para las categorías nuevas) y la marcha atrás de un paso del director
(scripts/quitar_categoria.py). Nada se activa mientras categorias.ACTIVABLES no lo diga. Sin red: árboles
sintéticos (los de test_activar_auto) y copias de la base real en carpetas de la prueba.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(1, str(Path(__file__).resolve().parent))
import activar_auto as A  # noqa: E402
import categorias  # noqa: E402
import test_activar_auto as T  # noqa: E402
from test_alevin_descargas import CATALOG, islas  # noqa: E402

INF_PG = ("54976908", "LIGA INFANTIL PREFERENTE DE GRAN CANARIA")
JUV_PG = ("54976880", "LIGA JUVENIL PREFERENTE GRAN CANARIA")
CAD_I = ("54976894", "LIGA CADETE INTERINSULAR")
DESEMPATE = ("55133947", "ELIMINATORIA DESEMPATE CADETE INSULAR")
ALEVIN = ("54976940", "LIGA ALEVIN GRAN CANARIA FASE PREVIA")


def activables(monkeypatch, *nuevas):
    monkeypatch.setattr(categorias, "ACTIVABLES", ("BENJAMIN", "PREBENJAMIN", "ALEVIN", *nuevas))


# ── Las tandas ───────────────────────────────────────────────────────────────

def test_tanda_de_cada_categoria(monkeypatch):
    I = islas(monkeypatch, "22inf")
    assert I.F.SEASON == "22" and I.F.OUTPUT_PATH.endswith("scripts/fiflp_islas_22inf_raw.json")
    assert I.F.GROUPS_PATH.endswith("scripts/fiflp_islas_22inf_grupos.json")
    assert I.tanda_categories("22inf") == ("INFANTIL",)
    assert I.tanda_categories("22cad") == ("CADETE",)
    assert I.tanda_categories("22juv") == ("JUVENIL",)
    assert I.tanda_categories("22al") == ("ALEVIN",)
    assert I.tanda_categories("22") == ("BENJAMIN", "PREBENJAMIN")
    assert I.F.COMPETITIONS == I.comps_from_catalog("2026-2027", categories=("INFANTIL",))
    inf = I.comps_from_catalog("2026-2027", catalog=CATALOG, categories=("INFANTIL",))
    assert [c["id"] for c in inf] == ["54976908", "54976916", "55184138", "54976911", "54976929"]
    assert {c["cat"] for c in inf} == {"infantil"}
    # La isla, la del convenio (la que usa la activación para los nombres de los equipos): la interinsular no es
    # de Gran Canaria.
    cad = {c["id"]: c["island"] for c in I.comps_from_catalog("2026-2027", catalog=CATALOG, categories=("CADETE",))}
    assert cad[CAD_I[0]] == "interinsular" and cad["54977104"] == "lanzarote" and cad["54976906"] == "fuerteventura"
    assert cad[DESEMPATE[0]] == "grancanaria"           # sin convenio: la de siempre (no se activará)
    # Con FIFLP_CATS manda ella, como siempre.
    monkeypatch.setenv("FIFLP_CATS", "juvenil")
    assert I.tanda_categories("22inf") == ("JUVENIL",)


@pytest.mark.parametrize("tanda", ["22cad", "22juv"])
def test_las_tandas_nuevas_arrancan(monkeypatch, tanda):
    I = islas(monkeypatch, tanda, ids=CAD_I[0] if tanda == "22cad" else JUV_PG[0])
    assert I.F.OUTPUT_PATH.endswith(f"scripts/fiflp_islas_{tanda}_raw.json")
    assert [c["id"] for c in I.F.COMPETITIONS] == [CAD_I[0] if tanda == "22cad" else JUV_PG[0]]


@pytest.mark.parametrize("tanda", ["22xx", "22infantil", "23inf", "22 inf"])
def test_una_tanda_que_no_existe_para(monkeypatch, tanda):
    with pytest.raises(SystemExit, match="no soportada"):
        islas(monkeypatch, tanda)


# ── Qué tandas baja activar.yml ──────────────────────────────────────────────

def _con_alevin(root):
    """El árbol de test_activar_auto con un grupo alevín de hoy (AL1) además de los de benjamín."""
    conn = sqlite3.connect(root / "futbolbase.db")
    conn.execute("INSERT INTO categories(id, name) VALUES (3, 'ALEVIN')")
    conn.execute("""INSERT INTO groups(season_id, category_id, code, name, full_name, phase, island, url, current_jornada)
                    VALUES (1, 3, 'AL1', 'Grupo 1', 'LIGA ALEVIN GRAN CANARIA FASE PREVIA - GRUPO 1', 'Fase Previa GC',
                            'grancanaria', ?, 'Jornada 1')""", (T.URL.format(comp=ALEVIN[0], grupo="94001"),))
    conn.commit()
    conn.close()
    return root


def test_tandas_pendientes(tmp_path, capsys, monkeypatch):
    root = _con_alevin(T.tree(tmp_path))
    health = {"newCompetitions": [T.new_comp(T.PLZ), T.new_comp(JUV_PG), T.new_comp(INF_PG)],
              "newGroups": [{"competition": T.FF[0], "competitionName": "BENJAMIN PRIMERA FASE GC", "id": "25",
                             "name": "GRUPO 25"}]}
    # Con ACTIVABLES de hoy, las de infantil y juvenil no se bajan (no se activarían).
    assert A.tandas_pendientes(health, "22", root) == ["22"]
    activables(monkeypatch, "INFANTIL", "JUVENIL")
    assert A.tandas_pendientes(health, "22", root) == ["22", "22inf", "22juv"]
    assert A.tandas_pendientes({}, "22", root) == []
    # Un grupo nuevo de una competición que la temporada ya tiene: la tanda de la categoría de sus grupos (el
    # nombre de newGroups es el de la web y puede no decirla).
    alevin = {"newGroups": [{"competition": ALEVIN[0], "competitionName": "Fase Previa GC", "id": "9", "name": "G9"}]}
    assert A.tandas_pendientes(alevin, "22", root) == ["22al"]
    # Lo que no dice su categoría, a la de siempre (como raw_de).
    assert A.tandas_pendientes({"newCompetitions": [{"id": "1", "name": "TORNEO X"}]}, "22", root) == ["22"]
    (root / "data-health.json").write_text(json.dumps({"season": "2026-2027", **health}))
    assert A.main(["--tandas"], root=root) == 0
    assert capsys.readouterr().out == "22 22inf 22juv\n"
    (root / "data-health.json").write_text(json.dumps({"season": "2026-2027"}))
    assert A.main(["--tandas"], root=root) == 0
    assert capsys.readouterr().out == ""


def test_raw_de_busca_en_las_tandas_nuevas(tmp_path):
    root = T.tree(tmp_path)
    scripts = root / "scripts"
    (scripts / "fiflp_islas_22cad_raw.json").write_text(json.dumps([T.entry(CAD_I, 1)]))
    assert A.raw_de(CAD_I[0], CAD_I[1], "22", root).name == "fiflp_islas_22cad_raw.json"
    # Sin estar en ningún raw, el de la tanda de su categoría.
    assert A.raw_de(INF_PG[0], INF_PG[1], "22", root).name == "fiflp_islas_22inf_raw.json"
    assert A.raw_de(JUV_PG[0], JUV_PG[1], "22", root).name == "fiflp_islas_22juv_raw.json"
    assert A.raw_de(ALEVIN[0], ALEVIN[1], "22", root).name == "fiflp_islas_22al_raw.json"
    assert A.raw_de("1", "TORNEO X", "22", root).name == "fiflp_islas_22_raw.json"
    # La que ya está en uno, en ese, diga lo que diga su nombre (un grupo nuevo de newGroups lleva el de la web).
    assert A.raw_de(CAD_I[0], "Interinsular", "22", root).name == "fiflp_islas_22cad_raw.json"


# ── De punta a punta ─────────────────────────────────────────────────────────

def _raw(root, sufijo, entries):
    """El raw de una tanda y su lista de grupos de la federación (la de los del raw)."""
    scripts = root / "scripts"
    (scripts / f"fiflp_islas_22{sufijo}_raw.json").write_text(json.dumps(entries), encoding="utf-8")
    listing = {}
    for g in entries:
        listing.setdefault(g["competition_id"], {})[g["group_id"]] = g["group_name"]
    (scripts / f"fiflp_islas_22{sufijo}_grupos.json").write_text(json.dumps(listing), encoding="utf-8")


def _grupos(root):
    conn = sqlite3.connect(root / "futbolbase.db")
    try:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS sin_pendientes (group_id INTEGER)")
        pending = "fiflp_full_pending" if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='fiflp_full_pending'").fetchone() else "sin_pendientes"
        return conn.execute(
            f"""SELECT g.code, c.name, g.island, g.phase, g.url, g.full_name,
                      g.id IN (SELECT group_id FROM {pending})
               FROM groups g JOIN categories c ON c.id=g.category_id ORDER BY g.id""").fetchall()
    finally:
        conn.close()


def _filas_de(root, codes):
    conn = sqlite3.connect(root / "futbolbase.db")
    try:
        marks = ",".join("?" * len(codes))
        return {t: conn.execute(f"SELECT * FROM {t} WHERE group_id IN (SELECT id FROM groups WHERE code IN ({marks})) "
                                "ORDER BY 1, 2", codes).fetchall() for t in ("standings", "matches")}
    finally:
        conn.close()


def _entry(comp, n, island):
    return {**T.entry(comp, n), "island": island, "cat": categorias.web_key(categorias.category_of(comp[1]))}


def test_activar_infantil_de_punta_a_punta(tmp_path, monkeypatch):
    activables(monkeypatch, "INFANTIL")
    root = _con_alevin(T.tree(tmp_path, health={"newCompetitions": [T.new_comp(INF_PG)]}))
    _raw(root, "inf", [_entry(INF_PG, 1, "grancanaria"), _entry(INF_PG, 2, "grancanaria")])
    before = _grupos(root)
    rows = _filas_de(root, ["FF1", "FF2", "FF3", "AL1"])
    code, logs = T.run(root, generar=lambda root, db: None)
    assert code == 0, logs
    after = _grupos(root)
    assert after[:len(before)] == before and _filas_de(root, ["FF1", "FF2", "FF3", "AL1"]) == rows
    nuevos = after[len(before):]
    assert [(c, cat, isla, fase, pendiente) for c, cat, isla, fase, _, _, pendiente in nuevos] == [
        ("INFPG1", "INFANTIL", "grancanaria", "Preferente GC", 1), ("INFPG2", "INFANTIL", "grancanaria", "Preferente GC", 1)]
    assert nuevos[0][4] == T.URL.format(comp=INF_PG[0], grupo=T.group_id(INF_PG, 1))
    report = T.health(root)
    assert report["activation"]["activated"] == [{"competition": INF_PG[0], "name": INF_PG[1], "codes": ["INFPG1", "INFPG2"]}]
    assert report["activation"]["failed"] == [] and "newCompetitions" not in report


def test_desempate_falla_sin_convenio(tmp_path, monkeypatch):
    """La de Interinsular (isla interinsular, que la activación admite para las categorías nuevas) se activa; la del
    desempate, sin convenio, queda en activation.failed y la activación sale con 1."""
    activables(monkeypatch, "CADETE")
    root = T.tree(tmp_path, health={"newCompetitions": [T.new_comp(DESEMPATE), T.new_comp(CAD_I)]})
    _raw(root, "cad", [_entry(DESEMPATE, 1, "grancanaria"), _entry(CAD_I, 1, "interinsular")])
    code, logs = T.run(root, generar=lambda root, db: None)
    assert code == 1
    assert [(c, cat, isla, fase) for c, cat, isla, fase, *_ in _grupos(root) if cat == "CADETE"] == [
        ("CADI1", "CADETE", "interinsular", "Interinsular")]
    activation = T.health(root)["activation"]
    assert activation["activated"] == [{"competition": CAD_I[0], "name": CAD_I[1], "codes": ["CADI1"]}]
    assert activation["failed"] == [{"competition": DESEMPATE[0], "name": DESEMPATE[1],
                                     "reason": "sin convenio de código: ELIMINATORIA DESEMPATE CADETE INSULAR"}]
    assert T.health(root)["newCompetitions"] == [T.new_comp(DESEMPATE)]


def test_nada_se_activa_sin_activables(tmp_path):
    """Con ACTIVABLES como hoy, una competición de infantil pendiente (en data-health.json a mano, o un grupo nuevo
    que vio el carril de mayores tras volver atrás un paso) no se activa: queda en activation.failed con su motivo
    (y el bot la reintenta una vez al día, sin cambiar nada)."""
    assert "INFANTIL" not in categorias.ACTIVABLES
    root = T.tree(tmp_path, health={"newCompetitions": [T.new_comp(INF_PG)]})
    _raw(root, "inf", [_entry(INF_PG, 1, "grancanaria")])
    before = T.fingerprint(root)
    code, logs = T.run(root, generar=lambda root, db: None)
    assert code == 1
    assert [c for c, *_ in _grupos(root)] == ["FF1", "FF2", "FF3"]
    activation = T.health(root)["activation"]
    assert activation["activated"] == [] and activation["tried"] == [INF_PG[0]]
    assert activation["failed"] == [{"competition": INF_PG[0], "name": INF_PG[1],
                                     "reason": "categoría que el bot aún no activa: INFANTIL"}]
    assert T.fingerprint(root)[0] == before[0]                      # la base, igual


# ── La isla interinsular ─────────────────────────────────────────────────────

def _manifiesto(cat, island):
    return {"season": "2026-2027", "groups": [{"id": "CADI1", "cat": cat, "name": "Grupo 1", "phase": "Interinsular",
                                               "island": island, "url": T.URL.format(comp="1", grupo="2")}]}


@pytest.mark.parametrize("cat", ["infantil", "cadete", "juvenil"])
def test_interinsular_solo_para_las_categorias_nuevas(cat):
    from activate_season import validate_manifest
    validate_manifest(_manifiesto(cat, "interinsular"), "2026-2027", adding=True)


@pytest.mark.parametrize("cat", ["benjamin", "prebenjamin", "alevin"])
def test_interinsular_sigue_siendo_un_error_en_las_de_siempre(cat):
    from activate_season import validate_manifest
    with pytest.raises(ValueError, match="Isla no admitida"):
        validate_manifest(_manifiesto(cat, "interinsular"), "2026-2027", adding=True)
    validate_manifest(_manifiesto(cat, "lanzarote"), "2026-2027", adding=True)
    with pytest.raises(ValueError, match="Isla no admitida"):
        validate_manifest(_manifiesto("cadete", "tenerife"), "2026-2027", adding=True)


def test_un_equipo_de_lanzarote_en_una_interinsular_conserva_su_nombre():
    """raw_team_names: un equipo no cambia de isla, pero una competición interinsular es de varias: su equipo de
    Lanzarote es el de la base (que solo ha jugado en Lanzarote: «UD Tinajo»). Con la isla de Gran Canaria (lo que
    daba el catálogo a una interinsular, sin isla en el nombre) no casaba y salía un equipo nuevo («Tinajo»)."""
    from activate_season import raw_team_names
    conn = sqlite3.connect(":memory:")
    from db import SCHEMA
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO seasons(id,name,start_year,end_year,is_current) VALUES (1,'2026-2027',2026,2027,1)")
    conn.execute("INSERT INTO categories(id,name) VALUES (1,'BENJAMIN')")
    for gid, (code, island, team) in enumerate((("LZ1", "lanzarote", "UD Tinajo"), ("FF1", "grancanaria", "Arucas")), 1):
        conn.execute("INSERT INTO groups(id,season_id,category_id,code,island,url) VALUES (?,1,1,?,?,'')", (gid, code, island))
        tid = conn.execute("INSERT INTO teams(name) VALUES (?)", (team,)).lastrowid
        conn.execute("INSERT INTO standings(group_id,team_id,position,points,played,won,drawn,lost,gf,gc,gd) "
                     "VALUES (?,?,1,0,0,0,0,0,0,0,0)", (gid, tid))
    raw = lambda island: [{"competition_id": CAD_I[0], "competition_name": CAD_I[1], "island": island, "cat": "cadete",
                           "standings": [{"team": 'TINAJO, C.D. "A"'}, {"team": 'ARUCAS, C.F. "A"'}], "jornadas": []}]
    names = raw_team_names(raw("interinsular"), conn, "2026-2027")
    assert names['TINAJO, C.D. "A"'] == "UD Tinajo" and names['ARUCAS, C.F. "A"'] == "Arucas"
    assert raw_team_names(raw("grancanaria"), conn, "2026-2027")['TINAJO, C.D. "A"'] == "Tinajo"   # otro equipo


# ── quitar_categoria.py ──────────────────────────────────────────────────────

def _fin_de_pasada(path):
    """Lo que hace el final de una pasada con la base: las fichas y los enlaces de la liga de escuelas."""
    import enlace_mygol
    import migrate_identidad
    from db import get_connection
    conn = get_connection(path)
    try:
        migrate_identidad.resolver_fichas(conn, log=lambda *a: None)
        enlace_mygol.guardar_enlaces(conn, registro=lambda *a: None)
    finally:
        conn.close()


def _poblar(path, **kw):
    import base_mayores
    from db import get_connection
    conn = get_connection(path)
    try:
        return base_mayores.poblar(conn, log=lambda *a: None, **kw)
    finally:
        conn.close()


def _distinto(a, b):
    """Las tablas (y el esquema) en que dos bases difieren, fila a fila (sin sqlite_sequence, el contador de los
    AUTOINCREMENT: no es un dato)."""
    conn = sqlite3.connect(a)
    conn.execute("ATTACH DATABASE ? AS otra", (str(b),))
    try:
        esquema = lambda db: conn.execute(f"SELECT type, name, sql FROM {db}.sqlite_master ORDER BY type, name").fetchall()
        out = [] if esquema("main") == esquema("otra") else ["esquema"]
        for (t,) in conn.execute("SELECT name FROM main.sqlite_master WHERE type='table' AND name <> 'sqlite_sequence'"):
            n = [conn.execute(f'SELECT count(*) FROM {db}."{t}"').fetchone()[0] for db in ("main", "otra")]
            mas = conn.execute(f'SELECT count(*) FROM (SELECT * FROM main."{t}" EXCEPT SELECT * FROM otra."{t}")').fetchone()[0]
            menos = conn.execute(f'SELECT count(*) FROM (SELECT * FROM otra."{t}" EXCEPT SELECT * FROM main."{t}")').fetchone()[0]
            if n[0] != n[1] or mas or menos:
                out.append(f"{t}: {n[0]} y {n[1]} filas, {mas} y {menos} distintas")
        return out
    finally:
        conn.close()


def _en_curso(path):
    """La temporada en curso de la base (la que puebla base_mayores.poblar): la de hoy no está escrita aquí, para que
    el cambio de temporada (activate_season) no ponga la puerta de pruebas del bot en rojo."""
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT name FROM seasons WHERE is_current=1").fetchone()[0]
    finally:
        conn.close()


def _quitar(path, *argv, capsys=None):
    import quitar_categoria
    code = quitar_categoria.main(["--db", str(path), "--temporada", _en_curso(path), *argv])
    return code, capsys.readouterr().out if capsys else ""


def _por_categoria(path):
    conn = sqlite3.connect(path)
    try:
        return dict(conn.execute(
            """SELECT c.name || '/' || g.island, count(*) FROM groups g JOIN categories c ON c.id=g.category_id
               JOIN seasons s ON s.id=g.season_id WHERE s.is_current=1 GROUP BY 1"""))
    finally:
        conn.close()


_NUEVAS = ("INFANTIL/", "CADETE/", "JUVENIL/", "ALEVIN/lanzarote", "ALEVIN/fuerteventura")


@pytest.fixture(scope="module")
def nunca(bases_reales, tmp_path_factory):
    """La copia de la base real en la que nunca se activaron las categorías nuevas (ni el alevín de islas), tras el
    final de una pasada. Con la base de hoy, la resuelta de conftest.bases_reales tal cual (no tiene nada de ellas:
    quitar_categoria no quitaría nada). Con la base de después (la del bot con las mayores ya leídas:
    prueba_mayores.py), lo que ya hubiera de ellas se quita primero y se pasan las fichas: lo que se compara es lo
    que añade poblar."""
    resuelta = bases_reales["resuelta"]
    if not any(k.startswith(_NUEVAS) for k in _por_categoria(resuelta)):
        return resuelta
    path = tmp_path_factory.mktemp("nunca") / "nunca.db"
    shutil_copy(resuelta, path)
    for argv in (["--categoria", "INFANTIL"], ["--categoria", "CADETE"], ["--categoria", "JUVENIL"],
                 ["--categoria", "ALEVIN", "--isla", "lanzarote"], ["--categoria", "ALEVIN", "--isla", "fuerteventura"]):
        assert _quitar(path, *argv, "--apply")[0] == 0
    _fin_de_pasada(path)
    return path


@pytest.fixture(scope="module")
def mayores_leidas(nunca, bases_reales, tmp_path_factory):
    """La de nunca con infantil, cadete y juvenil activados y leídos (base_mayores.poblar) y el final de una pasada:
    (ruta, lo que devolvió poblar). Con la base de hoy, la de conftest.bases_reales (la misma cuenta, ya hecha)."""
    if nunca == bases_reales["resuelta"]:
        return bases_reales["mayores"], bases_reales["hecho"]
    path = tmp_path_factory.mktemp("mayores") / "mayores.db"
    shutil_copy(nunca, path)
    hecho = _poblar(path)
    _fin_de_pasada(path)
    return path, hecho


def test_quitar_categoria(tmp_path, capsys, nunca, mayores_leidas):
    """Sobre una copia de la base real con las mayores leídas (base_mayores.poblar), el ensayo cuenta lo de infantil
    sin tocar nada; con --apply lo quita y deja benjamín, alevín, cadete y juvenil igual; y quitadas las tres, la
    base es EXACTAMENTE (tabla a tabla, fila a fila: identidades, fichas y enlaces de la liga de escuelas incluidos)
    la de una copia en la que nunca se activaron. Con una categoría de las de siempre, error sin tocar nada."""
    activada = tmp_path / "activada.db"
    shutil_copy(mayores_leidas[0], activada)
    hecho = mayores_leidas[1]
    antes = _por_categoria(activada)
    assert {k.split("/")[0] for k in antes} >= {"INFANTIL", "CADETE", "JUVENIL"}
    assert any(k.endswith("/interinsular") for k in antes)          # base_mayores trae una interinsular
    copia = tmp_path / "ensayo.db"
    shutil_copy(activada, copia)

    code, out = _quitar(copia, "--categoria", "INFANTIL", capsys=capsys)
    assert code == 0 and "ensayo" in out
    inf = [g for g in hecho["grupos"] if g.startswith("INF")]
    assert f"{len(inf)} grupos" in out and all(g in out for g in inf)
    assert _distinto(copia, activada) == []                         # el ensayo no toca nada

    code, out = _quitar(copia, "--categoria", "INFANTIL", "--apply", capsys=capsys)
    assert code == 0
    despues = _por_categoria(copia)
    assert not any(k.startswith("INFANTIL") for k in despues)
    assert {k: v for k, v in antes.items() if not k.startswith("INFANTIL")} == despues

    for cat in ("CADETE", "JUVENIL"):
        assert _quitar(copia, "--categoria", cat, "--apply")[0] == 0
    assert _distinto(copia, nunca) == []

    intacta = tmp_path / "intacta.db"
    shutil_copy(activada, intacta)
    for argv in (["--categoria", "BENJAMIN", "--apply"], ["--categoria", "PREBENJAMIN"],
                 ["--categoria", "ALEVIN", "--apply"], ["--categoria", "ALEVIN", "--isla", "grancanaria", "--apply"],
                 ["--categoria", "SENIOR", "--apply"]):
        with pytest.raises(SystemExit) as exit_:
            _quitar(activada, *argv)
        assert exit_.value.code != 0, argv
    assert _distinto(activada, intacta) == []


def test_quitar_una_mayor_borra_la_huella_del_raw_de_actas_de_su_lote():
    """Quitada infantil de 2026-27, la huella de scripts/fiflp_actas_2026-2027_infantil_raw.json (el raw del carril
    del histórico) sale de raw_imports: si se reactiva, import_changed_raws vuelve a importar esas actas. Las demás
    huellas se quedan (otra temporada, otro lote). El ensayo no toca nada, y el alevín de Lanzarote (--isla) deja
    la del raw de alevín, que es el lote de todo el alevín, Gran Canaria incluido."""
    import quitar_categoria as Q
    from db import SCHEMA
    from migrate_actas_schema import migrate as migrate_actas
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate_actas(conn, log=lambda *a, **k: None)
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS raw_imports (path TEXT PRIMARY KEY, sha1 TEXT NOT NULL, imported_at TEXT NOT NULL);
      INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2025-2026', 2025, 2026, 0),
                                                                            (2, '2026-2027', 2026, 2027, 1);
      INSERT INTO categories(id, name) VALUES (1, 'BENJAMIN'), (2, 'ALEVIN'), (3, 'INFANTIL');
      INSERT INTO groups(id, season_id, category_id, code, name, island) VALUES
        (1, 2, 1, 'FF1', 'Grupo 1', 'grancanaria'), (2, 2, 2, 'AL1', 'Grupo 1', 'grancanaria'),
        (3, 2, 2, 'ALUL1', 'Grupo 1', 'lanzarote'), (4, 2, 3, 'INFPG1', 'Grupo 1', 'grancanaria');
    """)
    huellas = ["fiflp_actas_2026-2027_raw.json", "fiflp_actas_2026-2027_alevin_raw.json",
               "fiflp_actas_2026-2027_infantil_raw.json", "fiflp_actas_2025-2026_infantil_raw.json",
               "fiflp_actas_2026-2027_cadete_raw.json", "grupos:2025-2026"]
    conn.executemany("INSERT INTO raw_imports VALUES (?, 'x', '2026-11-25')", [(h,) for h in huellas])
    conn.commit()
    quedan = lambda: sorted(p for (p,) in conn.execute("SELECT path FROM raw_imports"))  # noqa: E731
    assert Q.quitar(conn, "2026-2027", "INFANTIL")["filas"]["raw_imports"] == 1          # el ensayo la cuenta
    assert quedan() == sorted(huellas)                                                   # y no toca nada
    assert Q.quitar(conn, "2026-2027", "INFANTIL", apply=True)["filas"]["raw_imports"] == 1
    assert quedan() == sorted(h for h in huellas if h != "fiflp_actas_2026-2027_infantil_raw.json")
    hecho = Q.quitar(conn, "2026-2027", "ALEVIN", "lanzarote", apply=True)
    assert hecho["grupos"] == ["ALUL1"] and "raw_imports" not in hecho["filas"]
    assert "fiflp_actas_2026-2027_alevin_raw.json" in quedan()


def test_quitar_el_alevin_de_lanzarote(tmp_path, nunca, bases_reales):
    """El paso D6 hacia atrás: --categoria ALEVIN --isla lanzarote quita solo el alevín de Lanzarote (el de Gran
    Canaria se queda) y, tras la pasada siguiente (sus fichas, que sí miraban esos grupos: alevín es de la web), la
    base es la de nunca."""
    activada = tmp_path / "activada.db"
    if nunca == bases_reales["resuelta"]:               # la base de hoy: la de bases_reales (la misma cuenta, ya hecha)
        shutil_copy(bases_reales["islas"], activada)
        hecho = bases_reales["hecho_islas"]
    else:
        shutil_copy(nunca, activada)
        hecho = _poblar(activada, categorias=(), islas=True)
        _fin_de_pasada(activada)
    assert hecho["grupos"] and all(g.startswith("ALUL") for g in hecho["grupos"])
    antes = _por_categoria(activada)
    assert "ALEVIN/lanzarote" in antes
    assert _quitar(activada, "--categoria", "ALEVIN", "--isla", "lanzarote", "--apply")[0] == 0
    quedan = _por_categoria(activada)
    # (Recién empezada una temporada puede no haber aún alevín de Gran Canaria: entonces, tampoco después.)
    assert "ALEVIN/lanzarote" not in quedan and quedan.get("ALEVIN/grancanaria") == antes.get("ALEVIN/grancanaria")
    _fin_de_pasada(activada)
    assert _distinto(activada, nunca) == []


def shutil_copy(a, b):
    import shutil
    shutil.copyfile(a, b)
