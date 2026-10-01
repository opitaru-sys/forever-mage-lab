"""Does evaluate() find the fastest rotation? It is compared with an exhaustive search on a grid of builds.

Run from the repo root: python analysis/leveling_search_check.py      (a few minutes on 16 cores)
Exhaustive: every base rotation the build can cast x every combination of the modifier groups (each off or one of
its options) x every allowed rank of the main spell, the same space evaluate() searches with its heuristic (a probe
per base, then single-group changes from the best six and two-group changes from the best two). Grid: the four
orders of analysis/leveling_paths.py at every third level from 10 to 58 and at 60, gear 1 and 2, plus option cases
and races. Reports
the largest gap (evaluate's seconds per kill over the exhaustive best) and every case over 0.1%.
"""
import io
import os
import sys
import contextlib
import itertools
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
sys.path.insert(0, HERE)

import character as C   # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from leveling_paths import build, ORDERS   # noqa: E402


def exhaustive(L, tal, gear=1, race='none', **o):
    def ch_fn():
        return C.make_char(L, tal, gear, race, **o)
    ch0 = ch_fn()
    groups = C.mod_groups(L, tal, ch0)
    best, seen = None, set()
    for name, pol in C.POLICIES.items():
        sig = C.usable_steps(pol, ch0)
        if sig is None or sig in seen:
            continue
        seen.add(sig)
        gs = groups + ([C.rank_group(L, pol, ch0)] if C.rank_group(L, pol, ch0) else [])
        for choice in itertools.product(*[[None] + list(range(len(g))) for g in gs]):
            p, n = C.compose(pol, name, gs, list(choice))
            r = C.run_policy(ch_fn, L, p, C.HP_MULTS, C.TRAVEL)
            if best is None or C.better(r, best[1]):
                best = (n, r)
    return best


def job(a):
    L, bname, gear, race, o = a
    tal = build(ORDERS[bname], L - 9)
    n, r = C.evaluate(L, tal, gear, race, **o)
    n2, r2 = exhaustive(L, tal, gear, race, **o)
    return dict(L=L, b=bname, gear=gear, race=race, o=o, name=n, spk=r['spk'], ex_name=n2, ex_spk=r2['spk'],
                feas=r['feasible'], ex_feas=r2['feasible'], gap=100 * (r['spk'] / r2['spk'] - 1))


def cases():
    out = []
    for L in list(range(10, 60, 3)) + [60]:
        for b in ORDERS:
            for gear in (1, 2):
                out.append((L, b, gear, 'none', {}))
    for L in (20, 34, 46, 58):
        for b in ('planner', 'fire', 'arcane'):
            for o in (dict(low_ranks='full'), dict(fb_break=0.0), dict(kite=False), dict(mob_dps_mult=1.5)):
                out.append((L, b, 1, 'none', o))
        for race in ('orc', 'troll', 'gnome', 'undead', 'skyborne'):
            out.append((L, 'planner', 1, race, {}))
    return out


def main():
    cs = cases()
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        res = pool.map(job, cs, chunksize=1)
    worst = max(res, key=lambda x: x['gap'])
    wrong_feas = [x for x in res if x['feas'] != x['ex_feas']]
    print(f'{len(res)} cases; largest gap {worst["gap"]:.3f}% ({worst["L"]} {worst["b"]} gear {worst["gear"]} '
          f'{worst["race"]} {worst["o"]}: {worst["name"]} {worst["spk"]:.3f} vs {worst["ex_name"]} {worst["ex_spk"]:.3f})')
    print(f'cases where evaluate is feasible and the exhaustive best is not, or the reverse: {len(wrong_feas)}')
    over = sorted([x for x in res if x['gap'] > 0.1], key=lambda x: -x['gap'])
    print(f'cases over 0.1%: {len(over)}')
    for x in over:
        print(f"  {x['gap']:.2f}%  L{x['L']} {x['b']} gear {x['gear']} {x['race']} {x['o']}: {x['name']} "
              f"{x['spk']:.2f} vs {x['ex_name']} {x['ex_spk']:.2f}")


if __name__ == '__main__':
    main()
