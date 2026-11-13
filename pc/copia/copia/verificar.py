"""¿Es buena esta base? Integridad, claves foráneas, tablas vigiladas y mengua."""

import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

TABLAS: tuple[str, ...] = (
    "matches",
    "players",
    "appearances",
    "goals",
    "standings",
    "match_events",
    "teams",
    "groups",
    "scorers",
    "match_staff_all",
)
MARGEN_MENGUA = 0.02

# SQLite antepone esta cabecera a los fallos del árbol B y no dice nada por sí sola.
_CABECERA = re.compile(r"\*\*\* in database \S+ \*\*\*")


@dataclass(frozen=True)
class Resultado:
    ok: bool
    motivos: tuple[str, ...]
    recuentos: dict[str, int]


def comprobar(db: Path, anterior: Mapping[str, int] | None = None, margen: float = MARGEN_MENGUA) -> Resultado:
    try:
        # immutable=1 lee la base en modo WAL sin crear -wal ni -shm al lado.
        con = sqlite3.connect(f"file:{quote(str(Path(db).absolute()))}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as e:
        return Resultado(False, (f"no se puede abrir: {e}",), {})
    try:
        return _comprobar(con, anterior or {}, margen)
    finally:
        con.close()


def _comprobar(con: sqlite3.Connection, anterior: Mapping[str, int], margen: float) -> Resultado:
    try:
        # Leer el esquema es lo primero que falla si el fichero no es una base o está truncado.
        existentes = {fila[0] for fila in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.Error as e:
        return Resultado(False, (f"no se puede abrir: {e}",), {})

    motivos: list[str] = []

    def danada(e: sqlite3.Error) -> None:
        # Una consulta que revienta en una base que sí abre es señal de daño; se anota una sola vez.
        motivo = f"integridad: {e}"
        if motivo not in motivos:
            motivos.append(motivo)

    try:
        primera = _primera_linea(con.execute("PRAGMA integrity_check").fetchall())
        if primera != "ok":
            motivos.append(f"integridad: {primera}")
    except sqlite3.Error as e:
        danada(e)

    try:
        malas = len(con.execute("PRAGMA foreign_key_check").fetchall())
        if malas:
            motivos.append(f"claves foráneas: {malas} filas")
    except sqlite3.Error as e:
        danada(e)

    recuentos: dict[str, int] = {}
    for tabla in TABLAS:
        if tabla not in existentes:
            motivos.append(f"falta la tabla {tabla}")
            continue
        try:
            recuentos[tabla] = con.execute(f'SELECT count(*) FROM "{tabla}"').fetchone()[0]
        except sqlite3.Error as e:
            danada(e)
            continue
        if recuentos[tabla] == 0:
            motivos.append(f"{tabla} está vacía")

    motivos += [f"mengua: {m}" for m in menguas(anterior, recuentos, margen)]
    return Resultado(not motivos, tuple(motivos), recuentos)


def menguas(anterior: Mapping[str, int], recuentos: Mapping[str, int], margen: float = MARGEN_MENGUA) -> list[str]:
    """Las tablas vigiladas que han perdido más del margen, como «matches 40 → 38»."""
    return [
        f"{tabla} {anterior[tabla]} → {recuentos[tabla]}"
        for tabla in TABLAS
        if tabla in anterior and tabla in recuentos and recuentos[tabla] < anterior[tabla] * (1 - margen)
    ]


def _primera_linea(filas: list[tuple[str]]) -> str:
    for (texto,) in filas:
        for linea in str(texto).splitlines():
            if linea.strip() and not _CABECERA.fullmatch(linea.strip()):
                return linea.strip()
    return "sin resultado"
