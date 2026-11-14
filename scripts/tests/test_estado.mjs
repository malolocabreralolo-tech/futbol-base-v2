// El aviso de estado de la portada (src/estado.js) y la salud fresca que lo alimenta (ensureHealth y
// healthNeeds de src/state.js). Las frases no llevan datos: el aviso nunca enseña un nombre.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { UMBRAL_VENTANA_H, UMBRAL_BASE_H, enVentana, estadoDatos, statusNotice } from '../../src/estado.js';

const TZ = 'Atlantic/Canary';
const H = 3600000;
const MIN = 60000;
const FALLO = 'La última actualización de los datos falló.';
const PENDIENTES = 'Hay competiciones o fases publicadas que aún no están cargadas.';
const viejo = (n) => `Los datos llevan ${n} sin comprobarse.`;

// Un sábado a mediodía de Canarias (en ventana) y un miércoles a mediodía (fuera), en invierno (UTC+0).
const SABADO = new Date('2026-11-14T12:00:00Z');
const MIERCOLES = new Date('2026-11-18T12:00:00Z');
const hace = (now, ms) => new Date(now.getTime() - ms).toISOString();
const sana = (now) => ({ version: 1, runHealth: { ok: true }, checkedAt: hace(now, H), activation: { failed: [] } });

test('umbrales: 4 h en las ventanas del bot y 8 h fuera', () => {
  assert.equal(UMBRAL_VENTANA_H, 4);
  assert.equal(UMBRAL_BASE_H, 8);
});

test('enVentana: viernes de 18:00 a 24:00 y sábado y domingo de 10:00 a 24:00, hora de Canarias (invierno, UTC+0)', () => {
  const at = (iso) => enVentana(new Date(iso), TZ);
  assert.equal(at('2026-11-13T17:59:00Z'), false, 'viernes 17:59');
  assert.equal(at('2026-11-13T18:00:00Z'), true, 'viernes 18:00');
  assert.equal(at('2026-11-13T23:59:00Z'), true, 'viernes 23:59');
  assert.equal(at('2026-11-14T09:59:00Z'), false, 'sábado 09:59');
  assert.equal(at('2026-11-14T10:00:00Z'), true, 'sábado 10:00');
  assert.equal(at('2026-11-14T23:59:00Z'), true, 'sábado 23:59');
  assert.equal(at('2026-11-15T10:00:00Z'), true, 'domingo 10:00');
  assert.equal(at('2026-11-16T00:00:00Z'), false, 'lunes 00:00');
  assert.equal(at('2026-11-18T20:00:00Z'), false, 'miércoles 20:00');
});

test('enVentana: en verano (UTC+1) cuenta la hora de Canarias, no la UTC', () => {
  const at = (iso) => enVentana(new Date(iso), TZ);
  assert.equal(at('2026-07-03T16:59:00Z'), false, 'viernes 17:59 de Canarias');
  assert.equal(at('2026-07-03T17:00:00Z'), true, 'viernes 18:00 de Canarias');
  assert.equal(at('2026-07-04T08:59:00Z'), false, 'sábado 09:59 de Canarias');
  assert.equal(at('2026-07-04T09:00:00Z'), true, 'sábado 10:00 de Canarias');
  assert.equal(at('2026-07-04T22:59:00Z'), true, 'sábado 23:59 de Canarias');
  assert.equal(at('2026-07-05T09:00:00Z'), true, 'domingo 10:00 de Canarias');
  assert.equal(at('2026-07-05T23:00:00Z'), false, 'lunes 00:00 de Canarias');
});

test('estadoDatos: sana y reciente, nada; sin comprobar más que el umbral, la frase con las horas o los días', () => {
  assert.deepEqual(estadoDatos(sana(SABADO), SABADO, TZ), []);
  assert.deepEqual(estadoDatos({ ...sana(SABADO), checkedAt: hace(SABADO, 4 * H + MIN) }, SABADO, TZ), [viejo('4 h')], 'en ventana: 4 h 01 min');
  assert.deepEqual(estadoDatos({ ...sana(SABADO), checkedAt: hace(SABADO, 4 * H) }, SABADO, TZ), [], 'en ventana: 4 h justas no pasan del umbral');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 7 * H + 59 * MIN) }, MIERCOLES, TZ), [], 'fuera: 7 h 59 min');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 8 * H + MIN) }, MIERCOLES, TZ), [viejo('8 h')], 'fuera: 8 h 01 min');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 47 * H + 59 * MIN) }, MIERCOLES, TZ), [viejo('47 h')]);
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 50 * H) }, MIERCOLES, TZ), [viejo('2 días')], 'desde 48 h, en días');
});

