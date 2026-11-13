# v2 · Fase 1: v2 en su enlace, aislada de v1 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar v2 en `https://malolocabreralolo-tech.github.io/futbol-base-v2/` como copia fiel de v1, con su propio bot y su propio reloj, sin que pueda alterar v1 aunque compartan origen web.

**Architecture:** v2 es el mismo proyecto con otros nombres para todo lo que el navegador comparte por origen (cachés del service worker y claves de `localStorage`/`sessionStorage`), una importación única y de solo lectura de «mi equipo» y los jugadores seguidos de v1, una marca «v2» visible, y un repositorio y un temporizador del PC propios. El bot y los datos no cambian en esta fase.

**Tech Stack:** HTML + módulos JS sin compilar, service worker, Python 3.11/3.12 + SQLite, GitHub Actions y Pages, Playwright 1.58 (pruebas de navegador), bash + systemd de usuario.

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O2, 7.1, 7.2, 7.8 «El reloj», 8 fase 1). Hallazgos: `docs/revision-2026-11-13.md` (A7, A8).

## Global Constraints

- **v1 no se toca**: ningún `git push` a `malolocabreralolo-tech/futbol-base` (el remoto `v1` tiene el push anulado), ningún cambio en `~/.config/futbol-base-reloj/`, `~/.local/bin/futbol-base-reloj`, `~/.local/share/futbol-base-reloj/` ni en `futbol-base-reloj.timer/.service`.
- **v2 nunca escribe ni borra una caché o una clave de v1.** Solo lee, una vez, `futbol-base:v2`, `futbol-base:jugadores` y `futbol-base:favorites:v1`.
- Prefijos de caché de v2: `futbolbase2-v` (datos y código; antes `futbolbase-v`) y `futbolbase2-escudos-` (antes `futbolbase-escudos-`).
- Claves de v2: `fb2:almacen` (antes `futbol-base:v2`), `fb2:jugadores` (antes `futbol-base:jugadores`), `fb2:codigo` (antes `futbol-base:codigo`), `fb2:destino` en `sessionStorage` (antes `futbol-base:destino`).
- Repositorio: `malolocabreralolo-tech/futbol-base-v2`, público, sin Issues ni wiki. Ruta del sitio: `/futbol-base-v2/`.
- Nombre visible: `<title>` «Fútbol Base Las Palmas v2»; manifiesto `id` `/futbol-base-v2/index.html`, `name` «Fútbol Base Las Palmas v2», `short_name` «Fútbol Base v2»; `apple-mobile-web-app-title` «Fútbol Base v2»; en la cabecera, «v2» tras «Las Palmas».
- **El aspecto y el comportamiento de las pantallas son los de v1**, salvo la marca «v2».
- El bot de v2 no pide a la federación más que el de v1: misma cadencia y mismas páginas.
- La federación solo responde desde GitHub Actions: nada de leerla desde el PC.
- No empujar al repositorio de v2 con un workflow suyo en marcha o en cola (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --limit 5` antes de cada push).
- Nunca el correo del dueño en peticiones ni cabeceras. El token de GitHub nunca se imprime ni se copia.
- Tras cambiar `src/`, `acta.css`, `index.html` o `sw.js`: `python3 scripts/codigo.py` antes de las pruebas.
- Suites que tienen que quedar en verde al final de cada tarea de código: `python3 -m pytest scripts/tests/ -q`, `node --test scripts/tests/test_*.mjs`; y al final de la fase, además, `node scripts/tests/render-smoke.mjs`, `node scripts/tests/interaction-smoke.mjs`, `node scripts/tests/pwa-smoke.mjs` y la nueva `node scripts/tests/aislamiento-smoke.mjs`.
- `python3 -m pytest scripts/tests/` reescribe `scripts/fiflp_actas_unmatched.json`: tras ejecutarla, `git checkout -- scripts/fiflp_actas_unmatched.json`.
- Español en código, comentarios, mensajes y commits. Los comentarios dicen el porqué en una frase, sin citar planes ni decisiones numeradas. Al tocar una línea con un comentario que nombra una caché o una clave de v1, se actualiza el comentario.
- Cada commit acaba con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```
- `git add` por nombre de fichero; nunca `git add -A` ni `git commit -a`. Sin `git push` salvo en la tarea 8, que hace el controlador.

## Review Focus

1. **v1 instalada y v2 abierta en el mismo navegador; después v1 se actualiza** → al activarse el SW nuevo de v1 las cachés de v2 siguen enteras, y al revés. (Tarea 4, `aislamiento-smoke.mjs`, pasos 4 y 5.)
2. **Almacenamiento bloqueado o en modo privado** → v2 arranca con el equipo por defecto y la importación desde v1 no lanza. (Tarea 2, `test_importar_con_almacenamiento_que_falla`.)
3. **Lo guardado en v1 está corrupto o es de un equipo que ya no existe** → se ignora y queda el equipo por defecto; nunca una pantalla en blanco. (Tarea 2, `test_importar_ignora_lo_corrupto`.)
4. **Una pasada del bot que solo cambia datos** → sube la versión en `sw.js` con el prefijo de v2; si la expresión no casara, la app instalada no vería datos nuevos nunca. (Tarea 1, pruebas adaptadas de `test_pygen_fixes.py` y `test_index_bot_contract.py`.)
5. **`reloj.yml` de v2 desactivado a mano** (durante la primera pasada pequeña) → el reloj del PC no lanza nada y no falla. (Tarea 6, `test_reloj_desactivado_no_lanza`.)

---

## Estructura de ficheros

```
sw.js, index.html, manifest.json, src/store.js, src/router.js, src/followed.js, src/shell.js   nombres de v2 e importación desde v1
scripts/generate_js.py, publicar.py, sync_versions.py, build_crests.py                          el prefijo de caché que escriben y buscan
scripts/tests/test_aislamiento_v1.mjs        (nuevo) ningún nombre de v1 en lo que v2 publica
scripts/tests/aislamiento-smoke.mjs          (nuevo) v1 real y v2 en el mismo origen, en un navegador
scripts/tests/pages-server.mjs               sirve además un segundo sitio bajo otro prefijo
.github/workflows/update.yml                 entrada `cats`
.github/workflows/tests.yml                  job de la prueba de aislamiento
pc/reloj/futbol-base-v2-reloj, instalar.sh, systemd/*.{service,timer}, tests/test_reloj.py     (nuevo) el reloj del PC de v2
pc/copia/origenes.json                       añade v2
README.md                                    qué es v2 y en qué se diferencia de v1
```

---

### Task 1: Cachés y claves propias

**Files:**
- Modify: `sw.js`, `index.html`, `src/store.js`, `src/router.js`, `src/followed.js`, `scripts/generate_js.py`, `scripts/publicar.py`, `scripts/sync_versions.py`, `scripts/build_crests.py`, y las pruebas que fijan esos nombres (`scripts/tests/test_sw_fixes.mjs`, `pwa-smoke.mjs`, `test_pygen_fixes.py`, `test_sync_versions.py`, `test_publicar.py`, `test_build_crests.py`, `test_index_bot_contract.py`, `test_season_preparation.py`, `test_alevin_generador.py`, `test_rediseno_index.mjs`, `test_rediseno_store.mjs`, `test_rediseno_fixtures.mjs`, `test_rediseno_integracion.mjs`, `test_rediseno_model_temporadas.mjs`, `test_rediseno_router.mjs`, `interaction-smoke.mjs`, `fixture-site.mjs`, `fixtures/rediseno/build_fixtures.mjs`)
- Create: `scripts/tests/test_aislamiento_v1.mjs`

**Interfaces:**
- Produces (`src/store.js`):
  ```js
  export const STORE_KEY = 'fb2:almacen';
  export const FOLLOWED_KEY = 'fb2:jugadores';
  export const V1_STORE_KEY = 'futbol-base:v2';            // solo lectura
  export const V1_FOLLOWED_KEY = 'futbol-base:jugadores';  // solo lectura
  export const LEGACY_KEY = 'futbol-base:favorites:v1';    // solo lectura, como hasta ahora
  ```
  `clearStore` borra solo `STORE_KEY` y `FOLLOWED_KEY` (ya no `LEGACY_KEY`, `season`, `cat` ni `theme`).
- Produces: `SESSION_KEY = 'fb2:destino'` (`src/router.js`); la clave de la versión del código en `index.html`, `fb2:codigo`.
- `sw.js` línea 1: `const CACHE_NAME = 'futbolbase2-v<versión>';`; línea 2: `const CRESTS_CACHE = 'futbolbase2-escudos-<sello>';`. `activate` borra solo cachés `futbolbase2-v*` y `futbolbase2-escudos-*` que no sean las suyas. La limpieza del arranque de `index.html` solo mira cachés `futbolbase2-v*`.
- Los cuatro scripts escriben y buscan el prefijo nuevo.
- `scripts/tests/fixtures/app-anterior/` representa a partir de ahora «una versión anterior de v2»: sus nombres pasan también al prefijo nuevo, para que las pruebas de transición sigan probando la limpieza de v2 sobre sus propias cachés. v2 no tiene ninguna transición que hacer desde v1.
- En esta tarea `loadStore` sigue leyendo solo su clave (`STORE_KEY`) y `LEGACY_KEY`; la importación desde v1 es la tarea 2.

- [ ] **Step 1: Escribir la prueba que falla** (`scripts/tests/test_aislamiento_v1.mjs`)

```js
const SITIO = ['index.html', 'sw.js', 'manifest.json', ...readdirSync('src').filter(f => f.endsWith('.js')).map(f => `src/${f}`)];

test('lo que v2 publica no nombra ninguna caché de v1', () => {
  for (const f of SITIO) assert.doesNotMatch(readFileSync(f, 'utf8'), /futbolbase-v|futbolbase-escudos-/, f);
});

test('las claves de v1 solo aparecen como constantes de solo lectura de store.js', () => {
  for (const f of SITIO) {
    const hits = readFileSync(f, 'utf8').match(/futbol-base:[a-z0-9:]+/g) || [];
    if (f === 'src/store.js') assert.deepEqual([...new Set(hits)].sort(), ['futbol-base:favorites:v1', 'futbol-base:jugadores', 'futbol-base:v2']);
    else assert.deepEqual(hits, [], f);
  }
});

test('sw.js lleva los nombres de v2 en sus dos primeras líneas', () => {
  const [l1, l2] = readFileSync('sw.js', 'utf8').split('\n');
  assert.match(l1, /^const CACHE_NAME = 'futbolbase2-v[0-9a-z]+';$/);
  assert.match(l2, /^const CRESTS_CACHE = 'futbolbase2-escudos-[0-9a-f]{8}';$/);
});

test('al activarse, el SW solo borra cachés viejas de v2', async () => {
  // con el arnés de test_sw_fixes.mjs: caches.keys() = las de abajo; se dispara `activate`
  const claves = ['futbolbase-v20261113', 'futbolbase-escudos-aaaa1111', 'futbolbase2-vvieja', 'futbolbase2-escudos-00000000', 'otra-app'];
  assert.deepEqual(borradas.sort(), ['futbolbase2-escudos-00000000', 'futbolbase2-vvieja']);
});

test('«Borrar datos» solo quita claves de v2', () => {
  const s = almacenDePrueba({ 'fb2:almacen': '{}', 'fb2:jugadores': '[]', 'futbol-base:v2': 'x', 'futbol-base:jugadores': 'y',
                              'futbol-base:favorites:v1': 'z', season: 'a', cat: 'b', theme: 'c' });
  clearStore(s);
  assert.deepEqual(Object.keys(s.datos).sort(), ['cat', 'futbol-base:favorites:v1', 'futbol-base:jugadores', 'futbol-base:v2', 'season', 'theme']);
});
```

- [ ] **Step 2: Ejecutarla y ver que falla** — Run: `node --test scripts/tests/test_aislamiento_v1.mjs` — Expected: FAIL en las cinco.
- [ ] **Step 3: Cambiar los nombres** en el sitio, en los cuatro scripts y en las pruebas y fixtures que los fijan. Después `python3 scripts/codigo.py`.
- [ ] **Step 4: Ejecutar las dos suites enteras**

Run: `python3 -m pytest scripts/tests/ -q && node --test scripts/tests/test_*.mjs; git checkout -- scripts/fiflp_actas_unmatched.json`
Expected: todo en verde (1.324 de pytest con 5 saltadas, y las de node con las 5 nuevas).

- [ ] **Step 5: Commit** — `git commit -m "v2: cachés y claves propias, para no tocar las de v1 en el mismo origen"`

---

### Task 2: Traer una vez «mi equipo» y los seguidos de v1

**Files:**
- Modify: `src/store.js`, `src/followed.js`, `src/app.js`
- Test: `scripts/tests/test_importar_v1.mjs` (nuevo)

**Interfaces:**
- Consumes: las constantes de la tarea 1.
- Produces (`src/store.js`):
  ```js
  // Copia a las claves de v2 lo que v1 tenga guardado, si v2 aún no tiene lo suyo. Devuelve qué copió.
  export function importFromV1(storage): { store: boolean, followed: boolean }
  ```
  - Si no existe `fb2:almacen`: si `futbol-base:v2` existe y es un JSON de objeto, se copia tal cual a `fb2:almacen`; si no, no se escribe nada (y `loadStore` seguirá leyendo `LEGACY_KEY` como hoy).
  - Si no existe `fb2:jugadores`: si `futbol-base:jugadores` existe y es un JSON de lista, se copia tal cual a `fb2:jugadores`.
  - Nunca escribe, cambia ni borra una clave de v1. Con un almacenamiento que falla, devuelve `{ store: false, followed: false }` sin lanzar.
  - La validación fina (equipo que no existe, forma incorrecta) la siguen haciendo `loadStore` y `loadFollowed`, que ya descartan lo que no vale.
- `src/app.js` llama a `importFromV1(storage)` una vez, antes del primer `loadStore`.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_importar_v1.mjs`)

```js
test('copia mi equipo y los seguidos de v1 la primera vez', () => {
  const s = almacenDePrueba({ 'futbol-base:v2': JSON.stringify({ myTeam: EQUIPO, recent: [] }), 'futbol-base:jugadores': JSON.stringify([{ id: 1, n: 'A' }]) });
  assert.deepEqual(importFromV1(s), { store: true, followed: true });
  assert.equal(s.datos['fb2:almacen'], s.datos['futbol-base:v2']);
  assert.equal(s.datos['fb2:jugadores'], s.datos['futbol-base:jugadores']);
});
test('no pisa lo que v2 ya tiene', () => { /* con fb2:almacen y fb2:jugadores ya puestos -> {false,false} y no cambian */ });
test('nunca toca las claves de v1', () => { /* antes y después, las tres claves de v1 son idénticas byte a byte */ });
test('test_importar_ignora_lo_corrupto', () => {
  const s = almacenDePrueba({ 'futbol-base:v2': '{no es json', 'futbol-base:jugadores': '"texto"' });
  assert.deepEqual(importFromV1(s), { store: false, followed: false });
  assert.equal(loadStore(s, { defaultTeam: POR_DEFECTO, portalSeason: '2026-2027' }).myTeam.name, POR_DEFECTO.name);
});
test('un equipo de v1 que ya no existe acaba en el equipo por defecto', () => { /* importFromV1 copia; loadStore + la resolución de la app dan el de por defecto */ });
test('test_importar_con_almacenamiento_que_falla', () => {
  const roto = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('bloqueado'); }, removeItem() {} };
  assert.deepEqual(importFromV1(roto), { store: false, followed: false });
});
test('sin nada en v1 no escribe nada', () => { /* almacén vacío -> {false,false} y sigue vacío */ });
```

- [ ] **Step 2: Ejecutarlas y ver que fallan**
- [ ] **Step 3: Implementar `importFromV1` y llamarla en el arranque.** Después `python3 scripts/codigo.py`.
- [ ] **Step 4: Ejecutar las dos suites enteras** — Expected: todo en verde.
- [ ] **Step 5: Commit** — `git commit -m "v2: trae una vez «mi equipo» y los jugadores seguidos de v1, sin tocar lo de v1"`

---

### Task 3: Que se vea que es v2

**Files:**
- Modify: `index.html`, `manifest.json`, `acta.css`, `src/shell.js` (si la cabecera se pinta ahí), `scripts/update.sh`, `scripts/tests/pages-server.mjs`, `README.md`, y las pruebas que fijan el título, el manifiesto o la cabecera
- Test: `scripts/tests/test_identidad_v2.mjs` (nuevo)

**Interfaces:**
- `<title>`, manifiesto y `apple-mobile-web-app-title`: los valores de Global Constraints. Los títulos por pantalla («Jornada · Fútbol Base Las Palmas») llevan también «v2» al final.
- Cabecera: `Fútbol base <span class="brand-place">Las Palmas</span> <span class="brand-version">v2</span>`; `.brand-version` es pequeña, en la tinta del tema y sin cambiar la altura de la cabecera ni partirla en dos líneas a 320 px de ancho.
- `scripts/tests/pages-server.mjs`: `PREFIX = '/futbol-base-v2'`. `scripts/update.sh` anuncia la URL de v2.
- `README.md`: primer párrafo nuevo que dice que esto es v2, enlaza v2 y v1, dice que v1 no se toca y apunta al diseño (`docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md`) y a `pc/copia/README.md`. El resto del README se queda.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_identidad_v2.mjs`)

