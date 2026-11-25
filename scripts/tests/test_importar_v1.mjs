// La primera vez que se abre v2 en un navegador, «mi equipo», los vistos y los jugadores seguidos de
// v1 (que comparte el origen y, con él, el localStorage) pasan a las claves de v2: importFromV1 lee
// v1 una sola vez, nunca escribe en sus claves y deja la marca fb2:importado, que «Borrar datos» no
// quita. A partir de ahí, v2 no vuelve a mirar a v1: loadStore solo lee fb2:almacen.
// Ejecutar: node --test scripts/tests/test_importar_v1.mjs
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { fixture } from './fixtures/rediseno/load.mjs';
import { datasetsFrom } from './fixtures/rediseno/simulate.mjs';
import { IMPORTED_KEY, importFromV1, loadStore, clearStore, migrateV1 } from '../../src/store.js';
import { loadFollowed } from '../../src/followed.js';
import { startContext } from '../../src/app.js';

// Storage en memoria con la interfaz de localStorage; `datos` es lo que guarda y `escrituras`, cada
// setItem y removeItem, en orden.
function almacenDePrueba(inicial = {}) {
  const datos = { ...inicial };
  const escrituras = [];
  return {
    datos,
    escrituras,
    getItem: (k) => (Object.hasOwn(datos, k) ? datos[k] : null),
    setItem: (k, v) => { escrituras.push(['set', k]); datos[k] = String(v); },
    removeItem: (k) => { escrituras.push(['remove', k]); delete datos[k]; },
  };
}

const OPC = { portalSeason: '2026-2027' };
const POR_DEFECTO = { cat: 'prebenjamin', groupId: 'PG2', name: 'Las Mesas Hu.' };
const EQUIPO = { name: 'AD Huracán', season: '2025-2026', cat: 'prebenjamin', groupId: 'PG2' };
const OTRO = { name: 'CD Moya', season: '2025-2026', cat: 'benjamin', groupId: 'A1' };
const cargar = (s, portalSeason = '2026-2027') => loadStore(s, { defaultTeam: POR_DEFECTO, portalSeason });
// Lo que guarda v1: su almacén, sus jugadores seguidos y los favoritos de la app anterior.
const V1 = {
  'futbol-base:v2': JSON.stringify({ myTeam: EQUIPO, recent: [{ s: '2025-2026', g: 'PG2', t: 'Acodetti' }] }),
  'futbol-base:jugadores': JSON.stringify([{ id: '7', n: 'Luis' }]),
  'futbol-base:favorites:v1': JSON.stringify(fixture('favorites-v1')),
};
const NADA = { store: false, followed: false };

test('IMPORTED_KEY es una clave de v2', () => {
  assert.equal(IMPORTED_KEY, 'fb2:importado');
});

test('copia mi equipo y los seguidos de v1 la primera vez', () => {
  const s = almacenDePrueba({ 'futbol-base:v2': JSON.stringify({ myTeam: EQUIPO, recent: [] }), 'futbol-base:jugadores': JSON.stringify([{ id: 1, n: 'A' }]) });
  assert.deepEqual(importFromV1(s, OPC), { store: true, followed: true });
  assert.equal(s.datos['fb2:almacen'], s.datos['futbol-base:v2']);
  assert.equal(s.datos['fb2:jugadores'], s.datos['futbol-base:jugadores']);
  assert.equal(s.datos['fb2:importado'], '1');
  // Y la app los lee de sus claves: mi equipo con su temporada y el jugador seguido.
  assert.deepEqual(cargar(s), { myTeam: EQUIPO, recent: [] });
  assert.deepEqual(loadFollowed(s), [{ id: '1', n: 'A' }]);
});

test('la marca va antes que la copia', () => {
  const s = almacenDePrueba(V1);
  importFromV1(s, OPC);
  assert.deepEqual(s.escrituras, [['set', 'fb2:importado'], ['set', 'fb2:almacen'], ['set', 'fb2:jugadores']]);
});

