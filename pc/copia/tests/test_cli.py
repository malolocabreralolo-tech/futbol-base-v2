import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import commit_base
from copia.__main__ import main
from copia.almacen import versiones
from copia.ejecutar import ejecutar
from copia.fuentes import Origen

ORIGENES = Path(__file__).resolve().parent.parent / "origenes.json"


@pytest.fixture
def origenes(remoto, tmp_path, monkeypatch) -> Path:
    f = tmp_path / "origenes.json"
    f.write_text(json.dumps({"v1": {"repo": str(remoto), "rama": "main", "base": "futbolbase.db"}}), encoding="utf-8")
    monkeypatch.setenv("FB_COPIA_ORIGENES", str(f))
    return f


def test_cli(raiz, remoto, origenes, tmp_path, monkeypatch, capsys):
    assert main(["estado"]) == 1 and "sin copias" in capsys.readouterr().out
    assert main(["ejecutar"]) == 0
    linea, = capsys.readouterr().out.splitlines()       # una línea por origen
    assert " v1 aceptada matches 40; " in linea
    assert main(["estado"]) == 0 and "v1" in capsys.readouterr().out
    assert main(["versiones", "v1"]) == 0
    v, = versiones("v1")
    sello = f"{v.momento:%Y%m%d-%H%M%S}"
    fila, = capsys.readouterr().out.splitlines()
    assert fila.startswith(sello) and "matches 40" in fila and str(v.ruta) in fila
    assert main(["restaurar", "v1", str(tmp_path / "r")]) == 0 and list((tmp_path / "r").glob("*.db"))
    restaurada, = (tmp_path / "r").glob("*.db")
    assert restaurada.read_bytes() == (remoto / "futbolbase.db").read_bytes()
    assert capsys.readouterr().out.strip() == str(restaurada)
    # --momento se lee en UTC, como los nombres de las versiones que lista `versiones`.
    assert main(["restaurar", "v1", str(tmp_path / "m"), "--momento", sello]) == 0
    assert (tmp_path / "m" / f"futbolbase-{sello}.db").read_bytes() == restaurada.read_bytes()
    assert main(["extraer", "v1", "scripts/x_raw.json", str(tmp_path / "x.json")]) == 0
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": 1}
    capsys.readouterr()
    assert main(["restaurar", "v9", str(tmp_path / "r")]) == 1        # origen desconocido
    salida = capsys.readouterr()
    assert salida.out == "" and salida.err.startswith("error: ") and "v9" in salida.err


def test_cli_fallos_previstos(raiz, remoto, origenes, tmp_path, monkeypatch, capsys):
    assert main(["versiones", "v1"]) == 1                              # sin versiones todavía
    assert main(["restaurar", "v1", str(tmp_path / "r")]) == 1
    assert main(["ejecutar"]) == 0
    v, = versiones("v1")
    for argv in (
        ["restaurar", "v1", str(tmp_path / "r"), "--momento", "20200101-000000"],   # no hay versión de ese momento
        ["restaurar", "v1", str(raiz / "actual/v1")],                               # la actual no se pisa
        ["versiones", "v9"],
        ["extraer", "v9", "scripts/x_raw.json", str(tmp_path / "x.json")],          # origen desconocido
        ["extraer", "v1", "scripts/no-esta.json", str(tmp_path / "x.json")],
        ["ejecutar", "--aceptar-mengua", "v9"],                                     # una errata no se ignora
    ):
        capsys.readouterr()
        assert main(argv) == 1, argv
        assert capsys.readouterr().err.startswith("error: "), argv
    assert not (tmp_path / "r").exists() and not (tmp_path / "x.json").exists()
    assert len((raiz / "registro.log").read_text().splitlines()) == 1     # el --aceptar-mengua erróneo no hizo pasada
    # Una copia que no cuadra se dice y no deja nada.
    v.ruta.write_bytes(b"esto no es xz")
    assert main(["restaurar", "v1", str(tmp_path / "r")]) == 1 and list((tmp_path / "r").glob("*")) == []
    # Un fichero de orígenes que falta o no se entiende.
    for contenido in (None, "no es json"):
        f = tmp_path / "otros.json"
        if contenido is not None:
            f.write_text(contenido)
        monkeypatch.setenv("FB_COPIA_ORIGENES", str(f))
        for argv in (["ejecutar"], ["extraer", "v1", "scripts/x_raw.json", str(tmp_path / "x.json")]):
            capsys.readouterr()
            assert main(argv) == 1, argv
            assert str(f) in capsys.readouterr().err
    # Un --momento mal escrito es un error de uso.
    with pytest.raises(SystemExit) as salida:
        main(["restaurar", "v1", str(tmp_path / "r"), "--momento", "ayer"])
    assert salida.value.code == 2


def test_cli_cuarentena_y_cerrojo(raiz, remoto, origenes, capsys):
    # La primera copia, de otro día: dos versiones distintas del mismo segundo no pueden guardarse.
    ejecutar([Origen("v1", str(remoto), "main", "futbolbase.db")], datetime(2026, 1, 1, tzinfo=timezone.utc))
    commit_base(remoto, 10)
    capsys.readouterr()
    assert main(["ejecutar"]) == 1
    assert " v1 cuarentena mengua: matches 40 → 10; " in capsys.readouterr().out
    assert main(["ejecutar", "--aceptar-mengua", "v1"]) == 0
    assert " v1 aceptada matches 10; " in capsys.readouterr().out
    with open(raiz / ".cerrojo", "w") as otra_pasada:
        fcntl.flock(otra_pasada, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["ejecutar"]) == 2
    salida = capsys.readouterr()
    assert salida.out == "" and "cerrojo" in salida.err


def test_origenes_junto_al_paquete(raiz, monkeypatch, capsys):
    # Sin la variable se usan los del origenes.json que va junto al paquete; nada sale a la red.
    monkeypatch.delenv("FB_COPIA_ORIGENES", raising=False)
    assert main(["ejecutar", "--aceptar-mengua", "v9"]) == 1
    err = capsys.readouterr().err
    assert "v9" in err and "v1" in err and str(ORIGENES) in err