test('estadoDatos: sin conexión (fromCache) nunca dice «sin comprobarse»; sin checkedAt válido, tampoco', () => {
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 50 * H), fromCache: true }, MIERCOLES, TZ), []);
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: 'ayer' }, MIERCOLES, TZ), []);
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: undefined }, MIERCOLES, TZ), []);
  // Sin instante válido (un ctx hecho a mano, sin now), tampoco: no hay con qué medir.
  const vieja = { ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 50 * H) };
  for (const now of [undefined, null, new Date('x'), '2026-11-18']) assert.deepEqual(estadoDatos(vieja, now, TZ), [], String(now));
  assert.deepEqual(estadoDatos({ ...vieja, runHealth: { ok: false } }, undefined, TZ), [FALLO], 'lo demás, igual');
});

test('estadoDatos: la pasada en rojo y lo publicado sin cargar, cada una con su frase y en su orden', () => {
  const base = sana(MIERCOLES);
  assert.deepEqual(estadoDatos({ ...base, runHealth: { ok: false, reasons: ['x'] } }, MIERCOLES, TZ), [FALLO]);
  assert.deepEqual(estadoDatos({ ...base, newGroups: [{ id: '1', name: 'G' }] }, MIERCOLES, TZ), [PENDIENTES]);
  assert.deepEqual(estadoDatos({ ...base, newCompetitions: [{ id: '2', name: 'C' }] }, MIERCOLES, TZ), [PENDIENTES]);
  assert.deepEqual(estadoDatos({ ...base, activation: { failed: [{ competition: '3', name: 'C', reason: 'r' }] } }, MIERCOLES, TZ), [PENDIENTES]);
  assert.deepEqual(estadoDatos({ ...base, activation: { failed: [] }, newGroups: [], newCompetitions: [] }, MIERCOLES, TZ), []);
  const todas = { ...base, runHealth: { ok: false, reasons: ['x'] }, checkedAt: hace(MIERCOLES, 9 * H), newGroups: [{ id: '1' }] };
  assert.deepEqual(estadoDatos(todas, MIERCOLES, TZ), [FALLO, viejo('9 h'), PENDIENTES]);
});

test('estadoDatos: sin objeto de salud, nada', () => {
  for (const health of [null, undefined, {}, 'x', 3]) assert.deepEqual(estadoDatos(health, MIERCOLES, TZ), [], String(health));
});

test('statusNotice: el aviso exacto con las frases en negrita y el enlace a Datos y fuentes; nada sin frases', () => {
  const roja = { ...sana(MIERCOLES), runHealth: { ok: false, reasons: ['x'] }, checkedAt: hace(MIERCOLES, 9 * H) };
  assert.equal(String(statusNotice(roja, MIERCOLES, TZ)),
    `<p class="notice home-status" role="status"><b>${FALLO} ${viejo('9 h')}</b> <a class="more" href="#/fuentes">Ver datos y fuentes</a></p>`);
  assert.equal(String(statusNotice(sana(MIERCOLES), MIERCOLES, TZ)), '');
  assert.equal(String(statusNotice(null, MIERCOLES, TZ)), '');
});

test('statusNotice: un nombre de los datos nunca llega al aviso', () => {
  const out = String(statusNotice({ ...sana(MIERCOLES), newGroups: [{ id: '1', name: '<b>G</b>', competitionName: 'A & B' }],
    activation: { failed: [{ competition: '3', name: '<script>', reason: '<i>' }] } }, MIERCOLES, TZ));
  assert.equal(out, `<p class="notice home-status" role="status"><b>${PENDIENTES}</b> <a class="more" href="#/fuentes">Ver datos y fuentes</a></p>`);
});

// ── ensureHealth y healthNeeds (src/state.js) ───────────────────────────
// Cada prueba usa su propia copia del módulo (otra URL), con su memoria vacía, y una red falsa.
let copia = 0;
const freshState = () => import(`../../src/state.js?estado=${++copia}`);
const SALUD = { version: 1, checkedAt: '2026-11-14T21:01:42+00:00', runHealth: { ok: true } };

