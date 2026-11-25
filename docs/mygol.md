# La liga de escuelas (MyGol)

La liga de escuelas de Gran Canaria (miniprebenjamín, prebenjamín, benjamín y, desde 2025-26, alevín) no
pasa por la federación: la organiza ACADEE en la plataforma MyGol (`tusligascanarias.mygol.es`), que tiene
una API pública. De ahí se bajan, desde 2022-23 (antes no hay liga de escuelas en MyGol), los torneos, los
equipos, los partidos y qué niños estaban convocados en cada partido y si jugaron. Entra en tablas propias
de la base (`mygol_*`). Cuando un niño de escuela se puede enlazar con seguridad con su ficha de la
federación, la ficha dice en qué equipos de escuela estuvo y cuándo, y esas temporadas afinan su año de
nacimiento ([más abajo](#el-enlace-con-las-fichas)).

## Qué hay y qué no

- **Sí:** torneos, equipos (con su nombre), partidos (jornada, fecha, estado, campo) y, de cada partido, la
  plantilla de los dos equipos (nombre y apellidos de cada niño) y si cada niño jugó esa jornada
  (`dayResultSummary.gamesPlayed` de MyGol).
- **No:** marcadores ni goles (las escuelas no los publican: todos los partidos salen 0-0), ni fecha de
  nacimiento (MyGol la da en blanco, `0001-01-01`).
- **El id del jugador es de cada temporada.** MyGol crea las fichas de nuevo cada año: el mismo niño tiene
  otro id (y otro `idUser`) la temporada siguiente, y en la base, una fila de `mygol_jugadores` por
  temporada. Entre temporadas solo se le puede seguir por nombre y apellidos (`norm`); dentro de una, el id
  sí es el mismo en todos sus partidos. Cuidado al cruzar: en algunos equipos MyGol solo guarda el primer
  apellido.

## La tabla de torneos

MyGol oculta los torneos de temporadas pasadas: la API sigue dando sus partidos, pero no su nombre ni su
categoría. Lo dice una tabla revisada a mano, `scripts/mygol_torneos.json`
(`{"<id>": {"temporada", "categoria", "nombre"}}`). **Un torneo que no está en ella no se baja.**

| Temporada | Torneos (equipos) | Categoría |
|---|---|---|
| 2022-23 | 32 (19), 33 (33), 34 (14) | miniprebenjamín, prebenjamín, benjamín |
| 2023-24 | 51 (13), 52 (28), 53 (20) | benjamín, prebenjamín, miniprebenjamín |
| 2024-25 | 66 (16), 67 (34), 68 (12) | miniprebenjamín, prebenjamín, benjamín |
| 2025-26 | 85 (18), 86 (17), 87 (33), 88 (9) | miniprebenjamín, benjamín, prebenjamín, alevín |
| 2026-27 | 95 (26), 96 (16), 97 (20), 101 (10) | prebenjamín, benjamín, miniprebenjamín, alevín |

Cómo se decidieron (el 25/11/2026, con unas 20 peticiones a la API): 2025-26 y 2026-27, por el nombre que tenían cuando eran visibles; 2024-25, por niños que aparecen al año
siguiente en un torneo de categoría conocida (11 del mismo club en el prebenjamín de 2025-26) y por el
tamaño (el prebenjamín es siempre el mayor). Las de 2022-23 y 2023-24, también el 25/11/2026, con las
plantillas enteras: cada niño cruzado por nombre y dos apellidos con los de las otras temporadas de MyGol
y con las fichas de la federación, y para cada torneo, la categoría cuya ventana de edad encaja con casi
todos (152 de 158, 74 de 76, 178 de 181, 278 de 282 pares). El 34 apenas tiene pares: es benjamín porque
sus niños se comportan en la federación como benjamines de segundo año la temporada siguiente.

La categoría de la tabla manda sobre la que copió el original al bajarlo, y la pasada siguiente del bot
la importa (la tabla entra en la huella): para corregir una basta con cambiar la tabla. La columna admite
`null` (sin decidir), y entonces esas temporadas no cuentan para el año de nacimiento.

### Una temporada nueva

Cada temporada MyGol crea torneos nuevos (los de escuela: sin marcadores). Para verlos:

    python3 scripts/fetch_mygol.py --descubrir --hasta 130

recorre los ids de torneo de 1 a 130 y lista los que tienen partidos (equipos, partidos, cuántos tienen
marcador y fechas), con el nombre y la temporada de MyGol de los visibles. No escribe nada. Los de escuela
(«… ESCUELA 2027/2028», 0 con marcador) se añaden a `scripts/mygol_torneos.json` con su temporada
(`2027-2028`) y su categoría; desde entonces son la temporada en curso (`--en-curso` baja la más reciente
de la tabla).

## Los originales

`scripts/fetch_mygol.py` escribe uno por temporada, `scripts/mygol_<S>_raw.json`: por torneo, sus equipos y
sus partidos, y de cada partido leído, sus plantillas (`[id, nombre, apellidos, 1 si jugó]`) y el día en que
se leyó. Un partido aún sin leer va sin plantillas. Un partido leído de hace más de 21 días ya no se vuelve
a pedir (los recientes y los futuros, sí, porque cambian); uno a más de 14 días vista todavía no se pide.
Así, una descarga cortada sigue por donde iba.

    python3 scripts/fetch_mygol.py --en-curso                 # la temporada en curso
    python3 scripts/fetch_mygol.py --temporadas 2022-2023     # las que se digan
    python3 scripts/fetch_mygol.py --todas --max-peticiones 500

Sale con 0 aunque queden partidos pendientes (lo dice); con 1 solo si no pudo leer nada.

**Cortesía con MyGol:** una petición cada 2 segundos como mínimo, de una en una; dos reintentos ante un
fallo de red o un error del servidor; para tras 5 fallos seguidos guardando lo ya bajado. Solo pide a
`https://tusligascanarias.mygol.es/api`, con las cabeceras de un navegador y nada que identifique a nadie.
La descarga entera (unos 5.400 partidos) son unas 3 horas.

## El workflow

`.github/workflows/mygol.yml` baja cada lunes (04:17 UTC) la temporada en curso, con 2.000 peticiones como
mucho, y sube solo los originales que cambian (`scripts/mygol_*_raw.json`), rebasando sobre `main`. No toca
la base. Va en el grupo `descargas-manuales` (no se pisa con las descargas de la federación ni para al
bot). A mano, con otras temporadas o más peticiones:

    gh workflow run mygol.yml -R malolocabreralolo-tech/futbol-base-v2 -f temporadas=2022-2023,2023-2024 -f max_peticiones=3000

(`temporadas` vacía = la temporada en curso.)

## En la base

La pasada del bot (`fetch_futbolaspalmas.py`, después de las temporadas pasadas) llama a
`import_mygol.importar_si_cambia`: si la huella de los originales y de la tabla de torneos ha cambiado
(`raw_imports`, clave `mygol`), rehace **enteras** las cinco tablas, en una transacción. Un fallo de MyGol
nunca para la pasada: se apunta (`! MyGol: …`) y sigue. `scripts/reconstruir.py` lo comprueba (dominio
`mygol`: [reconstruccion.md](reconstruccion.md)).

| Tabla | Qué es |
|---|---|
| `mygol_torneos(id, temporada, categoria, nombre)` | `categoria` NULL = sin decidir (hoy, ninguno) |
| `mygol_equipos(id, nombre)` | el nombre de la temporada más reciente, si cambia |
| `mygol_jugadores(id, nombre, apellidos, norm)` | una fila por niño **y temporada**; `norm` = «APELLIDOS, NOMBRE» sin tildes, en mayúsculas |
| `mygol_partidos(id, torneo_id, jornada, fecha, estado, local_id, visitante_id, campo)` | `estado` 5 = jugado, 1 = sin jugar |
| `mygol_participaciones(partido_id, jugador_id, equipo_id, jugo)` | convocado en ese partido con ese equipo; `jugo` 0/1 |

Por ejemplo, cuántos partidos jugó cada niño en cada torneo:

```sql
SELECT t.temporada, t.categoria, j.norm, e.nombre AS equipo, sum(p.jugo) AS jugados
FROM mygol_participaciones p
JOIN mygol_jugadores j ON j.id = p.jugador_id
JOIN mygol_partidos m ON m.id = p.partido_id
JOIN mygol_torneos t ON t.id = m.torneo_id
LEFT JOIN mygol_equipos e ON e.id = p.equipo_id
GROUP BY t.id, j.id, p.equipo_id
ORDER BY t.temporada, t.categoria, equipo, j.norm;
```

## El enlace con las fichas

MyGol no da ningún identificador que sirva en la federación ni la fecha de nacimiento: solo el nombre y los
apellidos. Así que el enlace es por el nombre, y muy prudente, porque es peor enseñar en la ficha de un niño
la escuela de otro que no enseñar ninguna. La regla, en `scripts/enlace_mygol.py` (`enlazar`): un niño de
MyGol (un id de una temporada) va a una ficha solo si

1. tiene nombre y **dos apellidos** («APELLIDO APELLIDO, NOMBRE», igual que en la federación, sin tildes);
2. esa temporada no hay en MyGol **otro niño con el mismo nombre en un club que no tenga nada que ver** (el
   club es `identidad.club` del nombre del equipo). Si lo hay, son dos niños y no se sabe cuál es cuál: no se
   enlaza ninguno de los dos. El mismo club dos veces (los equipos A y E de un club) es el mismo niño apuntado
   dos veces, y sí;
3. en la federación hay **una sola ficha** con ese nombre exacto (en su identidad principal o en una unida).
   Con dos, ninguna, aunque solo una tenga la edad;
4. **la edad cuadra**: alguno de los años de nacimiento de la ficha, estimado solo con la federación, cabe
   en la categoría de esa temporada de escuela, con un año de margen por el lado joven (en la escuela muchos
   juegan con los mayores);
5. y a la ficha no le llegan, de la misma temporada, dos niños de MyGol en clubes sin nada en común (por
   dos nombres distintos de sus identidades). Si pasa, ninguno de esa temporada.

Un id de MyGol que sale en dos torneos (dos categorías la misma temporada, o, rara vez, el mismo id en dos
temporadas) se enlaza solo si todos sus torneos llevan a la misma ficha.

Las fichas y sus años son los que ve la web (`categorias.EN_WEB`, como el generador): hasta que la web enseñe
infantil, cadete y juvenil (parte E2), una identidad que solo sale en ellas no cuenta como otra ficha del
mismo nombre (regla 3) y sus partidos no cuentan para el año (regla 4). Así, que el carril de las mayores lea
a un niño de cadete no quita ni cambia ningún enlace (`enlace_mygol.fichas_de`).

**Lo que no se enlaza, a propósito:** los niños de un solo apellido (MyGol solo guarda el primero en algunos
equipos): enlazarlos por el nombre y el primer apellido falla en torno a una de cada seis veces. Tampoco se
usa el club para enlazar más: los nombres de club de MyGol y de la federación no casan bien («Vet. del
Pilar» frente a «Veteranos»…), y exigir el mismo club solo añadiría 6 niños.

**Las cifras** (25/11/2026, con los cinco originales y la base de ese día): de 5.191 niños de MyGol (4.907
con nombre y dos apellidos), se enlazan **1.521 con 968 fichas**. Se quedan fuera 3.235 sin ninguna ficha
con su nombre (la mayoría no se ha federado), 58 por repetirse su nombre en dos clubes la misma temporada,
39 con dos o más fichas candidatas y 55 por la edad. Error estimado: por debajo del 1,3 % (los homónimos de
edad compatible que cabe esperar por azar). De las 968 fichas, 928 tienen la escuela antes de su primera
temporada federada; y 409 de las 485 que tenían dos años de nacimiento posibles pasan a uno.

**Dónde está:** la pasada del bot (`fetch_futbolaspalmas.enlazar_mygol`), después de resolver las fichas y
antes de publicar, rehace entera la tabla `mygol_enlaces(jugador_id, player_id)`: el id de MyGol y el de la
principal de su ficha. Es derivada (si el resolvedor cambia la principal, el enlace la sigue en la misma
pasada) y no se escribe si no cambia. Un fallo del enlace nunca para la pasada (`! MyGol (enlaces): …`): la
web sale como en la pasada anterior. El generador (`generate_js._escuela`) le pone a cada ficha enlazada
`"e"`: `[temporada, equipo, categoría, jornadas jugadas]` por temporada y equipo, y la ficha de la web lo
enseña en «Liga de escuelas», siempre como «enlazado por el nombre y los dos apellidos». Sin enlaces (o sin
las tablas), lo publicado es igual byte a byte que sin la liga de escuelas.

**Si un enlace está mal:** hoy no hay una lista para separarlo a mano. Lo que sí deshace un enlace es
cualquier cosa que rompa una de las cinco condiciones (por ejemplo, una ficha más con ese nombre).
