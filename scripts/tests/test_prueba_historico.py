"""La prueba del histórico sobre una copia (prueba_historico.py, fetch_futbolaspalmas.solo_historico): lo bajado
se importa sin leer ninguna fuente, como lo importará el bot, se mide (tamaño de la base y tiempo) y el veredicto
es todo o nada. Nunca sobre el árbol de verdad ni su futbolbase.db: raíces temporales."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import prueba_historico as P  # noqa: E402


def test_los_limites():
    import base_sana
    assert P.IMPORTACION_MAX_S == 600 and P.MB_MAX == base_sana.AVISO_MB == 80


def test_veredicto():
    assert P.veredicto(41.2, 48.9, 95, True) == {"verde": True, "motivo": "", "mb_antes": 41.2,
                                                 "mb_despues": 48.9, "segundos": 95}
    assert P.veredicto(41.2, 48.9, 95, False)["motivo"] == "las pruebas fallaron"
    assert P.veredicto(41.2, 80.0, 95, True)["motivo"] == "la base pasaría a 80.0 MB (desde 80 hace falta la parte D)"
    assert P.veredicto(41.2, 50.0, 900, True)["motivo"] == \
        "la importación tarda 15 min (más de 10: no cabe en una pasada del bot)"
    assert P.veredicto(41.2, 90.0, 900, False)["motivo"] == "las pruebas fallaron"     # el primero que se cumple
    assert P.veredicto(41.2, 90.0, 900, True)["motivo"].startswith("la base pasaría a 90.0 MB")
    for args in ((41.2, 48.9, 95, False), (41.2, 80.0, 95, True), (41.2, 50.0, 900, True)):
        assert P.veredicto(*args)["verde"] is False, args
    assert P.veredicto(41.2, 79.99, 600, True)["verde"] is True              # los límites, sin pasarlos


@pytest.fixture
def FP(monkeypatch):
    """El módulo de la pasada, con los dos pasos de la liga de escuelas (MyGol) a cero: van protegidos, nunca
    paran nada y tienen sus pruebas (test_mygol_pasada.py); aquí solo estorbarían a las conexiones de mentira.
    La prueba que mira el orden entero de una pasada los vuelve a poner para apuntarlos."""
    import fetch_futbolaspalmas as FP
    monkeypatch.setattr(FP, "importar_mygol", lambda conn, *a, **k: None)
    monkeypatch.setattr(FP, "enlazar_mygol", lambda conn, *a, **k: None)
    return FP


def test_solo_historico_no_lee_ninguna_fuente(FP, monkeypatch):
    import migrate_identidad
    import source_health
    import update_fiflp
    orden = []

    def falla(nombre):
        def f(*a, **k):
            raise AssertionError(f"{nombre}: lee una fuente")
        return f
    monkeypatch.setattr(FP, "process_file", falla("process_file"))
    monkeypatch.setattr(FP, "update_fp_app", falla("update_fp_app"))
    monkeypatch.setattr(update_fiflp, "update_groups", falla("update_fiflp.update_groups"))
    monkeypatch.setattr(source_health, "begin", falla("source_health.begin"))
    monkeypatch.setattr(source_health, "finish", falla("source_health.finish"))
    monkeypatch.setenv("FIFLP_UPDATE", "1")                     # ni con el bot de verdad
    monkeypatch.setattr(FP, "preparar_base", lambda conn: orden.append("preparar_base"))
    monkeypatch.setattr(FP, "import_past_seasons", lambda conn, log=print: orden.append("import_past_seasons"))
    monkeypatch.setattr(migrate_identidad, "resolver_fichas", lambda conn, *a, **k: orden.append("resolver_fichas"))
    FP.solo_historico(object(), log=lambda *a: None, generar=lambda: orden.append("generar"))
    assert orden == ["preparar_base", "import_past_seasons", "resolver_fichas", "generar"]
    # Sin `generar`, el de siempre (generate_js.main).
    import generate_js
    orden.clear()
    monkeypatch.setattr(generate_js, "main", lambda *a, **k: orden.append("generate_js.main"))
    FP.solo_historico(object(), log=lambda *a: None)
    assert orden[-1] == "generate_js.main"


class _Conn:
    def commit(self):
        pass

    def close(self):
        pass


def test_main_prepara_la_base_igual(FP, monkeypatch):
    import generate_js
    import migrate_identidad
    import source_health
    orden = []
    monkeypatch.setattr(FP, "get_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr(FP, "init_db", lambda conn: orden.append("init_db"))
    monkeypatch.setattr(FP, "preparar_base", lambda conn: orden.append("preparar_base"))
    monkeypatch.setattr(FP, "active_season", lambda conn: orden.append("active_season") or (1, "2026-2027"))
    monkeypatch.setattr(FP, "FILES", [])
    monkeypatch.setattr(FP, "update_fp_app", lambda *a, **k: orden.append("update_fp_app"))
    monkeypatch.setattr(FP, "import_past_seasons", lambda conn, log=print: orden.append("import_past_seasons"))
    monkeypatch.setattr(FP, "importar_mygol", lambda conn, *a, **k: orden.append("importar_mygol"))
    monkeypatch.setattr(FP, "enlazar_mygol", lambda conn, *a, **k: orden.append("enlazar_mygol"))
    monkeypatch.setattr(source_health, "begin", lambda *a, **k: orden.append("source_health.begin"))
    monkeypatch.setattr(source_health, "finish", lambda *a, **k: orden.append("source_health.finish"))
    monkeypatch.setattr(migrate_identidad, "resolver_fichas", lambda conn, *a, **k: orden.append("resolver_fichas"))
    monkeypatch.setattr(generate_js, "main", lambda *a, **k: orden.append("generate_js.main"))
    monkeypatch.delenv("FIFLP_UPDATE", raising=False)
    monkeypatch.setattr(sys, "argv", ["fetch_futbolaspalmas.py"])
    FP.main()
    assert orden.index("preparar_base") < orden.index("active_season") < orden.index("source_health.begin")
    assert orden[:2] == ["init_db", "preparar_base"] and "update_fp_app" in orden
    # Con --solo-historico: la base preparada, lo de temporadas pasadas y nada de las fuentes.
    orden.clear()
    monkeypatch.setattr(sys, "argv", ["fetch_futbolaspalmas.py", "--solo-historico"])
    FP.main()
    assert orden == ["init_db", "preparar_base", "import_past_seasons", "importar_mygol", "resolver_fichas",
                     "enlazar_mygol", "generate_js.main"]


def _huella(path):
    return (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha1(path.read_bytes()).hexdigest()) \
        if path.exists() else None


GUION = """import pathlib, sys
# La importación de prueba: 1 MB más en la base de su raíz (cwd), y sale con 0.
assert sys.argv[1:] == ["--solo-historico"], sys.argv
with open("futbolbase.db", "ab") as f:
    f.write(b"x" * 1024 * 1024)
