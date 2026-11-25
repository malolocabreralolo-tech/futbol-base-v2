#!/usr/bin/env python3
"""reconstruir.py — Qué parte de la base se rehace desde los originales guardados en scripts/, comprobado.

Por dominios (el conjunto de tablas que un importador del bot saca de unos originales). Para cada uno, sobre
una COPIA de la base en una carpeta temporal (la API backup de sqlite3; la base de verdad no se abre más que
para leerla): borra las filas del dominio y su marca en raw_imports, vuelve a importar con el importador del
bot (sin red: un socket o un navegador lanzan) y compara con lo que había, fila a fila por clave natural
(códigos de grupo, nombres de equipo, jornadas, ids de la federación), nunca por ids autoincrementales, que
cambian al reinsertar.

    python3 scripts/reconstruir.py --comprobar [--dominio X] [--db futbolbase.db]

Sale con 1 si un dominio declarado rehacible no sale igual. Lo que se rehace y lo que no, para el dueño:
docs/reconstruccion.md. Nunca escribe nombres de personas: las diferencias, en recuentos.
"""
import argparse
import contextlib
import copy
import io
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
ROOT = SCRIPTS.parent


@dataclass(frozen=True)
class Consulta:
    """Las filas de una tabla del dominio, con las referencias ya traducidas a claves naturales (las vistas
    temporales _s, _g, _t, _m y _p de _VISTAS). `clave`: las columnas del SELECT que identifican la fila."""
    tabla: str
    sql: str
    clave: tuple
    cuenta: bool = True    # False: se mide y se dice, pero no decide si el dominio sale igual


@dataclass(frozen=True)
class Dominio:
    nombre: str            # 'app', 'torneos', 'actas_bot', 'actas', 'goleadores', 'detalle', 'portal', 'mygol'
    tablas: tuple          # las que rehace
    originales: tuple      # globs relativos a la raíz
    rehacible: bool        # lo declarado: lo que la prueba exige
    # Cómo: ámbito(conn, carpeta) apunta en tablas temporales qué filas son del dominio (antes de borrar);
    # borrar(conn); rehacer(conn, carpeta de los originales); consultas, lo que se compara.
    borrar: Callable = field(default=None, compare=False, repr=False)
    rehacer: Callable = field(default=None, compare=False, repr=False)
    consultas: tuple = field(default=(), compare=False, repr=False)
    ambito: Callable = field(default=None, compare=False, repr=False)
    motivo: str = ""       # por qué no se rehace (lo medido), para la salida


# ---------------------------------------------------------------------------------------------- sin red

class SinRed(RuntimeError):
    """Un importador ha intentado salir a la red durante la comprobación. No es un OSError a propósito: los
    reintentos de red (except OSError) no lo tragan."""


def _prohibido(*args, **kwargs):
    raise SinRed("reconstruir: sin red durante la comprobación")


def _modulo_sin_navegador():
    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = _prohibido
    return mod


@contextlib.contextmanager
def sin_red():
    """Mientras dura, abrir un socket, resolver un nombre o lanzar Playwright lanza SinRed."""
    guardado = {n: getattr(socket, n) for n in ("create_connection", "getaddrinfo")}
    metodos = {n: getattr(socket.socket, n) for n in ("connect", "connect_ex")}
    modulos = {n: sys.modules.get(n) for n in ("playwright", "playwright.sync_api")}
    falso = _modulo_sin_navegador()
    try:
        for n in guardado:
            setattr(socket, n, _prohibido)
        for n in metodos:
            setattr(socket.socket, n, _prohibido)
        paquete = types.ModuleType("playwright")
        paquete.__path__ = []
        paquete.sync_api = falso
        sys.modules["playwright"], sys.modules["playwright.sync_api"] = paquete, falso
        yield
    finally:
        for n, v in guardado.items():
            setattr(socket, n, v)
        for n, v in metodos.items():
            setattr(socket.socket, n, v)
        for n, v in modulos.items():
            if v is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = v


# ------------------------------------------------------------------------------------- como el bot

def _modulos(nombre):
    """El módulo de scripts/ con los dos nombres con que puede estar cargado (import_fiflp_actas carga
    `scripts.x` cuando lo importa la CLI): una constante se parchea en los dos."""
    import importlib
    out = [importlib.import_module(nombre)]
    if f"scripts.{nombre}" in sys.modules:
        out.append(sys.modules[f"scripts.{nombre}"])
    return out


@contextlib.contextmanager
def _como_el_bot(carpeta, tmp):
    """Lo que el bot ve al importar y las pruebas cambian (conftest): la tabla de nombres revisados de la
    raíz comprobada. Y lo que un importador escribe fuera de la base (los sin partido de las actas, los
    originales del bot), en la carpeta temporal, nunca en scripts/."""
    deshacer = []
    env = os.environ.get("ACTAS_BOT_DIR")
    try:
        # Dentro del try: un fallo a mitad de preparar deshace lo ya parcheado.
        for mod in _modulos("fiflp_names"):
            deshacer.append((mod, "FED_NAMES_PATH", mod.FED_NAMES_PATH))
            mod.FED_NAMES_PATH = str(Path(carpeta) / "fiflp_team_names.json")
            mod.fed_alias.cache_clear()
        sin_partido = Path(tmp) / "fiflp_actas_unmatched.json"
        if (Path(carpeta) / sin_partido.name).exists():
            shutil.copyfile(Path(carpeta) / sin_partido.name, sin_partido)
        for mod in _modulos("import_fiflp_actas"):
            deshacer.append((mod, "UNMATCHED_PATH", mod.UNMATCHED_PATH))
            mod.UNMATCHED_PATH = str(sin_partido)
        os.environ["ACTAS_BOT_DIR"] = str(Path(tmp) / "actas_bot")
        yield
    finally:
        for mod, attr, valor in reversed(deshacer):
            setattr(mod, attr, valor)
            if attr == "FED_NAMES_PATH":
                mod.fed_alias.cache_clear()
        if env is None:
            os.environ.pop("ACTAS_BOT_DIR", None)
        else:
            os.environ["ACTAS_BOT_DIR"] = env


