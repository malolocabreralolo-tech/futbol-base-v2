# Infantil, cadete y juvenil (y el alevín de Lanzarote y Fuerteventura): los datos

La parte E1 de la ampliación (plan: [`superpowers/plans/2026-11-25-ampliacion-e1-categorias-datos.md`](superpowers/plans/2026-11-25-ampliacion-e1-categorias-datos.md)). El código ya conoce infantil, cadete y juvenil de 2026-27 (fútbol 11, Gran Canaria, Lanzarote, Fuerteventura y las ligas de varias islas) y el alevín de Lanzarote y Fuerteventura, y tiene listo su carril, pero **no activa ni lee nada de eso todavía**: cada paso lo da el director, uno cada vez (abajo, «Los pasos del director»). Y aunque estén en la base, **la web no los enseña** hasta la parte E2 (`categorias.EN_WEB`), salvo el alevín de las islas desde su paso (D6), que entra en «Alevín».

## Alcance

- **Entran** (cuando el director dé su paso): las competiciones de **infantil, cadete y juvenil** de la temporada en curso, de fútbol, de cualquier isla y de varias (División de Honor, Autonómica, Interinsular, Territorial: isla `interinsular` en la base), y las de **alevín de Lanzarote y Fuerteventura** (desde D6).
- **Fuera, siempre**: fútbol sala (`SALA`, `FS` o `F.S.` sueltos, la liga `LPFS`), fútbol femenino (`FEMENIN…`, `FUTUREFEM`), playa, veteranos y las categorías de mayores (senior). Un nombre con dos de las categorías alevín, infantil, cadete y juvenil, tampoco (no se sabe cuál es). `categorias.category_of` da `None` («no se publica») y `convenio.convenio` da `SinConvenio("no se publica")`.
- **2026-27**: 24 competiciones de las categorías nuevas en el catálogo (juvenil 6, cadete 11, infantil 5, alevín de las islas 2); 23 con convenio de código y 1 sin él («ELIMINATORIA DESEMPATE CADETE INSULAR», que no dice la isla: queda en `activation.failed` a propósito). Los grupos no los dice el catálogo; la estimación es de **~45** (juvenil ~10, cadete ~17, infantil ~14, alevín de las islas ~4), entre 35 y 60. El número de verdad sale de `scripts/fiflp_islas_22<sufijo>_grupos.json` al descargar cada categoría.
- **Lo que se ve antes de E2**: nada en la web, salvo «Datos y fuentes», que lista con su código (al final de «Comprobación por grupo») los grupos de las categorías nuevas que compruebe el carril: `data-health.json` trae su entrada como la de cualquier grupo. El rojo del carril no sale en la web (`runHealthNote` solo mira el del bot de siempre): está en `carriles.mayores` de `data-health.json` y en Actions.

## El contrato (`scripts/categorias.py`)

Un solo sitio decide la categoría, y separa cuatro preguntas a propósito: **conocerla no dispara nada**. Si reconocer infantil bastara para activarlo, en cuanto el módulo lo conociera se activarían de golpe sus competiciones, el bot de siempre leería sus grupos sin sitio para ellos y la web los enseñaría a medio cargar.

| | Qué es | Hoy | Quién lo cambia |
|---|---|---|---|
| `category_of(nombre)` | la categoría de una competición, de la cabecera de un acta o de una liga de la app: `PREBENJAMIN`, `BENJAMIN`, `ALEVIN`, `INFANTIL`, `CADETE`, `JUVENIL` o `None` | las seis | — |
| `DB_NAME` | clave de la web (`infantil`) → nombre en `categories` (`INFANTIL`) | las seis | — |
| `ACTIVABLES` | lo que el bot apunta en `newCompetitions` y `activar_auto` activa solo | `("BENJAMIN", "PREBENJAMIN", "ALEVIN")` | el director: D3, D4, D5 |
| `ALEVIN_ISLAS` | el alevín de Lanzarote y Fuerteventura cuenta como alevín (si no, `None`) | `False` | el director: D6 |
| `CARRILES` | qué lee cada carril: `principal` (prebenjamín, benjamín, alevín: el bot de siempre, sin `FIFLP_CATS`) y `mayores` (infantil, cadete, juvenil: `carril-mayores.yml`) | — | — |
| `EN_WEB` | lo que ven el generador (`vista_web.copia_web`) y el resolvedor de fichas | `("BENJAMIN", "PREBENJAMIN", "ALEVIN")` | la parte E2 |
| `TANDAS` | el sufijo de la tanda de activación (`scripts/fiflp_islas_<CodTemporada><sufijo>_raw.json`): `""` benjamín y prebenjamín, `al` alevín, `inf`, `cad`, `juv` | — | — |

Y lo que cuelga de ellas:

