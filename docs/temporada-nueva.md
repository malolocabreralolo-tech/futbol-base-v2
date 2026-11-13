# Arranque de una temporada nueva

`src/config.js` contiene la configuración compartida por navegador e importador: temporada, siguiente temporada, equipo inicial y zona horaria. El importador exige que esa temporada coincida con la única fila `is_current=1` de SQLite.

## Lo que pasó en 2026/27 (octubre de 2026)

futbolaspalmas.com migró a una app nueva (`directo.php?liga_id=N`, con API JSON: `?action=get_full_calendar&liga_id=N` y `?action=get_live_data&liga_id=N`) y sus URLs de siempre se quedaron sirviendo 2025/26 congelado. A 3 de octubre la app aún no publicaba benjamín ni prebenjamín; la federación sí había publicado grupos y calendario: la temporada 2026/27 se activó desde **FIFLP** (abajo, «Activar desde la federación»), y el bot la pone al día con `scripts/update_fiflp.py`. Después la app publicó también benjamín y prebenjamín de Gran Canaria (además de alevín), y desde el 7 de octubre el bot la lee en cada pasada (`scripts/fetch_fp_app.py` e `import_fp_app.py`): estado de cada partido, equipación y qué significa cada zona de la tabla, sin cambiar nunca un marcador. Alevín solo con `FP_APP_CATS` ([alevin.md](alevin.md)).

## Activar desde la federación (FIFLP)

FIFLP contesta vacío a las IPs domésticas: el scrape va en GitHub Actions y todo lo demás en local.

```bash
# 0. El reloj de las pasadas (reloj.yml), activo: GitHub desactiva los workflows con schedule de un repositorio
#    público tras 60 días sin commits, y en verano el bot casi no hace (docs/federacion.md, «El reloj de las
#    pasadas»). Si sale «disabled_inactivity», no hay pasadas del bot (ni nada en rojo):
gh workflow list --all -R malolocabreralolo-tech/futbol-base-v2 | grep -i reloj
gh workflow enable reloj.yml -R malolocabreralolo-tech/futbol-base-v2   # solo si estaba desactivado
# 1. Catálogo de competiciones de la temporada nueva (CodTemporada = año inicial − 2004)
gh workflow run discover-fiflp.yml -R malolocabreralolo-tech/futbol-base-v2   # escribe scripts/fiflp_comps_catalog.json
# 2. Grupos, clasificaciones y calendarios (tanda = CodTemporada; las competiciones
#    salen del catálogo: CATALOG_SEASONS en scripts/fetch_fiflp_islas.py)
gh workflow run fetch-fiflp-islas.yml -R malolocabreralolo-tech/futbol-base-v2 -f temporada=22   # escribe scripts/fiflp_islas_22_raw.json
git pull
# 3. Manifiesto (códigos y fases con el convenio de 2025/26; aborta si una competición no encaja)
python3 scripts/fiflp_manifest.py scripts/fiflp_islas_22_raw.json 2026-2027 --team "Las Mesas" --cat prebenjamin > docs/temporadas/2026-2027.json
# 4. Verificar y activar con la evidencia del raw (nombres reconciliados con la base)
python3 scripts/activate_season.py docs/temporadas/2026-2027.json --fiflp-raw scripts/fiflp_islas_22_raw.json
python3 scripts/activate_season.py docs/temporadas/2026-2027.json --fiflp-raw scripts/fiflp_islas_22_raw.json --apply
```

