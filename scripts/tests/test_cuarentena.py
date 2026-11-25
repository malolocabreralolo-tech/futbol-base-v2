"""La cuarentena del histórico (cuarentena.py): lo que bajan las tandas va a scripts/historico/, que el bot no
mira, y solo pasa a scripts/ (promover) lo que se ha probado en verde. Sin red: la federación de mentira."""
import builtins
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import cuarentena as C  # noqa: E402
from federacion_falsa import FederacionFalsa, Pagina, Reloj  # noqa: E402
# Las webs de mentira y el `main` de las actas de las pruebas de cada descargador (fixtures incluidos).
from tests.test_fiflp_goleadores import S, correr as correr_goleadores, sitio_goleadores  # noqa: E402,F401
from tests.test_fiflp_detalle import correr as correr_detalle, fed_detalle, sitio_detalle  # noqa: E402,F401
from tests.test_fiflp_actas_enumeration import sitio_actas, tanda, todas  # noqa: E402,F401


# ── Los nombres y los trabajos ────────────────────────────────────────────────

def test_trabajo_de_cada_fichero():
    assert C.trabajo_de("fiflp_goleadores_2025-2026_raw.json") == "goleadores:2025-2026"
    assert C.trabajo_de("fiflp_detalle_2019-2020_raw.json") == "detalle:2019-2020"
    assert C.trabajo_de("fiflp_campos_raw.json") == "campos"
    assert C.trabajo_de("fiflp_actas_2025-2026_alevin_status.json") == "actas:2025-2026:alevin"
    assert C.trabajo_de("fiflp_actas_2025-2026_index.json") == "actas:2025-2026:siempre"
    assert C.trabajo_de("fiflp_actas_2019-2020_raw.json") == "actas:2019-2020:siempre"
    for nombre in ("fiflp_goleadores_2025-2026_grupos.json", "plan.json", "estado.json",
                   "actas_bot_2026-2027_alevin.jsonl", "fiflp_actas_unmatched.json",
                   "fiflp_actas_2025-2026_senior_raw.json", "fiflp_detalle_2025_raw.json"):
        assert C.trabajo_de(nombre) is None, nombre
    # Cada categoría nueva, su lote de actas (actas_lotes.LOTES).
    assert C.trabajo_de("fiflp_actas_2025-2026_cadete_raw.json") == "actas:2025-2026:cadete"
    assert C.trabajo_de("fiflp_actas_2024-2025_juvenil_index.json") == "actas:2024-2025:juvenil"


def test_ficheros_de_cada_trabajo():
    assert C.ficheros("actas:2025-2026:alevin") == ["fiflp_actas_2025-2026_alevin_raw.json",
                                                   "fiflp_actas_2025-2026_alevin_index.json",
                                                   "fiflp_actas_2025-2026_alevin_status.json"]
    assert C.ficheros("actas:2025-2026:siempre") == ["fiflp_actas_2025-2026_raw.json",
                                                    "fiflp_actas_2025-2026_index.json",
                                                    "fiflp_actas_2025-2026_status.json"]
    assert C.ficheros("goleadores:2025-2026") == C.ficheros("escudos:2025-2026") == [
        "fiflp_goleadores_2025-2026_raw.json"]
    assert C.ficheros("calendario:2019-2020") == ["fiflp_detalle_2019-2020_raw.json"]
    assert C.ficheros("campos") == ["fiflp_campos_raw.json"]
    assert C.ficheros("actas:2025-2026:infantil") == ["fiflp_actas_2025-2026_infantil_raw.json",
                                                     "fiflp_actas_2025-2026_infantil_index.json",
                                                     "fiflp_actas_2025-2026_infantil_status.json"]
    for malo in ("actas:2025-2026:senior", "fotos:2025-2026", "goleadores:2025", "actas:2025-2026", "campos:x",
                 "goleadores"):
        with pytest.raises(ValueError):
            C.ficheros(malo)
    # Cada fichero de un trabajo vuelve a ese trabajo (las fases, al de su familia).
    for trabajo in ("actas:2025-2026:alevin", "goleadores:2025-2026", "detalle:2019-2020", "campos"):
        assert {C.trabajo_de(n) for n in C.ficheros(trabajo)} == {trabajo}


