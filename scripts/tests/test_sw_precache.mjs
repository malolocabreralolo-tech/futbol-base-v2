/**
 * El service worker por contenido (sw.js): precache con huellas, todo o nada al instalar, la página de la red
 * primero, los datos de otra versión de la red primero y una sola espera con mala red.
 * Run: node --test scripts/tests/test_sw_precache.mjs
 *
 * sw.js es un guion clásico: se evalúa en un contexto vm con `caches`, `fetch`, `clients`, `crypto`, el reloj
 * y los temporizadores simulados. Para instalar y activar se le cambia el bloque del precache por uno de
 * ficheros de juguete, con sus huellas de verdad (SHA-1 de su contenido).
 */
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SW_REAL = readFileSync(join(ROOT, 'sw.js'), 'utf8');
const ORIGEN = JSON.parse(readFileSync(join(ROOT, 'dist', 'origen.json'), 'utf8'));
const INICIO = '// >>> precache: lo escribe scripts/precache.py';
const FIN = '// <<< precache';
const BASE = 'https://example.test/futbol-base-v2/';
const huella = (texto) => createHash('sha1').update(texto).digest('hex').slice(0, 8);

// ─── el mundo simulado ─────────────────────────────────────────────────────
const urlDe = (request) => (typeof request === 'string' ? request : request.url);

class CacheFalsa {
  constructor() { this.entradas = new Map(); }
  async match(request, opciones = {}) {
    const url = urlDe(request);
    if (this.entradas.has(url)) return this.entradas.get(url).clone();
    if (opciones.ignoreSearch) {
      const sin = url.split('?')[0];
      for (const [clave, valor] of this.entradas) if (clave.split('?')[0] === sin) return valor.clone();
    }
    return undefined;
  }
  async put(request, response) { this.entradas.set(urlDe(request), response); }
  async keys() { return [...this.entradas.keys()].map((url) => ({ url })); }
  async delete(request) { return this.entradas.delete(urlDe(request)); }
}

class CachesFalsas {
  constructor() { this.porNombre = new Map(); }
  async open(nombre) {
    if (!this.porNombre.has(nombre)) this.porNombre.set(nombre, new CacheFalsa());
    return this.porNombre.get(nombre);
  }
  async keys() { return [...this.porNombre.keys()]; }
  async has(nombre) { return this.porNombre.has(nombre); }
  async delete(nombre) { return this.porNombre.delete(nombre); }
  async match() { throw new Error('el SW no busca en todas las cachés a la vez'); }
  claves(nombre) { return [...(this.porNombre.get(nombre)?.entradas.keys() || [])]; }
}

// Un sw.js con este bloque del precache y esta versión.
function fuenteCon({ precache, opcionales = [], version }) {
  let fuente = SW_REAL;
  if (precache) {
    const bloque = [INICIO, 'const PRECACHE = {', ...Object.entries(precache).map(([r, h]) => `  ${JSON.stringify(r)}: ${JSON.stringify(h)},`),
      '};', 'const OPCIONALES = [', ...opcionales.map((r) => `  ${JSON.stringify(r)},`), '];', FIN].join('\n');
    fuente = fuente.slice(0, fuente.indexOf(INICIO)) + bloque + fuente.slice(fuente.indexOf(FIN) + FIN.length);
  }
  if (version) fuente = fuente.replace(/^const CACHE_NAME = 'futbolbase2-v[0-9a-z]+';/, `const CACHE_NAME = 'futbolbase2-v${version}';`);
  return fuente;
}

// La red: `respuestas` da, por ruta (relativa al ámbito), el cuerpo, una función (url, init) → Response o
// promesa, o nada (404). Cada petición queda en `pedidas`, con su caché HTTP.
function redFalsa(respuestas) {
  const pedidas = [];
  const fetch = async (request, init = {}) => {
    const url = new URL(urlDe(request));
    pedidas.push({ url: url.href, cache: init.cache });
    const ruta = url.pathname.startsWith('/futbol-base-v2/') ? url.pathname.slice('/futbol-base-v2/'.length) || 'index.html' : url.pathname;
    const dato = respuestas[ruta];
    if (typeof dato === 'function') return dato(url, init);
    if (dato === undefined) return new Response('no está', { status: 404 });
    return new Response(dato, { status: 200 });
  };
  return { fetch, pedidas };
}