Los grupos quedan con su URL de la federación. `fetch_futbolaspalmas.py` los salta y, con `FIFLP_UPDATE=1` (lo pone `update.yml`, que instala Playwright), llama a `update_fiflp.py`: clasificación oficial (no ofuscada) con el mismo guard de no-regresión, y solo las jornadas recientes, próximas, pendientes o nuevas. Los marcadores de FIFLP están ofuscados: cada uno mezcla texto visible, dígitos pintados por CSS (`::before`/`::after`) y señuelos ocultos (`display:none`, el 4.º argumento de `ntype`). `fetch_fiflp_2425._scores_from_browser` lee lo que se pinta, en orden; aun así, algunas variantes cuelan una cifra de más (Haría 41-2 por 4-2). Por eso: un marcador nuevo entra siempre; uno guardado solo se cambia si el nuevo cuadra mejor con los goles de la clasificación oficial (que no está ofuscada), y `reconcile_with_table` corrige los de dos cifras que la tabla desmiente quitando una cifra. Solo cuentan los equipos cuya tabla tiene tantos partidos como resultados en la base: una tabla atrasada no dice nada. Para ver una página tal cual: `gh workflow run debug-fiflp-copa.yml -R malolocabreralolo-tech/futbol-base-v2 -f comp=… -f grupo=… -f season=22 -f scores=1` (vuelca al log cada dígito con sus estilos). Cuando la federación publique una fase nueva (Segunda Fase, Fase 2 insular; el bot la detecta solo, la apunta en `newCompetitions` de `data-health.json` y abre una issue con su código: ver [federacion.md](federacion.md)) se repiten los pasos 1-2 (ampliando `CATALOG_SEASONS`/la tanda si hace falta; con `-f ids=<ids nuevos>` solo se bajan esas y se añaden al raw de la tanda) y se añaden sus grupos a la temporada en curso, sin cambiar de temporada. La Segunda Fase admite cualquier letra («FASE LIGA F» o «SEGUNDA FASE F» → `F1`…, «Segunda Fase F») las eliminatorias tienen código propio (`EL1`…, `PEL1`…, `ALEL1`…; fase «Eliminatorias», que la web trata como copa) y la Copa Benjamín de Gran Canaria (2026-27) es `CGC1`…, fase «Copa Gran Canaria» (una copa insular en la web; nunca `BC…` ni `PCC…`, que son la Copa de Campeones y `synth_copa_campeones.py` les reescribe la tabla). La primera pasada del bot sobre un grupo recién añadido lee todas sus jornadas ya jugadas, para tener el código de sus actas aunque sean de hace más de 10 días (`BACK_DAYS`). Con muchos grupos el bot no los lee todos en cada pasada: los reparte con una rotación sin estado (los prioritarios siempre; los demás por turnos: sin el cupo de la federación, cada grupo al menos una vez cada cuatro pasadas; con él, ~15 páginas por IP, en ~una semana: [federacion.md](federacion.md)). Alevín de Gran Canaria va con su propia tanda (`22al`) y sus códigos `AL…`: [alevin.md](alevin.md).

### Añadir una fase a mitad de temporada: con el bot parado

`activate_season.py --add --apply` escribe en la base viva (`futbolbase.db`, binaria) y el bot comitea en `main` cada 1-2 h: si los dos la cambian, el conflicto no se fusiona. Por eso todo, desde el catálogo (paso 1) hasta el push, va en una ventana con el bot parado: se para el reloj y se espera a que no quede ninguna «Actualización automática» en marcha; al acabar, con las suites en verde y el push hecho, se vuelve a activar. Si algo falla por el camino, no se empuja nada y se reactiva el reloj igual.

```bash
gh workflow disable reloj.yml -R malolocabreralolo-tech/futbol-base-v2   # y esperar a que no haya ninguna pasada en marcha
# pasos 1-2 de arriba (catálogo y raw, con -f ids=<ids nuevos>) y git pull
python3 scripts/fiflp_manifest.py scripts/fiflp_islas_22_raw.json 2026-2027 --comps <ids nuevos> > fase.json
python3 scripts/activate_season.py fase.json --fiflp-raw scripts/fiflp_islas_22_raw.json --add          # verifica
python3 scripts/activate_season.py fase.json --fiflp-raw scripts/fiflp_islas_22_raw.json --add --apply  # escribe y genera
python3 -m pytest scripts/tests/ -q && node --test scripts/tests/test_*.mjs                            # y la sonda de «otra-…» (abajo)
git add futbolbase.db data-*.js index.html sw.js && git commit && git push                             # git pull antes, si hace falta
gh workflow enable reloj.yml -R malolocabreralolo-tech/futbol-base-v2
```

`--comps` no es opcional al añadir una fase: `fiflp_manifest.py` pasa `comp_meta` a **todas** las competiciones del raw para ordenarlas, y el raw de la tanda trae también las que ya están activadas y las que aún no tienen convenio de código (un torneo, una copa nueva…). Una sola sin convenio aborta el manifiesto entero («competición sin convenio de código: …»); con `--comps <ids>` solo cuentan las pedidas.

## Descubrir y comprobar candidatos

```bash
python3 scripts/discover_temporada.py --todas
```

La sonda no escribe en la base. Compara equipos y muestra enlaces candidatos. Una tabla ausente o unos equipos diferentes requieren contraste; no activan automáticamente ninguna temporada.

