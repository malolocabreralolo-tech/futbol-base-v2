#!/bin/bash
# Instala la copia de seguridad de futbol-base en el PC: el paquete, el lanzador y el temporizador diario.
# No hace ninguna copia ni escribe en ~/backups. Volver a ejecutarlo sustituye entera la copia instalada.
#
#   FBC_HOME=/otra/carpeta   instala bajo otra carpeta en vez de $HOME (para las pruebas)
#   FBC_SIN_SYSTEMD=1        no llama a systemctl
set -euo pipefail

aqui=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
home=${FBC_HOME:-$HOME}
sin_systemd=${FBC_SIN_SYSTEMD:-}

if [[ $sin_systemd != 1 && $(realpath -m -- "$home") != "$(realpath -m -- "$HOME")" ]]; then
    # systemctl --user solo lee las unidades del HOME de verdad: activaría otras, no las que se instalan aquí.
    echo "instalar.sh: FBC_HOME ($home) no es el HOME ($HOME); para instalar en otra carpeta hace falta FBC_SIN_SYSTEMD=1" >&2
    exit 1
fi

compartida=$home/.local/share
destino=$compartida/futbol-base-copia
lanzador=$home/.local/bin/futbol-base-copia
unidades=$home/.config/systemd/user

mkdir -p -- "$compartida" "$(dirname -- "$lanzador")" "$unidades"
# Restos de una instalación cortada a medias.
rm -rf -- "$compartida"/.futbol-base-copia.*

# La copia nueva se prepara y se prueba al lado: si no arranca, la instalada sigue como estaba.
nueva=$(mktemp -d -- "$compartida/.futbol-base-copia.XXXXXX")
trap 'rm -rf -- "$nueva"' EXIT
mkdir -- "$nueva/copia"
cp -- "$aqui"/copia/*.py "$nueva/copia/"
cp -- "$aqui/origenes.json" "$nueva/"
# De qué commit sale la copia (+cambios si pc/copia tiene algo sin commit) y cuándo se instaló: lo dice `estado`.
if commit=$(git -C "$aqui" rev-parse HEAD 2> /dev/null); then
    if [[ -n $(git --no-optional-locks -C "$aqui" status --porcelain -- . 2> /dev/null) ]]; then
        commit+="+cambios"
    fi
else
    commit="desconocido (no es un repositorio git)"
fi
printf 'commit %s, %s\n' "$commit" "$(date -Iseconds)" > "$nueva/INSTALADO"
chmod 755 -- "$nueva"
if ! PYTHONPATH=$nueva PYTHONDONTWRITEBYTECODE=1 python3 -P -s -m copia --help > /dev/null; then
    echo "instalar.sh: la copia nueva no arranca con $(command -v python3 || echo python3); no se ha cambiado nada" >&2
    exit 1
fi
# Entera (que no quede ningún módulo ni __pycache__ de la versión anterior) y sin hueco: la vieja se aparta con un
# cambio de nombre, la nueva ocupa su sitio con otro y solo después se borra la vieja.
vieja=$compartida/.futbol-base-copia.vieja
if [[ -e $destino ]]; then
    mv -T -- "$destino" "$vieja"
fi
if ! mv -T -- "$nueva" "$destino"; then
    if [[ -e $vieja ]]; then
        mv -T -- "$vieja" "$destino"
    fi
    echo "instalar.sh: no se pudo poner la copia nueva en $destino; se deja la que había" >&2
    exit 1
fi
trap - EXIT
rm -rf -- "$vieja"

{
    echo '#!/bin/bash'
    echo '# Lanzador de la copia de seguridad de futbol-base. Lo escribe instalar.sh: no se edita a mano.'
    printf 'export PYTHONPATH=%q\n' "$destino"
    echo '# -P: un paquete «copia» en la carpeta desde la que se lanza no sustituye al instalado.'
    # shellcheck disable=SC2016  # "$@" es para el lanzador, no para este script.
    echo 'exec python3 -P -s -m copia "$@"'
} > "$lanzador.tmp"
chmod 755 -- "$lanzador.tmp"
mv -f -- "$lanzador.tmp" "$lanzador"

install -m 644 -- "$aqui/systemd/futbol-base-copia.service" "$aqui/systemd/futbol-base-copia.timer" "$unidades/"

if [[ $sin_systemd == 1 ]]; then
    temporizador="sin activar: con FBC_SIN_SYSTEMD=1 no se llama a systemctl"
else
    systemctl --user daemon-reload
    systemctl --user enable --now futbol-base-copia.timer
    temporizador="activado, cada día a las 04:40"
fi

cat <<FIN
Instalado:
  programa:       $destino
  orden:          $lanzador
  temporizador:   $unidades/futbol-base-copia.timer ($temporizador)
  servicio:       $unidades/futbol-base-copia.service
No se ha hecho ninguna copia. Para comprobar la instalación:
  $lanzador estado
  systemctl --user list-timers futbol-base-copia.timer
Hasta la primera copia, «estado» dice «sin copias». Para hacerla ya: $lanzador ejecutar
FIN
