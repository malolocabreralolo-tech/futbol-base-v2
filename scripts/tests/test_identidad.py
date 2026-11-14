"""El resolvedor de fichas (scripts/identidad.py, fase 2C).

Una identidad de acta es lo que el acta dice con certeza (un id de la federación, o un nombre sin id en
un equipo y una temporada); una ficha es el niño. Aquí se fijan las reglas de docs/identidad.md con
casos inventados: ningún nombre de estas pruebas es el de un niño real (los cinco ejemplos del mapa
van con las iniciales del mapa).
"""
import random
import time
from collections import Counter

import pytest

from identidad import (Identidad, NIVEL, club, clave_publica, compatibles, intervalo, nombre_completo,
                       normalizar, resolver, trozo)
from import_fiflp_actas import _norm_player

PRE, BEN, ALE = NIVEL["PREBENJAMIN"], NIVEL["BENJAMIN"], NIVEL["ALEVIN"]


def v(anio, nivel, equipo, n=5, ini=None, fin=None):
    """Una vista: la temporada entera (octubre a mayo) si no se dice otra cosa."""
    return (anio, nivel, equipo, ini or f"{anio}-10-01", fin or f"{anio + 1}-05-31", n)


def ident(id_, norm, fiflp=None, *vistas):
    return Identidad(id=id_, norm=norm, fiflp_id=fiflp, vistas=tuple(vistas))


def fichas(resultado):
    """{principal: frozenset de ids} del resultado de resolver."""
    out = {}
    for i, (p, _) in resultado.items():
        out.setdefault(p, set()).add(i)
    return {p: frozenset(m) for p, m in out.items()}


def juntos(resultado, *ids):
    return len({resultado[i][0] for i in ids}) == 1


# ---------------------------------------------------------------------------
# Piezas sueltas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", [
    "Álvarez  Peña, José", "  muñoz ruiz,   iñigo ", "GARCÍA-LÓPEZ, ÁNGEL", "lucas", "Ñ", "",
    "DE LA ROSA DÍAZ, MARÍA DEL PINO", "o'neil, tom",
])
def test_normalizar_es_la_del_importador(nombre):
    assert normalizar(nombre) == _norm_player(nombre)


def test_normalizar_quita_tildes_y_espacios():
    assert normalizar("  Álvarez  Peña,   José ") == "ALVAREZ PENA, JOSE"


@pytest.mark.parametrize("norm, esperado", [
    ("ALVAREZ PENA, JOSE", True),
    ("DE LA ROSA, MARIA DEL PINO", True),
    ("ALVAREZ PENA, JOSE#2", True),             # el ordinal de la alineación no cuenta como palabra
    ("ALVAREZ PENA, JOSE#55329034", True),      # ni el id de la federación de 'NOMBRE#id'
    ("ALVAREZ, JOSE", False),                    # un solo apellido
    ("ALVAREZ PENA,", False),                    # nada detrás de la coma
    ("ALVAREZ PENA, ", False),
    ("LUCAS", False),                            # nombre de pila suelto
    ("ALVAREZ PENA JOSE", False),               # sin coma
    ("A.", False),
    ("H. G., G.", True),                         # dos apellidos en iniciales
    ("#SIN NOMBRE PUBLICADO", False),
    ("", False),
])
def test_nombre_completo(norm, esperado):
    assert nombre_completo(norm) is esperado


@pytest.mark.parametrize("equipo, esperado", [
    ("Tamaraceite", "tamaraceite"),
    ("Tamaraceite B", "tamaraceite"),
    ("Las Mesas Hu. C", "las mesas hu"),
    ("Las Mesas Hu.", "las mesas hu"),
    ("UD Atalaya B", "atalaya"),
    ("UD Atalaya", "atalaya"),
    ("Arucas CF", "arucas"),
    ('ARUCAS, C.F. "B"', "arucas"),
    ("RC Victoria E", "victoria"),               # siglas que normalizeForTeamsMapping no quita
    ("Gran Canaria F", "gran canaria f"),        # la letra de filial va de la A a la E, como en la web
    ("B", "b"),                                  # una sola palabra no pierde su letra
    ("", ""),
])
def test_club_es_el_nombre_sin_la_letra_de_filial(equipo, esperado):
    assert club(equipo) == esperado


