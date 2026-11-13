# v2 · Fase 0: copia en el PC y limpieza local — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una copia diaria, comprobada y con versiones, de la base y de los repositorios de fútbol base en el PC del dueño, y la copia local de v1 limpia.

**Architecture:** Un paquete Python pequeño (`pc/copia/copia/`), solo con la biblioteca estándar: un espejo de git por origen del que se saca la base, una verificación que decide si se acepta, y un almacén con versiones comprimidas, retención y volcados en texto. Lo lanza un temporizador de usuario de systemd desde una copia instalada, no desde el árbol de trabajo.

**Tech Stack:** Python 3.12 (stdlib: `sqlite3`, `lzma`, `hashlib`, `fcntl`, `subprocess`), git, pytest 9, bash, systemd de usuario.

**Spec:** `docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md` (O1, 7.3, 7.9). Hallazgos: `docs/revision-2026-11-13.md`.

## Global Constraints

- **v1 no se toca**: ningún `git push` a `malolocabreralolo-tech/futbol-base`, ningún cambio en sus ficheros remotos, en `~/.config/futbol-base-reloj/`, en `~/.local/bin/futbol-base-reloj` ni en `futbol-base-reloj.timer/.service`.
- **Esta fase no publica nada**: v2 no tiene remoto todavía; no se crea ningún repositorio en GitHub ni se empuja nada.
- Solo biblioteca estándar de Python 3.12. Nada de `pip install`.
- Las pruebas no usan red ni tocan `~/backups`: la raíz va por la variable `FB_COPIA_RAIZ` a un directorio temporal, y los «remotos» son repositorios git locales.
- Raíz real: `~/backups/futbol-base/`, con permisos `0o700`.
- Tablas que se vigilan: `matches`, `players`, `appearances`, `goals`, `standings`, `match_events`, `teams`, `groups`, `scorers`.
- Margen de mengua: 2 % (`0.02`).
- Retención de versiones: la más nueva de cada día durante 30 días, la más nueva de cada semana ISO durante 26 semanas, la más nueva de cada mes para siempre, y siempre la última.
- Volcados en texto: uno por semana ISO; se conservan los 12 más nuevos.
- Cuarentena: comprimida, sin repetir la misma base, las 10 más nuevas por origen.
- Compresión: `lzma` (`.xz`), preset 6.
- Toda escritura es atómica (fichero temporal en el mismo directorio y `os.replace`). Una copia mala nunca sustituye a `actual/`.
- La base de v1 está en modo WAL: se abre siempre con `file:<ruta>?mode=ro&immutable=1` y no se deja ningún `-wal` ni `-shm` al lado.
- Nunca el correo del dueño en ninguna petición ni cabecera.
- Español en código, comentarios, mensajes y commits. Los comentarios dicen el porqué en una frase, sin citar planes ni decisiones numeradas.
- Cada commit acaba con estas dos líneas:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013YEDWLhBHY2k5emLFbvcpv
  ```

## Review Focus

1. **GitHub no responde o se corta a medias** → la pasada acaba con error, `actual/` no cambia y no queda un espejo a medio clonar que la siguiente pasada tome por bueno. (Tarea 5, `test_remoto_caido`.)
2. **La escritura se interrumpe** (disco lleno, apagón) → no aparece ninguna versión truncada ni cambia `actual/`. (Tarea 3, `test_escritura_interrumpida_no_deja_version`.)
3. **El historial del remoto se reescribe o se vacía** → el espejo conserva lo que ya tenía. (Tarea 5, `test_reescritura_no_pierde_lo_anterior`.)
4. **Una base menguada a propósito llega día tras día** → va a cuarentena una sola vez, y con `--aceptar-mengua` se acepta. (Tarea 6, `test_misma_rechazada_no_se_repite` y `test_aceptar_mengua`.)
5. **Dos pasadas a la vez** (el temporizador y una a mano) → la segunda sale sin tocar nada. (Tarea 6, `test_cerrojo`.)

---

## Estructura de ficheros

```
pc/copia/
  README.md                      qué es, instalar, ver el estado, restaurar
  origenes.json                  de dónde se copia (v1 ahora; v2 en la fase 1)
  instalar.sh                    instala la copia revisada, el lanzador y el temporizador
  systemd/futbol-base-copia.service
  systemd/futbol-base-copia.timer
  copia/__init__.py
  copia/verificar.py             ¿es buena esta base?
  copia/almacen.py               versiones, actual, cuarentena, retención, restaurar, volcados
  copia/fuentes.py               espejo de git y extracción de ficheros
  copia/ejecutar.py              una pasada completa, el estado y el cerrojo
  copia/__main__.py              la orden
  tests/conftest.py              raíz temporal, base de prueba, remoto de prueba
  tests/test_verificar.py  test_almacen.py  test_retencion.py  test_fuentes.py
  tests/test_ejecutar.py  test_cli.py  test_instalar.py
