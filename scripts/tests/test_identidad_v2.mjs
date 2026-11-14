// v2 se ve igual que v1 y vive a su lado, en el mismo origen: su nombre con «v2» la distingue en la
// pestaña, en la app instalada y en la cabecera, y lo que la anuncia apunta a su enlace.
// Ejecutar: node --test scripts/tests/test_identidad_v2.mjs
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixture } from './fixtures/rediseno/load.mjs';
import { fakeBrowser } from './fixtures/rediseno/fake-browser.mjs';
import { html } from '../../src/html.js';
import { buildSeason, buildCups } from '../../src/model.js';
import { buildClubIndex } from '../../src/myteam.js';
import { alevinData } from '../../src/state.js';
import { startRouter } from '../../src/router.js';
import { renderHeader } from '../../src/shell.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (path) => readFileSync(join(ROOT, path), 'utf8');
const V2 = 'https://malolocabreralolo-tech.github.io/futbol-base-v2/';
const V1 = 'https://malolocabreralolo-tech.github.io/futbol-base/';

test('manifiesto de v2', () => {
  const m = JSON.parse(read('manifest.json'));
  assert.equal(m.id, '/futbol-base-v2/index.html');
  assert.equal(m.name, 'Fútbol Base Las Palmas v2');
  // «v2» delante: si el móvil recorta la etiqueta de la app instalada, la de v1 («Fútbol Base LP») empieza igual.
  assert.equal(m.short_name, 'v2 Fútbol Base');
});

test('título y cabecera de v2', () => {
  const page = read('index.html');
  assert.match(page, /<title>Fútbol Base Las Palmas v2<\/title>/);
  assert.match(page, /<meta name="apple-mobile-web-app-title" content="v2 Fútbol Base">/);
  assert.match(page, /<span class="brand-place">Las Palmas<\/span> <span class="brand-version">v2<\/span>/);
  // La cabecera que pinta la app es la misma que la de index.html, con la marca.
  assert.match(String(renderHeader()), /<a class="brand" href="#\/">Fútbol base <span class="brand-place">Las Palmas<\/span> <span class="brand-version">v2<\/span><\/a>/);
});

