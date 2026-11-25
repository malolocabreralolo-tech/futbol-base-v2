// Mundos de fixtures para las pruebas de navegador: la app real (index.html, src/,
// acta.css, fuentes y escudos) con los datos de las fixtures congeladas en lugar de los data-*.js
// vivos y un PORTAL fijo en lugar de src/config.js. Así los smoke y las capturas no cambian cuando
// el bot publica datos ni al activar 2026/27. El «hoy» se fija con el reloj de Playwright.
// Lo usan interaction-smoke.mjs, render-smoke.mjs (estado D) y capturas.mjs.
// Cada mundo solo anuncia en SEASONS las temporadas cuyo archivo sirve, y sirve el que anuncia; y lleva
// los goleadores congelados, la Copa de Campeones en los mundos del 23/09/2026, las cuatro copas de la
// Maspalomas y las actas de A1 y FF1.
import { fixture } from './fixtures/rediseno/load.mjs';
import {
  alevinRaw, archive, cupsRaw, currentAt, dataFile, goleadores, groupLineups, lineupGroups, nextSeasonRaw, pastAlevinRaw, withChampions,
} from './fixtures/rediseno/simulate.mjs';

export const STORE_KEY = 'fb2:almacen';
const DEFAULT_TEAM = { cat: 'prebenjamin', groupId: 'PG2', name: 'Las Mesas Hu.' };
const LAS_MESAS_2526 = { name: 'Las Mesas Hu.', season: '2025-2026', cat: 'prebenjamin', groupId: 'PG2' };
// SEASONS con cada temporada del portal: files() sirve el archivo de cada temporada pasada.
// 2025-26 lleva `detail`, como en el data-seasons.js real: la cronología de las fixtures es suya.
const SEASONS_2526 = [{ name: '2025-2026', current: true, detail: true }, { name: '2024-2025', current: false }, { name: '2023-2024', current: false }];
const SEASONS_2627 = [{ name: '2026-2027', current: true }, { name: '2025-2026', current: false, detail: true }, { name: '2024-2025', current: false }];
// data-health.json de las fixtures es el del 23/09/2026 (D y E). En los mundos de otro día, sus
// fechas pasan a la víspera, la comprobación de la noche anterior: la frescura de la portada nunca
// es de un día posterior al «hoy» del mundo.
const HEALTH_DAY = '2026-09-23';
function healthOn(today) {
  const health = fixture('health');
  if (today === HEALTH_DAY) return health;
  const eve = new Date(Date.parse(`${today}T00:00:00Z`) - 86400000).toISOString().slice(0, 10);
  return JSON.parse(JSON.stringify(health).replaceAll(HEALTH_DAY, eve));
}

// data-goleadores.js: los goleadores congelados (gol-2025-2026), los de fin de temporada de los grupos
// de las fixtures; a mitad de temporada, scorersAt los reduce a su día. En A2 van las 12 filas de Las
// Mesas, y no solo 6.
const GOL = (({ golBenj, golPrebenj }) => ({ benjamin: golBenj, prebenjamin: golPrebenj }))(goleadores());

