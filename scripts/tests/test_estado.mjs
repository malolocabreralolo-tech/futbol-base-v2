// El aviso de estado de la portada (src/estado.js) y la salud fresca que lo alimenta (ensureHealth y
// healthNeeds de src/state.js). Las frases no llevan datos: el aviso nunca enseña un nombre.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { UMBRAL_VENTANA_H, UMBRAL_BASE_H, enVentana, estadoDatos, statusNotice, avisoBase } from '../../src/estado.js';

const TZ = 'Atlantic/Canary';
const H = 3600000;
const MIN = 60000;
const FALLO = 'La última actualización de los datos falló.';
const PENDIENTES = 'Hay competiciones o fases publicadas que aún no están cargadas.';
const viejo = (n) => `Los datos llevan ${n} sin comprobarse.`;
const BASE_83 = 'La base de datos ocupa 83\u00a0MB de los 100 que admite GitHub.';

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
  assert.deepEqual(estadoDatos({ ...sana(SABADO), checkedAt: hace(SABADO, 4 * H + MIN) }, SABADO, TZ), [viejo('4\u00a0h')], 'en ventana: 4 h 01 min');
  assert.deepEqual(estadoDatos({ ...sana(SABADO), checkedAt: hace(SABADO, 4 * H) }, SABADO, TZ), [], 'en ventana: 4 h justas no pasan del umbral');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 7 * H + 59 * MIN) }, MIERCOLES, TZ), [], 'fuera: 7 h 59 min');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 8 * H + MIN) }, MIERCOLES, TZ), [viejo('8\u00a0h')], 'fuera: 8 h 01 min');
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 47 * H + 59 * MIN) }, MIERCOLES, TZ), [viejo('47\u00a0h')]);
  assert.deepEqual(estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 50 * H) }, MIERCOLES, TZ), [viejo('2\u00a0días')], 'desde 48 h, en días');
  // Entre el número y la unidad, un espacio de no separación (como percent de ui.js): nunca «10» al final
  // de una línea y «h» al principio de la siguiente. El resto de la frase, con espacios normales.
  const [frase] = estadoDatos({ ...sana(MIERCOLES), checkedAt: hace(MIERCOLES, 10 * H) }, MIERCOLES, TZ);
  assert.equal(frase, 'Los datos llevan 10\u00a0h sin comprobarse.');
  assert.equal((frase.match(/\u00a0/g) || []).length, 1);
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
  assert.deepEqual(estadoDatos(todas, MIERCOLES, TZ), [FALLO, viejo('9\u00a0h'), PENDIENTES]);
});

test('estadoDatos: sin objeto de salud, nada', () => {
  for (const health of [null, undefined, {}, 'x', 3]) assert.deepEqual(estadoDatos(health, MIERCOLES, TZ), [], String(health));
});

test('avisoBase: con base.mb entero entre 1 y 1000, la frase exacta; si no, nada', () => {
  assert.equal(avisoBase({ base: { mb: 83, limite: 100 } }), BASE_83);
  assert.equal(avisoBase({ base: { mb: 83 } }), BASE_83);
  assert.equal(avisoBase({ base: { mb: 1 } }), 'La base de datos ocupa 1\u00a0MB de los 100 que admite GitHub.');
  assert.equal(avisoBase({ base: { mb: 1000 } }), 'La base de datos ocupa 1000\u00a0MB de los 100 que admite GitHub.');
  // El límite es texto fijo: el que traiga data-health.json no llega a la frase.
  assert.equal(avisoBase({ base: { mb: 83, limite: '<b>x</b>' } }), BASE_83);
  for (const base of [{ mb: 'x' }, { mb: '83' }, { mb: 0 }, { mb: -5 }, { mb: 1001 }, { mb: 83.5 }, { mb: NaN }, { mb: Infinity }, { mb: null }, {}, null, 'grande', 83, []]) {
    assert.equal(avisoBase({ base }), null, JSON.stringify(base));
  }
  for (const health of [{}, null, undefined, 'x']) assert.equal(avisoBase(health), null, String(health));
});

test('avisoBase con la base en piezas: la pieza mayor, la común o la de una temporada; si no se entiende, la frase de siempre', () => {
  assert.equal(avisoBase({ base: { mb: 83, limite: 100, pieza: 'comun' } }),
    'La parte común de la base de datos ocupa 83 MB de los 100 que admite GitHub por fichero.');
  assert.equal(avisoBase({ base: { mb: 83, limite: 100, pieza: '2025-2026' } }),
    'La parte de 2025/26 de la base de datos ocupa 83 MB de los 100 que admite GitHub por fichero.');
  assert.equal(avisoBase({ base: { mb: 83, limite: 100 } }), BASE_83);
  for (const pieza of [null, '', 'Comun', 'actas-2025-2026.db', '2025-26', '<b>x</b>', 2025, ['comun'], {}]) {
    assert.equal(avisoBase({ base: { mb: 83, pieza } }), BASE_83, JSON.stringify(pieza));
  }
  // El tamaño manda: sin un mb que valga, nada, también con pieza.
  assert.equal(avisoBase({ base: { mb: 'x', pieza: 'comun' } }), null);
});