function cargar({ fuente = SW_REAL, caches = new CachesFalsas(), red = redFalsa({}), reloj = { t: 1_000_000 }, enLinea = true } = {}) {
  const listeners = {};
  const temporizadores = [];
  const mensajes = [];
  const avisos = [];
  let reclamado = false;
  const self = {
    addEventListener: (tipo, fn) => { listeners[tipo] = fn; },
    skipWaiting: () => {},
    clients: {
      claim: async () => { reclamado = true; },
      matchAll: async (opciones) => (opciones?.includeUncontrolled ? [] : [{ postMessage: (m) => mensajes.push(m) }]),
    },
    location: { origin: 'https://example.test', href: `${BASE}sw.js` },
    navigator: { onLine: enLinea },
  };
  const ctx = {
    self, caches, fetch: red.fetch, crypto: globalThis.crypto, Response, Headers, URL,
    console: { warn: (...a) => avisos.push(a.join(' ')), log() {}, error() {} },
    Date: { now: () => reloj.t },
    setTimeout: (fn, ms) => { temporizadores.push({ fn, ms, vivo: true }); return temporizadores.length; },
    clearTimeout: (id) => { if (temporizadores[id - 1]) temporizadores[id - 1].vivo = false; },
  };
  vm.createContext(ctx);
  const nombres = ['CACHE_NAME', 'CRESTS_CACHE', 'VERSION', 'PRECACHE', 'OPCIONALES', 'PRECACHE_CACHE', 'LIMITE_PAGINA_MS',
    'LIMITE_SALUD_MS', 'LIMITE_DATOS_MS', 'VENTANA_RED_MALA_MS', 'DESCARGAS_A_LA_VEZ', 'classifyRequest', 'precacheKey', 'rutaDe', 'huellaDe', 'lineupsToCarry'];
  vm.runInContext(`${fuente}\nthis.__sw = {${nombres.map((n) => `${n}: typeof ${n} !== 'undefined' ? ${n} : undefined`).join(', ')}};`, ctx);
  const pendientes = [];
  const servir = (url) => new Promise((resolve, reject) => {
    let respondido = false;
    listeners.fetch({
      request: { url, method: 'GET' },
      respondWith: (p) => { respondido = true; Promise.resolve(p).then(resolve, reject); },
      waitUntil: (p) => pendientes.push(p),
    });
    if (!respondido) resolve(null);
  });
  const evento = async (tipo) => {
    let promesa;
    listeners[tipo]({ waitUntil: (p) => { promesa = p; } });
    return promesa;
  };
  return {
    sw: ctx.__sw, caches, red, reloj, temporizadores, mensajes, avisos, servir, evento,
    reclamado: () => reclamado, asentar: () => Promise.allSettled(pendientes),
    vivos: () => temporizadores.filter((t) => t.vivo),
  };
}
const tic = () => new Promise((resolve) => setImmediate(resolve));

// Un juego de ficheros con su manifiesto: dos obligatorios, un dato inmediato y un opcional.
const FICHEROS = {
  'index.html': '<!DOCTYPE html><title>v2</title>',
  'dist/app-aaaaaaaa.js': 'export function start() {}',
  'data-benjamin.js': 'const BENJAMIN = 1;',
  'data-season-2024-2025.js': 'const SEASON_2024_2025 = {};',
};
const MANIFIESTO = Object.fromEntries(Object.entries(FICHEROS).map(([ruta, texto]) => [ruta, huella(texto)]));
const OPC = ['data-season-2024-2025.js'];
const clave = (ruta, h = MANIFIESTO[ruta]) => `${BASE}${ruta}?h=${h}`;
const red = (extra = {}) => redFalsa({ ...FICHEROS, 'data-health.json': '{"checkedAt":"nueva"}', ...extra });

// ─── las funciones puras ───────────────────────────────────────────────────
const real = cargar();

