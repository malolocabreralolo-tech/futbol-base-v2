"""convenio.py — El código de grupo, la fase legible y la isla de las competiciones de infantil,
cadete y juvenil (siempre) y de las de alevín de Lanzarote y Fuerteventura, por su nombre.

El alevín de Gran Canaria, benjamín y prebenjamín siguen con lo suyo (docs/alevin.md,
fiflp_manifest.comp_meta, import_fiflp_grupos.meta_by_name): aquí no se tocan. Módulo puro, sin
base ni red; lo comprueba scripts/tests/test_convenio.py contra el catálogo entero de la
federación de 2016-17 a 2026-27.

    código = CATEGORÍA + NIVEL + ISLA + FASE + TIPO + número de grupo

    CATEGORÍA  INF, CAD, JUV o AL (alevín de islas)
    NIVEL      H División de Honor, A Autonómica, I Interinsular, T Territorial, S Superliga,
               P Preferente, 1 Primera, 2 Segunda, NB Insular B, N Insular; U si no dice ninguno
    ISLA       X Lanzarote-Fuerteventura, L Lanzarote, F Fuerteventura, G Gran Canaria; sin
               isla, nada si el nivel es de varias islas (H, A, I, T) y G si no
    FASE       SF la segunda, FO oro, FP plata, la letra de un subgrupo; la primera, nada
    TIPO       nada (liga), C copa (CK de campeones, CD delegación), A fase de ascenso,
               E eliminatorias, F final, S semifinal

    LIGA INFANTIL PREFERENTE DE GRAN CANARIA        -> INFPG1..  «Preferente GC»
    LIGA JUVENIL INTERINSULAR                       -> JUVI1..   «Interinsular»
    COPA CABILDO DE LANZAROTE CADETE INSULAR        -> CADNLC1.. «Copa Cabildo Insular Lanzarote»
    FASE DE ASCENSO A CADETE INTERINSULAR (LANZAROTE-FUERTEVENTURA) -> CADIXA1..
    LIGA ALEVIN LANZAROTE FASE 1                    -> ALUL1..   «Lanzarote Fase 1»

Por qué no chocan con ningún código de hoy:

  1. Todo prefijo empieza por INF, CAD, JUV o AL y acaba en letra; el número del grupo va detrás.
     Así, dos prefijos distintos nunca dan el mismo código (ABC + 12 no es AB + C12: C no es cifra).
  2. Ningún código de hoy empieza por INF, CAD ni JUV (benjamín y prebenjamín: FF, A-F, LZ, FV, PG,
     PLZ, PFV, BC, PCC, CGC, EL, PEL…): con esos tres no hay nada con qué chocar.
  3. Los de alevín de islas llevan SIEMPRE nivel e isla tras AL (ALUL, ALPL, AL1L, ALSF…): su
     nombre dice Lanzarote o Fuerteventura (si no, no aplica), así que tras el nivel (U si no dice
     ninguno) siempre va L, F o X. Nunca son AL + una letra (la Segunda Fase de Gran Canaria,
     ALA…ALZ), ALP (Preferente GC), ALCC… (Copa de Campeones), ALCL (Clausura) ni ALEL
     (eliminatorias): C y E no son ningún nivel.
  4. Ninguno empieza por LZ, FV, CLZ, CFV, PLZ, PFV (que leen la isla por startswith:
     import_fiflp_grupos.ISLAND_OF_PREFIX), PCC, BC, MCP ni MCB (copas en la web: isCupGroup), ni
     acaba en KO (model.js).
  5. Dentro de una temporada, dos competiciones distintas no dan el mismo prefijo, ni el prefijo de
     una liga más EL (sus grupos de eliminatoria, eliminatoria_de_liga) es el de otra: lo comprueba
     la prueba contra el catálogo entero, temporada a temporada.

Lo que no encaja no se inventa: SinConvenio con el motivo, y la activación lo apunta («sin
convenio de código: …») sin cargar esa competición.
"""
import re
import unicodedata
from typing import NamedTuple

