// Router. La ruta vive en el hash (#/<pantalla>?<parámetros>) y es la fuente de verdad de lo que se ve.
// - Funciones puras: resolveParams (valores por defecto y redirecciones),
//   historyMode (pushState o replaceState), parentOf («‹») y activeTab (barra, con routeIsMine de
//   myteam.js).
// - startRouter, la parte con DOM: hashchange y popstate, enlaces antiguos, token de
//   navegación, la temporada pendiente, needs → render → mount, desplazamiento por entrada del
//   historial, foco al h1 (o al control del ancla), «‹» y Reintentar; y el nav de las pantallas,
//   con la búsqueda que se apunta sin pintar (update, solo desde el mount vigente), los vistos hace
//   poco y «Borrar datos».
// No toca el navegador al importarse: startRouter recibe `window`.
import { Html } from './html.js';
import { isPlayerKey, parseRoute, routeHref, translateLegacy } from './links.js';
import { CATEGORIES, CAT_WORDS, LAZY_CATS, competitions, findGroup, findMatch, findRound, seasonLabel } from './model.js';
import { defaultCategory, myTeamIn, routeIsMine, sameClub } from './myteam.js';
import { skeleton, errorScreen, routeNotice, routeTitle, updateTabbar } from './shell.js';
import { lazyNeeds, normalizeTeamName, seasonNeeds } from './state.js';
import { forecastOptions } from './ui.js';
import { projectionApplies, standingsStart } from './proyeccion.js';

// Destinos principales de la barra, por pantalla.
const PRIMARY = { '': 'miequipo', jornada: 'jornada', tabla: 'tabla', explorar: 'explorar' };
const TABS = new Set(Object.values(PRIMARY));
const NO_PARAMS = new Set(['', 'temporadas', 'fuentes', 'ajustes']);
// Las vistas de Tabla. Las de la antigua Evolución del grupo (evolucion y posiciones) se quitan, sin
// aviso, como cualquier otra que no existe: los enlaces viejos abren la vista por defecto. La del
// pronóstico de la clasificación final (pronostico; PROJECTION_VIEW de screen-tabla.js), solo donde lo
// hay (projectionParams).
const PROJECTION_VIEW = 'pronostico';
const VIEWS = ['puntos', 'goles', 'forma', 'casa', 'fuera', 'todas', PROJECTION_VIEW];
// Lo que se cambia sin crear entrada en el historial: jornada, vista de Tabla y búsqueda; y el
// grupo en Jornada y en Tabla (la tira de grupos y «Mi grupo»), también de un grupo a «Todos» y de
// vuelta (c y f), que se recorre como las jornadas: Atrás no repasa cada grupo visto, sino que vuelve a
// donde se estaba antes de recorrerlos, y el foco se queda en la ficha pulsada (mismo id). En Tabla, `t`
// va con la vista del pronóstico (el equipo resaltado): de ella a la clasificación se quitan los dos. En
// el ranking, el año y la vista (su fila de años y sus dos pestañas), igual.
const REPLACE_ONLY = { jornada: ['r', 'g', 'c', 'f'], tabla: ['v', 'g', 't'], explorar: ['q'], goleadores: ['q'], ranking: ['y', 'v'] };
// Pantallas que se abren desde Explorar: su «‹» sin historial lleva a #/explorar.
const UNDER_EXPLORE = new Set(['equipo', 'copa', 'goleadores', 'ligas', 'temporadas', 'records', 'fuentes', 'ajustes', 'jugador', 'ranking']);
const MAX_REDIRECTS = 5;
// El último destino principal, en la sesión (app.js lo borra con «Borrar datos»).
export const SESSION_KEY = 'fb2:destino';
// Un ancla que es uno de estos controles se lleva el foco en lugar del h1 (#/explorar#buscar).
const FORM_CONTROLS = new Set(['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON']);
// Parámetros de valor cerrado: el que no está en su lista se quita, sin aviso, como una vista de Tabla
// que no existe. Con una isla (`i`) desconocida Ligas saldría vacía, y con otro `to` sus grupos
// enlazarían a otra pantalla. Las categorías, las de la app (alevín incluido).
const CLOSED = {
  ligas: { c: CATEGORIES, i: ['grancanaria', 'lanzarote', 'fuerteventura'], to: ['tabla', 'jornada'] },
  goleadores: { c: CATEGORIES },
  records: { c: CATEGORIES },
};

const redirect = (screen, params, notice = null) => ({ redirect: { screen, params, notice } });
const omit = (params, key) => Object.fromEntries(Object.entries(params).filter(([k]) => k !== key));
const pick = (params, keys) => Object.fromEntries(keys.filter((k) => params[k] != null && params[k] !== '').map((k) => [k, params[k]]));
const knownSeason = (ctx, name) => (ctx.datasets?.seasons || []).some((entry) => entry && entry.name === name);
const hasTeam = (group, name) => group.standings.some((row) => row.team === name)
  || group.rounds.some((round) => round.matches.some((m) => m.home === name || m.away === name));

// Nombre y categoría de mi equipo: los resueltos o, en E y X, los guardados.
function identity(ctx) {
  const r = ctx.resolution;
  return r?.status === 'ok' ? { name: r.name, cat: r.cat } : { name: ctx.myTeam?.name || '', cat: ctx.myTeam?.cat || '' };
}

// ── Las categorías perezosas ────────────────────────────────────────────
//
// Alevín, infantil, cadete y juvenil (LAZY_CATS) nunca están en la carga inicial: el router pide las que
// necesita una ruta (loadLazy, lazyNeeds de state.js) antes de pintarla, una vez por navegación. Cada una
// es { cat, season, soft }: la categoría, la temporada y si, al no llegar, la ruta se pinta sin ella y lo
// dice (soft) o da la caja de error («No se pudieron cargar los datos de cadete»). Las necesita para
// validarse (resolveParams las devuelve en `lazy`, igual que `pending` con una temporada sin cargar): un
// grupo que no está, que puede ser de una de ellas, antes de darlo por perdido, y Jornada y Tabla de mi
// equipo cuando este se resuelve con una de ellas; o para pintarse (needsLazy).

// La categoría perezosa de un código de grupo por su prefijo (scripts/convenio.py: INF, CAD y JUV; los de
// alevín, AL…), o null si el código no la dice.
const LAZY_PREFIXES = [['INF', 'infantil'], ['CAD', 'cadete'], ['JUV', 'juvenil'], ['AL', 'alevin']];
function lazyCatOf(id) {
  const code = String(id || '').toUpperCase();
  const hit = LAZY_PREFIXES.find(([prefix]) => code.startsWith(prefix));
  return hit ? hit[1] : null;
}

