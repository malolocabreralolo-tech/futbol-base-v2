# Qué se puede rehacer si se pierde la base

La web sale de una base de datos, `futbolbase.db`. El bot la rellena con lo que lee de la federación y de
ficheros originales que guarda en `scripts/` (lo que bajó una vez de la federación, de la app de
futbolaspalmas, del archivo de Internet…). Si la base se perdiera o se estropeara, ¿qué se podría volver a
sacar de esos originales?

Se ha comprobado de verdad, por partes, con `python3 scripts/reconstruir.py --comprobar`: sobre una copia de
la base (la de verdad no se toca), borra una parte, la vuelve a importar con el mismo programa que usa el
bot, sin conectarse a nada, y la compara fila a fila con lo que había. Una prueba lo repite en GitHub cada
día (`tests.yml`, paso «Reconstrucción desde los originales»).

## El resultado, por partes

| Parte | Qué es | De qué original sale | ¿Se rehace? |
|---|---|---|---|
| `app` | Lo que da la app de futbolaspalmas de 2026-27: estados, horas, campos, goleadores de pila | `fp_app_2026-2027_raw.json` | Sí, comprobado |
| `torneos` | La Maspalomas Cup | `maspalomas_cup_2026_raw.json` | Sí, comprobado |
| `actas_bot` | Alineaciones, sucesos y cuerpo técnico de las actas de 2026-27 que el bot ya guarda (402 de 1.096) | `actas_bot_2026-2027_*.jsonl` | Sí, comprobado |
| `goleadores` | Los goleadores de temporadas pasadas que vienen de la federación | `fiflp_goleadores_*_raw.json` | Sí, comprobado |
| `mygol` | La liga de escuelas de MyGol (2022-23 a hoy): torneos, equipos, partidos y qué niños jugaron | `mygol_*_raw.json` (y la tabla de torneos, `mygol_torneos.json`) | Sí, comprobado |
| `actas` | Alineaciones, sucesos y cuerpo técnico de 2016-17 a 2025-26 | `fiflp_actas_*_raw.json` | No |
| `detalle` | Casa/fuera, fichas de equipo y de campo de temporadas pasadas | `fiflp_detalle_*_raw.json`, `fiflp_campos_raw.json` | No |
| `portal` | Las temporadas antiguas de futbolaspalmas (2012-13 a 2020-21) | `wayback_portal_*_raw.json` | No |

En las actas de 2026-27 hay un detalle que no cambia nada de lo que se ve salvo una letra: de 4.942
jugadores, 6 saldrían con el nombre escrito de otra forma (una tilde o una mayúscula en 5, una corrección de
la federación en 1). La base guarda el nombre tal como venía la primera vez que se leyó un acta suya, y el
original guarda la última lectura.

`mygol` es entero de sus originales: el importador vacía sus cinco tablas y las vuelve a llenar en cada
importación. En una base de antes de la primera pasada que lo importa, la comprobación le hace primero lo que
hará esa pasada (crear las tablas e importar) y después comprueba que rehacerlas sale igual. Mientras se
está bajando una temporada, sus originales cambian: lo que se compara es lo importado con lo que hay ese día.

Si la comprobación diaria sale en rojo en una de las partes que se rehacen, la base tiene algo que sus
originales no explican, y la salida dice qué. Por ejemplo, el 17/11/2026 un partido de 2026-27 estaba dos
veces en la base (la federación cambió el nombre de un equipo después de jugarse y el bot lo entró otra vez
con el nombre nuevo): el acta no sabe a cuál de los dos va, y la comprobación lo dice con el código del acta.
El 24/11/2026, `app` salió con 156 equipos de más en `fp_teams`: los de 10 ligas de la app (la segunda fase de
benjamín de Gran Canaria y la eliminatoria A-B) que una pasada casaron con un grupo y la siguiente con
ninguno; el importador no tocaba los equipos de una liga sin grupo y se quedaban los de la pasada anterior.
Ahora los de cada liga son siempre los de su tabla en el original, con o sin grupo.

## Lo que no se puede rehacer, y por qué

- **Lo de la temporada en curso que el bot lee en vivo**: calendario, clasificación, goleadores, equipos y
  campos de 2026-27. La federación no deja un original de eso; solo de las actas (y aún no de todas: 694 de
  1.096 se leyeron antes de que el bot empezara a guardarlas, el 14/11, y las va releyendo poco a poco).
