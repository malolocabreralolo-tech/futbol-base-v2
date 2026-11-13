// Plan B4, decisión 11: el servidor que imita a GitHub Pages (pages-server.mjs) y las cuentas del
// informe de presupuesto.mjs, sin navegador y sin medir tiempos (el guion mide; estas pruebas, no).
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { request } from 'node:http';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';
import { startPagesServer } from './pages-server.mjs';
import { LIMITS, median, parseArgs, report } from './presupuesto.mjs';

// Una petición tal cual, sin descomprimir: estado, cabeceras y bytes.
function get(url, { method = 'GET', headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = request(url, { method, headers }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.on('error', reject);
    req.end();
  });
}

// `options` va tal cual a startPagesServer; `other`, si se da, es la carpeta de un segundo sitio (v1), con
// su index.html y su sw.js, que la prueba monta donde quiera (options(other)).
async function withSite(fn, options = () => ({})) {
  const root = mkdtempSync(join(tmpdir(), 'pages-'));
  const other = mkdtempSync(join(tmpdir(), 'pages-v1-'));
  const html = '<!DOCTYPE html><title>sitio</title>' + 'x'.repeat(2000);
  const js = `const DATOS = ${JSON.stringify('y'.repeat(3000))};\n`;
  const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);
  const v1 = { html: '<!DOCTYPE html><title>v1</title>' + 'z'.repeat(2000), sw: "const CACHE_NAME = 'futbolbase-v20261113b';\n" };
  writeFileSync(join(root, 'index.html'), html);
  writeFileSync(join(root, 'data-x.js'), js);
  mkdirSync(join(root, 'escudos'));
  writeFileSync(join(root, 'escudos', 'a.png'), png);
  writeFileSync(join(other, 'index.html'), v1.html);
  writeFileSync(join(other, 'sw.js'), v1.sw);
  const server = await startPagesServer(root, options(other));
  try {
    await fn(server.url, { html, js, png, v1 });
  } finally {
    await server.close();
    rmSync(root, { recursive: true, force: true });
    rmSync(other, { recursive: true, force: true });
  }
}

test('pages-server: index.html en la raíz y bajo /futbol-base-v2/, con max-age=600 como GitHub Pages', async () => {
  await withSite(async (url, { html }) => {
    assert.match(url, /^http:\/\/127\.0\.0\.1:\d+\/$/);
    for (const path of ['', 'index.html', 'futbol-base-v2/', 'futbol-base-v2/index.html?v=20991231a']) {
      const res = await get(url + path);
      assert.equal(res.status, 200, path);
      assert.equal(res.headers['content-type'], 'text/html; charset=utf-8');
      assert.equal(res.headers['cache-control'], 'max-age=600');
      assert.equal(res.body.toString(), html);
    }
  });
});

test('pages-server: gzip en el texto si el navegador lo acepta; las imágenes, tal cual', async () => {
  await withSite(async (url, { js, png }) => {
    const gz = await get(`${url}futbol-base-v2/data-x.js?v=1`, { headers: { 'accept-encoding': 'gzip, deflate, br' } });
    assert.equal(gz.headers['content-encoding'], 'gzip');
    assert.equal(gz.headers['content-type'], 'application/javascript; charset=utf-8');
    assert.equal(Number(gz.headers['content-length']), gz.body.length);
    assert.ok(gz.body.length < js.length / 10, `${gz.body.length} bytes con gzip`);
    assert.equal(gunzipSync(gz.body).toString(), js);
    const plain = await get(`${url}data-x.js`);
    assert.equal(plain.headers['content-encoding'], undefined, 'sin Accept-Encoding, sin gzip');
    assert.equal(plain.body.toString(), js);
    const image = await get(`${url}escudos/a.png`, { headers: { 'accept-encoding': 'gzip' } });
    assert.equal(image.headers['content-type'], 'image/png');
    assert.equal(image.headers['content-encoding'], undefined);
    assert.deepEqual(image.body, png);
  });
});

test('pages-server: 404 fuera del sitio o si no existe; HEAD sin cuerpo; solo GET y HEAD', async () => {
  await withSite(async (url) => {
    for (const path of ['escudos/s/a.png', 'escudos', '..%2f..%2fetc%2fpasswd', 'futbol-base-v2/..%2f..%2fetc%2fhosts', '%E0%A4%A', 'futbol-base/', 'futbol-base/index.html']) {
      assert.equal((await get(url + path)).status, 404, path);
    }
    const head = await get(`${url}index.html`, { method: 'HEAD' });
    assert.equal(head.status, 200);
    assert.equal(head.body.length, 0);
    assert.equal((await get(`${url}index.html`, { method: 'POST' })).status, 405);
  });
});

// v1 y v2 en el mismo origen, como en malolocabreralolo-tech.github.io (aislamiento-smoke.mjs): cada uno
// bajo su prefijo, y nada de uno se sirve bajo el otro.
test('pages-server: un segundo sitio bajo /futbol-base/, en el mismo origen que /futbol-base-v2/', async () => {
  await withSite(async (url, { html, js, v1 }) => {
    for (const path of ['futbol-base/', 'futbol-base', 'futbol-base/index.html?v=20261113b']) {
      const res = await get(url + path);
      assert.equal(res.status, 200, path);
      assert.equal(res.headers['content-type'], 'text/html; charset=utf-8');
      assert.equal(res.headers['cache-control'], 'max-age=600');
      assert.equal(res.body.toString(), v1.html, path);
    }
    assert.equal((await get(`${url}futbol-base/sw.js`)).body.toString(), v1.sw);
    for (const path of ['', 'index.html', 'futbol-base-v2/', 'futbol-base-v2/index.html']) {
      assert.equal((await get(url + path)).body.toString(), html, path);
    }
    assert.equal((await get(`${url}futbol-base-v2/data-x.js`)).body.toString(), js);
    // Lo de un sitio no está en el otro, ni fuera de su carpeta; y un prefijo parecido no es el sitio.
    for (const path of ['futbol-base/data-x.js', 'futbol-base-v2/sw.js', 'futbol-base/..%2f..%2fetc%2fhosts', 'futbol-basex/', 'futbol-base-v1/']) {
      assert.equal((await get(url + path)).status, 404, path);
    }
  }, (other) => ({ sites: { '/futbol-base': other } }));
});

