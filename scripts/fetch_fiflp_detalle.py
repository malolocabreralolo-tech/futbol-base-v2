#!/usr/bin/env python3
"""fetch_fiflp_detalle.py — El detalle de la federación (FIFLP) que no traen las
actas ni los goleadores, de cada grupo de benjamín y prebenjamín (fútbol 7/8, sin
sala; con --categorias alevin, de alevín de Gran Canaria) de las temporadas pedidas:

  - la clasificación detallada (NFG_VisClasificacion): código del equipo en la
    federación, partidos en casa y fuera, últimos resultados y puntos de sanción;
  - el directorio del grupo (NFG_LstDirectorioEquipos): código, escudo, colores
    de la equipación y campo de cada equipo (sin los datos de contacto);
  - con --jornadas, el calendario completo del grupo (NFG_CmpJornada por
    jornada, aplanado): resultados, fecha, hora, campo y árbitro. Es lo que hay de
    las temporadas en las que la federación no publica actas (2016-17 a 2018-19).

Y al final la ficha de cada campo (NFG_VisCampos) que aparezca en los
directorios o en la tabla venues de la base: coordenadas, dirección, superficie,
instalaciones y equipos que juegan allí.

Solo escribe raws (reanudables: lo ya leído no se vuelve a pedir):
  scripts/fiflp_detalle_<S>_raw.json   {"_grupos": {comp: [[grupo, nombre]]},
                                        "comp:grupo": {clasificacion, directorio, jornadas…}}
  scripts/fiflp_campos_raw.json        {código: ficha}
Los importa import_fiflp_detalle.py (lo llama el bot), que salta las entradas sin `ok`
y las claves con «_». Solo funciona desde GitHub Actions (detalle-federacion.yml):
FIFLP contesta vacío a las IPs domésticas.

Lee como el bot (fiflp_carga.para_tanda): una página vacía solo es el freno si la
federación tampoco sirve otra. Lo que no carga nunca se guarda como leído: si la
federación para (el freno, el tope de peticiones, el plazo, un runner rechazado),
lo de esa entrada se queda como estaba y la ejecución acaba; si sirve otras y esa
no (una página muerta), la entrada gasta un intento y, con MAX_INTENTOS, queda «no
disponible en la federación». Las jornadas de un calendario leídas antes de un
corte se guardan («jornadas_leidas») y la ejecución siguiente pide solo las que
faltan; «jornadas» solo está con el calendario entero.

  python3 scripts/fetch_fiflp_detalle.py --temporadas 12,13,14 --jornadas 12,13,14 [--max-minutes 320]
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fiflp_detalle import parse_campo, parse_clasificacion, parse_directorio  # noqa: E402
from escritura import escribir_atomico  # noqa: E402
from fiflp_carga import (MAX_INTENTOS, guardar_resumen, para_tanda, parada_de, ultima_linea,  # noqa: E402
                         un_intento)

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "futbolbase.db"
CAMPOS_RAW = HERE / "fiflp_campos_raw.json"
DIRECTORIO_URL = ("/NFG_LstDirectorioEquipos?cod_primaria=1000117&search=1&Buscar=1"
                  "&Sch_Cod_Temporada={season}&Sch_Codigo_Delegacion=&Sch_Tipo_Juego="
                  "&Sch_CodCompeticion={comp}&Sch_CodGrupo={grupo}")
CLASIFICACION_URL = ("/NFG_VisClasificacion?cod_primaria=1000120&CodTemporada={season}"
                     "&codcompeticion={comp}&codgrupo={grupo}&codjornada=99")
CALENDARIO_URL = ("/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}"
                  "&CodCompeticion={comp}&CodGrupo={grupo}")
CAMPO_URL = "/NFG_VisCampos?cod_primaria=1000122&Codigo_Campo={code}"


def season_name(code):
    """'12' -> '2016-2017' (CodTemporada = año inicial − 2004)."""
    start = 2004 + int(code)
    return f"{start}-{start + 1}"


def raw_path(code):
    return HERE / f"fiflp_detalle_{season_name(code)}_raw.json"


def benjamin_comps(comps, categories=None):
    """[(id, nombre)] de fútbol 7/8 de las categorías dadas (categorias.category_of: sin sala ni
    alevín de Lanzarote o Fuerteventura); por defecto, benjamín y prebenjamín."""
    from categorias import DEFAULT_CATEGORIES, category_of
    categories = categories or DEFAULT_CATEGORIES
    return [(c["id"], c["name"].strip()) for c in comps if category_of(c["name"]) in categories]


def catalog_comps(code, categories=None, catalog=None):
    """Las de la temporada en el catálogo de discover_fiflp_comps.py (o en `catalog`, ya leído:
    las pruebas pasan el congelado)."""
    if catalog is None:
        path = HERE / "fiflp_comps_catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return benjamin_comps((catalog.get(season_name(code)) or {}).get("all", []), categories)


def live_comps(page, F, code, categories=None):
    """Las de la temporada leídas de la web, para una que el catálogo aún no tiene ([] si la página no carga)."""
    if not F.goto(page, F.BASE + f"/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={code}"):
        return []
    comps = page.evaluate("""() => {
        const sel = document.querySelector('select[name="competicion"]');
        return sel ? Array.from(sel.options).filter(o => o.value && o.value !== '0')
                       .map(o => ({id: o.value, name: o.text.trim()})) : [];
    }""") or []
    F.delay()
    return benjamin_comps(comps, categories)


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path, data):
    escribir_atomico(path, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def group_done(entry, jornadas):
    """Un grupo hecho: «no disponible en la federación» o leído (cargaron la clasificación y el directorio y,
    si se piden, el calendario entero)."""
    return bool(entry and (entry.get("no_disponible")
                           or (entry.get("ok") and (not jornadas or "jornadas" in entry))))


def _grupos(page, F):
    """[[valor, nombre]] del desplegable de grupos de la página cargada."""
    for _ in range(4):
        try:
            opts = page.evaluate("""() => Array.from(document.querySelectorAll('select[name="grupo"] option'))
                .filter(o => o.value && o.value !== '0').map(o => [o.value, o.text.trim()])""") or []
        except Exception:
            opts = []
        if opts:
            return opts
        page.wait_for_timeout(2500)
    return []


def _jornadas(page, F, base, log=print, leidas=None):
    """({etiqueta de jornada: [partidos]}, estado) del calendario ya cargado de un grupo: cada jornada por su
    URL y aplanada (las cifras de los marcadores van ofuscadas), salvo las de `leidas` (de una ejecución
    anterior), que no se vuelven a pedir. El estado: "completo" (todas), "parada" (la federación dejó de servir:
    lo leído hasta ahí vale), "fallo" (alguna no cargó con la federación sirviendo: las demás sí se leen) o
    "vacio" (el desplegable, sin jornadas)."""
    from fiflp_render import flatten
    from update_fiflp import option_round
    from activate_season import _iso
    options = []
    for _ in range(4):
        options = page.evaluate("""() => {
            const sel = document.querySelector('select[name="jornada"]');
            return sel ? Array.from(sel.options).filter(o => o.value && o.value !== '0')
                           .map(o => ({value: o.value, text: o.text.trim()})) : [];
        }""") or []
        if options:
            break
        page.wait_for_timeout(2500)
    rounds = dict(leidas or {})
    if not options:
        return rounds, "vacio"
    estado = "completo"
    for opt in options:
        label, when = option_round(opt["text"])
        if label in rounds:
            continue
        if not F.goto(page, f"{base}&CodJornada={opt['value']}"):
            if parada_de(F) is not None:
                return rounds, "parada"
            log(f"      ! no carga la {label.lower()}")
            estado = "fallo"
            continue
        flatten(page)
        rounds[label] = [{**m, "date": _iso(m.get("date")) or (when.isoformat() if when else "")}
                         for m in F.parse_matches(page)]
        F.delay()
    return rounds, estado


def _sin_fecha(entry):
    return {k: v for k, v in (entry or {}).items() if k != "fetched"}


def scrape_group(page, F, season, comp, grupo, jornadas, previo=None, log=print):
    """La entrada nueva del grupo (sobre `previo`, la que había), o None si no hay nada que escribir (la
    federación paró antes de leer nada nuevo: se queda la de antes).
    Con `previo` ya leído (`ok`), ni la clasificación ni el directorio se vuelven a pedir. Si no, las dos: si una
    no carga con la federación sirviendo, la entrada queda sin `ok` y gasta un intento (fiflp_carga.un_intento);
    la otra ni se pide. Con `jornadas`, el calendario: lo leído antes de un corte va a «jornadas_leidas» (la
    ejecución siguiente pide solo lo que falta) y, con todas, a «jornadas». Una jornada que no carga con la
    federación sirviendo (o un calendario sin jornadas) gasta un intento del grupo: con MAX_INTENTOS, no
    disponible, con lo leído en «jornadas_leidas» y sin «jornadas» (no es el calendario entero)."""
    previo = previo or {}
    if previo.get("ok"):
        entry = dict(previo)
    else:
        entry = {"comp": comp, "grupo": grupo, "clasificacion": [], "directorio": [], "ok": False}
        for campo, url, parse in (("clasificacion", CLASIFICACION_URL, parse_clasificacion),
                                  ("directorio", DIRECTORIO_URL, parse_directorio)):
            if not F.goto(page, F.BASE + url.format(season=season, comp=comp, grupo=grupo)):
                if parada_de(F) is not None:
                    return None
                return un_intento(entry, previo)
            entry[campo] = parse(page.content())
            F.delay()
        entry["ok"] = True
    if jornadas and "jornadas" not in entry:
        base = F.BASE + CALENDARIO_URL.format(season=season, comp=comp, grupo=grupo)
        if not F.goto(page, base):
            if parada_de(F) is None:
                un_intento(entry, previo)
        else:
            rounds, estado = _jornadas(page, F, base, log, entry.get("jornadas_leidas"))
            if estado == "completo":
                entry["jornadas"] = rounds
                entry.pop("jornadas_leidas", None)
            else:
                if rounds:
                    entry["jornadas_leidas"] = rounds
                if estado != "parada":
                    un_intento(entry, previo)
    return None if _sin_fecha(entry) == _sin_fecha(previo) else entry


def _web_key(categories):
    """La clave de las competiciones leídas de la web: _comps las de siempre, _comps_alevin las de alevín."""
    from categorias import DEFAULT_CATEGORIES, web_key
    return "_comps" if tuple(categories or DEFAULT_CATEGORIES) == DEFAULT_CATEGORIES else \
        "_comps_" + "_".join(web_key(c) for c in categories)


def _parte(comps, data, want_rounds):
    """{"completo", "pendientes", "no_disponible"} de una temporada. Pendientes: la lista de competiciones si
    aún no se sabe (comps None), las competiciones sin lista de grupos y los grupos sin hacer. No disponibles:
    los grupos así y las competiciones que nunca dieron grupos."""
    if comps is None:
        return {"completo": False, "pendientes": 1, "no_disponible": 0}
    pendientes = no_disponible = 0
    listas = data.get("_grupos") or {}
    for comp, _ in comps:
        if comp not in listas:
            pendientes += 1
            continue
        if not listas[comp]:
            no_disponible += 1
            continue
        for grupo, _ in listas[comp]:
            entry = data.get(f"{comp}:{grupo}")
            if entry and entry.get("no_disponible"):
                no_disponible += 1
            elif not group_done(entry, want_rounds):
                pendientes += 1
    return {"completo": pendientes == 0, "pendientes": pendientes, "no_disponible": no_disponible}


def _intento_de(data, clave):
    """Un intento más de `clave` (una competición, o la lista de competiciones de la web) en data["_intentos"];
    True si ya son MAX_INTENTOS (se da por hecha, sin nada)."""
    intentos = data.setdefault("_intentos", {})
    intentos[clave] = int(intentos.get(clave) or 0) + 1
    return intentos[clave] >= MAX_INTENTOS


def run_groups(page, F, seasons, jornadas_seasons, deadline, log=print, categories=None, partes=None, resumen=None):
    """`categories`: las del catálogo que se recorren ('ALEVIN'…); por defecto, benjamín y prebenjamín. Todas
    van al mismo raw de la temporada (claves comp:grupo). En `partes`, la de cada temporada pedida
    («detalle:<S>», o «calendario:<S>» si se piden sus jornadas); con `resumen` (una ruta), guardar_resumen tras
    cada grupo guardado. Da False si la ejecución se cortó (el plazo o una parada de la federación); True si
    recorrió todo, aunque quede algo pendiente de una página muerta (las partes lo dicen)."""
    partes = {} if partes is None else partes
    key = _web_key(categories)

    def clave(season):
        return f"{'calendario' if season in jornadas_seasons else 'detalle'}:{season_name(season)}"

    def comps_de(season, data):
        """Las del catálogo, las ya leídas de la web o None si aún no se saben."""
        return catalogo[season] or ([tuple(c) for c in data[key]] if key in data else None)

    def anotar(season, data):
        comps = comps_de(season, data)
        partes[clave(season)] = _parte(comps, data, season in jornadas_seasons)
        if comps == [] and int((data.get("_intentos") or {}).get(key) or 0) >= MAX_INTENTOS:
            partes[clave(season)]["no_disponible"] = 1     # la web nunca dio sus competiciones
        if resumen:
            guardar_resumen(resumen, F, partes)

    catalogo = {season: catalog_comps(season, categories) for season in seasons}
    for season in seasons:
        anotar(season, load(raw_path(season)))
    for season in seasons:
        path = raw_path(season)
        data = load(path)
        comps = comps_de(season, data)
        if comps is None:
            # Una temporada que el catálogo aún no tiene: las de la web, guardadas por categorías. Si no las da
            # (la página no carga o no trae ninguna), un intento; con MAX_INTENTOS, ninguna.
            comps = live_comps(page, F, season, categories)
            if not comps and parada_de(F) is not None:
                return False
            if comps or _intento_de(data, key):
                data[key] = comps
            save(path, data)
            anotar(season, data)
            if not comps:
                continue
        log(f"Temporada {season_name(season)}: {len(comps)} competiciones")
        want_rounds = season in jornadas_seasons
        for comp, comp_name in comps:
            if time.monotonic() > deadline:
                log("  plazo agotado: sigue en la próxima tanda")
                return False
            listas = data.setdefault("_grupos", {})
            if comp not in listas:
                if not F.goto(page, F.BASE + f"/NFG_CmpJornada?cod_primaria=1000120&CodTemporada={season}"
                                             f"&CodCompeticion={comp}"):
                    if parada_de(F) is not None:
                        return False
                    log(f"  ! {comp}: no carga")
                    grupos = []
                else:
                    grupos = _grupos(page, F)
                    F.delay()
                    if not grupos:
                        log(f"  ! {comp} {comp_name[:50]}: sin grupos")
                if grupos or _intento_de(data, comp):
                    listas[comp] = grupos
                save(path, data)
                anotar(season, data)
                if not grupos:
                    continue
            grupos = listas[comp]
            new = 0
            for grupo, grupo_name in grupos:
                if time.monotonic() > deadline:
                    log("  plazo agotado: sigue en la próxima tanda")
                    return False
                gkey = f"{comp}:{grupo}"
                if group_done(data.get(gkey), want_rounds):
                    continue
                entry = scrape_group(page, F, season, comp, grupo, want_rounds, data.get(gkey), log)
                if entry is not None:
                    entry.update(comp_name=comp_name, grupo_name=grupo_name, fetched=date.today().isoformat())
                    data[gkey] = entry
                    save(path, data)
                    anotar(season, data)
                    new += 1
                if parada_de(F) is not None:
                    return False
            log(f"  {comp} {comp_name[:50]}: {len(grupos)} grupos, {new} leídos")
    return True


def venue_codes(seasons):
    """Códigos de campo de los directorios descargados y de la tabla venues."""
    codes = set()
    for path in HERE.glob("fiflp_detalle_*_raw.json"):
        for key, entry in load(path).items():
            if key.startswith("_"):
                continue
            codes.update(t.get("venue_code") for t in entry.get("directorio") or [] if t.get("venue_code"))
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            codes.update(c for (c,) in conn.execute("SELECT code FROM venues WHERE code IS NOT NULL"))
            conn.close()
        except sqlite3.Error:
            pass
    return sorted(c for c in codes if c)


def _campo_hecho(entry):
    return bool(entry and (entry.get("ok") or entry.get("no_disponible")))


def _parte_campos(codes, data):
    pendientes = sum(not _campo_hecho(data.get(str(c))) for c in codes)
    no_disponible = sum(bool((data.get(str(c)) or {}).get("no_disponible")) for c in codes)
    return {"completo": pendientes == 0, "pendientes": pendientes, "no_disponible": no_disponible}


def run_campos(page, F, deadline, log=print, partes=None, resumen=None):
    """La ficha de cada campo. Una que no carga con la federación parada no se escribe (y la ejecución acaba);
    una que no carga con la federación sirviendo, o que carga sin datos (parse_campo None), gasta un intento y,
    con MAX_INTENTOS, queda no disponible. En `partes`, la parte «campos»."""
    partes = {} if partes is None else partes
    data = load(CAMPOS_RAW)
    todos = venue_codes(None)
    codes = [c for c in todos if not _campo_hecho(data.get(str(c)))]
    partes["campos"] = _parte_campos(todos, data)
    log(f"Campos: {len(codes)} fichas por leer")
    for code in codes:
        if time.monotonic() > deadline:
            log("  plazo agotado: sigue en la próxima tanda")
            return False
        ficha = None
        if F.goto(page, F.BASE + CAMPO_URL.format(code=code)):
            ficha = parse_campo(page.content())
        elif parada_de(F) is not None:
            return False
        previo = data.get(str(code))
        nueva = {**(ficha or {}), "ok": bool(ficha), "fetched": date.today().isoformat()}
        data[str(code)] = nueva if ficha else un_intento(nueva, previo)
        save(CAMPOS_RAW, data)
        partes["campos"] = _parte_campos(todos, data)
        if resumen:
            guardar_resumen(resumen, F, partes)
        F.delay()
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--temporadas", default="12,13,14,15,16,17,18,19,20,21,22")
    ap.add_argument("--jornadas", default="12,13,14",
                    help="temporadas de las que bajar también el calendario completo")
    ap.add_argument("--sin-campos", action="store_true", help="no leer las fichas de los campos")
    ap.add_argument("--max-minutes", type=float, default=320)
    ap.add_argument("--max-paginas", type=int, default=0, help="tope de peticiones de la ejecución (0, sin tope)")
    ap.add_argument("--resumen", default="", help="dónde escribir el resumen de la ejecución (JSON)")
    ap.add_argument("--categorias", default="", help="'benjamin,prebenjamin' (por defecto) o 'alevin'")
    args = ap.parse_args(argv)
    from categorias import parse_categories
    categories = parse_categories(args.categorias)
    seasons = [s.strip() for s in args.temporadas.split(",") if s.strip()]
    jornadas = {s.strip() for s in args.jornadas.split(",") if s.strip()}
    import fetch_fiflp_2425
    # La lectura del bot (la vacía solo es el freno si la federación no sirve otra), sin esperas del freno y
    # con el tope de la ejecución; la nube, la de la máquina.
    F = para_tanda(fetch_fiflp_2425, args.max_minutes, args.max_paginas)
    resumen = args.resumen or None
    partes = {}
    from fiflp_render import fiflp_launch_args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Sin lo ajeno a la federación ni imágenes, y con caché: sin ruta (fiflp_launch_args).
        browser = p.chromium.launch(headless=True, args=fiflp_launch_args())
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"))
        page.set_default_timeout(30000)
        try:
            complete = run_groups(page, F, seasons, jornadas, F.deadline, categories=categories, partes=partes,
                                  resumen=resumen)
            if complete and not args.sin_campos:
                complete = run_campos(page, F, F.deadline, partes=partes, resumen=resumen)
        finally:
            browser.close()
            guardar_resumen(resumen, F, partes)
    print(ultima_linea(F, complete and all(p["completo"] for p in partes.values())))


if __name__ == "__main__":
    main()
