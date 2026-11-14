"""Activación sin manos (fase 2D de v2, tarea 2): scripts/activar_auto.py activa, a partir de un raw de la
federación ya descargado, lo que el bot apuntó en data-health.json (newCompetitions enteras y newGroups
sueltos): manifiesto (fiflp_manifest.build) → verify_sources → add_groups, una transacción por competición,
generate_js y la sonda de fases (sonda_fases.mjs). Todo o nada por competición: una que no encaja no toca la
base ni impide las demás, y lo que falló queda en data-health.json (`activation`). Sin red: árboles
sintéticos en una carpeta de la prueba (base pequeña, raw, data-health.json), nunca los vivos.
"""
from datetime import datetime
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import activar_auto as A  # noqa: E402
import fetch_fiflp_2425 as F  # noqa: E402
import source_health  # noqa: E402
from activate_season import fiflp_evidence, verify_sources  # noqa: E402
from db import SCHEMA  # noqa: E402
from migrate_actas_schema import migrate  # noqa: E402

URL = ("https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120"
       "&CodTemporada=22&CodCompeticion={comp}&CodGrupo={grupo}")
FF = ("54976988", "LIGA BENJAMIN GRAN CANARIA FASE PREVIA")
PLZ = ("54977161", "LIGA PREBENJAMIN LANZAROTE")
SEGUNDA = ("55400001", "LIGA BENJAMIN GRAN CANARIA SEGUNDA FASE A")
TORNEO = ("55400002", "TORNEO PREBENJAMIN X")
COPA = ("55331982", "COPA BENJAMÍN GRAN CANARIA")
ALEVIN = ("54976940", "LIGA ALEVIN GRAN CANARIA FASE PREVIA")
TEAMS = ['ARUCAS, C.F. "A"', 'MOYA, U.D. "B"', 'TELDE, U.D. "A"', 'GALDAR, C.D. "A"']
WORKER = ("const CACHE_NAME = 'futbolbase2-v20261101';\n"
          "const CRESTS_CACHE = 'futbolbase2-escudos-00000000';\n"
          "const STATIC_ASSETS = [\n  './',\n];\n\n"
          "const SEASON_FILES = [\n  './data-season-2025-2026.js',\n];\n\n"
          "function classifyRequest(pathname) {}\n")


def group_id(comp, n):
    return str(int(comp[0][-3:]) * 100 + n)


def entry(comp, n, table=True, played=True, name=None):
    """Un grupo del raw de fetch_fiflp_islas: dos jornadas, cuatro equipos y, si `table`, su clasificación."""
    teams = TEAMS
    rounds = [{"num": str(j), "date": f"0{j + 2}-10-2026", "matches": [
        {"home": teams[0 + j % 2], "away": teams[2 + j % 2], "hs": 2 if played else None, "as": 1 if played else None,
         "date": f"0{j + 2}-10-2026", "time": "10:00", "venue": "CAMPO"},
        {"home": teams[1 - j % 2], "away": teams[3 - j % 2], "hs": 0 if played else None, "as": 0 if played else None,
         "date": f"0{j + 2}-10-2026", "time": "11:00", "venue": "CAMPO"}]} for j in (1, 2)]
    standings = [{"pos": i, "team": t, "pts": 3, "j": 2, "g": 1, "e": 0, "p": 1, "gf": 2, "gc": 2, "df": 0}
                 for i, t in enumerate(teams, 1)] if table else []
    return {"competition_id": comp[0], "competition_name": comp[1], "cat": "", "island": "", "phase": comp[1],
            "group_id": group_id(comp, n), "group_name": name or f"GRUPO {n}", "standings": standings, "jornadas": rounds}


