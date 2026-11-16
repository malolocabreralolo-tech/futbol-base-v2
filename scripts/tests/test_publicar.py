"""La subida de versión de una publicación.

Cada fase del rediseño se publica al terminarla. La publicación empaqueta dist/, sube a la vez las ?v= de
index.html y CACHE_NAME de sw.js, con la misma cadena, y reescribe el manifiesto del precache, sin tocar
«Última actualización», que es la fecha de los datos (source_health la publica como lastDataChange). La
versión es la fecha UTC y estrictamente mayor que la vigente. El bot sigue como hoy: bump_cache_version sin
argumentos mueve el pie. Árboles sintéticos, y una copia del árbol real: nunca los ficheros vivos. Las que
empaquetan se saltan sin esbuild, como en el bot.
"""
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import codigo  # noqa: E402
import generate_js  # noqa: E402
import precache  # noqa: E402
import publicar  # noqa: E402

VERSION_RE = re.compile(r"\?v=(\d{8}[a-z]?)")
FOOTER = "Última actualización: 01/09/2026"


def _tree(tmp_path, version="20260925b"):
    """Un árbol completo de juguete: index.html y sw.js con las marcas del bot y el bloque del precache, un
    dist/ de una publicación anterior, el código que se empaqueta y lo demás que se precachea."""
    files = {
        "src/app.js": "export function start() {}\n",
        "src/config.js": "export const PORTAL = {};\n",
        "acta.css": "body { margin: 0; }\n",
        "index.html": (
            '<link rel="stylesheet" href="./dist/acta-00000000.css">\n'
            f'<span id="legacyUpdated" hidden>{FOOTER}</span>\n'
            f'<script defer src="./data-benjamin.js?v={version}"></script>\n'
            f'<script defer src="./data-seasons.js?v={version}"></script>\n'
            "<script type=\"module\">\n"
            "  import('./dist/app-00000000.js');\n"
            "</script>\n"),
        "sw.js": (f"const CACHE_NAME = 'futbolbase2-v{version}';\nconst CRESTS_CACHE = 'futbolbase2-escudos-00000000';\n"
                  f"{precache.INICIO}\nconst PRECACHE = {{}};\nconst OPCIONALES = [];\n{precache.FIN}\n"),
        "dist/origen.json": '{"codigo": "00000000", "app": "dist/app-00000000.js", "css": "dist/acta-00000000.css", "externos": ["src/config.js"]}\n',
        "dist/app-00000000.js": "export function start() {}\n",
        "dist/acta-00000000.css": "body{}\n",
        "data-benjamin.js": "const BENJAMIN=[];\n",
        "data-seasons.js": "const SEASONS=[];\n",
        **{rel: f"fijo {rel}\n" for rel in precache.FIJOS},
    }
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _copia_del_arbol(tmp_path):
    """Lo que leen publicar.py, codigo.py y precache.py, copiado del repositorio."""
    for name in ("index.html", "sw.js", "acta.css", "manifest.json", *(path.name for path in ROOT.glob("data-*.js"))):
        shutil.copy(ROOT / name, tmp_path / name)
    for name in ("src", "dist", "fonts", "icons"):
        shutil.copytree(ROOT / name, tmp_path / name)
    return tmp_path


def _fuera_del_bloque(sw):
    return sw[:sw.index(precache.INICIO)] + sw[sw.index(precache.FIN):]


con_esbuild = pytest.mark.skipif(not codigo.ESBUILD.exists(), reason="sin esbuild: npm ci --prefix scripts/empaquetar")


@pytest.mark.parametrize("current, today, want", [
    ("20260925b", "20260926", "20260926"),     # vigente de un día anterior: la fecha del día
    ("20260926", "20260926", "20260926b"),     # vigente de hoy: la letra siguiente
    ("20260926b", "20260926", "20260926c"),
    ("20260927", "20260926", "20260927b"),     # vigente de un día posterior: nunca retrocede
    ("20260927c", "20260926", "20260927d"),
    ("20260925z", "20260926", "20260926"),     # con la z, pero de un día anterior: la fecha del día
    ("20260926z", "20260926", "20260927"),     # con la z de hoy: el día siguiente al de la vigente, sin letra
    ("20260927z", "20260926", "20260928"),     # con la z de un día posterior: el siguiente a ese
    ("20261130z", "20261130", "20261201"),     # fin de mes
    ("20261231z", "20261231", "20270101"),     # fin de año
], ids=["de-ayer", "de-hoy", "de-hoy-b", "posterior", "posterior-c", "z-de-ayer", "z-de-hoy", "z-posterior",
        "z-fin-de-mes", "z-31-dic"])
