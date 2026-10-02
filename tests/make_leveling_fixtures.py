"""Generate expected leveling results from the Python model for tests/leveling_parity_test.js.

Run from the repo root: python tests/make_leveling_fixtures.py
It first checks the model's embedded data against data/: every spell rank row (check_tables) and every
talent per-rank value (check_talents below), that every tv() lookup in both models names a real talent
(check_tv_calls), and that the chill's slow follows Permafrost's ranks (slow_cases). Then it writes
tests/leveling_fixtures.json: a grid of builds (the planner order and the three tree-first orders of
analysis/leveling_paths.py, and no talents), levels, gear, races and options; and tests/leveling_slow_fixtures.json,
the chill slow at 0 to 3 ranks of Permafrost.
"""
import io
import json
import os
import re
import sys
import contextlib
from multiprocessing import Pool

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'models'))
sys.path.insert(0, os.path.join(ROOT, 'analysis'))

import leveling_sim as ls                         # noqa: E402
from character import evaluate, valid, make_char, KEYS, SCORED, BY_KEY, POLICIES   # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from leveling_paths import build, ORDERS      # noqa: E402

RACES = ['none', 'human', 'gnome', 'skyborne', 'orc', 'undead', 'troll']

# leveling_sim.TV key -> (talent key, perRank field in data/talents.json, divisor)
TV_SOURCE = dict(
    WandSpecialization=('WandSpecialization', 'wandDamagePct', 100), ArcaneFocus=('ArcaneFocus', 'spellHitPct', 100),
    ImprovedChanneling=('ImprovedChanneling', 'pushbackProtectPct_ArcaneMissiles', 100),
    ImprovedChannelingAB=('ImprovedChanneling', 'pushbackProtectPct_ArcaneBlast', 100),
    ArcaneConcentration=('ArcaneConcentration', 'clearcastingProcPct', 100), ArcaneImpact=('ArcaneImpact', 'critPct', 100),
    ArcaneMeditation=('ArcaneMeditation', 'regenWhileCastingPct', 100), ArcaneMind=('ArcaneMind', 'intellectPct', 100),
    ArcaneMindCrit=('ArcaneMind', 'arcaneCritDamageBonusPct', 100),
    ArcaneInstability=('ArcaneInstability', 'damagePct', 100),
    WakeOfFire=('WakeOfFire', 'fireBlastCooldownReductionMs', 1000),
    WakeOfFireCrit=('WakeOfFire', 'fireBlastCritPctAfterKill', 100), Incineration=('Incineration', 'critPct', 100),
    ImprovedFireball=('ImprovedFireball', 'castTimeReductionMs', 1000), Ignite=('Ignite', 'ignitePctOfCrit', 100),
    Impact=('Impact', 'stunProcPct', 100), BurningSoul=('BurningSoul', 'pushbackProtectPct', 100),
    ImprovedScorch=('ImprovedScorch', 'fireVulnerabilityApplyPct', 100),
    MasterOfElements=('MasterOfElements', 'refundPctOfBaseCost', 100), CriticalMass=('CriticalMass', 'critPct', 100),
    FirePower=('FirePower', 'fireDamagePct', 100), ImprovedFrostbolt=('ImprovedFrostbolt', 'castTimeReductionMs', 1000),
    ElementalPrecision=('ElementalPrecision', 'spellHitPct', 100),
    IceShards=('IceShards', 'frostCritDamageBonusPct', 100), Permafrost=('Permafrost', 'chillDurationPct', 100),
    PermafrostSlow=('Permafrost', 'extraSlowPct', 100),
    ImprovedFrostNova=('ImprovedFrostNova', 'frostNovaCooldownReductionMs', 1000),
    Frostbite=('Frostbite', 'freezeProcPct', 100), PiercingIce=('PiercingIce', 'frostDamagePct', 100),
    FrostChanneling=('FrostChanneling', 'frostManaCostReductionPct', 100), Shatter=('Shatter', 'critPctVsFrozen', 100),
    ImprovedConeOfCold=('ImprovedConeOfCold', 'coneOfColdDamagePct', 100), FingersOfFrost=('FingersOfFrost', 'charges', 1),
    WintersChill=('WintersChill', 'applyChancePct', 100), ArcaneGeometry=('ArcaneGeometry', 'arcaneRangeYards', 1),
    FlameThrowing=('FlameThrowing', 'fireRangeYards', 1), ArcticReach=('ArcticReach', 'rangePct_FrostboltBlizzard', 100))


