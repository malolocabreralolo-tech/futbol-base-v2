"""El manifiesto del precache del service worker (scripts/precache.py): el bloque de sw.js con cada fichero
que se instala y su huella.

El SW comprueba al instalar que cada cuerpo da su huella y, si un obligatorio no la da, no se instala: un
bloque que no es el del árbol dejaría la app instalada sin actualizarse. Por eso la primera prueba mira el
árbol de verdad, y el bot la pasa antes de publicar. Las demás, sobre árboles de juguete.
"""
import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_js  # noqa: E402
import precache  # noqa: E402

LINEA_1 = "const CACHE_NAME = 'futbolbase2-v20260101';"
LINEA_2 = "const CRESTS_CACHE = 'futbolbase2-escudos-00000000';"
SW = f"{LINEA_1}\n{LINEA_2}\n\n{precache.INICIO}\nconst PRECACHE = {{}};\nconst OPCIONALES = [];\n{precache.FIN}\n\nfunction classifyRequest() {{}}\n"
INDEX = """<!DOCTYPE html>
<link rel="stylesheet" href="./dist/acta-11111111.css">
<span id="legacyUpdated" hidden>Última actualización: 01/01/2026</span>
<script defer src="./data-a.js?v=20260101"></script>
<script defer src="./data-b.js?v=20260101"></script>
<script type="module">
  (async () => { const { start } = await import('./dist/app-22222222.js'); start(document, window); })();
</script>
"""
OBLIGATORIOS = ["index.html", "dist/acta-11111111.css", "dist/app-22222222.js", "src/config.js", *precache.FIJOS,
                "data-a.js", "data-b.js"]
OPCIONALES = ["data-alevin.js", "data-season-2024-2025.js", "data-season-2023-2024.js"]


def _arbol(root):
    """Un árbol completo de juguete: cada fichero con un contenido distinto."""
    root = Path(root)
    files = {
        "index.html": INDEX,
        "sw.js": SW,
        "dist/origen.json": json.dumps({"codigo": "33333333", "app": "dist/app-22222222.js",
                                        "css": "dist/acta-11111111.css", "externos": ["src/config.js"]}),
        "dist/acta-11111111.css": "body{}",
        "dist/app-22222222.js": "export function start() {}",
        "src/config.js": "export const PORTAL = {};\n",
        "data-a.js": "const A=1;\n",
        "data-b.js": "const B=1;\n",
        "data-alevin.js": "const ALEVIN=[];\n",
        "data-season-2024-2025.js": "const SEASON_2024_2025={};\n",
        "data-season-2023-2024.js": "const SEASON_2023_2024={};\n",
        "data-season-2024-2025-alevin.js": "const SEASON_2024_2025_ALEVIN={};\n",
        "data-lineups-2024-2025-X1.js": "const LINEUPS={};\n",
        "data-jugadores-3.js": "const JUGADORES_3 = {};\n",
        "data-buscar-go.js": "const BUSCAR_GO = [];\n",
        "data-ranking.js": "const RANKING = {};\n",
        "data-ranking-2017.js": "const RANKING_2017 = {};\n",
        "data-health.json": "{}\n",
    }
    for rel in precache.FIJOS:
        files[rel] = f"fijo {rel}"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _bloque(root):
    sw = (Path(root) / "sw.js").read_text(encoding="utf-8")
    return dict(precache.ENTRADA_RE.findall(sw[sw.index(precache.INICIO):sw.index(precache.FIN)]))


def test_el_bloque_del_repositorio_es_el_del_arbol():
    assert precache.comprobar(ROOT) == []


def test_obligatorios_y_opcionales(tmp_path):
    site = _arbol(tmp_path)
    entries, opcionales = precache.entradas(site)
    assert list(entries) == OBLIGATORIOS + OPCIONALES
    assert opcionales == OPCIONALES
    assert "data-season-2024-2025-alevin.js" not in entries, "el alevín de temporada se baja al usarse"
    assert "data-lineups-2024-2025-X1.js" not in entries, "las actas, también"
    # Las fichas, el buscador y el ranking: perezosos, se guardan al usarse (ni obligatorios ni opcionales).
    for ruta in ("data-jugadores-3.js", "data-buscar-go.js", "data-ranking.js", "data-ranking-2017.js"):
        assert ruta not in entries and ruta not in opcionales, ruta
    assert "data-health.json" not in entries, "la salud va en la caché de la versión, de la red primero"


def test_la_huella_es_el_sha1_del_contenido(tmp_path):
    site = _arbol(tmp_path)
    entries, _ = precache.entradas(site)
    for ruta, huella in entries.items():
        assert huella == hashlib.sha1((site / ruta).read_bytes()).hexdigest()[:8], ruta
    assert precache.escribir(site) is True
    assert _bloque(site) == entries


def test_escribir_solo_si_cambia(tmp_path):
    site = _arbol(tmp_path)
    assert precache.escribir(site) is True
    antes = (site / "sw.js").read_bytes()
    assert precache.escribir(site) is False
    assert (site / "sw.js").read_bytes() == antes
    assert precache.comprobar(site) == []


