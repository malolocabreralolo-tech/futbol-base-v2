// Pantalla Explorar: el selector de temporada, el buscador de equipos y de jugadores, «Vistos hace poco»,
// las ligas por categoría, las copas y los torneos, y «Más». Es un destino principal. render(ctx) es pura y
// pinta los resultados de la `q` de la dirección (un enlace directo, Atrás o una recarga); mount filtra al
// escribir con la misma función (searchView), repinta solo la lista y apunta la búsqueda con nav.update,
// sin volver a pintar la pantalla: el cursor no salta y Atrás no recorre cada letra. La temporada de la
// ruta la carga el router; el foco del ancla #buscar lo pone el router, nunca mount. Los jugadores salen
// del índice de búsqueda (data-buscar-<xy>.js), perezoso: lo pide needs con la `q` de la dirección y
// mount al escribir.
import { html } from './html.js';
import { screenHead, block, countLabel, crest, empty, notice, searchBox, seasonPicker, linkRow, listEs } from './ui.js';
import { alevinFailedBox, errorBox } from './shell.js';
import {
  CATEGORIES, CAT_NAMES, CAT_SHORT, bornText, competitionKey, competitions, findGroup, groupSummary, playerName,
  playerSearchPrefix, searchKey, searchPlayers, searchTeams, seasonLabel,
} from './model.js';
import { canaryDateTime, dayMonth, monthName, playerHref, routeHref, teamHref } from './links.js';
import { ensureBuscar, healthNeeds } from './state.js';

const PICKER_ID = 'temporada';
const shieldsOf = ctx => (ctx.datasets && ctx.datasets.shields) || {};
const seasonOf = ctx => (ctx.params && ctx.params.s) || ctx.portal.season;

// ── Buscador ────────────────────────────────────────────────────────────

function resultRow(entry, { cup, shields }) {
  const { name, group } = entry;
  // Liga: la ficha del equipo. Copa o torneo: su cuadro o su liguilla.
  const href = cup ? routeHref('copa', { s: group.season, g: group.id }) : teamHref(group.season, group.id, name);
  return html`<li><a class="search-result" href="${href}">${crest(name, { size: 32, shields })}<span class="search-result-text"><span class="search-result-name">${name}</span><span class="search-result-label">${group.label}</span></span></a></li>`;
}

// Los jugadores de una búsqueda que se pintan; los demás, en una línea que pide escribir más.
export const PLAYER_LIMIT = 30;
const PLAYERS_FAILED = 'No hemos podido cargar los jugadores.';

/* Los jugadores de `text`, del trozo del índice de su prefijo (ctx.datasets.buscar: { <prefijo>: entradas
 * | null }, sin la clave mientras no ha llegado): { state, total, list }. state: 'none' (la búsqueda no
 * tiene ninguna palabra que cuente: «de la»), 'loading', 'failed' (null: no llegó) u 'ok'. Los jugadores
 * no dependen de la temporada elegida: el índice es de todas. */
function playersOf(ctx, text) {
  const prefix = playerSearchPrefix(text);
  if (!prefix) return { state: 'none', total: 0, list: [] };
  const buscar = (ctx.datasets && ctx.datasets.buscar) || {};
  if (!Object.hasOwn(buscar, prefix)) return { state: 'loading', total: 0, list: [] };
  if (!Array.isArray(buscar[prefix])) return { state: 'failed', total: 0, list: [] };
  return { state: 'ok', ...searchPlayers(buscar[prefix], text, PLAYER_LIMIT) };
}

// Un jugador: a su ficha, con su nombre y, debajo, su último equipo, esa temporada y su año de nacimiento
// (el índice no dice si es seguro: siempre «(estimado)»; sin año, nada).
function playerRow(player) {
  const href = playerHref(player.id);
  if (!href) return '';
  const detail = [player.team, player.season ? seasonLabel(player.season) : '', bornText(player.years)].filter(Boolean).join(' · ');
  return html`<li><a class="search-result" href="${href}"><span class="search-result-text"><span class="search-result-name">${playerName(player.name)}</span><span class="search-result-label">${detail}</span></span></a></li>`;
}

