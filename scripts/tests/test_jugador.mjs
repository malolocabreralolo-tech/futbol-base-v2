// La ficha de jugador (#/jugador?id) y los jugadores seguidos: followed.js, la pantalla, la ruta y
// los enlaces desde la plantilla y el acta. Una ficha por niño: su clave es la de su
// identidad principal (el id de la federación o «n» + 9 cifras en base 36) y las demás son alias.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ctxFor, datasetsFor } from './fixtures/rediseno/screens.mjs';
import { memoryStorage } from './fixtures/rediseno/fake-browser.mjs';
import { FOLLOWED_KEY, clearStore } from '../../src/store.js';
import { MAX_FOLLOWED, cleanFollowed, isFollowed, loadFollowed, saveFollowed, toggleFollowed } from '../../src/followed.js';
import { screen, followedBlock } from '../../src/screen-jugador.js';
import { resolveParams } from '../../src/router.js';
import { parseRoute, playerHref } from '../../src/links.js';
import { jugadoresShard } from '../../src/state.js';
import { playerMatches, teamSquad, timelineFor } from '../../src/model.js';
import { screen as partido } from '../../src/screen-partido.js';

const s = (h) => String(h);
const ID = '55181078';
const SIN_ID = 'n0k3z9q2ab';
// Un trozo de data-jugadores-<k>.js con la forma de generate_js.jugadores_files.
const SHARD = {
  p: {
    [ID]: { n: 'SERRANO DOMINGUEZ, LEYRE', c: [
      ['2024-2025', 'PGC2', 'Las Mesas Hu.', 12, 10, 3, 1, 0],
      ['2025-2026', 'PG2', 'Las Mesas Hu.', 20, 18, 7, 0, 0],
      ['2025-2026', 'BCB1', 'Las Mesas Hu.', 2, 2, 0, 0, 0],
    ] },
  },
  g: {
    '2024-2025/PGC2': ['prebenjamin', 'Grupo 2', 'Gran Canaria', 'grancanaria'],
    '2025-2026/PG2': ['prebenjamin', 'Grupo 2', 'Gran Canaria', 'grancanaria'],
  },
};
const ctxWith = (params, { shard = SHARD, followed = [] } = {}) => {
  const datasets = datasetsFor();
  datasets.jugadores = { [jugadoresShard(ID)]: shard };
  return { ...ctxFor('jugador', params, { datasets }), followed };
};

test('followed: limpia, alterna (el nuevo el primero), guarda en su clave y «Borrar datos» la borra', () => {
  assert.deepEqual(cleanFollowed([{ id: 1, n: 'A' }, { id: '1', n: 'B' }, { id: 'x', n: 'C' }, { id: '2', n: '' }, null]), [{ id: '1', n: 'A' }]);
  // Una clave sin id de la federación también se sigue; una que no es clave, no.
  assert.deepEqual(cleanFollowed([{ id: SIN_ID, n: 'A' }, { id: 'n12', n: 'B' }, { id: 'NABCDEFGHI', n: 'C' }]), [{ id: SIN_ID, n: 'A' }]);
  assert.deepEqual(toggleFollowed([], { id: SIN_ID, n: 'A' }), [{ id: SIN_ID, n: 'A' }]);
  let list = toggleFollowed([], { id: ID, n: 'SERRANO DOMINGUEZ, LEYRE' });
  list = toggleFollowed(list, { id: '7', n: 'OTRO, NIÑO' });
  assert.deepEqual(list.map(p => p.id), ['7', ID]);
  assert.ok(isFollowed(list, Number(ID)));
  assert.deepEqual(toggleFollowed(list, { id: '7', n: 'OTRO, NIÑO' }).map(p => p.id), [ID]);
  const many = Array.from({ length: MAX_FOLLOWED + 3 }, (_, i) => ({ id: String(i), n: `N${i}` }));
  assert.equal(cleanFollowed(many).length, MAX_FOLLOWED);
  const storage = memoryStorage();
  assert.deepEqual(loadFollowed(storage), []);
  assert.equal(saveFollowed(storage, list), true);
  assert.deepEqual(loadFollowed(storage), list);
  storage.setItem(FOLLOWED_KEY, '{roto');
  assert.deepEqual(loadFollowed(storage), []);
  saveFollowed(storage, list);
  clearStore(storage);
  assert.equal(storage.getItem(FOLLOWED_KEY), null);
  const blocked = { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); } };
  assert.deepEqual(loadFollowed(blocked), []);
  assert.equal(saveFollowed(blocked, list), false);
});

