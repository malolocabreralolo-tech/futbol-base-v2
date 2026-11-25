"""Los originales de las actas que lee el bot (scripts/actas_bot.py).

El bot lee cada acta de la temporada en curso, la analiza (fiflp_acta.parse_flat_acta) y la escribe en
la base, y guarda el dict de cada acta que importa (scripts/actas_bot_<temporada>_<categoría>.jsonl,
una línea por acta): sin él, rehacer las apariciones de una temporada pediría volver a leer cada acta
a la federación. Relee, poco a poco y dentro del cupo de la pasada, las de la temporada que ya están
en la base sin original (update_fiflp.releer_originales).

Las pruebas escriben en una carpeta temporal (conftest: ACTAS_BOT_DIR), nunca en scripts/.
"""
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "scripts" / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import actas_bot as A  # noqa: E402
import actas_lotes  # noqa: E402
from db import SCHEMA  # noqa: E402
from fiflp_acta import parse_flat_acta  # noqa: E402
from migrate_actas_schema import migrate  # noqa: E402
import update_fiflp as U  # noqa: E402

SBD = "acta_flat_2627_sanbartolomeD_puertocarmen.html"
LEIDA = "2026-11-14T10:00:00+00:00"


def lineas(path):
    return path.read_text(encoding="utf-8").splitlines()


# ── El fichero de los originales ─────────────────────────────────────────

def test_las_pruebas_no_escriben_en_scripts():
    assert A.carpeta() != Path(A.__file__).resolve().parent
    assert A.ruta("2026-2027", "BENJAMIN").parent == A.carpeta()


def test_ida_y_vuelta_y_formato():
    acta = parse_flat_acta((FIX / SBD).read_text(encoding="utf-8"))
    A.guardar("2026-2027", "BENJAMIN", 280291, acta, LEIDA)
    path = A.ruta("2026-2027", "BENJAMIN")
    assert path.name == "actas_bot_2026-2027_benjamin.jsonl"
    (linea,) = lineas(path)
    d = json.loads(linea)
    assert d == {"cod_acta": 280291, "leida": LEIDA, "acta": acta}
    # Compacto, con las claves ordenadas, y las tildes tal cual.
    assert linea == json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert A.guardadas("2026-2027") == {280291}
    assert A.guardadas("2025-2026") == set()


def test_las_tres_categorias_un_fichero_cada_una_y_guardadas_las_junta():
    for cat, code in (("PREBENJAMIN", 1), ("BENJAMIN", 2), ("ALEVIN", 3), ("alevin", 4)):
        A.guardar("2026-2027", cat, code, {"n": code}, LEIDA)
    assert sorted(p.name for p in A.carpeta().iterdir()) == [
        "actas_bot_2026-2027_alevin.jsonl", "actas_bot_2026-2027_benjamin.jsonl",
        "actas_bot_2026-2027_prebenjamin.jsonl"]
    assert A.guardadas("2026-2027") == {1, 2, 3, 4}


def test_lineas_ordenadas_por_codigo_y_la_releida_sustituye_a_la_suya():
    for code in (30, 10, 20):
        A.guardar("2026-2027", "BENJAMIN", code, {"v": 1}, LEIDA)
    A.guardar("2026-2027", "BENJAMIN", 20, {"v": 2}, "2026-11-15T08:00:00+00:00")
    rows = [json.loads(l) for l in lineas(A.ruta("2026-2027", "BENJAMIN"))]
    assert [r["cod_acta"] for r in rows] == [10, 20, 30]
    assert rows[1] == {"cod_acta": 20, "leida": "2026-11-15T08:00:00+00:00", "acta": {"v": 2}}


@pytest.mark.parametrize("falla", ["fsync", "replace"])
def test_un_fallo_a_mitad_no_deja_el_fichero_roto(monkeypatch, falla):
    A.guardar("2026-2027", "BENJAMIN", 10, {"v": 1}, LEIDA)
    path = A.ruta("2026-2027", "BENJAMIN")
    before = path.read_bytes()

    def roto(*a, **k):
        raise OSError("disco lleno")
    with monkeypatch.context() as m:
        m.setattr(A.os, falla, roto)
        with pytest.raises(OSError):
            A.guardar("2026-2027", "BENJAMIN", 20, {"v": 2}, LEIDA)
    assert path.read_bytes() == before
    assert [p.name for p in A.carpeta().iterdir()] == [path.name]       # ni el temporal


