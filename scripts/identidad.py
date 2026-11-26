"""identidad.py — Quién es cada niño: el resolvedor de fichas. Puro: sin base ni red.

Una fila de `players` es una IDENTIDAD DE ACTA: lo que el acta dice con certeza (un id de la federación,
o un nombre sin id en un equipo y una temporada). Una FICHA es el niño: un conjunto de identidades con
una principal. `resolver` decide las fichas desde cero, siempre igual para las mismas identidades (no
depende del orden de entrada ni de lo que se resolvió antes), con las reglas de docs/identidad.md:

    U0  mismo nombre con coma, mismo equipo y temporada (el id de un solo uso)    union_por 'equipo'
        y, sin coma y con id, la de 1 aparición con la única asentada del cubo
    U0  de club: mismo nombre con coma, mismo club y temporada, ≤ 1 ficha con id   union_por 'club'
    U1  mismo nombre, mismo club, temporadas seguidas, no las dos con id         union_por 'club'
    U2  sin id y nombre completo, con la única otra ficha de ese nombre          union_por 'nombre'

y ninguna unión entre conjuntos incompatibles (edad imposible o dos clubes a la vez en la misma
categoría) ni entre dos que salieron en la misma alineación (`juntas`). Ante la duda, dos fichas mejor que una
mezclada: cada «Decisión» de docs/identidad.md es la lectura de una regla que une menos. Una sola excepción a «la
duda»: lo que solo está en el cubo de una regla por sus partidos de infantil, cadete o juvenil y no cabe por la edad
con nada de prebenjamín, benjamín o alevín de ese cubo no puede ser ninguno de ellos, así que no es una duda para
ellos: cada regla se aplica por separado al grupo de hoy del cubo y a cada grupo de lo demás que cabe entre sí
(por_edad, dentro de resolver; docs/identidad.md, «Las categorías nuevas no crean dudas imposibles»). Sin vistas de
esas categorías, el cubo es un solo grupo y todo es como antes.

`clave_publica` y `trozo` tienen su gemelo en JavaScript (la web): la tabla de
scripts/tests/test_identidad.py (TABLA_CLAVES) fija lo que deben dar los dos.
"""
import hashlib
import os
import re
import sys
import unicodedata
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_js import normalize_for_teams_mapping  # noqa: E402  (la clave de club C1, gemela de la web)

NIVEL = {"PREBENJAMIN": 1, "BENJAMIN": 2, "ALEVIN": 3, "INFANTIL": 4, "CADETE": 5, "JUVENIL": 6}
# Años de nacimiento posibles de quien juega la temporada que empieza el año Y: [Y - a, Y - b]. Desde
# benjamín, la ventana natural de la categoría (nacimiento.VENTANA) y dos años más por abajo: quien juega con
# los mayores. Infantil, cadete y juvenil (parte E) solo cuentan cuando la web los enseña: el resolvedor lee
# las apariciones de categorias.EN_WEB (migrate_identidad._vistas).
_EDAD = {1: (7, 5), 2: (9, 6), 3: (11, 8), 4: (13, 10), 5: (15, 12), 6: (18, 14)}
# Los niveles de infantil, cadete y juvenil (parte E: la web los enseña desde el paso E2-D2). Un niño de
# prebenjamín, benjamín o alevín tiene hoy su ficha; cuando entran los partidos de estas categorías, sus homónimos
# de cadete del mismo club (otros niños, seis años mayores) caerían en los cubos de las reglas y, como «duda»,
# desharían uniones de hoy (U1 de uno a uno, U2 de candidata única, la U0 de club con un id de más, la U0 de los
# cortos con otra asentada). Por eso cada regla se aplica por separado a los grupos del cubo que cabe por la edad
# (resolver, por_edad): lo de las nuevas que no cabe con nada de hoy va en su propio grupo, sean cuantos sean y
# quepan o no entre sí. Solo estos niveles: entre los de siempre, la regla es la de antes (un solo grupo, quepan o
# no entre sí: une menos), y sin vistas de estos niveles el resolvedor recorre los mismos cubos con los mismos
# miembros que antes: da exactamente lo mismo.
NIVELES_NUEVOS = frozenset({4, 5, 6})
UNIONES = ("equipo", "club", "nombre")
# Lo que dio la medida de los nombres sin coma (scripts/medir_identidad.py, docs/identidad.md): pares de
# uno a uno, 100 % ≥ 95 %. Los de coma (completos o de un apellido) se unen en el club siempre.
UNIR_CORTOS_EN_CLUB = True
# U0 de club: medida entre jugadores con id, mismo nombre, club y temporada en equipos distintos
# (scripts/medir_identidad.py): completos 99,4 % y un apellido 100 %, los dos ≥ 95 %.
U0_CLUB_COMPLETOS = True
U0_CLUB_UN_APELLIDO = True

