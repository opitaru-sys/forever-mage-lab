"""Does spending mana evenly hold up when potions arrive in lumps? A check of the raid model's one-budget program.

The model gives the whole fight one mana budget. Real income arrives in lumps (potions, runes, gems, Evocation), and
mana cannot be spent before it arrives. This script takes each spec's plan, draws the income ceiling (pool + regen +
items that have arrived), bends the spending line under it (the tightest path: from the end of the opening, the
lowest slope to any point just before a lump, repeated), and solves the same linear program in each window with the
window's mana. If the one-budget program were too optimistic, the windowed total would come out lower.

Run from the repo root: python analysis/raid_windows.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
import raid_model as R  # noqa: E402


def windowed(o, tal):
    res = R.evaluate(o, tal)
    S = R.context(o, tal, res['fv'], res['state'])
    acts, fixed = R.build_actions(S)
    T, regen = S['T'], S['regen_cast']
    items = res['items']
    op = res['opening']
    t0 = op['t'] if op else 0.0
    # the one-budget model books the opening as pure top action and the Scorch upkeep beside it, so the upkeep's
    # time and mana fall in the windows after the opening
    fm = fixed['m'] / (T - t0) if fixed else 0.0
    ft = fixed['t'] / (T - t0) if fixed else 0.0
    evo = next((c for c in res['chosen'] if c['spec']['kind'] == 'evo'), None)
    xe = evo['x'] if evo else 0.0
    lump = -evo['m'] * xe if evo else 0.0
    t_evo = max(R.EVO_LAG, t0)

    def ceiling(t, before=True):
        inc = S['max_mana'] + regen * t + S['state']['eu_mana'] * t / T
        for tm, amt, _ in items:
            if tm < t - 1e-9 or (not before and tm <= t + 1e-9):
                inc += amt
        if xe and t_evo < t - 1e-9:
            inc += lump
        return inc

    s0 = op['m'] if op else 0.0
    pts = [(tm, ceiling(tm)) for tm, _, _ in items if tm > t0 + 1e-9] + [(T, ceiling(T, before=False))]
    path = [(t0, s0)]
    cur = path[0]
    while cur[0] < T - 1e-9:
        best = None
        for p in pts:
            if p[0] <= cur[0] + 1e-9:
                continue
            slope = (p[1] - cur[1]) / (p[0] - cur[0])
            if best is None or slope < best[0] - 1e-12 or (abs(slope - best[0]) < 1e-12 and p[0] > best[1][0]):
                best = (slope, p)
        cur = best[1]
        path.append(cur)
    capped = [a for a in acts if a['cap'] is not None and a['spec'].get('kind') != 'evo']
    unc = [a for a in acts if a['cap'] is None]
    dmg = 0.0
    for (ta, sa), (tb, sb) in zip(path, path[1:]):
        dur = tb - ta
        seg = unc + [dict(a, cap=a['cap'] * dur / (T - t0)) for a in capped]
        v, _ = R.solve_lp(seg, dur * (1 - ft) - R.EVO_TIME * xe * dur / (T - t0), sb - sa - fm * dur)
        dmg += v
    top = R.top_action(acts, res.get('top'))
    dmg += (top['d'] * op['t'] / top['t'] if op else 0.0) + (fixed['d'] if fixed else 0.0)
    extras = sum(v for k, v in res['parts'].items() if k in ('Combustion', 'Racial'))
    return res['total'], dmg / T + extras, len(path) - 1


def main():
    print('| spec | one budget | windows | windows / one budget | windows |')
    print('|---|---|---|---|---|')
    for s in R.SPECS:
        one, win, n = windowed(dict(R.DEFAULTS), s['talents'])
        print('| %s | %.1f | %.1f | %+.2f%% | %d |' % (s['name'], one, win, (win / one - 1) * 100, n))


if __name__ == '__main__':
    main()
