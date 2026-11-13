"""De dónde sale la base: un espejo completo del repositorio de cada origen y la extracción de ficheros de él."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from .rutas import raiz

# El nombre acaba siendo una carpeta: sin barras, puntos ni comodines no se sale de repos/ ni se confunde con otro.
_NOMBRE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
# Los repositorios son públicos: git no debe enviar credenciales guardadas ni quedarse esperando a que alguien teclee.
_SIN_CREDENCIALES = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}


class FuenteError(Exception):
    """No se pudo traer el repositorio de un origen o sacar de él lo pedido."""


@dataclass(frozen=True)
class Origen:
    nombre: str
    repo: str
    rama: str
    base: str


def cargar_origenes(ruta: Path) -> list[Origen]:
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        origenes = [Origen(nombre, d["repo"], d["rama"], d["base"]) for nombre, d in datos.items()]
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as e:
        raise FuenteError(f"{ruta}: no se pueden leer los orígenes ({type(e).__name__}: {e})") from e
    for o in origenes:
        if not _NOMBRE.fullmatch(o.nombre) or not all(isinstance(v, str) and v for v in (o.repo, o.rama, o.base)):
            raise FuenteError(f"{ruta}: el origen {o.nombre!r} no es válido")
    return origenes


def actualizar_espejo(origen: Origen, ahora: datetime) -> str:
    espejo = _espejo(origen)
    if espejo.is_dir():
        # Sin podar, aunque la configuración de git lo pida: lo que el remoto borre o reescriba se queda aquí. La rama va
        # pedida aparte para que el fetch falle si el remoto la ha perdido, en vez de dar por buena la que ya teníamos.
        _git(espejo, "fetch", "--quiet", "--no-prune", "--", origen.repo, "+refs/*:refs/*", f"refs/heads/{origen.rama}")
    else:
        _clonar(origen, espejo)
    sha = _punta(espejo, origen)
    # Una referencia por día mantiene alcanzable cada estado de la rama aunque el remoto reescriba su historial.
    _git(espejo, "update-ref", f"refs/copia/{origen.rama}/{ahora.astimezone(timezone.utc):%Y%m%d}", sha)
    return sha


def extraer_base(origen: Origen, commit: str, destino: Path) -> Path:
    return extraer_fichero(origen, origen.base, destino, commit)


def extraer_fichero(origen: Origen, ruta: str, destino: Path, commit: str | None = None) -> Path:
    espejo = _espejo(origen)
    if not espejo.is_dir():
        raise FuenteError(f"todavía no hay espejo de {origen.nombre} en {espejo}")
    revision = f"refs/heads/{origen.rama}" if commit is None else commit
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nombre = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent)
    temporal = Path(nombre)
    try:
        # La base son unos 40 MB: va de git al fichero sin pasar por la memoria.
        with os.fdopen(fd, "wb") as salida:
            try:
                _git(espejo, "cat-file", "blob", f"{revision}:{ruta}", salida=salida)
            except FuenteError as e:
                raise FuenteError(f"no se puede sacar {ruta} de {revision}: {e}") from e
            os.fsync(salida.fileno())
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return destino


def _espejo(origen: Origen) -> Path:
    if not _NOMBRE.fullmatch(origen.nombre):
        raise FuenteError(f"el nombre de origen {origen.nombre!r} no sirve como carpeta")
    return raiz() / "repos" / f"{origen.nombre}.git"


def _clonar(origen: Origen, espejo: Path) -> None:
    repos = espejo.parent
    repos.mkdir(mode=0o700, exist_ok=True)
    prefijo = f".{espejo.name}."
    # Un clon cortado a medias (el temporizador lo mata, un apagón) no llegó a borrar su temporal.
    for resto in repos.iterdir():
        if resto.name.startswith(prefijo) and resto.name.endswith(".tmp"):
            shutil.rmtree(resto, ignore_errors=True)
    temporal = Path(tempfile.mkdtemp(prefix=prefijo, suffix=".tmp", dir=repos))
    try:
        _git(repos, "clone", "--mirror", "--quiet", "--", origen.repo, str(temporal))
        _punta(temporal, origen)
        # Que ningún gc borre nunca un objeto, aunque se quede sin referencia (otra rama reescrita en el remoto).
        _git(temporal, "config", "gc.pruneExpire", "never")
        os.rename(temporal, espejo)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise


def _punta(repo: Path, origen: Origen) -> str:
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{origen.rama}^{{commit}}")
    except FuenteError:
        raise FuenteError(f"el repositorio de {origen.nombre} no tiene la rama {origen.rama}") from None


def _git(carpeta: Path, *args: str, salida: BinaryIO | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", "-c", "credential.helper=", "-C", str(carpeta), *args],
            env={**os.environ, **_SIN_CREDENCIALES},
            stdout=subprocess.PIPE if salida is None else salida,
            stderr=subprocess.PIPE,
        )
    except OSError as e:
        raise FuenteError(f"no se puede ejecutar git: {e}") from e
    if r.returncode:
        detalle = "; ".join(linea.strip() for linea in r.stderr.decode(errors="replace").splitlines() if linea.strip())
        raise FuenteError(f"git {args[0]}: {detalle or f'código {r.returncode}'}")
    return "" if salida is not None else r.stdout.decode(errors="replace").strip()
