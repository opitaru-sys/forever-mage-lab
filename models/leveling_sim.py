"""Expected-value single-target leveling fight simulator and rest model for a WoW: Forever Mage.

Pattern: the Warlock lab's models/leveling_sim.py (v8): a 0.02 s event loop, hit and crit folded into every hit as
expected values, proc-driven casts (Hot Streak, Fingers of Frost, Frostbite, Missile Barrage) as accumulated expected
procs that fire once a whole proc has built up, and cooldowns longer than a kill entered as the share of pulls they
are ready for (policy keys p_*, set by evaluate() in character.py). Spell data: data/mage_spells.json; talent values:
data/talents.json (tests/make_leveling_fixtures.py checks every embedded row against both). ASSUMPTION marks a value
with no source; docs/leveling-model.md lists each with its option. The rest model (rest_setup, travel_regen,
rest_solve) stands apart from the fight loop so the AoE model can call it.
"""
import math
from dataclasses import dataclass, field

DT = 0.02
GCD = 1.5
MAX_TIME = 240.0
FIN_BELOW = 0.2        # policy fin='Wand': wand once the mob is under 20% health
MELEE_GAP = 5.0        # Frost Nova, Cone of Cold, Arcane Explosion and Blast Wave reach 10 yd: within 5 yd of melee
WAND_SPEED = 1.5       # ASSUMPTION: a 1.5 s wand; each shot is a damage event (breaks, Touch of the Grave)
CONJURE_S = 3.0        # every Conjure Water and Conjure Food rank is a 3 s cast (client)
MIN_SAVE = 1.0         # ASSUMPTION: a rest cooldown action (potion, Evocation, racial) must save 1 s a use

# ---------------------------------------------------------------- spell ranks (data/mage_spells.json)
# Direct rows: [learn level (= spell level), average at learn, per level, max level, coefficient, mana, cast s].
# Rows with a DoT add [average per tick, ticks, period s, coefficient per tick]. Arcane Missiles rows end in the
# missile count instead of a cast time, and their average and coefficient are per missile.
FROSTBOLT = [[4, 19, 0.5, 8, 0.407, 25, 1.5], [8, 33, 0.7, 12, 0.489, 35, 1.8], [14, 46, 0.9, 18, 0.597, 50, 2.2],
             [20, 60, 1.1, 24, 0.706, 65, 2.6], [26, 95, 1.5, 30, 0.814, 100, 3], [32, 134, 1.7, 36, 0.814, 130, 3],
             [38, 181, 2, 42, 0.814, 160, 3], [44, 244, 2.3, 48, 0.814, 195, 3], [50, 308, 2.6, 54, 0.814, 225, 3],
             [56, 386, 2.9, 60, 0.814, 260, 3]]
# Frostbolt's chill (40% slow on every rank) lasts by rank, keyed by learn level (client)
FROSTBOLT_SLOW_S = {4: 5, 8: 6, 14: 6, 20: 7, 26: 7, 32: 8, 38: 8, 44: 9, 50: 9, 56: 9, 60: 9}
FIREBALL = [[1, 18, 0.6, 5, 0.429, 30, 1.5, 1, 2, 2, 0], [6, 37, 0.7, 10, 0.571, 45, 2, 1, 3, 2, 0],
            [12, 53, 0.9, 16, 0.714, 65, 2.5, 2, 3, 2, 0], [18, 74, 1.1, 22, 0.857, 95, 3, 3, 4, 2, 0],
            [24, 108, 1.5, 28, 1, 140, 3.5, 4, 4, 2, 0], [30, 153, 1.8, 34, 1, 185, 3.5, 6, 4, 2, 0],
            [36, 187, 2.3, 40, 1, 220, 3.5, 6, 4, 2, 0], [42, 235, 2.2, 46, 1, 260, 3.5, 8, 4, 2, 0],
            [48, 300, 2.4, 52, 1, 305, 3.5, 10, 4, 2, 0], [54, 374, 2.7, 58, 1, 350, 3.5, 12, 4, 2, 0],
            [60, 451, 3, 64, 1, 395, 3.5, 14, 4, 2, 0]]
ARCANE_MISSILES = [[8, 24, 0.3, 12, 0.286, 85, 3], [16, 31, 0.4, 20, 0.286, 140, 4], [24, 44, 0.5, 28, 0.286, 235, 5],
                   [32, 66, 0.6, 36, 0.286, 320, 5], [40, 95, 0.7, 44, 0.286, 410, 5], [48, 130, 0.8, 52, 0.286, 500, 5],
                   [56, 171, 0.9, 60, 0.286, 595, 5]]
# Top ranks from looted tomes (Tome of Frostbolt XI, Fireball XII, Arcane Missiles VIII); where they drop in Forever is
# UNKNOWN (gap TOMES.md, test m6), so they are off unless the top_ranks option is on.
TOME = {'Frostbolt': [60, 475, 3.2, 64, 0.814, 290, 3], 'Fireball': [60, 483, 3, 64, 1, 410, 3.5, 15, 4, 2, 0],
        'ArcaneMissiles': [56, 209, 1, 60, 0.286, 655, 5]}
FIRE_BLAST = [[6, 28, 0.6, 11, 0.429, 40, 0], [14, 58, 1, 19, 0.429, 75, 0], [22, 100, 1.4, 27, 0.429, 115, 0],
              [30, 163, 1.8, 35, 0.429, 165, 0], [38, 236, 2.2, 43, 0.429, 220, 0], [46, 331, 2.6, 51, 0.429, 280, 0],
              [54, 438, 3, 59, 0.429, 340, 0]]
SCORCH = [[22, 39, 0.8, 26, 0.429, 50, 1.5], [28, 55, 1, 32, 0.429, 65, 1.5], [34, 69, 1, 38, 0.429, 80, 1.5],
          [40, 93, 1.2, 44, 0.429, 100, 1.5], [46, 116, 1.4, 50, 0.429, 115, 1.5], [52, 150, 1.5, 56, 0.429, 135, 1.5],
          [58, 178, 1.7, 62, 0.429, 150, 1.5]]
PYROBLAST = [[20, 110, 1.5, 24, 1, 125, 6, 11, 4, 3, 0.15], [24, 134, 1.7, 30, 1, 150, 6, 14, 4, 3, 0.15],
             [30, 191, 2.1, 36, 1, 195, 6, 19, 4, 3, 0.15], [36, 245, 2.4, 42, 1, 240, 6, 25, 4, 3, 0.15],
             [42, 311, 2.7, 48, 1, 285, 6, 31, 4, 3, 0.15], [48, 394, 3, 54, 1, 335, 6, 38, 4, 3, 0.15],
             [54, 481, 3.4, 60, 1, 385, 6, 46, 4, 3, 0.15], [60, 583, 4.6, 66, 1, 440, 6, 53, 4, 3, 0.15]]
ARCANE_BLAST = [[20, 54, 0.9, 28, 0.714, 0, 2.5], [30, 130, 1.4, 38, 0.714, 0, 2.5], [40, 169, 1.6, 48, 0.714, 0, 2.5],
                [50, 274, 2.1, 58, 0.714, 0, 2.5], [60, 394, 2.6, 68, 0.714, 0, 2.5]]