- **La base.** Las filas `INFANTIL`, `CADETE` y `JUVENIL` de `categories` no existen hasta que `activate_season` activa su primer grupo (`migrate_categories` solo crea las de `EN_WEB`: si no, la primera pasada tras publicar el código cambiaría la base sin nada que publicar). `groups.island` admite `interinsular` solo en las mayores (`activate_season.isla_admitida`); en benjamín, prebenjamín y alevín sigue siendo «Isla no admitida». Al casar los nombres de los equipos del raw con los de la base, una interinsular casa con cualquier isla (`activate_season.mismas_islas`).
- **La activación.** `activar_auto.py --tandas` da las tandas con algo pendiente de una categoría activable (`22`, `22al`, `22inf`, `22cad`, `22juv`, en ese orden), y `activar.yml` descarga solo esas. Lo pendiente de una categoría que no está en `ACTIVABLES` va a `activation.failed` («categoría que el bot aún no activa: INFANTIL») sin tocar la base ni descargarse.
- **Las actas, un lote por categoría** (`actas_lotes.py`): las del carril del histórico van a `scripts/fiflp_actas_<S>_<categoría>_raw.json` (con su `_index.json` y su `_status.json`), nunca al raw de benjamín y prebenjamín ni al de alevín; las que lee el bot, a `scripts/actas_bot_<S>_<categoría>.jsonl`.
- **Identidad y ranking** (`docs/identidad.md`, `docs/ranking.md`): niveles 4, 5 y 6 y sus edades (`identidad._EDAD`); el resolvedor de fichas y los enlaces de MyGol (`enlace_mygol.fichas_de`) solo miran las apariciones de `EN_WEB`. Un niño que la federación da con el mismo identificador en benjamín y en cadete cae en la misma fila de `players`, pero antes de E2 su ficha, su año y el ranking no cambian.
- **La web**, sobre una copia: `generate_js.main` trabaja sobre `vista_web.copia_web(conn)`, una copia en memoria sin los grupos de fuera de `EN_WEB` ni lo que cuelga de ellos (con la base de hoy, la misma conexión). Con la base de después, los `data-*.js` salen iguales byte a byte que sin las mayores (`test_vista_web.test_generador_igual_con_y_sin_mayores`).

## El convenio de códigos (`scripts/convenio.py`)

Para las competiciones de **infantil, cadete y juvenil** (siempre) y las de **alevín cuyo nombre dice Lanzarote o Fuerteventura** (el alevín de Gran Canaria sigue con [alevin.md](alevin.md)), por un algoritmo sobre el nombre, comprobado contra el catálogo entero de 2016-17 a 2026-27:

```
código = CATEGORÍA + NIVEL + ISLA + FASE + TIPO + número de grupo
```

1. **El nombre**, sin tildes y en mayúsculas; `1ª`/`2ª` → `PRIMERA`/`SEGUNDA`; lo que no es letra ni cifra, espacio; fuera la modalidad (`F-8`, `F8`, `F7`, `FUTBOL-8`…), `GRUPO <n>`, `DE LAS PALMAS` y un guion inicial.
2. **Fuera** (`SinConvenio("no se publica")`): sala, femenino, playa y veteranos (arriba).
3. **CATEGORÍA** (también `INFANTILL`, así en el catálogo de 2024-25): `INF`, `CAD`, `JUV`, `AL`.
4. **TIPO**: `FINAL`/`SEMIFINAL(ES)` delante → el del resto más `F`/`S`; `FASE FINAL` detrás → la liga más `F`; `ELIMINATORIA(S) COPA …` o `COPA … ELIMINATORIAS` → la copa más `E`; `ELIMINATORIAS DE ASCENSO A …` → `E` sobre el nivel e isla del destino; `FASE (DE) ASCENSO (A) …` → `A`; otra `ELIMINATORIA`, `PLAY OFF`, `DESEMPATE`, `TORNEO` o `CLAUSURA` → sin convenio; `COPA …` → `CK` (campeones), `CD` (delegación) o `C`; lo demás, una liga.
5. **FASE**: segunda fase → `SF` (« Fase 2»); primera fase → nada (« Fase 1»); `FASE ORO` → `FO`; `FASE PLATA` → `FP`; `SUBGRUPO X` → la letra; otra `FASE` → sin convenio.
6. **NIVEL** (uno; con dos, sin convenio, salvo `INSULAR B`, que manda sobre `INSULAR`): `H` División de Honor, `A` Autonómica, `I` Interinsular, `T` Territorial, `S` Superliga, `P` Preferente, `1` Primera, `2` Segunda, `NB` Insular B, `N` Insular; ninguno, `U`.
7. **ISLA**: Lanzarote y Fuerteventura → `X` (isla `interinsular`); Lanzarote → `L`; Fuerteventura → `F`; Gran Canaria → `G`; ninguna → nada si el nivel es `H`, `A`, `I` o `T` (`interinsular`) y `G` si no (la federación nombra sin isla muchas de Gran Canaria).
8. **La fase legible**: con nivel, «<Nivel> <isla corta>» («Preferente GC», «Interinsular»); sin nivel, la isla larga («Gran Canaria», «Lanzarote»); más la fase y el tipo («Lanzarote Fase 1», «Copa Cabildo Preferente Lanzarote», «Final Liga Primera Lanzarote», «Copa de Campeones»): las mismas formas que ya usan benjamín y alevín donde existen.
9. **Una eliminatoria dentro de una liga** («Eliminatoria de Primeros…» en el desplegable de una liga): el prefijo de la liga más `EL`, fase «Eliminatorias <fase de la liga>», numerados tras los que ya tenga la temporada (como `EL`, `PEL` y `ALEL`).
10. **Por qué no chocan**: todo prefijo empieza por `INF`, `CAD`, `JUV` o `AL` más al menos un carácter (dos en alevín), acaba en letra y tiene 17 caracteres como mucho; el número va detrás, así que dos prefijos distintos nunca dan el mismo código. Los de alevín de las islas siempre llevan nivel e isla tras `AL` (`ALUL`, `ALPL`, `AL1L`…): nunca son `AL` + una letra (la Segunda Fase), `ALP`, `ALCC…`, `ALCL` ni `ALEL`. Ninguno empieza por `LZ`, `FV`, `CLZ`, `CFV`, `PLZ`, `PFV`, `PCC`, `BC`, `MCP` ni `MCB`, ni acaba en `KO`.

