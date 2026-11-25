# Ampliación, parte C2: la liga de escuelas llega a la ficha de cada niño — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la ficha de un niño federado diga en qué equipo de la liga de escuelas (MyGol) estuvo y cuándo, cuando se le puede enlazar con seguridad, y que esas temporadas de escuela afinen su año de nacimiento.

**Architecture:** Un módulo puro (`scripts/enlace_mygol.py`) decide qué niño de MyGol es qué ficha con una sola regla prudente (nombre y dos apellidos idénticos, un solo candidato, edad compatible, y nunca un nombre que se repite en dos clubes de MyGol la misma temporada). La pasada del bot guarda el resultado en una tabla (`mygol_enlaces`) después de resolver las fichas. El generador añade a cada ficha enlazada sus temporadas de escuela (`"e"`) y las cuenta como observaciones del estimador del año de nacimiento. La ficha de la web las pinta en un bloque propio, marcado como enlazado por el nombre.

**Tech Stack:** Python 3.11 (sqlite3, pytest 9.2.0), módulos ES de `src/` con `node --test`; esbuild solo al publicar (no lo ejecuta ninguna tarea).

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (decisiones 1 y 7). Lo que ya existe: `docs/mygol.md` (tablas `mygol_*`, el id de jugador es de cada temporada), `docs/identidad.md` (fichas e identidades), `docs/ranking.md` (el año de nacimiento).

## Lo medido que manda (25/11/2026, sobre los originales completos y la base)

- 5.196 niños de MyGol (un id por temporada): 4.905 con dos apellidos, 291 con uno.
- La regla de este plan enlaza 1.548 con 983 fichas, con un error estimado por debajo del 1,3 %. Enlazar por el primer apellido falla en torno al 16 %: no se hace. Exigir el mismo club solo añade 6 niños: no se hace.
- 13 nombres completos se repiten en la misma temporada en clubes distintos de MyGol (alguno, en los dos equipos del mismo partido: son dos niños): no se enlazan.
- De las fichas enlazadas, unas 950 tienen la escuela antes de su primera temporada federada. Y 422 de las 496 que hoy tienen dos años posibles pasan a uno.
- La categoría de los seis torneos sin decidir, con el cruce completo: 32 miniprebenjamín, 33 prebenjamín, 34 benjamín (2022-23); 51 benjamín, 52 prebenjamín, 53 miniprebenjamín (2023-24).

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-escuelas`, rama `escuelas`. No se toca v1 ni los otros árboles.
- Nada de red. `futbolbase.db` y `base/` del árbol no se modifican (las pruebas sobre la base real la copian a `tmp_path`). Ojo: las tablas `mygol_*` puede que aún no estén en la base del árbol (las crea el bot en su primera pasada con los originales): todo tiene que funcionar con ellas ausentes, vacías o llenas.
- No se hace `git push` ni `git stash`, ni se ejecutan `scripts/publicar.py`, `scripts/generate_js.py` ni `scripts/fetch_futbolaspalmas.py` sobre el árbol; no se tocan `dist/`, `index.html` ni `sw.js`; ningún `data-*.js` en un commit.
- Ningún nombre real de niño en código, pruebas, fixtures, documentos, informe ni commits. Los originales de MyGol (`scripts/mygol_*_raw.json`) llevan nombres reales: se leen, no se copian.
- Es peor enlazar a un niño con otro que no enlazarlo: ante la duda, no se enlaza. El enlace nunca une dos fichas de la federación entre sí ni cambia una ficha: solo le añade las temporadas de escuela.
- Lo enlazado se enseña siempre como enlazado por el nombre.
- Un fallo del enlace nunca deja al bot sin publicar: su llamada en la pasada va protegida como la de `importar_mygol`, y si falla la web sale sin escuelas.
- Las claves de las fichas y lo que hoy publican `data-jugadores-*` no cambian salvo `"e"` y `"y"`.
- Estilo del fichero que se toca (comentarios en español que explican el porqué). Cada commit acaba con `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.

## Review Focus