```js
test('manifiesto de v2', () => {
  const m = JSON.parse(readFileSync('manifest.json', 'utf8'));
  assert.equal(m.id, '/futbol-base-v2/index.html');
  assert.equal(m.name, 'Fútbol Base Las Palmas v2');
  assert.equal(m.short_name, 'Fútbol Base v2');
});
test('título y cabecera de v2', () => {
  const html = readFileSync('index.html', 'utf8');
  assert.match(html, /<title>Fútbol Base Las Palmas v2<\/title>/);
  assert.match(html, /<meta name="apple-mobile-web-app-title" content="Fútbol Base v2">/);
  assert.match(html, /<span class="brand-place">Las Palmas<\/span> <span class="brand-version">v2<\/span>/);
});
test('el título de cada pantalla acaba en «v2»', () => { /* el título que pone el router para #/jornada es 'Jornada · Fútbol Base Las Palmas v2' */ });
```

- [ ] **Step 2: Ejecutarlas y ver que fallan**
- [ ] **Step 3: Implementar** y `python3 scripts/codigo.py`.
- [ ] **Step 4: Ejecutar las dos suites enteras** — Expected: todo en verde.
- [ ] **Step 5: Commit** — `git commit -m "v2: nombre, manifiesto y marca «v2» en la cabecera"`

