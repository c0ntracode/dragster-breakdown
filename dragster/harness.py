"""Run the real Dragster ROM in py65 with just enough 2600 hardware to drive the game logic.

The display kernel is cycle-counted, but the game *state* depends only on RAM and three
input ports, so we stub the hardware instead of emulating the TIA:

  * RAM        $80-$FF
  * SWCHA      $0280  joystick (P0 = high nibble, active low; left = bit 6)
  * SWCHB      $0282  console switches (bit 0 = Reset, bit 1 = Select, active low)
  * INTIM      $0284  always reads 0, so the game's timer waits fall through
  * INPT4/5    $0C/$0D fire buttons (bit 7 clear = pressed)

One call to `Game.frame()` runs one game frame, from the start of the display kernel
(`$F016`) to the next one. The game services ONE player per frame (X = $81 & 1), so a
"step" for player 0 is two frames.
"""
import hashlib
import os
import sys

from py65.devices.mpu6502 import MPU

KNOWN_ROMS = {
    "944c52de85464070a946813b050518977750e939": "NTSC",
    "2fdad16a60cd3a49d3bdfb301b3590f2aaa71da3": "PAL",
}
FRAME_START = 0xF016
RESET_VECTOR = 0xF000

# RAM map (zero-page addresses) used by the analysis
FRAME, CNT, RNG = 0x81, 0x8D, 0x82      # frame counter, start countdown, RNG
RPM, SPEED, FRAC, POS = 0xA8, 0xC0, 0xC2, 0xBA
GEAR, STICK_PREV = 0xCC, 0xD6
BLOWN, FLAG = 0xCE, 0xD4                # FLAG: 1 = "BLOWN", $1D = "EARLY" shown instead of the time
FINISHED = 0xD2
TIME_HI, TIME_MID, TIME_LO = 0xB3, 0xB5, 0xB7  # BCD, 0.0334 s added per player-0 step


def load_rom(path=None):
    """Load the 2 KB ROM. Looks at `path`, $DRAGSTER_ROM, then ./Dragster.bin.

    The ROM is copyrighted and is not distributed with this project. A SHA-1 outside
    KNOWN_ROMS only prints a warning: the model was validated against those two dumps.
    """
    path = path or os.environ.get("DRAGSTER_ROM") or "Dragster.bin"
    with open(path, "rb") as f:
        rom = f.read()
    if len(rom) != 2048:
        raise SystemExit(f"{path}: expected a 2048-byte ROM, got {len(rom)} bytes")
    sha1 = hashlib.sha1(rom).hexdigest()
    if sha1 not in KNOWN_ROMS:
        print(f"warning: ROM SHA-1 {sha1} is not a validated dump ({', '.join(KNOWN_ROMS.values())}); "
              "results may not apply to it", file=sys.stderr)
    return rom


class Mem:
    """64K address space with only the hardware listed in the module docstring."""

    def __init__(self, rom):
        self.rom = rom
        self.ram = bytearray(256)
        self.swcha = 0xFF
        self.swchb = 0x3F
        self.fire = [0x80, 0x80]

    def __getitem__(self, a):
        a &= 0x1FFF
        if a >= 0x1000:
            return self.rom[a & 0x7FF]
        if a & 0x280 == 0x280:
            r = a & 0x1F
            return {0: self.swcha, 2: self.swchb}.get(r, 0)
        if a & 0x80:
            return self.ram[a & 0xFF] if a & 0x200 == 0 else 0
        r = a & 0xF
        if r == 0xC:
            return self.fire[0]
        if r == 0xD:
            return self.fire[1]
        return 0

    def __setitem__(self, a, v):
        a &= 0x1FFF
        if a >= 0x1000 or a & 0x280 == 0x280:
            return
        if a & 0x80 and a & 0x200 == 0:
            self.ram[a & 0xFF] = v & 0xFF

    def __len__(self):
        return 0x10000


class Game:
    def __init__(self, rom):
        self.mem = Mem(rom)
        self.ram = self.mem.ram
        self.cpu = MPU(memory=self.mem)
        self.cpu.memory = self.mem
        self.cpu.pc = RESET_VECTOR
        self.cpu.sp = 0xFF

    def run_to(self, pc, max_instr=200000):
        c = self.cpu
        n = 0
        while c.pc != pc or n == 0:
            c.step()
            n += 1
            if n > max_instr:
                raise RuntimeError("runaway at pc=%04x" % c.pc)

    def frame(self):
        self.run_to(FRAME_START)

    def p0_step(self, fire, left):
        """One player-0 step: a player-0 frame with the given inputs, then a player-1 frame."""
        self.mem.fire[0] = 0x00 if fire else 0x80
        self.mem.swcha = 0xFF & ~(0x40 if left else 0)
        self.frame()
        self.mem.fire[0] = 0x80
        self.mem.swcha = 0xFF
        self.frame()


def start_race(rom, pre_frames=0):
    """Boot, idle `pre_frames` extra frames, press Reset, and align to the next player-0 frame.

    `pre_frames` moves the frame counter, so 0..15 covers every start phase.
    Returns (game, cnt0, phase): the countdown value after player-0 step 0's frame, and
    `$81 & 15` at the start of that frame. Those two numbers fully describe the start.
    """
    g = Game(rom)
    g.run_to(FRAME_START)
    for _ in range(2 + pre_frames):
        g.frame()
    g.mem.swchb = 0x3E          # Reset pressed for one frame
    g.frame()
    g.mem.swchb = 0x3F
    while g.ram[FRAME] & 1:
        g.frame()
    return g, g.ram[CNT] - 1, g.ram[FRAME] & 0xF
