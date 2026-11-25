// Carga de datos y funciones de dominio. No guarda estado de interfaz, no pinta HTML y no toca el DOM
// al importarse: la URL es la fuente de verdad, myteam.js y store.js guardan mi equipo y ui.js pinta
// los escudos.
import { isPlayerKey } from './links.js';

/* Goleadores de un grupo, de GOL_BENJ o GOL_PREBENJ ([{ id, g, s: [[jugador, equipo, goles,
 * partidos]] }], lo que da model.scorers; cada entrada lleva el código del grupo en `id`):
 * [{ name, team, goals, games }], de más a menos goles y, a igualdad, con menos partidos. null si
 * la fuente no trae el grupo. Lo usan Tabla y, con teamScorers, Mi equipo: un solo orden para las
 * dos. */
export function groupScorers(gol, groupId) {
  const entry = (Array.isArray(gol) ? gol : []).find(item => item && item.id === groupId);
  if (!entry) return null;
  return (Array.isArray(entry.s) ? entry.s : [])
    .map(([name, team, goals, games]) => ({ name, team, goals, games }))
    .sort((a, b) => b.goals - a.goals || a.games - b.games);
}

/* Goleadores de un equipo en su grupo: los de groupScorers con su nombre exacto (los de los
 * goleadores son los de la clasificación), [{ name, goals, games }]. `team` es { cat, groupId,
 * name }, como myTeam. */
export function teamScorers(gol, team) {
  if (!team) return [];
  return (groupScorers(gol, team.groupId) || []).filter(s => s.team === team.name)
    .map(({ name, goals, games }) => ({ name, goals, games }));
}

/* Goleadores de una categoría entera, de GOL_BENJ o GOL_PREBENJ (lo
 * que da model.scorers): una fila por jugador y equipo, con los nombres exactos, que suma los goles y
 * los partidos de todos sus grupos, que son sus fases (la Primera y la Segunda Fase de benjamín). Dos
 * homónimos de equipos distintos van por separado. [{ name, team, goals, games, groupId, groups }],
 * de más a menos goles y, a igualdad, con menos partidos (y en el orden de la fuente): el orden de
 * groupScorers. groups: sus grupos, en el orden de la fuente; groupId, el de su ficha de equipo, el
 * grupo en el que jugó más partidos (a igualdad, el primero). La usan Goleadores y Récords. */
export function categoryScorers(gol) {
  const byPlayer = new Map();
  for (const entry of Array.isArray(gol) ? gol : []) {
    if (!entry || !Array.isArray(entry.s)) continue;
    for (const [name, team, goals, games] of entry.s) {
      const key = JSON.stringify([name, team]);
      const row = byPlayer.get(key) || { name, team, goals: 0, games: 0, groupId: entry.id, groups: [], most: -1 };
      row.goals += goals;
      row.games += games;
      row.groups.push(entry.id);
      if (games > row.most) { row.most = games; row.groupId = entry.id; }
      byPlayer.set(key, row);
    }
  }
  return [...byPlayer.values()].map(({ most, ...row }) => row)
    .sort((a, b) => b.goals - a.goals || a.games - b.games);
}

/* El puesto de cada fila de una lista de goleadores ya ordenada (la de categoryScorers o la de
 * groupScorers): con los mismos goles y partidos, el mismo puesto (1, 2, 2, 4). Una sola regla para
 * Goleadores y para los 30 primeros de Récords. */
export function rankScorers(rows) {
  const out = [];
  rows.forEach((row, i) => {
    const prev = out[i - 1];
    out.push({ ...row, pos: prev && prev.goals === row.goals && prev.games === row.games ? prev.pos : i + 1 });
  });
  return out;
}

/* ====== JORNADA KEY HELPERS ======
 * Jornada labels are mixed across seasons: 'Jornada N' (current HISTORY),
 * 'N' (wayback per-season files) and copa-round keys like
 * '08-06-2025 ( Ronda 1 Ida )' (Copa 2024-25). Only the first two are
 * truly numeric — copa keys contain digits (the DATE) that must NOT be
 * mistaken for a jornada number. */
export function jornadaNumber(key) {
  const m = String(key).trim().match(/^(?:jornada|jor\.?|j)?\s*(\d+)$/i);
  return m ? parseInt(m[1], 10) : null;
}

/* Sort jornada keys: numeric ones ascending, non-numeric ones after them
 * preserving insertion order (data files emit rounds in play order). */
export function sortJornadaKeys(keys) {
  return keys
    .map((k, i) => ({ k, n: jornadaNumber(k), i }))
    .sort((a, b) => {
      const an = a.n === null ? Number.MAX_SAFE_INTEGER : a.n;
      const bn = b.n === null ? Number.MAX_SAFE_INTEGER : b.n;
      return (an - bn) || (a.i - b.i);
    })
    .map(x => x.k);
}

/* A cup / knockout group (vs a regular league group). By code prefix
 * (PCC or BC) or phase ("Copa"/"Campeón", y las finales, semifinales y torneos
 * de cierre o clausura de la federación, que se juegan aparte de su liga, y
 * las «Eliminatorias» de benjamín, prebenjamín y alevín, que reparten los
 * puestos de la fase siguiente). */
export function isCupGroup(g) {
  const id = ((g && g.id) || '').toUpperCase();
  if (id.startsWith('PCC') || id.startsWith('BC')) return true;
  if (id.startsWith('MCP') || id.startsWith('MCB')) return true;
  const phase = ((g && g.phase) || '').toLowerCase();
  // Y las fases de ascenso de infantil, cadete y juvenil («Fase de Ascenso a Interinsular»; las
  // «Eliminatorias de Ascenso a …» ya empiezan por «eliminatorias»): copas, como _is_league_group de
  // scripts/generate_js.py (decisión 3 de la parte E).
  return phase.includes('copa') || phase.includes('campeon') || phase.includes('maspalomas')
    || /^(?:semi)?final\b|^torneo\b|^clausura\b|^eliminatorias\b|^fase de ascenso\b/.test(phase);
}

