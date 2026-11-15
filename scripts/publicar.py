#!/usr/bin/env python3
"""La subida de versión de una publicación del rediseño (spec §5.5; Plan B4, decisión 10).

Cada fase se publica al terminarla (docs/rediseno-rebase.md). La publicación, en este orden: empaqueta el
código en dist/ (scripts/codigo.py, que necesita esbuild: npm ci --prefix scripts/empaquetar; sin él, se
para sin escribir nada); sube a la vez todas las ?v= de index.html y CACHE_NAME de sw.js, con la misma
cadena, para que los móviles con la app instalada cambien a la versión nueva; y reescribe el manifiesto
del precache de sw.js (scripts/precache.py), con las huellas de lo que ya ha quedado escrito. No toca
«Última actualización»: es la fecha de los datos, la escribe el bot y source_health la publica como
lastDataChange. Las marcas las reescribe bump_cache_version, la misma función del bot, con
touch_footer=False.

La versión es la fecha UTC, como la del bot (date.today() en el runner de GitHub: con la de Canarias,
entre las 00:00 y la 01:00 se podía repetir o hacer retroceder una CACHE_NAME), y estrictamente mayor
que la vigente, la primera ?v= de index.html. Si no lo es (la del día ya está publicada, o la vigente
es de un día posterior), la letra siguiente de la vigente: 20260925 → 20260925b → 20260925c. Se para
sin escribir nada si la vigente ya lleva la z.

Uso, desde la raíz del repositorio:
  python3 scripts/publicar.py    # dist/, las ?v= y CACHE_NAME de index.html y sw.js, y el precache
"""
import argparse
import contextlib
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codigo  # noqa: E402
import generate_js  # noqa: E402
import precache  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"\?v=(\d{8}[a-z]?)")
FOOTER_RE = re.compile(r"Última actualización: \d{2}/\d{2}/\d{4}")
CACHE_LINE_RE = re.compile(r"^const CACHE_NAME = 'futbolbase2-v([0-9a-z]+)';$")


def next_publish_version(current, today_utc):
    """La versión de una publicación: `today_utc` (AAAAMMDD) si es mayor que `current`, la vigente; si
    no, la letra siguiente de `current`. En estas cadenas, el orden alfabético es el de las versiones.
    ValueError si `current` ya lleva la z o si alguna no tiene la forma del bot."""
    found = re.fullmatch(r"(\d{8})([a-z]?)", current)
    if not found or not re.fullmatch(r"\d{8}", today_utc):
        raise ValueError(f"versiones sin la forma del bot: {current!r} y {today_utc!r}")
    if today_utc > current:
        return today_utc
    day, letter = found.groups()
    if letter == "z":
        raise ValueError(f"la versión {current} ya no admite otra letra")
    return day + (chr(ord(letter) + 1) if letter else "b")


def _today_utc():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sube las ?v= y CACHE_NAME de una publicación y empaqueta dist/, sin tocar «Última actualización».")
    parser.add_argument("--root", default=str(ROOT), help="la raíz del árbol (por defecto, la del repositorio)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    index = (root / "index.html").read_text(encoding="utf-8")
    sw = (root / "sw.js").read_text(encoding="utf-8")
    marks = VERSION_RE.findall(index)
    footer = FOOTER_RE.findall(index)
    cache_line = CACHE_LINE_RE.match(sw.split("\n", 1)[0])
    if not marks or len(footer) != 1 or not cache_line or precache.tramo(sw) is None:
        print("index.html y sw.js tienen que llevar sus marcas: las ?v=, un «Última actualización», CACHE_NAME "
              "en la línea 1 de sw.js y el bloque del precache: nada escrito")
        return 1
    if len(set(marks)) != 1 or cache_line.group(1) != marks[0]:
        print(f"las ?v= de index.html tienen que ir todas iguales y coincidir con el CACHE_NAME de sw.js "
              f"({sorted(set(marks))} vs. futbolbase2-v{cache_line.group(1)}): nada escrito")
        return 1
    current = marks[0]
    try:
        version = next_publish_version(current, _today_utc())
    except ValueError as error:
        print(f"{error}: nada escrito")
        return 1
    # Sin poder empaquetar, la versión subiría con el código de antes; sin un obligatorio del precache, el SW
    # no se instalaría: se para antes de escribir.
    why = codigo.puede_empaquetar(root)
    if why:
        print(f"{why}: nada escrito")
        return 1
    try:
        precache.entradas(root)
    except (OSError, ValueError, KeyError) as error:
        print(f"el precache no se puede calcular ({error}): nada escrito")
        return 1
    if codigo.main(["--root", str(root)]) != 0:
        return 1
    # Las mismas expresiones que el bot; sus avisos por línea sobran aquí, que lo resume en una.
    with contextlib.redirect_stdout(io.StringIO()):
        generate_js.bump_cache_version(str(root), touch_footer=False, version=version)
    index = (root / "index.html").read_text(encoding="utf-8")
    first = (root / "sw.js").read_text(encoding="utf-8").split("\n", 1)[0]
    assert VERSION_RE.findall(index) == [version] * len(marks), "alguna ?v= no subió"
    assert FOOTER_RE.findall(index) == footer, "el pie cambió"
    assert first == f"const CACHE_NAME = 'futbolbase2-v{version}';", first
    print(f"versión {version} (antes, {current}): {len(marks)} ?v= en index.html y futbolbase2-v{version} en sw.js; "
          f"«{footer[0]}», sin tocar")
    # El último: las huellas de index.html, ya subido, y del paquete nuevo.
    with contextlib.redirect_stdout(io.StringIO()):
        precache.escribir(root)
    entries, opcionales = precache.entradas(root)
    print(f"precache: {len(entries)} ficheros, {len(opcionales)} opcionales, en sw.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
