# Ampliación, parte E1: infantil, cadete y juvenil (y alevín de Lanzarote y Fuerteventura), los datos — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el bot lea, active y guarde en `futbolbase.db` los grupos, calendarios, clasificaciones, goleadores y actas de infantil, cadete y juvenil de 2026-27 (fútbol, Gran Canaria, Lanzarote y Fuerteventura) y del alevín de Lanzarote y Fuerteventura, por pasos y en un carril aparte, sin cambiar el ritmo ni el reparto del bot de hoy y sin que la web cambie; y dejar preparado lo que necesita el histórico de esas categorías (parte F).

**Architecture:** Un solo sitio decide la categoría (`scripts/categorias.py`), que separa «la conozco» (`category_of`) de «el bot la activa» (`ACTIVABLES`), «la lee este carril» (`CARRILES`) y «la ve la web» (`EN_WEB`). Un módulo puro nuevo, `scripts/convenio.py`, da a cada competición de las categorías nuevas su prefijo de código, su fase legible y su isla con un algoritmo sobre el nombre, comprobado contra el catálogo entero de 2019-20 a 2026-27. El bot de hoy pasa a leer por defecto solo su carril (prebenjamín, benjamín y alevín); las categorías nuevas las lee `update.yml` llamado desde un workflow nuevo (`carril-mayores.yml`, con su propio número de pasada) que el reloj lanza fuera de las ventanas de partidos y entre dos pasadas del bot, en el mismo grupo de concurrencia. El generador trabaja sobre una copia de la base con solo las categorías de la web (`scripts/vista_web.py`), y el resolvedor de fichas solo mira esas categorías: lo nuevo está en la base pero no sale hasta E2.