test('las constantes: tres cachés de esta app, los límites y la versión de la línea 1', () => {
  assert.equal(real.sw.PRECACHE_CACHE, 'futbolbase2-precache');
  assert.equal(real.sw.VERSION, real.sw.CACHE_NAME.replace('futbolbase2-v', ''));
  assert.match(real.sw.CRESTS_CACHE, /^futbolbase2-escudos-[0-9a-f]{8}$/);
  assert.equal(real.sw.LIMITE_PAGINA_MS, 2500);
  assert.equal(real.sw.LIMITE_SALUD_MS, 2500);
  assert.equal(real.sw.LIMITE_DATOS_MS, 8000);
  assert.equal(real.sw.VENTANA_RED_MALA_MS, 30000);
  assert.ok(real.sw.DESCARGAS_A_LA_VEZ >= 2 && real.sw.DESCARGAS_A_LA_VEZ <= 8, String(real.sw.DESCARGAS_A_LA_VEZ));
});

test('classifyRequest: una fila por clase, en el orden de la tabla', () => {
  const c = (ruta, v = null) => real.sw.classifyRequest(`/futbol-base-v2/${ruta}`, v);
  const V = real.sw.VERSION;
  const filas = [
    ['', null, 'pagina'], ['index.html', null, 'pagina'], ['index.html', 'otra', 'pagina'],
    ['data-health.json', V, 'salud'], ['data-health.json', 'otra', 'salud'],
    ['escudos/x.png', 'otra', 'escudo'], ['escudos/s/x.png', null, 'escudo'],
    ['data-benjamin.js', 'otra', 'otra-version'], ['src/app.js', '20261101a', 'otra-version'], ['acta.css', '20261101a', 'otra-version'],
    ['data-benjamin.js', V, 'precache'], ['data-season-2019-2020.js', null, 'precache'], [ORIGEN.app, null, 'precache'],
    [ORIGEN.css, null, 'precache'], ['src/config.js', null, 'precache'], ['icons/icon-192.png', null, 'precache'],
    ['data-lineups-2026-2027-FF1.js', V, 'dato'], ['data-jugadores-3.js', V, 'dato'], ['data-matchdetail.js', null, 'dato'],
    ['futbolbase.db', null, 'red'], ['src/state.js', null, 'red'], ['dist/app-00000000.js', null, 'red'],
  ];
  for (const [ruta, v, clase] of filas) assert.equal(c(ruta, v), clase, `${ruta} ?v=${v}`);
});

test('rutaDe, precacheKey y huellaDe', async () => {
  assert.equal(real.sw.rutaDe('/futbol-base-v2/'), 'index.html');
  assert.equal(real.sw.rutaDe('/futbol-base-v2/index.html'), 'index.html');
  assert.equal(real.sw.rutaDe(`/futbol-base-v2/${ORIGEN.app}`), ORIGEN.app);
  assert.equal(real.sw.precacheKey('index.html', '0a1b2c3d'), `${BASE}index.html?h=0a1b2c3d`);
  const texto = 'const A = 1;\n';
  assert.equal(await real.sw.huellaDe(new TextEncoder().encode(texto).buffer), huella(texto));
});

