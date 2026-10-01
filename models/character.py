"""The Forever Mage by level, the mob model, the rotations, and evaluate(): the best single-target rotation for a build.

Sources:
- Base mana and spell crit per Intellect by level: the beta client's PlayerExpectedStat (1.60.1.69893, wago.tools).
- Base health, Intellect, Spirit and Stamina by level: Wowhead's Forever gear planner (ElliotWood/Forever
  assets/db_inputs/wowhead_forever_gearplanner.txt, the arrays the sim takes its level 60 row from). Race offsets:
  the sim's base_stats.go. Copies: forever-warlock-lab-drafts/mage-research/leveling/mage_base_stats.json.
- Mana from Intellect (first 20 give 1, the rest 15) and health from Stamina (first 20 give 1, the rest 10): the sim
  (sim/core/mana.go, character.go). Spirit regeneration 6.25 + Spirit/8 a second: the sim (mana.go), which keeps
  Classic's rule for Mages.
- Mob health, mob damage, the level-difference hit table, 8 s walking and the mob health multiples: the Warlock lab,
  unchanged, so the two pages stay comparable (forever-warlock-lab README assumptions table; models/character.py
  mob_hp; models/leveling_sim.py BASE_HIT; src/builder.js HP_MULTS).
Everything else marked ASSUMPTION below is a modelling choice with an option to change it.
"""
import json
import os

import leveling_sim as ls
from leveling_sim import Char, seconds_per_kill

HERE = os.path.dirname(os.path.abspath(__file__))
TALENTS = json.load(open(os.path.join(HERE, '..', 'data', 'talents.json'), encoding='utf-8'))['talents']
KEYS = [t['k'] for t in TALENTS]
BY_KEY = {t['k']: t for t in TALENTS}


def valid(tal):
    """Point rules of data/talents.json: ranks within max, 5 points per row within a tree, prerequisites at full
    ranks (the Classic convention, UNVERIFIED for Forever). Keys starting with '_' are ignored."""
    rows = [[0] * 7 for _ in range(3)]
    for key, n in tal.items():
        if key.startswith('_') or not n:
            continue
        t = BY_KEY.get(key)
        if t is None or n < 0 or n > t['m']:
            return False
        rows[t['t']][t['r']] += n
    for tree in rows:
        for r in range(7):
            if tree[r] and sum(tree[:r]) < 5 * r:
                return False
    for key, n in tal.items():
        if n and not key.startswith('_') and BY_KEY[key]['req']:
            req, need = BY_KEY[key]['req']
            if tal.get(req, 0) < need:
                return False
    return True


def points(tal):
    return sum(n for key, n in tal.items() if not key.startswith('_'))


# ---------------------------------------------------------------- base stats by level (index 0 is level 1)
BASE_MANA = [100, 110, 121, 118, 131, 145, 160, 161, 178, 196, 215, 220, 241, 263, 271, 295, 305, 331, 343, 371, 385,
             415, 431, 463, 481, 515, 535, 556, 592, 613, 634, 670, 691, 712, 733, 754, 790, 811, 832, 853, 874, 895,
             916, 937, 958, 979, 1000, 1021, 1042, 1048, 1069, 1090, 1111, 1117, 1138, 1159, 1165, 1186, 1192, 1213]
BASE_HP = [41, 47, 52, 67, 82, 97, 102, 117, 132, 137, 152, 167, 172, 187, 202, 207, 222, 237, 242, 257, 272, 277, 292,
           298, 315, 333, 342, 362, 373, 395, 418, 432, 457, 473, 500, 518, 547, 577, 598, 630, 653, 687, 712, 748, 775,
           813, 842, 882, 913, 955, 988, 1032, 1067, 1103, 1150, 1188, 1237, 1277, 1328, 1370]
BASE_STA = [20, 20, 21, 21, 21, 21, 22, 22, 22, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27, 28, 28, 28, 29,
            29, 30, 30, 30, 31, 31, 32, 32, 33, 33, 33, 34, 34, 35, 35, 36, 36, 37, 37, 38, 38, 39, 39, 40, 40, 41, 42,
            42, 43, 43, 44, 44, 45]