test('estadoDatos: el tamaño de la base, la última frase; sin la clave, como siempre', () => {
  const base = sana(MIERCOLES);
  assert.deepEqual(estadoDatos({ ...base, base: { mb: 83, limite: 100 } }, MIERCOLES, TZ), [BASE_83]);
  assert.deepEqual(estadoDatos({ ...base, base: { mb: 'x' } }, MIERCOLES, TZ), []);
  assert.deepEqual(estadoDatos({ ...base, base: {} }, MIERCOLES, TZ), []);
  assert.deepEqual(estadoDatos(base, MIERCOLES, TZ), []);
  const todas = { ...base, runHealth: { ok: false, reasons: ['x'] }, checkedAt: hace(MIERCOLES, 9 * H), newGroups: [{ id: '1' }], base: { mb: 83 } };
  assert.deepEqual(estadoDatos(todas, MIERCOLES, TZ), [FALLO, viejo('9\u00a0h'), PENDIENTES, BASE_83]);
  // Sin conexión también: no depende de cuándo se comprobó.
  assert.deepEqual(estadoDatos({ ...base, fromCache: true, base: { mb: 83 } }, MIERCOLES, TZ), [BASE_83]);
  assert.equal(String(statusNotice({ ...base, base: { mb: 83 } }, MIERCOLES, TZ)),
    `<p class="notice home-status" role="status"><b>${BASE_83}</b> <a class="more" href="#/fuentes">Ver datos y fuentes</a></p>`);
});

test('statusNotice: el aviso exacto con las frases en negrita y el enlace a Datos y fuentes; nada sin frases', () => {
  const roja = { ...sana(MIERCOLES), runHealth: { ok: false, reasons: ['x'] }, checkedAt: hace(MIERCOLES, 9 * H) };
  assert.equal(String(statusNotice(roja, MIERCOLES, TZ)),
    `<p class="notice home-status" role="status"><b>${FALLO} ${viejo('9\u00a0h')}</b> <a class="more" href="#/fuentes">Ver datos y fuentes</a></p>`);
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

test('ensureHealth: la copia del service worker (fromCache) se recuerda 30 s, no 10 min (HEALTH_TTL_COPIA_MS)', async (t) => {
  const state = await freshState();
  const net = fakeNet(t);
  let clock = 1_000_000;
  const now = () => clock;
  assert.equal(state.HEALTH_TTL_COPIA_MS, 30000);
  net.origin = 'cache';
  const a = await state.ensureHealth({ now });
  assert.equal(a.fromCache, true);
  clock += 30000;
  assert.equal(await state.ensureHealth({ now }), a, 'a los 30 s justos, la misma');
  assert.equal(net.calls, 1);
  clock += 1;
  net.origin = null;
  const b = await state.ensureHealth({ now });
  assert.equal(net.calls, 2, 'pasados los 30 s, otra petición');
  assert.equal(b.fromCache, undefined, 'la de la red, sin fromCache');
  // La de la red, otra vez los 10 min de siempre.
  clock += 5 * MIN;
  await state.ensureHealth({ now });
  assert.equal(net.calls, 2);
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

test('healthNeeds: una salud fromCache caducada (31 s) se pide sin esperarla: null, y la nueva queda en datasets', async () => {
  const state = await freshState();
  let asked = 0;
  let llegar;
  const ensure = () => { asked += 1; return new Promise((resolve) => { llegar = resolve; }); };
  const clock = 50 * MIN;
  const now = () => clock;
  const copia = { ...SALUD, fromCache: true };
  assert.equal(state.HEALTH_TTL_COPIA_MS, 30000);
  assert.equal(state.healthNeeds({ health: copia, healthAt: clock - 30000 }, { ensure, now }), null, 'a los 30 s justos: nada');
  assert.equal(asked, 0);
  const vieja = { health: copia, healthAt: clock - 31000 };
  assert.equal(state.healthNeeds(vieja, { ensure, now }), null, 'la pantalla no espera');
  assert.equal(asked, 1, 'pero se pide');
  assert.equal(vieja.health, copia, 'mientras tanto, la copia');
  const nueva = { ...SALUD, checkedAt: '2026-11-14T22:01:42+00:00' };
  llegar(nueva);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(vieja.health, nueva, 'cuando llega, la nueva');
  assert.equal(vieja.healthAt, clock);
});

test('healthNeeds: si falla la petición de fondo de una copia caducada, ningún rechazo suelto y la copia sigue', async () => {
  const state = await freshState();
  const rejected = [];
  const onRejection = (reason) => rejected.push(reason);
  process.on('unhandledRejection', onRejection);
  try {
    const clock = 50 * MIN;
    const copia = { ...SALUD, fromCache: true };
    const vieja = { health: copia, healthAt: clock - 31000 };
    assert.equal(state.healthNeeds(vieja, { ensure: () => Promise.reject(new Error('sin red')), now: () => clock }), null);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(vieja.health, copia);
    assert.equal(vieja.healthAt, clock - 31000);
  } finally {
    process.off('unhandledRejection', onRejection);
  }
  assert.deepEqual(rejected, []);
});

test('healthNeeds: sin salud, o con la de la red caducada (11 min), devuelve la promesa, que la pantalla espera', async () => {
  const state = await freshState();
  let asked = 0;
  const ensure = async () => { asked += 1; return SALUD; };
  const clock = 50 * MIN;
  const now = () => clock;
  assert.equal(state.healthNeeds({ health: SALUD, healthAt: clock - 9 * MIN }, { ensure, now }), null, 'la de la red, de hace 9 min: nada');
  const old = { health: { ...SALUD }, healthAt: clock - 11 * MIN };
  const load = state.healthNeeds(old, { ensure, now });
  assert.ok(load && typeof load.then === 'function', 'de la red caducada: una promesa');
  await load;
  assert.equal(old.health, SALUD);
  const none = { health: undefined };
  const first = state.healthNeeds(none, { ensure, now });
  assert.ok(first && typeof first.then === 'function', 'sin salud: una promesa');
  await first;
  assert.equal(none.health, SALUD);
  assert.equal(asked, 2);
});
