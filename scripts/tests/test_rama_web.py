"""La rama web (scripts/rama_web.py): qué entra, que su árbol lleva todo lo que la web puede pedir, y que se sube
sin forzar y sin retroceder nunca. Repositorios de mentira con su remoto desnudo, en tmp_path; del repositorio de
verdad solo se lee (git ls-tree, cat-file y write-tree, que escribe un árbol en .git y nada más)."""
import hashlib
import http.server
import json
import re
import subprocess
import sys
import threading
from fnmatch import fnmatch
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import precache  # noqa: E402
import rama_web  # noqa: E402
from rama_web import RamaWebError, es_web  # noqa: E402


@pytest.mark.parametrize("ruta,web", [
    ("index.html", True), ("sw.js", True), (".nojekyll", True), ("data-health.json", True),
    ("data-lineups-2025-2026-FF1.js", True), ("dist/app-64f418c9.js", True), ("src/config.js", True),
    ("escudos/s/x.png", True), ("acta.css", True), ("data-history-2024.json", False),
    ("futbolbase.db", False), ("base/comun.db", False), ("scripts/generate_js.py", False),
    ("docs/decisiones.md", False), (".github/workflows/update.yml", False), ("README.md", False),
    ("pc/copia/README.md", False), ("sub/data-x.js", False)])
def test_es_web(ruta, web):
    assert es_web(ruta) is web


def test_lo_del_sitio_es_lo_de_copia_web():
    """Los smokes de navegador sirven DEL_SITIO (scripts/tests/copia-web.mjs) más sus datos: es lo de la rama web
    sin data-health.json ni .nojekyll (los datos los pone cada smoke). Si una lista cambia, la otra también."""
    texto = (ROOT / "scripts" / "tests" / "copia-web.mjs").read_text(encoding="utf-8")
    lista = re.search(r"export const DEL_SITIO = \[([^\]]*)\];", texto).group(1)
    del_sitio = re.findall(r"'([^']+)'", lista)
    esperada = [f for f in rama_web.WEB_FICHEROS if f not in ("data-health.json", ".nojekyll")]
    esperada += [c.rstrip("/") for c in rama_web.WEB_CARPETAS]
    assert del_sitio == esperada
    assert "rama_web.py" in texto, "el comentario de copia-web.mjs dice de dónde sale la lista"


def _es_repo():
    return subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, capture_output=True).returncode == 0


def _rutas(objeto, repo=ROOT):
    salida = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", objeto], cwd=repo, capture_output=True,
                            text=True, check=True).stdout
    return [r for r in salida.split("\0") if r]


