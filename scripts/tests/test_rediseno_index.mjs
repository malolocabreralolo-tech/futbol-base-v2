// index.html es el esqueleto del rediseño. La cabecera, la barra y la primera caja se pintan antes de
// que lleguen los datos; app.js sustituye la caja. Lo que lee el bot (generate_js.py y source_health.py)
// se ejecuta de verdad en test_index_bot_contract.py; aquí, la forma. La hoja y el módulo de arranque
// son los de dist/ (scripts/codigo.py), con la huella de su contenido en el nombre y sin ?v=, y el
// arranque no limpia cachés: el SW instala por contenido (test_sw_precache.mjs). Los datos inmediatos
// van con defer, el arranque, en una función asíncrona, y el registro del SW, tras load; los iconos y
// el manifiesto, en test_rediseno_pwa.mjs.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { tabbar } from '../../src/ui.js';
import { WORLDS, worldFiles } from './fixture-site.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const INDEX = readFileSync(join(ROOT, 'index.html'), 'utf8');
const ORIGEN = JSON.parse(readFileSync(join(ROOT, 'dist', 'origen.json'), 'utf8'));

test('esqueleto: saltar al contenido, cabecera, la barra de ui.tabbar y main#contenido.page con su primera caja', () => {
  assert.match(INDEX, /<html lang="es">/);
  assert.match(INDEX, /<a class="skip-link" href="#contenido">Saltar al contenido<\/a>/);
  assert.match(INDEX, /<header class="shell-header">/);
  assert.ok(INDEX.includes(String(tabbar('miequipo'))), 'la barra estática es ui.tabbar("miequipo"), tal cual');
  assert.equal((INDEX.match(/<nav\b/g) || []).length, 1);
  assert.match(INDEX, /<main id="contenido" class="page" tabindex="-1">\s*<div class="skeleton-screen" data-skeleton="home" aria-busy="true">/);
  assert.doesNotMatch(INDEX, /<h1\b/, 'el h1 lo pone cada pantalla');
});

test('datos inmediatos: los siete que lee la portada, con defer y en el orden de antes (decisión 5 de B2; B4, decisiones 1 y 4), y después el arranque', () => {
  const scripts = [...INDEX.matchAll(/<script\b[^>]*\bsrc="\.\/([^"?]+)\?v=\d{8}[a-z]?"[^>]*><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(scripts, [
    'data-benjamin.js', 'data-prebenjamin.js', 'data-history.js', 'data-goleadores.js',
    'data-shields.js', 'data-seasons.js', 'data-maspalomas-cup-2026.js',
  ]);
  // Con defer se ejecutan en el orden del documento cuando termina el análisis, y el módulo en línea,
  // detrás: los globales ya están cuando arranca app.js.
  const deferred = [...INDEX.matchAll(/<script defer src="\.\/([^"?]+)\?v=\d{8}[a-z]?"><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(deferred, scripts, 'los siete, con defer');
  // app.js no se arranca al importarse: index.html importa su paquete de dist/ y llama a start.
  const boot = INDEX.match(/<script type="module">[\s\S]*?<\/script>/);
  assert.ok(boot, 'falta el arranque');
  assert.match(boot[0], /const \{ start \} = await import\('\.\/dist\/app-[0-9a-f]{8}\.js'\);\s*start\(document, window\);/);
  assert.ok(boot[0].includes(`await import('./${ORIGEN.app}');`), `el paquete de dist/origen.json, ${ORIGEN.app}`);
  assert.ok(INDEX.indexOf(boot[0]) > INDEX.indexOf('data-maspalomas-cup-2026.js'), 'arranca después de los datos');
  // Sin limpieza de cachés ni marcador: el arranque solo importa el paquete y llama a start.
  assert.doesNotMatch(boot[0], /CODIGO|fb2:codigo|caches\.|localStorage/);
});

