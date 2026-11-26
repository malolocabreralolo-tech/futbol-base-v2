"""El reloj del PC de v2 (futbol-base-v2-reloj) y su instalador, sin red, sin el gh de verdad y sin el systemd real.

Un gh de mentira, delante en el PATH, responde con los JSON preparados y apunta cada llamada (sus argumentos y una
huella del token que le llega, nunca el token): así se ve qué se lanzó, contra qué repositorio y con qué token.
"""

import configparser
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PC_RELOJ = Path(__file__).resolve().parent.parent
REPO = PC_RELOJ.parent.parent
EJECUTABLE = PC_RELOJ / "futbol-base-v2-reloj"
LOGICA = REPO / "scripts" / "reloj_pasadas.py"
V2 = "malolocabreralolo-tech/futbol-base-v2"
V1 = "malolocabreralolo-tech/futbol-base"
LANZAR_V2 = ["workflow", "run", "reloj.yml", "-R", V2, "--ref", "main"]
DATOS = Path(".local/share/futbol-base-v2-reloj")
INSTALADO = Path(".local/bin/futbol-base-v2-reloj")
UNIDADES = Path(".config/systemd/user")
# Con otra forma que la de un token de GitHub (gho_ y 36 caracteres), para que ningún escáner lo tome por uno.
TOKEN = "token-de-prueba-no-es-real"
NUEVOS = {
    INSTALADO.as_posix(),
    (DATOS / "reloj_pasadas.py").as_posix(),
    (DATOS / "reloj_pasadas.sha").as_posix(),
    (UNIDADES / "futbol-base-v2-reloj.service").as_posix(),
    (UNIDADES / "futbol-base-v2-reloj.timer").as_posix(),
}
# Lo que tiene el reloj de v1 en el HOME (de mentira): instalar el de v2 no puede cambiar ni un byte.
V1_FICHEROS = {
    ".local/bin/futbol-base-reloj": "#!/bin/bash\n# el reloj de v1, de mentira\n",
    ".local/share/futbol-base-reloj/reloj_pasadas.py": "# la copia revisada de v1, de mentira\n",
    ".local/share/futbol-base-reloj/reloj_pasadas.sha": "0" * 40 + "\n",
    ".local/share/futbol-base-reloj/INSTALLATION.md": "# v1\n",
    ".config/futbol-base-reloj/token": TOKEN + "\n",
    ".config/systemd/user/futbol-base-reloj.service": "[Service]\nType=oneshot\n",
    ".config/systemd/user/futbol-base-reloj.timer": "[Timer]\nOnCalendar=*:02/5 UTC\n",
}

_GH = r'''#!{python}
# gh de mentira: apunta la llamada y responde con lo preparado en respuestas/ (o falla si hay un .fallo).
import hashlib, json, os, pathlib, sys

aqui = pathlib.Path({dir!r})
args = sys.argv[1:]
token = os.environ.get("GH_TOKEN")
with open(aqui / "llamadas.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({{"args": args, "token": hashlib.sha256(token.encode()).hexdigest() if token else None}}) + "\n")


def opcion(nombre):
    return args[args.index(nombre) + 1] if nombre in args and args.index(nombre) + 1 < len(args) else None


if args[:2] == ["workflow", "run"]:
    nombre = "lanzar"
elif args[:2] == ["run", "list"]:
    nombre = {{"update.yml": "pasadas", "reloj.yml": "relojes", "carril-mayores.yml": "carril", "activar.yml": "activar",
              "historico.yml": "historico"}}.get(opcion("--workflow"))
elif args[:1] == ["api"] and len(args) > 1 and args[1].split("?")[0].endswith("/contents/scripts/reloj_pasadas.py"):
    nombre = "contenido"
elif args[:1] == ["api"] and len(args) > 1 and args[1].endswith("/actions/workflows/reloj.yml"):
    nombre = "workflow"
elif args[:1] == ["api"] and len(args) > 1 and args[1].endswith("/actions/variables/CARRIL_MAYORES"):
    nombre = "variable"
else:
    nombre = None
if nombre is None:
    sys.stderr.write(f"gh de mentira: no sé responder a {{args}}\n")
    sys.exit(1)
fallo = aqui / "respuestas" / f"{{nombre}}.fallo"
if fallo.exists():
    sys.stderr.write(fallo.read_text(encoding="utf-8"))
    sys.exit(1)
if nombre == "lanzar":
    sys.exit(0)
respuesta = json.loads((aqui / "respuestas" / f"{{nombre}}.json").read_text(encoding="utf-8"))
jq = opcion("--jq")
print(respuesta[jq[1:]] if jq in (".sha", ".value") else json.dumps(respuesta))
'''


def _sha_de_git(datos: bytes) -> str:
    # El sha de blob de git, el mismo que da la API de GitHub para un fichero (contents: .sha).
    return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _hace(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pasada(hace: timedelta) -> list[dict]:
    # Lo que da `gh run list --workflow update.yml --json number,event,status,conclusion,createdAt,startedAt`.
    return [{"number": 1200, "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
             "createdAt": _hace(hace), "startedAt": _hace(hace)}]


def _entorno_limpio() -> dict[str, str]:
    # Nada del entorno de quien lanza las pruebas que cambie dónde lee el reloj, qué token usa o qué decide; ni el
    # bus del systemd de usuario real.
    fuera = ("FBR2_", "FBR_", "GH_", "GITHUB_")
    quitar = ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "DRY_RUN")
    return {k: v for k, v in os.environ.items() if not k.startswith(fuera) and k not in quitar}


