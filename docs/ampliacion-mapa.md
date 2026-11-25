# Ampliación: mapa del reconocimiento (25/11/2026)

Lo que se leyó y se midió antes de planificar la ampliación
([diseño](superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md)). Las líneas son las del árbol de
ese día: sirven para encontrar el sitio, no como referencia exacta.

## 1. Qué hay que tocar para una categoría nueva (infantil, cadete, juvenil)

**Quién decide la categoría**
- `scripts/categorias.py:19` `DB_NAME`, `:21` `DEFAULT_CATEGORIES` (no cambia: las nuevas se piden a
  propósito), `:23` y `:45` `ALEVIN_FUERA` (alevín de Lanzarote y Fuerteventura), `:37` solo excluye `SALA` y
  `LPFS` (hay una «COPA JUVENIL ISLA DE GRAN CANARIA FS» en 2024-25: falta `\bFS\b`), `:44` cadena de `if`,
  `:55` `excluded()` solo conoce alevín.
- Listas escritas a mano: `update_fiflp.py:152`, `:235-240` (`LEVELS`, `_level`: `startswith("AL")`, lo demás
  cae en benjamín), `:1651` `BACKFILL_ORDER`; `identidad.py:31-33` (`NIVEL`, `_EDAD`) y
  `migrate_identidad.py:754`; `import_fiflp_islas.py:119` (lo que no es benjamín pasa a prebenjamín);
  `activar_auto.py:236,243` y `activar.yml:101` (sufijos `""`/`"al"`); `fetch_fiflp_islas.py:163,168`;
  `check_missing_shields.py:15,35-41,103,121`.
- Ya generalizado (pasa por `category_of`/`parse_categories`): `fetch_fiflp_actas.py:96,432`,
  `fetch_fiflp_islas.py:146`, `fetch_fiflp_detalle.py:67`, `fetch_fiflp_goleadores.py:165`,
  `fetch_fp_app.py:147`, `discover_temporada.py:73`, `acta_reconciler.py:225`, `import_fp_app.py:104`,
  `import_fiflp_goleadores.py:46`, `activate_season.py:52,259`, `migrate_categories.py:58`.
- **Trampa**: `update_fiflp.py:599` `new_competitions` acepta todo lo que `category_of` reconozca. En cuanto
  reconozca infantil, sus competiciones entran en `newCompetitions` y `activar_auto` intenta activarlas solo.

**Códigos, fase e isla**
- `fiflp_manifest.py:51`, `:85-98` `_alevin_meta`, `:101-137` `comp_meta` (lo que no es alevín ni prebenjamín
  se trata como benjamín), «sin convenio» en `:98,114,128,137`, isla por prefijo en `:184-185`.
- `import_fiflp_grupos.py:84` `ISLAND_OF_PREFIX` (por `startswith`: un prefijo nuevo que empiece por `LZ`,
  `FV`, `CLZ`… hereda isla), `:216`, `:224` frente a `fetch_fiflp_islas.py:150-151` («LANZAROTE-FUERTEVENTURA»
  da una isla en un sitio y otra en el otro; «INTERINSULAR» acaba en Gran Canaria), `:230`, `:233-255`,
  `:258-322` `meta_by_name`, `:274`, `:341` (por nombre solo ALEVIN).
- Supuestos sobre el código: una letra suelta es la Segunda Fase de benjamín (`fiflp_manifest.py:53-73`);
  `state.js:96-97` `isCupGroup` (`PCC`/`BC`/`MCP`/`MCB`); `model.js:111` (`…KO`); `activate_season.py:49`
  exige `[A-Z][A-Z0-9_-]{0,19}`; el código es único en la temporada entre todas las categorías (`HISTORY`,
  `ESTADOS` y `data-lineups-<S>-<código>.js` van por código: `model.js:1002,1075`).
- Fases en la web: `model.js:326-385` `PHASE_TABLE`, `:1318` `PHASE_LEVEL`; lo que no casa acaba en «otra-…».

**Lotes de originales de actas**: `actas_lotes.py:32` `LOTES`, `:34` `RAW_FILE`, `:47-48` `lote_of`, `:62`;
`fetch_fiflp_actas.py:137,150-155`; `actas-federacion.yml:57,79,97,105,140` (lote binario con
`contains(…,'alev')`). `actas_bot.py:41` ya es por categoría.

**Bot en vivo**: `update_fiflp.py:144-153` `fiflp_groups(categories)`, `:1840-1847` `FIFLP_CATS` (los grupos
que no se leen conservan su entrada: `source_health.py:202` `carry`), turnos en `:541-549` con niveles
`(3,1,2)` fijos, cuota de alevín `:348-354` (`ALEVIN_MIN_GROUPS`, `:136`). `fetch_futbolaspalmas.py:22-25`.

**Temporadas pasadas**: `import_changed_raws` (`import_fiflp_actas.py:1010`) importa lo que liste
`actas_lotes.raw_files`; la purga (`:446-466`) filtra por las categorías del raw (un acta sin categoría
reconocida se compararía con toda la temporada: `acta_reconciler.py:222-226`); `import_fiflp_grupos.py:341`
y `:621-623`; `import_fiflp_detalle.py:569`.