BASE_INT = [23, 24, 25, 27, 28, 29, 30, 31, 33, 34, 35, 37, 38, 39, 41, 42, 43, 45, 46, 48, 49, 51, 52, 54, 55, 57, 59,
            60, 62, 64, 65, 67, 69, 70, 72, 74, 76, 78, 80, 81, 83, 85, 87, 89, 91, 93, 95, 98, 100, 102, 104, 106, 108,
            111, 113, 115, 118, 120, 123, 125]
BASE_SPI = [22, 23, 24, 25, 27, 28, 29, 30, 31, 33, 34, 35, 36, 38, 39, 40, 42, 43, 44, 46, 47, 49, 50, 52, 53, 55, 56,
            58, 59, 61, 63, 64, 66, 68, 69, 71, 73, 75, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100, 102, 104,
            106, 109, 111, 113, 115, 118, 120]
CRIT_PER_INT = [0.00191999995, 0.00184599997, 0.00177800003, 0.00165500003, 0.00159999996, 0.00154800003,
                0.00150000001, 0.00145500002, 0.00137099996, 0.00133300002, 0.00123099994, 0.00109100004,
                0.00102099997, 0.00085700001, 0.000787, 0.00075000001, 0.00070600002, 0.00066700001, 0.00063199998,
                0.00059299998, 0.00057099998, 0.00053899997, 0.00052200002, 0.00049499999, 0.00047500001,
                0.00045699999, 0.000436, 0.000397, 0.00038099999, 0.00036599999, 0.00035799999, 0.00034500001,
                0.000336, 0.00032699999, 0.00031599999, 0.00030799999, 0.000298, 0.000291, 0.00028199999,
                0.00027600001, 0.00026999999, 0.00025300001, 0.00024699999, 0.000241, 0.000235, 0.000231, 0.000225,
                0.00022, 0.00021499999, 0.00021100001, 0.000207, 0.000203, 0.000199, 0.00019399999, 0.00019000001,
                0.000181, 0.00017699999, 0.00017499999, 0.00017100001, 0.000168]
# Base spell crit before Intellect: 0.2%, Classic's gtChanceToSpellCritBase for Mages, which the sim now uses
# (sim/core/base_stats.go ClassBaseCritPercent, lines 230 to 255); the 0.9075% in base_stats_auto_gen.go is TBC's
# level 70 fit, which that file says a level 60 Forever character has no business with.
BASE_SPELL_CRIT = 0.002
ARCANE_INTELLECT = [[1, 2], [14, 7], [28, 15], [42, 22], [56, 31]]   # self-buff, 1 hour: [learn, Intellect]
# Race offsets to Intellect, Spirit, Stamina (sim base_stats.go); 'none' is the Human base without racials
RACES = dict(none=(0, 0, 0), human=(0, 0, 0), gnome=(3, 0, -1), skyborne=(1, 0, -1), orc=(-3, 3, 2), undead=(-2, 5, 1),
             troll=(-4, 1, 1))
BASE_HIT = {0: .96, 1: .95, 2: .94, 3: .83}     # Warlock lab leveling_sim.py BASE_HIT, the level-difference table