def test_intervalo_de_edad():
    assert intervalo(2024, PRE) == (2017, 2019)
    assert intervalo(2024, BEN) == (2015, 2018)
    assert intervalo(2024, ALE) == (2013, 2016)


def test_compatibles_por_edad_y_solape():
    # Prebenjamín tres años seguidos cabe (nació en Y-5); cuatro, no.
    assert compatibles([v(2022, PRE, "X")], [v(2023, PRE, "X")], [v(2024, PRE, "X")])
    assert not compatibles([v(2022, PRE, "X")], [v(2023, PRE, "X")], [v(2024, PRE, "X")], [v(2025, PRE, "X")])
    # Misma temporada y categoría en dos clubes: imposible si las fechas se cruzan; seguidas, no.
    assert not compatibles([v(2024, PRE, "Arucas")], [v(2024, PRE, "Teror", ini="2025-03-01")])
    assert compatibles([v(2024, PRE, "Arucas", fin="2025-01-31")], [v(2024, PRE, "Teror", ini="2025-02-01")])
    # Dos equipos del mismo club a la vez sí (sube o baja de equipo).
    assert compatibles([v(2024, PRE, "Arucas")], [v(2024, PRE, "Arucas B")])
    # Sin fechas no se puede descartar el cruce: no se une.
    assert not compatibles([(2024, PRE, "Arucas", None, None, 3)], [v(2024, PRE, "Teror")])


# Clave pública y trozo. TABLA_CLAVES es la que copia la prueba de Node de la tarea 5:
# (fiflp_id, nombre normalizado, equipo, año de inicio, clave, trozo de 16).
TABLA_CLAVES = [
    (153432, "", "", 0, "153432", 8),
    (55329034, "", "", 0, "55329034", 10),
    (214080, "ALVAREZ PENA, JOSE", "Tamaraceite", 2023, "214080", 0),
    (1000017, "LUCAS", "Arucas", 2024, "1000017", 1),
    (None, "ALVAREZ PENA, JOSE", "Tamaraceite", 2024, "nisxwgmjvp", 5),
    (None, "ALVAREZ PENA, JOSE", "Tamaraceite", 2025, "ns8zin819i", 6),
    (None, "ALVAREZ PENA, JOSE", "Tamaraceite B", 2024, "nphzk2mnyf", 7),
    (None, "ALVAREZ PENA, JOSE#2", "Tamaraceite", 2024, "njkibiyk9d", 1),
    (None, "LUCAS", "Arucas", 2024, "n22zp0f76w", 8),
    (None, "LUCAS", "Arucas B", 2024, "n1ddjsy73e", 10),
    (None, "LUCAS", "Las Mesas Hu.", 2026, "nb6t8ejz2s", 4),
    (None, "LUCAS", "Las Mesas Hu. C", 2026, "n8qeq0zomr", 3),
    (None, "DE LA ROSA, MARIA DEL PINO", "UD Guía", 2026, "nccuo4q7lp", 13),
    (None, "DE LA ROSA, MARIA DEL PINO", "UD Guia", 2026, "ni6iou2qm2", 10),
    (None, "MUNOZ RUIZ, INIGO", "Unión Viera", 2025, "nc7n9df8hm", 10),
    (None, "H. G., G.", "UD Guía", 2026, "npp634adwo", 8),
    (None, "A.", "Santa Brígida", 2026, "n06wbfdyqg", 8),
    (None, "A.", "CD Calero", 2026, "nogme3ruur", 3),
    (None, "M.", "UD Atalaya", 2026, "nib8aqb17c", 8),
    (None, "D.", "Tamaraceite B", 2026, "njzprohv7i", 14),
    (None, "", "", 2026, "nlaihmii3x", 13),
    (None, "SANCHEZ, LEO", "Roque Amagro A", 2019, "ns9cly007v", 11),
]


@pytest.mark.parametrize("fiflp, norm, equipo, anio, clave, parte", TABLA_CLAVES)
def test_clave_publica_y_trozo(fiflp, norm, equipo, anio, clave, parte):
    assert clave_publica(fiflp, norm, equipo, anio) == clave
    assert trozo(clave) == parte


