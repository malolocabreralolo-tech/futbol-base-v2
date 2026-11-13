# Fútbol Base v2: diseño

Fecha: 13/11/2026. Estado: pendiente de aprobación del dueño.

Documentos que acompañan a este: `docs/revision-2026-11-13.md` (los hallazgos de la revisión, con fichero y línea; es la lista de trabajo detallada).

## 1. Qué es y por qué

El portal de fútbol base (`malolocabreralolo-tech/futbol-base`, publicado en `https://malolocabreralolo-tech.github.io/futbol-base/`) funciona y a su dueño le va bien. La revisión del 13/11/2026 encontró fallos y riesgos que conviene arreglar, pero el dueño no quiere arriesgar la web que usa.

Se construye **otra versión, con otro enlace, al lado de la actual**: una copia completa del proyecto con todas las mejoras de la revisión salvo las de privacidad. La web actual (en adelante **v1**) se queda exactamente como está. La nueva (**v2**) la usa solo el dueño, para compararla con v1 y decidir más adelante con cuál se queda.

Además, el dueño quiere **toda la información y la base de datos guardadas en su PC**, a salvo de que algo se corrompa o se pierda.

## 2. Lo que decidió el dueño (no se reabre)

1. **v1 no se toca**: ni su código, ni su bot, ni sus datos, ni su repositorio remoto, ni sus workflows, ni su reloj del PC. Tampoco se le añaden las fases que le faltan.
2. **v2 va en otro enlace.**
3. **No se toca nada de los datos de menores ni de la información.** v2 conserva todo el detalle de v1: nombre y apellidos de cada niño, equipos, alineaciones, actas, goleadores, cuerpo técnico, árbitros y la descarga de la base. No se oculta, abrevia, anonimiza ni recorta nada, y no se añaden avisos de privacidad ni bloqueos de buscadores. Máximo detalle posible.
4. **Es importante saber quién es cada niño**: su historial tiene que ser el suyo.
5. **Pronósticos con marcador exacto**: se mantiene el marcador exacto, el de mayor probabilidad. No se quita.
6. **Sin avisos por Telegram** ni por ningún otro canal externo.
7. **Una base de datos interna en el PC** con toda la información posible, guardada de forma que una corrupción o una pérdida no se la lleve.
8. **Construye Opus 5.5; revisa Claude (Fable)** antes de dar nada por bueno.
9. Todo lo demás de la revisión se hace, con los matices de este documento. «El informe» es el resumen de diez puntos que Claude dio al dueño en la conversación; la tabla de 2.1 dice a qué hallazgos de `docs/revision-2026-11-13.md` corresponde cada uno y cuáles entran.

### 2.1 Alcance: qué entra de la revisión

| Punto del informe | Hallazgos | En v2 |
|---|---|---|
| 1. La web se queda atrás y el aviso está roto | A1 | Entra (7.4, 7.5) |
| 2. La primera apertura enseña datos viejos | A2, B1, B2, B3 | Entra (7.7) |
| 3. Fichas de jugador mezcladas | A3 | Entra (7.6) |
| 4. Datos de menores | — | **No entra** (decisión del dueño) |
| 5. Scraping | C9 | Solo «v2 no pide más que v1». Sin cambiar cómo se identifica el bot |
| 6. Pronósticos | D2 | Entra solo el margen junto al pronóstico final. D1, D3 y D7 se quedan como están (decisión del dueño). D4, D5, D6, D8, D9 y D10 no entran: los modelos no se tocan |
| 7. Fallos silenciosos del bot | C1, C2 | Entra (7.5, 7.8) |
| 8. La base es la única copia | C3, C4, C13, C15 (integridad antes del commit) | Entra (7.3, 7.8) |
| 9. Sobra complejidad | B4, B6, B7, B12, C7, C10, C11, C12 | Entra (7.7, 7.8) |
| 10. Copia local | A6 | Entra (7.9) |

Arreglos menores que entran con la fase que les toca: B5, B10, B11, B13, B14 (web) y C5 (no reescribir puntos oficiales con sanción).

Entran solo si sobra tiempo al final de su fase, y sin ellos la fase se da por cerrada: B8, B9, partir `model.js`, C6, C8, C14 y el resto de C15.