# ---------------------------------------------------------------- assumptions (docs/leveling-model.md, with options)
GEAR = dict(int=1.0, sta=1.0, spi=0.5)   # ASSUMPTION: leveling gear adds 1 Int, 1 Sta, 0.5 Spirit per level
MOB_SPEED = 8.0         # mob run speed, gap register mobRunSpeed (ElliotWood sim framework constant; test m3)
PULL_GAP = 25.0         # ASSUMPTION: pulled at 30 yd, melee reach 5 yd
STEP_S = 2.0            # ASSUMPTION: a root lets you walk 2 s away (14 yd at 7 yd/s, gap register) before casting
SWING_S = 2.0           # ASSUMPTION: mob swing time (gap register mobSwingTime), for pushback and armor chills
PUSHBACK_S = 0.5        # ASSUMPTION: each melee hit delays a cast 0.5 s (a channel loses one missile a hit)
# ASSUMPTION: each damage event breaks Frost Nova's root half the time (gap register, m12). Frostbite's freeze
# (12494) breaks the same way by default: its SpellAuraOptions row equals Frost Nova's (122, 865, 6131, 10230) and
# Entangling Roots' (339) in both Classic Era 1.15.9 and Forever 1.60.1 (ProcChance 100, ProcTypeMask 0x800A22A8,
# every damage-taken flag); roots that do not break on damage (23694, 19675) have mask 0 or no row.
NOVA_BREAK = 0.5
ARMOR_SLOW = 0.25       # ASSUMPTION: Frost and Ice Armor's chill slows the attacker's swings 25% (gap register armorChill)
BEASTS, HUMANOIDS, ELEMENTALS = 0.4, 0.4, 0.1   # ASSUMPTION: mob mix (beasts and humanoids as the Warlock lab)
HP_MULTS = (0.9, 1.0, 1.1)      # results averaged over mob health 90/100/110% (Warlock builder HP_MULTS)
TRAVEL = 8.0                    # seconds walking to the next mob (Warlock lab)


def mob_hp(L):
    return 18 * L + 0.62 * L * L


def mob_dps(L):
    return 0.035 * L * L


def arcane_intellect(L):
    return [r for r in ARCANE_INTELLECT if r[0] <= L][-1][1]


def make_char(L, tal, gear=1, race='none', **o):
    """The Mage at level L with talents tal, spell power gear x L (gear 1 or 2, as the Warlock page), and race.
    Options (all have defaults; docs/leveling-model.md): gear_int, gear_sta, gear_spi, level_diff, sword, beast_share,
    humanoid_share, elemental_share, leyline, regen_stack ('add' or 'max'), armor ('auto': Frost or Ice Armor below 34,
    Mage Armor from 34; 'frost': never Mage Armor), frostbite_source ('every' chill, or 'spells' only: test m17),
    armor_slow, thrill (Thrill of Adventure rank 0 to 5), pushback, mob_dps_mult (test m16), low_ranks ('measured',
    'full', 'classic', 'tbc': test m13), plus every Char option. fb_break defaults to nova_break."""
    r = RACES[race]
    g = dict(GEAR, int=o.get('gear_int', GEAR['int']), sta=o.get('gear_sta', GEAR['sta']), spi=o.get('gear_spi', GEAR['spi']))
    intel = (BASE_INT[L - 1] + r[0] + g['int'] * L + arcane_intellect(L)) * (1 + ls.TV['ArcaneMind'][tal['ArcaneMind'] - 1]
                                                                              if tal.get('ArcaneMind') else 1)
    spirit = (BASE_SPI[L - 1] + r[1] + g['spi'] * L) * (1.05 if race == 'human' else 1.0)
    sta = BASE_STA[L - 1] + r[2] + g['sta'] * L
    mana = (BASE_MANA[L - 1] + 20 + 15 * (intel - 20)) * (1.05 if race == 'gnome' else 1.0)
    hp = BASE_HP[L - 1] + 20 + 10 * (sta - 20)
    leyline = o.get('leyline', 'short') if race == 'skyborne' else 'off'
    regen = 2.0 if leyline == 'long' else 1.0
    hreg = (6 + 0.1 * spirit) / 2 * regen * (1.1 if race == 'troll' else 1.0)   # ASSUMPTION: Classic formula
    mage_armor = L >= 34 and o.get('armor', 'auto') == 'auto'                   # Mage Armor from 34
    ma = 0.5 if mage_armor else 0.0
    am = ls.TV['ArcaneMeditation'][tal['ArcaneMeditation'] - 1] if tal.get('ArcaneMeditation') else 0.0
    cast_regen = min(1.0, ma + am) if o.get('regen_stack', 'add') == 'add' else max(ma, am)
    dmg = 1.0
    if race == 'troll':
        dmg += 0.05 * o.get('beast_share', BEASTS)
    if race == 'skyborne':
        dmg += 0.05 * o.get('elemental_share', ELEMENTALS)
    keep = {k: o[k] for k in ('pull_gap', 'mob_speed', 'player_speed', 'step_s', 'swing', 'pushback_s', 'nova_break',
                              'fb_break', 'kite', 'il_coef', 'dd_mode', 'below20', 'low_ranks', 'top_ranks', 'potions',
                              'gems', 'evocation', 'wowhead_drinks', 'spirit_drink', 'mountain_water') if k in o}
    keep.setdefault('pull_gap', PULL_GAP)
    keep.setdefault('mob_speed', MOB_SPEED)
    keep.setdefault('step_s', STEP_S)
    keep.setdefault('swing', SWING_S)
    keep.setdefault('pushback_s', PUSHBACK_S if o.get('pushback', True) else 0.0)
    keep.setdefault('nova_break', NOVA_BREAK)
    keep.setdefault('fb_break', keep['nova_break'])   # Frostbite's freeze has Frost Nova's aura row (see NOVA_BREAK)
    return Char(level=L, race=race, talents=tal, sp=gear * L, crit=BASE_SPELL_CRIT + intel * CRIT_PER_INT[L - 1],
                crit_bonus=0.02 if race == 'human' and o.get('sword', True) and L >= 21 else 0.0,
                hit_base=BASE_HIT[o.get('level_diff', 0)], max_hp=hp, max_mana=mana, base_mana=BASE_MANA[L - 1],
                intellect=intel, spirit=spirit, mreg=(6.25 + spirit / 8) * regen, hreg=hreg,
                hreg_combat=0.1 * hreg if race == 'troll' else 0.0, cast_regen=cast_regen,
                haste=1.01 if race == 'skyborne' else 1.0, dmg_mult=dmg, wand_dps=0.9 * L + 3, totg=race == 'undead',
                mob_dps=mob_dps(L) * o.get('mob_dps_mult', 1.0), thrill=0.01 * o.get('thrill', 0), leyline=leyline,
                cannibalize=o.get('humanoid_share', HUMANOIDS) if race == 'undead' else 0.0,
                rapid_regen=race == 'troll', armor_chill=not mage_armor, armor_slow=o.get('armor_slow', ARMOR_SLOW),
                frostbite_armor=o.get('frostbite_source', 'every') == 'every', **keep)


