#!/usr/bin/env python3
"""El manifiesto del precache del service worker: un bloque de sw.js, entre dos marcas, con lo que se instala.

Cada fichero va con su huella, las 8 primeras cifras hex del SHA-1 de su contenido: el SW lo pide como
`./<ruta>?h=<huella>`, comprueba que el cuerpo que llega da esa huella y solo entonces lo guarda, con esa
clave, en la caché futbolbase2-precache. Así una instalación nunca mezcla dos versiones de un fichero, y la
siguiente solo baja lo que ha cambiado.

Obligatorios (sin uno de ellos el SW no se instala): index.html; la hoja, el paquete y lo que se queda fuera
de él (dist/origen.json, que escribe scripts/codigo.py); manifest.json; la fuente; los cuatro iconos; y los
data-*.js de las etiquetas <script defer> de index.html. Opcionales (si fallan, se bajan al usarse):
data-alevin.js y los data-season-AAAA-AAAA.js del árbol, de la temporada más nueva a la más vieja. Nunca los
de infantil, cadete y juvenil (data-infantil.js, data-matchdetail-<clave>.js, data-season-<S>-<clave>.js: parte
E2), ni obligatorios ni opcionales: cada uno pesa ~0,5 MB al acabar la temporada, y una familia que sigue a un
niño de benjamín no tiene por qué instalarlos; se bajan al usarse.

Lo escribe generate_js.main() en cada pasada del bot, activate_season.apply_manifest al activar una
temporada y scripts/publicar.py al publicar; nadie lo toca a mano. Un árbol sin las marcas en sw.js o sin
dist/origen.json (los de juguete de las pruebas, la carpeta temporal de una activación) no se toca. La
prueba test_precache.py comprueba que el bloque es el del árbol: el bot la pasa antes de publicar.

Uso, desde la raíz del repositorio:
  python3 scripts/precache.py          # reescribe el bloque, si cambia
  python3 scripts/precache.py --check  # no escribe nada: sale con 1 si el bloque no es el del árbol
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from escritura import escribir_atomico

ROOT = Path(__file__).resolve().parents[1]
INICIO = "// >>> precache: lo escribe scripts/precache.py"
FIN = "// <<< precache"
FIJOS = [
    "manifest.json",
    "fonts/PublicSans-latin.woff2",
    "icons/icon-180.png",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/icon-maskable-512.png",
]
DATO_INMEDIATO_RE = re.compile(r'<script\b(?=[^>]*\sdefer\b)[^>]*\ssrc="\./(data-[\w.-]+\.js)(?:\?[^"]*)?"')
TEMPORADA_RE = re.compile(r"data-season-(\d{4})-(\d{4})\.js")
ENTRADA_RE = re.compile(r'^  "([^"]+)": "([0-9a-f]{8})",?$', re.M)


def huella(path):
    """Las 8 primeras cifras hex del SHA-1 del contenido de `path`."""
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]


def _origen(root):
    return json.loads((Path(root) / "dist" / "origen.json").read_text(encoding="utf-8"))


def datos_inmediatos(index):
    """Los data-*.js de las etiquetas <script defer> de index.html, en su orden."""
    return DATO_INMEDIATO_RE.findall(index)


def temporadas(root):
    """Los data-season-AAAA-AAAA.js del árbol, de la temporada más nueva a la más vieja."""
    found = [path.name for path in Path(root).glob("data-season-*.js") if TEMPORADA_RE.fullmatch(path.name)]
    return sorted(found, reverse=True)


def entradas(root=ROOT):
    """(ruta → huella, opcionales): lo que el SW instala, los obligatorios primero. FileNotFoundError si
    falta un obligatorio."""
    root = Path(root)
    origen = _origen(root)
    index = (root / "index.html").read_text(encoding="utf-8")
    obligatorios = ["index.html", origen["css"], origen["app"], *origen.get("externos", []), *FIJOS,
                    *datos_inmediatos(index)]
    opcionales = (["data-alevin.js"] if (root / "data-alevin.js").is_file() else []) + temporadas(root)
    rutas = list(dict.fromkeys(obligatorios + opcionales))
    opcionales = [ruta for ruta in opcionales if ruta not in obligatorios]
    return {ruta: huella(root / ruta) for ruta in rutas}, opcionales


def bloque(precache, opcionales):
    """El texto del bloque, marcas incluidas."""
    lines = [INICIO, "const PRECACHE = {"]
    lines += [f"  {json.dumps(ruta)}: {json.dumps(h)}," for ruta, h in precache.items()]
    lines += ["};", "const OPCIONALES = ["]
    lines += [f"  {json.dumps(ruta)}," for ruta in opcionales]
    lines += ["];", FIN]
    return "\n".join(lines)


def tramo(sw):
    """(inicio, fin) del bloque en sw.js, marcas incluidas, o None si no lleva una de cada."""
    if sw.count(INICIO) != 1 or sw.count(FIN) != 1:
        return None
    start = sw.index(INICIO)
    end = sw.find(FIN, start)
    if end < 0:
        return None
    return start, end + len(FIN)


def _completo(root):
    """El árbol tiene sw.js con las marcas y dist/origen.json: el bloque se puede escribir."""
    root = Path(root)
    sw_path = root / "sw.js"
    if not sw_path.is_file() or not (root / "dist" / "origen.json").is_file():
        return None
    sw = sw_path.read_text(encoding="utf-8")
    return sw if tramo(sw) else None


def escribir(root=ROOT):
    """Reescribe el bloque de sw.js con el del árbol; True si ha cambiado. En un árbol parcial (sw.js sin
    las marcas o sin dist/origen.json) no hace nada y devuelve False."""
    root = Path(root)
    sw = _completo(root)
    if sw is None:
        return False
    precache, opcionales = entradas(root)
    start, end = tramo(sw)
    nuevo = sw[:start] + bloque(precache, opcionales) + sw[end:]
    if nuevo == sw:
        return False
    escribir_atomico(root / "sw.js", nuevo)
    print(f"  sw.js precache: {len(precache)} ficheros, {len(opcionales)} opcionales")
    return True


def comprobar(root=ROOT):
    """Lo que no cuadra entre el bloque de sw.js y el árbol; vacío si está al día."""
    root = Path(root)
    try:
        sw = (root / "sw.js").read_text(encoding="utf-8")
    except OSError as error:
        return [f"sw.js no se puede leer: {error}"]
    donde = tramo(sw)
    if donde is None:
        return [f"sw.js tiene que llevar una vez cada marca del bloque del precache ({INICIO!r} y {FIN!r})"]
    try:
        precache, opcionales = entradas(root)
        origen = _origen(root)
    except (OSError, ValueError, KeyError) as error:
        return [f"no se puede calcular el precache del árbol: {error}"]
    problems = []
    actual = sw[donde[0]:donde[1]]
    if actual != bloque(precache, opcionales):
        tenia = dict(ENTRADA_RE.findall(actual))
        for ruta, h in precache.items():
            if ruta not in tenia:
                problems.append(f"falta {ruta} en el precache")
            elif tenia[ruta] != h:
                problems.append(f"{ruta}: el precache dice {tenia[ruta]} y su contenido da {h}")
        for ruta in tenia:
            if ruta not in precache:
                problems.append(f"sobra {ruta} en el precache")
        problems.append("el bloque del precache de sw.js no es el del árbol: python3 scripts/precache.py")
    index = (root / "index.html").read_text(encoding="utf-8")
    for key in ("app", "css"):
        if f"./{origen[key]}" not in index:
            problems.append(f"index.html no carga ./{origen[key]}, el {key} de dist/origen.json")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Escribe (o comprueba) el bloque del precache de sw.js.")
    parser.add_argument("--check", action="store_true", help="no escribe nada: sale con 1 si el bloque no es el del árbol")
    parser.add_argument("--root", default=str(ROOT), help="la raíz del árbol (por defecto, la del repositorio)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.check:
        problems = comprobar(root)
        for problem in problems:
            print(problem)
        if not problems:
            print("el bloque del precache de sw.js es el del árbol")
        return 1 if problems else 0
    if _completo(root) is None:
        print(f"{root} no tiene sw.js con las marcas del precache o dist/origen.json: nada escrito")
        return 1
    if not escribir(root):
        print("el bloque del precache de sw.js ya estaba al día")
    return 0


if __name__ == "__main__":
    sys.exit(main())
