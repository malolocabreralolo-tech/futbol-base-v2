"""Dónde se guardan las copias en el PC."""

import os
from pathlib import Path


def raiz() -> Path:
    valor = os.environ.get("FB_COPIA_RAIZ")
    ruta = Path(valor) if valor else Path.home() / "backups" / "futbol-base"
    # Las copias llevan datos personales de jugadores: solo el dueño puede entrar.
    ruta.mkdir(mode=0o700, parents=True, exist_ok=True)
    return ruta
