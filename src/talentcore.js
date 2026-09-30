// Talent rules and the #b- share link, with no DOM. Used by the page, src/builder.js and tests/builder_test.js.
// A build is an object {talent key: rank}; missing keys mean 0. Every function returns new objects, never mutates.
// Rules (CONTRACTS section 1): points = max(0, level - (firstLevel - 1)); perRow points in a tree unlock each row;
// a prerequisite needs the listed ranks of the named talent (full ranks, the Classic convention, UNVERIFIED for Forever).
// Share link: b-<level>-<one digit per talent, in list order>-<gear digit>. The talent list order is frozen.
(function (root) {
  'use strict';

  const DEFAULTS = { trees: 3, rows: 7, perRow: 5, firstLevel: 10, maxLevel: 60, gears: [1, 2] };

  function checkList(talents, o) {
    const keys = new Set();
    talents.forEach(x => {
      if (keys.has(x.k)) throw new Error('duplicate talent key ' + x.k);
      keys.add(x.k);
      if (!(x.t >= 0 && x.t < o.trees && x.r >= 0 && x.r < o.rows)) throw new Error('talent outside the grid: ' + x.k);
      if (!(Number.isInteger(x.m) && x.m >= 1 && x.m <= 9)) throw new Error('max rank must be 1 to 9 for a one-digit link: ' + x.k);
    });
    talents.forEach(x => { if (x.req && !keys.has(x.req[0])) throw new Error('unknown prerequisite for ' + x.k); });
  }

  function make(talents, opts) {
    const o = Object.assign({}, DEFAULTS, opts || {});
    checkList(talents, o);
    const N = talents.length;
    const byKey = Object.fromEntries(talents.map(x => [x.k, x]));
    const isKey = k => typeof k === 'string' && Object.prototype.hasOwnProperty.call(byKey, k);   // never 'constructor' and the like
    const linkRe = new RegExp('^b-(\\d{1,2})-(\\d{' + N + '})-(\\d)$');

    const points = L => Math.max(0, L - (o.firstLevel - 1));
    const empty = () => Object.fromEntries(talents.map(x => [x.k, 0]));
    const rankOf = (r, k) => (r && r[k]) || 0;
    const spent = r => talents.reduce((a, x) => a + rankOf(r, x.k), 0);
    const treeSpent = (r, t) => talents.reduce((a, x) => a + (x.t === t ? rankOf(r, x.k) : 0), 0);

    function ranksValid(r) {
      return talents.every(x => { const v = rankOf(r, x.k); return Number.isInteger(v) && v >= 0 && v <= x.m; });
    }
    function rowsOk(r) {
      for (let t = 0; t < o.trees; t++) {
        const rows = new Array(o.rows).fill(0);
        talents.forEach(x => { if (x.t === t) rows[x.r] += rankOf(r, x.k); });
        let below = 0;
        for (let i = 0; i < o.rows; i++) {
          if (rows[i] && below < o.perRow * i) return false;
          below += rows[i];
        }
      }
      return true;
    }
    const reqsOk = r => talents.every(x => !rankOf(r, x.k) || !x.req || rankOf(r, x.req[0]) >= x.req[1]);
    const buildOk = (r, L) => ranksValid(r) && spent(r) <= points(L) && rowsOk(r) && reqsOk(r);

    const withStep = (r, k, d) => Object.assign(empty(), r, { [k]: rankOf(r, k) + d });
    const canAdd = (r, k, L) => rankOf(r, k) < byKey[k].m && buildOk(withStep(r, k, 1), L);
    // removing a point is never blocked by the level, only by rows and prerequisites that depend on it
    const canRemove = (r, k) => rankOf(r, k) > 0 && buildOk(withStep(r, k, -1), o.maxLevel);

    function lockReason(r, k, L, treeNames) {
      const x = byKey[k];
      if (rankOf(r, k) >= x.m) return 'Maxed.';
      if (spent(r) >= points(L)) return 'No points left at level ' + L + '.';
      const below = talents.reduce((a, y) => a + (y.t === x.t && y.r < x.r ? rankOf(r, y.k) : 0), 0);
      if (below < o.perRow * x.r) return 'Needs ' + o.perRow * x.r + ' points in ' + treeNames[x.t] + ' first.';
      if (x.req && rankOf(r, x.req[0]) < x.req[1]) return 'Needs ' + x.req[1] + ' in ' + byKey[x.req[0]].n + '.';
      return '';
    }

    // saved or foreign data to a clean build: every key present, integer ranks clamped to 0..max
    function clean(saved) {
      const r = empty();
      if (!saved || typeof saved !== 'object') return r;
      talents.forEach(x => {
        const v = Number(saved[x.k]);
        r[x.k] = Number.isFinite(v) ? Math.min(x.m, Math.max(0, Math.round(v))) : 0;
      });
      return r;
    }
    const compact = r => Object.fromEntries(talents.filter(x => rankOf(r, x.k)).map(x => [x.k, rankOf(r, x.k)]));

    // [[key, points], ...] to one key per point
    function expand(pairs) {
      return pairs.flatMap(([k, c]) => {
        if (!isKey(k)) throw new Error('unknown talent in order: ' + k);
        return Array(c).fill(k);
      });
    }
    // the first points(L) entries of an order (one key per point)
    function fromOrder(order, L) {
      const r = empty();
      order.slice(0, points(L)).forEach(k => { r[k] += 1; });
      return r;
    }
    // a point order that reaches `build` and is legal at every step: the main tree top down, then the other trees
    function orderFor(build, mainTree) {
      const target = clean(build);
      if (!buildOk(target, o.maxLevel)) throw new Error('orderFor: the build is not legal at level ' + o.maxLevel);
      const sorted = talents.slice().sort((a, b) => ((a.t !== mainTree) - (b.t !== mainTree)) || (a.t - b.t) || (a.r - b.r) || (a.c - b.c));
      const order = [];
      let r = empty();
      for (let n = spent(target); n > 0; n--) {
        const next = sorted.find(x => r[x.k] < target[x.k] && buildOk(withStep(r, x.k, 1), o.maxLevel));
        if (!next) throw new Error('orderFor: no legal next point');
        r = withStep(r, next.k, 1);
        order.push(next.k);
      }
      return order;
    }

    function encode(L, r, gear) {
      return 'b-' + L + '-' + talents.map(x => rankOf(r, x.k)).join('') + '-' + gear;
    }
    // a hash without '#', to { level, ranks, gear } or null. Rejects anything that is not exactly a legal build.
    function decode(h) {
      const m = typeof h === 'string' ? h.match(linkRe) : null;
      if (!m) return null;
      const level = Number(m[1]), gear = Number(m[3]);
      if (level < o.firstLevel || level > o.maxLevel || !o.gears.includes(gear)) return null;
      const ranks = empty();
      for (let i = 0; i < N; i++) {
        const d = Number(m[2][i]);
        if (d > talents[i].m) return null;
        ranks[talents[i].k] = d;
      }
      return buildOk(ranks, level) ? { level, ranks, gear } : null;
    }

    return { talents, N, rules: o, points, empty, spent, treeSpent, buildOk, canAdd, canRemove, lockReason,
      clean, compact, expand, fromOrder, orderFor, encode, decode };
  }

  const api = { make };
  if (typeof module !== 'undefined') module.exports = api; else root.TalentCore = api;
})(this);
