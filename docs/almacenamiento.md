# La base en piezas

La web sale de una base de datos, `futbolbase.db`, que vive dentro de git y que el bot actualiza cada hora.
Hoy ocupa 41 MB; con todas las categorías y las actas de siete temporadas pasará de 200 MB. Y hay tres
límites:

- **GitHub no admite ficheros de más de 100 MB** (avisa desde 50). Aquí se avisa desde 80 y no se sube nada
  desde 95, para no llegar nunca a un push rechazado.
- **GitHub Pages admite 1024 MB por sitio.** Hoy publica todo `main`; las tareas siguientes lo dejan en solo
  la web.
- **La base entera no puede ir en un fichero**: con 280 MB ya no cabe en git.

Por eso la base se guarda en git **partida en piezas**, en la carpeta `base/`, y se monta en `futbolbase.db`
al empezar cada trabajo. Para todo el código la base sigue siendo una, con el mismo esquema: solo cambia cómo
se guarda. El módulo que lo hace es `scripts/piezas.py` (solo la biblioteca estándar).

Hasta la fase 3 de la transición **la que manda es `futbolbase.db`**: sigue en git, las piezas van a su lado
y se comprueba en cada subida que son iguales a ella. Las fases, más abajo.

## Qué hay en `base/`

| Fichero | Qué lleva | Hoy |
|---|---|---|
| `comun.db` | El esquema entero (tablas, índices, la vista `match_staff`) y todas las filas de todas las tablas salvo las de `appearances`, `match_events` y `match_staff_all`, que van vacías (con sus índices). Su `sqlite_sequence`, `user_version` y `application_id`, los de la base. | 10,6 MB |
| `actas-<AAAA-AAAA>.db` | Solo esas tres tablas, con el `CREATE TABLE` de la base letra a letra y sin índices secundarios, y sus filas de los partidos de esa temporada (`matches.group_id → groups.season_id → seasons.name`). Una temporada sin filas no tiene pieza. | de 1,1 (2020-21) a 3,8 MB (2025-26) |
| `piezas.json` | El manifiesto: qué piezas hay, sus bytes y las filas de cada tabla. | 2 KB |

Todas las piezas, 31,9 MB (medido el 25/11/2026 sobre una copia de la base). Con ×7 actas se esperan
45-60 MB la común, 25-30 MB la mayor de temporada y 250-300 MB en total.

Las piezas van en **modo de diario `DELETE`**, nunca WAL: git solo sube el fichero, y lo que quedara en un
`-wal` se perdería. La base montada sí va en WAL, como la de hoy.

El manifiesto tiene este formato (formato 1), escrito con `json.dumps(…, ensure_ascii=False, indent=2,
sort_keys=True)` y un salto de línea al final:

```json
{"formato": 1, "piezas": {"comun.db": {"bytes": 11091968, "filas": {"matches": 41234, "…": 0}},
                          "actas-2025-2026.db": {"bytes": 4005888,
                                                 "filas": {"appearances": 0, "match_events": 0, "match_staff_all": 0}}}}
```

En `comun.db`, todas las tablas menos las tres pesadas y `sqlite_sequence`; en cada `actas-…`, las tres.

### La identidad de cada fila

Cada fila conserva su **identidad**, que es lo que se compara y lo que se copia:

- en una tabla `WITHOUT ROWID` (`appearances`), su clave primaria;
- en una con `INTEGER PRIMARY KEY` (`matches`, `match_events`, `players`…), esa columna, que es el rowid;
- en las demás (`match_staff_all`, `venues`, `fp_goals`, `raw_imports`, `standings_detail`…), su `rowid`, que
  se copia explícito.

Montar devuelve la base con los mismos `rowid`. Y dos filas iguales salvo el rowid (dos veces el mismo cargo
del cuerpo técnico en un acta) siguen siendo dos.

## Las tres órdenes

Desde la raíz del repositorio. Por defecto, `--db futbolbase.db` y `--piezas base`.

### `python3 scripts/piezas.py montar [--db F] [--piezas D] [--solo-comun] [--contra F]`

Arma la base en un temporal junto al destino (`.futbolbase.db.<azar>.tmp`): copia `comun.db` (con su
`quick_check`), le añade las filas de cada pieza de temporada y la deja en WAL. Antes de ponerla en su sitio
comprueba que cuadra con el manifiesto: los `.db` de la carpeta son exactamente los que nombra, cada uno con
sus bytes, cada tabla con sus filas, las pesadas de `comun.db` vacías y el mismo `CREATE TABLE` de las
pesadas en todas. Si algo no cuadra, el destino no se toca.

- Si junto al destino hay un `-wal` (o un `-journal`) **con datos**, no monta: serían cambios sin volcar de
  otra sesión, y una base nueva con el WAL de otra es una base rota. Vacíos, los quita con el `-shm`.
