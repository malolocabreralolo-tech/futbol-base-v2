# v2 · Fase 2A: las competiciones que faltan — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que v2 tenga las tres competiciones de 2026-27 que la federación ya publicó y la web no tiene, y que actualizar el catálogo de la federación no pueda volver a parar al bot.

**Architecture:** Tres cambios de código pequeños (las pruebas dejan de leer el catálogo vivo, un convenio de código para la Copa Benjamín de Gran Canaria y fuera el paso de avisos por issue, que no funciona) y después la activación con el procedimiento que ya existe (`discover-fiflp.yml` → `fetch-fiflp-islas.yml` → `fiflp_manifest.py` → `activate_season.py --add`), dentro de una ventana con el bot parado.

**Tech Stack:** Python 3.11/3.12 + SQLite, GitHub Actions, la web sin compilar (`src/model.js` para las fases).

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O3, 7.4). Mapa del código, con fichero y línea de todo lo que se toca: `docs/superpowers/plans/2026-11-13-v2-fase2-mapa.md` (bloque A y trampas 1 a 6 y 16).

## Global Constraints

- Repositorio: `/home/manolo/claude/futbol-base-v2`, remoto `origin` = `malolocabreralolo-tech/futbol-base-v2`. **v1 no se toca** (ni su repositorio, ni su reloj del PC).
- La federación (fiflp.com) solo responde desde GitHub Actions: nada de pedirle páginas desde el PC. Toda orden `gh` lleva `-R malolocabreralolo-tech/futbol-base-v2`.
- El bot de v2 comitea en `main` cada 1-2 h y ejecuta `python3 -m pytest scripts/tests/ -q` y `node --test scripts/tests/test_*.mjs` antes de publicar: **si una de las dos suites queda en rojo en `main`, v2 deja de publicar datos**. Nada se empuja con una prueba en rojo.
- La base (`futbolbase.db`) es binaria: un conflicto no se fusiona. Los cambios que la tocan se hacen con el bot parado (tarea 4).
- Competiciones que entran: Copa Benjamín Gran Canaria (55331982), Liga Prebenjamín Lanzarote (54977161), Liga Prebenjamín Fuerteventura (54977026). No entran: fútbol sala (54977051, 54977049) ni alevín de Lanzarote y Fuerteventura (54976933, 54976977).
- Códigos de grupo: únicos entre categorías dentro de la temporada. Prebenjamín Lanzarote `PLZ<n>`, fase «Lanzarote»; prebenjamín Fuerteventura `PFV<n>`, fase «Fuerteventura» (ya los da `comp_meta`). Copa Benjamín Gran Canaria: **`CGC<n>`, fase «Copa Gran Canaria»**. Nunca `BC*` ni `PCC*` (son la Copa de Campeones y `synth_copa_campeones.py` les reescribe la tabla).
- «COPA CAMPEONES BENJAMÍN» y «COPA CAMPEONES PREBENJAMIN» siguen abortando en `comp_meta`.
- Ninguna fase nueva puede caer en la clave «otra-…» de `competitionKey`.
- No se añaden avisos externos de ningún tipo (decisión del dueño).
- Suites en verde al acabar cada tarea de código: `python3 -m pytest scripts/tests/ -q` (1329 passed, 5 skipped de base; reescribe `scripts/fiflp_actas_unmatched.json`: después `git checkout -- scripts/fiflp_actas_unmatched.json`) y `node --test scripts/tests/test_*.mjs` (998 de base). `.github/workflows/` se edita con `python3` o `sed` desde la terminal (un hook bloquea las herramientas de edición).
- Español en código, comentarios, mensajes y commits; los comentarios dicen el porqué en una frase. `git add` por nombre. Cada commit acaba con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```
- Los implementadores no hacen `git push`, ni lanzan workflows, ni tocan la base viva: eso es de la tarea 4, que hace el controlador.

## Review Focus

1. **El catálogo de la federación cambia otra vez** (aparece la Segunda Fase, por ejemplo) → ninguna prueba que ejecute el bot depende del fichero vivo; el bot sigue publicando. (Tarea 1, `test_ninguna_prueba_lee_el_catalogo_vivo`.)
2. **Una copa que no es la de campeones** con otro nombre parecido («COPA BENJAMIN GRAN CANARIA» sin tilde, con espacios dobles) → mismo código; y la de campeones sigue abortando. (Tarea 2.)
3. **El raw de la tanda trae a la vez una competición con convenio y otra sin él** → el manifiesto con `--comps` sale bien y sin él aborta diciendo cuál. (Tarea 2, `test_el_manifiesto_filtrado_no_aborta_por_otra_competicion`.)
4. **El paso de avisos ya no existe** → `update.yml` no pide el permiso `issues` y ninguna pasada intenta abrir una issue; `newCompetitions` sigue llegando a `data-health.json` y a «Datos y fuentes». (Tarea 3.)
5. **Un grupo nuevo con un equipo que ya existe en la base con otro nombre** → la activación lo reconcilia o aborta sin escribir nada; nunca dos filas para el mismo club. (Tarea 4, verificación antes de `--apply`.)

---

### Task 1: Las pruebas dejan de leer el catálogo vivo

**Files:**
- Create: `scripts/tests/fixtures/fiflp_comps_catalog.json` (copia exacta del `scripts/fiflp_comps_catalog.json` de hoy)
- Modify: `scripts/tests/test_competiciones_nuevas.py`, `scripts/tests/test_alevin_descargas.py` (y `scripts/tests/test_categorias.py`, `scripts/tests/test_fiflp_actas_enumeration.py` si leen el fichero vivo)
- Test: `scripts/tests/test_catalogo_congelado.py` (nuevo)

**Interfaces:**
- Las 7 pruebas que hoy fallarían con un catálogo nuevo (4 en `test_competiciones_nuevas.py`, 3 en `test_alevin_descargas.py`: mapa, A3) pasan a leer `scripts/tests/fixtures/fiflp_comps_catalog.json`. Donde la función probada lee el catálogo por su cuenta (`fetch_fiflp_islas.comps_from_catalog(season_name, catalog=None, …)`, `fetch_fiflp_actas.catalog_comps`), se le pasa el catálogo de la fixture por parámetro; si no lo admite, se le añade un parámetro opcional `catalog=None` con el comportamiento de hoy por defecto.
- Ningún cambio de comportamiento en el código de producción.

- [ ] **Step 1: Escribir la prueba que falla** (`test_catalogo_congelado.py`)

```python
VIVO = "fiflp_comps_catalog.json"

