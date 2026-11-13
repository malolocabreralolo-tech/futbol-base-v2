#!/bin/bash
# Instala el reloj del PC de v2: el ejecutable, la copia revisada de scripts/reloj_pasadas.py con su sha de git y el
# temporizador cada 5 min. No lanza nada, no lee el token y no toca nada del reloj de v1 (futbol-base-reloj).
# Volver a ejecutarlo sustituye lo instalado: es lo que hay que hacer tras revisar un cambio de reloj_pasadas.py.
#
#   FBR2_HOME=/otra/carpeta   instala bajo otra carpeta en vez de $HOME (para las pruebas); la copia revisada va,
#                             como la busca el ejecutable, en ${XDG_DATA_HOME:-$FBR2_HOME/.local/share}
#   FBR2_SIN_SYSTEMD=1        no llama a systemctl
set -euo pipefail

aqui=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$aqui/../.." && pwd)
home=${FBR2_HOME:-$HOME}
sin_systemd=${FBR2_SIN_SYSTEMD:-}

if [[ $sin_systemd != 1 && $(realpath -m -- "$home") != "$(realpath -m -- "$HOME")" ]]; then
    # systemctl --user solo lee las unidades del HOME de verdad: activaría otras, no las que se instalan aquí.
    echo "instalar.sh: FBR2_HOME ($home) no es el HOME ($HOME); para instalar en otra carpeta hace falta FBR2_SIN_SYSTEMD=1" >&2
    exit 1
fi

logica=$repo/scripts/reloj_pasadas.py
ejecutable=$aqui/futbol-base-v2-reloj
# La misma regla que el ejecutable (SHARE), con $home haciendo de HOME: si no, con XDG_DATA_HOME definida no la encuentra.
datos=${XDG_DATA_HOME:-$home/.local/share}/futbol-base-v2-reloj
bin=$home/.local/bin
unidades=$home/.config/systemd/user

# Antes de cambiar nada, que lo nuevo funcione: si no, lo instalado sigue como estaba.
if ! bash -n -- "$ejecutable" \
        || ! printf '[]' | env -u GITHUB_OUTPUT python3 -I -- "$logica" > /dev/null 2>&1; then
    echo "instalar.sh: $ejecutable o $logica no funcionan con $(command -v python3 || echo python3); no se ha cambiado nada" >&2
    exit 1
fi
# El sha de blob de git, el mismo que da la API de GitHub para la de main: el reloj los compara para avisar.
sha=$(git -C "$repo" hash-object -- scripts/reloj_pasadas.py)

mkdir -p -- "$datos" "$bin" "$unidades"
temporales=()
trap 'rm -f -- "${temporales[@]}"' EXIT

# pon MODO DESTINO < CONTENIDO: lo escribe al lado y cambia el nombre, para que el reloj no lea nunca uno a medias.
pon() {
    local tmp
    tmp=$(mktemp -- "$(dirname -- "$2")/.$(basename -- "$2").XXXXXX")
    temporales+=("$tmp")
    cat > "$tmp"
    chmod "$1" -- "$tmp"
    mv -f -- "$tmp" "$2"
}

pon 644 "$datos/reloj_pasadas.py" < "$logica"
pon 644 "$datos/reloj_pasadas.sha" <<< "$sha"
pon 755 "$bin/futbol-base-v2-reloj" < "$ejecutable"
pon 644 "$unidades/futbol-base-v2-reloj.service" < "$aqui/systemd/futbol-base-v2-reloj.service"
pon 644 "$unidades/futbol-base-v2-reloj.timer" < "$aqui/systemd/futbol-base-v2-reloj.timer"

if [[ $sin_systemd == 1 ]]; then
    temporizador="sin activar: con FBR2_SIN_SYSTEMD=1 no se llama a systemctl"
else
    systemctl --user daemon-reload
    systemctl --user enable --now futbol-base-v2-reloj.timer
    temporizador="activado, cada 5 min (a y 4, 9, 14…)"
fi

cat <<FIN
Instalado:
  orden:          $bin/futbol-base-v2-reloj
  lógica:         $datos/reloj_pasadas.py (sha ${sha:0:8})
  temporizador:   $unidades/futbol-base-v2-reloj.timer ($temporizador)
  servicio:       $unidades/futbol-base-v2-reloj.service
No se ha lanzado nada. Para comprobarlo:
  systemctl --user list-timers futbol-base-v2-reloj.timer
  journalctl --user -u futbol-base-v2-reloj.service -n 20
Para ver qué decidiría ahora sin lanzar nada: DRY_RUN=1 $bin/futbol-base-v2-reloj
FIN
