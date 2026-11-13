"""Una pasada completa por cada origen, el estado que deja y el cerrojo que impide dos pasadas a la vez."""

import fcntl
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import almacen
from .fuentes import FuenteError, Origen, actualizar_espejo, avisos_del_espejo, extraer_base
from .rutas import raiz
from .verificar import comprobar, menguas

ACEPTADA = "aceptada"
SIN_CAMBIOS = "sin cambios"
CUARENTENA = "cuarentena"
ERROR = "error"
_BUENOS = (ACEPTADA, SIN_CAMBIOS)
CADUCIDAD = timedelta(days=3)
_TEMPORAL = ".pasada-"
_NUNCA_SE_PERDONA = ("integridad:", "claves foráneas:", "no se puede abrir:", "mengua:")


def ejecutar(origenes: Sequence[Origen], ahora: datetime, aceptar_mengua: Collection[str] = ()) -> int:
    with _cerrojo() as tomado:
        if not tomado:
            print(f"otra pasada tiene el cerrojo {raiz() / '.cerrojo'}: esta no hace nada", file=sys.stderr, flush=True)
            return 2
        # Con el cerrojo tomado nadie usa ya lo que dejó una pasada cortada a medias (el temporizador la mató, un apagón).
        for resto in raiz().glob(f"{_TEMPORAL}*"):
            shutil.rmtree(resto, ignore_errors=True)
        datos = _estado_para_la_pasada()
        codigo = 0
        for origen in origenes:
            entrada = datos.setdefault(origen.nombre, {})
            resultado, detalle, commit = _pasada(origen, ahora, entrada, origen.nombre in aceptar_mengua)
            entrada["ultima_comprobacion"] = {
                "momento": _iso(ahora), "resultado": resultado, "detalle": detalle, "commit": commit,
            }
            _escribir_estado(datos)
            linea = " ".join([_iso(ahora), origen.nombre, resultado, "; ".join(detalle)]).rstrip()
            with (raiz() / "registro.log").open("a", encoding="utf-8") as registro:
                registro.write(linea + "\n")
            print(linea, flush=True)
            if resultado not in _BUENOS:
                codigo = 1
        return codigo


def estado(ahora: datetime) -> tuple[str, int]:
    ruta = raiz() / "estado.json"
    ocupa = f"ocupa {_tamano(_ocupa(raiz()))} en {raiz()}"
    try:
        datos = _leer_estado(ruta)
        if not datos:
            return f"sin copias en {raiz()}\n{ocupa}", 1
        lineas, codigo = [], 0
        for nombre, entrada in datos.items():
            linea, bien = _resumen(nombre, entrada, ahora)
            lineas.append(linea)
            codigo = codigo if bien else 1
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return f"{ruta} ilegible: {e}\n{ocupa}", 1
    return "\n".join([*lineas, ocupa]), codigo


def _pasada(origen: Origen, ahora: datetime, entrada: dict, a_mano: bool) -> tuple[str, list[str], str | None]:
    commit = None
    avisos: list[str] = []
    try:
        commit = actualizar_espejo(origen, ahora)
        avisos = [f"espejo incompleto: {aviso}" for aviso in avisos_del_espejo(origen)]
        anterior = _anterior(origen.nombre, entrada)
        apartada = entrada.get("ultima_apartada") if a_mano else None
        with tempfile.TemporaryDirectory(prefix=_TEMPORAL, dir=raiz()) as carpeta:
            db = extraer_base(origen, commit, Path(carpeta) / "futbolbase.db")
            if apartada:
                # Aceptar a mano es aceptar la base que se apartó, o una prácticamente igual: se mide contra ella.
                r = comprobar(db, apartada["recuentos"])
                motivos = [m for m in r.motivos if not _perdonable(m, apartada["motivos"])]
            else:
                # Pedido por adelantado, sin nada apartado con que comparar, no se mide la mengua; lo demás sí.
                r = comprobar(db, None if a_mano else anterior)
                motivos = list(r.motivos)
            if motivos:
                ruta = almacen.apartar(origen.nombre, db, motivos, ahora)
                entrada["ultima_apartada"] = {
                    "momento": _iso(ahora),
                    "sha256": almacen._huella(db),
                    "recuentos": r.recuentos,
                    "motivos": list(r.motivos),
                }
                return CUARENTENA, [*motivos, f"apartada en {_relativa(ruta)}", *avisos], commit
            nueva = almacen.aceptar(origen.nombre, db, r.recuentos, ahora)
        # Lo apartado ya no es lo que hay en el remoto: no puede servir de medida a un --aceptar-mengua posterior.
        entrada.pop("ultima_apartada", None)
        ultima = nueva or almacen.versiones(origen.nombre)[-1]
        # Una pasada cortada tras guardar la versión, o un estado.json perdido, se ponen al día con la versión guardada.
        if nueva or (entrada.get("ultima_buena") or {}).get("sha256") != ultima.sha256:
            entrada["ultima_buena"] = {
                "momento": ultima.momento.isoformat(),
                "sha256": ultima.sha256,
                "recuentos": ultima.recuentos,
                "version": _relativa(ultima.ruta),
                "commit": commit,
            }
        detalle = [f"{t} {r.recuentos[t]}" for t in ("matches", "players")] + [f"versión {_relativa(ultima.ruta)}"]
        # Lo que se ha perdonado, contra la última buena: lo que queda en r.motivos son tablas que faltan o vacías.
        if a_mano and (perdonado := [*menguas(anterior or {}, r.recuentos), *r.motivos]):
            detalle.append("aceptado a mano: " + "; ".join(perdonado))
        if volcado := almacen.volcar(origen.nombre, ahora):
            detalle.append(f"volcado en {_relativa(volcado)}")
        if podadas := almacen.podar(origen.nombre, ahora):
            detalle.append(f"versiones viejas borradas: {len(podadas)}")
        return (ACEPTADA if nueva else SIN_CAMBIOS), [*detalle, *avisos], commit
    except Exception as e:
        texto = " ".join(str(e).splitlines())
        return ERROR, [texto if isinstance(e, FuenteError) else f"{type(e).__name__}: {texto}", *avisos], commit


