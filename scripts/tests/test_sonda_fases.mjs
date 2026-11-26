/**
 * La sonda de «otra-…» como script (scripts/sonda_fases.mjs), la que pasa
 * activar_auto.py después de activar. Árboles de prueba en una carpeta temporal; nunca los data-*.js
 * ni src/config.js vivos.
 * Run: node --test scripts/tests/test_sonda_fases.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sonda } from '../sonda_fases.mjs';

const SCRIPT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'sonda_fases.mjs');

function tree({ benjamin = [], prebenjamin = [], alevin = [] } = {}) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'sonda-fases-'));
  mkdirSync(path.join(root, 'src'));
  writeFileSync(path.join(root, 'src', 'config.js'),
    'export const PORTAL = {"season": "2026-2027", "nextSeason": "2027-2028"};\n');
  writeFileSync(path.join(root, 'data-benjamin.js'), `const BENJAMIN=${JSON.stringify(benjamin)};\n`);
  writeFileSync(path.join(root, 'data-prebenjamin.js'), `const PREBENJAMIN=${JSON.stringify(prebenjamin)};\n`);
  writeFileSync(path.join(root, 'data-alevin.js'), `const ALEVIN=${JSON.stringify(alevin)};\n`);
  return root;
}

const grupo = (id, phase, island = 'grancanaria') => ({ id, name: 'Grupo 1', phase, island, standings: [] });

test('sin fases desconocidas sale con 0 y dice cuántos grupos ha mirado', () => {
  const root = tree({ benjamin: [grupo('FF1', 'Primera Fase GC'), grupo('CGC1', 'Copa Gran Canaria')],
    prebenjamin: [grupo('PFV1', 'Fuerteventura', 'fuerteventura')], alevin: [grupo('AL1', 'Primera Fase GC')] });
  const out = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8' });
  assert.equal(out.status, 0, out.stderr);
  assert.match(out.stdout, /2026-2027: 4 grupos, 0 en otra-…/);
});

test('una fase que la web no reconoce, también de alevín o de otra isla, sale con 1 y nombra cada grupo', async () => {
  const root = tree({ benjamin: [grupo('FF1', 'Primera Fase GC'), grupo('T1', 'Tercera Fase')],
    prebenjamin: [grupo('X1', 'Superfase Rara', 'lanzarote')], alevin: [grupo('ALZ1', 'Fase Imposible')] });
  const out = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8' });
  assert.equal(out.status, 1);
  assert.match(out.stdout, /benjamin T1 Tercera Fase → otra-tercera-fase/);
  assert.match(out.stdout, /prebenjamin X1 Superfase Rara → lanzarote-otra-/);
  assert.match(out.stdout, /alevin ALZ1 Fase Imposible → otra-/);
  const json = spawnSync(process.execPath, [SCRIPT, root, '--json'], { encoding: 'utf8' });
  assert.equal(json.status, 1);
  assert.deepEqual(JSON.parse(json.stdout).map((g) => [g.cat, g.id, g.phase]),
    [['benjamin', 'T1', 'Tercera Fase'], ['prebenjamin', 'X1', 'Superfase Rara'], ['alevin', 'ALZ1', 'Fase Imposible']]);
  const { otras, total } = await sonda(root);
  assert.equal(total, 4);
  assert.equal(otras.length, 3);
});

test('sin los datos de una categoría no da por buena la temporada: sale con error, no con 0', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'sonda-fases-'));
  mkdirSync(path.join(root, 'src'));
  writeFileSync(path.join(root, 'src', 'config.js'), 'export const PORTAL = {"season": "2026-2027"};\n');
  const out = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8' });
  assert.equal(out.status, 2);
});

test('los grupos de eliminatoria de una liga (EL, PEL, ALEL; fase «Eliminatorias») son una copa que la web reconoce', async () => {
  const { competitionKey } = await import('../../src/model.js');
  const { isCupGroup } = await import('../../src/state.js');
  for (const [cat, id] of [['benjamin', 'EL1'], ['prebenjamin', 'PEL1'], ['alevin', 'ALEL2']]) {
    const key = competitionKey({ cat, id, phase: 'Eliminatorias', island: 'grancanaria', name: 'Eliminatoria de Primeros y Segundos' }, '2026-2027');
    assert.equal(key.key, 'eliminatorias');
    assert.equal(key.cup, 'eliminatorias');
    assert.equal(isCupGroup({ id, phase: 'Eliminatorias' }), true);
  }
  const root = tree({ benjamin: [grupo('FF1', 'Primera Fase GC'), grupo('EL1', 'Eliminatorias')], alevin: [grupo('ALEL1', 'Eliminatorias')] });
  assert.deepEqual((await sonda(root)).otras, []);
});

// Infantil, cadete y juvenil (parte E2): sus data-<cat>.js perezosos también. Con EN_WEB ampliado, una fase
// nueva de una de ellas tiene que parar la activación automática como la de benjamín. Son opcionales: un árbol
// sin ellos (los de antes de E2) se mira igual.
function treeConMayores(base, mayores) {
  const root = tree(base);
  for (const [cat, groups] of Object.entries(mayores))
    writeFileSync(path.join(root, `data-${cat}.js`), `const ${cat.toUpperCase()}=${JSON.stringify(groups)};\n`);
  return root;
}

test('un grupo de cadete en una fase que el modelo no conoce: la sonda lo cuenta y sale con 1', async () => {
  const root = treeConMayores({ benjamin: [grupo('FF1', 'Primera Fase GC')] }, {
    infantil: [grupo('INFPG1', 'Preferente GC')], cadete: [grupo('CADI1', 'Interinsular', 'interinsular'), grupo('CADZZ1', 'Fase Rara Inventada')],
    juvenil: [grupo('JUVH1', 'División de Honor', 'interinsular')],
  });
  const out = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8' });
  assert.equal(out.status, 1, out.stderr);
  assert.match(out.stdout, /cadete CADZZ1 Fase Rara Inventada → otra-/);
  assert.match(out.stdout, /2026-2027: 5 grupos, 1 en otra-…/);
  const { otras, total } = await sonda(root);
  assert.equal(total, 5);
  assert.deepEqual(otras.map((g) => [g.cat, g.id]), [['cadete', 'CADZZ1']]);
  // Con las fases del convenio, ninguna: sale con 0.
  const bien = treeConMayores({ benjamin: [grupo('FF1', 'Primera Fase GC')] }, { cadete: [grupo('CADI1', 'Interinsular', 'interinsular')] });
  const ok = spawnSync(process.execPath, [SCRIPT, bien], { encoding: 'utf8' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.match(ok.stdout, /2026-2027: 2 grupos, 0 en otra-…/);
});
