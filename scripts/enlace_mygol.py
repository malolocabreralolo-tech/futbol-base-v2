"""enlace_mygol.py — Qué niño de la liga de escuelas (MyGol, docs/mygol.md) es qué ficha de la federación.

La regla (enlazar) es pura: sin base ni red. Un niño de MyGol (un id POR TEMPORADA: MyGol crea las fichas de
nuevo cada año) se enlaza con una ficha solo si:

  1. su nombre es completo: «APELLIDO APELLIDO, NOMBRE» (identidad.nombre_completo);
  2. esa temporada no hay en MyGol otro niño con el mismo nombre en un club que no tenga nada que ver con el
     suyo (si lo hay, son dos niños y no se sabe cuál es cuál: no se enlaza ninguno de los de ese nombre);
  3. hay UNA sola ficha con ese nombre exacto en alguna de sus identidades (la principal o una unida);
  4. la edad cuadra: algún año de nacimiento de la ficha (estimado solo con la federación) cabe en la
     ventana de la categoría de escuela de esa temporada, con un año de margen por el lado joven;
  5. y, ya con todos, a ninguna ficha le llegan dos niños de la misma temporada en clubes sin nada en común
     (por dos nombres distintos de sus identidades): si pasa, ninguno de esa temporada.

Es estrecha a propósito, porque es peor enlazar a un niño con otro que no enlazarlo. Lo medido el 25/11/2026
(sobre los cinco originales y la base): 5.196 niños de MyGol, 4.905 con dos apellidos. Así se enlazan 1.548
con 983 fichas, con un error estimado por debajo del 1,3 % (homónimos de edad compatible que cabe esperar
por azar). Con el primer apellido solo se equivocaría en torno al 16 %: no se hace. Exigir además el mismo
club solo añadiría 6 niños (y los nombres de club de MyGol y de la federación no casan bien): tampoco. 13
nombres completos se repiten la misma temporada en clubes distintos de MyGol (alguno en los dos equipos del
mismo partido): son dos niños, y la regla 2 los deja fuera.

El enlace nunca une dos fichas de la federación entre sí ni cambia una ficha: solo le añade sus temporadas
de escuela (generate_js) y, con ellas, afina su año de nacimiento.
"""
import os
import sys
from dataclasses import dataclass
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from identidad import nombre_completo  # noqa: E402
from nacimiento import VENTANA  # noqa: E402

# Un niño de escuela puede jugar un año con los mayores (en la liga de escuelas es muy habitual: en algún
# torneo, la mitad); quedarse con los pequeños, no.
MARGEN_JOVEN = 1


@dataclass(frozen=True)
class Nino:
    """Un niño de MyGol en una temporada."""
    id: int                     # el de MyGol, de esa temporada
    norm: str                   # identidad.normalizar("<apellidos>, <nombre>")
    temporada: int              # año de inicio
    categoria: str | None       # en minúsculas; None si el torneo no la tiene decidida
    clubes: frozenset[str]      # identidad.club de cada equipo de MyGol en el que sale esa temporada


@dataclass(frozen=True)
class Ficha:
    """Una ficha de la federación."""
    id: int                     # el players.id de su principal
    nombres: frozenset[str]     # el nombre normalizado (sin sufijo '#…') de cada una de sus identidades
    anios: tuple[int, ...]      # su año de nacimiento estimado solo con la federación; () si no se sabe


def edad_compatible(anios: tuple[int, ...], temporada: int, categoria: str | None) -> bool:
    """¿Puede quien nació en alguno de `anios` jugar en `categoria` la temporada que empieza `temporada`? Sin
    categoría (o una sin ventana) o sin años no hay con qué descartarlo: sí."""
    if not anios or categoria not in VENTANA:
        return True
    mayor, menor = VENTANA[categoria]
    return any(temporada - mayor <= a <= temporada - menor + MARGEN_JOVEN for a in anios)


def _choca(grupo) -> bool:
    """¿Hay en el grupo dos niños en clubes sin ninguno en común?"""
    grupo = list(grupo)
    return any(a.clubes.isdisjoint(b.clubes) for i, a in enumerate(grupo) for b in grupo[i + 1:])


