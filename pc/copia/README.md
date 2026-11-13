# Copia de seguridad de futbol-base en el PC

Cada madrugada este PC guarda una copia de la base de datos de la web de fútbol base y de su repositorio de GitHub.
Antes de guardar una base comprueba que está sana. Si no lo está, la aparta y no toca la buena que ya había.

La orden es `futbol-base-copia` (está en `~/.local/bin`; si la terminal no la encuentra, escribe `~/.local/bin/futbol-base-copia`).
`v1` es la web actual. Cuando exista la nueva aparecerá `v2` al lado y todo funcionará igual.

## Qué se guarda y dónde

Todo va en `~/backups/futbol-base/`, una carpeta que solo puede abrir tu usuario:

- `actual/v1/futbolbase.db`: la última base buena, sin comprimir. Se puede abrir tal cual.
- `versiones/v1/<año>/`: las bases buenas de otros días, comprimidas (`.db.xz`). Cada una lleva al lado un `.json` con su huella y cuántas filas tenía cada tabla.
- `volcados/v1/`: la base entera en texto (SQL), una por semana. Sirve aunque el fichero de la base se estropee.
- `repos/v1.git`: una copia completa del repositorio de GitHub, con toda su historia. No pierde nada aunque en GitHub se borre o se reescriba.
- `cuarentena/v1/`: las bases que no pasaron las comprobaciones, comprimidas, cada una con un `.motivo.txt` que dice por qué.
- `estado.json`: cómo fue la última pasada (es lo que lee `estado`).
- `registro.log`: una línea por cada pasada, con lo que pasó.

Las otras carpetas que hay ahí (`correcciones-2026-09-09`, `mejoras-completas-2026-09-09`, `notas-viejas-2026-10-14`, `rediseno-2026-09-23`, `revision-2026-09-09` y `local-v1/`, con todas las ramas locales de la web actual a 13/11/2026) son de antes: esta herramienta no las toca.

## Cada cuánto y qué se conserva

- Una pasada al día, a las 04:40 (con hasta 10 minutos de margen al azar). Si el PC estaba apagado a esa hora, la hace al iniciar sesión en el PC.
- Versiones: la más nueva de cada día durante 30 días, la más nueva de cada semana durante 26 semanas, la más nueva de cada mes para siempre, y siempre la última. Si la base no ha cambiado, no se guarda otra vez.
- Volcados en texto: uno por semana; se conservan los 12 más nuevos.
- Cuarentena: la misma base rechazada se guarda una sola vez; se conservan las 10 más nuevas.
- Todo lo comprimido va en formato xz.

## Cómo ver si va bien

    futbol-base-copia estado

Escribe una línea por web, lo que ocupa la carpeta y de qué commit es la copia instalada. Va bien si pone `(aceptada)` o `(sin cambios)` y no sale la palabra `AVISO`. Por ejemplo:

    v1: comprobada 2026-11-14T04:43:05+00:00 (aceptada) · última buena 2026-11-14T04:43:05+00:00 (matches 37850, players 17402)
    ocupa 352,8 MB en /home/manolo/backups/futbol-base
    instalado: commit 0123abcd…, 2026-11-13T15:02:11+01:00

La última línea dice de qué commit del repositorio es la copia instalada y cuándo se instaló (con `+cambios` si `pc/copia` tenía cambios sin commit).

Sale `AVISO` si la última pasada falló, si la base fue a cuarentena, si lleva 3 días o más sin comprobarse o si una web de `origenes.json` no tiene todavía ninguna copia (`sin copias`).
Si quitas una web de `origenes.json`, sus copias se quedan y `estado` la sigue enseñando con `(ya no está en origenes.json)`, sin avisar por ella.
`(error)` quiere decir que la pasada no pudo terminar (por ejemplo, sin internet): se vuelve a intentar al día siguiente.
Para ver cuándo fue la última pasada automática y cuándo toca la próxima:

    systemctl --user list-timers futbol-base-copia.timer

Lo que escribió la última pasada automática: `journalctl --user -u futbol-base-copia.service -n 20`.
Para hacer una pasada ahora, a mano (tarda unos minutos): `futbol-base-copia ejecutar`. Si ya hay otra en marcha, esta no hace nada.

## Cómo recuperar la base de un día

Primero mira qué versiones hay:

    futbol-base-copia versiones v1

Cada línea empieza por el momento de la versión, `AAAAMMDD-HHMMSS`, en hora UTC (en invierno es la hora de Canarias; en verano, una hora menos). Después sácala a una carpeta:

    futbol-base-copia restaurar v1 ~/recuperada --momento 20261113-044012

Sin `--momento` saca la última. Deja en esa carpeta `futbolbase-20261113-044012.db` y escribe dónde la ha dejado.
Antes de dártela comprueba que es idéntica a la que se guardó; si no lo es, lo dice y no deja nada.
También comprueba que está sana; si es idéntica pero no pasa las comprobaciones de hoy (por ejemplo, porque se guardó cuando se vigilaban otras tablas), te la da igual y avisa de qué le pasa.
Nunca escribe dentro de `actual/`.

## Cómo recuperar la base del volcado en texto

