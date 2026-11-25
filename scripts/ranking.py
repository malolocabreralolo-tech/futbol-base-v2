"""ranking.py — El índice del ranking de los mejores de cada año de nacimiento. Puro: sin base ni red.

El ranking solo sale de las actas, que es donde cada gol y cada partido están atados a una ficha, y es un
ranking de lo medible: favorece a quien marca (defensas y porteros casi no se pueden valorar con lo que dan
las actas). Es más difícil destacar en un equipo bueno y en una liga buena que en un equipo malo y en una
liga mala, así que un gol no vale lo mismo en todas partes. Cuatro factores, cada uno en una frase:

1. El rival (por partido): un gol vale más cuanto menos encaja el rival, medido con toda su temporada en
   la categoría y con prudencia (encajados_prudente, peso_rival).
2. La liga (por grupo): la letra de la Segunda Fase y «Preferente» (nivel_fase), y la isla (nivel_isla).
   En infantil, cadete y juvenil (que entran en el ranking cuando la web los enseña, parte E2), también la
   División de Honor, la Autonómica, la Interinsular, la Fase Oro y la Fase Plata de Preferente, la Segunda
   y la Insular (y su B). Un grupo sin nivel propio (la Primera Fase, las eliminatorias, una copa) cuenta
   como la Segunda Fase en la que la federación puso a su equipo esa temporada (fase_que_cuenta): el equipo
   bueno es el que acabó en la A; en las categorías nuevas, como la liga de su equipo esa temporada.
3. El equipo (por grupo): un poco más si su equipo es de los de arriba de la tabla (nivel_equipo).
4. La edad: más si es de los pequeños de la categoría o juega en la de arriba (factor_edad).

Y se corrige a quien ha jugado muy pocos partidos, para que tres goles en un partido no lo pongan primero:

    índice = 100 × (GP + PRUDENCIA) / (PJ + PRUDENCIA)

PJ son los partidos jugados y GP los goles «ponderados» de cada fila (temporada, categoría y grupo):
goles por rival / media de goles por partido de esa temporada y categoría × nivel de la fase × nivel de la
isla × nivel del equipo × premio por edad. Los goles por rival son la suma, partido a partido, de cada gol
por el peso de su rival. 100 es la media de la categoría: quien marca al ritmo medio, a rivales normales,
en una liga de nivel 1, en un equipo de nivel 1 (o sin cifras) y siendo de los mayores, tiene 100. Los
PRUDENCIA partidos de más, a ritmo medio, son la corrección: con pocos partidos el índice se queda cerca de
100; con muchos, manda lo que el niño ha hecho.
"""
import re
import unicodedata
from typing import Iterable, Mapping

from nacimiento import VENTANA

# Partidos «a ritmo medio» que se suman a todos: con pocos partidos, el índice se acerca a 100.
PRUDENCIA = 6
# Partidos mínimos para salir en el ranking de esta temporada y en el de toda la trayectoria.
MIN_TEMPORADA = 3
MIN_TRAYECTORIA = 10
# Como mucho estos niños por lista.
TOPE = 100

# Un gol vale la media de lo que se encaja en el grupo entre lo que encaja ese rival, entre estos dos topes:
# al rival que lo encaja todo, la mitad; al que no encaja nada, una vez y media.
RIVAL_MIN = 0.5
RIVAL_MAX = 1.5
# Lo que encaja el rival se mide con toda su temporada en la categoría, con estos partidos de más a la
# media (encajados_prudente): con uno, el rival queda casi en la media; con veinte, pesa lo que ha hecho.
PRUDENCIA_RIVAL = 4
# Con menos partidos en el grupo, el puesto de un equipo aún no dice nada (nivel_equipo).
MIN_PARTIDOS_EQUIPO = 3
# El del último de su grupo y el del primero; entre ellos, en línea recta por el puesto.
EQUIPO_MIN = 0.90
EQUIPO_MAX = 1.15
# Las ligas de Lanzarote y Fuerteventura tienen menos equipos y menos nivel que las de Gran Canaria. Es una
# apreciación fija, no una medida: los equipos de islas distintas no se cruzan en las actas.
# Las de varias islas (interinsular: la División de Honor, la Autonómica, la Interinsular de infantil, cadete y
# juvenil), explícitas: no se rebajan.
NIVEL_ISLA = {"grancanaria": 1.0, "lanzarote": 0.85, "fuerteventura": 0.85, "interinsular": 1.0}

# (temporada, categoría, fase, partidos, titular, goles, goles por rival, isla, percentil)
Fila = tuple[int, str, str | None, int, int, int, float, str | None, float | None]