# ---------------------------------------------------------------- rotations
def _p(filler, *prio):
    return dict(prio=list(prio), filler=filler)


# Base rotations, simplest first: on a tie the first name wins. Every rotation also casts, when the build has them,
# Ice Lance on a frozen target or a Fingers of Frost charge, a 1.5 s Pyroblast at 3 Hot Streak stacks, and a free
# Arcane Missiles on Missile Barrage (evaluate() tags the name when it does). evaluate() searches the modifiers.
POLICIES = {
    'Frostbolt': _p('Frostbolt', 'Frostbolt'),
    'Fireball': _p('Fireball', 'Fireball'),
    'Arcane Missiles': _p('ArcaneMissiles', 'ArcaneMissiles'),
    'Fire Blast + Frostbolt': _p('Frostbolt', 'FireBlast', 'Frostbolt'),
    'Fire Blast + Fireball': _p('Fireball', 'FireBlast', 'Fireball'),
    'Fire Blast + Arcane Missiles': _p('ArcaneMissiles', 'FireBlast', 'ArcaneMissiles'),
    'Fire Blast + Scorch': _p('Scorch', 'FireBlast', 'Scorch'),
    'Frostfire Bolt': _p('FrostfireBolt', 'FrostfireBolt'),
    'Fire Blast + Frostfire Bolt': _p('FrostfireBolt', 'FireBlast', 'FrostfireBolt'),
    'Arcane Blast + Frostbolt': _p('Frostbolt', 'ArcaneBlast', 'Frostbolt'),
    'Arcane Blast + Fireball': _p('Fireball', 'ArcaneBlast', 'Fireball'),
    'Fire Blast + Wand': _p(None, 'FireBlast', 'Wand'),
    'Wand': _p(None, 'Wand'),
}
BASE_LABEL = {
    'Frostbolt': 'Frostbolt',
    'Fireball': 'Fireball',
    'Arcane Missiles': 'Arcane Missiles',
    'Fire Blast + Frostbolt': 'Frostbolt, Fire Blast on cooldown',
    'Fire Blast + Fireball': 'Fireball, Fire Blast on cooldown',
    'Fire Blast + Arcane Missiles': 'Arcane Missiles, Fire Blast on cooldown',
    'Fire Blast + Scorch': 'Scorch, Fire Blast on cooldown',
    'Frostfire Bolt': 'Frostfire Bolt',
    'Fire Blast + Frostfire Bolt': 'Frostfire Bolt, Fire Blast on cooldown',
    'Arcane Blast + Frostbolt': 'Arcane Blast, then Frostbolt to spend the stack',
    'Arcane Blast + Fireball': 'Arcane Blast, then Fireball to spend the stack',
    'Fire Blast + Wand': 'wand, Fire Blast on cooldown',
    'Wand': 'wand only',
}
# Longest tag first: policy_label strips each tag it finds, so ' +Nova' must come after the tags that start with it.
MOD_LABEL = [
    (' +Nova, step back after freezes', 'Frost Nova when the mob gets close, and step back after any freeze'),
    (' +Nova, step back', 'Frost Nova when the mob gets close, then step back'),
    (' +Nova', 'Frost Nova when the mob gets close (no stepping back)'),
    (' +step back after freezes', 'step back when Frostbite freezes the mob'),
    (' +melee instants', 'Cone of Cold, Blast Wave or Arcane Explosion when the mob is close'),
    (' +Pyroblast pull', 'open with Pyroblast'),
    (' +Ice Barrier', 'Ice Barrier before the pull'),
    (' +wand finish', 'wand the last 20%'),
    (' (1 rank down)', 'main spell one rank down'),
    (' (2 ranks down)', 'main spell two ranks down'),
    (' (rank 1)', 'main spell at rank 1'),
    (' +Ice Lance', 'Ice Lance on every freeze and Fingers of Frost charge'),
    (' +Hot Streak Pyroblast', 'a fast Pyroblast at 3 Hot Streak stacks'),
    (' +Missile Barrage', 'free Arcane Missiles on Missile Barrage'),
]
DOWNRANK = [(1, ' (1 rank down)'), (2, ' (2 ranks down)'), ('r1', ' (rank 1)')]
AUTO_TAGS = [('IceLance', ' +Ice Lance'), ('HotPyro', ' +Hot Streak Pyroblast'), ('Barrage', ' +Missile Barrage')]


