#!/usr/bin/env python3
"""La base en piezas: montar futbolbase.db a partir de base/, partirla al acabar y comprobar que salen iguales.

Por qué. La base vive dentro de git y el bot la sube cada hora. Hoy ocupa 41 MB, pero con todas las categorías
y las actas de siete temporadas pasará de 200 MB, y GitHub no admite ficheros de más de 100 MB (avisa desde 50;
aquí, desde 80, y no se sube desde 95). Por eso en git va partida (medido el 25/11/2026 sobre una copia):
  - base/comun.db: el esquema entero (tablas, índices, la vista match_staff) y todas las filas salvo las de
    las tres tablas pesadas, que van vacías. Hoy, 11 MB; con todo, 45-60 MB.
  - base/actas-<AAAA-AAAA>.db: las filas de appearances, match_events y match_staff_all de los partidos de
    esa temporada (matches.group_id → groups.season_id → seasons.name), sin índices secundarios. Hoy, de
    1,2 a 4 MB; con todo, 25-30 MB la mayor. Una temporada sin filas no tiene pieza.
  - base/piezas.json: qué piezas hay, sus bytes y cuántas filas lleva cada tabla.
Las piezas van en modo de diario DELETE, nunca WAL: git solo sube el fichero, y lo que quedara en un -wal se
perdería. La base montada sí va en WAL, como la de hoy.

Cada fila conserva su identidad: en una tabla WITHOUT ROWID, su clave primaria; en una con INTEGER PRIMARY
KEY, esa columna; en las demás (match_staff_all, venues, fp_goals…), su rowid, que se copia explícito. Así
montar devuelve la base con los mismos rowid, y dos filas iguales salvo el rowid siguen siendo dos.

Tres órdenes, desde la raíz del repositorio:
  python3 scripts/piezas.py montar [--db F] [--piezas D] [--solo-comun] [--contra F]
  python3 scripts/piezas.py partir [--db F] [--piezas D]
  python3 scripts/piezas.py verificar [--db F] [--piezas D]
y, para mirar a mano, comparar --db F --piezas D (monta D en un temporal y lo compara con F).

montar arma la base en un temporal junto al destino y solo la pone en su sitio (os.replace) si cuadra con el
manifiesto. partir escribe en cada pieza solo las filas que cambian, en una transacción; una pieza sin
cambios no se abre en escritura (ni un byte cambia, y git no ve nada). verificar monta las piezas en un
directorio temporal y compara, tabla a tabla, una huella de todas sus filas con la base: lo que no sea
idéntico no se sube. Detalles y decisiones: docs/almacenamiento.md.

Solo la biblioteca estándar: la copia del PC instala este fichero tal cual.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "futbolbase.db"
DIR_PIEZAS = ROOT / "base"
PESADAS = ("appearances", "match_events", "match_staff_all")
COMUN = "comun.db"
MANIFIESTO = "piezas.json"
FORMATO = 1
MB = 1024 * 1024
AVISO_MB = 80     # desde aquí, la web lo dice (tarea 7)
PARADA_MB = 95    # desde aquí no se sube: GitHub rechaza ficheros de 100 MB
GITHUB_MB = 100

# Los pragmas que forman parte del esquema. Los tres primeros, distintos, rehacen la pieza; user_version y
# application_id solo los lleva comun.db y se igualan en sitio.
PRAGMAS = ("page_size", "auto_vacuum", "encoding", "user_version", "application_id")
PRAGMAS_FICHERO = ("page_size", "auto_vacuum", "encoding")
SOLO_COMUN = "solo-comun"     # lo que lleva <destino>.piezas tras montar --solo-comun

_NOMBRE_PIEZA = re.compile(r"actas-([0-9]{4}-[0-9]{4})\.db")
_TROZO = 5000                 # filas por vuelta al leer la huella
_TEMPORAL = re.compile(r"\..+\.tmp(-journal|-wal|-shm)?")


class PiezasError(Exception):
    """Lo que impide montar o partir. El texto, en español, dice qué y dónde."""


def nombre_pieza(temporada: str) -> str:
    """'2025-2026' → 'actas-2025-2026.db'. Solo cuatro cifras, un guion y cuatro cifras: el nombre de la
    temporada acaba en un nombre de fichero."""
    if not isinstance(temporada, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{4}", temporada):
        raise ValueError(f"temporada con un nombre que no es AAAA-AAAA: {temporada!r}")
    return f"actas-{temporada}.db"


# ---------------------------------------------------------------- conexiones

def _q(nombre) -> str:
    """Un identificador entre comillas dobles, para cualquier nombre de tabla o columna."""
    return '"' + str(nombre).replace('"', '""') + '"'


def _texto(datos: bytes) -> str:
    """Un TEXT con bytes que no son UTF-8 se lee igual (surrogateescape) en vez de fallar: la huella los ve."""
    return datos.decode("utf-8", "surrogateescape")


def _uri(path, modo) -> str:
    return Path(path).resolve().as_uri() + "?mode=" + modo


def _abrir(path, modo="ro"):
    """Sin transacciones implícitas (BEGIN y COMMIT, a mano) y sin claves ajenas: copiar filas en cualquier
    orden no puede fallar ni borrar nada en cascada."""
    conn = sqlite3.connect(_uri(path, modo), uri=True, isolation_level=None)
    conn.text_factory = _texto
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def _adjuntar(conn, path, alias, modo="ro"):
    conn.execute(f"ATTACH DATABASE ? AS {_q(alias)}", (_uri(path, modo),))


def _cerrar(conn):
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    finally:
        conn.close()


# ---------------------------------------------------------------- identidad, columnas, huella, esquema

def _info(conn, tabla, esquema):
    filas = conn.execute(f"PRAGMA {_q(esquema)}.table_xinfo({_q(tabla)})").fetchall()
    if not filas:
        raise PiezasError(f"no está la tabla {tabla} en {esquema}")
    return filas


def identidad(conn, tabla: str, esquema: str = "main") -> list:
    """Lo que identifica cada fila: las columnas de la clave primaria en una WITHOUT ROWID, la columna en una
    con INTEGER PRIMARY KEY (es el rowid), y si no, ['rowid']."""
    info = _info(conn, tabla, esquema)
    clave = [nombre for _, nombre in sorted((f[5], f[1]) for f in info if f[5])]
    de_la_clave = [f[1] for f in conn.execute(f"PRAGMA {_q(esquema)}.index_list({_q(tabla)})") if f[3] == "pk"]
    if clave and de_la_clave:
        # Una clave con índice propio: en una WITHOUT ROWID ese índice es la tabla y no sale en sqlite_master.
        listado = conn.execute(f"SELECT 1 FROM {_q(esquema)}.sqlite_master WHERE type = 'index' AND name = ?",
                               (de_la_clave[0],)).fetchone()
        if listado is None:
            return clave
    elif len(clave) == 1:
        return clave        # INTEGER PRIMARY KEY: sin índice, porque es el rowid
    if any(f[1].lower() == "rowid" for f in info):
        raise PiezasError(f"{tabla}: una columna se llama rowid y no se sabría copiar el rowid de verdad")
    return ["rowid"]


def columnas(conn, tabla: str, esquema: str = "main") -> list:
    """La identidad y después el resto de columnas, en su orden y sin repetir. Las generadas no: se calculan."""
    ident = identidad(conn, tabla, esquema)
    return ident + [f[1] for f in _info(conn, tabla, esquema) if f[6] == 0 and f[1] not in ident]


def _sin_afinidad(conn, tabla, esquema):
    """Las columnas sin afinidad (sin tipo o BLOB): las únicas donde caben 1 y 1.0 a la vez, que EXCEPT da por
    iguales. En ellas se compara también typeof()."""
    fuera = set()
    for f in _info(conn, tabla, esquema):
        tipo = (f[2] or "").upper()
        if "INT" in tipo or any(t in tipo for t in ("CHAR", "CLOB", "TEXT")):
            continue
        if "BLOB" in tipo or not tipo:
            fuera.add(f[1])
    return fuera


def huella(conn, tabla: str, esquema: str = "main") -> tuple:
    """(filas, sha256) de todas las filas de la tabla en el orden de su identidad, cada una como
    repr(tuple(fila)) en UTF-8 y un salto de línea. repr distingue 1, 1.0, '1' y b'1', y da todos los
    decimales de un REAL. sqlite_sequence, por (name, seq) ordenada por name."""
    s = _q(esquema)
    if tabla == "sqlite_sequence":
        sql = f"SELECT name, seq FROM {s}.sqlite_sequence ORDER BY name, seq"
    else:
        cols = columnas(conn, tabla, esquema)
        orden = ", ".join(map(_q, identidad(conn, tabla, esquema)))
        sql = f"SELECT {', '.join(map(_q, cols))} FROM {s}.{_q(tabla)} ORDER BY {orden}"
    h = hashlib.sha256()
    n = 0
    cur = conn.execute(sql)
    while True:
        filas = cur.fetchmany(_TROZO)
        if not filas:
            break
        h.update(b"".join(repr(tuple(f)).encode("utf-8") + b"\n" for f in filas))
        n += len(filas)
    return n, h.hexdigest()


def _maestro(conn, esquema="main"):
    return [tuple(f) for f in conn.execute(
        f"SELECT type, name, tbl_name, sql FROM {_q(esquema)}.sqlite_master ORDER BY type, name")]


def _pragma(conn, esquema, nombre):
    return conn.execute(f"PRAGMA {_q(esquema)}.{nombre}").fetchone()[0]


def esquema(conn, esquema: str = "main") -> list:
    """(type, name, tbl_name, sql) de sqlite_master por (type, name), y los cinco pragmas como
    ('pragma', nombre, valor)."""
    return _maestro(conn, esquema) + [("pragma", p, _pragma(conn, esquema, p)) for p in PRAGMAS]


def _tablas(conn, esquema="main"):
    return [n for (n,) in conn.execute(
        f"SELECT name FROM {_q(esquema)}.sqlite_master WHERE type = 'table' ORDER BY name")]


def _contar(conn, esquema, tabla):
    return conn.execute(f"SELECT count(*) FROM {_q(esquema)}.{_q(tabla)}").fetchone()[0]


# ---------------------------------------------------------------- comparar

def comparar(a: Path, b: Path) -> list:
    """Vacía si las dos bases tienen el mismo esquema() y, tabla a tabla, la misma huella(). Si no, una frase
    por diferencia."""
    for p in (a, b):
        if not Path(p).is_file():
            raise PiezasError(f"no está {p}")
    ca, cb = _abrir(a), _abrir(b)
    try:
        dif = []
        ea, eb = esquema(ca), esquema(cb)
        if ea != eb:
            da = {(f[0], f[1]): f for f in ea}
            db_ = {(f[0], f[1]): f for f in eb}
            for clave in sorted(set(da) | set(db_)):
                tipo, nombre = clave
                if clave not in db_:
                    dif.append(f"esquema: {tipo} {nombre} solo en la primera")
                elif clave not in da:
                    dif.append(f"esquema: {tipo} {nombre} solo en la segunda")
                elif da[clave] != db_[clave]:
                    if tipo == "pragma":
                        dif.append(f"pragma {nombre}: {da[clave][2]} y {db_[clave][2]}")
                    else:
                        dif.append(f"esquema: {tipo} {nombre} distinto")
        comunes = sorted(set(_tablas(ca)) & set(_tablas(cb)))
        for tabla in comunes:
            ha, hb = huella(ca, tabla), huella(cb, tabla)
            if ha[0] != hb[0]:
                dif.append(f"{tabla}: {ha[0]} filas y {hb[0]}")
            elif ha[1] != hb[1]:
                dif.append(f"{tabla}: las mismas {ha[0]} filas, con otro contenido")
        return dif
    finally:
        ca.close()
        cb.close()


# ---------------------------------------------------------------- ficheros

def _sincroniza_carpeta(carpeta):
    try:
        fd = os.open(carpeta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _fsync(path):
    with open(path, "rb+") as f:
        os.fsync(f.fileno())


def escribir_atomico(path, contenido, *, encoding="utf-8") -> None:
    """El mismo patrón que scripts/escritura.py (aquí, para no importar nada del proyecto): temporal en la misma
    carpeta, fsync y os.replace. Un corte deja el fichero de antes o el nuevo, nunca uno a medias."""
    path = os.fspath(path)
    carpeta, nombre = os.path.split(os.path.abspath(path))
    try:
        permisos = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        permisos = 0o644
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix="." + nombre + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido.encode(encoding) if isinstance(contenido, str) else contenido)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, permisos)
        os.replace(tmp, path)
    except BaseException:
        _quitar(tmp)
        raise
    _sincroniza_carpeta(carpeta)


def _quitar(*paths):
    for p in paths:
        for extra in ("", "-journal", "-wal", "-shm"):
            try:
                os.unlink(f"{p}{extra}")
            except FileNotFoundError:
                pass


def _temporal(junto_a: Path) -> Path:
    """Un temporal junto al fichero (.<nombre>.<azar>.tmp), con los permisos del de antes o 0644: mkstemp lo
    crea con 0600 y la base o la pieza saldrían solo para su dueño."""
    try:
        permisos = stat.S_IMODE(os.stat(junto_a).st_mode)
    except FileNotFoundError:
        permisos = 0o644
    fd, tmp = tempfile.mkstemp(dir=junto_a.parent, prefix=f".{junto_a.name}.", suffix=".tmp")
    os.close(fd)
    os.chmod(tmp, permisos)
    return Path(tmp)


def _texto_manifiesto(piezas: dict) -> str:
    return json.dumps({"formato": FORMATO, "piezas": piezas}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _leer_manifiesto(carpeta: Path):
    """(manifiesto, sha256 de su texto). PiezasError si falta, no se entiende o nombra un fichero raro."""
    ruta = carpeta / MANIFIESTO
    if not ruta.is_file():
        raise PiezasError(f"no está {ruta}")
    datos = ruta.read_bytes()
    try:
        man = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PiezasError(f"{ruta} no se entiende: {e}") from None
    if not isinstance(man, dict) or man.get("formato") != FORMATO or not isinstance(man.get("piezas"), dict):
        raise PiezasError(f"{ruta}: no es del formato {FORMATO}")
    for fichero, pieza in man["piezas"].items():
        if fichero != COMUN and not _NOMBRE_PIEZA.fullmatch(fichero):
            raise PiezasError(f"{ruta} nombra un fichero que no es una pieza: {fichero}")
        if (not isinstance(pieza, dict) or not isinstance(pieza.get("bytes"), int)
                or not isinstance(pieza.get("filas"), dict)):
            raise PiezasError(f"{ruta}: la entrada de {fichero} está incompleta")
    if COMUN not in man["piezas"]:
        raise PiezasError(f"{ruta} no nombra {COMUN}")
    return man, hashlib.sha256(datos).hexdigest()


def _cabecera_delete(path) -> bool:
    """Bytes 18 y 19 de la cabecera: 1 y 1 en modo de diario clásico (DELETE), 2 y 2 en WAL."""
    with open(path, "rb") as f:
        cabecera = f.read(20)
    return len(cabecera) == 20 and cabecera[18:20] == b"\x01\x01"


# ---------------------------------------------------------------- lo que tiene la base

def _admisible(conn, esquema_base="w"):
    """Lo que no se sabría partir ni montar sin perder algo: triggers (se dispararían al copiar), tablas
    internas que no son sqlite_sequence (sqlite_stat1 de un ANALYZE…), tablas virtuales; y las tres pesadas
    tienen que estar, con su match_id."""
    s = _q(esquema_base)
    disparadores = [n for (n,) in conn.execute(f"SELECT name FROM {s}.sqlite_master WHERE type = 'trigger' "
                                               "ORDER BY name")]
    if disparadores:
        raise PiezasError(f"la base tiene triggers ({', '.join(disparadores)}): no se sabría montarla sin que "
                          "se disparen")
    internas = [n for n in _tablas(conn, esquema_base) if n.lower().startswith("sqlite_") and n != "sqlite_sequence"]
    if internas:
        raise PiezasError(f"la base tiene tablas internas ({', '.join(internas)}): bórralas antes de partirla")
    virtuales = [n for (n,) in conn.execute(f"SELECT name FROM {s}.sqlite_master WHERE type = 'table' "
                                            "AND upper(sql) LIKE 'CREATE VIRTUAL TABLE%' ORDER BY name")]
    if virtuales:
        raise PiezasError(f"la base tiene tablas virtuales ({', '.join(virtuales)}): no se saben partir")
    tablas = set(_tablas(conn, esquema_base))
    for tabla in PESADAS + ("matches", "groups", "seasons"):
        if tabla not in tablas:
            raise PiezasError(f"la base no tiene la tabla {tabla}")
    for tabla in PESADAS:
        if "match_id" not in columnas(conn, tabla, esquema_base):
            raise PiezasError(f"la tabla {tabla} no tiene match_id: no se sabe de qué temporada es cada fila")


def _mapa(conn):
    """La temporada de cada partido, en una tabla temporal con índice: la usan todas las consultas de la
    conexión que separan las filas pesadas por temporada."""
    conn.execute("CREATE TEMP TABLE _temporada (match_id INTEGER PRIMARY KEY, temporada TEXT NOT NULL)")
    conn.execute("INSERT INTO temp._temporada SELECT m.id, s.name FROM w.matches m "
                 "JOIN w.groups g ON g.id = m.group_id JOIN w.seasons s ON s.id = g.season_id")
    conn.execute("CREATE INDEX temp._temporada_t ON _temporada (temporada, match_id)")


def _de_la_temporada(tabla_alias):
    return (f"{tabla_alias}.match_id IN (SELECT tt.match_id FROM temp._temporada tt "
            "WHERE tt.temporada = :temporada)")


def _seleccion(conn, tabla, esquema_tabla, temporada=None, info_de="w"):
    """SELECT de todas las columnas (c0, c1…; la identidad, primero) para EXCEPT: con COLLATE BINARY, para que
    'a' y 'A' no salgan iguales en una columna NOCASE, y con typeof() en las columnas sin afinidad."""
    cols = columnas(conn, tabla, info_de)
    sin = _sin_afinidad(conn, tabla, info_de)
    partes = [f"{_q(c)} COLLATE BINARY AS c{k}" for k, c in enumerate(cols)]
    partes += [f"typeof({_q(c)}) AS t{k}" for k, c in enumerate(cols) if c in sin]
    sql = f"SELECT {', '.join(partes)} FROM {_q(esquema_tabla)}.{_q(tabla)} AS x"
    if temporada is not None:
        sql += " WHERE " + _de_la_temporada("x")
    return sql


class _Base:
    """Lo que partir necesita saber de la base, leído una vez por llamada: una conexión en memoria con la base
    adjunta en solo lectura (w) y la temporada de cada partido (temp._temporada)."""

    def __init__(self, db: Path):
        self.db = db
        primera = _abrir(db)
        try:
            codificacion = _pragma(primera, "main", "encoding")
        finally:
            primera.close()
        self.conn = sqlite3.connect(":memory:", uri=True, isolation_level=None)
        self.conn.text_factory = _texto
        # Una base adjunta tiene que tener la codificación de la principal.
        self.conn.execute(f"PRAGMA encoding = '{codificacion}'")
        try:
            self._leer()
        except BaseException:
            self.conn.close()
            raise

    def _leer(self):
        db = self.db
        _adjuntar(self.conn, db, "w")
        _admisible(self.conn)
        _mapa(self.conn)
        c = self.conn
        self.maestro = [tuple(f) for f in c.execute(
            "SELECT type, name, tbl_name, sql FROM w.sqlite_master ORDER BY rowid")]
        self.pragmas = {p: _pragma(c, "w", p) for p in PRAGMAS}
        self.tablas = _tablas(c, "w")
        self.comunes = [t for t in self.tablas if t not in PESADAS and t != "sqlite_sequence"]
        self._sin_temporada()
        self.filas_comun = {t: _contar(c, "w", t) for t in self.comunes}
        self.temporadas = {}
        for tabla in PESADAS:
            total = _contar(c, "w", tabla)
            repartidas = 0
            for temporada, n in c.execute(
                    f"SELECT tt.temporada, count(*) FROM w.{_q(tabla)} x JOIN temp._temporada tt "
                    "ON tt.match_id = x.match_id GROUP BY tt.temporada"):
                self.temporadas.setdefault(temporada, dict.fromkeys(PESADAS, 0))[tabla] = n
                repartidas += n
            if repartidas != total:
                raise PiezasError(f"{tabla}: {total} filas en la base y {repartidas} repartidas por temporadas")
        for temporada in self.temporadas:
            try:
                nombre_pieza(temporada)
            except ValueError as e:
                raise PiezasError(f"no se sabe dónde guardar las actas de la temporada {temporada!r}: {e}") from None
        self.total_pesadas = sum(sum(t.values()) for t in self.temporadas.values())

    def _sin_temporada(self):
        """Filas pesadas de un partido que no está, o cuyo grupo o temporada no están: no tienen pieza."""
        problemas = []
        for tabla in PESADAS:
            fuera = (f"FROM w.{_q(tabla)} x WHERE NOT EXISTS (SELECT 1 FROM temp._temporada tt "
                     "WHERE tt.match_id = x.match_id)")
            n = self.conn.execute(f"SELECT count(*) {fuera}").fetchone()[0]
            if n:
                ids = [str(r[0]) for r in self.conn.execute(
                    f"SELECT DISTINCT x.match_id {fuera} ORDER BY 1 LIMIT 20")]
                problemas.append(f"{n} de {tabla} (partidos {', '.join(ids)})")
        if problemas:
            raise PiezasError("filas sin temporada (su partido, su grupo o su temporada no están): "
                              + "; ".join(problemas))

    def entradas_pesadas(self):
        """Lo que crea en sqlite_master el CREATE TABLE de las pesadas: la tabla y sus autoíndices."""
        return sorted(f for f in self.maestro if f[2] in PESADAS and (f[0] == "table" or f[3] is None))

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------- partir

def _corte():
    """Solo para las pruebas: PIEZAS_CORTE_PRUEBA=tras:<n> o dentro:<n> simula un corte en la pieza n."""
    m = re.fullmatch(r"(tras|dentro):([0-9]+)", os.environ.get("PIEZAS_CORTE_PRUEBA", ""))
    return (m.group(1), int(m.group(2))) if m else None


_MAGIA_DIARIO = bytes.fromhex("d9d505f920a163d7")


def _rescatar(carpeta: Path):
    """Una pieza con un -journal al lado es una transacción cortada: al abrirla en escritura y leerla, SQLite
    la devuelve a su último commit y borra el diario. Si el corte llegó antes de que SQLite escribiera nada en
    la pieza, el diario tiene la cabecera a ceros: no está «caliente», SQLite lo deja y aquí se borra."""
    for diario in sorted(carpeta.glob("*.db-journal")):
        pieza = carpeta / diario.name[: -len("-journal")]
        if not pieza.exists():
            if diario.stat().st_size == 0:
                diario.unlink()
                continue
            raise PiezasError(f"hay un diario sin su pieza: {diario}")
        conn = _abrir(pieza, "rw")
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            conn.close()
        if diario.exists():
            with open(diario, "rb") as f:
                cabecera = f.read(8)
            if cabecera == _MAGIA_DIARIO:
                raise PiezasError(f"no se pudo devolver {pieza.name} a su último commit: queda {diario.name}")
            diario.unlink()


def _limpiar_temporales(carpeta: Path):
    """Los temporales de un rehacer o de un manifiesto que se cortaron (.<fichero>.<azar>.tmp)."""
    for resto in carpeta.iterdir():
        if _TEMPORAL.fullmatch(resto.name):
            resto.unlink()


def _contar_pieza(conn, esquema_pieza, tablas):
    """Filas de las tablas de una pieza, o None si no se pueden contar (pieza rota)."""
    try:
        return sum(_contar(conn, esquema_pieza, t) for t in tablas if t in _tablas(conn, esquema_pieza))
    except sqlite3.DatabaseError:
        return None


def _mismo_esquema(base: _Base, alias, comun: bool) -> bool:
    c = base.conn
    for p in PRAGMAS_FICHERO:
        if _pragma(c, alias, p) != base.pragmas[p]:
            return False
    if comun:
        return _maestro(c, alias) == _maestro(c, "w")
    propias = sorted(f for f in _maestro(c, alias) if f[1] != "sqlite_sequence")
    return propias == [f for f in base.entradas_pesadas() if f[1] != "sqlite_sequence"]


def _diferencias(base: _Base, alias, temporada):
    """({tabla: (nuevas, sobran)} con diferencias, si hay algo más que igualar: sqlite_sequence o los pragmas),
    o (None, None) si la pieza hay que rehacerla. Solo lee: la pieza está adjunta en solo lectura."""
    c = base.conn
    params = {"temporada": temporada}
    tablas = PESADAS if temporada is not None else base.comunes
    cambios = {}
    for tabla in tablas:
        de_base = _seleccion(c, tabla, "w", temporada)
        de_pieza = _seleccion(c, tabla, alias)
        nuevas = c.execute(f"SELECT count(*) FROM ({de_base} EXCEPT {de_pieza})", params).fetchone()[0]
        sobran = c.execute(f"SELECT count(*) FROM ({de_pieza} EXCEPT {de_base})", params).fetchone()[0]
        if nuevas or sobran:
            cambios[tabla] = (nuevas, sobran)
    otro = False
    if temporada is None:
        if any(_contar(c, alias, t) for t in PESADAS):
            return None, None           # comun.db con filas pesadas: se rehace entera
        otro = any(_pragma(c, alias, p) != base.pragmas[p] for p in ("user_version", "application_id"))
        if "sqlite_sequence" in base.tablas:
            sec = "SELECT name, seq, typeof(seq) FROM {}.sqlite_sequence"
            otro = otro or bool(
                c.execute(f"SELECT count(*) FROM ({sec.format('w')} EXCEPT {sec.format(_q(alias))})").fetchone()[0]
                or c.execute(f"SELECT count(*) FROM ({sec.format(_q(alias))} EXCEPT {sec.format('w')})").fetchone()[0]
                or _contar(c, "w", "sqlite_sequence") != _contar(c, alias, "sqlite_sequence"))
    return cambios, otro


def _igualar_comun(conn, base: _Base):
    """sqlite_sequence, user_version y application_id de comun.db, los de la base."""
    if "sqlite_sequence" in base.tablas:
        conn.execute("DELETE FROM main.sqlite_sequence")
        conn.execute("INSERT INTO main.sqlite_sequence (name, seq) SELECT name, seq FROM w.sqlite_sequence "
                     "ORDER BY rowid")
    for p in ("user_version", "application_id"):
        conn.execute(f"PRAGMA main.{p} = {int(base.pragmas[p])}")


def _comprobar_filas(conn, esperadas, donde):
    for tabla, n in esperadas.items():
        hay = _contar(conn, "main", tabla)
        if hay != n:
            raise PiezasError(f"{donde}: {tabla} tiene {hay} filas y la base {n}")


def _esperadas(base: _Base, temporada):
    return dict(base.filas_comun) if temporada is None else dict(base.temporadas[temporada])


def _rehacer(base: _Base, ruta: Path, temporada, corte, numero):
    """La pieza entera, en un temporal junto a ella, con los CREATE de la base letra a letra; después,
    os.replace. Devuelve las filas que lleva."""
    comun = temporada is None
    tmp = _temporal(ruta)
    try:
        conn = _abrir(tmp, "rw")
        try:
            # Antes de crear nada: el tamaño de página, el auto_vacuum y la codificación de la base.
            conn.execute(f"PRAGMA page_size = {int(base.pragmas['page_size'])}")
            conn.execute(f"PRAGMA auto_vacuum = {int(base.pragmas['auto_vacuum'])}")
            conn.execute(f"PRAGMA encoding = '{base.pragmas['encoding']}'")
            # Un temporal: si algo falla se borra entero, así que no hace falta diario mientras se llena.
            conn.execute("PRAGMA main.journal_mode = OFF")
            conn.execute("PRAGMA main.synchronous = OFF")
            _adjuntar(conn, base.db, "w")
            if not comun:
                _mapa(conn)
            conn.execute("BEGIN")
            tablas = base.comunes if comun else list(PESADAS)
            crear = [sql for tipo, nombre, _, sql in base.maestro
                     if tipo == "table" and sql and nombre != "sqlite_sequence" and (comun or nombre in PESADAS)]
            for sql in crear:
                conn.execute(sql)
            params = {"temporada": temporada}
            for tabla in tablas:
                cols = ", ".join(map(_q, columnas(conn, tabla, "w")))
                orden = ", ".join(map(_q, identidad(conn, tabla, "w")))
                donde = "" if comun else " WHERE " + _de_la_temporada("x")
                conn.execute(f"INSERT INTO main.{_q(tabla)} ({cols}) SELECT {cols} FROM w.{_q(tabla)} AS x"
                             f"{donde} ORDER BY {orden}", params)
            if comun:
                # Los índices, después de las filas (se ordenan de una vez), y las vistas.
                for tipo in ("index", "view"):
                    for t, _, _, sql in base.maestro:
                        if t == tipo and sql:
                            conn.execute(sql)
                _igualar_comun(conn, base)
            esperadas = _esperadas(base, temporada)
            _comprobar_filas(conn, esperadas, ruta.name)
            hecho = _maestro(conn)
            if comun:
                if hecho != _maestro(base.conn, "w"):
                    raise PiezasError(f"{ruta.name}: el esquema rehecho no es el de la base")
            elif sorted(f for f in hecho if f[1] != "sqlite_sequence") != [
                    f for f in base.entradas_pesadas() if f[1] != "sqlite_sequence"]:
                raise PiezasError(f"{ruta.name}: el esquema rehecho no es el de las tablas pesadas de la base")
            conn.execute("COMMIT")
            if conn.execute("PRAGMA main.journal_mode = DELETE").fetchone()[0] != "delete":
                raise PiezasError(f"{ruta.name}: no se pudo dejar en modo DELETE")
        finally:
            _cerrar(conn)
        _fsync(tmp)
        if corte == ("dentro", numero):
            os._exit(3)
        os.replace(tmp, ruta)
        # El -wal y el -shm de una pieza que estaba en WAL serían de otra base: fuera.
        for sufijo in ("-wal", "-shm"):
            try:
                os.unlink(f"{ruta}{sufijo}")
            except FileNotFoundError:
                pass
        _sincroniza_carpeta(ruta.parent)
    except BaseException:
        _quitar(tmp)
        raise
    return sum(esperadas.values())


def _aplicar(base: _Base, ruta: Path, temporada, corte, numero):
    """Las diferencias, en sitio y en una transacción: se borran por identidad las filas que sobran o
    cambiaron y se insertan las nuevas o cambiadas. Devuelve (insertadas, borradas)."""
    comun = temporada is None
    tablas = base.comunes if comun else list(PESADAS)
    params = {"temporada": temporada}
    conn = _abrir(ruta, "rw")
    try:
        _adjuntar(conn, base.db, "w")
        if not comun:
            _mapa(conn)
        conn.execute("BEGIN IMMEDIATE")
        borradas = insertadas = 0
        for tabla in tablas:
            ident = identidad(conn, tabla, "w")
            k = len(ident)
            de_base = _seleccion(conn, tabla, "w", temporada)
            de_pieza = _seleccion(conn, tabla, "main")
            # Sin tipo en la tabla temporal: los valores pasan tal cual, sin conversiones de afinidad.
            conn.execute(f"CREATE TEMP TABLE _sobran ({', '.join(f'i{j}' for j in range(k))})")
            conn.execute(f"INSERT INTO temp._sobran SELECT {', '.join(f'c{j}' for j in range(k))} "
                         f"FROM ({de_pieza} EXCEPT {de_base})", params)
            n = conn.execute("SELECT count(*) FROM temp._sobran").fetchone()[0]
            if n:
                izquierda = _q(ident[0]) if k == 1 else "(" + ", ".join(map(_q, ident)) + ")"
                cur = conn.execute(f"DELETE FROM main.{_q(tabla)} WHERE {izquierda} IN "
                                   f"(SELECT {', '.join(f'i{j}' for j in range(k))} FROM temp._sobran)")
                if cur.rowcount != n:
                    raise PiezasError(f"{ruta.name}: {tabla}: había que borrar {n} filas y se borraron "
                                      f"{cur.rowcount}")
            conn.execute("DROP TABLE temp._sobran")
            borradas += n
        if corte == ("dentro", numero):
            os._exit(3)
        for tabla in tablas:
            cols = columnas(conn, tabla, "w")
            de_base = _seleccion(conn, tabla, "w", temporada)
            de_pieza = _seleccion(conn, tabla, "main")
            # Lo que queda en la pieza ya es parte de la base: lo que falta es exactamente esto.
            cur = conn.execute(f"INSERT INTO main.{_q(tabla)} ({', '.join(map(_q, cols))}) "
                               f"SELECT {', '.join(f'c{j}' for j in range(len(cols)))} "
                               f"FROM ({de_base} EXCEPT {de_pieza})", params)
            insertadas += cur.rowcount
        if comun:
            _igualar_comun(conn, base)
        _comprobar_filas(conn, _esperadas(base, temporada), ruta.name)
        conn.execute("COMMIT")
    finally:
        _cerrar(conn)
    return insertadas, borradas


def partir(db: Path, dir_piezas: Path) -> dict:
    """Deja en dir_piezas las piezas de db, tocando solo las que cambian. Devuelve
    {'creadas': [...], 'cambiadas': {fichero: (insertadas, borradas)}, 'borradas': [...], 'intactas': [...]}.
    Volver a llamarla tras un corte arregla lo que quedó a medias."""
    db, carpeta = Path(db), Path(dir_piezas)
    if not db.is_file():
        raise PiezasError(f"no está la base {db}")
    marca = Path(f"{db}.piezas")
    if marca.is_file() and SOLO_COMUN in marca.read_text(encoding="utf-8", errors="replace"):
        raise PiezasError(f"{db} se montó solo con la parte común: partirla borraría las actas")
    carpeta.mkdir(parents=True, exist_ok=True)
    _limpiar_temporales(carpeta)
    _rescatar(carpeta)
    corte = _corte()
    try:
        anterior, _ = _leer_manifiesto(carpeta)
    except PiezasError:
        anterior = None
    try:
        base = _Base(db)
    except sqlite3.Error as e:
        raise PiezasError(f"no se pudo leer {db}: {e}") from None
    try:
        if anterior and base.total_pesadas == 0 and any(
                n for f, p in anterior["piezas"].items() if f != COMUN for n in p["filas"].values()):
            raise PiezasError(f"{db} está sin actas y las piezas tienen: ¿montada con --solo-comun? No se parte")
        objetivo = {COMUN: None}
        objetivo.update({nombre_pieza(t): t for t in base.temporadas})
        r = {"creadas": [], "cambiadas": {}, "borradas": [], "intactas": []}
        numero = 0
        for fichero in sorted(objetivo):
            ruta = carpeta / fichero
            temporada = objetivo[fichero]
            comun = temporada is None
            tablas = base.comunes if comun else list(PESADAS)
            if not ruta.exists():
                numero += 1
                _rehacer(base, ruta, temporada, corte, numero)
                r["creadas"].append(fichero)
            else:
                cambios = otro = None
                viejas = None
                try:
                    if not _cabecera_delete(ruta):
                        # En WAL (o sin cabecera): git solo subiría el fichero. Se rehace en modo DELETE.
                        raise sqlite3.DatabaseError("pieza que no está en modo DELETE")
                    _adjuntar(base.conn, ruta, "p")
                    try:
                        viejas = _contar_pieza(base.conn, "p", tablas)
                        if _mismo_esquema(base, "p", comun):
                            cambios, otro = _diferencias(base, "p", temporada)
                    finally:
                        base.conn.execute("DETACH DATABASE p")
                except sqlite3.DatabaseError:
                    cambios = None            # una pieza rota: se rehace
                if cambios is None:
                    numero += 1
                    filas = _rehacer(base, ruta, temporada, corte, numero)
                    r["cambiadas"][fichero] = (filas, viejas or 0)
                elif cambios or otro:
                    numero += 1
                    r["cambiadas"][fichero] = _aplicar(base, ruta, temporada, corte, numero)
                else:
                    r["intactas"].append(fichero)
                    continue
            if corte == ("tras", numero):
                os._exit(3)
        for ruta in sorted(carpeta.glob("actas-*.db")):
            if ruta.name not in objetivo and _NOMBRE_PIEZA.fullmatch(ruta.name):
                ruta.unlink()
                r["borradas"].append(ruta.name)
        if r["borradas"]:
            _sincroniza_carpeta(carpeta)
        manifiesto = {f: {"bytes": (carpeta / f).stat().st_size, "filas": _esperadas(base, objetivo[f])}
                      for f in objetivo}
    except sqlite3.Error as e:
        raise PiezasError(f"error de SQLite al partir {db}: {e}") from None
    finally:
        base.close()
    texto = _texto_manifiesto(manifiesto)
    ruta_man = carpeta / MANIFIESTO
    if not ruta_man.is_file() or ruta_man.read_bytes() != texto.encode("utf-8"):
        escribir_atomico(ruta_man, texto)
    escribir_atomico(marca, hashlib.sha256(texto.encode("utf-8")).hexdigest() + "\n")
    return r


# ---------------------------------------------------------------- montar

def _quitar_transitorios(destino: Path):
    """Un -wal, -shm o -journal junto al destino serían de otra base. Con datos, no se monta (serían cambios sin
    volcar); vacíos, se quitan."""
    for sufijo in ("-wal", "-journal"):
        resto = Path(f"{destino}{sufijo}")
        if resto.exists() and resto.stat().st_size > 0:
            raise PiezasError(f"hay datos sin volcar en {resto}: no se monta encima")
    for sufijo in ("-wal", "-shm", "-journal"):
        try:
            os.unlink(f"{destino}{sufijo}")
        except FileNotFoundError:
            pass


def montar(dir_piezas: Path, destino: Path, *, solo_comun: bool = False, contra=None) -> dict:
    """Arma la base de dir_piezas en un temporal junto a destino, la comprueba contra el manifiesto y, solo si
    todo cuadra (y con contra, si es igual a ese fichero), la pone en destino. Devuelve las filas por tabla."""
    carpeta, destino = Path(dir_piezas), Path(destino)
    man, sha = _leer_manifiesto(carpeta)
    diarios = sorted(p.name for p in carpeta.glob("*-journal"))
    if diarios:
        raise PiezasError(f"partir se cortó a medias: {', '.join(diarios)} (vuelve a partir antes de montar)")
    en_carpeta = {p.name for p in carpeta.glob("*.db")}
    nombradas = set(man["piezas"])
    usar = [COMUN] if solo_comun else [COMUN] + sorted(nombradas - {COMUN})
    if not solo_comun:
        faltan, sobran = sorted(nombradas - en_carpeta), sorted(en_carpeta - nombradas)
        if faltan or sobran:
            raise PiezasError(f"las piezas de {carpeta} no son las del manifiesto: "
                              + "; ".join(([f"faltan {', '.join(faltan)}"] if faltan else [])
                                          + ([f"sobran {', '.join(sobran)}"] if sobran else [])))
    for fichero in usar:
        ruta = carpeta / fichero
        if not ruta.is_file():
            raise PiezasError(f"falta {ruta}")
        if ruta.stat().st_size != man["piezas"][fichero]["bytes"]:
            raise PiezasError(f"{fichero} ocupa {ruta.stat().st_size} bytes y el manifiesto dice "
                              f"{man['piezas'][fichero]['bytes']}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = _temporal(destino)
    donde = COMUN
    try:
        shutil.copyfile(carpeta / COMUN, tmp)
        conn = _abrir(tmp, "rw")
        try:
            conn.execute("PRAGMA main.journal_mode = OFF")      # un temporal: si falla, se borra
            conn.execute("PRAGMA main.synchronous = OFF")
            if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise PiezasError(f"{COMUN} no pasa la comprobación de integridad")
            _comprobar_comun(conn, man)
            entradas = sorted(f for f in _maestro(conn) if f[2] in PESADAS and (f[0] == "table" or f[3] is None))
            for fichero in usar[1:]:
                donde = fichero
                _adjuntar(conn, carpeta / fichero, "p")
                conn.execute("BEGIN")
                propias = sorted(f for f in _maestro(conn, "p") if f[1] != "sqlite_sequence")
                if propias != [f for f in entradas if f[1] != "sqlite_sequence"]:
                    raise PiezasError(f"{fichero}: sus tablas no son las tablas pesadas de {COMUN} (el mismo "
                                      "CREATE TABLE)")
                filas = man["piezas"][fichero]["filas"]
                if set(filas) != set(PESADAS):
                    raise PiezasError(f"{fichero}: el manifiesto no da las filas de las tres tablas pesadas")
                for tabla in PESADAS:
                    hay = _contar(conn, "p", tabla)
                    if hay != filas[tabla]:
                        raise PiezasError(f"{fichero}: {tabla} tiene {hay} filas y el manifiesto dice "
                                          f"{filas[tabla]}")
                    cols = ", ".join(map(_q, columnas(conn, tabla, "main")))
                    orden = ", ".join(map(_q, identidad(conn, tabla, "main")))
                    conn.execute(f"INSERT INTO main.{_q(tabla)} ({cols}) SELECT {cols} FROM p.{_q(tabla)} "
                                 f"ORDER BY {orden}")
                conn.execute("COMMIT")
                conn.execute("DETACH DATABASE p")
            donde = destino.name
            for tabla in PESADAS:
                esperado = sum(man["piezas"][f]["filas"][tabla] for f in usar[1:])
                hay = _contar(conn, "main", tabla)
                if hay != esperado:
                    raise PiezasError(f"{tabla}: la base montada tiene {hay} filas y las piezas {esperado}")
            filas = {t: _contar(conn, "main", t) for t in _tablas(conn) if t != "sqlite_sequence"}
            if conn.execute("PRAGMA main.journal_mode = WAL").fetchone()[0] != "wal":
                raise PiezasError("no se pudo dejar la base montada en modo WAL")
        finally:
            _cerrar(conn)
        # Con la última conexión cerrada, SQLite vuelca el -wal y lo borra.
        if Path(f"{tmp}-wal").exists() and Path(f"{tmp}-wal").stat().st_size:
            raise PiezasError("la base montada dejó datos sin volcar en su -wal")
        _quitar_transitorios(tmp)
        if contra is not None:
            dif = comparar(Path(contra), tmp)
            # Leer en solo lectura una base en WAL deja su -wal y su -shm vacíos: son del temporal, fuera.
            _quitar_transitorios(tmp)
            if dif:
                raise PiezasError(f"la base montada y {contra} no son iguales: " + "; ".join(dif[:10]))
        _fsync(tmp)
        _quitar_transitorios(destino)
        os.replace(tmp, destino)
        _sincroniza_carpeta(destino.parent)
    except sqlite3.Error as e:
        _quitar(tmp)
        raise PiezasError(f"{donde}: {e}") from None
    except BaseException:
        _quitar(tmp)
        raise
    escribir_atomico(Path(f"{destino}.piezas"), sha + (f" {SOLO_COMUN}" if solo_comun else "") + "\n")
    return filas


def _comprobar_comun(conn, man):
    """comun.db: nada que no se sepa montar, las pesadas vacías y cada tabla con las filas del manifiesto."""
    s = conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    if s:
        raise PiezasError(f"{COMUN} tiene triggers: no se monta")
    tablas = _tablas(conn)
    for tabla in PESADAS:
        if tabla not in tablas:
            raise PiezasError(f"{COMUN} no tiene la tabla {tabla}")
        if _contar(conn, "main", tabla):
            raise PiezasError(f"{COMUN}: {tabla} tiene filas y tendría que ir vacía")
    filas = man["piezas"][COMUN]["filas"]
    propias = [t for t in tablas if t not in PESADAS and t != "sqlite_sequence"]
    if set(propias) != set(filas):
        raise PiezasError(f"{COMUN}: sus tablas no son las del manifiesto")
    for tabla in propias:
        hay = _contar(conn, "main", tabla)
        if hay != filas[tabla]:
            raise PiezasError(f"{COMUN}: {tabla} tiene {hay} filas y el manifiesto dice {filas[tabla]}")


# ---------------------------------------------------------------- verificar

def _mb(n):
    return f"{n / MB:.1f}".replace(".", ",")


def verificar(db: Path, dir_piezas: Path) -> dict:
    """¿Se pueden subir las piezas? {'ok', 'motivos', 'mayor': (fichero, bytes), 'total': bytes}. Monta las
    piezas en un directorio temporal del sistema y las compara con db; mira también los diarios, el modo de
    cada pieza, las que faltan o sobran y el tamaño de la mayor."""
    db, carpeta = Path(db), Path(dir_piezas)
    motivos = []
    for diario in sorted(carpeta.glob("*-journal")):
        motivos.append(f"partir se cortó a medias: {diario.name}")
    try:
        man, _ = _leer_manifiesto(carpeta)
    except PiezasError as e:
        man = None
        motivos.append(str(e))
    piezas_db = sorted(carpeta.glob("*.db"))
    for pieza in piezas_db:
        if not _cabecera_delete(pieza):
            motivos.append(f"la pieza {pieza.name} no está en modo DELETE: git solo subiría el fichero")
    if man is not None:
        conocidos = set(man["piezas"]) | {MANIFIESTO}
        for resto in sorted(carpeta.iterdir()):
            if resto.name not in conocidos and not resto.name.endswith("-journal"):
                motivos.append(f"sobra {resto.name} en {carpeta.name}/")
        for fichero in sorted(man["piezas"]):
            if fichero != COMUN and not (carpeta / fichero).exists():
                temporada = _NOMBRE_PIEZA.fullmatch(fichero).group(1)
                if _filas_de_temporada(db, temporada):
                    motivos.append(f"falta la pieza {fichero} y la base tiene actas de {temporada}")
        with tempfile.TemporaryDirectory(prefix="piezas-") as tmp:
            montada = Path(tmp) / "montada.db"
            try:
                montar(carpeta, montada)
            except PiezasError as e:
                motivos.append(str(e))
            else:
                motivos.extend(comparar(db, montada))
    tamanos = [(p.name, p.stat().st_size) for p in piezas_db]
    mayor = max(tamanos, key=lambda t: (t[1], t[0])) if tamanos else (None, 0)
    if mayor[0] is not None and mayor[1] >= PARADA_MB * MB:
        motivos.append(f"la pieza {mayor[0]} ocupa {mayor[1] // MB} MB y GitHub no admite más de {GITHUB_MB}")
    return {"ok": not motivos, "motivos": motivos, "mayor": mayor, "total": sum(t[1] for t in tamanos)}


def _filas_de_temporada(db, temporada) -> int:
    try:
        conn = _abrir(db)
    except sqlite3.Error:
        return 0
    try:
        return sum(conn.execute(
            f"SELECT count(*) FROM {_q(t)} x JOIN matches m ON m.id = x.match_id JOIN groups g ON g.id = m.group_id "
            "JOIN seasons s ON s.id = g.season_id WHERE s.name = ?", (temporada,)).fetchone()[0] for t in PESADAS)
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------- órdenes

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="La base en piezas: montar, partir, verificar y comparar.")
    ordenes = parser.add_subparsers(dest="orden", required=True)
    for nombre, ayuda in (("montar", "monta la base a partir de las piezas"),
                          ("partir", "parte la base en sus piezas"),
                          ("verificar", "comprueba que las piezas vueltas a montar son la base"),
                          ("comparar", "monta las piezas en un temporal y las compara con la base")):
        p = ordenes.add_parser(nombre, help=ayuda)
        p.add_argument("--db", default=str(DB_PATH), help="la base (por defecto, futbolbase.db del repositorio)")
        p.add_argument("--piezas", default=str(DIR_PIEZAS), help="la carpeta de las piezas (por defecto, base/)")
        if nombre == "montar":
            p.add_argument("--solo-comun", action="store_true", help="solo comun.db: las tablas pesadas, vacías")
            p.add_argument("--contra", help="no la pone en su sitio si no es igual a este fichero")
    args = parser.parse_args(argv)
    db, carpeta = Path(args.db), Path(args.piezas)
    try:
        if args.orden == "montar":
            filas = montar(carpeta, db, solo_comun=args.solo_comun, contra=args.contra)
            n = 1 if args.solo_comun else len(_leer_manifiesto(carpeta)[0]["piezas"])
            print(f"montada {db}: {n} piezas, {filas.get('appearances', 0)} apariciones")
        elif args.orden == "partir":
            r = partir(db, carpeta)
            print(f"partida {db}: {len(r['creadas'])} creadas, {len(r['cambiadas'])} cambiadas, "
                  f"{len(r['borradas'])} borradas, {len(r['intactas'])} sin cambios")
            for fichero, (ins, bor) in sorted(r["cambiadas"].items()):
                print(f"  {fichero}: +{ins} -{bor}")
        elif args.orden == "verificar":
            r = verificar(db, carpeta)
            for motivo in r["motivos"]:
                print(motivo)
            if not r["ok"]:
                return 1
            conn = _abrir(db)
            try:
                t = len(_tablas(conn))
            finally:
                conn.close()
            print(f"piezas iguales a la base: {t} tablas; la mayor, {r['mayor'][0]} ({_mb(r['mayor'][1])} MB); "
                  f"en total {_mb(r['total'])} MB")
        else:
            with tempfile.TemporaryDirectory(prefix="piezas-") as tmp:
                montada = Path(tmp) / "montada.db"
                montar(carpeta, montada)
                dif = comparar(db, montada)
            for linea in dif:
                print(linea)
            if dif:
                return 1
            print("iguales")
    except (PiezasError, sqlite3.Error) as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
