"""Invariants of the AoE model (models/aoe.py). Run from the repo root: python tests/aoe_test.py

1. More mobs never lower damage dealt: one AoE damage event on a larger pack deals at least as much, with and without
   a target cap, and so does a scripted pull (fixed casts at fixed times, no cap). Under a cap a whole pull can deal a
   little less with more mobs, because the cap spreads Frost Nova's root and Blizzard's chill thinner and the extras
   leave the storm sooner; the test prints how much (a note, not a failure).
2. A higher slow never makes the Mage take more hits: a free pack walking at the Mage through one Blizzard, and a
   scripted pull, land no more hits when the chill is stronger or lasts longer. The loops themselves make discrete
   choices, so the test also prints (without failing) how often the scored model gets worse with a stronger slow.
3. A failed pull is never scored: run_pull gives spk None when the Mage dies, breakeven() skips it, and better()
   ranks any surviving pull above it. Failures are labelled: caught (health under the floor first) or oom (out of
   mana first).
4. The embedded values match the gap register (skipped when the register file is not next to the repo).
5. Calibration: one mob through the AoE engine (the small-pull loop, planner build) lands within 10% of
   character.evaluate()'s seconds per kill at 20, 30, 40, 50 and 60. Small-pull results are trusted only while this
   passes.
6. The applied slows: the Blizzard chill the engine applies equals the register's blizzardChillTotal (Improved
   Blizzard 3 + Permafrost 3), at full strength on the share a tick hits; Cone of Cold's is 40% + Permafrost's.
7. A single-target spell lands on one whole mob: Frostbolt takes exactly 1.0 of weight across cohorts and deals one
   mob's damage.
8. The potion floor: a pull that drinks cannot repeat faster than the 2 min potion cooldown, one that does not has
   no such floor, a no-potion variant never drinks, and best_pull keeps the faster of the two.
Exit code 1 on any failure.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))

import aoe                                                  # noqa: E402
import character                                            # noqa: E402
import leveling_sim as ls                                   # noqa: E402
from character import make_char, mob_hp                     # noqa: E402

FAILS = []
CHECKS = [0]


def check(ok, msg):
    CHECKS[0] += 1
    if not ok:
        FAILS.append(msg)
        print('FAIL', msg)


def setup(L, arch, o=None):
    o = aoe.opts(o)
    ch = make_char(L, aoe.aoe_talents(arch, L), 1, 'none', **dict(aoe.char_opts(o), armor=o['aoe_armor']))
    return ch, aoe.spell_consts(ch, o), o


# ---------------------------------------------------------------- 1. more mobs never lower damage dealt
def test_more_mobs_event():
    for L in (30, 60):
        ch, K, o0 = setup(L, 'blizzard')
        for cap in (0, 5, 4):
            o = dict(o0, cap=cap)
            for name, r in (('ArcaneExplosion', aoe.AE_RADIUS), ('ConeOfCold', K['coc_r']), ('Blizzard', 30.0)):
                last = -1.0
                for n in range(1, 11):
                    P = aoe.Pull(ch, K, n, mob_hp(L), 'blizzard', aoe.POLICIES['blizzard'][0], o)
                    aoe.strike(P, name, aoe.within(P, r))
                    check(P.dealt >= last - 1e-9, f'{name} L{L} cap {cap}: {n} mobs deal {P.dealt:.1f} < {last:.1f}')
                    last = P.dealt


SCRIPT = (('FrostNova', 0.0), ('walk', 0.2, 2.8), ('Blizzard', 3.0), ('ConeOfCold', 12.0), ('ArcaneExplosion', 14.0),
          ('ArcaneExplosion', 16.0), ('FrostNova', 22.0))


def scripted(L, n, o, until=26.0, script=SCRIPT):
    """A pull with fixed actions at fixed times and no loop decisions, so pulls of different sizes or slows take the
    same actions: the mechanics alone. The storm sits where Nova froze the pack. Returns the Pull at the end."""
    ch, K, oo = setup(L, 'blizzard', o)
    P = aoe.Pull(ch, K, n, mob_hp(L) * 50, 'blizzard', aoe.POLICIES['blizzard'][0], oo)
    done = set()
    while P.t < until:
        aoe.land(P)
        aoe.ticks(P)
        aoe.reap(P)
        aoe.move(P)
        aoe.attacks(P)
        P.walk = any(a[0] == 'walk' and a[1] <= P.t < a[2] for a in script)
        for i, a in enumerate(script):
            if a[0] != 'walk' and i not in done and P.t >= a[1] - 1e-9 and not P.chan:
                done.add(i)
                P.gcd = 0.0
                if a[0] in P.cd:
                    P.cd[a[0]] = 0.0
                P.mana = ch.max_mana
                aoe.cast(P, a[0])
                if P.chan:
                    P.chan['cx'] = aoe.GAP0 - aoe.LEAD * aoe.BZ_RADIUS
        aoe.merge(P)
        P.t += aoe.DT
    return P


def test_more_mobs_pull():
    for L in (30, 60):
        last = -1.0
        for n in range(1, 11):
            # the same path for every pull size: no daze on the walk (more attackers daze more)
            P = scripted(L, n, dict(daze=0.0))
            check(P.dealt >= last - 1e-6, f'scripted pull L{L}: {n} mobs deal {P.dealt:.0f} < {last:.0f}')
            last = P.dealt


def note_capped_pull():
    """Not an assertion: the largest drop in a scripted pull's damage from one more mob, under a cap."""
    worst = 0.0
    for L in (30, 60):
        for cap in (5, 4):
            last = None
            for n in range(cap, 11):
                d = scripted(L, n, dict(cap=cap, daze=0.0, bz_pushback='none')).dealt
                if last:
                    worst = max(worst, 1 - d / last)
                last = d
    print(f'note: under a target cap, one more mob cost a scripted pull at most {worst:.1%} of its damage (not a '
          f'failure: the cap spreads Nova and the chill thinner)')


