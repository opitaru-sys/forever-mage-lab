"""Talent orders for the page planner, levels 10 to 60, found by search (the Warlock lab's analysis/planner_order.py
method), plus the tree-first orders the Frost / Fire / Arcane comparison uses.

Run from the repo root:
    python analysis/leveling_planner.py            the three tree-first orders, then the planner order (any tree)
    python analysis/leveling_planner.py frost      one variant only: frost, fire, arcane or all

Objective: mean seconds per kill over levels 10 to 60, each level using the first (level - 9) points of the order,
gear 1, no race, every model option at its default (the Warlock lab's objective; analysis/leveling_paths.py also
reports time-weighted hours). Scored with the default evaluate(), the search the builder uses, averaged over mob
health 0.9, 1.0 and 1.1 (the page's HP_MULTS); a level where every rotation is infeasible counts 1000 s extra.
Method:
1. Greedy fill: each step adds the single point, or the cheapest package of points that unlocks a talent (a row's
   five points, a prerequisite), with the best gain per point over the levels it covers. A tree-first variant only
   considers its own tree until that tree has no scored talent left to take.
2. Moves: one point, or a run of the same talent, moved up to 6 places earlier or later, while the mean improves
   (every move keeps the order legal at every level). Moves start from the greedy order and from seed orders (the
   orders in analysis/leveling_paths.py, and for the planner the three tree-first orders just found), and the best
   result is kept: a greedy fill alone starts in Arcane, because the wand wins at levels 10 to 19, and cannot recover.
3. Swaps: one point from the 16th on replaced by another scored talent (a tree-first order only takes talents of
   its own tree), each swap followed by more moves. Greedy and swaps take a talent the score cannot see only when
   no scored talent fits, so a row is never filled with dead points while a live one is open.
Prints every order as a Python list for analysis/leveling_paths.py and a legality check.
"""
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))

from character import valid, evaluate, TALENTS, BY_KEY, KEYS, HP_MULTS, SCORED   # noqa: E402

LEVELS = list(range(10, 61))
TREE = {'arcane': 0, 'fire': 1, 'frost': 2}
TREE_OF = {t['k']: t['t'] for t in TALENTS}
ROW_OF = {t['k']: t['r'] for t in TALENTS}
MAXR = {t['k']: t['m'] for t in TALENTS}
INFEASIBLE = 1000.0


def counts(order):
    t = {}
    for k in order:
        t[k] = t.get(k, 0) + 1
    return t


def addable(t, k):
    return t.get(k, 0) < MAXR[k] and valid(dict(t, **{k: t.get(k, 0) + 1}))


def legal(order):
    """Every prefix of the order is a legal build (the planner shows every level)."""
    t = {}
    for k in order:
        t[k] = t.get(k, 0) + 1
        if not valid(t):
            return False
    return True


def rep_format(order):
    runs = []
    for k in order:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    return 'rep(' + ', '.join("('%s', %d)" % (k, n) for k, n in runs) + ')'


# ---------------------------------------------------------------- cached, pooled scoring
def score_job(args):
    L, items = args
    n, r = evaluate(L, dict(items), 1, hp_mults=HP_MULTS)
    return r['spk'] + (0.0 if r['feasible'] else INFEASIBLE)


class Scorer:
    def __init__(self, pool):
        self.pool, self.cache = pool, {}

    @staticmethod
    def key(L, t):
        return (L, tuple(sorted((k, v) for k, v in t.items() if v)))

    def run(self, pairs):
        keys = [self.key(L, t) for L, t in pairs]
        todo = sorted({k for k in keys if k not in self.cache})
        if todo:
            res = self.pool.map(score_job, todo, chunksize=2)
            self.cache.update(zip(todo, res))
        return [self.cache[k] for k in keys]

    def levels(self, order):
        return self.run([(L, counts(order[:L - 9])) for L in LEVELS])

    def mean(self, order):
        v = self.levels(order)
        return sum(v) / len(v)


# ---------------------------------------------------------------- greedy fill
def unlock(t, k, pref, left, allowed):
    """The package of points that makes talent k addable (its tree's lower rows, filled with the points that gain
    most, or its prerequisite), ending with k; None if it needs more than `left` points or is out of reach."""
    t, pack = dict(t), []
    while not addable(t, k):
        if len(pack) >= left or t.get(k, 0) >= MAXR[k]:
            return None
        req = BY_KEY[k]['req']
        if req and t.get(req[0], 0) < req[1]:
            if not addable(t, req[0]) or req[0] not in allowed:
                return None
            c = req[0]
        else:
            cands = [c for c in allowed if TREE_OF[c] == TREE_OF[k] and ROW_OF[c] < ROW_OF[k] and addable(t, c)]
            if not cands:
                return None
            c = max(cands, key=lambda x: (x in SCORED, pref.get(x, 0.0)))   # a talent the score sees fills first
        pack.append(c)
        t[c] = t.get(c, 0) + 1
    pack.append(k)
    return pack if len(pack) <= left else None


