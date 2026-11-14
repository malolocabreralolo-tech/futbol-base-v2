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

from identidad import (UNIR_CORTOS_EN_CLUB, Identidad, NIVEL, club, clave_publica, compatibles, intervalo,
                       nombre_completo, nombre_con_coma, normalizar, resolver, resumen_u0_cortos, trozo)
import identidad
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


# U0 de nombres cortos (ronda de arreglo 1): con id, mismo nombre corto, equipo y temporada; las de una
# sola aparición en total van a la única asentada del cubo.

def corto_con_id(id_, fiflp, n, anio=2022, equipo="Teror", nombre="LUCAS", nivel=BEN, *mas):
    return ident(id_, f"{nombre}#{fiflp}" if id_ % 2 else nombre, fiflp,
                 v(anio, nivel, equipo, n=n, ini=f"{anio}-11-{1 + id_ % 28:02d}",
                   fin=f"{anio}-11-{1 + id_ % 28:02d}" if n == 1 else None), *mas)


def test_u0_cortos_una_asentada_y_quince_de_un_solo_uso_son_un_nino():
    asentada = corto_con_id(1, 300001, 12)
    sueltas = [corto_con_id(10 + k, 400000 + k, 1) for k in range(15)]
    r = resolver([asentada] + sueltas, unir_cortos_en_club=False)
    assert fichas(r) == {1: frozenset([1] + [s.id for s in sueltas])}
    assert all(r[s.id] == (1, "equipo") for s in sueltas)


def test_u0_cortos_dos_asentadas_no_une_ninguna():
    # Dos niños con el mismo nombre de pila en el equipo: no se sabe de cuál es cada suelta.
    todas = [corto_con_id(1, 300001, 12), corto_con_id(2, 300002, 7)] + \
        [corto_con_id(10 + k, 400000 + k, 1) for k in range(3)]
    assert len(fichas(resolver(todas, unir_cortos_en_club=True))) == 5


def test_u0_cortos_todas_de_un_solo_uso_no_une():
    todas = [corto_con_id(10 + k, 400000 + k, 1) for k in range(4)]
    r = resolver(todas, unir_cortos_en_club=True)
    assert all(r[i.id] == (i.id, None) for i in todas)


def test_u0_cortos_un_solo_uso_cuenta_las_apariciones_de_todas_las_vistas():
    # Una aparición aquí y otra en otro equipo son dos: es otra asentada, y con dos no se une nada.
    asentada = corto_con_id(1, 300001, 12)
    dos_vistas = corto_con_id(2, 300002, 1, 2022, "Teror", "LUCAS", BEN, v(2023, BEN, "Arucas", n=1))
    suelta = corto_con_id(11, 400011, 1)
    assert len(fichas(resolver([asentada, dos_vistas, suelta], unir_cortos_en_club=False))) == 3


def test_u0_cortos_la_incompatible_por_edad_no_se_une():
    # La asentada jugó benjamín en 2022 y prebenjamín en 2023 (nació en 2016); una suelta de alevín en
    # 2022 (2011-2014) no cabe; otra de benjamín, sí.
    asentada = corto_con_id(1, 300001, 12, 2022, "Teror", "LUCAS", BEN, v(2023, PRE, "Arucas", n=9))
    mala = corto_con_id(11, 400011, 1, 2022, "Teror", "LUCAS", ALE)
    buena = corto_con_id(13, 400013, 1)
    r = resolver([mala, asentada, buena], unir_cortos_en_club=False)
    assert r[13] == (1, "equipo") and r[11] == (11, None)


def test_u0_cortos_otro_equipo_u_otra_temporada_no_une():
    asentada = corto_con_id(1, 300001, 12)
    otra_temporada = corto_con_id(11, 400011, 1, 2023)
    otro_equipo = corto_con_id(13, 400013, 1, 2022, "Teror B")
    assert len(fichas(resolver([asentada, otra_temporada, otro_equipo], unir_cortos_en_club=False))) == 3


def test_u0_cortos_sin_id_no_entran():
    asentada = corto_con_id(1, 300001, 12)
    sin_id = ident(2, "LUCAS", None, v(2022, BEN, "Teror", n=1))
    assert len(fichas(resolver([asentada, sin_id], unir_cortos_en_club=True))) == 2


