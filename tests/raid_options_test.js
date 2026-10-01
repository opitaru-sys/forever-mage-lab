// Raid options against the Python reference, plus the contract checks the page relies on.
// 1. rank() for every fixture case (tests/raid_options_fixtures.json, written by tests/make_raid_fixtures.py): the
//    order, each total within 0.001 dps, viability, a reason on every non-viable spec, and no infeasible plan.
// 2. OPTIONS: every option has a default in DEFAULTS, of the right type and inside its range or choices, and the
//    fixture cases move every option and pick every choice at least once.
// 3. SPECS: legal builds under CONTRACTS section 1 (data/talents.json keys, 51 points, 5 per row, prerequisites at
//    full rank), unique ids, a tree, and no dashes the house style forbids in any page text.
// Run from the repo root: node tests/raid_options_test.js
const path = require('path');
const m = require(path.join(__dirname, '..', 'model.js'));
const fixtures = require(path.join(__dirname, 'raid_options_fixtures.json'));
const talents = require(path.join(__dirname, '..', 'data', 'talents.json')).talents;

const TOLERANCE = 0.001;
let failed = 0, checked = 0;
const check = (label, ok, detail) => {
  checked++;
  if (!ok) { failed++; console.error('FAIL ' + label + (detail ? '  ' + detail : '')); }
};

// ---------------------------------------------------------------- 1. every case against the Python
fixtures.cases.forEach(cs => {
  const o = Object.assign({}, m.DEFAULTS, cs.opts);
  const tag = JSON.stringify(cs.opts);
  const ranked = m.rank(o);
  check(`${tag} spec count`, ranked.length === cs.rank.length);
  cs.rank.forEach((exp, i) => {
    const r = ranked[i];
    check(`${tag} rank #${i + 1}`, r && r.id === exp.id && r.viable === exp.viable && Math.abs(r.total - exp.total) <= TOLERANCE,
      r ? `got ${r.id} ${r.viable} ${r.total.toFixed(4)} expected ${exp.id} ${exp.viable} ${exp.total}` : 'missing');
    if (!r) return;
    if (!r.viable) {
      check(`${tag} ${r.id} carries a reason`, typeof r.reason === 'string' && r.reason.length > 0);
      check(`${tag} ${r.id} scores zero`, r.total === 0);
    } else {
      check(`${tag} ${r.id} plan is feasible`, r.feasible === true && r.idle >= -1e-9);
      const sum = Object.values(r.parts).reduce((a, b) => a + b, 0);
      check(`${tag} ${r.id} parts add up`, Math.abs(sum - r.total) < 1e-6, `${sum} vs ${r.total}`);
    }
  });
  const viable = ranked.filter(r => r.viable);
  for (let i = 1; i < viable.length; i++) check(`${tag} sorted`, viable[i - 1].total >= viable[i].total);
});
console.log(`rank: ${fixtures.cases.length} cases checked against the Python`);

