"""nacimiento.py — El año de nacimiento de un niño, estimado por las categorías en las que ha jugado.
Puro: sin base, sin red y sin estado.

Nadie publica la fecha de nacimiento: ni la federación ni las actas. Lo único que se sabe es en qué
categoría jugó cada temporada y cuántos partidos, y cada categoría admite dos o tres años de nacimiento
(VENTANA). Una temporada sola deja dos años posibles; varias se cruzan y van cerrando la ventana.

No basta con cruzar intervalos: un niño puede jugar un año con los mayores (subir de categoría antes de
tiempo es habitual; quedarse en una de pequeños siendo demasiado mayor, raro), y un acta puede estar mal.
Por eso cada observación no descarta un año, lo hace menos verosímil (`verosimilitud`), y `estimar` suma
los logaritmos de todas, pesando cada una por sus partidos: dos partidos sueltos con los mayores no pesan
lo que una temporada entera. Se devuelven los años que quedan cerca del mejor (a menos de RAZON veces), de
uno a tres: con uno, el año es seguro; con dos o tres, la web lo marca como dudoso.
"""
import math
from typing import Iterable

# Por categoría (en minúsculas): quien juega la temporada que empieza el año Y en ella nació entre
# Y - mayor e Y - menor (los dos incluidos).
VENTANA: dict[str, tuple[int, int]] = {
    "prebenjamin": (7, 6),
    "benjamin": (9, 8),
    "alevin": (11, 10),
    "infantil": (13, 12),
    "cadete": (15, 14),
    "juvenil": (18, 16),
}

# Se quedan los años cuya verosimilitud total es al menos la del mejor dividida por RAZON.
RAZON = 3.0
# Con estos partidos o más, una observación pesa entera; con menos, en proporción (y nunca menos de 0,2).
PARTIDOS_PLENOS = 5
_PESO_MINIMO = 0.2
_MAXIMO_DE_ANIOS = 3
# Margen en el logaritmo para que dos años empatados no se separen por el redondeo.
_TOLERANCIA = 1e-9

# Verosimilitud de un año fuera de la ventana, por cuántos años se sale. Más joven: juega con los mayores
# (habitual con uno, raro con dos, casi imposible con tres o más). Más viejo: se queda con los pequeños,
# que no se permite (un año, un error de acta o una dispensa; dos o más, casi nunca).
_MAS_JOVEN = {1: 0.25, 2: 0.05}
_MAS_JOVEN_LEJOS = 0.002
_MAS_VIEJO = {1: 0.01}
_MAS_VIEJO_LEJOS = 0.0005
# Cuántos años de más se miran alrededor de las ventanas: los que caben en las tablas de arriba.
_MARGEN_VIEJO = 2
_MARGEN_JOVEN = 4


def verosimilitud(anio: int, temporada: int, categoria: str) -> float:
    """Lo verosímil que es haber nacido en `anio` para quien juega en `categoria` la temporada que empieza
    `temporada`: 1 dentro de la ventana y menos cuanto más se sale. Categoría desconocida: KeyError."""
    mayor, menor = VENTANA[categoria]
    mas_viejo, mas_joven = temporada - mayor, temporada - menor     # los dos extremos de la ventana
    if anio > mas_joven:
        return _MAS_JOVEN.get(anio - mas_joven, _MAS_JOVEN_LEJOS)
    if anio < mas_viejo:
        return _MAS_VIEJO.get(mas_viejo - anio, _MAS_VIEJO_LEJOS)
    return 1.0


def _peso(partidos: int) -> float:
    """Cuánto cuenta una observación por sus partidos, antes de compararla con las demás."""
    return max(_PESO_MINIMO, min(1.0, partidos / PARTIDOS_PLENOS))


def estimar(observaciones: Iterable[tuple[int, str, int]]) -> tuple[int, ...]:
    """Los años de nacimiento posibles (de uno a tres, en orden creciente) de quien tiene estas
    observaciones: (año de inicio de la temporada, categoría en minúsculas, partidos). Las de categoría
    desconocida no cuentan; sin ninguna que cuente, ().

    El peso de cada observación es el de sus partidos dividido por el de la que más pesa: la que más pesa,
    pesa 1. Así una sola observación de un partido decide igual que una de veinte, y lo que se rebaja es la
    que tiene pocos partidos al lado de otra con muchos."""
    # Ordenadas: la suma (y con ella los empates) no depende del orden de entrada.
    validas = sorted((t, c, p) for t, c, p in observaciones if c in VENTANA)
    if not validas:
        return ()
    pesos = [_peso(p) for _, _, p in validas]
    mayor_peso = max(pesos)
    desde = min(t - VENTANA[c][0] for t, c, _ in validas) - _MARGEN_VIEJO
    hasta = max(t - VENTANA[c][1] for t, c, _ in validas) + _MARGEN_JOVEN
    total = {
        anio: sum(peso / mayor_peso * math.log(verosimilitud(anio, t, c))
                  for (t, c, _), peso in zip(validas, pesos))
        for anio in range(desde, hasta + 1)
    }
    mejor = max(total.values())
    corte = mejor - math.log(RAZON) - _TOLERANCIA
    # Los mejores primero; a igualdad (dentro de la tolerancia), el año menor.
    cerca = sorted((anio for anio, v in total.items() if v >= corte), key=lambda a: (-round(total[a], 9), a))
    return tuple(sorted(cerca[:_MAXIMO_DE_ANIOS]))
