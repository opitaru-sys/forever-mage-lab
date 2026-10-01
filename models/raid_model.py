"""Forever Mage raid model: a level 60 Mage against a level 63 boss, expected values over a finite fight.

The reference that model.js ports (tests/parity_test.js, tests/raid_options_test.js, tests/weights_test.js hold
values generated here by tests/make_raid_fixtures.py). analysis/raid_check.py rolls the dice for the same plans;
docs/raid-model.md has the method and every assumption.

Method:
  1. Character: spell power, crit, hit per school, mana pool, regen while casting, haste, from the options and
     the talent build {key: rank} (data/talents.json keys).
  2. Actions. Every castable spell and rank becomes an action with expected damage, time and mana per use.
     An action carries its own procs as expected follow-up casts: Fingers of Frost Ice Lances, Missile Barrage
     Arcane Missiles, Hot Streak Pyroblasts, Clearcasting and Master of Elements mana, Ignite. Arcane Blast
     is cast in cycles: n Arcane Blasts, a spender that takes the stacks, then Arcane Missiles if Barrage
     came up. Cooldown spells (Fire Blast, Blast Wave, Presence of Mind, Evocation) are actions with a cap.
  3. Mana: the pool, regen while casting, potions, runes and gems on a schedule (room for each is opened with the
     top action from the pull; what arrives too late to spend is stranded), Evocation as an action, Eureka.
  4. A linear program: split the rest of the fight's time across actions to maximise damage, with the mana
     spent no more than the budget. Two constraints, so the optimum mixes at most two uncapped actions; it is
     found by enumerating vertices over the upper hull of the uncapped actions, which ports to JavaScript as is.
  5. Fight-level effects that depend on the plan (Winter's Chill ramp, Hot Streak's chance of keeping its stacks,
     Pyroblast DoT overlap, Eureka!, cooldown drift) come from a damped fixed-point loop of ITERATIONS passes.
     Combustion is booked after the program (a fixed number of extra crits per press at the plan's value of a Fire
     crit), so it cannot feed back into the plan.

Options use the page's names (DEFAULTS below). Every number carries its source; guesses say ASSUMPTION.
"""
import json
import math
import os

# ---------------------------------------------------------------- character constants
GCD = 1.5
BASE_MANA = 1213            # Mage base mana at 60: sim core/base_stats_auto_gen.go ExtraClassBaseStats (client table)
INT_MANA = 15               # sim core/mana.go: 15 mana per Intellect ...
INT_MANA_OFFSET = -280      # ... except the first 20, which give 1 each (20 - 15 x 20)
CRIT_PER_INT = 0.000168     # sim core/base_stats_auto_gen.go CritPerIntMaxLevel Mage: 0.0168% crit per Intellect
SPIRIT_BASE = 6.25          # sim core/mana.go: mages regen 12.5 + Spirit/4 per 2 s tick outside the 5 second rule
SPIRIT_PER = 1.0 / 8
MAGE_ARMOR = 0.5            # Mage Armor rank 3 (22783): 50% of regen continues while casting (client; NOTES c)
HIT_GAP = 0.16              # Classic table vs a level 63 boss: 17% miss, 1% floor. UNVERIFIED for Forever
                            # (FINDINGS 3). As on the Warlock page, capped hit counts as 100% landed.
CRIT_BONUS = 0.5            # spell crits deal 150% (sim core/spell.go base multiplier 1.5)
LEVEL_RESIST = 0.94         # levelResist: the sim's 6% average partial resist vs level 63 on non-binary spells
                            # (sim core/spell_resistances.go:81 and :96-101, 2% a level). On by default, as the sim;
                            # the Warlock page does not apply it.
AB_COST = 0.15 * BASE_MANA  # Arcane Blast costs 15% of base mana (client 1239700); 181.95, rounding UNVERIFIED
AB_STACK_COST = 1.75        # Arcane Blast buff 400573: +175% Arcane Blast cost per stack (client)
AB_STACK_DMG = 0.10         # and +10% damage to other spells per stack, 4 stacks, 8 s (client)
AP_DMG, AP_COST, AP_DUR, AP_CD = 0.30, 0.30, 15.0, 180.0      # Arcane Power 12042 (client, NOTES a)
POM_CD = 180.0                                                 # Presence of Mind 12043
COMB_CD, COMB_CRIT, COMB_CRITS, COMB_MAX = 180.0, 0.10, 4, 10  # Combustion: +10% per Fire hit, 4 crits, 10 stacks (sim)
FV_PER_STACK, FV_STACKS = 0.03, 5                              # Fire Vulnerability 22959, 30 s (FINDINGS 3)
FV_REFRESH = 27.0           # ASSUMPTION: one Scorch every 27 s keeps a 30 s debuff (the sim refreshes at 5 s left)
HS_WINDOW = 20.0            # Hot Streak 400625 lasts 20 s since build 70009 (FC-PN); 3 stacks, -25% Pyroblast cast each
WC_PER_STACK, WC_WINDOW = 0.02, 15.0   # Winter's Chill 12579: +2% crit per stack, 15 s (sim spell store)
FOF_CHANCE = 0.15           # Fingers of Frost: 15% per landed chill at both ranks (curve; sim talents_frost.go)
IL_FROZEN = 4.0             # Ice Lance x4 on a frozen target, whole hit (sim ice_lance.go)
MB_AB, MB_OTHER = 0.40, 0.20  # Missile Barrage from Arcane Blast / Fireball, Frostbolt, Frostfire Bolt (sim)
EVO_TIME, EVO_CD, EVO_MULT = 8.0, 480.0, 16.0   # Evocation: 8 s channel, 8 min, +1500% regen (client 12051)
EVO_LAG = 30.0              # ASSUMPTION: the first Evocation is not before 30 s (the pool must have room)
ITEM_CD = 120.0             # potions (category 4) and gems or runes (category 1153), 2 min each (client)
POTION_MANA, POTION_MAX = (1350 + 2250) / 2.0, 2250.0   # Major Mana Potion 13444: 1350 to 2250
RUNE_MANA, RUNE_MAX = (900 + 1500) / 2.0, 1500.0        # Demonic Rune 12662 / Dark Rune 20520: 900 to 1500
GEMS = (1100.0, 850.0, 600.0, 400.0)   # Mana Ruby, Citrine, Jade, Agate averages; one of each (client)
BLAST_SP, BLAST_DUR = 47.0, 30.0       # Major Spellblasting Potion 250937: +47 spell damage 30 s (Wowhead)
EUREKA = 0.10               # Gnome Eureka!: next 3 damaging spells +10% damage, -10% cost, 2 min (FC-PN, WH)
TOTG_CHANCE, TOTG_HP = 0.10, 0.05      # Undead caster Touch of the Grave 1260201, 1 s cooldown (WH, CSV)
WAND_SPEC = (0.0, 0.13, 0.25)   # Wand Specialization +13/25% wand damage (curve, data/talents.json)
# Raid buffs, Forever tooltips (nether.wowhead.com/forever/tooltip/spell/ID, fetched 1 Oct 2026). ForeverChanges'
# racials data (foreverchanges.pro/racials) has Paladins and Shamans on both factions (Undead Paladin, Dwarf Shaman).
GBOW_MP5 = 40.0             # Greater Blessing of Wisdom rank 2 (25918): 40 mana every 5 s, 1 hour (Classic 33)
MANA_SPRING_MP5 = 25.0      # Mana Spring Totem rank 4 (10497): 10 mana every 2 s, party only
PRAYER_SPIRIT = 40.0        # Prayer of Spirit rank 1 (27681): +40 Spirit, party and raid
GOTW_STAT = 16.0            # Gift of the Wild rank 2 (21850): +16 all attributes, party and raid (Classic 12)
MAGEBLOOD_MP5 = 12.0        # Mageblood Elixir (20007): 12 mana every 5 s, 1 hour
KINGS = 0.10                # Greater Blessing of Kings (25898): total stats +10%, 1 hour; one Blessing per Paladin
MOONKIN_CRIT = 0.03         # Moonkin Form (24858): party members within 45 yd +3% critical strike chance
FIVE_SEC = 5.0              # the five-second rule: full Spirit regen once 5 s pass without spending mana
IDLE_BLOCK = 15.0           # ASSUMPTION: a Mage waits out mana in 15 s blocks (wanding); the first 5 s of each
                            # regen at the casting rate, so idle regen runs at (15 - 5) / 15 of full
ITERATIONS = 10             # fixed-point passes (convergence checked in tests/make_raid_fixtures.py)
DAMP, DAMP_FROM = 0.5, 2    # damping of the plan-dependent state from the third pass on
TOP_BAND = 0.99             # the opening action: the fastest spender within 1% of the best damage per second
GEM_ROOM = 1200.0 / 1100.0  # a gem needs room for its top roll (Ruby 1000 to 1200)
EPS = 1e-9

