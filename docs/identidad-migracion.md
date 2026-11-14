# La migración de la fase 2C, ensayada sobre una copia de la base

Generado por `python3 scripts/migrate_identidad.py --db <copia> --informe docs/identidad-migracion.md --muestras <fichero no versionado> --dos-veces` sobre una copia de `futbolbase.db` (la de la rama `fase2c`). Solo cifras: los nombres de los niños, en las muestras para revisar a ojo, van en un fichero aparte que no se versiona. Reglas: `docs/identidad.md`.

## Qué hace

1. Esquema: `players.ficha_id`, `union_por` y, para la identidad sin id, `team_id`, `season_id` y `ordinal`; `norm_name` sigue siendo único: `NOMBRE@<equipo>.<temporada>` (y `#<ordinal>` desde el segundo del mismo nombre en una alineación).
2. Separar: cada aparición, con sus sucesos de ese partido y equipo, a su identidad de acta según el original (los del bot, si hay; si no, los raws): sin id, a la de (nombre, equipo, temporada); con id, a la fila de ese id. Sin original: la liga prebenjamín de Gran Canaria desde 2024-25 (`PGC*`, `PG*`), sin id; lo demás, lo que diga la fila. No se borra ninguna fila.
3. Resolver: `identidad.resolver` sobre todas las identidades con aparición o suceso, y `ficha_id` (NULL en la principal) y `union_por` en cada fila.

Decisiones (lecturas que unen menos y no pierden nada):

- Casar una entrada del original con su aparición: el partido por `cod_acta`, el equipo por el lado; primero por el `fiflp_id` de la fila, después por el nombre normalizado y, entre homónimos, por el dorsal; si queda una de cada, son la misma.
- Una aparición sin dorsal que el original no trae es un goleador de otra lectura del acta (el importador solo deja sin dorsal a quien sale en los sucesos y no en la alineación): sin id.
- El ordinal sale del dorsal en el original; sin original, si dos apariciones de un equipo y partido fueran a la misma identidad sin id, también por el dorsal (no se pierde ninguna).
- La identidad sin id es de (nombre, equipo, temporada), sin la categoría: un mismo equipo de la base juega a veces dos categorías en una temporada; identidades sin id que caen en dos: 0.

## Recuentos por tabla

| Tabla | Antes | Después |
|---|---:|---:|
| `appearances` | 431.658 | 431.658 |
| `match_events` | 144.031 | 144.031 |
| `matches` | 38.052 | 38.052 |
| `goals` | 10.961 | 10.961 |
| `scorers` | 25.193 | 25.193 |
| `match_staff_all` | 71.439 | 71.439 |
| `players` | 17.670 | 19.650 |

Iguales salvo `players`, que solo crece (no se borra ninguna fila).

## Fichas

| | Antes | Después |
|---|---:|---:|
| Fichas (con alguna aparición) | 17669 | 15134 |
| Con algún id de la federación (v1 publicaba las filas con `fiflp_id`) | 17019 | 14239 |
| Sin ningún id | 650 | 895 |
| Imposibles por edad | 15 | 0 |
| Imposibles por solape (dos clubes a la vez) | 101 | 89 |
| Filas de `players` sin ninguna aparición | 1 | 651 |
| Filas sin aparición ni suceso | 0 | 650 |

Identidades con aparición o suceso: 19000; fichas que da el resolvedor: 15135.

Uniones (identidades que no son la principal de su ficha, por la regla que las unió):

- U0, mismo equipo y temporada (`equipo`): 3039
- U1, mismo club, temporadas seguidas (`club`): 615
- U2, candidata única (`nombre`): 211

## Separar

- apariciones separadas: 24531
- apariciones separadas de filas con id: 18660
- apariciones separadas de filas sin id: 5871
- filas de las que se separaron apariciones: 1558
- corregidas por identificador: 0
- corregidas desde una fila con otro id: 0
- corregidas desde una fila sin id: 0
- filas de las que se corrigieron apariciones: 0
- sucesos movidos: 7955
- identidades sin id creadas: 1980
- filas con id creadas: 0
- ordinales puestos por dorsal: 0
- apariciones sin original: 21622

Lo que no casó entre el original y la base (no se tocó, salvo lo que se dice):

- actas del original sin partido en la base: 56
- entradas de la alineación sin aparición en la base: 21
- entradas de los sucesos sin aparición en la base: 0
- sucesos de un nombre con homónimos en la alineación (sin tocar): 0
- apariciones sin dorsal que el original no trae (goleador: sin id): 12
- apariciones con dorsal que el original no trae (regla sin original): 0
- apariciones que no se movieron por un choque: 0