// ¿Está sin pedir la categoría perezosa `cat` de la temporada `s`? La de la del portal es
// datasets.lazy[cat] y la de una pasada, datasets.seasonLazy[cat][s] (el registro de app.js): sin pedir
// mientras no tiene valor.
function lazyMissing(ctx, cat, s) {
  const data = ctx.datasets || {};
  if (!s) return false;
  if (s === ctx.portal.season) return !(data.lazy && data.lazy[cat] !== undefined);
  const past = data.seasonLazy && data.seasonLazy[cat];
  return !(past && Object.hasOwn(past, s));
}
const triedKey = (cat, season) => `${cat}|${season}`;
// Las de `cats` que faltan en la temporada `s`, con su `soft`. Con `skipTried`, sin las ya pedidas en esta
// navegación (ctx.lazyTried): lo soft que ya se pidió y no llegó no se espera más.
function wantsOf(ctx, cats, s, soft, skipTried = false) {
  return cats.filter((cat) => lazyMissing(ctx, cat, s) && !(skipTried && ctx.lazyTried?.has(triedKey(cat, s))))
    .map((cat) => ({ cat, season: s, soft }));
}

// ¿Espera mi equipo a una perezosa de la temporada del portal para resolverse? → [{ cat, season, soft }]
// - Si es de una de ellas: sin ella, X por error (soft: false, la caja de error si no llega).
// - Si es de otra temporada: el paso 1 de resolveMyTeam busca en todas las categorías, y sin alevín daría
//   «ok» en silencio y, al cargarlo, la pregunta. No es «una vez al año»: un
//   cambio de temporada nunca se guarda solo (myTeamToSave), así que, mientras la familia no lo confirme,
//   se espera en cada carga en frío de toda la temporada (con el SW, data-alevin.js sale del precache,
//   donde va como opcional). Por eso es soft: si no llega (ctx.lazyTried, ya pedida en esta navegación),
//   se resuelve sin él, como antes de alevín, nunca con la caja de error en su portada. Solo alevín, como
//   siempre: la portada de un equipo de benjamín no baja infantil, cadete ni juvenil.
function mineWaits(ctx) {
  const mine = ctx.myTeam;
  const portal = ctx.portal.season;
  if (!mine || !mine.name) return [];
  if (LAZY_CATS.includes(mine.cat)) return wantsOf(ctx, [mine.cat], portal, false);
  return mine.season !== portal ? wantsOf(ctx, ['alevin'], portal, true, true) : [];
}

// Un grupo `id` que no está en la temporada `s`: lo que falta de la categoría de su prefijo (o de `cat`,
// la de la ruta) o, si no se sabe, de todas, soft (que, si no llegan, dan el grupo por perdido).
function groupWants(ctx, id, s, cat = null) {
  const own = cat || lazyCatOf(id);
  return own ? wantsOf(ctx, [own], s, false) : wantsOf(ctx, LAZY_CATS, s, true, true);
}

const SCORER_SCREENS = new Set(['goleadores', 'records']);

/* Lo que una pantalla ya validada pinta con las perezosas → [{ cat, season, soft }] ([] si no hace
 * falta ninguna o ya se pidieron). soft: si no llega, la pantalla se pinta igual, con las demás, un aviso
 * y «Reintentar» (Explorar y Ligas sin `c`; ctx.lazyFailed); si no, la caja de error «No se pudieron
 * cargar los datos de <categoría>», nunca una pantalla a medias que lo calle:
 * - la portada, y la categoría por defecto de Goleadores y Récords, si mi equipo la espera (mineWaits);
 * - `c=<perezosa>` (o, en Goleadores y Récords, una perezosa como categoría por defecto), de la temporada `s`;
 * - Explorar y Ligas sin `c`, que enseñan todas las categorías (soft);
 * - un grupo de la ruta que no está: la de su prefijo (AL, INF, CAD, JUV) o, si no se sabe, todas (soft).
 * La portada de un equipo de benjamín o prebenjamín nunca pide nada: tiene que abrir en 3 s. */
export function needsLazy(route, ctx) {
  const screen = route?.screen ?? '';
  const params = route?.params || {};
  const portal = ctx.portal.season;
  const s = params.s || portal;
  const byDefault = SCORER_SCREENS.has(screen) && !params.c && !params.g;
  if (screen === '' || byDefault) {
    const waits = mineWaits(ctx);
    if (waits.length) return waits;
  }
  const cat = params.c || (byDefault ? defaultCategory(ctx.resolution, ctx.portal.defaultTeam) : null);
  if (LAZY_CATS.includes(cat) && (screen === 'ligas' || SCORER_SCREENS.has(screen))) return wantsOf(ctx, [cat], s, false);
  if (screen === 'explorar' || (screen === 'ligas' && !params.c)) return wantsOf(ctx, LAZY_CATS, s, true);
  if (params.g && ctx.model && ctx.model.season(s) && !findGroup(ctx.model, s, params.g)) return groupWants(ctx, params.g, s);
  return [];
}

// needsAlevin de antes: lo de alevín de needsLazy → { season, soft } | null.
export function needsAlevin(route, ctx) {
  const want = needsLazy(route, ctx).find((w) => w.cat === 'alevin');
  return want ? { season: want.season, soft: want.soft } : null;
}

// Un grupo `g` que no está en la temporada `s`: con su categoría perezosa sin pedir (la de su prefijo, la
// `cat` de la ruta o, si no se sabe, todas), la ruta queda pendiente de ella (puede ser un grupo de un
// enlace compartido o de «Vistos hace poco»); si ya está, `lost`.
const missingGroup = (params, ctx, lost, cat = null) => {
  const wants = groupWants(ctx, params.g, params.s, cat);
  return wants.length ? { params, lazy: wants } : lost();
};

// ── Valores por defecto y redirecciones ─────────────────────────────────
//
// resolveParams(route, ctx) → { params, pending?, lazy? } | { redirect: { screen, params, notice } }
//   ctx: { portal: { season }, model, resolution, myTeam, datasets: { seasons, lazy, seasonLazy },
//   lazyTried? }
//   params: los de la ruta con `s` (y `g` en Jornada y Tabla) ya puestos; pending: la temporada
//   pasada aún no está cargada y no se puede validar la ruta (el router la carga y la vuelve a
//   resolver cuando termina `needs`); lazy: lo mismo con las categorías perezosas que faltan,
//   [{ cat, season, soft }], con soft si, al no llegar, la ruta se resuelve sin ella: el router pasa en
//   lazyTried ('<cat>|<temporada>') las que ya pidió en esta navegación. Las redirecciones se aplican
//   con replaceState.
export function resolveParams(route, ctx) {
  const screen = route.screen;
  const raw = route.params || {};
  if (NO_PARAMS.has(screen)) return { params: {} };
  // Jugador: solo su clave (isPlayerKey); su ficha no depende de ninguna temporada.
  if (screen === 'jugador') return { params: isPlayerKey(raw.id) ? { id: raw.id } : {} };
  // Ranking: tampoco. El año, si es de cuatro cifras, y la vista, solo `h` (toda la trayectoria): la de
  // esta temporada es la de por defecto y no se escribe. Lo demás se quita, sin aviso, como en la ficha.
  // Qué año se ve si no hay `y`, o si el año no tiene a nadie, lo dice la pantalla, que es la que carga
  // data-ranking.js.
  if (screen === 'ranking') return { params: { ...(/^\d{4}$/.test(raw.y ?? '') ? { y: raw.y } : {}), ...(raw.v === 'h' ? { v: 'h' } : {}) } };
  const portal = ctx.portal.season;
  if (raw.s && raw.s !== portal && !knownSeason(ctx, raw.s)) {
    return redirect(screen, omit(raw, 's'), `No existe la temporada ${seasonLabel(raw.s)}; te enseñamos la actual`);
  }
  const closed = CLOSED[screen] || {};
  const wrong = Object.keys(closed).filter((key) => raw[key] != null && !closed[key].includes(raw[key]));
  if (wrong.length) return redirect(screen, Object.fromEntries(Object.entries(raw).filter(([key]) => !wrong.includes(key))));
  const params = { ...raw, s: raw.s || portal };
  if (screen === 'jornada' || screen === 'tabla') return leagueParams(screen, raw, params, ctx);
  if (screen === 'partido') return matchParams(raw, params, ctx);
  if (screen === 'equipo') return teamParams(raw, params, ctx);
  // Explorar, Ligas, Copa, Goleadores y Récords: con una temporada pasada sin cargar, pendientes. La
  // carga el router: ninguna pantalla pide la de su ruta.
  if (!ctx.model.season(params.s)) return { params, pending: true };
  if (screen === 'copa') return cupParams(params, ctx);
  if (screen === 'goleadores') return scorersParams(raw, params, ctx);
  return { params };
}

