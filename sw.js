const CACHE_NAME = 'futbolbase2-v20261126i';
const CRESTS_CACHE = 'futbolbase2-escudos-21f9b5f8';

// El service worker de Fútbol Base v2. La línea 1 la sube el bot con cada versión de datos
// (generate_js.bump_cache_version) y la línea 2, el sello de escudos/, la escribe scripts/build_crests.py.
//
// Tres cachés, todas futbolbase2-…, porque el origen lo comparten v1 (/futbol-base/) y otros proyectos:
// - futbolbase2-precache: lo que se instala, con clave <ruta>?h=<huella>; no cambia de nombre y al activar
//   pierde las claves que ya no están en el manifiesto.
// - CACHE_NAME (futbolbase2-v<versión>): los datos perezosos ya usados y data-health.json; una por versión.
// - CRESTS_CACHE (futbolbase2-escudos-<sello>): los escudos; cambia solo cuando cambian los escudos.

const VERSION = CACHE_NAME.slice('futbolbase2-v'.length);
const PRECACHE_CACHE = 'futbolbase2-precache';

// >>> precache: lo escribe scripts/precache.py
const PRECACHE = {
  "index.html": "400132b8",
  "dist/acta-c2dfa212.css": "c2dfa212",
  "dist/app-7b470b99.js": "7b470b99",
  "src/config.js": "34193a4f",
  "manifest.json": "823d3903",
  "fonts/PublicSans-latin.woff2": "fd76a14f",
  "icons/icon-180.png": "31b9d3f2",
  "icons/icon-192.png": "efe8a25e",
  "icons/icon-512.png": "498ff532",
  "icons/icon-maskable-512.png": "a3e02b61",
  "data-benjamin.js": "3d95419d",
  "data-prebenjamin.js": "a5099abd",
  "data-history.js": "ef083659",
  "data-goleadores.js": "0c4a2758",
  "data-shields.js": "eaeca19f",
  "data-seasons.js": "9cb8a6e7",
  "data-maspalomas-cup-2026.js": "4a43b19c",
  "data-alevin.js": "d2b5c8b7",
  "data-season-2025-2026.js": "d21763a9",
  "data-season-2024-2025.js": "3880023c",
  "data-season-2023-2024.js": "ab706092",
  "data-season-2022-2023.js": "1789efd4",
  "data-season-2021-2022.js": "632744ee",
  "data-season-2020-2021.js": "d119b816",
  "data-season-2019-2020.js": "737a8032",
  "data-season-2018-2019.js": "7e2903e9",
  "data-season-2017-2018.js": "fb2b4069",
  "data-season-2016-2017.js": "d9cd4bcd",
  "data-season-2015-2016.js": "e971baba",
  "data-season-2014-2015.js": "09d9dafd",
  "data-season-2013-2014.js": "7a456470",
  "data-season-2012-2013.js": "f8c88dd3",
};
const OPCIONALES = [
  "data-alevin.js",
  "data-season-2025-2026.js",
  "data-season-2024-2025.js",
  "data-season-2023-2024.js",
  "data-season-2022-2023.js",
  "data-season-2021-2022.js",
  "data-season-2020-2021.js",
  "data-season-2019-2020.js",
  "data-season-2018-2019.js",
  "data-season-2017-2018.js",
  "data-season-2016-2017.js",
  "data-season-2015-2016.js",
  "data-season-2014-2015.js",
  "data-season-2013-2014.js",
  "data-season-2012-2013.js",
];
// <<< precache

// Lo que se espera a la red antes de servir la copia: la página y la salud, poco (abrir no puede tardar);
// un dato de otra versión, más (sin él la página nueva se pintaría con el dato viejo).
const LIMITE_PAGINA_MS = 2500;
const LIMITE_SALUD_MS = 2500;
const LIMITE_DATOS_MS = 8000;
// El tope de cada petición de los manejadores de fetch: si la respuesta no ha llegado en este rato, se aborta,
// también cuando ya se sirvió la copia. Una colgada mantendría al SW con trabajo y el navegador no activaría el
// siguiente. Las descargas de la instalación no lo llevan: un fichero grande en una red lenta no la hace fallar.
const LIMITE_RED_MS = 15000;
// Tras un fallo de la red, la página y la salud van derechas a la copia durante este rato: una sola espera.
const VENTANA_RED_MALA_MS = 30000;
// Descargas simultáneas al instalar: las justas para no ahogar una red de móvil.
const DESCARGAS_A_LA_VEZ = 6;
// Las actas de grupo ya vistas que se vuelven a bajar para la versión nueva, como mucho.
const LINEUPS_KEEP = 12;