def test_clave_sin_id_es_el_sha1_en_base_36():
    import hashlib
    clave = clave_publica(None, "LUCAS", "Arucas", 2024)
    entero = int(hashlib.sha1("LUCAS|Arucas|2024".encode()).hexdigest(), 16)
    cifras = ""
    while entero:
        entero, resto = divmod(entero, 36)
        cifras = "0123456789abcdefghijklmnopqrstuvwxyz"[resto] + cifras
    assert clave == "n" + cifras.rjust(31, "0")[:9]
    assert len(clave) == 10 and clave[1:].isalnum() and clave[1:] == clave[1:].lower()
    assert trozo(clave) == int(clave[1:], 36) % 16
    assert trozo(clave, 4) == int(clave[1:], 36) % 4
    assert trozo("214080") == 214080 % 16


# ---------------------------------------------------------------------------
# U0: identificador de un solo uso
# ---------------------------------------------------------------------------

def test_u0_treinta_identificadores_de_un_solo_uso_son_un_nino():
    principal = ident(10, "ALVAREZ PENA, JOSE", 300000, v(2022, BEN, "Teror", n=20), v(2023, BEN, "Teror", n=18))
    sueltos = [ident(100 + k, f"ALVAREZ PENA, JOSE#{400000 + k}", 400000 + k,
                     v(2022 + k % 2, BEN, "Teror", n=1, ini=f"{2022 + k % 2}-11-0{1 + k % 9}",
                       fin=f"{2022 + k % 2}-11-0{1 + k % 9}"))
               for k in range(30)]
    r = resolver([principal] + sueltos, unir_cortos_en_club=False)
    assert r[10] == (10, None)
    assert all(r[s.id] == (10, "equipo") for s in sueltos)


def test_u0_otro_equipo_u_otra_temporada_no_une():
    a = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2022, BEN, "Teror"))
    b = ident(2, "ALVAREZ PENA, JOSE#300002", 300002, v(2022, BEN, "Arucas"))
    c = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2024, BEN, "Teror"))
    r = resolver([a, b, c], unir_cortos_en_club=True)
    assert len(fichas(r)) == 3


def test_u0_no_une_nombres_cortos():
    a = ident(1, "LUCAS", 300001, v(2022, BEN, "Teror", n=10))
    b = ident(2, "LUCAS#300002", 300002, v(2022, BEN, "Teror", n=1))
    r = resolver([a, b], unir_cortos_en_club=True)
    assert len(fichas(r)) == 2


def test_u0_une_el_goleador_sin_id_con_su_fila_con_id():
    # El goleador que no está en la alineación llega siempre sin id: mismo nombre completo, equipo y
    # temporada que la fila con id.
    con_id = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, BEN, "Teror", n=12))
    goleador = ident(2, "ALVAREZ PENA, JOSE", None, v(2024, BEN, "Teror", n=1))
    r = resolver([goleador, con_id], unir_cortos_en_club=False)
    assert r == {1: (1, None), 2: (1, "equipo")}


def test_u0_respeta_la_edad():
    # El mismo nombre en el mismo equipo y temporada, pero la otra fila trae una historia imposible
    # con la primera (alevín cinco años antes): no se une.
    a = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror", n=12))
    b = ident(2, "ALVAREZ PENA, JOSE#300002", 300002, v(2024, PRE, "Teror", n=1), v(2019, ALE, "Teror", n=9))
    r = resolver([a, b], unir_cortos_en_club=False)
    assert len(fichas(r)) == 2


# ---------------------------------------------------------------------------
# U1: mismo club, temporadas seguidas (identidades sin id)
# ---------------------------------------------------------------------------

def test_u1_une_un_completo_sin_id_en_temporadas_seguidas_del_club():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2024, PRE, "Tamaraceite B", n=8))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Tamaraceite", n=11))
    c = ident(3, "ALVAREZ PENA, JOSE", None, v(2026, PRE, "Tamaraceite C", n=4))
    otro = ident(4, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas", n=6))
    r = resolver([a, b, c, otro], unir_cortos_en_club=False)
    assert r[1] == (1, None) and r[2] == (1, "club") and r[3] == (1, "club")
    assert r[4] == (4, None)


def test_u1_cortos_segun_la_medida():
    a = ident(1, "LUCAS", None, v(2024, PRE, "Arucas", n=8))
    b = ident(2, "LUCAS", None, v(2025, PRE, "Arucas B", n=8))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=False))) == 2
    assert resolver([a, b], unir_cortos_en_club=True) == {1: (1, None), 2: (1, "club")}


