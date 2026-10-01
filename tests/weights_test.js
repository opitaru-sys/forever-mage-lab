// Stat weights and item comparison: model.js against the Python fixtures, plus sanity checks.
// Weights are damage per second per +1 spell power, Intellect, Spirit or mp5, and per +1 percentage point (0.01)
// of crit or hit. Run from the repo root: node tests/weights_test.js
const path = require('path');
const m = require(path.join(__dirname, '..', 'model.js'));
const fixtures = require(path.join(__dirname, 'raid_options_fixtures.json'));

const TOLERANCE = 0.001;
let failed = 0, checked = 0;
const check = (label, ok, detail) => {
  checked++;
  if (!ok) { failed++; console.error('FAIL ' + label + (detail ? '  ' + detail : '')); }
};
const close = (a, b, tol) => Math.abs(a - b) <= tol;
const opts = extra => Object.assign({}, m.DEFAULTS, extra);

// 1. Against the Python.
fixtures.weights.forEach(cs => {
  const o = opts(cs.opts);
  Object.entries(cs.weights).forEach(([id, exp]) => {
    const w = m.statWeights(o, id);
    Object.entries(exp).forEach(([k, v]) => check(`weights ${JSON.stringify(cs.opts)} ${id} ${k}`, close(w[k], v, TOLERANCE),
      `got ${w[k]} expected ${v}`));
  });
});
fixtures.items.forEach(cs => {
  const o = opts(cs.opts);
  Object.entries(cs.result).forEach(([id, exp]) => {
    const r = m.compareItems(o, id, cs.a, cs.b);
    Object.entries(exp).forEach(([k, v]) => check(`compareItems ${JSON.stringify(cs.opts)} ${id} ${k}`, close(r[k], v, TOLERANCE),
      `got ${r[k]} expected ${v}`));
  });
});

// 2. Sanity.
m.SPECS.forEach(s => {
  const w = m.statWeights(opts({ gearHit: 0.08 }), s.id);
  check('weights positive below the hit cap: ' + s.id, w.sp > 0 && w.crit > 0 && w.hit > 0 && w.int > 0,
    `sp ${w.sp.toFixed(3)} crit ${w.crit.toFixed(2)} hit ${w.hit.toFixed(2)} int ${w.int.toFixed(3)}`);
  check('spirit and mp5 never hurt: ' + s.id, w.spirit >= -1e-9 && w.mp5 >= -1e-9);
  check('in-spell-power ratios: ' + s.id, close(w.critInSp, w.crit / w.sp, 1e-9) && close(w.hitInSp, w.hit / w.sp, 1e-9)
    && close(w.intInSp, w.int / w.sp, 1e-9) && close(w.spiritInSp, w.spirit / w.sp, 1e-9) && close(w.mp5InSp, w.mp5 / w.sp, 1e-9));
  const capped = m.statWeights(opts({ gearHit: 0.16 }), s.id);
  check('hit weight is zero at the cap: ' + s.id, capped.hit === 0);
  const same = m.compareItems(opts({}), s.id, { sp: 30, crit: 0.01, hit: 0, int: 10, spirit: 5, mp5: 0 },
    { sp: 30, crit: 0.01, hit: 0, int: 10, spirit: 5, mp5: 0 });
  check('identical swap is zero: ' + s.id, close(same.diff, 0, 1e-9));
  const up = m.compareItems(opts({}), s.id, { sp: 20 }, { sp: 40 });
  check('+20 spell power swap is positive: ' + s.id, up.diff > 0, up.diff.toFixed(2));
  const direct = m.specTotal(opts({ mp5: 50, fightLength: 180 }), s.id);
  const carried = m.compareItems(opts({ mp5: 50, fightLength: 180 }), s.id, {}, {});
  check('compareItems carries the options: ' + s.id, close(carried.base, direct, 1e-9));
});
// The item's Intellect also moves the character sheet crit.
const intSwap = m.compareItems(opts({}), 'arcane', { int: 0 }, { int: 20 });
const byHand = m.specTotal(opts({ int: m.DEFAULTS.int + 20, crit: m.DEFAULTS.crit + 20 * 0.000168 }), 'arcane');
check('Intellect in compareItems raises crit too', close(intSwap.swapped, byHand, 1e-9));
// Options pass through: on a Fire-immune boss a Fire build has no weight.
check('fire-immune Fire spec weight is 0', m.statWeights(opts({ fireImmune: true }), 'fire-sim').sp === 0);

if (failed) { console.error(`\n${failed} of ${checked} weight checks failed`); process.exit(1); }
console.log(`All ${checked} weight checks passed (tolerance ${TOLERANCE}).`);
