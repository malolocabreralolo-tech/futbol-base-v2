# Rebase y publicación de la rama del rediseño (`rediseno-acta`)

El rediseño «Acta» se construye en la rama `rediseno-acta`, y cada fase se publica al terminarla, con el visto bueno del usuario: `main` avanza hasta la rama con avance rápido (B2 en `376e981`, B3 en `862486f` y B4 en `a66a36b`). Entre una publicación y otra, el bot sigue comiteando en `main` cada pocas horas, y la rama trae `main` a menudo (spec §12). Este es el procedimiento (Plan B2, decisión 8), y al final, el de publicar (Plan B4, decisión 10).

## Qué choca y qué se queda

El bot (`update.yml`, y la activación, `activar.yml`) comitea tres cosas:

- **`data-*.js`, `data-health.json` y `futbolbase.db`.** La rama no los toca, así que no chocan. Si alguno chocara, se queda el de `main`: `git checkout --ours -- <fichero>` (en un rebase, «ours» es `main`). La excepción son los `data-*.js` que la rama retira a propósito (B4: `data-matchdetail-keys.js`, `data-stats.js` y `data-players-*.js`): si el bot los regeneró en `main`, chocan como «borrados en la rama y modificados en `main`», y se resuelven con `git rm`, nunca con el de `main`.
- **`sw.js`.** El bot solo cambia `CACHE_NAME`, en la línea 1, y el manifiesto del precache, el bloque entre `// >>> precache` y `// <<< precache`, con las huellas de lo que publica (`generate_js.main()` → `scripts/precache.py`). La línea 2, `CRESTS_CACHE` (el sello de `escudos/`, Plan B5), solo la cambia `scripts/build_crests.py`, al añadir o cambiar un escudo; y la rama cambia el resto. Git no mezcla solo dos cambios en líneas contiguas: si el bot subió la versión y la rama trae otra línea 2 (la primera vez, al traer B5), `sw.js` choca, y se resuelve como `index.html`, con la estructura de la rama y las marcas de `main` (abajo).
- **`index.html`.** El bot sube todas las `?v=` y el literal oculto «Última actualización». Desde el corte, la rama tiene otro `index.html`, y el choque es casi seguro.

Siempre se queda **la estructura de la rama con las marcas de versión de `main`**: las `?v=`, «Última actualización» y `CACHE_NAME`. Lo hace `scripts/sync_versions.py` (que no cuenta el manifiesto del precache como un cambio de `main`). Tras fusionar, el manifiesto se rehace con el árbol fusionado: `python3 scripts/precache.py`. `CACHE_NAME` y las `?v=` no se suben a mano: las sube `scripts/publicar.py` al publicar una fase (abajo).

## Antes de rebasar

```bash
cd /home/manolo/claude/futbol-base-v2
git status --short
git fetch origin
git switch rediseno-acta
python3 scripts/sync_versions.py --from origin/main --since "$(git merge-base HEAD origin/main)"
```

- `git status` no debe mostrar ficheros modificados. `HANDOFF.md` y `docs/mejoras-2026-09.md` salen con `??` porque no están en git, y no cuentan.
- `sync_versions.py --since` comprueba que, desde la base común, `main` solo ha cambiado las marcas de versión de `index.html` y `sw.js`. Si sale con 1, alguien arregló algo en esos ficheros en `main`: hay que llevar ese cambio a mano a la rama después del rebase, porque la estructura de la rama lo sustituye.

## Rebasar

```bash
cd /home/manolo/claude/futbol-base-v2
git rebase origin/main
```

Si se para con un conflicto:

```bash
cd /home/manolo/claude/futbol-base-v2
git diff --name-only --diff-filter=U
```

Si los únicos ficheros en conflicto son `index.html`, `sw.js` o los dos:

```bash
cd /home/manolo/claude/futbol-base-v2
git checkout --theirs -- $(git diff --name-only --diff-filter=U -- index.html sw.js)
python3 scripts/sync_versions.py --from origin/main
git add index.html sw.js
GIT_EDITOR=true git rebase --continue
```

- En un rebase, «theirs» es el commit de la rama que se está aplicando: su estructura.
- `sync_versions.py` le pone las marcas de `origin/main`.

Se repite en cada parada hasta que termine el rebase. Un conflicto en cualquier otro fichero se resuelve a mano: el bot nunca toca `src/` ni `docs/`; en `scripts/` solo comitea lo que generan `fetch-fiflp*.yml` (`scripts/fiflp_*_raw.json`, `scripts/tests/fixtures/acta_*.html`), que la rama no toca.

## Después de rebasar

```bash
cd /home/manolo/claude/futbol-base-v2
python3 scripts/sync_versions.py --from origin/main --check
python3 -m pytest scripts/tests/ -q
node --test scripts/tests/test_*.mjs
node scripts/tests/render-smoke.mjs
node scripts/tests/interaction-smoke.mjs
node scripts/tests/pwa-smoke.mjs
node scripts/tests/frescura-smoke.mjs
```