Crear un JSON con los grupos reales encontrados. Este ejemplo solo ilustra el formato; el nombre, equipo, categoría, fase y URL deben contrastarse antes de usarlo:

```json
{
  "season": "2026-2027",
  "defaultTeam": { "cat": "prebenjamin", "groupId": "PG1", "name": "NOMBRE EXACTO VERIFICADO" },
  "groups": [
    { "id": "PG1", "cat": "prebenjamin", "name": "Grupo 1", "phase": "Gran Canaria", "island": "grancanaria", "url": "https://futbolaspalmas.com/1prebenjamin1/" }
  ]
}
```

Los códigos deben ser únicos entre categorías, porque el historial se consulta por código. Las categorías admitidas son `benjamin`, `prebenjamin` y `alevin` (solo Gran Canaria, con códigos `AL…`: [alevin.md](alevin.md)); la activación crea en la base la que falte. Las islas son `grancanaria`, `lanzarote` y `fuerteventura`. Incluir todos los grupos confirmados que se vayan a publicar, con las fases y nombres reales de la fuente.

```bash
python3 scripts/activate_season.py temporada-2026-2027.json
```

Este comando verifica sin modificar archivos ni base. Descarga clasificación y calendario de cada grupo y exige:

- Temporada inmediatamente posterior a la publicada.
- Clasificación y partidos con año explícito.
- Todas las fechas entre julio del primer año y junio del segundo.
- Equipos coincidentes entre calendario y clasificación.
- Equipo inicial presente en el grupo y categoría indicados.

Un calendario vacío, mezclado con otro año o aún de 2025/26 impide continuar.

## Activar y publicar

Ejecutar cuando no haya otra importación en curso:

```bash
python3 scripts/activate_season.py temporada-2026-2027.json --apply
python3 -m pytest scripts/tests/ -q
node --test scripts/tests/test_*.mjs
node scripts/tests/render-smoke.mjs
node scripts/tests/interaction-smoke.mjs
```

`--apply` cambia `src/config.js`, que es código, y recalcula él solo `CODIGO` (con la función de `scripts/codigo.py`), la versión del código que lee el arranque de `index.html` (Plan B3, decisión 156): ya no hace falta ejecutar `scripts/codigo.py` a mano después de activar. `pytest` y `node --test` se ejecutan, y tienen que salir en verde, antes de empujar la activación: el bot (`update.yml`) los ejecuta antes de comitear los datos y, si alguno falla, se para en rojo sin avisar y deja de publicar. Una activación por partes (solo una categoría, como en el ejemplo, que solo trae prebenjamín) es válida, y la suite tiene que seguir en verde con ella.

Después de activar, fija la línea base de desvío de marcadores para que la temporada que acaba de cerrarse quede protegida por el vigilante `test_score_deviation_does_not_regress`:

```bash
python3 scripts/score_deviation.py --write-baseline
```

Comprueba también, a mano, que ninguna fase de la temporada nueva cae en «otra-…», la clave que da `competitionKey` (`src/model.js`) a una fase que no reconoce. Ninguna prueba lo detecta, y a propósito: `phases.json` y `phases-archivo.json` (las de las temporadas archivadas, 2017-18 a 2020-21, que también deben dar «0 en otra-…»; se comprueban con la misma sonda sobre su `data-season-<S>.js`) están congeladas, y una fase nueva de la fuente no debe bloquear al bot. Pero una fase sin clasificar recibe de `PHASE_LEVEL` (`src/model.js`, el que usa `src/myteam.js`) el nivel de la Primera Fase, así que una «Tercera Fase» nunca provocaría un cambio de fase. La sonda mira las tres categorías, alevín incluido:

```bash
node --input-type=module -e "
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { PORTAL } from './src/config.js';
import { buildSeason } from './src/model.js';
const data = vm.createContext({});
for (const file of ['data-benjamin.js', 'data-prebenjamin.js', 'data-alevin.js', 'data-history.js'])
  vm.runInContext(readFileSync(file, 'utf8').replace(/^const /gm, 'var '), data);
const season = buildSeason({ name: PORTAL.season, current: true, benjamin: data.BENJAMIN, prebenjamin: data.PREBENJAMIN, alevin: data.ALEVIN, history: data.HISTORY });
const otras = season.groups.filter(group => /(^|-)otra-/.test(group.compKey));
for (const group of otras) console.log(group.cat, group.id, group.phase, '→', group.compKey);
console.log(season.name + ':', season.groups.length, 'grupos,', otras.length, 'en otra-…');
"
```