```

Las pruebas se ejecutan con `cd pc/copia && python3 -m pytest tests -q`. No entran en `scripts/tests/`, que es la batería del bot.

---

### Task 1: Repositorio local de v2 (lo hace el controlador)

**Files:** `/home/manolo/claude/futbol-base-v2/.git` (nuevo), y los tres documentos de `docs/`.

- [ ] **Step 1: Crear el repositorio con el historial de v1, sin remoto donde empujar**

```bash
git -C /home/manolo/claude/futbol-base fetch origin          # solo actualiza origin/main en local
cd /home/manolo/claude/futbol-base-v2
git init -b main
git fetch /home/manolo/claude/futbol-base 'refs/remotes/origin/main:refs/remotes/v1/main'
git reset --hard refs/remotes/v1/main
git remote add v1 https://github.com/malolocabreralolo-tech/futbol-base.git
git remote set-url --push v1 no-se-empuja-a-v1
```

- [ ] **Step 2: Comprobar**

Run: `git log -1 --format='%h %s' && git status --short && git remote -v`
Expected: el último commit de v1; solo `docs/` nuevos sin seguimiento; la URL de push de `v1` es `no-se-empuja-a-v1`.

- [ ] **Step 3: Commit de los documentos y rama de trabajo**

```bash
git add docs/superpowers/specs/2026-11-13-futbol-base-v2-design.md docs/revision-2026-11-13.md docs/superpowers/plans/2026-11-13-v2-fase0-copia-pc.md
git commit -m "docs: diseño de v2, hallazgos de la revisión y plan de la fase 0"
git switch -c fase0-copia-pc
```

Las tareas 2 a 7 se hacen en la rama `fase0-copia-pc`, una detrás de otra. `fase0-copia-pc` se fusiona en `main` cuando el controlador ha revisado toda la fase.

---

### Task 2: Verificar una base

**Files:**
- Create: `pc/copia/copia/__init__.py`, `pc/copia/copia/rutas.py`, `pc/copia/copia/verificar.py`
- Test: `pc/copia/tests/conftest.py`, `pc/copia/tests/test_rutas.py`, `pc/copia/tests/test_verificar.py`

**Interfaces:**
- Produces (`rutas.py`, lo usan `almacen` y `fuentes`):
  ```python
  def raiz() -> Path        # FB_COPIA_RAIZ o ~/backups/futbol-base; la crea si falta, con 0o700
  ```
- Produces (`verificar.py`):
  ```python
  TABLAS: tuple[str, ...]            # las nueve de Global Constraints, en ese orden
  MARGEN_MENGUA = 0.02
  @dataclass(frozen=True)
  class Resultado:
      ok: bool
      motivos: tuple[str, ...]
      recuentos: dict[str, int]      # tabla -> filas; {} si no se pudo abrir
  def comprobar(db: Path, anterior: Mapping[str, int] | None = None, margen: float = MARGEN_MENGUA) -> Resultado
  ```
- Produces (conftest, lo usan todas las tareas):
  ```python
  @pytest.fixture
  def raiz(tmp_path, monkeypatch) -> Path     # tmp_path/"copias"; fija FB_COPIA_RAIZ; no la crea
  def crear_base(ruta: Path, partidos: int = 40, wal: bool = True) -> Path
  ```
  `crear_base`: las nueve tablas; `matches.group_id REFERENCES groups(id)`; `partidos` filas en `matches` y al menos una en cada una de las demás; en modo WAL y cerrada tras `PRAGMA wal_checkpoint(TRUNCATE)`.

Textos exactos de los motivos:
`no se puede abrir: <error>` · `integridad: <primera línea de integrity_check>` · `claves foráneas: <n> filas` · `falta la tabla <t>` · `<t> está vacía` · `mengua: <t> <antes> → <ahora>`

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_rutas.py` y `test_verificar.py`)

```python
# test_rutas.py
def test_raiz_por_variable(raiz):
    assert rutas.raiz() == raiz and raiz.is_dir() and stat.S_IMODE(raiz.stat().st_mode) == 0o700

def test_raiz_por_defecto(tmp_path, monkeypatch):
    monkeypatch.delenv("FB_COPIA_RAIZ", raising=False); monkeypatch.setenv("HOME", str(tmp_path))
    assert rutas.raiz() == tmp_path / "backups" / "futbol-base"

# test_verificar.py
def test_base_sana(tmp_path):
    r = comprobar(crear_base(tmp_path / "a.db"))
    assert r.ok and r.motivos == ()
    assert r.recuentos["matches"] == 40 and set(r.recuentos) == set(TABLAS)

def test_no_deja_ficheros_al_lado(tmp_path):
    comprobar(crear_base(tmp_path / "a.db"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.db"]

def test_corrupta(tmp_path):          # bytes 4096-8192 a 0xff
    ...; assert not r.ok and r.motivos[0].startswith(("integridad:", "no se puede abrir:"))

def test_truncada(tmp_path):          # recortada a 1000 bytes
def test_no_es_sqlite(tmp_path):      # un fichero de texto
    ...; assert not r.ok and r.recuentos == {}

def test_falta_tabla(tmp_path):       # DROP TABLE scorers
    ...; assert "falta la tabla scorers" in r.motivos

def test_tabla_vacia(tmp_path):       # DELETE FROM goals
    ...; assert "goals está vacía" in r.motivos

def test_clave_foranea(tmp_path):     # un partido con group_id=999999 metido con foreign_keys=OFF
    ...; assert "claves foráneas: 1 filas" in r.motivos

def test_mengua(tmp_path):
    r = comprobar(crear_base(tmp_path / "a.db", partidos=40), anterior={"matches": 100})
    assert not r.ok and "mengua: matches 100 → 40" in r.motivos

def test_mengua_en_el_margen(tmp_path):
    assert comprobar(crear_base(tmp_path / "a.db", partidos=98), anterior={"matches": 100}).ok
    assert not comprobar(crear_base(tmp_path / "b.db", partidos=97), anterior={"matches": 100}).ok

def test_crecer_no_es_mengua(tmp_path):
    assert comprobar(crear_base(tmp_path / "a.db"), anterior={"matches": 10}).ok
```