test('el manifiesto de verdad: cada fichero existe y da su huella; los obligatorios incluyen los inmediatos de index.html', () => {
  const index = readFileSync(join(ROOT, 'index.html'), 'utf8');
  for (const [ruta, h] of Object.entries(real.sw.PRECACHE)) {
    assert.equal(huella(readFileSync(join(ROOT, ruta))), h, `${ruta}: python3 scripts/precache.py`);
  }
  const inmediatos = [...index.matchAll(/<script defer src="\.\/(data-[\w.-]+\.js)\?v=/g)].map((m) => m[1]);
  const obligatorios = Object.keys(real.sw.PRECACHE).filter((r) => !real.sw.OPCIONALES.includes(r));
  for (const ruta of ['index.html', ORIGEN.app, ORIGEN.css, ...ORIGEN.externos, 'manifest.json', ...inmediatos]) {
    assert.ok(obligatorios.includes(ruta), ruta);
  }
  assert.ok(real.sw.OPCIONALES.every((r) => r in real.sw.PRECACHE));
});

// ─── instalar ──────────────────────────────────────────────────────────────
test('instalar con todo bien: cada fichero, pedido con su huella y sin la caché HTTP, en futbolbase2-precache', async () => {
  const w = cargar({ fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red() });
  await w.evento('install');
  assert.deepEqual(w.caches.claves('futbolbase2-precache').sort(), Object.keys(MANIFIESTO).map((r) => clave(r)).sort());
  for (const ruta of Object.keys(MANIFIESTO)) assert.ok(w.red.pedidas.some((p) => p.url === clave(ruta) && p.cache === 'no-cache'), ruta);
  // Y data-health.json, en la caché de la versión.
  assert.ok(w.caches.claves(w.sw.CACHE_NAME).includes(`${BASE}data-health.json`));
});

test('instalar con un obligatorio en 404: install rechaza y la caché de la versión anterior sigue entera', async () => {
  const caches = new CachesFalsas();
  const anterior = await caches.open('futbolbase2-v20000101a');
  await anterior.put(`${BASE}index.html`, new Response('vieja'));
  await anterior.put(`${BASE}data-benjamin.js?v=20000101a`, new Response('vieja'));
  const w = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'dist/app-aaaaaaaa.js': undefined }) });
  await assert.rejects(w.evento('install'));
  assert.deepEqual(caches.claves('futbolbase2-v20000101a'), [`${BASE}index.html`, `${BASE}data-benjamin.js?v=20000101a`]);
  assert.ok(!(await caches.has(w.sw.CACHE_NAME)), 'sin la caché de la versión nueva');
});

test('instalar con un obligatorio cuyo cuerpo no da su huella (despliegue a medias): rechaza', async () => {
  const w = cargar({ fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'index.html': '<!DOCTYPE html><title>otra</title>' }) });
  await assert.rejects(w.evento('install'));
  assert.ok(!w.caches.claves('futbolbase2-precache').includes(clave('index.html')), 'no se guarda');
});

test('instalar con un opcional en 404: no rechaza, y lo dice en la consola', async () => {
  const w = cargar({ fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'data-season-2024-2025.js': undefined }) });
  await w.evento('install');
  assert.ok(!w.caches.claves('futbolbase2-precache').includes(clave('data-season-2024-2025.js')));
  assert.equal(w.caches.claves('futbolbase2-precache').length, 3);
  assert.ok(w.avisos.some((a) => a.includes('data-season-2024-2025.js')), w.avisos.join('\n'));
});

test('instalar por segunda vez con una sola huella cambiada: solo se pide ese fichero', async () => {
  const caches = new CachesFalsas();
  await cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red() }).evento('install');
  const nuevo = 'const BENJAMIN = 2;';
  const w = cargar({ caches, fuente: fuenteCon({ precache: { ...MANIFIESTO, 'data-benjamin.js': huella(nuevo) }, opcionales: OPC, version: '20991231a' }),
    red: red({ 'data-benjamin.js': nuevo }) });
  await w.evento('install');
  assert.deepEqual(w.red.pedidas.map((p) => p.url).filter((u) => u.includes('?h=')), [clave('data-benjamin.js', huella(nuevo))]);
});

test('instalar no lanza más de DESCARGAS_A_LA_VEZ descargas a la vez', async () => {
  const muchos = Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`data-season-${2000 + i}-${2001 + i}.js`, `const S${i} = ${i};`]));
  let enVuelo = 0;
  let maximo = 0;
  const lenta = (texto) => async () => {
    enVuelo += 1; maximo = Math.max(maximo, enVuelo);
    await tic();
    enVuelo -= 1;
    return new Response(texto, { status: 200 });
  };
  const respuestas = Object.fromEntries(Object.entries(muchos).map(([ruta, texto]) => [ruta, lenta(texto)]));
  const precache = Object.fromEntries(Object.entries(muchos).map(([ruta, texto]) => [ruta, huella(texto)]));
  const w = cargar({ fuente: fuenteCon({ precache, opcionales: Object.keys(muchos) }), red: redFalsa(respuestas) });
  await w.evento('install');
  assert.equal(w.caches.claves('futbolbase2-precache').length, 20);
  assert.ok(maximo <= w.sw.DESCARGAS_A_LA_VEZ && maximo > 1, `máximo en vuelo: ${maximo}`);
});