**Tech Stack:** Python 3.11 en Actions (3.12 en el PC) con la biblioteca estándar; sqlite3; pytest 9.2.0 y pyyaml 6.0.3; Node 22 (`node --test`) para las suites de la web; GitHub Actions (`ubuntu-24.04`, `actions/checkout@v5`, `actions/setup-python@v6`, `actions/setup-node@v5`, workflows reutilizables con `workflow_call`, variables del repositorio `vars.*`) y `gh`.

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (parte E; decisiones 4 y 5). Mapa del código: `docs/ampliacion-mapa.md`, sección 1 (las líneas son del 25/11 por la mañana: índice, no referencia). El contrato que se generaliza: `docs/alevin.md`. El bot: `docs/federacion.md` («El bot», «El reloj de las pasadas», «La activación automática», «El carril del histórico», «Noviembre de 2026»), `docs/freno-2026-11.md`. Identidad y ranking: `docs/identidad.md`, `docs/ranking.md`. La web de E2: `docs/superpowers/plans/2026-11-25-ampliacion-e2-categorias-web.md`.

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-categorias`, rama `categorias`. No se toca la versión 1 (`/home/manolo/claude/futbol-base`) ni ningún otro árbol.
- Nunca una petición a fiflp.com ni a ninguna otra web, ni desde el PC ni en las pruebas (páginas, catálogos y federación falsos; `scripts/tests/federacion_falsa.py`).
- No se lanzan workflows (`gh workflow run`), no se hace `git push` ni `git stash`, no se cambian variables del repositorio (`gh variable set`): eso son PASOS DEL DIRECTOR.
- No se ejecutan `scripts/publicar.py`, `scripts/generate_js.py` ni `scripts/fetch_futbolaspalmas.py` sobre el árbol, ni nada que escriba `futbolbase.db`, `base/` o `data-*.js` del árbol. Las pruebas trabajan con copias (API `backup` de sqlite3) en directorios temporales y con árboles temporales (`git worktree add --detach`), que se borran al acabar.
- No se modifica `futbolbase.db` ni `base/`. La base solo la escribe el bot (`update.yml`, también cuando lo llama `carril-mayores.yml`, y `activar.yml`, grupo `update-data`).
- Ningún nombre real de niño en código, pruebas, documentos ni mensajes de commit: nombres inventados («GOMEZ PEREZ, RAUL») o claves. Los nombres de clubes y de competiciones sí (son públicos y ya están en el repositorio).
- Fútbol sala nunca (tampoco «FS» o «F.S.» sueltos ni «LPFS»); ninguna liga femenina; ninguna de mayores.
- **El bot no puede dejar de publicar.** La puerta de pruebas del bot (`update.yml`, «Tests Python» y «Tests Node») corre DESPUÉS de sus pasos de importación: toda prueba que mire la base real o los `data-*.js` del árbol tiene que valer con la base de hoy y con la de después de que el bot haya activado y leído las categorías nuevas. Cada tarea que toca una prueba así, o algo que lee la base real, acaba pasando la suite entera en ese estado con `python3 scripts/prueba_mayores.py` (tarea 6) además de en el árbol.
- El bot de hoy no cambia de ritmo ni de reparto: con `FIFLP_CATS` vacía lee prebenjamín, benjamín y alevín exactamente en el mismo orden que antes de este plan (prueba de oro de la tarea 7), y una pasada del carril nuevo nunca retrasa una del bot (simulación de la tarea 9).
- Reconocer una categoría no dispara nada: el bot solo activa lo de `categorias.ACTIVABLES` (y el alevín de Lanzarote y Fuerteventura solo con `categorias.ALEVIN_ISLAS = True`), y solo lee las categorías de su carril. Ninguna tarea de este plan cambia `ACTIVABLES`, `ALEVIN_ISLAS` ni `EN_WEB`: lo hace el director, por pasos.
- Cada tarea, publicada sola, deja `main` funcionando y la web exactamente igual (los `data-*.js` iguales byte a byte salvo `COBERTURA.mb` y las versiones `?v=`, que dependen del tamaño de la base). La única diferencia visible permitida es «Datos y fuentes», que lista con su código los grupos nuevos que compruebe el carril.
- No se empuja a `main` con un workflow en marcha (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --status in_progress` y `--status queued`, vacías): la base es binaria.
- No se intenta saltar el freno ni el rechazo a AWS: un carril más no es una IP más a la vez; va en el grupo `update-data`, nunca a la vez que otra pasada.
- Estilo: el del fichero que se toca (comentarios y docstrings en español que explican el porqué; mensajes del registro en español; escritura atómica con `escritura.escribir_atomico`; entradas de los workflows por `env:`, nunca interpoladas en un `run:`). Las pruebas de Python corren sin Playwright (se importa solo dentro de los `main()`).
- Cada commit acaba con las dos líneas `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.
- Lo marcado **PASO DEL DIRECTOR** no lo hace el implementador: lo deja escrito y se para.

## Review Focus

- **La base de después pone una prueba en rojo en el bot** (una prueba «sobre la base real» que cuenta categorías, partidos o grupos de la temporada en curso sin filtrar por las de la web; o que compara `data-*.js` con la base entera): el bot dejaría de publicar en cuanto active infantil. Prueba: tarea 6, `python3 scripts/prueba_mayores.py` (la suite entera en un árbol temporal con la base real más infantil, cadete y juvenil activados y leídos) en verde, y `test_generador_igual_con_y_sin_mayores`.
- **Un niño de cadete que ya está en la base como benjamín** (la federación le da el mismo identificador): sus apariciones nuevas caen en la misma fila de `players`. Antes de E2 su ficha, su año y el ranking no cambian; y dos niños de categorías incompatibles nunca se unen. Pruebas: tarea 5 `test_resolver_no_mira_categorias_fuera_de_la_web` y `test_edades_nuevas_separan`, tarea 6 `test_generador_igual_con_y_sin_mayores` (con jugadores de la base reutilizados).
- **Dos competiciones de una temporada con el mismo prefijo** (o un prefijo nuevo que lee otro código por `startswith`: `LZ`, `FV`, `CLZ`, `PCC`, `BC`, `AL` + letra): dos grupos con el mismo código pisarían sus `data-lineups`, su `HISTORY` y su comprobación. Prueba: tarea 2 `test_el_catalogo_entero_sin_choques`.
- **Una pasada del carril retrasa o descoloca el bot de hoy** (gasta su número de pasada, reinicia el reloj de `reloj_pasadas.due` o cancela su ejecución pendiente en `update-data`): Pruebas: tarea 7 `test_plan_principal_igual_que_antes`, tarea 9 `test_semana_con_carril` y `test_carril_no_comparte_numero_ni_reloj`.
- **Una competición nueva sin convenio o una categoría aún no activable** (la «ELIMINATORIA DESEMPATE CADETE INSULAR» de 2026-27; infantil antes de su paso): no se carga, no rompe la activación de las demás y «Datos y fuentes» lo dice. Pruebas: tarea 1 `test_new_competitions_solo_las_activables`, tarea 8 `test_desempate_falla_sin_convenio`.

## Lo medido (25/11/2026, con el catálogo del árbol y una copia de solo lectura de la base)

- **Catálogo** (`scripts/fiflp_comps_catalog.json`, 11 temporadas): de 2019-20 a 2026-27, **139 nombres distintos** de infantil (35), cadete (47) y juvenil (32) y de alevín de Lanzarote y Fuerteventura (25), sin sala ni femenino. El congelado de las pruebas (`scripts/tests/fixtures/fiflp_comps_catalog.json`) tiene 44 competiciones en 2026-27 y el vivo 72: se actualiza en la tarea 1.
- **2026-27**: 24 competiciones de las categorías nuevas: juvenil 6, cadete 11, infantil 5, alevín de islas 2. Con convenio, 23; sin convenio, 1 («ELIMINATORIA DESEMPATE CADETE INSULAR»: no dice la isla, y el insular existe en las tres).
- **Grupos**: el catálogo no los dice (no hay ningún raw de estas categorías). Estimación con el tamaño habitual de esas ligas: **~45 grupos** (juvenil ~10, cadete ~17, infantil ~14, alevín de islas ~4), entre 35 y 60; ~520 equipos; ~7.000 actas de fútbol 11 en la temporada (~2.300 a 25/11). El número de verdad sale de `scripts/fiflp_islas_22<sufijo>_grupos.json` en cuanto se descargue cada categoría (pasos del director).
- **Bot de hoy**: 107 grupos (alevín 51, benjamín 47, prebenjamín 9). Una pasada en Azure sin freno lee ~137 páginas (16 min, 7 s por página) y ~34 grupos (~4 páginas por grupo con sus goleadores y actas). Cerca de la mitad de los runners caen en AWS y no leen nada.
- **Base**: 47,6 MB; 18.847 actas; 23,3 apariciones por acta en fútbol 7/8 (alevín 23,6). Lo de las actas son ~1,7 KB por acta. En fútbol 11 se esperan ~36 apariciones por acta: ~2,4 KB por acta.
- **Originales del bot**: `actas_bot_2026-2027_alevin.jsonl`, 1,6 MB para 543 actas (~3 KB); en fútbol 11, ~4,5 KB.

## El convenio de códigos

Lo implementa la tarea 2 (`scripts/convenio.py`). Para las competiciones de **infantil, cadete y juvenil** (siempre) y las de **alevín cuyo nombre dice Lanzarote o Fuerteventura** (el alevín de Gran Canaria sigue con `docs/alevin.md`, sin cambios):

```
código = CATEGORÍA + NIVEL + ISLA + FASE + TIPO + número de grupo
```

1. **Nombre**: sin tildes, en mayúsculas; `1ª`/`2ª` → `PRIMERA`/`SEGUNDA`; lo que no es letra ni cifra, espacio; fuera la modalidad (`F-8`, `F8`, `F7`, `FUTBOL-8`…), `GRUPO <n>`, `DE LAS PALMAS`, un guion inicial; espacios simples.
2. **Fuera** (`SinConvenio("no se publica")`): `SALA`, `FS` suelto, `LPFS`, `FEMENIN…`, `FUTUREFEM`, `PLAYA`, `VETERAN…`.
3. **CATEGORÍA** (la palabra, también `INFANTILL`): `INF`, `CAD`, `JUV`, `AL`. Se quita del nombre.
4. **TIPO**, por este orden: `FINAL`/`SEMIFINAL(ES)` delante → el convenio del resto (que tiene que ser liga o copa) más `F`/`S`, fase «Final Liga X» o «Final X» (la de una copa ya empieza por «Copa»); `FASE FINAL` detrás → el de la liga más `F`, «Final Liga X»; `ELIMINATORIA(S) COPA …` o `COPA … ELIMINATORIAS` → el de la copa más `E`, «Eliminatorias X»; `ELIMINATORIAS DE ASCENSO A …` → `E` sobre el nivel e isla del destino, «Eliminatorias de Ascenso a X»; `FASE (DE) ASCENSO (A) …` → `A`, «Fase de Ascenso a X»; cualquier otra `ELIMINATORIA`, `PLAY OFF`, `DESEMPATE`, `TORNEO` o `CLAUSURA` → `SinConvenio("tipo de competición sin convenio")`; `COPA …` → `CK` si dice `CAMPEON` («Copa de Campeones»), `CD` si dice `DELEGACION` («Copa Delegación X»), `C` si dice `CABILDO` («Copa Cabildo X») o es otra copa («Copa X»); lo demás es una liga (con `LIGA` o sin ella).
5. **FASE** (de una liga, también dentro de una copa o un ascenso): `SEGUNDA FASE`, `2 FASE`, `FASE 2` → `SF`, « Fase 2»; `PRIMERA FASE`, `FASE 1` → sin token, « Fase 1»; `FASE ORO` → `FO`; `FASE PLATA` → `FP`; `SUBGRUPO X` → la letra detrás (` X` en la fase). Otra `FASE` que quede → `SinConvenio("fase desconocida")`.
6. **NIVEL** (uno; con dos, `SinConvenio("dos niveles en el nombre")`, salvo `INSULAR B`, que manda sobre `INSULAR`): `DIVISION (DE) HONOR` → `H` «División de Honor»; `AUTONOMIC[AO]` → `A` «Autonómica»; `INTERINSULAR` → `I` «Interinsular»; `TERRITORIAL` → `T` «Territorial»; `SUPERLIGA` → `S` «Superliga»; `PREFERENTE` → `P` «Preferente»; `PRIMERA` → `1` «Primera»; `SEGUNDA` → `2` «Segunda»; `INSULAR B` → `NB` «Insular B»; `INSULAR` → `N` «Insular»; ninguno → `U` (sin palabra).
7. **ISLA**: `LANZAROTE` y `FUERTEVENTURA` → `X` (Lanzarote-Fuerteventura, isla de la base `interinsular`); `LANZAROTE` → `L` (`lanzarote`); `FUERTEVENTURA` → `F` (`fuerteventura`); `GRAN CANARIA` → `G` (`grancanaria`); ninguna → sin token si el nivel es `H`, `A`, `I` o `T` (isla de la base `interinsular`), y si no, `G` (la federación nombra sin isla muchas de Gran Canaria: «COPA CAMPEONES INFANTIL», «COPA FIFLP CADETE PRIMERA»).
8. **Fase legible**: con nivel, «<Nivel> <isla corta>» (`GC`, `Lanzarote`, `Fuerteventura`, `Lanzarote-Fuerteventura`; sin isla, «<Nivel>»); sin nivel (`U`), la isla larga («Gran Canaria», «Lanzarote»…); más la fase del punto 5 y lo del tipo del punto 4. Son las mismas formas que usan benjamín y alevín donde existen («Preferente Lanzarote», «Lanzarote Fase 1», «Copa Cabildo Primera Lanzarote», «Final Liga Primera Lanzarote», «Copa de Campeones»).
9. **Grupos de eliminatoria dentro de una liga** («Eliminatoria de Primeros…» en el desplegable de una liga): el prefijo de la liga más `EL` y la fase «Eliminatorias <fase de la liga>», numerados tras los que ya tenga la temporada, como hoy `EL`/`PEL`/`ALEL`.
10. **Por qué no chocan**: todo prefijo empieza por `INF`, `CAD`, `JUV` o `AL` + al menos dos caracteres, acaba en letra y tiene como mucho 17 caracteres (el número va detrás, así que dos prefijos distintos nunca dan el mismo código). Los de alevín de islas siempre llevan nivel e isla tras `AL` (`ALUL`, `ALPL`, `AL1L`…): nunca son `AL` + una letra (la Segunda Fase), `ALP`, `ALCC…`, `ALCL` ni `ALEL`. Ninguno empieza por `LZ`, `FV`, `CLZ`, `CFV`, `PLZ`, `PFV`, `PCC`, `BC`, `MCP` ni `MCB`, ni acaba en `KO`.

**La tabla resultante** (2019-20 a 2026-27; la fixture `scripts/tests/fixtures/convenio_mayores.json` de la tarea 2 lleva estas filas tal cual, `{"<nombre>": [prefijo, fase, isla, tipo]}`, con el nombre con los espacios simplificados):

| Nombre en el catálogo | Temporadas | Prefijo | Fase | Isla | Tipo |
|---|---|---|---|---|---|
| LIGA PRIMERA INFANTIL DE GRAN CANARIA | 19-20 a 26-27 | `INF1G` | Primera GC | grancanaria | liga |
| LIGA PRIMERA INFANTIL DE LANZAROTE | 19-20 a 24-25 | `INF1L` | Primera Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE PRIMERA INFANTIL | 23-24, 24-25 | `INF1LC` | Copa Cabildo Primera Lanzarote | lanzarote | copa |
| FINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTIL | 23-24 | `INF1LCF` | Final Copa Cabildo Primera Lanzarote | lanzarote | final |
| FINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTILL | 24-25 | `INF1LCF` | Final Copa Cabildo Primera Lanzarote | lanzarote | final |
| SEMIFINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTIL | 24-25 | `INF1LCS` | Semifinal Copa Cabildo Primera Lanzarote | lanzarote | final |
| FINAL LIGA PRIMERA INFANTIL LANZAROTE | 22-23, 23-24, 24-25 | `INF1LF` | Final Liga Primera Lanzarote | lanzarote | final |
| LIGA INFANTIL PREFERENTE DE GRAN CANARIA | 19-20 a 26-27 | `INFPG` | Preferente GC | grancanaria | liga |
| INFANTIL PREFERENTE DE GRAN CANARIA FASE FINAL | 25-26 | `INFPGF` | Final Liga Preferente GC | grancanaria | final |
| LIGA INFANTIL PREFERENTE DE GRAN CANARIA FASE ORO | 25-26 | `INFPGFO` | Preferente GC Fase Oro | grancanaria | liga |
| LIGA INFANTIL PREFERENTE DE GRAN CANARIA FASE PLATA | 25-26 | `INFPGFP` | Preferente GC Fase Plata | grancanaria | liga |
| LIGA INFANTIL PREFERENTE DE LANZAROTE | 24-25 | `INFPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA PREFERENTE INFANTIL LANZAROTE | 19-20 a 23-24 | `INFPL` | Preferente Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE PREFERENTE INFANTIL | 23-24, 24-25 | `INFPLC` | Copa Cabildo Preferente Lanzarote | lanzarote | copa |
| FINAL COPA CABILDO DE LANZAROTE PREFERENTE INFANTIL | 23-24, 24-25 | `INFPLCF` | Final Copa Cabildo Preferente Lanzarote | lanzarote | final |
| LIGA INFANTIL DE FUERTEVENTURA | 23-24 | `INFUF` | Fuerteventura | fuerteventura | liga |
| LIGA INFANTIL DE FUERTEVENTURA 1ª FASE | 25-26, 26-27 | `INFUF` | Fuerteventura Fase 1 | fuerteventura | liga |
| LIGA INFANTIL DE FUERTEVENTURA PRIMERA FASE | 24-25 | `INFUF` | Fuerteventura Fase 1 | fuerteventura | liga |
| LIGA INFANTIL FUERTEVENTURA | 19-20 a 22-23 | `INFUF` | Fuerteventura | fuerteventura | liga |
| COPA INFANTIL FUERTEVENTURA | 21-22, 22-23, 23-24 | `INFUFC` | Copa Fuerteventura | fuerteventura | copa |
| COPA DELEGACION INFANTIL FUERTEVENTURA | 22-23 | `INFUFCD` | Copa Delegación Fuerteventura | fuerteventura | copa |
| FINAL COPA INFANTIL FUERTEVENTURA | 21-22, 22-23 | `INFUFCF` | Final Copa Fuerteventura | fuerteventura | final |
| FINAL LIGA INFANTIL FUERTEVENTURA | 21-22, 22-23 | `INFUFF` | Final Liga Fuerteventura | fuerteventura | final |
| LIGA INFANTIL FUERTEVENTURA 2ª FASE | 24-25, 25-26 | `INFUFSF` | Fuerteventura Fase 2 | fuerteventura | liga |
| LIGA INFANTIL GRAN CANARIA | 26-27 | `INFUG` | Gran Canaria | grancanaria | liga |
| COPA CAMPEONES INFANTIL | 25-26 | `INFUGCK` | Copa de Campeones | grancanaria | copa |
| COPA DE CAMPEONES INFANTIL GRAN CANARIA | 23-24, 24-25 | `INFUGCK` | Copa de Campeones | grancanaria | copa |
| LIGA INFANTIL LANZAROTE FASE 1 | 25-26, 26-27 | `INFUL` | Lanzarote Fase 1 | lanzarote | liga |
| COPA CABILDO DE LANZAROTE INFANTIL | 22-23 | `INFULC` | Copa Cabildo Lanzarote | lanzarote | copa |
| COPA DELEGACION INFANTIL LANZAROTE | 21-22 | `INFULCD` | Copa Delegación Lanzarote | lanzarote | copa |
| FINAL COPA DELEGACION INFANTIL LANZAROTE | 21-22 | `INFULCDF` | Final Copa Delegación Lanzarote | lanzarote | final |
| SEMIFINAL COPA DELEGACION INFANTIL LANZAROTE | 21-22 | `INFULCDS` | Semifinal Copa Delegación Lanzarote | lanzarote | final |
| FINAL COPA CABILDO DE LANZAROTE INFANTIL | 22-23 | `INFULCF` | Final Copa Cabildo Lanzarote | lanzarote | final |
| SEMIFINAL COPA CABILDO DE LANZAROTE INFANTIL | 22-23 | `INFULCS` | Semifinal Copa Cabildo Lanzarote | lanzarote | final |
| LIGA INFANTIL DE LANZAROTE FASE 2 | 25-26 | `INFULSF` | Lanzarote Fase 2 | lanzarote | liga |
| LIGA PRIMERA CADETE DE GRAN CANARIA | 19-20, 20-21 | `CAD1G` | Primera GC | grancanaria | liga |
| COPA FIFLP CADETE PRIMERA | 21-22, 22-23, 23-24 | `CAD1GC` | Copa Primera GC | grancanaria | copa |
| LIGA PRIMERA CADETE DE LANZAROTE | 19-20, 20-21 | `CAD1L` | Primera Lanzarote | lanzarote | liga |
| LIGA CADETE AUTONÓMICA | 21-22 a 24-25 | `CADA` | Autonómica | interinsular | liga |
| FASE DE ASCENSO A CADETE AUTONÓMICO | 22-23 a 25-26 | `CADAA` | Fase de Ascenso a Autonómica | interinsular | ascenso |
| LIGA CADETE INTERINSULAR | 23-24 a 26-27 | `CADI` | Interinsular | interinsular | liga |
| LIGA CADETE INTERINSULAR DE LAS PALMAS | 20-21, 21-22, 22-23 | `CADI` | Interinsular | interinsular | liga |
| FASE DE ASCENSO A CADETE INTERINSULAR | 21-22 a 25-26 | `CADIA` | Fase de Ascenso a Interinsular | interinsular | ascenso |
| ELIMINATORIAS DE ASCENSO A CADETE INTERINSULAR (LANZAROTE) | 21-22, 22-23, 24-25 | `CADILE` | Eliminatorias de Ascenso a Interinsular Lanzarote | lanzarote | eliminatorias |
| FASE DE ASCENSO A CADETE INTERINSULAR (LANZAROTE-FUERTEVENTURA) | 25-26 | `CADIXA` | Fase de Ascenso a Interinsular Lanzarote-Fuerteventura | interinsular | ascenso |
| ELIMINATORIAS DE ASCENSO A CADETE INTERINSULAR (LANZAROTE-FUERTEVENTURA) | 22-23, 23-24, 24-25 | `CADIXE` | Eliminatorias de Ascenso a Interinsular Lanzarote-Fuerteventura | interinsular | eliminatorias |
| LIGA CADETE INSULAR B DE LANZAROTE | 23-24, 24-25 | `CADNBL` | Insular B Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE CADETE INSULAR B | 24-25 | `CADNBLC` | Copa Cabildo Insular B Lanzarote | lanzarote | copa |
| FINAL COPA CABILDO DE LANZAROTE CADETE INSULAR B | 24-25 | `CADNBLCF` | Final Copa Cabildo Insular B Lanzarote | lanzarote | final |
| LIGA CADETE INSULAR DE FUERTEVENTURA | 21-22 a 26-27 | `CADNF` | Insular Fuerteventura | fuerteventura | liga |
| FASE ASCENSO CADETE INSULAR DE FUERTEVENTURA | 22-23, 23-24, 24-25 | `CADNFA` | Fase de Ascenso a Insular Fuerteventura | fuerteventura | ascenso |
| LIGA CADETE INSULAR DE GRAN CANARIA | 21-22, 22-23 | `CADNG` | Insular GC | grancanaria | liga |
| LIGA CADETE INSULAR GRAN CANARIA | 23-24, 24-25, 25-26 | `CADNG` | Insular GC | grancanaria | liga |
| LIGA CADETE INSULAR GRAN CANARIA 1ª FASE | 26-27 | `CADNG` | Insular GC Fase 1 | grancanaria | liga |
| COPA CADETE INSULAR GRAN CANARIA | 25-26 | `CADNGC` | Copa Insular GC | grancanaria | copa |
| COPA CADETE INSULAR GRAN CANARIA ELIMINATORIAS | 25-26 | `CADNGCE` | Eliminatorias Copa Insular GC | grancanaria | eliminatorias |
| LIGA CADETE INSULAR DE LANZAROTE | 21-22 a 26-27 | `CADNL` | Insular Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE CADETE INSULAR | 23-24, 24-25, 25-26 | `CADNLC` | Copa Cabildo Insular Lanzarote | lanzarote | copa |
| COPA CADETE INSULAR DE LANZAROTE | 22-23, 26-27 | `CADNLC` | Copa Insular Lanzarote | lanzarote | copa |
| ELIMINATORIAS COPA CADETE INSULAR DE LANZAROTE | 26-27 | `CADNLCE` | Eliminatorias Copa Insular Lanzarote | lanzarote | eliminatorias |
| FINAL COPA CABILDO DE LANZAROTE CADETE INSULAR | 23-24, 24-25, 25-26 | `CADNLCF` | Final Copa Cabildo Insular Lanzarote | lanzarote | final |
| FINAL COPA CADETE INSULAR LANZAROTE | 22-23 | `CADNLCF` | Final Copa Insular Lanzarote | lanzarote | final |
| CADETE PREFERENTE GRAN CANARIA | 25-26 | `CADPG` | Preferente GC | grancanaria | liga |
| LIGA CADETE PREFERENTE DE GRAN CANARIA | 19-20, 20-21 | `CADPG` | Preferente GC | grancanaria | liga |
| LIGA CADETE PREFERENTE GRAN CANARIA | 26-27 | `CADPG` | Preferente GC | grancanaria | liga |
| FASE DE ASCENSO A CADETE PREFERENTE | 25-26 | `CADPGA` | Fase de Ascenso a Preferente GC | grancanaria | ascenso |
| LIGA CADETE PREFERENTE DE LANZAROTE | 25-26 | `CADPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA CADETE PREFERENTE LANZAROTE | 26-27 | `CADPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA PREFERENTE CADETE LANZAROTE | 19-20, 20-21 | `CADPL` | Preferente Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE CADETE PREFERENTE | 25-26 | `CADPLC` | Copa Cabildo Preferente Lanzarote | lanzarote | copa |
| COPA CADETE PREFERENTE DE LANZAROTE | 26-27 | `CADPLC` | Copa Preferente Lanzarote | lanzarote | copa |
| ELIMINATORIAS COPA CADETE PREFERENTE DE LANZAROTE | 26-27 | `CADPLCE` | Eliminatorias Copa Preferente Lanzarote | lanzarote | eliminatorias |
| FINAL COPA CABILDO DE LANZAROTE CADETE PREFERENTE | 25-26 | `CADPLCF` | Final Copa Cabildo Preferente Lanzarote | lanzarote | final |
| LIGA CADETE FUERTEVENTURA | 19-20, 20-21 | `CADUF` | Fuerteventura | fuerteventura | liga |
| COPA CADETE FUERTEVENTURA | 19-20, 22-23 | `CADUFC` | Copa Fuerteventura | fuerteventura | copa |
| COPA DELEGACION CADETE FUERTEVENTURA | 22-23 | `CADUFCD` | Copa Delegación Fuerteventura | fuerteventura | copa |
| FINAL COPA CADETE FUERTEVENTURA | 22-23 | `CADUFCF` | Final Copa Fuerteventura | fuerteventura | final |
| COPA CAMPEON DE CAMPEONES CADETE FUERTEVENTURA | 19-20 | `CADUFCK` | Copa de Campeones | fuerteventura | copa |
| FINAL LIGA CADETE FUERTEVENTURA | 19-20 | `CADUFF` | Final Liga Fuerteventura | fuerteventura | final |
| COPA DELEGACION CADETE LANZAROTE | 21-22 | `CADULCD` | Copa Delegación Lanzarote | lanzarote | copa |
| FINAL COPA DELEGACION CADETE LANZAROTE | 21-22 | `CADULCDF` | Final Copa Delegación Lanzarote | lanzarote | final |
| LIGA PRIMERA JUVENIL DE GRAN CANARIA | 19-20 a 25-26 | `JUV1G` | Primera GC | grancanaria | liga |
| LIGA PRIMERA JUVENIL GRAN CANARIA | 26-27 | `JUV1G` | Primera GC | grancanaria | liga |
| FASE ASCENSO A PRIMERA JUVENIL GRAN CANARIA | 21-22 a 24-25 | `JUV1GA` | Fase de Ascenso a Primera GC | grancanaria | ascenso |
| FASE DE ASCENSO A PRIMERA JUVENIL GRAN CANARIA | 25-26 | `JUV1GA` | Fase de Ascenso a Primera GC | grancanaria | ascenso |
| LIGA SEGUNDA JUVENIL DE GRAN CANARIA | 19-20 a 25-26 | `JUV2G` | Segunda GC | grancanaria | liga |
| LIGA SEGUNDA JUVENIL GRAN CANARIA | 26-27 | `JUV2G` | Segunda GC | grancanaria | liga |
| LIGA DIVISION DE HONOR JUVENIL | 19-20 | `JUVH` | División de Honor | interinsular | liga |
| LIGA DIVISION DE HONOR JUVENIL GRUPO 6 | 20-21 a 24-25 | `JUVH` | División de Honor | interinsular | liga |
| FASE ASCENSO A DIVISION DE HONOR JUVENIL | 22-23, 23-24, 24-25 | `JUVHA` | Fase de Ascenso a División de Honor | interinsular | ascenso |
| FASE DE ASCENSO A DIVISION DE HONOR JUVENIL | 25-26 | `JUVHA` | Fase de Ascenso a División de Honor | interinsular | ascenso |
| SEGUNDA FASE DIVISION DE HONOR JUVENIL GRUPO 6-SUBGRUPO C | 20-21 | `JUVHSFC` | División de Honor Fase 2 C | interinsular | liga |
| SEGUNDA FASE DIVISION DE HONOR JUVENIL GRUPO 6-SUBGRUPO D | 20-21 | `JUVHSFD` | División de Honor Fase 2 D | interinsular | liga |
| LIGA JUVENIL INTERINSULAR | 24-25, 25-26, 26-27 | `JUVI` | Interinsular | interinsular | liga |
| LIGA JUVENIL INTERINSULAR DE LAS PALMAS | 20-21 a 23-24 | `JUVI` | Interinsular | interinsular | liga |
| - FASE DE ASCENSO A JUVENIL INTERINSULAR | 25-26 | `JUVIA` | Fase de Ascenso a Interinsular | interinsular | ascenso |
| FASE DE ASCENSO A JUVENIL INTERINSULAR | 22-23, 23-24, 24-25 | `JUVIA` | Fase de Ascenso a Interinsular | interinsular | ascenso |
| FASE DE ASCENSO A JUVENIL INTERINSULAR FUERTEVENTURA | 22-23, 23-24, 24-25 | `JUVIFA` | Fase de Ascenso a Interinsular Fuerteventura | fuerteventura | ascenso |
| ELIMINATORIAS DE ASCENSO A JUVENIL INTERINSULAR (LANZAROTE) | 21-22 a 24-25 | `JUVILE` | Eliminatorias de Ascenso a Interinsular Lanzarote | lanzarote | eliminatorias |
| FASE DE ASCENSO A JUVENIL INTERINSULAR (LANZAROTE-FUERTEVENTURA) | 25-26 | `JUVIXA` | Fase de Ascenso a Interinsular Lanzarote-Fuerteventura | interinsular | ascenso |
| FASE DE ASCENSO A JUVENIL INTERINSULAR - LANZAROTE/FUERTEVENTURA | 22-23 | `JUVIXA` | Fase de Ascenso a Interinsular Lanzarote-Fuerteventura | interinsular | ascenso |
| ELIMINATORIAS DE ASCENSO A JUVENIL INTERINSULAR (LANZAROTE-FUERTEVENTURA) | 23-24, 24-25 | `JUVIXE` | Eliminatorias de Ascenso a Interinsular Lanzarote-Fuerteventura | interinsular | eliminatorias |
| LIGA JUVENIL PREFERENTE DE FUERTEVENTURA | 24-25, 25-26 | `JUVPF` | Preferente Fuerteventura | fuerteventura | liga |
| LIGA JUVENIL PREFERENTE FUERTEVENTURA | 19-20 a 23-24, 26-27 | `JUVPF` | Preferente Fuerteventura | fuerteventura | liga |
| COPA JUVENIL PREFERENTE FUERTEVENTURA | 21-22, 22-23, 24-25, 25-26 | `JUVPFC` | Copa Preferente Fuerteventura | fuerteventura | copa |
| FINAL COPA JUVENIL PREFERENTE FUERTEVENTURA | 22-23 | `JUVPFCF` | Final Copa Preferente Fuerteventura | fuerteventura | final |
| LIGA JUVENIL PREFERENTE DE GRAN CANARIA | 24-25, 25-26 | `JUVPG` | Preferente GC | grancanaria | liga |
| LIGA JUVENIL PREFERENTE GRAN CANARIA | 26-27 | `JUVPG` | Preferente GC | grancanaria | liga |
| LIGA PREFERENTE JUVENIL DE GRAN CANARIA | 19-20 a 23-24 | `JUVPG` | Preferente GC | grancanaria | liga |
| FASE DE ASCENSO A JUVENIL PREFERENTE GRAN CANARIA | 22-23 a 25-26 | `JUVPGA` | Fase de Ascenso a Preferente GC | grancanaria | ascenso |
| LIGA JUVENIL PREFERENTE DE LANZAROTE | 19-20 a 25-26 | `JUVPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA JUVENIL PREFERENTE LANZAROTE | 26-27 | `JUVPL` | Preferente Lanzarote | lanzarote | liga |
| COPA FIFLP JUVENIL TERRITORIAL | 21-22 | `JUVTC` | Copa Territorial | interinsular | copa |
| LIGA PRIMERA ALEVIN F-8 DE LANZAROTE | 19-20 a 24-25 | `AL1L` | Primera Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8 | 23-24, 24-25 | `AL1LC` | Copa Cabildo Primera Lanzarote | lanzarote | copa |
| FINAL COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8 | 23-24, 24-25 | `AL1LCF` | Final Copa Cabildo Primera Lanzarote | lanzarote | final |
| SEMIFINAL COPA CABILDO DE LANZAROTE PRIMERA ALEVIN FUTBOL-8 | 24-25 | `AL1LCS` | Semifinal Copa Cabildo Primera Lanzarote | lanzarote | final |
| FINAL LIGA PRIMERA ALEVIN LANZAROTE | 21-22 a 24-25 | `AL1LF` | Final Liga Primera Lanzarote | lanzarote | final |
| LIGA ALEVÍN PREFERENTE FÚTBOL-8 DE LANZAROTE | 24-25 | `ALPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA PREFERENTE ALEVIN F-8 DE LANZAROTE | 19-20 a 23-24 | `ALPL` | Preferente Lanzarote | lanzarote | liga |
| COPA CABILDO DE LANZAROTE PREFERENTE ALEVIN FUTBOL-8 | 23-24, 24-25 | `ALPLC` | Copa Cabildo Preferente Lanzarote | lanzarote | copa |
| FINAL COPA CABILDO DE LANZAROTE PREFERENTE ALEVIN FUTBOL-8 | 23-24, 24-25 | `ALPLCF` | Final Copa Cabildo Preferente Lanzarote | lanzarote | final |
| SUPERLIGA ALEVIN FUERTEVENTURA | 21-22 | `ALSF` | Superliga Fuerteventura | fuerteventura | liga |
| FINAL SUPERLIGA ALEVIN FUERTEVENTURA | 22-23 | `ALSFF` | Final Liga Superliga Fuerteventura | fuerteventura | final |
| LIGA ALEVIN F-8 DE FUERTEVENTURA | 23-24 | `ALUF` | Fuerteventura | fuerteventura | liga |
| LIGA ALEVIN F-8 DE FUERTEVENTURA PRIMERA FASE | 24-25 | `ALUF` | Fuerteventura Fase 1 | fuerteventura | liga |
| LIGA ALEVIN F-8 FUERTEVENTURA | 19-20 a 22-23 | `ALUF` | Fuerteventura | fuerteventura | liga |
| LIGA ALEVIN FUERTEVENTURA F7 1ª FASE | 25-26, 26-27 | `ALUF` | Fuerteventura Fase 1 | fuerteventura | liga |
| COPA ALEVIN F-8 FUERTEVENTURA | 21-22, 22-23, 23-24 | `ALUFC` | Copa Fuerteventura | fuerteventura | copa |
| FINAL COPA ALEVIN FUERTEVENTURA | 21-22 | `ALUFCF` | Final Copa Fuerteventura | fuerteventura | final |
| FINAL LIGA ALEVIN FUERTEVENTURA | 22-23 | `ALUFF` | Final Liga Fuerteventura | fuerteventura | final |
| 2ª FASE LIGA ALEVIN FUERTEVENTURA | 22-23, 23-24, 24-25 | `ALUFSF` | Fuerteventura Fase 2 | fuerteventura | liga |
| LIGA ALEVIN FUERTEVENTURA 2ª FASE | 25-26 | `ALUFSF` | Fuerteventura Fase 2 | fuerteventura | liga |
| LIGA ALEVIN LANZAROTE FASE 1 | 25-26, 26-27 | `ALUL` | Lanzarote Fase 1 | lanzarote | liga |
| COPA DELEGACION ALEVIN LANZAROTE | 21-22 | `ALULCD` | Copa Delegación Lanzarote | lanzarote | copa |
| FINAL COPA DELEGACION ALEVIN LANZAROTE | 21-22 | `ALULCDF` | Final Copa Delegación Lanzarote | lanzarote | final |
| SEMIFINAL COPA DELEGACION ALEVIN LANZAROTE | 21-22 | `ALULCDS` | Semifinal Copa Delegación Lanzarote | lanzarote | final |
| LIGA ALEVIN LANZAROTE FASE 2 | 25-26 | `ALULSF` | Lanzarote Fase 2 | lanzarote | liga |