- **Dos niños con el mismo nombre completo en MyGol la misma temporada, en clubes distintos**: ninguno se enlaza. Prueba en la tarea 2 (`test_nombre_repetido_en_dos_clubes_no_se_enlaza`).
- **Una ficha a la que llegarían dos niños de MyGol de la misma temporada y clubes distintos** (por dos caminos): ninguno se enlaza. Prueba en la tarea 2 (`test_una_ficha_no_recibe_dos_ninos_de_la_misma_temporada`).
- **La base sin tablas `mygol_*`** (o vacías): el enlace no hace nada, el generador publica las fichas como hoy y la web no pinta el bloque. Pruebas en las tareas 3 y 4.
- **La ficha principal cambia** entre pasadas (el resolvedor elige otra identidad): los enlaces se rehacen enteros en cada pasada y siguen a la ficha. Prueba en la tarea 3 (`test_los_enlaces_se_rehacen_enteros`).
- **Una temporada de escuela sin ninguna jornada jugada apuntada** (`jugo` 0 en todas): sale en la ficha con «en la plantilla», y cuenta para el año con el peso mínimo. Pruebas en las tareas 4 y 5.

---

### Task 1: Las categorías de los seis torneos y la ventana del miniprebenjamín

**Files:**
- Modify: `scripts/mygol_torneos.json`, `scripts/nacimiento.py`, `docs/mygol.md`
- Test: `scripts/tests/test_nacimiento.py`, `scripts/tests/test_fetch_mygol.py` o `test_import_mygol.py` (donde ya se compruebe la tabla)

**Interfaces:**
- Produces: en `mygol_torneos.json`, `"categoria"` de 32 → `"miniprebenjamin"`, 33 → `"prebenjamin"`, 34 → `"benjamin"`, 51 → `"benjamin"`, 52 → `"prebenjamin"`, 53 → `"miniprebenjamin"`, y sus `"nombre"` como los demás («Miniprebenjamín Escuela 2022/2023»…). `nacimiento.VENTANA["miniprebenjamin"] = (5, 4)`.

- [ ] **Step 1: Pruebas que fallan**: `VENTANA` con siete categorías (la prueba `test_ventanas` se actualiza); `estimar([(2025, "miniprebenjamin", 10)]) == (2020, 2021)`; `estimar([(2024, "miniprebenjamin", 12), (2026, "prebenjamin", 15)]) == (2020,)`; ningún torneo de la tabla con `categoria` `None` y todas las categorías dentro de `VENTANA`.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_nacimiento.py` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar.** En `docs/mygol.md`, quitar lo de «categoría sin decidir» y contar en cuatro líneas cómo se decidieron (el cruce completo entre temporadas y con las fichas; el 34, por la continuidad en la federación).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_nacimiento.py scripts/tests/test_ranking.py scripts/tests/test_fetch_mygol.py scripts/tests/test_import_mygol.py scripts/tests/test_jugadores_ampliacion.py` — Expected: en verde (`ranking.factor_edad` e `indice` siguen igual: en el ranking no hay filas de miniprebenjamín).
- [ ] **Step 5: Commit.** Asunto: «MyGol: la categoría de los torneos de 2022-23 y 2023-24, y la ventana del miniprebenjamín».

---

### Task 2: La regla de enlace

**Files:**
- Create: `scripts/enlace_mygol.py`
- Test: `scripts/tests/test_enlace_mygol.py`

