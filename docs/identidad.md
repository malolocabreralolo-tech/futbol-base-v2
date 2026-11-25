# Quién es cada niño: identidades de acta y fichas

Desde la fase 2C la base separa dos cosas:

- la **identidad de acta** (una fila de `players`): lo que el acta dice con certeza;
- la **ficha** (el niño): un conjunto de identidades con una **principal**. `players.ficha_id` apunta a la principal (`NULL` en la principal) y `players.union_por` dice por qué se unió.

Las apariciones y los sucesos cuelgan siempre de la identidad de acta y no se mueven. La capa de fichas la recalcula entera `scripts/identidad.py::resolver`, un resolvedor puro (sin base ni red): para las mismas identidades da siempre lo mismo, en cualquier orden, y aplicado a su propio resultado no une nada más. Ante la duda, dos fichas mejor que una mezclada.

## Identidad de acta

- Con identificador de la federación: una por `fiflp_id` (`norm_name` `NOMBRE` o `NOMBRE#id`).
- Sin identificador: una por (nombre normalizado, equipo, temporada). En otro equipo u otra temporada, otra.
- Dos sin identificador con el mismo nombre en la **misma alineación**: el de dorsal más bajo es la identidad normal y el siguiente lleva ordinal (`…#2`, `…#3`), que forma parte de su identidad en ese equipo y temporada. Es una aproximación: el dorsal puede cambiar de un partido a otro y entonces los dos niños pueden cruzarse entre `X` y `X#2`; lo que no puede pasar es que se pierda una aparición o falle el acta.

Nombre normalizado: sin tildes, en mayúsculas y con espacios simples (`identidad.normalizar`, la misma que `import_fiflp_actas._norm_player`).

**El importador** (`import_fiflp_actas._import_one`, también el del bot) crea y usa estas identidades desde la fase 2C (`_get_or_create_player(conn, nombre, fiflp_id, team_id, season_id, ordinal)`): con id, la fila de ese id (nunca adopta una fila sin id ni devuelve la de otro id por el nombre); sin id, la de su nombre, el equipo y la temporada del partido, y el ordinal por dorsal como arriba. Quien sale en un suceso y no en la alineación de su lado es el de la alineación con el mismo nombre normalizado si lo hay (con dos o más, el último, como con el nombre exacto); si no, la identidad sin id de su equipo y temporada. Reimportar un acta deja las mismas filas. Cada pasada del bot, después de importar y de podar (`prune_players`, que no borra una fila a la que apunta otra por `ficha_id`) y antes de publicar, llama a `migrate_identidad.resolver_fichas`; si falla, la pasada se para.

**La identidad sin id sigue a sus apariciones** (`migrate_identidad.realinear`, lo primero de `resolver_fichas` y, en la migración, antes de separar). La verdad es `appearances`: `update_fiflp.merge_twin_teams`, `import_fiflp_grupos` (`_move_teams`, `fix_positions`) y `migrate_team_names` cambian `appearances.team_id` y `match_events.team_id`, y pueden borrar la fila vieja de `teams`, sin mirar `players`. Cada aparición (con los sucesos de ese jugador en ese partido y equipo) y cada suceso sin aparición cuyo equipo o temporada no son los de su identidad sin id pasan a la identidad sin id de (nombre, ese equipo, esa temporada, mismo ordinal), creándola si falta. Si todo lo de una identidad está en un único equipo y temporada que no es el suyo y esa identidad no existe, cambia la misma fila (`team_id`, `season_id`, `norm_name`): conserva su id y su clave. La aparición que chocaría con otra de la identidad destino en el mismo partido y equipo se queda donde está y se cuenta. Sin nada que mover no escribe nada. Y al publicar (`generate_js._fichas`), una identidad sin clave guardada cuyo equipo o temporada ya no existen toma la clave del equipo y la temporada en los que más aparece (a igualdad, el de `teams.id` menor) y, si ni así, su ficha sale con la clave de otra identidad suya: ninguna ficha se queda sin publicar.

## Las reglas

