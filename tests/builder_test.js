// Talent rules, share links and class data checks. Run from the repo root: node tests/builder_test.js
// Covers src/talentcore.js (point rules, prerequisites, #b- encode and decode) and src/class.js (races, icons,
// orders and spec cards legal under the rules). Exits 1 on the first failed group, with every failure listed.
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.join(__dirname, '..');
const TalentCore = require(path.join(ROOT, 'src', 'talentcore.js'));
const CLASS = require(path.join(ROOT, 'src', 'class.js'));
const DATA = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'talents.json'), 'utf8'));
const core = TalentCore.make(DATA.talents, CLASS.talentRules);
const T = DATA.talents;

let checks = 0;
const failures = [];
function check(name, fn) {
  try { fn(); checks++; } catch (e) { failures.push(name + ': ' + e.message); }
}

// deterministic random numbers (mulberry32), so a failure reproduces
let seed = 20261001;
function rnd() {
  seed |= 0; seed = seed + 0x6D2B79F5 | 0;
  let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
  return ((t ^ t >>> 14) >>> 0) / 4294967296;
}
// a random legal build at level L: add random legal points until a random budget is spent or nothing fits
function randomBuild(L) {
  let r = core.empty();
  const budget = Math.floor(rnd() * (core.points(L) + 1));
  for (let n = 0; n < budget; n++) {
    const open = T.filter(x => core.canAdd(r, x.k, L));
    if (!open.length) break;
    const x = open[Math.floor(rnd() * open.length)];
    r = Object.assign({}, r, { [x.k]: r[x.k] + 1 });
  }
  return r;
}
const digitsOf = r => T.map(x => r[x.k] || 0).join('');

// ---------------------------------------------------------------- the frozen talent contract
check('54 talents, 3 trees, known shape', () => {
  assert.strictEqual(T.length, 54);
  assert.deepStrictEqual(DATA.trees, ['Arcane', 'Fire', 'Frost']);
  assert.deepStrictEqual([0, 1, 2].map(t => T.filter(x => x.t === t).length), [18, 17, 19]);
  assert.strictEqual(core.N, 54);
});
check('talent list is in tree, row, col order', () => {
  for (let i = 1; i < T.length; i++) {
    const a = T[i - 1], b = T[i];
    assert.ok(a.t < b.t || (a.t === b.t && (a.r < b.r || (a.r === b.r && a.c < b.c))), 'out of order at ' + b.k);
  }
});
check('points rule', () => {
  assert.strictEqual(core.points(9), 0); assert.strictEqual(core.points(10), 1); assert.strictEqual(core.points(60), 51);
});

// ---------------------------------------------------------------- round trips
check('random legal builds round-trip at every level 10 to 60', () => {
  let n = 0;
  for (let L = 10; L <= 60; L++) {
    for (let i = 0; i < 20; i++) {
      const r = randomBuild(L), gear = 1 + (i % 2);
      assert.ok(core.buildOk(r, L), 'generator made an illegal build at ' + L);
      const h = core.encode(L, r, gear), d = core.decode(h);
      assert.ok(d, 'decode rejected a legal build: ' + h);
      assert.strictEqual(d.level, L); assert.strictEqual(d.gear, gear);
      assert.deepStrictEqual(d.ranks, core.clean(r));
      assert.strictEqual(core.encode(d.level, d.ranks, d.gear), h);
      n++;
    }
  }
  assert.strictEqual(n, 51 * 20);
});
check('full builds at 60 round-trip and orderFor reaches them legally', () => {
  for (let i = 0; i < 200; i++) {
    const r = randomBuild(60), main = Math.floor(rnd() * 3);
    const order = core.orderFor(r, main);
    assert.strictEqual(order.length, core.spent(r));
    for (let p = 1; p <= order.length; p++) {
      const partial = core.fromOrder(order, p + 9);
      assert.ok(core.buildOk(partial, p + 9), 'orderFor prefix ' + p + ' is illegal');
    }
    assert.deepStrictEqual(core.fromOrder(order, 60), core.clean(r));
  }
});

