"""La base «de después»: la que dejará el bot cuando el director haya activado infantil, cadete y juvenil
(pasos D3-D5 de la parte E1) y su carril los haya leído.

No empieza por «test_»: pytest no la recoge. La usan test_vista_web.py (test_generador_igual_con_y_sin_mayores) y
scripts/prueba_mayores.py, que pasa la suite entera sobre esa base. Es la red contra el fallo del 25/11: una
prueba «sobre la base real» que valía con la base de antes y no con la de después dejó al bot una pasada sin
publicar. Toda prueba que mira la base real o los data-*.js tiene que valer con las dos.

    poblar(conn, categorias=("INFANTIL", "CADETE", "JUVENIL"), temporada=None, islas=False) -> dict

escribe en `conn` (una COPIA: nunca la base del árbol) lo que dejaría el bot en la temporada EN CURSO de esa base
(sin `temporada`; con ella, tiene que ser la en curso), con sus mismos pasos y sus mismas funciones, donde se puede
sin navegador. La temporada sale de la base, no de una fecha escrita aquí: la puerta de pruebas del bot corre esto en
cada pasada, y el día que activate_season ponga 2027-28 en curso no puede ponerse en rojo (el nombre del acta, las
fechas de las jornadas y los años de los niños reutilizados salen de su año de inicio):

  1. la activación (como activar_auto.activar, por competición): un raw sintético con la forma del de
     fetch_fiflp_islas (por categoría, tres competiciones con convenio, con los nombres del catálogo de 2026-27: una liga de Gran Canaria con
     dos grupos, una liga de Lanzarote y una copa a eliminatorias; en cadete, además, la liga interinsular, con
     equipos de Gran Canaria y de Lanzarote), su manifiesto con fiflp_manifest.build (con
     los códigos que ya tiene la temporada en `taken`), activate_season.validate_manifest, los nombres de los
     equipos con activate_season.raw_team_names, la verificación con verify_sources y el alta con add_groups;
  2. la pasada del carril (lo que escribe update_fiflp de cada grupo): la jornada y la clasificación con
     update_group, la lectura completa hecha (fiflp_full_pending), los goleadores con write_scorers, un acta por
     partido jugado con apply_acta (que importa con import_fiflp_actas._import_one) y la ficha de la temporada
     (team_seasons) de los equipos nuevos, como update_directorio.

Los equipos son clubes que ya están en la base (con su nombre de la federación de esta temporada, el de sus
fichas: el mismo club en benjamín y en juvenil es la misma fila de teams) y uno nuevo por grupo. Seis jornadas
jugadas por liga (y la séptima sin jugar), con resultado, clasificación y goleadores; dos rondas jugadas en la
copa. Cada acta, 18 jugadores por equipo: un tercio con el id de la federación de un niño de benjamín o alevín
de entre 7 y 4 temporadas antes (de 2019-20 a 2022-23 para 2026-27) que ya está en la base (el mismo niño, más
mayor: la misma fila de players), en la categoría que le toca por su edad (_ids_de_la_base: la base de después tiene
que parecerse a la real, y un niño de prebenjamín de este año no juega en juvenil), el resto con ids nuevos. Y en el
primer grupo de Gran Canaria de cada categoría, dos equipos llevan además a dos niños sin id con el nombre, el club
y la temporada de dos sin id de otra categoría (SIN_ID_DE): en infantil, de dos alevines (el mismo niño, que sube);
en cadete y juvenil, de dos prebenjamines (otro niño, que se llama igual). Nunca la misma identidad: la de las
mayores lleva su categoría (migrate_identidad.norm_sin_id), como lo hace el importador; si son la misma ficha lo
decide el resolvedor por sus edades, cuando la web las enseñe.

Los nombres de los niños nuevos son inventados (f"JUGADOR {n:06d}, PRUEBA"); los de los reutilizados no se
escriben (con id, la fila conserva el suyo) salvo los sin id, que se leen de la copia al vuelo para que sean
el mismo nombre (nunca se imprimen ni salen de la copia, ni van en lo que devuelve). Con `islas`, también dos
grupos de «LIGA ALEVIN LANZAROTE FASE 1» (con categorias.ALEVIN_ISLAS a True durante la llamada: el paso D6).

Devuelve {"grupos": [códigos], "partidos": n jugados, "actas": n, "jugadores_reutilizados": n ids de la base,
"sin_id_reutilizados": n nombres sin id de otra categoría del mismo club y temporada, "sin_id_disponibles": n
equipos de la liga alevín y la prebenjamín de la temporada con dos sin id (con 0, el caso no se monta),
"sin_id_en_fila_ajena": n identidades sin id con apariciones en una de las mayores y en otra categoría (tiene que
ser 0)}.
"""
import contextlib
import random
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from categorias import MAYORES  # noqa: E402

