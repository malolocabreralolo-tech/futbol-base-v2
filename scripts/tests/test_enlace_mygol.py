"""TDD — el enlace de los niños de la liga de escuelas (MyGol) con las fichas de la federación
(scripts/enlace_mygol.py).

La regla, pura: nombres inventados, sin base ni red."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from enlace_mygol import MARGEN_JOVEN, Ficha, Nino, edad_compatible, enlazar  # noqa: E402

RAUL = "GOMEZ PEREZ, RAUL"


def nino(id, norm=RAUL, temporada=2024, categoria="prebenjamin", clubes=("viera",)):
    return Nino(id=id, norm=norm, temporada=temporada, categoria=categoria, clubes=frozenset(clubes))


def ficha(id, *nombres, anios=(2017,)):
    return Ficha(id=id, nombres=frozenset(nombres or (RAUL,)), anios=tuple(anios))


def test_edad_compatible():
    assert MARGEN_JOVEN == 1
    # Prebenjamín 2024: nacidos en 2017 o 2018, y un año por abajo (2019) también vale.
    assert edad_compatible((2018,), 2024, "prebenjamin")
    assert edad_compatible((2019,), 2024, "prebenjamin")
    assert not edad_compatible((2020,), 2024, "prebenjamin")
    assert not edad_compatible((2016,), 2024, "prebenjamin")
    assert edad_compatible((2016, 2017), 2024, "prebenjamin")
    assert edad_compatible((), 2024, "prebenjamin")              # sin año: no se puede descartar
    assert edad_compatible((2010,), 2024, None)                  # sin categoría, tampoco
    assert edad_compatible((2010,), 2024, "veteranos")


def test_enlaza_nombre_completo_unico():
    assert enlazar([nino(1)], [ficha(500)]) == {1: 500}


def test_un_apellido_no_se_enlaza():
    assert enlazar([nino(1, norm="GOMEZ, RAUL")], [ficha(500)]) == {}
    assert enlazar([nino(1, norm="GOMEZ, RAUL")], [ficha(500, "GOMEZ, RAUL")]) == {}


def test_dos_fichas_candidatas_no_se_enlaza():
    assert enlazar([nino(1)], [ficha(500), ficha(501)]) == {}
    # Aunque una de las dos sea de otra edad: dos fichas con el nombre ya son la duda.
    assert enlazar([nino(1)], [ficha(500), ficha(501, anios=(2010,))]) == {}


def test_edad_incompatible_no_se_enlaza():
    assert enlazar([nino(1)], [ficha(500, anios=(2014,))]) == {}
    assert enlazar([nino(1, temporada=2026, categoria="miniprebenjamin")], [ficha(500, anios=(2017,))]) == {}


def test_nombre_repetido_en_dos_clubes_no_se_enlaza():
    # Dos niños con el mismo nombre la misma temporada, en clubes que no tienen nada en común: dos niños.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"b"})], [ficha(500)]) == {}
    # El mismo club apuntado dos veces (sus equipos A y E): es el mismo niño, y los dos van a la ficha.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"a", "c"})], [ficha(500)]) == {1: 500, 2: 500}
    # El que se repite en otra temporada no estorba al de esta.
    assert enlazar([nino(1, clubes={"a"}), nino(2, clubes={"b"}), nino(3, temporada=2025, categoria="benjamin")],
                   [ficha(500)]) == {3: 500}


def test_una_ficha_no_recibe_dos_ninos_de_la_misma_temporada():
    otro = "GOMEZ PEREZ, RAUL ANTONIO"
    f = ficha(500, RAUL, otro)                 # dos identidades de la federación, con dos nombres
    a, b = nino(1, clubes={"a"}), nino(2, norm=otro, clubes={"b"})
    assert enlazar([a, b], [f]) == {}
    # Con un club en común, sí (el mismo niño apuntado dos veces con dos grafías).
    assert enlazar([a, nino(2, norm=otro, clubes={"a"})], [f]) == {1: 500, 2: 500}
    # En temporadas distintas, también: un niño cambia de club de un año a otro.
    assert enlazar([a, nino(2, norm=otro, temporada=2025, categoria="benjamin", clubes={"b"})], [f]) \
        == {1: 500, 2: 500}


def test_el_mismo_nino_en_varias_temporadas():
    ninos = [nino(1, temporada=2023, categoria="miniprebenjamin"), nino(2, temporada=2024),
             nino(3, temporada=2025)]
    assert enlazar(ninos, [ficha(500, anios=(2018,))]) == {1: 500, 2: 500, 3: 500}


def test_el_orden_no_importa():
    ninos = [nino(1), nino(2, norm="SUAREZ DIAZ, IVAN"), nino(3, clubes={"a"}, temporada=2025),
             nino(4, clubes={"b"}, temporada=2025), nino(5, norm="MORALES RUIZ, HUGO", temporada=2023,
                                                         categoria="miniprebenjamin"),
             nino(6, norm="NAVARRO GIL, OSCAR", clubes={"x"}), nino(7, norm="NAVARRO GIL, OSCAR", clubes={"x", "y"})]
    fichas = [ficha(500), ficha(501, "SUAREZ DIAZ, IVAN"), ficha(502, "MORALES RUIZ, HUGO", anios=(2018, 2019)),
              ficha(503, "NAVARRO GIL, OSCAR", anios=())]
    esperado = enlazar(ninos, fichas)
    assert esperado == {1: 500, 2: 501, 5: 502, 6: 503, 7: 503}
    azar = random.Random(7)
    for _ in range(20):
        n, f = ninos[:], fichas[:]
        azar.shuffle(n)
        azar.shuffle(f)
        assert enlazar(n, f) == esperado
        assert list(enlazar(n, f)) == list(esperado)        # también el orden de las claves


def test_el_nombre_de_una_identidad_secundaria_vale():
    # La principal de la ficha es «GOMEZ PEREZ, RAUL ANTONIO»; el acta de otra temporada (unida) dice «RAUL».
    f = ficha(500, "GOMEZ PEREZ, RAUL ANTONIO", RAUL)
    assert enlazar([nino(1)], [f]) == {1: 500}
