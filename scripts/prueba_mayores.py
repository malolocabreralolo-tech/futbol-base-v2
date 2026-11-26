#!/usr/bin/env python3
"""prueba_mayores.py — La suite entera sobre la base «de después»: la que dejará el bot cuando el director haya
activado y leído infantil, cadete y juvenil (pasos D3-D5 de la parte E1).

Por qué. La puerta de pruebas del bot (update.yml, «Tests Python» y «Tests Node») corre DESPUÉS de sus pasos de
importación, sobre la base que acaba de escribir: una prueba «sobre la base real» que vale con la base de hoy y
no con la de después (que cuenta los grupos de la temporada en curso sin filtrar por las categorías de la web, o
compara los data-*.js con la base entera) deja al bot sin publicar en cuanto el director active infantil. Ya
pasó el 25/11 con otra base de después. Esto fabrica esa base sobre una copia y pasa sobre ella todo.

    python3 scripts/prueba_mayores.py [--categorias infantil,cadete,juvenil] [--islas] [--conservar] [--con-cambios]

  1. un árbol temporal del repositorio (git worktree add --detach <tmp>/despues HEAD); con --con-cambios, además
     los ficheros modificados o nuevos del árbol de trabajo (sin la base, base/ ni scripts/historico/), para
     probar antes de un commit;
  2. la base real del árbol, copiada con backup a su futbolbase.db;
  3. en ese árbol, con su código: base_mayores.poblar (las categorías de --categorias; con --islas, también el
     alevín de Lanzarote), una entrada «ok» en data-health.json por cada grupo nuevo (como la deja el bot),
     migrate_identidad.resolver_fichas, los enlaces de la liga de escuelas y generate_js.main();
  4. allí, python3 -m pytest scripts/tests/ y node --test scripts/tests/test_*.mjs.

Imprime el tamaño de la base antes y después, los segundos de cada paso y «verde» o «rojo» con lo que falló;
sale con 0 solo en verde. Borra el árbol temporal salvo con --conservar. Nunca toca el árbol de trabajo (ni su
base, ni sus data-*.js) ni pide nada a ninguna web.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Lo que --con-cambios no copia nunca: la base, sus copias y lo del carril del histórico.
_NO_SE_COPIA = re.compile(r"^(futbolbase\.db.*|base/.*|scripts/historico/.*|backups/.*)$")
_PASO_INTERNO = "--paso-interno"


def _mb(db):
    total = sum(p.stat().st_size for p in (Path(db), Path(f"{db}-wal")) if p.exists())
    return round(total / 1024 / 1024, 1)


def _cambios(raiz):
    """Los ficheros modificados o nuevos del árbol de trabajo (git status), sin los de _NO_SE_COPIA."""
    salida = subprocess.run(["git", "-C", str(raiz), "status", "--porcelain=v1", "-uall", "-z"],
                            capture_output=True, text=True, check=True).stdout
    out = []
    for entrada in salida.split("\0"):
        if len(entrada) < 4 or entrada[0] == "D" or entrada[1] == "D":
            continue
        ruta = entrada[3:]
        if not _NO_SE_COPIA.match(ruta) and (raiz / ruta).is_file():
            out.append(ruta)
    return sorted(out)


def paso_interno(categorias, islas):
    """Lo que se hace DENTRO del árbol temporal (con su código y su base): la base de después, las fichas y los
    data-*.js. Imprime una línea JSON con lo hecho y los segundos de cada parte."""
    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "scripts"))
    sys.path.insert(1, str(raiz / "scripts" / "tests"))
    import base_mayores
    from categorias import parse_categories
    from db import get_connection
    cats = parse_categories(categorias)
    t0 = time.monotonic()
    conn = get_connection()
    hecho = base_mayores.poblar(conn, categorias=cats, islas=islas, log=lambda *a: None)
    t_poblar = time.monotonic() - t0
    # data-health.json: una comprobación correcta por grupo nuevo, como la deja la pasada del carril.
    salud = raiz / "data-health.json"
    datos = json.loads(salud.read_text(encoding="utf-8")) if salud.exists() else {}
    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for code, url in conn.execute(
            f"SELECT code, url FROM groups WHERE code IN ({','.join('?' * len(hecho['grupos']))})", hecho["grupos"]):
        datos.setdefault("groups", {})[code] = {"url": url, "status": "ok", "message": "6 jornadas leídas",
                                                "checkedAt": ahora}
    salud.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Como el final de la pasada: las fichas, los enlaces de la liga de escuelas y los datos de la web.
    import enlace_mygol
    import migrate_identidad
    t1 = time.monotonic()
    migrate_identidad.resolver_fichas(conn, log=lambda *a: None)
    enlace_mygol.guardar_enlaces(conn, registro=lambda *a: None)
    conn.close()
    t_fichas = time.monotonic() - t1
    import generate_js
    import vista_web
    t2 = time.monotonic()
    # Lo que añade la copia filtrada a la pasada (vista_web.copia_web), medido aparte.
    medir = get_connection()
    t_copia0 = time.monotonic()
    copia = vista_web.copia_web(medir)
    t_copia = time.monotonic() - t_copia0
    if copia is not medir:
        copia.close()
    medir.close()
    with open(os.devnull, "w") as nada:
        stdout, sys.stdout = sys.stdout, nada
        try:
            generate_js.main()
        finally:
            sys.stdout = stdout
    t_generar = time.monotonic() - t2
    print(json.dumps({**hecho, "segundos": {"poblar": round(t_poblar, 1), "fichas": round(t_fichas, 1),
                                            "copia_web": round(t_copia, 2), "generar": round(t_generar, 1)}}))


def _fallos(texto):
    """Las pruebas que fallaron, de la salida de pytest (-q, «FAILED …» y «ERROR …») o de node --test."""
    out = re.findall(r"^(?:FAILED|ERROR) (\S+)", texto, re.M)
    out += [f"node: {m}" for m in re.findall(r"^not ok \d+ - (.+)$", texto, re.M)]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--categorias", default="infantil,cadete,juvenil")
    parser.add_argument("--islas", action="store_true", help="también el alevín de Lanzarote (el paso D6)")
    parser.add_argument("--conservar", action="store_true", help="no borrar el árbol temporal al acabar")
    parser.add_argument("--con-cambios", action="store_true",
                        help="copiar al árbol temporal los ficheros modificados o nuevos del árbol de trabajo")
    parser.add_argument(_PASO_INTERNO, action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.paso_interno:
        paso_interno(args.categorias, args.islas)
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="prueba-mayores-"))
    arbol = tmp / "despues"
    tiempos = {}
    verde = False
    try:
        t = time.monotonic()
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "-q", "--detach", str(arbol), "HEAD"], check=True)
        if args.con_cambios:
            copiados = _cambios(ROOT)
            for ruta in copiados:
                (arbol / ruta).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / ruta, arbol / ruta)
            print(f"Con los cambios del árbol de trabajo: {len(copiados)} ficheros")
        src = sqlite3.connect(f"file:{ROOT / 'futbolbase.db'}?mode=ro", uri=True)
        for sobra in (arbol / "futbolbase.db-wal", arbol / "futbolbase.db-shm"):
            sobra.unlink(missing_ok=True)
        dst = sqlite3.connect(str(arbol / "futbolbase.db"))
        src.backup(dst)
        dst.close()
        src.close()
        tiempos["árbol y copia de la base"] = time.monotonic() - t
        mb_antes = _mb(arbol / "futbolbase.db")

        t = time.monotonic()
        orden = [sys.executable, str(arbol / "scripts" / "prueba_mayores.py"), _PASO_INTERNO,
                 "--categorias", args.categorias] + (["--islas"] if args.islas else [])
        r = subprocess.run(orden, cwd=arbol, capture_output=True, text=True)
        tiempos["base de después, fichas y data-*.js"] = time.monotonic() - t
        if r.returncode != 0:
            print(r.stdout[-4000:] + r.stderr[-4000:])
            print("rojo: no se pudo fabricar la base de después")
            return 1
        hecho = json.loads(r.stdout.strip().splitlines()[-1])
        mb_despues = _mb(arbol / "futbolbase.db")
        print(f"Base de después: {len(hecho['grupos'])} grupos ({', '.join(hecho['grupos'])}), {hecho['partidos']} "
              f"partidos jugados, {hecho['actas']} actas, {hecho['jugadores_reutilizados']} niños de la base con su "
              f"id, {hecho['sin_id_reutilizados']} sin id con el mismo nombre y club (en la fila de otra categoría: "
              f"{hecho['sin_id_en_fila_ajena']})")
        print(f"La base: {mb_antes} MB antes, {mb_despues} MB después")
        print("Segundos dentro: " + ", ".join(f"{k} {v}" for k, v in hecho["segundos"].items()))

        t = time.monotonic()
        py = subprocess.run([sys.executable, "-m", "pytest", "scripts/tests/", "-q", "-p", "no:cacheprovider"],
                            cwd=arbol, capture_output=True, text=True)
        tiempos["pytest"] = time.monotonic() - t
        t = time.monotonic()
        mjs = sorted(str(p.relative_to(arbol)) for p in (arbol / "scripts" / "tests").glob("test_*.mjs"))
        nd = subprocess.run(["node", "--test", *mjs], cwd=arbol, capture_output=True, text=True)
        tiempos["node"] = time.monotonic() - t
        resumen_py = (py.stdout.strip().splitlines() or [""])[-1]
        resumen_node = " ".join(l.strip("# ") for l in nd.stdout.splitlines() if re.match(r"^# (pass|fail) ", l))
        print(f"pytest: {resumen_py}")
        print(f"node: {resumen_node}")
        print("Segundos: " + ", ".join(f"{k} {v:.0f}" for k, v in tiempos.items()))
        fallos = _fallos(py.stdout) + _fallos(nd.stdout)
        verde = py.returncode == 0 and nd.returncode == 0
        if verde:
            print("verde")
        else:
            print("rojo: " + ("; ".join(fallos) if fallos else "las pruebas no acabaron bien"))
            if args.conservar:
                (tmp / "pytest.txt").write_text(py.stdout + py.stderr, encoding="utf-8")
                (tmp / "node.txt").write_text(nd.stdout + nd.stderr, encoding="utf-8")
        return 0 if verde else 1
    finally:
        if args.conservar:
            print(f"Árbol conservado: {arbol}")
        else:
            subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(arbol)],
                           capture_output=True)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