def test_u1_no_salta_temporadas():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2023, PRE, "Teror"))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror"))
    c = ident(3, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas"))    # para que U2 no los una
    assert len(fichas(resolver([a, b, c], unir_cortos_en_club=True))) == 3


def test_u1_cuatro_prebenjamines_seguidos_no_caben():
    ids = [ident(k, "LUCAS", None, v(2022 + k, PRE, "Teror")) for k in range(4)]
    r = resolver(ids, unir_cortos_en_club=True)
    assert juntos(r, 0, 1, 2) and not juntos(r, 2, 3)


def test_u1_con_dos_candidatos_en_el_club_no_une():
    # Decisión: dos «LUCAS» del club al año siguiente (equipos A y B): no se sabe cuál es; unir los
    # tres mezclaría a dos niños de la misma temporada.
    a = ident(1, "LUCAS", None, v(2024, PRE, "Arucas"))
    b = ident(2, "LUCAS", None, v(2025, PRE, "Arucas"))
    c = ident(3, "LUCAS", None, v(2025, PRE, "Arucas B"))
    assert len(fichas(resolver([a, b, c], unir_cortos_en_club=True))) == 3


def test_u1_no_une_con_una_ficha_con_id():
    # Decisión: U1 es para identidades sin id. Un corto con id en el club al año siguiente no se lleva al
    # corto sin id (y un completo solo por U2, si es el único).
    a = ident(1, "LUCAS", None, v(2025, PRE, "Arucas"))
    b = ident(2, "LUCAS", 300002, v(2026, BEN, "Arucas"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_u1_respeta_la_edad():
    a = ident(1, "LUCAS", None, v(2025, ALE, "Arucas"))
    b = ident(2, "LUCAS", None, v(2026, PRE, "Arucas"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


# ---------------------------------------------------------------------------
# U2: candidata única (nombres completos)
# ---------------------------------------------------------------------------

def test_u2_una_candidata_une():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas", n=10))
    b = ident(2, "ALVAREZ PENA, JOSE", 300002, v(2027, BEN, "Teror", n=10))
    assert resolver([a, b], unir_cortos_en_club=False) == {1: (2, "nombre"), 2: (2, None)}


def test_u2_dos_candidatas_no_une():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas", n=10))
    b = ident(2, "ALVAREZ PENA, JOSE", 300002, v(2027, BEN, "Teror", n=10))
    c = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2026, BEN, "Galdar", n=10))
    assert len(fichas(resolver([a, b, c], unir_cortos_en_club=True))) == 3


def test_u2_una_candidata_incompatible_por_edad_no_une():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2026, PRE, "Arucas", n=10))
    b = ident(2, "ALVAREZ PENA, JOSE", 300002, v(2020, BEN, "Teror", n=10))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_u2_dos_sin_id_unicas_se_unen():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2024, BEN, "Arucas", n=1))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, BEN, "Teror", n=1))
    assert resolver([b, a], unir_cortos_en_club=False) == {1: (1, None), 2: (1, "nombre")}


def test_u2_dos_con_id_no_se_unen():
    a = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, BEN, "Arucas"))
    b = ident(2, "ALVAREZ PENA, JOSE#300002", 300002, v(2025, BEN, "Teror"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=False))) == 2