const AMBITO = new URL('./', self.location.href).pathname;
const RED = { cache: 'no-cache', credentials: 'same-origin' };

// La ruta relativa al ámbito del SW; la raíz es index.html.
function rutaDe(pathname) {
  const ruta = pathname.startsWith(AMBITO) ? pathname.slice(AMBITO.length) : pathname;
  return ruta === '' ? 'index.html' : ruta;
}

function enPrecache(ruta) {
  return Object.prototype.hasOwnProperty.call(PRECACHE, ruta);
}

// La clave de un fichero en futbolbase2-precache, que es también la URL con la que se pide a la red.
function precacheKey(ruta, huella) {
  return new URL(`./${ruta}?h=${huella}`, self.location.href).href;
}

// Las 8 primeras cifras hex del SHA-1 del contenido, como las calcula scripts/precache.py.
async function huellaDe(buffer) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-1', buffer));
  return Array.from(digest.slice(0, 4), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

// Qué hacer con un GET del mismo origen, según su ruta y su ?v= (o null).
function classifyRequest(pathname, v) {
  const file = pathname.split('/').pop();
  if (pathname.endsWith('/') || pathname.endsWith('.html')) return 'pagina';
  if (file === 'data-health.json') return 'salud';
  if (pathname.includes('/escudos/')) return 'escudo';
  if (v && v !== VERSION) return 'otra-version';
  if (enPrecache(rutaDe(pathname))) return 'precache';
  if (file.startsWith('data-') && file.endsWith('.js')) return 'dato';
  return 'red';
}

// De las URLs de las cachés anteriores (la más reciente al final), las actas de grupo que hay que volver a
// bajar, sin repetir y como mucho `keep`.
function lineupsToCarry(urls, keep = LINEUPS_KEEP) {
  const files = [];
  for (const url of urls) {
    const file = new URL(url).pathname.split('/').pop();
    if (!/^data-lineups-\d{4}-\d{4}-[A-Za-z0-9]+\.js$/.test(file)) continue;
    const i = files.indexOf(file);
    if (i >= 0) files.splice(i, 1);
    files.push(file);
  }
  return files.slice(-keep).map(file => './' + file);
}

async function actasUsadas() {
  const urls = [];
  for (const name of await caches.keys()) {
    if (!name.startsWith('futbolbase2-v') || name === CACHE_NAME) continue;
    for (const request of await (await caches.open(name)).keys()) urls.push(request.url);
  }
  return lineupsToCarry(urls);
}

function sinQuery(url) {
  const u = new URL(url);
  return u.origin + u.pathname;
}

function conVersion(url, v) {
  const u = new URL(url, self.location.href);
  u.searchParams.set('v', v);
  return u.href;
}

// La copia guardada, con sus cabeceras y la que dice a la página que viene de la caché.
function markedFromCache(cached) {
  const headers = new Headers(cached.headers);
  headers.set('x-fb2-origen', 'cache');
  return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers });
}

// Lo que dio la red antes de `ms`: { response }, { caida: true } o { tarde: true }.
function aTiempo(peticion, ms) {
  let timer;
  const limite = new Promise(resolve => { timer = setTimeout(() => resolve({ tarde: true }), ms); });
  const red = peticion.then(response => ({ response }), () => ({ caida: true }));
  return Promise.race([red, limite]).then(resultado => {
    clearTimeout(timer);
    return resultado;
  });
}