/* Friendly label for a knockout round. Prefers the explicit round name in the
 * key ("( Semifinales )") — authoritative and order-independent — then
 * "Ronda N", then position relative to the final (last = Final). Check
 * semifinal BEFORE final ("Semifinales" contains "final"). */
export function knockoutRoundLabel(raw, idx, total) {
  const s = String(raw);
  // 1) explicit round name in the key (2025-26 cups: "( Semifinales )").
  //    Check semifinal BEFORE final ("Semifinales" contains "final").
  //    "Previa": ronda incompleta que abre un cuadro cuyo número de equipos no
  //    es potencia de 2 (Maspalomas Cup: 34 equipos → 2 eliminatorias → 32).
  if (/previa/i.test(s)) return 'Previa';
  if (/dieciseis/i.test(s)) return 'Dieciseisavos';
  if (/octavos/i.test(s)) return 'Octavos';
  if (/cuartos/i.test(s)) return 'Cuartos';
  if (/semifinal/i.test(s)) return 'Semifinales';
  if (/\bfinal\b/i.test(s)) return 'Final';
  // 2) position relative to the final (2024-25 "Ronda N" cups, ≤4 rounds →
  //    friendlier Cuartos/Semis/Final than "Ronda N").
  const fromEnd = total - 1 - idx;
  if (fromEnd === 0) return 'Final';
  if (fromEnd === 1) return 'Semifinales';
  if (fromEnd === 2) return 'Cuartos';
  if (fromEnd === 3) return 'Octavos';
  // 3) deeper brackets: "Ronda N" / stripped key.
  const r = s.match(/Ronda\s+(\d+)/i);
  if (r) return 'Ronda ' + r[1];
  return s.replace(/\d{2}-\d{2}-\d{4}\s*/, '').trim();
}

/** A cup whose only "round" is a multi-match group stage (round-robin) — e.g.
 * the 2023-24 Copa de Campeones (one "Ronda 1" with 7 matches per group). It
 * must render as a classification TABLE, not a one-column bracket (which
 * knockoutRoundLabel would mislabel "Final" by position). A lone final (1 round,
 * 1 match) is NOT a round-robin → stays a bracket. */
export function isRoundRobinCup(jornadas) {
  if (!jornadas) return false;
  const keys = Object.keys(jornadas);
  if (!keys.length) return false;
  // Un cuadro es un EMBUDO: cada ronda tiene menos partidos que la anterior y
  // termina en una sola final. Si la última ronda no es menor que la primera,
  // esto es una liguilla y va como TABLA — da igual que se llame "Copa".
  // Cubre la Copa de Campeones 2023-24 (1 ronda de 7) y las copas insulares
  // de Lanzarote y Fuerteventura (jornadas numeradas de tamaño constante).
  // Comparar primera contra última, y no "última === 1", evita clasificar mal
  // un cuadro a medio jugar cuya última ronda disputada son las semifinales.
  const first = (jornadas[keys[0]] || []).length;
  const last = (jornadas[keys[keys.length - 1]] || []).length;
  // Ronda única: liguilla si tiene varios partidos; una final suelta es cuadro.
  if (keys.length === 1) return first > 2;
  return last >= first;
}

/* Shield-matching normalizer. NOTE: mirrored by scripts/check_missing_shields.py
 * (normalize()) and by the reference copy in scripts/tests \u2014 keep in sync.
 * Pipeline: NFD accent-strip \u2192 strip quotes (straight + curly) / dots /
 * commas \u2192 strip club tokens \u2192 lowercase \u2192 collapse whitespace. */
export function normalizeTeamName(s) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/['".,\u2018\u2019\u201c\u201d]/g, '').replace(/\b(CF|UD|CD|AD|SD|AFC|SC|CP|CE|CEF|SSD|ATLETICO|ATL)\b/gi, '').toLowerCase().trim().replace(/\s+/g, ' ');
}

// Fichero de escudo de un equipo: la clave exacta de `shields`
// o, si no está, la primera clave con el mismo nombre normalizado; null si no hay. Nunca por
// subcadena: «UD Las Mesas Huracán» se llevaría el escudo de AD Huracán. Es la única búsqueda de
// escudos de la app: la usan crest (ui.js) y buildClubIndex (myteam.js), que no deben divergir.
const _shieldIndex = new WeakMap();
export function shieldFile(name, shields) {
  if (!name || !shields) return null;
  if (Object.hasOwn(shields, name)) return shields[name];
  let index = _shieldIndex.get(shields);
  if (!index) {
    index = new Map();
    for (const [key, file] of Object.entries(shields)) {
      const norm = normalizeTeamName(key);
      if (norm && !index.has(norm)) index.set(norm, file);
    }
    _shieldIndex.set(shields, index);
  }
  return index.get(normalizeTeamName(String(name))) || null;
}

