# Ampliación, parte B: año de nacimiento, buscador de jugadores y ranking por año — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Con los datos que ya hay en la base, que cada ficha de jugador diga su año de nacimiento estimado y resuma su trayectoria, que Explorar busque jugadores por nombre y que haya un ranking de los mejores de cada año de nacimiento.

**Architecture:** Dos módulos puros en Python (`scripts/nacimiento.py`, `scripts/ranking.py`) que `scripts/generate_js.py` usa para publicar tres cosas: el año en `data-jugadores-<k>.js`, un índice de búsqueda troceado por las dos primeras letras (`data-buscar-<xy>.js`) y un fichero de ranking por año (`data-ranking-<año>.js`). La web los lee de forma perezosa: la ficha (`src/screen-jugador.js`), el buscador de Explorar (`src/screen-explorar.js`) y una pantalla nueva (`src/screen-ranking.js`). La web nunca recalcula el año ni el índice.

**Tech Stack:** Python 3.11 (sqlite3, pytest 9.2.0), módulos ES sin dependencias en `src/`, pruebas de Node (`node --test`), esbuild al publicar (`scripts/publicar.py`, no lo ejecuta ninguna tarea).

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (decisiones 1, 2 y 3). Mapa del código: `docs/ampliacion-mapa.md`, sección 4.

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-fichas`, rama `fichas`. No se toca `/home/manolo/claude/futbol-base` (v1) ni el árbol `/home/manolo/claude/futbol-base-v2`.
- Nada de red: ni la federación (fiflp.com) ni ninguna otra web. Todo sale de `futbolbase.db`, que no se modifica (las pruebas sobre la base real la copian).
- Ningún nombre real de niño en código, pruebas, documentos ni mensajes de commit: nombres inventados («GOMEZ PEREZ, RAUL») o claves.
- No se hace `git push`, ni `git stash`, ni se ejecuta `scripts/publicar.py` ni `scripts/generate_js.py` sobre el árbol (escribiría cientos de ficheros de datos): las pruebas llaman a las funciones con una conexión.
- Lo estimado se enseña siempre como estimado: «(estimado)» o «2018 o 2019». Un año confirmado va sin esa marca.
- Las claves de las fichas no cambian. Los enlaces `#/jugador?id=<clave>` y los seguidos de hoy siguen valiendo.
- Estilo: el del fichero que se toca (comentarios en español que explican el porqué; `html\`\`` para todo HTML; sin dependencias nuevas). Las pantallas son `render(ctx)` pura y `mount(root, ctx, nav)`.
- La portada no carga nada nuevo: los ficheros nuevos son perezosos y no entran en el precache del SW (`scripts/precache.py`).
- Cada commit acaba con las dos líneas `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.
- Ancho mínimo 320 px sin desplazamiento horizontal de la página; tema claro y oscuro con las variables de `acta.css` que ya existen.

## Review Focus

- Un niño con **una sola temporada** vista: la ficha, el buscador y el ranking enseñan dos años (tres en juvenil) y lo dicen; el ranking lo saca en las dos listas marcado como dudoso. Prueba en la tarea 1 (`test_una_temporada_da_dos_anios`) y en la 3 (`test_dudoso_sale_en_sus_dos_anios`).
- Una ficha **sin ninguna fila de categoría conocida** (o con filas de una categoría que el estimador no conoce): sin año, y la web no pinta «Nacido en». Prueba en la tarea 1 (`test_sin_observaciones`) y en la 4.
- **Pocos partidos**: tres goles en un partido no ponen a nadie primero del ranking. Prueba en la tarea 2 (`test_pocos_partidos_no_gana`).
- Buscar con **tildes, mayúsculas, apellidos compuestos y partículas** («de la cruz», «GARCÍA», «o'neill»): se encuentra igual. Prueba en la tarea 5 (web) y en la 3 (el trozo en el que cae cada palabra).
- El índice de búsqueda **falla al cargar** (sin red): Explorar sigue buscando equipos y dice que los jugadores no se han podido cargar, con la búsqueda de equipos intacta. Prueba en la tarea 5.

---

### Task 1: El estimador del año de nacimiento

**Files:**
- Create: `scripts/nacimiento.py`
- Test: `scripts/tests/test_nacimiento.py`

**Interfaces:**
- Produces:
  - `VENTANA: dict[str, tuple[int, int]]` — por categoría en minúsculas, `(mayor, menor)`: quien juega la temporada que empieza el año `Y` en su categoría nació entre `Y - mayor` e `Y - menor`. Valores exactos: `{"prebenjamin": (7, 6), "benjamin": (9, 8), "alevin": (11, 10), "infantil": (13, 12), "cadete": (15, 14), "juvenil": (18, 16)}`.
  - `verosimilitud(anio: int, temporada: int, categoria: str) -> float` — `1.0` si `anio` está en la ventana; más joven que la ventana por 1 año `0.25`, por 2 `0.05`, por 3 o más `0.002`; más viejo por 1 año `0.01`, por 2 o más `0.0005`. Categoría desconocida: `KeyError`.
  - `estimar(observaciones: Iterable[tuple[int, str, int]]) -> tuple[int, ...]` — cada observación es `(año de inicio de la temporada, categoría en minúsculas, partidos)`. Devuelve de uno a tres años en orden creciente, o `()` sin observaciones de categoría conocida.
  - `RAZON = 3.0` y `PARTIDOS_PLENOS = 5`.

- [ ] **Step 1: Escribir las pruebas que fallan** en `scripts/tests/test_nacimiento.py` (importa con `sys.path` como las demás pruebas de `scripts/tests/`):

```python
from nacimiento import VENTANA, estimar, verosimilitud