// El bloque «Jugadores»: buscándolos, el aviso de que no llegaron (con «Reintentar», que atiende mount),
// o la lista; sin ninguno, no sale (los equipos ya lo dicen, o el vacío de searchView).
function playersBlock(players) {
  if (players.state === 'loading') return block('Jugadores', notice(null, 'Buscando jugadores…'));
  if (players.state === 'failed') {
    return block('Jugadores', html`<div class="box" role="alert"><p class="error-text">${PLAYERS_FAILED}</p><div class="buttons"><button class="button is-main" type="button" data-action="reintentar-jugadores">Reintentar</button></div></div>`);
  }
  if (!players.total) return '';
  const more = players.total > players.list.length ? notice(null, `y ${players.total - players.list.length} más: escribe más letras`) : '';
  return block('Jugadores', html`<ul class="box search-list">${players.list.map(playerRow)}</ul>${more}`,
    { context: countLabel(players.total, 'jugador', 'jugadores') });
}

// La frase de la región de estado: «3 equipos y 12 jugadores encontrados», «1 jugador encontrado»…;
// mientras llegan los jugadores, la de los equipos (o «Buscando jugadores…» sin ninguno) y, si no llegaron,
// también lo dice.
function statusText(teams, players) {
  const found = players.state === 'ok' ? players.total : 0;
  let text = teams && found ? `${countLabel(teams, 'equipo', 'equipos')} y ${countLabel(found, 'jugador', 'jugadores')} encontrados`
    : teams ? countLabel(teams, 'equipo encontrado', 'equipos encontrados')
      : found ? countLabel(found, 'jugador encontrado', 'jugadores encontrados') : '';
  if (players.state === 'loading' && !text) text = 'Buscando jugadores…';
  if (players.state === 'failed') text = text ? `${text}. ${PLAYERS_FAILED}` : PLAYERS_FAILED;
  return text;
}

/* Los resultados de `q`: los equipos de la temporada de la ruta y, detrás, los jugadores de todas. La
 * lista (Html) y la frase de la región de estado, que dice cuántos hay a los lectores de pantalla mientras
 * se escribe. Sin búsqueda, nada; con menos de 2 letras, un aviso; sin equipos ni jugadores (con el índice
 * ya llegado), un vacío que lo dice, sin la temporada, que no vale para los jugadores. La usan render (la q
 * de la dirección) y mount (lo que se escribe, y otra vez cuando llega el índice): el mismo resultado por
 * los dos caminos. */
export function searchView(ctx, q) {
  const text = String(q ?? '');
  if (!text.trim()) return { list: html``, status: '' };
  const s = seasonOf(ctx);
  if (searchKey(text).length < 2) {
    const hint = 'Escribe al menos 2 letras del nombre del equipo o del jugador.';
    return { list: notice(null, hint), status: hint };
  }
  const { leagues, cups } = searchTeams(ctx.model, s, text);
  const total = leagues.length + cups.length;
  const players = playersOf(ctx, text);
  if (!total && (players.state === 'none' || (players.state === 'ok' && !players.total))) {
    const none = `No encontramos ningún equipo ni ningún jugador con «${text.trim()}».`;
    return { list: empty(none), status: none };
  }
  const shields = shieldsOf(ctx);
  const list = (entries, cup) => html`<ul class="box search-list">${entries.map(entry => resultRow(entry, { cup, shields }))}</ul>`;
  return {
    list: html`${leagues.length ? block('Resultados', list(leagues, false), { context: countLabel(leagues.length, 'equipo', 'equipos') }) : ''}${cups.length ? block('En copas y torneos', list(cups, true), { context: countLabel(cups.length, 'equipo', 'equipos') }) : ''}${playersBlock(players)}`,
    status: statusText(total, players),
  };
}

// Pide el trozo del índice de `prefix` y lo deja en datasets.buscar (null si no llegó). Nunca rechaza.
function loadBuscar(prefix, datasets) {
  return ensureBuscar(prefix).then((entries) => { (datasets.buscar ||= {})[prefix] = entries; });
}

