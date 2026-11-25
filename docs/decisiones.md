# Decisiones vigentes

Lo que el código hace a propósito y no se ve a simple vista. Cada línea dice qué y por qué, con el fichero
al que afecta. Solo lo que sigue siendo verdad: la historia de cómo se llegó a cada cosa está en git y en
`docs/superpowers/`. Si una decisión cambia, se cambia aquí en el mismo commit.

## La web

- **La ruta es la fuente de verdad.** Lo que se ve sale del hash (`#/<pantalla>?<parámetros>`); ningún módulo guarda estado de interfaz. `src/router.js`, `src/links.js`, `src/state.js`.
- **Un enlace a una ficha lleva siempre su temporada.** Un enlace compartido no cambia de partido ni de equipo al activar la temporada siguiente. `src/links.js` (`matchHref`, `teamHref`).
- **Los enlaces antiguos de v1 (`#section=…`) se traducen, nunca cambian mi equipo.** Un `miequipo` abre Mi equipo solo si es el guardado; si no, la ficha de ese equipo. `src/links.js` (`translateLegacy`).
- **Un parámetro con un valor que no existe se quita sin aviso**, como una vista de Tabla que no existe: un enlace escrito a mano no rompe la pantalla. `src/router.js` (`CLOSED`).
- **«Hoy» es el día de Canarias, nunca el del dispositivo**: un móvil con hora peninsular ya está en mañana entre las 23 y las 24. `src/links.js` (`canaryTodayISO`).
- **Días, meses y cifras van escritos a mano**, sin los datos de idioma del navegador: lo que se ve no depende del navegador ni del Node de las pruebas. `src/links.js`, `src/ui.js` (`decimal`).
- **La temporada del portal llega por el contexto**, nunca leyendo `src/config.js` desde los módulos puros: se prueban sin navegador y con cualquier temporada. `src/model.js`, `src/pronostico.js`, `src/router.js`.
- **El alevín nunca va en la carga inicial**: la portada de un equipo de benjamín o prebenjamín tiene que abrir en 3 s. Se pide al entrar en lo que lo necesita. `src/state.js`, `src/router.js` (`needsAlevin`).
- **Un cambio de fase de mi equipo se guarda solo; uno de temporada, nunca** hasta que la familia lo confirma: con la temporada nueva publicada por partes, un candidato único del primer día no puede tapar la pregunta cuando llegan los demás. `src/myteam.js` (`myTeamToSave`), `src/app.js`.
- **Una fase siguiente a medio publicar no mueve mi equipo**: se espera; a los 7 días sin el club en ella, aviso `stale`. `src/myteam.js` (`laterPhase`, `STALE_AFTER_DAYS`).
- **El mismo nombre en dos grupos de la misma fase son dos equipos** (los B1 y B2 de un club): nunca se unen ni se resaltan juntos. `src/myteam.js`, `src/model.js` (`searchTeams`).
- **Quién pasó una eliminatoria es lo que dice la fuente**: el marcador o la columna de penaltis. Un empate sin ella sale «según el cuadro», nunca con unos penaltis inventados. `src/model.js`, `src/screen-copa.js`.
- **Retirado tiene una sola definición** (`retiredTeams`), y el generador usa la misma regla. `src/model.js`, `scripts/generate_js.py` (`retired_outside_table`).
- **La clasificación de la web va por puntos, diferencia y goles**, también en prebenjamín, donde la federación ordena por puntos por partido; lo pidió el dueño. `scripts/generate_js.py` (`points_order`).
- **Pronóstico solo de prebenjamín de la temporada en curso y solo con sus partidos jugados**; las temporadas pasadas sirven para probar el modelo, no como entrada. El 1X2 de las notas de Massey y el marcador del Poisson, dentro del favorito. `src/pronostico.js`, `scripts/pronostico_banco.mjs`.
- **El pronóstico se enseña desde 2 jornadas jugadas**: es una decisión, no una prueba (con dos, la ventaja sobre la tabla aún no es demostrable). `src/pronostico.js` (`PARAMS.minRounds`).
- **Un pronóstico nunca parece un resultado**: debajo del partido, en letra pequeña y apagada, empezando por «Pronóstico». `src/ui.js` (`forecastLine`).
- **El pronóstico de la clasificación final es una cifra en «La temporada en cifras»**; su tabla vive solo en la Tabla (`v=pronostico`), fuera del selector de vistas. `src/proyeccion.js`, `src/team-view.js`, `src/screen-tabla.js`.
- **Gráficos sin líneas discontinuas ni degradados**, con colores sólidos distintos: preferencia del dueño. `src/ui.js` (`oddsBar`), `acta.css`.
- **El tema sigue al sistema**: no hay selector. `src/screen-ajustes.js`, `acta.css`.
- **Goleadores se pinta por páginas** (200, o 30 con una búsqueda): benjamín pasa de 2.000 jugadores y pintarlos de una vez congela el móvil. `src/screen-goleadores.js`.
- **Todo HTML sale de `html```, que escapa cada dato.** `src/html.js`.
- **«Borrar datos» no quita la marca de que ya se leyó v1**, para que lo de v1 no vuelva. `src/store.js`.
- **El año de nacimiento se estima y nunca se enseña como dato**: siempre con «(estimado)», «2016 o 2017» o «entre … y …»; sin la marca, solo el confirmado a mano (`scripts/anios_confirmados.json`). `scripts/nacimiento.py`, `src/model.js` (`birthText`), `docs/ranking.md`.
- **El ranking de los mejores de cada año sale solo de las actas**: es donde cada gol y cada partido están atados a una ficha; los goleadores de la federación no tienen id y unos 4.700 goles van sin nombre. Favorece a quien marca, y la web lo explica en «Cómo se calcula». `scripts/ranking.py`, `src/screen-ranking.js`, `docs/ranking.md`.
- **El buscador de jugadores no depende de la temporada elegida**: los equipos se buscan en la temporada de Explorar y los jugadores en todas (el índice `data-buscar-<xy>.js` es de todas). `src/screen-explorar.js`, `src/model.js` (`searchPlayers`).
- **Un año que no está en el ranking se enseña vacío** («Todavía no hay ningún jugador de 2008 con partidos suficientes.»), no el más reciente: la ficha enlaza a cada año posible del niño sin cargar el ranking, y abrir otro año confundiría. Sin `y` en la dirección, sí el más reciente con alguien en la vista. **El buscador dice siempre «(estimado)»**: el índice de búsqueda trae los años pero no si están confirmados. `src/screen-ranking.js` (`chosenYear`), `src/screen-explorar.js`.