def check_tables(path=None):
    """Every rank row in models/leveling_sim.py against data/mage_spells.json; returns the mismatches (empty when
    all agree)."""
    path = path or os.path.join(ROOT, 'data', 'mage_spells.json')
    recs = json.load(open(path, encoding='utf-8'))['records']

    def val(x, *p):
        for key in p:
            if not isinstance(x, dict) or key not in x:
                return None
            x = x[key]
        return x['value'] if isinstance(x, dict) and 'value' in x else x

    def ranks(name):
        return sorted([r for r in recs if r['spell'] == name and r.get('rank')], key=lambda r: r['rank'])
    bad = []
    names = dict(Frostbolt='Frostbolt', Fireball='Fireball', ArcaneMissiles='Arcane Missiles', FireBlast='Fire Blast',
                 Scorch='Scorch', Pyroblast='Pyroblast', ArcaneBlast='Arcane Blast', IceLance='Ice Lance',
                 FrostfireBolt='Frostfire Bolt', ArcaneExplosion='Arcane Explosion', ConeOfCold='Cone of Cold',
                 FrostNova='Frost Nova', BlastWave='Blast Wave')
    for key, name in names.items():
        rows = ls.TABLES[key] + ([ls.TOME[key]] if key in ls.TOME else [])
        src = ranks(name)
        if len(rows) != len(src):
            bad.append((key, 'rank count', len(rows), len(src)))
        for row, r in zip(rows, src):
            dm = r['damage']
            want = [val(r, 'level_learned'), val(dm, 'base_avg_at_learn'), val(dm, 'per_level'), val(r, 'max_level'),
                    val(dm, 'sp_coefficient'), val(r, 'mana_cost') or 0,
                    val(r, 'missiles') if key == 'ArcaneMissiles' else (val(r, 'cast_ms') or 0) / 1000]
            if r.get('dot'):
                want += [val(r, 'dot', 'base_avg_at_learn'), val(r, 'dot', 'ticks'), val(r, 'dot', 'period_ms') / 1000,
                         val(r, 'dot', 'sp_coefficient')]
            if [float(x) for x in row] != [float(x) for x in want]:
                bad.append((key, r['rank'], row, want))
            if key == 'Frostbolt' and ls.FROSTBOLT_SLOW_S[row[0]] * 1000 != val(r, 'slow_duration_ms'):
                bad.append((key, r['rank'], 'slow'))
    for key, name, table in (('WATER', 'Conjure Water', ls.WATER + [ls.MOUNTAIN_WATER]), ('FOOD', 'Conjure Food', ls.FOOD)):
        for row, r in zip(table, ranks(name)):
            want = [val(r, 'level_learned'), val(r, 'drink_mana_per_5s') or val(r, 'food_health_per_5s'),
                    (val(r, 'drink_duration_ms') or val(r, 'food_duration_ms')) / 1000, val(r, 'mana_cost'),
                    val(r, 'count_at_learn'), val(r, 'count_per_level'), val(r, 'max_level')]
            if [float(x) for x in row] != [float(x) for x in want]:
                bad.append((key, r['rank'], row, want))
    for row, r in zip(ls.GEMS, ranks('Conjure Mana Gem')):
        lo, hi = val(r, 'mana_restored_min_max')
        if [row[0], row[1], row[2]] != [val(r, 'level_learned'), val(r, 'mana_cost'), (lo + hi) / 2]:
            bad.append(('GEMS', r['rank'], row))
    for row, r in zip(ls.ICE_BARRIER, ranks('Ice Barrier')):
        want = [val(r, 'level_learned'), val(r, 'absorb_at_learn'), round(val(r, 'absorb_per_level'), 6),
                val(r, 'max_level'), val(r, 'mana_cost')]
        if [float(x) for x in row] != [float(x) for x in want]:
            bad.append(('ICE_BARRIER', r['rank'], row, want))
    return bad


