# v2, fase 2B: pasada sana

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el bot de v2 no pueda quedarse ciego en verde (objetivo O4 del diseño): una pasada que no lee de verdad acaba en rojo, lo dice en `data-health.json` y «Datos y fuentes» lo enseña.

**Architecture:** el bot calcula un veredicto de cada pasada con una función pura (`scripts/pasada_sana.py`) y lo guarda en `data-health.json` como `runHealth`. Los datos de los grupos que sí se leyeron bien se publican igual; después del commit, un paso del workflow lee `runHealth` y pone el job en rojo. Cuando fallan las pruebas, el workflow publica también el diagnóstico (hoy se pierde).

**Tech Stack:** Python 3 (pytest), GitHub Actions (YAML), módulos ES sin empaquetar (`node --test`).

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O4, 7.5, 7.8). Mapa del código: `docs/superpowers/plans/2026-11-13-v2-fase2-mapa.md`, bloques B6 y B7 y trampas 7, 8 y 9 (los números de línea se han movido unas pocas líneas desde entonces: buscar por nombre de función).

## Global Constraints

- Idioma del proyecto: español (código, comentarios, commits, documentos). Los campos de `data-health.json` siguen en inglés como los que ya hay (`checkedAt`, `newCompetitions`, `run`).
- Nada contra fiflp.com ni contra GitHub desde local: solo pruebas con federaciones simuladas (las de `scripts/tests/test_bot_*.py`, `test_fiflp_carga.py`, `test_fiflp_actas_federacion.py`).
- No se toca nada de v1 ni se nombra su repositorio en ninguna orden.
- No se cambia qué se pide a la federación ni cuánto: esta fase solo cambia cómo se juzga lo leído.
- El freno de la federación (grupos `unserved`) y la rotación (`deferred`, los que descansan) son funcionamiento normal: una pasada con freno que leyó bien algunos grupos es **verde**.
- Los datos de los grupos leídos bien se publican aunque la pasada acabe en rojo. El rojo no borra ni retiene datos buenos.
- `data-health.json` no debe reescribirse en cada pasada sana (hoy: solo con cambio con significado o cada 24 h; `source_health.VOLATILE`). Una pasada sana detrás de otra sana no genera commit por `runHealth`.
- Suites completas en verde al acabar cada tarea: `python3 -m pytest scripts/tests -q` y `node --test scripts/tests/test_*.mjs`.
- Se trabaja en la rama `fase2b`, en `/home/manolo/claude/futbol-base-v2-fase2b`. No se hace `git push` ni se toca `main`: lo fusiona y publica el controlador.
- Commits pequeños, mensaje en español, terminados con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```

## Review Focus

1. Pasada con freno: 6 grupos `ok`, 20 `unserved`, 0 errores → verde, `runHealth.ok` cierto.
2. Pasada pequeña (`FIFLP_CATS=prebenjamin`): el veredicto cuenta solo los grupos de esa pasada; los de otras categorías (arrastrados con `carry`) no cuentan ni como fallo ni como leídos.
3. Ejecución sin federación (`FIFLP_UPDATE` sin poner, en local): `runHealth` se queda como estaba en el informe anterior.
4. Dos pasadas en rojo seguidas por el mismo motivo: `since` no cambia; la tercera, sana, vuelve a `{"ok": true}`.
5. Grupo recién activado (sin jornadas en la base, primera pasada completa) y jornada que la federación ha vaciado porque movió sus partidos sin jugar a otra jornada leída en la misma pasada: ninguno de los dos es «jornada vacía».

---

### Task 1: el veredicto de la pasada, en el bot y en `data-health.json`

**Files:**
- Create: `scripts/pasada_sana.py`
- Modify: `scripts/update_fiflp.py` (`update_group`, `run_passes` → función interna `read` y el final, `update_groups`)
- Modify: `scripts/source_health.py`
- Modify: `scripts/fiflp_carga.py` (`_refused`)
- Modify: `scripts/fetch_futbolaspalmas.py` (`main`, solo si hace falta para el caso «la ejecución se interrumpió»)
- Test: `scripts/tests/test_pasada_sana.py` (nuevo), y las pruebas existentes que haya que ajustar en `scripts/tests/test_fiflp_carga.py` y `scripts/tests/test_source_health.py`
- Docs: `docs/federacion.md` (apartado nuevo «Pasada sana», 10-20 líneas: las cuatro reglas y qué pasa en rojo)

**Interfaces (produce):**

```python
# scripts/pasada_sana.py — puro, sin base ni red
def veredicto(estados: dict[str, str], previstos: int, vacias: list[str] = (), interrumpida: str | None = None) -> list[str]:
    """Motivos por los que la pasada no es sana (lista vacía: sana).
    estados: {código de grupo: 'ok' | 'error' | 'rejected'} de los grupos que la pasada llegó a leer.
    previstos: grupos que la pasada intentó (leídos + sin servir por el freno + aplazados por plazo)."""