- [ ] **Step 2: Ejecutarlas y ver que fallan**

Run: `cd pc/copia && python3 -m pytest tests -q`
Expected: FAIL (`ModuleNotFoundError: copia.rutas` / `copia.verificar`).

- [ ] **Step 3: Implementar `raiz`** en `pc/copia/copia/rutas.py` **y `comprobar`** en `pc/copia/copia/verificar.py`

Se acumulan todos los motivos (no se para en el primero), salvo si no se puede abrir. Una tabla de `anterior` que no esté en `TABLAS` se ignora.

- [ ] **Step 4: Ejecutarlas y ver que pasan**

Run: `cd pc/copia && python3 -m pytest tests -q`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add pc/copia/copia/__init__.py pc/copia/copia/rutas.py pc/copia/copia/verificar.py pc/copia/tests/conftest.py pc/copia/tests/test_rutas.py pc/copia/tests/test_verificar.py
git commit -m "copia del PC: raíz de las copias y verificación de una base (integridad, claves, tablas y mengua)"
```

---

### Task 3: Almacén de versiones

**Files:**
- Create: `pc/copia/copia/almacen.py`
- Test: `pc/copia/tests/test_almacen.py`

**Interfaces:**
- Consumes: `rutas.raiz`, `verificar.comprobar`, `verificar.Resultado`; `conftest.raiz`, `conftest.crear_base`.
- Produces:
  ```python
  class CopiaDanada(Exception): ...
  @dataclass(frozen=True)
  class Version:
      origen: str
      momento: datetime                  # UTC, con tzinfo
      ruta: Path                         # versiones/<origen>/<AAAA>/futbolbase-<AAAAMMDD-HHMMSS>.db.xz
      sha256: str                        # de la base sin comprimir
      recuentos: dict[str, int]
  def versiones(origen: str) -> list[Version]                 # de la más antigua a la más nueva
  def aceptar(origen: str, db: Path, recuentos: Mapping[str, int], ahora: datetime) -> Version | None
  def apartar(origen: str, db: Path, motivos: Sequence[str], ahora: datetime) -> Path
  def restaurar(origen: str, destino: Path, momento: datetime | None = None) -> Path
  ```
- Disposición bajo `raiz()`:
  - `versiones/<origen>/<AAAA>/futbolbase-<AAAAMMDD-HHMMSS>.db.xz` y, al lado, `…db.json` con `{"sha256", "bytes", "recuentos"}`.
  - `actual/<origen>/futbolbase.db`, sin comprimir.
  - `cuarentena/<origen>/futbolbase-<AAAAMMDD-HHMMSS>.db.xz` y `…db.motivo.txt` (un motivo por línea, y la huella en la primera).
- `aceptar` devuelve `None` si la huella es la de la última versión, pero repone `actual/` si falta o no coincide.
- `restaurar` escribe `destino/futbolbase-<AAAAMMDD-HHMMSS>.db`, comprueba la huella y `comprobar()`, y lanza `CopiaDanada` si no cuadran; lanza `ValueError` si `destino` está dentro de `raiz()/"actual"`.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_almacen.py`)

