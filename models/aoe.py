"""AoE leveling model for the Forever Mage: does pulling several mobs beat killing them one at a time, and from which
pull size, level band by level band. This module: spell data, builds, loop variants and the pull mechanics (spells,
the pack, damage, freezes, chills, movement, attacks). models/aoe_loops.py: the loops, the pull driver and the scoring
(run_pull, best_pull, baseline, breakeven), served from here as aoe.run_pull and so on. docs/aoe-model.md: the method.

One pull of n identical mobs is a deterministic expected-value simulation in 0.1 s steps, in one dimension (distance
from the Mage). The pack is a list of cohorts: shares of the pack that share a position, health, freeze and chill.
A freeze that damage may break, or a chill that lands on part of a cohort, splits it. Single-target spells hit one
whole mob's weight. Hit, crit, break, Frostbite and Fingers of Frost enter as expected values, as in the single-target
model (models/leveling_sim.py), whose spell constants and rest model this imports, not copies. Every AoE-only number
is an item of the gap register (forever-warlock-lab-drafts/mage-research/gap/aoe_assumptions.json), cited as
'reg <id>'; ASSUMPTION marks a value no source gives.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'analysis'))

import leveling_sim as ls                                               # noqa: E402
from character import BY_KEY                                           # noqa: E402
from leveling_paths import PLANNER, build                              # noqa: E402

# ---------------------------------------------------------------- spell data read from data/mage_spells.json
_SPELLS = json.load(open(os.path.join(HERE, '..', 'data', 'mage_spells.json'), encoding='utf-8'))['records']


def _v(x):
    return x['value'] if isinstance(x, dict) else x


def _recs(name):
    return sorted((r for r in _SPELLS if r['spell'] == name), key=lambda r: r['rank'])


def _rows_blizzard():
    """[spell level, tick average at learn, per level, max level, coefficient a tick, mana, ticks, period s]"""
    out = []
    for r in _recs('Blizzard'):
        d = r['damage']
        out.append([_v(r['spell_level']), _v(d['base_avg_at_learn']), _v(d['per_level']), _v(r['max_level']),
                    _v(d['sp_coefficient']), _v(r['mana_cost']), _v(d['ticks']), _v(d['period_ms']) / 1000.0])
    return out


def _rows_flamestrike():
    """[spell level, average at learn, per level, max level, coefficient, mana, cast s, burn tick average, burn
    coefficient a tick, burn ticks, burn period s]"""
    out = []
    for r in _recs('Flamestrike'):
        d, b = r['damage'], r['dot']
        out.append([_v(r['spell_level']), _v(d['base_avg_at_learn']), _v(d['per_level']), _v(r['max_level']),
                    _v(d['sp_coefficient']), _v(r['mana_cost']), _v(r['cast_ms']) / 1000.0, _v(b['base_avg_at_learn']),
                    _v(b['sp_coefficient']), _v(b['ticks']), _v(b['period_ms']) / 1000.0])
    return out


BLIZZARD = _rows_blizzard()
FLAMESTRIKE = _rows_flamestrike()
MANA_SHIELD = [[_v(r['level_learned']), _v(r['absorb_physical']), _v(r['mana_cost'])] for r in _recs('Mana Shield')]
_BLINK = _recs('Blink')[0]
BLINK = dict(level=_v(_BLINK['level_learned']), base_share=_v(_BLINK['mana_cost_pct_base']) / 100.0,
             cd=_v(_BLINK['cooldown_ms']) / 1000.0, yd=_v(_BLINK['distance_yd']))   # 20 yd, 15 s, 35% of base mana
MS_MANA_PER_POINT = 2.0     # Mana Shield drains 2 mana a point absorbed (data/mage_spells.json note, amplitude 2)
BZ_RADIUS = _v(_recs('Blizzard')[0]['radius_yd'])          # 8 yd, reg blizzardRadius
FS_RADIUS = _v(_recs('Flamestrike')[0]['radius_yd'])       # 5 yd, reg flamestrikeArea
AE_RADIUS = _v(_recs('Arcane Explosion')[0]['radius_yd'])  # 10 yd, reg arcaneExplosionRadius
NOVA_RADIUS = _v(_recs('Frost Nova')[0]['radius_yd'])      # 10 yd, reg frostNovaRadius
COC_RADIUS = _v(_recs('Cone of Cold')[0]['radius_yd'])     # 10 yd, reg coneOfColdShape
ARCTIC = BY_KEY['ArcticReach']['perRank']                  # +10/20% Blizzard range, Nova and Cone radius
IMP_BLIZZARD = BY_KEY['ImprovedBlizzard']['perRank']['blizzardChillSlowPct']   # 15/25/40, reg improvedBlizzardSlow
IMP_FLAMESTRIKE = BY_KEY['ImprovedFlamestrike']['perRank']['critPct']          # 5/10/15
IB_CD = BY_KEY['IceBarrier']['perRank']['cooldownSec']                         # 30 s
BW_DAZE = (BY_KEY['BlastWave']['perRank']['dazeSlowPct'] / 100.0, BY_KEY['BlastWave']['perRank']['dazeSec'])
IL_FROZEN = 1 + BY_KEY['IceLance']['perRank']['frozenDamageBonusPct'] / 100.0   # x4 on a frozen target
FROST = frozenset(('Frostbolt', 'IceLance', 'FrostNova', 'ConeOfCold', 'Blizzard'))   # Winter's Chill applies

# ---------------------------------------------------------------- AoE geometry and timing (gap register)
BZ_RANGE = 30.0             # reg blizzardRange base 30 yd (+10% a rank of Arctic Reach)
FS_RANGE = 30.0             # reg flamestrikeArea range 30 yd
BW_RADIUS = 10.0            # reg blastWaveRadius
BZ_CHILL_S = 1.5            # reg chillDurationBlizzard base 1.5 s (client 12484), times 1 + Permafrost duration
ROW30 = 0.30                # reg improvedBlizzardSlow caveat: the Chilled row's own -30%
NOVA_ROOT_S = 8.0           # reg frostNovaRoot 8 s at every rank
FB_ROOT_S = 5.0             # reg frostbiteFreeze rootSec 5
ARMOR_MOVE, ARMOR_S = 0.30, 5.0   # reg armorChill: 30% movement slow for 5 s on melee attackers (Frost or Ice Armor)
DAZE_SLOW, DAZE_S = 0.5, 4.0      # reg creatureDaze: 50% for 4 s
POTION_CD = 120.0           # potions and gems: one each per 2 min (leveling_sim rest model)

# ---------------------------------------------------------------- simulation constants
DT = 0.1
MAX_T = 240.0               # a pull not over in 240 s stalls (the single-target model's MAX_TIME)
GAP0 = 2.0                  # ASSUMPTION: a gathered pack starts stacked right behind the Mage
MIN_GAP = 2.0               # ASSUMPTION: a chasing mob closes to 2 yd
LEAD = 0.9                  # ASSUMPTION: Blizzard is aimed with the rear mob just inside the far edge of the storm
OUTRUN = 0.85               # a pack is outrun when it moves under 85% of the Mage's speed for the next second
ETA_MIN = 4.0               # a Blizzard is not started on a pack due in melee within 4 s while Nova will be ready
END_W = 0.05                # a pull ends when under 0.05 mobs (expected value) are left; they are finished by Frostbolt
NEAR = ls.MELEE_GAP         # Frost Nova when a free mob is this far past melee reach (the single-target model's rule)

AOE_DEFAULTS = dict(
    cap=0,              # reg aoeTargetCap: 0 = no cap (client), sensitivity 5 and 4 (m1)
    bz_slow=None,       # reg blizzardChillTotal: None = Improved Blizzard + Permafrost ranks; else a fraction
    bz_row30=False,     # reg improvedBlizzardSlow caveat: the Chilled row's own 30% replaces the talent value (m3)
    bz_chill_s=None,    # reg chillDurationBlizzard: None = 1.5 s x (1 + Permafrost duration); else seconds (m3)
    bz_refresh=True,    # reg chillRefreshInStorm: every tick re-applies the chill (m3)
    bz_crit=False,      # reg blizzardTickCrit: Blizzard and Flamestrike ticks crit (m9)
    bz_first=1.0,       # reg blizzardTicks firstTickSec (m9)
    bz_pushback='tick',  # reg channelPushback: 'tick' (a hit costs one tick), 'none', 'end' (the first hit ends it)
    fb_rolls='every',   # reg frostbiteFreeze rollsOn: 'every' Blizzard tick, or 'first' tick of a cast (m17)
    hp_scale=1.0,       # reg mobHealth multiple (x0.8 to x1.2, m16), applied to the AoE pulls and the baseline alike
    gather0=8.0,        # reg gatherTime: 8 + 6 (n - 1) s; the first 8 s is the walk, as the single-target model's
    gather_per=6.0, find_per=3.0,   # a gathered pack; find_per: a group pulled from range, nothing gathered (gather())
    reach=5.0,          # reg meleeRange (ASSUMPTION there too)
    cone_share=0.75,    # ASSUMPTION: share of the mobs in Cone of Cold's radius its 60 degree cone catches
    flee=0.0,           # reg humanoidFlee: share of the pack that runs; ASSUMPTION 0 = beasts, per WFB's advice
    flee_at=0.15,       # reg humanoidFlee healthPct 15
    daze=0.2,           # reg creatureDaze chanceEqualLevel, per hit from behind while the Mage runs
    safety=0.25,        # ASSUMPTION: lowest expected health allowed during a pull, share of max health
    aoe_armor='frost',  # the AoE Mage wears Frost or Ice Armor (AOE.md loop step 1); 'auto' = Mage Armor from 34
    ice_barrier=True,   # cast before the pull and again when it breaks, if talented (from 40)
    mana_shield=True,   # cast when health is under half and a mob is in melee (from 20)
    cd_carry=False,     # False: Nova and Ice Barrier ready at every pull, as in the single-target model (its fights
                        # all start with every cooldown ready); True: they carry over between pulls (per_kill)
)
AOE_KEYS = frozenset(AOE_DEFAULTS)


def opts(o=None):
    """AoE options with defaults filled in; keys that are not AoE options go to make_char and evaluate."""
    out = dict(AOE_DEFAULTS)
    out.update(o or {})
    return out


def char_opts(o):
    return {k: v for k, v in (o or {}).items() if k not in AOE_KEYS}


def gather(n, o, arch=None):    # find_per ASSUMPTION 3 s: groups standing together are rarer than singles, half of 6
    return o['gather0'] + (o['find_per'] if ARCH_START.get(arch) == 'range' else o['gather_per']) * (n - 1)


# ---------------------------------------------------------------- builds (orders checked legal after every point)
def _rep(*p):
    out = []
    for k, n in p:
        out += [k] * n
    return out


# ASSUMPTION: the model's AoE orders, not searched. Frost: AoE talents as early as the point rules allow after Improved
# Frostbolt (Improved Blizzard 20 to 22, reg talentLevels), then mana, reach, Nova, Shatter, Ice Barrier at 40. Fire:
# Improved Flamestrike at 20, Burning Soul, Blast Wave at 30. Unread talents only open rows. Cold Snap (Ice Barrier's
# prerequisite) and Ice Block are never cast: their 10 and 5 min cooldowns cover one pull in several.
FROST_AOE = _rep(('ImprovedFrostbolt', 5), ('Permafrost', 3), ('Frostbite', 2), ('ImprovedBlizzard', 3),
                 ('Frostbite', 1), ('FrostChanneling', 3), ('ArcticReach', 2), ('ImprovedFrostNova', 2), ('Shatter', 3),
                 ('PiercingIce', 3), ('ColdSnap', 1), ('ImprovedConeOfCold', 2), ('IceBarrier', 1),
                 ('ImprovedConeOfCold', 1), ('ElementalPrecision', 3), ('IceShards', 5), ('ElementalPrecision', 2),
                 ('ArcaneFocus', 5), ('ArcaneSubtlety', 2), ('MagicAbsorption', 2))
FIRE_AOE = _rep(('Incineration', 3), ('WakeOfFire', 2), ('Ignite', 5), ('ImprovedFlamestrike', 3), ('BurningSoul', 3),
                ('Pyroblast', 1), ('MasterOfElements', 3), ('BlastWave', 1), ('CriticalMass', 3),
                ('ImprovedFireball', 1), ('FirePower', 5), ('Combustion', 1), ('ElementalPrecision', 5),
                ('ImprovedFrostNova', 2), ('Permafrost', 3), ('ArcaneFocus', 5), ('ArcaneSubtlety', 2),
                ('MagicAbsorption', 2), ('ArcaneResilience', 1))
ARCHES = ('nb', 'blizzard', 'ae', 'fs', 'cone')
ARCH_NAME = {'nb': 'Small pulls: Frost Nova, step out, Frostbolt one mob at a time (planner build)',
             'blizzard': 'Frost AoE loop (Nova, Blizzard, Cone, Arcane Explosion)',
             'ae': 'Arcane Explosion in melee after Frost Nova',
             'fs': 'Flamestrike with Arcane Explosion (Fire build)',
             'cone': 'Cone of Cold kiting with Frostbolt (small groups)'}
ARCH_FROM = {'nb': 10, 'blizzard': 20, 'ae': 14, 'fs': 16, 'cone': 26}   # Nova 10, Blizzard 20, AE 14, FS 16, Cone 26
# How a pull starts. 'stacked': a gathered pack right behind the Mage (GAP0). 'range': the group stands unaware at the
# single-target model's pull range (melee reach + pull_gap + Arctic Reach) until the first spell lands, as there.
ARCH_START = {'nb': 'range', 'cone': 'range', 'blizzard': 'stacked', 'ae': 'stacked', 'fs': 'stacked'}
# The damage spells a loop lives on: the Mage has run dry when mana plus an unused potion and gem cannot pay the
# cheapest of them.
ARCH_MAIN = {'nb': ('Frostbolt',), 'blizzard': ('Blizzard', 'ArcaneExplosion'), 'ae': ('ArcaneExplosion',),
             'fs': ('Flamestrike', 'ArcaneExplosion'), 'cone': ('ConeOfCold', 'Frostbolt')}
POLICIES = {        # loop variants; best_pull keeps the best surviving one, each with and without fight potions
    'nb': [dict(gap=12.0, cone=True, melee=True), dict(gap=18.0, cone=True, melee=True),
           dict(gap=18.0, cone=False, melee=False, ib=False), dict(gap=12.0, cone=True, melee=True, ib=False),
           dict(gap=18.0, cone=False, melee=False, ib=False, fin='Wand'),
           dict(gap=12.0, cone=True, melee=True, ib=False, fin='Wand')],
    'blizzard': [dict(step=s, kite=k, wait=w, finish=2.0) for s, k, w in ((21.0, True, True), (21.0, False, False),
                 ('max', True, True), (21.0, True, False), ('short', True, True), ('short', False, False))],
    'ae': [dict(gap=7.5), dict(gap=0.0)],
    'fs': [dict(gap=12.0, melee=False), dict(gap=20.0, melee=False), dict(gap=12.0, melee=True)],
    'cone': [dict(gap=9.0, finish=2.0), dict(gap=9.0, finish=0.0)],
}


def aoe_talents(arch, L):
    """The build a loop runs: the planner build for small pulls (no respec), else the Fire or Frost AoE order."""
    if arch == 'nb':
        return build(PLANNER, max(0, L - 9))
    return build(FIRE_AOE if arch == 'fs' else FROST_AOE, max(0, L - 9))


# ---------------------------------------------------------------- spell constants for one character
def _row(table, L):
    rows = [r for r in table if r[0] <= L]
    return rows[-1] if rows else None


def _coef(row, ch):
    """Share of a rank's stored coefficient it keeps: the single-target model's rule (option low_ranks, test m13)."""
    return ls.coef_factor(row, ch.level, 'classic' if ch.below20 else ch.low_ranks)


def _scaled(row, L, ch, avg, coef):
    return ls.dd_avg([row[0], avg, row[2], row[3]], L, ch.dd_mode) + coef * _coef(row, ch) * ch.sp


def spell_consts(ch, o):
    """Per-hit values for every spell the loops cast: x (average hit before hit and crit), hit, crit, cm (crit
    multiplier), can_crit, fire, cost, plus cooldowns, radii and slows. Frost Nova, Cone of Cold, Arcane Explosion,
    Frostbolt and Blast Wave come from leveling_sim.fight_consts, so they match the single-target model exactly."""
    L, T = ch.level, ch.talents
    k = ls.fight_consts(ch, {'prio': []})
    sp = {}
    for n in ('FrostNova', 'ConeOfCold', 'ArcaneExplosion', 'Frostbolt', 'BlastWave', 'IceLance'):
        if k['row'][n]:
            sp[n] = dict(x=(k['avg'][n] + k['coef'][n] * ch.sp) * k['smult'][n], hit=k['hit'][n], crit=k['crit'][n],
                         cm=k['cm'][n], can_crit=True, fire=n == 'BlastWave', cost=k['cost'][n], ct=k['ct'][n],
                         fm=IL_FROZEN if n == 'IceLance' else 1.0)
    ai = ls.tv(ch, 'ArcaneInstability')
    hit = min(0.99, ch.hit_base + ls.tv(ch, 'ElementalPrecision'))
    base_crit = ch.crit + ch.crit_bonus + ai
    bz = _row(BLIZZARD, L)
    if bz:
        sp['Blizzard'] = dict(x=_scaled(bz, L, ch, bz[1], bz[4]) * (1 + ai + ls.tv(ch, 'PiercingIce')) * ch.dmg_mult,
                              hit=hit, crit=base_crit, cm=1 + 0.5 * (1 + ls.tv(ch, 'IceShards')), can_crit=o['bz_crit'],
                              fire=False, cost=bz[5] * (1 - ls.tv(ch, 'FrostChanneling')), ticks=bz[6], period=bz[7])
    fs = _row(FLAMESTRIKE, L)
    if fs:
        mult = (1 + ai + ls.tv(ch, 'FirePower')) * ch.dmg_mult
        ifs = IMP_FLAMESTRIKE[T['ImprovedFlamestrike'] - 1] / 100.0 if T.get('ImprovedFlamestrike') else 0.0
        fcrit = base_crit + ls.tv(ch, 'CriticalMass')
        sp['Flamestrike'] = dict(x=_scaled(fs, L, ch, fs[1], fs[4]) * mult, hit=hit, crit=fcrit + ifs, cm=1.5,
                                 can_crit=True, fire=True, cost=fs[5], ct=fs[6] / ch.haste)
        sp['Burn'] = dict(x=(fs[7] + fs[8] * _coef(fs, ch) * ch.sp) * mult, hit=hit, crit=fcrit, cm=1.5,
                          can_crit=o['bz_crit'], fire=True, cost=0.0, ticks=fs[9], period=fs[10])
    ms = _row(MANA_SHIELD, L)
    pf_s, pf_slow = ls.tv(ch, 'Permafrost'), ls.tv(ch, 'Permafrost', 'PermafrostSlow')   # +11/22/33% length, +3/7/10%
    ib_rank = T.get('ImprovedBlizzard', 0)
    if o['bz_slow'] is not None:
        bz_slow = o['bz_slow']
    elif ib_rank:
        bz_slow = (ROW30 if o['bz_row30'] else IMP_BLIZZARD[ib_rank - 1] / 100.0) + pf_slow
    else:
        bz_slow = 0.0           # without Improved Blizzard, Blizzard does not chill (Classic; reg improvedBlizzardSlow)
    ar = T.get('ArcticReach', 0)
    reach_pct = ARCTIC['radiusPct_FrostNovaConeOfCold'][ar - 1] / 100.0 if ar else 0.0
    range_pct = ARCTIC['rangePct_FrostboltBlizzard'][ar - 1] / 100.0 if ar else 0.0
    return dict(sp=sp, shatter=k['shatter'], fb=k['fb_chance'], ignite=k['ignite'], prot=k['prot'],
                fof_n=k['fof_n'], wc_chance=k['wc_chance'], wc_cap=k['wc_cap'], fb_reach=k['reach']['Frostbolt'],
                wand=ch.wand_dps * k['wandspec'] * ch.dmg_mult * min(0.99, ch.hit_base),   # expected wand dps
                fb_break=ch.fb_break,     # Frostbite's freeze breaks like Nova's unless fb_break is set (make_char)
                blink=BLINK['base_share'] * ch.base_mana if L >= BLINK['level'] else None,
                cd=dict(k['cd'], IceBarrier=float(IB_CD), Blink=BLINK['cd']), ib=k['ib'], ib_cost=k['ib_cost'],
                ms=ms, bz_slow=bz_slow, bz_chill=o['bz_chill_s'] if o['bz_chill_s'] is not None else BZ_CHILL_S * (1 + pf_s),
                coc_slow=k['slow'], coc_s=k['chill_s']['ConeOfCold'], fbolt_slow=k['slow'], fbolt_s=k['chill_s']['Frostbolt'],
                armor_slow=ARMOR_MOVE + pf_slow, nova_r=NOVA_RADIUS * (1 + reach_pct),
                coc_r=COC_RADIUS * (1 + reach_pct), bz_range=BZ_RANGE * (1 + range_pct))


# ---------------------------------------------------------------- the pack
class Mob:
    """A cohort: w mobs sharing a position x (world, yd; the Mage starts at 0 and runs toward minus), health per mob,
    a freeze until `hold` that each damage event breaks with chance `brk`, the strongest chill (slow `cs` until `cu`)
    and the longest weaker one behind it (`cs2` until `cu2`), the armor
    chill's attack slow until `au`, a swing accumulator, whether it has passed the flee check, and `focus`: the id of
    the single-target spell in flight whose target mob this cohort is part of (0: none)."""
    __slots__ = ('w', 'x', 'hp', 'hold', 'brk', 'cu', 'cs', 'cu2', 'cs2', 'acc', 'au', 'fc', 'focus')

    def __init__(self, w, x, hp):
        self.w, self.x, self.hp = w, x, hp
        self.hold, self.brk, self.cu, self.cs, self.cu2, self.cs2 = -1.0, 0.0, -1.0, 0.0, -1.0, 0.0
        self.acc, self.au, self.fc, self.focus = 0.0, -1.0, False, 0

    def split(self, frac, P):
        """Move a share frac of this cohort into a new cohort with the same state (added to the pack); return it.
        Both parts keep the focus id: a share of the target mob is still the target."""
        if frac >= 1.0 - 1e-12:
            return self
        new = Mob.__new__(Mob)
        for s in Mob.__slots__:
            setattr(new, s, getattr(self, s))
        new.w = self.w * frac
        self.w -= new.w
        P.mobs.append(new)
        return new


class Pull:
    """The state of one pull."""

    def __init__(self, ch, K, n, H0, arch, pol, o, phase=0.5):
        self.ch, self.K, self.n, self.H0, self.arch, self.pol, self.o = ch, K, n, H0, arch, pol, o
        self.t, self.m, self.t_ev = 0.0, 0.0, 0.0     # t_ev: expected fight time so far (live())
        self.reach = o['reach']
        if ARCH_START.get(arch, 'stacked') == 'range':      # unaware at pull range until the first spell lands
            self.mobs, self.engaged = [Mob(float(n), self.reach + ch.pull_gap + K['fb_reach'], H0)], False
        else:
            self.mobs, self.engaged = [Mob(float(n), GAP0, H0)], True
        self.hp, self.mana, self.ib, self.ms = ch.max_hp, ch.max_mana, 0.0, 0.0
        self.gcd, self.walk, self.last_spend = 0.0, False, -99.0
        self.cd = dict(FrostNova=0.0, ConeOfCold=0.0, BlastWave=0.0, IceBarrier=0.0, Blink=0.0)
        self.chan = self.cast = self.burn = None
        self.daze_p, self.daze_u = 0.0, -1.0
        self.pot = self.gem = False
        self.dealt, self.taken, self.hits, self.spent, self.min_hp = 0.0, 0.0, 0.0, 0.0, ch.max_hp
        self.nova_first = self.ib_first = None          # first use: the next pull needs the cooldown back by then
        self.nova_last = self.ib_last = -1e9
        self.dry_t = self.low_t = None                  # first time out of mana, first time under the safety floor
        self.dry_hp = self.dry_left = None              # her health share and the pack's health share then
        self.bz_hit = self.bz_pack = 0.0                # Blizzard: mob-ticks landed, mobs alive at each cast
        # Frostbite's accumulator and Fingers of Frost's charges start at `phase`, the remainder carried from earlier
        # pulls, as in the single-target model (run_pull spreads it over the health multiples)
        self.fbacc = phase if K['fb'] else 0.0
        self.fof, self.wc, self.wc_n, self.fid = phase if K['fof_n'] else 0.0, 0.0, n, 0   # Winter's Chill; spell ids
        self.casts, self.dealt_at, self.runners = {}, [], []
        if o['ice_barrier'] and pol.get('ib', True) and K['ib']:   # cast at the start of the gather (ASSUMPTION)
            g = gather(n, o, arch) - o['gather0']
            self.ib, self.mana, self.spent = K['ib'], ch.max_mana - K['ib_cost'], K['ib_cost']
            self.ib_first = self.ib_last = -g
            self.cd['IceBarrier'] = max(0.0, K['cd']['IceBarrier'] - g)


# ---------------------------------------------------------------- damage, freezes and chills
def cap_share(P, mobs):
    tot = sum(c.w for c in mobs)
    cap = P.o['cap']
    return tot, (cap / tot if cap and tot > cap else 1.0)


def in_area(P, cx, r):
    return [c for c in P.mobs if abs(c.x - cx) <= r + 1e-9]


def within(P, r):
    return [c for c in P.mobs if c.x - P.m <= r + 1e-9]


def weight(mobs):
    return sum(c.w for c in mobs)


def strike(P, name, mobs, extra=1.0, chill=None, root=False, fb=True, as_frozen=False):
    """One damage event of spell `name` on the cohorts `mobs` (all inside its area). chill = (slow, seconds) lands at
    full strength on the share of each cohort the spell hits (the cohort splits, as freezes do) and rolls Frostbite
    and Fingers of Frost unless fb is False; root = Frost Nova's freeze. A frozen cohort hit by damage breaks free with
    chance share x brk. as_frozen: a Fingers of Frost charge makes the target count as frozen (Shatter, Ice Lance)."""
    K, t, sp = P.K, P.t, P.K['sp'][name]
    tot, cs = cap_share(P, mobs)
    if tot <= 0:
        return
    P.engaged = True
    share = sp['hit'] * extra * cs
    wc = ls.WC_CRIT * P.wc if name in ('Frostbolt', 'IceLance') else 0.0
    touched = []
    for c in list(mobs):
        frozen = c.hold > t
        icy = frozen or as_frozen
        cr = min(1.0, sp['crit'] + wc + (K['shatter'] if icy else 0.0)) if sp['can_crit'] else 0.0
        dmg = sp['x'] * share * (sp.get('fm', 1.0) if icy else 1.0) * (1 + cr * (sp['cm'] - 1))
        if sp['fire'] and K['ignite']:          # Ignite: 40% of a crit over 4 s, entered at once (EV)
            dmg += K['ignite'] * sp['x'] * share * sp['cm'] * cr
        P.dealt += min(dmg, max(0.0, c.hp)) * c.w
        c.hp -= dmg
        touched.append(c)
        if root:
            part = c.split(share, P)
            part.hold, part.brk = t + NOVA_ROOT_S, P.ch.nova_break
        elif frozen and c.brk > 0:
            freed = c.split(share * c.brk, P)
            freed.hold, freed.brk = -1.0, 0.0
            if freed is not c:
                touched.append(freed)
    if name in FROST and K['wc_cap']:           # Winter's Chill stacks on the target (one mob, see reap)
        P.wc = min(K['wc_cap'], P.wc + share * K['wc_chance'])
    if chill:
        parts = [c.split(share, P) for c in touched]
        for c in parts:
            chill_on(P, c, chill[0], chill[1], frostbite=fb)
        if fb:
            frostbite(P, parts, whole=name == 'Frostbolt')


def chill_on(P, c, slow, dur, frostbite=True):
    """A chill (slow for dur seconds) on a whole cohort; strongest slow wins (reg slowStacking). Adds Fingers of
    Frost charges (for the next single-target spell) unless frostbite is False; Frostbite itself is frostbite()."""
    t, K = P.t, P.K
    live = sorted((e for e in ((c.cs, c.cu), (c.cs2, c.cu2), (slow, t + dur)) if e[1] > t and e[0] > 0),
                  key=lambda e: (-e[0], -e[1]))    # strongest first; of equal slows, the longest
    c.cs, c.cu = live[0] if live else (0.0, -1.0)
    rest = [e for e in live[1:] if e[1] > c.cu]
    c.cs2, c.cu2 = rest[0] if rest else (0.0, -1.0)
    if frostbite and K['fof_n']:
        P.fof = min(K['fof_n'], P.fof + c.w * ls.FOF_CHANCE * K['fof_n'])


def frostbite(P, parts, whole=False):
    """Frostbite on the cohorts just chilled, freezing for FB_ROOT_S and breaking on damage with fb_break.
    whole (a single-target chill, Frostbolt: one mob): the single-target model's expected-value accumulator, so the
    mob freezes whole once it passes 1 (from its phase), as there. Otherwise (an area chill or the armor chill on a
    cohort): each cohort freezes the chance's share of its weight at once, the plain expected value; lumps on a pack
    would make the outcome hinge on which cohorts a lump lands on."""
    K, t = P.K, P.t
    w = weight(parts)
    if not K['fb'] or w <= 1e-12:
        return
    frac = K['fb']
    if whole:
        P.fbacc += K['fb'] * w
        k = int(P.fbacc + 1e-9)
        if k < 1:
            return
        P.fbacc -= k
        frac = min(1.0, k / w)
    for c in parts:
        if c.w <= 1e-12:
            continue
        fz = c.split(frac, P)
        if t + FB_ROOT_S > fz.hold:
            fz.hold, fz.brk = t + FB_ROOT_S, K['fb_break']


def slow_at(c, t):
    """A cohort's movement slow at time t: its strongest chill, then the weaker one behind it."""
    return c.cs if c.cu > t else (c.cs2 if c.cu2 > t else 0.0)


