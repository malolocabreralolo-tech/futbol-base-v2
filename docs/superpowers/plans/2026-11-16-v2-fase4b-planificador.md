# Fase 4B de v2 (el planificador del bot): plan de implementación

> **Para quien lo ejecute:** SUB-SKILL OBLIGATORIA: superpowers:subagent-driven-development. Este plan tiene una puerta: la tarea 3 solo se hace si la tarea 2 demuestra, con las simulaciones que ya existen, una frescura igual o mejor. Si no, se para y se deja escrito.

**Objetivo:** sustituir el reparto de lecturas del bot (unas 1.100 líneas de turnos, rotaciones y cuotas calculadas a partir del número de pasada) por la regla que pide el diseño: se guarda cuándo se leyó completo cada grupo por última vez y se lee primero el que lleva más tiempo, con preferencia para los grupos del dueño. **Solo entra si la frescura simulada es igual o mejor.**

**Arquitectura:** el orden de una pasada lo decide una función pura nueva, `scripts/planificador.py`, a partir de un estado pequeño que pasa de una pasada a la siguiente sin hacer commits (la caché de GitHub Actions, con `data-health.json` de respaldo). Todo lo demás del bot no cambia: cómo lee, el freno de la federación, el plazo de la pasada, las actas, el veredicto de pasada sana, el reloj.

**Tecnología:** Python 3.11, SQLite, GitHub Actions (`actions/cache`).

**Diseño:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` §7.8, último punto y §6. **Mapa:** `docs/superpowers/plans/2026-11-16-v2-fase4-mapa.md` §8 (qué partes forman hoy el planificador, con `fichero:línea`, qué estado pasa de una pasada a otra y qué mide cada simulación). Decisiones vigentes del bot: `docs/decisiones.md`, «El bot y la federación».

## Restricciones globales

- Las del plan de la fase 4 (`docs/superpowers/plans/2026-11-16-v2-fase4-mantenimiento.md`, «Restricciones globales»), todas.
- No se toca: `scripts/fiflp_carga.py` (el freno), `scripts/fiflp_render.py`, `scripts/reloj_pasadas.py`, `scripts/pasada_sana.py`, el plazo de la pasada (`DEADLINE_SECONDS`, `RESERVE_SECONDS`), ni la regla de que cada grupo se lee completo antes del siguiente.
- El bot no pide más páginas por pasada ni por día que hoy (el diseño: «v2 no debe pedir más que v1»).
- Los umbrales de las simulaciones no se aflojan: `scripts/tests/test_bot_pasada_corta.py` (prioritarios leídos cada 6 h y justo tras su partido; completos en 1 día o menos; el peor grupo, 8 días o menos; mediana 4,5 o menos; 70 % en 5 o menos; 330 páginas útiles al día o más) y `test_bot_rotacion.py` valen igual para el planificador nuevo.
- Nada de esto se publica en viernes tarde, sábado ni domingo.

## Foco de la revisión

1. El estado no llega (primera pasada, caché caducada o vacía): la pasada funciona con el respaldo y no relee siempre los mismos grupos (T2: simulación con el estado borrado cada N pasadas).
2. Una pasada seca (la federación frena desde la primera página) no marca nada como leído (T2).
3. Un grupo que falla siempre no bloquea la cola: no vuelve a ser el primero en cada pasada (T2).
4. Dos pasadas solapadas o repetidas (una relanzada) no corrompen el estado (T3: escritura atómica, y el estado de la que acaba la última manda).
5. Activación de grupos nuevos a mitad de temporada: un grupo sin estado entra el primero, una vez (T2).

---

### Task 1: Medir el planificador de hoy

**Ficheros:** crear `scripts/tests/frescura_planificador.py` (un guion, no una prueba: no se llama `test_*.py`) y `docs/planificador-medidas.md`. No cambia código del bot ni pruebas.

**Qué hace:** ejecuta los escenarios que ya simulan `test_bot_pasada_corta.py` (`simulate`, `complete_gaps`; fixtures `week`, `three_weeks`, `clock_week`, `perfect_clock_week`) y `test_bot_rotacion.py`, importándolos, y saca de cada uno las mismas magnitudes que esas pruebas comparan con sus umbrales, pero como números: para los grupos prioritarios, la edad máxima y la espera tras su partido; para los abiertos, días hasta estar completos (máximo, mediana, percentil 70); páginas útiles al día; pasadas que esperan un segundo freno; actas de los prioritarios leídas dentro de la ventana. Y dos escenarios más, con la misma maquinaria: (a) una de cada cinco pasadas, seca; (b) el estado que pasa entre pasadas, borrado cada 12 pasadas.

**Interfaz que produce:**
```python
# scripts/tests/frescura_planificador.py
def medir(planificar=None, semilla=7) -> dict:
    """{escenario: {magnitud: número}}. `planificar`: la función que ordena los grupos de una pasada
    (None = la de hoy, update_fiflp.plan_groups); se instala con monkeypatch mientras dura la medida."""