Una entrada del original sin aparición en la base, o una aparición que el original no trae, es de otra lectura del acta (la base se importó de una versión y el raw es de otra): no se crea ni se borra ninguna aparición. Las apariciones sin dorsal que el original no trae son goleadores que no estaban en la alineación (el importador solo deja sin dorsal a esos; ninguna entrada de alineación de los raws va sin dorsal) y van sin id, como todo goleador fuera de la alineación; las que tienen dorsal siguen la regla sin original (con `fiflp_id` en la fila, se quedan).

Originales leídos:

- actas: 17669
- actas de los raws: 17669
- actas del bot: 0

## Imposibles que quedan

- por solape, una sola identidad, con id: 89

Una sola identidad con id es lo que dice la federación: el mismo id en dos equipos de clubes distintos (para `identidad.club`) la misma temporada y categoría, con fechas que se cruzan: un cambio de club a mitad de temporada, un niño que juega en dos equipos o dos grafías de un mismo club que la clave de club no junta. No lo hace la migración (el resolvedor no une nada a una identidad así) y no se separa: el id manda.

<details><summary>Todas (ficha, tipo, identidades y tramos: temporada, categoría, equipo)</summary>

- ficha 244 (solape; 1 identidades): 2021-22 ben Puertos; 2021-22 ben Veteranos B; 2022-23 ben Veteranos
- ficha 541 (solape; 1 identidades): 2020-21 ben Acodetti B; 2021-22 ben Acodetti; 2021-22 ben Simusetti B
- ficha 551 (solape; 1 identidades): 2020-21 pre Atco. Huracán; 2021-22 ben San Juan; 2021-22 ben San Juan At.; 2022-23 ben San Juan
- ficha 833 (solape; 1 identidades): 2025-26 ben Juventud Marítima; 2025-26 ben O. Marítima B; 2025-26 ben O. Marítima C; 2025-26 pre O. Marítima; 2026-27 ben Juventud Marítima
- ficha 1825 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben Lomo B; 2023-24 ben O. Marítima B; 2024-25 ben CD Lomo
- ficha 1841 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B; 2024-25 ben Internacional PH; 2025-26 ben Juventud Marítima
- ficha 1843 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B; 2024-25 ben Internacional PH
- ficha 1844 (solape; 1 identidades): 2022-23 ben Internacional C; 2023-24 ben Internacional C; 2023-24 ben Internacional PH; 2024-25 ben Internacional PH
- ficha 1854 (solape; 1 identidades): 2023-24 ben Sporting C; 2023-24 ben Sporting Tías; 2024-25 ben Sporting Tías
- ficha 1858 (solape; 1 identidades): 2023-24 ben Sporting C; 2023-24 ben Sporting Tías; 2024-25 ben Sporting Tías
- ficha 1866 (solape; 1 identidades): 2024-25 ben Sporting C; 2024-25 ben Sporting Tías
- ficha 1888 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima
- ficha 1891 (solape; 1 identidades): 2022-23 ben Puerto del Carmen; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima
- ficha 1894 (solape; 1 identidades): 2024-25 ben Juventud Marítima; 2024-25 ben O. Marítima B
- ficha 1895 (solape; 1 identidades): 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima; 2024-25 ben O. Marítima B; 2025-26 ben Juventud Marítima
- ficha 1896 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima
- ficha 1897 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima
- ficha 1898 (solape; 1 identidades): 2023-24 ben CD Adassa; 2024-25 ben Juventud Marítima; 2024-25 ben O. Marítima B
- ficha 2002 (solape; 1 identidades): 2024-25 ben Sporting C; 2024-25 ben Sporting Tías; 2025-26 ben Sporting Tías
- ficha 2003 (solape; 1 identidades): 2024-25 ben Sporting C; 2024-25 ben Sporting Tías; 2025-26 ben Sporting Tías
- ficha 2075 (solape; 1 identidades): 2023-24 ben Internacional C; 2024-25 ben Internacional B; 2024-25 ben Internacional PH
- ficha 2085 (solape; 1 identidades): 2023-24 ben Internacional C; 2024-25 ben CD Teguise; 2024-25 ben Internacional B; 2024-25 ben Internacional PH
- ficha 2092 (solape; 1 identidades): 2024-25 ben Sporting C; 2024-25 ben Sporting Tías; 2025-26 ben Sporting Tías
- ficha 2098 (solape; 1 identidades): 2022-23 ben Internacional PH; 2023-24 ben Internacional C; 2024-25 ben Internacional B; 2024-25 ben Internacional PH
- ficha 2105 (solape; 1 identidades): 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima; 2024-25 ben O. Marítima B
- ficha 2174 (solape; 1 identidades): 2023-24 ben O. Marítima C; 2024-25 ben Juventud Marítima; 2024-25 ben O. Marítima B
- ficha 2215 (solape; 1 identidades): 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B; 2024-25 ben Internacional B
- ficha 3337 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 3358 (solape; 1 identidades): 2022-23 ben Internacional C; 2023-24 ben Internacional B; 2023-24 ben Internacional PH
- ficha 3407 (solape; 1 identidades): 2022-23 ben Internacional C; 2023-24 ben Internacional B; 2023-24 ben Internacional PH
- ficha 3408 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 3429 (solape; 1 identidades): 2022-23 ben Internacional C; 2023-24 ben Internacional B; 2023-24 ben Internacional PH
- ficha 3446 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 3456 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 3488 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 3489 (solape; 1 identidades): 2022-23 ben O. Marítima B; 2023-24 ben Juventud Marítima; 2023-24 ben O. Marítima B
- ficha 4446 (solape; 1 identidades): 2019-20 pre Atco. Huracán; 2020-21 pre Atco. Huracán B; 2020-21 pre Tamaraceite; 2021-22 ben Tamaraceite; 2022-23 ben Tamaraceite
- ficha 4626 (solape; 1 identidades): 2021-22 ben Veteranos B; 2022-23 ben Puertos; 2022-23 ben Veteranos B; 2023-24 ben Puertos
- ficha 4682 (solape; 1 identidades): 2022-23 ben Puertos; 2022-23 ben Veteranos B; 2023-24 ben Veteranos
- ficha 4685 (solape; 1 identidades): 2022-23 ben Puertos; 2022-23 ben Veteranos B
- ficha 4686 (solape; 1 identidades): 2022-23 ben Puertos; 2022-23 ben Veteranos B; 2023-24 ben Puertos
- ficha 4690 (solape; 1 identidades): 2022-23 ben Puertos; 2022-23 ben Veteranos B; 2023-24 ben Puertos
- ficha 4691 (solape; 1 identidades): 2022-23 ben Puertos; 2022-23 ben Veteranos B; 2023-24 ben Puertos
- ficha 11381 (solape; 1 identidades): 2021-22 ben Puertos; 2021-22 ben Veteranos B; 2022-23 ben Gáldar CF
- ficha 11544 (solape; 1 identidades): 2019-20 ben Altavista; 2020-21 ben Altavista; 2021-22 ben Juventud Marítima; 2021-22 ben O. Marítima B; 2022-23 ben Juventud Marítima
- ficha 11545 (solape; 1 identidades): 2020-21 ben O. Marítima C; 2021-22 ben Juventud Marítima; 2021-22 ben O. Marítima B; 2022-23 ben Juventud Marítima
- ficha 11547 (solape; 1 identidades): 2020-21 ben O. Marítima C; 2021-22 ben Juventud Marítima; 2021-22 ben O. Marítima B; 2022-23 ben Juventud Marítima
- ficha 11548 (solape; 1 identidades): 2020-21 ben O. Marítima C; 2021-22 ben Juventud Marítima; 2021-22 ben O. Marítima B; 2022-23 ben Juventud Marítima
- ficha 12277 (solape; 1 identidades): 2023-24 pre Fuerteklub; 2024-25 pre Peña Amistad; 2025-26 ben Peña Amistad; 2025-26 ben Peña B; 2025-26 pre Peña Amistad; 2026-27 ben Peña Amistad
- ficha 12282 (solape; 1 identidades): 2025-26 ben Peña Amistad; 2025-26 ben Peña B; 2025-26 pre Peña Amistad; 2026-27 ben Peña B
- ficha 12299 (solape; 1 identidades): 2024-25 pre Atisachi FTV; 2025-26 ben Atisachi FTV; 2025-26 ben Peña Amistad; 2025-26 ben Peña B; 2025-26 pre Atisachi FTV B; 2025-26 pre Peña Amistad; 2026-27 ben Peña Amistad
- ficha 14860 (solape; 1 identidades): 2021-22 ben CD Corralejo; 2023-24 ben CD Corralejo; 2023-24 ben Fuerteklub
- ficha 15971 (solape; 1 identidades): 2019-20 pre San Juan; 2020-21 ben San Juan; 2020-21 ben San Juan At.; 2021-22 ben Las Mesas Hu.
- ficha 15972 (solape; 1 identidades): 2019-20 pre San Juan; 2020-21 ben San Juan; 2020-21 ben San Juan At.; 2021-22 ben Las Mesas Hu.
- ficha 15973 (solape; 1 identidades): 2019-20 pre San Juan; 2020-21 ben San Juan; 2020-21 ben San Juan At.; 2021-22 ben Las Mesas Hu.
- ficha 15975 (solape; 1 identidades): 2019-20 pre San Juan; 2020-21 ben San Juan; 2020-21 ben San Juan At.; 2021-22 ben Las Mesas Hu.
- ficha 16577 (solape; 1 identidades): 2019-20 pre Doramas; 2020-21 ben CD Arinaga; 2020-21 ben Doramas B; 2021-22 ben CD Arinaga
- ficha 17047 (solape; 1 identidades): 2020-21 ben Guiniguada; 2020-21 ben Guiniguada B; 2021-22 ben Acodetti; 2021-22 ben Simusetti B
- ficha 17450 (solape; 1 identidades): 2019-20 pre Atlético; 2020-21 ben Atlético; 2020-21 ben CD Cerruda; 2020-21 ben Cerruda B; 2021-22 ben Gran Canaria
- ficha 17471 (solape; 1 identidades): 2019-20 pre Victoria; 2020-21 ben Corazón Mª C; 2020-21 ben Las Mesas Hu.; 2021-22 ben Corazón Mª
- ficha 18134 (solape; 1 identidades): 2019-20 ben O. Marítima B; 2019-20 ben O. Marítima C; 2020-21 ben O. Marítima; 2020-21 ben O. Marítima C; 2021-22 ben Juventud Marítima; 2021-22 ben O. Marítima B
- ficha 18614 (solape; 1 identidades): 2021-22 ben La Oliva; 2021-22 ben Villaverde
- ficha 18750 (solape; 1 identidades): 2019-20 ben Atlético; 2019-20 ben Atlético B; 2020-21 ben Universitario
- ficha 18789 (solape; 1 identidades): 2019-20 ben San Juan; 2019-20 ben San Juan At.; 2020-21 ben Atco. Huracán; 2020-21 ben San Juan
- ficha 18822 (solape; 1 identidades): 2019-20 ben Colegio Norte Viera; 2020-21 ben Colegio Norte Viera; 2020-21 ben Unión Viera
- ficha 18838 (solape; 1 identidades): 2019-20 ben Colegio Norte Viera; 2019-20 ben Colegio Norte Viera At.; 2020-21 ben Unión Viera
- ficha 18873 (solape; 1 identidades): 2019-20 ben Atlético; 2019-20 ben Atlético B; 2020-21 ben Atlético
- ficha 18880 (solape; 1 identidades): 2019-20 ben Guiniguada; 2019-20 ben Puertos; 2019-20 ben San Juan; 2019-20 ben San Juan At.; 2020-21 ben Veteranos
- ficha 18925 (solape; 1 identidades): 2019-20 ben San Juan; 2019-20 ben San Juan At.; 2020-21 ben San Juan
- ficha 18928 (solape; 1 identidades): 2019-20 ben San Juan At.; 2020-21 ben San Juan; 2020-21 ben San Juan At.
- ficha 19443 (solape; 1 identidades): 2019-20 ben Colegio Norte Viera; 2019-20 ben Colegio Norte Viera At.; 2020-21 ben Garepa Viera
- ficha 19520 (solape; 1 identidades): 2019-20 ben San Juan; 2019-20 ben San Juan At.; 2020-21 ben San Juan At.
- ficha 19634 (solape; 1 identidades): 2019-20 ben Puerto del Carmen; 2019-20 ben Puerto del Carmen B; 2020-21 ben Puerto del Carmen; 2020-21 ben San Bartolomé
- ficha 19731 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH; 2020-21 ben O. Marítima; 2020-21 ben O. Marítima B
- ficha 19775 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH; 2020-21 ben Internacional B
- ficha 19776 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH; 2020-21 ben Internacional B
- ficha 19777 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH; 2020-21 ben Internacional B
- ficha 19801 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH; 2020-21 ben Internacional B
- ficha 19924 (solape; 1 identidades): 2019-20 ben Atco. Huracán; 2019-20 ben Las Mesas Hu.
- ficha 19957 (solape; 1 identidades): 2019-20 ben Alcotán Can.; 2019-20 ben Atlético; 2019-20 ben Atlético B
- ficha 20006 (solape; 1 identidades): 2019-20 ben San Juan; 2019-20 ben San Juan At.
- ficha 20087 (solape; 1 identidades): 2019-20 ben CD Calero; 2019-20 ben Las Longueras; 2019-20 ben Longueras B
- ficha 20174 (solape; 1 identidades): 2019-20 ben Las Longueras; 2019-20 ben Longueras B
- ficha 20188 (solape; 1 identidades): 2019-20 ben Las Longueras; 2019-20 ben Longueras B
- ficha 20191 (solape; 1 identidades): 2019-20 ben Las Longueras; 2019-20 ben Longueras B
- ficha 21471 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH
- ficha 21472 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH
- ficha 21476 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH
- ficha 21479 (solape; 1 identidades): 2019-20 ben Internacional B; 2019-20 ben Internacional PH