# El nivel de cada grupo de la segunda fase (A el más fuerte) y el de Preferente y la Copa de Campeones,
# que juntan a los mejores equipos. Lo que no se reconoce es una liga normal: 1.
_NIVEL_LETRA = {"a": 1.30, "b": 1.15, "c": 1.05, "d": 1.00, "e": 0.95}
_NIVEL_OTRA_LETRA = 0.90
_NIVEL_PREFERENTE = 1.25
_NIVEL_CAMPEONES = 1.25
_NIVEL_NORMAL = 1.0
# Infantil, cadete y juvenil (fútbol 11, parte E): los niveles por encima de las ligas de isla (División de
# Honor, Autonómica e Interinsular, que juntan a los mejores de varias islas), la Fase Oro y la Fase Plata de
# Preferente, y por debajo de Primera, la Segunda y la Insular (y la Insular B, el escalón de debajo). Es una
# apreciación fija, como la de las islas: los grupos de niveles distintos no se cruzan.
_NIVEL_DIVISION_HONOR = 1.50
_NIVEL_AUTONOMICA = 1.45
_NIVEL_INTERINSULAR = 1.35
_NIVEL_ORO = 1.30
_NIVEL_PLATA = 1.15
_NIVEL_SEGUNDA = 0.95
_NIVEL_INSULAR = 0.90
_NIVEL_INSULAR_B = 0.85
# Por dónde empieza la fase (groups.phase, normalizada) y su nivel, por este orden.
_NIVEL_POR_PRINCIPIO = (("division de honor", _NIVEL_DIVISION_HONOR), ("autonomica", _NIVEL_AUTONOMICA),
                        ("interinsular", _NIVEL_INTERINSULAR))
_SEGUNDA_FASE = re.compile(r"^segunda fase ([a-z])\b")
_CAMPEONES = re.compile(r"^copa (de )?campeones\b")
_LETRA_FINAL = re.compile(r" ([a-e])$")

# Premio por edad, por cuántos años es más joven que el mayor que admite la categoría: 1, de los pequeños;
# 2, juega con los mayores; 3 o más, dos categorías por encima de la suya.
_PREMIO_EDAD = {1: 1.10, 2: 1.25}
_PREMIO_EDAD_LEJOS = 1.40


