#!/usr/bin/env python3
"""activar_auto.py — Activa sola, a partir de un raw de la federación YA descargado, lo que el bot apuntó
como nuevo en data-health.json: las competiciones de `newCompetitions` (enteras) y los grupos de
`newGroups` (solo esos). Es el camino manual de docs/temporada-nueva.md («Añadir una fase a mitad de
temporada») sin manos: manifiesto (fiflp_manifest.build) → verificación (activate_season.verify_sources)
→ alta (activate_season.add_groups) → generate_js → sonda de fases (sonda_fases.mjs).

    python3 scripts/activar_auto.py                 # activa lo pendiente y lo apunta en data-health.json
    python3 scripts/activar_auto.py --dry-run       # solo dice qué activaría; no escribe nada
    python3 scripts/activar_auto.py --pendientes    # imprime los ids pendientes, separados por comas
    python3 scripts/activar_auto.py --raw scripts/fiflp_islas_22_raw.json   # un raw para todas
    python3 scripts/activar_auto.py --temporada     # el CodTemporada de la temporada en curso (22 en 2026-27)

Y las de activar.yml (docs/federacion.md, «Competiciones y grupos nuevos»):

    python3 scripts/activar_auto.py --relanzar 1    # imprime 2 y sale con 0 si solo falló la descarga
    python3 scripts/activar_auto.py --pruebas-fallaron <data-health.json de la ejecución>

Sin --raw, cada competición se busca en el raw de su tanda: scripts/fiflp_islas_<CodTemporada>_raw.json
(benjamín y prebenjamín) o scripts/fiflp_islas_<CodTemporada>al_raw.json (alevín); la que no está en
ninguno, en el de su categoría (y falla: la descarga no está completa).

Reglas (docs/temporada-nueva.md, «Activación automática»):
  - Todo o nada por competición, cada una en su transacción: una que falla no toca la base ni impide
    las demás. Sale con 0 si no falló ninguna y con 1 si alguna falló (lo activado se queda).
  - Una competición entera solo entra si la descarga está completa: todos los grupos que lista la
    federación (scripts/fiflp_islas_<tanda>_grupos.json, que deja la descarga) están en el raw.
  - Antes de escribir, copia de la base y de lo que genera generate_js en backups/auto-<UTC>/; si
    generar falla, todo vuelve a esa copia (nunca una base cambiada con data-*.js viejos).
  - Una fase que la web no reconoce (sonda_fases.mjs) no deshace la activación: los datos son buenos y
    falta una regla de PHASE_TABLE, que es código; queda en activation.failed y sale con 1.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fiflp_manifest as M  # noqa: E402
from activate_season import add_groups, fiflp_ids, raw_team_names, validate_manifest, verify_sources  # noqa: E402
from categorias import category_of  # noqa: E402
from db import get_connection  # noqa: E402

# Los motivos de fallo (activation.failed[].reason), con estos textos: «Datos y fuentes» los enseña y
# activar.yml relanza la descarga solo con el de la descarga incompleta.
SIN_CONVENIO = "sin convenio de código: {}"
DESCARGA = "la descarga no está completa"
INCOMPLETA = DESCARGA + ": faltan {} grupos"
SIN_LISTA = DESCARGA + ": falta la lista de grupos de la federación"
VERIFICACION = "verificación: {}"
FASE_DESCONOCIDA = "fase que la web no reconoce: {}"
SIN_GENERAR = "no se pudo regenerar la web: {}"
SIN_SONDA = "no se pudo pasar la sonda de fases: {}"
# El que pone activar.yml (--pruebas-fallaron) cuando las suites fallan tras activar: no se publica nada.
PRUEBAS = "las pruebas fallaron tras activar"
# Los intentos de una cadena de activar.yml (--relanzar): el último no se relanza.
MAX_INTENTOS = 4


class Fallo(Exception):
    """Una competición que no se activa, con su motivo (uno de los de arriba)."""


def pendientes(health):
    """{CodCompeticion: None (competición entera) | [CodGrupo, …] (solo esos grupos)} de newCompetitions y
    newGroups de data-health.json. Una competición entera manda sobre sus grupos sueltos."""
    out = {}
    for item in (health or {}).get("newCompetitions") or []:
        if isinstance(item, dict) and str(item.get("id") or "").isdigit():
            out[str(item["id"])] = None
    for item in (health or {}).get("newGroups") or []:
        if not isinstance(item, dict):
            continue
        comp, group = str(item.get("competition") or ""), str(item.get("id") or "")
        if comp.isdigit() and group.isdigit() and out.get(comp, []) is not None and group not in out.get(comp, []):
            out.setdefault(comp, []).append(group)
    return {comp: (sorted(groups) if groups is not None else None) for comp, groups in sorted(out.items())}


def nombres(health):
    """{CodCompeticion: nombre} de lo pendiente: el de la federación (newCompetitions) o el de la web
    (newGroups.competitionName), para los motivos y para elegir el raw de su tanda."""
    out = {}
    for item in (health or {}).get("newGroups") or []:
        if isinstance(item, dict) and item.get("competitionName"):
            out[str(item.get("competition"))] = str(item["competitionName"])
    for item in (health or {}).get("newCompetitions") or []:
        if isinstance(item, dict) and item.get("name"):
            out[str(item.get("id"))] = str(item["name"])
    return out


def grupos_path(raw_path):
    """scripts/fiflp_islas_<tanda>_grupos.json, al lado de su raw (fetch_fiflp_2425.save_group_list)."""
    raw_path = Path(raw_path)
    return raw_path.with_name(raw_path.name.replace("_raw.json", "_grupos.json"))


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _current(conn):
    rows = conn.execute("SELECT id, name FROM seasons WHERE is_current=1").fetchall()
    if len(rows) != 1:
        raise ValueError("Debe existir una sola temporada actual")
    return rows[0]


def season_code(season):
    """'2026-2027' → '22', el CodTemporada de la federación (año inicial − 2004, como fiflp_manifest.main)."""
    return str(int(season[:4]) - 2004)


def _season_groups(conn, sid):
    """({(CodCompeticion, CodGrupo)}, {códigos}) de los grupos de la temporada."""
    pairs, codes = set(), set()
    for code, url in conn.execute("SELECT code, url FROM groups WHERE season_id=?", (sid,)):
        codes.add(code)
        ids = fiflp_ids(url or "")
        if ids:
            pairs.add(ids)
    return pairs, codes


def _has_content(entry):
    return bool(entry and (entry.get("jornadas") or entry.get("standings")))


def _wanted_groups(comp, wanted, by_group, listed):
    """Los grupos de la competición que tienen que estar en el raw: los pedidos (newGroups) o, para una
    competición entera, todos los que lista la federación. Fallo si falta alguno (o la lista)."""
    if wanted is None:
        if not isinstance(listed.get(comp), dict) or not listed[comp]:
            raise Fallo(SIN_LISTA)
        wanted = sorted(str(g) for g in listed[comp])
    # Un grupo guardado vacío es una página que la federación no sirvió (fetch_fiflp_islas.drop_empty_groups
    # lo vuelve a pedir): cuenta como que falta.
    missing = [g for g in wanted if not _has_content(by_group.get((comp, g)))]
    if missing:
        raise Fallo(INCOMPLETA.format(len(missing)))
    return wanted


def activar(raw_path, db_path, comps, root=ROOT, log=print, dry_run=False, names=None):
    """Por competición, en una transacción propia: manifiesto de SOLO los grupos que la temporada no tiene
    → verify_sources → add_groups. Devuelve {"activated": [{competition, name, codes}], "failed":
    [{competition, name, reason}], "groups": [grupos del manifiesto activados]}. Una competición que falla
    no toca la base ni impide las demás. Con `dry_run`, todo menos add_groups. `names`: {competición:
    nombre} de data-health.json, para la que no está en el raw."""
    raw = _read_json(raw_path, [])
    listed = _read_json(grupos_path(raw_path), {})
    names = dict(names or {})
    by_group = {(str(g.get("competition_id")), str(g.get("group_id"))): g for g in raw}
    raw_comps = {comp for comp, _ in by_group}
    for g in raw:
        names[str(g.get("competition_id"))] = g.get("competition_name") or names.get(str(g.get("competition_id")))
    result = {"activated": [], "failed": [], "groups": []}
    conn = get_connection(db_path)
    try:
        sid, season = _current(conn)
        known, taken = _season_groups(conn, sid)
        ready = []
        # Primero se prepara todo sin escribir (los nombres de los equipos, como activate_season.main, del raw
        # entero menos las demás pendientes: una que no encaja no cambia los nombres de otra); después se escribe.
        for comp, wanted in sorted(comps.items()):
            name = names.get(comp) or comp
            try:
                # El convenio, antes que la descarga: una competición sin él no se activará nunca sola, y
                # relanzar la descarga no lo arregla. Con el nombre de la federación (el del raw o el de
                # newCompetitions); el de newGroups es el de la web y no vale.
                fed_name = names.get(comp) if (comp in raw_comps or wanted is None) else None
                if fed_name:
                    try:
                        M.comp_meta(fed_name)
                    except ValueError:
                        raise Fallo(SIN_CONVENIO.format(fed_name))
                groups = _wanted_groups(comp, wanted, by_group, listed)
                new = [g for g in groups if (comp, g) not in known]
                if not new:
                    log(f"{name} [{comp}]: ya está entera en la temporada")
                    result["activated"].append({"competition": comp, "name": name, "codes": []})
                    continue
                try:
                    manifest = {"season": season, "groups": M.build(
                        raw, season, season_code(season), only={(comp, g) for g in new}, taken=taken)}
                except ValueError as error:
                    raise Fallo(str(error) if str(error).startswith("código repetido") else VERIFICACION.format(error))
                try:
                    validate_manifest(manifest, season, adding=True)
                    subset = [g for g in raw if str(g.get("competition_id")) == comp
                              or str(g.get("competition_id")) not in comps]
                    team_names = raw_team_names(subset, conn, season)
                    evidence = verify_sources(manifest, fiflp_raw=raw, names=team_names)
                except ValueError as error:
                    raise Fallo(VERIFICACION.format(error))
                taken |= {g["id"] for g in manifest["groups"]}
                ready.append((comp, name, manifest, evidence))
            except Fallo as error:
                log(f"{name} [{comp}]: {error}")
                result["failed"].append({"competition": comp, "name": name, "reason": str(error)})
        for comp, name, manifest, evidence in ready:
            codes = [g["id"] for g in manifest["groups"]]
            if not dry_run:
                try:
                    add_groups(conn, manifest, evidence)     # su propia transacción: o todos o ninguno
                except (ValueError, sqlite3.Error) as error:
                    log(f"{name} [{comp}]: {error}")
                    result["failed"].append({"competition": comp, "name": name, "reason": VERIFICACION.format(error)})
                    continue
            log(f"{name} [{comp}]: {'se activarían' if dry_run else 'activados'} {', '.join(codes)}")
            result["activated"].append({"competition": comp, "name": name, "codes": codes})
            result["groups"] += manifest["groups"]
    finally:
        conn.close()
    return result


def raw_de(comp, name, code, root=ROOT, raws=None):
    """El raw de la tanda de una competición: el de la tanda que la tiene (benjamín y prebenjamín en
    fiflp_islas_<code>_raw.json, alevín en fiflp_islas_<code>al_raw.json) o, si no está en ninguno, el
    de su categoría."""
    paths = [Path(root) / "scripts" / f"fiflp_islas_{code}{suffix}_raw.json" for suffix in ("", "al")]
    raws = raws if raws is not None else {}
    for path in paths:
        if path not in raws:
            raws[path] = {str(g.get("competition_id")) for g in _read_json(path, [])}
        if comp in raws[path]:
            return path
    return paths[1] if category_of(name or "") == "ALEVIN" else paths[0]


def run_sonda(root):
    """[{cat, id, phase, compKey}] de los grupos que la web pone en «otra-…» (scripts/sonda_fases.mjs)."""
    out = subprocess.run(["node", str(ROOT / "scripts" / "sonda_fases.mjs"), str(root), "--json"],
                         capture_output=True, text=True, timeout=300)
    if out.returncode not in (0, 1):
        raise RuntimeError((out.stderr or out.stdout).strip() or f"sale con {out.returncode}")
    return json.loads(out.stdout or "[]")


def regenerar(root, db_path):
    """generate_js sobre `root` y `db_path` (los vivos en el bot; una copia en las pruebas)."""
    import generate_js
    old = generate_js.PROJECT_ROOT, generate_js.get_connection
    try:
        generate_js.PROJECT_ROOT = str(root)
        generate_js.get_connection = lambda: get_connection(db_path)
        generate_js.main()
    finally:
        generate_js.PROJECT_ROOT, generate_js.get_connection = old


def _artefactos(root):
    root = Path(root)
    return sorted(root.glob("data-*.js")) + [p for p in (root / "index.html", root / "sw.js") if p.exists()]


def copia(root, db_path):
    """backups/auto-<UTC>/: la base (con la API de copia de SQLite) y lo que reescribe generate_js."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path(root) / "backups" / f"auto-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    source = get_connection(db_path)
    try:
        with sqlite3.connect(backup / "futbolbase.db") as target:
            source.backup(target)
        target.close()
    finally:
        source.close()
    for path in _artefactos(root):
        shutil.copy2(path, backup / path.name)
    return backup