test('si el arranque falla, un aviso con estilos en línea y «Reintentar», que busca el SW nuevo y recarga (R2-3)', () => {
  const boot = INDEX.match(/<script type="module">[\s\S]*?<\/script>/)[0];
  // Todo el arranque (el import y start) va dentro del try: sin conexión, con una página nueva cuyo paquete
  // todavía no está guardado, la página nunca se queda en «Cargando…». Y el try, en una función asíncrona
  // que se llama al cerrarla, sin await de nivel superior en el módulo: antes, solo
  // comentarios; después, nada.
  assert.match(boot, /^<script type="module">\s*(?:\/\/[^\n]*\s*)*\(async \(\) => \{\s*try \{\s*const \{ start \} = await import\(/);
  assert.match(boot, /\}\)\(\);\s*<\/script>$/, 'la función asíncrona cierra el módulo');
  assert.ok(boot.indexOf('} catch (error) {') > boot.indexOf('start(document, window);'), 'el catch recoge el import y start');
  assert.match(boot, /innerHTML = `<div role="alert" style="[^"]+">\s*<p style="[^"]+">No se pudo abrir la versión nueva de la app\. Comprueba la conexión y pulsa Reintentar\.<\/p>\s*<button type="button" id="reintentar-arranque" style="[^"]*min-height:44px[^"]*">Reintentar<\/button>\s*<\/div>`;/);
  const retry = boot.slice(boot.indexOf("getElementById('reintentar-arranque')"));
  assert.match(retry, /registration\.update\(\)/, 'Reintentar busca el SW nuevo');
  assert.match(retry, /location\.reload\(\);/, 'y recarga');
});

test('marcas del bot: una sola versión en todas las ?v=, data-seasons.js versionado y el literal oculto', () => {
  const versions = new Set([...INDEX.matchAll(/\?v=([0-9a-z]+)/g)].map((m) => m[1]));
  assert.equal(versions.size, 1, [...versions].join(', '));
  assert.match([...versions][0], /^\d{8}[a-z]?$/);
  // La hoja, la de dist/, sin ?v=: su nombre lleva la huella de su contenido.
  assert.match(INDEX, /<link rel="stylesheet" href="\.\/dist\/acta-[0-9a-f]{8}\.css">/);
  assert.ok(INDEX.includes(`<link rel="stylesheet" href="./${ORIGEN.css}">`), `la hoja de dist/origen.json, ${ORIGEN.css}`);
  assert.equal((INDEX.match(/<link rel="stylesheet"/g) || []).length, 1);
  assert.match(INDEX, /<script defer src="\.\/data-seasons\.js\?v=\d{8}[a-z]?"><\/script>/);
  assert.match(INDEX, /<span id="legacyUpdated" hidden>Última actualización: \d{2}\/\d{2}\/\d{4}<\/span>/);
  assert.equal((INDEX.match(/Última actualización: /g) || []).length, 1);
});

test('tema del sistema: theme-color claro y oscuro, sin selector de tema ni fuentes de Google (spec §4.9)', () => {
  assert.match(INDEX, /<meta name="theme-color" content="#FFFFFF" media="\(prefers-color-scheme: light\)">/);
  assert.match(INDEX, /<meta name="theme-color" content="#15171C" media="\(prefers-color-scheme: dark\)">/);
  assert.doesNotMatch(INDEX, /fonts\.googleapis|fonts\.gstatic|style-acta\.css|style\.css|themeToggle|data-theme/);
});

test('dist/ es el de las fuentes del árbol: src/*.js sin config.js y acta.css (scripts/codigo.py)', () => {
  // La misma huella que calcula scripts/codigo.py: sha1 de acta.css y de src/*.js por nombre, sin
  // src/config.js (se queda fuera del paquete), de cada uno su ruta, un cero, su contenido y otro cero; sus
  // 8 primeras cifras. Si falla, se cambió código sin empaquetar: `python3 scripts/codigo.py` y después
  // `python3 scripts/precache.py`. El bot nunca toca src/ ni acta.css.
  const files = ['acta.css', ...readdirSync(join(ROOT, 'src')).filter((f) => f.endsWith('.js')).sort().map((f) => `src/${f}`)]
    .filter((file) => !ORIGEN.externos.includes(file));
  const hash = createHash('sha1');
  for (const file of files) hash.update(Buffer.concat([Buffer.from(`${file}\0`), readFileSync(join(ROOT, file)), Buffer.from('\0')]));
  assert.equal(ORIGEN.codigo, hash.digest('hex').slice(0, 8), 'dist/ desfasado: ejecuta python3 scripts/codigo.py');
});

// data-matchdetail-keys.js, data-stats.js y data-players-<S>.js no los lee nadie (el ⚽ de las listas se
// fue con la app anterior, Récords sale del modelo y la plantilla, de las actas) y el generador no los
// escribe (su prueba, en test_pygen_fixes.py). Si volvieran, cada carga en frío los descargaría para
// nada. Una fusión con main que se quede con los que el bot regeneró también sale aquí.
const RETIRED = /data-(?:matchdetail-keys|stats|players-\d{4}-\d{4})\.js/;
test('los datos retirados en B4 no vuelven: ni en index.html, ni en sw.js, ni en el repositorio, ni en los mundos de las pruebas', () => {
  assert.doesNotMatch(INDEX, RETIRED);
  assert.doesNotMatch(readFileSync(join(ROOT, 'sw.js'), 'utf8'), RETIRED);
  assert.deepEqual(readdirSync(ROOT).filter((file) => RETIRED.test(file)), []);
  for (const name of Object.keys(WORLDS)) {
    assert.deepEqual(Object.keys(worldFiles(name)).filter((file) => RETIRED.test(file)), [], `mundo ${name}`);
  }
});

// El SW se registra tras el evento load: con los datos en defer, el <script> del registro corre
// durante el análisis, y en la primera visita su precache (unos 2 MB) competía con los datos y los
// módulos de la portada. Si load ya pasó, en seguida. Se conserva el contrato: register('./sw.js')
// y .update(), sin unregister, dentro de if ('serviceWorker' in navigator). Se ejecuta el <script> real
// con un navegador falso, durante el análisis y ya cargada la página.
test('el service worker se registra tras load, o en seguida si load ya pasó, con register(\'./sw.js\') y .update() (§10)', async () => {
  const script = [...INDEX.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).find((text) => text.includes('serviceWorker'));
  assert.ok(script, 'falta el <script> del registro');
  assert.match(script, /if \('serviceWorker' in navigator\) \{/);
  assert.match(script, /navigator\.serviceWorker\.register\('\.\/sw\.js'\)\s*\.then\(reg => reg\.update\(\)\)/, 'el literal de §10');
  assert.doesNotMatch(script, /unregister\s*\(/, 'sin unregister');
  const run = (readyState) => {
    const calls = [];
    const listeners = {};
    const register = (url) => { calls.push(url); return Promise.resolve({ update: () => calls.push('update') }); };
    vm.runInContext(script, vm.createContext({
      navigator: { serviceWorker: { register } },
      document: { readyState },
      addEventListener: (type, listener) => { listeners[type] = listener; },
    }));
    return { calls, listeners };
  };
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const parsing = run('loading');
  await settle();
  assert.deepEqual(parsing.calls, [], 'durante el análisis no se registra');
  assert.deepEqual(Object.keys(parsing.listeners), ['load']);
  parsing.listeners.load();
  await settle();
  assert.deepEqual(parsing.calls, ['./sw.js', 'update'], 'tras load, se registra y busca la versión nueva');
  const loaded = run('complete');
  await settle();
  assert.deepEqual(loaded.calls, ['./sw.js', 'update'], 'si load ya pasó, en seguida');
  assert.deepEqual(Object.keys(loaded.listeners), []);
});