// La clasificación de un día de temporada. La de las fixtures es la
// final; currentAt quita los marcadores desde `today`, pero no la toca, y a una fecha anterior saldrían
// 28 partidos jugados en marzo. Aquí se recalcula con los resultados del calendario hasta ese día: 3
// puntos la victoria y 1 el empate; por puntos, diferencia y goles a favor, y después el orden
// oficial. Los partidos contra un retirado que no está en el calendario (CD Batán en PG2) cuentan 3–0:
// cada equipo tiene los que la clasificación final le cuenta de más (dos en PG2, uno por vuelta), y
// cada uno cuenta cuando el grupo ha jugado su parte de la temporada (el de la ida, tras la jornada
// 15 de 30). El retirado pierde todos esos. Así, al final sale la clasificación oficial, y a mitad
// de temporada la nota de cobertura cuadra. La jornada de la fuente pasa a ser la última
// con algún resultado.
const FINAL = fixture('current-2025-2026');
function standingsAt(raw, today) {
  for (const cat of ['benjamin', 'prebenjamin']) {
    for (const group of raw[cat]) {
      const rounds = Object.values(raw.history[group.id] || {});
      if (!rounds.length || !group.standings.length) continue;
      const blank = (team, order) => ({ team, order, pts: 0, pj: 0, g: 0, e: 0, p: 0, gf: 0, gc: 0 });
      const rows = new Map(group.standings.map((row, i) => [row[1], blank(row[1], i)]));
      const add = (team, gf, gc) => {
        if (!rows.has(team)) rows.set(team, blank(team, rows.size));
        const r = rows.get(team);
        r.pj += 1;
        r.gf += gf;
        r.gc += gc;
        if (gf > gc) { r.g += 1; r.pts += 3; } else if (gf === gc) { r.e += 1; r.pts += 1; } else r.p += 1;
      };
      const played = (m) => m[3] != null && m[4] != null;
      for (const matches of rounds) for (const m of matches.filter(played)) { add(m[1], m[3], m[4]); add(m[2], m[4], m[3]); }
      const inCalendar = new Set(rounds.flatMap((matches) => matches.flatMap((m) => [m[1], m[2]])));
      const gone = group.standings.map((row) => row[1]).filter((team) => !inCalendar.has(team));
      if (gone.length === 1) {
        // Los partidos de más de cada equipo en la clasificación final: los que jugó contra el retirado.
        const final = FINAL[cat].find((g) => g.id === group.id);
        const finalPlayed = new Map();
        for (const matches of Object.values(FINAL.history[group.id] || {})) {
          for (const m of matches.filter(played)) for (const team of [m[1], m[2]]) finalPlayed.set(team, (finalPlayed.get(team) || 0) + 1);
        }
        const reached = (index) => rounds[index] && rounds[index].some(played);
        for (const row of final ? final.standings : []) {
          if (!inCalendar.has(row[1])) continue;
          const extra = Math.max(0, row[3] - (finalPlayed.get(row[1]) || 0));
          for (let k = 1; k <= extra; k++) {
            if (!reached(Math.ceil((k * rounds.length) / extra) - 1)) continue;
            add(row[1], 3, 0);
            add(gone[0], 0, 3);
          }
        }
      }
      const order = [...rows.values()].sort((a, b) => (gone.includes(a.team) - gone.includes(b.team)) || (b.pts - a.pts)
        || ((b.gf - b.gc) - (a.gf - a.gc)) || (b.gf - a.gf) || (a.order - b.order));
      group.standings = order.map((r, i) => [i + 1, r.team, r.pts, r.pj, r.g, r.e, r.p, r.gf, r.gc, r.gf - r.gc]);
      const lastKey = Object.keys(raw.history[group.id]).filter((key) => raw.history[group.id][key].some(played)).pop();
      if (lastKey) group.jornada = lastKey;
    }
  }
  return raw;
}
const seasonAt = (today) => standingsAt(currentAt(today), today);

// Los goleadores de un día (B12): las fixtures no guardan su evolución. Mientras su equipo no ha
// terminado, los goles y los partidos de cada uno se reducen en la proporción de partidos que el
// equipo lleva jugados (los partidos, al menos 1 y nunca más que los del equipo), y se ordenan por
// goles. Una aproximación verosímil, como la clasificación de los demás equipos.
function scorersAt(raw) {
  const played = (groups, id, team) => groups.find((g) => g.id === id)?.standings.find((row) => row[1] === team)?.[3] ?? null;
  const scale = (cat) => GOL[cat].map((entry) => ({
    ...entry,
    s: entry.s.map(([name, team, goals, games]) => {
      const now = played(raw[cat], entry.id, team);
      const end = played(FINAL[cat], entry.id, team);
      if (now === null || !end || now >= end) return [name, team, goals, games];
      return [name, team, Math.round((goals * now) / end), Math.max(1, Math.min(now, Math.round((games * now) / end)))];
    }).filter((row) => row[2] > 0).sort((a, b) => b[2] - a[2]),
  }));
  return { benjamin: scale('benjamin'), prebenjamin: scale('prebenjamin') };
}