def restaurar(backup, root, db_path):
    """Todo como en la copia: la base y los ficheros generados (los nuevos, fuera)."""
    source = sqlite3.connect(backup / "futbolbase.db")
    try:
        target = get_connection(db_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    for path in _artefactos(root):
        if not (backup / path.name).exists():
            path.unlink()
    for path in backup.iterdir():
        if path.name != "futbolbase.db":
            shutil.copy2(path, Path(root) / path.name)


def escribir_manifiesto(root, season, groups, today=None):
    """docs/temporadas/<temporada>-auto-<AAAAMMDD>.json: lo activado (como el manifiesto del camino manual),
    sumado a lo que ya hubiera del mismo día."""
    day = (today or datetime.now(timezone.utc)).strftime("%Y%m%d")
    path = Path(root) / "docs" / "temporadas" / f"{season}-auto-{day}.json"
    before = _read_json(path, {}).get("groups") or []
    fresh = {g["id"] for g in groups}
    manifest = {"season": season, "groups": [g for g in before if g.get("id") not in fresh] + list(groups)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def escribir_activacion(health_path, activation, done_comps, season_pairs):
    """`activation` en data-health.json del disco, sin tocar nada más (como source_health.py marcar); lo
    activado sale de newCompetitions y newGroups (la pasada siguiente del bot lo confirmaría igual)."""
    report = _read_json(health_path, {})
    if not isinstance(report, dict):
        report = {}
    report["activation"] = activation
    comps = [c for c in report.get("newCompetitions") or []
             if not (isinstance(c, dict) and str(c.get("id")) in done_comps)]
    groups = [g for g in report.get("newGroups") or []
              if not (isinstance(g, dict) and (str(g.get("competition")), str(g.get("id"))) in season_pairs)]
    for key, items in (("newCompetitions", comps), ("newGroups", groups)):
        if items:
            report[key] = items
        else:
            report.pop(key, None)
    Path(health_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def siguiente_intento(health, intento):
    """El intento siguiente de activar.yml (intento + 1) si todo lo que falló es la descarga incompleta (lo
    único que arregla volver a descargar) y quedan intentos (MAX_INTENTOS); None si no se relanza."""
    try:
        intento = int(intento)
    except (TypeError, ValueError):
        return None
    activation = (health or {}).get("activation")
    failed = activation.get("failed") if isinstance(activation, dict) else None
    if not isinstance(failed, list) or not failed or not 1 <= intento < MAX_INTENTOS:
        return None
    if all(isinstance(f, dict) and str(f.get("reason") or "").startswith(DESCARGA) for f in failed):
        return intento + 1
    return None


def pruebas_fallaron(health_path, db_path, ejecucion_path):
    """activar.yml, si las suites fallan tras activar: `health_path` es ya el data-health.json publicado (la base
    y lo generado, también) y `ejecucion_path` el que dejó esta ejecución. Lo activado pasa a fallido por
    PRUEBAS (lo que falló por otra cosa conserva su motivo), con su `at` y su `tried` (el freno de 6 h de
    source_health.py pendiente). Sin el de la ejecución, todo lo pendiente cuenta como intentado y fallido."""
    published = _read_json(health_path, {})
    run_activation = _read_json(ejecucion_path, {})
    run_activation = run_activation.get("activation") if isinstance(run_activation, dict) else None
    if isinstance(run_activation, dict) and isinstance(run_activation.get("tried"), list):
        activated = [a for a in run_activation.get("activated") or [] if isinstance(a, dict)]
        failed = [f for f in run_activation.get("failed") or [] if isinstance(f, dict)]
        failed += [{"competition": a.get("competition"), "name": a.get("name"), "reason": PRUEBAS}
                   for a in activated if a.get("codes")]
        # Lo que ya estaba entero en la temporada (sin códigos) no se tocó: sigue activado.
        activation = {"at": run_activation.get("at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "activated": [a for a in activated if not a.get("codes")], "failed": failed,
                      "tried": list(run_activation["tried"])}
    else:
        comps, names = pendientes(published), nombres(published)
        activation = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "activated": [],
                      "failed": [{"competition": c, "name": names.get(c) or c, "reason": PRUEBAS} for c in comps],
                      "tried": sorted(comps)}
    conn = get_connection(db_path)
    try:
        sid, _ = _current(conn)
        season_pairs, _ = _season_groups(conn, sid)
    finally:
        conn.close()
    escribir_activacion(health_path, activation, {a["competition"] for a in activation["activated"]}, season_pairs)


def main(argv=None, root=ROOT, sonda=run_sonda, generar=regenerar, log=print):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, help="el raw de todas las pendientes (sin él, el de la tanda de cada una)")
    parser.add_argument("--dry-run", action="store_true", help="solo comprobar: no escribe nada")
    parser.add_argument("--pendientes", action="store_true", help="imprime los ids pendientes, separados por comas")
    parser.add_argument("--temporada", action="store_true",
                        help="imprime el CodTemporada de la federación de la temporada en curso (la tanda)")
    parser.add_argument("--relanzar", metavar="INTENTO",
                        help="activar.yml: imprime el intento siguiente y sale con 0 si toca relanzar; con 1 si no")
    parser.add_argument("--pruebas-fallaron", metavar="INFORME", type=Path,
                        help="activar.yml: las suites fallaron tras activar (INFORME, el data-health.json de la ejecución)")
    args = parser.parse_args(argv)
    root = Path(root)
    health_path, db_path = root / "data-health.json", root / "futbolbase.db"
    health = _read_json(health_path, {})
    comps, names = pendientes(health), nombres(health)
    if args.pendientes:
        print(",".join(comps))
        return 0
    if args.temporada:
        conn = get_connection(db_path)
        try:
            print(season_code(_current(conn)[1]))
        finally:
            conn.close()
        return 0
    if args.relanzar is not None:
        nxt = siguiente_intento(health, args.relanzar)
        if nxt is None:
            # A stderr: activar.yml recoge la salida (el intento siguiente) y esto va al registro.
            print(f"Sin relanzar (intento {args.relanzar}): nada fallido, algo que no es la descarga o sin intentos.",
                  file=sys.stderr)
            return 1
        print(nxt)
        return 0
    if args.pruebas_fallaron is not None:
        pruebas_fallaron(health_path, db_path, args.pruebas_fallaron)
        return 0
    if not comps:
        log("Nada pendiente de activar.")
        return 0
    conn = get_connection(db_path)
    try:
        sid, season = _current(conn)
    finally:
        conn.close()
    by_raw, seen = {}, {}
    for comp, wanted in comps.items():
        path = Path(args.raw) if args.raw else raw_de(comp, names.get(comp), season_code(season), root, seen)
        by_raw.setdefault(path, {})[comp] = wanted
    backup = None if args.dry_run else copia(root, db_path)
    result = {"activated": [], "failed": [], "groups": []}
    for path, subset in sorted(by_raw.items()):
        log(f"{path.name}: {', '.join(subset)}")
        part = activar(path, db_path, subset, root=root, log=log, dry_run=args.dry_run, names=names)
        for key in result:
            result[key] += part[key]
    activated = [a for a in result["activated"] if a["codes"]]
    if args.dry_run:
        return 1 if result["failed"] else 0
    if activated:
        try:
            generar(root, db_path)
            escribir_manifiesto(root, season, result["groups"])
        except Exception as error:          # cualquier fallo tras escribir: todo como estaba
            restaurar(backup, root, db_path)
            log(f"Deshecho: {error}")
            result["failed"] += [{"competition": a["competition"], "name": a["name"],
                                  "reason": SIN_GENERAR.format(error)} for a in activated]
            result["activated"] = [a for a in result["activated"] if not a["codes"]]
            activated = []
    if activated:
        owner = {code: a for a in activated for code in a["codes"]}
        try:
            otras = sonda(root)
        except Exception as error:          # sin sonda no se sabe: en rojo, sin deshacer
            otras = []
            result["failed"] += [{"competition": a["competition"], "name": a["name"],
                                  "reason": SIN_SONDA.format(error)} for a in activated]
        reported = set()
        for group in otras:
            item = owner.get(group.get("id"))
            if item is None:
                log(f"Fase que la web no reconoce, de antes: {group.get('id')} {group.get('phase')}")
                continue
            if (item["competition"], group.get("phase")) in reported:
                continue
            reported.add((item["competition"], group.get("phase")))
            result["failed"].append({"competition": item["competition"], "name": item["name"],
                                     "reason": FASE_DESCONOCIDA.format(group.get("phase"))})
    if not activated and backup is not None:
        shutil.rmtree(backup)               # nada cambió: la copia sobra
    conn = get_connection(db_path)
    try:
        season_pairs, _ = _season_groups(conn, sid)
    finally:
        conn.close()
    activation = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "activated": [{k: a[k] for k in ("competition", "name", "codes")} for a in result["activated"]],
                  "failed": result["failed"], "tried": sorted(comps)}
    escribir_activacion(health_path, activation, {a["competition"] for a in result["activated"]}, season_pairs)
    for item in result["failed"]:
        log(f"No activada: {item['name']} [{item['competition']}]: {item['reason']}")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
