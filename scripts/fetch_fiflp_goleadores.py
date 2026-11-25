#!/usr/bin/env python3
"""fetch_fiflp_goleadores.py — Goleadores y clasificación oficial de cada grupo
de benjamín y prebenjamín de temporadas pasadas, de la web de la federación.

Recorre las competiciones del catálogo (fiflp_comps_catalog.json, las mismas
que las actas: benjamín y prebenjamín de fútbol 7/8, sin sala; con --categorias
alevin, las de alevín de Gran Canaria) y, de cada grupo, guarda:
  - la clasificación (NFG_VisClasificacion, no ofuscada): para casar el grupo
    con el de la base aunque no tenga actas importadas;
  - los goleadores (NFG_CMP_Goleadores, aplanados con fiflp_render): jugador,
    equipo, partidos, goles y penaltis;
  - el escudo de cada equipo (la URL de la imagen que va en su celda de una
    jornada; --escudos rellena solo eso en los grupos ya leídos).

Solo escribe scripts/fiflp_goleadores_<S>_raw.json (reanudable: un grupo ya
leído no se vuelve a pedir) y, junto a él, la lista de grupos de cada competición
(fiflp_goleadores_<S>_grupos.json, que ningún importador lee). Lo importa el bot
(import_fiflp_goleadores.py).

Lee como el bot (fiflp_carga.para_tanda): una página vacía solo es el freno si la
federación tampoco sirve otra. Lo que no carga nunca se guarda como leído: si la
federación para (el freno, el tope de peticiones, el plazo, un runner rechazado),
el grupo se queda como estaba y la ejecución acaba; si sirve otras y esa no (una
página muerta), el grupo gasta un intento y, con MAX_INTENTOS, queda «no
disponible en la federación». La última línea dice «Completo.» solo sin nada
pendiente.
Solo funciona desde GitHub Actions (historico.yml): FIFLP contesta
vacío a las IPs domésticas.

  python3 scripts/fetch_fiflp_goleadores.py --temporadas 17,18,19,20,21 [--max-minutes 320] [--categorias alevin]
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

# scripts/ (sus módulos) y la raíz (fetch_fiflp_actas importa scripts.acta_parser).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from fetch_fiflp_actas import SEASON_NAME, catalog_comps, _options  # noqa: E402
from fiflp_render import flatten, fiflp_launch_args  # noqa: E402
from update_fiflp import GOLEADORES_URL, parse_goleadores  # noqa: E402
from escritura import escribir_atomico  # noqa: E402
import cuarentena  # noqa: E402
from fiflp_carga import (MAX_INTENTOS, guardar_resumen, para_tanda, parada_de, ultima_linea,  # noqa: E402
                         un_intento)

HERE = Path(__file__).resolve().parent
# La carpeta de la cuarentena (--carpeta: cuarentena.py): None, lo de siempre (leer y escribir en scripts/).
CARPETA = None


def raw_path(season_code):
    return HERE / f"fiflp_goleadores_{SEASON_NAME[season_code]}_raw.json"


def comp_names(season_code):
    """{id: nombre} de las competiciones de la temporada, del catálogo."""
    entry = json.loads((HERE / "fiflp_comps_catalog.json").read_text(encoding="utf-8")).get(SEASON_NAME[season_code]) or {}
    return {c["id"]: c["name"] for c in entry.get("all", [])}


def _origen(path):
    """De dónde se lee `path`: él mismo; con CARPETA (--carpeta), la copia de la cuarentena si existe y si no
    el publicado (cuarentena.leer: se empieza por lo que ya hay)."""
    if CARPETA is None:
        return path
    return cuarentena.leer(path.name, CARPETA, path.parent) or path


def _destino(path):
    """Dónde se escribe `path`: él mismo; con CARPETA, en la cuarentena (cuarentena.escribir): lo publicado no
    se toca hasta que se promueve."""
    return path if CARPETA is None else cuarentena.escribir(path.name, CARPETA, path.parent)


def load(path):
    path = _origen(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path, data):
    escribir_atomico(_destino(path), json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def grupos_path(season_code):
    """La lista de grupos de cada competición, junto al raw: {"grupos": {comp: [[valor, texto]]}, "intentos":
    {comp: n}}. Así la página de la competición no se vuelve a pedir en cada ejecución. Ningún importador la
    lee (sus patrones de nombre son estrictos: *_raw.json)."""
    return raw_path(season_code).parent / f"fiflp_goleadores_{SEASON_NAME[season_code]}_grupos.json"


def done(entry):
    """Un grupo hecho: leído (cargaron la clasificación y los goleadores, aunque no tenga ninguno) o «no
    disponible en la federación» (MAX_INTENTOS ejecuciones sin cargar con la federación sirviendo otras: los
    importadores lo saltan, porque miran `ok`)."""
    return bool(entry and (entry.get("ok") or entry.get("no_disponible")))


CRESTS_JS = r"""() => {
  const out = {};
  for (const img of document.querySelectorAll('img[src*="/Clubes/"]')) {
    const cell = img.closest('td');
    if (!cell) continue;
    const clone = cell.cloneNode(true);
    clone.querySelectorAll('script, style').forEach(n => n.remove());
    const name = clone.textContent.replace(/\s+/g, ' ').trim();
    if (name && name.length < 80 && !out[name]) out[name] = img.src;
  }
  return out;
}"""


def scrape_crests(page, F, season, comp, grupo, teams):
    """({equipo: URL de su escudo}, ¿sin parada?) de las jornadas del grupo (el escudo va en la celda del
    equipo): la que sirve por defecto y, si falta alguno (un descanso), otra. Una jornada que no carga con la
    federación sirviendo (parada_de None) se salta; si la federación deja de servir (el freno, el tope, el
    plazo…), se para ahí y el grupo se queda sin escudos (pendientes), no con los que dio a medias."""
    base = f"{F.BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}&CodCompeticion={comp}&CodGrupo={grupo}"
    crests = {}
    for url in (base, base + "&CodJornada=1", base + "&CodJornada=2"):
        if not F.goto(page, url):
            if parada_de(F) is not None:
                return crests, False
            continue
        try:
            crests.update({k: v for k, v in (page.evaluate(CRESTS_JS) or {}).items() if k not in crests})
        except Exception:
            pass
        F.delay()
        if teams and all(t in crests for t in teams):
            break
    return crests, True


def scrape_group(page, F, season, comp, grupo):
    """(clasificación, goleadores, ok) de un grupo: ok solo si cargaron LAS DOS páginas (hasta noviembre de
    2026 bastaba la de goleadores, y un grupo sin clasificación no casaba con ninguno de la base). Si la
    clasificación no carga, los goleadores ni se piden: el grupo no quedaría leído igual."""
    standings = []
    loaded = F.goto(page, f"{F.BASE}/NFG_VisClasificacion?cod_primaria=1000120&CodTemporada={season}"
                          f"&codcompeticion={comp}&codgrupo={grupo}&codjornada=99")
    if loaded:
        standings = F.parse_standings(page)
    F.delay()
    if not loaded or not F.goto(page, F.BASE + GOLEADORES_URL.format(comp=comp, season=season, group=grupo)):
        return standings, [], False
    flatten(page)
    scorers = [list(r) for r in parse_goleadores(page.content())]
    F.delay()
    return standings, scorers, True


def _comps(season, categories):
    return catalog_comps(season, categories) if categories else catalog_comps(season)


def _parte(comps, data, listas, crests_only=False):
    """{"completo", "pendientes", "no_disponible"} de una temporada. Pendientes: las competiciones sin lista
    de grupos y los grupos sin hacer (con `crests_only`, los leídos sin escudos). No disponibles: los grupos
    así y las competiciones que nunca dieron grupos."""
    pendientes = no_disponible = 0
    for comp in comps:
        grupos = (listas.get("grupos") or {}).get(comp)
        if grupos is None:
            pendientes += 1
            continue
        if not grupos:
            no_disponible += 1
            continue
        for grupo, _ in grupos:
            entry = data.get(f"{comp}:{grupo}")
            if entry and entry.get("no_disponible"):
                no_disponible += 1
            elif crests_only:
                pendientes += bool(entry and entry.get("ok") and "crests" not in entry)
            elif not done(entry):
                pendientes += 1
    return {"completo": pendientes == 0, "pendientes": pendientes, "no_disponible": no_disponible}


def parte(season, categories=None, crests_only=False):
    """La parte de una temporada, de lo que hay escrito (el raw y su lista de grupos)."""
    return _parte(_comps(season, categories), load(raw_path(season)), load(grupos_path(season)), crests_only)


def _intento(listas, comp):
    """Una competición cuya página no carga (con la federación sirviendo) o carga sin grupos: un intento; con
    MAX_INTENTOS, sin grupos (hecha). Da la lista (vacía) o None si aún se volverá a pedir."""
    n = listas["intentos"][comp] = int(listas["intentos"].get(comp) or 0) + 1
    if n >= MAX_INTENTOS:
        listas["grupos"][comp] = []
        return []
    return None


def leer_grupos(page, F, season, comp, listas, log=print):
    """Los [[valor, texto]] de los grupos de la competición, de su página (y apuntados en `listas`); None si no
    los dio: por una parada (parada_de(F)) o, sin ella, gastando un intento (_intento)."""
    base = f"{F.BASE}/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}&CodCompeticion={comp}"
    if not F.goto(page, base):
        if parada_de(F) is not None:
            return None
        log(f"  ! {comp}: no carga")
        return _intento(listas, comp)
    try:
        labels = dict(page.evaluate("""() => Array.from(document.querySelectorAll('select[name="grupo"] option'))
            .map(o => [o.value, o.text.trim()])""") or [])
    except Exception:
        labels = {}
    valores = _options(page, "grupo")
    F.delay()
    if not valores:
        log(f"  ! {comp}: sin grupos")
        return _intento(listas, comp)
    grupos = listas["grupos"][comp] = [[g, labels.get(g, "")] for g in valores]
    return grupos


def run(page, F, seasons, deadline, log=print, crests_only=False, categories=None, escudos=True, partes=None,
        resumen=None):
    """`categories`: las del catálogo que se recorren ('ALEVIN'…); por defecto, benjamín y prebenjamín. Todas
    van al mismo raw de la temporada (claves comp:grupo). Con `escudos` False, sin las jornadas de los escudos
    (las pide después crests_only). En `partes`, la de cada temporada pedida («goleadores:<S>», o «escudos:<S>»
    con crests_only); con `resumen` (una ruta), guardar_resumen tras cada grupo guardado.
    La lectura es la de una tanda (fiflp_carga.para_tanda). Si una página no carga y la federación ha
    parado (parada_de: el freno, el tope, el plazo, el navegador o un runner rechazado), no se escribe nada de
    ese grupo (se queda el de antes), no gasta intento y la ejecución acaba: lo pendiente sigue pendiente. Si la
    federación sirve otras (una página muerta), el grupo gasta un intento (fiflp_carga.un_intento).
    Da False si la ejecución se cortó (el plazo o una parada); True si recorrió todo, aunque quede algo pendiente
    (una página muerta antes de su último intento: las partes lo dicen)."""
    partes = {} if partes is None else partes
    clave = "escudos" if crests_only else "goleadores"

    def anotar(season, comps, data, listas):
        partes[f"{clave}:{SEASON_NAME[season]}"] = _parte(comps, data, listas, crests_only)
        if resumen:
            guardar_resumen(resumen, F, partes)

    # Las partes de todas las temporadas pedidas desde el principio: una ejecución cortada en la primera
    # dice también lo que falta de las demás. Las competiciones, una vez por temporada.
    comps_de = {season: _comps(season, categories) for season in seasons}
    for season in seasons:
        partes[f"{clave}:{SEASON_NAME[season]}"] = _parte(comps_de[season], load(raw_path(season)),
                                                          load(grupos_path(season)), crests_only)
    for season in seasons:
        path, gpath = raw_path(season), grupos_path(season)
        data = load(path)
        listas = {"grupos": {}, "intentos": {}, **load(gpath)}
        names = comp_names(season)
        comps = comps_de[season]
        log(f"Temporada {SEASON_NAME[season]}: {len(comps)} competiciones")
        for comp in comps:
            if time.monotonic() > deadline:
                log("  plazo agotado: sigue en la próxima tanda")
                return False
            grupos = listas["grupos"].get(comp)
            if grupos is None:
                antes = json.dumps(listas, sort_keys=True)
                grupos = leer_grupos(page, F, season, comp, listas, log)
                if json.dumps(listas, sort_keys=True) != antes:
                    save(gpath, listas)
                    anotar(season, comps, data, listas)
                if parada_de(F) is not None:
                    return False
                if grupos is None:
                    continue
            new = 0
            for grupo, grupo_name in grupos:
                key = f"{comp}:{grupo}"
                if time.monotonic() > deadline:
                    log("  plazo agotado: sigue en la próxima tanda")
                    return False
                entry = data.get(key)
                if not done(entry):
                    if crests_only:
                        continue
                    standings, scorers, ok = scrape_group(page, F, season, comp, grupo)
                    if not ok and parada_de(F) is not None:
                        return False              # la federación paró: nada de este grupo, ni un intento
                    nuevo = {"comp": comp, "comp_name": names.get(comp, ""), "grupo": grupo,
                             "grupo_name": grupo_name, "standings": standings, "scorers": scorers, "ok": ok,
                             "fetched": date.today().isoformat()}
                    entry = data[key] = nuevo if ok else un_intento(nuevo, entry)
                    save(path, data)
                    anotar(season, comps, data, listas)
                    new += 1
                if (escudos or crests_only) and entry.get("ok") and "crests" not in entry:
                    teams = [r["team"] for r in entry.get("standings") or []]
                    crests, sin_parada = scrape_crests(page, F, season, comp, grupo, teams)
                    if not sin_parada:
                        return False              # sin escudos (pendientes): no los que dio a medias
                    entry["crests"] = crests
                    save(path, data)
                    anotar(season, comps, data, listas)
                    new += 1
            log(f"  {comp} {names.get(comp, '')[:50]}: {len(grupos)} grupos, {new} leídos")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--temporadas", default="17,18,19,20,21")
    ap.add_argument("--max-minutes", type=float, default=320)
    ap.add_argument("--max-paginas", type=int, default=0, help="tope de peticiones de la ejecución (0, sin tope)")
    ap.add_argument("--resumen", default="", help="dónde escribir el resumen de la ejecución (JSON)")
    ap.add_argument("--escudos", action="store_true", help="solo los escudos de los grupos ya leídos")
    ap.add_argument("--sin-escudos", action="store_true", help="sin las jornadas de los escudos (van después)")
    ap.add_argument("--categorias", default="", help="'benjamin,prebenjamin' (por defecto) o 'alevin'")
    ap.add_argument("--carpeta", default="", help="la cuarentena (scripts/historico): leer y escribir allí")
    args = ap.parse_args(argv)
    global CARPETA
    CARPETA = Path(args.carpeta) if args.carpeta else None
    try:
        _main(args)
    finally:
        CARPETA = None                    # la carpeta es de esta tanda (las pruebas llaman a main varias veces)


def _main(args):
    from categorias import parse_categories
    categories = parse_categories(args.categorias)
    seasons = [s.strip() for s in args.temporadas.split(",") if s.strip()]
    for s in seasons:
        if s not in SEASON_NAME:
            sys.exit(f"temporada desconocida: {s}")
    import fetch_fiflp_2425
    # La lectura del bot (la vacía solo es el freno si la federación no sirve otra), sin esperas del freno y
    # con el tope de la ejecución; la nube, la de la máquina.
    F = para_tanda(fetch_fiflp_2425, args.max_minutes, args.max_paginas)
    resumen = args.resumen or None
    partes = {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Sin lo ajeno a la federación ni imágenes (los escudos se leen del src), y con caché: sin ruta.
        browser = p.chromium.launch(headless=True, args=fiflp_launch_args())
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"))
        page.set_default_timeout(30000)
        try:
            complete = run(page, F, seasons, F.deadline, crests_only=args.escudos, categories=categories,
                           escudos=not args.sin_escudos, partes=partes, resumen=resumen)
        finally:
            browser.close()
            guardar_resumen(resumen, F, partes)
    print(ultima_linea(F, complete and all(p["completo"] for p in partes.values())))


if __name__ == "__main__":
    main()
