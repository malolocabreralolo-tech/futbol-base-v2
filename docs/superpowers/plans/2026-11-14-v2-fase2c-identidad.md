# v2, fase 2C: quién es cada niño

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que cada niño tenga su historial y solo el suyo (objetivo O5 del diseño), que todo jugador tenga ficha, y que el bot guarde el original de cada acta que lee.

**Architecture:** la tabla `players` pasa a guardar **identidades de acta** (lo que el acta dice con certeza: un identificador de la federación, o un nombre sin identificador en un equipo y una temporada). Las apariciones y los sucesos cuelgan siempre de la identidad de acta y no se vuelven a mover. Encima, una capa de **fichas**: `players.ficha_id` apunta a la identidad principal de la ficha a la que pertenece, y `players.union_por` dice por qué se unió. Esa capa la recalcula entera, de forma determinista e idempotente, un resolvedor puro (`scripts/identidad.py`); deshacer una unión es cambiar un puntero. La web publica una ficha por ficha, con clave propia para las que no tienen identificador y con alias para que ningún enlace antiguo se rompa.

**Tech Stack:** Python 3 + SQLite (pytest), módulos ES (`node --test`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O5, 7.6, sección 2 entera). Mapa del código: `docs/superpowers/plans/2026-11-13-v2-fase2-mapa.md`, bloques D y E y trampas 11 a 15.

## Lo medido el 14/11/2026 (base de `main`, 17.661 jugadores)

Sobre los originales (`scripts/fiflp_actas_*_raw.json`, 2019-20 a 2025-26), que dicen de cada jugador de cada acta si venía con identificador:

1. **Sin identificador viene solo la liga prebenjamín de Gran Canaria desde 2024-25** (11.261 apariciones en 2024-25 y 11.100 en 2025-26; hasta 2023-24 venía con identificador), más unas decenas sueltas al año en benjamín y los goleadores que no están en la alineación (siempre sin identificador).
2. **El identificador de la federación no es único por niño.** Hay 1.542 niños con varias filas: mismo nombre completo, mismo equipo, misma temporada y otro identificador. Sobran 2.801 filas; 2.791 tienen exactamente 1 aparición (la federación dio un identificador de un solo uso en esa acta). Temporadas 2019-20 a 2024-25; ninguna en 2025-26 ni 2026-27.
3. **Modelo de edad** (año de nacimiento posible de quien juega en la temporada que empieza el año `Y`): prebenjamín `[Y-7, Y-5]`, benjamín `[Y-9, Y-6]`, alevín `[Y-11, Y-8]`. Un conjunto de apariciones es posible si la intersección de sus intervalos no es vacía. Entre los 15.266 jugadores con identificador de los originales, todos los pares (diferencia de temporadas, diferencia de nivel) observados caben en el modelo: (0,+1) 138, (1,−1) 32, (1,0) 7.410, (1,+1) 1.877, (2,0) 925, (2,+1) 2.145, (3,0) 101, (3,+1) 525, (4,+1) 74; ninguno a 5 años o más ni (2,−1).
4. Con ese modelo, hoy hay 15 filas imposibles por edad (todas con identificador, mezcladas por nombre).

## Global Constraints

