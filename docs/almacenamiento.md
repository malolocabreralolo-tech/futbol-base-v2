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

En la fase 1 de la transición **mandaba `futbolbase.db`**: las piezas iban a su lado y se comprobaba en cada
subida que eran iguales a ella. Desde la fase 2 **mandan las piezas**: cada pasada monta la base de `base/`, y
`futbolbase.db` sigue en git, idéntica, hasta la fase 3. Las fases, más abajo.

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

En la fase 1 bastaba con cambiar `futbolbase.db`: el bot partía y verificaba al subir. Desde la fase 2 la base
y sus piezas se suben siempre juntas y la pasada siguiente exige que sean la misma (`--contra`): quien cambie
la base a mano parte, verifica y sube las dos en el mismo commit (`git add futbolbase.db` y `git add -A base/`),
con el bot parado. En la fase 2 no hace falta montar en local: la `futbolbase.db` de git es la de las piezas. Si se
monta, la montada tiene otros bytes y `git pull` se negará a pisarla: `git checkout -- futbolbase.db` antes. Desde la
fase 3, que la base ya no esté en git:

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

## Quién lee la base

Lo que abre `futbolbase.db`, lo que la escribe y lo que la sube, en todos los workflows y órdenes (26/11/2026), y
lo que hace cada uno en cada fase. Desde la fase 3 la base no está en git: quien la lee la monta antes.

| Sitio | Qué hace con la base | Fase 2 | Fase 3 (tarea 7) |
|---|---|---|---|
| `update.yml` (el bot) y `carril-mayores.yml` (lo llama con `cats`: los mismos pasos) | La lee y la escribe (`fetch_futbolaspalmas.py`), la comprueba (`base_sana.py`), la parte (`piezas.py`), las suites la leen y la sube con sus piezas | Monta con `--contra`; parte y bloquea; sube las dos | Monta; sube solo `base/` |
| `activar.yml` | «Qué hay pendiente» (`activar_auto.py --temporada` y `--tandas`, la de la temporada en curso), «Activar» la escribe, las suites la leen; la sube con sus piezas; «Publicar el fallo» la devuelve a la de `main` y la abre (`--pruebas-fallaron`) | Como el bot | Monta; sube y devuelve `base/`; vuelve a montar antes de `--pruebas-fallaron` |
| `tests.yml`, job `pytest` | Las pruebas sobre la base real (`test_db_sanity.py`, `test_data_integrity.py`… se saltan sin ella), `PIEZAS_REAL` y `test_reconstruir.py` | Monta con `--contra` | Monta; en GitHub, sin base montada la suite falla en vez de saltarse |
| `tests.yml`, los demás jobs | No la leen (los smokes, solo `data-*.js`) | — | — |
| `historico.yml`, «Descargar» | `fetch_fiflp_detalle.py` lee los códigos de `venues` (solo lectura; sin base, se los salta **en silencio**) | Igual que hoy (en git) | Monta la parte común (`--solo-comun`) antes |
| `historico.yml`, «Preparar la copia» … «Tests Node» | Un `git worktree` de `main` en `$RUNNER_TEMP/prueba`: «Importar sin red» escribe la base de la copia, «Base sana» y las suites la leen. Nunca la sube | Igual que hoy (la copia trae `futbolbase.db`) | Monta la de la copia desde su `base/` |
| `historico.yml`, «¿Qué toca?», «Promover», «Registrar», «Subir» | No la leen (`historico.py`, `cuarentena.py`; solo `scripts/historico/` y lo promovido) | — | — |
| `freno-fiflp.yml` (a mano) | `freno_experimento.py` lee `groups` y `seasons` (`sqlite3.connect`: sin base, crea una vacía y falla) | Igual que hoy | Monta la parte común antes |
| `mygol.yml`, `actas-federacion.yml`, `fetch-fiflp-islas.yml`, `discover-fiflp.yml`, `probe-fiflp.yml`, `reloj.yml` | No la leen | — | — |
| `scripts/reconstruir.py` (`--db`, por defecto la de la raíz) | Lee la de la raíz y trabaja en copias | Con la de git | Montar antes |
| `scripts/prueba_mayores.py`, `scripts/prueba_historico.py` | Copian la de la raíz (o la de su copia) y trabajan allí | Con la de git | Montar antes; `prueba_historico.py` mide la pieza mayor y no la base entera |
| Órdenes a mano que la abren: `activate_season.py`, `quitar_categoria.py`, `fiflp_manifest.py`, `medir_identidad.py`, `migrate_*.py`, `synth_copa_campeones.py`, `discover_temporada.py`, `escudos_federacion.py`, `import_*.py` | La leen o la escriben en la raíz | La de git (el bot parte y sube) | Montar antes; `partir`, `verificar` y `git add -A base/` después; sin montar, `db.get_connection` para con «monta la base» |
| `pc/copia/` (la copia del PC: `copia/fuentes.py`, `extraer_base`) | Saca `futbolbase.db` del commit del día | La de git | Si el commit no la trae, la monta de su `base/` (tarea 4) |
| «Datos y fuentes» (`src/screen-fuentes.js`) y `generate_js.py` (`COBERTURA.mb`) | El enlace de descarga y su tamaño | `./futbolbase.db` | El ZIP del día de la release `base-completa` (tarea 5, antes de la 7) |