```python
AHORA = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)

def test_aceptar_guarda_version_y_actual(raiz, tmp_path):
    db = crear_base(tmp_path / "a.db"); r = comprobar(db)
    v = aceptar("v1", db, r.recuentos, AHORA)
    assert v.ruta == raiz / "versiones/v1/2026/futbolbase-20261113-050000.db.xz"
    assert lzma.open(v.ruta).read() == db.read_bytes()
    assert v.sha256 == hashlib.sha256(db.read_bytes()).hexdigest()
    assert json.loads(v.ruta.with_suffix("").with_suffix(".db.json").read_text())["recuentos"]["matches"] == 40
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == db.read_bytes()
    assert stat.S_IMODE(raiz.stat().st_mode) == 0o700

def test_aceptar_sin_cambios_devuelve_none(raiz, tmp_path):     # misma base una hora después -> None, 1 versión
def test_aceptar_repone_actual(raiz, tmp_path):                 # se borra actual/, misma base -> None y actual vuelve
def test_versiones_ordenadas_y_por_origen(raiz, tmp_path):      # 3 bases distintas en v1 y 1 en v2
def test_apartar(raiz, tmp_path):
    p = apartar("v1", db, ["mengua: matches 100 → 40"], AHORA)
    assert p == raiz / "cuarentena/v1/futbolbase-20261113-050000.db.xz"
    assert "mengua: matches 100 → 40" in p.with_suffix("").with_suffix(".db.motivo.txt").read_text()
    assert not (raiz / "actual").exists()
def test_apartar_no_repite_la_misma(raiz, tmp_path):            # dos veces la misma base -> 1 .xz
def test_apartar_conserva_diez(raiz, tmp_path):                 # 12 distintas -> quedan las 10 más nuevas
def test_restaurar_ultima(raiz, tmp_path):
    assert restaurar("v1", tmp_path / "r").read_bytes() == ultima.read_bytes()
def test_restaurar_por_momento(raiz, tmp_path)
def test_restaurar_detecta_copia_danada(raiz, tmp_path):        # se sustituye el .xz por otro contenido
    with pytest.raises(CopiaDanada): restaurar("v1", tmp_path / "r")
def test_restaurar_no_escribe_en_actual(raiz, tmp_path):
    with pytest.raises(ValueError): restaurar("v1", raiz / "actual/v1")
def test_escritura_interrumpida_no_deja_version(raiz, tmp_path, monkeypatch):
    # os.replace lanza OSError durante aceptar. Con monkeypatch.context(), nunca monkeypatch.undo():
    # undo() desharía también FB_COPIA_RAIZ de la fixture y la prueba escribiría en ~/backups.
    with monkeypatch.context() as m:
        m.setattr(os, "replace", falla)
        with pytest.raises(OSError): aceptar("v1", db, r.recuentos, AHORA)
    assert versiones("v1") == [] and not (raiz / "actual/v1/futbolbase.db").exists()
    assert aceptar("v1", db, r.recuentos, AHORA) is not None
```

- [ ] **Step 2: Ejecutarlas y ver que fallan**

Run: `cd pc/copia && python3 -m pytest tests/test_almacen.py -q` — Expected: FAIL (`ModuleNotFoundError: copia.almacen`).

- [ ] **Step 3: Implementar `almacen.py`**

El orden dentro de `aceptar`: primero la versión comprimida y su `.json`, después `actual/`. `versiones()` solo cuenta un `.xz` que tenga su `.json`.

- [ ] **Step 4: Ejecutarlas y ver que pasan** — Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add pc/copia/copia/almacen.py pc/copia/tests/test_almacen.py
git commit -m "copia del PC: almacén de versiones, actual, cuarentena y restauración"
```

---

### Task 4: Retención y volcados en texto

**Files:**
- Modify: `pc/copia/copia/almacen.py`
- Test: `pc/copia/tests/test_retencion.py`

**Interfaces:**
- Consumes: `almacen.versiones`, `almacen.aceptar`, `almacen.raiz`.
- Produces:
  ```python
  def a_conservar(momentos: Sequence[datetime], ahora: datetime) -> set[datetime]     # pura
  def podar(origen: str, ahora: datetime) -> list[Path]         # devuelve los .xz borrados (borra también su .json)
  def volcar(origen: str, ahora: datetime) -> Path | None       # volcados/<origen>/futbolbase-<AAAA>-S<WW>.sql.xz
  ```
- Ventanas: diaria `ahora - m < timedelta(days=30)`; semanal `ahora - m < timedelta(weeks=26)`; semana y año ISO en UTC.
- `volcar` usa `sqlite3.Connection.iterdump()` sobre `actual/<origen>/futbolbase.db`; devuelve `None` si ya hay volcado de esa semana ISO o si no hay `actual/`; tras escribir, deja los 12 más nuevos.
- De paso, en `aceptar` (tarea 3): si ya existe una versión con ese mismo segundo y otra huella, lanza `FileExistsError` en vez de pisarla. Una copia nunca se sobrescribe.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_retencion.py`)