## El service worker y la puesta al día

- **Tres cachés, todas `futbolbase2-…`**: el origen lo comparten v1 y otros proyectos, y el SW solo borra lo suyo. `sw.js`.
- **El precache va por huella de contenido** (`./<ruta>?h=<huella>`) y se instala todo o nada: una instalación nunca mezcla dos versiones de un fichero, y la siguiente solo baja lo que cambió. `sw.js`, `scripts/precache.py`.
- **El código va en `dist/` con su huella en el nombre**; `src/config.js` queda fuera porque lo reescribe la activación de una temporada sin que cambie el código. `scripts/codigo.py`, `scripts/empaquetar/empaquetar.mjs`.
- **`?v=` de `index.html` y `CACHE_NAME` de `sw.js` llevan la misma versión y solo suben si cambia algún `data-*.js`**: una pasada sin cambios no hace commit. `scripts/generate_js.py` (`bump_if_changed`).
- **El SW se registra tras `load` y pide `update()` en cada apertura; nunca `unregister`**, que reinstalaría todo. `index.html`.
- **Si el arranque falla, un aviso con «Reintentar»**, nunca «Cargando…» para siempre. `index.html`.
- **La página y la salud van a la red con poca espera (2,5 s) y si no, la copia**; un dato de otra versión espera más (8 s), porque sin él la página nueva se pintaría con el dato viejo. `sw.js`.
- **La copia de `data-health.json` vale poco (30 s)** frente a la de la red (10 min): la web tiene que enterarse pronto de que volvió la conexión. Con una copia caducada, la pantalla no espera a la red: se pinta con la copia y la respuesta queda para la navegación siguiente. `src/state.js` (`healthNeeds`).
- **La página se pone al día sola** si nadie la ha tocado desde que se abrió o volvió a primer plano; si no, «Hay datos nuevos.» con «Actualizar». `src/actualizacion.js`.

## El bot y la federación