test('la segunda vez no hace nada, aunque v1 haya cambiado', () => {
  const s = almacenDePrueba(V1);
  assert.deepEqual(importFromV1(s, OPC), { store: true, followed: true });
  const almacen = s.datos['fb2:almacen'];
  const jugadores = s.datos['fb2:jugadores'];
  // v1 sigue viva al lado: el dueño cambia allí su equipo y sus seguidos.
  s.datos['futbol-base:v2'] = JSON.stringify({ myTeam: OTRO, recent: [] });
  s.datos['futbol-base:jugadores'] = JSON.stringify([{ id: '9', n: 'Ana' }]);
  s.escrituras.length = 0;
  assert.deepEqual(importFromV1(s, OPC), NADA);
  assert.equal(s.datos['fb2:almacen'], almacen);
  assert.equal(s.datos['fb2:jugadores'], jugadores);
  assert.deepEqual(s.escrituras, [], 'ni siquiera vuelve a poner la marca');
  assert.deepEqual(cargar(s).myTeam, EQUIPO);
});

test('«Borrar datos» dura: tras clearStore y otra importación, el equipo por defecto', () => {
  const s = almacenDePrueba(V1);
  importFromV1(s, OPC); clearStore(s);
  assert.deepEqual(importFromV1(s, OPC), { store: false, followed: false });
  assert.equal(loadStore(s, { defaultTeam: POR_DEFECTO, portalSeason: '2026-2027' }).myTeam.name, POR_DEFECTO.name);
  assert.equal(s.datos['fb2:importado'], '1');
  assert.equal(s.datos['fb2:almacen'], undefined);
  assert.equal(s.datos['fb2:jugadores'], undefined);
  assert.deepEqual(loadFollowed(s), []);
});

test('no pisa lo que v2 ya tiene', () => {
  const mio = JSON.stringify({ myTeam: OTRO, recent: [] });
  const seguidos = JSON.stringify([{ id: '9', n: 'Ana' }]);
  const s = almacenDePrueba({ ...V1, 'fb2:almacen': mio, 'fb2:jugadores': seguidos });
  assert.deepEqual(importFromV1(s, OPC), NADA);
  assert.equal(s.datos['fb2:almacen'], mio);
  assert.equal(s.datos['fb2:jugadores'], seguidos);
  assert.equal(s.datos['fb2:importado'], '1');
  // Cada clave va por su lado: con solo el almacén de v2, los seguidos sí se traen.
  const medio = almacenDePrueba({ ...V1, 'fb2:almacen': mio });
  assert.deepEqual(importFromV1(medio, OPC), { store: false, followed: true });
  assert.equal(medio.datos['fb2:almacen'], mio);
  assert.equal(medio.datos['fb2:jugadores'], V1['futbol-base:jugadores']);
});

test('sin almacén en v1 pero con favoritos antiguos, los migra', () => {
  // AD Huracán elegido entre los favoritos de la app anterior: no es el equipo por defecto.
  const favoritos = JSON.stringify({ teams: [{ name: 'Las Mesas Hu.', cat: 'prebenjamin', groupId: 'PG2' },
    { name: 'AD Huracán', cat: 'prebenjamin', groupId: 'PG2' }], selected: 'prebenjamin|PG2|huracan' });
  const migrado = migrateV1(JSON.parse(favoritos));
  assert.deepEqual(migrado.myTeam, EQUIPO);
  // Sin el almacén de v1, o con uno que no es un objeto JSON.
  for (const almacenV1 of [undefined, '{roto', '[]', 'null', '"texto"']) {
    const inicial = { 'futbol-base:favorites:v1': favoritos };
    if (almacenV1 !== undefined) inicial['futbol-base:v2'] = almacenV1;
    const s = almacenDePrueba(inicial);
    assert.deepEqual(importFromV1(s, OPC), { store: true, followed: false }, String(almacenV1));
    assert.deepEqual(JSON.parse(s.datos['fb2:almacen']), migrado, String(almacenV1));
    // La temporada es la de los favoritos, no la del portal: resolveMyTeam hará el cambio de temporada.
    assert.deepEqual(loadStore(s, { defaultTeam: POR_DEFECTO, portalSeason: '2026-2027' }), migrado, String(almacenV1));
  }
  // Con almacén de v1, manda él: los favoritos antiguos ni se migran.
  const s = almacenDePrueba({ 'futbol-base:v2': JSON.stringify({ myTeam: OTRO, recent: [] }), 'futbol-base:favorites:v1': favoritos });
  assert.deepEqual(importFromV1(s, OPC), { store: true, followed: false });
  assert.deepEqual(cargar(s).myTeam, OTRO);
});