AB_COST = 0.15          # of base mana; +175% per stack (client 400573)
ICE_LANCE = [[20, 28, 0.35, 26, 0, 45, 0], [28, 36, 0.4, 32, 0, 55, 0], [34, 45, 0.5, 40, 0, 70, 0],
             [42, 79, 0.7, 48, 0, 105, 0], [48, 98, 0.7, 56, 0, 120, 0], [56, 145, 0.9, 64, 0, 160, 0]]
FROSTFIRE = [[40, 100, 1.3, 48, 0.814, 205, 3, 9, 3, 3, 0], [50, 182, 1.7, 58, 0.814, 285, 3, 13, 3, 3, 0],
             [60, 292, 2.1, 68, 0.814, 370, 3, 19, 3, 3, 0]]
ARCANE_EXPLOSION = [[14, 32, 0.4, 19, 0.143, 75, 0], [22, 55, 0.6, 27, 0.143, 120, 0], [30, 94, 0.9, 35, 0.143, 185, 0],
                    [38, 135, 0.9, 43, 0.143, 250, 0], [46, 183, 1.1, 51, 0.143, 315, 0], [54, 242, 1.3, 59, 0.143, 390, 0]]
CONE_OF_COLD = [[26, 97, 0.8, 31, 0.129, 210, 0], [34, 144, 1, 39, 0.129, 290, 0], [42, 204, 1.2, 47, 0.129, 380, 0],
                [50, 267, 1.3, 55, 0.129, 465, 0], [58, 340, 1.5, 63, 0.129, 555, 0]]
FROST_NOVA = [[10, 20, 0.5, 15, 0.029, 55, 0], [26, 34, 0.5, 31, 0.029, 85, 0], [40, 53, 0.5, 45, 0.029, 115, 0],
              [54, 73, 0.5, 59, 0.029, 145, 0]]
BLAST_WAVE = [[30, 163, 1, 36, 0.129, 215, 0], [36, 212, 1.2, 42, 0.129, 270, 0], [44, 293, 1.4, 50, 0.129, 355, 0],
              [52, 389, 1.6, 58, 0.129, 450, 0], [60, 493, 1.9, 66, 0.129, 545, 0]]
# Ice Barrier: [learn, absorb at learn, per level, max level, mana]
ICE_BARRIER = [[40, 431, 2.8, 46, 305], [46, 542, 3.2, 52, 360], [52, 671, 3.6, 58, 420], [58, 811, 4, 64, 480]]
TABLES = {'Frostbolt': FROSTBOLT, 'Fireball': FIREBALL, 'ArcaneMissiles': ARCANE_MISSILES, 'FireBlast': FIRE_BLAST,
          'Scorch': SCORCH, 'Pyroblast': PYROBLAST, 'ArcaneBlast': ARCANE_BLAST, 'IceLance': ICE_LANCE,
          'FrostfireBolt': FROSTFIRE, 'ArcaneExplosion': ARCANE_EXPLOSION, 'ConeOfCold': CONE_OF_COLD,
          'FrostNova': FROST_NOVA, 'BlastWave': BLAST_WAVE}
SCHOOL = {'Frostbolt': 'frost', 'Fireball': 'fire', 'ArcaneMissiles': 'arcane', 'FireBlast': 'fire', 'Scorch': 'fire',
          'Pyroblast': 'fire', 'ArcaneBlast': 'arcane', 'IceLance': 'frost', 'FrostfireBolt': 'frostfire',
          'ArcaneExplosion': 'arcane', 'ConeOfCold': 'frost', 'FrostNova': 'frost', 'BlastWave': 'fire'}
TALENT_SPELL = {'Pyroblast': 'Pyroblast', 'ArcaneBlast': 'ArcaneBlast', 'IceLance': 'IceLance', 'BlastWave': 'BlastWave'}
COOLDOWN = {'FireBlast': 8.0, 'ConeOfCold': 10.0, 'FrostNova': 25.0, 'BlastWave': 45.0}
INSTANT = ('FireBlast', 'IceLance', 'ArcaneExplosion', 'ConeOfCold', 'FrostNova', 'BlastWave')
CHILLS = ('Frostbolt', 'FrostfireBolt', 'ConeOfCold')
# Arcane Blast's stack buff reaches these (client mask, NOTES.md (a)); not Arcane Missiles, Blizzard or Flamestrike
AB_MASK = ('Frostbolt', 'Fireball', 'FireBlast', 'Scorch', 'Pyroblast', 'IceLance', 'FrostfireBolt', 'ArcaneExplosion',
           'ConeOfCold', 'FrostNova', 'BlastWave')
HOT_STREAK_FROM = ('Fireball', 'FrostfireBolt', 'FireBlast', 'Scorch')
DOT_NAME = {'Fireball': 'FireballDoT', 'Pyroblast': 'PyroblastDoT', 'FrostfireBolt': 'FrostfireBoltDoT'}

# Conjured water and food: [learn, per 5 s, duration s, conjure mana, count at learn, count per level, max level]
WATER = [[4, 42, 18, 60, 2, 2, 13], [10, 104, 21, 105, 2, 2, 19], [20, 174, 24, 180, 2, 2, 29],
         [30, 249, 27, 285, 2, 2, 39], [40, 332, 30, 420, 2, 2, 49], [50, 489, 30, 585, 2, 2, 59],
         [60, 700, 30, 780, 10, 2, 65]]
MOUNTAIN_WATER = [60, 850, 30, 845, 20, 2, 65]    # rank 8; whether Forever teaches it is UNKNOWN (option)
FOOD = [[6, 17, 18, 60, 2, 2, 15], [12, 58, 21, 105, 2, 2, 21], [22, 115, 24, 180, 2, 2, 31],
        [32, 162, 27, 285, 2, 2, 41], [42, 232, 30, 420, 2, 2, 51], [52, 358, 30, 585, 2, 2.25, 61],
        [60, 530, 30, 705, 10, 2, 65]]
STACK = 20              # conjured water and food stack to 20 (client max_stack)
WOWHEAD_DRINK = 25.0 / 26.0   # Wowhead prints 25/26 of the client total on all 15 conjured drinks and foods
# Mana gems: [learn, conjure mana, average restored]; all share one 120 s cooldown with Demonic and Dark Runes
GEMS = [[28, 530, 400], [38, 800, 600], [48, 1130, 850], [58, 1470, 1100]]
# Mana potions: [required level, average mana, client BuyPrice in copper] (Wowhead Forever tooltips; ItemSparse)
POTIONS = [[5, 160, 40], [14, 320, 120], [22, 520, 480], [31, 800, 480], [41, 1200, 1600], [49, 1800, 6000]]
POTION_NAMES = ['Minor Mana Potion', 'Lesser Mana Potion', 'Mana Potion', 'Greater Mana Potion',
                'Superior Mana Potion', 'Major Mana Potion']