# ---------------------------------------------------------------- spell data at level 60
# data/mage_spells.json (client 1.60.1.69893; check_data() re-reads the file). Row:
# [rank, spell id, level learned, cast ms, mana, cooldown ms, average damage at 60, coefficient]
# then for a DoT [damage per tick, ticks, period ms, coefficient per tick]; Arcane Missiles [missiles, channel ms].
SPELL_ROWS = {
    'frostbolt': [
        [1, 116, 4, 1500, 25, 0, 21, 0.407], [2, 205, 8, 1800, 35, 0, 35, 0.489],
        [3, 837, 14, 2200, 50, 0, 49, 0.597], [4, 7322, 20, 2600, 65, 0, 64, 0.706],
        [5, 8406, 26, 3000, 100, 0, 101, 0.814], [6, 8407, 32, 3000, 130, 0, 140, 0.814],
        [7, 8408, 38, 3000, 160, 0, 189, 0.814], [8, 10179, 44, 3000, 195, 0, 253, 0.814],
        [9, 10180, 50, 3000, 225, 0, 318, 0.814], [10, 10181, 56, 3000, 260, 0, 397, 0.814],
        [11, 25304, 60, 3000, 290, 0, 475, 0.814]],
    'fireball': [
        [1, 133, 1, 1500, 30, 0, 20, 0.429, 1, 2, 2000, 0.0], [2, 143, 6, 2000, 45, 0, 39, 0.571, 1, 3, 2000, 0.0],
        [3, 145, 12, 2500, 65, 0, 56, 0.714, 2, 3, 2000, 0.0], [4, 3140, 18, 3000, 95, 0, 78, 0.857, 3, 4, 2000, 0.0],
        [5, 8400, 24, 3500, 140, 0, 114, 1.0, 4, 4, 2000, 0.0], [6, 8401, 30, 3500, 185, 0, 160, 1.0, 6, 4, 2000, 0.0],
        [7, 8402, 36, 3500, 220, 0, 196, 1.0, 6, 4, 2000, 0.0], [8, 10148, 42, 3500, 260, 0, 243, 1.0, 8, 4, 2000, 0.0],
        [9, 10149, 48, 3500, 305, 0, 309, 1.0, 10, 4, 2000, 0.0], [10, 10150, 54, 3500, 350, 0, 384, 1.0, 12, 4, 2000, 0.0],
        [11, 10151, 60, 3500, 395, 0, 451, 1.0, 14, 4, 2000, 0.0], [12, 25306, 60, 3500, 410, 0, 483, 1.0, 15, 4, 2000, 0.0]],
    'frostfire': [
        [1, 401502, 40, 3000, 205, 0, 110, 0.814, 9, 3, 3000, 0.0], [2, 1237312, 50, 3000, 285, 0, 195, 0.814, 13, 3, 3000, 0.0],
        [3, 1237313, 60, 3000, 370, 0, 292, 0.814, 19, 3, 3000, 0.0]],
    'scorch': [
        [1, 2948, 22, 1500, 50, 0, 42, 0.429], [2, 8444, 28, 1500, 65, 0, 59, 0.429], [3, 8445, 34, 1500, 80, 0, 73, 0.429],
        [4, 8446, 40, 1500, 100, 0, 97, 0.429], [5, 10205, 46, 1500, 115, 0, 121, 0.429],
        [6, 10206, 52, 1500, 135, 0, 156, 0.429], [7, 10207, 58, 1500, 150, 0, 181, 0.429]],
    'arcaneMissiles': [
        [1, 5143, 8, 0, 85, 0, 25, 0.286, 3, 3000], [2, 5144, 16, 0, 140, 0, 32, 0.286, 4, 4000],
        [3, 5145, 24, 0, 235, 0, 46, 0.286, 5, 5000], [4, 8416, 32, 0, 320, 0, 68, 0.286, 5, 5000],
        [5, 8417, 40, 0, 410, 0, 97, 0.286, 5, 5000], [6, 10211, 48, 0, 500, 0, 133, 0.286, 5, 5000],
        [7, 10212, 56, 0, 595, 0, 174, 0.286, 5, 5000], [8, 25345, 56, 0, 655, 0, 209, 0.286, 5, 5000]],
    'fireBlast': [[7, 10199, 54, 0, 340, 8000, 453, 0.429]],
    'arcaneBlast': [[5, 1239700, 60, 2500, 0, 0, 394, 0.714]],     # mana: AB_COST (15% of base mana)
    'iceLance': [[6, 1240047, 56, 0, 160, 0, 148, 0.0]],            # coefficient: the iceLanceCoef option
    'pyroblast': [[8, 18809, 60, 6000, 440, 0, 583, 1.0, 53, 4, 3000, 0.15]],
    'blastWave': [[5, 13021, 60, 0, 545, 45000, 493, 0.129]],
}
# school, binary (the sim's SpellFlagBinary: no partial resists), Hot Streak builder, chill (Fingers of Frost),
# Missile Barrage chance, and the rank that comes from a looted tome (NOTES a: Tome of Frostbolt XI etc.)
SPELL_META = {
    'frostbolt': {'name': 'Frostbolt', 'school': 'frost', 'binary': True, 'hs': False, 'chill': True, 'mb': MB_OTHER, 'tome': 11},
    'fireball': {'name': 'Fireball', 'school': 'fire', 'binary': False, 'hs': True, 'chill': False, 'mb': MB_OTHER, 'tome': 12},
    'frostfire': {'name': 'Frostfire Bolt', 'school': 'frostfire', 'binary': False, 'hs': True, 'chill': True, 'mb': MB_OTHER, 'tome': 0},
    'scorch': {'name': 'Scorch', 'school': 'fire', 'binary': False, 'hs': True, 'chill': False, 'mb': 0.0, 'tome': 0},
    'arcaneMissiles': {'name': 'Arcane Missiles', 'school': 'arcane', 'binary': False, 'hs': False, 'chill': False, 'mb': 0.0, 'tome': 8},
    'fireBlast': {'name': 'Fire Blast', 'school': 'fire', 'binary': False, 'hs': True, 'chill': False, 'mb': 0.0, 'tome': 0},
    'arcaneBlast': {'name': 'Arcane Blast', 'school': 'arcane', 'binary': False, 'hs': False, 'chill': False, 'mb': MB_AB, 'tome': 0},
    'iceLance': {'name': 'Ice Lance', 'school': 'frost', 'binary': True, 'hs': False, 'chill': False, 'mb': 0.0, 'tome': 0},
    'pyroblast': {'name': 'Pyroblast', 'school': 'fire', 'binary': False, 'hs': False, 'chill': False, 'mb': 0.0, 'tome': 0},
    'blastWave': {'name': 'Blast Wave', 'school': 'fire', 'binary': True, 'hs': False, 'chill': False, 'mb': 0.0, 'tome': 0},
}
FILLERS = ('frostbolt', 'fireball', 'frostfire', 'scorch', 'arcaneMissiles')
FIRE_SPELLS = ('fireball', 'frostfire', 'scorch', 'fireBlast', 'pyroblast', 'blastWave')   # frostfire: ASSUMPTION
AP_TO_SHATTER = (0.0, 0.17, 0.33, 0.50)          # Shatter per rank (curve)
AMED = (0.0, 0.17, 0.33, 0.50)                   # Arcane Meditation per rank (curve)
ISCORCH = (0.0, 0.33, 0.67, 1.0)                 # Improved Scorch apply chance per rank (curve)

DEFAULTS = {
    'sp': 500, 'crit': 0.10, 'gearHit': 0.11, 'int': 300, 'spirit': 120, 'mp5': 0,
    'race': 'none', 'sword': True, 'maxHp': 4000, 'fightLength': 300, 'fireImmune': False, 'targets': 1,
    'potion': 'mana', 'runes': True, 'gems': True, 'mageblood': True, 'raidBuffs': 'all', 'kings': True,
    'moonkin': False, 'wandDps': 57,
    'iceLanceCoef': 0.143, 'abMask': 'client', 'amSpends': False, 'regenStack': 'add', 'evocation': 1.0,
    'igniteMunch': 0.0, 'downrank': 'top', 'topRanks': False, 'levelResist': True, 'mbRate': 1.0,
    'iceLanceBinary': True, 'fingersOnBoss': True,
}


def opt(o, k):
    v = o.get(k) if o else None
    return DEFAULTS[k] if v is None else v


def uses(cd, T, lag=0.0):
    """Casts of a cooldown in a fight of T seconds, the first at `lag`."""
    if T <= lag:
        return 0
    return int(math.floor((T - lag) / cd)) + 1


def press_left(cd, T):
    """Seconds left in the fight after each press of a cooldown used on cooldown from the pull."""
    return [T - k * cd for k in range(uses(cd, T))]


def eureka_casts(T, casts):
    """Eureka! spells a fight holds: 3 per press, fewer when the fight ends before 3 more casts."""
    rate = casts / T if T > 0 else 0.0
    return sum(min(3.0, left * rate) for left in press_left(ITEM_CD, T))


def uptime(dur, cd, T):
    """Share of the fight a buff of `dur` seconds on a `cd` cooldown from the pull is up."""
    up = 0.0
    for k in range(uses(cd, T)):
        up += min(dur, T - k * cd)
    return up / T


def fire_ish(sch):
    return sch == 'fire' or sch == 'frostfire'


def frost_ish(sch):
    return sch == 'frost' or sch == 'frostfire'