function fakeNet(t) {
  const net = { calls: 0, mode: 'ok', origin: null };
  t.mock.method(console, 'warn', () => {});
  t.mock.method(globalThis, 'fetch', async () => {
    net.calls += 1;
    if (net.mode === 'down') throw new TypeError('Failed to fetch');
    const headers = { get: (name) => (name.toLowerCase() === 'x-fb2-origen' ? net.origin : null) };
    return { ok: true, status: 200, headers, text: async () => JSON.stringify(SALUD) };
  });
  return net;
}

test('ensureHealth: dos llamadas seguidas, una petición; pasados 10 min 01 s, otra (HEALTH_TTL_MS)', async (t) => {
  const state = await freshState();
  const net = fakeNet(t);
  let clock = 1_000_000;
  const now = () => clock;
  assert.equal(state.HEALTH_TTL_MS, 600000);
  const a = await state.ensureHealth({ now });
  const b = await state.ensureHealth({ now });
  assert.equal(a, b);
  assert.equal(net.calls, 1);
  clock += 10 * MIN;
  await state.ensureHealth({ now });
  assert.equal(net.calls, 1, 'a los 10 min justos, todavía la misma');
  clock += 1000;
  const c = await state.ensureHealth({ now });
  assert.equal(net.calls, 2, '10 min 01 s después, otra petición');
  assert.equal(c.checkedAt, SALUD.checkedAt);
  assert.equal(c.fromCache, undefined, 'de la red: sin fromCache');
});

test('ensureHealth: un solo vuelo también al refrescar', async (t) => {
  const state = await freshState();
  const net = fakeNet(t);
  const [a, b] = await Promise.all([state.ensureHealth(), state.ensureHealth()]);
  assert.equal(a, b);
  assert.equal(net.calls, 1);
});

test('ensureHealth: la copia del service worker (x-fb2-origen: cache) llega con fromCache: true', async (t) => {
  const state = await freshState();
  const net = fakeNet(t);
  net.origin = 'cache';
  const health = await state.ensureHealth();
  assert.equal(health.fromCache, true);
  assert.equal(health.checkedAt, SALUD.checkedAt);
});

test('ensureHealth: si falla un refresco tras un éxito, el anterior con fromCache: true; sin anterior, null', async (t) => {
  const state = await freshState();
  const net = fakeNet(t);
  let clock = 0;
  const now = () => clock;
  net.mode = 'down';
  assert.equal(await state.ensureHealth({ now }), null, 'sin anterior: null');
  net.mode = 'ok';
  const first = await state.ensureHealth({ now });
  assert.equal(first.fromCache, undefined);
  clock += 11 * MIN;
  net.mode = 'down';
  const stale = await state.ensureHealth({ now });
  assert.equal(stale.fromCache, true);
  assert.equal(stale.checkedAt, SALUD.checkedAt);
  assert.equal(first.fromCache, undefined, 'el anterior no se toca');
});

test('healthNeeds: pide sin salud; no con la de hace 5 min; sí con la de hace 11 min; y la guarda con su hora', async () => {
  const state = await freshState();
  let asked = 0;
  const ensure = async () => { asked += 1; return SALUD; };
  const clock = 50 * MIN;
  const now = () => clock;
  const datasets = { health: undefined };
  const load = state.healthNeeds(datasets, { ensure, now });
  assert.ok(load && typeof load.then === 'function');
  await load;
  assert.equal(datasets.health, SALUD);
  assert.equal(datasets.healthAt, clock);
  assert.equal(state.healthNeeds({ health: SALUD, healthAt: clock - 5 * MIN }, { ensure, now }), null, 'de hace 5 min: nada');
  const old = { health: SALUD, healthAt: clock - 11 * MIN };
  await state.healthNeeds(old, { ensure, now });
  assert.equal(old.healthAt, clock);
  assert.equal(asked, 2);
  // Un fallo (null) también lleva su hora: no se vuelve a esperar hasta pasados los 10 min.
  const failed = { health: undefined };
  await state.healthNeeds(failed, { ensure: async () => null, now });
  assert.equal(failed.health, null);
  assert.equal(state.healthNeeds(failed, { ensure, now }), null);
});
