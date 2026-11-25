// Los mundos de navegador de fixture-site.mjs. Cada mundo solo
// anuncia en SEASONS las temporadas cuyo archivo sirve, y sirve el que anuncia: Temporadas, la
// Trayectoria de Equipo o el selector de Explorar nunca llevan a un fichero que da 404. Y sirve los
// datos de las fixtures ampliadas: los goleadores congelados, la Copa de Campeones en los mundos del
// 23/09/2026 (se jugó en junio), las cuatro copas de la Maspalomas y las actas de A1 y FF1. Solo
// fixtures: nunca los data-*.js vivos.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import vm from 'node:vm';
import { WORLDS, worldFiles } from './fixture-site.mjs';
import { fixture } from './fixtures/rediseno/load.mjs';
import { archive, goleadores, groupLineups, lineupsFor } from './fixtures/rediseno/simulate.mjs';
import { buildSeason } from '../../src/model.js';

// Los globales que declara un fichero servido, como los lee el navegador; en este reino (los objetos
// de node:vm tienen otros prototipos, y deepStrictEqual los distinguiría).
function globalsOf(file) {
  const ctx = vm.createContext({});
  vm.runInContext(file.body.replace(/^const /gm, 'var '), ctx);
  return JSON.parse(JSON.stringify(ctx));
}
const seasonsOf = (files) => globalsOf(files['data-seasons.js']).SEASONS;

test('cada mundo anuncia en SEASONS las temporadas cuyo archivo sirve, y solo esas (decisión 31)', () => {
  for (const name of Object.keys(WORLDS)) {
    const files = worldFiles(name);
    const seasons = seasonsOf(files);
    assert.deepEqual(seasons.filter((s) => s.current).map((s) => s.name), [WORLDS[name].portalSeason], name);
    const past = seasons.filter((s) => !s.current).map((s) => s.name).sort();
    const served = Object.keys(files).map((f) => (f.match(/^data-season-(\d{4}-\d{4})\.js$/) || [])[1]).filter(Boolean).sort();
    assert.deepEqual(served, past, name);
    for (const season of past) {
      const raw = globalsOf(files[`data-season-${season}.js`])[`SEASON_${season.replace('-', '_')}`];
      assert.deepEqual([raw.name, raw.current], [season, false], `${name} ${season}`);
    }
  }
  assert.throws(() => worldFiles('Z'), /mundo desconocido: Z/);
});

test('en 2025/26, el archivo de las fixtures; en 2026/27, además 2025-26 terminada, con la forma de data-season-<S>.js', () => {
  const d = worldFiles('D');
  assert.deepEqual(seasonsOf(d).map((s) => s.name), ['2025-2026', '2024-2025', '2023-2024']);
  assert.deepEqual(globalsOf(d['data-season-2024-2025.js']).SEASON_2024_2025, archive('2024-2025'));
  assert.deepEqual(globalsOf(d['data-season-2023-2024.js']).SEASON_2023_2024, archive('2023-2024'));
  const b = worldFiles('B');
  assert.deepEqual(seasonsOf(b).map((s) => s.name), ['2026-2027', '2025-2026', '2024-2025']);
  const past = globalsOf(b['data-season-2025-2026.js']).SEASON_2025_2026;
  const season = buildSeason({ name: '2025-2026', current: false, benjamin: past.benjamin, prebenjamin: past.prebenjamin });
  const final = buildSeason({ name: '2025-2026', current: true, ...fixture('current-2025-2026') });
  // La misma temporada que la del portal el 23/09/2026 (su clasificación y su calendario), más la Copa
  // de Campeones.
  const pg2 = (s) => s.groups.find((g) => g.id === 'PG2');
  const played = (g) => g.rounds.flatMap((r) => r.matches.map((m) => [r.key, m.home, m.away, m.hs, m.as, m.dateISO]));
  assert.deepEqual(pg2(season).standings, pg2(final).standings);
  assert.deepEqual(played(pg2(season)), played(pg2(final)));
  assert.deepEqual(season.groups.filter((g) => g.kind === 'cup-bracket').map((g) => g.id), ['BCA1', 'BCB1', 'BCC1', 'PCC1']);
});

