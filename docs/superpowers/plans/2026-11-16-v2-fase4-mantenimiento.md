# Fase 4 de v2 (mantenimiento): plan de implementación

> **Para quien lo ejecute:** SUB-SKILL OBLIGATORIA: superpowers:subagent-driven-development. Un constructor por tarea, revisión de quien dirige tras cada una, revisión final independiente antes de cada publicación.

**Objetivo:** que el bot de v2 tenga un solo camino para escribir la base, no pueda subir una base dañada, use versiones fijadas, escriba sus ficheros sin dejarlos a medias, y que quede comprobado qué parte de la base se puede rehacer desde los originales guardados; y dejar el código sin lo que ya no se usa y con los comentarios en su porqué.

**Arquitectura:** nada cambia en lo que el bot lee, en su cadencia ni en lo que publica. Se añade una comprobación de la base entre la lectura y las pruebas, se retiran los workflows heredados, se fija lo que hoy se instala «lo último», y se añade una herramienta de solo lectura (`scripts/reconstruir.py`) que rehace sobre una copia lo que tiene original. La web recibe tres retoques menores aparcados en la fase 3. El planificador del bot NO entra en este plan: va después, con plan propio (fase 4B), como manda el diseño («va el último»).

**Tecnología:** Python 3.11 (bot) y 3.12 (CI), SQLite, GitHub Actions, Node 22, esbuild 0.28.2 (solo al publicar), Playwright.

**Diseño:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (apartados 6, 7.8, 8). **Mapa del código (leerlo: trae `fichero:línea` de todo lo que se nombra aquí):** `docs/superpowers/plans/2026-11-16-v2-fase4-mapa.md`. Hallazgos de origen: `docs/revision-2026-11-13.md` (C3, C7, C8, C12, C13).

## Restricciones globales

