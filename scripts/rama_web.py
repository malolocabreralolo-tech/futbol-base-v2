#!/usr/bin/env python3
"""La rama `web`: lo que publica GitHub Pages, sacado de `main` en cada subida.

Por qué. Hasta la parte D, Pages publicaba `main` entero: la web y, con ella, la base, sus piezas, los originales
de `scripts/`, los documentos y la copia del PC (287 MB el 25/11/2026). Pages admite 1 GB por sitio y, con todas
las actas, `main` lo pasaría. La web sola ocupa hoy unos 81 MB (unos 520 con todas las actas). Así que Pages
publica la rama `web`, que lleva solo lo que la web sirve:
  - WEB_FICHEROS de la raíz: la página, el SW, el manifiesto, la hoja de la app de antes del empaquetado,
    .nojekyll (sin él, Pages pasaría la web por Jekyll) y data-health.json;
  - WEB_CARPETAS enteras: dist/ (el código), src/ y acta.css (la app de antes del empaquetado, que se sirve
    mientras un móvil se pone al día: scripts/tests/copia-web.mjs), fonts/, icons/ y escudos/;
  - los data-*.js de la raíz (WEB_PATRONES).
Fuera, todo lo demás: data-history-2024.json (no lo pide la web), scripts/, base/, futbolbase.db, docs/, pc/,
.github/ y README.md.

Cada commit de `web` es un árbol hecho con los mismos blobs de `main` (no duplica nada en git: solo árboles y
commits, unos KB por subida), con el anterior de `web` como padre, y se sube sin forzar: la rama nunca retrocede
(un push que pasa sin forzar no tiene a nadie delante, y su `main` es la de ese mismo fetch). La ponen al día el
bot (update.yml) y la activación (activar.yml) tras sus subidas, y web.yml tras un push a mano, a mano y cada 6 h.
Antes de subir se comprueba que el árbol lleva todo lo que el SW precachea, lo que carga index.html y .nojekyll:
sin uno de ellos el SW no se instalaría en ningún móvil, y no se sube.

Uso, desde la raíz del repositorio:
  python3 scripts/rama_web.py publicar           # pone al día la rama web del remoto (origin)
  python3 scripts/rama_web.py arbol [--commit C] # el árbol de la web de C (por defecto, HEAD) y su tamaño
  python3 scripts/rama_web.py sitio URL          # para el director: el precache del sitio publicado, fichero a fichero
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import precache

ROOT = Path(__file__).resolve().parents[1]
WEB_FICHEROS = ("index.html", "sw.js", "manifest.json", "acta.css", ".nojekyll", "data-health.json")
WEB_CARPETAS = ("dist/", "src/", "fonts/", "icons/", "escudos/")
WEB_PATRONES = ("data-*.js",)     # solo en la raíz
MB = 1024 * 1024
AVISO_MB = 800    # desde aquí, una línea de aviso en el registro
PARADA_MB = 950   # desde aquí no se sube: Pages no admite sitios de más de 1024 MB
RAMA = "web"
AUTOR = {"GIT_AUTHOR_NAME": "GitHub Actions", "GIT_AUTHOR_EMAIL": "actions@github.com",
         "GIT_COMMITTER_NAME": "GitHub Actions", "GIT_COMMITTER_EMAIL": "actions@github.com"}
_DATO_RE = re.compile(r"data-[^/]*\.js")


class RamaWebError(Exception):
    """La rama web no se puede poner al día (su árbol no tiene lo que la web necesita, o el push no pasa)."""


def es_web(ruta: str) -> bool:
    """¿Va `ruta` (relativa a la raíz, con «/») en la rama web?"""
    if ruta in WEB_FICHEROS:
        return True
    if any(ruta.startswith(carpeta) for carpeta in WEB_CARPETAS):
        return True
    return "/" not in ruta and _DATO_RE.fullmatch(ruta) is not None


def _git(repo, *args, env=None, entrada=None, binario=False):
    hecho = subprocess.run(["git", *args], cwd=repo, input=entrada, capture_output=True,
                           env={**os.environ, **(env or {})}, text=not binario)
    if hecho.returncode != 0:
        error = hecho.stderr.decode("utf-8", "replace") if binario else hecho.stderr
        raise RamaWebError(f"git {' '.join(args[:2])}: {error.strip()}")
    return hecho.stdout


def _entradas(repo, objeto):
    """[(modo, tipo, sha, bytes, ruta)] de todo el árbol de `objeto` (git ls-tree -r -z -l)."""
    salida = _git(repo, "ls-tree", "-r", "-z", "-l", objeto)
    entradas = []
    for linea in salida.split("\0"):
        if not linea:
            continue
        cabeza, ruta = linea.split("\t", 1)
        modo, tipo, sha, tam = cabeza.split()
        entradas.append((modo, tipo, sha, int(tam) if tam.isdigit() else 0, ruta))
    return entradas


def arbol_web(commit: str, repo: Path = ROOT) -> tuple[str, int]:
    """(sha del árbol, bytes): el árbol con lo de la web de `commit`, mismos modos y blobs, escrito con un índice
    temporal (el del repositorio y el árbol de trabajo no se tocan)."""
    elegidas = [e for e in _entradas(repo, f"{commit}^{{tree}}") if es_web(e[4])]
    with tempfile.TemporaryDirectory(prefix="rama-web-") as carpeta:
        indice = {"GIT_INDEX_FILE": str(Path(carpeta) / "index")}
        info = "".join(f"{modo} {sha}\t{ruta}\0" for modo, _, sha, _, ruta in elegidas)
        _git(repo, "update-index", "--add", "-z", "--index-info", env=indice, entrada=info)
        arbol = _git(repo, "write-tree", env=indice).strip()
    return arbol, sum(e[3] for e in elegidas)


def _leer(repo, arbol, ruta):
    hecho = subprocess.run(["git", "cat-file", "blob", f"{arbol}:{ruta}"], cwd=repo, capture_output=True)
    return hecho.stdout.decode("utf-8") if hecho.returncode == 0 else None


def comprobar_arbol(arbol: str, repo: Path = ROOT) -> list[str]:
    """Lo que le falta al árbol `arbol` para que la web funcione: cada entrada del precache de su sw.js, el app,
    el css y los externos de dist/origen.json, los iconos de manifest.json, los data-*.js de los <script defer>
    de index.html y .nojekyll; y su tamaño, desde PARADA_MB. Vacía si no falta nada."""
    entradas = _entradas(repo, arbol)
    hay = {e[4] for e in entradas}
    faltan = []

    def pide(ruta, quien):
        if ruta not in hay:
            faltan.append(f"falta {ruta} ({quien})")

    pide(".nojekyll", "sin él, Pages pasaría la web por Jekyll")
    sw = _leer(repo, arbol, "sw.js")
    tramo = precache.tramo(sw) if sw is not None else None
    if tramo is None:
        faltan.append("sw.js no está o no lleva el bloque del precache")
    else:
        bloque = sw[tramo[0]:tramo[1]]
        rutas = precache.ENTRADA_RE.findall(bloque)
        if not rutas:
            faltan.append("el bloque del precache de sw.js está vacío")
        for ruta, _ in rutas:
            pide(ruta, "el precache de sw.js")
    origen = _leer(repo, arbol, "dist/origen.json")
    try:
        origen = json.loads(origen) if origen is not None else None
    except ValueError:
        origen = None
    if not isinstance(origen, dict):
        faltan.append("dist/origen.json no está o no se entiende")
    else:
        for ruta in [origen.get("app"), origen.get("css"), *(origen.get("externos") or [])]:
            if isinstance(ruta, str):
                pide(ruta, "dist/origen.json")
            else:
                faltan.append("dist/origen.json sin app o sin css")
    manifiesto = _leer(repo, arbol, "manifest.json")
    try:
        iconos = (json.loads(manifiesto) or {}).get("icons") if manifiesto is not None else None
    except ValueError:
        iconos = None
    if not isinstance(iconos, list):
        faltan.append("manifest.json no está o no tiene iconos")
    else:
        for icono in iconos:
            src = icono.get("src") if isinstance(icono, dict) else None
            if isinstance(src, str):
                pide(src.removeprefix("./"), "los iconos de manifest.json")
    index = _leer(repo, arbol, "index.html")
    if index is None:
        faltan.append("falta index.html")
    else:
        for ruta in precache.datos_inmediatos(index):
            pide(ruta, "un <script defer> de index.html")
    total = sum(e[3] for e in entradas)
    if total >= PARADA_MB * MB:
        faltan.append(f"la web ocupa {total // MB} MB y Pages no admite sitios de más de 1024 (aquí se para desde "
                      f"{PARADA_MB})")
    return faltan


def _existe_web(repo, remoto):
    hecho = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", remoto, f"refs/heads/{RAMA}"], cwd=repo,
                           capture_output=True, text=True)
    if hecho.returncode == 2:
        return False
    if hecho.returncode != 0:
        raise RamaWebError(f"git ls-remote {remoto}: {hecho.stderr.strip()}")
    return True


def _traer(repo, remoto):
    """Un solo fetch de main y, si existe, de web: las dos puntas, del mismo instante. (main, web o None). Con
    --depth=1 solo si el clon ya es superficial (el del runner): en un clon entero lo dejaría superficial."""
    con_web = _existe_web(repo, remoto)
    specs = [f"+refs/heads/main:refs/remotes/{remoto}/main"]
    if con_web:
        specs.append(f"+refs/heads/{RAMA}:refs/remotes/{remoto}/{RAMA}")
    superficial = _git(repo, "rev-parse", "--is-shallow-repository").strip() == "true"
    _git(repo, "fetch", "--no-tags", *(["--depth=1"] if superficial else []), remoto, *specs)
    main = _git(repo, "rev-parse", f"refs/remotes/{remoto}/main").strip()
    web = _git(repo, "rev-parse", f"refs/remotes/{remoto}/{RAMA}").strip() if con_web else None
    return main, web


def publicar(repo: Path = ROOT, remoto: str = "origin", intentos: int = 3,
             _antes_de_subir: Callable[[], None] | None = None) -> str | None:
    """Pone al día la rama web del remoto con la main del remoto. Devuelve el commit subido, o None si ya estaba
    al día. RamaWebError si al árbol le falta algo (no se sube nada) o si el push no pasa en `intentos`."""
    for intento in range(1, intentos + 1):
        main, web = _traer(repo, remoto)
        arbol, total = arbol_web(main, repo)
        faltan = comprobar_arbol(arbol, repo)
        if faltan:
            raise RamaWebError("la rama web no se publica: " + "; ".join(faltan))
        if total >= AVISO_MB * MB:
            print(f"Aviso: la web ocupa {total // MB} MB; Pages no admite más de 1024 y aquí se para desde {PARADA_MB}.")
        if web is not None and _git(repo, "rev-parse", f"{web}^{{tree}}").strip() == arbol:
            print(f"La rama web ya está al día con main {main[:12]}.")
            return None
        padre = ["-p", web] if web is not None else []
        commit = _git(repo, "commit-tree", arbol, *padre, "-m", f"Web de main {main[:12]}", env=AUTOR).strip()
        if _antes_de_subir is not None:
            _antes_de_subir()
        hecho = subprocess.run(["git", "push", remoto, f"{commit}:refs/heads/{RAMA}"], cwd=repo, capture_output=True,
                               text=True)
        if hecho.returncode == 0:
            print(f"Rama web al día: {commit[:12]} (main {main[:12]}, {total / MB:.0f} MB).")
            return commit
        # Rechazado: otro la ha puesto al día entretanto (o main se ha movido). Otra vez desde el fetch.
        print(f"La rama web no subió (intento {intento} de {intentos}): {hecho.stderr.strip()}")
    raise RamaWebError(f"la rama web no se pudo subir en {intentos} intentos")


def sitio(url: str) -> list[str]:
    """Para el director, tras cambiar Pages: cada entrada del precache del sw.js publicado en `url`, pedida como la
    pide el SW (<url><ruta>?h=<huella>), con el SHA-1 de su cuerpo contra su huella. Lo que no casa o no responde
    200; vacía si todo está bien."""
    base = url if url.endswith("/") else url + "/"

    def pedir(ruta):
        with urllib.request.urlopen(base + ruta, timeout=30) as respuesta:
            return respuesta.status, respuesta.read()

    try:
        estado, cuerpo = pedir("sw.js")
    except (urllib.error.URLError, OSError) as error:
        return [f"sw.js: {error}"]
    sw = cuerpo.decode("utf-8", "replace")
    tramo = precache.tramo(sw)
    if estado != 200 or tramo is None:
        return [f"sw.js: {estado}, sin el bloque del precache" if estado == 200 else f"sw.js: {estado}"]
    mal = []
    for ruta, huella in precache.ENTRADA_RE.findall(sw[tramo[0]:tramo[1]]):
        try:
            estado, cuerpo = pedir(f"{ruta}?h={huella}")
        except urllib.error.HTTPError as error:
            mal.append(f"{ruta}: {error.code}")
            continue
        except (urllib.error.URLError, OSError) as error:
            mal.append(f"{ruta}: {error}")
            continue
        if estado != 200:
            mal.append(f"{ruta}: {estado}")
        elif hashlib.sha1(cuerpo).hexdigest()[:8] != huella:
            mal.append(f"{ruta}: el precache dice {huella} y el sitio sirve {hashlib.sha1(cuerpo).hexdigest()[:8]}")
    return mal


def main(argv=None):
    parser = argparse.ArgumentParser(description="La rama web: lo que publica GitHub Pages.")
    ordenes = parser.add_subparsers(dest="orden")
    ordenes.add_parser("publicar", help="pone al día la rama web del remoto origin")
    a = ordenes.add_parser("arbol", help="el árbol de la web de un commit y su tamaño")
    a.add_argument("--commit", default="HEAD")
    s = ordenes.add_parser("sitio", help="comprueba el precache del sitio publicado")
    s.add_argument("url")
    try:
        args = parser.parse_args(argv)
    except SystemExit as salida:
        return salida.code if isinstance(salida.code, int) else 2
    try:
        if args.orden == "publicar":
            publicar()
            return 0
        if args.orden == "arbol":
            arbol, total = arbol_web(args.commit)
            print(arbol)
            print(f"{total / MB:.1f} MB", file=sys.stderr)
            faltan = comprobar_arbol(arbol)
            for motivo in faltan:
                print(motivo, file=sys.stderr)
            return 1 if faltan else 0
        if args.orden == "sitio":
            mal = sitio(args.url)
            for motivo in mal:
                print(motivo)
            return 1 if mal else 0
    except RamaWebError as error:
        print(error, file=sys.stderr)
        return 1
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
