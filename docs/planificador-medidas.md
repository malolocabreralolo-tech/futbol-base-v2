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

## El planificador por antigüedad, comparado con el de hoy (fase 4B, tarea 2)

**Veredicto: peor.** El planificador nuevo mantiene la información de los grupos normales bastante más fresca que el de hoy: en tres semanas, el peor grupo pasa de 7,8 a 4,1 días y todos quedan al día en 5 días o menos. Aun así es peor en cuatro cosas, y con eso no se cambia:
1. Si el estado se pierde cada día, 30 grupos se quedan sin leer en tres semanas.
2. Un grupo del dueño puede pasar casi 8 h sin leerse, con la semilla 23 y en las pasadas secas.
3. Al final de la semana del reloj quedan más actas pendientes.
4. Los goleadores de un grupo pequeño se leen alguna vez menos.

Eso es con los dos añadidos que se permiten. Con un tercero, que no cuenta, seguiría siendo peor en cinco magnitudes.

**Qué se mide.** `scripts/planificador.py` es una función pura que devuelve el orden de la pasada. Aplica cuatro tramos:
1. los calientes;
2. los prioritarios abiertos cuya última lectura completa tiene más de `max_prioritario`;
3. los demás abiertos, por antigüedad;
4. los cerrados sin actas pendientes, al final.

`PlanNuevo`, en `frescura_planificador.py`, lo enchufa a las simulaciones con la firma de `plan_groups`, sin tocar `update_fiflp.py`. Cuatro decisiones del adaptador:
- **Antigüedad.** Es la más reciente entre la última lectura completa y el último intento. Si contara solo la lectura completa, un grupo que falla siempre sería el primero en todas las pasadas.
- **Leído completo.** `status` ok y fuera de `run.extrasDeferred` (sin goleadores ni actas por hacer): es lo que el bot sabe de sí mismo. Una lectura con error solo mueve `intento`. Lo que el freno o el plazo no dejaron empezar no apunta nada, así que una pasada seca no marca nada.
- **`max_prioritario`.** El adaptador pasa 6 h − 2 h + 30 min = 4,5 h, lo mismo que mira `stale` hoy: «en la pasada siguiente pasaría de 6 h». Con 6 h literales, los huecos serían de 8 h. No cuenta como añadido.
- **Respaldo y estado.** El estado se guarda en memoria de una pasada a otra; en el bot iría en la caché de GitHub Actions. Para un grupo que no está en el estado se usa `checks` (`data-health.json`): la última comprobación correcta cuenta como lectura completa y una que falló, como intento. En «estado perdido cada 12» se vacían los dos a la vez.

**Cómo se repite.**
- `python3 scripts/tests/frescura_planificador.py --comparar` compara el de hoy con el nuevo con sus dos añadidos.
- `--comparar regla` lo compara con la regla sin añadidos.
- `--planificador nuevo` da la tabla del nuevo sola.
- Cada ejecución, unos 3 min.
- Magnitudes nuevas, sin umbral, para el criterio de páginas: `paginas_pedidas_dia` (semana, reloj y los dos escenarios nuevos), `paginas_pedidas` (rotación) y `paginas_servidas` (cupo). Además, `prioritarios_hueco_pasadas` se mide también sin commits.

**Cómo se lee la tabla.**
- Valor con la semilla 7 y, entre corchetes, mínimo–máximo con las semillas 7, 11 y 23. La diferencia es nuevo − hoy con la semilla 7.
- «Ruido» es el rango del de hoy entre las tres semillas.
- **PEOR** quiere decir que, en alguna semilla, el nuevo es peor que el de hoy en esa misma semilla por más que ese ruido.
- «(ok: NO)» marca que con la semilla 7 no cumple el umbral de la prueba.
- Las filas en que todo vale 0 en los dos (pausas, esperas, bloqueos, páginas pasado el plazo, errores) salen «igual o mejor» en todos los escenarios. Se omiten aquí; están en la salida del guion.