- **No se quita, abrevia ni oculta ningún nombre ni ningún dato.** Ninguna aparición, suceso, gol, partido ni jugador se pierde: los recuentos de `appearances`, `match_events`, `matches`, `goals`, `scorers` y `match_staff_all` son idénticos antes y después de la migración; en `players` no desaparece ninguna fila (solo se añaden).
- **Ante la duda, dos fichas mejor que una mezclada.**
- Toda unión que no venga de un mismo identificador queda marcada (`union_por`) y se deshace poniendo `ficha_id` a `NULL`.
- Ninguna operación sobre `futbolbase.db` de la rama: la migración se desarrolla y se ensaya sobre una **copia** (`cp futbolbase.db <scratch>/ensayo.db`). Aplicarla a la base viva lo hace el controlador, con el bot parado y copia previa comprobada.
- Nada contra fiflp.com ni GitHub desde local. No se toca v1 ni se nombra su repositorio.
- El bot no pide más páginas por pasada que hoy (`MAX_ACTAS_PER_RUN = 60`): la relectura va dentro de ese cupo.
- Idioma: español. Estilo: el del código vecino.
- Suites completas en verde al acabar cada tarea: `python3 -m pytest scripts/tests -q` y `node --test scripts/tests/test_*.mjs`.
- Rama `fase2c`, en `/home/manolo/claude/futbol-base-v2-fase2c`. Sin `git push`, sin tocar `main`.
- Commits en español terminados con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```

## Las reglas (deciden; no se reabren en la implementación)

**Identidad de acta** (una fila de `players`):
- con identificador de la federación: una fila por `fiflp_id` (como hoy, con `norm_name` `NOMBRE` o `NOMBRE#id`);
- sin identificador: una fila por (nombre normalizado, equipo, temporada). Dos apariciones sin identificador con el mismo nombre en el mismo equipo y la misma temporada son la misma identidad; en otro equipo u otra temporada, otra.
- dos jugadores sin identificador con el mismo nombre en la **misma alineación** (dos «DANIEL» en un equipo): el de dorsal más bajo es la identidad normal y el siguiente lleva ordinal (`…#2`, `…#3`), que forma parte de su identidad en ese equipo y temporada. Es una aproximación (el dorsal puede cambiar de un partido a otro) y `docs/identidad.md` lo dice; lo que no puede pasar es que se pierda una aparición o falle el acta.

**Nombre completo**: lleva coma, dos o más palabras antes de la coma y al menos una después («APELLIDO APELLIDO, NOMBRE»). Todo lo demás (nombre de pila suelto, un solo apellido) es **nombre corto**.

**Club de un equipo**: el nombre del equipo sin la letra final de filial (` B`, ` "B"`, ` C`…). Si el proyecto ya tiene una función para eso, se usa esa.

**Compatibles**: dos conjuntos de identidades son compatibles si (a) la intersección de los intervalos de edad de todas sus apariciones no es vacía y (b) no hay solape imposible: en una misma temporada y categoría, dos clubes distintos cuyos rangos de fechas de partidos se cruzan.

**Uniones** (por este orden; cada una trabaja sobre las fichas que dejó la anterior):
- **U0, identificador de un solo uso.** Identidades con el mismo nombre completo que comparten equipo y temporada → la misma ficha. `union_por = 'equipo'`.
- **U1, mismo club, temporadas seguidas.** Identidades sin identificador con el mismo nombre (completo o corto), del mismo club, en temporadas consecutivas y compatibles → la misma ficha. `union_por = 'club'`. Los nombres cortos solo si la medida del paso 2 de la tarea 2 da una precisión del 95 % o más; si no, los cortos no se unen nunca.
- **U2, candidata única.** Una ficha sin ningún identificador y de nombre completo se une a otra ficha cuando es la **única** otra ficha con ese mismo nombre normalizado y son compatibles. `union_por = 'nombre'`. Con dos o más fichas más con ese nombre, no se une a ninguna. Los nombres cortos nunca pasan por U2.
- Nada más une. Lo imposible por edad no se une nunca.

**Principal de una ficha**: la identidad con identificador que más apariciones tiene (a igualdad, el `fiflp_id` menor); si ninguna lo tiene, la de la temporada más antigua (a igualdad, la de más apariciones y luego el `id` menor). `ficha_id` es `NULL` en la principal y el `id` de la principal en las demás.

**Clave pública** de una identidad: su `fiflp_id` en decimal; sin identificador, `n` + los 9 primeros caracteres en base 36 del SHA-1 de `"<nombre normalizado>|<nombre del equipo>|<año de inicio de la temporada>"` (en minúsculas, relleno con ceros). La clave de la ficha es la de su principal; las de las demás identidades son **alias** que llevan a ella. Trozo (`shard`) de una clave: numérica, `id % 16`; `n…`, `parseInt(resto, 36) % 16`. Python y JavaScript deben dar lo mismo.