## Fases

Tres, publicables por separado. Las describen las tareas 2, 3 y 7 del plan
`docs/superpowers/plans/2026-11-25-ampliacion-d-almacenamiento.md`, que completan esta sección.

1. Sombra (tarea 2): abajo.
2. Cambio de fuente de verdad (tarea 3): abajo.
3. `futbolbase.db` fuera de git (tarea 7).

### Fase 1: en sombra

La fuente de verdad sigue siendo `futbolbase.db`, en git como hasta ahora. Las piezas se generan al lado y
se suben con ella, para ver durante unos días que salen siempre iguales antes de fiarse de ellas. **Nada de lo
nuevo puede dejar al bot sin publicar**: si algo de las piezas falla, la pasada publica igual que hoy.

En cada pasada del bot (`update.yml`) y en cada activación con datos (`activar.yml`), justo después de «Base
sana», el paso **«Piezas de la base (en sombra)»**:

1. `python3 scripts/piezas.py partir`: pone `base/` al día con la base de esta pasada (solo las piezas que
   cambian).
2. `python3 scripts/piezas.py verificar`: monta las piezas en un temporal y comprueba que son la base, fila a
   fila. En el registro: `piezas iguales a la base: 30 tablas; la mayor, comun.db (10,6 MB); en total 31,9 MB`.
3. Si cualquiera de las dos falla (o se cuelga: 5 min de plazo), `base/` vuelve a lo que hay en `main` (las
   piezas nuevas y los diarios de una cortada, fuera), el paso sale en rojo con su motivo en el registro y la
   pasada **sigue** (`continue-on-error`): pruebas, commit y lo demás, como hoy.

Al subir («Commit y push si hay cambios» y «Subir la activación»), `base/` va **con la base y solo con ella**:
dentro de la misma puerta (si no cambió nada publicado ni hay marca de `update_fiflp`, no se sube ni la base ni
las piezas) y solo si el paso de las piezas salió bien. Con las piezas en rojo, la pasada sube la base y lo
demás, y `base/` en `main` se queda como estaba (la pasada siguiente lo pone al día). Si las pruebas fallan tras
activar, «Publicar el fallo» devuelve también `base/` a lo de `main`.

La primera pasada con datos sube `base/` entera (unos 32 MB: la común y una pieza por temporada); las
siguientes, solo la pieza que cambia y `piezas.json`, que se comprimen en git a unos KB.

`tests.yml` (cada día y en cada push que toque la base o `base/`) añade dos cosas al job de Python:

- `PIEZAS_REAL=1` en la suite: la base de verdad partida y vuelta a montar en una copia
  (`test_piezas_real.py`).
- **«Las piezas son la base»**: `python3 scripts/piezas.py comparar --db futbolbase.db --piezas base`. Es el aviso
  de que la sombra se ha desviado: las piezas que subió la última pasada, montadas, tienen que ser la base que
  subió. En rojo, se mira el registro de la última pasada con datos (el paso de las piezas dice por qué). Antes
  de que la primera pasada suba `base/`, no hay nada que comparar y sale en verde con un aviso.

Cómo se mira que va bien:

- En el registro de cada pasada con datos, la línea `piezas iguales a la base: …`
  (`gh run view <id> -R malolocabreralolo-tech/futbol-base-v2 --log | grep "piezas iguales"`).
- `git show --stat origin/main -- base/` tras una pasada con datos: las piezas que cambiaron.
- `tests.yml` en verde cada día, con «Las piezas son la base».
- Antes de pasar a la fase 2, las últimas pasadas una a una (en un clon limpio):

```bash
for c in $(git log -n 12 --format=%H origin/main -- futbolbase.db); do
  d=$(mktemp -d); git archive "$c" base futbolbase.db | tar -x -C "$d"
  python3 scripts/piezas.py comparar --db "$d/futbolbase.db" --piezas "$d/base" > /dev/null || echo "DISTINTO $c"
  rm -rf "$d"
done
```

