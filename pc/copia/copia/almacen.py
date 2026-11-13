"""Dónde y cómo se guardan las bases: versiones comprimidas, la actual, la cuarentena y la restauración."""

import hashlib
import json
import lzma
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .rutas import raiz
from .verificar import comprobar

PRESET = 6
CONSERVAR_CUARENTENA = 10
_BLOQUE = 1 << 20
_SELLO = "%Y%m%d-%H%M%S"
_NOMBRE = re.compile(r"futbolbase-(\d{8}-\d{6})\.db\.xz")


class CopiaDanada(Exception):
    """La copia guardada no devuelve la base que se guardó."""


@dataclass(frozen=True)
class Version:
    origen: str
    momento: datetime
    ruta: Path
    sha256: str
    recuentos: dict[str, int]


def versiones(origen: str) -> list[Version]:
    lista = []
    for xz in (raiz() / "versiones" / origen).glob("*/futbolbase-*.db.xz"):
        momento = _momento(xz)
        # Sin su .json la versión no llegó a guardarse entera.
        if momento is None or not _ficha(xz).is_file():
            continue
        datos = json.loads(_ficha(xz).read_text(encoding="utf-8"))
        lista.append(Version(origen, momento, xz, datos["sha256"], datos["recuentos"]))
    return sorted(lista, key=lambda v: v.momento)


def aceptar(origen: str, db: Path, recuentos: Mapping[str, int], ahora: datetime) -> Version | None:
    huella = _huella(db)
    actual = raiz() / "actual" / origen / "futbolbase.db"
    previas = versiones(origen)
    if previas and previas[-1].sha256 == huella:
        if not actual.is_file() or _huella(actual) != huella:
            _copiar(db, actual)
        return None
    momento = _en_utc(ahora)
    xz = raiz() / "versiones" / origen / f"{momento:%Y}" / f"futbolbase-{momento:{_SELLO}}.db.xz"
    ficha = {"sha256": huella, "bytes": db.stat().st_size, "recuentos": dict(recuentos)}
    _guardar(db, xz, _ficha(xz), json.dumps(ficha, ensure_ascii=False, indent=2) + "\n")
    # La actual se toca la última: si algo falla antes, sigue siendo la buena anterior.
    _copiar(db, actual)
    return Version(origen, momento, xz, huella, dict(recuentos))


def apartar(origen: str, db: Path, motivos: Sequence[str], ahora: datetime) -> Path:
    huella = _huella(db)
    carpeta = raiz() / "cuarentena" / origen
    # La misma base rechazada día tras día se guarda una sola vez.
    for xz in _apartadas(carpeta):
        if _huella_apartada(xz) == huella:
            return xz
    momento = _en_utc(ahora)
    xz = carpeta / f"futbolbase-{momento:{_SELLO}}.db.xz"
    lineas = [huella, *(" ".join(str(m).splitlines()) for m in motivos)]
    _guardar(db, xz, _motivo(xz), "\n".join(lineas) + "\n")
    for vieja in _apartadas(carpeta)[:-CONSERVAR_CUARENTENA]:
        _motivo(vieja).unlink(missing_ok=True)
        vieja.unlink()
    return xz


def restaurar(origen: str, destino: Path, momento: datetime | None = None) -> Path:
    destino = Path(destino)
    prohibida = raiz() / "actual"
    # La actual solo la escribe aceptar, con una base ya comprobada.
    if destino.resolve().is_relative_to(prohibida.resolve()):
        raise ValueError(f"no se restaura dentro de {prohibida}")
    candidatas = [v for v in versiones(origen) if momento is None or v.momento == momento]
    if not candidatas:
        cuando = "" if momento is None else f" del {momento.isoformat()}"
        raise LookupError(f"no hay ninguna versión de {origen}{cuando}")
    v = candidatas[-1]
    final = destino / f"futbolbase-{v.momento:{_SELLO}}.db"
    with _atomico(final) as temporal:
        huella = hashlib.sha256()
        try:
            with lzma.open(v.ruta) as entrada, temporal.open("wb") as salida:
                while bloque := entrada.read(_BLOQUE):
                    huella.update(bloque)
                    salida.write(bloque)
        except (lzma.LZMAError, EOFError) as e:
            raise CopiaDanada(f"{v.ruta}: no se puede descomprimir ({e})") from e
        if huella.hexdigest() != v.sha256:
            raise CopiaDanada(f"{v.ruta}: la huella no coincide con la guardada")
        r = comprobar(temporal)
        if not r.ok:
            raise CopiaDanada(f"{v.ruta}: " + "; ".join(r.motivos))
    return final


def _en_utc(momento: datetime) -> datetime:
    # El nombre del fichero solo guarda segundos: el momento devuelto tiene que ser el que luego se lee de él.
    return momento.astimezone(timezone.utc).replace(microsecond=0)


def _momento(xz: Path) -> datetime | None:
    encontrado = _NOMBRE.fullmatch(xz.name)
    if not encontrado:
        return None
    try:
        return datetime.strptime(encontrado[1], _SELLO).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _ficha(xz: Path) -> Path:
    return xz.with_name(xz.name.removesuffix(".xz") + ".json")


def _motivo(xz: Path) -> Path:
    return xz.with_name(xz.name.removesuffix(".xz") + ".motivo.txt")


def _apartadas(carpeta: Path) -> list[Path]:
    return sorted((xz for xz in carpeta.glob("futbolbase-*.db.xz") if _momento(xz)), key=_momento)


def _huella_apartada(xz: Path) -> str | None:
    try:
        with _motivo(xz).open(encoding="utf-8") as f:
            return f.readline().strip()
    except FileNotFoundError:
        return None


def _huella(ruta: Path) -> str:
    with ruta.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _guardar(db: Path, xz: Path, ficha: Path, texto: str) -> None:
    with _atomico(xz) as temporal:
        with db.open("rb") as entrada, lzma.open(temporal, "wb", preset=PRESET) as salida:
            shutil.copyfileobj(entrada, salida, _BLOQUE)
    try:
        with _atomico(ficha) as temporal:
            temporal.write_text(texto, encoding="utf-8")
    except BaseException:
        # Un .xz sin su ficha no cuenta como copia y nadie lo borraría después.
        xz.unlink(missing_ok=True)
        raise


def _copiar(db: Path, destino: Path) -> None:
    with _atomico(destino) as temporal:
        shutil.copyfile(db, temporal)


@contextmanager
def _atomico(destino: Path) -> Iterator[Path]:
    """Da un temporal junto a `destino` y, si todo va bien, lo pone en su sitio de una vez."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nombre = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent)
    os.close(fd)
    temporal = Path(nombre)
    try:
        yield temporal
        _sincronizar(temporal)
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    # Sin esto un apagón justo después podría deshacer el cambio de nombre.
    _sincronizar(destino.parent)


def _sincronizar(ruta: Path) -> None:
    fd = os.open(ruta, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