# ---------------------------------------------------------------- talent values per rank (data/talents.json)
TV = dict(
    WandSpecialization=[.13, .25], ArcaneFocus=[.01, .02, .03, .04, .05],
    ImprovedChanneling=[.20, .40, .60, .80, 1.0], ImprovedChannelingAB=[.14, .28, .42, .56, .70],
    ArcaneConcentration=[.02, .04, .06, .08, .10], ArcaneImpact=[.02, .04, .06], ArcaneMeditation=[.17, .33, .50],
    ArcaneMind=[.02, .04, .06, .08, .10], ArcaneMindCrit=[.2, .4, .6, .8, 1.0], ArcaneInstability=[.01, .02, .03],
    WakeOfFire=[1.0, 2.0], WakeOfFireCrit=[.25, .50], Incineration=[.02, .04, .06], ImprovedFireball=[.1, .2, .3, .4, .5],
    Ignite=[.08, .16, .24, .32, .40], Impact=[.03, .07, .10], BurningSoul=[.23, .47, .70], ImprovedScorch=[.33, .67, 1.0],
    MasterOfElements=[.10, .20, .30], CriticalMass=[.02, .04, .06], FirePower=[.02, .04, .06, .08, .10],
    ImprovedFrostbolt=[.1, .2, .3, .4, .5], ElementalPrecision=[.01, .02, .03, .04, .05],
    IceShards=[.2, .4, .6, .8, 1.0], Permafrost=[.11, .22, .33], PermafrostSlow=[.03, .07, .10],
    ImprovedFrostNova=[2.0, 4.0], Frostbite=[.05, .10, .15], PiercingIce=[.02, .04, .06],
    FrostChanneling=[.05, .10, .15], Shatter=[.17, .33, .50], ImprovedConeOfCold=[.12, .23, .35],
    FingersOfFrost=[1, 2], WintersChill=[.20, .40, .60, .80, 1.0], ArcaneGeometry=[3.0, 6.0], FlameThrowing=[3.0, 6.0],
    ArcticReach=[.10, .20])
FOF_CHANCE = 0.15       # Fingers of Frost: 15% per chill at both ranks (client row's second effect)
WC_CRIT = 0.02          # Winter's Chill: +2% crit a stack on your own Frostbolt and Ice Lance
HOT_STREAK_CUT = 0.25   # Heating Up (Hot Streak before 1 Oct 2026): -25% Pyroblast cast a stack, 3 stacks, spent by the next Pyroblast
COMB_CRITS = 3          # Combustion ends after 3 Fire crits (Blizzard's 1 Oct 2026 beta notes; was 4)
BARRAGE = {'ArcaneBlast': 0.40, 'Fireball': 0.20, 'Frostbolt': 0.20, 'FrostfireBolt': 0.20}   # Missile Barrage
FV_STEP = 0.03          # Improved Scorch's Fire Vulnerability: +3% Fire damage from you a stack, 5 stacks


def add_up(xs):
    """Plain left-to-right float sum. Python 3.12+ sum() compensates rounding and JavaScript does not; this keeps
    leveling.js bit-for-bit equal."""
    s = 0.0
    for x in xs:
        s += x
    return s


def tv(ch, key, table=None):
    """A talent's per-rank value for this character's rank (0 when untaken)."""
    r = ch.talents.get(key, 0)
    return TV[table or key][r - 1] if r > 0 else 0


def rank_rows(name, L, top_ranks=False):
    """The ranks of a spell learned by level L, lowest first (the tome rank last when top_ranks is on)."""
    rows = [r for r in TABLES[name] if r[0] <= L]
    if top_ranks and name in TOME and TOME[name][0] <= L:
        rows.append(TOME[name])
    return rows


def dd_avg(row, L, mode='scaled'):
    """Average hit of a rank at level L. 'scaled' (default): the client's in-game formula, floor(average at learn +
    per level x (min(L, max level) - spell level)) (sim/core/spelldata/effect.go). 'base': the average at learn."""
    if mode == 'base':
        return row[1]
    return math.floor(row[1] + row[2] * (min(L, row[3]) - row[0]) + 1e-9)


def below20(row, on):
    """Classic's below-level-20 coefficient penalty, 3.75% per level under 20 (it reproduces the Classic Era client's
    stored low-rank coefficients exactly). Forever's client stores no penalty; off by default."""
    return 1 - 0.0375 * (20 - row[0]) if on and row[0] < 20 else 1.0


LOW_RANKS = ('measured', 'full', 'classic', 'tbc')


def coef_factor(row, L, low_ranks):
    """Share of a rank's stored coefficient it keeps at character level L (option low_ranks, test m13).
    Forever's client stores full coefficients (SpellEffect 116: 0.407 in 1.60.1, 0.163 in Classic Era 1.15.9), and
    DoubleZug measured full coefficients on low ranks at levels 18 and 19 (ForeverChanges downrank page), which rules
    out both rules below at those levels. 'measured' and 'full' keep the stored value; 'classic' is Classic's cut for
    spells learned below 20; 'tbc' is The Burning Crusade's (rank max level + 6) / L, capped at 1."""
    if low_ranks == 'classic':
        return below20(row, True)
    if low_ranks == 'tbc':
        return min(1.0, (row[3] + 6) / L)
    return 1.0


def downrank_allowed(L, low_ranks):
    """Whether a rotation may cast lower ranks. Default ('measured'): only at level 19 and below, where full
    coefficients were measured; from 20 the highest trained rank only, until test m13 measures it. The other
    choices allow it at every level."""
    return L <= 19 or low_ranks != 'measured'


# ---------------------------------------------------------------- character
@dataclass
class Char:
    level: int
    race: str = 'none'
    talents: dict = field(default_factory=dict)
    sp: float = 0.0
    crit: float = 0.05          # base spell crit plus Intellect crit, fraction
    crit_bonus: float = 0.0     # Human sword +2%
    hit_base: float = 0.96      # vs the mob's level (Warlock lab BASE_HIT)
    max_hp: float = 500.0
    max_mana: float = 500.0
    base_mana: float = 100.0    # Arcane Blast's cost is 15% of this
    intellect: float = 0.0
    spirit: float = 0.0
    mreg: float = 0.0           # mana a second from Spirit outside the five-second rule
    hreg: float = 0.0           # health a second out of combat
    hreg_combat: float = 0.0    # health a second in combat (Troll Regeneration only)
    cast_regen: float = 0.0     # share of mreg kept while casting (Mage Armor, Arcane Meditation)
    haste: float = 1.0          # cast speed multiplier (Skyborne Wind Blessed 1.01)
    dmg_mult: float = 1.0       # racial damage vs a share of mob types (Troll beasts, Skyborne elementals)
    wand_dps: float = 0.0
    totg: bool = False          # Undead Touch of the Grave, caster version
    totg_wand: bool = True      # it also rolls on wand shots (tooltip: spells and attacks; test m23)
    wand_breaks: bool = True    # a wand shot rolls Frost Nova and Frostbite breaks like any damage event
    mob_dps: float = 0.0
    mob_speed: float = 8.0
    pull_gap: float = 25.0
    player_speed: float = 7.0
    step_s: float = 2.0
    swing: float = 2.0
    pushback_s: float = 0.5
    nova_break: float = 0.5
    fb_break: float = 0.5       # Frostbite's freeze breaks like Frost Nova's (client SpellAuraOptions 12494 = 122)
    kite: bool = True
    il_coef: float = 0.143
    dd_mode: str = 'scaled'
    below20: bool = False       # kept for old callers: True means low_ranks 'classic'
    low_ranks: str = 'measured' # LOW_RANKS: how low ranks scale (coef_factor, downrank_allowed)
    top_ranks: bool = False
    potions: bool = True
    gems: bool = True
    evocation: bool = True
    wowhead_drinks: bool = False
    spirit_drink: bool = True
    mountain_water: bool = False
    thrill: float = 0.0         # Thrill of Adventure: share of max health and mana back per killing blow
    leyline: str = 'short'      # Skyborne Read Ley Line: 'short' (15 s), 'long' (15 min, always up), 'off'
    cannibalize: float = 0.0    # Undead: share of corpses that are humanoid or undead
    rapid_regen: bool = False   # Troll Rapid Regeneration
    armor_chill: bool = True    # Frost or Ice Armor worn: melee attackers are chilled (off under Mage Armor)
    armor_slow: float = 0.25    # the armor chill's attack slow (gap register armorChill, aura 319 read as attack speed)
    frostbite_armor: bool = True   # the armor chill rolls Frostbite and Fingers of Frost (test m17 default)