// «v2» va dentro de la marca de la cabecera (que, como en v1, solo se ve desde 1024 px): más pequeña que el
// nombre, en la tinta del tema (sin colores a mano, para el claro y el oscuro) y en su misma línea base.
test('la marca «v2»: pequeña, en la tinta del tema y en la línea base del nombre', () => {
  const css = read('acta.css').replace(/\/\*[\s\S]*?\*\//g, '');
  const rule = (selector) => (css.match(new RegExp(`(?:^|\\n)\\s*${selector.replace('.', '\\.')}\\s*\\{([^}]*)\\}`, 'g')) || [])
    .map((r) => r.slice(r.indexOf('{') + 1, -1)).join(';');
  const version = rule('.brand-version');
  assert.ok(version, 'falta la regla de .brand-version');
  assert.match(version, /color:\s*var\(--ink\)/);
  assert.doesNotMatch(version, /#[0-9a-f]{3,8}\b|rgb|hsl/i, 'sin colores a mano');
  const px = (body, prop) => Number((body.match(new RegExp(`${prop}:\\s*([\\d.]+)rem`)) || [])[1]) * 16;
  const brand = rule('.brand').split(';').filter((d) => !/display:\s*none/.test(d)).join(';');
  assert.ok(px(version, 'font-size') < px(brand, 'font-size'), 'más pequeña que el nombre');
  assert.ok(Number((version.match(/font-weight:\s*(\d+)/) || [])[1]) < Number((brand.match(/font-weight:\s*(\d+)/) || [])[1]), 'con menos peso');
  assert.match(brand, /align-items:\s*baseline/, 'las partes de la marca, en la misma línea base');
});

// Reglas del CSS como {media, selector, body}; un nivel de @media (como en test_rediseno_css.mjs).
function parseCss(src) {
  const rules = [];
  const walk = (s, media) => {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      const prelude = s.slice(i, open).trim();
      let depth = 1, j = open + 1;
      for (; j < s.length && depth; j++) {
        if (s[j] === '{') depth++;
        else if (s[j] === '}') depth--;
      }
      const body = s.slice(open + 1, j - 1);
      if (prelude.startsWith('@media')) walk(body, prelude);
      else rules.push({ media, selector: prelude, body });
      i = j;
    }
  };
  walk(src.replace(/\/\*[\s\S]*?\*\//g, ''), null);
  return rules;
}

// Por debajo de 1024 px la marca de la cabecera no se ve: «v2» va como una muesca sobre la línea de la
// barra de abajo (la misma .tabbar en index.html y en la app), y nunca a la vez que la de la cabecera.
test('en móvil y tableta, «v2» sobre la línea de la barra de abajo, solo cuando la marca de la cabecera no se ve', () => {
  const rules = parseCss(read('acta.css'));
  const has = (rule, selector) => rule.selector.split(',').map((s) => s.trim()).includes(selector);
  const narrow = (media) => /^@media\s*\(max-width:\s*1023\.98px\)$/.test(media ?? '');
  const marks = rules.filter((r) => has(r, '.tabbar::before') && /(^|;)\s*content\s*:/.test(r.body));
  assert.equal(marks.length, 1, 'una sola regla .tabbar::before con contenido');
  const [mark] = marks;
  assert.ok(narrow(mark.media), `la muesca, fuera de la consulta de móvil y tableta: ${mark.media}`);
  assert.match(mark.body, /content:\s*'v2'/);
  assert.match(mark.body, /color:\s*var\(--ink\)/);
  assert.match(mark.body, /background:\s*var\(--paper\)/);
  assert.doesNotMatch(mark.body, /#[0-9a-f]{3,8}\b|rgb|hsl/i, 'sin colores a mano');
  assert.match(mark.body, /position:\s*absolute/);
  assert.match(mark.body, /top:\s*0/);
  assert.match(mark.body, /pointer-events:\s*none/);
  // Va colgada de la barra, que en móvil es fija.
  assert.ok(rules.some((r) => r.media === null && has(r, '.tabbar') && /position:\s*fixed/.test(r.body)));
  // La marca de la cabecera, con su «v2», solo se ve desde 1024 px: las dos nunca coinciden.
  assert.ok(rules.some((r) => r.media === null && has(r, '.brand') && /display:\s*none/.test(r.body)));
  const brandShown = rules.filter((r) => has(r, '.brand') && /display:\s*flex/.test(r.body));
  assert.ok(brandShown.length > 0 && brandShown.every((r) => /^@media\s*\(min-width:\s*1024px\)$/.test(r.media ?? '')));
  // La barra que se ve mientras carga (index.html) es la misma .tabbar que pinta la app.
  assert.match(read('index.html'), /<nav class="tabbar" aria-label="Navegación principal">/);
  assert.match(String(renderHeader()), /<nav class="tabbar" aria-label="Navegación principal">/);
});

// El router de verdad, con el título de index.html, sobre las fixtures congeladas.
const PORTAL = '2025-2026';
const raw = fixture('current-2025-2026');
const current = buildSeason({ name: raw.season, current: true, ...raw });
const cups = buildCups({ season: PORTAL, ...fixture('cups-2025-2026') });
const PG2 = current.groups.find((g) => g.id === 'PG2');
const context = () => ({
  portal: { season: PORTAL, defaultTeam: { cat: 'prebenjamin', groupId: 'PG2', name: 'Las Mesas Hu.' } },
  model: {
    season: (name) => (name === PORTAL ? current : null),
    group: (season, id) => (season === PORTAL ? current.groups.find((g) => g.id === id) || null : null),
    cups: () => cups,
    clubIndex: () => buildClubIndex([], fixture('shields')),
  },
  resolution: { status: 'ok', group: PG2, name: 'Las Mesas Hu.', cat: 'prebenjamin' },
  myTeam: { name: 'Las Mesas Hu.', season: PORTAL, cat: 'prebenjamin', groupId: 'PG2' },
  today: '2026-09-23',
  health: null,
  datasets: { seasons: [{ name: PORTAL, current: true }], seasonRaw: {}, alevin: alevinData({}), seasonAlevin: {} },
});
const screen = (id) => ({ id, render: () => html`<section data-screen="${id}"><h1>${id}</h1></section>` });

test('el título de cada pantalla acaba en «v2»', async () => {
  for (const [hash, title] of [['#/', 'Fútbol Base Las Palmas v2'], ['#/jornada', 'Jornada · Fútbol Base Las Palmas v2']]) {
    const b = fakeBrowser(hash);
    const router = startRouter({ screens: { '': screen('home'), jornada: screen('jornada') }, root: b.root, getContext: context, window: b.win });
    await router.idle();
    assert.equal(b.doc.title, title, hash);
  }
});

test('update.sh anuncia el enlace de v2, nunca el de v1', () => {
  const sh = read('scripts/update.sh');
  assert.ok(sh.includes(`Publicado en ${V2}`), 'update.sh no anuncia el enlace de v2');
  assert.ok(!sh.includes(V1), 'update.sh nombra el enlace de v1');
});

// Solo lo esencial: el bot pasa estas pruebas antes de publicar, y retocar la redacción del README no
// puede pararlo.
test('README: dice al principio que esto es v2 y enlaza v2 y v1', () => {
  const readme = read('README.md');
  assert.ok(readme.includes(`(${V2})`), 'falta el enlace a v2');
  assert.ok(readme.includes(`(${V1})`), 'falta el enlace a v1');
  // En el texto del primer párrafo, sin contar las direcciones de los enlaces (la de v2 ya lleva «v2»).
  const first = readme.split(/\n\s*\n/).find((p) => !p.startsWith('#')) ?? '';
  assert.match(first.replace(/\]\([^)]*\)/g, ']'), /\bv2\b/, 'el primer párrafo no dice que esto es v2');
});

// En este repositorio conviven la historia de v1 y la de v2: una orden de gh sin -R actúa sobre el
// repositorio por defecto de la carpeta donde se teclea, que puede ser v1, y v1 no se toca. Los documentos
// vivos: el README, los de docs/ y los de pc/. Los planes y los diseños (docs/superpowers/, docs/plans/) son
// historia, y la revisión del 13/11 (docs/revision-2026-11-13.md) es el registro de lo que había en v1.
const V2_REPO = 'malolocabreralolo-tech/futbol-base-v2';
function livingDocs() {
  const docs = readdirSync(join(ROOT, 'docs')).filter((name) => name.endsWith('.md') && name !== 'revision-2026-11-13.md');
  const pc = readdirSync(join(ROOT, 'pc')).filter((name) => existsSync(join(ROOT, 'pc', name, 'README.md')));
  return ['README.md', ...docs.map((name) => `docs/${name}`), ...pc.map((name) => `pc/${name}/README.md`)];
}

test('las órdenes de gh de los documentos van al repositorio de v2, nunca al de v1', () => {
  const docs = livingDocs();
  for (const doc of ['docs/federacion.md', 'docs/temporada-nueva.md', 'pc/reloj/README.md', 'pc/copia/README.md']) {
    assert.ok(docs.includes(doc), `${doc}, fuera de los documentos que se miran`);
  }
  const wrong = [];
  let commands = 0;
  for (const doc of docs) {
    read(doc).split('\n').forEach((line, i) => {
      const where = `${doc}:${i + 1}`;
      // Una orden llega hasta el final de su código en línea (`), hasta su comentario (#) o hasta el final de la línea.
      for (const [command, verb] of line.matchAll(/\bgh (workflow|run|issue|api)\b[^`#\n]*/g)) {
        commands += 1;
        const toV2 = verb === 'api' ? !command.includes('repos/') || command.includes(`repos/${V2_REPO}/`) : command.includes(`-R ${V2_REPO}`);
        if (!toV2) wrong.push(`${where}: ${command.trim()}`);
      }
      // Ninguna orden apunta a v1: ni su repositorio (por -R, --repo, la API o la URL de git) ni su carpeta del PC.
      if (/(?:-R\s+|--repo[\s=]+|repos\/|github\.com[/:])malolocabreralolo-tech\/futbol-base(?!-v2\b)/.test(line)) wrong.push(`${where}: apunta a v1: ${line.trim()}`);
      if (/\bcd\s+(?:\/home\/manolo|~)\/claude\/futbol-base(?![\w-])/.test(line)) wrong.push(`${where}: entra en la carpeta de v1: ${line.trim()}`);
    });
  }
  assert.ok(commands > 20, `solo ${commands} órdenes de gh en los documentos: ¿se leen?`);
  assert.deepEqual(wrong, [], `órdenes sin -R ${V2_REPO} (o que apuntan a v1):\n  ${wrong.join('\n  ')}`);
});