def _huella_ficheros(root):
    """{nombre: sha1} de lo que un importador podría reescribir: scripts/ y los publicados. Por contenido, no
    por fecha: otro proceso que reescribe un fichero igual (alguna prueba lo hace) no es un cambio."""
    import hashlib
    root = Path(root)
    out = {}
    for path in [*(root / "scripts").iterdir(), *root.glob("*.js"), *root.glob("*.json"), *root.glob("*.db")]:
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha1(path.read_bytes()).hexdigest()
    return out


def _callar(*args, **kwargs):
    return None


# ---------------------------------------------------------------------------------------- comparar

# Las claves naturales de lo que las tablas referencian por id: temporada, grupo, equipo, partido y jugador.
# El jugador con id de la federación es ese id; el que no lo tiene, su norm_name ('NOMBRE@equipo.temporada',
# con ids de equipo y temporada, tablas que ningún dominio reinserta).
_VISTAS = (
    ("_s", "CREATE TEMP VIEW _s AS SELECT id, name AS k FROM main.seasons"),
    ("_t", "CREATE TEMP VIEW _t AS SELECT id, name AS k FROM main.teams"),
    ("_g", """CREATE TEMP VIEW _g AS SELECT g.id, s.name || ' ' || c.name || ' ' || g.code AS k
              FROM main.groups g JOIN main.seasons s ON s.id = g.season_id
              JOIN main.categories c ON c.id = g.category_id"""),
    ("_m", """CREATE TEMP VIEW _m AS SELECT m.id, g.k || ' | ' || coalesce(m.jornada, '') || ' | ' || th.name
              || ' - ' || ta.name AS k FROM main.matches m JOIN _g g ON g.id = m.group_id
              JOIN main.teams th ON th.id = m.home_team_id JOIN main.teams ta ON ta.id = m.away_team_id"""),
    ("_p", """CREATE TEMP VIEW _p AS SELECT id, CASE WHEN fiflp_id IS NOT NULL THEN 'fed:' || fiflp_id
              ELSE norm_name END AS k FROM main.players"""),
)


def _vistas(conn):
    for nombre, sql in _VISTAS:
        conn.execute(f"DROP VIEW IF EXISTS temp.{nombre}")
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass                # una base sin esa tabla (las de prueba): la consulta que la use fallará


def _instantanea(conn, consultas):
    """{tabla: {clave: [filas]}} de las consultas."""
    _vistas(conn)
    out = {}
    for c in consultas:
        cur = conn.execute(c.sql)
        cols = [d[0] for d in cur.description]
        idx = [cols.index(k) for k in c.clave]
        filas = {}
        for row in cur:
            filas.setdefault(tuple(row[i] for i in idx), []).append(tuple(row))
        out[c.tabla] = {k: sorted(v, key=repr) for k, v in filas.items()}
    return out


def diferencias(antes, despues):
    """{tabla: (cambiadas, faltan, sobran)} con las claves de cada clase (para investigar; la salida solo
    da los recuentos: las claves pueden llevar nombres)."""
    out = {}
    for tabla in antes:
        a, d = antes[tabla], despues.get(tabla, {})
        out[tabla] = (sorted((k for k in a.keys() & d.keys() if a[k] != d[k]), key=repr),
                      sorted(a.keys() - d.keys(), key=repr), sorted(d.keys() - a.keys(), key=repr))
    return out


def _resultado(antes, despues, consultas):
    difs = diferencias(antes, despues)
    cuentan = {c.tabla for c in consultas if c.cuenta}
    filas = sum(len(v) for t, filas_t in antes.items() if t in cuentan for v in filas_t.values())
    distintas = sum(len(c) + len(f) + len(s) for t, (c, f, s) in difs.items() if t in cuentan)
    partes = []
    for tabla, (c, f, s) in difs.items():
        n = sum(len(v) for v in antes[tabla].values())
        aparte = "" if tabla in cuentan else " (aparte, no cuenta)"
        if c or f or s:
            partes.append(f"{tabla}{aparte}: {n} filas, {len(c)} cambiadas, {len(f)} faltan, {len(s)} sobran")
        else:
            partes.append(f"{tabla}{aparte}: {n} filas iguales")
    return {"igual": distintas == 0, "filas": filas, "distintas": distintas, "detalle": "; ".join(partes)}


# --------------------------------------------------------------------------------------- comprobar

def _abrir_origen(db_path):
    """La base de verdad, solo para leerla. Sin -wal, inmutable (no crea -wal ni -shm a su lado)."""
    p = Path(db_path).resolve()
    modo = "ro" if Path(f"{p}-wal").exists() else "ro&immutable=1"
    return sqlite3.connect(f"file:{p}?mode={modo}", uri=True)


def _copiar(db_path, destino):
    origen = _abrir_origen(db_path)
    try:
        dst = sqlite3.connect(destino)
        with dst:
            origen.backup(dst)
        dst.close()
    finally:
        origen.close()


