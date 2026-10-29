"""How close does each time get to the finish line?

For each start phase, the largest distance reachable after N timed steps, relative to the
finish threshold 0x6100 = 24832 (distance is position*256 + fraction, so 256 = one position
step). Positive means the line is crossed with room to spare.

    python -m dragster.margin
"""
import argparse
from multiprocessing import Pool

from .model import display_time
from .search import max_distance

THRESHOLD = 0x6100
STEPS = (165, 166, 167, 168)


def _job(arg):
    cnt0, phase = arg
    return phase, [max_distance(cnt0, phase, n) - THRESHOLD for n in STEPS]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cnt0", type=int, default=157, choices=(157, 158))
    args = ap.parse_args()
    with Pool(8) as pool:
        rows = sorted(pool.map(_job, [(args.cnt0, p) for p in range(0, 16, 2)]))
    heads = [f"{display_time(n) // 100}.{display_time(n) % 100:02d} ({n})" for n in STEPS]
    print("phase  " + "  ".join(f"{h:>12}" for h in heads))
    for phase, margins in rows:
        print(f"{phase:5d}  " + "  ".join(f"{m:+12d}" for m in margins))


if __name__ == "__main__":
    main()
