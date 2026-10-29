"""Differential test: the reduced model against the real ROM, step by step.

Plays random but legal inputs (the model vetoes moves that would blow the engine or shift
early, so runs go the whole distance) and compares RPM, gear, clutch, stick bit, speed and
distance after every step. At a finish it also checks the time registers.

    python -m dragster.difftest --rom Dragster.bin --trials 60
"""
import argparse
import random

from .harness import (CNT, FINISHED, FLAG, FRAME, GEAR, POS, FRAC, RPM, SPEED, STICK_PREV,
                      TIME_HI, TIME_MID, load_rom, start_race)
from .model import START, display_time, mstep


def time_registers(ram):
    """Hundredths of a second shown by the BCD registers $B3/$B5."""
    return ((ram[TIME_HI] >> 4) * 1000 + (ram[TIME_HI] & 15) * 100
            + (ram[TIME_MID] >> 4) * 10 + (ram[TIME_MID] & 15))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--steps", type=int, default=400, help="max steps per trial")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rom = load_rom(args.rom)
    random.seed(args.seed)

    compared = finishes = bad = 0
    for trial in range(args.trials):
        g, cnt0, phase = start_race(rom, random.randrange(16))
        ram = g.ram
        frame0 = ram[FRAME]
        state, timed = START, 0
        for k in range(args.steps):
            cnt = max(0, cnt0 - 2 * k)
            frame = (frame0 + 2 * k) & 0xFF
            legal = [(f, l) for f in (0, 1) for l in (0, 1)
                     if mstep(state, f, l, frame, cnt)[1] in ("ok", "fin")]
            if not legal:
                break
            weights = [(3 if f else 1) * (2 if (l and cnt == 0) or not l else 1) for f, l in legal]
            fire, left = random.choices(legal, weights)[0]
            new, status = mstep(state, fire, left, frame, cnt)
            g.p0_step(fire, left)
            timed += cnt == 0
            compared += 1
            rom_state = (ram[RPM], ram[GEAR] & 0x7F, ram[GEAR] >> 7, ram[STICK_PREV],
                         ram[SPEED], ram[POS] * 256 + ram[FRAC])
            if status == "fin":
                finishes += 1
                ok = (ram[FINISHED] and rom_state[4:] == new[4:]
                      and time_registers(ram) == display_time(timed) and ram[FLAG] == 0)
                if not ok:
                    bad += 1
                    print(f"FINISH MISMATCH trial {trial} step {k}: rom {rom_state} model {new} "
                          f"time {time_registers(ram)} vs {display_time(timed)}")
                break
            if rom_state != new:
                bad += 1
                print(f"MISMATCH trial {trial} step {k} fire={fire} left={left}: rom {rom_state} model {new}")
                break
            state = new
    print(f"{compared} steps compared over {args.trials} trials, {finishes} finishes, {bad} mismatches")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