def test_ventanas():
    assert VENTANA == {"prebenjamin": (7, 6), "benjamin": (9, 8), "alevin": (11, 10),
                       "infantil": (13, 12), "cadete": (15, 14), "juvenil": (18, 16)}

def test_verosimilitud():
    assert verosimilitud(2017, 2026, "benjamin") == 1.0 and verosimilitud(2018, 2026, "benjamin") == 1.0
    assert verosimilitud(2019, 2026, "benjamin") == 0.25      # un año por debajo: juega con los mayores
    assert verosimilitud(2020, 2026, "benjamin") == 0.05
    assert verosimilitud(2021, 2026, "benjamin") == 0.002
    assert verosimilitud(2016, 2026, "benjamin") == 0.01      # demasiado mayor
    assert verosimilitud(2015, 2026, "benjamin") == 0.0005

def test_una_temporada_da_dos_anios():
    assert estimar([(2026, "benjamin", 10)]) == (2017, 2018)
    assert estimar([(2026, "alevin", 22)]) == (2015, 2016)
    assert estimar([(2026, "juvenil", 20)]) == (2008, 2009, 2010)
    assert estimar([(2026, "benjamin", 1)]) == (2017, 2018)   # un solo partido no cambia el empate

def test_dos_temporadas_en_la_misma_categoria():
    assert estimar([(2025, "benjamin", 20), (2026, "benjamin", 10)]) == (2017,)

def test_tres_temporadas_en_la_misma_categoria():
    # La primera la jugó con los mayores.
    assert estimar([(2024, "benjamin", 18), (2025, "benjamin", 20), (2026, "benjamin", 20)]) == (2017,)

def test_cambio_de_categoria():
    assert estimar([(2025, "prebenjamin", 18), (2026, "benjamin", 12)]) == (2018,)
    assert estimar([(2024, "prebenjamin", 15), (2025, "benjamin", 20), (2026, "benjamin", 9)]) == (2017,)

def test_dos_categorias_la_misma_temporada():
    # Prebenjamín toda la temporada y dos partidos con el benjamín: no basta para decidir.
    assert estimar([(2025, "prebenjamin", 20), (2025, "benjamin", 2)]) == (2018, 2019)
    # Con media temporada en el benjamín, sí: es de los mayores de prebenjamín.
    assert estimar([(2025, "prebenjamin", 20), (2025, "benjamin", 12)]) == (2018,)

def test_sin_observaciones():
    assert estimar([]) == ()
    assert estimar([(2026, "veteranos", 30)]) == ()

def test_el_orden_no_importa():
    obs = [(2024, "prebenjamin", 15), (2025, "benjamin", 20), (2026, "benjamin", 9)]
    assert estimar(obs) == estimar(list(reversed(obs)))
```

- [ ] **Step 2: Ejecutarlas y verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_nacimiento.py` — Expected: error de importación (`No module named 'nacimiento'`).

- [ ] **Step 3: Implementar `scripts/nacimiento.py`.** `estimar` suma, por cada año candidato, `peso × ln(verosimilitud)`, sobre los años desde `min(Y - mayor) - 2` hasta `max(Y - menor) + 4`; las observaciones de categoría desconocida se saltan. El peso de una observación es `max(0.2, min(1.0, partidos / PARTIDOS_PLENOS))` **dividido por el mayor de esos valores entre todas las observaciones** (la que más pesa, pesa 1: así una sola observación de un partido decide igual que una de veinte, y lo que se rebaja es la que tiene pocos partidos al lado de otra con muchos). Se quedan los candidatos cuya verosimilitud total es al menos la del mejor dividida por `RAZON` (con una tolerancia de `1e-9` en el logaritmo para los empates), como mucho los tres mejores, y se devuelven en orden creciente. Sin base, sin red y sin estado: función pura. Cabecera del módulo: qué estima y por qué (nadie publica la fecha), en el estilo de `scripts/identidad.py`.

