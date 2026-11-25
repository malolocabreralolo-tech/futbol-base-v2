# Ampliación: todas las categorías, trayectorias y ranking por año de nacimiento

Diseño acordado con el dueño el 25/11/2026. Es la continuación de
[2026-11-13-futbol-base-v2-design.md](2026-11-13-futbol-base-v2-design.md) y hereda sus normas (abajo,
«Normas que siguen en pie»).

## Para qué

El dueño quiere usar la web para **seguir a los niños que destacan**: coger a uno y ver todo lo que ha hecho
desde que empezó (en qué equipos ha estado, en qué categorías, cuánto ha jugado, los goles que ha marcado,
cómo ha ido evolucionando), de la liga de escuelas a juvenil. Y quiere ver, **por año de nacimiento**, quiénes
están siendo los mejores («del 2020, quiénes son los mejores; del 2019…»).

Hoy la web solo tiene prebenjamín y benjamín (con alineaciones desde 2019-20) y el alevín de Gran Canaria de
2026-27. Un niño que hoy es juvenil no aparece: su etapa de alevín, infantil y cadete no está en la base.

## Lo que se va a tener al acabar

1. **Categorías**: prebenjamín, benjamín, alevín, infantil, cadete y juvenil, de fútbol (nunca fútbol sala), de
   Gran Canaria, Lanzarote y Fuerteventura, con el mismo detalle que hoy tiene benjamín: grupos,
   clasificaciones, calendario, actas (alineaciones, goles, cuerpo técnico), goleadores.
2. **Histórico**: todas las temporadas en las que la federación tiene actas (desde 2019-20) y, de antes, lo
   que tenga (resultados y clasificaciones desde 2016-17).
3. **Ficha de cada niño con su trayectoria entera**, de una categoría a otra.
4. **Buscador de jugadores** por nombre.
5. **Año de nacimiento estimado** de cada niño, y un **ranking de los mejores de cada año**.
6. **Liga de escuelas de MyGol** (2022-23 en adelante), enlazada con la ficha de cada niño.
7. Todo ello en la base y en la copia del PC del dueño.

## Lo que no entra

- Fútbol sala, categorías de mayores (regional, veteranos), ligas femeninas de mayores.
- Las ligas que no publica la federación de Las Palmas (Liga Nacional juvenil, selecciones). La División de
  Honor juvenil y el cadete autonómico están en su catálogo unas temporadas sí y otras no: entran las que
  estén.
- La fecha de nacimiento real: nadie la publica (abajo). Se estima el año.
- Avisos fuera de la web. La versión 1.

## Lo que haría de esto un fracaso

- Que el bot de hoy deje de publicar o que los equipos del dueño se actualicen más tarde que ahora.
- Mezclar a dos niños en una misma ficha. Ante la duda, dos fichas (norma de `docs/identidad.md`).
- Enseñar como dato algo que es una estimación (el año de nacimiento, un enlace con MyGol hecho por el
  nombre): lo estimado va siempre marcado como tal.
- Cargar a la federación más de la cuenta: sigue en pie no saltarse su cupo (`docs/federacion.md`, «El freno
  de la federación»).

## Normas que siguen en pie

- La versión 1 no se toca. Todo va a la versión 2 (`futbol-base-v2`).
- Los datos de los niños se publican con el máximo detalle (nombre, apellidos, equipos). No se recortan ni
  se anonimizan. En documentos, pruebas, commits e informes versionados no se escriben nombres reales de
  niños (iniciales o identificadores).
- La federación solo se consulta desde GitHub Actions. Nunca el correo del dueño en cabeceras.
- No se empuja a `main` con un workflow en marcha. La base es binaria: un conflicto obliga a repetir.
- Los pronósticos siguen con marcador exacto. Sin avisos externos.
- Quien construye es Opus 5.5 (subagentes); quien revisa y decide es el director de la sesión.

## Lo medido antes de diseñar (25/11/2026)

- **Base de hoy**: 41 MB, 19.301 identidades de jugador (17.109 con el identificador de la federación, que
  sigue al niño de un equipo a otro y de una temporada a otra), 437.942 apariciones, 18.800 actas. Las
  alineaciones empiezan en 2019-20: los originales de actas de 2016-17 a 2018-19 están vacíos.
