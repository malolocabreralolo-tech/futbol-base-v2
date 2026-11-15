// v1 y v2 en el mismo origen, con sus service workers de verdad: Cache Storage y localStorage son del
// origen (malolocabreralolo-tech.github.io), no de la ruta, así que esta prueba abre las dos apps en un
// Chrome real y comprueba que ninguna toca lo de la otra, tampoco cuando una se actualiza.
// v1 es el código y los datos reales de v1 en V1_COMMIT, sacados con git archive a una carpeta temporal y
// servidos bajo /futbol-base/; v2, el árbol de trabajo, bajo /futbol-base-v2/ (pages-server.mjs).
//   1. v1 instalada, con su equipo (el primero de prebenjamín de sus datos que no es el de por defecto), un
//      jugador seguido y sus claves antiguas (season, cat, theme).
//   2. v2 instalada: lo de v1 sigue igual; las cachés de v2 son futbolbase2-* (su precache incluido);
//      trae el equipo y los seguidos de v1 a fb2:almacen y fb2:jugadores.
//   3. «Borrar datos de esta app» en v1: lo de v2 sigue igual; de v1 solo queda futbol-base:codigo; al
//      recargar, su equipo por defecto.
//   4. «Borrar datos de esta app» en v2: lo de v1 sigue igual; de fb2: solo queda fb2:importado; al
//      recargar, el equipo por defecto.
//   5. Subida de v1 (otra versión y otro sello de escudos en sw.js e index.html): su SW nuevo borra sus
//      cachés viejas, y lo de v2 sigue igual.
//   6. Subida de v2, igual: borra sus viejas, en su precache deja solo lo del manifiesto nuevo, y lo de v1
//      sigue igual.
//   7. Cambio de CODIGO de v1 con su SW al mando: la limpieza del arranque de su index.html quita src/*.js
//      y las hojas de su caché vieja, y nada de v2 (v2 ya no tiene esa limpieza: su SW instala por
//      contenido).
//   8. Ni un error de consola ni una excepción en las dos apps.
// Cada caché del origen tiene que ser de una de las dos por su nombre y guardar solo lo de su ruta.
// Sin Chrome o sin el commit de v1, falla: esta prueba no se salta.
//
// npm install --no-save --package-lock=false playwright@1.58.0
// node scripts/tests/aislamiento-smoke.mjs
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
import { findChrome } from './render-smoke.mjs';
import { labeled, takeOver, waitForAsync } from './browser-wait.mjs';
import { startPagesServer } from './pages-server.mjs';
import { PORTAL } from '../../src/config.js';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
// El commit de v1 del que nació v2: su código y sus datos son los que tiene publicados v1.
const V1_COMMIT = 'c47a1caaddd19b8000b394487fb0eb4ef25c59d2';
// El estado de v1 en este navegador: su equipo (de sus datos, lo elige extractV1), un jugador seguido y las
// claves antiguas que v1 aún borra con su «Borrar datos».
const v1State = (team) => ({
  'futbol-base:v2': JSON.stringify({ myTeam: team, recent: [{ s: '2026-2027', g: 'PG2', t: 'AD Huracán' }] }),
  'futbol-base:jugadores': JSON.stringify([{ id: '900001', n: 'PRUEBA PRUEBA, JUGADOR' }]),
  season: '2025-2026',
  cat: 'benjamin',
  theme: 'dark',
});
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
// Su equipo en la prueba, de sus datos y no fijo: el primero de prebenjamín que no es el de por defecto.
function extractV1(dir) {
  const has = () => git(['cat-file', '-e', `${V1_COMMIT}^{commit}`]).status === 0;
  // En CI el clon es de un solo commit: se trae el de v1, y si no llega, la prueba falla.
  if (!has()) git(['fetch', '--quiet', '--depth', '1', 'origin', V1_COMMIT], { stdio: 'inherit' });
  assert.ok(has(), `el commit de v1 (${V1_COMMIT}) no está en el clon ni se pudo traer de origin`);
  const show = (file) => execFileSync('git', ['show', `${V1_COMMIT}:${file}`], { cwd: ROOT, encoding: 'utf8' });
  const sw = show('sw.js');
  const config = JSON.parse(show('src/config.js').replace(/^export const PORTAL = /, '').replace(/;\s*$/, ''));
  const data = [...sw.matchAll(/'\.\/(data-[^']+)'/g)].map((m) => m[1]);
  const groups = runInNewContext(`${show('data-prebenjamin.js')};PREBENJAMIN`);
  const team = groups.flatMap((group) => (group.standings || []).map((row) => ({ name: row[1], season: config.season, cat: 'prebenjamin', groupId: group.id })))
    .find((candidate) => candidate.name !== config.defaultTeam.name);
  assert.ok(team, 'los datos de prebenjamín de v1 no tienen ningún equipo que no sea el de por defecto');
  const lineups = [...new Set([config.defaultTeam.groupId, team.groupId])].map((group) => `data-lineups-${config.season}-${group}.js`);
  const paths = ['index.html', 'sw.js', 'manifest.json', 'acta.css', 'src', 'fonts', 'icons', 'escudos', ...data, ...lineups];
  const tar = execFileSync('git', ['archive', '--format=tar', V1_COMMIT, '--', ...paths], { cwd: ROOT, maxBuffer: 1 << 28 });
  execFileSync('tar', ['-x', '-C', dir], { input: tar });
  return { ...versionsOf(sw), defaultTeam: config.defaultTeam.name, team };
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
  const { team: V1_TEAM, ...v1Real } = extractV1(v1Dir);
  const V1_STATE = v1State(V1_TEAM);
  const v2Real = versionsOf(readFileSync(join(ROOT, 'sw.js'), 'utf8'));
  // Cada app: su ruta, el prefijo de sus cachés, sus claves (y la del CODIGO que vio por última vez), su
  // versión y la de su subida.
  const v1 = { id: 'v1', path: '/futbol-base/', prefix: 'futbolbase-', ownsKey: (key) => !key.startsWith('fb2:'), codigoKey: 'futbol-base:codigo',
    ...v1Real, next: '20991231a', nextSeal: 'c1c1c1c1', published: false };
  const v2 = { id: 'v2', path: '/futbol-base-v2/', prefix: 'futbolbase2-', ownsKey: (key) => key.startsWith('fb2:'),
    ...v2Real, defaultTeam: PORTAL.defaultTeam.name, next: '20991231b', nextSeal: 'c2c2c2c2', published: false, fixed: ['futbolbase2-precache'] };
  v1.fixed = [];
  const apps = [v1, v2];
  for (const app of apps) {
    app.data = (version = app.version) => `${app.prefix}v${version}`;
    app.crests = (seal = app.seal) => `${app.prefix}escudos-${seal}`;
  }
  assert.notEqual(V1_TEAM.name, v1.defaultTeam, 'el equipo de v1 tiene que ser otro que el de por defecto');

  // Una subida: el servidor da otra versión de los datos y otro sello de escudos en sw.js e index.html,
  // como el bot (y build_crests.py) al publicar; así se activan las dos ramas de la limpieza del SW. En el
  // sw.js de v2, también la huella del index.html subido, como precache.py: si no, no se instalaría.
  const bySite = { '/futbol-base': v1, '/futbol-base-v2': v2 };
  const bump = (app, text) => text.replaceAll(app.version, app.next).replace(`-escudos-${app.seal}'`, `-escudos-${app.nextSeal}'`);
  const huella = (text) => createHash('sha1').update(text).digest('hex').slice(0, 8);
  const transform = ({ site, path, body }) => {
    const app = bySite[site];
    if (!app.published || (path !== 'sw.js' && path !== 'index.html')) return undefined;
    const text = bump(app, body.toString());
    if (app !== v2 || path !== 'sw.js') return text;
    return text.replace(/^  "index\.html": "[0-9a-f]{8}",$/m, `  "index.html": "${huella(bump(v2, readFileSync(join(ROOT, 'index.html'), 'utf8')))}",`);
  };
  // Las claves del precache que tiene que dejar el SW de v2: las de su manifiesto, tal como lo sirve el servidor.
  const precacheKeys = () => {
    const sw = readFileSync(join(ROOT, 'sw.js'), 'utf8');
    const served = transform({ site: '/futbol-base-v2', path: 'sw.js', body: Buffer.from(sw) }) ?? sw;
    const block = served.slice(served.indexOf('const PRECACHE = {'), served.indexOf('const OPCIONALES'));
    return [...block.matchAll(/^  "([^"]+)": "([0-9a-f]{8})",$/gm)].map(([, ruta, h]) => `${v2.path}${ruta}?h=${h}`).sort();
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
    assert.deepEqual(mine.sort(), [v2.crests(), v2.data(), ...v2.fixed].sort(), 'las cachés de v2');
    assert.deepEqual(s2.caches['futbolbase2-precache'], precacheKeys(), 'el precache de v2: su manifiesto entero');
    checkOwners(s2, apps, 'v2 instalada');
    assert.equal(s2.keys['fb2:almacen'], s1.keys['futbol-base:v2'], 'fb2:almacen no es el almacén de v1');
    assert.equal(s2.keys['fb2:jugadores'], s1.keys['futbol-base:jugadores'], 'fb2:jugadores no son los seguidos de v1');
  });

  // «Borrar datos de esta app» en `app`: desde Ajustes, hasta que se van `gone` (sus claves del almacén y de
  // los seguidos). Devuelve la página, abierta en Ajustes.
  const clearData = async (app, gone) => {
    const page = await open(app, `${app.id}, antes de borrar`);
    await page.evaluate(() => { location.hash = '#/ajustes'; });
    await labeled(`${app.id}, Ajustes`, () => page.locator('#contenido section[data-screen="ajustes"]').waitFor());
    await labeled(`${app.id}, «Borrar datos de esta app»`, () => page.click('#contenido button[data-action="borrar-datos"]'));
    await labeled(`${app.id}, «Borrar»`, () => page.click('#ajustes-borrar button[data-action="confirmar-borrado"]'));
    await waitForAsync(page, (keys) => keys.every((key) => localStorage.getItem(key) === null), gone, { label: `${app.id}, el borrado` });
    return page;
  };
  // Tras borrar, vuelve a la portada y recarga: el equipo por defecto de `app`, sin el jugador seguido.
  const reloadedDefault = async (page, app) => {
    await page.evaluate(() => { location.hash = '#/'; });
    await labeled(`${app.id}, recargar tras borrar`, () => page.reload());
    await painted(page, `${app.id} tras borrar y recargar`);
    assert.equal(await title(page), app.defaultTeam, `tras borrar y recargar, ${app.id} no enseña el equipo por defecto`);
    assert.equal(await page.locator(PLAYER_LINK).count(), 0, `tras borrar y recargar, ${app.id} sigue con el jugador seguido`);
  };

  // ── 3. «Borrar datos de esta app» en v1, con v2 instalada ───────────────────────────────────────
  let s3;
  await run(3, '«Borrar datos» de v1: lo de v2, intacto; de v1 queda futbol-base:codigo; al recargar, su equipo por defecto', async () => {
    const page = await clearData(v1, ['futbol-base:v2', 'futbol-base:jugadores']);
    const cleared = await quiet(probe, 'v1 tras borrar');
    checkUntouched(v2, s2, cleared, 'tras «Borrar datos» de v1');
    assert.deepEqual(Object.keys(pick(cleared.keys, v1.ownsKey)).sort(), [v1.codigoKey], 'lo que queda de v1');
    await reloadedDefault(page, v1);
    await page.close();
    s3 = await quiet(probe, 'v1 recargada tras borrar');
    checkUntouched(v2, s2, s3, 'tras recargar v1');
    checkOwners(s3, apps, 'tras borrar en v1');
  });

  // ── 4. «Borrar datos de esta app» en v2 ─────────────────────────────────────────────────────────
  let s4;
  await run(4, '«Borrar datos» de v2: lo de v1, intacto; queda fb2:importado; al recargar, el equipo por defecto', async () => {
    const page = await clearData(v2, ['fb2:almacen', 'fb2:jugadores']);
    const cleared = await quiet(probe, 'v2 tras borrar');
    checkUntouched(v1, s3, cleared, 'tras «Borrar datos» de v2');
    assert.deepEqual(Object.keys(pick(cleared.keys, v2.ownsKey)).sort(), ['fb2:importado'], 'lo que queda de fb2:');
    await reloadedDefault(page, v2);
    await page.close();
    s4 = await quiet(probe, 'v2 recargada tras borrar');
    checkUntouched(v1, s3, s4, 'tras recargar v2');
    checkOwners(s4, apps, 'tras borrar en v2');
  });

  // Una subida de `app`: la abre como quien recarga (su index.html pide la actualización), espera sin
  // ninguna página suya abierta a que su SW nuevo mande con su caché de datos nueva (takeOver), la abre
  // con él y devuelve la foto de después, con la de antes.
  const publish = async (app, label) => {
    const before = await quiet(probe, `${label}, antes`);
    assert.deepEqual(Object.keys(pick(before.caches, (name) => name.startsWith(app.prefix))).sort(), [app.crests(), app.data(), ...app.fixed].sort(),
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

  // ── 5. Subida de v1 ─────────────────────────────────────────────────────────────────────────────
  await run(5, 'subida de v1: su SW nuevo borra sus cachés viejas y las de v2 siguen', async () => {
    const { before, after } = await publish(v1, 'subida de v1');
    const left = Object.keys(pick(after.caches, (name) => name.startsWith(v1.prefix))).sort();
    assert.deepEqual(left, [v1.crests(v1.nextSeal), v1.data(v1.next)].sort(), 'las cachés de v1 tras su subida (las viejas, fuera)');
    checkUntouched(v2, before, after, 'tras la subida de v1');
    checkOwners(after, apps, 'tras la subida de v1');
  });

  // ── 6. Subida de v2 ─────────────────────────────────────────────────────────────────────────────
  await run(6, 'subida de v2: su SW nuevo borra sus cachés viejas y las de v1 siguen', async () => {
    const { before, after } = await publish(v2, 'subida de v2');
    const left = Object.keys(pick(after.caches, (name) => name.startsWith(v2.prefix))).sort();
    assert.deepEqual(left, [v2.crests(v2.nextSeal), v2.data(v2.next), ...v2.fixed].sort(), 'las cachés de v2 tras su subida (las viejas, fuera)');
    assert.deepEqual(after.caches['futbolbase2-precache'], precacheKeys(), 'el precache de v2: solo su manifiesto nuevo');
    assert.notDeepEqual(before.caches['futbolbase2-precache'], after.caches['futbolbase2-precache'], 'el index.html subido, con su huella nueva');
    checkUntouched(v1, before, after, 'tras la subida de v2');
    checkOwners(after, apps, 'tras la subida de v2');
  });

  // ── 7. Cambio de CODIGO de v1 con su SW al mando ────────────────────────────────────────────────
  // Tras publicar código, la primera apertura de v1 con su SW al mando (y otro CODIGO apuntado en este
  // navegador) quita src/*.js y las hojas de sus cachés de datos que no son las de su versión: la limpieza
  // del arranque de su index.html. v1 y v2, cada una con una caché vieja con código, datos, su página y un
  // icono: v1 deja en la suya lo que no es código, y lo de v2 (su precache incluido) no cambia.
  const OLD = '20000101a';
  const oldFiles = ['src/app.js', 'src/store.js', `acta.css?v=${OLD}`, `data-seasons.js?v=${OLD}`, 'index.html', 'icons/icon-192.png'];
  const isCode = (path) => /\/src\/[^/]+\.js$|\.css$/.test(path.split('?')[0]);
  await run(7, 'cambio de CODIGO de v1: quita src/*.js y las hojas de su caché vieja, y nada de v2', async () => {
    const [app, other] = [v1, v2];
    const label = 'cambio de CODIGO en v1';
    await probe.evaluate(async ({ old, key }) => {
      for (const { name, urls } of old) {
        const cache = await caches.open(name);
        for (const url of urls) await cache.put(url, new Response('de la versión vieja'));
      }
      localStorage.setItem(key, 'otro');
    }, { old: apps.map((a) => ({ name: a.data(OLD), urls: oldFiles.map((file) => `${a.path}${file}`) })), key: app.codigoKey });
    const before = await quiet(probe, `${label}, antes`);
    const page = await open(app, label);
    // El arranque apunta su CODIGO tras la limpieza y tras start(): entonces ya ha quitado lo que quitaba.
    await waitForAsync(page, (key) => localStorage.getItem(key) !== 'otro', app.codigoKey, { label: `${label}: su CODIGO, apuntado` });
    await page.close();
    const after = await quiet(probe, `${label}, después`);
    const old = app.data(OLD);
    assert.deepEqual(after.caches[old], before.caches[old].filter((path) => !isCode(path)), `${label}: lo que queda en su caché vieja`);
    for (const [name, entries] of Object.entries(pick(before.caches, (n) => n.startsWith(app.prefix) && n !== old))) {
      const gone = entries.filter((path) => !(after.caches[name] || []).includes(path));
      assert.deepEqual(gone, [], `${label}: la caché ${name}, que no es vieja, ha perdido entradas`);
    }
    checkUntouched(other, before, after, label);
    checkOwners(after, apps, label);
  });

  // ── 8. Sin errores ──────────────────────────────────────────────────────────────────────────────
  step = 8;
  assert.deepEqual(errors, [], `paso 8 (errores de consola y excepciones de las dos apps):\n  ${errors.join('\n  ')}`);
  console.log('aislamiento-smoke: ok (7 pasos)');
} catch (error) {
  console.error(`aislamiento-smoke: FALLA: ${error.message}`);
  if (errors.length && step !== 8) console.error(`y errores de consola:\n  ${errors.join('\n  ')}`);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  if (v1Dir) rmSync(v1Dir, { recursive: true, force: true });
}