test('nunca toca las claves de v1', () => {
  const v1 = { ...V1, season: '2024-2025', cat: 'benjamin', theme: 'light' };
  const s = almacenDePrueba(v1);
  importFromV1(s, OPC);
  cargar(s);
  clearStore(s);
  importFromV1(s, OPC);
  cargar(s);
  for (const [clave, valor] of Object.entries(v1)) assert.equal(s.datos[clave], valor, clave);
  assert.deepEqual(s.escrituras.filter(([, clave]) => !clave.startsWith('fb2:')), [], 'solo escribe y borra claves fb2:');
  // También con los favoritos antiguos como única fuente.
  const solo = almacenDePrueba({ 'futbol-base:favorites:v1': V1['futbol-base:favorites:v1'] });
  importFromV1(solo, OPC);
  assert.equal(solo.datos['futbol-base:favorites:v1'], V1['futbol-base:favorites:v1']);
  assert.deepEqual(solo.escrituras, [['set', 'fb2:importado'], ['set', 'fb2:almacen']]);
});

test('loadStore ya no mira v1: lo de v1 entra solo por importFromV1', () => {
  const s = almacenDePrueba(V1);
  assert.deepEqual(cargar(s), { myTeam: { ...POR_DEFECTO, season: '2026-2027' }, recent: [] });
  assert.deepEqual(loadFollowed(s), []);
  assert.deepEqual(s.escrituras, [], 'ni escribe nada');
});

test('test_importar_ignora_lo_corrupto', () => {
  const s = almacenDePrueba({ 'futbol-base:v2': '{no es json', 'futbol-base:jugadores': '"texto"' });
  assert.deepEqual(importFromV1(s, OPC), { store: false, followed: false });
  assert.equal(loadStore(s, { defaultTeam: POR_DEFECTO, portalSeason: '2026-2027' }).myTeam.name, POR_DEFECTO.name);
  assert.deepEqual(s.escrituras, [['set', 'fb2:importado']]);
  // Seguidos que no son una lista y favoritos antiguos sin equipos válidos, tampoco.
  for (const [jugadores, favoritos] of [['{"id":"7"}', '{"teams":[]}'], ['null', '{roto'], ['7', '[]']]) {
    const t = almacenDePrueba({ 'futbol-base:jugadores': jugadores, 'futbol-base:favorites:v1': favoritos });
    assert.deepEqual(importFromV1(t, OPC), NADA, jugadores);
    assert.deepEqual(Object.keys(t.datos).filter((k) => k.startsWith('fb2:')), ['fb2:importado'], jugadores);
  }
});

test('un equipo de v1 de una categoría que v2 no tiene acaba en el equipo por defecto', () => {
  // Un equipo de una categoría que v2 no tiene y un seguido mal formado: se copian tal cual, y la
  // validación fina la hacen loadStore y loadFollowed.
  const viejo = { name: 'CD Viejo', season: '2025-2026', cat: 'senior', groupId: 'I1' };
  const s = almacenDePrueba({
    'futbol-base:v2': JSON.stringify({ myTeam: viejo, recent: [] }),
    'futbol-base:jugadores': JSON.stringify([{ id: 'x' }, { id: '7', n: 'Luis' }]),
  });
  assert.deepEqual(importFromV1(s, { portalSeason: '2025-2026' }), { store: true, followed: true });
  assert.deepEqual(JSON.parse(s.datos['fb2:almacen']).myTeam, viejo);
  // El arranque de la app (loadStore y resolveMyTeam contra la temporada): el equipo por defecto, resuelto.
  const ctx = startContext({ storage: s, portal: { season: '2025-2026', defaultTeam: POR_DEFECTO },
    datasets: datasetsFrom(fixture('current-2025-2026')), today: '2026-03-01' });
  assert.deepEqual(ctx.myTeam, { ...POR_DEFECTO, season: '2025-2026' });
  assert.equal(ctx.resolution.status, 'ok');
  assert.equal(ctx.resolution.name, POR_DEFECTO.name);
  assert.equal(ctx.resolution.group.id, POR_DEFECTO.groupId);
  assert.deepEqual(ctx.followed, [{ id: '7', n: 'Luis' }]);
});

