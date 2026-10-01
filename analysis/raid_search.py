"""Talent search for the raid specs: an iterated local search under the point rules, in several scenarios.

The raid model reads 32 of the 54 talents; the other 22 (range, threat, pushback, defensive, crowd control) change
no raid number, so they only fill tiers. A build is searched as its modeled ranks; fill() adds the fewest inert points
that make it legal (CONTRACTS 1: 51 points, 5 per row, prerequisites at full rank). Moves: one point from one
modeled talent to another (and single adds while points are spare), first improvement in a shuffled order, until a
full pass finds nothing better; then KICKS random kicks (4 points moved at random), each followed by a new climb, so
a seed stuck at a local optimum (as the Fire sim build was) can still move. It runs under each scenario in
SCENARIOS: the model defaults and the untested flips that move the ranking most. robust() then scores every
distinct build found against every scenario.

Run from the repo root: python analysis/raid_search.py [scenario ...]
Writes forever-warlock-lab-drafts/mage-research/raid/search_v2.json (outside the repo); takes a while. With one
scenario it writes search_v2_<scenario>.json instead, so the scenarios can run in parallel;
python analysis/raid_search.py --merge then reads those files and writes search_v2.json with the robustness rows.
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
import raid_model as R  # noqa: E402

TALENTS = R.load_talents()
BY_KEY = {t['k']: t for t in TALENTS}
MODELED = ['ArcaneFocus', 'ArcaneConcentration', 'ArcaneImpact', 'ArcaneBlast', 'ArcaneMeditation', 'MissileBarrage',
           'PresenceOfMind', 'ArcaneMind', 'ArcaneInstability', 'ArcanePower',
           'WakeOfFire', 'Incineration', 'ImprovedFireball', 'Ignite', 'Pyroblast', 'ImprovedScorch', 'HotStreak',
           'MasterOfElements', 'CriticalMass', 'BlastWave', 'FirePower', 'Combustion',
           'ImprovedFrostbolt', 'ElementalPrecision', 'IceShards', 'PiercingIce', 'FrostChanneling', 'IceLance',
           'Shatter', 'FingersOfFrost', 'WintersChill', 'WandSpecialization']
INERT = [t['k'] for t in TALENTS if t['k'] not in MODELED]
POINTS = 51


def strip(tal):
    return {k: v for k, v in tal.items() if k in MODELED and v}


def fill(modeled):
    """Add the fewest inert points so every row has the 5-per-row points above it, and the inert prerequisites
    (Ice Barrier needs Cold Snap) hold. Returns the full build or None if impossible within 51 points."""
    b = dict(modeled)
    for tree in (0, 1, 2):
        rows = [t for t in TALENTS if t['t'] == tree]
        deepest = max([t['r'] for t in rows if b.get(t['k'])] or [-1])
        for r in range(1, deepest + 1):
            need = 5 * r
            have = sum(b.get(t['k'], 0) for t in rows if t['r'] < r)
            while have < need:
                # an inert point as deep as possible above row r, so it also counts for later rows
                cands = [t for t in rows if t['k'] in INERT and t['r'] < r and b.get(t['k'], 0) < t['m'] and not t['req']]
                if not cands:
                    return None
                cands.sort(key=lambda t: (-t['r'], t['c']))
                k = cands[0]['k']
                b[k] = b.get(k, 0) + 1
                have += 1
    if sum(b.values()) > POINTS:
        return None
    return b if not R.build_errors(b, talents=TALENTS) else None


def prereq_ok(m):
    for k, v in m.items():
        req = BY_KEY[k]['req']
        if v and req and req[0] in MODELED and m.get(req[0], 0) < req[1]:
            return False
    return True


def score(o, full):
    return R.evaluate(o, full)['total']


def climb(o, seed, rng, log=None):
    cur = strip(seed)
    full = fill(cur)
    assert full is not None, 'seed not legal'
    best = score(o, full)
    cache = {}
    improved = True
    passes = 0
    while improved:
        improved = False
        passes += 1
        moves = []
        spare = POINTS - sum(full.values())
        for a in MODELED:
            if spare > 0 and cur.get(a, 0) < BY_KEY[a]['m']:
                moves.append((None, a))
            if cur.get(a, 0) > 0:
                for b in MODELED:
                    if b != a and cur.get(b, 0) < BY_KEY[b]['m']:
                        moves.append((a, b))
        rng.shuffle(moves)
        for a, b in moves:
            cand = dict(cur)
            if a:
                cand[a] -= 1
                if not cand[a]:
                    del cand[a]
            cand[b] = cand.get(b, 0) + 1
            if not prereq_ok(cand):
                continue
            key = tuple(sorted(cand.items()))
            if key in cache:
                continue
            f = fill(cand)
            if f is None:
                cache[key] = None
                continue
            v = score(o, f)
            cache[key] = v
            if v > best + 0.05:
                cur, full, best = cand, f, v
                improved = True
                if log:
                    log('    %+.1f -> %.1f  (%s -> %s)' % (v - best, v, a, b))
                break
    return full, best, passes


def trees(full):
    pts = [0, 0, 0]
    for k, v in full.items():
        pts[BY_KEY[k]['t']] += v
    return '%d/%d/%d' % tuple(pts)


SEEDS = {
    'arcane-sim': R.SIM_ARCANE,
    'fire-sim': R.SIM_FIRE,
    'frost-sim': R.SIM_FROST,
    # Arcane Blast and Missile Barrage with a deep Frost tree
    'arcane-frost': {'ArcaneFocus': 5, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneBlast': 1, 'ArcaneMeditation': 3,
                     'MissileBarrage': 1, 'ImprovedFrostbolt': 5, 'ElementalPrecision': 5, 'IceShards': 5, 'PiercingIce': 3,
                     'IceLance': 1, 'Shatter': 3, 'FingersOfFrost': 2, 'WintersChill': 5},
    # Frostfire Bolt takes Fire and Frost talents both
    'frostfire': {'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'Pyroblast': 1, 'ImprovedScorch': 3, 'HotStreak': 1,
                  'MasterOfElements': 3, 'ElementalPrecision': 5, 'IceShards': 5, 'PiercingIce': 3, 'FrostChanneling': 3,
                  'IceLance': 1, 'Shatter': 3, 'FingersOfFrost': 2},
    # Arcane Power and Presence of Mind over a Fire core
    'arcane-fire': {'ArcaneFocus': 5, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneMeditation': 3, 'PresenceOfMind': 1,
                    'ArcaneMind': 5, 'ArcaneInstability': 3, 'ArcanePower': 1, 'Incineration': 3, 'ImprovedFireball': 5,
                    'Ignite': 5, 'ImprovedScorch': 3, 'Pyroblast': 1, 'HotStreak': 1},
    # the reviewer's Fire 19/31/1: Arcane Blast, Barrage and Meditation 3/3 over deep Fire
    'fire-ab': {'ArcaneFocus': 5, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneBlast': 1, 'ArcaneMeditation': 3,
                'MissileBarrage': 1, 'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'Pyroblast': 1,
                'ImprovedScorch': 3, 'HotStreak': 1, 'MasterOfElements': 3, 'CriticalMass': 3, 'FirePower': 5,
                'Combustion': 1, 'ElementalPrecision': 1},
    # Fire deep with Arcane Blast and Barrage
    'fire-arcane': {'ArcaneFocus': 5, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneBlast': 1, 'ArcaneMeditation': 3,
                    'MissileBarrage': 1, 'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'Pyroblast': 1,
                    'ImprovedScorch': 3, 'HotStreak': 1, 'MasterOfElements': 3, 'CriticalMass': 3, 'FirePower': 5},
}


SCENARIOS = {
    'defaults': {},
    'ilc0': {'iceLanceCoef': 0},
    'tooltip': {'abMask': 'tooltip'},
    'fullranks': {'downrank': 'full'},
    'nobuffs': {'raidBuffs': 'none'},
}
KICKS = 6


def kicked(cur, rng):
    """Move 4 random points between modeled talents, keeping the build legal."""
    for _ in range(4):
        have = [t for t in cur if cur[t] > 0]
        room = [t for t in MODELED if cur.get(t, 0) < BY_KEY[t]['m']]
        a, b = rng.choice(have), rng.choice(room)
        cand = dict(cur)
        cand[a] -= 1
        if not cand[a]:
            del cand[a]
        cand[b] = cand.get(b, 0) + 1
        if prereq_ok(cand) and fill(cand) is not None:
            cur = cand
    return cur


def search(o, seed, rng):
    """Climb, then KICKS kicks with a climb each; the best build found."""
    full, best, _ = climb(o, seed, rng)
    for _ in range(KICKS):
        f = fill(kicked(strip(full), rng))
        if f is None:
            continue
        cand, v, _ = climb(o, f, rng)
        if v > best + 0.05:
            full, best = cand, v
    return full, best


def key_of(build):
    return tuple(sorted(strip(build).items()))


def robust(found):
    """Every distinct build found, scored in every scenario as a share of that scenario's best."""
    builds = {}
    for per in found.values():
        for r in per.values():
            builds.setdefault(key_of(r['build']), r['build'])
    for s in R.SPECS:
        builds.setdefault(key_of(s['talents']), s['talents'])
    table = {}
    for k, b in builds.items():
        table[k] = {sc: R.evaluate(dict(R.DEFAULTS, **kw), b)['total'] for sc, kw in SCENARIOS.items()}
    best = {sc: max(v[sc] for v in table.values()) for sc in SCENARIOS}
    rows = []
    for k, v in table.items():
        shares = [v[sc] / best[sc] for sc in SCENARIOS]
        rows.append({'build': builds[k], 'trees': trees(builds[k]), 'dps': v, 'mean': sum(shares) / len(shares),
                     'worst': min(shares)})
    rows.sort(key=lambda r: -r['mean'])
    return rows