test('si mientras se instala alguien quita una clave ya guardada (la limpieza de la versión anterior), se vuelve a bajar', async () => {
  const caches = new CachesFalsas();
  let quitada = false;
  const respuestas = { ...FICHEROS, 'data-season-2024-2025.js': async () => {
    // La última descarga: la limpieza de la versión que activa quita index.html, que ya estaba guardado.
    const cache = await caches.open('futbolbase2-precache');
    for (let i = 0; i < 100 && !(await cache.match(clave('index.html'))); i += 1) await tic();
    if (!quitada) quitada = await cache.delete(clave('index.html'));
    return new Response(FICHEROS['data-season-2024-2025.js'], { status: 200 });
  } };
  const w = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: redFalsa(respuestas) });
  await w.evento('install');
  assert.ok(quitada);
  assert.ok(w.caches.claves('futbolbase2-precache').includes(clave('index.html')), 'index.html, otra vez en su sitio');
});

test('instalar lleva a la versión nueva las actas de grupo usadas en la anterior', async () => {
  const caches = new CachesFalsas();
  const anterior = await caches.open('futbolbase2-v20000101a');
  await anterior.put(`${BASE}data-lineups-2026-2027-FF1.js`, new Response('vieja'));
  await anterior.put(`${BASE}data-benjamin.js?v=20000101a`, new Response('vieja'));
  const w = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'data-lineups-2026-2027-FF1.js': 'const L = 1;' }) });
  await w.evento('install');
  assert.deepEqual(w.caches.claves(w.sw.CACHE_NAME).sort(), [`${BASE}data-health.json`, `${BASE}data-lineups-2026-2027-FF1.js`].sort());
});

// ─── activar ───────────────────────────────────────────────────────────────
test('activar: fuera las claves que no están en el manifiesto y las cachés viejas de esta app; las demás, intactas; y el mensaje version', async () => {
  const caches = new CachesFalsas();
  const precache = await caches.open('futbolbase2-precache');
  await precache.put(clave('index.html'), new Response('compartida'));           // la comparten la vieja y la nueva
  await precache.put(clave('index.html', '00000000'), new Response('vieja'));
  await precache.put(`${BASE}src/app.js?h=11111111`, new Response('vieja'));
  const ajenas = ['futbol-base-v1', 'futbol-base:v2', 'otro-proyecto-v1', 'workbox-precache-v2', 'futbolbase2'];
  for (const nombre of ['futbolbase2-v20000101a', 'futbolbase2-escudos-00000000', ...ajenas]) await caches.open(nombre);
  const w = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }) });
  await caches.open(w.sw.CACHE_NAME);
  await caches.open(w.sw.CRESTS_CACHE);
  await w.evento('activate');
  assert.deepEqual(caches.claves('futbolbase2-precache'), [clave('index.html')]);
  assert.deepEqual((await caches.keys()).sort(), ['futbolbase2-precache', w.sw.CACHE_NAME, w.sw.CRESTS_CACHE, ...ajenas].sort());
  assert.ok(w.reclamado());
  assert.deepEqual(JSON.parse(JSON.stringify(w.mensajes)), [{ type: 'version', version: w.sw.VERSION }]);
});

test('transición desde el SW publicado antes: sus cachés se borran al activar, y una página vieja pide su código a la red', async () => {
  const caches = new CachesFalsas();
  const vieja = await caches.open('futbolbase2-v20261114w');
  for (const ruta of ['', 'index.html', 'src/app.js?v=20261114w', 'acta.css?v=20261114w', 'data-benjamin.js']) await vieja.put(`${BASE}${ruta}`, new Response('vieja'));
  const w = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC, version: '20991231a' }),
    red: red({ 'src/app.js': 'export function start() {}', 'acta.css': 'body{}' }) });
  await w.evento('install');
  await w.evento('activate');
  assert.ok(!(await caches.has('futbolbase2-v20261114w')));
  for (const ruta of ['src/app.js?v=20261114w', 'acta.css?v=20261114w']) {
    const response = await w.servir(`${BASE}${ruta}`);
    assert.equal(response.status, 200, ruta);
    assert.ok(w.red.pedidas.some((p) => p.url === `${BASE}${ruta}` && p.cache === 'no-cache'), `${ruta}, a la red, con su ?v=`);
  }
  // Un módulo de src/ sin ?v= (los imports de la app vieja): a la red, sin pasar por el SW.
  assert.equal(await w.servir(`${BASE}src/state.js`), null);
});