**2026-27** (del catálogo del 25/11/2026):

| Competición (id) | Prefijo | Fase | Isla | Tipo |
|---|---|---|---|---|
| LIGA PRIMERA INFANTIL DE GRAN CANARIA (54976916) | `INF1G` | Primera GC | grancanaria | liga |
| LIGA INFANTIL PREFERENTE DE GRAN CANARIA (54976908) | `INFPG` | Preferente GC | grancanaria | liga |
| LIGA INFANTIL GRAN CANARIA (55184138) | `INFUG` | Gran Canaria | grancanaria | liga |
| LIGA INFANTIL LANZAROTE FASE 1 (54976911) | `INFUL` | Lanzarote Fase 1 | lanzarote | liga |
| LIGA INFANTIL DE FUERTEVENTURA 1ª FASE (54976929) | `INFUF` | Fuerteventura Fase 1 | fuerteventura | liga |
| LIGA CADETE INTERINSULAR (54976894) | `CADI` | Interinsular | interinsular | liga |
| LIGA CADETE PREFERENTE GRAN CANARIA (54977183) | `CADPG` | Preferente GC | grancanaria | liga |
| LIGA CADETE INSULAR GRAN CANARIA 1ª FASE (54976896) | `CADNG` | Insular GC Fase 1 | grancanaria | liga |
| LIGA CADETE PREFERENTE LANZAROTE (54976904) | `CADPL` | Preferente Lanzarote | lanzarote | liga |
| COPA CADETE PREFERENTE DE LANZAROTE (54977178) | `CADPLC` | Copa Preferente Lanzarote | lanzarote | copa |
| ELIMINATORIAS COPA CADETE PREFERENTE DE LANZAROTE (54977202) | `CADPLCE` | Eliminatorias Copa Preferente Lanzarote | lanzarote | eliminatorias |
| LIGA CADETE INSULAR DE LANZAROTE (54977104) | `CADNL` | Insular Lanzarote | lanzarote | liga |
| COPA CADETE INSULAR DE LANZAROTE (54977072) | `CADNLC` | Copa Insular Lanzarote | lanzarote | copa |
| ELIMINATORIAS COPA CADETE INSULAR DE LANZAROTE (55133909) | `CADNLCE` | Eliminatorias Copa Insular Lanzarote | lanzarote | eliminatorias |
| LIGA CADETE INSULAR DE FUERTEVENTURA (54976906) | `CADNF` | Insular Fuerteventura | fuerteventura | liga |
| ELIMINATORIA DESEMPATE CADETE INSULAR (55133947) | — | sin convenio («tipo de competición sin convenio») | | |
| LIGA JUVENIL INTERINSULAR (54976878) | `JUVI` | Interinsular | interinsular | liga |
| LIGA PRIMERA JUVENIL GRAN CANARIA (54976886) | `JUV1G` | Primera GC | grancanaria | liga |
| LIGA SEGUNDA JUVENIL GRAN CANARIA (54976889) | `JUV2G` | Segunda GC | grancanaria | liga |
| LIGA JUVENIL PREFERENTE GRAN CANARIA (54976880) | `JUVPG` | Preferente GC | grancanaria | liga |
| LIGA JUVENIL PREFERENTE LANZAROTE (54976882) | `JUVPL` | Preferente Lanzarote | lanzarote | liga |
| LIGA JUVENIL PREFERENTE FUERTEVENTURA (54976884) | `JUVPF` | Preferente Fuerteventura | fuerteventura | liga |
| LIGA ALEVIN LANZAROTE FASE 1 (54976933) | `ALUL` | Lanzarote Fase 1 | lanzarote | liga |
| LIGA ALEVIN FUERTEVENTURA F7 1ª FASE (54976977) | `ALUF` | Fuerteventura Fase 1 | fuerteventura | liga |

La tabla entera, de 2019-20 a 2026-27 (139 nombres; 138 con convenio), está en el plan («La tabla resultante») y, tal cual, en la fixture `scripts/tests/fixtures/convenio_mayores.json`, que comprueba `test_convenio.py` junto con que ninguna temporada de 2016-17 a 2026-27 tenga dos prefijos iguales (`test_el_catalogo_entero_sin_choques`). Para el alevín de Gran Canaria, benjamín y prebenjamín, `fiflp_manifest.comp_meta` e `import_fiflp_grupos.meta_by_name` dan lo mismo que antes (fixture `convenio_anterior.json`).

## Las protecciones