test('los datos de B3: goleadores congelados, la Copa de Campeones el 23/09, las cuatro copas de la Maspalomas y las actas de A1 y FF1', () => {
  const d = worldFiles('D');
  assert.deepEqual(globalsOf(d['data-goleadores.js']).GOL_PREBENJ, goleadores().golPrebenj, 'el 23/09, los de fin de temporada');
  // A mitad de temporada (01/03/2026), reducidos a su día: el máximo goleador no lleva todavía sus 50 en 20.
  const leon = globalsOf(worldFiles('A')['data-goleadores.js']).GOL_PREBENJ.find((e) => e.id === 'PG2').s
    .find((row) => row[0] === 'León Rodríguez, Lucas');
  assert.ok(leon[2] < 50 && leon[3] < 20, JSON.stringify(leon));
  // La Copa de Campeones se jugó del 4 al 10 de junio: en los mundos del 23/09 está; en marzo y en junio, no.
  const ids = (files, cat) => globalsOf(files[`data-${cat}.js`])[cat.toUpperCase()].map((g) => g.id);
  assert.ok(ids(d, 'benjamin').includes('BCA1') && ids(worldFiles('E'), 'prebenjamin').includes('PCC1'));
  assert.ok(!ids(worldFiles('A'), 'benjamin').includes('BCA1') && !ids(worldFiles('C'), 'prebenjamin').includes('PCC1'));
  const cups = globalsOf(d['data-maspalomas-cup-2026.js']);
  assert.deepEqual([cups.MASPALOMAS_CUP_BENJAMIN.map((g) => g.id), cups.MASPALOMAS_CUP_PREBENJAMIN.map((g) => g.id)],
    [['MCB16', 'MCBK1', 'MCBK2'], ['MCP3', 'MCPK1', 'MCPK2']]);
  // Las actas, un fichero por grupo con actas (A1 y FF1), con las suyas.
  assert.deepEqual(Object.keys(d).filter((f) => f.startsWith('data-lineups-')), ['data-lineups-2025-2026-A1.js', 'data-lineups-2025-2026-FF1.js']);
  for (const g of ['A1', 'FF1']) {
    assert.deepEqual(Object.keys(globalsOf(d[`data-lineups-2025-2026-${g}.js`])[`LINEUPS_2025_2026_${g}`]), Object.keys(groupLineups('2025-2026', g)));
  }
  assert.equal(Object.keys(groupLineups('2025-2026', 'A1')).length + Object.keys(groupLineups('2025-2026', 'FF1')).length, Object.keys(lineupsFor('2025-2026')).length);
});

// Alevín (contrato común de alevín, puntos 4 y 5): el mundo L sirve data-alevin.js, con las seis
// constantes en su orden y los grupos AL1 y AL2, y el alevín de 2025-26; los demás, no (un 404, «sin
// alevín», que no notan: los smoke de siempre), salvo M, el de las seis categorías, que sirve lo mismo que L.
test('el mundo L sirve data-alevin.js (AL1 y AL2) y data-season-2025-2026-alevin.js; los demás, ninguno (M, lo de L)', () => {
  const l = worldFiles('L');
  const alevin = globalsOf(l['data-alevin.js']);
  assert.deepEqual(Object.keys(alevin), ['ALEVIN', 'ALEV_STATS', 'HISTORY_ALEV', 'GOL_ALEV', 'ESTADOS_ALEV', 'EQUIPOS_ALEV']);
  assert.deepEqual(alevin.ALEVIN.map((g) => g.id), ['AL1', 'AL2']);
  assert.deepEqual(Object.keys(alevin.HISTORY_ALEV), ['AL1', 'AL2']);
  const past = globalsOf(l['data-season-2025-2026-alevin.js']).SEASON_2025_2026_ALEVIN;
  assert.deepEqual(past.alevin.map((g) => `${g.id} ${g.phase}`), ['ALA1 Segunda Fase A', 'ALF1 Segunda Fase F', 'ALEL1 Eliminatorias']);
  for (const name of Object.keys(WORLDS).filter((w) => w !== 'L' && w !== 'M')) {
    assert.deepEqual(Object.keys(worldFiles(name)).filter((f) => /alevin/.test(f)), [], name);
  }
  const m = worldFiles('M');
  for (const file of ['data-alevin.js', 'data-season-2025-2026-alevin.js']) assert.equal(m[file].body, l[file].body, file);
});

