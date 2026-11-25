#!/usr/bin/env python3
"""
check_missing_shields.py - Lista equipos sin escudo en data-shields.js.
Util para identificar equipos historicos que necesitan escudo manual.
"""
import json, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categorias import DB_NAME  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIELDS_PATH = os.path.join(ROOT, 'data-shields.js')
SEASONS_PATH = os.path.join(ROOT, 'data-seasons.js')
# Las seis categorías de la web (categorias.DB_NAME), no unas cuantas a mano. La temporada en curso, cada una
# en data-<cat>.js (const BENJAMIN, PREBENJAMIN, ALEVIN, INFANTIL...: el nombre de la base); las pasadas,
# benjamín y prebenjamín en data-season-<S>.js y las perezosas (alevín, infantil, cadete y juvenil;
# docs/alevin.md §5) en data-season-<S>-<cat>.js, que solo existe si la temporada la tiene.
EN_SU_TEMPORADA = ('benjamin', 'prebenjamin')

STRIP = re.compile(r'\b(CF|UD|CD|AD|SD|AFC|SC|CP|CE|CEF|SSD|ATLETICO|ATL)\b', re.IGNORECASE)

def normalize(name):
    """Mirror of src/state.js::normalizeTeamName — keep both in sync.

    Pipeline (same as JS): NFD accent-strip -> strip quotes (straight+curly),
    dots and commas -> strip club tokens (STRIP) -> lowercase -> collapse
    whitespace. Verified equivalent against the JS side on every team name in
    data-benjamin/prebenjamin + the season files + SHIELDS keys.
    """
    # Strip diacritics/accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # Strip punctuation and common suffixes
    name = re.sub(r"['\",.‘’“”]", '', name)
    name = STRIP.sub('', name)
    return re.sub(r'\s+', ' ', name.lower()).strip()

def lazy_of_season(sname, cat):
    """Los grupos de una categoría perezosa (alevín, infantil, cadete o juvenil) de una temporada pasada
    (data-season-<S>-<cat>.js), o [] si la temporada no la tiene."""
    path = os.path.join(ROOT, f'data-season-{sname}-{cat}.js')
    if not os.path.exists(path):
        return []
    try:
        return load_json_var(path, f"SEASON_{sname.replace('-', '_')}_{DB_NAME[cat]}").get(cat, [])
    except Exception as e:
        print(f"[{sname}] WARNING: parse error in {path}: {e}")
        return []


def current_of(cat):
    """Los grupos de una categoría en la temporada en curso (data-<cat>.js), o [] si el fichero no está (una
    web de antes de esa categoría)."""
    path = os.path.join(ROOT, f'data-{cat}.js')
    return load_json_var(path, DB_NAME[cat]) if os.path.exists(path) else []


def load_json_var(path, varname):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    m = re.search(r'const\s+' + re.escape(varname) + r'\s*=\s*', content)
    if not m:
        raise ValueError(f"Variable '{varname}' not found in {path}")
    rest = content[m.end():]
    # Use raw_decode to consume only the first JSON value
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(rest.lstrip())
    return obj

def has_shield(name, shields, shields_norm):
    # 1. Exact
    if name in shields:
        return True
    # 2. Normalized
    n = normalize(name)
    if n and n in shields_norm:
        return True
    # 3. Substring
    if len(n) >= 4:
        for k in shields:
            kn = normalize(k)
            if len(kn) >= 4 and (n in kn or kn in n):
                return True
    return False

def teams_in_groups(groups):
    out = set()
    for g in groups:
        for row in g.get('standings', []):
            out.add(row[1])
    return out

def main():
    shields = load_json_var(SHIELDS_PATH, 'SHIELDS')
    shields_norm = {}
    for k in shields:
        n = normalize(k)
        if n and n not in shields_norm:
            shields_norm[n] = shields[k]

    seasons = load_json_var(SEASONS_PATH, 'SEASONS')
    print(f"Shields loaded: {len(shields)}\n")

    # Build {season_name: {cat: [groups]}}
    season_groups = {}
    for s in seasons:
        sname = s['name']
        if s.get('current'):
            # La temporada en curso, en data-<cat>.js.
            try:
                season_groups[sname] = {cat: current_of(cat) for cat in DB_NAME}
            except Exception as e:
                print(f"[{sname}] WARNING: can't load current data: {e}")
                season_groups[sname] = {cat: s.get(cat, []) for cat in EN_SU_TEMPORADA}
        else:
            # Historical seasons may be embedded in seasons or in data-season-XXXX.js
            ben = s.get('benjamin', [])
            pre = s.get('prebenjamin', [])
            if not ben and not pre:
                slug = sname.replace('-', '_')
                path = os.path.join(ROOT, f'data-season-{sname}.js')
                if os.path.exists(path):
                    try:
                        d = load_json_var(path, f'SEASON_{slug}')
                        ben = d.get('benjamin', [])
                        pre = d.get('prebenjamin', [])
                    except Exception as e:
                        print(f"[{sname}] WARNING: parse error in {path}: {e}")
            season_groups[sname] = {'benjamin': ben, 'prebenjamin': pre,
                                    **{cat: lazy_of_season(sname, cat) for cat in DB_NAME if cat not in EN_SU_TEMPORADA}}

    grand_missing = set()
    for sname, cats in season_groups.items():
        for cat, groups in cats.items():
            if not groups:
                continue
            missing = set()
            for team in teams_in_groups(groups):
                if not has_shield(team, shields, shields_norm):
                    missing.add(team)
                    grand_missing.add(team)
            if missing:
                print(f"[{sname}] {cat.upper()} - {len(missing)} sin escudo:")
                for t in sorted(missing):
                    print(f"  - {t!r}")
                print()

    print(f"=== TOTAL equipos únicos sin escudo: {len(grand_missing)} ===")

if __name__ == '__main__':
    main()
