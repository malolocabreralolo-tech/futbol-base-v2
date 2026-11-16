#!/usr/bin/env python3
"""¿Está entera la base que va a subir el bot? Va entre la lectura y las pruebas (update.yml y activar.yml,
paso «Base sana»): una base dañada no se sube nunca y la web lo dice (el paso de diagnóstico la marca en rojo).

Mira, por este orden:
  - que el WAL esté volcado al fichero principal: la base va en modo WAL dentro de git y el -wal no se sube
    (.gitignore), así que lo que se quedara en él se perdería; se vuelca (wal_checkpoint(TRUNCATE)) y se
    comprueba que no queda nada;
  - PRAGMA integrity_check (la entera, no quick_check: unos segundos con la base real);
  - que tenga alguna tabla: un fichero de 0 bytes o recién creado pasa integrity_check y borraría la web;
  - PRAGMA foreign_key_check;
  - el tamaño: desde AVISO_MB la web lo dice (data-health.json, `base`); desde PARADA_MB no se sube, porque
    GitHub rechaza ficheros de 100 MB y el push fallaría en cada pasada.

Uso, desde la raíz del repositorio:
  python3 scripts/base_sana.py [--db futbolbase.db] [--salud]
Imprime una línea por motivo y sale con 1 si la base no está bien. Con --salud y la base bien, además deja el
tamaño en data-health.json (source_health.set_base: con aviso, la clave `base`; sin él, fuera); con la base
mal no toca el informe: lo marca el paso de diagnóstico de update.yml.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import source_health
from source_health import GITHUB_MB, MB

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "futbolbase.db"
AVISO_MB = 80     # desde aquí, la web lo dice
PARADA_MB = 95    # desde aquí no se sube: GitHub rechaza ficheros de 100 MB


def _uri(db_path):
    """La URI de la base sin crearla si no existe (mode=rw): un fichero que falta es una base mala."""
    return Path(db_path).resolve().as_uri() + "?mode=rw"


def _integridad(error):
    return f"la base de datos no pasa la comprobación de integridad: {str(error)[:200]}"


def comprobar(db_path) -> dict:
    """{'ok': bool, 'motivos': [str], 'bytes': int, 'aviso': bool}. Vuelca el WAL al fichero
    (wal_checkpoint(TRUNCATE)), y mira: que no quede `-wal` con contenido, PRAGMA integrity_check,
    PRAGMA foreign_key_check, y el tamaño. Nunca lanza por una base mala: lo devuelve en `motivos`."""
    db_path = Path(db_path)
    motivos = []
    try:
        con = sqlite3.connect(_uri(db_path), uri=True)
    except sqlite3.Error as e:
        con, motivos = None, [_integridad(e)]
    if con is not None:
        try:
            # El volcado es lo único que escribe; las comprobaciones, con la conexión en solo lectura (query_only).
            # Con una sola conexión, al cerrarla SQLite borra el -wal y el -shm: no quedan sueltos en el árbol.
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            con.execute("PRAGMA query_only = ON")
            filas = con.execute("PRAGMA integrity_check").fetchall()
            if filas != [("ok",)]:
                motivos.append(_integridad(filas[0][0] if filas else "sin respuesta"))
            elif con.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] == 0:
                motivos.append("la base de datos está vacía")
            else:
                rotas = con.execute("PRAGMA foreign_key_check").fetchall()
                if rotas:
                    motivos.append(f"la base de datos tiene referencias rotas: {len(rotas)} filas")
        except sqlite3.Error as e:
            motivos.append(_integridad(e))
        finally:
            con.close()
    # Después de cerrar: con otra conexión abierta, TRUNCATE lo deja en 0 bytes; si no pudo volcarlo entero
    # (un lector que no suelta), queda contenido. Un -wal vacío o un -shm no son datos sin volcar.
    wal = Path(f"{db_path}-wal")
    if wal.exists() and wal.stat().st_size > 0:
        motivos.append("quedan datos sin volcar a la base (-wal)")
    size = db_path.stat().st_size if db_path.exists() else 0
    if size >= PARADA_MB * MB:
        motivos.append(f"la base de datos ocupa {size // MB} MB y GitHub no admite más de {GITHUB_MB}")
    return {"ok": not motivos, "motivos": motivos, "bytes": size, "aviso": size >= AVISO_MB * MB}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Comprueba la base antes de subirla.")
    parser.add_argument("--db", default=str(DB_PATH), help="la base (por defecto, futbolbase.db del repositorio)")
    parser.add_argument("--salud", action="store_true",
                        help="con la base bien, deja su tamaño en data-health.json (la clave base, desde AVISO_MB)")
    args = parser.parse_args(argv)
    r = comprobar(args.db)
    for motivo in r["motivos"]:
        print(motivo)
    if not r["ok"]:
        return 1
    print(f"Base sana: {r['bytes'] // MB} MB" + (f" (aviso desde {AVISO_MB} MB)" if r["aviso"] else "") + ".")
    if args.salud:
        source_health.set_base(r["bytes"], r["aviso"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