Sin ninguna línea `DISTINTO`, se puede seguir. Vuelta atrás: `git revert` de los commits de esta fase (con el
bot sin nada en marcha); las piezas que haya en `base/` se quedan sin uso.

Lo que cuesta: en cada pasada, unos 15 s del paso de las piezas (partir sin cambios, 3,4 s; verificar, 10,7 s)
y unos 25 s más de la suite (`test_piezas.py`); con todas las actas, alrededor de 1,5 min del paso.

### Fase 2: mandan las piezas

La base de cada pasada sale de sus piezas. `futbolbase.db` sigue en git, idéntica a ellas: las dos se suben
siempre juntas, en el mismo commit, y así la vuelta a la fase 1 es segura en cualquier momento.

En `update.yml`, `activar.yml` y el job de Python de `tests.yml`, el primer paso que ejecuta algo de `scripts/`
es **«Montar la base»**: `python3 scripts/piezas.py montar --contra futbolbase.db` (en `update.yml`, justo antes
del bot y después de la IP y la nube del runner, que así salen en el registro también si no se puede montar; en
`activar.yml`, antes de «Qué hay pendiente», que abre la base). Monta `base/` en
`futbolbase.db` y, antes de ponerla en su sitio, la compara fila a fila con la `futbolbase.db` del commit
(`--contra`). Si no son la misma base, alguien ha subido solo una de las dos (a mano, o una pasada vieja de la
fase 1 cuyas piezas salieron mal) y hay que decidir a mano cuál vale: el paso sale en rojo, la pasada **no se
hace** y «Datos y fuentes» lo dice («no se pudo montar la base desde sus piezas: esta pasada no se ha hecho»).
Con las piezas rotas o sin `base/`, lo mismo.

Al acabar, **«Partir la base y comprobarla (bloquea el commit si falla)»** (`partir && verificar`), justo
después de «Base sana». Si las piezas no salen iguales a la base, ni suites ni subida, y el diagnóstico lo
publica («las piezas de la base no salieron iguales a la base: los datos de esta pasada no se publicaron»). En
el commit, `git add -A base/` va siempre junto a `git add futbolbase.db`, dentro de su puerta.

Si algo de esto falla, la web no se queda en blanco: sigue con lo último publicado, y «Datos y fuentes» lo
marca en rojo hasta que una pasada salga bien. Lo que sí se pierde es esa pasada. Si el fallo se repite
(`--contra` que no cuadra), el bot no publica hasta que alguien lo arregle.

Cómo se arregla un `--contra` que no cuadra: se mira qué commit subió solo una de las dos
(`git log -3 --stat -- futbolbase.db base/`) y se decide cuál es la buena. Si la buena es `futbolbase.db`:
`python3 scripts/piezas.py partir && python3 scripts/piezas.py verificar` y se suben las piezas. Si son las
piezas: `python3 scripts/piezas.py montar` (sin `--contra`) y se sube la base. En los dos casos, con el bot
parado (`gh workflow disable reloj.yml -R malolocabreralolo-tech/futbol-base-v2`).

Vuelta atrás: con el bot parado y nada en marcha, `git revert` del commit de esta fase. Es segura en
cualquier momento, porque cada subida de la fase 2 lleva `futbolbase.db` al día, que es lo que lee la fase 1.

Cuesta, por pasada: unos 11 s de montar (la comparación de `--contra` es casi todo) y los 14 s de partir y
verificar que ya había en la fase 1.

Si falla «Montar la base» o el paso de las piezas, lo que va después en la pasada sigue funcionando como con
cualquier otro fallo: «Publicar diagnóstico…» sube el informe en rojo, y «Relanzar si el runner fue rechazado»
corre igual (no lee la base) y, con el job en rojo, no relanza: la pasada la retoma el reloj. Una pasada rechazada
por AWS en la que montar y las piezas salen bien sube su informe y se relanza como hasta ahora.

Los demás workflows en la fase 2 (la tabla de arriba, «Quién lee la base»):

- **El carril de las mayores** (`carril-mayores.yml`) no tiene pasos: llama a `update.yml`, y hereda montar,
  partir y la subida de `base/` (lo prueba `test_el_carril_de_las_mayores_monta_y_parte_como_el_bot`).
- **El carril del histórico** (`historico.yml`) no cambia: no sube la base, y la que lee (la copia de la prueba,
  un `git worktree` de `main`) trae `futbolbase.db`, idéntica a las piezas. Montar en su checkout cambiaría un
  fichero versionado sin necesidad.
- **`mygol.yml`, las tandas de la federación, `reloj.yml`** y los demás no leen la base.
- **`freno-fiflp.yml`** (a mano) lee `futbolbase.db` del checkout, que en la fase 2 está en git: igual que hoy.

