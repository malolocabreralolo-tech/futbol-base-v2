/**
 * Node test runner — el contrato del service worker con el bot, con index.html y con v1, los escudos y
 * data-health.json. Lo de instalar, activar y servir por contenido, en test_sw_precache.mjs.
 * Run: node --test scripts/tests/test_sw_fixes.mjs
 *
 * Cubre:
 *   1. el manifiesto del precache: las temporadas archivadas y el alevín, opcionales; las actas, fuera
 *   2. index.html registra el SW sin desregistrarlo en cada carga
 *   3. C3: CACHE_NAME literal en la línea 1, que sube el bot con /futbolbase2-v[0-9a-z]+/
 *   4. activate: solo las cachés de esta app de otras versiones
 *   5. los escudos, en su propia caché: CRESTS_CACHE en la línea 2, con el sello de escudos/
 *   6. data-health.json, primero de la red: el aviso de estado de la portada no puede leer la salud de la
 *      visita anterior
 *
 * sw.js es un guion clásico: se carga en un contexto vm con un `self` falso, y sus funciones puras se leen
 * por su nombre.
 */

import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const swSrc = readFileSync(join(ROOT, 'sw.js'), 'utf8');
const idxSrc = readFileSync(join(ROOT, 'index.html'), 'utf8');

// ─── cargar sw.js (guion clásico → vm con un self falso) ──────────────────
function loadSw(globals = {}) {
  const listeners = {};
  const selfStub = {
    addEventListener: (type, fn) => { listeners[type] = fn; },
    skipWaiting: () => {},
    clients: { claim: async () => {}, matchAll: async () => [] },
    location: { origin: 'https://example.test', href: 'https://example.test/sw.js' },
  };
  // AbortController y los temporizadores: los usa el tope de las peticiones (LIMITE_RED_MS).
  const ctx = { self: selfStub, console, URL, AbortController, setTimeout, clearTimeout, ...globals };
  vm.createContext(ctx);
  const probes = ['CACHE_NAME', 'CRESTS_CACHE', 'PRECACHE', 'OPCIONALES', 'LINEUPS_KEEP', 'lineupsToCarry', 'classifyRequest', 'LIMITE_SALUD_MS',
    'LIMITE_RED_MS'];
  const probe = probes
    .map(n => `${n}:typeof ${n}!=='undefined'?${n}:undefined`)
    .join(',');
  vm.runInContext(`${swSrc}\nthis.__exports={${probe}};`, ctx);
  return { ...ctx.__exports, listeners };
}

const sw = loadSw();

// ─── 1. el manifiesto: lo perezoso que se instala, y lo que no ─────────────
// Las temporadas archivadas (Trayectoria y «Ver temporadas anteriores» cargan el archivo entero) y el
// alevín de la temporada en curso se guardan al instalar, opcionales: si fallan, se bajan al usarse. El
// manifiesto lo escribe scripts/precache.py con todo data-season-AAAA-AAAA.js del árbol.
test('invariant: cada temporada pasada de data-seasons.js tiene su archivo en el precache, opcional', () => {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(`${readFileSync(join(ROOT, 'data-seasons.js'), 'utf8')}\nthis.__s = SEASONS;`, ctx);
  const past = Array.from(ctx.__s).filter((s) => !s.current).map((s) => `data-season-${s.name}.js`);
  assert.ok(past.length > 0);
  for (const file of past) assert.ok(sw.OPCIONALES.includes(file), file);
  const seasons = sw.OPCIONALES.filter((f) => f.startsWith('data-season-'));
  assert.deepEqual([...seasons], [...seasons].sort().reverse(), 'de la más nueva a la más vieja');
});

test('data-alevin.js, opcional y fuera de index.html; los data-season-<S>-alevin.js y las actas, fuera del precache', () => {
  assert.ok(sw.OPCIONALES.includes('data-alevin.js'));
  assert.doesNotMatch(idxSrc, /data-alevin\.js/, 'index.html no lo carga');
  assert.ok(existsSync(join(ROOT, 'data-alevin.js')), 'data-alevin.js existe siempre (vacío sin grupos de alevín)');
  assert.ok(!Object.keys(sw.PRECACHE).some((f) => /^data-season-.*-alevin\.js$|^data-lineups-|^data-jugadores-/.test(f)));
  assert.equal(sw.classifyRequest('/data-season-2025-2026-alevin.js', null), 'dato');
});