- Con `--contra F`, antes de ponerla la compara con `F` (lo mismo que `comparar`); si no son iguales, para
  sin tocar el destino.
- Con `--solo-comun`, solo `comun.db`: las tres pesadas, vacías. Para los trabajos que solo leen la parte
  común.
- Escribe `<destino>.piezas` con el sha256 del texto de `piezas.json` (con `--solo-comun`, seguido de
  `solo-comun`): de qué piezas sale la base montada.

Salida: `montada futbolbase.db: 9 piezas, 437942 apariciones`.

### `python3 scripts/piezas.py partir [--db F] [--piezas D]`

Deja en `base/` las piezas de la base, **tocando solo las que cambian**. Lee la base en solo lectura.

1. Quita los temporales de un corte anterior y, si una pieza tiene un `-journal` al lado (una transacción
   cortada), la abre en escritura: SQLite la devuelve a su último commit.
2. Si hay filas pesadas sin temporada (su partido, su grupo o su temporada no están), para y dice cuántas y
   de qué partidos: no se sabría dónde guardarlas.
3. Por cada pieza:
   - si falta, está rota, no está en modo `DELETE` o su esquema no es el de la base, se **rehace entera** en
     un temporal y se pone en su sitio con `os.replace`;
   - si no, se adjunta en solo lectura y se cuentan las diferencias con un `EXCEPT` en los dos sentidos
     contra las filas de la base de esa temporada. **Sin diferencias no se abre en escritura**: ni un byte
     cambia y git no ve nada. Con ellas, en una transacción, se borran por identidad las filas que sobran o
     cambiaron y se insertan las nuevas o cambiadas; antes del commit se comprueba que cada tabla tiene las
     filas de la base. En `comun.db`, además, se igualan `sqlite_sequence`, `user_version` y
     `application_id`.
4. Borra la pieza de una temporada que se ha quedado sin filas.
5. Escribe el manifiesto el último (temporal y `os.replace`), solo si cambia, y después `<db>.piezas`.

Volver a llamarla tras un corte arregla lo que quedó a medias.

Una tabla nueva de la base va sola a `comun.db`. Un cambio de esquema rehace la pieza afectada: `comun.db`
con cualquier cambio (lleva el esquema entero), y las de temporada solo si cambia el `CREATE TABLE` de una
pesada (no llevan índices secundarios, así que un índice nuevo no las toca).

No se parten (para, con `PiezasError`): una base con **triggers** (se dispararían al montarla), con una tabla
interna que no sea `sqlite_sequence` (`sqlite_stat1` de un `ANALYZE`), con tablas virtuales, una base sin
actas cuando las piezas sí tienen (montada con `--solo-comun`) o con un `<db>.piezas` que dice `solo-comun`.

Salida: `partida futbolbase.db: 0 creadas, 2 cambiadas, 0 borradas, 7 sin cambios` y una línea
`  actas-2025-2026.db: +22 -22` por cada pieza cambiada.

### `python3 scripts/piezas.py verificar [--db F] [--piezas D]`

¿Se pueden subir las piezas? Monta las piezas en un directorio temporal del sistema y compara la montada con
la base, tabla a tabla, con una **huella** de todas sus filas: un sha256 de cada fila como `repr(tuple(fila))`
en el orden de su identidad (`repr` distingue 1, 1.0, '1' y b'1', y da todos los decimales de un REAL). Lo
que no sea idéntico, esquema incluido, no se sube. Además mira:

- un `-journal` en la carpeta: «partir se cortó a medias»;
- una pieza que no está en modo `DELETE` (bytes 18 y 19 de la cabecera);
- una pieza del manifiesto que ha desaparecido mientras su temporada tiene filas;
- un fichero en `base/` que no es una pieza del manifiesto (un resto de un corte);
- la pieza mayor: desde 95 MB, «la pieza … ocupa 96 MB y GitHub no admite más de 100».

Salida: `piezas iguales a la base: 30 tablas; la mayor, comun.db (10,6 MB); en total 31,9 MB`, o una línea
por motivo y sale con 1.

### `python3 scripts/piezas.py comparar --db F --piezas D`

Monta `D` en un temporal y lo compara con `F`. Escribe `iguales` o una línea por diferencia
(«appearances: 437942 filas y 437941»).

## Lo medido (25/11/2026, sobre una copia de la base, en este PC)

| Qué | Tiempo |
|---|---|
| Partir desde cero (9 piezas) | 2,5 s |
| Partir sin cambios (EXCEPT en las 9 piezas) | 3,4 s |
| Partir con un acta cambiada (su pieza y `comun.db`, en sitio) | 4,9 s |
| Montar (437.942 apariciones, 146.619 sucesos, 72.908 del cuerpo técnico) | 2,3 s |
| Comparar (huella de todas las tablas de las dos bases) | 8,1 s |
| Verificar (montar + comparar) | 10,7 s |