def test_ninguna_prueba_lee_el_catalogo_vivo():
    """El bot ejecuta estas pruebas antes de publicar: si leyeran el catálogo que actualiza
    discover-fiflp.yml, una competición nueva de la federación lo dejaría sin publicar."""
    culpables = []
    for ruta in sorted(TESTS.glob("test_*.py")):
        if ruta.name == "test_catalogo_congelado.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if VIVO in linea and "fixtures" not in linea:
                culpables.append(f"{ruta.name}:{n}")
    assert culpables == []

def test_las_pruebas_pasan_con_un_catalogo_vivo_distinto(tmp_path):
    """Con una competición inventada añadida al catálogo vivo, las suites del catálogo siguen en verde."""
    # copia scripts/ a tmp_path, añade {"id": "99999999", "name": "LIGA BENJAMIN INVENTADA"} a
    # ["2026-2027"]["all"] y ["relevant"] del catálogo vivo de la copia, y ejecuta allí
    # pytest de test_competiciones_nuevas.py y test_alevin_descargas.py: código 0.
```

- [ ] **Step 2: Verla fallar** — Run: `python3 -m pytest scripts/tests/test_catalogo_congelado.py -q` — Expected: FAIL (lista de `fichero:línea` no vacía).
- [ ] **Step 3: Crear la fixture y cambiar las pruebas.**
- [ ] **Step 4: Suites enteras en verde.** Además, comprobación manual que va al informe: sustituir en una copia temporal el catálogo vivo por el de `~/backups/futbol-base/local-v1/catalogo-federacion-20261113.json` (trae las tres competiciones nuevas) y ejecutar pytest entero: 0 fallos (antes, 7).
- [ ] **Step 5: Commit** — `git commit -m "pruebas: el catálogo de la federación, congelado en una fixture (uno nuevo ya no para al bot)"`

---

### Task 2: Código para la Copa Benjamín de Gran Canaria

**Files:**
- Modify: `scripts/fiflp_manifest.py` (`comp_meta`, cabecera de convenios), `docs/temporada-nueva.md`
- Test: `scripts/tests/test_alevin_activacion.py` (o el fichero donde están `test_comp_meta_codes` y `test_comp_meta_refuses_…`), `scripts/tests/test_rediseno_model_competicion.mjs`

**Interfaces:**
- `comp_meta("COPA BENJAMÍN GRAN CANARIA")` → `("CGC", "Copa Gran Canaria")`. Vale también sin tilde y con espacios de más. No casa con ningún nombre que lleve «CAMPEONES», ni con sala, ni con prebenjamín o alevín (esos siguen como hoy).
- La isla de un código `CGC<n>` es `grancanaria` (como sale del prefijo en `fiflp_manifest.build`; compruébalo).
- En la web no hace falta regla nueva: «Copa Gran Canaria» ya casa con `/^copa\b/` de `PHASE_TABLE` (clave `copa`). Se fija con una prueba.
- `docs/temporada-nueva.md`: `PHASE_LEVEL` está en `src/model.js`, no en `src/myteam.js`; la sonda de «otra-…» carga también `data-alevin.js`; y el apartado de añadir una fase a mitad de temporada explica la ventana con el bot parado (tarea 4) y el filtro `--comps`.

- [ ] **Step 1: Pruebas que fallan**

```python
def test_copa_benjamin_de_gran_canaria_tiene_codigo():
    assert comp_meta("COPA BENJAMÍN GRAN CANARIA") == ("CGC", "Copa Gran Canaria")
    assert comp_meta("COPA  BENJAMIN GRAN CANARIA") == ("CGC", "Copa Gran Canaria")
    for nombre in ("COPA CAMPEONES BENJAMÍN", "COPA CAMPEONES PREBENJAMIN", "COPA BENJAMIN FUTBOL SALA GRAN CANARIA"):
        with pytest.raises(ValueError): comp_meta(nombre)

