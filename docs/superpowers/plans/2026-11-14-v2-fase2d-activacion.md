# v2, fase 2D: fases y grupos nuevos, detectados y activados solos

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que una competición, una fase o un grupo nuevo de las categorías seguidas se cargue solo cuando encaja en los convenios conocidos y pasa las verificaciones; y que, si no encaja, la base no se toque y «Datos y fuentes» lo diga (objetivo O3 del diseño).

**Architecture:** el bot ya detecta competiciones nuevas una vez al día (`update_fiflp.check_competitions` → `newCompetitions` en `data-health.json`). Se añade la detección de grupos nuevos dentro de competiciones conocidas, sin pedir páginas de más (el desplegable de grupos de las páginas de calendario que el bot ya carga). Un script local y puro en lo posible, `scripts/activar_auto.py`, hace con un raw ya descargado lo que hoy se hace a mano (manifiesto de solo lo nuevo → verificar → aplicar → sonda de fases) y un workflow nuevo, `activar.yml`, lo encadena en Actions (catálogo → descarga de lo nuevo → activar → pruebas → commit), lanzado por `update.yml` cuando hay algo pendiente.

**Tech Stack:** Python 3 (pytest), GitHub Actions, módulos ES (`node --test`).

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O3, 7.4, 7.5). Mapa del código: `docs/superpowers/plans/2026-11-13-v2-fase2-mapa.md`, bloque A entero (A1 el camino manual, A2 lo que detecta el bot, A4 claves de fase) y trampas 1 a 5, 16 y 17. Procedimiento manual vigente: `docs/temporada-nueva.md` y, tal como se hizo el 13/11 para tres competiciones, el plan `2026-11-13-v2-fase2a-competiciones.md`.

## Global Constraints

- Nada contra fiflp.com ni GitHub desde local: la federación solo responde desde Actions. Todo lo que hable con ella se prueba con páginas simuladas (las de `scripts/tests/`).
- No se toca v1 ni se nombra su repositorio. Todas las órdenes `gh` de workflows y documentos llevan `-R malolocabreralolo-tech/futbol-base-v2`.
- **Si algo no encaja, no se toca la base.** La activación es todo o nada por ejecución: o entran todos los grupos nuevos verificados de una competición, o ninguno de esa competición. Nunca se inventa una clasificación a cero para un grupo sin tabla que no sea una eliminatoria (y para una eliminatoria, no se escribe tabla).
- Un solo escritor de la base a la vez: `activar.yml` va en el grupo de concurrencia `update-data`, como `update.yml`.
- El bot no pide más páginas por pasada que hoy. La descarga de una fase nueva (una página por grupo y jornada) va en `activar.yml`, no en la pasada.
- Sin avisos externos (ni issues, ni correo propio, ni Telegram): lo pendiente y lo fallido se ve en `data-health.json` y en «Datos y fuentes».
- Sin bucles: una activación que falla no se reintenta en cada pasada; como mucho una vez cada 6 h por el mismo conjunto de pendientes.
- `data-health.json` no se reescribe en cada pasada sin cambio con significado (`source_health.VOLATILE`).
- Idioma: español; campos de `data-health.json` en inglés como los que hay. Estilo del código vecino.
- Suites completas en verde al acabar cada tarea: `python3 -m pytest scripts/tests -q` y `node --test scripts/tests/test_*.mjs`.
- Rama `fase2d`, en `/home/manolo/claude/futbol-base-v2-fase2d`. Sin `git push`, sin tocar `main`, sin lanzar workflows.
- Commits en español terminados con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```

## Review Focus

1. Competición nueva que encaja (una liga prebenjamín insular, una «SEGUNDA FASE A» de benjamín): se activa sola, con sus pruebas en verde, y deja de salir en `newCompetitions`.
2. Competición nueva sin convenio de código (`comp_meta` lanza `ValueError`): nada cambia en la base ni en los `data-*.js`; sigue en `newCompetitions`; `activation` dice por qué; el job acaba en rojo.
3. Dos competiciones pendientes, una encaja y otra no: se activa la que encaja y la otra se queda pendiente (una no bloquea a la otra).
4. Grupo nuevo dentro de una competición ya activada (un «Grupo 25» añadido): se detecta sin páginas de más, se activa solo ese grupo y los 24 existentes no se tocan.
5. La descarga se corta a medias (freno, plazo): no se activa nada incompleto; lo descargado se conserva para el siguiente intento y el siguiente intento llega (encadenado, con tope).

---

### Task 1: el bot detecta grupos nuevos de competiciones conocidas

**Files:**
- Modify: `scripts/update_fiflp.py` (`scrape_group`, el final de `run_passes`), `scripts/source_health.py`
- Modify: `src/screen-fuentes.js` (la nota de lo pendiente), `scripts/tests/test_rediseno_fuentes.mjs`
- Test: `scripts/tests/test_grupos_nuevos.py` (nuevo)
- Docs: `docs/federacion.md` (apartado «Competiciones y grupos nuevos»)

**Interfaces (produce):**
- En cada calendario que el bot ya carga (`…NFG_CmpJornada?…&CodCompeticion=C&CodGrupo=G`), lee también `select[name="grupo"]` (ids y nombres) sin pedir nada. No se sabe si esa página lo trae (mapa A2: «no verificado»): si no lo trae, no se detecta nada y `run` (volátil) lleva `"groupSelects": {"seen": n, "of": m}` para saberlo tras la primera pasada real.
- `update_fiflp.new_groups(seen: dict[str, dict[str, str]], known: set[tuple[str, str]], previous=(), today=None) -> list[dict]`: `seen` = `{CodCompeticion: {CodGrupo: nombre}}`; `known` = los (`CodCompeticion`, `CodGrupo`) de las URL de `groups` de la temporada. Devuelve `[{"competition": C, "competitionName": …, "id": G, "name": …, "firstSeen": "AAAA-MM-DD"}]`, ordenado, conservando `firstSeen` de `previous`.
- `source_health.set_new_groups(items)` / `new_groups()`: como `set_new_competitions`; campo `newGroups` del informe, con significado (no volátil), arrastrado entre pasadas mientras la pasada no lea el desplegable de esa competición (una competición cuyo desplegable se leyó y ya no trae el grupo lo quita).
- «Datos y fuentes»: junto a la nota de competiciones, otra del mismo estilo: «La federación ha publicado N grupo(s) nuevo(s) en competiciones que esta web ya sigue: <competición>, <grupo>; …». Con `activation.failed` (tarea 3), una línea más: «No se han podido cargar solos: <motivo>.»

- [ ] Pruebas: `new_groups` (nuevo, conocido, `firstSeen` conservado, orden); el bot con federación simulada cuyo calendario trae un grupo de más → `newGroups` con ese grupo y cero páginas de más (mismo recuento de `F.pages` que sin el cambio); calendario sin desplegable de grupos → `newGroups` no cambia y `groupSelects.seen == 0`; el grupo desaparece del desplegable → se quita; pantalla con y sin `newGroups`, mal formado sin romper.
- [ ] Implementar. Documento. Suites. Commit.

### Task 2: `activar_auto.py`, la activación sin manos (local, con un raw ya descargado)

**Files:**
- Create: `scripts/activar_auto.py`, `scripts/sonda_fases.mjs`, `scripts/tests/test_activar_auto.py`
- Modify: `scripts/fiflp_manifest.py` (solo lo nuevo), `scripts/activate_season.py` (`fiflp_evidence`: la tabla de una eliminatoria)
- Docs: `docs/temporada-nueva.md` (apartado «Activación automática» y cómo hacerlo a mano si falla)

**Interfaces (produce):**
```python
# scripts/activar_auto.py
def pendientes(health: dict) -> dict[str, list[str] | None]:
    """{CodCompeticion: None (competición entera) | [CodGrupo, …] (solo esos grupos)} de newCompetitions y newGroups."""