def reap(P):
    """Remove dead cohorts; split off runners (reg humanoidFlee) at 15% health. They and an expected-value tail of
    under END_W mobs are finished after the pull with Frostbolt (result())."""
    o = P.o
    for c in list(P.mobs):
        if o['flee'] and c.hp > 0 and not c.fc and c.hp < o['flee_at'] * P.H0:
            c.fc = True
            r = c.split(o['flee'], P)
            P.runners.append((r.w, r.hp))
            r.w = 0.0
    P.mobs = [c for c in P.mobs if c.w > 1e-9 and c.hp > 0]
    while P.wc_n > 1 and weight(P.mobs) < P.wc_n - 0.5:     # a mob died: its Winter's Chill stacks go with it
        P.wc_n -= 1
        P.wc = 0.0
    if P.mobs and weight(P.mobs) < END_W:
        P.runners += [(c.w, c.hp) for c in P.mobs]
        P.mobs = []


def _fold(g, c):
    """Merge cohort c into g (weighted means of the state)."""
    w = g.w + c.w
    for s in ('x', 'hp', 'cs', 'cu', 'cs2', 'cu2', 'acc', 'au', 'hold'):
        setattr(g, s, (getattr(g, s) * g.w + getattr(c, s) * c.w) / w)
    g.w = w


