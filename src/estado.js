// El aviso de estado de la portada: si la última pasada del bot falló, si los datos llevan demasiado
// sin comprobarse o si la federación ha publicado algo que la web aún no tiene. Puro: la salud, el
// instante y la zona horaria llegan como argumentos. Las frases no llevan datos de data-health.json.
import { html } from './html.js';

// En las ventanas del bot hay pasada cada hora; fuera, cada dos (scripts/reloj_pasadas.py).
export const UMBRAL_VENTANA_H = 4;
export const UMBRAL_BASE_H = 8;

const HORA_MS = 3600000;

// Día de la semana (en inglés, el mismo en cualquier dispositivo) y hora de `now` en `timeZone`.
function relojEn(now, timeZone) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone, weekday: 'short', hour: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map((part) => [part.type, part.value]));
  return { dia: p.weekday, hora: Number(p.hour) };
}

// Las ventanas del bot: viernes de 18:00 a 24:00 y sábado y domingo de 10:00 a 24:00.
export function enVentana(now, timeZone) {
  const { dia, hora } = relojEn(now, timeZone);
  if (dia === 'Fri') return hora >= 18;
  if (dia === 'Sat' || dia === 'Sun') return hora >= 10;
  return false;
}

const conElementos = (list) => Array.isArray(list) && list.length > 0;

// «N h» hasta las 48 h; desde ahí, «N días». Con un espacio de no separación entre el número y la
// unidad (como percent de ui.js), para que una línea nunca acabe en el número.
const edad = (ms) => {
  const horas = Math.floor(ms / HORA_MS);
  return horas >= 48 ? `${Math.floor(horas / 24)}\u00a0días` : `${horas}\u00a0h`;
};

export function estadoDatos(health, now, timeZone) {
  if (!health || typeof health !== 'object') return [];
  const frases = [];
  if (health.runHealth && health.runHealth.ok === false) frases.push('La última actualización de los datos falló.');
  const checked = typeof health.checkedAt === 'string' ? Date.parse(health.checkedAt) : NaN;
  const at = now instanceof Date ? now.getTime() : NaN;
  // Sin conexión, lo viejo es la copia del móvil, no el bot: lo dice ya la cabecera.
  if (Number.isFinite(checked) && Number.isFinite(at) && !health.fromCache) {
    const age = at - checked;
    const umbral = (enVentana(now, timeZone) ? UMBRAL_VENTANA_H : UMBRAL_BASE_H) * HORA_MS;
    if (age > umbral) frases.push(`Los datos llevan ${edad(age)} sin comprobarse.`);
  }
  if (conElementos(health.newCompetitions) || conElementos(health.newGroups) || conElementos(health.activation && health.activation.failed)) {
    frases.push('Hay competiciones o fases publicadas que aún no están cargadas.');
  }
  return frases;
}

export function statusNotice(health, now, timeZone) {
  const frases = estadoDatos(health, now, timeZone);
  if (!frases.length) return '';
  return html`<p class="notice home-status" role="status"><b>${frases.join(' ')}</b> <a class="more" href="#/fuentes">Ver datos y fuentes</a></p>`;
}