# ---------------------------------------------------------------- 2. a higher slow never adds hits
def channel_hits(L, slow, chill_s, n=4, gap=30.0):
    """A free pack at gap yards walks at the Mage through one Blizzard aimed at it; hits taken in 12 s."""
    ch, K, o = setup(L, 'blizzard', dict(bz_slow=slow, bz_chill_s=chill_s, mob_dps_mult=0.0, fb_rolls='every'))
    K = dict(K, fb=0.0)                   # no Frostbite freezes: the slow alone
    P = aoe.Pull(ch, K, n, mob_hp(L) * 50, 'blizzard', aoe.POLICIES['blizzard'][0], o)
    P.mobs[0].x = gap
    aoe.cast(P, 'Blizzard')
    while P.t < 12.0:
        aoe.land(P)
        aoe.ticks(P)
        aoe.move(P)
        aoe.attacks(P)
        P.t += aoe.DT
    return P.hits


def test_slow_hits_channel():
    for L in (30, 60):
        for chill_s in (1.5, 2.0, 4.5):
            last = 1e9
            for slow in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75):
                h = channel_hits(L, slow, chill_s)
                check(h <= last + 1e-9, f'L{L} chill {chill_s} s: slow {slow} gives {h:.2f} hits > {last:.2f}')
                last = h
        for slow in (0.3, 0.5, 0.75):
            last = 1e9
            for chill_s in (0.5, 1.5, 2.0, 3.0, 4.5):
                h = channel_hits(L, slow, chill_s)
                check(h <= last + 1e-9, f'L{L} slow {slow}: chill {chill_s} s gives {h:.2f} hits > {last:.2f}')
                last = h


def test_slow_hits_pull():
    for L in (30, 60):
        for n in (3, 6):
            for chill_s in (1.5, 2.0, 4.5):
                last = 1e9
                for slow in (0.0, 0.3, 0.4, 0.5, 0.6, 0.75):
                    h = scripted(L, n, dict(bz_slow=slow, bz_chill_s=chill_s, mob_dps_mult=0.0)).hits
                    check(h <= last + 1e-6, f'scripted pull L{L} n{n} chill {chill_s} s: slow {slow} gives {h:.2f} hits '
                                            f'> {last:.2f}')
                    last = h


def note_slow_scored():
    """Not an assertion: how often the scored model (the best surviving loop) gets worse with a stronger Blizzard
    slow. The loops make discrete choices, so near the survival and mana edge a stronger slow can flip a pull."""
    worse = steps = 0
    for L in (40, 60):
        for n in (2, 4, 6):
            prev = None
            for slow in (0.3, 0.4, 0.5, 0.6, 0.75):
                r = aoe.best_pull(L, n, 'blizzard', dict(bz_slow=slow), hp_mults=(1.0,))
                if prev is not None:
                    steps += 1
                    worse += bool(prev['feasible'] and (not r['feasible'] or r['spk'] > prev['spk'] * 1.01))
                prev = r
    print(f'note: the scored model got worse with a stronger slow in {worse} of {steps} steps (not a failure)')