```python
def test_a_conservar():
    ahora = datetime(2027, 6, 30, 12, 0, tzinfo=timezone.utc)
    dias = [datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc) + timedelta(days=i) for i in range(395)]   # hasta el 30/6/2027
    k = a_conservar(dias, ahora)
    d = lambda a, m, dd: datetime(a, m, dd, 5, 0, tzinfo=timezone.utc)
    assert d(2027, 6, 30) in k            # la última
    assert d(2027, 6, 5) in k             # diaria (25 días)
    assert d(2027, 6, 1) in k             # diaria (29 días y 7 h)
    assert d(2027, 5, 30) in k            # domingo: la más nueva de su semana ISO
    assert d(2027, 5, 31) in k            # la más nueva de mayo
    assert d(2027, 5, 25) not in k        # 36 días, ni fin de semana ISO ni fin de mes
    assert d(2026, 12, 31) in k           # la más nueva de diciembre
    assert d(2026, 12, 13) not in k       # domingo, pero de hace 199 días
    assert d(2026, 6, 30) in k and d(2026, 6, 15) not in k

def test_a_conservar_vacio():  assert a_conservar([], ahora) == set()

def test_podar_borra_y_nunca_la_ultima(raiz, tmp_path):
    # versiones el 1/6/2026, 15/6/2026, 30/6/2026, 25/5/2027, 30/5/2027 y 30/6/2027 (05:00 UTC, bases distintas)
    borradas = podar("v1", datetime(2027, 6, 30, 12, 0, tzinfo=timezone.utc))
    assert len(borradas) == 3
    assert [v.momento.date().isoformat() for v in versiones("v1")] == ["2026-06-30", "2027-05-30", "2027-06-30"]
    assert not any(p.with_suffix("").with_suffix(".db.json").exists() for p in borradas)

def test_volcar(raiz, tmp_path):
    # tras aceptar una base el 13/11/2026
    p = volcar("v1", AHORA)
    assert p == raiz / "volcados/v1/futbolbase-2026-S46.sql.xz"
    # cargar el volcado en una base nueva da los mismos recuentos en las nueve tablas
    assert volcar("v1", AHORA + timedelta(days=1)) is None          # misma semana ISO

def test_volcar_sin_actual(raiz):  assert volcar("v1", AHORA) is None
def test_volcar_conserva_doce(raiz, tmp_path)   # 14 semanas seguidas -> 12 ficheros

def test_aceptar_no_pisa_una_version_del_mismo_segundo(raiz, tmp_path):
    v = aceptar("v1", a, ra.recuentos, AHORA)                 # a y b son bases distintas
    with pytest.raises(FileExistsError): aceptar("v1", b, rb.recuentos, AHORA)
    assert lzma.open(v.ruta).read() == a.read_bytes() and len(versiones("v1")) == 1
    assert (raiz / "actual/v1/futbolbase.db").read_bytes() == a.read_bytes()
```

- [ ] **Step 2: Ejecutarlas y ver que fallan** — Run: `cd pc/copia && python3 -m pytest tests/test_retencion.py -q`
- [ ] **Step 3: Implementar `a_conservar`, `podar` y `volcar`**
- [ ] **Step 4: Ejecutarlas y ver que pasan** — Expected: 7 passed.
- [ ] **Step 5: Commit**

```bash
git add pc/copia/copia/almacen.py pc/copia/tests/test_retencion.py
git commit -m "copia del PC: retención de versiones y volcado semanal en texto"
```

---

### Task 5: Espejo de git y extracción

**Files:**
- Create: `pc/copia/copia/fuentes.py`, `pc/copia/origenes.json`
- Modify: `pc/copia/tests/conftest.py` (añade `remoto`)
- Test: `pc/copia/tests/test_fuentes.py`

**Interfaces:**
- Consumes: `rutas.raiz` y `conftest.crear_base` (tarea 2). No depende de las tareas 3 y 4.
- Produces:
  ```python
  class FuenteError(Exception): ...
  @dataclass(frozen=True)
  class Origen:
      nombre: str; repo: str; rama: str; base: str
  def cargar_origenes(ruta: Path) -> list[Origen]
  def actualizar_espejo(origen: Origen, ahora: datetime) -> str      # sha del commit de la rama
  def extraer_base(origen: Origen, commit: str, destino: Path) -> Path
  def extraer_fichero(origen: Origen, ruta: str, destino: Path, commit: str | None = None) -> Path
  ```
- Produces (conftest): `remoto(tmp_path) -> Path`, un repositorio git local con rama `main`, un `futbolbase.db` de `crear_base` y `scripts/x_raw.json` con `{"a": 1}`; y `commit_base(remoto, partidos) -> str`, que sustituye la base y devuelve el sha.
- Espejo: `raiz()/repos/<nombre>.git`, creado con `git clone --mirror` en un nombre temporal y renombrado al acabar. Se actualiza con `git fetch` **sin** `--prune`. Tras cada actualización se fija `refs/copia/<rama>/<AAAAMMDD>` al commit de la rama.
- `origenes.json`:
  ```json
  {"v1": {"repo": "https://github.com/malolocabreralolo-tech/futbol-base.git", "rama": "main", "base": "futbolbase.db"}}
  ```
- git se llama con `GIT_TERMINAL_PROMPT=0` y sin credenciales (los repositorios son públicos).

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_fuentes.py`)

```python
def test_cargar_origenes(tmp_path):
    assert cargar_origenes(f) == [Origen("v1", "https://x/y.git", "main", "futbolbase.db")]

def test_espejo_y_extraer(raiz, remoto, tmp_path):
    o = Origen("v1", str(remoto), "main", "futbolbase.db")
    sha = actualizar_espejo(o, AHORA)
    assert sha == git(remoto, "rev-parse", "main")
    assert (raiz / "repos/v1.git").is_dir()
    assert extraer_base(o, sha, tmp_path / "x.db").read_bytes() == (remoto / "futbolbase.db").read_bytes()
    assert git(raiz / "repos/v1.git", "rev-parse", "refs/copia/main/20261113") == sha

