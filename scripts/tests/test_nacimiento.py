"""El estimador del año de nacimiento (scripts/nacimiento.py).

Nadie publica la fecha de nacimiento de un niño: se deduce de las categorías en las que ha jugado cada
temporada. Aquí se fijan las ventanas por categoría y los casos de la regla (una temporada, varias en la
misma categoría, el paso de una categoría a otra y dos categorías a la vez), todos inventados.
"""
from nacimiento import VENTANA, estimar, verosimilitud


def test_ventanas():
    assert VENTANA == {"miniprebenjamin": (5, 4), "prebenjamin": (7, 6), "benjamin": (9, 8),
                       "alevin": (11, 10), "infantil": (13, 12), "cadete": (15, 14), "juvenil": (18, 16)}


def test_verosimilitud():
    assert verosimilitud(2017, 2026, "benjamin") == 1.0 and verosimilitud(2018, 2026, "benjamin") == 1.0
    assert verosimilitud(2019, 2026, "benjamin") == 0.25      # un año por debajo: juega con los mayores
    assert verosimilitud(2020, 2026, "benjamin") == 0.05
    assert verosimilitud(2021, 2026, "benjamin") == 0.002
    assert verosimilitud(2016, 2026, "benjamin") == 0.01      # demasiado mayor
    assert verosimilitud(2015, 2026, "benjamin") == 0.0005


def test_una_temporada_da_dos_anios():
    assert estimar([(2026, "benjamin", 10)]) == (2017, 2018)
    assert estimar([(2026, "alevin", 22)]) == (2015, 2016)
    assert estimar([(2026, "juvenil", 20)]) == (2008, 2009, 2010)
    assert estimar([(2026, "benjamin", 1)]) == (2017, 2018)   # un solo partido no cambia el empate


def test_miniprebenjamin():
    # Solo lo juega la liga de escuelas (MyGol): niños de 4 y 5 años.
    assert estimar([(2025, "miniprebenjamin", 10)]) == (2020, 2021)
    # Miniprebenjamín en 2024 (2019-2020) y prebenjamín en 2026 (2019-2020): las dos ventanas son la misma
    # (dos años en el mini y otros dos en el pre, sin repetir), así que no se cierra nada.
    assert estimar([(2024, "miniprebenjamin", 12), (2026, "prebenjamin", 15)]) == (2019, 2020)
    # Miniprebenjamín en 2025 (2020-2021) y prebenjamín en 2026 (2019-2020): solo 2020 cabe en las dos.
    assert estimar([(2025, "miniprebenjamin", 12), (2026, "prebenjamin", 15)]) == (2020,)


def test_dos_temporadas_en_la_misma_categoria():
    assert estimar([(2025, "benjamin", 20), (2026, "benjamin", 10)]) == (2017,)


def test_tres_temporadas_en_la_misma_categoria():
    # La primera la jugó con los mayores.
    assert estimar([(2024, "benjamin", 18), (2025, "benjamin", 20), (2026, "benjamin", 20)]) == (2017,)


def test_cambio_de_categoria():
    assert estimar([(2025, "prebenjamin", 18), (2026, "benjamin", 12)]) == (2018,)
    assert estimar([(2024, "prebenjamin", 15), (2025, "benjamin", 20), (2026, "benjamin", 9)]) == (2017,)


def test_dos_categorias_la_misma_temporada():
    # Prebenjamín toda la temporada y dos partidos con el benjamín: no basta para decidir.
    assert estimar([(2025, "prebenjamin", 20), (2025, "benjamin", 2)]) == (2018, 2019)
    # Con media temporada en el benjamín, sí: es de los mayores de prebenjamín.
    assert estimar([(2025, "prebenjamin", 20), (2025, "benjamin", 12)]) == (2018,)


def test_sin_observaciones():
    assert estimar([]) == ()
    assert estimar([(2026, "veteranos", 30)]) == ()


def test_el_orden_no_importa():
    obs = [(2024, "prebenjamin", 15), (2025, "benjamin", 20), (2026, "benjamin", 9)]
    assert estimar(obs) == estimar(list(reversed(obs)))
