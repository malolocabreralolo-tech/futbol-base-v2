# El reloj de v2 en el PC

Cada 5 minutos este PC mira si toca que el bot de la web v2 haga una pasada (buscar resultados nuevos), o si toca
el carril de infantil, cadete y juvenil (`carril-mayores.yml`) o el del histórico (`historico.yml`).
Si toca alguno, se lo pide a GitHub: lanza `reloj.yml` en el repositorio `malolocabreralolo-tech/futbol-base-v2`,
que vuelve a mirarlo y lanza lo que toque.

## Por qué existe

GitHub debería hacerlo solo, con su propio reloj, pero casi nunca llega: un día avisó 10 veces de las 112 que tocaban.
Con este reloj, las pasadas salen a su hora mientras el PC esté encendido y con internet.
Si el PC está apagado, el reloj de GitHub sigue ahí de reserva.

El carril y el histórico también los lanza `reloj.yml`, pero solo en un aviso en el que no toca la pasada: por eso
este reloj mira también si toca alguno de los dos (el histórico, un intento cada hora y media fuera de los partidos;
el carril, entre dos pasadas del bot, cada 4 h). El carril, solo si está encendido: lee en GitHub la variable
`CARRIL_MAYORES` (a `1`, encendido; sin poner o con otra cosa, apagado, y entonces ni lo mira). Para eso el token
tiene que poder leer las variables del repositorio (el de hoy puede).

## Es aparte del de v1

La web actual (v1) tiene su propio reloj, `futbol-base-reloj`. Este no lo toca: no lo cambia, no lo para y no lanza nada en v1.
Van dos minutos desfasados (v1 a y 2, 7, 12…; v2 a y 4, 9, 14…) para no ir los dos a la vez.

## El token de GitHub

Usa el mismo token que el reloj de v1, leyéndolo donde está: `~/.config/futbol-base-reloj/token`.
No lo copia, no lo cambia y no lo escribe en ningún sitio.
Si algún día quieres un token aparte para v2, basta con cambiar una línea: pídeselo a Claude.

## Cómo ver si va

    systemctl --user list-timers futbol-base-v2-reloj.timer

Dice cuándo miró por última vez y cuándo toca la próxima.

    journalctl --user -u futbol-base-v2-reloj.service -n 20

Enseña una línea por cada vez que miró:

- `No toca`: aún no es la hora; no hace nada.
- `Lanzado reloj.yml`: ha pedido la pasada (o, si la línea dice `Carril de las categorías mayores: toca` o
  `Carril del histórico: toca`, ese carril).
- `No se pudo mirar el carril` o `No se pudo mirar el histórico`: GitHub no dio una de sus listas, o la copia
  instalada es antigua (entonces dice que hay que reinstalar). No es un error: la pasada del bot sigue igual.
- `No se pudo leer la variable CARRIL_MAYORES`: el token no la deja leer o falló la red. Hace como si el carril
  estuviera apagado; el histórico y la pasada, igual.
- `No se lanza: reloj.yml está «disabled_manually»`: alguien lo apagó en GitHub (pestaña Actions). Espera sin dar error.
- `AVISO: reloj_pasadas.py ha cambiado en main`: en GitHub cambió la regla de cuándo toca. Sigue con la suya, la revisada. Revisa el cambio y reinstala (abajo).
- `error: GitHub desactivó reloj.yml por inactividad`: pasa tras 60 días sin cambios. El mensaje dice la orden que lo reactiva.

Si falla, también sale en `systemctl --user --failed`.

## Cómo pararlo

    systemctl --user disable --now futbol-base-v2-reloj.timer

Para volver a ponerlo: `systemctl --user enable --now futbol-base-v2-reloj.timer`. Pararlo no afecta al reloj de v1.

## Reinstalar después de cambiar `scripts/reloj_pasadas.py`

El reloj no usa ese fichero del repositorio, sino una copia revisada en `~/.local/share/futbol-base-v2-reloj/`.
Así, un cambio que llegue a GitHub sin mirar no se ejecuta en el PC.
Con el cambio ya revisado y en esta carpeta, pasa las pruebas y vuelve a instalar:

    cd ~/claude/futbol-base-v2
    python3 -m pytest pc/reloj/tests -q
    bash pc/reloj/instalar.sh

`instalar.sh` pone la orden `~/.local/bin/futbol-base-v2-reloj`, la copia y el temporizador, y lo activa. No lanza ninguna pasada.
Para ver qué decidiría ahora, sin lanzar nada: `DRY_RUN=1 ~/.local/bin/futbol-base-v2-reloj`.