def test_la_version_de_una_publicacion_es_estrictamente_mayor(current, today, want):
    assert publicar.next_publish_version(current, today) == want
    assert want > current


@pytest.mark.parametrize("current, today", [
    ("2026092", "20260926"), ("20260926", "hoy"),
], ids=["vigente-sin-forma", "hoy-sin-forma"])
def test_sin_version_posible_se_para(current, today):
    with pytest.raises(ValueError):
        publicar.next_publish_version(current, today)


def test_bump_cache_version_sin_tocar_el_pie(tmp_path):
    site = _tree(tmp_path)
    before = (site / "index.html").read_text(encoding="utf-8")
    generate_js.bump_cache_version(str(site), touch_footer=False, version="20260930")
    after = (site / "index.html").read_text(encoding="utf-8")
    assert VERSION_RE.findall(after) == ["20260930"] * 2
    assert FOOTER in after
    assert after == before.replace("20260925b", "20260930")
    assert (site / "sw.js").read_text(encoding="utf-8").splitlines()[0] == "const CACHE_NAME = 'futbolbase2-v20260930';"


def test_bump_cache_version_del_bot_mueve_el_pie(tmp_path):
    # Sin argumentos, como la llama bump_if_changed: la versión del día y el pie, a hoy.
    site = _tree(tmp_path)
    generate_js.bump_cache_version(str(site))
    after = (site / "index.html").read_text(encoding="utf-8")
    today = date.today()
    assert set(VERSION_RE.findall(after)) == {today.strftime("%Y%m%d")}
    assert f"Última actualización: {today.strftime('%d/%m/%Y')}" in after