def policy_label(name):
    """A short plain-English rotation for a policy name, for the builder."""
    base = name
    parts = []
    for tag, text in MOD_LABEL:
        if tag in base:
            base = base.replace(tag, '')
            parts.append(text)
    return ', '.join([BASE_LABEL.get(base, base)] + parts)


# Talents the score responds to; the builder marks the rest "not in the score" (reasons in leveling.js UNSCORED):
# ArcaneSubtlety (mob resistances are not modelled), MagicAbsorption (resists), ArcaneResilience, FrostWarding (armor:
# mob damage is a flat rate), ArcaneShielding (Mana Shield is not cast), ImprovedCounterspell, ImprovedFireWard (no
# caster mobs), ImprovedFlamestrike, ImprovedBlizzard (area spells: the AoE model), IceBlock (defensive), ColdSnap
# (10 min cooldown, about one extra Frost Nova per 15 kills, not modelled). The range talents score through the pull.
SCORED = ['WandSpecialization', 'ArcaneFocus', 'ImprovedChanneling', 'ArcaneConcentration', 'ArcaneGeometry',
          'ArcaneImpact', 'ArcaneBlast', 'ArcaneMeditation', 'MissileBarrage', 'PresenceOfMind', 'ArcaneMind',
          'ArcaneInstability', 'ArcanePower', 'WakeOfFire', 'Incineration', 'ImprovedFireball', 'Ignite',
          'FlameThrowing', 'Impact', 'BurningSoul', 'Pyroblast', 'ImprovedScorch', 'HotStreak', 'MasterOfElements',
          'CriticalMass', 'BlastWave', 'FirePower', 'Combustion', 'ImprovedFrostbolt', 'ElementalPrecision',
          'IceShards', 'Permafrost', 'ImprovedFrostNova', 'Frostbite', 'PiercingIce', 'FrostChanneling', 'IceLance',
          'ArcticReach', 'Shatter', 'ImprovedConeOfCold', 'FingersOfFrost', 'WintersChill', 'IceBarrier']