# ---------------------------------------------------------------- fight
def pick_row(ch, name, pol):
    """The rank a policy casts: the highest learned, or the filler downranked by pol['dr'] (1, 2, or 'r1')."""
    if name in TALENT_SPELL and not ch.talents.get(TALENT_SPELL[name], 0):
        return None
    rows = rank_rows(name, ch.level, ch.top_ranks)
    if not rows:
        return None
    dr = pol.get('dr', 0) if name == pol.get('filler') else 0
    if dr == 'r1':
        return rows[0]
    return rows[max(0, len(rows) - 1 - dr)]


def fight_consts(ch, pol):
    """Everything about a fight that stays fixed while it runs."""
    T, L = ch.talents, ch.level
    ai = tv(ch, 'ArcaneInstability')
    k = dict(row={}, avg={}, coef={}, smult={}, crit={}, crit_dot={}, cm={}, hit={}, cost={}, base_cost={}, ct={},
             prot={})
    for name in TABLES:
        row = pick_row(ch, name, pol)
        k['row'][name] = row
        if not row:
            continue
        sc = SCHOOL[name]
        fire, frost, arc = sc in ('fire', 'frostfire'), sc in ('frost', 'frostfire'), sc == 'arcane'
        k['avg'][name] = dd_avg(row, L, ch.dd_mode)
        rule = 'classic' if ch.below20 else ch.low_ranks
        k['coef'][name] = (ch.il_coef if name == 'IceLance' else row[4]) * coef_factor(row, L, rule)
        add = ai + (tv(ch, 'FirePower') if fire else 0) + (tv(ch, 'PiercingIce') if frost else 0)
        if name == 'ConeOfCold':
            add += tv(ch, 'ImprovedConeOfCold')
        k['smult'][name] = (1 + add) * ch.dmg_mult
        c = ch.crit + ch.crit_bonus + ai + (tv(ch, 'CriticalMass') if fire else 0) + (tv(ch, 'ArcaneImpact') if arc else 0)
        k['crit_dot'][name] = c
        if name in ('FireBlast', 'Scorch', 'ArcaneBlast', 'IceLance'):
            c += tv(ch, 'Incineration')
        k['crit'][name] = c
        bonus = (tv(ch, 'IceShards') if frost else 0) + (tv(ch, 'ArcaneMind', 'ArcaneMindCrit') if arc else 0)
        k['cm'][name] = 1 + 0.5 * (1 + bonus)
        k['hit'][name] = min(0.99, ch.hit_base + (tv(ch, 'ArcaneFocus') if arc else tv(ch, 'ElementalPrecision')))
        k['base_cost'][name] = row[5]
        k['cost'][name] = row[5] * (1 - (tv(ch, 'FrostChanneling') if frost else 0))
        ct = 0.0 if name in INSTANT or name == 'ArcaneMissiles' else row[6]
        if name == 'Frostbolt':
            ct -= tv(ch, 'ImprovedFrostbolt')
        if name in ('Fireball', 'FrostfireBolt'):
            ct -= tv(ch, 'ImprovedFireball')
        k['ct'][name] = max(0.0, ct) / ch.haste
        k['prot'][name] = tv(ch, 'BurningSoul') if fire else 0.0
    if k['row']['ArcaneMissiles']:
        k['prot']['ArcaneMissiles'] = tv(ch, 'ImprovedChanneling')
    if k['row']['ArcaneBlast']:
        k['prot']['ArcaneBlast'] = tv(ch, 'ImprovedChanneling', 'ImprovedChannelingAB')
    k['cd'] = dict(FireBlast=COOLDOWN['FireBlast'] - tv(ch, 'WakeOfFire'), ConeOfCold=COOLDOWN['ConeOfCold'],
                   FrostNova=COOLDOWN['FrostNova'] - tv(ch, 'ImprovedFrostNova'), BlastWave=COOLDOWN['BlastWave'])
    fb, pf = k['row']['Frostbolt'], tv(ch, 'Permafrost')
    k['chill_s'] = dict(Frostbolt=(FROSTBOLT_SLOW_S[fb[0]] if fb else 0) * (1 + pf), FrostfireBolt=9.0 * (1 + pf),
                        ConeOfCold=6.0 * (1 + pf))
    k['slow'] = 0.40 + tv(ch, 'Permafrost', 'PermafrostSlow')   # the chill's movement slow, Permafrost's extra
    k['p_cc'] = tv(ch, 'ArcaneConcentration')
    k['moe'] = tv(ch, 'MasterOfElements')
    k['ignite'] = tv(ch, 'Ignite')
    k['impact'] = tv(ch, 'Impact')
    k['isc'] = tv(ch, 'ImprovedScorch')
    k['fb_chance'] = tv(ch, 'Frostbite')
    k['fof_n'] = tv(ch, 'FingersOfFrost')
    k['wc_chance'] = tv(ch, 'WintersChill')
    k['wc_cap'] = T.get('WintersChill', 0)
    k['shatter'] = tv(ch, 'Shatter')
    k['hs'] = bool(T.get('HotStreak', 0) and k['row']['Pyroblast'])
    k['mb'] = bool(T.get('MissileBarrage', 0) and k['row']['ArcaneMissiles'])
    k['wake_crit'] = tv(ch, 'WakeOfFire', 'WakeOfFireCrit')
    k['wandspec'] = 1 + tv(ch, 'WandSpecialization')
    # range talents lengthen the pull: Arcane Geometry (Arcane), Flame Throwing (Fire), Arctic Reach (Frostbolt only,
    # +10/20% of its 30 yd range); the Frost Nova and Cone of Cold radius half of Arctic Reach is not modelled
    ag, ft, ar = tv(ch, 'ArcaneGeometry'), tv(ch, 'FlameThrowing'), 30.0 * tv(ch, 'ArcticReach')
    k['reach'] = {n: (ag if SCHOOL[n] == 'arcane' else 0.0) + (ft if SCHOOL[n] in ('fire', 'frostfire') else 0.0)
                  + (ar if n == 'Frostbolt' else 0.0) for n in TABLES}
    ibr = [r for r in ICE_BARRIER if r[0] <= L] if T.get('IceBarrier', 0) else []
    k['ib'] = math.floor(ibr[-1][1] + ibr[-1][2] * (min(L, ibr[-1][3]) - ibr[-1][0]) + 1e-9) if ibr else 0.0
    k['ib_cost'] = ibr[-1][4] if ibr else 0.0
    # shares of pulls a long cooldown is ready for (evaluate() sets them from a first pass); 0 without the talent
    k['p_pom'] = pol.get('p_pom', 0.0) if T.get('PresenceOfMind', 0) else 0.0
    k['p_ap'] = pol.get('p_ap', 0.0) if T.get('ArcanePower', 0) else 0.0
    k['p_comb'] = pol.get('p_comb', 0.0) if T.get('Combustion', 0) and L >= 40 else 0.0
    k['p_bf'] = pol.get('p_bf', 0.0) if ch.race == 'orc' else 0.0
    k['p_bz'] = pol.get('p_bz', 0.0) if ch.race == 'troll' else 0.0
    k['p_eu'] = pol.get('p_eu', 0.0) if ch.race == 'gnome' else 0.0
    k['p_ib'] = pol.get('p_ib', 0.0) if k['ib'] else 0.0
    k['wake'] = pol.get('wake', 0.0) if T.get('WakeOfFire', 0) else 0.0
    k['prio'] = list(pol['prio'])
    return k


