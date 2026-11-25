// Pantalla «Los mejores de cada año» (#/ranking?y&v): data-ranking.js (qué años hay y cuántos de cada
// vista) y data-ranking-<año>.js (las dos listas de ese año), con la forma de generate_js.ranking_files.
// render(ctx) es pura: se prueba sobre el HTML que devuelve, con nombres inventados. needs, con un fetch
// falso; el router, con el navegador falso común.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { ctxFor, datasetsFor, cssRules } from './fixtures/rediseno/screens.mjs';
import { fakeBrowser } from './fixtures/rediseno/fake-browser.mjs';
import { screen, chosenYear } from '../../src/screen-ranking.js';
import { SCREEN_MAP } from '../../src/screens.js';
import { startRouter } from '../../src/router.js';
import { routeTitle } from '../../src/shell.js';

const s = (h) => String(h);
const text = (h) => s(h).replace(/<[^>]*>/g, ' ').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();

// data-ranking.js: cada año con [entradas en "t", entradas en "h"]. Como hoy: los mayores (2012) solo
// con trayectoria; los pequeños (2020), solo con esta temporada.
const RANKING = { temporada: '2026-2027', anios: { 2012: [0, 1], 2017: [1, 1], 2018: [3, 2], 2020: [1, 0] } };
// [clave, nombre, equipo, categoría, partidos, titular, goles, índice, dudoso]
const YEARS = {
  2018: {
    t: [
      ['1001', 'GOMEZ PEREZ, RAUL', 'Club Uno', 'prebenjamin', 20, 18, 40, 180, 0],
      ['n0k3z9q2f6', 'MORALES RUIZ, HUGO', 'Club Dos', 'benjamin', 12, 10, 15, 140, 1],
      ['1003', 'DIAZ LEON, ANA', 'Club <Tres>', 'prebenjamin', 9, 9, 6, 101, 0],
    ],
    h: [
      ['1001', 'GOMEZ PEREZ, RAUL', 'Club Uno', 'prebenjamin', 45, 40, 70, 160, 0],
      ['n0k3z9q2f6', 'MORALES RUIZ, HUGO', 'Club Dos', 'benjamin', 30, 22, 31, 120, 1],
    ],
  },
  2017: { t: [['1004', 'SOSA, IVAN', 'Club Uno', 'benjamin', 10, 8, 9, 99, 1]], h: [['1004', 'SOSA, IVAN', 'Club Uno', 'benjamin', 20, 16, 15, 95, 1]] },
  2012: { t: [], h: [['1005', 'VEGA, LUIS', 'Club Seis', 'infantil', 40, 38, 25, 130, 0]] },
  2020: { t: [['1006', 'CRUZ, LEO', 'Club Uno', 'prebenjamin', 5, 5, 4, 112, 0]], h: [] },
};
// options.ranking: el de data-ranking.js (null: falló; undefined, pasado a propósito: sin pedir).
const ctxWith = (params, options = {}) => {
  const datasets = datasetsFor();
  datasets.ranking = 'ranking' in options ? options.ranking : RANKING;
  datasets.rankingYears = 'years' in options ? options.years : YEARS;
  return ctxFor('ranking', params, { datasets });
};
const render = (params, options) => s(screen.render(ctxWith(params, options)));
// Las filas de la lista: [puesto, enlace, nombre, marca, equipo · categoría, goles, partidos, titular, índice].
const rows = (out) => [...out.matchAll(/<tr><td class="st-pos">(\d+)<\/td><th scope="row" class="rank-player"><a class="rank-link" href="([^"]+)"><span class="rank-line"><span class="rank-name">([^<]+)<\/span>(?: <span class="rank-mark">([^<]+)<\/span>)?<\/span><span class="rank-team">([^<]+)<\/span><\/a><\/th><td class="sc-goals">(\d+)<\/td><td class="rank-pj">(\d+)<\/td><td class="rank-tit">(\d+)<\/td><td class="rank-idx">(\d+)<\/td><\/tr>/g)]
  .map((m) => m.slice(1).map((v) => v ?? ''));
