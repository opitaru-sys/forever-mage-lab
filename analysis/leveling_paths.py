"""Leveling results for the Forever Mage: the best single-target rotation by level, Frost vs Fire vs Arcane talent
orders, races, consumables, whether a respec plan beats one order, the low-rank options, a builder monotonicity check,
and the assumptions that move the results.

Run from the repo root:
    python analysis/leveling_paths.py              every section (about 15 minutes on 16 cores)
    python analysis/leveling_paths.py phases       one section: phases, trees, races, consumables, respec, lowranks,
                                                   monotone, sensitivity
Every number is evaluate() (models/character.py): the best rotation and modifiers, lower ranks at level 19 and below,
averaged over mob health 0.9, 1.0 and 1.1 (the page's HP_MULTS), gear 1, no race and every option at its default
unless the section says otherwise. Seconds per kill: fight + 8 s walking + rest; lower is better. Hours weight each
level by the kills it takes (kills(), an ASSUMPTION: Classic's experience table).
"""
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))

from character import evaluate, valid                      # noqa: E402
import leveling_sim as ls                                   # noqa: E402

LEVELS = list(range(10, 61))
BANDS = [(10, 19), (20, 29), (30, 39), (40, 49), (50, 60)]


def rep(*p):
    out = []
    for k, n in p:
        out += [k] * n
    return out


# Orders found by analysis/leveling_planner.py (1 Oct 2026, fixed model). PLANNER is the page's one order for
# levels 10 to 60 (no respec); the three tree-first orders put every point in one tree until it has nothing
# left to take.
PLANNER = rep(('ImprovedFrostbolt', 5), ('Frostbite', 2), ('IceShards', 2), ('Frostbite', 1), ('IceLance', 1),
              ('PiercingIce', 3), ('IceShards', 1), ('Shatter', 3), ('IceShards', 2), ('FingersOfFrost', 2),
              ('FrostChanneling', 2), ('ElementalPrecision', 1), ('FrostChanneling', 1), ('ElementalPrecision', 1),
              ('Incineration', 1), ('ElementalPrecision', 1), ('Incineration', 1), ('WintersChill', 1),
              ('ArcticReach', 1), ('WintersChill', 1), ('ArcticReach', 1), ('WakeOfFire', 2), ('WintersChill', 2),
              ('ImprovedFrostNova', 1), ('IceBlock', 1), ('ColdSnap', 1), ('IceBarrier', 1),
              ('ImprovedConeOfCold', 1), ('WandSpecialization', 2), ('ImprovedConeOfCold', 2), ('ArcaneFocus', 3),
              ('ElementalPrecision', 1))
FROST = rep(('ImprovedFrostbolt', 5), ('Frostbite', 2), ('IceShards', 2), ('Frostbite', 1), ('IceLance', 1),
            ('PiercingIce', 3), ('IceShards', 1), ('Shatter', 3), ('IceShards', 2), ('FingersOfFrost', 2),
            ('FrostChanneling', 2), ('ElementalPrecision', 1), ('FrostChanneling', 1), ('ElementalPrecision', 2),
            ('ArcticReach', 2), ('WintersChill', 3), ('ImprovedFrostNova', 1), ('Permafrost', 2), ('WintersChill', 2),
            ('ImprovedFrostNova', 1), ('IceBlock', 1), ('ColdSnap', 1), ('IceBarrier', 1), ('ImprovedConeOfCold', 1),
            ('WandSpecialization', 2), ('ImprovedConeOfCold', 2), ('ArcaneFocus', 3), ('ElementalPrecision', 1))
