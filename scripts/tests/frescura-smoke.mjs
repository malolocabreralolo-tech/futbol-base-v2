// Frescura: con el service worker de verdad en un Chrome de verdad, tras una subida de datos la
// primera apertura enseña los datos nuevos, una actualización a medias nunca deja la app sin abrir sin
// conexión y la página abierta se pone al día sola.
//
// Cada caso sirve su propia copia de la web, en una carpeta temporal (copia-web.mjs), como GitHub Pages
// (pages-server.mjs: gzip y max-age=600), bajo /futbol-base-v2/, con un contexto de Chrome nuevo que dura lo
// que el caso: el SW y sus cachés sobreviven a cerrar y abrir páginas (el 2 sigue en el del 1). Los datos, los del mundo D de
// fixture-site.mjs (23/09/2026, con el reloj de las páginas en ese día), escritos en la copia: la portada es
// la de Las Mesas Hu. (el equipo por defecto) y sus puntos en la clasificación del grupo, el dato visible.
// «Publicar una versión nueva» es lo que hace el bot, sin esbuild (el código no cambia): en la copia, otros
// puntos en data-prebenjamin.js y, con python3, generate_js.bump_cache_version y precache.escribir.
// «Cortar la red»: context.setOffline y, además, el servidor corta cada conexión (así no depende de si la
// emulación llega al SW).
//
//   1. Primera apertura tras publicar: el dato nuevo, sin recargar; y, cuando el SW nuevo toma el mando,
//      ni recarga ni «Hay datos nuevos» (la página ya es de su versión).
//   2. Tras el 1, sin conexión: abre con el dato nuevo.
//   3. Una versión nueva con un obligatorio en 404 (data-history.js): el SW nuevo no se instala; sin
//      conexión, la versión anterior entera.
//   4. Despliegue a medias (el data-prebenjamin.js anterior con el sw.js nuevo): sigue el SW anterior; con el
//      bueno ya servido, el dato nuevo, y sin conexión también.
//   5. Página abierta que vuelve a primer plano: en menos de 10 s, el dato nuevo, sin tocar nada.
//   6. Página en uso al llegar el SW nuevo (tocada tras volver a primer plano, mientras el SW nuevo se
//      instala): no recarga, «Hay datos nuevos»; «Actualizar» trae el dato nuevo.
//   7. Red que no contesta (ni la página ni data-health.json): la portada con lo guardado en menos de 4 s; y,
//      pasados 31 s (con la copia de la salud ya caducada y la ventana de red mala del SW también), volver a
//      Mi equipo desde Tabla pinta en menos de 1 s, y la salud se sigue pidiendo.
//   8. En cada contexto, una caché de otra app del origen (futbolbase-v1-prueba), creada al empezar, sigue
//      intacta al acabar, y todas las demás son futbolbase2-.
//   9. Página abierta que no recibe el aviso del SW nuevo al activarse (lo descarta un oyente de captura de
//      la prueba): sigue en su versión; al volver a primer plano pregunta al SW al mando y se pone al día.
//
// Una línea por caso, PASS o FAIL; sale con 1 si falla alguno. Sin Chrome, falla: esta prueba no se salta.
//   npm install --no-save --package-lock=false playwright@1.58.0
//   node scripts/tests/frescura-smoke.mjs
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findChrome } from './render-smoke.mjs';
import { labeled, waitForAsync } from './browser-wait.mjs';
import { startPagesServer } from './pages-server.mjs';
import { worldFiles } from './fixture-site.mjs';
import { copiaDeLaWeb } from './copia-web.mjs';

const { chromium } = createRequire(import.meta.url)('playwright');
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SITIO = '/futbol-base-v2/';
const HOY = new Date('2026-09-23T12:00:00Z');
const MUNDO = worldFiles('D');
const MI_EQUIPO = JSON.parse(MUNDO['src/config.js'].body.replace(/^export const PORTAL = /, '').replace(/;\s*$/, '')).defaultTeam;
const PUNTOS = '#contenido tr.is-mine td.st-pts';
const AJENA = 'futbolbase-v1-prueba';
// Las versiones, con la forma del bot y siempre más nuevas que la de la copia: no dependen del día ni del
// árbol (la página solo se pone al día con una más nueva que la suya).
const V0 = '20991230';
const versionN = (n) => `20991231${'abcdefgh'[n - 1]}`;