def check_talents():
    """Every talent value the model embeds against data/talents.json, and SCORED against the talent list."""
    bad = []
    for key, (tk, field, div) in TV_SOURCE.items():
        want = [round(x / div, 6) for x in BY_KEY[tk]['perRank'][field]]
        if [round(x, 6) for x in ls.TV[key]] != want:
            bad.append((key, ls.TV[key], want))
    pr = BY_KEY
    checks = [(pr['FingersOfFrost']['perRank']['procPctOnChill'] / 100, ls.FOF_CHANCE, 'FoF chance'),
              (pr['HotStreak']['perRank']['pyroblastCastReductionPctPerStack'] / 100, ls.HOT_STREAK_CUT, 'Heating Up'),
              (pr['Combustion']['perRank']['endsAfterNonPeriodicFireCrits'], ls.COMB_CRITS, 'Combustion crits'),
              (pr['MissileBarrage']['perRank']['procPct_ArcaneBlast'] / 100, ls.BARRAGE['ArcaneBlast'], 'Barrage AB'),
              (pr['MissileBarrage']['perRank']['procPct_FireballFrostboltFrostfireBolt'] / 100, ls.BARRAGE['Frostbolt'],
               'Barrage Frostbolt'),
              (pr['ArcaneBlast']['perRank']['arcaneBlastCostPctPerStack'] / 100, 1.75, 'AB cost a stack'),
              (pr['ImprovedFrostNova']['perRank']['frostNovaCooldownReductionMs'][1] / 1000, 4.0, 'Imp Frost Nova')]
    bad += [(label, got, want) for want, got, label in checks if abs(want - got) > 1e-9]
    unknown = [k for k in SCORED if k not in KEYS]
    if unknown:
        bad.append(('SCORED', unknown))
    return bad


TV_CALL = re.compile(r"\btv\(\s*[\w.]+\s*,\s*'(\w+)'(?:\s*,\s*'(\w+)')?\s*\)")
CHILL_SLOW = 0.40       # the Frostbolt and Cone of Cold chill's movement slow before Permafrost (the model's base)


def check_tv_calls():
    """Every literal tv(ch, 'Talent'[, 'Table']) in the Python and JS models names a real talent and a known table.
    tv() reads the rank of its first argument, so a table name there (tv(ch, 'PermafrostSlow')) silently reads rank 0."""
    bad = []
    for rel in ('models/leveling_sim.py', 'leveling.js'):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            calls = TV_CALL.findall(f.read())
        if len(calls) < 10:
            bad.append((rel, 'only %d tv() calls found: the scan pattern is stale' % len(calls)))
        bad += [(rel, 'tv', key, table) for key, table in calls if key not in KEYS or (table or key) not in ls.TV]
    return bad


def slow_cases():
    """The chill's movement slow at 0 to 3 ranks of Permafrost: data/talents.json against the model."""
    out, bad = [], []
    per = BY_KEY['Permafrost']['perRank']['extraSlowPct']
    for r in range(len(per) + 1):
        tal = dict(ImprovedFrostbolt=5, **({'Permafrost': r} if r else {}))
        assert valid(tal), tal
        want = CHILL_SLOW + (per[r - 1] / 100 if r else 0.0)
        got = ls.fight_consts(make_char(30, tal), POLICIES['Frostbolt'])['slow']
        if abs(got - want) > 1e-12:
            bad.append(('Permafrost slow', r, got, want))
        out.append(dict(level=30, talents=tal, rank=r, slow=want))
    return out, bad


def job(c):
    kw = dict(c['opts'])
    n, r = evaluate(c['level'], c['talents'], c['gear'], c['race'], **kw)
    return dict(c, policy=n, spk=r['spk'], ttk=r['ttk'], rest=r['rest'], feasible=r['feasible'], taken=r['taken'],
                pots=r['pots'], evo=r['evo'], mana_spent=r['mana_spent'])


OPTION_CASES = [dict(potions=False), dict(gems=False), dict(evocation=False), dict(wowhead_drinks=True),
                dict(spirit_drink=False), dict(regen_stack='max'), dict(below20=True), dict(il_coef=0.0),
                dict(il_coef=0.429), dict(kite=False), dict(nova_break=1.0), dict(fb_break=0.0), dict(pushback=False),
                dict(thrill=5), dict(top_ranks=True), dict(dd_mode='base'), dict(armor='frost'),
                dict(frostbite_source='spells'), dict(mountain_water=True), dict(level_diff=2), dict(level_diff=3),
                dict(mob_dps_mult=1.5), dict(mob_speed=7.0), dict(hp_mults=[1.0]), dict(top=1), dict(mods=False),
                dict(downrank=False), dict(gear_int=0.5, gear_sta=2.0, gear_spi=1.0), dict(armor_slow=0.0),
                dict(step_s=1.0), dict(pull_gap=10.0), dict(player_speed=5.0), dict(swing=1.5), dict(pushback_s=1.0),
                dict(travel=12.0), dict(level_diff=1), dict(low_ranks='full'), dict(low_ranks='tbc'),
                dict(low_ranks='classic'), dict(nova_break=0.2), dict(top=2), dict(pair_top=0), dict(wand_breaks=False),
                dict(mob_dps_mult=6.0, kite=False, potions=False)]   # the last makes some builds die: infeasible path