FIRE = rep(('WakeOfFire', 2), ('Incineration', 3), ('Ignite', 5), ('Pyroblast', 1), ('BurningSoul', 1),
           ('ImprovedFireball', 1), ('BurningSoul', 2), ('HotStreak', 1), ('ImprovedScorch', 3), ('FlameThrowing', 1),
           ('CriticalMass', 3), ('Impact', 1), ('FlameThrowing', 1), ('FirePower', 4), ('ImprovedFireball', 1),
           ('Combustion', 1), ('FirePower', 1), ('MasterOfElements', 2), ('Impact', 1), ('ElementalPrecision', 1),
           ('MasterOfElements', 1), ('ElementalPrecision', 2), ('Impact', 1), ('ElementalPrecision', 2),
           ('ImprovedFireball', 1), ('BlastWave', 1), ('ImprovedFrostbolt', 1), ('WandSpecialization', 1),
           ('ImprovedFrostbolt', 4), ('PiercingIce', 1))
ARCANE = rep(('ImprovedChanneling', 1), ('WandSpecialization', 2), ('ArcaneFocus', 2), ('ArcaneConcentration', 3),
             ('ImprovedChanneling', 1), ('ArcaneConcentration', 1), ('ArcaneFocus', 1), ('ArcaneConcentration', 1),
             ('ArcaneFocus', 1), ('ImprovedChanneling', 1), ('ArcaneBlast', 1), ('MissileBarrage', 1),
             ('ArcaneMeditation', 1), ('ArcaneImpact', 2), ('ArcaneMeditation', 1), ('PresenceOfMind', 1),
             ('ArcaneMeditation', 1), ('ArcaneImpact', 1), ('ImprovedChanneling', 2), ('ArcaneInstability', 3),
             ('ArcaneMind', 2), ('ImprovedFrostbolt', 1), ('ArcanePower', 1), ('ArcaneMind', 1),
             ('ImprovedFrostbolt', 4), ('ElementalPrecision', 1), ('ArcaneMind', 2), ('ElementalPrecision', 4),
             ('FrostChanneling', 2), ('IceLance', 1), ('FrostChanneling', 1), ('Permafrost', 1), ('Shatter', 1),
             ('ArcaneFocus', 1))
ORDERS = {'planner': PLANNER, 'frost': FROST, 'fire': FIRE, 'arcane': ARCANE}


def build(order, n):
    """The first n points of an order, checked legal after every point."""
    t = {}
    for k in order[:n]:
        t[k] = t.get(k, 0) + 1
        assert valid(t), (k, t)
    return t


def _job(args):
    L, tal, gear, race, kw = args
    n, r = evaluate(L, tal, gear, race, **kw)
    return n, r


def run_many(jobs, procs=None):
    """evaluate() for a list of (level, talents, gear, race, options), in a process pool."""
    with Pool(procs or max(1, (os.cpu_count() or 2) - 2)) as pool:
        return pool.map(_job, jobs, chunksize=1)


def mean(xs):
    return sum(xs) / len(xs)


def band_means(levels, vals):
    out = []
    for a, b in BANDS:
        v = [x for L, x in zip(levels, vals) if a <= L <= b]
        out.append(mean(v) if v else float('nan'))
    return out


# ASSUMPTION: Classic's experience to the next level (levels 1 to 59) and 45 + 5 x level experience per kill of a
# same-level mob (Classic's formula). No Forever source gives either; they only weight levels by the kills each takes.
XP_TO_NEXT = [400, 900, 1400, 2100, 2800, 3600, 4500, 5400, 6500, 7600, 8800, 10100, 11400, 12900, 14400, 16000,
              17700, 19400, 21300, 23200, 25200, 27300, 29400, 31700, 34000, 36400, 38900, 41400, 44300, 47400, 50800,
              54500, 58600, 62800, 67100, 71600, 76100, 80800, 85700, 90700, 95800, 101000, 106300, 111800, 117500,
              123200, 129100, 135100, 141200, 147500, 153900, 160400, 167100, 173900, 180800, 187900, 195000, 202300,
              209800]


def kills(L):
    """Kills to finish level L (0 at 60)."""
    return XP_TO_NEXT[L - 1] / (45 + 5 * L) if L < 60 else 0.0


