// v1 y v2 en el mismo origen, con sus service workers de verdad: Cache Storage y localStorage son del
// origen (malolocabreralolo-tech.github.io), no de la ruta, así que esta prueba abre las dos apps en un
// Chrome real y comprueba que ninguna toca lo de la otra, tampoco cuando una se actualiza.
// v1 es el código y los datos reales de v1 en V1_COMMIT, sacados con git archive a una carpeta temporal y
// servidos bajo /futbol-base/; v2, el árbol de trabajo, bajo /futbol-base-v2/ (pages-server.mjs).
//   1. v1 instalada, con su equipo, un jugador seguido y sus claves antiguas (season, cat, theme).
//   2. v2 instalada: lo de v1 sigue igual; las cachés de v2 son futbolbase2-*; trae el equipo y los
//      seguidos de v1 a fb2:almacen y fb2:jugadores.
//   3. «Borrar datos de esta app» en v2: lo de v1 sigue igual; de fb2: solo quedan fb2:importado y
//      fb2:codigo; al recargar, el equipo por defecto.
//   4. Subida de v1 (otra versión y otro sello de escudos en sw.js e index.html): su SW nuevo borra sus
//      cachés viejas, y lo de v2 sigue igual.
//   5. Subida de v2, igual: borra sus viejas, y lo de v1 sigue igual.
//   6. Ni un error de consola ni una excepción en las dos apps.
// Cada caché del origen tiene que ser de una de las dos por su nombre y guardar solo lo de su ruta.
// Sin Chrome o sin el commit de v1, falla: esta prueba no se salta.
//
// npm install --no-save --package-lock=false playwright@1.58.0
// node scripts/tests/aislamiento-smoke.mjs
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findChrome } from './render-smoke.mjs';
import { labeled, takeOver, waitForAsync } from './browser-wait.mjs';
import { startPagesServer } from './pages-server.mjs';
import { PORTAL } from '../../src/config.js';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
// El commit de v1 del que nació v2: su código y sus datos son los que tiene publicados v1.
const V1_COMMIT = 'c47a1caaddd19b8000b394487fb0eb4ef25c59d2';
// El estado de v1 en este navegador: un equipo de sus datos distinto del de por defecto (Heidelberg, de
// PG3), un jugador seguido y las claves antiguas que v1 aún borra con su «Borrar datos».
const V1_TEAM = { name: 'Heidelberg', season: '2026-2027', cat: 'prebenjamin', groupId: 'PG3' };
const V1_STATE = {
  'futbol-base:v2': JSON.stringify({ myTeam: V1_TEAM, recent: [{ s: '2026-2027', g: 'PG2', t: 'AD Huracán' }] }),
  'futbol-base:jugadores': JSON.stringify([{ id: '900001', n: 'PRUEBA PRUEBA, JUGADOR' }]),
  season: '2025-2026',
  cat: 'benjamin',
  theme: 'dark',
};
const PLAYER_LINK = 'a.traj-row[href*="id=900001"]';
const HOME = '#contenido section[data-screen="home"][data-state] h1';

const git = (args, options = {}) => spawnSync('git', args, { cwd: ROOT, ...options });
// La versión de los datos y el sello de los escudos de un sw.js, sin mirar el prefijo: lo que se espera
// de cada app (futbolbase- o futbolbase2-) lo pone la prueba, no el código que se prueba.
function versionsOf(sw) {
  const version = (sw.match(/^const CACHE_NAME = '[a-z0-9]+-v([0-9a-z]+)';$/m) || [])[1];
  const seal = (sw.match(/^const CRESTS_CACHE = '[a-z0-9]+-escudos-([0-9a-f]+)';$/m) || [])[1];
  assert.ok(version && seal, 'sw.js sin CACHE_NAME o sin CRESTS_CACHE en su sitio');
  return { version, seal };
}