MAX_COHORTS = 32


def merge(P):
    """Merge cohorts in the same state (1 yd, 0.5 s freeze end, 4% health, 0.1 slow, 1 s chill end bins); past
    MAX_COHORTS, fold the lightest cohort into the nearest one with the same frozen or free status."""
    t, groups, out = P.t, {}, []
    for c in P.mobs:
        if c.focus:
            out.append(c)
            continue
        held = c.hold > t
        key = (round(c.hold * 2) if held else -1, round(c.brk * 100) if held else 0, round(c.x),
               round(c.hp * 25 / P.H0), c.fc, round(slow_at(c, t) * 10), round(max(c.cu, c.cu2, t) - t))
        g = groups.get(key)
        if g is None:
            groups[key] = c
            out.append(c)
        else:
            _fold(g, c)
    while len(out) > MAX_COHORTS:
        out.sort(key=lambda c: c.w)
        for s in (c for c in out if not c.focus):
            pool = [c for c in out if c is not s and not c.focus and (c.hold > t) == (s.hold > t)]
            if pool:
                _fold(min(pool, key=lambda c: abs(c.x - s.x) + 10 * abs(c.hp - s.hp) / P.H0), s)
                out.remove(s)
                break
        else:
            break
    P.mobs = out


# ---------------------------------------------------------------- spells
def ready(P, name):
    """Cooldown and global cooldown over, and the mana there (a potion or gem may still cover it)."""
    if name not in P.K['sp'] and name not in ('IceBarrier', 'ManaShield', 'Blink'):
        return False
    if name == 'Blink' and P.K['blink'] is None:
        return False
    if P.t < P.gcd - 1e-9 or P.t < P.cd.get(name, 0.0) - 1e-9:
        return False
    return P.mana + spare(P) >= cost(P, name)