# 'NOMBRE#id' (homónimo con id) o 'NOMBRE#2' (el segundo del mismo nombre en una alineación sin ids).
_SUFIJO = re.compile(r"#\d+$")
# Siglas que normalize_for_teams_mapping no quita y la web sí (src/myteam.js, SIGLAS).
_SIGLAS = {"rc", "us", "cda", "cef"}
_LETRA_FILIAL = re.compile(r"^[a-e]$")
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"
_CIFRAS_SHA1 = 31          # cifras en base 36 de un SHA-1 (36**31 > 2**160): el relleno con ceros
_INF = 10 ** 9


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------

def normalizar(nombre: str) -> str:
    """Sin tildes, mayúsculas, espacios simples: la de import_fiflp_actas._norm_player (una prueba fija
    que dan lo mismo), copiada para no traer el importador a un módulo puro."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def nombre_completo(nombre_normalizado: str) -> bool:
    """«APELLIDO APELLIDO, NOMBRE»: coma, dos o más palabras antes y al menos una después. El sufijo
    '#…' (id u ordinal) no es parte del nombre."""
    antes, coma, despues = _SUFIJO.sub("", nombre_normalizado or "").partition(",")
    return bool(coma) and len(antes.split()) >= 2 and len(despues.split()) >= 1


def nombre_con_coma(nombre_normalizado: str) -> bool:
    """«APELLIDO(S), NOMBRE»: coma, al menos una palabra antes y una después (U0 y U1; U2 pide
    nombre_completo, dos apellidos). El sufijo '#…' no es parte del nombre."""
    antes, coma, despues = _SUFIJO.sub("", nombre_normalizado or "").partition(",")
    return bool(coma) and len(antes.split()) >= 1 and len(despues.split()) >= 1


def club(nombre_equipo: str) -> str:
    """El club de un equipo: su nombre sin la letra de filial. Es baseKey de src/myteam.js (la clave
    con la que la web agrupa los equipos de un club, sin escudos ni alias), sobre la misma
    normalización de club que ya tiene Python (generate_js.normalize_for_teams_mapping)."""
    tokens = [t for t in normalize_for_teams_mapping(nombre_equipo).split(" ") if t and t not in _SIGLAS]
    if len(tokens) > 1 and _LETRA_FILIAL.match(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def intervalo(anio: int, nivel: int) -> tuple[int, int]:
    """Años de nacimiento posibles en la temporada que empieza `anio` (1 prebenjamín, 2 benjamín,
    3 alevín, 4 infantil, 5 cadete, 6 juvenil). Medido sobre los 15.266 jugadores con id de los originales
    (prebenjamín, benjamín y alevín): ninguno se sale. Los de infantil, cadete y juvenil siguen la misma regla
    que benjamín y alevín (la ventana natural y dos años más por abajo), sin medir todavía: no hay actas."""
    a, b = _EDAD[nivel]
    return anio - a, anio - b


def clave_publica(fiflp_id: int | None, norm: str, equipo: str, anio: int, categoria: str | None = None) -> str:
    """El id de la federación en decimal o, sin id, 'n' + las 9 primeras cifras en base 36 (minúsculas,
    rellenas con ceros hasta 31) del SHA-1 de '<nombre normalizado>|<equipo>|<año de inicio>' en UTF-8.
    `norm` lleva el ordinal si lo tiene ('X#2'): si no, los dos «X» de una alineación tendrían la misma.
    `categoria`: la de la identidad sin id de infantil, cadete o juvenil (migrate_identidad.categoria_de), que
    va detrás ('…|<año>|CADETE'): un cadete sin id es otra identidad que el prebenjamín sin id del mismo nombre,
    club y temporada, y no puede tener su clave. Sin ella (prebenjamín, benjamín, alevín), la de siempre."""
    if fiflp_id is not None:
        return str(int(fiflp_id))
    texto = f"{norm}|{equipo}|{anio}" + (f"|{categoria}" if categoria else "")
    n = int(hashlib.sha1(texto.encode("utf-8")).hexdigest(), 16)
    cifras = []
    while n:
        n, resto = divmod(n, 36)
        cifras.append(_BASE36[resto])
    return "n" + "".join(reversed(cifras)).rjust(_CIFRAS_SHA1, "0")[:9]


def trozo(clave: str, n: int = 64) -> int:
    """El fichero de la web en el que va una clave: numérica, su valor % n; 'n…', el resto en base 36 % n
    (9 cifras caben en un número de JavaScript sin perder nada: 36**9 < 2**53). Por defecto, los 64 de
    data-jugadores (generate_js.JUGADORES_SHARDS, src/state.js): sin n, el mismo fichero que la web."""
    return int(clave[1:], 36) % n if clave.startswith("n") else int(clave) % n


@dataclass(frozen=True)
class Identidad:
    """Una fila de players con lo que hace falta para decidir.

    norm: el nombre normalizado, con '#<fiflp_id>' si lo lleva o con el ordinal de la alineación ('X#2').
    vistas: ((anio, nivel, equipo, primera_fecha, ultima_fecha, apariciones), …), una por temporada,
    categoría y equipo; fechas ISO ('2025-10-04'), None si no se saben."""
    id: int
    norm: str
    fiflp_id: int | None
    vistas: tuple = ()


# ---------------------------------------------------------------------------
# Compatibilidad
# ---------------------------------------------------------------------------

def _se_cruzan(a_ini, a_fin, b_ini, b_fin) -> bool:
    """¿Se cruzan dos rangos de fechas? Sin fecha no se puede descartar: se cruzan."""
    if None in (a_ini, a_fin, b_ini, b_fin):
        return True
    return a_ini <= b_fin and b_ini <= a_fin


class _Ficha:
    """Lo que se mira de un conjunto de identidades para saber si cabe con otro. veta: las identidades que
    salieron en la misma alineación que alguna de las suyas (otro niño, seguro). sola: separada a mano
    (scripts/identidad_separadas.json), no cabe con ninguna."""
    __slots__ = ("miembros", "con_id", "ordinal", "lo", "hi", "tramos", "solape", "veta", "sola")

    def __init__(self, miembros, vistas, con_id=False, ordinal=False, veta=(), sola=False):
        self.miembros = list(miembros)
        self.con_id, self.ordinal = con_id, ordinal
        self.veta = set(veta)
        self.sola = sola
        self.lo, self.hi = -_INF, _INF
        self.tramos = {}            # (anio, nivel) -> [(club, primera, ultima)]
        self.solape = False
        for anio, nivel, equipo, ini, fin, _ in vistas:
            if nivel in _EDAD:
                lo, hi = intervalo(anio, nivel)
                self.lo, self.hi = max(self.lo, lo), min(self.hi, hi)
            tramo = (club(equipo or ""), ini, fin)
            otros = self.tramos.setdefault((anio, nivel), [])
            if any(c != tramo[0] and _se_cruzan(i, f, ini, fin) for c, i, f in otros):
                self.solape = True
            otros.append(tramo)

    def cabe_con(self, otra) -> bool:
        if self.sola or otra.sola or self.solape or otra.solape or max(self.lo, otra.lo) > min(self.hi, otra.hi):
            return False
        if (self.veta and not self.veta.isdisjoint(otra.miembros)) or \
                (otra.veta and not otra.veta.isdisjoint(self.miembros)):
            return False
        menor, mayor = sorted((self.tramos, otra.tramos), key=len)
        for clave, tramos in menor.items():
            for c, i, f in mayor.get(clave, ()):
                if any(c != c2 and _se_cruzan(i, f, i2, f2) for c2, i2, f2 in tramos):
                    return False
        return True

    def absorbe(self, otra):
        self.miembros += otra.miembros
        self.con_id = self.con_id or otra.con_id
        self.ordinal = self.ordinal or otra.ordinal
        self.lo, self.hi = max(self.lo, otra.lo), min(self.hi, otra.hi)
        self.veta |= otra.veta
        for clave, tramos in otra.tramos.items():
            self.tramos.setdefault(clave, []).extend(tramos)


def compatibles(*grupos_de_vistas) -> bool:
    """¿Pueden ser del mismo niño todas estas vistas? (a) los intervalos de edad de todas se cruzan y
    (b) no hay solape imposible: misma temporada y categoría, dos clubes, fechas que se cruzan."""
    todas = [vista for grupo in grupos_de_vistas for vista in grupo]
    ficha = _Ficha((), todas)
    return not ficha.solape and ficha.lo <= ficha.hi


# ---------------------------------------------------------------------------
# El resolvedor
# ---------------------------------------------------------------------------

def _nombre(i: Identidad) -> str:
    """El nombre con el que se compara: sin '#<id>' en las que tienen id; con el ordinal en las que no."""
    return _SUFIJO.sub("", i.norm) if i.fiflp_id is not None else i.norm


def _base(nombre: str) -> str:
    return _SUFIJO.sub("", nombre)


def _fuera(i: Identidad) -> bool:
    """La fila «sin nombre publicado» ('#…') y un nombre vacío no son de nadie: no se unen nunca."""
    return not _base(i.norm).strip() or i.norm.startswith("#")


def _apariciones(i: Identidad) -> int:
    return sum(vista[5] or 0 for vista in i.vistas)


def _orden_principal(i: Identidad):
    """Antes la que sería principal: con id, más apariciones, id de la federación menor; sin id, la
    temporada más antigua, más apariciones, id menor."""
    if i.fiflp_id is not None:
        return (0, -_apariciones(i), i.fiflp_id, 0, i.id)
    primera = min((vista[0] for vista in i.vistas), default=_INF)
    return (1, 0, 0, primera, -_apariciones(i), i.id)


def _cubos_cortos(identidades):
    """{(nombre, equipo, anio): (asentadas, de un solo uso)} de las identidades con id y nombre corto; de
    un solo uso es la que tiene exactamente 1 aparición en total (sumando todas sus vistas)."""
    cubos = {}
    for i in sorted(identidades, key=lambda i: i.id):
        nombre = _nombre(i)
        if i.fiflp_id is None or nombre_con_coma(nombre) or _fuera(i):
            continue
        uso_unico = _apariciones(i) == 1
        for clave in sorted({(nombre, equipo or "", anio) for anio, _, equipo, *_ in i.vistas}):
            cubos.setdefault(clave, ([], []))[1 if uso_unico else 0].append(i)
    return cubos


def resumen_u0_cortos(identidades) -> dict[str, int]:
    """Cuántos cubos de U0 de nombres cortos tienen algo que unir y qué pasa con ellos: 'una asentada'
    (se unen), 'dos o más asentadas' o 'ninguna asentada' (dos o más de un solo uso; no se une nada)."""
    out = {"una asentada": 0, "dos o más asentadas": 0, "ninguna asentada": 0}
    for asentadas, sueltas in _cubos_cortos(identidades).values():
        if len(asentadas) == 1 and sueltas:
            out["una asentada"] += 1
        elif len(asentadas) >= 2 and sueltas:
            out["dos o más asentadas"] += 1
        elif not asentadas and len(sueltas) >= 2:
            out["ninguna asentada"] += 1
    return out


def resolver(identidades: list[Identidad], unir_cortos_en_club: bool,
             juntas=(), separadas=()) -> dict[int, tuple[int, str | None]]:
    """{id de identidad: (id de la principal de su ficha, union_por)}; la principal se apunta a sí misma
    con None. union_por es la regla de la unión que juntó a esa identidad con la principal: deshacerla
    es apartarla de la ficha (ficha_id a NULL).

    juntas: pares (id, id) de identidades que salieron en un mismo partido con el mismo equipo: son dos
    niños, así que dos fichas con una de cada par no se unen por ninguna regla, ni directa ni a través de
    otra (los pares con ids que no están se ignoran).

    separadas: ids de identidades que no se unen a nadie (su ficha son ellas solas): las que se apartaron a
    mano de una unión. Siguen contando como otra ficha de su nombre (U1 de uno a uno, U2 candidata única):
    así apartar una no hace que se una lo que antes no se unía."""
    por_id = {}
    for i in identidades:
        if i.id in por_id:
            raise ValueError(f"identidad repetida: {i.id}")
        por_id[i.id] = i
    ids = sorted(por_id)
    veta = {}
    for a, b in juntas:
        if a in por_id and b in por_id and a != b:
            veta.setdefault(a, set()).add(b)
            veta.setdefault(b, set()).add(a)
    padre = {k: k for k in ids}
    fichas = {k: _Ficha([k], por_id[k].vistas, con_id=por_id[k].fiflp_id is not None,
                        ordinal=por_id[k].fiflp_id is None and bool(_SUFIJO.search(por_id[k].norm)),
                        veta=veta.get(k, ()), sola=k in separadas)
              for k in ids}
    uniones = []            # (regla, a, b) en el orden en que se hicieron

    def raiz(k):
        while padre[k] != k:
            padre[k] = padre[padre[k]]
            k = padre[k]
        return k

    def edad_cabe(a, b) -> bool:
        """¿Caben por la edad las fichas de las identidades `a` y `b` (sus intervalos se cruzan)?"""
        fa, fb = fichas[raiz(a)], fichas[raiz(b)]
        return max(fa.lo, fb.lo) <= min(fa.hi, fb.hi)

    def cabe_edad(a, b) -> bool:
        """¿Pueden ser el mismo niño por la edad las identidades o raíces `a` y `b`? (la misma ficha, o dos cuyos
        intervalos se cruzan)"""
        return raiz(a) == raiz(b) or edad_cabe(a, b)

    def por_edad(cubo, cabe=cabe_edad):
        """Los grupos del cubo de una regla en los que se aplica la regla, cada uno por separado: [(miembros,
        bloqueadas)]. `cubo`: {identidad o raíz: es de hoy}; de hoy es lo que está en el cubo por alguna vista de
        prebenjamín, benjamín o alevín (o de categoría desconocida), y lo demás es de las nuevas (está solo por
        vistas de NIVELES_NUEVOS). `cabe(x, y)`: ¿pueden ser el mismo niño? (en U1, solo entre los dos años).

        Sin nada de las nuevas (siempre, con el EN_WEB de hoy), un solo grupo: el cubo entero, en su orden y sin
        bloqueadas, y la regla hace lo de siempre. Con algo de las nuevas:
          - el grupo de hoy: todo lo de hoy (quepa o no entre sí, como siempre) y lo de las nuevas que cabe por la edad
            con algo de hoy (la duda de verdad: un infantil homónimo del alevín del cubo);
          - un grupo por cada conjunto de lo demás que cabe entre sí (sus componentes por `cabe`): no puede ser nadie
            de hoy, así que no le estorba a lo de hoy ni lo de hoy le estorba a él, y entre ellos, la regla de siempre
            (dos cadetes homónimos del club son la duda de siempre);
          - lo de las nuevas del grupo de hoy que cabe también con algo de un grupo de los demás (un infantil entre el
            alevín y el cadete) está en los dos y cuenta en los dos, pero no se une en ninguno (bloqueadas): puede ser
            el de hoy o el otro. Nunca está en el grupo de hoy lo que no cabe con nada de hoy."""
        miembros = list(cubo)
        if all(cubo.values()):
            return [(miembros, frozenset())]
        hoy = [m for m in miembros if cubo[m]]
        del_grupo_de_hoy = {m for m in miembros if cubo[m] or any(cabe(m, h) for h in hoy)}
        demas = [m for m in miembros if m not in del_grupo_de_hoy]
        dos_grupos = {m for m in del_grupo_de_hoy if not cubo[m] and any(cabe(m, d) for d in demas)}
        grupos = [([m for m in miembros if m in del_grupo_de_hoy], frozenset(dos_grupos))] if hoy else []
        while demas:
            componente, frontera = {demas[0]}, [demas.pop(0)]
            while frontera:
                x = frontera.pop()
                juntos = [y for y in demas if cabe(x, y)]
                demas = [y for y in demas if y not in juntos]
                componente.update(juntos)
                frontera += juntos
            suyas = frozenset(m for m in dos_grupos if any(cabe(m, c) for c in componente))
            grupos.append(([m for m in miembros if m in componente or m in suyas], suyas))
        return grupos

    def unir(a, b, regla) -> bool:
        ra, rb = raiz(a), raiz(b)
        if ra == rb or not fichas[ra].cabe_con(fichas[rb]):
            return False
        if len(fichas[ra].miembros) < len(fichas[rb].miembros):
            ra, rb = rb, ra
        fichas[ra].absorbe(fichas.pop(rb))
        padre[rb] = ra
        uniones.append((regla, a, b))
        return True

    validas = [por_id[k] for k in ids if not _fuera(por_id[k])]

    # U0: el mismo nombre con coma (uno o más apellidos) en el mismo equipo y temporada. Si en ese equipo y
    # temporada hay dos sin id con ese nombre (el ordinal), no se sabe cuál es cuál: solo se juntan las que
    # tienen id.
    cubos = {}
    for i in validas:
        nombre = _nombre(i)
        if nombre_con_coma(nombre):
            for anio, nivel, equipo, *_ in i.vistas:
                cubo = cubos.setdefault((_base(nombre), equipo or "", anio), {})
                cubo[i.id] = cubo.get(i.id, False) or nivel not in NIVELES_NUEVOS
    for clave in sorted(cubos):
        for grupo, bloqueadas in por_edad(cubos[clave]):
            miembros = [por_id[k] for k in grupo]
            if any(fichas[raiz(m.id)].ordinal for m in miembros):
                miembros = [m for m in miembros if m.fiflp_id is not None]
            semillas = []
            # Cada una, a la primera ficha del cubo con la que quepa; si no cabe con ninguna, empieza otra:
            # así dos fichas que quedan en el mismo cubo no caben juntas, ni ahora ni después.
            for m in sorted(miembros, key=_orden_principal):
                if m.id not in bloqueadas and not any(raiz(s) == raiz(m.id) or unir(s, m.id, "equipo")
                                                      for s in semillas):
                    semillas.append(m.id)

    # U0 de nombres sin coma: las de una sola aparición van a la única asentada de su cubo (con dos o más
    # asentadas, dos niños con ese nombre de pila en el equipo; con ninguna, nada a lo que ir).
    for clave, (asentadas, sueltas) in sorted(_cubos_cortos(validas).items()):
        _, equipo, anio = clave
        cubo = {m.id: any(v[0] == anio and (v[2] or "") == equipo and v[1] not in NIVELES_NUEVOS for v in m.vistas)
                for m in asentadas + sueltas}
        for grupo, bloqueadas in por_edad(cubo):
            grupo = set(grupo)
            suyas = [m for m in asentadas if m.id in grupo]
            if len(suyas) == 1 and suyas[0].id not in bloqueadas:
                for m in sueltas:
                    if m.id in grupo and m.id not in bloqueadas:
                        unir(suyas[0].id, m.id, "equipo")

    # U0 de club: mismo nombre con coma, mismo club y misma temporada en equipos distintos («X» y «X B»).
    # Con dos o más fichas con id en el cubo no se une nada (no se sabe de cuál es la que no lo tiene); una
    # ficha con ordinal lo bloquea. Cada ficha, a la primera del cubo con la que quepa, como en U0.
    cubos_club = {}
    for i in validas:
        base = _base(_nombre(i))
        if not nombre_con_coma(base) or not (U0_CLUB_COMPLETOS if nombre_completo(base) else U0_CLUB_UN_APELLIDO):
            continue
        for anio, nivel, equipo, *_ in i.vistas:
            c = club(equipo or "")
            if c:
                cubo = cubos_club.setdefault((base, c, anio), {})
                cubo[i.id] = cubo.get(i.id, False) or nivel not in NIVELES_NUEVOS
    for clave in sorted(cubos_club):
        cubo = {}
        for k, vieja in cubos_club[clave].items():
            cubo[raiz(k)] = cubo.get(raiz(k), False) or vieja
        for grupo, bloqueadas in por_edad(cubo):
            raices = set(grupo)
            if len(raices) < 2 or sum(fichas[r].con_id for r in raices) > 1 or \
                    any(fichas[r].ordinal for r in raices):
                continue
            semillas = []
            orden = sorted(raices - bloqueadas,
                           key=lambda r: min(_orden_principal(por_id[k]) for k in fichas[r].miembros))
            for m in orden:
                if not any(raiz(s) == raiz(m) or unir(s, m, "club") for s in semillas):
                    semillas.append(m)

    # U1: mismo nombre, mismo club, temporadas seguidas, entre dos fichas que no tienen id las dos (manda
    # el id). Solo de uno a uno: con dos fichas de ese nombre en el club en una de las dos temporadas (con
    # id o sin él) no se sabe cuál es. Y si los enlaces llevan de una ficha con id a otra con otro id
    # (con id → sin id → con id), la sin id puede ser de cualquiera de los dos: ese grupo no se une.
    lados = {}
    for i in validas:
        base = _base(_nombre(i))
        for anio, nivel, equipo, *_ in i.vistas:
            c = club(equipo or "")
            if c:
                lado = lados.setdefault((base, c, anio), {})
                lado[raiz(i.id)] = lado.get(raiz(i.id), False) or nivel not in NIVELES_NUEVOS
    enlaces = []
    for base, c, anio in sorted(lados):
        if not (nombre_con_coma(base) or unir_cortos_en_club):
            continue
        # El cubo, los dos años: (0, raíz) este y (1, raíz) el siguiente; la duda es entre los dos años.
        cubo = {(0, r): vieja for r, vieja in lados[(base, c, anio)].items()}
        cubo.update(((1, r), vieja) for r, vieja in lados.get((base, c, anio + 1), {}).items())
        for grupo, bloqueadas in por_edad(cubo, cabe=lambda x, y: x[0] != y[0] and cabe_edad(x[1], y[1])):
            aqui, despues = [r for lado, r in grupo if lado == 0], [r for lado, r in grupo if lado == 1]
            if len(aqui) == 1 and len(despues) == 1 and not bloqueadas:
                a, b = aqui[0], despues[0]
                fa, fb = fichas[a], fichas[b]
                if a != b and not (fa.con_id and fb.con_id) and not (fa.ordinal or fb.ordinal) and fa.cabe_con(fb):
                    enlaces.append((a, b))
    grupo_u1 = {}

    def raiz_u1(k):
        while grupo_u1.setdefault(k, k) != k:
            k = grupo_u1[k]
        return k

    for a, b in enlaces:
        grupo_u1[raiz_u1(a)] = raiz_u1(b)
    con_id_u1 = {}
    for r in {k for par in enlaces for k in par}:
        con_id_u1[raiz_u1(r)] = con_id_u1.get(raiz_u1(r), 0) + fichas[r].con_id
    for a, b in enlaces:
        if con_id_u1[raiz_u1(a)] <= 1:
            unir(a, b, "club")

    # U2: una ficha sin id y de nombre completo, con la única otra ficha de ese nombre.
    por_nombre = {}
    for i in validas:
        cubo = por_nombre.setdefault(_base(_nombre(i)), {})
        cubo[raiz(i.id)] = cubo.get(raiz(i.id), False) or any(v[1] not in NIVELES_NUEVOS for v in i.vistas)
    for base in sorted(por_nombre):
        if not nombre_completo(base):
            continue
        for grupo, bloqueadas in por_edad(por_nombre[base]):
            raices = sorted(grupo)
            if len(raices) == 2 and not bloqueadas:
                fa, fb = fichas[raices[0]], fichas[raices[1]]
                if not (fa.ordinal or fb.ordinal) and not (fa.con_id and fb.con_id):
                    unir(raices[0], raices[1], "nombre")

    # La principal de cada ficha y, repasando las uniones en orden, la que llevó a cada una hasta ella.
    principal = {}
    for r, ficha in fichas.items():
        p = min((por_id[k] for k in ficha.miembros), key=_orden_principal).id
        for k in ficha.miembros:
            principal[k] = p
    padre2 = {k: k for k in ids}
    grupo = {k: [k] for k in ids}
    con_principal = {k: principal[k] == k for k in ids}
    union_por = {}

    def raiz2(k):
        while padre2[k] != k:
            padre2[k] = padre2[padre2[k]]
            k = padre2[k]
        return k

    for regla, a, b in uniones:
        ra, rb = raiz2(a), raiz2(b)
        if con_principal[ra]:
            union_por.update((k, regla) for k in grupo[rb])
        elif con_principal[rb]:
            union_por.update((k, regla) for k in grupo[ra])
        if len(grupo[ra]) < len(grupo[rb]):
            ra, rb = rb, ra
        grupo[ra] += grupo.pop(rb)
        con_principal[ra] = con_principal[ra] or con_principal.pop(rb)
        padre2[rb] = ra
    return {k: (principal[k], None if principal[k] == k else union_por[k]) for k in ids}