def test_u2_nunca_con_nombres_cortos():
    a = ident(1, "LUCAS", None, v(2025, PRE, "Arucas"))
    b = ident(2, "LUCAS", 300002, v(2026, BEN, "Teror"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_solape_imposible_no_une():
    # Mismo nombre completo, misma temporada y categoría, dos clubes, fechas que se cruzan.
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas", ini="2025-10-01", fin="2026-02-28"))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror", ini="2026-01-15", fin="2026-05-31"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2
    # Si una acaba antes de que empiece la otra (cambio de club a mitad de temporada), sí.
    b2 = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror", ini="2026-03-01", fin="2026-05-31"))
    assert len(fichas(resolver([a, b2], unir_cortos_en_club=True))) == 1


# ---------------------------------------------------------------------------
# El ordinal de la alineación (dos «X» sin id en el mismo equipo)
# ---------------------------------------------------------------------------

def test_dos_iguales_en_la_misma_alineacion_nunca_son_la_misma_ficha():
    x1 = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Arucas", n=10))
    x2 = ident(2, "ALVAREZ PENA, JOSE#2", None, v(2025, PRE, "Arucas", n=9))
    r = resolver([x1, x2], unir_cortos_en_club=True)
    assert len(fichas(r)) == 2
    # Y con una sola ficha más de ese nombre en otro sitio, no se sabe cuál de los dos es: no se une.
    otro = ident(3, "ALVAREZ PENA, JOSE", 300003, v(2026, BEN, "Teror", n=10))
    assert len(fichas(resolver([x1, x2, otro], unir_cortos_en_club=True))) == 3
    # Ni por U1 al año siguiente en el mismo club.
    sig = ident(4, "ALVAREZ PENA, JOSE", None, v(2026, PRE, "Arucas", n=10))
    assert len(fichas(resolver([x1, x2, sig], unir_cortos_en_club=True))) == 3


def test_la_fila_sin_nombre_publicado_no_se_une_nunca():
    anon = ident(1242, "#SIN NOMBRE PUBLICADO", None, v(2024, PRE, "Arucas"))
    otra = ident(5, "#SIN NOMBRE PUBLICADO", None, v(2025, PRE, "Arucas"))
    assert len(fichas(resolver([anon, otra], unir_cortos_en_club=True))) == 2


# ---------------------------------------------------------------------------
# Principal y union_por
# ---------------------------------------------------------------------------

def test_principal_la_de_id_con_mas_apariciones_y_a_igualdad_el_id_menor():
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2024, BEN, "Teror", n=30))
    b = ident(2, "ALVAREZ PENA, JOSE#500000", 500000, v(2024, BEN, "Teror", n=5))
    c = ident(3, "ALVAREZ PENA, JOSE#400000", 400000, v(2024, BEN, "Teror", n=5))
    r = resolver([a, b, c], unir_cortos_en_club=False)
    assert r == {1: (3, "equipo"), 2: (3, "equipo"), 3: (3, None)}


