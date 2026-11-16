// PWA smoke: el paso de la app anterior al rediseño, con el service worker de verdad.
// La versión anterior es la app guardada en scripts/tests/fixtures/app-anterior, con su sw.js,
// con los nombres de caché de v2: hace de una versión anterior de la propia v2, cuyas cachés limpia v2;
// después se publica el árbol de trabajo con las marcas de versión subidas, como un despliegue.
// Las dos versiones reciben los mismos datos y el mismo src/config.js, congelados: los de las
// fixtures (23/09/2026), nunca los data-*.js vivos, que cambian con el bot y al activar 2026/27.
// El SW anterior sirve los .js de src/ con stale-while-revalidate y los .css con cache-first, los dos
// ignorando la ?v=:
//  - la hoja nueva va en otra URL, la de dist/ (con su huella en el nombre), que su caché no tiene;
//  - y el módulo, también en dist/: el index.html nuevo no mezcla nada con lo de la caché anterior (el
//    SW nuevo no limpia cachés al arrancar: instala por contenido, con huellas).
// El SW instala por contenido (con huellas) y la página va de la red primero: los
// servidores de esta prueba vuelven a sellar el sw.js que sirven con las huellas de lo que sirven
// (resellar). Lo que una subida de datos del bot tiene que dar (la primera apertura con los datos nuevos,
// una actualización a medias, la página abierta que se pone al día) está en frescura-smoke.mjs.
// Sirven una copia de la web y de la app anterior, en carpetas temporales (copia-web.mjs), nunca el árbol.
// Mientras el SW nuevo se instala (su precache queda retenido), cada apertura tiene que ser entera de
// una versión: la 1.ª, la anterior; la 2.ª y la 3.ª, la nueva (documento, hoja y módulos), también si
// en la 1.ª falló la actualización en segundo plano de app.js y state.js. Sin conexión entre la 1.ª y
// la 2.ª, el index.html nuevo no encuentra ni la hoja ni los módulos: el aviso con «Reintentar», que
// con conexión abre la app nueva. Con el SW nuevo activo, la app nueva funciona sin conexión: la
// portada, Jornada y el buscador de Explorar, con los datos precacheados.
// Después, un segundo escenario: un despliegue de código sobre el SW de la propia rama (codeDeploy).
// En los dos, ni la app nueva ni su SW piden los datos retirados. Y un tercero:
// sin conexión tras una subida de datos del bot, los escudos ya vistos siguen ahí (dataDeploy).
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer, findChrome } from './render-smoke.mjs';
import { takeOver, waitForAsync } from './browser-wait.mjs';
import { fixture } from './fixtures/rediseno/load.mjs';
import { alevinRaw, dataFile } from './fixtures/rediseno/simulate.mjs';
import { STORE_KEY } from '../../src/store.js';
import { copiaDeLaWeb } from './copia-web.mjs';

const { chromium } = createRequire(import.meta.url)('playwright');
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
// Lo que se sirve: la web del árbol y la app anterior, copiadas (se borran al acabar).
const WEB = copiaDeLaWeb('pwa-web-');
const ANTERIOR_DIR = join(ROOT, 'scripts', 'tests', 'fixtures', 'app-anterior');
const ANTERIOR = copiaDeLaWeb('pwa-anterior-', { origen: ANTERIOR_DIR, entradas: readdirSync(ANTERIOR_DIR) });
const SITE = WEB.dir;
const PREVIOUS = ANTERIOR.dir;
process.on('exit', () => { WEB.limpiar(); ANTERIOR.limpiar(); });
// La portada del rediseño, en cualquier estado, y la de la app anterior.
const HOME = 'section[data-screen="home"][data-state]';
const OLD_HOME = '.me-hero';
const read = (dir, file) => {
  const path = join(dir, file);
  return existsSync(path) && statSync(path).isFile() ? readFileSync(path, 'utf8') : null;
};
const versionOf = (sw) => sw.match(/CACHE_NAME = 'futbolbase2-v([^']+)'/)[1];
// El código que carga la página: el paquete de dist/ (scripts/codigo.py) y src/config.js, aparte.
const ORIGEN = JSON.parse(read(SITE, 'dist/origen.json'));
const OLD_VERSION = versionOf(read(PREVIOUS, 'sw.js'));
const TREE_VERSION = versionOf(read(SITE, 'sw.js'));
const PUBLISHED = '20991231a';
const oldCache = `futbolbase2-v${OLD_VERSION}`;
const expected = `futbolbase2-v${PUBLISHED}`;
const publish = (file, text) => (file === 'index.html' || file === 'sw.js' ? text.replaceAll(TREE_VERSION, PUBLISHED) : text);
const NOTICE = 'No se pudo abrir la versión nueva de la app. Comprueba la conexión y pulsa Reintentar.';
const sha8 = (text) => createHash('sha1').update(text).digest('hex').slice(0, 8);
// El sw.js servido, con las huellas de lo que sirve el servidor de la prueba (como scripts/precache.py con
// el árbol): con los datos congelados y el index.html publicado, las del árbol no casan y el SW nuevo no
// se instalaría. `contenido(ruta)` da el cuerpo que se sirve, o null si es el del árbol.
const resellar = (sw, contenido) => sw.replace(/^ {2}"([^"]+)": "[0-9a-f]{8}",$/gm, (line, ruta) => {
  const body = contenido(ruta);
  return body === null ? line : `  "${ruta}": "${sha8(body)}",`;
});
// Lo que nunca sirve la caché HTTP de antes de publicar: una URL con ?v=<versión> o ?h=<huella> (las del
// precache del SW nuevo), que no estaba antes, o una petición con Cache-Control: no-cache (la página que el
// SW nuevo pide a la red, sin query: el navegador la revalida).
const fresca = (url, req) => url.searchParams.has('v') || url.searchParams.has('h') || /no-cache/.test(req.headers['cache-control'] || '');