**Sin convenio**: 1 de 139 (138 con convenio), «ELIMINATORIA DESEMPATE CADETE INSULAR» (2026-27), por el tipo («desempate»: no se sabe ni la isla ni si es copa o liga). No se carga; la activación lo apunta en `activation.failed` («sin convenio de código: …») y «Datos y fuentes» lo enseña, como hoy. Ninguna temporada de 2016-17 a 2026-27 tiene dos competiciones con el mismo prefijo.

## El carril de las categorías mayores

- **Qué es**: `update.yml` llamado por `carril-mayores.yml` (`workflow_call`) con `cats: infantil,cadete,juvenil`. Llamado así tiene el número de pasada del workflow que llama (`GITHUB_RUN_NUMBER` es el de `carril-mayores.yml`): no gasta números del bot de hoy (su rotación sin estado sale de ellos) y el reloj no lo cuenta como pasada del bot (si lo contara, cada pasada del carril retrasaría hasta 2 h la siguiente del bot). Mismo grupo de concurrencia (`update-data`, que pasa al job de `update.yml`): nunca dos pasadas a la vez.
- **Cuándo**: lo lanza el reloj (`reloj.yml`), solo con la variable del repositorio `CARRIL_MAYORES` a `1`, cuando: no está en una ventana de partidos ni a menos de 1 h de que empiece una (viernes desde las 17:00, sábado y domingo desde las 9:00, hora de Canarias); no hay ninguna ejecución sin acabar de `update.yml`, `carril-mayores.yml` ni `activar.yml`; la última pasada del bot empezó hace entre 25 y 75 min (ya acabó, y la siguiente toca a los 110-120: el carril, ~24 min, acaba antes); y la última del carril empezó hace al menos 4 h menos 10 min (`CARRIL_CADA`). Como solo cabe en el hueco tras una pasada del bot, y fuera de las ventanas el bot pasa cada 2 h, el carril puede ir cada 2 h o cada 4 h, no entre medias: cada 4 h.
- **Cuántas**: de lunes a jueves 6 al día; el viernes 5 (de 0 a 17 h); el sábado y el domingo 3 (de 0 a 9 h): **35 a la semana**.
- **Los números**: ~45 grupos × ~4 páginas = ~180 páginas por vuelta completa, ~1,3 pasadas de Azure (~137 páginas). Con la mitad de las pasadas en AWS (no leen nada), se esperan 17-18 pasadas útiles a la semana, ~2.400 páginas, frente a ~1.500 que hacen falta (una vuelta al día, ~180 páginas, más las ~230 actas nuevas de cada semana): margen de 1,6. De lunes a jueves, 6 pasadas: se esperan 3 en Azure (~410 páginas, más de 2 vueltas) y la probabilidad de un día con menos de 2 en Azure (menos de una vuelta y media) es del 11 %; el viernes, 19 %; el sábado y el domingo (3 pasadas, ~1,1 vueltas esperadas) puede quedar algún grupo para el lunes (son los días en que se juega: importa tener el resultado, no al minuto). Lo que no se lee en un día conserva su comprobación (`source_health.carry`) y va primero en la pasada siguiente (rotación de 4 turnos, como el bot).
- **Las actas ya jugadas** (~2.300 a 25/11) no las espera el carril: tras activar cada categoría, el director encarga sus actas de 2026-27 al carril del histórico (~2.000 páginas al día: un día por categoría).
- **Si hay más grupos de los previstos** (más de 60 en `fiflp_islas_22<sufijo>_grupos.json`), el director baja `reloj_pasadas.CARRIL_CADA` a 2 h (12 pasadas de lunes a jueves, una tras cada pasada del bot) en un commit de una línea; con menos de 25 grupos, se puede subir a 6 h.
- Lo que no hace el carril: las competiciones nuevas y el directorio de campos (las sigue mirando el bot de hoy, una vez al día); sí las fichas de los equipos de sus grupos. Su veredicto va a `data-health.json` aparte (`carriles.mayores`): una pasada del carril en AWS no pone en rojo ni alarga la racha seca del bot de hoy.

## Lo que añade

- **A la base**, la temporada en curso: ~7.000 actas × ~2,4 KB = ~17 MB de actas, ~1,5 MB de partidos, ~2 MB de jugadores nuevos y ~0,5 MB de clasificaciones, goleadores y fichas de equipo: **~21 MB al acabar la temporada** (de 47,6 a ~69 MB) y **~9 MB a final de diciembre**, con las actas ya jugadas traídas por el histórico. El alevín de islas, ~0,5 MB. No depende de la parte D, pero con la parte A (alevín histórico, ~+15-20 MB) en marcha a la vez la base pasaría del aviso de 80 MB en primavera: el director mira el tamaño antes de cada paso y para si pasa de 70 MB sin la parte D en su fase 3.
- **Al repositorio**: `scripts/actas_bot_2026-2027_{infantil,cadete,juvenil}.jsonl` (~10 MB cada uno al acabar la temporada), `scripts/fiflp_actas_2026-2027_{infantil,cadete,juvenil}_raw.json` (las del histórico, ~8 MB cada uno), `scripts/fiflp_islas_22{inf,cad,juv}_raw.json` (~0,5-1 MB cada uno).
- **A lo publicado**: nada (los `data-*.js` no cambian; `data-health.json` gana ~45 entradas de grupo y la clave `carriles`). El paso del alevín de islas (D6), si se da, añade sus ~4 grupos a `data-alevin.js` y se ve en la web.