**Interfaces:**
- Consumes: `identidad.normalizar`, `identidad.nombre_completo`, `identidad.club`, `nacimiento.VENTANA`.
- Produces (todo puro: sin base ni red):
  - `@dataclass(frozen=True) class Nino`: `id: int` (el id de MyGol, de esa temporada), `norm: str` (`identidad.normalizar("<apellidos>, <nombre>")`), `temporada: int` (año de inicio), `categoria: str | None`, `clubes: frozenset[str]` (`identidad.club` de cada equipo de MyGol en el que sale esa temporada).
  - `@dataclass(frozen=True) class Ficha`: `id: int` (el `players.id` de la principal), `nombres: frozenset[str]` (el nombre normalizado, sin sufijo `#…`, de cada una de sus identidades), `anios: tuple[int, ...]` (su año de nacimiento estimado solo con la federación; `()` si no se sabe).
  - `MARGEN_JOVEN = 1`.
  - `edad_compatible(anios: tuple[int, ...], temporada: int, categoria: str | None) -> bool` — `True` sin categoría, sin años o con categoría que no está en `VENTANA`; si no, si algún año de `anios` cae entre `temporada - mayor` y `temporada - menor + MARGEN_JOVEN` (los dos incluidos).
  - `enlazar(ninos: Iterable[Nino], fichas: Iterable[Ficha]) -> dict[int, int]` — `{id de MyGol: id de la ficha}`. Un niño se enlaza si y solo si: (1) `identidad.nombre_completo(norm)`; (2) en su temporada, ningún otro niño con el mismo `norm` tiene un conjunto de clubes sin ningún club en común con el suyo (si lo hay, no se enlaza ninguno de los de ese nombre esa temporada); (3) hay exactamente una ficha con ese `norm` entre sus `nombres`; (4) `edad_compatible`. Y después: (5) si a una ficha le llegan, de la misma temporada, dos niños sin ningún club en común, no se enlaza ninguno de los dos. El resultado no depende del orden de entrada.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_enlace_mygol.py`, con nombres inventados:
  - `test_edad_compatible`: prebenjamín 2024 (ventana 2017-2018): `(2018,)` sí, `(2019,)` sí (un año por abajo), `(2020,)` no, `(2016,)` no, `(2016, 2017)` sí; `()` sí; categoría `None` sí.
  - `test_enlaza_nombre_completo_unico`: «GOMEZ PEREZ, RAUL» en MyGol y una sola ficha con ese nombre y edad compatible → enlazado.
  - `test_un_apellido_no_se_enlaza`: «GOMEZ, RAUL» en MyGol → no, aunque haya una sola ficha «GOMEZ PEREZ, RAUL».
  - `test_dos_fichas_candidatas_no_se_enlaza`.
  - `test_edad_incompatible_no_se_enlaza`.
  - `test_nombre_repetido_en_dos_clubes_no_se_enlaza`: dos niños con el mismo `norm`, misma temporada, clubes `{"a"}` y `{"b"}` → ninguno; con clubes `{"a"}` y `{"a", "c"}` (el mismo club apuntado dos veces) → los dos, a la misma ficha.
  - `test_una_ficha_no_recibe_dos_ninos_de_la_misma_temporada`: una ficha con dos identidades de nombres distintos, y dos niños de MyGol (uno por cada nombre), misma temporada, clubes sin nada en común → ninguno; en temporadas distintas → los dos.
  - `test_el_mismo_nino_en_varias_temporadas`: tres ids (uno por temporada) con el mismo nombre → los tres a la misma ficha.
  - `test_el_orden_no_importa`: barajando las entradas sale lo mismo.
  - `test_el_nombre_de_una_identidad_secundaria_vale`: la ficha tiene el nombre en una identidad unida, no en la principal → enlazado a la principal.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_enlace_mygol.py` — Expected: error de importación.
- [ ] **Step 3: Implementar `scripts/enlace_mygol.py`.** La cabecera explica la regla y por qué es tan estrecha, con las cifras de «Lo medido que manda».
- [ ] **Step 4: Ejecutar.** Expected: `10 passed`.
- [ ] **Step 5: Commit.** Asunto: «MyGol: la regla que enlaza a un niño de escuela con su ficha».

---

### Task 3: Los enlaces en la base, en cada pasada

**Files:**
- Modify: `scripts/enlace_mygol.py` (la parte con base), `scripts/fetch_futbolaspalmas.py` (la llamada protegida, después de `resolver_fichas`), `scripts/reconstruir.py` y `docs/reconstruccion.md` si la tabla nueva tiene que declararse (es derivada: se rehace en cada pasada)
- Test: `scripts/tests/test_enlace_mygol.py`, `scripts/tests/test_mygol_pasada.py`