## Correcciones durante la ejecución (14/11/2026)

Las reglas de unión se ampliaron en tres rondas, cada una a partir de lo visto en el ensayo sobre la base real y con su medida entre jugadores con identificador (lo vigente, con cifras y decisiones, está en `docs/identidad.md`; el resultado del ensayo, en `docs/identidad-migracion.md`):

1. **U0 de nombres cortos**: en un equipo y temporada, los identificadores de un solo uso (una aparición) de un nombre sin coma se unen a la única identidad asentada de ese nombre. Con ella, los nombres cortos uno a uno en el mismo club dan 97,8 % (después, 100 % los sin coma) y `UNIR_CORTOS_EN_CLUB = True`.
2. **U0 con un apellido**: la U0 normal vale para todo nombre con coma, no solo con dos apellidos (un niño con un apellido tenía 39 fichas de un partido). **U1 entre una ficha sin identificador y una con identificador** del mismo club en temporadas seguidas, de uno a uno (nunca dos con identificador).
3. **U0 de club**: mismo nombre con coma, mismo club y misma temporada, con como mucho una ficha con identificador → una ficha (el niño que juega en el prebenjamín del club y sube un partido al benjamín «B»). Medida: 99,4 % completos, 100 % un apellido.

Resultado del ensayo final: 14.989 fichas (17.669 antes), 0 imposibles por edad, recuentos de todas las tablas idénticos; uniones `equipo` 3.039, `club` 791, `nombre` 180. La tarea 5 se hizo en la rama `fase2c-web` (fusionada) en paralelo con la 4. Textos de la ficha: «unido por nombre», con «(mismo equipo y temporada)» o «(mismo club)».

## Review Focus

1. Un acta releída o reimportada (`_import_one` borra y reescribe): las identidades y las fichas quedan igual que antes (idempotencia de punta a punta, dos veces seguidas).
2. Un niño sin identificador que al año siguiente aparece con identificador: su ficha pasa a tener la clave numérica y la clave `n…` antigua sigue abriendo la ficha (alias); un jugador seguido con la clave antigua sigue saliendo en «seguidos».
3. Dos niños distintos con el mismo nombre completo en el mismo equipo y la misma acta (dos filas en la alineación con el mismo nombre): no se pierde ninguna aparición (hoy la clave primaria de `appearances` los fundiría).
4. Nombre corto («LUCAS») en dos clubes: dos fichas, y ninguna hereda historial de otra de otros años.
5. `prune_players` y cualquier limpieza no borran identidades secundarias de una ficha ni rompen `ficha_id` (ninguna fila apunta a una que no existe).

---

### Task 1: el bot guarda el original de cada acta y relee una vez las de 2026-27

**Files:**
- Create: `scripts/actas_bot.py` (leer y escribir los originales)
- Modify: `scripts/update_fiflp.py` (`import_actas`, y el final de `run_passes` para la relectura)
- Modify: `.github/workflows/update.yml` (el `git add` de los ficheros nuevos), `scripts/tests/test_workflows.py`
- Test: `scripts/tests/test_actas_bot.py`
- Docs: `docs/federacion.md` (apartado «Originales de las actas»)

