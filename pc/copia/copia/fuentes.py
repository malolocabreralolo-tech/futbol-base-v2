"""De dónde sale la base: un espejo completo del repositorio de cada origen y la extracción de ficheros de él."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from .rutas import raiz

# El nombre acaba siendo una carpeta: sin barras, puntos ni comodines no se sale de repos/ ni se confunde con otro.
_NOMBRE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
# Los repositorios son públicos: git no debe enviar credenciales guardadas ni quedarse esperando a que alguien teclee.
_SIN_CREDENCIALES = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}
# Heredadas de un hook de git o de un `rebase --exec`, harían que git leyese y escribiese en otro repositorio.
_DE_OTRO_REPOSITORIO = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE", "GIT_COMMON_DIR",
)
# Al traer: que gc --auto no se quede en segundo plano (systemd lo mataría a medias y con pruneExpire=never nadie
# limpia sus restos) y que una conexión colgada (menos de 1000 B/s durante 2 minutos) se corte en vez de esperar sin fin.
_AL_TRAER = ("gc.autoDetach=false", "http.lowSpeedLimit=1000", "http.lowSpeedTime=120")
# Solo ramas y etiquetas, cada una a su sitio: refs/copia/* es nuestro y el remoto no puede escribir en él.
_REFSPECS = ("+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")
# Por origen, lo que la última actualización del espejo no pudo traer sin que eso impidiera copiar la base.
_avisos: dict[str, list[str]] = {}


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
    if not origenes:
        # Una pasada sin nada que copiar acabaría bien y nadie se enteraría de que no se copia nada.
        raise FuenteError(f"{ruta}: no hay ningún origen")
    for o in origenes:
        if not _NOMBRE.fullmatch(o.nombre) or not all(isinstance(v, str) and v for v in (o.repo, o.rama, o.base)):
            raise FuenteError(f"{ruta}: el origen {o.nombre!r} no es válido")
    return origenes


def actualizar_espejo(origen: Origen, ahora: datetime) -> str:
    espejo = _espejo(origen)
    _avisos[origen.nombre] = []
    if espejo.is_dir():
        _traer(espejo, origen)
    else:
        _crear(origen, espejo)
    sha = _punta(espejo, origen)
    # Una referencia por día mantiene alcanzable cada estado de la rama aunque el remoto reescriba su historial.
    _fijar_copia(espejo, f"refs/copia/{origen.rama}/{ahora.astimezone(timezone.utc):%Y%m%d}", sha)
    return sha


def avisos_del_espejo(origen: Origen) -> list[str]:
    """Lo que la última actualización del espejo de este origen no pudo traer (otras ramas o etiquetas)."""
    return list(_avisos.get(origen.nombre, []))


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


def _crear(origen: Origen, espejo: Path) -> None:
    repos = espejo.parent
    repos.mkdir(mode=0o700, exist_ok=True)
    prefijo = f".{espejo.name}."
    # Una descarga cortada a medias (el temporizador la mata, un apagón) no llegó a borrar su temporal.
    for resto in repos.iterdir():
        if resto.name.startswith(prefijo) and resto.name.endswith(".tmp"):
            shutil.rmtree(resto, ignore_errors=True)
    temporal = Path(tempfile.mkdtemp(prefix=prefijo, suffix=".tmp", dir=repos))
    try:
        # Un repositorio vacío y el mismo fetch de cada día, no `clone --mirror`, que trae también el refs/copia/* del remoto.
        _git(None, "init", "--quiet", "--bare", f"--initial-branch={origen.rama}", str(temporal.absolute()))
        # Que ningún gc borre nunca un objeto, aunque se quede sin referencia (otra rama reescrita en el remoto).
        _git(temporal, "config", "gc.pruneExpire", "never")
        _traer(temporal, origen)
        os.rename(temporal, espejo)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise


def _traer(repo: Path, origen: Origen) -> None:
    # Sin podar, aunque la configuración de git lo pida: lo que el remoto borre o reescriba se queda aquí.
    # Primero la rama de la base, sola: si el remoto la ha perdido falla aquí, en vez de dar por buena la que ya teníamos.
    rama = f"refs/heads/{origen.rama}"
    _git(repo, "fetch", "--quiet", "--no-prune", "--no-tags", "--", origen.repo, f"+{rama}:{rama}", ajustes=_AL_TRAER)
    try:
        _git(repo, "fetch", "--quiet", "--no-prune", "--", origen.repo, *_REFSPECS, ajustes=_AL_TRAER)
    except FuenteError as e:
        # Como el espejo no poda, una rama borrada en el remoto puede chocar con otra nueva (claude/x y claude):
        # eso deja el espejo incompleto, pero no puede impedir la copia de la base, que ya está traída.
        _avisos.setdefault(origen.nombre, []).append(str(e))


def _fijar_copia(repo: Path, ref: str, sha: str) -> None:
    previo = _git(repo, "for-each-ref", "--format=%(objectname)", ref)
    # Si el remoto reescribió la rama desde la pasada anterior del mismo día, lo que señalaba se guarda antes de moverla.
    if previo and previo != sha and not _es_antepasado(repo, previo, sha):
        _git(repo, "update-ref", f"{ref}-{previo[:12]}", previo)
    _git(repo, "update-ref", ref, sha)


def _es_antepasado(repo: Path, viejo: str, nuevo: str) -> bool:
    args = ("merge-base", "--is-ancestor", viejo, nuevo)
    r = _ejecutar(repo, *args)
    # 1 es «no»; cualquier otro código distinto de 0 es un fallo de git.
    if r.returncode not in (0, 1):
        raise FuenteError(_fallo(args, r))
    return r.returncode == 0


def _punta(repo: Path, origen: Origen) -> str:
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{origen.rama}^{{commit}}")
    except FuenteError:
        raise FuenteError(f"el repositorio de {origen.nombre} no tiene la rama {origen.rama}") from None


def _git(repo: Path | None, *args: str, salida: BinaryIO | None = None, ajustes: Sequence[str] = ()) -> str:
    r = _ejecutar(repo, *args, salida=salida, ajustes=ajustes)
    if r.returncode:
        raise FuenteError(_fallo(args, r))
    return "" if salida is not None else r.stdout.decode(errors="replace").strip()


def _ejecutar(
    repo: Path | None, *args: str, salida: BinaryIO | None = None, ajustes: Sequence[str] = ()
) -> subprocess.CompletedProcess:
    orden = ["git", "-c", "credential.helper="]
    for ajuste in ajustes:
        orden += ["-c", ajuste]
    if repo is not None:
        # El repositorio siempre explícito: git no lo busca a partir del directorio actual ni del entorno.
        orden.append(f"--git-dir={Path(repo).absolute()}")
    entorno = {k: v for k, v in os.environ.items() if k not in _DE_OTRO_REPOSITORIO}
    try:
        return subprocess.run(
            [*orden, *args],
            env={**entorno, **_SIN_CREDENCIALES},
            stdout=subprocess.PIPE if salida is None else salida,
            stderr=subprocess.PIPE,
        )
    except OSError as e:
        raise FuenteError(f"no se puede ejecutar git: {e}") from e


def _fallo(args: tuple[str, ...], r: subprocess.CompletedProcess) -> str:
    detalle = "; ".join(linea.strip() for linea in r.stderr.decode(errors="replace").splitlines() if linea.strip())
    return f"git {args[0]}: {detalle or f'código {r.returncode}'}"