// ── Vistos hace poco ────────────────────────────────────────────────────

/* Una ficha vista (ctx.recent: [{ s, g, t }], la más reciente primero). Su grupo sale del modelo si
 * su temporada está cargada, o de los torneos (los MC* que trae la importación de v1): así se sabe su
 * categoría y si es de liga. Un grupo que no es de liga abre su cuadro o su liguilla (#/copa). Con la
 * temporada sin cargar, abre la ficha igual (el router carga la temporada y valida el grupo) y enseña la
 * temporada en lugar de la categoría, que no se sabe sin cargarla. */
function recentChip(ctx, entry, shields) {
  const group = findGroup(ctx.model, entry.s, entry.g);
  const href = group && group.kind !== 'league' ? routeHref('copa', { s: entry.s, g: entry.g }) : teamHref(entry.s, entry.g, entry.t);
  const cat = group ? html`<abbr title="${CAT_NAMES[group.cat]}">${CAT_SHORT[group.cat]}</abbr>` : '';
  const season = entry.s !== ctx.portal.season ? seasonLabel(entry.s) : '';
  const meta = cat && season ? html`${cat} · ${season}` : cat || season;
  return html`<li><a class="recent-chip" href="${href}">${crest(entry.t, { shields })}<span class="recent-name">${entry.t}</span>${meta ? html`<span class="recent-meta">${meta}</span>` : ''}</a></li>`;
}

// Sin fichas vistas, el bloque no sale (la primera visita no enseña un vacío).
function recentBlock(ctx) {
  const recent = Array.isArray(ctx.recent) ? ctx.recent : [];
  if (!recent.length) return '';
  const shields = shieldsOf(ctx);
  return block('Vistos hace poco', html`<ul class="recent">${recent.map(entry => recentChip(ctx, entry, shields))}</ul>`);
}

// ── Ligas, copas y torneos ──────────────────────────────────────────────

// Ligas: por categoría, una fila por competición con su recuento de grupos, que abre
// #/ligas?s&c&f. El contexto del bloque es el total de grupos de liga de la temporada.
function leaguesBlock(ctx, s) {
  const leagues = competitions(ctx.model, s).filter(c => c.kind === 'liga');
  if (!leagues.length) return block('Ligas', empty(`No hay ligas en la temporada ${seasonLabel(s)}.`));
  const total = leagues.reduce((n, c) => n + c.groups.length, 0);
  const cats = CATEGORIES.map(cat => [cat, leagues.filter(c => c.cat === cat)]).filter(([, list]) => list.length);
  return block('Ligas', html`<div class="box">${cats.map(([cat, list]) => html`<h3 class="link-head">${CAT_NAMES[cat]}</h3><ul class="link-list">${list.map(c => html`<li>${linkRow(routeHref('ligas', { s, c: cat, f: c.key }), c.label, { context: countLabel(c.groups.length, 'grupo', 'grupos') })}</li>`)}</ul>`)}</div>`,
    { context: countLabel(total, 'grupo', 'grupos') });
}

// Los meses de un torneo («junio», «junio y julio»), de las fechas de sus partidos.
function monthsOf(groups) {
  const days = groups.flatMap(g => g.rounds.flatMap(r => r.matches.map(m => m.dateISO))).filter(Boolean).sort();
  const names = [...new Set(days.map(monthName))];
  return names.length ? listEs(names) : null;
}

/* Copas y torneos: una fila por competición, con las dos categorías juntas,
 * que abre #/ligas?s&f sin `c` (Ligas lista las dos). La Copa de Campeones enseña sus campeones; un
 * torneo, sus meses; una copa insular, sus grupos. Sin copas en la temporada, el bloque no sale. */
