# Ampliación, parte E2: infantil, cadete y juvenil en la web — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la web enseñe infantil, cadete y juvenil de 2026-27 (y las temporadas pasadas que traiga la parte F) con el mismo detalle que benjamín —Explorar, Ligas, Tabla, Jornada, Equipo, Partido, Goleadores, Récords, Temporadas anteriores, Mi equipo, fichas, buscador y ranking—, sin que la portada cargue nada nuevo.

**Depende de:** la parte E1 entera en `main` (`docs/superpowers/plans/2026-11-25-ampliacion-e1-categorias-datos.md`): `categorias.EN_WEB`, `vista_web.copia_web`, `convenio.py` y su fixture `scripts/tests/fixtures/convenio_mayores.json`, `scripts/tests/base_mayores.py` y `scripts/prueba_mayores.py`, `ranking.fase_que_cuenta` con fase entera. Para el último paso (tarea 8), además, al menos infantil activado y leído en la base (paso D3 de E1). Si al empezar E1 no está en `main`, se para y se avisa.

**Architecture:** Lo que hoy es «alevín perezoso» pasa a ser «categorías perezosas» (alevín, infantil, cadete y juvenil) con un registro por categoría en Python (`generate_js.LAZY`) y en la web (`state.js`, `LAZY`): un fichero por categoría para la temporada en curso (`data-alevin.js`, `data-infantil.js`, `data-cadete.js`, `data-juvenil.js`) y uno por categoría y temporada pasada (`data-season-<S>-<cat>.js`), con las mismas constantes y nombres de fichero que alevín ya publica. El modelo aprende las seis categorías, la isla `interinsular` y las fases del convenio. Todo el código llega con `EN_WEB` de E1 (la web sigue igual: los ficheros nuevos salen vacíos); el último paso amplía `EN_WEB` y entonces el generador publica lo nuevo y el resolvedor une las fichas de una categoría a otra.

**Tech Stack:** Python 3.11 (sqlite3, pytest 9.2.0); módulos ES sin dependencias en `src/`, pruebas de Node 22 (`node --test`), Playwright para los smoke y las capturas (`scripts/tests/render-smoke.mjs`, `interaction-smoke.mjs`, `capturas.mjs`, con el servidor local y los mundos de `fixture-site.mjs`); esbuild al publicar (`scripts/publicar.py`, solo el director).

**Spec:** `docs/superpowers/specs/2026-11-25-ampliacion-trayectorias-design.md` (parte E; decisión 4, «En la web, las categorías nuevas se cargan de forma perezosa»). Mapa: `docs/ampliacion-mapa.md`, sección 1, «Generador» y «Web». El contrato que se generaliza: `docs/alevin.md` §4 y §5. El de E1: `docs/categorias-mayores.md`.

## Global Constraints

- Árbol de trabajo: `/home/manolo/claude/futbol-base-v2-categorias`, rama `categorias` (la de E1, ya en `main`, rebasada). No se toca la versión 1 (`/home/manolo/claude/futbol-base`) ni ningún otro árbol.
- Nunca una petición a fiflp.com ni a ninguna otra web (los smoke y las capturas sirven el árbol en `localhost` con los mundos de fixtures).
- No se lanzan workflows, no se hace `git push` ni `git stash`, no se cambian variables del repositorio.
- No se ejecutan `scripts/publicar.py`, `scripts/generate_js.py` ni `scripts/fetch_futbolaspalmas.py` sobre el árbol; no se modifica `futbolbase.db` ni `base/`. Las pruebas usan copias en directorios temporales y `scripts/prueba_mayores.py` (árbol temporal).
- La base solo la escribe el bot. Ningún nombre real de niño en código, pruebas, documentos ni commits (nombres inventados o claves).
- **El bot no puede dejar de publicar**: la puerta de pruebas del bot corre después de sus importaciones, así que toda prueba que mire la base real o los `data-*.js` vale con la base de antes y con la de después de activar y leer las categorías nuevas, con `EN_WEB` de E1 y con el ampliado. Cada tarea acaba con `python3 scripts/prueba_mayores.py` en verde (y la tarea 8, además, con `EN_WEB` ampliado en la copia).
- **La portada no carga nada nuevo**: `index.html` pide los mismos `data-*.js` que hoy; `data-history.js`, `data-benjamin.js`, `data-prebenjamin.js`, `data-goleadores.js` y `data-seasons.js` no llevan nada de infantil, cadete ni juvenil; el precache del SW (`scripts/precache.py`) no gana ningún fichero de las categorías nuevas (ni obligatorio ni opcional).
- Los nombres de fichero y las constantes que alevín ya publica no cambian (`data-alevin.js` con `ALEVIN`, `ALEV_STATS`, `HISTORY_ALEV`, `GOL_ALEV`, `ESTADOS_ALEV`, `EQUIPOS_ALEV`; `data-season-<S>-alevin.js` con `SEASON_<S>_ALEVIN`): con la base de hoy, `data-alevin.js` y los demás salen iguales byte a byte.
- Cada tarea, publicada sola, deja `main` funcionando y la web igual hasta la tarea 8 (con `EN_WEB` de E1 las categorías nuevas no tienen datos que enseñar).
- Ancho mínimo 320 px sin desplazamiento horizontal de la página, en claro y en oscuro, con las variables de `acta.css` que ya existen. Lo visual se comprueba con capturas antes de darlo por bueno.
- Estilo: el del fichero que se toca (comentarios en español que explican el porqué; `html\`\`` para todo HTML; sin dependencias nuevas). Las pantallas son `render(ctx)` pura y `mount(root, ctx, nav)`.
- Las tareas que tocan `src/` dejan en rojo `test_rediseno_index.mjs` («dist/ es el de las fuentes…») y la que depende de ella hasta que el director empaquete `dist/` (`scripts/publicar.py`); todo lo demás, en verde.
- Cada commit acaba con las dos líneas `Co-Authored-By: Claude <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv`.
- Lo marcado **PASO DEL DIRECTOR** no lo hace el implementador: lo deja escrito y se para.