def _normalizar(texto: str) -> str:
    """Sin tildes, en minúsculas y con espacios simples."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def nivel_fase(fase: str | None) -> float:
    """El nivel de la liga por la fase del grupo, tal como está en groups.phase, por este orden: empieza
    por «División de Honor» 1,50, «Autonómica» 1,45, «Interinsular» 1,35; «Preferente …» 1,25 (con «Fase
    Oro» 1,30 y con «Fase Plata» 1,15); la Copa de Campeones sin letra 1,25 (con letra A-E, la de esa
    letra); «Segunda Fase A» (o «… A GC») 1,30, B 1,15, C 1,05, D 1,00, E 0,95 y otra letra 0,90; empieza
    por «Segunda» sin ser la Segunda Fase («Segunda GC», de juvenil) 0,95; «Insular B …» 0,85; «Insular …»
    0,90; lo demás («Primera GC», una copa, una fase de ascenso), y sin fase, 1."""
    if not fase:
        return _NIVEL_NORMAL
    f = _normalizar(fase)
    for principio, nivel in _NIVEL_POR_PRINCIPIO:
        if f.startswith(principio):
            return nivel
    if f.startswith("preferente"):
        if " fase oro" in f:
            return _NIVEL_ORO
        if " fase plata" in f:
            return _NIVEL_PLATA
        return _NIVEL_PREFERENTE
    if _CAMPEONES.match(f):
        letra = _LETRA_FINAL.search(f)
        return _NIVEL_LETRA[letra.group(1)] if letra else _NIVEL_CAMPEONES
    segunda = _SEGUNDA_FASE.match(f)
    if segunda:
        return _NIVEL_LETRA.get(segunda.group(1), _NIVEL_OTRA_LETRA)
    if f.startswith("segunda") and not f.startswith("segunda fase"):
        return _NIVEL_SEGUNDA
    if f.startswith("insular b"):
        return _NIVEL_INSULAR_B
    if f.startswith("insular"):
        return _NIVEL_INSULAR
    return _NIVEL_NORMAL


def factor_edad(anio: int, temporada: int, categoria: str) -> float:
    """El premio por jugar siendo más joven que el mayor que admite la categoría: 1 si es de los mayores
    (o más viejo de lo que cabe), 1,10 un año menos, 1,25 dos y 1,40 tres o más."""
    mayor, _ = VENTANA[categoria]
    e = anio - (temporada - mayor)
    if e <= 0:
        return 1.0
    return _PREMIO_EDAD.get(e, _PREMIO_EDAD_LEJOS)


def tiene_nivel(fase: str | None) -> bool:
    """¿Tiene la fase un nivel propio en nivel_fase: una Segunda Fase con letra (aunque valga 1, como la D),
    «Preferente …», la Copa de Campeones o uno de los niveles de infantil, cadete y juvenil (División de
    Honor, Autonómica, Interinsular, Segunda, Insular)? La Primera Fase («Primera GC» también: vale 1), las
    eliminatorias, las copas y las ligas de isla, no."""
    if not fase:
        return False
    f = _normalizar(fase)
    return (f.startswith(("preferente", "insular") + tuple(p for p, _ in _NIVEL_POR_PRINCIPIO))
            or (f.startswith("segunda") and not f.startswith("segunda fase"))
            or bool(_CAMPEONES.match(f)) or bool(_SEGUNDA_FASE.match(f)))


def letra_segunda_fase(fase: str | None) -> str | None:
    """La letra («A», «B»…) de una fase «Segunda Fase X» (o «… X GC»); None si no lo es."""
    m = _SEGUNDA_FASE.match(_normalizar(fase)) if fase else None
    return m.group(1).upper() if m else None


def fase_que_cuenta(fase: str | None, mejor: str | None) -> str | None:
    """La fase con la que se mide el nivel de una fila: la suya si tiene nivel propio (tiene_nivel); si no,
    «Segunda Fase <mejor>», la mejor letra de Segunda Fase de su equipo esa temporada (la que le puso la
    federación), si la tiene; y si tampoco, la suya. Los goles de la Primera Fase o de las eliminatorias de
    un equipo que acabó en la A valen como de la A. En infantil, cadete y juvenil `mejor` es una fase entera
    (más de un carácter: la de la mejor liga de su equipo esa temporada, generate_js._rival_y_puesto), y se
    usa tal cual: la «Copa Insular Lanzarote» de un equipo de la Insular cuenta como «Insular Lanzarote»."""
    if tiene_nivel(fase) or not mejor:
        return fase
    if len(mejor) > 1:
        return mejor
    return f"Segunda Fase {mejor}"


def encajados_prudente(en_contra: int, partidos: int, media: float | None) -> float | None:
    """Lo que encaja un equipo por partido en su temporada, con PRUDENCIA_RIVAL partidos de más a la `media`
    (lo que encaja un equipo por partido de media en esa temporada y categoría): (en contra + PRUDENCIA_RIVAL
    × media) / (partidos + PRUDENCIA_RIVAL). Sin partidos, la media; sin media (None o no positiva), None."""
    if media is None or media <= 0:
        return None
    return (en_contra + PRUDENCIA_RIVAL * media) / (partidos + PRUDENCIA_RIVAL)


def peso_rival(encajados: float | None, media: float | None) -> float:
    """Lo que vale un gol marcado a un rival que encaja `encajados` goles por partido en un grupo donde se
    encajan `media` de media: media / encajados, entre RIVAL_MIN y RIVAL_MAX. Sin datos (None, o una media
    que no es positiva), 1; a un rival que no ha encajado ninguno, RIVAL_MAX."""
    if encajados is None or media is None or media <= 0:
        return 1.0
    if encajados <= 0:
        return RIVAL_MAX
    return min(RIVAL_MAX, max(RIVAL_MIN, media / encajados))


def nivel_equipo(percentil: float | None) -> float:
    """El nivel del equipo por su puesto en el grupo: `percentil` es 1 el primero y 0 el último (por puntos
    por partido), y el nivel va en línea recta de EQUIPO_MIN a EQUIPO_MAX (un percentil fuera de [0, 1] se
    recorta). None (sin datos, una copa, menos de MIN_PARTIDOS_EQUIPO partidos): 1."""
    if percentil is None:
        return 1.0
    p = min(1.0, max(0.0, percentil))
    return EQUIPO_MIN + (EQUIPO_MAX - EQUIPO_MIN) * p


def nivel_isla(isla: str | None) -> float:
    """El nivel de la isla del grupo (groups.island), de NIVEL_ISLA; una desconocida o None, 1."""
    return NIVEL_ISLA.get(isla, 1.0) if isla else 1.0


def indice(filas: Iterable[Fila], anio: int, medias: Mapping[tuple[int, str], float]) -> int:
    """round(100 × (GP + PRUDENCIA) / (PJ + PRUDENCIA)) de un niño nacido en `anio`. Una fila de categoría
    que no está en VENTANA o cuya (temporada, categoría) no tiene media (o la tiene a 0) no cuenta: ni sus
    partidos ni sus goles. Sin ninguna fila que cuente, 0."""
    pj, gp, cuenta = 0, 0.0, False
    for temporada, categoria, fase, partidos, _titular, _goles, por_rival, isla, percentil in filas:
        media = medias.get((temporada, categoria))
        if categoria not in VENTANA or not media:
            continue
        cuenta = True
        pj += partidos
        gp += (por_rival / media * nivel_fase(fase) * nivel_isla(isla) * nivel_equipo(percentil)
               * factor_edad(anio, temporada, categoria))
    if not cuenta:
        return 0
    return round(100 * (gp + PRUDENCIA) / (pj + PRUDENCIA))


def medias_de(filas_de_todos: Iterable[Fila]) -> dict[tuple[int, str], float]:
    """Goles por partido de cada (temporada, categoría): la suma de goles (los de verdad, sin ponderar por
    el rival) entre la suma de partidos de todas las filas. Una (temporada, categoría) sin ningún partido no
    tiene media (no sale)."""
    partidos, goles = {}, {}
    for temporada, categoria, _fase, pj, _titular, g, *_ in filas_de_todos:
        clave = (temporada, categoria)
        partidos[clave] = partidos.get(clave, 0) + pj
        goles[clave] = goles.get(clave, 0) + g
    return {clave: goles[clave] / pj for clave, pj in partidos.items() if pj}
