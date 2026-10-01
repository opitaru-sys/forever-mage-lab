"""AoE breakevens for the Forever Mage: from which pull size each AoE loop beats the single-target model, level band
by level band, and how that moves across every uncertain assumption.

Run from the repo root:
    python analysis/aoe_breakeven.py                 every section (10 to 20 minutes on 16 cores)
    python analysis/aoe_breakeven.py defaults        one section: calibration, defaults, failures, budget,
                                                     sensitivity, pairs, ranks
Every AoE number is models/aoe.py best_pull() (loops in models/aoe_loops.py): the fastest surviving loop variant,
each run with and without a potion and gem in the fight, averaged over mob health 0.9, 1.0 and 1.1 of the curve (the
single-target model's HP_MULTS). Every single-target number is character.evaluate() on the leveling planner build
with the same options, called live, so these tables follow whatever the imported leveling model returns. A pull size
the Mage does not survive shows why: 'oom' (out of mana for her loop's damage spells before her health first fell
under the safety floor), 'caught' (under the floor first), 'stall' (neither, and not over in 240 s). It never counts
toward a breakeven. The calibration section is the gate for small-pull claims: one mob through the AoE engine must
land within 10% of evaluate() (tests/aoe_test.py checks it).
"""
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))

import aoe                                                  # noqa: E402
import leveling_sim as ls                                   # noqa: E402
from character import make_char, mob_hp                     # noqa: E402

LEVELS = (20, 25, 30, 40, 50, 60)
NS = tuple(range(2, 11))
PULL_N = 4              # reg pullSize default (social pull size); the columns sweep 2 to 10
SHOW = (3, 4, 6, 10)    # pull sizes in the failures table

# (label, options, the register item or test that settles it)
VARIANTS = [
    ('defaults', {}, ''),
    ('target cap 5', dict(cap=5), 'm1'),
    ('target cap 4', dict(cap=4), 'm1'),
    ('Blizzard chill 40% (Chilled row value)', dict(bz_row30=True), 'm3'),
    ('Blizzard chill lasts 1.5 s', dict(bz_chill_s=1.5), 'm3'),
    ('Blizzard chill set once a cast', dict(bz_refresh=False), 'm3'),
    ('Classic chill: 75% for 4.5 s', dict(bz_slow=0.75, bz_chill_s=4.5), 'reference'),
    ('Frost Nova break 0.1 a hit', dict(nova_break=0.1), 'm12'),
    ('Frost Nova break 1.0 a hit', dict(nova_break=1.0), 'm12'),
    ('Frostbite rolls on the first tick only', dict(fb_rolls='first'), 'm17'),
    ('mob damage x0.5', dict(mob_dps_mult=0.5), 'm16'),
    ('mob damage x0.7', dict(mob_dps_mult=0.7), 'm16'),
    ('mob damage x1.5', dict(mob_dps_mult=1.5), 'm16'),
    ('mob health x0.8', dict(hp_scale=0.8), 'm16'),
    ('mob health x1.2', dict(hp_scale=1.2), 'm16'),
    ('mob swing 1.5 s', dict(swing=1.5), 'm16'),
    ('mob swing 2.5 s', dict(swing=2.5), 'm16'),
    ('mobs run 7 yd/s', dict(mob_speed=7.0), 'm3'),
    ('Blizzard and Flamestrike ticks crit', dict(bz_crit=True), 'm9'),
    ('first Blizzard tick at 0 s', dict(bz_first=0.0), 'm9'),
    ('no Blizzard pushback', dict(bz_pushback='none'), 'channelPushback'),
    ('first melee hit ends Blizzard', dict(bz_pushback='end'), 'channelPushback'),
    ('gathering 8 + 4 s a mob', dict(gather_per=4.0), 'gatherTime'),
    ('gathering 8 + 10 s a mob', dict(gather_per=10.0), 'gatherTime'),
    ('finding a group to pull from range: 0 s a mob', dict(find_per=0.0), 'model'),
    ('finding a group to pull from range: 6 s a mob', dict(find_per=6.0), 'model'),
    ('mob reach 8 yd', dict(reach=8.0), 'meleeRange'),
    ('Cone catches 50% of the pack', dict(cone_share=0.5), 'coneOfColdShape'),
    ('Cone catches the whole pack', dict(cone_share=1.0), 'coneOfColdShape'),
    ('humanoid pack, all flee at 15%', dict(flee=1.0), 'm20'),
    ('safety floor 0 (expected death only)', dict(safety=0.0), 'model'),
    ('safety floor 50%', dict(safety=0.5), 'model'),
    ('Nova and Ice Barrier cooldowns carry over between pulls', dict(cd_carry=True), 'model'),
    ('no mana potions', dict(potions=False), 'consumables'),
    ('no mana gems', dict(gems=False), 'consumables'),
    ('Mage Armor from 34, not Frost or Ice Armor', dict(aoe_armor='auto'), 'model'),
    ('gear: 2 Int and 2 Stamina a level', dict(gear_int=2.0, gear_sta=2.0), 'gear'),
    ('low ranks full: single target may downrank at every level', dict(low_ranks='full'), 'm13'),
    ('kind world: Classic chill, Nova break 0.1, mob health x0.8, gear x2',
     dict(bz_slow=0.75, bz_chill_s=4.5, nova_break=0.1, hp_scale=0.8, gear_int=2.0, gear_sta=2.0), 'combined'),
]


