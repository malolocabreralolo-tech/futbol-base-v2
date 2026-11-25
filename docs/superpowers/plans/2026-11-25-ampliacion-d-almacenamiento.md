# Ampliación, parte D: la base en piezas y Pages solo con la web — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la base pueda crecer de 41 MB a más de 200 MB sin que el bot se pare: en git va partida en una pieza común y una por temporada (todas muy por debajo de los 100 MB que admite GitHub), GitHub Pages publica solo la web (una rama `web` derivada de `main`) y la base completa se descarga desde un fichero diario fuera de git y de Pages.

**Architecture:** Un módulo de la biblioteca estándar, `scripts/piezas.py`, **monta** `futbolbase.db` a partir de `base/` (la pieza `comun.db`, una `actas-<temporada>.db` por temporada y el manifiesto `piezas.json`) y la **parte** al acabar aplicando a cada pieza solo las filas que cambian, en sitio; antes de subir, **verifica** que las piezas vueltas a montar dan las mismas filas. Para todo el código la base sigue siendo una, con el mismo esquema. La transición va en tres fases publicables por separado (sombra, cambio de fuente de verdad, `futbolbase.db` fuera de git); entre medias, la copia del PC aprende a montar la de v2, el bot sube cada día un ZIP de la base a una release fija y pone al día la rama `web`, y el director cambia el origen de Pages.

**Tech Stack:** Python 3.11 en el bot y 3.12 en `tests.yml` (sqlite3 de la biblioteca estándar, pytest 9.2.0), bash de GitHub Actions, órdenes de bajo nivel de git (`ls-tree`, `update-index`, `write-tree`, `commit-tree`), `gh` (release y API de Pages), módulos ES de `src/` con `node --test`; esbuild solo al publicar (`scripts/publicar.py`, que no ejecuta ninguna tarea).

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (parte D, decisión 6). Contexto: `docs/ampliacion-mapa.md`, `docs/reconstruccion.md`, `docs/decisiones.md`, `docs/SP-1-actas.md`, `pc/copia/README.md`.

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-almacen`, rama `almacen`. Ni `/home/manolo/claude/futbol-base` (v1) ni `/home/manolo/claude/futbol-base-v2` se tocan.
- Nunca una petición a fiflp.com (ni a ninguna web salvo lo que diga un PASO DEL DIRECTOR). No se lanzan workflows (`gh workflow run`), ni se hace `git push`, ni `git stash`, ni se ejecutan `scripts/publicar.py` o `scripts/generate_js.py` sobre el árbol.
- La base del árbol (`futbolbase.db`) no se modifica: las pruebas trabajan sobre copias en `tmp_path`, y la real se abre en solo lectura. La base solo la escriben `update.yml` y `activar.yml`, los dos en el grupo `update-data`.
- Ningún nombre real de niño en código, pruebas, documentos ni mensajes de commit: nombres inventados («GOMEZ PEREZ, RAUL») o claves.
- v1 no se toca, tampoco su parte de la copia del PC: la entrada `v1` de `pc/copia/origenes.json` y su camino por el código salen iguales byte a byte.
- `scripts/piezas.py` solo importa la biblioteca estándar en el módulo (la copia del PC lo instala tal cual); lo demás (`source_health`), dentro de `main`. Sin dependencias nuevas en ningún fichero.
- Límites, en MiB (`MB = 1024 * 1024`, como `source_health`): GitHub, 100 por fichero (aviso desde 80, no se sube desde 95); Pages, 1024 por sitio (la rama `web` no se publica desde 950).
- Cada tarea, publicada sola, deja `main` funcionando: el bot sigue publicando con el mismo ritmo y lo de los equipos del dueño no llega más tarde.
- Estilo: el del fichero que se toca (comentarios en español que explican el porqué, frases cortas, sin jerga). Los workflows llevan sobre cada paso nuevo el comentario de por qué está ahí, como los de hoy.
- Cada commit acaba con las dos líneas `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.
- Lo marcado **PASO DEL DIRECTOR** no lo hace el implementador: lo deja escrito y se para.

## Review Focus

- **Un programa que abre la base sin montarla** (un paso que se adelanta al montaje, un workflow que no monta, una orden a mano): `sqlite3.connect` crea un fichero vacío, `init_db` le pone tablas, `base_sana` lo da por bueno y la web saldría vacía. Se espera un error que diga «monta la base». Prueba en la tarea 7 (`test_get_connection_no_crea_la_base_sin_montar`) y, para el orden de los pasos, en la 3 (`test_montar_va_antes_que_todo_lo_que_lee_la_base`).
- **Las pruebas sobre la base real se saltan en silencio** cuando falta `futbolbase.db` (`pytest.skip("futbolbase.db not present")` en una docena de ficheros): en GitHub, sin montar, la suite saldría verde sin haber mirado la base. En CI se espera un fallo. Prueba en la tarea 7 (`test_en_ci_la_base_tiene_que_estar_montada`).
- **Un `-wal` o un `-shm` viejos junto al destino al montar** (una sesión local que dejó la base abierta): una base nueva con el WAL de otra es una base rota. Se espera que montar se niegue si el `-wal` tiene datos y lo quite si está vacío. Prueba en la tarea 1 (`test_montar_no_hereda_un_wal_viejo`).
- **Los identificadores AUTOINCREMENT** (`matches`, `groups`, `teams`, `standings`, `goals`, `scorers`, `seasons`, `categories`): si al montar se pierde `sqlite_sequence`, un partido nuevo reutilizaría el id de uno borrado. Se espera el mismo `sqlite_sequence` que la base de partida. Prueba en la tarea 1 (`test_autoincremento_no_reutiliza_ids`).
- **Un fichero que el service worker necesita y no está en la rama `web`** (o falta `.nojekyll`, y Pages pasaría la web por Jekyll): el SW no se instalaría en ningún móvil. Se espera que la rama no se publique. Prueba en la tarea 6 (`test_arbol_web_del_repositorio` y `test_falta_uno_del_precache_y_no_se_publica`).

## Lo medido (25/11/2026, sobre una copia de la base en un directorio temporal)

| Qué | Hoy | Con ×7 actas (estimado) |
|---|---|---|
| `comun.db` (todo salvo las filas de las tres tablas pesadas, con todos sus índices) | 11,1 MB | 45-60 MB (`matches` ×3,5, `players` ×6, `scorers` ×4, tablas de MyGol de la parte C ~5 MB) |
| `actas-<S>.db` (las tres tablas de una temporada, sin índices secundarios) | de 1,2 (2020-21) a 4,0 MB (2025-26); 2023-24, 3,9 | 25-30 MB la mayor |
| Todas las piezas | 33,4 MB | 250-300 MB |
| `futbolbase.db` montada | 45 MB (41 la de git: los índices se rellenan sin ordenar) | ~280 MB |
| Partir desde cero / montar / detectar cambios (EXCEPT en las 8 temporadas) / huella de todas las tablas | 1,8 s / 2,6 s / 2,7 s / 3,6 s por base | ~13 s / ~20 s / ~20 s / ~25 s |
| Delta en git de una pieza cambiada en sitio (20 actas nuevas en la de 2026-27) | 1,8 KB (la pieza: 1,6 MB, 470 KB comprimida) | — |
| ZIP de la base (deflate 6) | 2,8 s, 13,3 MB (xz: 32 s, 7,7 MB) | ~20 s, ~85 MB |
| Rama `web` (lo de la web dentro de `main`) | 81 MB, unos 855 ficheros | ~520 MB (`data-lineups-*` ×7) |
| Pages «legacy» hoy, con todo `main` (287 MB en git) | 44-49 s por despliegue (checkout 12 s, subida 6 s, despliegue 8 s; últimos 5) | — |
| `generate_js.write_lineups` | 8,9 s (346 ficheros, 66 MB; las temporadas cerradas son el 93 %) | ~60 s |

## Quién lee la base

| Sitio | Qué hace con ella | Tarea |
|---|---|---|
| `update.yml:49-52` (checkout), `:96` (`fetch_futbolaspalmas.py`, `db.DB_PATH`), `:104` (`base_sana.py --salud`), `:113`/`:118` (suites), `:131-136` (`git add futbolbase.db`), `:175` (diagnóstico) | La pasada la lee, la escribe y la sube | 2, 3, 5, 6, 7 |
| `activar.yml:57-58` (`activar_auto.py --pendientes/--temporada`: `--temporada` abre la base), `:138`, `:158`, `:165`, `:170`, `:183` (`git add futbolbase.db`), `:208` (`git checkout HEAD -- futbolbase.db`), `:211` (`--pruebas-fallaron`, abre la base) | La activación la lee, la escribe y la sube | 2, 3, 6, 7 |
| `tests.yml`, job `pytest` (`:90`, `:94`, `:100` `test_reconstruir.py`) | Las pruebas sobre la base real: `test_db_sanity.py:23`, `test_data_integrity.py:17`, `test_acta_reconciler.py:12`, `test_import_fiflp_actas.py:13`, `test_pygen_fixes.py:29`, `test_score_deviation.py:108`, `test_categorias.py:138`, `test_fiflp_grupos.py:554`, `test_nombres_alevin.py:451`, `test_reconstruir.py:262` (todas esperan `futbolbase.db` en la raíz y se saltan sin ella) | 2, 3, 7 |
| `tests.yml`, jobs `node-tests`, `render-smoke`, `aislamiento-smoke`, `pc-tests` | No la leen (los smokes, solo `data-*.js`; `pc-tests`, repositorios de mentira) | — |
| `detalle-federacion.yml:62` → `fetch_fiflp_detalle.py:40,235-240` (`venue_codes`: códigos de `venues`; sin base, se los salta **en silencio**) | Solo lee la parte común | 7 |
| `freno-fiflp.yml:43` → `freno_experimento.py:33` (`sqlite3.connect`: sin base, crea una vacía y falla) | Solo lee la parte común (`groups`, `seasons`) | 7 |
| `actas-federacion.yml`, `goleadores-federacion.yml`, `discover-fiflp.yml`, `fetch-fiflp-islas.yml`, `probe-fiflp.yml`, `reloj.yml` | No la leen | — |
| `scripts/reconstruir.py:762` (`--db`, por defecto la de la raíz) y `:263` (la copia) | Lee la de la raíz: con «montar» antes, sigue igual | 3 (en `tests.yml`) |
| Órdenes a mano que abren la de la raíz: `activate_season.py`, `fiflp_manifest.py:251`, `medir_identidad.py:224`, `migrate_identidad.py`, `synth_copa_campeones.py:112`, `import_*.py` (CLI), `migrate_actas_schema.py:152` | Desde la fase 3, montar antes y partir después | 7 (documentos y la guarda de `db.get_connection`) |
| `pc/copia/origenes.json:7-11` (`v2`), `copia/fuentes.py:80-81` (`extraer_base`), `copia/ejecutar.py:95` | Saca `futbolbase.db` del espejo | 4 |
| `src/screen-fuentes.js:133` (`href="./futbolbase.db"`), `scripts/generate_js.py:616-617` (`COBERTURA.mb`) | El enlace de descarga y su tamaño | 5 |

