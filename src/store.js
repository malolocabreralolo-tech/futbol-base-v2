// Almacén persistente de v2, STORE_KEY: { myTeam, recent }.
//   myTeam = { name, season, cat, groupId }
//   recent = [{ s, g, t }], lo último visto primero, sin repetidos y como máximo 8.
//
// Módulo puro e importable en Node, sin DOM ni globales del navegador: recibe
// el Storage por parámetro (o una función que lo devuelve) y lo envuelve con
// safeStorage, así que un almacenamiento que falla (modo privado, cookies
// bloqueadas, cuota agotada o ninguno) deja la app con los valores por defecto
// en memoria. Solo borra con «Borrar datos de esta app» (clearStore), y solo
// claves de v2: v1 comparte el origen, y sus claves (las V1_* y LEGACY_KEY)
// nunca se escriben ni se borran, y solo las lee, una vez, importFromV1; las
// antiguas `season`, `cat` y `theme`, ni se leen.
import { normalizeTeamName } from './state.js';
import { CATEGORIES } from './model.js';

export const STORE_KEY = 'fb2:almacen';
// Los jugadores seguidos (followed.js) van en su propia clave: «Borrar datos» también la borra.
export const FOLLOWED_KEY = 'fb2:jugadores';
// La marca de que ya se leyó v1 en este navegador: «Borrar datos» no la quita, para que no vuelva lo de v1.
export const IMPORTED_KEY = 'fb2:importado';
// Las de v1, en el mismo origen: solo las lee importFromV1, una vez.
export const V1_STORE_KEY = 'futbol-base:v2';            // solo lectura
export const V1_FOLLOWED_KEY = 'futbol-base:jugadores';  // solo lectura
export const LEGACY_KEY = 'futbol-base:favorites:v1';    // solo lectura, como hasta ahora
export const MAX_RECENT = 8;

// Las categorías de la app anterior (favorites.js, v1), que nunca tuvo alevín; las de la v2 son las de
// la app (CATEGORIES de model.js, alevín incluido: si no, un equipo alevín guardado se descartaba en
// silencio y volvía el equipo por defecto en cada carga, r3.md §3).
const V1_CATS = ['benjamin', 'prebenjamin'];
const isText = value => typeof value === 'string' && value !== '';
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);

// `storage` es el Storage o una función que lo devuelve: con las cookies
// bloqueadas, solo con leer el Storage del navegador ya se lanza un error, y
// así también se captura.
export function safeStorage(storage) {
  const target = () => (typeof storage === 'function' ? storage() : storage);
  return {
    getItem(key) {
      try {
        const value = target().getItem(key);
        return typeof value === 'string' ? value : null;
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        target().setItem(key, value);
        return true;
      } catch {
        return false;
      }
    },
    removeItem(key) {
      try {
        target().removeItem(key);
        return true;
      } catch {
        return false;
      }
    },
  };
}