// Los mundos con nombre. today: el día en Canarias; current(): la temporada del portal en crudo;
// myTeam: lo que hay guardado (null: almacén vacío, el equipo por defecto); fail: ficheros que
// responden 503; alevin: sirve data-alevin.js (contrato común de alevín). Sin él, como en la web de
// antes de alevín, data-alevin.js da 404: «sin alevín», y todo lo demás igual.
export const WORLDS = {
  // 01/03/2026: a mitad de temporada, Las Mesas en A (próximo partido en la jornada 18).
  A: { today: '2026-03-01', portalSeason: '2025-2026', current: () => seasonAt('2026-03-01') },
  // 01/10/2026 con 2026/27 activada y sin nada jugado: B.
  B: { today: '2026-10-01', portalSeason: '2026-2027',
    current: () => nextSeasonRaw({ benjamin: ['A1', 'B2', 'FF15'], prebenjamin: ['PG2', 'PG3'] }), gol: false },
  // 03/06/2026: Las Mesas ya jugó la jornada 30 y el grupo no ha terminado: C.
  C: { today: '2026-06-03', portalSeason: '2025-2026', current: () => seasonAt('2026-06-03') },
  // 23/09/2026, los datos de hoy: D con la caja de la temporada siguiente (data-health pendiente). Con
  // la Copa de Campeones, que se jugó del 4 al 10 de junio (en A y C, todavía no).
  D: { today: '2026-09-23', portalSeason: '2025-2026', current: () => withChampions(fixture('current-2025-2026')) },
  // D con «Las Mesas Hu. B» de FF13 guardado: la filial cambia de nombre y se pregunta (E, caso 2b).
  E: { today: '2026-09-23', portalSeason: '2025-2026', current: () => withChampions(fixture('current-2025-2026')),
    myTeam: { name: 'Las Mesas Hu. B', season: '2025-2026', cat: 'benjamin', groupId: 'FF13' } },
  // 2026/27 sin Las Mesas: X.
  X: { today: '2026-10-01', portalSeason: '2026-2027', current: () => nextSeasonRaw({ benjamin: ['A1'], prebenjamin: ['PG3'] }),
    myTeam: LAS_MESAS_2526, gol: false },
  // 14/10/2026, 2026/27 con alevín: data-alevin.js con AL1 y AL2 (tres jornadas jugadas; Las Mesas Hu.
  // en AL1, el homónimo de PG2) y, de 2025-26, data-season-2025-2026-alevin.js con la Segunda Fase A y
  // F y unas Eliminatorias (alevinRaw y pastAlevinRaw de simulate.mjs). 2024-25, sin alevín (un 404).
  L: { today: '2026-10-14', portalSeason: '2026-2027',
    current: () => nextSeasonRaw({ benjamin: ['A1', 'B2', 'FF15'], prebenjamin: ['PG2', 'PG3'] }), gol: false, alevin: true },
  // 14/10/2026, 2026/27 con infantil, cadete y juvenil (parte E2): un grupo de cada una, con equipos y
  // goleadores inventados (mayoresFiles), y su entrada de SEASONS lo dice (`lazy`). Sin data-alevin.js (un
  // 404: alevín, vacío), como B. Para el selector de categoría con seis a 320 px.
  S: { today: '2026-10-14', portalSeason: '2026-2027',
    current: () => nextSeasonRaw({ benjamin: ['A1', 'B2', 'FF15'], prebenjamin: ['PG2', 'PG3'] }), gol: false, mayores: true },
};

// Infantil, cadete y juvenil del mundo S, con la forma de data-<cat>.js (generate_js.generate_lazy_js): un
// grupo de liga de seis equipos inventados con dos jornadas jugadas y sus goleadores, también inventados.
const MAYORES = [['infantil', 'INFANTIL', 'INF', 'INFPG1', 'Preferente GC', 'LIGA INFANTIL PREFERENTE DE GRAN CANARIA'],
  ['cadete', 'CADETE', 'CAD', 'CADNG1', 'Insular GC', 'LIGA CADETE INSULAR GRAN CANARIA'],
  ['juvenil', 'JUVENIL', 'JUV', 'JUV2G1', 'Segunda GC', 'LIGA SEGUNDA JUVENIL GRAN CANARIA']];