def _uno(dominio, db_path, root):
    from db import get_connection
    carpeta = str(Path(root) / "scripts")
    with tempfile.TemporaryDirectory(prefix="reconstruir-") as tmp:
        copia = os.path.join(tmp, "futbolbase.db")
        _copiar(db_path, copia)
        conn = get_connection(copia)
        huella = _huella_ficheros(root)
        try:
            with sin_red(), _como_el_bot(carpeta, tmp), contextlib.redirect_stdout(io.StringIO()):
                if dominio.ambito:
                    dominio.ambito(conn, carpeta)
                    conn.commit()
                antes = _instantanea(conn, dominio.consultas)
                dominio.borrar(conn)
                conn.commit()
                dominio.rehacer(conn, carpeta)
                conn.commit()
                despues = _instantanea(conn, dominio.consultas)
            cambiados = sorted(k for k, v in _huella_ficheros(root).items() if huella.get(k) != v)
            if cambiados:
                raise RuntimeError(f"el importador ha escrito fuera de la copia: {', '.join(cambiados)}")
            out = _resultado(antes, despues, dominio.consultas)
            avisos = [t for (t,) in conn.execute("SELECT texto FROM temp._avisos ORDER BY rowid")] \
                if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='_avisos'").fetchone() else []
            if avisos:
                texto = "; ".join(avisos[:10]) + (f"; y {len(avisos) - 10} más" if len(avisos) > 10 else "")
                out = {**out, "igual": False, "detalle": f"{out['detalle']}; avisos: {texto}"}
            return out
        except SinRed as e:
            return {"igual": False, "filas": 0, "distintas": 0, "detalle": f"intentó salir a la red: {e}"}
        except Exception as e:
            return {"igual": False, "filas": 0, "distintas": 0, "detalle": f"error: {type(e).__name__}: {e}"}
        finally:
            conn.close()


def comprobar(db_path, root, dominios=None) -> dict:
    """{nombre: {'igual': bool, 'filas': int, 'distintas': int, 'detalle': str}}. Trabaja SIEMPRE sobre
    una copia de `db_path` en una carpeta temporal (API backup de sqlite3): en la copia borra las filas del
    dominio y su marca en raw_imports, vuelve a importar con el importador del bot, y compara con la base
    original fila a fila por clave natural (no por ids autoincrementales). Una copia por dominio: lo que
    borra uno no lo ve el siguiente. Cada resultado lleva también 'segundos'."""
    out = {}
    for d in (DOMINIOS if dominios is None else dominios):
        t0 = time.monotonic()
        out[d.nombre] = {**_uno(d, db_path, root), "segundos": round(time.monotonic() - t0, 1)}
    return out


# ------------------------------------------------------------------------------------------ ayudas

def _sin_marca(conn, *patrones):
    """Borra la huella de raw_imports de los originales del dominio: el importador los vuelve a leer."""
    for p in patrones:
        conn.execute("DELETE FROM raw_imports WHERE path LIKE ?", (p,))


def _temporadas_pasadas(conn, carpeta, patron):
    """Las temporadas con un original en `carpeta` que casa con `patron` (su grupo 1, la temporada), menos la
    que la base tiene en curso (esa se lee en vivo cada pasada)."""
    import re
    en_curso = {n for (n,) in conn.execute("SELECT name FROM seasons WHERE is_current = 1")}
    return sorted({m.group(1) for m in (re.match(patron, n) for n in os.listdir(carpeta)) if m} - en_curso)


def _ambito_grupos(conn, where, args=()):
    """temp._grupos: la clave natural de los grupos del dominio (un grupo borrado y vuelto a crear cambia de
    id, no de clave); temp._ambito: sus partidos, los que haya en cada momento (es una vista)."""
    _vistas(conn)
    conn.execute("CREATE TEMP TABLE _grupos (k TEXT PRIMARY KEY)")
    conn.execute(f"""INSERT OR IGNORE INTO temp._grupos SELECT gg.k FROM groups g JOIN _g gg ON gg.id = g.id
                     JOIN seasons s ON s.id = g.season_id WHERE {where}""", args)
    conn.execute("""CREATE TEMP VIEW _ambito AS SELECT m.id AS match_id FROM main.matches m
                    JOIN _g g ON g.id = m.group_id
                    WHERE g.k IN (SELECT k FROM temp._grupos)""")


def _en(temporadas):
    return f"s.name IN ({','.join('?' * len(temporadas))})", tuple(temporadas)


def _borrar_actas_del_ambito(conn):
    """Lo que sale de las actas de los partidos del ámbito, y los jugadores que solo salían en ellas (el
    importador los vuelve a crear). La ficha de otro que apuntara a uno de ellos se suelta: resolver_fichas
    las recalcula todas."""
    dentro = "match_id IN (SELECT match_id FROM temp._ambito)"
    conn.execute(f"""CREATE TEMP TABLE _suyos AS SELECT player_id AS id FROM appearances WHERE {dentro}
                     UNION SELECT player_id FROM match_events WHERE {dentro}""")
    for tabla in ("appearances", "match_events", "match_staff_all"):
        conn.execute(f"DELETE FROM {tabla} WHERE {dentro}")
    conn.execute("UPDATE matches SET cod_acta = NULL WHERE id IN (SELECT match_id FROM temp._ambito)")
    huerfanos = """id IN (SELECT id FROM temp._suyos) AND id NOT IN (SELECT player_id FROM appearances)
                   AND id NOT IN (SELECT player_id FROM match_events)"""
    conn.execute(f"UPDATE players SET ficha_id = NULL WHERE ficha_id IN (SELECT id FROM players WHERE {huerfanos})")
    conn.execute(f"DELETE FROM players WHERE {huerfanos}")


def _sin_cuerpo_tecnico(conn, gid):
    """El cuerpo técnico de los partidos de un grupo: db.delete_group_matches no lo borra (MATCH_CHILD_TABLES)
    y, con las claves ajenas activas, un partido con él no se deja borrar."""
    conn.execute("DELETE FROM match_staff_all WHERE match_id IN (SELECT id FROM matches WHERE group_id = ?)", (gid,))