// fetch con LIMITE_RED_MS: se aborta solo si las cabeceras no han llegado; con ellas se retira el temporizador
// y un cuerpo que ya está llegando no se corta. Un aborto es un fallo de red más.
function fetchConTope(url, init = RED) {
  const control = new AbortController();
  const timer = setTimeout(() => control.abort(), LIMITE_RED_MS);
  const peticion = fetch(url, { ...init, signal: control.signal });
  const retirar = () => clearTimeout(timer);
  peticion.then(retirar, retirar);
  return peticion;
}

let redMalaHasta = 0;

function ahora() {
  return Date.now();
}

function redMala() {
  return self.navigator?.onLine === false || ahora() < redMalaHasta;
}

function apuntarRedMala() {
  redMalaHasta = ahora() + VENTANA_RED_MALA_MS;
}

// Pide `./ruta?h=huella` y lee el cuerpo: la respuesta, rehecha con él, y si es un 2xx que da su huella. Sin
// tope, como en la instalación, salvo que se le pase `pedir` (fetchConTope).
async function bajar(ruta, huella, pedir = fetch) {
  const response = await pedir(precacheKey(ruta, huella), RED);
  const cuerpo = await response.arrayBuffer();
  const buena = response.ok && (await huellaDe(cuerpo)) === huella;
  const rehecha = new Response(cuerpo, { status: response.status, statusText: response.statusText, headers: response.headers });
  return { response: rehecha, buena };
}

// Ejecuta `fn` sobre cada elemento, como mucho `n` a la vez.
async function aLaVez(items, n, fn) {
  const cola = [...items];
  const obrero = async () => {
    while (cola.length) await fn(cola.shift());
  };
  await Promise.all(Array.from({ length: Math.min(n, cola.length) }, obrero));
}

// ─── instalar: todo o nada ──────────────────────────────────────────────────

async function faltanEnPrecache(cache) {
  const hay = new Set((await cache.keys()).map(request => request.url));
  return Object.keys(PRECACHE).filter(ruta => !hay.has(precacheKey(ruta, PRECACHE[ruta])));
}

async function llenarPrecache(cache, rutas, fallos, pedir = fetch) {
  await aLaVez(rutas, DESCARGAS_A_LA_VEZ, async ruta => {
    try {
      const { response, buena } = await bajar(ruta, PRECACHE[ruta], pedir);
      if (!buena) throw new Error(`HTTP ${response.status} o un cuerpo que no da la huella ${PRECACHE[ruta]}`);
      await cache.put(precacheKey(ruta, PRECACHE[ruta]), response);
      fallos.delete(ruta);
    } catch (error) {
      fallos.set(ruta, error);
    }
  });
}

// Lo que ya está guardado con su huella no se vuelve a pedir. Un obligatorio que falla rechaza la
// instalación (el SW anterior sigue al mando, con su versión entera); un opcional, solo avisa.
async function instalar() {
  const cache = await caches.open(PRECACHE_CACHE);
  const fallos = new Map();
  await llenarPrecache(cache, await faltanEnPrecache(cache), fallos);
  const obligatorio = ruta => !OPCIONALES.includes(ruta);
  // Una segunda vuelta por los obligatorios que falten ahora: la limpieza de la versión que se activa puede
  // haber quitado una clave que esta ya había guardado.
  if (![...fallos.keys()].some(obligatorio)) {
    const quitados = (await faltanEnPrecache(cache)).filter(obligatorio);
    if (quitados.length) await llenarPrecache(cache, quitados, fallos);
  }
  const faltan = (await faltanEnPrecache(cache)).filter(obligatorio);
  if (faltan.length) {
    const detalle = faltan.map(ruta => `${ruta}${fallos.has(ruta) ? `: ${fallos.get(ruta).message}` : ''}`).join('; ');
    throw new Error(`[SW] no se instala la versión ${VERSION}: ${detalle}`);
  }
  const opcionales = [...fallos.keys()];
  if (opcionales.length) console.warn(`[SW] se bajarán al usarse: ${opcionales.join(', ')}`);
  await llevarDatos().catch(() => {});
}

