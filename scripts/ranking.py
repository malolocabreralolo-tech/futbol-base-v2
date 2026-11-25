"""ranking.py — El índice del ranking de los mejores de cada año de nacimiento. Puro: sin base ni red.

El ranking solo sale de las actas, que es donde cada gol y cada partido están atados a una ficha, y es un
ranking de lo medible: favorece a quien marca (defensas y porteros casi no se pueden valorar con lo que dan
las actas). La fórmula premia marcar mucho, hacerlo en una liga de nivel alto y hacerlo siendo de los
pequeños de la categoría o jugando en la de arriba, y corrige a quien ha jugado muy pocos partidos para que
tres goles en un partido no lo pongan primero:

    índice = 100 × (GP + PRUDENCIA) / (PJ + PRUDENCIA)

PJ son los partidos jugados y GP los goles «ponderados» de cada fila (temporada, categoría y fase):
goles / media de goles por partido de esa temporada y categoría × nivel de la fase × premio por edad.
100 es la media de la categoría: quien marca al ritmo medio, en una liga de nivel 1 y siendo de los
mayores, tiene 100. Los PRUDENCIA partidos de más, a ritmo medio, son la corrección: con pocos partidos
el índice se queda cerca de 100; con muchos, manda lo que el niño ha hecho.
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

# (temporada, categoría, fase, partidos, titular, goles)
Fila = tuple[int, str, str | None, int, int, int]

# El nivel de cada grupo de la segunda fase (A el más fuerte) y el de Preferente y la Copa de Campeones,
# que juntan a los mejores equipos. Lo que no se reconoce es una liga normal: 1.
_NIVEL_LETRA = {"a": 1.30, "b": 1.15, "c": 1.05, "d": 1.00, "e": 0.95}
_NIVEL_OTRA_LETRA = 0.90
_NIVEL_PREFERENTE = 1.25
_NIVEL_CAMPEONES = 1.25
_NIVEL_NORMAL = 1.0
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
    """El nivel de la liga por la fase del grupo, tal como está en groups.phase: «Segunda Fase A» (o
    «… A GC») 1,30, B 1,15, C 1,05, D 1,00, E 0,95 y otra letra 0,90; «Preferente …» y la Copa de
    Campeones sin letra 1,25 (con letra A-E, la de esa letra); lo demás, y sin fase, 1."""
    if not fase:
        return _NIVEL_NORMAL
    f = _normalizar(fase)
    if f.startswith("preferente"):
        return _NIVEL_PREFERENTE
    if _CAMPEONES.match(f):
        letra = _LETRA_FINAL.search(f)
        return _NIVEL_LETRA[letra.group(1)] if letra else _NIVEL_CAMPEONES
    segunda = _SEGUNDA_FASE.match(f)
    if segunda:
        return _NIVEL_LETRA.get(segunda.group(1), _NIVEL_OTRA_LETRA)
    return _NIVEL_NORMAL


def factor_edad(anio: int, temporada: int, categoria: str) -> float:
    """El premio por jugar siendo más joven que el mayor que admite la categoría: 1 si es de los mayores
    (o más viejo de lo que cabe), 1,10 un año menos, 1,25 dos y 1,40 tres o más."""
    mayor, _ = VENTANA[categoria]
    e = anio - (temporada - mayor)
    if e <= 0:
        return 1.0
    return _PREMIO_EDAD.get(e, _PREMIO_EDAD_LEJOS)


def indice(filas: Iterable[Fila], anio: int, medias: Mapping[tuple[int, str], float]) -> int:
    """round(100 × (GP + PRUDENCIA) / (PJ + PRUDENCIA)) de un niño nacido en `anio`. Una fila de categoría
    que no está en VENTANA o cuya (temporada, categoría) no tiene media (o la tiene a 0) no cuenta: ni sus
    partidos ni sus goles. Sin ninguna fila que cuente, 0."""
    pj, gp, cuenta = 0, 0.0, False
    for temporada, categoria, fase, partidos, _titular, goles in filas:
        media = medias.get((temporada, categoria))
        if categoria not in VENTANA or not media:
            continue
        cuenta = True
        pj += partidos
        gp += goles / media * nivel_fase(fase) * factor_edad(anio, temporada, categoria)
    if not cuenta:
        return 0
    return round(100 * (gp + PRUDENCIA) / (pj + PRUDENCIA))


def medias_de(filas_de_todos: Iterable[Fila]) -> dict[tuple[int, str], float]:
    """Goles por partido de cada (temporada, categoría): la suma de goles entre la suma de partidos de
    todas las filas. Una (temporada, categoría) sin ningún partido no tiene media (no sale)."""
    partidos, goles = {}, {}
    for temporada, categoria, _fase, pj, _titular, g in filas_de_todos:
        clave = (temporada, categoria)
        partidos[clave] = partidos.get(clave, 0) + pj
        goles[clave] = goles.get(clave, 0) + g
    return {clave: goles[clave] / pj for clave, pj in partidos.items() if pj}
