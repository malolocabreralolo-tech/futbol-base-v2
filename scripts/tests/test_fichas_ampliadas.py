"""Las fichas cuando la web enseñe infantil, cadete y juvenil (el paso E2-D2 de la parte E2: categorias.EN_WEB con
las seis). Con ese EN_WEB el resolvedor de fichas (migrate_identidad.resolver_fichas) mira también sus apariciones:
une a un niño de benjamín con su cadete, y lo que une puede mover fichas publicadas hoy. Estas pruebas FIJAN los dos
EN_WEB (base_mayores.con_en_web; nunca lo que diga categorias.py: valen igual antes y después del paso) y comparan,
sobre la base real de después (conftest.bases_reales: «mayores», con el final de una pasada con el de antes, y
«mayores_seis», la misma con el de después), lo que publica la web con uno y con otro:

  (a) cada clave pública de hoy (la de cada ficha y sus alias en data-jugadores-*.js con el EN_WEB de antes) sigue
      llevando a una ficha, y esa ficha conserva todas sus filas (temporada, grupo, equipo, partidos, titular,
      goles, tarjetas): solo puede ganar filas de las categorías nuevas;
  (b) ninguna ficha junta dos identificadores de la federación que el EN_WEB de antes no juntaba, ni tiene un
      intervalo de edad vacío, ni dos categorías en una temporada que un mismo niño no puede jugar (EDAD_CONTIGUA);
  (c) un niño sin id de cadete o juvenil nunca se une por nombre y club a uno sin id de prebenjamín o benjamín de la
      misma temporada;
  (d) al menos la mitad de los niños de la base que base_mayores pone en las nuevas con su id (el mismo niño, más
      mayor) acaban con las dos categorías en una sola ficha publicada: las trayectorias;
  (e) el ranking y el año de nacimiento de los niños de hoy sin filas nuevas no cambian (ni orden ni índice, salvo
      los que entran o salen por el tope de cada lista).

Solo afirman sobre lo que fabrica base_mayores y los niños de hoy de prebenjamín, benjamín y alevín, nunca sobre los
datos reales de infantil, cadete y juvenil: estas pruebas van en la puerta del bot, y un dato raro de la federación
(un id en prebenjamín y en juvenil, dos homónimos sin id en un club) no puede pararlo. Por eso, si la base real ya trae
grupos de las nuevas (desde D3), se quitan de una copia antes de fabricar (fabricadas: vista_web.quitar_grupos, lo
mismo que no ve la web de hoy) y todo se compara sobre esa copia; con la base de hoy, son las de bases_reales tal
cual. Y (b), (c) y (d) miran solo las fichas con filas de los grupos fabricados. Lo real se mira fuera de la puerta:
medir_identidad.py --entre-categorias (docs/categorias-mayores.md, E2-D2).

Saltan sin futbolbase.db. Lo caro (la web de las dos bases: las fichas, el año y el ranking, sin escribir nada; ~15 s
cada una con la base real) se hace una vez por módulo y a la vez (paralelo.en_paralelo). Sin nombres de niños: los
mensajes de error llevan claves."""
import sqlite3
from collections import Counter

import pytest

import base_mayores
from categorias import MAYORES
from identidad import NIVELES_NUEVOS

# Las filas de una ficha en data-jugadores: [temporada, grupo, equipo, partidos, titular, goles, amarillas, rojas]
# y, en la de una identidad unida, 1 y el motivo. Lo que se compara es lo primero: el motivo cambia si cambia la
# principal (lo que era la principal pasa a ser una unida), y eso no es perder nada.
CAMPOS_DE_FILA = 8


def _const(texto):
    import json
    return json.loads(texto[texto.index("=") + 1:].rstrip().rstrip(";"))


def publicado(path, en_web):
    """Lo que publicaría la web con la base `path` y ese EN_WEB (sin escribir nada): {"p": {clave: ficha}, "a":
    {alias: clave}, "g": {temporada/grupo: [categoría, …]}, "ranking": {año: {"t": [...], "h": [...]}}}. Las fichas de
    la base ya son las de ese EN_WEB (bases_reales); la copia de la web (vista_web), el año y el ranking, también."""
    import generate_js as G
    import vista_web
    with base_mayores.con_en_web(en_web):
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            web = vista_web.copia_web(conn)
            datos = G._datos_fichas(web)
            jugadores = G.jugadores_files(web, datos)
            ranking = G.ranking_files(web, datos)
            if web is not conn:
                web.close()
        finally:
            conn.close()
    out = {"p": {}, "a": {}, "g": {}, "ranking": {}}
    for texto in jugadores.values():
        trozo = _const(texto)
        for k in ("p", "a", "g"):
            out[k].update(trozo[k])
    for nombre, texto in ranking.items():
        if nombre != "data-ranking.js":
            out["ranking"][nombre[len("data-ranking-"):-len(".js")]] = _const(texto)
    return out


