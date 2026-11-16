#!/usr/bin/env python3
"""Que desde un commit solo hayan cambiado comentarios en el código de la web y del bot.

Para cada fichero del alcance (src/*.js, sw.js, index.html, scripts/*.py, scripts/*.mjs) que cambia entre
<commit base> y el árbol de trabajo, compara las dos versiones sin sus comentarios:

- Python: los tokens sin comentarios, saltos de línea vacíos ni docstrings, y el `ast.dump` de los dos
  árboles sin docstrings. Las docstrings pueden cambiar; cualquier otra cadena, no.
- JavaScript: la salida de esbuild con `minifyWhitespace` (quita comentarios y espacios, sin renombrar ni
  reordenar). En sw.js, el bloque del precache se deja fuera: lo escribe scripts/precache.py con las huellas
  de los ficheros (cambia cuando cambia un comentario de index.html) y lo comprueba `precache.py --check`.
- index.html: sin comentarios HTML ni espacios de principio y fin de línea, y el JS de cada <script> en
  línea pasado por el mismo esbuild.

Con --pruebas mira en su lugar las pruebas (scripts/tests/*.py, scripts/tests/*.mjs y los ayudantes .mjs de
fixtures/rediseno y fixtures/config-2026-2027) con las mismas comparaciones. Los nombres de las pruebas y los
textos de test('…') son código, así que un cambio en ellos sale en rojo. fixtures/app-anterior es una copia
congelada de la web anterior y no entra, y la propia guardia tampoco (es lo que se amplía).

No es una prueba de pytest: se lanza a mano antes de un commit que solo toca comentarios.

Uso, desde la raíz del repositorio:
  python3 scripts/tests/solo_comentarios.py [--pruebas] <commit base>
Sale con 0 y la lista de ficheros comprobados; con 1, el fichero y la primera diferencia; con 2 si falta
esbuild o el commit no existe.
"""
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
ESBUILD = ROOT / "scripts" / "empaquetar" / "node_modules" / "esbuild"
ALCANCE = ["src/*.js", "sw.js", "index.html", "scripts/*.py", "scripts/*.mjs"]
ALCANCE_PRUEBAS = ["scripts/tests/*.py", "scripts/tests/*.mjs", "scripts/tests/fixtures/rediseno/*.mjs",
                   "scripts/tests/fixtures/config-2026-2027/*.mjs"]
PRECACHE_INICIO = "// >>> precache: lo escribe scripts/precache.py"
PRECACHE_FIN = "// <<< precache"

# Lee de la entrada estándar una lista JSON de fuentes y devuelve otra con cada una sin comentarios ni
# espacios; un elemento {"error": …} si esbuild no la entiende.
NODE_SIN_COMENTARIOS = r"""
import { createRequire } from 'node:module';
const require = createRequire(process.argv[1] + '/');
const esbuild = require(process.argv[1]);
let input = '';
for await (const chunk of process.stdin) input += chunk;
const out = [];
for (const code of JSON.parse(input)) {
  try {
    out.push(esbuild.transformSync(code, {
      loader: 'js', minifyWhitespace: true, legalComments: 'inline', charset: 'utf8', logLevel: 'silent',
    }).code);
  } catch (error) {
    out.push({ error: String(error.message || error) });
  }
}
process.stdout.write(JSON.stringify(out));
"""


class Diferencia(Exception):
    pass


def en_alcance(rel, alcance=ALCANCE):
    if alcance is ALCANCE_PRUEBAS and rel == "scripts/tests/solo_comentarios.py":
        return False
    path = PurePosixPath(rel)
    return any(path.match(pattern) and len(path.parts) == len(PurePosixPath(pattern).parts) for pattern in alcance)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


# --- Python -------------------------------------------------------------------------------------------