- [ ] **Step 4: Ejecutar las pruebas.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_nacimiento.py` — Expected: `9 passed`.

- [ ] **Step 5: Commit.** `git add scripts/nacimiento.py scripts/tests/test_nacimiento.py && git commit` con el asunto «Año de nacimiento: el estimador por las categorías jugadas».

---

### Task 2: El índice del ranking

**Files:**
- Create: `scripts/ranking.py`
- Test: `scripts/tests/test_ranking.py`

**Interfaces:**
- Consumes: `nacimiento.VENTANA`.
- Produces:
  - `PRUDENCIA = 6` (partidos), `MIN_TEMPORADA = 3`, `MIN_TRAYECTORIA = 10`, `TOPE = 100`.
  - `nivel_fase(fase: str | None) -> float` — sobre la fase del grupo tal como está en `groups.phase`: «Segunda Fase A», «Segunda Fase A GC» → `1.30`; B → `1.15`; C → `1.05`; D → `1.00`; E → `0.95`; cualquier otra letra → `0.90`; lo que empieza por «Preferente» → `1.25`; «Copa de Campeones» o «Copa Campeones …» sin letra final → `1.25`, y con letra final (A-E), el valor de esa letra; todo lo demás (y `None`) → `1.0`. Sin distinguir mayúsculas ni tildes.
  - `factor_edad(anio: int, temporada: int, categoria: str) -> float` — con `e = anio - (temporada - mayor)` (cuántos años más joven que el mayor que admite la categoría): `e <= 0` → `1.0`; `1` → `1.10`; `2` → `1.25`; `3` o más → `1.40`.
  - `Fila = tuple[int, str, str | None, int, int, int]` — `(año de inicio de la temporada, categoría en minúsculas, fase, partidos, titular, goles)`.
  - `indice(filas: Iterable[Fila], anio: int, medias: Mapping[tuple[int, str], float]) -> int` — `round(100 × (GP + PRUDENCIA) / (PJ + PRUDENCIA))`, con `PJ` = suma de partidos de las filas que cuentan y `GP` = suma de `goles / medias[(temporada, categoría)] × nivel_fase(fase) × factor_edad(anio, temporada, categoría)`. Una fila cuya `(temporada, categoría)` no está en `medias`, o con media `0`, o de categoría que no está en `VENTANA`, no cuenta (ni sus partidos ni sus goles). Sin filas que cuenten: `0`.
  - `medias_de(filas_de_todos: Iterable[Fila]) -> dict[tuple[int, str], float]` — goles por partido (suma de goles entre suma de partidos) de cada `(temporada, categoría)`.

`100` es la media de la categoría: quien marca al ritmo medio, en una liga de nivel `1.0` y siendo de los mayores, tiene `100`.

- [ ] **Step 1: Escribir las pruebas que fallan** en `scripts/tests/test_ranking.py`:

```python
import pytest
from ranking import PRUDENCIA, factor_edad, indice, medias_de, nivel_fase

def test_nivel_fase():
    assert nivel_fase("Segunda Fase A") == 1.30 and nivel_fase("Segunda Fase A GC") == 1.30
    assert nivel_fase("Segunda Fase B") == 1.15 and nivel_fase("Segunda Fase C GC") == 1.05
    assert nivel_fase("Segunda Fase D GC") == 1.00 and nivel_fase("Segunda Fase E GC") == 0.95
    assert nivel_fase("Segunda Fase F") == 0.90
    assert nivel_fase("Segunda Fase GC") == 1.0            # sin letra (2023-24)
    assert nivel_fase("Preferente GC") == 1.25 and nivel_fase("Preferente Lanzarote") == 1.25
    assert nivel_fase("Copa de Campeones") == 1.25 and nivel_fase("Copa Campeones Benjamin B") == 1.15
    assert nivel_fase("Primera Fase GC") == 1.0 and nivel_fase("Eliminatorias") == 1.0
    assert nivel_fase(None) == 1.0 and nivel_fase("segunda fase a") == 1.30

def test_factor_edad():
    assert factor_edad(2017, 2026, "benjamin") == 1.0      # de los mayores
    assert factor_edad(2018, 2026, "benjamin") == 1.10     # de los pequeños
    assert factor_edad(2019, 2026, "benjamin") == 1.25     # juega con los mayores
    assert factor_edad(2020, 2026, "benjamin") == 1.40
    assert factor_edad(2016, 2026, "benjamin") == 1.0      # más viejo de lo que cabe: sin premio
    assert factor_edad(2010, 2026, "juvenil") == 1.25

MEDIAS = {(2026, "benjamin"): 0.5}

def test_indice_media_es_100():
    # 20 partidos y 10 goles con una media de 0,5: marca al ritmo medio.
    assert indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 10)], 2017, MEDIAS) == 100