# ---------------------------------------------------------------- character and fight context
def context(o, tal, fv_plan, state):
    """Everything a cast needs. state: the fixed-point variables from the previous pass."""
    def r(k):
        return tal.get(k, 0) or 0
    T = float(opt(o, 'fightLength'))
    race = opt(o, 'race')
    fire_ok = not opt(o, 'fireImmune')
    buffs = opt(o, 'raidBuffs')                   # 'all', 'noTotem' (no Shaman in your group) or 'none'
    b_mp5 = (GBOW_MP5 + (MANA_SPRING_MP5 if buffs == 'all' else 0.0)) if buffs != 'none' else 0.0
    b_spirit = PRAYER_SPIRIT + GOTW_STAT if buffs != 'none' else 0.0
    b_int = GOTW_STAT if buffs != 'none' else 0.0
    int_in = float(opt(o, 'int'))                 # the sheet, own Arcane Brilliance included, raid buffs not
    kings = 1 + KINGS if (buffs != 'none' and opt(o, 'kings')) else 1.0   # a Paladin's Blessing, like Wisdom
    int0 = (int_in + b_int) * kings
    int_eff = int0 * (1 + 0.02 * r('ArcaneMind'))
    crit = float(opt(o, 'crit')) + (int_eff - int_in) * CRIT_PER_INT + 0.01 * r('ArcaneInstability')
    if race == 'human' and opt(o, 'sword'):
        crit += 0.02                                  # Human Sword Specialization: +2% crit with a sword
    if opt(o, 'moonkin'):
        crit += MOONKIN_CRIT                          # Moonkin Form in your party
    spirit = (float(opt(o, 'spirit')) + b_spirit) * kings * (1.05 if race == 'human' else 1.0)   # The Human Spirit
    max_mana = (BASE_MANA + INT_MANA_OFFSET + INT_MANA * int_eff) * (1.05 if race == 'gnome' else 1.0)
    sp = float(opt(o, 'sp'))
    potion = opt(o, 'potion')
    u_pot = uptime(BLAST_DUR, ITEM_CD, T) if potion == 'blast' else 0.0
    if race == 'orc':          # Blood Fury: +10% spell power 15 s every 2 min; inside the potion's 30 s windows
        u_bf = uptime(15.0, 120.0, T)
        sp = sp * (1 + 0.10 * u_bf) + BLAST_SP * (u_pot + 0.10 * min(u_bf, u_pot))
    else:
        sp = sp + BLAST_SP * u_pot
    haste = 1.0
    if race == 'skyborne':
        haste = 1.01                                  # Wind Blessed: +1% haste
    if race == 'troll':
        haste = 1 + 0.10 * uptime(10.0, 180.0, T)     # Berserking: flat 10% for 10 s, 3 min
    gear_hit = float(opt(o, 'gearHit'))

    def landed(th):
        return 1 - max(0.0, HIT_GAP - gear_hit - th)
    ep = 0.01 * r('ElementalPrecision')
    h = {'arcane': landed(0.01 * r('ArcaneFocus')), 'fire': landed(ep), 'frost': landed(ep), 'frostfire': landed(ep)}
    spirit_regen = SPIRIT_BASE + spirit * SPIRIT_PER
    am = AMED[r('ArcaneMeditation')]
    stack = opt(o, 'regenStack')
    if stack == 'full':            # no five-second rule at all (test m14)
        frac = 1.0
    elif stack == 'add':           # Mage Armor and Arcane Meditation add up (the sim)
        frac = min(1.0, MAGE_ARMOR + am)
    else:                          # 'max': they do not add; the larger one counts
        frac = max(MAGE_ARMOR, am)
    mp5 = float(opt(o, 'mp5')) + b_mp5 + (MAGEBLOOD_MP5 if opt(o, 'mageblood') else 0.0)
    regen_cast = mp5 / 5 + spirit_regen * frac
    # idle time (a wand, no mana spent) regens in full once the five-second rule clears, in IDLE_BLOCK blocks
    idle_gain = spirit_regen * (1 - frac) * (IDLE_BLOCK - FIVE_SEC) / IDLE_BLOCK
    wand = float(opt(o, 'wandDps')) * (1 + WAND_SPEC[r('WandSpecialization')]) * landed(0.0) \
        * (LEVEL_RESIST if opt(o, 'levelResist') else 1.0)
    u_ap = uptime(AP_DUR, AP_CD, T) if r('ArcanePower') else 0.0
    wc = r('WintersChill')
    return {
        'o': o, 'tal': tal, 'T': T, 'race': race, 'fire_ok': fire_ok, 'fv': fv_plan, 'state': state,
        'sp': sp, 'crit': crit, 'spirit': spirit, 'max_mana': max_mana, 'haste': haste, 'h': h,
        'spirit_regen': spirit_regen, 'regen_cast': regen_cast, 'mp5': mp5, 'u_ap': u_ap,
        'idle_gain': idle_gain, 'wand': wand, 'am_spends': bool(opt(o, 'amSpends')),
        'cc': 0.02 * r('ArcaneConcentration'),
        'moe': 0.10 * r('MasterOfElements'),
        'ignite': (0.08 * r('Ignite') * (1 - float(opt(o, 'igniteMunch')))) if fire_ok else 0.0,
        'wc_avg': (WC_PER_STACK * wc if state['wc_avg'] is None else state['wc_avg']) if wc else 0.0,
        'eta': state['eta'],
        'pyro_ticks': state['pyro_ticks'],
        'mb': float(opt(o, 'mbRate')) if r('MissileBarrage') else 0.0,
        'fof': r('FingersOfFrost') if (r('IceLance') and r('FingersOfFrost') and opt(o, 'fingersOnBoss')) else 0,
        'il_binary': bool(opt(o, 'iceLanceBinary')),
        'shatter': AP_TO_SHATTER[r('Shatter')],
        'hs': 1 if (r('HotStreak') and r('Pyroblast') and fire_ok) else 0,
        'resist': opt(o, 'levelResist'),
        'downrank': opt(o, 'downrank'),
        'tomes': opt(o, 'topRanks'),
        'il_coef': float(opt(o, 'iceLanceCoef')),
        'ab_tooltip': opt(o, 'abMask') == 'tooltip',
        'r': r,
    }


def crit_of(S, key, sch, frozen):
    r = S['r']
    c = S['crit']
    if fire_ish(sch):
        c += 0.02 * r('CriticalMass')
    if sch == 'arcane':
        c += 0.02 * r('ArcaneImpact')
    if key in ('fireBlast', 'scorch', 'arcaneBlast', 'iceLance'):
        c += 0.02 * r('Incineration')
    if key == 'frostbolt' or key == 'iceLance':
        c += S['wc_avg']
    if frozen:
        c += S['shatter']
    return min(1.0, c)


def crit_bonus(S, sch):
    r = S['r']
    b = 1.0
    if frost_ish(sch):
        b += 0.2 * r('IceShards')
    if sch == 'arcane':
        b += 0.2 * r('ArcaneMind')
    return CRIT_BONUS * b


def flat_mult(S, sch, stacks):
    """The additive damage bucket (the sim's DamageDone_Flat mods add up)."""
    r = S['r']
    b = 1 + 0.01 * r('ArcaneInstability') + AP_DMG * S['u_ap'] + AB_STACK_DMG * stacks
    if fire_ish(sch):
        b += 0.02 * r('FirePower')
    if frost_ish(sch):
        b += 0.02 * r('PiercingIce')
    return b


def is_binary(S, key):
    """No partial resists: the sim's binary flag; Ice Lance's is an option (iceLanceBinary)."""
    if key == 'iceLance':
        return S['il_binary']
    return SPELL_META[key]['binary']


def pct_mult(S, sch, binary):
    m = 1.0
    if S['fv'] and fire_ish(sch):
        m *= 1 + FV_PER_STACK * FV_STACKS
    if S['resist'] and not binary:
        m *= LEVEL_RESIST
    return m


def cost_mult(S, sch):
    m = 1 + AP_COST * S['u_ap']
    if frost_ish(sch):
        m -= 0.05 * S['r']('FrostChanneling')
    return m


def coef_of(S, key, row, coef):
    if key == 'iceLance':
        return S['il_coef']
    return coef


def cast_time(S, key, row):
    r = S['r']
    ms = row[3]
    if ms <= 0:
        return GCD
    sec = ms / 1000.0
    if key == 'frostbolt':
        sec -= 0.1 * r('ImprovedFrostbolt')
    if key == 'fireball' or key == 'frostfire':
        sec -= 0.1 * r('ImprovedFireball')
    return max(GCD, sec / S['haste'])


def new_counters():
    return {'casts': 0.0, 'landed': 0.0, 'direct': 0.0, 'cost': 0.0, 'fireHits': 0.0, 'fireCrit': 0.0,
            'fireCritValue': 0.0, 'frostHits': 0.0, 'hsCasts': 0.0, 'hsHits': 0.0, 'hsCrit': 0.0, 'pyros': 0.0,
            'pyroTime': 0.0,
            'time': 0.0, 'time2': 0.0}


def new_action(name, cap=None, spec=None):
    """spec: what the action casts, for analysis/raid_check.py (kind filler, cycle, cd, pom, evo, idle)."""
    return {'name': name, 'd': 0.0, 't': 0.0, 'm': 0.0, 'cap': cap, 'parts': {}, 'n': new_counters(), 'mainCast': 0.0,
            'spec': spec or {}}


def add_cast(act, cast, w):
    """Add w expected casts of `cast` (a cast result) to an action."""
    if w <= 0:
        return
    for k, v in cast['parts'].items():
        act['parts'][k] = act['parts'].get(k, 0.0) + w * v
        act['d'] += w * v
    act['t'] += w * cast['t']
    act['m'] += w * cast['m']
    for k, v in cast['n'].items():
        act['n'][k] += w * v


def add_action(act, sub, w):
    """Add w uses of a sub-action (a cast and its procs) to an action."""
    if w <= 0:
        return
    for k, v in sub['parts'].items():
        act['parts'][k] = act['parts'].get(k, 0.0) + w * v
    act['d'] += w * sub['d']
    act['t'] += w * sub['t']
    act['m'] += w * sub['m']
    for k in act['n']:
        act['n'][k] += w * sub['n'][k]