**Generador** (casi todo escrito a mano para alevín): `generate_js.py:131-132`, `:149-156` (`_alevin_only`:
`cats == {ALEVIN}`; un equipo que solo juega en infantil entraría en la carga inicial), `:469`, `:567-580`
`generate_alevin_js`, `:636-650` (`MATCH_DETAIL` y `CAMPOS` van enteros en la carga inicial),
`:1133-1160`, `:1199`, `:1432-1453`, `:1495-1512`, `:1530-1543`, `:1664-1671`. `precache.py:76`.

**Web**: `model.js:307-310` (`CATEGORIES`, `CAT_*`), `:257-282`, `:390-396`, `:980-1098`; `state.js:186-205`,
`:434-526` (todo lo de alevín, con nombre fijo); `app.js:40,56`; `router.js:75-123`, `:185-231`, `:560-633`;
`shell.js:155-157`; `screen-goleadores.js:24` y `screen-records.js:16,91` (selector de categorías: con seis
no cabe en 320 px); `screen-partido.js:388,489`; `team-extras.js:117-142`; `pronostico.js:212`. Genéricas
(recorren `CATEGORIES`): Explorar, Ligas, Tabla, Jornada, Mi equipo, Temporadas.

**Pruebas que fijan la lista**: `test_categorias.py:48,86,119,148`, `test_competiciones_nuevas.py:48`,
`test_rediseno_alevin.mjs:46`, `test_rediseno_modulos.mjs:140`, `test_data_integrity.py:51,236,250,334`,
`test_actas_lotes.py:108-110,224,709-717`, `test_alevin_aislamiento.py`, `test_alevin_generador.py`,
`test_nombres_alevin.py`, `test_bot_rotacion.py`, `test_precache.py`, y el catálogo congelado
`fixtures/fiflp_comps_catalog.json`.

## 2. Las descargas por tandas, hoy

- **Ningún descargador por tandas sabe tratar el freno de la federación.** Solo el bot
  (`fiflp_carga.Federacion`). Las tandas leen con `fetch_fiflp_2425.goto` (`:90-107`) o
  `fetch_fiflp_actas.goto` (`:228-244`), que dan por cargada una página vacía con un 200. La última tanda de
  actas es del 7/10/2026; el freno, del 14/10.
  - Actas: un acta vacía se reintenta dos veces y no se guarda, sin esperas (`fetch_fiflp_actas.py:649-659`);
    una jornada vacía al enumerar se salta en silencio (`:492-503`) y el índice queda guardado, así que
    `_status.json` puede acabar con `pending 0` y la temporada incompleta (solo lo arregla `reindex=true`).
  - Goleadores y detalle: una página vacía se guarda como `ok` con la tabla vacía y no se vuelve a leer
    (`fetch_fiflp_goleadores.py:58-60`, `fetch_fiflp_detalle.py:149-169,224`).
- `actas-federacion.yml`: entradas `temporada` (12-22), `cola`, `tandas`, `comps`, `categorias`, `reindex`,
  `refrescar`; 2 navegadores, 320 min; sube solo los ficheros de su lote; se relanza mientras queden;
  concurrencia `actas-federacion-<T>[-alevin]`; lanza `update.yml` al acabar.
- `goleadores-federacion.yml` (`temporadas`, `escudos`, `categorias`), `detalle-federacion.yml`
  (`temporadas`, `jornadas`, `tandas`, `categorias`), `fetch-fiflp-islas.yml` (`temporada`, `ids`; solo sirve
  para la temporada en curso: listas fijas en `fetch_fiflp_islas.py:46-120`), `discover-fiflp.yml` (catálogo),
  `probe-fiflp.yml` (solo un artefacto).
- Código de temporada de la federación = año inicial − 2004 (15 = 2019-20 … 22 = 2026-27).
- Los grupos de una temporada pasada **solo se crean a partir del raw de goleadores**
  (`import_fiflp_grupos.py:585,601,680`): el orden es goleadores → actas → detalle.
- El bot importa solo lo que cambie (`fetch_futbolaspalmas.py:879-916`), dentro del mismo job de 40 min,
  después de la pasada. **Si un dato nuevo pone una prueba en rojo, la pasada no publica nada, tampoco lo de
  la temporada en curso**, y cada pasada repite lo mismo: `test_data_integrity.py:118,136,207`,
  `test_db_sanity.py:39,53,78,107,214,290,378,416`, `base_sana`. Hay que probar antes cada importación sobre
  una copia.
- Con categorías nuevas, hoy: `parse_categories` aborta con un nombre desconocido; goleadores y detalle no
  aceptan ids sueltos; `actas-federacion -f comps=<id>` sí, pero lo mandaría al raw de benjamín.

## 3. El freno de la federación, día a día

Páginas que la federación ha servido al bot (de `run.pages` en la historia de `data-health.json`):