## Orden de publicación

| Tarea | `main` después | PASO DEL DIRECTOR | Vuelta atrás |
|---|---|---|---|
| 1. Categorías | Igual: nada nuevo es activable; el bot lee por defecto su carril (las mismas categorías de hoy) | Ninguno | `git revert` |
| 2. Convenio | Igual; el manifiesto y los grupos de temporadas pasadas saben los códigos nuevos | Ninguno | `git revert` |
| 3. Lotes y temporadas pasadas | Igual; el histórico acepta las categorías nuevas | Ninguno | `git revert` |
| 4. Aislamiento | Igual; más pruebas | Ninguno | `git revert` |
| 5. Identidad y ranking | Igual (las fichas solo miran `EN_WEB`) | Ninguno | `git revert` |
| 6. El generador solo publica lo de la web | Igual (lo prueba byte a byte) | Ninguno | `git revert` |
| 7. El bot por carriles | Igual (prueba de oro) | Ninguno | `git revert` |
| 8. Activación | Igual; activar sabe bajar y activar las tandas nuevas | Ninguno | `git revert` |
| 9. Workflows del carril | El reloj sabe lanzar el carril, apagado (`CARRIL_MAYORES` sin poner) | Ninguno | `git revert` |
| 10. Documentación | Igual | D1 (publicar 1-10) | `git revert` |
| — | | D2 encender el carril; D3 infantil; D4 cadete; D5 juvenil; D6 alevín de islas | Ver cada paso |

Las tareas se pueden empujar de una en una o juntas, en este orden; ninguna activa nada. Los pasos D2-D6 van después de la tarea 10 en `main`, en este orden, cada uno con su comprobación en verde antes del siguiente.

---

### Task 1: Las categorías: conocer no es activar, y cada carril lo suyo

**Files:**
- Modify: `scripts/categorias.py` (todo el módulo: docstring, constantes nuevas, `category_of`, `excluded`, funciones nuevas)
- Modify: `scripts/update_fiflp.py` (`new_competitions`; `update_groups`: las categorías por defecto)
- Modify: `scripts/tests/fixtures/fiflp_comps_catalog.json` (copia byte a byte de `scripts/fiflp_comps_catalog.json` del árbol, la del 25/11)
- Test: `scripts/tests/test_categorias.py`, `scripts/tests/test_competiciones_nuevas.py`, `scripts/tests/test_alevin_activacion.py` (las de `update_groups` y `FIFLP_CATS`), y las que fijen el número de competiciones de 2026-27 del catálogo congelado (búscalas con `grep -rn "2026-2027" scripts/tests/*.py | grep -i catalog`)

**Interfaces:**
- Produces (en `scripts/categorias.py`):
  - `DB_NAME = {"benjamin": "BENJAMIN", "prebenjamin": "PREBENJAMIN", "alevin": "ALEVIN", "infantil": "INFANTIL", "cadete": "CADETE", "juvenil": "JUVENIL"}`; `DEFAULT_CATEGORIES` no cambia (`("BENJAMIN", "PREBENJAMIN")`).
  - `MAYORES = ("INFANTIL", "CADETE", "JUVENIL")`.
  - `ALEVIN_ISLAS = False` — mientras sea `False`, el alevín de Lanzarote y Fuerteventura sigue fuera, como hoy (`category_of` → `None`, `excluded` → `True`); a `True` (paso D6) es `ALEVIN`.
  - `ACTIVABLES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")` — las que el bot apunta en `newCompetitions` y activa solo. Las nuevas entran en los pasos D3-D5.
  - `CARRILES = {"principal": ("PREBENJAMIN", "BENJAMIN", "ALEVIN"), "mayores": MAYORES}`.
  - `EN_WEB = ("BENJAMIN", "PREBENJAMIN", "ALEVIN")` — lo que ven el generador y el resolvedor de fichas (tareas 5 y 6). E2 lo amplía.
  - `TANDAS = {"": ("BENJAMIN", "PREBENJAMIN"), "al": ("ALEVIN",), "inf": ("INFANTIL",), "cad": ("CADETE",), "juv": ("JUVENIL",)}` — el sufijo de la tanda de activación (`fiflp_islas_<CodTemporada><sufijo>_raw.json`) de cada categoría.
  - `category_of(name) -> 'PREBENJAMIN' | 'BENJAMIN' | 'ALEVIN' | 'INFANTIL' | 'CADETE' | 'JUVENIL' | None` — `None` también para sala (`SALA`, `LPFS`, `FS` o `F.S.` como palabra suelta), lo femenino (`FEMENIN`), el alevín de islas con `ALEVIN_ISLAS` a `False` y un nombre con dos de las categorías alevín, infantil, cadete y juvenil. `INFANTILL` es infantil. Lo de prebenjamín y benjamín, igual que hoy y en el mismo orden.
  - `es_alevin_de_islas(name) -> bool` — alevín (sin benjamín) cuyo nombre dice Lanzarote o Fuerteventura, valga lo que valga `ALEVIN_ISLAS`.
  - `excluded(name) -> bool` — sala, femenino y (con `ALEVIN_ISLAS` a `False`) el alevín de islas.
  - `activable(name) -> bool` — `category_of(name) in ACTIVABLES`.
  - `carril_de(categories) -> str` — `"principal"` o `"mayores"` según `CARRILES`; `ValueError("las categorías de un carril no se mezclan: …")` si hay de los dos o la tupla está vacía.
  - `carril_actual(env=None) -> str` — el de `FIFLP_CATS` (`parse_categories`); vacía o sin poner, `"principal"`.
  - `categorias_del_carril(carril) -> tuple` — `CARRILES[carril]`; `KeyError` si no existe.
  - `sufijo_tanda(category) -> str` y `categorias_de_tanda(sufijo) -> tuple` — de `TANDAS`; `KeyError` con lo desconocido.
- Produces (en `scripts/update_fiflp.py`): `new_competitions` filtra con `categorias.activable` en vez de `category_of`; `update_groups` lee `parse_categories(FIFLP_CATS)` si está puesta y, si no, `CARRILES["principal"]` (hoy, sin ella, lee todas).

- [ ] **Step 1: Actualizar el catálogo congelado.** `cp scripts/fiflp_comps_catalog.json scripts/tests/fixtures/fiflp_comps_catalog.json`. Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — anota qué pruebas fallan solo por el catálogo nuevo (cuentas de 2026-27: eran 44 y son 72) y corrige sus números; ninguna otra cosa.

- [ ] **Step 2: Pruebas que fallan** en `scripts/tests/test_categorias.py`:
  - En la lista de `test_category_of`: fuera `("LIGA INFANTIL PREFERENTE", None)`; dentro `("LIGA INFANTIL PREFERENTE DE GRAN CANARIA", "INFANTIL")`, `("LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", "CADETE")`, `("LIGA DIVISION DE HONOR JUVENIL GRUPO 6", "JUVENIL")`, `("FINAL COPA CABILDO DE LANZAROTE PRIMERA INFANTILL", "INFANTIL")`, `("LIGA PRIMERA INFANTIL DE GRAN CANARIA (GRUPO 3)", "INFANTIL")` (cabecera de un acta), `("copa juvenil isla de gran canaria fs", None)`, `("LIGA INFANTIL F.S. LANZAROTE", None)`, `("LIGA INFANTIL FUTBOL SALA GRAN CANARIA", None)`, `("CAMPEONATO DE CANARIAS DE FÚTBOL SALA CADETE", None)`, `("COPA FEMENINA LANZAROTE", None)`, `("LIGA INFANTIL FEMENINA", None)`, `("LIGA INFANTIL FASE 1", "INFANTIL")` («FASE» no es «FS»), `("COPA ALEVIN E INFANTIL", None)`. Las de alevín de islas siguen en `None`.
  - `test_alevin_de_islas_con_la_marca(monkeypatch)`: con `monkeypatch.setattr(categorias, "ALEVIN_ISLAS", True)`, `category_of("LIGA ALEVIN LANZAROTE FASE 1") == "ALEVIN"`, `excluded(...)` es `False` y `es_alevin_de_islas(...)` es `True` con la marca y sin ella; `category_of("LIGA ALEVIN GRAN CANARIA FASE PREVIA") == "ALEVIN"` y `es_alevin_de_islas` de ella, `False`.
  - `test_category_of_whole_catalog` (sobre el congelado nuevo): además de lo de hoy, ningún nombre con `SALA`, `FS` suelto o `FEMENIN` tiene categoría; todo nombre de 2019-20 a 2026-27 con `INFANTIL`, `CADETE` o `JUVENIL` y sin eso tiene esa categoría; y los nombres distintos de 2019-20 a 2026-27 (con los espacios simplificados) son 35 de infantil, 47 de cadete y 32 de juvenil.
  - `test_activable(monkeypatch)`: `activable("LIGA BENJAMIN GRAN CANARIA FASE PREVIA")` y `activable("LIGA ALEVIN GRAN CANARIA FASE PREVIA")` son `True`; `activable("LIGA INFANTIL PREFERENTE DE GRAN CANARIA")` es `False`; con `ACTIVABLES` parcheado a `("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL")`, `True`; el alevín de islas es `False` con `ALEVIN_ISLAS` a `False` aunque `ALEVIN` esté en `ACTIVABLES`.
  - `test_carriles`: `carril_de(("INFANTIL",)) == "mayores"`, `carril_de(("BENJAMIN", "ALEVIN")) == "principal"`, `carril_de(("BENJAMIN", "CADETE"))` y `carril_de(())` lanzan `ValueError`; `carril_actual({}) == "principal"`, `carril_actual({"FIFLP_CATS": " "}) == "principal"`, `carril_actual({"FIFLP_CATS": "infantil,cadete,juvenil"}) == "mayores"`; `categorias_del_carril("mayores") == ("INFANTIL", "CADETE", "JUVENIL")`.
  - `test_tandas`: `sufijo_tanda("JUVENIL") == "juv"`, `sufijo_tanda("BENJAMIN") == ""`, `categorias_de_tanda("cad") == ("CADETE",)`, `categorias_de_tanda("al") == ("ALEVIN",)`; `categorias_de_tanda("xx")` lanza `KeyError`.
  - En `test_parse_categories`: `parse_categories("benjamin,cadete") == ("BENJAMIN", "CADETE")`; `parse_categories("benjamin,senior")` lanza `ValueError` con «senior» y las seis claves en el mensaje; `DB_NAME` con las seis.
  - `test_migration_on_a_copy_of_the_real_base`: la última comprobación de categorías pasa a ser `{"BENJAMIN", "PREBENJAMIN", "ALEVIN"} <= nombres <= set(DB_NAME.values())` (con la base de después, las nuevas están).
