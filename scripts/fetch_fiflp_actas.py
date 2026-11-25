#!/usr/bin/env python3
"""Scrape FIFLP actas (lineups + events + staff) for benjamin/prebenjamin
across all 5 seasons, incrementally and resumably.

Saves to scripts/fiflp_actas_<season>_raw.json keyed by CodActa (benjamín y
prebenjamín) y las de cada otra categoría APARTE (alevín, en
scripts/fiflp_actas_<season>_alevin_raw.json: actas_lotes.LOTE_DE_CATEGORIA), cada
lote con su índice y su estado (actas_lotes.py): el histórico alevín en el mismo raw
lo duplicaría y lo acercaría a los límites de GitHub. Una tanda es de UN lote
(tanda_lote: las categorías que mezclan dos se rechazan) y solo escribe los ficheros
de ese lote, los que sube su cadena (una por temporada y lote): dos cadenas nunca
escriben el mismo fichero. Tampoco al refrescar.

Lee como el bot (fiflp_carga.para_tanda: una página vacía solo es el freno si la
federación tampoco sirve otra), con UN navegador y una página para toda la tanda, y
competición a competición: la enumera (enumerar) y en seguida lee sus actas
(leer_actas). Lo que falta va apuntado en el estado (formato 2: status_de), jornada
a jornada: si la federación para (el freno, el tope de peticiones, el plazo, un
runner rechazado), lo que no leyó queda pendiente y la tanda acaba; si sirve otras y
una página no (una página muerta), o una carga y no se entiende (una excepción al
leerla: su tipo, en «motivos» del estado), esa gasta un intento por tanda y, con
fiflp_carga.MAX_INTENTOS, queda «no disponible en la federación», fuera de lo
pendiente. Nada que vino vacío se guarda como leído.

CLI:
  --temporada NN      (required) CodTemporada: 12..22
  --comps "id,id"     (optional) override comp list; otherwise auto-discover
  --categorias LISTA  (optional) 'benjamin,prebenjamin' (por defecto) o 'alevin' (solo
                      Gran Canaria, sin sala): las competiciones del catálogo que se recorren;
                      las de un solo lote
  --lote siempre|alevin (optional) el lote de la tanda (el de su trabajo en historico.py, o el de
                      su grupo de concurrencia en actas-federacion.yml): si las categorías son de
                      otro, para
  --max-actas N       (optional) cap for spike runs
  --max-paginas N     (optional) tope de peticiones a la federación de la tanda (0, sin tope)
  --resumen RUTA      (optional) el resumen de la tanda (fiflp_carga.guardar_resumen; parte
                      «actas:<S>:<lote o siempre>»)
  --dump-fixture COD  (optional) dump acta HTML to scripts/tests/fixtures/
  --estado            (optional) sin navegador: imprime chain_state del lote de la tanda
                      (lo lee actas-federacion.yml para encadenar)

Designed to run only in GitHub Actions (FIFLP blocks the local IP).
"""
import os, sys, re, json, time, random, argparse, threading
from pathlib import Path
from scripts.acta_parser import parse_acta
from scripts import actas_lotes
from scripts.escritura import escribir_atomico