def test_leer_prefiere_la_cuarentena_y_escribir_va_a_ella(tmp_path):
    principal, carpeta = tmp_path / "scripts", tmp_path / "scripts" / "historico"
    principal.mkdir()
    (principal / "fiflp_campos_raw.json").write_text("{}")
    assert C.leer("fiflp_campos_raw.json", carpeta, principal) == principal / "fiflp_campos_raw.json"
    assert C.leer("fiflp_campos_raw.json", None, principal) == principal / "fiflp_campos_raw.json"
    assert C.escribir("fiflp_campos_raw.json", carpeta, principal) == carpeta / "fiflp_campos_raw.json"
    assert carpeta.is_dir()
    (carpeta / "fiflp_campos_raw.json").write_text('{"75": {}}')
    assert C.leer("fiflp_campos_raw.json", carpeta, principal) == carpeta / "fiflp_campos_raw.json"
    assert C.leer("fiflp_detalle_2019-2020_raw.json", carpeta, principal) is None
    assert C.leer("fiflp_detalle_2019-2020_raw.json", None, principal) is None
    assert C.escribir("fiflp_campos_raw.json", None, principal) == principal / "fiflp_campos_raw.json"


def test_promover_solo_mueve_lo_de_sus_trabajos(tmp_path):
    principal, carpeta = tmp_path / "scripts", tmp_path / "scripts" / "historico"
    carpeta.mkdir(parents=True)
    nombres = ["fiflp_goleadores_2025-2026_raw.json", "fiflp_goleadores_2025-2026_grupos.json", "plan.json",
               "fiflp_actas_2025-2026_alevin_raw.json", "fiflp_actas_2025-2026_alevin_index.json",
               "fiflp_actas_2025-2026_alevin_status.json"]
    for n in nombres:
        (carpeta / n).write_text(json.dumps({"de": n}))
    (principal / "fiflp_actas_2025-2026_alevin_raw.json").write_text('{"viejo": 1}')
    assert C.en_cuarentena(carpeta) == {
        "actas:2025-2026:alevin": ["fiflp_actas_2025-2026_alevin_index.json", "fiflp_actas_2025-2026_alevin_raw.json",
                                   "fiflp_actas_2025-2026_alevin_status.json"],
        "goleadores:2025-2026": ["fiflp_goleadores_2025-2026_raw.json"]}
    assert sorted(C.promover(["actas:2025-2026:alevin"], carpeta, principal)) == [
        "fiflp_actas_2025-2026_alevin_index.json", "fiflp_actas_2025-2026_alevin_raw.json",
        "fiflp_actas_2025-2026_alevin_status.json"]
    assert sorted(p.name for p in carpeta.iterdir()) == ["fiflp_goleadores_2025-2026_grupos.json",
                                                         "fiflp_goleadores_2025-2026_raw.json", "plan.json"]
    assert json.loads((principal / "fiflp_actas_2025-2026_alevin_raw.json").read_text()) == {
        "de": "fiflp_actas_2025-2026_alevin_raw.json"}                 # el promovido sustituye al publicado
    with pytest.raises(ValueError):
        C.promover(["fotos:2025-2026"], carpeta, principal)
    # Un trabajo desconocido entre otros: no se mueve nada.
    with pytest.raises(ValueError):
        C.promover(["goleadores:2025-2026", "actas:2025-2026:senior"], carpeta, principal)
    assert (carpeta / "fiflp_goleadores_2025-2026_raw.json").exists()
    # Un trabajo sin ficheros en la cuarentena: nada.
    assert C.promover(["detalle:2019-2020"], carpeta, principal) == []
    assert C.en_cuarentena(tmp_path / "no-esta") == {}