- [ ] **Step 3: Pruebas que fallan** en `scripts/tests/test_competiciones_nuevas.py`: en `test_category_of_a_federation_competition`, `("LIGA INFANTIL PREFERENTE DE GRAN CANARIA", "INFANTIL")`; nueva `test_new_competitions_solo_las_activables(monkeypatch)`: con opciones `[{"id": "54976908", "name": "LIGA INFANTIL PREFERENTE DE GRAN CANARIA"}, {"id": "55331982", "name": "COPA BENJAMÍN GRAN CANARIA"}]` y `known` vacío, `new_competitions` devuelve solo la de benjamín; con `ACTIVABLES` parcheado con `INFANTIL`, las dos; con `IGNORED_COMPETITIONS` igual que hoy. Y en `scripts/tests/test_alevin_activacion.py`, junto a las de `FIFLP_CATS` (hacia la línea 535): `test_sin_fifl_cats_solo_el_carril_principal(monkeypatch)` — una base con un grupo de cada carril (`FF1` de benjamín y `INFPG1` de infantil, los dos con URL de la federación) y `FIFLP_CATS` sin poner: los grupos que llegan a `run_passes` (parchea `_with_browser` para capturarlos, como las pruebas de al lado) son solo `FF1`, y `INFPG1` conserva su entrada de `data-health.json` (`source_health.carry`); con `FIFLP_CATS=infantil`, al revés; con `FIFLP_CATS=benjamin,infantil`, `ValueError` antes de pedir nada.
- [ ] **Step 4: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_categorias.py scripts/tests/test_competiciones_nuevas.py scripts/tests/test_alevin_activacion.py` — Expected: fallan las nuevas.
- [ ] **Step 5: Implementar** lo de «Produces». El docstring de `categorias.py` explica las cuatro preguntas que contesta el módulo (qué categoría es, si el bot la activa, qué carril la lee y si la web la ve) y por qué van separadas (decisión 1 de la parte E: reconocerla no puede disparar la activación de 24 competiciones a la vez). `update_groups` valida el carril con `carril_de` antes de abrir el navegador.
- [ ] **Step 6: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde.
- [ ] **Step 7: Commit.** `git add scripts/categorias.py scripts/update_fiflp.py scripts/tests/` y asunto «Categorías: infantil, cadete y juvenil se conocen, pero ni se activan ni se leen hasta su paso».

---

### Task 2: El convenio de códigos de las categorías nuevas

**Files:**
- Create: `scripts/convenio.py`
- Create: `scripts/tests/fixtures/convenio_mayores.json` (las 138 filas de la tabla de «El convenio de códigos», tal cual)
- Modify: `scripts/fiflp_manifest.py` (`meta` nueva; `comp_meta`, `build`, `eliminatoria_de_liga`, `category`, `--cat`; el docstring del módulo)
- Modify: `scripts/import_fiflp_grupos.py` (`meta_by_name`, `comp_meta`)
- Test: `scripts/tests/test_convenio.py` (nuevo); `scripts/tests/test_alevin_aislamiento.py::test_the_benjamin_conventions_did_not_move` y `test_meta_by_name_alevin_codes_never_collide` siguen sin tocar

**Interfaces:**
- Consumes: `categorias.category_of`, `categorias.es_alevin_de_islas`, `categorias.MAYORES`.
- Produces (en `scripts/convenio.py`, puro, sin base ni red):
  - `class SinConvenio(ValueError)` — su texto es el motivo: `"no se publica"`, `"sin categoría"`, `"tipo de competición sin convenio"`, `"fase desconocida"`, `"dos niveles en el nombre"`, `"final de algo que no es liga ni copa"`.
  - `Convenio = NamedTuple("Convenio", [("prefijo", str), ("fase", str), ("isla", str), ("tipo", str)])` — `isla` en `{"grancanaria", "lanzarote", "fuerteventura", "interinsular"}`; `tipo` en `{"liga", "copa", "ascenso", "eliminatorias", "final"}`.
  - `aplica(nombre: str) -> bool` — infantil, cadete o juvenil por el nombre (sin mirar si se publica) o `categorias.es_alevin_de_islas`.
  - `convenio(nombre: str) -> Convenio` — el algoritmo de «El convenio de códigos» (puntos 1-8), con estas tablas como constantes del módulo: `CATEGORIA = {"INFANTIL": "INF", "CADETE": "CAD", "JUVENIL": "JUV", "ALEVIN": "AL"}`; `NIVELES` (expresión, token, nombre) en el orden del punto 6; `ISLAS = {"G": ("GC", "Gran Canaria", "grancanaria"), "L": ("Lanzarote", "Lanzarote", "lanzarote"), "F": ("Fuerteventura", "Fuerteventura", "fuerteventura"), "X": ("Lanzarote-Fuerteventura", "Lanzarote-Fuerteventura", "interinsular"), "": ("", "", "interinsular")}`; `MULTIISLA = {"H", "A", "I", "T"}`. Un nombre que no `aplica` → `SinConvenio("sin categoría")`.
  - `eliminatoria_de_liga(c: Convenio) -> Convenio` — `(c.prefijo + "EL", "Eliminatorias " + c.fase, c.isla, "eliminatorias")` (punto 9).
- Produces (en `scripts/fiflp_manifest.py`):
  - `meta(name: str) -> tuple[str, str, str]` — `(prefijo, fase, isla)`: si `convenio.aplica(name)`, el de `convenio` (con `ValueError(f"competición sin convenio de código: {name}")` si lanza `SinConvenio`, el texto que ya espera `activar_auto.SIN_CONVENIO`); si no, lo de hoy con la isla que hoy calcula `build` por el prefijo.
  - `comp_meta(name) -> tuple[str, str]` — `meta(name)[:2]` (la firma de hoy).
  - `build(...)`: la isla de cada grupo sale de `meta`; los grupos de eliminatoria dentro de una liga de las categorías nuevas toman `convenio.eliminatoria_de_liga` del de su liga, numerados como hoy tras los que ya tenga la temporada con ese prefijo; `fullName` como hoy (`f"{cat.upper()} {fold(phase)} - GRUPO {n}"`, «INFANTIL PREFERENTE GC - GRUPO 1»).
  - `category(name)` acepta las seis; `--cat` toma sus valores de `categorias.DB_NAME`.
- Produces (en `scripts/import_fiflp_grupos.py`): `meta_by_name(comp_name)` — si `convenio.aplica(comp_name)` y `category_of(comp_name)` no es `None`: `(prefijo, fase, isla)` de `convenio`, o `None` con `SinConvenio`; si no, lo de hoy. `comp_meta(...)` lee el nombre (como hoy con alevín) también si `category_of(comp_name) in MAYORES` o es alevín de islas.

- [ ] **Step 1: Crear la fixture** `scripts/tests/fixtures/convenio_mayores.json`: un objeto con una clave por fila de la tabla (el nombre de la primera columna, con los espacios simplificados) y su valor `[prefijo, fase, isla, tipo]`, en el orden de la tabla, `json.dumps(…, ensure_ascii=False, indent=1)`.
- [ ] **Step 2: Pruebas que fallan** en `scripts/tests/test_convenio.py`:
  - `test_la_tabla_entera`: para cada fila de la fixture, `tuple(convenio(nombre)) == tuple(fila)`; y son 138 filas.
  - `test_el_catalogo_entero_sin_choques` (sobre `scripts/tests/fixtures/fiflp_comps_catalog.json`, de 2016-2017 a 2026-2027): para cada temporada, cada competición con `aplica` y sin `SALA`/`FS`/`FEMENIN` tiene convenio salvo, exactamente, «ELIMINATORIA DESEMPATE CADETE INSULAR» (2026-27, motivo `"tipo de competición sin convenio"`); ningún prefijo se repite dentro de la temporada; ninguno coincide con el de una competición de benjamín, prebenjamín o alevín de Gran Canaria de esa temporada (`fiflp_manifest.comp_meta` o `import_fiflp_grupos.meta_by_name`, las que no lancen ni den `None`); ningún `prefijo + "EL"` de una liga coincide con otro prefijo de la temporada; cada prefijo casa con `^(INF|CAD|JUV|AL)[A-Z0-9]{2,14}$`, acaba en letra, no empieza por `LZ`, `FV`, `CLZ`, `CFV`, `PLZ`, `PFV`, `PCC`, `BC`, `MCP` ni `MCB`, no acaba en `KO`, y los de alevín no casan con `^AL(?:[A-Z]|P|CC[A-Z]?|CL|EL)$`.
  - `test_sin_convenio_y_sus_motivos`: «ELIMINATORIA DESEMPATE CADETE INSULAR» → `"tipo de competición sin convenio"`; «LIGA INFANTIL TERCERA FASE GRAN CANARIA» → `"fase desconocida"`; «LIGA CADETE PREFERENTE INTERINSULAR» → `"dos niveles en el nombre"`; «COPA JUVENIL FUTBOL SALA» y «LIGA INFANTIL FEMENINA» → `"no se publica"`; «FINAL FASE DE ASCENSO A JUVENIL INTERINSULAR» → `"final de algo que no es liga ni copa"`; `aplica("LIGA ALEVIN GRAN CANARIA FASE PREVIA")` es `False` y `convenio` de ella lanza `"sin categoría"`.
  - `test_eliminatoria_de_liga`: `eliminatoria_de_liga(convenio("LIGA INFANTIL PREFERENTE DE GRAN CANARIA")) == ("INFPGEL", "Eliminatorias Preferente GC", "grancanaria", "eliminatorias")`.
  - `test_manifiesto_de_las_categorias_nuevas`: `fiflp_manifest.build` sobre un raw sintético (la forma de `scripts/fiflp_islas_22al_raw.json`: `competition_id`, `competition_name`, `group_id`, `group_name`, `jornadas`, `standings`) con «LIGA INFANTIL PREFERENTE DE GRAN CANARIA» grupos «GRUPO 1» y «GRUPO 2», «LIGA JUVENIL INTERINSULAR» «GRUPO 1» y un grupo «ELIMINATORIA DE PRIMEROS» de la primera: ids `INFPG1`, `INFPG2`, `JUVI1`, `INFPGEL1`; `cat` `"infantil"`/`"juvenil"`; fases «Preferente GC», «Interinsular», «Eliminatorias Preferente GC»; islas `grancanaria`, `interinsular`; `fullName` de `INFPG1` «INFANTIL PREFERENTE GC - GRUPO 1»; con `taken={"INFPG1"}`, `ValueError` «código repetido: INFPG1»; con «ELIMINATORIA DESEMPATE CADETE INSULAR», `ValueError` «competición sin convenio de código: …».
  - `test_el_alevin_de_gran_canaria_no_se_mueve`: `fiflp_manifest.comp_meta("LIGA ALEVIN GRAN CANARIA FASE PREVIA") == ("AL", "Primera Fase GC")`, `("LIGA ALEVIN GRAN CANARIA FASE F") → ("ALF", "Segunda Fase F")`, `("COPA CAMPEONES ALEVÍN") → ("ALCC", "Copa de Campeones")`; y `meta` de todos los nombres de benjamín, prebenjamín y alevín de Gran Canaria del catálogo congelado da lo mismo que `comp_meta` de antes de esta tarea (calcula la lista esperada en el commit anterior y guárdala como `scripts/tests/fixtures/convenio_anterior.json`).
  - `test_meta_by_name_de_las_nuevas(monkeypatch)`: `import_fiflp_grupos.meta_by_name("LIGA PRIMERA INFANTIL DE LANZAROTE") == ("INF1L", "Primera Lanzarote", "lanzarote")`; la del desempate, `None`; «LIGA PRIMERA ALEVIN F-8 DE LANZAROTE», `None` con `ALEVIN_ISLAS` a `False` y `("AL1L", "Primera Lanzarote", "lanzarote")` con `True`.
- [ ] **Step 3: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_convenio.py` — Expected: no encuentra el módulo.
- [ ] **Step 4: Implementar** `scripts/convenio.py` (la cabecera del módulo copia el esquema `CATEGORÍA + NIVEL + ISLA + FASE + TIPO + número` y explica, punto por punto, por qué no choca con los códigos de hoy) y lo de «Produces» en `fiflp_manifest.py` e `import_fiflp_grupos.py`. El docstring de `fiflp_manifest.py` añade una línea por familia («LIGA <nivel> <CATEGORÍA> <isla> → <CAT><nivel><isla>1.. (scripts/convenio.py)»).
- [ ] **Step 5: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_convenio.py scripts/tests/test_alevin_aislamiento.py scripts/tests/test_alevin_activacion.py scripts/tests/test_categorias.py` — Expected: en verde. Después, la suite entera: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` en verde.
- [ ] **Step 6: Commit.** Asunto «Convenio de códigos para infantil, cadete, juvenil y el alevín de islas, comprobado contra el catálogo».

---

### Task 3: Los lotes de originales y las temporadas pasadas (lo que necesita la parte F)

**Files:**
- Modify: `scripts/actas_lotes.py` (`LOTE_DE_CATEGORIA`, `lote_of_name`, docstring)
- Modify: `scripts/fetch_fiflp_actas.py` (la regla «una tanda es de un solo lote», con los cinco lotes; sus mensajes)
- Modify: `scripts/historico.py` (`NOMBRE_CATEGORIA`, `rango_competicion`, `encargar`, `_categorias_legibles`)
- Modify: `scripts/import_fiflp_detalle.py` (el calendario de la federación en las temporadas pasadas de las categorías sin portal, hoy solo alevín: `:569`)
- Modify: `.github/workflows/historico.yml` (la descripción de la entrada `categorias`), `.github/workflows/actas-federacion.yml` (la descripción de `categorias`: solo `benjamin,prebenjamin` o `alevin`; las demás, con el carril del histórico)
- Test: `scripts/tests/test_actas_lotes.py`, `scripts/tests/test_historico.py` (el que pruebe `encargar` y `rango_competicion`: búscalo con `grep -ln rango_competicion scripts/tests/`), `scripts/tests/test_fiflp_actas_federacion.py` o el que pruebe la regla de un lote (`grep -ln "un solo lote" scripts/tests/`), `scripts/tests/test_alevin_aislamiento.py` (la del detalle)

**Interfaces:**
- Consumes: `categorias.DB_NAME`, `categorias.MAYORES`, `convenio.convenio`, `convenio.aplica`.
- Produces:
  - `actas_lotes.LOTE_DE_CATEGORIA = {"ALEVIN": "alevin", "INFANTIL": "infantil", "CADETE": "cadete", "JUVENIL": "juvenil"}` y, con ella, `LOTES == ("", "alevin", "infantil", "cadete", "juvenil")` y `RAW_FILE` casa `fiflp_actas_<S>_<lote>_raw.json` de los cinco. Cada lote con su raw, su índice y su estado.
  - `actas_lotes.lote_of_name(name)`: sin categoría publicable (sala, femenino, alevín de islas sin la marca), el lote de la palabra de la categoría que lleve el nombre (alevín, infantil, cadete o juvenil, sin benjamín); `None` si no dice ninguna. Nunca `""` para uno de ellos.
  - `historico.NOMBRE_CATEGORIA` con `"infantil": "infantil", "cadete": "cadete", "juvenil": "juvenil"`.
  - `historico.rango_competicion(nombre) -> int` — para los nombres con `convenio.aplica` y convenio: liga de nivel `H`, `A`, `I` o `P` → `0`; liga de nivel `1` → `10`; otra liga → `30`; copa, ascenso, eliminatorias o final → `40`; sin convenio → `40`. Los demás, exactamente como hoy.
  - `historico.encargar(..., categorias="infantil", ...)` acepta las seis (con `parse_categories`) y cada categoría nueva va en su lote: los trabajos de actas son `actas:<S>:infantil`, `actas:<S>:cadete`, `actas:<S>:juvenil`.
  - `import_fiflp_detalle`: en una temporada pasada, el calendario de la federación se importa para toda categoría que no sea benjamín ni prebenjamín (las únicas con portal), no solo alevín.