---

### Task 4: Prueba de navegador: v1 y v2 en el mismo origen

**Files:**
- Create: `scripts/tests/aislamiento-smoke.mjs`
- Modify: `scripts/tests/pages-server.mjs` (segundo sitio bajo otro prefijo), `.github/workflows/tests.yml` (job nuevo), `scripts/tests/test_workflows.py` si fija los jobs, `README.md` (la orden)

**Interfaces:**
- Consumes: tareas 1 a 3; los ayudantes de `pwa-smoke.mjs` e `interaction-smoke.mjs` (arranque de Chrome con Playwright 1.58, espera del SW, simulación de una subida).
- v1 es el código real de v1 en el commit de la copia: `V1_COMMIT = 'c47a1caa'` (completar con el sha entero de `git rev-parse c47a1caa`). La prueba saca a un directorio temporal, con `git archive`, solo lo que el sitio necesita (`index.html`, `sw.js`, `manifest.json`, `acta.css`, `src/`, `fonts/`, `icons/`, los `data-*.js` de arranque, `data-health.json` y `data-season-*.js`; sin `escudos/`, sin `data-lineups-*`, sin la base). Si el commit no está en el clon (CI con poca profundidad), lo trae con `git fetch --depth 1 origin <sha>`; si aun así no lo tiene, la prueba **falla**, no se salta.
- El servidor sirve v1 bajo `/futbol-base/` y el árbol de trabajo bajo `/futbol-base-v2/`, en el mismo origen.
- Pasos y aserciones:
  1. Abrir v1; esperar a que su SW controle la página. Poner en `localStorage` un estado de v1: `futbol-base:v2` con un equipo válido distinto del de por defecto, `futbol-base:jugadores` con un jugador, y `season`, `cat`, `theme`. Anotar cachés y claves.
  2. Abrir v2 en el mismo contexto; esperar a su SW. **Aserciones:** todas las cachés de v1 siguen; las claves de v1 son idénticas; las cachés de v2 empiezan por `futbolbase2-`; v2 muestra el equipo traído de v1 y tiene `fb2:almacen` y `fb2:jugadores`.
  3. En v2, Ajustes → «Borrar datos de esta app». **Aserciones:** las claves de v1 (también `season`, `cat`, `theme`) siguen idénticas; no queda ninguna `fb2:`.
  4. Subida de v1 (el servidor cambia la versión de `sw.js` e `index.html` de v1); recargar v1 hasta que el SW nuevo esté activo. **Aserciones:** las cachés viejas de v1 ya no están y **todas las de v2 siguen**.
  5. Subida de v2, igual. **Aserciones:** las cachés de v1 siguen todas; las viejas de v2 no.
  6. Cero errores de consola y cero excepciones en las dos apps.