// data-health.json y las actas de grupo ya vistas, a la caché de esta versión; si algo falla, se baja al usarse.
async function llevarDatos() {
  const cache = await caches.open(CACHE_NAME);
  const rutas = ['./data-health.json', ...(await actasUsadas().catch(() => []))];
  await aLaVez(rutas, DESCARGAS_A_LA_VEZ, async ruta => {
    try {
      const response = await fetch(conVersion(ruta, VERSION), RED);
      if (response.ok) await cache.put(sinQuery(new URL(ruta, self.location.href)), response);
    } catch { /* se baja al usarse */ }
  });
}

self.addEventListener('install', event => {
  event.waitUntil(instalar());
  self.skipWaiting();
});

// ─── activar ────────────────────────────────────────────────────────────────

function viejaDeEstaApp(name) {
  return (name.startsWith('futbolbase2-v') && name !== CACHE_NAME)
    || (name.startsWith('futbolbase2-escudos-') && name !== CRESTS_CACHE);
}

// Las obligatorias del manifiesto propio que falten: la limpieza de otra versión activada mientras esta se
// instalaba pudo quitar alguna tras su última comprobación. Con su huella y con LIMITE_RED_MS; si falla, se
// bajan al pedirse (servirPrecache), como las opcionales, que no se reponen aquí. Nunca rechaza.
function reponer(cache) {
  return faltanEnPrecache(cache)
    .then(faltan => {
      const obligatorias = faltan.filter(ruta => !OPCIONALES.includes(ruta));
      if (obligatorias.length) return llenarPrecache(cache, obligatorias, new Map(), fetchConTope);
    })
    .catch(() => {});
}

// La última reposición lanzada al activar (la miran las pruebas).
let reposicion = null;

// Solo se borra lo de esta app; del precache, solo las claves que el manifiesto ya no tiene (las que comparte
// con el anterior son la misma URL y se quedan).
async function activar() {
  await Promise.all((await caches.keys()).filter(viejaDeEstaApp).map(name => caches.delete(name)));
  const cache = await caches.open(PRECACHE_CACHE);
  const validas = new Set(Object.keys(PRECACHE).map(ruta => precacheKey(ruta, PRECACHE[ruta])));
  for (const request of await cache.keys()) {
    if (!validas.has(request.url)) await cache.delete(request);
  }
  await self.clients.claim();
  for (const client of await self.clients.matchAll({ type: 'window' })) {
    client.postMessage({ type: 'version', version: VERSION });
  }
  // Ya al mando y avisadas las ventanas, se reponen las obligatorias que falten, sin esperarlas: mientras
  // activate no acaba, el SW sigue en «activating» y el navegador retiene los fetch de las páginas que ya
  // controla. Con todo en su sitio, ninguna petición.
  reposicion = reponer(cache);
}

self.addEventListener('activate', event => {
  event.waitUntil(activar());
});

// La página pregunta la versión al arrancar y al volver: si se perdió el aviso de activar, así se entera.
// Contesta con el mismo mensaje, para que la página no tenga otro camino.
self.addEventListener('message', event => {
  if (event.data?.type !== 'version?') return;
  event.source?.postMessage({ type: 'version', version: VERSION });
});

// ─── servir ─────────────────────────────────────────────────────────────────

async function copiaDePagina() {
  const cache = await caches.open(PRECACHE_CACHE);
  return cache.match(precacheKey('index.html', PRECACHE['index.html']));
}

// La red primero, sin la caché HTTP; si falla o tarda, el index.html instalado. Lo de la red no se guarda:
// lo guarda la instalación de su versión, con el resto de su código.
async function servirPagina(event, url) {
  if (redMala()) {
    const copia = await copiaDePagina();
    if (copia) return copia;
  }
  const red = fetchConTope(url.href);
  const resultado = await aTiempo(red, LIMITE_PAGINA_MS);
  if (resultado.response?.ok) return resultado.response;
  if (!resultado.response) apuntarRedMala();
  return (await copiaDePagina()) || resultado.response || red;
}