def hold_q(holds, t, kind):
    """Chance the mob is held now: kind 1 freezes only (Frost Nova, Frostbite), 2 stuns only (Impact), 0 either,
    3 Frost Nova's root only. A hold is [end time, chance it holds, break chance per damage event, is a freeze,
    source ('nova', 'frostbite' or 'stun')]."""
    q = 1.0
    for h in holds:
        if h[0] > t and (kind == 0 or (kind == 3 and h[4] == 'nova') or (kind != 3 and (kind == 1) == h[3])):
            q *= 1 - h[1]
    return 1 - q


def simulate(ch, mob_hp, pol, max_time=MAX_TIME, phase=0.5, k=None):
    """One fight from a full mana and health pool until the mob dies, the Mage dies or max_time passes.
    phase: where the Frostbite, Fingers of Frost, Missile Barrage and Hot Streak accumulators start. Procs roll on
    every cast, so across a session the remainder a fight starts with is spread evenly over [0, 1) (Hot Streak's
    three stacks over [0, 3)); averaging fights started at evenly spread phases gives the expected proc count exactly
    (evaluate() gives each mob health multiple its own phase). Hot Streak stacks carry to the next pull: they last
    20 s, and 8 s of walking plus a few seconds of rest is shorter (ASSUMPTION: no expiry between pulls)."""
    k = k or fight_consts(ch, pol)     # fight_consts never changes during a fight, so callers may share it
    S = dict(casts={}, dmg={}, mana_spent=0.0, taken=0.0, absorbed=0.0, healed=0.0, dead=False)
    st = dict(t=0.0, hp=mob_hp, php=ch.max_hp, mana=ch.max_mana, absorb=0.0, gcd=0.0, wand=False, step=-1.0,
              last_spend=-99.0, engaged=False, pulled=False, ib_done=False, gap=ch.pull_gap,
              cd=dict(FireBlast=0.0, ConeOfCold=0.0, FrostNova=0.0, BlastWave=0.0),
              chill_until=-1.0, chill_p=0.0, daze_until=-1.0, daze_p=0.0, fb=phase if k['fb_chance'] else 0.0,
              fof=phase if k['fof_n'] else 0.0, wc=0.0, hs=3.0 * phase if k['hs'] else 0.0,
              mb=phase if k['mb'] else 0.0,
              cc=0.0, ab=0, ab_until=-1.0, fv=0.0, eu=3, comb_bonus=0.0, comb_crits=0.0, wake_used=False,
              pom_used=False, swing=0.0, armor_until=-1.0, shot_at=0.0)
    holds = []          # [end time, chance it holds, break chance per damage event, is a freeze]
    dots = {}
    ign = []            # [due time, amount, chance the tick exists] Ignite ticks
    cast, chan = [None], [None]

    def break_holds(p):
        """A damage event that happens with chance p may break a Frost Nova root (test m12)."""
        for h in holds:
            if h[2] > 0 and h[0] > st['t']:
                h[1] *= 1 - h[2] * p

    def chill_procs(p):
        """A chill that lands with chance p rolls Frostbite (a whole expected freeze fires once built up) and Fingers
        of Frost (a proc grants every charge)."""
        if k['fb_chance']:
            st['fb'] += p * k['fb_chance']
            if st['fb'] >= 1:
                st['fb'] -= 1
                holds.append([st['t'] + 5.0, 1.0, ch.fb_break, True, 'frostbite'])
        if k['fof_n']:
            st['fof'] = min(k['fof_n'], st['fof'] + p * FOF_CHANCE * k['fof_n'])

    def deal(name, x):
        st['hp'] -= x
        S['dmg'][name] = S['dmg'].get(name, 0.0) + x

    def heal(x):
        st['php'] = min(ch.max_hp, st['php'] + x)
        S['healed'] += x

    def totg_proc(hit):
        """Undead Touch of the Grave on a landed hit or wand shot: 10%, draining 5% of max health. Its 1 s proc
        cooldown (client SpellAuraOptions 243733) is not modelled: applied exactly, it changed Undead by 0.03%."""
        x = 0.1 * hit * 0.05 * ch.max_hp
        deal('TouchOfTheGrave', x)
        heal(x)

    def sp_now():
        return ch.sp * (1 + 0.1 * k['p_bf']) if st['t'] < 15.0 else ch.sp

    def ab_now():
        return st['ab'] if st['t'] <= st['ab_until'] else 0

    def cost_full(a):
        """Mana a cast costs before Clearcasting."""
        if a == 'Barrage':
            return 0.0
        if a == 'IceBarrier':           # cast before the pull, ahead of Arcane Power and Eureka!
            return k['ib_cost']
        name = 'Pyroblast' if a == 'HotPyro' else a
        c = AB_COST * ch.base_mana * (1 + 1.75 * ab_now()) if name == 'ArcaneBlast' else k['cost'][name]
        if st['t'] < 15.0:
            c *= 1 + 0.3 * k['p_ap']
        if st['eu'] > 0:
            c *= 1 - 0.1 * k['p_eu']
        return c

    def live(name, fire):
        """Multipliers that change during the fight: Arcane Power, Improved Scorch stacks."""
        m = 1 + 0.3 * k['p_ap'] if st['t'] < 15.0 else 1.0
        if fire:
            m *= 1 + FV_STEP * st['fv']
        return m

    def after_hit(name, hit, pcrit, cc_used, cost_paid_full):
        """Procs every landed direct hit or missile shares."""
        sc = SCHOOL[name]
        fire, frost = sc in ('fire', 'frostfire'), sc in ('frost', 'frostfire')
        st['engaged'] = True
        break_holds(hit)
        if k['p_cc']:
            st['cc'] = 1 - (1 - st['cc']) * (1 - hit * k['p_cc'])
        if k['moe'] and (fire or frost) and cost_paid_full > 0:
            st['mana'] = min(ch.max_mana, st['mana'] + k['base_cost'][name] * k['moe'] * hit * pcrit * (1 - cc_used))
        if ch.totg:
            totg_proc(hit)
        if fire and k['impact']:
            holds.append([st['t'] + 2.0, hit * k['impact'], 0.0, False, 'stun'])
        if frost and k['wc_cap']:
            st['wc'] = min(k['wc_cap'], st['wc'] + hit * k['wc_chance'])

    def land(name, cc_used, eu, cost_paid_full, missile=False):
        """Damage and procs of one landed cast (or one Arcane Missiles missile)."""
        t = st['t']
        sc = SCHOOL[name]
        fire = sc in ('fire', 'frostfire')
        hit = k['hit'][name]
        f = hold_q(holds, t, 1)
        if not missile and st['fof'] >= 1:         # Fingers of Frost: this cast counts as frozen
            st['fof'] -= 1
            f = 1.0
        c = k['crit'][name]
        if name in ('Frostbolt', 'IceLance'):
            c += WC_CRIT * st['wc']
        if fire and k['p_comb'] and st['comb_crits'] < COMB_CRITS:
            c += k['p_comb'] * st['comb_bonus']
        if name == 'FireBlast' and not st['wake_used'] and t < k['wake']:
            c += k['wake_crit']
            st['wake_used'] = True
        m = k['cm'][name]
        cn, cf = min(1.0, c), min(1.0, c + k['shatter'])
        il = 4.0 if name == 'IceLance' else 1.0
        x = (k['avg'][name] + k['coef'][name] * sp_now()) * k['smult'][name] * live(name, fire) * (1 + 0.1 * eu)
        if name in AB_MASK:
            x *= 1 + 0.1 * ab_now()
            st['ab'] = 0
        ev = (1 - f) * (1 + cn * (m - 1)) + f * il * (1 + cf * (m - 1))
        deal(name, x * hit * ev)
        pcrit = (1 - f) * cn + f * cf
        if fire and k['ignite']:
            owed = k['ignite'] * x * hit * m * pcrit
            ign.append([t + 2.0, owed / 2, hit * pcrit])
            ign.append([t + 4.0, owed / 2, hit * pcrit])
        if fire and k['p_comb'] and st['comb_crits'] < COMB_CRITS:
            st['comb_crits'] += hit * min(1.0, k['crit'][name] + st['comb_bonus'])
            st['comb_bonus'] += 0.1 * hit
        if name in HOT_STREAK_FROM and k['hs']:
            st['hs'] = min(3.0, st['hs'] + hit * pcrit)
        after_hit(name, hit, pcrit, cc_used, cost_paid_full)
        if missile:
            return
        if name in CHILLS:
            st['chill_until'] = t + k['chill_s'][name]
            st['chill_p'] = hit
            chill_procs(hit)
        if name == 'FrostNova':
            holds.append([t + 8.0, hit, ch.nova_break, True, 'nova'])
        if name == 'BlastWave':
            st['daze_until'], st['daze_p'] = t + 6.0, hit
        if name == 'Scorch' and k['isc']:
            st['fv'] = min(5.0, st['fv'] + hit * k['isc'])
        if name == 'ArcaneBlast':
            st['ab'] = min(4, ab_now() + 1)
            st['ab_until'] = t + 8.0
        if k['mb'] and name in BARRAGE:
            st['mb'] = min(1.0, st['mb'] + BARRAGE[name])
        if name in DOT_NAME:
            row = k['row'][name]
            per = (row[7] + row[10] * sp_now()) * k['smult'][name] * hit * (1 + min(1.0, k['crit_dot'][name]) * (m - 1))
            dots[name] = dict(next=t + row[9], left=row[8], per=per, period=row[9], fire=fire, p=hit)

    def tick_dots(t):
        for name in list(dots):
            d = dots[name]
            if t < d['next'] - 1e-9:
                continue
            deal(DOT_NAME[name], d['per'] * live(name, d['fire']))
            break_holds(d['p'])
            d['left'] -= 1
            d['next'] += d['period']
            if d['left'] <= 0:
                del dots[name]
        i = 0
        while i < len(ign):
            if t >= ign[i][0] - 1e-9:
                deal('Ignite', ign[i][1])
                break_holds(ign[i][2])
                ign.pop(i)
            else:
                i += 1

    def tick_channel(t):
        c = chan[0]
        if not c or t < c['next'] - 1e-9:
            return
        land('ArcaneMissiles', c['cc'], c['eu'], c['cost'], missile=True)
        c['left'] -= 1
        c['next'] += c['period']
        if c['left'] <= 0:
            chan[0] = None

    def act(a, t):
        if a == 'Wand':
            if not st['wand']:
                st['shot_at'] = t       # ASSUMPTION: the first shot leaves as wanding starts, then one every WAND_SPEED
            st['wand'] = True
            st['pulled'] = True
            return
        st['wand'] = False
        if a == 'Step':
            st['step'] = t + ch.step_s
            S['casts']['Step'] = S['casts'].get('Step', 0) + 1
            return
        full = cost_full(a)
        cc_used = st['cc'] if full > 0 else 0.0
        paid = full * (1 - cc_used)
        if full > 0:
            st['cc'] = 0.0
            st['last_spend'] = t
        st['mana'] -= paid
        S['mana_spent'] += paid
        S['casts'][a] = S['casts'].get(a, 0) + 1
        st['gcd'] = t + GCD
        if a == 'IceBarrier':
            st['ib_done'] = True
            st['absorb'] = k['ib'] * k['p_ib']
            return
        if not st['pulled']:               # the pull: range talents open a longer gap
            st['gap'] += k['reach']['Pyroblast' if a == 'HotPyro' else ('ArcaneMissiles' if a == 'Barrage' else a)]
        st['pulled'] = True
        eu = 0.0
        if st['eu'] > 0:
            eu = k['p_eu']
            st['eu'] -= 1
        if a == 'Barrage':
            st['mb'] -= 1
            row = k['row']['ArcaneMissiles']
            chan[0] = dict(next=t + 0.5, left=row[6], period=0.5, cc=0.0, eu=eu, cost=0.0, lost=0.0)
            return
        if a == 'ArcaneMissiles':
            row = k['row']['ArcaneMissiles']
            per = 1.0 / ch.haste
            if t < 10.0:
                per *= 1 - k['p_bz'] * (1 - 1 / 1.1)
            chan[0] = dict(next=t + per, left=row[6], period=per, cc=cc_used, eu=eu, cost=full, lost=0.0)
            return
        name = a
        if a == 'HotPyro':
            name = 'Pyroblast'
            st['hs'] -= 3
        if name in COOLDOWN:
            st['cd'][name] = t + k['cd'][name]
        ct = k['ct'][name] * (HOT_STREAK_CUT if a == 'HotPyro' else 1.0)
        if ct > 0 and t < 10.0:
            ct *= 1 - k['p_bz'] * (1 - 1 / 1.1)
        if ct > 0 and not st['pom_used']:
            st['pom_used'] = True
            ct *= 1 - k['p_pom']
        if ct > 0:
            cast[0] = dict(end=t + ct, name=name, cc=cc_used, eu=eu, cost=full)
        else:
            land(name, cc_used, eu, full)

    def mob_tick(t):
        """The mob closes the gap (slowed by the strongest slow, stopped while held), then hits while in melee."""
        if not st['engaged']:
            return
        qh = qs = 1.0                   # hold_q kinds 0 and 2 in one pass
        for h in holds:
            if h[0] > t:
                qh *= 1 - h[1]
                if not h[3]:
                    qs *= 1 - h[1]
        hold, stun = 1 - qh, 1 - qs
        chill = st['chill_p'] * k['slow'] if t < st['chill_until'] else 0.0
        daze = st['daze_p'] * 0.5 if t < st['daze_until'] else 0.0
        if t < st['step']:
            st['gap'] += ch.player_speed * DT
        st['gap'] = max(0.0, st['gap'] - ch.mob_speed * (1 - max(chill, daze)) * (1 - hold) * DT)
        if st['gap'] > 0:
            return
        swings = DT / ch.swing * (1 - stun) * (1 - ch.armor_slow if t < st['armor_until'] else 1.0)
        x = ch.mob_dps * ch.swing * swings
        if st['absorb'] > 0:
            a = min(st['absorb'], x)
            st['absorb'] -= a
            S['absorbed'] += a
            x -= a
        st['php'] -= x
        S['taken'] += x
        if ch.armor_chill:              # Frost or Ice Armor chills the attacker on each hit
            st['swing'] += swings
            if st['swing'] >= 1:
                st['swing'] -= 1
                st['armor_until'] = t + 5.0
                if ch.frostbite_armor:
                    chill_procs(1.0)
        if ch.pushback_s <= 0 or st['absorb'] > 0:
            return
        if cast[0]:                     # each hit delays a cast pushback_s (ASSUMPTION)
            cast[0]['end'] += ch.pushback_s * swings * (1 - k['prot'][cast[0]['name']])
        elif chan[0]:                   # and costs a channel one missile (gap register channelPushback)
            c = chan[0]
            c['lost'] += swings * (1 - k['prot']['ArcaneMissiles'])
            if c['lost'] >= 1:
                c['lost'] -= 1
                c['left'] -= 1
                if c['left'] <= 0:
                    chan[0] = None

    while st['hp'] > 0 and st['t'] < max_time:
        t = st['t']
        tick_dots(t)
        tick_channel(t)
        kc = cast[0]
        if kc and t >= kc['end'] - 1e-9:
            cast[0] = None
            land(kc['name'], kc['cc'], kc['eu'], kc['cost'])
        mob_tick(t)
        rate = ch.mreg if t >= st['last_spend'] + 5.0 else ch.mreg * ch.cast_regen
        st['mana'] = min(ch.max_mana, st['mana'] + rate * DT)
        if ch.hreg_combat:
            st['php'] = min(ch.max_hp, st['php'] + ch.hreg_combat * DT)
        busy = cast[0] is not None or chan[0] is not None or t < st['step'] - 1e-9
        if st['wand'] and not busy:
            hit = min(0.99, ch.hit_base)
            deal('Wand', ch.wand_dps * DT * hit * k['wandspec'] * ch.dmg_mult)
            if t >= st['shot_at'] - 1e-9:   # a shot leaves: a damage event (its damage is in the rate above)
                st['shot_at'] += WAND_SPEED
                if ch.wand_breaks:
                    break_holds(hit)
                if ch.totg and ch.totg_wand:
                    totg_proc(hit)
            st['engaged'] = True
        if not busy and st['hp'] > 0:
            if want_step(ch, st, holds, pol):   # walking needs no global cooldown
                act('Step', t)
            elif t >= st['gcd'] - 1e-9:
                act(choose(ch, pol, st, k, holds, mob_hp, cost_full), t)
        if st['php'] <= 0:
            S['dead'] = True
            break
        st['t'] += DT
    S['ttk'] = st['t']
    S['killed'] = st['hp'] <= 0
    S['feasible'] = S['killed'] and not S['dead']
    S['end_mana'] = st['mana']
    S['end_hp'] = st['php']
    S['last_spend'] = st['last_spend']
    return S