def sin_lo_real(origen, destino):
    """Una copia de `origen` en `destino` sin los grupos de fuera del EN_WEB de antes (los reales de infantil, cadete
    y juvenil) ni lo que cuelga de ellos (vista_web.quitar_grupos, como la copia de la web de hoy), con el final de
    una pasada con ese EN_WEB: la base real de hoy más lo de siempre que ya haya leído el bot."""
    import shutil
    import vista_web
    from db import get_connection
    shutil.copyfile(origen, destino)
    conn = get_connection(destino)
    try:
        fuera = vista_web.grupos_fuera(conn, base_mayores.EN_WEB_DE_ANTES)
        conservar = [n for (n,) in conn.execute("SELECT name FROM categories")]
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")         # se borra en orden (vista_web); se comprueba al final
        conn.execute("BEGIN")
        vista_web.quitar_grupos(conn, fuera, conservar)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        conn.commit()
    finally:
        conn.close()
    base_mayores.fin_de_pasada(destino, "antes")
    return len(fuera)


@pytest.fixture(scope="module")
def fabricadas(bases_reales, tmp_path_factory):
    """{"antes": la base de después con el final de una pasada con el EN_WEB de antes, "seis": con el de después,
    "hecho": lo que devolvió poblar, "grupos": {códigos fabricados}}, sin nada real de las nuevas: con la base de hoy
    (sin grupos de ellas), las «mayores» y «mayores_seis» de bases_reales; si ya los trae, las mismas fabricadas sobre
    una copia de la resuelta sin ellos (sin_lo_real), a la vez."""
    from paralelo import en_paralelo
    import vista_web
    conn = sqlite3.connect(f"file:{bases_reales['resuelta']}?mode=ro", uri=True)
    try:
        reales = vista_web.grupos_fuera(conn, base_mayores.EN_WEB_DE_ANTES)
    finally:
        conn.close()
    if not reales:
        return {"antes": bases_reales["mayores"], "seis": bases_reales["mayores_seis"], "hecho": bases_reales["hecho"],
                "grupos": set(bases_reales["hecho"]["grupos"])}
    carpeta = tmp_path_factory.mktemp("fabricadas")
    limpia = carpeta / "limpia.db"
    sin_lo_real(bases_reales["resuelta"], limpia)
    antes, seis = carpeta / "antes.db", carpeta / "seis.db"
    hecho, hecho_seis = en_paralelo((base_mayores.leida, (limpia, antes, MAYORES, False, "antes")),
                                    (base_mayores.leida, (limpia, seis, MAYORES, False, "seis")))
    assert hecho == hecho_seis
    return {"antes": antes, "seis": seis, "hecho": hecho, "grupos": set(hecho["grupos"])}