"""


def test_importar_mide_la_copia(tmp_path):
    real = _huella(ROOT / "futbolbase.db")
    raiz = tmp_path / "copia"
    (raiz / "scripts").mkdir(parents=True)
    (raiz / "scripts" / "fetch_futbolaspalmas.py").write_text(GUION, encoding="utf-8")
    (raiz / "futbolbase.db").write_bytes(b"\0" * (3 * 1024 * 1024))
    medida = tmp_path / "medida.json"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "prueba_historico.py"), "importar", "--raiz", str(raiz),
                          "--medida", str(medida)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    m = json.loads(medida.read_text(encoding="utf-8"))
    assert set(m) == {"mb_antes", "mb_despues", "segundos", "codigo"} and m["codigo"] == 0
    assert m["mb_despues"] - m["mb_antes"] == pytest.approx(1.0, abs=0.01) and m["mb_antes"] == pytest.approx(3.0)
    assert 0 <= m["segundos"] < 60
    assert _huella(ROOT / "futbolbase.db") == real                   # la del repositorio, intacta


def test_importar_sale_con_el_codigo_de_la_importacion(tmp_path):
    raiz = tmp_path / "copia"
    (raiz / "scripts").mkdir(parents=True)
    (raiz / "scripts" / "fetch_futbolaspalmas.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    medida = tmp_path / "medida.json"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "prueba_historico.py"), "importar", "--raiz", str(raiz),
                          "--medida", str(medida)], capture_output=True, text=True)
    m = json.loads(medida.read_text(encoding="utf-8"))
    assert out.returncode == 3 and m["codigo"] == 3 and m["mb_antes"] == m["mb_despues"] == 0


@pytest.mark.parametrize("pruebas, verde", [("success", True), ("failure", False), ("skipped", False), ("", False)])
def test_la_cli_del_veredicto(tmp_path, pruebas, verde):
    medida = tmp_path / "medida.json"
    medida.write_text(json.dumps({"mb_antes": 41.2, "mb_despues": 48.9, "segundos": 95, "codigo": 0}), encoding="utf-8")
    salida, gh = tmp_path / "veredicto.json", tmp_path / "github_output"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "prueba_historico.py"), "veredicto", "--medida",
                          str(medida), "--pruebas", pruebas, "--salida", str(salida)],
                         capture_output=True, text=True, env={"GITHUB_OUTPUT": str(gh), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    v = json.loads(salida.read_text(encoding="utf-8"))
    assert v["verde"] is verde and (v["motivo"] == "" if verde else v["motivo"] == "las pruebas fallaron")
    assert gh.read_text(encoding="utf-8").strip() == f"verde={'true' if verde else 'false'}"


def test_una_importacion_que_falla_nunca_es_verde(tmp_path):
    """La importación sale con error (código distinto de 0): aunque las pruebas salieran bien, no se promueve."""
    medida = tmp_path / "medida.json"
    medida.write_text(json.dumps({"mb_antes": 41.2, "mb_despues": 41.2, "segundos": 5, "codigo": 1}), encoding="utf-8")
    salida = tmp_path / "v.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "prueba_historico.py"), "veredicto", "--medida", str(medida),
                    "--pruebas", "success", "--salida", str(salida)], check=True, capture_output=True,
                   env={"PATH": "/usr/bin:/bin"})
    v = json.loads(salida.read_text(encoding="utf-8"))
    assert v["verde"] is False and v["motivo"] == "la importación falló (código 1)"



def test_sin_medida_el_veredicto_es_rojo(tmp_path):
    """La importación se cortó antes de escribir su medida (el plazo del job, un fallo del propio paso): rojo,
    y la orden sale con 0 igual (el carril apunta el motivo)."""
    salida, gh = tmp_path / "v.json", tmp_path / "github_output"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "prueba_historico.py"), "veredicto", "--medida",
                          str(tmp_path / "no-esta.json"), "--pruebas", "success", "--salida", str(salida)],
                         capture_output=True, text=True, env={"GITHUB_OUTPUT": str(gh), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    v = json.loads(salida.read_text(encoding="utf-8"))
    assert v["verde"] is False and v["motivo"] == "no hay medida de la importación"
    assert gh.read_text(encoding="utf-8").strip() == "verde=false"

# ── Un importador que falla en la copia ───────────────────────────────────────

PASOS = (("import_fiflp_actas", "import_changed_raws"), ("import_fiflp_grupos", "import_changed_grupos"),
         ("import_fiflp_grupos", "fix_positions"), ("import_fiflp_goleadores", "import_changed_goleadores"),
         ("import_torneos", "import_changed_torneos"), ("import_wayback_portal", "import_changed_portal"),
         ("import_fiflp_detalle", "import_changed_detalle"), ("import_fiflp_actas", "prune_players"))


@pytest.fixture
def pasadas(FP, monkeypatch):
    """El import_past_seasons de verdad (sus pasos, su orden y su `try`), con cada importador cambiado por uno
    que apunta su nombre, la base preparada sin tocar nada y las fichas y los data-*.js que apuntan."""
    import importlib
    import migrate_actas_schema
    import migrate_identidad
    hechos = []
    monkeypatch.setattr(migrate_actas_schema, "migrate", lambda conn, log=print: None)
    for modulo, nombre in PASOS:
        monkeypatch.setattr(importlib.import_module(modulo), nombre,
                            lambda conn, *a, _n=nombre, **k: hechos.append(_n))
    monkeypatch.setattr(FP, "preparar_base", lambda conn: hechos.append("preparar_base"))
    monkeypatch.setattr(migrate_identidad, "resolver_fichas", lambda conn, *a, **k: hechos.append("resolver_fichas"))
    # También el generate_js de verdad: si solo_historico dejara pasar un fallo, nunca escribiría los data-*.js
    # del árbol.
    import generate_js
    monkeypatch.setattr(generate_js, "main", lambda *a, **k: hechos.append("generate_js.main"))
    return hechos


class _Base:
    def rollback(self):
        pass


def test_un_importador_que_falla_pone_la_prueba_en_rojo(FP, pasadas, monkeypatch):
    """import_past_seasons apunta un paso que falla y sigue (el bot publica lo demás): en la copia, un raw que
    rompe su importador saldría con código 0 y se promovería. solo_historico lo cuenta y falla justo después,
    sin fichas ni data-*.js; el mensaje dice el paso y el tipo de error, nunca el texto (puede llevar un nombre)."""
    import import_fiflp_goleadores

    def roto(conn, *a, **k):
        raise ValueError("JUGADOR INVENTADO, UNO")
    monkeypatch.setattr(import_fiflp_goleadores, "import_changed_goleadores", roto)
    lineas = []
    with pytest.raises(RuntimeError) as error:
        FP.solo_historico(_Base(), log=lineas.append, generar=lambda: pasadas.append("generar"))
    assert "Goleadores de temporadas pasadas" in str(error.value) and "ValueError" in str(error.value)
    assert "INVENTADO" not in str(error.value)
    # Los demás pasos sí se hicieron (como en el bot); las fichas y la web, no.
    assert pasadas == ["preparar_base", "import_changed_raws", "import_changed_grupos", "fix_positions",
                       "import_changed_torneos", "import_changed_portal", "import_changed_detalle", "prune_players"]
    assert any("! ERROR" in linea for linea in lineas)                # el registro, el del bot


def test_sin_fallos_la_copia_acaba_entera(FP, pasadas):
    FP.solo_historico(_Base(), log=lambda *a: None, generar=lambda: pasadas.append("generar"))
    assert pasadas == ["preparar_base"] + [n for _, n in PASOS] + ["resolver_fichas", "generar"]


def test_un_importador_que_falla_en_la_copia_sale_con_error(FP, pasadas, monkeypatch):
    """Por la orden (main --solo-historico): la excepción sale de main, el proceso con código distinto de 0, y la
    orden veredicto da rojo con «la importación falló»."""
    import import_fiflp_detalle

    def roto(conn, *a, **k):
        raise KeyError("x")
    monkeypatch.setattr(import_fiflp_detalle, "import_changed_detalle", roto)
    cerradas = []
    monkeypatch.setattr(FP, "get_connection", lambda *a, **k: type("C", (_Base,), {
        "close": lambda self: cerradas.append(True)})())
    monkeypatch.setattr(FP, "init_db", lambda conn: None)
    monkeypatch.setattr(sys, "argv", ["fetch_futbolaspalmas.py", "--solo-historico"])
    with pytest.raises(RuntimeError, match="Detalle de la federación"):
        FP.main()
    assert cerradas == [True] and "resolver_fichas" not in pasadas and "generate_js.main" not in pasadas


# ── Una pasada normal del bot, igual que antes ────────────────────────────────

@pytest.mark.parametrize("argv", [[], ["-q", "--otra-cosa"]])
def test_una_pasada_normal_hace_lo_mismo_que_antes(FP, monkeypatch, argv):
    """main() sin --solo-historico: cada paso, en el orden de antes de sacar preparar_base (con la base preparada
    de verdad: las migraciones apuntan su nombre). Cualquier otro argumento se ignora, como siempre."""
    import generate_js
    import migrate_categories
    import migrate_compactar
    import migrate_identidad
    import migrate_team_names
    import source_health
    import update_fiflp
    pasos = []
    apunta = lambda nombre: (lambda *a, **k: pasos.append(nombre))           # noqa: E731

    class Conn:
        commit, close = apunta("commit"), apunta("close")

        def rollback(self):
            pasos.append("rollback")
    monkeypatch.setattr(FP, "get_connection", lambda *a, **k: Conn())
    monkeypatch.setattr(FP, "init_db", apunta("init_db"))
    monkeypatch.setattr(migrate_categories, "migrate", apunta("migrate_categories"))
    monkeypatch.setattr(migrate_compactar, "migrate", apunta("migrate_compactar"))
    monkeypatch.setattr(migrate_identidad, "asegurar_esquema", apunta("asegurar_esquema"))
    monkeypatch.setattr(migrate_team_names, "migrate", apunta("migrate_team_names"))
    monkeypatch.setattr(FP, "active_season", lambda conn: pasos.append("active_season") or (7, "2026-2027"))
    monkeypatch.setattr(source_health, "begin", apunta("source_health.begin"))
    monkeypatch.setattr(source_health, "finish", lambda failed=False, **k: pasos.append(f"finish({failed})"))
    monkeypatch.setattr(FP, "FILES", [("a.js", "BENJAMIN", "B"), ("b.js", "PREBENJAMIN", "P")])
    monkeypatch.setattr(FP, "get_or_create_category", lambda conn, var: pasos.append(f"categoria {var}") or 1)
    monkeypatch.setattr(FP, "process_file", lambda conn, js, var, stats, sid, cid: pasos.append(f"process_file {var}"))
    monkeypatch.setenv("FIFLP_UPDATE", "1")
    monkeypatch.setattr(update_fiflp, "update_groups", lambda conn, sid: pasos.append(f"update_groups {sid}"))
    monkeypatch.setattr(FP, "update_fp_app", lambda conn, name: pasos.append(f"update_fp_app {name}"))
    monkeypatch.setattr(FP, "import_past_seasons", lambda conn: pasos.append("import_past_seasons"))
    # La liga de escuelas (MyGol), que entró en main el mismo día: va tras las temporadas pasadas.
    monkeypatch.setattr(FP, "importar_mygol", apunta("importar_mygol"))
    monkeypatch.setattr(FP, "enlazar_mygol", apunta("enlazar_mygol"))
    monkeypatch.setattr(migrate_identidad, "resolver_fichas", apunta("resolver_fichas"))
    monkeypatch.setattr(generate_js, "main", apunta("generate_js.main"))
    monkeypatch.setattr(sys, "argv", ["fetch_futbolaspalmas.py", *argv])
    FP.main()
    assert pasos == ["init_db", "migrate_categories", "migrate_compactar", "asegurar_esquema", "migrate_team_names",
                     "active_season", "source_health.begin", "categoria BENJAMIN", "process_file BENJAMIN",
                     "categoria PREBENJAMIN", "process_file PREBENJAMIN", "commit", "update_groups 7",
                     "update_fp_app 2026-2027", "import_past_seasons", "importar_mygol", "resolver_fichas",
                     "enlazar_mygol", "generate_js.main", "close",
                     "finish(False)"]
    # Un fallo al corregir los nombres de equipo se apunta y no para la pasada (su `try`, tal cual).
    pasos.clear()

    def roto(*a, **k):
        raise RuntimeError("nombres")
    monkeypatch.setattr(migrate_team_names, "migrate", roto)
    FP.main()
    assert pasos[:6] == ["init_db", "migrate_categories", "migrate_compactar", "asegurar_esquema", "rollback",
                         "active_season"] and pasos[-1] == "finish(False)"