No entra A4 (fechas de `matches.date` en tres formatos): es una migración de riesgo sobre la base que la web ya sortea. Queda anotada como deuda.

## 3. Objetivos

Cada uno lleva su comprobación. Sin la comprobación hecha y enseñada, no está terminado.

**O1. La copia en el PC existe y es de fiar.**
- Hay una copia diaria automática de la base de v1 y de la de v2, y un espejo completo de los dos repositorios (con los ficheros originales de cada scrape y todo el historial).
- Una copia dañada, vacía o claramente menguada nunca sustituye a la última buena: se aparta y la buena sigue siendo «la actual».
- Se guardan versiones para volver atrás.
- Comprobación: una prueba que intenta colar una base corrupta y una base con la mitad de las filas y ve que se rechazan; una restauración real de una versión antigua a una carpeta temporal cuyo contenido coincide con su huella.

**O2. v2 está publicada en su enlace y no puede estropear v1.**
- Comprobación: con v1 y v2 abiertas en el mismo navegador, instalar, actualizar y «borrar datos» en v2 no cambia ninguna caché ni ningún dato guardado de v1, y al revés. Prueba automática de que v2 no usa ningún nombre de caché ni clave de almacenamiento de v1.

**O3. v2 tiene la temporada completa y dice en portada cuando no la tiene.**
- Se cargan las fases y competiciones que la federación ya ha publicado y faltan.
- En adelante, una fase o competición nueva de las categorías seguidas se carga sola cuando encaja en los convenios conocidos; si no encaja, o si los datos llevan demasiado sin actualizarse, la portada lo dice.
- Comprobación: lista de lo publicado por la federación frente a lo cargado en v2, sin diferencias no explicadas; una prueba con una competición nueva simulada (se activa sola) y otra que no encaja (sale el aviso).

**O4. El bot de v2 no puede quedarse ciego en verde.**
- Si lee cero partidos de una jornada que la base tiene, si falla más de un tercio de los grupos o si la federación no sirve nada, la pasada queda en rojo y la web lo refleja.
- Comprobación: pruebas que simulan cada caso.

**O5. Cada niño tiene su historial y solo el suyo.**
- Un jugador sin identificador de la federación solo se une a otra ficha por su nombre cuando la unión es única y posible por edad, y esa unión queda marcada (7.6).
- Los historiales ya mezclados se separan volviendo a leer las actas guardadas.
- Todo jugador tiene ficha, también los que no tienen identificador.
- Comprobación: cero jugadores con historiales imposibles (prebenjamín años después de benjamín, más de seis temporadas, etc.) salvo los justificados uno a uno; toda unión por nombre está marcada; ningún jugador, alineación, gol ni partido se pierde en la migración (recuentos antes y después); v2 publica al menos tantas fichas como v1.

**O6. Al abrir v2 se ven los datos de ahora.**
- Tras una subida de datos, la primera apertura enseña los datos nuevos sin recargar a mano, o los enseña sola en pocos segundos.
- Una actualización con mala cobertura nunca deja la app sin poder abrirse sin conexión.
- Comprobación: pruebas de navegador de los dos casos (hoy `pwa-smoke` da por buena la apertura con datos viejos).

**O7. Pronósticos: se conserva todo y se añade el margen.**
- El marcador exacto sigue, con la regla de v1: el más probable dentro del desenlace del favorito (`src/pronostico.js`, `outcome` y `likelyScore`), para que nunca contradiga al favorito pintado a su lado. Donde v1 no pinta marcador en las listas (cuando los goles esperados no van con el favorito), v2 hace lo mismo.
- El pronóstico de la clasificación final enseña el margen junto a la cifra (por ejemplo «3.º · entre 2.º y 5.º»).
- Comprobación: prueba de que el marcador pintado es el más probable dentro del desenlace del favorito y de que v2 pinta los mismos marcadores que v1 con los mismos datos; capturas.

**O8. v2 pesa menos y es más simple, sin cambiar lo que se ve.**
- El aspecto y las pantallas de v2 son los de v1 salvo lo que este documento cambia a propósito.
- Comprobación: capturas emparejadas v1/v2 de las pantallas principales; cifras de peso y tiempo de arranque antes y después.