// Globales inmediatos de los data-*.js: identificador desnudo con typeof, nunca a
// través del objeto global, y null si el fichero no ha llegado. Es la puerta de los datos de la
// app: el resto de módulos los recibe por parámetro (datasets).
export function readGlobals() {
  return {
    benjamin: typeof BENJAMIN !== 'undefined' ? BENJAMIN : null,
    prebenjamin: typeof PREBENJAMIN !== 'undefined' ? PREBENJAMIN : null,
    history: typeof HISTORY !== 'undefined' ? HISTORY : null,
    golBenj: typeof GOL_BENJ !== 'undefined' ? GOL_BENJ : null,
    golPrebenj: typeof GOL_PREBENJ !== 'undefined' ? GOL_PREBENJ : null,
    shields: typeof SHIELDS !== 'undefined' ? SHIELDS : null,
    campos: typeof CAMPOS !== 'undefined' ? CAMPOS : null,
    // La ficha de cada equipo de la temporada (equipación y campo) y el estado de los partidos que da
    // la app de futbolaspalmas (aplazado, suspendido…), los dos en data-history.js.
    equipos: typeof EQUIPOS !== 'undefined' ? EQUIPOS : null,
    estados: typeof ESTADOS !== 'undefined' ? ESTADOS : null,
    // Lo que guarda la base (temporadas, partidos, actas…), para «Fuentes» (data-history.js).
    cobertura: typeof COBERTURA !== 'undefined' ? COBERTURA : null,
    seasons: typeof SEASONS !== 'undefined' ? SEASONS : null,
    cupBenjamin: typeof MASPALOMAS_CUP_BENJAMIN !== 'undefined' ? MASPALOMAS_CUP_BENJAMIN : null,
    cupPrebenjamin: typeof MASPALOMAS_CUP_PREBENJAMIN !== 'undefined' ? MASPALOMAS_CUP_PREBENJAMIN : null,
  };
}