def cost(P, name):
    if name == 'IceBarrier':
        return P.K['ib_cost']
    if name == 'ManaShield':
        return P.K['ms'][2] if P.K['ms'] else 1e9
    if name == 'Blink':
        return P.K['blink']
    return P.K['sp'][name]['cost']


def spare(P):
    """Mana a potion and a gem not yet used this pull would give (consumables count, Omri's rule). A loop variant
    with pol pots False keeps them for the rest, as the single-target model does (best_pull scores both)."""
    L, ch = P.ch.level, P.ch
    if not P.pol.get('pots', True):
        return 0.0
    pot = [p for p in ls.POTIONS if p[0] <= L] if ch.potions and not P.pot else []
    gem = [g for g in ls.GEMS if g[0] <= L] if ch.gems and not P.gem else []
    return (pot[-1][1] if pot else 0.0) + (gem[-1][2] if gem else 0.0)


def pay(P, c):
    """Spend c mana, drinking a potion and then using a gem first when the pool is short (if pol pots allows)."""
    L, ch = P.ch.level, P.ch
    fight = P.pol.get('pots', True)
    if fight and P.mana < c and ch.potions and not P.pot:
        pot = [p for p in ls.POTIONS if p[0] <= L]
        if pot:
            P.pot, P.mana = True, min(ch.max_mana, P.mana + pot[-1][1])
    if fight and P.mana < c and ch.gems and not P.gem:
        gem = [g for g in ls.GEMS if g[0] <= L]
        if gem:
            P.gem, P.mana = True, min(ch.max_mana, P.mana + gem[-1][2])
    P.mana -= c
    P.spent += c
    if c > 0:
        P.last_spend = P.t