def test_u0_un_nombre_completo_sigue_la_u0_normal():
    # Con dos asentadas, la variante de los cortos no uniría nada; un nombre completo une las cinco.
    todas = [corto_con_id(1, 300001, 12, nombre="SOSA VEGA, ANA"), corto_con_id(2, 300002, 7, nombre="SOSA VEGA, ANA")] + \
        [corto_con_id(10 + k, 400000 + k, 1, nombre="SOSA VEGA, ANA") for k in range(3)]
    assert len(fichas(resolver(todas, unir_cortos_en_club=False))) == 1


def test_u0_cortos_resumen_de_los_cubos():
    una = [corto_con_id(1, 300001, 12)] + [corto_con_id(10 + k, 400000 + k, 1) for k in range(2)]
    dos = [corto_con_id(3, 300003, 5, equipo="Galdar"), corto_con_id(5, 300005, 5, equipo="Galdar"),
           corto_con_id(21, 400021, 1, equipo="Galdar")]
    ninguna = [corto_con_id(31 + k, 400031 + k, 1, equipo="Arucas") for k in range(3)]
    sola = [corto_con_id(41, 400041, 1, equipo="Moya")]           # una suelta sola: nada que unir
    assert resumen_u0_cortos(una + dos + ninguna + sola) == {
        "una asentada": 1, "dos o más asentadas": 1, "ninguna asentada": 1}


@pytest.mark.parametrize("cortos", [False, True])
def test_u0_cortos_barajado_y_punto_fijo(cortos):
    casos = ([corto_con_id(1, 300001, 12)] + [corto_con_id(10 + k, 400000 + k, 1) for k in range(15)] +
             [corto_con_id(101, 300101, 12, equipo="Galdar"), corto_con_id(102, 300102, 7, equipo="Galdar")] +
             [corto_con_id(110 + k, 400110 + k, 1, equipo="Galdar") for k in range(3)] +
             [corto_con_id(201 + k, 400201 + k, 1, equipo="Arucas") for k in range(4)] +
             [corto_con_id(301, 300301, 12, 2022, "Moya", "LUCAS", BEN, v(2023, PRE, "Arucas", n=9)),
              corto_con_id(311, 400311, 1, 2022, "Moya", "LUCAS", ALE), corto_con_id(313, 400313, 1, 2022, "Moya")])
    esperado = resolver(casos, unir_cortos_en_club=cortos)
    assert len(fichas(esperado)) == 1 + 5 + 4 + 2
    for semilla in range(5):
        barajados = list(casos)
        random.Random(semilla).shuffle(barajados)
        assert resolver(barajados, unir_cortos_en_club=cortos) == esperado
    assert punto_fijo(casos, esperado, cortos)


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


@pytest.mark.parametrize("cortos", [False, True])
def test_u1_corto_sin_coma_sin_id_y_con_id_segun_el_interruptor(cortos):
    # Ronda 2: U1 une una ficha sin id con una con id; para los nombres sin coma manda el interruptor.
    a = ident(1, "LUCAS", None, v(2025, PRE, "Arucas"))
    b = ident(2, "LUCAS", 300002, v(2026, BEN, "Arucas B"))
    r = resolver([a, b], unir_cortos_en_club=cortos)
    assert r == ({1: (2, "club"), 2: (2, None)} if cortos else {1: (1, None), 2: (2, None)})


def test_u1_respeta_la_edad():
    a = ident(1, "LUCAS", None, v(2025, ALE, "Arucas"))
    b = ident(2, "LUCAS", None, v(2026, PRE, "Arucas"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


# ---------------------------------------------------------------------------
# Ronda de arreglo 2: U0 con un apellido y U1 entre una ficha sin id y una con id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("norm, esperado", [
    ("ALVAREZ, JOSE", True), ("ALVAREZ PENA, JOSE", True), ("ALVAREZ, JOSE#2", True), ("ALVAREZ,", False),
    (", JOSE", False), ("LUCAS", False), ("ALVAREZ JOSE", False), ("", False),
])
def test_nombre_con_coma(norm, esperado):
    assert nombre_con_coma(norm) is esperado