def spell_cast(S, key, row, stacks=0, frozen=False, cc_in=0.0, ticks=0.0, t=None, mult=1.0, label=None):
    """One cast of a single-hit spell (direct part plus DoT), expected over hit and crit."""
    meta = SPELL_META[key]
    sch = meta['school']
    h = S['h'][sch]
    c = crit_of(S, key, sch, frozen)
    k = crit_bonus(S, sch)
    fl = flat_mult(S, sch, 0 if key == 'arcaneBlast' else stacks)   # the buff's damage mask leaves Arcane Blast out
    pc = pct_mult(S, sch, is_binary(S, key))
    coef = coef_of(S, key, row, row[7])
    base = (row[6] + coef * S['sp']) * fl * pc * mult
    direct = base * (1 + c * k) * h
    name = label or meta['name']
    parts = {name: direct}
    if len(row) >= 12 and ticks > 0:
        tcoef = coef_of(S, key, row, row[11])
        parts[name] += (row[8] + tcoef * S['sp']) * fl * pc * (1 + c * k) * h * ticks   # ticks crit (client flag)
    if fire_ish(sch) and S['ignite'] > 0:
        parts['Ignite'] = h * c * (1 + k) * base * S['ignite']
    base_cost = AB_COST if key == 'arcaneBlast' else row[4]
    cm = cost_mult(S, sch) + (AB_STACK_COST * stacks if key == 'arcaneBlast' else 0.0)
    paid = base_cost * cm * (1 - cc_in)
    if (fire_ish(sch) or frost_ish(sch)) and S['moe'] > 0:
        paid -= h * c * base_cost * S['moe'] * (1 - cc_in)     # Master of Elements: base cost, not on a free cast
    tt = cast_time(S, key, row) if t is None else t
    n = new_counters()
    n['casts'] = 1.0
    n['landed'] = h
    n['direct'] = direct
    n['cost'] = base_cost * cm
    if fire_ish(sch):
        n['fireHits'] = h
        n['fireCrit'] = h * c
        n['fireCritValue'] = h * (base * k + (1 + k) * base * S['ignite'])   # damage per +1 crit chance
    if frost_ish(sch):
        n['frostHits'] = h
    if meta['hs']:
        n['hsCasts'] = 1.0
        n['hsHits'] = h
        n['hsCrit'] = h * c
    n['time'] = tt
    n['time2'] = tt * tt
    return {'parts': parts, 't': tt, 'm': paid, 'n': n, 'h': h, 'c': c}


def missiles_cast(S, row, barrage, stacks=0, cc_in=0.0, label=None):
    """Arcane Missiles: one hit per missile. Barrage: free, a missile every 0.5 s. Stacks only in tooltip mode."""
    sch = 'arcane'
    h = S['h'][sch]
    c = crit_of(S, 'arcaneMissiles', sch, False)
    k = crit_bonus(S, sch)
    st = stacks if S['ab_tooltip'] else 0
    base = (row[6] + coef_of(S, 'arcaneMissiles', row, row[7]) * S['sp']) * flat_mult(S, sch, st) * pct_mult(S, sch, False)
    missiles = row[8]
    dmg = base * (1 + c * k) * h * missiles
    name = label or ('Arcane Missiles (Barrage)' if barrage else 'Arcane Missiles')
    if barrage:
        tt = 0.5 * missiles
        paid = 0.0
        cost = 0.0
    else:
        tt = row[9] / 1000.0
        cost = row[4] * cost_mult(S, sch)
        paid = cost * (1 - cc_in)
    n = new_counters()
    n['casts'] = 1.0
    n['landed'] = h
    n['direct'] = dmg
    n['cost'] = cost
    n['time'] = tt
    n['time2'] = tt * tt
    return {'parts': {name: dmg}, 't': tt, 'm': paid, 'n': n, 'h': h, 'c': c, 'missiles': missiles}


# ---------------------------------------------------------------- composites
def rows_for(S, key):
    """The ranks the plan may cast: every rank at full coefficients (downrank 'full') or the top one ('top').
    Without the tomes (topRanks off) the looted top rank is gone (NOTES a)."""
    rows = SPELL_ROWS[key]
    tome = SPELL_META[key]['tome']
    if not S['tomes'] and tome:
        rows = [row for row in rows if row[0] != tome]
    if S['downrank'] == 'top' or key not in FILLERS:
        return [rows[-1]]
    return rows


def top_row(S, key):
    return rows_for(S, key)[-1]


def pcc1(S, h):
    return S['cc'] * h


def pcc_am(S, missiles):
    return 1 - (1 - S['cc'] * S['h']['arcane']) ** missiles


def hs_pyro(S, cc_in):
    """A Pyroblast at 3 Hot Streak stacks: 6 s cast cut by 75%."""
    row = top_row(S, 'pyroblast')
    t = max(GCD, row[3] / 1000.0 * (1 - 0.75) / S['haste'])
    cast = spell_cast(S, 'pyroblast', row, cc_in=cc_in, ticks=S['pyro_ticks'], t=t, label='Pyroblast (Hot Streak)')
    cast['n']['pyros'] = 1.0
    cast['n']['pyroTime'] = t
    return cast


def barrage_am(S, stacks=0):
    row = top_row(S, 'arcaneMissiles')
    return missiles_cast(S, row, True, stacks=stacks, cc_in=0.0)


def follow_ups(S, act, key, cast, p_mb_extra=0.0, with_mb=True):
    """Expected procs after a cast: Hot Streak Pyroblasts, Fingers of Frost Ice Lances, Barrage Missiles.
    Returns the chance the action ends with Arcane Missiles (for Clearcasting on the next cast)."""
    meta = SPELL_META[key]
    h, c = cast['h'], cast['c']
    p1 = pcc1(S, h)
    if S['hs'] and meta['hs']:
        add_cast(act, hs_pyro(S, p1), S['eta'] * h * c)
    if S['fof'] and meta['chill']:
        il = spell_cast(S, 'iceLance', top_row(S, 'iceLance'), frozen=True, cc_in=p1, t=GCD, mult=IL_FROZEN,
                        label='Ice Lance (Fingers)')
        add_cast(act, il, h * FOF_CHANCE * S['fof'])
    p_am = 0.0
    if with_mb and S['mb'] > 0 and meta['mb'] > 0:
        p_am = meta['mb'] * S['mb']
    p_am = 1 - (1 - p_am) * (1 - p_mb_extra)
    if p_am > 0:
        add_cast(act, barrage_am(S), p_am)
    return p_am


def filler_action(S, key, row):
    """Cast `key` at this rank as the filler, with its procs."""
    meta = SPELL_META[key]
    top = rows_for(S, key)[-1][0] == row[0]
    label = meta['name'] if top else '%s (rank %d)' % (meta['name'], row[0])
    act = new_action(label, spec={'kind': 'filler', 'key': key, 'rank': row[0]})
    if key == 'arcaneMissiles':
        # a hard cast; the steady-state Clearcasting chance comes from its own missiles
        cast = missiles_cast(S, row, False, cc_in=pcc_am(S, row[8]), label=label)
        add_cast(act, cast, 1.0)
        act['mainCast'] = cast['t']
        return act
    ticks = 0.0
    if len(row) >= 12:    # DoT when spammed: refreshed every cast, so only whole ticks before the next one land
        ticks = min(row[9], math.floor(cast_time(S, key, row) / (row[10] / 1000.0)))
    h = S['h'][meta['school']]
    p_mb = meta['mb'] * S['mb'] if (S['mb'] > 0 and meta['mb'] > 0) else 0.0
    cc_in = p_mb * pcc_am(S, top_row(S, 'arcaneMissiles')[8]) + (1 - p_mb) * pcc1(S, h)
    cast = spell_cast(S, key, row, cc_in=cc_in, ticks=ticks, label=label)
    add_cast(act, cast, 1.0)
    act['mainCast'] = cast['t']
    follow_ups(S, act, key, cast)
    return act


def arcane_cycle(S, n, spender, tooltip_style):
    """n Arcane Blasts, then the spender takes the stacks, then Arcane Missiles if Barrage came up.
    tooltip_style (abMask 'tooltip', or amSpends): if Barrage is up after the Blasts, Missiles ends the cycle in
    place of the spender (it takes the stacks' damage only in tooltip mode)."""
    ab_row = top_row(S, 'arcaneBlast')
    sp_row = top_row(S, spender)
    sp_meta = SPELL_META[spender]
    p_ab = MB_AB * S['mb']
    p_sp = sp_meta['mb'] * S['mb']
    miss = top_row(S, 'arcaneMissiles')[8]
    p_by_ab = 1 - (1 - p_ab) ** n
    p_am = 1 - (1 - p_by_ab) * (1 - p_sp)
    label = 'Arcane Blast x%d + %s' % (n, sp_meta['name']) + (' (Missiles spend)' if tooltip_style else '')
    act = new_action(label, spec={'kind': 'cycle', 'n': n, 'key': spender, 'tooltip': tooltip_style})
    h_ab = S['h']['arcane']
    for k in range(1, n + 1):
        if k == 1:
            cc_in = p_am * pcc_am(S, miss) + (1 - p_am) * pcc1(S, h_ab)
        else:
            cc_in = pcc1(S, h_ab)
        add_cast(act, spell_cast(S, 'arcaneBlast', ab_row, stacks=k - 1, cc_in=cc_in), 1.0)
    ticks = 0.0
    if len(sp_row) >= 12:    # the spender's DoT is refreshed a cycle later
        cyc = n * cast_time(S, 'arcaneBlast', ab_row) + cast_time(S, spender, sp_row)
        ticks = min(sp_row[9], math.floor(cyc / (sp_row[10] / 1000.0)))
    cast = spell_cast(S, spender, sp_row, stacks=n, cc_in=pcc1(S, h_ab), ticks=ticks,
                      label=sp_meta['name'] + ' (stacks)')
    if not tooltip_style:
        add_cast(act, cast, 1.0)
        follow_ups(S, act, spender, cast, p_mb_extra=p_by_ab)
    else:
        add_cast(act, barrage_am(S, stacks=n), p_by_ab)
        sub = new_action('')
        add_cast(sub, cast, 1.0)
        follow_ups(S, sub, spender, cast)
        add_action(act, sub, 1 - p_by_ab)
    act['mainCast'] = cast_time(S, 'arcaneBlast', ab_row)
    # a cooldown that comes up mid-cycle waits for the whole cycle: count the Blasts and the spender as one block
    t_ab, t_sp = cast_time(S, 'arcaneBlast', ab_row), cast_time(S, spender, sp_row)
    w_sp = 1.0 if not tooltip_style else 1 - p_by_ab
    act['n']['time2'] += (n * t_ab + t_sp) ** 2 - n * t_ab ** 2 - w_sp * t_sp ** 2
    return act


