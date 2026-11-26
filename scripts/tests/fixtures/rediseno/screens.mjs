// Contexto de pantalla (ctx) con las fixtures congeladas, para probar
// render(ctx) en Node. Nunca lee los data-*.js ni src/config.js vivos: la temporada del portal
// y el equipo por defecto van aquí, fijos.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { fixture } from './load.mjs';
import { datasetsFrom, withChampions, cupsRaw } from './simulate.mjs';
import { memoryStorage } from './fake-browser.mjs';
import { startContext } from '../../../../src/app.js';
import { routeHref } from '../../../../src/links.js';
import { activeTab, parentOf } from '../../../../src/router.js';
import { STORE_KEY } from '../../../../src/store.js';
import { LAZY, alevinData, lazyData } from '../../../../src/state.js';
import { LAZY_CATS } from '../../../../src/model.js';

// Las categorías perezosas ya pedidas y vacías (data-<cat>.js sin grupos y un 404 en cada
// data-season-<S>-<cat>.js de `past`): el registro de app.js para las pruebas que no esperan a ninguna.
export function lazyEmpty(past = []) {
  return {
    lazy: Object.fromEntries(LAZY_CATS.map((cat) => [cat, lazyData(cat, {})])),
    seasonLazy: Object.fromEntries(LAZY_CATS.map((cat) => [cat, Object.fromEntries(past.map((name) => [name, {}]))])),
  };
}

/* Una perezosa de la temporada del portal ya pedida, con grupos inventados: lazyData(cat, …) con sus grupos
 * crudos (la forma de BENJAMIN: el primero de `teams`, líder) y su HISTORY (una jornada: el primero contra el
 * segundo, el tercero contra el cuarto…, ya jugada). groups: [{ id, phase, island?, fullName?, name?, teams }].
 * Para infantil, cadete y juvenil, que las fixtures congeladas no traen. */
export function lazyWith(cat, groups, { day = '2025-10-11' } = {}) {
  const names = LAZY[cat].consts;
  const raws = groups.map(({ id, phase, island = 'grancanaria', fullName = '', name = 'Grupo 1', teams }) => ({
    id, name, fullName, phase, island, url: null, jornada: 'Jornada 1', standingsKind: 'source', matches: [],
    standings: teams.map((team, i) => [i + 1, team, i % 2 ? 0 : 3, 1, i % 2 ? 0 : 1, 0, i % 2 ? 1 : 0, i % 2 ? 0 : 2, i % 2 ? 2 : 0, i % 2 ? -2 : 2]),
  }));
  const history = Object.fromEntries(groups.map(({ id, teams }) => [id, {
    'Jornada 1': teams.filter((_, i) => i % 2 === 0).map((home, k) => [day, home, teams[2 * k + 1], 2, 0, null, '10:00', null])
      .filter((row) => row[2]),
  }]));
  return lazyData(cat, { [names.groups]: raws, [names.stats]: { groups: raws.length, teams: 0 }, [names.history]: history });
}

export const PORTAL_SEASON = '2025-2026';
export const MY_TEAM = { name: 'Las Mesas Hu.', season: PORTAL_SEASON, cat: 'prebenjamin', groupId: 'PG2' };
// El equipo por defecto con la forma de PORTAL.defaultTeam (config.js), sin temporada.
export const DEFAULT_TEAM = { cat: 'prebenjamin', groupId: 'PG2', name: 'Las Mesas Hu.' };