**Nombre con coma** (`identidad.nombre_con_coma`): con coma, al menos una palabra antes y al menos una después («APELLIDO(S), NOMBRE»). **Nombre completo** (`identidad.nombre_completo`): con coma y dos o más palabras antes («APELLIDO APELLIDO, NOMBRE»). Un nombre con coma y una sola palabra antes es de **un apellido**; sin coma (nombre de pila suelto, «A.»), **nombre corto**. El sufijo `#…` no cuenta.

**Club de un equipo** (`identidad.club`): el nombre sin la letra de filial. Es la regla de `baseKey` de `src/myteam.js` (la clave con la que la web agrupa los equipos de un club) sobre la normalización C1 que ya existe en Python (`generate_js.normalize_for_teams_mapping`, gemela de `normalizeForTeamsMapping`): quita las siglas (`UD`, `CD`, `CF`…, más `RC`, `US`, `CDA`, `CEF`) y la última palabra si es una letra de la A a la E. No usa escudos ni los alias de `TEAM_ALIASES`, como `baseKey`: dos grafías del mismo club que solo une el escudo cuentan como dos clubes (une menos).

**Edad** (`identidad.intervalo`): quien juega la temporada que empieza el año `Y` nació en prebenjamín `[Y-7, Y-5]`, en benjamín `[Y-9, Y-6]` y en alevín `[Y-11, Y-8]`.

**Compatibles**: un conjunto de identidades lo es si (a) los intervalos de edad de todas sus apariciones se cruzan y (b) no hay solape imposible: en una misma temporada y categoría, dos clubes distintos con rangos de fechas de partidos que se cruzan. Prebenjamín tres temporadas seguidas cabe; cuatro, no.

**Uniones**, por este orden, cada una sobre las fichas que dejó la anterior:

| | Regla | `union_por` |
|---|---|---|
| U0 | Identidad de un solo uso: el mismo nombre **con coma** (uno o más apellidos) en el mismo equipo y la misma temporada → la misma ficha. Después, la de los nombres **sin coma** (abajo). | `equipo` |
| U0 de club | Mismo club y misma temporada: las fichas con el mismo nombre **con coma**, del mismo club, en la misma temporada (equipos «X» y «X B», o prebenjamín y benjamín del club) → una, si en ese cubo hay **como mucho una** con identificador (abajo). | `club` |
| U1 | Mismo club, temporadas seguidas: dos fichas con el mismo nombre, del mismo club, en temporadas consecutivas y compatibles, de uno a uno, cuando **no tienen identificador las dos** (las dos sin él, o una con él y otra sin él, en cualquier orden de temporadas; dos con identificador no: manda el id). Los nombres sin coma solo si `unir_cortos_en_club` (la medida de abajo); los de coma, siempre. | `club` |
| U2 | Candidata única: una ficha sin ningún identificador y de nombre completo se une a la otra ficha con ese nombre cuando es la **única** y son compatibles. Con dos o más, a ninguna. Los de un apellido y los sin coma, nunca. | `nombre` |

**U0 de los nombres sin coma** (añadida el 14/11/2026, tras la medida de abajo; hasta la ronda 2 valía también para los de un apellido, que ahora van por la U0 normal): cubo de identidades **con identificador** y nombre sin coma, mismo nombre, mismo equipo y misma temporada. «De un solo uso» es la que tiene exactamente 1 aparición en total (sumando todas sus vistas); «asentada», todas las demás. Con **exactamente una** asentada, cada una de un solo uso se une a ella si caben; con dos o más asentadas (dos niños con el mismo nombre de pila en el equipo) o con ninguna (todas de un solo uso), no se une ninguna. Las sin identificador de nombre sin coma no entran (ya son una sola por nombre, equipo y temporada).