- `--check` sale con 0 si `index.html` y `sw.js` llevan las marcas de `origin/main`. Si no, dice cuáles faltan.
- Después vienen las suites y los cuatro smoke, todos en verde. Los smoke necesitan Playwright (`npm install --no-save --package-lock=false playwright@1.58.0`) y Chrome.

## Empujar

**Nunca se empuja con un workflow en marcha.**

```bash
cd /home/manolo/claude/futbol-base-v2
gh run list -R malolocabreralolo-tech/futbol-base-v2 --limit 3
git push --force-with-lease origin rediseno-acta
```

`gh run list -R malolocabreralolo-tech/futbol-base-v2` no debe mostrar ninguna ejecución `in_progress` ni `queued`. `--force-with-lease` no pisa la rama remota si alguien la movió después del último `fetch`.

El PR borrador #2 hacia `main` quedó cerrado al publicar B2, y un push a la rama no lanza `tests.yml`: se lanza a mano, `gh workflow run tests.yml -R malolocabreralolo-tech/futbol-base-v2 --ref rediseno-acta`, con las suites y los tres smoke.

## Publicar una fase

Con el visto bueno del usuario, sin ningún workflow en marcha y con el árbol limpio. El paso de publicar de cada plan (el de B3, Tarea 12, paso 10) tiene las comprobaciones de la web; esto es lo que se repite en cada fase:

1. **Traer `main`** con un merge (`git merge --no-edit origin/main`): en un merge, «ours» es la rama. Si chocan `index.html` o `sw.js`, `git checkout --ours` de esos dos y `python3 scripts/sync_versions.py --from origin/main`; al final, `python3 scripts/sync_versions.py --from origin/main --check`. Un conflicto en otro fichero se resuelve a mano: el bot nunca toca `src/` ni `docs/`; en `scripts/` solo comitea lo que generan `fetch-fiflp*.yml` (`scripts/fiflp_*_raw.json`, `scripts/tests/fixtures/acta_*.html`), que la rama no toca. Si la fase borró un `data-*.js` que el bot sigue regenerando en `main` (B4: `data-matchdetail-keys.js`, `data-stats.js` y `data-players-*.js`), sale un conflicto «modificado y borrado»: se resuelve con `git rm` de esos ficheros. Resuelto todo, `python3 scripts/precache.py` (el manifiesto del precache, con las huellas del árbol fusionado), `git add` de lo resuelto y `git commit` termina el merge. Si fue limpio (sin conflicto) pero se queda con las marcas de una versión que no llegó a publicarse en `main` (decisión 53: el bot comitea `data-health.json` varias veces al día y la fusión suele ser limpia), `--check` falla al final: `python3 scripts/sync_versions.py --from origin/main`, `git add index.html sw.js` y `git commit --amend --no-edit` lo meten en el commit de la fusión. Y un retirado que `main` añada sin conflicto (p. ej. un `data-players-<temporada>.js` nuevo al activar una temporada) no lo avisa el merge: se comprueba a mano y se quita con `git rm`. El bloque completo, con sus comprobaciones, está en el paso de publicar del plan (Tarea 7, paso 2).
2. **Subir la versión** con `scripts/publicar.py`: el código empaquetado en `dist/`, las `?v=` de `index.html` y `CACHE_NAME` de `sw.js` a la vez, con la fecha UTC (o, si no es mayor que la vigente, la letra siguiente de la vigente y, tras la `z`, el día siguiente al suyo, sin letra: la misma regla que el bot), y el manifiesto del precache, sin tocar «Última actualización»:

   ```bash
   cd /home/manolo/claude/futbol-base-v2
   python3 scripts/publicar.py
   git diff --stat
   ```

   Sale la línea del paquete (`fuentes <h>: dist/app-<h>.js y dist/acta-<h>.css, en index.html …`), `versión <V> (antes, <la vigente>): <N> ?v= en index.html y futbolbase-v<V> en sw.js; «Última actualización: <la de los datos>», sin tocar` y la del precache, y en el `diff`, solo `index.html`, `sw.js` y `dist/`. Si falta esbuild o si falta algo que el SW tiene que instalar, se para sin escribir nada.

   **`dist/`** es el código que carga la página: `dist/app-<h>.js` (`src/app.js` con todo su grafo, en un módulo, sin `src/config.js`, que se carga aparte) y `dist/acta-<h>.css` (la hoja minificada), cada uno con las 8 primeras cifras del SHA-1 de su contenido en el nombre, y `dist/origen.json`, que dice de qué fuentes salen. No se edita a mano: lo escribe `python3 scripts/codigo.py` (que también llama `publicar.py`), con las rutas en `index.html` (después, `python3 scripts/precache.py` las lleva, con sus huellas, al precache de `sw.js`), y `python3 scripts/codigo.py --check`, sin node, comprueba que está al día con `src/` y `acta.css` (lo hace también `test_empaquetar.py`). Empaqueta con esbuild, que se instala una vez en el PC con `npm ci --prefix scripts/empaquetar` (su `package-lock.json` fija la versión; `node_modules/` no se versiona). El bot y la activación de una temporada nunca empaquetan: `src/config.js` queda fuera del paquete.