def usable_steps(pol, ch):
    """The steps of a rotation, or None when the character cannot cast one of them yet (a rotation is only run when
    every spell it names is learned, so its name never hides a different rotation)."""
    for s in pol['prio']:
        if s != 'Wand' and not ls.pick_row(ch, s, {}):
            return None
    return tuple(pol['prio'])


def mod_groups(L, tal, ch):
    """Modifier groups the rotation search tries. Each group is off or one of its options; an option is (the policy
    keys it sets, the label it adds to the name). The first group is how the Mage uses roots: Frost Nova without
    stepping, Frost Nova then step back, Frost Nova and step back after any freeze, or (with Frostbite) step back
    after freezes without Frost Nova. Stepping is offered only while the kite option allows it."""
    groups, ctl = [], []
    if L >= 10:
        ctl.append(({'nova': True}, ' +Nova'))
        if ch.kite:
            ctl.append(({'nova': True, 'step': 'nova'}, ' +Nova, step back'))
    if L >= 10 and ch.kite and tal.get('Frostbite'):
        ctl.append(({'nova': True, 'step': 'all'}, ' +Nova, step back after freezes'))
    if ch.kite and tal.get('Frostbite'):
        ctl.append(({'step': 'all'}, ' +step back after freezes'))
    if ctl:
        groups.append(ctl)
    if L >= 14:
        groups.append([({'melee': True}, ' +melee instants')])
    if tal.get('Pyroblast') and L >= 20:
        groups.append([({'pull': 'Pyroblast'}, ' +Pyroblast pull')])
    if tal.get('IceBarrier') and L >= 40:
        groups.append([({'ib': True}, ' +Ice Barrier')])
    groups.append([({'fin': 'Wand'}, ' +wand finish')])
    return groups


def rank_group(L, pol, ch, downrank=True):
    """The downrank options for a rotation's main spell: only where low ranks may be cast (leveling_sim
    downrank_allowed: level 19 and below by default) and the spell has the ranks."""
    if not downrank or not pol.get('filler') or not ls.downrank_allowed(L, 'classic' if ch.below20 else ch.low_ranks):
        return []
    n = len(ls.rank_rows(pol['filler'], L, ch.top_ranks))
    return [({'dr': dr}, label) for dr, label in DOWNRANK if n > (1 if dr == 'r1' else dr)]


def mod_options(L, tal):
    """The v1 flat list of modifier options, (key, value, label), kept for old callers; the search uses mod_groups."""
    out = []
    for group in mod_groups(L, tal, Char(level=L)):
        for keys, label in group:
            for key, val in keys.items():
                out.append((key, val, label))
    return out


def needs_ref(ch, pol):
    """Whether a rotation leans on a cooldown longer than a kill, whose share of pulls needs a first pass."""
    T = ch.talents
    return bool(ch.race in ('orc', 'troll', 'gnome') or T.get('PresenceOfMind') or T.get('ArcanePower')
                or (T.get('Combustion') and ch.level >= 40) or (T.get('WakeOfFire') and 'FireBlast' in pol['prio'])
                or pol.get('ib'))