// Las actas de grupo ya usadas pasan a la versión nueva (la ficha de mi equipo, ya
// vista, sigue con su plantilla sin conexión tras una subida de datos): sin repetir, las más recientes
// y como mucho LINEUPS_KEEP; ni los demás datos ni las actas antiguas, de temporada entera.
test('lineupsToCarry: las actas de grupo de las cachés anteriores, sin repetir, las más recientes', () => {
  const base = 'https://x.github.io/futbol-base/';
  const urls = [
    `${base}data-lineups-2025-2026-A1.js?v=1`, `${base}data-benjamin.js?v=1`, `${base}data-lineups-2025-2026.js`,
    `${base}data-lineups-2026-2027-FF3.js`, `${base}data-lineups-2025-2026-A1.js?v=2`,
  ];
  assert.deepEqual([...sw.lineupsToCarry(urls)], ['./data-lineups-2026-2027-FF3.js', './data-lineups-2025-2026-A1.js']);
  const many = Array.from({ length: 20 }, (_, i) => `${base}data-lineups-2025-2026-P${i + 1}.js`);
  const kept = [...sw.lineupsToCarry(many)];
  assert.equal(kept.length, sw.LINEUPS_KEEP);
  assert.equal(kept.at(-1), './data-lineups-2025-2026-P20.js');
});

test('source contract: el fetch reparte con classifyRequest(url.pathname, ?v=)', () => {
  assert.equal(typeof sw.classifyRequest, 'function');
  assert.match(swSrc, /classifyRequest\(url\.pathname, url\.searchParams\.get\('v'\)\)/);
});