def greedy(sc, tree=None, n=51):
    order = []
    while len(order) < n:
        t, L, left = counts(order), len(order) + 10, n - len(order)
        allowed = [k for k in KEYS if tree is None or TREE_OF[k] == tree]
        live = [k for k in allowed if k in SCORED]
        if tree is not None and not any(addable(t, k) for k in live) and not any(
                unlock(t, k, {}, left, allowed) for k in live):
            allowed = list(KEYS)            # nothing the score sees is left in the tree: spill into the others
        singles = [k for k in allowed if addable(t, k)]
        if any(k in SCORED for k in singles):     # a point the score cannot see only when nothing else fits
            singles = [k for k in singles if k in SCORED]
        base = sc.run([(L, t)])[0]
        gains = sc.run([(L, counts(order + [k])) for k in singles])
        pref = {k: base - g for k, g in zip(singles, gains)}
        packs = []
        for k in allowed:
            if k in SCORED and not addable(t, k):
                p = unlock(t, k, pref, left, allowed)
                if p and tuple(p) not in packs and len(p) > 1:
                    packs.append(tuple(p))
        scored = [(pref[k], (k,)) for k in singles]
        for p in packs:
            lv = [L + i for i in range(len(p))]
            before = sc.run([(x, t) for x in lv])
            after = sc.run([(x, counts(order + list(p[:i + 1]))) for i, x in enumerate(lv)])
            scored.append((sum(b - a for b, a in zip(before, after)) / len(p), p))
        gain, pick = max(scored, key=lambda s: s[0])
        order += list(pick[:left])
    return order


# ---------------------------------------------------------------- polish: move points or runs
def runs_of(order):
    out, i = [], 0
    while i < len(order):
        j = i
        while j < len(order) and order[j] == order[i]:
            j += 1
        out.append((i, j))
        i = j
    return out


def candidates(order, reach=6):
    seen, out = set(), []
    for i, j in runs_of(order):
        for a, b in ((i, j), (i, i + 1), (j - 1, j)):
            block, rest = order[a:b], order[:a] + order[b:]
            for pos in range(max(0, a - reach), min(len(rest), a + reach) + 1):
                new = rest[:pos] + block + rest[pos:]
                key = tuple(new)
                if new != order and key not in seen and legal(new):
                    seen.add(key)
                    out.append(new)
    return out


def polish(sc, order, rounds=20, log=None):
    cur = sc.mean(order)
    for r in range(rounds):
        cands = candidates(order)
        sc.run([(L, counts(o[:L - 9])) for o in cands for L in LEVELS])
        best = min(cands, key=sc.mean)
        val = sc.mean(best)
        if log:
            log(f'  move round {r + 1}: {len(cands)} candidates, mean {cur:.3f} -> {min(val, cur):.3f}')
        if val >= cur - 1e-6:
            break
        order, cur = best, val
    return order


def substitutes(order, start, allowed=None):
    out = []
    for p in range(start, len(order)):
        for b in (allowed or SCORED):
            if b != order[p]:
                new = order[:p] + [b] + order[p + 1:]
                if legal(new):
                    out.append(new)
    return out


def improve(sc, order, start=15, rounds=4, log=None, allowed=None):
    cur = sc.mean(order)
    for r in range(rounds):
        cands = substitutes(order, start, allowed)
        if not cands:
            break
        sc.run([(L, counts(o[:L - 9])) for o in cands for L in LEVELS if L - 9 > start])
        best = min(cands, key=sc.mean)
        if log:
            log(f'  swap round {r + 1}: {len(cands)} candidates, mean {cur:.3f} -> {min(sc.mean(best), cur):.3f}')
        if sc.mean(best) >= cur - 1e-6:
            break
        order = polish(sc, best, rounds=4, log=log)
        cur = sc.mean(order)
    return order


def search(sc, variant, log, seeds=()):
    """Greedy fill, then moves from the greedy order and from every seed order, keeping the best; then swaps for
    the 'all' variant."""
    tree = None if variant == 'all' else TREE[variant]
    t0 = time.time()
    order = greedy(sc, tree)
    log(f'{variant}: greedy mean {sc.mean(order):.3f} ({time.time() - t0:.0f} s)')
    starts = [order] + [list(s) for s in seeds if legal(list(s)) and len(s) >= 51]
    polished = []
    for i, s in enumerate(starts):
        s = list(s[:51])
        log(f'{variant}: start {i} ({"greedy" if i == 0 else "seed"}) mean {sc.mean(s):.3f}')
        polished.append(polish(sc, s, log=log))
    order = min(polished, key=sc.mean)
    log(f'{variant}: after moves {sc.mean(order):.3f}, best of {len(starts)} starts ({time.time() - t0:.0f} s)')
    allowed = None if tree is None else [k for k in SCORED if TREE_OF[k] == tree]
    order = improve(sc, order, log=log, allowed=allowed)
    log(f'{variant}: after swaps {sc.mean(order):.3f} ({time.time() - t0:.0f} s)')
    assert legal(order) and len(order) == 51
    return order


def main():
    """Tree-first orders first (seeded with analysis/leveling_paths.py's current orders), then the planner order,
    seeded with all of them."""
    import io
    import contextlib
    sys.path.insert(0, HERE)
    with contextlib.redirect_stdout(io.StringIO()):
        from leveling_paths import ORDERS
    variants = sys.argv[1:] or ['frost', 'fire', 'arcane', 'all']

    def log(s):
        print(s, flush=True)
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        sc = Scorer(pool)
        found = {}
        for v in variants:
            if v == 'all':
                seeds = [found[x] for x in ('frost', 'fire', 'arcane') if x in found] + [ORDERS['planner']]
            else:
                seeds = [ORDERS[v]]
            found[v] = search(sc, v, log, seeds)
        print('\n### Orders found (paste into analysis/leveling_paths.py)\n')
        for v, order in found.items():
            print(f'{("PLANNER" if v == "all" else v.upper())} = {rep_format(order)}')
            print(f'# legal at every level: {legal(order)}; mean seconds per kill 10 to 60: {sc.mean(order):.3f}\n')
        print('### Seconds per kill by level\n')
        print('| L | ' + ' | '.join(found) + ' |')
        print('|---|' + '---|' * len(found))
        vals = {v: sc.levels(o) for v, o in found.items()}
        for i, L in enumerate(LEVELS):
            print(f'| {L} | ' + ' | '.join(f'{vals[v][i]:.2f}' for v in found) + ' |')


if __name__ == '__main__':
    main()