// Jornada y Tabla: `g` por defecto, grupos que no son de liga a #/copa y, sin mi equipo, a #/ligas.
// En Tabla, la vista del pronóstico solo donde lo hay (projectionParams), y `t` solo con ella.
function leagueParams(screen, raw, params, ctx) {
  if (screen === 'tabla' && raw.v && !VIEWS.includes(raw.v)) return redirect(screen, omit(raw, 'v'));
  if (screen === 'tabla' && raw.t && raw.v !== PROJECTION_VIEW) return redirect(screen, omit(raw, 't'));
  const season = ctx.model.season(params.s);
  if (!season) return { params, pending: true };
  const portal = ctx.portal.season;
  const s = params.s === portal ? '' : params.s;
  if (screen === 'jornada' && !params.g && raw.f) return competitionParams(raw, params, ctx);
  // Con un grupo, `c` y `f` (los de «Todos los grupos») no dicen nada: se quitan, sin aviso.
  if (screen === 'jornada' && params.g && (raw.c || raw.f)) return redirect(screen, omit(omit(raw, 'c'), 'f'));
  const mine = identity(ctx);
  let group;
  if (params.g) {
    group = findGroup(ctx.model, params.s, params.g);
    if (!group) {
      return missingGroup(params, ctx, () => redirect('ligas', { s, c: mine.cat, to: screen },
        `No encontramos el grupo ${params.g} en la temporada ${seasonLabel(params.s)}`));
    }
    if (group.kind !== 'league') return redirect('copa', { s, g: group.id });
  } else if (params.s === portal) {
    // Mi equipo que se resuelve con una perezosa (mineWaits): antes, ella (alevín soft en un cambio de temporada).
    const waits = mineWaits(ctx);
    if (waits.length) return { params, lazy: waits };
    // Mi equipo sin resolver (E, pregunta pendiente; X, ausente): a Ligas de la temporada actual.
    if (ctx.resolution?.status !== 'ok') return redirect('ligas', { to: screen }, 'Elige tu equipo en Mi equipo');
    group = ctx.resolution.group;
  } else {
    // Temporada pasada: el primer grupo de liga de la categoría de mi equipo con su nombre (en una
    // perezosa, con la de esa temporada).
    if (LAZY_CATS.includes(mine.cat) && lazyMissing(ctx, mine.cat, params.s)) return { params, lazy: [{ cat: mine.cat, season: params.s, soft: false }] };
    group = mine.name ? season.groups.find((g) => g.cat === mine.cat && g.kind === 'league' && hasTeam(g, mine.name)) : null;
    if (!group) {
      return redirect('ligas', { s, c: mine.cat, to: screen },
        mine.name ? `${mine.name} no aparece en la temporada ${seasonLabel(params.s)}` : 'Elige tu equipo en Mi equipo');
    }
  }
  // La jornada vale por su clave o por su número (la pantalla lee las dos); si no, se quita.
  if (screen === 'jornada' && raw.r && !findRound(group, raw.r)) return redirect(screen, omit(raw, 'r'));
  if (screen === 'tabla' && raw.v === PROJECTION_VIEW) {
    const lost = projectionParams(raw, group, ctx);
    if (lost) return lost;
  }
  return { params: { ...params, g: group.id } };
}

// La vista del pronóstico de la clasificación final: solo en un grupo con pronóstico
// (projectionApplies de proyeccion.js, la misma de la pantalla y una vez por grupo, sin pronosticar ni
// simular nada: las simulaciones, solo al pintar la vista); si no, se quita con su `t`, sin aviso, como una
// vista que no existe. `t`, el equipo resaltado, solo si está en la tabla prevista, que es la de la
// clasificación de partida (standingsStart: no un retirado ni otro grupo); si no, se quita. La redirección
// (null si vale).
function projectionParams(raw, group, ctx) {
  if (!group.standings.length || !projectionApplies(group, forecastOptions(ctx))) return redirect('tabla', omit(omit(raw, 'v'), 't'));
  if (raw.t && !standingsStart(group).some((row) => row.team === raw.t)) return redirect('tabla', omit(raw, 't'));
  return null;
}

// Jornada de todos los grupos de una competición («Todos los grupos», #/jornada?s&c&f&r, sin `g`): `c` y
// `f` la eligen entre las de competitions() con algún grupo de liga (sin `c`, la de la categoría que la
// tiene). Una que no existe, a Ligas de su categoría, con aviso. La jornada vale por su número (o su
// clave) en cualquiera de sus grupos, porque las claves cambian de un grupo a otro; si no, se quita.
function competitionParams(raw, params, ctx) {
  const s = params.s === ctx.portal.season ? '' : params.s;
  const entry = competitions(ctx.model, params.s, { cat: raw.c || null })
    .find((e) => e.key === raw.f && e.groups.some((g) => g.kind === 'league'));
  if (!entry) {
    const lost = () => redirect('ligas', { s, c: raw.c, to: 'jornada' }, `No encontramos la competición ${raw.f} en la temporada ${seasonLabel(params.s)}`);
    // La de una perezosa (o, sin `c`, la que puede serlo: todas, soft), como un grupo que no está: antes, ella.
    if (raw.c && !LAZY_CATS.includes(raw.c)) return lost();
    const wants = raw.c ? wantsOf(ctx, [raw.c], params.s, false) : wantsOf(ctx, LAZY_CATS, params.s, true, true);
    return wants.length ? { params, lazy: wants } : lost();
  }
  if (raw.c !== entry.cat) return redirect('jornada', { ...raw, c: entry.cat });
  if (raw.r && !entry.groups.some((g) => g.kind === 'league' && findRound(g, raw.r))) return redirect('jornada', omit(raw, 'r'));
  return { params };
}

