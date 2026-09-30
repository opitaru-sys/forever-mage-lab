// STUB leveling model. Implements the LevelingModel shape in CONTRACTS section 4 with FAKE numbers, so the page runs
// before leveling.js exists. src/build.py uses it only when leveling.js is missing (or with --stubs). Never publish it.
(function (root) {
  'use strict';
  // a few Frost and Fire keys, so the builder shows both "counts in the score" and "not in the score"
  const SCORED = ['ImprovedFrostbolt', 'ElementalPrecision', 'IceShards', 'PiercingIce', 'Shatter', 'WintersChill',
    'ImprovedFireball', 'Ignite', 'FirePower', 'ArcaneFocus'];

  function evaluate(L, tal, gear, opts) {
    const pts = Object.keys(tal || {}).filter(k => SCORED.includes(k)).reduce((a, k) => a + tal[k], 0);
    const race = opts && opts.race && opts.race !== 'none' ? 0.5 : 0;
    const ttk = Math.max(6, 20 - 0.1 * L - 0.1 * pts - (gear === 2 ? 1 : 0) - race);
    const rest = 10 + 0.05 * L;
    return { spk: ttk + rest + 8, ttk, rest, policy: pts > 5 ? 'stub-b' : 'stub-a' };
  }
  const policyLabel = name => 'STUB rotation "' + name + '": models not wired yet';

  const api = { STUB: true, SCORED, evaluate, policyLabel };
  if (typeof module !== 'undefined') module.exports = api; else root.LevelingModel = api;
})(this);