**U0 de club** (ronda de arreglo 3; va después de las dos U0 de equipo y antes de U1): cubo de fichas, tal como las dejaron las U0 de equipo, con el mismo nombre con coma, el mismo club (`club(equipo)`, no vacío) y la misma temporada. Si en el cubo hay como mucho una ficha con identificador, se unen todas (las sin identificador entre sí y con la que lo tiene), cada una a la primera del cubo con la que cabe (la que sería principal primero), como en U0; la que no cabe con ninguna se queda fuera. Con dos o más con identificador, nada (manda el id, y no se sabe de cuál es la que no lo tiene). Los nombres sin coma no entran (dos «DANIEL» en dos categorías de un club son probablemente dos niños), y una ficha con ordinal bloquea su cubo. El caso que la trajo: un niño sin identificador en prebenjamín de un club dos temporadas, con un partido con identificador en el benjamín B del club la segunda y el mismo identificador en otro club la tercera, salía en tres fichas (U0 no unía «X» y «X B»; U1 veía dos fichas en el club esa temporada); ahora la U0 de club une las dos de la segunda temporada y U1 la primera con ellas: una ficha, con la principal del identificador. Detrás de `identidad.U0_CLUB_COMPLETOS` y `U0_CLUB_UN_APELLIDO` (la medida de abajo).

Nada más une. Lo imposible por edad no se une nunca (tampoco en U0). Dos identidades que salen en el mismo partido con el mismo equipo (`migrate_identidad.pares_juntas`, solo las del mismo nombre: las demás no las une ninguna regla) son dos niños: dos fichas con una de cada una no se unen por ninguna regla, ni directa ni a través de otra (`resolver(…, juntas=pares)`; el caso que lo trajo: U0 unía dos identificadores del mismo nombre, equipo y temporada que jugaron el mismo partido).

**Principal**: la identidad con identificador que más apariciones tiene (a igualdad, el `fiflp_id` menor); si ninguna lo tiene, la de la temporada más antigua (a igualdad, la de más apariciones y luego el `id` menor). `union_por` de cada identidad es la regla de la unión que la juntó con la principal: si dos sin identificador de clubes distintos se unieron por U2 a la ficha de una con identificador, llevan `nombre`; si una sin identificador va a la del mismo club la temporada anterior o la siguiente, `club`.

**Clave pública** (`identidad.clave_publica`): el `fiflp_id` en decimal o, sin identificador, `n` + las 9 primeras cifras en base 36 (minúsculas) del SHA-1 de `"<nombre normalizado>|<nombre del equipo>|<año de inicio>"` en UTF-8, con el número escrito con 31 cifras (relleno con ceros por la izquierda: 31 es lo que ocupa un SHA-1 en base 36). El nombre lleva el ordinal si lo tiene (`X#2`). La de una identidad sin id se calcula **una vez**, con el nombre del equipo de ese momento, al crearla (el importador, `separar`, `realinear`; las que ya existían, `asegurar_esquema`), y se guarda en `players.clave` (índice único): renombrar o cambiar la fila del equipo (`activate_season.club_id`, `realinear`) no la cambia. Si otra fila ya la tiene (un equipo que hoy se llama como se llamaba otro), la nueva lleva la del nombre con `|<id de la fila>` (`X|1234`). Las que tienen id no la guardan (su clave es el id). La clave de una ficha es la de su principal; las de las demás identidades son **alias** que llevan a ella. **Trozo** (`identidad.trozo(clave, 64)`): numérica, `id % 64`; `n…`, `parseInt(resto, 36) % 64` (9 cifras en base 36 caben enteras en un número de JavaScript). Son 64 ficheros `data-jugadores-<k>.js` (`generate_js.JUGADORES_SHARDS`, `src/state.js` `JUGADORES_SHARDS`); eran 16 antes de la ampliación. La tabla `TABLA_CLAVES` de `scripts/tests/test_identidad.py` (22 casos) fija lo que deben dar Python y JavaScript; en JavaScript, `BigInt('0x' + sha1).toString(36).padStart(31, '0').slice(0, 9)`.

## Decisiones (lecturas de las reglas que unen menos)

