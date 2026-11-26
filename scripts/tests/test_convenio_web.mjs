// El modelo de la web con infantil, cadete y juvenil (parte E2, tarea 2): las seis categorías, la isla
// «interinsular» y TODAS las fases del convenio de códigos de la parte E1 (scripts/convenio.py, su tabla en
// scripts/tests/fixtures/convenio_mayores.json: nombre de la federación → [prefijo, fase, isla, tipo]).
// - Ninguna fase cae en «otra-…» (sin clasificar: saldría sin nombre en Ligas, y la sonda de activar_auto
//   daría la activación por fallida).
// - Dos prefijos distintos de la misma categoría e isla nunca dan la misma clave de competición (saldrían
//   juntas en Ligas: dos copas de Lanzarote, «Copa Insular» y «Copa Preferente»; o dos eliminatorias).
// - Las de tipo liga son ligas, y las demás (copa, final, ascenso y eliminatorias), copas.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import {
  CATEGORIES, CAT_NAMES, CAT_WORDS, CAT_SHORT, LAZY_CATS, buildSeason, competitionKey, competitions, groupKind,
  groupLabel, phaseLevel,
} from '../../src/model.js';
import { isCupGroup } from '../../src/state.js';
import { SCREEN_MAP } from '../../src/screens.js';
import { ctxFor, datasetsFor, lazyWith, PORTAL_SEASON } from './fixtures/rediseno/screens.mjs';

const CONVENIO = JSON.parse(readFileSync(new URL('./fixtures/convenio_mayores.json', import.meta.url), 'utf8'));
const SEASON = '2026-2027';
const CAT_OF_PREFIX = [['INF', 'infantil'], ['CAD', 'cadete'], ['JUV', 'juvenil'], ['AL', 'alevin']];
const catOf = prefix => CAT_OF_PREFIX.find(([p]) => prefix.startsWith(p))[1];
// Un grupo crudo como los de data-<cat>.js, con su categoría por el prefijo y el nombre de la federación.
const rawOf = (name, [prefix, phase, island]) => ({
  id: `${prefix}1`, cat: catOf(prefix), phase, island, name: 'Grupo 1', fullName: `${name} - GRUPO 1`,
});

test('test_todas_las_fases_del_convenio: cada fase, conocida y con su clave; ninguna clave para dos prefijos', () => {
  const rows = Object.entries(CONVENIO);
  assert.ok(rows.length >= 130, `la tabla entera (${rows.length})`);
  const owners = new Map();                 // categoría|isla|clave → prefijo
  for (const [name, row] of rows) {
    const [prefix, phase, island, tipo] = row;
    const raw = rawOf(name, row);
    const ck = competitionKey(raw, SEASON);
    assert.ok(!ck.key.startsWith('otra-') && !ck.key.startsWith(`${island}-otra-`), `${prefix} «${phase}»: sin clasificar (${ck.key})`);
    assert.equal(ck.island, island, `${prefix}: su isla`);
    assert.ok(ck.label && !/\bde Interinsular\b/.test(ck.label), `${prefix} «${phase}»: su nombre (${ck.label})`);
    const id = `${raw.cat}|${island}|${ck.key}`;
    const owner = owners.get(id);
    assert.ok(!owner || owner === prefix, `${prefix} «${phase}» y ${owner} comparten la clave ${ck.key}`);
    owners.set(id, prefix);
    const cup = tipo !== 'liga';
    assert.equal(isCupGroup(raw), cup, `${prefix} «${phase}» (${tipo}): isCupGroup`);
    assert.equal(groupKind(raw) !== 'league', cup, `${prefix} «${phase}» (${tipo}): groupKind`);
    assert.ok([1, 2].includes(phaseLevel({ ...raw, season: SEASON })), `${prefix}: su nivel`);
    // La categoría sale también del nombre, sin `cat` (las filas de las fichas de jugador).
    assert.equal(competitionKey({ ...raw, cat: undefined }, SEASON).cat, raw.cat, `${prefix}: su categoría por el nombre`);
  }
});