def live(P):
    """Chance the pull is still on: min(1, mobs alive in expectation). Once under one mob is left, the pull is over in
    the rest of the expected outcomes, so a cast then is paid and counted only in that share, and the fight clock runs
    at that rate (P.t_ev). Exact for one mob; for a pack it is an upper bound on the chance some mob is alive, so it
    never flatters AoE."""
    return min(1.0, weight(P.mobs))


def cast(P, name):
    """Start or land a spell chosen by the loop."""
    K, t = P.K, P.t
    share = live(P)
    pay(P, cost(P, name) * share)
    P.casts[name] = P.casts.get(name, 0) + share
    P.gcd = t + ls.GCD
    if name in P.cd:
        P.cd[name] = t + K['cd'][name]
    if name == 'IceBarrier':
        P.ib, P.ib_last = K['ib'], t
        P.ib_first = t if P.ib_first is None else P.ib_first
    elif name == 'ManaShield':
        P.ms = K['ms'][1]
    elif name == 'Blink':
        P.m -= BLINK['yd']
    elif name == 'FrostNova':
        P.nova_last = t
        P.nova_first = t if P.nova_first is None else P.nova_first
        strike(P, name, within(P, K['nova_r']), root=True)
    elif name == 'ConeOfCold':
        strike(P, name, within(P, K['coc_r']), extra=P.o['cone_share'], chill=(K['coc_slow'], K['coc_s']))
    elif name == 'ArcaneExplosion':
        strike(P, name, within(P, AE_RADIUS))
    elif name == 'BlastWave':
        strike(P, name, within(P, BW_RADIUS), chill=BW_DAZE, fb=False)     # a daze, not a chill
    elif name == 'Blizzard':
        s = K['sp']['Blizzard']
        P.bz_pack += weight(P.mobs) * share
        P.chan = dict(cx=aim_bz(P), next=t + P.o['bz_first'], left=s['ticks'], lost=0.0, n=0)
    elif name == 'Flamestrike':
        P.cast = dict(name=name, end=t + K['sp'][name]['ct'], cx=aim_fs(P))
    elif name == 'Frostbolt':
        P.fid += 1
        take_target(P, P.fid)
        P.cast = dict(name=name, end=t + K['sp'][name]['ct'], fid=P.fid)
    elif name == 'IceLance':                            # instant: lands now
        parts = take_target(P, 0)
        strike(P, name, parts, as_frozen=use_fof(P))