Si el fichero de una base no sirve, los volcados de `volcados/v1/` la tienen entera en texto, uno por semana. Este PC no tiene la orden `sqlite3`; se carga con Python.
En una carpeta donde no haya ya un `recuperada.db` (cambia el nombre del volcado por el de la semana que quieras):

    xz -dc ~/backups/futbol-base/volcados/v1/futbolbase-2026-S46.sql.xz | python3 -c "import sqlite3,sys; sqlite3.connect('recuperada.db').executescript(sys.stdin.read())"

Deja allí `recuperada.db`, con todas las tablas y filas de esa semana.

## Cómo sacar un fichero original del repositorio

    futbol-base-copia extraer v1 scripts/fiflp_2425_raw.json ~/fiflp_2425_raw.json

Saca ese fichero tal como estaba en la rama `main` en la última pasada. La ruta es la de dentro del repositorio.
Cada pasada deja marcado cómo estaba el repositorio ese día (fecha en UTC). Para sacar el fichero de un día anterior:

    git --git-dir ~/backups/futbol-base/repos/v1.git show refs/copia/main/20261113:scripts/fiflp_2425_raw.json > ~/fiflp_2425_raw.json

Los días que hay: `git --git-dir ~/backups/futbol-base/repos/v1.git for-each-ref refs/copia`.

Solo la rama `main` tiene esa marca de cada día. Las otras ramas también se copian, y lo que se reescriba en ellas no se pierde (el espejo no borra nada), pero sus estados anteriores solo se encuentran buscándolos con `git --git-dir ~/backups/futbol-base/repos/v1.git fsck --unreachable`.

## Si se pierde el repositorio de GitHub

`repos/v1.git` tiene todas sus ramas y etiquetas. Para devolverlas a GitHub (por ejemplo, a un repositorio nuevo y vacío), con `URL` la dirección de ese repositorio:

    git --git-dir ~/backups/futbol-base/repos/v1.git push URL 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'

No ejecutes nunca `git remote prune` ni `git fetch --prune` en el espejo, aunque git lo sugiera en un mensaje (puede salir en los avisos de `espejo incompleto`): borrarían las ramas que GitHub ya no tiene, que es justo lo que el espejo guarda.

## Si algo va a cuarentena

Quiere decir que la base de GitHub no pasó las comprobaciones: está dañada, tiene filas que apuntan a otras que no existen, le falta una tabla o tiene alguna vacía, o una de las tablas principales (partidos, jugadores, alineaciones, goles, clasificaciones…) ha perdido más del 2 % de sus filas desde la última buena.
No se ha perdido nada: la buena anterior sigue en `actual/` y en `versiones/`. `estado` sale con `AVISO` y el motivo, que también está en el `.motivo.txt` de `cuarentena/v1/`. Mientras la base de GitHub siga igual, el aviso se repetirá cada día.

Qué hacer:

- Si el cambio era querido (por ejemplo, se borraron a propósito partidos repetidos), acéptalo:

      futbol-base-copia ejecutar --aceptar-mengua v1

  Acepta la base que se apartó, o una prácticamente igual: la que hay en GitHub en ese momento se compara con la apartada (con el mismo margen del 2 %), no con la última buena. Si desde que la viste ha perdido más filas, no la acepta: va otra vez a cuarentena con su motivo, y decides viendo esa.
  Perdona también que falte una tabla o que esté vacía, pero solo si ya le pasaba a la base apartada. Una base dañada o con filas que apuntan a otras que no existen va siempre a cuarentena.
  La línea de la pasada dice lo que se ha perdonado comparando con la última buena, por ejemplo `aceptado a mano: matches 40 → 38`. Desde ese momento esa base es la buena, y las pérdidas se miden contra ella.
  Si la pasas sin que haya nada apartado (por adelantado, sabiendo que viene una base con menos filas), acepta la que llegue sin medir cuánto ha menguado; lo demás lo comprueba igual.
- Si no era querido, la base de la web está estropeada. La buena está en `~/backups/futbol-base/actual/v1/futbolbase.db` (o en una versión anterior, con `restaurar`), y con ella se arregla la de la web.

## Reinstalar después de cambiar el código

El temporizador no usa el código de este repositorio, sino una copia instalada en `~/.local/share/futbol-base-copia/`.
Después de cambiar algo aquí (también `origenes.json`, por ejemplo para añadir `v2`), pasa las pruebas y vuelve a instalar:

    cd ~/claude/futbol-base-v2/pc/copia
    python3 -m pytest tests -q
    bash instalar.sh

`instalar.sh` sustituye entera la copia instalada (aparta la vieja, pone la nueva en su sitio y solo entonces borra la vieja) y vuelve a escribir la orden `~/.local/bin/futbol-base-copia` y el temporizador (`~/.config/systemd/user/futbol-base-copia.service` y `.timer`).
No toca las copias ni hace ninguna. Al acabar dice qué ha instalado y cómo comprobarlo.
Para dejar de hacer la copia diaria: `systemctl --user disable --now futbol-base-copia.timer`.

## Límites

- La copia está en el mismo disco que el sistema. Protege de una base estropeada y de perder lo que hay en GitHub, pero no de que se rompa el disco. Para eso, lleva de vez en cuando la carpeta `~/backups/futbol-base/` a un disco externo.
- No está cifrada. Lleva nombres de jugadores; la carpeta solo la puede abrir tu usuario, pero cualquiera que entre en el PC con tu usuario la puede leer.