try:
    import categorias
except ImportError:                      # importado como scripts.convenio
    from scripts import categorias


class SinConvenio(ValueError):
    """La competición no tiene convenio de código; el texto es el motivo."""


class Convenio(NamedTuple):
    prefijo: str
    fase: str
    isla: str          # grancanaria, lanzarote, fuerteventura o interinsular
    tipo: str          # liga, copa, ascenso, eliminatorias o final


CATEGORIA = {"INFANTIL": "INF", "CADETE": "CAD", "JUVENIL": "JUV", "ALEVIN": "AL"}
# (expresión, token, nombre), en este orden; uno por nombre («INSULAR B» manda sobre «INSULAR»).
NIVELES = (
    (r"\bDIVISION (?:DE )?HONOR\b", "H", "División de Honor"),
    (r"\bAUTONOMIC[AO]\b", "A", "Autonómica"),
    (r"\bINTERINSULAR\b", "I", "Interinsular"),
    (r"\bTERRITORIAL\b", "T", "Territorial"),
    (r"\bSUPERLIGA\b", "S", "Superliga"),
    (r"\bPREFERENTE\b", "P", "Preferente"),
    (r"\bPRIMERA\b", "1", "Primera"),
    (r"\bSEGUNDA\b", "2", "Segunda"),
    (r"\bINSULAR B\b", "NB", "Insular B"),
    (r"\bINSULAR\b", "N", "Insular"),
)
# token → (corta, larga, isla de la base). La corta va tras el nivel («Preferente GC»); la larga, sola
# («Gran Canaria»).
ISLAS = {"G": ("GC", "Gran Canaria", "grancanaria"),
         "L": ("Lanzarote", "Lanzarote", "lanzarote"),
         "F": ("Fuerteventura", "Fuerteventura", "fuerteventura"),
         "X": ("Lanzarote-Fuerteventura", "Lanzarote-Fuerteventura", "interinsular"),
         "": ("", "", "interinsular")}
# Los niveles de varias islas: sin isla en el nombre, no llevan ninguna (y su isla es «interinsular»).
MULTIISLA = {"H", "A", "I", "T"}

# Lo que no se publica nunca (punto 2).
_NO_SE_PUBLICA = re.compile(r"SALA|\bFS\b|\bLPFS\b|FEMENIN|FUTUREFEM|PLAYA|VETERAN")
# Tipos sin convenio (punto 4): no se sabe si son liga o copa, ni a veces de qué isla.
_SIN_TIPO = re.compile(r"\bELIMINATORIAS?\b|\bPLAY OFF\b|\bDESEMPATE\b|\bTORNEO\b|\bCLAUSURA\b")


def _normaliza(nombre):
    """Punto 1: sin tildes, en mayúsculas; 1ª/2ª en letra; sin signos, sin la modalidad (F-8, F8, F7,
    FUTBOL-8…), sin «GRUPO <n>» ni «DE LAS PALMAS»; espacios simples."""
    n = "".join(c for c in unicodedata.normalize("NFD", nombre or "") if unicodedata.category(c) != "Mn").upper()
    n = n.replace("1ª", " PRIMERA ").replace("2ª", " SEGUNDA ")
    n = re.sub(r"\bF-?[78]\b|\bFUTBOL-?[78]\b", " ", n)
    n = re.sub(r"[^A-Z0-9]+", " ", n)
    n = re.sub(r"\bGRUPO \d+\b", " ", n)
    n = re.sub(r"\bDE LAS PALMAS\b", " ", n)
    return " ".join(n.split())


def _quita(n, patron):
    return " ".join(re.sub(patron, " ", n).split())


