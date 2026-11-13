import json
import lzma
import re
import shlex
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import crear_base
from copia.almacen import a_conservar, aceptar, podar, versiones, volcar
from copia.verificar import TABLAS, comprobar

AHORA = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)
README = Path(__file__).resolve().parent.parent / "README.md"


def _ficheros(carpeta: Path) -> list[str]:
    return sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*") if p.is_file())


def test_a_conservar():
    ahora = datetime(2027, 6, 30, 12, 0, tzinfo=timezone.utc)
    dias = [datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc) + timedelta(days=i) for i in range(395)]   # hasta el 30/6/2027
    k = a_conservar(dias, ahora)
    d = lambda a, m, dd: datetime(a, m, dd, 5, 0, tzinfo=timezone.utc)
    assert d(2027, 6, 30) in k            # la última
    assert d(2027, 6, 5) in k             # diaria (25 días)
    assert d(2027, 6, 1) in k             # diaria (29 días y 7 h)
    assert d(2027, 5, 30) in k            # domingo: la más nueva de su semana ISO
    assert d(2027, 5, 31) in k            # la más nueva de mayo
    assert d(2027, 5, 25) not in k        # 36 días, ni fin de semana ISO ni fin de mes
    assert d(2026, 12, 31) in k           # la más nueva de diciembre
    assert d(2026, 12, 13) not in k       # domingo, pero de hace 199 días
    assert d(2026, 6, 30) in k and d(2026, 6, 15) not in k
    # 30 diarias, 22 semanales más y 10 mensuales más.
    assert len(k) == 62 and k <= set(dias)


def test_a_conservar_vacio():
    assert a_conservar([], AHORA) == set()


def test_podar_borra_y_nunca_la_ultima(raiz, tmp_path):
    fechas = [(2026, 6, 1), (2026, 6, 15), (2026, 6, 30), (2027, 5, 25), (2027, 5, 30), (2027, 6, 30)]
    for i, (a, m, d) in enumerate(fechas):
        db = crear_base(tmp_path / f"{i}.db", partidos=40 + i)
        aceptar("v1", db, comprobar(db).recuentos, datetime(a, m, d, 5, 0, tzinfo=timezone.utc))
    ahora = datetime(2027, 6, 30, 12, 0, tzinfo=timezone.utc)
    borradas = podar("v1", ahora)
    assert [p.name for p in borradas] == [
        "futbolbase-20260601-050000.db.xz",
        "futbolbase-20260615-050000.db.xz",
        "futbolbase-20270525-050000.db.xz",
    ]
    assert [v.momento.date().isoformat() for v in versiones("v1")] == ["2026-06-30", "2027-05-30", "2027-06-30"]
    assert not any(p.exists() or p.with_suffix("").with_suffix(".db.json").exists() for p in borradas)
    assert podar("v1", ahora) == []


def test_podar_borra_como_mucho_siete(raiz):
    # 74 diarias puestas a mano (podar no abre las bases) y un reloj que de repente va un año adelantado.
    dias = [datetime(2026, 9, 1, 5, 0, tzinfo=timezone.utc) + timedelta(days=i) for i in range(74)]
    for d in dias:
        xz = raiz / f"versiones/v1/{d:%Y}/futbolbase-{d:%Y%m%d-%H%M%S}.db.xz"
        xz.parent.mkdir(parents=True, exist_ok=True)
        xz.write_bytes(b"xz")
        xz.with_name(xz.name.removesuffix(".xz") + ".json").write_text(json.dumps({"sha256": "0" * 64, "recuentos": {}}))
    ahora = dias[-1] + timedelta(days=365)
    assert len(dias) - len(a_conservar(dias, ahora)) > 7       # sin el tope se llevaría casi todas
    borradas = podar("v1", ahora)
    assert [p.name for p in borradas] == [f"futbolbase-{d:%Y%m%d-%H%M%S}.db.xz" for d in dias[:7]]    # las más viejas
    assert [v.momento for v in versiones("v1")] == dias[7:]
    # Un atraso de verdad se pone al día en unas pocas pasadas.
    assert [p.name for p in podar("v1", ahora)] == [f"futbolbase-{d:%Y%m%d-%H%M%S}.db.xz" for d in dias[7:14]]


def test_volcar(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db")
    aceptar("v1", db, comprobar(db).recuentos, AHORA)
    p = volcar("v1", AHORA)
    assert p == raiz / "volcados/v1/futbolbase-2026-S46.sql.xz"
    # Cargar el volcado en una base nueva da los mismos recuentos en las diez tablas.
    cargada = tmp_path / "cargada.db"
    con = sqlite3.connect(cargada)
    try:
        with lzma.open(p, "rt", encoding="utf-8") as f:
            con.executescript(f.read())
    finally:
        con.close()
    r = comprobar(cargada)
    assert r.ok and set(r.recuentos) == set(TABLAS) and r.recuentos == comprobar(db).recuentos
    # Abrir la actual para volcarla no deja -wal ni -shm a su lado.
    assert _ficheros(raiz / "actual") == ["v1/futbolbase.db"]
    assert volcar("v1", AHORA + timedelta(days=1)) is None          # misma semana ISO
    assert _ficheros(raiz / "volcados") == ["v1/futbolbase-2026-S46.sql.xz"]


def test_el_volcado_se_recupera_con_la_orden_del_readme(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db", partidos=123)
    aceptar("v1", db, comprobar(db).recuentos, AHORA)
    volcado = volcar("v1", AHORA)
    # La orden tal como está en el README, con este volcado: sin la orden sqlite3, que no está en este PC.
    linea, = [l.strip() for l in README.read_text(encoding="utf-8").splitlines() if l.strip().startswith("xz -dc ")]
    orden = re.sub(r"^xz -dc \S+", lambda _: f"xz -dc {shlex.quote(str(volcado))}", linea)
    carpeta = tmp_path / "recuperar"
    carpeta.mkdir()
    subprocess.run(["bash", "-c", orden], cwd=carpeta, check=True)
    r = comprobar(carpeta / "recuperada.db")
    assert r.ok and r.recuentos == comprobar(db).recuentos


def test_volcar_sin_actual(raiz):
    assert volcar("v1", AHORA) is None
    assert not (raiz / "volcados").exists()


def test_volcar_conserva_doce(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db")
    aceptar("v1", db, comprobar(db).recuentos, AHORA)
    for i in range(14):                 # 14 semanas seguidas, la 8.ª ya en 2027 pero aún en la semana 53 de 2026
        assert volcar("v1", AHORA + timedelta(weeks=i)) is not None
    assert _ficheros(raiz / "volcados/v1") == (
        [f"futbolbase-2026-S{s}.sql.xz" for s in range(48, 54)]
        + [f"futbolbase-2027-S{s:02d}.sql.xz" for s in range(1, 7)]
    )


def test_aceptar_no_pisa_una_version_del_mismo_segundo(raiz, tmp_path):
    a = crear_base(tmp_path / "a.db")
    b = crear_base(tmp_path / "b.db", partidos=41)
    ra, rb = comprobar(a), comprobar(b)
    v = aceptar("v1", a, ra.recuentos, AHORA)
    with pytest.raises(FileExistsError): aceptar("v1", b, rb.recuentos, AHORA)
    # El nombre solo guarda segundos: medio segundo después es el mismo.
    with pytest.raises(FileExistsError): aceptar("v1", b, rb.recuentos, AHORA + timedelta(microseconds=500000))
    assert lzma.open(v.ruta).read() == a.read_bytes() and versiones("v1") == [v]
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == a.read_bytes()