#### El cambio a la fase 2 (PASO DEL DIRECTOR)

Sin carrera con ninguna pasada: hoy lanzan el bot el reloj de GitHub (`reloj.yml`), el reloj del PC (`pc/reloj/`,
que cada 5 min lanza `reloj.yml`), el carril de las mayores (`carril-mayores.yml`, y su relanzamiento), el del
histórico (`historico.yml`, «Importar y publicar (bot)») y la propia pasada («Relanzar si el runner fue
rechazado»).

1. Parar todo lo que lanza o escribe el bot, y `mygol.yml` (su cron de los lunes, 04:17 UTC, sube a `main`):
   `for wf in reloj.yml carril-mayores.yml historico.yml update.yml activar.yml mygol.yml; do gh workflow disable "$wf" -R malolocabreralolo-tech/futbol-base-v2; done`.
   El reloj del PC solo lanza `reloj.yml`, que desactivado no corre; para que su registro no se llene de fallos,
   `systemctl --user stop futbol-base-v2-reloj.timer` en el PC (y `start` en el paso 7). Desactivar no cancela lo
   que ya estaba en marcha o esperando.
2. Esperar a que no quede nada en marcha ni esperando, de ningún workflow (la norma de no empujar con un workflow en
   marcha; una ejecución del histórico puede durar horas). Una ejecución parada por su grupo de concurrencia sale
   como `pending` o `waiting`, no como `queued`, y entre que acaba una y arranca la que espera hay un momento en que
   `in_progress` y `queued` salen vacías: se miran los cinco estados, hasta que todos den `[]`:

   ```sh
   for st in in_progress queued pending waiting requested; do gh run list -R malolocabreralolo-tech/futbol-base-v2 --status "$st" --json workflowName,databaseId; done
   ```
3. Antes de empujar, que el `main` de ahora tenga sus piezas iguales a su base (si la última pasada de la fase 1 salió
   con las piezas en rojo, subió `futbolbase.db` sin `base/`, y la primera de la fase 2 se pararía en «Montar»):

   ```sh
   git fetch origin && d=$(mktemp -d) && git archive origin/main base futbolbase.db | tar -x -C "$d" \
     && python3 scripts/piezas.py comparar --db "$d/futbolbase.db" --piezas "$d/base"; rm -rf "$d"
   ```

   Tiene que decir `iguales`. Si no, no se sigue: se vuelve a habilitar todo (paso 7) y se espera a una pasada de la
   fase 1 con las piezas en verde (`piezas iguales a la base` en su registro); después, otra vez desde el paso 1.
4. Subir el commit de la fase 2, rebasado sobre `main`: `git push origin <sha>:main`.
5. `for wf in update.yml activar.yml; do gh workflow enable "$wf" -R malolocabreralolo-tech/futbol-base-v2; done`, una pasada y seguirla. La ejecución
   nueva tarda unos segundos en salir en la lista: se sigue la creada después de lanzarla, no la última
   que haya (que puede ser una vieja, ya acabada):

   ```sh
   antes=$(date -u +%Y-%m-%dT%H:%M:%SZ); gh workflow run update.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main
   until id=$(gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml -L 5 --json databaseId,createdAt --jq "map(select(.createdAt >= \"$antes\")) | .[0].databaseId // empty") && [ -n "$id" ]; do sleep 5; done
   gh run watch -R malolocabreralolo-tech/futbol-base-v2 "$id" --exit-status
   ```
6. Comprobación: en su registro, `montada …/futbolbase.db: 9 piezas, …` y `piezas iguales a la base: …`; si subió
   algo, el commit lleva `futbolbase.db` y lo cambiado de `base/` (`git fetch origin && git show --stat
   origin/main`). Con `CARRIL_MAYORES` a 1, lo mismo en la primera pasada del carril.
7. `for wf in carril-mayores.yml historico.yml mygol.yml reloj.yml; do gh workflow enable "$wf" -R malolocabreralolo-tech/futbol-base-v2; done`
   (y el reloj del PC, si se paró).
8. Si algo falla en el paso 5 o en las pasadas siguientes: 1 y 2, `git revert --no-edit <commit de la fase 2>`,
   `git push origin main`, y 5 y 7. Volver es seguro en cualquier momento: en la fase 2 cada subida lleva
   `futbolbase.db` al día, que es lo que lee la fase 1. El revert solo sale limpio mientras la fase 2 sea lo último de
   la serie en `main`: con la descarga o la rama `web` ya encima, chocan `update.yml` y las huellas de
   `test_workflows.py`; entonces se revierten antes los de encima, del último al primero (o se resuelve el choque y
   se recalculan las huellas, como dice su comentario).