Los clubes son los mismos en todas las categorías, y la base comparte `teams.name` y `players`: lo que podría mezclarlas, y su prueba.

- **Un acta, una clasificación, unos goleadores o una liga de la app de una categoría nueva nunca caen en un grupo de otra** (`category_of` en cada importador): `test_alevin_aislamiento.py`, con cinco casos (alevín, infantil, cadete, juvenil y, con `ALEVIN_ISLAS`, el alevín de Lanzarote frente al benjamín de Lanzarote), `test_nombres_alevin.py` (un club de juvenil y el de benjamín).
- **La base de después no pone el bot en rojo**: la puerta de pruebas del bot corre sobre la base que acaba de escribir, así que ninguna prueba «sobre la base real» puede contar categorías, grupos o islas sin filtrar por `EN_WEB`. `python3 scripts/prueba_mayores.py` fabrica sobre una copia la base de después (13 grupos de las tres categorías, con `CADI1` interinsular; con `--islas`, también el alevín de Lanzarote, `ALUL1-2`) por el camino del bot y pasa allí las dos suites enteras. Va antes de cada paso del director.
- **Las fichas y los enlaces no se mueven** con apariciones de fuera de la web: `test_resolver_no_mira_categorias_fuera_de_la_web`, `test_edades_nuevas_separan`, `test_lo_de_fuera_de_la_web_no_mueve_los_enlaces`.
- **El bot de siempre no cambia de ritmo ni de reparto**: sin `FIFLP_CATS` lee prebenjamín, benjamín y alevín en el mismo orden que antes (`test_bot_rotacion.test_plan_principal_igual_que_antes`, 200 órdenes del código de antes); las pasadas del carril no le gastan números ni le mueven el reloj (`test_reloj_pasadas.test_semana_con_carril`, `test_carril_no_comparte_numero_ni_reloj`).
- **La activación**: lo de una categoría no activable no se carga; una competición sin convenio no rompe las demás (`test_activacion_categorias.py`, `test_competiciones_nuevas.py`).
- **Lo que cuestan en la puerta de pruebas** (que corre en cada pasada del bot, y del carril): las pruebas de esta parte sobre la base real comparten sus bases (`conftest.bases_reales`: la base real tras una pasada, con las mayores leídas y con el alevín de Lanzarote leído, una vez por sesión, las dos últimas a la vez) y generan la web dos veces a la vez (`paralelo.en_paralelo`, en procesos aparte). Medido el 25/11 en el PC: las tres más pesadas (`test_generador_igual_con_y_sin_mayores`, `test_quitar_categoria`, `test_quitar_el_alevin_de_lanzarote`), ~111 s; en serie y cada una con lo suyo, ~197 s. La suite entera, de ~9 min en `main` a ~11-12 min.
- **En la pasada del carril, las pruebas no ven `FIFLP_CATS`**: `update.yml` la pone en el `env` del job, y `conftest._sin_carril_del_job` la quita (una prueba que no la mira daría lo del carril y pondría la puerta en rojo); las que la miran la ponen ellas.

## El carril de las categorías mayores (`carril-mayores.yml`)

**Qué es.** Una pasada del bot, `update.yml` entero, llamado (`workflow_call`) por `carril-mayores.yml` («Pasadas de infantil, cadete y juvenil») con `cats: infantil,cadete,juvenil`: lee solo los grupos de la federación de esas categorías (`FIFLP_CATS`, en el `env` del job de `update.yml`: la ven todos sus pasos) y hace lo demás de una pasada (la app de futbolaspalmas, lo del histórico ya promovido, las fichas, la web y las suites). Un workflow aparte, y no `update.yml` lanzado con una entrada, **por su número de pasada**: llamado así, `GITHUB_RUN_NUMBER` es el de `carril-mayores.yml` (el contexto `github` es el del llamante), así que no gasta números del bot, del que sale su rotación sin estado, y sus ejecuciones no están en la lista de `update.yml` que mira el reloj. Mismo grupo de concurrencia que el bot y la activación (`update-data`, que ahora va en el job de `update.yml`: con la misma concurrencia en el llamante y en el llamado, GitHub lo daría por bloqueo mutuo): nunca dos pasadas a la vez.

**Cuándo** (`reloj_pasadas.due_carril`, desde `reloj.yml`): solo con la variable del repositorio `CARRIL_MAYORES` a `1` (sin ella, o con otro valor, el reloj no lista nada de más ni lanza nada, y decide las pasadas del bot exactamente como antes), y si:

- no es una ventana de partidos ni falta menos de 1 h (`ANTES_DE_VENTANA`) para que empiece una: el viernes, desde las 17:00; el sábado y el domingo, desde las 9:00 (hora de Canarias). Sin la base de zonas horarias, nunca;
- no hay **ninguna ejecución sin acabar** (en cola, en marcha, esperando) de `update.yml`, `carril-mayores.yml`, `activar.yml` ni `historico.yml`: GitHub guarda una sola ejecución en espera por grupo de concurrencia (una más nueva cancela la que esperaba), el histórico puede tardar horas y, al promover, lanza el bot;
- la última pasada del bot empezó hace **entre 25 y 75 min** (`CARRIL_DESDE`, `CARRIL_HASTA`): ya acabó (~24 min), y la siguiente toca a los 110-120 min, así que el carril (~24 min) acaba antes;
- la última del carril empezó hace **4 h menos 10 min** o más (`CARRIL_CADA - SLACK`), o no hay ninguna;
- y no toca la del bot (si toca, gana ella).