def test_indice_premia_nivel_y_edad():
    base = indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert base == round(100 * (60 + PRUDENCIA) / 26) == 254
    assert indice([(2026, "benjamin", "Segunda Fase A", 20, 20, 30)], 2017, MEDIAS) == round(100 * (78 + 6) / 26) == 323
    assert indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2018, MEDIAS) == round(100 * (66 + 6) / 26) == 277

def test_pocos_partidos_no_gana():
    uno = indice([(2026, "benjamin", "Primera Fase GC", 1, 1, 3)], 2017, MEDIAS)      # 3 goles en 1 partido
    veinte = indice([(2026, "benjamin", "Primera Fase GC", 20, 20, 30)], 2017, MEDIAS)
    assert uno == round(100 * (6 + 6) / 7) == 171 and uno < veinte

def test_filas_que_no_cuentan():
    filas = [(2026, "benjamin", None, 10, 10, 5), (2025, "benjamin", None, 30, 30, 90), (2026, "veteranos", None, 9, 9, 9)]
    assert indice(filas, 2017, MEDIAS) == 100          # 2025 no tiene media y «veteranos» no es una categoría
    assert indice([], 2017, MEDIAS) == 0
    assert indice([(2026, "benjamin", None, 10, 10, 5)], 2017, {(2026, "benjamin"): 0}) == 0

def test_medias_de():
    filas = [(2026, "benjamin", None, 10, 10, 5), (2026, "benjamin", None, 30, 0, 5), (2025, "alevin", None, 4, 4, 0)]
    assert medias_de(filas) == {(2026, "benjamin"): pytest.approx(0.25), (2025, "alevin"): 0.0}
```

- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_ranking.py` — Expected: error de importación.

- [ ] **Step 3: Implementar `scripts/ranking.py`** (puro, sin base ni red). La cabecera explica la fórmula con las palabras de la decisión 2 del diseño.

- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_ranking.py` — Expected: `7 passed`.

- [ ] **Step 5: Commit.** Asunto: «Ranking: el índice (goles ponderados por partido, nivel de la liga y edad)».

---

### Task 3: El generador publica el año, el índice de búsqueda y el ranking

**Files:**
- Modify: `scripts/generate_js.py` (`JUGADORES_SHARDS`, `jugadores_files`, `write_jugadores`, `main`)
- Modify: `src/state.js` (`JUGADORES_SHARDS`, solo la constante y su comentario)
- Create: `scripts/anios_confirmados.json` (contenido: `{}` y un salto de línea)
- Modify: `scripts/tests/test_identidad.py` y `scripts/tests/test_jugador.mjs` (la tabla `TABLA_CLAVES`: la columna del trozo pasa a ser de 64)
- Test: `scripts/tests/test_jugadores_ampliacion.py` (nuevo); ampliar `scripts/tests/test_precache.py`

**Interfaces:**
- Consumes: `nacimiento.estimar`, `ranking.indice`, `ranking.medias_de`, `ranking.MIN_TEMPORADA`, `ranking.MIN_TRAYECTORIA`, `ranking.TOPE`.
- Produces (lo que leen las tareas 4, 5 y 6):
  - `JUGADORES_SHARDS = 64` en `generate_js.py` y en `src/state.js`. `identidad.trozo(clave, n)` no cambia.
  - Cada ficha de `data-jugadores-<k>.js` gana `"y": [2018]` o `"y": [2018, 2019]` (los años de `estimar`, en orden; sin la clave si `estimar` da `()`) y `"yc": 1` solo si el año es confirmado.
  - `anios_confirmados(path=None) -> dict[str, int]` — lee `scripts/anios_confirmados.json`, de forma `{"<clave>": {"anio": 2010, "fuente": "texto"}}`; un fichero que falta o vacío es `{}`. Si la clave de la ficha o uno de sus alias está, `"y": [anio]` y `"yc": 1`.
  - `buscar_files(conn) -> dict[str, str]` — `{"data-buscar-<xy>.js": "const BUSCAR_<XY> = [...];\n"}`. Cada entrada es `[clave, nombre, último equipo, última temporada, [años]]` (`[años]` es `"y"`, `[]` si no hay). `<xy>` son las dos primeras letras (a-z) de una palabra del nombre normalizado; una ficha va en el fichero de cada prefijo distinto de sus palabras. Normalizar: sin tildes (`ñ` → `n`), en minúsculas, lo que no es letra separa palabras; no cuentan las palabras de una letra ni las partículas `de`, `del`, `la`, `las`, `los`, `y`, `da`, `do`. `prefijos_de(nombre) -> list[str]` lo expone para las pruebas. Las entradas de cada fichero van por orden de clave (`_orden_clave`).
  - `ranking_files(conn) -> dict[str, str]` — `"data-ranking.js"`: `const RANKING = {"temporada": "2026-2027", "anios": {"2018": [n_temporada, n_trayectoria], ...}};` y, por cada año con alguna entrada, `"data-ranking-<año>.js"`: `const RANKING_<año> = {"t": [...], "h": [...]};`. Cada entrada: `[clave, nombre, equipo, categoría, partidos, titular, goles, índice, dudoso]` (`dudoso` es `1` si la ficha tiene más de un año posible, `0` si no). `"t"` es la temporada en curso (`seasons.is_current`; filas de esa temporada; al menos `MIN_TEMPORADA` partidos) y `"h"`, toda la trayectoria (al menos `MIN_TRAYECTORIA`); equipo y categoría, los de la fila más reciente de las que cuentan. Orden: índice de mayor a menor, después goles de mayor a menor, después `_orden_clave`. Como mucho `TOPE` por lista. Una ficha con dos años posibles sale en los dos ficheros, con el índice calculado para cada año.
  - `write_buscar(conn, root=None)` y `write_ranking(conn, root=None)`: escriben con `escribir_atomico` y **borran** los `data-buscar-*.js` y `data-ranking-*.js` del árbol que ya no salgan (como `write_lineups` con los suyos). `main()` los llama después de `write_jugadores`.

Las tres funciones parten de las mismas filas por ficha que hoy calcula `jugadores_files` (identidad, temporada, grupo, equipo, partidos, titular, goles, categoría, fase): sácalas a una función compartida para que la consulta grande se haga una vez por pasada cuando las llama `main()`, y cada `*_files(conn)` siga funcionando sola.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_jugadores_ampliacion.py`, sobre una base sintética en memoria (mira cómo la montan `scripts/tests/test_fichas_publicadas.py` y `_synth_conn` de `scripts/tests/test_pygen_fixes.py` y reutiliza su ayudante si sirve). Casos, con nombres inventados:
  - `test_anio_en_la_ficha`: un jugador con id `1001` y apariciones en benjamín 2025-26 y 2026-27 → su ficha lleva `"y": [2017]` y no lleva `"yc"`; otro con una sola temporada de benjamín 2026-27 → `"y": [2017, 2018]`.
  - `test_anio_confirmado_manda`: con `anios_confirmados` devolviendo `{"1001": 2016}` (pásalo por parámetro o con `monkeypatch`), `"y": [2016]` y `"yc": 1`; también si la clave confirmada es un alias de la ficha.
  - `test_sesenta_y_cuatro_trozos`: `jugadores_files` devuelve 64 ficheros `data-jugadores-0.js`…`data-jugadores-63.js` y la ficha `1001` está en el `1001 % 64 = 41`.
  - `test_prefijos_de`: `prefijos_de("GARCÍA PÉREZ, JOSÉ ÁNGEL") == ["ga", "pe", "jo", "an"]`; `prefijos_de("DE LA CRUZ O'NEILL, IÑAKI") == ["cr", "ne", "in"]`; `prefijos_de("A., X") == []`.
  - `test_buscar_files`: la ficha de «GOMEZ PEREZ, RAUL» está en `data-buscar-go.js`, `data-buscar-pe.js` y `data-buscar-ra.js`, con la entrada `["1001", "GOMEZ PEREZ, RAUL", <último equipo>, "2026-2027", [2017]]`, y cada fichero empieza por `const BUSCAR_GO = [` (el prefijo en mayúsculas).
  - `test_ranking_files`: con dos jugadores de 2017 (benjamín en 2025-26 y en 2026-27, con 10 partidos o más entre las dos y 3 o más en la segunda; uno con más goles), `data-ranking-2017.js` los trae en ese orden en `"t"` y `data-ranking.js` dice `"anios": {"2017": [2, 2]}` y `"temporada": "2026-2027"`; una ficha con menos de 3 partidos esta temporada no sale en `"t"`.
  - `test_dudoso_sale_en_sus_dos_anios`: el de una sola temporada (con goles y 10 partidos o más) sale en `data-ranking-2017.js` y en `data-ranking-2018.js` con `dudoso` `1`, y con índice mayor en el de 2018 (`factor_edad`).
  - `test_write_borra_los_que_sobran` (con `tmp_path`): un `data-buscar-zz.js` y un `data-ranking-1999.js` viejos desaparecen al escribir, y `data-ranking.js` no.
  - `test_base_real` (salta si no hay `futbolbase.db`; copia con `backup` a `tmp_path`): `jugadores_files`, `buscar_files` y `ranking_files` terminan; todas las fichas de la base real con filas de benjamín, prebenjamín o alevín tienen `"y"` con entre 1 y 3 años, y no más del 1 % con 3; ninguna clave se pierde respecto a 16 trozos (la unión de las claves `p` es la misma que antes: compárala con un cálculo independiente de `identidad.trozo(k, 64)`); el fichero de búsqueda más grande pesa menos de 400.000 bytes; hay ranking para cada año de 2011 a 2020.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_jugadores_ampliacion.py` — Expected: fallos de atributo (`buscar_files`…).
- [ ] **Step 3: Implementar** lo de «Produces». En `scripts/tests/test_identidad.py` y `scripts/tests/test_jugador.mjs`, la columna del trozo de `TABLA_CLAVES` se recalcula para 64 (y el comentario que dice «de 16»); `src/state.js` pasa a `JUGADORES_SHARDS = 64`.
- [ ] **Step 4: Precache.** Añade a `scripts/tests/test_precache.py` (junto a la comprobación de las actas, hacia la línea 83) que `data-buscar-go.js`, `data-ranking.js` y `data-ranking-2017.js` no entran en las entradas ni en las opcionales; si `scripts/precache.py` los metiera, corrígelo allí.
- [ ] **Step 5: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_jugadores_ampliacion.py scripts/tests/test_identidad.py scripts/tests/test_fichas_publicadas.py scripts/tests/test_precache.py scripts/tests/test_pygen_fixes.py && node --test scripts/tests/test_jugador.mjs scripts/tests/test_identidad_v2.mjs` — Expected: todo en verde.
- [ ] **Step 6: Medir y apuntar en el informe** (no en el repo): sobre una copia de la base real, segundos de `jugadores_files`, `buscar_files` y `ranking_files`, número de ficheros `data-buscar-*`, bytes del mayor y del total, y número de fichas con un año y con dos.
- [ ] **Step 7: Commit.** Asunto: «Fichas: el año de nacimiento, el índice de búsqueda y el ranking por año salen del generador».

