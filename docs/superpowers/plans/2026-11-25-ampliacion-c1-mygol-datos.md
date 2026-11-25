# Ampliación, parte C1: la liga de escuelas de MyGol entra en la base — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bajar de la API de MyGol los torneos de escuela de 2022-23 a hoy (equipos, partidos y qué niños jugaron cada jornada; los de 2022-23 y 2023-24, con la categoría sin decidir, a `null` en la tabla de torneos), guardarlos como originales en el repositorio y meterlos en tablas propias de `futbolbase.db`, con una actualización semanal de la temporada en curso.

**Architecture:** Un descargador (`scripts/fetch_mygol.py`) que escribe un original por temporada (`scripts/mygol_<S>_raw.json`), con una tabla revisada a mano que dice de qué temporada y categoría es cada torneo (`scripts/mygol_torneos.json`). Un importador puro de red (`scripts/import_mygol.py`) que rehace las tablas `mygol_*` a partir de los originales y que el bot llama en cada pasada solo si un original ha cambiado. Un workflow semanal (`.github/workflows/mygol.yml`) que baja la temporada en curso y sube el original; la base la sigue escribiendo solo el bot.

**Tech Stack:** Python 3.11 de la biblioteca estándar (`urllib`, `json`, `sqlite3`), pytest 9.2.0, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md`, decisión 7. Lo medido de la API: `docs/ampliacion-mapa.md`, sección 5. Enlazar los niños de MyGol con las fichas de la federación y enseñarlo en la web **no** es de este plan (parte C2, cuando la parte B esté publicada).

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-mygol`, rama `mygol`. No se toca v1 (`/home/manolo/claude/futbol-base`) ni los otros árboles.
- La única red permitida es `https://tusligascanarias.mygol.es/api`. Nunca fiflp.com. Cabeceras: un `User-Agent` de navegador y `Accept: application/json`; **nunca** un correo ni nada que identifique al dueño.
- Cortesía con MyGol: una petición cada 2 segundos como mínimo, de una en una, y parar tras 5 fallos seguidos guardando lo ya bajado. Ninguna tarea de este plan lanza la descarga completa: en las pruebas a mano, como mucho 12 peticiones.
- Ningún nombre real de niño en código, pruebas, fixtures, documentos ni commits. Los originales (`scripts/mygol_*_raw.json`) sí llevan los nombres reales, como los de las actas: son datos, no pruebas.
- La base (`futbolbase.db`) solo la escribe el bot (`update.yml`, `activar.yml`). El workflow nuevo sube originales, nunca la base ni `data-*.js`.
- Un fallo de MyGol o de su importación **nunca** deja al bot sin publicar: la llamada desde la pasada va protegida y, si falla, se dice en el registro y la pasada sigue.
- No se hace `git push` ni `git stash`, ni se ejecutan `scripts/publicar.py` ni `scripts/generate_js.py`.
- Ficheros escritos con `escritura.escribir_atomico`. Estilo del fichero más parecido que ya exista (comentarios en español que explican el porqué).
- Cada commit acaba con `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.

## Review Focus

- La API **corta a medias** (fallos seguidos, o el proceso muere): lo bajado queda guardado y la siguiente ejecución sigue por donde iba, sin volver a pedir lo que ya tiene. Prueba en la tarea 1 (`test_reanuda_sin_repetir`, `test_para_tras_cinco_fallos`).
- Un torneo **que no está en la tabla** de torneos (uno nuevo de la temporada que viene, o uno de adultos): no se baja ni se importa, y el descargador lo dice. Prueba en la tarea 1 (`test_torneo_fuera_de_la_tabla`).
- Importar **dos veces** el mismo original deja la base igual; importar uno que ha perdido un partido lo quita de la base. Prueba en la tarea 2 (`test_idempotente`, `test_refleja_lo_que_desaparece`).
- El importador **revienta** dentro de la pasada del bot: la pasada sigue y la base queda como estaba. Prueba en la tarea 3 (`test_un_fallo_no_para_la_pasada`).
- Un niño con el **nombre o los apellidos vacíos**, con espacios de más o en minúsculas: entra, y su nombre normalizado es el de `identidad.normalizar` sobre «APELLIDOS, NOMBRE». Prueba en la tarea 2 (`test_nombres_raros`).

---

### Task 1: El descargador y la tabla de torneos

**Files:**
- Create: `scripts/fetch_mygol.py`
- Create: `scripts/mygol_torneos.json`
- Create: `scripts/tests/test_fetch_mygol.py`, `scripts/tests/fixtures/mygol/` (respuestas de ejemplo **anonimizadas**)

**Interfaces:**
- Produces:
  - `scripts/mygol_torneos.json`: `{"<id de torneo>": {"temporada": "2025-2026", "categoria": "miniprebenjamin" | "prebenjamin" | "benjamin" | "alevin", "nombre": "texto"}}`. Solo los torneos de escuela.
  - `scripts/mygol_<S>_raw.json` (un fichero por temporada, `<S>` como `2025-2026`):
    ```json
    {"temporada": "2025-2026",
     "torneos": {"85": {"categoria": "miniprebenjamin", "nombre": "…",
       "equipos": {"1159": "NOMBRE DEL EQUIPO"},
       "partidos": {"13088": {"jornada": "Jornada 1", "fecha": "2025-11-08T11:00:00", "estado": 5,
                              "local": 1148, "visitante": 1160, "campo": "…",
                              "jugadores": {"1148": [[10284, "Nombre", "Apellidos", 1]], "1160": []},
                              "leido": "2026-11-25"}}}}}
    ```
    `jugadores` es, por equipo, `[id del jugador, nombre, apellidos, 1 si jugó esa jornada o 0]`, en orden de id. Un partido sin leer todavía no lleva `jugadores` ni `leido`. Las claves de `torneos`, `equipos` y `partidos` se escriben en orden numérico, para que el fichero no baile de una ejecución a otra.
  - `fetch_mygol.py`:
    - `BASE = "https://tusligascanarias.mygol.es/api"`, `PAUSA = 2.0`, `MAX_FALLOS = 5`.
    - `class Api` con `get(path) -> object` (JSON; respeta `PAUSA` entre el inicio de dos peticiones; reintenta 2 veces un fallo de red o un 5xx; un 4xx es `ApiError` sin reintento) y un contador de peticiones. Se le puede pasar `abrir=` (la función que hace la petición) y `dormir=` para las pruebas.
    - `partidos_del_torneo(jornadas_json) -> dict[int, dict]` (de `/matches/fortournament/<id>` a las entradas de `partidos` sin `jugadores`).
    - `jugadores_del_partido(partido_json) -> tuple[dict[str, list], dict[str, str]]` (de `/matches/<id>`: los `jugadores` por equipo y los nombres de los dos equipos). `jugó` es `1` si `dayResultSummary.gamesPlayed >= 1`.
    - `pendientes(torneo, hoy) -> list[int]` — los partidos que hay que pedir: sin `leido`, o con fecha en los últimos 21 días o en el futuro (cambian), en orden de id. Un partido ya leído con fecha de hace más de 21 días no se vuelve a pedir.
    - `descargar(temporadas, api, hoy, raiz=None, max_peticiones=None, registro=print) -> dict` — por cada torneo de la tabla de esas temporadas: su lista de partidos, y después cada pendiente; guarda el original de la temporada cada 25 partidos leídos y al acabar; devuelve `{"peticiones": n, "leidos": n, "pendientes": n, "fallos": n}`.
    - CLI: `python3 scripts/fetch_mygol.py --temporadas 2022-2023,2023-2024` | `--en-curso` (la de `mygol_torneos.json` más reciente) | `--todas`, con `--max-peticiones N`. Sale con 0 aunque queden pendientes (lo dice); con 1 solo si no pudo leer nada.
    - `descubrir(api, hasta) -> list[dict]` y `--descubrir`: recorre `/matches/fortournament/<id>` de 1 a `hasta` y lista, de cada torneo con partidos, id, partidos, equipos, cuántos tienen marcador y fechas; no escribe nada. Sirve para ver los torneos nuevos de una temporada.

- [ ] **Step 1: Fixtures anonimizadas.** En `/tmp/claude-1000/-home-manolo/5edae910-4f7b-4c95-a191-b24f0179e06c/scratchpad/mygol/` hay respuestas reales de la API (`tournaments.json`, `tournaments_96.json`, `matches_fortournament_96.json`, `matches_14750.json`, `matches_5004.json`) y `NOTAS.md` con lo medido. Recórtalas (dos jornadas, y de cada partido lo que usa el código) y **cambia todos los nombres y apellidos de personas** por inventados («Nombre12», «Apellido12 Apellido13») antes de copiarlas a `scripts/tests/fixtures/mygol/`. Comprueba con un `grep` que ningún nombre real ha pasado.
- [ ] **Step 2: Pruebas que fallan** en `scripts/tests/test_fetch_mygol.py`, con una `Api` de mentira que sirve las fixtures y cuenta peticiones:
  - `test_partidos_del_torneo`: ids, jornada, fecha, estado, local, visitante y campo de la fixture.
  - `test_jugadores_del_partido`: los dos equipos con sus jugadores en orden de id, `jugó` según `gamesPlayed`, y un jugador sin `dayResultSummary` es `0`.
  - `test_pausa_entre_peticiones`: con `dormir` falso, dos `get` seguidos duermen lo que falte hasta `PAUSA`.
  - `test_reintentos_y_4xx`: un 503 se reintenta dos veces; un 400 lanza `ApiError` a la primera.
  - `test_reanuda_sin_repetir`: con un original a medias en `tmp_path`, `descargar` solo pide los pendientes.
  - `test_pendientes_por_fecha`: un partido leído de hace 30 días no se pide; uno de hace 5, sí; uno futuro, sí.
  - `test_para_tras_cinco_fallos`: con la API fallando siempre, `descargar` para tras `MAX_FALLOS` fallos seguidos y el original conserva lo que tenía.
  - `test_torneo_fuera_de_la_tabla`: un torneo que no está en `mygol_torneos.json` no se pide.
  - `test_max_peticiones`: se corta al llegar y guarda.
  - `test_original_estable`: escribir dos veces el mismo contenido da los mismos bytes (claves en orden numérico, `ensure_ascii=False`, salto de línea final).
- [ ] **Step 3: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fetch_mygol.py` — Expected: error de importación.
- [ ] **Step 4: Implementar `scripts/fetch_mygol.py`.**
- [ ] **Step 5: La tabla de torneos.** Lo que se sabe seguro: 2025-26: 85 miniprebenjamín, 87 prebenjamín; 2026-27: 95 prebenjamín, 96 benjamín, 97 miniprebenjamín, 101 alevín. Faltan por decidir 86 y 88 (2025-26), 66, 67 y 68 (2024-25), 51, 52 y 53 (2023-24) y 32, 33 y 34 (2022-23). Decídelos con pruebas, con **como mucho 12 peticiones** a la API en total: lee un partido de cada torneo dudoso y cruza sus niños con los de los torneos conocidos (por nombre y apellidos: el id de jugador es propio de cada temporada, como se vio al hacerlo): un niño de miniprebenjamín pasa a prebenjamín a los dos años, y así. Escribe `scripts/mygol_torneos.json` con los 17 torneos y deja en el informe, por cada torneo dudoso, la prueba en la que te apoyas (cuántos niños coinciden con qué torneo) y lo seguro que estás. Si alguno no se puede decidir con 12 peticiones, déjalo fuera de la tabla y dilo.
- [ ] **Step 6: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fetch_mygol.py` — Expected: `10 passed`.
- [ ] **Step 7: Commit.** Asunto: «MyGol: el descargador de la liga de escuelas y la tabla de torneos».

---

### Task 2: Las tablas y el importador

**Files:**
- Create: `scripts/import_mygol.py`
- Create: `scripts/tests/test_import_mygol.py`
- Modify: `scripts/reconstruir.py` y `docs/reconstruccion.md` (un dominio más, `mygol`), y la prueba que lista los dominios

**Interfaces:**
- Consumes: los originales `scripts/mygol_<S>_raw.json` (tarea 1) e `identidad.normalizar`.
- Produces:
  - Tablas (creadas con `CREATE TABLE IF NOT EXISTS` por `import_mygol.crear_tablas(conn)`):
    ```sql
    mygol_torneos(id INTEGER PRIMARY KEY, temporada TEXT NOT NULL, categoria TEXT NOT NULL, nombre TEXT NOT NULL)
    mygol_equipos(id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)
    mygol_jugadores(id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, apellidos TEXT NOT NULL, norm TEXT NOT NULL)
    mygol_partidos(id INTEGER PRIMARY KEY, torneo_id INTEGER NOT NULL, jornada TEXT, fecha TEXT, estado INTEGER,
                   local_id INTEGER, visitante_id INTEGER, campo TEXT)
    mygol_participaciones(partido_id INTEGER NOT NULL, jugador_id INTEGER NOT NULL, equipo_id INTEGER NOT NULL,
                          jugo INTEGER NOT NULL, PRIMARY KEY (partido_id, jugador_id)) WITHOUT ROWID
    ```
    y el índice `idx_mygol_participaciones_jugador` sobre `(jugador_id)`. `norm` es `identidad.normalizar("<apellidos>, <nombre>")` (solo `identidad.normalizar("<nombre>")` si no hay apellidos).
  - `mygol_jugadores.id` es el id de MyGol, propio de cada temporada: el mismo niño tiene una fila por temporada. Cruzarlos entre temporadas (por `norm`) es de la parte C2.
  - `raws(raiz=None) -> list[Path]` — los `scripts/mygol_*_raw.json` que existan, en orden.
  - `importar(conn, rutas=None) -> dict` — rehace **enteras** las cinco tablas con lo que digan los originales, en una transacción (si algo falla, la base queda como estaba), y devuelve los recuentos por tabla. El nombre de un jugador o de un equipo que cambia entre originales: el del original de la temporada más reciente.
  - `huella(rutas) -> str` (sha1 del contenido de todos, en orden) y `importar_si_cambia(conn, raiz=None, registro=print) -> bool` — compara con la huella guardada en `raw_imports` (mira cómo la usan `import_fiflp_actas.import_changed_raws` y compañía y haz lo mismo, con la clave `mygol`); importa y guarda la huella solo si cambia; `True` si importó.
  - En `scripts/reconstruir.py`, el dominio `mygol`: se rehace desde los originales y sale igual.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_import_mygol.py` (base en memoria; originales inventados escritos en `tmp_path`): `test_importa` (recuentos y una fila de cada tabla), `test_nombres_raros` (apellidos vacíos, espacios de más, minúsculas con tildes: `norm` esperado escrito a mano), `test_idempotente` (dos veces: mismas filas), `test_refleja_lo_que_desaparece` (un partido que ya no está en el original deja de estar en la base, con sus participaciones), `test_nombre_mas_reciente`, `test_transaccion` (un original con un partido mal formado: `importar` lanza y las tablas siguen como estaban), `test_importar_si_cambia` (la segunda vez no importa; al cambiar un byte, sí), `test_sin_originales` (no falla y deja las tablas vacías).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_import_mygol.py` — Expected: error de importación.
- [ ] **Step 3: Implementar `scripts/import_mygol.py`.**
- [ ] **Step 4: El dominio `mygol` de `reconstruir.py`**, con su línea en las dos tablas de `docs/reconstruccion.md` («Sí, comprobado») y en la prueba que enumera los dominios.
- [ ] **Step 5: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_import_mygol.py scripts/tests/test_reconstruir.py scripts/tests/test_db_sanity.py scripts/tests/test_base_sana.py` — Expected: en verde (las pruebas sobre la base real siguen pasando con las tablas nuevas vacías o ausentes).
- [ ] **Step 6: Commit.** Asunto: «MyGol: tablas e importador de la liga de escuelas».