La base montada ocupa 42,9 MB (41,0 la de git: los índices se rellenan sin ordenar). Con ×7 actas, todo se
multiplica por algo menos de 7 (unos 20 s partir sin cambios, 70 s verificar).

## Cómo se trabaja con la base a mano

Mientras `futbolbase.db` siga en git (hasta la fase 3), como hoy: se abre, se cambia, y el bot parte y
verifica al subir. Desde la fase 3, que la base ya no esté en git:

```sh
python3 scripts/piezas.py montar          # base/ → futbolbase.db
python3 scripts/…                         # la orden que sea, sobre futbolbase.db
python3 scripts/piezas.py partir          # futbolbase.db → base/ (solo lo que cambió)
python3 scripts/piezas.py verificar       # las piezas vueltas a montar son la base
git add -A base/
```

Antes de montar, cierra todo lo que tenga la base abierta: montar la cambia por otro fichero (`os.replace`), y
un programa que la tuviera abierta seguiría escribiendo en la vieja.

## Decisiones y detalles

- **La comparación de `partir` y la de `verificar` no son la misma, a propósito.** `partir` usa `EXCEPT` (en
  SQLite, rápido), y `EXCEPT` tiene puntos ciegos: da por iguales 'a' y 'A' en una columna `NOCASE`, y 1 y 1.0
  en una columna sin tipo. Se tapan los dos: cada columna va con `COLLATE BINARY`, y en las columnas sin
  afinidad (sin tipo o `BLOB`) se compara también `typeof()`. Queda uno: 0.0 y -0.0 en una columna sin tipo
  (en una `REAL`, SQLite no guarda el signo de un cero). Hoy no hay ninguna columna así fuera de
  `sqlite_sequence`; si la hubiera, `verificar` lo vería (la huella sí los distingue) y no se subiría, pero
  `partir` no lo arreglaría solo: habría que borrar la pieza para que se rehaga.
- **Los rowid se copian siempre explícitos** (`INSERT INTO t (rowid, …) SELECT rowid, …`). Un
  `INSERT INTO t SELECT * FROM …` los conserva solo cuando SQLite aplica su copia rápida, y si no la aplica
  los renumera sin decir nada.
- **Montar no se queda con una de dos filas repetidas.** La misma identidad en dos piezas (un corte a mitad
  de mover un partido de temporada) hace fallar el `INSERT` por la clave: nada de `OR IGNORE` ni
  `OR REPLACE`.
- **Un `VACUUM` de la base renumera los rowid** de las tablas sin `INTEGER PRIMARY KEY` (`match_staff_all`,
  `venues`, `standings_detail`…). No se pierde nada (la identidad es el rowid de la base), pero el siguiente
  `partir` reescribe esas tablas enteras y el cambio en git es grande. Hoy solo hace `VACUUM`
  `migrate_compactar`, una vez.
- **Un diario cortado antes de escribir nada** tiene la cabecera a ceros: SQLite no lo considera «caliente»
  (la pieza no llegó a cambiar) y no lo borra al abrirla. `partir` lo borra; si tuviera cabecera, sería un
  diario caliente que SQLite no pudo deshacer, y para.
- **`comun.db` se rehace con los índices después de las filas** (se ordenan de una vez y la pieza sale más
  pequeña). El orden de `sqlite_master` cambia respecto a la base; el esquema (tipo, nombre, tabla y SQL de
  cada objeto) es el mismo.
- **La temporada de cada partido va en una tabla temporal con índice por conexión**, no una vez por llamada:
  una tabla temporal es de su conexión, y cada pieza que se escribe usa la suya (la pieza es la base
  principal, para ejecutar los `CREATE` de la base letra a letra). Cuesta unos milisegundos por pieza.
- **`partir` lee la base con varias conexiones** (una para contar, otra por pieza que escribe): supone que
  nadie la escribe mientras tanto. Si alguien lo hiciera, la cuenta de filas de antes del commit no cuadraría
  y pararía; y si cuadrara por casualidad, `verificar` lo vería.
- **Los temporales salen con permisos 0644** (o los del fichero de antes): `mkstemp` los crea con 0600.

## Fases

Tres, publicables por separado. Las describen las tareas 2, 3 y 7 del plan
`docs/superpowers/plans/2026-11-25-ampliacion-d-almacenamiento.md`, que completan esta sección.

1. Sombra (tarea 2).
2. Cambio de fuente de verdad (tarea 3).
3. `futbolbase.db` fuera de git (tarea 7).