## Orden de publicación

| Tarea | `main` después | PASO DEL DIRECTOR | Vuelta atrás |
|---|---|---|---|
| 1. `scripts/piezas.py` | Igual; un módulo y sus pruebas | Ninguno | `git revert` |
| 2. Sombra | El bot y la activación parten y verifican en cada subida, sin bloquear; `base/` entra en git; la fuente de verdad sigue siendo `futbolbase.db` | Publicar; mirar 12 pasadas | `git revert` (las piezas se quedan, sin uso) |
| 3. Cambio de fuente de verdad | La pasada monta de `base/` y para si no es igual a `futbolbase.db`; parte y verifica bloqueando; sube las dos | Publicar con el bot parado | `git revert` del commit, con el bot parado |
| 4. Copia del PC | Igual (el PC usa `futbolbase.db` mientras exista y, si no, monta) | Instalar en el PC | Reinstalar la versión anterior |
| 5. Descarga diaria | El bot sube un ZIP al día a la release `base-completa`; «Datos y fuentes» enlaza ahí | Crear la release; publicar la web | `git revert`; el enlace vuelve a `./futbolbase.db` |
| 6. Rama `web` | El bot, la activación y `web.yml` ponen al día la rama `web` | Publicar; cambiar Pages a `web` | Pages otra vez a `main` |
| 7. `futbolbase.db` fuera de git | Solo `base/`; todos montan | Publicar con el bot parado | `git revert` y volver a subir la base montada |
| — `write_lineups` incremental | Plan aparte (abajo) | — | — |

**Lo de no rehacer `data-lineups` (punto 6 del encargo) va a un plan aparte.** Hoy son 8,9 s por pasada y con ×7 serán ~60 s de un job de 40 min: no es urgente. Y la llave para saltarse una temporada no puede ser solo su pieza: cada `data-lineups` lleva la clave de ficha de cada niño (`claves_de_ficha`, que el resolvedor de identidad cambia en temporadas cerradas cuando une dos identidades), los nombres de los equipos (que se renombran) y los marcadores de `matches`, todo en la pieza común. Una llave incompleta dejaría enlaces a fichas rotos en actas viejas sin que nada falle. Se planifica cuando E y F hayan llenado la base, con la medida de entonces.

---

### Task 1: Montar, partir y verificar (`scripts/piezas.py`)

**Files:**
- Create: `scripts/piezas.py`, `docs/almacenamiento.md`
- Test: `scripts/tests/test_piezas.py`, `scripts/tests/test_piezas_real.py`

**Formato de `base/`** (lo fija esta tarea y lo describe `docs/almacenamiento.md`):
- `base/comun.db`: SQLite en modo de diario `DELETE` (nunca WAL: git solo sube el fichero), con el esquema entero de la base (tablas, índices, la vista `match_staff`), el mismo `page_size`, `auto_vacuum`, `encoding`, `user_version` y `application_id`, todas las filas de todas las tablas salvo las de `appearances`, `match_events` y `match_staff_all` (vacías, con sus índices), y su `sqlite_sequence` igual al de la base.
- `base/actas-<AAAA-AAAA>.db`: SQLite en modo `DELETE` con solo esas tres tablas (el `CREATE TABLE` de la base, letra a letra, sin índices secundarios) y sus filas de los partidos de esa temporada (`matches.group_id → groups.season_id → seasons.name`). Una temporada sin filas no tiene pieza.
- Cada fila conserva su **identidad**: en una tabla `WITHOUT ROWID`, su clave primaria; en una con `INTEGER PRIMARY KEY`, esa columna; en las demás (`match_staff_all`, `fp_goals`, `venues`, `raw_imports`…), su `rowid`, que se copia explícito. Montar da la base con los mismos `rowid`.
- `base/piezas.json`: `{"formato": 1, "piezas": {"<fichero>": {"bytes": <int>, "filas": {"<tabla>": <int>}}}}`, con `json.dumps(…, ensure_ascii=False, indent=2, sort_keys=True) + "\n"`. En `comun.db`, todas las tablas menos las tres pesadas y `sqlite_sequence`; en cada `actas-…`, las tres.
- Una tabla nueva de la base va sola a `comun.db`. Una diferencia de esquema (tabla, columna, índice, vista o pragma de los de arriba salvo `user_version`/`application_id`, que se igualan en sitio) rehace entera la pieza afectada: la común si es de las demás tablas, todas las de temporada si es de una pesada. Una tabla interna que no sea `sqlite_sequence` (`sqlite_stat1`…) o cualquier trigger: `PiezasError` (no se sabría montar sin que se disparen).

**Interfaces:**
- Produces (en `scripts/piezas.py`):
  - `ROOT`, `DB_PATH = ROOT / "futbolbase.db"`, `DIR_PIEZAS = ROOT / "base"`, `PESADAS = ("appearances", "match_events", "match_staff_all")`, `COMUN = "comun.db"`, `MANIFIESTO = "piezas.json"`, `FORMATO = 1`, `MB = 1024 * 1024`, `AVISO_MB = 80`, `PARADA_MB = 95`.
  - `class PiezasError(Exception)` — lo que impide montar o partir; su texto, en español, dice qué y dónde.
  - `nombre_pieza(temporada: str) -> str` — `"2025-2026"` → `"actas-2025-2026.db"`; `ValueError` si no casa `^\d{4}-\d{4}$`.
  - `identidad(conn, tabla: str, esquema: str = "main") -> list[str]` — la regla de arriba: `["rowid"]`, `["id"]` o las columnas de la clave primaria en su orden.
  - `columnas(conn, tabla: str, esquema: str = "main") -> list[str]` — la identidad y después el resto de columnas en su orden, sin repetir.
  - `huella(conn, tabla: str, esquema: str = "main") -> tuple[int, str]` — `(filas, sha256 hex)` de `SELECT <columnas> FROM <tabla> ORDER BY <identidad>`, cada fila como `repr(tuple(fila)).encode("utf-8") + b"\n"`; `sqlite_sequence`, por `(name, seq)` ordenado por `name`.
  - `esquema(conn, esquema: str = "main") -> list[tuple]` — `(type, name, tbl_name, sql)` de `sqlite_master`, ordenado por `(type, name)`, más los cinco pragmas.
  - `montar(dir_piezas: Path, destino: Path, *, solo_comun: bool = False, contra: Path | None = None) -> dict[str, int]` — monta en un temporal junto a `destino` (`.<nombre>.<azar>.tmp`), comprueba contra el manifiesto (los `.db` de la carpeta son exactamente los del manifiesto, cada tabla con sus filas, las pesadas de `comun.db` vacías, el mismo `CREATE TABLE` de las pesadas en todas), deja la base en modo WAL y, solo si todo va bien, la pone en `destino` con `os.replace`. Antes de ponerla: si `destino-wal` tiene datos, `PiezasError` («hay datos sin volcar en …-wal»); si está vacío, lo borra con su `-shm`. Con `contra`, compara antes con ese fichero (`comparar`) y, si difieren, `PiezasError` sin tocar `destino`. Con `solo_comun`, solo `comun.db` (las pesadas, vacías). Escribe `<destino>.piezas` con el sha256 del texto de `piezas.json`. Devuelve las filas por tabla. Conexiones con `foreign_keys=OFF`.
  - `partir(db: Path, dir_piezas: Path) -> dict` — `{"creadas": [fichero], "cambiadas": {fichero: (insertadas, borradas)}, "borradas": [fichero], "intactas": [fichero]}`. Lee `db` en solo lectura (`file:…?mode=ro`). Antes de nada, abre en escritura cada pieza con un `-journal` al lado (SQLite la devuelve a su último commit). Filas pesadas sin temporada: `PiezasError` con cuántas y de qué partidos. Por pieza: si falta o su esquema no es el de la base, se rehace entera en un temporal y se pone con `os.replace`; si no, se adjunta en solo lectura y se cuentan las diferencias (`SELECT <columnas> … EXCEPT …` en los dos sentidos, contra las filas de la base de esa temporada); sin diferencias, **no se abre en escritura** (ni un byte cambia); con ellas, en una transacción, se borran por identidad las que sobran o cambiaron y se insertan las nuevas o cambiadas. `sqlite_sequence` de `comun.db` se iguala al final de su transacción. La pieza de una temporada sin filas se borra. El manifiesto se escribe el último (`escribir_atomico` del mismo patrón: temporal y `os.replace`) y solo si cambia; después, `<db>.piezas`. Volver a llamarla tras un corte arregla lo que quedó a medias.
  - `comparar(a: Path, b: Path) -> list[str]` — vacía si las dos bases tienen el mismo `esquema()` y, tabla a tabla, la misma `huella()`; si no, una frase por diferencia («appearances: 437942 filas y 437941»).
  - `verificar(db: Path, dir_piezas: Path) -> dict` — `{"ok": bool, "motivos": [str], "mayor": (fichero, bytes), "total": bytes}`. Motivos: un `-journal` en la carpeta («partir se cortó a medias: <fichero>-journal»); una pieza que no está en modo `DELETE` (bytes 18 y 19 de la cabecera distintos de 1); una pieza del manifiesto anterior que ha desaparecido sin que su temporada se quede sin filas; lo que diga `montar` a un directorio temporal del sistema; lo que diga `comparar(db, montada)`; la mayor pieza desde `PARADA_MB` («la pieza actas-2025-2026.db ocupa 96 MB y GitHub no admite más de 100»).
  - `main(argv=None) -> int` — `python3 scripts/piezas.py montar [--db F] [--piezas D] [--solo-comun] [--contra F]`, `partir [--db F] [--piezas D]`, `verificar [--db F] [--piezas D] [--salud]` (`--salud` llega en la tarea 7), `comparar --db F --piezas D` (monta `D` en un temporal y compara). Por defecto, `DB_PATH` y `DIR_PIEZAS`. Sale con 0 o, con `PiezasError` o motivos, con 1 tras una línea por motivo. Primeras líneas de una salida buena: `montada <destino>: <n> piezas, <apariciones> apariciones`; `partida <db>: <c> creadas, <m> cambiadas, <b> borradas, <i> sin cambios` (y una línea `  <fichero>: +<ins> -<bor>` por cambiada); `piezas iguales a la base: <t> tablas; la mayor, <fichero> (<mb> MB); en total <mb> MB`; `iguales`.
  - Solo para las pruebas: con `PIEZAS_CORTE_PRUEBA=tras:<n>`, `partir` termina el proceso con `os._exit(3)` justo después del commit de su pieza número `n`; con `dentro:<n>`, dentro de su transacción, tras los borrados y antes del commit (deja un `-journal` caliente).