// Partido: vale si findMatch lo encuentra, igual que la pantalla (en su ronda o, si ahí no está, el
// único h–a del grupo). Si no, otra grafía de sus equipos («Las Mesas Hu», sin el punto que se pierde
// al final de una URL): con un solo partido de esos nombres normalizados, la ruta pasa a la suya, sin
// aviso y con la `s` que traía (como Equipo); con ninguno o con varios, a su jornada, con aviso.
function matchParams(raw, params, ctx) {
  const season = ctx.model.season(params.s);
  if (!season) return { params, pending: true };
  const s = params.s === ctx.portal.season ? '' : params.s;
  const lost = 'No encontramos ese partido';
  const group = params.g ? findGroup(ctx.model, params.s, params.g) : null;
  if (!group) return params.g ? missingGroup(params, ctx, () => redirect('jornada', { s }, lost)) : redirect('jornada', { s }, lost);
  if (!findMatch(group, params)) {
    const round = findRound(group, params.r);
    const same = sameNamedMatches(group, round, params);
    if (same.length === 1) {
      const [{ match, key }] = same;
      return redirect('partido', { s: raw.s, g: group.id, r: key, h: match.home, a: match.away });
    }
    return redirect('jornada', { s, g: group.id, r: round ? round.key : '' }, lost);
  }
  return { params };
}

// Los partidos del grupo, con la clave de su ronda, cuyos local y visitante tienen los nombres
// normalizados de `h` y `a`: los de la ronda, si los hay en ella; si no, los de todo el grupo.
function sameNamedMatches(group, round, { h, a }) {
  const home = normalizeTeamName(String(h ?? ''));
  const away = normalizeTeamName(String(a ?? ''));
  if (!home || !away) return [];
  const inRound = (r) => r.matches.filter((m) => typeof m.home === 'string' && typeof m.away === 'string'
    && normalizeTeamName(m.home) === home && normalizeTeamName(m.away) === away).map((match) => ({ match, key: r.key }));
  const there = round ? inRound(round) : [];
  return there.length ? there : (group.rounds || []).flatMap(inRound);
}

// Equipo: `g` y `t` son obligatorios; sin ellos, el equipo se busca en Explorar (como un enlace
// antiguo). Con la temporada cargada: un grupo que no es de liga (un torneo MC* o una copa de la
// federación, sin ficha de equipo) abre su Copa, sin aviso, como «Vistos hace poco» y los enlaces
// antiguos a torneos. Un equipo que no juega en el grupo con ese nombre exacto: si un solo equipo del
// grupo tiene su nombre normalizado, es otra grafía del mismo («Las Mesas Hu», sin punto), y la ruta
// pasa a su nombre canónico, sin aviso y con el resto de sus parámetros; si no hay ninguno, o hay
// varios, se busca en Explorar, con aviso (el `g` de un enlace antiguo puede no ser el de su equipo).
function teamParams(raw, params, ctx) {
  const s = params.s === ctx.portal.season ? '' : params.s;
  if (!params.g || !params.t) return redirect('explorar', { s, q: params.t });
  const season = ctx.model.season(params.s);
  if (!season) return { params, pending: true };
  const group = findGroup(ctx.model, params.s, params.g);
  if (!group) {
    return missingGroup(params, ctx, () => redirect('explorar', { s, q: params.t },
      `No encontramos el grupo ${params.g} en la temporada ${seasonLabel(params.s)}`));
  }
  if (group.kind !== 'league') return redirect('copa', { s, g: group.id });
  if (!hasTeam(group, params.t)) {
    const same = sameNamed(group, params.t);
    if (same.length === 1) return redirect('equipo', { ...raw, t: same[0] });
    return redirect('explorar', { s, q: params.t }, `No encontramos a ${params.t} en ${group.label}`);
  }
  return { params };
}

// Los equipos del grupo, de la clasificación o del calendario, con el nombre normalizado de `name`
// (normalizeTeamName de state.js: sin tildes, puntos ni siglas del club).
function sameNamed(group, name) {
  const key = normalizeTeamName(String(name));
  const teams = new Set([...group.standings.map((row) => row.team),
    ...group.rounds.flatMap((round) => round.matches.flatMap((m) => [m.home, m.away]))]);
  return [...teams].filter((team) => typeof team === 'string' && team !== '' && normalizeTeamName(team) === key);
}

// Copa: el grupo es una copa de la federación o un torneo. Uno de liga abre su
// Tabla, sin aviso; uno que no existe, Ligas de esa temporada con el aviso de la Tabla; sin grupo,
// Ligas sin aviso (ningún enlace de la app lo da: una dirección escrita a mano).
function cupParams(params, ctx) {
  const s = params.s === ctx.portal.season ? '' : params.s;
  if (!params.g) return redirect('ligas', { s });
  const group = findGroup(ctx.model, params.s, params.g);
  if (!group) {
    return missingGroup(params, ctx, () => redirect('ligas', { s }, `No encontramos el grupo ${params.g} en la temporada ${seasonLabel(params.s)}`));
  }
  if (group.kind === 'league') return redirect('tabla', { s, g: group.id });
  return { params };
}

// Goleadores: un grupo que no existe se quita, con aviso: la global de su
// categoría (la `c` del enlace o, sin ella, la que la pantalla pone por defecto).
function scorersParams(raw, params, ctx) {
  if (!params.g || findGroup(ctx.model, params.s, params.g)) return { params };
  return missingGroup(params, ctx, () => redirect('goleadores', omit(raw, 'g'),
    `No encontramos el grupo ${params.g} en la temporada ${seasonLabel(params.s)}`));
}

// ── Historial, «‹» y barra ───────────────────────────────────────────────

// 'replace' si solo cambian la jornada, la vista de Tabla o la búsqueda (o nada); si no, 'push'.
export function historyMode(from, to) {
  if (!from || !to || from.screen !== to.screen) return 'push';
  const a = from.params || {};
  const b = to.params || {};
  const changed = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((k) => (a[k] ?? '') !== (b[k] ?? ''));
  const allowed = REPLACE_ONLY[to.screen] || [];
  return changed.every((k) => allowed.includes(k)) ? 'replace' : 'push';
}

// Padre de «‹» cuando no hay entrada anterior de la app: lo que cuelga de Explorar → Explorar; los
// destinos principales no tienen; y Partido, según su grupo, que se busca en `model` (el del contexto):
// - de un grupo que no es de liga (una copa o un torneo MC*) → #/copa?s&g;
// - de liga → su jornada, con la clave de la ronda del partido (findMatch) o, si el partido no
//   está en el grupo, sin `r`: la jornada por defecto;
// - sin modelo, o con el grupo sin encontrar (su temporada sin cargar), la jornada del enlace.
export function parentOf(route, model = null) {
  const params = route?.params || {};
  if (route?.screen === 'partido') {
    const group = model && params.g ? findGroup(model, params.s, params.g) : null;
    if (!group) return { screen: 'jornada', params: pick(params, ['s', 'g', 'r']) };
    if (group.kind !== 'league') return { screen: 'copa', params: { s: group.season, g: group.id } };
    const match = findMatch(group, params);
    return { screen: 'jornada', params: pick({ s: group.season, g: group.id, r: match ? match.roundKey : '' }, ['s', 'g', 'r']) };
  }
  if (UNDER_EXPLORE.has(route?.screen)) return { screen: 'explorar', params: {} };
  return null;
}