def pick_target(P):
    """One whole mob for a single-target spell, as [(cohort, weight taken)], the pack unchanged: up to 1.0 of
    weight, the most damaged cohorts first (focus fire), frozen before free at equal health, then the nearest. Expected
    values spread a mob over cohorts; a single-target spell still hits one mob's worth of them at full damage."""
    t, need, out = P.t, min(1.0, weight(P.mobs)), []
    for c in sorted(P.mobs, key=lambda c: (round(c.hp * 25 / P.H0), c.hold <= t, c.x)):
        if need <= 1e-9:
            break
        take = min(need, c.w)
        out.append((c, take))
        need -= take
    return out


def take_target(P, fid):
    """Split off the cohorts pick_target chose, tag them with the spell id fid, and return them."""
    parts = []
    for c, take in pick_target(P):
        part = c.split(take / c.w, P)
        part.focus = fid
        parts.append(part)
    return parts


def use_fof(P):
    """Spend a Fingers of Frost charge on this single-target spell, if there is one."""
    if P.fof >= 1.0:
        P.fof -= 1.0
        return True
    return False


def speed(P, c, dt):
    """How far a cohort moves toward the Mage in the next dt seconds at its current state (frozen: not at all)."""
    t = P.t
    free = max(0.0, t + dt - max(t, c.hold))
    return P.ch.mob_speed * (1 - slow_at(c, t)) * free