def test_segunda_pasada_trae_lo_nuevo(raiz, remoto, tmp_path):     # commit_base(remoto, 50); la ref del día anterior sigue
def test_reescritura_no_pierde_lo_anterior(raiz, remoto, tmp_path):
    viejo = actualizar_espejo(o, AHORA)
    # main del remoto pasa a ser un historial huérfano nuevo
    nuevo = actualizar_espejo(o, AHORA + timedelta(days=1))
    assert nuevo != viejo
    assert subprocess.run(["git", "-C", str(raiz / "repos/v1.git"), "cat-file", "-e", viejo]).returncode == 0
    assert extraer_base(o, viejo, tmp_path / "v.db").exists()

def test_remoto_caido(raiz, tmp_path):
    o = Origen("v1", str(tmp_path / "no-existe"), "main", "futbolbase.db")
    with pytest.raises(FuenteError): actualizar_espejo(o, AHORA)
    assert not (raiz / "repos").exists() or list((raiz / "repos").iterdir()) == []

def test_extraer_fichero(raiz, remoto, tmp_path):
    assert json.loads(extraer_fichero(o, "scripts/x_raw.json", tmp_path / "x.json").read_text()) == {"a": 1}

def test_sin_base_en_el_commit(raiz, remoto, tmp_path):            # git rm futbolbase.db
    with pytest.raises(FuenteError): extraer_base(o, sha, tmp_path / "x.db")
```

- [ ] **Step 2: Ejecutarlas y ver que fallan** — Run: `cd pc/copia && python3 -m pytest tests/test_fuentes.py -q`
- [ ] **Step 3: Implementar `fuentes.py` y escribir `origenes.json`**
- [ ] **Step 4: Ejecutarlas y ver que pasan** — Expected: 7 passed.
- [ ] **Step 5: Commit**

```bash
git add pc/copia/copia/fuentes.py pc/copia/origenes.json pc/copia/tests/conftest.py pc/copia/tests/test_fuentes.py
git commit -m "copia del PC: espejo de git sin podas y extracción de la base y de ficheros"
```

---

### Task 6: La pasada, el estado y la orden

**Files:**
- Create: `pc/copia/copia/ejecutar.py`, `pc/copia/copia/__main__.py`
- Test: `pc/copia/tests/test_ejecutar.py`, `pc/copia/tests/test_cli.py`

**Interfaces:**
- Consumes: todo lo de las tareas 2 a 5.
- Produces:
  ```python
  def ejecutar(origenes: Sequence[Origen], ahora: datetime, aceptar_mengua: Collection[str] = ()) -> int
  def estado(ahora: datetime) -> tuple[str, int]
  def main(argv: Sequence[str] | None = None) -> int
  ```
- `ejecutar`, por cada origen: espejo → extraer la base a un temporal → `comprobar` contra los recuentos de `ultima_buena` (sin ellos si el origen está en `aceptar_mengua`) → `aceptar`, `volcar` y `podar`, o `apartar`. Un fallo de un origen no para a los demás. Devuelve `0` si todos acaban en `aceptada` o `sin cambios`, `1` si alguno acaba en `cuarentena` o `error`, `2` si otra pasada tiene el cerrojo (`raiz()/.cerrojo`, `fcntl.flock` sin espera) y entonces no toca nada.
- `raiz()/estado.json`, escrito de forma atómica tras cada origen:
  ```json
  {"v1": {"ultima_buena": {"momento": "2026-11-13T05:00:00+00:00", "sha256": "…", "recuentos": {"matches": 40}, "version": "versiones/v1/2026/futbolbase-20261113-050000.db.xz", "commit": "…"},
          "ultima_comprobacion": {"momento": "…", "resultado": "aceptada|sin cambios|cuarentena|error", "detalle": ["…"], "commit": "…"}}}
  ```
- `raiz()/registro.log`: una línea por origen y pasada: `<momento ISO> <origen> <resultado> <detalle separado por «; »>`.
- `almacen.restaurar` lanza `LookupError` si no hay versión (o no la hay de ese momento): `main` lo convierte en un mensaje y código `1`. `--momento` se lee como UTC (`tzinfo=timezone.utc`), porque `restaurar` compara el momento exacto.
- `estado`: una línea por origen con el momento y el resultado de la última comprobación, el momento de la última buena y sus recuentos de `matches` y `players`, y una última línea con lo que ocupa `raiz()`. Código `0` si todos los orígenes tienen `ultima_buena`, su último resultado es `aceptada` o `sin cambios` y su última comprobación tiene menos de 3 días; si no, `1`. Sin `estado.json`: el texto contiene `sin copias` y el código es `1`.
- Orden: `ejecutar [--aceptar-mengua ORIGEN]…`, `estado`, `versiones ORIGEN`, `restaurar ORIGEN DESTINO [--momento AAAAMMDD-HHMMSS]`, `extraer ORIGEN RUTA DESTINO`. Los orígenes salen de `FB_COPIA_ORIGENES` o, si no está, del `origenes.json` que hay junto al paquete (`Path(__file__).parent.parent`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# test_ejecutar.py
def test_pasada_buena(raiz, remoto):
    assert ejecutar([o], AHORA) == 0
    e = json.loads((raiz / "estado.json").read_text())["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "aceptada"
    assert e["ultima_buena"]["recuentos"]["matches"] == 40
    assert e["ultima_buena"]["commit"] == git(remoto, "rev-parse", "main")
    assert (raiz / "actual/v1/futbolbase.db").exists()
    assert (raiz / "volcados/v1/futbolbase-2026-S46.sql.xz").exists()
    linea, = (raiz / "registro.log").read_text().splitlines()
    assert " v1 aceptada" in linea

def test_sin_cambios(raiz, remoto):              # segunda pasada -> 0, «sin cambios», 1 versión
def test_base_menguada_va_a_cuarentena(raiz, remoto):
    ejecutar([o], AHORA); commit_base(remoto, 10)
    assert ejecutar([o], AHORA + timedelta(days=1)) == 1
    e = json.loads((raiz / "estado.json").read_text())["v1"]
    assert e["ultima_comprobacion"]["resultado"] == "cuarentena"
    assert "mengua: matches 40 → 10" in e["ultima_comprobacion"]["detalle"]
    assert e["ultima_buena"]["recuentos"]["matches"] == 40
    assert comprobar(raiz / "actual/v1/futbolbase.db").recuentos["matches"] == 40
def test_base_corrupta_va_a_cuarentena(raiz, remoto):   # el remoto sube la base con los bytes 4096-8192 a 0xff -> 1, «cuarentena», actual sigue siendo la buena
def test_aceptar_mengua(raiz, remoto):           # …, aceptar_mengua={"v1"} -> 0 y ultima_buena con 10
def test_misma_rechazada_no_se_repite(raiz, remoto):   # dos pasadas con la menguada -> 1 .xz en cuarentena/v1
def test_un_origen_caido_no_para_al_otro(raiz, remoto, tmp_path):   # v1 bueno y v2 con URL inexistente -> 1; v1 «aceptada», v2 «error»
def test_cerrojo(raiz, remoto):                  # con flock tomado en raiz/.cerrojo -> 2 y no existe estado.json
def test_estado(raiz, remoto):
    assert "sin copias" in estado(AHORA)[0] and estado(AHORA)[1] == 1
    ejecutar([o], AHORA)
    texto, codigo = estado(AHORA + timedelta(hours=1)); assert codigo == 0 and "v1" in texto and "40" in texto
    assert estado(AHORA + timedelta(days=4))[1] == 1

# test_cli.py  (FB_COPIA_ORIGENES apunta a un origenes.json con el remoto de prueba)
def test_cli(raiz, remoto, tmp_path, monkeypatch, capsys):
    assert main(["ejecutar"]) == 0
    assert main(["estado"]) == 0 and "v1" in capsys.readouterr().out
    assert main(["versiones", "v1"]) == 0
    assert main(["restaurar", "v1", str(tmp_path / "r")]) == 0 and list((tmp_path / "r").glob("*.db"))
    assert main(["extraer", "v1", "scripts/x_raw.json", str(tmp_path / "x.json")]) == 0
    assert main(["restaurar", "v9", str(tmp_path / "r")]) == 1        # origen desconocido
```