def enlazar(ninos: Iterable[Nino], fichas: Iterable[Ficha]) -> dict[int, int]:
    """{id de MyGol: id de la ficha} de los niños que se pueden enlazar con seguridad (la regla de arriba),
    en orden de id de MyGol. No depende del orden de entrada.

    Un id de MyGol que sale en dos torneos (dos categorías, o, rara vez, dos temporadas con el mismo id) es un
    Nino por cada uno: se enlaza solo si todos ellos llevan a la misma ficha, porque el enlace es del id."""
    ninos = sorted(set(ninos), key=lambda n: (n.id, n.temporada, n.categoria or "", n.norm, sorted(n.clubes)))
    # Las fichas de cada nombre (un nombre en dos identidades de la misma ficha cuenta una vez).
    por_nombre: dict[str, set[int]] = {}
    anios: dict[int, tuple[int, ...]] = {}
    for f in fichas:
        anios[f.id] = f.anios
        for nombre in f.nombres:
            por_nombre.setdefault(nombre, set()).add(f.id)
    # 2: los nombres que esa temporada son de dos niños.
    mismo_nombre: dict[tuple[int, str], list[Nino]] = {}
    for n in ninos:
        mismo_nombre.setdefault((n.temporada, n.norm), []).append(n)
    dos_ninos = {k for k, grupo in mismo_nombre.items() if _choca(grupo)}
    candidatos: dict[Nino, int | None] = {}
    for n in ninos:
        candidatos[n] = None
        if not nombre_completo(n.norm) or (n.temporada, n.norm) in dos_ninos:
            continue
        unica = por_nombre.get(n.norm, set())
        if len(unica) != 1:
            continue                    # 3: ninguna ficha, o dos (la duda)
        (fid,) = unica
        if edad_compatible(anios[fid], n.temporada, n.categoria):
            candidatos[n] = fid
    # 5: dos niños de la misma temporada en clubes sin nada en común no pueden ser la misma ficha; como no
    # se sabe cuál de los dos lo es, se quitan todos los de esa ficha y esa temporada.
    por_ficha: dict[tuple[int, int], list[Nino]] = {}
    for n, fid in candidatos.items():
        if fid is not None:
            por_ficha.setdefault((fid, n.temporada), []).append(n)
    for grupo in por_ficha.values():
        if _choca(grupo):
            for n in grupo:
                candidatos[n] = None
    # Por id: todos sus torneos a la misma ficha, o nada.
    por_id: dict[int, set[int | None]] = {}
    for n, fid in candidatos.items():
        por_id.setdefault(n.id, set()).add(fid)
    return {i: next(iter(fids)) for i, fids in por_id.items() if len(fids) == 1 and None not in fids}


# ---------------------------------------------------------------------------
# Con base: los enlaces en mygol_enlaces, rehechos en cada pasada del bot
# ---------------------------------------------------------------------------

# Las tablas de MyGol que hacen falta (las de import_mygol): sin alguna, no hay nada que enlazar.
TABLAS_MYGOL = ("mygol_torneos", "mygol_equipos", "mygol_jugadores", "mygol_partidos", "mygol_participaciones")
# Derivada: se rehace entera en cada pasada con las fichas de ese momento (como players.ficha_id), así que
# sigue a la ficha si el resolvedor le cambia la principal. jugador_id, el de mygol_jugadores; player_id, el
# players.id de la principal de su ficha.
ESQUEMA = """CREATE TABLE IF NOT EXISTS mygol_enlaces (
    jugador_id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL)"""