3. **Suites y los tres smoke**, en verde, y el commit `Publica Bn del rediseño «Acta»: versión <V>` con `index.html`, `sw.js` y `dist/`.
4. **Empujar la rama, su CI y después `main`**: `git push origin rediseno-acta`, `gh workflow run tests.yml -R malolocabreralolo-tech/futbol-base-v2 --ref rediseno-acta` y, con esa ejecución en verde, `git push origin rediseno-acta:main` (avance rápido). Cada push, sin ningún workflow en marcha (`gh run list -R malolocabreralolo-tech/futbol-base-v2 --limit 5`). Si `main` avanzó mientras tanto, el push se rechaza: se vuelve al paso 1.
5. **Comprobar la web** con el perfil de un móvil que tenía la versión anterior, apertura a apertura, como en el paso de publicar del plan.

## Cómo se actualiza la app

La app instalada se actualiza con el service worker (`sw.js`), que guarda en tres cachés, todas `futbolbase2-…` (el origen lo comparten v1 y otros proyectos; nunca toca otras):

- **`futbolbase2-precache`**: lo que se instala, cada fichero con la clave `<ruta>?h=<huella>` (las 8 primeras cifras del SHA-1 de su contenido). La lista es el manifiesto del principio de `sw.js`, que escribe `scripts/precache.py`: obligatorios (`index.html`, el paquete de `dist/`, `src/config.js`, `manifest.json`, la fuente, los iconos y los `data-*.js` inmediatos de `index.html`) y opcionales (`data-alevin.js` y los archivos de temporada).
- **`futbolbase2-v<versión>`** (`CACHE_NAME`): los datos perezosos ya usados y `data-health.json`; una por versión de datos.
- **`futbolbase2-escudos-<sello>`**: los escudos.

**Instalar es todo o nada.** El SW nuevo pide cada fichero del manifiesto que no tenga ya (`?h=<huella>`, sin la caché HTTP) y lo guarda solo si su cuerpo da su huella; como mucho 6 a la vez. Si falla un obligatorio (un 404, o un despliegue a medias que da otro contenido), no se instala: el anterior sigue al mando con su versión entera, y el navegador lo reintenta. Lo que ya bajó se queda para el reintento. Un opcional que falla se baja al usarse. Al activarse, borra las `futbolbase2-v*` y `futbolbase2-escudos-*` viejas, quita del precache las claves que su manifiesto ya no tiene, toma el mando y avisa a las ventanas abiertas (`{ type: 'version' }`).

**La página abierta se pone al día sola** (`src/actualizacion.js`): si el aviso del SW trae una versión más nueva que la suya (la `?v=` de `data-seasons.js`; se comparan como texto, que con la forma del bot, `AAAAMMDD` y una letra opcional, es su orden), recarga, si nadie la ha tocado (ni puntero, ni tecla, ni desplazamiento) desde que se abrió o volvió a primer plano y no se ha recargado ya sola por esa versión (la apunta en `sessionStorage`, `fb2:recarga`); si no, pone en la cabecera «Hay datos nuevos.» con «Actualizar», que no se quita solo. Oculta, lo decide al volver a verse. Una versión más vieja (la de un SW intermedio que se activa cuando la página ya llegó más nueva de la red) no hace nada. Al volver a primer plano (o a tener red) pide al navegador que busque un `sw.js` nuevo, como mucho una vez por minuto.

**Qué sirve a cada petición:** la página, de la red primero (2,5 s como mucho) y, si no llega, el `index.html` instalado; `data-health.json`, igual, guardado en `CACHE_NAME` y marcado `x-fb2-origen: cache` cuando sale de la copia; los escudos, de su caché; lo que pide una página de otra versión (otra `?v=`), de la red primero (8 s) y, si no, la copia que haya, sin guardarlo; lo del manifiesto, de su clave; los datos perezosos, de `CACHE_NAME` o de la red, y se guardan; lo demás, la red. Tras un fallo de la red, durante 30 s la página y la salud van derechas a la copia: con mala cobertura se espera una sola vez.

**Limitación aceptada:** si la página nueva llega de la red y un dato suyo no llega en 8 s, se pinta con la copia anterior de ese dato y nadie avisa; se corrige en la apertura siguiente.

**Lo prueba en un Chrome de verdad** `scripts/tests/frescura-smoke.mjs`: sobre una copia de la web, publica versiones de datos como el bot (`generate_js.bump_cache_version` y `precache.escribir`) y comprueba la primera apertura tras publicar, sin conexión después, un obligatorio en 404, un despliegue a medias, la página abierta que vuelve a primer plano, la página en uso y la red que no contesta.