def slim(r):
    keep = ('spk', 'feasible', 'fail', 'T', 'rest', 'cycle', 'min_hp', 'pot', 'gem', 'pol', 'casts', 'taken', 'spent')
    out = {k: r[k] for k in keep}
    mid = r['runs'][len(r['runs']) // 2]          # the run at mob health x1.0
    out.update({k: mid[k] for k in ('dry_t', 'low_t', 'dry_hp', 'dry_left', 'bz_tpm', 't_all')})
    return out


def _pull(args):
    arch, L, n, o = args
    return slim(aoe.best_pull(L, n, arch, o))


def _base(args):
    L, o = args
    name, r = aoe.baseline(L, o)
    return name, r['spk'], r['feasible'], r['ttk'], r['rest']


def run(fn, jobs):
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        return pool.map(fn, jobs, chunksize=1)


_GRIDS = {}


def grid(variants, arches=aoe.ARCHES):
    """best_pull for every variant, archetype, band level and pull size, and the baselines: two dicts (memoized
    within a run, so sections share them)."""
    memo = repr((variants, arches))
    if memo not in _GRIDS:
        jobs = [(a, L, n, o) for _, o, _ in variants for a in arches for L in LEVELS if L >= aoe.ARCH_FROM[a]
                for n in NS]
        out = dict(zip([(repr(sorted(o.items())), a, L, n) for a, L, n, o in jobs], run(_pull, jobs)))
        bjobs = [(L, o) for _, o, _ in variants for L in LEVELS]
        base = dict(zip([(repr(sorted(o.items())), L) for L, o in bjobs], run(_base, bjobs)))
        _GRIDS[memo] = out, base
    return _GRIDS[memo]


def modes(rows):
    """'oom 2-5, caught 6-10': the failure label of each failing pull size, in runs of pull sizes."""
    out = []
    for n, r in rows:
        if r['feasible']:
            continue
        if out and out[-1][0] == r['fail'] and out[-1][2] == n - 1:
            out[-1][2] = n
        else:
            out.append([r['fail'], n, n])
    return ', '.join(f'{m} {a}' if a == b else f'{m} {a}-{b}' for m, a, b in out)


def verdict(base, rows):
    """'n (-x%)' for a breakeven, else 'none, +x% at n' (the fastest surviving pull size and its gap) or 'none (...)'
    with why every pull size failed."""
    b = aoe.breakeven(base, rows)
    if b['best_spk'] is None:
        return f'none ({modes(rows)})', b
    pct = 100.0 * (b['best_spk'] / base - 1)
    if b['n_star'] is None:
        return f"none, {pct:+.0f}% at {b['best_n']}", b
    return f"{b['n_star']} ({pct:+.0f}% at {b['best_n']})", b


def cell(r):
    return f"{r['spk']:.1f}" if r['feasible'] else r['fail']


def stamp():
    m = os.path.join(HERE, '..', 'models')
    files = [os.path.join(m, f) for f in ('character.py', 'leveling_sim.py', 'aoe.py', 'aoe_loops.py')]
    files.append(os.path.join(HERE, 'leveling_paths.py'))
    for f in files:
        t = os.path.getmtime(f)
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))
        print(f'- {os.path.relpath(f, os.path.join(HERE, ".."))}: {when}')