## 4. Lo que no se hace

- Cualquier cambio en v1 (ver 2.1).
- Cualquier reducción, ocultación o protección de datos personales (ver 2.3).
- Avisos externos (Telegram, correo, issues).
- Categorías o islas nuevas. «Máximo detalle» significa conservar y completar lo que ya se obtiene.
- Cambiar los modelos de pronóstico o sus umbrales (los decidió el dueño: desde 2 jornadas, calendario entero).
- Rediseñar el aspecto.
- Retirar v1 o parar su bot. Lo decidirá el dueño cuando haya comparado.

## 5. Lo que haría de esto un fracaso aunque «funcione»

- v2 rompe o altera v1 (comparten origen web: `malolocabreralolo-tech.github.io`).
- v2 enseña menos detalle que v1.
- La migración de identidades pierde o mezcla datos.
- El bot sigue pudiendo quedarse en verde sin leer nada.
- La copia del PC pisa una copia buena con una mala.
- Algo se da por hecho sin haberlo visto funcionar.

## 6. Restricciones

- **La federación (fiflp.com) no responde a IPs domésticas**: todo lo que la lea tiene que correr en GitHub Actions.
- **Dos bots**: mientras convivan v1 y v2, la federación recibe peticiones de los dos. El dueño lo sabe y lo acepta. v2 no debe pedir más que v1.
- **Nunca el correo del dueño** en cabeceras, User-Agent ni peticiones a servicios externos. Por eso no se pone un User-Agent «con contacto».
- **No empujar a un repositorio mientras corre un workflow suyo.**
- **Probar en pequeño antes de lo grande**: primero una pasada con pocos grupos, luego todo.
- **Todo cambio visual se verifica con captura** en navegador real, móvil y escritorio, claro y oscuro.
- **Nada de enlaces a localhost para el dueño**: capturas o el enlace publicado.
- **Ninguna operación destructiva sobre la base** sin una copia previa comprobada.
- El PC tiene **un solo disco, al 94 %** (110 GB libres). La copia del PC protege de corrupción y de perder GitHub, no de que muera el disco.
- Idioma del proyecto: español (código, comentarios, commits, documentos).

## 7. Cómo se hace

Lo marcado **(dueño)** está decidido. Lo marcado **(criterio de Claude)** es una decisión de Claude que el dueño puede cambiar. El resto queda al constructor.

### 7.1 Dónde vive v2

- **(criterio de Claude)** Repositorio público nuevo `malolocabreralolo-tech/futbol-base-v2`, con el historial completo de v1 hasta el día de la copia. Así v2 es además una segunda copia íntegra de v1. Carpeta local: `/home/manolo/claude/futbol-base-v2`.
- **(criterio de Claude)** Enlace: `https://malolocabreralolo-tech.github.io/futbol-base-v2/`, GitHub Pages, como v1.
- **(criterio de Claude)** La base sigue versionada en el repositorio (los cambios de cada pasada ocupan 15-45 KB empaquetados), con una alarma en las pruebas cuando pase de 80 MB (GitHub rechaza ficheros de más de 100 MB) y el camino para sacarla documentado.
- v2 se distingue a simple vista: marca «v2» junto al nombre, en el título, en el manifiesto de la app instalable y en su icono o nombre corto.

### 7.2 Aislamiento con v1 (mismo origen)

v1 y v2 comparten origen, y por tanto `localStorage` y Cache Storage. Hoy v1 borra al activarse toda caché `futbolbase-v*` y `futbolbase-escudos-*` que no sea la suya, y guarda en `futbol-base:v2`, `futbol-base:jugadores`, `futbol-base:codigo`, `season`, `cat` y `theme`.

- v2 usa prefijos propios para cachés y claves, que no empiecen por los de v1, y un `id` de manifiesto propio.
- v2 nunca escribe ni borra una clave o caché de v1.
- **(criterio de Claude)** La primera vez que se abre, v2 copia (solo lee) «mi equipo», los vistos y los jugadores seguidos de v1, para que el dueño no tenga que volver a elegirlos.

