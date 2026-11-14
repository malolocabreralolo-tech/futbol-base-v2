// Jugadores seguidos (la ficha de jugador, #/jugador?id): FOLLOWED_KEY = [{ id, n }], la
// clave de su ficha (isPlayerKey: el id de la federación o «n…») y su nombre, el último seguido primero,
// sin repetidos y como máximo MAX_FOLLOWED. Una clave que hoy es alias de otra ficha sigue valiendo: la
// ficha la reconoce (screen-jugador). Puro e importable en Node: recibe el Storage (o una
// función que lo devuelve) y lo envuelve con safeStorage; si falla, la lista vive en memoria.
import { FOLLOWED_KEY, safeStorage } from './store.js';
import { isPlayerKey } from './links.js';

export const MAX_FOLLOWED = 12;

const isPlayer = p => p !== null && typeof p === 'object' && isPlayerKey(p.id)
  && typeof p.n === 'string' && p.n !== '';

export function cleanFollowed(list) {
  const out = [];
  for (const p of Array.isArray(list) ? list : []) {
    if (out.length === MAX_FOLLOWED) break;
    if (!isPlayer(p) || out.some(q => q.id === String(p.id))) continue;
    out.push({ id: String(p.id), n: p.n });
  }
  return out;
}

export function loadFollowed(storage) {
  const text = safeStorage(storage).getItem(FOLLOWED_KEY);
  if (text === null) return [];
  try {
    return cleanFollowed(JSON.parse(text));
  } catch {
    return [];
  }
}

// Devuelve false si no se pudo guardar.
export function saveFollowed(storage, list) {
  return safeStorage(storage).setItem(FOLLOWED_KEY, JSON.stringify(cleanFollowed(list)));
}

export const isFollowed = (list, id) => (Array.isArray(list) ? list : []).some(p => p.id === String(id));

// Seguir o dejar de seguir: el que ya estaba sale; el nuevo entra el primero.
export function toggleFollowed(list, player) {
  if (!isPlayer(player)) return cleanFollowed(list);
  const id = String(player.id);
  return isFollowed(list, id) ? cleanFollowed(list).filter(p => p.id !== id) : cleanFollowed([{ id, n: player.n }, ...(list || [])]);
}