# ---------------------------------------------------------------- sections
def _cal(L):
    return slim(aoe.best_pull(L, 1, 'nb'))


def calibration():
    """One mob through the AoE engine against the single-target model: the gate for small-pull claims."""
    rs = dict(zip(LEVELS, run(_cal, LEVELS)))
    bs = dict(zip(LEVELS, run(_base, [(L, {}) for L in LEVELS])))
    print('\n### Calibration: one mob through the AoE engine against the single-target model\n')
    print('The small-pull loop (planner build, pulled from range) on one mob, against character.evaluate() on the same '
          'build. Gate: within 10% at every band (tests/aoe_test.py).')
    print('\n| L | single target s per kill (fight, rest) | AoE engine, one mob (fight, rest) | gap | loop |')
    print('|---|---|---|---|---|')
    for L in LEVELS:
        name, b, _, ttk, rest = bs[L]
        r = rs[L]
        eng = f"{r['spk']:.2f} ({r['T']:.1f}, {r['rest']:.1f})" if r['feasible'] else r['fail']
        gap = f"{100 * (r['spk'] / b - 1):+.1f}%" if r['feasible'] else '-'
        print(f'| {L} | {b:.2f} ({ttk:.1f}, {rest:.1f}) | {eng} | {gap} | {r["pol"]} |')


def defaults():
    """Seconds per kill by pull size at the defaults, against the single-target baseline."""
    out, base = grid(VARIANTS[:1])
    key = repr([])
    print('\n### Seconds per kill by pull size, default assumptions (gear 1, no race)\n')
    print('Single target: the planner build, best rotation (character.evaluate). A failed pull shows why: "oom" (out '
          'of mana first), "caught" (health under the floor first), "stall". The floor is '
          f'{aoe.AOE_DEFAULTS["safety"]:.0%} health at every mob health multiple.')
    for a in aoe.ARCHES:
        print(f'\n#### {aoe.ARCH_NAME[a]}\n')
        print('| L | single target | ' + ' | '.join(f'n={n}' for n in NS) +
              ' | breakeven n (fastest) | largest safe n |')
        print('|---|---|' + '---|' * len(NS) + '---|---|')
        for L in LEVELS:
            if L < aoe.ARCH_FROM[a]:
                continue
            b = base[(key, L)][1]
            rows = [(n, out[(key, a, L, n)]) for n in NS]
            v, br = verdict(b, rows)
            print(f'| {L} | {b:.1f} | ' + ' | '.join(cell(r) for _, r in rows) +
                  f" | {v} | {br['max_safe'] if br['max_safe'] else 'none'} |")


