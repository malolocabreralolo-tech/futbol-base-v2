// La página se pone al día sola (src/actualizacion.js): cuando el SW nuevo se activa manda
// { type: 'version', version } a las ventanas; si no es la de la página, recarga si nadie la ha tocado
// y, si no, el aviso «Hay datos nuevos.» con «Actualizar». Al volver a primer plano pide al navegador
// que busque un SW nuevo, como mucho una vez por minuto. Con una ventana y un documento simulados.
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { startUpdates, RELOAD_KEY, UPDATE_EVERY_MS } from '../../src/actualizacion.js';
import { updateNotice } from '../../src/shell.js';
import { memoryStorage } from './fixtures/rediseno/fake-browser.mjs';

const PAGINA = '20261114w';
const NUEVA = '20261115a';

// Oyentes de un objeto que emite eventos, con su desenganche.
function emisor() {
  const bag = {};
  return {
    bag,
    addEventListener: (type, fn) => { (bag[type] ||= []).push(fn); },
    removeEventListener: (type, fn) => { bag[type] = (bag[type] || []).filter((f) => f !== fn); },
    fire: (type, event = {}) => (bag[type] || []).slice().forEach((fn) => fn(event)),
  };
}

// La ventana, el documento con el hueco del aviso y el SW. session: el sessionStorage (null: ninguno;
// 'roto': uno que lanza). registration: lo que da getRegistration().
function pagina({ session = new Map(), sw = true, registration } = {}) {
  const reloads = [];
  const updates = [];
  const w = emisor();
  const d = emisor();
  const slot = { innerHTML: '' };
  const reg = registration === undefined ? { update: () => { updates.push(clock.t); return Promise.resolve(); } } : registration;
  const container = sw ? { ...emisor(), getRegistration: () => Promise.resolve(reg) } : undefined;
  const clock = { t: 0 };
  const broken = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('bloqueado'); }, removeItem() { throw new Error('bloqueado'); } };
  const win = {
    ...w,
    navigator: sw ? { serviceWorker: container } : {},
    location: { reload: () => { reloads.push(clock.t); } },
    sessionStorage: session === 'roto' ? broken : session ? memoryStorage(session) : undefined,
  };
  const doc = { ...d, hidden: false, querySelector: (selector) => (selector === '.shell-update' ? slot : null) };
  return {
    win, doc, slot, reloads, updates, clock,
    now: () => clock.t,
    version: (version, type = 'version') => container.fire('message', { data: { type, version } }),
    touch: (type = 'pointerdown') => w.fire(type, {}),
    hide: () => { doc.hidden = true; d.fire('visibilitychange'); },
    show: () => { doc.hidden = false; d.fire('visibilitychange'); },
    // Un clic como lo recibe la delegación del documento, en un elemento con esos atributos.
    click: (attrs) => d.fire('click', { target: { closest: (sel) => (sel === '[data-action="actualizar"]' && attrs['data-action'] === 'actualizar' ? attrs : null) } }),
    listeners: () => [w.bag, d.bag, container?.bag || {}].map((bag) => Object.values(bag).flat().length).reduce((a, b) => a + b, 0),
  };
}
const arrancar = (p, version = PAGINA) => startUpdates({ win: p.win, doc: p.doc, version, now: p.now });
const turnos = () => new Promise((resolve) => setTimeout(resolve, 0));
const AVISO = String(updateNotice());

test('updateNotice: «Hay datos nuevos.» y el botón «Actualizar» (data-action="actualizar", type="button")', () => {
  assert.match(AVISO, /Hay datos nuevos\./);
  assert.match(AVISO, /<button class="[^"]*\bbutton\b[^"]*" type="button" data-action="actualizar">Actualizar<\/button>/);
});

test('la misma versión: ni recarga ni aviso', () => {
  const p = pagina();
  arrancar(p);
  p.version(PAGINA);
  assert.deepEqual(p.reloads, []);
  assert.equal(p.slot.innerHTML, '');
});

test('una versión más vieja que la de la página (un SW intermedio): ni recarga ni aviso, tocada o no, visible u oculta', () => {
  for (const vieja of ['20261114', '20261114a', '20261113z']) {
    const sinTocar = pagina();
    arrancar(sinTocar);
    sinTocar.version(vieja);
    const tocada = pagina();
    arrancar(tocada);
    tocada.touch();
    tocada.version(vieja);
    const oculta = pagina();
    arrancar(oculta);
    oculta.hide();
    oculta.version(vieja);
    oculta.show();
    for (const p of [sinTocar, tocada, oculta]) {
      assert.deepEqual(p.reloads, [], vieja);
      assert.equal(p.slot.innerHTML, '', vieja);
    }
  }
});

