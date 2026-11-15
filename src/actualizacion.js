// La página se pone al día sola. El SW nuevo, al activarse, manda a las ventanas { type: 'version',
// version } (sw.js); si es más nueva que la de la página, la página está vieja (una más vieja es la de
// un SW intermedio que se activa cuando la página ya llegó más nueva de la red: no se hace nada). Si
// nadie la ha tocado desde que se abrió o volvió a primer plano, se recarga (una sola vez por versión,
// apuntada en la sesión); si no, el aviso de la cabecera, «Hay datos nuevos.» con «Actualizar». Al
// volver a primer plano pide al navegador que busque un SW nuevo, como mucho una vez por minuto. No
// toca el navegador al importarse: start le pasa la ventana y el documento.
import { safeStorage } from './store.js';
import { updateNotice } from './shell.js';

// La versión por la que ya se recargó sola esta pestaña: con ella, otra recarga daría un bucle.
export const RELOAD_KEY = 'fb2:recarga';
export const UPDATE_EVERY_MS = 60000;

// Lo que cuenta como usar la página: puntero, tecla o desplazamiento (en captura, para ver también el
// desplazamiento de una tabla, que no burbujea).
const TOQUES = ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll'];
const PASIVO = { capture: true, passive: true };

const NADA = { stop() {} };

export function startUpdates({ win, doc, version, now = () => Date.now() } = {}) {
  const sw = win?.navigator?.serviceWorker;
  if (!sw) return NADA;
  const session = safeStorage(() => win.sessionStorage);
  let tocada = false;
  let avisada = false;
  // La versión nueva que llegó con la página oculta: se decide al volver a verse.
  let pendiente = null;
  let ultimaBusqueda = -Infinity;

  function avisar() {
    if (avisada) return;
    const slot = doc.querySelector('.shell-update');
    if (!slot) return;
    slot.innerHTML = String(updateNotice());
    avisada = true;
  }

  function ponerseAlDia(nueva) {
    if (tocada || session.getItem(RELOAD_KEY) === nueva || !session.setItem(RELOAD_KEY, nueva)) avisar();
    else win.location.reload();
  }

  function onMessage(event) {
    const data = event?.data;
    if (!data || data.type !== 'version' || typeof data.version !== 'string' || !data.version) return;
    // Versiones del bot (AAAAMMDD y una letra opcional): su orden alfabético es el de las versiones.
    if (!version || data.version <= version) return;
    if (doc.hidden) pendiente = data.version;
    else ponerseAlDia(data.version);
  }

  // Que el navegador busque un sw.js nuevo; sus fallos (sin red, sin registro) no importan.
  function buscar() {
    if (now() - ultimaBusqueda < UPDATE_EVERY_MS) return;
    ultimaBusqueda = now();
    Promise.resolve()
      .then(() => sw.getRegistration())
      .then((registration) => registration && registration.update())
      .catch(() => {});
  }

  function alVolver() {
    tocada = false;
    if (pendiente) {
      const nueva = pendiente;
      pendiente = null;
      ponerseAlDia(nueva);
    }
    buscar();
  }

  const onTouch = () => { tocada = true; };
  const onVisibility = () => { if (!doc.hidden) alVolver(); };
  // La carga normal ya la busca index.html al registrar el SW; solo cuenta la vuelta desde la caché del navegador.
  const onPageshow = (event) => { if (event?.persisted) alVolver(); };
  const onClick = (event) => {
    if (event.target?.closest?.('[data-action="actualizar"]')) win.location.reload();
  };

  sw.addEventListener('message', onMessage);
  for (const type of TOQUES) win.addEventListener(type, onTouch, PASIVO);
  doc.addEventListener('visibilitychange', onVisibility);
  win.addEventListener('pageshow', onPageshow);
  win.addEventListener('online', buscar);
  doc.addEventListener('click', onClick);

  return {
    stop() {
      sw.removeEventListener('message', onMessage);
      for (const type of TOQUES) win.removeEventListener(type, onTouch, PASIVO);
      doc.removeEventListener('visibilitychange', onVisibility);
      win.removeEventListener('pageshow', onPageshow);
      win.removeEventListener('online', buscar);
      doc.removeEventListener('click', onClick);
    },
  };
}