// Versión de los datos: la ?v= del <script> de data-seasons.js, que index.html
// siempre carga; '' sin documento o sin ese <script>. La llevan todas las peticiones perezosas.
export function dataVersion() {
  if (typeof document === 'undefined') return '';
  const src = document.querySelector('script[src*="data-seasons.js"]')?.getAttribute('src') || '';
  return (src.match(/[?&]v=([^&#]+)/) || [])[1] || '';
}

// La query de las peticiones perezosas: '?v=<versión>' o ''.
function dataQuery() {
  const version = dataVersion();
  return version ? `?v=${version}` : '';
}

// Nada espera para siempre: si una petición perezosa no termina, cuerpo incluido, en
// LAZY_TIMEOUT_MS, se aborta y la carga falla como con un error de red. Lo opcional pinta su
// caja de error en el bloque; lo necesario, en la pantalla, siempre con «Reintentar».
export const LAZY_TIMEOUT_MS = 15000;

// Una petición perezosa: `file` con la ?v= de los datos y el tiempo límite. Devuelve lo que los
// cargadores usan de una respuesta (ok, status y text()), con el cuerpo ya leído dentro del plazo, y
// fromCache si la sirvió el service worker de su copia porque la red no llegó (x-fb2-origen: cache).
async function fetchData(file) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), LAZY_TIMEOUT_MS);
  try {
    const r = await fetch(`./${file}${dataQuery()}`, { signal: controller.signal });
    const body = r.ok ? await r.text() : '';
    const fromCache = r.headers?.get?.('x-fb2-origen') === 'cache';
    return { ok: r.ok, status: r.status, fromCache, text: async () => body };
  } finally {
    clearTimeout(timer);
  }
}

/* Lazy loader for the full goal-timeline data. data-matchdetail.js is no
 * longer an eager <script> (it is ~359 KB); fetch+parse it on demand the
 * first time the match screen needs it. Single-flight + module cache.
 * ?v= is dataVersion() (the one of data-seasons.js), like every lazy loader.
 * On failure the single-flight promise is cleared (next call retries) and
 * a null sentinel is returned — callers already null-check. */
let _matchDetail = null;
let _matchDetailPromise = null;
export async function ensureMatchDetail() {
  if (_matchDetail) return _matchDetail;
  if (_matchDetailPromise) return _matchDetailPromise;
  _matchDetailPromise = (async () => {
    try {
      const r = await fetchData('data-matchdetail.js');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const txt = await r.text();
      const m = txt.match(/const MATCH_DETAIL=(\{[\s\S]*\});/);
      if (!m) throw new Error('MATCH_DETAIL not found in data-matchdetail.js');
      _matchDetail = JSON.parse(m[1]);
      return _matchDetail;
    } catch (e) {
      console.error('[state] ensureMatchDetail failed:', e);
      _matchDetailPromise = null; // clear single-flight → retry allowed
      return null;                // error sentinel (never cached)
    }
  })();
  return _matchDetailPromise;
}

/* La cronología de goles de infantil, cadete y juvenil: data-matchdetail-<cat>.js, const MATCH_DETAIL_<S>
 * (generate_js.generate_matchdetail_lazy_js, con la forma de MATCH_DETAIL), aparte para que sus actas de
 * fútbol 11 no hagan crecer data-matchdetail.js para todos. Se pide al abrir un partido de esa categoría
 * (partidoNeeds). Como ensureMatchDetail: un vuelo por categoría, el texto leído con readConsts (nunca el
 * global) y null si falla, sin memorizarlo, para reintentar; el partido se pinta sin la cronología. */
const MATCH_DETAIL_CATS = { infantil: 'INF', cadete: 'CAD', juvenil: 'JUV' };
const _matchDetailLazy = {};
const _matchDetailLazyPromise = {};
export function ensureMatchDetailLazy(cat) {
  if (!Object.hasOwn(MATCH_DETAIL_CATS, cat)) return Promise.resolve(null);
  return lazyConst(_matchDetailLazy, _matchDetailLazyPromise, cat, {
    file: `data-matchdetail-${cat}.js`, name: `MATCH_DETAIL_${MATCH_DETAIL_CATS[cat]}`,
    // Siempre se publica (vacío si no hay nada): un 404 es la web de antes de la categoría, sin cronología.
    missing: () => ({}), valid: (value) => isObject(value),
  });
}
// Las categorías con data-matchdetail-<cat>.js propio (las demás, en data-matchdetail.js).
export const hasOwnMatchDetail = (cat) => Object.hasOwn(MATCH_DETAIL_CATS, cat);

// Season data cache — loaded lazily per historical season.
const _seasonCache = {};
const _seasonPromise = {};

// Async — call this before reading a historical season with createModel (datasets.seasonRaw).
// Single-flight per season; on failure the in-flight promise is cleared so
// a later call (e.g. the "Reintentar" button) refetches. Returns the season
// object, or null as error sentinel (the failure goes to the console).
export async function ensureSeasonData(seasonName) {
  if (!seasonName) return null;
  if (_seasonCache[seasonName]) return _seasonCache[seasonName];
  if (_seasonPromise[seasonName]) return _seasonPromise[seasonName];
  _seasonPromise[seasonName] = (async () => {
    try {
      const r = await fetchData(`data-season-${seasonName}.js`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const text = await r.text();
      // Extract JSON: "const SEASON_2024_2025=..." → parse the object
      const m = text.match(/const SEASON_\w+=(.+);/);
      if (!m) throw new Error('No SEASON_ var found');
      const seasonObj = JSON.parse(m[1]);
      _seasonCache[seasonName] = seasonObj;
      return seasonObj;
    } catch (e) {
      console.error('[state] ensureSeasonData failed:', seasonName, e);
      return null; // error sentinel
    } finally {
      delete _seasonPromise[seasonName]; // allow retry after failure
    }
  })();
  return _seasonPromise[seasonName];
}

/* ──────────────────────────────────────────────────────────────────────
 * Las actas de un grupo: carga perezosa de data-lineups-<S>-<grupo>.js (una
 * temporada entera con todas sus actas pesa ~10 MB; la ficha de un equipo o un
 * partido solo necesita las de su grupo). La plantilla sale de LINEUPS, no de
 * data-players-<S>.js. Como ensureMatchDetail: el texto del fichero se lee con
 * una expresión regular y JSON.parse, nunca por el objeto global, porque un
 * `const` de primer nivel no pasa a ser propiedad del objeto global.
 * null si falta el fichero o no se puede leer: la pantalla enseña el vacío.
 * ────────────────────────────────────────────────────────────────────── */

/* Normalizador de las claves de TEAMS_<S>, copia exacta de normalize_for_teams_mapping de
 * scripts/generate_js.py (si cambia uno, el otro también): minúsculas, sin tildes (NFKD), sin comillas
 * (rectas y curvas) ni puntuación, sin las siglas de club (la misma lista que
 * acta_reconciler._CLUB_SUFFIX) y con los espacios juntados. La letra de filial del final
 * (A/B/C/D) SE QUEDA: las claves de TEAMS_<S> la llevan, y 'UD Atalaya' y 'UD Atalaya B' son equipos
 * distintos. normalizeTeamName, más arriba, es la de los escudos y no hace lo mismo: no se reutiliza. */
const _SP1_CLUB_SUFFIX = /\b(c\s*f|c\s*d|c\s*d\s*f|u\s*d|a\s*d|s\s*d|s\s*c|s\s*a\s*d|e\s*f|c\s*p|c\s*e|club|deportivo|atletico|atletico\s+c\s*f|deportiva|sociedad|union|f\s*c)\b/g;
export function normalizeForTeamsMapping(s) {
  if (!s) return "";
  s = String(s).normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  s = s.toLowerCase();
  s = s.replace(/["'\u2018\u2019\u201C\u201D]/g, " ");
  s = s.replace(/[.,;:]/g, " ");
  s = s.replace(_SP1_CLUB_SUFFIX, " ");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

const _lineups = {};
const _lineupsPromise = {};

function _seasonSuffix(season) { return season.replace('-', '_'); }

// La clave de las actas de un grupo en datasets.lineups (y en la caché del cargador).
export function lineupsKey(season, group) { return `${season}/${group}`; }

/* On failure the loader returns a null sentinel WITHOUT caching it and
 * clears its single-flight promise, so a later call retries the fetch
 * (a transient network error no longer blanks the feature for the whole
 * session). Callers already null-check (UI empty-state). */
export async function ensureLineups(season, group) {
  const key = lineupsKey(season, group);
  if (_lineups[key] !== undefined) return _lineups[key];
  if (_lineupsPromise[key]) return _lineupsPromise[key];
  _lineupsPromise[key] = (async () => {
    const name = 'LINEUPS_' + _seasonSuffix(season) + '_' + group;
    try {
      const r = await fetchData(`data-lineups-${season}-${group}.js`);
      // generate_js.py solo escribe data-lineups-<S>-<grupo>.js si el grupo tiene
      // alguna acta: sin fichero (404) no hay actas, y eso no es un error de
      // carga (la mayoría de los grupos de futbolaspalmas, o uno recién empezado).
      if (r.status === 404) { _lineups[key] = {}; return _lineups[key]; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const txt = await r.text();
      const m = txt.match(new RegExp('const ' + name + '\\s*=\\s*(\\{[\\s\\S]*\\});'));
      if (!m) throw new Error(name + ' not parseable');
      _lineups[key] = JSON.parse(m[1]);
      return _lineups[key];
    } catch (e) {
      console.warn('[state] ensureLineups failed:', e.message);
      _lineupsPromise[key] = null; // clear single-flight → retry allowed
      return null;                 // error sentinel (never cached)
    }
  })();
  return _lineupsPromise[key];
}

/* Las fichas de jugador: data-jugadores-<k>.js, el trozo de su clave (generate_js.jugadores_files),
 * el mismo que identidad.trozo: numérica, su valor módulo JUGADORES_SHARDS; «n…», las 9 cifras en base
 * 36 módulo JUGADORES_SHARDS (caben enteras en un número: 36^9 < 2^53). null si no es una clave. Como
 * ensureLineups: un vuelo por trozo, null si falla (sin guardarlo, para reintentar) y el texto
 * parseado, nunca el global. */
export const JUGADORES_SHARDS = 64;
export function jugadoresShard(id) {
  const key = String(id ?? '');
  if (!isPlayerKey(key)) return null;
  return (key[0] === 'n' ? parseInt(key.slice(1), 36) : Number(key)) % JUGADORES_SHARDS;
}
const _jugadores = {};
const _jugadoresPromise = {};

export async function ensureJugadores(shard) {
  if (_jugadores[shard] !== undefined) return _jugadores[shard];
  if (_jugadoresPromise[shard]) return _jugadoresPromise[shard];
  _jugadoresPromise[shard] = (async () => {
    const name = 'JUGADORES_' + shard;
    try {
      const r = await fetchData(`data-jugadores-${shard}.js`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const txt = await r.text();
      const m = txt.match(new RegExp('const ' + name + '\\s*=\\s*(\\{[\\s\\S]*\\});'));
      if (!m) throw new Error(name + ' not parseable');
      _jugadores[shard] = JSON.parse(m[1]);
      return _jugadores[shard];
    } catch (e) {
      console.warn('[state] ensureJugadores failed:', e.message);
      _jugadoresPromise[shard] = null;
      return null;
    }
  })();
  return _jugadoresPromise[shard];
}

/* Los ficheros perezosos de una sola constante (el índice de búsqueda de jugadores y el ranking por año
 * de nacimiento), con el patrón de ensureJugadores: un vuelo por clave, el texto leído con readConsts
 * (nunca el global), un 404 que da `missing()` y se memoriza (el fichero no existe porque no hay nada que
 * publicar) y un fallo, o un texto sin la constante (sin conexión y sin su copia, el SW responde con
 * index.html), null sin memorizarse, para reintentar. valid(valor) dice si la constante tiene su forma. */
function lazyConst(cache, flights, key, { file, name, missing, valid }) {
  if (cache[key] !== undefined) return Promise.resolve(cache[key]);
  if (flights[key]) return flights[key];
  flights[key] = (async () => {
    try {
      const r = await fetchData(file);
      if (r.status === 404) { cache[key] = missing(); return cache[key]; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const value = readConsts(await r.text())[name];
      if (!valid(value)) throw new Error(name + ' not parseable');
      cache[key] = value;
      return value;
    } catch (e) {
      console.warn(`[state] ${file} failed:`, e.message);
      return null;
    } finally {
      delete flights[key];
    }
  })();
  return flights[key];
}

/* El índice de búsqueda de jugadores de un prefijo (dos letras de la a a la z; model.playerSearchPrefix):
 * data-buscar-<xy>.js, const BUSCAR_<XY> = [[clave, nombre, último equipo, última temporada, [años]]]
 * (generate_js.buscar_files). Solo se publican los prefijos con algún jugador: un 404 es «ningún jugador
 * con ese prefijo», [], no un fallo. Lo que no es un prefijo, [] sin pedir nada. */
const _buscar = {};
const _buscarPromise = {};
export function ensureBuscar(prefix) {
  const xy = String(prefix ?? '');
  if (!/^[a-z]{2}$/.test(xy)) return Promise.resolve([]);
  return lazyConst(_buscar, _buscarPromise, xy, {
    file: `data-buscar-${xy}.js`, name: `BUSCAR_${xy.toUpperCase()}`, missing: () => [], valid: Array.isArray,
  });
}

/* El ranking por año de nacimiento (generate_js.ranking_files): data-ranking.js, const RANKING =
 * { temporada, anios: { "<año>": [entradas en "t", entradas en "h"] } }, lo que dice qué años hay; y
 * data-ranking-<año>.js, const RANKING_<año> = { t: [...], h: [...] }, las dos listas de ese año. Como el
 * índice de búsqueda (lazyConst): un vuelo por fichero, null si falla, sin memorizarlo. Un 404 es que no
 * se ha publicado nada: un ranking sin años, o un año sin nadie. */
const _ranking = {};
const _rankingPromise = {};
const isObject = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
export function ensureRanking() {
  return lazyConst(_ranking, _rankingPromise, 'RANKING', {
    file: 'data-ranking.js', name: 'RANKING', missing: () => ({ temporada: null, anios: {} }),
    valid: (value) => isObject(value) && isObject(value.anios),
  });
}
export function ensureRankingYear(year) {
  const y = String(year ?? '');
  if (!/^\d{4}$/.test(y)) return Promise.resolve({ t: [], h: [] });
  return lazyConst(_ranking, _rankingPromise, `RANKING_${y}`, {
    file: `data-ranking-${y}.js`, name: `RANKING_${y}`, missing: () => ({ t: [], h: [] }),
    valid: (value) => isObject(value) && Array.isArray(value.t) && Array.isArray(value.h),
  });
}

/* ──────────────────────────────────────────────────────────────────────
 * Las categorías perezosas: alevín, infantil, cadete y juvenil. Nunca van en
 * la carga inicial (la portada tiene que abrir en 3 s): data-<cat>.js, la
 * temporada del portal, y data-season-<S>-<cat>.js, cada temporada pasada que
 * tenga esa categoría, se piden cuando una pantalla los necesita (needsLazy de
 * router.js). Un fichero por categoría (generate_js.LAZY): una familia que
 * sigue a un niño de infantil no baja cadete ni juvenil. Como ensureLineups:
 * un vuelo por fichero, el texto leído por expresión regular (nunca el
 * global), un 404 es «sin esa categoría» (y se memoriza) y un fallo da null
 * sin memorizarse, para reintentar.
 * ────────────────────────────────────────────────────────────────────── */

// Las constantes de nivel superior de un data-*.js, { NOMBRE: valor }: una por línea, «const
// NOMBRE=<json>;», como las escribe generate_js.py (el JSON nunca lleva un salto de línea crudo).
function readConsts(text) {
  const out = {};
  for (const chunk of String(text).split(/^const /m).slice(1)) {
    const m = chunk.match(/^([A-Z][A-Z0-9_]*)\s*=\s*([\s\S]*?);\s*$/);
    if (m) out[m[1]] = JSON.parse(m[2]);
  }
  return out;
}

const objectOr = (value, fallback) => (value && typeof value === 'object' && !Array.isArray(value) ? value : fallback);

/* El registro de las perezosas, en el orden de LAZY_CATS de model.js (state.js no importa de model.js:
 * model.js importa de aquí): su fichero de la temporada del portal, el nombre de sus constantes (las de
 * generate_js.LAZY: las de alevín, las de siempre) con el del registro de datos, y su nombre en una frase
 * para la caja de error («No se pudieron cargar los datos de alevín»). Infantil, cadete y juvenil traen
 * además sus campos (CAMPOS_<S>: los que no están en el CAMPOS de data-history.js). */
const lazyEntry = (cat, groups, suffix, word, campos) => ({
  file: `data-${cat}.js`, word,
  consts: {
    groups, stats: `${suffix}_STATS`, history: `HISTORY_${suffix}`, gol: `GOL_${suffix}`, estados: `ESTADOS_${suffix}`,
    equipos: `EQUIPOS_${suffix}`, ...(campos ? { campos: `CAMPOS_${suffix}` } : {}),
  },
});
export const LAZY = {
  alevin: lazyEntry('alevin', 'ALEVIN', 'ALEV', 'alevín', false),
  infantil: lazyEntry('infantil', 'INFANTIL', 'INF', 'infantil', true),
  cadete: lazyEntry('cadete', 'CADETE', 'CAD', 'cadete', true),
  juvenil: lazyEntry('juvenil', 'JUVENIL', 'JUV', 'juvenil', true),
};
const lazyOf = (cat) => {
  if (!Object.hasOwn(LAZY, cat)) throw new TypeError(`categoría perezosa desconocida: ${cat}`);
  return LAZY[cat];
};

// La categoría perezosa de un código de grupo por su prefijo (scripts/convenio.py: INF, CAD y JUV; los de
// alevín, AL…), o null si el código no la dice (los de benjamín y prebenjamín, o uno escrito a mano).
const LAZY_PREFIXES = [['INF', 'infantil'], ['CAD', 'cadete'], ['JUV', 'juvenil'], ['AL', 'alevin']];
export function lazyCatOfCode(id) {
  const code = String(id || '').toUpperCase();
  const hit = LAZY_PREFIXES.find(([prefix]) => code.startsWith(prefix));
  return hit ? hit[1] : null;
}

/* Las perezosas que tiene la temporada `name`, según su entrada de SEASONS (data-seasons.js, `lazy`: solo
 * sale cuando alguna no es alevín; generate_js.season_lazy_keys), en el orden de LAZY: alevín siempre (la web
 * lo pide como antes de las nuevas: un 404 es «sin alevín») y las que diga. Lo que la web pide cuando no sabe
 * qué categoría busca (Explorar y Ligas sin `c`, un grupo cuyo código no la dice, la Trayectoria, las
 * temporadas anteriores de un partido): así no pide a ciegas las cuatro de cada temporada (decenas de 404), y
 * con la base de hoy pide lo mismo que antes. Lo que la ruta nombra (`c=cadete`, un grupo CAD…) se pide igual. */
export function lazyCatsOf(seasons, name) {
  const entry = (Array.isArray(seasons) ? seasons : []).find((s) => s && s.name === name);
  const declared = entry && Array.isArray(entry.lazy) ? entry.lazy : [];
  return Object.keys(LAZY).filter((cat) => cat === 'alevin' || declared.includes(cat));
}

/* Una categoría perezosa de la temporada del portal con los nombres del registro de datos
 * (datasets.lazy[cat]) a partir de las constantes de su data-<cat>.js (`consts`, por defecto las de
 * LAZY[cat]): { groups, stats, history, gol, estados, equipos } y, en infantil, cadete y juvenil, campos.
 * Sin ellas (un 404, o el fichero vacío de una temporada sin esa categoría), todo vacío. */
export function lazyData(cat, consts = {}, names = lazyOf(cat).consts) {
  return {
    groups: Array.isArray(consts[names.groups]) ? consts[names.groups] : [],
    stats: objectOr(consts[names.stats], null),
    history: objectOr(consts[names.history], {}),
    gol: Array.isArray(consts[names.gol]) ? consts[names.gol] : [],
    estados: objectOr(consts[names.estados], {}),
    equipos: objectOr(consts[names.equipos], {}),
    ...(names.campos ? { campos: objectOr(consts[names.campos], {}) } : {}),
  };
}

/* El alevín de la temporada del portal (lazyData de alevín): { groups: ALEVIN, stats: ALEV_STATS,
 * history: HISTORY_ALEV, gol: GOL_ALEV, estados: ESTADOS_ALEV, equipos: EQUIPOS_ALEV }. */
export function alevinData(consts = {}) {
  return lazyData('alevin', consts);
}

const _lazy = {};
const _lazyPromise = {};
export async function ensureLazy(cat) {
  const entry = lazyOf(cat);
  if (_lazy[cat]) return _lazy[cat];
  if (_lazyPromise[cat]) return _lazyPromise[cat];
  _lazyPromise[cat] = (async () => {
    try {
      const r = await fetchData(entry.file);
      // Sin fichero (la web de antes de esa categoría), sin ella: nunca un error de carga.
      if (r.status === 404) { _lazy[cat] = lazyData(cat, {}); return _lazy[cat]; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      // Sin conexión y sin su copia, el SW responde con index.html: sin la constante de los grupos, es un fallo.
      const consts = readConsts(await r.text());
      if (!Array.isArray(consts[entry.consts.groups])) throw new Error(entry.consts.groups + ' not parseable');
      _lazy[cat] = lazyData(cat, consts);
      return _lazy[cat];
    } catch (e) {
      console.warn(`[state] ${entry.file} failed:`, e.message);
      return null;                 // error sentinel (never cached)
    } finally {
      delete _lazyPromise[cat];    // allow retry after failure
    }
  })();
  return _lazyPromise[cat];
}

const _seasonLazy = {};
const _seasonLazyPromise = {};
export async function ensureSeasonLazy(cat, season) {
  const entry = lazyOf(cat);
  if (!season) return null;
  const key = `${cat}|${season}`;
  if (_seasonLazy[key] !== undefined) return _seasonLazy[key];
  if (_seasonLazyPromise[key]) return _seasonLazyPromise[key];
  _seasonLazyPromise[key] = (async () => {
    const name = 'SEASON_' + _seasonSuffix(season) + '_' + entry.consts.groups;
    const file = `data-season-${season}-${cat}.js`;
    try {
      const r = await fetchData(file);
      // Solo existe si la temporada tuvo esa categoría: un 404 es esa temporada sin ella.
      if (r.status === 404) { _seasonLazy[key] = {}; return _seasonLazy[key]; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const value = readConsts(await r.text())[name];
      if (!value || typeof value !== 'object') throw new Error(name + ' not parseable');
      _seasonLazy[key] = value;
      return value;
    } catch (e) {
      console.warn(`[state] ${file} failed:`, e.message);
      return null;
    } finally {
      delete _seasonLazyPromise[key];
    }
  })();
  return _seasonLazyPromise[key];
}

// Las de alevín de antes, que siguen usando pruebas y pantallas.
export const ensureAlevin = () => ensureLazy('alevin');
export const ensureSeasonAlevin = (season) => ensureSeasonLazy('alevin', season);

const seasonText = (name) => String(name).replace(/^(\d{4})-\d{2}(\d{2})$/, '$1/$2');

/* La carga de la categoría perezosa `cat` de la temporada `name` que pide el router (loadLazy de
 * startRouter), como seasonNeeds: [] si ya se pidió (datasets.lazy[cat] en la del portal,
 * datasets.seasonLazy[cat][name] en una pasada); si no, una promesa que la guarda allí, o que rechaza con
 * Error('<categoría>…') para la caja «No se pudieron cargar los datos de <categoría>» (o para el aviso de
 * Explorar y Ligas). `loaders`: { ensure(cat), ensureSeason(cat, season) } (las pruebas pasan otros). */
export function lazyNeeds(cat, name, datasets, portalSeason, { ensure = ensureLazy, ensureSeason = ensureSeasonLazy } = {}) {
  const { word } = lazyOf(cat);
  if (!portalSeason) throw new TypeError('lazyNeeds: falta la temporada del portal');
  if (name === portalSeason) {
    if (datasets.lazy && datasets.lazy[cat] !== undefined) return [];
    return [ensure(cat).then((data) => {
      if (!data) throw new Error(word);
      (datasets.lazy ||= {})[cat] = data;
    })];
  }
  const past = datasets.seasonLazy && datasets.seasonLazy[cat];
  if (!name || (past && Object.hasOwn(past, name))) return [];
  return [ensureSeason(cat, name).then((raw) => {
    if (!raw) throw new Error(`${word} de la temporada ${seasonText(name)}`);
    ((datasets.seasonLazy ||= {})[cat] ||= {})[name] = raw;
  })];
}

// alevinNeeds de antes: lazyNeeds de alevín, con los cargadores de antes ({ ensure(), ensureSeason(season) }).
export function alevinNeeds(name, datasets, portalSeason, { ensure = ensureAlevin, ensureSeason = ensureSeasonAlevin } = {}) {
  if (!portalSeason) throw new TypeError('alevinNeeds: falta la temporada del portal');
  return lazyNeeds('alevin', name, datasets, portalSeason, { ensure: () => ensure(), ensureSeason: (_cat, season) => ensureSeason(season) });
}

// Carga lo que falte de las categorías perezosas `cats` de las temporadas `names` (lazyNeeds:
// data-<cat>.js en la del portal y data-season-<S>-<cat>.js en una pasada, donde un 404 es «sin esa
// categoría» y cuenta como cargado) y devuelve las que no llegaron, [{ cat, season }] en el orden de
// `names` y, en cada una, de `cats` ([] si están todas): un fallo no se memoriza y la llamada siguiente
// las vuelve a pedir. Como loadSeasons, para el cara a cara de un partido y la Trayectoria, que sin ellas
// dirían de menos. Solo las que la temporada tiene (lazyCatsOf de datasets.seasons): las demás quedan
// «sin esa categoría», como un 404, sin pedirlas. `loaders`, los de lazyNeeds.
export async function loadLazySeasons(datasets, names, portalSeason, cats = Object.keys(LAZY), loaders = {}) {
  const has = (cat, season) => lazyCatsOf(datasets.seasons, season).includes(cat);
  for (const season of names) {
    for (const cat of cats.filter((c) => !has(c, season))) {
      if (season === portalSeason) { if (!datasets.lazy || datasets.lazy[cat] === undefined) (datasets.lazy ||= {})[cat] = lazyData(cat, {}); }
      else if (!Object.hasOwn((datasets.seasonLazy || {})[cat] || {}, season)) ((datasets.seasonLazy ||= {})[cat] ||= {})[season] = {};
    }
  }
  const pairs = names.flatMap((season) => cats.filter((cat) => has(cat, season)).map((cat) => ({ cat, season })));
  const done = await Promise.all(pairs.map(({ cat, season }) => Promise.all(lazyNeeds(cat, season, datasets, portalSeason, loaders))
    .then(() => true, () => false)));
  return pairs.filter((_, i) => !done[i]);
}

// Los cargadores de lazyNeeds ({ ensure(cat), ensureSeason(cat, season) }) con los de alevín de antes
// ({ ensure(), ensureSeason(season) }, los de alevinNeeds) para alevín y `others` para las demás (las pruebas
// pasan los suyos; sin ellos, los de siempre).
export function lazyLoaders(alevin = {}, others = {}) {
  const { ensure = ensureLazy, ensureSeason = ensureSeasonLazy } = others;
  return {
    ensure: (cat) => (cat === 'alevin' && alevin.ensure ? alevin.ensure() : ensure(cat)),
    ensureSeason: (cat, season) => (cat === 'alevin' && alevin.ensureSeason ? alevin.ensureSeason(season) : ensureSeason(cat, season)),
  };
}

// loadAlevinSeasons de antes: las temporadas (no los pares) cuyo alevín no llegó. `loaders`, los de alevinNeeds.
export async function loadAlevinSeasons(datasets, names, portalSeason, { ensure = ensureAlevin, ensureSeason = ensureSeasonAlevin } = {}) {
  const failed = await loadLazySeasons(datasets, names, portalSeason, ['alevin'],
    { ensure: () => ensure(), ensureSeason: (_cat, season) => ensureSeason(season) });
  return failed.map(({ season }) => season);
}

// data-health.json: la comprobación de las fuentes, parseada, o null si no
// llega (sin conexión, por ejemplo). Un único vuelo: las llamadas simultáneas comparten la
// petición. Una respuesta vale HEALTH_TTL_MS: el aviso de estado de la portada no puede leer la de
// hace horas. Si la sirvió la copia del service worker, o si un refresco falla y había una anterior,
// el objeto lleva fromCache: true y vale solo HEALTH_TTL_COPIA_MS: el SW da la copia mientras la red
// no contesta a tiempo, y la web tiene que enterarse pronto de que volvió. Un fallo no se memoriza y
// la siguiente llamada reintenta.
export const HEALTH_TTL_MS = 600000;
export const HEALTH_TTL_COPIA_MS = 30000;
const ttlDe = (health) => (health && health.fromCache ? HEALTH_TTL_COPIA_MS : HEALTH_TTL_MS);
let _health = null;
let _healthAt = 0;
let _healthPromise = null;
async function loadHealth(now) {
  try {
    const r = await fetchData('data-health.json');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const health = JSON.parse(await r.text());
    _health = r.fromCache ? { ...health, fromCache: true } : health;
    _healthAt = now();
    return _health;
  } catch (e) {
    console.warn('[state] ensureHealth failed:', e.message);
    return _health ? { ..._health, fromCache: true } : null;
  }
}
export async function ensureHealth({ now = Date.now } = {}) {
  if (_health && now() - _healthAt <= ttlDe(_health)) return _health;
  if (!_healthPromise) _healthPromise = loadHealth(now).finally(() => { _healthPromise = null; });
  return _healthPromise;
}

// Lo que ponen en `needs` las pantallas que leen data-health: una promesa que deja la salud (o null)
// en datasets.health y su hora en datasets.healthAt, o null si no hace falta esperarla. Se pide si
// no se ha pedido nunca o si la última respuesta tiene más de HEALTH_TTL_MS (HEALTH_TTL_COPIA_MS si
// es fromCache); sin healthAt (una salud puesta a mano), vale la que hay. Con una copia caducada se
// pide sin esperarla: con la red que no contesta, cada navegación esperaría su límite; la pantalla se
// pinta con la copia y la respuesta queda para la siguiente. Nunca rechaza.
export function healthNeeds(datasets, { ensure = ensureHealth, now = Date.now } = {}) {
  const fresh = datasets.health !== undefined && !(Number.isFinite(datasets.healthAt) && now() - datasets.healthAt > ttlDe(datasets.health));
  if (fresh) return null;
  const copia = !!(datasets.health && datasets.health.fromCache);
  const load = ensure().then((health) => {
    datasets.health = health;
    datasets.healthAt = now();
  });
  if (!copia) return load;
  // Si falla, se queda la copia y la navegación siguiente lo vuelve a intentar.
  load.catch(() => {});
  return null;
}

/* `needs` de las pantallas que leen una temporada: [] si es la del portal o ya
 * está en datasets.seasonRaw; si no, una promesa que la guarda allí, o que rechaza con
 * Error(<qué>) para la caja «No se pudieron cargar los datos de <qué>» del router. La temporada del
 * portal la da el router (needs(params, datasets, { portalSeason })), nunca config.js. */
export function seasonNeeds(name, datasets, portalSeason) {
  if (!portalSeason) throw new TypeError('seasonNeeds: falta la temporada del portal');
  if (!name || name === portalSeason || datasets.seasonRaw[name]) return [];
  return [ensureSeasonData(name).then((raw) => {
    if (!raw) throw new Error(`la temporada ${String(name).replace(/^(\d{4})-\d{2}(\d{2})$/, '$1/$2')}`);
    datasets.seasonRaw[name] = raw;
  })];
}

// Carga las temporadas `names` que falten en datasets.seasonRaw; true si están todas (false si alguna
// no llegó: ensureSeasonData no memoriza el fallo, y la llamada siguiente la vuelve a pedir). La usan
// el cara a cara de Partido (temporadas anteriores) y la Trayectoria de Equipo (todo el archivo).
export async function loadSeasons(datasets, names, load = ensureSeasonData) {
  const done = await Promise.all(names.map(async (name) => {
    if (datasets.seasonRaw[name]) return true;
    const raw = await load(name);
    if (raw) datasets.seasonRaw[name] = raw;
    return Boolean(raw);
  }));
  return done.every(Boolean);
}