def test_u0_un_apellido_con_38_de_un_solo_uso_es_un_nino():
    # Con un solo apellido no hay asentada: las 39 son de un partido y U0 normal las junta.
    todas = [ident(1 + k, "ROSALES, TEO" if k == 0 else f"ROSALES, TEO#{500000 + k}", 500000 + k,
                   v(2021, BEN, "Teror", n=1, ini=f"2021-{10 + k % 3}-{1 + k % 28:02d}",
                     fin=f"2021-{10 + k % 3}-{1 + k % 28:02d}")) for k in range(39)]
    r = resolver(todas, unir_cortos_en_club=False)
    assert len(fichas(r)) == 1
    assert sorted(u for _, u in r.values() if u) == ["equipo"] * 38


def test_u0_un_apellido_en_dos_equipos_son_dos_fichas():
    # Y U2 no las junta: es para dos apellidos.
    a = ident(1, "ROSALES, TEO", 500001, v(2021, BEN, "Teror"))
    b = ident(2, "ROSALES, TEO", None, v(2022, BEN, "Galdar"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_u1_completo_sin_id_y_con_id_al_ano_siguiente_en_el_club():
    # Hay otra ficha con ese nombre en otro club: U2 no podía; U1 sí.
    sin = ident(1, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror B", n=14))
    con = ident(2, "ALVAREZ PENA, JOSE", 300002, v(2026, BEN, "Teror", n=6))
    otro = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2026, BEN, "Galdar", n=9))
    r = resolver([sin, con, otro], unir_cortos_en_club=False)
    assert r == {1: (2, "club"), 2: (2, None), 3: (3, None)}


def test_u1_con_id_y_sin_id_al_ano_siguiente_en_el_club():
    con = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror", n=10))
    sin = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror B", n=8))
    otro = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2025, PRE, "Galdar", n=9))
    r = resolver([sin, otro, con], unir_cortos_en_club=False)
    assert r == {1: (1, None), 2: (1, "club"), 3: (3, None)}


def test_u1_un_apellido_sin_id_y_con_id_sin_interruptor():
    # Un apellido lleva coma: U1 lo une aunque los cortos sin coma no se unan.
    sin = ident(1, "ROSALES, TEO", None, v(2025, PRE, "Teror", n=14))
    con = ident(2, "ROSALES, TEO", 300002, v(2026, BEN, "Teror", n=6))
    assert resolver([sin, con], unir_cortos_en_club=False) == {1: (2, "club"), 2: (2, None)}