test('test_etiquetas: la División de Honor no es «de Interinsular»; fuera de Gran Canaria, la isla detrás', () => {
  assert.equal(groupLabel({ season: SEASON, cat: 'juvenil', phase: 'División de Honor', island: 'interinsular', name: 'Grupo 6' }),
    'Juvenil, División de Honor, Grupo 6');
  assert.equal(groupLabel({ season: SEASON, cat: 'cadete', phase: 'Insular Lanzarote', island: 'lanzarote', name: 'Grupo 1' }),
    'Cadete, Insular, Grupo 1 de Lanzarote');
  assert.equal(groupLabel({ season: SEASON, cat: 'infantil', phase: 'Preferente GC Fase Oro', island: 'grancanaria', name: 'Grupo 1' }),
    'Infantil, Preferente Fase Oro, Grupo 1');
  assert.equal(groupLabel({ season: SEASON, cat: 'juvenil', phase: 'División de Honor Fase 2 C', island: 'interinsular', name: 'Grupo 1' }),
    'Juvenil, División de Honor Fase 2 C, Grupo 1');
  assert.equal(groupLabel({ season: SEASON, cat: 'cadete', phase: 'Insular B Lanzarote', island: 'lanzarote', name: 'Grupo 1' }),
    'Cadete, Insular B, Grupo 1 de Lanzarote');
  assert.equal(groupLabel({ season: SEASON, cat: 'cadete', phase: 'Insular GC Fase 1', island: 'grancanaria', name: 'Grupo 2' }),
    'Cadete, Insular Fase 1, Grupo 2');
  const ascenso = competitionKey({ cat: 'cadete', phase: 'Fase de Ascenso a Interinsular', island: 'interinsular' }, SEASON);
  assert.equal(ascenso.cup, 'ascenso');
  assert.equal(ascenso.label, 'Fase de Ascenso a Interinsular');
  const copa = competitionKey({ cat: 'cadete', phase: 'Copa Insular Lanzarote', island: 'lanzarote' }, SEASON);
  assert.deepEqual([copa.cup, copa.division, copa.label], ['insular', 'insular', 'Copa Insular de Lanzarote']);
  const cabildo = competitionKey({ cat: 'cadete', phase: 'Copa Cabildo Insular Lanzarote', island: 'lanzarote' }, SEASON);
  assert.notEqual(cabildo.key, copa.key, 'la Copa Cabildo Insular y la Copa Insular, dos competiciones');
});

test('test_niveles: la fase de ascenso y la Segunda Fase con subgrupo, nivel 2; la liga, nivel 1', () => {
  const level = (cat, phase, island = 'interinsular') => phaseLevel({ season: SEASON, id: 'X1', cat, phase, island, name: 'Grupo 1' });
  assert.equal(level('juvenil', 'Fase de Ascenso a División de Honor'), 2);
  assert.equal(level('juvenil', 'División de Honor Fase 2 C'), 2);
  assert.equal(level('cadete', 'Insular GC Fase 1', 'grancanaria'), 1);
  assert.equal(level('juvenil', 'División de Honor'), 1);
  assert.equal(level('infantil', 'Preferente GC Fase Oro', 'grancanaria'), 2, 'como el oro de Fuerteventura');
});

test('test_categorias: las seis, las de hoy en su orden y las nuevas detrás; las perezosas', () => {
  assert.deepEqual(CATEGORIES, ['benjamin', 'prebenjamin', 'alevin', 'infantil', 'cadete', 'juvenil']);
  assert.deepEqual(CAT_NAMES, { benjamin: 'Benjamín', prebenjamin: 'Prebenjamín', alevin: 'Alevín', infantil: 'Infantil', cadete: 'Cadete', juvenil: 'Juvenil' });
  assert.deepEqual(CAT_WORDS, { benjamin: 'benjamín', prebenjamin: 'prebenjamín', alevin: 'alevín', infantil: 'infantil', cadete: 'cadete', juvenil: 'juvenil' });
  assert.deepEqual(CAT_SHORT, { benjamin: 'benj.', prebenjamin: 'preb.', alevin: 'alev.', infantil: 'inf.', cadete: 'cad.', juvenil: 'juv.' });
  assert.deepEqual(LAZY_CATS, ['alevin', 'infantil', 'cadete', 'juvenil']);
  const catOfName = fullName => competitionKey({ fullName, phase: 'Insular GC', island: 'grancanaria' }, SEASON).cat;
  assert.equal(catOfName('CADETE INSULAR GC - GRUPO 2'), 'cadete');
  assert.equal(catOfName('LIGA INFANTIL PREFERENTE DE GRAN CANARIA - GRUPO 1'), 'infantil');
  assert.equal(catOfName('LIGA SEGUNDA JUVENIL GRAN CANARIA - GRUPO 1'), 'juvenil');
  assert.equal(catOfName('PREBENJAMIN PRIMERA GRAN CANARIA G-1'), 'prebenjamin');
  assert.equal(catOfName('BENJAMIN PRIMERA FASE GC - GRUPO 3'), 'benjamin');
  assert.equal(catOfName('ALEVIN PRIMERA FASE GC - GRUPO 3'), 'alevin');
});

