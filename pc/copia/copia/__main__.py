"""La orden: una pasada, el estado, las versiones guardadas, restaurar una y sacar un fichero original."""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from . import almacen
from .ejecutar import ejecutar, estado
from .fuentes import FuenteError, Origen, cargar_origenes, extraer_fichero
from .rutas import raiz

_SELLO = "%Y%m%d-%H%M%S"


class _Fallo(Exception):
    """Un fallo previsto: se dice en una línea y la orden acaba con código 1, sin traza."""


def main(argv: Sequence[str] | None = None) -> int:
    args = _analizador().parse_args(argv)
    try:
        return args.orden(args, datetime.now(timezone.utc))
    except _Fallo as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _ejecutar(args: argparse.Namespace, ahora: datetime) -> int:
    origenes = _origenes()
    for nombre in args.aceptar_mengua:
        # Una errata en el nombre no puede dejar la base en cuarentena creyendo que se ha aceptado.
        _origen(origenes, nombre)
    return ejecutar(origenes, ahora, set(args.aceptar_mengua))


def _estado(args: argparse.Namespace, ahora: datetime) -> int:
    texto, codigo = estado(ahora)
    print(texto)
    return codigo


def _versiones(args: argparse.Namespace, ahora: datetime) -> int:
    lista = almacen.versiones(args.origen)
    if not lista:
        raise _Fallo(f"no hay ninguna versión de {args.origen}")
    for v in lista:
        print(f"{v.momento:{_SELLO}}  matches {v.recuentos.get('matches')}  players {v.recuentos.get('players')}  {v.ruta}")
    return 0


def _restaurar(args: argparse.Namespace, ahora: datetime) -> int:
    # Las versiones se leen de la copia, no de origenes.json: así se restaura aunque ese fichero falte o esté mal.
    try:
        final = almacen.restaurar(args.origen, args.destino, args.momento)
    except almacen.CopiaDanada as e:
        raise _Fallo(f"{e} (`versiones {args.origen}` lista otras para elegir con --momento)") from None
    except (LookupError, ValueError, OSError) as e:
        raise _Fallo(str(e)) from None
    print(final)
    return 0


def _extraer(args: argparse.Namespace, ahora: datetime) -> int:
    origen = _origen(_origenes(), args.origen)
    copias = raiz()
    # La carpeta de las copias solo la escribe la pasada: un fichero extraído podría pisar la actual o una versión.
    if Path(args.destino).resolve().is_relative_to(copias.resolve()):
        raise _Fallo(f"no se extrae dentro de {copias}: elige un destino fuera de esa carpeta")
    try:
        final = extraer_fichero(origen, args.ruta, args.destino)
    except (FuenteError, OSError) as e:
        raise _Fallo(str(e)) from None
    print(final)
    return 0


def _ruta_origenes() -> Path:
    valor = os.environ.get("FB_COPIA_ORIGENES")
    # Instalado, origenes.json va junto a la carpeta del paquete.
    return Path(valor) if valor else Path(__file__).parent.parent / "origenes.json"


def _origenes() -> list[Origen]:
    try:
        return cargar_origenes(_ruta_origenes())
    except FuenteError as e:
        raise _Fallo(str(e)) from None


def _origen(origenes: Sequence[Origen], nombre: str) -> Origen:
    for o in origenes:
        if o.nombre == nombre:
            return o
    raise _Fallo(f"origen desconocido: {nombre} (los de {_ruta_origenes()} son: {', '.join(o.nombre for o in origenes)})")


def _momento(texto: str) -> datetime:
    try:
        # En UTC, como los nombres de las versiones: restaurar busca ese momento exacto.
        return datetime.strptime(texto, _SELLO).replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"«{texto}» no es AAAAMMDD-HHMMSS") from None


def _analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="futbol-base-copia", description="Copia de seguridad en el PC de la base de fútbol base."
    )
    ordenes = analizador.add_subparsers(required=True, metavar="ORDEN")

    p = ordenes.add_parser("ejecutar", help="una pasada por todos los orígenes")
    p.add_argument("--aceptar-mengua", action="append", default=[], metavar="ORIGEN",
                   help="acepta la base de ORIGEN que se apartó, o una prácticamente igual (se puede repetir)")
    p.set_defaults(orden=_ejecutar)

    p = ordenes.add_parser("estado", help="cómo fue la última pasada de cada origen")
    p.set_defaults(orden=_estado)

    p = ordenes.add_parser("versiones", help="las versiones guardadas de un origen")
    p.add_argument("origen", metavar="ORIGEN")
    p.set_defaults(orden=_versiones)

    p = ordenes.add_parser("restaurar", help="descomprime una versión, comprobada, en DESTINO")
    p.add_argument("origen", metavar="ORIGEN")
    p.add_argument("destino", metavar="DESTINO", type=Path)
    p.add_argument("--momento", type=_momento, metavar="AAAAMMDD-HHMMSS", help="la de ese momento (UTC); si no, la última")
    p.set_defaults(orden=_restaurar)

    p = ordenes.add_parser("extraer", help="saca un fichero del repositorio, tal como estaba en la última pasada")
    p.add_argument("origen", metavar="ORIGEN")
    p.add_argument("ruta", metavar="RUTA")
    p.add_argument("destino", metavar="DESTINO", type=Path)
    p.set_defaults(orden=_extraer)
    return analizador


if __name__ == "__main__":
    sys.exit(main())