| Días | Páginas al día | Pasadas sin freno |
|---|---|---|
| 16-20/10 | 100-730 | ninguna |
| 21/10 a 13/11 | 1.240-2.720 | todas |
| 14-17/11 | 880-2.020 | la mitad |
| 18-21/11 | 590-1.200 | la mitad |
| 22/11 | 537 | 1 de 16 |
| 23-25/11 | unas 200 | ninguna (8 de 11 frenadas desde la primera página) |

El estudio del 25/11 ([docs/freno-2026-11.md](freno-2026-11.md), 840 registros de v1 y v2) corrige la
lectura de esta tabla: el cupo de octubre (~15 páginas por IP y ~5 min de bloqueo) no se ha vuelto a ver en
Azure desde el 21/10. Lo de noviembre son dos cosas distintas:

- **Los runners en AWS.** Desde el 13/11 GitHub pone cerca de la mitad de los jobs en AWS, y la federación
  les sirve vacío desde la primera petición, siempre (183 de 183, también a v1); en Azure, ninguna pasada
  frenada desde la primera (0 de 187). De ahí las «frenadas desde la primera página».
- **Las páginas muertas.** Desde el 21/11 hay actas de alevín (ALD1, ALE2) cuya página sale vacía siempre.
  El bot las tomaba por el freno, no les gastaba intento y volvían las primeras en cada pasada: 22 de 25
  pasadas de v2 en Azure se quedaban 9-12 min sondeándolas (v1, en Azure, lo sirvió todo esos días).

El bot ya distingue las dos (desde el 25/11: `docs/federacion.md`, «Noviembre de 2026»). Para las tandas del
histórico: en Azure, ~124-138 páginas por pasada sin freno desde el 21/10; antes de escalar, una tanda corta
que mire la nube al arrancar y trate la página vacía (§2: hoy ninguna lo hace). El Archivo de Internet no
tiene las páginas de la federación.

## 4. Fichas de jugador, hoy

- Pantalla: `src/screen-jugador.js` (trayectoria por temporada; «Seguir», hasta 12, en la portada). Se llega
  desde el partido, la plantilla del equipo y los seguidos; no desde Goleadores ni Récords. No hay buscador
  de jugadores (`screen-explorar.js:33-48,163` y `model.js:1407` buscan equipos).
- Datos: `generate_js.py:1005-1093` `jugadores_files` → 16 `data-jugadores-<k>.js` (3,5 MB; 15.088 fichas,
  4.212 alias, 48.336 filas). El trozo es `id % 16` o, en las claves `n…`, sus 9 cifras en base 36 `% 16`
  (`identidad.py:109-112`, `state.js:376-404`). Subir el número de trozos obliga a cambiarlo a la vez en
  `generate_js.py:911`, `state.js:376` y la tabla `TABLA_CLAVES` de las pruebas.
- Resolvedor: `identidad.py:253` `resolver`, edades en `_EDAD` (`:33`) e `intervalo` (`:88-92`),
  `compatibles` (`:186-191`); se ejecuta en cada pasada (`fetch_futbolaspalmas.py:962-966`,
  `migrate_identidad.py:701-744`). Medido: 7,7 s con 19.301 identidades; crece de forma lineal (unos 50 s
  con seis veces más).
- No hay año de nacimiento en ningún sitio (solo dentro del resolvedor: `identidad.py:150-156`).
- Goles por jugador: `appearances.goals` (de los sucesos del acta), `scorers` (la tabla de goleadores, por
  nombre y sin id, que cubre también partidos sin acta). `GOL_*` son filas `[nombre, equipo, goles,
  partidos]` sin id (`generate_js.py:1164-1189`).
- Lo que dice un acta de cada niño: dorsal, `starter`/`sub` (suplente es convocado, no se sabe si jugó),
  goles. `match_events` solo tiene goles (ni cambios ni tarjetas); 4.749 goles van a «sin nombre publicado».
  No hay minutos ni posición.

## 5. Liga de escuelas (MyGol)

API `https://tusligascanarias.mygol.es/api`: `/tournaments` (visibles), `/tournaments/<id>` (400 si está
oculto), `/matches/fortournament/<id>` (también los ocultos), `/matches/<id>` (equipos y jugadores con id
estable, nombre y apellidos; `birthDate` en blanco; `dayResultSummary.gamesPlayed`).

| Temporada | Torneos de escuela (equipos, partidos) |
|---|---|
| 2022-23 | 32 (19, 146) · 33 (33, 288) · 34 (14, 118) |
| 2023-24 | 51 (13, 144) · 52 (28, 321) · 53 (20, 230) |
| 2024-25 | 66 (16, 177) · 67 (34, 759) · 68 (12, 174) |
| 2025-26 | 85 miniprebenjamín (18, 299) · 86 (17, 236) · 87 prebenjamín (33, 477) · 88 (9, 72) |
| 2026-27 | 95 prebenjamín (26, 314) · 96 benjamín (16, 229) · 97 miniprebenjamín (20, 270) · 101 alevín (10, 135) |

Sin marcadores ni goles. Los demás torneos (con marcador) son ligas de adultos. El Archivo de Internet no
guardó nada de esa web.