def capped_instant(S, key, cap_cd):
    """Fire Blast or Blast Wave on its cooldown; cap = uses in the fight with cooldown drift."""
    row = top_row(S, key)
    meta = SPELL_META[key]
    # on cooldown from the pull; a cooldown that comes up mid-cast waits for it (drift)
    act = new_action(meta['name'], cap=0.5 + S['T'] / (cap_cd + S['state']['drift']), spec={'kind': 'cd', 'key': key})
    h = S['h'][meta['school']]
    cast = spell_cast(S, key, row, cc_in=pcc1(S, h), t=GCD)
    add_cast(act, cast, 1.0)
    follow_ups(S, act, key, cast)
    return act


def pom_action(S, candidates):
    """Presence of Mind: the biggest cast-time spell once per 3 min, instant (its procs as usual)."""
    best = None
    for act, key in candidates:
        if best is None or act['parts'].get(SPELL_META[key]['name'], 0.0) > best[0]['parts'].get(SPELL_META[best[1]]['name'], 0.0):
            best = (act, key)
    if best is None:
        return None
    src, key = best
    pom = sum(min(1.0, left / GCD) for left in press_left(POM_CD, S['T']))   # the last press needs a cast's time
    act = new_action('Presence of Mind: ' + SPELL_META[key]['name'], cap=pom,
                     spec={'kind': 'pom', 'key': key, 'rank': src['spec'].get('rank', 0)})
    act['d'], act['m'] = src['d'], src['m']
    act['t'] = src['t'] - (src['mainCast'] - GCD)
    act['parts'] = dict(src['parts'])
    act['n'] = dict(src['n'])
    act['n']['time'] = src['n']['time'] - (src['mainCast'] - GCD)
    act['n']['time2'] = src['n']['time2'] - src['mainCast'] ** 2 + GCD ** 2
    act['mainCast'] = GCD
    return act


def scorch_upkeep(S):
    """Improved Scorch plan: 5 stacks at the pull, then a Scorch every FV_REFRESH seconds. Fixed time and mana."""
    r = S['r']
    row = top_row(S, 'scorch')
    h = S['h']['fire']
    apply = max(1e-6, ISCORCH[r('ImprovedScorch')] * h)
    ramp_casts = FV_STACKS / apply
    ramp_time = ramp_casts * cast_time(S, 'scorch', row)
    refresh_casts = max(0.0, S['T'] - ramp_time) / FV_REFRESH / apply
    act = new_action('Scorch (Fire Vulnerability)')
    # ramp Scorches (and their procs) see 0 to 4 stacks: on average 2 stacks, +6%
    s_ramp = dict(S, fv=False)
    ramp = new_action('')
    cast = spell_cast(s_ramp, 'scorch', row, cc_in=pcc1(S, h), label='Scorch (Fire Vulnerability)')
    add_cast(ramp, cast, 1.0)
    follow_ups(s_ramp, ramp, 'scorch', cast)
    ramp_mult = 1 + FV_PER_STACK * (FV_STACKS - 1) / 2.0
    for k in ramp['parts']:
        ramp['parts'][k] *= ramp_mult
    ramp['d'] *= ramp_mult
    add_action(act, ramp, ramp_casts)
    keep = new_action('')
    cast = spell_cast(S, 'scorch', row, cc_in=pcc1(S, h), label='Scorch (Fire Vulnerability)')
    add_cast(keep, cast, 1.0)
    follow_ups(S, keep, 'scorch', cast)
    add_action(act, keep, refresh_casts)
    return act


def build_actions(S):
    """Every action this build can take, and the fixed part of the plan."""
    r = S['r']
    fire_ok = S['fire_ok']
    acts = []
    pom_src = []
    for key in FILLERS:
        if not fire_ok and key in FIRE_SPELLS:
            continue
        for row in rows_for(S, key):
            act = filler_action(S, key, row)
            acts.append(act)
            if row[0] == rows_for(S, key)[-1][0] and key != 'arcaneMissiles' and key != 'scorch':
                pom_src.append((act, key))
    if r('Pyroblast') and fire_ok:
        row = top_row(S, 'pyroblast')
        act = new_action('Pyroblast', spec={'kind': 'filler', 'key': 'pyroblast', 'rank': row[0]})
        # hard cast as a filler: the next one refreshes the DoT, so only whole ticks inside one cast land
        ticks = min(row[9], math.floor(cast_time(S, 'pyroblast', row) / (row[10] / 1000.0)))
        cast = spell_cast(S, 'pyroblast', row, cc_in=pcc1(S, S['h']['fire']), ticks=ticks)
        add_cast(act, cast, 1.0)
        act['mainCast'] = cast['t']
        acts.append(act)
        pom_src.append((act, 'pyroblast'))
    if r('ArcaneBlast'):
        spenders = ['frostbolt'] + (['fireball', 'frostfire'] if fire_ok else [])
        for n in range(1, 5):
            for sp_key in spenders:
                acts.append(arcane_cycle(S, n, sp_key, False))
                if (S['ab_tooltip'] or S['am_spends']) and S['mb'] > 0:
                    acts.append(arcane_cycle(S, n, sp_key, True))
    if fire_ok:
        acts.append(capped_instant(S, 'fireBlast', 8.0 - 1.0 * r('WakeOfFire')))
        if r('BlastWave'):
            acts.append(capped_instant(S, 'blastWave', 45.0))
    if r('PresenceOfMind'):
        pom = pom_action(S, pom_src)
        if pom is not None:
            acts.append(pom)
    evo = evocation_mana(S)
    if evo > 0:
        n_evo = uses(EVO_CD, S['T'] - EVO_TIME, EVO_LAG)
        act = new_action('Evocation', cap=float(n_evo), spec={'kind': 'evo'})
        act['t'] = EVO_TIME
        act['m'] = -evo
        act['n']['time'] = EVO_TIME
        act['n']['time2'] = EVO_TIME * EVO_TIME
        acts.append(act)
    # waiting out mana: shoot the wand (no mana spent, so full Spirit regen once the five-second rule clears, in
    # IDLE_BLOCK blocks). It blocks no cooldown.
    idle = new_action('Idle', spec={'kind': 'idle'})
    idle['t'] = 1.0
    idle['m'] = -S['idle_gain']
    if S['wand'] > 0:
        idle['d'] = S['wand']
        idle['parts'] = {'Wand': S['wand']}
    idle['n']['time'] = 1.0
    acts.append(idle)
    fixed = scorch_upkeep(S) if S['fv'] else None
    return acts, fixed


def evocation_mana(S):
    """8 s at 16x spirit regen plus mp5 (the sim's formula: 800 + 16 x Spirit + 1.6 x mp5 with 0 talents), less the
    casting regen those 8 s would have given anyway. Scaled by the evocation option (UNVERIFIED)."""
    full = EVO_TIME * (EVO_MULT * S['spirit_regen'] + S['mp5'] / 5)
    return full * float(opt(S['o'], 'evocation')) - EVO_TIME * S['regen_cast'] if float(opt(S['o'], 'evocation')) > 0 else 0.0


def item_schedule(S, top_rate):
    """When potions, runes and gems go out, and how much of them the fight can still spend.

    A potion needs room for its top roll (2250), a rune 1500, a gem its own top roll; the room comes from spending
    faster than regen. The model assumes the player opens room with the build's top action (top_rate, mana per
    second above regen): the first potion at 2250 / top_rate, a rune or gem after it, then each every 2 min.
    Mana that arrives too late to spend at top_rate before the fight ends is stranded (a backward pass): spending
    it faster would mean swapping the top action for weaker spells (conservative: a capped spell such as Fire
    Blast could spend a little of it). Runes and gems share one cooldown: the slots are filled in the better of two orders, runes only or the Ruby
    first then runes (with runes off, the gems in size order). Returns (potions, runes, gems, stranded, schedule)."""
    o = S['o']
    runes, gems = opt(o, 'runes'), opt(o, 'gems')
    orders = []
    if runes:
        orders.append('runes')
    if gems:
        orders.append('gems')
    if not orders:
        orders.append('none')
    best = None
    for order in orders:
        res = one_schedule(S, top_rate, order)
        usable = res[0] + res[1] + res[2] - res[3]
        if best is None or usable > best[0] + 1e-9:
            best = (usable, res)
    return best[1]


def one_schedule(S, top_rate, order):
    """order 'runes': every rune and gem slot takes a rune. 'gems': the Ruby first, then runes if on, else the next
    gem. 'none': potions only."""
    o = S['o']
    T = S['T']
    rate = max(1e-6, top_rate)
    runes = opt(o, 'runes')
    items = []                       # (time, mana, kind)
    has_pot = opt(o, 'potion') == 'mana'
    t_pot = POTION_MAX / rate
    if has_pot:
        k = t_pot
        while k <= T:
            items.append((k, POTION_MANA, 'potion'))
            k += ITEM_CD
    first = True
    gi = 0
    k = t_pot if has_pot else 0.0
    while order != 'none':
        if order == 'gems' and gi < len(GEMS) and (first or not runes):
            amt, top, kind = GEMS[gi], GEMS[gi] * GEM_ROOM, 'gem'
            gi += 1
        elif runes:
            amt, top, kind = RUNE_MANA, RUNE_MAX, 'rune'
        else:
            break
        if first:
            k += top / rate          # the room for the first one, after the potion's
        if k > T:
            break
        items.append((k, amt, kind))
        first = False
        k += ITEM_CD
    items.sort()
    cum = 0.0
    stranded = 0.0
    for idx in range(len(items) - 1, -1, -1):
        tm, amt = items[idx][0], items[idx][1]
        cum += amt
        stranded = max(stranded, cum - rate * (T - tm))
    pot = sum(it[1] for it in items if it[2] == 'potion')
    rune = sum(it[1] for it in items if it[2] == 'rune')
    gem = sum(it[1] for it in items if it[2] == 'gem')
    return pot, rune, gem, stranded, items