def test_principal_sin_id_la_mas_antigua():
    a = ident(7, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror", n=30))
    b = ident(9, "ALVAREZ PENA, JOSE", None, v(2024, PRE, "Teror", n=2))
    assert resolver([a, b], unir_cortos_en_club=False) == {7: (9, "club"), 9: (9, None)}
    # Misma temporada (cambio de club a mitad, unidas por U2): manda la de más apariciones y luego el id.
    c = ident(3, "SOSA VEGA, ANA", None, v(2025, PRE, "Teror", n=2, fin="2025-12-31"))
    d = ident(4, "SOSA VEGA, ANA", None, v(2025, PRE, "Arucas", n=5, ini="2026-01-10"))
    assert resolver([c, d], unir_cortos_en_club=False) == {3: (4, "nombre"), 4: (4, None)}
    d2 = ident(4, "SOSA VEGA, ANA", None, v(2025, PRE, "Arucas", n=2, ini="2026-01-10"))
    assert resolver([d2, c], unir_cortos_en_club=False) == {3: (3, None), 4: (3, "nombre")}


def test_union_por_es_la_union_que_lo_llevo_a_la_principal():
    # Dos sin id del club en temporadas seguidas (U1) y, después, la única otra ficha con ese nombre,
    # con id (U2): las dos sin id llegan a la principal por 'nombre'.
    a = ident(1, "ALVAREZ PENA, JOSE", None, v(2024, PRE, "Teror", n=10))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror", n=10))
    c = ident(3, "ALVAREZ PENA, JOSE", 300003, v(2026, BEN, "Arucas", n=10))
    d = ident(4, "ALVAREZ PENA, JOSE#300004", 300004, v(2026, BEN, "Arucas", n=1))
    r = resolver([a, b, c, d], unir_cortos_en_club=False)
    assert r == {1: (3, "nombre"), 2: (3, "nombre"), 3: (3, None), 4: (3, "equipo")}


def test_review_focus_2_el_nino_sin_id_que_al_ano_siguiente_lo_tiene():
    # Prebenjamín sin id en 2025-26 y benjamín con id en 2026-27, mismo club: una ficha, con la clave
    # numérica; la clave n… de antes es un alias de la misma ficha.
    sin = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror B", n=14))
    con = ident(2, "ALVAREZ PENA, JOSE", 300002, v(2026, BEN, "Teror", n=6))
    r = resolver([sin, con], unir_cortos_en_club=False)
    assert r == {1: (2, "nombre"), 2: (2, None)}
    assert clave_publica(con.fiflp_id, con.norm, "Teror", 2026) == "300002"
    alias = clave_publica(None, sin.norm, "Teror B", 2025)
    assert alias.startswith("n") and alias != "300002"


def test_review_focus_4_un_corto_en_dos_clubes():
    # «LUCAS» en dos clubes: dos fichas (y más), ninguna hereda el historial de otra de otros años.
    viejo = ident(1, "LUCAS", 300001, v(2021, PRE, "Arucas", n=10), v(2022, BEN, "Arucas", n=10))
    a24 = ident(2, "LUCAS", None, v(2024, PRE, "Arucas", n=8))
    a25 = ident(3, "LUCAS", None, v(2025, PRE, "Arucas", n=8))
    t25 = ident(4, "LUCAS", None, v(2025, PRE, "Teror", n=8))
    t26 = ident(5, "LUCAS", None, v(2026, PRE, "Teror", n=8))
    for cortos in (False, True):
        r = resolver([viejo, a24, a25, t25, t26], unir_cortos_en_club=cortos)
        assert r[1] == (1, None)
        assert not juntos(r, 2, 4) and not juntos(r, 3, 5) and not juntos(r, 3, 4)
        assert all(not juntos(r, 1, k) for k in (2, 3, 4, 5))
        assert juntos(r, 2, 3) is cortos and juntos(r, 4, 5) is cortos


# ---------------------------------------------------------------------------
# Los cinco ejemplos del mapa (D12), con lo que dirá el acta en la fase 2C: la parte con id, una
# identidad; lo de prebenjamín 2026-27, sin id.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cortos", [False, True])
def test_d12_los_cinco_ejemplos(cortos):
    e1 = ident(4472, "A.", 700001, v(2019, PRE, "Roque Amagro"), v(2020, PRE, "Roque Amagro"),
               v(2021, BEN, "Arucas"), v(2022, BEN, "Arucas"))
    e1_pre = ident(30001, "A.", None, v(2026, PRE, "Las Mesas Hu.", n=3))
    e2 = ident(1746, "D.", 700002, v(2024, BEN, "Tamaraceite"), v(2025, BEN, "Tamaraceite"),
               v(2026, ALE, "Las Mesas Hu. C"))
    e2_pre = ident(30002, "D.", None, v(2026, PRE, "Tamaraceite B"))
    e3 = ident(19911, "M.", 700003, v(2019, BEN, "Universitario"))
    e3_pre = ident(30003, "M.", None, v(2026, PRE, "UD Atalaya"))
    e4 = ident(22560, "H. G., G.", 700004, v(2020, BEN, "UD Tarajalejo"))
    e4_pre = ident(30004, "H. G., G.", None, v(2026, PRE, "UD Guía"))
    e5 = ident(4891, "A.#700005", 700005, v(2022, BEN, "LasTorres"))
    e5_pre1 = ident(30005, "A.", None, v(2026, PRE, "Santa Brígida"))
    e5_pre2 = ident(30006, "A.", None, v(2026, PRE, "CD Calero"))
    todas = [e1, e1_pre, e2, e2_pre, e3, e3_pre, e4, e4_pre, e5, e5_pre1, e5_pre2]
    r = resolver(todas, unir_cortos_en_club=cortos)
    # Nadie se une a nadie: cada niño de prebenjamín 2026-27 tiene su ficha y ninguna ficha con id
    # recibe partidos imposibles.
    assert all(r[i.id] == (i.id, None) for i in todas)


def test_d12_ejemplo_4_con_edad_posible_si_se_uniria():
    # El mismo caso que el ejemplo 4 con un año compatible: U2 lo une (lo que lo impide es la edad).
    e4 = ident(22560, "H. G., G.", 700004, v(2025, BEN, "UD Tarajalejo"))
    e4_pre = ident(30004, "H. G., G.", None, v(2024, PRE, "UD Guía"))
    assert resolver([e4, e4_pre], unir_cortos_en_club=False)[30004] == (22560, "nombre")


# ---------------------------------------------------------------------------
# Propiedades: orden, punto fijo, tamaño
# ---------------------------------------------------------------------------

EQUIPOS = ["Arucas", "Arucas B", "Teror", "Teror B", "Teror C", "Galdar", "UD Guía", "Tamaraceite"]
NOMBRES = ["LUCAS", "TEO", "ALVAREZ PENA, JOSE", "RUANO MESA, LEO", "SOSA VEGA, ANA", "PEREZ, IKER",
           "DIAZ DIAZ, HUGO", "MARRERO LEON, PAULA"]


# Muchos nombres poco repetidos: ahí trabajan U1 y U2 (con muchos homónimos, casi solo U0).
VARIADOS = ([f"APELLIDO{k} OTRO{k % 7}, NOMBRE{k % 5}" for k in range(300)] +
            [f"CORTO{k}" for k in range(150)])


def sinteticas(n, semilla, nombres=NOMBRES, equipos=EQUIPOS, desde=0):
    """n identidades con muchos homónimos, ids de la federación, filas de un solo uso y ordinales."""
    rnd = random.Random(semilla)
    out, vistas_vistas = [], set()
    for k in range(n):
        nombre = rnd.choice(nombres)
        anio = rnd.randint(2019, 2026)
        nivel = rnd.choice((PRE, PRE, BEN, ALE))
        equipo = rnd.choice(equipos)
        fiflp = 900000 + desde + k if rnd.random() < 0.6 else None
        mes = rnd.randint(10, 12)
        vistas = [v(anio, nivel, equipo, n=rnd.randint(1, 20), ini=f"{anio}-{mes}-01")]
        if fiflp and rnd.random() < 0.5:
            vistas.append(v(anio + 1, min(nivel + rnd.randint(0, 1), ALE), rnd.choice(equipos), n=rnd.randint(1, 20)))
        norm = nombre
        if fiflp is None:
            clave = (nombre, equipo, anio)
            while clave in vistas_vistas:         # una identidad sin id por nombre, equipo y temporada
                norm = f"{nombre}#{int(norm.split('#')[1]) + 1 if '#' in norm else 2}"
                clave = (norm, equipo, anio)
            vistas_vistas.add(clave)
        elif rnd.random() < 0.5:
            norm = f"{nombre}#{fiflp}"
        out.append(Identidad(id=desde + k + 1, norm=norm, fiflp_id=fiflp, vistas=tuple(vistas)))
    return out


def mezcla(semilla):
    return sinteticas(1500, semilla) + sinteticas(1500, semilla + 1, nombres=VARIADOS, desde=1500)


def test_las_mezclas_tienen_uniones_de_las_tres_reglas():
    for cortos in (False, True):
        for semilla in (7, 11):
            reglas = {u for _, u in resolver(mezcla(semilla), unir_cortos_en_club=cortos).values()}
            assert reglas == {None, "equipo", "club", "nombre"}


@pytest.mark.parametrize("cortos", [False, True])
def test_no_depende_del_orden_de_entrada(cortos):
    base = mezcla(7)
    esperado = resolver(base, unir_cortos_en_club=cortos)
    for semilla in range(3):
        barajadas = list(base)
        random.Random(semilla).shuffle(barajadas)
        assert resolver(barajadas, unir_cortos_en_club=cortos) == esperado


@pytest.mark.parametrize("cortos", [False, True])
def test_resolver_su_propio_resultado_no_cambia_nada(cortos):
    base = mezcla(11)
    r = resolver(base, unir_cortos_en_club=cortos)
    assert resolver(base, unir_cortos_en_club=cortos) == r
    # Cada ficha como una sola identidad (la principal con todas las vistas de la ficha): ninguna regla
    # une ya nada.
    por_id = {i.id: i for i in base}
    juntas = {}
    for i, (p, _) in r.items():
        juntas.setdefault(p, []).extend(por_id[i].vistas)
    fichas_como_identidad = [Identidad(id=p, norm=por_id[p].norm, fiflp_id=por_id[p].fiflp_id,
                                       vistas=tuple(vs)) for p, vs in juntas.items()]
    otra = resolver(fichas_como_identidad, unir_cortos_en_club=cortos)
    assert otra == {p: (p, None) for p in juntas}


def test_cada_identidad_sale_una_vez_y_la_principal_se_apunta_a_si_misma():
    base = mezcla(3)
    r = resolver(base, unir_cortos_en_club=True)
    assert set(r) == {i.id for i in base}
    for i, (p, por) in r.items():
        assert r[p] == (p, None)
        assert (por is None) == (i == p)
        assert por in (None, "equipo", "club", "nombre")


def test_ids_repetidos_abortan():
    a = ident(1, "LUCAS", None, v(2024, PRE, "Arucas"))
    with pytest.raises(ValueError):
        resolver([a, a], unir_cortos_en_club=False)


def test_veinte_mil_identidades_en_menos_de_diez_segundos():
    # Nombres de un universo grande (como la base: la mayoría casi únicos, algunos muy repetidos).
    nombres = [f"APELLIDO{k} OTRO{k % 97}, NOMBRE{k % 13}" for k in range(6000)] + ["LUCAS", "TEO", "HUGO"] * 50
    equipos = [f"Club {k}" + (" B" if k % 3 == 0 else "") for k in range(400)]
    base = sinteticas(20000, 5, nombres=nombres, equipos=equipos)
    t0 = time.perf_counter()
    r = resolver(base, unir_cortos_en_club=True)
    assert time.perf_counter() - t0 < 10
    assert len(r) == 20000


# ---------------------------------------------------------------------------
# La medida de los cortos (scripts/medir_identidad.py)
# ---------------------------------------------------------------------------

def test_la_medida_cuenta_los_pares_de_u1():
    import medir_identidad as M
    f = lambda fid, norm, anio, equipo, nivel=PRE, fecha=None: (fid, norm, anio, nivel, equipo,  # noqa: E731
                                                                 fecha or f"{anio}-11-01")
    filas = [
        # Un corto que sigue en el club (A → B): mismo niño.
        f(1, "LUCAS", 2020, "Arucas"), f(1, "LUCAS", 2021, "Arucas B"),
        # Otro corto con el mismo nombre en el club al año siguiente: distinto.
        f(2, "LUCAS", 2021, "Arucas"),
        # Un completo que sigue, y uno de un solo uso en su equipo (U0 lo une: mismo niño).
        f(3, "SOSA VEGA, ANA", 2020, "Teror"), f(3, "SOSA VEGA, ANA", 2021, "Teror"),
        f(3, "SOSA VEGA, ANA", 2021, "Teror", fecha="2021-12-01"), f(4, "SOSA VEGA, ANA", 2021, "Teror"),
        # Otro club, o imposible por edad: no es un par.
        f(5, "TEO", 2020, "Galdar"), f(6, "TEO", 2021, "Arucas"),
        f(7, "PEREZ, IKER", 2020, "Galdar", nivel=ALE), f(8, "PEREZ, IKER", 2021, "Galdar"),
    ]
    nino = M.ninos(filas)
    assert nino[3] == nino[4] and nino[1] != nino[2]
    medida = M.pares(filas, nino)
    assert medida[("todos", "cortos")] == {"mismo": 1, "distinto": 1}
    assert medida[("todos", "completos")] == {"mismo": 1}
    # Uno a uno: dos LUCAS del club en 2021, no cuenta; ANA sí (una identidad sin id con los dos ids).
    assert medida[("uno a uno", "cortos")] == {}
    assert medida[("uno a uno", "completos")] == {"mismo": 1}
    texto, decision = M.informe(Counter(), nino, medida)
    assert decision is False and "unir_cortos_en_club = False" in texto