// ---------------------------------------------------------------- rejections
const base = () => { const r = core.empty(); r.ArcaneFocus = 5; r.ImprovedChanneling = 2; r.ArcaneConcentration = 3; return r; };  // 10 points, legal at 19+
const good = 'b-30-' + digitsOf(base()) + '-2';
check('the reference link decodes', () => { assert.ok(core.decode(good)); });
check('rejects wrong digit counts', () => {
  const d = digitsOf(base());
  assert.strictEqual(core.decode('b-30-' + d.slice(1) + '-2'), null);
  assert.strictEqual(core.decode('b-30-' + d + '0-2'), null);
  assert.strictEqual(core.decode('b-30--2'), null);
});
check('rejects a digit above a talent max rank', () => {
  T.forEach((x, i) => {
    if (x.m >= 9) return;
    const d = digitsOf(core.empty()).split(''); d[i] = String(x.m + 1);
    assert.strictEqual(core.decode('b-60-' + d.join('') + '-1'), null, x.k + ' accepted ' + (x.m + 1));
  });
});
check('rejects row gating breaks', () => {
  const r = core.empty(); r.ArcaneSubtlety = 1;          // row 1 with nothing in row 0
  assert.strictEqual(core.decode('b-60-' + digitsOf(r) + '-1'), null);
  const s = core.empty(); s.ArcaneFocus = 4; s.ArcaneSubtlety = 1;   // 4 below row 1, needs 5
  assert.strictEqual(core.decode('b-60-' + digitsOf(s) + '-1'), null);
  s.ArcaneFocus = 5;
  assert.ok(core.decode('b-60-' + digitsOf(s) + '-1'), 'exactly 5 below should unlock row 1');
});
check('rejects every missing prerequisite, and only because of it', () => {
  const reqs = T.filter(x => x.req);
  assert.ok(reqs.length >= 6, 'expected the six prerequisites in data/talents.json');
  reqs.forEach(x => {
    const [need, ranks] = x.req, needRow = T.find(y => y.k === need).r;
    const ok = core.fromOrder(core.orderFor(fillTo(x), x.t), 60);
    assert.ok(core.buildOk(ok, 60), 'setup build for ' + x.k + ' should be legal');
    // move one point from the prerequisite to a talent in the same or a lower row: row gating stays the same or better
    const spare = T.find(y => y.t === x.t && y.r <= needRow && y.k !== need && !y.req && ok[y.k] < y.m);
    assert.ok(spare, 'no spare talent for ' + x.k);
    const broken = Object.assign({}, ok, { [need]: ranks - 1, [spare.k]: ok[spare.k] + 1 });
    assert.ok(core.buildOk(Object.assign({}, broken, { [need]: ranks }), 60), 'control build for ' + x.k + ' should be legal');
    assert.strictEqual(core.decode('b-60-' + digitsOf(broken) + '-1'), null, x.k + ' accepted without full ' + need);
  });
});
check('rejects trailing and leading characters', () => {
  ['\r', '\n', '\r\n', ' ', 'x', '#', '0', '-'].forEach(c => {
    assert.strictEqual(core.decode(good + c), null, 'trailing ' + JSON.stringify(c));
    assert.strictEqual(core.decode(c + good), null, 'leading ' + JSON.stringify(c));
  });
  assert.strictEqual(core.decode(good.replace('b-', 'B-')), null);
});
check('rejects levels outside 10 to 60 and bad gear', () => {
  const d = digitsOf(core.empty());
  ['0', '9', '09', '61', '99', '100', '-1'].forEach(L => assert.strictEqual(core.decode('b-' + L + '-' + d + '-1'), null, 'level ' + L));
  ['10', '60'].forEach(L => assert.ok(core.decode('b-' + L + '-' + d + '-1'), 'level ' + L));
  ['0', '3', '9', '12', ''].forEach(g => assert.strictEqual(core.decode('b-60-' + d + '-' + g), null, 'gear ' + g));
});
check('rejects more points than the level has', () => {
  assert.strictEqual(core.decode('b-18-' + digitsOf(base()) + '-1'), null);   // 10 points, level 18 has 9
  assert.ok(core.decode('b-19-' + digitsOf(base()) + '-1'));
});
check('rejects non-strings', () => {
  [null, undefined, 42, {}, []].forEach(v => assert.strictEqual(core.decode(v), null));
});