@pytest.mark.skipif(not _es_repo(), reason="sin git (una copia del árbol)")
def test_arbol_web_del_repositorio():
    """El árbol de la web de HEAD lleva todo lo que necesita la web, nada que no sea de ella, y cabe en Pages."""
    arbol, total = rama_web.arbol_web("HEAD")
    assert rama_web.comprobar_arbol(arbol) == []
    rutas = _rutas(arbol)
    assert rutas and all(es_web(r) for r in rutas)
    assert {"index.html", "sw.js", "manifest.json", ".nojekyll", "data-health.json"} <= set(rutas)
    assert total < rama_web.PARADA_MB * rama_web.MB
    # Los mismos blobs y modos que HEAD, ni uno más ni uno menos de los de la web.
    def entradas(objeto):
        salida = subprocess.run(["git", "ls-tree", "-r", "-z", objeto], cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout
        return {linea for linea in salida.split("\0") if linea}
    assert entradas(arbol) == {e for e in entradas("HEAD") if es_web(e.split("\t", 1)[1])}


@pytest.mark.skipif(not _es_repo(), reason="sin git (una copia del árbol)")
def test_la_rama_lleva_las_seis_categorias_de_la_web():
    """Con EN_WEB ampliado (las seis categorías, E2-D2), la rama lleva los ficheros de cada una: su data-<cat>.js
    y, si está en HEAD, su data-matchdetail-<cat>.js, y todos los data-season-*.js, data-lineups-*.js y
    data-matchdetail-*.js de HEAD (los de infantil, cadete y juvenil, también)."""
    import categorias
    rutas = set(_rutas(rama_web.arbol_web("HEAD")[0]))
    head = set(subprocess.run(["git", "ls-tree", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.split())
    for cat in categorias.EN_WEB:
        clave = categorias.web_key(cat)
        assert f"data-{clave}.js" in head and f"data-{clave}.js" in rutas, clave
        assert f"data-matchdetail-{clave}.js" not in head or f"data-matchdetail-{clave}.js" in rutas, clave
    for prefijo in ("data-season-", "data-lineups-", "data-matchdetail-"):
        suyos = {r for r in head if r.startswith(prefijo) and r.endswith(".js")}
        assert suyos and suyos <= rutas, prefijo


# ---------------------------------------------------------- todo lo que la web puede pedir

_PREFIJO_RE = re.compile(r"(?<![\w-])(?:\./|\.\./)?(data-|escudos/|icons/|fonts/|dist/|src/)")
_CARACTER = re.compile(r"[\w.\-/]")
_EXTENSION_RE = re.compile(r"\.(?:js|json|css|png|webp|svg|woff2|html)$")


def _rutas_en(texto):
    """Las rutas del sitio que nombra `texto` (código, página o hoja): cada aparición de data-…, escudos/…,
    icons/…, fonts/…, dist/… o src/… seguida de caracteres de ruta, con cada ${…} de una plantilla (aunque lleve
    llaves o comillas dentro) como «*». Solo las que acaban en una extensión del sitio o en «/*»."""
    rutas = set()
    for m in _PREFIJO_RE.finditer(texto):
        i, ruta = m.end(), m.group(1)
        while i < len(texto):
            if texto.startswith("${", i):
                hondo, i = 1, i + 2
                while i < len(texto) and hondo:
                    hondo += {"{": 1, "}": -1}.get(texto[i], 0)
                    i += 1
                ruta += "*"
            elif _CARACTER.match(texto[i]):
                ruta += texto[i]
                i += 1
            else:
                break
        ruta = ruta.rstrip(".")
        if _EXTENSION_RE.search(ruta) or ruta.endswith("/*"):
            rutas.add(ruta)
    return rutas


def _lo_que_la_web_puede_pedir(objeto=None):
    """Los patrones (fnmatch) de todo lo que la web puede pedir, sacados de las fuentes del árbol de trabajo: el
    bloque del precache de sw.js (lo que el SW instala), lo que nombran index.html (sus <script>, sus <link>, el
    import de dist/ y el registro del SW), manifest.json (los iconos), dist/origen.json, las hojas (sus url(),
    resueltas desde su carpeta) y src/*.js (las cargas perezosas de state.js y compañía, con sus plantillas)."""
    pedidos = set()
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    inicio, fin = precache.tramo(sw)
    bloque = sw[inicio:fin]
    pedidos |= {ruta for ruta, _ in precache.ENTRADA_RE.findall(bloque)}
    pedidos |= set(re.findall(r'^  "([^"]+)",$', bloque, re.M))       # OPCIONALES
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    pedidos |= {r.split("?")[0] for r in re.findall(r'''(?:src|href)="\./([^"#]+)"''', index)}
    pedidos |= set(re.findall(r"import\('\./([^']+)'\)", index))
    pedidos |= set(re.findall(r"register\('\./([^']+)'\)", index))
    manifiesto = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    pedidos |= {icono["src"].removeprefix("./") for icono in manifiesto["icons"]}
    origen = json.loads((ROOT / "dist" / "origen.json").read_text(encoding="utf-8"))
    pedidos |= {origen["app"], origen["css"], *origen.get("externos", [])}
    for hoja in [ROOT / "acta.css", *sorted((ROOT / "dist").glob("*.css"))]:
        carpeta = hoja.parent.relative_to(ROOT)
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", hoja.read_text(encoding="utf-8")):
            if not re.match(r"[a-z]+:", url):
                pedidos.add(str((Path("/") / carpeta / url).resolve()).lstrip("/"))
    for fuente in sorted((ROOT / "src").glob("*.js")):
        pedidos |= _rutas_en(fuente.read_text(encoding="utf-8"))
    pedidos |= _rutas_en(sw) | _rutas_en(index)
    return pedidos


def test_la_extraccion_ve_lo_que_busca():
    """La prueba de abajo no puede pasar por no encontrar nada: ve cada carga perezosa de state.js (con sus
    plantillas), los escudos de ui.js, la fuente de las hojas y el precache."""
    assert _rutas_en("fetchData(`data-lineups-${season}-${group}.js`); x = `./escudos/s/${f.replace(/\\.[^./]+$/, '')}.png`;"
                     " y = 'data-action'; z = \"data-matchdetail.js\"") == \
        {"data-lineups-*-*.js", "escudos/s/*.png", "data-matchdetail.js"}
    pedidos = _lo_que_la_web_puede_pedir()
    for patron in ("data-lineups-*-*.js", "data-jugadores-*.js", "data-buscar-*.js", "data-ranking.js",
                   "data-ranking-*.js", "data-season-*.js", "data-season-*-*.js", "data-matchdetail-*.js",
                   "data-alevin.js",
                   "data-health.json", "data-matchdetail.js", "data-seasons.js", "escudos/s/*.png", "escudos/*",
                   "fonts/PublicSans-latin.woff2", "manifest.json", "sw.js", "index.html", "icons/icon-512.png",
                   "src/config.js"):
        assert patron in pedidos, patron
    assert any(fnmatch(p, "dist/app-*.js") for p in pedidos) and any(fnmatch(p, "dist/acta-*.css") for p in pedidos)


@pytest.mark.skipif(not _es_repo(), reason="sin git (una copia del árbol)")
def test_todo_lo_que_la_web_puede_pedir_va_en_la_rama():
    """Cada fichero de HEAD que case con algo que la web puede pedir (_lo_que_la_web_puede_pedir) está en el árbol
    de la rama web: si faltara, esa parte de la web se rompería sin que ninguna prueba del bot lo viera. Y las cargas
    perezosas de las fichas, el buscador, el ranking y las actas casan con ficheros de verdad de la rama."""
    arbol, _ = rama_web.arbol_web("HEAD")
    web = set(_rutas(arbol))
    head = _rutas("HEAD")
    pedidos = _lo_que_la_web_puede_pedir()
    fuera = sorted({r for r in head for p in pedidos if fnmatch(r, p) and r not in web})
    assert fuera == [], fuera
    for patron in ("data-lineups-*-*.js", "data-jugadores-*.js", "data-buscar-*.js", "data-ranking-*.js"):
        assert any(fnmatch(r, patron) for r in web), patron


# ---------------------------------------------------------- repositorios de mentira

def _entorno(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[init]\n\tdefaultBranch = main\n[user]\n\tname = t\n\temail = t@t\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


SITIO = {
    "index.html": '<link rel="stylesheet" href="./dist/acta-1.css"><script defer src="./data-x.js?v=1"></script>'
                  "<script type=\"module\">import('./dist/app-1.js')</script>",
    "dist/origen.json": json.dumps({"codigo": "1", "app": "dist/app-1.js", "css": "dist/acta-1.css",
                                    "externos": ["src/config.js"]}),
    "dist/app-1.js": "export const start = () => {};", "dist/acta-1.css": "body{}", "src/config.js": "export const PORTAL = {};",
    "manifest.json": json.dumps({"icons": [{"src": "./icons/icon-192.png"}, {"src": "./icons/icon-512.png"},
                                           {"src": "./icons/icon-maskable-512.png"}]}),
    "icons/icon-180.png": "180", "icons/icon-192.png": "192", "icons/icon-512.png": "512",
    "icons/icon-maskable-512.png": "m512", "fonts/PublicSans-latin.woff2": "fuente", ".nojekyll": "",
    "data-health.json": "{}", "data-x.js": "const X = 1;", "acta.css": "a{}", "escudos/s/e.png": "e",
    "scripts/x.py": "print(1)", "futbolbase.db": "base", "base/comun.db": "pieza", "docs/a.md": "doc",
    "data-history-2024.json": "{}", "README.md": "léeme",
    "sw.js": f"const CACHE_NAME = 'x';\n{precache.INICIO}\n{precache.FIN}\nself.addEventListener('fetch', () => {{}});\n",
}


def _escribir(carpeta, ficheros):
    for nombre, texto in ficheros.items():
        (carpeta / nombre).parent.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_text(texto, encoding="utf-8")


def _remoto(tmp_path, monkeypatch, ficheros=SITIO):
    """Un remoto desnudo con `ficheros` en main (sw.js con su bloque del precache al día) y un clon. (remoto, clon)."""
    _entorno(tmp_path, monkeypatch)
    remoto, clon = tmp_path / "remoto.git", tmp_path / "clon"
    git("init", "--bare", "-b", "main", str(remoto), cwd=tmp_path)
    git("clone", str(remoto), str(clon), cwd=tmp_path)
    _escribir(clon, ficheros)
    precache.escribir(clon)
    git("add", "-A", cwd=clon)
    git("commit", "-m", "publicado", cwd=clon)
    git("push", "origin", "main", cwd=clon)
    return remoto, clon


def _web(remoto):
    hecho = subprocess.run(["git", "rev-parse", "--verify", "refs/heads/web"], cwd=remoto, capture_output=True, text=True)
    return hecho.stdout.strip() if hecho.returncode == 0 else None


def _cambiar(clon, ficheros, mensaje="cambio"):
    _escribir(clon, ficheros)
    precache.escribir(clon)
    git("add", "-A", cwd=clon)
    git("commit", "-m", mensaje, cwd=clon)
    git("push", "origin", "main", cwd=clon)


def test_publicar_crea_la_rama_y_no_repite(tmp_path, monkeypatch, capsys):
    remoto, clon = _remoto(tmp_path, monkeypatch)
    primero = rama_web.publicar(clon)
    assert primero and _web(remoto) == primero
    assert git("rev-list", "--parents", "-n", "1", "web", cwd=remoto).split() == [primero], "sin padre"
    rutas = set(_rutas("web", remoto))
    assert rutas == {r for r in SITIO if es_web(r)}
    assert not rutas & {"scripts/x.py", "futbolbase.db", "base/comun.db", "docs/a.md", "data-history-2024.json",
                        "README.md"}
    assert git("log", "-1", "--format=%an <%ae>|%cn <%ce>|%s", "web", cwd=remoto).strip() == \
        f"GitHub Actions <actions@github.com>|GitHub Actions <actions@github.com>|Web de main " \
        f"{git('rev-parse', 'main', cwd=remoto)[:12]}"
    # Otra vez, sin cambios: nada.
    assert rama_web.publicar(clon) is None and _web(remoto) == primero
    assert "ya está al día" in capsys.readouterr().out
    # Un commit que solo toca lo que no es de la web: nada.
    _cambiar(clon, {"scripts/x.py": "print(2)", "futbolbase.db": "otra base"})
    assert rama_web.publicar(clon) is None and _web(remoto) == primero
    # Uno que toca un dato: un commit nuevo, hijo del anterior, con los blobs de main.
    _cambiar(clon, {"data-x.js": "const X = 2;"})
    segundo = rama_web.publicar(clon)
    assert segundo and _web(remoto) == segundo
    assert git("rev-list", "--parents", "-n", "1", "web", cwd=remoto).split() == [segundo, primero]

    def blobs(objeto, filtro):
        salida = git("ls-tree", "-r", "-z", objeto, cwd=remoto)
        return {l for l in salida.split("\0") if l and filtro(l.split("\t", 1)[1])}
    assert blobs("web", lambda r: True) == blobs("main", es_web)
    # El árbol de trabajo y el índice del clon no se han tocado.
    assert git("status", "--porcelain", cwd=clon) == ""


def test_publicar_no_retrocede(tmp_path, monkeypatch):
    """Entre el fetch y el push del primero, otro clon sube una main más nueva y pone la web al día con ella: el push
    del primero (sin forzar) no pasa, reintenta desde el fetch y la web se queda con la main más nueva."""
    remoto, clon = _remoto(tmp_path, monkeypatch)
    inicial = rama_web.publicar(clon)
    otro = tmp_path / "otro"
    git("clone", str(remoto), str(otro), cwd=tmp_path)
    _cambiar(clon, {"data-x.js": "const X = 'del primero';"})
    llamadas = []

    def entretanto():
        llamadas.append(1)
        if len(llamadas) > 1:
            return
        git("pull", "-q", "origin", "main", cwd=otro)
        _cambiar(otro, {"data-x.js": "const X = 'del otro, más nuevo';"})
        assert rama_web.publicar(otro)

    assert rama_web.publicar(clon, _antes_de_subir=entretanto) is None
    assert len(llamadas) == 1, "el reintento no sube: la web ya está al día con la main más nueva"
    nueva = git("rev-parse", "main", cwd=remoto).strip()
    assert git("rev-parse", "web^{tree}", cwd=remoto).strip() == rama_web.arbol_web(nueva, otro)[0]
    assert git("show", "web:data-x.js", cwd=remoto) == "const X = 'del otro, más nuevo';"
    assert git("merge-base", "--is-ancestor", inicial, "web", cwd=remoto) == ""


def test_publicar_desde_un_clon_superficial(tmp_path, monkeypatch):
    """Como en el runner (actions/checkout, profundidad 1): crea la rama y, tras otra subida, la pone al día con
    el commit anterior de web como padre."""
    remoto, clon = _remoto(tmp_path, monkeypatch)
    superficial = tmp_path / "superficial"
    git("clone", "-q", "--depth=1", f"file://{remoto}", str(superficial), cwd=tmp_path)
    assert git("rev-parse", "--is-shallow-repository", cwd=superficial).strip() == "true"
    primero = rama_web.publicar(superficial)
    _cambiar(clon, {"data-x.js": "const X = 3;"})
    segundo = rama_web.publicar(superficial)
    assert git("rev-list", "--parents", "-n", "1", "web", cwd=remoto).split() == [segundo, primero]
    assert git("show", "web:data-x.js", cwd=remoto) == "const X = 3;"


def test_un_clon_entero_no_se_vuelve_superficial(tmp_path, monkeypatch):
    """En el PC (un clon entero), publicar no le corta la historia: --depth=1 solo en un clon que ya lo es."""
    remoto, clon = _remoto(tmp_path, monkeypatch)
    _cambiar(clon, {"data-x.js": "const X = 4;"})
    rama_web.publicar(clon)
    assert git("rev-parse", "--is-shallow-repository", cwd=clon).strip() == "false"
    assert len(git("rev-list", "main", cwd=clon).split()) == 2


def test_publicar_reintenta_y_acaba_en_error(tmp_path, monkeypatch):
    """Si el push no pasa nunca, tras `intentos` vueltas, RamaWebError (el paso del bot sale en rojo, sin parar la
    pasada: continue-on-error)."""
    remoto, clon = _remoto(tmp_path, monkeypatch)
    vueltas = []

    def rompe():
        vueltas.append(1)
        (remoto / "hooks" / "pre-receive").write_text("#!/bin/sh\nexit 1\n")
        (remoto / "hooks" / "pre-receive").chmod(0o755)

    with pytest.raises(RamaWebError, match="3 intentos"):
        rama_web.publicar(clon, _antes_de_subir=rompe)
    assert len(vueltas) == 3 and _web(remoto) is None


def test_falta_uno_del_precache_y_no_se_publica(tmp_path, monkeypatch):
    remoto, clon = _remoto(tmp_path, monkeypatch)
    git("rm", "-q", "icons/icon-512.png", cwd=clon)
    git("commit", "-q", "-m", "sin el icono", cwd=clon)
    git("push", "-q", "origin", "main", cwd=clon)
    with pytest.raises(RamaWebError, match=r"icons/icon-512\.png"):
        rama_web.publicar(clon)
    assert _web(remoto) is None


@pytest.mark.parametrize("quitar,motivo", [
    (".nojekyll", r"\.nojekyll"), ("dist/app-1.js", r"dist/app-1\.js"), ("src/config.js", r"src/config\.js"),
    ("data-x.js", r"data-x\.js"), ("sw.js", "sw.js"), ("manifest.json", "manifest.json")])
def test_comprobar_arbol_ve_lo_que_falta(tmp_path, monkeypatch, quitar, motivo):
    _, clon = _remoto(tmp_path, monkeypatch)
    git("rm", "-q", quitar, cwd=clon)
    git("commit", "-q", "-m", "sin uno", cwd=clon)
    arbol, _ = rama_web.arbol_web("HEAD", clon)
    faltan = rama_web.comprobar_arbol(arbol, clon)
    assert faltan and any(re.search(motivo, f) for f in faltan), faltan


def test_comprobar_arbol_para_desde_950_mb(tmp_path, monkeypatch):
    _, clon = _remoto(tmp_path, monkeypatch)
    arbol, total = rama_web.arbol_web("HEAD", clon)
    assert rama_web.comprobar_arbol(arbol, clon) == []
    monkeypatch.setattr(rama_web, "PARADA_MB", 0)
    assert any("Pages no admite" in f for f in rama_web.comprobar_arbol(arbol, clon))


def test_la_orden_arbol(tmp_path, monkeypatch):
    _, clon = _remoto(tmp_path, monkeypatch)
    (clon / "scripts" / "rama_web.py").write_bytes((ROOT / "scripts" / "rama_web.py").read_bytes())
    for nombre in ("precache.py", "escritura.py"):
        (clon / "scripts" / nombre).write_bytes((ROOT / "scripts" / nombre).read_bytes())
    hecho = subprocess.run([sys.executable, "scripts/rama_web.py", "arbol", "--commit", "HEAD"], cwd=clon,
                           capture_output=True, text=True)
    assert hecho.returncode == 0, hecho.stderr
    assert hecho.stdout.strip() == rama_web.arbol_web("HEAD", clon)[0]


def test_sitio(tmp_path):
    """sitio pide cada entrada del precache del sw.js publicado con su ?h= y compara la huella: aquí, un servidor
    local con un fichero cambiado y otro que no está."""
    web = tmp_path / "web"
    web.mkdir()
    _escribir(web, {k: v for k, v in SITIO.items() if es_web(k)})
    precache.escribir(web)
    (web / "icons" / "icon-192.png").write_text("otro contenido")
    (web / "data-x.js").unlink()
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(web)))
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        mal = rama_web.sitio(f"http://127.0.0.1:{servidor.server_address[1]}")
    finally:
        servidor.shutdown()
    assert len(mal) == 2, mal
    assert any(m.startswith("icons/icon-192.png: el precache dice") for m in mal)
    assert any(m == "data-x.js: 404" for m in mal)
    huella = hashlib.sha1(b"otro contenido").hexdigest()[:8]
    assert any(huella in m for m in mal)


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