test('más nueva por la letra o por el día: 20261114b sobre 20261114, y 20261115 sobre 20261114z, recargan', () => {
  for (const [paginaV, nueva] of [['20261114', '20261114b'], ['20261114z', '20261115']]) {
    const session = new Map();
    const p = pagina({ session });
    arrancar(p, paginaV);
    p.version(nueva);
    assert.equal(p.reloads.length, 1, `${nueva} sobre ${paginaV}`);
    assert.equal(session.get('fb2:recarga'), nueva);
  }
});

test('otra versión, sin tocar la página: recarga una vez y apunta la versión en fb2:recarga', () => {
  const session = new Map();
  const p = pagina({ session });
  arrancar(p);
  p.version(NUEVA);
  assert.equal(RELOAD_KEY, 'fb2:recarga');
  assert.equal(p.reloads.length, 1);
  assert.equal(session.get('fb2:recarga'), NUEVA);
  assert.equal(p.slot.innerHTML, '');
});

test('otra versión tras tocar la página: el aviso, sin recarga; «Actualizar» recarga', () => {
  for (const type of ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']) {
    const session = new Map();
    const p = pagina({ session });
    arrancar(p);
    p.touch(type);
    p.version(NUEVA);
    assert.deepEqual(p.reloads, [], type);
    assert.equal(p.slot.innerHTML, AVISO, type);
    assert.equal(session.has('fb2:recarga'), false, `${type}: la recarga a mano no se apunta`);
    p.click({ 'data-action': 'otra' });
    assert.deepEqual(p.reloads, [], `${type}: otro clic no recarga`);
    p.click({ 'data-action': 'actualizar' });
    assert.equal(p.reloads.length, 1, type);
  }
});

test('el aviso no se quita solo ni se repite: otra versión con el aviso puesto lo deja como está', () => {
  const p = pagina();
  arrancar(p);
  p.touch();
  p.version(NUEVA);
  p.slot.innerHTML = AVISO + '<!-- el mismo nodo -->';
  p.version('20261115b');
  p.touch('keydown');
  assert.equal(p.slot.innerHTML, AVISO + '<!-- el mismo nodo -->');
  assert.deepEqual(p.reloads, []);
});

test('otra versión ya apuntada en fb2:recarga: el aviso, sin recarga (una sola recarga sola por versión)', () => {
  const p = pagina({ session: new Map([['fb2:recarga', NUEVA]]) });
  arrancar(p);
  p.version(NUEVA);
  assert.deepEqual(p.reloads, []);
  assert.equal(p.slot.innerHTML, AVISO);
});

test('otra versión apuntada antes no frena una versión más nueva', () => {
  const session = new Map([['fb2:recarga', '20261114a']]);
  const p = pagina({ session });
  arrancar(p);
  p.version(NUEVA);
  assert.equal(p.reloads.length, 1);
  assert.equal(session.get('fb2:recarga'), NUEVA);
});

test('sin sessionStorage, o con uno que no deja escribir: el aviso, nunca una recarga sin freno', () => {
  for (const session of [null, 'roto']) {
    const p = pagina({ session });
    arrancar(p);
    p.version(NUEVA);
    assert.deepEqual(p.reloads, [], String(session));
    assert.equal(p.slot.innerHTML, AVISO, String(session));
  }
});

test('otra versión con la página oculta: nada; al volver a verse, recarga', () => {
  const session = new Map();
  const p = pagina({ session });
  arrancar(p);
  p.hide();
  p.version(NUEVA);
  assert.deepEqual(p.reloads, []);
  assert.equal(p.slot.innerHTML, '');
  assert.equal(session.has('fb2:recarga'), false);
  p.show();
  assert.equal(p.reloads.length, 1);
  assert.equal(session.get('fb2:recarga'), NUEVA);
});

test('oculta y tocada antes de ocultarse: al volver a verse cuenta como sin tocar, y recarga', () => {
  const p = pagina();
  arrancar(p);
  p.touch();
  p.hide();
  p.version(NUEVA);
  p.show();
  assert.equal(p.reloads.length, 1);
});

test('tocar, ocultar, volver a verse y recibir otra versión: recarga («tocada» vuelve a cero al volver)', () => {
  const p = pagina();
  arrancar(p);
  p.touch('scroll');
  p.hide();
  p.show();
  p.version(NUEVA);
  assert.equal(p.reloads.length, 1);
});