// ---------------------------------------------------------------- builder helpers
check('canRemove blocks a point that a higher row or prerequisite needs', () => {
  const r = core.empty(); r.ArcaneFocus = 5; r.ArcaneSubtlety = 1;
  assert.strictEqual(core.canRemove(r, 'ArcaneFocus'), false, 'row: Arcane Subtlety needs 5 points below it');
  assert.strictEqual(core.canRemove(r, 'ArcaneSubtlety'), true);
  // prerequisite: Arcane Power needs Presence of Mind. The sim's Arcane build keeps 34 points below row 6, so taking
  // Presence of Mind out would leave 33, still enough for the row: only the prerequisite blocks it.
  const arc = core.fromOrder(core.orderFor({ ArcaneFocus: 5, ImprovedChanneling: 5, ArcaneConcentration: 5, ArcaneGeometry: 2,
    ArcaneImpact: 3, ArcaneBlast: 1, ArcaneMeditation: 3, MissileBarrage: 1, PresenceOfMind: 1, ArcaneMind: 5, ArcaneInstability: 3,
    ArcanePower: 1 }, 0), 60);
  assert.strictEqual(core.canRemove(arc, 'PresenceOfMind'), false, 'prerequisite: Arcane Power needs Presence of Mind');
  assert.strictEqual(core.canRemove(arc, 'ArcanePower'), true);
  assert.strictEqual(core.canRemove(Object.assign({}, arc, { ArcanePower: 0 }), 'PresenceOfMind'), true, 'control: without Arcane Power it comes out');
  assert.strictEqual(core.canRemove(arc, 'ArcaneConcentration'), false, 'prerequisite: Arcane Meditation needs 5 Arcane Concentration');
});
check('expand rejects unknown and prototype names', () => {
  ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'Nope'].forEach(k =>
    assert.throws(() => core.expand([[k, 1]]), /unknown talent/, k));
  assert.deepStrictEqual(core.expand([['IceLance', 1], ['Shatter', 2]]), ['IceLance', 'Shatter', 'Shatter']);
});
check('lockReason explains rows, points and prerequisites', () => {
  const names = DATA.trees;
  assert.match(core.lockReason(core.empty(), 'ArcaneSubtlety', 60, names), /Needs 5 points in Arcane/);
  const r = core.empty(); r.ArcaneFocus = 1;
  assert.match(core.lockReason(r, 'ArcaneFocus', 10, names), /No points left at level 10/);
  const m = core.fromOrder(core.orderFor({ ArcaneFocus: 5, ImprovedChanneling: 5, ArcaneConcentration: 4, ArcaneImpact: 1 }, 0), 60);
  assert.match(core.lockReason(m, 'ArcaneMeditation', 60, names), /Needs 5 in Arcane Concentration/);
});
check('clean clamps and fills foreign data', () => {
  const r = core.clean({ ArcaneFocus: 9, WandSpecialization: -3, ArcaneBlast: '1', Nope: 4, IceLance: 0.6 });
  assert.strictEqual(r.ArcaneFocus, 5); assert.strictEqual(r.WandSpecialization, 0); assert.strictEqual(r.ArcaneBlast, 1);
  assert.strictEqual(r.IceLance, 1); assert.strictEqual(r.Nope, undefined); assert.strictEqual(Object.keys(r).length, 54);
});

