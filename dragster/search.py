"""Exact search for the fastest legal Dragster finish.

Layered BFS over player-0 steps. The dynamics never depend on distance (it only feeds the
finish test), so for equal (RPM, gear, clutch, stick bit, speed) the state with the larger
distance dominates and the others can be dropped. That makes the pruning exact: the first
layer in which any state finishes is the true minimum.

The start has two free parameters, set by when Reset is pressed:
  cnt0   countdown after the first player-0 frame (157 or 158)
  phase  frame counter ($81) mod 16 at that frame (0, 2, ..., 14)

    python -m dragster.search                 # all 16 start configurations
    python -m dragster.search --phase 0 --cnt0 158 --moves moves.txt
"""
import argparse
from multiprocessing import Pool

from .model import START, display_time, mstep


def search(cnt0, phase, max_steps=260):
    """Return (finish_step, timed_steps, moves) for the earliest legal finish, or None.

    moves[k] = (fire, left) for player-0 step k, counted from the first player-0 frame
    after Reset. timed_steps counts the steps the clock runs, including the finishing one.
    """
    first_timed = (cnt0 + 1) // 2
    layer = {START[:5]: (0, None, None)}   # key -> (best distance, parent key, move)
    history = []
    for k in range(max_steps):
        frame = (phase + 2 * k) & 0xFF
        cnt = max(0, cnt0 - 2 * k)
        nxt, finishers = {}, []
        for key, (dist, _, _) in layer.items():
            for fire in (0, 1):
                for left in (0, 1):
                    ns, status = mstep(key + (dist,), fire, left, frame, cnt)
                    if status == "fin":
                        finishers.append((key, (fire, left)))
                    elif status == "ok":
                        nkey = ns[:5]
                        old = nxt.get(nkey)
                        if old is None or ns[5] > old[0]:
                            nxt[nkey] = (ns[5], key, (fire, left))
        history.append(layer)
        if finishers:
            key, move = finishers[0]
            moves = [move]
            for j in range(k, 0, -1):
                _, key, mv = history[j][key]
                moves.append(mv)
            return k, k - first_timed + 1, moves[::-1]
        layer = nxt
    return None


def max_distance(cnt0, phase, timed_steps):
    """Largest reachable distance (position*256 + fraction) after `timed_steps` timed steps,
    with the finish line disabled. Compare with 0x6100 = 24832 to see how close a time is."""
    first_timed = (cnt0 + 1) // 2
    layer = {START[:5]: 0}
    for k in range(first_timed + timed_steps):
        frame = (phase + 2 * k) & 0xFF
        cnt = max(0, cnt0 - 2 * k)
        nxt = {}
        for key, dist in layer.items():
            for fire in (0, 1):
                for left in (0, 1):
                    ns, status = mstep(key + (dist,), fire, left, frame, cnt, finish_pos=0x6000)
                    if status == "ok" and nxt.get(ns[:5], -1) < ns[5]:
                        nxt[ns[:5]] = ns[5]
        layer = nxt
    return max(layer.values())


def _search_job(cfg):
    cnt0, phase = cfg
    return cfg, search(cnt0, phase)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cnt0", type=int, choices=(157, 158))
    ap.add_argument("--phase", type=int, choices=range(0, 16, 2))
    ap.add_argument("--moves", help="write the optimal (fire left) moves, one step per line")
    args = ap.parse_args()

    if args.cnt0 is not None and args.phase is not None:
        configs = [(args.cnt0, args.phase)]
    else:
        configs = [(c, p) for c in (157, 158) for p in range(0, 16, 2)]
    with Pool(min(len(configs), 16)) as pool:
        results = pool.map(_search_job, configs)

    best = None
    for (cnt0, phase), res in results:
        step, timed, moves = res
        t = display_time(timed)
        print(f"cnt0={cnt0} phase={phase:2d}: finish at step {step}, {timed} timed steps -> {t // 100}.{t % 100:02d}")
        if best is None or timed < best[0]:
            best = (timed, moves)
    t = display_time(best[0])
    print(f"fastest legal time over these start configurations: {t // 100}.{t % 100:02d} ({best[0]} timed steps)")
    if args.moves:
        with open(args.moves, "w") as f:
            f.writelines(f"{fire} {left}\n" for fire, left in best[1])


if __name__ == "__main__":
    main()
