-- render_drive.lua  (REAPER, ReaScript Lua)
-- Ścieżka: item z plikiem szumu (stały seed) -> AP SansAmp Rack (referencja). Bez generatora.
-- Pętla: CRUNCH x DRIVE. Wszystkie gałki PSA-1 są wystawione do hosta.
-- Wyniki: <OUTDIR>/<PREFIX>_<crunch>_<drive>_<LEVEL_LABEL>.wav  oraz  <PREFIX>_log.txt
--
-- PRZED UŻYCIEM:
--   1. Item ze szumem na zaznaczonej ścieżce, EMO-Generator usunięty (lub wyłączony) z łańcucha.
--   2. W oknie Render ustaw raz: źródło (Master mix / Selected tracks), zakres obejmujący cały item,
--      WAV 32-bit float, sample rate = rate pliku szumu.
--   3. LIST_ONLY = true -> sprawdź nazwy, potem LIST_ONLY = false.
--   4. Dla innego poziomu: podmień item na plik o innym poziomie i zmień LEVEL_LABEL.

local REF_MATCH = "sansamp rack"      -- referencja (NIE "sansamp", bo pasuje do klona)
local LIST_ONLY = true

local OUTDIR = "/Users/igi/SansAmp"
local PREFIX = "drive"
local LEVEL_LABEL = "-60"             -- poziom RMS szumu w itemie; trafia do nazwy pliku

local DRY_ONLY   = false              -- true: tylko dry

-- Sam DRIVE przy wyłączonym crunchu. Do taperu crunchu (drive 0):
--   CRUNCH_POS = { {"cmin",0.0}, {"c25",0.25}, {"cmid",0.5}, {"c75",0.75}, {"cmax",1.0} }
--   DRIVE_POS  = { {"min",0.0} }
local LEVEL_LABEL = "-60"
local DRY_RENDER = false
local CRUNCH_POS = { {"cmin",0.0} }
local DRIVE_POS  = { {"min",0.0} }
-- Stałe ustawienia (raw 0..1 wg listy parametrów). Dotyczą obu kanałów (Link Parameters = on).
local CHANNEL_FIXED = {
  ["Low"] = 0.5, ["Buzz"] = 0.5, ["High"] = 0.5, ["Punch"] = 0.5,
  ["Pre-Amp"] = 0.488, ["Level"] = 1.0, ["Mix"] = 1.0,
  ["Unit ON/Unit OFF"] = 1.0, ["Phase"] = 0.0,
}
local GLOBAL_FIXED = {
  ["Link Parameters"] = 1.0, ["Rack In"] = 0.5, ["Rack Out"] = 0.5, ["LR/MS Processing"] = 0.0,
  ["Channel 1 Unit Selection"] = 0.0, ["Channel 2 Unit Selection"] = 0.0,
}

local function msg(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end

local track = reaper.GetSelectedTrack(0, 0)
if not track then msg("Zaznacz ścieżkę."); return end

local function find_fx(match)
  for i = 0, reaper.TrackFX_GetCount(track) - 1 do
    local _, name = reaper.TrackFX_GetFXName(track, i, "")
    if name:lower():find(match, 1, true) then return i end
  end
end

local function param_map(fx)
  local m = {}
  for p = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
    local _, pn = reaper.TrackFX_GetParamName(track, fx, p, "")
    if m[pn:lower()] == nil then m[pn:lower()] = p end   -- przy duplikatach (Bypass, Wet) pierwszy
  end
  return m
end

if LIST_ONLY then
  for i = 0, reaper.TrackFX_GetCount(track) - 1 do
    local _, name = reaper.TrackFX_GetFXName(track, i, "")
    msg("FX [" .. i .. "] " .. name)
    for p = 0, reaper.TrackFX_GetNumParams(track, i) - 1 do
      local _, pn = reaper.TrackFX_GetParamName(track, i, p, "")
      local v = reaper.TrackFX_GetParamNormalized(track, i, p)
      local _, shown = reaper.TrackFX_GetFormattedParamValue(track, i, p, "")
      msg(string.format("    [%d] %s  raw=%.3f  (%s)", p, pn, v, shown))
    end
  end
  return
end

local ref = find_fx(REF_MATCH)
if not ref then msg("Nie znaleziono referencji '" .. REF_MATCH .. "'."); return end
local rp = param_map(ref)

local function set_ref(name, val)
  local p = rp[name:lower()]
  if not p then msg("UWAGA: brak parametru '" .. name .. "'"); return nil end
  reaper.TrackFX_SetParamNormalized(track, ref, p, val)
  return p
end

local log = io.open(OUTDIR .. "/" .. PREFIX .. "_log.txt", "w")
local function logline(s) if log then log:write(s .. "\n") end end

for name, val in pairs(GLOBAL_FIXED) do set_ref(name, val); logline(string.format("FIXED %s = %.3f", name, val)) end
for ch = 1, 2 do
  for name, val in pairs(CHANNEL_FIXED) do
    set_ref("PSA-1 " .. ch .. ": " .. name, val)
    logline(string.format("FIXED PSA-1 %d: %s = %.3f", ch, name, val))
  end
end

reaper.GetSetProjectInfo_String(0, "RENDER_FILE", OUTDIR, true)

-- 42230 = File: Render project, using the most recent render settings, auto-close render dialog
local function render(pattern)
  reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", pattern, true)
  reaper.Main_OnCommand(42230, 0)
end

if DRY_RENDER or DRY_ONLY then
  reaper.TrackFX_SetEnabled(track, ref, false)
  local pattern = string.format("%s_dry_%s", PREFIX, LEVEL_LABEL)
  msg(pattern); logline(pattern .. " (referencja wyłączona)")
  render(pattern)
  reaper.TrackFX_SetEnabled(track, ref, true)
end

if not DRY_ONLY then
  for _, c in ipairs(CRUNCH_POS) do
    for ch = 1, 2 do set_ref("PSA-1 " .. ch .. ": Crunch", c[2]) end
    for _, d in ipairs(DRIVE_POS) do
      for ch = 1, 2 do set_ref("PSA-1 " .. ch .. ": Drive", d[2]) end
      local pattern = string.format("%s_%s_%s_%s", PREFIX, c[1], d[1], LEVEL_LABEL)
      local line = string.format("%s: crunch=%.3f drive=%.3f", pattern, c[2], d[2])
      msg(line); logline(line)
      render(pattern)
    end
  end
end

if log then log:close() end
msg("Gotowe.")