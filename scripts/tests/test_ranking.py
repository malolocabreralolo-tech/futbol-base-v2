"""El índice del ranking (scripts/ranking.py).

100 es la media de la categoría: quien marca al ritmo medio, a rivales normales, en una liga de nivel 1 y
en un equipo de nivel 1 (o sin cifras), siendo de los mayores. Aquí se fijan el peso del rival, el nivel de cada
fase y de cada isla, el del equipo, el premio por edad, la corrección de los pocos partidos y qué filas no
cuentan, con casos inventados.
"""
import pytest

from ranking import (PRUDENCIA, encajados_prudente, factor_edad, fase_que_cuenta, indice, letra_segunda_fase,
                     medias_de, nivel_equipo, nivel_fase, nivel_isla, peso_rival, tiene_nivel)


def fila(t, c, fase, pj, tit, g, gr=None, isla=None, pct=None):
    """Una fila de nueve campos; sin los goles por rival, los goles tal cual (rivales de la media)."""
    return (t, c, fase, pj, tit, g, g if gr is None else gr, isla, pct)


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
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 10)], 2017, MEDIAS) == 100


def test_indice_premia_nivel_y_edad():
    base = indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert base == round(100 * (60 + PRUDENCIA) / 26) == 254
    assert indice([fila(2026, "benjamin", "Segunda Fase A", 20, 20, 30)], 2017, MEDIAS) == round(100 * (78 + 6) / 26) == 323
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2018, MEDIAS) == round(100 * (66 + 6) / 26) == 277


def test_pocos_partidos_no_gana():
    uno = indice([fila(2026, "benjamin", "Primera Fase GC", 1, 1, 3)], 2017, MEDIAS)      # 3 goles en 1 partido
    veinte = indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert uno == round(100 * (6 + 6) / 7) == 171 and uno < veinte


def test_filas_que_no_cuentan():
    filas = [fila(2026, "benjamin", None, 10, 10, 5), fila(2025, "benjamin", None, 30, 30, 90), fila(2026, "veteranos", None, 9, 9, 9)]
    assert indice(filas, 2017, MEDIAS) == 100          # 2025 no tiene media y «veteranos» no es una categoría
    assert indice([], 2017, MEDIAS) == 0
    assert indice([fila(2026, "benjamin", None, 10, 10, 5)], 2017, {(2026, "benjamin"): 0}) == 0


def test_medias_de():
    filas = [fila(2026, "benjamin", None, 10, 10, 5), fila(2026, "benjamin", None, 30, 0, 5), fila(2025, "alevin", None, 4, 4, 0)]
    assert medias_de(filas) == {(2026, "benjamin"): pytest.approx(0.25), (2025, "alevin"): 0.0}


def test_peso_rival():
    assert peso_rival(2.0, 2.0) == 1.0
    assert peso_rival(4.0, 2.0) == 0.5 and peso_rival(8.0, 2.0) == 0.5      # el rival más goleado: el mínimo
    assert peso_rival(1.0, 2.0) == 1.5 and peso_rival(1.6, 2.0) == 1.25      # el que menos encaja: hasta 1,5
    assert peso_rival(0, 2.0) == 1.5
    assert peso_rival(None, 2.0) == 1.0 and peso_rival(2.0, None) == 1.0 and peso_rival(2.0, 0) == 1.0


def test_nivel_equipo():
    assert nivel_equipo(1.0) == 1.15 and nivel_equipo(0.0) == 0.90
    assert nivel_equipo(0.5) == pytest.approx(1.025) and nivel_equipo(None) == 1.0
    assert nivel_equipo(1.7) == 1.15 and nivel_equipo(-0.2) == 0.90


def test_nivel_isla():
    assert nivel_isla("grancanaria") == 1.0 and nivel_isla("lanzarote") == 0.85
    assert nivel_isla("fuerteventura") == 0.85 and nivel_isla(None) == 1.0 and nivel_isla("otra") == 1.0


def test_indice_pondera_rival_liga_y_equipo():
    medias = {(2026, "benjamin"): 0.5}
    # 20 partidos y 30 goles, todos a rivales de la media: como antes.
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30, gr=30.0)], 2017, medias) == 254
    # Los mismos 30 goles, pero a los rivales más goleados (cada gol vale la mitad).
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30, gr=15.0)], 2017, medias) == round(100 * (30 + 6) / 26) == 138
    # En Lanzarote: 60 × 0,85.
    assert indice([fila(2026, "benjamin", "Lanzarote", 20, 20, 30, gr=30.0, isla="lanzarote")], 2017, medias) == round(100 * (51 + 6) / 26) == 219
    # En el primero del grupo: 60 × 1,15.
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30, gr=30.0, isla="grancanaria", pct=1.0)], 2017, medias) == round(100 * (69 + 6) / 26) == 288
    # En el último: 60 × 0,90.
    assert indice([fila(2026, "benjamin", "Primera Fase GC", 20, 20, 30, gr=30.0, pct=0.0)], 2017, medias) == round(100 * (54 + 6) / 26) == 231


def test_medias_de_con_los_goles_sin_ponderar():
    # La media es de goles de verdad: los goles por rival (7.º campo) no la mueven.
    filas = [fila(2026, "benjamin", None, 10, 10, 5, gr=50.0), fila(2026, "benjamin", None, 10, 0, 5, gr=0.0)]
    assert medias_de(filas) == {(2026, "benjamin"): 0.5}


