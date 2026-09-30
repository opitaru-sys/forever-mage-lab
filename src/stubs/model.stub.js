// STUB raid model. Implements the MageModel shape in CONTRACTS section 3 with FAKE numbers, so the page runs before
// model.js exists. src/build.py uses it only when model.js is missing (or with --stubs). Never publish it.
// The three spec builds are the ElliotWood sim's test builds (mage-research/talents/FINDINGS.md section 3);
// every number below them is made up.
(function (root) {
  'use strict';
  const RACES = ['human', 'gnome', 'skyborne', 'orc', 'undead', 'troll'];
  const SPECS = [
    { id: 'arcane-stub', name: 'Stub Arcane 35/0/16', tree: 0, note: 'STUB: fake numbers. Talents are the sim test build',
      talents: { ArcaneFocus: 5, ImprovedChanneling: 5, ArcaneConcentration: 5, ArcaneGeometry: 2, ArcaneImpact: 3, ArcaneBlast: 1,
        ArcaneMeditation: 3, MissileBarrage: 1, PresenceOfMind: 1, ArcaneMind: 5, ArcaneInstability: 3, ArcanePower: 1,
        ElementalPrecision: 5, IceShards: 5, PiercingIce: 3, FrostChanneling: 3 } },
    { id: 'fire-stub', name: 'Stub Fire 0/35/16', tree: 1, note: 'STUB: fake numbers. Talents are the sim test build',
      talents: { Incineration: 3, ImprovedFireball: 5, Ignite: 5, FlameThrowing: 2, BurningSoul: 2, Pyroblast: 1, ImprovedScorch: 3,
        HotStreak: 1, MasterOfElements: 3, CriticalMass: 3, BlastWave: 1, FirePower: 5, Combustion: 1,
        ElementalPrecision: 5, IceShards: 5, PiercingIce: 3, FrostChanneling: 3 } },
    { id: 'frost-stub', name: 'Stub Frost 14/0/35', tree: 2, note: 'STUB: fake numbers. Talents are the sim test build',
      talents: { ArcaneFocus: 5, ArcaneConcentration: 5, ArcaneGeometry: 1, ArcaneImpact: 3, ImprovedFrostbolt: 5, ElementalPrecision: 5,
        IceShards: 5, Frostbite: 3, PiercingIce: 3, IceLance: 1, IceBlock: 1, Shatter: 3, ColdSnap: 1, FingersOfFrost: 2,
        WintersChill: 5, IceBarrier: 1 } },
  ];
  const DEFAULTS = { race: 'none', sp: 500, crit: 0.1, gearHit: 0.1, int: 250, spirit: 120, mp5: 0, fightLength: 300,
    sword: true, consumables: true, fakeCoef: 0.143 };
  const OPTIONS = [
    { id: 'race', label: 'Race', type: 'seg', choices: [['none', 'No racials']].concat(RACES.map(r => [r, r])), hint: '' },
    { id: 'sword', label: 'Human with a sword equipped', type: 'toggle', race: 'human', hint: 'STUB option.' },
    { id: 'sp', label: 'Spell power', type: 'range', min: 200, max: 1000, step: 10, hint: '' },
    { id: 'crit', label: 'Crit chance, %', type: 'range', min: 0.05, max: 0.3, step: 0.01, hint: '' },
    { id: 'gearHit', label: 'Hit from gear, %', type: 'range', min: 0, max: 0.16, step: 0.01, hint: 'STUB hint with a [link](#tests).' },
    { id: 'int', label: 'Intellect', type: 'range', min: 100, max: 500, step: 5, hint: '' },
    { id: 'spirit', label: 'Spirit', type: 'range', min: 50, max: 300, step: 5, hint: '' },
    { id: 'mp5', label: 'Mana per 5 sec from gear and buffs', type: 'range', min: 0, max: 300, step: 5, hint: '' },
    { id: 'fightLength', label: 'Fight length, seconds', type: 'range', min: 60, max: 600, step: 30, hint: '' },
    { id: 'consumables', label: 'STUB consumables toggle', type: 'toggle', group: 'The fight', hint: 'Fake. Turns every total down by 10%.' },
    { id: 'fakeCoef', label: 'STUB untested choice', type: 'seg', choices: [[0.143, '0.143'], [0.429, '0.429'], [0.572, '0.572']], hint: 'Fake.', untested: true },
  ];

  function specTotal(o, id) {
    const i = SPECS.findIndex(s => s.id === id);
    if (i < 0) return 0;
    const hit = Math.min(0.16, o.gearHit || 0);
    const race = o.race && o.race !== 'none' ? 1 + (RACES.indexOf(o.race) + 1) / 1000 : 1;
    const base = (111 + 22 * i) + 0.2 * o.sp + 300 * o.crit + 100 * hit + 0.01 * o.int + 0.005 * o.spirit + 0.02 * o.mp5
      + (o.fakeCoef - 0.143) * 50 * (i === 2 ? 1 : 0);
    return base * (o.consumables ? 1 : 0.9) * race;
  }
  function rank(o) {
    return SPECS.map(s => {
      const total = specTotal(o, s.id);
      return { id: s.id, name: s.name, total, viable: true, reason: '',
        parts: { 'Stub spell A': total * 0.6, 'Stub spell B': total * 0.3, 'Stub spell C': total * 0.1 } };
    }).sort((a, b) => b.total - a.total);
  }
  // dps per point: +1 spell power, Intellect, Spirit or mp5, and +1 percentage point (0.01) of crit or hit
  function statWeights(o, id) {
    const t0 = specTotal(o, id);
    const d = (k, h) => specTotal(Object.assign({}, o, { [k]: o[k] + h }), id) - t0;
    const sp = d('sp', 1), crit = d('crit', 0.01), hit = d('gearHit', 0.01), int = d('int', 1), spirit = d('spirit', 1), mp5 = d('mp5', 1);
    return { sp, crit, hit, int, spirit, mp5, critInSp: crit / sp, hitInSp: hit / sp, intInSp: int / sp, spiritInSp: spirit / sp, mp5InSp: mp5 / sp };
  }
  function compareItems(o, id, a, b) {
    const shift = (x, s) => Object.assign({}, o, { sp: o.sp + s * x.sp, crit: o.crit + s * x.crit, gearHit: o.gearHit + s * x.hit,
      int: o.int + s * x.int, spirit: o.spirit + s * x.spirit, mp5: o.mp5 + s * x.mp5 });
    const base = specTotal(o, id);
    const swapped = specTotal(shift(b, 1), id) - specTotal(shift(a, 1), id) + base;
    return { base, swapped, diff: swapped - base, pct: (swapped / base - 1) * 100 };
  }

  const api = { STUB: true, SPECS, DEFAULTS, OPTIONS, rank, specTotal, statWeights, compareItems };
  if (typeof module !== 'undefined') module.exports = api; else root.MageModel = api;
})(this);
