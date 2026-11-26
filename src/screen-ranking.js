// Pantalla «Los mejores de cada año», `#/ranking?y&v`: los niños de un año de nacimiento, ordenados por el
// índice de scripts/ranking.py (los goles por partido frente a la media de su categoría, con el nivel de la
// liga y la edad; docs/ranking.md), esta temporada (v sin escribir) o en toda su trayectoria (v=h). La web
// no calcula nada: pinta data-ranking.js (qué años hay y cuántos niños tiene cada vista) y
// data-ranking-<año>.js (las dos listas del año), que pide needs, perezosos (la portada no los carga). Sin
// `y`, el año más reciente que tenga a alguien en la vista. Cuelga de Explorar («Más») y de la ficha del
// jugador («Ver los mejores de 2018»). render(ctx) es pura; mount solo desliza la fila de años al elegido.
import { html } from './html.js';
import { block, box, empty, notice, screenHead, scrollToCurrent, segmented } from './ui.js';
import { categoryName, playerName, seasonLabel } from './model.js';
import { playerHref, routeHref } from './links.js';
import { errorBox } from './shell.js';
import { ensureRanking, ensureRankingYear } from './state.js';

// Las dos vistas: la de esta temporada es la de por defecto y no se escribe en la dirección.
const VIEWS = [{ value: 't', label: 'Esta temporada' }, { value: 'h', label: 'Toda su trayectoria' }];
const SLOT = { t: 0, h: 1 };
const viewOf = (params) => (params && params.v === 'h' ? 'h' : 't');
const otherView = (v) => (v === 'h' ? 't' : 'h');
const hrefFor = (y, v) => routeHref('ranking', { y: y || '', v: v === 'h' ? 'h' : '' });

const HOW = 'El índice compara los goles por partido de cada niño con la media de su categoría (100 es la media). Un gol vale más si el rival encaja poco, si la liga es de más nivel y si su equipo es de los de arriba de su grupo, y también si el niño es de los pequeños de la categoría o juega con los mayores. Se corrige a quien ha jugado pocos partidos. Sale solo de las actas de la federación: no hay minutos, ni se sabe quién es portero o defensa, así que favorece a quien marca. El año de nacimiento es una estimación por las categorías en las que ha jugado; quien puede ser de dos años sale en los dos.';

// Los años de data-ranking.js, de más joven a más mayor: [{ year, t, h }], con cuántos tiene cada vista.
function yearsOf(ranking) {
  const anios = ranking && ranking.anios && typeof ranking.anios === 'object' ? ranking.anios : {};
  return Object.keys(anios).filter(y => /^\d{4}$/.test(y)).sort().reverse()
    .map(year => ({ year, t: Number(anios[year] && anios[year][0]) || 0, h: Number(anios[year] && anios[year][1]) || 0 }));
}

/* El año que se ve: el de la dirección (tenga o no a alguien: la ficha enlaza a cada año posible del niño
 * y un año sin nadie lo dice) o, sin él, el más reciente con alguien en la vista pedida; si ninguno lo
 * tiene, el más reciente con alguien en la otra (su vacío enlaza a ella). null sin ningún año. */
export function chosenYear(params, ranking) {
  if (params && params.y) return String(params.y);
  const years = yearsOf(ranking);
  const v = viewOf(params);
  const found = years.find(e => e[v] > 0) || years[0];
  return found ? found.year : null;
}

// Lo que pinta la pantalla: { v, year, years, known (el año está en data-ranking.js), data (sus listas:
// undefined sin pedir, null si falló) }; ranking: undefined sin pedir y null si falló.
function locate(ctx) {
  const params = ctx.params || {};
  const ranking = ctx.datasets ? ctx.datasets.ranking : undefined;
  const v = viewOf(params);
  const year = ranking ? chosenYear(params, ranking) : (params.y || null);
  const years = ranking ? yearsOf(ranking) : [];
  const known = years.some(e => e.year === year);
  const data = known && ctx.datasets.rankingYears ? ctx.datasets.rankingYears[year] : undefined;
  return { v, ranking, year, years, known, data };
}

const titleOf = (year) => (year ? `Los mejores de ${year}` : 'Los mejores de cada año');

// Un año de data-ranking.js cuya lista de toda la trayectoria está vacía (los pequeños, con una sola
// temporada; con las categorías nuevas, también los mayores) no ofrece esa vista: ni su pestaña ni, en la
// fila de años de esa vista, su ficha, que lleva a la de esta temporada, la que tiene.
const withoutH = (entry) => Boolean(entry) && entry.h === 0;

// La fila de años: las fichas de la tira de grupos de Tabla (se desliza dentro de su caja, nunca la
// página; en escritorio, en filas), con id estable: al cambiar de año, el foco vuelve a la pulsada.
function yearStrip(years, year, v) {
  if (!years.length) return '';
  const href = (e) => hrefFor(e.year, withoutH(e) ? 't' : v);
  const chips = years.map(e => (e.year === year
    ? html`<a class="group-chip" id="anio-${e.year}" href="${href(e)}" aria-current="true">${e.year}</a>`
    : html`<a class="group-chip" id="anio-${e.year}" href="${href(e)}">${e.year}</a>`));
  return html`<nav class="group-strip" aria-label="Año de nacimiento"><div class="group-scroll">${chips}</div></nav>`;
}