def aim_bz(P):
    """Blizzard's centre: the rear of the pack (90% of the weight) where it will be at the first tick, just inside
    the storm's far edge, within range. Pol step 'short' with half the pack frozen: on the pack, near edge outside
    melee reach."""
    dt = P.o['bz_first']
    ahead = [Mob.__new__(Mob) for _ in P.mobs]
    for a, c in zip(ahead, P.mobs):
        a.x, a.w = c.x - speed(P, c, dt), c.w
    short = P.pol.get('step') == 'short' and weight([c for c in P.mobs if c.hold > P.t]) >= 0.5 * weight(P.mobs)
    cx = P.m + edge(P, ahead, 0.9) - (0.0 if short else LEAD) * BZ_RADIUS
    return min(max(cx, P.m + P.reach + BZ_RADIUS) if short else cx, P.m + P.K['bz_range'])


def aim_fs(P):
    """Flamestrike goes on the heaviest group: the frozen cohorts if half the pack is frozen, else the nearest."""
    t = P.t
    held = [c for c in P.mobs if c.hold > t]
    pool = held if weight(held) >= 0.5 * weight(P.mobs) else P.mobs
    x = sum(c.x * c.w for c in pool) / weight(pool)
    return min(x, P.m + FS_RANGE)


def land(P):
    """A cast that finishes this step."""
    c = P.cast
    if not c or P.t < c['end'] - 1e-9:
        return
    P.cast = None
    K, t = P.K, P.t
    if c['name'] == 'Flamestrike':
        strike(P, 'Flamestrike', in_area(P, c['cx'], FS_RADIUS))
        b = K['sp']['Burn']
        P.burn = dict(cx=c['cx'], next=t + b['period'], left=b['ticks'])
    else:                                       # Frostbolt: every live part of its target mob
        parts = [m for m in P.mobs if m.focus == c['fid']]
        for m in parts:
            m.focus = 0
        parts = [m for m in parts if m.w > 1e-9 and m.hp > 0]
        if parts:
            strike(P, 'Frostbolt', parts, chill=(K['fbolt_slow'], K['fbolt_s']), as_frozen=use_fof(P))