**Interfaces:**
- Consumes: `enlazar` (tarea 2); `generate_js._fichas(conn)` (qué identidad es de qué ficha) y lo que `generate_js._datos_fichas` usa para estimar el año solo con la federación; las tablas `mygol_*`.
- Produces:
  - Tabla `mygol_enlaces(jugador_id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL)` — `jugador_id`, el de `mygol_jugadores`; `player_id`, el `players.id` de la principal de su ficha.
  - `ninos_de(conn) -> list[Nino]` y `fichas_de(conn) -> list[Ficha]` — de la base; con las tablas `mygol_*` ausentes o sin `players.fiflp_id`, listas vacías. El año de las fichas, el de `nacimiento.estimar` solo con sus apariciones federadas (nunca con la escuela: si no, el enlace dependería de sí mismo).
  - `guardar_enlaces(conn, registro=print) -> int` — rehace `mygol_enlaces` entera (crea la tabla si falta) con lo que diga `enlazar`, en un `SAVEPOINT`; **no escribe nada si el contenido no cambia** (para no ensuciar la base de una pasada que no cambia nada); devuelve cuántos enlaces hay. Sin tablas `mygol_*`: no crea nada y devuelve 0.
  - En `fetch_futbolaspalmas.py`: `enlazar_mygol(conn, registro=print)`, como `importar_mygol` (protegida: ante cualquier excepción, `rollback`, `  ! MyGol (enlaces): <tipo>: <error>` y la pasada sigue), llamada justo después de `migrate_identidad.resolver_fichas(conn)` y antes de generar.

- [ ] **Step 1: Pruebas que fallan**: con una base sintética (fichas con apariciones federadas y tablas `mygol_*` rellenas con `import_mygol.importar` desde originales inventados): `test_guardar_enlaces` (las filas esperadas); `test_los_enlaces_se_rehacen_enteros` (cambiando la principal de una ficha, la fila apunta a la nueva; quitando un niño del original y reimportando, su enlace desaparece); `test_no_escribe_si_no_cambia` (dos llamadas seguidas: `conn.total_changes` no sube en la segunda); `test_sin_tablas_de_mygol` (0, y la tabla `mygol_enlaces` no se crea); `test_un_fallo_del_enlace_no_para_la_pasada` (con `guardar_enlaces` sustituida por una que lanza); `test_el_orden_de_la_pasada` (en `main`, `enlazar_mygol` va después de `resolver_fichas` y antes de `generate_main`: como las pruebas que ya miran el orden de `main`); y, sobre una copia de la base real con los originales reales importados en la copia (salta si no hay base): entre 1.400 y 1.700 enlaces, a entre 900 y 1.100 fichas, ningún `player_id` que no sea una principal, y ninguna ficha con dos niños de la misma temporada sin club en común.
- [ ] **Step 2: Verlas fallar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_enlace_mygol.py scripts/tests/test_mygol_pasada.py scripts/tests/test_reconstruir.py scripts/tests/test_db_sanity.py scripts/tests/test_base_sana.py scripts/tests/test_piezas.py` — Expected: en verde (la tabla nueva va sola a la pieza común: `test_piezas` no cambia).
- [ ] **Step 5: Commit.** Asunto: «MyGol: los enlaces con las fichas se guardan en cada pasada».

---

### Task 4: El generador publica la escuela y afina el año

**Files:**
- Modify: `scripts/generate_js.py` (`_datos_fichas`, `jugadores_files`)
- Test: `scripts/tests/test_jugadores_ampliacion.py`

**Interfaces:**
- Consumes: `mygol_enlaces`, `mygol_participaciones`, `mygol_partidos`, `mygol_torneos`, `mygol_equipos`.
- Produces:
  - Cada ficha enlazada de `data-jugadores-<k>.js` gana `"e": [[temporada, equipo, categoría, jornadas], ...]`: una fila por temporada y equipo de MyGol (los nombres de equipo, con los espacios de más quitados; `temporada` como `"2024-2025"`; `categoría` en minúsculas o `null`; `jornadas`, las participaciones con `jugo = 1`), en orden de temporada y después de equipo. Sin enlaces, la ficha no lleva `"e"`.
  - El año (`"y"`) de una ficha enlazada se estima con sus observaciones federadas **y** una por cada temporada de escuela de categoría conocida: `(año de inicio, categoría, max(1, jornadas))`.
  - `buscar_files` y `ranking_files` usan ese mismo año (ya lo toman de `_datos_fichas`). El ranking no cuenta la escuela (no hay goles): solo le cambia el año.
  - Con la tabla `mygol_enlaces` ausente o vacía, los tres `*_files` dan exactamente los mismos bytes que hoy.

- [ ] **Step 1: Pruebas que fallan**: `test_la_escuela_en_la_ficha` (filas `"e"` esperadas, con dos equipos el mismo año y una temporada sin jornadas jugadas, `jornadas` 0); `test_la_escuela_afina_el_anio` (una ficha con una sola temporada de benjamín 2026, `(2017, 2018)`, y miniprebenjamín en 2022 → `"y": [2017]`... calcula a mano el caso y escríbelo en un comentario); `test_sin_enlaces_sale_igual` (los mismos bytes con la tabla ausente, vacía y con enlaces a otras fichas, para una ficha no enlazada); `test_determinista_con_escuela` (dos veces, los mismos bytes); sobre la copia de la base real con enlaces: cuántas fichas pasan de dos años a uno (imprímelo; exige solo que no baje ninguna de uno a tres).
- [ ] **Step 2: Verlas fallar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_jugadores_ampliacion.py scripts/tests/test_fichas_publicadas.py scripts/tests/test_pygen_fixes.py scripts/tests/test_precache.py` — Expected: en verde.
- [ ] **Step 5: Medir y apuntar en el informe**: sobre la copia real con enlaces, segundos de `_datos_fichas` antes y después, bytes de más en `data-jugadores-*`, y fichas con `"e"`.
- [ ] **Step 6: Commit.** Asunto: «Fichas: las temporadas de la liga de escuelas y el año afinado con ellas».

