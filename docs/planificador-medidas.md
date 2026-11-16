# La frescura del planificador del bot: medidas

**Qué se mide.** `scripts/tests/frescura_planificador.py` corre las simulaciones de `test_bot_pasada_corta.py` y `test_bot_rotacion.py` (sin red, reloj falso) y saca como números lo que esas pruebas comparan con sus umbrales, con el nombre de la prueba. Añade dos escenarios sin prueba, de tres semanas: **seca 1 de 5** (una de cada cinco pasadas la federación frena desde la primera página) y **estado perdido cada 12** (antes de las pasadas 12, 24… se borran las comprobaciones por grupo de `data-health.json`, lo único que el planificador de hoy recibe de la pasada anterior; la base sigue).
**Cómo se lanza.** `python3 scripts/tests/frescura_planificador.py` (tabla; `--json`, `--semillas`, `--escenarios`). Con 3 semillas y 36 escenarios tarda ~2,5 min en 8 núcleos (~11 min de CPU); no está en la suite. Desde código: `medir(planificar=otro, semilla=7)` instala `otro` en lugar de `update_fiflp.plan_groups` mientras dura la medida.
**Semillas.** 7 (la de las pruebas), 11 y 23: cambian la temporada simulada (horas de publicación de resultados y actas) y los ticks perdidos del reloj (con la 7, el reloj usa la 1, la de la prueba). `test_bot_rotacion` no tiene azar.

## Línea base (el planificador de hoy)

Valor con la semilla 7; entre corchetes, mínimo–máximo con las tres. Los umbrales de los escenarios nuevos son solo referencia (los de la semana y las tres semanas): ninguna prueba los afirma.

| Magnitud | Umbral (prueba) | semana / tres semanas | reloj | seca 1 de 5 | estado perdido cada 12 |
|---|---|---|---|---|---|
| Prioritarios: hueco máximo entre lecturas (h) | ≤ 6,27 (b); ≤ 8 con reloj (f) | 6,11 [6,10–6,11] | 7,55 [7,38–**8,64**] | 8,12 [8,11–8,12] | 8,00 [7,99–8,00] |
| Prioritarios: resultados no leídos en la 1.ª pasada posible | = 0 (b, f) | 0 | 0 | 3 [3–6] | 0 |
| Prioritarios: minutos desde que se publica hasta que se lee, mediana / máx. | ≤ 60 / ≤ 150 (f) | — | 43 [8–50] / 107 [43–114] | — | — |
| Prioritarios: completos, lo más viejo (días) | ≤ 1 (c) | 0,92 [0,67–0,92] | — | 1,01 [1,01–1,17] | 0,92 [0,92] |
| Abiertos: completos, el peor (días) | ≤ 8 (c) | 7,76 [7,76–8,00] | — | 19,83* [14,51–19,83] | 14,01 [11,33–15,17] |
| Abiertos: completos, mediana (días) | ≤ 4,5 (c) | 4,26 [4,26] | — | 6,92 [6,92] | 4,67 [4,34–4,76] |
| No prioritarios: percentil 70 (días) | ≤ 5 (c) | 4,84 [4,67–4,92] | — | 8,58 [8,01–8,58] | 6,17 [6,17–6,67] |
| No prioritarios: fracción en ≤ 5 días | ≥ 0,7 (c) | 0,730 [0,716–0,743] | — | 0,014 [0,014] | 0,500 [0,486–0,554] |
| Páginas útiles al día | ≥ 330 (e, f) | 360 [360] | 372 [372–402] | 287 [287] | 360 [360] |
| Pasadas que esperan un 2.º freno (≥ 600 s) | = 0 (a, f) | 0 | 0 | 50 (las secas) | 0 |
| Actas de los prioritarios: horas hasta importarlas, máx. | ≤ 8 (g) | | reloj perfecto: 7,05 [2,29–7,05], 7 de 7 | | |
| Pasadas / en ventanas de partidos | ≥ 75 / ≥ 20 (f) | | 81 [81–87] / 25 [25–30] | | |
| Actas pendientes al final / sin intentos | ≤ 5 / = 0 (f) | | 1 [1–2] / 0 | | |

\* Con la semilla 7 ese máximo sigue abierto al acabar las tres semanas (`open_complete_gaps`): es una cota inferior.

En todas las semillas y escenarios, sin nada que señalar: 0 páginas pasado el plazo, 0 errores por el freno y al final, 0 grupos sin ninguna lectura, y como mucho 1 espera y 2 bloqueos por pasada. «Completo» es `complete_gaps`: calendario, goleadores y actas. Pruebas de `test_bot_pasada_corta`: (a) `test_no_pass_waits_…`, (b) `test_every_priority_group_…`, (c) `test_how_long_each_open_group_…` (sobre tres semanas), (d) `test_a_brake_is_never_an_error_…`, (e) `test_more_useful_pages_per_day`, (f) `test_with_the_clock_…`, (g) `test_with_a_perfect_clock_…`.

**`test_bot_rotacion`** (30 escenarios, uno por parámetro de cada prueba; 180 magnitudes): todas dentro, sin variación entre semillas. Muchas, justo en el umbral: huecos de 2 de 2 (un salto), 4 de 4 y 3 de 3 (saltos con páginas lentas), 3 de 3 (páginas lentas, 8 págs. a 5,3 s y pasada perdida a 3 s), 7 de 7 (cortes a 6,8 s y a 6,0 s con 8 págs., pasada perdida a 4 s en las fases 1 y 2, cerrados con pasada perdida), 5 de 5 (cerrados); con el cupo medido, prioritarios cada 3 pasadas (≤ 3) y otros por pasada, mín. 1 (≥ 1). La tabla entera, con el guion.

No se miden: `test_the_clock_without_losses_…` (no depende del planificador) y `test_each_priority_group_is_read_complete_before_the_next_…` (el orden dentro de una pasada, no frescura; la suite lo sigue guardando).

## Observaciones

- **Lo más justo:** el peor grupo abierto (7,76–8,00 días para ≤ 8: con la semilla 23 toca el umbral) y el hueco de los prioritarios con reloj: con los ticks perdidos de la semilla 23 (es el reloj, no la temporada: con la temporada 7 y el reloj 23, lo mismo) un prioritario (AL11) pasa 8,64 h sin leerse, por encima de las 8 que afirma (f). La prueba pasa porque usa el reloj de la semilla 1. En la semana, 6,11 h para ≤ 6,27.
- **Ruido entre semillas:** pequeño en las tres semanas (mediana idéntica; p70 ±0,13 días; peor grupo +0,24) y grande en lo que depende del reloj (minutos tras el partido: mediana de 8 a 50). Para comparar otro planificador, mismas semillas y diferencias mayores que estos rangos.
- **Los escenarios nuevos** son los que más castigan a la rotación sin estado: con una pasada seca de cada cinco (20 % menos de páginas) la mediana pasa de 4,3 a 6,9 días y solo 1 de 74 no prioritarios queda en ≤ 5; perder el estado cada día casi dobla el peor grupo (de 7,8 a 14 días) y deja a los prioritarios en el límite de 8 h. Las pasadas secas esperan sondeando hasta el plazo (762 s): son las 50 «esperas del 2.º freno».