## Review Focus

- **Una fase del convenio que la web pone en «otra-…», o dos competiciones con la misma clave en Ligas** (dos copas de Lanzarote del mismo año, «Copa Insular» y «Copa Preferente»; o dos eliminatorias): saldrían juntas o sin nombre, y la sonda de `activar_auto` daría la activación por fallida. Prueba: tarea 2 `test_todas_las_fases_del_convenio`.
- **Una categoría perezosa que no llega** (404, sin conexión, un fichero a medias) en Explorar, Ligas sin categoría o la trayectoria de un equipo: la pantalla se pinta con las demás y lo dice, con «Reintentar»; nunca una pantalla en blanco ni un aviso que nombre solo alevín. Pruebas: tarea 3 `test_lazy_needs_y_fallos` y tarea 4 `test_explorar_con_una_perezosa_caida`.
- **Seis categorías en Goleadores y Récords a 320 px**: el selector no empuja la página ni se corta; en una temporada pasada solo salen las categorías que la tienen. Pruebas: tarea 5 `test_selector_de_categorias` y el escenario de 320 px de `interaction-smoke.mjs`.
- **Un club que juega en benjamín y en juvenil con el mismo nombre** (la misma fila de `teams`): Equipo, la trayectoria, el buscador de equipos y Mi equipo enseñan cada grupo en su categoría, y la carga inicial no gana sus equipos de juvenil. Pruebas: tarea 1 `test_la_carga_inicial_no_gana_nada` y tarea 4 `test_un_club_en_dos_categorias`.
- **Un niño con temporadas de benjamín y de cadete en dos fichas que el resolvedor une al ampliar `EN_WEB`**: la clave publicada no se pierde (los enlaces y los seguidos de hoy siguen valiendo, por los alias) y dos niños de edades incompatibles no se unen. Prueba: tarea 8 `test_las_claves_de_hoy_siguen_valiendo` sobre la base de después.

## Lo que añade a lo publicado (temporada en curso, al acabarla; a 25/11, ~un tercio)

| Fichero | Tamaño |
|---|---|
| `data-infantil.js`, `data-cadete.js`, `data-juvenil.js` | ~0,4-0,6 MB cada uno (alevín: 0,37 MB para 51 grupos de fútbol 7); ~60-80 KB comprimidos |
| `data-matchdetail-<cat>.js` (uno por categoría nueva) | ~0,1-0,2 MB cada uno |
| `data-lineups-2026-2027-<código>.js` de los grupos nuevos | ~6 KB por acta × ~7.000: ~41 MB (hoy 4,7 MB para 1.234 actas de fútbol 7) |
| `data-jugadores-<k>.js` (64) | +~3 MB en total (~15.000 fichas nuevas o ampliadas) |
| `data-buscar-<xy>.js` | +~1,5 MB en total |
| `data-ranking-<año>.js` | los años de 2008 a 2014 ganan listas (~15 KB cada uno) |
| Carga inicial (`index.html` y lo que pide) | **nada** |

---

### Task 1: El generador, por categorías perezosas

**Files:**
- Modify: `scripts/generate_js.py` (`EAGER_CATEGORIES` sin cambio; `ALEVIN` → registro `LAZY`; `_alevin_only`/`_in_alevin` → `_lazy_only`/`_in_category`; `generate_alevin_js` → `generate_lazy_js`; `generate_history_js`; `_match_details`/`generate_matchdetail_js`; `archive_alevin` → `archive_lazy`; la escritura de `data-season-<S>-<cat>.js`; `_is_league_group`; `main`)
- Modify: `scripts/precache.py` (los opcionales: `data-alevin.js` sí, como hoy; los de las categorías nuevas, nunca)
- Test: `scripts/tests/test_alevin_generador.py` (sin tocar: tiene que seguir en verde), `scripts/tests/test_categorias_generador.py` (nuevo), `scripts/tests/test_precache.py`, `scripts/tests/test_data_integrity.py` (los ficheros de temporada de las seis)