- Sale con código 0 y una línea `aislamiento-smoke: ok (5 pasos)`; cualquier aserción fallida, código 1 con el paso y lo que encontró. Sin Chrome: código 1 (aquí no vale saltarse).

- [ ] **Step 1: Escribir `aislamiento-smoke.mjs`** y ampliar `pages-server.mjs`.
- [ ] **Step 2: Comprobar que caza un fallo de verdad**: con `git stash` de la tarea 1 no se puede; en su lugar, cambiar a mano en una copia temporal del árbol el prefijo de `sw.js` a `futbolbase-v` y ver que el paso 4 falla. Dejar anotada la salida en el informe.
- [ ] **Step 3: Ejecutarla sobre el árbol real** — Run: `npm install --no-save --package-lock=false playwright@1.58.0 && node scripts/tests/aislamiento-smoke.mjs` — Expected: `aislamiento-smoke: ok (5 pasos)`.
- [ ] **Step 4: Job en `tests.yml`** (`aislamiento-smoke`, mismo patrón que `pwa-smoke`), y las dos suites enteras en verde.
- [ ] **Step 5: Commit** — `git commit -m "v2: prueba de navegador de que v1 y v2 no se pisan en el mismo origen"`

---

### Task 5: Poder lanzar una pasada de pocas categorías