# ---------------------------------------------------------------- the linear program
def hull(acts, idx):
    """The uncapped actions on the upper concave hull of (mana per second, damage per second): at an optimum an
    uncapped action in use maximises damage minus a mana price, so it is a hull vertex. Sorted by mana per second
    then damage per second (index breaks ties), each point first drops the ones it beats on both counts."""
    pts = sorted(((acts[i]['m'] / acts[i]['t'], acts[i]['d'] / acts[i]['t'], i) for i in idx))
    front = []
    for m, d, i in pts:                   # Pareto: rising mana must buy more damage
        if front and d <= front[-1][1]:
            continue
        front.append((m, d, i))
    up = []
    for p in front:                       # upper hull: drop middle points on or under the chord
        while len(up) >= 2:
            (m1, d1, _), (m2, d2, _) = up[-2], up[-1]
            if (d2 - d1) * (p[0] - m1) <= (p[1] - d1) * (m2 - m1):
                up.pop()
            else:
                break
        up.append(p)
    return sorted(i for _, _, i in up)


def solve_lp(acts, T_free, M):
    """max sum d x  s.t.  sum t x = T_free, sum m x <= M, 0 <= x <= cap (None = no cap).
    Vertices have at most two actions strictly inside their bounds; enumerate them over the uncapped hull
    and the capped actions."""
    unc = [i for i, a in enumerate(acts) if a['cap'] is None]
    keep = hull(acts, unc)
    capped = [i for i, a in enumerate(acts) if a['cap'] is not None and a['cap'] > 0]
    cand = keep + capped
    best_v = -1.0
    best_x = None
    nc = len(cand)
    for size in (1, 2):
        for qa in range(nc):
            for qb in range(qa + 1 if size == 2 else nc, nc if size == 2 else nc + 1):
                basics = [cand[qa]] if size == 1 else [cand[qa], cand[qb]]
                others = [i for i in capped if i not in basics]
                for mask in range(1 << len(others)):
                    Tr, Mr, V = T_free, M, 0.0
                    x = {}
                    for bit in range(len(others)):
                        if (mask >> bit) & 1:
                            i = others[bit]
                            u = acts[i]['cap']
                            x[i] = u
                            Tr -= acts[i]['t'] * u
                            Mr -= acts[i]['m'] * u
                            V += acts[i]['d'] * u
                    if size == 1:
                        a = acts[basics[0]]
                        xa = Tr / a['t']
                        if xa < -EPS or (a['cap'] is not None and xa > a['cap'] + EPS):
                            continue
                        xa = max(0.0, xa)
                        if a['m'] * xa > Mr + 1e-6:
                            continue
                        x[basics[0]] = xa
                        V += a['d'] * xa
                    else:
                        a, b = acts[basics[0]], acts[basics[1]]
                        det = a['t'] * b['m'] - b['t'] * a['m']
                        if abs(det) < 1e-12:
                            continue
                        xa = (Tr * b['m'] - b['t'] * Mr) / det
                        xb = (a['t'] * Mr - Tr * a['m']) / det
                        if xa < -EPS or xb < -EPS:
                            continue
                        if a['cap'] is not None and xa > a['cap'] + EPS:
                            continue
                        if b['cap'] is not None and xb > b['cap'] + EPS:
                            continue
                        xa, xb = max(0.0, xa), max(0.0, xb)
                        x[basics[0]] = xa
                        x[basics[1]] = xb
                        V += a['d'] * xa + b['d'] * xb
                    if V > best_v + 1e-9:
                        best_v = V
                        best_x = x
    return best_v, best_x


# ---------------------------------------------------------------- fixed point
def comb_extra(c, max_hits=None):
    """Expected extra crits from one Combustion: the crits it adds over what the same hits would crit anyway.
    Hit i after the press has c + 10% x i (up to 10 stacks); the aura ends at the 4th crit. max_hits: the Fire hits
    the fight has left after the press (a fraction counts that share of the next hit); None means no limit."""
    probs = [1.0, 0.0, 0.0, 0.0]        # P(j crits so far, window open)
    extra = 0.0
    for i in range(1, 60):
        open_p = sum(probs)
        if open_p < 1e-12:
            break
        if max_hits is not None and i > max_hits + 1 - 1e-12:
            break
        p = min(1.0, c + COMB_CRIT * min(COMB_MAX, i))
        share = 1.0 if max_hits is None else min(1.0, max_hits - (i - 1))
        extra += share * open_p * (p - c)
        nxt = [0.0, 0.0, 0.0, 0.0]
        for j in range(4):
            nxt[j] += probs[j] * (1 - p)
            if j + 1 < 4:
                nxt[j + 1] += probs[j] * p
        probs = nxt
    return extra


def initial_state():
    return {'wc_avg': None, 'eta': 1.0 / 3.0, 'pyro_ticks': 4.0, 'drift': 0.75, 'eu_mana': 0.0}


def plan_totals(acts, x, fixed):
    tot = new_counters()
    for i, xi in x.items():
        for k in tot:
            tot[k] += xi * acts[i]['n'][k]
    if fixed is not None:
        for k in tot:
            tot[k] += fixed['n'][k]
    return tot


def next_state(S, tot, state):
    r = S['r']
    T = S['T']
    st = dict(state)
    wc = r('WintersChill')
    if wc and tot['frostHits'] > 0:
        shortfall = 2.5 * (wc + 1)          # stack-casts lost while stacks build: (r(r+1)/2) / (0.2 r)
        st['wc_avg'] = WC_PER_STACK * max(0.0, wc - shortfall / tot['frostHits'])
    if S['hs'] and tot['hsCasts'] > 0:
        p = min(1.0, tot['hsCrit'] / tot['hsCasts'])
        tbar = max(GCD, (T - tot['pyroTime']) / tot['hsCasts'])
        a = 1 - (1 - p) ** (HS_WINDOW / tbar)
        st['eta'] = a * a / (1 + a + a * a)
    if tot['pyros'] > 0:
        mu = T / tot['pyros']
        st['pyro_ticks'] = sum(math.exp(-3.0 * j / mu) for j in range(1, 5))
    else:
        st['pyro_ticks'] = 4.0
    if tot['time'] > 0:
        st['drift'] = tot['time2'] / (2 * tot['time'])
    if S['race'] == 'gnome' and tot['casts'] > 0:
        st['eu_mana'] = eureka_casts(T, tot['casts']) * EUREKA * tot['cost'] / tot['casts']
    return st


def run_plan(o, tal, fv_plan):
    """The fixed point: solve, update the plan-dependent state, repeat. After two full updates the state moves
    halfway to each new value (damping), so a plan that flips between two vertices settles between them. The
    opening action and the item set are chosen afresh on the first DAMP_FROM + 1 passes and then kept, so two
    choices near a tie cannot trade places on every pass."""
    state = initial_state()
    res = None
    lock = drop_lock = None
    for it in range(ITERATIONS):
        S = context(o, tal, fv_plan, state)
        S['top_lock'] = lock
        S['drop_lock'] = drop_lock
        res = solve_once(S)
        if it == DAMP_FROM:
            lock = res['top']
            drop_lock = res['drop']
        new = next_state(S, res['tot'], state)
        if it >= DAMP_FROM:
            new = {k: (v if state[k] is None or v is None else state[k] + DAMP * (v - state[k])) for k, v in new.items()}
        state = new
    res['state'] = state
    return res


def top_action(acts, lock=None):
    """What a player casts when mana is no object, to open room for the first potion: among the uncapped actions
    within 1% of the best damage per second, the one that spends fastest (a near-tie cannot flip the choice).
    lock (index, name), from run_plan: keep that action once the loop has chosen it."""
    if lock is not None and lock[0] < len(acts) and acts[lock[0]]['name'] == lock[1]:
        return acts[lock[0]]
    best = 0.0
    for a in acts:
        if a['cap'] is None and a['t'] > 0 and a['d'] > 0:
            best = max(best, a['d'] / a['t'])
    top = None
    for a in acts:
        if a['cap'] is None and a['t'] > 0 and a['d'] > 0 and a['d'] / a['t'] >= TOP_BAND * best:
            if top is None or a['m'] / a['t'] > top['m'] / top['t']:
                top = a
    return top


def item_drops(o):
    """The item sets a player may pick from: all of them, then (when that leaves something) without the potion,
    without the runes and gems, and with none."""
    pot = opt(o, 'potion') == 'mana'
    slots = bool(opt(o, 'runes') or opt(o, 'gems'))
    drops = [{}]
    if pot and slots:
        drops += [{'potion': 'none'}, {'runes': False, 'gems': False}]
    if pot or slots:
        drops.append({'potion': 'none', 'runes': False, 'gems': False})
    return drops


def with_items(S, acts, fixed, top, rate, drop):
    """The program with the items left after `drop`. From the pull to the first potion (or gem) the top action runs,
    opening the room the item schedule needs (the opening); the program splits the rest."""
    T = S['T']
    sched = item_schedule(dict(S, o=dict(S['o'], **drop)), rate)
    pot, rune, gem, stranded, items = sched
    M = S['max_mana'] + T * S['regen_cast'] + pot + rune + gem - stranded + S['state']['eu_mana']
    T_free = T
    if fixed is not None:
        T_free -= fixed['t']
        M -= fixed['m']
    opening = None
    if items and top is not None:
        t_open = min(items[0][0], T_free)
        opening = new_action('opening')
        add_action(opening, top, t_open / top['t'])
        opening['spec'] = top['spec']
        opening['name'] = top['name']
        T_free -= opening['t']
        M -= opening['m']
    v, x = solve_lp(acts, T_free, M)
    return {'score': v + (opening['d'] if opening is not None else 0.0), 'v': v, 'x': x, 'M': M,
            'opening': opening, 'sched': sched}