| Escenario | Magnitud | Umbral | Hoy | Nuevo | Dif. | Ruido | ¿Dentro del ruido? |
|---|---|---|---|---|---|---|---|
| semana | prioritarios_hueco_max_h | ≤ 6,27 | 6,11 [6,1–6,11] | 6,11 [6,11–7,89] | 0 | 0,01 | **PEOR** (semilla 23: 7,89; con la 7 cumple) |
| semana | prioritarios_tarde | = 0 | 0 | 0 | 0 | 0 | igual |
| semana | paginas_utiles_dia / pedidas | ≥ 330 / — | 360 / 396 | 360 / 396 | 0 | 0 | igual |
| tres semanas | prioritarios_completo_max_d | ≤ 1 | 0,92 [0,67–0,92] | 0,92 [0,67–0,92] | 0 | 0,25 | igual |
| tres semanas | completo_max_d | ≤ 8 | 7,76 [7,76–8] | 4,09 [3,92–4,09] | −3,67 | 0,24 | mejor |
| tres semanas | completo_mediana_d | ≤ 4,5 | 4,26 | 3,92 [3,76–3,92] | −0,34 | 0 | mejor |
| tres semanas | otros_p70_d | ≤ 5 | 4,84 [4,67–4,92] | 4 [3,83–4] | −0,84 | 0,25 | mejor |
| tres semanas | otros_en_5d | ≥ 0,7 | 0,73 [0,716–0,743] | 1 | +0,27 | 0,027 | mejor |
| reloj | prioritarios_hueco_max_h | ≤ 8 | 7,55 [7,38–8,64] | 7,55 [7,38–8,65] | 0 | 1,26 | dentro del ruido |
| reloj | prioritarios_min mediana / máx. | ≤ 60 / ≤ 150 | 43,1 / 107,2 | 43,1 / 107,2 | 0 | 41,9 / 71,4 | dentro del ruido / igual |
| reloj | paginas_utiles_dia / pedidas | ≥ 330 / — | 372 / 409 [372–402 / 409–442] | 372 / 409 [igual] | 0 | 30 / 33 | igual |
| reloj | pasadas / en ventanas | ≥ 75 / ≥ 20 | 81 / 25 | 81 / 25 | 0 | 6 / 5 | igual (las pone el reloj) |
| reloj | actas_pendientes_final | ≤ 5 | 1 [1–2] | 7 [2–7] | +6 | 1 | **PEOR** (ok: NO) |
| reloj | actas_agotadas | = 0 | 0 | 0 | 0 | 0 | igual |
| reloj perfecto | actas_prioritarios_horas_max | ≤ 8 | 7,05 [2,29–7,05] | 1,92 [1,92–4,92] | −5,13 | 4,76 | dentro del ruido (mejor con la 7; peor con la 11: 4,92 frente a 4,12) |
| seca 1 de 5 | prioritarios_hueco_max_h | ref. 6,27 | 8,12 [8,11–8,12] | 9,87 [9,87–9,98] | +1,75 | 0,01 | **PEOR** |
| seca 1 de 5 | prioritarios_tarde | ref. 0 | 3 [3–6] | 3 [3–6] | 0 | 3 | igual |
| seca 1 de 5 | paginas_utiles_dia / pedidas | ref. 330 / — | 287 / 343 | 287 / 343 | 0 | 0 | igual |
| seca 1 de 5 | prioritarios_completo_max_d | ref. 1 | 1,01 [1,01–1,17] | 0,93 [0,93–1,01] | −0,08 | 0,16 | mejor |
| seca 1 de 5 | completo_max_d | ref. 8 | 19,83 [14,51–19,83] | 8,75 [8,75–9,17] | −11,08 | 5,32 | mejor |
| seca 1 de 5 | completo_mediana_d | ref. 4,5 | 6,92 | 5,33 [5,33–5,42] | −1,59 | 0 | mejor |
| seca 1 de 5 | otros_p70_d / otros_en_5d | ref. 5 / 0,7 | 8,58 / 0,014 | 5,76 / 0,324 | −2,82 / +0,31 | 0,57 / 0 | mejor |
| estado perdido cada 12 | prioritarios_hueco_max_h | ref. 6,27 | 8 [7,99–8] | 8 [8–8,01] | 0 | 0,01 | **PEOR** (por un minuto: 8,01 frente a 7,99 con la 23) |
| estado perdido cada 12 | prioritarios_completo_max_d | ref. 1 | 0,92 | 0,84 [0,84–0,92] | −0,08 | 0 | mejor |
| estado perdido cada 12 | paginas_utiles_dia / pedidas | ref. 330 / — | 360 / 396 | 360 / 396 | 0 | 0 | igual |
| estado perdido cada 12 | grupos_sin_lectura | ref. 0 | 0 | 30 | +30 | 0 | **PEOR** |
| estado perdido cada 12 | completo_max_d | ref. 8 | 14,01 [11,33–15,17] | 20,92* | +6,91 | 3,84 | **PEOR** |
| estado perdido cada 12 | completo_mediana_d | ref. 4,5 | 4,67 [4,34–4,76] | 6,84 | +2,17 | 0,42 | **PEOR** |
| estado perdido cada 12 | otros_p70_d / otros_en_5d | ref. 5 / 0,7 | 6,17 / 0,5 | 20,92* / 0,338 | +14,75 / −0,16 | 0,5 / 0,068 | **PEOR** |

