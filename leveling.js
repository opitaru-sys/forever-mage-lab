/* Forever Mage leveling model: expected-value single-target fight simulator and rest model.
 * Line-for-line port of models/leveling_sim.py and models/character.py (read those for sources and reasoning).
 * tests/leveling_parity_test.js checks it against Python fixtures (tests/make_leveling_fixtures.py).
 * API (CONTRACTS section 4): evaluate(L, tal, gear, opts) -> { spk, ttk, rest, policy, feasible, ... },
 * policyLabel(name), SCORED. opts: { race, hpMults, ... } with the camelCase names in OPT_MAP.
 */
(function (root) {
  const DT = 0.02, GCD = 1.5, MAX_TIME = 240.0, FIN_BELOW = 0.2, MELEE_GAP = 5.0, WAND_SPEED = 1.5, CONJURE_S = 3.0;
  const MIN_SAVE = 1.0;

  // ---------------------------------------------------------------- spell ranks (data/mage_spells.json)
  // direct rows: [learn, average at learn, per level, max level, coefficient, mana, cast s] (+ [DoT tick, ticks, period, coef])
  const FROSTBOLT = [[4, 19, 0.5, 8, 0.407, 25, 1.5], [8, 33, 0.7, 12, 0.489, 35, 1.8], [14, 46, 0.9, 18, 0.597, 50, 2.2],
    [20, 60, 1.1, 24, 0.706, 65, 2.6], [26, 95, 1.5, 30, 0.814, 100, 3], [32, 134, 1.7, 36, 0.814, 130, 3],
    [38, 181, 2, 42, 0.814, 160, 3], [44, 244, 2.3, 48, 0.814, 195, 3], [50, 308, 2.6, 54, 0.814, 225, 3],
    [56, 386, 2.9, 60, 0.814, 260, 3]];
  const FROSTBOLT_SLOW_S = { 4: 5, 8: 6, 14: 6, 20: 7, 26: 7, 32: 8, 38: 8, 44: 9, 50: 9, 56: 9, 60: 9 };
  const FIREBALL = [[1, 18, 0.6, 5, 0.429, 30, 1.5, 1, 2, 2, 0], [6, 37, 0.7, 10, 0.571, 45, 2, 1, 3, 2, 0],
    [12, 53, 0.9, 16, 0.714, 65, 2.5, 2, 3, 2, 0], [18, 74, 1.1, 22, 0.857, 95, 3, 3, 4, 2, 0],
    [24, 108, 1.5, 28, 1, 140, 3.5, 4, 4, 2, 0], [30, 153, 1.8, 34, 1, 185, 3.5, 6, 4, 2, 0],
    [36, 187, 2.3, 40, 1, 220, 3.5, 6, 4, 2, 0], [42, 235, 2.2, 46, 1, 260, 3.5, 8, 4, 2, 0],
    [48, 300, 2.4, 52, 1, 305, 3.5, 10, 4, 2, 0], [54, 374, 2.7, 58, 1, 350, 3.5, 12, 4, 2, 0],
    [60, 451, 3, 64, 1, 395, 3.5, 14, 4, 2, 0]];
  const ARCANE_MISSILES = [[8, 24, 0.3, 12, 0.286, 85, 3], [16, 31, 0.4, 20, 0.286, 140, 4], [24, 44, 0.5, 28, 0.286, 235, 5],
    [32, 66, 0.6, 36, 0.286, 320, 5], [40, 95, 0.7, 44, 0.286, 410, 5], [48, 130, 0.8, 52, 0.286, 500, 5],
    [56, 171, 0.9, 60, 0.286, 595, 5]];
  // top ranks from looted tomes, source UNKNOWN in Forever (test m6): off unless top_ranks
  const TOME = { Frostbolt: [60, 475, 3.2, 64, 0.814, 290, 3], Fireball: [60, 483, 3, 64, 1, 410, 3.5, 15, 4, 2, 0],
    ArcaneMissiles: [56, 209, 1, 60, 0.286, 655, 5] };
  const FIRE_BLAST = [[6, 28, 0.6, 11, 0.429, 40, 0], [14, 58, 1, 19, 0.429, 75, 0], [22, 100, 1.4, 27, 0.429, 115, 0],
    [30, 163, 1.8, 35, 0.429, 165, 0], [38, 236, 2.2, 43, 0.429, 220, 0], [46, 331, 2.6, 51, 0.429, 280, 0],
    [54, 438, 3, 59, 0.429, 340, 0]];
  const SCORCH = [[22, 39, 0.8, 26, 0.429, 50, 1.5], [28, 55, 1, 32, 0.429, 65, 1.5], [34, 69, 1, 38, 0.429, 80, 1.5],
    [40, 93, 1.2, 44, 0.429, 100, 1.5], [46, 116, 1.4, 50, 0.429, 115, 1.5], [52, 150, 1.5, 56, 0.429, 135, 1.5],
    [58, 178, 1.7, 62, 0.429, 150, 1.5]];
  const PYROBLAST = [[20, 110, 1.5, 24, 1, 125, 6, 11, 4, 3, 0.15], [24, 134, 1.7, 30, 1, 150, 6, 14, 4, 3, 0.15],
    [30, 191, 2.1, 36, 1, 195, 6, 19, 4, 3, 0.15], [36, 245, 2.4, 42, 1, 240, 6, 25, 4, 3, 0.15],
    [42, 311, 2.7, 48, 1, 285, 6, 31, 4, 3, 0.15], [48, 394, 3, 54, 1, 335, 6, 38, 4, 3, 0.15],
    [54, 481, 3.4, 60, 1, 385, 6, 46, 4, 3, 0.15], [60, 583, 4.6, 66, 1, 440, 6, 53, 4, 3, 0.15]];
  const ARCANE_BLAST = [[20, 54, 0.9, 28, 0.714, 0, 2.5], [30, 130, 1.4, 38, 0.714, 0, 2.5], [40, 169, 1.6, 48, 0.714, 0, 2.5],
    [50, 274, 2.1, 58, 0.714, 0, 2.5], [60, 394, 2.6, 68, 0.714, 0, 2.5]];
  const AB_COST = 0.15;
  const ICE_LANCE = [[20, 28, 0.35, 26, 0, 45, 0], [28, 36, 0.4, 32, 0, 55, 0], [34, 45, 0.5, 40, 0, 70, 0],
    [42, 79, 0.7, 48, 0, 105, 0], [48, 98, 0.7, 56, 0, 120, 0], [56, 145, 0.9, 64, 0, 160, 0]];
  const FROSTFIRE = [[40, 100, 1.3, 48, 0.814, 205, 3, 9, 3, 3, 0], [50, 182, 1.7, 58, 0.814, 285, 3, 13, 3, 3, 0],
    [60, 292, 2.1, 68, 0.814, 370, 3, 19, 3, 3, 0]];
  const ARCANE_EXPLOSION = [[14, 32, 0.4, 19, 0.143, 75, 0], [22, 55, 0.6, 27, 0.143, 120, 0], [30, 94, 0.9, 35, 0.143, 185, 0],
    [38, 135, 0.9, 43, 0.143, 250, 0], [46, 183, 1.1, 51, 0.143, 315, 0], [54, 242, 1.3, 59, 0.143, 390, 0]];
  const CONE_OF_COLD = [[26, 97, 0.8, 31, 0.129, 210, 0], [34, 144, 1, 39, 0.129, 290, 0], [42, 204, 1.2, 47, 0.129, 380, 0],
    [50, 267, 1.3, 55, 0.129, 465, 0], [58, 340, 1.5, 63, 0.129, 555, 0]];
  const FROST_NOVA = [[10, 20, 0.5, 15, 0.029, 55, 0], [26, 34, 0.5, 31, 0.029, 85, 0], [40, 53, 0.5, 45, 0.029, 115, 0],
    [54, 73, 0.5, 59, 0.029, 145, 0]];
  const BLAST_WAVE = [[30, 163, 1, 36, 0.129, 215, 0], [36, 212, 1.2, 42, 0.129, 270, 0], [44, 293, 1.4, 50, 0.129, 355, 0],
    [52, 389, 1.6, 58, 0.129, 450, 0], [60, 493, 1.9, 66, 0.129, 545, 0]];
  const ICE_BARRIER = [[40, 431, 2.8, 46, 305], [46, 542, 3.2, 52, 360], [52, 671, 3.6, 58, 420], [58, 811, 4, 64, 480]];
  const TABLES = { Frostbolt: FROSTBOLT, Fireball: FIREBALL, ArcaneMissiles: ARCANE_MISSILES, FireBlast: FIRE_BLAST,
    Scorch: SCORCH, Pyroblast: PYROBLAST, ArcaneBlast: ARCANE_BLAST, IceLance: ICE_LANCE, FrostfireBolt: FROSTFIRE,
    ArcaneExplosion: ARCANE_EXPLOSION, ConeOfCold: CONE_OF_COLD, FrostNova: FROST_NOVA, BlastWave: BLAST_WAVE };
  const TABLE_NAMES = Object.keys(TABLES);
  const SCHOOL = { Frostbolt: 'frost', Fireball: 'fire', ArcaneMissiles: 'arcane', FireBlast: 'fire', Scorch: 'fire',
    Pyroblast: 'fire', ArcaneBlast: 'arcane', IceLance: 'frost', FrostfireBolt: 'frostfire', ArcaneExplosion: 'arcane',
    ConeOfCold: 'frost', FrostNova: 'frost', BlastWave: 'fire' };
  const TALENT_SPELL = { Pyroblast: 'Pyroblast', ArcaneBlast: 'ArcaneBlast', IceLance: 'IceLance', BlastWave: 'BlastWave' };
  const COOLDOWN = { FireBlast: 8.0, ConeOfCold: 10.0, FrostNova: 25.0, BlastWave: 45.0 };
  const INSTANT = ['FireBlast', 'IceLance', 'ArcaneExplosion', 'ConeOfCold', 'FrostNova', 'BlastWave'];
  const CHILLS = ['Frostbolt', 'FrostfireBolt', 'ConeOfCold'];
  const AB_MASK = ['Frostbolt', 'Fireball', 'FireBlast', 'Scorch', 'Pyroblast', 'IceLance', 'FrostfireBolt', 'ArcaneExplosion',
    'ConeOfCold', 'FrostNova', 'BlastWave'];
  const HOT_STREAK_FROM = ['Fireball', 'FrostfireBolt', 'FireBlast', 'Scorch'];
  const DOT_NAME = { Fireball: 'FireballDoT', Pyroblast: 'PyroblastDoT', FrostfireBolt: 'FrostfireBoltDoT' };

  // conjured water and food: [learn, per 5 s, duration s, conjure mana, count at learn, count per level, max level]
  const WATER = [[4, 42, 18, 60, 2, 2, 13], [10, 104, 21, 105, 2, 2, 19], [20, 174, 24, 180, 2, 2, 29],
    [30, 249, 27, 285, 2, 2, 39], [40, 332, 30, 420, 2, 2, 49], [50, 489, 30, 585, 2, 2, 59], [60, 700, 30, 780, 10, 2, 65]];
  const MOUNTAIN_WATER = [60, 850, 30, 845, 20, 2, 65];
  const FOOD = [[6, 17, 18, 60, 2, 2, 15], [12, 58, 21, 105, 2, 2, 21], [22, 115, 24, 180, 2, 2, 31],
    [32, 162, 27, 285, 2, 2, 41], [42, 232, 30, 420, 2, 2, 51], [52, 358, 30, 585, 2, 2.25, 61], [60, 530, 30, 705, 10, 2, 65]];
  const STACK = 20, WOWHEAD_DRINK = 25.0 / 26.0;
  const GEMS = [[28, 530, 400], [38, 800, 600], [48, 1130, 850], [58, 1470, 1100]];
  const POTIONS = [[5, 160, 40], [14, 320, 120], [22, 520, 480], [31, 800, 480], [41, 1200, 1600], [49, 1800, 6000]];
  const POTION_NAMES = ['Minor Mana Potion', 'Lesser Mana Potion', 'Mana Potion', 'Greater Mana Potion',
    'Superior Mana Potion', 'Major Mana Potion'];

  // ---------------------------------------------------------------- talent values per rank (data/talents.json)
  const TV = {
    WandSpecialization: [.13, .25], ArcaneFocus: [.01, .02, .03, .04, .05],
    ImprovedChanneling: [.20, .40, .60, .80, 1.0], ImprovedChannelingAB: [.14, .28, .42, .56, .70],
    ArcaneConcentration: [.02, .04, .06, .08, .10], ArcaneImpact: [.02, .04, .06], ArcaneMeditation: [.17, .33, .50],
    ArcaneMind: [.02, .04, .06, .08, .10], ArcaneMindCrit: [.2, .4, .6, .8, 1.0], ArcaneInstability: [.01, .02, .03],
    WakeOfFire: [1.0, 2.0], WakeOfFireCrit: [.25, .50], Incineration: [.02, .04, .06], ImprovedFireball: [.1, .2, .3, .4, .5],
    Ignite: [.08, .16, .24, .32, .40], Impact: [.03, .07, .10], BurningSoul: [.23, .47, .70], ImprovedScorch: [.33, .67, 1.0],
    MasterOfElements: [.10, .20, .30], CriticalMass: [.02, .04, .06], FirePower: [.02, .04, .06, .08, .10],
    ImprovedFrostbolt: [.1, .2, .3, .4, .5], ElementalPrecision: [.01, .02, .03, .04, .05],
    IceShards: [.2, .4, .6, .8, 1.0], Permafrost: [.11, .22, .33], PermafrostSlow: [.03, .07, .10],
    ImprovedFrostNova: [2.0, 4.0], Frostbite: [.05, .10, .15], PiercingIce: [.02, .04, .06],
    FrostChanneling: [.05, .10, .15], Shatter: [.17, .33, .50], ImprovedConeOfCold: [.12, .23, .35],
    FingersOfFrost: [1, 2], WintersChill: [.20, .40, .60, .80, 1.0], ArcaneGeometry: [3.0, 6.0], FlameThrowing: [3.0, 6.0],
    ArcticReach: [.10, .20] };
  const FOF_CHANCE = 0.15, WC_CRIT = 0.02, HOT_STREAK_CUT = 0.25, FV_STEP = 0.03;
  const BARRAGE = { ArcaneBlast: 0.40, Fireball: 0.20, Frostbolt: 0.20, FrostfireBolt: 0.20 };

  function tv(ch, key, table) {
    const r = ch.talents[key] || 0;
    return r > 0 ? TV[table || key][r - 1] : 0;
  }
  function rankRows(name, L, topRanks) {
    const rows = TABLES[name].filter(r => r[0] <= L);
    if (topRanks && TOME[name] && TOME[name][0] <= L) rows.push(TOME[name]);
    return rows;
  }
  function ddAvg(row, L, mode) {
    if (mode === 'base') return row[1];
    return Math.floor(row[1] + row[2] * (Math.min(L, row[3]) - row[0]) + 1e-9);
  }
  function below20(row, on) {
    return on && row[0] < 20 ? 1 - 0.0375 * (20 - row[0]) : 1.0;
  }
  // low_ranks (test m13): 'measured' and 'full' keep the stored coefficient (client; DoubleZug's level 18 and 19
  // beta measurements); 'classic' is Classic's below-20 cut; 'tbc' is (rank max level + 6) / L, capped at 1
  const LOW_RANKS = ['measured', 'full', 'classic', 'tbc'];
  function coefFactor(row, L, lowRanks) {
    if (lowRanks === 'classic') return below20(row, true);
    if (lowRanks === 'tbc') return Math.min(1.0, (row[3] + 6) / L);
    return 1.0;
  }
  // lower ranks only at level 19 and below by default (measured there); every level with the other choices
  const downrankAllowed = (L, lowRanks) => L <= 19 || lowRanks !== 'measured';
  const g0 = (o, key, dflt) => (o[key] === undefined ? dflt : o[key]);

  // ---------------------------------------------------------------- character (Char defaults as models/leveling_sim.py)
  const CHAR_DEFAULTS = { level: 1, race: 'none', talents: {}, sp: 0.0, crit: 0.05, crit_bonus: 0.0, hit_base: 0.96,
    max_hp: 500.0, max_mana: 500.0, base_mana: 100.0, intellect: 0.0, spirit: 0.0, mreg: 0.0, hreg: 0.0, hreg_combat: 0.0,
    cast_regen: 0.0, haste: 1.0, dmg_mult: 1.0, wand_dps: 0.0, totg: false, mob_dps: 0.0, mob_speed: 8.0, pull_gap: 25.0,
    player_speed: 7.0, step_s: 2.0, swing: 2.0, pushback_s: 0.5, nova_break: 0.5, fb_break: 0.5, kite: true, il_coef: 0.143,
    dd_mode: 'scaled', below20: false, low_ranks: 'measured', top_ranks: false, potions: true, gems: true, evocation: true,
    wowhead_drinks: false, spirit_drink: true, mountain_water: false, thrill: 0.0, leyline: 'short', cannibalize: 0.0,
    rapid_regen: false, armor_chill: true, armor_slow: 0.25, frostbite_armor: true };

  // ---------------------------------------------------------------- fight
  function pickRow(ch, name, pol) {
    if (TALENT_SPELL[name] && !(ch.talents[TALENT_SPELL[name]] || 0)) return null;
    const rows = rankRows(name, ch.level, ch.top_ranks);
    if (!rows.length) return null;
    const dr = name === pol.filler ? g0(pol, 'dr', 0) : 0;
    if (dr === 'r1') return rows[0];
    return rows[Math.max(0, rows.length - 1 - dr)];
  }

  function fightConsts(ch, pol) {
    const T = ch.talents, L = ch.level;
    const ai = tv(ch, 'ArcaneInstability');
    const k = { row: {}, avg: {}, coef: {}, smult: {}, crit: {}, crit_dot: {}, cm: {}, hit: {}, cost: {}, base_cost: {}, ct: {}, prot: {} };
    for (const name of TABLE_NAMES) {
      const row = pickRow(ch, name, pol);
      k.row[name] = row;
      if (!row) continue;
      const sc = SCHOOL[name];
      const fire = sc === 'fire' || sc === 'frostfire', frost = sc === 'frost' || sc === 'frostfire', arc = sc === 'arcane';
      k.avg[name] = ddAvg(row, L, ch.dd_mode);
      const rule = ch.below20 ? 'classic' : ch.low_ranks;
      k.coef[name] = (name === 'IceLance' ? ch.il_coef : row[4]) * coefFactor(row, L, rule);
      let add = ai + (fire ? tv(ch, 'FirePower') : 0) + (frost ? tv(ch, 'PiercingIce') : 0);
      if (name === 'ConeOfCold') add += tv(ch, 'ImprovedConeOfCold');
      k.smult[name] = (1 + add) * ch.dmg_mult;
      let c = ch.crit + ch.crit_bonus + ai + (fire ? tv(ch, 'CriticalMass') : 0) + (arc ? tv(ch, 'ArcaneImpact') : 0);
      k.crit_dot[name] = c;
      if (name === 'FireBlast' || name === 'Scorch' || name === 'ArcaneBlast' || name === 'IceLance') c += tv(ch, 'Incineration');
      k.crit[name] = c;
      const bonus = (frost ? tv(ch, 'IceShards') : 0) + (arc ? tv(ch, 'ArcaneMind', 'ArcaneMindCrit') : 0);
      k.cm[name] = 1 + 0.5 * (1 + bonus);
      k.hit[name] = Math.min(0.99, ch.hit_base + (arc ? tv(ch, 'ArcaneFocus') : tv(ch, 'ElementalPrecision')));
      k.base_cost[name] = row[5];
      k.cost[name] = row[5] * (1 - (frost ? tv(ch, 'FrostChanneling') : 0));
      let ct = INSTANT.includes(name) || name === 'ArcaneMissiles' ? 0.0 : row[6];
      if (name === 'Frostbolt') ct -= tv(ch, 'ImprovedFrostbolt');
      if (name === 'Fireball' || name === 'FrostfireBolt') ct -= tv(ch, 'ImprovedFireball');
      k.ct[name] = Math.max(0.0, ct) / ch.haste;
      k.prot[name] = fire ? tv(ch, 'BurningSoul') : 0.0;
    }
    if (k.row.ArcaneMissiles) k.prot.ArcaneMissiles = tv(ch, 'ImprovedChanneling');
    if (k.row.ArcaneBlast) k.prot.ArcaneBlast = tv(ch, 'ImprovedChanneling', 'ImprovedChannelingAB');
    k.cd = { FireBlast: COOLDOWN.FireBlast - tv(ch, 'WakeOfFire'), ConeOfCold: COOLDOWN.ConeOfCold,
      FrostNova: COOLDOWN.FrostNova - tv(ch, 'ImprovedFrostNova'), BlastWave: COOLDOWN.BlastWave };
    const fb = k.row.Frostbolt, pf = tv(ch, 'Permafrost');
    k.chill_s = { Frostbolt: (fb ? FROSTBOLT_SLOW_S[fb[0]] : 0) * (1 + pf), FrostfireBolt: 9.0 * (1 + pf), ConeOfCold: 6.0 * (1 + pf) };
    k.slow = 0.40 + tv(ch, 'Permafrost', 'PermafrostSlow');   // the chill's movement slow, Permafrost's extra
    k.p_cc = tv(ch, 'ArcaneConcentration');
    k.moe = tv(ch, 'MasterOfElements');
    k.ignite = tv(ch, 'Ignite');
    k.impact = tv(ch, 'Impact');
    k.isc = tv(ch, 'ImprovedScorch');
    k.fb_chance = tv(ch, 'Frostbite');
    k.fof_n = tv(ch, 'FingersOfFrost');
    k.wc_chance = tv(ch, 'WintersChill');
    k.wc_cap = T.WintersChill || 0;
    k.shatter = tv(ch, 'Shatter');
    k.hs = !!((T.HotStreak || 0) && k.row.Pyroblast);
    k.mb = !!((T.MissileBarrage || 0) && k.row.ArcaneMissiles);
    k.wake_crit = tv(ch, 'WakeOfFire', 'WakeOfFireCrit');
    k.wandspec = 1 + tv(ch, 'WandSpecialization');
    // range talents lengthen the pull (Arctic Reach: Frostbolt only, +10/20% of its 30 yd range)
    const ag = tv(ch, 'ArcaneGeometry'), ft = tv(ch, 'FlameThrowing'), ar = 30.0 * tv(ch, 'ArcticReach');
    k.reach = {};
    for (const n of TABLE_NAMES) {
      k.reach[n] = (SCHOOL[n] === 'arcane' ? ag : 0.0) + (SCHOOL[n] === 'fire' || SCHOOL[n] === 'frostfire' ? ft : 0.0) +
        (n === 'Frostbolt' ? ar : 0.0);
    }
    const ibr = (T.IceBarrier || 0) ? ICE_BARRIER.filter(r => r[0] <= L) : [];
    const ib = ibr.length ? ibr[ibr.length - 1] : null;
    k.ib = ib ? Math.floor(ib[1] + ib[2] * (Math.min(L, ib[3]) - ib[0]) + 1e-9) : 0.0;
    k.ib_cost = ib ? ib[4] : 0.0;
    k.p_pom = (T.PresenceOfMind || 0) ? g0(pol, 'p_pom', 0.0) : 0.0;
    k.p_ap = (T.ArcanePower || 0) ? g0(pol, 'p_ap', 0.0) : 0.0;
    k.p_comb = (T.Combustion || 0) && L >= 40 ? g0(pol, 'p_comb', 0.0) : 0.0;
    k.p_bf = ch.race === 'orc' ? g0(pol, 'p_bf', 0.0) : 0.0;
    k.p_bz = ch.race === 'troll' ? g0(pol, 'p_bz', 0.0) : 0.0;
    k.p_eu = ch.race === 'gnome' ? g0(pol, 'p_eu', 0.0) : 0.0;
    k.p_ib = k.ib ? g0(pol, 'p_ib', 0.0) : 0.0;
    k.wake = (T.WakeOfFire || 0) ? g0(pol, 'wake', 0.0) : 0.0;
    k.prio = pol.prio.slice();
    return k;
  }

  // chance the mob is held now: kind 1 freezes only, 2 stuns only, 0 either, 3 Frost Nova's root only
  // (a hold: [end, chance it holds, break chance per damage event, is a freeze, 'nova' | 'frostbite' | 'stun'])
  function holdQ(holds, t, kind) {
    let q = 1.0;
    for (const h of holds) {
      if (h[0] > t && (kind === 0 || (kind === 3 && h[4] === 'nova') || (kind !== 3 && (kind === 1) === h[3]))) q *= 1 - h[1];
    }
    return 1 - q;
  }

  function simulate(ch, mobHpV, pol, maxTime, phase, kIn) {
    maxTime = maxTime === undefined ? MAX_TIME : maxTime;
    phase = phase === undefined ? 0.5 : phase;
    const k = kIn || fightConsts(ch, pol);   // never changed during a fight, so callers may share it
    const S = { casts: {}, dmg: {}, mana_spent: 0.0, taken: 0.0, absorbed: 0.0, healed: 0.0, dead: false };
    const st = { t: 0.0, hp: mobHpV, php: ch.max_hp, mana: ch.max_mana, absorb: 0.0, gcd: 0.0, wand: false, step: -1.0,
      last_spend: -99.0, engaged: false, pulled: false, ib_done: false, gap: ch.pull_gap,
      cd: { FireBlast: 0.0, ConeOfCold: 0.0, FrostNova: 0.0, BlastWave: 0.0 },
      chill_until: -1.0, chill_p: 0.0, daze_until: -1.0, daze_p: 0.0, fb: k.fb_chance ? phase : 0.0,
      fof: k.fof_n ? phase : 0.0, wc: 0.0, hs: k.hs ? 3.0 * phase : 0.0, mb: k.mb ? phase : 0.0,
      cc: 0.0, ab: 0, ab_until: -1.0, fv: 0.0, eu: 3, comb_bonus: 0.0, comb_crits: 0.0, wake_used: false,
      pom_used: false, swing: 0.0, armor_until: -1.0 };
    const holds = [];      // [end time, chance it holds, break chance per damage event, is a freeze]
    const dots = {};
    const ign = [];        // [due time, amount, chance the tick exists]
    let cast = null, chan = null;

    const breakHolds = p => { for (const h of holds) if (h[2] > 0 && h[0] > st.t) h[1] *= 1 - h[2] * p; };
    const chillProcs = p => {
      if (k.fb_chance) {
        st.fb += p * k.fb_chance;
        if (st.fb >= 1) { st.fb -= 1; holds.push([st.t + 5.0, 1.0, ch.fb_break, true, 'frostbite']); }
      }
      if (k.fof_n) st.fof = Math.min(k.fof_n, st.fof + p * FOF_CHANCE * k.fof_n);
    };
    const deal = (name, x) => { st.hp -= x; S.dmg[name] = (S.dmg[name] || 0.0) + x; };
    const heal = x => { st.php = Math.min(ch.max_hp, st.php + x); S.healed += x; };
    const spNow = () => (st.t < 15.0 ? ch.sp * (1 + 0.1 * k.p_bf) : ch.sp);
    const abNow = () => (st.t <= st.ab_until ? st.ab : 0);
    const costFull = a => {
      if (a === 'Barrage') return 0.0;
      if (a === 'IceBarrier') return k.ib_cost;
      const name = a === 'HotPyro' ? 'Pyroblast' : a;
      let c = name === 'ArcaneBlast' ? AB_COST * ch.base_mana * (1 + 1.75 * abNow()) : k.cost[name];
      if (st.t < 15.0) c *= 1 + 0.3 * k.p_ap;
      if (st.eu > 0) c *= 1 - 0.1 * k.p_eu;
      return c;
    };
    const live = (name, fire) => {
      let m = st.t < 15.0 ? 1 + 0.3 * k.p_ap : 1.0;
      if (fire) m *= 1 + FV_STEP * st.fv;
      return m;
    };
    const afterHit = (name, hit, pcrit, ccUsed, costPaidFull) => {
      const sc = SCHOOL[name];
      const fire = sc === 'fire' || sc === 'frostfire', frost = sc === 'frost' || sc === 'frostfire';
      st.engaged = true;
      breakHolds(hit);
      if (k.p_cc) st.cc = 1 - (1 - st.cc) * (1 - hit * k.p_cc);
      if (k.moe && (fire || frost) && costPaidFull > 0) {
        st.mana = Math.min(ch.max_mana, st.mana + k.base_cost[name] * k.moe * hit * pcrit * (1 - ccUsed));
      }
      if (ch.totg) {
        const x = 0.1 * hit * 0.05 * ch.max_hp;
        deal('TouchOfTheGrave', x);
        heal(x);
      }
      if (fire && k.impact) holds.push([st.t + 2.0, hit * k.impact, 0.0, false, 'stun']);
      if (frost && k.wc_cap) st.wc = Math.min(k.wc_cap, st.wc + hit * k.wc_chance);
    };
    const land = (name, ccUsed, eu, costPaidFull, missile) => {
      const t = st.t;
      const sc = SCHOOL[name];
      const fire = sc === 'fire' || sc === 'frostfire';
      const hit = k.hit[name];
      let f = holdQ(holds, t, 1);
      if (!missile && st.fof >= 1) { st.fof -= 1; f = 1.0; }
      let c = k.crit[name];
      if (name === 'Frostbolt' || name === 'IceLance') c += WC_CRIT * st.wc;
      if (fire && k.p_comb && st.comb_crits < 4) c += k.p_comb * st.comb_bonus;
      if (name === 'FireBlast' && !st.wake_used && t < k.wake) { c += k.wake_crit; st.wake_used = true; }
      const m = k.cm[name];
      const cn = Math.min(1.0, c), cf = Math.min(1.0, c + k.shatter);
      const il = name === 'IceLance' ? 4.0 : 1.0;
      let x = (k.avg[name] + k.coef[name] * spNow()) * k.smult[name] * live(name, fire) * (1 + 0.1 * eu);
      if (AB_MASK.includes(name)) { x *= 1 + 0.1 * abNow(); st.ab = 0; }
      const ev = (1 - f) * (1 + cn * (m - 1)) + f * il * (1 + cf * (m - 1));
      deal(name, x * hit * ev);
      const pcrit = (1 - f) * cn + f * cf;
      if (fire && k.ignite) {
        const owed = k.ignite * x * hit * m * pcrit;
        ign.push([t + 2.0, owed / 2, hit * pcrit]);
        ign.push([t + 4.0, owed / 2, hit * pcrit]);
      }
      if (fire && k.p_comb && st.comb_crits < 4) {
        st.comb_crits += hit * Math.min(1.0, k.crit[name] + st.comb_bonus);
        st.comb_bonus += 0.1 * hit;
      }
      if (HOT_STREAK_FROM.includes(name) && k.hs) st.hs = Math.min(3.0, st.hs + hit * pcrit);
      afterHit(name, hit, pcrit, ccUsed, costPaidFull);
      if (missile) return;
      if (CHILLS.includes(name)) {
        st.chill_until = t + k.chill_s[name];
        st.chill_p = hit;
        chillProcs(hit);
      }
      if (name === 'FrostNova') holds.push([t + 8.0, hit, ch.nova_break, true, 'nova']);
      if (name === 'BlastWave') { st.daze_until = t + 6.0; st.daze_p = hit; }
      if (name === 'Scorch' && k.isc) st.fv = Math.min(5.0, st.fv + hit * k.isc);
      if (name === 'ArcaneBlast') { st.ab = Math.min(4, abNow() + 1); st.ab_until = t + 8.0; }
      if (k.mb && BARRAGE[name] !== undefined) st.mb = Math.min(1.0, st.mb + BARRAGE[name]);
      if (DOT_NAME[name]) {
        const row = k.row[name];
        const per = (row[7] + row[10] * spNow()) * k.smult[name] * hit * (1 + Math.min(1.0, k.crit_dot[name]) * (m - 1));
        dots[name] = { next: t + row[9], left: row[8], per, period: row[9], fire, p: hit };
      }
    };
    const tickDots = t => {
      for (const name in dots) {   // insertion order, as the Python dict; deleting the current key is safe
        const d = dots[name];
        if (t < d.next - 1e-9) continue;
        deal(DOT_NAME[name], d.per * live(name, d.fire));
        breakHolds(d.p);
        d.left -= 1;
        d.next += d.period;
        if (d.left <= 0) delete dots[name];
      }
      let i = 0;
      while (i < ign.length) {
        if (t >= ign[i][0] - 1e-9) {
          deal('Ignite', ign[i][1]);
          breakHolds(ign[i][2]);
          ign.splice(i, 1);
        } else i += 1;
      }
    };
    const tickChannel = t => {
      const c = chan;
      if (!c || t < c.next - 1e-9) return;
      land('ArcaneMissiles', c.cc, c.eu, c.cost, true);
      c.left -= 1;
      c.next += c.period;
      if (c.left <= 0) chan = null;
    };
    const act = (a, t) => {
      if (a === 'Wand') { st.wand = true; st.pulled = true; return; }
      st.wand = false;
      if (a === 'Step') { st.step = t + ch.step_s; S.casts.Step = (S.casts.Step || 0) + 1; return; }
      const full = costFull(a);
      const ccUsed = full > 0 ? st.cc : 0.0;
      const paid = full * (1 - ccUsed);
      if (full > 0) { st.cc = 0.0; st.last_spend = t; }
      st.mana -= paid;
      S.mana_spent += paid;
      S.casts[a] = (S.casts[a] || 0) + 1;
      st.gcd = t + GCD;
      if (a === 'IceBarrier') { st.ib_done = true; st.absorb = k.ib * k.p_ib; return; }
      if (!st.pulled) st.gap += k.reach[a === 'HotPyro' ? 'Pyroblast' : (a === 'Barrage' ? 'ArcaneMissiles' : a)];
      st.pulled = true;
      let eu = 0.0;
      if (st.eu > 0) { eu = k.p_eu; st.eu -= 1; }
      if (a === 'Barrage') {
        st.mb -= 1;
        const row = k.row.ArcaneMissiles;
        chan = { next: t + 0.5, left: row[6], period: 0.5, cc: 0.0, eu, cost: 0.0, lost: 0.0 };
        return;
      }
      if (a === 'ArcaneMissiles') {
        const row = k.row.ArcaneMissiles;
        let per = 1.0 / ch.haste;
        if (t < 10.0) per *= 1 - k.p_bz * (1 - 1 / 1.1);
        chan = { next: t + per, left: row[6], period: per, cc: ccUsed, eu, cost: full, lost: 0.0 };
        return;
      }
      let name = a;
      if (a === 'HotPyro') { name = 'Pyroblast'; st.hs -= 3; }
      if (COOLDOWN[name] !== undefined) st.cd[name] = t + k.cd[name];
      let ct = k.ct[name] * (a === 'HotPyro' ? HOT_STREAK_CUT : 1.0);
      if (ct > 0 && t < 10.0) ct *= 1 - k.p_bz * (1 - 1 / 1.1);
      if (ct > 0 && !st.pom_used) { st.pom_used = true; ct *= 1 - k.p_pom; }
      if (ct > 0) cast = { end: t + ct, name, cc: ccUsed, eu, cost: full };
      else land(name, ccUsed, eu, full, false);
    };
    const mobTick = t => {
      if (!st.engaged) return;
      let qh = 1.0, qs = 1.0;   // holdQ kinds 0 and 2 in one pass
      for (const h of holds) {
        if (h[0] > t) { qh *= 1 - h[1]; if (!h[3]) qs *= 1 - h[1]; }
      }
      const hold = 1 - qh, stun = 1 - qs;
      const chill = t < st.chill_until ? st.chill_p * k.slow : 0.0;
      const daze = t < st.daze_until ? st.daze_p * 0.5 : 0.0;
      if (t < st.step) st.gap += ch.player_speed * DT;
      st.gap = Math.max(0.0, st.gap - ch.mob_speed * (1 - Math.max(chill, daze)) * (1 - hold) * DT);
      if (st.gap > 0) return;
      const swings = DT / ch.swing * (1 - stun) * (t < st.armor_until ? 1 - ch.armor_slow : 1.0);
      let x = ch.mob_dps * ch.swing * swings;
      if (st.absorb > 0) {
        const a = Math.min(st.absorb, x);
        st.absorb -= a;
        S.absorbed += a;
        x -= a;
      }
      st.php -= x;
      S.taken += x;
      if (ch.armor_chill) {
        st.swing += swings;
        if (st.swing >= 1) {
          st.swing -= 1;
          st.armor_until = t + 5.0;
          if (ch.frostbite_armor) chillProcs(1.0);
        }
      }
      if (ch.pushback_s <= 0 || st.absorb > 0) return;
      if (cast) cast.end += ch.pushback_s * swings * (1 - k.prot[cast.name]);
      else if (chan) {
        const c = chan;
        c.lost += swings * (1 - k.prot.ArcaneMissiles);
        if (c.lost >= 1) {
          c.lost -= 1;
          c.left -= 1;
          if (c.left <= 0) chan = null;
        }
      }
    };

    while (st.hp > 0 && st.t < maxTime) {
      const t = st.t;
      tickDots(t);
      tickChannel(t);
      const kc = cast;
      if (kc && t >= kc.end - 1e-9) { cast = null; land(kc.name, kc.cc, kc.eu, kc.cost, false); }
      mobTick(t);
      const rate = t >= st.last_spend + 5.0 ? ch.mreg : ch.mreg * ch.cast_regen;
      st.mana = Math.min(ch.max_mana, st.mana + rate * DT);
      if (ch.hreg_combat) st.php = Math.min(ch.max_hp, st.php + ch.hreg_combat * DT);
      const busy = cast !== null || chan !== null || t < st.step - 1e-9;
      if (st.wand && !busy) {
        const hit = Math.min(0.99, ch.hit_base);
        deal('Wand', ch.wand_dps * DT * hit * k.wandspec * ch.dmg_mult);
        st.engaged = true;
      }
      if (!busy && st.hp > 0) {
        if (wantStep(ch, st, holds, pol)) act('Step', t);
        else if (t >= st.gcd - 1e-9) act(choose(ch, pol, st, k, holds, mobHpV, costFull), t);
      }
      if (st.php <= 0) { S.dead = true; break; }
      st.t += DT;
    }
    S.ttk = st.t;
    S.killed = st.hp <= 0;
    S.feasible = S.killed && !S.dead;
    S.end_mana = st.mana;
    S.end_hp = st.php;
    S.last_spend = st.last_spend;
    return S;
  }

  function ready(step, st, k) {
    if (step === 'Wand') return true;
    if (!k.row[step]) return false;
    if (COOLDOWN[step] !== undefined) return st.t >= st.cd[step] - 1e-9;
    if (step === 'ArcaneBlast') return (st.t <= st.ab_until ? st.ab : 0) < 1;
    return true;
  }
  // step 'none' never, 'nova' only after Frost Nova's root, 'all' after any freeze; no policy: 'all' (v1)
  function wantStep(ch, st, holds, pol) {
    const mode = pol === undefined || pol === null ? 'all' : g0(pol, 'step', 'none');
    if (!ch.kite || mode === 'none' || !st.engaged || st.gap >= MELEE_GAP) return false;
    return holdQ(holds, st.t, mode === 'nova' ? 3 : 1) >= 0.5;
  }
  function choose(ch, pol, st, k, holds, mobHpV, costFull) {
    const t = st.t;
    const ok = a => a === 'Wand' || st.mana >= costFull(a) * (1 - st.cc);   // first candidate, in order, that fits
    if (!st.pulled) {
      if (pol.ib && k.ib && !st.ib_done && ok('IceBarrier')) return 'IceBarrier';
      if (pol.pull === 'Pyroblast' && k.row.Pyroblast && ok('Pyroblast')) return 'Pyroblast';
      if (pol.filler && k.row[pol.filler] && ok(pol.filler)) return pol.filler;
    }
    if (k.row.IceLance && (st.fof >= 1 || holdQ(holds, t, 1) >= 0.5) && ok('IceLance')) return 'IceLance';
    const near = st.engaged && st.gap <= MELEE_GAP;
    if (pol.nova && near && ready('FrostNova', st, k) && ok('FrostNova')) return 'FrostNova';
    if (k.hs && st.hs >= 3 && ok('HotPyro')) return 'HotPyro';
    if (k.mb && st.mb >= 1 && ok('Barrage')) return 'Barrage';
    if (pol.melee && near) {
      for (const s of MELEE_INSTANTS) if (ready(s, st, k) && ok(s)) return s;
    }
    if (pol.fin === 'Wand' && st.hp / mobHpV < FIN_BELOW) return 'Wand';
    for (const s of k.prio) if (ready(s, st, k) && ok(s)) return s;
    return 'Wand';
  }
  const MELEE_INSTANTS = ['ConeOfCold', 'BlastWave', 'ArcaneExplosion'];

  // ---------------------------------------------------------------- rest model (also for the AoE model)
  function conjRow(table, L) {
    const rows = table.filter(r => r[0] <= L);
    return rows.length ? rows[rows.length - 1] : table[0];
  }
  function conjCount(row, L) {
    return Math.min(STACK, Math.floor(row[4] + row[5] * (Math.max(row[0], Math.min(L, row[6])) - row[0]) + 1e-9));
  }
  function restSetup(ch) {
    const L = ch.level;
    const w = ch.mountain_water && L >= MOUNTAIN_WATER[0] ? MOUNTAIN_WATER : conjRow(WATER, L);
    const f = conjRow(FOOD, L);
    const scale = ch.wowhead_drinks ? WOWHEAD_DRINK : 1.0;
    const d = w[1] / 5.0 * scale, e = f[1] / 5.0 * scale;
    const totW = d * w[2], totF = e * f[2];
    const nW = conjCount(w, L), nF = conjCount(f, L);
    const mreg = ch.mreg, hreg = ch.hreg;
    const stack = ch.spirit_drink ? 1.0 : 0.0;
    const R = { d, e, D: d + mreg * stack, E: e + hreg * stack, kw: w[3] / (nW * totW), kf: f[3] / (nF * totF),
      tw: CONJURE_S / (nW * totW), tf: CONJURE_S / (nF * totF), water: w, food: f, acts: [] };
    const acts = R.acts;
    if (ch.evocation && L >= 20) acts.push(['Evocation', 8.0, 8.0 * 16 * mreg, 8.0 * hreg, 480.0, 1.0]);
    const pot = ch.potions ? POTIONS.filter(p => p[0] <= L) : [];
    if (pot.length) acts.push(['ManaPotion', 0.0, pot[pot.length - 1][1], 0.0, 120.0, 1.0]);
    const gem = ch.gems ? GEMS.filter(g => g[0] <= L) : [];
    if (gem.length) acts.push(['ManaGem', CONJURE_S, gem[gem.length - 1][2] - gem[gem.length - 1][1], 0.0, 120.0, 1.0]);
    if (ch.cannibalize > 0) {
      acts.push(['Cannibalize', 10.0, 0.35 * ch.max_mana + 10.0 * mreg, 0.35 * ch.max_hp + 10.0 * hreg, 120.0, ch.cannibalize]);
    }
    if (ch.rapid_regen) acts.push(['RapidRegeneration', 6.0, 6.0 * mreg, 0.5 * ch.max_hp + 6.0 * hreg, 180.0, 1.0]);
    if (ch.leyline === 'short') acts.push(['ReadLeyLine', 2.0, (2.0 + 15.0 * stack) * mreg, (2.0 + 15.0 * stack) * hreg, 120.0, 1.0]);
    return R;
  }
  function travelRegen(ch, ttk, lastSpend, travel) {
    return [ch.mreg * Math.max(0.0, Math.min(travel, ttk + travel - (lastSpend + 5.0))), ch.hreg * travel];
  }
  function restTime(R, M, H, use, spk) {
    let ta = 0.0, am = 0.0, bh = 0.0;
    for (const a of use) {
      const u = a[5] * spk / a[4];
      ta += u * a[1];
      am += u * a[2];
      bh += u * a[3];
    }
    const mr = Math.max(0.0, M - am), hr = Math.max(0.0, H - bh);
    const te = hr / R.E;
    const eaten = R.e * te;
    const td = (mr + R.kf * eaten) / (R.D - R.kw * R.d);
    const tc = R.tw * R.d * td + R.tf * eaten;
    return ta + tc + Math.max(td, te);
  }
  function restSolve(R, F, M, H, iters) {
    iters = iters === undefined ? 40 : iters;
    const acts = R.acts.filter(a => a[2] > 0 || a[3] > 0);
    let best = null;
    for (let mask = 0; mask < (1 << acts.length); mask++) {
      const use = acts.filter((a, i) => ((mask >> i) & 1) === 1);
      let spk = F + restTime(R, M, H, use, F);
      for (let j = 0; j < iters; j++) {
        const nxt = F + restTime(R, M, H, use, spk);
        const done = Math.abs(nxt - spk) <= 1e-12 * spk;
        spk = nxt;
        if (done) break;
      }
      let n = 0;
      for (const a of use) n += a[5] * spk / a[4];
      const score = spk + MIN_SAVE * n;
      if (best === null || score < best[2] - 1e-9) best = [spk, use, score];
    }
    const spk = best[0], use = best[1];
    const uses = {};
    for (const a of use) uses[a[0]] = a[5] * spk / a[4];
    let am = 0, bh = 0;
    for (const a of use) am += uses[a[0]] * a[2];
    for (const a of use) bh += uses[a[0]] * a[3];
    const te = Math.max(0.0, H - bh) / R.E;
    const td = (Math.max(0.0, M - am) + R.kf * R.e * te) / (R.D - R.kw * R.d);
    return { spk, rest: spk - F, uses, drink: td, eat: te };
  }
  function secondsPerKill(ch, mobHpV, pol, travel, phase, k, R) {
    travel = travel === undefined ? 8.0 : travel;
    const s = simulate(ch, mobHpV, pol, MAX_TIME, phase, k);
    const [tm, th] = travelRegen(ch, s.ttk, s.last_spend, travel);
    const M = Math.max(0.0, ch.max_mana - s.end_mana - tm - ch.thrill * ch.max_mana);
    const H = s.dead ? ch.max_hp : Math.max(0.0, ch.max_hp - s.end_hp - th - ch.thrill * ch.max_hp);
    const r = restSolve(R || restSetup(ch), s.ttk + travel, M, H);
    s.rest = r.rest; s.spk = r.spk; s.uses = r.uses;
    s.drink = r.drink; s.eat = r.eat;
    s.pots = r.uses.ManaPotion === undefined ? 0.0 : r.uses.ManaPotion;
    s.evo = r.uses.Evocation === undefined ? 0.0 : r.uses.Evocation;
    return s;
  }

  // ---------------------------------------------------------------- character by level (models/character.py)
  const BASE_MANA = [100, 110, 121, 118, 131, 145, 160, 161, 178, 196, 215, 220, 241, 263, 271, 295, 305, 331, 343, 371, 385,
    415, 431, 463, 481, 515, 535, 556, 592, 613, 634, 670, 691, 712, 733, 754, 790, 811, 832, 853, 874, 895,
    916, 937, 958, 979, 1000, 1021, 1042, 1048, 1069, 1090, 1111, 1117, 1138, 1159, 1165, 1186, 1192, 1213];
  const BASE_HP = [41, 47, 52, 67, 82, 97, 102, 117, 132, 137, 152, 167, 172, 187, 202, 207, 222, 237, 242, 257, 272, 277, 292,
    298, 315, 333, 342, 362, 373, 395, 418, 432, 457, 473, 500, 518, 547, 577, 598, 630, 653, 687, 712, 748, 775,
    813, 842, 882, 913, 955, 988, 1032, 1067, 1103, 1150, 1188, 1237, 1277, 1328, 1370];
  const BASE_STA = [20, 20, 21, 21, 21, 21, 22, 22, 22, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27, 28, 28, 28, 29,
    29, 30, 30, 30, 31, 31, 32, 32, 33, 33, 33, 34, 34, 35, 35, 36, 36, 37, 37, 38, 38, 39, 39, 40, 40, 41, 42,
    42, 43, 43, 44, 44, 45];
  const BASE_INT = [23, 24, 25, 27, 28, 29, 30, 31, 33, 34, 35, 37, 38, 39, 41, 42, 43, 45, 46, 48, 49, 51, 52, 54, 55, 57, 59,
    60, 62, 64, 65, 67, 69, 70, 72, 74, 76, 78, 80, 81, 83, 85, 87, 89, 91, 93, 95, 98, 100, 102, 104, 106, 108,
    111, 113, 115, 118, 120, 123, 125];
  const BASE_SPI = [22, 23, 24, 25, 27, 28, 29, 30, 31, 33, 34, 35, 36, 38, 39, 40, 42, 43, 44, 46, 47, 49, 50, 52, 53, 55, 56,
    58, 59, 61, 63, 64, 66, 68, 69, 71, 73, 75, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100, 102, 104,
    106, 109, 111, 113, 115, 118, 120];
  const CRIT_PER_INT = [0.00191999995, 0.00184599997, 0.00177800003, 0.00165500003, 0.00159999996, 0.00154800003,
    0.00150000001, 0.00145500002, 0.00137099996, 0.00133300002, 0.00123099994, 0.00109100004,
    0.00102099997, 0.00085700001, 0.000787, 0.00075000001, 0.00070600002, 0.00066700001, 0.00063199998,
    0.00059299998, 0.00057099998, 0.00053899997, 0.00052200002, 0.00049499999, 0.00047500001,
    0.00045699999, 0.000436, 0.000397, 0.00038099999, 0.00036599999, 0.00035799999, 0.00034500001,
    0.000336, 0.00032699999, 0.00031599999, 0.00030799999, 0.000298, 0.000291, 0.00028199999,
    0.00027600001, 0.00026999999, 0.00025300001, 0.00024699999, 0.000241, 0.000235, 0.000231, 0.000225,
    0.00022, 0.00021499999, 0.00021100001, 0.000207, 0.000203, 0.000199, 0.00019399999, 0.00019000001,
    0.000181, 0.00017699999, 0.00017499999, 0.00017100001, 0.000168];
  const BASE_SPELL_CRIT = 0.002;   // Classic Mage base spell crit (sim base_stats.go ClassBaseCritPercent)
  const ARCANE_INTELLECT = [[1, 2], [14, 7], [28, 15], [42, 22], [56, 31]];
  const RACES = { none: [0, 0, 0], human: [0, 0, 0], gnome: [3, 0, -1], skyborne: [1, 0, -1], orc: [-3, 3, 2], undead: [-2, 5, 1],
    troll: [-4, 1, 1] };
  const BASE_HIT = { 0: .96, 1: .95, 2: .94, 3: .83 };
  const GEAR = { int: 1.0, sta: 1.0, spi: 0.5 };
  const MOB_SPEED = 8.0, PULL_GAP = 25.0, STEP_S = 2.0, SWING_S = 2.0, PUSHBACK_S = 0.5, NOVA_BREAK = 0.5, ARMOR_SLOW = 0.25;
  const BEASTS = 0.4, HUMANOIDS = 0.4, ELEMENTALS = 0.1;
  const HP_MULTS = [0.9, 1.0, 1.1];
  const TRAVEL = 8.0;

  const mobHp = L => 18 * L + 0.62 * L * L;
  const mobDps = L => 0.035 * L * L;
  const arcaneIntellect = L => { const r = ARCANE_INTELLECT.filter(x => x[0] <= L); return r[r.length - 1][1]; };

  // o: internal (snake_case) options, as the keyword arguments of make_char in models/character.py
  function makeChar(L, tal, gear, race, o) {
    gear = gear === undefined ? 1 : gear;
    race = race || 'none';
    o = o || {};
    const r = RACES[race];
    const gInt = g0(o, 'gear_int', GEAR.int), gSta = g0(o, 'gear_sta', GEAR.sta), gSpi = g0(o, 'gear_spi', GEAR.spi);
    const intel = (BASE_INT[L - 1] + r[0] + gInt * L + arcaneIntellect(L)) * (tal.ArcaneMind ? 1 + TV.ArcaneMind[tal.ArcaneMind - 1] : 1);
    const spirit = (BASE_SPI[L - 1] + r[1] + gSpi * L) * (race === 'human' ? 1.05 : 1.0);
    const sta = BASE_STA[L - 1] + r[2] + gSta * L;
    const mana = (BASE_MANA[L - 1] + 20 + 15 * (intel - 20)) * (race === 'gnome' ? 1.05 : 1.0);
    const hp = BASE_HP[L - 1] + 20 + 10 * (sta - 20);
    const leyline = race === 'skyborne' ? g0(o, 'leyline', 'short') : 'off';
    const regen = leyline === 'long' ? 2.0 : 1.0;
    const hreg = (6 + 0.1 * spirit) / 2 * regen * (race === 'troll' ? 1.1 : 1.0);
    const mageArmor = L >= 34 && g0(o, 'armor', 'auto') === 'auto';
    const ma = mageArmor ? 0.5 : 0.0;
    const am = tal.ArcaneMeditation ? TV.ArcaneMeditation[tal.ArcaneMeditation - 1] : 0.0;
    const castRegen = g0(o, 'regen_stack', 'add') === 'add' ? Math.min(1.0, ma + am) : Math.max(ma, am);
    let dmg = 1.0;
    if (race === 'troll') dmg += 0.05 * g0(o, 'beast_share', BEASTS);
    if (race === 'skyborne') dmg += 0.05 * g0(o, 'elemental_share', ELEMENTALS);
    const keep = {};
    for (const key of ['pull_gap', 'mob_speed', 'player_speed', 'step_s', 'swing', 'pushback_s', 'nova_break',
      'fb_break', 'kite', 'il_coef', 'dd_mode', 'below20', 'low_ranks', 'top_ranks', 'potions',
      'gems', 'evocation', 'wowhead_drinks', 'spirit_drink', 'mountain_water']) if (o[key] !== undefined) keep[key] = o[key];
    if (keep.pull_gap === undefined) keep.pull_gap = PULL_GAP;
    if (keep.mob_speed === undefined) keep.mob_speed = MOB_SPEED;
    if (keep.step_s === undefined) keep.step_s = STEP_S;
    if (keep.swing === undefined) keep.swing = SWING_S;
    if (keep.pushback_s === undefined) keep.pushback_s = g0(o, 'pushback', true) ? PUSHBACK_S : 0.0;
    if (keep.nova_break === undefined) keep.nova_break = NOVA_BREAK;
    if (keep.fb_break === undefined) keep.fb_break = keep.nova_break;   // Frostbite's freeze has Frost Nova's aura row
    return Object.assign({}, CHAR_DEFAULTS, { level: L, race, talents: tal, sp: gear * L,
      crit: BASE_SPELL_CRIT + intel * CRIT_PER_INT[L - 1],
      crit_bonus: race === 'human' && g0(o, 'sword', true) && L >= 21 ? 0.02 : 0.0,
      hit_base: BASE_HIT[g0(o, 'level_diff', 0)], max_hp: hp, max_mana: mana, base_mana: BASE_MANA[L - 1],
      intellect: intel, spirit, mreg: (6.25 + spirit / 8) * regen, hreg,
      hreg_combat: race === 'troll' ? 0.1 * hreg : 0.0, cast_regen: castRegen,
      haste: race === 'skyborne' ? 1.01 : 1.0, dmg_mult: dmg, wand_dps: 0.9 * L + 3, totg: race === 'undead',
      mob_dps: mobDps(L) * g0(o, 'mob_dps_mult', 1.0), thrill: 0.01 * g0(o, 'thrill', 0), leyline,
      cannibalize: race === 'undead' ? g0(o, 'humanoid_share', HUMANOIDS) : 0.0,
      rapid_regen: race === 'troll', armor_chill: !mageArmor, armor_slow: g0(o, 'armor_slow', ARMOR_SLOW),
      frostbite_armor: g0(o, 'frostbite_source', 'every') === 'every' }, keep);
  }

  // ---------------------------------------------------------------- rotations
  const P = (filler, ...prio) => ({ prio, filler });
  const POLICIES = [
    ['Frostbolt', P('Frostbolt', 'Frostbolt')],
    ['Fireball', P('Fireball', 'Fireball')],
    ['Arcane Missiles', P('ArcaneMissiles', 'ArcaneMissiles')],
    ['Fire Blast + Frostbolt', P('Frostbolt', 'FireBlast', 'Frostbolt')],
    ['Fire Blast + Fireball', P('Fireball', 'FireBlast', 'Fireball')],
    ['Fire Blast + Arcane Missiles', P('ArcaneMissiles', 'FireBlast', 'ArcaneMissiles')],
    ['Fire Blast + Scorch', P('Scorch', 'FireBlast', 'Scorch')],
    ['Frostfire Bolt', P('FrostfireBolt', 'FrostfireBolt')],
    ['Fire Blast + Frostfire Bolt', P('FrostfireBolt', 'FireBlast', 'FrostfireBolt')],
    ['Arcane Blast + Frostbolt', P('Frostbolt', 'ArcaneBlast', 'Frostbolt')],
    ['Arcane Blast + Fireball', P('Fireball', 'ArcaneBlast', 'Fireball')],
    ['Fire Blast + Wand', P(null, 'FireBlast', 'Wand')],
    ['Wand', P(null, 'Wand')],
  ];
  const BASE_LABEL = {
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
  };
  // longest tag first: policyLabel strips each tag it finds, so ' +Nova' comes after the tags that start with it
  const MOD_LABEL = [
    [' +Nova, step back after freezes', 'Frost Nova when the mob gets close, and step back after any freeze'],
    [' +Nova, step back', 'Frost Nova when the mob gets close, then step back'],
    [' +Nova', 'Frost Nova when the mob gets close (no stepping back)'],
    [' +step back after freezes', 'step back when Frostbite freezes the mob'],
    [' +melee instants', 'Cone of Cold, Blast Wave or Arcane Explosion when the mob is close'],
    [' +Pyroblast pull', 'open with Pyroblast'],
    [' +Ice Barrier', 'Ice Barrier before the pull'],
    [' +wand finish', 'wand the last 20%'],
    [' (1 rank down)', 'main spell one rank down'],
    [' (2 ranks down)', 'main spell two ranks down'],
    [' (rank 1)', 'main spell at rank 1'],
    [' +Ice Lance', 'Ice Lance on every freeze and Fingers of Frost charge'],
    [' +Hot Streak Pyroblast', 'a fast Pyroblast at 3 Hot Streak stacks'],
    [' +Missile Barrage', 'free Arcane Missiles on Missile Barrage'],
  ];
  const DOWNRANK = [[1, ' (1 rank down)'], [2, ' (2 ranks down)'], ['r1', ' (rank 1)']];
  const AUTO_TAGS = [['IceLance', ' +Ice Lance'], ['HotPyro', ' +Hot Streak Pyroblast'], ['Barrage', ' +Missile Barrage']];

  function policyLabel(name) {
    let base = name;
    const parts = [];
    for (const [tag, text] of MOD_LABEL) {
      if (base.includes(tag)) { base = base.replace(tag, ''); parts.push(text); }
    }
    return [BASE_LABEL[base] === undefined ? base : BASE_LABEL[base]].concat(parts).join(', ');
  }

  // talents the score responds to; the builder marks the rest "not in the score" (reasons in UNSCORED)
  const SCORED = ['WandSpecialization', 'ArcaneFocus', 'ImprovedChanneling', 'ArcaneConcentration', 'ArcaneGeometry',
    'ArcaneImpact', 'ArcaneBlast', 'ArcaneMeditation', 'MissileBarrage', 'PresenceOfMind', 'ArcaneMind',
    'ArcaneInstability', 'ArcanePower', 'WakeOfFire', 'Incineration', 'ImprovedFireball', 'Ignite',
    'FlameThrowing', 'Impact', 'BurningSoul', 'Pyroblast', 'ImprovedScorch', 'HotStreak', 'MasterOfElements',
    'CriticalMass', 'BlastWave', 'FirePower', 'Combustion', 'ImprovedFrostbolt', 'ElementalPrecision',
    'IceShards', 'Permafrost', 'ImprovedFrostNova', 'Frostbite', 'PiercingIce', 'FrostChanneling', 'IceLance',
    'ArcticReach', 'Shatter', 'ImprovedConeOfCold', 'FingersOfFrost', 'WintersChill', 'IceBarrier'];
  const UNSCORED = {
    ArcaneSubtlety: 'mob resistances are not modelled',
    MagicAbsorption: 'resistances are not modelled',
    ArcaneResilience: 'mob damage is a flat rate, not armor-based',
    FrostWarding: 'mob damage is a flat rate, not armor-based',
    ArcaneShielding: 'Mana Shield is not cast',
    ImprovedCounterspell: 'the model has no caster mobs',
    ImprovedFireWard: 'the model has no caster mobs',
    ImprovedFlamestrike: 'area spell (the AoE model)',
    ImprovedBlizzard: 'area spell (the AoE model)',
    IceBlock: 'defensive',
    ColdSnap: '10 min cooldown, about one extra Frost Nova per 15 kills, not modelled',
  };

  function usableSteps(pol, ch) {
    for (const s of pol.prio) if (s !== 'Wand' && !pickRow(ch, s, {})) return null;
    return pol.prio.join(',');
  }
  // modifier groups (models/character.py mod_groups): each is off or one option [policy keys, name label]
  function modGroups(L, tal, ch) {
    const groups = [], ctl = [];
    if (L >= 10) {
      ctl.push([{ nova: true }, ' +Nova']);
      if (ch.kite) ctl.push([{ nova: true, step: 'nova' }, ' +Nova, step back']);
    }
    if (L >= 10 && ch.kite && tal.Frostbite) ctl.push([{ nova: true, step: 'all' }, ' +Nova, step back after freezes']);
    if (ch.kite && tal.Frostbite) ctl.push([{ step: 'all' }, ' +step back after freezes']);
    if (ctl.length) groups.push(ctl);
    if (L >= 14) groups.push([[{ melee: true }, ' +melee instants']]);
    if (tal.Pyroblast && L >= 20) groups.push([[{ pull: 'Pyroblast' }, ' +Pyroblast pull']]);
    if (tal.IceBarrier && L >= 40) groups.push([[{ ib: true }, ' +Ice Barrier']]);
    groups.push([[{ fin: 'Wand' }, ' +wand finish']]);
    return groups;
  }
  function rankGroup(L, pol, ch, downrank) {
    if (downrank === false || !pol.filler || !downrankAllowed(L, ch.below20 ? 'classic' : ch.low_ranks)) return [];
    const n = rankRows(pol.filler, L, ch.top_ranks).length;
    return DOWNRANK.filter(([dr]) => n > (dr === 'r1' ? 1 : dr)).map(([dr, label]) => [{ dr }, label]);
  }
  function needsRef(ch, pol) {
    const T = ch.talents;
    return !!(ch.race === 'orc' || ch.race === 'troll' || ch.race === 'gnome' || T.PresenceOfMind || T.ArcanePower ||
      (T.Combustion && ch.level >= 40) || (T.WakeOfFire && pol.prio.includes('FireBlast')) || pol.ib);
  }
  const AVG_KEYS = ['spk', 'ttk', 'rest', 'taken', 'mana_spent', 'pots', 'evo', 'drink', 'eat'];
  function runPolicy(chFn, L, pol, hpMults, travel) {
    const avg = (p, mults) => {
      mults = mults || hpMults;
      const n = mults.length, ch = chFn();
      const k = fightConsts(ch, p), R = restSetup(ch);
      const rs = mults.map((m, i) => secondsPerKill(ch, mobHp(L) * m, p, travel, (2 * i + 1) / (2 * n), k, R));
      const out = Object.assign({}, rs[0]);
      for (const key of AVG_KEYS) out[key] = rs.reduce((a, r) => a + r[key], 0) / rs.length;
      out.feasible = rs.every(r => r.feasible);
      out.casts_all = {};
      for (const r of rs) for (const a in r.casts) out.casts_all[a] = (out.casts_all[a] || 0) + r.casts[a];
      return out;
    };
    const ch = chFn();
    if (!needsRef(ch, pol)) return avg(pol);
    const r = avg(pol, [1.0]);   // first pass at mob health x1.0 alone: the kill cycle for the cooldown shares
    const ref = r.spk;
    const p2 = Object.assign({}, pol, { p_pom: Math.min(1.0, ref / 180), p_ap: Math.min(1.0, ref / 180),
      p_comb: Math.min(1.0, ref / 180), p_bf: Math.min(1.0, ref / 120), p_bz: Math.min(1.0, ref / 180),
      p_eu: Math.min(1.0, ref / 120), p_ib: Math.min(1.0, ref / 30), wake: 30.0 - travel - r.rest });
    return avg(p2);
  }
  function better(a, b) {
    if (b === null) return true;
    if (a.feasible !== b.feasible) return a.feasible;
    return a.spk < b.spk - 1e-9;
  }
  function compose(pol, name, gs, choice) {
    const p = Object.assign({}, pol);
    let n = name;
    for (let i = 0; i < gs.length; i++) {
      const c = choice[i];
      if (c !== null) { Object.assign(p, gs[i][c][0]); n += gs[i][c][1]; }
    }
    return [p, n];
  }
  const polKey = pol => Object.keys(pol).sort().map(k => k + '=' + (k === 'prio' ? pol[k].join(',') : String(pol[k]))).join('|');
  const offOr = g => [null].concat(g.map((_, i) => i));
  // the choices one group (singleMoves) or two groups (pairMoves) away from `choice`
  function singleMoves(gs, choice) {
    const out = [];
    for (let gi = 0; gi < gs.length; gi++) {
      for (const c of offOr(gs[gi])) if (c !== choice[gi]) out.push(choice.slice(0, gi).concat([c], choice.slice(gi + 1)));
    }
    return out;
  }
  function pairMoves(gs, choice) {
    const out = [];
    for (let gi = 0; gi < gs.length; gi++) {
      for (let gj = gi + 1; gj < gs.length; gj++) {
        for (const ci of offOr(gs[gi])) {
          for (const cj of offOr(gs[gj])) {
            if (ci === choice[gi] && cj === choice[gj]) continue;
            const trial = choice.slice();
            trial[gi] = ci; trial[gj] = cj;
            out.push(trial);
          }
        }
      }
    }
    return out;
  }
  // the fastest trial that beats cur (the first of equals, in order) as [choice, result]; null if none does
  function bestMove(run, pol, name, gs, cur, trials) {
    let best = null;
    for (const trial of trials) {
      const r = run(compose(pol, name, gs, trial)[0]);
      if (better(r, cur) && (best === null || better(r, best[1]))) best = [trial, r];
    }
    return best;
  }
  // Steepest descent over the modifier groups: the fastest single-group change while one helps (at most
  // passes x groups moves), then, if pairs, the fastest two-group change, and start over (coord_search in Python).
  function coordSearch(run, pol, name, gs, start, passes, pairs) {
    passes = passes === undefined ? 3 : passes;
    pairs = pairs === undefined ? true : pairs;
    let choice = start.slice();
    let cur = run(compose(pol, name, gs, choice)[0]);
    for (;;) {
      for (let i = 0; i < passes * Math.max(1, gs.length); i++) {
        const best = bestMove(run, pol, name, gs, cur, singleMoves(gs, choice));
        if (best === null) break;
        choice = best[0]; cur = best[1];
      }
      if (!pairs) return [choice, cur];
      const best = bestMove(run, pol, name, gs, cur, pairMoves(gs, choice));
      if (best === null) return [choice, cur];
      choice = best[0]; cur = best[1];
    }
  }

  // page option names (camelCase) to the model's keyword names (models/character.py make_char and Char)
  const OPT_MAP = { gearInt: 'gear_int', gearSta: 'gear_sta', gearSpi: 'gear_spi', levelDiff: 'level_diff', sword: 'sword',
    beastShare: 'beast_share', humanoidShare: 'humanoid_share', elementalShare: 'elemental_share', leyline: 'leyline',
    regenStack: 'regen_stack', armor: 'armor', frostbiteSource: 'frostbite_source', armorSlow: 'armor_slow',
    thrill: 'thrill', pushback: 'pushback', pullGap: 'pull_gap', mobSpeed: 'mob_speed', playerSpeed: 'player_speed',
    stepS: 'step_s', swing: 'swing', pushbackS: 'pushback_s', novaBreak: 'nova_break', fbBreak: 'fb_break', kite: 'kite',
    ilCoef: 'il_coef', ddMode: 'dd_mode', below20: 'below20', lowRanks: 'low_ranks', topRanks: 'top_ranks',
    potions: 'potions', gems: 'gems', evocation: 'evocation', wowheadDrinks: 'wowhead_drinks', spiritDrink: 'spirit_drink',
    mountainWater: 'mountain_water', mobDpsMult: 'mob_dps_mult' };

  // Best single-target rotation for a build (models/character.py evaluate): probe every base, then coordSearch the
  // best `top` (6), with two-group changes for the best `pairTop` (2). opts: { race, hpMults, top, pairTop, mods,
  // downrank, travel } plus any OPT_MAP option.
  // Returns the result with .policy (the rotation name).
  function evaluateUncached(L, tal, gear, opts) {
    opts = opts || {};
    const race = opts.race || 'none';
    const hpMults = opts.hpMults || HP_MULTS;
    const top = opts.top === undefined ? 6 : opts.top;
    const pairTop = opts.pairTop === undefined ? 2 : opts.pairTop;
    const travel = opts.travel === undefined ? TRAVEL : opts.travel;
    const downrank = opts.downrank !== false;
    const o = {};
    for (const key in OPT_MAP) if (opts[key] !== undefined) o[OPT_MAP[key]] = opts[key];
    const ch0 = makeChar(L, tal, gear, race, o);
    const chFn = () => ch0;   // a fight never changes the character, so every run shares one
    const memo = new Map();
    const run = p => {
      const key = polKey(p);
      if (!memo.has(key)) memo.set(key, runPolicy(chFn, L, p, hpMults, travel));
      return memo.get(key);
    };
    const groups = opts.mods !== false ? modGroups(L, tal, ch0) : [];
    const seen = new Set(), probed = [];
    let best = null;
    for (const [name, pol] of POLICIES) {
      const sig = usableSteps(pol, ch0);
      if (sig === null || seen.has(sig)) continue;
      seen.add(sig);
      const rg = rankGroup(L, pol, ch0, downrank);
      const gs = rg.length ? groups.concat([rg]) : groups.slice();
      const blank = gs.map(() => null);
      let cands = [blank];
      if (rg.length) cands = cands.concat(rg.map((_, c) => blank.slice(0, -1).concat([c])));
      if (gs.length && !(rg.length && gs.length === 1)) {
        const first = Math.min(1, gs[0].length - 1);
        cands.push([first].concat(blank.slice(1)));
        // that option at each rank: a lower rank can pay only once Nova is in
        if (rg.length) cands = cands.concat(rg.map((_, c) => [first].concat(blank.slice(1, -1), [c])));
      }
      let pb = null;
      for (const c of cands) {
        const r = run(compose(pol, name, gs, c)[0]);
        if (pb === null || better(r, pb[4])) pb = [name, pol, gs, c, r];
      }
      probed.push(pb);
      if (best === null || better(pb[4], best[1])) best = [compose(pol, name, gs, pb[3])[1], pb[4]];
    }
    const feas = probed.filter(b => b[4].feasible);
    const ranked = (feas.length ? feas : probed).slice().sort((a, b) => a[4].spk - b[4].spk).slice(0, top);
    for (let i = 0; i < ranked.length; i++) {
      const [name, pol, gs, c0] = ranked[i];
      const [choice, cur] = coordSearch(run, pol, name, gs, c0, 3, i < pairTop);
      if (better(cur, best[1])) best = [compose(pol, name, gs, choice)[1], cur];
    }
    let name = best[0];
    const r = best[1];
    for (const [cast, tag] of AUTO_TAGS) if ((r.casts_all[cast] || 0) > 0) name += tag;
    const out = Object.assign({}, r);
    out.policy = name;
    return out;
  }
  // The builder asks for the page plan's score at the same level on every click: remember the last 256 answers.
  // A hit returns a copy, so a caller cannot change what is remembered. Results are identical with or without it.
  const CACHE = new Map(), CACHE_MAX = 256;
  function cacheKey(L, tal, gear, opts) {
    tal = tal || {};
    opts = opts || {};
    const t = Object.keys(tal).filter(k => tal[k]).sort().map(k => k + ':' + tal[k]).join(',');
    const o = Object.keys(opts).sort().map(k => k + ':' + JSON.stringify(opts[k])).join(',');
    return L + '|' + t + '|' + gear + '|' + o;
  }
  function evaluate(L, tal, gear, opts) {
    const key = cacheKey(L, tal, gear, opts);
    let r = CACHE.get(key);
    if (r === undefined) {
      r = evaluateUncached(L, tal, gear, opts);
      CACHE.set(key, r);
      if (CACHE.size > CACHE_MAX) CACHE.delete(CACHE.keys().next().value);
    }
    return Object.assign({}, r);
  }

  const api = { evaluate, evaluateUncached, policyLabel, SCORED, UNSCORED, OPT_MAP, POLICIES, makeChar, mobHp, mobDps, simulate,
    secondsPerKill, restSetup, restSolve, travelRegen, rankRows, ddAvg, POTIONS, POTION_NAMES, HP_MULTS, LOW_RANKS,
    modGroups, rankGroup, runPolicy, fightConsts };
  if (typeof module !== 'undefined') module.exports = api; else root.LevelingModel = api;
})(this);