**Interfaces (produce):**
```python
# scripts/actas_bot.py
def ruta(temporada: str, categoria: str) -> Path      # scripts/actas_bot_<2026-2027>_<prebenjamin|benjamin|alevin>.jsonl
def guardadas(temporada: str) -> set[int]             # CodActa con original guardado (las tres categorías)
def guardar(temporada: str, categoria: str, cod_acta: int, acta: dict, leida: str) -> None
```
- Formato: una línea por acta, JSON compacto con claves ordenadas, `{"cod_acta": N, "leida": "<ISO UTC>", "acta": {…el dict de parse_flat_acta tal cual…}}`, líneas ordenadas por `cod_acta`; un acta que se vuelve a leer sustituye a su línea. Escritura atómica (fichero temporal + `os.replace`). El nombre **no** casa con `actas_lotes.RAW_FILE` (trampa 14 del mapa: si casara, `import_changed_raws` lo reimportaría por nombres en cada pasada); una prueba lo fija.
- `import_actas` guarda el original de cada acta que aplica con éxito (después de `apply_acta`, antes del commit del grupo). Un fallo al guardar no pierde el acta ya aplicada: se registra y sigue.
- **Relectura**: al final de la pasada (donde hoy va `catch_up`, después de él), si la federación no está bloqueada y queda plazo y cupo de actas, se releen como mucho `RELECTURA_POR_PASADA = 20` actas de la temporada en curso que tienen `cod_acta` y no tienen original guardado, por este orden: prebenjamín, benjamín, alevín; dentro, la fecha más reciente primero. Cada una se aplica (`apply_acta`) y se guarda. No se marca `acta_recheck` (trampa 15). Lo releído cuenta en el cupo de `MAX_ACTAS_PER_RUN`. Cuando no queda ninguna, no hace nada.
- `update.yml`: `git add 'scripts/actas_bot_*.jsonl'` siempre, como `data-health.json` (una relectura no cambia nada publicado ni la base, pero su original hay que subirlo). Solo en el paso «Commit y push si hay cambios», nunca en el de diagnóstico.
- La tarea 1 va en su propia rama (`fase2c-actas`, worktree `/home/manolo/claude/futbol-base-v2-actas`) para publicarla antes que el resto y empezar a guardar originales cuanto antes.

- [ ] Pruebas de `actas_bot` (ida y vuelta, orden, sustitución, atómica: un fallo a mitad no deja el fichero roto, el nombre no casa con `RAW_FILE`).
- [ ] Pruebas del bot con federación simulada: un acta nueva queda guardada con su dict íntegro (incluido `fiflp_id` de cada jugador); la relectura respeta orden, tope de 20, cupo, plazo y bloqueo; con todo guardado no pide ninguna página.
- [ ] Implementar. Pruebas del workflow. Documento. Suites. Commit.

### Task 2: el resolvedor de fichas (puro)

**Files:**
- Create: `scripts/identidad.py`, `scripts/tests/test_identidad.py`
- Create: `docs/identidad.md` (las reglas de arriba, la medida del paso 2 y cómo deshacer una unión)

**Interfaces (produce):**
```python
# scripts/identidad.py — sin base ni red
def nombre_completo(nombre_normalizado: str) -> bool
def club(nombre_equipo: str) -> str
def intervalo(anio: int, nivel: int) -> tuple[int, int]         # nivel: 1 prebenjamín, 2 benjamín, 3 alevín
def clave_publica(fiflp_id: int | None, norm: str, equipo: str, anio: int) -> str
def trozo(clave: str, n: int = 16) -> int
@dataclass(frozen=True)
class Identidad:      # una fila de players con lo que hace falta para decidir
    id: int; norm: str; fiflp_id: int | None
    vistas: tuple     # ((anio, nivel, equipo, primera_fecha, ultima_fecha, apariciones), …)
def resolver(identidades: list[Identidad], unir_cortos_en_club: bool) -> dict[int, tuple[int, str | None]]
    """{id de identidad: (id de la principal de su ficha, union_por)}; la principal se apunta a sí misma con None."""
```
- [ ] **Step 1:** pruebas de cada regla con casos sintéticos, incluidos los cinco ejemplos del mapa (D12), los de «Review Focus» 2 y 4, U0 con 30 identificadores de un solo uso, U2 con una candidata, con dos (no une) y con una incompatible por edad (no une), solape imposible, y: el resultado no depende del orden de entrada (barajar y comparar) y aplicar `resolver` a su propio resultado no cambia nada.
- [ ] **Step 2: la medida de los nombres cortos.** Script de solo lectura (`scripts/medir_identidad.py`, se queda en el repositorio) que, con los originales de 2019-20 a 2023-24 (cuando prebenjamín venía con identificador), cuenta entre jugadores **con** identificador: de los pares (mismo nombre, mismo club, temporadas consecutivas, compatibles), cuántos son el mismo identificador (o el mismo niño tras U0) y cuántos no, separando nombres completos y cortos. Su salida va a `docs/identidad.md`. Con precisión de los cortos ≥ 95 %, `unir_cortos_en_club = True` en el resto del plan; si no, `False`.
- [ ] **Step 3:** implementar `identidad.py`. Verde. Commit.