// Antes la ruta solo aceptaba un número (el id de la federación); ahora, cualquier clave pública.
test('ruta: #/jugador?id con una clave (un número o «n» + 9 cifras en base 36); cualquier otra cosa se queda sin id', () => {
  assert.equal(playerHref(ID), `#/jugador?id=${ID}`);
  assert.equal(playerHref(SIN_ID), `#/jugador?id=${SIN_ID}`);
  assert.equal(playerHref(Number(ID)), `#/jugador?id=${ID}`);
  for (const bad of [null, undefined, '', 'abc', '12x', 'n12345678', 'n1234567890', 'N0ABCDEFGH', 'n0abcdefg_', ' 7']) {
    assert.equal(playerHref(bad), null, String(bad));
  }
  assert.deepEqual(parseRoute(playerHref(ID)), { screen: 'jugador', params: { id: ID } });
  assert.deepEqual(parseRoute(playerHref(SIN_ID)), { screen: 'jugador', params: { id: SIN_ID } });
  const ctx = ctxWith({ id: ID });
  assert.deepEqual(resolveParams({ screen: 'jugador', params: { id: ID, s: '2024-2025' } }, ctx), { params: { id: ID } });
  assert.deepEqual(resolveParams({ screen: 'jugador', params: { id: SIN_ID } }, ctx), { params: { id: SIN_ID } });
  for (const bad of ['12x', 'n12345678', 'NABCDEFGHI']) {
    assert.deepEqual(resolveParams({ screen: 'jugador', params: { id: bad } }, ctx), { params: {} }, bad);
  }
});

test('ficha: nombre, resumen, «Seguir» y su trayectoria de la temporada más reciente a la más antigua', () => {
  const out = s(screen.render(ctxWith({ id: ID })));
  assert.match(out, /<h1>Leyre Serrano Dominguez<\/h1>/);
  assert.match(out, /2 temporadas · 34 partidos · 10 goles/);
  assert.match(out, /data-action="seguir-jugador" aria-pressed="false">Seguir</);
  const seasons = [...out.matchAll(/<h3 class="traj-season">([^<]+)<\/h3>/g)].map(m => m[1]);
  assert.deepEqual(seasons, ['2025/26', '2024/25']);
  // Cada fila, a la ficha de su equipo en su grupo; el grupo con su nombre de la app (o su código sin él).
  assert.match(out, /href="#\/equipo\?s=2025-2026&amp;g=PG2&amp;t=Las%20Mesas%20Hu\."/);
  assert.match(out, /<span class="traj-group">Prebenjamín, Grupo 2 de Gran Canaria · 18 de titular<\/span>/);
  assert.match(out, /<span class="traj-group">BCB1 · 2 de titular<\/span>/);
  assert.match(out, /Grupo 2 de Gran Canaria · 10 de titular · 1 amarilla</);
  assert.match(out, /<span class="traj-pts">20 partidos<\/span>/);
  assert.match(out, /<span class="traj-pos">sin goles<\/span>/);
  assert.match(s(screen.render(ctxWith({ id: ID }, { followed: [{ id: ID, n: 'X' }] }))), /aria-pressed="true">Siguiendo</);
});

test('ficha: sin id, sin el trozo (error con «Reintentar») o sin el jugador en las actas', () => {
  assert.match(s(screen.render(ctxWith({}))), /Abre la ficha de un jugador/);
  assert.match(s(screen.render(ctxWith({ id: ID }, { shard: null }))), /data-action="retry"/);
  assert.match(s(screen.render(ctxWith({ id: '16' }))), /No encontramos a ese jugador/);
});

test('needs: pide el trozo de su id una vez; con él ya cargado, nada', async () => {
  const datasets = {};
  assert.deepEqual(screen.needs({}, datasets), []);
  const fetched = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    fetched.push(String(url));
    return { ok: true, status: 200, text: async () => `const JUGADORES_${jugadoresShard(ID)} = ${JSON.stringify(SHARD)};\n` };
  };
  try {
    await Promise.all(screen.needs({ id: ID }, datasets));
  } finally {
    globalThis.fetch = realFetch;
  }
  assert.equal(fetched.length, 1);
  assert.match(fetched[0], new RegExp(`data-jugadores-${jugadoresShard(ID)}\\.js`));
  assert.deepEqual(datasets.jugadores[jugadoresShard(ID)], SHARD);
  assert.deepEqual(screen.needs({ id: ID }, datasets), []);
});