Y la del bot, con el carril encendido: además de lo de siempre, espera si hay una ejecución del carril sin acabar (haría cola tras ella en `update-data`); las acabadas no cuentan para nada.

**Cuántas.** Solo cabe en el hueco tras una pasada del bot, y fuera de las ventanas el bot pasa cada 2 h: el carril puede ir cada 2 h o cada 4 h, no entre medias, y va cada 4 h. La semana del 30/11 al 6/12/2026 con el reloj sin perder ticks (`test_semana_con_carril`): de lunes a jueves 6 al día (00:07, 04:07, 08:07, 12:07, 16:07 y 20:07, una hora después de una pasada del bot), el viernes 5 (hasta las 16:07), el sábado y el domingo 3 (00:07, 04:07 y 08:07): **35 a la semana**, y las pasadas del bot a la misma hora que sin carril. Con ticks perdidos, alguna menos: el que no llega en su hueco espera al siguiente hueco.

**Los números.** ~45 grupos × ~4 páginas = ~180 páginas por vuelta completa, ~1,3 pasadas en Azure (~137 páginas cada una). Con la mitad de los runners en AWS (no leen nada: [freno-2026-11.md](freno-2026-11.md)), se esperan 17-18 pasadas útiles a la semana, ~2.400 páginas para ~1.500 que hacen falta (una vuelta al día más las ~230 actas nuevas de cada semana): margen de 1,6. De lunes a jueves, la probabilidad de un día con menos de 2 pasadas en Azure es del 11 %; el viernes, del 19 %; el sábado y el domingo (3 pasadas, ~1,1 vueltas) puede quedar algún grupo para el lunes. Lo que no se lee en un día conserva su comprobación (`source_health.carry`) y va primero en la pasada siguiente. Las actas ya jugadas (~2.300 a 25/11) no las espera el carril: tras activar cada categoría, se encargan al carril del histórico (D3, punto 4).

- **Con más de 60 grupos** entre las categorías activas, `CARRIL_CADA = timedelta(hours=2)` en `scripts/reloj_pasadas.py` (un commit de una línea, con las suites en verde): 12 pasadas de lunes a jueves, una tras cada pasada del bot. Con menos de 25, se puede subir a 6 h.

**Lo que no hace.** No busca competiciones nuevas ni lee el directorio de campos (sus extras, una vez cada 12 pasadas suyas, son solo `directorio`: las fichas de los equipos de sus grupos; `update_fiflp.EXTRAS`), y **no lanza la activación** (el paso «Lanzar la activación si hay algo nuevo» de `update.yml` solo corre sin `cats`: lo pendiente lo lanza la pasada siguiente del bot de siempre).

**Su veredicto, aparte.** En `data-health.json`, `carriles.mayores.runHealth` (con su `drySince`) y `carriles.mayores.run` (con `pass`, el número de `carril-mayores.yml`, `cloud`, `refusedRunner`, `seconds`…); el del bot de siempre sigue en `runHealth` y `run`, y una pasada del carril no lo toca (en AWS no pone en rojo ni alarga la racha seca del bot). La clave `carriles` no existe hasta la primera pasada del carril; sin grupos que leer (D2), `carriles.mayores.runHealth` es `{"ok": true}` y no hay `run`. El commit de datos de una pasada del carril se llama «Actualización automática (infantil,cadete,juvenil) <fecha>». El carril del histórico (`historico.freno_del_bot`) mira los dos: si cualquiera vio hoy el freno de verdad en Azure, no lee más ese día.

**Encenderlo, apagarlo, mirarlo:**

```bash
gh variable set CARRIL_MAYORES --body 1 -R malolocabreralolo-tech/futbol-base-v2                     # encendido (D2)
gh variable set CARRIL_MAYORES --body 0 -R malolocabreralolo-tech/futbol-base-v2                     # apagado (o: gh variable delete CARRIL_MAYORES -R malolocabreralolo-tech/futbol-base-v2)
gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml --limit 5         # sus últimas pasadas
gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow reloj.yml --limit 1 --json databaseId --jq '.[0].databaseId' | xargs -I{} gh run view {} -R malolocabreralolo-tech/futbol-base-v2 --log | grep "Carril de las categorías mayores"   # qué decidió el último tick
```

Una pasada a mano (`gh workflow run carril-mayores.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main`) hace lo mismo; mejor sin nada en marcha en `update-data` (si no, espera en fila y otra en cola la cancelaría).

## Los pasos del director

Ninguno lo da el código: cada uno es una orden o un commit de una línea, con su comprobación en verde antes del siguiente. El ritmo: **entre D3, D4 y D5, al menos un día entero de pasadas en verde del bot y del carril, y la base medida**.

**Antes de cada uno** (D2-D6):