const years = (out) => [...out.matchAll(/<a class="group-chip" id="anio-(\d{4})" href="([^"]+)"( aria-current="true")?>(\d{4})<\/a>/g)]
  .map((m) => [m[1], m[2].replace(/&amp;/g, '&'), Boolean(m[3])]);
const views = (out) => [...out.matchAll(/<a class="segment" id="vista-([th])" href="([^"]+)"( aria-current="true")?>([^<]+)<\/a>/g)]
  .map((m) => [m[4], m[2].replace(/&amp;/g, '&'), Boolean(m[3])]);

test('la lista de esta temporada en el orden del fichero, con su puesto; cada nombre a su ficha; equipo y categoría debajo', () => {
  const out = render({ y: '2018' });
  assert.match(out, /^<section data-screen="ranking"><header class="screen-head"><a class="back" href="#\/explorar" data-action="back" aria-label="Volver">‹<\/a><div class="screen-head-text"><h1>Los mejores de 2018<\/h1><p class="screen-sub">Esta temporada<\/p><\/div><\/header>/);
  assert.equal((out.match(/<h1[ >]/g) || []).length, 1);
  assert.deepEqual(rows(out), [
    ['1', '#/jugador?id=1001', 'Raul Gomez Perez', '', 'Club Uno · Prebenjamín', '40', '20', '18', '180'],
    ['2', '#/jugador?id=n0k3z9q2f6', 'Hugo Morales Ruiz', 'año dudoso', 'Club Dos · Benjamín', '15', '12', '10', '140'],
    ['3', '#/jugador?id=1003', 'Ana Diaz Leon', '', 'Club &lt;Tres&gt; · Prebenjamín', '6', '9', '9', '101'],
  ]);
  // La cabecera de la tabla y su título para el lector de pantalla.
  assert.match(out, /<caption class="vh">Los mejores nacidos en 2018, esta temporada \(2026\/27\)<\/caption>/);
  assert.match(out, /<th scope="col" class="sc-goals">Goles<\/th><th scope="col" class="rank-pj"><abbr title="Partidos jugados">PJ<\/abbr><\/th><th scope="col" class="rank-tit"><abbr title="Partidos de titular">Tit\.<\/abbr><\/th><th scope="col" class="rank-idx">Índice<\/th>/);
});

test('la vista de toda la trayectoria pinta "h"; la categoría que la app no tiene, con mayúscula', () => {
  const out = render({ y: '2018', v: 'h' });
  assert.match(out, /<p class="screen-sub">Toda su trayectoria<\/p>/);
  assert.deepEqual(rows(out).map((r) => [r[0], r[1], r[5], r[8]]), [['1', '#/jugador?id=1001', '70', '160'], ['2', '#/jugador?id=n0k3z9q2f6', '31', '120']]);
  assert.match(out, /<caption class="vh">Los mejores nacidos en 2018, en toda su trayectoria<\/caption>/);
  assert.deepEqual(rows(render({ y: '2012', v: 'h' })).map((r) => r[4]), ['Club Seis · Infantil']);
});

test('los años, de más joven a más mayor, con el elegido marcado; las dos vistas, con el año', () => {
  const out = render({ y: '2018' });
  assert.deepEqual(years(out), [
    ['2020', '#/ranking?y=2020', false], ['2018', '#/ranking?y=2018', true], ['2017', '#/ranking?y=2017', false], ['2012', '#/ranking?y=2012', false],
  ]);
  assert.match(out, /<nav class="group-strip" aria-label="Año de nacimiento"><div class="group-scroll">/);
  assert.deepEqual(views(out), [['Esta temporada', '#/ranking?y=2018', true], ['Toda su trayectoria', '#/ranking?y=2018&v=h', false]]);
  // En la vista de toda la trayectoria, los años la conservan.
  const h = render({ y: '2017', v: 'h' });
  assert.deepEqual(years(h).map(([y, href, current]) => [y, href, current]), [
    ['2020', '#/ranking?y=2020&v=h', false], ['2018', '#/ranking?y=2018&v=h', false], ['2017', '#/ranking?y=2017&v=h', true], ['2012', '#/ranking?y=2012&v=h', false],
  ]);
  assert.deepEqual(views(h), [['Esta temporada', '#/ranking?y=2017', false], ['Toda su trayectoria', '#/ranking?y=2017&v=h', true]]);
});