// v1 en una carpeta temporal: lo que su sitio necesita para abrir sin un 404 (cada uno, un error de
// consola): la página, su SW, el manifiesto, la hoja, src/, la fuente, los iconos, los escudos, los datos
// que precachea su SW y las actas de los dos grupos que se abren. Sin la base ni el resto de actas.
function extractV1(dir) {
  const has = () => git(['cat-file', '-e', `${V1_COMMIT}^{commit}`]).status === 0;
  // En CI el clon es de un solo commit: se trae el de v1, y si no llega, la prueba falla.
  if (!has()) git(['fetch', '--quiet', '--depth', '1', 'origin', V1_COMMIT], { stdio: 'inherit' });
  assert.ok(has(), `el commit de v1 (${V1_COMMIT}) no está en el clon ni se pudo traer de origin`);
  const show = (file) => execFileSync('git', ['show', `${V1_COMMIT}:${file}`], { cwd: ROOT, encoding: 'utf8' });
  const sw = show('sw.js');
  const config = JSON.parse(show('src/config.js').replace(/^export const PORTAL = /, '').replace(/;\s*$/, ''));
  const data = [...sw.matchAll(/'\.\/(data-[^']+)'/g)].map((m) => m[1]);
  const lineups = [config.defaultTeam.groupId, V1_TEAM.groupId].map((group) => `data-lineups-${config.season}-${group}.js`);
  const paths = ['index.html', 'sw.js', 'manifest.json', 'acta.css', 'src', 'fonts', 'icons', 'escudos', ...data, ...lineups];
  const tar = execFileSync('git', ['archive', '--format=tar', V1_COMMIT, '--', ...paths], { cwd: ROOT, maxBuffer: 1 << 28 });
  execFileSync('tar', ['-x', '-C', dir], { input: tar });
  return { ...versionsOf(sw), defaultTeam: config.defaultTeam.name };
}

// Lo que hay en el origen: las cachés, con las rutas que guarda cada una, y localStorage. Se mira desde
// una página fuera del ámbito de los dos SW. caches.has antes de abrir: abrir una que no existe la crea.
async function snapshot(probe) {
  return probe.evaluate(async () => {
    const out = { caches: {}, keys: {} };
    for (const name of (await caches.keys()).sort()) {
      if (!(await caches.has(name))) continue;
      out.caches[name] = (await (await caches.open(name)).keys()).map((request) => {
        const url = new URL(request.url);
        return url.pathname + url.search;
      }).sort();
    }
    for (let i = 0; i < localStorage.length; i += 1) out.keys[localStorage.key(i)] = localStorage.getItem(localStorage.key(i));
    return out;
  });
}

// Una foto cuando ya no cambia (dos seguidas iguales): con las páginas de las apps cerradas, su SW puede
// estar guardando todavía lo último que pidieron.
async function quiet(probe, label) {
  const deadline = Date.now() + 10000;
  let last = await snapshot(probe);
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    const now = await snapshot(probe);
    if (JSON.stringify(now) === JSON.stringify(last)) return now;
    if (Date.now() >= deadline) throw new Error(`${label}: las cachés y las claves no se quedan quietas en 10 s`);
    last = now;
  }
}

const pick = (object, keep) => Object.fromEntries(Object.entries(object).filter(([key]) => keep(key)));

// Toda caché del origen es de una de las dos apps por su nombre, y guarda solo lo de la ruta de esa app.
function checkOwners(snap, apps, label) {
  const problems = [];
  for (const [name, entries] of Object.entries(snap.caches)) {
    const app = apps.find((a) => name.startsWith(a.prefix));
    if (!app) {
      problems.push(`la caché ${name} no es de ninguna de las dos apps`);
      continue;
    }
    const foreign = entries.filter((path) => !path.startsWith(app.path));
    if (foreign.length) problems.push(`la caché ${name} (de ${app.id}) guarda ${foreign.length} de otra ruta: ${foreign.slice(0, 3).join(', ')}`);
  }
  assert.deepEqual(problems, [], `${label}: ${problems.join('; ')}`);
}

// Las cachés y las claves de `app` siguen como en `before`: los mismos nombres y lo mismo dentro.
function checkUntouched(app, before, after, label) {
  const was = pick(before.caches, (name) => name.startsWith(app.prefix));
  const now = pick(after.caches, (name) => name.startsWith(app.prefix));
  assert.ok(Object.keys(was).length > 0, `${label}: ${app.id} no tenía ninguna caché que comprobar`);
  for (const [name, entries] of Object.entries(was)) {
    assert.ok(Object.hasOwn(now, name), `${label}: la caché ${name} de ${app.id} ya no está (quedan ${JSON.stringify(Object.keys(after.caches))})`);
    const added = now[name].filter((path) => !entries.includes(path));
    const removed = entries.filter((path) => !now[name].includes(path));
    assert.ok(added.length + removed.length === 0,
      `${label}: la caché ${name} de ${app.id} ha cambiado: +${added.length} (${added.slice(0, 3).join(', ')}), -${removed.length} (${removed.slice(0, 3).join(', ')})`);
  }
  assert.deepEqual(Object.keys(now).sort(), Object.keys(was).sort(), `${label}: las cachés de ${app.id}`);
  assert.deepEqual(pick(after.keys, app.ownsKey), pick(before.keys, app.ownsKey), `${label}: las claves de ${app.id}`);
}

