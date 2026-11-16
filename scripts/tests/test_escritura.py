"""escritura.escribir_atomico: un fichero que el bot escribe acaba entero o no acaba (un corte a mitad no deja
un original, un data-*.js o el sw.js truncados), y ningún módulo que escribe esos ficheros lo hace a pelo."""
import ast
import os
import stat
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import escritura  # noqa: E402
from escritura import escribir_atomico  # noqa: E402


def _temporales(carpeta):
    return sorted(p.name for p in Path(carpeta).iterdir() if p.name.endswith(".tmp"))


def test_escribe_texto_y_bytes(tmp_path):
    texto, crudo = tmp_path / "a.json", tmp_path / "b.bin"
    escribir_atomico(texto, "año\nñ\n")
    escribir_atomico(str(crudo), b"\x00\xff")
    assert texto.read_bytes() == "año\nñ\n".encode("utf-8")
    assert crudo.read_bytes() == b"\x00\xff"
    escribir_atomico(texto, "otra")
    assert texto.read_text(encoding="utf-8") == "otra"
    assert _temporales(tmp_path) == []


def test_respeta_la_codificacion(tmp_path):
    path = tmp_path / "a.txt"
    escribir_atomico(path, "ñ", encoding="latin-1")
    assert path.read_bytes() == b"\xf1"


def test_permisos_644_en_fichero_nuevo(tmp_path):
    path = tmp_path / "nuevo.js"
    escribir_atomico(path, "x")
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_conserva_permisos_del_que_sustituye(tmp_path):
    path = tmp_path / "viejo.sh"
    path.write_text("antes", encoding="utf-8")
    path.chmod(0o755)
    escribir_atomico(path, "después")
    assert stat.S_IMODE(path.stat().st_mode) == 0o755
    assert path.read_text(encoding="utf-8") == "después"


def test_un_fallo_deja_el_anterior_entero(tmp_path, monkeypatch):
    path = tmp_path / "fiflp_actas_raw.json"
    path.write_text('{"entero": true}', encoding="utf-8")

    def falla(*args, **kwargs):
        raise OSError("corte simulado")

    monkeypatch.setattr(escritura.os, "replace", falla)
    with pytest.raises(OSError):
        escribir_atomico(path, '{"a medias"')
    assert path.read_text(encoding="utf-8") == '{"entero": true}'
    assert _temporales(tmp_path) == []


def test_fallo_al_escribir_no_deja_temporal(tmp_path):
    path = tmp_path / "data-x.js"
    path.write_text("antes", encoding="utf-8")
    with pytest.raises(TypeError):
        escribir_atomico(path, {"no": "es texto"})
    assert path.read_text(encoding="utf-8") == "antes"
    assert _temporales(tmp_path) == []


def test_el_temporal_va_en_la_misma_carpeta_con_su_nombre(tmp_path, monkeypatch):
    path = tmp_path / "sw.js"
    vistos = []
    real = os.replace

    def mira(origen, destino):
        vistos.append((Path(origen), Path(destino)))
        real(origen, destino)

    monkeypatch.setattr(escritura.os, "replace", mira)
    escribir_atomico(path, "x")
    (origen, destino), = vistos
    assert origen.parent == tmp_path and destino == path
    assert origen.name.startswith("sw.js.") and origen.name.endswith(".tmp")


# Los módulos que escriben originales, estado o lo publicado (el apartado 3 del mapa de la fase 4).
MODULOS = ["fetch_fiflp_actas.py", "fetch_fiflp_goleadores.py", "fetch_fiflp_detalle.py", "fetch_fp_app.py",
           "discover_fiflp_comps.py", "import_fiflp_actas.py", "fetch_fiflp_islas.py", "source_health.py",
           "activar_auto.py", "generate_js.py", "precache.py", "codigo.py"]

# (fichero, función) que sí escriben a pelo, y por qué. Lo más corta posible.
PERMITIDAS = {}


def _modo_de_open(call):
    f = call.func
    modulo = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
    if modulo == "os":
        return "?"  # os.open(path, flags): banderas, no un modo
    # open(path, modo) e io.open(path, modo); Path(...).open(modo)
    pos = 1 if isinstance(f, ast.Name) or modulo in ("io", "builtins", "codecs") else 0
    if len(call.args) > pos:
        modo = call.args[pos]
    else:
        modo = next((k.value for k in call.keywords if k.arg == "mode"), None)
    if modo is None:
        return "r"
    if isinstance(modo, ast.Constant) and isinstance(modo.value, str):
        return modo.value
    return "?"  # un modo calculado: se cuenta como escritura


def _escrituras_a_pelo(fuente):
    """[(función, línea, qué)] de las llamadas a open() con modo de escritura, .write_text() y .write_bytes()."""
    arbol = ast.parse(fuente)
    found = []

    def visita(nodo, funcion):
        for hijo in ast.iter_child_nodes(nodo):
            dentro = hijo.name if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)) else funcion
            if isinstance(hijo, ast.Call):
                f = hijo.func
                if isinstance(f, ast.Name) and f.id == "open" or isinstance(f, ast.Attribute) and f.attr == "open":
                    modo = _modo_de_open(hijo)
                    if modo == "?" or set(modo) & set("wax+"):
                        found.append((funcion, hijo.lineno, f"open(…, {modo!r})"))
                elif isinstance(f, ast.Attribute) and f.attr in ("write_text", "write_bytes"):
                    found.append((funcion, hijo.lineno, f".{f.attr}()"))
            visita(hijo, dentro)

    visita(arbol, "<módulo>")
    return found


def test_el_detector_ve_las_formas_de_escribir():
    fuente = ("def a(p):\n    open(p, 'w')\n    open(p, mode='ab')\n    open(p)\n    open(p, 'rb')\n"
              "def b(p, m):\n    p.write_text('x')\n    p.write_bytes(b'x')\n    os.open(p, m)\n"
              "    p.open('w')\n    p.open()\n    io.open(p, 'r+')\n    open(p, m)\n")
    assert [(f, l) for f, l, _ in _escrituras_a_pelo(fuente)] == [
        ("a", 2), ("a", 3), ("b", 7), ("b", 8), ("b", 9), ("b", 10), ("b", 12), ("b", 13)]


def test_nadie_escribe_a_pelo():
    quedan = []
    for nombre in MODULOS:
        for funcion, linea, que in _escrituras_a_pelo((SCRIPTS / nombre).read_text(encoding="utf-8")):
            if (nombre, funcion) not in PERMITIDAS:
                quedan.append(f"{nombre}:{linea} ({funcion}): {que}")
    assert not quedan, "escrituras sin escribir_atomico:\n" + "\n".join(quedan)


def test_las_permitidas_existen():
    """Una entrada de PERMITIDAS que ya no casa con ninguna escritura sobra."""
    vivas = {(nombre, funcion) for nombre in MODULOS
             for funcion, _, _ in _escrituras_a_pelo((SCRIPTS / nombre).read_text(encoding="utf-8"))}
    assert set(PERMITIDAS) <= vivas