---

### Task 4: La ficha dice el año y resume la trayectoria

**Files:**
- Modify: `src/screen-jugador.js`
- Modify: `acta.css` (solo si hace falta alguna regla nueva; antes mira `.traj-*`)
- Test: `scripts/tests/test_jugador.mjs`

**Interfaces:**
- Consumes: `player.y` (uno, dos o tres años, o ausente) y `player.yc` (tarea 3); `shard.g["<temporada>/<grupo>"][0]` (categoría en minúsculas) para saber la categoría de cada fila; `CAT_NAMES` de `src/model.js`; `routeHref` de `src/links.js`.
- Produces: `birthLabel(player) -> string` exportada: `''` sin `y`; `'Nacido en 2018'` con `yc`; `'Nacido en 2018 (estimado)'`; `'Nacido en 2018 o 2019 (estimado)'`; con tres, `'Nacido entre 2008 y 2010 (estimado)'`.

Qué cambia en pantalla, de arriba abajo:
1. El subtítulo de la cabecera empieza por `birthLabel(player)` cuando lo hay, seguido de lo de hoy (temporadas · partidos · goles).
2. Un bloque nuevo «Resumen», antes de «Trayectoria»: una fila por categoría en la que ha jugado, de la más alta a la más baja (juvenil, cadete, infantil, alevín, benjamín, prebenjamín), con nombre de la categoría, temporadas, partidos, goles y goles por partido con un decimal y coma («1,4»; sin partidos, «–»). Solo si la ficha tiene filas de más de un grupo; con un solo grupo no aporta nada y no se pinta. La categoría que el trozo no trae (`g` sin esa clave) va a una fila «Otras».
3. El título de cada temporada de «Trayectoria» lleva sus totales: «2025/26 · 22 partidos · 31 goles».
4. Con año, al final del bloque «Resumen» (o, si no se pinta, bajo la trayectoria) un enlace «Ver los mejores de 2018» a `#/ranking?y=2018` (con dos o tres años, un enlace por año). El enlace se construye con `routeHref('ranking', { y })`.
5. El contexto de «Trayectoria» sigue diciendo «según las actas de la federación».

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_jugador.mjs` (sigue el estilo de las que hay: `render` sobre un `ctx` con `datasets.jugadores`): `birthLabel` en sus cinco formas; el subtítulo empieza por «Nacido en 2018 (estimado)»; sin `y` no aparece «Nacido»; el bloque «Resumen» sale con dos categorías en el orden alevín, benjamín y con «1,5» para 30 goles en 20 partidos; no sale con un solo grupo; el título de temporada lleva «· 22 partidos · 31 goles»; el enlace `#/ranking?y=2018` está y, con dos años, están los dos.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_jugador.mjs` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar** en `src/screen-jugador.js`, con los ayudantes de `src/ui.js` que ya usa la pantalla (`block`, `box`, `countLabel`…).
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_jugador.mjs scripts/tests/test_rediseno_css.mjs scripts/tests/test_rediseno_contrast.mjs` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Ficha del jugador: año de nacimiento y resumen por categoría».

---

### Task 5: Explorar busca jugadores

**Files:**
- Modify: `src/state.js` (carga perezosa del índice), `src/model.js` (búsqueda), `src/screen-explorar.js`
- Test: `scripts/tests/test_rediseno_explorar.mjs`, `scripts/tests/test_rediseno_state.mjs`, `scripts/tests/test_rediseno_model_nombres.mjs` (o el que ya pruebe `searchKey`)

**Interfaces:**
- Consumes: `data-buscar-<xy>.js` (tarea 3).
- Produces:
  - `src/model.js`: `playerSearchPrefix(q) -> string | null` — el prefijo (dos letras a-z) de la primera palabra de `q` que cuenta, con la misma normalización que `prefijos_de` de Python (sin tildes, minúsculas, lo que no es letra separa, fuera las palabras de una letra y las partículas `de`, `del`, `la`, `las`, `los`, `y`, `da`, `do`); `null` si no hay ninguna de dos letras o más. `searchPlayers(entries, q, limit = 30) -> { total, list }` — `entries` son las del fichero; casa la entrada en la que **cada** palabra de `q` que cuenta es prefijo de alguna palabra del nombre; orden: última temporada de la más reciente a la más antigua y después nombre; `list` son como mucho `limit` objetos `{ id, name, team, season, years }`.
  - `src/state.js`: `ensureBuscar(prefix) -> Promise<Array | null>` — como `ensureJugadores`: un vuelo por prefijo, el texto parseado (nunca el global), `null` si falla (sin guardarlo, para reintentar). Un 404 es «ningún jugador con ese prefijo»: `[]`, no un fallo.
  - `src/screen-explorar.js`: `searchView(ctx, q)` añade, tras los equipos, el bloque «Jugadores»; `ctx.datasets.buscar` es `{ "<prefijo>": entradas | null }` (sin la clave: aún no pedido).

Comportamiento:
- La etiqueta del cuadro pasa a «Buscar un equipo o un jugador» y el aviso de menos de dos letras, a «Escribe al menos 2 letras del nombre del equipo o del jugador.».
- Los jugadores no dependen de la temporada elegida: se buscan en todas.
- Cada resultado enlaza a `playerHref(id)` y dice nombre (`playerName`), y debajo «último equipo · temporada · nacido en …» (con `birthLabel` sin la palabra «Nacido»: «2018 (estimado)»; nada si no hay año). Con más de `limit`, una línea «y N más: escribe más letras».
- Mientras el fichero del prefijo no ha llegado, el bloque «Jugadores» dice «Buscando jugadores…»; si falla (`null`), «No hemos podido cargar los jugadores.» y un botón «Reintentar» (`data-action="reintentar-jugadores"`); los equipos se siguen viendo en los tres casos.
- El vacío de hoy («No encontramos ningún equipo con…») solo sale si tampoco hay jugadores y el índice ya ha llegado; su texto pasa a «No encontramos ningún equipo ni ningún jugador con «…».» (sin la temporada, que no vale para los jugadores).
- La región de estado suma equipos y jugadores («3 equipos y 12 jugadores encontrados»).
- `needs` de la pantalla: con `q` en la dirección, pide el fichero de su prefijo (para el enlace directo, Atrás y la recarga). `mount`: al escribir, si el prefijo cambia y no está pedido, lo pide y, cuando llega, repinta la lista solo si el cuadro sigue teniendo el mismo texto (sin temporizadores, como hoy).

- [ ] **Step 1: Pruebas que fallan**: `playerSearchPrefix('  García ') === 'ga'`, `('de la Cruz') === 'cr'`, `('a') === null`, `("o'neill") === 'ne'`; `searchPlayers` con cuatro entradas inventadas: «garcia jo» encuentra «GARCÍA PÉREZ, JOSÉ» y no «GARCÍA, ANA»; el orden por temporada; `limit` y `total`; `ensureBuscar` (con `fetchData` falso, como las pruebas de `ensureJugadores` en `test_rediseno_state.mjs`): parsea, comparte el vuelo, `[]` con 404 y `null` con un fallo de red, que no se guarda; `searchView`: bloque «Jugadores» con el índice cargado, «Buscando jugadores…» sin la clave, el aviso y «Reintentar» con `null`, y en los tres los equipos siguen; el texto de la región de estado.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_rediseno_explorar.mjs scripts/tests/test_rediseno_state.mjs` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_rediseno_explorar.mjs scripts/tests/test_rediseno_state.mjs scripts/tests/test_rediseno_model_nombres.mjs scripts/tests/test_rediseno_router.mjs scripts/tests/test_rediseno_integracion.mjs` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Explorar: el buscador también encuentra jugadores».

---

### Task 6: Pantalla «Los mejores de cada año»

**Files:**
- Create: `src/screen-ranking.js`
- Modify: `src/screens.js`, `src/router.js` (ruta `ranking`, bajo Explorar, parámetros `y` y `v`), `src/state.js` (carga), `src/screen-explorar.js` (`moreBlock`), `acta.css`
- Test: `scripts/tests/test_rediseno_ranking.mjs` (nuevo), `scripts/tests/test_rediseno_router.mjs`, `scripts/tests/test_rediseno_explorar.mjs`

**Interfaces:**
- Consumes: `data-ranking.js` y `data-ranking-<año>.js` (tarea 3).
- Produces:
  - `src/state.js`: `ensureRanking() -> Promise<{temporada, anios} | null>` y `ensureRankingYear(year) -> Promise<{t, h} | null>` (mismo patrón que `ensureJugadores`).
  - Ruta `#/ranking?y=<año>&v=<t|h>`: `y` un año de cuatro cifras; `v` `t` (esta temporada, por defecto: no se escribe en la dirección) o `h` (toda la trayectoria). Sin `y`, o con un año que no está en `anios`, el más reciente que tenga entradas en la vista. Cambiar de año o de vista **sustituye** la entrada del historial (añade `ranking: ['y', 'v']` a `REPLACE_ONLY`). `ranking` entra en `UNDER_EXPLORE`.
  - `screen` con `id: 'ranking'`, `needs`, `render`, `title` («Los mejores de 2018»).