// data-prebenjamin.js del mundo con `puntos` en la fila de mi equipo (no cambia el orden: siguen por
// debajo del de encima).
const PREBENJAMIN = JSON.parse(MUNDO['data-prebenjamin.js'].body.replace(/^const PREBENJAMIN=/, '').replace(/;\s*$/, ''));
const filaMia = (groups) => groups.find((g) => g.id === MI_EQUIPO.groupId).standings.find((row) => row[1] === MI_EQUIPO.name);
const PUNTOS_0 = filaMia(PREBENJAMIN)[2];
function prebenjaminCon(puntos) {
  const groups = structuredClone(PREBENJAMIN);
  filaMia(groups)[2] = puntos;
  return `const PREBENJAMIN=${JSON.stringify(groups)};\n`;
}

// Lo que hace el bot tras regenerar datos, sobre la copia: subir la versión (index.html y sw.js) y escribir
// el bloque del precache con las huellas de la copia.
const PUBLICAR_PY = `import sys
sys.path.insert(0, sys.argv[1])
import generate_js, precache
generate_js.bump_cache_version(sys.argv[2], touch_footer=False, version=sys.argv[3])
precache.escribir(sys.argv[2])
`;
function subirVersion(dir, version) {
  execFileSync('python3', ['-c', PUBLICAR_PY, join(ROOT, 'scripts'), dir, version], { stdio: ['ignore', 'pipe', 'pipe'] });
  const sw = readFileSync(join(dir, 'sw.js'), 'utf8');
  assert.match(sw, new RegExp(`^const CACHE_NAME = 'futbolbase2-v${version}';$`, 'm'), `sw.js de la copia sin la versión ${version}`);
}
// La huella de `ruta` en el bloque del precache del sw.js de la copia.
function huellaEnSw(dir, ruta) {
  const linea = readFileSync(join(dir, 'sw.js'), 'utf8').match(new RegExp(`^ {2}"${ruta.replace(/[.]/g, '\\.')}": "([0-9a-f]{8})",$`, 'm'));
  assert.ok(linea, `${ruta} no está en el precache de la copia`);
  return linea[1];
}

// assert.deepEqual con lo visto y lo esperado en el mensaje (con un mensaje propio, assert no los enseña).
function igual(visto, esperado, mensaje) {
  assert.deepEqual(visto, esperado, `${mensaje}\n  visto:    ${JSON.stringify(visto)}\n  esperado: ${JSON.stringify(esperado)}`);
}

// Espera, en Node, a una condición, con tope.
async function esperar(condicion, { timeout = 15000, label }) {
  const fin = Date.now() + timeout;
  while (!(await condicion())) {
    if (Date.now() >= fin) throw new Error(`${label}: no se cumplió en ${timeout} ms`);
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

// ── Un caso: su copia, su servidor y su contexto ─────────────────────────────────────────────────────────
async function prepararCaso(browser, nombre) {
  const web = copiaDeLaWeb('frescura-');
  let server;
  try {
    return await montarCaso(browser, nombre, web, (s) => { server = s; });
  } catch (error) {
    // Lo que alcanzó a montarse se deshace: ninguna carpeta temporal se queda.
    if (server) await server.close();
    web.limpiar();
    throw error;
  }
}

async function montarCaso(browser, nombre, web, apuntarServidor) {
  for (const [ruta, { body }] of Object.entries(MUNDO)) {
    mkdirSync(dirname(join(web.dir, ruta)), { recursive: true });
    writeFileSync(join(web.dir, ruta), body);
  }
  subirVersion(web.dir, V0);
  // Lo que hace el servidor con cada petición: `cortada`, corta la conexión; `colgar(ruta)`, no contesta
  // nunca; `falta`, un 404; `retener`, una promesa que retiene las peticiones de instalación (?h=); `cuerpo`,
  // otro contenido para una ruta. `log`: cada petición, con quién la hizo (document o empty: un SW).
  const red = { cortada: false, colgar: null, falta: new Set(), retener: null, retenidas: [], colgadas: [], cuerpo: {}, log: [] };
  const server = await startPagesServer(web.dir, {
    intercept: async ({ site, path, url, req, res }) => {
      if (site !== '/futbol-base-v2' || !url.pathname.startsWith(SITIO)) return false;
      red.log.push(`${req.headers['sec-fetch-dest'] || '-'} ${path}${url.search}${red.cortada ? ' (cortada)' : ''}`);
      if (red.cortada) { req.socket.destroy(); return true; }
      if (red.colgar?.(path)) { red.colgadas.push(path); return true; }
      if (red.retener && url.searchParams.has('h')) {
        red.retenidas.push(path);
        await red.retener;
      }
      if (red.falta.has(path)) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'max-age=600' });
        res.end('no está en el sitio');
        return true;
      }
      return false;
    },
    transform: ({ path }) => red.cuerpo[path],
  });
  apuntarServidor(server);
  const base = `${server.url.replace(/\/$/, '')}${SITIO}`;
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES', timezoneId: 'Atlantic/Canary' });
  await context.clock.setFixedTime(HOY);
  // Los avisos del SW que recibe cada página, para saber cuándo ya ha llegado el de una versión.
  await context.addInitScript(() => {
    window.__fb2Mensajes = [];
    navigator.serviceWorker?.addEventListener('message', (event) => window.__fb2Mensajes.push(event.data));
  });
  const caso = { nombre, web, red, server, base, context, versiones: 0, version: V0 };
  await crearAjena(caso);
  return caso;
}