# ---------------------------------------------------------------- 3. a failed pull is never scored
def test_failed_never_scored():
    dead = aoe.run_pull(40, 6, 'ae', aoe.POLICIES['ae'][0], dict(mob_dps_mult=20.0))
    check(not dead['feasible'] and dead['spk'] is None, 'a pull the Mage dies in must have spk None')
    ok = dict(dead, feasible=True, spk=50.0)
    check(aoe.better(ok, dead) and not aoe.better(dead, ok), 'better() must rank a surviving pull above a failed one')
    b = aoe.breakeven(100.0, [(2, dead), (3, ok)])
    check(b['n_star'] == 3 and b['best_n'] == 3, f'breakeven must skip the failed pull size: {b}')
    b = aoe.breakeven(100.0, [(2, dead), (3, dict(dead))])
    check(b['n_star'] is None and b['best_spk'] is None and b['max_safe'] is None, f'all failed must give none: {b}')
    for arch in aoe.ARCHES:
        r = aoe.best_pull(max(30, aoe.ARCH_FROM[arch]), 8, arch, dict(mob_dps_mult=20.0))
        check(r['spk'] is None, f'{arch}: best_pull of a deadly pull must not carry a score')
        check(r['fail'] == 'caught', f'{arch}: a pull that kills the Mage at once is caught, got {r["fail"]}')
    r = aoe.run_pull(40, 4, 'blizzard', aoe.POLICIES['blizzard'][0], dict(mob_dps_mult=0.0, hp_scale=20.0))
    check(r['fail'] == 'oom', f'a pull the Mage cannot finish and is never hurt in is oom, got {r["fail"]}')


# ---------------------------------------------------------------- 4. register
def test_register():
    path = os.environ.get('AOE_REGISTER') or os.path.join(HERE, '..', '..', 'forever-warlock-lab-drafts',
                                                          'mage-research', 'gap', 'aoe_assumptions.json')
    if not os.path.exists(path):
        print('skip: register not found at', path)
        return
    reg = {i['id']: i for i in json.load(open(path, encoding='utf-8'))['items']}
    d = aoe.AOE_DEFAULTS
    ch = make_char(40, aoe.aoe_talents('blizzard', 40), 1, 'none')
    pairs = [
        ('playerRunSpeed', ch.player_speed, reg['playerRunSpeed']['value']),
        ('mobRunSpeed', character.MOB_SPEED, reg['mobRunSpeed']['value']),
        ('improvedBlizzardSlow', aoe.IMP_BLIZZARD, reg['improvedBlizzardSlow']['value']['perRank']),
        ('permafrostExtraSlow', [round(x * 100) for x in aoe.ls.TV['PermafrostSlow']],
         reg['permafrostExtraSlow']['value']['perRank']),
        ('chillDurationBlizzard', aoe.BZ_CHILL_S, reg['chillDurationBlizzard']['value']['base']),
        ('chillRefreshInStorm', d['bz_refresh'], reg['chillRefreshInStorm']['value']),
        ('blizzardRadius', aoe.BZ_RADIUS, reg['blizzardRadius']['value']),
        ('blizzardRange', aoe.BZ_RANGE, reg['blizzardRange']['value']['base']),
        ('coneOfColdShape', aoe.COC_RADIUS, reg['coneOfColdShape']['value']['radius']),
        ('arcaneExplosionRadius', aoe.AE_RADIUS, reg['arcaneExplosionRadius']['value']),
        ('frostNovaRadius', aoe.NOVA_RADIUS, reg['frostNovaRadius']['value']['base']),
        ('flamestrikeArea', (aoe.FS_RADIUS, aoe.FS_RANGE), (reg['flamestrikeArea']['value']['radius'],
                                                            reg['flamestrikeArea']['value']['range'])),
        ('blastWaveRadius', aoe.BW_RADIUS, reg['blastWaveRadius']['value']),
        ('meleeRange', d['reach'], reg['meleeRange']['value']),
        ('blink', (aoe.BLINK['yd'], aoe.BLINK['cd']), (reg['blink']['value']['distance'],
                                                       reg['blink']['value']['cooldownSec'])),
        ('frostNovaRoot', aoe.NOVA_ROOT_S, reg['frostNovaRoot']['value']['rootSecEveryRank']),
        ('frostNovaBreakChance', ch.nova_break, reg['frostNovaBreakChance']['value']),
        ('frostbiteFreeze', aoe.FB_ROOT_S, reg['frostbiteFreeze']['value']['rootSec']),
        ('armorChill', (aoe.ARMOR_MOVE * 100, aoe.ARMOR_S), (reg['armorChill']['value']['moveSlowPct'],
                                                             reg['armorChill']['value']['durationSec'])),
        ('creatureDaze', (aoe.DAZE_SLOW * 100, aoe.DAZE_S, d['daze']),
         (reg['creatureDaze']['value']['slowPct'], reg['creatureDaze']['value']['durationSec'],
          reg['creatureDaze']['value']['chanceEqualLevel'])),
        ('mobSwingTime', ch.swing, reg['mobSwingTime']['value']),
        ('gatherTime', (d['gather0'], d['gather_per']), (8.0, 6.0)),
        ('humanoidFlee', d['flee_at'] * 100, reg['humanoidFlee']['value']['healthPct']),
        ('aoeTargetCap', d['cap'], 0 if reg['aoeTargetCap']['value'] == 'none' else reg['aoeTargetCap']['value']),
        ('blizzardTicks', d['bz_first'], reg['blizzardTicks']['value']['firstTickSec']),
        ('blizzardTickCrit', d['bz_crit'], reg['blizzardTickCrit']['value']),
        ('pullSize', 4, reg['pullSize']['value']),
    ]
    check(reg['gatherTime']['value'] == '8 + 6 x (n - 1)', 'register gatherTime formula changed')
    for name, mine, theirs in pairs:
        check(mine == theirs, f'register {name}: model {mine} vs register {theirs}')
    b = aoe.BLIZZARD[-1]
    check(abs(b[4] - 0.042) < 1e-9 and b[6] == reg['blizzardTicks']['value']['ticks'], 'Blizzard rows vs register')