def failures():
    """How the failed pulls fail at the defaults: running dry against being caught, at mob health x1.0."""
    out, _ = grid(VARIANTS[:1])
    key = repr([])
    print('\n### How pulls fail at the defaults (mob health x1.0, the loop variant kept)\n')
    print('"oom at t s (h% health, p% of the pack left)": out of mana for the loop\'s damage spells at t seconds, at '
          'h% of her health, with p% of the pack\'s total health still standing; she is beaten down after. "caught at '
          't s": under the safety floor at t seconds with mana left. "ok": the pull survives (seconds per kill).')
    for a in aoe.ARCHES:
        print(f'\n#### {aoe.ARCH_NAME[a]}\n')
        print('| L | ' + ' | '.join(f'n={n}' for n in SHOW) + ' |')
        print('|---|' + '---|' * len(SHOW))
        for L in LEVELS:
            if L < aoe.ARCH_FROM[a]:
                continue
            cells = []
            for n in SHOW:
                r = out[(key, a, L, n)]
                if r['feasible']:
                    cells.append(f"ok {r['spk']:.1f}")
                elif r['fail'] == 'oom' and r['dry_t'] is not None:
                    cells.append(f"oom at {r['dry_t']:.0f} s ({r['dry_hp']:.0%} health, {r['dry_left']:.0%} of the pack "
                                 "left)")
                elif r['fail'] == 'caught' and r['low_t'] is not None:
                    cells.append(f"caught at {r['low_t']:.0f} s")
                else:
                    cells.append(r['fail'])
            print(f'| {L} | ' + ' | '.join(cells) + ' |')
    print(f'\n### What a pull of {PULL_N} looks like (default assumptions, the loop variant kept)\n')
    print('| arch | L | s per kill | fight s | rest s | lowest health | potion | gem | loop | casts |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for a in aoe.ARCHES:
        for L in LEVELS:
            if L < aoe.ARCH_FROM[a]:
                continue
            r = out[(key, a, L, PULL_N)]
            casts = ', '.join(f'{k} {v:.1f}' for k, v in sorted(r['casts'].items()))
            print(f"| {a} | {L} | {cell(r)} | {r['T']:.1f} | {r['rest']:.1f} | {r['min_hp']:.0%} | {r['pot']} | "
                  f"{r['gem']} | {r['pol']} | {casts} |")


def ranks():
    """Under low_ranks 'full' (every rank keeps its coefficient, test m13), is a lower rank of an AoE spell ever more
    damage per mana than the top rank? Per target, gear 1 (spell power = level), no talents."""
    print('\n### Lower ranks under full coefficients: damage per mana, best lower rank vs the top rank\n')
    print('| L | Blizzard | Arcane Explosion | Flamestrike (hit) |')
    print('|---|---|---|---|')
    tables = (('Blizzard', aoe.BLIZZARD, 4, 5, 8), ('ArcaneExplosion', ls.ARCANE_EXPLOSION, 4, 5, 1),
              ('Flamestrike', aoe.FLAMESTRIKE, 4, 5, 1))
    for L in LEVELS:
        cells = []
        for name, rows, ci, mi, mult in tables:
            learned = [r for r in rows if r[0] <= L]
            if not learned:
                cells.append('-')
                continue
            per = [(ls.dd_avg(r, L) + r[ci] * L) * mult / r[mi] for r in learned]
            top, best = per[-1], max(per[:-1]) if len(per) > 1 else None
            cells.append('top only' if best is None else f'{best / top:.2f}x of top')
        print(f'| {L} | ' + ' | '.join(cells) + ' |')


def budget():
    """The arithmetic behind the verdict, Frost AoE build at the defaults: what one Blizzard does to one mob and
    costs, the slow actually applied and how long a free mob stays in the storm, how much mana the Mage has, what
    single target spends, and how fast a pack in melee brings her to the safety floor."""
    out, _ = grid(VARIANTS[:1])
    key = repr([])
    print('\n### The budget of a pull (Frost AoE build, defaults, gear 1)\n')
    print('"Ticks a mob takes": Blizzard ticks landed per mob per cast in the default pulls of 4 and 6 (mob health '
          'x1.0), against the 8 a cast has.')
    print('\n| L | mob health | one full Blizzard, per mob hit | Blizzards to kill a mob | their mana | pool | '
          'potion + gem '
          '| single target mana per kill | Blizzard slow applied | s for a free mob to cross the 16 yd storm '
          '| ticks a mob takes, n=4 / n=6 | Mage health | s for 4 mobs in melee to reach the floor |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    o = aoe.opts()
    floor = 1 - o['safety']
    for L in LEVELS:
        ch = make_char(L, aoe.aoe_talents('blizzard', L), 1, 'none', armor=o['aoe_armor'])
        K = aoe.spell_consts(ch, o)
        H = mob_hp(L)
        bz = K['sp']['Blizzard']
        per = bz['ticks'] * bz['x'] * bz['hit']
        pot = [p for p in ls.POTIONS if p[0] <= L]
        gem = [g for g in ls.GEMS if g[0] <= L]
        extra = (pot[-1][1] if pot else 0) + (gem[-1][2] if gem else 0)
        st = aoe.baseline(L)[1]
        cross = 2 * aoe.BZ_RADIUS / (ch.mob_speed * (1 - K['bz_slow']))
        tpms = [out[(key, 'blizzard', L, n)]['bz_tpm'] for n in (4, 6)]
        tpm = '/'.join('-' if x is None else f'{x:.1f}' for x in tpms)
        print(f"| {L} | {H:.0f} | {per:.0f} | {H / per:.1f} | {H / per * bz['cost']:.0f} | {ch.max_mana:.0f} | "
              f"{extra:.0f} | {st['mana_spent']:.0f} | {K['bz_slow']:.0%} for {K['bz_chill']:.1f} s | {cross:.1f} | "
              f"{tpm} | {ch.max_hp:.0f} | {floor * ch.max_hp / (4 * ch.mob_dps):.1f} |")


def sensitivity():
    """Breakeven pull size by level band for every assumption at its low and high."""
    out, base = grid(VARIANTS)
    print('\n### Sensitivity: breakeven pull size by level band\n')
    print('Cell: the smallest surviving pull size (2 to 10) that beats single target, with the fastest pull size '
          'and its gap to single target; "none, +x% at n": every surviving pull size is slower, the fastest (n) by x%; '
          '"none (oom 2-5, caught 6-10)": no pull size survives, and why. Single target is re-run with the same '
          'options.')
    for a in aoe.ARCHES:
        lv = [L for L in LEVELS if L >= aoe.ARCH_FROM[a]]
        print(f'\n#### {aoe.ARCH_NAME[a]}\n')
        print('| assumption | test | ' + ' | '.join(f'L{L}' for L in lv) + ' |')
        print('|---|---|' + '---|' * len(lv))
        for label, o, test in VARIANTS:
            key = repr(sorted(o.items()))
            cells = []
            for L in lv:
                rows = [(n, out[(key, a, L, n)]) for n in NS]
                cells.append(verdict(base[(key, L)][1], rows)[0])
            print(f'| {label} | {test} | ' + ' | '.join(cells) + ' |')


HELPS = [('Classic chill', dict(bz_slow=0.75, bz_chill_s=4.5)), ('Nova break 0.1', dict(nova_break=0.1)),
         ('mob health x0.8', dict(hp_scale=0.8)), ('mob damage x0.5', dict(mob_dps_mult=0.5)),
         ('gear x2', dict(gear_int=2.0, gear_sta=2.0)), ('ticks crit', dict(bz_crit=True))]


def pairs():
    """Every pair of the assumptions that help AoE most, for the small-pull loop and the two strongest AoE loops:
    does any pair flip the verdict?"""
    from itertools import combinations
    combos = [(f'{a} + {b}', dict(oa, **ob), '') for (a, oa), (b, ob) in combinations(HELPS, 2)]
    arches = ('nb', 'blizzard', 'ae')
    out, base = grid(combos, arches)
    print('\n### Pairs of helpful assumptions: breakeven pull size by level band\n')
    print('Cells as in the sensitivity section. Every pair of: ' + ', '.join(h[0] for h in HELPS) + '.')
    for a in arches:
        print(f'\n#### {aoe.ARCH_NAME[a]}\n')
        print('| pair | ' + ' | '.join(f'L{L}' for L in LEVELS) + ' |')
        print('|---|' + '---|' * len(LEVELS))
        for label, o, _ in combos:
            key = repr(sorted(o.items()))
            cells = [verdict(base[(key, L)][1], [(n, out[(key, a, L, n)]) for n in NS])[0] for L in LEVELS]
            print(f'| {label} | ' + ' | '.join(cells) + ' |')


def main():
    which = sys.argv[1:] or ['calibration', 'defaults', 'failures', 'budget', 'sensitivity', 'pairs', 'ranks']
    print('Baseline files (the imported single-target model) and this model, last modified:')
    stamp()
    for w in which:
        t = time.time()
        globals()[w]()
        print(f'\n({w}: {time.time() - t:.0f} s)')


if __name__ == '__main__':
    main()