def test_bump_cache_version_rechaza_una_version_sin_la_forma_del_bot(tmp_path):
    site = _tree(tmp_path)
    before = (site / "index.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        generate_js.bump_cache_version(str(site), touch_footer=False, version="b4")
    assert (site / "index.html").read_text(encoding="utf-8") == before


def test_next_version_con_el_dia_del_bot():
    day = date(2026, 9, 26)
    assert generate_js._next_version('<script src="./a.js?v=20260925b">', day) == "20260926"
    assert generate_js._next_version('<script src="./a.js?v=20260926">', day) == "20260926b"
    assert generate_js._next_version('<script src="./a.js?v=20260926b">', day) == "20260926c"
    assert generate_js._next_version('<script src="./a.js?v=20260926z">', day) == "20260927"
    assert generate_js._next_version("<p>sin versión</p>", day) == "20260926"


@pytest.mark.parametrize("current, today, want", [
    ("20260927", date(2026, 9, 26), "20260927b"),    # vigente posterior a hoy, sin letra: la b
    ("20260927c", date(2026, 9, 26), "20260927d"),
    ("20260927z", date(2026, 9, 26), "20260928"),    # vigente posterior con la z: el día siguiente al suyo
    ("20261130z", date(2026, 11, 30), "20261201"),   # fin de mes
    ("20261231z", date(2026, 12, 31), "20270101"),   # fin de año
    ("20261231z", date(2026, 12, 30), "20270101"),
], ids=["posterior", "posterior-c", "z-posterior", "z-fin-de-mes", "z-31-dic", "z-31-dic-posterior"])
def test_next_version_siempre_sube(current, today, want):
    assert generate_js._next_version(f'<script src="./a.js?v={current}">', today) == want
    assert want > current


@pytest.mark.parametrize("subir", ["bot", "publicar"])
def test_sesenta_subidas_el_mismo_dia_siempre_suben(subir):
    # Un día con 60 versiones (más allá de la z): cada una, mayor como texto que la anterior y con la forma del bot.
    day = date(2026, 11, 15)
    current = "20261115"
    for _ in range(60):
        if subir == "bot":
            new = generate_js._next_version(f'<script src="./a.js?v={current}">', day)
        else:
            new = publicar.next_publish_version(current, day.strftime("%Y%m%d"))
        assert re.fullmatch(r"\d{8}[a-z]?", new), new
        assert new > current, (current, new)
        current = new


def test_el_bot_sigue_moviendo_el_pie_cuando_cambian_los_datos(tmp_path):
    site = _tree(tmp_path)
    (site / "data-foo.js").write_text("const FOO=1;\n", encoding="utf-8")
    before = generate_js.snapshot_data_files(str(site))
    (site / "data-foo.js").write_text("const FOO=2;\n", encoding="utf-8")
    assert generate_js.bump_if_changed(before, str(site)) is True
    assert f"Última actualización: {date.today().strftime('%d/%m/%Y')}" in (site / "index.html").read_text(encoding="utf-8")


@con_esbuild
def test_publicar_sube_las_marcas_y_empaqueta_sin_tocar_el_pie(tmp_path, monkeypatch, capsys):
    site = _tree(tmp_path)
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    assert publicar.main(["--root", str(site)]) == 0
    index = (site / "index.html").read_text(encoding="utf-8")
    assert VERSION_RE.findall(index) == ["20260925c"] * 2
    assert FOOTER in index
    origen = codigo.leer_origen(site)
    assert origen["codigo"] == codigo.huella(site) and "CODIGO" not in index
    assert f"./{origen['app']}" in index and f"./{origen['css']}" in index
    assert not (site / "dist" / "app-00000000.js").exists(), "el paquete viejo se borra"
    assert (site / "sw.js").read_text(encoding="utf-8").splitlines()[0] == "const CACHE_NAME = 'futbolbase2-v20260925c';"
    assert codigo.main(["--check", "--root", str(site)]) == 0
    # El manifiesto, el último: con la huella del index.html ya subido y la del paquete nuevo.
    assert precache.comprobar(site) == []
    entries, _ = precache.entradas(site)
    assert origen["app"] in entries and origen["css"] in entries
    assert capsys.readouterr().out.splitlines()[:4] == [
        f"fuentes {codigo.huella(site)}: {origen['app']} y {origen['css']}, en index.html (el precache de sw.js: scripts/precache.py)",
        f"versión 20260925c (antes, 20260925b): 2 ?v= en index.html y futbolbase2-v20260925c en sw.js; «{FOOTER}», sin tocar",
        f"precache: {len(entries)} ficheros, 0 opcionales, en sw.js",
        "fuentes " + codigo.huella(site) + f": dist/ es el de las fuentes ({origen['app']} y {origen['css']})",
    ]


def _textos(site):
    return {path.relative_to(site).as_posix(): path.read_bytes() for path in sorted(site.rglob("*")) if path.is_file()}


def test_publicar_sin_esbuild_se_para_sin_escribir(tmp_path, monkeypatch, capsys):
    # Sin esbuild, la versión subiría con el código de antes: nada escrito, ni las ?v=.
    site = _tree(tmp_path)
    before = _textos(site)
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    monkeypatch.setattr(codigo, "ESBUILD", tmp_path / "no-esta" / "esbuild")
    assert publicar.main(["--root", str(site)]) == 1
    assert _textos(site) == before
    assert capsys.readouterr().out.strip() == "falta esbuild: npm ci --prefix scripts/empaquetar: nada escrito"


def test_publicar_sin_un_obligatorio_del_precache_se_para_sin_escribir(tmp_path, monkeypatch, capsys):
    # Sin manifest.json el SW no se instalaría: nada escrito, ni dist/ ni las ?v=. Con esbuild o sin él (el
    # bot no lo tiene): la comprobación de esbuild, que va antes, se da por buena.
    site = _tree(tmp_path)
    (site / "manifest.json").unlink()
    before = _textos(site)
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    monkeypatch.setattr(codigo, "puede_empaquetar", lambda root: None)
    assert publicar.main(["--root", str(site)]) == 1
    assert _textos(site) == before
    out = capsys.readouterr().out.strip()
    assert out.startswith("el precache no se puede calcular") and out.endswith(": nada escrito"), out


def test_publicar_sin_el_bloque_del_precache_se_para_sin_escribir(tmp_path, monkeypatch, capsys):
    site = _tree(tmp_path)
    sw = (site / "sw.js").read_text(encoding="utf-8")
    (site / "sw.js").write_text(_fuera_del_bloque(sw).replace(precache.FIN, ""), encoding="utf-8")
    before = _textos(site)
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    assert publicar.main(["--root", str(site)]) == 1
    assert _textos(site) == before
    assert capsys.readouterr().out.strip().endswith(": nada escrito")


def test_publicar_se_para_si_las_v_no_son_todas_iguales(tmp_path, monkeypatch, capsys):
    # Una de las dos ?v= queda distinta de la otra (una fusión a medias, por ejemplo): la versión
    # no puede salir solo de la primera sin comprobar que todas van iguales.
    site = _tree(tmp_path, version="20260925b")
    index = (site / "index.html").read_text(encoding="utf-8")
    index = index.replace("data-seasons.js?v=20260925b", "data-seasons.js?v=20260925c", 1)
    (site / "index.html").write_text(index, encoding="utf-8")
    before = [(site / name).read_text(encoding="utf-8") for name in ("index.html", "sw.js")]
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    assert publicar.main(["--root", str(site)]) == 1
    assert [(site / name).read_text(encoding="utf-8") for name in ("index.html", "sw.js")] == before
    assert capsys.readouterr().out.strip().endswith(": nada escrito")


def test_publicar_se_para_si_cache_name_no_coincide_con_las_v(tmp_path, monkeypatch, capsys):
    # Las dos ?v= van iguales entre sí, pero el CACHE_NAME de sw.js quedó de otra versión.
    site = _tree(tmp_path, version="20260925b")
    sw = (site / "sw.js").read_text(encoding="utf-8")
    (site / "sw.js").write_text(sw.replace("futbolbase2-v20260925b", "futbolbase2-v20260925c", 1), encoding="utf-8")
    before = [(site / name).read_text(encoding="utf-8") for name in ("index.html", "sw.js")]
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    assert publicar.main(["--root", str(site)]) == 1
    assert [(site / name).read_text(encoding="utf-8") for name in ("index.html", "sw.js")] == before
    assert capsys.readouterr().out.strip().endswith(": nada escrito")


@con_esbuild
def test_publicar_en_la_z_pasa_al_dia_siguiente(tmp_path, monkeypatch):
    site = _tree(tmp_path, version="20260925z")
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20260925")
    assert publicar.main(["--root", str(site)]) == 0
    assert VERSION_RE.findall((site / "index.html").read_text(encoding="utf-8")) == ["20260926"] * 2
    assert (site / "sw.js").read_text(encoding="utf-8").splitlines()[0] == "const CACHE_NAME = 'futbolbase2-v20260926';"


@con_esbuild
def test_publicar_sobre_una_copia_del_arbol_solo_cambia_las_marcas(tmp_path, monkeypatch):
    # El árbol real, con el código del que sale: solo cambian las ?v=, CACHE_NAME y, en el bloque del
    # precache, la huella de index.html (dist/ ya es el de las fuentes, test_empaquetar.py), nunca el pie, el
    # paquete ni el resto.
    site = _copia_del_arbol(tmp_path)
    before = (site / "index.html").read_text(encoding="utf-8")
    sw_before = (site / "sw.js").read_text(encoding="utf-8")
    dist_before = {path.name: path.read_bytes() for path in (site / "dist").iterdir()}
    entries_before, _ = precache.entradas(site)
    monkeypatch.setattr(publicar, "_today_utc", lambda: "20991231")
    assert publicar.main(["--root", str(site)]) == 0
    after = (site / "index.html").read_text(encoding="utf-8")
    assert VERSION_RE.sub("", after) == VERSION_RE.sub("", before)
    assert set(VERSION_RE.findall(after)) == {"20991231"}
    assert len(VERSION_RE.findall(after)) == len(VERSION_RE.findall(before))
    sw = (site / "sw.js").read_text(encoding="utf-8")
    assert sw.splitlines()[0] == "const CACHE_NAME = 'futbolbase2-v20991231';"
    assert _fuera_del_bloque(sw).splitlines()[1:] == _fuera_del_bloque(sw_before).splitlines()[1:]
    assert {path.name: path.read_bytes() for path in (site / "dist").iterdir()} == dist_before
    assert precache.comprobar(site) == []
    entries, _ = precache.entradas(site)
    assert [ruta for ruta in entries if entries[ruta] != entries_before.get(ruta)] == ["index.html"]
