// La web en una carpeta temporal, para los smokes de navegador que la sirven: nunca el árbol ni enlaces a
// él, porque una prueba que publica otra versión cambia ficheros, y un árbol que cambia a mitad (el bot) no
// puede mover la prueba. Copia lo que sirve el sitio, sin los datos (data-*.js, data-health.json): cada
// smoke pone los suyos, congelados.
import { cpSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
// Lo del sitio que no son datos: la página, el SW, el manifiesto, el código (dist/ y, para la app de antes
// del empaquetado, src/ y acta.css), la fuente, los iconos y los escudos. Es lo que publica Pages (la rama web:
// WEB_FICHEROS y WEB_CARPETAS de scripts/rama_web.py) sin data-health.json ni .nojekyll: si cambia una lista,
// cambia la otra (test_rama_web.py lo comprueba).
export const DEL_SITIO = ['index.html', 'sw.js', 'manifest.json', 'acta.css', 'dist', 'src', 'fonts', 'icons', 'escudos'];

// { dir, limpiar() }: `dir`, una carpeta temporal nueva con `entradas` de `origen` copiadas (los enlaces,
// resueltos: copias de verdad); `limpiar`, la borra.
export function copiaDeLaWeb(prefijo, { origen = ROOT, entradas = DEL_SITIO } = {}) {
  const dir = mkdtempSync(join(tmpdir(), prefijo));
  for (const entrada of entradas) {
    if (existsSync(join(origen, entrada))) cpSync(join(origen, entrada), join(dir, entrada), { recursive: true, dereference: true });
  }
  return { dir, limpiar: () => rmSync(dir, { recursive: true, force: true }) };
}
