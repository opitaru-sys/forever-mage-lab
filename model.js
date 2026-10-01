/* Forever Mage raid model: a level 60 Mage against a level 63 boss, expected values over a finite fight.
 * A hand port of models/raid_model.py, the reference (tests/parity_test.js, tests/raid_options_test.js and
 * tests/weights_test.js hold values generated there by tests/make_raid_fixtures.py). docs/raid-model.md has the method.
 *
 * In short: every castable spell and rank is an action with expected damage, time and mana per use, its procs
 * included as expected follow-up casts (Fingers of Frost Ice Lances, Missile Barrage Missiles, Hot Streak
 * Pyroblasts, Clearcasting, Master of Elements, Ignite). Arcane Blast is cast in cycles. A linear program splits
 * the fight's time across actions for the most damage, with the mana spent no more than the pool, regen, potions,
 * runes, gems and Evocation. Fight-level effects that depend on the plan (Winter's Chill ramp, Combustion, Hot
 * Streak, Pyroblast DoT overlap, Eureka!, cooldown drift) come from a fixed-point loop of ITERATIONS passes.
 * Spell values: data/mage_spells.json (client 1.60.1.69893). Every guess is marked ASSUMPTION.
 */
(function (root) {
  'use strict';
  const GCD = 1.5;
  const BASE_MANA = 1213;          // Mage base mana at 60 (sim base_stats_auto_gen.go, client table)
  const INT_MANA = 15, INT_MANA_OFFSET = -280;   // 15 mana per Intellect past the first 20 (sim mana.go)
  const CRIT_PER_INT = 0.000168;   // 0.0168% crit per Intellect (sim CritPerIntMaxLevel)
  const SPIRIT_BASE = 6.25, SPIRIT_PER = 1 / 8;  // 12.5 + Spirit/4 per 2 s outside the five-second rule (sim mana.go)
  const MAGE_ARMOR = 0.5;          // Mage Armor rank 3: 50% of regen while casting (client 22783)
  const HIT_GAP = 0.16;            // Classic table vs level 63 (UNVERIFIED for Forever); capped counts as 100%, as on the Warlock page
  const CRIT_BONUS = 0.5;          // spell crits deal 150%
  const LEVEL_RESIST = 0.94;       // levelResist: the sim's 6% average partial resist vs level 63 on non-binary spells
                                   // (sim core/spell_resistances.go:81, :96-101); on by default, the Warlock page has none
  const AB_COST = 0.15 * BASE_MANA, AB_STACK_COST = 1.75, AB_STACK_DMG = 0.10;   // Arcane Blast and its buff 400573
  const AP_DMG = 0.30, AP_COST = 0.30, AP_DUR = 15, AP_CD = 180;                  // Arcane Power
  const POM_CD = 180;
  const COMB_CD = 180, COMB_CRIT = 0.10, COMB_CRITS = 4, COMB_MAX = 10;           // Combustion
  const FV_PER_STACK = 0.03, FV_STACKS = 5;                                        // Fire Vulnerability, 30 s
  const FV_REFRESH = 27;           // ASSUMPTION: one Scorch every 27 s keeps a 30 s debuff
  const HS_WINDOW = 20;            // Hot Streak lasts 20 s since build 70009
  const WC_PER_STACK = 0.02;       // Winter's Chill: +2% crit a stack, 15 s
  const FOF_CHANCE = 0.15, IL_FROZEN = 4;           // Fingers of Frost; Ice Lance x4 on frozen, whole hit
  const MB_AB = 0.40, MB_OTHER = 0.20;              // Missile Barrage chances (sim)
  const EVO_TIME = 8, EVO_CD = 480, EVO_MULT = 16;  // Evocation: 8 s, 8 min, +1500% regen
  const EVO_LAG = 30;              // ASSUMPTION: the first Evocation is not before 30 s
  const ITEM_CD = 120;             // potions, and gems or runes: 2 min each
  const POTION_MANA = (1350 + 2250) / 2, POTION_MAX = 2250;   // Major Mana Potion 13444
  const RUNE_MANA = (900 + 1500) / 2, RUNE_MAX = 1500;        // Demonic Rune / Dark Rune
  const GEMS = [1100, 850, 600, 400];                         // Ruby, Citrine, Jade, Agate averages
  const BLAST_SP = 47, BLAST_DUR = 30;                        // Major Spellblasting Potion
  const EUREKA = 0.10;             // Gnome Eureka!: 3 damaging spells +10% damage, -10% cost, 2 min
  const TOTG_CHANCE = 0.10, TOTG_HP = 0.05;                   // Undead caster Touch of the Grave
  const WAND_SPEC = [0, 0.13, 0.25];   // Wand Specialization +13/25% wand damage
  // Raid buffs, Forever tooltips (nether.wowhead.com/forever/tooltip/spell/ID). ForeverChanges' racials data has
  // Paladins and Shamans on both factions (Undead Paladin, Dwarf Shaman).
  const GBOW_MP5 = 40;             // Greater Blessing of Wisdom rank 2 (25918): 40 mana every 5 s
  const MANA_SPRING_MP5 = 25;      // Mana Spring Totem rank 4 (10497): 10 mana every 2 s, party only
  const PRAYER_SPIRIT = 40;        // Prayer of Spirit rank 1 (27681): +40 Spirit
  const GOTW_STAT = 16;            // Gift of the Wild rank 2 (21850): +16 all attributes
  const MAGEBLOOD_MP5 = 12;        // Mageblood Elixir (20007): 12 mana every 5 s
  const FIVE_SEC = 5;              // the five-second rule
  const IDLE_BLOCK = 15;           // ASSUMPTION: mana is waited out in 15 s blocks; the first 5 s regen at the casting rate
  const ITERATIONS = 10;
  const DAMP = 0.5, DAMP_FROM = 2;   // damping of the plan-dependent state from the third pass on
  const TOP_BAND = 0.99;             // the opening action: the fastest spender within 1% of the best damage per second
  const GEM_ROOM = 1200.0 / 1100.0;  // a gem needs room for its top roll
  const EPS = 1e-9;

  // [rank, spell id, level learned, cast ms, mana, cooldown ms, average damage at 60, coefficient,
  //  (DoT: per tick, ticks, period ms, coefficient per tick) or (Arcane Missiles: missiles, channel ms)]
  const SPELL_ROWS = {
    frostbolt: [
      [1, 116, 4, 1500, 25, 0, 21, 0.407], [2, 205, 8, 1800, 35, 0, 35, 0.489],
      [3, 837, 14, 2200, 50, 0, 49, 0.597], [4, 7322, 20, 2600, 65, 0, 64, 0.706],
      [5, 8406, 26, 3000, 100, 0, 101, 0.814], [6, 8407, 32, 3000, 130, 0, 140, 0.814],
      [7, 8408, 38, 3000, 160, 0, 189, 0.814], [8, 10179, 44, 3000, 195, 0, 253, 0.814],
      [9, 10180, 50, 3000, 225, 0, 318, 0.814], [10, 10181, 56, 3000, 260, 0, 397, 0.814],
      [11, 25304, 60, 3000, 290, 0, 475, 0.814]],
    fireball: [
      [1, 133, 1, 1500, 30, 0, 20, 0.429, 1, 2, 2000, 0.0], [2, 143, 6, 2000, 45, 0, 39, 0.571, 1, 3, 2000, 0.0],
      [3, 145, 12, 2500, 65, 0, 56, 0.714, 2, 3, 2000, 0.0], [4, 3140, 18, 3000, 95, 0, 78, 0.857, 3, 4, 2000, 0.0],
      [5, 8400, 24, 3500, 140, 0, 114, 1.0, 4, 4, 2000, 0.0], [6, 8401, 30, 3500, 185, 0, 160, 1.0, 6, 4, 2000, 0.0],
      [7, 8402, 36, 3500, 220, 0, 196, 1.0, 6, 4, 2000, 0.0], [8, 10148, 42, 3500, 260, 0, 243, 1.0, 8, 4, 2000, 0.0],
      [9, 10149, 48, 3500, 305, 0, 309, 1.0, 10, 4, 2000, 0.0], [10, 10150, 54, 3500, 350, 0, 384, 1.0, 12, 4, 2000, 0.0],
      [11, 10151, 60, 3500, 395, 0, 451, 1.0, 14, 4, 2000, 0.0], [12, 25306, 60, 3500, 410, 0, 483, 1.0, 15, 4, 2000, 0.0]],
    frostfire: [
      [1, 401502, 40, 3000, 205, 0, 110, 0.814, 9, 3, 3000, 0.0], [2, 1237312, 50, 3000, 285, 0, 195, 0.814, 13, 3, 3000, 0.0],
      [3, 1237313, 60, 3000, 370, 0, 292, 0.814, 19, 3, 3000, 0.0]],
    scorch: [
      [1, 2948, 22, 1500, 50, 0, 42, 0.429], [2, 8444, 28, 1500, 65, 0, 59, 0.429], [3, 8445, 34, 1500, 80, 0, 73, 0.429],
      [4, 8446, 40, 1500, 100, 0, 97, 0.429], [5, 10205, 46, 1500, 115, 0, 121, 0.429],
      [6, 10206, 52, 1500, 135, 0, 156, 0.429], [7, 10207, 58, 1500, 150, 0, 181, 0.429]],
    arcaneMissiles: [
      [1, 5143, 8, 0, 85, 0, 25, 0.286, 3, 3000], [2, 5144, 16, 0, 140, 0, 32, 0.286, 4, 4000],
      [3, 5145, 24, 0, 235, 0, 46, 0.286, 5, 5000], [4, 8416, 32, 0, 320, 0, 68, 0.286, 5, 5000],
      [5, 8417, 40, 0, 410, 0, 97, 0.286, 5, 5000], [6, 10211, 48, 0, 500, 0, 133, 0.286, 5, 5000],
      [7, 10212, 56, 0, 595, 0, 174, 0.286, 5, 5000], [8, 25345, 56, 0, 655, 0, 209, 0.286, 5, 5000]],
    fireBlast: [[7, 10199, 54, 0, 340, 8000, 453, 0.429]],
    arcaneBlast: [[5, 1239700, 60, 2500, 0, 0, 394, 0.714]],
    iceLance: [[6, 1240047, 56, 0, 160, 0, 148, 0.0]],
    pyroblast: [[8, 18809, 60, 6000, 440, 0, 583, 1.0, 53, 4, 3000, 0.15]],
    blastWave: [[5, 13021, 60, 0, 545, 45000, 493, 0.129]],
  };
  // school, binary (no partial resists), Hot Streak builder, chill, Missile Barrage chance, tome rank
  const SPELL_META = {
    frostbolt: { name: 'Frostbolt', school: 'frost', binary: true, hs: false, chill: true, mb: MB_OTHER, tome: 11 },
    fireball: { name: 'Fireball', school: 'fire', binary: false, hs: true, chill: false, mb: MB_OTHER, tome: 12 },
    frostfire: { name: 'Frostfire Bolt', school: 'frostfire', binary: false, hs: true, chill: true, mb: MB_OTHER, tome: 0 },
    scorch: { name: 'Scorch', school: 'fire', binary: false, hs: true, chill: false, mb: 0, tome: 0 },
    arcaneMissiles: { name: 'Arcane Missiles', school: 'arcane', binary: false, hs: false, chill: false, mb: 0, tome: 8 },
    fireBlast: { name: 'Fire Blast', school: 'fire', binary: false, hs: true, chill: false, mb: 0, tome: 0 },
    arcaneBlast: { name: 'Arcane Blast', school: 'arcane', binary: false, hs: false, chill: false, mb: MB_AB, tome: 0 },
    iceLance: { name: 'Ice Lance', school: 'frost', binary: true, hs: false, chill: false, mb: 0, tome: 0 },
    pyroblast: { name: 'Pyroblast', school: 'fire', binary: false, hs: false, chill: false, mb: 0, tome: 0 },
    blastWave: { name: 'Blast Wave', school: 'fire', binary: true, hs: false, chill: false, mb: 0, tome: 0 },
  };
  const FILLERS = ['frostbolt', 'fireball', 'frostfire', 'scorch', 'arcaneMissiles'];
  const FIRE_SPELLS = ['fireball', 'frostfire', 'scorch', 'fireBlast', 'pyroblast', 'blastWave'];   // frostfire: ASSUMPTION
  const SHATTER = [0, 0.17, 0.33, 0.50], AMED = [0, 0.17, 0.33, 0.50], ISCORCH = [0, 0.33, 0.67, 1.0];

  const DEFAULTS = {
    sp: 500, crit: 0.10, gearHit: 0.11, int: 300, spirit: 120, mp5: 0,
    race: 'none', sword: true, maxHp: 4000, fightLength: 300, fireImmune: false, targets: 1,
    potion: 'mana', runes: true, gems: true, mageblood: true, raidBuffs: 'all', wandDps: 57,
    iceLanceCoef: 0.143, abMask: 'client', amSpends: false, regenStack: 'add', evocation: 1, igniteMunch: 0,
    downrank: 'top', topRanks: false, levelResist: true, mbRate: 1,
  };

  const opt = (o, k) => (o && o[k] !== undefined && o[k] !== null ? o[k] : DEFAULTS[k]);
  const uses = (cd, T, lag) => (T <= (lag || 0) ? 0 : Math.floor((T - (lag || 0)) / cd) + 1);
  function uptime(dur, cd, T) {
    let up = 0;
    const n = uses(cd, T, 0);
    for (let k = 0; k < n; k++) up += Math.min(dur, T - k * cd);
    return up / T;
  }
  const fireIsh = sch => sch === 'fire' || sch === 'frostfire';
  const frostIsh = sch => sch === 'frost' || sch === 'frostfire';

  // ---------------------------------------------------------------- character and fight context
  function context(o, tal, fvPlan, state) {
    const r = k => tal[k] || 0;
    const T = opt(o, 'fightLength');
    const race = opt(o, 'race');
    const fireOk = !opt(o, 'fireImmune');
    const buffs = opt(o, 'raidBuffs');            // 'all', 'noTotem' (no Shaman in your group) or 'none'
    const bMp5 = buffs !== 'none' ? GBOW_MP5 + (buffs === 'all' ? MANA_SPRING_MP5 : 0.0) : 0.0;
    const bSpirit = buffs !== 'none' ? PRAYER_SPIRIT + GOTW_STAT : 0.0;
    const bInt = buffs !== 'none' ? GOTW_STAT : 0.0;
    const intIn = opt(o, 'int');                  // the sheet, own Arcane Brilliance included, raid buffs not
    const int0 = intIn + bInt;
    const intEff = int0 * (1 + 0.02 * r('ArcaneMind'));
    let crit = opt(o, 'crit') + (intEff - intIn) * CRIT_PER_INT + 0.01 * r('ArcaneInstability');
    if (race === 'human' && opt(o, 'sword')) crit += 0.02;
    const spirit = (opt(o, 'spirit') + bSpirit) * (race === 'human' ? 1.05 : 1.0);
    const maxMana = (BASE_MANA + INT_MANA_OFFSET + INT_MANA * intEff) * (race === 'gnome' ? 1.05 : 1.0);
    let sp = opt(o, 'sp');
    const potion = opt(o, 'potion');
    const uPot = potion === 'blast' ? uptime(BLAST_DUR, ITEM_CD, T) : 0.0;
    if (race === 'orc') {
      const uBf = uptime(15.0, 120.0, T);
      sp = sp * (1 + 0.10 * uBf) + BLAST_SP * (uPot + 0.10 * Math.min(uBf, uPot));
    } else {
      sp = sp + BLAST_SP * uPot;
    }
    let haste = 1.0;
    if (race === 'skyborne') haste = 1.01;
    if (race === 'troll') haste = 1 + 0.10 * uptime(10.0, 180.0, T);
    const gearHit = opt(o, 'gearHit');
    const landed = th => 1 - Math.max(0.0, HIT_GAP - gearHit - th);
    const ep = 0.01 * r('ElementalPrecision');
    const h = { arcane: landed(0.01 * r('ArcaneFocus')), fire: landed(ep), frost: landed(ep), frostfire: landed(ep) };
    const spiritRegen = SPIRIT_BASE + spirit * SPIRIT_PER;
    const am = AMED[r('ArcaneMeditation')];
    const stack = opt(o, 'regenStack');
    let frac;
    if (stack === 'full') frac = 1.0;
    else if (stack === 'add') frac = Math.min(1.0, MAGE_ARMOR + am);
    else frac = Math.max(MAGE_ARMOR, am);
    const mp5 = opt(o, 'mp5') + bMp5 + (opt(o, 'mageblood') ? MAGEBLOOD_MP5 : 0.0);
    const regenCast = mp5 / 5 + spiritRegen * frac;
    // idle time (a wand, no mana spent) regens in full once the five-second rule clears, in IDLE_BLOCK blocks
    const idleGain = spiritRegen * (1 - frac) * (IDLE_BLOCK - FIVE_SEC) / IDLE_BLOCK;
    const wand = opt(o, 'wandDps') * (1 + WAND_SPEC[r('WandSpecialization')]) * landed(0.0)
      * (opt(o, 'levelResist') ? LEVEL_RESIST : 1.0);
    const uAp = r('ArcanePower') ? uptime(AP_DUR, AP_CD, T) : 0.0;
    const wc = r('WintersChill');
    return {
      o, tal, T, race, fireOk, fv: fvPlan, state,
      sp, crit, spirit, maxMana, haste, h, spiritRegen, regenCast, mp5, uAp, idleGain, wand,
      amSpends: !!opt(o, 'amSpends'),
      cc: 0.02 * r('ArcaneConcentration'),
      moe: 0.10 * r('MasterOfElements'),
      ignite: fireOk ? 0.08 * r('Ignite') * (1 - opt(o, 'igniteMunch')) : 0.0,
      wcAvg: wc ? (state.wcAvg === null ? WC_PER_STACK * wc : state.wcAvg) : 0.0,
      eta: state.eta, pyroTicks: state.pyroTicks,
      mb: r('MissileBarrage') ? opt(o, 'mbRate') : 0.0,
      fof: r('IceLance') && r('FingersOfFrost') ? r('FingersOfFrost') : 0,
      shatter: SHATTER[r('Shatter')],
      hs: r('HotStreak') && r('Pyroblast') && fireOk ? 1 : 0,
      resist: opt(o, 'levelResist'), downrank: opt(o, 'downrank'), tomes: opt(o, 'topRanks'),
      ilCoef: opt(o, 'iceLanceCoef'), abTooltip: opt(o, 'abMask') === 'tooltip',
      r,
    };
  }

  function critOf(S, key, sch, frozen) {
    const r = S.r;
    let c = S.crit;
    if (fireIsh(sch)) c += 0.02 * r('CriticalMass');
    if (sch === 'arcane') c += 0.02 * r('ArcaneImpact');
    if (key === 'fireBlast' || key === 'scorch' || key === 'arcaneBlast' || key === 'iceLance') c += 0.02 * r('Incineration');
    if (key === 'frostbolt' || key === 'iceLance') c += S.wcAvg;
    if (frozen) c += S.shatter;
    return Math.min(1.0, c);
  }
  function critBonus(S, sch) {
    const r = S.r;
    let b = 1.0;
    if (frostIsh(sch)) b += 0.2 * r('IceShards');
    if (sch === 'arcane') b += 0.2 * r('ArcaneMind');
    return CRIT_BONUS * b;
  }
  function flatMult(S, sch, stacks) {    // the sim's DamageDone_Flat mods add up
    const r = S.r;
    let b = 1 + 0.01 * r('ArcaneInstability') + AP_DMG * S.uAp + AB_STACK_DMG * stacks;
    if (fireIsh(sch)) b += 0.02 * r('FirePower');
    if (frostIsh(sch)) b += 0.02 * r('PiercingIce');
    return b;
  }
  function pctMult(S, sch, binary) {
    let m = 1.0;
    if (S.fv && fireIsh(sch)) m *= 1 + FV_PER_STACK * FV_STACKS;
    if (S.resist && !binary) m *= LEVEL_RESIST;
    return m;
  }
  function costMult(S, sch) {
    let m = 1 + AP_COST * S.uAp;
    if (frostIsh(sch)) m -= 0.05 * S.r('FrostChanneling');
    return m;
  }
  function coefOf(S, key, row, coef) {
    if (key === 'iceLance') return S.ilCoef;
    return coef;
  }
  function castTime(S, key, row) {
    const r = S.r;
    const ms = row[3];
    if (ms <= 0) return GCD;
    let sec = ms / 1000.0;
    if (key === 'frostbolt') sec -= 0.1 * r('ImprovedFrostbolt');
    if (key === 'fireball' || key === 'frostfire') sec -= 0.1 * r('ImprovedFireball');
    return Math.max(GCD, sec / S.haste);
  }

  const COUNTERS = ['casts', 'landed', 'direct', 'cost', 'fireHits', 'fireCrit', 'fireCritValue', 'frostHits', 'hsCasts',
    'hsHits', 'hsCrit', 'pyros', 'pyroTime', 'time', 'time2'];
  function newCounters() { const n = {}; COUNTERS.forEach(k => { n[k] = 0.0; }); return n; }
  function newAction(name, cap, spec) {
    return { name, d: 0.0, t: 0.0, m: 0.0, cap: cap === undefined ? null : cap, parts: {}, n: newCounters(), mainCast: 0.0,
      spec: spec || {} };
  }
  function addCast(act, cast, w) {
    if (w <= 0) return;
    for (const k in cast.parts) {
      const v = cast.parts[k];
      act.parts[k] = (act.parts[k] || 0.0) + w * v;
      act.d += w * v;
    }
    act.t += w * cast.t;
    act.m += w * cast.m;
    for (const k in cast.n) act.n[k] += w * cast.n[k];
  }
  function addAction(act, sub, w) {
    if (w <= 0) return;
    for (const k in sub.parts) act.parts[k] = (act.parts[k] || 0.0) + w * sub.parts[k];
    act.d += w * sub.d;
    act.t += w * sub.t;
    act.m += w * sub.m;
    for (const k in act.n) act.n[k] += w * sub.n[k];
  }

  // One cast of a single-hit spell (direct part plus DoT), expected over hit and crit.
  function spellCast(S, key, row, p) {
    p = p || {};
    const stacks = p.stacks || 0, ccIn = p.ccIn || 0.0, ticks = p.ticks || 0.0, mult = p.mult === undefined ? 1.0 : p.mult;
    const meta = SPELL_META[key];
    const sch = meta.school;
    const h = S.h[sch];
    const c = critOf(S, key, sch, !!p.frozen);
    const k = critBonus(S, sch);
    const fl = flatMult(S, sch, key === 'arcaneBlast' ? 0 : stacks);   // the buff's damage mask leaves Arcane Blast out
    const pc = pctMult(S, sch, meta.binary);
    const coef = coefOf(S, key, row, row[7]);
    const base = (row[6] + coef * S.sp) * fl * pc * mult;
    const direct = base * (1 + c * k) * h;
    const name = p.label || meta.name;
    const parts = {};
    parts[name] = direct;
    if (row.length >= 12 && ticks > 0) {
      const tcoef = coefOf(S, key, row, row[11]);
      parts[name] += (row[8] + tcoef * S.sp) * fl * pc * (1 + c * k) * h * ticks;   // ticks crit (client flag)
    }
    if (fireIsh(sch) && S.ignite > 0) parts.Ignite = h * c * (1 + k) * base * S.ignite;
    const baseCost = key === 'arcaneBlast' ? AB_COST : row[4];
    const cm = costMult(S, sch) + (key === 'arcaneBlast' ? AB_STACK_COST * stacks : 0.0);
    let paid = baseCost * cm * (1 - ccIn);
    if ((fireIsh(sch) || frostIsh(sch)) && S.moe > 0) paid -= h * c * baseCost * S.moe * (1 - ccIn);   // Master of Elements
    const tt = p.t === undefined || p.t === null ? castTime(S, key, row) : p.t;
    const n = newCounters();
    n.casts = 1.0; n.landed = h; n.direct = direct; n.cost = baseCost * cm;
    if (fireIsh(sch)) { n.fireHits = h; n.fireCrit = h * c; n.fireCritValue = h * (base * k + (1 + k) * base * S.ignite); }
    if (frostIsh(sch)) n.frostHits = h;
    if (meta.hs) { n.hsCasts = 1.0; n.hsHits = h; n.hsCrit = h * c; }
    n.time = tt; n.time2 = tt * tt;
    return { parts, t: tt, m: paid, n, h, c };
  }

  // Arcane Missiles: a hit per missile. Barrage: free, a missile every 0.5 s. Stacks only in tooltip mode.
  function missilesCast(S, row, barrage, stacks, ccIn, label) {
    const sch = 'arcane';
    const h = S.h[sch];
    const c = critOf(S, 'arcaneMissiles', sch, false);
    const k = critBonus(S, sch);
    const st = S.abTooltip ? (stacks || 0) : 0;
    const base = (row[6] + coefOf(S, 'arcaneMissiles', row, row[7]) * S.sp) * flatMult(S, sch, st) * pctMult(S, sch, false);
    const missiles = row[8];
    const dmg = base * (1 + c * k) * h * missiles;
    const name = label || (barrage ? 'Arcane Missiles (Barrage)' : 'Arcane Missiles');
    let tt, paid, cost;
    if (barrage) { tt = 0.5 * missiles; paid = 0.0; cost = 0.0; }
    else { tt = row[9] / 1000.0; cost = row[4] * costMult(S, sch); paid = cost * (1 - (ccIn || 0.0)); }
    const n = newCounters();
    n.casts = 1.0; n.landed = h; n.direct = dmg; n.cost = cost; n.time = tt; n.time2 = tt * tt;
    const parts = {};
    parts[name] = dmg;
    return { parts, t: tt, m: paid, n, h, c, missiles };
  }

  // ---------------------------------------------------------------- composites
  function rowsFor(S, key) {
    let rows = SPELL_ROWS[key];
    const tome = SPELL_META[key].tome;
    if (!S.tomes && tome) rows = rows.filter(row => row[0] !== tome);
    if (S.downrank === 'top' || !FILLERS.includes(key)) return [rows[rows.length - 1]];
    return rows;
  }
  const topRow = (S, key) => { const rows = rowsFor(S, key); return rows[rows.length - 1]; };
  const pcc1 = (S, h) => S.cc * h;
  const pccAm = (S, missiles) => 1 - Math.pow(1 - S.cc * S.h.arcane, missiles);

  function hsPyro(S, ccIn) {         // a Pyroblast at 3 Hot Streak stacks: 6 s cut by 75%
    const row = topRow(S, 'pyroblast');
    const t = Math.max(GCD, row[3] / 1000.0 * (1 - 0.75) / S.haste);
    const cast = spellCast(S, 'pyroblast', row, { ccIn, ticks: S.pyroTicks, t, label: 'Pyroblast (Hot Streak)' });
    cast.n.pyros = 1.0;
    cast.n.pyroTime = t;
    return cast;
  }
  const barrageAm = (S, stacks) => missilesCast(S, topRow(S, 'arcaneMissiles'), true, stacks || 0, 0.0);

  function followUps(S, act, key, cast, pMbExtra) {
    const meta = SPELL_META[key];
    const h = cast.h, c = cast.c;
    const p1 = pcc1(S, h);
    if (S.hs && meta.hs) addCast(act, hsPyro(S, p1), S.eta * h * c);
    if (S.fof && meta.chill) {
      const il = spellCast(S, 'iceLance', topRow(S, 'iceLance'), { frozen: true, ccIn: p1, t: GCD, mult: IL_FROZEN,
        label: 'Ice Lance (Fingers)' });
      addCast(act, il, h * FOF_CHANCE * S.fof);
    }
    let pAm = 0.0;
    if (S.mb > 0 && meta.mb > 0) pAm = meta.mb * S.mb;
    pAm = 1 - (1 - pAm) * (1 - (pMbExtra || 0.0));
    if (pAm > 0) addCast(act, barrageAm(S, 0), pAm);
    return pAm;
  }

  function fillerAction(S, key, row) {
    const meta = SPELL_META[key];
    const rows = rowsFor(S, key);
    const top = rows[rows.length - 1][0] === row[0];
    const label = top ? meta.name : meta.name + ' (rank ' + row[0] + ')';
    const act = newAction(label, null, { kind: 'filler', key, rank: row[0] });
    if (key === 'arcaneMissiles') {
      const cast = missilesCast(S, row, false, 0, pccAm(S, row[8]), label);
      addCast(act, cast, 1.0);
      act.mainCast = cast.t;
      return act;
    }
    let ticks = 0.0;
    if (row.length >= 12) ticks = Math.min(row[9], Math.floor(castTime(S, key, row) / (row[10] / 1000.0)));
    const h = S.h[meta.school];
    const pMb = S.mb > 0 && meta.mb > 0 ? meta.mb * S.mb : 0.0;
    const ccIn = pMb * pccAm(S, topRow(S, 'arcaneMissiles')[8]) + (1 - pMb) * pcc1(S, h);
    const cast = spellCast(S, key, row, { ccIn, ticks, label });
    addCast(act, cast, 1.0);
    act.mainCast = cast.t;
    followUps(S, act, key, cast, 0.0);
    return act;
  }

  function arcaneCycle(S, n, spender, tooltipStyle) {
    const abRow = topRow(S, 'arcaneBlast');
    const spRow = topRow(S, spender);
    const spMeta = SPELL_META[spender];
    const pAb = MB_AB * S.mb;
    const pSp = spMeta.mb * S.mb;
    const miss = topRow(S, 'arcaneMissiles')[8];
    const pByAb = 1 - Math.pow(1 - pAb, n);
    const pAm = 1 - (1 - pByAb) * (1 - pSp);
    const label = 'Arcane Blast x' + n + ' + ' + spMeta.name + (tooltipStyle ? ' (Missiles spend)' : '');
    const act = newAction(label, null, { kind: 'cycle', n, key: spender, tooltip: tooltipStyle });
    const hAb = S.h.arcane;
    for (let k = 1; k <= n; k++) {
      const ccIn = k === 1 ? pAm * pccAm(S, miss) + (1 - pAm) * pcc1(S, hAb) : pcc1(S, hAb);
      addCast(act, spellCast(S, 'arcaneBlast', abRow, { stacks: k - 1, ccIn }), 1.0);
    }
    let ticks = 0.0;
    if (spRow.length >= 12) {       // the spender's DoT is refreshed a cycle later
      const cyc = n * castTime(S, 'arcaneBlast', abRow) + castTime(S, spender, spRow);
      ticks = Math.min(spRow[9], Math.floor(cyc / (spRow[10] / 1000.0)));
    }
    const cast = spellCast(S, spender, spRow, { stacks: n, ccIn: pcc1(S, hAb), ticks, label: spMeta.name + ' (stacks)' });
    if (!tooltipStyle) {
      addCast(act, cast, 1.0);
      followUps(S, act, spender, cast, pByAb);
    } else {
      addCast(act, barrageAm(S, n), pByAb);
      const sub = newAction('');
      addCast(sub, cast, 1.0);
      followUps(S, sub, spender, cast, 0.0);
      addAction(act, sub, 1 - pByAb);
    }
    act.mainCast = castTime(S, 'arcaneBlast', abRow);
    // a cooldown that comes up mid-cycle waits for the whole cycle: count the Blasts and the spender as one block
    const tAb = castTime(S, 'arcaneBlast', abRow), tSp = castTime(S, spender, spRow);
    const wSp = !tooltipStyle ? 1.0 : 1 - pByAb;
    act.n.time2 += Math.pow(n * tAb + tSp, 2) - n * Math.pow(tAb, 2) - wSp * Math.pow(tSp, 2);
    return act;
  }

  function cappedInstant(S, key, capCd) {   // on cooldown from the pull; a cooldown up mid-cast waits (drift)
    const row = topRow(S, key);
    const meta = SPELL_META[key];
    const act = newAction(meta.name, 0.5 + S.T / (capCd + S.state.drift), { kind: 'cd', key });
    const h = S.h[meta.school];
    const cast = spellCast(S, key, row, { ccIn: pcc1(S, h), t: GCD });
    addCast(act, cast, 1.0);
    followUps(S, act, key, cast, 0.0);
    return act;
  }

  function pomAction(S, candidates) {    // Presence of Mind: the biggest cast-time spell, instant, once per 3 min
    let best = null;
    candidates.forEach(([act, key]) => {
      if (best === null || (act.parts[SPELL_META[key].name] || 0.0) > (best[0].parts[SPELL_META[best[1]].name] || 0.0)) best = [act, key];
    });
    if (best === null) return null;
    const [src, key] = best;
    const act = newAction('Presence of Mind: ' + SPELL_META[key].name, uses(POM_CD, S.T, 0),
      { kind: 'pom', key, rank: src.spec.rank || 0 });
    act.d = src.d; act.m = src.m;
    act.t = src.t - (src.mainCast - GCD);
    act.parts = Object.assign({}, src.parts);
    act.n = Object.assign({}, src.n);
    act.n.time = src.n.time - (src.mainCast - GCD);
    act.n.time2 = src.n.time2 - Math.pow(src.mainCast, 2) + Math.pow(GCD, 2);
    act.mainCast = GCD;
    return act;
  }

  function scorchUpkeep(S) {     // Improved Scorch: 5 stacks at the pull, then a Scorch every FV_REFRESH s
    const r = S.r;
    const row = topRow(S, 'scorch');
    const h = S.h.fire;
    const apply = Math.max(1e-6, ISCORCH[r('ImprovedScorch')] * h);
    const rampCasts = FV_STACKS / apply;
    const rampTime = rampCasts * castTime(S, 'scorch', row);
    const refreshCasts = Math.max(0.0, S.T - rampTime) / FV_REFRESH / apply;
    const act = newAction('Scorch (Fire Vulnerability)');
    const sRamp = Object.assign({}, S, { fv: false });   // ramp Scorches see 0 to 4 stacks: +6% on average
    const ramp = newAction('');
    let cast = spellCast(sRamp, 'scorch', row, { ccIn: pcc1(S, h), label: 'Scorch (Fire Vulnerability)' });
    addCast(ramp, cast, 1.0);
    followUps(sRamp, ramp, 'scorch', cast, 0.0);
    const rampMult = 1 + FV_PER_STACK * (FV_STACKS - 1) / 2.0;
    for (const k in ramp.parts) ramp.parts[k] *= rampMult;
    ramp.d *= rampMult;
    addAction(act, ramp, rampCasts);
    const keep = newAction('');
    cast = spellCast(S, 'scorch', row, { ccIn: pcc1(S, h), label: 'Scorch (Fire Vulnerability)' });
    addCast(keep, cast, 1.0);
    followUps(S, keep, 'scorch', cast, 0.0);
    addAction(act, keep, refreshCasts);
    return act;
  }

  function evocationMana(S) {   // 8 s at 16x spirit regen plus mp5, less the casting regen it replaces (UNVERIFIED)
    const scale = opt(S.o, 'evocation');
    const full = EVO_TIME * (EVO_MULT * S.spiritRegen + S.mp5 / 5);
    return scale > 0 ? full * scale - EVO_TIME * S.regenCast : 0.0;
  }

  function buildActions(S) {
    const r = S.r;
    const fireOk = S.fireOk;
    const acts = [];
    const pomSrc = [];
    FILLERS.forEach(key => {
      if (!fireOk && FIRE_SPELLS.includes(key)) return;
      const rows = rowsFor(S, key);
      rows.forEach(row => {
        const act = fillerAction(S, key, row);
        acts.push(act);
        if (row[0] === rows[rows.length - 1][0] && key !== 'arcaneMissiles' && key !== 'scorch') pomSrc.push([act, key]);
      });
    });
    if (r('Pyroblast') && fireOk) {
      const row = topRow(S, 'pyroblast');
      const act = newAction('Pyroblast', null, { kind: 'filler', key: 'pyroblast', rank: row[0] });
      // hard cast as a filler: the next one refreshes the DoT, so only whole ticks inside one cast land
      const ticks = Math.min(row[9], Math.floor(castTime(S, 'pyroblast', row) / (row[10] / 1000.0)));
      const cast = spellCast(S, 'pyroblast', row, { ccIn: pcc1(S, S.h.fire), ticks });
      addCast(act, cast, 1.0);
      act.mainCast = cast.t;
      acts.push(act);
      pomSrc.push([act, 'pyroblast']);
    }
    if (r('ArcaneBlast')) {
      const spenders = ['frostbolt'].concat(fireOk ? ['fireball', 'frostfire'] : []);
      for (let n = 1; n < 5; n++) {
        spenders.forEach(spKey => {
          acts.push(arcaneCycle(S, n, spKey, false));
          if ((S.abTooltip || S.amSpends) && S.mb > 0) acts.push(arcaneCycle(S, n, spKey, true));
        });
      }
    }
    if (fireOk) {
      acts.push(cappedInstant(S, 'fireBlast', 8.0 - 1.0 * r('WakeOfFire')));
      if (r('BlastWave')) acts.push(cappedInstant(S, 'blastWave', 45.0));
    }
    if (r('PresenceOfMind')) {
      const pom = pomAction(S, pomSrc);
      if (pom !== null) acts.push(pom);
    }
    const evo = evocationMana(S);
    if (evo > 0) {
      const act = newAction('Evocation', uses(EVO_CD, S.T - EVO_TIME, EVO_LAG), { kind: 'evo' });
      act.t = EVO_TIME; act.m = -evo; act.n.time = EVO_TIME; act.n.time2 = EVO_TIME * EVO_TIME;
      acts.push(act);
    }
    // waiting out mana: shoot the wand (no mana spent, so full Spirit regen once the five-second rule clears, in
    // IDLE_BLOCK blocks). It blocks no cooldown.
    const idle = newAction('Idle', null, { kind: 'idle' });
    idle.t = 1.0; idle.m = -S.idleGain; idle.n.time = 1.0;
    if (S.wand > 0) { idle.d = S.wand; idle.parts = { Wand: S.wand }; }
    acts.push(idle);
    const fixed = S.fv ? scorchUpkeep(S) : null;
    return { acts, fixed };
  }

  // When potions, runes and gems go out, and how much of them the fight can still spend: room for the first
  // opened at topRate (the top action's mana per second above regen), each on its 2 min cooldown after; what
  // arrives too late to spend at topRate is stranded. Runes and gems share one cooldown: the slots are filled in the
  // better of two orders, runes only or the Ruby first then runes (with runes off, the gems in size order).
  function itemSchedule(S, topRate) {
    const o = S.o;
    const orders = [];
    if (opt(o, 'runes')) orders.push('runes');
    if (opt(o, 'gems')) orders.push('gems');
    if (!orders.length) orders.push('none');
    let best = null;
    orders.forEach(order => {
      const res = oneSchedule(S, topRate, order);
      const usable = res.pot + res.rune + res.gem - res.stranded;
      if (best === null || usable > best[0] + 1e-9) best = [usable, res];
    });
    return best[1];
  }
  function oneSchedule(S, topRate, order) {
    const o = S.o, T = S.T;
    const rate = Math.max(1e-6, topRate);
    const runes = opt(o, 'runes');
    const items = [];
    const hasPot = opt(o, 'potion') === 'mana';
    const tPot = POTION_MAX / rate;
    if (hasPot) for (let k = tPot; k <= T; k += ITEM_CD) items.push([k, POTION_MANA, 'potion']);
    let first = true, gi = 0;
    let k = hasPot ? tPot : 0.0;
    while (order !== 'none') {
      let amt, top, kind;
      if (order === 'gems' && gi < GEMS.length && (first || !runes)) { amt = GEMS[gi]; top = GEMS[gi] * GEM_ROOM; kind = 'gem'; gi += 1; }
      else if (runes) { amt = RUNE_MANA; top = RUNE_MAX; kind = 'rune'; }
      else break;
      if (first) k += top / rate;
      if (k > T) break;
      items.push([k, amt, kind]);
      first = false;
      k += ITEM_CD;
    }
    items.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
    let cum = 0.0, stranded = 0.0;
    for (let i = items.length - 1; i >= 0; i--) {
      cum += items[i][1];
      stranded = Math.max(stranded, cum - rate * (T - items[i][0]));
    }
    let pot = 0.0, rune = 0.0, gem = 0.0;
    items.forEach(it => { if (it[2] === 'potion') pot += it[1]; });
    items.forEach(it => { if (it[2] === 'rune') rune += it[1]; });
    items.forEach(it => { if (it[2] === 'gem') gem += it[1]; });
    return { pot, rune, gem, stranded, items };
  }

  // ---------------------------------------------------------------- the linear program
  // The uncapped actions on the upper concave hull of (mana per second, damage per second): at an optimum an
  // uncapped action in use maximises damage minus a mana price, so it is a hull vertex.
  function hull(acts, idx) {
    const pts = idx.map(i => [acts[i].m / acts[i].t, acts[i].d / acts[i].t, i]);
    pts.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
    const front = [];
    pts.forEach(p => { if (!(front.length && p[1] <= front[front.length - 1][1])) front.push(p); });
    const up = [];
    front.forEach(p => {
      while (up.length >= 2) {
        const [m1, d1] = up[up.length - 2], [m2, d2] = up[up.length - 1];
        if ((d2 - d1) * (p[0] - m1) <= (p[1] - d1) * (m2 - m1)) up.pop(); else break;
      }
      up.push(p);
    });
    return up.map(p => p[2]).sort((a, b) => a - b);
  }

  // max sum d x  s.t.  sum t x = tFree, sum m x <= M, 0 <= x <= cap (null = no cap). Vertices have at most two
  // actions strictly inside their bounds: enumerate them. Uncapped actions beaten on damage and mana per second go first.
  // Returns [value, x] with x a list of [index, amount] pairs in the order they were set.
  function solveLp(acts, tFree, M) {
    const unc = [];
    acts.forEach((a, i) => { if (a.cap === null) unc.push(i); });
    const keep = hull(acts, unc);
    const capped = [];
    acts.forEach((a, i) => { if (a.cap !== null && a.cap > 0) capped.push(i); });
    const cand = keep.concat(capped);
    let bestV = -1.0, bestX = null;
    const nc = cand.length;
    for (let size = 1; size <= 2; size++) {
      for (let qa = 0; qa < nc; qa++) {
        const qbStart = size === 2 ? qa + 1 : nc, qbEnd = size === 2 ? nc : nc + 1;
        for (let qb = qbStart; qb < qbEnd; qb++) {
          const basics = size === 1 ? [cand[qa]] : [cand[qa], cand[qb]];
          const others = capped.filter(i => !basics.includes(i));
          for (let mask = 0; mask < (1 << others.length); mask++) {
            let Tr = tFree, Mr = M, V = 0.0;
            const x = [];
            for (let bit = 0; bit < others.length; bit++) {
              if ((mask >> bit) & 1) {
                const i = others[bit], u = acts[i].cap;
                x.push([i, u]);
                Tr -= acts[i].t * u; Mr -= acts[i].m * u; V += acts[i].d * u;
              }
            }
            if (size === 1) {
              const a = acts[basics[0]];
              let xa = Tr / a.t;
              if (xa < -EPS || (a.cap !== null && xa > a.cap + EPS)) continue;
              xa = Math.max(0.0, xa);
              if (a.m * xa > Mr + 1e-6) continue;
              x.push([basics[0], xa]);
              V += a.d * xa;
            } else {
              const a = acts[basics[0]], b = acts[basics[1]];
              const det = a.t * b.m - b.t * a.m;
              if (Math.abs(det) < 1e-12) continue;
              let xa = (Tr * b.m - b.t * Mr) / det;
              let xb = (a.t * Mr - Tr * a.m) / det;
              if (xa < -EPS || xb < -EPS) continue;
              if (a.cap !== null && xa > a.cap + EPS) continue;
              if (b.cap !== null && xb > b.cap + EPS) continue;
              xa = Math.max(0.0, xa); xb = Math.max(0.0, xb);
              x.push([basics[0], xa]); x.push([basics[1], xb]);
              V += a.d * xa + b.d * xb;
            }
            if (V > bestV + 1e-9) { bestV = V; bestX = x; }
          }
        }
      }
    }
    return [bestV, bestX];
  }

  // ---------------------------------------------------------------- fixed point
  // Expected extra crits from one Combustion: 4 crits minus what those hits would crit anyway.
  function combExtra(c) {
    let probs = [1.0, 0.0, 0.0, 0.0];
    let expectedHits = 0.0;
    for (let i = 1; i < 60; i++) {
      const openP = probs[0] + probs[1] + probs[2] + probs[3];
      if (openP < 1e-12) break;
      expectedHits += openP;
      const p = Math.min(1.0, c + COMB_CRIT * Math.min(COMB_MAX, i));
      const nxt = [0.0, 0.0, 0.0, 0.0];
      for (let j = 0; j < 4; j++) {
        nxt[j] += probs[j] * (1 - p);
        if (j + 1 < 4) nxt[j + 1] += probs[j] * p;
      }
      probs = nxt;
    }
    return COMB_CRITS - c * expectedHits;
  }
  const initialState = () => ({ wcAvg: null, eta: 1.0 / 3.0, pyroTicks: 4.0, drift: 0.75, euMana: 0.0 });
  function planTotals(acts, x, fixed) {
    const tot = newCounters();
    x.forEach(([i, xi]) => { COUNTERS.forEach(k => { tot[k] += xi * acts[i].n[k]; }); });
    if (fixed !== null) COUNTERS.forEach(k => { tot[k] += fixed.n[k]; });
    return tot;
  }
  function nextState(S, tot, state) {
    const r = S.r, T = S.T;
    const st = Object.assign({}, state);
    const wc = r('WintersChill');
    if (wc && tot.frostHits > 0) {
      const shortfall = 2.5 * (wc + 1);     // stack-casts lost while stacks build: (r(r+1)/2) / (0.2 r)
      st.wcAvg = WC_PER_STACK * Math.max(0.0, wc - shortfall / tot.frostHits);
    }
    if (S.hs && tot.hsCasts > 0) {
      const p = Math.min(1.0, tot.hsCrit / tot.hsCasts);
      const tbar = Math.max(GCD, (T - tot.pyroTime) / tot.hsCasts);
      const a = 1 - Math.pow(1 - p, HS_WINDOW / tbar);
      st.eta = a * a / (1 + a + a * a);
    }
    if (tot.pyros > 0) {
      const mu = T / tot.pyros;
      let s = 0;
      for (let j = 1; j < 5; j++) s += Math.exp(-3.0 * j / mu);
      st.pyroTicks = s;
    } else st.pyroTicks = 4.0;
    if (tot.time > 0) st.drift = tot.time2 / (2 * tot.time);
    if (S.race === 'gnome' && tot.casts > 0) st.euMana = uses(ITEM_CD, T, 0) * 3 * EUREKA * tot.cost / tot.casts;
    return st;
  }
  // What a player casts when mana is no object, to open room for the first potion: among the uncapped actions within
  // 1% of the best damage per second, the one that spends fastest (a near-tie cannot flip the choice).
  function topAction(acts, lock) {
    if (lock && lock[0] < acts.length && acts[lock[0]].name === lock[1]) return acts[lock[0]];
    let best = 0.0;
    acts.forEach(a => { if (a.cap === null && a.t > 0 && a.d > 0) best = Math.max(best, a.d / a.t); });
    let top = null;
    acts.forEach(a => {
      if (a.cap === null && a.t > 0 && a.d > 0 && a.d / a.t >= TOP_BAND * best) {
        if (top === null || a.m / a.t > top.m / top.t) top = a;
      }
    });
    return top;
  }

  // The item sets a player may pick from: all of them, then (when that leaves something) without the potion, without
  // the runes and gems, and with none.
  function itemDrops(o) {
    const pot = opt(o, 'potion') === 'mana';
    const slots = !!(opt(o, 'runes') || opt(o, 'gems'));
    const drops = [{}];
    if (pot && slots) drops.push({ potion: 'none' }, { runes: false, gems: false });
    if (pot || slots) drops.push({ potion: 'none', runes: false, gems: false });
    return drops;
  }

  // The program with the items left after `drop`. From the pull to the first potion (or gem) the top action runs,
  // opening the room the item schedule needs (the opening); the program splits the rest.
  function withItems(S, acts, fixed, top, rate, drop) {
    const T = S.T;
    const sch = itemSchedule(Object.assign({}, S, { o: Object.assign({}, S.o, drop) }), rate);
    let M = S.maxMana + T * S.regenCast + sch.pot + sch.rune + sch.gem - sch.stranded + S.state.euMana;
    let tFree = T;
    if (fixed !== null) { tFree -= fixed.t; M -= fixed.m; }
    let opening = null;
    if (sch.items.length && top !== null) {
      const tOpen = Math.min(sch.items[0][0], tFree);
      opening = newAction('opening');
      addAction(opening, top, tOpen / top.t);
      opening.spec = top.spec;
      opening.name = top.name;
      tFree -= opening.t;
      M -= opening.m;
    }
    const [v, x] = solveLp(acts, tFree, M);
    return { score: v + (opening !== null ? opening.d : 0.0), v, x, M, opening, sch };
  }

  function solveOnce(S) {
    const { acts, fixed } = buildActions(S);
    const T = S.T;
    const top = topAction(acts, S.topLock);
    const rate = (top !== null ? top.m / top.t : 0.0) - S.regenCast;
    // the opening forces the top action for its length; when the regen above it is small (high mp5, a short fight)
    // that can cost more than an item brings, and a player would skip that item: the best of the item sets
    const drops = itemDrops(S.o);
    const picks = S.dropLock !== null && S.dropLock !== undefined ? [S.dropLock] : drops.map((d, k) => k);
    let best = null;
    picks.forEach(k => {
      const c = withItems(S, acts, fixed, top, rate, drops[k]);
      if (best === null || c.score > best.score + 1e-9) { best = c; best.drop = k; }
    });
    const { v, x, M, opening, sch } = best;
    const tot = planTotals(acts, x, fixed);
    const parts = {};
    x.forEach(([i, xi]) => { for (const k in acts[i].parts) parts[k] = (parts[k] || 0.0) + xi * acts[i].parts[k]; });
    [fixed, opening].forEach(extra => {
      if (extra !== null) for (const k in extra.parts) parts[k] = (parts[k] || 0.0) + extra.parts[k];
    });
    if (opening !== null) COUNTERS.forEach(k => { tot[k] += opening.n[k]; });
    // Combustion: each press adds a fixed number of crits (4 minus what those hits crit anyway), worth the plan's
    // average Fire crit (crit bonus, Ignite, and on Hot Streak spells a stack: eta Pyroblasts less the filler time
    // they take). Booked after the program so it cannot feed back into it.
    if (S.r('Combustion') && S.fireOk && tot.fireHits > 0) {
      const cBar = Math.min(1.0, tot.fireCrit / tot.fireHits);
      let value = tot.fireCritValue / tot.fireHits;
      if (S.hs) {
        const pyro = hsPyro(S, 0.0);
        let before = 0.0, pd = 0.0;
        for (const k in parts) before += parts[k];
        for (const k in pyro.parts) pd += pyro.parts[k];
        const net = pd - pyro.t * before / T;
        value += tot.hsHits / tot.fireHits * S.eta * Math.max(0.0, net);
      }
      parts.Combustion = uses(COMB_CD, T, 0) * combExtra(cBar) * value;
    }
    let racial = 0.0;
    if (S.race === 'gnome' && tot.casts > 0) racial = uses(ITEM_CD, T, 0) * 3 * EUREKA * tot.direct / tot.casts;
    if (S.race === 'undead') {
      const pl = TOTG_CHANCE * tot.landed / T;
      racial = pl / (1 + pl) * TOTG_HP * opt(S.o, 'maxHp') * T;
    }
    if (racial) parts.Racial = racial;
    const dpsParts = {};
    let total = 0;
    for (const k in parts) if (parts[k] > 1e-9) { dpsParts[k] = parts[k] / T; total += dpsParts[k]; }
    const plan = [];
    if (opening !== null) plan.push({ name: opening.name + ' (opening)', uses: opening.t / top.t, seconds: opening.t });
    const order = x.map(p => p[0]).sort((a, b) => a - b);
    const xv = {};
    x.forEach(([i, xi]) => { xv[i] = xi; });
    let idle = 0.0;
    order.forEach(i => {
      if (xv[i] > 1e-9) {
        let name = acts[i].name;
        if (name === 'Idle') name = S.wand > 0 ? 'Wand, full regen' : 'Idle, full regen';
        plan.push({ name, uses: xv[i], seconds: xv[i] * acts[i].t });
      }
      if (acts[i].name === 'Idle') idle += xv[i] * acts[i].t;
    });
    return { total, parts: dpsParts, plan, tot, idle, feasible: x.every(p => p[1] >= -1e-6),
      mana: { pool: S.maxMana, regen: T * S.regenCast, potions: sch.pot, runes: sch.rune, gems: sch.gem,
        stranded: sch.stranded, budget: M, fixed: fixed !== null ? fixed.m : 0.0 },
      items: sch.items, top: top !== null ? [acts.indexOf(top), top.name] : null, drop: best.drop, lp: v };
  }

  // The fixed point: solve, update the plan-dependent state, repeat. After two full updates the state moves halfway
  // to each new value (damping), so a plan that flips between two vertices settles between them. The opening action
  // and the item set are chosen afresh on the first DAMP_FROM + 1 passes and then kept, so two choices near a tie
  // cannot trade places on every pass.
  function runPlan(o, tal, fvPlan) {
    let state = initialState();
    let res = null;
    let lock = null, dropLock = null;
    for (let it = 0; it < ITERATIONS; it++) {
      const S = context(o, tal, fvPlan, state);
      S.topLock = lock;
      S.dropLock = dropLock;
      res = solveOnce(S);
      if (it === DAMP_FROM) { lock = res.top; dropLock = res.drop; }
      let nw = nextState(S, res.tot, state);
      if (it >= DAMP_FROM) {
        const d = {};
        for (const k in nw) d[k] = state[k] === null || nw[k] === null ? nw[k] : state[k] + DAMP * (nw[k] - state[k]);
        nw = d;
      }
      state = nw;
    }
    res.state = state;
    return res;
  }

  // Best plan for a talent build {key: rank}: with and without keeping Fire Vulnerability up, whichever is higher.
  function evaluate(o, tal) {
    const hasFv = (tal.ImprovedScorch || 0) > 0 && !opt(o, 'fireImmune');
    let res = runPlan(o, tal, false);
    res.fv = false;
    if (hasFv) {
      const alt = runPlan(o, tal, true);
      if (alt.total > res.total + 1e-9) { res = alt; res.fv = true; }
    }
    return res;
  }

  // ---------------------------------------------------------------- specs
  const SIM_ARCANE = { ArcaneFocus: 5, ImprovedChanneling: 5, ArcaneConcentration: 5, ArcaneGeometry: 2, ArcaneImpact: 3,
    ArcaneBlast: 1, ArcaneMeditation: 3, MissileBarrage: 1, PresenceOfMind: 1, ArcaneMind: 5, ArcaneInstability: 3, ArcanePower: 1,
    ElementalPrecision: 5, IceShards: 5, PiercingIce: 3, FrostChanneling: 3 };
  const SIM_FIRE = { Incineration: 3, ImprovedFireball: 5, Ignite: 5, FlameThrowing: 2, BurningSoul: 2, Pyroblast: 1,
    ImprovedScorch: 3, HotStreak: 1, MasterOfElements: 3, CriticalMass: 3, BlastWave: 1, FirePower: 5, Combustion: 1,
    ElementalPrecision: 5, IceShards: 5, PiercingIce: 3, FrostChanneling: 3 };
  const SIM_FROST = { ArcaneFocus: 5, ArcaneConcentration: 5, ArcaneGeometry: 1, ArcaneImpact: 3,
    ImprovedFrostbolt: 5, ElementalPrecision: 5, IceShards: 5, Frostbite: 3, PiercingIce: 3, IceLance: 1, IceBlock: 1,
    Shatter: 3, ColdSnap: 1, FingersOfFrost: 2, WintersChill: 5, IceBarrier: 1 };
  const FROST_MB = { ArcaneFocus: 5, ArcaneSubtlety: 2, ArcaneConcentration: 5, ArcaneImpact: 3, ArcaneMeditation: 2,
    MissileBarrage: 1,
    Incineration: 3,
    ImprovedFrostbolt: 5, ElementalPrecision: 5, IceShards: 5, PiercingIce: 3, FrostChanneling: 1, IceLance: 1, Shatter: 3,
    FingersOfFrost: 2, WintersChill: 5 };
  const FIRE_MB = { ArcaneFocus: 5, ImprovedChanneling: 1, ArcaneConcentration: 5, ArcaneImpact: 3, ArcaneBlast: 1,
    ArcaneMeditation: 3, MissileBarrage: 1,
    Incineration: 3, ImprovedFireball: 5, Ignite: 5, BurningSoul: 1, Pyroblast: 1, ImprovedScorch: 3, HotStreak: 1,
    MasterOfElements: 3, CriticalMass: 3, FirePower: 5, Combustion: 1,
    ElementalPrecision: 1 };
  const ARCANE_TUNED = { ArcaneFocus: 5, ImprovedChanneling: 1, ArcaneSubtlety: 2, ArcaneConcentration: 5, ArcaneImpact: 3,
    ArcaneBlast: 1, ArcaneMeditation: 3, MissileBarrage: 1, PresenceOfMind: 1, ArcaneMind: 5, ArcaneInstability: 3, ArcanePower: 1,
    Incineration: 3,
    ImprovedFrostbolt: 5, ElementalPrecision: 5, IceShards: 4, PiercingIce: 3 };
  const ARCANE_FIRE = { ArcaneFocus: 5, ImprovedChanneling: 1, ArcaneSubtlety: 2, ArcaneConcentration: 5, ArcaneImpact: 3,
    ArcaneBlast: 1, ArcaneMeditation: 3, MissileBarrage: 1, PresenceOfMind: 1, ArcaneMind: 5, ArcaneInstability: 3, ArcanePower: 1,
    Incineration: 3, ImprovedFireball: 5, Ignite: 5, BurningSoul: 1, Pyroblast: 1, ImprovedScorch: 3, HotStreak: 1,
    ElementalPrecision: 1 };

  const SPECS = [
    { id: 'frost-mb', name: 'Frost with Barrage 18/3/30', tree: 2, talents: FROST_MB,
      note: 'Frostbolt, Ice Lance on Fingers of Frost, free Arcane Missiles from Missile Barrage; Incineration for Ice Lance crits' },
    { id: 'fire-mb', name: 'Fire with Arcane Blast 19/31/1', tree: 1, talents: FIRE_MB,
      note: 'One Arcane Blast then Fireball, Fire Blast, Hot Streak Pyroblasts and Ignite, free Arcane Missiles from Barrage' },
    { id: 'arcane', name: 'Arcane 31/3/17', tree: 0, talents: ARCANE_TUNED,
      note: 'Arcane Blast then Frostbolt to spend the stacks, Missiles on Barrage, Arcane Power; Incineration for Blast crits' },
    { id: 'arcane-fire', name: 'Arcane with Ignite 31/19/1', tree: 0, talents: ARCANE_FIRE,
      note: 'Arcane Blast then Fireball to spend the stacks, Hot Streak Pyroblasts, Presence of Mind on Pyroblast' },
    { id: 'frost-sim', name: 'Frost 14/0/35 (sim build)', tree: 2, talents: SIM_FROST,
      note: "The ElliotWood sim's Frost build (2 points unspent), for comparison" },
    { id: 'arcane-sim', name: 'Arcane 35/0/16 (sim build)', tree: 0, talents: SIM_ARCANE,
      note: "The ElliotWood sim's Arcane build, for comparison" },
    { id: 'fire-sim', name: 'Fire 0/35/16 (sim build)', tree: 1, talents: SIM_FIRE,
      note: "The ElliotWood sim's Fire build, for comparison" },
  ];
  const FIRE_REASON = 'Not viable on a boss immune to Fire: Fireball, Scorch, Pyroblast and Ignite deal nothing. Use a Frost or Arcane build.';

  // ---------------------------------------------------------------- options (the page renders the calculator from these)
  const OPTIONS = [
    { id: 'race', label: 'Race', type: 'seg', choices: [['none', 'No racials'], ['human', 'Human'], ['gnome', 'Gnome'],
      ['skyborne', 'Skyborne'], ['orc', 'Orc'], ['undead', 'Undead'], ['troll', 'Troll']],
      hint: 'Human: +2% crit with a sword, +5% Spirit. Gnome: +5% max mana, Eureka! (+10% damage, -10% cost on 3 spells, 2 min). Skyborne: +1% haste. Orc: Blood Fury, +10% spell power for 15 s, 2 min. Undead: Touch of the Grave. Troll: Berserking, +10% haste for 10 s, 3 min.' },
    { id: 'sword', label: 'Sword in hand (+2% crit)', type: 'toggle', race: 'human',
      hint: 'Human Sword Specialization. The Coldflame Saber from Comprehension is a Mage sword.' },
    { id: 'maxHp', label: 'Your maximum health', type: 'range', min: 2000, max: 8000, step: 100, race: 'undead',
      hint: 'Touch of the Grave (caster version) drains 5% of your maximum health on 10% of damaging spells, 1 s cooldown, modelled as the Warlock page does. 4000 is an ASSUMPTION.' },
    { id: 'sp', label: 'Spell power', type: 'range', min: 200, max: 1000, step: 10,
      hint: 'Character sheet spell damage with your consumables (flask, elixirs, wizard oil). 500 matches the Warlock page.' },
    { id: 'crit', label: 'Spell crit', type: 'range', min: 0.03, max: 0.3, step: 0.005,
      hint: "Character sheet spell crit before talents and raid buffs, Intellect's share included (0.0168% a point)." },
    { id: 'gearHit', label: 'Hit from gear', type: 'range', min: 0, max: 0.16, step: 0.01,
      hint: 'Talents add up to 5% for their own school: Arcane Focus for Arcane, Elemental Precision for Fire and Frost. 16% caps a level 63 boss on the Classic table, unverified for Forever ([test m15](#tests)). Capped counts as every spell landing, as on the Warlock page; the sim keeps a 1% miss floor.' },
    { id: 'int', label: 'Intellect', type: 'range', min: 150, max: 500, step: 5,
      hint: 'Character sheet with your own Arcane Brilliance, before raid buffs and talents. 15 mana a point.' },
    { id: 'spirit', label: 'Spirit', type: 'range', min: 50, max: 350, step: 5,
      hint: 'Character sheet before raid buffs. Regen is 12.5 + Spirit/4 every 2 s outside the five-second rule; Mage Armor keeps half of it while casting.' },
    { id: 'mp5', label: 'Mana per 5 sec from gear', type: 'range', min: 0, max: 300, step: 5,
      hint: 'Gear only: raid buffs and Mageblood Elixir have their own switches. It keeps ticking while you cast.' },
    { id: 'fightLength', label: 'Fight length, seconds', type: 'range', min: 60, max: 600, step: 30,
      hint: 'Cooldowns, potions and Evocation are counted for this length.' },
    { id: 'fireImmune', label: 'Boss immune to Fire', type: 'toggle', group: 'The fight',
      hint: 'Fire builds drop out; the others stop casting Fire spells. Frostfire Bolt is treated as blocked too (ASSUMPTION).' },
    { id: 'raidBuffs', label: 'Raid buffs', type: 'seg',
      choices: [['all', 'All, with Mana Spring'], ['noTotem', 'No Shaman in your group'], ['none', 'None']],
      hint: 'Greater Blessing of Wisdom 40 mp5, Prayer of Spirit +40 Spirit, Gift of the Wild +16 Intellect and Spirit, and Mana Spring Totem 25 mp5 (your party only). Forever tooltip values. Both factions have Paladins and Shamans in Forever (Undead Paladins, Dwarf Shamans). Arcane Brilliance is yours, already in Intellect.' },
    { id: 'potion', label: 'Potion (2 min cooldown)', type: 'seg',
      choices: [['mana', 'Major Mana Potion'], ['blast', 'Major Spellblasting Potion'], ['none', 'None']],
      hint: 'Major Mana Potion: 1350 to 2250 mana. Major Spellblasting Potion: +47 spell damage for 30 s. They share one cooldown, and both cost gold.' },
    { id: 'runes', label: 'Demonic or Dark Runes', type: 'toggle', group: 'Consumables',
      hint: '900 to 1500 mana each on a 2 min cooldown shared with the mana gems. Each costs 600 to 1000 health that a healer pays, and gold.' },
    { id: 'gems', label: 'Mana gems, conjured before the pull', type: 'toggle', group: 'Consumables',
      hint: "Ruby 1100, Citrine 850, Jade 600, Agate 400 on average, one of each, on the runes' cooldown: each slot takes whichever gives more mana. Free, but conjuring costs mana before the pull." },
    { id: 'mageblood', label: 'Mageblood Elixir (12 mp5)', type: 'toggle', group: 'Consumables',
      hint: '12 mana every 5 s for an hour. Costs gold.' },
    { id: 'wandDps', label: 'Wand damage per second', type: 'range', min: 0, max: 120, step: 1,
      hint: 'While you wait out mana you shoot the wand, and with no mana spent Spirit regen runs in full once the five-second rule clears (in 15 s blocks, an ASSUMPTION). 57 is 0.9 x 60 + 3, the leveling model\'s wand (ASSUMPTION); Wand Specialization adds 13/25%. 0 means no wand.' },
    { id: 'iceLanceCoef', label: 'Ice Lance spell power coefficient', type: 'seg', untested: true,
      choices: [[0, '0 (client row)'], [0.143, '0.143 (sim)'], [0.429, '0.429'], [0.572, '0.572']],
      hint: 'Unknown. The client row reads 0, the sim guesses 0.143, and 0.429 or 0.572 are as likely. [test m4](#tests).' },
    { id: 'abMask', label: 'What Arcane Blast stacks raise', type: 'seg', untested: true,
      choices: [['client', 'Client masks (not Missiles)'], ['tooltip', 'Tooltip (Missiles too)']],
      hint: "The client's masks leave Arcane Missiles out of the +10% per stack; the tooltip says all your other spells. [test m8](#tests)." },
    { id: 'regenStack', label: 'Regen while casting', type: 'seg', untested: true,
      choices: [['add', 'Mage Armor and Meditation add (sim)'], ['max', 'They do not add'], ['full', 'No five-second rule']],
      hint: 'Mage Armor keeps 50% of Spirit regen while casting, Arcane Meditation up to 50%. [Tests m5 and m14](#tests).' },
    { id: 'evocation', label: 'Evocation return', type: 'seg', untested: true,
      choices: [[1, 'Sim formula'], [0.5, 'Half of it'], [0, 'Skip Evocation']],
      hint: 'The sim assumes 800 + 16 x Spirit + 1.6 x mp5 over the 8 s channel. [test m7](#tests).' },
    { id: 'igniteMunch', label: 'Ignite lost', type: 'seg', untested: true,
      choices: [[0, 'None (it rolls)'], [0.15, '15% lost'], [0.3, '30% lost']],
      hint: 'The sim rolls Ignite over and pays all of it. Whether some is lost when crits overlap, or when Mages share a target, is untested. [test m11](#tests).' },
    { id: 'downrank', label: 'Low spell ranks at 60', type: 'seg', untested: true,
      choices: [['top', 'Top ranks only'], ['full', 'Low ranks at full strength']],
      hint: "Measured in the beta up to level 19: low ranks keep their full spell power share there (ForeverChanges, DoubleZug's tests). Nobody has measured it at higher levels, and a level-based cut could still apply, so the default casts top ranks only. 'Full strength' lets the plan mix in cheap low ranks when mana runs short. The sim never downranks, except its Fire rotation's rank 1 Scorch below 10% mana. [test m13](#tests)." },
    { id: 'mbRate', label: 'Missile Barrage chance', type: 'seg', untested: true,
      choices: [[1, '40% / 20% (tooltip)'], [0.5, '20% / 10%']],
      hint: 'Arcane Blast 40%, Fireball, Frostbolt and Frostfire Bolt 20%, per the tooltip and the sim. The talent row also carries a 50% chance that could halve them. [test m18](#tests).' },
    { id: 'amSpends', label: 'Barrage Missiles end Arcane Blast stacks', type: 'toggle', untested: true, group: 'Untested',
      hint: "Off: Missiles leave the stacks alone, in line with the client masks, which leave Missiles out of the buff. On: as the sim plays (its Missiles channel ends the stacks), Barrage Missiles can close a Blast cycle in place of the spender and reset Arcane Blast's cost. No game source either way yet. [test m28](#tests)." },
    { id: 'topRanks', label: 'Top-rank tomes (Frostbolt 11, Fireball 12, Missiles 8)', type: 'toggle', untested: true,
      group: 'Untested',
      hint: "The tomes' only known source is Ruins of Ahn'Qiraj, not on the Forever roadmap, so the default uses the trainer ranks. [test m6](#tests)." },
    { id: 'levelResist', label: 'Partial resists from boss level (6%)', type: 'toggle', untested: true, group: 'Untested',
      hint: 'On, as the sim does: a level 63 boss resists 6% of non-binary spells on average (Frostbolt, Ice Lance and Blast Wave are binary). The Warlock page leaves this out, so damage here reads about 6% lower on non-binary spells than a like-for-like Warlock number. No test yet.' },
  ];

  // ---------------------------------------------------------------- the page API
  function evalSpec(o, s) {
    const head = { id: s.id, name: s.name, note: s.note };
    if (opt(o, 'fireImmune') && s.tree === 1) {
      return Object.assign(head, { total: 0, viable: false, reason: FIRE_REASON, parts: {}, plan: [], fv: false });
    }
    const res = evaluate(o, s.talents);
    return Object.assign(head, { total: res.total, viable: true, reason: '', parts: res.parts, plan: res.plan, fv: res.fv,
      idle: res.idle, feasible: res.feasible, mana: res.mana });
  }
  // Viable specs first, by total damage per second; non-viable ones (fireImmune) last, at zero, with a reason.
  function rank(o) {
    return SPECS.map(s => evalSpec(o, s)).sort((a, b) => (b.viable - a.viable) || (b.total - a.total));
  }
  function specTotal(o, id) {
    const s = SPECS.find(x => x.id === id);
    return s ? evalSpec(o, s).total : 0;
  }
  const withOpts = (o, p) => Object.assign({}, o, p);
  // Damage per second per +1 of spell power, Intellect, Spirit, mp5, and per +1 percentage point (0.01) of crit or
  // hit, and each in spell power. Intellect also raises crit, 0.0168% a point (crit is the character sheet value).
  function statWeights(o, id) {
    const f = p => specTotal(withOpts(o, p), id);
    const sp0 = opt(o, 'sp'), c0 = opt(o, 'crit'), h0 = opt(o, 'gearHit');
    const i0 = opt(o, 'int'), s0 = opt(o, 'spirit'), m0 = opt(o, 'mp5');
    const sp = (f({ sp: sp0 + 10 }) - f({ sp: Math.max(0, sp0 - 10) })) / (sp0 >= 10 ? 20 : 10 + sp0);
    const crit = (f({ crit: c0 + 0.01 }) - f({ crit: Math.max(0.0, c0 - 0.01) })) / (c0 >= 0.01 ? 2 : 1);
    const hit = f({ gearHit: h0 + 0.01 }) - f({ gearHit: h0 });
    const di = i0 >= 10 ? 10 : i0;
    const intel = (f({ int: i0 + 10, crit: c0 + 10 * CRIT_PER_INT }) - f({ int: i0 - di, crit: Math.max(0.0, c0 - di * CRIT_PER_INT) })) / (10 + di);
    const ds = s0 >= 10 ? 10 : s0;
    const spirit = (f({ spirit: s0 + 10 }) - f({ spirit: s0 - ds })) / (10 + ds);
    const dm = m0 >= 10 ? 10 : m0;
    const mp5 = (f({ mp5: m0 + 10 }) - f({ mp5: m0 - dm })) / (10 + dm);
    const ins = v => (sp > 0 ? v / sp : 0.0);
    return { sp, crit, hit, int: intel, spirit, mp5, critInSp: ins(crit), hitInSp: ins(hit), intInSp: ins(intel),
      spiritInSp: ins(spirit), mp5InSp: ins(mp5) };
  }
  // Swap an equipped item a for b. Items: { sp, crit, hit, int, spirit, mp5 }, crit and hit as fractions. The item's
  // Intellect also moves the character sheet crit.
  function compareItems(o, id, a, b) {
    const g = (it, k) => (it && it[k]) || 0;
    const base = specTotal(o, id);
    const dInt = g(b, 'int') - g(a, 'int');
    const swapped = specTotal(withOpts(o, {
      sp: Math.max(0, opt(o, 'sp') - g(a, 'sp') + g(b, 'sp')),
      crit: Math.max(0.0, opt(o, 'crit') - g(a, 'crit') + g(b, 'crit') + dInt * CRIT_PER_INT),
      gearHit: Math.max(0.0, opt(o, 'gearHit') - g(a, 'hit') + g(b, 'hit')),
      int: Math.max(0, opt(o, 'int') + dInt),
      spirit: Math.max(0, opt(o, 'spirit') - g(a, 'spirit') + g(b, 'spirit')),
      mp5: Math.max(0, opt(o, 'mp5') - g(a, 'mp5') + g(b, 'mp5')),
    }), id);
    return { base, swapped, diff: swapped - base, pct: base ? (swapped / base - 1) * 100 : 0 };
  }

  const api = { SPECS, DEFAULTS, OPTIONS, rank, specTotal, statWeights, compareItems, evaluate, itemSchedule, solveLp,
    combExtra, SPELL_ROWS };
  if (typeof module !== 'undefined') module.exports = api; else root.MageModel = api;
})(this);