\* 20,92 días es toda la ventana: esos 30 grupos no se leen nunca. Tras cada pérdida, todos quedan sin estado, el desempate por código pone delante siempre los mismos, y en 12 pasadas no se llega al resto.

**`test_bot_rotacion`** (30 escenarios; sin azar, así que el ruido es 0 y cualquier diferencia cuenta):

| Magnitud | Escenarios | Hoy | Nuevo | ¿Dentro del ruido? |
|---|---|---|---|---|
| hueco_abiertos / hueco_goleadores (pasadas seguidas sin leer) | 28 | 1–7 | 1–3 | mejor o igual en todos (p. ej., cortes a 6,8 s: 7 → 3) |
| hueco_cerrados | 6 | 5–7 | 4–5 | mejor |
| pasadas_pasado_plazo, pasadas_sin_prioritarios, pasadas_no_todo_ok, errores, freno | 32 | 0 | 0 | igual |
| paginas_pedidas / paginas_servidas | 28 / 4 | 5178–11355 / 720–2520 | 5178–11329 / 720–2520 | igual o menos |
| cupo: prioritarios_hueco_pasadas (con commits / sin commits) | 4 | 3 / 25 | 3 / 3 | igual / mejor (hoy, sin commits, un prioritario no se lee en 24 pasadas) |
| cupo: prioritarios_en_todas, otros_media, otros_min, nunca_leidos, niveles_leidos | 2 | 0; 2,14–3,16; 1; 0; 3 | 0; 2,22–3,16; 1; 0; 3 | igual o mejor |
| pg3_goleadores (pasadas en que se leen los goleadores de PG3) | 5 | 10–18 | 9–16 | **PEOR** en 4 de 5 (17 → 16, 18 → 16, 13 → 12, 10 → 9; umbral ≥ 6, cumple) |

**No aplica.** Decidido antes de medir; no cuentan ni a favor ni en contra:
- `pasadas_sin_aplazados`: es una condición del escenario (el plazo corta en todas las pasadas), no frescura. Igual: 0.
- `goleadores_max_grupos`: es una condición del escenario (los goleadores tampoco caben todos). Igual: 58.
- `grupos_max_pasada`: es una condición del escenario (con páginas lentas caben menos de 40 grupos). Igual: 29–32.
- `pasadas_con_aplazados`: es una condición del escenario (con páginas más lentas, el plazo corta). Igual: 24.
- `cerrados_fuera_de_epoca`: es la forma de `closed_turn`, una lectura exacta en cada época de 4 pasadas; la frescura de los cerrados es `hueco_cerrados`. Nuevo: 23 (no sigue épocas).
- `fijos_en_todas`: es la forma de la rotación sin estado (sin `data-health.json` publicado, los prioritarios tocan en todas y se llevan el cupo los primeros por código); la frescura es `prioritarios_hueco_pasadas`. Nuevo: 0.

