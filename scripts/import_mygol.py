#!/usr/bin/env python3
"""import_mygol.py — La liga de escuelas de MyGol, de sus originales (scripts/mygol_<S>_raw.json) a la base.

Puro de red: lee lo que bajó fetch_mygol.py y rehace ENTERAS sus cinco tablas propias, mygol_*, en una
transacción. No toca ninguna otra tabla: enlazar a estos niños con las fichas de la federación es de
enlace_mygol.py (la tabla mygol_enlaces, después de resolver las fichas), y lo que se ve en la web, del
generador.

  mygol_torneos          id de MyGol, temporada, categoría (NULL = sin decidir) y nombre
  mygol_equipos          id de MyGol y nombre (el de la temporada más reciente, si cambia)
  mygol_jugadores        id de MyGol, nombre, apellidos y `norm` (identidad.normalizar de
                         «<apellidos>, <nombre>»). El id es PROPIO DE CADA TEMPORADA: MyGol crea las fichas de
                         nuevo cada año, y el mismo niño tiene una fila por temporada. Si dentro de una temporada
                         el mismo id sale con dos nombres, gana el del partido más reciente.
  mygol_partidos         los partidos de los originales; uno aún sin leer entra sin participaciones
  mygol_participaciones  quién estaba convocado en cada partido, con qué equipo y si jugó (0/1)

La temporada, la categoría y el nombre de cada torneo salen de la tabla revisada a mano
(scripts/mygol_torneos.json) si el torneo está en ella, y si no, de lo que el original copió de ella al bajarlo:
así una categoría que se decide después entra sin volver a bajar la temporada.

La pasada del bot llama a importar_si_cambia: solo importa si cambia la huella de los originales y de la
tabla (raw_imports, clave 'mygol').

  python3 scripts/import_mygol.py      (importa en futbolbase.db si algo ha cambiado)
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from identidad import normalizar  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = re.compile(r"^mygol_(\d{4}-\d{4})_raw\.json$")
TABLA = "mygol_torneos.json"
CLAVE = "mygol"                 # la fila de raw_imports
VERSION = "mygol-1"             # entra en la huella: un cambio de lo que se importa obliga a reimportar
TABLAS = ("mygol_torneos", "mygol_equipos", "mygol_jugadores", "mygol_partidos", "mygol_participaciones")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mygol_torneos (
    id INTEGER PRIMARY KEY, temporada TEXT NOT NULL, categoria TEXT, nombre TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mygol_equipos (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mygol_jugadores (
    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, apellidos TEXT NOT NULL, norm TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mygol_partidos (
    id INTEGER PRIMARY KEY, torneo_id INTEGER NOT NULL, jornada TEXT, fecha TEXT, estado INTEGER,
    local_id INTEGER, visitante_id INTEGER, campo TEXT);
CREATE TABLE IF NOT EXISTS mygol_participaciones (
    partido_id INTEGER NOT NULL, jugador_id INTEGER NOT NULL, equipo_id INTEGER NOT NULL, jugo INTEGER NOT NULL,
    PRIMARY KEY (partido_id, jugador_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_mygol_participaciones_jugador ON mygol_participaciones (jugador_id);
"""


def crear_tablas(conn):
    conn.executescript(ESQUEMA)


def raws(raiz=None):
    """Los originales que haya en `raiz` (por defecto scripts/), en orden de temporada."""
    carpeta = Path(raiz or HERE)
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.iterdir() if RAW.match(p.name))


def huella(rutas):
    """sha1 del contenido de todos los ficheros, en orden (con la versión del importador delante)."""
    h = hashlib.sha1(VERSION.encode())
    for p in rutas:
        contenido = Path(p).read_bytes()
        h.update(f"\n{len(contenido)}\n".encode())
        h.update(contenido)
    return h.hexdigest()


def norm_jugador(nombre, apellidos):
    nombre, apellidos = (nombre or "").strip(), (apellidos or "").strip()
    if not apellidos:
        return normalizar(nombre)
    if not nombre:
        return normalizar(apellidos)
    return normalizar(f"{apellidos}, {nombre}")


def _entero(valor, que, donde):
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(f"{donde}: {que} no es un número")
    return valor


def _orden_fecha(fecha):
    """Para «el partido más reciente»: la fecha ISO; las de relleno (0001, 1901) y las que faltan, antes."""
    f = fecha if isinstance(fecha, str) else ""
    return f if f[:4] > "1901" else ""