test('volver a verse dos veces en 10 s: un solo registration.update(); a los 61 s, otro', async () => {
  const p = pagina();
  arrancar(p);
  assert.equal(UPDATE_EVERY_MS, 60000);
  p.hide();
  p.show();
  await turnos();
  p.clock.t = 10000;
  p.hide();
  p.show();
  await turnos();
  assert.deepEqual(p.updates, [0]);
  p.clock.t = 61000;
  p.hide();
  p.show();
  await turnos();
  assert.deepEqual(p.updates, [0, 61000]);
});

test('pageshow desde la caché del navegador y online también lo piden, con el mismo límite; al arrancar, no', async () => {
  const p = pagina();
  arrancar(p);
  p.win.fire('pageshow', { persisted: false });
  await turnos();
  assert.deepEqual(p.updates, [], 'la carga normal ya la pide index.html al registrar el SW');
  p.win.fire('pageshow', { persisted: true });
  await turnos();
  p.clock.t = 30000;
  p.win.fire('online');
  await turnos();
  assert.deepEqual(p.updates, [0]);
  p.clock.t = 90000;
  p.win.fire('online');
  await turnos();
  assert.deepEqual(p.updates, [0, 90000]);
});

test('pageshow desde la caché del navegador cuenta como volver a verse: «tocada» vuelve a cero', () => {
  const p = pagina();
  arrancar(p);
  p.touch();
  p.win.fire('pageshow', { persisted: true });
  p.version(NUEVA);
  assert.equal(p.reloads.length, 1);
});

test('registration.update() que falla, o sin registro: no lanza nada', async () => {
  const rejected = [];
  const onRejection = (reason) => rejected.push(reason);
  process.on('unhandledRejection', onRejection);
  try {
    for (const registration of [null, { update: () => Promise.reject(new Error('sin red')) }, { update: () => { throw new Error('roto'); } }]) {
      const p = pagina({ registration });
      arrancar(p);
      assert.doesNotThrow(() => { p.hide(); p.show(); });
      await turnos();
    }
    const p = pagina();
    p.win.navigator.serviceWorker.getRegistration = () => Promise.reject(new Error('sin SW'));
    arrancar(p);
    p.hide();
    p.show();
    await turnos();
    const q = pagina();
    q.win.navigator.serviceWorker.getRegistration = () => { throw new Error('sin SW'); };
    arrancar(q);
    assert.doesNotThrow(() => { q.hide(); q.show(); });
    await turnos();
  } finally {
    process.off('unhandledRejection', onRejection);
  }
  assert.deepEqual(rejected, []);
});

test('sin serviceWorker: no lanza ni escucha nada, y stop() tampoco lanza', () => {
  const p = pagina({ sw: false });
  const updates = arrancar(p);
  assert.equal(p.listeners(), 0);
  assert.doesNotThrow(() => updates.stop());
  assert.doesNotThrow(() => startUpdates({ win: {}, doc: p.doc, version: PAGINA }).stop());
});

test('un mensaje de otro tipo, sin versión o sin datos: nada', () => {
  const p = pagina();
  arrancar(p);
  p.version(NUEVA, 'otro');
  p.version(undefined);
  p.version('');
  p.version(42);
  p.win.navigator.serviceWorker.fire('message', { data: null });
  p.win.navigator.serviceWorker.fire('message', { data: 'version' });
  p.win.navigator.serviceWorker.fire('message', {});
  assert.deepEqual(p.reloads, []);
  assert.equal(p.slot.innerHTML, '');
});

test('la página que no sabe su versión (dataVersion() vacío) no hace nada', () => {
  const p = pagina();
  arrancar(p, '');
  p.version(NUEVA);
  assert.deepEqual(p.reloads, []);
  assert.equal(p.slot.innerHTML, '');
});

test('sin el hueco del aviso en la página: no lanza', () => {
  const p = pagina();
  p.doc.querySelector = () => null;
  arrancar(p);
  p.touch();
  assert.doesNotThrow(() => p.version(NUEVA));
  assert.deepEqual(p.reloads, []);
});

test('stop(): quita todos sus oyentes', async () => {
  const p = pagina();
  const updates = arrancar(p);
  assert.ok(p.listeners() > 0);
  updates.stop();
  assert.equal(p.listeners(), 0);
  p.version(NUEVA);
  p.hide();
  p.show();
  await turnos();
  assert.deepEqual(p.reloads, []);
  assert.deepEqual(p.updates, []);
});