// Destino marcado en la barra → { active, current }: 'page' en los principales y 'true'
// en las secundarias. Partido lleva el último destino principal de la sesión o, si se entra por
// enlace directo, Mi equipo si el partido es de mi equipo y Jornada si no.
export function activeTab(route, lastPrimary, isMine) {
  const screen = route?.screen ?? '';
  if (Object.hasOwn(PRIMARY, screen)) return { active: PRIMARY[screen], current: 'page' };
  if (screen === 'partido') return { active: TABS.has(lastPrimary) ? lastPrimary : isMine ? 'miequipo' : 'jornada', current: 'true' };
  if (screen === 'equipo') return { active: isMine ? 'miequipo' : 'explorar', current: 'true' };
  const to = route?.params?.to;
  if (screen === 'ligas' && (to === 'tabla' || to === 'jornada')) return { active: to, current: 'true' };
  return { active: 'explorar', current: 'true' };
}

// Adónde llevan las pestañas Jornada y Tabla de la barra (updateTabbar de shell.js): en Jornada, Tabla y
// Partido de un grupo de liga, a ese grupo y su temporada; en «Todos los grupos» (Jornada con c y f),
// Jornada a esa misma vista y Tabla a la de mi grupo, si está en esa competición, o a la del primero.
// Si el grupo es el resuelto de mi equipo, o en cualquier otra pantalla, {}: sus enlaces de siempre
// (#/jornada y #/tabla, el grupo de mi equipo). route: la ruta ya resuelta; ctx: { model, portal,
// myTeam, resolution }. Con su temporada sin cargar, {}.
export function tabTargets(route, ctx) {
  const params = route?.params || {};
  const screen = route?.screen;
  if (!['jornada', 'tabla', 'partido'].includes(screen) || !ctx?.model) return {};
  const season = params.s || ctx.portal.season;
  const r = ctx.resolution;
  const own = (group) => r?.status === 'ok' && r.group && r.group.season === group.season && r.group.id === group.id;
  const tabla = (group) => (own(group) ? '#/tabla' : routeHref('tabla', { s: group.season, g: group.id }));
  if (screen === 'jornada' && !params.g && params.f) {
    const entry = competitions(ctx.model, season, { cat: params.c || null }).find((e) => e.key === params.f);
    const groups = entry ? entry.groups.filter((g) => g.kind === 'league') : [];
    if (!groups.length) return {};
    const mine = groups.find((g) => myTeamIn(g, ctx.myTeam, r)) || groups[0];
    return { jornada: routeHref('jornada', { s: season, c: entry.cat, f: entry.key }), tabla: tabla(mine) };
  }
  const group = params.g ? findGroup(ctx.model, season, params.g) : null;
  if (!group || group.kind !== 'league' || own(group)) return {};
  return { jornada: routeHref('jornada', { s: group.season, g: group.id }), tabla: tabla(group) };
}

// ── startRouter ──────────────────────────────────────────────────────────

// Qué no se pudo cargar, para «No se pudieron cargar los datos de <qué>»: el `what` del error o
// el mensaje de un Error simple (las cargas de `needs` rechazan con Error('la temporada 2024/25')).
// Un fallo de programación (TypeError, RangeError…) no enseña su mensaje.
function loadWhat(err) {
  if (err && typeof err.what === 'string' && err.what) return err.what;
  if (err && Object.getPrototypeOf(err) === Error.prototype && err.message) return err.message;
  return 'esta pantalla';
}

// El aviso de una redirección va detrás de la cabecera de la pantalla (o de su h1).
function withNotice(markup, text) {
  if (!text) return markup;
  const note = String(routeNotice(text));
  const head = markup.indexOf('</header>');
  const h1 = markup.indexOf('</h1>');
  const at = head >= 0 ? head + '</header>'.length : h1 >= 0 ? h1 + '</h1>'.length : 0;
  return markup.slice(0, at) + note + markup.slice(at);
}

const decode = (text) => { try { return decodeURIComponent(text); } catch { return text; } };

// ¿Es mi equipo el de un enlace antiguo «miequipo»? El mismo nombre, o el mismo club en el mismo
// grupo, que el guardado o el resuelto.
function legacyMine(ctx) {
  const mine = [
    ctx.myTeam && ctx.myTeam.name ? { name: ctx.myTeam.name, groupId: ctx.myTeam.groupId } : null,
    ctx.resolution?.status === 'ok' ? { name: ctx.resolution.name, groupId: ctx.resolution.group.id } : null,
  ].filter(Boolean);
  return (team, group) => mine.some((m) => m.name === team
    || (Boolean(group) && group === m.groupId && sameClub(ctx.model.clubIndex(), team, m.name)));
}