async function cerrarCaso(caso) {
  await caso.context.close().catch(() => {});
  await caso.server.close();
  caso.web.limpiar();
}

// Publica la versión siguiente: los puntos de mi equipo y, si hace falta, otros ficheros cambiados.
function publicar(caso, puntos, otros = {}) {
  writeFileSync(join(caso.web.dir, 'data-prebenjamin.js'), prebenjaminCon(puntos));
  for (const [ruta, cuerpo] of Object.entries(otros)) writeFileSync(join(caso.web.dir, ruta), cuerpo);
  caso.versiones += 1;
  caso.version = versionN(caso.versiones);
  subirVersion(caso.web.dir, caso.version);
  return caso.version;
}

function cortarRed(caso, cortada) {
  caso.red.cortada = cortada;
  return caso.context.setOffline(cortada);
}

// ── Caso 8: la caché de otra app del origen ──────────────────────────────────────────────────────────────
// Desde una página del origen fuera del sitio (un 404, que ningún SW controla).
const fueraDelSitio = (caso) => `${caso.server.url}v1-prueba/`;
async function crearAjena(caso) {
  const page = await caso.context.newPage();
  try {
    await page.goto(fueraDelSitio(caso));
    await page.evaluate(async (name) => {
      const cache = await caches.open(name);
      await cache.put('/futbol-base/index.html', new Response('v1 de prueba', { headers: { 'Content-Type': 'text/html' } }));
      await cache.put('/futbol-base/data-benjamin.js?v=1', new Response('const BENJAMIN=[];'));
    }, AJENA);
  } finally {
    await page.close();
  }
}
async function comprobarAjena(caso) {
  await cortarRed(caso, false);
  caso.red.colgar = null;
  const page = await caso.context.newPage();
  try {
    await page.goto(fueraDelSitio(caso));
    const visto = await page.evaluate(async (name) => {
      const names = await caches.keys();
      const cache = names.includes(name) ? await caches.open(name) : null;
      const entradas = cache ? await Promise.all((await cache.keys()).map(async (request) => [new URL(request.url).pathname + new URL(request.url).search, await (await cache.match(request)).text()])) : null;
      return { otras: names.filter((n) => n !== name && !n.startsWith('futbolbase2-')), entradas };
    }, AJENA);
    igual(visto, { otras: [], entradas: [['/futbol-base/index.html', 'v1 de prueba'], ['/futbol-base/data-benjamin.js?v=1', 'const BENJAMIN=[];']] },
      `${caso.nombre}: la caché ${AJENA} o las cachés del origen al acabar`);
  } finally {
    await page.close();
  }
}