function parseJSON(text) {
  if (text === null) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
const readJSON = (store, key) => parseJSON(store.getItem(key));

// Equipo de favorites.js (v1) y su clave `selected` (favoriteKey); mi equipo de la v2.
const isV1Team = team => isObject(team) && isText(team.name) && V1_CATS.includes(team.cat) && isText(team.groupId);
const v1Key = team => `${team.cat}|${team.groupId}|${normalizeTeamName(team.name)}`;
const isMyTeam = team => isObject(team) && isText(team.name) && CATEGORIES.includes(team.cat) && isText(team.groupId)
  && isText(team.season);
const isRecent = entry => isObject(entry) && isText(entry.s) && isText(entry.g) && isText(entry.t);

// Conserva el orden de `list`: descarta inválidos y repetidos, y corta en MAX_RECENT.
function cleanRecent(list) {
  const out = [];
  for (const entry of Array.isArray(list) ? list : []) {
    if (out.length === MAX_RECENT) break;
    if (!isRecent(entry) || out.some(e => e.s === entry.s && e.g === entry.g && e.t === entry.t)) continue;
    out.push({ s: entry.s, g: entry.g, t: entry.t });
  }
  return out;
}

// v1 = { teams: [{name, cat, groupId}], selected: 'cat|groupId|normalizeTeamName(name)' }.
// La temporada es el literal de la única con favoritos v1, nunca la del portal:
// si el portal ya está en otra, resolveMyTeam aplica el paso 1 (spec §6.3).
// Un grupo de torneo (MC*) se devuelve tal cual: los torneos no están en la
// temporada (van en Cups), así que resolveMyTeam no encuentra el grupo y aplica
// el paso 2 (o el 1, si la temporada ya cambió).
export function migrateV1(v1, legacySeason = '2025-2026') {
  if (!isObject(v1) || !Array.isArray(v1.teams)) return null;
  // Lo mismo que leía restoreFavorites (favorites.js): equipos válidos, hasta 30.
  const teams = v1.teams.filter(isV1Team).slice(0, 30);
  if (!teams.length) return null;
  const selected = teams.find(team => v1Key(team) === v1.selected) || teams[0];
  return {
    myTeam: { name: selected.name, season: legacySeason, cat: selected.cat, groupId: selected.groupId },
    recent: cleanRecent(teams
      .filter(team => v1Key(team) !== v1Key(selected))
      .map(team => ({ s: legacySeason, g: team.groupId, t: team.name }))),
  };
}

export function loadStore(storage, { defaultTeam, portalSeason }) {
  const store = safeStorage(storage);
  const fallback = { name: defaultTeam.name, season: portalSeason, cat: defaultTeam.cat, groupId: defaultTeam.groupId };
  const saved = readJSON(store, STORE_KEY);
  if (isObject(saved)) {
    const t = saved.myTeam;
    return {
      myTeam: isMyTeam(t) ? { name: t.name, season: t.season, cat: t.cat, groupId: t.groupId } : fallback,
      recent: cleanRecent(saved.recent),
    };
  }
  return { myTeam: fallback, recent: [] };
}

// Lee v1 una sola vez en este navegador, para no volver a elegir mi equipo ni los seguidos: copia tal
// cual lo que a v2 le falte (loadStore y loadFollowed lo validan al leerlo). La marca va antes de
// copiar, porque es mejor quedarse con el equipo por defecto que releer v1 a medias en cada carga.
// Devuelve qué copió y nunca lanza. portalSeason no cambia nada: los favoritos antiguos llevan su
// propia temporada (migrateV1).
export function importFromV1(storage, { portalSeason } = {}) {
  const store = safeStorage(storage);
  const copied = { store: false, followed: false };
  if (store.getItem(IMPORTED_KEY) !== null || !store.setItem(IMPORTED_KEY, '1')) return copied;
  if (store.getItem(STORE_KEY) === null) {
    const v1Store = store.getItem(V1_STORE_KEY);
    if (isObject(parseJSON(v1Store))) {
      copied.store = store.setItem(STORE_KEY, v1Store);
    } else {
      const migrated = migrateV1(readJSON(store, LEGACY_KEY));
      if (migrated) copied.store = saveStore(storage, migrated);
    }
  }
  if (store.getItem(FOLLOWED_KEY) === null) {
    const v1Followed = store.getItem(V1_FOLLOWED_KEY);
    if (Array.isArray(parseJSON(v1Followed))) copied.followed = store.setItem(FOLLOWED_KEY, v1Followed);
  }
  return copied;
}

// Devuelve false si no se pudo guardar (la app sigue con el estado en memoria).
export function saveStore(storage, state) {
  return safeStorage(storage).setItem(STORE_KEY, JSON.stringify({ myTeam: state.myTeam, recent: state.recent }));
}

export function addRecent(state, entry) {
  if (!isRecent(entry)) return state;
  return { ...state, recent: cleanRecent([{ s: entry.s, g: entry.g, t: entry.t }, ...(state.recent || [])]) };
}

// «Borrar datos de esta app»: el almacén y los jugadores seguidos. Las claves de v1 y las antiguas
// `season`, `cat` y `theme` son de v1, que comparte el origen, y se quedan; IMPORTED_KEY también, para
// que tras borrar y recargar salga el equipo por defecto y no otra vez el de v1.
// Nunca storage.clear(): el origen (malolocabreralolo-tech.github.io) es de más proyectos. Devuelve
// false si alguna no se pudo borrar; nunca lanza.
export function clearStore(storage) {
  const store = safeStorage(storage);
  return [STORE_KEY, FOLLOWED_KEY].map((key) => store.removeItem(key)).every(Boolean);
}