def test_la_cli_promueve_y_apunta_lo_promovido(tmp_path):
    import subprocess
    carpeta = tmp_path / "scripts" / "historico"
    carpeta.mkdir(parents=True)
    (carpeta / "fiflp_campos_raw.json").write_text("{}")
    (carpeta / "fiflp_goleadores_2025-2026_grupos.json").write_text("{}")
    lista = tmp_path / "lista.txt"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "cuarentena.py"), "promover", "--trabajos",
                          "campos,goleadores:2025-2026", "--raiz", str(tmp_path), "--lista", str(lista)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert lista.read_text().splitlines() == ["scripts/fiflp_campos_raw.json"]
    assert (tmp_path / "scripts" / "fiflp_campos_raw.json").exists()
    assert (carpeta / "fiflp_goleadores_2025-2026_grupos.json").exists()       # del carril: no se promueve
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "cuarentena.py"), "promover", "--trabajos", "fotos",
                          "--raiz", str(tmp_path)], capture_output=True, text=True)
    assert out.returncode != 0


# ── Una tanda con carpeta no toca lo publicado ────────────────────────────────

def test_una_tanda_con_carpeta_no_toca_lo_publicado_goleadores(S, tmp_path, monkeypatch):
    publicado = tmp_path / "fiflp_goleadores_2024-2025_raw.json"
    previo = {"900:11": {"comp": "900", "grupo": "11", "ok": True, "standings": [{"pos": 1, "team": "X"}],
                         "scorers": [["A, B", "X", 1, 1, 0]], "crests": {}}}
    publicado.write_text(json.dumps(previo), encoding="utf-8")
    antes = publicado.read_bytes()
    carpeta = tmp_path / "historico"
    monkeypatch.setattr(S, "CARPETA", carpeta)
    ok, F, partes = correr_goleadores(S, FederacionFalsa(sitio_goleadores(), Reloj()))
    assert ok and publicado.read_bytes() == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fiflp_goleadores_2024-2025_raw.json", "historico"]
    copia = json.loads((carpeta / publicado.name).read_text(encoding="utf-8"))
    assert copia["900:11"] == previo["900:11"] and copia["900:12"]["ok"]       # lo que había, más lo leído
    assert (carpeta / "fiflp_goleadores_2024-2025_grupos.json").exists()       # la lista, del carril
    assert partes["goleadores:2024-2025"]["completo"]
    # Otra ejecución lee la copia de la cuarentena: no pide nada.
    ok, F, partes = correr_goleadores(S, FederacionFalsa(sitio_goleadores(), Reloj()))
    assert F.pages == 0


def test_una_tanda_con_carpeta_no_toca_lo_publicado_detalle(fed_detalle, monkeypatch):
    import fetch_fiflp_detalle as D
    principal = fed_detalle.parent
    previo = {"_grupos": {"900": [["G1", "GRUPO 1"]]},
              "900:G1": {"comp": "900", "grupo": "G1", "ok": True, "clasificacion": [], "directorio": [
                  {"venue_code": 75}]}}
    fed_detalle.write_text(json.dumps(previo), encoding="utf-8")
    campos = principal / "fiflp_campos_raw.json"
    campos.write_text(json.dumps({"75": {"ok": True, "code": 75}}), encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in (fed_detalle, campos)}
    carpeta = principal / "historico"
    monkeypatch.setattr(D, "CARPETA", carpeta)
    ok, F, partes = correr_detalle(FederacionFalsa(sitio_detalle(), Reloj()))
    assert ok and {p.name: p.read_bytes() for p in (fed_detalle, campos)} == antes
    g1 = json.loads((carpeta / fed_detalle.name).read_text(encoding="utf-8"))["900:G1"]
    assert len(g1["jornadas"]) == 5 and g1["directorio"] == [{"venue_code": 75}]  # sin volver a pedir la clasificación
    # Los campos: los de los directorios de la cuarentena mandan (aquí, el 76) sobre los de scripts/.
    copia = json.loads((carpeta / fed_detalle.name).read_text(encoding="utf-8"))
    copia["900:G1"]["directorio"] = [{"venue_code": 76}]
    (carpeta / fed_detalle.name).write_text(json.dumps(copia), encoding="utf-8")
    assert D.venue_codes(None) == [76]
    ok, F, partes = correr_detalle(FederacionFalsa(sitio_detalle(), Reloj()), campos=True)
    assert campos.read_bytes() == antes[campos.name]
    assert sorted(json.loads((carpeta / campos.name).read_text(encoding="utf-8"))) == ["75", "76"]


