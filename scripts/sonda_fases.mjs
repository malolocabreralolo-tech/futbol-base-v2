#!/usr/bin/env node
// sonda_fases.mjs — ¿Alguna fase de la temporada en curso cae en «otra-…»? Es la clave que da
// competitionKey (src/model.js) a una fase que no reconoce: la web la enseña, pero suelta y con el nivel
// de la Primera Fase (PHASE_LEVEL). Ninguna prueba lo detecta a propósito (una fase nueva no debe parar
// al bot); esta sonda sí, y la pasa activar_auto.py después de activar (docs/temporada-nueva.md).
//
//   node scripts/sonda_fases.mjs [raíz] [--json]
//
// Lee de la raíz (por defecto, la del repositorio) src/config.js y los data-*.js de benjamín,
// prebenjamín y alevín (más data-history.js si está). Sale con 0 si ninguna fase cae en «otra-…» y con
// 1 nombrando cada grupo que cae; con --json imprime solo [{cat, id, phase, compKey}].
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';
import { buildSeason } from '../src/model.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FILES = ['data-benjamin.js', 'data-prebenjamin.js', 'data-alevin.js', 'data-history.js'];
// Fuera de Gran Canaria la clave lleva delante la isla: 'lanzarote-otra-…'.
const OTRA = /(^|-)otra-/;

export async function sonda(root = REPO) {
  const { PORTAL } = await import(pathToFileURL(path.join(root, 'src', 'config.js')).href);
  const data = vm.createContext({});
  for (const file of FILES) {
    const full = path.join(root, file);
    // data-history.js es opcional; los tres de categoría no: sin ellos la sonda no diría nada.
    if (!existsSync(full) && file === 'data-history.js') continue;
    vm.runInContext(readFileSync(full, 'utf8').replace(/^const /gm, 'var '), data);
  }
  const season = buildSeason({
    name: PORTAL.season, current: true, benjamin: data.BENJAMIN, prebenjamin: data.PREBENJAMIN,
    alevin: data.ALEVIN, history: data.HISTORY,
  });
  const otras = season.groups.filter((group) => OTRA.test(group.compKey))
    .map((group) => ({ cat: group.cat, id: group.id, phase: group.phase, compKey: group.compKey }));
  return { season: season.name, total: season.groups.length, otras };
}

async function main(argv) {
  const json = argv.includes('--json');
  const root = argv.find((arg) => !arg.startsWith('--')) || REPO;
  const { season, total, otras } = await sonda(path.resolve(root));
  if (json) {
    console.log(JSON.stringify(otras));
  } else {
    for (const group of otras) console.log(group.cat, group.id, group.phase, '→', group.compKey);
    console.log(`${season}: ${total} grupos, ${otras.length} en otra-…`);
  }
  return otras.length ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).then((code) => { process.exitCode = code; },
    (error) => { console.error(`sonda_fases: ${error.message}`); process.exitCode = 2; });
}
