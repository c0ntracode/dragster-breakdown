#!/usr/bin/env python3
"""Replay the optimal run in MAME (headless) and read the time the game itself reports.

Steps: (1) probe MAME for the start alignment produced by pressing Reset at a chosen frame,
(2) compute the optimal moves for that alignment with the exact search, (3) replay them in
MAME through mame/dr.lua, (4) optionally record video + audio and encode an MP4.

    python mame/replay.py --rom Dragster.bin
    python mame/replay.py --rom Dragster.bin --reset-at 64 --video media/run.mp4
    python mame/replay.py --rom Dragster.bin --snapshot media/final.png

--reset-at N picks the start phase (N mod 16). 64 gives phase 0, the best one.
Requires: mame (with the a2600 driver), and ffmpeg for --video.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dragster.model import display_time  # noqa: E402
from dragster.search import search  # noqa: E402

ENV = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")


def run_mame(rom, extra, env_vars, timeout=180):
    cmd = ["mame", "a2600", "-cart", rom, "-nothrottle", "-autoboot_script",
           os.path.join(HERE, "dr.lua")] + extra
    out = subprocess.run(cmd, env=dict(ENV, **env_vars), capture_output=True, text=True, timeout=timeout)
    return out.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True)
    ap.add_argument("--reset-at", type=int, default=64)
    ap.add_argument("--video", help="write an MP4 (needs ffmpeg)")
    ap.add_argument("--snapshot", help="write a PNG of the final screen")
    args = ap.parse_args()
    rom = os.path.abspath(args.rom)
    if shutil.which("mame") is None:
        raise SystemExit("mame not found in PATH")

    probe = run_mame(rom, ["-video", "none", "-sound", "none", "-seconds_to_run", "60"],
                     {"DR_MODE": "probe", "DR_RESET_AT": str(args.reset_at)})
    m = re.search(r"PROBE cnt0=(\d+) fr0=(\d+) \(phase (\d+)\)", probe)
    if not m:
        raise SystemExit("probe failed:\n" + probe)
    cnt0, phase = int(m.group(1)), int(m.group(3))
    print(f"start alignment: cnt0={cnt0} phase={phase}")

    step, timed, moves = search(cnt0, phase)
    t = display_time(timed)
    print(f"model: finish at step {step}, {timed} timed steps -> {t // 100}.{t % 100:02d}")

    with tempfile.TemporaryDirectory() as tmp:
        movefile = os.path.join(tmp, "moves.txt")
        with open(movefile, "w") as f:
            f.writelines(f"{a} {b}\n" for a, b in moves)
        env = {"DR_MODE": "run", "DR_RESET_AT": str(args.reset_at), "DR_PATH": movefile}
        extra = ["-video", "none", "-sound", "none", "-seconds_to_run", "40"]
        snapdir = None
        if args.snapshot:
            snapdir = os.path.join(tmp, "snap")
            os.makedirs(snapdir)
            env["DR_SNAP"] = "1"
            extra = ["-video", "soft", "-sound", "none", "-skip_gameinfo", "-seconds_to_run", "40",
                     "-snapshot_directory", snapdir]
        if args.video:
            avi, wav = os.path.join(tmp, "run.avi"), os.path.join(tmp, "run.wav")
            env["DR_TAIL"] = "180"
            extra = ["-video", "soft", "-sound", "sdl", "-skip_gameinfo", "-seconds_to_run", "40",
                     "-aviwrite", avi, "-wavwrite", wav]
        out = run_mame(rom, extra, env)
        fin = re.search(r"FINISHED step=(\d+) time_regs=(\w+) pos=(\w+) flag=(\w+) blown=(\w+)", out)
        if not fin:
            raise SystemExit("run did not finish:\n" + out[-500:])
        regs = fin.group(2)
        print(f"MAME: finished at step {fin.group(1)}, time registers {regs[:2]} {regs[2:4]} {regs[4:]} "
              f"-> {int(regs[:2])}.{regs[2:4]}, flag={fin.group(4)}, blown={fin.group(5)}")
        if args.snapshot:
            shots = [os.path.join(r, f) for r, _, fs in os.walk(snapdir) for f in fs if f.endswith(".png")]
            shutil.copy(shots[0], args.snapshot)
            print("snapshot:", args.snapshot)
        if args.video:
            if shutil.which("ffmpeg") is None:
                raise SystemExit("ffmpeg not found; cannot encode --video")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", avi, "-i", wav, "-vf",
                            "scale=880:660:flags=neighbor,format=yuv420p", "-c:v", "libx264", "-crf", "18",
                            "-r", "60", "-c:a", "aac", "-b:a", "128k", "-shortest", args.video], check=True)
            print("video:", args.video)


if __name__ == "__main__":
    main()
