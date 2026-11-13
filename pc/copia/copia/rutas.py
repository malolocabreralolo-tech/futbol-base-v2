"""Dónde se guardan las copias en el PC."""

import os
import stat
from pathlib import Path


def raiz() -> Path:
    valor = os.environ.get("FB_COPIA_RAIZ")
    ruta = Path(valor) if valor else Path.home() / "backups" / "futbol-base"
    # Las copias llevan datos personales de jugadores: solo el dueño puede entrar.
    ruta.mkdir(mode=0o700, parents=True, exist_ok=True)
    # También si la carpeta ya existía de antes con otros permisos.
    if stat.S_IMODE(ruta.stat().st_mode) != 0o700:
        ruta.chmod(0o700)
    return ruta
