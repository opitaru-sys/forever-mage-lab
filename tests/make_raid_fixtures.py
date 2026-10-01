"""Regenerate the raid parity data from models/raid_model.py, the reference.

1. Checks the hardcoded spell rows against data/mage_spells.json, the SPECS against the point rules, and that the
   fixed-point loop has settled (ITERATIONS passes against 3 more) on every case below.
2. Rewrites the EXPECTED table in tests/parity_test.js: every spec at spell power 300/500/800 x crit 5/10/20%,
   race none, other options at their defaults.
3. Writes tests/raid_options_fixtures.json: rank() (order, totals, viability) for cases that cover every option and
   every choice of every option, plus statWeights() and compareItems() for a few.

Run from the repo root: python tests/make_raid_fixtures.py   (twice gives the same files)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
import raid_model as R  # noqa: E402

SP_VALUES = (300, 500, 800)
CRIT_VALUES = (0.05, 0.10, 0.20)

# Each case: options on top of DEFAULTS. Together they cover every option id and every choice.
CASES = [
    {},
    {'race': 'human'}, {'race': 'human', 'sword': False}, {'race': 'gnome'}, {'race': 'skyborne'}, {'race': 'orc'},
    {'race': 'undead'}, {'race': 'undead', 'maxHp': 6000}, {'race': 'troll'},
    {'sp': 300, 'crit': 0.05}, {'sp': 900, 'crit': 0.25}, {'gearHit': 0.0}, {'gearHit': 0.16}, {'gearHit': 0.05, 'crit': 0.15},
    {'int': 200}, {'int': 450, 'spirit': 250}, {'spirit': 60}, {'mp5': 40}, {'mp5': 150},
    {'fightLength': 60}, {'fightLength': 120}, {'fightLength': 180}, {'fightLength': 450}, {'fightLength': 600},
    {'fireImmune': True}, {'fireImmune': True, 'race': 'orc', 'topRanks': True},
    {'potion': 'blast'}, {'potion': 'none'}, {'runes': False}, {'gems': False}, {'runes': False, 'gems': False},
    {'potion': 'none', 'runes': False, 'gems': False}, {'mageblood': False}, {'potion': 'none', 'mageblood': False},
    {'raidBuffs': 'noTotem'}, {'raidBuffs': 'none'}, {'raidBuffs': 'none', 'mageblood': False, 'runes': False},
    {'wandDps': 0}, {'wandDps': 90}, {'wandDps': 0, 'raidBuffs': 'none'},
    {'kings': False}, {'moonkin': True}, {'kings': False, 'moonkin': True, 'race': 'human'},
    {'iceLanceBinary': False}, {'fingersOnBoss': False}, {'fingersOnBoss': False, 'iceLanceCoef': 0.429},
    {'fightLength': 90}, {'fightLength': 179}, {'fightLength': 360, 'race': 'gnome'}, {'fightLength': 181, 'race': 'gnome'},
    {'iceLanceCoef': 0}, {'iceLanceCoef': 0.429}, {'iceLanceCoef': 0.572},
    {'abMask': 'tooltip'}, {'abMask': 'tooltip', 'mbRate': 0.5},
    {'amSpends': True}, {'amSpends': True, 'abMask': 'tooltip'}, {'amSpends': True, 'mbRate': 0.5},
    {'regenStack': 'max'}, {'regenStack': 'full'},
    {'evocation': 0.5}, {'evocation': 0},
    {'igniteMunch': 0.15}, {'igniteMunch': 0.3},
    {'downrank': 'full'}, {'downrank': 'full', 'topRanks': True}, {'downrank': 'full', 'raidBuffs': 'none'},
    {'topRanks': True}, {'levelResist': False}, {'mbRate': 0.5},
    {'race': 'gnome', 'potion': 'blast', 'regenStack': 'max', 'fightLength': 240},
    {'race': 'troll', 'downrank': 'full', 'levelResist': False, 'igniteMunch': 0.15, 'mp5': 60},
    {'race': 'undead', 'iceLanceCoef': 0.572, 'abMask': 'tooltip', 'evocation': 0.5, 'topRanks': True, 'sp': 700},
]
WEIGHT_CASES = [{}, {'gearHit': 0.08}, {'race': 'human', 'sp': 700, 'crit': 0.15}, {'mp5': 80, 'topRanks': True},
                {'raidBuffs': 'none', 'wandDps': 0}, {'kings': False, 'moonkin': True, 'fightLength': 180}]
ITEM_CASES = [
    ({}, {'sp': 30, 'crit': 0.01, 'hit': 0, 'int': 10, 'spirit': 0, 'mp5': 0},
     {'sp': 20, 'crit': 0.0, 'hit': 0.01, 'int': 20, 'spirit': 10, 'mp5': 5}),
    ({'gearHit': 0.08}, {'sp': 0, 'crit': 0, 'hit': 0, 'int': 0, 'spirit': 0, 'mp5': 0},
     {'sp': 0, 'crit': 0, 'hit': 0.02, 'int': 0, 'spirit': 0, 'mp5': 0}),
]


def r4(x):
    return round(x, 4)


def settled(o):
    """Largest change in any spec total from ITERATIONS passes to ITERATIONS + 3."""
    base = {r['id']: r['total'] for r in R.rank(o)}
    keep = R.ITERATIONS
    R.ITERATIONS = keep + 3
    try:
        more = {r['id']: r['total'] for r in R.rank(o)}
    finally:
        R.ITERATIONS = keep
    return max(abs(base[k] - more[k]) for k in base)


def parity_table():
    rows = []
    for sp in SP_VALUES:
        for c in CRIT_VALUES:
            o = dict(R.DEFAULTS, sp=sp, crit=c)
            vals = [R.spec_total(o, s['id']) for s in R.SPECS]
            rows.append("  '%d,%.2f': [" % (sp, c) + ', '.join('%.4f' % v for v in vals) + '],')
    return '\n'.join(rows)


def rank_rows(o):
    return [{'id': r['id'], 'viable': r['viable'], 'total': r4(r['total'])} for r in R.rank(o)]


def main():
    bad = R.check_data()
    if bad:
        raise SystemExit('spell rows differ from data/mage_spells.json: %r' % bad)
    for s in R.SPECS:
        errs = R.build_errors(s['talents'])
        if errs:
            raise SystemExit('%s breaks the point rules: %r' % (s['id'], errs))
    worst = 0.0
    for case in CASES:
        worst = max(worst, settled(dict(R.DEFAULTS, **case)))
    if worst > 0.01:
        raise SystemExit('fixed point not settled: %.4f dps' % worst)

    path = os.path.join(HERE, 'parity_test.js')
    with open(path, newline='') as fh:
        src = fh.read()
    eol = '\r\n' if '\r\n' in src else '\n'
    table = parity_table().replace('\n', eol)
    new, n = re.subn(r'(const EXPECTED = \{' + re.escape(eol) + r').*?(' + re.escape(eol) + r'\};)',
                     lambda m: m.group(1) + table + m.group(2), src, flags=re.S)
    if n != 1:
        raise SystemExit('EXPECTED block not found in parity_test.js')
    new = re.sub(r"const SPEC_ORDER = \[[^\]]*\];", 'const SPEC_ORDER = [' + ', '.join("'%s'" % s['id'] for s in R.SPECS) + '];', new)
    with open(path, 'w', newline='') as fh:
        fh.write(new)

    cases = [{'opts': c, 'rank': rank_rows(dict(R.DEFAULTS, **c))} for c in CASES]
    weights = []
    for c in WEIGHT_CASES:
        o = dict(R.DEFAULTS, **c)
        weights.append({'opts': c, 'weights': {s['id']: {k: r4(v) for k, v in R.stat_weights(o, s['id']).items()}
                                               for s in R.SPECS}})
    items = []
    for c, a, b in ITEM_CASES:
        o = dict(R.DEFAULTS, **c)
        items.append({'opts': c, 'a': a, 'b': b,
                      'result': {s['id']: {k: r4(v) for k, v in R.compare_items(o, s['id'], a, b).items()}
                                 for s in R.SPECS}})
    fixtures = {'generated_by': 'tests/make_raid_fixtures.py', 'settled_within': r4(worst), 'cases': cases,
                'weights': weights, 'items': items}
    with open(os.path.join(HERE, 'raid_options_fixtures.json'), 'w', encoding='utf-8', newline='\r\n') as fh:
        json.dump(fixtures, fh, indent=1)
        fh.write('\n')
    print(parity_table())
    print('wrote %d option cases, %d weight cases, %d item cases; fixed point settled within %.4f dps'
          % (len(cases), len(weights), len(items), worst))


if __name__ == '__main__':
    main()