- **Todo lo que lee la federación corre en GitHub Actions**: contesta vacío a las IPs domésticas. `scripts/update_fiflp.py`, `docs/federacion.md`.
- **La federación sirve unas 15 páginas por IP y luego frena** (unos 5 min, y escala dentro de la pasada). Cada pasada espera un solo freno y acaba en el segundo; no se intenta saltar el cupo (ni IPs, ni proxies, ni runners en paralelo). `scripts/fiflp_carga.py`, `scripts/update_fiflp.py`.
- **Lo que se repite va a la red**: la federación da sus páginas con `max-age=300`, y un sondeo del freno no puede ser la página vacía guardada. `scripts/fiflp_render.py` (`goto`).
- **Sin `page.route`**: desactiva la caché HTTP y multiplica por diez las peticiones por página; lo ajeno se corta en el lanzamiento de Chromium. `scripts/fiflp_render.py` (`fiflp_launch_args`).
- **Un 4xx de la federación también es un rechazo**: si no, un 403 a todo daría una pasada en verde sin leer nada. `scripts/fiflp_carga.py` (`_refused`), `scripts/pasada_sana.py`.
- **Las pasadas las lanza un reloj (`reloj.yml`), no el cron**: GitHub pierde o retrasa los cron. Una cada 2 h; cada hora en las ventanas de partidos (viernes tarde, sábado y domingo). `scripts/reloj_pasadas.py`.
- **El orden de cada pasada sale de su número**, no de nada guardado: una pasada sin cambios publicados no sube nada, y la siguiente repetiría los mismos grupos. `scripts/update_fiflp.py` (`plan_groups`).
- **El reparto de lecturas por turnos se queda**: una regla más simple («el más antiguo primero», con estado guardado) se midió en las simulaciones y empeoraba lo de los equipos del dueño (y más). `docs/planificador-medidas.md`.
- **Los prioritarios solo cuando toca** (cada 6 h, o en cada pasada mientras tienen un partido recién jugado sin resultado o sin acta, 12 h como mucho). `scripts/update_fiflp.py`.
- **Alevín va intercalado con benjamín y prebenjamín**, con una cuota mínima: delante se llevaría todo el cupo. `scripts/update_fiflp.py` (`ALEVIN_MIN_GROUPS`).
- **Cada grupo se lee completo (calendario, goleadores y actas) antes del siguiente**, para que el freno no deje calendarios sin sus actas. `scripts/update_fiflp.py` (`run_passes`).
- **Una pasada seca de vez en cuando es normal** (un runner con una IP ya frenada); solo una racha larga es un fallo. `scripts/pasada_sana.py`.
- **El directorio de campos cortado a medias no vacía la tabla**: solo añade lo leído. `scripts/update_fiflp.py` (`update_campos`).
- **El histórico va por un solo carril (`historico.yml`) con la lectura del bot**: una ejecución cada vez, fuera de las ventanas de partidos, 2.000 páginas al día para empezar (la rampa, a mano) y nada más el día que aparece el freno de verdad; no se relanza por caer en un runner de AWS (decisión pendiente del dueño: `RELANZAR_SI_RUNNER_RECHAZADO`). `scripts/historico.py`, `docs/federacion.md`.
- **Lo bajado del histórico pasa por la cuarentena** (`scripts/historico/`, que el bot no mira) y por una prueba sobre una copia (importar sin red, la base sana y las dos suites) antes de que el bot lo importe: una temporada que rompe algo no deja al bot sin publicar. `scripts/cuarentena.py`, `scripts/prueba_historico.py`.
- **`historico.yml` sustituye a las tandas de goleadores y de detalle**; `actas-federacion.yml` queda solo para `reindex` y `refrescar`, que el carril no hace, hasta que el dueño decida. `.github/workflows/historico.yml`.
- **Del directorio de equipos no se lee el contacto de los clubes**: son datos personales y la base va a un repositorio público. `scripts/fiflp_detalle.py`, `docs/federacion.md`.

## La base y los originales