test('buildSeason con las perezosas: cada grupo con su categoría', () => {
  const g = (id, phase) => ({ id, name: 'Grupo 1', phase, island: 'grancanaria', standings: [], jornadas: {} });
  const season = buildSeason({
    name: '2025-2026', benjamin: [g('FF1', 'Primera Fase GC')], alevin: [g('AL1', 'Primera Fase GC')],
    infantil: [g('INFPG1', 'Preferente GC')], cadete: [g('CADNG1', 'Insular GC')], juvenil: [g('JUV2G1', 'Segunda GC')],
  });
  assert.deepEqual(season.groups.map(x => [x.id, x.cat]), [
    ['FF1', 'benjamin'], ['AL1', 'alevin'], ['INFPG1', 'infantil'], ['CADNG1', 'cadete'], ['JUV2G1', 'juvenil']]);
  assert.equal(season.groups[2].label, 'Infantil, Preferente, Grupo 1');
});

// ── El orden de las competiciones de infantil, cadete y juvenil ──────────
//
// Dentro de una categoría nueva, las ligas van del nivel más alto al más bajo, y el nivel manda sobre la isla y
// sobre la fase: División de Honor, Autonómica, Interinsular, (Fase Oro), Preferente, (Fase Plata), Primera,
// Segunda, Insular, Insular B y, al final, las de una sola división de su isla; a igual nivel, Gran Canaria,
// Lanzarote, Fuerteventura y las interinsulares. Después, las copas, ascensos, eliminatorias y finales, con la
// misma regla (como en benjamín, detrás de todas las ligas). Con TODAS las fases del convenio, en Ligas
// (`c=<cat>`) y en Explorar.
const ORDEN_LIGAS = {
  infantil: ['Preferente Fase Oro', 'Preferente', 'Preferente de Lanzarote', 'Preferente Fase Plata', 'Primera',
    'Primera de Lanzarote', 'Gran Canaria', 'Fase 2 de Lanzarote', 'Fase 1 de Lanzarote', 'Fase 2 de Fuerteventura',
    'Fase 1 de Fuerteventura', 'Fuerteventura'],
  cadete: ['Autonómica', 'Interinsular', 'Preferente', 'Preferente de Lanzarote', 'Primera', 'Primera de Lanzarote',
    'Insular Fase 1', 'Insular', 'Insular de Lanzarote', 'Insular de Fuerteventura', 'Insular B de Lanzarote',
    'Fuerteventura'],
  juvenil: ['División de Honor Fase 2 C', 'División de Honor Fase 2 D', 'División de Honor', 'Interinsular',
    'Preferente', 'Preferente de Lanzarote', 'Preferente de Fuerteventura', 'Primera', 'Segunda'],
};
// Una competición por prefijo y fase del convenio, de cada categoría nueva, con un id propio cada una.
function convenioPorCategoria() {
  const out = { infantil: [], cadete: [], juvenil: [] };
  const seen = new Set();
  for (const [name, [prefix, phase, island]] of Object.entries(CONVENIO)) {
    const cat = catOf(prefix);
    if (!out[cat] || seen.has(`${prefix}|${phase}`)) continue;
    seen.add(`${prefix}|${phase}`);
    out[cat].push({ id: `${prefix}${out[cat].length + 1}`, phase, island, fullName: `${name} - GRUPO 1`, teams: ['Club Uno', 'Club Dos'] });
  }
  return out;
}
const DIVISIONES = ['division-de-honor', 'autonomica', 'interinsular', 'territorial', 'preferente', 'primera', 'segunda',
  'insular', 'insular-b', 'unica'];