def main():
    rng = random.Random(20261001)
    names = [a for a in sys.argv[1:] if a in SCENARIOS] or list(SCENARIOS)
    out_dir = os.path.join(HERE, '..', '..', 'forever-warlock-lab-drafts', 'mage-research', 'raid')
    path = os.path.join(out_dir, 'search_v2.json')
    found = {}
    if '--merge' in sys.argv:          # the per-scenario files a parallel run wrote
        for sc in SCENARIOS:
            part = os.path.join(out_dir, 'search_v2_%s.json' % sc)
            if os.path.exists(part):
                with open(part, encoding='utf-8') as fh:
                    found.update(json.load(fh)['found'])
        names = []
    elif len(names) == 1:
        path = os.path.join(out_dir, 'search_v2_%s.json' % names[0])
    for sc in names:
        o = dict(R.DEFAULTS, **SCENARIOS[sc])
        seeds = dict(SEEDS)
        seeds.update({'page-' + s['id']: s['talents'] for s in R.SPECS})
        found[sc] = {}
        for name, seed in seeds.items():
            if fill(strip(seed)) is None:
                continue
            t0 = time.time()
            full, best = search(o, seed, rng)
            found[sc][name] = {'build': full, 'dps': best, 'trees': trees(full)}
            print('%-10s %-16s %s %.1f  (%.0f s)' % (sc, name, trees(full), best, time.time() - t0), flush=True)
    rows = robust(found)
    print('\nrobustness: share of each scenario best (%s)' % ', '.join(SCENARIOS))
    for r in rows[:25]:
        print('%-9s mean %.3f worst %.3f  %s  %s' % (r['trees'], r['mean'], r['worst'],
                                                   ' '.join('%.0f' % r['dps'][sc] for sc in SCENARIOS),
                                                   {k: v for k, v in sorted(strip(r['build']).items())}))
    with open(path, 'w', encoding='utf-8', newline='\r\n') as fh:
        json.dump({'scenarios': SCENARIOS, 'found': found, 'robust': rows}, fh, indent=1, sort_keys=True)
        fh.write('\n')


if __name__ == '__main__':
    main()
