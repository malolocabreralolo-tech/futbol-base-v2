"""categorias.py — La categoría de una competición de la federación (o de una liga de la
app de futbolaspalmas) por su nombre, en UN solo sitio.

Antes cada importador tenía su copia («PREBENJAMIN si lo dice, si no BENJAMIN») y alevín
caía en benjamín: un grupo alevín con los mismos clubes que uno de benjamín se casaba con
él y le escribía sus goleadores, sus actas o sus estados. Ahora todos preguntan aquí.

El módulo contesta cuatro preguntas, y van SEPARADAS a propósito:

  1. ¿Qué categoría es?        category_of(nombre) -> 'PREBENJAMIN' | 'BENJAMIN' | 'ALEVIN'
                                                      | 'INFANTIL' | 'CADETE' | 'JUVENIL' | None
  2. ¿La activa el bot solo?   activable(nombre): su categoría está en ACTIVABLES.
  3. ¿Qué carril la lee?       CARRILES: el principal (el bot de siempre, update.yml) o el de
                               las mayores (carril-mayores.yml); carril_de, carril_actual.
  4. ¿La ve la web?            EN_WEB: lo que miran el generador y el resolvedor de fichas.

Por qué no basta con la primera (decisión 1 de la parte E de la ampliación): el bot apunta en
newCompetitions y activar_auto activa SOLO todo lo que reconoce. Si reconocer infantil, cadete
y juvenil bastara para activarlas, en cuanto este módulo las conociera se activarían de golpe sus
24 competiciones de 2026-27, el bot de siempre leería sus ~45 grupos en sus pasadas (sin sitio:
ya no le cabe alevín entero) y la web las enseñaría a medio cargar. Así, conocerlas no dispara
nada: cada paso (activarlas, leerlas en su carril, enseñarlas) lo da el director cambiando su
tupla, una categoría cada vez.

None es «no se publica»: fútbol sala (también la liga «LPFS» y «FS» o «F.S.» sueltos), fútbol
femenino, alevín de Lanzarote y Fuerteventura mientras ALEVIN_ISLAS sea False, un nombre con dos
de las categorías alevín, infantil, cadete y juvenil (no se sabe cuál es) y cualquier competición
que no diga su categoría. Los nombres de la base son los de categories.name, en mayúsculas; las
claves de la web, en minúsculas (DB_NAME).
"""
import os
import re
import unicodedata

# Clave de la web (manifiestos, --categorias, data-*.js) → nombre en la tabla categories.
DB_NAME = {"benjamin": "BENJAMIN", "prebenjamin": "PREBENJAMIN", "alevin": "ALEVIN",
           "infantil": "INFANTIL", "cadete": "CADETE", "juvenil": "JUVENIL"}
# Lo que descargan e importan los scripts si no se les dice otra cosa: alevín y las mayores se piden a
# propósito.
DEFAULT_CATEGORIES = ("BENJAMIN", "PREBENJAMIN")
# Las categorías de fútbol 11 (parte E): las lee su propio carril.
MAYORES = ("INFANTIL", "CADETE", "JUVENIL")
# Islas del alevín que hoy no se publica.
ALEVIN_FUERA = ("LANZAROTE", "FUERTEVENTURA")
# El alevín de Lanzarote y Fuerteventura: mientras sea False sigue fuera, como siempre (category_of da
# None y excluded True). Lo pone a True el director en su paso (D6), y no antes: hay un encargo alevín del
# carril del histórico en marcha (scripts/historico/plan.json) que, con él dentro, bajaría también las
# competiciones de las otras dos islas.
ALEVIN_ISLAS = False
# Lo que el bot apunta en newCompetitions y activar_auto activa solo. Las mayores entran en los pasos
# D3-D5 del director, una cada vez.
ACTIVABLES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
# Qué lee cada carril. El principal es el bot de siempre, con FIFLP_CATS vacía; el de las mayores,
# update.yml llamado desde carril-mayores.yml con FIFLP_CATS=infantil,cadete,juvenil.
CARRILES = {"principal": ("PREBENJAMIN", "BENJAMIN", "ALEVIN"), "mayores": MAYORES}
# Lo que ven el generador y el resolvedor de fichas: lo demás puede estar en la base sin salir en la web
# hasta su parte (E2).
EN_WEB = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")
# El sufijo de la tanda de activación de cada categoría (fiflp_islas_<CodTemporada><sufijo>_raw.json):
# benjamín y prebenjamín comparten la de siempre.
TANDAS = {"": ("BENJAMIN", "PREBENJAMIN"), "al": ("ALEVIN",), "inf": ("INFANTIL",), "cad": ("CADETE",),
          "juv": ("JUVENIL",)}

# Las que se buscan por su palabra en el nombre (sin espacios ni guiones); benjamín y prebenjamín van
# antes y aparte, como siempre. «INFANTILL» (así en el catálogo de 2024-25) contiene «INFANTIL».
_POR_PALABRA = ("ALEVIN", "INFANTIL", "CADETE", "JUVENIL")
# Lo que no se publica nunca: sala («SALA», la liga «LPFS», «FS» o «F.S.» sueltos: la «COPA JUVENIL ISLA
# DE GRAN CANARIA FS» de 2024-25) y el fútbol femenino. «FASE» no es «FS».
_NO_SE_PUBLICA = re.compile(r"\bSALA\b|\bLPFS\b|\bFS\b|\bF\.S\b|FEMENIN")