def solve_once(S):
    acts, fixed = build_actions(S)
    top = top_action(acts, S.get('top_lock'))
    rate = (top['m'] / top['t'] if top is not None else 0.0) - S['regen_cast']
    # the opening forces the top action for its length; when the regen above it is small (high mp5, a short fight)
    # that can cost more than an item brings, and a player would skip that item: the best of the item sets
    drops = item_drops(S['o'])
    picks = [S['drop_lock']] if S.get('drop_lock') is not None else range(len(drops))
    best = None
    for k in picks:
        c = with_items(S, acts, fixed, top, rate, drops[k])
        if best is None or c['score'] > best['score'] + 1e-9:
            best = c
            best['drop'] = k
    T = S['T']
    v, x, M, opening = best['v'], best['x'], best['M'], best['opening']
    pot, rune, gem, stranded, items = best['sched']
    tot = plan_totals(acts, x, fixed)
    parts = {}
    for i, xi in x.items():
        for k, dv in acts[i]['parts'].items():
            parts[k] = parts.get(k, 0.0) + xi * dv
    for extra in (fixed, opening):
        if extra is not None:
            for k, dv in extra['parts'].items():
                parts[k] = parts.get(k, 0.0) + dv
    if opening is not None:
        for k in tot:
            tot[k] += opening['n'][k]
    # Combustion: each press adds a fixed number of crits (4 minus what those hits crit anyway), worth the plan's
    # average Fire crit (the crit bonus and its Ignite). Booked after the program so it cannot feed back into it.
    # An extra crit on a Hot Streak spell also adds a stack: eta Pyroblasts per stack, each worth its damage less
    # the filler time it takes.
    if S['r']('Combustion') and S['fire_ok'] and tot['fireHits'] > 0:
        c_bar = min(1.0, tot['fireCrit'] / tot['fireHits'])
        value = tot['fireCritValue'] / tot['fireHits']
        if S['hs']:
            pyro = hs_pyro(S, 0.0)
            before = sum(parts.values())
            net = sum(pyro['parts'].values()) - pyro['t'] * before / T
            value += tot['hsHits'] / tot['fireHits'] * S['eta'] * max(0.0, net)
        hits = tot['fireHits'] / T          # Fire hits a second: the last press only gets the hits left after it
        parts['Combustion'] = sum(comb_extra(c_bar, left * hits) for left in press_left(COMB_CD, T)) * value
    racial = 0.0
    if S['race'] == 'gnome' and tot['casts'] > 0:
        racial = eureka_casts(T, tot['casts']) * EUREKA * tot['direct'] / tot['casts']
    if S['race'] == 'undead':
        pl = TOTG_CHANCE * tot['landed'] / T
        racial = pl / (1 + pl) * TOTG_HP * float(opt(S['o'], 'maxHp')) * T
    if racial:
        parts['Racial'] = racial
    dps_parts = {k: dv / T for k, dv in parts.items() if dv > 1e-9}
    total = sum(dps_parts.values())
    plan = []
    if opening is not None:
        plan.append({'name': opening['name'] + ' (opening)', 'uses': opening['t'] / top['t'], 'seconds': opening['t']})
    for i in sorted(x):
        if x[i] > 1e-9:
            name = acts[i]['name']
            if name == 'Idle':
                name = 'Wand, full regen' if S['wand'] > 0 else 'Idle, full regen'
            plan.append({'name': name, 'uses': x[i], 'seconds': x[i] * acts[i]['t']})
    idle = sum(x[i] * acts[i]['t'] for i in x if acts[i]['name'] == 'Idle')
    feasible = all(xi >= -1e-6 for xi in x.values())
    chosen = [{'spec': acts[i]['spec'], 'name': acts[i]['name'], 'x': x[i], 'cap': acts[i]['cap'], 't': acts[i]['t'],
               'm': acts[i]['m'], 'd': acts[i]['d']} for i in sorted(x) if x[i] > 1e-9]
    return {'total': total, 'parts': dps_parts, 'plan': plan, 'tot': tot, 'idle': idle, 'feasible': feasible,
            'chosen': chosen, 'fixed_t': fixed['t'] if fixed is not None else 0.0,
            'opening': {'spec': opening['spec'], 't': opening['t'], 'm': opening['m']} if opening is not None else None,
            'mana': {'pool': S['max_mana'], 'regen': T * S['regen_cast'], 'potions': pot, 'runes': rune,
                     'gems': gem, 'stranded': stranded, 'budget': M, 'fixed': fixed['m'] if fixed is not None else 0.0},
            'items': items,
            'top': (acts.index(top), top['name']) if top is not None else None, 'drop': best['drop'],
            'lp': v}


def evaluate(o, tal):
    """Best plan for a talent build: with and without keeping Fire Vulnerability up, whichever is higher."""
    has_fv = (tal.get('ImprovedScorch', 0) or 0) > 0 and not opt(o, 'fireImmune')
    res = run_plan(o, tal, False)
    res['fv'] = False
    if has_fv:
        alt = run_plan(o, tal, True)
        if alt['total'] > res['total'] + 1e-9:
            res = alt
            res['fv'] = True
    return res


# ---------------------------------------------------------------- specs and the page API
# The ElliotWood sim's three builds (FINDINGS 3, decoded from its talent strings), plus hybrids the search in
# analysis/raid_specs.py found competitive.
SIM_ARCANE = {'ArcaneFocus': 5, 'ImprovedChanneling': 5, 'ArcaneConcentration': 5, 'ArcaneGeometry': 2, 'ArcaneImpact': 3,
              'ArcaneBlast': 1, 'ArcaneMeditation': 3, 'MissileBarrage': 1, 'PresenceOfMind': 1, 'ArcaneMind': 5,
              'ArcaneInstability': 3, 'ArcanePower': 1,
              'ElementalPrecision': 5, 'IceShards': 5, 'PiercingIce': 3, 'FrostChanneling': 3}
SIM_FIRE = {'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'FlameThrowing': 2, 'BurningSoul': 2, 'Pyroblast': 1,
            'ImprovedScorch': 3, 'HotStreak': 1, 'MasterOfElements': 3, 'CriticalMass': 3, 'BlastWave': 1,
            'FirePower': 5, 'Combustion': 1,
            'ElementalPrecision': 5, 'IceShards': 5, 'PiercingIce': 3, 'FrostChanneling': 3}
SIM_FROST = {'ArcaneFocus': 5, 'ArcaneConcentration': 5, 'ArcaneGeometry': 1, 'ArcaneImpact': 3,
             'ImprovedFrostbolt': 5, 'ElementalPrecision': 5, 'IceShards': 5, 'Frostbite': 3, 'PiercingIce': 3,
             'IceLance': 1, 'IceBlock': 1, 'Shatter': 3, 'ColdSnap': 1, 'FingersOfFrost': 2, 'WintersChill': 5,
             'IceBarrier': 1}

# The search (analysis/raid_search.py, iterated local search under the point rules, run under the defaults and four
# untested flips) found these ahead of the sim builds; each is the most robust of its family across those scenarios
# (mage-research/raid/search_v2.json). Points in talents the raid model does not read (threat, range, pushback) are
# filled with sensible picks; they change no number here.
FROST_MB = {'ArcaneFocus': 5, 'ArcaneSubtlety': 2, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneMeditation': 2,
            'MissileBarrage': 1,
            'Incineration': 3,
            'ImprovedFrostbolt': 5, 'ElementalPrecision': 5, 'IceShards': 5, 'PiercingIce': 3, 'FrostChanneling': 1,
            'IceLance': 1, 'Shatter': 3, 'FingersOfFrost': 2, 'WintersChill': 5}
FIRE_MB = {'ArcaneFocus': 5, 'ImprovedChanneling': 1, 'ArcaneConcentration': 5, 'ArcaneImpact': 3, 'ArcaneBlast': 1,
           'ArcaneMeditation': 3, 'MissileBarrage': 1,
           'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'BurningSoul': 1, 'Pyroblast': 1, 'ImprovedScorch': 3,
           'HotStreak': 1, 'MasterOfElements': 3, 'CriticalMass': 3, 'FirePower': 5, 'Combustion': 1,
           'ElementalPrecision': 1}
ARCANE_TUNED = {'ArcaneFocus': 5, 'ImprovedChanneling': 1, 'ArcaneSubtlety': 2, 'ArcaneConcentration': 5, 'ArcaneImpact': 3,
                'ArcaneBlast': 1, 'ArcaneMeditation': 3, 'MissileBarrage': 1, 'PresenceOfMind': 1, 'ArcaneMind': 5,
                'ArcaneInstability': 3, 'ArcanePower': 1,
                'Incineration': 3,
                'ImprovedFrostbolt': 5, 'ElementalPrecision': 5, 'IceShards': 4, 'PiercingIce': 3}
ARCANE_FIRE = {'ArcaneFocus': 5, 'ImprovedChanneling': 1, 'ArcaneSubtlety': 2, 'ArcaneConcentration': 5, 'ArcaneImpact': 3,
               'ArcaneBlast': 1, 'ArcaneMeditation': 3, 'MissileBarrage': 1, 'PresenceOfMind': 1, 'ArcaneMind': 5,
               'ArcaneInstability': 3, 'ArcanePower': 1,
               'Incineration': 3, 'ImprovedFireball': 5, 'Ignite': 5, 'BurningSoul': 1, 'Pyroblast': 1,
               'ImprovedScorch': 3, 'HotStreak': 1,
               'ElementalPrecision': 1}