test('mount: «Seguir» pasa el jugador a nav.toggleFollow', () => {
  const ctx = ctxWith({ id: ID });
  let listener = null;
  const button = { getAttribute: () => 'seguir-jugador' };
  const section = {
    matches: () => true,
    contains: () => true,
    addEventListener: (type, fn) => { listener = fn; },
  };
  const calls = [];
  screen.mount(section, ctx, { toggleFollow: (p) => calls.push(p) });
  listener({ target: { closest: () => button } });
  assert.deepEqual(calls, [{ id: ID, n: 'SERRANO DOMINGUEZ, LEYRE' }]);
});

test('Mi equipo: los jugadores seguidos, cada uno con su ficha; sin ninguno, nada', () => {
  assert.equal(s(followedBlock({ followed: [] })), '');
  const out = s(followedBlock({ followed: [{ id: ID, n: 'SERRANO DOMINGUEZ, LEYRE' }] }));
  assert.match(out, /Jugadores que sigues/);
  assert.match(out, new RegExp(`href="#/jugador\\?id=${ID}"`));
  assert.match(out, /Leyre Serrano Dominguez/);
});

test('plantilla: la fila del jugador lleva su id de la federación si el acta lo trae', () => {
  const match = { home: 'A', away: 'B', hs: 1, as: 0, roundKey: 'Jornada 1', season: '2025-2026', groupId: 'PG2', dateISO: '2025-10-04' };
  const group = { id: 'PG2', season: '2025-2026', rounds: [{ key: 'Jornada 1', matches: [match] }] };
  const lineups = { 'A|B|1-0': { s: '2025-2026', gr: 'PG2', home: [{ n: 'X, Y', id: 7, dn: 3, r: 'starter', g: 1 }], away: [{ n: 'Z, W', dn: 4, r: 'starter', g: 0 }], events: [] } };
  assert.deepEqual(teamSquad(lineups, { group, team: 'A' }).rows, [{ name: 'X, Y', id: 7, dorsal: 3, ap: 1, st: 1, g: 1, y: 0, rd: 0 }]);
  assert.deepEqual(teamSquad(lineups, { group, team: 'B' }).rows, [{ name: 'Z, W', dorsal: 4, ap: 1, st: 1, g: 0, y: 0, rd: 0 }]);
});

// ── claves, alias y lo que la ficha dice de cada fila ──────────────────────────────────────

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

// TABLA_CLAVES de scripts/tests/test_identidad.py: la clave que da identidad.clave_publica y su trozo de 16.
const TABLA_CLAVES = [
  ['153432', 8], ['55329034', 10], ['214080', 0], ['1000017', 1], ['nisxwgmjvp', 5], ['ns8zin819i', 6],
  ['nphzk2mnyf', 7], ['njkibiyk9d', 1], ['n22zp0f76w', 8], ['n1ddjsy73e', 10], ['nb6t8ejz2s', 4],
  ['n8qeq0zomr', 3], ['nccuo4q7lp', 13], ['ni6iou2qm2', 10], ['nc7n9df8hm', 10], ['npp634adwo', 8],
  ['n06wbfdyqg', 8], ['nogme3ruur', 3], ['nib8aqb17c', 8], ['njzprohv7i', 14], ['nlaihmii3x', 13],
  ['ns9cly007v', 11],
];

test('jugadoresShard da lo mismo que identidad.trozo: la tabla de las pruebas de Python', () => {
  for (const [clave, k] of TABLA_CLAVES) {
    assert.equal(jugadoresShard(clave), k, clave);
    assert.equal(playerHref(clave), `#/jugador?id=${clave}`);
  }
});