SEMILLA = 20261125
# Por categoría: (competición del catálogo, isla, grupos, copa). Tres por categoría, todas con convenio, y en cadete
# además la liga interinsular (isla «interinsular», que la activación admite solo en las categorías nuevas desde la
# tarea 8 de la parte E1: activate_season.isla_admitida), con equipos de Gran Canaria y de Lanzarote.
COMPETICIONES = {
    "INFANTIL": (("LIGA PRIMERA INFANTIL DE GRAN CANARIA", "grancanaria", 2, False),
                 ("LIGA INFANTIL LANZAROTE FASE 1", "lanzarote", 1, False),
                 ("COPA CAMPEONES INFANTIL", "grancanaria", 1, True)),
    "CADETE": (("LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", "grancanaria", 2, False),
               ("LIGA CADETE INSULAR DE LANZAROTE", "lanzarote", 1, False),
               ("COPA CADETE INSULAR DE LANZAROTE", "lanzarote", 1, True),
               ("LIGA CADETE INTERINSULAR", "interinsular", 1, False)),
    "JUVENIL": (("LIGA SEGUNDA JUVENIL GRAN CANARIA", "grancanaria", 2, False),
                ("LIGA JUVENIL PREFERENTE LANZAROTE", "lanzarote", 1, False),
                ("COPA JUVENIL PREFERENTE FUERTEVENTURA", "fuerteventura", 1, True)),
}
ISLAS = (("LIGA ALEVIN LANZAROTE FASE 1", "lanzarote", 2, False),)
EQUIPOS_POR_GRUPO = 8
JUGADORES_POR_EQUIPO = 18
TITULARES = 11
JORNADAS_JUGADAS = 6
# Los ids de la federación de los niños nuevos, lejos de los de verdad (hoy, por debajo de 60 millones).
ID_NUEVO = 900_000_000
# Los de la federación de la competición y del grupo, inventados (no son los de ninguna de verdad).
COMP_BASE, GRUPO_BASE, ACTA_BASE = 99_000_000, 99_500_000, 990_000_000


def _primer_sabado(anio):
    """El primer sábado de octubre del año de inicio de la temporada (el 3 de octubre en 2026-27): las jornadas."""
    from datetime import date, timedelta
    d = date(anio, 10, 1)
    return d + timedelta(days=(5 - d.weekday()) % 7)


def _sabado(anio, k):
    from datetime import timedelta
    return (_primer_sabado(anio) + timedelta(days=7 * k)).strftime("%d-%m-%Y")