# CLI: python3 scripts/tests/frescura_planificador.py [--json]   → la tabla
```
- [ ] **Paso 1:** escribirlo; comprobar que con el planificador de hoy cada magnitud cumple el umbral de su prueba (si alguna no cuadra con lo que la prueba afirma, es un hallazgo: decirlo).
- [ ] **Paso 2:** `docs/planificador-medidas.md`: la tabla de hoy (la línea base), con tres semillas, y cuánto varía entre semillas.
- [ ] **Paso 3:** suites en verde; commit.

### Task 2: El planificador nuevo, medido contra el de hoy (sin enchufarlo)

**Ficheros:** crear `scripts/planificador.py`, `scripts/tests/test_planificador.py`; ampliar `docs/planificador-medidas.md`. `scripts/update_fiflp.py` NO cambia en esta tarea.

**Interfaz que produce:**
```python
# scripts/planificador.py — puro: sin base, sin red, sin reloj propio
@dataclass(frozen=True)
class Grupo:
    codigo: str
    nivel: int            # 1 prebenjamín/benjamín del dueño… como update_fiflp._level
    prioritario: bool     # un equipo del dueño juega en él (update_fiflp.is_priority / pinned_groups)
    caliente: bool        # prioritario con un partido recién jugado sin resultado o sin acta (hot_reason)
    cerrado: bool         # todo jugado y la última jornada, vieja (is_closed)
    actas_pendientes: bool

def planificar(grupos: list[Grupo], estado: dict, ahora: datetime, *, max_prioritario=timedelta(hours=6)) -> list[str]:
    """Los códigos en el orden en que la pasada debe leerlos."""

def apuntar(estado: dict, codigo: str, ahora: datetime, *, completa: bool) -> dict:
    """El estado tras leer `codigo`: `{"completa": ISO, "intento": ISO}` por grupo. Una lectura que no
    llegó a completarse solo mueve `intento`."""
```
**La regla (lo único que se decide aquí; cualquier añadido tiene que ganarse su sitio con una medida):**
1. Los calientes, primero.
2. Los prioritarios cuya última lectura completa tiene más de `max_prioritario`.
3. Los demás abiertos, por la lectura completa más antigua (el que nunca se ha leído, antes que todos); a igualdad, por el intento más antiguo y luego por código.
4. Los cerrados sin actas pendientes, al final, por la misma antigüedad.

El adaptador que convierte lo que hoy recibe `plan_groups` (la conexión, los grupos, `checks` de `data-health.json`, el número de pasada) en `Grupo` y `estado` vive, para medir, en `frescura_planificador.py`; el estado de la simulación se guarda entre pasadas en memoria.

- [ ] **Paso 1 (pruebas, en rojo)** en `test_planificador.py`: una por cada línea de la regla; `un grupo sin estado va el primero y solo una vez`; `una lectura incompleta no cuenta como completa`; `un grupo que falla siempre no se queda el primero` (tras `apuntar(..., completa=False)` baja por su `intento`); `el orden es determinista`; `no pierde ni repite grupos`.
- [ ] **Paso 2:** implementar. Medir con `medir(planificar=…)` las tres semillas y los escenarios (a) y (b). Añadir al documento la tabla comparada, magnitud a magnitud, y el veredicto: **igual o mejor en todas** / **peor en X**. Si es peor en alguna, probar como mucho dos añadidos justificados (por ejemplo, una cuota mínima por categoría si alevín se queda atrás) y volver a medir; cada añadido, con la medida que lo justifica. No más.
- [ ] **Paso 3:** recuento honesto de líneas: cuántas de `update_fiflp.py` sustituiría (`plan_groups` y las funciones de rotación que solo usa él) frente a las de `planificador.py` más el adaptador.
- [ ] **Paso 4:** suites en verde; commit. Informe con el veredicto en la primera línea.

### PUERTA (quien dirige)

Con el informe de la tarea 2: si la frescura es igual o mejor en todas las magnitudes y escenarios, y el recuento de líneas baja de verdad, sigue la tarea 3. Si no, el plan termina aquí: se deja `scripts/planificador.py` fuera (se retira el commit o se archiva), `docs/planificador-medidas.md` se queda como constancia, y el planificador de hoy sigue. Se anota en `docs/decisiones.md`.

### Task 3: Enchufarlo (solo si pasa la puerta)

**Ficheros:** `scripts/update_fiflp.py` (`plan_groups` pasa a ser el adaptador sobre `planificador.planificar`; se quitan las funciones de rotación que queden sin uso), `scripts/estado_lecturas.py` (leer y escribir `estado-lecturas.json` con `escritura.escribir_atomico`; respaldo: los `checkedAt` de `data-health.json`), `.github/workflows/update.yml` (restaurar y guardar el estado con `actions/cache`, clave con el número de ejecución y `restore-keys` con el prefijo), `.gitignore` (`estado-lecturas.json`), las pruebas `test_bot_*.py` (las que prueban las tripas del reparto antiguo se sustituyen por las de la regla nueva; las simulaciones y sus umbrales se quedan), `scripts/tests/test_workflows.py`, `docs/federacion.md`, `docs/decisiones.md`.

- El estado no se sube al repositorio: no añade commits.
- [ ] Pasos: pruebas primero; simulaciones con sus umbrales de siempre en verde; `frescura_planificador.py` con el bot ya enchufado da la misma tabla que la tarea 2; suites en verde; commit.

### Publicar (quien dirige)

Revisión final independiente; un día entre semana, entre dos pasadas; mirar enteras las tres primeras pasadas (que el estado se restaura y se guarda, que el orden es el esperado, páginas leídas) y, a las 24 h, la frescura real (edad de `checkedAt` por grupo en `data-health.json`) frente a la del día anterior. Si empeora: `git revert`.