def test_una_tanda_con_carpeta_no_toca_lo_publicado_actas(tanda):
    # Lo publicado: una tanda de hoy (sin carpeta) que leyó tres actas.
    tanda.run(FederacionFalsa(sitio_actas(), Reloj()), "--comps", "900", "--max-actas", "3")
    publicados = {p.name: p.read_bytes() for p in tanda.dir.glob("fiflp_actas_*.json")}
    assert len(publicados) == 3 and len(tanda.raw()) == 3
    carpeta = tanda.dir / "historico"
    tanda.run(FederacionFalsa(sitio_actas(), Reloj()), "--comps", "900", "--carpeta", str(carpeta))
    assert {p.name: p.read_bytes() for p in tanda.dir.glob("fiflp_actas_*.json")} == publicados
    raw = json.loads((carpeta / "fiflp_actas_2025-2026_raw.json").read_text(encoding="utf-8"))
    assert set(raw) == todas("900")                                     # las tres de antes y las otras trece
    status = json.loads((carpeta / "fiflp_actas_2025-2026_status.json").read_text(encoding="utf-8"))
    assert status["pending"] == 0 and status["fetched"] == 13
    import scripts.fetch_fiflp_actas as A
    assert A.CARPETA is None                                            # main lo pone para su tanda y lo deja


