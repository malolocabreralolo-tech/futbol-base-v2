#!/usr/bin/env python3
"""migrate_identidad.py — La fase 2C en la base: identidades de acta y fichas (docs/identidad.md).

Tres fases, cada una en su transacción y todas idempotentes (la segunda vez no cambia nada):

1. `asegurar_esquema`: players.ficha_id y players.union_por (la ficha), y team_id, season_id y ordinal
   (la identidad sin id de la federación: nombre, equipo y temporada) con su clave pública, guardada una
   vez (players.clave). Lo llama también el bot al arrancar.
2. `separar`: cada aparición (con sus sucesos de ese partido y equipo) pasa a la identidad de acta que le
   toca según el original del acta: sin id, a la de (nombre, equipo, temporada), creándola si falta; con
   id, a la fila de ese id. No se borra nada: una fila que se queda sin apariciones se conserva.
3. `resolver_fichas`: `realinear` (cada identidad sin id con el equipo y la temporada de sus apariciones)
   e identidad.resolver sobre todas las identidades con aparición o suceso, y escribe ficha_id (NULL en la
   principal) y union_por. Lo llama también el bot en cada pasada.

De dónde sale si una aparición llegó con id, por este orden: el original del bot
(`actas_bot_<temporada>_<categoria>.jsonl`), los raws (`fiflp_actas_<temporada>*_raw.json`) y, sin
original, la regla de la liga prebenjamín de Gran Canaria desde 2024-25 (la federación no publica ids ahí:
sin id) o, en otro caso, lo que diga la fila (con fiflp_id, con id; sin él, sin id).

Se ensaya sobre una copia, nunca sobre la base del repositorio:

    python3 scripts/migrate_identidad.py --db <copia> [--raws scripts] [--informe docs/identidad-migracion.md]
                                         [--muestras <fichero no versionado>]
"""
import argparse
import glob
import json
import os
import random
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fiflp_acta import clean_scorer  # noqa: E402  (la limpieza del goleador que hace el importador)
from identidad import (NIVEL, UNIR_CORTOS_EN_CLUB, Identidad, clave_publica, club, compatibles, intervalo,  # noqa: E402
                       normalizar, resolver)

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ANON_NORM = "#SIN NOMBRE PUBLICADO"     # la fila del gol sin nombre publicado (import_fiflp_actas): no se toca
TABLAS = ("appearances", "match_events", "matches", "goals", "scorers", "match_staff_all", "players")
# 'NOMBRE#id', 'NOMBRE@equipo.temporada' y 'NOMBRE@equipo.temporada#2': el nombre es lo de delante.
_SUFIJOS = re.compile(r"(@\d+\.\d+)?(#\d+)?$")
_RAW = re.compile(r"^fiflp_actas_\d{4}-\d{4}(?:_\w+)?_raw\.json$")
_BOT = re.compile(r"^actas_bot_\d{4}-\d{4}_\w+\.jsonl$")
SEMILLA = 20261114


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

# clave: la clave pública de la identidad sin id, calculada una vez al crearla (poner_claves): si se
# calculara al publicar con el nombre del equipo, renombrar el equipo rompería sus enlaces.
COLUMNAS = (("ficha_id", "INTEGER"), ("union_por", "TEXT"), ("team_id", "INTEGER"), ("season_id", "INTEGER"),
            ("ordinal", "INTEGER"), ("clave", "TEXT"))
INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_players_fiflp ON players(fiflp_id)",
    # La identidad sin id se busca por equipo, temporada y nombre (el importador, tarea 4).
    "CREATE INDEX IF NOT EXISTS idx_players_sin_id ON players(team_id, season_id, norm_name) "
    "WHERE team_id IS NOT NULL",
    # prune_players no debe borrar una fila a la que apunta otra.
    "CREATE INDEX IF NOT EXISTS idx_players_ficha ON players(ficha_id) WHERE ficha_id IS NOT NULL",
    # Dos identidades nunca comparten clave (identidad_separadas.json y la web las buscan por ella).
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_players_clave ON players(clave) WHERE clave IS NOT NULL",
)


def asegurar_esquema(conn) -> bool:
    """Las columnas e índices de la fase 2C, si faltan, y la clave de las identidades sin id que aún no la
    tienen. Devuelve si añadió alguna columna. Hace commit."""
    if conn.in_transaction:
        conn.commit()
    tiene = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    nuevas = [(c, t) for c, t in COLUMNAS if c not in tiene]
    for col, tipo in nuevas:
        conn.execute(f"ALTER TABLE players ADD COLUMN {col} {tipo}")
    for sql in INDICES:
        conn.execute(sql)
    poner_claves(conn)
    conn.commit()
    return bool(nuevas)


def equipo_de_sus_apariciones(conn, pids) -> dict:
    """{player_id: (nombre del equipo, año de inicio)} del equipo y la temporada en los que más aparece cada
    fila (a igualdad, el de teams.id menor y la temporada más antigua): para la que apunta a un equipo o a
    una temporada que ya no existen."""
    pids = sorted(set(pids))
    out = {}
    for k in range(0, len(pids), 500):
        trozo_ = pids[k:k + 500]
        filas = conn.execute(
            f"""SELECT a.player_id, t.id, t.name, s.start_year, count(*) FROM appearances a
                  JOIN teams t ON t.id = a.team_id JOIN matches m ON m.id = a.match_id
                  JOIN groups g ON g.id = m.group_id JOIN seasons s ON s.id = g.season_id
                 WHERE a.player_id IN ({",".join("?" * len(trozo_))})
                 GROUP BY a.player_id, t.id, s.start_year""", trozo_).fetchall()
        for pid, tid, nombre, anio, n in sorted(filas, key=lambda r: (r[0], -r[4], r[1], r[3])):
            out.setdefault(pid, (nombre, anio))
    return out


def poner_claves(conn, pids=None) -> int:
    """Guarda la clave pública (identidad.clave_publica) de las identidades sin id que no la tienen (todas,
    o las de `pids`), con el nombre del equipo y el año de inicio de ahora; si el equipo o la temporada ya
    no existen, los de sus apariciones. Si otra fila ya tiene esa clave (un equipo que se llama hoy como se
    llamaba otro), la del nombre con '|<id>'. No hace commit. Devuelve cuántas puso."""
    falta = "p.clave IS NULL AND p.fiflp_id IS NULL AND p.team_id IS NOT NULL"
    if pids is not None:
        pids = list(pids)
        if not pids:
            return 0
        falta += f" AND p.id IN ({','.join('?' * len(pids))})"
    # Primero sin tocar teams ni seasons: casi siempre no falta ninguna (y así vale sin esas tablas).
    if not conn.execute(f"SELECT 1 FROM players p WHERE {falta} LIMIT 1", pids or ()).fetchone():
        return 0
    filas = conn.execute(
        "SELECT p.id, p.norm_name, p.ordinal, t.name, s.start_year FROM players p "
        "LEFT JOIN teams t ON t.id = p.team_id LEFT JOIN seasons s ON s.id = p.season_id "
        f"WHERE {falta}", pids or ()).fetchall()
    sin_equipo = equipo_de_sus_apariciones(conn, [r[0] for r in filas if r[3] is None or r[4] is None])
    puestas = 0
    for pid, norm_name, ordinal, equipo, anio in filas:
        base = nombre_base(norm_name)
        if not base or base.startswith("#"):
            continue
        if equipo is None or anio is None:
            equipo, anio = sin_equipo.get(pid, (None, None))
            if equipo is None:
                continue        # sin apariciones tampoco: generate_js._fichas le busca otra clave
        norm = base + (f"#{ordinal}" if ordinal and ordinal > 1 else "")
        clave = clave_publica(None, norm, equipo, anio)
        if conn.execute("SELECT 1 FROM players WHERE clave=? AND id<>?", (clave, pid)).fetchone():
            clave = clave_publica(None, f"{norm}|{pid}", equipo, anio)
        conn.execute("UPDATE players SET clave=? WHERE id=?", (clave, pid))
        puestas += 1
    return puestas