def test_el_nombre_no_es_un_raw_de_actas_de_las_tandas():
    """Trampa 14 del mapa: si casara con actas_lotes.RAW_FILE, import_changed_raws lo reimportaría por
    nombres en cada pasada en que cambie."""
    for cat in ("PREBENJAMIN", "BENJAMIN", "ALEVIN"):
        A.guardar("2026-2027", cat, 1, {}, LEIDA)
        assert not actas_lotes.RAW_FILE.match(A.ruta("2026-2027", cat).name)
    assert actas_lotes.raw_files(str(A.carpeta())) == []


# ── El bot guarda el original de cada acta que importa ───────────────────

def base():
    """La temporada 2026-27 con un grupo por categoría (el de benjamín, el del acta de la fixture)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.executescript("""
      INSERT INTO seasons(id, name, start_year, end_year, is_current) VALUES (1, '2026-2027', 2026, 2027, 1),
        (2, '2025-2026', 2025, 2026, 0);
      INSERT INTO categories(id, name) VALUES (1, 'BENJAMIN'), (2, 'PREBENJAMIN'), (3, 'ALEVIN');
      INSERT INTO groups(id, season_id, category_id, code, island, full_name, url) VALUES
        (1, 1, 1, 'LZ3', 'lanzarote', 'BENJAMIN LANZAROTE FASE 1 - GRUPO 3',
         'https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22&CodCompeticion=54976982&CodGrupo=55141374'),
        (2, 1, 2, 'PG1', 'gran_canaria', 'PREBENJAMIN GRUPO 1',
         'https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22&CodCompeticion=1&CodGrupo=2'),
        (3, 1, 3, 'AL1', 'gran_canaria', 'ALEVIN GRUPO 1',
         'https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=22&CodCompeticion=3&CodGrupo=4'),
        (4, 2, 1, 'OLD', 'lanzarote', 'BENJAMIN DE LA TEMPORADA PASADA',
         'https://www.fiflp.com/pnfg/NPcd/NFG_CmpJornada?cod_primaria=1000120&CodTemporada=21&CodCompeticion=5&CodGrupo=6');
      INSERT INTO teams(id, name) VALUES (1, 'San Bartolomé D'), (2, 'Puerto del Carmen');
      INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score, away_score, fiflp_acta)
        VALUES (1, 1, 'Jornada 1', '2026-10-03', 1, 2, 3, 1, 280291);
    """)
    return conn


class Page:
    """La página de Playwright justo para las actas: sirve la fixture para cualquier CodActa."""
    def __init__(self):
        self.urls = []

    def evaluate(self, js, *a):
        return 0

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return (FIX / SBD).read_text(encoding="utf-8")


class Fed:
    BASE = "https://www.fiflp.com/pnfg/NPcd"

    def __init__(self, page, blocked=False):
        self.page, self.blocked, self.pages = page, blocked, 0

    def goto(self, page, url):
        if self.blocked:
            return False                    # como fiflp_carga: bloqueada, ni se pide
        self.pages += 1
        page.urls.append(url)
        return True

    def delay(self, *a):
        pass


@pytest.fixture
def sin_aplanar(monkeypatch):
    monkeypatch.setattr(U, "flatten", lambda page, selector=None: 0)


def test_un_acta_nueva_queda_guardada_con_su_dict_integro(sin_aplanar):
    conn = base()
    page = Page()
    done, read = U.import_actas(page, Fed(page), conn, 1, 60, log=lambda *_: None)
    assert (done, read) == (1, 1)
    (linea,) = lineas(A.ruta("2026-2027", "BENJAMIN"))
    saved = json.loads(linea)
    assert saved["cod_acta"] == 280291 and saved["leida"].endswith("+00:00")
    assert saved["acta"] == parse_flat_acta((FIX / SBD).read_text(encoding="utf-8"))
    ids = [p.get("fiflp_id") for side in ("home", "away") for p in saved["acta"]["lineups"][side]]
    assert len(ids) == 22 and all(ids)
    assert A.guardadas("2026-2027") == {280291}


def test_un_acta_que_no_se_importa_no_se_guarda(sin_aplanar):
    conn = base()
    conn.execute("UPDATE matches SET home_team_id=2, away_team_id=1")      # al revés: no casa
    page = Page()
    assert U.import_actas(page, Fed(page), conn, 1, 60, log=lambda *_: None) == (0, 1)
    assert A.guardadas("2026-2027") == set()


def test_un_fallo_al_guardar_no_pierde_el_acta_ya_aplicada(sin_aplanar, monkeypatch):
    def roto(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(A, "guardar", roto)
    conn = base()
    page, lines = Page(), []
    assert U.import_actas(page, Fed(page), conn, 1, 60, log=lines.append) == (1, 1)
    assert conn.execute("SELECT cod_acta, home_score, away_score, acta_tries FROM matches").fetchone() == (
        280291, 3, 21, 0)
    assert conn.execute("SELECT count(*) FROM appearances").fetchone()[0] == 22
    assert any("original" in l and "disco lleno" in l for l in lines), lines


# ── La relectura de las ya importadas sin original ───────────────────────

def importadas(conn, specs):
    """Partidos ya importados (cod_acta) de los grupos de base(): (id, grupo, fecha, código)."""
    for mid, gid, day, code in specs:
        conn.execute("""INSERT INTO matches(id, group_id, jornada, date, home_team_id, away_team_id, home_score,
                            away_score, fiflp_acta, cod_acta) VALUES (?, ?, ?, ?, 1, 2, 3, 21, ?, ?)""",
                     (mid, gid, f"J{mid}", day, code, code))
    conn.commit()


def releer(conn, page, F, budget=60, deadline=None, tried=None, groups=(1, 2, 3)):
    return U.releer_originales(page, F, conn, 1, list(groups), budget, deadline, tried=tried, log=lambda *_: None)


def codes(page):
    return [int(u.rsplit("=", 1)[1]) for u in page.urls]


def test_relee_por_categoria_y_la_fecha_mas_reciente_primero(sin_aplanar):
    conn = base()
    importadas(conn, [(10, 3, "2026-10-20", 900), (11, 1, "2026-10-10", 800), (12, 2, "2026-10-01", 700),
                      (13, 1, "2026-10-17", 801), (14, 2, "2026-10-18", 701), (15, 3, "2026-10-04", 901)])
    page = Page()
    assert releer(conn, page, Fed(page)) == (6, 0)
    assert codes(page) == [701, 700, 801, 800, 900, 901]
    assert A.guardadas("2026-2027") == {700, 701, 800, 801, 900, 901}
    # Cada una, en el fichero de su categoría; no se marca nada para releer (trampa 15).
    assert [json.loads(l)["cod_acta"] for l in lineas(A.ruta("2026-2027", "PREBENJAMIN"))] == [700, 701]
    assert conn.execute("SELECT max(acta_recheck), max(acta_tries) FROM matches").fetchone() == (0, 0)


def test_relee_como_mucho_veinte_y_dentro_del_cupo_de_la_pasada(sin_aplanar):
    conn = base()
    importadas(conn, [(100 + i, 1, f"2026-10-{1 + i:02d}", 5000 + i) for i in range(25)])
    page = Page()
    assert U.RELECTURA_POR_PASADA == 20
    assert releer(conn, page, Fed(page)) == (20, 5)
    assert codes(page) == [5024 - i for i in range(20)]
    page = Page()
    assert releer(conn, page, Fed(page), budget=3) == (3, 2)            # lo que queda del cupo
    page = Page()
    assert releer(conn, page, Fed(page), budget=0) == (0, 2) and page.urls == []


def test_ni_las_de_otra_temporada_ni_las_ya_pedidas_ni_las_pendientes_del_camino_normal(sin_aplanar):
    conn = base()
    importadas(conn, [(10, 4, "2025-10-01", 600), (11, 1, "2026-10-10", 800), (12, 1, "2026-10-11", 801),
                      (13, 1, "2026-10-12", 802), (14, 1, "2026-10-13", 803)])
    # La marcada para releer y la de otro código, las relee import_actas (pending_actas).
    conn.execute("UPDATE matches SET acta_recheck=1 WHERE id=12")
    conn.execute("UPDATE matches SET fiflp_acta=999 WHERE id=13")
    page = Page()
    assert releer(conn, page, Fed(page), tried={14}) == (1, 1)      # la ya pedida queda para otra pasada
    assert codes(page) == [800]


def test_respeta_el_plazo_y_el_bloqueo(sin_aplanar, monkeypatch):
    conn = base()
    importadas(conn, [(10, 1, "2026-10-10", 800), (11, 1, "2026-10-11", 801)])
    page = Page()
    monkeypatch.setattr(U, "clock", lambda: 100.0)
    assert releer(conn, page, Fed(page), deadline=50.0) == (0, 2) and page.urls == []
    F = Fed(page, blocked=True)
    assert releer(conn, page, F, deadline=500.0) == (0, 2) and page.urls == [] and F.pages == 0
    F = Fed(page)
    monkeypatch.setattr(U, "clock", lambda: 999.0 if F.pages else 0.0)      # el plazo, tras la 1.ª
    assert releer(conn, page, F, deadline=500.0) == (1, 1) and codes(page) == [801]


def test_con_todo_guardado_no_pide_ninguna_pagina(sin_aplanar):
    conn = base()
    importadas(conn, [(10, 1, "2026-10-10", 800)])
    A.guardar("2026-2027", "BENJAMIN", 800, {}, LEIDA)
    A.guardar("2026-2027", "BENJAMIN", 280291, {}, LEIDA)
    page = Page()
    assert releer(conn, page, Fed(page)) is None and page.urls == []


def test_un_acta_releida_que_ya_no_casa_gasta_un_intento_y_no_se_guarda(sin_aplanar):
    conn = base()
    importadas(conn, [(10, 1, "2026-10-10", 800)])
    conn.execute("UPDATE matches SET home_team_id=2, away_team_id=1 WHERE id=10")
    page = Page()
    assert releer(conn, page, Fed(page)) == (1, 1)
    assert A.guardadas("2026-2027") == set()
    assert conn.execute("SELECT acta_tries, cod_acta FROM matches WHERE id=10").fetchone() == (1, 800)
    conn.execute(f"UPDATE matches SET acta_tries={U.MAX_ACTA_TRIES} WHERE id=10")
    page = Page()
    assert releer(conn, page, Fed(page)) is None and page.urls == []     # agotada: se deja


# ── En la pasada: al final, sin contar como grupo ────────────────────────

def test_la_pasada_relee_al_final_y_su_veredicto_no_cambia(sin_aplanar, monkeypatch, capsys):
    notes, recorded = [], []
    monkeypatch.setattr(U.source_health, "note_run", lambda info, carril="principal": notes.append(info))
    monkeypatch.setattr(U.source_health, "record", lambda *a, **k: recorded.append(a[:3]))
    monkeypatch.setattr(U.source_health, "carry", lambda *a, **k: None)
    conn = base()
    importadas(conn, [(10, 1, "2026-09-26", 280290)])                   # importada sin original
    for tid, pos in ((1, 1), (2, 2)):
        conn.execute("""INSERT INTO standings(group_id, team_id, position, points, played, won, drawn, lost, gf,
                            gc, gd) VALUES (1, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0)""", (tid, pos))
    conn.commit()

    class Pagina(Page):
        url = ""

        def evaluate(self, js, *a):
            return [{"value": "1", "text": "1 - 03-10-2026"}] if "select[name=" in js else 0

        def content(self):
            if "NFG_CmpPartido" in self.url:
                return super().content()
            return "<html></html>"

    class Federacion(Fed):
        def goto(self, page, url):
            page.url = url
            return super().goto(page, url)

        def parse_standings(self, page):
            return []

        def parse_matches(self, page):
            return [{"home": "SAN BARTOLOME, C.F D", "away": 'PUERTO DEL CARMEN, F.C. "A"', "hs": 3, "as": 1,
                     "date": "03-10-2026", "time": "09:00", "venue": "", "fiflp_acta": 280291}]

    page = Pagina()
    groups = [g for g in U.fiflp_groups(conn, 1) if g[1] == "LZ3"]
    run = U.run_passes(page, Federacion(page), conn, 1, groups, date(2026, 10, 5), {g[1]: g[2] for g in groups},
                       number=1116)
    assert run == {"estados": {"LZ3": "ok"}, "previstos": 1, "vacias": []}
    assert [code for code, *_ in recorded] == ["LZ3"]
    actas = [int(u.rsplit("=", 1)[1]) for u in page.urls if "NFG_CmpPartido" in u]
    assert actas == [280291, 280290]                    # la del camino normal y, al final, la relectura
    assert A.guardadas("2026-2027") == {280290, 280291}
    (note,) = notes
    assert note["rawBackfill"] == {"read": 1, "left": 0}
    assert "Originales de las actas: 1 releídas, quedan 0" in capsys.readouterr().out


def test_la_pasada_sin_nada_que_releer_no_lo_apunta(sin_aplanar, monkeypatch):
    notes = []
    monkeypatch.setattr(U.source_health, "note_run", lambda info, carril="principal": notes.append(info))
    monkeypatch.setattr(U.source_health, "carry", lambda *a, **k: None)
    conn = base()
    page = Page()
    run = U.run_passes(page, Fed(page), conn, 1, [], date(2026, 10, 5), {}, number=1116)
    assert run == {"estados": {}, "previstos": 0, "vacias": []}
    assert "rawBackfill" not in notes[0] and not [u for u in page.urls if "NFG_CmpPartido" in u]