### 7.3 La copia en el PC

- **(criterio de Claude)** Carpeta `~/backups/futbol-base/` (ya existe `~/backups`), con permisos solo del usuario:
  - `actual/`: la última base buena de v1 y la de v2, sin comprimir, consultables.
  - `versiones/`: copias fechadas comprimidas con su huella. Se conserva una diaria durante 30 días, una semanal durante 6 meses y una mensual para siempre.
  - `volcados/`: un volcado semanal en texto (SQL) de cada base, que sobrevive a una corrupción del binario.
  - `repos/`: espejos completos de los dos repositorios, que se actualizan en cada copia.
  - `cuarentena/`: lo que no pasó las comprobaciones, con el motivo.
  - `estado.json` y un registro.
- Antes de aceptar una base: comprobación de integridad de SQLite, claves foráneas, y que ninguna tabla principal (partidos, jugadores, alineaciones, goles, clasificaciones) mengüe más de un margen pequeño respecto a la última buena. Si falla, a cuarentena y la actual no cambia.
- Temporizador de usuario de systemd, diario y con recuperación si el PC estaba apagado, como los demás del dueño. Sin cifrado **(criterio de Claude)**: es su PC y «segura» aquí significa que no se pierda.
- Una orden para ver el estado y otra para restaurar una versión.
- La copia no depende de que v2 exista: empieza con v1 y añade v2 cuando esté.
- Antes de limpiar nada en local (7.9), todas las ramas y copias de trabajo locales de v1 se guardan aquí en un paquete de git.

### 7.4 Datos completos (punto 1 de la revisión)

- A 13/11/2026 faltan: la continuación de benjamín de Gran Canaria (la Primera Fase acabó entre el 6 y el 10 de noviembre), la de alevín (acabó entre el 1 y el 3) y tres competiciones que el bot ya detectó: Copa Benjamín Gran Canaria (55331982), Liga Prebenjamín Lanzarote (54977161) y Liga Prebenjamín Fuerteventura (54977026). No se sabe si la federación ha publicado ya la Segunda Fase: hay que mirarlo desde Actions.
- El procedimiento actual está en `docs/temporada-nueva.md` (`discover-fiflp.yml`, `fetch-fiflp-islas.yml`, `fiflp_manifest.py`, `activate_season.py --add`).
- El bot hoy solo detecta competiciones nuevas, no grupos o fases nuevas dentro de una competición conocida: hay que cubrir también eso.
- De las tres pendientes, las dos ligas prebenjamín encajan en `scripts/fiflp_manifest.py`. La Copa Benjamín Gran Canaria no (`comp_meta` aborta con «competición sin convenio de código»): necesita convenio y fase nuevos.
- **(criterio de Claude)** Activación automática cuando el manifiesto reconoce la competición y pasan todas las verificaciones que ya hace `activate_season.py` y las pruebas; si algo no encaja, no se toca la base y la portada lo dice. El paso de avisos por issue (`avisar_competiciones.py`) se quita.
- Fases que el modelo de la web no reconozca (`PHASE_TABLE`, `PHASE_LEVEL`): se añaden con sus pruebas, como dice la guía.

### 7.5 Estado a la vista (sustituye a los avisos)

- **(criterio de Claude)** La portada de v2 enseña un aviso breve cuando: los datos llevan sin comprobarse más de un umbral (más corto en fin de semana), la última pasada falló, o hay competiciones o fases publicadas sin cargar. Toca y lleva a «Datos y fuentes», que ya da el detalle.
- Para eso el bot publica su diagnóstico también cuando fallan las pruebas o la lectura.

### 7.6 Quién es cada niño (punto 3)