def nombre_base(norm_name: str) -> str:
    """El nombre normalizado de una fila, sin '#id', '@equipo.temporada' ni el ordinal."""
    return _SUFIJOS.sub("", norm_name or "") if not (norm_name or "").startswith("#") else norm_name


def norm_sin_id(nombre: str, team_id: int, season_id: int, ordinal: int | None = None) -> str:
    """El norm_name (UNIQUE) de la identidad sin id: 'NOMBRE@<equipo>.<temporada>', con '#<ordinal>' si es
    el segundo o siguiente del mismo nombre en una alineación."""
    return f"{nombre}@{team_id}.{season_id}" + (f"#{ordinal}" if ordinal and ordinal > 1 else "")


def recuentos(conn) -> dict:
    out = {}
    for t in TABLAS:
        try:
            out[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = None
    return out


# ---------------------------------------------------------------------------
# Los originales
# ---------------------------------------------------------------------------

def _lo_que_hace_falta(acta: dict) -> dict:
    """De un acta, solo las alineaciones y los sucesos (los raws de siete temporadas no caben enteros)."""
    return {"lineups": acta.get("lineups") or {}, "events": acta.get("events") or []}


def leer_originales(raws_dir: str) -> tuple[dict, Counter]:
    """{cod_acta: acta} de los originales del bot y de los raws (mandan los del bot; de un acta leída
    varias veces, la última) y lo que se leyó."""
    cuenta = Counter()
    actas = {}
    for path in sorted(glob.glob(os.path.join(raws_dir, "fiflp_actas_*_raw.json"))):
        if not _RAW.match(os.path.basename(path)):
            continue
        with open(path, encoding="utf-8") as f:
            datos = json.load(f)
        for cod, acta in datos.items():
            cuenta["actas de los raws"] += 1
            if int(cod) in actas:
                cuenta["actas repetidas en los raws"] += 1
            actas[int(cod)] = _lo_que_hace_falta(acta)
    del_bot = {}
    for path in sorted(glob.glob(os.path.join(raws_dir, "actas_bot_*.jsonl"))):
        if not _BOT.match(os.path.basename(path)):
            continue
        with open(path, encoding="utf-8") as f:
            for linea in f:
                if not linea.strip():
                    continue
                try:
                    obj = json.loads(linea)
                    cod, acta, leida = (int(obj["cod_acta"]), _lo_que_hace_falta(obj["acta"]),
                                        str(obj.get("leida") or ""))
                except (ValueError, KeyError, TypeError):
                    cuenta["líneas rotas en los originales del bot"] += 1
                    continue
                cuenta["lecturas de los originales del bot"] += 1
                # Una relectura manda sobre la anterior (a igual hora, la que va después en el fichero).
                if cod not in del_bot or leida >= del_bot[cod][0]:
                    del_bot[cod] = (leida, acta)
    for cod, (_, acta) in del_bot.items():
        if cod in actas:
            cuenta["actas de los raws sustituidas por el original del bot"] += 1
        actas[cod] = acta
    cuenta["actas del bot"] = len(del_bot)
    cuenta["actas"] = len(actas)
    return actas, cuenta


def liga_prebenjamin_gc(categoria, isla, codigo, anio) -> bool:
    """La liga prebenjamín de Gran Canaria desde 2024-25 (PGC* en 2024-25, PG* después): la federación no
    publica ahí el id de los jugadores. La copa (PCC*) no entra."""
    return (categoria == "PREBENJAMIN" and isla == "grancanaria" and (codigo or "").startswith("PG")
            and anio is not None and anio >= 2024)


# ---------------------------------------------------------------------------
# Separar
# ---------------------------------------------------------------------------

def _entradas(acta: dict, lado: str):
    """Las entradas del original de un lado: [(nombre, norm, fiflp_id, dorsal, 'alineación'|'suceso')]. Los
    del suceso son los que no están en la alineación (por el nombre, como el importador), una por nombre
    normalizado; sin nombre (el gol sin nombre publicado), fuera."""
    alineacion = (acta.get("lineups") or {}).get(lado) or []
    out, nombres = [], set()
    for p in alineacion:
        nombre = p.get("name") or ""
        fid = p.get("fiflp_id")
        out.append((nombre, normalizar(nombre), int(fid) if fid not in (None, "", 0) else None, p.get("dorsal"),
                    "alineación"))
        nombres.add(nombre)
    vistos = set()
    for ev in acta.get("events") or []:
        if ev.get("side") != lado:
            continue
        nombre = clean_scorer(ev.get("player_name")) or None
        if not nombre or nombre in nombres:
            continue
        norm = normalizar(nombre)
        if norm not in vistos:
            vistos.add(norm)
            out.append((nombre, norm, None, None, "suceso"))
    return out


def _clave_dorsal(dorsal, orden):
    return (dorsal is None, dorsal if dorsal is not None else 0, orden)


def _destinos_con_original(entradas, apps, filas, cuenta):
    """Casa las entradas del original de un lado con las apariciones de ese equipo en el partido.

    apps: [(pid, dorsal, ord)]. Devuelve {pid actual: destino} con destino ('id', fid, nombre) o
    ('sin', norm, ordinal, nombre), y la lista de las apariciones que no casaron."""
    libres = {pid: (dorsal, orden) for pid, dorsal, orden in apps}
    destino = {}
    alineacion = [e for e in entradas if e[4] == "alineación"]
    por_norm_alineacion = Counter(e[1] for e in alineacion)

    # El ordinal de las sin id del mismo nombre en la alineación: por dorsal (el más bajo, sin ordinal).
    ordinal = {}
    sin_id = defaultdict(list)
    for i, e in enumerate(alineacion):
        if e[2] is None:
            sin_id[e[1]].append((_clave_dorsal(e[3], i), i))
    for norm, lista in sin_id.items():
        for rango, (_, i) in enumerate(sorted(lista), start=1):
            ordinal[i] = rango if len(lista) > 1 and rango > 1 else None

    def meta(i, e):
        return ("id", e[2], e[0]) if e[2] is not None else ("sin", e[1], ordinal.get(i), e[0])

    pendientes = list(enumerate(alineacion))
    # 1) Por el id de la federación de la fila.
    resto = []
    for i, e in pendientes:
        cands = [pid for pid in libres if e[2] is not None and filas[pid][2] == e[2]]
        if len(cands) == 1:
            destino[cands[0]] = meta(i, e)
            del libres[cands[0]]
        else:
            resto.append((i, e))
    # 2) Por el nombre y, entre homónimos, por el dorsal; si queda uno de cada lado, son el mismo.
    grupos = defaultdict(list)
    for i, e in resto:
        grupos[e[1]].append((i, e))
    for norm, lista in grupos.items():
        cands = [pid for pid in libres if nombre_base(filas[pid][0]) == norm]
        sueltas = []
        for i, e in lista:
            mismos = [pid for pid in cands if pid in libres and e[3] is not None and libres[pid][0] == e[3]]
            dorsal_unico = sum(1 for _, o in lista if o[3] == e[3]) == 1
            if len(mismos) == 1 and dorsal_unico:
                destino[mismos[0]] = meta(i, e)
                del libres[mismos[0]]
            else:
                sueltas.append((i, e))
        cands = [pid for pid in cands if pid in libres]
        if len(sueltas) == 1 and len(cands) == 1:
            destino[cands[0]] = meta(*sueltas[0])
            del libres[cands[0]]
        elif sueltas:
            cuenta["entradas de la alineación sin aparición en la base"] += len(sueltas)
    # 3) Los que solo salen en los sucesos.
    for nombre, norm, _, _, _ in (e for e in entradas if e[4] == "suceso"):
        if por_norm_alineacion[norm] == 1:
            continue            # el mismo nombre que uno solo de la alineación: es él
        if por_norm_alineacion[norm] >= 2:
            cuenta["sucesos de un nombre con homónimos en la alineación (sin tocar)"] += 1
            continue
        cands = sorted((pid for pid in libres if nombre_base(filas[pid][0]) == norm),
                       key=lambda pid: _clave_dorsal(*libres[pid]))
        if len(cands) == 1:
            destino[cands[0]] = ("sin", norm, None, nombre)
            del libres[cands[0]]
        else:
            cuenta["entradas de los sucesos sin aparición en la base"] += 1
    return destino, [(pid, *libres[pid]) for pid in libres]


def _destino_sin_original(pid, fila, team_id, season_id, liga_sin_ids):
    """La regla sin original: la liga prebenjamín de GC, sin id; en otro caso, lo que diga la fila."""
    norm_name, full_name, fid, f_team, f_season, f_ordinal = fila
    if norm_name == ANON_NORM:
        return None
    if fid is not None and not liga_sin_ids:
        return None
    pista = f_ordinal if (f_team, f_season) == (team_id, season_id) else None
    return ("sin", nombre_base(norm_name), pista, full_name)


def separar(conn, originales: dict, log=print) -> dict:
    """La fase 2: cada aparición a su identidad de acta. Una transacción. Devuelve los recuentos y la lista
    de lo que se movió [(match_id, team_id, de, a, 'separada'|'corregida')]."""
    cuenta = Counter()
    filas = {pid: list(r) for pid, *r in conn.execute(
        "SELECT id, norm_name, full_name, fiflp_id, team_id, season_id, ordinal FROM players")}
    por_fid = {}
    for pid, f in sorted(filas.items()):
        if f[2] is not None:
            por_fid.setdefault(f[2], pid)
    por_norm = {f[0]: pid for pid, f in filas.items()}
    partidos = {mid: r for mid, *r in conn.execute(
        """SELECT m.id, m.cod_acta, m.home_team_id, m.away_team_id, g.season_id, c.name, g.island, g.code,
                  s.start_year
             FROM matches m JOIN groups g ON g.id = m.group_id JOIN categories c ON c.id = g.category_id
             JOIN seasons s ON s.id = g.season_id
            WHERE EXISTS (SELECT 1 FROM appearances a WHERE a.match_id = m.id)""")}
    apps = defaultdict(list)
    for mid, tid, pid, dorsal, orden in conn.execute(
            "SELECT match_id, team_id, player_id, dorsal, ord FROM appearances"):
        apps[(mid, tid)].append((pid, dorsal, orden))
    con_partido = {cod for (cod,) in conn.execute("SELECT cod_acta FROM matches WHERE cod_acta IS NOT NULL")}
    cuenta["actas del original sin partido en la base"] = sum(1 for cod in originales if cod not in con_partido)

    destinos = {}           # (mid, tid) -> {pid actual: destino}
    for (mid, tid), lista in apps.items():
        cod, local, visitante, season_id, categoria, isla, codigo, anio = partidos[mid]
        liga = liga_prebenjamin_gc(categoria, isla, codigo, anio)
        acta = originales.get(cod) if cod is not None else None
        lado = "home" if tid == local else "away" if tid == visitante else None
        if acta is not None and lado is not None and local != visitante:
            d, sueltas = _destinos_con_original(_entradas(acta, lado), lista, filas, cuenta)
            for pid, dorsal, _ in sueltas:
                if filas[pid][0] == ANON_NORM:
                    d[pid] = None
                elif dorsal is None:
                    # Sin dorsal solo la crea el importador para quien sale en los sucesos y no en la
                    # alineación (ninguna entrada de alineación de los raws va sin dorsal): es un goleador
                    # de otra lectura del acta, y esos van siempre sin id.
                    cuenta["apariciones sin dorsal que el original no trae (goleador: sin id)"] += 1
                    d[pid] = _destino_sin_original(pid, filas[pid], tid, season_id, True)
                else:
                    cuenta["apariciones con dorsal que el original no trae (regla sin original)"] += 1
                    d[pid] = _destino_sin_original(pid, filas[pid], tid, season_id, liga)
        else:
            cuenta["apariciones sin original"] += len(lista)
            d = {pid: _destino_sin_original(pid, filas[pid], tid, season_id, liga) for pid, *_ in lista}
        # Dos sin id del mismo nombre en un equipo y partido con el mismo ordinal: por dorsal.
        info = {pid: (dorsal, orden) for pid, dorsal, orden in lista}
        por_nombre = defaultdict(list)
        for pid, dest in d.items():
            if dest and dest[0] == "sin":
                por_nombre[dest[1]].append(pid)
        for norm, pids in por_nombre.items():
            ordinales = [d[p][2] or 1 for p in pids]
            if len(set(ordinales)) < len(pids):
                cuenta["ordinales puestos por dorsal"] += len(pids)
                for rango, p in enumerate(sorted(pids, key=lambda p: _clave_dorsal(*info[p])), start=1):
                    d[p] = ("sin", norm, rango if rango > 1 else None, d[p][3])
        destinos[(mid, tid)] = d

    conn.execute("BEGIN")
    try:
        # Las claves ajenas se miran al final: los cambios de fila pasan por un id negativo (dos
        # apariciones de un partido pueden cambiarse la fila la una a la otra).
        conn.execute("PRAGMA defer_foreign_keys=ON")
        movidas = []

        def fila_sin_id(norm, tid, season_id, ordinal, nombre):
            clave = norm_sin_id(norm, tid, season_id, ordinal)
            pid = por_norm.get(clave)
            if pid is None:
                pid = conn.execute(
                    "INSERT INTO players(full_name, norm_name, team_id, season_id, ordinal) VALUES (?,?,?,?,?)",
                    (nombre, clave, tid, season_id, ordinal)).lastrowid
                poner_claves(conn, [pid])
                filas[pid] = [clave, nombre, None, tid, season_id, ordinal]
                por_norm[clave] = pid
                cuenta["identidades sin id creadas"] += 1
            return pid

        def fila_con_id(fid, nombre):
            pid = por_fid.get(fid)
            if pid is None:
                norm = normalizar(nombre)
                clave, n = norm, 1
                while clave in por_norm:
                    clave = f"{norm}#{fid}" if n == 1 else f"{norm}#{fid}.{n}"
                    n += 1
                pid = conn.execute("INSERT INTO players(full_name, norm_name, fiflp_id) VALUES (?,?,?)",
                                   (nombre, clave, fid)).lastrowid
                filas[pid] = [clave, nombre, fid, None, None, None]
                por_norm[clave], por_fid[fid] = pid, pid
                cuenta["filas con id creadas"] += 1
            return pid

        cambios = []
        for (mid, tid), d in sorted(destinos.items()):
            season_id = partidos[mid][3]
            nuevo = {}
            for pid, dest in d.items():
                if dest is None:
                    nuevo[pid] = pid
                elif dest[0] == "id":
                    nuevo[pid] = fila_con_id(dest[1], dest[2])
                else:
                    nuevo[pid] = fila_sin_id(dest[1], tid, season_id, dest[2], dest[3])
            # Dos apariciones a la misma fila: la que cambiaría se queda donde está (no se pierde ninguna).
            while True:
                usados = Counter(nuevo.values())
                choque = [p for p, q in nuevo.items() if usados[q] > 1 and q != p]
                if not choque:
                    break
                for p in choque:
                    nuevo[p] = p
                    cuenta["apariciones que no se movieron por un choque"] += 1
            for pid, dest in sorted(nuevo.items()):
                if dest == pid:
                    continue
                tipo = "corregida" if filas[dest][2] is not None else "separada"
                cambios.append((mid, tid, pid, dest))
                movidas.append((mid, tid, pid, dest, tipo))
        for mid, tid, de, _ in cambios:
            conn.execute("UPDATE appearances SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                         (-de, mid, tid, de))
            conn.execute("UPDATE match_events SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                         (-de, mid, tid, de))
        for mid, tid, de, a in cambios:
            conn.execute("UPDATE appearances SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                         (a, mid, tid, -de))
            cuenta["sucesos movidos"] += conn.execute(
                "UPDATE match_events SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                (a, mid, tid, -de)).rowcount
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    for _, _, de, a, tipo in movidas:
        if tipo == "separada":
            cuenta["apariciones separadas"] += 1
            cuenta["apariciones separadas de filas con id" if filas[de][2] is not None
                   else "apariciones separadas de filas sin id"] += 1
        else:
            cuenta["corregidas por identificador"] += 1
            cuenta["corregidas desde una fila con otro id" if filas[de][2] is not None
                   else "corregidas desde una fila sin id"] += 1
    cuenta["filas de las que se separaron apariciones"] = len({de for _, _, de, _, t in movidas if t == "separada"})
    cuenta["filas de las que se corrigieron apariciones"] = len({de for _, _, de, _, t in movidas if t == "corregida"})
    log(f"  separar: {cuenta['apariciones separadas']} separadas, {cuenta['corregidas por identificador']} "
        f"corregidas por identificador, {cuenta['identidades sin id creadas']} identidades sin id nuevas")
    return {"cuenta": dict(cuenta), "movidas": movidas}


# ---------------------------------------------------------------------------
# Realinear
# ---------------------------------------------------------------------------

# Lo de una identidad sin id (x: una aparición o un suceso) que no está en su equipo o su temporada.
_FUERA = ("p.fiflp_id IS NULL AND p.team_id IS NOT NULL AND x.team_id IS NOT NULL "
          "AND (x.team_id IS NOT p.team_id OR g.season_id IS NOT p.season_id)")


def realinear(conn, log=print) -> dict:
    """La identidad sin id sigue a sus apariciones: la verdad es appearances. merge_twin_teams,
    import_fiflp_grupos (_move_teams, fix_positions) y migrate_team_names cambian appearances.team_id y
    match_events.team_id, y pueden borrar la fila vieja de teams, sin mirar players.

    Cada aparición (con los sucesos de ese jugador en ese partido y equipo) y cada suceso sin aparición
    cuyo equipo o temporada no son los de su identidad sin id pasan a la identidad sin id de (nombre, ese
    equipo, esa temporada, mismo ordinal), creándola si falta. Si todo lo de la identidad está en un único
    (equipo, temporada) que no es el suyo y esa identidad no existe, se cambia la misma fila: conserva su
    id y su clave. La aparición que chocaría con otra de la identidad destino en el mismo partido y equipo
    se queda donde está y se cuenta (como en separar). Idempotente; sin nada que mover no escribe nada.
    Devuelve {"movidas", "sucesos", "reubicadas", "creadas", "choques"}."""
    cuenta = {"movidas": 0, "sucesos": 0, "reubicadas": 0, "creadas": 0, "choques": 0}
    if conn.in_transaction:
        conn.commit()
    desde = "JOIN players p ON p.id = x.player_id JOIN matches m ON m.id = x.match_id JOIN groups g ON g.id = m.group_id"
    apps = conn.execute(f"SELECT x.player_id, x.match_id, x.team_id, g.season_id FROM appearances x {desde} "
                        f"WHERE {_FUERA}").fetchall()
    sucesos = conn.execute(f"SELECT x.id, x.player_id, x.match_id, x.team_id, g.season_id FROM match_events x "
                           f"{desde} WHERE {_FUERA}").fetchall()
    if not apps and not sucesos:
        return cuenta
    # Los sucesos de una aparición que se mueve van con ella; los demás (sin aparición), por su equipo.
    con_aparicion = {(pid, mid, tid) for pid, mid, tid, _ in apps}
    por_pid = defaultdict(lambda: defaultdict(lambda: ([], [])))   # pid -> (equipo, temporada) -> (partidos, sucesos)
    for pid, mid, tid, sid in apps:
        por_pid[pid][(tid, sid)][0].append(mid)
    for eid, pid, mid, tid, sid in sucesos:
        if (pid, mid, tid) not in con_aparicion:
            por_pid[pid][(tid, sid)][1].append(eid)
    conn.execute("BEGIN")
    try:
        for pid in sorted(por_pid):
            norm_name, nombre, ordinal, tid0, sid0 = conn.execute(
                "SELECT norm_name, full_name, ordinal, team_id, season_id FROM players WHERE id=?", (pid,)).fetchone()
            base = nombre_base(norm_name)
            destinos = por_pid[pid]
            if len(destinos) == 1:
                (tid, sid), = destinos
                norm = norm_sin_id(base, tid, sid, ordinal)
                queda = any(conn.execute(
                    f"SELECT 1 FROM {t} x JOIN matches m ON m.id = x.match_id JOIN groups g ON g.id = m.group_id "
                    "WHERE x.player_id=? AND (x.team_id IS NOT ? OR g.season_id IS NOT ?) LIMIT 1",
                    (pid, tid, sid)).fetchone() for t in ("appearances", "match_events"))
                if not queda and not conn.execute("SELECT 1 FROM players WHERE norm_name=?", (norm,)).fetchone():
                    conn.execute("UPDATE players SET team_id=?, season_id=?, norm_name=? WHERE id=?",
                                 (tid, sid, norm, pid))
                    cuenta["reubicadas"] += 1
                    continue
            for (tid, sid), (partidos, sueltos) in sorted(destinos.items()):
                norm = norm_sin_id(base, tid, sid, ordinal)
                r = conn.execute("SELECT id FROM players WHERE norm_name=?", (norm,)).fetchone()
                if r:
                    destino = r[0]
                else:
                    destino = conn.execute(
                        "INSERT INTO players(full_name, norm_name, team_id, season_id, ordinal) VALUES (?,?,?,?,?)",
                        (nombre, norm, tid, sid, ordinal)).lastrowid
                    poner_claves(conn, [destino])
                    cuenta["creadas"] += 1
                for mid in sorted(partidos):
                    if conn.execute("SELECT 1 FROM appearances WHERE match_id=? AND team_id=? AND player_id=?",
                                    (mid, tid, destino)).fetchone():
                        cuenta["choques"] += 1
                        continue
                    conn.execute("UPDATE appearances SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                                 (destino, mid, tid, pid))
                    cuenta["sucesos"] += conn.execute(
                        "UPDATE match_events SET player_id=? WHERE match_id=? AND team_id=? AND player_id=?",
                        (destino, mid, tid, pid)).rowcount
                    cuenta["movidas"] += 1
                for eid in sueltos:
                    cuenta["sucesos"] += conn.execute("UPDATE match_events SET player_id=? WHERE id=?",
                                                      (destino, eid)).rowcount
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    log(f"  realinear: {cuenta['movidas']} apariciones y {cuenta['sucesos']} sucesos a la identidad de su equipo y "
        f"temporada, {cuenta['reubicadas']} identidades reubicadas enteras, {cuenta['creadas']} nuevas, "
        f"{cuenta['choques']} apariciones que no se movieron por un choque")
    return cuenta


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def _iso(fecha, anio):
    """La fecha del partido en ISO. La base tiene 'AAAA-MM-DD', 'DD-MM-AAAA' y 'DD/MM' (sin año: de agosto
    en adelante, el año de inicio de la temporada); otra cosa, None (sin fecha no se descarta un cruce)."""
    f = (fecha or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", f)
    if m:
        return f
    m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", f)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", f)
    if m and anio is not None:
        mes = int(m.group(2))
        return f"{anio if mes >= 8 else anio + 1}-{mes:02d}-{int(m.group(1)):02d}"
    return None


def _vistas(conn) -> dict:
    """{player_id: [vista]} con vista = (anio, nivel, equipo, primera, última, apariciones), una por
    temporada, categoría y equipo; de las apariciones y, para quien solo sale en los sucesos, de ellos."""
    fechas = defaultdict(list)
    for pid, anio, cat, equipo, fecha in conn.execute(
            """SELECT a.player_id, s.start_year, c.name, t.name, m.date FROM appearances a
                 JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
                 JOIN seasons s ON s.id = g.season_id JOIN categories c ON c.id = g.category_id
                 JOIN teams t ON t.id = a.team_id"""):
        fechas[(pid, anio, NIVEL.get(cat), equipo)].append(_iso(fecha, anio))
    con_apariciones = {k[0] for k in fechas}
    solo_sucesos = defaultdict(set)
    for pid, mid, anio, cat, equipo, fecha in conn.execute(
            """SELECT e.player_id, e.match_id, s.start_year, c.name, t.name, m.date FROM match_events e
                 JOIN matches m ON m.id = e.match_id JOIN groups g ON g.id = m.group_id
                 JOIN seasons s ON s.id = g.season_id JOIN categories c ON c.id = g.category_id
                 JOIN teams t ON t.id = e.team_id"""):
        if pid not in con_apariciones:
            solo_sucesos[(pid, anio, NIVEL.get(cat), equipo)].add((mid, _iso(fecha, anio)))
    vistas = defaultdict(list)
    for (pid, anio, nivel, equipo), fs in fechas.items():
        conocidas = sorted(f for f in fs if f)
        vistas[pid].append((anio, nivel, equipo, conocidas[0] if conocidas else None,
                            conocidas[-1] if conocidas else None, len(fs)))
    for (pid, anio, nivel, equipo), partidos in solo_sucesos.items():
        conocidas = sorted(f for _, f in partidos if f)
        vistas[pid].append((anio, nivel, equipo, conocidas[0] if conocidas else None,
                            conocidas[-1] if conocidas else None, 0))
    return {pid: sorted(v, key=lambda x: (x[0], x[1] or 0, x[2] or "", x[3] or "", x[4] or "", x[5]))
            for pid, v in vistas.items()}


def identidades(conn) -> list[Identidad]:
    """Las identidades con alguna aparición o suceso, como las quiere identidad.resolver: norm con '#id' en
    las que tienen id (el norm_name), y el nombre con su ordinal ('X#2') en las sin id."""
    vistas = _vistas(conn)
    out = []
    for pid, norm_name, fid, team_id, ordinal in conn.execute(
            "SELECT id, norm_name, fiflp_id, team_id, ordinal FROM players"):
        if pid not in vistas:
            continue
        if fid is None and team_id is not None:
            norm = nombre_base(norm_name) + (f"#{ordinal}" if ordinal and ordinal > 1 else "")
        else:
            norm = norm_name
        out.append(Identidad(id=pid, norm=norm, fiflp_id=fid, vistas=tuple(vistas[pid])))
    return out


def pares_juntas(conn) -> list[tuple[int, int]]:
    """[(id, id)] de las identidades del mismo nombre (nombre_base) que salen en un mismo partido con el
    mismo equipo: dos niños (identidad.resolver no las une). Solo las del mismo nombre: las demás no las
    une ninguna regla. Una pasada por appearances en el orden de su clave primaria."""
    base = {pid: nombre_base(n) for pid, n in conn.execute("SELECT id, norm_name FROM players")}
    pares, grupo, vistos = set(), None, {}
    for mid, tid, pid in conn.execute("SELECT match_id, team_id, player_id FROM appearances ORDER BY match_id, team_id"):
        if (mid, tid) != grupo:
            grupo, vistos = (mid, tid), {}
        b = base.get(pid)
        for otro in vistos.get(b, ()):
            pares.add((min(otro, pid), max(otro, pid)))
        vistos.setdefault(b, []).append(pid)
    return sorted(pares)


# Las claves públicas de las identidades apartadas a mano de su ficha (docs/identidad.md, «Deshacer una
# unión»): versionado, lo lee resolver_fichas en cada pasada.
SEPARADAS = os.path.join(SCRIPTS, "identidad_separadas.json")


def leer_separadas(conn, ruta=SEPARADAS, log=print) -> set[int]:
    """Los ids de las filas de las claves de `ruta` (un id de la federación: todas las filas de ese id; 'n…':
    la de esa clave guardada). Sin fichero o vacío, ninguna; una clave que no es de nadie se ignora con un
    aviso. Un fichero que no es una lista de textos es un error (la pasada se para: nada a medias)."""
    if not os.path.exists(ruta):
        return set()
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    claves = json.loads(texto) if texto.strip() else []
    if not isinstance(claves, list) or not all(isinstance(c, str) for c in claves):
        raise ValueError(f"{ruta}: tiene que ser una lista de claves públicas (textos)")
    tiene_clave = any(r[1] == "clave" for r in conn.execute("PRAGMA table_info(players)"))
    ids = set()
    for c in claves:
        if c.isdigit():
            filas = conn.execute("SELECT id FROM players WHERE fiflp_id=?", (int(c),)).fetchall()
        else:
            filas = conn.execute("SELECT id FROM players WHERE clave=?", (c,)).fetchall() if tiene_clave else []
        if not filas:
            log(f"  ! {os.path.basename(ruta)}: la clave {c} no es de ninguna identidad (se ignora)")
        ids.update(pid for (pid,) in filas)
    return ids


def resolver_fichas(conn, log=print, separadas=SEPARADAS) -> dict:
    """Recalcula ficha_id y union_por de todas las filas (una transacción; solo escribe lo que cambia). Las
    filas sin aparición ni suceso quedan sueltas (ficha_id y union_por a NULL). Las identidades de las
    claves de `separadas` (scripts/identidad_separadas.json) no se unen a nadie."""
    t0 = time.monotonic()
    asegurar_esquema(conn)
    # Antes que nada, cada identidad sin id con sus apariciones: los movimientos de equipo de la pasada
    # (merge_twin_teams y compañía) no miran players.
    realineadas = realinear(conn, log=log)
    ids = identidades(conn)
    juntas = pares_juntas(conn)
    apartadas = leer_separadas(conn, separadas, log=log)
    t1 = time.monotonic()
    fichas = resolver(ids, UNIR_CORTOS_EN_CLUB, juntas=juntas, separadas=apartadas)
    t2 = time.monotonic()
    cambios = []
    for pid, ficha_id, union_por in conn.execute("SELECT id, ficha_id, union_por FROM players"):
        principal, por = fichas.get(pid, (pid, None))
        quiere = (None if principal == pid else principal, por)
        if (ficha_id, union_por) != quiere:
            cambios.append((quiere[0], quiere[1], pid))
    conn.execute("BEGIN")
    try:
        conn.executemany("UPDATE players SET ficha_id=?, union_por=? WHERE id=?", cambios)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    uniones = Counter(por for _, por in fichas.values() if por)
    out = {"identidades": len(ids), "fichas": sum(1 for k, (p, _) in fichas.items() if p == k),
           "uniones": dict(uniones), "cambiadas": len(cambios), "realinear": realineadas,
           "juntas": len(juntas), "separadas": len(apartadas),
           "segundos": round(time.monotonic() - t0, 2), "segundos_cargar": round(t1 - t0, 2),
           "segundos_resolver": round(t2 - t1, 2)}
    log(f"  resolver_fichas: {out['identidades']} identidades → {out['fichas']} fichas, uniones {out['uniones']}, "
        f"{out['cambiadas']} filas cambiadas, {out['segundos']} s")
    return out


# ---------------------------------------------------------------------------
# Medida (para el informe)
# ---------------------------------------------------------------------------

def _edad_imposible(vistas) -> bool:
    lo, hi = -10 ** 9, 10 ** 9
    for anio, nivel, *_ in vistas:
        if nivel in (1, 2, 3):
            a, b = intervalo(anio, nivel)
            lo, hi = max(lo, a), min(hi, b)
    return lo > hi


def medida_fichas(conn) -> dict:
    """Fichas (las que tienen alguna aparición), con y sin id, y las imposibles: por edad y por solape (dos
    clubes a la vez en la misma temporada y categoría). Sin ficha_id (antes de migrar), cada fila es una."""
    tiene = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    col = "ficha_id" if "ficha_id" in tiene else "NULL"
    vistas = _vistas(conn)
    con_apariciones = {pid for (pid,) in conn.execute("SELECT DISTINCT player_id FROM appearances")}
    grupos = defaultdict(list)
    fids = {}
    for pid, ficha_id, fid, norm_name in conn.execute(f"SELECT id, {col}, fiflp_id, norm_name FROM players"):
        grupos[ficha_id or pid].append(pid)
        fids[pid] = (fid, norm_name)
    out = Counter()
    imposibles = []
    for principal, miembros in sorted(grupos.items()):
        if not any(m in con_apariciones for m in miembros):
            continue
        out["fichas"] += 1
        con_id = any(fids[m][0] is not None for m in miembros)
        out["fichas con id" if con_id else "fichas sin ningún id"] += 1
        todas = [v for m in miembros for v in vistas.get(m, ())]
        edad = _edad_imposible(todas)
        if edad or not compatibles(todas):
            out["imposibles por edad" if edad else "imposibles por solape"] += 1
            imposibles.append((principal, "edad" if edad else "solape", miembros, todas, con_id))
    if "team_id" in tiene:
        out["identidades sin id en dos categorías"] = conn.execute(
            """SELECT count(*) FROM (SELECT a.player_id FROM appearances a JOIN players p ON p.id = a.player_id
                 JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
                WHERE p.team_id IS NOT NULL GROUP BY a.player_id HAVING count(DISTINCT g.category_id) > 1)""").fetchone()[0]
    out["filas sin aparición ni suceso"] = sum(1 for pid in fids if pid not in vistas)
    out["filas sin aparición"] = sum(1 for pid in fids if pid not in con_apariciones)
    return {"cuenta": dict(out), "imposibles": imposibles}


# ---------------------------------------------------------------------------
# La migración entera
# ---------------------------------------------------------------------------

def migrate(conn, raws_dir: str = SCRIPTS, log=print) -> dict:
    """Esquema, separar y resolver. Idempotente. Devuelve los recuentos de antes y de después y lo del
    informe."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    tiempos = {}
    antes = recuentos(conn)
    t = time.monotonic()
    originales, leidos = leer_originales(raws_dir)
    tiempos["leer originales"] = round(time.monotonic() - t, 2)
    t = time.monotonic()
    asegurar_esquema(conn)
    tiempos["esquema"] = round(time.monotonic() - t, 2)
    t = time.monotonic()
    # Una identidad sin id que ya existe y cuyo equipo cambió: que siga a sus apariciones con su fila (y su
    # clave) antes de que separar le busque otra.
    realinear(conn, log=log)
    sep = separar(conn, originales, log=log)
    tiempos["separar"] = round(time.monotonic() - t, 2)
    fichas = resolver_fichas(conn, log=log)
    tiempos["resolver_fichas"] = fichas["segundos"]
    despues = recuentos(conn)
    for t_ in TABLAS:
        if t_ != "players" and antes[t_] != despues[t_]:
            raise RuntimeError(f"la migración cambió el número de filas de {t_}: {antes[t_]} → {despues[t_]}")
    if despues["players"] < antes["players"]:
        raise RuntimeError("la migración borró filas de players")
    return {"antes": antes, "despues": despues, "originales": dict(leidos), "separar": sep["cuenta"],
            "movidas": sep["movidas"], "fichas": fichas, "tiempos": tiempos}


# ---------------------------------------------------------------------------
# El informe (solo cifras) y las muestras (con nombres; fichero no versionado)
# ---------------------------------------------------------------------------

EJEMPLOS_D12 = (4472, 1746, 19911, 22560, 4891)


def iniciales(nombre: str) -> str:
    """'APELLIDO1 APELLIDO2, NOMBRE' → 'N. A. A.' (el nombre delante): como cita el mapa a los niños (D12)."""
    apellidos, _, de_pila = (nombre or "").partition(",")
    return " ".join(f"{w[0]}." for w in (de_pila + " " + apellidos).split() if w[0].isalpha())


def perfil(conn, pid) -> list:
    """[(temporada, categoría, grupo, equipo, apariciones)] de una fila."""
    return conn.execute(
        """SELECT s.name, c.name, g.code, t.name, count(*) FROM appearances a
             JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
             JOIN seasons s ON s.id = g.season_id JOIN categories c ON c.id = g.category_id
             JOIN teams t ON t.id = a.team_id
            WHERE a.player_id = ? GROUP BY s.name, c.name, g.code, t.name ORDER BY s.name, c.name, g.code""",
        (pid,)).fetchall()


def _fila(conn, pid):
    return conn.execute("SELECT id, full_name, fiflp_id, ficha_id, union_por FROM players WHERE id=?",
                        (pid,)).fetchone()


def _ficha_de(conn, pid):
    r = _fila(conn, pid)
    principal = r[3] or r[0]
    return principal, [m for (m,) in conn.execute(
        "SELECT id FROM players WHERE id=? OR ficha_id=? ORDER BY id", (principal, principal))]


def _perfil_txt(p):
    return "; ".join(f"{s} {c[:3].lower()} {g} {t} ({n})" for s, c, g, t, n in p) or "sin apariciones"


def ejemplos_d12(conn, antes: dict, movidas) -> list[str]:
    """Las líneas de los cinco ejemplos del mapa D12, antes y después (iniciales e id interno)."""
    lineas = []
    destinos = defaultdict(set)
    for _, _, de, a, _ in movidas:
        destinos[de].add(a)
    for pid in EJEMPLOS_D12:
        r = _fila(conn, pid)
        if r is None:
            lineas.append(f"- {pid}: no está en la base.")
            continue
        lineas.append(f"- **{pid}, «{iniciales(r[1])}»** ({'con' if r[2] is not None else 'sin'} id)")
        lineas.append(f"  - antes: {_perfil_txt(antes.get(pid, []))}")
        principal, miembros = _ficha_de(conn, pid)
        lineas.append(f"  - después, su ficha ({len(miembros)} identidades, principal {principal}): "
                      f"{_perfil_txt([x for m in miembros for x in perfil(conn, m)])}")
        for a in sorted(destinos.get(pid, ())):
            ra = _fila(conn, a)
            pa, ma = _ficha_de(conn, a)
            estado = (f"en la ficha de {pa} (union_por {ra[4]})" if ra[3] else
                      f"principal de una ficha de {len(ma)} identidades" if len(ma) > 1 else "ficha suelta")
            lineas.append(f"  - separada a {a} ({'con' if ra[2] is not None else 'sin'} id), {estado}: "
                          f"{_perfil_txt(perfil(conn, a))}")
    return lineas


def informe(r: dict, medida_antes: dict, medida_despues: dict, d12: list[str], segunda: dict | None,
            integridad: dict) -> str:
    """docs/identidad-migracion.md: solo cifras (y los ejemplos del mapa con iniciales)."""
    sep, fi = r["separar"], r["fichas"]
    ca, cd = medida_antes["cuenta"], medida_despues["cuenta"]
    L = ["# La migración de la fase 2C, ensayada sobre una copia de la base",
         "",
         "Generado por `python3 scripts/migrate_identidad.py --db <copia> --informe docs/identidad-migracion.md "
         "--muestras <fichero no versionado> --dos-veces` sobre una copia de `futbolbase.db` (la de la rama "
         "`fase2c`). Solo cifras: los nombres de los niños, en las muestras para revisar a ojo, van en un fichero "
         "aparte que no se versiona. Reglas: `docs/identidad.md`.",
         "",
         "## Qué hace",
         "",
         "1. Esquema: `players.ficha_id`, `union_por` y, para la identidad sin id, `team_id`, `season_id` y "
         "`ordinal`; `norm_name` sigue siendo único: `NOMBRE@<equipo>.<temporada>` (y `#<ordinal>` desde el "
         "segundo del mismo nombre en una alineación).",
         "2. Separar: cada aparición, con sus sucesos de ese partido y equipo, a su identidad de acta según el "
         "original (los del bot, si hay; si no, los raws): sin id, a la de (nombre, equipo, temporada); con id, a "
         "la fila de ese id. Sin original: la liga prebenjamín de Gran Canaria desde 2024-25 (`PGC*`, `PG*`), "
         "sin id; lo demás, lo que diga la fila. No se borra ninguna fila.",
         "3. Resolver: `identidad.resolver` sobre todas las identidades con aparición o suceso, y `ficha_id` "
         "(NULL en la principal) y `union_por` en cada fila.",
         "",
         "Decisiones (lecturas que unen menos y no pierden nada):",
         "",
         "- Casar una entrada del original con su aparición: el partido por `cod_acta`, el equipo por el lado; "
         "primero por el `fiflp_id` de la fila, después por el nombre normalizado y, entre homónimos, por el "
         "dorsal; si queda una de cada, son la misma.",
         "- Una aparición sin dorsal que el original no trae es un goleador de otra lectura del acta (el "
         "importador solo deja sin dorsal a quien sale en los sucesos y no en la alineación): sin id.",
         "- El ordinal sale del dorsal en el original; sin original, si dos apariciones de un equipo y partido "
         "fueran a la misma identidad sin id, también por el dorsal (no se pierde ninguna).",
         "- La identidad sin id es de (nombre, equipo, temporada), sin la categoría: un mismo equipo de la base "
         "juega a veces dos categorías en una temporada; identidades sin id que caen en dos: "
         f"{cd.get('identidades sin id en dos categorías', 0)}.",
         "",
         "## Recuentos por tabla",
         "",
         "| Tabla | Antes | Después |",
         "|---|---:|---:|"]
    for t in TABLAS:
        L.append(f"| `{t}` | {r['antes'][t]:,} | {r['despues'][t]:,} |".replace(",", "."))
    L += ["",
          "Iguales salvo `players`, que solo crece (no se borra ninguna fila).",
          "",
          "## Fichas",
          "",
          "| | Antes | Después |",
          "|---|---:|---:|",
          f"| Fichas (con alguna aparición) | {ca.get('fichas', 0)} | {cd.get('fichas', 0)} |",
          f"| Con algún id de la federación (v1 publicaba las filas con `fiflp_id`) | {ca.get('fichas con id', 0)} | "
          f"{cd.get('fichas con id', 0)} |",
          f"| Sin ningún id | {ca.get('fichas sin ningún id', 0)} | {cd.get('fichas sin ningún id', 0)} |",
          f"| Imposibles por edad | {ca.get('imposibles por edad', 0)} | {cd.get('imposibles por edad', 0)} |",
          f"| Imposibles por solape (dos clubes a la vez) | {ca.get('imposibles por solape', 0)} | "
          f"{cd.get('imposibles por solape', 0)} |",
          f"| Filas de `players` sin ninguna aparición | {ca.get('filas sin aparición', 0)} | "
          f"{cd.get('filas sin aparición', 0)} |",
          f"| Filas sin aparición ni suceso | {ca.get('filas sin aparición ni suceso', 0)} | "
          f"{cd.get('filas sin aparición ni suceso', 0)} |",
          "",
          f"Identidades con aparición o suceso: {fi['identidades']}; fichas que da el resolvedor: {fi['fichas']}.",
          "",
          "Uniones (identidades que no son la principal de su ficha, por la regla que las unió):",
          ""]
    for regla, nombre in (("equipo", "U0, mismo equipo y temporada"), ("club", "mismo club (U0 de club y U1)"),
                          ("nombre", "U2, candidata única")):
        L.append(f"- {nombre} (`{regla}`): {fi['uniones'].get(regla, 0)}")
        if regla == "club" and "club y temporada" in fi:
            L += [f"  - de ellas, U0 de club, mismo club y temporada: {fi['club y temporada']}",
                  f"  - U1, mismo club, temporadas seguidas: {fi['uniones'].get('club', 0) - fi['club y temporada']}"]
    L += ["", "## Separar", ""]
    for clave in ("apariciones separadas", "apariciones separadas de filas con id",
                  "apariciones separadas de filas sin id", "filas de las que se separaron apariciones",
                  "corregidas por identificador", "corregidas desde una fila con otro id",
                  "corregidas desde una fila sin id", "filas de las que se corrigieron apariciones",
                  "sucesos movidos", "identidades sin id creadas", "filas con id creadas",
                  "ordinales puestos por dorsal", "apariciones sin original"):
        L.append(f"- {clave}: {sep.get(clave, 0)}")
    L += ["", "Lo que no casó entre el original y la base (no se tocó, salvo lo que se dice):", ""]
    for clave in ("actas del original sin partido en la base", "entradas de la alineación sin aparición en la base",
                  "entradas de los sucesos sin aparición en la base",
                  "sucesos de un nombre con homónimos en la alineación (sin tocar)",
                  "apariciones sin dorsal que el original no trae (goleador: sin id)",
                  "apariciones con dorsal que el original no trae (regla sin original)",
                  "apariciones que no se movieron por un choque"):
        L.append(f"- {clave}: {sep.get(clave, 0)}")
    L += ["",
          "Una entrada del original sin aparición en la base, o una aparición que el original no trae, es de "
          "otra lectura del acta (la base se importó de una versión y el raw es de otra): no se crea ni se "
          "borra ninguna aparición. Las apariciones sin dorsal que el original no trae son goleadores que no "
          "estaban en la alineación (el importador solo deja sin dorsal a esos; ninguna entrada de alineación "
          "de los raws va sin dorsal) y van sin id, como todo goleador fuera de la alineación; las que tienen "
          "dorsal siguen la regla sin original (con `fiflp_id` en la fila, se quedan)."]
    L += ["", "Originales leídos:", ""]
    for clave, n in sorted(r["originales"].items()):
        L.append(f"- {clave}: {n}")
    L += ["", "## Imposibles que quedan", ""]
    if not medida_despues["imposibles"]:
        L.append("Ninguna.")
    resumen = Counter((tipo, "una sola identidad, con id" if len(m) == 1 and con_id else
                       "una sola identidad, sin id" if len(m) == 1 else "varias identidades")
                      for _, tipo, m, _, con_id in medida_despues["imposibles"])
    for (tipo, forma), n in sorted(resumen.items()):
        L.append(f"- por {tipo}, {forma}: {n}")
    if any(len(m) == 1 and con_id for _, _, m, _, con_id in medida_despues["imposibles"]):
        L += ["", "Una sola identidad con id es lo que dice la federación: el mismo id en dos equipos de clubes "
              "distintos (para `identidad.club`) la misma temporada y categoría, con fechas que se cruzan: un "
              "cambio de club a mitad de temporada, un niño que juega en dos equipos o dos grafías de un mismo "
              "club que la clave de club no junta. No lo hace la migración (el resolvedor no une nada a una "
              "identidad así) y no se separa: el id manda."]
    if medida_despues["imposibles"]:
        L += ["", "<details><summary>Todas (ficha, tipo, identidades y tramos: temporada, categoría, equipo)</summary>",
              ""]
    for principal, tipo, miembros, vistas, _ in medida_despues["imposibles"]:
        tramos = sorted({(v[0], {1: 'pre', 2: 'ben', 3: 'ale'}.get(v[1], '?'), v[2]) for v in vistas})
        L.append(f"- ficha {principal} ({tipo}; {len(miembros)} identidades): "
                 + "; ".join(f"{a}-{(a + 1) % 100:02d} {n} {e}" for a, n, e in tramos))
    if medida_despues["imposibles"]:
        L += ["", "</details>"]
    L += ["", "## Los cinco ejemplos del mapa (D12)", ""] + d12
    L += ["", "## Comprobaciones", "",
          f"- `PRAGMA integrity_check`: {integridad.get('integrity_check')}",
          f"- `PRAGMA foreign_key_check`: {integridad.get('foreign_key_check')}",
          f"- `ficha_id` que apuntan a una fila que no existe o que no es principal: {integridad.get('punteros malos')}"]
    if segunda is not None:
        L.append(f"- Segunda pasada seguida: recuentos iguales: {segunda['recuentos iguales']}; "
                 f"`ficha_id`/`union_por` iguales: {segunda['fichas iguales']}; apariciones movidas: "
                 f"{segunda['movidas']}; filas cambiadas por el resolvedor: {segunda['cambiadas']}.")
    L += ["", "## Tiempos (segundos)", ""]
    for clave, s in r["tiempos"].items():
        L.append(f"- {clave}: {s}")
    L.append(f"- de `resolver_fichas`: cargar {fi['segundos_cargar']}, resolver {fi['segundos_resolver']}")
    return "\n".join(L) + "\n"


def _describe(conn, pid):
    r = _fila(conn, pid)
    return f"{pid} «{r[1]}» ({'id ' + str(r[2]) if r[2] is not None else 'sin id'}): {_perfil_txt(perfil(conn, pid))}"


def uniones_de_club_y_temporada(conn) -> list[int]:
    """Las identidades con union_por 'club' que comparten club y temporada con otra de su ficha: las de la U0
    de club (ronda 3 de docs/identidad.md). Las demás 'club' son de U1: U1 solo une de uno a uno, así que la
    identidad que une es la única de su ficha en ese club y temporada."""
    vistas = _vistas(conn)
    ficha = {pid: f or pid for pid, f in conn.execute("SELECT id, ficha_id FROM players")}
    por_ficha = defaultdict(list)
    for pid in vistas:
        por_ficha[ficha[pid]].append(pid)
    lados = {pid: {(club(v[2] or ""), v[0]) for v in vs} for pid, vs in vistas.items()}
    return [pid for (pid,) in conn.execute("SELECT id FROM players WHERE union_por='club' ORDER BY id")
            if any(lados.get(pid, set()) & lados[o] for o in por_ficha[ficha[pid]] if o != pid)]


def muestras(conn, movidas, semilla: int = SEMILLA, n: int = 20) -> str:
    """20 uniones de cada tipo y 20 separaciones al azar (semilla fija), con nombres: para revisar a ojo."""
    rnd = random.Random(semilla)
    L = ["# Muestras de la migración de la fase 2C (con nombres: NO se versiona)", "",
         f"Semilla {semilla}. Cada línea: la identidad y, debajo, la principal de su ficha (o la fila de la que "
         "salió).", ""]
    de_temporada = set(uniones_de_club_y_temporada(conn))
    for regla, titulo in (("nombre", "U2, candidata única"), ("club", "U1, mismo club, temporadas seguidas"),
                          ("club-temporada", "U0 de club, mismo club y temporada"), ("equipo", "U0, mismo equipo")):
        ids = [pid for (pid,) in conn.execute("SELECT id FROM players WHERE union_por=? ORDER BY id",
                                              (regla.split("-")[0],))]
        ids = [pid for pid in ids if (pid in de_temporada) == (regla == "club-temporada")]
        L += [f"## {titulo} ({len(ids)} en total)", ""]
        for pid in sorted(rnd.sample(ids, min(n, len(ids)))):
            principal = _fila(conn, pid)[3]
            L += [f"- {_describe(conn, pid)}", f"  - principal: {_describe(conn, principal)}"]
        L.append("")
    pares = sorted({(de, a) for _, _, de, a, t in movidas if t == "separada"})
    L += [f"## Separaciones ({len(pares)} pares de fila de origen e identidad nueva)", ""]
    for de, a in sorted(rnd.sample(pares, min(n, len(pares)))):
        principal = _fila(conn, a)[3]
        L += [f"- {_describe(conn, a)}" + (f" — en la ficha de {principal} ({_fila(conn, a)[4]})" if principal else ""),
              f"  - salió de: {_describe(conn, de)}"]
    return "\n".join(L) + "\n"


def comprobar(conn) -> dict:
    malos = conn.execute(
        """SELECT count(*) FROM players p LEFT JOIN players q ON q.id = p.ficha_id
            WHERE p.ficha_id IS NOT NULL AND (q.id IS NULL OR q.ficha_id IS NOT NULL)""").fetchone()[0]
    return {"integrity_check": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": len(conn.execute("PRAGMA foreign_key_check").fetchall()) or "sin fallos",
            "punteros malos": malos}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, help="la base a migrar (para ensayar: una copia)")
    ap.add_argument("--raws", default=SCRIPTS, help="la carpeta de los originales (raws y del bot)")
    ap.add_argument("--informe", help="escribe aquí el informe (solo cifras)")
    ap.add_argument("--muestras", help="escribe aquí las muestras con nombres (fichero NO versionado)")
    ap.add_argument("--dos-veces", action="store_true", help="migra otra vez y comprueba que no cambia nada")
    args = ap.parse_args(argv)
    conn = sqlite3.connect(args.db)
    medida_antes = medida_fichas(conn)
    antes_d12 = {pid: perfil(conn, pid) for pid in EJEMPLOS_D12}
    r = migrate(conn, args.raws)
    segunda = None
    if args.dos_veces:
        fichas1 = conn.execute("SELECT id, ficha_id, union_por FROM players ORDER BY id").fetchall()
        r2 = migrate(conn, args.raws)
        fichas2 = conn.execute("SELECT id, ficha_id, union_por FROM players ORDER BY id").fetchall()
        segunda = {"recuentos iguales": r2["antes"] == r2["despues"] == r["despues"],
                   "fichas iguales": fichas1 == fichas2, "movidas": len(r2["movidas"]),
                   "cambiadas": r2["fichas"]["cambiadas"], "segundos resolver_fichas": r2["fichas"]["segundos"]}
        print(f"segunda pasada: {segunda}")
    medida_despues = medida_fichas(conn)
    r["fichas"]["club y temporada"] = len(uniones_de_club_y_temporada(conn))
    integridad = comprobar(conn)
    print(f"comprobaciones: {integridad}")
    if args.informe:
        with open(args.informe, "w", encoding="utf-8") as f:
            f.write(informe(r, medida_antes, medida_despues, ejemplos_d12(conn, antes_d12, r["movidas"]), segunda,
                            integridad))
    if args.muestras:
        with open(args.muestras, "w", encoding="utf-8") as f:
            f.write(muestras(conn, r["movidas"]))
    print(json.dumps({k: r[k] for k in ("antes", "despues", "separar", "tiempos")}, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in r["fichas"].items()}, ensure_ascii=False))
    print(json.dumps(medida_despues["cuenta"], ensure_ascii=False))


if __name__ == "__main__":
    main()