// La red primero, con límite, y guardada; si no llega, la copia con x-fb2-origen: cache, para que la página
// sepa que no es la de ahora. Si la red llega tarde, se guarda igual para la próxima vez.
function servirSalud(event, url) {
  const clave = sinQuery(url);
  const red = fetchConTope(url.href);
  const guardada = red.then(async response => {
    if (!response.ok) return;
    const copia = response.clone();
    await (await caches.open(CACHE_NAME)).put(clave, copia);
  });
  event.waitUntil(guardada.catch(() => {}));
  return (async () => {
    const copiaGuardada = async () => (await caches.open(CACHE_NAME)).match(clave);
    if (redMala()) {
      const copia = await copiaGuardada();
      if (copia) return markedFromCache(copia);
    }
    const resultado = await aTiempo(red, LIMITE_SALUD_MS);
    if (resultado.response?.ok) return resultado.response;
    if (!resultado.response) apuntarRedMala();
    const copia = await copiaGuardada();
    return copia ? markedFromCache(copia) : (resultado.response || red);
  })();
}

// Primero CRESTS_CACHE; si no está, la red con el sello como ?v= (la clave de la caché HTTP), y se guarda
// antes de responder: el escudo que se ve ya queda guardado.
function servirEscudo(event) {
  return caches.open(CRESTS_CACHE).then(async cache => {
    const cached = await cache.match(event.request);
    if (cached) return cached;
    const response = await fetchConTope(conVersion(event.request.url, CRESTS_CACHE.replace('futbolbase2-escudos-', '')));
    if (response.ok) await cache.put(event.request, response.clone()).catch(() => {});
    return response;
  });
}

// Cualquier copia del mismo fichero, sin mirar la query: la del manifiesto, otra del precache o la de CACHE_NAME.
async function cualquierCopia(url) {
  const ruta = rutaDe(url.pathname);
  const precache = await caches.open(PRECACHE_CACHE);
  if (enPrecache(ruta)) {
    const suya = await precache.match(precacheKey(ruta, PRECACHE[ruta]));
    if (suya) return suya;
  }
  return (await precache.match(sinQuery(url), { ignoreSearch: true }))
    || (await (await caches.open(CACHE_NAME)).match(sinQuery(url), { ignoreSearch: true }));
}

// Lo pide una página de otra versión (más nueva, recién llegada de la red, o más vieja, abierta antes de
// esta): la red, con su ?v=, y sin guardarlo; si no llega a tiempo, la copia que haya.
async function servirOtraVersion(event, url) {
  const red = fetchConTope(url.href);
  const resultado = await aTiempo(red, LIMITE_DATOS_MS);
  if (resultado.response?.ok) return resultado.response;
  return (await cualquierCopia(url)) || resultado.response || red;
}

// La copia de su clave; si no está (un opcional que falló al instalar), la red, y se guarda si da su huella.
async function servirPrecache(event, url) {
  const ruta = rutaDe(url.pathname);
  const clave = precacheKey(ruta, PRECACHE[ruta]);
  const cache = await caches.open(PRECACHE_CACHE);
  const copia = await cache.match(clave);
  if (copia) return copia;
  try {
    const { response, buena } = await bajar(ruta, PRECACHE[ruta], fetchConTope);
    if (buena) await cache.put(clave, response.clone()).catch(() => {});
    return response;
  } catch (error) {
    const otra = await cualquierCopia(url);
    if (otra) return otra;
    throw error;
  }
}

// Los datos perezosos de esta versión: CACHE_NAME, sin mirar la query; si no están, la red, y se guardan.
async function servirDato(event, url) {
  const clave = sinQuery(url);
  const cache = await caches.open(CACHE_NAME);
  const copia = await cache.match(clave);
  if (copia) return copia;
  const response = await fetchConTope(url.href);
  if (response.ok) await cache.put(clave, response.clone()).catch(() => {});
  return response;
}

const SERVIR = {
  pagina: servirPagina,
  salud: servirSalud,
  escudo: servirEscudo,
  'otra-version': servirOtraVersion,
  precache: servirPrecache,
  dato: servirDato,
};

// Lo demás (clase 'red'), lo que no es GET y lo de otro origen no pasa por el SW.
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const servir = SERVIR[classifyRequest(url.pathname, url.searchParams.get('v'))];
  if (servir) event.respondWith(servir(event, url));
});