- [ ] **Step 1: Pruebas que fallan.**
  - `scripts/tests/test_actas_lotes.py`: `lote_of("INFANTIL") == "infantil"`; `lotes_of(("JUVENIL", "CADETE")) == ("cadete", "juvenil")` (el orden de `LOTES`); `file_name("2025-2026", "raw", "juvenil") == "fiflp_actas_2025-2026_juvenil_raw.json"`; `raw_files` de una carpeta con los cinco raws de 2025-26 los da en el orden `""`, `alevin`, `infantil`, `cadete`, `juvenil`; `load_merged` junta los cinco (el de siempre manda en una clave repetida); `sibling_raw_keys` del de cadete trae las claves de los otros cuatro; `lote_of_name("LIGA PRIMERA INFANTIL DE GRAN CANARIA (GRUPO 3)") == "infantil"`, `lote_of_name("LIGA INFANTIL FUTBOL SALA GRAN CANARIA") == "infantil"`, `lote_of_name("LIGA CADETE INSULAR DE LANZAROTE") == "cadete"`; `misplaced` encuentra un acta con cabecera de infantil en el raw de cadete. Revisa las aserciones de hoy que fijan `LOTES` de dos (hacia las líneas 108-110, 224 y 709-717 del 25/11) y pásalas a los cinco.
  - La de la regla de un lote: una tanda con `--categorias infantil,cadete` para sin escribir nada; con `--categorias infantil --lote ""`, también («la cadena es del lote … y las categorías del de infantil»); con `--categorias infantil --lote infantil`, sigue; con `--comps 54976908` (infantil, por el catálogo congelado) y las categorías por defecto, para.
  - `historico`: `encargar(plan, "21", "infantil", "goleadores,actas", "", now)` deja `categorias == ["infantil"]` y los trabajos `goleadores:2025-2026` y `actas:2025-2026:infantil`; `_lotes(["infantil", "cadete"]) == {"infantil": ["infantil"], "cadete": ["cadete"]}`; `rango_competicion` de «LIGA DIVISION DE HONOR JUVENIL GRUPO 6», «LIGA JUVENIL INTERINSULAR», «LIGA JUVENIL PREFERENTE GRAN CANARIA», «LIGA PRIMERA JUVENIL GRAN CANARIA», «LIGA SEGUNDA JUVENIL GRAN CANARIA», «COPA JUVENIL PREFERENTE FUERTEVENTURA» y «ELIMINATORIA DESEMPATE CADETE INSULAR» → `0, 0, 0, 10, 30, 40, 40`; los valores de hoy para benjamín y alevín, iguales.
  - Detalle (en `test_alevin_aislamiento.py`, junto a `test_detail_of_an_alevin_group_is_not_written_into_benjamin`): el detalle de un grupo de «LIGA PRIMERA INFANTIL DE GRAN CANARIA» de 2025-26 importa su calendario y no escribe nada en el grupo de benjamín con los mismos clubes.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_actas_lotes.py scripts/tests/test_alevin_aislamiento.py` y el de `historico` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces». En el docstring de `actas_lotes.py`, la tabla de lotes con los cinco y por qué uno por categoría (un raw de fútbol 11 son ~2.300 actas por categoría y temporada, ~20 MB: dos juntos se acercarían al aviso de 50 MB de GitHub).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto «Histórico: un lote de actas por categoría nueva, y las temporadas pasadas aceptan infantil, cadete y juvenil».

Con esto, **bajar una temporada de infantil** (parte F) es encargarla, después de E2 en `main`: `gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar -f temporadas=21 -f categorias=infantil -f trabajos=goleadores,actas,detalle,escudos` (2025-26; los grupos se crean del raw de goleadores con los códigos de la tabla, las actas van a `scripts/fiflp_actas_2025-2026_infantil_raw.json`, y todo se prueba sobre una copia antes de promoverse). Una temporada de cada categoría cada vez («una pequeña primero»: medir la base tras la primera).

---

### Task 4: Las protecciones contra mezclar categorías, para las nuevas

**Files:**
- Modify: `scripts/tests/test_alevin_aislamiento.py` (parametrizar sus pruebas por categoría: `ALEVIN`, `INFANTIL`, `CADETE`, `JUVENIL` y el alevín de Lanzarote con `ALEVIN_ISLAS` a `True`)
- Modify: `scripts/tests/test_nombres_alevin.py` (los casos de nombres de equipo con un club en benjamín y en juvenil)
- Modify (solo si una prueba lo pide): `scripts/acta_reconciler.py`, `scripts/import_fp_app.py`, `scripts/import_fiflp_goleadores.py` (`match_group`), `scripts/import_fiflp_actas.py` (la purga), `scripts/escudos_federacion.py`, `scripts/activate_season.py` (`name_clashes`, `known_names`)
- Test: las dos de arriba

**Interfaces:**
- Consumes: `categorias.category_of`, `categorias.CARRILES`, `update_fiflp.fiflp_groups`, `actas_lotes`.
- Produces: nada nuevo; las mismas funciones, con la garantía probada para las seis categorías.

Cada prueba de hoy de `test_alevin_aislamiento.py` que monta un grupo alevín al lado de uno de benjamín con los mismos clubes pasa a recibir `(categoria, competicion, codigo)` de esta lista y a montar ese grupo: `("ALEVIN", "LIGA ALEVIN GRAN CANARIA FASE PREVIA", "AL3")`, `("INFANTIL", "LIGA PRIMERA INFANTIL DE GRAN CANARIA", "INF1G3")`, `("CADETE", "LIGA CADETE INSULAR GRAN CANARIA 1ª FASE", "CADNG3")`, `("JUVENIL", "LIGA SEGUNDA JUVENIL GRAN CANARIA", "JUV2G3")` y, con `ALEVIN_ISLAS` a `True`, `("ALEVIN", "LIGA ALEVIN LANZAROTE FASE 1", "ALUL1")` frente a uno de benjamín de Lanzarote (`LZ1`). Los nombres de las pruebas no cambian (pytest añade el parámetro).

- [ ] **Step 1: Parametrizar y añadir** en `test_alevin_aislamiento.py`, además de las de hoy:
  - `test_un_acta_de_otra_categoria_nueva_tampoco_casa`: con grupos de infantil y de cadete de los mismos clubes el mismo día, un acta con la cabecera de cadete casa con el partido de cadete y nunca con el de infantil, y al revés.
  - `test_cada_raw_purga_solo_lo_suyo`: importar el raw de actas de cadete de una temporada cerrada no deja sin `cod_acta` ningún partido de benjamín, alevín ni infantil; y las actas leídas por el bot (`cod_acta = fiflp_acta`) de cadete sobreviven a un raw parcial de cadete.
  - `test_los_carriles_no_se_cruzan`: en una base con un grupo de cada una de las seis categorías (con URL de la federación), `fiflp_groups(conn, sid, CARRILES["principal"])` no trae ninguno de `INF`/`CAD`/`JUV` y `fiflp_groups(conn, sid, CARRILES["mayores"])` solo trae esos.
  - En `test_nombres_alevin.py`: `known_names` lleva `PALMAS, U.D. LAS "A"` de un raw de juvenil a la misma fila que el de benjamín (`Las Palmas`); `name_clashes` con `raw_categories` no da choque por un club con el mismo nombre en benjamín y en juvenil, y sí por dos clubes distintos que acabarían con el mismo nombre en juvenil.
- [ ] **Step 2: Ejecutarlas.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_alevin_aislamiento.py scripts/tests/test_nombres_alevin.py` — Expected: las que ya protegen por `category_of` pasan sin tocar código; arregla solo lo que falle, en el sitio que lo decide, sin cambiar el comportamiento de benjamín, prebenjamín ni alevín (sus casos siguen en verde).
- [ ] **Step 3: Ejecutar la suite.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde.
- [ ] **Step 4: Commit.** Asunto «Protecciones: un acta, una liga, unos goleadores o una purga nunca cruzan a otra categoría, también en las nuevas».

---

### Task 5: Identidad y ranking: las edades y los niveles de las categorías nuevas

**Files:**
- Modify: `scripts/identidad.py` (`NIVEL`, `_EDAD`, docstring de `intervalo`)
- Modify: `scripts/migrate_identidad.py` (`_vistas`, `identidades`, `pares_juntas`: solo las apariciones y sucesos de grupos de `categorias.EN_WEB`)
- Modify: `scripts/ranking.py` (`nivel_fase`, `tiene_nivel`, `fase_que_cuenta`, `NIVEL_ISLA`, docstring)
- Modify: `docs/identidad.md` (las edades), `docs/ranking.md` (la tabla de niveles)
- Test: `scripts/tests/test_identidad.py`, `scripts/tests/test_ranking.py`, `scripts/tests/test_migrate_identidad.py` (o el que pruebe `resolver_fichas` sobre una base sintética: `grep -ln resolver_fichas scripts/tests/`)

**Interfaces:**
- Consumes: `categorias.EN_WEB`; `nacimiento.VENTANA` (ya tiene infantil `(13, 12)`, cadete `(15, 14)` y juvenil `(18, 16)`).
- Produces:
  - `identidad.NIVEL = {"PREBENJAMIN": 1, "BENJAMIN": 2, "ALEVIN": 3, "INFANTIL": 4, "CADETE": 5, "JUVENIL": 6}` y `identidad._EDAD = {1: (7, 5), 2: (9, 6), 3: (11, 8), 4: (13, 10), 5: (15, 12), 6: (18, 14)}` (la ventana natural de `nacimiento.VENTANA` y dos años más por abajo, como benjamín y alevín).
  - `migrate_identidad.resolver_fichas`: las vistas, las identidades y los pares «juntas» salen solo de grupos cuya categoría está en `categorias.EN_WEB` (lo lee al llamarse, no al importarse: las pruebas lo parchean). Un jugador sin ninguna aparición en esas categorías queda suelto (`ficha_id` y `union_por` a `NULL`), como hoy uno sin apariciones.
  - `ranking.nivel_fase(fase)`, sobre la fase normalizada (sin tildes, minúsculas), por este orden: empieza por «division de honor» → `1.50`; por «autonomica» → `1.45`; por «interinsular» → `1.35`; empieza por «preferente» y lleva « fase oro» → `1.30`, « fase plata» → `1.15`, si no → `1.25` (hoy); lo de hoy de la Copa de Campeones y la Segunda Fase con letra; empieza por «segunda» sin ser «segunda fase» → `0.95`; por «insular b» → `0.85`; por «insular» → `0.90`; lo demás → `1.0`. Constantes: `_NIVEL_DIVISION_HONOR = 1.50`, `_NIVEL_AUTONOMICA = 1.45`, `_NIVEL_INTERINSULAR = 1.35`, `_NIVEL_ORO = 1.30`, `_NIVEL_PLATA = 1.15`, `_NIVEL_SEGUNDA = 0.95`, `_NIVEL_INSULAR = 0.90`, `_NIVEL_INSULAR_B = 0.85`.
  - `ranking.tiene_nivel(fase)`: también `True` para las fases de los niveles nuevos de arriba (no para «Primera …», que hoy es `False` y vale 1).
  - `ranking.fase_que_cuenta(fase, mejor)`: `mejor` puede ser una letra (hoy) o una fase entera (más de un carácter): con una fase sin nivel propio y `mejor` entero, devuelve `mejor` («Copa Insular Lanzarote» cuenta como «Insular Lanzarote», la liga de su equipo esa temporada). E2 calcula ese `mejor`.
  - `ranking.NIVEL_ISLA` gana `"interinsular": 1.0` (explícita: las ligas de varias islas no se rebajan).

- [ ] **Step 1: Pruebas que fallan.**
  - `test_identidad.py`: `intervalo(2026, 4) == (2013, 2016)`, `intervalo(2026, 5) == (2011, 2014)`, `intervalo(2026, 6) == (2008, 2012)`; `test_edades_nuevas_separan`: `compatibles` de una vista de juvenil de 2026 y una de benjamín de 2019 (nacido en 2010) es `True`, y de una de cadete de 2026 y una de prebenjamín de 2025, `False`.
  - En la de `resolver_fichas`: `test_resolver_no_mira_categorias_fuera_de_la_web(monkeypatch)` — base sintética con A (sin identificador, «GOMEZ PEREZ, RAUL», club X, benjamín 2025-26), B (mismo nombre y club, sin identificador, infantil 2026-27) y C (con identificador 9001, apariciones en benjamín 2019-20 e infantil 2026-27): con `EN_WEB` de hoy, B queda suelto, A no se une a nadie que no fuera antes y la ficha de C tiene exactamente sus vistas de benjamín (las de infantil no cuentan para su intervalo); con `EN_WEB` parcheado con las seis, B y A siguen separados si sus edades no caben (pon a A en prebenjamín 2025-26 para que no quepan) y C sigue siendo una sola ficha.
  - `test_ranking.py`: `nivel_fase("División de Honor") == 1.50`, `("Autonómica") == 1.45`, `("Interinsular") == 1.35`, `("Preferente GC Fase Oro") == 1.30`, `("Preferente GC Fase Plata") == 1.15`, `("Preferente GC") == 1.25`, `("Primera GC") == 1.0`, `("Segunda GC") == 0.95`, `("Segunda Fase B") == 1.15` (sin cambio), `("Insular GC Fase 1") == 0.90`, `("Insular B Lanzarote") == 0.85`, `("Copa Insular Lanzarote") == 1.0`; `tiene_nivel("Interinsular")` y `tiene_nivel("Insular GC")` son `True`, `tiene_nivel("Primera GC")` es `False`; `fase_que_cuenta("Copa Insular Lanzarote", "Insular Lanzarote") == "Insular Lanzarote"`, `fase_que_cuenta("Primera Fase GC", "A") == "Segunda Fase A"` (hoy); `nivel_isla("interinsular") == 1.0`. Todas las pruebas de hoy de `test_ranking.py`, sin tocarlas.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_identidad.py scripts/tests/test_ranking.py` y la de `resolver_fichas` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces»; en `docs/identidad.md`, la línea de «Edad» con las seis categorías; en `docs/ranking.md`, la tabla de niveles con los nuevos y una frase: «Infantil, cadete y juvenil entran en el ranking cuando la web los enseña (parte E2)».
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde (con la base real, las fichas no cambian: no hay nada fuera de `EN_WEB`).
- [ ] **Step 5: Commit.** Asunto «Identidad y ranking: edades y niveles de infantil, cadete y juvenil; las fichas solo miran lo que publica la web».

---

### Task 6: El generador solo publica lo de la web, y la prueba de la base de después

**Files:**
- Create: `scripts/vista_web.py`
- Modify: `scripts/generate_js.py` (`main`: trabaja sobre `vista_web.copia_web(conn)`; `coverage_summary` sigue midiendo el fichero de verdad, `PROJECT_ROOT/futbolbase.db`)
- Create: `scripts/tests/base_mayores.py` (no empieza por `test_`: ayudante de las pruebas y de `prueba_mayores.py`)
- Create: `scripts/prueba_mayores.py`
- Modify: las pruebas que la base de después ponga en rojo (las que comparan lo publicado con la base entera de la temporada en curso; p. ej. las de `test_data_integrity.py` sin filtro de categoría, `test_db_sanity.py`, `test_fichas_publicadas.py`, las `test_*base_real*`): que comparen con las categorías de `categorias.EN_WEB`
- Test: `scripts/tests/test_vista_web.py` (nuevo)

**Interfaces:**
- Consumes: `categorias.EN_WEB`; `fiflp_manifest.build`; `activate_season.add_groups`; `import_fiflp_actas._import_one`; `migrate_identidad.resolver_fichas`.
- Produces:
  - `vista_web.copia_web(conn, categorias=None) -> sqlite3.Connection` — con `categorias` `None`, `categorias.EN_WEB` leído al llamar. Si la base no tiene ningún grupo de otra categoría, devuelve **la misma** conexión (cero coste hasta el primer paso del director). Si los tiene, una copia en memoria (`conn.backup`) de la que se han borrado, en una transacción: esos grupos; sus partidos y lo que cuelga de ellos (`appearances`, `match_events`, `match_staff_all`, `goals` y cualquier tabla con `match_id`), sus filas de `standings`, `standings_detail`, `scorers`, `fiflp_groups` y `fiflp_full_pending`; las de `team_seasons` de los equipos que esa temporada solo salen en esos grupos; y los equipos que solo salían en ellos. Lo que cuelga se descubre con `PRAGMA foreign_key_list`/columnas `group_id`, `match_id`, `team_id` (una tabla nueva que las tenga entra sola), con la lista explícita de arriba como mínimo.
  - `scripts/tests/base_mayores.py`: `poblar(conn, categorias=("INFANTIL", "CADETE", "JUVENIL"), temporada="2026-2027", islas=False) -> dict` — escribe en una copia lo que dejaría el bot tras activar y leer esas categorías: un raw sintético con, por categoría, tres competiciones de la tabla de 2026-27 (una liga de Gran Canaria con dos grupos, una de Lanzarote y una copa con eliminatorias) y equipos con nombres de clubes que ya están en la base y alguno nuevo; su manifiesto con `fiflp_manifest.build` (con los códigos que ya tiene la temporada en `taken`); el alta con `activate_season.add_groups`; 6 jornadas jugadas por grupo con resultado, clasificación y goleadores; un acta sintética por partido jugado (con 18 jugadores por equipo) importada con `import_fiflp_actas._import_one`, en la que un tercio de los jugadores llevan el identificador de la federación de jugadores de benjamín o alevín de 2019-20 a 2021-22 de la base (los mismos niños, más mayores) y el resto, identificadores nuevos; fichas de equipo (`team_seasons`) de los equipos nuevos. Con `islas`, también dos grupos de «LIGA ALEVIN LANZAROTE FASE 1» (con `ALEVIN_ISLAS` a `True` durante la llamada). Devuelve `{"grupos": [códigos], "partidos": n, "actas": n, "jugadores_reutilizados": n}`. Nombres de jugador inventados (`f"JUGADOR {n:05d}, PRUEBA"`); nunca nombres reales.
  - `scripts/prueba_mayores.py [--categorias infantil,cadete,juvenil] [--islas] [--conservar]` — la base de después, entera, en un árbol temporal: `git worktree add --detach <tmp>/despues HEAD`; copia la base real del árbol con `backup` a su `futbolbase.db`; `poblar`; añade a su `data-health.json` una entrada `ok` por grupo nuevo (como la dejaría el bot); en ese árbol, `migrate_identidad.resolver_fichas` y `generate_js.main()` con `PROJECT_ROOT` y la conexión de esa copia; y allí `python3 -m pytest scripts/tests/ -q -p no:cacheprovider` y `node --test scripts/tests/test_*.mjs`. Imprime el tamaño de la base antes y después, los segundos de cada paso y «verde» o «rojo» con lo que falló; sale con 0 solo en verde. Borra el árbol temporal (`git worktree remove --force`) salvo con `--conservar`. Nunca toca el árbol de trabajo.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_vista_web.py`:
  - `test_sin_otras_categorias_es_la_misma_conexion`: en una base sintética con solo benjamín, `copia_web(conn) is conn`.
  - `test_la_copia_no_tiene_lo_de_infantil`: base sintética con `FF1` (benjamín) e `INFPG1` (infantil), partidos, apariciones, goleadores, clasificación y `team_seasons` de un equipo que solo juega en infantil y de otro que juega en los dos: en la copia no hay ningún grupo, partido, aparición, goleador ni fila de clasificación de infantil; el equipo solo de infantil no está y el de los dos conserva su `team_seasons`; la base original no ha cambiado (cuenta filas antes y después).
  - `test_generador_igual_con_y_sin_mayores` (salta sin `futbolbase.db`; lenta, ~2-3 min): dos copias de la base real en `tmp_path`, `A` tal cual y `B` con `poblar(B)`; en cada una, `resolver_fichas` y `generate_js.main()` con su propio `PROJECT_ROOT` (un directorio con `index.html`, `sw.js` y los `data-*.js` del árbol copiados); todos los ficheros que escribe son iguales byte a byte entre `A` y `B` tras quitar `"mb":<número>` de `COBERTURA` y las versiones (`?v=<hex>` y `CACHE_NAME`); y en `B`, ningún `data-*.js` nombra un código de la lista de `poblar`.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_vista_web.py` — Expected: no encuentra el módulo.
- [ ] **Step 3: Implementar** `vista_web.py` (cabecera: por qué una copia filtrada y no un filtro en cada consulta del generador: el generador tiene unas 40 consultas y la web no puede enseñar nada de una categoría que no sabe pintar; una copia sin esas filas es una garantía que no depende de no olvidar ninguna) y el cambio de `generate_js.main`.
- [ ] **Step 4: Implementar** `base_mayores.py` y `prueba_mayores.py`.
- [ ] **Step 5: La base de después.** Run: `python3 scripts/prueba_mayores.py` — Expected: «verde». Cada prueba en rojo se arregla para que valga con la base de antes y con la de después (que compare con las categorías de `EN_WEB`, o que no suponga que la temporada en curso solo tiene tres categorías), nunca saltándola con la base de después. Apunta en el informe cuáles fueron y los tiempos.
- [ ] **Step 6: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs` (en el árbol) y `python3 scripts/prueba_mayores.py --islas` — Expected: en verde los dos (el segundo, con el alevín de islas en la web: `data-alevin.js` lo trae y las suites lo aceptan).
- [ ] **Step 7: Commit.** Asunto «Generador: solo publica las categorías de la web; prueba de la base de después de activar las nuevas».

