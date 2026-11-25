"""El índice del ranking (scripts/ranking.py).

100 es la media de la categoría: quien marca al ritmo medio en una liga de nivel 1 y siendo de los
mayores. Aquí se fijan el nivel de cada fase, el premio por edad, la corrección de los pocos partidos y
qué filas no cuentan, con casos inventados.
"""
import pytest

from ranking import PRUDENCIA, factor_edad, indice, medias_de, nivel_fase


def test_nivel_fase():
    assert nivel_fase("Segunda Fase A") == 1.30 and nivel_fase("Segunda Fase A GC") == 1.30
    assert nivel_fase("Segunda Fase B") == 1.15 and nivel_fase("Segunda Fase C GC") == 1.05
    assert nivel_fase("Segunda Fase D GC") == 1.00 and nivel_fase("Segunda Fase E GC") == 0.95
    assert nivel_fase("Segunda Fase F") == 0.90
    assert nivel_fase("Segunda Fase GC") == 1.0            # sin letra (2023-24)
    assert nivel_fase("Preferente GC") == 1.25 and nivel_fase("Preferente Lanzarote") == 1.25
    assert nivel_fase("Copa de Campeones") == 1.25 and nivel_fase("Copa Campeones Benjamin B") == 1.15
    assert nivel_fase("Primera Fase GC") == 1.0 and nivel_fase("Eliminatorias") == 1.0
    assert nivel_fase(None) == 1.0 and nivel_fase("segunda fase a") == 1.30


def test_factor_edad():
    assert factor_edad(2017, 2026, "benjamin") == 1.0      # de los mayores
    assert factor_edad(2018, 2026, "benjamin") == 1.10     # de los pequeños
    assert factor_edad(2019, 2026, "benjamin") == 1.25     # juega con los mayores
    assert factor_edad(2020, 2026, "benjamin") == 1.40
    assert factor_edad(2016, 2026, "benjamin") == 1.0      # más viejo de lo que cabe: sin premio
    assert factor_edad(2010, 2026, "juvenil") == 1.25


MEDIAS = {(2026, "benjamin"): 0.5}


def test_indice_media_es_100():
    # 20 partidos y 10 goles con una media de 0,5: marca al ritmo medio.
    assert indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 10)], 2017, MEDIAS) == 100


def test_indice_premia_nivel_y_edad():
    base = indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert base == round(100 * (60 + PRUDENCIA) / 26) == 254
    assert indice([(2026, "benjamin", "Segunda Fase A", 20, 20, 30)], 2017, MEDIAS) == round(100 * (78 + 6) / 26) == 323
    assert indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2018, MEDIAS) == round(100 * (66 + 6) / 26) == 277


def test_pocos_partidos_no_gana():
    uno = indice([(2026, "benjamin", "Primera Fase GC", 1, 1, 3)], 2017, MEDIAS)      # 3 goles en 1 partido
    veinte = indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert uno == round(100 * (6 + 6) / 7) == 171 and uno < veinte


def test_filas_que_no_cuentan():
    filas = [(2026, "benjamin", None, 10, 10, 5), (2025, "benjamin", None, 30, 30, 90), (2026, "veteranos", None, 9, 9, 9)]
    assert indice(filas, 2017, MEDIAS) == 100          # 2025 no tiene media y «veteranos» no es una categoría
    assert indice([], 2017, MEDIAS) == 0
    assert indice([(2026, "benjamin", None, 10, 10, 5)], 2017, {(2026, "benjamin"): 0}) == 0


def test_medias_de():
    filas = [(2026, "benjamin", None, 10, 10, 5), (2026, "benjamin", None, 30, 0, 5), (2025, "alevin", None, 4, 4, 0)]
    assert medias_de(filas) == {(2026, "benjamin"): pytest.approx(0.25), (2025, "alevin"): 0.0}