def _filas(rutas, tabla):
    """Todo lo que va a la base, leído y comprobado antes de tocarla. Un partido mal formado lanza ValueError
    (con el fichero y el id del partido, nunca con un nombre)."""
    torneos, equipos, jugadores, partidos, participaciones = {}, {}, {}, {}, {}
    vistos = {}                     # jugador -> (temporada, fecha, partido) de la lectura que da su nombre
    for orden, ruta in enumerate(rutas):
        raw = json.loads(Path(ruta).read_text(encoding="utf-8"))
        nombre_f = Path(ruta).name
        temporada = raw.get("temporada") or (RAW.match(nombre_f).group(1) if RAW.match(nombre_f) else None)
        if not temporada:
            raise ValueError(f"{nombre_f}: sin temporada")
        for tid, t in (raw.get("torneos") or {}).items():
            donde_t = f"{nombre_f}, torneo {tid}"
            if not isinstance(t, dict):
                raise ValueError(f"{donde_t}: mal formado")
            fila = tabla.get(str(tid)) or {}
            torneos[int(tid)] = (int(tid), fila.get("temporada") or temporada,
                                 fila["categoria"] if "categoria" in fila else t.get("categoria"),
                                 fila.get("nombre") or t.get("nombre") or "")
            for eid, nombre in (t.get("equipos") or {}).items():
                equipos[int(eid)] = (int(eid), str(nombre or ""))      # el original más reciente pisa
            for pid, p in (t.get("partidos") or {}).items():
                donde = f"{donde_t}, partido {pid}"
                if not isinstance(p, dict):
                    raise ValueError(f"{donde}: mal formado")
                pid = int(pid)
                if pid in partidos:
                    raise ValueError(f"{donde}: el mismo partido está también en el torneo {partidos[pid][1]}")
                partidos[pid] =(pid, int(tid), p.get("jornada"), p.get("fecha"),
                                 _entero(p.get("estado"), "estado", donde),
                                 _entero(p.get("local"), "local", donde),
                                 _entero(p.get("visitante"), "visitante", donde), p.get("campo"))
                if "jugadores" not in p:
                    continue                    # aún sin leer: el partido, sin participaciones
                if not isinstance(p["jugadores"], dict):
                    raise ValueError(f"{donde}: jugadores mal formados")
                cuando = (orden, _orden_fecha(p.get("fecha")), pid)
                for eid, lista in p["jugadores"].items():
                    if not isinstance(lista, list):
                        raise ValueError(f"{donde}: jugadores mal formados")
                    for j in lista:
                        if (not isinstance(j, list) or len(j) != 4 or not isinstance(j[0], int)
                                or not isinstance(j[1], str) or not isinstance(j[2], str) or j[3] not in (0, 1)):
                            raise ValueError(f"{donde}: un jugador mal formado")
                        jid, nombre, apellidos, jugo = j
                        clave = (pid, jid)
                        previo = participaciones.get(clave)
                        # Un niño en las dos plantillas (no debería): se queda una fila, la que dice que jugó.
                        if previo is None or (jugo and not previo[3]):
                            participaciones[clave] = (pid, jid, int(eid), int(jugo))
                        if jid not in vistos or cuando >= vistos[jid]:
                            vistos[jid] = cuando
                            jugadores[jid] = (jid, nombre, apellidos, norm_jugador(nombre, apellidos))
    # Los jugadores que siguen saliendo en alguna participación (un partido que desaparece se los lleva).
    con_partido = {jid for (_, jid) in participaciones}
    jugadores = {k: v for k, v in jugadores.items() if k in con_partido}
    return {"mygol_torneos": sorted(torneos.values()), "mygol_equipos": sorted(equipos.values()),
            "mygol_jugadores": sorted(jugadores.values()), "mygol_partidos": sorted(partidos.values()),
            "mygol_participaciones": sorted(participaciones.values())}


def _leer_tabla(tabla):
    if tabla is None or not Path(tabla).exists():
        return {}
    return json.loads(Path(tabla).read_text(encoding="utf-8"))


def importar(conn, rutas=None, tabla=None):
    """Rehace enteras las cinco tablas con lo que digan los originales (por defecto, todos los de scripts/),
    en una transacción: si algo falla, la base queda como estaba. `tabla`: la de torneos revisada (por
    defecto, la de la carpeta de los originales). Devuelve {tabla: filas}."""
    if rutas is None:
        rutas = raws()
    rutas = [Path(p) for p in rutas]
    if tabla is None:
        tabla = (rutas[0].parent if rutas else HERE) / TABLA
    filas = _filas(rutas, _leer_tabla(tabla))
    crear_tablas(conn)
    columnas = {"mygol_torneos": 4, "mygol_equipos": 2, "mygol_jugadores": 4, "mygol_partidos": 8,
                "mygol_participaciones": 4}
    try:
        conn.execute("SAVEPOINT import_mygol")
        for t in TABLAS:
            conn.execute(f"DELETE FROM {t}")
        for t in TABLAS:
            marcas = ", ".join("?" * columnas[t])
            conn.executemany(f"INSERT INTO {t} VALUES ({marcas})", filas[t])
        conn.execute("RELEASE SAVEPOINT import_mygol")
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT import_mygol")
        conn.execute("RELEASE SAVEPOINT import_mygol")
        raise
    conn.commit()
    return {t: len(filas[t]) for t in TABLAS}


def importar_si_cambia(conn, raiz=None, registro=print):
    """importar, solo si la huella de los originales y de la tabla de torneos no es la guardada en
    raw_imports (clave 'mygol'). Sin originales, deja las tablas creadas y vacías. True si importó."""
    carpeta = Path(raiz or HERE)
    rutas = raws(carpeta)
    tabla = carpeta / TABLA
    crear_tablas(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS raw_imports (
        path TEXT PRIMARY KEY, sha1 TEXT NOT NULL, imported_at TEXT NOT NULL)""")
    digest = huella(rutas + ([tabla] if tabla.exists() else []))
    fila = conn.execute("SELECT sha1 FROM raw_imports WHERE path=?", (CLAVE,)).fetchone()
    if fila and fila[0] == digest:
        return False
    cuentas = importar(conn, rutas, tabla=tabla)
    conn.execute("INSERT OR REPLACE INTO raw_imports(path, sha1, imported_at) VALUES (?, ?, datetime('now'))",
                 (CLAVE, digest))
    conn.commit()
    registro(f"  MyGol: {len(rutas)} originales, {cuentas['mygol_torneos']} torneos, "
             f"{cuentas['mygol_partidos']} partidos, {cuentas['mygol_jugadores']} jugadores, "
             f"{cuentas['mygol_participaciones']} participaciones")
    return True


if __name__ == "__main__":
    from db import get_connection
    c = get_connection()
    importar_si_cambia(c)
    c.close()