def _calendario(equipos):
    """Las jornadas de una liga a una vuelta (método del círculo): [[(local, visitante)]]."""
    eq = list(equipos)
    n = len(eq)
    out = []
    for r in range(n - 1):
        ronda = []
        for i in range(n // 2):
            a, b = eq[i], eq[n - 1 - i]
            ronda.append((a, b) if (r + i) % 2 == 0 else (b, a))
        out.append(ronda)
        eq = [eq[0]] + [eq[-1]] + eq[1:-1]
    return out


@contextlib.contextmanager
def _alevin_de_islas(activo):
    """categorias.ALEVIN_ISLAS a True mientras dura (en las dos copias del módulo, si las hay)."""
    import categorias
    modulos = [categorias] + [m for m in (sys.modules.get("scripts.categorias"),) if m]
    antes = [m.ALEVIN_ISLAS for m in modulos]
    try:
        if activo:
            for m in modulos:
                m.ALEVIN_ISLAS = True
        yield
    finally:
        for m, v in zip(modulos, antes):
            m.ALEVIN_ISLAS = v


# El EN_WEB de antes del paso E2-D2 de la parte E2 (docs/categorias-mayores.md, «En la web») y el de después.
EN_WEB_DE_ANTES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
EN_WEB_SEIS = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")


@contextlib.contextmanager
def con_en_web(en_web):
    """categorias.EN_WEB a `en_web` («antes», «seis» o una tupla; None: lo que diga categorias.py) mientras dura, en
    las dos copias del módulo si las hay. Para lo que una prueba vuelve a calcular ella misma sobre su copia (las
    fichas, los enlaces, la web): así vale igual con el EN_WEB de hoy y con el del paso E2-D2."""
    import categorias
    modulos = [categorias] + [m for m in (sys.modules.get("scripts.categorias"),) if m and m is not categorias]
    antes = [m.EN_WEB for m in modulos]
    valor = {"antes": EN_WEB_DE_ANTES, "seis": EN_WEB_SEIS}.get(en_web, en_web) if isinstance(en_web, str) else en_web
    try:
        if valor is not None:
            for m in modulos:
                m.EN_WEB = tuple(valor)
        yield
    finally:
        for m, v in zip(modulos, antes):
            m.EN_WEB = v


def _equipos_de_la_base(conn, sid):
    """{isla: [(team_id, nombre de la federación)]} de los equipos de la temporada con ficha (team_seasons), por
    id: los de los grupos que la base ya tiene (benjamín, prebenjamín, alevín). Recién empezada una temporada
    (activate_season la acaba de poner en curso y aún no tiene grupos con clasificación ni fichas), los de la más
    reciente que los tenga: los clubes son los mismos de un año a otro."""
    for (otra,) in [(sid,)] + conn.execute(
            "SELECT id FROM seasons WHERE id <> ? ORDER BY start_year DESC", (sid,)).fetchall():
        por_isla = _equipos_de_la_temporada(conn, otra)
        if por_isla.get("grancanaria"):
            return por_isla
    raise ValueError("la base no tiene ninguna temporada con equipos de Gran Canaria con ficha")


def _equipos_de_la_temporada(conn, sid):
    por_isla = {}
    vistos = set()
    for tid, fed, isla in conn.execute(
            """SELECT DISTINCT st.team_id, ts.fiflp_name, g.island FROM standings st
                 JOIN groups g ON g.id = st.group_id JOIN team_seasons ts ON ts.team_id = st.team_id AND ts.season_id = ?
                WHERE g.season_id = ? AND ts.fiflp_name IS NOT NULL ORDER BY st.team_id""", (sid, sid)):
        if tid in vistos or fed in {f for lst in por_isla.values() for _, f in lst}:
            continue
        vistos.add(tid)
        por_isla.setdefault(isla, []).append((tid, fed))
    return por_isla


# El caso «mismo nombre, club y temporada sin id»: en el primer grupo de Gran Canaria de cada categoría nueva, dos
# equipos llevan cada uno a dos niños sin id con el nombre de dos sin id de ese club y esa temporada en otra
# categoría (la liga de Gran Canaria de esa categoría, que va sin id en parte). En infantil, alevines: el mismo niño
# que sube a infantil (edades contiguas: el resolvedor tiene que poder unirlos en una ficha); en cadete y juvenil,
# prebenjamines: otro niño que se llama igual (seis años o más de diferencia: no se unen nunca). Cada categoría con
# otros equipos (`desde`): si no, un cadete y un juvenil sin id del mismo nombre y club se unirían entre ellos.
SIN_ID_DE = {"INFANTIL": ("ALEVIN", 0), "CADETE": ("PREBENJAMIN", 0), "JUVENIL": ("PREBENJAMIN", 2)}


def _sin_id_de(conn, sid, categoria):
    """[(team_id, nombre de la federación, [dos nombres sin id])] de los equipos de la liga de `categoria` de Gran
    Canaria de la temporada con dos niños sin id o más que solo juegan en ella: los del caso «mismo nombre y club
    sin id» (SIN_ID_DE)."""
    out = []
    for tid, fed in conn.execute(
            """SELECT DISTINCT st.team_id, ts.fiflp_name FROM standings st JOIN groups g ON g.id = st.group_id
                 JOIN categories c ON c.id = g.category_id
                 JOIN team_seasons ts ON ts.team_id = st.team_id AND ts.season_id = g.season_id
                WHERE g.season_id = ? AND upper(c.name) = ? AND g.island = 'grancanaria'
                  AND ts.fiflp_name IS NOT NULL ORDER BY st.team_id""", (sid, categoria)):
        nombres = [n for (n,) in conn.execute(
            """SELECT p.full_name FROM players p WHERE p.fiflp_id IS NULL AND p.team_id = ? AND p.season_id = ?
                 AND p.full_name LIKE '%,%' AND p.full_name NOT LIKE '#%'
                 AND EXISTS (SELECT 1 FROM appearances a JOIN matches m ON m.id = a.match_id
                               JOIN groups g ON g.id = m.group_id JOIN categories c ON c.id = g.category_id
                              WHERE a.player_id = p.id AND upper(c.name) = ?)
                 AND NOT EXISTS (SELECT 1 FROM appearances a JOIN matches m ON m.id = a.match_id
                                   JOIN groups g ON g.id = m.group_id JOIN categories c ON c.id = g.category_id
                                  WHERE a.player_id = p.id AND upper(c.name) <> ?)
               ORDER BY p.id LIMIT 2""", (tid, sid, categoria, categoria))]
        if len(nombres) == 2:
            out.append((tid, fed, nombres))
    return out


def categoria_natural(anio, nacido):
    """La categoría de las nuevas (infantil, cadete o juvenil) en la que juega la temporada que empieza `anio` quien
    nació en `nacido`, por su ventana natural (nacimiento.VENTANA), o None."""
    from nacimiento import VENTANA
    for cat in MAYORES:
        mayor, menor = VENTANA[cat.lower()]
        if anio - mayor <= nacido <= anio - menor:
            return cat
    return None


def _ids_de_la_base(conn, sid, anio):
    """[(id de la federación, categorías en las que puede jugar esta temporada)] de los niños de benjamín o alevín
    de entre 7 y 4 temporadas antes (de 2019-20 a 2022-23 para 2026-27) que no juegan esta temporada (los mismos
    niños, más mayores), por id. Sus categorías salen de su edad, como en la realidad: el año de nacimiento que
    estima la web con todo lo que ha jugado su ficha (nacimiento.estimar, con las filas de prebenjamín, benjamín y
    alevín de todas sus identidades) da su categoría natural (categoria_natural), que tiene que caber además con el
    intervalo del resolvedor de toda su ficha (identidad.intervalo: si no, ese niño no podría ser él). Un niño que
    fue benjamín en 2019-20 es cadete o juvenil en 2026-27, nunca infantil; uno de 2022-23, infantil o cadete. Y solo
    el id de la principal de cada ficha: la federación ha dado a algunos niños un id para cada partido (los «ids de un
    solo uso» que la U0 de identidad.py junta en su ficha), y reutilizar dos de ellos como dos niños de las nuevas
    sería inventar a un niño que juega a la vez en dos equipos."""
    from identidad import NIVEL, intervalo
    from nacimiento import estimar
    candidatos = [(f, ficha) for f, ficha in conn.execute(
        """SELECT DISTINCT p.fiflp_id, coalesce(p.ficha_id, p.id) FROM players p JOIN appearances a ON a.player_id = p.id
             JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
             JOIN seasons s ON s.id = g.season_id JOIN categories c ON c.id = g.category_id
            WHERE p.fiflp_id IS NOT NULL AND p.ficha_id IS NULL AND upper(c.name) IN ('BENJAMIN', 'ALEVIN')
              AND s.start_year BETWEEN ? AND ?
              AND p.fiflp_id NOT IN (SELECT p2.fiflp_id FROM players p2 JOIN appearances a2 ON a2.player_id = p2.id
                                     JOIN matches m2 ON m2.id = a2.match_id JOIN groups g2 ON g2.id = m2.group_id
                                     WHERE g2.season_id = ? AND p2.fiflp_id IS NOT NULL)
            ORDER BY p.fiflp_id""", (anio - 7, anio - 4, sid))]
    # Lo que ha jugado cada ficha de esos niños en prebenjamín, benjamín y alevín (las de la web de antes).
    fichas = {ficha for _, ficha in candidatos}
    obs = {}
    for ficha, inicio, cat, partidos in conn.execute(
            """SELECT coalesce(p.ficha_id, p.id), s.start_year, upper(c.name), count(*) FROM appearances a
                 JOIN players p ON p.id = a.player_id JOIN matches m ON m.id = a.match_id
                 JOIN groups g ON g.id = m.group_id JOIN seasons s ON s.id = g.season_id
                 JOIN categories c ON c.id = g.category_id
                WHERE upper(c.name) IN ('PREBENJAMIN', 'BENJAMIN', 'ALEVIN') GROUP BY 1, 2, 3"""):
        if ficha in fichas:
            obs.setdefault(ficha, []).append((inicio, cat, partidos))
    out = []
    for fid, ficha in candidatos:
        vistas = obs.get(ficha, [])
        lo = max(intervalo(y, NIVEL[c])[0] for y, c, _ in vistas)
        hi = min(intervalo(y, NIVEL[c])[1] for y, c, _ in vistas)
        cats = []
        for nacido in estimar((y, c.lower(), n) for y, c, n in vistas):
            cat = categoria_natural(anio, nacido)
            if cat and cat not in cats:
                a, b = intervalo(anio, NIVEL[cat])
                if max(lo, a) <= min(hi, b):
                    cats.append(cat)
        if cats:
            out.append((fid, tuple(cats)))
    return out


class _Fabrica:
    """Lo que se inventa, siempre igual para la misma base (SEMILLA): equipos, plantillas, resultados y actas."""

    def __init__(self, conn, sid, anio):
        self.rnd = random.Random(SEMILLA)
        self.anio = anio                # el año de inicio de la temporada en curso
        self.equipos = _equipos_de_la_base(conn, sid)
        # Por categoría nueva, los equipos (y sus dos nombres sin id) del caso «mismo nombre y club sin id».
        de_otra = {}
        self.sin_id = {}
        for cat, (otra, desde) in SIN_ID_DE.items():
            if otra not in de_otra:
                de_otra[otra] = _sin_id_de(conn, sid, otra)
            self.sin_id[cat] = de_otra[otra][desde:desde + 2]
        self.sin_id_disponibles = sum(len(v) for v in de_otra.values())
        ids = _ids_de_la_base(conn, sid, anio)
        self.rnd.shuffle(ids)
        self.ids_base = ids
        self.reutilizados = set()
        self.sin_id_usados = set()
        # Sobre una base que ya tiene lo de una pasada anterior (la de después, que es la del bot cuando ya ha
        # leído las mayores: prueba_mayores pasa la suite, y esta la vuelve a poblar), todo lo inventado va
        # detrás de lo que ya hay: otros ids de niño, de acta, de competición y de grupo.
        ronda = conn.execute("SELECT count(*) FROM groups WHERE url LIKE ?",
                             (f"%CodGrupo={str(GRUPO_BASE)[:3]}%",)).fetchone()[0]
        self.siguiente = 100_000 * ronda    # el número del próximo niño nuevo
        self.club_nuevo = 0
        self.comp = COMP_BASE + 1_000 * ronda
        self.grupo = GRUPO_BASE + 1_000 * ronda
        self.acta = ACTA_BASE + 100_000 * ronda
        self.plantillas = {}            # (categoría, nombre de la federación) -> [jugador]
        self.cursor = {}                # isla -> por dónde va en su lista de equipos

    def nuevo_club(self, categoria):
        self.club_nuevo += 1
        return f"PRUEBA MAYORES {self.club_nuevo:02d}, C.D."

    def equipos_de(self, isla, n, con_sin_id=False):
        """`n` equipos de la isla (los de la base, sin repetir dentro de una competición) y uno nuevo. De una
        interinsular, de Gran Canaria y de Lanzarote, alternos."""
        if isla == "interinsular":
            gc, lz = self.equipos["grancanaria"], self.equipos.get("lanzarote") or self.equipos["grancanaria"]
            lista = [t for par in zip(gc[len(gc) // 2:], lz[len(lz) // 2:]) for t in par]
        else:
            lista = self.equipos.get(isla) or self.equipos["grancanaria"]
        fijos = []
        if con_sin_id:
            fijos = [(tid, fed) for tid, fed, _ in self.sin_id.get(con_sin_id, ())]
        i = self.cursor.get(isla, 0)
        out = list(fijos)
        while len(out) < n - 1:
            tid, fed = lista[i % len(lista)]
            i += 1
            if fed not in {f for _, f in out}:
                out.append((tid, fed))
        self.cursor[isla] = i
        return [fed for _, fed in out]

    def reutilizado(self, categoria):
        """El siguiente id de la base (en el orden barajado) de un niño que puede jugar esta temporada en
        `categoria` por su edad (_ids_de_la_base), o None si no queda ninguno."""
        for i, (fid, cats) in enumerate(self.ids_base):
            if categoria in cats:
                del self.ids_base[i]
                return fid
        return None

    def plantilla(self, categoria, equipo):
        """Los 18 de un equipo en su categoría, los mismos en todas sus competiciones: un tercio con un id de la
        base (de un niño de su edad), el resto con uno nuevo; y en los equipos del caso sin id, dos sin id del
        mismo nombre."""
        clave = (categoria, equipo)
        if clave in self.plantillas:
            return self.plantillas[clave]
        jugadores = []
        for k in range(JUGADORES_POR_EQUIPO):
            self.siguiente += 1
            nombre = f"JUGADOR {self.siguiente:06d}, PRUEBA"
            # Solo en las mayores (un niño de benjamín de 2019-20 es hoy cadete o juvenil, no alevín), y en la suya.
            fid = self.reutilizado(categoria) if k % 3 == 0 and categoria in MAYORES else None
            if fid is not None:
                self.reutilizados.add(fid)
            else:
                fid = ID_NUEVO + self.siguiente
            jugadores.append({"name": nombre, "fiflp_id": fid})
        for tid, fed, nombres in self.sin_id.get(categoria, ()):
            if fed == equipo:
                for j, nombre in enumerate(nombres):
                    jugadores[JUGADORES_POR_EQUIPO - 1 - j] = {"name": nombre, "fiflp_id": None}
                    self.sin_id_usados.add((categoria, tid, nombre))
        self.plantillas[clave] = jugadores
        return jugadores

    def marcador(self, copa):
        while True:
            hs, as_ = self.rnd.randint(0, 5), self.rnd.randint(0, 4)
            if not copa or hs != as_:
                return hs, as_


def _clasificacion(equipos, jornadas):
    """La clasificación de la federación ({pos, team, pts, j, g, e, p, gf, gc, df}) de los partidos jugados."""
    t = {e: {"team": e, "pts": 0, "j": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0} for e in equipos}
    for jornada in jornadas:
        for m in jornada["matches"]:
            if m["hs"] is None:
                continue
            for yo, otro, gf, gc in ((m["home"], m["away"], m["hs"], m["as"]), (m["away"], m["home"], m["as"], m["hs"])):
                r = t[yo]
                r["j"] += 1
                r["gf"] += gf
                r["gc"] += gc
                if gf > gc:
                    r["g"] += 1
                    r["pts"] += 3
                elif gf == gc:
                    r["e"] += 1
                    r["pts"] += 1
                else:
                    r["p"] += 1
    filas = sorted(t.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["gc"]), -r["gf"], r["team"]))
    return [{"pos": i, **r, "df": r["gf"] - r["gc"]} for i, r in enumerate(filas, 1)]


def _grupo_raw(fab, categoria, nombre, isla, n, copa, con_sin_id):
    """Un grupo del raw de fetch_fiflp_islas, con sus actas aparte: (entrada, {código del acta: acta})."""
    equipos = fab.equipos_de(isla, EQUIPOS_POR_GRUPO, con_sin_id) + [fab.nuevo_club(categoria)]
    fab.grupo += 1
    if copa:
        # Cuartos (jornada 1) y semifinales (jornada 2) jugados; la final, sin jugar.
        rondas = [[(equipos[i], equipos[7 - i]) for i in range(4)]]
    else:
        rondas = _calendario(equipos)
    jornadas, actas = [], {}
    for k, ronda in enumerate(rondas):
        jugada = k < (1 if copa else JORNADAS_JUGADAS)
        partidos = []
        for local, visitante in ronda:
            m = {"home": local, "away": visitante, "hs": None, "as": None, "date": _sabado(fab.anio, k), "time": "10:00",
                 "venue": "CAMPO DE PRUEBA", "referee": ""}
            if jugada:
                m["hs"], m["as"] = fab.marcador(copa)
                fab.acta += 1
                m["fiflp_acta"] = fab.acta
                actas[fab.acta] = _acta(fab, categoria, nombre, n, k + 1, m)
            partidos.append(m)
        jornadas.append({"num": str(k + 1), "date": _sabado(fab.anio, k), "matches": partidos})
    if copa:
        # Las semifinales: los ganadores de los cuartos, ya jugadas.
        ganadores = [m["home"] if m["hs"] > m["as"] else m["away"] for m in jornadas[0]["matches"]]
        partidos = []
        for local, visitante in ((ganadores[0], ganadores[1]), (ganadores[2], ganadores[3])):
            m = {"home": local, "away": visitante, "date": _sabado(fab.anio, 1), "time": "10:00", "venue": "CAMPO DE PRUEBA",
                 "referee": ""}
            m["hs"], m["as"] = fab.marcador(True)
            fab.acta += 1
            m["fiflp_acta"] = fab.acta
            actas[fab.acta] = _acta(fab, categoria, nombre, n, 2, m)
            partidos.append(m)
        jornadas.append({"num": "2", "date": _sabado(fab.anio, 1), "matches": partidos})
    entrada = {"competition_id": str(fab.comp), "competition_name": nombre, "cat": categoria.lower(), "island": isla,
               "phase": nombre, "group_id": str(fab.grupo), "group_name": f"GRUPO {n}",
               "standings": [] if copa else _clasificacion(equipos, jornadas), "jornadas": jornadas}
    return entrada, actas


def _acta(fab, categoria, competicion, n, jornada, m):
    """El acta aplanada (fiflp_acta.parse_flat_acta) de un partido jugado: las dos alineaciones (11 titulares y
    7 suplentes), un gol por cada uno del marcador, de un titular, y una tarjeta."""
    lineups, events = {}, []
    for lado, equipo, goles in (("home", m["home"], m["hs"]), ("away", m["away"], m["as"])):
        plantilla = fab.plantilla(categoria, equipo)
        lineups[lado] = [{"dorsal": i + 1, "name": j["name"], "role": "starter" if i < TITULARES else "sub",
                          "fiflp_id": j["fiflp_id"]} for i, j in enumerate(plantilla)]
        for g in range(goles):
            autor = plantilla[fab.rnd.randrange(1, TITULARES)]
            events.append({"kind": "goal", "side": lado, "player_name": autor["name"], "minute": 5 + 7 * g,
                           "goal_type": "normal"})
    events.append({"kind": "yellow", "side": "away", "player_name": lineups["away"][3]["name"], "minute": 40})
    temporada = f"{fab.anio}/{fab.anio + 1}"        # como la cabecera de la federación: «2026/2027»
    header = {"season": temporada, "jornada": str(jornada), "date": m["date"],
              "competition": f"{competicion} (GRUPO {n})", "home_team": m["home"], "away_team": m["away"],
              "home_score": m["hs"], "away_score": m["as"]}
    return {"header": header, "lineups": lineups, "events": events, "staff": {}, "consistent": True}


def _activar(conn, raw, season, taken, log):
    """La activación de activar_auto.activar, por competición: manifiesto → verificación → alta. Devuelve los
    grupos del manifiesto activados."""
    import fiflp_manifest as M
    from activar_auto import season_code
    from activate_season import add_groups, raw_team_names, validate_manifest, verify_sources
    activados = []
    for comp in sorted({str(g["competition_id"]) for g in raw}):
        suyos = {(comp, str(g["group_id"])) for g in raw if str(g["competition_id"]) == comp}
        manifest = {"season": season, "groups": M.build(raw, season, season_code(season), only=suyos, taken=taken)}
        validate_manifest(manifest, season, adding=True)
        names = raw_team_names(raw, conn, season)
        evidence = verify_sources(manifest, fiflp_raw=raw, names=names)
        add_groups(conn, manifest, evidence)
        taken |= {g["id"] for g in manifest["groups"]}
        activados += manifest["groups"]
        log(f"  activados {', '.join(g['id'] for g in manifest['groups'])}")
    return activados


def _pasada(conn, sid, grupo, entrada, actas, log):
    """Lo que escribe la pasada del carril de un grupo: jornadas y clasificación, goleadores, actas y fichas de
    los equipos nuevos. Devuelve (partidos jugados, actas importadas)."""
    import update_fiflp as U
    from import_fiflp_cups_2324 import clean_team_name
    gid = conn.execute("SELECT id FROM groups WHERE season_id=? AND code=?", (sid, grupo["id"])).fetchone()[0]
    # Como las lee scrape_group: por jornada, con la fecha en ISO.
    rondas = {f"Jornada {j['num']}": [{**m, "date": U._iso(m.get("date"))} for m in j["matches"]]
              for j in entrada["jornadas"]}
    estado, mensaje = U.update_group(conn, gid, grupo["id"], entrada["standings"], rondas, log=lambda *a: None)
    if estado != "ok":
        raise RuntimeError(f"{grupo['id']}: la pasada no escribe el grupo ({mensaje})")
    conn.execute("DELETE FROM fiflp_full_pending WHERE group_id=?", (gid,))
    # Goleadores: los de la federación, de las actas.
    goles = {}
    for acta in actas.values():
        for ev in acta["events"]:
            if ev["kind"] == "goal":
                equipo = acta["header"]["home_team" if ev["side"] == "home" else "away_team"]
                goles[(ev["player_name"], equipo)] = goles.get((ev["player_name"], equipo), 0) + 1
    filas = [[nombre, equipo, 1, g, 0] for (nombre, equipo), g in sorted(goles.items())]
    U.write_scorers(conn, gid, filas)
    # Las actas, por el código de su partido (cod_acta = fiflp_acta), como _read_actas.
    leidas = 0
    for codigo, acta in sorted(actas.items()):
        fila = conn.execute("SELECT id FROM matches WHERE group_id=? AND fiflp_acta=?", (gid, codigo)).fetchone()
        if not fila:
            raise RuntimeError(f"{grupo['id']}: el partido del acta {codigo} no está")
        if not U.apply_acta(conn, fila[0], codigo, acta, log=lambda *a: None):
            raise RuntimeError(f"{grupo['id']}: el acta {codigo} no se importa")
        leidas += 1
    # Las fichas de la temporada de los equipos que no la tienen (update_directorio).
    equipos = {clean_team_name(m[s]) for j in entrada["jornadas"] for m in j["matches"] for s in ("home", "away")}
    nombres = U.name_map(sorted(equipos), [r[1] for r in U.stored_standings(conn, gid)] or
                         [n for (n,) in conn.execute(
                             "SELECT DISTINCT t.name FROM matches m JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id) "
                             "WHERE m.group_id=?", (gid,))])
    for i, fed in enumerate(sorted(equipos)):
        nombre = nombres.get(fed)
        fila = conn.execute("SELECT id FROM teams WHERE name=?", (nombre,)).fetchone() if nombre else None
        if not fila or conn.execute("SELECT 1 FROM team_seasons WHERE team_id=? AND season_id=?",
                                    (fila[0], sid)).fetchone():
            continue
        conn.execute("""INSERT OR REPLACE INTO team_seasons(team_id, season_id, fiflp_code, fiflp_name, crest_url, shirt,
                            shorts, socks, venue_code, venue_name, surface) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (fila[0], sid, 98_000_000 + gid * 100 + i, fed, None, "Roja", "Blanco", "Rojas", None,
                      "CAMPO DE PRUEBA", "Artificial"))
    conn.commit()
    jugados = conn.execute("SELECT count(*) FROM matches WHERE group_id=? AND home_score IS NOT NULL", (gid,)).fetchone()[0]
    return jugados, leidas


def poblar(conn, categorias=("INFANTIL", "CADETE", "JUVENIL"), temporada=None, islas=False, log=print):
    """Ver el docstring del módulo. `conn`: una copia de la base (nunca la del árbol). Sin `temporada`, la en curso
    de la base; con ella, tiene que ser la en curso (el bot solo activa y lee la en curso)."""
    from migrate_identidad import asegurar_esquema
    asegurar_esquema(conn)
    fila = conn.execute("SELECT id, name, start_year FROM seasons WHERE is_current=1").fetchall()
    if len(fila) != 1:
        raise ValueError("la base no tiene una sola temporada en curso")
    if temporada is not None and fila[0][1] != temporada:
        raise ValueError(f"la temporada en curso de la base no es {temporada}")
    sid, season, anio = fila[0]
    fab = _Fabrica(conn, sid, anio)
    taken = {c for (c,) in conn.execute("SELECT code FROM groups WHERE season_id=?", (sid,))}
    tandas = [(cat, COMPETICIONES[cat]) for cat in categorias]
    if islas:
        tandas.append(("ALEVIN", ISLAS))
    out = {"grupos": [], "partidos": 0, "actas": 0}
    for categoria, comps in tandas:
        with _alevin_de_islas(categoria == "ALEVIN"):
            raw, actas = [], {}
            primero = True
            for nombre, isla, grupos, copa in comps:
                fab.comp += 1
                # Los grupos, detrás de los que la temporada ya tenga con ese prefijo.
                import fiflp_manifest
                prefijo = fiflp_manifest.meta(nombre)[0]
                hay = [int(c[len(prefijo):]) for c in taken
                       if c.startswith(prefijo) and c[len(prefijo):].isdigit()]
                for n in range(max(hay, default=0) + 1, max(hay, default=0) + grupos + 1):
                    entrada, suyas = _grupo_raw(fab, categoria, nombre, isla, n, copa,
                                                con_sin_id=categoria if primero and isla == "grancanaria" else None)
                    primero = False
                    raw.append(entrada)
                    actas[(entrada["competition_id"], entrada["group_id"])] = suyas
            log(f"{categoria}: {len(raw)} grupos")
            activados = _activar(conn, raw, season, taken, log)
            por_url = {(str(e["competition_id"]), str(e["group_id"])): e for e in raw}
            from activate_season import fiflp_ids
            for grupo in activados:
                clave = fiflp_ids(grupo["url"])
                jugados, leidas = _pasada(conn, sid, grupo, por_url[clave], actas[clave], log)
                out["grupos"].append(grupo["id"])
                out["partidos"] += jugados
                out["actas"] += leidas
    out["jugadores_reutilizados"] = len(fab.reutilizados)
    out["sin_id_reutilizados"] = len(fab.sin_id_usados)
    # Los equipos de alevín y prebenjamín con sin id de la temporada con los que montar ese caso: recién empezada una
    # temporada, ninguno.
    out["sin_id_disponibles"] = fab.sin_id_disponibles
    out["sin_id_en_fila_ajena"] = sin_id_en_fila_ajena(conn)
    return out


def sin_id_en_fila_ajena(conn):
    """Cuántas identidades sin id tienen apariciones en una de las mayores (infantil, cadete, juvenil) y también
    en otra categoría: un cadete sin id en la fila de un prebenjamín sin id del mismo nombre, club y temporada
    (migrate_identidad.categoria_sin_id lo impide). Tiene que ser 0."""
    mayores = ",".join("?" * len(MAYORES))
    return conn.execute(
        f"""SELECT count(*) FROM (SELECT a.player_id FROM appearances a JOIN players p ON p.id = a.player_id
              JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
              JOIN categories c ON c.id = g.category_id
             WHERE p.fiflp_id IS NULL AND p.team_id IS NOT NULL
             GROUP BY a.player_id
            HAVING sum(upper(c.name) IN ({mayores})) > 0 AND sum(upper(c.name) NOT IN ({mayores})) > 0)""",
        MAYORES + MAYORES).fetchone()[0]


# ── Las bases de las pruebas sobre la base real (fixture de sesión bases_reales, conftest.py) ─────────────

def fin_de_pasada(path, en_web=None):
    """Lo que hace el final de una pasada con la base de `path`: las fichas (migrate_identidad.resolver_fichas) y
    los enlaces de la liga de escuelas (enlace_mygol.guardar_enlaces). Con `en_web` («antes», «seis»), con ese
    categorias.EN_WEB (con_en_web): el resolvedor rehace las fichas desde cero, así que lo que dejó la pasada que
    escribió la base no cuenta."""
    import enlace_mygol
    import migrate_identidad
    from db import get_connection
    conn = get_connection(path)
    try:
        with con_en_web(en_web):
            migrate_identidad.resolver_fichas(conn, log=lambda *a: None)
            enlace_mygol.guardar_enlaces(conn, registro=lambda *a: None)
    finally:
        conn.close()


def leida(resuelta, path, categorias=MAYORES, islas=False, en_web=None):
    """Una copia de `resuelta` en `path` con lo de poblar (esas categorías y, con `islas`, el alevín de Lanzarote)
    activado y leído y el final de una pasada (con `en_web`, fin_de_pasada): lo que devolvió poblar."""
    import shutil
    from db import get_connection
    shutil.copyfile(resuelta, path)
    conn = get_connection(path)
    try:
        hecho = poblar(conn, categorias=categorias, islas=islas, log=lambda *a: None)
    finally:
        conn.close()
    fin_de_pasada(path, en_web)
    return hecho


def bases_reales(origen, carpeta):
    """Copias de la base real `origen`, en `carpeta`, tras el final de una pasada con el EN_WEB de antes del paso
    E2-D2 (fin_de_pasada con «antes», valga lo que valga categorias.py): «resuelta», tal cual; «mayores», la misma
    con infantil, cadete y juvenil activados y leídos (poblar); e «islas», la misma con solo el alevín de Lanzarote
    (poblar con islas). Y «mayores_seis»: la de «mayores» (poblar es siempre igual para la misma base) con el final de
    una pasada con el EN_WEB del paso E2-D2 (las seis): la que dejará el bot cuando la web enseñe las mayores. Con
    «resuelta» e «islas» no hace falta la de seis: sin grupos de las mayores, las fichas son las mismas con los dos.
    Las usan test_vista_web.test_generador_igual_con_y_sin_mayores (lo que genera la web con una y con otra), las
    pruebas de quitar_categoria (test_activacion_categorias.py) y test_fichas_ampliadas.py: una vez por sesión, y
    las tres últimas a la vez (paralelo.en_paralelo), porque las fichas de la base real tardan ~10 s cada vez y la
    puerta de pruebas del bot pasa la suite entera en cada pasada. Quien las usa no las cambia: trabaja sobre su
    propia copia. {'resuelta', 'mayores', 'mayores_seis', 'islas': rutas; 'hecho', 'hecho_islas': lo que devolvió
    poblar}."""
    import sqlite3
    from paralelo import en_paralelo
    carpeta = Path(carpeta)
    resuelta, mayores, islas = carpeta / "resuelta.db", carpeta / "mayores.db", carpeta / "islas.db"
    mayores_seis = carpeta / "mayores_seis.db"
    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    dst = sqlite3.connect(str(resuelta))
    src.backup(dst)
    dst.close()
    src.close()
    fin_de_pasada(resuelta, "antes")
    hecho, hecho_islas, hecho_seis = en_paralelo((leida, (resuelta, mayores, MAYORES, False, "antes")),
                                                 (leida, (resuelta, islas, (), True, "antes")),
                                                 (leida, (resuelta, mayores_seis, MAYORES, False, "seis")))
    if hecho_seis != hecho:
        raise AssertionError("poblar no ha dado lo mismo dos veces sobre la misma base")
    return {"resuelta": resuelta, "mayores": mayores, "mayores_seis": mayores_seis, "islas": islas, "hecho": hecho,
            "hecho_islas": hecho_islas}