test('jugadoresShard da lo mismo que identidad.trozo con 200 claves de identidad.clave_publica', () => {
  // 100 sin id (nombre, equipo, año inventados) y 100 ids de la federación: las calcula Python.
  const code = [
    'import json, sys', `sys.path.insert(0, ${JSON.stringify(join(ROOT, 'scripts'))})`,
    'from identidad import clave_publica, trozo',
    'claves = [clave_publica(None, f"APELLIDO{i} OTRO, NOMBRE{i % 7}", f"Equipo {i % 13}", 2019 + i % 8) for i in range(100)]',
    'claves += [clave_publica(37 + i * 104729 + i * i * 7919, "", "", 0) for i in range(100)]',
    'print(json.dumps([[c, trozo(c)] for c in claves]))',
  ].join('\n');
  const run = spawnSync('python3', ['-c', code], { encoding: 'utf8', timeout: 60000 });
  assert.equal(run.status, 0, run.stderr);
  const pares = JSON.parse(run.stdout);
  assert.equal(pares.length, 200);
  assert.equal(new Set(pares.map(([c]) => c)).size, 200);
  for (const [clave, k] of pares) {
    assert.match(clave, /^(?:\d+|n[0-9a-z]{9})$/);
    assert.equal(jugadoresShard(clave), k, clave);
  }
});

// Una ficha unida, con su alias en otro trozo: la del id de la federación (ID), que fue SIN_ID la temporada
// anterior (unida por nombre) y que tuvo otro id de un solo uso (ALIAS_UN_USO, unido por equipo).
const ALIAS_UN_USO = '55181090';
const OTRA = 'n0k3z9q2b0';
const UNIDA = {
  n: 'SERRANO DOMINGUEZ, LEYRE',
  c: [
    ['2024-2025', 'PGC2', 'Las Mesas Hu.', 12, 10, 3, 1, 0, 1, 'n'],
    ['2025-2026', 'PG2', 'Las Mesas Hu.', 20, 18, 7, 0, 0],
    ['2025-2026', 'PG2', 'Las Mesas Hu.', 1, 0, 1, 0, 0, 1, 'e'],
    ['2025-2026', 'BCB1', 'Las Mesas Hu.', 2, 2, 0, 0, 0, 1, 'c'],
  ],
  h: [[OTRA, 'Guayarmina', '2025-2026'], ['900001', 'UD Guía', '2023-2024']],
  al: [SIN_ID, ALIAS_UN_USO],
};
const shardsWith = (entries) => {
  const out = {};
  const put = (k) => (out[k] = out[k] || { p: {}, a: {}, g: SHARD.g });
  for (const [clave, entry] of Object.entries(entries)) {
    put(jugadoresShard(clave)).p[clave] = entry;
    for (const alias of entry.al || []) put(jugadoresShard(alias)).a[alias] = clave;
  }
  return out;
};
const ctxShards = (params, shards, followed = []) => {
  const datasets = datasetsFor();
  datasets.jugadores = shards;
  return { ...ctxFor('jugador', params, { datasets }), followed };
};

test('los alias de la prueba caen en otro trozo que su ficha', () => {
  assert.notEqual(jugadoresShard(SIN_ID), jugadoresShard(ID));
  assert.notEqual(jugadoresShard(ALIAS_UN_USO), jugadoresShard(ID));
});

test('ficha unida: cada fila unida dice por qué; ninguna se suma a otra; las otras fichas del mismo nombre al pie', () => {
  const out = s(screen.render(ctxShards({ id: ID }, shardsWith({ [ID]: UNIDA }))));
  assert.match(out, /<h1>Leyre Serrano Dominguez<\/h1>/);
  assert.match(out, /2 temporadas · 35 partidos · 11 goles/);
  const groups = [...out.matchAll(/<span class="traj-group">([^<]+)<\/span>/g)].map(m => m[1]);
  assert.deepEqual(groups.slice(0, 4), [
    'Prebenjamín, Grupo 2 de Gran Canaria · 18 de titular',
    'Prebenjamín, Grupo 2 de Gran Canaria · unido por nombre (mismo equipo y temporada)',
    'BCB1 · 2 de titular · unido por nombre (mismo club)',
    'Prebenjamín, Grupo 2 de Gran Canaria · 10 de titular · 1 amarilla · unido por nombre',
  ]);
  assert.doesNotMatch(out, /En las actas figura solo con este nombre/);
  // Al pie, las otras fichas del mismo nombre: cada una a su ficha, con su último equipo y temporada.
  const at = out.indexOf('Otras fichas con este mismo nombre');
  assert.ok(at > out.indexOf('Trayectoria'));
  const foot = out.slice(at);
  assert.match(foot, new RegExp(`<a class="traj-row" href="#/jugador\\?id=${OTRA}"><span class="traj-team">Guayarmina</span><span class="traj-group">2025/26</span></a>`));
  assert.match(foot, /<a class="traj-row" href="#\/jugador\?id=900001"><span class="traj-team">UD Guía<\/span><span class="traj-group">2023\/24<\/span><\/a>/);
});