### Task 3: la migración, ensayada sobre una copia, con informe

**Files:**
- Create: `scripts/migrate_identidad.py`, `scripts/tests/test_migrate_identidad.py`
- Create (salida del ensayo, no se versiona la copia): `docs/identidad-migracion.md` (el informe)

**Qué hace `migrate(conn, raws_dir, log=print) -> dict` (idempotente; la segunda vez no cambia nada):**
1. Esquema: `players.ficha_id INTEGER`, `players.union_por TEXT`, y lo que haga falta para la identidad sin identificador (equipo y temporada de la fila). `norm_name` sigue siendo `UNIQUE`: las filas sin identificador nuevas llevan un sufijo que las distingue (`NOMBRE@<equipo>.<año>`), igual que hoy `NOMBRE#id`.
2. **Separar** (sin borrar nada): para cada acta de los originales, cada jugador de la alineación que venía **sin** identificador y cada jugador que solo sale en los sucesos: su aparición y sus sucesos de ese partido pasan a la identidad sin identificador de (nombre, equipo, temporada), creándola si falta. Las de 2026-27, que aún no tienen original: todas las apariciones de los grupos de la liga prebenjamín de Gran Canaria se tratan como sin identificador (los `PG*`; dato 1); las demás, con el identificador de su fila. Los originales del bot (tarea 1), cuando existan, mandan sobre esta regla.
3. Una fila con identificador que se queda sin apariciones ni sucesos tras separar se conserva (no se borra ninguna fila en la migración).
4. **Resolver**: carga las identidades, llama a `identidad.resolver` y escribe `ficha_id` y `union_por`.
5. Devuelve los recuentos de antes y de después de cada tabla y las listas del informe.

**El informe (`docs/identidad-migracion.md`)**, generado por el ensayo sobre la copia: recuentos antes/después de cada tabla (idénticos salvo `players`, que solo crece); cuántas apariciones se separaron y de cuántas fichas; cuántas fichas hay ahora y cuántas publicaba v1 (`fiflp_id IS NOT NULL`); uniones por tipo (U0, U1, U2); fichas imposibles por edad que quedan (objetivo: 0; cada una que quede, con su explicación); los cinco ejemplos del mapa D12, antes y después; 20 uniones U2 y 20 separaciones al azar (semilla fija) para revisión a ojo, con nombre completo, equipos y temporadas.

- [ ] Pruebas con una base pequeña construida en la prueba (no la real): separación exacta según el original; recuentos idénticos; idempotencia; el caso de dos homónimos en la misma acta (Review Focus 3); una fila con identificador que tenía pegadas apariciones sin identificador de otro niño queda limpia; ninguna `ficha_id` apunta a una fila inexistente ni a una secundaria.
- [ ] Implementar. Ensayo sobre la copia de la base real (`cp`), informe escrito. Comprobar con `PRAGMA integrity_check` y `foreign_key_check` la copia migrada. Suites. Commit (sin la copia).

### Task 4: el importador y el bot usan las identidades de acta

**Files:**
- Modify: `scripts/import_fiflp_actas.py` (`_get_or_create_player`, `_import_one`, `prune_players`), `scripts/update_fiflp.py` (solo si `apply_acta` necesita pasar equipo y temporada), `scripts/fetch_futbolaspalmas.py` (llamar al resolvedor al final de la pasada, tras las importaciones y antes de `generate_js`)
- Modify: los demás llamadores de `_get_or_create_player` (`scripts/import_fiflp_grupos.py` y los que haya)
- Test: `scripts/tests/test_fiflp_actas_federacion.py` y las que fijan el comportamiento viejo

