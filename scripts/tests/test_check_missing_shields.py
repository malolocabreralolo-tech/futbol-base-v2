"""check_missing_shields.py: los escudos que faltan de las seis categorías (categorias.DB_NAME), las de la
temporada en curso (data-<cat>.js) y las de las pasadas (data-season-<S>.js y data-season-<S>-<cat>.js).

Sobre una web pequeña escrita aquí (los data-*.js con la forma de los del generador). Clubes inventados."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_missing_shields as C  # noqa: E402


def _grupo(gid, *equipos):
    return {"id": gid, "standings": [[i + 1, e, 0, 0, 0, 0, 0, 0, 0, 0] for i, e in enumerate(equipos)]}


def _js(nombre, valor):
    return f"const {nombre}={json.dumps(valor, ensure_ascii=False)};\n"


def web(tmp_path, monkeypatch, infantil=True):
    """2026-27 en curso con las seis (infantil, si `infantil`) y 2025-26 pasada con benjamín y cadete. El
    Club Uno tiene escudo y juega en benjamín y en juvenil; el Club Juvenil, solo en juvenil, no lo tiene."""
    ficheros = {
        "data-shields.js": _js("SHIELDS", {"Club Uno": "uno.png", "Club Dos": "dos.png"}),
        "data-seasons.js": _js("SEASONS", [{"name": "2026-2027", "current": True},
                                           {"name": "2025-2026", "current": False}]),
        "data-benjamin.js": _js("BENJAMIN", [_grupo("A1", "Club Uno", "Club Dos")]),
        "data-prebenjamin.js": _js("PREBENJAMIN", []),
        "data-alevin.js": _js("ALEVIN", []),
        "data-cadete.js": _js("CADETE", []),
        "data-juvenil.js": _js("JUVENIL", [_grupo("JUV2G1", "Club Uno", "Club Juvenil")]),
        "data-season-2025-2026.js": _js("SEASON_2025_2026", {"name": "2025-2026", "benjamin": [_grupo("A1", "Club Dos")],
                                                             "prebenjamin": []}),
        "data-season-2025-2026-cadete.js": _js("SEASON_2025_2026_CADETE", {"name": "2025-2026",
                                                                           "cadete": [_grupo("CADI1", "UD Cadete Viejo")]}),
    }
    if infantil:
        ficheros["data-infantil.js"] = _js("INFANTIL", [_grupo("INFPG1", "Club Dos", "Club Infantil")])
    for nombre, texto in ficheros.items():
        (tmp_path / nombre).write_text(texto, encoding="utf-8")
    monkeypatch.setattr(C, "ROOT", str(tmp_path))
    monkeypatch.setattr(C, "SHIELDS_PATH", str(tmp_path / "data-shields.js"))
    monkeypatch.setattr(C, "SEASONS_PATH", str(tmp_path / "data-seasons.js"))


def test_las_seis_categorias(tmp_path, monkeypatch, capsys):
    web(tmp_path, monkeypatch)
    C.main()
    out = capsys.readouterr().out
    # El que solo juega en juvenil sale en la lista; el club de benjamín y juvenil con escudo, no.
    assert "[2026-2027] JUVENIL - 1 sin escudo:\n  - 'Club Juvenil'\n" in out
    assert "[2026-2027] INFANTIL - 1 sin escudo:\n  - 'Club Infantil'\n" in out
    assert "[2025-2026] CADETE - 1 sin escudo:\n  - 'UD Cadete Viejo'\n" in out
    assert "'Club Uno'" not in out and "BENJAMIN" not in out
    assert "=== TOTAL equipos únicos sin escudo: 3 ===" in out


def test_una_categoria_sin_fichero_no_para(tmp_path, monkeypatch, capsys):
    # data-infantil.js no está (una web de antes de la parte E): las demás se cuentan igual.
    web(tmp_path, monkeypatch, infantil=False)
    C.main()
    out = capsys.readouterr().out
    assert "'Club Juvenil'" in out and "INFANTIL" not in out and "WARNING" not in out
    assert "=== TOTAL equipos únicos sin escudo: 2 ===" in out