def _de_lo_fabricado(path, grupos):
    """Los ids de players con alguna aparición o suceso en los grupos fabricados (`grupos`, sus códigos) de la
    temporada en curso."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        marcas = ",".join("?" * len(grupos))
        return {p for (p,) in conn.execute(
            f"""SELECT x.player_id FROM (SELECT player_id, match_id FROM appearances
                                         UNION SELECT player_id, match_id FROM match_events) x
                  JOIN matches m ON m.id = x.match_id JOIN groups g ON g.id = m.group_id
                  JOIN seasons s ON s.id = g.season_id
                 WHERE s.is_current = 1 AND g.code IN ({marcas})""", sorted(grupos))}
    finally:
        conn.close()


@pytest.fixture(scope="module")
def webs(fabricadas):
    """{"antes": lo publicado con el EN_WEB de antes, "seis": con el de después}, sobre las fabricadas, a la vez."""
    from paralelo import en_paralelo
    antes, seis = en_paralelo((publicado, (fabricadas["antes"], "antes")),
                              (publicado, (fabricadas["seis"], "seis")))
    return {"antes": antes, "seis": seis}


def _ficha(web, clave):
    """La ficha a la que lleva una clave (la suya o un alias), o None."""
    if clave in web["p"]:
        return web["p"][clave]
    destino = web["a"].get(clave)
    return web["p"].get(destino) if destino else None


def _filas(ficha):
    return Counter(tuple(fila[:CAMPOS_DE_FILA]) for fila in ficha["c"])


def _categoria(web, fila):
    """La categoría (en minúsculas) de una fila de ficha, por su grupo («g»)."""
    return web["g"][f"{fila[0]}/{fila[1]}"][0]


NUEVAS = tuple(c.lower() for c in MAYORES)


def test_cada_clave_de_hoy_sigue_en_una_ficha_con_todas_sus_filas(webs):
    """(a) Ninguna clave pública de hoy se pierde (los enlaces y los seguidos de hoy siguen valiendo) y la ficha a la
    que lleva tiene todas las filas que tenía; las que gana son solo de infantil, cadete y juvenil."""
    antes, seis = webs["antes"], webs["seis"]
    perdidas, menguan, ganan_viejas = [], [], []
    for clave in list(antes["p"]) + list(antes["a"]):
        hoy, despues = _ficha(antes, clave), _ficha(seis, clave)
        if despues is None:
            perdidas.append(clave)
            continue
        faltan = _filas(hoy) - _filas(despues)
        if faltan:
            menguan.append(clave)
        sobran = _filas(despues) - _filas(hoy)
        if any(_categoria(seis, fila) not in NUEVAS for fila in sobran):
            ganan_viejas.append(clave)
    assert perdidas == [], f"{len(perdidas)} claves de hoy ya no llevan a ninguna ficha: {perdidas[:20]}"
    assert menguan == [], f"{len(menguan)} claves de hoy llevan a una ficha que ha perdido filas: {menguan[:20]}"
    assert ganan_viejas == [], (f"{len(ganan_viejas)} claves de hoy llevan a una ficha que gana filas de prebenjamín, "
                                f"benjamín o alevín (se ha juntado con otra ficha de hoy): {ganan_viejas[:20]}")


# Un niño juega cada temporada en su categoría y, como mucho, también en la de al lado (subir una es habitual:
# nacimiento._MAS_JOVEN[1]; un alevín que sube a infantil). Dos categorías que no son contiguas (prebenjamín y
# alevín, benjamín e infantil, alevín y cadete, infantil y juvenil…) en una misma temporada no pueden ser el mismo
# niño: sus intervalos de edad del resolvedor (identidad.intervalo) ni se cruzan. La prueba lo comprueba también.
EDAD_CONTIGUA = 1


def test_la_regla_de_las_contiguas_es_la_de_las_edades():
    from identidad import NIVEL, intervalo
    for a in NIVEL.values():
        for b in NIVEL.values():
            lo = max(intervalo(2026, a)[0], intervalo(2026, b)[0])
            hi = min(intervalo(2026, a)[1], intervalo(2026, b)[1])
            assert (lo <= hi) == (abs(a - b) <= EDAD_CONTIGUA), (a, b)


def _fichas_de(path, en_web):
    """{principal: [identidad.Identidad]} de las fichas de la base `path` (players.ficha_id), con las vistas de ese
    EN_WEB (migrate_identidad.identidades): las que publica la web."""
    import migrate_identidad as M
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        with base_mayores.con_en_web(en_web):
            ids = {i.id: i for i in M.identidades(conn)}
        principal = {pid: (f or pid) for pid, f in conn.execute("SELECT id, ficha_id FROM players")}
    finally:
        conn.close()
    out = {}
    for pid, i in ids.items():
        out.setdefault(principal[pid], []).append(i)
    return out, principal


def _edad(vistas):
    """El intervalo de años de nacimiento de unas vistas (identidad.intervalo de cada una, cruzados)."""
    from identidad import intervalo
    lo, hi = -10 ** 9, 10 ** 9
    for anio, nivel, *_ in vistas:
        if nivel is not None:
            a, b = intervalo(anio, nivel)
            lo, hi = max(lo, a), min(hi, b)
    return lo, hi


def test_ninguna_ficha_imposible_ni_dos_ids_nuevos_juntos(fabricadas):
    """(b) Con el EN_WEB de después: ninguna ficha junta dos identificadores que con el de antes estaban en fichas
    distintas (los «ids de un solo uso» que ya juntaba la U0 de hoy siguen como estaban), ni tiene un intervalo de
    edad vacío, ni dos categorías no contiguas en una temporada; y ninguna de dos o más identidades (las que junta
    el resolvedor) es incompatible (identidad.compatibles de todas sus vistas: la edad y el solape de clubes). De
    una identidad sola, lo que no es del resolvedor no se mira: su solape (una fila con id en dos clubes a la vez la
    misma temporada: la base real tiene ~90 desde antes de la parte E), lo que ya era imposible solo con
    prebenjamín, benjamín y alevín, y la fila «sin nombre publicado» (identidad._fuera: no es un niño). Solo las fichas
    con filas de los grupos fabricados: lo demás es lo de hoy, que no cambia (las demás pruebas de este fichero)."""
    from identidad import _fuera, compatibles
    seis, _ = _fichas_de(fabricadas["seis"], "seis")
    _, principal_antes = _fichas_de(fabricadas["antes"], "antes")
    fabricados = _de_lo_fabricado(fabricadas["seis"], fabricadas["grupos"])
    assert fabricados
    dos_ids, vacias, lejanas = [], [], []
    for p, miembros in seis.items():
        if (len(miembros) == 1 and _fuera(miembros[0])) or not any(i.id in fabricados for i in miembros):
            continue
        con_id = {principal_antes.get(i.id, i.id) for i in miembros if i.fiflp_id is not None}
        if len(con_id) > 1:
            dos_ids.append(p)
        vistas = [v for i in miembros for v in i.vistas]
        lo, hi = _edad(vistas)
        ya_antes = _edad([v for v in vistas if v[1] not in NIVELES_NUEVOS])
        if (len(miembros) > 1 and not compatibles(vistas)) or (lo > hi and ya_antes[0] <= ya_antes[1]):
            vacias.append(p)
        por_temporada = {}
        for anio, nivel, *_ in vistas:
            por_temporada.setdefault(anio, set()).add(nivel)
        if len(miembros) > 1 and any(max(n) - min(n) > EDAD_CONTIGUA for n in por_temporada.values()):
            lejanas.append(p)
    assert dos_ids == [], f"{len(dos_ids)} fichas juntan ids de dos fichas de antes (principales {dos_ids[:20]})"
    assert vacias == [], f"{len(vacias)} fichas imposibles (principales {vacias[:20]})"
    assert lejanas == [], f"{len(lejanas)} fichas con dos categorías no contiguas en una temporada ({lejanas[:20]})"


def test_un_sin_id_de_cadete_o_juvenil_no_es_un_pequeno_sin_id_del_club(fabricadas):
    """(c) Los niños sin id de cadete y juvenil que se llaman como un prebenjamín (o benjamín) sin id del mismo club y
    la misma temporada (base_mayores los pone a propósito: SIN_ID_DE) siguen en fichas distintas con el EN_WEB de
    después: seis años o más de diferencia. Solo los de los grupos fabricados."""
    import migrate_identidad as M
    from identidad import club
    if not fabricadas["hecho"]["sin_id_disponibles"]:
        pytest.skip("la temporada en curso aún no tiene sin id de prebenjamín ni de alevín (recién empezada)")
    fabricados = _de_lo_fabricado(fabricadas["seis"], fabricadas["grupos"])
    conn = sqlite3.connect(f"file:{fabricadas['seis']}?mode=ro", uri=True)
    try:
        filas = conn.execute(
            """SELECT DISTINCT p.id, p.norm_name, t.name, p.season_id, upper(c.name), coalesce(p.ficha_id, p.id)
                 FROM players p JOIN appearances a ON a.player_id = p.id JOIN matches m ON m.id = a.match_id
                 JOIN groups g ON g.id = m.group_id JOIN categories c ON c.id = g.category_id
                 JOIN teams t ON t.id = p.team_id
                WHERE p.fiflp_id IS NULL AND p.team_id IS NOT NULL""").fetchall()
    finally:
        conn.close()
    pequenos = {}
    for pid, norm, equipo, sid, cat, ficha in filas:
        if cat in ("PREBENJAMIN", "BENJAMIN"):
            pequenos.setdefault((M.nombre_base(norm), club(equipo), sid), set()).add(ficha)
    vistos, juntos = 0, []
    for pid, norm, equipo, sid, cat, ficha in filas:
        if cat in ("CADETE", "JUVENIL") and pid in fabricados:
            suyos = pequenos.get((M.nombre_base(norm), club(equipo), sid), set())
            vistos += bool(suyos)
            if ficha in suyos:
                juntos.append(pid)
    assert vistos >= 1, "base_mayores no ha montado el caso: ningún cadete o juvenil sin id con el nombre de un pequeño"
    assert juntos == [], f"{len(juntos)} sin id de cadete o juvenil en la ficha de un pequeño sin id: {juntos}"


def test_trayectorias(fabricadas, webs):
    """(d) Los niños de la base que base_mayores pone en infantil, cadete o juvenil con su id (de su edad): al menos la
    mitad, con filas de su categoría de antes y de la nueva en su ficha publicada (la del EN_WEB de después). Y los
    infantiles sin id que se llaman como un alevín sin id de su club y temporada (el mismo niño, que sube), alguno en
    la ficha de ese alevín."""
    seis = webs["seis"]
    fabricados = _de_lo_fabricado(fabricadas["seis"], fabricadas["grupos"])
    conn = sqlite3.connect(f"file:{fabricadas['seis']}?mode=ro", uri=True)
    try:
        nuevas = ",".join("?" * len(MAYORES))
        reutilizados = [f for p, f in conn.execute(
            f"""SELECT DISTINCT p.id, p.fiflp_id FROM players p JOIN appearances a ON a.player_id = p.id
                  JOIN matches m ON m.id = a.match_id JOIN groups g ON g.id = m.group_id
                  JOIN categories c ON c.id = g.category_id
                 WHERE p.fiflp_id IS NOT NULL AND p.fiflp_id < ? AND upper(c.name) IN ({nuevas})""",
            (base_mayores.ID_NUEVO, *MAYORES)) if p in fabricados]
        subidos = conn.execute(
            """SELECT count(*) FROM players i JOIN players a ON a.team_id = i.team_id AND a.season_id = i.season_id
                 AND a.fiflp_id IS NULL AND a.id <> i.id AND coalesce(a.ficha_id, a.id) = coalesce(i.ficha_id, i.id)
                WHERE i.fiflp_id IS NULL AND i.norm_name LIKE '%.INFANTIL'
                  AND a.norm_name = substr(i.norm_name, 1, length(i.norm_name) - length('.INFANTIL'))""").fetchone()[0]
    finally:
        conn.close()
    assert len(reutilizados) >= fabricadas["hecho"]["jugadores_reutilizados"] > 0
    con_las_dos = 0
    for fid in reutilizados:
        ficha = _ficha(seis, str(fid))
        cats = {_categoria(seis, fila) for fila in ficha["c"]} if ficha else set()
        if cats & set(NUEVAS) and cats - set(NUEVAS):
            con_las_dos += 1
    assert con_las_dos * 2 >= len(reutilizados), f"solo {con_las_dos} de {len(reutilizados)} con las dos categorías"
    if fabricadas["hecho"]["sin_id_disponibles"]:
        assert subidos >= 1, "ningún infantil sin id en la ficha del alevín sin id de su nombre, club y temporada"


def test_el_ranking_y_el_anio_de_los_de_hoy_sin_filas_nuevas_no_cambian(webs):
    """(e) De las fichas de hoy que con el EN_WEB de después tienen exactamente las mismas filas (ni ganan ni
    pierden), el año de nacimiento es el mismo y, en cada lista del ranking, salen en el mismo orden y con el mismo
    índice: la lista de antes y la de después, quitados los demás, empiezan igual; lo que sobra al final de una es lo
    que entra o sale por el tope (ranking.TOPE)."""
    antes, seis = webs["antes"], webs["seis"]
    iguales = {k for k, ficha in antes["p"].items() if k in seis["p"] and _filas(ficha) == _filas(seis["p"][k])}
    assert len(iguales) * 2 > len(antes["p"])
    otro_anio = [k for k in iguales if antes["p"][k].get("y") != seis["p"][k].get("y")]
    assert otro_anio == [], f"{len(otro_anio)} fichas sin filas nuevas con otro año: {otro_anio[:20]}"
    distintas = []
    for anio in sorted(set(antes["ranking"]) | set(seis["ranking"])):
        for vista in ("t", "h"):
            a = [e for e in antes["ranking"].get(anio, {}).get(vista, []) if e[0] in iguales]
            b = [e for e in seis["ranking"].get(anio, {}).get(vista, []) if e[0] in iguales]
            n = min(len(a), len(b))
            if a[:n] != b[:n]:
                primera = next(i for i in range(n) if a[i] != b[i])
                distintas.append(f"{anio} {vista}: desde la {primera + 1}.ª ({a[primera][0]} / {b[primera][0]})")
    assert distintas == [], distintas