---

### Task 7: El bot por carriles

**Files:**
- Modify: `scripts/update_fiflp.py` (`LEVELS`, `LEVEL_ORDER` nueva, `plan_groups`, `BACKFILL_ORDER`, `run_passes` (parámetro `extras`), `update_groups`)
- Modify: `scripts/source_health.py` (`set_run_health`, `dry_since`, `note_run`, `begin` (`_carry_carriles`), `main`)
- Create: `scripts/tests/fixtures/plan_principal.json` (el orden de hoy, calculado en el commit anterior a esta tarea)
- Test: `scripts/tests/test_bot_rotacion.py`, `scripts/tests/test_bot_carriles.py` (nuevo), las de `source_health` (`grep -ln set_run_health scripts/tests/`)

**Interfaces:**
- Consumes: `categorias.carril_actual`, `categorias.CARRILES`.
- Produces:
  - `update_fiflp.LEVELS = {"PREBENJAMIN": 1, "ALEVIN": 3, "INFANTIL": 4, "CADETE": 5, "JUVENIL": 6}` (lo demás, 2); `_level` igual que hoy (un código `AL…` es 3).
  - `update_fiflp.LEVEL_ORDER = (3, 1, 2, 4, 5, 6)` — el orden de los tramos de `plan_groups` (los tres primeros son los de hoy, en su orden: así las fases de `pass_phase` de cada nivel de hoy no cambian). La cuota de `alevin_quota` sigue siendo solo del nivel 3.
  - `update_fiflp.BACKFILL_ORDER = ("PREBENJAMIN", "BENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")`.
  - `update_fiflp.EXTRAS = {"principal": ("competiciones", "campos", "directorio"), "mayores": ("directorio",)}` y `run_passes(..., extras=EXTRAS["principal"])`: solo hace los extras de la tupla (los demás no se piden ni cuentan como pendientes).
  - `update_groups`: con el carril de `carril_actual()`, llama a `run_passes(..., extras=EXTRAS[carril])` y escribe su veredicto y sus notas con `carril=`.
  - `source_health.set_run_health(reasons, now=None, dry=False, carril="principal")`, `source_health.dry_since(carril="principal")`, `source_health.note_run(info, carril="principal")`: con `"principal"`, lo de hoy (`runHealth`, `run`); con otro, en `report["carriles"][carril] = {"runHealth": {...}, "run": {...}}`, la misma forma, sin tocar `runHealth` ni `run`. `begin` arrastra `carriles` como arrastra `runHealth` (misma temporada). `VOLATILE` incluye `carriles.<c>.run` (no reescribe el informe por sí solo).
  - CLI `source_health.py veredicto` y `marcar "<motivo>"`: el carril de `carril_actual()` (la variable `FIFLP_CATS` del job); el de `"mayores"` mira y marca `carriles.mayores.runHealth`.

- [ ] **Step 1: La prueba de oro.** Antes de tocar `update_fiflp.py`, con el código de hoy, escribe `scripts/tests/fixtures/plan_principal.json`: para la base sintética de `test_bot_rotacion.py` (81 grupos, los 7 de Las Mesas) y los números de pasada 0 a 199, a las 8:00 UTC de un martes, `plan_groups(...).order` como lista de códigos. Prueba `test_plan_principal_igual_que_antes` en `test_bot_rotacion.py`: con el código nuevo, la misma base y la misma base más 45 grupos de infantil, cadete y juvenil (pero `groups` de `fiflp_groups(conn, sid, CARRILES["principal"])`), los mismos órdenes.
- [ ] **Step 2: Pruebas que fallan** en `scripts/tests/test_bot_carriles.py`:
  - `test_plan_del_carril`: una base con 14 grupos de infantil, 17 de cadete y 10 de juvenil (códigos de la tabla) y `plan_groups` sobre ellos: en 4 números seguidos cada grupo va en el tramo del turno exactamente una vez; cada pasada intercala las tres categorías en proporción a sus grupos (en los 12 primeros de cada orden hay de las tres); ningún grupo de nivel 1-3.
  - `test_el_carril_no_toca_la_salud_del_bot(monkeypatch)`: con `FIFLP_CATS=infantil,cadete,juvenil` y una pasada seca (`run_passes` parcheado que no lee nada), `data-health.json` gana `carriles.mayores.runHealth` con `drySince` y conserva `runHealth` y `run` como estaban; y la siguiente del carril principal, seca también, empieza su propia racha.
  - `test_extras_del_carril(monkeypatch)`: con el carril de mayores, `check_competitions` y `update_campos` no se llaman y `update_directorio` sí (con una federación falsa que sirve todo).
  - `test_veredicto_por_carril`: `source_health.main(["veredicto"])` con `FIFLP_CATS=infantil,cadete,juvenil` sale con 1 si `carriles.mayores.runHealth.ok` es falso aunque `runHealth.ok` sea verdadero, y con 0 al revés; `marcar "x"` con ese carril solo marca el suyo.
- [ ] **Step 3: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_bot_carriles.py scripts/tests/test_bot_rotacion.py` — Expected: fallan las nuevas; la de oro pasa (aún no hay cambios).
- [ ] **Step 4: Implementar** lo de «Produces». En el comentario de `LEVEL_ORDER`, por qué los niveles nuevos van detrás (no cambian las fases de interleave de los de hoy) y por qué cada carril tiene sus niveles (el carril de mayores nunca tiene grupos de los niveles 1-3 ni el principal de los 4-6).
- [ ] **Step 5: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && python3 scripts/prueba_mayores.py` — Expected: en verde los dos.
- [ ] **Step 6: Commit.** Asunto «Bot: cada carril con sus niveles, sus extras y su veredicto; el de siempre, en el mismo orden».

---

### Task 8: La activación de las categorías nuevas

**Files:**
- Modify: `scripts/fetch_fiflp_islas.py` (`tanda_categories`, el arranque con `ISLAS_SEASON`: los sufijos de `categorias.TANDAS`; `CATALOG_SEASONS`; docstring)
- Modify: `scripts/activar_auto.py` (`raw_de`, `tandas_pendientes` nueva, `--tandas`)
- Modify: `.github/workflows/activar.yml` («Descargar lo pendiente»: las tandas de `activar_auto.py --tandas`)
- Modify: `.github/workflows/fetch-fiflp-islas.yml` (la descripción de `temporada`: `22`, `22al`, `22inf`, `22cad`, `22juv`)
- Create: `scripts/quitar_categoria.py`
- Test: `scripts/tests/test_activacion_categorias.py` (nuevo; sigue el estilo de `test_alevin_activacion.py`), `scripts/tests/test_alevin_descargas.py` (los sufijos), `scripts/tests/test_workflows.py` (el bucle de `activar.yml`)