```

Reglas (cada una añade un motivo, en este orden; los códigos, ordenados, como mucho 12 y «y N más»):
1. `interrumpida` → `f"la federación no se pudo consultar: {interrumpida}"` (recortado a 200 caracteres).
2. `vacias` → `"jornada leída vacía que la base tiene con partidos: PG2, FF7"`.
3. `previstos > 0` y ningún `'ok'` en `estados` → `f"la federación no sirvió ningún grupo (de {previstos} previstos)"`.
4. si no se cumplió la 3: fallidos = estados `'error'` o `'rejected'`; si `3 * fallidos > len(estados)` → `f"fallaron {fallidos} de {len(estados)} grupos leídos: …códigos…"`.

Con `previstos == 0` y `estados` vacío (nada que leer): sana.

```python
# scripts/update_fiflp.py
class JornadaVacia(RuntimeError): ...
# update_group la lanza ANTES de escribir nada del grupo.
# run_passes devuelve {"estados": {código: estado}, "previstos": int, "vacias": [códigos]}
#   (hoy devuelve None; las pruebas que la llaman no miran su valor).
# update_groups calcula el veredicto en los dos caminos (pasada normal y excepción) y llama a
#   source_health.set_run_health(motivos).

# scripts/source_health.py
def set_run_health(reasons, now=None): ...
#   sana:   _report["runHealth"] = {"ok": True}
#   en rojo: {"ok": False, "reasons": [...], "since": <ISO>}; `since` es el del informe anterior si
#            ya estaba en rojo (misma temporada), si no, la hora de ahora.
#   Si nadie la llama en una ejecución (sin federación), begin() arrastra el runHealth anterior tal cual.
#   finish(failed=True): si runHealth no está ya en rojo, lo pone con el motivo
#            "la pasada se interrumpió antes de terminar".
#   runHealth NO es VOLATILE: un cambio suyo reescribe el informe.