test('pages-server: transform cambia lo que sirve un sitio en cada petición (una subida), también con gzip', async () => {
  let version = '20261113b';
  const calls = [];
  const transform = ({ site, path, body }) => {
    calls.push(`${site} ${path}`);
    return site === '/futbol-base' && path === 'sw.js' ? body.toString().replaceAll('20261113b', version) : undefined;
  };
  await withSite(async (url, { html, v1 }) => {
    assert.equal((await get(`${url}futbol-base/sw.js`)).body.toString(), v1.sw);
    version = '20991231a';
    const after = v1.sw.replace('20261113b', '20991231a');
    const plain = await get(`${url}futbol-base/sw.js`);
    assert.equal(plain.body.toString(), after);
    assert.equal(Number(plain.headers['content-length']), Buffer.byteLength(after));
    const gz = await get(`${url}futbol-base/sw.js`, { headers: { 'accept-encoding': 'gzip' } });
    assert.equal(gz.headers['content-encoding'], 'gzip');
    assert.equal(gunzipSync(gz.body).toString(), after);
    // Lo que transform deja (undefined), tal cual.
    assert.equal((await get(`${url}futbol-base/`)).body.toString(), v1.html);
    assert.equal((await get(url)).body.toString(), html);
    assert.equal((await get(`${url}futbol-base-v2/index.html`)).body.toString(), html);
    assert.deepEqual(calls, ['/futbol-base sw.js', '/futbol-base sw.js', '/futbol-base sw.js', '/futbol-base index.html',
      '/futbol-base-v2 index.html', '/futbol-base-v2 index.html']);
  }, (other) => ({ sites: { '/futbol-base': other }, transform }));
});

test('presupuesto: argumentos, mediana y el informe con sus umbrales (spec §5.4)', () => {
  assert.deepEqual(parseArgs([]), { web: null, runs: 3 });
  assert.deepEqual(parseArgs(['--web', 'https://example.test/futbol-base', '--runs', '5']),
    { web: 'https://example.test/futbol-base/', runs: 5 });
  assert.throws(() => parseArgs(['--runs', '0']), /argumento no válido/);
  assert.throws(() => parseArgs(['--rapido']), /argumento no válido/);
  assert.equal(median([2900, 2700, 2800]), 2800);
  assert.equal(median([4, 1, 3, 2]), 2.5);
  assert.deepEqual(LIMITS, { home: 3000, lcp: 3000, cls: 0.1, tablaKB: 300 });
  const base = { home: 2692.4, lcp: 2768.2, fcp: 620, kb: 331.2, runs: 3, cls: { 390: 0, 1440: 0.00012 }, tabla: { bytes: 48435, images: 15 } };
  assert.deepEqual(report(base), {
    ok: true,
    lines: [
      'portada: 2692 ms (< 3000); LCP 2768 ms (< 3000); FCP 620 ms; 331 KB; mediana de 3',
      'CLS: 0,0001 (< 0,1): 390 px 0,0000 y 1440 px 0,0001; máximo de 3, mundo A (Las Mesas, sin actas, y Guayarmina, A1 con actas)',
      'imágenes de Tabla: 47,3 KB (< 300): 15 imágenes, PG2',
      'PRESUPUESTO: OK',
    ],
  });
  // Cada umbral es estricto («menos de»), y basta uno para que salga MAL.
  for (const worse of [{ home: 3000 }, { lcp: 3000.4 }, { cls: { 390: 0.1, 1440: 0 } }, { tabla: { bytes: 300 * 1024, images: 15 } }]) {
    const { ok, lines } = report({ ...base, ...worse });
    assert.equal(ok, false, JSON.stringify(worse));
    assert.equal(lines.at(-1), 'PRESUPUESTO: MAL');
  }
});

// Regresión: si Chrome no arranca (CHROME apunta a un camino que no existe; findChrome() lo devuelve
// tal cual porque empieza por «/», sin comprobar que exista), presupuesto.mjs tiene que salir con 2 en
// seguida, sin dejar el servidor de pages-server.mjs abierto colgando el proceso. spawnSync con
// `timeout` es la red de seguridad: si el guion volviera a colgarse, esta prueba fallaría (la señal no
// sería null) en vez de colgar toda la suite. Sin navegador de verdad: chromium.launch() falla al
// comprobar el binario, antes de tocar la red.
test('presupuesto: sin Chrome que arranque, sale con 2 en seguida y no deja el servidor abierto', () => {
  const bin = fileURLToPath(new URL('./presupuesto.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [bin], {
    env: { ...process.env, CHROME: '/no/existe/chrome' },
    encoding: 'utf8',
    timeout: 15000,
  });
  assert.equal(run.signal, null, `no debería seguir vivo a los 15 s: ${run.stdout}${run.stderr}`);
  assert.equal(run.status, 2, `stdout: ${run.stdout}\nstderr: ${run.stderr}`);
  assert.match(run.stderr, /PRESUPUESTO: sin medir:/);
});
