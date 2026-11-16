#!/usr/bin/env python3
"""El código de la web, empaquetado en dist/.

La página no pide src/ ni acta.css: carga dist/app-<h>.js (src/app.js con todo su grafo, en un módulo) y
dist/acta-<h>.css (la hoja minificada), cada uno con las 8 primeras cifras del SHA-1 de su contenido en el
nombre, y src/config.js aparte, que queda fuera del paquete porque lo reescribe la activación de una
temporada sin que cambie el código. Los empaqueta scripts/empaquetar/empaquetar.mjs (esbuild); este guion
lo llama, borra los anteriores, escribe dist/origen.json (con la huella de las fuentes: acta.css y src/*.js
salvo src/config.js) y pone las dos rutas en index.html. El manifiesto del precache de sw.js, que lleva
las rutas y sus huellas, lo escribe después scripts/precache.py. Solo se empaqueta al publicar, en el PC
(scripts/publicar.py); ni el bot ni la activación de una temporada lo hacen nunca, y `--check`, que no
necesita node, comprueba que dist/ es el de las fuentes.

Uso, desde la raíz del repositorio:
  python3 scripts/codigo.py          # empaqueta y escribe dist/ e index.html (después: scripts/precache.py)
  python3 scripts/codigo.py --check  # no escribe nada: sale con 1 si dist/ no es el de las fuentes
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from escritura import escribir_atomico

ROOT = Path(__file__).resolve().parents[1]
EMPAQUETAR = ROOT / "scripts" / "empaquetar" / "empaquetar.mjs"
ESBUILD = ROOT / "scripts" / "empaquetar" / "node_modules" / "esbuild"
APP_RE = re.compile(r"\./dist/app-[0-9a-f]{8}\.js")
CSS_RE = re.compile(r"\./dist/acta-[0-9a-f]{8}\.css")
PAQUETE_RE = re.compile(r"(?:app-[0-9a-f]{8}\.js|acta-[0-9a-f]{8}\.css)")
EXTERNOS = ["src/config.js"]


def huella(root=ROOT):
    """La de acta.css y src/*.js (sin src/config.js) por nombre: de cada uno, su ruta, un cero, su
    contenido y otro cero."""
    root = Path(root)
    digest = hashlib.sha1()
    sources = [path for path in sorted((root / "src").glob("*.js")) if path.relative_to(root).as_posix() not in EXTERNOS]
    for path in [root / "acta.css", *sources]:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:8]


def huella_fichero(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]


def leer_origen(root=ROOT):
    """dist/origen.json: la huella de las fuentes, las rutas del paquete y lo que se queda fuera."""
    return json.loads((Path(root) / "dist" / "origen.json").read_text(encoding="utf-8"))


def _marcas(index):
    """Lo que tiene que haber en index.html para poner las rutas: una de cada."""
    problems = []
    for pattern, what in ((APP_RE, "./dist/app-<h>.js"), (CSS_RE, "./dist/acta-<h>.css")):
        if len(pattern.findall(index)) != 1:
            problems.append(f"index.html tiene que llevar una ruta {what}, y lleva {len(pattern.findall(index))}")
    return problems


def comprobar(root=ROOT):
    """Lo que no cuadra entre las fuentes, dist/ e index.html; vacío si todo está al día."""
    root = Path(root)
    try:
        origen = leer_origen(root)
    except (OSError, ValueError) as error:
        return [f"dist/origen.json no se puede leer: {error}"]
    problems = []
    want = huella(root)
    if origen.get("codigo") != want:
        problems.append(f"dist/ es de las fuentes {origen.get('codigo')}, y las del árbol son {want}: python3 scripts/codigo.py")
    index = (root / "index.html").read_text(encoding="utf-8")
    wanted = set()
    for key, prefix, ext in (("app", "dist/app-", ".js"), ("css", "dist/acta-", ".css")):
        rel = origen.get(key) or ""
        wanted.add(Path(rel).name)
        path = root / rel
        if not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{8}" + re.escape(ext), rel):
            problems.append(f"dist/origen.json: {key} = {rel!r} no tiene la forma {prefix}<h>{ext}")
        elif not path.is_file():
            problems.append(f"falta {rel}")
        elif huella_fichero(path) != rel[len(prefix):-len(ext)]:
            problems.append(f"{rel} no lleva en el nombre la huella de su contenido, {huella_fichero(path)}")
        if f"./{rel}" not in index:
            problems.append(f"index.html no referencia ./{rel}")
    extra = sorted(path.name for path in (root / "dist").glob("*") if PAQUETE_RE.fullmatch(path.name) and path.name not in wanted)
    if extra:
        problems.append(f"sobran en dist/ paquetes viejos: {', '.join(extra)}")
    return problems


def empaquetar(root):
    """Llama a empaquetar.mjs; devuelve sus rutas ({"app": …, "css": …}) o lanza RuntimeError."""
    done = subprocess.run(["node", str(EMPAQUETAR), "--root", str(root)], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"empaquetar.mjs falló ({done.returncode}): {done.stderr.strip()}")
    rutas = json.loads(done.stdout)
    for key, pattern in (("app", APP_RE), ("css", CSS_RE)):
        if not pattern.fullmatch(f"./{rutas.get(key, '')}"):
            raise RuntimeError(f"empaquetar.mjs dio una ruta {key} sin la forma de dist/: {rutas!r}")
    return rutas


def puede_empaquetar(root=ROOT):
    """Por qué no se puede empaquetar `root` (sin escribir nada), o None si se puede."""
    root = Path(root)
    for rel in ("src/app.js", "acta.css"):
        if not (root / rel).is_file():
            return f"{root} no tiene {rel}: nada que empaquetar"
    if not ESBUILD.exists():
        return "falta esbuild: npm ci --prefix scripts/empaquetar"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Empaqueta el código en dist/ (o comprueba que dist/ es el de las fuentes).")
    parser.add_argument("--check", action="store_true", help="no escribe nada: sale con 1 si dist/ no es el de las fuentes")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.check:
        problems = comprobar(root)
        for problem in problems:
            print(problem)
        if not problems:
            origen = leer_origen(root)
            print(f"fuentes {origen['codigo']}: dist/ es el de las fuentes ({origen['app']} y {origen['css']})")
        return 1 if problems else 0
    index_path = root / "index.html"
    index = index_path.read_text(encoding="utf-8")
    problems = _marcas(index)
    why = puede_empaquetar(root)
    if problems or why:
        print("\n".join(problems + ([why] if why else [])))
        return 1
    try:
        rutas = empaquetar(root)
    except RuntimeError as error:
        print(error)
        return 1
    keep = {Path(rutas["app"]).name, Path(rutas["css"]).name}
    for path in (root / "dist").glob("*"):
        if PAQUETE_RE.fullmatch(path.name) and path.name not in keep:
            path.unlink()
    want = huella(root)
    origen = {"codigo": want, "app": rutas["app"], "css": rutas["css"], "externos": EXTERNOS}
    escribir_atomico(root / "dist" / "origen.json", json.dumps(origen, ensure_ascii=False, indent=2) + "\n")
    nuevo = CSS_RE.sub(f"./{rutas['css']}", APP_RE.sub(f"./{rutas['app']}", index))
    if nuevo != index:
        escribir_atomico(index_path, nuevo)
    print(f"fuentes {want}: {rutas['app']} y {rutas['css']}, en index.html (el precache de sw.js: scripts/precache.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