// ── Aperturas ────────────────────────────────────────────────────────────────────────────────────────────
// Lo que enseña la página: los puntos de mi equipo, su versión (la ?v= de data-seasons.js, la de
// dataVersion), el aviso de la cabecera, la caja de error y la marca que pone la prueba (se pierde al
// recargar).
const mirar = (page) => page.evaluate(() => ({
  puntos: document.querySelector('#contenido tr.is-mine td.st-pts')?.textContent ?? null,
  version: (document.querySelector('script[src*="data-seasons.js"]')?.getAttribute('src').match(/[?&]v=([^&#]+)/) || [])[1] ?? null,
  aviso: document.querySelector('.shell-update')?.textContent.trim() ?? '',
  alerta: !!document.querySelector('#contenido [role="alert"]'),
  marca: window.__fb2Marca ?? null,
}));

// Una apertura: una página nueva hasta que pinta la fila de mi equipo (o una caja de error). `cargas`, los
// documentos que ha cargado (una recarga suma uno); `errores`, los de JavaScript y del arranque.
async function abrir(caso, label, { hash = '#/' } = {}) {
  const page = await caso.context.newPage();
  page.setDefaultTimeout(20000);
  const apertura = { page, errores: [], cargas: 0, label };
  page.on('pageerror', (error) => apertura.errores.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && message.text().startsWith('[arranque]')) apertura.errores.push(message.text().split('\n')[0]);
  });
  page.on('load', () => { apertura.cargas += 1; });
  const inicio = Date.now();
  await labeled(label, () => page.goto(`${caso.base}index.html${hash}`, { waitUntil: 'commit' }));
  await labeled(label, () => page.locator(`${PUNTOS}, #contenido [role="alert"]`).first().waitFor());
  apertura.ms = Date.now() - inicio;
  apertura.visto = await mirar(page);
  await page.evaluate(() => { window.__fb2Marca = 'sin recargar'; });
  return apertura;
}

// Lo que se espera de una apertura: la portada con `puntos`, de la versión `version`, sin caja de error,
// sin aviso (salvo que se diga) y sin errores.
function comoEsperado(caso, apertura, { puntos, version, aviso = '' }) {
  igual({ ...apertura.visto, marca: null, errores: apertura.errores },
    { puntos: String(puntos), version, aviso, alerta: false, marca: null, errores: [] },
    `${caso.nombre}, ${apertura.label}`);
}

// Cómo están los SW de la página: los estados de su registro, si el que manda es el activo, y las cachés.
const estadoSw = (page) => page.evaluate(async () => {
  const registration = await navigator.serviceWorker.getRegistration();
  return { installing: registration?.installing?.state ?? null, waiting: registration?.waiting?.state ?? null,
    active: registration?.active?.state ?? null, controla: !!registration?.active && navigator.serviceWorker.controller === registration.active,
    caches: await caches.keys() };
}).catch((error) => ({ error: error.message.split('\n')[0] }));

// El SW de `version` al mando de la página, sin otro instalándose ni esperando, y la suya como única caché
// de datos de la app. Si no llega, el error dice cómo quedaron.
async function alMando(caso, page, version, label) {
  try {
    await waitForAsync(page, async (cache) => {
      const registration = await navigator.serviceWorker.getRegistration();
      const datos = (await caches.keys()).filter((name) => name.startsWith('futbolbase2-v'));
      return registration?.active?.state === 'activated' && !registration.installing && !registration.waiting
        && navigator.serviceWorker.controller === registration.active && datos.length === 1 && datos[0] === cache;
    }, `futbolbase2-v${version}`, { timeout: 20000, label: `${caso.nombre}, ${label}` });
  } catch (error) {
    error.message = `${error.message.split('\n')[0]}\n  los SW: ${JSON.stringify(await estadoSw(page))}`;
    throw error;
  }
}

// Que la instalación de la versión de la copia ya lo ha intentado (el servidor vio pedir `ruta` con su
// huella nueva) y ha acabado sin quedarse: ni instalándose ni esperando.
async function instalacionFallida(caso, page, ruta, label) {
  const pedida = `empty ${ruta}?h=${huellaEnSw(caso.web.dir, ruta)}`;
  await esperar(() => caso.red.log.includes(pedida), { label: `${caso.nombre}, ${label}: el SW nuevo no pidió ${ruta} con su huella` });
  await waitForAsync(page, async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return !!registration?.active && !registration.installing && !registration.waiting;
  }, null, { timeout: 20000, label: `${caso.nombre}, ${label}: la instalación sigue en marcha` });
}

// Con la herramienta de pruebas conectada a los service workers (Playwright se conecta a cada uno), Chrome
// puede no activar el SW nuevo (aunque llame a skipWaiting) si el anterior está atendiendo peticiones de
// una página abierta justo cuando el nuevo acaba de instalarse: se queda esperando hasta que esa página se
// cierra (lo apunta también pwa-smoke.mjs, codeDeploy). Medido: 6 de 20
// pasadas con Playwright, 0 de 30 en Chrome sin DevTools en los SW; no es algo que vean los usuarios. Y si
// lo activa en mitad de la carga de una página, alguna petición de esa carga puede salir con la copia
// anterior, que se arregla sola en la apertura siguiente. Para que los casos que miran la página abierta no
// dependan de esa carrera de la herramienta, la instalación (sus peticiones ?h=) se retiene hasta que la
// página ha terminado de cargar (asentada) y luego se suelta.
async function conInstalacionRetenida(caso, accion) {
  let soltar;
  caso.red.retener = new Promise((resolve) => { soltar = resolve; });
  try {
    return await accion();
  } finally {
    caso.red.retener = null;
    soltar();
  }
}

// Que la página ha terminado de cargar lo de su portada: la plantilla resuelta (fillSquad), los escudos
// cargados (también los diferidos, que se piden ya) y, con `salud`, data-health.json pedido al servidor desde
// `desde` (la posición del registro de peticiones al abrir; la página lo pide una vez por carga).
async function asentada(caso, page, desde, label, { salud = true } = {}) {
  await page.evaluate(() => document.querySelectorAll('#contenido img.crest[loading="lazy"]').forEach((img) => { img.loading = 'eager'; }));
  await waitForAsync(page, () => !document.querySelector('#contenido [data-slot]')
    && [...document.querySelectorAll('#contenido img.crest')].every((img) => img.complete), null, { label: `${caso.nombre}, ${label}` });
  if (salud) await esperar(() => caso.red.log.slice(desde).some((linea) => linea.includes(' data-health.json')), { label: `${caso.nombre}, ${label}: sin data-health.json` });
}

// Cómo quedó el servidor, para leer un fallo sin reproducirlo: lo que se le pidió, lo último al final.
const diagnostico = (caso) => `\n  peticiones al servidor (${caso.red.log.length}, las últimas 40):\n    ${caso.red.log.slice(-40).join('\n    ')}`;

// ── Los casos ────────────────────────────────────────────────────────────────────────────────────────────
// La versión V0 instalada: la primera apertura registra su SW, que toma el mando (clients.claim).
async function instalada(caso, { cerrar = true } = {}) {
  const o = await abrir(caso, 'la primera visita');
  comoEsperado(caso, o, { puntos: PUNTOS_0, version: V0 });
  await alMando(caso, o.page, V0, 'el SW de la primera visita al mando');
  if (cerrar) await o.page.close();
  return o;
}

const CASOS = [
  ['caso 1 y caso 2', async (caso) => {
    await instalada(caso);
    const version = publicar(caso, PUNTOS_0 + 1);
    // La página llega de la red (versión nueva) y sus datos, con la ?v= nueva, también.
    const o = await conInstalacionRetenida(caso, async () => {
      const desde = caso.red.log.length;
      const apertura = await abrir(caso, '1.ª apertura tras publicar');
      comoEsperado(caso, apertura, { puntos: PUNTOS_0 + 1, version });
      await asentada(caso, apertura.page, desde, '1.ª apertura tras publicar, asentada');
      return apertura;
    });
    // El SW nuevo se instala, toma el mando y avisa: la página es ya de su versión, así que nada.
    await alMando(caso, o.page, version, 'el SW nuevo al mando');
    await waitForAsync(o.page, (v) => window.__fb2Mensajes.some((m) => m?.type === 'version' && m.version === v), version,
      { label: `${caso.nombre}, el aviso del SW nuevo a la página` });
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas }, { puntos: String(PUNTOS_0 + 1), version, aviso: '', alerta: false, marca: 'sin recargar', cargas: 1 },
      `${caso.nombre}: tras el aviso del SW nuevo, la página recargó o avisó`);
    await o.page.close();
    console.log(`PASS caso 1: primera apertura tras publicar: el dato nuevo (${PUNTOS_0 + 1} puntos, antes ${PUNTOS_0}) pintado en ${o.ms} ms, en una sola carga; con el SW nuevo ya al mando y su aviso recibido, ni recarga ni «Hay datos nuevos»`);
    // Caso 2: sin conexión, abre la versión nueva.
    await cortarRed(caso, true);
    const sin = await abrir(caso, 'sin conexión tras actualizar');
    comoEsperado(caso, sin, { puntos: PUNTOS_0 + 1, version });
    await sin.page.close();
    return `caso 2: sin conexión tras actualizar: abre la versión ${version} con el dato nuevo, en ${sin.ms} ms`;
  }],

  ['caso 3', async (caso) => {
    await instalada(caso);
    // Una versión nueva que también cambia data-history.js (si no, el SW nuevo no lo pediría), y ese, en 404.
    const version = publicar(caso, PUNTOS_0 + 1, { 'data-history.js': `${MUNDO['data-history.js'].body}// otra versión\n` });
    caso.red.falta.add('data-history.js');
    const o = await abrir(caso, 'apertura con data-history.js en 404');
    await instalacionFallida(caso, o.page, 'data-history.js', 'la instalación con data-history.js en 404');
    await alMando(caso, o.page, V0, 'tras la instalación fallida, el SW anterior');
    await o.page.close();
    await cortarRed(caso, true);
    const sin = await abrir(caso, 'sin conexión tras la instalación fallida');
    comoEsperado(caso, sin, { puntos: PUNTOS_0, version: V0 });
    await sin.page.close();
    return `caso 3: con data-history.js en 404, el SW de ${version} no se instala y sigue el de ${V0}; sin conexión, la versión ${V0} entera (${PUNTOS_0} puntos)`;
  }],

  ['caso 4', async (caso) => {
    await instalada(caso);
    const anterior = readFileSync(join(caso.web.dir, 'data-prebenjamin.js'));
    const version = publicar(caso, PUNTOS_0 + 1);
    // Pages a medias: el sw.js y el index.html nuevos, y el data-prebenjamin.js de antes.
    caso.red.cuerpo['data-prebenjamin.js'] = anterior;
    let o = await abrir(caso, 'apertura con el data-prebenjamin.js anterior');
    await instalacionFallida(caso, o.page, 'data-prebenjamin.js', 'la instalación con el data-prebenjamin.js anterior');
    await alMando(caso, o.page, V0, 'con el despliegue a medias, el SW anterior');
    await o.page.close();
    // Pages ya entero. Desde aquí, la instalación (también un reintento que Chrome tuviera ya en marcha)
    // espera a que la apertura haya cargado.
    o = await conInstalacionRetenida(caso, async () => {
      delete caso.red.cuerpo['data-prebenjamin.js'];
      const desde = caso.red.log.length;
      const apertura = await abrir(caso, 'apertura con el despliegue entero');
      comoEsperado(caso, apertura, { puntos: PUNTOS_0 + 1, version });
      await asentada(caso, apertura.page, desde, 'apertura con el despliegue entero, asentada');
      return apertura;
    });
    await alMando(caso, o.page, version, 'con el despliegue entero, el SW nuevo');
    await o.page.close();
    await cortarRed(caso, true);
    const sin = await abrir(caso, 'sin conexión tras el despliegue entero');
    comoEsperado(caso, sin, { puntos: PUNTOS_0 + 1, version });
    await sin.page.close();
    return `caso 4: despliegue a medias: el SW de ${version} no se instala (el cuerpo no da su huella) y sigue el de ${V0}; con el despliegue entero, el dato nuevo y su SW; sin conexión, el dato nuevo`;
  }],

  ['caso 5', async (caso) => {
    const o = await instalada(caso, { cerrar: false });
    const version = publicar(caso, PUNTOS_0 + 1);
    // Vuelve a primer plano: la primera vuelta tras abrir pide update() sin límite.
    const inicio = Date.now();
    await o.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitForAsync(o.page, (puntos) => document.querySelector('#contenido tr.is-mine td.st-pts')?.textContent === puntos, String(PUNTOS_0 + 1),
      { timeout: 10000, interval: 50, label: `${caso.nombre}, el dato nuevo en menos de 10 s` });
    const ms = Date.now() - inicio;
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas, errores: o.errores }, { puntos: String(PUNTOS_0 + 1), version, aviso: '', alerta: false, marca: null, cargas: 2, errores: [] },
      `${caso.nombre}: la página no se recargó una vez, sola, a la versión nueva`);
    await o.page.close();
    return `caso 5: página abierta que vuelve a primer plano: se recarga sola una vez y pinta el dato nuevo (versión ${version}) en ${ms} ms`;
  }],

  ['caso 6', async (caso) => {
    const o = await instalada(caso, { cerrar: false });
    // La usa: va a Tabla.
    await o.page.locator('.tabbar a.tab[href="#/tabla"]').click();
    await o.page.locator('#contenido section[data-screen="tabla"]').waitFor();
    const version = publicar(caso, PUNTOS_0 + 1);
    // Vuelve a primer plano y, mientras el SW nuevo se instala (retenido), vuelve a Mi equipo: la ha tocado
    // desde que volvió (volver pone «tocada» a cero).
    await conInstalacionRetenida(caso, async () => {
      await o.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await esperar(() => caso.red.retenidas.length > 0, { label: `${caso.nombre}: el SW nuevo no empezó a instalarse` });
      const desde = caso.red.log.length;
      await o.page.locator('.tabbar a.tab[href="#/"]').click();
      await o.page.locator(PUNTOS).waitFor();
      await asentada(caso, o.page, desde, 'de vuelta en Mi equipo, asentada', { salud: false });
    });
    await alMando(caso, o.page, version, 'el SW nuevo al mando con la página en uso');
    await waitForAsync(o.page, () => document.querySelector('.shell-update')?.textContent.includes('Hay datos nuevos'), null,
      { label: `${caso.nombre}, el aviso «Hay datos nuevos»` });
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas }, { puntos: String(PUNTOS_0), version: V0, aviso: 'Hay datos nuevos. Actualizar', alerta: false, marca: 'sin recargar', cargas: 1 },
      `${caso.nombre}: con la página en uso, recargó o no avisó`);
    await o.page.locator('.shell-update [data-action="actualizar"]').click();
    await waitForAsync(o.page, (puntos) => document.querySelector('#contenido tr.is-mine td.st-pts')?.textContent === puntos, String(PUNTOS_0 + 1),
      { label: `${caso.nombre}, el dato nuevo tras «Actualizar»` });
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas, errores: o.errores }, { puntos: String(PUNTOS_0 + 1), version, aviso: '', alerta: false, marca: null, cargas: 2, errores: [] },
      `${caso.nombre}: tras «Actualizar»`);
    await o.page.close();
    return `caso 6: página en uso: no se recarga, «Hay datos nuevos. Actualizar» en la cabecera; al pulsarlo, el dato nuevo (versión ${version})`;
  }],

  ['caso 7', async (caso) => {
    await instalada(caso);
    // El servidor deja colgadas la página y data-health.json: ni contesta ni corta.
    caso.red.colgar = (ruta) => ruta === 'index.html' || ruta === 'data-health.json';
    const o = await abrir(caso, 'con la red que no contesta');
    comoEsperado(caso, o, { puntos: PUNTOS_0, version: V0 });
    assert.ok(o.ms < 4000, `${caso.nombre}: la portada tardó ${o.ms} ms (más de 4 s)`);
    // La salud la pide la portada tras pintarse: se espera a que el servidor la vea colgada.
    await esperar(() => caso.red.colgadas.includes('data-health.json'), { label: `${caso.nombre}: la portada no pidió data-health.json` });
    assert.ok(caso.red.colgadas.includes('index.html'), `${caso.nombre}: la página no llegó a pedirse a la red`);
    // La salud de la portada es la copia del SW. Pasados 31 s de verdad (la ventana de red mala del SW se
    // cuenta en su reloj, que no es el de la página) y 31 s en el reloj de la página, la copia está
    // caducada y el SW vuelve a esperar a la red: la vuelta a Mi equipo no puede esperarla.
    await new Promise((resolve) => setTimeout(resolve, 31500));
    await caso.context.clock.setFixedTime(new Date(HOY.getTime() + 31000));
    await o.page.locator('.tabbar a.tab[href="#/tabla"]').click();
    await o.page.locator('#contenido section[data-screen="tabla"]').waitFor();
    const pedidas = caso.red.colgadas.filter((ruta) => ruta === 'data-health.json').length;
    const inicio = Date.now();
    await o.page.locator('.tabbar a.tab[href="#/"]').click();
    await o.page.locator('#contenido section[data-screen="home"]').waitFor();
    const vuelta = Date.now() - inicio;
    assert.ok(vuelta < 1000, `${caso.nombre}: la vuelta a Mi equipo con la copia caducada tardó ${vuelta} ms (1 s o más)`);
    await esperar(() => caso.red.colgadas.filter((ruta) => ruta === 'data-health.json').length > pedidas,
      { label: `${caso.nombre}: con la copia caducada, la salud no se volvió a pedir` });
    igual(o.errores, [], `${caso.nombre}: errores de JavaScript`);
    await o.page.close();
    return `caso 7: red que no contesta (la página y data-health.json colgadas): la portada con lo guardado en ${o.ms} ms; pasados 31 s, la vuelta a Mi equipo en ${vuelta} ms, sin esperar a la salud, que se vuelve a pedir`;
  }],

  ['caso 9', async (caso) => {
    // Un oyente de captura, antes que el de la app: con __fb2Descartar, los avisos de versión no le llegan.
    await caso.context.addInitScript(() => {
      window.__fb2Descartar = false;
      window.__fb2Descartados = [];
      navigator.serviceWorker?.addEventListener('message', (event) => {
        if (!window.__fb2Descartar || event.data?.type !== 'version') return;
        window.__fb2Descartados.push(event.data.version);
        event.stopImmediatePropagation();
      }, { capture: true });
    });
    const o = await instalada(caso, { cerrar: false });
    const version = publicar(caso, PUNTOS_0 + 1);
    // El SW nuevo se instala y toma el mando sin que la página vuelva a primer plano: lo pide la prueba.
    await o.page.evaluate(() => { window.__fb2Descartar = true; });
    await o.page.evaluate(() => navigator.serviceWorker.getRegistration().then((registration) => registration.update()));
    await alMando(caso, o.page, version, 'el SW nuevo al mando');
    await waitForAsync(o.page, (v) => window.__fb2Descartados.includes(v), version, { label: `${caso.nombre}, el aviso de activar, descartado` });
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas }, { puntos: String(PUNTOS_0), version: V0, aviso: '', alerta: false, marca: 'sin recargar', cargas: 1 },
      `${caso.nombre}: sin el aviso de activar, la página no debía cambiar`);
    // Vuelve a primer plano: pregunta al SW al mando, que contesta con su versión.
    await o.page.evaluate(() => { window.__fb2Descartar = false; });
    const inicio = Date.now();
    await o.page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitForAsync(o.page, (puntos) => document.querySelector('#contenido tr.is-mine td.st-pts')?.textContent === puntos, String(PUNTOS_0 + 1),
      { timeout: 10000, interval: 50, label: `${caso.nombre}, el dato nuevo al volver, en menos de 10 s` });
    const ms = Date.now() - inicio;
    o.visto = await mirar(o.page);
    igual({ ...o.visto, cargas: o.cargas, errores: o.errores }, { puntos: String(PUNTOS_0 + 1), version, aviso: '', alerta: false, marca: null, cargas: 2, errores: [] },
      `${caso.nombre}: al volver, la página no se recargó una vez, sola, a la versión nueva`);
    await o.page.close();
    return `caso 9: página que no recibió el aviso de activar del SW de ${version}: sigue en ${V0} hasta volver a primer plano; entonces pregunta, se recarga sola una vez y pinta el dato nuevo en ${ms} ms`;
  }],
];