test('sin `y`, el año más reciente con entradas en la vista pedida', () => {
  assert.equal(chosenYear({}, RANKING), '2020');
  assert.equal(chosenYear({ v: 'h' }, RANKING), '2018', '2020 no tiene a nadie con toda su trayectoria');
  assert.equal(chosenYear({ y: '2012' }, RANKING), '2012', 'con `y`, ese, tenga o no entradas');
  assert.match(render({}), /<h1>Los mejores de 2020<\/h1>/);
  assert.deepEqual(years(render({ v: 'h' })).filter(([, , current]) => current).map(([y]) => y), ['2018']);
  assert.deepEqual(rows(render({ v: 'h' })).map((r) => r[1]), ['#/jugador?id=1001', '#/jugador?id=n0k3z9q2f6']);
  // Si ninguno tiene a nadie en esa vista, el más reciente que tenga a alguien (con el vacío y su enlace).
  const onlyH = { temporada: '2026-2027', anios: { 2012: [0, 1], 2011: [0, 3] } };
  assert.equal(chosenYear({}, onlyH), '2012');
  assert.equal(chosenYear({}, { temporada: null, anios: {} }), null);
});

test('un año sin nadie en la vista elegida, pero sí en la otra: el vacío y el enlace a la otra vista', () => {
  const t = render({ y: '2012' });
  assert.match(t, /<p class="empty">Todavía no hay ningún jugador de 2012 con partidos suficientes esta temporada\.<\/p>/);
  assert.match(t, /<a class="more" href="#\/ranking\?y=2012&amp;v=h">Ver toda su trayectoria<\/a>/);
  assert.deepEqual(rows(t), []);
  const h = render({ y: '2020', v: 'h' });
  assert.match(h, /<p class="empty">Todavía no hay ningún jugador de 2020 con partidos suficientes en toda su trayectoria\.<\/p>/);
  assert.match(h, /<a class="more" href="#\/ranking\?y=2020">Ver esta temporada<\/a>/);
});

test('un año sin datos: «Todavía no hay ningún jugador de <año> con partidos suficientes.»', () => {
  // Uno que no está en el ranking (la ficha enlaza a cada año posible del niño): ese año, vacío, sin pedir nada.
  const out = render({ y: '2008' });
  assert.match(out, /<h1>Los mejores de 2008<\/h1>/);
  assert.match(out, /<p class="empty">Todavía no hay ningún jugador de 2008 con partidos suficientes\.<\/p>/);
  assert.doesNotMatch(out, /class="more"/);
  assert.deepEqual(years(out).filter(([, , current]) => current), [], 'ningún año marcado');
  // Uno con su fichero vacío en las dos vistas.
  const both = render({ y: '2017' }, { years: { ...YEARS, 2017: { t: [], h: [] } } });
  assert.match(both, /<p class="empty">Todavía no hay ningún jugador de 2017 con partidos suficientes\.<\/p>/);
  // Sin ningún año.
  const none = render({}, { ranking: { temporada: null, anios: {} }, years: {} });
  assert.match(none, /<h1>Los mejores de cada año<\/h1>/);
  assert.match(none, /<p class="empty">Todavía no hay ningún jugador con partidos suficientes\.<\/p>/);
});