// Los datos y la configuración de las dos versiones, congelados: las
// fixtures, el día de los datos de hoy (23/09/2026), y el config.js de la app anterior (2025/26,
// con Las Mesas en PG2). Lo que las fixtures no traen, vacío: las temporadas archivadas, que el SW
// anterior precachea todas, las fichas de jugadores, que la app anterior pide para su portada, y las
// actas de temporada entera de otra temporada, que pedía la app anterior. Las actas de un grupo sin
// fixture, un 404 (sin actas), como en la web.
const js = (pairs) => ({ type: 'text/javascript', body: pairs.map(([name, value]) => `const ${name}=${JSON.stringify(value)};`).join('\n') + '\n' });
const FROZEN = (() => {
  const raw = fixture('current-2025-2026');
  const past = fixture('historical-2024-2025');
  const cups = fixture('cups-2025-2026');
  return {
    'src/config.js': { type: 'text/javascript', body: read(PREVIOUS, 'src/config.js') },
    'data-benjamin.js': js([['BENJAMIN', raw.benjamin]]),
    'data-prebenjamin.js': js([['PREBENJAMIN', raw.prebenjamin]]),
    'data-history.js': js([['HISTORY', raw.history]]),
    'data-goleadores.js': js([['GOL_BENJ', []], ['GOL_PREBENJ', []]]),
    'data-shields.js': js([['SHIELDS', fixture('shields')]]),
    'data-seasons.js': js([['SEASONS', [{ name: '2025-2026', current: true, detail: true }, { name: '2024-2025', current: false }]]]),
    'data-maspalomas-cup-2026.js': js([['MASPALOMAS_CUP_BENJAMIN', cups.benjamin], ['MASPALOMAS_CUP_PREBENJAMIN', cups.prebenjamin]]),
    'data-season-2024-2025.js': js([['SEASON_2024_2025', { name: '2024-2025', current: false, benjamin: past.benjamin, prebenjamin: past.prebenjamin }]]),
    'data-matchdetail.js': js([['MATCH_DETAIL', fixture('matchdetail')]]),
    // Las actas: de temporada entera para la app anterior y, para la nueva, por grupo (las de A1).
    'data-lineups-2025-2026.js': js([['LINEUPS_2025_2026', fixture('lineups-2025-2026')]]),
    'data-lineups-2025-2026-A1.js': js([['LINEUPS_2025_2026_A1', fixture('lineups-2025-2026')]]),
    'data-health.json': { type: 'application/json', body: JSON.stringify(fixture('health')) },
    // El alevín (contrato común de alevín, punto 4): perezoso, fuera de index.html; el SW nuevo lo guarda
    // al instalarse (opcional del precache) y Explorar lo enseña sin conexión. La app anterior nunca lo pide.
    'data-alevin.js': { type: 'text/javascript', body: dataFile(alevinRaw({ season: '2025-2026', today: '2026-09-23' })) },
    // Solo para la app anterior: su index.html los nombra y su SW los precachea (la web nueva ya no los usa).
    'data-matchdetail-keys.js': js([['MATCH_DETAIL_KEYS', {}]]),
    'data-stats.js': js([['STATS', {}]]),
  };
})();
function frozen(file) {
  if (Object.hasOwn(FROZEN, file)) return FROZEN[file];
  const [, kind, from, to] = file.match(/^data-(season|players|lineups)-(\d{4})-(\d{4})\.js$/) || [];
  if (kind === 'season') return js([[`SEASON_${from}_${to}`, { name: `${from}-${to}`, current: false, benjamin: [], prebenjamin: [] }]]);
  if (kind === 'players') return js([[`PLAYERS_${from}_${to}`, {}], [`TEAMS_${from}_${to}`, {}]]);
  if (kind === 'lineups') return js([[`LINEUPS_${from}_${to}`, {}]]);
  return null;
}
// Las actas de un grupo sin fixture: un 404 esperado (el grupo no tiene actas), como en Pages; la
// portada pide las de mi equipo tras pintarse (fillSquad), y las de PG2 no existen.
const NO_LINEUPS = /^data-lineups-\d{4}-\d{4}-[A-Za-z0-9]+\.js$/;

// Los datos retirados. Solo los pide la app anterior (su index.html los
// nombra, su SW los precachea y su portada pide las fichas de jugadores), y el mundo se los sigue
// sirviendo; la app nueva y su SW, nunca. Cada petición se apunta con su ?v=: las del SW nuevo, y las
// de la app nueva con él al mando, llevan la versión publicada.
const RETIRED = /^data-(matchdetail-keys|stats|players-\d{4}-\d{4})\.js$/;
const retiredAsked = [];

// De qué versión es lo que sirvió una apertura: la anterior, la nueva, igual en las dos o ninguna.
function generation(file, body) {
  const data = frozen(file);
  if (data) return body === data.body ? 'igual' : 'ninguna';
  const before = read(PREVIOUS, file);
  const now = read(SITE, file);
  const after = now === null ? null : publish(file, now);
  if (body === before && body === after) return 'igual';
  if (body === after) return 'nueva';
  if (body === before) return 'anterior';
  return 'ninguna';
}

