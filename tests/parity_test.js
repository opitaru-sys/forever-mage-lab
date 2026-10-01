// Parity check: model.js (the page's raid model) against models/raid_model.py (the reference).
// Every spec across a 3x3 grid of spell power and crit, race none, every other option at its default. EXPECTED is
// written by tests/make_raid_fixtures.py; a cell may differ by at most 0.001 dps.
// Run from the repo root: node tests/parity_test.js
const path = require('path');
const m = require(path.join(__dirname, '..', 'model.js'));

// Columns follow SPEC_ORDER (the model's SPECS order when the table was written).
const SPEC_ORDER = ['frost-mb', 'fire-mb', 'arcane', 'arcane-fire', 'frost-sim', 'arcane-sim', 'fire-sim'];
const EXPECTED = {
  '300,0.05': [423.3050, 395.5339, 382.7449, 384.5386, 383.0418, 356.0509, 315.1717],
  '300,0.10': [438.4442, 414.5638, 397.5521, 404.9618, 397.8712, 370.6119, 335.1850],
  '300,0.20': [468.7225, 457.0634, 427.3035, 446.4720, 427.5302, 399.7078, 377.6515],
  '500,0.05': [515.6871, 484.6850, 467.8272, 469.6773, 466.5211, 435.1278, 399.2923],
  '500,0.10': [534.2441, 510.1856, 486.1004, 495.5022, 484.7095, 452.8476, 426.5621],
  '500,0.20': [571.3581, 561.4206, 524.9251, 547.0174, 521.0862, 488.9476, 478.2384],
  '800,0.05': [654.2602, 618.4119, 600.4734, 602.8696, 591.7401, 554.7155, 528.7612],
  '800,0.10': [677.9440, 652.2942, 625.5321, 633.9980, 614.9668, 578.6666, 562.1474],
  '800,0.20': [725.3116, 720.6892, 675.7663, 698.4044, 661.4203, 627.3988, 629.1187],
};

const TOLERANCE = 0.001;
const SP_VALUES = [300, 500, 800];
const CRIT_VALUES = [0.05, 0.10, 0.20];

let failures = 0, checked = 0;
const ids = m.SPECS.map(s => s.id);
if (ids.join() !== SPEC_ORDER.join()) {
  console.error('SPECS changed since the table was written: ' + ids.join() + ' vs ' + SPEC_ORDER.join());
  failures++;
}
for (const sp of SP_VALUES) {
  for (const crit of CRIT_VALUES) {
    const key = `${sp},${crit.toFixed(2)}`;
    const expected = EXPECTED[key];
    if (!expected) { console.error('No expected row for ' + key); failures++; continue; }
    const o = Object.assign({}, m.DEFAULTS, { sp, crit, race: 'none' });
    const got = SPEC_ORDER.map(id => m.specTotal(o, id));
    got.forEach((g, i) => {
      checked++;
      const diff = Math.abs(g - expected[i]);
      if (!(diff <= TOLERANCE)) {
        console.error(`MISMATCH sp=${sp} crit=${crit} ${SPEC_ORDER[i]}: got ${g.toFixed(4)} expected ${expected[i]} (diff ${diff.toFixed(4)})`);
        failures++;
      }
    });
    console.log(`sp=${sp} crit=${crit}: ` + got.map(v => v.toFixed(1)).join(' '));
  }
}
if (failures > 0) {
  console.error(`\n${failures} mismatch(es) out of ${checked} checks.`);
  process.exit(1);
}
console.log(`\nAll ${checked} checks passed (tolerance ${TOLERANCE}).`);