def _fold(text):
    """Mayúsculas sin tildes."""
    return "".join(c for c in unicodedata.normalize("NFD", text or "")
                   if unicodedata.category(c) != "Mn").upper()


def _compact(folded):
    return re.sub(r"[\s\-_.]", "", folded)        # 'PRE-BENJAMIN', 'PRE BENJAMIN'


def es_alevin_de_islas(name):
    """¿Es alevín (sin benjamín) de Lanzarote o Fuerteventura por su nombre? Valga lo que valga
    ALEVIN_ISLAS: el convenio de códigos (scripts/convenio.py) y los lotes lo necesitan saber también
    mientras siga fuera."""
    n = _fold(name)
    return "ALEVIN" in _compact(n) and "BENJAMIN" not in n and any(i in n for i in ALEVIN_FUERA)


def category_of(name):
    """La categoría de la base de una competición, o None (ver el docstring del módulo). Lee el nombre
    del catálogo ('LIGA ALEVIN GRAN CANARIA FASE PREVIA'), el de la cabecera de un acta (con
    '(GRUPO 7)' detrás) o el de una liga de la app ('Liga Alevin Gran Canaria Grupo 1')."""
    n = _fold(name)
    if not n or _NO_SE_PUBLICA.search(n):
        return None
    compact = _compact(n)
    if "PREBENJAMIN" in compact:
        return "PREBENJAMIN"
    if "BENJAMIN" in compact:
        return "BENJAMIN"
    found = [cat for cat in _POR_PALABRA if cat in compact]
    if len(found) != 1:
        return None               # ninguna, o dos («COPA ALEVIN E INFANTIL»): no se sabe
    if found[0] == "ALEVIN" and not ALEVIN_ISLAS and any(isla in n for isla in ALEVIN_FUERA):
        return None
    return found[0]


def excluded(name):
    """¿Es una competición que la web no publica a propósito? Fútbol sala (o la liga «LPFS»), fútbol
    femenino y, con ALEVIN_ISLAS a False, alevín de Lanzarote o Fuerteventura. Un nombre que no dice su
    categoría no lo es: no se sabe."""
    n = _fold(name)
    if _NO_SE_PUBLICA.search(n):
        return True
    return not ALEVIN_ISLAS and es_alevin_de_islas(name)


def activable(name):
    """¿La activa el bot solo? Su categoría está en ACTIVABLES (conocerla no basta)."""
    return category_of(name) in ACTIVABLES


def parse_categories(text):
    """'benjamin,prebenjamin' (la entrada de un workflow o de --categorias) → ('BENJAMIN',
    'PREBENJAMIN'), en ese orden y sin repetir; vacío, las de siempre (DEFAULT_CATEGORIES). Una
    categoría que no existe aborta: mejor parar que bajar de más o de menos."""
    out = []
    for part in (text or "").split(","):
        key = _fold(part.strip()).lower()
        if not key:
            continue
        if key.upper() in DB_NAME.values():
            key = key.lower()
        if key not in DB_NAME:
            raise ValueError(f"categoría desconocida: {part.strip()} (valen {', '.join(DB_NAME)})")
        if DB_NAME[key] not in out:
            out.append(DB_NAME[key])
    return tuple(out) or DEFAULT_CATEGORIES


def carril_de(categories):
    """El carril ('principal' o 'mayores', CARRILES) que lee unas categorías ('BENJAMIN', 'CADETE'…).
    Una pasada es de un solo carril: cada uno tiene su número de pasada, su reloj y su parte de
    data-health.json, así que mezclarlos (o no pedir ninguna) para con ValueError, antes de leer nada."""
    cats = tuple(categories or ())
    for carril, suyas in CARRILES.items():
        if cats and all(c in suyas for c in cats):
            return carril
    raise ValueError(f"las categorías de un carril no se mezclan: {', '.join(cats) or '(ninguna)'} "
                     f"(principal: {', '.join(CARRILES['principal'])}; mayores: {', '.join(CARRILES['mayores'])})")


def carril_actual(env=None):
    """El carril de esta pasada por FIFLP_CATS (parse_categories); vacía o sin poner, el principal."""
    env = os.environ if env is None else env
    text = (env.get("FIFLP_CATS") or "").strip()
    return carril_de(parse_categories(text)) if text else "principal"


def categorias_del_carril(carril):
    """Las categorías de un carril (CARRILES); KeyError si no existe."""
    return CARRILES[carril]


def sufijo_tanda(category):
    """El sufijo de la tanda de activación de una categoría ('JUVENIL' → 'juv'; 'BENJAMIN' → '');
    KeyError si ninguna la tiene."""
    for sufijo, cats in TANDAS.items():
        if category in cats:
            return sufijo
    raise KeyError(category)


def categorias_de_tanda(sufijo):
    """Las categorías de la tanda de un sufijo ('cad' → ('CADETE',)); KeyError si no existe."""
    return TANDAS[sufijo]


def web_key(db_name):
    """'ALEVIN' → 'alevin' (la clave de la web)."""
    return (db_name or "").lower()