def test_el_manifiesto_filtrado_no_aborta_por_otra_competicion():
    # raw con un grupo de «LIGA PREBENJAMIN LANZAROTE» y otro de «TORNEO PREBENJAMIN X» (sin convenio):
    # build(...) sobre el raw entero lanza ValueError que nombra el torneo; con el raw filtrado como hace --comps
    # devuelve un grupo PLZ1 con fase «Lanzarote» e isla lanzarote.
```
```js
test('«Copa Gran Canaria» de benjamín no cae en otra-', () => {
  const key = competitionKey({ cat: 'benjamin', phase: 'Copa Gran Canaria', island: 'grancanaria', id: 'CGC1' }, '2026-2027');
  assert.doesNotMatch(key, /otra-/);
  assert.equal(isCupGroup({ id: 'CGC1', phase: 'Copa Gran Canaria' }), true);
});
```
(ajusta la forma de los argumentos a la de las pruebas vecinas)

- [ ] **Step 2: Verlas fallar** · **Step 3: Implementar** · **Step 4: Suites enteras en verde** · **Step 5: Commit** — `git commit -m "activación: código CGC para la Copa Benjamín de Gran Canaria"`

---

### Task 3: Fuera el paso de avisos por issue

**Files:**
- Delete: `scripts/avisar_competiciones.py`
- Modify: `.github/workflows/update.yml` (el paso «Avisar de competiciones nuevas» y el permiso `issues: write`), `scripts/tests/test_workflows.py`, `scripts/tests/test_competiciones_nuevas.py`, los comentarios que lo nombran (`scripts/update_fiflp.py:608-610,650-651`), `docs/federacion.md`, `docs/temporada-nueva.md`

**Interfaces:**
- `update.yml` queda sin ese paso y con `permissions: contents: write` solo.
- `check_competitions` y `newCompetitions` en `data-health.json` no cambian: «Datos y fuentes» sigue diciendo qué competiciones faltan.
- Las cinco pruebas del aviso se quitan con el script; el resto de `test_competiciones_nuevas.py` deja de importarlo y sigue pasando. `test_update_opens_one_issue_per_new_competition_without_stopping_the_bot` pasa a ser `test_update_no_abre_issues`: ni el paso, ni `issues: write`, ni `GH_TOKEN` en ningún paso de `update.yml`.

- [ ] **Step 1: Prueba que falla** (`test_update_no_abre_issues`) · **Step 2: Verla fallar** · **Step 3: Quitar el script, el paso y el permiso, y adaptar pruebas y textos** · **Step 4: Suites enteras en verde** · **Step 5: Commit** — `git commit -m "bot: fuera el aviso por issue (no funcionaba y no se quieren avisos externos)"`

---

### Task 4: Activar las tres competiciones (controlador)

Con el bot parado. Si algo falla en cualquier paso, se para, no se empuja nada y se vuelve a activar el reloj.

- [ ] **Step 1: Publicar las tareas 1 a 3** (suites en verde, nada en marcha, `git pull --rebase`, push, `Tests` de GitHub en verde).
- [ ] **Step 2: Parar el bot**: `gh workflow disable reloj.yml -R malolocabreralolo-tech/futbol-base-v2`; esperar a que no haya ninguna «Actualización automática» en marcha.
- [ ] **Step 3: Catálogo**: `gh workflow run discover-fiflp.yml -R …`; al acabar, `Tests` del commit del catálogo tiene que salir en verde (es la comprobación real de la tarea 1).
- [ ] **Step 4: Grupos, tablas y calendarios**: `gh workflow run fetch-fiflp-islas.yml -R … -f temporada=22 -f ids=54977161,54977026,55331982`; `git pull`.
- [ ] **Step 5: Manifiesto y verificación**, en local:
  ```bash
  python3 scripts/fiflp_manifest.py scripts/fiflp_islas_22_raw.json 2026-2027 --comps 54977161,54977026,55331982 > docs/temporadas/2026-2027-noviembre.json
  python3 scripts/activate_season.py docs/temporadas/2026-2027-noviembre.json --fiflp-raw scripts/fiflp_islas_22_raw.json --add
  ```
  Mirar el manifiesto: códigos, fases, islas, número de grupos y de equipos; que ningún equipo nuevo sea en realidad uno que ya está con otro nombre.
- [ ] **Step 6: Aplicar**: copia de la base aparte (`futbol-base-copia ejecutar` deja la de hoy en versiones), `… --add --apply`, `python3 scripts/codigo.py --check`.
- [ ] **Step 7: Comprobar**: suites enteras y los cuatro smokes de navegador en verde; la sonda de «otra-…» (con alevín) da 0; en el navegador, Explorar enseña las tres competiciones y cada una abre su Tabla y su Jornada (capturas en móvil).
- [ ] **Step 8: Publicar y arrancar**: commit de la base, los `data-*.js`, `index.html`, `sw.js` y el manifiesto; push; `gh workflow enable reloj.yml -R …`; lanzar una pasada y comprobar que lee los grupos nuevos (primera lectura completa) y que la web publicada los enseña.
- [ ] **Step 9: Copia y memoria**: `futbol-base-copia ejecutar` (la base de v2 crece: aceptada); ficha de memoria al día.
