// Checks leveling.js against the Python leveling model on a grid of builds, levels, gear, races and options.
// Run from the repo root: node tests/leveling_parity_test.js
// Regenerate the fixtures with: python tests/make_leveling_fixtures.py
const fs = require('fs');
const path = require('path');
const m = require('../leveling.js');
const cases = require('./leveling_fixtures.json');
const talents = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'talents.json'), 'utf8')).talents;

// Python option names (evaluate keyword arguments) to their leveling.js opts names
const OPT = { hp_mults: 'hpMults', top: 'top', pair_top: 'pairTop', mods: 'mods', downrank: 'downrank', travel: 'travel' };
for (const js in m.OPT_MAP) OPT[m.OPT_MAP[js]] = js;
const FIELDS = ['spk', 'ttk', 'rest', 'taken', 'pots', 'evo', 'mana_spent'];

let failed = 0, maxDiff = 0;
for (const c of cases) {
  const opts = { race: c.race };
  for (const k in c.opts) {
    if (OPT[k] === undefined) throw new Error('no leveling.js name for option ' + k);
    opts[OPT[k]] = c.opts[k];
  }
  const r = m.evaluate(c.level, c.talents, c.gear, opts);
  let ok = r.policy === c.policy && r.feasible === c.feasible;
  for (const f of FIELDS) {
    const d = Math.abs(r[f] - c[f]);
    maxDiff = Math.max(maxDiff, d);
    if (!(d <= 1e-9 * Math.max(1, Math.abs(c[f])))) ok = false;
  }
  const label = m.policyLabel(r.policy);
  if (typeof label !== 'string' || !label || label.includes('undefined')) ok = false;
  if (!ok) {
    failed++;
    if (failed <= 10) console.log('FAIL', c.level, c.build, 'gear', c.gear, c.race, JSON.stringify(c.opts),
      '| py', c.policy, c.spk, '| js', r.policy, r.spk);
  }
}
// the chill's slow follows Permafrost's ranks (Python's value, and data/talents.json directly)
{
  const per = talents.find(t => t.k === 'Permafrost').perRank.extraSlowPct;
  const frostbolt = m.POLICIES.find(p => p[0] === 'Frostbolt')[1];
  for (const c of require('./leveling_slow_fixtures.json')) {
    const got = m.fightConsts(m.makeChar(c.level, c.talents, 1, 'none', {}), frostbolt).slow;
    const want = 0.40 + (c.rank ? per[c.rank - 1] / 100 : 0);
    if (Math.abs(got - c.slow) > 1e-12 || Math.abs(got - want) > 1e-12) {
      failed++;
      console.log('SLOW: Permafrost', c.rank, 'gives', got, 'want', want);
    }
  }
}
// every talent is either scored or has a reason it is not
const keys = talents.map(t => t.k);
const covered = new Set(m.SCORED.concat(Object.keys(m.UNSCORED)));
const missing = keys.filter(k => !covered.has(k));
const extra = [...covered].filter(k => !keys.includes(k));
const both = m.SCORED.filter(k => m.UNSCORED[k] !== undefined);
if (missing.length || extra.length || both.length) {
  failed++;
  console.log('SCORED/UNSCORED mismatch: missing', missing, 'unknown', extra, 'in both', both);
}
// the evaluate cache returns equal copies: changing one result cannot change the next answer
{
  const c = cases[cases.length - 1];
  const a = m.evaluate(c.level, c.talents, c.gear, { race: c.race });
  a.spk = -1; a.policy = 'changed';
  const b = m.evaluate(c.level, c.talents, c.gear, { race: c.race });
  const u = m.evaluateUncached(c.level, c.talents, c.gear, { race: c.race });
  if (b.spk !== u.spk || b.policy !== u.policy || b.spk !== c.spk) { failed++; console.log('CACHE: a cached result changed'); }
}
if (failed) { console.log(`\n${failed} of ${cases.length} leveling checks failed (largest difference ${maxDiff})`); process.exit(1); }
console.log(`All ${cases.length} leveling cases match the Python model (largest difference ${maxDiff}).`);