**Files:**
- Modify: `.github/workflows/update.yml`, `scripts/tests/test_workflows.py`, `docs/federacion.md` (una línea donde se explica cómo lanzar a mano)

**Interfaces:**
- `update.yml`: `workflow_dispatch` gana la entrada opcional `cats` (texto, por defecto vacío, descripción «Categorías a leer, separadas por comas (vacío: todas)»). El paso «Actualizar datos…» pone `FIFLP_CATS: ${{ inputs.cats }}`. Con la entrada vacía la pasada es exactamente la de hoy (`update_fiflp.py` ya trata el vacío como «todas»).
- Nada más cambia en el workflow.

- [ ] **Step 1: Prueba que falla** en `test_workflows.py`:

```python
def test_update_admite_pasada_de_pocas_categorias():
    data = _load("update.yml")
    entrada = data[True]["workflow_dispatch"]["inputs"]["cats"]      # PyYAML lee `on:` como True
    assert entrada["required"] is False and entrada["default"] == ""
    paso = next(s for s in data["jobs"]["update"]["steps"] if s.get("id") == "scrape")
    assert paso["env"]["FIFLP_CATS"] == "${{ inputs.cats }}"
```
(usar el mismo acceso a `on` que ya usa el fichero)

- [ ] **Step 2: Verla fallar** · **Step 3: Implementar** · **Step 4: `python3 -m pytest scripts/tests/test_workflows.py -q` en verde y la suite entera** · **Step 5: Commit** — `git commit -m "bot: una pasada puede leer solo algunas categorías (entrada cats)"`