class _PlaywrightFalso:
    """sync_playwright de mentira para llamar a main() sin navegador (ni red): un navegador que no carga nada."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def chromium(self):
        return self

    def launch(self, **kw):
        return self

    def new_page(self, **kw):
        return self

    def set_default_timeout(self, ms):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("modulo, corre", [("fetch_fiflp_goleadores", "run"), ("fetch_fiflp_detalle", "run_groups")])
def test_main_pone_la_carpeta_para_su_tanda_y_la_quita(modulo, corre, tmp_path, monkeypatch):
    """--carpeta llega a CARPETA mientras corre la tanda y vuelve a None al acabar (como en las actas); sin
    --carpeta, None: lo de siempre."""
    import importlib
    import types
    M = importlib.import_module(modulo)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api",
                        types.SimpleNamespace(sync_playwright=lambda: _PlaywrightFalso()))
    vista = []

    def tanda(*a, **k):
        vista.append(M.CARPETA)
        return True
    monkeypatch.setattr(M, corre, tanda)
    argv = ["--temporadas", "20", "--sin-campos"] if corre == "run_groups" else ["--temporadas", "20"]
    M.main(argv + ["--carpeta", str(tmp_path / "historico")])
    assert M.CARPETA is None                       # quien llame después a load o run lee lo publicado
    M.main(argv)
    assert vista == [tmp_path / "historico", None] and M.CARPETA is None


# ── El bot no ve la cuarentena ────────────────────────────────────────────────

def _base():
    from db import SCHEMA
    from migrate_actas_schema import migrate
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.execute("INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2025-2026', 2025, 2026, 0)")
    conn.execute("INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (2, '2026-2027', 2026, 2027, 1)")
    return conn


def _raws(carpeta):
    """Un raw nuevo de cada tipo (datos de prueba, sin nadie de verdad), como los que deja una tanda."""
    carpeta.mkdir(parents=True, exist_ok=True)
    acta = {"header": {"season": "2025/2026", "competition": "LIGA BENJAMIN PRUEBA (GRUPO 1)", "home_team": "LOCAL, C.F.",
                       "away_team": "VISITANTE, C.D.", "date": "04-10-2025", "home_score": 1, "away_score": 0},
            "lineups": {"home": [{"name": "JUGADOR PRUEBA, UNO", "dorsal": 1}], "away": []}, "events": [],
            "consistent": True}
    ficheros = {
        "fiflp_actas_2025-2026_raw.json": {"900111": acta},
        "fiflp_actas_2025-2026_index.json": {"900111": {"comp_id": "900", "grupo": "1", "jornada": "1"}},
        "fiflp_actas_2025-2026_status.json": {"formato": 2, "pending": 0},
        "fiflp_actas_2025-2026_alevin_raw.json": {"900112": acta},
        "fiflp_actas_2025-2026_alevin_index.json": {"900112": {"comp_id": "901", "grupo": "1", "jornada": "1"}},
        "fiflp_actas_2025-2026_alevin_status.json": {"formato": 2, "pending": 0},
        "fiflp_goleadores_2025-2026_raw.json": {"900:1": {"comp": "900", "grupo": "1", "ok": True, "standings": [
            {"pos": 1, "team": "LOCAL, C.F."}], "scorers": [["PRUEBA, UNO", "LOCAL, C.F.", 1, 2, 0]],
            "crests": {"LOCAL, C.F.": "https://x/l.png"}}},
        "fiflp_goleadores_2025-2026_grupos.json": {"grupos": {"900": [["1", "GRUPO 1"]]}, "intentos": {}},
        "fiflp_detalle_2025-2026_raw.json": {"_grupos": {"900": [["1", "GRUPO 1"]]}, "900:1": {
            "comp": "900", "grupo": "1", "ok": True, "clasificacion": [], "directorio": [{"venue_code": 75}]}},
        "fiflp_campos_raw.json": {"75": {"ok": True, "code": 75, "name": "CAMPO PRUEBA"}},
        "fiflp_torneos_raw.json": {}, "maspalomas_cup_2025_raw.json": {}, "fp_app_2025-2026_raw.json": {},
        "wayback_portal_2018-2019_raw.json": {},
    }
    for nombre, data in ficheros.items():
        (carpeta / nombre).write_text(json.dumps(data), encoding="utf-8")
    return sorted(ficheros)


def _lectores(conn, scripts, root):
    """Todos los lectores del bot que buscan sus ficheros en scripts/ (listdir o glob): los de
    fetch_futbolaspalmas.import_past_seasons (import_changed_raws, import_changed_grupos con actas_complete y
    sources_digest, import_changed_goleadores, import_changed_torneos, import_changed_portal,
    import_changed_detalle con import_campos), import_changed_fp_app, escudos_federacion.candidates,
    actas_lotes (raw_files, load_merged, misplaced), migrate_identidad.leer_originales y reconstruir."""
    import actas_lotes
    import escudos_federacion
    import import_fiflp_actas
    import import_fiflp_detalle
    import import_fiflp_goleadores
    import import_fiflp_grupos
    import import_fp_app
    import import_torneos
    import import_wayback_portal
    import migrate_identidad
    import reconstruir
    folder = str(scripts)
    silencio = dict(log=lambda *a, **k: None)
    vistos = {
        "actas_lotes.raw_files": [n for n, _, _ in actas_lotes.raw_files(folder)],
        "actas_lotes.load_merged": sorted(actas_lotes.load_merged(folder, "2025-2026", "raw")),
        "actas_lotes.misplaced": sorted(actas_lotes.misplaced(folder)),
        "import_changed_raws": sorted(import_fiflp_actas.import_changed_raws(conn, folder, **silencio)),
        "import_changed_grupos": sorted(import_fiflp_grupos.import_changed_grupos(conn, folder, **silencio) or {}),
        "actas_complete": import_fiflp_grupos.actas_complete(folder, "2025-2026"),
        "import_changed_goleadores": sorted(import_fiflp_goleadores.import_changed_goleadores(conn, folder, **silencio)),
        "import_changed_detalle": sorted(import_fiflp_detalle.import_changed_detalle(conn, folder, **silencio)),
        "import_campos": import_fiflp_detalle.import_campos(conn, folder),
        "import_changed_torneos": sorted(import_torneos.import_changed_torneos(conn, folder, **silencio) or {}),
        "import_changed_portal": sorted(import_wayback_portal.import_changed_portal(conn, folder, **silencio) or {}),
        "import_changed_fp_app": sorted(import_fp_app.import_changed_fp_app(conn, folder, **silencio) or {}),
        "escudos_federacion.candidates": sorted(escudos_federacion.candidates(conn, scripts)),
        "migrate_identidad.leer_originales": sorted(migrate_identidad.leer_originales(folder)[0]),
        "reconstruir._temporadas_pasadas": reconstruir._temporadas_pasadas(conn, folder, r"^fiflp_actas_(\d{4}-\d{4})"
                                                                                       r"(?:_[a-z]+)?_raw\.json$"),
        "reconstruir._huella_ficheros": sorted(reconstruir._huella_ficheros(root)),
    }
    return vistos


def test_el_bot_no_ve_la_cuarentena(tmp_path, monkeypatch):
    """Raws nuevos de cada tipo en scripts/historico/ de una copia: ningún lector del bot los abre ni los lista,
    ni escribe nada en la base. Control: los mismos raws en scripts/ sí se leen (los lectores no están mudos)."""
    abiertos = []
    original_open, original_io_open = builtins.open, io.open

    def apunta(file, *a, **k):
        abiertos.append(str(file))
        return original_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", apunta)
    monkeypatch.setattr(io, "open", apunta)
    monkeypatch.setenv("ACTAS_BOT_DIR", str(tmp_path / "actas_bot"))
    # Las actas sin partido de la base de prueba van a una lista temporal, no a la del repositorio
    # (scripts/fiflp_actas_unmatched.json, que import_changed_raws completa en la mitad de control).
    import import_fiflp_actas
    monkeypatch.setattr(import_fiflp_actas, "UNMATCHED_PATH", str(tmp_path / "unmatched.json"))

    root = tmp_path / "raiz"
    scripts = root / "scripts"
    nombres = _raws(scripts / "historico")
    conn = _base()
    abiertos.clear()                                            # lo que escribió la preparación, fuera
    vistos = _lectores(conn, scripts, root)
    assert not [f for f in abiertos if "historico" in f], abiertos
    assert all(not v for v in vistos.values()), vistos
    assert conn.execute("SELECT COUNT(*) FROM raw_imports").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM matches").fetchone() == (0,)

    # Control: en scripts/, los mismos ficheros sí se ven.
    _raws(scripts)
    abiertos.clear()
    vistos = _lectores(_base(), scripts, root)
    leidos = {Path(f).name for f in abiertos if "historico" not in f}
    assert leidos >= {n for n in nombres if n.startswith(("fiflp_actas_2025-2026", "fiflp_goleadores_2025-2026_raw",
                                                          "fiflp_detalle_2025-2026", "fiflp_campos"))}, leidos
    assert vistos["actas_lotes.raw_files"] == ["fiflp_actas_2025-2026_raw.json", "fiflp_actas_2025-2026_alevin_raw.json"]
    assert vistos["import_changed_raws"] and vistos["actas_complete"] and vistos["import_campos"] == 1
    assert vistos["migrate_identidad.leer_originales"] == [900111, 900112]
    assert "scripts/fiflp_goleadores_2025-2026_raw.json" in vistos["reconstruir._huella_ficheros"]
    assert not [k for k in vistos["reconstruir._huella_ficheros"] if "historico" in k]
    assert vistos["reconstruir._temporadas_pasadas"] == ["2025-2026"]