```bash
gh run list -R malolocabreralolo-tech/futbol-base-v2 --status in_progress && gh run list -R malolocabreralolo-tech/futbol-base-v2 --status queued   # sin update.yml, carril-mayores.yml ni activar.yml (ni historico.yml si el paso le encarga algo)
git pull
ls -l futbolbase.db                                                          # por debajo de 70 MB (o la parte D en su fase 3)
python3 scripts/prueba_mayores.py --categorias <las ya activas y la nueva>    # en verde sobre el main de ese momento (--islas en D6)
```

### D1: publicar las tareas 1-10

1. Sin nada en marcha (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --status in_progress` y `--status queued`, vacías): la rama al día con `main` (`git fetch origin && git merge origin/main`, como en cada tarea, o rebasada como dice [rediseno-rebase.md](rediseno-rebase.md)); que la rama no toque la base (`git diff --stat origin/main...HEAD -- futbolbase.db base/` vacío); `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && python3 scripts/prueba_mayores.py`; y `git push origin categorias:main`.
2. Comprobación: la pasada siguiente del bot (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml --limit 1`) en verde, con los pasos de siempre (`gh run view <id> -R malolocabreralolo-tech/futbol-base-v2` : «Lanzar la activación si hay algo nuevo» corre, no sale como saltado); en su `data-health.json`, `run.groups` el de la de antes (107 el 25/11) y ninguna clave `carriles`; su commit (`git show --stat origin/main`) no cambia más `data-*.js` que una pasada normal; `gh variable list -R malolocabreralolo-tech/futbol-base-v2` sin `CARRIL_MAYORES`; `gh workflow list -R malolocabreralolo-tech/futbol-base-v2` con «Pasadas de infantil, cadete y juvenil» activo y sin ninguna ejecución; los ticks del reloj en verde (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow reloj.yml --limit 3`).
3. Vuelta atrás: `git revert` de los commits de la rama, con nada en marcha.

### D2: encender el carril

0. Antes, desde el PC: `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml --limit 20 --json number,event,status,conclusion,createdAt,startedAt` tiene que dar `[]` (y no un error): es lo que leerá el reloj en cada tick, y un error lo dejaría en rojo sin lanzar tampoco la pasada del bot.
1. `gh variable set CARRIL_MAYORES --body 1 -R malolocabreralolo-tech/futbol-base-v2`.
2. Comprobación: el tick siguiente del reloj, en verde y con la línea «Carril de las categorías mayores: …» en su registro; en las 4 h siguientes, fuera de una ventana, una ejecución de `carril-mayores.yml` (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml --limit 3`) en verde y sin ninguna página pedida a la federación (sin la línea «Federación (FIFLP): N grupos» en el registro: no hay grupos que leer); en `data-health.json`, `carriles.mayores.runHealth.ok` verdadero y `runHealth`/`run` del bot como estaban; las pasadas del bot de ese rato, a su hora de siempre (los `createdAt` de `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml` siguen cada ~2 h y sus números, seguidos). Y lo que solo se ve en GitHub (abajo, «Lo que solo se comprueba en GitHub»).
3. Vuelta atrás: `gh variable set CARRIL_MAYORES --body 0 -R malolocabreralolo-tech/futbol-base-v2` (o `gh variable delete CARRIL_MAYORES -R malolocabreralolo-tech/futbol-base-v2`).

### D3: infantil

1. Un commit de una línea en `main` (sin nada en marcha): `ACTIVABLES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL")` en `scripts/categorias.py`, con las suites en verde; `git push`.
2. Lo que pasa solo: en la primera pasada del bot con sus extras (como mucho un día), `newCompetitions` trae las 5 de infantil de 2026-27; `activar.yml` baja la tanda `22inf` (~14 grupos, ~450 páginas: 3-6 intentos de 20 min alternados con pasadas) y las activa; el carril hace la primera lectura completa de cada grupo (`fiflp_full_pending`).
3. Comprobación: `activation.activated` de `data-health.json` lista los códigos `INF…`; `python3 -c "import sqlite3; c=sqlite3.connect('futbolbase.db'); print(c.execute(\"select count(*) from groups g join categories c on c.id=g.category_id where c.name='INFANTIL'\").fetchone())"` da el número de grupos de `scripts/fiflp_islas_22inf_grupos.json`; las pasadas del bot siguen en verde y su `run.groups` no cambia; las del carril, en verde y con `carriles.mayores.run.groups` igual a ese número; la web, igual (`grep -l '"INF' data-*.js` no da nada en la pasada siguiente).
4. Las actas ya jugadas, con el carril del histórico (sin nada del histórico en marcha): `gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar -f temporadas=22 -f categorias=infantil -f trabajos=actas`; comprobación: `python3 scripts/historico.py estado` hasta «2026-27 · actas infantil: en la base», y el tamaño de la base tras esa promoción (lo previsto: ~+2-3 MB). Mientras el histórico lee, el carril no se lanza (no arranca con el histórico en marcha): ese día tiene menos pasadas.
5. Si hay más de 60 grupos entre las categorías activas, `CARRIL_CADA` a 2 h (arriba).
6. Vuelta atrás: revertir el commit de `ACTIVABLES` (no activa nada más); el carril sigue leyendo lo activado: para que no lo lea, la vuelta atrás de D2; para sacarlo de la base, con el bot parado (`gh workflow disable reloj.yml -R malolocabreralolo-tech/futbol-base-v2` y `gh workflow disable activar.yml -R malolocabreralolo-tech/futbol-base-v2`, y nada en marcha), `python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL` (ensayo) y con `--apply`, las suites en verde, el commit de la base y `gh workflow enable reloj.yml -R malolocabreralolo-tech/futbol-base-v2` y `gh workflow enable activar.yml -R malolocabreralolo-tech/futbol-base-v2` (abajo, «Quitar una categoría»).