// ─── 2. index.html: el registro de siempre, sin desregistrar ──────────────
test('index.html registers SW without unregistering on every load', () => {
  assert.ok(!/unregister\s*\(/.test(idxSrc),
    'index.html must NOT unregister the SW on every load');
  assert.ok(!/getRegistrations/.test(idxSrc),
    'index.html must NOT enumerate registrations to nuke them');
  assert.ok(/navigator\.serviceWorker\.register\(['"]\.\/sw\.js['"]\)/.test(idxSrc),
    'index.html must register ./sw.js');
  assert.ok(/\.update\(\)/.test(idxSrc),
    'index.html must call registration.update() on each load');
});

test('index.html ya no limpia cachés al arrancar: lo hace el SW al activarse', () => {
  assert.doesNotMatch(idxSrc, /caches\.|CODIGO|fb2:codigo/);
});

test('sw.js lifecycle: skipWaiting on install, clients.claim on activate', () => {
  assert.ok(/self\.skipWaiting\(\)/.test(swSrc), 'install must call self.skipWaiting()');
  assert.ok(/clients\.claim\(\)/.test(swSrc), 'activate must call clients.claim()');
  assert.equal(typeof sw.listeners.install, 'function', 'install listener registered');
  assert.equal(typeof sw.listeners.activate, 'function', 'activate listener registered');
  assert.equal(typeof sw.listeners.fetch, 'function', 'fetch listener registered');
});

// ─── 3. C3: CACHE_NAME contract for generate_js.py ────────────────────────
test('C3: CACHE_NAME literal on line 1, bumpable via /futbolbase2-v[0-9a-z]+/', () => {
  const firstLine = swSrc.split('\n')[0];
  assert.ok(/^const CACHE_NAME = 'futbolbase2-v[0-9a-z]+';\s*$/.test(firstLine),
    `line 1 must be const CACHE_NAME = 'futbolbase2-vXXXX'; — got: ${firstLine}`);
  assert.ok(/futbolbase2-v[0-9a-z]+/.test(sw.CACHE_NAME),
    'CACHE_NAME value must match futbolbase2-v[0-9a-z]+');
});

// La línea 2 es la caché de los escudos: su nombre lleva el sello de escudos/, que
// escribe scripts/build_crests.py (test_build_crests.py comprueba que es el de escudos/ tal como está), y
// la expresión con la que el bot sube la versión (futbolbase2-v[0-9a-z]+) no la alcanza
// (test_index_bot_contract.py lo ejecuta, con sync_versions.py y publicar.py).
test('CRESTS_CACHE literal on line 2, with the seal of escudos/ and out of reach of the bot', () => {
  const second = swSrc.split('\n')[1];
  assert.match(second, /^const CRESTS_CACHE = 'futbolbase2-escudos-[0-9a-f]{8}';$/);
  assert.equal(sw.CRESTS_CACHE, second.slice("const CRESTS_CACHE = '".length, -2));
  assert.doesNotMatch(second, /futbolbase2-v[0-9a-z]+/);
});

// ─── 4. activate: solo las cachés de esta app ──
test('activate solo borra las cachés de esta app de otras versiones, futbolbase2-v* y futbolbase2-escudos-*: el origen es compartido', async () => {
  // malolocabreralolo-tech.github.io lo comparten v1 y otros proyectos de la cuenta: sus cachés no se
  // tocan. La de los escudos se queda mientras su sello sea el de CRESTS_CACHE, aunque cambie CACHE_NAME;
  // futbolbase2-precache no se borra nunca (solo pierde las claves que ya no están en el manifiesto).
  assert.match(sw.CRESTS_CACHE ?? '', /^futbolbase2-escudos-[0-9a-f]{8}$/);
  assert.notEqual(sw.CRESTS_CACHE, 'futbolbase2-escudos-00000000');
  const deleted = [];
  const worker = loadSw({ caches: {
    keys: async () => ['futbolbase2-v20250101', sw.CACHE_NAME, 'futbolbase2-v20991231z', 'otro-proyecto-v1', 'workbox-precache-v2', 'futbolbase2',
      sw.CRESTS_CACHE, 'futbolbase2-escudos-00000000', 'futbolbase2-escudos', 'otro-proyecto-escudos-1', 'futbolbase2-precache'],
    delete: async (name) => { deleted.push(name); return true; },
    open: async () => ({ keys: async () => [], delete: async () => true }),
  } });
  let done;
  worker.listeners.activate({ waitUntil: (promise) => { done = promise; } });
  await done;
  assert.deepEqual(deleted.sort(), ['futbolbase2-escudos-00000000', 'futbolbase2-v20250101', 'futbolbase2-v20991231z']);
});

// ─── 5. los escudos, en su propia caché ──────────────────
test('classifyRequest: los escudos, originales y miniaturas, con cualquier ?v=, van a su propia caché', () => {
  assert.equal(sw.classifyRequest('/futbol-base/escudos/100x100arucas.png', null), 'escudo');
  assert.equal(sw.classifyRequest('/escudos/100x100arucas.png', 'otra'), 'escudo');
  assert.equal(sw.classifyRequest('/futbol-base/escudos/s/100x100arucas.png', null), 'escudo');
  assert.equal(sw.classifyRequest('/futbol-base/escudos/joveroLasRosas.jpg', null), 'escudo');
});

test('los escudos se sirven de CRESTS_CACHE; si no están, de la red con su sello como ?v=, y se guardan allí (decisión 1 de B5)', async () => {
  // El fetch de verdad, con unas cachés y una red falsas: nunca se abre CACHE_NAME, que cambia con cada
  // subida de datos, y la red se pide con el sello como ?v= (la clave de la caché HTTP del navegador).
  const seal = (sw.CRESTS_CACHE ?? '').replace('futbolbase2-escudos-', '');
  assert.match(seal, /^[0-9a-f]{8}$/);
  const opened = [];
  const stored = new Map();
  const asked = [];
  const worker = loadSw({
    caches: {
      open: async (name) => {
        opened.push(name);
        return { match: async (request) => stored.get(request.url), put: async (request, response) => { stored.set(request.url, response); } };
      },
    },
    fetch: async (url, init) => { asked.push(`${url} ${init.cache}`); return { ok: true, clone() { return this; } }; },
  });
  const serve = (url) => new Promise((resolve) => {
    worker.listeners.fetch({ request: { url, method: 'GET' }, respondWith: resolve, waitUntil: () => {} });
  });
  const url = 'https://example.test/futbol-base/escudos/s/huracan.png';
  const first = await serve(url);
  assert.deepEqual(asked, [`${url}?v=${seal} no-cache`], 'la primera vez, de la red, con el sello');
  assert.equal(stored.get(url), first, 'y ya guardado en CRESTS_CACHE al responder');
  assert.equal(await serve(url), first, 'la segunda, de CRESTS_CACHE');
  assert.equal(asked.length, 1, 'sin volver a la red');
  assert.deepEqual([...new Set(opened)], [sw.CRESTS_CACHE], 'nunca CACHE_NAME');
});

// ─── 6. data-health.json: primero la red, con límite; si no, la copia marcada ──
test('classifyRequest: data-health.json → salud, con cualquier ?v=; fuera del precache', () => {
  assert.equal(sw.classifyRequest('/futbol-base-v2/data-health.json', null), 'salud');
  assert.equal(sw.classifyRequest('/data-health.json', 'otra'), 'salud');
  assert.ok(!('data-health.json' in sw.PRECACHE), 'la instalación la guarda en CACHE_NAME, aparte');
  assert.equal(sw.LIMITE_SALUD_MS, 2500);
});

// Un SW con una caché en memoria (con su copia de data-health.json, sin query) y la red que se pida.
function healthWorker({ network, timers = { setTimeout, clearTimeout } }) {
  const stored = new Map([['https://example.test/data-health.json', new Response('{"checkedAt":"vieja"}', {
    status: 200, headers: { 'content-type': 'application/json' } })]]);
  const opened = [];
  const cache = {
    match: async (request) => stored.get(typeof request === 'string' ? request : request.url)?.clone(),
    put: async (request, response) => { stored.set(typeof request === 'string' ? request : request.url, response); },
  };
  const asked = [];
  const worker = loadSw({
    caches: { open: async (name) => { opened.push(name); return cache; } }, Response, Headers, ...timers,
    fetch: (url, init) => { asked.push(`${url} ${init.cache}`); return network(); },
  });
  const pending = [];
  const serve = (url) => new Promise((resolve) => {
    worker.listeners.fetch({ request: { url, method: 'GET' }, respondWith: resolve, waitUntil: (p) => pending.push(p) });
  });
  return { serve, stored, asked, opened, settle: () => Promise.all(pending) };
}
const URL_SALUD = 'https://example.test/data-health.json?v=20261114t';

test('salud: con red, la respuesta de la red, guardada sin query en CACHE_NAME y sin marca', async () => {
  const w = healthWorker({ network: async () => new Response('{"checkedAt":"nueva"}', { status: 200 }) });
  const response = await w.serve(URL_SALUD);
  assert.equal(await response.text(), '{"checkedAt":"nueva"}');
  assert.equal(response.headers.get('x-fb2-origen'), null);
  await w.settle();
  assert.equal(await w.stored.get('https://example.test/data-health.json').text(), '{"checkedAt":"nueva"}');
  assert.deepEqual([...new Set(w.opened)], [sw.CACHE_NAME]);
  assert.equal(w.asked[0], `${URL_SALUD} no-cache`);
});

test('salud: si la red rechaza o no da un 200, la copia guardada con x-fb2-origen: cache y sus cabeceras', async () => {
  for (const network of [async () => { throw new TypeError('Failed to fetch'); }, async () => new Response('', { status: 503 })]) {
    const w = healthWorker({ network });
    const response = await w.serve(URL_SALUD);
    assert.equal(response.headers.get('x-fb2-origen'), 'cache');
    assert.equal(response.headers.get('content-type'), 'application/json');
    assert.equal(response.status, 200);
    assert.equal(await response.text(), '{"checkedAt":"vieja"}');
    await w.settle().catch(() => {});
  }
});

test('salud: con la red colgada, la copia marcada en cuanto pasa LIMITE_SALUD_MS', async () => {
  const timers = [];
  const w = healthWorker({
    network: () => new Promise(() => {}),
    timers: { setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, clearTimeout: () => {} },
  });
  let response = null;
  const served = w.serve(URL_SALUD).then((r) => { response = r; });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(response, null, 'antes del límite, todavía esperando a la red');
  // Sin contar el tope de la petición (LIMITE_RED_MS), que la aborta más tarde.
  const limites = timers.filter((t) => t.ms !== sw.LIMITE_RED_MS);
  assert.deepEqual(limites.map((t) => t.ms), [sw.LIMITE_SALUD_MS]);
  limites[0].fn();
  await served;
  assert.equal(response.headers.get('x-fb2-origen'), 'cache');
  assert.equal(await response.text(), '{"checkedAt":"vieja"}');
});

test('salud: sin copia guardada, lo que dé la red', async () => {
  const w = healthWorker({ network: async () => new Response('', { status: 404 }) });
  w.stored.clear();
  const response = await w.serve(URL_SALUD);
  assert.equal(response.status, 404);
  assert.equal(response.headers.get('x-fb2-origen'), null);
});