# La lectura del bot (fiflp_carga) importa sus vecinos por su nombre (fiflp_render, escritura): la carpeta de
# scripts/ va en sys.path, al final (no tapa nada), también cuando este módulo se importa como
# scripts.fetch_fiflp_actas o se ejecuta copiado en otra carpeta (las pruebas del workflow).
_SCRIPTS = str(Path(actas_lotes.__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)
import fiflp_carga  # noqa: E402
import cuarentena  # noqa: E402
from fiflp_carga import MAX_INTENTOS, RELANZAR_MIN, guardar_resumen, parada_de  # noqa: E402

# Playwright is only needed at runtime (inside main()). Importing it at module
# level made the Tests CI pytest job red because the runner doesn't install
# Playwright. Lazy-import in main() instead.

# ── Constants ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent   # donde van los raws, índices y estados (las pruebas lo cambian)
# La carpeta de la cuarentena (--carpeta: cuarentena.py): None, lo de siempre. Con ella, raw, índice y estado
# se leen de la cuarentena si están (si no, los publicados: se empieza por lo que ya hay) y se escriben en ella;
# también el raw del otro lote que lee RawStore.
CARPETA = None


def _de(path):
    """De dónde se lee `path` (un raw, un índice o un estado publicados, en HERE): él mismo sin CARPETA; con
    ella, cuarentena.leer (si no está en ningún sitio, el de la cuarentena, que no existe)."""
    if CARPETA is None:
        return path
    return cuarentena.leer(path.name, CARPETA, path.parent) or Path(CARPETA) / path.name


def _a(path):
    """Dónde se escribe `path`: él mismo sin CARPETA; con ella, en la cuarentena (cuarentena.escribir)."""
    return path if CARPETA is None else cuarentena.escribir(path.name, CARPETA, path.parent)
BASE = "https://www.fiflp.com/pnfg/NPcd"
UA   = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537")

SEASON_NAME = {
    # 12-16: temporadas anteriores a la web (2016-17 a 2020-21), solo para descargar sus datos.
    # 2015-16 (11) no tiene benjamín ni prebenjamín en la federación (lo dice una sonda).
    "12": "2016-2017",
    "13": "2017-2018",
    "14": "2018-2019",
    "15": "2019-2020",
    "16": "2020-2021",
    "17": "2021-2022",
    "18": "2022-2023",
    "19": "2023-2024",
    "20": "2024-2025",
    "21": "2025-2026",
    # La temporada en curso: las actas que el bot (update_fiflp) ya no relee, p. ej. las de una fase
    # dada de alta tarde (alevín, Fuerteventura).
    "22": "2026-2027",
}

# Pre-shipped comp lists reused from existing scrapers.
# Seasons 17 and 18 use auto-discover at runtime.
KNOWN_COMPS = {
    "21": [c["id"] for c in
           __import__("scripts.fetch_fiflp", fromlist=["COMPETITIONS"]).COMPETITIONS],
    "20": [c["id"] for c in
           __import__("scripts.fetch_fiflp_2425", fromlist=["ALL_COMPETITIONS"]).ALL_COMPETITIONS],
    "19": [c["id"] for c in
           __import__("scripts.fetch_fiflp_2324", fromlist=["ALL_COMPETITIONS"]).ALL_COMPETITIONS],
}

# Regex to find CodActa anchors in page HTML
ACTA_HREF = re.compile(r"NFG_CmpPartido[^\"'\s]*CodActa=(\d+)", re.IGNORECASE)


def _categorias():
    try:
        from scripts import categorias
    except ImportError:
        import categorias
    return categorias


def catalog_comps(season_code, categories=None, catalog=None):
    """Ids de las competiciones de fútbol 7/8 de la temporada de las categorías dadas ('ALEVIN',
    'BENJAMIN'…; por defecto benjamín y prebenjamín), del catálogo y según
    categorias.category_of (sin sala ni alevín de Lanzarote o Fuerteventura); [] si el catálogo
    no la tiene. `catalog`: otro catálogo ya leído (las pruebas, el congelado); por defecto, el
    del repositorio."""
    C = _categorias()
    categories = categories or C.DEFAULT_CATEGORIES
    entry = _catalog_entry(season_code, catalog)
    return [c["id"] for c in entry.get("all", []) if C.category_of(c["name"]) in categories]


def _catalog_entry(season_code, catalog=None):
    if season_code not in SEASON_NAME:
        return {}
    if catalog is None:
        path = Path(__file__).parent / "fiflp_comps_catalog.json"
        if not path.exists():
            return {}
        catalog = json.loads(path.read_text(encoding="utf-8"))
    return catalog.get(SEASON_NAME[season_code]) or {}


def catalog_names(season_code):
    """{id: nombre} de las competiciones de la temporada en el catálogo ({} si no la tiene)."""
    return {str(c["id"]): c["name"] for c in _catalog_entry(season_code).get("all", [])}


def comp_lotes(season_code, comps, categories=None, names=None):
    """{competición: lote} (actas_lotes: '' benjamín y prebenjamín, 'alevin' alevín), por el nombre
    de la competición en el catálogo o en `names` (el desplegable que lee discover_comps). Una que
    no está en ninguno va al lote de las categorías pedidas si son de uno solo; si son de los dos,
    no se sabe dónde guardarla y se para (ValueError): mejor no bajar que mezclar."""
    categories = categories or _categorias().DEFAULT_CATEGORIES
    known = {**catalog_names(season_code), **{str(k): v for k, v in (names or {}).items()}}
    asked = actas_lotes.lotes_of(categories)
    out = {}
    for comp in comps:
        lote = actas_lotes.lote_of_name(known.get(str(comp)))
        if lote is None:
            if len(asked) != 1:
                raise ValueError(f"competición {comp}: no está en el catálogo y las categorías "
                                 f"({', '.join(categories)}) son de los dos lotes; "
                                 "pide --categorias alevin o benjamin,prebenjamin")
            lote = asked[0]
        out[str(comp)] = lote
    return out


# --lote de la CLI (historico.py lo pasa con el lote de su trabajo; actas-federacion.yml, con el de su grupo de
# concurrencia): «siempre», el de benjamín y prebenjamín, y cada lote de actas_lotes.LOTES por su nombre.
LOTE_ARG = {"siempre": "", **{lote: lote for lote in actas_lotes.LOTES if lote}}


def _lote_label(lote):
    return lote or "benjamín/prebenjamín"


def tanda_lote(season_code, categories=None, comps=None, names=None, expected=None):
    """El lote de una tanda, que es UNO: el de sus categorías. Una cadena de actas-federacion.yml
    escribe y sube solo los ficheros de su lote (su grupo de concurrencia es por temporada y lote):
    si escribiera los del otro, chocaría con la cadena de ese lote y una de las dos perdería su
    tanda al subir. Por eso para (ValueError) si las categorías mezclan los dos lotes, si una
    competición de --comps es del otro lote (por su nombre en el catálogo o en `names`) o si el lote
    no es el que espera la cadena (`expected`, el de --lote)."""
    categories = categories or _categorias().DEFAULT_CATEGORIES
    lotes = actas_lotes.lotes_of(categories)
    if len(lotes) != 1:
        raise ValueError(f"las categorías ({', '.join(categories)}) son de los dos lotes: una tanda baja "
                         "las de uno solo; lanza alevin y benjamin,prebenjamin por separado")
    lote = lotes[0]
    if comps:
        other = sorted(c for c, lt in comp_lotes(season_code, comps, categories, names).items() if lt != lote)
        if other:
            raise ValueError(f"competiciones que no son del lote de las categorías ({_lote_label(lote)}): "
                             f"{', '.join(other)}")
    if expected is not None and expected != lote:
        raise ValueError(f"la cadena es del lote {_lote_label(expected)} y las categorías "
                         f"({', '.join(categories)}) del {_lote_label(lote)}")
    return lote


def index_path(season_code, lote=""):
    """Índice de actas enumeradas (cod_acta → comp, grupo, jornada): una tanda
    encadenada no vuelve a recorrer todas las jornadas de la temporada. Uno por lote."""
    return HERE / actas_lotes.file_name(SEASON_NAME[season_code], "index", lote)


def status_path(season_code, lote=""):
    return HERE / actas_lotes.file_name(SEASON_NAME[season_code], "status", lote)


def chain_state(season_code, lote=""):
    """Lo que queda de la tanda por el estado de su lote: la regla de actas-federacion.yml para lanzar otra
    tanda o pasar a la temporada siguiente. Sin estado, {"pending": 1, "stuck": 0, "lote"}: que siga.
    Con el estado nuevo (formato 2), {"pending", "stuck", "lote", "parada", "servidas"}: atascada (stuck 1) si
    la federación paró la tanda (el freno, el tope, un runner rechazado…) habiendo servido menos de
    RELANZAR_MIN páginas. Así la cadena deja de relanzarse contra el freno; una tanda con lo pendiente de una
    página muerta no está atascada (cada tanda le gasta un intento). Con el antiguo, como hasta noviembre de
    2026: atascada si no trajo ninguna acta ni dejó competiciones sin enumerar."""
    try:
        status = json.loads(_de(status_path(season_code, lote)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pending": 1, "stuck": 0, "lote": lote}
    pending = int(status.get("pending", 1))
    if status.get("formato") == 2:
        parada = status.get("parada")
        servidas = int((status.get("paginas") or {}).get("servidas") or 0)
        stuck = parada is not None and servidas < RELANZAR_MIN
        return {"pending": pending, "stuck": int(stuck), "lote": lote, "parada": parada, "servidas": servidas}
    stuck = int(status.get("fetched", 1)) == 0 and not int(status.get("unenumerated_comps") or 0)
    return {"pending": pending, "stuck": int(stuck), "lote": lote}


def needs_refresh(acta):
    """Un acta aplanada leída antes de que se guardara todo el cuerpo técnico y el
    código del campo (fiflp_acta.STAFF_VERSION): --refrescar la vuelve a leer. Una
    cuya relectura salió peor (`staff_refresh_failed`) no se vuelve a pedir."""
    try:
        from scripts.fiflp_acta import STAFF_VERSION
    except ImportError:
        from fiflp_acta import STAFF_VERSION
    return (isinstance(acta, dict) and "consistent" in acta and (acta.get("staff_v") or 0) < STAFF_VERSION
            and not acta.get("staff_refresh_failed"))


def keep_old_on_refresh(old, new):
    """En --refrescar, la relectura solo sustituye al acta si es tan buena como
    ella: aplanada y, si la vieja cuadraba, cuadrando también."""
    if not isinstance(old, dict) or "consistent" not in old:
        return False
    return "consistent" not in new or (old.get("consistent") and not new.get("consistent"))


def needs_rescrape(acta):
    """Las actas leídas con acta_parser, sin aplanar, traen la cabecera mal
    descifrada y sin minutos: se vuelven a leer. Una que
    ya se releyó con el lector aplanado y aun así no se dejó aplanar
    (`rescrape_failed`: la página de algunos partidos no tiene la forma de acta)
    no se vuelve a pedir: si no, cada tanda la leería otra vez y la cadena no
    pararía nunca."""
    return isinstance(acta, dict) and "consistent" not in acta and not acta.get("rescrape_failed")


# ── Low-level helpers ─────────────────────────────────────────────────────────

def delay(extra=0):
    time.sleep(random.uniform(2.0, 3.5) + extra)


def goto(page, url, retries=3):
    """Carga `url` (hasta `retries` intentos) y espera 2,5 s. Por fiflp_render.goto: un reintento, o
    una URL que el navegador ya pidió, pide su documento a la red y no a la caché HTTP: la federación
    los guarda 5 min (y, con las mismas cabeceras, también su página vacía). Solo lo usan las
    estrategias manuales (NFG_LstPartidos, las páginas de los equipos) y discover_comps sin Federacion:
    la tanda lee por la Federacion (enumerar, fetch_and_parse_acta), que no da por buena una vacía."""
    try:
        from scripts import fiflp_render
    except ImportError:
        import fiflp_render
    for attempt in range(retries):
        try:
            fiflp_render.goto(page, url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            return True
        except Exception:
            time.sleep(10 * (attempt + 1))
    return False


def raw_path(season_code, lote=""):
    """scripts/fiflp_actas_<S>_raw.json (benjamín y prebenjamín) o, la del lote 'alevin',
    scripts/fiflp_actas_<S>_alevin_raw.json."""
    return HERE / actas_lotes.file_name(SEASON_NAME[season_code], "raw", lote)


def is_empty_acta(acta):
    """True when a parsed acta carries no data at all (the FIFLP anti-scrape
    empty frameset parsed into an all-None header with empty lineups).

    Such entries must never be treated as successfully scraped: persisting
    them poisons the resume state and the acta is skipped forever.
    """
    if not acta:
        return True
    h = acta.get("header") or {}
    lineups = acta.get("lineups") or {}
    return (
        all(h.get(k) is None for k in ("season", "home_team", "away_team", "date"))
        and not lineups.get("home")
        and not lineups.get("away")
    )


def load_raw(season_code, lote=""):
    p = _de(raw_path(season_code, lote))
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    # Purge empty entries persisted by older runs so the resume logic treats
    # them as pending again (they were anti-scrape blanks, not real data).
    dead = [k for k, v in data.items() if is_empty_acta(v)]
    for k in dead:
        del data[k]
    if dead:
        print(f"  purged {len(dead)} empty acta(s) from resume state — will retry")
    return data


def save_raw(season_code, data, lote=""):
    escribir_atomico(_a(raw_path(season_code, lote)), json.dumps(data, ensure_ascii=False, indent=2))


def acta_lote(acta, default=None):
    """El lote de un acta por la competición de su cabecera, si la dice; si no, `default`."""
    competition = ((acta or {}).get("header") or {}).get("competition")
    lote = actas_lotes.lote_of_name(competition) if competition else None
    return default if lote is None else lote


class RawStore:
    """Las actas ya descargadas de una temporada, para una tanda de un lote. Solo escribe el raw de
    su lote (el de su cadena); los de los otros lotes solo los lee, para no volver a leer un acta
    que ya está en ellos.

    Un acta en el raw que no es el suyo (la dejó una tanda de antes de partir los raws, que bajaba
    las de alevín al de siempre) pasa sola al suyo, cada cadena con sus ficheros: la tanda del lote
    del acta la ADOPTA (get: la copia a su raw sin volver a leerla) y la tanda del lote donde estaba
    la SUELTA (al cargar: la quita del suyo si su cabecera es de otro lote y ya está en el raw de
    ese lote). Mientras tanto está en los dos y la importación da lo mismo (import_fiflp_actas:
    la misma acta, el mismo partido)."""

    def __init__(self, season_code, lote="", log=print):
        self.season, self.lote, self.log = season_code, lote, log
        self.data = load_raw(season_code, lote)
        self._others = {}
        self.dirty = False
        self.adopted = 0
        self.released = self._release()

    def other(self, lote):
        if lote not in self._others:
            self._others[lote] = load_raw(self.season, lote)
        return self._others[lote]

    def _release(self):
        gone = []
        for cod, acta in self.data.items():
            lote = acta_lote(acta)
            if lote not in (None, self.lote) and cod in self.other(lote):
                gone.append(cod)
        for cod in gone:
            del self.data[cod]
        if gone:
            self.dirty = True
            self.log(f"  {len(gone)} acta(s) de otro lote ya en su raw: se quitan de "
                     f"{raw_path(self.season, self.lote).name}")
        return len(gone)

    def get(self, cod):
        """(lote, acta) del acta `cod` para la tanda: la de su raw (lote, el de la tanda); si solo
        está en el raw de otro lote, la adopta (la copia al suyo), salvo que su cabecera diga ese
        otro lote (está donde debe: no es de esta tanda; (ese lote, acta)). (None, None) si no está
        en ninguno."""
        if cod in self.data:
            return self.lote, self.data[cod]
        for lote in actas_lotes.LOTES:
            if lote == self.lote or cod not in self.other(lote):
                continue
            acta = self.other(lote)[cod]
            if acta_lote(acta) == lote:
                return lote, acta
            self.data[cod] = acta
            self.dirty = True
            self.adopted += 1
            return self.lote, acta
        return None, None

    def put(self, cod, acta):
        self.data[cod] = acta
        self.dirty = True

    def save(self, force=False):
        if self.dirty or force:
            save_raw(self.season, self.data, self.lote)
        self.dirty = False


def anotar_intento(intentos, no_disponible, clave):
    """Una página que no cargó aunque la federación servía otras (o un acta que cargó sin datos): un intento más
    de `clave` («comp:C», «grupo:C:G», «jornada:C:G:J», «acta:N»; uno por tanda, porque cada una se pide una vez
    en cada tanda). Con MAX_INTENTOS, sale de `intentos` y pasa a `no_disponible` (fuera de lo pendiente): da
    True. Si la federación paró, no se llama: lo que no leyó sigue pendiente sin gastar nada."""
    n = int(intentos.get(clave) or 0) + 1
    if n >= MAX_INTENTOS:
        intentos.pop(clave, None)
        if clave not in no_disponible:
            no_disponible.append(clave)
        return True
    intentos[clave] = n
    return False


class Collector:
    """on_result de leer_actas: cada acta leída va al raw del lote de la tanda (el de su competición), nunca al
    de otro; si su cabecera dice el otro lote, se avisa (no se escribe el raw de otra cadena). Con --refrescar,
    la relectura que sale peor se descarta y la vieja queda marcada. Cuenta las actas aplanadas nuevas (el
    avance de la cadena) y guarda cada `save_every` (y, con `on_save`, el estado).
    Un acta que no se leyó: si la federación paró (parada_de(F)), nada (sigue pendiente); si no (una página
    muerta, que cargó sin datos: is_empty_acta, o que cargó y no se entiende: `motivo`, el tipo de la excepción),
    un intento (anotar_intento); el motivo, en `motivos` (nunca el texto de la excepción: puede llevar un
    nombre)."""

    def __init__(self, store, refrescar=False, save_every=25, total=0, log=print, F=None, intentos=None,
                 no_disponible=None, on_save=None, motivos=None):
        self.store, self.refrescar, self.save_every, self.total, self.log = store, refrescar, save_every, total, log
        self.F, self.on_save = F, on_save
        self.intentos = {} if intentos is None else intentos
        self.no_disponible = [] if no_disponible is None else no_disponible
        self.motivos = {} if motivos is None else motivos
        self.lock = threading.Lock()
        self.fetched = 0
        self.asked = 0                    # las actas pedidas en la tanda (--max-actas)
        self.started = time.time()

    def _fallo(self, cod):
        if anotar_intento(self.intentos, self.no_disponible, f"acta:{cod}"):
            self.log(f"  ! acta {cod}: no disponible en la federación ({MAX_INTENTOS} tandas sin cargar)")

    def __call__(self, t, acta, motivo=None):
        cod = t["cod_acta"]
        if acta is None:
            if parada_de(self.F) is None:
                if motivo:
                    self.motivos[f"acta:{cod}"] = motivo
                self._fallo(cod)          # la federación sirve otras y esta no (o no se entiende): una muerta
            return
        if is_empty_acta(acta):
            # Cargó, pero sin nada: nunca como leída (envenenaría la reanudación); un intento.
            self.log(f"  ! acta {cod}: sin datos — no se guarda (intento)")
            self._fallo(cod)
            return
        acta["cod_acta"] = int(cod)
        acta["enumeration"] = {"comp_id": t["comp_id"], "grupo": t["grupo"], "jornada": t["jornada"]}
        flat = "consistent" in acta
        if not flat:
            acta["rescrape_failed"] = True     # leída ya con el lector nuevo: no se vuelve a pedir
        mine = self.store.lote
        with self.lock:
            old = self.store.data.get(cod)
            if self.refrescar and keep_old_on_refresh(old, acta):
                # La relectura salió peor que la que ya había: se queda la vieja y no se vuelve a pedir.
                old["staff_refresh_failed"] = True
                self.store.dirty = True
                return
            if acta_lote(acta, mine) != mine:
                self.log(f"  ! acta {cod}: su cabecera es del lote {_lote_label(acta_lote(acta))} y su "
                         f"competición ({t['comp_id']}) del {_lote_label(mine)}: se guarda en el de la tanda")
            self.store.put(cod, acta)
            # Solo cuenta como acta nueva la que se dejó aplanar: la cadena sigue mientras avanza.
            self.fetched += flat
            # save every 25 actas to survive crashes
            if flat and self.fetched % self.save_every == 0:
                self.store.save()
                if self.on_save:
                    self.on_save()
                rate = (time.time() - self.started) / self.fetched
                self.log(f"    progress: {self.fetched}/{self.total} (saved; {rate:.1f} s por acta)")


# ── Comp discovery ────────────────────────────────────────────────────────────

def discover_comps(page, season_code, categories=None, names=None, F=None):
    """Read the comp dropdown from NFG_CmpJornada and keep those of `categories`
    (benjamín/prebenjamín by default; categorias.category_of). `names`, si se da,
    recibe {id: nombre} de las que se quedan (comp_lotes las reparte por lote). Con `F` (la
    Federacion de la tanda), por F.goto; si no, por goto."""
    url = f"{BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season_code}"
    if not (F.goto(page, url) if F is not None else goto(page, url)):
        return []
    opts = page.evaluate("""
        () => {
            const s = document.querySelector('select[name="competicion"]');
            if (!s) return [];
            return Array.from(s.options)
                .filter(o => o.value && o.value !== '0')
                .map(o => ({value: o.value, text: o.text.trim().toUpperCase()}));
        }""")
    C = _categorias()
    categories = categories or C.DEFAULT_CATEGORIES
    keep = [o["value"] for o in opts if C.category_of(o["text"]) in categories]
    if names is not None:
        names.update({o["value"]: o["text"] for o in opts if o["value"] in keep})
    print(f"  discovered {len(keep)} comps ({', '.join(categories)}) for season {season_code}")
    return keep


# ── Enumeration: Strategy 1 — main path (comp→grupo→jornada→anchor) ──────────

def _options(page, name, tries=4):
    """Valores del desplegable `name` (grupo, jornada); FIFLP a veces tarda en servirlo."""
    for _ in range(tries):
        try:
            values = page.evaluate(f"""() => Array.from(document.querySelectorAll('select[name="{name}"] option'))
                .filter(o => o.value && o.value !== '0').map(o => o.value)""")
        except Exception:
            values = []
        if values:
            return values
        page.wait_for_timeout(3000)
    return []


# --grupos: solo estos grupos. Entradas separadas por comas: 'GRUPO 5' (en todas
# las competiciones) o '54422885:GRUPO 13' (en esa); también vale el CodGrupo.
GROUP_FILTER = []


def _wanted(comp_id, value, text):
    if not GROUP_FILTER:
        return True
    for entry in GROUP_FILTER:
        comp, _, name = entry.rpartition(":")
        if comp and comp != str(comp_id):
            continue
        if name.strip().upper() in (str(value).upper(), (text or "").strip().upper()):
            return True
    return False


def _completa(ledger):
    """¿Enumerada la competición? Con su lista de grupos y ningún grupo con jornadas por leer."""
    return ledger.get("grupos") is not None and not ledger.get("pendientes")


def enumerar(page, F, season, comp_id, ledger, index, intentos, no_disponible, log=print, motivos=None):
    """Enumera las actas de una competición pidiendo solo lo pendiente de `ledger` (su entrada en la
    «enumeracion» del estado: {"grupos": [[valor, nombre]] o None, "pendientes": {grupo: [jornadas] o None}},
    que va actualizando) y añade a `index` las actas de cada jornada leída. Por URL directa: comp → grupo
    (&CodGrupo=G) → jornada (&CodGrupo=G&CodJornada=J). Antes elegía grupo con select_option y jornada con
    BuscarPartidos sobre el formulario de búsqueda, que la página trae OCULTO (#portlet_search, display:none):
    select_option daba timeout en todos los grupos salvo el primero (2025-26: solo el grupo 1 del prebenjamín).
    Una jornada que carga sin enlaces a actas está leída (existen: 2018-19 entera). La que no carga: si la
    federación paró (parada_de), "parada" y lo que falta sigue en `ledger`; si sirve otras, un intento (clave
    «comp:C», «grupo:C:G» o «jornada:C:G:J»: anotar_intento) y, con MAX_INTENTOS, sale de lo pendiente. Lo
    mismo una competición o un grupo cuya página carga sin desplegable, y una jornada que carga y no se entiende
    (una excepción al leer sus enlaces: su tipo, en `motivos`). Sin esperas entre intentos (las de 20-60 s de
    antes): lo que falta lo pide la tanda siguiente.
    Con --grupos (GROUP_FILTER), solo esos grupos; los demás siguen pendientes.
    Da "completa", "pendiente" o "parada"."""
    base = f"{F.BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}&CodCompeticion={comp_id}"
    if ledger.get("grupos") is None:
        valores = []
        if F.goto(page, base):
            try:
                labels = dict(page.evaluate("""() => Array.from(document.querySelectorAll('select[name="grupo"] option'))
                    .map(o => [o.value, o.text.trim()])""") or [])
            except Exception:
                labels = {}
            valores = _options(page, "grupo")
            F.delay()
        elif parada_de(F) is not None:
            return "parada"
        if not valores:
            log(f"  ! comp {comp_id}: sin grupos")
            if anotar_intento(intentos, no_disponible, f"comp:{comp_id}"):
                ledger.update(grupos=[], pendientes={})
            return "completa" if _completa(ledger) else "pendiente"
        grupos = [[g, labels.get(g, "")] for g in valores]
        ledger.update(grupos=grupos, pendientes={g: None for g, _ in grupos})
    pendientes = ledger.setdefault("pendientes", {})
    for grupo, nombre in ledger["grupos"]:
        if grupo not in pendientes or not _wanted(comp_id, grupo, nombre):
            continue
        if pendientes[grupo] is None:
            valores = []
            if F.goto(page, f"{base}&CodGrupo={grupo}"):
                valores = _options(page, "jornada")
                F.delay()
            elif parada_de(F) is not None:
                return "parada"
            if not valores:
                log(f"  WARN season={season} comp={comp_id} grupo={grupo} jornadas:0")
                if anotar_intento(intentos, no_disponible, f"grupo:{comp_id}:{grupo}"):
                    del pendientes[grupo]
                continue
            pendientes[grupo] = list(valores)
        jornadas = pendientes[grupo]
        for jornada in list(jornadas):
            if not F.goto(page, f"{base}&CodGrupo={grupo}&CodJornada={jornada}"):
                if parada_de(F) is not None:
                    return "parada"
                if anotar_intento(intentos, no_disponible, f"jornada:{comp_id}:{grupo}:{jornada}"):
                    jornadas.remove(jornada)
                continue
            try:
                enlaces = [m.group(1) for m in ACTA_HREF.finditer(page.content())]
            except Exception as ex:
                # Antes la tanda acababa con error en esta jornada cada vez. El tipo, nunca el texto.
                if parada_de(F) is not None:
                    return "parada"
                log(f"  ! comp {comp_id} grupo {grupo} jornada {jornada}: no se entiende ({type(ex).__name__})")
                if motivos is not None:
                    motivos[f"jornada:{comp_id}:{grupo}:{jornada}"] = type(ex).__name__
                if anotar_intento(intentos, no_disponible, f"jornada:{comp_id}:{grupo}:{jornada}"):
                    jornadas.remove(jornada)
                F.delay()
                continue
            for cod in enlaces:
                index[cod] = {"comp_id": comp_id, "grupo": grupo, "jornada": jornada}
            jornadas.remove(jornada)
            F.delay()
        if not jornadas:
            del pendientes[grupo]
    return "completa" if _completa(ledger) else "pendiente"


# ── Enumeration: Strategy 2 — NFG_LstPartidos ────────────────────────────────

def enumerate_actas_lstpartidos(page, season, comp_id):
    """Strategy 2: scrape NFG_LstPartidos for the comp."""
    out = []
    url = (f"{BASE}/NFG_LstPartidos?cod_primaria=1000120"
           f"&CodTemporada={season}&CodCompeticion={comp_id}")
    if not goto(page, url):
        return out
    html = page.content()
    for m in ACTA_HREF.finditer(html):
        out.append({
            "cod_acta": m.group(1),
            "comp_id":  comp_id,
            "grupo":    None,
            "jornada":  None,
        })
    return list({r["cod_acta"]: r for r in out}.values())


# ── Enumeration: Strategy 3 — walk team pages ────────────────────────────────

def enumerate_actas_via_teams(page, season, comp_id):
    """Strategy 3: list teams in the comp, then walk each team's match list."""
    out = []
    url = (f"{BASE}/NFG_CmpJornada?cod_primaria=1000120"
           f"&CodTemporada={season}&CodCompeticion={comp_id}")
    if not goto(page, url):
        return out
    team_links = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href*="NFG_CmpEquipo"]'))
                   .map(a => a.getAttribute('href'))""")
    for href in set(team_links or []):
        team_url = BASE + "/" + href.lstrip("./")
        if not goto(page, team_url):
            continue
        html = page.content()
        for m in ACTA_HREF.finditer(html):
            out.append({
                "cod_acta": m.group(1),
                "comp_id":  comp_id,
                "grupo":    None,
                "jornada":  None,
            })
        delay()
    return list({r["cod_acta"]: r for r in out}.values())


# ── Enumeration: Strategy 4 — brute-force range scan ─────────────────────────

def enumerate_actas_by_range(page, F, season, comp_id, lo, hi):
    """Strategy 4: scan CodActa range, keep those whose header season matches.
    Expensive; use only for comps that strategies 1-3 cannot enumerate."""
    out = []
    target_season = SEASON_NAME[season]
    for cod in range(lo, hi + 1):
        try:
            acta = fetch_and_parse_acta(page, str(cod), F)
        except Exception:
            acta = None                   # como hasta ahora: la que no se entiende, se salta
        if not acta:
            continue
        s = (acta.get("header", {}).get("season") or "").replace("/", "-")
        if s == target_season:
            out.append({
                "cod_acta": str(cod),
                "comp_id":  comp_id,
                "grupo":    None,
                "jornada":  None,
            })
        delay()
    return out


# ── Fetch + parse single acta ─────────────────────────────────────────────────

def _fetch_acta_html(page, cod_acta, F):
    """Carga un acta por F.goto (la Federacion de la tanda) y da el HTML del frameset con el de sus marcos, o
    '' si no cargó."""
    url = (f"{BASE}/NFG_CmpPartido?cod_primaria=1000120"
           f"&CodActa={cod_acta}&cod_acta={cod_acta}")
    if not F.goto(page, url):
        return ""
    # Frameset actas need a longer settle: the content frame issues its own
    # request after the outer frameset loads. 4s tracks the fixture-capture timing
    # that gave a valid parse.
    page.wait_for_timeout(4000)
    html = page.content()
    for fr in page.frames:
        if fr is page.main_frame:
            continue
        try:
            html += "\n<!--FRAME " + fr.url + "-->\n" + fr.content()
        except Exception:
            pass
    return html


def _fixtures_dir():
    """Donde van los HTML de diagnóstico: scripts/tests/fixtures (junto a HERE: las pruebas lo cambian)."""
    return HERE / "tests" / "fixtures"


def fetch_and_parse_acta(page, cod_acta, F, dump_fixture_for=None):
    """Una sola carga del acta por F.goto, optionally dump fixture, parse. None si no cargó.

    Hasta noviembre de 2026 una vacía se reintentaba aquí dos veces (8 y 12 s después): con el freno de octubre
    salía vacía siempre. Ahora decide la Federacion, como en el bot: si es el freno de verdad, la tanda para
    (parada_de) y el acta sigue pendiente; si la federación sirve otras, es una página muerta (`dead` + 1) y
    Collector le gasta un intento. Lo mismo un acta que carga sin datos (is_empty_acta, en Collector). Una que
    carga y no se entiende lanza su excepción (antes daba None y no se sabía por qué): leer_actas le gasta el
    intento con el tipo como motivo. Una URL que el navegador ya pidió va a la red, no a la caché HTTP
    (fiflp_render.goto, por F.goto).
    """
    html = _fetch_acta_html(page, cod_acta, F)
    if not html:
        return None
    # "first" sentinel dumps whatever the first acta we visit is — useful when
    # we don't yet know a good CodActa to target for diagnosis.
    if dump_fixture_for and (
        str(dump_fixture_for) == str(cod_acta) or str(dump_fixture_for).lower() == "first"
    ):
        fix_dir = _fixtures_dir()
        fix_dir.mkdir(parents=True, exist_ok=True)
        out_path = fix_dir / f"acta_live_{cod_acta}.html"
        escribir_atomico(out_path, html)
        print(f"  dumped fixture: {out_path}")
    try:
        # Primero el acta tal como se ve (fiflp_render aplana la ofuscación de
        # marcadores, parciales y minutos; fiflp_acta la lee y comprueba que los
        # parciales cuadran). Si la página no tiene la forma de acta moderna,
        # el parser estático de siempre.
        result = None
        try:
            try:
                from scripts.fiflp_render import flatten
                from scripts.fiflp_acta import parse_flat_acta
            except ImportError:
                from fiflp_render import flatten
                from fiflp_acta import parse_flat_acta
            flatten(page)
            flat = parse_flat_acta(page.content())
            if flat["header"].get("home_team") and flat["lineups"]["home"]:
                result = flat
        except Exception as ex:
            print(f"  ! aplanado acta={cod_acta}: {type(ex).__name__}")
        if result is None:
            result = parse_acta(html)
    except Exception as ex:
        print(f"  ! parse error acta={cod_acta}: {type(ex).__name__}")
        raise
    # Auto-diagnostic: if every header field is None and lineups are empty, the
    # parser silently produced nothing. Save the HTML for one occurrence per
    # session so we can see what FIFLP actually served.
    h = result.get("header") or {}
    if all(h.get(k) is None for k in ("season", "home_team", "away_team", "date")) \
       and not result.get("lineups", {}).get("home") \
       and not getattr(fetch_and_parse_acta, "_dumped_failure", False):
        fix_dir = _fixtures_dir()
        fix_dir.mkdir(parents=True, exist_ok=True)
        out_path = fix_dir / f"acta_failed_{cod_acta}.html"
        escribir_atomico(out_path, html)
        print(f"  ! parse failed silently — dumped HTML to {out_path}")
        fetch_and_parse_acta._dumped_failure = True
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser(
        description="Scrape FIFLP actas for benjamín/prebenjamín."
    )
    ap.add_argument("--temporada", required=True, choices=list(SEASON_NAME),
                    help="CodTemporada: 12..22")
    ap.add_argument("--comps", default="",
                    help="Optional comma-separated comp IDs (override auto-discovery)")
    ap.add_argument("--categorias", default="",
                    help="Categorías del catálogo: 'benjamin,prebenjamin' (por defecto) o 'alevin'")
    ap.add_argument("--max-actas", type=int, default=0,
                    help="Cap on number of actas to process (0 = unlimited)")
    ap.add_argument("--max-minutes", type=int, default=0,
                    help="Minutos de descarga antes de parar limpio (0 = 330)")
    ap.add_argument("--max-paginas", type=int, default=0,
                    help="Tope de peticiones a la federación de la tanda (0 = sin tope)")
    ap.add_argument("--resumen", default="",
                    help="Dónde escribir el resumen de la tanda (JSON: fiflp_carga.guardar_resumen)")
    ap.add_argument("--reindex", action="store_true",
                    help="Volver a enumerar aunque haya índice (una fase nueva publicada)")
    ap.add_argument("--grupos", default="",
                    help="Solo estos grupos: 'GRUPO 5', '54422885:GRUPO 13' o el CodGrupo, separados por comas")
    ap.add_argument("--dump-fixture", default="",
                    help="CodActa whose raw HTML to dump to scripts/tests/fixtures/")
    ap.add_argument("--refrescar", action="store_true",
                    help="Volver a leer las actas ya descargadas sin todo el cuerpo técnico (needs_refresh)")
    ap.add_argument("--lote", choices=list(LOTE_ARG), default=None,
                    help="El lote de la cadena (su grupo de concurrencia): para si las categorías son de otro")
    ap.add_argument("--carpeta", default="",
                    help="La cuarentena (scripts/historico): leer y escribir raw, índice y estado allí")
    ap.add_argument("--estado", action="store_true",
                    help="Sin navegador: imprime en JSON lo que queda del lote de la tanda (chain_state)")
    return ap.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def _launch(pw):
    """Chromium para leer la federación: sin la publicidad (colgaba la carga de cada acta) ni lo demás
    ajeno a la federación, sin imágenes y CON la caché HTTP (fiflp_render.fiflp_launch_args; sin
    page.route, que la desactiva: cada acta volvía a pedir los ~20 scripts y las hojas de la federación).
    Un navegador, con un contexto y una página para toda la tanda: sus scripts se piden una vez."""
    try:
        from scripts.fiflp_render import fiflp_launch_args
    except ImportError:
        from fiflp_render import fiflp_launch_args
    return pw.chromium.launch(headless=True, args=fiflp_launch_args())


def federacion(minutos, max_paginas):
    """La Federacion de la tanda: la lectura del bot (fiflp_carga.para_tanda, con el raspador de siempre), sin
    esperas del freno, con su plazo y su tope de peticiones; la nube, la de la máquina. Las pruebas la cambian
    por la de la federación de mentira."""
    from scripts import fetch_fiflp_2425
    return fiflp_carga.para_tanda(fetch_fiflp_2425, minutos, max_paginas)


def leer_actas(page, F, pending, over, on_result, dump_fixture=""):
    """Lee las actas de `pending`, en su orden, con UN navegador (la página de la tanda), hasta que over() o
    hasta que la federación pare (parada_de(F)). on_result(target, acta) con cada una (None: no cargó).
    Sustituye a fetch_parallel (varios navegadores sobre una cola): con el intervalo de 7 s de la Federacion,
    un runner de Azure ya lee ~500 páginas por hora, más de lo que da el tope del día en una tanda; dos
    navegadores se saltarían el intervalo (el doble de carga) sin que haga falta.
    Un acta que cargó y no se entiende (una excepción al leerla o interpretarla): on_result(target, None,
    motivo=<tipo de la excepción>), como una muerta (Collector le gasta un intento si la federación sirve). Antes
    se saltaba sin apuntar nada: pendiente para siempre, con la tanda en verde. El tipo, nunca el texto."""
    for t in pending:
        if over() or parada_de(F) is not None:
            return
        try:
            acta = fetch_and_parse_acta(page, t["cod_acta"], F, dump_fixture or None)
        except Exception as ex:
            print(f"  ! acta {t['cod_acta']}: no se entiende ({type(ex).__name__})")
            on_result(t, None, motivo=type(ex).__name__)
            F.delay()
            continue
        on_result(t, acta)
        F.delay()


def status_de(season, comps, enumeracion, objetivos, wanted, store, collector, intentos, no_disponible, F):
    """El estado del lote, formato 2. `pending`: lo que falta de las competiciones de la tanda (las actas por
    leer, las jornadas y los grupos sin leer y las competiciones sin lista de grupos), sin lo no disponible."""
    actas = sum(1 for t in objetivos if f"acta:{t['cod_acta']}" not in no_disponible and wanted(t["cod_acta"]))
    ledgers = [enumeracion[c] for c in comps]
    jornadas = sum(len(v) for led in ledgers for v in (led.get("pendientes") or {}).values() if v)
    grupos = sum(v is None for led in ledgers for v in (led.get("pendientes") or {}).values())
    sin_lista = sum(led.get("grupos") is None for led in ledgers)
    return {"formato": 2, "season": SEASON_NAME[season], "enumerated": len(objetivos), "in_raw": len(store.data),
            "fetched": collector.fetched, "pending": actas + jornadas + grupos + sin_lista,
            "actas_por_leer": actas, "jornadas_por_leer": jornadas, "grupos_por_leer": grupos,
            "unenumerated_comps": sin_lista, "no_disponible": no_disponible, "intentos": intentos,
            # El motivo (el tipo de la excepción) de lo que no se entendió, solo de lo que sigue en intentos o
            # no disponible (lo que después se leyó bien ya no tiene motivo).
            "motivos": {k: v for k, v in sorted(collector.motivos.items()) if k in intentos or k in no_disponible},
            "enumeracion": enumeracion, "paginas": {"pedidas": F.pages, "servidas": F.served},
            "parada": parada_de(F)}


def _sin_enumeracion(comps, intentos, no_disponible):
    """--reindex: lo no disponible y los intentos de la enumeración de esas competiciones vuelven a pedirse."""
    def suya(clave):
        kind, _, rest = clave.partition(":")
        return kind in ("comp", "grupo", "jornada") and rest.split(":")[0] in comps
    for clave in [c for c in intentos if suya(c)]:
        del intentos[clave]
    no_disponible[:] = [c for c in no_disponible if not suya(c)]


def main():
    # Lazy import — keeps the module importable in environments without playwright
    # (the Tests CI pytest job doesn't install it).
    args = parse_args()
    global CARPETA
    CARPETA = Path(args.carpeta) if args.carpeta else None
    try:
        _main(args)
    finally:
        CARPETA = None                    # la carpeta es de esta tanda (las pruebas llaman a main varias veces)


def _main(args):
    GROUP_FILTER[:] = [g.strip() for g in args.grupos.split(",") if g.strip()]
    season = args.temporada
    comps_arg = [c.strip() for c in args.comps.split(",") if c.strip()]
    expected = LOTE_ARG[args.lote] if args.lote else None
    if args.estado:
        # Sin navegador ni red: lo que queda del lote de la tanda (actas-federacion.yml). Unas
        # categorías que no existen o de dos lotes, o de otro lote que el de la cadena: para.
        try:
            categories = _categorias().parse_categories(args.categorias)
            state = chain_state(season, tanda_lote(season, categories, comps_arg, expected=expected))
        except ValueError as ex:
            state = {"pending": 0, "stuck": 1, "lote": None, "error": str(ex)}
        print(json.dumps(state, ensure_ascii=False))
        return
    # Antes de abrir ningún navegador: un solo lote, el de la cadena (si no, para sin escribir nada).
    categories = _categorias().parse_categories(args.categorias)
    lote = tanda_lote(season, categories, comps_arg, expected=expected)

    from playwright.sync_api import sync_playwright

    # El plazo cuenta desde el arranque: enumerar también lleva su tiempo.
    minutes = args.max_minutes or 330     # bajo el timeout del job, para guardar y subir
    run_start = time.time()
    over = lambda: time.time() - run_start > minutes * 60
    F = federacion(minutes, args.max_paginas)
    resumen = args.resumen or None
    with sync_playwright() as p:
        # Un navegador y una página para toda la tanda (también para descubrir las competiciones).
        br = _launch(p)
        page = br.new_context(user_agent=UA).new_page()
        try:
            _tanda(page, F, season, lote, categories, comps_arg, args, over, resumen)
        finally:
            br.close()
    print(fiflp_carga.ultima_linea(F, chain_state(season, lote).get("pending") == 0))


def _tanda(page, F, season, lote, categories, comps_arg, args, over, resumen):
    # Resolve comp list
    names = {}
    if comps_arg:
        comps = comps_arg
    elif catalog_comps(season, categories):
        # Las competiciones de fútbol 7/8 de esas categorías de esa temporada (sin sala ni alevín
        # de otra isla) del catálogo de la federación (discover_fiflp_comps.py).
        comps = catalog_comps(season, categories)
    elif season in KNOWN_COMPS and categories == _categorias().DEFAULT_CATEGORIES:
        comps = KNOWN_COMPS[season]
    else:
        # auto-discover (used for seasons 17 and 18)
        comps = discover_comps(page, season, categories, names, F)
        if not comps:
            print(f"  sin competiciones de la temporada {season} (parada: {parada_de(F)}): nada que escribir")
            guardar_resumen(resumen, F, {})   # las páginas y la parada, para el carril (el día, el freno)
            return
    comps = [str(c) for c in comps]

    # Todas las competiciones, del lote de la tanda: sus actas van a su raw, su índice y su estado.
    tanda_lote(season, categories, comps, names, expected=lote)
    print(f"Season {SEASON_NAME[season]} ({season}): {len(comps)} comps to walk (lote {_lote_label(lote)})")

    store = RawStore(season, lote)
    print(f"Resume state ({raw_path(season, lote).name}): {len(store.data)} actas already scraped")
    # Leídos de la cuarentena si hay CARPETA (si no están allí, los publicados); escritos en ella (_de, _a).
    ipath, spath = _a(index_path(season, lote)), _a(status_path(season, lote))
    de_i, de_s = _de(index_path(season, lote)), _de(status_path(season, lote))
    index = json.loads(de_i.read_text(encoding="utf-8")) if de_i.exists() else {}
    try:
        old = json.loads(de_s.read_text(encoding="utf-8")) if de_s.exists() else {}
    except ValueError:
        old = {}
    nuevo = old.get("formato") == 2
    enumeracion = dict(old.get("enumeracion") or {}) if nuevo else {}
    intentos = dict(old.get("intentos") or {}) if nuevo else {}
    no_disponible = list(old.get("no_disponible") or []) if nuevo else []
    motivos = dict(old.get("motivos") or {}) if nuevo else {}
    if args.reindex:
        for comp in comps:
            enumeracion.pop(comp, None)
        _sin_enumeracion(set(comps), intentos, no_disponible)
    for comp in comps:
        if comp in enumeracion:
            continue
        known = sorted({str(e.get("grupo")) for e in index.values() if str(e.get("comp_id")) == comp})
        if not nuevo and known and not args.reindex and not GROUP_FILTER:
            # Un estado antiguo (sin formato): una competición que ya está en el índice se da por enumerada,
            # como hasta ahora (con --reindex, no).
            enumeracion[comp] = {"grupos": [[g, ""] for g in known], "pendientes": {}}
        else:
            enumeracion[comp] = {"grupos": None, "pendientes": {}}

    # Filter out already scraped (resume support). Una que está en el raw de otro lote: la de
    # una tanda antigua se adopta (RawStore.get) y la que es de ese lote no es de esta tanda.
    def wanted(cod):
        where, acta = store.get(cod)
        if acta is None:
            return True
        return where == lote and (needs_rescrape(acta) or (args.refrescar and needs_refresh(acta)))

    def objetivos():
        """Las actas del índice de las competiciones de la tanda (y de sus grupos pedidos), sin repetir."""
        out, seen = [], set()
        for comp in comps:
            names_of = dict(enumeracion[comp].get("grupos") or [])
            for cod, e in index.items():
                if str(e.get("comp_id")) != comp or cod in seen:
                    continue
                if not _wanted(comp, e.get("grupo"), names_of.get(str(e.get("grupo")))):
                    continue
                seen.add(cod)
                out.append(dict(e, cod_acta=cod))
        return out

    collector = Collector(store, refrescar=args.refrescar, F=F, intentos=intentos, no_disponible=no_disponible,
                          motivos=motivos)

    def guardar_estado():
        status = status_de(season, comps, enumeracion, objetivos(), wanted, store, collector, intentos,
                           no_disponible, F)
        escribir_atomico(spath, json.dumps(status, ensure_ascii=False, indent=1) + "\n")
        if resumen:
            parte = f"actas:{SEASON_NAME[season]}:{lote or 'siempre'}"
            guardar_resumen(resumen, F, {parte: {"completo": status["pending"] == 0, "pendientes": status["pending"],
                                                 "no_disponible": len(no_disponible)}})
        return status
    collector.on_save = guardar_estado

    vistas = set()
    for comp in comps:
        if over() or parada_de(F) is not None:
            break
        ledger = enumeracion[comp]
        if not _completa(ledger):
            print(f"  enumerating comp {comp}...")
            res = enumerar(page, F, season, comp, ledger, index, intentos, no_disponible, motivos=motivos)
            # Tras cada competición: una tanda cortada no pierde lo enumerado.
            escribir_atomico(ipath, json.dumps(index, ensure_ascii=False, indent=1))
            guardar_estado()
            if res == "parada":
                break
        # En seguida, sus actas (las de esta competición que faltan): la de más nivel, antes.
        pending = [t for t in objetivos() if str(t["comp_id"]) == comp and t["cod_acta"] not in vistas
                   and f"acta:{t['cod_acta']}" not in no_disponible and wanted(t["cod_acta"])]
        vistas.update(t["cod_acta"] for t in pending)
        if args.max_actas:
            pending = pending[:max(0, args.max_actas - collector.asked)]
        collector.asked += len(pending)
        if store.adopted:
            print(f"  {store.adopted} acta(s) adoptadas del raw de otro lote (de una tanda antigua)")
        print(f"  comp {comp}: {len(pending)} actas por leer")
        # La URL de un acta no lleva la temporada: sin ninguna página servida aún, la de competiciones primero
        # (fiflp_carga.preparar), o una primera acta muerta se tomaría por el freno.
        if pending and not fiflp_carga.preparar(page, F, season):
            break
        leer_actas(page, F, pending, over, collector, dump_fixture=args.dump_fixture)
        store.save()
        guardar_estado()
    if over():
        print(f"  time budget reached, stopping cleanly with {len(store.data)} actas saved")

    store.save(force=True)
    escribir_atomico(ipath, json.dumps(index, ensure_ascii=False, indent=1))
    status = guardar_estado()
    print(f"Done season {season} ({raw_path(season, lote).name}): total {len(store.data)} actas in raw, "
          f"{status['pending']} pending (parada: {status['parada']})")


if __name__ == "__main__":
    main()