def ready(step, st, k):
    """Whether a priority step can be cast now, mana aside."""
    if step == 'Wand':
        return True
    if not k['row'].get(step):
        return False
    if step in COOLDOWN:
        return st['t'] >= st['cd'][step] - 1e-9
    if step == 'ArcaneBlast':        # build one stack, then the next step spends it
        return (st['ab'] if st['t'] <= st['ab_until'] else 0) < 1
    return True


def want_step(ch, st, holds, pol=None):
    """Root and step back (ASSUMPTION; kite allows it, the policy's 'step' chooses it): a mob held within 10 yd, so
    walk step_s seconds away. step 'none' never steps, 'nova' only after Frost Nova's root, 'all' after any freeze
    (Frostbite too). Without a policy it steps after any freeze, the v1 behaviour."""
    mode = 'all' if pol is None else pol.get('step', 'none')
    if not ch.kite or mode == 'none' or not st['engaged'] or st['gap'] >= MELEE_GAP:
        return False
    return hold_q(holds, st['t'], 3 if mode == 'nova' else 1) >= 0.5


def choose(ch, pol, st, k, holds, mob_hp, cost_full):
    """The next action when the Mage is free to act and the global cooldown is over."""
    t = st['t']

    def ok(a):                      # the first candidate, in the order below, that is the wand or affordable
        return a == 'Wand' or st['mana'] >= cost_full(a) * (1 - st['cc'])
    if not st['pulled']:            # the pull: a cast while the mob is still unaware of you
        if pol.get('ib') and k['ib'] and not st['ib_done'] and ok('IceBarrier'):
            return 'IceBarrier'
        if pol.get('pull') == 'Pyroblast' and k['row']['Pyroblast'] and ok('Pyroblast'):
            return 'Pyroblast'
        if pol.get('filler') and k['row'][pol['filler']] and ok(pol['filler']):
            return pol['filler']
    if k['row']['IceLance'] and (st['fof'] >= 1 or hold_q(holds, t, 1) >= 0.5) and ok('IceLance'):
        return 'IceLance'
    near = st['engaged'] and st['gap'] <= MELEE_GAP
    if pol.get('nova') and near and ready('FrostNova', st, k) and ok('FrostNova'):
        return 'FrostNova'
    if k['hs'] and st['hs'] >= 3 and ok('HotPyro'):
        return 'HotPyro'
    if k['mb'] and st['mb'] >= 1 and ok('Barrage'):
        return 'Barrage'
    if pol.get('melee') and near:
        for s in ('ConeOfCold', 'BlastWave', 'ArcaneExplosion'):
            if ready(s, st, k) and ok(s):
                return s
    if pol.get('fin') == 'Wand' and st['hp'] / mob_hp < FIN_BELOW:
        return 'Wand'
    for s in k['prio']:
        if ready(s, st, k) and ok(s):
            return s
    return 'Wand'