**Los dos añadidos**, con su medida antes y después. Están en `planificar`, apagados por defecto; `PlanNuevo` los enciende con `AÑADIDOS`.
1. **`nivelar=3`** (unas 6 líneas): si en la pasada siguiente vencerían más de 3 prioritarios, los más viejos de ellos se adelantan a esta. Sin él, los prioritarios que se leyeron juntos vencen juntos. Un sábado, 3 calientes y 4 alevines vencidos no caben en ~30 páginas, y uno se va a la pasada siguiente: 8 h.
   - Regla sola → con el añadido:
     - semana, hueco de los prioritarios: 8,01 / 8,11 / 7,89 h → 6,11 / 6,12 / 7,89;
     - reloj: 8,70–9,07 → 7,38–8,65;
     - seca 1 de 5: 10,0 → 9,87;
     - estado perdido cada 12: 8,09 → 8,0;
     - cupo con commits (4 págs.), grupos no prioritarios por pasada: mínimo 0 → 1 y media 3,01 → 3,16.
   - Lo que empeora: actas pendientes al final del reloj, 3 / 4 / 6 → 7 / 7 / 2.
   - Probé tres formas y me quedé con la que empeoraba menos:
     - rellenar hasta 3 los tramos 1 y 2: semana 7,98 / 7,98 / 6,11; otros por pasada 3,01 → 2,46; un acta de un prioritario a 23,3 h con la semilla 23;
     - nivelar a 2: semana 7,99 / 6,12 / 6,11; actas pendientes 6 / 11 / 8;
     - nivelar a 3: la elegida.
2. **`cerrado_cada=1 día`** (unas 3 líneas): un cerrado sin actas pendientes que lleva más de un día sin leerse va con los abiertos. Sin él, con el plazo lleno de abiertos, un cerrado no se lee nunca.
   - `hueco_cerrados`: 24 y 28 pasadas → 4 y 5 (hoy, 5 y 7).
   - Nada más cambia: en las simulaciones de `test_bot_pasada_corta` no hay cerrados.

**Un tercer añadido, solo como información** (no cuenta, y no está en el código): desempatar entre los grupos sin estado por una suma de su código y la fecha, en vez de por el código. En «estado perdido cada 12» el peor grupo baja de 20,92 a 8,2–9,5 días y quedan 0 sin leer. Aun así seguiría siendo peor en cinco magnitudes:
- el hueco de los prioritarios en la semana (7,89 con la 23) y en la seca (9,87);
- las actas pendientes del reloj (7);
- en el estado perdido, la mediana (4,84–5,01 frente a 4,34–4,76) y `otros_en_5d` (0,446–0,459 frente a 0,486–0,554);
- `pg3_goleadores`.

**Recuento de líneas** (paso 3).
- **Lo que sustituiría en `update_fiflp.py`: 223 líneas.**
  - `plan_groups`: 100.
  - Las funciones que solo usa él, 81: `turn_size`, `turn_blocks`, `spin`, `rotate`, `interleave`, `pass_phase`, `closed_turn`, `alevin_quota`, `stale`, `priority_slot` y `_natural`.
  - Constantes y comentarios de rotación, cerrados y cuota de alevín: 20.
  - Líneas en blanco entre ellas: ~22.
  - `daily_turn`, `extras_turn` y `run_number` se quedan, porque también los usa `run_passes`.
- **Lo que pondría: unas 165 líneas.**
  - `scripts/planificador.py`: 92 (unas 30 de docstrings y comentarios).
  - El adaptador (`respaldo` y `__call__` de `PlanNuevo`): ~50.
  - Guardar y leer el estado y apuntar cada pasada: ~25 más en la tarea 3 (sin escribir), además de un paso de `actions/cache` en `update.yml`.
- **Neto: unas 60 líneas menos de código del bot**, no las ~1.100 que estimaba el plan, que contaban también `run_passes` y el freno, y esos no cambian.
- En pruebas, saldrían unas 200 líneas: 9 pruebas de `test_bot_plazo.py` (147) y 4 de `test_bot_prioritarios.py` (51) prueban las funciones de rotación. Entran las 151 de `test_planificador.py`.