- **Catálogo de la federación** (`scripts/fiflp_comps_catalog.json`): por temporada, unas 12 competiciones de
  juvenil, 16 de cadete, 10 de infantil y 10 de alevín (ligas, fases de ascenso, copas, finales).
- **Lo que ya existe en la web**: ficha del jugador con su trayectoria por temporada (equipo, grupo,
  partidos, titularidades, goles, tarjetas) y «Seguir a este jugador» (hasta 12, en la portada). No hay
  buscador de jugadores, ni año de nacimiento, ni ranking, y los goleadores no enlazan a la ficha.
- **Lo que un acta dice de cada niño**: dorsal, titular o suplente (convocado: no se sabe si llegó a jugar),
  goles, y nada más. No hay minutos, cambios ni posición; el portero no se distingue.
- **Histórico de alevín de Gran Canaria**: el canal ya está preparado (`docs/alevin.md`) y nunca se lanzó.
- **Tamaño**: cada acta ocupa unos 1,7 KB en la base. Con el alevín histórico (unas 13.600 actas) la base
  rondará los 65 MB; con infantil, cadete y juvenil (unas 70.000 actas de fútbol 11) pasará de 200 MB.
  GitHub no admite ficheros de más de 100 MB y Pages no publica más de 1 GB (hoy el árbol publicado ocupa
  324 MB, con los originales y la base dentro).
- **Freno de la federación**: en Azure no hay cupo desde el 21/10. Lo de noviembre son los runners en AWS (la
  federación no les sirve nada desde el 13/11) y actas vacías siempre que el bot tomaba por el freno (desde el
  21/11). Ninguna tanda trata aún ni lo uno ni lo otro: [docs/freno-2026-11.md](../../freno-2026-11.md).
- **El Archivo de Internet** no tiene las páginas de la federación (ni las de MyGol).
- **MyGol** (`https://tusligascanarias.mygol.es/api`): la liga de escuelas está de 2022-23 a hoy, unos
  5.400 partidos; cada partido trae los niños de los dos equipos (identificador estable, nombre, apellidos)
  y si jugaron esa jornada. No hay marcadores ni goles, y la fecha de nacimiento viene en blanco. Los
  torneos de temporadas pasadas están ocultos pero la API los sigue sirviendo. El Archivo de Internet no
  guardó nada útil de esa web.

## Las partes, y su orden

Cada parte tiene su propio plan y se publica cuando está terminada y revisada. El orden busca que el dueño
vea resultados pronto mientras las descargas largas avanzan solas.

| | Parte | Depende de | Qué se ve al acabar |
|---|---|---|---|
| B | Fichas: año de nacimiento estimado, trayectoria ampliada, buscador de jugadores, ranking por año, goleadores enlazados a la ficha (sobre los datos que ya hay) | — | Lo principal que pidió el dueño, con los niños que ya están en la base |
| C | Liga de escuelas de MyGol: descarga, tablas y enlace con las fichas | B (año estimado) para el enlace | «Venía de la escuela X» en la ficha |
| G | Descargas que respetan el freno: los descargadores por tandas leen con las mismas esperas que el bot, nunca dan por buena una página vacía, y bajan primero lo barato (clasificación y goleadores de cada grupo) y después las actas | — | Nada visible; sin esto no se puede bajar histórico |
| A | Histórico de alevín de Gran Canaria (ya preparado: una temporada para medir y luego el resto) | G | Alevín en «Temporadas anteriores»; las fichas ganan años |
| D | Almacenamiento a escala: base partida por temporadas, publicación solo de la web, base completa descargable | — (antes de E y F) | Nada visible; evita que el bot se pare por tamaño |
| E | Infantil, cadete y juvenil de la temporada en curso (y alevín de Lanzarote y Fuerteventura): datos y web | D, G | Las tres categorías nuevas en Explorar |
| F | Histórico de infantil, cadete y juvenil, temporada a temporada, de la más reciente a la más antigua | D, E, G | Trayectorias completas hasta juvenil |

B y C empiezan ya, en paralelo (no dependen de la federación ni tocan los mismos ficheros). G empieza con
un estudio de por qué volvió el freno el 14/11. Lo que depende de la federación (A, E, F) irá al ritmo que
ella deje: no se le pone fecha.

## Decisiones

### 1. Año de nacimiento

