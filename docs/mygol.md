# La liga de escuelas (MyGol)

La liga de escuelas de Gran Canaria (miniprebenjamín, prebenjamín, benjamín y, desde 2025-26, alevín) no
pasa por la federación: la organiza ACADEE en la plataforma MyGol (`tusligascanarias.mygol.es`), que tiene
una API pública. De ahí se bajan, desde 2022-23 (antes no hay liga de escuelas en MyGol), los torneos, los
equipos, los partidos y qué niños estaban convocados en cada partido y si jugaron. Entra en tablas propias
de la base (`mygol_*`); enlazar a estos niños con sus fichas de la federación y enseñarlo en la web es de
otra parte (C2), todavía no.

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