def hours(levels, vals):
    """Hours of fighting, walking and resting to go through the given levels at these seconds per kill."""
    return sum(kills(L) * v for L, v in zip(levels, vals)) / 3600


def by_order(names, kw=None, gear=1):
    res = run_many([(L, build(ORDERS[o], L - 9), gear, 'none', kw or {}) for L in LEVELS for o in names])
    vals = {o: [res[i * len(names) + j][1]['spk'] for i in range(len(LEVELS))] for j, o in enumerate(names)}
    rots = {o: [res[i * len(names) + j][0] for i in range(len(LEVELS))] for j, o in enumerate(names)}
    return vals, rots


# ---------------------------------------------------------------- sections
def phases():
    """The best single-target rotation at every level, planner build, gear 1 and 2."""
    for gear in (1, 2):
        res = run_many([(L, build(PLANNER, L - 9), gear, 'none', {}) for L in LEVELS])
        print(f'\n### Best rotation by level, planner build, gear {gear}\n')
        print('| L | s per kill | fight | rest | potions per kill | rotation |')
        print('|---|---|---|---|---|---|')
        for L, (n, r) in zip(LEVELS, res):
            flag = '' if r['feasible'] else ' (INFEASIBLE)'
            print(f"| {L} | {r['spk']:.2f} | {r['ttk']:.1f} | {r['rest']:.1f} | {r['pots']:.2f} | {n}{flag} |")


def trees():
    """Frost-first vs Fire-first vs Arcane-first vs the planner order, no respec."""
    names = list(ORDERS)
    vals, rots = by_order(names)
    print('\n### Talent orders without respecs, gear 1: seconds per kill by level\n')
    print('| L | ' + ' | '.join(names) + ' |')
    print('|---|' + '---|' * len(names))
    for i, L in enumerate(LEVELS):
        if L % 2 == 0 or L in (59,):
            print(f'| {L} | ' + ' | '.join(f'{vals[o][i]:.2f}' for o in names) + ' |')
    print('| mean 10-60 | ' + ' | '.join(f'{mean(vals[o]):.2f}' for o in names) + ' |')
    print('| hours 10 to 60 (time-weighted) | ' + ' | '.join(f'{hours(LEVELS, vals[o]):.1f}' for o in names) + ' |')
    print('\n| band | ' + ' | '.join(names) + ' |')
    print('|---|' + '---|' * len(names))
    bm = {o: band_means(LEVELS, vals[o]) for o in names}
    for b, (a, z) in enumerate(BANDS):
        print(f'| {a}-{z} | ' + ' | '.join(f'{bm[o][b]:.2f}' for o in names) + ' |')
    print('\nRotation at 20, 30, 40, 50, 60:')
    for o in names:
        print(f'- {o}: ' + '; '.join(f'{L}: {rots[o][LEVELS.index(L)]}' for L in (20, 30, 40, 50, 60)))
    return vals