let browser;
let server;
let v1Dir;
let step = 0;
const errors = [];
try {
  const chrome = findChrome();
  assert.ok(chrome, 'no hay Chrome (o CHROME=/ruta/absoluta): esta prueba no se salta');
  const { chromium } = createRequire(import.meta.url)('playwright');
  browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox'] });
  v1Dir = mkdtempSync(join(tmpdir(), 'aislamiento-v1-'));
  const v1Real = extractV1(v1Dir);
  const v2Real = versionsOf(readFileSync(join(ROOT, 'sw.js'), 'utf8'));
  // Cada app: su ruta, el prefijo de sus cachés, sus claves, su versión y la de su subida.
  const v1 = { id: 'v1', path: '/futbol-base/', prefix: 'futbolbase-', ownsKey: (key) => !key.startsWith('fb2:'),
    ...v1Real, next: '20991231a', nextSeal: 'c1c1c1c1', published: false };
  const v2 = { id: 'v2', path: '/futbol-base-v2/', prefix: 'futbolbase2-', ownsKey: (key) => key.startsWith('fb2:'),
    ...v2Real, defaultTeam: PORTAL.defaultTeam.name, next: '20991231b', nextSeal: 'c2c2c2c2', published: false };
  const apps = [v1, v2];
  for (const app of apps) {
    app.data = (version = app.version) => `${app.prefix}v${version}`;
    app.crests = (seal = app.seal) => `${app.prefix}escudos-${seal}`;
  }
  assert.notEqual(V1_TEAM.name, v1.defaultTeam, 'el equipo de v1 tiene que ser otro que el de por defecto');

  // Una subida: el servidor da otra versión de los datos y otro sello de escudos en sw.js e index.html,
  // como el bot (y build_crests.py) al publicar; así se activan las dos ramas de la limpieza del SW.
  const bySite = { '/futbol-base': v1, '/futbol-base-v2': v2 };
  const transform = ({ site, path, body }) => {
    const app = bySite[site];
    if (!app.published || (path !== 'sw.js' && path !== 'index.html')) return undefined;
    return body.toString().replaceAll(app.version, app.next).replace(`-escudos-${app.seal}'`, `-escudos-${app.nextSeal}'`);
  };
  server = await startPagesServer(ROOT, { sites: { '/futbol-base': v1Dir }, transform });
  const origin = server.url.replace(/\/$/, '');
  for (const app of apps) app.url = `${origin}${app.path}`;

  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'es-ES', timezoneId: 'Atlantic/Canary' });
  // Los errores de consola (de las páginas y de los SW) y las excepciones, con su paso. Menos uno: las
  // sondas (un manifest.json, sin <link rel="icon">) hacen que Chrome pida /favicon.ico a la raíz del
  // origen, que no es de ninguna de las dos apps (sus páginas declaran su icono).
  context.on('console', (message) => {
    if (message.type() !== 'error') return;
    const where = message.location().url || message.page()?.url() || message.worker()?.url() || '?';
    if (where === `${origin}/favicon.ico`) return;
    errors.push(`paso ${step}, ${where}: ${message.text().split('\n')[0]}`);
  });
  context.on('weberror', (error) => errors.push(`paso ${step}, ${error.page()?.url() ?? '?'}: ${error.error().message}`));
  // La página desde la que se miran cachés y claves: del origen, pero fuera del ámbito de los dos SW.
  const probe = await context.newPage();
  await probe.goto(`${origin}/manifest.json`);

  // Abre `app` en una página nueva y espera a su portada pintada, con la plantilla ya resuelta.
  const open = async (app, label) => {
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    await labeled(`${label}: abrir ${app.url}`, () => page.goto(app.url));
    await painted(page, label);
    return page;
  };
  const painted = async (page, label) => {
    await waitForAsync(page, (home) => !!document.querySelector(home), HOME, { label: `${label}: la portada` });
    await waitForAsync(page, () => !document.querySelector('#contenido [data-slot]'), null, { label: `${label}: la plantilla de la portada` });
  };
  const title = (page) => page.locator(HOME).textContent();
  // Espera a que un SW mande en `page`: el de su app, que toma el mando (clients.claim) al acabar de
  // instalarse con su precache. Qué cachés dejó lo dicen después las fotos, con su diagnóstico.
  const controlled = (page, label) => waitForAsync(page, () => !!navigator.serviceWorker.controller, null, { label });
  // Espera a que la portada tenga sus escudos (también los diferidos): con el SW al mando, cada uno ya está
  // en su caché de escudos al llegar a la página.
  const crestsLoaded = async (page, label) => {
    await page.evaluate(() => document.querySelectorAll('#contenido img.crest[loading="lazy"]').forEach((img) => { img.loading = 'eager'; }));
    await waitForAsync(page, () => {
      const imgs = [...document.querySelectorAll('#contenido img.crest')];
      return imgs.some((img) => img.naturalWidth > 0) && imgs.every((img) => img.complete);
    }, null, { label });
  };
  const run = async (n, label, fn) => {
    step = n;
    try {
      await fn();
    } catch (error) {
      error.message = `paso ${n} (${label}): ${error.message}`;
      throw error;
    }
    console.log(`paso ${n}: ${label}: ok`);
  };

  // ── 1. v1 instalada, con su estado ──────────────────────────────────────────────────────────────
  let s1;
  await run(1, 'v1 instalada con su equipo, un jugador seguido y sus claves', async () => {
    const page = await open(v1, 'v1, 1.ª apertura');
    await controlled(page, 'v1, su SW al mando');
    await page.evaluate((state) => { for (const [key, value] of Object.entries(state)) localStorage.setItem(key, value); }, V1_STATE);
    // Con su SW al mando, la portada de su equipo: guarda sus escudos en la caché aparte.
    await labeled('v1, recargar', () => page.reload());
    await painted(page, 'v1 con su equipo');
    assert.equal(await title(page), V1_TEAM.name, 'v1 no enseña su equipo');
    assert.equal(await page.locator(PLAYER_LINK).count(), 1, 'v1 no enseña su jugador seguido');
    await crestsLoaded(page, 'v1, sus escudos');
    await page.close();
    s1 = await quiet(probe, 'v1 instalada');
    checkOwners(s1, apps, 'v1 instalada');
    assert.deepEqual(Object.keys(s1.caches).sort(), [v1.crests(), v1.data()].sort(), 'las cachés de v1');
    assert.deepEqual(pick(s1.keys, v2.ownsKey), {}, 'claves de v2 antes de abrir v2');
    for (const [key, value] of Object.entries(V1_STATE)) assert.equal(s1.keys[key], value, `la clave ${key} de v1`);
  });

  // ── 2. v2 instalada en el mismo origen ──────────────────────────────────────────────────────────
  let s2;
  await run(2, 'v2 instalada: lo de v1, intacto; cachés futbolbase2-; trae el equipo y los seguidos de v1', async () => {
    const page = await open(v2, 'v2, 1.ª apertura');
    assert.equal(await title(page), V1_TEAM.name, 'v2 no trae el equipo de v1 en su 1.ª apertura');
    await controlled(page, 'v2, su SW al mando');
    await labeled('v2, recargar', () => page.reload());
    await painted(page, 'v2 con su SW');
    assert.equal(await title(page), V1_TEAM.name, 'v2 no enseña el equipo traído de v1');
    assert.equal(await page.locator(PLAYER_LINK).count(), 1, 'v2 no enseña el jugador seguido traído de v1');
    await crestsLoaded(page, 'v2, sus escudos');
    await page.close();
    s2 = await quiet(probe, 'v2 instalada');
    checkUntouched(v1, s1, s2, 'tras abrir v2');
    const mine = Object.keys(s2.caches).filter((name) => !Object.hasOwn(s1.caches, name));
    assert.deepEqual(mine.filter((name) => !name.startsWith(v2.prefix)), [], 'cachés de v2 que no empiezan por futbolbase2-');
    assert.deepEqual(mine.sort(), [v2.crests(), v2.data()].sort(), 'las cachés de v2');
    checkOwners(s2, apps, 'v2 instalada');
    assert.equal(s2.keys['fb2:almacen'], s1.keys['futbol-base:v2'], 'fb2:almacen no es el almacén de v1');
    assert.equal(s2.keys['fb2:jugadores'], s1.keys['futbol-base:jugadores'], 'fb2:jugadores no son los seguidos de v1');
  });

  // ── 3. «Borrar datos de esta app» en v2 ─────────────────────────────────────────────────────────
  let s3;
  await run(3, '«Borrar datos» de v2: lo de v1, intacto; quedan fb2:importado y fb2:codigo; al recargar, el equipo por defecto', async () => {
    const page = await open(v2, 'v2, antes de borrar');
    await page.evaluate(() => { location.hash = '#/ajustes'; });
    await labeled('v2, Ajustes', () => page.locator('#contenido section[data-screen="ajustes"]').waitFor());
    await labeled('v2, «Borrar datos de esta app»', () => page.click('#contenido button[data-action="borrar-datos"]'));
    await labeled('v2, «Borrar»', () => page.click('#ajustes-borrar button[data-action="confirmar-borrado"]'));
    await waitForAsync(page, () => localStorage.getItem('fb2:almacen') === null && localStorage.getItem('fb2:jugadores') === null, null,
      { label: 'v2, el borrado' });
    const cleared = await quiet(probe, 'v2 tras borrar');
    checkUntouched(v1, s2, cleared, 'tras «Borrar datos» de v2');
    assert.deepEqual(Object.keys(pick(cleared.keys, v2.ownsKey)).sort(), ['fb2:codigo', 'fb2:importado'], 'lo que queda de fb2:');
    await page.evaluate(() => { location.hash = '#/'; });
    await labeled('v2, recargar tras borrar', () => page.reload());
    await painted(page, 'v2 tras borrar y recargar');
    assert.equal(await title(page), v2.defaultTeam, 'tras borrar y recargar, v2 no enseña el equipo por defecto');
    assert.equal(await page.locator(PLAYER_LINK).count(), 0, 'tras borrar y recargar, v2 sigue con el jugador de v1');
    await page.close();
    s3 = await quiet(probe, 'v2 recargada tras borrar');
    checkUntouched(v1, s2, s3, 'tras recargar v2');
    checkOwners(s3, apps, 'tras borrar');
  });

  // Una subida de `app`: la abre como quien recarga (su index.html pide la actualización), espera sin
  // ninguna página suya abierta a que su SW nuevo mande con su caché de datos nueva (takeOver), la abre
  // con él y devuelve la foto de después, con la de antes.
  const publish = async (app, label) => {
    const before = await quiet(probe, `${label}, antes`);
    assert.deepEqual(Object.keys(pick(before.caches, (name) => name.startsWith(app.prefix))).sort(), [app.crests(), app.data()].sort(),
      `${label}: las cachés de ${app.id} antes de la subida`);
    app.published = true;
    let page = await open(app, `${label}, la recarga`);
    await page.close();
    await takeOver(context, `${app.url}manifest.json`, app.data(app.next), `${label}, el SW nuevo al mando`);
    page = await open(app, `${label}, con el SW nuevo`);
    await crestsLoaded(page, `${label}, sus escudos con el SW nuevo`);
    await page.close();
    return { before, after: await quiet(probe, `${label}, después`) };
  };

  // ── 4. Subida de v1 ─────────────────────────────────────────────────────────────────────────────
  await run(4, 'subida de v1: su SW nuevo borra sus cachés viejas y las de v2 siguen', async () => {
    const { before, after } = await publish(v1, 'subida de v1');
    const left = Object.keys(pick(after.caches, (name) => name.startsWith(v1.prefix))).sort();
    assert.deepEqual(left, [v1.crests(v1.nextSeal), v1.data(v1.next)].sort(), 'las cachés de v1 tras su subida (las viejas, fuera)');
    checkUntouched(v2, before, after, 'tras la subida de v1');
    checkOwners(after, apps, 'tras la subida de v1');
  });

  // ── 5. Subida de v2 ─────────────────────────────────────────────────────────────────────────────
  await run(5, 'subida de v2: su SW nuevo borra sus cachés viejas y las de v1 siguen', async () => {
    const { before, after } = await publish(v2, 'subida de v2');
    const left = Object.keys(pick(after.caches, (name) => name.startsWith(v2.prefix))).sort();
    assert.deepEqual(left, [v2.crests(v2.nextSeal), v2.data(v2.next)].sort(), 'las cachés de v2 tras su subida (las viejas, fuera)');
    checkUntouched(v1, before, after, 'tras la subida de v2');
    checkOwners(after, apps, 'tras la subida de v2');
  });

  // ── 6. Sin errores ──────────────────────────────────────────────────────────────────────────────
  step = 6;
  assert.deepEqual(errors, [], `paso 6 (errores de consola y excepciones de las dos apps):\n  ${errors.join('\n  ')}`);
  console.log('aislamiento-smoke: ok (5 pasos)');
} catch (error) {
  console.error(`aislamiento-smoke: FALLA: ${error.message}`);
  if (errors.length && step !== 6) console.error(`y errores de consola:\n  ${errors.join('\n  ')}`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  if (v1Dir) rmSync(v1Dir, { recursive: true, force: true });
}