</details>

## Los cinco ejemplos del mapa (D12)

- **4472, «A.»** (con id)
  - antes: 2019-2020 pre PGC1 Unión Moral (12); 2020-2021 pre PGC1 Roque Amagro (10); 2021-2022 ben GC1 Roque Amagro (30); 2022-2023 ben BPGC1 Arucas (24); 2026-2027 pre PG2 Las Mesas Hu. (4)
  - después, su ficha (1 identidades, principal 4472): 2019-2020 pre PGC1 Unión Moral (12); 2020-2021 pre PGC1 Roque Amagro (10); 2021-2022 ben GC1 Roque Amagro (30); 2022-2023 ben BPGC1 Arucas (24)
  - separada a 25920 (sin id), ficha suelta: 2026-2027 pre PG2 Las Mesas Hu. (4)
- **1746, «D.»** (con id)
  - antes: 2022-2023 pre PGC2 Simusetti (10); 2023-2024 pre PCC1 Tamaraceite (3); 2023-2024 pre PGC2 Tamaraceite (23); 2024-2025 ben B2 Tamaraceite B (18); 2024-2025 ben BCB1 Tamaraceite B (1); 2024-2025 ben P7 Tamaraceite B (9); 2025-2026 ben A2 Tamaraceite (22); 2025-2026 ben BCA1 Tamaraceite (2); 2025-2026 ben FF10 Tamaraceite (5); 2026-2027 ale AL4 Las Mesas Hu. C (4); 2026-2027 pre PG3 Tamaraceite B (4)
  - después, su ficha (1 identidades, principal 1746): 2022-2023 pre PGC2 Simusetti (10); 2023-2024 pre PCC1 Tamaraceite (3); 2023-2024 pre PGC2 Tamaraceite (23); 2024-2025 ben B2 Tamaraceite B (18); 2024-2025 ben BCB1 Tamaraceite B (1); 2024-2025 ben P7 Tamaraceite B (9); 2025-2026 ben A2 Tamaraceite (22); 2025-2026 ben BCA1 Tamaraceite (2); 2025-2026 ben FF10 Tamaraceite (5); 2026-2027 ale AL4 Las Mesas Hu. C (4)
  - separada a 26087 (sin id), ficha suelta: 2026-2027 pre PG3 Tamaraceite B (4)
