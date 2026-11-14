// Plan B2, tarea 3: la función pura del diseño anterior que sigue en model.js (spec §5.2):
// sourceInfo, que devuelve datos y no HTML (decisión 3); la pantalla Tabla lo pinta.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { fixture } from './fixtures/rediseno/load.mjs';
import * as model from '../../src/model.js';
import * as links from '../../src/links.js';
import { sourceInfo, buildSeason } from '../../src/model.js';

test('fase 3, tarea 3: sin las heredadas que solo usaban sus pruebas', () => {
  for (const gone of ['sortPlantillaRows', 'aggregatePlayerFromLineups', 'mergeAndOrderEvents',
    'resolveSeasonDataset', 'filterCompetitionGroups']) {
    assert.equal(gone in model, false, `${gone} sigue en model.js`);
  }
  assert.equal('matchDateISO' in links, false, 'matchDateISO sigue en links.js');
});

// ─── sourceInfo (decisión 3) ───────────────────────────────────────────────

const season = buildSeason({ name: '2025-2026', current: true, ...fixture('current-2025-2026') });
const groupOf = (id) => season.groups.find((group) => group.id === id);

test('sourceInfo: clasificación oficial de futbolaspalmas.com, con su enlace (PG2)', () => {
  assert.deepEqual(sourceInfo(groupOf('PG2')), {
    kind: 'oficial', source: 'futbolaspalmas.com', url: 'https://futbolaspalmas.com/1prebenjamin2',
  });
});

test('sourceInfo: sin URL no hay fuente ni enlace (PFV2, de la FIFLP)', () => {
  assert.deepEqual(sourceInfo(groupOf('PFV2')), { kind: 'oficial', source: null, url: null });
});

test('sourceInfo: calculada y corregida según standingsKind', () => {
  const pg2 = groupOf('PG2');
  assert.equal(sourceInfo({ ...pg2, standingsKind: 'reconstructed' }).kind, 'calculada');
  assert.equal(sourceInfo({ ...pg2, standingsKind: 'corrected' }).kind, 'corregida');
  assert.equal(sourceInfo({ ...pg2, standingsKind: null }).kind, 'oficial');
});

test('sourceInfo: en una temporada pasada no enlaza la página de la actual', () => {
  assert.deepEqual(sourceInfo(groupOf('PG2'), true), { kind: 'oficial', source: null, url: null });
});

test('sourceInfo: devuelve datos, no HTML, y nunca un enlace que no sea http(s)', () => {
  const info = sourceInfo({ id: 'X', url: 'javascript:alert(1)', standingsKind: 'source' });
  assert.deepEqual(info, { kind: 'oficial', source: null, url: null });
  assert.equal(sourceInfo({ id: 'X', url: 'http://' }).url, null, 'sin dominio no hay enlace');
  assert.equal(sourceInfo({ id: 'X', url: 'https://www.fiflp.com/pnfg/' }).source, 'fiflp.com');
  for (const value of Object.values(sourceInfo(groupOf('PG2')))) assert.doesNotMatch(String(value), /[<>]/);
});