const upstream = await startServer(SITE);
let phase = 'anterior';
let release;
const precacheHeld = new Promise((resolve) => { release = resolve; });
const failing = new Set();   // actualizaciones en segundo plano del SW anterior que fallan
const proxy = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://portal.test');
  const file = decodeURIComponent(url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
  if (RETIRED.test(file)) retiredAsked.push(`${file}?v=${url.searchParams.get('v')}`);
  const fromWorker = req.headers['sec-fetch-dest'] === 'empty';
  const isConfig = file === 'src/config.js';
  const isDocument = file === 'index.html';
  const cacheControl = isConfig || isDocument ? 'public, max-age=3600' : 'no-store';
  try {
    if (phase === 'nueva') {
      // El precache del SW nuevo (con la ?v= publicada, o con ?h=) espera a que la prueba lo suelte.
      if (fromWorker && (url.searchParams.get('v') === PUBLISHED || url.searchParams.has('h'))) await precacheHeld;
      // La actualización en segundo plano del SW anterior (con su ?v=) de un módulo que falla.
      if (fromWorker && url.searchParams.get('v') === OLD_VERSION && failing.has(file)) {
        res.writeHead(503, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' });
        res.end('no disponible');
        return;
      }
    }
    // Datos y config.js, congelados y los mismos en las dos versiones; ningún data-* vivo.
    const data = frozen(file);
    if (data || file.startsWith('data-')) {
      if (!data && !NO_LINEUPS.test(file)) console.error('PWA fixture HTTP 404 (sin dato congelado)', req.url);
      // Una CDN que aún guarda las URL sin ?v= de antes de publicar: el SW nuevo las pide con ?v=.
      const stale = phase === 'nueva' && isConfig && !fresca(url, req);
      res.writeHead(data ? 200 : 404, { 'Content-Type': data ? data.type : 'text/plain', 'Cache-Control': cacheControl });
      res.end(data ? data.body + (stale ? '\n// previously cached HTTP asset' : '') : 'no está congelado');
      return;
    }
    if (phase === 'anterior') {
      const body = read(PREVIOUS, file);
      if (body !== null) {
        res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.json') ? 'application/json' : 'text/javascript', 'Cache-Control': cacheControl });
        res.end(body);
        return;
      }
    }
    const response = await fetch(`http://127.0.0.1:${upstream.address().port}${req.url}`);
    // Los módulos de la app anterior ya no existen: su SW los pide en segundo plano y le dan 404.
    const expectedGone = phase === 'nueva' && fromWorker && read(PREVIOUS, file) !== null && read(SITE, file) === null;
    if (!response.ok && !expectedGone) console.error('PWA fixture HTTP', response.status, req.url);
    let body = Buffer.from(await response.arrayBuffer());
    if (phase === 'nueva' && response.ok) {
      let text = publish(file, body.toString());
      if (file === 'sw.js') {
        text += "\nself.addEventListener('message', e => e.ports[0]?.postMessage(CACHE_NAME));";
        text = resellar(text, (ruta) => frozen(ruta)?.body ?? (ruta === 'index.html' ? publish(ruta, read(SITE, ruta)) : null));
      }
      // Una CDN que aún guarda las URL sin ?v= de antes de publicar: el SW nuevo las pide con ?v= o ?h=.
      if (isDocument && !fresca(url, req)) text += '\n<!-- previously cached HTTP document -->';
      if (file === 'sw.js' || file === 'index.html') body = Buffer.from(text);
    }
    res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'text/plain', 'Cache-Control': cacheControl });
    res.end(body);
  } catch {
    res.writeHead(500);
    res.end();
  }
});
await new Promise((resolve) => proxy.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${proxy.address().port}/index.html`;

// ── 2. Despliegue de código sobre el SW de la rama ──
// La versión «a» es el árbol publicado como 20991231a, instalada y con su SW al mando. Se publica «b»
// (20991231b) con otro paquete en dist/, como lo dejaría scripts/codigo.py: el módulo marca la página
// (data-codigo="b"), la hoja lleva una marca (--version-codigo: "b"), los dos con su huella nueva en el
// nombre. El SW de «a» pide la página a la red primero y sirve lo suyo del precache:
//  - la instalación del SW de «b» (sus peticiones con ?h=) queda retenida hasta el final;
//  - 1.ª y 2.ª aperturas: «b» entera (las marcas del módulo y de la hoja, Explorar, sin el aviso del
//    arranque ni errores): el index.html de «b», de la red, pide el paquete de «b», también a la red;
//  - 3.ª, sin conexión (el servidor corta las conexiones): «a» entera, la que el SW de «a» instaló;
//  - se suelta la instalación: el SW de «b» toma el mando y borra la caché de «a», y la app es «b» entera.
// Los datos, los congelados de arriba (FROZEN), y el código sin caché HTTP (no-store): determinista.
const CODE_A = '20991231a';
const CODE_B = '20991231b';
const MARK = '--version-codigo';
// El paquete de «b»: el del árbol con sus marcas, con la huella de su contenido en el nombre.
const BUNDLE_B = (() => {
  const app = `${read(SITE, ORIGEN.app)}\ndocument.documentElement.dataset.codigo = 'b';\n`;
  const css = `${read(SITE, ORIGEN.css)}\n:root{${MARK}:"b"}\n`;
  return { [`dist/app-${sha8(app)}.js`]: app, [`dist/acta-${sha8(css)}.css`]: css };
})();
const [APP_B, CSS_B] = Object.keys(BUNDLE_B);
// La espera del SW nuevo sin ninguna página de la app abierta, takeOver, está en browser-wait.mjs: la
// comparte aislamiento-smoke.mjs.

async function codeDeploy(browser) {
  let phase = 'a';
  let down = false;          // sin conexión: el servidor corta cada conexión
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  // Para el diagnóstico si el SW de «b» no llega a mandar: cada petición al llegar y al acabar, y las
  // que siguen sin respuesta (ms desde el inicio del escenario).
  const started = Date.now();
  const requests = [];
  const pending = new Map();
  let lastRequest = 0;
  const retired = [];        // las peticiones de datos retirados: ninguna, las dos versiones son la app nueva
  // El código de cada versión: el del árbol con sus marcas y, en «b», su paquete en index.html y sw.js.
  const code = (file) => {
    if (phase === 'b' && Object.hasOwn(BUNDLE_B, file)) return BUNDLE_B[file];
    if (!(file === 'index.html' || file === 'sw.js' || /^dist\/[^/]+\.(?:js|css)$/.test(file) || /^src\/[^/]+\.js$/.test(file))) return null;
    let text = read(SITE, file);
    if (text === null) return null;
    if (file === 'index.html' || file === 'sw.js') text = text.replaceAll(TREE_VERSION, phase === 'a' ? CODE_A : CODE_B);
    if (phase === 'b' && (file === 'index.html' || file === 'sw.js')) {
      text = text.replaceAll(ORIGEN.app, APP_B).replaceAll(ORIGEN.css, CSS_B);
    }
    return text;
  };
  const server = createServer(async (req, res) => {
    const id = ++lastRequest;
    const dest = req.headers['sec-fetch-dest'] || '-';
    pending.set(id, `${Date.now() - started}ms ${dest} ${req.url}`);
    requests.push(`${Date.now() - started}ms → ${dest} ${req.url}${down ? ' (sin conexión)' : ''}`);
    res.on('close', () => {
      pending.delete(id);
      requests.push(`${Date.now() - started}ms ← ${res.headersSent ? res.statusCode : 'cortada'} ${req.url}`);
    });
    const url = new URL(req.url, 'http://portal.test');
    const file = decodeURIComponent(url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    if (RETIRED.test(file)) retired.push(req.url);
    if (down) { req.socket.destroy(); return; }
    const fromWorker = req.headers['sec-fetch-dest'] === 'empty';
    const v = url.searchParams.get('v');
    try {
      // Solo la instalación de «b» (?h=): con la ?v= de «b», el SW de «a» pide a la red los datos de la página
      // de «b», que no se pueden retener.
      if (fromWorker && phase === 'b' && url.searchParams.has('h')) await held;
      const data = frozen(file);
      if (data || file.startsWith('data-')) {
        if (!data && !NO_LINEUPS.test(file)) console.error('PWA fixture HTTP 404 (sin dato congelado)', req.url);
        res.writeHead(data ? 200 : 404, { 'Content-Type': data ? data.type : 'text/plain', 'Cache-Control': 'no-store' });
        res.end(data ? data.body : 'no está congelado');
        return;
      }
      let text = code(file);
      if (file === 'sw.js' && text !== null) text = resellar(text, (ruta) => frozen(ruta)?.body ?? code(ruta));
      if (text !== null) {
        const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : 'text/javascript';
        res.writeHead(200, { 'Content-Type': `${type}; charset=utf-8`, 'Cache-Control': 'no-store' });
        res.end(text);
        return;
      }
      const response = await fetch(`http://127.0.0.1:${upstream.address().port}${req.url}`);
      res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'text/plain', 'Cache-Control': 'no-store' });
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch {
      res.writeHead(500);
      res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const home = `http://127.0.0.1:${server.address().port}/index.html`;
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES', timezoneId: 'Atlantic/Canary' });
  // Una apertura: una página nueva, que carga la app entera; lo que se ve y los errores del arranque.
  const open = async (label, hash = '#/explorar') => {
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => { if (message.type() === 'error' && message.text().startsWith('[arranque]')) errors.push(message.text().split('\n')[0]); });
    await page.goto(home + hash);
    await waitForAsync(page, () => !!document.querySelector('#contenido section[data-screen], #contenido [role="alert"]'), null, { label });
    const look = await page.evaluate((mark) => ({
      screen: document.querySelector('#contenido section[data-screen]')?.getAttribute('data-screen') ?? null,
      alert: !!document.querySelector('#contenido [role="alert"]'),
      marca: getComputedStyle(document.documentElement).getPropertyValue(mark).trim(),
      codigo: document.documentElement.dataset.codigo ?? '',
    }), MARK);
    return { page, seen: { ...look, errores: errors } };
  };
  const whole = (label, seen, marca) => assert.deepEqual(seen, { screen: 'explorar', alert: false, marca, codigo: marca ? 'b' : '', errores: [] },
    `despliegue de código, ${label}: ${JSON.stringify(seen)}`);
  try {
    // «a» instalada: su SW al mando (clients.claim) y su precache, sin volver a cargar la página: así
    // ninguna revalidación de «a» queda pendiente cuando se publica «b».
    let o = await open('despliegue de código, «a»', '#/');
    await waitForAsync(o.page, (name) => caches.keys().then((keys) => keys.includes(name) && !!navigator.serviceWorker.controller),
      `futbolbase2-v${CODE_A}`, { label: 'despliegue de código, «a» instalada' });
    await o.page.close();
    // Se publica «b». 1.ª apertura: «b» entera, de la red. El SW de «a» pide la página a la red primero y su
    // paquete (otra URL, que «a» no tiene) también; y no guarda nada de «b»: lo guarda la instalación de «b».
    phase = 'b';
    o = await open('despliegue de código, 1.ª apertura');
    whole('1.ª apertura, «b» entera, de la red', o.seen, '"b"');
    const guardaB = await o.page.evaluate(async (bodies) => {
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          if (bodies.includes(await (await cache.match(request)).text())) return `${name}: ${request.url}`;
        }
      }
      return null;
    }, [code('index.html'), ...Object.values(BUNDLE_B)]);
    assert.equal(guardaB, null, 'despliegue de código, 1.ª apertura: el SW de «a» guarda la página o el paquete de «b»');
    await o.page.close();
    // 2.ª apertura, con el SW de «a» al mando: «b» entera.
    o = await open('despliegue de código, 2.ª apertura');
    whole('2.ª apertura, «b» entera', o.seen, '"b"');
    await o.page.close();
    // 3.ª, sin conexión, con el SW de «a» al mando (el de «b», retenido): el index.html que instaló «a», con lo
    // suyo: «a» entera, hasta que «b» esté instalado entero.
    down = true;
    o = await open('despliegue de código, 3.ª apertura sin conexión');
    whole('3.ª apertura sin conexión, «a» entera', o.seen, '');
    await o.page.close();
    down = false;
    // Se suelta la instalación del SW de «b»: toma el mando y borra la caché de «a».
    //  - Si una página abierta le pide algo al SW de «a» justo cuando «b» queda instalado, Chrome, con la
    //    herramienta de pruebas conectada a los SW (Playwright), vuelve a arrancar el de «a» y no activa
    //    «b» (skipWaiting) mientras esa página siga abierta. En CI le pasaba a la página de espera con su
    //    favicon.ico, en 1 de cada 3 pasadas; en local, con la petición lanzada a propósito, 3 de 3, con
    //    Chrome 150 y con 153. Sin DevTools en los SW no pasa (0 de 30): no lo ven los usuarios. Y en
    //    cualquier caso cada apertura es entera de una versión (CODIGO).
    //  - Así que la carrera se provoca a propósito, con una página que se cierra después, y se espera
    //    como quien abre la app y la cierra: una página nueva en cada vuelta, que se cierra en seguida.
    //  - La página es manifest.json, que el SW sirve de la red sin guardar nada: ninguna revalidación
    //    del SW de «a» toca su caché mientras «b» se activa. Y, como la comprobación de la
    //    publicación, se pide la actualización en cada vuelta.
    // Si no llega, el error dice cómo quedó: los SW en cada vuelta, las peticiones sin respuesta y las
    // del servidor desde que se soltó.
    const releasedAt = requests.length;
    release();
    const probeUrl = home.replace(/index\.html$/, 'manifest.json');
    const racer = await context.newPage();
    await racer.goto(probeUrl);
    await racer.evaluate(() => new Promise((resolve) => {
      const race = () => {
        for (let i = 0; i < 3; i += 1) setTimeout(() => fetch(`favicon.ico?carrera=${i}`).catch(() => {}), i * 5);
        setTimeout(resolve, 1000);
      };
      navigator.serviceWorker.getRegistration().then((registration) => {
        if (registration?.waiting) race();
        else if (registration?.installing) registration.installing.addEventListener('statechange', (event) => { if (event.target.state === 'installed') race(); });
        else resolve();
      });
    }));
    await racer.close();
    await takeOver(context, probeUrl, `futbolbase2-v${CODE_B}`, 'despliegue de código, el SW de «b» al mando', () => {
      // Sin las comprobaciones de sw.js de cada vuelta, que taparían el resto.
      const since = requests.slice(releasedAt);
      const others = since.filter((line) => !line.endsWith(' /sw.js'));
      return `\nsin respuesta (${pending.size}): ${JSON.stringify([...pending.values()])}\n`
        + `peticiones desde que se soltó «b» (y ${(since.length - others.length) / 2} comprobaciones de sw.js):\n  ${others.slice(0, 150).join('\n  ')}`;
    });
    // Con el SW de «b» al mando desde la navegación: «b» entera.
    o = await open('despliegue de código, con el SW de «b»');
    whole('con el SW de «b»', o.seen, '"b"');
    await o.page.close();
    assert.deepEqual(retired, [], 'despliegue de código: la app nueva pide datos retirados (decisión 3 de B4)');
    console.log('PASS: despliegue de código sobre el SW de la rama: con conexión, la 1.ª y la 2.ª aperturas son la nueva entera, de la red (su paquete y su hoja, sin el aviso del arranque); sin conexión, la anterior entera, la instalada; con el SW nuevo, la nueva, y sin pedir datos retirados');
  } finally {
    release();
    await context.close();
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
}