def _docstrings(tree):
    """Los nodos Expr que son docstring de módulo, clase o función."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.append(body[0])
    return found


def _sin_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:]
    return ast.dump(tree)


def _tokens(text):
    """(tipo, texto, línea) de cada token que cuenta: sin comentarios, NL, NEWLINE repetidos ni docstrings."""
    tree = ast.parse(text)
    tramos = [((d.lineno, d.col_offset), (d.end_lineno, d.end_col_offset)) for d in _docstrings(tree)]

    def es_docstring(tok):
        return any(start <= tok.start and tok.end <= end for start, end in tramos)

    out = []
    saltar_newline = False
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL):
            continue
        if tok.type == tokenize.STRING and es_docstring(tok):
            saltar_newline = True
            continue
        if tok.type == tokenize.NEWLINE:
            if saltar_newline or (out and out[-1][0] == tokenize.NEWLINE):
                saltar_newline = False
                continue
        saltar_newline = False
        out.append((tok.type, tok.string, tok.start[0]))
    return out


def comparar_python(rel, antes, ahora):
    try:
        t_antes, t_ahora = _tokens(antes), _tokens(ahora)
    except (SyntaxError, tokenize.TokenError) as error:
        raise Diferencia(f"no se puede leer como Python: {error}")
    for a, b in zip(t_antes, t_ahora):
        if a[:2] != b[:2]:
            raise Diferencia(f"token distinto: línea {a[2]} de la base {a[1]!r}, línea {b[2]} del árbol {b[1]!r}")
    if len(t_antes) != len(t_ahora):
        raise Diferencia(f"la base tiene {len(t_antes)} tokens y el árbol {len(t_ahora)}")
    if _sin_docstrings(ast.parse(antes)) != _sin_docstrings(ast.parse(ahora)):
        raise Diferencia("el árbol sintáctico sin docstrings es distinto")


# --- JavaScript ---------------------------------------------------------------------------------------

def sin_comentarios_js(fuentes):
    """Cada fuente, pasada por esbuild con minifyWhitespace."""
    done = subprocess.run(["node", "--input-type=module", "-e", NODE_SIN_COMENTARIOS, str(ESBUILD)],
                          input=json.dumps(fuentes), capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"esbuild falló: {done.stderr.strip()}")
    return json.loads(done.stdout)


def _sin_precache(rel, text):
    if rel != "sw.js":
        return text
    if text.count(PRECACHE_INICIO) != 1 or text.count(PRECACHE_FIN) != 1:
        raise Diferencia("sw.js tiene que llevar una vez cada marca del bloque del precache")
    start = text.index(PRECACHE_INICIO)
    end = text.index(PRECACHE_FIN, start) + len(PRECACHE_FIN)
    return text[:start] + "/*precache*/" + text[end:]


def _primera_diferencia(a, b):
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"en el carácter {i} del código sin comentarios: base …{a[max(0, i - 60):i + 60]!r}… árbol …{b[max(0, i - 60):i + 60]!r}…"


def comparar_js(rel, antes, ahora):
    antes, ahora = _sin_precache(rel, antes), _sin_precache(rel, ahora)
    a, b = sin_comentarios_js([antes, ahora])
    for version, out in (("base", a), ("árbol", b)):
        if isinstance(out, dict):
            raise Diferencia(f"esbuild no entiende la versión del {version}: {out['error']}")
    if a != b:
        raise Diferencia(_primera_diferencia(a, b))


# --- index.html ---------------------------------------------------------------------------------------

SCRIPT_RE = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
COMENTARIO_HTML_RE = re.compile(r"<!--.*?-->", re.S)


def _html_normalizado(text):
    """(marcado sin comentarios ni espacios de borde de línea, con los scripts como marcas; scripts)."""
    scripts = []

    def guardar(match):
        scripts.append(match.group(2))
        return f"{match.group(1)}\0{len(scripts) - 1}\0{match.group(3)}"

    marcado = SCRIPT_RE.sub(guardar, text)
    marcado = COMENTARIO_HTML_RE.sub("", marcado)
    lineas = [line.strip() for line in marcado.splitlines()]
    return "\n".join(line for line in lineas if line), scripts


def comparar_html(rel, antes, ahora):
    m_antes, s_antes = _html_normalizado(antes)
    m_ahora, s_ahora = _html_normalizado(ahora)
    if m_antes != m_ahora:
        raise Diferencia("el marcado fuera de los <script>, sin comentarios: " + _primera_diferencia(m_antes, m_ahora))
    salida = sin_comentarios_js(s_antes + s_ahora)
    a, b = salida[:len(s_antes)], salida[len(s_antes):]
    for n, (x, y) in enumerate(zip(a, b)):
        if isinstance(x, dict) or isinstance(y, dict):
            raise Diferencia(f"esbuild no entiende el <script> {n + 1}: {(x if isinstance(x, dict) else y)['error']}")
        if x != y:
            raise Diferencia(f"<script> {n + 1}: " + _primera_diferencia(x, y))


# ------------------------------------------------------------------------------------------------------

def comparar(rel, antes, ahora):
    if rel.endswith(".py"):
        comparar_python(rel, antes, ahora)
    elif rel.endswith((".js", ".mjs")):
        comparar_js(rel, antes, ahora)
    elif rel.endswith(".html"):
        comparar_html(rel, antes, ahora)
    else:
        raise Diferencia("no sé comparar este tipo de fichero")


def main(argv):
    pruebas = "--pruebas" in argv
    argv = [arg for arg in argv if arg != "--pruebas"]
    if len(argv) != 1:
        print(__doc__.strip().split("\n\n")[-1])
        return 2
    base = argv[0]
    alcance = ALCANCE_PRUEBAS if pruebas else ALCANCE
    try:
        git("rev-parse", "--verify", f"{base}^{{commit}}")
    except subprocess.CalledProcessError:
        print(f"{base} no es un commit de este repositorio")
        return 2
    cambiados = [rel for rel in git("diff", "--name-only", base, "--").split("\n") if rel and en_alcance(rel, alcance)]
    if not ESBUILD.exists() and any(rel.endswith((".js", ".mjs", ".html")) for rel in cambiados):
        print(f"falta esbuild ({ESBUILD}): npm ci --prefix scripts/empaquetar")
        return 2
    for rel in cambiados:
        path = ROOT / rel
        if not path.is_file():
            print(f"{rel}: ya no está en el árbol")
            return 1
        try:
            antes = git("show", f"{base}:{rel}")
        except subprocess.CalledProcessError:
            print(f"{rel}: no estaba en {base}")
            return 1
        try:
            comparar(rel, antes, path.read_text(encoding="utf-8"))
        except Diferencia as error:
            print(f"{rel}: no solo cambian comentarios: {error}")
            return 1
        except RuntimeError as error:
            print(f"{rel}: {error}")
            return 2
    print(f"{len(cambiados)} ficheros cambiados desde {base}, solo en comentarios:")
    for rel in cambiados:
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