def _tablas(conn) -> set[str]:
    return {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def ninos_de(conn) -> list[Nino]:
    """Los niños de MyGol de la base: uno por id y torneo (temporada y categoría), con los clubes de los
    equipos en los que sale en él. Sin las tablas mygol_*, []."""
    from identidad import club
    if not set(TABLAS_MYGOL) <= _tablas(conn):
        return []
    clubes: dict[tuple, set[str]] = {}
    for jid, norm, temporada, categoria, equipo in conn.execute("""
            SELECT j.id, j.norm, t.temporada, t.categoria, e.nombre
              FROM mygol_participaciones p JOIN mygol_jugadores j ON j.id = p.jugador_id
              JOIN mygol_partidos m ON m.id = p.partido_id JOIN mygol_torneos t ON t.id = m.torneo_id
              LEFT JOIN mygol_equipos e ON e.id = p.equipo_id
             GROUP BY j.id, t.temporada, t.categoria, p.equipo_id"""):
        try:
            anio = int(str(temporada)[:4])
        except ValueError:
            continue                    # una temporada que no se entiende: ese torneo no cuenta
        suyos = clubes.setdefault((jid, norm or "", anio, categoria.lower() if categoria else None), set())
        # Un equipo sin nombre no da club: sin ninguno, el niño no comparte club con nadie (la prudencia).
        if equipo and club(equipo):
            suyos.add(club(equipo))
    return [Nino(id=jid, norm=norm, temporada=anio, categoria=cat, clubes=frozenset(cs))
            for (jid, norm, anio, cat), cs in sorted(clubes.items(), key=lambda kv: (kv[0][0], kv[0][2],
                                                                                    kv[0][3] or ""))]


def fichas_de(conn) -> list[Ficha]:
    """Las fichas de la federación (generate_js._fichas): todas, publicadas o no (una más con el mismo nombre
    es una duda más), con los nombres de todas sus identidades y el año de nacimiento estimado SOLO con sus
    apariciones federadas: el que publicaría el generador sin la escuela (sin los años confirmados a mano). Si
    contara la escuela, el enlace dependería de sí mismo. Sin players.fiflp_id (una base sin migrar), [].

    Solo con lo que ve la web (categorias.EN_WEB, leído al llamar), como el generador (que trabaja sobre
    vista_web.copia_web): hasta que la web enseñe infantil, cadete y juvenil (parte E2), una identidad que
    solo sale en ellas no es una ficha más con su nombre, y sus partidos no cuentan para el año. Si no, un
    niño de cadete con el nombre de uno de benjamín le quitaría su enlace, y uno de benjamín al que la
    federación da el mismo id en cadete cambiaría de año y perdería el suyo."""
    import generate_js as G
    from migrate_identidad import _filtro_categorias
    from nacimiento import estimar
    if not any(r[1] == "fiflp_id" for r in conn.execute("PRAGMA table_info(players)")):
        return []
    filtro, cats = _filtro_categorias(None)
    # Las identidades con algo (una aparición o un suceso) solo fuera de la web: para la web no existen. Sin
    # ningún grupo fuera de la web (hasta el primer paso del director), ninguna: ni se busca.
    hay_fuera = conn.execute(f"SELECT 1 FROM groups g JOIN categories c ON c.id = g.category_id "
                             f"WHERE NOT {filtro} LIMIT 1", cats).fetchone()
    fuera = set() if not hay_fuera else {pid for (pid,) in conn.execute(f"""
            SELECT x.player_id FROM (SELECT player_id, match_id FROM appearances
                                     UNION ALL SELECT player_id, match_id FROM match_events) x
              JOIN matches m ON m.id = x.match_id JOIN groups g ON g.id = m.group_id
              JOIN categories c ON c.id = g.category_id
             GROUP BY x.player_id HAVING max({filtro}) = 0""", cats)}
    f = G._fichas(conn)
    nombres: dict[int, set[str]] = {}
    for pid, principal in f["ficha"].items():
        if pid in fuera:
            continue
        nombre = f["nombre"].get(pid) or ""
        suyos = nombres.setdefault(principal, set())
        if nombre and not nombre.startswith("#"):
            suyos.add(nombre)
    # Una observación por temporada y categoría con los partidos de todas sus identidades: la misma cuenta que
    # hace generate_js._datos_fichas (con los mismos JOIN), sin la consulta grande.
    partidos: dict[int, dict[tuple[int, str], int]] = {}
    for pid, anio, categoria, pj in conn.execute(f"""
            SELECT a.player_id, s.start_year, LOWER(c.name), COUNT(*)
              FROM appearances a JOIN players p ON p.id = a.player_id
              JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
              JOIN seasons s ON s.id = g.season_id JOIN teams t ON t.id = a.team_id
              JOIN categories c ON c.id = g.category_id
             WHERE {filtro}
             GROUP BY a.player_id, s.start_year, LOWER(c.name)""", cats):
        principal = f["ficha"].get(pid)
        if principal not in f["publicadas"]:
            continue
        suyas = partidos.setdefault(principal, {})
        suyas[(anio, categoria)] = suyas.get((anio, categoria), 0) + pj
    return [Ficha(id=p, nombres=frozenset(ns),
                  anios=estimar((y, c, n) for (y, c), n in partidos.get(p, {}).items()))
            for p, ns in sorted(nombres.items())]


def guardar_enlaces(conn, registro=print) -> int:
    """Rehace mygol_enlaces entera con lo que diga enlazar, en un SAVEPOINT (si algo falla, queda como
    estaba). Si el contenido no cambia, no escribe nada (una pasada sin cambios no ensucia la base). Sin las
    tablas mygol_*, no crea nada (y vacía la de enlaces si quedaba alguna de antes). Devuelve cuántos hay."""
    tablas = _tablas(conn)
    nuevos = enlazar(ninos_de(conn), fichas_de(conn)) if set(TABLAS_MYGOL) <= tablas else None
    if nuevos is None and "mygol_enlaces" not in tablas:
        return 0
    if "mygol_enlaces" not in tablas:
        conn.execute(ESQUEMA)
    nuevos = nuevos or {}
    actuales = dict(conn.execute("SELECT jugador_id, player_id FROM mygol_enlaces"))
    fichas = len(set(nuevos.values()))
    if actuales == nuevos:
        registro(f"  MyGol (enlaces): {len(nuevos)} niños enlazados con {fichas} fichas, sin cambios")
        return len(nuevos)
    try:
        conn.execute("SAVEPOINT enlace_mygol")
        conn.execute("DELETE FROM mygol_enlaces")
        conn.executemany("INSERT INTO mygol_enlaces VALUES (?, ?)", sorted(nuevos.items()))
        conn.execute("RELEASE SAVEPOINT enlace_mygol")
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT enlace_mygol")
        conn.execute("RELEASE SAVEPOINT enlace_mygol")
        raise
    conn.commit()
    registro(f"  MyGol (enlaces): {len(nuevos)} niños enlazados con {fichas} fichas "
             f"({len(set(nuevos.items()) - set(actuales.items()))} nuevos o cambiados, "
             f"{len(set(actuales) - set(nuevos))} quitados)")
    return len(nuevos)
