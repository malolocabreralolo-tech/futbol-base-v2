// Servidor estático que imita a GitHub Pages, para medir el presupuesto
// (presupuesto.mjs) con las mismas condiciones que la web publicada:
// - gzip en los ficheros de texto (HTML, CSS, JavaScript, JSON, SVG y el manifiesto) si el navegador
//   lo acepta, como GitHub Pages; las imágenes y la fuente, tal cual;
// - Cache-Control: max-age=600 en cada respuesta, como GitHub Pages;
// - el sitio en la raíz y también bajo /futbol-base-v2/, la ruta de la web publicada; «/» y
//   «/futbol-base-v2/» son index.html, y la ?v= no cuenta;
// - solo GET y HEAD, y nada fuera de `root` (404).
// startPagesServer(root, { port, sites, transform }) → { url, close() }: url es la raíz, con la barra final.
// - sites: { '/futbol-base': carpeta }, más sitios en el mismo origen, cada uno bajo su prefijo, como v1
//   y v2 en malolocabreralolo-tech.github.io (aislamiento-smoke.mjs); fuera de su carpeta, 404.
// - transform({ site, path, body }): lo que se sirve en lugar de `body` (un Buffer), o undefined para
//   servirlo tal cual; site es el prefijo ('/futbol-base-v2' para `root`) y path, la ruta dentro del
//   sitio. Se llama en cada petición: así una prueba publica otra versión sin tocar los ficheros.
// - intercept({ site, path, url, req, res }): antes de servir nada; si devuelve (o resuelve) true, la prueba
//   ya se ha encargado de la petición (un 404, una conexión cortada o una que no contesta nunca, que close()
//   corta); si no, se sirve como siempre. Puede esperar antes de devolver: así se retiene una petición.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { gzipSync } from 'node:zlib';

const PREFIX = '/futbol-base-v2';
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};
const COMPRESSIBLE = /^(?:text\/|application\/(?:javascript|json|manifest\+json)|image\/svg\+xml)/;

// El sitio y el fichero que sirven una ruta de la URL ({ site, path, file }), o null si queda fuera.
// `sites` va del prefijo a su carpeta; el de `root`, PREFIX, también sirve en la raíz.
function fileFor(sites, pathname) {
  let path;
  try { path = decodeURIComponent(pathname); } catch { return null; }
  let site = PREFIX;
  for (const prefix of Object.keys(sites)) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      site = prefix;
      path = path.slice(prefix.length) || '/';
      break;
    }
  }
  if (path.endsWith('/')) path += 'index.html';
  const root = sites[site];
  const file = normalize(join(root, path));
  return file.startsWith(root + sep) ? { site, path: file.slice(root.length + 1).split(sep).join('/'), file } : null;
}

export async function startPagesServer(root, { port = 0, sites = {}, transform = null, intercept = null } = {}) {
  const roots = { [PREFIX]: resolve(root) };
  for (const [prefix, dir] of Object.entries(sites)) roots[prefix] = resolve(dir);
  const gzipped = new Map();
  const server = createServer(async (req, res) => {
    try {
      if (req.method !== 'GET' && req.method !== 'HEAD') {
        res.writeHead(405, { Allow: 'GET, HEAD' });
        res.end();
        return;
      }
      const url = new URL(req.url, 'http://pages.local');
      const found = fileFor(roots, url.pathname);
      if (intercept && found && await intercept({ site: found.site, path: found.path, url, req, res })) return;
      const info = found ? await stat(found.file).catch(() => null) : null;
      if (!info || !info.isFile()) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'max-age=600' });
        res.end(req.method === 'HEAD' ? undefined : 'no está en el sitio');
        return;
      }
      const { file } = found;
      const type = TYPES[extname(file).toLowerCase()] || 'application/octet-stream';
      const headers = { 'Content-Type': type, 'Cache-Control': 'max-age=600', Vary: 'Accept-Encoding' };
      let body = await readFile(file);
      const changed = transform ? transform({ site: found.site, path: found.path, body }) : undefined;
      if (changed !== undefined) body = Buffer.from(changed);
      if (COMPRESSIBLE.test(type) && /\bgzip\b/.test(req.headers['accept-encoding'] || '')) {
        // Lo que cambia transform no se guarda: puede ser otro en la petición siguiente.
        const key = `${file}\0${info.mtimeMs}\0${info.size}`;
        if (changed === undefined && !gzipped.has(key)) gzipped.set(key, gzipSync(body));
        body = changed === undefined ? gzipped.get(key) : gzipSync(body);
        headers['Content-Encoding'] = 'gzip';
      }
      headers['Content-Length'] = body.length;
      res.writeHead(200, headers);
      res.end(req.method === 'HEAD' ? undefined : body);
    } catch {
      res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('error');
    }
  });
  await new Promise((ready, fail) => {
    server.once('error', fail);
    server.listen(port, '127.0.0.1', ready);
  });
  return {
    url: `http://127.0.0.1:${server.address().port}/`,
    close: () => new Promise((done) => {
      server.closeAllConnections();
      server.close(() => done());
    }),
  };
}