test('si falla data-ranking.js o el fichero del año, la caja de error con «Reintentar»', () => {
  for (const out of [render({ y: '2018' }, { ranking: null }), render({ y: '2018' }, { years: { ...YEARS, 2018: null } }), render({}, { ranking: undefined })]) {
    assert.match(text(out), /No se pudieron cargar los datos de este ranking\./);
    assert.match(out, /data-action="retry"/);
    assert.deepEqual(rows(out), []);
  }
  assert.match(render({ y: '2018' }, { ranking: null }), /<h1>Los mejores de 2018<\/h1>/);
  assert.match(render({}, { ranking: null }), /<h1>Los mejores de cada año<\/h1>/);
});

test('«Cómo se calcula», bajo la lista, con su texto', () => {
  const out = render({ y: '2018' });
  const how = out.match(/<details class="rank-how"><summary>Cómo se calcula<\/summary><p>([^<]+)<\/p><\/details>/);
  assert.ok(how, 'falta el desplegable');
  assert.equal(how[1], 'El índice compara los goles por partido de cada niño con la media de su categoría (100 es la media). Un gol vale más si el rival encaja poco, si la liga es de más nivel y si su equipo es de los de arriba de su grupo, y también si el niño es de los pequeños de la categoría o juega con los mayores. Se corrige a quien ha jugado pocos partidos. Sale solo de las actas de la federación: no hay minutos, ni se sabe quién es portero o defensa, así que favorece a quien marca. El año de nacimiento es una estimación por las categorías en las que ha jugado; quien puede ser de dos años sale en los dos.');
  assert.ok(out.indexOf('rank-how') > out.indexOf('</table>'));
  // También con la lista vacía.
  assert.match(render({ y: '2012' }), /<summary>Cómo se calcula<\/summary>/);
});

test('title: «Los mejores de <año>»; el de la ruta, «Los mejores de cada año»', () => {
  assert.equal(screen.title(ctxWith({ y: '2018' })), 'Los mejores de 2018');
  assert.equal(screen.title(ctxWith({})), 'Los mejores de 2020');
  assert.equal(screen.title(ctxWith({}, { ranking: { temporada: null, anios: {} } })), 'Los mejores de cada año');
  assert.equal(routeTitle('ranking'), 'Los mejores de cada año');
  assert.equal(SCREEN_MAP.ranking, screen);
  assert.equal(screen.id, 'ranking');
});