AVG_KEYS = ('spk', 'ttk', 'rest', 'taken', 'mana_spent', 'pots', 'evo', 'drink', 'eat')


def run_policy(ch_fn, L, pol, hp_mults, travel):
    """seconds_per_kill averaged over mob health multiples, run i of n starting its proc accumulators at phase
    (2i + 1) / 2n (see leveling_sim.simulate). A rotation with a long cooldown runs a first pass at mob health x1.0
    alone to measure its kill cycle, then the full average with each cooldown's share of pulls (and Wake of Fire's
    window) from that cycle. casts_all sums the casts of every run."""
    def avg(p, hp_mults=hp_mults):
        n, ch = len(hp_mults), ch_fn()
        k, R = ls.fight_consts(ch, p), ls.rest_setup(ch)
        rs = [seconds_per_kill(ch, mob_hp(L) * m, p, travel, (2 * i + 1) / (2 * n), k, R)
              for i, m in enumerate(hp_mults)]
        out = dict(rs[0])
        for key in AVG_KEYS:
            out[key] = ls.add_up(r[key] for r in rs) / len(rs)
        out['feasible'] = all(r['feasible'] for r in rs)
        out['casts_all'] = {}
        for r in rs:
            for a, c in r['casts'].items():
                out['casts_all'][a] = out['casts_all'].get(a, 0) + c
        return out
    ch = ch_fn()
    if not needs_ref(ch, pol):
        return avg(pol)
    r = avg(pol, (1.0,))
    ref = r['spk']
    p2 = dict(pol, p_pom=min(1.0, ref / 180), p_ap=min(1.0, ref / 180), p_comb=min(1.0, ref / 180),
              p_bf=min(1.0, ref / 120), p_bz=min(1.0, ref / 180), p_eu=min(1.0, ref / 120), p_ib=min(1.0, ref / 30),
              wake=30.0 - travel - r['rest'])
    return avg(p2)


def better(a, b):
    """Whether result a beats result b: feasible first, then fewer seconds per kill."""
    if b is None:
        return True
    if a['feasible'] != b['feasible']:
        return a['feasible']
    return a['spk'] < b['spk'] - 1e-9


def compose(pol, name, groups, choice):
    """A rotation with the chosen option of each group (None: off), and its name."""
    p, n = dict(pol), name
    for g, c in zip(groups, choice):
        if c is not None:
            p.update(g[c][0])
            n += g[c][1]
    return p, n


def pol_key(pol):
    """A policy's identity for the per-evaluate memo."""
    return '|'.join(k + '=' + (','.join(v) if k == 'prio' else str(v)) for k, v in sorted(pol.items()))


def _single_moves(gs, choice):
    """Every choice that differs from `choice` in one group (None: the group off)."""
    return [choice[:gi] + [c] + choice[gi + 1:] for gi, g in enumerate(gs)
            for c in [None] + list(range(len(g))) if c != choice[gi]]


def _pair_moves(gs, choice):
    """Every choice that differs from `choice` in two groups at once (or in one of the two)."""
    out = []
    for gi in range(len(gs)):
        for gj in range(gi + 1, len(gs)):
            for ci in [None] + list(range(len(gs[gi]))):
                for cj in [None] + list(range(len(gs[gj]))):
                    if ci == choice[gi] and cj == choice[gj]:
                        continue
                    trial = list(choice)
                    trial[gi], trial[gj] = ci, cj
                    out.append(trial)
    return out


def _best_move(run, pol, name, gs, cur, trials):
    """The fastest trial that beats `cur` (the first of equals, in order), as (choice, result); None if none does."""
    best = None
    for trial in trials:
        r = run(compose(pol, name, gs, trial)[0])
        if better(r, cur) and (best is None or better(r, best[1])):
            best = (trial, r)
    return best