def test_escribir_no_toca_la_linea_1(tmp_path):
    site = _arbol(tmp_path)
    precache.escribir(site)
    sw = (site / "sw.js").read_text(encoding="utf-8")
    assert sw.splitlines()[:2] == [LINEA_1, LINEA_2]
    assert sw.endswith(f"{precache.FIN}\n\nfunction classifyRequest() {{}}\n"), "lo de fuera del bloque, igual"
    # El bloque tiene la forma que lee el SW.
    assert re.search(r'^const PRECACHE = \{\n(  "[^"]+": "[0-9a-f]{8}",\n)+\};\nconst OPCIONALES = \[\n(  "[^"]+",\n)+\];$',
                     sw, re.M), sw


def test_cambiar_un_dato_cambia_solo_su_huella(tmp_path):
    site = _arbol(tmp_path)
    precache.escribir(site)
    antes = _bloque(site)
    (site / "data-b.js").write_text("const B=2;\n", encoding="utf-8")
    assert precache.comprobar(site) != []
    assert any("data-b.js" in problem for problem in precache.comprobar(site))
    assert precache.escribir(site) is True
    despues = _bloque(site)
    assert [ruta for ruta in antes if antes[ruta] != despues[ruta]] == ["data-b.js"]


def test_falta_un_obligatorio(tmp_path):
    site = _arbol(tmp_path)
    (site / "manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        precache.entradas(site)
    with pytest.raises(FileNotFoundError):
        precache.escribir(site)
    assert precache.comprobar(site) != []


def test_un_opcional_que_falta_no_entra(tmp_path):
    site = _arbol(tmp_path)
    (site / "data-alevin.js").unlink()
    entries, opcionales = precache.entradas(site)
    assert "data-alevin.js" not in entries and opcionales == OPCIONALES[1:]


def test_las_categorias_nuevas_no_entran(tmp_path):
    # Infantil, cadete y juvenil (parte E2) se bajan al usarse: ni obligatorios ni opcionales. Una familia que
    # sigue a un niño de benjamín no instala sus ~0,5 MB por categoría.
    site = _arbol(tmp_path)
    for rel in ("data-infantil.js", "data-matchdetail-cadete.js", "data-season-2025-2026-juvenil.js"):
        (site / rel).write_text("const X={};\n", encoding="utf-8")
    entries, opcionales = precache.entradas(site)
    for rel in ("data-infantil.js", "data-matchdetail-cadete.js", "data-season-2025-2026-juvenil.js"):
        assert rel not in entries and rel not in opcionales, rel
    assert opcionales == OPCIONALES


def test_arbol_parcial_no_se_toca(tmp_path):
    sin_origen = _arbol(tmp_path / "a")
    (sin_origen / "dist" / "origen.json").unlink()
    antes = (sin_origen / "sw.js").read_bytes()
    assert precache.escribir(sin_origen) is False
    assert (sin_origen / "sw.js").read_bytes() == antes
    sin_marcas = _arbol(tmp_path / "b")
    sw = f"{LINEA_1}\nconst SEASON_FILES = [\n];\n"
    (sin_marcas / "sw.js").write_text(sw, encoding="utf-8")
    assert precache.escribir(sin_marcas) is False
    assert (sin_marcas / "sw.js").read_text(encoding="utf-8") == sw
    assert precache.escribir(tmp_path / "vacio") is False
    assert precache.comprobar(sin_marcas) != [], "comprobar sí avisa"


def test_generate_js_deja_el_bloque_al_dia(tmp_path):
    # La subida de versión cambia index.html (sus ?v=): la huella de index.html del bloque tiene que ser la del
    # index.html ya subido, así que generate_js.main() escribe el bloque después de bump_if_changed.
    site = _arbol(tmp_path)
    precache.escribir(site)
    generate_js.bump_cache_version(str(site), version="20260102")
    assert precache.comprobar(site) != [], "la subida deja el bloque viejo"
    assert precache.escribir(site) is True
    assert _bloque(site)["index.html"] == hashlib.sha1((site / "index.html").read_bytes()).hexdigest()[:8]
    assert (site / "sw.js").read_text(encoding="utf-8").splitlines()[0] == "const CACHE_NAME = 'futbolbase2-v20260102';"
    main = inspect.getsource(generate_js.main)
    assert "precache.escribir(PROJECT_ROOT)" in main
    assert main.index("bump_if_changed(before_snapshot)") < main.index("precache.escribir(PROJECT_ROOT)")


def test_check_por_la_linea_de_ordenes(tmp_path, capsys):
    site = _arbol(tmp_path)
    assert precache.main(["--check", "--root", str(site)]) == 1
    assert precache.main(["--root", str(site)]) == 0
    assert precache.main(["--check", "--root", str(site)]) == 0
    assert "es el del árbol" in capsys.readouterr().out


def test_el_bloque_de_verdad_tiene_lo_que_lee_index():
    entries, opcionales = precache.entradas(ROOT)
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    origen = json.loads((ROOT / "dist" / "origen.json").read_text(encoding="utf-8"))
    for ruta in ("index.html", origen["app"], origen["css"], *origen["externos"], *precache.FIJOS):
        assert ruta in entries and ruta not in opcionales, ruta
    inmediatos = re.findall(r'<script defer src="\./(data-[\w.-]+\.js)\?v=', index)
    assert len(inmediatos) == 7 and all(ruta in entries and ruta not in opcionales for ruta in inmediatos)
    assert opcionales[0] == "data-alevin.js" and len(opcionales) > 1
    assert "data-matchdetail.js" not in entries, "perezoso: se guarda al usarse"