// Un equipo de v1 bien formado que no está en los datos (su nombre no sale en ningún grupo, o su grupo ya no
// existe) se trae tal cual y se resuelve como en v1, que arranca con el mismo startContext y la misma
// resolución (myteam.js): sin candidatos, ausente; con otro equipo de su club, se pregunta. Es decir, como si
// v2 lo hubiera guardado ella misma, y sin lanzar.
test('un equipo de v1 bien formado que no está en los datos acaba como en v1: ausente o preguntar', () => {
  const portal = { season: '2025-2026', defaultTeam: POR_DEFECTO };
  const datasets = datasetsFrom(fixture('current-2025-2026'));
  const arrancar = (storage) => startContext({ storage, portal, datasets, today: '2026-03-01' });
  const estado = (ctx) => ({ myTeam: ctx.myTeam, status: ctx.resolution.status,
    candidates: (ctx.resolution.candidates || []).map((c) => `${c.cat}|${c.group.id}|${c.name}`) });
  for (const [equipo, esperado] of [
    [{ name: 'CD Inexistente', season: '2025-2026', cat: 'prebenjamin', groupId: 'PG2' }, { status: 'absent', candidates: [] }],
    [{ name: 'Las Mesas Hu. B', season: '2025-2026', cat: 'prebenjamin', groupId: 'PG9' },
      { status: 'ask', candidates: ['prebenjamin|PG2|Las Mesas Hu.'] }],
  ]) {
    const almacen = JSON.stringify({ myTeam: equipo, recent: [] });
    const s = almacenDePrueba({ 'futbol-base:v2': almacen });
    assert.deepEqual(importFromV1(s, { portalSeason: '2025-2026' }), { store: true, followed: false }, equipo.name);
    let ctx;
    assert.doesNotThrow(() => { ctx = arrancar(s); }, equipo.name);
    // Sigue siendo su equipo (no el de por defecto), ausente o con la pregunta.
    assert.deepEqual(estado(ctx), { myTeam: equipo, ...esperado }, equipo.name);
    assert.deepEqual(estado(ctx), estado(arrancar(almacenDePrueba({ 'fb2:almacen': almacen }))), equipo.name);
  }
});

test('test_importar_con_almacenamiento_que_falla', () => {
  const roto = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('bloqueado'); }, removeItem() {} };
  assert.deepEqual(importFromV1(roto, OPC), { store: false, followed: false });
  // Sin almacenamiento, con las cookies bloqueadas (leer el Storage ya lanza) o sin cuota para escribir.
  const sinCuota = { ...almacenDePrueba(V1), setItem() { throw new Error('QuotaExceededError'); } };
  for (const almacen of [null, undefined, {}, () => { throw new Error('SecurityError'); }, sinCuota]) {
    assert.deepEqual(importFromV1(almacen, OPC), NADA);
  }
  // Si la marca entra pero la copia no cabe, dice la verdad: no se copió.
  const justo = almacenDePrueba(V1);
  const poner = justo.setItem;
  justo.setItem = (k, v) => { if (k !== 'fb2:importado') throw new Error('QuotaExceededError'); poner(k, v); };
  assert.deepEqual(importFromV1(justo, OPC), NADA);
  assert.equal(justo.datos['fb2:importado'], '1');
  assert.equal(justo.datos['fb2:almacen'], undefined);
});

test('sin nada en v1 solo deja la marca', () => {
  const s = almacenDePrueba();
  assert.deepEqual(importFromV1(s, OPC), { store: false, followed: false });
  assert.deepEqual(s.datos, { 'fb2:importado': '1' });
});