def activar(raw_path, db_path, comps: dict, root=ROOT, log=print) -> dict:
    """Por competición, en una transacción propia: manifiesto de SOLO los grupos que la temporada no tiene
    → verify_sources → add_groups. Devuelve {"activated": [{competition, codes}], "failed": [{competition, reason}]}.
    Una competición que falla no toca la base ni impide las demás."""
# CLI: python3 scripts/activar_auto.py [--raw scripts/fiflp_islas_22_raw.json] [--dry-run]
#   lee data-health.json, activa lo que encaja, regenera (generate_js) si activó algo, escribe el manifiesto
#   de lo activado en docs/temporadas/<temporada>-auto-<AAAAMMDD>.json, pasa la sonda de fases y deja en
#   data-health.json `activation`: {"at": ISO, "activated": […], "failed": [{competition, name, reason}], "tried": [ids]}.
#   Sale con 0 si no falló ninguna; con 1 si alguna falló (lo activado se queda).
```
- `fiflp_manifest.build(..., only_new: set[(comp, grupo)] | None)` o equivalente: genera solo los grupos pedidos; el código (`prefijo + número del grupo`) no puede chocar con uno existente de la temporada (si choca, esa competición falla con el motivo).
- `activate_season.fiflp_evidence`: un grupo sin clasificación en el raw cuya competición es una eliminatoria o copa a partido único (`COPA …`, eliminatorias) no recibe tabla inventada (hoy se inventa a cero y hubo que borrarla a mano en `CGC1`); para una liga sin tabla todavía (calendario publicado, nada jugado) se mantiene la tabla a cero de hoy.
- `scripts/sonda_fases.mjs`: la sonda de `docs/temporada-nueva.md` como script: carga `data-benjamin.js`, `data-prebenjamin.js`, `data-alevin.js` y sale con 1 nombrando cada grupo cuya `competitionKey` empieza por `otra-`. Si falla tras activar, `activar_auto` lo apunta en `activation.failed` con el motivo «fase que la web no reconoce: …» **sin deshacer la activación** (los datos son buenos; falta la regla de `PHASE_TABLE`, que es código): el job queda en rojo para que se añada la regla.
- Para saber si una descarga está completa, la descarga deja escrito qué grupos lista la federación en cada competición (el desplegable que lee `fetch_fiflp_2425.scrape_competition`): un fichero al lado del raw, `scripts/fiflp_islas_<tanda>_grupos.json` (`{CodCompeticion: {CodGrupo: nombre}}`), que `activar` compara con los grupos del raw. Sin ese fichero para una competición, la descarga se da por incompleta.
- Motivos de fallo, textos exactos: `"sin convenio de código: <nombre>"`, `"la descarga no está completa: faltan N grupos"`, `"verificación: <mensaje de verify_sources>"`, `"código repetido: <código>"`, `"fase que la web no reconoce: <fase>"`.

- [ ] Pruebas con una base pequeña y raws de prueba (mira `scripts/tests/test_alevin_activacion.py` y `test_season_preparation.py` para montar): Review Focus 1, 2, 3 y 4; raw incompleto (falta un grupo de la competición respecto al catálogo o al desplegable) → falla esa competición sin tocar nada; copa a partido único sin tabla → activada sin filas en `standings`; `--dry-run` no escribe nada; `activation` bien formado; segunda ejecución sin pendientes → no hace nada y sale con 0.
- [ ] Implementar. Documento. Suites. Commit.

### Task 3: `activar.yml` y el lanzamiento desde el bot

**Files:**
- Create: `.github/workflows/activar.yml`
- Modify: `.github/workflows/update.yml` (un paso final que lo lanza), `scripts/tests/test_workflows.py`
- Modify: `scripts/source_health.py` (orden `pendiente` para el paso), `scripts/fetch_fiflp_islas.py` solo si hace falta para descargar por lista de competiciones y grupos
- Docs: `docs/federacion.md`, `docs/temporada-nueva.md`

**`activar.yml`** (`workflow_dispatch` con entrada `intento`, por defecto 1; `permissions: contents: write, actions: write`; `concurrency: update-data` sin cancelar; imagen y versiones como `update.yml`; `checkout ref: main`):
1. Catálogo: `python3 scripts/discover_fiflp_comps.py` solo de la temporada en curso (`DISCOVER_SEASONS`).
2. Descarga de lo pendiente: `python3 scripts/fetch_fiflp_islas.py` con `ISLAS_SEASON=<código de temporada>` y `SCRAPE_IDS=<competiciones pendientes>` (las de `python3 scripts/activar_auto.py --pendientes`, que imprime los ids). Reanuda lo ya descargado (el raw se versiona).
3. `python3 scripts/activar_auto.py` (paso con `id: activar`, `continue-on-error: true`).
4. Pruebas Python y Node, como en `update.yml`, solo si hubo cambios en la base.
5. Commit y push (con los mismos reintentos y rebase que `update.yml`): catálogo, raw, base, `data-*.js`, `index.html`, `sw.js`, `docs/temporadas/*.json`, `data-health.json`. Si las pruebas fallan: no se sube nada de datos; se sube solo `data-health.json` con `activation.failed` = «las pruebas fallaron tras activar» (partiendo del publicado), y el job en rojo.
6. Si la descarga quedó incompleta (motivo «la descarga no está completa») y `intento < 4`: se relanza a sí mismo con `intento + 1` (`gh workflow run activar.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main -f intento=N`). Con `intento == 4` no se relanza.
7. Rojo final si `activation.failed` no está vacío.

**En `update.yml`**, paso «Lanzar la activación si hay algo nuevo», después de «Commit y push si hay cambios» y antes de «Pasada en rojo», `if: success()`, permiso `actions: write`: ejecuta `python3 scripts/source_health.py pendiente` (sale con 0 e imprime los ids si hay `newCompetitions` o `newGroups` que no estén en `activation.tried` de las últimas 6 h; con 1 si no hay nada que lanzar) y, si hay, `gh workflow run activar.yml -R malolocabreralolo-tech/futbol-base-v2 --ref main`. Un fallo al lanzar no pone la pasada en rojo (`continue-on-error: true`).

- [ ] Pruebas del workflow en `test_workflows.py`, con el estilo de las que hay: YAML válido, runner fijado, concurrencia `update-data`, permisos, orden de pasos, que el commit de datos exige pruebas en verde, que el relanzamiento tiene tope 4 y pasa `intento`, que `update.yml` lanza con `-R` y `--ref main` y no falla la pasada si no puede; `source_health.py pendiente` (con pendientes nuevos → 0; ya intentados hace menos de 6 h → 1; intentados hace más → 0; sin nada → 1). Donde el guion de un paso se pueda ejecutar en un repositorio temporal sin red (como hace la prueba del diagnóstico de la fase 2B), ejecútalo.
- [ ] Implementar. Documentos. Suites. Commit.