def races():
    """Each race with the planner build, gear 1: mean seconds per kill and the change against no race."""
    rs = ['none', 'human', 'gnome', 'skyborne', 'orc', 'undead', 'troll']
    res = run_many([(L, build(PLANNER, L - 9), 1, r, {}) for L in LEVELS for r in rs])
    vals = {r: [res[i * len(rs) + j][1]['spk'] for i in range(len(LEVELS))] for j, r in enumerate(rs)}
    base, base_h = mean(vals['none']), hours(LEVELS, vals['none'])
    print('\n### Races, planner build, gear 1\n')
    print('| race | mean s per kill 10-60 | vs no race | hours 10-60 | vs no race | 10-19 | 20-29 | 30-39 | 40-49 | 50-60 |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for r in rs:
        bm = band_means(LEVELS, vals[r])
        h = hours(LEVELS, vals[r])
        print(f'| {r} | {mean(vals[r]):.2f} | {100 * (mean(vals[r]) / base - 1):+.1f}% | {h:.1f} | '
              f'{100 * (h / base_h - 1):+.1f}% | ' + ' | '.join(f'{x:.2f}' for x in bm) + ' |')


def consumables():
    """Mana potions (default on) against off: seconds per kill, potions an hour and their price an hour."""
    res_on = run_many([(L, build(PLANNER, L - 9), 1, 'none', {}) for L in LEVELS])
    res_off = run_many([(L, build(PLANNER, L - 9), 1, 'none', dict(potions=False)) for L in LEVELS])
    res_ng = run_many([(L, build(PLANNER, L - 9), 1, 'none', dict(gems=False)) for L in LEVELS])
    print('\n### Mana potions, planner build, gear 1\n')
    print('| L | s per kill with potions | without | change | potions an hour | potion | gold an hour at the client price |')
    print('|---|---|---|---|---|---|---|')
    on_v, off_v = [], []
    for L, (n1, a), (n0, b) in zip(LEVELS, res_on, res_off):
        pots = [p for p in ls.POTIONS if p[0] <= L]
        per_hour = a['pots'] * 3600 / a['spk']
        price = pots[-1][2] / 10000 if pots else 0.0
        name = ls.POTION_NAMES[len(pots) - 1] if pots else 'none'
        on_v.append(a['spk'])
        off_v.append(b['spk'])
        if L % 5 == 0 or L in (14, 22, 31, 41, 49):
            print(f"| {L} | {a['spk']:.2f} | {b['spk']:.2f} | {100 * (a['spk'] / b['spk'] - 1):+.1f}% | "
                  f"{per_hour:.1f} | {name} | {per_hour * price:.2f} g |")
    print(f'| mean 10-60 | {mean(on_v):.2f} | {mean(off_v):.2f} | {100 * (mean(on_v) / mean(off_v) - 1):+.1f}% | | | |')
    h_on, h_off = hours(LEVELS, on_v), hours(LEVELS, off_v)
    print(f'\nTime-weighted, 10 to 60: {h_on:.1f} h with potions, {h_off:.1f} h without ({100 * (h_on / h_off - 1):+.1f}%).')
    gem_same = all(abs(a[1]['spk'] - c[1]['spk']) < 1e-9 for a, c in zip(res_on, res_ng))
    print(f'Mana gems on vs off change nothing at any level: {gem_same} (conjuring a gem costs more mana than it '
          f'restores: Agate 530 for 400, Jade 800 for 600, Citrine 1130 for 850, Ruby 1470 for 1100).')
    evo = [r['evo'] for n, r in res_on]
    print(f'Evocation uses per kill, levels 20 to 60: {min(evo[10:]):.3f} to {max(evo[10:]):.3f}.')


def respec(vals=None):
    """Does changing talents mid-leveling beat one fixed order? Respecs cost 1 silver on the beta (FINDINGS s2).
    Judged by leveling time: each level weighted by the kills it takes (kills(), ASSUMPTION), levels 10 to 59."""
    names = list(ORDERS)
    if vals is None:
        vals, _ = by_order(names)
    best_single = min(names, key=lambda o: hours(LEVELS, vals[o]))
    base_h, base_m = hours(LEVELS, vals[best_single]), mean(vals[best_single])
    per_level = [min(vals[o][i] for o in names) for i in range(len(LEVELS))]
    print('\n### Respec plans against one fixed order, gear 1\n')
    print(f'- Best single order: {best_single}, {base_h:.2f} h from 10 to 60 (mean {base_m:.2f} s per kill).')
    print(f'- Upper bound, the best of the {len(names)} orders at every level (a respec at any level): '
          f'{hours(LEVELS, per_level):.2f} h ({100 * (hours(LEVELS, per_level) / base_h - 1):+.2f}%); '
          f'level-weighted {100 * (mean(per_level) / base_m - 1):+.2f}%.')
    best = None
    for a in names:
        for b in names:
            if a == b:
                continue
            for X in range(11, 60):
                v = [vals[a][i] if L < X else vals[b][i] for i, L in enumerate(LEVELS)]
                h = hours(LEVELS, v)
                if best is None or h < best[0]:
                    best = (h, a, b, X, mean(v))
    h, a, b, X, m = best
    print(f'- Best one-respec plan: {a} to level {X - 1}, then {b} from {X}: {h:.2f} h '
          f'({100 * (h / base_h - 1):+.2f}% time-weighted; {100 * (m / base_m - 1):+.2f}% level-weighted).')
    share = sum(kills(L) * vals[best_single][i] for i, L in enumerate(LEVELS) if L < 20) / (3600 * base_h)
    print(f'- Share of leveling time spent in levels 10 to 19: {100 * share:.1f}%.')
    wins = [(L, o) for i, L in enumerate(LEVELS) for o in names
            if vals[o][i] < vals[best_single][i] * 0.99 and o != best_single]
    print(f'- Levels where another order is more than 1% faster than {best_single}: '
          + (', '.join(f'{L} ({o})' for L, o in wins) if wins else 'none'))


def lowranks():
    """What the untested low-rank options would change (test m13): planner build, gear 1, levels 20 to 60."""
    lv = [L for L in LEVELS if L >= 20]
    opts = [('measured (default: top rank from 20)', {}), ('full (low ranks keep full strength)', dict(low_ranks='full')),
            ('tbc ((max level + 6) / level)', dict(low_ranks='tbc')), ('classic (below-20 cut)', dict(low_ranks='classic'))]
    res = run_many([(L, build(PLANNER, L - 9), 1, 'none', kw) for _, kw in opts for L in lv])
    print('\n### Low ranks from level 20 (option low_ranks, test m13), planner build, gear 1\n')
    print('| option | mean s per kill 20-60 | vs default | hours 20-60 | from 34: mean | from 34 vs default | rotation at 40 | at 60 |')
    print('|---|---|---|---|---|---|---|---|')
    base = None
    for j, (label, kw) in enumerate(opts):
        rs = res[j * len(lv):(j + 1) * len(lv)]
        v = [r['spk'] for n, r in rs]
        v34 = [x for L, x in zip(lv, v) if L >= 34]
        if base is None:
            base = (mean(v), mean(v34))
        n40, n60 = rs[lv.index(40)][0], rs[lv.index(60)][0]
        print(f'| {label} | {mean(v):.2f} | {100 * (mean(v) / base[0] - 1):+.1f}% | {hours(lv, v):.1f} | {mean(v34):.2f} | '
              f'{100 * (mean(v34) / base[1] - 1):+.1f}% | {n40} | {n60} |')


def monotone():
    """Builder check: does one more point of an order ever make a build more than 1% slower at the same level, and
    does a Frostbite point ever score negative? (Frostbite freezes no longer force a step back: stepping is a
    searched modifier.)"""
    names = list(ORDERS)
    jobs = [(L, build(ORDERS[o], L - 9), g, 'none', {}) for o in names for g in (1, 2) for L in range(11, 61)]
    jobs += [(L, build(ORDERS[o], L - 10), g, 'none', {}) for o in names for g in (1, 2) for L in range(11, 61)]
    res = run_many(jobs)
    half = len(jobs) // 2
    worse = []
    for (L, t, g, _, _), (n1, a), (n0, b) in zip(jobs[:half], res[:half], res[half:]):
        if a['spk'] > b['spk'] * 1.01:
            worse.append((L, g, round(100 * (a['spk'] / b['spk'] - 1), 1)))
    print(f'\n### One more point: {len(worse)} of {half} cases more than 1% slower (orders x gear 1, 2 x levels 11-60)')
    if worse:
        print('    worst: ' + ', '.join(f'L{L} gear {g} {d:+.1f}%' for L, g, d in sorted(worse, key=lambda x: -x[2])[:10]))
    fb = []
    for o in names:
        for L in range(15, 61):
            t = build(ORDERS[o], L - 9)
            if t.get('Frostbite'):
                less = {k: v for k, v in t.items() if k != 'Frostbite'}
                fb.append((o, L, t, less))
    r = run_many([(L, t, 1, 'none', {}) for o, L, t, less in fb] + [(L, less, 1, 'none', {}) for o, L, t, less in fb])
    neg = [(o, L, round(100 * (r[i][1]['spk'] / r[i + len(fb)][1]['spk'] - 1), 2))
           for i, (o, L, t, less) in enumerate(fb) if r[i][1]['spk'] > r[i + len(fb)][1]['spk'] + 1e-9]
    print(f'Frostbite points scoring negative (build with them slower than without, same level): {len(neg)} of {len(fb)}'
          + (': ' + ', '.join(f'{o} L{L} {d:+.2f}%' for o, L, d in neg) if neg else ''))


SENS = [
    ('default', {}),
    ('Frostbite freeze never breaks (fb_break 0)', dict(fb_break=0.0)),
    ('Frost Nova and Frostbite never break', dict(nova_break=0.0)),
    ('Frost Nova and Frostbite break on every hit', dict(nova_break=1.0)),
    ('no stepping back after a root', dict(kite=False)),
    ('no spell pushback', dict(pushback=False)),
    ('mob damage x1.5 (test m16)', dict(mob_dps_mult=1.5)),
    ('mob damage x0.7', dict(mob_dps_mult=0.7)),
    ('Ice Lance coefficient 0 (client)', dict(il_coef=0.0)),
    ('Ice Lance coefficient 0.429', dict(il_coef=0.429)),
    ('low ranks keep full strength from 20 (m13)', dict(low_ranks='full')),
    ('casting regen: the larger of Mage Armor and Meditation', dict(regen_stack='max')),
    ('no Spirit regen while drinking', dict(spirit_drink=False)),
    ('Wowhead drink totals (25/26)', dict(wowhead_drinks=True)),
    ('no mana potions', dict(potions=False)),
    ('Frost or Ice Armor instead of Mage Armor from 34', dict(armor='frost')),
    ('armor chills do not roll Frostbite (test m17)', dict(frostbite_source='spells')),
    ('mobs run 7 yd/s', dict(mob_speed=7.0)),
    ('top-rank tomes (test m6)', dict(top_ranks=True)),
]


def sensitivity():
    """Each assumption flipped: mean seconds per kill (even levels 10 to 60) of the three tree-first orders."""
    names = ['frost', 'fire', 'arcane']
    lv = LEVELS[::2]
    jobs = [(L, build(ORDERS[o], L - 9), 1, 'none', kw) for _, kw in SENS for o in names for L in lv]
    res = run_many(jobs)
    per = len(names) * len(lv)
    print('\n### Sensitivity: mean seconds per kill, even levels 10 to 60, gear 1\n')
    print('| assumption | ' + ' | '.join(names) + ' | ranking |')
    print('|---|' + '---|' * (len(names) + 1))
    base = None
    for s, (label, kw) in enumerate(SENS):
        m = {o: mean([res[s * per + j * len(lv) + i][1]['spk'] for i in range(len(lv))]) for j, o in enumerate(names)}
        if base is None:
            base = m
        rank = ' < '.join(sorted(names, key=lambda o: m[o]))
        cells = ' | '.join(f'{m[o]:.2f} ({100 * (m[o] / base[o] - 1):+.1f}%)' if s else f'{m[o]:.2f}' for o in names)
        print(f'| {label} | {cells} | {rank} |')


def main():
    which = sys.argv[1:] or ['phases', 'trees', 'races', 'consumables', 'respec', 'lowranks', 'monotone', 'sensitivity']
    vals = None
    for w in which:
        if w == 'trees':
            vals = trees()
        elif w == 'respec':
            respec(vals)
        else:
            globals()[w]()


if __name__ == '__main__':
    main()