---

### Task 5: La ficha enseña la liga de escuelas

**Files:**
- Modify: `src/screen-jugador.js`, `src/model.js` (el nombre de la categoría), `acta.css` solo si hace falta
- Test: `scripts/tests/test_jugador.mjs`, `scripts/tests/test_rediseno_model_nombres.mjs`

**Interfaces:**
- Consumes: `player.e` (tarea 4).
- Produces: `categoryName('miniprebenjamin') === 'Miniprebenjamín'` en `src/model.js` (las demás, como hoy).

Qué se ve: un bloque «Liga de escuelas», con el contexto «enlazado por el nombre y los dos apellidos», después de «Trayectoria» y antes de «Otras fichas con este mismo nombre»: una fila por temporada y equipo, de la más reciente a la más antigua, con el equipo, debajo «Prebenjamín · 2024/25» (sin categoría, solo la temporada) y a la derecha «12 jornadas» (una: «1 jornada»; ninguna apuntada: «en la plantilla»). Las filas no son enlaces. Sin `player.e` (o vacío), el bloque no se pinta. La cabecera de la ficha no cambia.

- [ ] **Step 1: Pruebas que fallan**: el bloque con tres filas en su orden y sus textos; «en la plantilla»; sin `e`, sin bloque; `categoryName('miniprebenjamin')`.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_jugador.mjs`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_*.mjs` — Expected: en verde salvo las de `dist/` desfasado (`test_rediseno_index.mjs` «dist/ es el de las fuentes…» y la que depende de ella), que quedan en rojo hasta que el director publique.
- [ ] **Step 5: Commit.** Asunto: «Ficha del jugador: la liga de escuelas».

---

### Task 6: Documentar

**Files:**
- Modify: `docs/mygol.md` (el enlace: la regla, sus cifras, lo que no enlaza y por qué), `docs/ranking.md` (la escuela cuenta para el año de nacimiento), `docs/identidad.md` (una línea: el enlace con MyGol no une fichas), `docs/decisiones.md` (dos líneas)

- [ ] **Step 1:** Los cuatro documentos, en lenguaje llano, sin nombres reales.
- [ ] **Step 2: Commit.** Asunto: «Documentación: la liga de escuelas en las fichas».