function cupsBlock(ctx, s) {
  const byKey = new Map();
  for (const c of competitions(ctx.model, s).filter(entry => entry.kind === 'copa')) {
    const row = byKey.get(c.key) || { key: c.key, label: c.label, groups: [] };
    row.groups.push(...c.groups);
    byKey.set(c.key, row);
  }
  if (!byKey.size) return '';
  const rows = [...byKey.values()].map(({ key, label, groups }) => {
    const href = routeHref('ligas', { s, f: key });
    const { cup } = competitionKey(groups[0], s);
    const champions = groups.map(g => groupSummary(g).champion).filter(Boolean);
    if (cup === 'campeones' && champions.length) {
      const context = champions.length === groups.length ? countLabel(champions.length, 'campeón', 'campeones') : countLabel(groups.length, 'grupo', 'grupos');
      return linkRow(href, label, { context, detail: listEs(champions) });
    }
    if (cup === 'maspalomas') return linkRow(href, label, { context: monthsOf(groups) });
    return linkRow(href, label, { context: countLabel(groups.length, 'grupo', 'grupos') });
  });
  return block('Copas y torneos', html`<ul class="box link-list">${rows.map(row => html`<li>${row}</li>`)}</ul>`);
}

// ── Más ─────────────────────────────────────────────────────────────────

// «comprobado hoy» o «comprobado el 23 sept», de data-health.json (nunca «ahora»).
function checkedText(health, today) {
  const at = canaryDateTime(health && health.checkedAt);
  if (!at) return null;
  return at.day === today ? 'comprobado hoy' : `comprobado el ${dayMonth(at.day)}`;
}

// Más: Temporadas anteriores, Récords, Goleadores, los mejores de cada año, Datos y fuentes y Ajustes.
// Récords y Goleadores llevan la temporada elegida; el ranking no depende de ella.
function moreBlock(ctx, s) {
  const seasons = (ctx.datasets && ctx.datasets.seasons) || [];
  const oldest = seasons.length > 1 ? seasons[seasons.length - 1].name : null;
  const rows = [
    linkRow(routeHref('temporadas'), 'Temporadas anteriores', { context: oldest ? `desde ${seasonLabel(oldest)}` : null }),
    linkRow(routeHref('records', { s }), 'Récords y estadísticas'),
    linkRow(routeHref('goleadores', { s }), 'Goleadores'),
    linkRow(routeHref('ranking'), 'Los mejores de cada año', { context: 'por año de nacimiento' }),
    linkRow(routeHref('fuentes'), 'Datos y fuentes', { context: checkedText(ctx.health, ctx.today) }),
    linkRow(routeHref('ajustes'), 'Ajustes', { context: 'mi equipo y datos' }),
  ];
  return block('Más', html`<ul class="box link-list">${rows.map(row => html`<li>${row}</li>`)}</ul>`);
}

// ── Pantalla ────────────────────────────────────────────────────────────

function render(ctx) {
  const s = seasonOf(ctx);
  const seasons = (ctx.datasets && ctx.datasets.seasons && ctx.datasets.seasons.length) ? ctx.datasets.seasons : [{ name: ctx.portal.season }];
  const head = screenHead('Explorar', {
    sub: `Temporada ${seasonLabel(s)}`,
    action: seasonPicker(seasons, s, name => routeHref('explorar', { s: name }), { id: PICKER_ID }),
  });
  // La temporada de la ruta la carga el router; si aun así no está, la caja de
  // error con «Reintentar», nunca otra temporada.
  if (!ctx.model.season(s)) return html`<section data-screen="explorar">${head}${errorBox(`la temporada ${seasonLabel(s)}`)}</section>`;
  const { list, status } = searchView(ctx, ctx.params.q);
  // Sin los datos de alevín (el router no los pudo cargar): lo demás, con su aviso y «Reintentar».
  const partial = ctx.alevinFailed ? alevinFailedBox() : '';
  return html`<section data-screen="explorar">${head}${partial}${searchBox({ id: 'buscar', value: ctx.params.q || '', label: 'Buscar un equipo o un jugador' })}<p class="vh" role="status" id="buscar-estado">${status}</p><div class="search-results" id="resultados" data-results>${list}</div>${recentBlock(ctx)}${leaguesBlock(ctx, s)}${cupsBlock(ctx, s)}${moreBlock(ctx, s)}</section>`;
}