// El fallo de un caso: su mensaje, dónde, y lo que vio el servidor.
function informe(error, caso) {
  const donde = String(error?.stack || '').split('\n').filter((line) => /^\s+at /.test(line)).slice(0, 4).join('\n');
  return `${error?.message || error}\n${donde}${caso ? diagnostico(caso) : ''}`;
}

let browser;
let fallos = 0;
// Caso 8: la caché ajena, comprobada al final de cada caso (también de los que fallan, si se pudo).
const ajena = { bien: 0, mal: [] };
try {
  const chrome = findChrome();
  assert.ok(chrome, 'no hay Chrome (CHROME o google-chrome/chromium en el PATH)');
  browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox'] });
  for (const [nombre, correr] of CASOS) {
    const inicio = Date.now();
    let caso;
    try {
      caso = await prepararCaso(browser, nombre);
      const linea = await correr(caso);
      console.log(`PASS ${linea} (${((Date.now() - inicio) / 1000).toFixed(1)} s)`);
    } catch (error) {
      fallos += 1;
      console.log(`FAIL ${nombre} (${((Date.now() - inicio) / 1000).toFixed(1)} s): ${informe(error, caso)}`);
    }
    if (caso) {
      try {
        await comprobarAjena(caso);
        ajena.bien += 1;
      } catch (error) {
        ajena.mal.push(`${nombre}: ${informe(error)}`);
      } finally {
        await cerrarCaso(caso);
      }
    }
  }
  if (ajena.bien === CASOS.length) {
    console.log(`PASS caso 8: en los ${ajena.bien} contextos, la caché ${AJENA} del origen sigue intacta al acabar y las demás son futbolbase2-`);
  } else {
    fallos += 1;
    console.log(`FAIL caso 8: bien en ${ajena.bien} de ${CASOS.length} contextos\n${ajena.mal.join('\n')}`);
  }
} catch (error) {
  fallos += 1;
  console.log(`FAIL frescura-smoke: ${error.stack || error}`);
} finally {
  if (browser) await browser.close();
}
console.log(fallos ? `frescura-smoke: ${fallos} con fallos` : 'frescura-smoke: ok');
process.exit(fallos ? 1 : 0);