const ISLAS = ['grancanaria', 'lanzarote', 'fuerteventura', 'interinsular'];
// El nivel de la liga de una competición, para comprobar las copas: su división y, en ella, oro antes y plata
// después.
const nivelDe = ck => DIVISIONES.indexOf(ck.division) * 3 + (ck.phase === 'oro' ? 0 : ck.phase === 'plata' ? 2 : 1);

test('test_orden_de_las_ligas: en las nuevas, el nivel de la liga manda sobre la isla y la fase; las copas, detrás', () => {
  const por = convenioPorCategoria();
  const raws = Object.fromEntries(Object.entries(por).map(([cat, list]) => [cat, list.map(({ teams, ...g }) => ({ ...g, name: 'Grupo 1', standings: [], matches: [] }))]));
  const season = buildSeason({ name: SEASON, current: true, ...raws });
  const model = { season: n => (n === SEASON ? season : null), cups: () => null };
  for (const cat of Object.keys(ORDEN_LIGAS)) {
    const list = competitions(model, SEASON, { cat });
    assert.deepEqual(list.filter(e => e.kind === 'liga').map(e => e.label), ORDEN_LIGAS[cat], `ligas de ${cat}`);
    const kinds = list.map(e => e.kind);
    assert.equal(kinds.lastIndexOf('liga') < kinds.indexOf('copa'), true, `${cat}: las copas, detrás de las ligas`);
    const copas = list.filter(e => e.kind === 'copa').map(e => competitionKey(e.groups[0], SEASON));
    assert.ok(copas.length > 0);
    copas.forEach((ck, k) => {
      if (!k) return;
      const a = [nivelDe(copas[k - 1]), ISLAS.indexOf(copas[k - 1].island)], b = [nivelDe(ck), ISLAS.indexOf(ck.island)];
      assert.ok(a[0] < b[0] || (a[0] === b[0] && a[1] <= b[1]), `${cat}: «${ck.label}» después de una de nivel o isla mayor`);
    });
    // Sin `cat` (Explorar), lo mismo dentro de cada categoría.
    assert.deepEqual(competitions(model, SEASON).filter(e => e.cat === cat).map(e => e.key), list.map(e => e.key), `${cat} sin filtro`);
  }
});

test('test_orden_de_las_ligas: en Ligas (c=<cat>) y en Explorar, con todas las fases del convenio', () => {
  const por = convenioPorCategoria();
  const lazy = Object.fromEntries(Object.entries(por).map(([cat, list]) => [cat, lazyWith(cat, list)]));
  const seasons = [{ name: PORTAL_SEASON, current: true, lazy: ['infantil', 'cadete', 'juvenil'] }, { name: '2024-2025', current: false }];
  const datasets = datasetsFor({ seasons, lazy });
  const labels = (out, cls = 'link-row') => [...String(out).matchAll(new RegExp(`<a class="${cls}[^"]*" href="([^"]+)">(.*?)</a>`, 'g'))]
    .map(m => [m[1].replace(/&amp;/g, '&'), m[2].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()]);
  const explorar = String(SCREEN_MAP.explorar.render(ctxFor('explorar', {}, { datasets })));
  for (const cat of Object.keys(ORDEN_LIGAS)) {
    const ligas = labels(SCREEN_MAP.ligas.render(ctxFor('ligas', { s: PORTAL_SEASON, c: cat }, { datasets })))
      .filter(([href]) => href.includes(`c=${cat}&f=`));
    const nombres = ligas.map(([, t]) => t.replace(/ \d+ grupos?$/, ''));
    assert.deepEqual(nombres.slice(0, ORDEN_LIGAS[cat].length), ORDEN_LIGAS[cat], `Ligas de ${cat}`);
    const enExplorar = labels(explorar).filter(([href]) => href.includes(`c=${cat}&f=`)).map(([, t]) => t.replace(/ \d+ grupos?$/, ''));
    assert.deepEqual(enExplorar, ORDEN_LIGAS[cat], `Explorar, ligas de ${cat}`);
  }
});