// Un niño: su puesto, su nombre (a su ficha) con la marca del año dudoso (puede ser de dos años y sale en
// los dos; la entrada no trae cuáles), su equipo y categoría debajo, y a la derecha goles, partidos, de
// titular y el índice. Partidos y titularidades, solo desde 480 px (acta.css).
function rankRow(entry, i) {
  const [key, name, team, cat, pj, tit, goals, index, doubtful] = entry;
  const inner = html`<span class="rank-line"><span class="rank-name">${playerName(name)}</span>${doubtful ? html` <span class="rank-mark">año dudoso</span>` : ''}</span><span class="rank-team">${[team, cat ? categoryName(cat) : ''].filter(Boolean).join(' · ')}</span>`;
  const href = playerHref(key);
  const who = href ? html`<a class="rank-link" href="${href}">${inner}</a>` : html`<span class="rank-link">${inner}</span>`;
  return html`<tr><td class="st-pos">${i + 1}</td><th scope="row" class="rank-player">${who}</th><td class="sc-goals">${goals}</td><td class="rank-pj">${pj}</td><td class="rank-tit">${tit}</td><td class="rank-idx">${index}</td></tr>`;
}

function rankTable(list, year, v, season) {
  const when = v === 't' ? `esta temporada${season ? ` (${seasonLabel(season)})` : ''}` : 'en toda su trayectoria';
  return box(html`<table class="standings rank-table"><caption class="vh">Los mejores nacidos en ${year}, ${when}</caption><thead><tr><th scope="col" class="st-pos"><abbr title="Puesto">#</abbr></th><th scope="col" class="rank-player">Jugador</th><th scope="col" class="sc-goals">Goles</th><th scope="col" class="rank-pj"><abbr title="Partidos jugados">PJ</abbr></th><th scope="col" class="rank-tit"><abbr title="Partidos de titular">Tit.</abbr></th><th scope="col" class="rank-idx">Índice</th></tr></thead><tbody>${list.map(rankRow)}</tbody></table>`);
}

// Sin nadie en la vista: si la otra tiene a alguien, se dice cuál falta y se enlaza a la otra.
function emptyList(year, v, data) {
  if (!year) return block(null, empty('Todavía no hay ningún jugador con partidos suficientes.'));
  const other = otherView(v);
  if (data && Array.isArray(data[other]) && data[other].length) {
    const which = v === 't' ? 'esta temporada' : 'en toda su trayectoria';
    const link = other === 'h' ? 'Ver toda su trayectoria' : 'Ver esta temporada';
    return block(null, html`${empty(`Todavía no hay ningún jugador de ${year} con partidos suficientes ${which}.`)}${notice(null, html`<a class="more" href="${hrefFor(year, other)}">${link}</a>`)}`);
  }
  return block(null, empty(`Todavía no hay ningún jugador de ${year} con partidos suficientes.`));
}

const wrap = (content) => html`<section data-screen="ranking">${content}</section>`;

function render(ctx) {
  const { v, ranking, year, years, known, data } = locate(ctx);
  const head = screenHead(titleOf(year), { back: ctx.backHref, sub: v === 't' ? 'Esta temporada' : 'Toda su trayectoria' });
  // Sin data-ranking.js (null: falló; undefined: no llegó a pedirse), la caja de error con «Reintentar».
  if (!ranking) return wrap(html`${head}${errorBox('este ranking')}`);
  // Las pestañas, sin la de toda la trayectoria si el año no la tiene (salvo que sea la elegida, escrita a mano:
  // se ve dónde se está); con una sola, ninguna.
  const offered = VIEWS.filter(view => view.value !== 'h' || v === 'h' || !withoutH(years.find(e => e.year === year)));
  const tabs = offered.length > 1 ? segmented(offered, v, (value) => hrefFor(year, value), { idPrefix: 'vista' }) : '';
  const controls = html`${yearStrip(years, year, v)}${tabs}`;
  const how = html`<details class="rank-how"><summary>Cómo se calcula</summary><p>${HOW}</p></details>`;
  if (known && !data) return wrap(html`${head}${controls}${errorBox('este ranking')}`);
  const list = data && Array.isArray(data[v]) ? data[v] : [];
  const body = list.length ? block(null, rankTable(list, year, v, ranking.temporada)) : emptyList(year, v, data);
  return wrap(html`${head}${controls}${body}${how}`);
}

// Lleva la fila de años al elegido (scrollToCurrent: con scrollLeft, sin mover la página).
function mount(root) {
  scrollToCurrent(root.querySelector('.group-scroll'));
}

export const screen = {
  id: 'ranking',
  // data-ranking.js y, con él, el fichero del año que se ve, si está en el ranking (si no, no hay
  // fichero que pedir: la pantalla dice que no hay nadie). undefined sin pedir y null si falló, que la
  // pantalla dice con su caja de error y se vuelve a pedir con «Reintentar» o en la visita siguiente,
  // como la ficha del jugador. Nunca rechaza.
  needs: (params, datasets) => {
    const loadYear = (ranking) => {
      const year = ranking ? chosenYear(params, ranking) : null;
      if (!year || !yearsOf(ranking).some(e => e.year === year)) return undefined;
      if (datasets.rankingYears && datasets.rankingYears[year]) return undefined;
      return ensureRankingYear(year).then((data) => { (datasets.rankingYears ||= {})[year] = data; });
    };
    if (!datasets.ranking) return [ensureRanking().then((ranking) => { datasets.ranking = ranking; return loadYear(ranking); })];
    const next = loadYear(datasets.ranking);
    return next ? [next] : [];
  },
  render,
  mount,
  // El título de la pestaña: «Los mejores de 2018» (el router le añade el del sitio).
  title: (ctx) => titleOf(locate(ctx).year),
};