def _perdonable(motivo: str, de_la_apartada: Sequence[str]) -> bool:
    # Que falte una tabla o esté vacía se perdona si ya pasaba en la base apartada; un daño, una clave rota o una
    # mengua respecto a ella, nunca.
    if motivo.startswith(_NUNCA_SE_PERDONA):
        return False
    return (motivo.startswith("falta la tabla ") or motivo.endswith(" está vacía")) and motivo in de_la_apartada


def _anterior(nombre: str, entrada: Mapping) -> Mapping[str, int] | None:
    if entrada.get("ultima_buena"):
        return entrada["ultima_buena"]["recuentos"]
    # Sin estado.json la mengua se sigue midiendo, contra la última versión guardada.
    previas = almacen.versiones(nombre)
    return previas[-1].recuentos if previas else None


def _resumen(nombre: str, entrada: Mapping, ahora: datetime) -> tuple[str, bool]:
    comprobacion = entrada.get("ultima_comprobacion") or {}
    buena = entrada.get("ultima_buena")
    resultado = comprobacion.get("resultado", "nunca")
    partes = [f"{nombre}: comprobada {comprobacion.get('momento', 'nunca')} ({resultado})"]
    avisos = []
    if buena:
        recuentos = buena["recuentos"]
        partes.append(f"última buena {buena['momento']} (matches {recuentos.get('matches')}, players {recuentos.get('players')})")
    else:
        avisos.append("sin copia buena")
    if resultado not in _BUENOS:
        avisos.append("; ".join(comprobacion.get("detalle") or [resultado]))
    if "momento" in comprobacion:
        edad = ahora - datetime.fromisoformat(comprobacion["momento"])
        if edad >= CADUCIDAD:
            avisos.append(f"sin comprobar desde hace {edad.days} días")
    if avisos:
        partes.append("AVISO: " + "; ".join(avisos))
    return " · ".join(partes), not avisos and resultado in _BUENOS


def _estado_para_la_pasada() -> dict:
    ruta = raiz() / "estado.json"
    try:
        return _leer_estado(ruta)
    except ValueError as e:
        # Un estado ilegible no puede parar la copia de cada día: se rehace, y la mengua se mide contra las versiones.
        print(f"{ruta} ilegible ({e}): se empieza uno nuevo", file=sys.stderr, flush=True)
        return {}


def _leer_estado(ruta: Path) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(datos, dict) or not all(isinstance(e, dict) for e in datos.values()):
        raise ValueError("no es un objeto con un objeto por origen")
    return datos


def _escribir_estado(datos: Mapping) -> None:
    with almacen._atomico(raiz() / "estado.json") as temporal:
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _cerrojo() -> Iterator[bool]:
    fd = os.open(raiz() / ".cerrojo", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            tomado = True
        except BlockingIOError:
            tomado = False
        yield tomado
    finally:
        # Cerrar el descriptor suelta el cerrojo; si el proceso muere, lo suelta el sistema.
        os.close(fd)


def _iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).isoformat(timespec="seconds")


def _relativa(ruta: Path) -> str:
    return ruta.relative_to(raiz()).as_posix()


def _ocupa(carpeta: Path) -> int:
    total = 0
    for directorio, _, ficheros in os.walk(carpeta):
        for nombre in ficheros:
            try:
                total += os.lstat(os.path.join(directorio, nombre)).st_size
            except FileNotFoundError:
                pass
    return total


def _tamano(n: float) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1000 or unidad == "GB":
            break
        n /= 1000
    return (f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}").replace(".", ",")