# ---------------------------------------------------------------- 5. calibration
CAL_LEVELS, CAL_TOL = (20, 30, 40, 50, 60), 0.10


def calibration(L):
    """(engine seconds per kill for one mob, evaluate()'s): the small-pull loop on the planner build at n=1."""
    r = aoe.best_pull(L, 1, 'nb')
    return (r['spk'] if r['feasible'] else None), aoe.baseline(L)[1]['spk']


def test_calibration():
    for L in CAL_LEVELS:
        e, b = calibration(L)
        gap = f' ({e / b - 1:+.1%})' if e else ''
        print(f'  calibration L{L}: engine {e if e is None else round(e, 2)} vs evaluate {b:.2f}{gap}')
        check(e is not None and abs(e / b - 1) <= CAL_TOL, f'calibration L{L}: one mob {e} vs single target {b:.2f}')


# ---------------------------------------------------------------- 6. applied slows
def test_applied_slow():
    total = 50
    path = os.path.join(HERE, '..', '..', 'forever-warlock-lab-drafts', 'mage-research', 'gap', 'aoe_assumptions.json')
    if os.path.exists(path):
        total = {i['id']: i for i in json.load(open(path, encoding='utf-8'))['items']}['blizzardChillTotal']['value']
    for L in (40, 60):
        ch, K, o = setup(L, 'blizzard')
        check(abs(K['bz_slow'] - total / 100.0) < 1e-9,
              f'L{L}: Blizzard slow {K["bz_slow"]} vs blizzardChillTotal {total}')
        check(abs(K['coc_slow'] - (0.40 + ls.TV['PermafrostSlow'][2])) < 1e-9, f'L{L}: Cone slow {K["coc_slow"]}')
        P = aoe.Pull(ch, dict(K, fb=0.0), 4, mob_hp(L) * 50, 'blizzard', aoe.POLICIES['blizzard'][0], o)
        P.mobs[0].x = 10.0
        aoe.strike(P, 'Blizzard', list(P.mobs), chill=(K['bz_slow'], K['bz_chill']))
        hit = [c for c in P.mobs if aoe.slow_at(c, P.t) > 0]
        check(all(abs(aoe.slow_at(c, P.t) - K['bz_slow']) < 1e-9 for c in hit),
              f'L{L}: a Blizzard tick must slow the share it hits by the full {K["bz_slow"]}, not a diluted slow')
        check(abs(aoe.weight(hit) - 4 * K['sp']['Blizzard']['hit']) < 1e-9, f'L{L}: chilled weight {aoe.weight(hit)}')


