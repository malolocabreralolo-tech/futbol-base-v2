"""Lo que está en scripts/_archive/ no lo usa nadie: ningún código vivo lo importa ni ningún workflow lo ejecuta.
Si algo lo necesitara, tiene que volver a scripts/ (y esta prueba avisa antes de que falle en producción)."""
import ast
import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
ARCHIVO = SCRIPTS / "_archive"
WORKFLOWS = RAIZ / ".github" / "workflows"

# (fichero vivo, módulo archivado) -> por qué se admite. Solo lo que se carga a propósito desde _archive/.
ADMITIDAS = {
    ("scripts/tests/test_fed_names.py", "fix_nombres_federacion"):
        "comprueba un arreglo ya aplicado y carga a propósito el guion desde _archive/ por sys.path",
}


def _solo_archivados():
    vivos = {p.stem for p in SCRIPTS.glob("*.py")}
    return sorted(p.stem for p in ARCHIVO.glob("*.py") if p.stem not in vivos)


def _fuentes_vivas():
    """Todos los .py de scripts/ salvo el archivo (y dependencias descargadas)."""
    for p in sorted(SCRIPTS.rglob("*.py")):
        rel = p.relative_to(SCRIPTS).parts
        if rel[0] in ("_archive", "node_modules", "__pycache__") or "node_modules" in rel:
            continue
        yield p


def _importados(arbol):
    """Nombres de módulo que importa el árbol: `import x.y`, `from x.y import z`, `from scripts import z`
    y `from . import z`; de cada uno, el nombre completo y cada tramo."""
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                nombres.update(a.name.split("."))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                nombres.update(nodo.module.split("."))
            if nodo.module in (None, "scripts"):
                nombres.update(a.name for a in nodo.names)
    return nombres


def test_la_prueba_ve_lo_que_busca():
    """La prueba de abajo no puede pasar por no encontrar nada: hay archivados y se ven los cuatro tipos de uso."""
    assert len(_solo_archivados()) >= 20
    arbol = ast.parse("import a.b\nfrom c.d import e\nfrom scripts import f\nfrom . import g\n")
    assert {"a", "b", "c", "d", "f", "g"} <= _importados(arbol)


def test_nada_vivo_importa_del_archivo():
    archivados = _solo_archivados()
    assert archivados, "scripts/_archive/ no tiene módulos propios: ¿se ha movido la carpeta?"

    fallos = []
    for p in _fuentes_vivas():
        texto = p.read_text(encoding="utf-8")
        importados = _importados(ast.parse(texto, filename=str(p)))
        dinamico = "import_module" in texto or "__import__" in texto
        for nombre in archivados:
            if p == Path(__file__).resolve() or p.stem == nombre or (str(p.relative_to(RAIZ)), nombre) in ADMITIDAS:
                continue
            if nombre in importados:
                fallos.append(f"{p.relative_to(RAIZ)} importa {nombre}")
            elif dinamico and re.search(rf"""["'](?:scripts\.)?{re.escape(nombre)}["']""", texto):
                fallos.append(f"{p.relative_to(RAIZ)} importa {nombre} por nombre")

    for wf in sorted(WORKFLOWS.glob("*.yml")):
        trabajos = yaml.safe_load(wf.read_text(encoding="utf-8")).get("jobs") or {}
        for job, definicion in trabajos.items():
            for paso in definicion.get("steps") or []:
                orden = paso.get("run") or ""
                for nombre in archivados:
                    if re.search(rf"scripts/{re.escape(nombre)}\.py", orden):
                        fallos.append(f"{wf.name} ({job}) ejecuta scripts/{nombre}.py")

    assert not fallos, "\n".join(fallos)


def test_las_admitidas_siguen_siendo_ciertas():
    """Una entrada de ADMITIDAS cuyo fichero ya no existe o ya no importa el módulo sobra: se quita."""
    for (fichero, nombre), motivo in ADMITIDAS.items():
        assert motivo
        p = RAIZ / fichero
        assert p.exists(), f"{fichero} ya no existe"
        assert (ARCHIVO / f"{nombre}.py").exists(), f"{nombre} ya no está en _archive/"
        assert nombre in _importados(ast.parse(p.read_text(encoding="utf-8"))), f"{fichero} ya no importa {nombre}"


def test_fetch_fiflp_2324_se_queda_mientras_las_actas_lo_nombren():
    """fetch_fiflp_actas.py lo carga con __import__ en KNOWN_COMPS: sin el fichero, el bot no arranca."""
    if "fetch_fiflp_2324" in (SCRIPTS / "fetch_fiflp_actas.py").read_text(encoding="utf-8"):
        assert (SCRIPTS / "fetch_fiflp_2324.py").exists()