// El servidor de las pruebas: data-ranking.js y data-ranking-<año>.js de RANKING y YEARS, o lo que diga `fail`.
const serve = (t, fail = () => false) => {
  const asked = [];
  t.mock.method(globalThis, 'fetch', async (url) => {
    const file = String(url).replace(/^\.\//, '').replace(/\?.*$/, '');
    asked.push(file);
    if (fail(file)) throw new TypeError('Failed to fetch');
    const year = (file.match(/^data-ranking-(\d{4})\.js$/) || [])[1];
    const body = file === 'data-ranking.js' ? `const RANKING = ${JSON.stringify(RANKING)};\n`
      : year && YEARS[year] ? `const RANKING_${year} = ${JSON.stringify(YEARS[year])};\n` : null;
    return body ? { ok: true, status: 200, text: async () => body } : { ok: false, status: 404, text: async () => '' };
  });
  return asked;
};

test('needs: data-ranking.js y después el fichero del año que se ve; sin rechazar nunca; un fallo se vuelve a pedir', async (t) => {
  let down = true;
  const asked = serve(t, () => down);
  const quiet = console.warn;
  console.warn = () => {};
  try {
    const datasets = {};
    await Promise.all(screen.needs({ y: '2018' }, datasets));
    assert.equal(datasets.ranking, null, 'falló: la caja de error');
    down = false;
    await Promise.all(screen.needs({}, datasets));
    assert.deepEqual(datasets.ranking, RANKING);
    // Sin `y`, el más reciente con entradas en esta temporada: 2020.
    assert.deepEqual(Object.keys(datasets.rankingYears), ['2020']);
    assert.deepEqual(asked, ['data-ranking.js', 'data-ranking.js', 'data-ranking-2020.js']);
    assert.deepEqual(screen.needs({}, datasets), [], 'ya está');
    // Un año que no está en el ranking no se pide: no hay fichero.
    assert.deepEqual(screen.needs({ y: '2008' }, datasets), []);
    // Otro año, solo su fichero; con un fallo (null), en la visita siguiente otra vez.
    down = true;
    await Promise.all(screen.needs({ y: '2018', v: 'h' }, datasets));
    assert.equal(datasets.rankingYears['2018'], null);
    down = false;
    await Promise.all(screen.needs({ y: '2018', v: 'h' }, datasets));
    assert.deepEqual(datasets.rankingYears['2018'], YEARS[2018]);
    assert.deepEqual(asked.slice(3), ['data-ranking-2018.js', 'data-ranking-2018.js']);
  } finally {
    console.warn = quiet;
  }
});

test('con el router: desde «Más» de Explorar se abre con una entrada nueva; cambiar de año o de vista la sustituye', async (t) => {
  serve(t);
  const datasets = datasetsFor();
  const b = fakeBrowser('#/explorar');
  const router = startRouter({ screens: { ...SCREEN_MAP }, root: b.root, getContext: () => ctxFor('', {}, { datasets }), window: b.win });
  await router.idle();
  b.click({ href: '#/ranking' });
  await router.idle();
  assert.match(b.root.innerHTML, /<h1>Los mejores de 2020<\/h1>/);
  assert.equal(b.doc.title, 'Los mejores de 2020 · Fútbol Base Las Palmas v2');
  assert.deepEqual(b.marks(), [['#/explorar', 'true']], 'cuelga de Explorar');
  b.click({ href: '#/ranking?y=2018', id: 'anio-2018' });
  await router.idle();
  assert.match(b.root.innerHTML, /<h1>Los mejores de 2018<\/h1>/);
  b.click({ href: '#/ranking?y=2018&v=h', id: 'vista-h' });
  await router.idle();
  assert.match(b.root.innerHTML, /<p class="screen-sub">Toda su trayectoria<\/p>/);
  assert.deepEqual(b.entries(), ['#/explorar', '#/ranking?y=2018&v=h'], 'una sola entrada para el ranking');
  assert.equal(b.doc.getElementById('vista-h').focused, 1, 'el foco vuelve a la pestaña pulsada');
});

test('el CSS: solo clases que existen; a 320 px se quitan partidos y titularidades; los años se deslizan en su fila', () => {
  const rules = cssRules();
  // (La caja de error es la de shell.js, la de todas las pantallas.)
  const out = [render({ y: '2018' }), render({ y: '2012' }), render({ y: '2008' }), render({}, { ranking: { temporada: null, anios: {} } })].join('');
  const used = new Set(out.match(/class="[^"]+"/g).flatMap((m) => m.slice(7, -1).split(/\s+/)));
  assert.deepEqual([...used].filter((c) => !rules.classes.has(c)), []);
  const narrow = rules.filter((r) => r.media && /max-width:\s*479\.98px/.test(r.media) && /\.rank-pj/.test(r.selector) && /\.rank-tit/.test(r.selector));
  assert.ok(narrow.some((r) => /display:\s*none/.test(r.body)), 'partidos y titularidades, desde 480 px');
  const decl = (sel) => rules.filter((r) => r.media === null && r.selector.split(/\s*,\s*/).includes(sel)).map((r) => r.body).join(';');
  assert.match(decl('.rank-link'), /min-height:\s*44px/);
  assert.match(decl('.rank-name'), /text-overflow:\s*ellipsis/);
  assert.match(decl('.rank-how summary'), /min-height:\s*44px/);
  assert.match(decl('.group-scroll'), /overflow-x:\s*auto/, 'la fila de años se desliza, no la página');
  // Colores solo de las variables de acta.css.
  const own = rules.filter((r) => /\.rank-/.test(r.selector)).map((r) => r.body).join(';');
  assert.doesNotMatch(own, /#[0-9a-f]{3,8}\b|rgb|hsl/i);
});
