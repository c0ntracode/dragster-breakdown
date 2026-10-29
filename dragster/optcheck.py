"""Replay the optimal move list on the real ROM for all 16 start configurations.

For each Reset timing, search the reduced model for the fastest legal run, feed those inputs to
the ROM in py65, and compare the time the ROM itself computes with the model's prediction.

    python -m dragster.optcheck --rom Dragster.bin
"""
import argparse

from .harness import BLOWN, FINISHED, FLAG, TIME_HI, TIME_LO, TIME_MID, load_rom, start_race
from .model import display_time
from .search import search


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom")
    args = ap.parse_args()
    rom = load_rom(args.rom)

    bad = 0
    for pre in range(16):
        g, cnt0, phase = start_race(rom, pre)
        _, timed, moves = search(cnt0, phase)
        for fire, left in moves:
            g.p0_step(fire, left)
            if g.ram[FINISHED]:
                break
        regs = (g.ram[TIME_HI], g.ram[TIME_MID], g.ram[TIME_LO])
        t = display_time(timed)
        rom_t = int(f"{regs[0]:02x}{regs[1]:02x}")
        ok = g.ram[FINISHED] and rom_t == t and g.ram[FLAG] == 0 and g.ram[BLOWN] == 0
        bad += not ok
        print(f"cnt0={cnt0} phase={phase:2d}: model {t // 100}.{t % 100:02d}, ROM {rom_t // 100}.{rom_t % 100:02d}"
              f"{'' if ok else '  MISMATCH'}")
    print(f"{16 - bad}/16 start configurations agree")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