- **Las temporadas 2019-20 a 2025-26 fuera de las actas y los goleadores**: se cargaron una vez a mano, con
  programas y arreglos que el bot no vuelve a ejecutar.
- **`actas`**: al rehacerlas cambian unas 18.000 de 658.000 filas. El programa que las importa también
  escribe partidos, y lo que se corrigió después en la base no se repite: vuelven 1.533 partidos (casi todos
  de 2016-17 a 2018-19) que la base ya no tiene y faltan 257; cambian el campo, la hora o la fecha de casi
  10.000 partidos (y el marcador de 61); y salen distintas unas 2.600 filas de alineaciones y sucesos y unas
  3.500 del cuerpo técnico, casi todas de 2019-20 y 2020-21.
- **`detalle`**: sale igual salvo 7 de 1.973 fichas de equipo: 6 de 2024-25 venían de una versión anterior
  del original (que solo está en la historia de git) y el programa nunca borra una ficha; la otra, de
  2019-20, está en el original pero el programa de hoy ya no la escribe.
- **`portal`**: la base tiene sus partidos ya corregidos y el programa los vuelve a escribir tal como los trae
  el archivo: 309 marcadores de 2016-17 a 2018-19 distintos, los de 2020-21 con otro nombre de jornada (y
  salen duplicados), equipos que se renombraron después y dos grupos cuyos partidos ya no se colocan.
- **Los goles de 2025-26** (`goals`) y **los campos** (`venues`): se leyeron en vivo de la web de entonces.

**Para todo eso, la única copia es la propia base.** La protege la copia diaria del PC (`pc/copia/`, la orden
`futbol-base-copia`): cada madrugada guarda en `~/backups/futbol-base/` la base de v1 y la de v2 si está
sana, con las de días, semanas y meses anteriores y una copia entera del repositorio. Cómo sacar la de un
día está en [pc/copia/README.md](../pc/copia/README.md).

## Tabla por tablas

«Comprobado» quiere decir que la prueba la rehace y sale igual; «no» lleva su porqué arriba.

| Tabla | De qué original sale | ¿Comprobado que se rehace? |
|---|---|---|
| `fp_ligas`, `fp_teams`, `fp_matches`, `fp_goals` | `fp_app_2026-2027_raw.json` | Sí (`app`) |
| `tournaments`, `tournament_matches`, `tournament_standings` | `maspalomas_cup_2026_raw.json` | Sí (`torneos`) |
| `appearances`, `match_events`, `match_staff_all` | de 2026-27, `actas_bot_*.jsonl`; de antes, `fiflp_actas_*_raw.json` | 2026-27, las 402 con original: sí (`actas_bot`); las demás de 2026-27, no (sin original); las de antes, no (`actas`) |
| `players` | las mismas actas | Los de las 402 actas de 2026-27: sí, salvo 6 grafías; los demás, no |
| `scorers`, `fiflp_scorer_groups` | de temporadas pasadas, `fiflp_goleadores_*_raw.json` | Los de la federación: sí (`goleadores`); los de 2026-27 (en vivo) y los de futbolaspalmas, no |
| `mygol_torneos`, `mygol_equipos`, `mygol_jugadores`, `mygol_partidos`, `mygol_participaciones` | `mygol_*_raw.json` y `mygol_torneos.json` | Sí (`mygol`) |
| `standings_detail`, `team_seasons`, `venue_details`, `detalle_groups` | `fiflp_detalle_*_raw.json`, `fiflp_campos_raw.json` | No (`detalle`: 7 fichas de equipo); los de 2026-27, en vivo |
| `matches`, `standings`, `groups`, `portal_groups` | portal, actas, grupos y detalle; 2019-26, cargas a mano; 2026-27, en vivo | No |
| `goals` | — (2025-26, en vivo) | No |
| `teams`, `seasons`, `categories` | de todos los importadores | No por separado (las usan todas las partes) |
| `venues` | — (en vivo) | No |
| `fiflp_groups` | `fiflp_actas_*` y `fiflp_goleadores_*` | No por separado (va con `actas`) |
| `raw_imports`, `fiflp_full_pending`, `sqlite_sequence` | estado del bot, no datos | — |