// screens: { <pantalla>: { id, needs, render, mount? } }; root: <main id="contenido">;
// getContext() → { model, myTeam, recent, resolution, today, health, datasets, portal, legacyDate }
// (los datos de cada pintado; el router añade route, params, lastPrimary y backHref); actions, de
// app.js: saveMyTeam(myTeam) guarda mi equipo, addRecent(entry) apunta una ficha en «Vistos hace
// poco» y clearData() borra los datos de la app; session: { getItem, setItem } para el último
// destino principal;
// loadSeason(name, datasets, portalSeason) → Promise[]: la carga de una temporada pasada pendiente,
// seasonNeeds de state.js (las pruebas pasan otra); loadLazy(cat, name, datasets, portalSeason) →
// Promise[]: la de una categoría perezosa de una temporada, lazyNeeds de state.js; loadAlevin(name,
// datasets, portalSeason), la de antes solo para alevín (las pruebas de alevín la pasan; si no, la de
// loadLazy). Devuelve { nav, idle, current }: idle() es la promesa del último pintado.
export function startRouter({ screens, root, getContext, window: win, actions = {}, session = null, loadSeason = seasonNeeds, loadLazy = lazyNeeds, loadAlevin = null }) {
  const loadOne = (cat, season, datasets, portalSeason) => (cat === 'alevin' && loadAlevin
    ? loadAlevin(season, datasets, portalSeason) : loadLazy(cat, season, datasets, portalSeason));
  const doc = win.document;
  const hist = win.history;
  const baseTitle = doc.title;
  const positions = new Map();          // desplazamiento por entrada del historial (fbKey)
  let token = 0;
  let serial = 0;
  let current = null;                   // ruta resuelta de la última navegación
  let seen = { key: null, hash: null, idx: -1 };  // la última entrada atendida
  let cleanup = null;                   // lo que devolvió el último mount
  let latest = Promise.resolve();
  let lastPrimary = null;
  const nesting = [];                   // pila de { target, focusId } de la navegación en mount
  let pendingBack = null;               // resolve() de un nav.back() que espera al pintado de la vuelta
  try { lastPrimary = TABS.has(session?.getItem(SESSION_KEY)) ? session.getItem(SESSION_KEY) : null; } catch { lastPrimary = null; }

  // Cada entrada de la app lleva { fbIdx, fbKey }: fbIdx > 0 dice que la anterior es de la app.
  const entry = () => {
    const st = hist.state;
    return st && typeof st.fbIdx === 'number' && typeof st.fbKey === 'string' ? st : null;
  };
  const newKey = () => `${Date.now().toString(36)}.${++serial}`;
  const stamp = (idx) => {
    const st = { fbIdx: idx, fbKey: newKey() };
    hist.replaceState(st, '');
    return st;
  };
  // El «‹» de una ruta (ctx.backHref y la caja de error): el href de su padre, con el modelo del
  // contexto para saber de qué tipo es el grupo de un partido; null en los destinos principales.
  const backHref = (route, model) => {
    const parent = parentOf(route, model);
    return parent ? routeHref(parent.screen, parent.params) : null;
  };
  const screenOf = (name) => screens[name] || screens[''];

  function rememberPrimary(tab) {
    lastPrimary = tab;
    try { session?.setItem(SESSION_KEY, tab); } catch { /* sin sesión: solo en memoria */ }
  }

  // Enlace antiguo → ruta nueva, y valores por defecto y redirecciones, cada paso con
  // replaceState. Devuelve la ruta resuelta, si falta cargar su temporada (pending) o alguna perezosa
  // (lazy: [{ cat, season, soft }]) y el primer aviso.
  function settle(base) {
    let hash = win.location.hash;
    const legacy = translateLegacy(hash, { isMine: legacyMine(base) });
    if (legacy) {
      hist.replaceState(hist.state, '', legacy);
      hash = legacy;
    }
    let route = parseRoute(hash);
    let notice = null;
    for (let i = 0; i <= MAX_REDIRECTS; i++) {
      const res = resolveParams(route, base);
      if (!res.redirect) return { route: { screen: route.screen, params: res.params }, pending: !!res.pending, lazy: res.lazy || [], notice };
      notice = notice || res.redirect.notice || null;
      const href = routeHref(res.redirect.screen, res.redirect.params);
      hist.replaceState(hist.state, '', href);
      route = parseRoute(href);
    }
    // Defensivo: la cadena de redirecciones de resolveParams está pensada para converger; si no lo
    // hace, es un fallo de programación (RangeError: loadWhat no muestra su mensaje literal).
    throw new RangeError('Demasiadas redirecciones');
  }

  function paint(markup) {
    if (cleanup) {
      try { cleanup(); } catch (err) { console.error('[router] limpieza', err); }
      cleanup = null;
    }
    root.innerHTML = String(markup);
  }

  // Desplazamiento: arriba al avanzar, el guardado al volver, el mismo al cambiar jornada o
  // vista; un ancla (#/…#calendario) manda al avanzar. Foco: al h1 (tabindex -1), salvo en la
  // carga inicial; al cambiar jornada o vista, vuelve al control pulsado si sigue (mismo id); y si
  // el ancla es un control de formulario (#/explorar#buscar: «Cambiar» abre Explorar con el
  // buscador enfocado), al avanzar y al reintentar se lo lleva él, no el h1. Al volver (Atrás,
  // Adelante o un hash escrito a mano), el h1: en el móvil, el campo abriría el teclado sobre los
  // resultados que se querían ver.
  function place(mode, target, focusId) {
    const hash = win.location.hash;
    const at = hash.indexOf('#', 1);
    const anchorId = at > 0 ? decode(hash.slice(at + 1)) : '';
    const anchor = anchorId && (mode === 'push' || mode === 'initial') ? doc.getElementById(anchorId) : null;
    if (anchor) anchor.scrollIntoView();
    else win.scrollTo(0, target);
    if (mode === 'initial') return;
    const control = anchorId && (mode === 'push' || mode === 'refresh') ? doc.getElementById(anchorId) : null;
    const field = control && FORM_CONTROLS.has(control.tagName) && root.contains(control) ? control : null;
    const kept = focusId ? doc.getElementById(focusId) : null;
    const el = field || (kept && root.contains(kept) ? kept : root.querySelector('h1'));
    if (!el) return;
    if (el.tagName === 'H1' && !el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
    el.focus({ preventScroll: true });
  }

  // mode: 'initial' | 'push' | 'replace' | 'pop' | 'refresh'. clickedId: el id del enlace pulsado
  // (onClick), para el foco al cambiar de jornada o de vista aunque el clic no active el control
  // (Safari): activeElement queda como reserva, para el teclado.
  function show(mode, carried = null, clickedId = null) {
    const st = entry();
    // Una navegación que empieza dentro de un mount (nesting no vacío) hereda el destino de
    // desplazamiento y de foco de la navegación de fuera, en vez de recalcularlos con el scrollY
    // o el activeElement de ahora mismo, que todavía son los de antes de esa navegación.
    const inherited = nesting[nesting.length - 1] || null;
    const target = inherited ? inherited.target
      : mode === 'pop' ? (positions.get(st?.fbKey) ?? 0) : mode === 'replace' ? win.scrollY : 0;
    const focusId = inherited ? inherited.focusId
      : mode === 'replace' ? (clickedId || doc.activeElement?.id || null) : null;
    latest = run(mode, carried, 0, target, focusId);
    return latest;
  }

  // Las perezosas que le faltan a una ruta ya resuelta (settle), para validarse (`lazy` de resolveParams)
  // o para pintarse (needsLazy): [{ cat, season, soft }].
  const lazyWant = (settled, base) => (settled.lazy.length ? settled.lazy : needsLazy(settled.route, base));

  // tried: las perezosas ('<cat>|<temporada>') ya pedidas en esta navegación (con sus redirecciones), que no
  // se vuelven a pedir hasta la siguiente (Reintentar, u otra pantalla que las necesite). Va al contexto de
  // resolveParams y de needsLazy como lazyTried: lo soft que ya se pidió y no llegó no se espera más.
  async function run(mode, carried, depth, target, focusId, tried = new Set()) {
    const my = ++token;
    let route = parseRoute(win.location.hash);
    let screen = screenOf(route.screen);
    let base = null;
    try {
      base = { ...getContext(), lazyTried: tried };
      const first = settle(base);
      let settled = first;
      route = first.route;
      screen = screenOf(route.screen);
      const notice = carried || first.notice;
      const st = entry();
      current = route;
      seen = { key: st?.fbKey ?? null, hash: win.location.hash, idx: st?.fbIdx ?? 0 };
      const tab = activeTab(route, lastPrimary, routeIsMine(route, base.resolution));
      updateTabbar(tab.active, tab.current, doc, tabTargets(route, base));
      doc.title = route.screen === '' ? baseTitle : `${routeTitle(route.screen)} · ${baseTitle}`;
      // La temporada del portal llega a needs desde el contexto, nunca de config.js.
      const portalSeason = base.portal.season;
      // Una temporada pasada sin cargar (pending: resolveParams no pudo validar la ruta) la carga el
      // router, junto a los needs de la pantalla, pida esta su temporada o no: pending es justo
      // seasonNeeds(s). Si la carga falla, la caja de error con «Reintentar», que vuelve a pedirla
      // (ensureSeasonData no memoriza un fallo).
      // Las perezosas, igual, a la vez: si una falla, la caja de error con «Reintentar» («No se pudieron
      // cargar los datos de cadete»), salvo las soft (Explorar y Ligas sin `c`), que se pintan sin ella y
      // lo dicen (ctx.lazyFailed).
      const fresh = lazyWant(first, base).filter((w) => !tried.has(triedKey(w.cat, w.season)));
      const lazyLoads = fresh.flatMap((w) => loadOne(w.cat, w.season, base.datasets, portalSeason)
        .map((load) => (w.soft ? load.catch((err) => console.warn(`[router] ${w.cat}`, err)) : load)));
      fresh.forEach((w) => tried.add(triedKey(w.cat, w.season)));
      const needs = [
        ...(first.pending ? loadSeason(route.params.s, base.datasets, portalSeason) : []),
        ...lazyLoads,
        ...((screen.needs && screen.needs(route.params, base.datasets, { portalSeason })) || []),
      ];
      if (needs.length) {
        paint(skeleton(screen.id));
        await Promise.all(needs);
        if (my !== token) return latest;   // otra navegación empezó mientras cargaba: no se pinta; que idle() la espere
      }
      if (needs.length || first.pending || first.lazy.length) {
        base = { ...getContext(), lazyTried: tried };
        const again = settle(base);
        if (again.pending) throw Object.assign(new Error('temporada sin cargar'), { what: `la temporada ${seasonLabel(again.route.params.s)}` });
        // Con la temporada ya cargada, sus perezosas (un grupo que no está): otra vuelta, que las pide.
        const more = lazyWant(again, base).filter((w) => !tried.has(triedKey(w.cat, w.season)));
        if (more.length) {
          if (depth >= MAX_REDIRECTS) throw new RangeError('Demasiadas redirecciones');
          return run(mode, notice || again.notice, depth + 1, target, focusId, tried);
        }
        if (again.lazy.length) throw Object.assign(new Error(`${again.lazy[0].cat} sin cargar`), { what: CAT_WORDS[again.lazy[0].cat] });
        if (routeHref(again.route.screen, again.route.params) !== routeHref(route.screen, route.params)) {
          if (depth >= MAX_REDIRECTS) throw new RangeError('Demasiadas redirecciones');
          return run(mode, notice || again.notice, depth + 1, target, focusId, tried);
        }
        settled = again;
        // La barra, otra vez con lo cargado: mi equipo alevín solo se resuelve con su alevín (y uno de
        // infantil, cadete o juvenil, con la suya), y su ficha
        // o un partido suyo, abiertos en frío, marcaban Explorar o Jornada en vez de Mi equipo.
        const loadedTab = activeTab(route, lastPrimary, routeIsMine(route, base.resolution));
        updateTabbar(loadedTab.active, loadedTab.current, doc, tabTargets(route, base));
      }
      // Lo que la pantalla quería de las perezosas y no llegó: solo puede ser lo `soft` (lo demás ya dio su
      // caja de error), que la pantalla pinta con su aviso y «Reintentar». lazyFailed, las categorías;
      // alevinFailed, el de antes (las pantallas de hoy lo leen).
      const lazyFailed = [...new Set(lazyWant(settled, base).filter((w) => w.soft).map((w) => w.cat))];
      const { lazyTried: _tried, ...data } = base;   // lazyTried es del router, no de las pantallas
      const ctx = { ...data, route, params: route.params, lastPrimary, backHref: backHref(route, base.model), lazyFailed, alevinFailed: lazyFailed.includes('alevin') };
      // Solo se pinta Html de html``, que escapa cada interpolación.
      const view = screen.render(ctx);
      if (!(view instanceof Html)) throw new TypeError(`render de ${screen.id} no devolvió Html`);
      paint(withNotice(String(view), notice));
      // Una pantalla con title(ctx) (la ficha del jugador: su nombre) pone el suyo; sin él, el de la ruta.
      const named = typeof screen.title === 'function' ? screen.title(ctx) : null;
      if (named) doc.title = `${named} · ${baseTitle}`;
      if (Object.hasOwn(PRIMARY, route.screen)) rememberPrimary(PRIMARY[route.screen]);
      if (screen.mount) {
        // Si el mount navega (nav.go, nav.replace, saveMyTeam…) de forma síncrona, la navegación
        // anidada corre con el `target`/`focusId` de ESTA (nesting): «arriba al avanzar» no se
        // pierde por el scrollY de antes de este push.
        nesting.push({ target, focusId });
        let done;
        try {
          done = screen.mount(root, ctx, navFor(my));
        } catch (err) {
          // Un mount que lanza deja la pantalla pintada: sus
          // enlaces los atiende igual el router por delegación; la caja de error es solo de needs y render.
          console.error('[router] mount', err);
        } finally {
          nesting.pop();
        }
        if (my !== token) {
          // El mount ya navegó: su pantalla no está en el DOM. Si además devolvió una limpieza, se
          // llama ya mismo (nunca se guarda en `cleanup`, que ya es la de la navegación anidada) y
          // esa navegación manda la suya; idle() la espera encadenando en `latest` (hallazgo 1).
          if (typeof done === 'function') {
            try { done(); } catch (err) { console.error('[router] limpieza', err); }
          }
          return latest;
        }
        if (typeof done === 'function') cleanup = done;
      }
      place(mode, target, focusId);
    } catch (err) {
      if (my !== token) return latest;
      console.error('[router]', err);
      // El «‹» de la caja se calcula aparte. Con una temporada mal formada, parentOf de Partido vuelve
      // a tocarla (findGroup) y lanzaría aquí dentro: idle() rechazaría y se quedaría el esqueleto, sin
      // «Reintentar». Entonces, el padre sin modelo: la jornada del enlace.
      let back = null;
      try { back = backHref(route, base?.model); } catch { back = backHref(route, null); }
      paint(errorScreen({ screenId: screen?.id || route.screen || 'home', title: routeTitle(route.screen), what: loadWhat(err), back }));
      place(mode, 0, null);
    }
  }

  // Ir a un href de la app: pushState o replaceState según historyMode (o `forced`). clickedId: el
  // id del enlace pulsado (onClick), para el foco al cambiar de jornada o de vista.
  function navigate(href, forced = null, clickedId = null) {
    let mode = forced;
    if (!mode) {
      try {
        const target = parseRoute(href);
        const res = resolveParams(target, getContext());
        mode = historyMode(current, { screen: target.screen, params: res.params || target.params });
      } catch {
        mode = 'push';
      }
    }
    if (mode === 'replace') hist.replaceState(hist.state, '', href);
    else hist.pushState({ fbIdx: (entry()?.fbIdx ?? 0) + 1, fbKey: newKey() }, '', href);
    return show(mode, null, clickedId);
  }

  // «‹»: la entrada anterior si es de la app; si no, el padre. hist.back() dispara popstate más
  // tarde, nunca en este turno, así que el pintado real llega por onLocation: se deja un pendiente y
  // se resuelve desde allí, para que idle() y el propio nav.back() esperen al de la vuelta, no al de
  // la pantalla que ya estaba pintada. Dos nav.back()
  // seguidos, cada uno con su history.back(), encadenan sus pendientes en vez de pisarse, y el
  // primer popstate que atiende onLocation los resuelve todos con su pintado. En un navegador real
  // pueden llegar dos popstate, a entradas distintas (el segundo pinta sin pendiente que resolver);
  // en el navegador falso de las pruebas llegan a la misma entrada y onLocation descarta el segundo.
  // Sin encadenar, el pendiente del primero se perdería y su promesa se quedaría colgada para siempre.
  // El «‹» del DOM también pasa por aquí: idle() espera su vuelta, como la de nav.back().
  function goBack() {
    if ((entry()?.fbIdx ?? 0) > 0) {
      const earlier = pendingBack;
      latest = new Promise((resolve) => {
        pendingBack = earlier ? (value) => { earlier(value); resolve(value); } : resolve;
      });
      hist.back();
      return latest;
    }
    let model = null;
    try { model = getContext().model; } catch { /* sin contexto: el padre que dice el enlace */ }
    const parent = current ? parentOf(current, model) : null;
    return navigate(parent ? routeHref(parent.screen, parent.params) : '#/', 'push');
  }

  // Atrás, Adelante o un hash escrito a mano. popstate y hashchange llegan juntos: se atiende uno.
  function onLocation() {
    const st = entry();
    if (st && st.fbKey === seen.key && win.location.hash === seen.hash) return;
    if (!st) stamp(seen.idx + 1);   // entrada nueva del navegador, detrás de la última atendida
    const resolveBack = pendingBack;
    pendingBack = null;
    const painted = show('pop');
    if (resolveBack) painted.then(resolveBack, resolveBack);
  }

  // Delegación en el documento: enlaces #/… (con su modo de historial), «‹», Reintentar y
  // anclas internas como «Saltar al contenido», que nunca cambian la ruta.
  function onClick(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const el = event.target && event.target.closest ? event.target.closest('a[href],[data-action]') : null;
    if (!el) return;
    const action = el.getAttribute('data-action');
    if (action === 'retry') {
      event.preventDefault();
      show('refresh');
      return;
    }
    if (action === 'back' && (entry()?.fbIdx ?? 0) > 0) {
      event.preventDefault();
      goBack();
      return;
    }
    if (el.tagName !== 'A' || el.hasAttribute('download')) return;
    const target = el.getAttribute('target');
    if (target && target !== '_self') return;
    const href = el.getAttribute('href') || '';
    if (href.startsWith('#/')) {
      event.preventDefault();
      navigate(href, null, el.id || null);
    } else if (href.length > 1 && href.startsWith('#')) {
      // Un ancla interna nunca cambia la ruta: se previene siempre, exista o no su destino. Si no, un
      // hash sin ruta («#calendario») lo trataría el navegador y acabaría en Mi equipo, con una entrada
      // nueva. El destino va arriba de la ventana, como el ancla de una ruta en place(), y se lleva el
      // foco sin desplazar: un focus() a secas centra lo que no cabe, y en un móvil el calendario de
      // Mi equipo, más alto que la pantalla, quedaría con su título y su .ics por encima de la vista.
      event.preventDefault();
      const dest = doc.getElementById(decode(href.slice(1)));
      if (!dest) return;
      if (!dest.hasAttribute('tabindex')) dest.setAttribute('tabindex', '-1');
      dest.focus({ preventScroll: true });
      dest.scrollIntoView({ block: 'start' });
    }
  }

  // La ruta actual con otros parámetros (completos), con replaceState y sin pintar: los buscadores
  // de Explorar y Goleadores apuntan su `q` al escribir sin perder el cursor. La
  // entrada conserva su { fbIdx, fbKey } (y con ellos su desplazamiento guardado y el «‹») y su
  // ancla (#buscar); `current` pasa a ser la ruta nueva, resuelta como en navigate, para que la
  // navegación siguiente compare con ella. No toca el foco ni el desplazamiento. Devuelve false si
  // no hay ruta o si el navegador se niega: Safari lanza si pasan de 100 en pocos segundos.
  function update(params) {
    if (!current) return false;
    const hash = win.location.hash;
    const at = hash.indexOf('#', 1);
    const href = routeHref(current.screen, params) + (at > 0 ? hash.slice(at) : '');
    const target = parseRoute(href);
    let resolved = null;
    try { resolved = resolveParams(target, getContext()).params || null; } catch { resolved = null; }
    try {
      hist.replaceState(hist.state, '', href);
    } catch {
      return false;
    }
    current = { screen: target.screen, params: resolved || target.params };
    seen = { ...seen, hash: win.location.hash };
    return true;
  }

  const nav = {
    go: (screen, params) => navigate(routeHref(screen, params)),
    replace: (screen, params) => navigate(routeHref(screen, params), 'replace'),
    back: goBack,
    retry: () => show('refresh'),
    // «Hacer mi equipo» y la respuesta a E: lo guarda app.js y se vuelve a pintar la ruta.
    saveMyTeam(myTeam) {
      const saved = actions.saveMyTeam ? actions.saveMyTeam(myTeam) : false;
      show('refresh');
      return saved;
    },
    update,
    // «Seguir a este jugador»: lo guarda app.js y se vuelve a pintar la ruta (el botón cambia).
    toggleFollow(player) {
      const saved = actions.toggleFollow ? actions.toggleFollow(player) : false;
      show('refresh');
      return saved;
    },
    // «Vistos hace poco»: Equipo apunta su ficha en su mount; lo guarda app.js,
    // sin volver a pintar. Devuelve si quedó guardado en el almacén (false: solo en memoria).
    addRecent(entry) {
      return actions.addRecent ? actions.addRecent(entry) : false;
    },
    // «Borrar datos de esta app» (Ajustes): lo borra app.js y se abre Mi equipo,
    // con una entrada nueva.
    clearData() {
      if (actions.clearData) actions.clearData();
      return navigate('#/', 'push');
    },
  };

  // El nav que recibe cada mount: el de arriba, con su update ligado a esa navegación. Un update que
  // llega cuando ya empezó otra (el temporizador de una pantalla anterior, que ningún buscador usa hoy)
  // no reescribe la ruta nueva: devuelve false sin tocar nada.
  const navFor = (my) => ({ ...nav, update: (params) => my === token && update(params) });

  if ('scrollRestoration' in hist) hist.scrollRestoration = 'manual';
  win.addEventListener('popstate', onLocation);
  win.addEventListener('hashchange', onLocation);
  win.addEventListener('scroll', () => {
    const st = entry();
    if (st) positions.set(st.fbKey, win.scrollY);
  }, { passive: true });
  doc.addEventListener('click', onClick);
  if (!entry()) stamp(0);
  show('initial');
  return { nav, idle: () => latest, current: () => current };
}