---

### Task 3: La pasada del bot importa lo que cambie, y un workflow semanal baja la temporada en curso

**Files:**
- Modify: `scripts/fetch_futbolaspalmas.py` (la llamada protegida, después de `import_past_seasons`)
- Create: `.github/workflows/mygol.yml`
- Create: `docs/mygol.md`
- Modify: `scripts/tests/` (la prueba de la llamada protegida y la que comprueba los workflows: mira `test_workflows*.py` o la que valide `concurrency` y los permisos, y añade el nuevo)

**Interfaces:**
- Consumes: `import_mygol.importar_si_cambia`, `fetch_mygol.py --en-curso`.
- Produces:
  - En la pasada (`fetch_futbolaspalmas.py`, donde hoy se llama a `import_past_seasons`): después de ella, `import_mygol.importar_si_cambia(conn)` dentro de un `try` que, ante cualquier excepción, hace `rollback`, escribe en el registro `  ! MyGol: <error>` y sigue.
  - `.github/workflows/mygol.yml`: `workflow_dispatch` (entradas `temporadas`, vacía = la temporada en curso, y `max_peticiones`, por defecto `2000`) y `schedule` semanal (lunes 04:17 UTC); `permissions: contents: write`; `concurrency: { group: descargas-manuales, cancel-in-progress: false }` (el grupo de `discover-fiflp.yml` y `fetch-fiflp-islas.yml`); `timeout-minutes: 120`; pasos: checkout, Python 3.11, `python3 scripts/fetch_mygol.py …`, y subir **solo** `scripts/mygol_*_raw.json` si cambian, rebasando sobre `main` y reintentando como hace `fetch-fiflp-islas.yml`. No instala Playwright ni toca la base.
  - `docs/mygol.md`: qué es, qué se baja y qué no (sin marcadores ni goles, sin fecha de nacimiento, desde 2022-23), la tabla de torneos y cómo añadir los de una temporada nueva (`--descubrir`), las tablas de la base con una consulta de ejemplo, la cortesía con la API y cómo lanzar el workflow a mano.

- [ ] **Step 1: Pruebas que fallan**: `test_un_fallo_no_para_la_pasada` (con `import_mygol.importar_si_cambia` sustituida por una que lanza, la función de la pasada que la envuelve no propaga y deja escrito el aviso; si la llamada está en línea dentro de una función larga, sácala a una función pequeña `importar_mygol(conn, registro=print)` en `fetch_futbolaspalmas.py` y prueba esa) y la comprobación del workflow nuevo (grupo de concurrencia, que no hace `git add` de `futbolbase.db` ni de `data-*.js`, y que no pide fiflp.com).
- [ ] **Step 2: Verlas fallar.**
- [ ] **Step 3: Implementar** la llamada protegida, el workflow y el documento.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ -k "mygol or workflow or pasada"` y después la suite entera de Python (`python3 -m pytest -q -p no:cacheprovider scripts/tests`, unos 9 minutos) — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «MyGol: la pasada importa los originales que cambian y un workflow semanal los baja».