- **Nunca se borra un partido**: si la federación lo mueve de jornada, se avisa. Un marcador nuevo entra siempre; uno que ya estaba solo cambia si cuadra mejor con la clasificación oficial, y uno comprobado con el acta no lo cambia una lectura de la jornada. `scripts/update_fiflp.py`.
- **Un equipo que la federación renombra a mitad de temporada se junta en el nombre de la clasificación, solo en ese grupo**: la lectura de una jornada ya jugada no encuentra el partido y lo entra otra vez con el mismo enlace al acta (el partido sale dos veces y el acta pasa de uno a otro en cada lectura). Se reconoce por dos partidos jugados con el mismo enlace, jornada y marcador que difieren en un equipo; si los dos nombres juegan entre sí, o los dos o ninguno están en la clasificación, no se juntan y se avisa. `scripts/update_fiflp.py` (`merge_renamed_teams`).
- **La clave de club conserva la letra de filial** («UD Atalaya» y «UD Atalaya B» son dos equipos), y es la misma en Python y en la web. `scripts/generate_js.py` (`normalize_for_teams_mapping`), `src/state.js` (`normalizeForTeamsMapping`).
- **Cada niño es una ficha con una o varias identidades de acta**; lo imposible por edad no se une nunca. `scripts/identidad.py`, `scripts/migrate_identidad.py`, `docs/identidad.md`.
- **Un niño de la liga de escuelas (MyGol) solo se enlaza con su ficha sin ninguna duda**: nombre y dos apellidos idénticos, una sola ficha con ese nombre, la edad compatible y ningún homónimo en otro club esa temporada. Por el primer apellido fallaría una de cada seis veces; es peor la escuela de otro niño que ninguna. El enlace no une fichas. `scripts/enlace_mygol.py`, `docs/mygol.md`.
- **La escuela se enseña siempre como enlazada por el nombre**, en su propio bloque de la ficha, y cuenta para el año de nacimiento pero no para el ranking (no tiene goles). `src/screen-jugador.js`, `scripts/generate_js.py` (`_escuela`).
- **El bot guarda el original de cada acta que importa** (`scripts/actas_bot_<temporada>_<categoría>.jsonl`), para rehacer lo que sale de las actas sin volver a pedirlas. `scripts/actas_bot.py`.
- **`futbolbase.db` va en git en su esquema compacto**: GitHub no admite ficheros de 100 MB. Desde 80 MB la web lo dice; desde 95, no se sube. `scripts/migrate_compactar.py`, `scripts/base_sana.py`.
- **Una base que no pasa la comprobación no se sube**, ni los datos de esa pasada: sin ella no hay pruebas ni commit. `scripts/base_sana.py`, `.github/workflows/update.yml`.
- **Los ficheros se escriben enteros o no se escriben**: un corte a mitad deja el anterior. `scripts/escritura.py`.

## Publicar

- **Solo los workflows del grupo `update-data` suben datos (`data-*.js`) o base (`futbolbase.db`)**, uno detrás de otro, sin cancelar el que corre. `.github/workflows/update.yml`, `activar.yml`. Otros cuatro suben solo originales a `scripts/` (`historico.yml`, `actas-federacion.yml`, `discover-fiflp.yml`, `fetch-fiflp-islas.yml`).
- **`dist/` solo se empaqueta en el PC, al publicar**; ni el bot ni la activación lo hacen, y `--check` no necesita node. `scripts/codigo.py`, `scripts/publicar.py`.
- **El código de las fichas en 64 trozos y los datos se publican juntos**: al publicar se regeneran `dist/` y los datos (`generate_js.py`) en el mismo commit. La web de 64 trozos no puede salir con datos de 16 (abriría el trozo que no es), ni al revés. `scripts/publicar.py`, `scripts/generate_js.py` (`JUGADORES_SHARDS`), `src/state.js`.
- **Una publicación sube la versión sin mover la fecha «Última actualización»**, que es la de los datos. `scripts/publicar.py`, `scripts/generate_js.py` (`bump_cache_version`).
- **Al rebasar una rama sobre `main` solo cuentan tres marcas** (las `?v=`, «Última actualización» y `CACHE_NAME`), que el bot sube siempre a la vez, y el bloque del precache de `sw.js`, que el bot también reescribe y se rehace con `python3 scripts/precache.py`. `scripts/sync_versions.py`.

## Límites conocidos y aceptados

- **Durante un despliegue, un dato inmediato puede llegar con la `?v=` nueva y el contenido anterior.** La caché en memoria de Chrome puede servir uno de los siete `data-*.js` de `<script defer>` con la URL nueva y lo que tenía de antes; se corrige en la siguiente apertura. `index.html`.
- **El día en que se activa una temporada nueva, la primera apertura puede usar el `src/config.js` anterior.** La sirve el SW que ya está al mando, desde su precache, hasta que se instala el nuevo. `sw.js` (precache).
- **Los datos que se piden al entrar en una pantalla se guardan sin verificar su huella**, a diferencia de los del precache. `sw.js` (`servirDato`).
- **El tope de 15 s de las peticiones del SW cubre hasta que llegan las cabeceras**, no un cuerpo que se queda colgado a medias. `sw.js` (`fetchConTope`).

## Lo que no se puede rehacer

Qué partes de la base salen otra vez de los originales y cuáles no (y por qué): [`docs/reconstruccion.md`](reconstruccion.md).