- Causa: `scripts/import_fiflp_actas.py`, `_get_or_create_player`. Cuando el acta llega sin identificador de jugador, el jugador se casa solo por nombre normalizado con cualquier fila existente, también una de otro club y otros años. En la plantilla del equipo del dueño pasa con 4 de 12.
- Tamaño real (medido por el revisor del diseño): la liga prebenjamín de Gran Canaria viene sin identificador en el 100 % de las apariciones de 2024-25 y 2025-26 (11.219 y 11.100), y casi toda la de 2026-27. De los 1.057 jugadores de esas dos ligas, 822 están hoy pegados por nombre a una ficha con identificador de otra competición: unos 50 son imposibles por edad y el resto son plausibles (prebenjamín y después benjamín).
- **(criterio de Claude)** Regla, pensada para cumplir a la vez «saber quién es cada niño» y «máximo detalle»:
  1. Con identificador de la federación, manda el identificador.
  2. Sin él, un nombre completo con dos apellidos se une a otra ficha cuando la candidata es única y la edad cuadra (la categoría avanza con los años y no hay solape imposible). La unión queda marcada en la base como «unión por nombre», la ficha lo dice y se puede deshacer.
  3. Un nombre de pila suelto, o un nombre que tiene varias candidatas, no se une a otro club. Dentro del mismo club y en temporadas seguidas el constructor puede unirlo si lo justifica con datos, marcado igual.
  4. Lo imposible por edad no se une nunca. Ante la duda, dos fichas mejor que una mezclada.
- v1 solo publica ficha de quien tiene identificador (`scripts/generate_js.py`, `jugadores_files`: `WHERE p.fiflp_id IS NOT NULL`) y guarda los jugadores seguidos por ese identificador. **(criterio de Claude)** En v2 tiene ficha todo jugador, con clave propia para los que no tienen identificador, y se puede seguir a cualquiera. v2 nunca enseña menos fichas ni menos historial correcto que v1.
- Las actas de 2026-27 no están guardadas en bruto: el bot las analiza y escribe directo en la base (908 actas: 85 de prebenjamín, 427 de benjamín y 396 de alevín), y la base no registra si una aparición llegó con identificador. **(criterio de Claude)** El bot de v2 guarda desde el primer día el original de cada acta que lee, y vuelve a leer una vez las de 2026-27 para tenerlas: primero las 85 de prebenjamín, que hacen falta para separar con exactitud, y el resto poco a poco dentro del cupo normal de sus pasadas.
- Los historiales de temporadas anteriores se rehacen desde `scripts/fiflp_actas_*_raw.json`. Ojo: la revisión comprobó que reimportar hoy cambia ficheros publicados y que un importador falla por clave foránea (`docs/revision-2026-11-13.md`, C3). Hay que entender y controlar cada diferencia.
- La migración se hace sobre una copia, con recuentos antes y después, un informe de qué fichas se parten, cuáles se unen y por qué, y vuelta atrás.
- La ficha de un jugador sin identificador lo dice con naturalidad («en las actas figura solo con este nombre»).
- No se quita ni se abrevia ningún nombre.

### 7.7 La web

- **Datos frescos al abrir (punto 2)**: `sw.js` sirve hoy `index.html` y los `data-*.js` de caché y revalida detrás, y la página no se entera de la versión nueva. El constructor elige la estrategia; tiene que cumplir O6.
- **Instalación todo o nada** de lo imprescindible; lo opcional (temporadas archivadas, actas) puede fallar sin romper.
- **Pronósticos (dueño)**: el marcador exacto se queda. Se añade el margen al pronóstico final. **(criterio de Claude)** En la pantalla Partido, junto al «resultado más probable», su probabilidad real; si al dueño le estorba, se quita.
- **Peso**: un paso de empaquetado al publicar. Las fuentes siguen en módulos y las pruebas siguen importándolos. Con esto sobran los tres mecanismos de versión de hoy y la purga de `index.html`.
- **Arreglos menores** de la revisión: enlaces de partido que acaban en punto, `data-matchdetail.js` solo cuando hace falta, duración en el `.ics`, goleadores por páginas, letra en `rem` sin cambiar el tamaño por defecto, código muerto.
- **Barra inferior en iOS 26**: los dos commits de la rama local `barra-ios` de v1 (18/10/2026) se incorporan a v2. No se puede verificar aquí en un iPhone: lo prueba el dueño, y se le dice.

### 7.8 El bot y el mantenimiento

