import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import commit_base, git
from copia.fuentes import (
    FuenteError, Origen, actualizar_espejo, avisos_del_espejo, cargar_origenes, extraer_base, extraer_fichero,
)

AHORA = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)
ORIGENES = Path(__file__).resolve().parent.parent / "origenes.json"


def _origen(remoto: Path, rama: str = "main") -> Origen:
    return Origen("v1", str(remoto), rama, "futbolbase.db")


def _existe(repo: Path, objeto: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", objeto], capture_output=True).returncode == 0


def _nombres(carpeta: Path) -> list[str]:
    return sorted(p.name for p in carpeta.iterdir())


def _copias(espejo: Path) -> list[str]:
    return git(espejo, "for-each-ref", "--format=%(refname)", "refs/copia").splitlines()


def _reescribir(remoto: Path, partidos: int) -> str:
    # main del remoto pasa a ser un historial huérfano nuevo, con una base de `partidos` partidos.
    git(remoto, "checkout", "--quiet", "--orphan", "huerfana")
    sha = commit_base(remoto, partidos)
    git(remoto, "branch", "--quiet", "-M", "main")
    return sha


def test_cargar_origenes(tmp_path):
    f = tmp_path / "origenes.json"
    f.write_text(json.dumps({"v1": {"repo": "https://x/y.git", "rama": "main", "base": "futbolbase.db"}}))
    assert cargar_origenes(f) == [Origen("v1", "https://x/y.git", "main", "futbolbase.db")]
    # El que se instala junto al paquete.
    assert cargar_origenes(ORIGENES) == [
        Origen("v1", "https://github.com/malolocabreralolo-tech/futbol-base.git", "main", "futbolbase.db")
    ]
    # Un fichero que falta o está mal escrito, o un nombre que no sirve de carpeta, se dicen con FuenteError.
    with pytest.raises(FuenteError): cargar_origenes(tmp_path / "no-hay.json")
    for texto in (
        "no es json",
        '["v1"]',
        '{"v1": {"repo": "https://x/y.git", "rama": "main"}}',
        '{"v1": {"repo": 1, "rama": "main", "base": "futbolbase.db"}}',
        '{"../v1": {"repo": "https://x/y.git", "rama": "main", "base": "futbolbase.db"}}',
    ):
        f.write_text(texto)
        with pytest.raises(FuenteError): cargar_origenes(f)
    # Sin ningún origen no habría nada que copiar y la pasada parecería buena.
    f.write_text("{}")
    with pytest.raises(FuenteError, match="no hay ningún origen"): cargar_origenes(f)


def test_espejo_y_extraer(raiz, remoto, tmp_path, monkeypatch):
    o = _origen(remoto)
    espejo = raiz / "repos/v1.git"
    # Lo que dejó un clon cortado a medias se limpia; lo de otro origen no se toca.
    (raiz / "repos/.v1.git.cortado.tmp/objects").mkdir(parents=True)
    (raiz / "repos/.v2.git.cortado.tmp").mkdir()
    # Mientras git descarga, el nombre definitivo no existe: si lo matan a medias no queda un espejo que parezca bueno.
    durante_la_descarga = []
    run = subprocess.run

    def espia(args, **kwargs):
        r = run(args, **kwargs)
        if "fetch" in args:
            durante_la_descarga.append(espejo.exists())
        return r

    with monkeypatch.context() as m:
        m.setattr(subprocess, "run", espia)
        sha = actualizar_espejo(o, AHORA)
    assert durante_la_descarga == [False, False]        # la rama de la base y luego todo lo demás
    assert sha == git(remoto, "rev-parse", "main")
    assert espejo.is_dir()
    assert _nombres(raiz / "repos") == [".v2.git.cortado.tmp", "v1.git"]
    assert git(espejo, "rev-parse", "--is-bare-repository") == "true"
    # Sin remoto configurado: nada en el espejo puede volcar las referencias del remoto sobre las suyas.
    assert git(espejo, "remote") == ""
    assert git(espejo, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert git(espejo, "config", "gc.pruneExpire") == "never"
    assert extraer_base(o, sha, tmp_path / "x.db").read_bytes() == (remoto / "futbolbase.db").read_bytes()
    assert git(espejo, "rev-parse", "refs/copia/main/20261113") == sha
    assert _copias(espejo) == ["refs/copia/main/20261113"]


def test_segunda_pasada_trae_lo_nuevo(raiz, remoto, tmp_path):
    o = _origen(remoto)
    base_primera = (remoto / "futbolbase.db").read_bytes()
    primero = actualizar_espejo(o, AHORA)
    nuevo = commit_base(remoto, 50)
    assert actualizar_espejo(o, AHORA + timedelta(days=1)) == nuevo
    espejo = raiz / "repos/v1.git"
    assert git(espejo, "rev-parse", "refs/copia/main/20261113") == primero      # la del día anterior sigue
    assert git(espejo, "rev-parse", "refs/copia/main/20261114") == nuevo
    assert extraer_base(o, nuevo, tmp_path / "n.db").read_bytes() == (remoto / "futbolbase.db").read_bytes()
    assert extraer_base(o, primero, tmp_path / "p.db").read_bytes() == base_primera
    # Dos pasadas el mismo día: la referencia del día queda en el commit más nuevo.
    otro = commit_base(remoto, 60)
    assert actualizar_espejo(o, AHORA + timedelta(days=1, hours=6)) == otro
    assert git(espejo, "rev-parse", "refs/copia/main/20261114") == otro
    # El día es el de UTC: la una de la madrugada del 16 en UTC+2 todavía es el 15.
    assert actualizar_espejo(o, datetime(2026, 11, 16, 1, 0, tzinfo=timezone(timedelta(hours=2)))) == otro
    assert _copias(espejo) == ["refs/copia/main/20261113", "refs/copia/main/20261114", "refs/copia/main/20261115"]


def test_reescritura_no_pierde_lo_anterior(raiz, remoto, tmp_path, monkeypatch):
    o = _origen(remoto)
    # Ni aunque la configuración de git del usuario pida podar en cada fetch.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "fetch.prune")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    git(remoto, "branch", "otra")
    base_vieja = (remoto / "futbolbase.db").read_bytes()
    viejo = actualizar_espejo(o, AHORA)
    # main del remoto pasa a ser un historial huérfano nuevo, la otra rama se borra y el remoto tira los objetos viejos.
    git(remoto, "checkout", "--quiet", "--orphan", "nueva")
    commit_base(remoto, 30)
    git(remoto, "branch", "--quiet", "-D", "main", "otra")
    git(remoto, "branch", "--quiet", "-m", "main")
    git(remoto, "reflog", "expire", "--expire=now", "--all")
    git(remoto, "gc", "--quiet", "--prune=now")
    assert not _existe(remoto, viejo)
    nuevo = actualizar_espejo(o, AHORA + timedelta(days=1))
    assert nuevo != viejo and nuevo == git(remoto, "rev-parse", "main")
    espejo = raiz / "repos/v1.git"
    assert _existe(espejo, viejo)
    assert extraer_base(o, viejo, tmp_path / "v.db").read_bytes() == base_vieja
    assert git(espejo, "rev-parse", "refs/copia/main/20261113") == viejo
    assert git(espejo, "rev-parse", "refs/heads/otra") == viejo         # sin --prune, la rama borrada sigue
    # Ni una limpieza a fondo del espejo lo pierde: las referencias lo mantienen alcanzable.
    git(espejo, "gc", "--quiet", "--prune=now")
    assert extraer_base(o, viejo, tmp_path / "v2.db").read_bytes() == base_vieja


def test_el_remoto_no_puede_tocar_refs_copia(raiz, remoto):
    o = _origen(remoto)
    intruso = git(remoto, "commit-tree", "HEAD^{tree}", "-m", "intruso")
    # Una referencia de copia que el remoto ya tenía antes de la primera pasada no entra en el espejo.
    git(remoto, "update-ref", "refs/copia/main/20191231", intruso)
    a = actualizar_espejo(o, AHORA)
    espejo = raiz / "repos/v1.git"
    assert _copias(espejo) == ["refs/copia/main/20261113"]
    # Ni las que crea después, aunque se llamen como una nuestra.
    git(remoto, "update-ref", "refs/copia/main/20261113", intruso)
    git(remoto, "update-ref", "refs/copia/main/20200101", intruso)
    assert actualizar_espejo(o, AHORA + timedelta(hours=1)) == a
    assert git(espejo, "rev-parse", "refs/copia/main/20261113") == a
    assert _copias(espejo) == ["refs/copia/main/20261113"]
    assert not _existe(espejo, intruso)


def test_dos_reescrituras_el_mismo_dia_no_pierden_nada(raiz, remoto):
    o = _origen(remoto)
    ayer = actualizar_espejo(o, AHORA - timedelta(days=1))
    espejo = raiz / "repos/v1.git"
    # Un avance normal el mismo día mueve la referencia del día y no crea ninguna más.
    commit_base(remoto, 45)
    actualizar_espejo(o, AHORA)
    a = commit_base(remoto, 50)
    assert actualizar_espejo(o, AHORA + timedelta(hours=1)) == a
    assert _copias(espejo) == ["refs/copia/main/20261112", "refs/copia/main/20261113"]
    # Dos reescrituras el mismo día: lo que señalaba la referencia del día se guarda aparte antes de moverla.
    b = _reescribir(remoto, 30)
    assert actualizar_espejo(o, AHORA + timedelta(hours=2)) == b
    c = _reescribir(remoto, 20)
    assert actualizar_espejo(o, AHORA + timedelta(hours=3)) == c
    assert git(espejo, "rev-parse", "refs/copia/main/20261113") == c
    assert git(espejo, "rev-parse", f"refs/copia/main/20261113-{a[:12]}") == a
    assert git(espejo, "rev-parse", f"refs/copia/main/20261113-{b[:12]}") == b
    assert git(espejo, "rev-parse", "refs/copia/main/20261112") == ayer       # la de un día pasado no se toca
    assert sorted(_copias(espejo)) == sorted([
        "refs/copia/main/20261112",
        "refs/copia/main/20261113",
        f"refs/copia/main/20261113-{a[:12]}",
        f"refs/copia/main/20261113-{b[:12]}",
    ])
    # Siguen alcanzables: ni una limpieza a fondo del espejo los pierde.
    git(espejo, "gc", "--quiet", "--prune=now")
    assert _existe(espejo, a) and _existe(espejo, b)


def _espiar_git(monkeypatch, llamadas: list[tuple[list[str], dict[str, str]]]) -> None:
    # Apunta en `llamadas` cada llamada a git (sus argumentos y su entorno) y la deja seguir.
    run = subprocess.run

    def espia(args, **kwargs):
        llamadas.append((list(args), dict(kwargs.get("env") or {})))
        return run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", espia)


def _ajustes(args: list[str], orden: str) -> list[str]:
    # Los `-c clave=valor` que van antes de la orden de git.
    previos = args[: args.index(orden)]
    return [previos[i + 1] for i in range(len(previos) - 1) if previos[i] == "-c"]


def test_fetch_sin_gc_en_segundo_plano_y_con_limite_de_velocidad(raiz, remoto, monkeypatch):
    o = _origen(remoto)
    llamadas = []
    with monkeypatch.context() as m:
        _espiar_git(m, llamadas)
        actualizar_espejo(o, AHORA)                             # lo crea
    commit_base(remoto, 41)
    with monkeypatch.context() as m:
        _espiar_git(m, llamadas)
        actualizar_espejo(o, AHORA + timedelta(days=1))         # lo actualiza
    fetches = [args for args, _ in llamadas if "fetch" in args]
    assert len(fetches) == 4
    for args in fetches:
        assert {"gc.autoDetach=false", "http.lowSpeedLimit=1000", "http.lowSpeedTime=120"} <= set(_ajustes(args, "fetch")), args


def test_git_nunca_usa_credenciales(raiz, remoto, tmp_path, monkeypatch):
    o = _origen(remoto)
    # Aunque quien lance la orden tenga un programa que da la contraseña o deje a git preguntarla.
    monkeypatch.setenv("GIT_ASKPASS", "/bin/echo")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    llamadas = []
    with monkeypatch.context() as m:
        _espiar_git(m, llamadas)
        primero = actualizar_espejo(o, AHORA)
    commit_base(remoto, 41)
    with monkeypatch.context() as m:
        _espiar_git(m, llamadas)
        actualizar_espejo(o, AHORA + timedelta(days=1))
        extraer_base(o, primero, tmp_path / "x.db")
        extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json")
    ordenes = {next(a for a in args[1:] if not a.startswith("-") and "=" not in a) for args, _ in llamadas}
    assert {"init", "config", "fetch", "rev-parse", "for-each-ref", "update-ref", "cat-file"} <= ordenes
    for args, env in llamadas:
        assert args[:3] == ["git", "-c", "credential.helper="], args
        assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_ASKPASS"] == "", args


def test_ramas_que_chocan_no_paran_la_base(raiz, remoto, tmp_path):
    o = _origen(remoto)
    git(remoto, "branch", "claude/arreglo")
    viejo = actualizar_espejo(o, AHORA)
    assert avisos_del_espejo(o) == []
    # El remoto borra claude/arreglo y crea claude: en el espejo, que no poda, los dos nombres chocan.
    git(remoto, "branch", "--quiet", "-D", "claude/arreglo")
    git(remoto, "branch", "claude")
    nuevo = commit_base(remoto, 50)
    assert actualizar_espejo(o, AHORA + timedelta(days=1)) == nuevo
    assert extraer_base(o, nuevo, tmp_path / "n.db").read_bytes() == (remoto / "futbolbase.db").read_bytes()
    aviso, = avisos_del_espejo(o)
    assert aviso.startswith("git fetch: ") and "refs/heads/claude" in aviso and "\n" not in aviso
    espejo = raiz / "repos/v1.git"
    assert git(espejo, "rev-parse", "refs/copia/main/20261114") == nuevo
    assert git(espejo, "rev-parse", "refs/heads/claude/arreglo") == viejo        # lo que había no se pierde
    # Cuando deja de chocar, el aviso desaparece y la otra rama llega.
    git(remoto, "branch", "--quiet", "-m", "claude", "otra")
    assert actualizar_espejo(o, AHORA + timedelta(days=2)) == nuevo
    assert avisos_del_espejo(o) == []
    assert git(espejo, "rev-parse", "refs/heads/otra") == viejo


def test_remoto_caido(raiz, remoto, tmp_path):
    o = Origen("v1", str(tmp_path / "no-existe"), "main", "futbolbase.db")
    with pytest.raises(FuenteError): actualizar_espejo(o, AHORA)
    assert not (raiz / "repos").exists() or list((raiz / "repos").iterdir()) == []
    # Un remoto sin la rama pedida tampoco deja un espejo que la pasada siguiente tome por bueno.
    with pytest.raises(FuenteError): actualizar_espejo(_origen(remoto, rama="no-existe"), AHORA)
    assert list((raiz / "repos").iterdir()) == []
    # Un nombre que se saldría de repos/ no llega a usarse.
    with pytest.raises(FuenteError): actualizar_espejo(Origen("../fuera", str(remoto), "main", "futbolbase.db"), AHORA)
    assert _nombres(raiz) == ["repos"]
    # Con el espejo ya hecho, un remoto que pierde la rama o deja de responder da error y el espejo sigue como estaba.
    sha = actualizar_espejo(_origen(remoto), AHORA)
    espejo = raiz / "repos/v1.git"
    git(remoto, "branch", "--quiet", "-m", "main", "master")
    with pytest.raises(FuenteError): actualizar_espejo(_origen(remoto), AHORA + timedelta(days=1))
    remoto.rename(tmp_path / "apagado")
    with pytest.raises(FuenteError): actualizar_espejo(_origen(remoto), AHORA + timedelta(days=1))
    assert git(espejo, "rev-parse", "refs/heads/main") == sha
    assert _copias(espejo) == ["refs/copia/main/20261113"]
    assert extraer_base(_origen(remoto), sha, tmp_path / "x.db").read_bytes() == (tmp_path / "apagado/futbolbase.db").read_bytes()


def test_extraer_fichero(raiz, remoto, tmp_path):
    o = _origen(remoto)
    primero = actualizar_espejo(o, AHORA)
    assert json.loads(extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json").read_text()) == {"a": 1}
    # Sin commit sale de la rama tal como quedó en la última actualización; con commit, de ese commit.
    (remoto / "scripts/x_raw.json").write_text(json.dumps({"a": 2}))
    git(remoto, "commit", "--quiet", "-am", "a vale 2")
    assert json.loads(extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json").read_text()) == {"a": 1}
    actualizar_espejo(o, AHORA + timedelta(days=1))
    assert json.loads(extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json").read_text()) == {"a": 2}
    assert json.loads(extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json", primero).read_text()) == {"a": 1}
    # Lo que no es un fichero del commit, o un origen sin espejo, da FuenteError y no deja nada.
    with pytest.raises(FuenteError): extraer_fichero(o, "scripts/no-esta.json", tmp_path / "n.json")
    with pytest.raises(FuenteError): extraer_fichero(o, "scripts", tmp_path / "n.json")
    with pytest.raises(FuenteError): extraer_fichero(Origen("v2", str(remoto), "main", "futbolbase.db"), "scripts/x_raw.json", tmp_path / "n.json")
    assert _nombres(tmp_path) == ["copias", "remoto", "x.json"]


def test_sin_base_en_el_commit(raiz, remoto, tmp_path):
    o = _origen(remoto)
    git(remoto, "rm", "--quiet", "futbolbase.db")
    git(remoto, "commit", "--quiet", "-m", "sin base")
    sha = actualizar_espejo(o, AHORA)
    with pytest.raises(FuenteError): extraer_base(o, sha, tmp_path / "x.db")
    with pytest.raises(FuenteError): extraer_base(o, "0" * 40, tmp_path / "x.db")    # un commit que no existe
    assert _nombres(tmp_path) == ["copias", "remoto"]
    # Lo que ya hubiera en el destino no se pisa con una extracción fallida.
    (tmp_path / "x.db").write_bytes(b"anterior")
    with pytest.raises(FuenteError): extraer_base(o, sha, tmp_path / "x.db")
    assert (tmp_path / "x.db").read_bytes() == b"anterior"