La última línea debe acabar en «0 en otra-…». Si sale algún grupo (fuera de Gran Canaria, la clave lleva delante la isla, como `lanzarote-otra-…`), añade su fase a `PHASE_TABLE` y, si va después de la Primera Fase, a `PHASE_LEVEL`, los dos en `src/model.js`, con sus pruebas.

La activación vuelve a verificar las fuentes. Guarda una copia en `backups/temporada-FECHA/`, prepara la nueva base y genera los archivos en un directorio temporal. Solo tras completar esa generación reemplaza los archivos de trabajo. No publica ni hace push por su cuenta.

Se conservan partidos, clasificaciones, goleadores y actas anteriores. Se crea `data-season-2025-2026.js` y la Copa Maspalomas 2026 permanece asociada a 2025/26, también al consultar el archivo. En `sw.js`, `SEASON_FILES` gana ese archivo (lo pone `activate_season.season_files_for` y lo mantiene también `generate_js.py`, `sync_season_files`, que lo iguala a los `data-season-<S>.js` que escribe, de la más nueva a la más vieja) y cambia la plantilla que la app instalada guarda para abrir sin conexión, `data-lineups-2025-2026.js`, por la de la temporada nueva, `data-lineups-2026-2027.js`, aunque todavía no exista: sin actas no hay plantilla; cuando lleguen, la app la guardará al abrirla con red, y el SW, en su versión siguiente (Plan B5, decisión 2). Los favoritos siguen guardados: si un equipo cambia de grupo o categoría, la portada permite elegir su nueva ubicación.

Un equipo nuevo puede traer un escudo nuevo, y un escudo se puede cambiar en cualquier momento. `data-shields.js` se mantiene a mano, y la app pide primero la miniatura de cada escudo, `escudos/s/<nombre sin extensión>.png` (spec §5.4; Plan B4, Tarea 4). Se copia el original a `escudos/`, se añade su entrada a `data-shields.js` y se generan las miniaturas, con Pillow (solo en local):

```bash
python3 scripts/build_crests.py
python3 scripts/build_crests.py --check
```

La segunda orden tiene que acabar en «al día». Se comitean los cuatro: el original, su miniatura, `data-shields.js` y `sw.js`, en cuya línea 2 la primera orden escribe el sello nuevo de `escudos/` (`CRESTS_CACHE`, la caché de los escudos de la app instalada: con otro sello, los móviles la cambian y piden el escudo nuevo; Plan B5, decisión 1). Conviene traer `main` antes de comitear: si `sw.js` choca en sus dos primeras líneas, la 1 (`CACHE_NAME`) es la del bot y la 2 (`CRESTS_CACHE`) la que acaba de escribir esta orden; la resolución está en [rediseno-rebase.md](rediseno-rebase.md). `scripts/tests/test_build_crests.py` lo exige: sin la miniatura, con una que se quedó atrás o con el sello de antes, `Tests` sale en rojo. El bot no: dentro de él esas pruebas se saltan, porque nunca toca `escudos/` y no puede dejar de publicar los datos por un escudo. `scripts/trim_shields.py`, si trae escudos nuevos de la federación, ya genera sus miniaturas al terminar.

Comprobar ambas categorías, el equipo inicial y al menos un partido del archivo en el navegador. Incorporar los archivos generados, `src/config.js`, `data-health.json`, `index.html`, `sw.js` y la base al commit de publicación. No incorporar las copias de seguridad. GitHub Pages publica desde `main`.

## Protecciones de la actualización habitual

El importador rechaza clasificaciones vacías, retrocesos grandes de jornada y cambios fuertes de equipos. Conserva marcadores conocidos si la fuente difiere y señala la discrepancia en el informe. Las etiquetas `3` y `Jornada 3` comparten la identidad ya guardada para evitar duplicar encuentros.

El informe distingue la última consulta de fuentes del último cambio en datos deportivos. `data-health.json` solo se reescribe si cambia algo con significado (estado o mensaje de un grupo, versión de los datos publicados) o si su última comprobación publicada tiene más de 24 horas; sin eso, una ejecución sin marcadores nuevos no genera commit. Las pruebas de la actualización automática bloquean la publicación de datos incoherentes.