test('ficha sin ningún id: «En las actas figura solo con este nombre.»; sin homónimos, sin el bloque del pie', () => {
  const entry = { n: 'RUIZ, LEO', c: [['2025-2026', 'PG2', 'Las Mesas Hu.', 3, 3, 1, 0, 0]], s: 1 };
  const out = s(screen.render(ctxShards({ id: SIN_ID }, shardsWith({ [SIN_ID]: entry }))));
  assert.match(out, /<h1>Leo Ruiz<\/h1>/);
  assert.match(out, /<p class="notice">En las actas figura solo con este nombre\.<\/p>/);
  assert.doesNotMatch(out, /Otras fichas con este mismo nombre/);
  assert.doesNotMatch(out, /unido por nombre/);
});

test('un alias abre la ficha a la que lleva (la URL no cambia) y el «Seguir» de esa ficha sigue al alias guardado', () => {
  const shards = shardsWith({ [ID]: UNIDA });
  for (const alias of [SIN_ID, ALIAS_UN_USO]) {
    const out = s(screen.render(ctxShards({ id: alias }, shards)));
    assert.match(out, /<h1>Leyre Serrano Dominguez<\/h1>/, alias);
    assert.match(out, /aria-pressed="false">Seguir</);
  }
  // Seguido con la clave antigua (hoy alias): sale como seguido abriéndolo por su clave o por el alias…
  const followed = [{ id: SIN_ID, n: 'SERRANO DOMINGUEZ, LEYRE' }];
  for (const id of [ID, SIN_ID, ALIAS_UN_USO]) {
    assert.match(s(screen.render(ctxShards({ id }, shards, followed))), /aria-pressed="true">Siguiendo</, id);
  }
  // …y dejar de seguirlo quita esa entrada, no añade otra.
  const calls = [];
  let listener = null;
  const section = { matches: () => true, contains: () => true, addEventListener: (type, fn) => { listener = fn; } };
  screen.mount(section, ctxShards({ id: ID }, shards, followed), { toggleFollow: (p) => calls.push(p) });
  listener({ target: { closest: () => ({}) } });
  assert.deepEqual(calls, [{ id: SIN_ID, n: 'SERRANO DOMINGUEZ, LEYRE' }]);
  assert.deepEqual(toggleFollowed(followed, calls[0]), []);
  // Sin seguir, abierto por un alias: se sigue la ficha por su clave.
  calls.length = 0;
  screen.mount(section, ctxShards({ id: ALIAS_UN_USO }, shards), { toggleFollow: (p) => calls.push(p) });
  listener({ target: { closest: () => ({}) } });
  assert.deepEqual(calls, [{ id: ID, n: 'SERRANO DOMINGUEZ, LEYRE' }]);
  // En Mi equipo, el seguido con el alias lleva a su ficha por el alias.
  assert.match(s(followedBlock({ followed })), new RegExp(`href="#/jugador\\?id=${SIN_ID}"`));
});

test('needs con un alias: pide su trozo y después el de la ficha a la que lleva; un alias a nada, «No encontramos»', async () => {
  // Otra ficha que la de arriba: ensureJugadores guarda cada trozo ya pedido (el de ID lo pidió otra prueba).
  const FICHA = '55181081';
  const shards = shardsWith({ [FICHA]: { ...UNIDA, al: [SIN_ID] } });
  const datasets = {};
  const fetched = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    fetched.push(String(url));
    const k = Number(String(url).match(/data-jugadores-(\d+)\.js/)[1]);
    return { ok: true, status: 200, text: async () => `const JUGADORES_${k} = ${JSON.stringify(shards[k] || { p: {}, a: {}, g: {} })};\n` };
  };
  try {
    await Promise.all(screen.needs({ id: SIN_ID }, datasets));
  } finally {
    globalThis.fetch = realFetch;
  }
  assert.notEqual(jugadoresShard(SIN_ID), jugadoresShard(FICHA));
  assert.deepEqual(fetched.map(u => Number(u.match(/data-jugadores-(\d+)\.js/)[1])), [jugadoresShard(SIN_ID), jugadoresShard(FICHA)]);
  assert.deepEqual(screen.needs({ id: SIN_ID }, datasets), []);
  assert.match(s(screen.render(ctxShards({ id: SIN_ID }, datasets.jugadores))), /<h1>Leyre Serrano Dominguez<\/h1>/);
  // El trozo de la ficha falló: su caja de error, con «Reintentar».
  const broken = { ...shards, [jugadoresShard(FICHA)]: null };
  assert.match(s(screen.render(ctxShards({ id: SIN_ID }, broken))), /data-action="retry"/);
  const lost = { [jugadoresShard('n000000000')]: { p: {}, a: {}, g: {} }, [jugadoresShard(SIN_ID)]: { p: {}, a: { [SIN_ID]: 'n000000000' }, g: {} } };
  assert.match(s(screen.render(ctxShards({ id: SIN_ID }, lost))), /No encontramos a ese jugador/);
});