**Comportamiento:**
- `_get_or_create_player(conn, name, fiflp_id=None, team_id=None, season=None)`: con identificador, la fila de ese `fiflp_id` (se acabó «adoptar» una fila sin identificador); sin él, la fila sin identificador de (nombre, equipo, temporada). Nunca devuelve la fila de otro identificador por coincidir el nombre.
- El goleador que no está en la alineación (trampa 11): identidad sin identificador de su equipo y temporada; si en esa acta y ese equipo hay exactamente un jugador de la alineación con ese mismo nombre normalizado, es él.
- Dos jugadores con el mismo nombre en la misma alineación (Review Focus 3): no se pierde ninguno.
- `resolver_fichas(conn)` (en `migrate_identidad.py` o `identidad_db.py`): recalcula `ficha_id`/`union_por` de todas las filas; se llama una vez por pasada. Debe tardar menos de 20 s con la base real (medirlo en el ensayo).
- `prune_players`: no borra una fila a la que apunta otra por `ficha_id`.

- [ ] Pruebas primero (incluida la de punta a punta de Review Focus 1: importar, resolver, reimportar, resolver → mismas fichas). Implementar. Suites. Commit.

### Task 5: publicar y enseñar las fichas

**Files:**
- Modify: `scripts/generate_js.py` (`jugadores_files`, `lineups_entries`, cobertura si cuenta jugadores)
- Modify: `src/links.js`, `src/router.js`, `src/followed.js`, `src/state.js`, `src/screen-jugador.js`, `src/screen-partido.js`, `src/team-extras.js`, `src/model.js` (`teamSquad`)
- Test: `scripts/tests/test_jugador.mjs`, `scripts/tests/test_migrate_compactar.py` y las que fijan el formato; nuevas para claves y alias

**Formato publicado** (`data-jugadores-<k>.js`): `"p": {"<clave>": {"n": nombre, "c": [[temporada, grupo, equipo, partidos, titular, goles, amarillas, rojas, u], …], "u": […]}}` más `"a": {"<alias>": "<clave>"}`.
- Una entrada por ficha, en el trozo de su clave; cada alias, en el trozo **del alias** (para abrirlo sin saber la clave).
- El noveno valor de cada fila (`u`) es `0` si la fila viene de la identidad principal o de un identificador, y `1` si llegó por unión (`equipo`, `club` o `nombre`); la ficha lo dice en esa línea: «unión por nombre».
- Fichas sin ningún identificador: `"s": 1` en su entrada; la ficha dice «En las actas figura solo con este nombre.»
- `lineups_entries`: todo jugador lleva `"id"` con la clave de **su ficha** (hoy solo quien tiene `fiflp_id`), también en los sucesos (goles, cambios, tarjetas).

**La web:**
- La clave válida es `/^(?:\d+|n[0-9a-z]{9})$/` en `playerHref`, la ruta `#/jugador`, `isPlayer`/`cleanFollowed` y `jugadoresShard`.
- `screen-jugador`: si la clave pedida es un alias, enseña la ficha a la que lleva (sin cambiar la URL); los seguidos guardados con un alias siguen funcionando.
- Otras fichas con el mismo nombre: al pie de la ficha, «Otras fichas con este mismo nombre», con enlace a cada una y su último equipo y temporada. Para eso `"p"[clave]` lleva `"h": [claves]` cuando las hay (mismo nombre normalizado, otra ficha).
- `screen-partido`: el autor de cada gol enlaza a su ficha. `teamSquad` agrupa por clave de ficha, no por nombre.
- Ningún nombre se recorta ni se oculta.

- [ ] Pruebas primero (formato, alias en su trozo, `trozo` igual en Python y JS con 200 claves de ejemplo, ruta, seguidos con alias, texto de la ficha sin identificador y de la línea unida). Implementar. Suites. Commit. No se ejecuta `scripts/publicar.py`.