// ---------------------------------------------------------------- 2. options metadata and coverage
const moved = new Set(), picked = new Set();
fixtures.cases.forEach(cs => Object.entries(cs.opts).forEach(([k, v]) => {
  if (v !== m.DEFAULTS[k]) moved.add(k);
  picked.add(k + '=' + JSON.stringify(v));
}));
Object.entries(m.DEFAULTS).forEach(([k, v]) => picked.add(k + '=' + JSON.stringify(v)));
const ids = new Set();
m.OPTIONS.forEach(op => {
  check('option id unique: ' + op.id, !ids.has(op.id));
  ids.add(op.id);
  const d = m.DEFAULTS[op.id];
  check('option has a default: ' + op.id, d !== undefined);
  check('option has a label: ' + op.id, typeof op.label === 'string' && op.label.length > 0);
  check('option has a hint: ' + op.id, typeof op.hint === 'string');
  if (op.type === 'toggle') check('toggle default is boolean: ' + op.id, typeof d === 'boolean');
  else if (op.type === 'range') {
    check('range default inside: ' + op.id, typeof d === 'number' && d >= op.min && d <= op.max && op.step > 0);
    const steps = (d - op.min) / op.step;
    check('range default on a step: ' + op.id, Math.abs(steps - Math.round(steps)) < 1e-9);
  } else if (op.type === 'seg') {
    check('seg default is a choice: ' + op.id, op.choices.some(c => c[0] === d));
    op.choices.forEach(c => check(`choice ${op.id}=${c[0]} is covered by a case`, picked.has(op.id + '=' + JSON.stringify(c[0]))));
  } else check('option type: ' + op.id, false, op.type);
  check('option is moved by a case: ' + op.id, moved.has(op.id));
});
['sp', 'crit', 'gearHit', 'int', 'spirit', 'mp5', 'race', 'fightLength'].forEach(k => check('stat input listed: ' + k, ids.has(k)));
['iceLanceCoef', 'abMask', 'amSpends', 'regenStack', 'evocation', 'igniteMunch', 'downrank', 'mbRate', 'topRanks',
  'levelResist', 'iceLanceBinary', 'fingersOnBoss']
  .forEach(k => check('untested flag: ' + k, m.OPTIONS.find(op => op.id === k).untested === true));
console.log(`options: ${m.OPTIONS.length} checked, ${moved.size} moved by the cases`);

// ---------------------------------------------------------------- 3. specs and text
const byKey = Object.fromEntries(talents.map(t => [t.k, t]));
const specIds = new Set();
m.SPECS.forEach(s => {
  check('spec id unique: ' + s.id, !specIds.has(s.id));
  specIds.add(s.id);
  check('spec tree: ' + s.id, [0, 1, 2].includes(s.tree));
  let total = 0;
  const errs = [];
  Object.entries(s.talents).forEach(([k, v]) => {
    const t = byKey[k];
    if (!t) { errs.push('unknown ' + k); return; }
    if (!(v >= 1 && v <= t.m)) errs.push(k + ' rank ' + v);
    total += v;
    const above = talents.filter(u => u.t === t.t && u.r < t.r).reduce((a, u) => a + (s.talents[u.k] || 0), 0);
    if (above < 5 * t.r) errs.push(`${k} needs ${5 * t.r} above, has ${above}`);
    if (t.req && (s.talents[t.req[0]] || 0) < t.req[1]) errs.push(`${k} needs ${t.req[0]} ${t.req[1]}`);
  });
  if (total > 51) errs.push(total + ' points');
  check('spec is a legal build: ' + s.id, errs.length === 0, errs.join('; '));
});
const DASH = new RegExp('[' + String.fromCharCode(0x2013) + String.fromCharCode(0x2014) + ']');
const texts = [].concat(m.OPTIONS.map(op => [op.label, op.hint].concat((op.choices || []).map(c => c[1]))),
  m.SPECS.map(s => [s.name, s.note])).flat();
texts.forEach(t => check('no en or em dash: ' + t.slice(0, 40), !DASH.test(t)));
const lead = m.rank(m.DEFAULTS);
lead.forEach(r => check('reason text has no dash: ' + r.id, !DASH.test(r.reason || '')));
const fi = m.rank(Object.assign({}, m.DEFAULTS, { fireImmune: true }));
check('fire-immune: Fire specs rank last, not viable', fi.filter(r => !r.viable).every(r => m.SPECS.find(s => s.id === r.id).tree === 1)
  && fi.slice(-fi.filter(r => !r.viable).length).every(r => !r.viable));
check('fire-immune: specTotal of a Fire spec is 0', m.specTotal(Object.assign({}, m.DEFAULTS, { fireImmune: true }), 'fire-mb') === 0);

if (failed) { console.error(`\n${failed} of ${checked} option checks failed`); process.exit(1); }
console.log(`\nAll ${checked} option checks passed (tolerance ${TOLERANCE}).`);