Nadie lo publica, así que se **estima** con lo que el niño ha jugado. Quien juega la temporada que empieza
el año `Y` nació, si va en su categoría, en: prebenjamín `Y-7` o `Y-6`; benjamín `Y-9` o `Y-8`; alevín `Y-11`
o `Y-10`; infantil `Y-13` o `Y-12`; cadete `Y-15` o `Y-14`; juvenil `Y-18`, `Y-17` o `Y-16`. Puede ser más
pequeño (jugar en la categoría de arriba es frecuente) pero nunca mayor.

- Cada temporada con apariciones es una observación. El estimador puntúa cada año candidato: mucho si cae
  en la ventana natural de la categoría, poco si implicaría jugar con los mayores, cero si sería demasiado
  mayor para esa categoría; pesa cada temporada por los partidos jugados. Gana el año con más puntos.
- El resultado es **un año** («2018») cuando gana con claridad, o **dos** («2018 o 2019») cuando no. Con
  una sola temporada vista casi siempre serán dos.
- La liga de escuelas (parte C) cuenta como observación: su miniprebenjamín es una ventana más joven que
  ninguna de la federación y afina a los más pequeños.
- **Años confirmados**: un fichero versionado (`scripts/anios_confirmados.json`: clave de ficha → año y
  fuente) manda sobre la estimación. Sirve para los niños de los que se sepa el año por una fuente pública.
  Empieza vacío.
- En la web el año estimado lleva siempre la palabra «estimado» o la forma «2018 o 2019»; el confirmado, no.
- El estimador es una función pura (sin base ni red), con sus pruebas, en Python. La web no lo recalcula:
  lee el resultado.
- Los intervalos del resolvedor de identidad (`identidad._EDAD`) se amplían a las categorías nuevas con el
  mismo criterio que hoy (ventana natural y dos años más por abajo).

### 2. Ranking de los mejores de cada año

Solo sale de las actas (2019-20 en adelante), que es donde cada gol y cada partido están atados a una ficha.

- Una lista por año de nacimiento. Un niño con dos años posibles sale en los dos, marcado como dudoso.
- El orden lo da un **índice** que se explica en la propia pantalla y cuyas piezas se enseñan en columnas:
  partidos, titularidades, goles, goles por partido, nivel de la liga en la que juega y si juega con
  mayores. La fórmula premia marcar mucho, hacerlo en una liga de nivel alto y hacerlo siendo de los pequeños
  de la categoría o jugando en la de arriba, y corrige a quien ha jugado muy pocos partidos para que tres
  goles en un partido no lo pongan primero.
- Dos vistas: **esta temporada** y **toda la trayectoria**.
- Es un ranking de lo medible: favorece a quien marca. Defensas y porteros casi no se pueden valorar con lo
  que dan las actas; la pantalla lo dice.
- La fórmula exacta y sus pesos los fija el plan de la parte B y quedan en `docs/ranking.md`. El dueño la
  verá funcionando y podrá pedir cambios.

### 3. Ficha, buscador y seguidos

- La ficha gana: año de nacimiento, un resumen por categoría (temporadas, equipos, partidos, goles), la
  evolución temporada a temporada (goles y goles por partido) y, cuando exista, la etapa de escuela.
- **Buscador de jugadores**: en Explorar, el mismo cuadro busca equipos y jugadores. Los datos van en un
  índice aparte, troceado, que se carga al buscar (no en la portada).
- Los goleadores y los récords enlazan a la ficha cuando el goleador se puede atar a una sin duda.
- Las claves de las fichas no cambian: los enlaces y los seguidos de hoy siguen valiendo.
- Los trozos de `data-jugadores-*` se dimensionan para seis veces más fichas.

### 4. Categorías nuevas

- La categoría de una competición la decide un solo sitio (`scripts/categorias.py`), que pasa a conocer
  `INFANTIL`, `CADETE` y `JUVENIL` y el alevín de Lanzarote y Fuerteventura. Fútbol sala, nunca.
- **Códigos de grupo**: únicos en la temporada. Los de las categorías nuevas llevan un prefijo de tres
  letras (`INF`, `CAD`, `JUV`) para no chocar con los de hoy (una letra y un número es la Segunda Fase de
  benjamín; `AL…` es alevín), seguido del nivel y la isla y del número de grupo. La tabla de convenios sale
  del catálogo real de 2019-20 a 2026-27 y queda documentada; una competición sin convenio no se inventa:
  se queda sin cargar y la web lo dice (como hoy).