def test_encajados_prudente():
    # Lo que encaja un equipo en toda su temporada, con PRUDENCIA_RIVAL partidos de más a la media.
    assert encajados_prudente(0, 0, 2.0) == 2.0
    assert encajados_prudente(20, 1, 2.0) == pytest.approx(28 / 5)
    assert encajados_prudente(10, 20, 2.0) == pytest.approx(18 / 24)
    assert encajados_prudente(5, 3, None) is None and encajados_prudente(5, 3, 0) is None
    # Una goleada en un solo partido ya no hunde el peso al mínimo… salvo que sea de 20.
    assert peso_rival(encajados_prudente(20, 1, 2.0), 2.0) == 0.5
    assert peso_rival(encajados_prudente(3, 1, 2.0), 2.0) == pytest.approx(2.0 / (11 / 5))


def test_tiene_nivel_y_fase_que_cuenta():
    assert tiene_nivel("Segunda Fase D")                   # aunque valga 1,00
    assert tiene_nivel("Preferente GC") and tiene_nivel("Copa de Campeones")
    assert not tiene_nivel("Primera Fase GC") and not tiene_nivel("Eliminatorias")
    assert not tiene_nivel("Segunda Fase GC") and not tiene_nivel(None)
    assert fase_que_cuenta("Primera Fase GC", "A") == "Segunda Fase A"
    assert fase_que_cuenta("Eliminatorias", "F") == "Segunda Fase F"
    assert fase_que_cuenta("Segunda Fase C", "A") == "Segunda Fase C"
    assert fase_que_cuenta("Primera Fase GC", None) == "Primera Fase GC"
    assert fase_que_cuenta(None, "B") == "Segunda Fase B"
    assert letra_segunda_fase("Segunda Fase A GC") == "A" and letra_segunda_fase("segunda fase f") == "F"
    assert letra_segunda_fase("Segunda Fase GC") is None and letra_segunda_fase("Copa Campeones Benjamin B") is None
    assert letra_segunda_fase(None) is None


def test_nivel_fase_de_las_categorias_nuevas():
    """Los niveles de infantil, cadete y juvenil (parte E; entran en el ranking cuando la web los enseña)."""
    assert nivel_fase("División de Honor") == 1.50
    assert nivel_fase("Autonómica") == 1.45
    assert nivel_fase("Interinsular") == 1.35
    assert nivel_fase("Preferente GC Fase Oro") == 1.30
    assert nivel_fase("Preferente GC Fase Plata") == 1.15
    assert nivel_fase("Preferente GC") == 1.25
    assert nivel_fase("Primera GC") == 1.0
    assert nivel_fase("Segunda GC") == 0.95
    assert nivel_fase("Segunda Fase B") == 1.15              # sin cambio
    assert nivel_fase("Insular GC Fase 1") == 0.90
    assert nivel_fase("Insular B Lanzarote") == 0.85
    assert nivel_fase("Copa Insular Lanzarote") == 1.0        # una copa mezcla niveles
    # Lo que no empieza por el nivel no lo tiene: la fase de ascenso no es la liga a la que asciende.
    assert nivel_fase("Fase de Ascenso a División de Honor") == 1.0


def test_tiene_nivel_y_fase_que_cuenta_de_las_categorias_nuevas():
    assert tiene_nivel("Interinsular") and tiene_nivel("Insular GC")
    assert tiene_nivel("División de Honor") and tiene_nivel("Autonómica") and tiene_nivel("Segunda GC")
    assert tiene_nivel("Insular B Lanzarote") and tiene_nivel("Preferente GC Fase Oro")
    assert not tiene_nivel("Primera GC") and not tiene_nivel("Copa Insular Lanzarote")
    # Con la fase entera de la liga de su equipo esa temporada (la calcula E2), esa.
    assert fase_que_cuenta("Copa Insular Lanzarote", "Insular Lanzarote") == "Insular Lanzarote"
    assert fase_que_cuenta("Insular GC Fase 1", "Preferente GC") == "Insular GC Fase 1"   # tiene la suya
    assert fase_que_cuenta("Primera Fase GC", "A") == "Segunda Fase A"                   # hoy


def test_la_copa_de_campeones_de_las_nuevas_cuenta_con_su_liga():
    """En infantil, cadete y juvenil (por_liga: las del convenio, generate_js._cuenta_su_liga) la Copa de
    Campeones es una copa más: cuenta con la mejor liga de su equipo y, sin ella (una liga sin nivel propio,
    como la Primera), con 1, como las demás copas; nunca con su 1,25 fijo. En benjamín, prebenjamín y alevín
    de Gran Canaria, como siempre."""
    assert fase_que_cuenta("Copa de Campeones", "Primera Lanzarote", por_liga=True) == "Primera Lanzarote"
    assert fase_que_cuenta("Copa de Campeones", "Insular Fuerteventura", por_liga=True) == "Insular Fuerteventura"
    assert nivel_fase(fase_que_cuenta("Copa de Campeones", None, por_liga=True)) == 1.0
    assert fase_que_cuenta("Copa de Campeones", "Preferente GC Fase Oro", por_liga=True) == "Preferente GC Fase Oro"
    # Las demás, igual con por_liga.
    assert fase_que_cuenta("Copa Insular Lanzarote", "Insular Lanzarote", por_liga=True) == "Insular Lanzarote"
    assert fase_que_cuenta("Insular GC Fase 1", "Preferente GC", por_liga=True) == "Insular GC Fase 1"
    # Las de siempre: la suya, 1,25 (o la de su letra).
    assert fase_que_cuenta("Copa de Campeones", "A") == "Copa de Campeones"
    assert fase_que_cuenta("Copa Campeones Benjamin B", None) == "Copa Campeones Benjamin B"
    assert nivel_fase(fase_que_cuenta("Copa de Campeones", None)) == 1.25


def test_nivel_isla_interinsular():
    """Las ligas de varias islas no se rebajan."""
    assert nivel_isla("interinsular") == 1.0