def ticks(P):
    """Blizzard and Flamestrike ticks due this step."""
    t, o, K = P.t, P.o, P.K
    ch = P.chan
    if ch and t >= ch['next'] - 1e-9:
        mobs = in_area(P, ch['cx'], BZ_RADIUS)
        P.bz_hit += weight(mobs) * live(P)
        first = ch['n'] == 0
        chill = (K['bz_slow'], K['bz_chill']) if K['bz_slow'] > 0 and (o['bz_refresh'] or first) else None
        strike(P, 'Blizzard', mobs, chill=chill, fb=o['fb_rolls'] == 'every' or first)
        ch['n'] += 1
        ch['left'] -= 1
        ch['next'] += K['sp']['Blizzard']['period']
        if ch['left'] <= 0:
            P.chan = None
    b = P.burn
    if b and t >= b['next'] - 1e-9:
        strike(P, 'Burn', in_area(P, b['cx'], FS_RADIUS))
        b['left'] -= 1
        b['next'] += K['sp']['Burn']['period']
        if b['left'] <= 0:
            P.burn = None


# ---------------------------------------------------------------- mobs and the Mage
def move(P):
    """The Mage walks if the loop said so (dazed: slower); free mobs chase at their slowed speed."""
    t, ch = P.t, P.ch
    if P.walk:
        daze = P.daze_p * DAZE_SLOW if t < P.daze_u else 0.0
        P.m -= ch.player_speed * (1 - daze) * DT
    if not P.engaged:                   # an unaware group stands until the first spell lands
        return
    for c in P.mobs:
        if c.hold > t:
            continue
        c.x = max(P.m + MIN_GAP, c.x - ch.mob_speed * (1 - slow_at(c, t)) * DT)


def attacks(P):
    """Mobs within reach swing; Ice Barrier, then Mana Shield (2 mana a point), then health. Frost or Ice Armor
    chills each attacker (attack and movement slow, Frostbite roll). Hits cost Blizzard ticks or push a cast back
    unless Ice Barrier holds; hits on a running Mage may daze her."""
    t, ch, K = P.t, P.ch, P.K
    swings = 0.0
    for c in list(P.mobs):
        if c.x - P.m > P.reach + 1e-9:
            continue
        per = DT / ch.swing * (1 - ch.armor_slow if t < c.au else 1.0)
        swings += c.w * per
        if ch.armor_chill:
            c.acc += per
            if c.acc >= 1:
                c.acc -= 1
                c.au = t + ARMOR_S
                chill_on(P, c, K['armor_slow'], ARMOR_S, frostbite=ch.frostbite_armor)
                if ch.frostbite_armor:
                    frostbite(P, [c])
    if swings <= 0:
        return
    x = ch.mob_dps * ch.swing * swings
    shielded = P.ib > 0
    a = min(P.ib, x)
    P.ib -= a
    x -= a
    if x > 0 and P.ms > 0:
        a = min(P.ms, x, P.mana / MS_MANA_PER_POINT)
        P.ms -= a
        P.mana -= a * MS_MANA_PER_POINT
        x -= a
        if P.mana <= 0:
            P.ms = 0.0
    P.hp -= x
    P.taken += x
    P.hits += swings
    if P.walk:
        P.daze_p = 1 - (1 - P.daze_p) * (1 - P.o['daze'] * swings)
        P.daze_u = t + DAZE_S
    if shielded:
        return
    pushback(P, swings)


def pushback(P, swings):
    ch = P.chan
    if ch and P.o['bz_pushback'] != 'none':
        ch['lost'] += swings
        if ch['lost'] >= 1:
            ch['lost'] -= 1
            ch['left'] = 0 if P.o['bz_pushback'] == 'end' else ch['left'] - 1
            if ch['left'] <= 0:
                P.chan = None
    c = P.cast
    if c and P.ch.pushback_s > 0:
        c['end'] += P.ch.pushback_s * swings * (1 - P.K['prot'].get(c['name'], 0.0))


# ---------------------------------------------------------------- reading the pack (the loops decide from it)
def edge(P, mobs, q):
    """The gap at which q of the cohorts' weight is nearer (a weighted quantile; no sliver steers the loop)."""
    tot = weight(mobs)
    if tot <= 0:
        return 1e9
    cum = 0.0
    for c in sorted(mobs, key=lambda c: c.x):
        cum += c.w
        if cum >= q * tot - 1e-12:
            return c.x - P.m
    return mobs[-1].x - P.m


# ---------------------------------------------------------------- the scoring layer lives in aoe_loops
SCORING = ('result', 'fail_mode', 'per_kill', 'mean', 'run_pull', 'better', 'best_pull', 'baseline', 'breakeven',
           'simulate')


def __getattr__(name):
    """aoe.run_pull and the rest of the scoring layer, from aoe_loops at first use (either may be imported first)."""
    if name in SCORING:
        import aoe_loops
        return getattr(aoe_loops, name)
    raise AttributeError(f"module 'aoe' has no attribute {name!r}")