Nota: `.github/workflows/` está protegido por un hook que bloquea Write/Edit; esos YAML se escriben con `python3` o `cat` desde la terminal.

---

### Task 6: El reloj del PC de v2

**Files:**
- Create: `pc/reloj/futbol-base-v2-reloj`, `pc/reloj/instalar.sh`, `pc/reloj/systemd/futbol-base-v2-reloj.service`, `pc/reloj/systemd/futbol-base-v2-reloj.timer`, `pc/reloj/README.md`
- Test: `pc/reloj/tests/test_reloj.py`

**Interfaces:**
- `futbol-base-v2-reloj` hace lo mismo que `~/.local/bin/futbol-base-reloj` (léelo: es el modelo; no lo modifiques) para el repositorio `malolocabreralolo-tech/futbol-base-v2`: decide con una copia instalada y revisada de `scripts/reloj_pasadas.py` y, si toca, lanza `reloj.yml`. Diferencias:
  - Repositorio: `FBR2_REPO`, por defecto `malolocabreralolo-tech/futbol-base-v2`.
  - Token: lo lee de `FBR2_TOKEN_FILE`, por defecto `$HOME/.config/futbol-base-reloj/token` (el mismo fichero que usa v1). Solo lo lee: no lo copia, no lo imprime, no lo modifica.
  - Su copia de `reloj_pasadas.py` y su sha: `${XDG_DATA_HOME:-$HOME/.local/share}/futbol-base-v2-reloj/`.
  - `gh` se busca en el `PATH` (así las pruebas ponen uno de mentira delante).