**Interfaces:**
- Consumes: `categorias.TANDAS`, `categorias.sufijo_tanda`, `categorias.categorias_de_tanda`, `categorias.activable`, `fiflp_manifest.build` (tarea 2).
- Produces:
  - `fetch_fiflp_islas.tanda_categories(key, env=None)`: el sufijo de `key` tras los dígitos (`"22inf"` → `("INFANTIL",)`); `FIFLP_CATS` manda, como hoy; un sufijo que no está en `TANDAS` sale con el mensaje de hoy («ISLAS_SEASON=… no soportada»).
  - `activar_auto.raw_de(comp, name, code, root=ROOT, raws=None) -> Path` — busca la competición en el raw de cada tanda de `TANDAS` (`fiflp_islas_<code><sufijo>_raw.json`) y, si no está en ninguno, el de la tanda de su categoría.
  - `activar_auto.tandas_pendientes(health, code, root=ROOT) -> list[str]` — las tandas (`"22"`, `"22al"`, `"22inf"`…) con alguna competición pendiente (`pendientes(health)`) de sus categorías, en el orden de `TANDAS`.
  - CLI `python3 scripts/activar_auto.py --tandas` — imprime esas tandas separadas por espacios (nada si no hay); `activar.yml` las recorre: `for TANDA in $(python3 scripts/activar_auto.py --tandas); do …` (con el mismo plazo de 20 min, `ISLAS_HASTA`).
  - `scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL [--isla lanzarote] [--apply]` — la marcha atrás de un paso del director: sin `--apply`, cuántos grupos, partidos, actas, apariciones y jugadores sueltos quitaría; con `--apply`, los quita en una transacción (los grupos con `db.delete_group_matches` y lo que cuelga, como `vista_web.copia_web` pero en la base que se le dé con `--db`, por defecto `futbolbase.db`). Solo acepta una categoría de `MAYORES` o `ALEVIN` con `--isla` `lanzarote` o `fuerteventura`; con otra, sale con error sin tocar nada.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_activacion_categorias.py`:
  - `test_tanda_de_cada_categoria(monkeypatch)`: `tanda_categories("22inf") == ("INFANTIL",)`, `("22juv") == ("JUVENIL",)`, `("22al") == ("ALEVIN",)`, `("22") == ("BENJAMIN", "PREBENJAMIN")`; `comps_from_catalog("2026-2027", catalog=<congelado>, categories=("INFANTIL",))` da los ids `54976908`, `54976916`, `55184138`, `54976911`, `54976929`, en el orden del catálogo.
  - `test_activar_infantil_de_punta_a_punta(tmp_path, monkeypatch)`: un árbol en `tmp_path` con una base sintética de 2026-27 (los grupos de benjamín y alevín de hoy), `scripts/fiflp_islas_22inf_raw.json` y `_grupos.json` sintéticos (dos grupos de «LIGA INFANTIL PREFERENTE DE GRAN CANARIA», 54976908), `data-health.json` con `newCompetitions` de esa competición; con `ACTIVABLES` parcheado con `INFANTIL` y `regenerar` y `run_sonda` parcheados: `activar_auto` activa `INFPG1` e `INFPG2` con categoría `INFANTIL`, isla `grancanaria`, fase «Preferente GC», en `fiflp_full_pending`, y `activation.activated` los lista; los grupos de benjamín y alevín no cambian.
  - `test_desempate_falla_sin_convenio`: con `CADETE` activable y `newCompetitions` con 55133947 y 54976894 en el raw `22cad`: la de Interinsular se activa (`CADI1`) y la del desempate queda en `activation.failed` con «sin convenio de código: ELIMINATORIA DESEMPATE CADETE INSULAR»; sale con 1.
  - `test_tandas_pendientes`: con pendientes de benjamín, infantil y juvenil, `["22", "22inf", "22juv"]`; sin pendientes, `[]`; `--tandas` imprime `22 22inf 22juv`.
  - `test_quitar_categoria(tmp_path)`: sobre una copia con `poblar` (tarea 6), el ensayo cuenta lo de infantil; `--apply` lo quita y deja benjamín, alevín, cadete y juvenil igual; `--categoria BENJAMIN` sale con error sin tocar la base.
  - En `test_workflows.py`: «Descargar lo pendiente» de `activar.yml` saca sus tandas de `activar_auto.py --tandas` y ya no nombra `${CODIGO}al`.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_activacion_categorias.py scripts/tests/test_alevin_descargas.py scripts/tests/test_workflows.py` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces».
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && python3 scripts/prueba_mayores.py` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto «Activación: las tandas de infantil, cadete y juvenil, y cómo quitar una categoría si hace falta».

---

### Task 9: Los workflows del carril y el reloj

**Files:**
- Modify: `.github/workflows/update.yml` (`on.workflow_call` con la entrada `cats`; la concurrencia, del nivel del workflow al del job; `FIFLP_CATS` en el `env` del job; el asunto del commit; comentarios de cabecera)
- Create: `.github/workflows/carril-mayores.yml`
- Modify: `.github/workflows/reloj.yml` (lista las ejecuciones de los tres workflows; decide y lanza el carril)
- Modify: `scripts/reloj_pasadas.py` (`due_carril` nueva; `due` también mira el carril; la entrada `--carril`/`--activar`; constantes)
- Test: `scripts/tests/test_reloj_pasadas.py`, `scripts/tests/test_workflows.py`

**Interfaces:**
- Consumes: el veredicto por carril de la tarea 7 (`source_health.py veredicto` lee `FIFLP_CATS`).
- Produces:
  - `update.yml`: `on: workflow_dispatch` (como hoy, con `cats`) y `workflow_call` con `inputs.cats` (`type: string`, `default: ''`); `jobs.update.concurrency: {group: update-data, cancel-in-progress: false}` y ninguna concurrencia a nivel del workflow (con la del llamante, GitHub la daría por bloqueo mutuo); `jobs.update.env.FIFLP_CATS: ${{ inputs.cats }}` (la ven todos los pasos, también `source_health.py`); el asunto del commit de datos, `Actualización automática <fecha>` y, con `FIFLP_CATS`, `Actualización automática (infantil,cadete,juvenil) <fecha>`.
  - `carril-mayores.yml` («Pasadas de infantil, cadete y juvenil»): `on: workflow_dispatch` (sin entradas); `permissions: contents: write, actions: write`; un job `pasada` con `uses: ./.github/workflows/update.yml` y `with: cats: infantil,cadete,juvenil`; sin `concurrency` propia. Cabecera: por qué un workflow aparte (su número de pasada y el reloj, «El carril de las categorías mayores» en `docs/categorias-mayores.md`).
  - `reloj_pasadas.CARRIL_CADA = timedelta(hours=4)`, `CARRIL_DESDE = timedelta(minutes=25)`, `CARRIL_HASTA = timedelta(minutes=75)`, `ANTES_DE_VENTANA = timedelta(hours=1)`.
  - `reloj_pasadas.due(now, runs, otros=())` — lo de hoy, y además `False` («el carril está sin acabar») si alguna de `otros` (las ejecuciones del carril) no está `completed`.
  - `reloj_pasadas.due_carril(now, principal, carril, activar) -> tuple[bool, str]` (como `decide(now, runs)`, que ya da su motivo) — `(True, motivo)` solo si: `now` no está en una ventana ni a menos de `ANTES_DE_VENTANA` de una (con la base de zonas: sin ella, nunca); ninguna de las tres listas tiene una ejecución sin acabar; la última de `principal` empezó (`run_time`) hace entre `CARRIL_DESDE` y `CARRIL_HASTA`; y la última de `carril` empezó hace `CARRIL_CADA - SLACK` o más (o no hay ninguna). Nunca es `True` a la vez que `due` (si `due` toca, gana la pasada del bot).
  - CLI: `python3 scripts/reloj_pasadas.py [--now …] [--carril <json> --activar <json>] < pasadas.json` — escribe `due=…` y `due_carril=…` en `$GITHUB_OUTPUT`; sin `--carril`, `due_carril=false`.
  - `reloj.yml`: el paso que decide lista también `carril-mayores.yml` y `activar.yml` (`gh run list --workflow … --limit 20 --json number,event,status,conclusion,createdAt,startedAt`) y pasa `--carril`/`--activar` solo si `vars.CARRIL_MAYORES == '1'` (por `env:`); un paso «Lanzar el carril» con `if: steps.reloj.outputs.due_carril == 'true'` que lanza `gh workflow run carril-mayores.yml --ref main --repo "$GITHUB_REPOSITORY"` y espera a verlo como el de la pasada. El checkout disperso sigue siendo solo `scripts/reloj_pasadas.py`.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_reloj_pasadas.py`:
  - `test_due_carril`: un martes a las 10:40 (hora de Canarias, UTC+0 en invierno) con la última del bot empezada a las 10:10 y acabada, ninguna del carril → `True`; a las 10:20 (10 min) → `False`; a las 11:30 (80 min) → `False`; con una del carril empezada a las 7:00 → `False` (3 h 40 min), a las 6:45 → `True` (3 h 55 min); con `activar.yml` en marcha → `False`; con el carril sin acabar → `False`; un viernes a las 17:10 → `False` (a menos de 1 h de la ventana); un sábado a las 8:40 → `True`, a las 9:10 → `False`; un sábado a las 12:00 → `False` (ventana); sin zona horaria → `False`.
  - `test_due_espera_al_carril`: con el carril sin acabar, `due` es `False` aunque toque por la hora.
  - `test_semana_con_carril`: la semana del 30/11 al 6/12/2026 en ticks de 15 min (minutos 7, 22, 37 y 52), cada pasada del bot y del carril dura 24 min y nunca hay `activar.yml`: las horas de arranque de las pasadas del bot son las mismas que en la misma semana sin carril; nunca hay dos ejecuciones a la vez; el carril hace 6 pasadas cada día de lunes a jueves, al menos 4 el viernes y 3 el sábado y el domingo, y ninguna dentro de una ventana ni a menos de 1 h de una.
  - `test_carril_no_comparte_numero_ni_reloj`: la decisión del bot (`due`) solo mira la lista de `update.yml`: añadir ejecuciones acabadas del carril a `otros` no cambia cuándo toca.
- [ ] **Step 2: Pruebas que fallan** en `scripts/tests/test_workflows.py`: `update.yml` tiene `workflow_call` con la entrada `cats`, `jobs.update.concurrency.group == "update-data"` y ninguna `concurrency` a nivel del workflow, y `FIFLP_CATS` en el `env` del job; `carril-mayores.yml` solo se lanza a mano (`workflow_dispatch`), su único job llama a `./.github/workflows/update.yml` con `cats: infantil,cadete,juvenil`, no tiene `concurrency` y sus permisos son `contents: write` y `actions: write`; `reloj.yml` lanza `carril-mayores.yml` solo con `due_carril` y pasa `--carril` solo con `vars.CARRIL_MAYORES`; las de hoy (el reloj solo lanza `update.yml` sobre `main` cuando toca, el job de 40 min cabe en la cadencia, `test_solo_el_bot_escribe_la_base`), adaptadas a la concurrencia en el job y con `carril-mayores.yml` entre los que pueden escribir la base (a través de `update.yml`).
- [ ] **Step 3: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_reloj_pasadas.py scripts/tests/test_workflows.py` — Expected: fallan las nuevas.
- [ ] **Step 4: Implementar** lo de «Produces». En la cabecera de `reloj_pasadas.py`, la regla del carril con los números de «El carril de las categorías mayores»; en `update.yml` y `reloj.yml`, comentarios que dicen por qué (el número de pasada propio, la concurrencia en el job, el reloj que no cuenta el carril como pasada del bot).
- [ ] **Step 5: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && python3 scripts/prueba_mayores.py` — Expected: en verde.
- [ ] **Step 6: Commit.** Asunto «Carril de infantil, cadete y juvenil: update.yml reutilizable, su workflow y el reloj que lo lanza entre pasadas (apagado)».

---

### Task 10: Documentación

**Files:**
- Create: `docs/categorias-mayores.md`
- Modify: `docs/federacion.md` (sección nueva «El carril de las categorías mayores», tras «El reloj de las pasadas»), `docs/temporada-nueva.md` (las tandas `inf`, `cad`, `juv` y el carril al abrir una temporada), `docs/alevin.md` («Alcance»: el alevín de islas, desde el paso D6), `docs/decisiones.md` (cinco líneas: conocer no es activar; un carril aparte con su número de pasada; el convenio por algoritmo; el generador sobre una copia con lo de la web; un lote de actas por categoría)

- [ ] **Step 1:** `docs/categorias-mayores.md`, como `docs/alevin.md` para alevín: alcance (qué entra y qué no, con fútbol sala, femenino y mayores fuera); el contrato (las claves, `ACTIVABLES`, `CARRILES`, `EN_WEB`, `TANDAS`, `ALEVIN_ISLAS`); el convenio (el esquema, los diez puntos y la tabla de 2026-27, con un enlace a la tabla entera de este plan y a la fixture); las protecciones; el carril (cuándo, cuántas, los números, cómo se enciende y se apaga, su veredicto aparte); los pasos D2-D6 tal cual, con sus comprobaciones; cómo se quita una categoría (`quitar_categoria.py`); y lo de la parte F (el encargo de una temporada de infantil, con la orden). Sin nombres de niños.
- [ ] **Step 2:** Las modificaciones de los otros cuatro documentos.
- [ ] **Step 3: Commit.** Asunto «Documentación: infantil, cadete y juvenil (datos), el convenio, el carril y los pasos para activarlos».

---

## Pasos del director tras la tarea 10

**PASO DEL DIRECTOR — D1: publicar las tareas 1-10.** Con `R=malolocabreralolo-tech/futbol-base-v2`:
1. Sin nada en marcha (`gh run list -R $R --status in_progress` y `--status queued`, vacías): rebasar la rama sobre `main` como dice `docs/rediseno-rebase.md`, `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && python3 scripts/prueba_mayores.py`, y `git push origin categorias:main`.
2. Comprobación: la pasada siguiente del bot (`gh run list -R $R --workflow update.yml --limit 1`) en verde; en su `data-health.json`, `run.groups == 107` (o lo que tuviera la de antes) y ninguna clave `carriles`; `git show --stat origin/main` de su commit no cambia más `data-*.js` que una pasada normal; `gh variable list -R $R` no tiene `CARRIL_MAYORES` (el carril, apagado).
3. Vuelta atrás: `git revert` de los commits de la rama, con nada en marcha.

**Antes de cada uno** (D2-D6): nada en marcha en `update-data` (`gh run list -R $R --status in_progress` y `--status queued`, sin `update.yml`, `carril-mayores.yml` ni `activar.yml`); `git pull`; la base de `main` por debajo de 70 MB (`ls -l futbolbase.db`) o la parte D en su fase 3; y `python3 scripts/prueba_mayores.py --categorias <las que ya están activas y la nueva>` en verde sobre el `main` de ese momento.

**PASO DEL DIRECTOR — D2: encender el carril.**
1. `gh variable set CARRIL_MAYORES --body 1 -R $R`.
2. Comprobación: en las 4 h siguientes, fuera de una ventana, una ejecución de `carril-mayores.yml` (`gh run list -R $R --workflow carril-mayores.yml --limit 3`) en verde y sin ninguna página pedida a la federación (sin la línea «Federación (FIFLP): N grupos» en el registro: no hay grupos que leer); en `data-health.json`, `carriles.mayores.runHealth.ok` verdadero; las pasadas del bot de ese rato, a su hora de siempre (los `createdAt` de `gh run list --workflow update.yml` siguen cada ~2 h).
3. Vuelta atrás: `gh variable set CARRIL_MAYORES --body 0 -R $R` (o `gh variable delete CARRIL_MAYORES -R $R`).

**PASO DEL DIRECTOR — D3: infantil.**
1. Un commit de una línea en `main` (sin nada en marcha): `ACTIVABLES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL")` en `scripts/categorias.py`, con las suites en verde; `git push`.
2. Lo que pasa solo: en la primera pasada del bot con sus extras (como mucho un día), `newCompetitions` trae las 5 de infantil de 2026-27; `activar.yml` baja la tanda `22inf` (~14 grupos, ~450 páginas: 3-6 intentos de 20 min alternados con pasadas) y las activa; el carril hace la primera lectura completa de cada grupo.
3. Comprobación: `activation.activated` de `data-health.json` lista los códigos `INF…`; `python3 -c "import sqlite3; c=sqlite3.connect('futbolbase.db'); print(c.execute(\"select count(*) from groups g join categories c on c.id=g.category_id where c.name='INFANTIL'\").fetchone())"` da el número de grupos de `scripts/fiflp_islas_22inf_grupos.json`; las pasadas del bot siguen en verde y su `run.groups` no cambia; la web, igual (`data-*.js` de la pasada siguiente sin códigos `INF`: `grep -l '"INF' data-*.js` no da nada).
4. Las actas ya jugadas, con el carril del histórico (sin nada del histórico en marcha): `gh workflow run historico.yml -R $R --ref main -f accion=encargar -f temporadas=22 -f categorias=infantil -f trabajos=actas`; comprobación: `python3 scripts/historico.py estado` hasta «2026-27 · actas infantil: en la base», y el tamaño de la base tras esa promoción (lo previsto: ~+2-3 MB).
5. Si hay más de 60 grupos entre las categorías activas, `CARRIL_CADA` a 2 h (tarea 9).
6. Vuelta atrás: revertir el commit de `ACTIVABLES` (no activa nada más); el carril sigue leyendo lo activado: para que no lo lea, D2 vuelta atrás; para sacarlo de la base, con el bot parado (`reloj.yml` desactivado: `gh workflow disable reloj.yml -R $R`), `python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL --apply`, suites en verde, commit de la base y `gh workflow enable reloj.yml -R $R`.

**PASO DEL DIRECTOR — D4: cadete** y **D5: juvenil**: como D3, con `CADETE` (tanda `22cad`, ~17 grupos; la del desempate queda en `activation.failed`, a propósito) y después `JUVENIL` (`22juv`, ~10 grupos), cada uno con sus actas encargadas al histórico. Entre uno y otro, una semana de pasadas en verde y la base medida.

**PASO DEL DIRECTOR — D6: el alevín de Lanzarote y Fuerteventura.** Es el único paso de E1 que se ve en la web: sus grupos entran en «Alevín» (sus fases, «Lanzarote Fase 1» y «Fuerteventura Fase 1», ya las conoce la web). Mejor sin ningún encargo de alevín del histórico a medias (desde este paso, un encargo de alevín incluye también el de las islas). Un commit: `ALEVIN_ISLAS = True`; comprobación: `activation.activated` con `ALUL…` y `ALUF…`, los leen las pasadas del bot de siempre (su `run.groups` sube en ~4), `python3 scripts/prueba_mayores.py --islas` en verde antes; vuelta atrás: revertir y `quitar_categoria.py --categoria ALEVIN --isla lanzarote --apply` (y `fuerteventura`), con el bot parado.