function mayoresFiles(js) {
  return Object.fromEntries(MAYORES.map(([cat, groups, s, id, phase, fullName]) => {
    const name = cat[0].toUpperCase() + cat.slice(1);
    const teams = ['Uno', 'Dos', 'Tres', 'Cuatro', 'Cinco', 'Seis'].map((n) => `Club ${name} ${n}`);
    const rounds = { 'Jornada 1': [[0, 1], [2, 3], [4, 5]], 'Jornada 2': [[1, 2], [3, 4], [5, 0]] };
    const history = Object.fromEntries(Object.entries(rounds).map(([key, pairs], k) => [key,
      pairs.map(([h, a], i) => [['2026-10-03', '2026-10-10'][k], teams[h], teams[a], (i + k) % 3, (i + 2 * k) % 2, null, '10:00', null])]));
    const pts = new Map(teams.map((team) => [team, [0, 0, 0, 0, 0, 0, 0]]));
    for (const matches of Object.values(history)) {
      for (const [, home, away, hs, as] of matches) {
        for (const [team, gf, gc] of [[home, hs, as], [away, as, hs]]) {
          const r = pts.get(team);
          r[0] += gf > gc ? 3 : gf === gc ? 1 : 0; r[1] += 1; r[2] += gf > gc; r[3] += gf === gc; r[4] += gf < gc; r[5] += gf; r[6] += gc;
        }
      }
    }
    const standings = [...pts].sort((a, b) => b[1][0] - a[1][0] || (b[1][5] - b[1][6]) - (a[1][5] - a[1][6]))
      .map(([team, r], i) => [i + 1, team, r[0], r[1], Number(r[2]), Number(r[3]), Number(r[4]), r[5], r[6], r[5] - r[6]]);
    const group = { id, name: 'Grupo 1', fullName: `${fullName} - GRUPO 1`, phase, island: 'grancanaria', url: null, jornada: 'Jornada 2', standings, matches: [], standingsKind: 'source' };
    const gol = [{ id, g: `${groups} ${phase.toUpperCase()} - GRUPO 1`, s: teams.map((team, i) => [`PRUEBA, JUGADOR ${name.toUpperCase()} ${i + 1}`, team, 6 - i, 2]) }];
    return [`data-${cat}.js`, js([[groups, [group]], [`${s}_STATS`, { groups: 1, teams: teams.length }], [`HISTORY_${s}`, { [id]: history }],
      [`GOL_${s}`, gol], [`ESTADOS_${s}`, {}], [`EQUIPOS_${s}`, {}], [`CAMPOS_${s}`, {}]])];
  }));
}

// 2025-26 terminada, con la forma de data-season-<S>.js, para los mundos de 2026/27 (B y X): la fixture
// final con su Copa de Campeones, cada grupo con su calendario de HISTORY como `jornadas`.
function finishedSeason() {
  const raw = withChampions(FINAL);
  const group = (g) => ({ id: g.id, name: g.name, fullName: g.fullName, phase: g.phase, island: g.island,
    current_jornada: g.jornada ?? null, standings: g.standings, jornadas: raw.history[g.id] || {} });
  return { name: '2025-2026', current: false, benjamin: raw.benjamin.map(group), prebenjamin: raw.prebenjamin.map(group) };
}
// El archivo de una temporada pasada: el de las fixtures (2024-25 y 2023-24) o 2025-26 terminada.
const pastSeason = (name) => (name === '2025-2026' ? finishedSeason() : archive(name));

