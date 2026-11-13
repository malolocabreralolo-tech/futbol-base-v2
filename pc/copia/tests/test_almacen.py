import errno
import hashlib
import json
import lzma
import os
import shutil
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import crear_base
from copia.almacen import CopiaDanada, Version, aceptar, apartar, restaurar, versiones
from copia.verificar import comprobar

AHORA = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)
_SUSTITUIR = os.replace


def _ficha(xz: Path) -> Path:
    return xz.with_suffix("").with_suffix(".db.json")


def _motivo(xz: Path) -> Path:
    return xz.with_suffix("").with_suffix(".db.motivo.txt")


def _ficheros(carpeta: Path) -> list[str]:
    return sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*") if p.is_file())


def _aceptar(tmp_path: Path, nombre: str, partidos: int, ahora: datetime, origen: str = "v1") -> tuple[Path, Version]:
    db = crear_base(tmp_path / nombre, partidos=partidos)
    return db, aceptar(origen, db, comprobar(db).recuentos, ahora)


def _falla_tras(buenas: int):
    # Un os.replace que deja pasar las `buenas` primeras sustituciones y falla en las demás, como un disco lleno.
    hechas: list[str] = []

    def replace(origen, destino):
        if len(hechas) >= buenas:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        hechas.append(str(destino))
        _SUSTITUIR(origen, destino)

    return replace


def test_aceptar_guarda_version_y_actual(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db"); r = comprobar(db)
    v = aceptar("v1", db, r.recuentos, AHORA)
    assert v.ruta == raiz / "versiones/v1/2026/futbolbase-20261113-050000.db.xz"
    assert lzma.open(v.ruta).read() == db.read_bytes()
    assert v.sha256 == hashlib.sha256(db.read_bytes()).hexdigest()
    assert json.loads(v.ruta.with_suffix("").with_suffix(".db.json").read_text())["recuentos"]["matches"] == 40
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == db.read_bytes()
    assert stat.S_IMODE(raiz.stat().st_mode) == 0o700
    assert (v.origen, v.momento, v.recuentos) == ("v1", AHORA, r.recuentos)
    assert json.loads(_ficha(v.ruta).read_text()) == {"sha256": v.sha256, "bytes": db.stat().st_size, "recuentos": r.recuentos}
    assert v.ruta.read_bytes().startswith(b"\xfd7zXZ\x00")
    assert _ficheros(raiz) == [
        "actual/v1/futbolbase.db",
        "versiones/v1/2026/futbolbase-20261113-050000.db.json",
        "versiones/v1/2026/futbolbase-20261113-050000.db.xz",
    ]


def test_aceptar_sin_cambios_devuelve_none(raiz, tmp_path):
    db, v = _aceptar(tmp_path, "a.db", 40, AHORA)
    antes = _ficheros(raiz)
    assert aceptar("v1", db, comprobar(db).recuentos, AHORA + timedelta(hours=1)) is None
    assert versiones("v1") == [v] and _ficheros(raiz) == antes
    # Solo cuenta la última: volver a una base anterior sí es una versión nueva.
    _aceptar(tmp_path, "b.db", 41, AHORA + timedelta(days=1))
    assert aceptar("v1", db, comprobar(db).recuentos, AHORA + timedelta(days=2)) is not None
    assert len(versiones("v1")) == 3


def test_aceptar_repone_actual(raiz, tmp_path):
    db, _ = _aceptar(tmp_path, "a.db", 40, AHORA)
    actual = raiz / "actual/v1/futbolbase.db"
    shutil.rmtree(raiz / "actual")
    assert aceptar("v1", db, comprobar(db).recuentos, AHORA + timedelta(hours=1)) is None
    assert actual.read_bytes() == db.read_bytes()
    actual.write_bytes(crear_base(tmp_path / "otra.db", partidos=41).read_bytes())    # una actual que no coincide
    assert aceptar("v1", db, comprobar(db).recuentos, AHORA + timedelta(hours=2)) is None
    assert actual.read_bytes() == db.read_bytes() and len(versiones("v1")) == 1
    assert _ficheros(raiz / "actual") == ["v1/futbolbase.db"]


def test_versiones_ordenadas_y_por_origen(raiz, tmp_path):
    # Se aceptan fuera de orden, a los dos lados de un cambio de año y una con fracciones de segundo.
    momentos = [
        datetime(2027, 1, 1, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 13, 5, 0, 0, 250000, tzinfo=timezone.utc),
        datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc),
    ]
    hechas = [_aceptar(tmp_path, f"v1-{i}.db", 40 + i, m)[1] for i, m in enumerate(momentos)]
    _, de_v2 = _aceptar(tmp_path, "v2.db", 40, AHORA, origen="v2")     # la misma base que la primera de v1
    assert versiones("v1") == sorted(hechas, key=lambda v: v.momento)
    assert [v.ruta.relative_to(raiz).as_posix() for v in versiones("v1")] == [
        "versiones/v1/2026/futbolbase-20261113-050000.db.xz",
        "versiones/v1/2026/futbolbase-20261231-230000.db.xz",
        "versiones/v1/2027/futbolbase-20270101-010000.db.xz",
    ]
    assert versiones("v2") == [de_v2] and versiones("v3") == []
    # Un .xz sin su .json no es una versión.
    shutil.copyfile(hechas[0].ruta, raiz / "versiones/v1/2027/futbolbase-20270102-010000.db.xz")
    assert len(versiones("v1")) == 3