test('una instalación fallida de la versión siguiente no rompe la que sigue al mando; la siguiente buena no borra lo compartido', async () => {
  const caches = new CachesFalsas();
  const n = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC, version: '20990101a' }), red: red() });
  await n.evento('install');
  await n.evento('activate');
  // N+1 cambia el dato y el paquete, pero el paquete nuevo no está publicado todavía: falla a medias.
  const dato = 'const BENJAMIN = 2;';
  const siguiente = { ...MANIFIESTO, 'data-benjamin.js': huella(dato), 'dist/app-bbbbbbbb.js': huella('export function start() { return 2; }') };
  delete siguiente['dist/app-aaaaaaaa.js'];
  const fallida = cargar({ caches, fuente: fuenteCon({ precache: siguiente, opcionales: OPC, version: '20990101b' }), red: red({ 'data-benjamin.js': dato }) });
  await assert.rejects(fallida.evento('install'));
  assert.ok(caches.claves('futbolbase2-precache').includes(clave('data-benjamin.js', huella(dato))), 'lo bajado se queda para el reintento');
  // N sigue sirviendo lo suyo, sin red.
  const sinRed = cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC, version: '20990101a' }),
    red: redFalsa(Object.fromEntries(Object.keys(FICHEROS).map((r) => [r, async () => { throw new TypeError('Failed to fetch'); }]))) });
  assert.equal(await (await sinRed.servir(`${BASE}data-benjamin.js?v=20990101a`)).text(), FICHEROS['data-benjamin.js']);
  assert.equal(await (await sinRed.servir(`${BASE}dist/app-aaaaaaaa.js`)).text(), FICHEROS['dist/app-aaaaaaaa.js']);
  // Ya publicado, N+1 se instala bajando solo el paquete y, al activarse, quita lo que es solo de N.
  const buena = cargar({ caches, fuente: fuenteCon({ precache: siguiente, opcionales: OPC, version: '20990101b' }),
    red: red({ 'data-benjamin.js': dato, 'dist/app-bbbbbbbb.js': 'export function start() { return 2; }' }) });
  await buena.evento('install');
  assert.deepEqual(buena.red.pedidas.map((p) => p.url).filter((u) => u.includes('?h=')), [clave('dist/app-bbbbbbbb.js', siguiente['dist/app-bbbbbbbb.js'])]);
  await buena.evento('activate');
  assert.deepEqual(caches.claves('futbolbase2-precache').sort(), Object.entries(siguiente).map(([r, h]) => clave(r, h)).sort());
});

// ─── servir ────────────────────────────────────────────────────────────────
async function instalado(opciones = {}) {
  const caches = new CachesFalsas();
  await cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red() }).evento('install');
  return cargar({ caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), ...opciones });
}
const caida = async () => { throw new TypeError('Failed to fetch'); };
const colgada = () => new Promise(() => {});

test('pagina: con red, la de la red (sin la caché HTTP y sin guardarla)', async () => {
  const w = await instalado({ red: red({ 'index.html': '<p>de la red</p>' }) });
  const response = await w.servir(`${BASE}`);
  assert.equal(await response.text(), '<p>de la red</p>');
  assert.deepEqual(w.red.pedidas, [{ url: `${BASE}`, cache: 'no-cache' }]);
  await w.asentar();
  assert.equal(await (await (await w.caches.open('futbolbase2-precache')).match(clave('index.html'))).text(), FICHEROS['index.html']);
});