// Los ficheros que sirve un mundo, por su nombre (sin ?v=): el cuerpo y su tipo. SEASONS anuncia las
// temporadas cuyo archivo se sirve, y solo esas: Temporadas, la Trayectoria de
// Equipo o el selector de Explorar nunca llevan a un fichero que da 404.
function files(w) {
  const raw = w.current();
  const cups = cupsRaw({ extra: true });
  const gol = w.gol === false ? { benjamin: [], prebenjamin: [] } : scorersAt(raw);
  const listed = w.portalSeason === '2026-2027' ? SEASONS_2627 : SEASONS_2526;
  // El mundo S dice en SEASONS qué perezosas tiene su temporada (generate_js.season_lazy_keys).
  const seasons = w.mayores ? listed.map((s) => (s.current ? { ...s, lazy: MAYORES.map(([cat]) => cat) } : s)) : listed;
  const next = w.portalSeason === '2026-2027' ? '2027-2028' : '2026-2027';
  const js = (pairs) => ({ type: 'text/javascript', body: pairs.map(([name, value]) => `const ${name}=${JSON.stringify(value)};`).join('\n') + '\n' });
  const archived = Object.fromEntries(seasons.filter((s) => !s.current)
    .map(({ name }) => [`data-season-${name}.js`, js([[`SEASON_${name.replace('-', '_')}`, pastSeason(name)]])]));
  return {
    'src/config.js': { type: 'text/javascript', body: `export const PORTAL = ${JSON.stringify({ season: w.portalSeason, nextSeason: next, defaultTeam: DEFAULT_TEAM, timeZone: 'Atlantic/Canary' }, null, 2)};\n` },
    'data-benjamin.js': js([['BENJAMIN', raw.benjamin]]),
    'data-prebenjamin.js': js([['PREBENJAMIN', raw.prebenjamin]]),
    'data-history.js': js([['HISTORY', raw.history]]),
    'data-goleadores.js': js([['GOL_BENJ', gol.benjamin], ['GOL_PREBENJ', gol.prebenjamin]]),
    'data-shields.js': js([['SHIELDS', fixture('shields')]]),
    'data-seasons.js': js([['SEASONS', seasons]]),
    'data-maspalomas-cup-2026.js': js([['MASPALOMAS_CUP_BENJAMIN', cups.benjamin], ['MASPALOMAS_CUP_PREBENJAMIN', cups.prebenjamin]]),
    ...archived,
    'data-matchdetail.js': js([['MATCH_DETAIL', fixture('matchdetail')]]),
    // El alevín, perezoso: el de la temporada del portal y el de 2025-26 (contrato común, puntos 4 y 5).
    ...(w.mayores ? mayoresFiles(js) : {}),
    ...(w.alevin ? {
      'data-alevin.js': { type: 'text/javascript', body: dataFile(alevinRaw({ season: w.portalSeason, today: w.today })) },
      'data-season-2025-2026-alevin.js': js([['SEASON_2025_2026_ALEVIN', pastAlevinRaw('2025-2026')]]),
    } : {}),
    // Las actas, por grupo: los que tienen (A1 y FF1); el de cualquier otro, un 404 (sin actas).
    ...Object.fromEntries(lineupGroups('2025-2026').map((g) => [`data-lineups-2025-2026-${g}.js`,
      js([[`LINEUPS_2025_2026_${g}`, groupLineups('2025-2026', g)]])])),
    'data-health.json': { type: 'application/json', body: JSON.stringify(healthOn(w.today)) },
  };
}

// Lo que sirve el mundo `name`, por fichero: { body, type }. Lo usan useWorld y su prueba
// (test_rediseno_mundos.mjs).
export function worldFiles(name) {
  const w = WORLDS[name];
  if (!w) throw new Error(`mundo desconocido: ${name}`);
  return files(w);
}

// Instala el mundo `name` en un contexto de Playwright: rutas de los datos y de config.js (el resto
// lo sirve el servidor estático de siempre), el reloj en su día (a mediodía de Canarias) y, si el
// mundo lo trae, mi equipo guardado. `fail`: ficheros que responden 503 (la caja de error). `myTeam`:
// otro equipo guardado en lugar del del mundo (Guayarmina en A1, la plantilla de la portada).
export async function useWorld(context, name, { fail = [], myTeam = null } = {}) {
  const w = WORLDS[name];
  if (!w) throw new Error(`mundo desconocido: ${name}`);
  const served = files(w);
  await context.route(/\/(src\/config\.js|data-[\w.-]+\.(?:js|json))(\?.*)?$/, (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\//, '');
    if (fail.includes(path)) return route.fulfill({ status: 503, contentType: 'text/plain', body: 'no disponible' });
    const file = served[path];
    return file ? route.fulfill({ status: 200, contentType: file.type, body: file.body })
      : route.fulfill({ status: 404, contentType: 'text/plain', body: 'no está en el mundo de fixtures' });
  });
  await context.clock.setFixedTime(new Date(`${w.today}T12:00:00Z`));
  const saved = myTeam || w.myTeam;
  if (saved) {
    await context.addInitScript(([key, value]) => {
      try { if (!localStorage.getItem(key)) localStorage.setItem(key, value); } catch { /* almacén bloqueado */ }
    }, [STORE_KEY, JSON.stringify({ myTeam: saved, recent: [] })]);
  }
  return w;
}
