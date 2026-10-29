-- Drive Dragster in MAME with scripted player-0 inputs, using memory read taps.
--
-- The taps return the value the game reads from SWCHA ($0280), SWCHB ($0282) and INPT4/5
-- ($0C/$0D), so inputs land on exactly the frames the game samples them.
--
-- Environment:
--   DR_MODE      "probe" (print the start alignment and exit) or "run"
--   DR_RESET_AT  press Reset at the Nth SWCHA read (moves the start phase; N mod 16 = phase)
--   DR_PATH      file of "fire left" lines, one per player-0 step      (run mode)
--   DR_TAIL      frames to keep running after the finish (default 30)
--   DR_SNAP      if set, save a snapshot at the end
--   DR_DEBUG     if set, print one line of state per player-0 step
local m = manager.machine
local cpu = m.devices[":maincpu"]
local sp = cpu.spaces["program"]
local mode = os.getenv("DR_MODE") or "probe"
local reset_at = tonumber(os.getenv("DR_RESET_AT") or "64")
local tail = tonumber(os.getenv("DR_TAIL") or "30")

local path = {}
local pathfile = os.getenv("DR_PATH")
if pathfile then
  for line in io.lines(pathfile) do
    local f, l = line:match("(%d)%s+(%d)")
    if f then path[#path + 1] = {tonumber(f), tonumber(l)} end
  end
end

local function ram(a) return sp:read_u8(a) end

local reads, k = 0, -1          -- SWCHA reads so far; current player-0 step
local want_reset, reset_done = false, false
local fire, left = 0, 0
local finish_at

-- The game reads SWCHA once per frame, after it has incremented $81. $81 is therefore odd
-- on player 0's frames. Count those as steps and hand out that step's inputs.
-- NOTE: the tap handles live in a global on purpose. As locals, Lua's garbage collector
-- collects them and silently uninstalls the taps after a few hundred frames.
taps = {}
taps[#taps + 1] = sp:install_read_tap(0x280, 0x280, "swcha", function(off, data, mask)
  reads = reads + 1
  if reads == reset_at then want_reset = true end
  if reset_done and ram(0x81) % 2 == 1 then
    k = k + 1
    if k == 0 then
      print(string.format("PROBE cnt0=%d fr0=%d (phase %d)", ram(0x8d) - 1, ram(0x81) - 1, (ram(0x81) - 1) & 15))
    end
    local mv = path[k + 1]
    fire, left = 0, 0
    if mv then fire, left = mv[1], mv[2] end
    return (left == 1) and 0xBF or 0xFF
  end
  return 0xFF
end)

taps[#taps + 1] = sp:install_read_tap(0x282, 0x282, "swchb", function(off, data, mask)
  if want_reset then want_reset = false; reset_done = true; return 0x3E end   -- Reset held for one read
  return 0x3F
end)

-- INPT4 ($0C) is player 0's fire button, read on player 0's frames only.
taps[#taps + 1] = sp:install_read_tap(0x0C, 0x0D, "inpt", function(off, data, mask)
  if off == 0x0C and reset_done and ram(0x81) % 2 == 1 then
    return (fire == 1) and 0x00 or 0x80
  end
  return 0x80
end)

local frames, last_k = 0, -2
emu.register_frame_done(function()
  frames = frames + 1
  if mode == "probe" and k >= 3 then m:exit() end
  if os.getenv("DR_DEBUG") and k ~= last_k and k >= 0 then
    last_k = k
    print(string.format("K %d in=(%d,%d) cnt=%02x R=%02x G=%02x V=%02x pos=%02x.%02x time=%02x%02x%02x",
      k, fire, left, ram(0x8d), ram(0xa8), ram(0xcc), ram(0xc0), ram(0xba), ram(0xc2),
      ram(0xb3), ram(0xb5), ram(0xb7)))
  end
  if reset_done and ram(0xd2) ~= 0 and not finish_at then
    finish_at = frames + tail
    print(string.format("FINISHED step=%d time_regs=%02x%02x%02x pos=%02x flag=%02x blown=%02x",
      k, ram(0xb3), ram(0xb5), ram(0xb7), ram(0xba), ram(0xd4), ram(0xce)))
  end
  if finish_at and frames >= finish_at then
    if os.getenv("DR_SNAP") then m.video:snapshot() end
    m:exit()
  end
  if frames > 4000 then print("TIMEOUT"); m:exit() end
end)
