// Ficha de un jugador, `#/jugador?id` (la clave de su ficha, docs/identidad.md: el mismo niño de
// prebenjamín a benjamín y de una temporada a otra, con o sin id de la federación): su año de nacimiento
// (estimado, salvo que sea seguro), un resumen por categoría, su trayectoria según
// las actas, de la temporada más reciente a la más antigua (equipo, grupo, partidos, de titular, goles y
// tarjetas; la fila que llegó por una unión dice por qué), la liga de escuelas si está enlazada con MyGol,
// las otras fichas con su mismo nombre y
// «Seguir», que lo pone en Mi equipo. Los datos son el trozo de su clave de data-jugadores-<k>.js
// (ensureJugadores); una clave que es alias de otra ficha («a» de su trozo) abre esa, sin cambiar la URL.
// La ficha no depende de ninguna temporada cargada. render(ctx) es pura; mount pone «Seguir».
import { html } from './html.js';
import { block, box, countLabel, decimal, empty, notice, screenHead } from './ui.js';
import { bornText, categoryName, groupLabel, playerName, seasonLabel } from './model.js';
import { playerHref, routeHref, teamHref } from './links.js';
import { errorBox } from './shell.js';
import { ensureJugadores, jugadoresShard } from './state.js';
import { isFollowed } from './followed.js';

// La clave de la ficha a la que lleva un alias, según el trozo del alias; null si no es alias.
const aliasOf = (shard, id) => (shard && !(shard.p && shard.p[id]) && shard.a && shard.a[id]) || null;

// El jugador de la ruta: { id, key, shard, player }; key es la clave de su ficha (la de la ruta o, si es
// un alias, la de su ficha) y shard, el trozo de key: undefined sin pedir y null si falló.
function locate(ctx) {
  const id = ctx.params?.id || null;
  if (!id) return { id: null, key: null, shard: undefined, player: null };
  const all = ctx.datasets?.jugadores || {};
  const own = all[jugadoresShard(id)];
  const key = aliasOf(own, id) || id;
  const shard = key === id ? own : all[jugadoresShard(key)];
  return { id, key, shard, player: (shard && shard.p && shard.p[key]) || null };
}

// El seguido de esta ficha: el de su clave, el de la ruta o el de alguno de sus alias (un seguido guardado
// con una clave que hoy es alias); null si no se sigue.
function followedId(ctx, { id, key, player }) {
  const list = Array.isArray(ctx.followed) ? ctx.followed : [];
  const ids = [key, id, ...((player && player.al) || [])];
  return ids.find(k => isFollowed(list, k)) || null;
}

// Por qué una fila llegó a la ficha, si llegó por una unión (generate_js._MOTIVO). «e» no dice «otro
// identificador»: U0 también une una identidad sin id a la de su mismo equipo y temporada.
const UNION = { e: 'unido por nombre (mismo equipo y temporada)', c: 'unido por nombre (mismo club)', n: 'unido por nombre' };

// El nombre del grupo, como en el resto de la app (groupLabel), con lo que trae el trozo.
function where(shard, season, code) {
  const g = shard.g && shard.g[`${season}/${code}`];
  return g ? groupLabel({ id: code, cat: g[0], name: g[1], phase: g[2], island: g[3], season }) : code;
}

const sum = (rows, i) => rows.reduce((n, r) => n + (r[i] | 0), 0);

function stint(shard, row) {
  const [season, code, team, pj, tit, goals, yellow, red, united, why] = row;
  // Como la trayectoria del club: el equipo y su grupo a la izquierda; los goles y los partidos a la
  // derecha (cortos: caben a 320 px). De titular, las tarjetas y, al final, por qué se unió, con el grupo.
  const cards = [yellow ? countLabel(yellow, 'amarilla', 'amarillas') : '', red ? countLabel(red, 'roja', 'rojas') : ''];
  const union = united ? UNION[why] || UNION.n : '';
  const detail = [where(shard, season, code), tit ? `${tit} de titular` : '', ...cards, union].filter(Boolean).join(' · ');
  return html`<a class="traj-row" href="${teamHref(season, code, team)}"><span class="traj-team">${team}</span><span class="traj-group">${detail}</span><span class="traj-pos">${goals ? countLabel(goals, 'gol', 'goles') : 'sin goles'}</span><span class="traj-pts">${countLabel(pj, 'partido', 'partidos')}</span></a>`;
}

// El título de una temporada con sus totales, de todas sus filas (también las unidas, como la cabecera):
// «2025/26 · 22 partidos · 31 goles».
function seasonHead(season, rows) {
  return [seasonLabel(season), countLabel(sum(rows, 3), 'partido', 'partidos'), countLabel(sum(rows, 5), 'gol', 'goles')].join(' · ');
}

function career(shard, player) {
  const seasons = [...new Set(player.c.map(r => r[0]))].sort().reverse();
  return seasons.map((season) => {
    const rows = player.c.filter(r => r[0] === season);
    return html`<h3 class="traj-season">${seasonHead(season, rows)}</h3><div class="box">${rows.map(r => stint(shard, r))}</div>`;
  });
}

