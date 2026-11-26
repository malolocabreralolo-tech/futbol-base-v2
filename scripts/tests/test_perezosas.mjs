// La carga perezosa de las cuatro (parte E2, tarea 3): lo que era de alevín sirve para alevín, infantil,
// cadete y juvenil, cada una en su fichero (data-<cat>.js; data-season-<S>-<cat>.js en las temporadas
// pasadas), que nunca entra en la carga inicial.
// - state.js: ensureLazy y ensureSeasonLazy (un vuelo, 404 = sin esa categoría, fallo = null reintentable),
//   lazyNeeds y loadLazySeasons; ensureAlevin y compañía, iguales.
// - router.js: needsLazy, lo que una ruta pinta con cada perezosa; una que no llega, en Explorar, deja la
//   pantalla pintada con las demás y la nombra en ctx.lazyFailed.
// - model.js: createModel con lazyOf(cat, season): la temporada, las equipaciones, los campos, los
//   estados y los goleadores de cada perezosa.
// El navegador se simula: un document con el <script> de data-seasons.js y un fetch que anota las URLs.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';

globalThis.document = {
  querySelector(selector) {
    return /data-seasons\.js/.test(String(selector))
      ? { src: 'http://127.0.0.1:8000/data-seasons.js?v=20261125a', getAttribute: (name) => (name === 'src' ? './data-seasons.js?v=20261125a' : null) }
      : null;
  },
  querySelectorAll: () => [],
  addEventListener() {},
};
const requests = [];
const files = {};
globalThis.fetch = async (url) => {
  requests.push(String(url));
  const body = files[String(url).replace(/^\.\//, '').replace(/\?.*$/, '')];
  if (body === 'red') throw new TypeError('Failed to fetch');
  if (body === 503) return { ok: false, status: 503, text: async () => 'no disponible' };
  return body == null ? { ok: false, status: 404, text: async () => '' } : { ok: true, status: 200, text: async () => body };
};
const quiet = (fn) => async () => {
  const warn = console.warn;
  console.warn = () => {};
  try { await fn(); } finally { console.warn = warn; }
};

const state = await import('../../src/state.js');
const { LAZY_CATS, createModel } = await import('../../src/model.js');
const { needsLazy, resolveParams, startRouter } = await import('../../src/router.js');
const { parseRoute } = await import('../../src/links.js');
const { html } = await import('../../src/html.js');
const { fakeBrowser } = await import('./fixtures/rediseno/fake-browser.mjs');
const { buildClubIndex } = await import('../../src/myteam.js');

const PORTAL = '2026-2027';
const PAST = '2025-2026';
const row = (pos, team, pts) => [pos, team, pts, 1, pts / 3, 0, 1 - pts / 3, 1, 0, 1];
// Un grupo crudo de la forma de BENJAMIN, con un partido en HISTORY. Equipos y nombres inventados.
const raw = (id, phase, fullName) => ({
  id, name: 'Grupo 1', fullName, phase, island: 'grancanaria', url: null, jornada: 'Jornada 1',
  standings: [row(1, 'Club Uno', 3), row(2, 'Club Dos', 0)], matches: [], standingsKind: 'source',
});
const historyOf = (id) => ({ [id]: { 'Jornada 1': [['2026-10-03', 'Club Uno', 'Club Dos', 2, 1, null, '10:00', 'CAMPO CADETE']] } });
const CADETE = {
  CADETE: [raw('CADNG1', 'Insular GC', 'LIGA CADETE INSULAR GRAN CANARIA - GRUPO 1')],
  CAD_STATS: { groups: 1, teams: 2 },
  HISTORY_CAD: historyOf('CADNG1'),
  GOL_CAD: [{ id: 'CADNG1', g: 'CADETE INSULAR GC - GRUPO 1', s: [['PRUEBA, UNO', 'Club Uno', 2, 1]] }],
  ESTADOS_CAD: { CADNG1: { 'Jornada 1': { 'Club Uno|Club Dos': ['aplazado', 'lluvia', null] } } },
  EQUIPOS_CAD: { 'Club Uno': ['VERDE', 'BLANCO', 'VERDES', 'CAMPO CADETE', 'Césped', null] },
  CAMPOS_CAD: { 'CAMPO CADETE': ['Calle 2', 'Moya', 'Césped', 'F11'] },
};
const fileOf = (consts) => Object.entries(consts).map(([k, v]) => `const ${k}=${JSON.stringify(v)};`).join('\n') + '\n';

test('el registro de las perezosas: el de model.js, con las constantes de generate_js.LAZY', () => {
  assert.deepEqual(Object.keys(state.LAZY), LAZY_CATS);
  assert.deepEqual(state.LAZY.alevin, { file: 'data-alevin.js', word: 'alevín', consts: { groups: 'ALEVIN', stats: 'ALEV_STATS', history: 'HISTORY_ALEV', gol: 'GOL_ALEV', estados: 'ESTADOS_ALEV', equipos: 'EQUIPOS_ALEV' } });
  assert.deepEqual(state.LAZY.infantil.consts, { groups: 'INFANTIL', stats: 'INF_STATS', history: 'HISTORY_INF', gol: 'GOL_INF', estados: 'ESTADOS_INF', equipos: 'EQUIPOS_INF', campos: 'CAMPOS_INF' });
  assert.equal(state.LAZY.cadete.file, 'data-cadete.js');
  assert.equal(state.LAZY.juvenil.consts.groups, 'JUVENIL');
  assert.deepEqual(state.lazyData('juvenil', {}), { groups: [], stats: null, history: {}, gol: [], estados: {}, equipos: {}, campos: {} });
  assert.deepEqual(state.alevinData({}), { groups: [], stats: null, history: {}, gol: [], estados: {}, equipos: {} });
});

test('test_ensure_lazy: las siete constantes de data-cadete.js; un vuelo; un 404, vacío y memorizado; un fallo, null y se reintenta', quiet(async () => {
  requests.length = 0;
  files['data-cadete.js'] = 'red';
  assert.equal(await state.ensureLazy('cadete'), null, 'sin red: null');
  files['data-cadete.js'] = '<!doctype html><title>sin conexión</title>';
  assert.equal(await state.ensureLazy('cadete'), null, 'el index.html del SW sin conexión: null');
  files['data-cadete.js'] = `// generado por scripts/generate_js.py\n${fileOf(CADETE)}`;
  const [a, b] = await Promise.all([state.ensureLazy('cadete'), state.ensureLazy('cadete')]);
  assert.equal(a, b, 'un solo vuelo');
  assert.deepEqual(a, { groups: CADETE.CADETE, stats: CADETE.CAD_STATS, history: CADETE.HISTORY_CAD, gol: CADETE.GOL_CAD,
    estados: CADETE.ESTADOS_CAD, equipos: CADETE.EQUIPOS_CAD, campos: CADETE.CAMPOS_CAD });
  assert.equal(await state.ensureLazy('cadete'), a, 'cargado, no se vuelve a pedir');
  assert.deepEqual(requests, ['./data-cadete.js?v=20261125a', './data-cadete.js?v=20261125a', './data-cadete.js?v=20261125a']);
  // Un 404 (la web de antes de juvenil): juvenil vacío, memorizado.
  requests.length = 0;
  const empty = await state.ensureLazy('juvenil');
  assert.deepEqual(empty, state.lazyData('juvenil', {}));
  assert.equal(await state.ensureLazy('juvenil'), empty);
  assert.deepEqual(requests, ['./data-juvenil.js?v=20261125a']);
  // Alevín, el de siempre: la misma carga y la misma memoria.
  const ALEV = { ALEVIN: [], ALEV_STATS: { groups: 0, teams: 0 }, HISTORY_ALEV: {}, GOL_ALEV: [], ESTADOS_ALEV: {}, EQUIPOS_ALEV: {} };
  files['data-alevin.js'] = fileOf(ALEV);
  const alevin = await state.ensureLazy('alevin');
  assert.equal(await state.ensureAlevin(), alevin);
  assert.deepEqual(alevin, state.alevinData(ALEV));
  assert.throws(() => state.lazyNeeds('senior', PORTAL, {}, PORTAL), TypeError, 'una categoría que no es perezosa');
}));

// Un data-<cat>.js a medias (la conexión que se corta, un fichero escrito a medias): le falta alguna de sus
// constantes (LAZY[cat].consts). Es un fallo de carga (null, sin memorizar: «Reintentar» lo vuelve a pedir), no
// una categoría con menos datos que se pinta sin aviso (Goleadores diría «Todavía no hay goleadores»).
// También en alevín (lazyFromText, lo que lee ensureLazy).
test('un data-<cat>.js a medias es un fallo de carga, también en alevín; el completo, después, se carga', quiet(async () => {
  const inf = Object.fromEntries(Object.entries(CADETE).map(([k, v]) => [k.replace('CADETE', 'INFANTIL').replace(/_CAD$/, '_INF').replace(/^CAD_/, 'INF_'), v]));
  const whole = fileOf(inf);
  files['data-infantil.js'] = whole.slice(0, Math.floor(whole.length / 2));
  assert.equal(await state.ensureLazy('infantil'), null, 'cortado por la mitad');
  const { CAMPOS_INF, ...sinCampos } = inf;
  files['data-infantil.js'] = fileOf(sinCampos);
  assert.equal(await state.ensureLazy('infantil'), null, 'sin CAMPOS_INF, la última');
  files['data-infantil.js'] = whole;
  assert.deepEqual((await state.ensureLazy('infantil')).campos, CAMPOS_INF, 'entero, se carga');
  const ALEV = { ALEVIN: [], ALEV_STATS: { groups: 0, teams: 0 }, HISTORY_ALEV: {}, GOL_ALEV: [], ESTADOS_ALEV: {}, EQUIPOS_ALEV: {} };
  const { GOL_ALEV, ...sinGoles } = ALEV;
  assert.throws(() => state.lazyFromText('alevin', fileOf(sinGoles)), /GOL_ALEV/);
  assert.throws(() => state.lazyFromText('alevin', '<!doctype html><title>sin conexión</title>'), /ALEVIN/);
  assert.deepEqual(state.lazyFromText('alevin', fileOf(ALEV)), state.alevinData(ALEV));
}));

test('test_temporada_pasada: loadLazySeasons pide las de la temporada que dice data-seasons.js; un 404 es «sin esa categoría»; devuelve solo los fallos', quiet(async () => {
  requests.length = 0;
  files[`data-season-${PAST}-cadete.js`] = `const SEASON_2025_2026_CADETE=${JSON.stringify({ name: PAST, cadete: [raw('CADNG1', 'Insular GC', '')] })};\n`;
  files[`data-season-${PAST}-juvenil.js`] = 503;
  const seasons = [{ name: PORTAL, current: true }, { name: PAST, current: false, lazy: ['infantil', 'cadete', 'juvenil'] }];
  const datasets = { seasons, seasonRaw: {}, lazy: {}, seasonLazy: {} };
  const failed = await state.loadLazySeasons(datasets, [PAST], PORTAL);
  assert.deepEqual(requests.map((url) => url.replace(/\?.*$/, '')).sort(), [
    `./data-season-${PAST}-alevin.js`, `./data-season-${PAST}-cadete.js`, `./data-season-${PAST}-infantil.js`, `./data-season-${PAST}-juvenil.js`]);
  assert.deepEqual(failed, [{ cat: 'juvenil', season: PAST }]);
  assert.deepEqual(datasets.seasonLazy.alevin, { [PAST]: {} });
  assert.deepEqual(datasets.seasonLazy.infantil, { [PAST]: {} });
  assert.deepEqual(datasets.seasonLazy.cadete[PAST].cadete.map((g) => g.id), ['CADNG1']);
  assert.equal(Object.hasOwn(datasets.seasonLazy.juvenil || {}, PAST), false, 'un fallo no se guarda');
  // La siguiente vuelve a pedir solo lo que falló.
  requests.length = 0;
  files[`data-season-${PAST}-juvenil.js`] = `const SEASON_2025_2026_JUVENIL=${JSON.stringify({ name: PAST, juvenil: [] })};\n`;
  assert.deepEqual(await state.loadLazySeasons(datasets, [PAST], PORTAL), []);
  assert.deepEqual(requests.map((url) => url.replace(/\?.*$/, '')), [`./data-season-${PAST}-juvenil.js`]);
  // La de alevín de antes, con su firma de antes: las temporadas que no llegaron.
  assert.deepEqual(await state.loadAlevinSeasons(datasets, [PAST], PORTAL), []);
  // Una temporada cuya entrada de SEASONS no dice ninguna (las de hoy: sin `lazy`): solo alevín, como siempre;
  // las demás, «sin esa categoría» sin pedirlas (decenas de 404 en la Trayectoria).
  requests.length = 0;
  const today = { seasons: [{ name: PORTAL, current: true }, { name: '2024-2025', current: false }], seasonRaw: {}, lazy: {}, seasonLazy: {} };
  assert.deepEqual(await state.loadLazySeasons(today, ['2024-2025'], PORTAL), []);
  assert.deepEqual(requests.map((url) => url.replace(/\?.*$/, '')), ['./data-season-2024-2025-alevin.js']);
  assert.deepEqual([today.seasonLazy.infantil, today.seasonLazy.cadete, today.seasonLazy.juvenil], [{ '2024-2025': {} }, { '2024-2025': {} }, { '2024-2025': {} }]);
  // lazyCatsOf: alevín siempre y las que diga; nada de lo que no es perezosa.
  assert.deepEqual(state.lazyCatsOf(seasons, PAST), ['alevin', 'infantil', 'cadete', 'juvenil']);
  assert.deepEqual(state.lazyCatsOf([{ name: PAST, lazy: ['juvenil', 'senior', 'alevin'] }], PAST), ['alevin', 'juvenil']);
  assert.deepEqual(state.lazyCatsOf(null, PAST), ['alevin']);
  await assert.rejects(state.lazyNeeds('infantil', '2024-2025', datasets, PORTAL, { ensureSeason: async () => null })[0],
    { message: 'infantil de la temporada 2024/25' });
  await assert.rejects(state.lazyNeeds('cadete', PORTAL, { lazy: {} }, PORTAL, { ensure: async () => null })[0], { message: 'cadete' });
}));

// El contexto mínimo del router: la temporada del portal con benjamín y lo perezoso que se diga.
// declared: las perezosas de cada temporada en SEASONS (su `lazy`; sin él, solo alevín, como con la base de hoy).
const ALL = ['alevin', 'infantil', 'cadete', 'juvenil'];
function ctxWith(lazy = {}, seasonLazy = {}, declared = null) {
  const seasons = [{ name: PORTAL, current: true }, { name: PAST, current: false }]
    .map((entry) => (declared ? { ...entry, lazy: declared } : entry));
  const datasets = { benjamin: [raw('FF1', 'Primera Fase GC', 'BENJAMIN PRIMERA FASE GC - GRUPO 1')], prebenjamin: [], history: {},
    seasons, seasonRaw: {}, lazy, seasonLazy };
  const model = createModel(datasets, { portalSeason: PORTAL, buildClubIndex });
  return { portal: { season: PORTAL, defaultTeam: { name: 'Club Uno', cat: 'benjamin', groupId: 'FF1' } }, model, datasets,
    resolution: { status: 'ok', name: 'Club Uno', cat: 'benjamin', group: model.group(PORTAL, 'FF1') }, myTeam: null };
}
const loadedAll = () => Object.fromEntries(LAZY_CATS.map((cat) => [cat, state.lazyData(cat, {})]));
const need = (hash, ctx) => needsLazy(parseRoute(hash), ctx);

test('test_lazy_needs_y_fallos: needsLazy de cada ruta', () => {
  const none = ctxWith();
  const all = ctxWith({}, {}, ALL);
  assert.deepEqual(need('#/ligas?c=juvenil&s=2026-2027', none), [{ cat: 'juvenil', season: PORTAL, soft: false }]);
  // Explorar y Ligas sin `c`: las que dice data-seasons.js de la temporada (con la base de hoy, alevín).
  assert.deepEqual(need('#/explorar', none), [{ cat: 'alevin', season: PORTAL, soft: true }]);
  assert.deepEqual(need('#/ligas', none), [{ cat: 'alevin', season: PORTAL, soft: true }]);
  assert.deepEqual(need('#/explorar', all), LAZY_CATS.map((cat) => ({ cat, season: PORTAL, soft: true })));
  assert.deepEqual(need('#/ligas', all), LAZY_CATS.map((cat) => ({ cat, season: PORTAL, soft: true })));
  assert.deepEqual(need('#/explorar', ctxWith({}, {}, ['cadete'])), [{ cat: 'alevin', season: PORTAL, soft: true }, { cat: 'cadete', season: PORTAL, soft: true }]);
  assert.deepEqual(need('#/goleadores?c=infantil', none), [{ cat: 'infantil', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/records?c=cadete', none), [{ cat: 'cadete', season: PORTAL, soft: false }]);
  // Un grupo de una nueva, por su prefijo, si la temporada la tiene; si no (la base de hoy), lo de antes de las
  // nuevas (alevín), sin pedir un data-<cat>.js que no tendría nada.
  const cadete = ctxWith({}, {}, ['cadete']);
  assert.deepEqual(need('#/tabla?g=CADNG2&s=2026-2027', cadete), [{ cat: 'cadete', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/tabla?g=CADNG2&s=2026-2027', none), [{ cat: 'alevin', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/tabla?g=CADI1', none), [{ cat: 'alevin', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/tabla?g=JUVPL1', all), [{ cat: 'juvenil', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/tabla?g=JUVPL1', cadete), [{ cat: 'alevin', season: PORTAL, soft: false }], 'nunca la de otra nueva');
  assert.deepEqual(need('#/tabla?g=AL3', none), [{ cat: 'alevin', season: PORTAL, soft: false }]);
  // Un código que no dice su categoría: las de la temporada, sin soft (si no llegan, su caja de error, nunca un
  // falso «No encontramos el grupo»): con la base de hoy, alevín, como antes de las nuevas.
  assert.deepEqual(need('#/tabla?g=XQ9', none), [{ cat: 'alevin', season: PORTAL, soft: false }], 'un código que no dice su categoría');
  assert.deepEqual(need('#/tabla?g=XQ9', all), LAZY_CATS.map((cat) => ({ cat, season: PORTAL, soft: false })));
  assert.deepEqual(need('#/tabla?g=FF1', none), [], 'un grupo que está no espera a nada');
  assert.deepEqual(need('#/', none), [], 'la portada de un equipo de benjamín no pide nada');
  assert.deepEqual(need('#/ligas?c=benjamin', none), []);
  // Mi equipo, la de su categoría.
  const mine = { ...ctxWith({}, {}, ALL), myTeam: { name: 'Club Uno', season: PORTAL, cat: 'infantil', groupId: 'INFPG1' } };
  assert.deepEqual(need('#/', mine), [{ cat: 'infantil', season: PORTAL, soft: false }]);
  // En un cambio de temporada, también solo la suya; uno de benjamín, alevín (soft), como siempre: nunca las demás.
  assert.deepEqual(need('#/', { ...mine, myTeam: { ...mine.myTeam, season: PAST } }), [{ cat: 'infantil', season: PORTAL, soft: false }]);
  assert.deepEqual(need('#/', { ...mine, myTeam: { name: 'Club Uno', season: PAST, cat: 'benjamin', groupId: 'FF1' } }), [{ cat: 'alevin', season: PORTAL, soft: true }]);
  assert.deepEqual(need('#/', { ...mine, myTeam: { name: 'Club Uno', season: PORTAL, cat: 'benjamin', groupId: 'FF1' } }), []);
  // Ya cargadas, nada; una temporada pasada, su data-season-<S>-<cat>.js.
  assert.deepEqual(need('#/explorar', ctxWith(loadedAll(), {}, ALL)), []);
  assert.deepEqual(need(`#/explorar?s=${PAST}`, ctxWith(loadedAll(), {}, ALL)), LAZY_CATS.map((cat) => ({ cat, season: PAST, soft: true })));
  assert.deepEqual(need(`#/explorar?s=${PAST}`, ctxWith(loadedAll())), [{ cat: 'alevin', season: PAST, soft: true }]);
  const pastLoaded = Object.fromEntries(LAZY_CATS.map((cat) => [cat, { [PAST]: {} }]));
  assert.deepEqual(need(`#/explorar?s=${PAST}`, ctxWith(loadedAll(), pastLoaded, ALL)), []);
});

test('test_lazy_needs_y_fallos: «Todos los grupos» de una nueva (c=cadete&f=…) solo pide su fichero si la temporada la tiene', () => {
  const at = (hash, ctx) => resolveParams(parseRoute(hash), ctx);
  // Con la base de hoy (SEASONS sin `lazy`): nada que pedir, a Ligas con su aviso, como antes de las nuevas.
  const hoy = at('#/jornada?c=cadete&f=interinsular', ctxWith());
  assert.equal(hoy.lazy, undefined, 'no pide data-cadete.js');
  assert.equal(hoy.redirect.screen, 'ligas');
  // Con cadete en la temporada, lo pide antes de dar la competición por perdida; alevín, como siempre.
  assert.deepEqual(at('#/jornada?c=cadete&f=interinsular', ctxWith({}, {}, ['cadete'])).lazy, [{ cat: 'cadete', season: PORTAL, soft: false }]);
  assert.deepEqual(at('#/jornada?c=alevin&f=primera-fase', ctxWith()).lazy, [{ cat: 'alevin', season: PORTAL, soft: false }]);
});

test('test_lazy_needs_y_fallos: con data-juvenil.js caído, Explorar se pinta con las demás y lo dice en ctx.lazyFailed', quiet(async () => {
  const ctx = ctxWith({}, {}, ALL);
  const asked = [];
  // La carga de verdad (lazyNeeds) con cargadores que fallan en juvenil.
  const loadLazy = (cat, season, data, portalSeason) => {
    asked.push(`${cat}|${season}`);
    return state.lazyNeeds(cat, season, data, portalSeason, { ensure: async (c) => (c === 'juvenil' ? null : state.lazyData(c, {})) });
  };
  let painted = null;
  const screens = { explorar: { id: 'explorar', render: (c) => { painted = c; return html`<section data-screen="explorar"><h1>Explorar</h1></section>`; } } };
  screens[''] = screens.explorar;
  const b = fakeBrowser('#/explorar');
  const router = startRouter({ screens, root: b.root, getContext: () => ({ ...ctx, today: '2026-10-05' }), window: b.win, loadLazy });
  await router.idle();
  assert.ok(painted, 'se pinta');
  assert.deepEqual(painted.lazyFailed, ['juvenil']);
  assert.equal(painted.alevinFailed, false, 'alevín sí llegó');
  assert.deepEqual(asked.sort(), LAZY_CATS.map((cat) => `${cat}|${PORTAL}`).sort(), 'cada una, una vez');
  assert.equal(ctx.datasets.lazy.cadete.groups.length, 0);
  assert.equal(ctx.datasets.lazy.juvenil, undefined);
  assert.equal(Object.hasOwn(painted, 'lazyTried'), false, 'lo que pidió el router no va a las pantallas');
}));

test('test_lazy_needs_y_fallos: un grupo de cadete que no llega da la caja de error de cadete, nunca «No encontramos el grupo»', quiet(async () => {
  const ctx = ctxWith({}, {}, ['cadete']);
  const loadLazy = (cat, season, data, portalSeason) => state.lazyNeeds(cat, season, data, portalSeason, { ensure: async () => null });
  const screens = { tabla: { id: 'tabla', render: () => html`<section><h1>Tabla</h1></section>` } };
  screens[''] = screens.tabla;
  const b = fakeBrowser('#/tabla?g=CADNG2');
  const router = startRouter({ screens, root: b.root, getContext: () => ({ ...ctx, today: '2026-10-05' }), window: b.win, loadLazy });
  await router.idle();
  assert.match(b.root.innerHTML, /data-state="error"/);
  assert.match(b.root.innerHTML, /No se pudieron cargar los datos de cadete/);
  assert.doesNotMatch(b.root.innerHTML, /No encontramos el grupo/);
}));

test('test_modelo_con_las_perezosas: la temporada, las equipaciones, los campos, los estados y los goleadores de infantil y cadete', () => {
  const INF = {
    groups: [raw('INFPG1', 'Preferente GC', 'LIGA INFANTIL PREFERENTE DE GRAN CANARIA - GRUPO 1')],
    stats: { groups: 1, teams: 2 }, history: historyOf('INFPG1'),
    gol: [{ id: 'INFPG1', g: 'INFANTIL LIGA PREFERENTE', s: [['PRUEBA, DOS', 'Club Dos', 1, 1]] }],
    estados: { INFPG1: { 'Jornada 1': { 'Club Uno|Club Dos': ['suspendido', null, null] } } },
    equipos: { 'Club Uno': ['AZUL', 'AZUL', 'AZULES', 'CAMPO INFANTIL', 'Tierra', null] },
    campos: { 'CAMPO INFANTIL': ['Calle 3', 'Gáldar', 'Tierra', 'F11'] },
  };
  const datasets = {
    benjamin: [raw('FF1', 'Primera Fase GC', 'BENJAMIN PRIMERA FASE GC - GRUPO 1')], prebenjamin: [], history: historyOf('FF1'),
    equipos: { 'Club Uno': ['ROJA', 'ROJO', 'ROJAS', 'CAMPO', null, null] }, campos: { CAMPO: ['Calle 1', 'Arucas', 'Césped', 'F7'] },
    estados: {}, seasons: [{ name: PORTAL, current: true }], seasonRaw: {}, lazy: { alevin: undefined, infantil: undefined }, seasonLazy: {},
  };
  const model = createModel(datasets, { portalSeason: PORTAL, buildClubIndex });
  const before = model.season(PORTAL);
  assert.deepEqual(before.groups.map((g) => g.id), ['FF1']);
  datasets.lazy.infantil = INF;
  const after = model.season(PORTAL);
  assert.notEqual(after, before, 'se reconstruye cuando llega');
  assert.equal(model.season(PORTAL), after);
  const inf = model.group(PORTAL, 'INFPG1');
  assert.equal(inf.cat, 'infantil');
  assert.equal(inf.label, 'Infantil, Preferente, Grupo 1');
  assert.deepEqual(inf.rounds.map((r) => r.key), ['Jornada 1'], 'de HISTORY_INF');
  assert.deepEqual(model.matchStatus(inf.rounds[0].matches[0]), { state: 'suspendido', note: null, start: null });
  assert.equal(model.teamInfo(PORTAL, 'Club Uno', 'infantil').shirt, 'AZUL', 'EQUIPOS_INF');
  assert.equal(model.teamInfo(PORTAL, 'Club Uno', 'benjamin').shirt, 'ROJA', 'el homónimo de benjamín, la suya');
  assert.deepEqual(Object.keys(model.campos(PORTAL)).sort(), ['CAMPO', 'CAMPO INFANTIL'], 'CAMPOS y CAMPOS_INF');
  assert.equal(model.campos(PORTAL), model.campos(PORTAL), 'la unión, memorizada');
  assert.equal(model.scorers(PORTAL, 'infantil'), INF.gol);
  assert.deepEqual(model.scorers(PORTAL, 'cadete'), [], 'sin pedir');
  // Una temporada pasada con su data-season-<S>-cadete.js.
  datasets.seasons.push({ name: PAST, current: false });
  datasets.seasonRaw[PAST] = { name: PAST, current: false, benjamin: [], prebenjamin: [] };
  assert.deepEqual(model.season(PAST).groups, []);
  datasets.seasonLazy.cadete = { [PAST]: { name: PAST, cadete: [{ ...raw('CADNG1', 'Insular GC', ''), jornadas: historyOf('CADNG1').CADNG1 }],
    gol: { cadete: CADETE.GOL_CAD }, equipos: CADETE.EQUIPOS_CAD, campos: CADETE.CAMPOS_CAD } };
  assert.deepEqual(model.season(PAST).groups.map((g) => `${g.id} ${g.cat}`), ['CADNG1 cadete']);
  assert.deepEqual(model.scorers(PAST, 'cadete').map((e) => e.id), ['CADNG1']);
  assert.equal(model.teamInfo(PAST, 'Club Uno', 'cadete').shirt, 'VERDE');
  assert.deepEqual(Object.keys(model.campos(PAST)), ['CAMPO CADETE']);
});