def aplica(nombre):
    """¿Va por este convenio? Infantil, cadete o juvenil por el nombre (sin mirar si se publica) o alevín
    de Lanzarote o Fuerteventura (categorias.es_alevin_de_islas)."""
    n = re.sub(r"[\s\-_.]", "", _normaliza(nombre))
    if "BENJAMIN" in n:
        return False
    if any(c in n for c in ("INFANTIL", "CADETE", "JUVENIL")):
        return True
    return categorias.es_alevin_de_islas(nombre)


def _isla_y_nivel(n):
    """(token del nivel, su nombre, token de la isla) de lo que queda del nombre (puntos 6 y 7)."""
    niveles = []
    resto = n
    for patron, token, nombre in NIVELES:
        if re.search(patron, resto):
            niveles.append((token, nombre))
            resto = _quita(resto, patron)
    if len(niveles) > 1:
        raise SinConvenio("dos niveles en el nombre")
    nivel, nombre_nivel = niveles[0] if niveles else ("U", "")
    lz, fv, gc = "LANZAROTE" in n, "FUERTEVENTURA" in n, "GRAN CANARIA" in n
    isla = "X" if lz and fv else "L" if lz else "F" if fv else "G" if gc else \
        ("" if nivel in MULTIISLA else "G")
    return nivel, nombre_nivel, isla


def _base(n):
    """(token de nivel + isla + fase, fase legible, isla de la base) de una liga (o de lo que lleva una
    copa o un ascenso), puntos 5 a 8, sobre el nombre ya sin categoría ni tipo."""
    fase_token, fase_texto = "", ""
    if re.search(r"\bSEGUNDA FASE\b|\b2 FASE\b|\bFASE 2\b", n):
        fase_token, fase_texto = "SF", " Fase 2"
        n = _quita(n, r"\bSEGUNDA FASE\b|\b2 FASE\b|\bFASE 2\b")
    elif re.search(r"\bPRIMERA FASE\b|\bFASE 1\b", n):
        fase_texto = " Fase 1"
        n = _quita(n, r"\bPRIMERA FASE\b|\bFASE 1\b")
    elif re.search(r"\bFASE ORO\b", n):
        fase_token, fase_texto = "FO", " Fase Oro"
        n = _quita(n, r"\bFASE ORO\b")
    elif re.search(r"\bFASE PLATA\b", n):
        fase_token, fase_texto = "FP", " Fase Plata"
        n = _quita(n, r"\bFASE PLATA\b")
    m = re.search(r"\bSUBGRUPO ([A-Z])\b", n)
    if m:
        fase_token, fase_texto = fase_token + m.group(1), fase_texto + " " + m.group(1)
        n = _quita(n, r"\bSUBGRUPO [A-Z]\b")
    if re.search(r"\bFASE\b", n):
        raise SinConvenio("fase desconocida")
    nivel, nombre_nivel, isla = _isla_y_nivel(n)
    corta, larga, isla_base = ISLAS[isla]
    if nivel == "U":
        legible = larga
    else:
        legible = f"{nombre_nivel} {corta}".strip()
    return nivel + isla + fase_token, legible + fase_texto, isla_base


def _copa(n):
    """(token tras la categoría, fase legible, isla) de una copa (punto 4)."""
    if re.search(r"\bCAMPEON", n):
        tokens, _, isla = _base(_quita(n, r"\bCOPA\b|\bCAMPEON(?:ES)?\b|\bDE\b"))
        return tokens + "CK", "Copa de Campeones", isla
    if re.search(r"\bDELEGACION\b", n):
        tokens, legible, isla = _base(_quita(n, r"\bCOPA\b|\bDELEGACION\b"))
        return tokens + "CD", f"Copa Delegación {legible}", isla
    if re.search(r"\bCABILDO\b", n):
        tokens, legible, isla = _base(_quita(n, r"\bCOPA\b|\bCABILDO\b"))
        return tokens + "C", f"Copa Cabildo {legible}", isla
    tokens, legible, isla = _base(_quita(n, r"\bCOPA\b"))
    return tokens + "C", f"Copa {legible}", isla