- Copas, fases de ascenso, finales y eliminatorias entran como copas (sin clasificación de liga), con las
  reglas que ya existen.
- Las protecciones contra mezclar categorías (un acta solo casa con partidos de su categoría, etc.) se
  extienden a las nuevas con sus pruebas.
- En la web, las categorías nuevas se cargan de forma perezosa, como alevín, y aparecen en Explorar, Tabla,
  Jornada, Equipo, Goleadores, Temporadas anteriores y Récords.

### 5. El bot y las descargas

- El bot de hoy (prebenjamín, benjamín y alevín) no cambia de ritmo ni de reparto.
- Infantil, cadete y juvenil de la temporada en curso van en un **carril aparte**: pocas pasadas al día,
  fuera de las ventanas de partidos de los pequeños. Importa tener sus resultados y sus actas, no tenerlos
  al minuto.
- El histórico se baja con las tandas que ya existen (`actas-federacion.yml` y compañía), **una vez
  adaptadas al freno** (parte G): una cadena cada vez, con las esperas del bot, sin guardar nunca una página
  vacía como leída, y parando sola cuando la federación no sirve. No se intenta saltar el freno (ni varias
  IPs a la vez, ni proxies).
- **Primero lo barato**: la clasificación y los goleadores de cada grupo son una o dos páginas y dan, de
  cada goleador, equipo, partidos jugados y goles de esa temporada. Con eso las trayectorias de los que
  marcan se pueden enseñar pronto (enlazadas por el nombre, y marcadas así). Las actas, que dan a todos
  los niños con su identificador, llegan después y sustituyen a lo anterior.
- De la temporada más reciente a la más antigua, y dentro de cada una, de la liga de más nivel a la de menos.
- Cada temporada se importa antes sobre una copia de la base, con todas las pruebas, y solo entonces en la
  de verdad: un dato nuevo que rompa una prueba dejaría al bot sin publicar nada.
- Siempre «una pequeña primero»: una temporada, medir (tamaño de la base, tiempo de la pasada, pruebas) y
  después el resto.

### 6. Almacenamiento

- La base sigue siendo **una** para todo el código (`futbolbase.db`, el mismo esquema). Lo que cambia es
  cómo se guarda en git: una pieza común y una pieza por temporada con las tablas de las actas
  (alineaciones, sucesos y cuerpo técnico), todas muy por debajo de 100 MB. Un paso la **monta** al empezar
  cada workflow y otro la **parte** al acabar, cambiando solo lo que ha cambiado; antes de subir, se
  comprueba que lo partido, vuelto a montar, es igual que la base con la que se ha trabajado.
- GitHub Pages pasa a publicar **solo la web** (una rama derivada con los ficheros de la web), no los
  originales ni la base.
- La **base completa** se sigue pudiendo descargar desde la web (un fichero único que se renueva cada día)
  y la copia diaria del PC la sigue guardando.
- La generación de lo que no cambia (las actas de temporadas cerradas) no se repite en cada pasada.

### 7. Liga de escuelas (MyGol)

- Se baja de la API de MyGol, despacio (una petición cada dos segundos), los torneos de escuela de 2022-23 a
  hoy; después, una vez por semana, la temporada en curso. Los originales se guardan en el repositorio.
- La categoría de cada torneo (miniprebenjamín, prebenjamín, benjamín, alevín) va en una tabla revisada a
  mano, porque la API no la da en los torneos ocultos.
- En la base, tablas propias (`mygol_…`): torneos, equipos, jugadores, partidos y participaciones.
- **Enlace con las fichas**: por nombre y apellidos completos y normalizados, siempre que la edad sea
  compatible. Si hay un solo candidato, se enlaza y la ficha lo enseña como «Liga de escuelas» con su equipo
  y temporada, marcado «por el nombre»; si hay varios o ninguno, no se enlaza. Nunca une dos fichas de la
  federación entre sí.
- Los niños que solo están en la liga de escuelas no tienen ficha propia por ahora.

## Lo que queda a quien construye

Los nombres de funciones, la forma exacta de los ficheros de datos, los pesos del índice del ranking y la
tabla de códigos de grupo los fija el plan de cada parte. Lo que no puede cambiar sin volver a preguntar es
lo de «Lo que haría de esto un fracaso» y «Normas que siguen en pie».