# ---------------------------------------------------------------- rest model (also used by models/aoe.py)
def conj_row(table, L):
    """The best conjured water or food rank at level L. Below its first rank the Mage is assumed to use the
    first rank's values (ASSUMPTION: bought water or food of the same size)."""
    rows = [r for r in table if r[0] <= L]
    return rows[-1] if rows else table[0]


def conj_count(row, L):
    """Bottles or loaves per Conjure cast at level L (client count at learn plus per level, to a stack of 20)."""
    return min(STACK, math.floor(row[4] + row[5] * (max(row[0], min(L, row[6])) - row[0]) + 1e-9))


def rest_setup(ch):
    """Rates and cooldown actions for resting at this character's level.

    Eating and drinking run at once, so rest takes the longer of the two. Spirit and natural health regeneration
    run on top when spirit_drink is on (the default: Classic regeneration only pauses for 5 s after spending mana).
    Each cooldown action is [name, seconds, mana, health, cooldown s, share of pulls it can be used on]; its time
    replaces drinking and eating (every one is a channel or cast), and rest_solve uses it only when that saves time.
    """
    L = ch.level
    w = MOUNTAIN_WATER if ch.mountain_water and L >= MOUNTAIN_WATER[0] else conj_row(WATER, L)
    f = conj_row(FOOD, L)
    scale = WOWHEAD_DRINK if ch.wowhead_drinks else 1.0
    d, e = w[1] / 5.0 * scale, f[1] / 5.0 * scale
    tot_w, tot_f = d * w[2], e * f[2]
    n_w, n_f = conj_count(w, L), conj_count(f, L)
    mreg, hreg = ch.mreg, ch.hreg
    stack = 1.0 if ch.spirit_drink else 0.0
    R = dict(d=d, e=e, D=d + mreg * stack, E=e + hreg * stack, kw=w[3] / (n_w * tot_w), kf=f[3] / (n_f * tot_f),
             tw=CONJURE_S / (n_w * tot_w), tf=CONJURE_S / (n_f * tot_f), water=w, food=f, acts=[])
    acts = R['acts']
    if ch.evocation and L >= 20:        # 8 s channel, regeneration x16 (+1500%) and full while channeling
        acts.append(['Evocation', 8.0, 8.0 * 16 * mreg, 8.0 * hreg, 480.0, 1.0])
    pot = [p for p in POTIONS if p[0] <= L] if ch.potions else []
    if pot:
        acts.append(['ManaPotion', 0.0, pot[-1][1], 0.0, 120.0, 1.0])
    gem = [g for g in GEMS if g[0] <= L] if ch.gems else []
    if gem:                             # conjured (3 s, its mana cost drunk back) then used: net mana is negative
        acts.append(['ManaGem', CONJURE_S, gem[-1][2] - gem[-1][1], 0.0, 120.0, 1.0])
    if ch.cannibalize > 0:              # 7% health and mana every 2 s for 10 s, 2 min, humanoid or undead corpse
        acts.append(['Cannibalize', 10.0, 0.35 * ch.max_mana + 10.0 * mreg, 0.35 * ch.max_hp + 10.0 * hreg, 120.0,
                     ch.cannibalize])
    if ch.rapid_regen:                  # 50% max health over a 6 s channel, 3 min
        acts.append(['RapidRegeneration', 6.0, 6.0 * mreg, 0.5 * ch.max_hp + 6.0 * hreg, 180.0, 1.0])
    if ch.leyline == 'short':           # 2 s cast, +100% regeneration for 15 s, 2 min
        acts.append(['ReadLeyLine', 2.0, (2.0 + 15.0 * stack) * mreg, (2.0 + 15.0 * stack) * hreg, 120.0, 1.0])
    return R