class Entorno:
    """Un HOME de prueba, un token de mentira fuera de él, un gh de mentira delante en el PATH y un TMPDIR propio."""

    def __init__(self, tmp_path: Path, copia: bool = True):
        self.raiz = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.dir_gh = tmp_path / "gh"
        self.respuestas = self.dir_gh / "respuestas"
        self.respuestas.mkdir(parents=True)
        gh = self.dir_gh / "gh"
        gh.write_text(_GH.format(python=sys.executable, dir=str(self.dir_gh)), encoding="utf-8")
        gh.chmod(0o755)
        self.tmpdir = tmp_path / "tmp"
        self.tmpdir.mkdir()
        self.token = tmp_path / "secreto" / "token"
        self.token.parent.mkdir(mode=0o700)
        self.token.write_text(TOKEN + "\n", encoding="utf-8")
        self.token.chmod(0o600)
        self.sha = _sha_de_git(LOGICA.read_bytes())
        if copia:
            datos = self.home / DATOS
            datos.mkdir(parents=True)
            (datos / "reloj_pasadas.py").write_bytes(LOGICA.read_bytes())
            (datos / "reloj_pasadas.sha").write_text(self.sha + "\n", encoding="utf-8")
        self.env = {
            **_entorno_limpio(),
            "HOME": str(self.home),
            "PATH": f"{self.dir_gh}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(self.tmpdir),
            "FBR2_TOKEN_FILE": str(self.token),
        }
        # Por defecto: reloj_pasadas.py igual que en main, reloj.yml activo y sin ejecuciones, la última pasada de
        # hace 10 min (no toca; tampoco el carril, que entra a los 25), sin carril ni activación y la última del
        # histórico de hace 10 min (no toca).
        self.responder("contenido", {"sha": self.sha})
        self.responder("workflow", {"state": "active"})
        self.responder("relojes", [])
        self.responder("pasadas", _pasada(timedelta(minutes=10)))
        self.responder("carril", [])
        self.responder("activar", [])
        self.responder("historico", _pasada(timedelta(minutes=10)))
        self.variable(None)

    def variable(self, valor: str | None) -> None:
        """La variable del repositorio CARRIL_MAYORES: None, sin poner (la API da 404, como gh: «Not Found (HTTP 404)»)."""
        (self.respuestas / "variable.fallo").unlink(missing_ok=True)
        if valor is None:
            self.fallar("variable", "gh: Not Found (HTTP 404)\n")
        else:
            self.responder("variable", {"name": "CARRIL_MAYORES", "value": valor})

    def responder(self, nombre: str, contenido) -> None:
        (self.respuestas / f"{nombre}.json").write_text(json.dumps(contenido), encoding="utf-8")

    def fallar(self, nombre: str, mensaje: str) -> None:
        (self.respuestas / f"{nombre}.fallo").write_text(mensaje, encoding="utf-8")

    def ejecutar(self, programa: Path = EJECUTABLE, quitar: tuple[str, ...] = (), con: tuple[str, ...] = (),
                 **extra: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in {**self.env, **extra}.items() if k not in quitar}
        return subprocess.run([*con, str(programa)], cwd=self.raiz, env=env, capture_output=True, text=True, timeout=60)

    def llamadas(self) -> list[dict]:
        registro = self.dir_gh / "llamadas.jsonl"
        if not registro.exists():
            return []
        return [json.loads(linea) for linea in registro.read_text(encoding="utf-8").splitlines()]

    def lanzamientos(self) -> list[list[str]]:
        return [c["args"] for c in self.llamadas() if c["args"][:2] == ["workflow", "run"]]

    def a_las(self, momento: datetime) -> None:
        """La copia instalada decide como si fuera `momento` (la de verdad usa la hora del PC: el carril y el histórico
        no tocan en las ventanas de partidos, y las pruebas no pueden depender del día en que se pasan). El sha
        instalado sigue siendo el de main: sin AVISO."""
        texto = LOGICA.read_text(encoding="utf-8")
        assert texto.count("datetime.now(timezone.utc)") == 1
        fija = f"datetime({momento.year}, {momento.month}, {momento.day}, {momento.hour}, {momento.minute}, tzinfo=timezone.utc)"
        (self.home / DATOS / "reloj_pasadas.py").write_text(texto.replace("datetime.now(timezone.utc)", fija),
                                                             encoding="utf-8")


@pytest.fixture
def entorno(tmp_path) -> Entorno:
    return Entorno(tmp_path)


def _repositorios(llamada: list[str]) -> set[str]:
    # A qué repositorio va una llamada de gh: el de -R o el de la ruta de la API (repos/<dueño>/<nombre>/...).
    repos = set()
    if "-R" in llamada:
        repos.add(llamada[llamada.index("-R") + 1])
    if llamada[:1] == ["api"]:
        partes = llamada[1].split("/")
        repos.add("/".join(partes[1:3]))
    return repos


# ── Decidir y lanzar ──────────────────────────────────────────────────────────