# Línea de órdenes (python3 scripts/source_health.py <orden>), sobre data-health.json del disco:
#   veredicto           → sale con 1 e imprime los motivos si runHealth.ok es false; con 0 si es true o no existe.
#   marcar "<motivo>"   → pone runHealth en rojo con ese motivo (conserva `since` si ya estaba en rojo;
#                         si ya estaba en rojo con otros motivos, añade este sin repetirlo) y escribe el fichero.
#                         No toca nada más del informe.
```

**Jornada vacía (regla exacta).** En `update_group`, antes de la primera escritura: para cada etiqueta de `raw_rounds` cuya lista cruda (lo que dio `F.parse_matches`, antes de quitar descansos) está vacía y para la que `matches` tiene al menos un partido de ese grupo y esa `jornada`: es jornada vacía, salvo que todos los partidos guardados de esa jornada estén sin resultado y el cruce (local, visitante) de cada uno aparezca en otra jornada leída en esta misma llamada (la federación los movió: lo fija `test_an_unplayed_match_moved_by_the_federation_changes_round`). Con alguna jornada vacía: `raise JornadaVacia("la jornada 5 se leyó vacía y la base tiene 6 partidos")`, sin escribir nada. En `read`, `JornadaVacia` deshace (`conn.rollback()`), deja el grupo en `"error"` con ese mensaje y apunta su código en `vacias`. Un grupo sin jornadas en la base no puede dar jornada vacía.

**403 y demás 4xx.** `fiflp_carga._refused`: página no cargada si `status >= 400` (hoy `>= 500` o `429`). `BRAKE_STATUSES` no cambia: un 403 no es señal de freno; es «no carga», con sus reintentos, y tres seguidas bloquean (`BLOCKED_AFTER`), como hoy un 500.

- [ ] **Step 1: pruebas de `veredicto` (fallan: el módulo no existe).** En `scripts/tests/test_pasada_sana.py`, una prueba por caso, con estos valores:
  - `veredicto({"A": "ok", "B": "ok", "C": "error"}, 3) == []` (1 de 3 no supera el tercio);
  - `veredicto({"A": "ok", "B": "error", "C": "rejected", "D": "ok"}, 4)` → un motivo que empieza por `"fallaron 2 de 4 grupos leídos"` y nombra `B` y `C`;
  - `veredicto({}, 26)` → `["la federación no sirvió ningún grupo (de 26 previstos)"]`;
  - `veredicto({"A": "error"}, 5)` → solo el motivo de «no sirvió ningún grupo» (no se duplica con el del tercio);
  - `veredicto({}, 0) == []`;
  - `veredicto({"A": "ok"}, 21) == []` (freno: 1 leído, 20 sin servir);
  - `veredicto({"A": "ok", "B": "error"}, 2, vacias=["B"])` → primer motivo de jornada vacía con `B`, y además el del tercio;
  - `veredicto({"A": "error"}, 1, interrumpida="x" * 500)` → el primer motivo empieza por `"la federación no se pudo consultar: "` y mide como mucho 240 caracteres;
  - 15 grupos en error de 15: la lista de códigos lleva 12 y `"y 3 más"`.
- [ ] **Step 2: `scripts/pasada_sana.py`** hasta que pasen.
- [ ] **Step 3: pruebas de `source_health`** (en `test_source_health.py`, con su mismo montaje de informe en directorio temporal): `set_run_health([])` deja `{"ok": True}` y, con el anterior también sano y reciente, `finish()` **no** reescribe el fichero; `set_run_health(["m"])` escribe `ok: false`, `reasons == ["m"]` y `since`; una segunda ejecución en rojo conserva `since`; una ejecución sin llamar a `set_run_health` arrastra el `runHealth` anterior; `finish(failed=True)` deja `runHealth.ok` falso con «la pasada se interrumpió antes de terminar»; con otra temporada en el informe anterior no se arrastra nada. Órdenes: `veredicto` sale con 1/0 según el fichero (también 0 sin `runHealth`); `marcar "x"` sobre un informe sano lo pone en rojo sin tocar `groups` ni `checkedAt`, y sobre uno ya en rojo añade el motivo y conserva `since`.
- [ ] **Step 4: implementar en `scripts/source_health.py`** (con `if __name__ == "__main__":`), hasta verde.
- [ ] **Step 5: pruebas de jornada vacía y de la pasada**, con las federaciones simuladas que ya usan `test_update_fiflp.py` y `test_bot_*.py` (reutilizar sus ayudantes, no inventar otros):
  - `update_group` con una jornada que la base tiene con 6 partidos y que llega `[]` → `JornadaVacia`, y los recuentos de `matches` y `standings` del grupo no cambian;
  - la excepción de los partidos movidos (jornada vacía pero sus cruces sin jugar llegan en otra jornada de la misma llamada) → no lanza y los mueve como hoy;
  - grupo sin jornadas en la base → no lanza;
  - `run_passes` devuelve `estados`, `previstos` y `vacias` coherentes en: pasada con freno (algunos `ok`, resto sin servir → `previstos` = todos los intentados, veredicto vacío), pasada donde la federación sirve un 403 a todo (ningún `ok` → motivo de «no sirvió ningún grupo»), pasada con más de un tercio de grupos en error;
  - `update_groups` llama a `source_health.set_run_health` con los motivos en la pasada normal y en el camino de excepción (navegador que no abre: todos los pendientes en error y el motivo «la federación no se pudo consultar…»);
  - con `FIFLP_CATS`, los grupos arrastrados de otras categorías no entran en `estados` ni en `previstos`.
- [ ] **Step 6: implementar en `scripts/update_fiflp.py`** y `_refused` en `scripts/fiflp_carga.py`; ajustar las pruebas de `test_fiflp_carga.py` que fijan qué es «no cargada» y añadir la del 403 (no cargada, no cuenta como señal de freno, tres seguidas bloquean).
- [ ] **Step 7: `docs/federacion.md`**, apartado «Pasada sana».
- [ ] **Step 8: suites completas** (`python3 -m pytest scripts/tests -q`; `node --test scripts/tests/test_*.mjs`) en verde. Commit(s).

---

### Task 2: el workflow publica el diagnóstico y pone el rojo; «Datos y fuentes» lo enseña

**Files:**
- Modify: `.github/workflows/update.yml`
- Modify: `scripts/tests/test_workflows.py`
- Modify: `src/screen-fuentes.js`
- Test: `scripts/tests/test_rediseno_fuentes.mjs`
- Docs: `docs/federacion.md` (en el apartado de la tarea 1, qué hace el workflow)

**Interfaces (consume):** `python3 scripts/source_health.py veredicto` y `… marcar "<motivo>"` (tarea 1); `runHealth` en `data-health.json`.

**El workflow, pasos finales de `update.yml` en este orden** (los nombres son los que fijan las pruebas):
1. `scrape` (sin cambios).
2. «Tests Python (bloquean el commit si fallan)», `id: pytest`; «Tests Node (bloquean el commit si fallan)», `id: node` (mismas condiciones que hoy).
3. «Commit y push si hay cambios» (sin cambios).
4. «Publicar diagnóstico si la fuente o las pruebas fallan» (sustituye a «Publicar diagnóstico si la fuente falla»), `if: ${{ !cancelled() && (steps.scrape.outcome == 'failure' || steps.pytest.outcome == 'failure' || steps.node.outcome == 'failure') }}`:
   - si fallaron las pruebas (scrape con éxito): `git checkout HEAD -- data-health.json` y `python3 scripts/source_health.py marcar "las pruebas fallaron: los datos de esta pasada no se publicaron"` (el informe de esta pasada dice leído lo que no se publica: se parte del publicado);
   - si falló el scrape: el `data-health.json` que dejó `finish(failed=True)`, como hoy;
   - en los dos casos: `git add data-health.json`, commit «Estado de las fuentes …», push con los mismos reintentos que hoy, y `exit 1`. Nunca añade otro fichero.
5. «Pasada en rojo», `if: success()`: `python3 scripts/source_health.py veredicto`. Va después del commit: los datos buenos ya están publicados cuando el job se pone rojo.

- [ ] **Step 1: pruebas del workflow** en `test_workflows.py` (fallan): los ids `pytest` y `node`; el paso de diagnóstico con su nombre nuevo y las tres condiciones; que en la rama de las pruebas restaura `data-health.json` de `HEAD` antes de `marcar`; que solo hace `git add data-health.json`; que acaba en `exit 1`; que «Pasada en rojo» existe, corre `source_health.py veredicto`, lleva `if: success()` y va después de «Commit y push si hay cambios». Ajustar `test_two_passes_in_a_row_do_not_step_on_each_other` y cualquier otra que nombre el paso viejo.
- [ ] **Step 2: `update.yml`** hasta verde.
- [ ] **Step 3: prueba de la pantalla** en `test_rediseno_fuentes.mjs` (falla): con `health.runHealth = { ok: false, reasons: ['fallaron 9 de 20 grupos leídos: FF1, FF2', 'jornada leída vacía que la base tiene con partidos: PG2'], since: '2026-11-14T10:05:00+00:00' }` la pantalla lleva, justo debajo de «Estado de los datos», un aviso (`notice`) con el texto `La última pasada del bot no fue bien (desde el 14 de noviembre, 10:05): fallaron 9 de 20 grupos leídos: FF1, FF2; jornada leída vacía que la base tiene con partidos: PG2.` (fecha y hora de Canarias, con los ayudantes que ya usa la pantalla: `canaryDateTime`, `dayMonthLong`; «hoy» si es el día de `ctx.today`). Con `runHealth` ausente, `{ ok: true }` o mal formado (no objeto, `reasons` que no es lista, motivos que no son texto): sin aviso y sin romper. Sin `since` válido: el mismo texto sin el paréntesis.
- [ ] **Step 4: `runHealthNote(health, today)` en `src/screen-fuentes.js`** hasta verde. Sin clases CSS nuevas.
- [ ] **Step 5: `docs/federacion.md`**: en «Pasada sana», los pasos del workflow y qué ve el dueño.
- [ ] **Step 6: suites completas** en verde. Commit(s). No se ejecuta `scripts/publicar.py` (lo hace el controlador al fusionar).
