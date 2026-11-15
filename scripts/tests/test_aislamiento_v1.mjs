// v2 vive en el mismo origen que v1 (malolocabreralolo-tech.github.io, /futbol-base-v2/ y /futbol-base/),
// y Cache Storage, localStorage y sessionStorage son del origen, no de la ruta: v2 lleva cachés y claves
// propias, y nunca escribe ni borra las de v1. Solo nombra las de v1 en store.js, para leerlas.
// Ejecutar: node --test scripts/tests/test_aislamiento_v1.mjs
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { clearStore } from '../../src/store.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const leer = (f) => readFileSync(join(ROOT, f), 'utf8');
// Lo que v2 publica y ejecuta el navegador: la página, el SW, el manifiesto, el paquete de dist/ y los
// módulos de src/, de los que sale.
const SITIO = ['index.html', 'sw.js', 'manifest.json', ...readdirSync(join(ROOT, 'dist')).filter(f => f.endsWith('.js')).map(f => `dist/${f}`),
  ...readdirSync(join(ROOT, 'src')).filter(f => f.endsWith('.js')).map(f => `src/${f}`)];

// sw.js es un guion clásico: se carga en un contexto de vm con un `self` falso (como test_sw_fixes.mjs).
function cargarSw(globales = {}) {
  const escuchas = {};
  const self = {
    addEventListener: (tipo, fn) => { escuchas[tipo] = fn; },
    skipWaiting: () => {},
    clients: { claim: async () => {}, matchAll: async () => [] },
    location: { origin: 'https://example.test', href: 'https://example.test/futbol-base-v2/sw.js' },
  };
  const ctx = { self, console, URL, ...globales };
  vm.createContext(ctx);
  vm.runInContext(`${leer('sw.js')}\nthis.__exports = { CACHE_NAME, CRESTS_CACHE };`, ctx);
  return { ...ctx.__exports, escuchas };
}

// Storage en memoria con la interfaz de localStorage; `datos` es lo que guarda.
function almacenDePrueba(inicial = {}) {
  const datos = { ...inicial };
  return {
    datos,
    getItem: (k) => (Object.hasOwn(datos, k) ? datos[k] : null),
    setItem: (k, v) => { datos[k] = String(v); },
    removeItem: (k) => { delete datos[k]; },
  };
}

test('lo que v2 publica no nombra ninguna caché de v1', () => {
  for (const f of SITIO) assert.doesNotMatch(leer(f), /futbolbase-v|futbolbase-escudos-/, f);
});

test('las claves de v1 solo aparecen como constantes de solo lectura de store.js', () => {
  for (const f of SITIO) {
    const hits = leer(f).match(/futbol-base:[a-z0-9:]+/g) || [];
    // El paquete de dist/ lleva store.js dentro: las mismas, y ninguna más.
    if (f === 'src/store.js' || f.startsWith('dist/')) assert.deepEqual([...new Set(hits)].sort(), ['futbol-base:favorites:v1', 'futbol-base:jugadores', 'futbol-base:v2']);
    else assert.deepEqual(hits, [], f);
  }
});

test('sw.js lleva los nombres de v2 en sus dos primeras líneas', () => {
  const [l1, l2] = leer('sw.js').split('\n');
  assert.match(l1, /^const CACHE_NAME = 'futbolbase2-v[0-9a-z]+';$/);
  assert.match(l2, /^const CRESTS_CACHE = 'futbolbase2-escudos-[0-9a-f]{8}';$/);
});

test('al activarse, el SW solo borra cachés viejas de v2 y solo abre su precache', async () => {
  const { CACHE_NAME, CRESTS_CACHE } = cargarSw();
  // Las de v1 (datos y escudos), dos viejas de v2, la de otro proyecto del origen y las tres de este SW.
  const claves = ['futbolbase-v20261113', 'futbolbase-escudos-aaaa1111', 'futbolbase2-vvieja', 'futbolbase2-escudos-00000000', 'otra-app',
    CACHE_NAME, CRESTS_CACHE, 'futbolbase2-precache'];
  const borradas = [];
  const abiertas = [];
  const sw = cargarSw({ caches: {
    keys: async () => claves,
    delete: async (nombre) => { borradas.push(nombre); return true; },
    open: async (nombre) => { abiertas.push(nombre); return { keys: async () => [], delete: async () => true }; },
  } });
  let hecho;
  sw.escuchas.activate({ waitUntil: (promesa) => { hecho = promesa; } });
  await hecho;
  assert.deepEqual(borradas.sort(), ['futbolbase2-escudos-00000000', 'futbolbase2-vvieja']);
  assert.deepEqual(abiertas, ['futbolbase2-precache']);
});

test('«Borrar datos» solo quita claves de v2', () => {
  const s = almacenDePrueba({ 'fb2:almacen': '{}', 'fb2:jugadores': '[]', 'futbol-base:v2': 'x', 'futbol-base:jugadores': 'y',
                              'futbol-base:favorites:v1': 'z', season: 'a', cat: 'b', theme: 'c' });
  clearStore(s);
  assert.deepEqual(Object.keys(s.datos).sort(), ['cat', 'futbol-base:favorites:v1', 'futbol-base:jugadores', 'futbol-base:v2', 'season', 'theme']);
  assert.deepEqual([s.datos['futbol-base:v2'], s.datos['futbol-base:jugadores'], s.datos['futbol-base:favorites:v1']], ['x', 'y', 'z'], 'lo de v1, intacto');
});
