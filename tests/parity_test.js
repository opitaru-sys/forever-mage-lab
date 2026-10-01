// Parity check: model.js (the page's raid model) against models/raid_model.py (the reference).
// Every spec across a 3x3 grid of spell power and crit, race none, every other option at its default. EXPECTED is
// written by tests/make_raid_fixtures.py; a cell may differ by at most 0.001 dps.
// Run from the repo root: node tests/parity_test.js
const path = require('path');
const m = require(path.join(__dirname, '..', 'model.js'));

// Columns follow SPEC_ORDER (the model's SPECS order when the table was written).
const SPEC_ORDER = ['frost-mb', 'fire-mb', 'arcane', 'arcane-fire', 'frost-sim', 'arcane-sim', 'fire-sim'];
const EXPECTED = {
  '300,0.05': [421.6976, 390.7899, 380.1238, 378.6102, 369.9752, 354.0492, 304.0877],
  '300,0.10': [436.8367, 409.5897, 395.0640, 398.2568, 384.2924, 368.5774, 323.4791],
  '300,0.20': [467.1151, 449.2815, 425.1951, 438.5032, 412.9267, 397.6364, 364.4985],
  '500,0.05': [513.7168, 478.7922, 465.4100, 463.8745, 450.2206, 432.6696, 384.8519],
  '500,0.10': [532.2738, 501.9700, 483.7728, 487.2724, 467.7806, 450.3681, 411.2496],
  '500,0.20': [569.3878, 551.1112, 522.6385, 538.5499, 502.9006, 486.4517, 461.1949],
  '800,0.05': [651.7456, 610.7956, 597.5467, 596.6731, 570.5887, 551.8704, 509.1518],
  '800,0.10': [675.4294, 641.5946, 622.6054, 627.1345, 593.0130, 575.8489, 541.5193],
  '800,0.20': [722.7969, 707.9991, 672.8230, 690.4061, 637.8615, 624.5612, 606.2395],
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