test('pagina: con la red caída, la del precache', async () => {
  const w = await instalado({ red: red({ 'index.html': caida }) });
  assert.equal(await (await w.servir(`${BASE}index.html`)).text(), FICHEROS['index.html']);
});

test('pagina: con la red colgada, la del precache en cuanto pasa LIMITE_PAGINA_MS', async () => {
  const w = await instalado({ red: red({ 'index.html': colgada }) });
  let response = null;
  const servida = w.servir(`${BASE}`).then((r) => { response = r; });
  await tic();
  assert.equal(response, null, 'antes del límite, esperando a la red');
  const [limite] = w.vivos();
  assert.equal(limite.ms, w.sw.LIMITE_PAGINA_MS);
  limite.fn();
  await servida;
  assert.equal(await response.text(), FICHEROS['index.html']);
});

test('otra-version: con red, la de la red con su ?v=, sin guardarla; con la red caída, la copia que haya', async () => {
  const w = await instalado({ red: red({ 'data-benjamin.js': 'const BENJAMIN = 9;' }) });
  const url = `${BASE}data-benjamin.js?v=20991231z`;
  assert.equal(await (await w.servir(url)).text(), 'const BENJAMIN = 9;');
  assert.deepEqual(w.red.pedidas, [{ url, cache: 'no-cache' }]);
  assert.deepEqual(w.vivos().map((t) => t.ms), [], 'el límite, retirado');
  await w.asentar();
  assert.ok(!w.caches.claves(w.sw.CACHE_NAME).some((u) => u.includes('data-benjamin')), 'no se guarda');
  const sinRed = cargar({ caches: w.caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'data-benjamin.js': caida }) });
  assert.equal(await (await sinRed.servir(url)).text(), FICHEROS['data-benjamin.js']);
});

test('otra-version: con la red colgada, la copia pasado LIMITE_DATOS_MS', async () => {
  const w = await instalado({ red: red({ 'data-benjamin.js': colgada }) });
  const servida = w.servir(`${BASE}data-benjamin.js?v=20000101a`);
  await tic();
  const [limite] = w.vivos();
  assert.equal(limite.ms, w.sw.LIMITE_DATOS_MS);
  limite.fn();
  assert.equal(await (await servida).text(), FICHEROS['data-benjamin.js']);
});

// La salud con una copia guardada de la visita anterior.
async function conSalud(opciones) {
  const w = await instalado(opciones);
  await (await w.caches.open(w.sw.CACHE_NAME)).put(`${BASE}data-health.json`,
    new Response('{"checkedAt":"vieja"}', { status: 200, headers: { 'content-type': 'application/json' } }));
  return w;
}
const URL_SALUD = () => `${BASE}data-health.json?v=${real.sw.VERSION}`;

test('salud: con red, la de la red, sin marca, y guardada en CACHE_NAME', async () => {
  const w = await conSalud({ red: red() });
  const response = await w.servir(URL_SALUD());
  assert.equal(await response.text(), '{"checkedAt":"nueva"}');
  assert.equal(response.headers.get('x-fb2-origen'), null);
  await w.asentar();
  assert.equal(await (await (await w.caches.open(w.sw.CACHE_NAME)).match(`${BASE}data-health.json`)).text(), '{"checkedAt":"nueva"}');
});

test('salud: con la red caída, la guardada, con x-fb2-origen: cache y sus cabeceras', async () => {
  const w = await conSalud({ red: red({ 'data-health.json': caida }) });
  const response = await w.servir(URL_SALUD());
  assert.equal(response.headers.get('x-fb2-origen'), 'cache');
  assert.equal(response.headers.get('content-type'), 'application/json');
  assert.equal(await response.text(), '{"checkedAt":"vieja"}');
});