- **19911, «M.»** (con id)
  - antes: 2019-2020 ben BPGC1 Universitario (14); 2026-2027 pre PG1 UD Atalaya (5)
  - después, su ficha (1 identidades, principal 19911): 2019-2020 ben BPGC1 Universitario (14)
  - separada a 25776 (sin id), ficha suelta: 2026-2027 pre PG1 UD Atalaya (5)
- **22560, «H. G. G.»** (con id)
  - antes: 2020-2021 ben FV13 UD Tarajalejo (3); 2026-2027 pre PG1 UD Guía (3)
  - después, su ficha (1 identidades, principal 22560): 2020-2021 ben FV13 UD Tarajalejo (3)
  - separada a 25822 (sin id), ficha suelta: 2026-2027 pre PG1 UD Guía (3)
- **4891, «A.»** (con id)
  - antes: 2022-2023 ben BPGC1 LasTorres/EUDLP (21); 2026-2027 pre PG2 Santa Brígida (1); 2026-2027 pre PG3 CD Calero (3)
  - después, su ficha (1 identidades, principal 4891): 2022-2023 ben BPGC1 LasTorres/EUDLP (21)
  - separada a 25949 (sin id), ficha suelta: 2026-2027 pre PG2 Santa Brígida (1)
  - separada a 26105 (sin id), ficha suelta: 2026-2027 pre PG3 CD Calero (3)

## Comprobaciones

- `PRAGMA integrity_check`: ok
- `PRAGMA foreign_key_check`: sin fallos
- `ficha_id` que apuntan a una fila que no existe o que no es principal: 0
- Segunda pasada seguida: recuentos iguales: True; `ficha_id`/`union_por` iguales: True; apariciones movidas: 0; filas cambiadas por el resolvedor: 0.

## Tiempos (segundos)

- leer originales: 2.28
- esquema: 0.02
- separar: 8.23
- resolver_fichas: 6.51
- de `resolver_fichas`: cargar 4.3, resolver 2.15