// «Nacido en 2018 (estimado)», «Nacido en 2018 o 2019 (estimado)», «Nacido entre 2008 y 2010 (estimado)» o,
// si el año es seguro ("yc"), «Nacido en 2018»; '' sin "y" (ninguna categoría que el estimador conozca).
export function birthLabel(player) {
  const text = bornText(player && player.y, Boolean(player && player.yc));
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

// Las categorías del resumen, de la más alta a la más baja; una que no está aquí va detrás, y lo que el
// trozo no nombra (un grupo sin "g"), al final, en «Otras».
const CAT_ORDER = ['juvenil', 'cadete', 'infantil', 'alevin', 'benjamin', 'prebenjamin'];

// «Ver los mejores de 2018», al ranking de su año (#/ranking?y=2018): uno por año posible, porque el
// estimado sale en el de cada uno; sin año, nada.
function rankingLinks(player) {
  const years = (Array.isArray(player.y) ? player.y : []).map(Number).filter(Number.isInteger).sort((a, b) => a - b);
  if (!years.length) return '';
  const links = years.map(y => html`<a class="more" href="${routeHref('ranking', { y: String(y) })}">Ver los mejores de ${y}</a>`);
  return html`<p class="squad-more">${links.map((link, i) => html`${i ? ' · ' : ''}${link}`)}</p>`;
}

/* «Resumen»: una fila por categoría jugada (su nombre, temporadas, partidos, goles y goles por partido con
 * un decimal), de la más alta a la más baja, y los enlaces al ranking de su año. Con las filas de un solo
 * grupo no dice nada que no diga ya la trayectoria: no se pinta (y los enlaces van bajo la trayectoria).
 * Las filas, las de la trayectoria (traj-row), sin enlace. */
function summary(shard, player) {
  const groups = new Set(player.c.map(r => `${r[0]}/${r[1]}`));
  if (groups.size < 2) return '';
  const byCat = new Map();
  for (const row of player.c) {
    const g = shard.g && shard.g[`${row[0]}/${row[1]}`];
    const cat = g && g[0] ? String(g[0]) : null;
    if (!byCat.has(cat)) byCat.set(cat, []);
    byCat.get(cat).push(row);
  }
  const rank = (cat) => (cat === null ? CAT_ORDER.length + 1 : CAT_ORDER.includes(cat) ? CAT_ORDER.indexOf(cat) : CAT_ORDER.length);
  const cats = [...byCat.keys()].sort((a, b) => rank(a) - rank(b) || String(a).localeCompare(String(b)));
  const rows = cats.map((cat) => {
    const list = byCat.get(cat);
    const pj = sum(list, 3);
    const goals = sum(list, 5);
    const seasons = new Set(list.map(r => r[0])).size;
    const rate = pj ? decimal(goals / pj, 1) : '–';
    return html`<div class="traj-row"><span class="traj-team">${cat === null ? 'Otras' : categoryName(cat)}</span><span class="traj-group">${countLabel(seasons, 'temporada', 'temporadas')} · ${rate} goles por partido</span><span class="traj-pos">${goals ? countLabel(goals, 'gol', 'goles') : 'sin goles'}</span><span class="traj-pts">${countLabel(pj, 'partido', 'partidos')}</span></div>`;
  });
  return block('Resumen', html`${box(html`${rows}`)}${rankingLinks(player)}`, { context: 'por categoría' });
}

// «Liga de escuelas»: las temporadas de MyGol de una ficha enlazada ("e": [[temporada, equipo, categoría,
// jornadas jugadas]], en orden de temporada y de equipo; generate_js._escuela), de la más reciente a la más
// antigua y, dentro de una temporada, en el orden del trozo. El enlace es por el nombre y los dos apellidos
// (docs/mygol.md): se dice siempre. Las filas no son enlaces (la web no tiene páginas de la liga de
// escuelas); sin jornadas jugadas apuntadas, «en la plantilla». Sin "e", nada.
function school(player) {
  const rows = Array.isArray(player.e) ? player.e.filter(r => Array.isArray(r) && r.length >= 4) : [];
  if (!rows.length) return '';
  const recent = rows.map((r, i) => [r, i]).sort((a, b) => String(b[0][0]).localeCompare(String(a[0][0])) || a[1] - b[1]).map(([r]) => r);
  const line = ([season, team, cat, played]) => {
    const where = [cat ? categoryName(cat) : '', seasonLabel(season)].filter(Boolean).join(' · ');
    const n = Number(played) | 0;
    return html`<div class="traj-row"><span class="traj-team">${team}</span><span class="traj-group">${where}</span><span class="traj-pts">${n ? countLabel(n, 'jornada', 'jornadas') : 'en la plantilla'}</span></div>`;
  };
  return block('Liga de escuelas', box(html`${recent.map(line)}`), { context: 'enlazado por el nombre y los dos apellidos' });
}

// Las otras fichas con el mismo nombre ("h": [[clave, último equipo, temporada]]), cada una a la suya.
function namesakes(player) {
  const list = Array.isArray(player.h) ? player.h.filter(([key]) => playerHref(key)) : [];
  if (!list.length) return '';
  return block('Otras fichas con este mismo nombre', box(html`${list.map(([key, team, season]) => html`<a class="traj-row" href="${playerHref(key)}"><span class="traj-team">${team}</span><span class="traj-group">${seasonLabel(season)}</span></a>`)}`));
}

const wrap = (content) => html`<section data-screen="jugador">${content}</section>`;

function render(ctx) {
  const located = locate(ctx);
  const { id, shard, player } = located;
  const head = (title, opts = {}) => screenHead(title, { back: ctx.backHref, ...opts });
  if (!id) return wrap(html`${head('Jugador')}${block(null, empty('Abre la ficha de un jugador desde la plantilla de un equipo o desde un partido.'))}`);
  if (shard === null) return wrap(html`${head('Jugador')}${errorBox('la ficha del jugador')}`);
  if (!player) return wrap(html`${head('Jugador')}${block(null, empty('No encontramos a ese jugador en las actas de la federación.'))}`);
  const seasons = new Set(player.c.map(r => r[0])).size;
  const sub = [birthLabel(player), countLabel(seasons, 'temporada', 'temporadas'), countLabel(sum(player.c, 3), 'partido', 'partidos'),
    countLabel(sum(player.c, 5), 'gol', 'goles')].filter(Boolean).join(' · ');
  const following = followedId(ctx, located) !== null;
  const action = html`<button type="button" class="screen-action" data-action="seguir-jugador" aria-pressed="${following ? 'true' : 'false'}">${following ? 'Siguiendo' : 'Seguir'}</button>`;
  // Sin ningún id de la federación, la ficha es la de su nombre en sus actas: se dice.
  const only = player.s ? notice(null, 'En las actas figura solo con este nombre.') : '';
  const resumen = summary(shard, player);
  const below = resumen ? '' : rankingLinks(player);
  return wrap(html`${head(playerName(player.n), { sub, action })}${resumen}${block('Trayectoria', html`${career(shard, player)}${only}${below}`, { context: 'según las actas de la federación' })}${school(player)}${namesakes(player)}`);
}

function mount(root, ctx, nav) {
  const located = locate(ctx);
  const { player, key } = located;
  if (!player) return undefined;
  const section = root.matches && root.matches('[data-screen="jugador"]') ? root : root.querySelector('[data-screen="jugador"]');
  if (!section) return undefined;
  // La escucha va en la sección, que se sustituye en cada pintado: nunca se acumula. Lo guarda app.js
  // y el router vuelve a pintar la ficha, con el botón cambiado.
  section.addEventListener('click', (event) => {
    const target = event.target.closest('[data-action="seguir-jugador"]');
    if (!target || !section.contains(target)) return;
    // Dejar de seguir quita el seguido que hay (quizá un alias); seguir, sigue la clave de la ficha.
    if (nav && typeof nav.toggleFollow === 'function') nav.toggleFollow({ id: followedId(ctx, located) || key, n: player.n });
  });
  return undefined;
}

// Los jugadores seguidos, en Mi equipo: cada uno con el enlace a su ficha, el último seguido primero.
export function followedBlock(ctx) {
  const list = Array.isArray(ctx.followed) ? ctx.followed : [];
  if (!list.length) return '';
  return block('Jugadores que sigues', box(html`${list.map(p => html`<a class="traj-row" href="${playerHref(p.id)}"><span class="traj-team">${playerName(p.n)}</span><span class="traj-group">Ver su trayectoria</span></a>`)}`));
}

export const screen = {
  id: 'jugador',
  // El trozo de data-jugadores-<k>.js de su clave y, si es un alias, después el de la ficha a la que lleva:
  // undefined sin pedir y null si falló, que la ficha dice con su caja de error y se vuelve a pedir con
  // «Reintentar» o en la visita siguiente. Nunca rechaza.
  needs: (params, datasets) => {
    const id = params && params.id;
    if (!id || jugadoresShard(id) === null) return [];
    if (!datasets.jugadores) datasets.jugadores = {};
    const load = (k) => ensureJugadores(k).then((data) => { datasets.jugadores[k] = data; return data; });
    const follow = (data) => {
      const key = aliasOf(data, id);
      const k = key ? jugadoresShard(key) : null;
      return k !== null && !datasets.jugadores[k] ? load(k) : undefined;
    };
    const k = jugadoresShard(id);
    if (!datasets.jugadores[k]) return [load(k).then(follow)];
    const next = follow(datasets.jugadores[k]);
    return next ? [next] : [];
  },
  render,
  mount,
  // El título de la pestaña: el nombre del jugador (el router le añade el del sitio); sin él, null.
  title: (ctx) => { const { player } = locate(ctx); return player ? playerName(player.n) : null; },
};