- [ ] **Step 1: Escribir las pruebas que fallan** en `scripts/tests/test_piezas.py`. La base sintética, `_base(path, temporadas=("2024-2025", "2025-2026"), actas=6)`: `db.init_db` + `migrate_actas_schema.migrate(conn, log=lambda *a: None)` (el esquema compacto de verdad), una tabla `venues` como la real (rowid sin `INTEGER PRIMARY KEY`), dos grupos por temporada, partidos con acta y, por acta, apariciones, sucesos (dos con `pair_id` mutuo) y cuerpo técnico (uno con `team_id` NULL y uno con `ord` negativo); nombres inventados.

```python
def test_montar_partir_es_la_identidad(tmp_path):
    w = _base(tmp_path / "w.db"); partir(w, tmp_path / "base")
    montar(tmp_path / "base", tmp_path / "m.db")
    assert comparar(w, tmp_path / "m.db") == []
    assert sorted(p.name for p in (tmp_path / "base").iterdir()) == [
        "actas-2024-2025.db", "actas-2025-2026.db", "comun.db", "piezas.json"]

@pytest.mark.parametrize("semilla", range(20))
def test_propiedad_con_cambios_al_azar(tmp_path, semilla):
    # 15 cambios al azar (random.Random(semilla)): insertar, cambiar y borrar filas de las tres tablas
    # pesadas y de matches/scorers/venues; mover un partido a un grupo de otra temporada; crear una
    # temporada con su grupo y un acta. Tras cada cambio: partir, montar en un fichero nuevo y comparar.
    ...  # assert comparar(w, montada) == [] en cada vuelta

def test_partir_no_toca_las_piezas_sin_cambios(tmp_path):
    w = _base(tmp_path / "w.db"); partir(w, tmp_path / "base")
    antes = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "base").iterdir()}
    r = partir(w, tmp_path / "base")
    assert r["cambiadas"] == {} and r["creadas"] == [] and r["borradas"] == []
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "base").iterdir()} == antes
    _cambiar_un_gol(w, "2025-2026")
    r = partir(w, tmp_path / "base")
    assert set(r["cambiadas"]) == {"actas-2025-2026.db"}
    assert (tmp_path / "base/actas-2024-2025.db").read_bytes() == antes["actas-2024-2025.db"][0]
    assert (tmp_path / "base/comun.db").read_bytes() == antes["comun.db"][0]

@pytest.mark.parametrize("tabla", PESADAS)
def test_una_fila_cambiada_anadida_o_borrada_llega_a_su_pieza(tmp_path, tabla):
    # Por tabla, tres vueltas (cambiar una columna que no es la identidad, insertar, borrar), en 2025-26:
    # cada vez r["cambiadas"] == {"actas-2025-2026.db": (1, 0)}, (0, 1) o (1, 1) y comparar(...) == [].

def test_un_partido_que_cambia_de_temporada_mueve_sus_filas(tmp_path):
    # UPDATE matches SET group_id = <grupo de 2024-25> de un partido de 2025-26 con acta.
    # r["cambiadas"] tiene las dos piezas y comun.db; sus apariciones ya no están en
    # actas-2025-2026.db y sí en actas-2024-2025.db (contadas con sqlite3 sobre cada pieza).

def test_una_temporada_nueva_crea_su_pieza_y_una_vacia_la_borra(tmp_path):
    # Una temporada 2026-2027 con un acta: r["creadas"] == ["actas-2026-2027.db"]. Sus filas, borradas:
    # r["borradas"] == ["actas-2026-2027.db"], el fichero ya no está y piezas.json no la nombra.

def test_tabla_nueva_va_a_la_comun_sin_tocar_las_temporadas(tmp_path):
    # CREATE TABLE mygol_prueba (id INTEGER PRIMARY KEY, nombre TEXT) con dos filas: solo cambia comun.db
    # (rehecha), las actas-* salen iguales byte a byte y la montada la tiene con sus dos filas.

def test_columna_nueva_en_una_pesada_rehace_las_temporadas(tmp_path):
    # ALTER TABLE appearances ADD COLUMN minutos INTEGER: las dos actas-* se rehacen y comparar == [].

def test_autoincremento_no_reutiliza_ids(tmp_path):
    # Con el id más alto de matches borrado en w (sqlite_sequence sigue en él): partir, montar y un INSERT
    # en matches de la montada da un id mayor que el borrado; sqlite_sequence de la montada == el de w.

def test_conserva_los_rowid(tmp_path):
    # match_staff_all y venues con huecos en sus rowid (borrar filas del medio en w): la montada tiene
    # exactamente los mismos (SELECT rowid, * ... ORDER BY rowid) que w.

def test_las_piezas_no_van_en_wal(tmp_path):
    # Con w en modo WAL (get_connection): cada pieza tiene 1 y 1 en los bytes 18 y 19 de la cabecera, y la
    # montada, 2 y 2 (WAL, como la de hoy).

def test_montar_no_hereda_un_wal_viejo(tmp_path):
    # Un destino con un -wal de 10 bytes al lado: PiezasError con "-wal" en el texto y el destino como
    # estaba. Con un -wal vacío y un -shm: monta, y los dos ya no están.

def test_montar_comprueba_el_manifiesto(tmp_path):
    # Tres casos, cada uno PiezasError y destino sin crear: falta actas-2024-2025.db; sobra un actas-*.db
    # que el manifiesto no nombra; una pieza con una fila más que la que dice el manifiesto.

def test_montar_contra_un_fichero_distinto_no_toca_el_destino(tmp_path):
    # contra = una copia de w con un gol más: PiezasError ("no son iguales") y destino con sus bytes de antes.
    # contra = w: monta.

def test_solo_comun(tmp_path):
    # montar(..., solo_comun=True): las tres pesadas vacías y las demás tablas como en w.

def test_filas_sin_temporada_no_se_parten(tmp_path):
    # Una aparición de un partido que no existe (con foreign_keys=OFF): PiezasError que dice "sin
    # temporada" y el número de partido; las piezas, sin tocar.

def test_un_trigger_no_se_admite(tmp_path):
    # CREATE TRIGGER en w: partir lanza PiezasError con "trigger".

def test_corte_entre_dos_piezas(tmp_path):
    # Con un cambio en las dos temporadas y comun.db: subprocess que llama a partir con
    # PIEZAS_CORTE_PRUEBA=tras:1 (sale con 3). verificar(w, base)["ok"] es False; partir otra vez y
    # verificar da ok.

def test_corte_dentro_de_una_pieza(tmp_path):
    # PIEZAS_CORTE_PRUEBA=dentro:1: queda un "<pieza>-journal". verificar da ok False con "se cortó a
    # medias"; partir otra vez (devuelve la pieza a su commit y la vuelve a escribir) y verificar da ok.

def test_verificar_avisa_de_la_pieza_mayor(tmp_path, monkeypatch):
    # monkeypatch.setattr(piezas, "PARADA_MB", 0): ok False y el motivo nombra la mayor; con el valor de
    # verdad, ok True, mayor == (nombre, bytes) de la pieza más grande y total == suma de los .db.

def test_una_pieza_que_desaparece_no_se_sube(tmp_path):
    # Tras partir, borrar a mano actas-2024-2025.db y su entrada no: verificar da ok False.

def test_solo_biblioteca_estandar(tmp_path):
    # python3 -I con cwd en tmp_path carga scripts/piezas.py por spec_from_file_location sin ImportError.

def test_cli(tmp_path):
    # main(["partir", "--db", w, "--piezas", d]) == 0 y la salida empieza por "partida "; montar → 0 y
    # "montada "; verificar → 0 y "piezas iguales a la base: "; comparar → 0 e "iguales"; con una pieza
    # rota (truncada a la mitad), montar → 1 y el destino sin crear.
```

  Y en `scripts/tests/test_piezas_real.py`, con `pytest.mark.skipif(os.environ.get("PIEZAS_REAL") != "1", …)` y la base de la raíz copiada a `tmp_path` (nunca abierta en escritura): `test_la_base_real_se_parte_y_se_monta_igual` (`partir`, `montar`, `comparar == []`, la mayor pieza por debajo de `AVISO_MB`) y `test_la_base_real_no_cambia_al_volver_a_partir` (segunda `partir`: todo en `"intactas"`).

- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_piezas.py` — Expected: error de importación (`No module named 'piezas'`).
- [ ] **Step 3: Implementar `scripts/piezas.py`.** Cabecera del módulo: por qué la base va en piezas (los límites de GitHub y de Pages, con las cifras de «Lo medido»), qué es cada pieza y las tres órdenes. Las piezas se escriben con una conexión a la pieza y la base adjunta en solo lectura (`ATTACH 'file:…?mode=ro' AS w`), para ejecutar los `CREATE` de la base letra a letra. La temporada de cada partido, en una tabla temporal (`CREATE TEMP TABLE`) con índice, una vez por llamada.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_piezas.py && PIEZAS_REAL=1 python3 -m pytest -q -p no:cacheprovider scripts/tests/test_piezas_real.py` — Expected: todo en verde; la segunda, `2 passed` en menos de un minuto.
- [ ] **Step 5: `docs/almacenamiento.md`**, para el dueño y para quien trabaje en local: qué hay en `base/` y por qué (los tres límites), qué hacen montar, partir y verificar, las cifras de «Lo medido», cómo se trabaja con la base a mano (`python3 scripts/piezas.py montar`, la orden que sea, `partir`, `verificar`, `git add -A base/`) y que hasta la fase 3 la que manda es `futbolbase.db` (la sección de fases la completan las tareas 2, 3 y 7).
- [ ] **Step 6: Commit.** Asunto: «La base en piezas: montar, partir y verificar (scripts/piezas.py)».

