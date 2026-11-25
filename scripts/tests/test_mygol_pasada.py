"""La pasada del bot importa la liga de escuelas de MyGol (fetch_futbolaspalmas.importar_mygol), y un fallo de
MyGol nunca la para."""
import inspect
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_futbolaspalmas as F  # noqa: E402
import import_mygol  # noqa: E402


def test_un_fallo_no_para_la_pasada(monkeypatch):
    def revienta(conn, raiz=None, registro=print):
        conn.execute("INSERT INTO a_medias VALUES (1)")
        raise RuntimeError("MyGol se ha roto")

    monkeypatch.setattr(import_mygol, "importar_si_cambia", revienta)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE a_medias (x INTEGER)")
    conn.commit()
    lineas = []
    F.importar_mygol(conn, registro=lineas.append)          # no propaga
    assert any(linea.startswith("  ! MyGol: ") and "MyGol se ha roto" in linea for linea in lineas), lineas
    assert conn.execute("SELECT count(*) FROM a_medias").fetchone() == (0,)      # rollback de lo de a medias


def test_la_pasada_importa_lo_que_cambia(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(import_mygol, "importar_si_cambia",
                        lambda conn, raiz=None, registro=print: llamadas.append(raiz) or True)
    F.importar_mygol(sqlite3.connect(":memory:"), registro=lambda *a: None)
    assert llamadas == [None]                        # los originales de scripts/, los de verdad


def test_main_la_llama_despues_de_las_temporadas_pasadas():
    fuente = inspect.getsource(F.main)
    assert "importar_mygol(conn)" in fuente
    assert fuente.index("import_past_seasons(conn)") < fuente.index("importar_mygol(conn)") \
        < fuente.index("resolver_fichas(conn)")


# ------------------------------------------------------------------ los enlaces con las fichas (enlace_mygol)

def test_un_fallo_del_enlace_no_para_la_pasada(monkeypatch):
    import enlace_mygol

    def revienta(conn, registro=print):
        conn.execute("INSERT INTO a_medias VALUES (1)")
        raise RuntimeError("el enlace se ha roto")

    monkeypatch.setattr(enlace_mygol, "guardar_enlaces", revienta)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE a_medias (x INTEGER)")
    conn.commit()
    lineas = []
    F.enlazar_mygol(conn, registro=lineas.append)           # no propaga
    assert any(linea == "  ! MyGol (enlaces): RuntimeError: el enlace se ha roto" for linea in lineas), lineas
    assert conn.execute("SELECT count(*) FROM a_medias").fetchone() == (0,)      # rollback de lo de a medias


def test_la_pasada_guarda_los_enlaces(monkeypatch):
    import enlace_mygol
    llamadas = []
    monkeypatch.setattr(enlace_mygol, "guardar_enlaces",
                        lambda conn, registro=print: llamadas.append(conn) or 0)
    conn = sqlite3.connect(":memory:")
    F.enlazar_mygol(conn, registro=lambda *a: None)
    assert llamadas == [conn]


def test_el_orden_de_la_pasada():
    """Los enlaces, con las fichas ya resueltas (siguen a su principal) y antes de generar (que los publica)."""
    fuente = inspect.getsource(F.main)
    assert "enlazar_mygol(conn)" in fuente
    assert fuente.index("importar_mygol(conn)") < fuente.index("resolver_fichas(conn)") \
        < fuente.index("enlazar_mygol(conn)") < fuente.index("generate_main()")