def test_toca_y_lanza(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "Toca:" in r.stdout and "Lanzado reloj.yml" in r.stdout and "AVISO" not in r.stdout
    assert r.stderr == ""
    assert entorno.lanzamientos() == [LANZAR_V2]
    # Todas las llamadas, al repositorio de v2 y con el token del fichero; ninguna a v1.
    llamadas = entorno.llamadas()
    assert [_repositorios(c["args"]) for c in llamadas] == [{V2}] * len(llamadas)
    assert {c["token"] for c in llamadas} == {_huella(TOKEN)}


def test_no_toca(entorno):
    entorno.responder("pasadas", _pasada(timedelta(minutes=10)))
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "No toca:" in r.stdout
    assert entorno.lanzamientos() == []


def test_reloj_desactivado_no_lanza(entorno):
    # Desactivado a mano en Actions (por ejemplo, durante la primera pasada de v2): ni lanza ni falla.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    entorno.responder("workflow", {"state": "disabled_manually"})
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "No se lanza: reloj.yml está «disabled_manually» en Actions." in r.stdout
    assert entorno.lanzamientos() == []


def test_inactivo_por_github_falla(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    entorno.responder("workflow", {"state": "disabled_inactivity"})
    r = entorno.ejecutar()
    assert r.returncode != 0
    assert f"gh workflow enable reloj.yml -R {V2}" in r.stderr
    assert entorno.lanzamientos() == []


def test_dry_run_no_lanza(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    r = entorno.ejecutar(DRY_RUN="1")
    assert r.returncode == 0, r.stderr
    assert "Toca:" in r.stdout and "DRY_RUN: no se lanza reloj.yml." in r.stdout
    assert entorno.lanzamientos() == []


def test_uno_en_marcha_no_lanza_otro(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    entorno.responder("relojes", [{"status": "in_progress", "conclusion": "", "createdAt": _hace(timedelta(minutes=2))}])
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "No se lanza: ya hay un reloj.yml in_progress, de hace 2 min." in r.stdout
    assert entorno.lanzamientos() == []


def test_aviso_si_reloj_pasadas_cambia_en_main(entorno):
    # Decide igual con la copia instalada (revisada), pero avisa de que la de main es otra.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    entorno.responder("contenido", {"sha": "f" * 40})
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "Lanzado reloj.yml." in r.stdout
    assert "AVISO: reloj_pasadas.py ha cambiado en main (ffffffff)" in r.stdout and "instalar.sh" in r.stdout
    assert entorno.lanzamientos() == [LANZAR_V2]


def test_un_fallo_de_gh_falla_y_no_lanza(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    entorno.fallar("pasadas", "HTTP 404: Not Found\n")
    r = entorno.ejecutar()
    assert r.returncode != 0
    assert "gh run list de update.yml: HTTP 404: Not Found" in r.stderr
    assert entorno.lanzamientos() == []


def test_sin_la_copia_instalada_falla(entorno):
    # La copia revisada está en ${XDG_DATA_HOME:-$HOME/.local/share}/futbol-base-v2-reloj: con otro XDG_DATA_HOME,
    # no la encuentra, lo dice y no lanza nada.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    otra = entorno.raiz / "otra-share"
    r = entorno.ejecutar(XDG_DATA_HOME=str(otra))
    assert r.returncode != 0
    assert str(otra / "futbol-base-v2-reloj" / "reloj_pasadas.py") in r.stderr and "instalar.sh" in r.stderr
    assert entorno.lanzamientos() == []
    # Y en esa carpeta, si está, la usa.
    (otra / "futbol-base-v2-reloj").mkdir(parents=True)
    for nombre in ("reloj_pasadas.py", "reloj_pasadas.sha"):
        (otra / "futbol-base-v2-reloj" / nombre).write_bytes((entorno.home / DATOS / nombre).read_bytes())
    r = entorno.ejecutar(XDG_DATA_HOME=str(otra))
    assert r.returncode == 0 and "Lanzado reloj.yml." in r.stdout, r.stderr


def test_fbr2_repo(entorno):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    r = entorno.ejecutar(FBR2_REPO="pruebas/otro")
    assert r.returncode == 0, r.stderr
    assert entorno.lanzamientos() == [["workflow", "run", "reloj.yml", "-R", "pruebas/otro", "--ref", "main"]]
    assert {frozenset(_repositorios(c["args"])) for c in entorno.llamadas()} == {frozenset({"pruebas/otro"})}


@pytest.mark.parametrize("repo", [V1, V1.upper()])
def test_nunca_el_repositorio_de_v1(entorno, repo):
    # El de v1 tiene su propio reloj, que no se toca: este no le lanza nada ni le pregunta nada.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    r = entorno.ejecutar(FBR2_REPO=repo)
    assert r.returncode != 0 and "v1" in r.stderr
    assert entorno.llamadas() == []


@pytest.mark.parametrize("repo", [
    "github.com/malolocabreralolo-tech/futbol-base",
    "malolocabreralolo-tech/futbol-base.git",
    "MALOLOCABRERALOLO-TECH/Futbol-Base.GIT",
    "https://github.com/malolocabreralolo-tech/futbol-base",
    "pruebas/fútbol",
])
def test_fbr2_repo_solo_con_la_forma_dueno_nombre(entorno, repo):
    # Otra forma del repositorio de v1 (con el servidor, con .git o la URL entera) no se cuela por la guarda: solo
    # vale dueño/nombre, con letras sin tilde, cifras, «.», «_» y «-». No le pregunta ni le lanza nada a nadie.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    r = entorno.ejecutar(FBR2_REPO=repo)
    assert r.returncode != 0 and "FBR2_REPO" in r.stderr and "dueño/nombre" in r.stderr, r.stderr
    assert entorno.llamadas() == []


# ── El token ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("caso", ["inexistente", "vacío", "solo un salto de línea"])
def test_sin_token_falla(entorno, caso):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    token = entorno.raiz / "sin-token"
    if caso == "vacío":
        token.write_text("")
    elif caso == "solo un salto de línea":
        token.write_text("\n")
    r = entorno.ejecutar(FBR2_TOKEN_FILE=str(token))
    assert r.returncode != 0
    assert f"falta el token de GitHub en {token}" in r.stderr
    assert entorno.llamadas() == []


def test_token_por_defecto_el_de_v1(entorno):
    # Sin FBR2_TOKEN_FILE, el mismo fichero que usa el reloj de v1, leído donde está.
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    de_v1 = entorno.home / ".config/futbol-base-reloj/token"
    de_v1.parent.mkdir(parents=True)
    de_v1.write_text("token-de-prueba-de-v1-no-es-real\n")
    r = entorno.ejecutar(quitar=("FBR2_TOKEN_FILE",))
    assert r.returncode == 0, r.stderr
    assert {c["token"] for c in entorno.llamadas()} == {_huella("token-de-prueba-de-v1-no-es-real")}
    assert entorno.lanzamientos() == [LANZAR_V2]


@pytest.mark.parametrize("escenario", ["lanza", "no toca", "desactivado", "inactivo", "fallo de gh", "dry run",
                                       "con bash -x", "con SHELLOPTS=xtrace"])
def test_no_escribe_ni_muestra_el_token(entorno, escenario):
    entorno.responder("pasadas", _pasada(timedelta(hours=3)))
    extra, con = {}, ()
    if escenario == "no toca":
        entorno.responder("pasadas", _pasada(timedelta(minutes=10)))
    elif escenario == "desactivado":
        entorno.responder("workflow", {"state": "disabled_manually"})
    elif escenario == "inactivo":
        entorno.responder("workflow", {"state": "disabled_inactivity"})
    elif escenario == "fallo de gh":
        entorno.fallar("lanzar", "HTTP 401: Bad credentials\n")
    elif escenario == "dry run":
        extra["DRY_RUN"] = "1"
    elif escenario == "con bash -x":
        con = ("bash", "-x")            # quien lo depure así: la traza enseñaría cada asignación y cada orden
    elif escenario == "con SHELLOPTS=xtrace":
        extra["SHELLOPTS"] = "xtrace"
    antes = entorno.token.stat()
    r = entorno.ejecutar(con=con, **extra)
    despues = entorno.token.stat()
    if escenario == "fallo de gh":
        assert r.returncode != 0 and "gh workflow run reloj.yml: HTTP 401: Bad credentials" in r.stderr
    # El fichero del token, intacto: el mismo contenido, permisos y fecha.
    assert entorno.token.read_text(encoding="utf-8") == TOKEN + "\n"
    assert (despues.st_mode, despues.st_mtime_ns, despues.st_ino) == (antes.st_mode, antes.st_mtime_ns, antes.st_ino)
    # Ni en la salida, ni en los errores, ni en los argumentos de gh; a gh le llega por su entorno.
    assert TOKEN not in r.stdout and TOKEN not in r.stderr
    llamadas = entorno.llamadas()
    assert llamadas and all(TOKEN not in " ".join(c["args"]) for c in llamadas)
    assert {c["token"] for c in llamadas} == {_huella(TOKEN)}
    # Ni copiado en ningún sitio: solo está en su fichero; y la carpeta temporal del reloj se ha borrado.
    con_token = [p for p in entorno.raiz.rglob("*") if p.is_file() and TOKEN.encode() in p.read_bytes()]
    assert con_token == [entorno.token]
    assert list(entorno.tmpdir.iterdir()) == []


# ── El instalador ─────────────────────────────────────────────────────────────

def _systemctl_de_mentira(raiz: Path) -> tuple[Path, Path]:
    # Apunta las llamadas: las pruebas no tocan nunca el systemd del usuario.
    falsos = raiz / "falsos"
    falsos.mkdir()
    llamadas = raiz / "systemctl.llamadas"
    systemctl = falsos / "systemctl"
    systemctl.write_text(f'#!/bin/sh\necho "$*" >> "{llamadas}"\n')
    systemctl.chmod(0o755)
    return falsos, llamadas


def _env_instalar(tmp_path: Path, **extra: str) -> dict[str, str]:
    # Con HOME en otra carpeta de prueba, vacía: si el instalador escribiese en $HOME y no en FBR2_HOME, se vería ahí
    # y no en el HOME de verdad.
    otro = tmp_path / "home-de-quien-instala"
    otro.mkdir(exist_ok=True)
    return {**_entorno_limpio(), "HOME": str(otro), "FBR2_SIN_SYSTEMD": "1", **extra}


def _instalar(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "instalar.sh"], cwd=PC_RELOJ, env=env, capture_output=True, text=True, timeout=60)


def _ficheros(carpeta: Path) -> dict[str, bytes]:
    return {p.relative_to(carpeta).as_posix(): p.read_bytes() for p in carpeta.rglob("*") if p.is_file()}


def _unidad(ruta: Path) -> configparser.ConfigParser:
    unidad = configparser.ConfigParser(interpolation=None)
    unidad.optionxform = str
    unidad.read_string(ruta.read_text(encoding="utf-8"))
    return unidad


def test_instalar_en_un_home_de_prueba(tmp_path):
    e = Entorno(tmp_path, copia=False)
    falsos, systemctl = _systemctl_de_mentira(tmp_path)
    for nombre, contenido in V1_FICHEROS.items():
        (e.home / nombre).parent.mkdir(parents=True, exist_ok=True)
        (e.home / nombre).write_text(contenido, encoding="utf-8")
    v1_antes = {n: (e.home / n).stat().st_mtime_ns for n in V1_FICHEROS}
    env = _env_instalar(tmp_path, FBR2_HOME=str(e.home), PATH=f"{falsos}{os.pathsep}{os.environ['PATH']}")
    r = _instalar(env)
    assert r.returncode == 0, r.stderr
    assert not systemctl.exists()
    assert list((tmp_path / "home-de-quien-instala").iterdir()) == []

    # Lo nuevo, y solo eso; lo de v1, ni un byte cambiado.
    hay = _ficheros(e.home)
    assert set(hay) == set(V1_FICHEROS) | NUEVOS
    for nombre, contenido in V1_FICHEROS.items():
        assert hay[nombre] == contenido.encode(), nombre
        assert (e.home / nombre).stat().st_mtime_ns == v1_antes[nombre], nombre
    assert os.access(e.home / INSTALADO, os.X_OK)
    assert hay[INSTALADO.as_posix()] == EJECUTABLE.read_bytes()
    assert hay[(DATOS / "reloj_pasadas.py").as_posix()] == LOGICA.read_bytes()
    # El sha de git de la copia, el que da la API de GitHub para la de main.
    git = subprocess.run(["git", "-C", str(REPO), "hash-object", "scripts/reloj_pasadas.py"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert hay[(DATOS / "reloj_pasadas.sha").as_posix()].decode() == f"{git}\n" == f"{e.sha}\n"
    assert "OnCalendar=*:04/5 UTC" in (e.home / UNIDADES / "futbol-base-v2-reloj.timer").read_text()
    assert (e.home / UNIDADES / "futbol-base-v2-reloj.service").read_bytes() == \
        (PC_RELOJ / "systemd" / "futbol-base-v2-reloj.service").read_bytes()
    assert "FBR2_SIN_SYSTEMD=1" in r.stdout

    # Lo instalado funciona junto: el ejecutable encuentra su copia y lee el token de v1 donde está (sin copiarlo).
    e.responder("pasadas", _pasada(timedelta(hours=3)))
    r = e.ejecutar(programa=e.home / INSTALADO, quitar=("FBR2_TOKEN_FILE",))
    assert r.returncode == 0, r.stderr
    assert "Lanzado reloj.yml." in r.stdout and "AVISO" not in r.stdout
    assert e.lanzamientos() == [LANZAR_V2]
    assert {c["token"] for c in e.llamadas()} == {_huella(TOKEN)}
    assert _ficheros(e.home) == hay


def test_instalar_con_xdg_data_home(tmp_path):
    # Con XDG_DATA_HOME definida, el instalador deja la copia revisada donde la busca el ejecutable: los dos, en
    # ${XDG_DATA_HOME:-$HOME/.local/share}/futbol-base-v2-reloj (en el instalador, FBR2_HOME hace de HOME).
    e = Entorno(tmp_path, copia=False)
    xdg = tmp_path / "xdg-data"
    r = _instalar(_env_instalar(tmp_path, FBR2_HOME=str(e.home), XDG_DATA_HOME=str(xdg)))
    assert r.returncode == 0, r.stderr
    assert (xdg / "futbol-base-v2-reloj" / "reloj_pasadas.py").read_bytes() == LOGICA.read_bytes()
    assert not (e.home / DATOS).exists()
    e.responder("pasadas", _pasada(timedelta(hours=3)))
    r = e.ejecutar(programa=e.home / INSTALADO, XDG_DATA_HOME=str(xdg))
    assert r.returncode == 0, r.stderr
    assert "Lanzado reloj.yml." in r.stdout and "AVISO" not in r.stdout
    assert e.lanzamientos() == [LANZAR_V2]


def test_unidades(tmp_path):
    home = tmp_path / "home"
    assert _instalar(_env_instalar(tmp_path, FBR2_HOME=str(home))).returncode == 0
    servicio = _unidad(home / UNIDADES / "futbol-base-v2-reloj.service")["Service"]
    temporizador = _unidad(home / UNIDADES / "futbol-base-v2-reloj.timer")
    assert dict(servicio) == {"Type": "oneshot", "ExecStart": "%h/.local/bin/futbol-base-v2-reloj", "TimeoutStartSec": "120"}
    # %h es el HOME del usuario: la orden del servicio es el ejecutable que ha puesto el instalador.
    assert os.access(Path(servicio["ExecStart"].replace("%h", str(home))), os.X_OK)
    # A y 4, 9, 14…: dos minutos después del de v1 (a y 2, 7, 12…), para no lanzar los dos a la vez.
    assert dict(temporizador["Timer"]) == {"OnCalendar": "*:04/5 UTC", "RandomizedDelaySec": "30", "AccuracySec": "30s"}
    assert temporizador["Install"]["WantedBy"] == "timers.target"
    assert "v2" in temporizador["Unit"]["Description"] and "v2" in _unidad(home / UNIDADES / "futbol-base-v2-reloj.service")["Unit"]["Description"]


def test_reinstalar_sustituye_la_copia(tmp_path):
    home = tmp_path / "home"
    env = _env_instalar(tmp_path, FBR2_HOME=str(home))
    assert _instalar(env).returncode == 0
    (home / DATOS / "reloj_pasadas.py").write_text("# una copia vieja\n")
    (home / DATOS / "reloj_pasadas.sha").write_text("0" * 40 + "\n")
    (home / INSTALADO).write_text("#!/bin/bash\nexit 7\n")
    assert _instalar(env).returncode == 0
    hay = _ficheros(home)
    assert set(hay) == NUEVOS
    assert hay[(DATOS / "reloj_pasadas.py").as_posix()] == LOGICA.read_bytes()
    assert hay[(DATOS / "reloj_pasadas.sha").as_posix()].decode() == _sha_de_git(LOGICA.read_bytes()) + "\n"
    assert hay[INSTALADO.as_posix()] == EJECUTABLE.read_bytes()


def test_una_copia_que_no_decide_no_sustituye_a_la_instalada(tmp_path):
    home = tmp_path / "home"
    env = _env_instalar(tmp_path, FBR2_HOME=str(home))
    assert _instalar(env).returncode == 0
    antes = _ficheros(home)
    # Un python3 con el que reloj_pasadas.py no decide: la instalación se para sin cambiar nada.
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    (falsos / "python3").write_text("#!/bin/sh\nexit 1\n")
    (falsos / "python3").chmod(0o755)
    r = _instalar({**env, "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode != 0 and "no se ha cambiado nada" in r.stderr
    assert _ficheros(home) == antes


def test_systemd_solo_con_el_home_de_verdad(tmp_path):
    falsos, llamadas = _systemctl_de_mentira(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    env = {**_entorno_limpio(), "HOME": str(home), "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"}

    # FBR2_HOME por defecto es HOME: instala ahí, recarga systemd y activa solo este temporizador.
    r = _instalar(env)
    assert r.returncode == 0, r.stderr
    assert set(_ficheros(home)) == NUEVOS
    assert llamadas.read_text().splitlines() == ["--user daemon-reload", "--user enable --now futbol-base-v2-reloj.timer"]
    assert "systemctl --user list-timers futbol-base-v2-reloj.timer" in r.stdout

    # systemctl --user solo lee las unidades del HOME de verdad: con otro FBR2_HOME activaría unas que no ha instalado.
    llamadas.unlink()
    r = _instalar({**env, "FBR2_HOME": str(tmp_path / "otro")})
    assert r.returncode != 0 and "FBR2_SIN_SYSTEMD=1" in r.stderr
    assert not (tmp_path / "otro").exists() and not llamadas.exists()


# ── El carril de las mayores y el histórico ───────────────────────────────────
#
# Los ticks del cron de reloj.yml casi no llegan: si este reloj solo lanzara reloj.yml cuando toca una pasada del bot,
# el carril de las mayores (que entra entre los 25 y los 75 min de una) y el histórico (cada 3 h) casi nunca tendrían
# un tick en el que decidirse. Con due=false mira también due_carril y due_historico con la misma copia instalada; si
# toca uno, lanza reloj.yml como siempre. Un fallo de esa parte no es un fallo del reloj: se apunta y sale con 0.

MARTES = datetime(2026, 12, 1, 10, 40, tzinfo=timezone.utc)      # martes, 10:40 en Canarias (UTC+0): sin ventanas
SABADO = datetime(2026, 12, 5, 12, 0, tzinfo=timezone.utc)       # sábado, 12:00: ventana de partidos
LISTAS = ["carril-mayores.yml", "activar.yml", "historico.yml"]


def _ejecucion(momento: datetime, numero: int = 1, status: str = "completed") -> dict:
    texto = momento.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": numero, "event": "workflow_dispatch", "status": status,
            "conclusion": "success" if status == "completed" else "", "createdAt": texto, "startedAt": texto}


def _preparar(entorno: Entorno, ahora: datetime = MARTES, bot: int = 10, historico: int | None = 60,
              variable: str | None = "1") -> None:
    """A la hora `ahora`: la última pasada del bot, de hace `bot` min; la del histórico, de hace `historico` min (None:
    ninguna); sin ejecuciones del carril ni de la activación; y CARRIL_MAYORES a `variable` (por defecto, encendido;
    None, sin poner)."""
    entorno.a_las(ahora)
    entorno.variable(variable)
    entorno.responder("pasadas", [_ejecucion(ahora - timedelta(minutes=bot), 1200)])
    entorno.responder("historico", [] if historico is None else [_ejecucion(ahora - timedelta(minutes=historico), 40)])


def _otro(entorno: Entorno, nombre: str) -> Entorno:
    """Otro entorno, en su carpeta, para un segundo caso en la misma prueba."""
    (entorno.raiz / nombre).mkdir()
    return Entorno(entorno.raiz / nombre)


def _listados(entorno: Entorno) -> list[str]:
    return [c["args"][c["args"].index("--workflow") + 1] for c in entorno.llamadas() if c["args"][:2] == ["run", "list"]]


def test_con_due_true_las_mismas_llamadas_que_siempre(entorno):
    """Si toca la pasada del bot, nada de lo nuevo: ni una lista de más, y la misma línea de siempre."""
    _preparar(entorno, bot=180)
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    llamadas = [c["args"] for c in entorno.llamadas()]
    assert llamadas == [
        ["api", f"repos/{V2}/contents/scripts/reloj_pasadas.py?ref=main", "--jq", ".sha"],
        ["run", "list", "-R", V2, "--workflow", "update.yml", "--limit", "20",
         "--json", "number,event,status,conclusion,createdAt,startedAt"],
        ["api", f"repos/{V2}/actions/workflows/reloj.yml"],
        ["run", "list", "-R", V2, "--workflow", "reloj.yml", "--limit", "10", "--json", "status,conclusion,createdAt"],
        LANZAR_V2,
    ], llamadas
    lineas = r.stdout.splitlines()
    assert len(lineas) == 1 and lineas[0].startswith("01/12/2026 10:40 en Canarias") \
        and lineas[0].endswith(". Lanzado reloj.yml.") and "Carril" not in r.stdout, r.stdout


def test_toca_el_carril_y_lanza(entorno):
    _preparar(entorno, bot=30)
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert entorno.lanzamientos() == [LANZAR_V2]
    assert _listados(entorno) == ["update.yml", *LISTAS, "reloj.yml"]
    assert [f"repos/{V2}/actions/variables/CARRIL_MAYORES", "--jq", ".value"] in [c["args"][1:] for c in entorno.llamadas()]
    assert "No toca:" in r.stdout and "Carril de las categorías mayores: toca:" in r.stdout, r.stdout
    assert r.stdout.rstrip().endswith("Lanzado reloj.yml.") and len(r.stdout.splitlines()) == 1, r.stdout


def test_toca_el_historico_y_lanza(entorno):
    _preparar(entorno, bot=10, historico=None)
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert entorno.lanzamientos() == [LANZAR_V2]
    assert "Carril del histórico: toca: no hay ninguna ejecución de historico.yml." in r.stdout, r.stdout
    assert "Carril de las categorías mayores" not in r.stdout and r.stdout.rstrip().endswith("Lanzado reloj.yml.")


def test_no_toca_ninguno_la_linea_de_siempre(entorno):
    """Ni la pasada, ni el carril, ni el histórico: no lanza, y la línea es la de siempre (solo la decisión del bot)."""
    _preparar(entorno, bot=10, historico=60)
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert entorno.lanzamientos() == []
    lineas = r.stdout.splitlines()
    assert len(lineas) == 1 and lineas[0].startswith("01/12/2026 10:40 en Canarias") and "No toca:" in lineas[0]
    assert "Carril" not in r.stdout and "No se pudo" not in r.stdout and lineas[0].endswith("(toca a partir de los 110)."), r.stdout
    # En una ventana de partidos, tampoco (ni el carril ni el histórico corren en ellas).
    entorno2 = _otro(entorno, "sabado")
    _preparar(entorno2, ahora=SABADO, bot=30, historico=None)
    r = entorno2.ejecutar()
    assert r.returncode == 0 and entorno2.lanzamientos() == [] and "Carril" not in r.stdout, r.stdout


def test_un_fallo_de_la_parte_nueva_no_es_un_fallo_del_reloj(entorno):
    """carril-mayores.yml aún no está en main (404): no se mira el carril (y se dice), sale con 0, y el histórico se
    decide igual con lo que hay."""
    _preparar(entorno, bot=30, historico=None)
    entorno.fallar("carril", "HTTP 404: Not Found\n")
    r = entorno.ejecutar()
    assert r.returncode == 0 and r.stderr == "", r.stderr
    assert "No se pudo mirar el carril: gh run list de carril-mayores.yml: HTTP 404: Not Found." in r.stdout, r.stdout
    assert "Carril del histórico: toca" in r.stdout and entorno.lanzamientos() == [LANZAR_V2]
    # Sin histórico que lanzar: no lanza nada, lo dice y sale con 0.
    entorno2 = _otro(entorno, "dos")
    _preparar(entorno2, bot=30, historico=60)
    entorno2.fallar("carril", "HTTP 404: Not Found\n")
    r = entorno2.ejecutar()
    assert r.returncode == 0 and entorno2.lanzamientos() == [], r.stderr
    assert "No toca:" in r.stdout and "No se pudo mirar el carril: gh run list de carril-mayores.yml" in r.stdout
    # La lista del histórico la que falla: el carril se decide igual (y lanza); el histórico, no.
    entorno3 = _otro(entorno, "tres")
    _preparar(entorno3, bot=30, historico=None)
    entorno3.fallar("historico", "HTTP 502: Bad Gateway\n")
    r = entorno3.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "No se pudo mirar el carril: gh run list de historico.yml: HTTP 502: Bad Gateway." in r.stdout, r.stdout
    assert "No se pudo mirar el histórico: gh run list de historico.yml: HTTP 502: Bad Gateway." in r.stdout
    assert entorno3.lanzamientos() == []


_COPIA_SIN_CARRIL = """import os, sys
# Una copia de antes del carril: solo el modo de siempre.
if sys.argv[1:]:
    print("uso: reloj_pasadas.py [--now FECHA_ISO] < ejecuciones.json", file=sys.stderr)
    sys.exit(2)
sys.stdin.read()
print("No toca: la copia vieja.")
open(os.environ["GITHUB_OUTPUT"], "a").write("due=false\\n")
"""
_COPIA_SIN_HISTORICO = """import runpy, sys
# Una copia con el carril y sin el modo del histórico.
if "--historico" in sys.argv:
    print("uso: reloj_pasadas.py [--now FECHA_ISO] [--carril …] < ejecuciones.json", file=sys.stderr)
    sys.exit(2)
sys.argv[0] = {real!r}
runpy.run_path({real!r}, run_name="__main__")
"""


@pytest.mark.parametrize("copia", ["sin carril", "sin histórico"])
def test_una_copia_instalada_antigua_no_es_un_fallo(entorno, copia):
    _preparar(entorno, bot=30, historico=None)
    datos = entorno.home / DATOS
    if copia == "sin carril":
        (datos / "reloj_pasadas.py").write_text(_COPIA_SIN_CARRIL, encoding="utf-8")
    else:
        (datos / "real.py").write_bytes((datos / "reloj_pasadas.py").read_bytes())
        (datos / "reloj_pasadas.py").write_text(_COPIA_SIN_HISTORICO.format(real=str(datos / "real.py")), encoding="utf-8")
    r = entorno.ejecutar()
    assert r.returncode == 0 and r.stderr == "", r.stderr
    vieja = "la copia instalada de reloj_pasadas.py no conoce {}: revísala y vuelve a ejecutar pc/reloj/instalar.sh"
    assert vieja.format("--historico") in r.stdout, r.stdout
    if copia == "sin carril":
        assert vieja.format("--carril") in r.stdout and entorno.lanzamientos() == []
    else:
        assert "Carril de las categorías mayores: toca" in r.stdout and entorno.lanzamientos() == [LANZAR_V2]


def test_dry_run_dice_que_habria_lanzado_por_el_carril(entorno):
    _preparar(entorno, bot=30)
    r = entorno.ejecutar(DRY_RUN="1")
    assert r.returncode == 0, r.stderr
    assert "Carril de las categorías mayores: toca:" in r.stdout and "DRY_RUN: no se lanza reloj.yml." in r.stdout
    assert entorno.lanzamientos() == []


def test_carril_e_historico_respetan_el_bloqueo_de_reloj_yml(entorno):
    """Lo mismo que con la pasada: con un reloj.yml en marcha de hace menos de 30 min, no lanza otro."""
    _preparar(entorno, bot=30)
    entorno.responder("relojes", [{"status": "in_progress", "conclusion": "", "createdAt": _hace(timedelta(minutes=2))}])
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert "Carril de las categorías mayores: toca" in r.stdout and "No se lanza: ya hay un reloj.yml in_progress" in r.stdout
    assert entorno.lanzamientos() == []


@pytest.mark.parametrize("escenario", ["carril", "histórico", "falla carril-mayores", "copia sin histórico", "dry run"])
def test_la_parte_nueva_no_muestra_el_token(entorno, escenario):
    _preparar(entorno, bot=30 if escenario != "histórico" else 10, historico=None)
    extra = {}
    if escenario == "falla carril-mayores":
        entorno.fallar("carril", "HTTP 404: Not Found\n")
    elif escenario == "copia sin histórico":
        datos = entorno.home / DATOS
        (datos / "real.py").write_bytes((datos / "reloj_pasadas.py").read_bytes())
        (datos / "reloj_pasadas.py").write_text(_COPIA_SIN_HISTORICO.format(real=str(datos / "real.py")), encoding="utf-8")
    elif escenario == "dry run":
        extra["DRY_RUN"] = "1"
    r = entorno.ejecutar(**extra)
    assert r.returncode == 0, r.stderr
    assert TOKEN not in r.stdout and TOKEN not in r.stderr
    llamadas = entorno.llamadas()
    assert len(_listados(entorno)) >= 4 and all(TOKEN not in " ".join(c["args"]) for c in llamadas)
    assert {c["token"] for c in llamadas} == {_huella(TOKEN)}
    con_token = [p for p in entorno.raiz.rglob("*") if p.is_file() and TOKEN.encode() in p.read_bytes()]
    assert con_token == [entorno.token]
    assert list(entorno.tmpdir.iterdir()) == []


# ── El carril, solo con CARRIL_MAYORES a 1 ────────────────────────────────────
#
# Como reloj.yml: sin la variable (404) o con otro valor, el carril ni se mira ni se nombra, y ningún reloj.yml se lanza
# por él (si no, con el carril apagado, uno en cada tick de su hueco: ~120 al día en vano). El histórico, igual.

@pytest.mark.parametrize("variable", [None, "0", "", "true"])
def test_con_el_carril_apagado_ni_se_mira_ni_se_lanza(entorno, variable):
    _preparar(entorno, bot=30, historico=60, variable=variable)      # el hueco del carril: tocaría
    r = entorno.ejecutar()
    assert r.returncode == 0 and r.stderr == "", r.stderr
    assert entorno.lanzamientos() == []
    lineas = r.stdout.splitlines()
    assert len(lineas) == 1 and "No toca:" in lineas[0] and lineas[0].endswith("(toca a partir de los 110)."), r.stdout
    assert "Carril" not in r.stdout and "CARRIL_MAYORES" not in r.stdout and "No se pudo" not in r.stdout
    # Y el histórico, aun así: sin ninguna ejecución suya, toca y lanza.
    otro = _otro(entorno, "historico")
    _preparar(otro, bot=30, historico=None, variable=variable)
    r = otro.ejecutar()
    assert r.returncode == 0 and otro.lanzamientos() == [LANZAR_V2], r.stderr
    assert "Carril del histórico: toca" in r.stdout and "Carril de las categorías mayores" not in r.stdout, r.stdout


def test_con_el_carril_apagado_y_carril_mayores_yml_sin_estar_no_dice_nada(entorno):
    """Apagado y sin carril-mayores.yml en main (404): el histórico se decide sin esa lista, y nada del carril."""
    _preparar(entorno, bot=30, historico=None, variable=None)
    entorno.fallar("carril", "HTTP 404: Not Found\n")
    r = entorno.ejecutar()
    assert r.returncode == 0 and entorno.lanzamientos() == [LANZAR_V2], r.stderr
    assert "Carril del histórico: toca" in r.stdout and "carril-mayores" not in r.stdout and "No se pudo" not in r.stdout


def test_si_la_variable_no_se_lee_el_carril_va_apagado_y_se_dice(entorno):
    _preparar(entorno, bot=30, historico=None)
    entorno.fallar("variable", "HTTP 403: Resource not accessible by personal access token\n")
    r = entorno.ejecutar()
    assert r.returncode == 0 and r.stderr == "", r.stderr
    assert "No se pudo leer la variable CARRIL_MAYORES: HTTP 403: Resource not accessible by personal access token." \
        in r.stdout, r.stdout
    assert "Carril de las categorías mayores" not in r.stdout and "Carril del histórico: toca" in r.stdout
    assert entorno.lanzamientos() == [LANZAR_V2]
    # Sin histórico que lanzar: no lanza, lo dice y sale con 0.
    otro = _otro(entorno, "sin-historico")
    _preparar(otro, bot=30, historico=60)
    otro.fallar("variable", "HTTP 403: Forbidden\n")
    r = otro.ejecutar()
    assert r.returncode == 0 and otro.lanzamientos() == [] and "No se pudo leer la variable CARRIL_MAYORES" in r.stdout


@pytest.mark.parametrize("variable", ["1", None, "falla"])
def test_la_variable_no_muestra_el_token(entorno, variable):
    _preparar(entorno, bot=30, historico=None, variable=None if variable == "falla" else variable)
    if variable == "falla":
        entorno.fallar("variable", "HTTP 403: Forbidden\n")
    r = entorno.ejecutar()
    assert r.returncode == 0, r.stderr
    assert TOKEN not in r.stdout and TOKEN not in r.stderr
    llamadas = entorno.llamadas()
    assert any("CARRIL_MAYORES" in " ".join(c["args"]) for c in llamadas)
    assert all(TOKEN not in " ".join(c["args"]) for c in llamadas) and {c["token"] for c in llamadas} == {_huella(TOKEN)}
    assert [p for p in entorno.raiz.rglob("*") if p.is_file() and TOKEN.encode() in p.read_bytes()] == [entorno.token]
    assert list(entorno.tmpdir.iterdir()) == []