- v1 no se toca: nada en `/home/manolo/claude/futbol-base`. Tampoco el árbol principal `/home/manolo/claude/futbol-base-v2`. Se trabaja solo en `/home/manolo/claude/futbol-base-v2-fase4` (rama `fase4`).
- Ninguna petición a `fiflp.com` ni ejecución del bot o de workflows desde el PC. Sin `git push`. Sin `git stash` a secas.
- Ningún dato personal se reduce ni se oculta. Ningún nombre de persona de los datos en pruebas, commits, documentos ni informes (ids o recuentos).
- Lo que el bot lee, cuándo lo lee y lo que publica no cambia: tras cada tarea, `git status --short` no enseña ningún `data-*.js`, ni `futbolbase.db`, ni `data-health.json` modificados.
- Pruebas primero donde hay lógica. Al entregar cada tarea, en verde: `python3 -m pytest scripts/tests -q`; la misma suite sin esbuild (copia del árbol sin `scripts/empaquetar/node_modules`); `node --test scripts/tests/test_*.mjs`; `python3 scripts/precache.py --check` y `python3 scripts/codigo.py --check`. Si la tarea toca `src/`, `sw.js`, `index.html` o `acta.css`: además los cinco smokes (`node scripts/tests/{render,interaction,pwa,aislamiento,frescura}-smoke.mjs`) y `dist/` reempaquetado con `python3 scripts/codigo.py`.
- Idioma: español (código, comentarios, commits, documentos). Comentarios: el porqué en una frase; nada de historia.
- Commits terminados en `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.
- Los constructores no lanzan subagentes. Si un paso no se puede hacer como está escrito o cambia lo que ve el usuario, no se improvisa: se deja sin hacer y se dice en el informe.

## Foco de la revisión

Lo que el diseño implica y ninguna prueba de una tarea cubre por sí sola; cada línea tiene su prueba en la tarea que se indica.

1. Una pasada cuya base no pasa la comprobación no publica ni datos ni base, y la portada lo dice (T3: prueba del guion del paso con una base dañada).
2. Un corte a mitad de una escritura deja el fichero anterior entero, no uno truncado (T2: prueba que hace fallar la escritura).
3. Tras retirar workflows, ninguno que quede puede subir `futbolbase.db` o `data-*.js` fuera del grupo `update-data` (T1: prueba que recorre todos los YAML).
4. El bot sin esbuild y con las dependencias del fichero fijado sigue pasando su suite (T4: paso de CI que instala desde el fichero).
5. La herramienta de reconstrucción nunca escribe en la base real (T5: prueba que compara la huella de `futbolbase.db` antes y después).

---

# Parte I — el bot (se publica junta, entre semana)

### Task 1: Un solo escritor de la base

**Ficheros:**
- Borrar: `.github/workflows/fetch-fiflp-actas.yml`, `fetch-fiflp.yml`, `fetch-fiflp-cups-2324.yml`, `fetch-fiflp-cups.yml`, `fetch-wayback-2324.yml`, `debug-fiflp-copa.yml`.
- Mover a `scripts/_archive/` (con `git mv`): `scripts/update.sh`, `scripts/debug_fiflp_copa.py`, `scripts/fetch_fiflp_cups_2324.py`, `scripts/fetch_fiflp_cups_2526.py`, `scripts/fetch_wayback_2324.py`.
- Modificar: `.github/workflows/discover-fiflp.yml`, `fetch-fiflp-islas.yml`; `scripts/tests/test_workflows.py`, `scripts/tests/test_actas_lotes.py`; `docs/federacion.md`, `docs/identidad.md`, `docs/temporada-nueva.md`, `README.md` (donde nombren lo retirado).

**Qué queda:** 11 workflows. Escriben la base o `data-*.js`: solo `update.yml` y `activar.yml`, los dos en `update-data`. `discover-fiflp.yml` y `fetch-fiflp-islas.yml` (manuales, vigentes) pasan al grupo `update-data` (`cancel-in-progress: false`), dejan `git stash` por `git pull --rebase --autostash` con tres reintentos como `update.yml:138-144`, suben a `checkout@v5`/`setup-python@v6`, y `fetch-fiflp-islas.yml` pasa `inputs.temporada` e `inputs.ids` por `env:` en vez de interpolarlos en el `run`.

- [ ] **Paso 1 (pruebas, en rojo):** en `test_workflows.py`:
  - `test_solo_el_bot_escribe_la_base`: para cada YAML de `.github/workflows/`, si algún `run` contiene `git add` de una ruta que case con `futbolbase.db` o `data-*.js` o `index.html` o `sw.js`, entonces `concurrency.group == 'update-data'`; y el conjunto de los que lo hacen es exactamente `{'update.yml', 'activar.yml'}`.
  - `test_quien_sube_va_en_cola`: todo workflow con `git push` en algún `run` tiene `concurrency.group` y no usa `git stash`.
  - `test_workflows_que_hay`: el conjunto de ficheros es exactamente los 11 (sustituye al `len(workflows) >= 10` de `:737-741`).
  - `test_islas_entradas_por_env`: ningún `run` de `fetch-fiflp-islas.yml` contiene `${{ inputs.`.
  - Quitar las pruebas de los workflows retirados (`OWNED` `:44`, `:744-878`) y la lectura de `fetch-fiflp-actas.yml` en `test_actas_lotes.py:796-797`; lo que esas pruebas protegían y siga existiendo en `actas-federacion.yml` no se pierde (comprobarlo una a una y decirlo en el informe).
- [ ] **Paso 2:** borrar, mover y editar. Buscar con `grep -rn` cada nombre retirado en todo el repo (menos `docs/superpowers/` y `docs/revision-2026-11-13.md`, que son historia) y corregir el texto: `docs/federacion.md:237-241` debe describir `actas-federacion.yml` como el procedimiento vigente.
- [ ] **Paso 3:** suites en verde; commit.

### Task 2: Escritura atómica de originales, estado y ficheros publicados

**Ficheros:**
- Crear: `scripts/escritura.py`, `scripts/tests/test_escritura.py`.
- Modificar (los sitios «no» de la tabla del mapa §3): `fetch_fiflp_actas.py` (`:286`, `:881`, `:884`, `:920`), `fetch_fiflp_goleadores.py:54`, `fetch_fiflp_detalle.py:96`, `fetch_fp_app.py:162`, `discover_fiflp_comps.py:109`, `import_fiflp_actas.py:413`, `fetch_fiflp_islas.py:199`, `source_health.py` (`:256`, `:341`), `activar_auto.py` (`:316`, `:336`), `generate_js.py` (`write_file` `:1653`, `write_lineups` `:905`, `write_jugadores` `:1102`, `:1536`, `:1543`, `bump_cache_version` `:1622`, `:1634`), `precache.py:123`, `codigo.py` (`:150`, `:153`).

**Interfaz que produce:**
```python
# scripts/escritura.py
def escribir_atomico(path, contenido, *, encoding="utf-8") -> None:
    """`contenido` (str o bytes) acaba en `path` entero o no acaba: temporal en la misma carpeta,
    fsync, os.replace. Si algo falla, el fichero de antes queda intacto y el temporal se borra."""
```
Permisos del fichero nuevo: los del que sustituye, o 0o644 si no existía. El temporal se llama `<nombre>.<aleatorio>.tmp` (añadir `*.tmp` a `.gitignore` si no está).

- [ ] **Paso 1 (pruebas, en rojo)** en `test_escritura.py`:
  - `test_escribe_texto_y_bytes`; `test_permisos_644_en_fichero_nuevo`; `test_conserva_permisos_del_que_sustituye`.
  - `test_un_fallo_deja_el_anterior_entero`: con `os.replace` sustituido por uno que lanza `OSError`, el fichero conserva su contenido anterior, la llamada lanza, y en la carpeta no queda ningún `*.tmp`.
  - `test_fallo_al_escribir_no_deja_temporal`: `contenido` de un tipo no válido → `TypeError`, sin temporal.
  - `test_nadie_escribe_a_pelo`: recorre con `ast` los módulos de la lista de «Modificar» y falla si queda una llamada a `open(` con modo de escritura, `.write_text(` o `.write_bytes(` fuera de una lista `PERMITIDAS = {(fichero, función): motivo}` escrita en la prueba (por ejemplo, escrituras en una carpeta temporal propia). La lista permitida, lo más corta posible y con su motivo.
- [ ] **Paso 2:** implementar y sustituir sitio a sitio. El texto que se escribe no cambia en un solo byte: comprobarlo generando con `python3 scripts/generate_js.py` en una copia del árbol antes y después (mismos `sha1` de todos los `data-*.js`, `index.html` y `sw.js`).
- [ ] **Paso 3:** suites en verde; commit.

### Task 3: La base se comprueba antes de subirla, y avisa cuando crece

**Ficheros:**
- Crear: `scripts/base_sana.py`, `scripts/tests/test_base_sana.py`.
- Modificar: `.github/workflows/update.yml`, `.github/workflows/activar.yml`, `scripts/source_health.py`, `scripts/tests/test_workflows.py`, `scripts/tests/test_db_sanity.py`, `docs/federacion.md`.

**Interfaz que produce:**
```python
# scripts/base_sana.py
AVISO_MB = 80     # desde aquí, la web lo dice
PARADA_MB = 95    # desde aquí no se sube: GitHub rechaza ficheros de 100 MB

def comprobar(db_path) -> dict:
    """{'ok': bool, 'motivos': [str], 'bytes': int, 'aviso': bool}. Vuelca el WAL al fichero
    (wal_checkpoint(TRUNCATE)), y mira: que no quede `-wal` con contenido, PRAGMA integrity_check,
    PRAGMA foreign_key_check, y el tamaño."""
# CLI: python3 scripts/base_sana.py [--db futbolbase.db] [--salud]
#   imprime una línea por motivo; sale con 1 si no es ok. Con --salud, además deja el tamaño en
#   data-health.json (source_health.set_base).
```
```python
# scripts/source_health.py
def set_base(bytes_, aviso, path=REPORT_PATH) -> None:
    """Con aviso, `base: {"mb": <entero>, "limite": 100}` en el informe del disco; sin aviso, quita la
    clave. No toca nada más ni reescribe el fichero si no cambia."""
```
`source_health.finish` conserva la clave `base` del informe anterior tal cual (la pone y la quita solo `set_base`), y su presencia no es motivo para reescribir el informe.
Motivos (texto exacto): `la base de datos no pasa la comprobación de integridad: <primer mensaje, 200 caracteres>`; `la base de datos tiene referencias rotas: <n> filas`; `quedan datos sin volcar a la base (-wal)`; `la base de datos ocupa <n> MB y GitHub no admite más de 100`.

**En los workflows:**
- `update.yml`: paso nuevo `id: base`, «Base sana (bloquea el commit si falla)», después de `scrape` y antes de `pytest`, con `if: steps.scrape.outcome == 'success'`: `python3 scripts/base_sana.py --salud`. El paso «Publicar diagnóstico…» (`:150-162`) añade `|| steps.base.outcome == 'failure'` a su condición; con la base mal, el motivo que marca es `la base de datos no pasó la comprobación: los datos de esta pasada no se publicaron`. Las pruebas no corren si `base` falla (`if:` de `pytest` y `node` con `steps.base.outcome == 'success'`).
- `activar.yml`: la misma comprobación antes de sus suites; si falla, el mismo camino que cuando fallan las pruebas (`AA --pruebas-fallaron`, `:195-198`).

- [ ] **Paso 1 (pruebas, en rojo)** en `test_base_sana.py`, con bases de fixture creadas en la prueba (`tmp_path`):
  - `test_base_buena_ok`; `test_referencia_rota_no_ok` (fila hija sin madre, con `foreign_keys=OFF` al crearla); `test_fichero_danado_no_ok` (bytes de una página pisados con ceros: `ok` falso y motivo de integridad, sin excepción); `test_fichero_que_no_es_sqlite_no_ok`.
  - `test_vuelca_el_wal`: una conexión en WAL con una escritura sin volcar y sin cerrar → tras `comprobar`, los datos están en el fichero principal y no queda `-wal` con contenido.
  - `test_aviso_y_parada_por_tamano`: con `AVISO_MB`/`PARADA_MB` parcheados a valores pequeños: por debajo, sin aviso; entre los dos, `aviso` y `ok`; por encima, `ok` falso con el motivo de tamaño.
  - `test_cli_sale_con_1_y_dice_el_motivo`; `test_salud_escribe_y_quita_la_clave` (`set_base`: aparece con aviso, desaparece sin él, y sin cambio no reescribe: mismo `mtime`); `test_finish_conserva_base` (en `test_source_health.py`: un informe anterior con `base` y una pasada sin cambios → `finish` no reescribe, y si reescribe por otro motivo, `base` sigue).
  - En `test_db_sanity.py`: `test_la_base_publicada_pasa_base_sana` (sobre una copia de la base real: `ok`, sin aviso).
  - En `test_workflows.py`: `test_update_comprueba_la_base_antes_de_las_pruebas` (orden de pasos `scrape` < `base` < `pytest` < commit; condiciones) y `test_activar_comprueba_la_base`.
  - `test_guion_de_diagnostico_con_base_mala`: extrae el `run` del paso de diagnóstico de `update.yml` y lo ejecuta en un repo git temporal con `data-health.json` de fixture y `SCRAPE_OUTCOME=success` (como hacen las pruebas que ya ejecutan guiones de workflow en `test_workflows.py`; si ninguna lo hace, comprobar el texto del guion): acaba con `runHealth.ok` falso y el motivo exacto.
- [ ] **Paso 2:** implementar. `comprobar` no lanza nunca por una base mala: lo devuelve.
- [ ] **Paso 3:** ensayo en una copia del árbol en el scratchpad (nunca enlaces simbólicos): base buena → sale 0 y `git status` no enseña `futbolbase.db` modificada; base con una página pisada → sale 1.
- [ ] **Paso 4:** `docs/federacion.md`: un párrafo corto en el apartado del bot. Suites en verde; commit.

### Task 4: Dependencias fijadas

**Ficheros:**
- Crear: `scripts/requirements-tests.txt` (`pytest==…`, `pyyaml==…`), `scripts/requirements-bot.txt` (`-r requirements-tests.txt` y `playwright==…`).
- Modificar: todos los workflows que instalan con `pip`; `update.yml` y `activar.yml` (Node); `scripts/tests/test_workflows.py`; `docs/federacion.md`.

**Las versiones:** las que instaló la última pasada en verde del bot, leídas de su registro: `gh run list -R malolocabreralolo-tech/futbol-base-v2 --workflow update.yml --status success --limit 1` y `gh run view <id> -R … --log | grep -i "Successfully installed"` (leer el registro está permitido; no lanzar nada). Si el registro no las trae, las últimas publicadas en PyPI hoy, y decirlo en el informe. `playwright` de Python queda en la versión que usa el bot hoy aunque no sea la 1.58.0 de las pruebas de Node: no se cambia de navegador en esta tarea.

- [ ] **Paso 1 (pruebas, en rojo)** en `test_workflows.py`:
  - `test_pip_solo_desde_los_ficheros`: ningún `run` contiene `pip install` sin `-r scripts/requirements-`.
  - `test_requisitos_fijados`: cada línea de los dos ficheros que no sea `-r` casa con `^[a-z0-9_-]+==\d+(\.\d+)+$`.
  - `test_ci_sin_playwright_de_python`: `tests.yml` instala `requirements-tests.txt` y no `requirements-bot.txt` (sigue valiendo `:694`).
  - `test_node_fijado_en_el_bot`: `update.yml` y `activar.yml` usan `actions/setup-node` con `node-version: '22'` antes de su paso `node --test`.
- [ ] **Paso 2:** implementar. `tests.yml` gana un paso «Dependencias del bot instalables» que hace `pip install --dry-run -r scripts/requirements-bot.txt` (comprueba que el fichero se resuelve, sin instalar Playwright).
- [ ] **Paso 3:** suites en verde; commit.

### Task 5: Qué se puede rehacer desde los originales, comprobado

**Ficheros:**
- Crear: `scripts/reconstruir.py`, `scripts/tests/test_reconstruir.py`, `docs/reconstruccion.md`.
- Modificar: `.github/workflows/tests.yml`, `scripts/tests/test_workflows.py`, `README.md` (una línea con el enlace).

**Qué es:** el diseño pide «una prueba de reconstruir desde los originales da lo publicado, o la lista explícita y justificada de lo que no se puede rehacer». El mapa (§2) dice que entera no se puede (lo leído en vivo no deja original; siete temporadas vienen de importaciones hechas a mano una vez). Se hace lo comprobable: por dominios, sobre una copia.

**Interfaz que produce:**
```python
# scripts/reconstruir.py
@dataclass(frozen=True)
class Dominio:
    nombre: str            # 'app', 'torneos', 'actas_bot', 'actas', 'goleadores', 'detalle', 'portal'
    tablas: tuple          # las que rehace
    originales: tuple      # globs relativos a la raíz
    rehacible: bool        # lo declarado: lo que la prueba exige

DOMINIOS: tuple[Dominio, ...]

def comprobar(db_path, root, dominios=None) -> dict:
    """{nombre: {'igual': bool, 'filas': int, 'distintas': int, 'detalle': str}}. Trabaja SIEMPRE sobre
    una copia de `db_path` en una carpeta temporal (API backup de sqlite3): en la copia borra las filas del
    dominio y su marca en raw_imports, vuelve a importar con el importador del bot, y compara con la base
    original fila a fila por clave natural (no por ids autoincrementales)."""
# CLI: python3 scripts/reconstruir.py --comprobar [--dominio X]   (sale con 1 si un dominio declarado
#      rehacible no sale igual)
```
- `actas_bot`: las alineaciones, sucesos y cuerpo técnico de los partidos de 2026-27 cuyo original está en `scripts/actas_bot_*.jsonl`, rehechos pasando el original guardado por el mismo camino que usa el bot al leer un acta (`update_fiflp.import_actas` y `fiflp_acta`, mapa §2.1 y §6.1). Hoy ningún importador lo hace: es código nuevo, solo de esta herramienta.
- Mínimo exigido como `rehacible=True` y en verde: `app`, `torneos`, `actas_bot`. Los demás (`actas` de temporadas pasadas, `goleadores`, `detalle`, `portal`) se prueban: el que salga igual queda `rehacible=True`; el que no, `rehacible=False` con su diferencia medida y su causa en el documento. No se cambia ningún importador del bot para que salga igual.

**`docs/reconstruccion.md`** (corto, tabla): por cada tabla de la base, de qué original sale y si está comprobado que se rehace; y la lista de lo que no se puede rehacer, cada cosa con su porqué en una línea y dónde está su única copia (la base, y la copia diaria del PC). Sin nombres de personas.

- [ ] **Paso 1 (pruebas)** en `test_reconstruir.py`:
  - Siempre (rápidas, con una base de fixture mínima): `test_comprobar_no_toca_la_base` (sha1 de la base antes y después); `test_un_dominio_que_difiere_lo_dice` (dominio de prueba cuyo «rehacer» cambia una fila → `igual` falso, `distintas == 1`); `test_cli_sale_con_1_si_un_rehacible_difiere`.
  - Solo con `RECONSTRUIR=1` (lenta, sobre la base real): `test_los_dominios_rehacibles_salen_iguales` (cada `Dominio` con `rehacible=True` da `igual`) y `test_el_documento_dice_lo_mismo` (los nombres con `rehacible=True` son los que `docs/reconstruccion.md` marca como comprobados).
  - `test_workflows.py`: `tests.yml` tiene un paso con `RECONSTRUIR=1` que pasa esa prueba.
- [ ] **Paso 2:** implementar dominio a dominio, midiendo. Tiempo de la prueba lenta, en el informe.
- [ ] **Paso 3:** suites en verde (la lenta también, una vez, con su salida en el informe); commit.

**Publicar la parte I** (quien dirige): revisión final independiente de las tareas 1 a 5; fusionar `origin/main`; suites con y sin esbuild; entre dos pasadas, un día sin partidos, `git push origin fase4:main`; mirar entera la primera pasada del bot (paso «Base sana» en verde, mismas versiones instaladas que antes, commit de datos normal) y `Tests`. Si la pasada sale roja por algo de esta parte: `git revert` del commit de fusión y volver a mirar.

---

# Parte II — la web y la limpieza

### Task 6: Tres menores de la web aparcados en la fase 3, y el aviso de base grande

**Ficheros:** `sw.js`, `src/actualizacion.js`, `src/state.js`, `src/estado.js`, `src/screen-fuentes.js`; pruebas: `scripts/tests/test_sw_precache.mjs`, la de `actualizacion` y la de `estado` que ya existen (`grep -l actualizacion scripts/tests/*.mjs`), `scripts/tests/frescura-smoke.mjs`; `dist/` (reempaquetar).

- **M5 — segunda vía para enterarse de la versión.** `sw.js`: un oyente `message` que a `{type: 'version?'}` contesta a quien pregunta con `{type: 'version', version}` (el mismo mensaje que ya manda `activar`). `src/actualizacion.js`: al arrancar y cada vez que la página vuelve a primer plano, si hay un SW al mando, le pregunta. Lo que la página hace con la respuesta no cambia (solo actúa con una versión estrictamente mayor).
- **M9 — la salud «de la copia» no se recuerda diez minutos.** `src/state.js`: una respuesta con `fromCache` se recuerda `HEALTH_TTL_COPIA_MS = 30000`, no `HEALTH_TTL_MS`.
- **R2 —** prueba de que `reponer` nunca rechaza (con un `cache.keys()` que rechaza).
- **Aviso de base grande.** `src/estado.js`: si `health.base` es `{mb: número}`, una línea más en el estado de la portada y en Fuentes: `La base de datos ocupa <mb> MB de los 100 que admite GitHub.` Texto fijo, número validado (entero entre 1 y 1000; si no, nada).

- [ ] **Paso 1 (pruebas, en rojo):** `sw contesta a version?` (el mensaje llega a `event.source`, con la versión de `CACHE_NAME`; otro `type` no contesta nada); `la página pregunta al arrancar y al volver` (con un `controller` simulado: un `postMessage` cada vez; sin `controller`, ninguno y sin error); `una versión mayor por esta vía hace lo mismo que por activate`; `salud fromCache caduca a los 30 s` (reloj simulado); `reponer no rechaza`; `aviso de base` (con `{mb: 83}` sale el texto exacto; con `{mb: 'x'}`, `{}` o sin clave, no sale). En `frescura-smoke.mjs`, un caso 9: página abierta con la versión vieja y el SW nuevo ya al mando sin que la página recibiera el mensaje (se descarta el mensaje de `activate` en la página con un oyente de captura) → al volver a primer plano, la página se pone al día.
- [ ] **Paso 2:** implementar; `python3 scripts/codigo.py`; capturas a 390 px (claro y oscuro) de la portada y de Fuentes con el aviso de base, con el mundo de fixtures; mirarlas.
- [ ] **Paso 3:** suites y los cinco smokes en verde (frescura, tres veces); commit.

### Task 7: Lo que ya no usa nadie, a `_archive`

**Ficheros:** `git mv` a `scripts/_archive/` de los que el mapa §6.3 da como «nadie»: `scrape_fiflp_2024.py`, `fetch_fiflp_history.py`, `fetch_wayback_2122.py`, `fetch_wayback_2223.py`, `fetch_wayback_2425.py`, `import_existing.py`, `fetch_fiflp_2324.py`, `verify_2425_fill.py`, `refresh_scorers.py`, `fetch_mygol.py`, `sync_versions.py`. Documentos que los nombren.

- No se mueve nada que importe el bot, una prueba o un workflow (comprobar cada uno con `grep -rn "<módulo>"` en `scripts/`, `.github/`, `pc/`, `docs/` antes de moverlo; si alguno resulta usado, se queda y se dice). Los importadores de un solo uso que tienen pruebas se quedan donde están: son la única descripción ejecutable de cómo se construyó el histórico. Los ficheros de datos originales no se mueven ni se borran.
- [ ] **Paso 1:** prueba `scripts/tests/test_archivo.py::test_nada_vivo_importa_del_archivo`: ningún `.py` de `scripts/` (fuera de `_archive/`) ni workflow nombra un módulo que solo exista en `scripts/_archive/`.
- [ ] **Paso 2:** mover; corregir documentos; suites en verde; commit.

### Task 8: Comentarios en su porqué (código de la web y del bot) y `docs/decisiones.md`

**Ficheros:** `src/*.js`, `sw.js`, `index.html`, `scripts/*.py`, `scripts/*.mjs` (no `scripts/tests/`, no `scripts/_archive/`); crear `docs/decisiones.md` y `scripts/tests/solo_comentarios.py`.

- Regla: cada comentario dice por qué el código es así, en una frase o dos, en presente. Fuera: números de decisión, rondas, planes, tareas, fechas, «antes hacía», quién lo pidió. Si el porqué solo se entiende con la historia, la historia va en una línea de `docs/decisiones.md` y el comentario la resume sin citarla. Un comentario que solo repite el código se quita. Los que avisan de una trampa real (la federación, el orden de importación, GitHub Pages) se quedan, cortos.
- `docs/decisiones.md` (menos de 150 líneas): las decisiones vigentes que explican algo no evidente del código, agrupadas (web, service worker, bot, base, publicación), una línea cada una, con el fichero al que afecta. No es un historial.
- **Guardia:** `scripts/tests/solo_comentarios.py <commit base>`: para cada fichero cambiado desde ese commit comprueba que el código sin comentarios es idéntico. Python: comparar los tokens de `tokenize` sin `COMMENT`, `NL`, ni espacios finales; cadenas de documentación sí pueden cambiar (comparar `ast.dump` sin docstrings). JavaScript y `index.html`: el paquete de `python3 scripts/codigo.py` da la misma huella de `dist/app-*.js` que antes (esbuild quita los comentarios) y, para `sw.js` e `index.html`, igualdad tras quitar comentarios con esbuild/una expresión regular de comentarios HTML. Sale con 1 y dice el fichero si algo que no es comentario cambió.
- [ ] **Paso 1:** escribir la guardia y probarla con un cambio de código a propósito (tiene que dar rojo) y uno de comentario (verde).
- [ ] **Paso 2:** reescribir comentarios, por carpetas, pasando la guardia en cada commit: primero `src/` + `sw.js` + `index.html`; luego `scripts/`.
- [ ] **Paso 3:** `grep -rnE "decisión [0-9]+|ronda de arreglos|[Pp]lan [AB][0-9]|de B[1-5]\b" src sw.js index.html scripts/*.py scripts/*.mjs` → vacío. Suites y smokes en verde; `dist/` con la misma huella de `app`.

### Task 9: Comentarios de las pruebas

**Ficheros:** `scripts/tests/*` (mismo criterio y la misma guardia que la tarea 8). Los nombres de las pruebas no cambian. Las referencias a hallazgos que explican por qué existe una prueba se sustituyen por el porqué en una frase.

- [ ] **Paso 1:** por lotes de unos 25 ficheros, guardia en cada commit; suites en verde al final.

**Publicar la parte II** (quien dirige): revisión final independiente de las tareas 6 a 9; fusionar `origin/main` (en `index.html` y `sw.js`, la estructura de la rama con la versión y «Última actualización» de `main`); `python3 scripts/publicar.py`; suites con y sin esbuild, node y los cinco smokes; entre dos pasadas, `git push origin fase4:main`; captura de la web publicada; primera pasada del bot detrás, mirada entera.

---

# Lo que este plan deja fuera, a propósito

- **El planificador del bot** (mapa §8, unas 1.100 líneas, y el estado que se pierde cuando no se sube la base, C12): plan propio, fase 4B, cuando esto esté publicado. Solo entra si las simulaciones (`test_bot_pasada_corta.py:638`) dan una frescura igual o mejor.
- **Menores de la fase 3 que se aceptan como límite conocido** y se apuntan en `docs/decisiones.md` (tarea 8): M2 (una `?v=` con dos contenidos en la caché en memoria de Chrome durante un despliegue), M6 (`src/config.js` de la versión anterior el día en que se activa una temporada), M8 (los datos que se piden al entrar en una pantalla no se verifican por huella), R1 (el tope de 15 s cubre hasta las cabeceras).
- **Mover los lectores que el bot importa de guiones de un solo uso** (`fetch_fiflp_2425`, `clean_team_name`, `COMP_META`): funcionan y moverlos es riesgo sin beneficio para el usuario.
- **Escudos que faltan** (4 equipos de 2026-27): hay que bajarlos de la federación, que solo contesta desde Actions.
- **La etiqueta «( Única )»**: mirada en la web publicada el 15/11: no se ve en ninguna pantalla.
- Acciones de GitHub fijadas por SHA; fechas de `matches.date` en tres formatos (deuda anotada en el diseño).