1. **U1 es de uno a uno.** Si en una de las dos temporadas hay dos o más fichas con ese nombre en el club (con identificador o sin él; por ejemplo, un «LUCAS» en el equipo A y otro en el B al año siguiente), no se une ninguna: unir los tres por la cadena mezclaría a dos niños de la misma temporada, y el solape imposible no lo impide porque es el mismo club.
2. **U1 y los identificadores** (cambiada en la ronda de arreglo 2; antes U1 solo unía dos fichas sin ningún identificador). U1 une una ficha sin identificador con otra con o sin él; dos con identificador, nunca. Si los enlaces de uno a uno de un nombre en un club llevan de una ficha con identificador a otra con otro (con id en 2024, sin id en 2025, con id en 2026), la sin identificador puede ser de cualquiera de los dos niños: ese grupo de enlaces no se une entero (decisión de la ronda 2).
3. **El ordinal.** Las identidades `X` y `X#2` del mismo equipo y temporada no se unen nunca entre sí (U0 se salta a las que no tienen identificador en ese equipo y temporada si hay un ordinal), una ficha con ordinal no se une por U1 ni por U2, y cuenta como otra ficha del nombre `X` (así bloquea U2: no se sabe cuál de los dos es el otro).
4. **Sin fechas, se cruzan.** Si una vista no tiene fechas, no se puede descartar el solape imposible: se trata como si se cruzara.
5. **La fila «sin nombre publicado»** (`#SIN NOMBRE PUBLICADO`) y un nombre vacío no se unen nunca a nada.
6. **U0 reparte por compatibilidad.** En cada (nombre, equipo, temporada), cada identidad va a la primera ficha del grupo con la que cabe (la que sería principal primero); si no cabe con ninguna, empieza otra. Así el resultado es un punto fijo. La U0 de club hace lo mismo con las fichas de su cubo.

## La medida de los nombres cortos

`python3 scripts/medir_identidad.py` (solo lectura): con los originales de 2019-20 a 2023-24, cuando prebenjamín también traía el identificador, hace como si los jugadores con identificador no lo trajeran (cada nombre, equipo y temporada, una identidad sin identificador) y cuenta, de los pares que uniría U1 (mismo nombre, mismo club, temporadas consecutivas, compatibles), cuántos son el mismo niño (el mismo identificador, o el mismo niño tras U0: `resolver` sobre las identidades con identificador) y cuántos no, con los nombres completos, los de un apellido y los sin coma aparte. Los equipos son los de la base, por el `CodActa` del acta (con los nombres de la federación, la letra de filial no sale bien). «Todos» cuenta cada niño de un lado con cada niño del otro; «uno a uno», lo que une de verdad el resolvedor (decisión 1), y es la que decide para los sin coma. Salida del 14/11/2026, con las reglas de la ronda 2:

```
Originales: 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024 (equipos de la base, por CodActa).
  actas: 11292
  actas de una categoría que no se publica: 0
  actas sin partido en la base: 32
  apariciones: 261636
  apariciones sin id: 8
  apariciones con id: 261628
  ids de la federación: 12027; niños tras U0: 9525
  cubos de U0 sin coma: 0 con una asentada (se unen), 0 con dos o más (no se unen), 0 sin ninguna (no se unen)
Pares todos:
  nombres       pares   mismo distinto mezcla precisión
  completos      4378    4365       13      0     99.7%
  un apellido     102      99        3      0     97.1%
  sin coma         59      59        0      0    100.0%
Pares uno a uno:
  nombres       pares   mismo distinto mezcla precisión
  completos      3930    3919        6      5     99.7%
  un apellido      83      80        2      1     96.4%
  sin coma         53      53        0      0    100.0%
Precisión sin coma (uno a uno) 100.0 % ≥ 95 % → unir_cortos_en_club = True
```

**Resultado: `unir_cortos_en_club = True`** (`identidad.UNIR_CORTOS_EN_CLUB`). Los de un apellido, 96,4 % uno a uno. Los cubos cuentan solo los que tienen algo que unir: con una asentada y alguna de un solo uso, con dos o más asentadas y alguna de un solo uso, o sin asentada y con dos o más de un solo uso; entre 2019-20 y 2023-24 no hay ninguno sin coma (los identificadores de un solo uso de nombre corto eran de nombres de un apellido).