Qué se ve:
- Cabecera «Los mejores de 2018», con el subtítulo «Esta temporada» o «Toda su trayectoria».
- Una fila de años (enlaces, de más joven a más mayor; si no caben, se desplaza la fila, no la página; el elegido con `aria-current="true"`) y dos pestañas de vista (enlaces).
- La lista, numerada: puesto, nombre (`playerName`, enlace a la ficha), debajo «equipo · categoría», y a la derecha goles, partidos y el índice. A 320 px caben puesto, nombre y equipo, goles e índice; partidos y titularidades se ven desde 480 px. Un dudoso lleva tras el nombre la marca «2018 o 2019» en pequeño.
- Bajo la lista, un desplegable `<details>` «Cómo se calcula» con este texto exacto: «El índice compara los goles por partido de cada niño con la media de su categoría (100 es la media). Cuenta más marcar en una liga de más nivel y hacerlo siendo de los pequeños de la categoría o jugando con los mayores, y se corrige a quien ha jugado pocos partidos. Sale solo de las actas de la federación: no hay minutos, ni se sabe quién es portero o defensa, así que favorece a quien marca. El año de nacimiento es una estimación por las categorías en las que ha jugado; quien puede ser de dos años sale en los dos.»
- Sin datos del año: «Todavía no hay ningún jugador de 2018 con partidos suficientes.» Si el fichero falla: `errorBox('el ranking')`.
- En Explorar, «Más» gana, justo después de «Goleadores», la fila «Los mejores de cada año» con el contexto «por año de nacimiento».

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_rediseno_ranking.mjs`: la lista sale en el orden del fichero con sus puestos; el enlace de cada nombre es `#/jugador?id=<clave>`; el dudoso lleva su marca; la vista `h` pinta `"h"`; el año elegido tiene `aria-current`; sin `y` se elige el más reciente con entradas; un año sin entradas da el vacío; con el fichero a `null`, la caja de error; el texto de «Cómo se calcula»; `title`. En `test_rediseno_router.mjs`: `ranking` valida `y` y `v` y descarta lo demás. En `test_rediseno_explorar.mjs`: la fila nueva de «Más».
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_rediseno_ranking.mjs` — Expected: no encuentra el módulo.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/` — Expected: toda la suite de Node en verde (dura poco; si una prueba ajena falla ya en `main`, dilo en el informe en vez de tocarla).
- [ ] **Step 5: Commit.** Asunto: «Pantalla nueva: los mejores de cada año de nacimiento».

---

### Task 7: Documentar

**Files:**
- Create: `docs/ranking.md`
- Modify: `docs/identidad.md` (una sección corta «El año de nacimiento», que remite a `scripts/nacimiento.py`), `docs/decisiones.md` (tres líneas: el año se estima y nunca se enseña como dato; el ranking sale solo de las actas; el buscador de jugadores no depende de la temporada)

- [ ] **Step 1:** `docs/ranking.md`, para el dueño de la web, en lenguaje llano: qué mide, la fórmula con un ejemplo de números inventados, los valores de nivel y de edad en dos tablas, de dónde sale el año de nacimiento, cómo confirmar un año (`scripts/anios_confirmados.json`, con un ejemplo de clave inventada) y lo que el ranking no puede ver (minutos, porteros y defensas, goles que la federación publica sin nombre, partidos sin acta). Sin nombres reales.
- [ ] **Step 2:** Las dos modificaciones.
- [ ] **Step 3: Commit.** Asunto: «Documentación: el ranking y el año de nacimiento».
