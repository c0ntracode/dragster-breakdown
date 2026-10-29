"""Reduced model of Dragster's player-0 physics, bit-exact against the ROM (see difftest.py).

State is (R, G, cl, d6, V, dist):
  R     engine RPM ($A8); reaching 0x20 blows the engine
  G     gear 0..4 ($CC & 0x7F)
  cl    clutch held (stick-left pressed; bit 7 of $CC). Acts as neutral.
  d6    previous stick-left bit ($D6): 0 = held, 4 = released
  V     speed ($C0)
  dist  position * 256 + fraction ($BA, $C2)

Per step the ROM does, in this order: position, RPM, speed, shift.

Moves are (fire, left). A step is `legal` unless it blows the engine or releases the
shifter before the start countdown ends: the game then draws BLOWN / EARLY in place of
the time, so no time can be read.
"""

MASK = (0x00, 0x00, 0x02, 0x06, 0x0E)   # RPM only changes when (frame & mask[gear]) == 0
INC = (3, 1, 1, 1, 1)                   # RPM change per update, by gear (neutral/clutch = 3)
FINISH_POS = 0x60                       # race ends when position > $60
STEP_TIME = 334                         # 0.0334 s per timed step, in units of 1e-4 s


def target(R, Y):
    """Speed limit for RPM R in effective gear Y >= 1: R rotated left (Y-1) times, with the
    carry from (R >= $14) rotated in first."""
    if Y == 1:
        return R
    c = 1 if R >= 0x14 else 0
    A = R
    for _ in range(Y - 1):
        A = ((A << 1) | c) & 0x1FF
        c = A >> 8
        A &= 0xFF
    return A


def display_time(timed_steps):
    """Time the game shows after `timed_steps` timer increments, as hundredths of a second."""
    return timed_steps * STEP_TIME // 100


def mstep(s, fire, left, frame, cnt_after, finish_pos=FINISH_POS):
    """Advance one player-0 step.

    frame      $81 at the start of the player-0 frame (only its low 4 bits matter)
    cnt_after  start countdown ($8D) after this frame's decrement; 0 once the clock runs
    Returns (new_state, status) with status in 'ok', 'fin', 'blown', 'early'.
    """
    R, G, cl, d6, V, dist = s
    if V:
        dist += V
        if (dist >> 8) > finish_pos:
            return (R, G, cl, d6, V, dist), "fin"
    Y = 0 if cl else G
    if (frame & MASK[Y]) == 0:
        R += INC[Y] if fire else -INC[Y]
        if R < 0:
            R = 0
        if R >= 0x20:
            return None, "blown"
    if Y:
        T = target(R, Y)
        if T > V:
            if T - V >= 0x10:       # engine bogs down when it is far ahead of the wheels
                R -= 1
            V += 2
        elif T < V:
            V -= 1
    new = 0 if left else 4
    if new != d6:
        d6 = new
        if new == 0:
            cl = 1
        else:
            if cnt_after != 0:
                return None, "early"
            G = min(G + 1, 4)
            cl = 0
    return (R, G, cl, d6, V, dist), "ok"


START = (0, 0, 0, 4, 0, 0)