// La pantalla Partido con un acta inventada en PG2 (Las Mesas Hu. 2–7 AD Huracán, sin cronología).
const PG2_J30 = { s: '2025-2026', g: 'PG2', r: 'Jornada 30', h: 'Las Mesas Hu.', a: 'AD Huracán' };
const partidoCon = (events) => {
  const datasets = datasetsFor();
  datasets.matchDetail = {};
  datasets.lineups = { '2025-2026/PG2': { 'Las Mesas Hu.|AD Huracán|2-7': {
    s: '2025-2026', gr: 'PG2', cod: 1, events, coachH: null, coachA: null, ref: null,
    home: [{ n: 'RUIZ, LEO', id: SIN_ID, dn: 4, r: 'starter', g: 1 }, { n: 'PEREZ, ANA', id: 7, dn: 5, r: 'starter', g: 1 }],
    away: [{ n: 'GOMEZ, LUIS', dn: 9, r: 'starter', g: 0 }] } } };
  return s(partido.render(ctxFor('partido', PG2_J30, { datasets })));
};

test('Partido: el autor de cada gol del acta enlaza a su ficha (con minuto y sin él); sin clave, solo el nombre', () => {
  const timed = partidoCon([
    { t: 'goal', s: 'h', n: 'RUIZ, LEO', m: 3, gt: 'normal', id: SIN_ID },
    { t: 'goal', s: 'h', n: 'PEREZ, ANA', m: 10, gt: 'penalty', id: 7 },
    { t: 'goal', s: 'a', n: 'GOMEZ, LUIS', m: 12, gt: 'normal' },
  ]);
  assert.match(timed, new RegExp(`<td class="pt-g-home(?: pt-mine)?"><a href="#/jugador\\?id=${SIN_ID}">Leo Ruiz</a></td>`));
  assert.match(timed, /<td class="pt-g-home(?: pt-mine)?"><a href="#\/jugador\?id=7">Ana Perez \(p\)<\/a><\/td>/);
  assert.match(timed, /<td class="pt-g-away(?: pt-mine)?">Luis Gomez<\/td>/);
  // Las alineaciones, también con la clave sin id.
  assert.match(timed, new RegExp(`<th scope="row" class="pt-player"><a href="#/jugador\\?id=${SIN_ID}">Leo Ruiz</a></th>`));
  const lists = partidoCon([
    { t: 'goal', s: 'h', n: 'RUIZ, LEO', m: null, gt: 'normal', id: SIN_ID },
    { t: 'goal', s: 'h', n: 'RUIZ, LEO', m: 20, gt: 'normal', id: SIN_ID },
  ]);
  assert.match(lists, new RegExp(`<li><a href="#/jugador\\?id=${SIN_ID}">Leo Ruiz</a> <span class="pt-glist-n">\\(2`));
});

test('timelineFor: los goles del acta llevan la clave de la ficha de su autor; los de futbolaspalmas, ninguna', () => {
  const match = { home: 'A', away: 'B', hs: 1, as: 1, season: '2025-2026', groupId: 'PG2' };
  const lineups = { 'A|B|1-1': { s: '2025-2026', gr: 'PG2', home: [], away: [], events: [
    { t: 'goal', s: 'h', n: 'X, Y', m: 3, gt: 'normal', id: SIN_ID }, { t: 'goal', s: 'a', n: 'Z, W', m: 5, gt: 'normal' }] } };
  assert.deepEqual(timelineFor(match, {}, lineups).goals.map(g => g.id ?? null), [SIN_ID, null]);
  const detail = { 'A|B|1-1': { s: '2025-2026', gr: 'PG2', g: [[3, 'X', '1-0', 'h', 'r'], [5, 'Z', '1-1', 'a', 'r']] } };
  assert.deepEqual(timelineFor(match, detail, lineups).goals.map(g => g.id ?? null), [null, null]);
});