**Interfaces:**
- Consumes: `categorias.EN_WEB` (leída al llamar), `vista_web.copia_web`.
- Produces:
  - `generate_js.LAZY = {"ALEVIN": ("alevin", "ALEVIN", "ALEV"), "INFANTIL": ("infantil", "INFANTIL", "INF"), "CADETE": ("cadete", "CADETE", "CAD"), "JUVENIL": ("juvenil", "JUVENIL", "JUV")}` — categoría de la base → (clave de la web y del fichero, constante de grupos, sufijo de las demás constantes).
  - `generate_lazy_js(conn, category) -> str` — el contenido de `data-<clave>.js`, siempre (vacío si la categoría no tiene grupos o no está en `EN_WEB`), con estas constantes en este orden: `<GRUPOS>` (la forma de `BENJAMIN`), `<S>_STATS` (`{groups, teams}`), `HISTORY_<S>`, `GOL_<S>`, `ESTADOS_<S>`, `EQUIPOS_<S>` y, **solo en las categorías nuevas**, `CAMPOS_<S>` (los campos de sus partidos que no están en el `CAMPOS` de `data-history.js`, misma forma). Con `ALEVIN`, exactamente lo que hoy da `generate_alevin_js` (que queda como `generate_lazy_js(conn, "ALEVIN")`).
  - `data-history.js`: `HISTORY`, `HIST_MATCHES`, `ESTADOS` y `EQUIPOS` siguen siendo solo de `EAGER_CATEGORIES`; `EQUIPOS` sin los equipos que esa temporada solo juegan en categorías perezosas (`_lazy_only`); `CAMPOS`, de benjamín, prebenjamín y alevín (como hoy), sin los de las categorías nuevas; `COBERTURA` como hoy.
  - `data-matchdetail.js` (`MATCH_DETAIL`): solo de las categorías de hoy; `data-matchdetail-<clave>.js` con `const MATCH_DETAIL_<S>=…;` (misma forma) para cada categoría nueva, siempre (vacío `{}` si no tiene).
  - `archive_lazy(conn, season_id, season_name, category) -> dict | None` — `{name, <clave>: [grupos], gol?: {<clave>: [...]}, equipos?, campos?}` (la forma de §5 de `docs/alevin.md`, con la clave de la categoría); `data-season-<S>-<clave>.js` con `const SEASON_<S con _>_<GRUPOS>=…;`, solo si la temporada tiene grupos de esa categoría (y se borra el de una que ya no los tiene).
  - `_is_league_group(code, phase)`: además, `False` para una fase que empieza por «fase de ascenso» o «eliminatorias de ascenso» (copas, como las eliminatorias: decisión 3 de E).
  - `precache.entradas`: los opcionales siguen siendo `data-alevin.js` y los `data-season-AAAA-AAAA.js`; ni `data-infantil.js` ni `data-matchdetail-*.js` ni `data-season-*-<cat>.js`.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_categorias_generador.py` (base sintética como la de `test_alevin_generador.py`, con un grupo de benjamín, uno de alevín y uno de infantil que comparten un club, y `EN_WEB` parcheado con las seis):
  - `test_data_infantil`: `generate_lazy_js(conn, "INFANTIL")` empieza por `const INFANTIL=[` y trae, en este orden, `INF_STATS`, `HISTORY_INF`, `GOL_INF`, `ESTADOS_INF`, `EQUIPOS_INF` y `CAMPOS_INF`; el grupo `INFPG1` está en `INFANTIL` y en `HISTORY_INF`, y no en `HISTORY` de `data-history.js`.
  - `test_la_carga_inicial_no_gana_nada`: `EQUIPOS` de `data-history.js` no trae el equipo que solo juega en infantil y sí el club que juega en benjamín y en infantil; `CAMPOS` no trae el campo que solo sale en partidos de infantil; `MATCH_DETAIL` no trae partidos de infantil y `MATCH_DETAIL_INF` sí.
  - `test_temporada_pasada_de_cadete`: con un grupo de cadete en 2025-26, sale `data-season-2025-2026-cadete.js` con `SEASON_2025_2026_CADETE` y la clave `cadete`; sin él, no sale, y uno viejo se borra.
  - `test_con_en_web_de_hoy_salen_vacios`: sin parchear `EN_WEB`, `data-infantil.js` trae `const INFANTIL=[];`, `INF_STATS` a cero y lo demás vacío, y `data-matchdetail-infantil.js`, `{}`.
  - `test_el_ascenso_es_copa`: `_is_league_group("CADIA1", "Fase de Ascenso a Interinsular")` y `("JUVILE1", "Eliminatorias de Ascenso a Interinsular Lanzarote")` son `False`; `("CADI1", "Interinsular")`, `True`.
  - En `test_precache.py`: con `data-infantil.js`, `data-matchdetail-cadete.js` y `data-season-2025-2026-juvenil.js` en el árbol de la prueba, ninguno está en las entradas ni en los opcionales.
  - `test_alevin_igual_byte_a_byte` (salta sin `futbolbase.db`): sobre una copia de la base real, `generate_lazy_js(conn, "ALEVIN")` es idéntico a lo que daba `generate_alevin_js` antes de esta tarea (guárdalo del commit anterior en `scripts/tests/fixtures/data-alevin-antes.js.txt`, sin datos personales nuevos: es un fichero ya publicado).
- [ ] **Step 2: Verlas fallar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_categorias_generador.py scripts/tests/test_precache.py` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces». El comentario de `LAZY` explica por qué un fichero por categoría (una familia que sigue a un niño de infantil no baja cadete ni juvenil) y por qué los campos de las nuevas van en su fichero (la carga inicial no crece).
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && python3 scripts/prueba_mayores.py` — Expected: en verde; `test_generador_igual_con_y_sin_mayores` de E1 sigue en verde (los ficheros nuevos salen iguales, vacíos, en las dos copias).
- [ ] **Step 5: Commit.** Asunto «Generador: alevín, infantil, cadete y juvenil, cada una en su fichero perezoso».

---

### Task 2: El modelo de la web conoce las seis categorías y las fases del convenio

**Files:**
- Modify: `src/model.js` (`CATEGORIES`, `CAT_NAMES`, `CAT_WORDS`, `CAT_SHORT`, `LAZY_CATS` nueva, `catOfGroup`, `ISLAND_NAMES`, `islandSuffix`, `ISLAND_ORDER`, `PHASE_TABLE`, `PHASE_LEVEL`, `buildSeason`, `buildCups`)
- Modify: `src/state.js` (`isCupGroup`)
- Create: `scripts/tests/test_convenio_web.mjs`
- Test: `scripts/tests/test_rediseno_modulos.mjs` (la lista de categorías, hacia la línea 140 del 25/11), `scripts/tests/test_rediseno_alevin.mjs` (hacia la 46), `scripts/tests/test_rediseno_model_nombres.mjs`

**Interfaces:**
- Consumes: `scripts/tests/fixtures/convenio_mayores.json` (E1).
- Produces (en `src/model.js`):
  - `CATEGORIES = ['benjamin', 'prebenjamin', 'alevin', 'infantil', 'cadete', 'juvenil']` (las de hoy en su orden, las nuevas detrás de menor a mayor: no cambia ningún orden ni respaldo de hoy); `CAT_NAMES` gana `infantil: 'Infantil'`, `cadete: 'Cadete'`, `juvenil: 'Juvenil'`; `CAT_WORDS`, `'infantil'`, `'cadete'`, `'juvenil'`; `CAT_SHORT`, `'inf.'`, `'cad.'`, `'juv.'`.
  - `LAZY_CATS = ['alevin', 'infantil', 'cadete', 'juvenil']` (exportada).
  - `catOfGroup(raw)`: también por `fullName` con «infantil», «cadete» o «juvenil» (después de prebenjamín y antes de benjamín, como alevín).
  - `ISLAND_NAMES` gana `interinsular: 'Interinsular'`; `islandSuffix` no añade nada con la isla `interinsular` («División de Honor», no «División de Honor de Interinsular»); `ISLAND_ORDER = ['grancanaria', 'lanzarote', 'fuerteventura', 'interinsular']`.
  - `PHASE_TABLE`, reglas nuevas **delante** de la de `/\bfase ([12])\b/` y sin cambiar ninguna de hoy (las fases de hoy dan la misma clave y la misma etiqueta: `phases.json` y `phases-archivo.json` siguen en verde):
    - `/^(division de honor|autonomica|interinsular|territorial|segunda|insular b|insular)\b(?: (?:gc|lanzarote|fuerteventura|lanzarote-fuerteventura))?(?: fase (1|2|oro|plata))?(?: ([a-z]))?$/` → `division: slug(nivel)` (`'division-de-honor'`, `'autonomica'`, `'interinsular'`, `'territorial'`, `'segunda'`, `'insular-b'`, `'insular'`), `phase` (`'fase-1'`, `'fase-2'`, `'oro'`, `'plata'`, o con subgrupo `'fase-2-c'`), nombre «División de Honor», «Insular B», «Insular Fase 1»…;
    - `/^preferente\b.* fase (oro|plata)$/` → `division: 'preferente'`, `phase: 'oro'|'plata'`, nombre «Preferente Fase Oro»;
    - `/^fase de ascenso a (.+)$/` → `cup: 'ascenso'`, `cupKey: 'ascenso-' + slug(m[1])`, nombre la fase tal cual;
    - `/^eliminatorias (.+)$/` (con algo detrás: «Eliminatorias de Ascenso a …», «Eliminatorias Copa …», «Eliminatorias Preferente GC» de los grupos `…EL`) → `cup: 'eliminatorias'`, `cupKey: 'eliminatorias-' + slug(m[1])`, nombre la fase tal cual (antes de la regla `/^eliminatorias\b/` de hoy, que sigue dando lo mismo a la fase «Eliminatorias» a secas de `EL`, `PEL` y `ALEL`);
    - `/^copa (cabildo |delegacion )?(division de honor|autonomica|interinsular|territorial|preferente|primera|segunda|insular b|insular)\b/` → `cup: 'insular'`, `cupKey: 'copa-' + slug(nivel)` (con «cabildo» o «delegación», `'copa-cabildo-' + …`), `division: slug(nivel)`, nombre la fase sin la isla. Va después de la `/^copa cabildo (preferente|primera)\b/` de hoy (que sigue dando lo mismo a benjamín y alevín).
  - `PHASE_LEVEL` gana `ascenso: 2` (el equipo que juega la fase de ascenso al acabar su liga la tiene como su fase más alta, como la Segunda Fase) y `'fase-2-*'` como `'fase-2'`.
  - `buildSeason({ name, current, history, benjamin, prebenjamin, alevin, infantil, cadete, juvenil })` y `buildCups(...)`: las de `LAZY_CATS` con la misma forma que hoy `alevin` (una lista de grupos por clave).
- Produces (en `src/state.js`): `isCupGroup(g)` también con una fase que empieza por «fase de ascenso» o «eliminatorias de ascenso».

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_convenio_web.mjs`:
  - `test_todas_las_fases_del_convenio`: para cada fila de `convenio_mayores.json` (`[prefijo, fase, isla, tipo]`), un grupo crudo `{ id: prefijo + '1', cat, phase: fase, island: isla, name: 'Grupo 1', fullName }` (la categoría por el prefijo: `INF`, `CAD`, `JUV`, `AL`) clasifica como conocido (`competitionKey(g, temporada).key` no empieza por `otra-` ni por `<isla>-otra-`); dentro de cada temporada de la fila (las de la tabla), dos prefijos distintos de la misma categoría e isla nunca dan la misma `key`; `groupKind` (o `isCupGroup`) es copa para las de tipo distinto de `liga`, y liga para las de tipo `liga`.
  - `test_etiquetas`: `groupLabel` de `{cat: 'juvenil', phase: 'División de Honor', island: 'interinsular', name: 'Grupo 6'}` es «Juvenil, División de Honor, Grupo 6»; de `{cat: 'cadete', phase: 'Insular Lanzarote', island: 'lanzarote', name: 'Grupo 1'}`, «Cadete, Insular, Grupo 1 de Lanzarote»; de `{cat: 'infantil', phase: 'Preferente GC Fase Oro', island: 'grancanaria', name: 'Grupo 1'}`, «Infantil, Preferente Fase Oro, Grupo 1».
  - `test_categorias`: `CATEGORIES`, `CAT_NAMES`, `CAT_WORDS`, `CAT_SHORT` y `LAZY_CATS` con los valores de arriba; `catOfGroup` por `fullName` («CADETE INSULAR GC - GRUPO 2» → `'cadete'`; «PREBENJAMIN …» sigue siendo prebenjamín).
  - Las listas de categorías de `test_rediseno_modulos.mjs` y `test_rediseno_alevin.mjs`, con las seis.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_convenio_web.mjs` — Expected: fallan.
- [ ] **Step 3: Implementar** lo de «Produces».
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_*.mjs` — Expected: en verde (salvo lo de `dist/`, ver «Global Constraints»); `phases.json`/`phases-archivo.json` sin tocar.
- [ ] **Step 5: Commit.** Asunto «Web: el modelo conoce infantil, cadete y juvenil, la isla interinsular y las fases del convenio».

---

### Task 3: La carga perezosa, para las cuatro

**Files:**
- Modify: `src/state.js` (todo lo de alevín, hacia las líneas 466-600 del 25/11)
- Modify: `src/app.js` (el registro de datos, hacia la línea 56)
- Modify: `src/router.js` (`alevinMissing`, `needsAlevin`, `missingGroup`, `resolveParams`, `startRouter` y `alevinWant`/`alevinTried`: hacia las líneas 68-237 y 447-640)
- Modify: `src/model.js` (`createModel`: `alevinOf` → `lazyOf(cat, season)`, hacia las líneas 980-1125)
- Test: `scripts/tests/test_rediseno_alevin.mjs`, `scripts/tests/test_rediseno_state.mjs`, `scripts/tests/test_rediseno_router.mjs`, `scripts/tests/test_perezosas.mjs` (nuevo)

**Interfaces:**
- Consumes: `LAZY_CATS` (tarea 2); los ficheros de la tarea 1.
- Produces:
  - `src/state.js`: `LAZY = { alevin: { file: 'data-alevin.js', consts: { groups: 'ALEVIN', stats: 'ALEV_STATS', history: 'HISTORY_ALEV', gol: 'GOL_ALEV', estados: 'ESTADOS_ALEV', equipos: 'EQUIPOS_ALEV' } }, infantil: { file: 'data-infantil.js', consts: { groups: 'INFANTIL', stats: 'INF_STATS', history: 'HISTORY_INF', gol: 'GOL_INF', estados: 'ESTADOS_INF', equipos: 'EQUIPOS_INF', campos: 'CAMPOS_INF' } }, cadete: { … 'CADETE', 'CAD_…' }, juvenil: { … 'JUVENIL', 'JUV_…' } }`; `lazyData(cat, consts) -> { groups, stats, history, gol, estados, equipos, campos }`; `ensureLazy(cat) -> Promise<data | null>` y `ensureSeasonLazy(cat, season) -> Promise<object | {} | null>` (como `ensureAlevin` y `ensureSeasonAlevin` hoy: un vuelo por fichero, el texto leído por expresión regular, un 404 es «sin esa categoría» y se memoriza, un fallo da `null` sin memorizarse); `lazyNeeds(cat, name, datasets, portalSeason, loaders)` y `loadLazySeasons(datasets, names, portalSeason, cats = LAZY_CATS, loaders) -> Promise<[{cat, season}] fallidas>`. `ensureAlevin`, `ensureSeasonAlevin`, `alevinData`, `alevinNeeds` y `loadAlevinSeasons` se quedan como envolturas de una línea (las usan pruebas y pantallas de hoy).
  - Registro de datos (`app.js`): `lazy: { alevin: undefined, infantil: undefined, cadete: undefined, juvenil: undefined }` y `seasonLazy: { alevin: {}, infantil: {}, cadete: {}, juvenil: {} }` en lugar de `alevin` y `seasonAlevin` (cambia el registro, no los ficheros: las pruebas que montan `datasets.alevin` pasan a `datasets.lazy.alevin`).
  - `src/router.js`: `needsLazy(route, ctx) -> [{ cat, season, soft }]` — `c=<cat perezosa>` en Ligas, Goleadores y Récords (y la categoría por defecto de esas dos), de esa categoría y sin `soft`; Explorar y Ligas sin categoría, todas las perezosas con `soft`; un grupo de la ruta que no está, la de su prefijo si es perezosa (`AL` → alevín, `INF`, `CAD`, `JUV`) o, si no se sabe, todas con `soft`; Mi equipo, la de su categoría. `ctx.lazyFailed: string[]` (las categorías `soft` que no llegaron) sustituye a `ctx.alevinFailed`.
  - `createModel`: `lazyOf(cat, season)` sustituye a `alevinOf`; `season(name)`, `teamsOf`, `camposOf` (con los `campos` de cada perezosa), `estadosOf` y `scorersOf(cat, season)` recorren `LAZY_CATS`.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_perezosas.mjs` (con `fetchData` falso, como `test_rediseno_state.mjs`):
  - `test_ensure_lazy`: `ensureLazy('cadete')` parsea las siete constantes de un `data-cadete.js` falso; dos llamadas comparten el vuelo; un 404 da datos vacíos y se memoriza; un fallo de red da `null` y no se memoriza; `ensureLazy('alevin')` da lo mismo que `ensureAlevin()`.
  - `test_lazy_needs_y_fallos`: `needsLazy` de `#/ligas?c=juvenil&s=2026-2027` es `[{cat: 'juvenil', season: '2026-2027', soft: false}]`; de `#/explorar`, las cuatro con `soft: true`; de `#/tabla?g=CADNG2&s=2026-2027` sin cadete cargado, `[{cat: 'cadete', …, soft: false}]`; con `data-juvenil.js` fallando en Explorar, la ruta se pinta con `ctx.lazyFailed == ['juvenil']`.
  - `test_temporada_pasada`: `loadLazySeasons(datasets, ['2025-2026'], '2026-2027')` pide `data-season-2025-2026-alevin.js`, `-infantil.js`, `-cadete.js` y `-juvenil.js`, trata sus 404 como «sin esa categoría» y devuelve solo las que fallaron de verdad.
  - `test_modelo_con_las_perezosas`: `createModel` con `lazy.infantil` cargado: la temporada del portal tiene los grupos de infantil con `cat: 'infantil'`, su `history` y sus estados; `teamsOf('2026-2027', 'infantil')` saca `EQUIPOS_INF`; `camposOf` une `CAMPOS` y `CAMPOS_INF`.
  - Las de alevín de hoy (`test_rediseno_alevin.mjs`), con el registro nuevo y el mismo comportamiento.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_perezosas.mjs scripts/tests/test_rediseno_alevin.mjs` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces».
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_*.mjs` — Expected: en verde (salvo `dist/`).
- [ ] **Step 5: Commit.** Asunto «Web: la carga perezosa de alevín sirve para infantil, cadete y juvenil».

---

### Task 4: Las pantallas

**Files:**
- Modify: `src/shell.js` (`alevinFailedBox` → `lazyFailedBox(cats)`), `src/screen-explorar.js`, `src/screen-ligas.js`, `src/screen-tabla.js`, `src/screen-jornada.js`, `src/screen-equipo.js`, `src/team-extras.js` (trayectoria: `alevinMissingBox` → la de las perezosas), `src/screen-partido.js` (temporadas anteriores, hacia las líneas 388 y 489), `src/screen-temporadas.js`, `src/screen-fuentes.js` (la salud del carril), `src/myteam.js` (`defaultCategory` ya recorre `CATEGORIES`; lo que mire `alevin` a mano)
- Test: `scripts/tests/test_rediseno_explorar.mjs`, `scripts/tests/test_rediseno_ligas.mjs` (o el de Ligas), `scripts/tests/test_detalle_web.mjs`, `scripts/tests/test_navegacion_grupos.mjs`, `scripts/tests/test_rediseno_fuentes.mjs` (o el de Fuentes), `scripts/tests/test_myteam*.mjs`

**Interfaces:**
- Consumes: tareas 2 y 3 (`CATEGORIES`, `LAZY_CATS`, `ctx.lazyFailed`, `loadLazySeasons`, `lazyOf`).
- Produces:
  - `lazyFailedBox(cats: string[])` — «No se pudieron cargar los datos de juvenil: se ven las demás categorías.» (con dos o más, «de cadete y juvenil»), con «Reintentar»; con `['alevin']`, el texto de hoy.
  - Explorar y Ligas: las categorías nuevas en sus listas y filtros (ya recorren `CATEGORIES`); el filtro de isla con «Interinsular» al final.
  - Equipo y la trayectoria: carga las perezosas que falten con `loadLazySeasons` (todas, no solo alevín) y avisa de las que no llegan, con su nombre.
  - Partido, «Temporadas anteriores»: con un grupo de categoría perezosa, carga esa categoría de las temporadas pasadas (no solo alevín).
  - Fuentes: bajo el veredicto de la pasada, una línea «Carril de infantil, cadete y juvenil: …» con `carriles.mayores.runHealth` (mismo texto que `runHealthNote`) si existe; nada si no.
  - Pronóstico (`pronostico.js`): sin cambio (solo prebenjamín).

- [ ] **Step 1: Pruebas que fallan:**
  - `test_explorar_con_una_perezosa_caida`: Explorar con infantil y cadete cargados y juvenil a `null`: lista las competiciones de infantil y de cadete, el aviso nombra juvenil y no alevín, y «Reintentar» está.
  - `test_un_club_en_dos_categorias`: un equipo que juega en `FF3` (benjamín) y en `JUV2G1` (juvenil) con el mismo nombre: el buscador de Explorar lo da dos veces, «Benjamín» y «Juvenil»; la ficha del equipo en `JUV2G1` enseña su calendario de juvenil; la trayectoria del club lista los dos grupos de 2026-27 en su categoría.
  - `test_ligas_interinsular`: Ligas de juvenil con «División de Honor» (`interinsular`), «Preferente GC» y «Preferente Lanzarote»: el filtro de isla tiene Gran Canaria, Lanzarote e Interinsular, en ese orden, y la competición de División de Honor sale con su nombre sin «de Interinsular».
  - `test_partido_temporadas_anteriores_cadete`: un partido de `CADNG2` pide el cadete de las temporadas pasadas; sin él (un fallo), la caja de error de hoy.
  - `test_fuentes_carril`: con `carriles.mayores.runHealth.ok` falso y motivos, la línea del carril los enseña; sin `carriles`, no hay línea.
  - Mi equipo: `defaultCategory` de un equipo resuelto en cadete es `'cadete'`.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_rediseno_explorar.mjs scripts/tests/test_detalle_web.mjs scripts/tests/test_navegacion_grupos.mjs` y las de Ligas, Fuentes y Mi equipo — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar** lo de «Produces».
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_*.mjs` — Expected: en verde (salvo `dist/`).
- [ ] **Step 5: Commit.** Asunto «Web: Explorar, Ligas, Tabla, Jornada, Equipo, Partido, Temporadas y Mi equipo con las categorías nuevas».

---

### Task 5: El selector de categoría para seis (Goleadores y Récords)

**Files:**
- Modify: `src/ui.js` (`categoryPicker` nueva), `src/screen-goleadores.js` (hacia la línea 24), `src/screen-records.js` (hacia las líneas 16 y 91), `acta.css` (`.cat-picker`)
- Test: `scripts/tests/test_rediseno_goleadores.mjs` (o el de Goleadores), `scripts/tests/test_rediseno_records.mjs`, `scripts/tests/test_rediseno_css.mjs`, `scripts/tests/interaction-smoke.mjs` (un escenario a 320 px)

**Interfaces:**
- Consumes: `CATEGORIES`, `CAT_NAMES`.
- Produces:
  - `categoryPicker(cats: string[], current: string, hrefFor: (cat) => string, { label = 'Categoría' } = {})` — una fila de enlaces con el nombre entero de cada categoría (`CAT_NAMES`), el elegido con `aria-current="true"`; si no caben, **se desplaza la fila, no la página** (`overflow-x: auto`, sin barra visible en móvil, con el elegido a la vista al pintar), como la fila de años del ranking (parte B). Sustituye al `segmented` de las dos pantallas.
  - `cats` son las categorías **que tienen grupos en esa temporada** (en una pasada sin infantil, no sale), más la elegida si viniera en la dirección; con una sola, no se pinta selector.

- [ ] **Step 1: Pruebas que fallan:**
  - `test_selector_de_categorias`: Goleadores y Récords de 2026-27 con las seis categorías con grupos pintan seis enlaces en el orden de `CATEGORIES`, el elegido con `aria-current`; de 2021-22 con solo benjamín y prebenjamín, dos; con una sola, ninguno.
  - En `test_rediseno_css.mjs`: `.cat-picker` tiene `overflow-x: auto` y sus enlaces `white-space: nowrap`; la página no gana `overflow-x`.
  - En `interaction-smoke.mjs`: «Goleadores a 320 px con seis categorías» y «Récords a 320 px con seis categorías», en claro y en oscuro: `document.documentElement.scrollWidth <= 320` y el enlace elegido (juvenil) visible tras desplazar la fila.
- [ ] **Step 2: Verlas fallar.** Run: `node --test scripts/tests/test_rediseno_records.mjs scripts/tests/test_rediseno_css.mjs` — Expected: fallan las nuevas.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `node --test scripts/tests/test_*.mjs && node scripts/tests/interaction-smoke.mjs` — Expected: en verde (salvo `dist/`).
- [ ] **Step 5: Capturas.** Run: `OUT=$(mktemp -d) node scripts/tests/capturas.mjs` y mira las de Goleadores y Récords a 390 px en claro y en oscuro (con el mundo M de la tarea 7, cuando exista; hasta entonces, con el de alevín). Adjunta en el informe la ruta de las dos capturas.
- [ ] **Step 6: Commit.** Asunto «Goleadores y Récords: el selector de categoría cabe con seis».

---

### Task 6: Fichas, buscador y ranking con las categorías nuevas

**Files:**
- Modify: `scripts/generate_js.py` (`_datos_fichas`/`ranking_files`: el `mejor` de cada fila de una categoría nueva para `ranking.fase_que_cuenta`)
- Modify: `src/screen-ranking.js` (la categoría de cada fila con `CAT_NAMES`), `src/screen-jugador.js` (comprobar que `CAT_ORDER`, que ya tiene `juvenil`, `cadete`, `infantil`, se usa para el «Resumen»)
- Test: `scripts/tests/test_jugadores_ampliacion.py`, `scripts/tests/test_rediseno_ranking.mjs`, `scripts/tests/test_jugador.mjs`

**Interfaces:**
- Consumes: `ranking.fase_que_cuenta(fase, mejor)` con fase entera (E1, tarea 5); `nacimiento.VENTANA`.
- Produces:
  - En las filas del ranking de una categoría de `MAYORES` (o alevín de islas), `mejor` es la fase de liga con más `nivel_fase` que tuvo su equipo esa temporada en esa categoría (de los grupos con `tiene_nivel`), para que una copa o un ascenso cuenten con el nivel de su liga; en las de hoy, la letra de la Segunda Fase, como ahora.
  - `screen-ranking.js`: «equipo · Juvenil» con el nombre de `CAT_NAMES` (hoy salía la clave si no era una de las tres).

- [ ] **Step 1: Pruebas que fallan:**
  - En `test_jugadores_ampliacion.py`, con `EN_WEB` parcheado con las seis: `test_ranking_de_cadete`: un niño de cadete con 10 goles en 12 partidos de «Interinsular» y 3 en 2 de «Copa Insular Lanzarote» (su equipo juega «Interinsular»): las filas de copa cuentan con nivel `1.35`; uno con los mismos goles en «Insular GC», con `0.90`; los dos salen en el ranking de su año en ese orden.
  - `test_ficha_de_benjamin_a_cadete`: un niño con identificador con filas de benjamín 2019-20 y de cadete 2026-27 tiene una sola ficha con las dos categorías en su «Resumen» y año estimado 2011 (el cruce de las dos ventanas).
  - En `test_rediseno_ranking.mjs`: una fila de categoría `cadete` dice «· Cadete».
  - En `test_jugador.mjs`: el «Resumen» con filas de juvenil, cadete y benjamín va en ese orden.
- [ ] **Step 2: Verlas fallar** con `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_jugadores_ampliacion.py` y `node --test scripts/tests/test_rediseno_ranking.mjs scripts/tests/test_jugador.mjs`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && python3 scripts/prueba_mayores.py` — Expected: en verde (salvo `dist/`).
- [ ] **Step 5: Commit.** Asunto «Fichas y ranking: infantil, cadete y juvenil, con el nivel de su liga».

---

### Task 7: Escudos, fixtures y capturas

**Files:**
- Modify: `scripts/check_missing_shields.py` (las categorías de `categorias.DB_NAME`, no tres a mano: hacia las líneas 15, 35-41, 103 y 121 del 25/11)
- Modify: `scripts/tests/fixture-site.mjs` (un mundo `M`: 2026-27 con dos grupos de infantil, dos de cadete —uno `CADI1` interinsular— y uno de juvenil, con clubes que también están en benjamín, actas y goleadores; nombres inventados), `scripts/tests/render-smoke.mjs`, `scripts/tests/capturas.mjs` (las pantallas del mundo `M`: Explorar, Ligas de juvenil, Tabla de `CADI1`, Equipo con trayectoria, Goleadores y Récords a 390 px en claro y en oscuro y a 1440 px en claro), `scripts/tests/aislamiento-smoke.mjs` (si mira categorías a mano)
- Test: `scripts/tests/test_check_missing_shields.py` (o el que pruebe ese script), los tres `.mjs` de arriba

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `check_missing_shields.py` cuenta y lista los escudos que faltan de las seis categorías; el mundo `M` de `fixture-site.mjs` (`useWorld('M')`).

- [ ] **Step 1: Pruebas que fallan:** el escudo que falta de un equipo que solo juega en juvenil sale en la lista; `render-smoke.mjs` con el mundo `M` pinta sin errores de consola Explorar, Ligas, Tabla, Jornada, Equipo, Partido, Goleadores, Récords y Temporadas; `interaction-smoke.mjs` recorre a 320 px Ligas de cadete y la Tabla de `CADI1` sin desplazamiento horizontal.
- [ ] **Step 2: Implementar.**
- [ ] **Step 3: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && node scripts/tests/render-smoke.mjs && node scripts/tests/interaction-smoke.mjs` — Expected: en verde (salvo `dist/`).
- [ ] **Step 4: Capturas.** Run: `OUT=$(mktemp -d) node scripts/tests/capturas.mjs`; mira las del mundo `M` (claro y oscuro) y apunta en el informe su ruta y lo que se haya corregido al verlas.
- [ ] **Step 5: Commit.** Asunto «Web: escudos, fixtures y capturas de infantil, cadete y juvenil».

**PASO DEL DIRECTOR — E2-D1: publicar las tareas 1-7.** Con `R=malolocabreralolo-tech/futbol-base-v2` y nada en marcha (`gh run list -R $R --status in_progress` y `--status queued`, vacías): rebasar sobre `main` (`docs/rediseno-rebase.md`), `python3 scripts/publicar.py` (empaqueta `dist/`), las dos suites y `python3 scripts/prueba_mayores.py` en verde, `git push origin categorias:main`. Comprobación: la pasada siguiente en verde; en la web publicada, Explorar y Ligas igual que antes (las categorías nuevas aún no tienen datos: `data-infantil.js` publicado con `const INFANTIL=[];`), y `index.html` pide los mismos ficheros que antes (`git show origin/main:index.html | grep -o 'data-[a-z0-9-]*\.js' | sort -u` igual que con el `main` de antes de empujar). Vuelta atrás: `git revert` y volver a empaquetar.

---

### Task 8: El paso: la web ve las categorías nuevas

**Files:**
- Modify: `scripts/categorias.py` (`EN_WEB = ("BENJAMIN", "PREBENJAMIN", "ALEVIN", "INFANTIL", "CADETE", "JUVENIL")`)
- Modify: `scripts/medir_identidad.py` (`--entre-categorias` y `--db`: solo lectura; cuántas fichas une el resolvedor entre categorías al ampliar `EN_WEB`, por regla de `docs/identidad.md`, y cuántas no une por las edades)
- Modify: `docs/categorias-mayores.md` («En la web»), `docs/identidad.md` (lo medido), `docs/decisiones.md` (una línea)
- Test: `scripts/tests/test_fichas_ampliadas.py` (nuevo)

**Interfaces:**
- Consumes: todo lo anterior; una base con al menos infantil activado (paso D3 de E1) para la medida y para la prueba sobre la base real.
- Produces: con `EN_WEB` de seis, `vista_web.copia_web` devuelve la misma conexión, el resolvedor mira todas las apariciones y el generador publica todo.

- [ ] **Step 1: Pruebas que fallan** en `scripts/tests/test_fichas_ampliadas.py` (salta sin `futbolbase.db`; sobre una copia de la base real con `base_mayores.poblar`):
  - `test_las_claves_de_hoy_siguen_valiendo`: el conjunto de claves (`p` y alias) de `data-jugadores-*.js` generados con `EN_WEB` de E1 está contenido en el de los generados con `EN_WEB` de seis (ninguna clave publicada hoy deja de resolver una ficha).
  - `test_nadie_se_une_con_edades_imposibles`: ninguna ficha del resultado tiene un intervalo de edad vacío (`identidad.compatibles` de todas sus vistas) ni junta dos jugadores con identificador distinto de la federación.
  - `test_trayectorias`: al menos la mitad de los jugadores reutilizados por `poblar` (los que tienen el identificador de un niño de benjamín o alevín) acaban en una ficha con filas de las dos categorías.
- [ ] **Step 2: Verlas fallar** (con `EN_WEB` todavía de E1). Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fichas_ampliadas.py` — Expected: fallan las que dependen del cambio.
- [ ] **Step 3: Implementar** el cambio de `EN_WEB` y el apartado de `medir_identidad.py`.
- [ ] **Step 4: Ejecutar.** Run: `python3 -m pytest -q -p no:cacheprovider scripts/tests/ && node --test scripts/tests/test_*.mjs && python3 scripts/prueba_mayores.py` — Expected: en verde (salvo `dist/`).
- [ ] **Step 5: Medir** sobre una copia de la base de `main` (con lo que el bot ya haya leído): `python3 scripts/medir_identidad.py --entre-categorias --db <copia>` (el apartado nuevo; solo lee); apunta en `docs/identidad.md` las fichas unidas entre categorías por regla, las que no se unen por la edad y los segundos del resolvedor (hoy, 7,7 s con 19.301 identidades), y en el informe el tamaño de `data-jugadores-*`, `data-buscar-*` y `data-lineups-2026-2027-*` antes y después.
- [ ] **Step 6: Commit.** Asunto «Web: infantil, cadete y juvenil, publicados; las fichas siguen a cada niño de una categoría a otra».

**PASO DEL DIRECTOR — E2-D2: publicar el paso.** Con la tarea 8 en la rama y nada en marcha:
1. `git fetch origin && git rebase origin/main` (la base de `main` ya trae lo leído por el carril); `python3 scripts/prueba_mayores.py` y `python3 -m pytest -q -p no:cacheprovider scripts/tests/test_fichas_ampliadas.py` en verde sobre ella; la medida de la tarea 8 revisada (si une más de un 2 % de las fichas entre categorías por la regla de nombre y club sin identificador, se para y se mira antes de seguir).
2. `python3 scripts/publicar.py`, las dos suites y `git push origin categorias:main`.
3. Comprobación: la pasada siguiente en verde y con commit de datos; en la web publicada, Explorar con Infantil, Cadete y Juvenil; una Tabla de cadete; la ficha de un niño de cadete que venía de benjamín con las dos categorías en su trayectoria; Goleadores con el selector de seis a 320 px; el tamaño del commit (`git show --stat`) dentro de lo previsto (~+15 MB de `data-lineups` a esta altura de la temporada).
4. Vuelta atrás: `git revert` del commit de `EN_WEB` (con nada en marcha) y volver a empaquetar: la pasada siguiente vuelve a publicar sin las categorías nuevas (sus `data-*.js` vacíos) y el resolvedor deshace las uniones entre categorías; las claves de las fichas de hoy no se han perdido en ningún momento (`test_las_claves_de_hoy_siguen_valiendo`).