# builds that take the range talents (they lengthen the pull)
RANGE_BUILDS = [(22, 'arcane-geometry', dict(ArcaneFocus=3, WandSpecialization=2, ArcaneGeometry=2, ArcaneConcentration=5)),
                (24, 'flame-throwing', dict(ImprovedFireball=5, Ignite=5, FlameThrowing=2, Pyroblast=1, Incineration=2)),
                (30, 'arctic-reach', dict(ImprovedFrostbolt=5, Frostbite=3, IceShards=3, PiercingIce=3, IceLance=1,
                                          ArcticReach=2, Shatter=3, Permafrost=1)),
                (45, 'arctic-reach', dict(ImprovedFrostbolt=5, Frostbite=3, IceShards=5, PiercingIce=3, IceLance=1,
                                          ArcticReach=2, Shatter=3, Permafrost=3, ImprovedFrostNova=2, FingersOfFrost=2,
                                          WintersChill=5, FrostChanneling=2))]
RACE_OPTIONS = [('human', dict(sword=False)), ('skyborne', dict(leyline='long')), ('skyborne', dict(leyline='off')),
                ('troll', dict(beast_share=1.0)), ('undead', dict(humanoid_share=1.0)),
                ('undead', dict(totg_source='spells')),
                ('skyborne', dict(elemental_share=1.0))]


def cases():
    out = []

    def add(L, bname, tal, gear, race, opts=None):
        assert valid(tal), (bname, L)
        out.append(dict(level=L, build=bname, talents=tal, gear=gear, race=race, opts=opts or {}))
    i = 0
    for L in (10, 14, 20, 26, 30, 34, 40, 46, 50, 56, 60):
        for bname, order in ORDERS.items():
            for gear in (1, 2):
                add(L, bname, build(order, L - 9), gear, RACES[i % 7])
                i += 1
        add(L, 'empty', {}, 1, RACES[i % 7])
        i += 1
    for L in (1, 3, 5, 8):                               # below the first talent point, below conjured water
        add(L, 'empty', {}, 1, 'none')
    for L in (20, 40, 60):
        for race in RACES:
            add(L, 'planner', build(ORDERS['planner'], L - 9), 1, race)
    for L in (20, 34, 48, 60):
        for bname in ('frost', 'fire', 'arcane'):
            for opts in OPTION_CASES:
                add(L, bname, build(ORDERS[bname], L - 9), 1, 'none', opts)
        for race, opts in RACE_OPTIONS:
            add(L, 'planner', build(ORDERS['planner'], L - 9), 1, race, opts)
    for L in (18, 19, 20, 21):                           # lower ranks are searched at 19 and below by default
        for bname in ORDERS:
            for opts in ({}, dict(low_ranks='full')):
                add(L, bname, build(ORDERS[bname], L - 9), 1, 'none', opts)
    for L, bname, tal in RANGE_BUILDS:
        for gear in (1, 2):
            add(L, bname, tal, gear, 'none')
    for L in range(10, 61):                              # the page planner, every level
        add(L, 'planner', build(ORDERS['planner'], L - 9), 1, 'none')
    return out


def main():
    slows, slow_bad = slow_cases()
    bad = check_tables() + check_talents() + check_tv_calls() + slow_bad
    if bad:
        for b in bad:
            print('DATA MISMATCH', b)
        sys.exit(1)
    print('data check: every spell row and talent value matches data/; every tv() names a talent; the chill slow '
          'follows Permafrost at 0 to %d ranks' % (len(slows) - 1))
    with open(os.path.join(ROOT, 'tests', 'leveling_slow_fixtures.json'), 'w', newline='\r\n') as f:
        json.dump(slows, f, indent=0)
    cs = cases()
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        res = pool.map(job, cs, chunksize=2)
    bad = [(c['level'], c['build'], c['race']) for c in res if c['build'] == 'planner' and not c['opts']
           and not c['feasible']]
    if bad:
        print('INFEASIBLE planner builds at default options:', bad)
        sys.exit(1)
    with open(os.path.join(ROOT, 'tests', 'leveling_fixtures.json'), 'w', newline='\r\n') as f:
        json.dump(res, f, indent=0)
    print(len(res), 'cases written;', sum(1 for c in res if not c['feasible']), 'infeasible (an option case where no '
          'rotation survives); every planner build at default options is feasible')


if __name__ == '__main__':
    main()