def _avisar(conn, texto):
    """Apunta en temp._avisos lo que impide dar el dominio por igual aunque las filas coincidan; comprobar lo
    añade al detalle. Sin nombres de personas: códigos, tipos de error y recuentos. No hace commit."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _avisos (texto TEXT)")
    conn.execute("INSERT INTO temp._avisos VALUES (?)", (texto,))


def _fichas(conn, carpeta):
    """Las fichas, como al final de cada pasada del bot (fetch_futbolaspalmas.main)."""
    import migrate_identidad
    migrate_identidad.resolver_fichas(conn, log=_callar,
                                      separadas=os.path.join(carpeta, "identidad_separadas.json"))


def _pasada(conn, carpeta):
    """Lo que hace cada pasada del bot con los originales de temporadas pasadas: import_past_seasons (sus
    pasos, en su orden; cada importador rehace lo que ya no tiene su huella en raw_imports) y las fichas.
    El bot apunta un paso que falla y sigue: aquí queda en temp._avisos (el título del paso y el tipo de
    error, nunca el mensaje, que puede llevar un nombre) y el dominio no sale igual."""
    if Path(carpeta).resolve() != SCRIPTS:
        raise RuntimeError("import_past_seasons lee los originales de su propia carpeta: la raíz ha de ser esta")
    import fetch_futbolaspalmas
    lineas = []
    fetch_futbolaspalmas.import_past_seasons(conn, log=lineas.append)
    avisos, paso = [], None
    for linea in lineas:
        if linea.startswith("\n"):
            paso = linea.strip()
        elif "! ERROR" in linea:
            ultima = [x for x in linea.strip().splitlines() if x.strip()][-1]
            avisos.append(f"falló «{paso}» ({ultima.split(':')[0].strip()})")
    _fichas(conn, carpeta)
    for aviso in avisos:
        _avisar(conn, aviso)
    conn.commit()


# -------------------------------------------------------------------------------------- consultas

_DENTRO = "IN (SELECT match_id FROM temp._ambito)"
_EN_GRUPOS = "IN (SELECT k FROM temp._grupos)"
_JUGADORES_DEL_AMBITO = f"""(SELECT player_id FROM appearances WHERE match_id {_DENTRO}
                             UNION SELECT player_id FROM match_events WHERE match_id {_DENTRO})"""

_C_APARICIONES = Consulta(
    "appearances", f"""SELECT m.k AS partido, t.k AS equipo, p.k AS jugador, a.dorsal, a.role, a.goals, a.yellow,
                              a.red, a.ord
                       FROM appearances a JOIN _m m ON m.id = a.match_id JOIN _t t ON t.id = a.team_id
                       JOIN _p p ON p.id = a.player_id WHERE a.match_id {_DENTRO}""",
    ("partido", "equipo", "jugador"))
# El suceso, por su orden en el partido (su id cambia al reinsertar); su pareja (un cambio), por el de ella.
_C_SUCESOS = Consulta(
    "match_events", f"""WITH e AS (SELECT *, row_number() OVER (PARTITION BY match_id ORDER BY id) AS n
                                   FROM match_events WHERE match_id {_DENTRO})
                        SELECT m.k AS partido, e.n, t.k AS equipo, p.k AS jugador, e.kind, e.minute, e.goal_type,
                               pe.n AS pareja
                        FROM e JOIN _m m ON m.id = e.match_id JOIN _t t ON t.id = e.team_id
                        JOIN _p p ON p.id = e.player_id LEFT JOIN e pe ON pe.id = e.pair_id""",
    ("partido", "n"))
_C_CUERPO = Consulta(
    "match_staff_all", f"""SELECT m.k AS partido, x.ord, t.k AS equipo, x.role, x.name
                           FROM match_staff_all x JOIN _m m ON m.id = x.match_id
                           LEFT JOIN _t t ON t.id = x.team_id WHERE x.match_id {_DENTRO}""",
    ("partido", "ord"))
# Los jugadores de esos partidos: su identidad (equipo, temporada y ordinal de la sin id, su clave pública) y su
# ficha (la clave natural de la principal).
_C_JUGADORES = Consulta(
    "players", f"""SELECT p.k AS jugador, x.fiflp_id, f.k AS ficha, x.union_por, t.k AS equipo, s.k AS temporada,
                          x.ordinal, x.clave
                   FROM players x JOIN _p p ON p.id = x.id LEFT JOIN _p f ON f.id = x.ficha_id
                   LEFT JOIN _t t ON t.id = x.team_id LEFT JOIN _s s ON s.id = x.season_id
                   WHERE x.id IN {_JUGADORES_DEL_AMBITO}""",
    ("jugador",))
# La grafía del nombre, aparte: la de una fila es la de la PRIMERA lectura que la creó (_get_or_create_player no
# la cambia después), y el original guarda la ÚLTIMA lectura de cada acta. Se mide y se dice; no es un dato del
# original. Su norm_name, con ella: el de un jugador con id de la federación es su nombre de entonces.
_C_GRAFIAS = Consulta(
    "players (grafía del nombre)", f"""SELECT p.k AS jugador, x.full_name, x.norm_name FROM players x
                                       JOIN _p p ON p.id = x.id WHERE x.id IN {_JUGADORES_DEL_AMBITO}""",
    ("jugador",), cuenta=False)
# Lo que el acta (y el calendario) escriben en el partido. Fuera acta_tries y acta_recheck: los reintentos del
# bot, no datos.
_C_PARTIDOS = Consulta(
    "matches", f"""SELECT m.k AS partido, x.date, x.time, x.home_score, x.away_score, x.venue, x.cod_acta,
                          x.fiflp_acta, x.venue_code
                   FROM matches x JOIN _m m ON m.id = x.id WHERE x.id {_DENTRO}""",
    ("partido",))
_C_CLASIFICACION = Consulta(
    "standings", f"""SELECT g.k AS grupo, t.k AS equipo, x.position, x.points, x.played, x.won, x.drawn, x.lost,
                            x.gf, x.gc, x.gd
                     FROM standings x JOIN _g g ON g.id = x.group_id JOIN _t t ON t.id = x.team_id
                     WHERE g.k {_EN_GRUPOS}""",
    ("grupo", "equipo"))
_C_GRUPOS = Consulta(
    "groups", f"""SELECT g.k AS grupo, x.name, x.full_name, x.phase, x.island, x.url, x.current_jornada
                  FROM groups x JOIN _g g ON g.id = x.id WHERE g.k {_EN_GRUPOS}""",
    ("grupo",))
_C_ACTAS = (_C_APARICIONES, _C_SUCESOS, _C_CUERPO, _C_JUGADORES, _C_GRAFIAS, _C_PARTIDOS)


# ------------------------------------------------------------------------------------------- app

def _borrar_app(conn):
    for tabla in ("fp_goals", "fp_matches", "fp_teams", "fp_ligas"):
        conn.execute(f"DELETE FROM {tabla}")
    _sin_marca(conn, "fp_app_%")


def _rehacer_app(conn, carpeta):
    import import_fp_app
    import_fp_app.import_changed_fp_app(conn, folder=carpeta, log=_callar)


_CONSULTAS_APP = (
    Consulta("fp_ligas", """SELECT l.liga_id, s.k AS temporada, g.k AS grupo, l.name, l.tipo, l.total_jornadas,
                                   l.jornada_actual, l.plazas_ascenso, l.plazas_playoff, l.plazas_copa,
                                   l.plazas_promocion, l.plazas_descenso, l.texto_ascenso, l.texto_playoff,
                                   l.texto_copa, l.texto_promocion, l.texto_descenso, l.fetched
                            FROM fp_ligas l LEFT JOIN _s s ON s.id = l.season_id LEFT JOIN _g g ON g.id = l.group_id""",
             ("liga_id",)),
    Consulta("fp_teams", """SELECT x.fp_team_id, x.liga_id, t.k AS equipo, x.name, x.escudo, x.equipacion,
                                   x.banderas, x.sanciones
                            FROM fp_teams x LEFT JOIN _t t ON t.id = x.team_id""", ("fp_team_id",)),
    Consulta("fp_matches", """SELECT x.fp_id, x.liga_id, m.k AS partido, x.jornada, x.estado, x.fecha_programada,
                                     x.hora_inicio, x.local, x.visitante, x.estadio, x.campo_gps, x.latitud,
                                     x.longitud, x.goles_local, x.goles_visitante, x.goleadores_local,
                                     x.goleadores_visitante, x.penaltis_local, x.penaltis_visitante,
                                     x.motivo_aplazado, x.arbitro, x.asistente1, x.asistente2, x.tecnico_local,
                                     x.tecnico_visitante, x.fase_eliminatoria
                              FROM fp_matches x LEFT JOIN _m m ON m.id = x.match_id""", ("fp_id",)),
    Consulta("fp_goals", "SELECT fp_id, ord, side, minute, name FROM fp_goals", ("fp_id", "ord")),
)


# --------------------------------------------------------------------------------------- torneos

def _borrar_torneos(conn):
    for tabla in ("tournament_standings", "tournament_matches", "tournaments"):
        conn.execute(f"DELETE FROM {tabla}")
    _sin_marca(conn, "maspalomas_cup_%")


def _rehacer_torneos(conn, carpeta):
    import import_torneos
    import_torneos.import_changed_torneos(conn, folder=carpeta, log=_callar)


# El torneo, por su nombre (su id se reasigna al reinsertar).
_CONSULTAS_TORNEOS = (
    Consulta("tournaments", "SELECT name, edition, organizer, url, first_day, last_day FROM tournaments", ("name",)),
    Consulta("tournament_matches", """SELECT x.id, t.name AS torneo, x.category, x.match_number, x.phase,
                                             x.group_name, x.round, x.date, x.time, x.field, x.home, x.away,
                                             x.home_ext_id, x.away_ext_id, x.home_score, x.away_score, x.status,
                                             x.penalty_winner, x.penalty_home, x.penalty_away
                                      FROM tournament_matches x JOIN tournaments t ON t.id = x.tournament_id""",
             ("id",)),
    Consulta("tournament_standings", """SELECT t.name AS torneo, x.category, x.group_name, x.team, x.position,
                                               x.points, x.played, x.won, x.drawn, x.lost, x.gf, x.gc
                                        FROM tournament_standings x JOIN tournaments t ON t.id = x.tournament_id""",
             ("torneo", "category", "group_name", "team")),
)


# ------------------------------------------------------------------------------------- actas_bot

def _originales_bot(carpeta):
    """[(leída, temporada, CodActa, acta)] de scripts/actas_bot_<S>_<categoría>.jsonl, en el orden en que el
    bot las leyó (un acta aparece una vez: actas_bot.guardar sustituye su línea)."""
    import glob
    import re
    out = []
    for path in sorted(glob.glob(os.path.join(carpeta, "actas_bot_*.jsonl"))):
        m = re.match(r"^actas_bot_(\d{4}-\d{4})_\w+\.jsonl$", os.path.basename(path))
        if not m:
            continue
        with open(path, encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    obj = json.loads(linea)
                    out.append((str(obj.get("leida") or ""), m.group(1), int(obj["cod_acta"]), obj["acta"]))
    return sorted(out, key=lambda r: (r[0], r[2]))


def _ambito_bot(conn, carpeta):
    """temp._ambito: los partidos de la temporada de cada original cuya acta importada (cod_acta) es la suya.
    Sus ids no cambian: este dominio no reinserta partidos."""
    conn.execute("CREATE TEMP TABLE _ambito (match_id INTEGER PRIMARY KEY)")
    for _, temporada, cod, _ in _originales_bot(carpeta):
        conn.execute("""INSERT OR IGNORE INTO temp._ambito SELECT m.id FROM matches m JOIN groups g ON g.id = m.group_id
                        JOIN seasons s ON s.id = g.season_id WHERE s.name = ? AND m.cod_acta = ?""", (temporada, cod))


def _rehacer_bot(conn, carpeta):
    """Cada original, por el camino del bot al leer un acta (update_fiflp._read_actas): el partido de la
    temporada que la enlaza en su calendario (fiflp_acta, lo que lee pending_actas) y apply_acta, con su
    commit. Después, las fichas. Un original que no casa con un solo partido, o que apply_acta rechaza, no
    entra: queda como aviso (su código y por qué) y el dominio no sale igual. Dos partidos con el mismo enlace
    son el mismo partido entrado dos veces (docs/reconstruccion.md): el bot no sabe cuál es el bueno y le pasa
    el acta al que la tiene pendiente, así que tampoco se puede rehacer sin elegir."""
    import update_fiflp
    for _, temporada, cod, acta in _originales_bot(carpeta):
        filas = conn.execute("""SELECT m.id FROM matches m JOIN groups g ON g.id = m.group_id
                                JOIN seasons s ON s.id = g.season_id WHERE s.name = ? AND m.fiflp_acta = ?""",
                             (temporada, cod)).fetchall()
        if len(filas) != 1:
            _avisar(conn, f"el original del acta {cod} casa con {len(filas)} partidos de {temporada} (fiflp_acta)")
        else:
            try:
                if not update_fiflp.apply_acta(conn, filas[0][0], cod, copy.deepcopy(acta), log=_callar):
                    _avisar(conn, f"apply_acta rechaza el original del acta {cod}")
            except Exception as e:
                conn.rollback()
                _avisar(conn, f"el original del acta {cod} no se aplica ({type(e).__name__})")
        conn.commit()
    _fichas(conn, carpeta)


# ----------------------------------------------------------------------------- actas (pasadas)

_RAW_ACTAS = r"^fiflp_actas_(\d{4}-\d{4})(?:_\w+)?_raw\.json$"


def _ambito_actas(conn, carpeta):
    _ambito_grupos(conn, *_en(_temporadas_pasadas(conn, carpeta, _RAW_ACTAS)))


def _borrar_actas(conn):
    """Las actas de las temporadas pasadas y las huellas de sus raws y de los grupos de la federación (los
    grupos que creó import_fiflp_grupos importan ellos sus actas)."""
    _borrar_actas_del_ambito(conn)
    _sin_marca(conn, "fiflp_actas_%", "grupos:%")


# ------------------------------------------------------------------------------------ goleadores

_RAW_GOLEADORES = r"^fiflp_goleadores_(\d{4}-\d{4})_raw\.json$"


def _ambito_goleadores(conn, carpeta):
    _ambito_grupos(conn, *_en(_temporadas_pasadas(conn, carpeta, _RAW_GOLEADORES)))


def _borrar_goleadores(conn):
    """Los goleadores que escribió el importador de la federación (fiflp_scorer_groups; los de futbolaspalmas
    se quedan, él tampoco los toca) y las huellas de sus raws."""
    conn.execute("DELETE FROM scorers WHERE group_id IN (SELECT group_id FROM fiflp_scorer_groups)")
    conn.execute("DELETE FROM fiflp_scorer_groups")
    _sin_marca(conn, "fiflp_goleadores_%")


_CONSULTAS_GOLEADORES = (
    Consulta("scorers", f"""SELECT g.k AS grupo, x.player_name, t.k AS equipo, x.goals, x.games
                            FROM scorers x JOIN _g g ON g.id = x.group_id JOIN _t t ON t.id = x.team_id
                            WHERE g.k {_EN_GRUPOS}""", ("grupo", "player_name", "equipo")),
    Consulta("fiflp_scorer_groups", f"""SELECT g.k AS grupo, x.comp, x.grupo AS grupo_federacion
                                        FROM fiflp_scorer_groups x JOIN _g g ON g.id = x.group_id""", ("grupo",)),
    _C_CLASIFICACION, _C_GRUPOS,
)


# --------------------------------------------------------------------------------------- detalle

_RAW_DETALLE = r"^fiflp_detalle_(\d{4}-\d{4})_raw\.json$"


def _ambito_detalle(conn, carpeta):
    """Los grupos y las temporadas pasadas con raw de detalle, y los campos con ficha en fiflp_campos_raw.json."""
    temporadas = _temporadas_pasadas(conn, carpeta, _RAW_DETALLE)
    _ambito_grupos(conn, *_en(temporadas))
    conn.execute("CREATE TEMP TABLE _temporadas (name TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO temp._temporadas VALUES (?)", [(t,) for t in temporadas])
    conn.execute("CREATE TEMP TABLE _campos (code INTEGER PRIMARY KEY)")
    with open(os.path.join(carpeta, "fiflp_campos_raw.json"), encoding="utf-8") as f:
        campos = json.load(f)
    conn.executemany("INSERT INTO temp._campos VALUES (?)", [(int(c),) for c, v in campos.items() if v.get("ok")])


def _borrar_detalle(conn):
    """Lo del detalle de las temporadas pasadas (casa/fuera, fichas de equipo, las copas que creó desde su
    calendario), las fichas de campo de su raw y sus huellas. La temporada en curso, no: la lee en vivo el bot."""
    from db import delete_group
    temporadas = [t for (t,) in conn.execute("SELECT name FROM temp._temporadas")]
    conn.execute(f"""DELETE FROM standings_detail WHERE group_id IN
                     (SELECT g.id FROM _g g WHERE g.k {_EN_GRUPOS})""")
    conn.execute("""DELETE FROM team_seasons WHERE season_id IN
                    (SELECT id FROM seasons WHERE name IN (SELECT name FROM temp._temporadas))""")
    conn.execute("DELETE FROM venue_details WHERE code IN (SELECT code FROM temp._campos)")
    for (gid,) in conn.execute("""SELECT d.group_id FROM detalle_groups d JOIN seasons s ON s.id = d.season_id
                                  WHERE s.name IN (SELECT name FROM temp._temporadas)""").fetchall():
        conn.execute("DELETE FROM detalle_groups WHERE group_id = ?", (gid,))
        _sin_cuerpo_tecnico(conn, gid)
        delete_group(conn, gid)
    _sin_marca(conn, "fiflp_campos_raw.json", *(f"fiflp_detalle_{t}_raw.json" for t in temporadas))


_CONSULTAS_DETALLE = (
    Consulta("standings_detail", f"""SELECT g.k AS grupo, t.k AS equipo, x.fiflp_code, x.home_played, x.home_won,
                                            x.home_drawn, x.home_lost, x.away_played, x.away_won, x.away_drawn,
                                            x.away_lost, x.sanction, x.form
                                     FROM standings_detail x JOIN _g g ON g.id = x.group_id
                                     JOIN _t t ON t.id = x.team_id WHERE g.k {_EN_GRUPOS}""", ("grupo", "equipo")),
    Consulta("team_seasons", """SELECT t.k AS equipo, s.k AS temporada, x.fiflp_code, x.fiflp_name, x.crest_url,
                                       x.shirt, x.shorts, x.socks, x.venue_code, x.venue_name, x.surface
                                FROM team_seasons x JOIN _t t ON t.id = x.team_id JOIN _s s ON s.id = x.season_id
                                WHERE s.k IN (SELECT name FROM temp._temporadas)""", ("equipo", "temporada")),
    Consulta("venue_details", """SELECT code, name, lat, lon, address, city, province, postal_code, surface, photo,
                                        fenced, doping_room, referee_room, internet, teams, training, fetched
                                 FROM venue_details WHERE code IN (SELECT code FROM temp._campos)""", ("code",)),
    Consulta("detalle_groups", """SELECT g.k AS grupo, x.comp, x.grupo AS grupo_federacion
                                  FROM detalle_groups x JOIN _g g ON g.id = x.group_id""", ("grupo",)),
    _C_PARTIDOS, _C_CLASIFICACION, _C_GRUPOS,
)


# ---------------------------------------------------------------------------------------- portal

def _ambito_portal(conn, carpeta):
    _ambito_grupos(conn, "g.id IN (SELECT group_id FROM portal_groups)")


def _borrar_portal(conn):
    """Lo que escribió el archivo del portal: los grupos (y temporadas) que dio de alta, enteros, y los
    partidos que puso en grupos de la federación sin partidos, con lo que cuelga de ellos (las actas: sus
    raws pierden también la huella, para que el bot las vuelva a enlazar), y las huellas de sus raws."""
    from db import delete_group, delete_group_matches
    con_actas = [t for (t,) in conn.execute(
        """SELECT DISTINCT s.name FROM matches m JOIN groups g ON g.id = m.group_id JOIN seasons s ON s.id = g.season_id
           WHERE m.group_id IN (SELECT group_id FROM portal_groups) AND m.cod_acta IS NOT NULL""")]
    nuevas = set()
    grupos = conn.execute("SELECT group_id, mode, season FROM portal_groups").fetchall()
    conn.execute("DELETE FROM portal_groups")
    for gid, modo, temporada in grupos:
        _sin_cuerpo_tecnico(conn, gid)
        if modo == "group":
            delete_group(conn, gid)
            nuevas.add(temporada)
        else:
            delete_group_matches(conn, gid)
    for t in nuevas:
        conn.execute("""DELETE FROM seasons WHERE name = ?
                        AND NOT EXISTS (SELECT 1 FROM groups g WHERE g.season_id = seasons.id)""",
                     (t,))
    _sin_marca(conn, "wayback_portal_%", *(f"fiflp_actas_{t}%" for t in con_actas))


_CONSULTAS_PORTAL = (
    Consulta("portal_groups", """SELECT g.k AS grupo, x.season, x.code, x.mode, x.source
                                 FROM portal_groups x JOIN _g g ON g.id = x.group_id""", ("grupo",)),
    _C_GRUPOS, _C_PARTIDOS, _C_CLASIFICACION,
)


# ----------------------------------------------------------------------------------------- mygol

_TABLAS_MYGOL = ("mygol_participaciones", "mygol_partidos", "mygol_jugadores", "mygol_equipos", "mygol_torneos")


def _ambito_mygol(conn, carpeta):
    """Una base de antes de la primera pasada con import_mygol no tiene sus tablas: se le hace lo que hará esa
    pasada (crearlas e importar los originales), y lo que se comprueba es que rehacerlas sale igual."""
    import import_mygol
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'mygol_partidos'").fetchone():
        import_mygol.importar_si_cambia(conn, raiz=carpeta, registro=_callar)


def _borrar_mygol(conn):
    for tabla in _TABLAS_MYGOL:
        conn.execute(f"DELETE FROM {tabla}")
    _sin_marca(conn, "mygol")


def _rehacer_mygol(conn, carpeta):
    import import_mygol
    import_mygol.importar_si_cambia(conn, raiz=carpeta, registro=_callar)


# Los ids son los de MyGol: claves naturales, no cambian al reinsertar.
_CONSULTAS_MYGOL = (
    Consulta("mygol_torneos", "SELECT id, temporada, categoria, nombre FROM mygol_torneos", ("id",)),
    Consulta("mygol_equipos", "SELECT id, nombre FROM mygol_equipos", ("id",)),
    Consulta("mygol_jugadores", "SELECT id, nombre, apellidos, norm FROM mygol_jugadores", ("id",)),
    Consulta("mygol_partidos", """SELECT id, torneo_id, jornada, fecha, estado, local_id, visitante_id, campo
                                  FROM mygol_partidos""", ("id",)),
    Consulta("mygol_participaciones", """SELECT partido_id, jugador_id, equipo_id, jugo
                                         FROM mygol_participaciones""", ("partido_id", "jugador_id")),
)


# ------------------------------------------------------------------------------------------ dominios

DOMINIOS: tuple = (
    Dominio("app", ("fp_ligas", "fp_teams", "fp_matches", "fp_goals"), ("scripts/fp_app_*_raw.json",), True,
            borrar=_borrar_app, rehacer=_rehacer_app, consultas=_CONSULTAS_APP),
    Dominio("torneos", ("tournaments", "tournament_matches", "tournament_standings"),
            ("scripts/maspalomas_cup_*_raw.json",), True,
            borrar=_borrar_torneos, rehacer=_rehacer_torneos, consultas=_CONSULTAS_TORNEOS),
    Dominio("actas_bot", ("appearances", "match_events", "match_staff_all", "players"),
            ("scripts/actas_bot_*.jsonl",), True,
            ambito=_ambito_bot, borrar=_borrar_actas_del_ambito, rehacer=_rehacer_bot, consultas=_C_ACTAS),
    Dominio("actas", ("appearances", "match_events", "match_staff_all", "players"),
            ("scripts/fiflp_actas_*_raw.json", "scripts/fiflp_actas_*_index.json"), False,
            ambito=_ambito_actas, borrar=_borrar_actas, rehacer=_pasada,
            consultas=(*_C_ACTAS, _C_CLASIFICACION, _C_GRUPOS),
            motivo="la importación de las actas también escribe partidos y lo que la base tiene ya corregido no "
                   "se repite: vuelven 1.533 partidos que la base ya no tiene (casi todos de 2016-19, con jornada "
                   "'Jornada N') y faltan 257; cambian el campo, la hora o la fecha de casi 10.000 (y 61 "
                   "marcadores); y las alineaciones, sucesos y cuerpo técnico de 2019-21 (archivadas) y algo de "
                   "2024-26 salen distintos"),
    Dominio("goleadores", ("scorers", "fiflp_scorer_groups"), ("scripts/fiflp_goleadores_*_raw.json",), True,
            ambito=_ambito_goleadores, borrar=_borrar_goleadores, rehacer=_pasada,
            consultas=_CONSULTAS_GOLEADORES),
    Dominio("detalle", ("standings_detail", "team_seasons", "venue_details", "detalle_groups"),
            ("scripts/fiflp_detalle_*_raw.json", "scripts/fiflp_campos_raw.json"), False,
            ambito=_ambito_detalle, borrar=_borrar_detalle, rehacer=_pasada,
            consultas=_CONSULTAS_DETALLE,
            motivo="7 fichas de equipo (team_seasons) no salen: 6 de 2024-25 venían de una versión anterior del "
                   "raw (en la historia de git, no en el de hoy) y el importador nunca borra una ficha; 1 de 2019-20 "
                   "está en el raw, pero el importador de hoy ya no la escribe"),
    Dominio("portal", ("portal_groups", "groups", "matches", "standings"),
            ("scripts/wayback_portal_*_raw.json",), False,
            ambito=_ambito_portal, borrar=_borrar_portal, rehacer=_pasada,
            consultas=_CONSULTAS_PORTAL,
            motivo="la base guarda sus partidos ya corregidos y el importador los reescribe como los trae el "
                   "portal: 309 marcadores de 2016-19 distintos; en 2020-21 sus partidos van con otra jornada "
                   "('1' frente a 'Jornada 1') y salen duplicados; equipos renombrados en 2013-16; 2 grupos de "
                   "2016-17 y 2018-19 que ya no casan con su grupo de la base"),
    Dominio("mygol", ("mygol_torneos", "mygol_equipos", "mygol_jugadores", "mygol_partidos",
                      "mygol_participaciones"), ("scripts/mygol_*_raw.json",), True,
            ambito=_ambito_mygol, borrar=_borrar_mygol, rehacer=_rehacer_mygol, consultas=_CONSULTAS_MYGOL),
)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--comprobar", action="store_true", help="rehace cada dominio sobre una copia y compara")
    ap.add_argument("--dominio", action="append", help="solo este dominio (se puede repetir)")
    ap.add_argument("--db", default=str(ROOT / "futbolbase.db"), help="la base (solo se lee)")
    args = ap.parse_args(argv)
    if not args.comprobar:
        ap.print_help()
        return 2
    nombres = [d.nombre for d in DOMINIOS]
    pedidos = args.dominio or nombres
    if set(pedidos) - set(nombres):
        ap.error(f"dominio desconocido: {', '.join(sorted(set(pedidos) - set(nombres)))}")
    fallan = []
    t0 = time.monotonic()
    for d in (d for d in DOMINIOS if d.nombre in pedidos):
        r = comprobar(args.db, str(ROOT), [d])[d.nombre]
        estado = "igual" if r["igual"] else "DISTINTO"
        declarado = "rehacible" if d.rehacible else "no rehacible"
        print(f"{d.nombre:<11} {estado:<8} ({declarado}) {r['filas']} filas, {r['distintas']} distintas, "
              f"{r['segundos']} s", flush=True)
        print(f"            {r['detalle']}", flush=True)
        if not d.rehacible and d.motivo:
            print(f"            por qué no se rehace: {d.motivo}", flush=True)
        if d.rehacible and not r["igual"]:
            fallan.append(d.nombre)
    print(f"\n{round(time.monotonic() - t0, 1)} s en total.")
    if fallan:
        print(f"No salen iguales y están declarados rehacibles: {', '.join(fallan)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