test('el mundo M: infantil, cadete y juvenil con clubes de benjamín, CADI1 interinsular con actas y cronología, y SEASONS lo dice', () => {
  const m = worldFiles('M');
  const g = (file, name) => globalsOf(m[file])[name];
  assert.deepEqual(seasonsOf(m)[0], { name: '2026-2027', current: true, lazy: ['infantil', 'cadete', 'juvenil'] });
  assert.deepEqual(g('data-infantil.js', 'INFANTIL').map((x) => x.id), ['INFPG1', 'INF1G1']);
  const cadete = g('data-cadete.js', 'CADETE');
  assert.deepEqual(cadete.map((x) => [x.id, x.island, x.phase]), [['CADI1', 'interinsular', 'Interinsular'], ['CADNG1', 'grancanaria', 'Insular GC']]);
  assert.deepEqual(g('data-juvenil.js', 'JUVENIL').map((x) => x.id), ['JUV2G1']);
  // Clubes que también están en benjamín: el mismo nombre en dos categorías.
  const benjamin = new Set(g('data-benjamin.js', 'BENJAMIN').flatMap((x) => x.standings.map((row) => row[1])));
  assert.ok(benjamin.has('Guayarmina') && cadete[0].standings.some((row) => row[1] === 'Guayarmina'));
  assert.ok(benjamin.has('Arucas') && g('data-juvenil.js', 'JUVENIL')[0].standings.some((row) => row[1] === 'Arucas'));
  // Las actas de CADI1, una por partido jugado (tres jornadas de tres), con los goles de su marcador, y su cronología.
  const actas = g('data-lineups-2026-2027-CADI1.js', 'LINEUPS_2026_2027_CADI1');
  const detail = g('data-matchdetail-cadete.js', 'MATCH_DETAIL_CAD');
  assert.equal(Object.keys(actas).length, 9);
  assert.deepEqual(Object.keys(detail), Object.keys(actas));
  for (const [key, acta] of Object.entries(actas)) {
    const [hs, as] = key.split('|')[2].split('-').map(Number);
    assert.deepEqual([acta.home.reduce((n, p) => n + p.g, 0), acta.away.reduce((n, p) => n + p.g, 0)], [hs, as], key);
    assert.equal(detail[key].g.length, hs + as, key);
    assert.ok([...acta.home, ...acta.away].every((p) => p.n.startsWith('PRUEBA ')), `${key}: nombres inventados`);
  }
  // Los goleadores de cada grupo, inventados, y los de CADI1, los de sus actas.
  const gol = g('data-cadete.js', 'GOL_CAD');
  assert.deepEqual(gol.map((x) => x.id), ['CADI1', 'CADNG1']);
  assert.ok(gol.every((x) => x.s.length && x.s.every((row) => row[0].startsWith('PRUEBA '))));
  const total = Object.values(actas).reduce((n, a) => n + [...a.home, ...a.away].reduce((k, p) => k + p.g, 0), 0);
  assert.equal(gol[0].s.reduce((n, row) => n + row[2], 0), total);
  assert.deepEqual(g('data-matchdetail-juvenil.js', 'MATCH_DETAIL_JUV'), {});
});