// ---------------------------------------------------------------- class data
const iconList = fs.readFileSync(path.join(ROOT, 'assets', 'icons', 'ICONS.txt'), 'utf8').split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'));
const ICON_SET = new Set(iconList);
check('races and storage match CONTRACTS section 5', () => {
  assert.deepStrictEqual(Object.keys(CLASS.races), ['human', 'gnome', 'skyborne', 'orc', 'undead', 'troll']);
  assert.deepStrictEqual(Object.values(CLASS.races).map(r => r.faction), ['Alliance', 'Alliance', 'Alliance', 'Horde', 'Horde', 'Horde']);
  assert.strictEqual(CLASS.storagePrefix, 'fml.');
  assert.ok(CLASS.races[CLASS.defaultRace]);
});
check('every icon the class data names is in ICONS.txt and on disk', () => {
  const named = [CLASS.icon, ...CLASS.treeIcons, ...Object.values(CLASS.talentIcons), ...Object.values(CLASS.spellIcons),
    ...Object.values(CLASS.races).flatMap(r => [r.icon, ...r.racials.map(x => x[2])]), ...CLASS.specCards.map(s => s.icon),
    ...CLASS.planner.phases.flatMap(p => (p.steps || []).map(n => CLASS.spellIcons[n]))];
  named.forEach(n => {
    assert.ok(ICON_SET.has(n), 'not in ICONS.txt: ' + n);
    assert.ok(fs.existsSync(path.join(ROOT, 'assets', 'icons', n + '.jpg')), 'missing file: ' + n);
  });
  assert.deepStrictEqual(Object.keys(CLASS.talentIcons).sort(), T.map(x => x.k).sort());
});
check('planner orders, presets and spec cards are legal at every level', () => {
  const orders = [['planner', CLASS.planner.order]].concat(CLASS.planner.respec ? [['respec', CLASS.planner.respec.order]] : [])
    .concat(CLASS.presets.map(p => ['preset ' + p.id, p.order]));
  orders.forEach(([name, pairs]) => {
    const order = core.expand(pairs);
    assert.ok(order.length <= 51, name + ' has more than 51 points');
    for (let L = 10; L <= 60; L++) assert.ok(core.buildOk(core.fromOrder(order, L), L), name + ' is illegal at level ' + L);
  });
  CLASS.specCards.forEach(s => assert.ok(core.buildOk(core.clean(s.build), 60), 'spec card ' + s.name + ' is illegal'));
});
check('planner phases, gear and ranks are well formed', () => {
  [CLASS.planner.phases, CLASS.planner.gear].forEach(list => {
    assert.ok(list.length && list[0].from === 1, 'first entry must start at level 1');
    list.forEach((p, i) => { if (i) assert.ok(p.from > list[i - 1].from, 'entries must rise'); });
  });
  Object.entries(CLASS.planner.ranks).forEach(([n, s]) => {
    s.levels.forEach((L, i) => { assert.ok(L >= 1 && L <= 60, n); if (i) assert.ok(L > s.levels[i - 1], n + ' levels must rise'); });
    if (s.talent) assert.ok(T.some(x => x.k === s.talent), n + ' names an unknown talent');
  });
});
check('claims and tests have unique, well-formed ids', () => {
  const ids = CLASS.claims.map(c => c.id).concat(CLASS.tests.map(t => t.id));
  assert.strictEqual(new Set(ids).size, ids.length);
  CLASS.claims.forEach(c => { assert.match(c.id, /^c-[a-z0-9-]+$/); assert.ok(['proof', 'test', 'bust', 'known'].includes(c.group), c.id); });
  CLASS.tests.forEach(t => assert.match(t.id, /^t\d+$/));
});
check('no em or en dashes in the class data', () => {
  const s = JSON.stringify(CLASS);
  assert.ok(!s.includes(String.fromCharCode(0x2013)) && !s.includes(String.fromCharCode(0x2014)));
});

// a build that holds talent x at rank 1 with its prerequisite at full ranks, filled to the rows x needs
function fillTo(x) {
  const r = core.empty();
  r[x.req[0]] = x.req[1];
  r[x.k] = 1;
  // put points in the lowest rows of x's tree until the row gating for every taken talent is met
  const tree = T.filter(y => y.t === x.t && y.k !== x.k && y.k !== x.req[0] && !y.req).sort((a, b) => a.r - b.r || a.c - b.c);
  for (const y of tree) {
    if (core.buildOk(r, 60)) break;
    while (r[y.k] < y.m && !core.buildOk(r, 60) && core.spent(r) < 51) r[y.k] += 1;
  }
  if (!core.buildOk(r, 60)) throw new Error('could not build a legal setup for ' + x.k);
  return r;
}

if (failures.length) {
  console.error('FAILED ' + failures.length + ' of ' + (checks + failures.length) + ' check groups:');
  failures.forEach(f => console.error('  ' + f));
  process.exit(1);
}
console.log('All ' + checks + ' builder check groups passed (' + (51 * 20) + ' random round trips, 200 full-build orders).');