- [ ] **Step 2: Ejecutarlas y ver que fallan** — Run: `cd pc/copia && python3 -m pytest tests/test_ejecutar.py tests/test_cli.py -q`
- [ ] **Step 3: Implementar `ejecutar.py` y `__main__.py`** (`main` usa `datetime.now(timezone.utc)`; las funciones reciben `ahora`).
- [ ] **Step 4: Ejecutar toda la batería** — Run: `cd pc/copia && python3 -m pytest tests -q` — Expected: todo en verde.
- [ ] **Step 5: Commit**

```bash
git add pc/copia/copia/ejecutar.py pc/copia/copia/__main__.py pc/copia/tests/test_ejecutar.py pc/copia/tests/test_cli.py
git commit -m "copia del PC: la pasada completa, el estado y la orden"
```

---

### Task 7: Instalación, temporizador y primera copia real

**Files:**
- Create: `pc/copia/instalar.sh`, `pc/copia/systemd/futbol-base-copia.service`, `pc/copia/systemd/futbol-base-copia.timer`, `pc/copia/README.md`
- Test: `pc/copia/tests/test_instalar.py`

**Interfaces:**
- Consumes: la orden de la tarea 6.
- Produces:
  - `instalar.sh` copia `copia/` y `origenes.json` a `$FBC_HOME/.local/share/futbol-base-copia/`, escribe `$FBC_HOME/.local/bin/futbol-base-copia` (ejecutable; `PYTHONPATH` a esa carpeta y `exec python3 -s -m copia "$@"`), copia las dos unidades a `$FBC_HOME/.config/systemd/user/` y, salvo con `FBC_SIN_SYSTEMD=1`, hace `systemctl --user daemon-reload` y `enable --now futbol-base-copia.timer`. `FBC_HOME` vale `$HOME` por defecto. Volver a ejecutarlo actualiza la copia instalada.
  - Servicio: `Type=oneshot`, `ExecStart=%h/.local/bin/futbol-base-copia ejecutar`, `TimeoutStartSec=1800`, `Nice=10`.
  - Temporizador: `OnCalendar=*-*-* 04:40:00`, `Persistent=true`, `RandomizedDelaySec=600`.
  - `README.md`: qué guarda y dónde, cómo ver el estado, cómo restaurar una versión, cómo sacar un fichero original, qué hacer si algo va a cuarentena, y que la copia está en el mismo disco que el sistema.

