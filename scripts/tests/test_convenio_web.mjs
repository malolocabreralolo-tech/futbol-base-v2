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
  CATEGORIES, CAT_NAMES, CAT_WORDS, CAT_SHORT, LAZY_CATS, buildSeason, competitionKey, groupKind, groupLabel,
  phaseLevel,
} from '../../src/model.js';
import { isCupGroup } from '../../src/state.js';

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
