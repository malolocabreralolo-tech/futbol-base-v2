import fcntl
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import commit_base, crear_base, git
from copia import ejecutar as ejecutar_mod
from copia import rutas, verificar
from copia.__main__ import main
from copia.almacen import restaurar, versiones
from copia.ejecutar import ejecutar, estado
from copia.fuentes import Origen, actualizar_espejo, extraer_base
from copia.verificar import comprobar

AHORA = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)


def _origen(remoto: Path, nombre: str = "v1", base: str = "futbolbase.db") -> Origen:
    return Origen(nombre, str(remoto), "main", base)


def _estado(raiz: Path) -> dict:
    return json.loads((raiz / "estado.json").read_text(encoding="utf-8"))


def _registro(raiz: Path) -> list[str]:
    return (raiz / "registro.log").read_text(encoding="utf-8").splitlines()


def _temporales(raiz: Path) -> list[Path]:
    return list(raiz.glob(".pasada-*"))


def _subir(remoto: Path, datos: bytes) -> str:
    (remoto / "futbolbase.db").write_bytes(datos)
    git(remoto, "commit", "--quiet", "-am", "otra base")
    return git(remoto, "rev-parse", "HEAD")


def test_pasada_buena(raiz, remoto, capsys, monkeypatch):
    o = _origen(remoto)
    sacadas = []

    def espia(origen, commit, destino):
        sacadas.append(destino)
        return extraer_base(origen, commit, destino)

    with monkeypatch.context() as m:
        m.setattr(ejecutar_mod, "extraer_base", espia)
        assert ejecutar([o], AHORA) == 0
    # La base sale a un temporal en la propia raíz (mismo disco que actual/ y versiones/) y no se queda allí.
    destino, = sacadas
    assert destino.parent.parent == raiz and destino.parent.name.startswith(".pasada-")
    assert not destino.parent.exists()
    e = json.loads((raiz / "estado.json").read_text())["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada"
    assert e["ultima_buena"]["recuentos"]["matches"] == 40
    assert e["ultima_buena"]["commit"] == git(remoto, "rev-parse", "main")
    assert (raiz / "actual/v1/futbolbase.db").exists()
    assert (raiz / "volcados/v1/futbolbase-2026-S46.sql.xz").exists()
    linea, = (raiz / "registro.log").read_text().splitlines()
    assert " v1 aceptada" in linea
    v, = versiones("v1")
    assert e["ultima_buena"] == {
        "momento": "2026-11-13T05:00:00+00:00",
        "sha256": v.sha256,
        "recuentos": v.recuentos,
        "version": "versiones/v1/2026/futbolbase-20261113-050000.db.xz",
        "commit": git(remoto, "rev-parse", "main"),
    }
    assert e["ultima_comprobacion"]["momento"] == "2026-11-13T05:00:00+00:00"
    assert e["ultima_comprobacion"]["commit"] == e["ultima_buena"]["commit"]
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == (remoto / "futbolbase.db").read_bytes()
    assert linea.startswith("2026-11-13T05:00:00+00:00 v1 aceptada matches 40; players 1; ")
    # Lo que sale por pantalla (el journal de systemd) es la misma línea del registro.
    assert capsys.readouterr().out.splitlines() == [linea]
    # La base sacada del espejo no se queda en la raíz.
    assert _temporales(raiz) == []


def test_sin_cambios(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA)
    buena = _estado(raiz)["v1"]["ultima_buena"]
    assert ejecutar([o], AHORA + timedelta(hours=1)) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "sin cambios"
    assert e["ultima_comprobacion"]["momento"] == "2026-11-13T06:00:00+00:00"
    assert e["ultima_buena"] == buena
    assert len(versiones("v1")) == 1
    assert [l.split(" ", 1)[1].startswith("v1 sin cambios ") for l in _registro(raiz)] == [False, True]
    # Un commit nuevo que no toca la base tampoco cambia la última buena.
    (remoto / "scripts/x_raw.json").write_text(json.dumps({"a": 2}))
    git(remoto, "commit", "--quiet", "-am", "a vale 2")
    assert ejecutar([o], AHORA + timedelta(hours=2)) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "sin cambios"
    assert e["ultima_comprobacion"]["commit"] == git(remoto, "rev-parse", "main") != buena["commit"]
    assert e["ultima_buena"] == buena


def test_sin_cambios_tambien_vuelca_y_poda(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA)
    commit_base(remoto, 41)
    ejecutar([o], AHORA + timedelta(days=1))
    assert len(versiones("v1")) == 2
    # Días sin cambios en la base: el volcado de la semana sale igual y la retención sigue corriendo.
    assert ejecutar([o], AHORA + timedelta(days=40)) == 0
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["resultado"] == "sin cambios"
    assert sorted(p.name for p in (raiz / "volcados/v1").iterdir()) == ["futbolbase-2026-S46.sql.xz", "futbolbase-2026-S52.sql.xz"]
    assert [v.momento for v in versiones("v1")] == [AHORA + timedelta(days=1)]
    assert _registro(raiz)[-1].endswith("; volcado en volcados/v1/futbolbase-2026-S52.sql.xz; versiones viejas borradas: 1")


def test_base_menguada_va_a_cuarentena(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 10)
    buena = _estado(raiz)["v1"]["ultima_buena"]
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    e = json.loads((raiz / "estado.json").read_text())["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "cuarentena"
    assert "mengua: matches 40 → 10" in e["ultima_comprobacion"]["detalle"]
    assert e["ultima_buena"]["recuentos"]["matches"] == 40
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 40
    assert e["ultima_buena"] == buena and len(versiones("v1")) == 1
    assert e["ultima_comprobacion"]["commit"] == git(remoto, "rev-parse", "main")
    assert len(list((raiz / "cuarentena/v1").glob("*.db.xz"))) == 1
    assert " v1 cuarentena mengua: matches 40 → 10; " in _registro(raiz)[-1]
    assert _temporales(raiz) == []


def test_base_corrupta_va_a_cuarentena(raiz, remoto):
    o = _origen(remoto)
    buena = (remoto / "futbolbase.db").read_bytes()
    ejecutar([o], AHORA)
    datos = bytearray(buena)
    datos[4096:8192] = b"\xff" * 4096
    _subir(remoto, bytes(datos))
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "cuarentena"
    assert e["ultima_comprobacion"]["detalle"][0].startswith(("integridad:", "no se puede abrir:"))
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == buena
    assert len(versiones("v1")) == 1
    # Aceptar una mengua no se salta el resto de las comprobaciones.
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 1
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["resultado"] == "cuarentena"
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == buena


def test_aceptar_mengua(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 10)
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada"
    assert e["ultima_buena"]["recuentos"]["matches"] == 10
    assert e["ultima_buena"]["momento"] == "2026-11-15T05:00:00+00:00"
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 10
    assert len(versiones("v1")) == 2
    # Desde ahí la mengua se mide contra la nueva: la siguiente pasada ya no la ve.
    assert ejecutar([o], AHORA + timedelta(days=3)) == 0
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["resultado"] == "sin cambios"


def _base(ruta: Path, partidos: int, sql: str = "") -> bytes:
    # Una base de prueba con algún cambio más (una tabla borrada o vaciada) metido con SQL.
    crear_base(ruta, partidos=partidos, wal=False)
    con = sqlite3.connect(ruta)
    try:
        con.executescript(sql)
    finally:
        con.close()
    return ruta.read_bytes()


def test_aceptar_mengua_acepta_la_que_se_aparto(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 38)        # 40 → 38 es un 5 % menos
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    apartada = remoto / "futbolbase.db"
    assert _estado(raiz)["v1"]["ultima_apartada"] == {
        "momento": "2026-11-14T05:00:00+00:00",
        "sha256": hashlib.sha256(apartada.read_bytes()).hexdigest(),
        "recuentos": comprobar(apartada).recuentos,
        "motivos": ["mengua: matches 40 → 38"],
    }
    # El remoto no cambia y se acepta a mano.
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada"
    assert "aceptado a mano: matches 40 → 38" in e["ultima_comprobacion"]["detalle"]
    assert e["ultima_buena"]["recuentos"]["matches"] == 38 and "ultima_apartada" not in e
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 38
    assert " v1 aceptada matches 38; " in _registro(raiz)[-1]


def test_aceptar_mengua_no_acepta_lo_que_llegue_despues(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 38)
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    # Antes de aceptarla, el remoto baja a 3: eso no es lo que se vio.
    commit_base(remoto, 3)
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 1
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "cuarentena"
    assert e["ultima_comprobacion"]["detalle"][0] == "mengua: matches 38 → 3"
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 40
    assert e["ultima_buena"]["recuentos"]["matches"] == 40 and len(versiones("v1")) == 1
    assert e["ultima_apartada"]["recuentos"]["matches"] == 3
    # Aceptar esta otra es otra decisión, que ya se puede tomar viéndola.
    assert ejecutar([o], AHORA + timedelta(days=3), aceptar_mengua={"v1"}) == 0
    assert "aceptado a mano: matches 40 → 3" in _estado(raiz)["v1"]["ultima_comprobacion"]["detalle"]


def test_aceptar_mengua_por_adelantado(raiz, remoto, tmp_path):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 10)
    # Sin una base apartada se acepta sin medir la mengua, como antes.
    assert ejecutar([o], AHORA + timedelta(days=1), aceptar_mengua={"v1"}) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada"
    assert "aceptado a mano: matches 40 → 10" in e["ultima_comprobacion"]["detalle"]
    assert e["ultima_buena"]["recuentos"]["matches"] == 10
    # Pero que falte una tabla no se perdona si no se había visto antes.
    _subir(remoto, _base(tmp_path / "sin.db", 10, "DROP TABLE scorers"))
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 1
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["detalle"][0] == "falta la tabla scorers"


def test_aceptar_mengua_perdona_solo_lo_que_tenia_la_apartada(raiz, remoto, tmp_path):
    o = _origen(remoto)
    ejecutar([o], AHORA)
    _subir(remoto, _base(tmp_path / "a.db", 38, "DROP TABLE scorers; DELETE FROM goals"))
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    assert _estado(raiz)["v1"]["ultima_apartada"]["motivos"] == [
        "goals está vacía", "falta la tabla scorers", "mengua: matches 40 → 38", "mengua: goals 1 → 0",
    ]
    # Llega otra con una tabla vacía más: eso no estaba en la apartada y no se perdona.
    _subir(remoto, _base(tmp_path / "b.db", 38, "DROP TABLE scorers; DELETE FROM goals; DELETE FROM teams"))
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 1
    c = _estado(raiz)["v1"]["ultima_comprobacion"]
    assert c["resultado"] == "cuarentena" and c["detalle"][:2] == ["teams está vacía", "mengua: teams 1 → 0"]
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 40
    # Con esa ya apartada, aceptarla perdona lo que tenía, y el detalle lo dice contra la última buena.
    assert ejecutar([o], AHORA + timedelta(days=3), aceptar_mengua={"v1"}) == 0
    c = _estado(raiz)["v1"]["ultima_comprobacion"]
    assert c["resultado"] == "aceptada"
    assert "aceptado a mano: matches 40 → 38; goals 1 → 0; teams 1 → 0; goals está vacía; teams está vacía; falta la tabla scorers" in c["detalle"]
    # Una base dañada no se perdona nunca, ni apartada antes.
    datos = bytearray((remoto / "futbolbase.db").read_bytes())
    datos[4096:8192] = b"\xff" * 4096
    _subir(remoto, bytes(datos))
    assert ejecutar([o], AHORA + timedelta(days=4)) == 1
    assert ejecutar([o], AHORA + timedelta(days=5), aceptar_mengua={"v1"}) == 1
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["detalle"][0].startswith(("integridad:", "no se puede abrir:"))


# Lo que vigilaba la herramienta ya instalada cuando hizo sus primeras copias, antes de match_staff_all.
_TABLAS_DE_ANTES = (
    "matches", "players", "appearances", "goals", "standings", "match_events", "teams", "groups", "scorers",
)


def test_lo_guardado_antes_sigue_sirviendo(raiz, remoto, tmp_path, monkeypatch):
    o = _origen(remoto)
    primera = (remoto / "futbolbase.db").read_bytes()
    # Estado, versión y espejo como los dejó la herramienta instalada: nueve tablas y sin ultima_apartada.
    with monkeypatch.context() as m:
        m.setattr(verificar, "TABLAS", _TABLAS_DE_ANTES)
        assert ejecutar([o], AHORA) == 0
    e = _estado(raiz)["v1"]
    assert sorted(e) == ["ultima_buena", "ultima_comprobacion"]
    assert sorted(e["ultima_buena"]) == ["commit", "momento", "recuentos", "sha256", "version"]
    assert sorted(e["ultima_buena"]["recuentos"]) == sorted(_TABLAS_DE_ANTES)
    vieja, = versiones("v1")
    ficha = json.loads(vieja.ruta.with_name(vieja.ruta.name.removesuffix(".xz") + ".json").read_text())
    assert sorted(ficha) == ["bytes", "recuentos", "sha256"] and sorted(ficha["recuentos"]) == sorted(_TABLAS_DE_ANTES)
    # Con el código de hoy: la misma base, sin cambios; una nueva, aceptada; nunca cuarentena por la tabla nueva.
    assert ejecutar([o], AHORA + timedelta(days=1)) == 0
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["resultado"] == "sin cambios"
    commit_base(remoto, 41)
    assert ejecutar([o], AHORA + timedelta(days=2)) == 0
    e = _estado(raiz)["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada" and e["ultima_buena"]["recuentos"]["match_staff_all"] == 1
    # Y la versión vieja se sigue restaurando.
    assert restaurar("v1", tmp_path / "r", AHORA).read_bytes() == primera


def test_una_cuarentena_de_antes_se_acepta_a_mano(raiz, remoto, monkeypatch):
    o = _origen(remoto)
    with monkeypatch.context() as m:
        m.setattr(verificar, "TABLAS", _TABLAS_DE_ANTES)
        ejecutar([o], AHORA); commit_base(remoto, 10)
        assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    # La herramienta instalada no guardaba la base apartada en estado.json.
    datos = _estado(raiz)
    del datos["v1"]["ultima_apartada"]
    (raiz / "estado.json").write_text(json.dumps(datos), encoding="utf-8")
    assert ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"}) == 0
    c = _estado(raiz)["v1"]["ultima_comprobacion"]
    assert c["resultado"] == "aceptada" and "aceptado a mano: matches 40 → 10" in c["detalle"]


def test_misma_rechazada_no_se_repite(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA); commit_base(remoto, 10)
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    assert ejecutar([o], AHORA + timedelta(days=2)) == 1
    assert len(list((raiz / "cuarentena/v1").glob("*.db.xz"))) == 1
    assert [l.split(" ")[2] for l in _registro(raiz)] == ["aceptada", "cuarentena", "cuarentena"]
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["momento"] == "2026-11-15T05:00:00+00:00"


def test_espejo_incompleto_no_para_la_pasada(raiz, remoto):
    o = _origen(remoto)
    git(remoto, "branch", "claude/arreglo")
    assert ejecutar([o], AHORA) == 0
    git(remoto, "branch", "--quiet", "-D", "claude/arreglo")
    git(remoto, "branch", "claude")
    commit_base(remoto, 41)
    assert ejecutar([o], AHORA + timedelta(days=1)) == 0
    c = _estado(raiz)["v1"]["ultima_comprobacion"]
    assert c["resultado"] == "aceptada" and c["commit"] == git(remoto, "rev-parse", "main")
    assert c["detalle"][-1].startswith("espejo incompleto: git fetch: ") and "refs/heads/claude" in c["detalle"][-1]
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 41
    assert " v1 aceptada matches 41; " in _registro(raiz)[-1] and "; espejo incompleto: " in _registro(raiz)[-1]
    assert estado(AHORA + timedelta(days=1, hours=1))[1] == 0


def _foto(carpeta: Path) -> dict[str, bytes]:
    return {p.relative_to(carpeta).as_posix(): p.read_bytes() for p in carpeta.rglob("*") if p.is_file()}


@pytest.mark.parametrize("todas", [False, True], ids=["solo GIT_DIR", "todas"])
def test_un_git_dir_heredado_no_toca_otro_repositorio(raiz, remoto, tmp_path, monkeypatch, todas):
    o = _origen(remoto)
    ajeno = tmp_path / "ajeno"
    ajeno.mkdir()
    git(ajeno, "init", "--quiet", "--initial-branch=main")
    (ajeno / "f.txt").write_text("ajeno\n")
    git(ajeno, "add", "f.txt")
    git(ajeno, "commit", "--quiet", "-m", "ajeno")
    antes = _foto(ajeno)
    heredadas = {"GIT_DIR": ajeno / ".git"}
    if todas:
        heredadas |= {
            "GIT_WORK_TREE": ajeno, "GIT_INDEX_FILE": ajeno / ".git/index",
            "GIT_OBJECT_DIRECTORY": ajeno / ".git/objects", "GIT_ALTERNATE_OBJECT_DIRECTORIES": ajeno / ".git/objects",
            "GIT_NAMESPACE": "ajeno", "GIT_COMMON_DIR": ajeno / ".git",
        }
    for dia in (0, 1):          # la primera crea el espejo; la segunda lo actualiza
        if dia:
            commit_base(remoto, 41)
        with monkeypatch.context() as m:
            # Como si la orden se lanzase desde un hook de git o un `rebase --exec` de ese otro repositorio.
            for nombre, valor in heredadas.items():
                m.setenv(nombre, str(valor))
            assert ejecutar([o], AHORA + timedelta(days=dia)) == 0
    assert _foto(ajeno) == antes
    espejo = raiz / "repos/v1.git"
    assert sorted(p.name for p in (raiz / "repos").iterdir()) == ["v1.git"]
    assert git(espejo, "rev-parse", "--is-bare-repository") == "true"
    assert git(espejo, "config", "gc.pruneExpire") == "never"
    assert git(espejo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines() == [
        f"refs/copia/main/20261113 {git(remoto, 'rev-parse', 'main~1')}",
        f"refs/copia/main/20261114 {git(remoto, 'rev-parse', 'main')}",
        f"refs/heads/main {git(remoto, 'rev-parse', 'main')}",
    ]
    assert [v.recuentos["matches"] for v in versiones("v1")] == [40, 41]


def test_un_origen_caido_no_para_al_otro(raiz, remoto, tmp_path, monkeypatch):
    caido = _origen(tmp_path / "no-existe", "v2")
    sin_base = _origen(remoto, "v3", base="no-esta.db")      # falla ya con la base a medio sacar
    o = _origen(remoto)
    # El estado se escribe al acabar cada origen, no solo al final de la pasada.
    vistos = []

    def espia(origen, ahora):
        vistos.append(sorted(_estado(raiz)) if (raiz / "estado.json").exists() else [])
        return actualizar_espejo(origen, ahora)

    with monkeypatch.context() as m:
        m.setattr(ejecutar_mod, "actualizar_espejo", espia)
        assert ejecutar([caido, sin_base, o], AHORA) == 1
    assert vistos == [[], ["v2"], ["v2", "v3"]]
    e = _estado(raiz)
    assert e["v1"]["ultima_comprobacion"]["resultado"] == "aceptada"
    assert e["v2"]["ultima_comprobacion"]["resultado"] == "error"
    assert e["v3"]["ultima_comprobacion"]["resultado"] == "error"
    assert "ultima_buena" not in e["v2"] and "ultima_buena" not in e["v3"]
    assert e["v2"]["ultima_comprobacion"]["commit"] is None
    assert e["v3"]["ultima_comprobacion"]["commit"] == git(remoto, "rev-parse", "main")
    assert "no-esta.db" in e["v3"]["ultima_comprobacion"]["detalle"][0]
    assert all(e[n]["ultima_comprobacion"]["detalle"][0] for n in ("v2", "v3"))
    assert [l.split(" ")[1:3] for l in _registro(raiz)] == [["v2", "error"], ["v3", "error"], ["v1", "aceptada"]]
    assert (raiz / "actual/v1/futbolbase.db").exists() and not (raiz / "actual/v3").exists()
    assert _temporales(raiz) == []
    # Si cae el que ya tenía copia, su última buena y su actual siguen como estaban.
    buena, actual = e["v1"]["ultima_buena"], (raiz / "actual/v1/futbolbase.db").read_bytes()
    remoto.rename(tmp_path / "apagado")
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    e = _estado(raiz)
    assert e["v1"]["ultima_comprobacion"]["resultado"] == "error"
    assert e["v1"]["ultima_buena"] == buena
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == actual
    assert e["v2"]["ultima_comprobacion"]["momento"] == "2026-11-13T05:00:00+00:00"   # los demás no se tocan


def test_cualquier_fallo_de_un_origen_es_su_error(raiz, remoto, tmp_path):
    o, otro = _origen(remoto), _origen(remoto, "v2")
    ejecutar([o], AHORA)
    commit_base(remoto, 41)
    # Otra base en el mismo segundo que la versión guardada: almacen no la pisa y lanza FileExistsError.
    assert ejecutar([o, otro], AHORA) == 1
    e = _estado(raiz)
    assert e["v1"]["ultima_comprobacion"]["resultado"] == "error"
    assert e["v1"]["ultima_comprobacion"]["detalle"][0].startswith("FileExistsError: ya hay otra versión de v1")
    assert e["v1"]["ultima_buena"]["recuentos"]["matches"] == 40
    assert e["v2"]["ultima_comprobacion"]["resultado"] == "aceptada"
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 40
    assert _temporales(raiz) == []


def test_cerrojo(raiz, remoto, capsys):
    o = _origen(remoto)
    with open(rutas.raiz() / ".cerrojo", "w") as otra_pasada:
        fcntl.flock(otra_pasada, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert ejecutar([o], AHORA) == 2
        assert sorted(p.name for p in raiz.iterdir()) == [".cerrojo"]
        assert not (raiz / "estado.json").exists()
        assert "cerrojo" in capsys.readouterr().err
    assert ejecutar([o], AHORA) == 0
    # Al acabar la suelta, también cuando la pasada revienta fuera de un origen.
    with open(raiz / ".cerrojo") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (raiz / "estado.json").unlink()
    (raiz / "estado.json").mkdir()
    with pytest.raises(OSError): ejecutar([o], AHORA + timedelta(days=1))
    with open(raiz / ".cerrojo") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_limpia_lo_que_dejo_una_pasada_cortada(raiz, remoto):
    cortada = rutas.raiz() / ".pasada-cortada"
    cortada.mkdir()
    (cortada / "futbolbase.db").write_bytes(b"medio sacada")
    assert ejecutar([_origen(remoto)], AHORA) == 0
    assert _temporales(raiz) == []


def test_una_ficha_danada_no_para_la_copia(raiz, remoto, tmp_path, capsys):
    o = _origen(remoto)
    ejecutar([o], AHORA)
    for dia, partidos in ((1, 41), (2, 42)):
        commit_base(remoto, partidos)
        assert ejecutar([o], AHORA + timedelta(days=dia)) == 0
    vieja, *_ = versiones("v1")
    ficha = vieja.ruta.with_name(vieja.ruta.name.removesuffix(".xz") + ".json")
    ficha.write_text("", encoding="utf-8")
    capsys.readouterr()
    assert [v.recuentos["matches"] for v in versiones("v1")] == [41, 42]
    assert str(ficha) in capsys.readouterr().err
    # La orden lista y restaura las sanas, también la última.
    assert main(["versiones", "v1"]) == 0 and len(capsys.readouterr().out.splitlines()) == 2
    assert main(["restaurar", "v1", str(tmp_path / "r")]) == 0
    restaurada, = (tmp_path / "r").glob("*.db")
    assert restaurada.read_bytes() == (remoto / "futbolbase.db").read_bytes()
    # Y las pasadas siguientes guardan.
    commit_base(remoto, 43)
    assert ejecutar([o], AHORA + timedelta(days=3)) == 0
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["resultado"] == "aceptada"
    assert [v.recuentos["matches"] for v in versiones("v1")] == [41, 42, 43]


def test_limpia_los_ficheros_a_medio_escribir(raiz, remoto):
    o = _origen(remoto)
    assert ejecutar([o], AHORA) == 0
    # Lo que deja una escritura atómica cortada (el temporizador mata la pasada, un apagón): .<destino>.<azar>.tmp
    restos = [
        raiz / ".estado.json.k3j2h1.tmp",
        raiz / "versiones/v1/2026/.futbolbase-20261114-050000.db.xz.k3j2h1.tmp",
        raiz / "actual/v1/.futbolbase.db.k3j2h1.tmp",
        raiz / "volcados/v1/.futbolbase-2026-S47.sql.xz.k3j2h1.tmp",
        raiz / "cuarentena/v1/.futbolbase-20261114-050000.db.xz.k3j2h1.tmp",
    ]
    # Lo que no sigue ese patrón, o está en carpetas que no son de la herramienta, no se toca.
    ajenos = [raiz / "notas.tmp", raiz / ".notas", raiz / "local-v1/.rama.tmp", raiz / "actual/v1/.oculto"]
    for p in restos + ajenos:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"a medio escribir")
    assert ejecutar([o], AHORA + timedelta(hours=1)) == 0
    assert [p for p in restos if p.exists()] == []
    assert all(p.exists() for p in ajenos)


def test_estado(raiz, remoto):
    o = _origen(remoto)
    assert "sin copias" in estado(AHORA)[0] and estado(AHORA)[1] == 1
    ejecutar([o], AHORA)
    texto, codigo = estado(AHORA + timedelta(hours=1)); assert codigo == 0 and "v1" in texto and "40" in texto
    assert estado(AHORA + timedelta(days=4))[1] == 1
    linea, ocupa = texto.splitlines()
    assert linea.startswith("v1") and "matches 40" in linea and "players 1" in linea and "aceptada" in linea
    assert ocupa.startswith("ocupa ") and str(raiz) in ocupa
    # Menos de 3 días.
    assert estado(AHORA + timedelta(days=3) - timedelta(seconds=1))[1] == 0
    texto, codigo = estado(AHORA + timedelta(days=3))
    assert codigo == 1 and "3 días" in texto
    # El último resultado tiene que ser bueno, aunque haya una copia buena de antes.
    commit_base(remoto, 10)
    ejecutar([o], AHORA + timedelta(days=1))
    texto, codigo = estado(AHORA + timedelta(days=1, hours=1))
    assert codigo == 1 and "cuarentena" in texto and "mengua: matches 40 → 10" in texto
    # Y todos los orígenes tienen que tener una copia buena.
    ejecutar([o], AHORA + timedelta(days=2), aceptar_mengua={"v1"})
    assert estado(AHORA + timedelta(days=2, hours=1))[1] == 0
    ejecutar([o, _origen(remoto, "v2", base="no-esta.db")], AHORA + timedelta(days=3))
    texto, codigo = estado(AHORA + timedelta(days=3, hours=1))
    assert codigo == 1 and len(texto.splitlines()) == 3 and "sin copia buena" in texto


def test_estado_con_los_origenes_esperados(raiz, remoto):
    o = _origen(remoto)
    # Antes de la primera pasada, cada origen de origenes.json sale sin copias.
    texto, codigo = estado(AHORA, ["v1", "v2"])
    v1, v2, ocupa = texto.splitlines()
    assert codigo == 1 and ocupa.startswith("ocupa ")
    assert all(l.startswith(f"{n}: sin copias") and "AVISO" in l for n, l in (("v1", v1), ("v2", v2)))
    ejecutar([o], AHORA)
    assert estado(AHORA + timedelta(hours=1), ["v1"])[1] == 0
    # Uno que está en origenes.json y no tiene ninguna pasada (se añadió y no se ha copiado nunca) es un aviso.
    texto, codigo = estado(AHORA + timedelta(hours=1), ["v1", "v2"])
    v1, v2, _ = texto.splitlines()
    assert codigo == 1 and v1.startswith("v1: comprobada ") and "AVISO" not in v1
    assert v2.startswith("v2: sin copias") and "AVISO" in v2
    # Uno que ya no está en origenes.json se sigue mostrando, pero lo suyo no cuenta para el código.
    ejecutar([_origen(remoto, "v9", base="no-esta.db")], AHORA + timedelta(hours=1))
    texto, codigo = estado(AHORA + timedelta(hours=2), ["v1"])
    v1, v9, _ = texto.splitlines()
    assert codigo == 0 and v1.startswith("v1: comprobada ")
    assert v9.startswith("v9 (ya no está en origenes.json): comprobada ") and "(error)" in v9 and "AVISO" in v9
    # Sin saber cuáles se esperan (origenes.json ilegible), cuenta todo lo que hay, como antes.
    assert estado(AHORA + timedelta(hours=2))[1] == 1


def test_estado_perdido_o_atrasado(raiz, remoto):
    o = _origen(remoto)
    ejecutar([o], AHORA)
    buena = _estado(raiz)["v1"]["ultima_buena"]
    # Sin estado.json, la misma base vuelve a dar su última buena, sacada de la versión guardada.
    (raiz / "estado.json").unlink()
    assert ejecutar([o], AHORA + timedelta(days=1)) == 0
    assert _estado(raiz)["v1"]["ultima_buena"] == buena
    assert estado(AHORA + timedelta(days=1, hours=1))[1] == 0
    # Un estado.json de antes de la última versión (la pasada se cortó tras guardarla) se pone al día.
    atrasado = (raiz / "estado.json").read_text(encoding="utf-8")
    commit_base(remoto, 41)
    assert ejecutar([o], AHORA + timedelta(days=2)) == 0
    nueva = _estado(raiz)["v1"]["ultima_buena"]
    (raiz / "estado.json").write_text(atrasado, encoding="utf-8")
    assert ejecutar([o], AHORA + timedelta(days=3)) == 0
    assert _estado(raiz)["v1"]["ultima_buena"] == nueva
    # Con un estado.json ilegible, estado lo dice y la mengua se sigue midiendo contra la última versión guardada.
    (raiz / "estado.json").write_text("no es json", encoding="utf-8")
    texto, codigo = estado(AHORA + timedelta(days=3, hours=1))
    assert codigo == 1 and "ilegible" in texto
    commit_base(remoto, 10)
    assert ejecutar([o], AHORA + timedelta(days=4)) == 1
    assert _estado(raiz)["v1"]["ultima_comprobacion"]["detalle"][0] == "mengua: matches 41 → 10"
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 41