test('plantilla: agrupa por la clave de la ficha (dos niños con el mismo nombre, dos filas); sin clave, por el nombre', () => {
  const m1 = { home: 'A', away: 'B', hs: 1, as: 0, roundKey: 'Jornada 1', season: '2025-2026', groupId: 'PG2', dateISO: '2025-10-04' };
  const m2 = { ...m1, roundKey: 'Jornada 2', dateISO: '2025-10-11', hs: 2 };
  const group = { id: 'PG2', season: '2025-2026', rounds: [{ key: 'Jornada 1', matches: [m1] }, { key: 'Jornada 2', matches: [m2] }] };
  const acta = (home) => ({ s: '2025-2026', gr: 'PG2', home, away: [{ n: 'Z, W', dn: 4, r: 'starter', g: 0 }], events: [] });
  const lineups = {
    'A|B|1-0': acta([{ n: 'DANIEL', id: SIN_ID, dn: 3, r: 'starter', g: 1 }, { n: 'DANIEL', id: OTRA, dn: 8, r: 'sub', g: 0 }]),
    'A|B|2-0': acta([{ n: 'DANIEL', id: SIN_ID, dn: 3, r: 'starter', g: 2 }]),
  };
  assert.deepEqual(teamSquad(lineups, { group, team: 'A' }).rows, [
    { name: 'DANIEL', id: SIN_ID, dorsal: 3, ap: 2, st: 2, g: 3, y: 0, rd: 0 },
    { name: 'DANIEL', id: OTRA, dorsal: 8, ap: 1, st: 0, g: 0, y: 0, rd: 0 },
  ]);
  assert.deepEqual(teamSquad(lineups, { group, team: 'B' }).rows, [{ name: 'Z, W', dorsal: 4, ap: 2, st: 2, g: 0, y: 0, rd: 0 }]);
  // Los partidos de cada uno, por su clave: el segundo DANIEL solo jugó la jornada 1.
  assert.deepEqual(playerMatches(lineups, { group, team: 'A', player: 'DANIEL', id: OTRA }).map(x => x.match.roundKey), ['Jornada 1']);
  assert.deepEqual(playerMatches(lineups, { group, team: 'A', player: 'DANIEL', id: SIN_ID }).map(x => x.goals), [1, 2]);
});

test('fila unida sin motivo conocido: «unido por nombre», como las demás', () => {
  const entry = { n: 'RUIZ, LEO', c: [['2025-2026', 'PG2', 'Las Mesas Hu.', 1, 0, 0, 0, 0, 1], ['2025-2026', 'PG2', 'Las Mesas Hu.', 1, 0, 0, 0, 0, 1, 'x']] };
  const out = s(screen.render(ctxShards({ id: SIN_ID }, shardsWith({ [SIN_ID]: entry }))));
  const groups = [...out.matchAll(/<span class="traj-group">([^<]+)<\/span>/g)].map(m => m[1]);
  assert.deepEqual(groups, ['Prebenjamín, Grupo 2 de Gran Canaria · unido por nombre', 'Prebenjamín, Grupo 2 de Gran Canaria · unido por nombre']);
});

test('título de la pestaña: el nombre del jugador; sin jugador, el de la pantalla (null)', () => {
  assert.equal(screen.title(ctxShards({ id: ID }, shardsWith({ [ID]: UNIDA }))), 'Leyre Serrano Dominguez');
  assert.equal(screen.title(ctxShards({ id: SIN_ID }, shardsWith({ [ID]: UNIDA }))), 'Leyre Serrano Dominguez');
  assert.equal(screen.title(ctxShards({}, {})), null);
  assert.equal(screen.title(ctxShards({ id: '16' }, shardsWith({ [ID]: UNIDA }))), null);
});

test('acta.css: en la ficha del jugador el nombre parte línea en vez de cortarse; las demás cabeceras siguen igual', () => {
  const css = readFileSync(join(ROOT, 'acta.css'), 'utf8');
  const rule = css.match(/\[data-screen="jugador"\] \.screen-head h1 \{([^}]*)\}/);
  assert.ok(rule, 'falta la regla de la ficha');
  assert.match(rule[1], /white-space: normal/);
  assert.match(rule[1], /overflow: visible/);
  assert.match(css, /\.screen-head h1 \{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; \}/);
});