# ---------------------------------------------------------------- 7. whole-mob single-target spells
def test_whole_mob_frostbolt():
    for L in (30, 60):
        ch, K, o = setup(L, 'cone')
        K = dict(K, fb=0.0, fof_n=0, wc_cap=0)
        fb = K['sp']['Frostbolt']
        ev = fb['x'] * fb['hit'] * (1 + fb['crit'] * (fb['cm'] - 1))
        for weights in ((3.0,), (0.3, 0.45, 2.25), (0.6,)):
            P = aoe.Pull(ch, K, 3, mob_hp(L) * 50, 'cone', aoe.POLICIES['cone'][0], o)
            P.engaged = True
            c = P.mobs[0]
            c.w = weights[0]
            for w in weights[1:]:
                m = c.split(0.5, P)
                m.w = w
            for i, m in enumerate(P.mobs):          # different health, so focus fire has a choice
                m.hp -= 10.0 * i
            aoe.cast(P, 'Frostbolt')
            tgt = [m for m in P.mobs if m.focus == P.cast['fid']]
            want = min(1.0, sum(weights))
            check(abs(aoe.weight(tgt) - want) < 1e-9,
                  f'L{L} {weights}: Frostbolt target weight {aoe.weight(tgt)} != {want}')
            d0 = P.dealt
            P.t = P.cast['end']
            aoe.land(P)
            check(abs(P.dealt - d0 - ev * want) < 1e-6 * ev, f'L{L} {weights}: Frostbolt dealt {P.dealt - d0:.1f}, '
                                                              f'one mob is {ev * want:.1f}')


# ---------------------------------------------------------------- 8. the potion floor
def test_potion_floor():
    ch, K, o = setup(40, 'nb')
    res = dict(T=20.0, mana=0.5 * ch.max_mana, hp=ch.max_hp, last_spend=19.0, pot=True, gem=False, nova_first=None,
               nova_last=-1e9, ib_first=None, ib_last=-1e9)
    _, x = aoe.per_kill(ch, K, 2, res, o)
    check(x['cycle'] >= aoe.POTION_CD - 1e-9, f'a pull that drinks must not repeat faster than {aoe.POTION_CD} s')
    _, x = aoe.per_kill(ch, K, 2, dict(res, pot=False), o)
    check(x['cycle'] < aoe.POTION_CD, f'a pull that does not drink has no potion floor: cycle {x["cycle"]:.1f}')
    r = aoe.run_pull(40, 4, 'blizzard', dict(aoe.POLICIES['blizzard'][0], pots=False))
    check(not r['pot'] and not r['gem'], 'a no-potion variant must never drink or use a gem in the fight')
    for L, n in ((60, 2), (60, 3)):
        runs = [aoe.run_pull(L, n, 'nb', dict(p, pots=x)) for p in aoe.POLICIES['nb'] for x in (True, False)]
        ok = [r['spk'] for r in runs if r['feasible']]
        best = aoe.best_pull(L, n, 'nb')
        if ok:
            check(abs(best['spk'] - min(ok)) < 1e-9,
                  f'best_pull L{L} n{n} must keep the fastest of both potion variants')


def test_gather_by_start():
    """A gathered pack pays the register's gather; a group pulled from range is not gathered, only found."""
    o = aoe.opts()
    for n in (1, 2, 5):
        check(aoe.gather(n, o, 'blizzard') == o['gather0'] + o['gather_per'] * (n - 1), f'gathered pack of {n}')
        for arch in ('nb', 'cone'):
            check(aoe.gather(n, o, arch) == o['gather0'] + o['find_per'] * (n - 1), f'{arch}: a range start of {n}')
    check(aoe.gather(1, o, 'nb') == o['gather0'], 'one mob from range pays the single-target walk only')


def main():
    for f in (test_more_mobs_event, test_more_mobs_pull, test_slow_hits_channel, test_slow_hits_pull,
              test_failed_never_scored, test_register, test_applied_slow, test_whole_mob_frostbolt, test_potion_floor,
              test_gather_by_start, test_calibration):
        n0 = len(FAILS)
        f()
        print(f'{f.__name__}: {"ok" if len(FAILS) == n0 else f"{len(FAILS) - n0} failures"}')
    note_capped_pull()
    note_slow_scored()
    print(f'{CHECKS[0]} checks, {len(FAILS)} failures')
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