def travel_regen(ch, ttk, last_spend, travel):
    """(mana, health) regenerated walking to the next mob: mana resumes 5 s after the last mana spent."""
    return ch.mreg * max(0.0, min(travel, ttk + travel - (last_spend + 5.0))), ch.hreg * travel


def rest_time(R, M, H, use, spk):
    """Seconds of rest per kill to cover M mana and H health, with the cooldown actions in `use` each used on
    (spk / cooldown) x share of pulls. Conjuring costs a 3 s cast per stack and its mana, both paid by resting."""
    ta = am = bh = 0.0
    for a in use:
        u = a[5] * spk / a[4]
        ta += u * a[1]
        am += u * a[2]
        bh += u * a[3]
    mr, hr = max(0.0, M - am), max(0.0, H - bh)
    te = hr / R['E']
    eaten = R['e'] * te
    td = (mr + R['kf'] * eaten) / (R['D'] - R['kw'] * R['d'])
    tc = R['tw'] * R['d'] * td + R['tf'] * eaten
    return ta + tc + max(td, te)


def rest_solve(R, F, M, H, iters=40):
    """Seconds per kill and rest for a kill cycle of F seconds (fight plus walking) that leaves M mana and H health
    to restore. Every subset of the cooldown actions is tried (an action that restores nothing is skipped); a kill
    cycle spk uses each action (spk / cooldown) times, so spk = F + rest(spk) is solved by fixed-point iteration.
    A subset counts MIN_SAVE seconds against each use, so an action is only used when it saves at least that much
    (ASSUMPTION: nobody drinks a potion to save a tenth of a second of conjuring).
    Returns the fastest: dict(spk, rest, uses={name: uses per kill}, drink, eat)."""
    acts = [a for a in R['acts'] if a[2] > 0 or a[3] > 0]
    best = None
    for mask in range(1 << len(acts)):
        use = [acts[i] for i in range(len(acts)) if mask >> i & 1]
        spk = F + rest_time(R, M, H, use, F)
        for _ in range(iters):
            nxt = F + rest_time(R, M, H, use, spk)
            done = abs(nxt - spk) <= 1e-12 * spk
            spk = nxt
            if done:
                break
        score = spk + MIN_SAVE * add_up(a[5] * spk / a[4] for a in use)
        if best is None or score < best[2] - 1e-9:
            best = (spk, use, score)
    spk, use = best[0], best[1]
    uses = {a[0]: a[5] * spk / a[4] for a in use}
    am = add_up(uses[a[0]] * a[2] for a in use)
    bh = add_up(uses[a[0]] * a[3] for a in use)
    te = max(0.0, H - bh) / R['E']
    td = (max(0.0, M - am) + R['kf'] * R['e'] * te) / (R['D'] - R['kw'] * R['d'])
    return dict(spk=spk, rest=spk - F, uses=uses, drink=td, eat=te)


# ---------------------------------------------------------------- per kill
def seconds_per_kill(ch, mob_hp, pol, travel=8.0, phase=0.5, k=None, R=None):
    """Fight, then walk `travel` seconds to the next mob, then rest back to full: seconds per kill."""
    s = simulate(ch, mob_hp, pol, MAX_TIME, phase, k)
    tm, th = travel_regen(ch, s['ttk'], s['last_spend'], travel)
    M = max(0.0, ch.max_mana - s['end_mana'] - tm - ch.thrill * ch.max_mana)
    H = ch.max_hp if s['dead'] else max(0.0, ch.max_hp - s['end_hp'] - th - ch.thrill * ch.max_hp)
    r = rest_solve(R or rest_setup(ch), s['ttk'] + travel, M, H)
    s['rest'], s['spk'], s['uses'] = r['rest'], r['spk'], r['uses']
    s['drink'], s['eat'] = r['drink'], r['eat']
    s['pots'] = r['uses'].get('ManaPotion', 0.0)
    s['evo'] = r['uses'].get('Evocation', 0.0)
    return s