// ── 3. Sin conexión tras una subida de datos del bot ───────────────────────
// Cada subida de datos del bot cambia CACHE_NAME, y el SW nuevo, al activarse, borra la caché anterior.
// Los escudos se guardan según se usan (cache-first) y van aparte, en CRESTS_CACHE, con el sello de
// escudos/, que solo cambia con un escudo: si fueran en la caché de los datos, se irían con ella y la
// primera apertura sin red tras cada subida pintaría monogramas:
//  - «a» (el árbol publicado como 20991231a) instalada, y una apertura de la ficha de Unión Viera (A1)
//    con su SW al mando, que guarda sus escudos;
//  - se publica «b», solo datos (sube CACHE_NAME; escudos/ igual): su SW toma el mando (takeOver) y
//    borra la caché de «a». Sin conexión, la ficha pinta los mismos escudos, en miniatura, y ningún
//    monograma más; la caché de los escudos es la misma. Y su plantilla: las actas de su grupo, que el
//    SW de «b» vuelve a bajar al instalarse porque estaban en la caché de «a» (lineupsToCarry); sin
//    ellas, la caja de error. Y Mi equipo con Unión Viera guardado, sin conexión: la plantilla de la
//    portada (fillSquad), con esas mismas actas;
//  - se publica «c», con el escudo de Unión Viera cambiado y su sello nuevo, como lo dejaría
//    build_crests.py: su SW borra la caché de escudos anterior, y la apertura siguiente guarda el escudo
//    nuevo en la nueva.
// Los datos, los congelados (FROZEN); el código y los escudos, los del árbol; sin caché HTTP (no-store).
const DATA = { a: '20991231a', b: '20991231b', c: '20991231c' };
const FICHA = '#/equipo?s=2025-2026&g=A1&t=Uni%C3%B3n%20Viera';
const CHANGED = 'escudos/s/unionviera.png';   // el escudo que cambia en «c»
const REPLACEMENT = 'escudos/s/huracan.png';  // lo que sirve «c» en su lugar
const NEW_SEAL = 'c0c0c0c0';
async function dataDeploy(browser) {
  let phase = 'a';
  let down = false;          // sin conexión: el servidor corta cada conexión
  const treeCrests = (read(SITE, 'sw.js').match(/^const CRESTS_CACHE = '(futbolbase2-escudos-[0-9a-f]{8})';$/m) || [])[1];
  assert.notEqual(treeCrests, `futbolbase2-escudos-${NEW_SEAL}`);
  assert.notEqual(statSync(join(SITE, CHANGED)).size, statSync(join(SITE, REPLACEMENT)).size);
  const server = createServer(async (req, res) => {
    if (down) { req.socket.destroy(); return; }
    const url = new URL(req.url, 'http://portal.test');
    const file = decodeURIComponent(url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
    try {
      const data = frozen(file);
      if (data || file.startsWith('data-')) {
        if (!data && !NO_LINEUPS.test(file)) console.error('PWA fixture HTTP 404 (sin dato congelado)', req.url);
        res.writeHead(data ? 200 : 404, { 'Content-Type': data ? data.type : 'text/plain', 'Cache-Control': 'no-store' });
        res.end(data ? data.body : 'no está congelado');
        return;
      }
      if (file === 'index.html' || file === 'sw.js') {
        let text = read(SITE, file).replaceAll(TREE_VERSION, DATA[phase]);
        if (file === 'sw.js' && phase === 'c') text = text.replace(/futbolbase2-escudos-[0-9a-f]{8}/, `futbolbase2-escudos-${NEW_SEAL}`);
        if (file === 'sw.js') {
          text = resellar(text, (ruta) => frozen(ruta)?.body ?? (ruta === 'index.html' ? read(SITE, ruta).replaceAll(TREE_VERSION, DATA[phase]) : null));
        }
        res.writeHead(200, { 'Content-Type': `${file === 'sw.js' ? 'text/javascript' : 'text/html'}; charset=utf-8`, 'Cache-Control': 'no-store' });
        res.end(text);
        return;
      }
      const source = phase === 'c' && file === CHANGED ? `/${REPLACEMENT}` : req.url;
      const response = await fetch(`http://127.0.0.1:${upstream.address().port}${source}`);
      res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') || 'text/plain', 'Cache-Control': 'no-store' });
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch {
      res.writeHead(500);
      res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const home = `http://127.0.0.1:${server.address().port}/index.html`;
  const probeUrl = home.replace(/index\.html$/, 'manifest.json');
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES', timezoneId: 'Atlantic/Canary' });
  // El reloj de las páginas, el día de los datos congelados (23/09/2026): la ficha es la misma cada día.
  await context.clock.setFixedTime(new Date('2026-09-23T12:00:00Z'));
  // Una apertura de la ficha en una página nueva, y sus escudos: también los diferidos (loading="lazy"),
  // que se piden ya para que la cuenta no dependa del alto de la ventana; cuando cada <img> ha cargado o,
  // si no pudo, ha pasado a monograma (crestFallback: la miniatura, el original y el monograma). Y si
  // pinta la tabla de su plantilla.
  const open = async (label) => {
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(home + FICHA);
    await waitForAsync(page, () => !!document.querySelector('#contenido section[data-screen], #contenido [role="alert"]'), null, { label });
    await page.evaluate(() => document.querySelectorAll('#contenido img.crest[loading="lazy"]').forEach((img) => { img.loading = 'eager'; }));
    await waitForAsync(page, () => [...document.querySelectorAll('#contenido img.crest')].every((img) => img.complete && img.naturalWidth > 0),
      null, { label: `${label}, sus escudos` });
    const seen = await page.evaluate(() => {
      const imgs = [...document.querySelectorAll('#contenido img.crest')];
      const mini = imgs.filter((img) => new URL(img.currentSrc).pathname.startsWith('/escudos/s/')).length;
      return { screen: document.querySelector('#contenido section[data-screen]')?.getAttribute('data-screen') ?? null,
        mini, orig: imgs.length - mini, mono: document.querySelectorAll('#contenido .mono').length,
        plantilla: !!document.querySelector('#contenido table.squad') };
    });
    return { page, seen: { ...seen, errores: errors } };
  };
  try {
    // «a» instalada: la 1.ª apertura registra su SW, que toma el mando (clients.claim) con su precache.
    let o = await open('sin conexión tras una subida de datos, «a»');
    await waitForAsync(o.page, (name) => caches.keys().then((keys) => keys.includes(name) && !!navigator.serviceWorker.controller),
      `futbolbase2-v${DATA.a}`, { label: 'sin conexión tras una subida de datos, «a» instalada' });
    await o.page.close();
    // Con el SW de «a» al mando, la ficha le pide sus escudos, y él los guarda.
    o = await open('sin conexión tras una subida de datos, «a» con su SW');
    const online = o.seen;
    assert.ok(online.screen === 'equipo' && online.plantilla && online.mini > 0 && online.orig === 0 && online.errores.length === 0,
      `sin conexión tras una subida de datos, «a» con su SW: ${JSON.stringify(online)}`);
    await o.page.close();
    // Se publica «b», solo datos: su SW toma el mando y borra la caché de «a».
    phase = 'b';
    let seen = await takeOver(context, probeUrl, `futbolbase2-v${DATA.b}`, 'sin conexión tras una subida de datos, el SW de «b» al mando');
    // Sin conexión, la misma ficha: los mismos escudos, en miniatura, y su plantilla.
    down = true;
    o = await open('sin conexión tras una subida de datos, «b» sin conexión');
    assert.deepEqual(o.seen, online, 'sin conexión tras una subida de datos, la ficha no pinta lo mismo que con conexión');
    await o.page.close();
    // Mi equipo, sin conexión, con Unión Viera (A1) guardado: la plantilla de la portada, con las actas
    // que el SW de «b» heredó. Desde aquí, cada página nueva lo tiene guardado.
    await context.addInitScript(([key, value]) => {
      try { localStorage.setItem(key, value); } catch { /* almacén bloqueado */ }
    }, [STORE_KEY, JSON.stringify({ myTeam: { name: 'Unión Viera', season: '2025-2026', cat: 'benjamin', groupId: 'A1' }, recent: [] })]);
    const mine = await context.newPage();
    mine.setDefaultTimeout(20000);
    const mineErrors = [];
    mine.on('pageerror', (error) => mineErrors.push(error.message));
    await mine.goto(`${home}#/`);
    await mine.locator(`#contenido ${HOME}`).waitFor();
    assert.equal(await mine.locator('#contenido h1').textContent(), 'Unión Viera', 'sin conexión tras una subida de datos, Mi equipo es Unión Viera');
    await waitForAsync(mine, () => !document.querySelector('#contenido [data-slot]'), null, { label: 'sin conexión tras una subida de datos, la plantilla de Mi equipo' });
    assert.equal(await mine.locator('#plantilla table.squad').count(), 1, 'sin conexión tras una subida de datos, Mi equipo sin su plantilla');
    assert.deepEqual(mineErrors, [], 'sin conexión tras una subida de datos, Mi equipo: sin errores de JavaScript');
    await mine.close();
    down = false;
    assert.deepEqual(seen.caches.filter((name) => name.startsWith('futbolbase2-escudos-')), [treeCrests],
      `la caché de los escudos, tras una subida de datos: ${JSON.stringify(seen.caches)}`);
    // Se publica «c», con un escudo cambiado y su sello nuevo: su SW borra la caché de escudos anterior...
    phase = 'c';
    seen = await takeOver(context, probeUrl, `futbolbase2-v${DATA.c}`, 'un escudo cambiado, el SW de «c» al mando');
    assert.deepEqual(seen.caches.filter((name) => name.startsWith('futbolbase2-escudos-')), [],
      `con un escudo cambiado, la caché de escudos anterior sigue ahí: ${JSON.stringify(seen.caches)}`);
    // ... y la apertura siguiente guarda el escudo nuevo en la caché nueva.
    o = await open('un escudo cambiado, «c»');
    await waitForAsync(o.page, async ([name, path, size]) => {
      const response = await (await caches.open(name)).match(path);
      return !!response && (await response.arrayBuffer()).byteLength === size;
    }, [`futbolbase2-escudos-${NEW_SEAL}`, `./${CHANGED}`, statSync(join(SITE, REPLACEMENT)).size], { label: 'un escudo cambiado, el nuevo en la caché nueva' });
    await o.page.close();
    console.log(`PASS: sin conexión tras una subida de datos: la ficha pinta sus ${online.mini} escudos en miniatura, como con conexión, porque su caché (${treeCrests}) no cambia con CACHE_NAME, y su plantilla y la de Mi equipo con Unión Viera, con las actas de A1 que el SW nuevo heredó de la caché anterior; con un escudo cambiado, su sello nuevo da otra caché, con el escudo nuevo`);
  } finally {
    await context.close();
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
}

let browser;
try {
  browser = await chromium.launch({ executablePath: findChrome(), headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES', timezoneId: 'Atlantic/Canary' });
  // La app anterior pide sus fuentes a Google: fuera de la prueba.
  await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort());
  context.on('console', (message) => { if (message.text().includes('[SW]')) console.log(message.text()); });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  // Lo que sirve cada apertura (documento, hojas y módulos de src/ y de dist/), con su versión.
  let served = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.origin !== new URL(base).origin || !/^\/(index\.html)?$|\.css$|^\/(?:src|dist)\/.+\.js$/.test(url.pathname)) return;
    const file = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.slice(1));
    served.push(response.text().then((body) => ({ file, generation: generation(file, body) }), () => ({ file, generation: 'sin cuerpo' })));
  });
  const opening = async (label, wanted) => {
    const seen = await Promise.all(served);
    served = [];
    const byGeneration = {};
    for (const { file, generation: g } of seen) (byGeneration[g] ||= []).push(file);
    const other = wanted === 'nueva' ? 'anterior' : 'nueva';
    assert.ok(seen.some(({ file }) => file === 'index.html'), `${label}: no llegó el documento`);
    assert.ok(seen.some(({ file }) => file.endsWith('.css')), `${label}: no llegó ninguna hoja`);
    for (const g of [other, 'ninguna', 'sin cuerpo']) {
      assert.deepEqual(byGeneration[g] || [], [], `${label}: la versión ${wanted} con ficheros de «${g}»`);
    }
    assert.deepEqual(errors, [], `${label}: errores de JavaScript`);
  };

  // 1. La app anterior instalada: su SW controla la página y tiene su precache.
  await page.goto(base);
  await page.locator(OLD_HOME).waitFor();
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  await page.locator(OLD_HOME).waitFor();
  await waitForAsync(page, (name) => caches.keys().then((keys) => keys.includes(name) && !!navigator.serviceWorker.controller), oldCache);
  served = [];

  // 2. Se publica el rediseño. En la 1.ª apertura, la actualización en segundo plano de app.js y
  // state.js falla: su caché se queda con los viejos, aunque ya guarde el index.html nuevo.
  phase = 'nueva';
  failing.add('src/app.js');
  failing.add('src/state.js');
  await page.reload();
  await page.locator(OLD_HOME).waitFor();
  await opening('1.ª apertura', 'anterior');
  await waitForAsync(page, (name) => caches.open(name).then((cache) => cache.match('./index.html'))
    .then((response) => (response ? response.text() : '')).then((text) => text.includes('id="contenido"')), oldCache);
  failing.clear();

  // 3. Sin conexión, con el SW anterior al mando y el index.html nuevo en su caché, que no tiene ni
  // la hoja ni el paquete nuevos: el aviso con «Reintentar», nunca «Cargando…» sin más.
  await context.setOffline(true);
  await page.reload();
  const notice = page.locator('#contenido [role="alert"]');
  await notice.waitFor();
  assert.equal((await notice.locator('p').textContent()).trim(), NOTICE);
  const retry = notice.getByRole('button', { name: 'Reintentar' });
  assert.ok((await retry.boundingBox()).height >= 44, '«Reintentar» mide al menos 44 px');
  assert.equal(await page.locator(`${HOME}, ${OLD_HOME}, [data-skeleton]`).count(), 0, 'sin conexión: ni una portada ni el esqueleto');
  assert.deepEqual(errors, [], 'sin conexión: errores de JavaScript');
  served = [];

  // 4. Con conexión, «Reintentar» abre la app nueva (2.ª apertura), y recargar, la 3.ª; con el SW
  // anterior todavía al mando: la app nueva entera, con su hoja de dist/.
  await context.setOffline(false);
  for (const [label, open] of [['2.ª apertura, con «Reintentar»', () => retry.click()], ['3.ª apertura', () => page.reload()]]) {
    await open();
    await page.locator(HOME).waitFor();
    await opening(label, 'nueva');
    assert.ok(await page.evaluate((name) => caches.keys().then((keys) => keys.includes(name)), oldCache), `${label}: el SW anterior ya no manda`);
    const look = await page.evaluate(() => ({
      sheets: [...document.styleSheets].map((sheet) => new URL(sheet.href || location.href).pathname),
      font: getComputedStyle(document.body).fontFamily.split(',')[0].replace(/["']/g, ''),
      bar: getComputedStyle(document.querySelector('.tabbar')).position,
    }));
    assert.deepEqual(look, { sheets: [`/${ORIGEN.css}`], font: 'Public Sans', bar: 'fixed' }, label);
  }

  // 5. El SW nuevo termina de instalarse, borra la caché anterior y toma el mando.
  release();
  await waitForAsync(page, ({ expected, oldCache }) => caches.keys().then((keys) => keys.includes(expected) && !keys.includes(oldCache)), { expected, oldCache });
  await waitForAsync(page, async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return registration?.active?.state === 'activated' && navigator.serviceWorker.controller === registration.active;
  });
  await waitForAsync(page, (expected) => new Promise((resolve) => {
    const channel = new MessageChannel();
    channel.port1.onmessage = (event) => resolve(event.data === expected);
    navigator.serviceWorker.controller?.postMessage('version', [channel.port2]);
    setTimeout(() => resolve(false), 500);
  }), expected);
  await page.reload();
  await page.locator(HOME).waitFor();
  await opening('con el SW nuevo', 'nueva');
  // Lo instalado va en futbolbase2-precache, con clave <ruta>?h=<huella> (antes, en CACHE_NAME sin query).
  const config = await page.evaluate(async () => {
    const response = await (await caches.open('futbolbase2-precache')).match('./src/config.js', { ignoreSearch: true });
    return response ? response.text() : null;
  });
  assert.ok(config && config.includes('export const PORTAL'), 'config.js precacheado');
  assert.ok(!config.includes('previously cached HTTP asset'), 'the new PWA must bypass HTTP entries cached before publication');
  assert.ok(!(await page.content()).includes('previously cached HTTP document'), 'navigation must retain the newly published HTML');
  assert.equal(await page.evaluate(async () => (await (await caches.open('futbolbase2-precache')).match('./index.html', { ignoreSearch: true }))?.status), 200);

  // 6. Sin conexión: la portada, con la fuente, los iconos y la hoja precacheados.
  await context.setOffline(true);
  await page.reload();
  await page.locator(HOME).waitFor();
  await opening('sin conexión', 'nueva');
  assert.match(await page.locator(HOME).getAttribute('data-state'), /^[ABCD]$/);
  assert.equal(await page.locator('h1').count(), 1);
  // Su plantilla, sin las actas de PG2 (no existen): sin conexión, un vacío tranquilo, nunca la caja de
  // error (fillSquad).
  await waitForAsync(page, () => !document.querySelector('#contenido [data-slot]'), null, { label: 'sin conexión, la plantilla de la portada' });
  assert.equal(await page.locator('#contenido .error-box').count(), 0, 'la portada sin conexión: sin cajas de error');
  if (await page.locator('#plantilla').count()) {
    assert.match(await page.locator('#plantilla').textContent(), /^Plantilla\s*Sin conexión/, 'la plantilla sin conexión: el vacío tranquilo');
  }
  assert.deepEqual(errors, [], 'la portada sin conexión: sin errores de JavaScript');
  const precached = await page.evaluate(async () => (await (await caches.open('futbolbase2-precache')).keys()).map((r) => new URL(r.url).pathname));
  for (const path of ['/fonts/PublicSans-latin.woff2', '/icons/icon-192.png', `/${ORIGEN.app}`, `/${ORIGEN.css}`, '/src/config.js', '/data-alevin.js']) {
    assert.ok(precached.includes(path), `${path} is not precached`);
  }
  // La cabecera avisa de que no hay conexión.
  await waitForAsync(page, () => document.querySelector('.shell-offline')?.textContent.startsWith('Sin conexión.'));
  // Jornada, por la barra, también sin conexión: su módulo y los datos inmediatos están en caché.
  await page.locator('.tabbar a.tab[href="#/jornada"]').click();
  await page.locator('#contenido section[data-screen="jornada"]').waitFor();
  assert.equal(await page.locator('#contenido section[data-screen="jornada"][data-state="error"]').count(), 0);
  assert.equal(await page.locator('#contenido h1').textContent(), 'Jornada');
  // Explorar, por la barra, también sin conexión: el buscador filtra con los datos precacheados.
  await page.locator('.tabbar a.tab[href="#/explorar"]').click();
  await page.locator('#contenido section[data-screen="explorar"]').waitFor();
  assert.equal(await page.locator('#contenido h1').textContent(), 'Explorar');
  await page.locator('#buscar').fill('hurac');
  await page.locator('#resultados a.search-result[href="#/equipo?s=2025-2026&g=PG2&t=AD%20Hurac%C3%A1n"]').waitFor();
  assert.equal(await page.locator('#contenido .error-box').count(), 0, 'Explorar sin conexión: sin cajas de error');
  // Y alevín, con data-alevin.js de la instalación (opcional del precache): sus ligas y su AD Huracán, sin el aviso.
  await page.locator('#resultados a.search-result[href="#/equipo?s=2025-2026&g=AL1&t=AD%20Hurac%C3%A1n"]').waitFor();
  assert.deepEqual(await page.locator('#contenido h3.link-head').allTextContents(), ['Benjamín', 'Prebenjamín', 'Alevín'], 'Explorar sin conexión, con alevín');
  assert.equal(await page.locator('#contenido .partial-box').count(), 0, 'Explorar sin conexión: alevín, sin aviso');
  assert.deepEqual(errors, []);
  // Los datos retirados: la app anterior los pide y el mundo se los da; ni el SW
  // nuevo ni la app nueva con él al mando piden ninguno (llevarían la versión publicada).
  assert.ok(retiredAsked.some((asked) => asked.endsWith(`?v=${OLD_VERSION}`)), `la app anterior pide sus datos: ${JSON.stringify(retiredAsked)}`);
  assert.deepEqual(retiredAsked.filter((asked) => asked.endsWith(`?v=${PUBLISHED}`)), [], 'la app nueva pide datos retirados');
  console.log(`PASS: de la app anterior (su SW real) al rediseño, con datos congelados: la 1.ª apertura es la anterior; sin conexión a medias, el aviso con «Reintentar»; la 2.ª y la 3.ª, la nueva con su paquete y su hoja de dist/; con ${expected}, la portada, Jornada y el buscador de Explorar funcionan sin conexión, y ni la app nueva ni su SW piden los datos retirados`);
  await context.close();
  await codeDeploy(browser);
  await dataDeploy(browser);
} finally {
  if (browser) await browser.close();
  proxy.closeAllConnections();
  upstream.closeAllConnections();
  await Promise.all([new Promise((resolve) => proxy.close(resolve)), new Promise((resolve) => upstream.close(resolve))]);
}