test('una sola espera: tras una página que agota su límite, la salud responde de la copia sin esperar; a los 31 s vuelve a probar la red', async () => {
  const w = await conSalud({ red: red({ 'index.html': colgada, 'data-health.json': colgada }) });
  const pagina = w.servir(`${BASE}`);
  await tic();
  w.vivos()[0].fn();
  assert.equal(await (await pagina).text(), FICHEROS['index.html']);
  w.reloj.t += 1000;
  const antes = w.temporizadores.length;
  const salud = await w.servir(URL_SALUD());
  assert.equal(salud.headers.get('x-fb2-origen'), 'cache', 'de la copia');
  assert.equal(w.temporizadores.length, antes, 'sin esperar a la red');
  assert.ok(w.red.pedidas.some((p) => p.url === URL_SALUD()), 'pero la refresca en segundo plano');
  // Y la página, también derecha a la copia, sin pedirla.
  const pedidas = w.red.pedidas.length;
  assert.equal(await (await w.servir(`${BASE}index.html`)).text(), FICHEROS['index.html']);
  assert.equal(w.red.pedidas.length, pedidas);
  w.reloj.t += 30_000;
  let otra = null;
  w.servir(URL_SALUD()).then((r) => { otra = r; });
  await tic();
  assert.equal(otra, null, 'pasada la ventana, espera a la red otra vez');
  assert.deepEqual(w.vivos().map((t) => t.ms), [w.sw.LIMITE_SALUD_MS]);
});

test('sin conexión (navigator.onLine === false), la página y la salud van derechas a la copia', async () => {
  const w = await conSalud({ red: red({ 'index.html': colgada, 'data-health.json': colgada }), enLinea: false });
  assert.equal(await (await w.servir(`${BASE}`)).text(), FICHEROS['index.html']);
  assert.equal((await w.servir(URL_SALUD())).headers.get('x-fb2-origen'), 'cache');
  assert.deepEqual(w.vivos(), []);
});

test('precache: de su clave, sin red', async () => {
  const w = await instalado({ red: red({ 'data-benjamin.js': caida }) });
  assert.equal(await (await w.servir(`${BASE}data-benjamin.js?v=${real.sw.VERSION}`)).text(), FICHEROS['data-benjamin.js']);
  assert.deepEqual(w.red.pedidas, []);
});

test('precache sin copia (un opcional que falló): se pide, se verifica y se guarda; si la huella no coincide, se devuelve y no se guarda', async () => {
  const fuente = fuenteCon({ precache: MANIFIESTO, opcionales: OPC });
  const buena = cargar({ fuente, red: red() });
  const ruta = 'data-season-2024-2025.js';
  assert.equal(await (await buena.servir(`${BASE}${ruta}`)).text(), FICHEROS[ruta]);
  assert.deepEqual(buena.red.pedidas, [{ url: clave(ruta), cache: 'no-cache' }]);
  assert.deepEqual(buena.caches.claves('futbolbase2-precache'), [clave(ruta)]);
  const mala = cargar({ fuente, red: red({ [ruta]: 'const SEASON_2024_2025 = { otra: 1 };' }) });
  assert.equal(await (await mala.servir(`${BASE}${ruta}`)).text(), 'const SEASON_2024_2025 = { otra: 1 };');
  assert.deepEqual(mala.caches.claves('futbolbase2-precache'), []);
});

test('dato: de CACHE_NAME, sin mirar la query; si no está, de la red, y se guarda', async () => {
  const w = await instalado({ red: red({ 'data-lineups-2026-2027-FF1.js': 'const L = 1;' }) });
  const url = `${BASE}data-lineups-2026-2027-FF1.js?v=${real.sw.VERSION}`;
  assert.equal(await (await w.servir(url)).text(), 'const L = 1;');
  assert.ok(w.caches.claves(w.sw.CACHE_NAME).includes(`${BASE}data-lineups-2026-2027-FF1.js`));
  const sinRed = cargar({ caches: w.caches, fuente: fuenteCon({ precache: MANIFIESTO, opcionales: OPC }), red: red({ 'data-lineups-2026-2027-FF1.js': caida }) });
  assert.equal(await (await sinRed.servir(`${BASE}data-lineups-2026-2027-FF1.js`)).text(), 'const L = 1;');
});

test('red: lo demás no pasa por el SW, ni lo que no es GET ni lo de otro origen', async () => {
  const w = await instalado({ red: red() });
  assert.equal(await w.servir(`${BASE}futbolbase.db`), null);
  assert.equal(await w.servir('https://otro.test/futbol-base-v2/data-benjamin.js'), null);
});
