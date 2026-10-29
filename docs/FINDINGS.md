# Findings: how Dragster's timing and physics work

Everything here was read from the ROM's behavior (addresses are the game's zero-page RAM and `$F000`-mapped code).
No ROM bytes or disassembly are reproduced.

## Frame structure

- The game services **one player per frame**: `X = $81 & 1`, where `$81` is the frame counter. Player 0 runs on frames
  where `$81` is even before the game increments it, so each player steps at 30 Hz. In this project a *step* means one
  player-0 frame (plus the player-1 frame after it).
- Logic runs after the display kernel, in vertical blank. Inputs are read once per frame
  (SWCHA `$0280`, SWCHB `$0282`, fire via `$0C`/`$0D`).
- Reset runs the init routine, which loads the start countdown `$8D = $9F` and seeds the RNG `$82`.
  The countdown drops by 1 **per frame** (not per step) and the clock starts when it reaches 0.

## The timer

- Each player step with `$8D == 0` and the finish flag `$D2 == 0` adds BCD `0x000334` to `$B3/$B5/$B7`.
  That is **0.0334 s per step**. The display shows the top four digits, truncated.
- Steps → time: 165 → 5.51, 166 → 5.54, 167 → 5.57, 168 → 5.61.
- The finishing step is counted (the add happens before the finish test).
- The finish test is `position > $60`, checked on every step where speed is non-zero.

## Physics (per player-0 step, in the order the ROM does it)

1. **Position.** `fraction += speed`; a carry increments position. Position is *not* gated by the start countdown.
2. **RPM** (`$A8`). Only updated when `($81 & mask[gear]) == 0`, with masks `00 00 02 06 0E` for gears 0..4
   (every step, every step, every 2nd, 4th, 8th). Fire pressed: `+= inc[gear]`; released: `-= inc[gear]` (clamped at 0).
   `inc = 3,1,1,1,1` (neutral and clutch-held count as gear 0). RPM ≥ `$20` blows the engine.
3. **Speed** (`$C0`), for effective gear ≥ 1 (clutch held = neutral = speed unchanged). The limit is RPM rotated left
   `(gear − 1)` times, with the carry from `RPM ≥ $14` rotated in first. Speed moves **+2 per step** toward a higher limit
   and **−1 per step** toward a lower one. If the limit is at least `$10` above speed, RPM drops by 1 that step.
4. **Shifting.** Stick-left is `SWCHA` bit 6 for player 0. Pressing sets the clutch (bit 7 of `$CC`); *releasing* adds one
   gear (cap 4). Neutral is gear 0, the gear after Reset.

The speed ramp is the real bottleneck: speed can rise at most 2 per step, and shifting up with RPM held high doubles the
limit instantly. Optimal play keeps RPM just under the blow-up point while shifting on a ~2-step cadence.

## Legality: BLOWN and EARLY

`$D4` selects an image drawn in place of the time digits (`$F53B` routine, table of 7-row × 32-pixel images):

| `$D4` | Image | Set when |
|---|---|---|
| `$01` | `BLOWN` | RPM reaches `$20` |
| `$1D` | `EARLY` | stick released (gear-up) while the countdown is non-zero |
| `$39` | title logo | (not a game state) |

Nothing in the game logic clears `$D4`, so a run that shows either word never displays a time.

Consequence: **the car cannot legally move before the clock starts.** Speed needs gear ≥ 1, a gear needs a stick release,
and a release before the countdown ends sets EARLY. A greedy policy that rolls before the start "finishes" in 4.27 s but shows `EARLY`.
The only legal pre-start actions are revving in neutral (`+3` per step, up to `$1E`) and holding the clutch.

## Start phase

Reset can be pressed at any frame, which sets two free parameters of the start:

- `cnt0`: the countdown after player 0's first frame (157 or 158; both behave the same)
- `phase`: `$81 mod 16` at that frame, any even value 0..14. Only bits 1..3 matter (the RPM masks).

The best phases (0, 14, 2, 4, 6, 8) reach 5.57; phases 10 and 12 need 168 steps (5.61). The best phase has the largest margin.

Margins (distance units; 24 832 = finish) after N timed steps, for each phase:

| phase | 165 | 166 | 167 |
|---:|---:|---:|---:|
| 0 | −408 | −155 | **+98** |
| 14 | −415 | −162 | +91 |
| 2 | −425 | −172 | +81 |
| 8 | −460 | −207 | +46 |
| 6 | −477 | −224 | +29 |
| 4 | −492 | −239 | +14 |
| 12 | −530 | −277 | −24 |
| 10 | −539 | −286 | −33 |

Regenerate with `python -m dragster.margin`.

## Not modeled

- Odd game numbers (`$80 & 1`) add a tilt mechanic (stick up/down, `$AB`/`$CA`) that, from reading the code, only halves RPM gain.
- Player 1's lane: argued symmetric (same code, `$81` odd), not tested.
- The cycle-exact display kernel. It does not affect game state.

## MAME pitfalls (if you adapt `mame/dr.lua`)

- Keep tap handles in a **global**. As locals they are garbage-collected and the taps silently stop after a few hundred frames.
- `-video soft` needs `-skip_gameinfo`, or MAME blocks on a startup screen waiting for a keypress.
- Headless: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`. A harmless `load_dat` plugin error prints at startup.
- A memory tap's return value replaces the value the CPU reads. The game reads SWCHA after incrementing `$81`, so `$81` is
  **odd** on player 0's frames.
