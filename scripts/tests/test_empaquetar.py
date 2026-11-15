"""El código de la web se publica empaquetado en dist/: un app-<h>.js y un acta-<h>.css, con la huella de
su contenido en el nombre (scripts/codigo.py y scripts/empaquetar/empaquetar.mjs).

`codigo.py --check` no necesita node ni esbuild: corre también en el bot. Las pruebas que empaquetan de
verdad se saltan sin esbuild (scripts/empaquetar/node_modules), como en el bot; en el PC y en tests.yml,
que lo instala (npm ci --prefix scripts/empaquetar), corren. Siempre sobre copias del árbol.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import codigo  # noqa: E402

con_esbuild = pytest.mark.skipif(not codigo.ESBUILD.exists(), reason="sin esbuild: npm ci --prefix scripts/empaquetar")


def _copia(tmp_path):
    """Lo que leen codigo.py y empaquetar.mjs: la página, el SW, la hoja, src/ y dist/."""
    for name in ("index.html", "sw.js", "acta.css"):
        shutil.copy2(ROOT / name, tmp_path / name)
    for name in ("src", "dist"):
        shutil.copytree(ROOT / name, tmp_path / name)
    return tmp_path


def _textos(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in [root / "index.html", root / "sw.js", *sorted((root / "dist").iterdir())]}


def test_check_pasa_en_el_arbol():
    assert codigo.main(["--check"]) == 0


def test_check_falla_si_cambian_las_fuentes(tmp_path):
    # src/config.js no cuenta (test_config_queda_fuera): cualquier otro módulo de src/, sí.
    site = _copia(tmp_path)
    (site / "src" / "app.js").write_text((site / "src" / "app.js").read_text(encoding="utf-8") + "// otro\n", encoding="utf-8")
    assert codigo.main(["--check", "--root", str(site)]) == 1


def test_check_falla_si_cambia_la_hoja(tmp_path):
    site = _copia(tmp_path)
    (site / "acta.css").write_text((site / "acta.css").read_text(encoding="utf-8") + "/* otra */\n", encoding="utf-8")
    assert codigo.main(["--check", "--root", str(site)]) == 1


def test_check_falla_si_dist_no_es_su_huella(tmp_path):
    site = _copia(tmp_path)
    app = site / codigo.leer_origen(site)["app"]
    data = bytearray(app.read_bytes())
    data[-1] = ord(" ") if data[-1] != ord(" ") else ord("\n")
    app.write_bytes(bytes(data))
    assert codigo.main(["--check", "--root", str(site)]) == 1


def test_check_falla_si_falta_un_fichero_de_dist(tmp_path):
    site = _copia(tmp_path)
    (site / codigo.leer_origen(site)["css"]).unlink()
    assert codigo.main(["--check", "--root", str(site)]) == 1


def test_check_falla_si_sobra_un_paquete_viejo_en_dist(tmp_path):
    site = _copia(tmp_path)
    (site / "dist" / "app-00000000.js").write_text("export {};\n", encoding="utf-8")
    assert codigo.main(["--check", "--root", str(site)]) == 1


def test_check_falla_si_index_no_referencia(tmp_path, capsys):
    site = _copia(tmp_path)
    css = codigo.leer_origen(site)["css"]
    index = (site / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(index.replace(f"./{css}", "./dist/acta-00000000.css"), encoding="utf-8")
    assert codigo.main(["--check", "--root", str(site)]) == 1
    assert f"index.html no referencia ./{css}" in capsys.readouterr().out


def test_check_no_mira_sw_js(tmp_path):
    # El paquete en sw.js es cosa del manifiesto del precache (scripts/precache.py y test_precache.py).
    site = _copia(tmp_path)
    (site / "sw.js").write_text("const CACHE_NAME = 'futbolbase2-v20260101';\n", encoding="utf-8")
    assert codigo.main(["--check", "--root", str(site)]) == 0


def test_origen_describe_el_paquete():
    origen = codigo.leer_origen(ROOT)
    assert list(origen) == ["codigo", "app", "css", "externos"]
    assert origen["codigo"] == codigo.huella(ROOT)
    assert re.fullmatch(r"dist/app-[0-9a-f]{8}\.js", origen["app"]), origen
    assert re.fullmatch(r"dist/acta-[0-9a-f]{8}\.css", origen["css"]), origen
    assert origen["externos"] == ["src/config.js"]
    for key in ("app", "css"):
        data = (ROOT / origen[key]).read_bytes()
        assert origen[key].endswith(f"-{hashlib.sha1(data).hexdigest()[:8]}" + Path(origen[key]).suffix)
    assert sorted(path.name for path in (ROOT / "dist").iterdir()) == sorted(
        ["origen.json", Path(origen["app"]).name, Path(origen["css"]).name])


def test_index_y_sw_cargan_el_paquete():
    origen = codigo.leer_origen(ROOT)
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert f'<link rel="stylesheet" href="./{origen["css"]}">' in index
    assert f"await import('./{origen['app']}');" in index
    for key in ("app", "css"):
        assert f'  "{origen[key]}": "{Path(origen[key]).stem.split("-")[-1]}",\n' in sw, f"{key}, en el precache con su huella"
    assert '"acta.css"' not in sw and "'./acta.css'" not in sw


@con_esbuild
def test_empaquetar_es_reproducible(tmp_path):
    site = _copia(tmp_path)
    viejo = site / "dist" / "app-00000000.js"
    viejo.write_text("export {};\n", encoding="utf-8")
    antes = _textos(ROOT)
    assert codigo.main(["--root", str(site)]) == 0
    assert not viejo.exists(), "el paquete viejo se borra"
    assert _textos(site) == antes, "mismos nombres y mismos bytes que el repositorio"
    assert codigo.main(["--check", "--root", str(site)]) == 0


@con_esbuild
def test_empaquetar_cambia_el_nombre_si_cambia_el_codigo(tmp_path):
    site = _copia(tmp_path)
    antes = codigo.leer_origen(site)
    state = site / "src" / "state.js"
    # Una exportación que nadie usa no llegaría al paquete: una sentencia, sí.
    state.write_text(state.read_text(encoding="utf-8") + "\nglobalThis.otraVersion = 'b';\n", encoding="utf-8")
    assert codigo.main(["--root", str(site)]) == 0
    despues = codigo.leer_origen(site)
    assert despues["app"] != antes["app"] and despues["css"] == antes["css"]
    assert despues["codigo"] == codigo.huella(site) != antes["codigo"]
    assert sorted(path.name for path in (site / "dist").iterdir()) == sorted(
        ["origen.json", Path(despues["app"]).name, Path(despues["css"]).name])
    index = (site / "index.html").read_text(encoding="utf-8")
    assert f"./{despues['app']}" in index and f"./{antes['app']}" not in index
    assert "CODIGO" not in index
    assert (site / "sw.js").read_bytes() == (ROOT / "sw.js").read_bytes(), "sw.js lo escribe precache.py, no codigo.py"
    assert codigo.main(["--check", "--root", str(site)]) == 0


def test_sin_esbuild_se_para_sin_escribir(tmp_path, monkeypatch, capsys):
    site = _copia(tmp_path)
    (site / "src" / "app.js").write_text((site / "src" / "app.js").read_text(encoding="utf-8") + "// otro\n", encoding="utf-8")
    antes = _textos(site)
    monkeypatch.setattr(codigo, "ESBUILD", tmp_path / "no-esta" / "esbuild")
    assert codigo.main(["--root", str(site)]) == 1
    assert capsys.readouterr().out.strip() == "falta esbuild: npm ci --prefix scripts/empaquetar"
    assert _textos(site) == antes


def test_sin_app_js_no_hay_nada_que_empaquetar(tmp_path, capsys):
    site = _copia(tmp_path)
    (site / "src" / "app.js").unlink()
    antes = _textos(site)
    assert codigo.main(["--root", str(site)]) == 1
    assert capsys.readouterr().out.strip() == f"{site} no tiene src/app.js: nada que empaquetar"
    assert _textos(site) == antes


def test_la_hoja_empaquetada_resuelve_la_fuente():
    css_path = ROOT / codigo.leer_origen(ROOT)["css"]
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", css_path.read_text(encoding="utf-8"))
    assert urls, "la hoja sin url(): ¿y la fuente?"
    for url in urls:
        assert (css_path.parent / url).resolve().is_file(), f"{url}, desde dist/, no existe"


def test_el_paquete_exporta_start():
    app = ROOT / codigo.leer_origen(ROOT)["app"]
    done = subprocess.run(["node", "--input-type=module", "-e",
                           f"import({json.dumps(app.as_uri())}).then(m => process.exit(typeof m.start === 'function' ? 0 : 1))"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


def test_config_queda_fuera(tmp_path):
    app = (ROOT / codigo.leer_origen(ROOT)["app"]).read_text(encoding="utf-8")
    assert re.search(r"""from\s*["']\.\./src/config\.js["']""", app), "el paquete importa ../src/config.js"
    # Los valores de config.js no van dentro (los nombres de sus campos, sí: el código los lee; y el nombre del
    # equipo por defecto puede salir en otras tablas del código).
    portal = json.loads(re.sub(r"^export const PORTAL = |;\s*$", "", (ROOT / "src" / "config.js").read_text(encoding="utf-8")))
    assert f'"{portal["season"]}"' not in app
    assert f'nextSeason:"{portal["nextSeason"]}"' not in app
    site = _copia(tmp_path)
    antes = codigo.huella(site)
    config = site / "src" / "config.js"
    config.write_text(config.read_text(encoding="utf-8").replace(portal["defaultTeam"]["name"], "Otro equipo") + "// otra\n",
                      encoding="utf-8")
    assert codigo.huella(site) == antes
    assert codigo.main(["--check", "--root", str(site)]) == 0
