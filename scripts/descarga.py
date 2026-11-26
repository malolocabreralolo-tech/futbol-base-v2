#!/usr/bin/env python3
"""La base completa para descargar desde «Datos y fuentes»: un ZIP con futbolbase.db en una release fija de GitHub
(base-completa), fuera de git y de Pages.

Por qué. Hasta la parte D, «Datos y fuentes» enlazaba ./futbolbase.db, la de git, que Pages servía tal cual. Pero la
base pasa a guardarse en git partida en piezas (base/, docs/almacenamiento.md) y Pages deja de publicar lo que no es
la web (la rama web): ya no hay un fichero de la base que enlazar. Una release no tiene el límite de 100 MB por
fichero de git (admite hasta 2 GB) ni cuenta para el 1 GB de Pages. El ZIP es la base tal cual (con 45 MB, unos
13 en ZIP; con todas las actas, unos 85), y se rehace una vez al día: la primera pasada sana del día (UTC) del bot
(update.yml, «Base completa del día»). Su fecha y su tamaño van en data-health.json (`descarga`), que la web lee
para el botón.

Tres órdenes, desde la raíz del repositorio:
  python3 scripts/descarga.py toca               # sale con 0 si toca rehacerla hoy, con 1 si ya está
  python3 scripts/descarga.py preparar <zip> [--db F]
  python3 scripts/descarga.py apuntar <zip>      # descarga: {url, fecha, bytes} en data-health.json
Entre preparar y apuntar, el workflow la sube (gh release upload base-completa <zip> --clobber): si la subida
falla, no se apunta nada y la pasada siguiente lo vuelve a intentar.
"""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import source_health

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "futbolbase.db"
TAG = "base-completa"
ASSET = "futbolbase.zip"
URL = f"https://github.com/malolocabreralolo-tech/futbol-base-v2/releases/download/{TAG}/{ASSET}"
# Lo que se llama el fichero dentro del ZIP: el de siempre.
DENTRO = "futbolbase.db"


def _hoy(hoy=None) -> str:
    return (hoy or datetime.now(timezone.utc).date()).isoformat()


def toca(health_path: Path = source_health.REPORT_PATH, hoy: date | None = None) -> bool:
    """True si la descarga apuntada en el informe no es de hoy (UTC), o no hay ninguna que se entienda."""
    try:
        report = json.loads(Path(health_path).read_text())
    except (OSError, ValueError):
        return True
    descarga = report.get("descarga") if isinstance(report, dict) else None
    fecha = descarga.get("fecha") if isinstance(descarga, dict) else None
    return fecha != _hoy(hoy)


def preparar(db: Path, zip_path: Path) -> int:
    """El ZIP con una sola entrada, futbolbase.db (deflate, nivel 6), con la base tal como está. Devuelve sus bytes.

    La base no se escribe: se abre en solo lectura (lo que haya en su -wal también se lee) y se copia por páginas
    con la copia de SQLite (backup) a un temporal, que se pasa a modo DELETE: así se abre en cualquier sitio, también
    de solo lectura y sin -wal al lado. No VACUUM INTO: renumera los rowid de las tablas sin INTEGER PRIMARY KEY que
    no copia con su atajo (medido el 25/11/2026: fp_goals, de 13762… a 1…), y la descargada no sería la base. El ZIP
    se escribe en un temporal y se pone en su sitio al acabar: un corte no deja uno a medias."""
    db, zip_path = Path(db), Path(zip_path)
    if not db.is_file():
        raise FileNotFoundError(f"no está la base {db}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=zip_path.parent, prefix=".descarga-") as carpeta:
        copia = Path(carpeta) / DENTRO
        origen = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            destino = sqlite3.connect(copia)
            try:
                origen.backup(destino)
                modo = destino.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if modo != "delete":
                    raise sqlite3.DatabaseError(f"la copia no pasa a modo DELETE ({modo})")
                bien = destino.execute("PRAGMA quick_check").fetchone()[0]
                if bien != "ok":
                    raise sqlite3.DatabaseError(f"la copia no está entera: {bien}")
            finally:
                destino.close()
        finally:
            origen.close()
        temporal = Path(carpeta) / ASSET
        with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(copia, DENTRO)
        os.chmod(temporal, 0o644)
        os.replace(temporal, zip_path)
    return zip_path.stat().st_size


def apuntar(zip_path: Path, health_path: Path = source_health.REPORT_PATH, hoy: date | None = None) -> None:
    """`descarga: {"url", "fecha" (hoy, UTC), "bytes" (los del ZIP)}` en data-health.json, sin tocar nada más."""
    source_health.set_descarga({"url": URL, "fecha": _hoy(hoy), "bytes": Path(zip_path).stat().st_size}, health_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="La base completa para descargar (un ZIP al día).")
    ordenes = parser.add_subparsers(dest="orden")
    ordenes.add_parser("toca", help="sale con 0 si toca rehacerla hoy (UTC), con 1 si ya está")
    p = ordenes.add_parser("preparar", help="escribe el ZIP con la base")
    p.add_argument("zip")
    p.add_argument("--db", default=str(DB_PATH), help="la base (por defecto, futbolbase.db del repositorio)")
    a = ordenes.add_parser("apuntar", help="apunta el ZIP subido en data-health.json")
    a.add_argument("zip")
    try:
        args = parser.parse_args(argv)
    except SystemExit as salida:
        return salida.code if isinstance(salida.code, int) else 2
    if args.orden == "toca":
        return 0 if toca() else 1
    if args.orden == "preparar":
        n = preparar(Path(args.db), Path(args.zip))
        print(f"futbolbase.zip: {n / source_health.MB:.1f} MB")
        return 0
    if args.orden == "apuntar":
        apuntar(Path(args.zip))
        print(f"Apuntada la base completa de hoy: {URL}")
        return 0
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