---

### Task 2: Fase 1, las piezas en sombra

**Files:**
- Modify: `.github/workflows/update.yml` (paso nuevo tras «Base sana», `:120-159`), `.github/workflows/activar.yml` (paso nuevo tras «Base sana», `:175-196`, `:202-221`), `.github/workflows/tests.yml` (job `pytest`, rutas `:4-58`), `.gitignore`, `docs/almacenamiento.md`
- Test: `scripts/tests/test_workflows.py`

**Interfaces:**
- Consumes: `python3 scripts/piezas.py partir|verificar|comparar` (tarea 1).
- Produces: en `update.yml` y `activar.yml`, el paso `Piezas de la base (en sombra)` con `id: piezas`; `base/` en git desde la primera pasada con datos.

Qué cambia:
- `update.yml`, tras «Base sana»:

```yaml
      # Parte D, fase 1 (docs/almacenamiento.md): la base, partida en sus piezas (base/) y comprobada en cada
      # pasada, en sombra: la fuente de verdad sigue siendo futbolbase.db. Si algo falla aquí, la pasada publica
      # igual y solo no sube las piezas (vuelven a las de main).
      - name: Piezas de la base (en sombra)
        id: piezas
        if: steps.base.outcome == 'success'
        continue-on-error: true
        run: |
          python3 scripts/piezas.py partir && python3 scripts/piezas.py verificar || {
            git checkout -q HEAD -- base/ 2>/dev/null || true
            git clean -fdq -- base/
            exit 1
          }
```

- `update.yml`, «Commit y push si hay cambios»: `env: PIEZAS: ${{ steps.piezas.outcome }}` y, dentro de la puerta de la base, justo después de `git add futbolbase.db`: `if [ "$PIEZAS" = success ]; then git add -A base/; fi`. Las piezas suben con la base o no suben: la misma puerta que hoy (sin cambios publicados ni marca, no se sube ni la una ni las otras).
- `activar.yml`: el mismo paso tras «Base sana», con `if: steps.cambios.outputs.datos == 'true' && steps.base.outcome == 'success'` (así lo admite `test_activar_does_nothing_when_nothing_is_pending`); en «Subir la activación», `env: PIEZAS: …` y, con `DATOS` a `true`, `if [ "$PIEZAS" = success ]; then git add -A base/; fi`; en «Publicar el fallo», tras devolver la base: `git checkout HEAD -- base/ 2>/dev/null || true` y `git clean -fdq -- base/`. `ACTIVAR_STEPS` gana `"Piezas de la base (en sombra)"` tras `"Base sana (bloquea el commit si falla)"`.
- `tests.yml`, job `pytest`, tras «Run Python tests»: el paso `Las piezas son la base` con `run: python3 scripts/piezas.py comparar --db futbolbase.db --piezas base` (con un comentario: en la fase 1, el aviso diario de que la sombra se ha desviado) y `PIEZAS_REAL: '1'` en el `env` de «Run Python tests». En `push.paths` y `pull_request.paths`, `'base/**'` tras `'futbolbase.db'`.
- `.gitignore`, junto a los transitorios de SQLite: `base/*.db-journal` y `/futbolbase.db.piezas`, con su porqué.
- `test_workflows.py`: `PUBLICADO` gana `"base/*"`; las pruebas que fijan pasos y `git add` se ponen al día (`test_update_stages_all_generate_js_outputs`, `test_update_gates_db_commit_on_published_changes`, las de `_run_commit_step`, `ACTIVAR_STEPS`).

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_workflows.py`:
  - `test_las_piezas_van_tras_la_base_sana_y_no_paran_la_pasada`: en `update.yml` y `activar.yml`, el paso `Piezas de la base (en sombra)` va justo después de «Base sana…», con `continue-on-error: true` y su `run` llama a `partir` y a `verificar` en ese orden.
  - `test_las_piezas_suben_solo_con_la_base`: en «Commit y push si hay cambios», `git add -A base/` está dentro de la puerta (después de `git add futbolbase.db`, en la misma rama del `if`) y condicionado a `"$PIEZAS" = success`.
  - `test_pasada_en_seco_sube_solo_la_pieza_que_cambia(tmp_path)`: con el arnés de `_run_commit_step` ampliado (un repositorio de mentira con su remoto y, en `scripts/`, `piezas.py`, `base_sana.py`, `source_health.py`, `portal_config.py`, `escritura.py` y `db.py` copiados), se ejecutan con `bash -e -c` los `run` de verdad de «Base sana…», «Piezas de la base (en sombra)» y «Commit y push si hay cambios». Pasada 1 (sin `base/` y con `data-x.js` cambiado): el último commit del remoto lleva `base/comun.db`, `base/actas-2024-2025.db`, `base/actas-2025-2026.db`, `base/piezas.json`, `data-x.js` y `futbolbase.db`. Pasada 2 (un gol cambiado en 2025-26 y `data-x.js`): `base/actas-2025-2026.db`, `base/piezas.json`, `data-x.js`, `futbolbase.db` y nada más de `base/`. Pasada 3 (nada publicado cambia): ningún fichero de `base/` en el commit. Pasada 4 (`PIEZAS_CORTE_PRUEBA=dentro:1` en el entorno del paso de piezas): el job sigue, el commit lleva `futbolbase.db` y ningún fichero de `base/`, y `git status --porcelain -- base/` queda vacío.
  - `test_tests_yml_compara_las_piezas_con_la_base`: el paso existe en el job `pytest`, tras «Run Python tests», y `'base/**'` está en las dos listas de rutas.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_workflows.py` — Expected: las nuevas fallan; las demás, en verde.
- [ ] **Step 3: Implementar** los cambios de arriba y el apartado «Fase 1: en sombra» de `docs/almacenamiento.md` (qué pasa en cada pasada y cómo se mira que va bien).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde (salvo lo que ya falle en `main`, que se dice en el informe sin tocarlo).
- [ ] **Step 5: Commit.** Asunto: «Parte D, fase 1: el bot y la activación parten la base en sombra».