def _sin_categoria(nombre):
    """(nombre normalizado sin la palabra de la categoría, prefijo de la categoría)."""
    n = _normaliza(nombre)
    if _NO_SE_PUBLICA.search(n):
        raise SinConvenio("no se publica")
    for palabra, token in CATEGORIA.items():
        patron = r"\bINFANTILL?\b" if palabra == "INFANTIL" else rf"\b{palabra}\b"
        if re.search(patron, n):
            return _quita(n, patron), token
    raise SinConvenio("sin categoría")


def _resto(n):
    """(tokens tras la categoría, fase legible, isla, tipo) de un nombre ya sin categoría."""
    # FINAL o SEMIFINAL(ES) delante: lo de la liga o la copa del resto, con F o S.
    m = re.match(r"^(SEMI)?FINAL(?:ES)? (.+)$", n)
    if m:
        tokens, legible, isla, tipo = _resto(m.group(2))
        if tipo not in ("liga", "copa"):
            raise SinConvenio("final de algo que no es liga ni copa")
        palabra = "Semifinal" if m.group(1) else "Final"
        legible = f"{palabra} {legible}" if tipo == "copa" else f"{palabra} Liga {legible}"
        return tokens + palabra[0], legible, isla, "final"
    # FASE FINAL detrás: la final de la liga.
    if re.search(r"\bFASE FINAL$", n):
        tokens, legible, isla = _base(_quita(_quita(n, r"\bFASE FINAL$"), r"\bLIGA\b"))
        return tokens + "F", f"Final Liga {legible}", isla, "final"
    # Las eliminatorias de una copa: lo de la copa, con E.
    if re.match(r"^ELIMINATORIAS? COPA\b", n) or re.search(r"^COPA\b.*\bELIMINATORIAS$", n):
        tokens, legible, isla = _copa(_quita(n, r"\bELIMINATORIAS?\b"))
        return tokens + "E", f"Eliminatorias {legible}", isla, "eliminatorias"
    # Las eliminatorias de ascenso: el nivel y la isla del destino, con E.
    if re.match(r"^ELIMINATORIAS (?:DE )?ASCENSO A\b", n):
        tokens, legible, isla = _base(_quita(n, r"^ELIMINATORIAS (?:DE )?ASCENSO A\b"))
        return tokens + "E", f"Eliminatorias de Ascenso a {legible}", isla, "eliminatorias"
    if re.search(r"\bFASE (?:DE )?ASCENSO(?: A)?\b", n):
        tokens, legible, isla = _base(_quita(n, r"\bFASE (?:DE )?ASCENSO(?: A)?\b"))
        return tokens + "A", f"Fase de Ascenso a {legible}", isla, "ascenso"
    if _SIN_TIPO.search(n):
        raise SinConvenio("tipo de competición sin convenio")
    if re.match(r"^COPA\b", n):
        tokens, legible, isla = _copa(n)
        return tokens, legible, isla, "copa"
    tokens, legible, isla = _base(_quita(n, r"\bLIGA\b"))
    return tokens, legible, isla, "liga"


def convenio(nombre):
    """El Convenio (prefijo, fase, isla, tipo) de una competición de las categorías nuevas (aplica), o
    SinConvenio con el motivo."""
    if not aplica(nombre):
        raise SinConvenio("sin categoría")
    n, categoria = _sin_categoria(nombre)
    tokens, fase, isla, tipo = _resto(_quita(n, r"\bDE\b"))
    return Convenio(categoria + tokens, fase, isla, tipo)


def eliminatoria_de_liga(c):
    """Los grupos de eliminatoria publicados dentro de una liga («Eliminatoria de Primeros…»): el prefijo
    de la liga más EL y la fase «Eliminatorias <fase de la liga>» (punto 9), como EL, PEL y ALEL."""
    return Convenio(c.prefijo + "EL", "Eliminatorias " + c.fase, c.isla, "eliminatorias")