// Registro de datos con la forma de readGlobals() más lo perezoso: el de
// datasetsFrom con SEASONS, data-health y lo que se pida:
// - current: el crudo de la temporada actual (la fixture, currentAt(...) o withChampions(...));
// - golBenj y golPrebenj: los goleadores; los congelados, con ...goleadores() de simulate.mjs;
// - seasonRaw: las temporadas pasadas ya cargadas, { [name]: archive(name) o pastSeasonRaw() };
// - champions: añade a current la Copa de Campeones 2025-26 (withChampions);
// - cupsExtra: los torneos con la Copa Plata de benjamín y la Copa Oro de prebenjamín (cupsRaw);
// - lineups: las actas ya cargadas, { [season]: lineupsFor(season) };
// - seasons: SEASONS. Por defecto, 2025-26 (actual), 2024-25 y las de seasonRaw, de la más reciente
//   a la más antigua: se anuncian las temporadas que se sirven;
// - alevin y seasonAlevin: el alevín ya pedido (contrato común de alevín), en el registro de las
//   perezosas (lazy.alevin y seasonLazy.alevin). Por defecto, el de la temporada actual y el de cada
//   temporada anunciada, vacíos (data-alevin.js sin grupos y un 404 en cada data-season-<S>-alevin.js),
//   como infantil, cadete y juvenil: las pruebas que no son de una perezosa no la esperan. Las de alevín
//   ponen lazy.alevin a undefined (sin pedir, lo de app.js) o pasan los datos de alevinData;
// - lazy y seasonLazy: otras perezosas ya pedidas ({ infantil: lazyData('infantil', …) }), sobre las vacías.
export function datasetsFor({
  current = fixture('current-2025-2026'), golBenj = [], golPrebenj = [], seasonRaw = {},
  champions = false, cupsExtra = false, lineups = {}, seasons = null, alevin = alevinData({}), seasonAlevin = null,
  lazy = {}, seasonLazy = {},
} = {}) {
  const cups = cupsRaw({ extra: cupsExtra });
  const names = [...new Set([PORTAL_SEASON, '2024-2025', ...Object.keys(seasonRaw)])].sort().reverse();
  const announced = seasons || names.map(name => ({ name, current: name === PORTAL_SEASON }));
  return datasetsFrom(champions ? withChampions(current) : current, {
    golBenj, golPrebenj, seasonRaw, lineups, health: fixture('health'),
    cupBenjamin: cups.benjamin, cupPrebenjamin: cups.prebenjamin,
    seasons: announced,
    ...mergeLazy(lazyEmpty(announced.filter(s => !s.current).map(s => s.name)),
      { lazy: { alevin, ...lazy }, seasonLazy: { ...(seasonAlevin ? { alevin: seasonAlevin } : {}), ...seasonLazy } }),
  });
}

// El registro de las perezosas `base` con lo de `extra` encima, categoría a categoría.
function mergeLazy(base, extra) {
  return { lazy: { ...base.lazy, ...extra.lazy }, seasonLazy: { ...base.seasonLazy, ...extra.seasonLazy } };
}

// La temporada 2024-25 congelada con la forma de SEASON_2024_2025 (que trae `name`).
export function pastSeasonRaw() {
  const raw = fixture('historical-2024-2025');
  return { name: raw.season, current: false, benjamin: raw.benjamin, prebenjamin: raw.prebenjamin };
}

// El ctx de una pantalla, el mismo que le da la app:
// startContext de app.js, que comparte contextFor con start (el modelo, mi equipo resuelto con
// resolveMyTeam sobre la temporada del portal, el hoy inyectado, health y legacyDate), desde un
// almacén con `myTeam` guardado (null: el almacén vacío, que da el equipo por defecto), más lo que
// añade el router:
// - route y params (ya resueltos: lo hace el router);
// - lastPrimary, un destino de la barra: el de la pantalla si es uno principal y, si no, el
//   último visitado (por defecto, el de startContext: Mi equipo); nunca 'partido';
// - backHref, el «‹» del router: parentOf con el modelo del ctx.
// portalSeason cambia la temporada del portal (2026/27 simulada) y legacyDate, el literal oculto
// «Última actualización» de index.html. recent son los vistos hace poco guardados con `myTeam`
// ([{ s, g, t }], que llegan a ctx.recent); con myTeam null, el almacén vacío.
export function ctxFor(screen, params, {
  today = '2026-09-24', datasets = datasetsFor(), myTeam = MY_TEAM, recent = [], portalSeason = PORTAL_SEASON,
  legacyDate = null, lastPrimary = null,
} = {}) {
  const storage = memoryStorage(new Map(myTeam ? [[STORE_KEY, JSON.stringify({ myTeam, recent })]] : []));
  const base = startContext({ storage, portal: { season: portalSeason, defaultTeam: DEFAULT_TEAM }, datasets, today });
  const route = { screen, params };
  const tab = activeTab(route, null, false);
  const parent = parentOf(route, base.model);
  return {
    ...base, legacyDate, route, params,
    lastPrimary: lastPrimary || (tab.current === 'page' ? tab.active : base.lastPrimary),
    backHref: parent ? routeHref(parent.screen, parent.params) : null,
  };
}

// Reglas de acta.css como { media, selector, body } (un nivel de @media, como en
// test_rediseno_css.mjs), y las clases que define.
export function cssRules() {
  const src = readFileSync(fileURLToPath(new URL('../../../../acta.css', import.meta.url)), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '');
  const rules = [];
  const walk = (text, media) => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf('{', i);
      if (open < 0) break;
      const prelude = text.slice(i, open).trim();
      let depth = 1, j = open + 1;
      for (; j < text.length && depth; j++) depth += text[j] === '{' ? 1 : text[j] === '}' ? -1 : 0;
      const body = text.slice(open + 1, j - 1);
      if (prelude.startsWith('@media')) walk(body, prelude);
      else rules.push({ media, selector: prelude, body });
      i = j;
    }
  };
  walk(src, null);
  rules.classes = new Set([...src.matchAll(/\.([a-zA-Z][\w-]*)/g)].map(m => m[1]));
  return rules;
}
