"""Raid ranking at the model defaults, and how every untested option (and the main settings) moves it.

Prints markdown for the raid report:
  1. the ranking at the defaults and with the top-rank tomes, with each spec's plan and damage by source;
  2. the sensitivity table: every spec's dps under each alternative value of each untested option, the leader,
     and the leader's margin over #2;
  3. the same for the settings a reader moves most (mp5, fight length, consumables, raid buffs, wand, race, power);
  4. every pair of untested flips that changes the leader.

Run from the repo root: python analysis/raid_specs.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
import raid_model as R  # noqa: E402

UNTESTED = [
    ('topRanks', [True], 'test m6'),
    ('downrank', ['full'], 'test m13'),
    ('iceLanceCoef', [0, 0.429, 0.572], 'test m4'),
    ('abMask', ['tooltip'], 'test m8'),
    ('amSpends', [True], 'test m28'),
    ('regenStack', ['max', 'full'], 'tests m5, m14'),
    ('evocation', [0.5, 0], 'test m7'),
    ('igniteMunch', [0.15, 0.3], 'test m11'),
    ('mbRate', [0.5], 'test m18'),
    ('levelResist', [False], 'no test yet'),
]
SETTINGS = [
    ('mp5', [30, 60, 120]),
    ('fightLength', [120, 180, 450, 600]),
    ('potion', ['blast', 'none']),
    ('runes', [False]),
    ('gems', [False]),
    ('mageblood', [False]),
    ('raidBuffs', ['noTotem', 'none']),
    ('wandDps', [0, 90]),
    ('sp', [300, 700, 900]),
    ('crit', [0.05, 0.15, 0.20]),
    ('int', [200, 400]),
    ('spirit', [80, 200]),
    ('race', ['human', 'gnome', 'skyborne', 'orc', 'undead', 'troll']),
    ('fireImmune', [True]),
]
SHORT = {'frost-mb': 'Frost MB', 'fire-mb': 'Fire AB', 'arcane': 'Arcane', 'arcane-fire': 'Arc/Ignite',
         'frost-sim': 'Frost sim', 'arcane-sim': 'Arcane sim', 'fire-sim': 'Fire sim'}


def ranking_block(o, title):
    print('\n### %s\n' % title)
    print('| # | Spec | dps | gap to #1 | plan (seconds) | damage by source (dps) |')
    print('|---|---|---|---|---|---|')
    res = R.rank(o)
    top = res[0]['total']
    for i, r in enumerate(res, 1):
        if not r['viable']:
            print('| %d | %s | n/a | out | %s | |' % (i, r['name'], r['reason']))
            continue
        plan = '; '.join('%s %.0f' % (p['name'], p['seconds']) for p in r['plan'])
        parts = ', '.join('%s %.0f' % (k, v) for k, v in sorted(r['parts'].items(), key=lambda kv: -kv[1]))
        gap = 'best' if i == 1 else '%.1f%%' % ((1 - r['total'] / top) * 100)
        print('| %d | %s | %.1f | %s | %s | %s |' % (i, r['name'], r['total'], gap, plan, parts))
    return res


def row(label, o, ids):
    res = R.rank(o)
    by = {r['id']: r for r in res}
    live = [r for r in res if r['viable']]
    lead = live[0]
    margin = (lead['total'] / live[1]['total'] - 1) * 100 if len(live) > 1 else 0.0
    cells = ['%.0f' % by[i]['total'] if by[i]['viable'] else 'out' for i in ids]
    print('| %s | %s | %s %+.1f%% |' % (label, ' | '.join(cells), SHORT[lead['id']], margin))


def table(title, spec, ids):
    print('\n### %s\n' % title)
    print('| option | ' + ' | '.join(SHORT[i] for i in ids) + ' | leader, margin over #2 |')
    print('|---' * (len(ids) + 2) + '|')
    row('defaults', dict(R.DEFAULTS), ids)
    for key, values, note in spec:
        for v in values:
            label = '%s = %s' % (key, v) + (' (%s)' % note if note else '')
            row(label, dict(R.DEFAULTS, **{key: v}), ids)


def leader(o):
    live = [r for r in R.rank(o) if r['viable']]
    return live[0]['id'], (live[0]['total'] / live[1]['total'] - 1) * 100


def pair_flips():
    """Every pair of untested flips (two different options) whose leader differs from the defaults' leader."""
    print('\n### Pairs of untested flips that change the leader\n')
    base = leader(dict(R.DEFAULTS))[0]
    flips = [(k, v) for k, vals, _ in UNTESTED for v in vals]
    found = 0
    print('| flips | leader, margin over #2 |')
    print('|---|---|')
    for i, (ka, va) in enumerate(flips):
        for kb, vb in flips[i + 1:]:
            if ka == kb:
                continue
            lead, margin = leader(dict(R.DEFAULTS, **{ka: va, kb: vb}))
            if lead != base:
                found += 1
                print('| %s = %s, %s = %s | %s %+.1f%% |' % (ka, va, kb, vb, SHORT[lead], margin))
    if not found:
        print('| none | %s in every pair |' % SHORT[base])


def main():
    ids = [s['id'] for s in R.SPECS]
    ranking_block(dict(R.DEFAULTS), 'Ranking at the defaults (trainer ranks)')
    ranking_block(dict(R.DEFAULTS, topRanks=True), 'Ranking with the top-rank tomes (topRanks on)')
    table('Sensitivity: every untested option, one at a time (dps)', UNTESTED, ids)
    table('Sensitivity: the main settings, one at a time (dps)', [(k, v, '') for k, v in SETTINGS], ids)
    pair_flips()


if __name__ == '__main__':
    main()