SPECS = [
    {'id': 'frost-mb', 'name': 'Frost with Barrage 18/3/30', 'tree': 2, 'talents': FROST_MB,
     'note': 'Frostbolt, Ice Lance on Fingers of Frost, free Arcane Missiles from Missile Barrage; Incineration for Ice Lance crits'},
    {'id': 'fire-mb', 'name': 'Fire with Arcane Blast 19/31/1', 'tree': 1, 'talents': FIRE_MB,
     'note': 'One Arcane Blast then Fireball, Fire Blast, Hot Streak Pyroblasts and Ignite, free Arcane Missiles from Barrage'},
    {'id': 'arcane', 'name': 'Arcane 31/3/17', 'tree': 0, 'talents': ARCANE_TUNED,
     'note': 'Arcane Blast then Frostbolt to spend the stacks, Missiles on Barrage, Arcane Power; Incineration for Blast crits'},
    {'id': 'arcane-fire', 'name': 'Arcane with Ignite 31/19/1', 'tree': 0, 'talents': ARCANE_FIRE,
     'note': 'Arcane Blast then Fireball to spend the stacks, Hot Streak Pyroblasts, Presence of Mind on Pyroblast'},
    {'id': 'frost-sim', 'name': 'Frost 14/0/35 (sim build)', 'tree': 2, 'talents': SIM_FROST,
     'note': "The ElliotWood sim's Frost build (2 points unspent), for comparison"},
    {'id': 'arcane-sim', 'name': 'Arcane 35/0/16 (sim build)', 'tree': 0, 'talents': SIM_ARCANE,
     'note': "The ElliotWood sim's Arcane build, for comparison"},
    {'id': 'fire-sim', 'name': 'Fire 0/35/16 (sim build)', 'tree': 1, 'talents': SIM_FIRE,
     'note': "The ElliotWood sim's Fire build, for comparison"},
]
FIRE_REASON = ('Not viable on a boss immune to Fire: Fireball, Scorch, Pyroblast and Ignite deal nothing. '
               'Use a Frost or Arcane build.')


def spec_by_id(sid):
    for s in SPECS:
        if s['id'] == sid:
            return s
    raise KeyError(sid)


def eval_spec(o, s):
    if opt(o, 'fireImmune') and s['tree'] == 1:
        return {'id': s['id'], 'name': s['name'], 'total': 0.0, 'viable': False, 'reason': FIRE_REASON, 'parts': {},
                'plan': [], 'fv': False}
    res = evaluate(o, s['talents'])
    return {'id': s['id'], 'name': s['name'], 'total': res['total'], 'viable': True, 'reason': '', 'parts': res['parts'],
            'plan': res['plan'], 'fv': res['fv'], 'idle': res['idle'], 'feasible': res['feasible'], 'mana': res['mana']}


def rank(o):
    out = [eval_spec(o, s) for s in SPECS]
    return sorted(out, key=lambda r: (not r['viable'], -r['total']))


def spec_total(o, sid):
    return eval_spec(o, spec_by_id(sid))['total']


def with_opts(o, **kw):
    n = dict(o)
    n.update(kw)
    return n


def stat_weights(o, sid):
    """Damage per second per point of each stat and in spell power. Intellect also raises crit
    (0.0168% a point), because the crit input is the character sheet value."""
    def f(**kw):
        return spec_total(with_opts(o, **kw), sid)
    sp0, c0, h0 = opt(o, 'sp'), opt(o, 'crit'), opt(o, 'gearHit')
    i0, s0, m0 = opt(o, 'int'), opt(o, 'spirit'), opt(o, 'mp5')
    sp = (f(sp=sp0 + 10) - f(sp=max(0, sp0 - 10))) / (20 if sp0 >= 10 else 10 + sp0)
    crit = (f(crit=c0 + 0.01) - f(crit=max(0.0, c0 - 0.01))) / (2 if c0 >= 0.01 else 1)
    hit = f(gearHit=h0 + 0.01) - f(gearHit=h0)
    di = 10 if i0 >= 10 else i0
    intel = (f(int=i0 + 10, crit=c0 + 10 * CRIT_PER_INT) - f(int=i0 - di, crit=max(0.0, c0 - di * CRIT_PER_INT))) / (10 + di)
    ds = 10 if s0 >= 10 else s0
    spirit = (f(spirit=s0 + 10) - f(spirit=s0 - ds)) / (10 + ds)
    dm = 10 if m0 >= 10 else m0
    mp5 = (f(mp5=m0 + 10) - f(mp5=m0 - dm)) / (10 + dm)
    def ins(v):
        return v / sp if sp > 0 else 0.0
    return {'sp': sp, 'crit': crit, 'hit': hit, 'int': intel, 'spirit': spirit, 'mp5': mp5,
            'critInSp': ins(crit), 'hitInSp': ins(hit), 'intInSp': ins(intel), 'spiritInSp': ins(spirit),
            'mp5InSp': ins(mp5)}


def compare_items(o, sid, a, b):
    """Swap an equipped item a for b. Items: {sp, crit, hit, int, spirit, mp5}; crit and hit are fractions."""
    def g(it, k):
        return it.get(k, 0) or 0
    base = spec_total(o, sid)
    d_int = g(b, 'int') - g(a, 'int')
    swapped = spec_total(with_opts(
        o,
        sp=max(0, opt(o, 'sp') - g(a, 'sp') + g(b, 'sp')),
        crit=max(0.0, opt(o, 'crit') - g(a, 'crit') + g(b, 'crit') + d_int * CRIT_PER_INT),
        gearHit=max(0.0, opt(o, 'gearHit') - g(a, 'hit') + g(b, 'hit')),
        int=max(0, opt(o, 'int') + d_int),
        spirit=max(0, opt(o, 'spirit') - g(a, 'spirit') + g(b, 'spirit')),
        mp5=max(0, opt(o, 'mp5') - g(a, 'mp5') + g(b, 'mp5')),
    ), sid)
    return {'base': base, 'swapped': swapped, 'diff': swapped - base, 'pct': (swapped / base - 1) * 100 if base else 0.0}


# ---------------------------------------------------------------- data check and point rules
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')


def check_data():
    """Every hardcoded spell row equals data/mage_spells.json. Returns a list of mismatches (empty = fine)."""
    with open(os.path.join(DATA, 'mage_spells.json'), encoding='utf-8') as fh:
        recs = json.load(fh)['records']
    names = {'frostbolt': 'Frostbolt', 'fireball': 'Fireball', 'frostfire': 'Frostfire Bolt', 'scorch': 'Scorch',
             'arcaneMissiles': 'Arcane Missiles', 'fireBlast': 'Fire Blast', 'arcaneBlast': 'Arcane Blast',
             'iceLance': 'Ice Lance', 'pyroblast': 'Pyroblast', 'blastWave': 'Blast Wave'}

    def v(x, k):
        y = x.get(k)
        return y.get('value') if isinstance(y, dict) else y
    bad = []
    for key, rows in SPELL_ROWS.items():
        for row in rows:
            rec = [r for r in recs if r['spell'] == names[key] and r['rank'] == row[0]]
            if len(rec) != 1:
                bad.append((key, row[0], 'missing'))
                continue
            rec = rec[0]
            dm = rec['damage']
            want = [rec['rank'], rec['id'], v(rec, 'level_learned'), v(rec, 'cast_ms') or 0,
                    v(rec, 'mana_cost') if key != 'arcaneBlast' else 0, v(rec, 'cooldown_ms') or 0,
                    v(dm, 'avg_at_60'), v(dm, 'sp_coefficient')]
            dot = rec.get('dot')
            if dot:
                want += [v(dot, 'avg_at_60'), v(dot, 'ticks'), v(dot, 'period_ms'), v(dot, 'sp_coefficient')]
            if key == 'arcaneMissiles':
                want += [v(rec, 'missiles'), v(rec, 'channel_ms')]
            if key == 'arcaneBlast' and v(rec, 'mana_cost_pct_base') != 15:
                bad.append((key, row[0], 'cost pct'))
            if [float(a) for a in want] != [float(a) for a in row]:
                bad.append((key, row[0], row, want))
    return bad


def load_talents():
    with open(os.path.join(DATA, 'talents.json'), encoding='utf-8') as fh:
        return json.load(fh)['talents']


def build_errors(tal, level=60, talents=None):
    """Point rules (CONTRACTS 1): max(0, level - 9) points, 5 per row within a tree, prerequisites at full rank."""
    talents = talents or load_talents()
    by_key = {t['k']: t for t in talents}
    errs = []
    total = 0
    for k, v in tal.items():
        if k not in by_key:
            errs.append('unknown talent ' + k)
            continue
        if v < 0 or v > by_key[k]['m']:
            errs.append('%s rank %d out of range' % (k, v))
        total += v
    if total > max(0, level - 9):
        errs.append('%d points > %d' % (total, max(0, level - 9)))
    for t in talents:
        v = tal.get(t['k'], 0)
        if not v:
            continue
        below = sum(tal.get(u['k'], 0) for u in talents if u['t'] == t['t'] and u['r'] < t['r'])
        if below < 5 * t['r']:
            errs.append('%s needs %d points above it, has %d' % (t['k'], 5 * t['r'], below))
        if t['req'] and tal.get(t['req'][0], 0) < t['req'][1]:
            errs.append('%s needs %s %d' % (t['k'], t['req'][0], t['req'][1]))
    return errs


if __name__ == '__main__':
    print('data check:', check_data() or 'ok')
    for s in SPECS:
        print(s['id'], build_errors(s['talents']) or 'build ok', sum(s['talents'].values()), 'points')
    for r in rank(DEFAULTS):
        print('%-26s %7.1f  %s' % (r['name'], r['total'], ', '.join('%s %.0f' % (k, v) for k, v in
                                                                      sorted(r['parts'].items(), key=lambda kv: -kv[1]))))
        for p in r['plan']:
            print('      %-44s %7.2f uses %6.1f s' % (p['name'], p['uses'], p['seconds']))
