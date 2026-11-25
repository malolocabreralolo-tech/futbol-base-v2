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
    en orden de id de MyGol. No depende del orden de entrada."""
    ninos = sorted(set(ninos), key=lambda n: n.id)
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
    candidatos: dict[int, int] = {}
    for n in ninos:
        if not nombre_completo(n.norm) or (n.temporada, n.norm) in dos_ninos:
            continue
        unica = por_nombre.get(n.norm, set())
        if len(unica) != 1:
            continue                    # 3: ninguna ficha, o dos (la duda)
        (fid,) = unica
        if edad_compatible(anios[fid], n.temporada, n.categoria):
            candidatos[n.id] = fid
    # 5: dos niños de la misma temporada en clubes sin nada en común no pueden ser la misma ficha; como no
    # se sabe cuál de los dos lo es, se quitan todos los de esa ficha y esa temporada.
    por_ficha: dict[tuple[int, int], list[Nino]] = {}
    for n in ninos:
        if n.id in candidatos:
            por_ficha.setdefault((candidatos[n.id], n.temporada), []).append(n)
    fuera = {n.id for grupo in por_ficha.values() if _choca(grupo) for n in grupo}
    return {i: fid for i, fid in candidatos.items() if i not in fuera}