Historia de la cifra: sin ninguna U0 para los cortos (un apellido y sin coma juntos), la misma medida daba 33,2 % (todos) y 94,9 % (uno a uno), y los 318 pares distintos tenían todos en un lado un identificador con una sola aparición; con la U0 de una asentada (ronda 1), 35,7 % y 97,8 %, y los 285 pares distintos que quedaban eran de identificadores de un solo uso en cubos sin asentada (de 2 a 30 cada uno). Con la U0 normal para los de un apellido (ronda 2), esos cubos se unen: quedan 3 pares distintos de un apellido en «todos» y ninguno sin coma.

**La U0 de club**, medida igual (entre jugadores con identificador, tras U0): de los pares de (nombre con coma, equipo, temporada) con el mismo nombre, club y temporada y equipos distintos, que caben, cuántos son el mismo niño (`pares_club`); «cubos» cuenta los (nombre, club, temporada) con dos o más equipos, con un solo niño o con varios. Si la precisión de los completos bajara del 95 %, la regla no se activaría; si solo la de un apellido, quedaría solo para completos.

```
U0 de club (mismo nombre, club y temporada, equipos distintos):
  nombres       pares   mismo distinto no caben cubos 1 niño cubos varios precisión
  completos       324     322        2        0          319            2     99.4%
  un apellido      17      17        0        0           17            0    100.0%
  → U0_CLUB_COMPLETOS = True, U0_CLUB_UN_APELLIDO = True
```

**Resultado: la U0 de club, activa para completos (99,4 %) y de un apellido (100 %).**

## El año de nacimiento

Nadie publica la fecha de nacimiento: la ficha lleva un año **estimado** por las categorías en las que jugó el niño, con todas las filas de sus identidades (`scripts/nacimiento.py`, `estimar`). Salen de uno a tres años posibles (`"y"` en `data-jugadores-<k>.js`), y la web los enseña siempre como estimados («Nacido en 2017 (estimado)», «2016 o 2017», «entre 2007 y 2009»). Un año **confirmado** por una fuente pública se pone a mano en `scripts/anios_confirmados.json` (`{"<clave>": {"anio": 2016, "fuente": "…"}}`), con la clave de la ficha o de uno de sus alias; ese manda sobre el estimado y se publica con `"yc": 1`. El estimador no influye en las uniones (el resolvedor usa sus propias edades, `_EDAD` e `intervalo`). Para qué sirve el año (el ranking de los mejores de cada año) y cómo se explica al dueño: [`docs/ranking.md`](ranking.md).

## Limitaciones

- Cuando `realinear` pasa las apariciones de una identidad sin id a otra que ya existía (el niño jugó con los dos equipos que luego se juntaron), la vieja se queda vacía, la poda la borra y su clave deja de abrir la ficha (no queda como alias). Si todo lo suyo cambió a un único equipo y temporada donde no había identidad de su nombre, la fila se mueve entera y conserva la clave.

## Deshacer una unión

Una unión que no venga de un mismo identificador queda marcada (`union_por`). Para deshacerla, se añade la clave pública de la identidad (la que lleva a ella en la web: su `fiflp_id` o su `n…`, la de `players.clave`) a `scripts/identidad_separadas.json`, una lista versionada (hoy `[]`), por ejemplo `["n0abc12345", "228567"]`, y se sube; la siguiente pasada del bot la separa: `resolver_fichas` lee el fichero en cada pasada y esas identidades no se unen a nadie (su ficha son ellas solas, con su clave propia; sus apariciones no se mueven porque nunca se movieron). Siguen contando como otra ficha de su nombre, así que apartar una no hace que se una lo que antes no se unía (U1 de uno a uno, U2 de candidata única). Para separar a la principal de su ficha se pone su clave: las demás siguen unidas entre ellas. Quitar la clave de la lista la vuelve a unir en la pasada siguiente. Una clave que no es de ninguna identidad se ignora con un aviso en el registro de la pasada; un fichero que no sea una lista de textos para la pasada. Poner `ficha_id` a `NULL` a mano no sirve: `resolver` no recuerda nada y la pasada siguiente lo rehace.