- Pasada sana definida y comprobada (O4).
- **Un solo escritor de la base**: se quitan los workflows heredados y de depuración que pueden escribirla fuera del grupo `update-data`.
- **La base se puede rehacer**: una prueba de «reconstruir desde los ficheros originales da lo publicado», o la lista explícita y justificada de lo que no se puede rehacer.
- Escritura atómica de los ficheros originales, versiones fijadas de Playwright y Chromium, comprobación de integridad antes de cada commit de la base.
- El reloj: v2 necesita el suyo. El cron de GitHub casi no llega (10 de 112 en un día), por eso v1 tiene un temporizador en el PC (`futbol-base-reloj`, cada 5 min). v2 tendrá uno propio, aparte; el de v1 no se toca. **(criterio de Claude)** El reloj de v2 lee el mismo token de GitHub que ya usa el de v1 (`~/.config/futbol-base-reloj/token`, de `gh`, válido para todos los repositorios del dueño) desde donde está: no se copia, no se imprime y no se modifica. Si el dueño prefiere un token aparte, lo crea él y se cambia una línea.
- **(criterio de Claude)** Cadencia de v2 no superior a la de v1.
- **Simplificar el planificador** (unas 1.650 líneas para repartir lecturas alrededor de un corte que hoy no se ve): estado persistido de la última lectura por grupo y «el más antiguo primero», con preferencia para los grupos del dueño. Es el cambio de más riesgo: va el último y solo entra si las simulaciones que ya existen (`test_bot_*`) dan una frescura igual o mejor.
- Scripts sin uso y de un solo uso: a `_archive` o fuera, sin romper lo que el bot importa de ellos (los lectores viven hoy en `fetch_fiflp_2425.py`, `import_fiflp_cups_2324.py` y `activate_season.py`).
- Comentarios: se queda el porqué en una frase; la historia («decisión 155 de B3») va a git y a un `docs/decisiones.md` corto.

### 7.9 Limpieza local (punto 10)

Solo en la copia local de v1 (`/home/manolo/claude/futbol-base`), nunca en su remoto:
- Guardar antes todas las ramas en un paquete dentro de la copia del PC.
- Poner `main` al día con el remoto.
- Quitar las 10 copias de trabajo abandonadas (todas sin cambios pendientes) y las ramas ya fusionadas. Las ramas con trabajo sin fusionar se conservan.
- Compactar git (hay 1,2 GB de objetos sueltos).
- Recortar la ficha de memoria del proyecto (hoy 80.000 tokens, ilegible de una vez), guardando la antigua en la copia.

## 8. Orden

Cada fase acaba con algo que funciona y se ha visto funcionar. No se empieza una sin cerrar la anterior.

0. **Copia en el PC y limpieza local.** No publica nada. Es lo que más le importa al dueño y no depende del resto.
1. **v2 en su enlace**, como copia fiel de v1 con el aislamiento, su reloj y su bot. Primera pasada con pocos grupos.
2. **Datos**: fases y competiciones que faltan, detección y activación, pasada sana, estado en portada, identidad de jugadores.
3. **Web**: datos frescos, instalación robusta, margen del pronóstico, empaquetado, arreglos menores, barra de iOS.
4. **Mantenimiento**: un solo escritor, reconstrucción, dependencias fijadas, scripts y comentarios, y al final el planificador.

## 9. Cómo se trabaja

- Cada fase tiene su plan escrito (`docs/superpowers/plans/`) antes de tocar código.
- Construyen subagentes con Opus 5.5, con pruebas primero, en ramas de v2.
- Claude revisa cada entrega antes de fusionar: lee el diff, ejecuta las pruebas, mira la web en navegador real con capturas y, para el bot, una pasada real en Actions. Lo que no pase vuelve al constructor.
- Al dueño se le enseña el resultado de cada fase con capturas y cifras, y lo que no se pudo verificar se le dice.

## 10. Riesgos conocidos

- La federación puede no haber publicado aún la Segunda Fase: entonces O3 se cumple con la detección y la portada, y la carga llega cuando se publique.
- La federación puede endurecer su corte con dos bots leyendo.
- El arreglo de iOS no se puede probar aquí.
- La migración de identidades cambia muchas fichas: se hace sobre copia, con recuentos y con vuelta atrás.
- GitHub desactiva los workflows programados de un repositorio público tras 60 días sin commits.
