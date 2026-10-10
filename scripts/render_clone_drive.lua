-- render_clone_drive.lua (REAPER, ReaScript Lua)
-- Item z tym samym plikiem szumu co dla referencji -> SansAmpClone.
-- Wyniki: /Users/igi/SansAmp/clone/clone_drive_<crunch>_<drive>_<level>.wav
--
-- Użycie:
--   1. Zaznacz ścieżkę z itemem noise_-60.wav albo noise_-90.wav.
--   2. Wybierz właściwe źródło w ustawieniach renderu i WAV 32-bit float.
--   3. Najpierw uruchom z LIST_ONLY = true, aby sprawdzić nazwę FX i parametry.
--   4. Ustaw LIST_ONLY = false i uruchom render.

local LIST_ONLY = false

local OUTDIR = "/Users/igi/SansAmp/clone"
local PREFIX = "clone_drive"
local LEVEL_LABEL = "-90" -- zmień na "-90" dla serii DRIVE

-- To odpowiada aktualnie istniejącym plikom ref/drive/*_-60.wav.
local CRUNCH_POS = {
  { "cmin", 0.0 }, { "c125", 0.125 }, { "c375", 0.375 },
  { "c625", 0.625 }, { "c875", 0.875 },
}

local DRIVE_POS = { { "min", 0.0 } }

if LEVEL_LABEL == "-90" then
  CRUNCH_POS = { { "cmin", 0.0 } }
  DRIVE_POS = { { "min", 0.0 }, { "mid", 0.5 }, { "max", 1.0 } }
end

-- Tryb dry jest opcjonalny; do porównania można użyć ref/drive/drive_dry_*.wav.
local DRY_RENDER = false
local DRY_ONLY = false

local function msg(s)
  reaper.ShowConsoleMsg(tostring(s) .. "\n")
end

local track = reaper.GetSelectedTrack(0, 0)
if not track then
  msg("Zaznacz ścieżkę z szumem.")
  return
end

local function fx_name(fx)
  local _, name = reaper.TrackFX_GetFXName(track, fx, "")
  return name
end

local function find_fx()
  local fallback

  for i = 0, reaper.TrackFX_GetCount(track) - 1 do
    local name = fx_name(i):lower()
    if name:find("sansampclone", 1, true) then
      return i
    end
    if not fallback and name:find("sansamp", 1, true) then
      fallback = i
    end
  end

  return fallback
end

local function param_map(fx)
  local map = {}
  for p = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
    local _, name = reaper.TrackFX_GetParamName(track, fx, p, "")
    map[name:lower()] = p
  end
  return map
end

local function list_fx()
  for i = 0, reaper.TrackFX_GetCount(track) - 1 do
    msg("FX [" .. i .. "] " .. fx_name(i))
    for p = 0, reaper.TrackFX_GetNumParams(track, i) - 1 do
      local _, name = reaper.TrackFX_GetParamName(track, i, p, "")
      local value = reaper.TrackFX_GetParamNormalized(track, i, p)
      local _, shown = reaper.TrackFX_GetFormattedParamValue(track, i, p, "")
      msg(string.format("    [%d] %s raw=%.6f (%s)", p, name, value, shown))
    end
  end
end

if LIST_ONLY then
  list_fx()
  return
end

local fx = find_fx()
if not fx then
  msg("Nie znaleziono FX zawierającego nazwę 'sansamp'.")
  return
end

msg("Wybrany FX [" .. fx .. "] " .. fx_name(fx))
local params = param_map(fx)

local function parameter(name)
  local index = params[name:lower()]
  if index == nil then
    msg("BLAD: brak parametru '" .. name .. "' w klonie.")
  end
  return index
end

local function set_parameter(name, value)
  local index = parameter(name)
  if index == nil then
    return false
  end
  reaper.TrackFX_SetParamNormalized(track, fx, index, value)
  return true
end

-- Wartości są normalized values hosta. Input: -12..12 dB, Output: -24..12 dB.
local function set_clone_controls(crunch, drive)
  set_parameter("Input", 0.5)       -- 0 dB
  set_parameter("Output", 2.0 / 3.0) -- 0 dB
  set_parameter("Gain", 0.5)
  set_parameter("Buzz", 0.5)
  set_parameter("Punch", 0.5)
  set_parameter("High", 0.5)
  set_parameter("Low", 0.5)
  set_parameter("Crunch", crunch)
  set_parameter("Drive", drive)
  set_parameter("Bypass", 0.0)
  set_parameter("Wet", 1.0)
  set_parameter("Delta", 0.0)
end

local function render(pattern)
  reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", pattern, true)
  reaper.Main_OnCommand(42230, 0)
end

reaper.GetSetProjectInfo_String(0, "RENDER_FILE", OUTDIR, true)

if DRY_RENDER or DRY_ONLY then
  reaper.TrackFX_SetEnabled(track, fx, false)
  render(string.format("%s_dry_%s", PREFIX, LEVEL_LABEL))
  reaper.TrackFX_SetEnabled(track, fx, true)
end

if not DRY_ONLY then
  for _, crunch in ipairs(CRUNCH_POS) do
    for _, drive in ipairs(DRIVE_POS) do
      set_clone_controls(crunch[2], drive[2])
      local pattern = string.format("%s_%s_%s_%s",
                                    PREFIX, crunch[1], drive[1], LEVEL_LABEL)
      msg(string.format("%s: crunch=%.3f drive=%.3f",
                       pattern, crunch[2], drive[2]))
      render(pattern)
    end
  end
end

msg("Gotowe.")
