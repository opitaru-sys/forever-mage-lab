"""Would a time-weighted objective change the planner order? A local check, not a new search.

Run from the repo root: python analysis/leveling_hours_check.py
analysis/leveling_planner.py optimizes the mean seconds per kill over levels 10 to 60 (every level counts the same).
The headline numbers are time-weighted hours (analysis/leveling_paths.py: the Classic XP table, 45 + 5L XP a mob,
ASSUMPTION), which weight the high levels more. This script scores orders in hours instead and runs the planner's
own neighbourhood from the PLANNER order: move rounds (a point or a run moved up to 6 places) and one swap round
(any point from the 16th replaced by another scored talent, then moves). If nothing improves the hours, the order is
also a local optimum for the time-weighted objective; if something does, it prints the gain and the changed order.
"""
import io
import os
import sys
import time
import contextlib
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'models'))

import leveling_planner as lpl                      # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from leveling_paths import PLANNER, kills       # noqa: E402

WEIGHTS = [kills(L) for L in lpl.LEVELS]


class HoursScorer(lpl.Scorer):
    """The planner's Scorer with mean() replaced by time-weighted hours over levels 10 to 60."""

    def mean(self, order):
        return sum(w * s for w, s in zip(WEIGHTS, self.levels(order))) / 3600


def main():
    t0 = time.time()
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        sc = HoursScorer(pool)
        start = sc.mean(PLANNER)
        print(f'PLANNER: {start:.3f} h (level mean {lpl.Scorer.mean(sc, PLANNER):.3f} s per kill)')
        moved = lpl.polish(sc, list(PLANNER), rounds=20, log=print)
        swapped = lpl.improve(sc, moved, start=15, rounds=1, log=print)
        end = sc.mean(swapped)
        print(f'after moves and one swap round: {end:.3f} h ({100 * (end / start - 1):+.2f}%), '
              f'level mean {lpl.Scorer.mean(sc, swapped):.3f} s per kill ({time.time() - t0:.0f} s)')
        if swapped != list(PLANNER):
            d = next(i for i, (a, b) in enumerate(zip(PLANNER, swapped)) if a != b)
            print(f'first change at level {d + 10}: {PLANNER[d]} -> {swapped[d]}')
            print(lpl.rep_format(swapped))
        else:
            print('no move or swap improves the hours: the order is a local optimum for time-weighting too')


if __name__ == '__main__':
    main()