def test_u1_con_id_y_con_id_no_se_unen():
    a = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror"))
    b = ident(2, "ALVAREZ PENA, JOSE#300002", 300002, v(2025, PRE, "Teror"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_u1_con_id_dos_fichas_del_nombre_en_el_club_no_une():
    # Sin coma (la U0 de club no los toca): dos «LUCAS» del club en 2025 → U1 no sabe cuál es.
    con = ident(1, "LUCAS", 300001, v(2024, PRE, "Teror"))
    sin_a = ident(2, "LUCAS", None, v(2025, PRE, "Teror"))
    sin_b = ident(3, "LUCAS", None, v(2025, PRE, "Teror B"))
    assert len(fichas(resolver([con, sin_a, sin_b], unir_cortos_en_club=True))) == 3
    # También si la segunda del club tiene id.
    con_b = ident(3, "LUCAS#300003", 300003, v(2025, PRE, "Teror B"))
    assert len(fichas(resolver([con, sin_a, con_b], unir_cortos_en_club=True))) == 3


def test_u1_con_coma_tras_la_u0_de_club():
    # Con coma, las dos sin id de 2025 (Teror y Teror B) ya son una por la U0 de club (ronda 3), y U1 la une
    # con la de 2024. Con dos con id en el cubo de 2025, nada.
    con = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror"))
    sin_a = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror"))
    sin_b = ident(3, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror B"))
    assert resolver([con, sin_a, sin_b], unir_cortos_en_club=False) == {1: (1, None), 2: (1, "club"), 3: (1, "club")}
    con_b = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2025, PRE, "Teror B"))
    con_c = ident(4, "ALVAREZ PENA, JOSE#300004", 300004, v(2025, PRE, "Teror C"))
    assert len(fichas(resolver([con, sin_a, con_b, con_c], unir_cortos_en_club=True))) == 4


def test_u1_no_lleva_dos_ids_a_la_misma_ficha_por_una_sin_id():
    # Con id (2024) → sin id (2025) → con id (2026), todo en el club: la sin id puede ser de cualquiera de
    # los dos niños con id (dos ids son dos niños): no se une a ninguno.
    a = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror", n=9))
    b = ident(2, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror", n=9))
    c = ident(3, "ALVAREZ PENA, JOSE#300003", 300003, v(2026, PRE, "Teror", n=9))
    r = resolver([a, b, c], unir_cortos_en_club=True)
    assert r == {1: (1, None), 2: (2, None), 3: (3, None)}


def test_u1_con_id_respeta_el_ordinal_y_la_edad():
    con = ident(1, "ALVAREZ PENA, JOSE", 300001, v(2024, PRE, "Teror"))
    ordinal = ident(2, "ALVAREZ PENA, JOSE#2", None, v(2025, PRE, "Galdar"))
    sin = ident(3, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Galdar"))
    con_g = ident(4, "ALVAREZ PENA, JOSE#300004", 300004, v(2024, PRE, "Galdar"))
    assert len(fichas(resolver([con, ordinal, sin, con_g], unir_cortos_en_club=True))) == 4
    viejo = ident(5, "SOSA VEGA, ANA", 300005, v(2024, ALE, "Teror"))
    nuevo = ident(6, "SOSA VEGA, ANA", None, v(2025, PRE, "Teror"))
    otra = ident(7, "SOSA VEGA, ANA#300007", 300007, v(2025, PRE, "Galdar"))
    assert len(fichas(resolver([viejo, nuevo, otra], unir_cortos_en_club=True))) == 3


def casos_ronda_2():
    return [
        *[ident(1 + k, "ROSALES, TEO" if k == 0 else f"ROSALES, TEO#{500000 + k}", 500000 + k,
                v(2021, BEN, "Teror", n=1, ini=f"2021-11-{1 + k % 28:02d}", fin=f"2021-11-{1 + k % 28:02d}"))
          for k in range(39)],
        ident(101, "ROSALES, IVO", 600101, v(2021, BEN, "Teror")), ident(102, "ROSALES, IVO", None, v(2022, BEN, "Galdar")),
        ident(201, "ALVAREZ PENA, JOSE", None, v(2025, PRE, "Teror B", n=14)),
        ident(202, "ALVAREZ PENA, JOSE", 300202, v(2026, BEN, "Teror", n=6)),
        ident(203, "ALVAREZ PENA, JOSE#300203", 300203, v(2026, BEN, "Galdar", n=9)),
        ident(301, "SOSA VEGA, ANA", 300301, v(2024, PRE, "Moya", n=10)),
        ident(302, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya B", n=8)),
        ident(303, "SOSA VEGA, ANA#300303", 300303, v(2025, PRE, "Galdar", n=9)),
        ident(401, "MESA LUIS, IKER", 300401, v(2024, PRE, "Moya")),
        ident(402, "MESA LUIS, IKER#300402", 300402, v(2025, PRE, "Moya")),
        ident(501, "MESA LUIS, ABEL", 300501, v(2024, PRE, "Moya")),
        ident(502, "MESA LUIS, ABEL", None, v(2025, PRE, "Moya")), ident(503, "MESA LUIS, ABEL", None, v(2025, PRE, "Moya B")),
        ident(601, "LUCAS", None, v(2025, PRE, "Arucas")), ident(602, "LUCAS", 300602, v(2026, BEN, "Arucas B")),
        ident(701, "RUANO MESA, LEO", 300701, v(2024, PRE, "Teror", n=9)),
        ident(702, "RUANO MESA, LEO", None, v(2025, PRE, "Teror", n=9)),
        ident(703, "RUANO MESA, LEO#300703", 300703, v(2026, PRE, "Teror", n=9)),
    ]


@pytest.mark.parametrize("cortos", [False, True])
def test_ronda_2_barajado_y_punto_fijo(cortos):
    casos = casos_ronda_2()
    esperado = resolver(casos, unir_cortos_en_club=cortos)
    assert len(fichas(esperado)) == 1 + 2 + 2 + 2 + 2 + 1 + (1 if cortos else 2) + 3   # ABEL: U0 de club
    for semilla in range(5):
        barajados = list(casos)
        random.Random(semilla).shuffle(barajados)
        assert resolver(barajados, unir_cortos_en_club=cortos) == esperado
    assert punto_fijo(casos, esperado, cortos)


# ---------------------------------------------------------------------------
# Ronda de arreglo 3: U0 de club (mismo nombre con coma, mismo club, misma temporada)
# ---------------------------------------------------------------------------

def otro_lado(id_, norm, fiflp=None):
    """Una ficha más con ese nombre en otro club y otra temporada, para que U2 no pueda unir."""
    return ident(id_, norm if fiflp is None else f"{norm}#{fiflp}", fiflp, v(2019, BEN, "Lejos FC"))


def caso_real():
    # 2024-25 prebenjamín sin id; 2025-26 prebenjamín sin id y un partido en el benjamín B con id; 2026-27
    # benjamín de otro club con ese id.
    return [ident(1, "SOSA VEGA, ANA", None, v(2024, PRE, "Moya", n=19)),
            ident(2, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya", n=15)),
            ident(3, "SOSA VEGA, ANA", 300003, v(2025, BEN, "Moya B", n=1), v(2026, BEN, "Teror", n=20))]


def test_u0_club_el_caso_real_es_una_ficha_con_la_principal_del_id():
    r = resolver(caso_real(), unir_cortos_en_club=False)
    assert r == {1: (3, "club"), 2: (3, "club"), 3: (3, None)}


def test_u0_club_dos_sin_id_en_x_y_x_b_son_una():
    a = ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya", n=9))
    b = ident(2, "SOSA VEGA, ANA", None, v(2025, BEN, "Moya B", n=3))
    r = resolver([a, b, otro_lado(3, "SOSA VEGA, ANA", 300003)], unir_cortos_en_club=False)
    assert r == {1: (1, None), 2: (1, "club"), 3: (3, None)}


def test_u0_club_un_apellido_tambien():
    a = ident(1, "ROSALES, TEO", None, v(2025, PRE, "Moya", n=9))
    b = ident(2, "ROSALES, TEO", 300002, v(2025, BEN, "Moya B", n=3))
    assert resolver([a, b], unir_cortos_en_club=False) == {1: (2, "club"), 2: (2, None)}


def test_u0_club_una_sin_id_y_dos_con_id_no_une_nada():
    sin = ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya"))
    a = ident(2, "SOSA VEGA, ANA", 300002, v(2025, BEN, "Moya B"))
    b = ident(3, "SOSA VEGA, ANA#300003", 300003, v(2025, BEN, "Moya C"))
    r = resolver([sin, a, b], unir_cortos_en_club=True)
    assert all(r[k] == (k, None) for k in (1, 2, 3))


def test_u0_club_sin_coma_no():
    a = ident(1, "LUCAS", None, v(2025, PRE, "Moya"))
    b = ident(2, "LUCAS", 300002, v(2025, BEN, "Moya B"))
    assert len(fichas(resolver([a, b], unir_cortos_en_club=True))) == 2


def test_u0_club_con_ordinal_no():
    a = ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya"))
    a2 = ident(2, "SOSA VEGA, ANA#2", None, v(2025, PRE, "Moya"))
    b = ident(3, "SOSA VEGA, ANA", None, v(2025, BEN, "Moya B"))
    assert len(fichas(resolver([a, a2, b], unir_cortos_en_club=True))) == 3


def test_u0_club_incompatibles_por_edad_no_y_la_que_cabe_si():
    # Prebenjamín y benjamín B caben (nacido en 2018 o 2019); alevín C, no.
    a = ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya", n=9))
    b = ident(2, "SOSA VEGA, ANA", None, v(2025, BEN, "Moya B", n=5))
    c = ident(3, "SOSA VEGA, ANA", None, v(2025, ALE, "Moya C", n=7))
    r = resolver([c, b, a, otro_lado(4, "SOSA VEGA, ANA", 300004)], unir_cortos_en_club=False)
    assert r[1] == (1, None) and r[2] == (1, "club") and r[3] == (3, None)


def test_u0_club_otro_club_no():
    a = ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya", fin="2025-12-31"))
    b = ident(2, "SOSA VEGA, ANA", None, v(2025, BEN, "Teror", ini="2026-01-10"))
    r = resolver([a, b, otro_lado(3, "SOSA VEGA, ANA", 300003)], unir_cortos_en_club=False)
    assert len(fichas(r)) == 3


def test_u0_club_otra_temporada_no_es_u0_club():
    # Dos temporadas del club son de U1, no de esta regla (con un tercero en el club, U1 no puede).
    a = ident(1, "SOSA VEGA, ANA", None, v(2024, PRE, "Moya"))
    b = ident(2, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya B"))
    c = ident(3, "SOSA VEGA, ANA#300003", 300003, v(2025, BEN, "Moya C"))
    d = ident(4, "SOSA VEGA, ANA#300004", 300004, v(2025, BEN, "Moya"))
    assert len(fichas(resolver([a, b, c, d], unir_cortos_en_club=False))) == 4


@pytest.mark.parametrize("constante", ["U0_CLUB_COMPLETOS", "U0_CLUB_UN_APELLIDO"])
def test_u0_club_cada_tipo_detras_de_su_constante(monkeypatch, constante):
    completos = [ident(1, "SOSA VEGA, ANA", None, v(2025, PRE, "Moya")),
                 ident(2, "SOSA VEGA, ANA", None, v(2025, BEN, "Moya B")), otro_lado(3, "SOSA VEGA, ANA", 300003)]
    apellido = [ident(11, "ROSALES, TEO", None, v(2025, PRE, "Moya")),
                ident(12, "ROSALES, TEO", 300012, v(2025, BEN, "Moya B"))]
    monkeypatch.setattr(identidad, constante, False)
    r = resolver(completos + apellido, unir_cortos_en_club=False)
    assert juntos(r, 1, 2) is (constante != "U0_CLUB_COMPLETOS")
    assert juntos(r, 11, 12) is (constante != "U0_CLUB_UN_APELLIDO")


def casos_ronda_3():
    out = caso_real()
    grupos = [
        [ident(11, "MARRERO LEON, PAULA", None, v(2025, PRE, "Moya", n=9)),
         ident(12, "MARRERO LEON, PAULA", None, v(2025, BEN, "Moya B", n=3)), otro_lado(13, "MARRERO LEON, PAULA", 300013)],
        [ident(21, "ROSALES, TEO", None, v(2025, PRE, "Moya", n=9)), ident(22, "ROSALES, TEO", 300022, v(2025, BEN, "Moya B"))],
        [ident(31, "RUANO MESA, LEO", None, v(2025, PRE, "Galdar")), ident(32, "RUANO MESA, LEO", 300032, v(2025, BEN, "Galdar B")),
         ident(33, "RUANO MESA, LEO#300033", 300033, v(2025, BEN, "Galdar C"))],
        [ident(41, "LUCAS", None, v(2025, PRE, "Moya")), ident(42, "LUCAS", 300042, v(2025, BEN, "Moya B"))],
        [ident(51, "DIAZ DIAZ, HUGO", None, v(2025, PRE, "Moya")), ident(52, "DIAZ DIAZ, HUGO#2", None, v(2025, PRE, "Moya")),
         ident(53, "DIAZ DIAZ, HUGO", None, v(2025, BEN, "Moya B"))],
        [ident(61, "MESA LUIS, ABEL", None, v(2025, PRE, "Teror", n=9)), ident(62, "MESA LUIS, ABEL", None, v(2025, BEN, "Teror B", n=5)),
         ident(63, "MESA LUIS, ABEL", None, v(2025, ALE, "Teror C", n=7)), otro_lado(64, "MESA LUIS, ABEL", 300064)],
    ]
    return out + [i for g in grupos for i in g]


@pytest.mark.parametrize("cortos", [False, True])
def test_ronda_3_barajado_y_punto_fijo(cortos):
    casos = casos_ronda_3()
    esperado = resolver(casos, unir_cortos_en_club=cortos)
    assert juntos(esperado, 11, 12) and not juntos(esperado, 11, 13)
    assert juntos(esperado, 1, 2, 3) and juntos(esperado, 21, 22) and not juntos(esperado, 41, 42)
    assert len({esperado[k][0] for k in (31, 32, 33)}) == 3 and len({esperado[k][0] for k in (51, 52, 53)}) == 3
    assert juntos(esperado, 61, 62) and not juntos(esperado, 61, 63)
    for semilla in range(5):
        barajados = list(casos)
        random.Random(semilla).shuffle(barajados)
        assert resolver(barajados, unir_cortos_en_club=cortos) == esperado
    assert punto_fijo(casos, esperado, cortos)


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
    assert r == {1: (2, "club"), 2: (2, None)}         # el mismo club: U1 (ronda 2) antes que U2
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
    assert punto_fijo(base, r, cortos)


def punto_fijo(base, r, cortos):
    """Cada ficha como una sola identidad (la principal con todas las vistas de la ficha): ¿no une ya
    nada ninguna regla?"""
    por_id = {i.id: i for i in base}
    juntas = {}
    for i, (p, _) in r.items():
        juntas.setdefault(p, []).extend(por_id[i].vistas)
    fichas_como_identidad = [Identidad(id=p, norm=por_id[p].norm, fiflp_id=por_id[p].fiflp_id,
                                       vistas=tuple(vs)) for p, vs in juntas.items()]
    return resolver(fichas_como_identidad, unir_cortos_en_club=cortos) == {p: (p, None) for p in juntas}


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
        # Un id de un solo uso del primer LUCAS en su equipo (U0 de los cortos lo une: mismo niño).
        f(9, "LUCAS", 2020, "Arucas", fecha="2020-12-01"),
    ]
    nino = M.ninos(filas)
    assert nino[3] == nino[4] and nino[1] != nino[2] and nino[9] == nino[1]
    medida = M.pares(filas, nino)
    assert medida[("todos", "sin coma")] == {"mismo": 1, "distinto": 1}
    assert medida[("todos", "completos")] == {"mismo": 1}
    assert medida[("todos", "un apellido")] == {}         # «PEREZ, IKER» no cabe por edad
    # Uno a uno: dos LUCAS del club en 2021, no cuenta; ANA sí (una identidad sin id con los dos ids).
    assert medida[("uno a uno", "sin coma")] == {}
    assert medida[("uno a uno", "completos")] == {"mismo": 1}
    texto, decision = M.informe(Counter(), nino, medida)
    assert decision is False and "unir_cortos_en_club = False" in texto
    assert M.resumen_u0_cortos(M.identidades_con_id(filas)) == {
        "una asentada": 1, "dos o más asentadas": 0, "ninguna asentada": 0}


def test_la_medida_decide_por_los_pares_de_uno_a_uno():
    import medir_identidad as M
    medida = {("todos", "sin coma"): Counter(mismo=1, distinto=9), ("uno a uno", "sin coma"): Counter(mismo=19, mezcla=1),
              ("todos", "completos"): Counter(), ("uno a uno", "completos"): Counter(),
              ("todos", "un apellido"): Counter(distinto=5), ("uno a uno", "un apellido"): Counter(distinto=5)}
    texto, decision = M.informe(Counter(), {}, medida, {"una asentada": 2, "dos o más asentadas": 1,
                                                       "ninguna asentada": 3})
    assert decision is True and "unir_cortos_en_club = True" in texto
    assert "2 con una asentada" in texto and "1 con dos o más" in texto and "3 sin ninguna" in texto
    medida[("uno a uno", "sin coma")] = Counter(mismo=18, distinto=2)
    assert M.informe(Counter(), {}, medida)[1] is False


def test_los_cortos_se_unen_en_el_club():
    # La medida del 14/11/2026 (docs/identidad.md): sin coma, uno a uno, 100 % ≥ 95 %.
    assert UNIR_CORTOS_EN_CLUB is True