### D4: cadete y D5: juvenil

Como D3, cada uno tras al menos un día entero de pasadas en verde del bot y del carril desde el anterior y con la base medida:

- **D4**: `ACTIVABLES = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE")`; tanda `22cad` (~17 grupos); la «ELIMINATORIA DESEMPATE CADETE INSULAR» queda en `activation.failed` («sin convenio de código»), a propósito; comprobación con `c.name='CADETE'`, `scripts/fiflp_islas_22cad_grupos.json` y `grep -l '"CAD' data-*.js` vacío; sus actas, `-f categorias=cadete`; marcha atrás, `--categoria CADETE`.
- **D5**: `… "CADETE", "JUVENIL")`; tanda `22juv` (~10 grupos); comprobación con `c.name='JUVENIL'`, `scripts/fiflp_islas_22juv_grupos.json` y `grep -l '"JUV' data-*.js` vacío; sus actas, `-f categorias=juvenil`; marcha atrás, `--categoria JUVENIL`.

Las interinsulares (`CADI`, `JUVI`) entran con isla `interinsular` y equipos de las tres islas.

### D6: el alevín de Lanzarote y Fuerteventura

Es el único paso de E1 que se ve en la web: sus grupos entran en «Alevín» (sus fases, «Lanzarote Fase 1» y «Fuerteventura Fase 1», ya las conoce la web) y los lee el bot de siempre (alevín es del carril principal), no el carril. Mejor sin ningún encargo de alevín del histórico a medias: desde este paso, un encargo de alevín incluye también las competiciones de las islas.

1. Antes, `python3 scripts/prueba_mayores.py --islas` en verde.
2. Un commit: `ALEVIN_ISLAS = True` en `scripts/categorias.py`, con las suites en verde; `git push`.
3. Comprobación: `activation.activated` con `ALUL…` y `ALUF…` (tanda `22al`); los leen las pasadas del bot de siempre (su `run.groups` sube en ~4); `data-alevin.js` los trae.
4. Vuelta atrás: revertir el commit y, con el bot parado como en D3, `python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria ALEVIN --isla lanzarote --apply` (y `--isla fuerteventura`), las suites, el commit de la base y los dos `enable`.

## Lo que solo se comprueba en GitHub

`test_workflows.py` comprueba la forma de los workflows (disparadores, permisos, a quién llama y con qué, la condición de cada paso que lanza) y ejecuta con un `gh` de mentira los guiones del reloj, pero no se pueden lanzar aquí. Lo que solo se ve al publicar (D1) y al encender (D2), y cómo mirarlo:

| Qué | Cuándo | Cómo |
|---|---|---|
| GitHub acepta `update.yml` con `workflow_call` y la concurrencia en el job (si no, ninguna pasada arranca) | D1 | `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml --limit 3`: la primera pasada tras el push, en verde |
| `inputs.cats` llega vacía con el disparo del reloj | D1 | en esa pasada, `gh run view <id> -R malolocabreralolo-tech/futbol-base-v2 --log \| grep -m3 FIFLP_CATS` (vacía) y «Lanzar la activación si hay algo nuevo» no saltado: `gh run view <id> -R malolocabreralolo-tech/futbol-base-v2 --json jobs --jq '.jobs[].steps[] \| select(.name \| startswith("Lanzar")) \| .conclusion'` |
| La concurrencia del job (`update-data`) sigue en fila con la de `activar.yml` (en su workflow) | D1, la primera activación | `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow activar.yml --limit 1` y la pasada que la lanzó: el job de la activación empieza al acabar la pasada (`gh run view <id> -R malolocabreralolo-tech/futbol-base-v2 --json jobs --jq '.jobs[] \| {startedAt, completedAt}'`) |
| GitHub acepta `carril-mayores.yml` | D1 | `gh workflow list -R malolocabreralolo-tech/futbol-base-v2` lo enseña activo, sin errores de fichero |
| `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml` sin ejecuciones da `[]` y no un error | antes de D2 | la orden del paso 0 de D2 |
| El reloj lee la variable | D2 | el registro del tick siguiente trae «Carril de las categorías mayores: …» (arriba, «mirarlo») |
| El `GITHUB_TOKEN` del reloj puede lanzar `carril-mayores.yml` | D2 | «Lanzar el carril» en verde y una ejecución nueva con evento `workflow_dispatch` en `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml` |
| Los permisos del llamante bastan al llamado (si no: «The nested job … is requesting 'actions: write'…») | D2 | la primera pasada del carril, en verde: `gh run view <id> -R malolocabreralolo-tech/futbol-base-v2` |
| `FIFLP_CATS` llega a todos los pasos | D2 | `gh run view <id> -R malolocabreralolo-tech/futbol-base-v2 --log \| grep FIFLP_CATS` (infantil,cadete,juvenil en cada paso) y `carriles.mayores.runHealth` en `data-health.json` |
| El carril no lanza la activación | D2 | en su ejecución, «Lanzar la activación si hay algo nuevo» como saltado (la orden de `--jq` de arriba: `skipped`) |
| Las ejecuciones del carril no salen en la lista de `update.yml` (si salieran, el reloj las contaría como pasadas del bot y lo retrasaría) | D2 | `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml --limit 10` sin ellas, y los números de `update.yml` seguidos |
| El número de pasada del carril es el suyo | D3 (la primera con grupos) | `carriles.mayores.run.pass` de `data-health.json` igual a `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow carril-mayores.yml --limit 1 --json number` |
| Nunca dos pasadas a la vez | D2-D3 | los `createdAt`/`updatedAt` de `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml` y `--workflow carril-mayores.yml` no se pisan |
| El asunto del commit del carril | D3 | `git log origin/main --format=%s \| grep -m3 "(infantil,cadete,juvenil)"` |

