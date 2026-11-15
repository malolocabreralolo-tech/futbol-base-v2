// Playwright's page.waitForFunction does NOT await a predicate that returns a
// Promise: it runs `const success = predicate(); if (success) fulfill(...)`
// (playwright-core/lib/server/frames.js), and a Promise is always truthy — so
// an async condition "passes" at once without being checked. pwa-smoke.mjs
// waited like that for the new service worker, reloaded while the previous
// one was still in control, and failed whenever CI lost that race
// (2026-09-12..22, every other day). Async conditions — caches, service
// workers, dynamic imports — are polled here through page.evaluate, which
// does await the result. `label` (B3, «Para B3» punto 21): el escenario, el
// ancho y el tema, que el mensaje de un tiempo agotado nombra para que un
// fallo de la CI se lea sin reproducirlo.
export async function waitForAsync(page, predicate, arg, { timeout = 15000, interval = 100, label = null } = {}) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  for (;;) {
    try {
      if (await page.evaluate(predicate, arg)) return;
      lastError = null;
    } catch (error) {
      // A navigation can destroy the execution context mid-poll: retry.
      lastError = error;
    }
    if (Date.now() >= deadline) {
      throw new Error(`waitForAsync${label ? ` (${label})` : ''}: condition not met after ${timeout}ms`
        + (lastError ? ` (last error: ${lastError.message})` : '') + `\n${predicate}`);
    }
    await new Promise(resolve => setTimeout(resolve, interval));
  }
}

// Espera, sin ninguna página de la app abierta, a que mande el SW de la versión cuya caché es `cache`
// (futbolbase2-v… en v2, futbolbase-v… en v1), y devuelve lo que vio la última vuelta, con todas las
// cachés. En cada vuelta, una página nueva de sonda (`probeUrl`: manifest.json de la app, que el SW sirve
// de la red sin tocar su caché) pide la actualización, mira el estado y se cierra en seguida, como quien
// abre la app y la cierra: con una página de la app abierta y la herramienta de pruebas conectada a los SW
// (Playwright), Chrome puede no activar el SW nuevo (codeDeploy de pwa-smoke.mjs; sin ella no pasa, y los
// usuarios no lo ven). Solo cuentan las cachés de datos de la app de `cache`, las que empiezan
// como ella hasta la «-v» de la versión: la de los escudos va aparte, y las de la otra app, que comparte
// el origen (aislamiento-smoke.mjs), no son suyas. Si no llega en 30 s, el error dice cómo quedaron los
// SW en cada vuelta y lo que añada `diagnose`.
export async function takeOver(context, probeUrl, cache, label, diagnose = () => '') {
  const family = cache.slice(0, cache.lastIndexOf('-v') + 2);
  const states = [];
  const waitStart = Date.now();
  const look = async () => {
    const page = await context.newPage();
    try {
      await page.goto(probeUrl);
      return await page.evaluate(async () => {
        const registration = await navigator.serviceWorker.getRegistration();
        try { await registration?.update(); } catch { /* ya se está instalando */ }
        return { caches: await caches.keys(), installing: registration?.installing?.state ?? null, waiting: registration?.waiting?.state ?? null,
          active: registration?.active?.state ?? null, controlled: !!registration?.active && navigator.serviceWorker.controller === registration.active };
      });
    } finally {
      await page.close();
    }
  };
  for (;;) {
    // Una navegación que falla en una vuelta cuenta como «todavía no», con su error en los estados.
    const seen = await look().catch((error) => ({ caches: [], installing: null, waiting: null, active: null, controlled: false,
      error: error.message.split('\n')[0] }));
    // Cada cambio de estado de los SW, con los ms desde que empezó la espera.
    const state = [seen.installing, seen.waiting, seen.active, seen.controlled, seen.caches.length, seen.error ?? ''].join('/');
    if (states.at(-1)?.endsWith(` ${state}`) !== true) states.push(`${Date.now() - waitStart}ms ${state}`);
    const versions = seen.caches.filter((name) => name.startsWith(family));
    if (versions.length === 1 && versions[0] === cache && seen.active === 'activated' && seen.controlled) return seen;
    if (Date.now() - waitStart >= 30000) {
      throw new Error(`${label}: condition not met after 30000ms: ${JSON.stringify({ ...seen, vueltas: states })}${diagnose()}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

// Una acción de Playwright (un clic, la espera de un localizador, una navegación) con la etiqueta de su
// paso (el escenario, el ancho y el tema) delante de su error, como el tiempo agotado de waitForAsync:
// un fallo de la CI se lee sin reproducirlo (B5, decisión 7). Devuelve lo que devuelve la acción.
// Reescribir solo error.message no basta: Playwright ya ha formado error.stack para cuando este
// helper lo recibe, V8 no lo vuelve a formatear al cambiar message, y tanto Node (al imprimir un
// error no capturado) como util.inspect muestran stack, no message. Por eso stack se reescribe
// también: si ya contiene el mensaje sin etiqueta (el caso normal), se sustituye ahí mismo; si no, la
// etiqueta va delante de stack entero. El reemplazo va con una función (no con el string de
// error.message) porque un selector puede llevar un "$" (p. ej. [href$="…"]), y String.replace lee un
// "$&" o un "$1" del reemplazo como patrón, no como texto, cuando el reemplazo es un string (revisión
// final de B5, arreglo 1).
export async function labeled(label, action) {
  try {
    return await action();
  } catch (error) {
    if (error instanceof Error) {
      const { stack, message } = error;
      error.message = `${label}: ${message}`;
      if (typeof stack === 'string') error.stack = stack.includes(message) ? stack.replace(message, () => error.message) : `${label}: ${stack}`;
    }
    throw error;
  }
}