- [ ] **Step 1: Escribir la prueba que falla** (`test_instalar.py`)

```python
def test_instalar_en_un_home_de_prueba(tmp_path):
    env = {**os.environ, "FBC_HOME": str(tmp_path), "FBC_SIN_SYSTEMD": "1", "FB_COPIA_RAIZ": str(tmp_path / "copias")}
    subprocess.run(["bash", "instalar.sh"], cwd=PC_COPIA, env=env, check=True)
    lanzador = tmp_path / ".local/bin/futbol-base-copia"
    assert os.access(lanzador, os.X_OK)
    assert (tmp_path / ".local/share/futbol-base-copia/copia/ejecutar.py").exists()
    assert (tmp_path / ".local/share/futbol-base-copia/origenes.json").exists()
    assert "Persistent=true" in (tmp_path / ".config/systemd/user/futbol-base-copia.timer").read_text()
    r = subprocess.run([str(lanzador), "estado"], env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "sin copias" in r.stdout
```

- [ ] **Step 2: Ejecutarla y ver que falla**
- [ ] **Step 3: Escribir `instalar.sh`, las dos unidades y el `README.md`**
- [ ] **Step 4: Ejecutar toda la batería** — Run: `cd pc/copia && python3 -m pytest tests -q` — Expected: todo en verde.
- [ ] **Step 5: Commit**

```bash
git add pc/copia/instalar.sh pc/copia/systemd pc/copia/README.md pc/copia/tests/test_instalar.py
git commit -m "copia del PC: instalación, temporizador diario y guía"
```

- [ ] **Step 6 (controlador): instalar de verdad y hacer la primera copia**

```bash
bash /home/manolo/claude/futbol-base-v2/pc/copia/instalar.sh
~/.local/bin/futbol-base-copia ejecutar; echo "código $?"
~/.local/bin/futbol-base-copia estado
systemctl --user list-timers futbol-base-copia.timer --no-pager
```
Expected: código 0; `v1 aceptada` con `matches` por encima de 37.000 y `players` por encima de 17.000; el temporizador listado con su próxima ejecución.

- [ ] **Step 7 (controlador): restauración real**

```bash
D=$(mktemp -d); ~/.local/bin/futbol-base-copia restaurar v1 "$D"
sha256sum "$D"/*.db ~/backups/futbol-base/actual/v1/futbolbase.db
```
Expected: las dos huellas iguales, e iguales a la del `.json` de la versión.

---

### Task 8: Limpieza local de v1 y memoria (lo hace el controlador)

**Files:** `/home/manolo/claude/futbol-base` (solo local), `~/backups/futbol-base/local-v1/`, la ficha de memoria del proyecto.

- [ ] **Step 1: Guardar todas las ramas, el stash y las copias de respaldo antes de tocar nada**

```bash
mkdir -p ~/backups/futbol-base/local-v1
git -C /home/manolo/claude/futbol-base bundle create ~/backups/futbol-base/local-v1/futbol-base-local-20261113.bundle --all
git -C /home/manolo/claude/futbol-base bundle verify ~/backups/futbol-base/local-v1/futbol-base-local-20261113.bundle
git -C /home/manolo/claude/futbol-base for-each-ref --format='%(refname) %(objectname)' > ~/backups/futbol-base/local-v1/refs-20261113.txt
```
Expected: «is okay»; el fichero de referencias lista las 27 ramas, el stash y las remotas.

- [ ] **Step 2: Quitar las copias de trabajo sin cambios y las ramas ya fusionadas**

Para cada copia de trabajo de `git worktree list` que no sea la principal: comprobar `git -C <ruta> status --porcelain` vacío y entonces `git worktree remove <ruta>`. Después `git worktree prune`. Borrar con `git branch -d` solo las ramas que salgan en `git branch --merged origin/main` (nunca `main`, nunca con `-D`).
Expected: quedan `main` y las ramas con commits sin fusionar (`barra-ios`, `mejoras-mad`, `respaldo-web`, `worktree-wf_1b09086d-679-5`, `worktree-wf_b5a8652d-076-1`, `worktree-wf_b5a8652d-076-2`) más las que git no dé por fusionadas.

- [ ] **Step 3: Poner `main` al día y compactar**

```bash
cd /home/manolo/claude/futbol-base && git status --short && git merge --ff-only origin/main && git gc
git count-objects -vH && du -sh .git .
```
Expected: avance rápido sin conflictos; `size` de objetos sueltos cerca de cero.

- [ ] **Step 4: Recortar la ficha de memoria**

Copiar `~/.claude/projects/-home-manolo/memory/futbol-base-state.md` a `~/backups/futbol-base/local-v1/futbol-base-state-20261113.md` y reescribirla en menos de 150 líneas: qué es cada versión, dónde está, cómo se publica, las reglas que siguen vigentes y los punteros a los documentos del repositorio.