**PASO DEL DIRECTOR — publicar la fase 1 y dejarla correr.**
1. Con las tareas 1 y 2 en la rama: sin ningún workflow en marcha (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --status in_progress` y `--status queued`, las dos vacías), rebasar sobre `main` como dice `docs/rediseno-rebase.md` y `git push origin almacen:main`.
2. Comprobación: la primera pasada con datos trae `base/` (`git fetch origin && git show --stat origin/main -- base/` lista `base/comun.db`, las ocho `actas-*.db` y `base/piezas.json`) y su log dice `piezas iguales a la base: …` (`gh run view <id> -R … --log | grep "piezas iguales"`).
3. Puerta para la tarea 3, al cabo de al menos 12 pasadas con datos y un `tests.yml` diario en verde con el paso «Las piezas son la base»: en un clon limpio,

```bash
for c in $(git log -n 12 --format=%H origin/main -- futbolbase.db); do
  d=$(mktemp -d); git archive "$c" base futbolbase.db | tar -x -C "$d"
  python3 scripts/piezas.py comparar --db "$d/futbolbase.db" --piezas "$d/base" > /dev/null || echo "DISTINTO $c"
  rm -rf "$d"
done
```
   Expected: ninguna línea `DISTINTO`. Con alguna, no se sigue: se mira el log de esa pasada.
4. Vuelta atrás: `git revert` de los commits de la tarea 2 (con el bot sin nada en marcha). Las piezas que haya en `base/` se quedan sin uso.

---

### Task 3: Fase 2, la fuente de verdad pasa a las piezas

Un solo commit, pequeño, que se revierte entero.

**Files:**
- Modify: `.github/workflows/update.yml`, `.github/workflows/activar.yml`, `.github/workflows/tests.yml` (job `pytest`), `docs/almacenamiento.md`
- Test: `scripts/tests/test_workflows.py`

**Interfaces:**
- Consumes: `piezas.py montar --contra futbolbase.db`, `partir`, `verificar`.
- Produces: en `update.yml` y `activar.yml`, el paso `Montar la base` (`id: montar`) y `Partir la base y comprobarla (bloquea el commit si falla)` (`id: piezas`, el de la tarea 2 sin `continue-on-error` ni la vuelta atrás de `base/`).

Qué cambia:
- `update.yml`: justo después de «Set up Python», antes de instalar nada:

```yaml
      # Parte D, fase 2 (docs/almacenamiento.md): la base de la pasada sale de sus piezas (base/). futbolbase.db
      # sigue en git, idéntica a ellas (las dos se suben juntas): --contra para la pasada si no lo es, porque
      # entonces alguien ha subido solo una de las dos y hay que decidir a mano cuál vale.
      - name: Montar la base
        id: montar
        run: python3 scripts/piezas.py montar --contra futbolbase.db
```
  `Piezas de la base (en sombra)` pasa a `Partir la base y comprobarla (bloquea el commit si falla)`, sin `continue-on-error` y con `run: python3 scripts/piezas.py partir && python3 scripts/piezas.py verificar`. Las dos suites pasan a `if: steps.piezas.outcome == 'success'`. En el commit, `git add -A base/` sin condición, junto a `git add futbolbase.db`. El diagnóstico se lanza también con `steps.montar.outcome == 'failure' || steps.piezas.outcome == 'failure'`, recibe `MONTAR_OUTCOME` y `PIEZAS_OUTCOME`, y su guion empieza por `if [ "$MONTAR_OUTCOME" = failure ]; then python3 scripts/source_health.py marcar "no se pudo montar la base desde sus piezas: esta pasada no se ha hecho"; elif [ "$SCRAPE_OUTCOME" = success ]; then …` (lo de hoy, con un caso más: `PIEZAS_OUTCOME = failure` → `"las piezas de la base no salieron iguales a la base: los datos de esta pasada no se publicaron"`).
- `activar.yml`: `Montar la base` justo después de «Set up Node» (antes de «Qué hay pendiente», que abre la base); el paso de piezas, como en `update.yml` (bloquea); «Subir la activación», `git add -A base/` sin condición con `DATOS` a `true`; «Publicar el fallo» se lanza también con `steps.piezas.outcome == 'failure'`. `ACTIVAR_STEPS`: `"Montar la base"` en la posición 3 y el paso de piezas renombrado; en `test_activar_does_nothing_when_nothing_is_pending`, los cortes pasan a `[5:11]` y `[11:]`.
- `tests.yml`, job `pytest`: `Montar la base` (`python3 scripts/piezas.py montar --contra futbolbase.db`) justo después de `actions/setup-python`; fuera el paso «Las piezas son la base» (lo hace `--contra`).

- [ ] **Step 1: Pruebas que fallan** en `test_workflows.py`:
  - `test_montar_va_antes_que_todo_lo_que_lee_la_base`: en `update.yml`, `activar.yml` y el job `pytest` de `tests.yml`, el paso `Montar la base` es el primero cuyo `run` llama a `python3 scripts/` (en `activar.yml`, antes que «Qué hay pendiente»), y su `run` lleva `--contra futbolbase.db`.
  - `test_partir_bloquea`: el paso de piezas no tiene `continue-on-error`; las dos suites dependen de `steps.piezas.outcome == 'success'`; el diagnóstico de `update.yml` mira `steps.montar.outcome` y `steps.piezas.outcome`.
  - `test_diagnostico_si_no_se_puede_montar(tmp_path)`: el guion de verdad del diagnóstico con `MONTAR_OUTCOME=failure` y `SCRAPE_OUTCOME=skipped`, en el repositorio de mentira: sube solo `data-health.json`, con `runHealth.ok` a `false` y el motivo «no se pudo montar la base…».
  - `test_pasada_en_seco_sube_solo_la_pieza_que_cambia` pasa a ejecutar también `Montar la base` al principio, y gana una pasada 5: con `futbolbase.db` del remoto cambiada a mano (otro commit que solo la toca), `Montar la base` sale con 1 y ni la pasada ni el commit se hacen.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_workflows.py` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar** y escribir en `docs/almacenamiento.md` el apartado «Fase 2: mandan las piezas», con lo que hace `--contra` y la vuelta atrás.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Parte D, fase 2: la pasada monta la base de sus piezas». Un solo commit con los tres workflows, sus pruebas y el documento.

**PASO DEL DIRECTOR — el cambio, sin carrera con una pasada.** Con `R=malolocabreralolo-tech/futbol-base-v2`:
1. Parar lo que lanza pasadas: `gh workflow disable reloj.yml -R $R`.
2. Esperar a que no quede nada en marcha ni en cola, de ningún workflow (la norma de no empujar con un workflow en marcha): repetir `gh run list -R $R --status in_progress --json workflowName` y `gh run list -R $R --status queued --json workflowName` hasta que las dos den `[]`.
3. Cerrar las otras puertas (las tandas lanzan el bot con `|| echo`, sin fallar): `gh workflow disable update.yml -R $R && gh workflow disable activar.yml -R $R`.
4. `git push origin almacen:main` (rebasada sobre `main`, con la tarea 3 en la punta).
5. `gh workflow enable update.yml -R $R && gh workflow enable activar.yml -R $R`, `gh workflow run update.yml -R $R --ref main` y seguirla: `gh run watch -R $R $(gh run list -R $R --workflow update.yml -L 1 --json databaseId --jq '.[0].databaseId') --exit-status`.
6. Comprobación: el log trae `montada …/futbolbase.db: 9 piezas, …` y `piezas iguales a la base: …`; si subió algo, el commit lleva `futbolbase.db` y lo cambiado de `base/` (`git show --stat origin/main`).
7. `gh workflow enable reloj.yml -R $R`.
8. Si algo falla en el paso 5 o en las pasadas siguientes: repetir 1-3, `git revert --no-edit <commit de la tarea 3>`, `git push origin main`, y 5 y 7. Volver es seguro en cualquier momento: en la fase 2 cada subida lleva `futbolbase.db` al día, que es lo que lee la fase 1. Una pasada que se lanzó antes del cambio y arranca después corre con el workflow de la fase 1 sobre el `main` nuevo: parte de `futbolbase.db` y sube las dos, iguales.

---

### Task 4: La copia del PC monta la base de v2

**Files:**
- Create: `pc/copia/copia/piezas.py` (enlace simbólico a `../../../scripts/piezas.py`)
- Modify: `pc/copia/copia/fuentes.py` (`Origen`, `cargar_origenes`, `extraer_base`), `pc/copia/origenes.json` (solo la entrada `v2`), `pc/copia/instalar.sh` (si hace falta: comprobar que `cp` copia el fichero de verdad), `pc/copia/README.md`
- Test: `pc/copia/tests/test_fuentes.py`, `pc/copia/tests/test_instalar.py`

**Interfaces:**
- Consumes: `piezas.montar(dir_piezas, destino)` y `piezas.PiezasError` (tarea 1), importados como `from . import piezas`.
- Produces:
  - `Origen` gana `piezas: str | None = None` (la carpeta de las piezas en el repositorio). `cargar_origenes` lo lee de `d.get("piezas")`: ausente, `None`; presente, una ruta relativa sin `..` ni barra inicial, o `FuenteError`.
  - `extraer_base(origen, commit, destino) -> Path`: si el commit tiene `origen.base` (`git cat-file -e <commit>:<base>`), lo de hoy, byte a byte. Si no, y `origen.piezas` está y el commit tiene `<piezas>/piezas.json`, saca cada fichero de `git ls-tree -r --name-only <commit> -- <piezas>/` a una carpeta temporal junto a `destino` (con `extraer_fichero`) y monta con `piezas.montar(carpeta, destino)`; un `PiezasError` se convierte en `FuenteError` con su texto. Si no hay ni lo uno ni lo otro, `FuenteError` como hoy.
  - `origenes.json`: la entrada `v2` gana `"piezas": "base"`; `v1` no cambia.

Por qué en este orden: mientras `futbolbase.db` esté en git (fases 1 y 2) es la buena, y es idéntica a las piezas; desde la fase 3 ya no está y el PC monta solo, sin otra instalación. La copia guarda la base montada igual que hoy: `actual/v2/futbolbase.db`, versiones, volcados y cuarentena no cambian.

- [ ] **Step 1: Pruebas que fallan** en `pc/copia/tests/test_fuentes.py` (con el remoto de mentira de las pruebas que hay; las piezas, hechas con `piezas.partir` sobre una base sintética pequeña de nombres inventados):
  - `test_v2_sin_la_base_monta_las_piezas`: un commit con solo `base/`: `extraer_base` da una base con las mismas filas (`piezas.comparar(original, extraida) == []`).
  - `test_con_la_base_en_el_commit_usa_la_base`: un commit con las dos: el resultado es `futbolbase.db` byte a byte.
  - `test_piezas_rotas_es_un_fallo_de_la_fuente`: un commit con `base/` sin una de sus piezas: `FuenteError`, y nada en `destino`.
  - `test_v1_no_cambia`: el origen de `v1` cargado de `origenes.json` tiene `piezas is None`, y las pruebas de hoy de `extraer_base` pasan sin tocarlas.
  - `test_origen_con_piezas_que_se_salen`: `"piezas": "../x"` y `"/x"` dan `FuenteError`.
  - En `test_instalar.py`, `test_instala_piezas_como_fichero`: tras `instalar.sh` en su carpeta de mentira, `copia/piezas.py` instalado es un fichero normal (no un enlace) con el contenido de `scripts/piezas.py`.
- [ ] **Step 2: Verlas fallar.** Run: `cd pc/copia && python3 -m pytest tests -q -W error` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar.** El enlace se crea con `ln -s ../../../scripts/piezas.py pc/copia/copia/piezas.py` (git guarda el enlace; `cp` sin `-R` copia el fichero al que apunta).
- [ ] **Step 4: Ejecutar.** Run: `cd pc/copia && python3 -m pytest tests -q -W error` — Expected: en verde. Y `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_piezas.py` sigue en verde.
- [ ] **Step 5: `pc/copia/README.md`**: un párrafo en «Qué se guarda y dónde»: la de v2, desde que no está en git, se monta de sus piezas (`base/`) del commit de ese día; lo demás igual. En «Cómo sacar un fichero original», que `futbolbase.db` de v2 ya no se saca con `extraer` sino con `restaurar`.
- [ ] **Step 6: Commit.** Asunto: «Copia del PC: la base de v2 se monta de sus piezas cuando ya no está en git».

**PASO DEL DIRECTOR — instalar en el PC del dueño** (antes de la tarea 7):
1. Con la tarea 4 en `main` y traída a `~/claude/futbol-base-v2`: `cd ~/claude/futbol-base-v2/pc/copia && python3 -m pytest tests -q && bash instalar.sh`.
2. Comprobación: `futbol-base-copia ejecutar` y `futbol-base-copia estado`: la línea de `v2` dice `(aceptada)` o `(sin cambios)`, la de `v1` sigue como estaba y no sale `AVISO`; `instalado: commit <el de la tarea 4>`. El día siguiente a la tarea 7, otra vez `estado`: `v2 … (aceptada)` con la base montada.
3. Vuelta atrás: en un árbol aparte con el commit anterior (`git -C ~/claude/futbol-base-v2 worktree add /tmp/copia-anterior <commit anterior>`), `cd /tmp/copia-anterior/pc/copia && bash instalar.sh`.

---

### Task 5: La base completa para descargar, una vez al día

**Files:**
- Create: `scripts/descarga.py`
- Modify: `scripts/source_health.py` (`set_descarga`, `_carry_descarga`, `set_base` con `pieza`), `.github/workflows/update.yml` (paso nuevo antes del commit), `src/screen-fuentes.js` (`databaseBlock`, `render`), `src/estado.js` (`avisoBase`), `docs/decisiones.md`
- Test: `scripts/tests/test_descarga.py`, `scripts/tests/test_source_health.py`, `scripts/tests/test_workflows.py`, `scripts/tests/test_detalle_web.mjs`, `scripts/tests/test_estado.mjs`

**Interfaces:**
- Produces:
  - `scripts/descarga.py`: `TAG = "base-completa"`, `ASSET = "futbolbase.zip"`, `URL = "https://github.com/malolocabreralolo-tech/futbol-base-v2/releases/download/base-completa/futbolbase.zip"`.
  - `toca(health_path: Path = source_health.REPORT_PATH, hoy: date | None = None) -> bool` — `True` si `descarga.fecha` del informe no es la fecha UTC de `hoy` (o no hay `descarga`).
  - `preparar(db: Path, zip_path: Path) -> int` — `VACUUM INTO` un temporal (sale en modo `DELETE`: se abre en cualquier sitio, también de solo lectura), y un ZIP con una sola entrada `futbolbase.db`, `ZIP_DEFLATED` nivel 6. Devuelve los bytes del ZIP. La base no se escribe.
  - `apuntar(zip_path: Path, health_path: Path = …, hoy: date | None = None) -> None` — `source_health.set_descarga({"url": URL, "fecha": "<AAAA-MM-DD UTC>", "bytes": <tamaño del ZIP>}, health_path)`.
  - CLI: `python3 scripts/descarga.py toca` (sale con 0 si toca, 1 si no), `preparar <zip> [--db F]`, `apuntar <zip>`.
  - `source_health.set_descarga(info: dict, path=None)` — pone `descarga` en el informe sin tocar nada más (como `set_base`); `begin()` la conserva (`_carry_descarga`, junto a `_carry_base`).
  - `source_health.set_base(bytes_, aviso, path=None, pieza=None)` — con `pieza`, `base: {"mb", "limite": 100, "pieza": "<comun|AAAA-AAAA>"}`; sin ella, como hoy. Lo usará la tarea 7.
  - `src/screen-fuentes.js`: `databaseBlock(cobertura, descarga)` — `descarga` es `health.descarga`; vale si `url` empieza por `https://github.com/malolocabreralolo-tech/futbol-base-v2/releases/download/`, `fecha` casa `^\d{4}-\d{2}-\d{2}$` y `bytes` es un entero positivo. `render` le pasa `health.descarga`.
  - `src/estado.js`: `avisoBase(health)` con `base.pieza`.

Qué se ve en «La base de datos»:
- Con una descarga válida: el botón `<a class="button is-main" href="<url>" download>Descargar la base de datos<span class="vh"> (ZIP, <n> MB)</span></a>`, el contexto del bloque `ZIP, <n> MB` y, en la caja, tras el texto de hoy: «Es un archivo ZIP con la base tal como estaba el <día y mes>; se renueva una vez al día.» y, si `cobertura.mb`, «Descomprimida ocupa unos <mb> MB.». `<n>` = `max(1, round(bytes / 1048576))`; el día, con `dayMonthLong`.
- Sin ella: sin botón, el contexto `SQLite`, y «La copia para descargar se prepara una vez al día y todavía no está lista.».
- `avisoBase`: con `pieza` igual a `"comun"`, «La parte común de la base de datos ocupa 83 MB de los 100 que admite GitHub por fichero.»; con una temporada, «La parte de 2025/26 de la base de datos ocupa 83 MB de los 100 que admite GitHub por fichero.» (con `seasonLabel`); sin `pieza` o con una que no es ninguna de las dos formas, la frase de hoy.

El paso de `update.yml`, después de «Tests Node» y antes de «Commit y push si hay cambios»:

```yaml
      # La base completa para descargar desde «Datos y fuentes» (parte D): un ZIP en la release fija
      # base-completa, fuera de git y de Pages. La primera pasada sana de cada día (UTC) lo rehace y lo apunta en
      # data-health.json (descarga), que sube en el commit de abajo. Un fallo no para la pasada: la siguiente
      # lo vuelve a intentar.
      - name: Base completa del día
        id: descarga
        if: success() && steps.scrape.outcome == 'success'
        continue-on-error: true
        timeout-minutes: 5
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if python3 scripts/descarga.py toca; then
            python3 scripts/descarga.py preparar "$RUNNER_TEMP/futbolbase.zip"
            gh release upload base-completa "$RUNNER_TEMP/futbolbase.zip" --clobber -R malolocabreralolo-tech/futbol-base-v2
            python3 scripts/descarga.py apuntar "$RUNNER_TEMP/futbolbase.zip"
          else
            echo "La base completa de hoy ya está subida."
          fi
```

- [ ] **Step 1: Pruebas que fallan.**
  - `scripts/tests/test_descarga.py`: `test_toca` (sin informe, sin `descarga`, con la de ayer → `True`; con la de hoy → `False`); `test_preparar(tmp_path)` (sobre una base sintética en WAL: el ZIP tiene solo `futbolbase.db`, abre con `sqlite3`, bytes 18 y 19 de la cabecera a 1, `piezas.comparar(original, descomprimida) == []`, y la original con sus bytes de antes); `test_apuntar` (el informe queda con `descarga == {"url": URL, "fecha": "2026-11-25", "bytes": <tamaño>}` y lo demás igual).
  - `scripts/tests/test_source_health.py`: `test_begin_conserva_la_descarga` y `test_set_base_con_pieza` (`{"mb": 83, "limite": 100, "pieza": "2025-2026"}`).
  - `test_workflows.py`: `test_la_descarga_va_antes_del_commit_y_no_para_la_pasada` (posición, `continue-on-error: true`, `GH_TOKEN`, `--clobber`, el repositorio escrito entero) y `test_solo_el_bot_escribe_la_base` sigue en verde.
  - `test_detalle_web.mjs`: la prueba de Fuentes pasa a dos: con descarga (el `href` de la release, `download`, «ZIP, 13 MB», «tal como estaba el 25 de noviembre», «Descomprimida ocupa unos 45 MB») y sin ella o con una inválida (URL de otro sitio, fecha mal, bytes `0`): sin botón y la frase de «todavía no está lista»; nunca `./futbolbase.db`.
  - `test_estado.mjs`: las dos frases nuevas de `avisoBase` y la de hoy sin `pieza`.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_descarga.py scripts/tests/test_source_health.py scripts/tests/test_workflows.py && node --test scripts/tests/test_detalle_web.mjs scripts/tests/test_estado.mjs` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar**, y en `docs/decisiones.md` («La base y los originales») una línea: la base completa se descarga de la release `base-completa`, la renueva la primera pasada sana de cada día y su fecha y tamaño van en `data-health.json` (`descarga`).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs` — Expected: en verde salvo `test_empaquetar.py::test_check_pasa_en_el_arbol`, que queda en rojo hasta que el director empaquete `dist/` (como en toda tarea que toca `src/`).
- [ ] **Step 5: Commit.** Asunto: «La base completa se descarga de una release que el bot renueva cada día».

**PASO DEL DIRECTOR — la release y la publicación.**
1. Antes de publicar: `gh release create base-completa -R malolocabreralolo-tech/futbol-base-v2 --target main --latest=false --title "Base de datos completa" --notes "La base de datos de la web en un ZIP. El bot la renueva una vez al día; la fecha está en «Datos y fuentes» de la web."`. Comprobación: `gh release view base-completa -R … --json tagName,isPrerelease,assets` da `"tagName":"base-completa"` y `assets` vacío.
2. Publicar como siempre con la web: `python3 scripts/publicar.py` en la rama (empaqueta `dist/`), suites en verde y push a `main` sin workflows en marcha. Después, `gh workflow run update.yml -R … --ref main` para no esperar a la pasada siguiente.
3. Comprobación: el log de esa pasada sube `futbolbase.zip`; `gh release view base-completa -R … --json assets --jq '.[] | .[] | {name, size}'` da `futbolbase.zip` de unos 13 MB; `data-health.json` de `main` tiene `descarga` con la fecha de hoy; `curl -sL -o /tmp/f.zip <URL> && python3 -c "import zipfile; print(zipfile.ZipFile('/tmp/f.zip').namelist())"` da `['futbolbase.db']`; en la web, «Datos y fuentes» enseña el botón con su tamaño y su fecha.
4. Vuelta atrás: `git revert` de la tarea 5 y publicar la web (el enlace vuelve a `./futbolbase.db`, que Pages sirve mientras sea `main`). La release se queda.

---

### Task 6: La rama `web` y Pages solo con la web

**Files:**
- Create: `scripts/rama_web.py`, `.github/workflows/web.yml`
- Modify: `.github/workflows/update.yml` y `.github/workflows/activar.yml` (un paso tras sus subidas), `scripts/tests/copia-web.mjs` (comentario: la lista es la de `rama_web.py`), `scripts/tests/test_workflows.py` (`WORKFLOWS` gana `web.yml`), `docs/decisiones.md`, `docs/almacenamiento.md`
- Test: `scripts/tests/test_rama_web.py`, `scripts/tests/test_workflows.py`

**Decisión (rama `web` frente a `upload-pages-artifact` + `deploy-pages`).** Se elige la rama. Las dos tardan lo mismo por despliegue (hoy, 44-49 s para 287 MB; con la web sola, unos 81 MB hoy y ~520 MB con ×7, de 30 s a 1 min: el grueso es subir el sitio, y las dos lo suben entero), y las dos se quedan bajo el límite de 1 GB. Pero el despliegue por artefacto obliga a cambiar Pages a `build_type: workflow`, a dar `pages: write` e `id-token: write` al bot y a la activación, a un job de despliegue en cada uno (los push con `GITHUB_TOKEN` no lanzan workflows) y en otro para los push a mano, a serializar despliegues (uno a la vez) y, para volver a una versión, a tener aún su artefacto. Con la rama, el despliegue «legacy» que ya funciona (lo lanza el push con `GITHUB_TOKEN`: lo hacen hoy las «Actualizaciones automáticas») sigue igual; cada versión publicada es un commit de `web` con los mismos blobs de `main` (no duplica nada: solo árboles y commits, unos pocos KB por subida); y volver atrás es apuntar Pages a `main` otra vez. El bot pone la rama al día dentro de su propio job, tras su push (~3 s): la web llega igual de pronto que hoy.

**Interfaces:**
- Produces (en `scripts/rama_web.py`):
  - `WEB_FICHEROS = ("index.html", "sw.js", "manifest.json", "acta.css", ".nojekyll", "data-health.json")`, `WEB_CARPETAS = ("dist/", "src/", "fonts/", "icons/", "escudos/")`, `WEB_PATRONES = ("data-*.js",)` (solo en la raíz). `acta.css` y `src/` entran aunque la página de hoy carga `dist/`: los sirve la app de antes del empaquetado mientras se pone al día (`copia-web.mjs`, `DEL_SITIO`). `data-history-2024.json`, `scripts/`, `base/`, `futbolbase.db`, `docs/`, `pc/`, `.github/` y `README.md` quedan fuera.
  - `AVISO_MB = 800`, `PARADA_MB = 950`.
  - `es_web(ruta: str) -> bool`.
  - `arbol_web(commit: str, repo: Path = ROOT) -> tuple[str, int]` — `(sha del árbol, bytes)`: `git ls-tree -r -z -l <commit>`, filtrado con `es_web`, a un índice temporal (`GIT_INDEX_FILE` en un directorio temporal, `git update-index --add -z --index-info`) y `git write-tree`. Mismos modos y blobs que en `main`.
  - `comprobar_arbol(arbol: str, repo: Path = ROOT) -> list[str]` — lo que falta: cada entrada de `PRECACHE` del `sw.js` del árbol (con `precache.ENTRADA_RE` sobre el bloque entre `precache.INICIO` y `precache.FIN`), `app`, `css` y `externos` de `dist/origen.json`, los iconos de `manifest.json`, los `data-*.js` de los `<script defer>` de `index.html` (`precache.datos_inmediatos`) y `.nojekyll`; y el tamaño desde `PARADA_MB`.
  - `publicar(repo: Path = ROOT, remoto: str = "origin", intentos: int = 3, _antes_de_subir: Callable[[], None] | None = None) -> str | None` — `_antes_de_subir` se llama justo antes de cada `git push` (solo para la prueba de la carrera). Un solo `git fetch --no-tags --depth=1 <remoto> +refs/heads/main:refs/remotes/<remoto>/main` (y `+refs/heads/web:refs/remotes/<remoto>/web` en la misma orden si existe: así las dos puntas son del mismo instante), `arbol_web` de la `main` traída, `comprobar_arbol` (con algo, `RamaWebError` y no se sube nada), y si el árbol es el de la punta de `web`, `None` («la rama web ya está al día»). Si no, `git commit-tree <árbol> [-p <punta de web>] -m "Web de main <12 cifras>"` con autor y committer `GitHub Actions <actions@github.com>` por entorno, y `git push <remoto> <commit>:refs/heads/web` **sin forzar**; si lo rechaza (otro la puso al día entretanto), vuelve a empezar desde el `fetch`, hasta `intentos`. Devuelve el commit subido. Con el árbol desde `AVISO_MB`, una línea de aviso en la salida. Así la rama nunca retrocede: un push que pasa sin forzar no tiene a nadie delante, y su `main` es la de ese mismo `fetch`.
  - `sitio(url: str) -> list[str]` — para el director: pide `<url><ruta>?h=<huella>` de cada entrada del precache del `sw.js` publicado y compara el SHA-1 del cuerpo con su huella; lo que no casa o no responde 200.
  - `class RamaWebError(Exception)`; CLI `python3 scripts/rama_web.py publicar | arbol [--commit C] | sitio URL`.
- `web.yml`: `on: push (branches: [main]), workflow_dispatch, schedule '41 */6 * * *'`; `permissions: contents: write`; `concurrency: {group: rama-web, cancel-in-progress: false}`; un job `web` en `ubuntu-24.04`, `timeout-minutes: 10`, con `actions/checkout@v5` (`ref: main`) y el paso `Poner al día la rama web` (`python3 scripts/rama_web.py publicar`). Comentario de cabecera: por qué existe (Pages publica `web`; el bot y la activación la ponen al día ellos mismos; este, tras un push a mano, a mano y cada 6 h por si alguno falló).
- `update.yml`: tras «Publicar diagnóstico…» y antes de «Lanzar la activación…», el paso `Poner al día la rama web` con `if: ${{ !cancelled() }}`, `continue-on-error: true` y `run: python3 scripts/rama_web.py publicar` (`data-health.json` también es de la web: sube tras el commit de datos y tras el de diagnóstico).
- `activar.yml`: el mismo paso tras «Publicar el fallo si las pruebas fallan», con `if: ${{ !cancelled() && steps.activar.outcome != 'skipped' }}` y `continue-on-error: true`. `ACTIVAR_STEPS` lo gana antes de `"Activación en rojo"`. Sin `gh workflow run`: los permisos de la activación no cambian.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_rama_web.py`:

```python
@pytest.mark.parametrize("ruta,web", [
    ("index.html", True), ("sw.js", True), (".nojekyll", True), ("data-health.json", True),
    ("data-lineups-2025-2026-FF1.js", True), ("dist/app-64f418c9.js", True), ("src/config.js", True),
    ("escudos/s/x.png", True), ("acta.css", True), ("data-history-2024.json", False),
    ("futbolbase.db", False), ("base/comun.db", False), ("scripts/generate_js.py", False),
    ("docs/decisiones.md", False), (".github/workflows/update.yml", False), ("README.md", False),
    ("pc/copia/README.md", False), ("sub/data-x.js", False)])
def test_es_web(ruta, web):
    assert es_web(ruta) is web

def test_lo_del_sitio_es_lo_de_copia_web():
    # DEL_SITIO de scripts/tests/copia-web.mjs (leído con una expresión regular) == WEB_FICHEROS y
    # WEB_CARPETAS (sin la barra) menos data-health.json y .nojekyll.
```
  - `test_arbol_web_del_repositorio`: sobre `HEAD` del árbol: `comprobar_arbol(...) == []`, ninguna ruta fuera de `es_web`, y menos de `PARADA_MB`.
  - Con un repositorio de mentira y su remoto desnudo (como `_run_commit_step`), con `index.html`, `sw.js` con su bloque, `dist/origen.json` y lo que nombran, `manifest.json`, iconos, `.nojekyll`, `data-x.js`, `scripts/x.py` y `futbolbase.db`: `test_publicar_crea_la_rama_y_no_repite` (la primera crea `web` sin padre y con solo lo de la web; la segunda devuelve `None` y el remoto no cambia; un commit en `main` que solo toca `scripts/x.py`, `None`; uno que toca `data-x.js`, un commit nuevo cuyo padre es el anterior y cuyos blobs son los de `main`), `test_publicar_no_retrocede` (con `_antes_de_subir`, otro clon sube una `main` más nueva y pone `web` al día con ella entre el `fetch` y el `push` del primero: el primero reintenta y la `web` final es la de la `main` más nueva) y `test_falta_uno_del_precache_y_no_se_publica` (sin el icono de 512: `RamaWebError` que lo nombra, y `web` no se crea).
  - En `test_workflows.py`: `test_web_yml` (disparadores, permisos, grupo `rama-web` sin cancelar, `publicar`), `test_el_bot_y_la_activacion_ponen_al_dia_la_web` (el paso, su posición, `!cancelled()` y `continue-on-error`), y `test_workflows_que_hay` con `web.yml`.
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_rama_web.py scripts/tests/test_workflows.py` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar.** En `docs/decisiones.md` («Publicar»): Pages publica la rama `web` (solo la web, sacada de `main`), la ponen al día el bot, la activación y `web.yml`, y nunca se fuerza. En `docs/almacenamiento.md`, el apartado «La web».
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs` — Expected: en verde.
- [ ] **Step 5: Commit.** Asunto: «Rama web: lo que publica Pages, sacado de main en cada subida».

**PASO DEL DIRECTOR — publicar la rama y cambiar Pages.** Con `R=malolocabreralolo-tech/futbol-base-v2` y la tarea 5 ya en marcha (el botón de descarga ya no es `./futbolbase.db`):
1. Push de la tarea 6 a `main` sin workflows en marcha. El push lanza `web.yml`, que crea la rama: `gh run watch -R $R $(gh run list -R $R --workflow web.yml -L 1 --json databaseId --jq '.[0].databaseId') --exit-status`.
2. Comprobación de la rama: `git fetch origin web && git ls-tree -r --name-only origin/web | grep -cE '^(scripts|base|docs|pc|\.github)/|^futbolbase\.db$'` da `0`; `git ls-tree -r --name-only origin/web | wc -l` da unos 855; `python3 scripts/rama_web.py arbol --commit origin/main` da el mismo árbol que `git rev-parse origin/web^{tree}`. Tras la pasada siguiente del bot, `web` tiene un commit nuevo (`git log -2 --oneline origin/web`).
3. El cambio: `gh api -X PUT repos/$R/pages --input - <<< '{"build_type": "legacy", "source": {"branch": "web", "path": "/"}}'`. Comprobación: `gh api repos/$R/pages --jq .source` da `{"branch":"web","path":"/"}`; `gh api -X POST repos/$R/pages/builds` y, hasta que salga `built`, `gh api repos/$R/pages/builds/latest --jq '{status, commit}'`, con `commit` igual a `git rev-parse origin/web`.
4. Comprobación del sitio (tras los 10 min de caché de Pages): `python3 scripts/rama_web.py sitio https://malolocabreralolo-tech.github.io/futbol-base-v2/` no dice nada; `curl -s -o /dev/null -w '%{http_code}\n'` da 200 para `index.html`, `sw.js` y `data-health.json`, y 404 para `futbolbase.db` y `scripts/generate_js.py`; la web, abierta en el móvil con la app instalada, se pone al día sola. Tras la pasada siguiente, `pages/builds/latest` es del commit nuevo de `web` (el push con `GITHUB_TOKEN` lanza la publicación «legacy»). Si no lo fuera, volver a `main` (paso 5) antes de nada más.
5. Vuelta atrás: `gh api -X PUT repos/$R/pages --input - <<< '{"build_type": "legacy", "source": {"branch": "main", "path": "/"}}'` y la misma comprobación con `main`. La rama `web` puede seguir poniéndose al día sin que nadie la publique.

---

### Task 7: Fase 3, `futbolbase.db` fuera de git

Dos commits: el del cambio (código, pruebas, workflows, `.gitignore` y `git rm --cached`), que se revierte entero, y el de los documentos.

**Files:**
- Modify: `scripts/db.py` (`get_connection`), `scripts/tests/conftest.py`, `scripts/base_sana.py`, `scripts/piezas.py` (`verificar --salud`), `.github/workflows/update.yml`, `activar.yml`, `tests.yml`, `detalle-federacion.yml`, `freno-fiflp.yml`, `.gitignore`; `git rm --cached futbolbase.db`
- Docs: `docs/almacenamiento.md`, `docs/decisiones.md:69,75`, `docs/SP-1-actas.md:29`, `docs/reconstruccion.md:55-58`, `docs/temporada-nueva.md:36-46`, `docs/alevin.md:76-92`, `docs/rediseno-rebase.md:9`, `README.md:50`
- Test: `scripts/tests/test_db.py` (nuevo), `scripts/tests/test_base_sana.py`, `scripts/tests/test_piezas.py`, `scripts/tests/test_workflows.py`, `scripts/tests/test_conftest_base.py` (nuevo)

**Interfaces:**
- Consumes: `piezas.verificar`, `source_health.set_base(…, pieza=…)` (tarea 5), `piezas.montar` y el fichero `<db>.piezas` (tarea 1).
- Produces:
  - `db.get_connection(db_path=None)`: si la ruta es `DB_PATH`, no existe y existe `base/piezas.json`, `FileNotFoundError("futbolbase.db no está montada: python3 scripts/piezas.py montar")` en vez de crear un fichero vacío. Con otra ruta, como hoy.
  - `scripts/tests/conftest.py`, `pytest_sessionstart`: con `base/piezas.json` en la raíz, si falta `futbolbase.db` y `GITHUB_ACTIONS == "true"`, `pytest.UsageError("futbolbase.db no está montada: python3 scripts/piezas.py montar")`; si están las dos y `futbolbase.db.piezas` no tiene el sha256 de `piezas.json`, `pytest.UsageError("futbolbase.db es de otras piezas: python3 scripts/piezas.py montar")`.
  - `base_sana.comprobar` deja de mirar el tamaño (`AVISO_MB`, `PARADA_MB` y `--salud` salen: la base ya no va en git); `{"ok", "motivos", "bytes"}`.
  - `piezas.py verificar --salud`: con la verificación bien, `source_health.set_base(bytes de la mayor, bytes >= AVISO_MB * MB, pieza=…)`, con `pieza` `"comun"` si la mayor es `comun.db` y, si no, su temporada (`actas-2025-2026.db` → `"2025-2026"`); el total se dice en la salida y no tiene límite (con ×7, unos 300 MB; GitHub recomienda repositorios de menos de unos GB, y lo que pesa en el repositorio son los originales de `scripts/`).
- Workflows:
  - `update.yml`: `Montar la base` sin `--contra`; «Base sana» con `run: python3 scripts/base_sana.py`; el paso de piezas con `verificar --salud`; en el commit, `git add -A base/` en lugar de `git add futbolbase.db`.
  - `activar.yml`: igual; «Subir la activación», `git add 'data-*.js' index.html sw.js` y `git add -A base/`; «Publicar el fallo», `git checkout HEAD -- base/ 'data-*.js' index.html sw.js data-health.json`, `git clean -fdq -- base/` (además de su `git clean` de hoy) y `python3 scripts/piezas.py montar` antes de `activar_auto.py --pruebas-fallaron` (que abre la base).
  - `tests.yml`: `Montar la base` sin `--contra`; fuera `'futbolbase.db'` de las rutas.
  - `detalle-federacion.yml` y `freno-fiflp.yml`: antes de su paso de Python, `Montar la base (solo la parte común)` con `run: python3 scripts/piezas.py montar --solo-comun` (hasta ahora no: en la fase 2 habría cambiado un fichero versionado y su `git pull --rebase` sin `--autostash` se habría negado a rebasar).
  - `.gitignore`: el comentario de los transitorios de SQLite deja de decir que la base va en git, y entran `/futbolbase.db` y `/futbolbase.db.piezas`.
  - `test_workflows.py`: `PUBLICADO` pierde `futbolbase.db`; `test_solo_el_bot_escribe_la_base` sigue (por `base/*`); `test_update_comprueba_la_base_antes_de_las_pruebas` con el `run` nuevo; el guion de diagnóstico con base mala (`test_guion_de_diagnostico_con_base_mala`) y `_run_commit_step`, con `base/` en lugar de `futbolbase.db`.

- [ ] **Step 1: Pruebas que fallan.**
  - `scripts/tests/test_db.py`: `test_get_connection_no_crea_la_base_sin_montar(tmp_path, monkeypatch)` (con `db.DB_PATH` y `db.PROJECT_ROOT` en `tmp_path` y un `base/piezas.json`: `FileNotFoundError` que dice «piezas.py montar», y el fichero no aparece; sin `base/`, la crea como hoy; con una ruta explícita en `tmp_path`, como hoy).
  - `scripts/tests/test_conftest_base.py`, con `pytester` (`pytest_plugins = ["pytester"]`) y una copia del `conftest.py` en una raíz de mentira: `test_en_ci_la_base_tiene_que_estar_montada` (sin base y `GITHUB_ACTIONS=true`: la sesión sale con error de uso y el texto); `test_en_local_sin_base_se_salta_como_hoy`; `test_base_de_otras_piezas` (el `.piezas` con otra huella: error de uso).
  - `test_base_sana.py`: fuera las pruebas del tamaño; una nueva, `test_el_tamano_ya_no_cuenta` (`comprobar` de una base buena devuelve exactamente las claves `ok`, `motivos` y `bytes`, y el módulo ya no tiene `AVISO_MB` ni `PARADA_MB`).
  - `test_piezas.py`: `test_verificar_salud_apunta_la_pieza_mayor` (con `AVISO_MB = 0`: el informe queda con `base.pieza` = la de la mayor; con el de verdad, sin `base`).
  - `test_workflows.py`: `test_ningun_workflow_sube_ni_restaura_futbolbase_db` (ningún `git add` ni `git checkout` de `futbolbase.db` en ningún workflow), `test_los_que_leen_la_base_la_montan` (`update.yml`, `activar.yml`, `tests.yml` job `pytest`, `detalle-federacion.yml` y `freno-fiflp.yml` montan antes de su primer paso de Python que la lee; los dos últimos con `--solo-comun`), y la pasada en seco de la tarea 3 sin `futbolbase.db` en el repositorio de mentira (el commit de la pasada 2 lleva solo `base/actas-2025-2026.db`, `base/piezas.json` y `data-x.js`).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_db.py scripts/tests/test_conftest_base.py scripts/tests/test_base_sana.py scripts/tests/test_piezas.py scripts/tests/test_workflows.py` — Expected: las nuevas fallan.
- [ ] **Step 3: Implementar** el código, los workflows y el `.gitignore`, y `git rm --cached futbolbase.db` (el fichero se queda en el árbol, ya ignorado).
- [ ] **Step 4: Ejecutar.** Run: `python3 scripts/piezas.py montar && python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && (cd pc/copia && python3 -m pytest tests -q -W error)` — Expected: `montada …` y todo en verde. (`montar` escribe la base de la raíz desde `base/` de la rama: es la misma que había.)
- [ ] **Step 5: Commit del cambio.** Asunto: «Parte D, fase 3: futbolbase.db sale de git; todos la montan de sus piezas».
- [ ] **Step 6: Documentos.** `docs/almacenamiento.md` (apartado «Fase 3» y cómo se trabaja en local: tras cada `git pull`, `python3 scripts/piezas.py montar`; para cambiar la base a mano, montar, la orden, `partir`, `verificar` y `git add -A base/`; la vuelta atrás); `docs/decisiones.md:69` (la base va en git en piezas, cada una por debajo de 95 MB; aviso desde 80 por la mayor) y `:75` (`base/` en lugar de `futbolbase.db`); `docs/SP-1-actas.md:29` (una frase: desde la parte D va en piezas); `docs/reconstruccion.md:55-58` (la copia del PC monta la de v2); `docs/temporada-nueva.md:36-46` y `docs/alevin.md:76-92` (montar antes, y `partir`, `verificar` y `git add -A base/` en lugar de `git add futbolbase.db`); `docs/rediseno-rebase.md:9` (`base/` en lugar de `futbolbase.db`, mismo `git checkout --ours`); `README.md:50` (`base/` y `futbolbase.db` montada, ignorada). Commit: «Documentación: la base en piezas».

**PASO DEL DIRECTOR — sacar la base de git.** Antes: la tarea 4 instalada en el PC, y la 5 y la 6 en marcha. Con el bot parado como en la tarea 3 (pasos 1-3):
1. `git push origin almacen:main` (rebasada; los dos commits de la tarea 7 en la punta).
2. Habilitar `update.yml` y `activar.yml`, lanzar una pasada y seguirla, como en la tarea 3 (paso 5).
3. Comprobación: `git ls-tree origin/main futbolbase.db` no da nada; el log trae `montada …`, `piezas iguales a la base: …` y, si subió algo, el commit lleva solo `base/` de la base; `gh workflow run tests.yml -R $R --ref main` sale en verde (el job `pytest` monta y las pruebas sobre la base real no se saltan: en su log, `test_db_sanity.py` con sus pruebas `PASSED`). Después, `gh workflow enable reloj.yml -R $R`. Al día siguiente, `futbol-base-copia estado` en el PC: `v2 … (aceptada)`.
4. Vuelta atrás, con el bot parado: en un clon limpio de `main`, `git revert --no-edit <commit del cambio>`, `python3 scripts/piezas.py montar` (con el revert, el `.gitignore` ya no la ignora y los workflows vuelven a la fase 2, que la quiere idéntica a las piezas: lo es), `git add futbolbase.db && git commit --amend --no-edit`, `git push origin main`, habilitar, una pasada y `reloj.yml`.

---

## Lo que queda para otro plan

- **`data-lineups` de las temporadas cerradas sin regenerar** (punto 6): lo de arriba, «Orden de publicación». Cuando se haga, la llave de cada temporada tiene que cubrir sus filas de las tres tablas, las de `matches` y `groups` de esa temporada, los nombres de sus equipos, la clave publicada de cada jugador que sale en ella y la versión del generador; y una prueba que cambie cada una de esas cosas por separado y vea el fichero regenerado.
- **Si la pieza común se acerca a 80 MB** (con ×7 se estima en 45-60): el mismo mecanismo admite partir por temporada otras tablas (`matches` por su grupo, `scorers` por su grupo) cambiando la lista de tablas por temporada y su filtro; no se hace ahora porque no hace falta.
