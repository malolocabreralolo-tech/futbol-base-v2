"""El instalador: la copia del paquete, el lanzador y las unidades, siempre en un HOME de prueba y sin el systemd real."""

import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import git

PC_COPIA = Path(__file__).resolve().parent.parent
INSTALADA = Path(".local/share/futbol-base-copia")
LANZADOR = Path(".local/bin/futbol-base-copia")
UNIDADES = Path(".config/systemd/user")


def _sin_fbc() -> dict[str, str]:
    # Ni un FBC_* del entorno de quien lanza las pruebas ni acceso al bus del systemd de usuario real.
    quitar = ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    return {k: v for k, v in os.environ.items() if not k.startswith("FBC_") and k not in quitar}


def _instalar(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "instalar.sh"], cwd=PC_COPIA, env=env, capture_output=True, text=True)


def _unidad(ruta: Path) -> configparser.ConfigParser:
    unidad = configparser.ConfigParser(interpolation=None)
    unidad.optionxform = str
    unidad.read_string(ruta.read_text(encoding="utf-8"))
    return unidad


def test_instalar_en_un_home_de_prueba(tmp_path):
    env = {**os.environ, "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1", "FB_COPIA_RAIZ": str(tmp_path / "copias")}
    subprocess.run(["bash", "instalar.sh"], cwd=PC_COPIA, env=env, check=True)
    lanzador = tmp_path / ".local/bin/futbol-base-copia"
    assert os.access(lanzador, os.X_OK)
    assert (tmp_path / ".local/share/futbol-base-copia/copia/ejecutar.py").exists()
    assert (tmp_path / ".local/share/futbol-base-copia/origenes.json").exists()
    assert "Persistent=true" in (tmp_path / ".config/systemd/user/futbol-base-copia.timer").read_text()
    r = subprocess.run([str(lanzador), "estado"], env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "sin copias" in r.stdout


def test_unidades(tmp_path):
    env = {**_sin_fbc(), "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1"}
    assert _instalar(env).returncode == 0
    servicio = _unidad(tmp_path / UNIDADES / "futbol-base-copia.service")["Service"]
    temporizador = _unidad(tmp_path / UNIDADES / "futbol-base-copia.timer")
    assert {
        "Type": "oneshot",
        "ExecStart": "%h/.local/bin/futbol-base-copia ejecutar",
        "TimeoutStartSec": "1800",
        "Nice": "10",
    }.items() <= dict(servicio).items()
    # %h es el HOME del usuario: la orden del servicio es el lanzador que ha escrito el instalador.
    assert os.access(Path(servicio["ExecStart"].split()[0].replace("%h", str(tmp_path))), os.X_OK)
    temporizado = {"OnCalendar": "*-*-* 04:40:00", "Persistent": "true", "RandomizedDelaySec": "600"}
    assert temporizado.items() <= dict(temporizador["Timer"]).items()
    assert temporizador["Install"]["WantedBy"] == "timers.target"
    # Con la sesión de usuario activa sin iniciar sesión (linger), la pasada que se saltó se hace al arrancar el PC.
    assert temporizador["Unit"]["Description"].endswith("(04:40, o al arrancar si se la saltó)")


def test_reinstalar_sustituye_la_copia_entera(tmp_path):
    env = {**_sin_fbc(), "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1", "FB_COPIA_RAIZ": str(tmp_path / "copias")}
    assert _instalar(env).returncode == 0
    instalada = tmp_path / INSTALADA
    # Lo que dejaría una versión anterior y ya no existe en el código: no puede seguir importándose.
    (instalada / "copia" / "viejo.py").write_text("raise SystemExit('módulo viejo')\n")
    (instalada / "copia" / "__pycache__").mkdir(exist_ok=True)
    (instalada / "copia" / "__pycache__" / "viejo.cpython-312.pyc").write_bytes(b"x")
    (instalada / "origenes.json").write_text("{}")
    assert _instalar(env).returncode == 0
    esperados = {f"copia/{p.name}" for p in (PC_COPIA / "copia").glob("*.py")} | {"origenes.json"}
    hay = {p.relative_to(instalada).as_posix() for p in instalada.rglob("*") if p.is_file()}
    assert hay == esperados | {"INSTALADO"}
    for nombre in esperados:
        assert (instalada / nombre).read_bytes() == (PC_COPIA / nombre).read_bytes(), nombre
    # Instalar no hace ninguna copia ni escribe en la carpeta de las copias.
    assert not (tmp_path / "copias").exists() and not (tmp_path / "backups").exists()


def test_reinstalar_no_deja_hueco(tmp_path):
    env = {**_sin_fbc(), "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1"}
    assert _instalar(env).returncode == 0
    instalada = tmp_path / INSTALADA
    # Un rm de mentira apunta lo que borra: la copia instalada no se borra en su sitio (un pasada que arrancase
    # en ese momento no la encontraría), se aparta con un cambio de nombre y se borra después.
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    borrados = tmp_path / "borrados"
    (falsos / "rm").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{borrados}"\nexec {shutil.which("rm")} "$@"\n')
    (falsos / "rm").chmod(0o755)
    (instalada / "copia" / "viejo.py").write_text("raise SystemExit('módulo viejo')\n")
    r = _instalar({**env, "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    assert str(instalada) not in borrados.read_text().splitlines()
    assert [p.name for p in instalada.parent.iterdir()] == ["futbol-base-copia"]
    assert not (instalada / "copia" / "viejo.py").exists()
    assert (instalada / "copia" / "__main__.py").read_bytes() == (PC_COPIA / "copia" / "__main__.py").read_bytes()


def _repo_de_prueba(tmp_path: Path) -> Path:
    # Una copia de pc/copia dentro de un repositorio git de prueba con un solo commit; devuelve su pc/copia.
    repo = tmp_path / "repo"
    aqui = repo / "pc" / "copia"
    shutil.copytree(PC_COPIA / "copia", aqui / "copia", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PC_COPIA / "systemd", aqui / "systemd")
    for nombre in ("instalar.sh", "origenes.json"):
        shutil.copy2(PC_COPIA / nombre, aqui / nombre)
    (repo / "otro.txt").write_text("fuera de pc/copia\n")
    (repo / ".gitignore").write_text("__pycache__/\n")         # como el del repositorio de verdad
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "prueba")
    return aqui


def test_instalado_dice_de_que_commit_es(tmp_path):
    aqui = _repo_de_prueba(tmp_path)
    repo = aqui.parent.parent
    home = tmp_path / "home"
    env = {**_sin_fbc(), "FBC_HOME": str(home), "FBC_SIN_SYSTEMD": "1", "FB_COPIA_RAIZ": str(tmp_path / "copias")}
    commit = git(repo, "rev-parse", "HEAD")
    fecha = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"

    def instalar() -> str:
        r = subprocess.run(["bash", "instalar.sh"], cwd=aqui, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return (home / INSTALADA / "INSTALADO").read_text(encoding="utf-8")

    assert re.fullmatch(rf"commit {commit}, {fecha}\n", instalar())
    # estado lo dice en su última línea.
    r = subprocess.run([str(home / LANZADOR), "estado"], env=env, capture_output=True, text=True)
    assert r.stdout.splitlines()[-1] == f"instalado: {(home / INSTALADA / 'INSTALADO').read_text().strip()}"
    # Lanzado desde el repositorio, donde no hay INSTALADO, no.
    r = subprocess.run([sys.executable, "-m", "copia", "estado"], cwd=aqui, env=env, capture_output=True, text=True)
    assert r.stdout.splitlines()[-1].startswith("ocupa ")
    # Un cambio fuera de pc/copia no cuenta; uno dentro, con commit o sin él (también un fichero nuevo), sí.
    (repo / "otro.txt").write_text("cambiado\n")
    assert re.fullmatch(rf"commit {commit}, {fecha}\n", instalar())
    (aqui / "copia" / "__init__.py").write_text('"""Cambiado."""\n')
    assert re.fullmatch(rf"commit {commit}\+cambios, {fecha}\n", instalar())
    git(repo, "commit", "--quiet", "-am", "otro")
    nuevo = git(repo, "rev-parse", "HEAD")
    assert re.fullmatch(rf"commit {nuevo}, {fecha}\n", instalar())
    (aqui / "nuevo.txt").write_text("sin añadir\n")
    assert re.fullmatch(rf"commit {nuevo}\+cambios, {fecha}\n", instalar())
    # Fuera de un repositorio git se instala igual y lo dice.
    suelta = tmp_path / "suelta"
    shutil.copytree(aqui, suelta)
    r = subprocess.run(["bash", "instalar.sh"], cwd=suelta, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert re.fullmatch(rf"commit desconocido \(no es un repositorio git\), {fecha}\n", (home / INSTALADA / "INSTALADO").read_text())


def test_una_copia_que_no_arranca_no_sustituye_a_la_instalada(tmp_path):
    env = {**_sin_fbc(), "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1"}
    assert _instalar(env).returncode == 0
    instalada = tmp_path / INSTALADA
    antes = {p: p.read_bytes() for p in instalada.rglob("*") if p.is_file()}
    # Un python3 que no arranca el paquete: la instalación se para antes de quitar la que había.
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    (falsos / "python3").write_text("#!/bin/sh\nexit 1\n")
    (falsos / "python3").chmod(0o755)
    r = _instalar({**env, "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode != 0 and "no se ha cambiado nada" in r.stderr
    assert {p: p.read_bytes() for p in instalada.rglob("*") if p.is_file()} == antes
    assert [p.name for p in instalada.parent.iterdir()] == ["futbol-base-copia"]   # sin restos de la nueva


def test_lanzador_desde_cualquier_directorio(remoto, tmp_path):
    home = tmp_path / "home"
    origenes = tmp_path / "origenes.json"
    origenes.write_text(json.dumps({"v1": {"repo": str(remoto), "rama": "main", "base": "futbolbase.db"}}))
    env = {**_sin_fbc(), "FBC_HOME": str(home), "FBC_SIN_SYSTEMD": "1",
           "FB_COPIA_RAIZ": str(tmp_path / "copias"), "FB_COPIA_ORIGENES": str(origenes)}
    assert _instalar(env).returncode == 0
    lanzador = str(home / LANZADOR)
    # Una carpeta con su propio paquete «copia»: el lanzador usa siempre la copia instalada, no la del directorio actual.
    otra = tmp_path / "otra"
    (otra / "copia").mkdir(parents=True)
    (otra / "copia" / "__init__.py").write_text("")
    (otra / "copia" / "__main__.py").write_text("raise SystemExit(7)\n")

    def lanzar(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([lanzador, *args], cwd=otra, env=env, capture_output=True, text=True)

    r = lanzar("ejecutar")
    assert r.returncode == 0 and " v1 aceptada matches 40; " in r.stdout, r.stderr
    assert lanzar("estado").returncode == 0
    # Los argumentos llegan tal cual (con espacios) y los códigos de salida vuelven tal cual.
    r = lanzar("versiones", "otro origen")
    assert r.returncode == 1 and r.stderr == "error: no hay ninguna versión de otro origen\n"
    assert lanzar("restaurar", "v1", "x", "--momento", "ayer").returncode == 2
    # Un destino relativo es relativo a donde está quien lanza la orden.
    r = lanzar("restaurar", "v1", "recuperada")
    restaurada, = (otra / "recuperada").glob("futbolbase-*.db")
    assert r.returncode == 0 and r.stdout.strip() == str(Path("recuperada") / restaurada.name)
    assert restaurada.read_bytes() == (remoto / "futbolbase.db").read_bytes()


def test_systemd_solo_con_el_home_de_verdad(tmp_path):
    # Un systemctl de mentira apunta las llamadas: las pruebas no tocan nunca el systemd del usuario.
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    llamadas = tmp_path / "llamadas"
    systemctl = falsos / "systemctl"
    systemctl.write_text(f'#!/bin/sh\necho "$*" >> "{llamadas}"\n')
    systemctl.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**_sin_fbc(), "HOME": str(home), "PATH": f"{falsos}{os.pathsep}{os.environ['PATH']}"}

    # FBC_HOME por defecto es HOME: instala ahí, recarga systemd y activa solo este temporizador.
    r = _instalar(env)
    assert r.returncode == 0, r.stderr
    assert (home / LANZADOR).is_file() and (home / UNIDADES / "futbol-base-copia.timer").is_file()
    assert llamadas.read_text().splitlines() == ["--user daemon-reload", "--user enable --now futbol-base-copia.timer"]
    assert "futbol-base-copia estado" in r.stdout and "systemctl --user list-timers futbol-base-copia.timer" in r.stdout

    # systemctl --user solo lee las unidades del HOME de verdad: con otro FBC_HOME activaría unas que no ha instalado.
    llamadas.unlink()
    r = _instalar({**env, "FBC_HOME": str(tmp_path / "otro")})
    assert r.returncode != 0 and "FBC_SIN_SYSTEMD=1" in r.stderr
    assert not (tmp_path / "otro").exists() and not llamadas.exists()