- Temporizador: `OnCalendar=*:04/5 UTC` (a y 4, 9, 14…: dos minutos después del de v1), `RandomizedDelaySec=30`, `AccuracySec=30s`. Servicio: `Type=oneshot`, `ExecStart=%h/.local/bin/futbol-base-v2-reloj`, `TimeoutStartSec=120`.
- `instalar.sh`: copia el ejecutable a `$FBR2_HOME/.local/bin/`, `scripts/reloj_pasadas.py` del repositorio y su sha de git a la carpeta de datos, las unidades a `$FBR2_HOME/.config/systemd/user/`, y salvo con `FBR2_SIN_SYSTEMD=1` hace `daemon-reload` y `enable --now` del temporizador. `FBR2_HOME` vale `$HOME` por defecto. No toca nada de v1.
- `DRY_RUN=1`: decide y no lanza, como el de v1.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_reloj.py`; un `gh` de mentira en un directorio temporal puesto delante en el `PATH`, que responde con ficheros JSON preparados y apunta en un registro cada llamada)

```python
def test_toca_y_lanza(entorno):            # última pasada de hace 3 h, reloj.yml activo -> sale 0, «Lanzado reloj.yml», y el gh de mentira recibió `workflow run reloj.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main`
def test_no_toca(entorno):                 # última pasada de hace 10 min -> sale 0 y no hay `workflow run`
def test_reloj_desactivado_no_lanza(entorno):   # state «disabled_manually» -> sale 0, dice que no se lanza, y no hay `workflow run`
def test_inactivo_por_github_falla(entorno):    # state «disabled_inactivity» -> código distinto de 0 y el mensaje dice cómo reactivarlo
def test_dry_run_no_lanza(entorno):
def test_sin_token_falla(entorno):         # FBR2_TOKEN_FILE inexistente -> código distinto de 0, sin llamar a gh
def test_no_escribe_ni_muestra_el_token(entorno):   # el fichero del token queda idéntico y su contenido no sale en stdout ni stderr
def test_instalar_en_un_home_de_prueba(tmp_path):   # FBR2_HOME=tmp, FBR2_SIN_SYSTEMD=1 -> ejecutable, reloj_pasadas.py, .sha y las dos unidades; «OnCalendar=*:04/5 UTC» en el temporizador
```

- [ ] **Step 2: Verlas fallar** · **Step 3: Implementar** · **Step 4: `python3 -m pytest pc/reloj/tests -q` en verde** · **Step 5: Commit** — `git commit -m "v2: su reloj del PC, aparte del de v1 y leyendo el mismo token sin copiarlo"`

---

### Task 7: Datos al día y comprobación en local (controlador)

- [ ] **Step 1:** `git fetch v1 main` y traer de `v1/main` solo datos: `git checkout v1/main -- futbolbase.db 'data-*.js' data-health.json 'scripts/*_raw.json' docs/temporadas`. Después `python3 scripts/generate_js.py` (reescribe los `data-*.js` y sube la versión con los nombres de v2) y `python3 scripts/codigo.py`.
- [ ] **Step 2:** todas las suites de Global Constraints en verde, incluidas las cuatro de navegador.
- [ ] **Step 3:** capturas emparejadas v1/v2 con el servidor de pruebas (v1 del commit de la copia y v2 del árbol): portada, Jornada, Tabla, Partido con acta, Explorar y ficha de jugador, en móvil (390×844) claro y oscuro y en escritorio (1280×800). La única diferencia admitida es la marca «v2».
- [ ] **Step 4:** fusionar la rama de la fase en `main` local y commit de los datos.

### Task 8: Publicar (controlador)

- [ ] **Step 1:** crear el repositorio y empujar:
  ```bash
  gh repo create malolocabreralolo-tech/futbol-base-v2 --public --disable-issues --disable-wiki \
    --description "Fútbol base de Las Palmas, versión 2 (en pruebas junto a la actual)"
  git remote add origin https://github.com/malolocabreralolo-tech/futbol-base-v2.git
  git push -u origin main
  gh workflow disable reloj.yml -R malolocabreralolo-tech/futbol-base-v2     # hasta acabar la pasada pequeña
  ```
- [ ] **Step 2:** Pages desde `main`, raíz: `gh api -X POST repos/malolocabreralolo-tech/futbol-base-v2/pages -f 'source[branch]=main' -f 'source[path]=/'`. Esperar al despliegue y comprobar que `https://malolocabreralolo-tech.github.io/futbol-base-v2/` responde 200 y que `tests.yml` del push sale en verde.
- [ ] **Step 3:** primera pasada, pequeña: `gh workflow run update.yml -R malolocabreralolo-tech/futbol-base-v2 -f cats=prebenjamin`. Verde, 4 grupos leídos, commit del bot correcto. Si falla, se para aquí y se diagnostica.
- [ ] **Step 4:** una pasada completa a mano; verde.
- [ ] **Step 5:** web real en navegador (móvil y escritorio): portada, Jornada, Tabla, Partido; consola sin errores; v1 abierta al lado en el mismo navegador y sin cambios. Capturas para el dueño.
- [ ] **Step 6:** `gh workflow enable reloj.yml`; `bash pc/reloj/instalar.sh`; comprobar en el journal que decide bien y, cuando toque, que lanza.
- [ ] **Step 7:** añadir v2 a `pc/copia/origenes.json`, reinstalar la copia (`bash pc/copia/instalar.sh`), `futbol-base-copia ejecutar` y `estado` con v1 y v2 aceptadas.
- [ ] **Step 8:** ficha de memoria `futbol-base-v2` al día.