def test_apartar(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db")
    p = apartar("v1", db, ["mengua: matches 100 → 40"], AHORA)
    assert p == raiz / "cuarentena/v1/futbolbase-20261113-050000.db.xz"
    assert "mengua: matches 100 → 40" in p.with_suffix("").with_suffix(".db.motivo.txt").read_text()
    assert not (raiz / "actual").exists()
    assert lzma.decompress(p.read_bytes()) == db.read_bytes() and not (raiz / "versiones").exists()
    otra = crear_base(tmp_path / "b.db", partidos=41)
    q = apartar("v1", otra, ["claves foráneas: 1 filas", "goals está vacía"], AHORA + timedelta(days=1))
    assert _motivo(q).read_text(encoding="utf-8").splitlines() == [
        hashlib.sha256(otra.read_bytes()).hexdigest(),
        "claves foráneas: 1 filas",
        "goals está vacía",
    ]


def test_apartar_no_repite_la_misma(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db")
    p = apartar("v1", db, ["mengua: matches 100 → 40"], AHORA)
    assert apartar("v1", db, ["mengua: matches 100 → 40"], AHORA + timedelta(days=1)) == p
    assert _ficheros(raiz / "cuarentena") == [
        "v1/futbolbase-20261113-050000.db.motivo.txt",
        "v1/futbolbase-20261113-050000.db.xz",
    ]
    # En otro origen la misma base sí se aparta.
    assert apartar("v2", db, ["x"], AHORA + timedelta(days=1)) == raiz / "cuarentena/v2/futbolbase-20261114-050000.db.xz"


def test_apartar_conserva_diez(raiz, tmp_path):
    for i in range(12):
        apartar("v1", crear_base(tmp_path / f"{i}.db", partidos=40 + i), [f"motivo {i}"], AHORA + timedelta(days=i))
    nombres = [f"futbolbase-{AHORA + timedelta(days=i):%Y%m%d-%H%M%S}.db" for i in range(2, 12)]
    assert _ficheros(raiz / "cuarentena/v1") == sorted([n + ".motivo.txt" for n in nombres] + [n + ".xz" for n in nombres])


def test_restaurar_ultima(raiz, tmp_path):
    _aceptar(tmp_path, "vieja.db", 40, AHORA)
    ultima, _ = _aceptar(tmp_path, "ultima.db", 41, AHORA + timedelta(days=1))
    assert restaurar("v1", tmp_path / "r").read_bytes() == ultima.read_bytes()
    assert _ficheros(tmp_path / "r") == ["futbolbase-20261114-050000.db"]


def test_restaurar_por_momento(raiz, tmp_path):
    vieja, _ = _aceptar(tmp_path, "vieja.db", 40, AHORA)
    _aceptar(tmp_path, "ultima.db", 41, AHORA + timedelta(days=1))
    p = restaurar("v1", tmp_path / "r", AHORA)
    assert p == tmp_path / "r/futbolbase-20261113-050000.db" and p.read_bytes() == vieja.read_bytes()
    with pytest.raises(LookupError):
        restaurar("v1", tmp_path / "r", AHORA + timedelta(hours=1))     # no hay versión de ese momento
    with pytest.raises(LookupError):
        restaurar("v2", tmp_path / "r")                                  # origen sin versiones


def test_restaurar_detecta_copia_danada(raiz, tmp_path):
    db, v = _aceptar(tmp_path, "a.db", 40, AHORA)
    buena = v.ruta.read_bytes()
    otra = crear_base(tmp_path / "otra.db", partidos=41)
    # Otra base que se descomprime bien, bytes que no son xz y el .xz recortado.
    for contenido in (lzma.compress(otra.read_bytes()), b"esto no es xz", buena[:-100]):
        v.ruta.write_bytes(contenido)
        with pytest.raises(CopiaDanada): restaurar("v1", tmp_path / "r")
    # Una base dañada con su huella apuntada en el .json: la para comprobar().
    datos = bytearray(db.read_bytes())
    datos[4096:8192] = b"\xff" * 4096
    v.ruta.write_bytes(lzma.compress(bytes(datos)))
    _ficha(v.ruta).write_text(json.dumps({"sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos), "recuentos": v.recuentos}))
    with pytest.raises(CopiaDanada): restaurar("v1", tmp_path / "r")
    assert _ficheros(tmp_path / "r") == []


def test_restaurar_no_escribe_en_actual(raiz, tmp_path):
    db, _ = _aceptar(tmp_path, "a.db", 40, AHORA)
    with pytest.raises(ValueError): restaurar("v1", raiz / "actual/v1")
    (tmp_path / "enlace").symlink_to(raiz / "actual/v1")
    for destino in (raiz / "actual", raiz / "actual/v1/sub", raiz / "versiones/../actual/v1", tmp_path / "enlace"):
        with pytest.raises(ValueError): restaurar("v1", destino)
    assert _ficheros(raiz / "actual") == ["v1/futbolbase.db"]
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == db.read_bytes()


def test_escritura_interrumpida_no_deja_version(raiz, tmp_path, monkeypatch):
    db = crear_base(tmp_path / "a.db"); r = comprobar(db)
    # monkeypatch.context() y no monkeypatch.undo(), que desharía también FB_COPIA_RAIZ y escribiría en ~/backups.
    for buenas in (0, 1):       # falla al poner el .xz o, ya puesto el .xz, al poner su .json
        with monkeypatch.context() as m:
            m.setattr(os, "replace", _falla_tras(buenas))
            with pytest.raises(OSError): aceptar("v1", db, r.recuentos, AHORA)
        assert versiones("v1") == [] and not (raiz / "actual/v1/futbolbase.db").exists()
        assert _ficheros(raiz) == []        # ni temporales sueltos ni un .xz sin su .json
    assert aceptar("v1", db, r.recuentos, AHORA) is not None
    # Con una actual buena, un fallo en cualquier paso de la siguiente la deja como estaba.
    nueva = crear_base(tmp_path / "b.db", partidos=41)
    for buenas in (0, 1, 2):    # el .xz, su .json o la propia actual
        with monkeypatch.context() as m:
            m.setattr(os, "replace", _falla_tras(buenas))
            with pytest.raises(OSError): aceptar("v1", nueva, comprobar(nueva).recuentos, AHORA + timedelta(days=1))
        assert (raiz / "actual/v1/futbolbase.db").read_bytes() == db.read_bytes()
        assert _ficheros(raiz / "actual") == ["v1/futbolbase.db"]
    # La pasada siguiente encuentra la versión ya guardada y repone la actual.
    assert aceptar("v1", nueva, comprobar(nueva).recuentos, AHORA + timedelta(days=2)) is None
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == nueva.read_bytes()
