// Empaqueta el código de la web en dist/: src/app.js con todo su grafo en un módulo, y acta.css
// minificada, cada uno con las 8 primeras cifras del SHA-1 de su contenido en el nombre. src/config.js se
// queda fuera: lo reescribe la activación de una temporada sin que cambie el código, y los smokes lo
// sustituyen por su mundo de prueba. No toca nada más que esos dos ficheros: lo demás (borrar los
// anteriores, dist/origen.json, index.html y sw.js) lo hace scripts/codigo.py, que es quien lo llama.
//
// Uso: node scripts/empaquetar/empaquetar.mjs --root <raíz del árbol>
// Saca por la salida estándar {"app": "dist/app-<h>.js", "css": "dist/acta-<h>.css"}.
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import * as esbuild from 'esbuild';

const { values } = parseArgs({ options: { root: { type: 'string' } } });
if (!values.root) {
  console.error('uso: node scripts/empaquetar/empaquetar.mjs --root <raíz del árbol>');
  process.exit(2);
}
const root = resolve(values.root);
const src = join(root, 'src');

// Todo import de ./config.js desde src/ sale como ../src/config.js: relativo a dist/, el mismo fichero.
const configFuera = {
  name: 'config-fuera',
  setup(build) {
    build.onResolve({ filter: /^\.\/config\.js$/ }, (args) => (
      args.importer && dirname(args.importer) === src ? { path: '../src/config.js', external: true } : undefined));
  },
};

// Las url() relativas de la hoja resuelven desde la raíz; desde dist/, un nivel más arriba.
function urlsDesdeDist(css) {
  return css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (whole, quote, url) => (
    /^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(url) ? whole : `url(${quote}../${url}${quote})`));
}

const huella = (text) => createHash('sha1').update(text).digest('hex').slice(0, 8);

const app = await esbuild.build({
  entryPoints: [join(src, 'app.js')],
  bundle: true,
  minify: true,
  format: 'esm',
  target: 'es2020',
  legalComments: 'none',
  charset: 'utf8',
  write: false,
  logLevel: 'warning',
  plugins: [configFuera],
});
const css = await esbuild.transform(urlsDesdeDist(readFileSync(join(root, 'acta.css'), 'utf8')), {
  loader: 'css',
  minify: true,
  legalComments: 'none',
  charset: 'utf8',
  logLevel: 'warning',
});

const out = {};
mkdirSync(join(root, 'dist'), { recursive: true });
for (const [key, name, ext, text] of [['app', 'app', 'js', app.outputFiles[0].text], ['css', 'acta', 'css', css.code]]) {
  out[key] = `dist/${name}-${huella(text)}.${ext}`;
  writeFileSync(join(root, out[key]), text);
}
process.stdout.write(`${JSON.stringify(out)}\n`);