def coord_search(run, pol, name, gs, start, passes=3, pairs=True):
    """Steepest descent over the modifier groups, from `start` (one entry per group, None: off). Move to the fastest
    single-group change while one beats the current choice (at most passes x groups moves). Then, if `pairs`, move
    to the fastest two-group change and start over. Returns (choice, result). Taking the first faster change instead
    stranded the search three changes from the best (3.3% at level 46, 1 Oct 2026)."""
    choice = list(start)
    cur = run(compose(pol, name, gs, choice)[0])
    while True:
        for _ in range(passes * max(1, len(gs))):
            best = _best_move(run, pol, name, gs, cur, _single_moves(gs, choice))
            if best is None:
                break
            choice, cur = best
        if not pairs:
            return choice, cur
        best = _best_move(run, pol, name, gs, cur, _pair_moves(gs, choice))
        if best is None:
            return choice, cur
        choice, cur = best


def evaluate(L, tal, gear=1, race='none', hp_mults=HP_MULTS, top=6, mods=True, downrank=True, policies=None,
             travel=TRAVEL, pair_top=2, **o):
    """Best single-target rotation for a build: (name, result).
    The space: every base rotation the build can cast x every combination of the modifier groups (mod_groups, each
    off or one option) x every allowed rank of its main spell (rank_group).
    1. Probe: every base runs plain, at each allowed rank, with its first group's second option alone (Frost
       Nova, then step back), and with that option at each allowed rank; its best probe ranks it.
    2. The best `top` bases (feasible first) each get coord_search from their best probe: steepest descent over
       single-group changes, and for the best `pair_top` also two-group changes. Results are memoized within the call.
    analysis/leveling_search_check.py compares this with the exhaustive search (every base, modifier set and rank).
    On its 212-case grid (1 Oct 2026, final orders) the largest gap was 0.000%, at 87 rotations run on average
    against 229 for the exhaustive search. A rotation in which the Mage dies or
    the mob lives 240 s is infeasible and never beats a feasible one. The name carries ' +Ice Lance', ' +Hot Streak
    Pyroblast' and ' +Missile Barrage' when the rotation casts them. result has spk (seconds per kill: fight +
    walking + rest), ttk, rest, feasible, pots and evo, and the fight details."""
    ch0 = make_char(L, tal, gear, race, **o)

    def ch_fn():                    # a fight never changes the character, so every run shares one
        return ch0
    memo = {}

    def run(p):
        key = pol_key(p)
        if key not in memo:
            memo[key] = run_policy(ch_fn, L, p, hp_mults, travel)
        return memo[key]
    groups = mod_groups(L, tal, ch0) if mods else []
    seen, probed, best = set(), [], None
    for name, pol in (policies or POLICIES).items():
        sig = usable_steps(pol, ch0)
        if sig is None or sig in seen:
            continue
        seen.add(sig)
        rg = rank_group(L, pol, ch0, downrank)
        gs = groups + ([rg] if rg else [])
        blank = [None] * len(gs)
        cands = [blank]
        if rg:
            cands += [blank[:-1] + [c] for c in range(len(rg))]
        if gs and not (rg and len(gs) == 1):
            first = min(1, len(gs[0]) - 1)
            cands.append([first] + blank[1:])
            if rg:                  # that option at each rank: a lower rank can pay only once Nova is in
                cands += [[first] + blank[1:-1] + [c] for c in range(len(rg))]
        pb = None
        for c in cands:
            r = run(compose(pol, name, gs, c)[0])
            if pb is None or better(r, pb[4]):
                pb = (name, pol, gs, c, r)
        probed.append(pb)
        if best is None or better(pb[4], best[1]):
            best = (compose(pol, name, gs, pb[3])[1], pb[4])
    ranked = sorted([b for b in probed if b[4]['feasible']] or probed, key=lambda b: b[4]['spk'])[:top]
    for i, (name, pol, gs, c0, r0) in enumerate(ranked):
        choice, cur = coord_search(run, pol, name, gs, c0, pairs=i < pair_top)
        if better(cur, best[1]):
            best = (compose(pol, name, gs, choice)[1], cur)
    name, r = best
    for cast, tag in AUTO_TAGS:
        if r['casts_all'].get(cast, 0) > 0:
            name += tag
    return name, r