/* Al escribir: la lista (Html de html``, que escapa cada dato) y la región de estado con searchView, y
 * la búsqueda en la dirección con nav.update ({ s, q }, sin pintar: la entrada, su ancla y su
 * desplazamiento se quedan). Sin temporizadores: un update que llegara después de navegar reescribiría
 * la ruta nueva. Intro no envía el formulario. El botón de la cabecera abre y cierra la lista de
 * temporadas; Escape la cierra. Las escuchas van en elementos de la sección, que se sustituye en cada
 * pintado: nunca se acumulan.
 * Los jugadores: si lo escrito busca en un trozo del índice que no se ha pedido, se pide (uno por prefijo,
 * aunque se siga escribiendo) y, cuando llega, se repinta la lista solo si el cuadro sigue en la página y
 * lo que tiene escrito busca en ese mismo trozo (si ya busca en otro, su lista es otra). Un trozo que no
 * llegó (null) no se vuelve a pedir al escribir: para eso está «Reintentar». */
function mount(root, ctx, nav) {
  const input = root.querySelector('#buscar');
  const results = root.querySelector('#resultados');
  const status = root.querySelector('#buscar-estado');
  if (input && results) {
    const datasets = ctx.datasets || {};
    const asked = new Set();
    const paint = () => {
      const view = searchView(ctx, input.value);
      results.innerHTML = String(view.list);
      if (status) status.textContent = view.status;
    };
    const ask = (prefix) => {
      if (!prefix || asked.has(prefix) || (datasets.buscar && Object.hasOwn(datasets.buscar, prefix))) return;
      asked.add(prefix);
      loadBuscar(prefix, datasets).then(() => {
        asked.delete(prefix);
        if ((!root.contains || root.contains(input)) && playerSearchPrefix(input.value) === prefix) paint();
      });
    };
    input.addEventListener('input', () => {
      paint();
      ask(playerSearchPrefix(input.value));
      if (nav && typeof nav.update === 'function') nav.update({ ...ctx.params, q: input.value.trim() ? input.value : '' });
    });
    // «Reintentar» del bloque de jugadores: vuelve a «Buscando jugadores…» y pide otra vez su trozo.
    results.addEventListener('click', (event) => {
      const retry = event.target && event.target.closest ? event.target.closest('[data-action="reintentar-jugadores"]') : null;
      const prefix = playerSearchPrefix(input.value);
      if (!retry || !prefix) return;
      event.preventDefault();
      if (datasets.buscar) delete datasets.buscar[prefix];
      paint();
      ask(prefix);
    });
    if (input.form) input.form.addEventListener('submit', event => event.preventDefault());
  }
  const toggle = root.querySelector(`#${PICKER_ID}`);
  const menu = root.querySelector(`#${PICKER_ID}-lista`);
  if (toggle && menu) {
    const show = open => {
      toggle.setAttribute('aria-expanded', String(open));
      menu.hidden = !open;
    };
    const close = event => {
      if (event.key !== 'Escape' || menu.hidden) return;
      show(false);
      toggle.focus();
    };
    toggle.addEventListener('click', () => show(toggle.getAttribute('aria-expanded') !== 'true'));
    toggle.addEventListener('keydown', close);
    menu.addEventListener('keydown', close);
  }
}

export const screen = {
  id: 'explorar',
  // Todo sale de los datos inmediatos y de la temporada de la ruta, que carga el router.
  // data-health.json solo pone la fecha de «Datos y fuentes»: se pide como en la portada
  // (healthNeeds) y nunca rechaza; sin él, la fila va sin fecha. Con una `q` en la dirección (un enlace
  // directo, Atrás o una recarga), el trozo del índice de jugadores de su prefijo, si no está o si falló
  // (null), como la ficha del jugador; tampoco rechaza: si no llega, la lista lo dice.
  needs: (params, datasets) => {
    const loads = [];
    const health = healthNeeds(datasets);
    if (health) loads.push(health);
    const prefix = params && params.q ? playerSearchPrefix(params.q) : null;
    if (prefix && !(datasets.buscar && datasets.buscar[prefix])) loads.push(loadBuscar(prefix, datasets));
    return loads;
  },
  render,
  mount,
};