Si algo de eso falla: la vuelta atrás de D2 (la variable a 0) deja el reloj y el bot como antes; si falla lo de D1, `git revert`.

## Quitar una categoría (`scripts/quitar_categoria.py`)

La marcha atrás de D3-D6: saca de la base una categoría nueva de una temporada como si el bot nunca la hubiera activado ni leído.

```bash
python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL            # ensayo: cuenta tabla a tabla y lo deshace
python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria INFANTIL --apply    # la quita (todo o nada)
python3 scripts/quitar_categoria.py --temporada 2026-2027 --categoria ALEVIN --isla lanzarote --apply
```

Solo con el bot parado (`reloj.yml` y `activar.yml` desactivados y nada en marcha: una pasada podría estar escribiendo la base a la vez) y con `ACTIVABLES` (o `ALEVIN_ISLAS`) ya revertido: si no, la pasada siguiente volvería a apuntar sus competiciones en `newCompetitions` y la activación las cargaría otra vez. Después, las suites en verde y el commit de la base. Solo acepta infantil, cadete o juvenil (con `--isla`, solo esa isla) o alevín con `--isla lanzarote` o `fuerteventura`; benjamín, prebenjamín, el alevín de Gran Canaria o una categoría que no existe salen con error sin tocar nada.

**Qué quita**: los grupos de esa categoría (e isla) de la temporada y todo lo que cuelga de ellos y de sus partidos (toda tabla con `group_id` o `match_id`, y lo que cuelga de esas filas por clave ajena: actas, apariciones, sucesos, cuerpo técnico, goles, clasificaciones, goleadores, la lectura completa pendiente…); las fichas de temporada (`team_seasons`) de los equipos que esa temporada ya no salen en ningún grupo; los equipos que ya no salen en nada; las identidades (`players`) que solo salían en sus partidos (un niño que ya estaba en la base conserva su fila: solo pierde las apariciones de lo borrado); y la fila de `categories` si se queda sin grupos. Con la base de después, quitadas las tres, la base es la de la copia en la que nunca se activaron, tabla a tabla y fila a fila (`test_activacion_categorias.py`).

**Lo que deja sin quitar:**

- en la base: el detalle de los campos (`venue_details`) que solo usan sus equipos (lo baja el directorio, y es del campo, no de la categoría); la ficha de temporada (`team_seasons`) que el carril escribiera para un equipo que esa temporada también juega en otra categoría (se queda, con el nombre de la federación de la categoría quitada); y el contador de `sqlite_sequence`;
- en el repositorio: lo descargado y los originales (`scripts/fiflp_islas_22inf_raw.json` y `_grupos.json`, `scripts/actas_bot_2026-2027_infantil.jsonl`, `scripts/fiflp_actas_2026-2027_infantil_raw.json` con su índice y su estado si el histórico las trajo) y el manifiesto de la activación (`docs/temporadas/2026-2027-auto-*.json`);
- en `data-health.json`: `activation` (lo intentado); las entradas de sus grupos, hasta la pasada siguiente (cada pasada rehace `groups` con los de la base); y `carriles.mayores`, mientras dure la temporada (`source_health.begin` lo arrastra).

## La parte F: el histórico de las categorías nuevas

El carril del histórico ya acepta `infantil`, `cadete` y `juvenil` (cada una con su lote de actas: arriba, «El contrato»), y las temporadas pasadas importan sus grupos con los códigos del convenio (`import_fiflp_grupos.meta_by_name`) y su calendario de la federación. Una temporada de infantil, por ejemplo la 2025-26 (sin nada del histórico en marcha, y con la base medida antes y después: cada temporada de fútbol 11 son unas 7.000 actas, ~2,4 KB cada una):

```bash
gh workflow run historico.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f accion=encargar -f temporadas=21 -f categorias=infantil -f trabajos=goleadores,actas,detalle,escudos
python3 scripts/historico.py estado          # tras git pull, hasta «2025-26 · … infantil: en la base»
```

Lo que trae entra en la base pero no en la web hasta E2 (`EN_WEB`; `data-season-*.js` no cambia). Es la parte F: no se encarga antes de acabar D5.