def tree(tmp_path, raw=(), listed=None, health=None, ff_groups=3, raw_al=()):
    """Un árbol de la web con la temporada 2026-27 en curso y `ff_groups` grupos de la Fase Previa de
    benjamín ya activados (FF1…); el raw de la tanda 22 (y el de 22al), la lista de grupos de la federación
    (`listed`; por defecto, la de los grupos del raw) y data-health.json con `health`."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.js").write_text("export const PORTAL = " + json.dumps(
        {"season": "2026-2027", "nextSeason": "2027-2028",
         "defaultTeam": {"cat": "benjamin", "groupId": "FF1", "name": "Arucas"}, "timeZone": "Atlantic/Canary"},
        indent=2) + ";\n", encoding="utf-8")
    (tmp_path / "index.html").write_text('<script defer src="./data-seasons.js?v=20261101"></script>\n'
                                         '<span id="legacyUpdated" hidden>Última actualización: 01/11/2026</span>\n',
                                         encoding="utf-8")
    (tmp_path / "sw.js").write_text(WORKER, encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "futbolbase.db")
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.execute("INSERT INTO seasons(id,name,start_year,end_year,is_current) VALUES (1,'2026-2027',2026,2027,1)")
    conn.execute("INSERT INTO categories(id,name) VALUES (1,'BENJAMIN'),(2,'PREBENJAMIN')")
    for i, name in enumerate(["Arucas", "Moya B", "Telde", "Gáldar"], 1):
        conn.execute("INSERT INTO teams(id,name) VALUES (?,?)", (i, name))
    for n in range(1, ff_groups + 1):
        gid = conn.execute("""INSERT INTO groups(season_id,category_id,code,name,full_name,phase,island,url,current_jornada)
            VALUES (1,1,?,?,?,'Primera Fase GC','grancanaria',?,'Jornada 1')""",
                           (f"FF{n}", f"Grupo {n}", f"BENJAMIN PRIMERA FASE GC - GRUPO {n}",
                            URL.format(comp=FF[0], grupo=group_id(FF, n)))).lastrowid
        for pos, team in enumerate((1, 2, 3, 4), 1):
            conn.execute("""INSERT INTO standings(group_id,team_id,position,points,played,won,drawn,lost,gf,gc,gd)
                VALUES (?,?,?,3,1,1,0,0,2,1,1)""", (gid, team, pos))
        conn.execute("""INSERT INTO matches(group_id,jornada,date,home_team_id,away_team_id,home_score,away_score)
            VALUES (?,'Jornada 1','2026-10-03',1,3,2,1)""", (gid,))
    conn.commit()
    conn.close()
    (tmp_path / "scripts").mkdir()
    for suffix, items in (("", raw), ("al", raw_al)):
        if items:
            (tmp_path / "scripts" / f"fiflp_islas_22{suffix}_raw.json").write_text(json.dumps(list(items)), encoding="utf-8")
            listing = listed if listed is not None and suffix == "" else {}
            if listed is None or suffix == "al":
                for g in items:
                    listing.setdefault(g["competition_id"], {})[g["group_id"]] = g["group_name"]
            (tmp_path / "scripts" / f"fiflp_islas_22{suffix}_grupos.json").write_text(json.dumps(listing), encoding="utf-8")
    (tmp_path / "data-health.json").write_text(json.dumps(
        {"version": 1, "season": "2026-2027", "groups": {}, "runHealth": {"ok": True}, **(health or {})},
        indent=2) + "\n", encoding="utf-8")
    return tmp_path


def new_comp(comp):
    return {"id": comp[0], "name": comp[1], "firstSeen": "2026-11-14"}


def run(root, *argv, sonda=lambda root: [], generar=A.regenerar):
    logs = []
    code = A.main(list(argv), root=root, sonda=sonda, generar=generar, log=logs.append)
    return code, logs


def health(root):
    return json.loads((root / "data-health.json").read_text(encoding="utf-8"))


def codes(root):
    conn = sqlite3.connect(root / "futbolbase.db")
    try:
        return [r[0] for r in conn.execute("SELECT code FROM groups ORDER BY id")]
    finally:
        conn.close()


def fingerprint(root):
    """Lo que la activación podría cambiar: la base (su volcado), los data-*.js, index.html, sw.js,
    data-health.json, docs/ y backups/."""
    conn = sqlite3.connect(root / "futbolbase.db")
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    files = {p.relative_to(root).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest()
             for pattern in ("data-*", "index.html", "sw.js", "docs/**/*", "backups/**/*") for p in root.glob(pattern)
             if p.is_file()}
    return dump, files


# ── Qué está pendiente ───────────────────────────────────────────────────────

def test_pendientes_son_las_competiciones_enteras_y_los_grupos_sueltos():
    report = {"newCompetitions": [new_comp(PLZ), {"id": "x"}, None],
              "newGroups": [{"competition": FF[0], "competitionName": "BENJAMIN PRIMERA FASE GC", "id": "26", "name": "GRUPO 26"},
                            {"competition": FF[0], "id": "25"}, {"competition": FF[0], "id": "25"},
                            {"competition": PLZ[0], "id": "9"}, {"competition": "", "id": "1"}, "x"]}
    assert A.pendientes(report) == {FF[0]: ["25", "26"], PLZ[0]: None}
    assert A.pendientes({}) == {}
    assert A.nombres(report)[PLZ[0]] == PLZ[1]


# ── Review Focus 1: lo que encaja se activa solo ────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None, reason="la sonda de fases necesita node")
def test_una_liga_prebenjamin_insular_y_una_segunda_fase_se_activan_solas(tmp_path):
    raw = [entry(FF, n) for n in (1, 2, 3)] + [entry(PLZ, 1), entry(PLZ, 2), entry(SEGUNDA, 1)]
    root = tree(tmp_path, raw, health={"newCompetitions": [new_comp(PLZ), new_comp(SEGUNDA)]})
    code = A.main([], root=root, log=lambda *a: None)          # con la sonda de verdad (node)
    assert code == 0
    assert codes(root) == ["FF1", "FF2", "FF3", "PLZ1", "PLZ2", "A1"]      # por id de competición
    conn = sqlite3.connect(root / "futbolbase.db")
    assert conn.execute("SELECT code, phase, island FROM groups WHERE code IN ('PLZ1','A1') ORDER BY code").fetchall() == [
        ("A1", "Segunda Fase A", "grancanaria"), ("PLZ1", "Lanzarote", "lanzarote")]
    assert conn.execute("SELECT count(*) FROM fiflp_full_pending").fetchone()[0] == 3   # primera pasada completa
    assert conn.execute("SELECT count(*) FROM standings s JOIN groups g ON g.id=s.group_id WHERE g.code='PLZ1'").fetchone()[0] == 4
    conn.close()
    assert '"PLZ1"' in (root / "data-prebenjamin.js").read_text() and '"A1"' in (root / "data-benjamin.js").read_text()
    report = health(root)
    assert "newCompetitions" not in report
    activation = report["activation"]
    assert activation["activated"] == [
        {"competition": PLZ[0], "name": PLZ[1], "codes": ["PLZ1", "PLZ2"]},
        {"competition": SEGUNDA[0], "name": SEGUNDA[1], "codes": ["A1"]}]
    assert activation["failed"] == [] and activation["tried"] == [PLZ[0], SEGUNDA[0]]
    manifest = json.loads(next((root / "docs" / "temporadas").glob("2026-2027-auto-*.json")).read_text())
    assert [g["id"] for g in manifest["groups"]] == ["PLZ1", "PLZ2", "A1"]
    assert manifest["groups"][0]["url"] == URL.format(comp=PLZ[0], grupo=group_id(PLZ, 1))
    backup = next((root / "backups").glob("auto-*"))                 # la copia de antes de escribir
    assert "PLZ1" not in "\n".join(sqlite3.connect(backup / "futbolbase.db").iterdump())
    assert (backup / "index.html").exists()


# ── Review Focus 2: sin convenio, nada cambia ────────────────────────────────

def test_una_competicion_sin_convenio_no_cambia_nada_y_sale_en_rojo(tmp_path):
    raw = [entry(FF, n) for n in (1, 2, 3)] + [entry(TORNEO, 1)]
    root = tree(tmp_path, raw, health={"newCompetitions": [new_comp(TORNEO)]})
    dump, files = fingerprint(root)
    code, _ = run(root, generar=lambda *a: pytest.fail("no se regenera sin nada activado"))
    assert code == 1
    after_dump, after_files = fingerprint(root)
    assert after_dump == dump
    assert {k: v for k, v in after_files.items() if k != "data-health.json"} == \
        {k: v for k, v in files.items() if k != "data-health.json"}       # ni data-*.js, ni copias, ni manifiesto
    report = health(root)
    assert report["newCompetitions"] == [new_comp(TORNEO)]
    assert report["activation"]["failed"] == [
        {"competition": TORNEO[0], "name": TORNEO[1], "reason": "sin convenio de código: TORNEO PREBENJAMIN X"}]
    assert report["activation"]["activated"] == [] and report["activation"]["tried"] == [TORNEO[0]]
    assert report["runHealth"] == {"ok": True}          # lo demás del informe, igual


# ── Review Focus 3: una no bloquea a la otra ─────────────────────────────────

def test_de_dos_pendientes_se_activa_la_que_encaja_y_la_otra_sigue_pendiente(tmp_path):
    raw = [entry(PLZ, 1), entry(TORNEO, 1)]
    root = tree(tmp_path, raw, health={"newCompetitions": [new_comp(PLZ), new_comp(TORNEO)]})
    code, _ = run(root)
    assert code == 1
    assert codes(root)[-1:] == ["PLZ1"]
    report = health(root)
    assert report["newCompetitions"] == [new_comp(TORNEO)]
    assert [a["competition"] for a in report["activation"]["activated"]] == [PLZ[0]]
    assert [f["competition"] for f in report["activation"]["failed"]] == [TORNEO[0]]


# ── Review Focus 4: un grupo nuevo en una competición ya activada ────────────

def test_un_grupo_25_nuevo_entra_solo_y_los_24_de_antes_no_se_tocan(tmp_path):
    raw = [entry(FF, n) for n in range(1, 26)]
    pending = {"newGroups": [{"competition": FF[0], "competitionName": "BENJAMIN PRIMERA FASE GC",
                              "id": group_id(FF, 25), "name": "GRUPO 25", "firstSeen": "2026-11-14"}]}
    root = tree(tmp_path, raw, listed={}, health=pending, ff_groups=24)      # sin lista: no hace falta
    conn = sqlite3.connect(root / "futbolbase.db")
    before = [conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in ("groups", "standings", "matches")]
    conn.close()
    code, _ = run(root)
    assert code == 0
    assert codes(root) == [f"FF{n}" for n in range(1, 26)]
    conn = sqlite3.connect(root / "futbolbase.db")
    after = [conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in ("groups", "standings", "matches")]
    conn.close()
    assert [rows[:len(old)] for rows, old in zip(after, before)] == before          # los de antes, intactos
    assert "newGroups" not in health(root)
    assert health(root)["activation"]["activated"] == [
        {"competition": FF[0], "name": FF[1], "codes": ["FF25"]}]


def test_un_grupo_nuevo_cuyo_codigo_ya_existe_falla_con_el_codigo(tmp_path):
    raw = [entry(FF, n) for n in (1, 2, 3)] + [entry(FF, 9, name="GRUPO 3")]
    pending = {"newGroups": [{"competition": FF[0], "id": group_id(FF, 9), "name": "GRUPO 3"}]}
    root = tree(tmp_path, raw, health=pending)
    dump, _ = fingerprint(root)
    assert run(root)[0] == 1
    assert fingerprint(root)[0] == dump
    assert health(root)["activation"]["failed"] == [
        {"competition": FF[0], "name": FF[1], "reason": "código repetido: FF3"}]


# ── Descarga incompleta: nada a medias ───────────────────────────────────────

@pytest.mark.parametrize("listed, raw_groups, reason", [
    ({PLZ[0]: {group_id(PLZ, 1): "GRUPO 1", group_id(PLZ, 2): "GRUPO 2", group_id(PLZ, 3): "GRUPO 3"}}, (1, 2),
     "la descarga no está completa: faltan 1 grupos"),
    ({}, (1, 2), "la descarga no está completa: falta la lista de grupos de la federación"),
])
def test_si_falta_un_grupo_del_desplegable_o_la_lista_no_se_activa_nada(tmp_path, listed, raw_groups, reason):
    root = tree(tmp_path, [entry(PLZ, n) for n in raw_groups], listed=listed,
                health={"newCompetitions": [new_comp(PLZ)]})
    dump, _ = fingerprint(root)
    assert run(root)[0] == 1
    assert fingerprint(root)[0] == dump
    assert health(root)["activation"]["failed"] == [{"competition": PLZ[0], "name": PLZ[1], "reason": reason}]
    assert health(root)["newCompetitions"] == [new_comp(PLZ)]


def test_un_grupo_guardado_vacio_cuenta_como_que_falta(tmp_path):
    empty = dict(entry(PLZ, 2), standings=[], jornadas=[])
    root = tree(tmp_path, [entry(PLZ, 1), empty], health={"newCompetitions": [new_comp(PLZ)]})
    assert run(root)[0] == 1
    assert health(root)["activation"]["failed"][0]["reason"] == "la descarga no está completa: faltan 1 grupos"
    assert codes(root) == ["FF1", "FF2", "FF3"]


def test_una_competicion_que_no_esta_en_ningun_raw_falla_por_la_descarga(tmp_path):
    root = tree(tmp_path, [entry(FF, 1)], health={"newCompetitions": [new_comp(PLZ)]})
    assert run(root)[0] == 1
    assert health(root)["activation"]["failed"][0]["reason"].startswith("la descarga no está completa")


# ── La copa a partido único, sin tabla inventada ─────────────────────────────

def test_una_copa_a_partido_unico_sin_tabla_se_activa_sin_filas_en_standings(tmp_path):
    copa = entry(COPA, 1, table=False, played=False, name="Eliminatoria previa")
    root = tree(tmp_path, [copa], health={"newCompetitions": [new_comp(COPA)]})
    assert run(root)[0] == 0
    conn = sqlite3.connect(root / "futbolbase.db")
    assert conn.execute("SELECT g.code, g.name, g.phase, count(s.id) FROM groups g LEFT JOIN standings s ON s.group_id=g.id "
                        "WHERE g.code='CGC1'").fetchone() == ("CGC1", "Eliminatoria previa", "Copa Gran Canaria", 0)
    assert conn.execute("SELECT count(*) FROM matches m JOIN groups g ON g.id=m.group_id WHERE g.code='CGC1'").fetchone()[0] == 4
    conn.close()


def test_una_liga_sin_tabla_todavia_sigue_con_su_tabla_a_cero_y_la_copa_sin_ella():
    liga = entry(PLZ, 1, table=False, played=False)
    copa = entry(COPA, 1, table=False, played=False)
    group = lambda comp, code, phase: {"id": code, "phase": phase, "url": URL.format(comp=comp[0], grupo=group_id(comp, 1))}
    _, standings = fiflp_evidence(group(PLZ, "PLZ1", "Lanzarote"), [liga])
    assert [row[2:] for row in standings] == [[0] * 8] * 4
    assert fiflp_evidence(group(COPA, "CGC1", "Copa Gran Canaria"), [copa])[1] == []
    manifest = lambda comp, code, phase: {"season": "2026-2027", "groups": [dict(
        group(comp, code, phase), cat="benjamin", name="Grupo 1", island="grancanaria")]}
    assert verify_sources(manifest(COPA, "CGC1", "Copa Gran Canaria"), fiflp_raw=[copa])[0]["standings"] == []
    # Una liga cuya tabla no sale de ningún sitio (sin calendario tampoco) sigue sin pasar.
    with pytest.raises(ValueError, match="faltan clasificación o partidos"):
        verify_sources(manifest(PLZ, "PLZ1", "Lanzarote"), fiflp_raw=[dict(liga, jornadas=[])])


# ── --dry-run, segunda ejecución y la forma de `activation` ──────────────────

def test_dry_run_no_escribe_nada(tmp_path):
    root = tree(tmp_path, [entry(PLZ, 1), entry(PLZ, 2), entry(TORNEO, 1)],
                health={"newCompetitions": [new_comp(PLZ), new_comp(TORNEO)]})
    dump, files = fingerprint(root)
    code, logs = run(root, "--dry-run", generar=lambda *a: pytest.fail("nada se genera en --dry-run"),
                     sonda=lambda *a: pytest.fail("ni se sondea"))
    assert code == 1                                    # el torneo fallaría
    assert fingerprint(root) == (dump, files)
    assert not (root / "backups").exists()
    assert any("se activarían PLZ1, PLZ2" in line for line in logs)


def test_activation_bien_formado_y_la_segunda_ejecucion_no_hace_nada(tmp_path):
    root = tree(tmp_path, [entry(PLZ, 1)], health={"newCompetitions": [new_comp(PLZ)]})
    assert run(root)[0] == 0
    activation = health(root)["activation"]
    assert set(activation) == {"at", "activated", "failed", "tried", "attempts"}
    assert datetime.fromisoformat(activation["at"]).tzinfo is not None
    assert all(set(a) == {"competition", "name", "codes"} for a in activation["activated"])
    snapshot = fingerprint(root)
    code, logs = run(root, generar=lambda *a: pytest.fail("sin pendientes no se genera"))
    assert code == 0 and logs == ["Nada pendiente de activar."]
    assert fingerprint(root) == snapshot


def test_pendientes_imprime_los_ids(tmp_path, capsys):
    root = tree(tmp_path, [entry(PLZ, 1)], health={
        "newCompetitions": [new_comp(PLZ)], "newGroups": [{"competition": FF[0], "id": "77"}]})
    assert run(root, "--pendientes")[0] == 0
    assert capsys.readouterr().out == f"{FF[0]},{PLZ[0]}\n"


def test_temporada_imprime_el_codigo_de_la_federacion_de_la_temporada_en_curso(tmp_path, capsys):
    """activar.yml descarga la tanda de la temporada en curso (22 y 22al en 2026-27) sin escribirla a fuego."""
    root = tree(tmp_path)
    assert run(root, "--temporada")[0] == 0
    assert capsys.readouterr().out == "22\n"


# ── Los intentos y lo que deja activar.yml ──────────────────────────────────

def falla(comp, reason):
    return {"competition": comp[0], "name": comp[1], "reason": reason}


def test_attempts_cuenta_los_intentos_seguidos_del_mismo_conjunto(tmp_path):
    """Ronda de arreglo 1: activation.attempts, 1 con otro conjunto de pendientes que el intento anterior y el
    anterior + 1 con el mismo (source_health.py pendiente reanuda una descarga incompleta hasta 8)."""
    root = tree(tmp_path, [entry(PLZ, 1)], listed={PLZ[0]: {group_id(PLZ, 1): "GRUPO 1", group_id(PLZ, 2): "GRUPO 2"}},
                health={"newCompetitions": [new_comp(PLZ)]})
    assert run(root)[0] == 1                                        # falta el grupo 2: descarga incompleta
    assert health(root)["activation"]["attempts"] == 1
    assert run(root)[0] == 1
    assert run(root)[0] == 1
    assert health(root)["activation"]["attempts"] == 3
    report = health(root)
    report["newCompetitions"].append(new_comp(TORNEO))              # otro conjunto: vuelve a 1
    (root / "data-health.json").write_text(json.dumps(report), encoding="utf-8")
    assert run(root)[0] == 1
    assert health(root)["activation"]["attempts"] == 1 and health(root)["activation"]["tried"] == [PLZ[0], TORNEO[0]]


def test_un_reintento_que_falla_igual_no_reescribe_el_informe_hasta_pasado_un_dia(tmp_path):
    """Sin commits de ruido: mismo resultado que el publicado (nada activado, los mismos fallos, ninguno de
    descarga) de hace menos de 24 h → data-health.json tal cual (ni `at` ni `attempts`). Pasadas 24 h sí se
    reescribe (`at` nuevo: lo necesita el freno de 24 h de source_health.py pendiente): un commit al día."""
    root = tree(tmp_path, [entry(TORNEO, 1)], health={"newCompetitions": [new_comp(TORNEO)]})
    assert run(root)[0] == 1
    first = (root / "data-health.json").read_bytes()
    assert run(root)[0] == 1
    assert (root / "data-health.json").read_bytes() == first
    report = json.loads(first)
    report["activation"]["at"] = "2026-11-01T10:00:00+00:00"        # de hace días
    (root / "data-health.json").write_text(json.dumps(report), encoding="utf-8")
    assert run(root)[0] == 1
    activation = health(root)["activation"]
    assert activation["at"] != "2026-11-01T10:00:00+00:00" and activation["attempts"] == 2
    assert activation["failed"] == report["activation"]["failed"]


def test_pruebas_fallaron_parte_del_publicado_y_apunta_el_motivo(tmp_path):
    """Si las suites fallan tras activar, activar.yml deja la base y lo generado como estaban (los publicados) y
    sube solo data-health.json: el publicado, con lo que se intentó como fallido por las pruebas (lo que ya
    había fallado por otra cosa conserva su motivo); lo activado sigue en newCompetitions/newGroups."""
    root = tree(tmp_path, [entry(PLZ, 1)], health={"newCompetitions": [new_comp(PLZ), new_comp(TORNEO)]})
    published = health(root)
    ejecucion = tmp_path / "activacion.json"
    (ejecucion).write_text(json.dumps({**published, "activation": {
        "at": "2026-11-14T10:00:00+00:00", "activated": [{"competition": PLZ[0], "name": PLZ[1], "codes": ["PLZ1"]}],
        "failed": [falla(TORNEO, A.SIN_CONVENIO.format(TORNEO[1]))], "tried": [PLZ[0], TORNEO[0]], "attempts": 3}}))
    assert run(root, "--pruebas-fallaron", str(ejecucion))[0] == 0
    after = health(root)
    assert after.pop("activation") == {
        "at": "2026-11-14T10:00:00+00:00", "activated": [], "tried": [PLZ[0], TORNEO[0]], "attempts": 3,
        "failed": [falla(TORNEO, A.SIN_CONVENIO.format(TORNEO[1])), falla(PLZ, A.PRUEBAS)]}
    assert after == published
    assert A.PRUEBAS == "las pruebas fallaron tras activar"


def test_pruebas_fallaron_sin_el_informe_de_la_ejecucion_frena_igual(tmp_path):
    """Sin el informe de la ejecución (no se pudo leer), todo lo pendiente cuenta como intentado y fallido por
    las pruebas: sin `tried`, cada pasada del bot relanzaría la activación (source_health.py pendiente)."""
    root = tree(tmp_path, health={"newCompetitions": [new_comp(PLZ)], "newGroups": [{"competition": FF[0], "id": "77"}]})
    assert run(root, "--pruebas-fallaron", str(tmp_path / "no-existe.json"))[0] == 0
    activation = health(root)["activation"]
    assert activation["tried"] == [FF[0], PLZ[0]] and activation["activated"] == [] and activation["attempts"] == 1
    assert [f["reason"] for f in activation["failed"]] == [A.PRUEBAS, A.PRUEBAS]
    assert datetime.fromisoformat(activation["at"]).tzinfo is not None


# ── Lo que pasa después de escribir ──────────────────────────────────────────

def test_si_generar_falla_la_base_y_los_ficheros_vuelven_a_la_copia(tmp_path):
    root = tree(tmp_path, [entry(PLZ, 1)], health={"newCompetitions": [new_comp(PLZ)]})
    A.regenerar(root, root / "futbolbase.db")            # data-*.js de partida, como en el árbol vivo
    dump, files = fingerprint(root)

    def roto(root_, db_path):
        A.regenerar(root_, db_path)                     # escribe los data-*.js nuevos…
        (Path(root_) / "data-extra.js").write_text("x")
        raise RuntimeError("disco lleno")               # …y falla después
    code, _ = run(root, generar=roto)
    assert code == 1
    after_dump, after_files = fingerprint(root)
    assert after_dump == dump
    assert {k: v for k, v in after_files.items() if not k.startswith(("data-health", "backups/"))} == \
        {k: v for k, v in files.items() if not k.startswith(("data-health", "backups/"))}
    report = health(root)
    assert report["activation"]["failed"] == [
        {"competition": PLZ[0], "name": PLZ[1], "reason": "no se pudo regenerar la web: disco lleno"}]
    assert report["activation"]["activated"] == [] and report["newCompetitions"] == [new_comp(PLZ)]


def test_una_fase_que_la_web_no_reconoce_queda_en_rojo_sin_deshacer(tmp_path):
    root = tree(tmp_path, [entry(PLZ, 1), entry(PLZ, 2)], health={"newCompetitions": [new_comp(PLZ)]})
    otras = [{"cat": "prebenjamin", "id": "PLZ1", "phase": "Lanzarote", "compKey": "lanzarote-otra-x"},
             {"cat": "prebenjamin", "id": "PLZ2", "phase": "Lanzarote", "compKey": "lanzarote-otra-x"},
             {"cat": "benjamin", "id": "FF1", "phase": "Primera Fase GC", "compKey": "otra-y"}]
    code, _ = run(root, sonda=lambda root: otras)
    assert code == 1
    assert codes(root)[-2:] == ["PLZ1", "PLZ2"]          # los datos se quedan
    activation = health(root)["activation"]
    assert activation["activated"][0]["codes"] == ["PLZ1", "PLZ2"]
    assert activation["failed"] == [
        {"competition": PLZ[0], "name": PLZ[1], "reason": "fase que la web no reconoce: Lanzarote"}]
    assert "newCompetitions" not in health(root)


# ── Qué raw para cada competición ────────────────────────────────────────────

def test_cada_competicion_se_busca_en_el_raw_de_su_tanda(tmp_path):
    root = tree(tmp_path, [entry(PLZ, 1)], raw_al=[entry(ALEVIN, 1)],
                health={"newCompetitions": [new_comp(PLZ), new_comp(ALEVIN)]})
    scripts = root / "scripts"
    assert A.raw_de(ALEVIN[0], ALEVIN[1], "22", root) == scripts / "fiflp_islas_22al_raw.json"
    assert A.raw_de(PLZ[0], PLZ[1], "22", root) == scripts / "fiflp_islas_22_raw.json"
    # La que no está en ninguno, en el de su categoría.
    assert A.raw_de("1", "LIGA ALEVIN GRAN CANARIA SEGUNDA FASE B", "22", root) == scripts / "fiflp_islas_22al_raw.json"
    assert A.raw_de("1", None, "22", root) == scripts / "fiflp_islas_22_raw.json"
    conn = sqlite3.connect(root / "futbolbase.db")
    conn.execute("INSERT INTO categories(id,name) VALUES (3,'ALEVIN')")
    conn.commit()
    conn.close()
    assert run(root)[0] == 0
    assert codes(root)[-2:] == ["PLZ1", "AL1"]


# ── La lista de grupos de la federación que deja la descarga ─────────────────

class Page:
    def __init__(self, groups):
        self.groups, self.evaluated = groups, 0

    def evaluate(self, script):
        self.evaluated += 1
        return self.groups


def test_la_descarga_apunta_los_grupos_del_desplegable_sin_pedir_nada_mas(tmp_path, monkeypatch):
    path = tmp_path / "fiflp_islas_22_grupos.json"
    monkeypatch.setattr(F, "GROUPS_PATH", str(path))
    visits = []
    monkeypatch.setattr(F, "goto", lambda page, url, retries=3: visits.append(url) or True)
    comp = {"id": PLZ[0], "name": PLZ[1], "cat": "prebenjamin", "island": "lanzarote", "phase": PLZ[1]}
    page = Page([{"value": "11", "text": "GRUPO 1"}, {"value": "12", "text": "GRUPO 2"}])
    assert F.scrape_competition(page, comp, done={f"{PLZ[0]}_11", f"{PLZ[0]}_12"}) == []
    assert len(visits) == 1 and page.evaluated == 1     # la misma página de siempre, y nada más
    assert json.loads(path.read_text()) == {PLZ[0]: {"11": "GRUPO 1", "12": "GRUPO 2"}}
    # Otra competición se suma; un desplegable vacío (no servido a tiempo) no borra lo de antes.
    F.save_group_list("999", [{"value": "1", "text": "GRUPO 1"}])
    F.save_group_list(PLZ[0], [])
    assert json.loads(path.read_text()) == {PLZ[0]: {"11": "GRUPO 1", "12": "GRUPO 2"}, "999": {"1": "GRUPO 1"}}
    assert not (tmp_path / "fiflp_islas_22_grupos.json.tmp").exists()


def test_sin_ruta_la_descarga_no_escribe_la_lista(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "GROUPS_PATH", None)
    monkeypatch.chdir(tmp_path)
    F.save_group_list("1", [{"value": "1", "text": "GRUPO 1"}])
    assert list(tmp_path.iterdir()) == []


# ── El bot arrastra `activation` entre pasadas ───────────────────────────────

def test_el_bot_conserva_activation_entre_pasadas(tmp_path, monkeypatch):
    report_path = tmp_path / "data-health.json"
    (tmp_path / "index.html").write_text("", encoding="utf-8")
    activation = {"at": "2026-11-14T10:00:00+00:00", "activated": [], "tried": [TORNEO[0]],
                  "failed": [{"competition": TORNEO[0], "name": TORNEO[1], "reason": "sin convenio de código: X"}]}
    report_path.write_text(json.dumps({"version": 1, "season": "2026-2027", "groups": {}, "activation": activation,
                                       "checkedAt": "2026-11-14T10:00:00+00:00"}), encoding="utf-8")
    monkeypatch.setattr(source_health, "REPORT_PATH", report_path)
    monkeypatch.setattr(source_health, "ROOT", tmp_path)
    source_health.begin("2026-2027")
    source_health.finish()
    assert json.loads(report_path.read_text())["activation"] == activation
    source_health.begin("2027-2028")                    # otra temporada: fuera
    source_health.finish()
    assert "activation" not in json.loads(report_path.read_text())


def test_el_grupo_sin_numero_de_la_federacion_conserva_su_nombre():
    import fiflp_manifest as M
    assert [M.group_label(n) for n in ("GRUPO 7", " Eliminatoria  previa ", "", None)] == [
        "Grupo 7", "Eliminatoria previa", "Grupo 1", "Grupo 1"]


# ── Ronda 1: grupos de eliminatoria dentro de una liga (14/11/2026) ──────────
# La federación publicó «Eliminatoria de Primeros y Segundos» y «… de Terceros y Cuartos» como grupos de la
# Fase Previa de benjamín (54976988) y de alevín (54976940): sin número, salían FF1/AL1 («código repetido»).
# Convenio: el prefijo y la fase de las eliminatorias de su categoría (EL, PEL, ALEL; «Eliminatorias»),
# numerados tras los que ya tiene la temporada, por orden de CodGrupo.

def elim(comp, group, name, table=False):
    return dict(entry(comp, 1, table=table, played=False, name=name), group_id=group)


ELIM_FF = [elim(FF, "55331350", "Eliminatoria de Terceros y Cuartos"),
           elim(FF, "55331279", "Eliminatoria  de Primeros y Segundos")]
FF_TAKEN = {f"FF{n}" for n in range(1, 25)}


def test_los_grupos_de_eliminatoria_de_una_liga_son_el_correlativos():
    import fiflp_manifest as M
    groups = M.build(ELIM_FF + [entry(FF, 25)], "2026-2027", "22", taken=FF_TAKEN)
    assert [(g["id"], g["phase"], g["name"], g["fullName"], g["island"]) for g in groups] == [
        ("EL1", "Eliminatorias", "Eliminatoria de Primeros y Segundos",
         "BENJAMIN ELIMINATORIAS - ELIMINATORIA DE PRIMEROS Y SEGUNDOS", "grancanaria"),
        ("EL2", "Eliminatorias", "Eliminatoria de Terceros y Cuartos",
         "BENJAMIN ELIMINATORIAS - ELIMINATORIA DE TERCEROS Y CUARTOS", "grancanaria"),
        ("FF25", "Primera Fase GC", "Grupo 25", "BENJAMIN PRIMERA FASE GC - GRUPO 25", "grancanaria")]
    assert groups[0]["url"] == URL.format(comp=FF[0], grupo="55331279")
    # Con EL1 ya en la temporada, siguen detrás (sin chocar con PEL1 ni ALEL1).
    assert [g["id"] for g in M.build(ELIM_FF, "2026-2027", "22", taken=FF_TAKEN | {"EL1", "PEL4", "ALEL7"})] == ["EL2", "EL3"]


def test_eliminatorias_de_alevin_y_prebenjamin_y_las_de_otra_isla_sin_convenio():
    import fiflp_manifest as M
    alevin = [elim(ALEVIN, "55317330", "Eliminatorias Terceros y Cuartos"),
              elim(ALEVIN, "55317325", "Eliminatoria de Primeros y Segundos")]
    assert [(g["id"], g["cat"], g["phase"]) for g in M.build(alevin, "2026-2027", "22", taken={"AL1"})] == [
        ("ALEL1", "alevin", "Eliminatorias"), ("ALEL2", "alevin", "Eliminatorias")]
    pg = elim(("54977022", "LIGA PREBENJAMIN DE GRAN CANARIA"), "1", "ELIMINATORIA FINAL")
    assert [(g["id"], g["cat"], g["phase"]) for g in M.build([pg], "2026-2027", "22")] == [
        ("PEL1", "prebenjamin", "Eliminatorias")]
    lz = elim(("54976982", "LIGA BENJAMIN DE LANZAROTE FASE 1"), "2", "Eliminatoria de Primeros")
    with pytest.raises(ValueError, match="sin convenio de código: LIGA BENJAMIN DE LANZAROTE FASE 1 / Eliminatoria de Primeros"):
        M.build([lz], "2026-2027", "22")
    # Una copa (la Copa Benjamín, cuyo grupo es «Eliminatoria previa») sigue con su código: ya es una copa.
    assert [g["id"] for g in M.build([elim(COPA, "55331983", "Eliminatoria previa")], "2026-2027", "22")] == ["CGC1"]


def test_una_eliminatoria_sin_tabla_no_recibe_tabla_y_se_verifica_con_sus_partidos():
    import fiflp_manifest as M
    manifest = {"season": "2026-2027", "groups": M.build(ELIM_FF[:1], "2026-2027", "22", taken=FF_TAKEN)}
    evidence = verify_sources(manifest, fiflp_raw=ELIM_FF)
    assert evidence[0]["group"]["id"] == "EL1" and evidence[0]["standings"] == []
    assert sum(len(ms) for ms in evidence[0]["rounds"].values()) == 4


@pytest.mark.skipif(shutil.which("node") is None, reason="la sonda de fases necesita node")
def test_las_eliminatorias_de_la_fase_previa_se_activan_solas(tmp_path):
    raw = [entry(FF, n) for n in range(1, 25)] + ELIM_FF
    pending = {"newGroups": [
        {"competition": FF[0], "competitionName": "BENJAMIN PRIMERA FASE GC", "id": g["group_id"],
         "name": g["group_name"], "firstSeen": "2026-11-14"} for g in ELIM_FF]}
    root = tree(tmp_path, raw, listed={}, health=pending, ff_groups=24)
    conn = sqlite3.connect(root / "futbolbase.db")
    before = [conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in ("groups", "standings", "matches")]
    conn.close()
    logs = []
    assert A.main([], root=root, log=logs.append) == 0               # con la sonda de verdad (node)
    assert codes(root) == [f"FF{n}" for n in range(1, 25)] + ["EL1", "EL2"]
    conn = sqlite3.connect(root / "futbolbase.db")
    after = [conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in ("groups", "standings", "matches")]
    assert [rows[:len(old)] for rows, old in zip(after, before)] == before          # los 24 FF, intactos
    assert conn.execute("SELECT g.code, g.name, g.phase, count(s.id) FROM groups g LEFT JOIN standings s "
                        "ON s.group_id=g.id WHERE g.code LIKE 'EL%' GROUP BY g.id ORDER BY g.code").fetchall() == [
        ("EL1", "Eliminatoria de Primeros y Segundos", "Eliminatorias", 0),
        ("EL2", "Eliminatoria de Terceros y Cuartos", "Eliminatorias", 0)]
    conn.close()
    report = health(root)
    assert "newGroups" not in report and report["activation"]["failed"] == []
    assert report["activation"]["activated"] == [{"competition": FF[0], "name": FF[1], "codes": ["EL1", "EL2"]}]
    assert '"EL1"' in (root / "data-benjamin.js").read_text()
    assert A.run_sonda(root) == []                                    # «0 en otra-…»


def test_activar_dice_sin_convenio_para_una_eliminatoria_de_otra_isla(tmp_path):
    lz = ("54976982", "LIGA BENJAMIN DE LANZAROTE FASE 1")
    raw = [entry(lz, 1), elim(lz, "9001", "Eliminatoria de Primeros")]
    root = tree(tmp_path, raw, health={"newGroups": [{"competition": lz[0], "id": "9001", "name": "Eliminatoria de Primeros"}]})
    dump, _ = fingerprint(root)
    assert run(root)[0] == 1
    assert fingerprint(root)[0] == dump
    assert health(root)["activation"]["failed"] == [{"competition": lz[0], "name": lz[1],
        "reason": "sin convenio de código: LIGA BENJAMIN DE LANZAROTE FASE 1 / Eliminatoria de Primeros"}]
