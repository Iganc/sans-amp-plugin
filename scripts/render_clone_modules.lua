-- REAPER, ReaScript Lua
-- Renderuje serie pojedynczych modulow klona przy pozostalych galach w pozycji srodkowej.
--
-- Uzycie:
--   1. Zaznacz sciezke z odpowiednim plikiem noise.
--   2. Ustaw MODULE na buzz, punch, high albo low.
--   3. Ustaw LEVEL_LABEL zgodnie z plikiem szumu i uruchom skrypt.
--   4. Najpierw uruchom z LIST_ONLY = true, aby sprawdzic FX i parametry.
--
-- Wyniki:
--   /Users/igi/SansAmp/clone/clone_<module>_<tag>_<level>.wav

local LIST_ONLY = false

local OUTDIR = "/Users/igi/SansAmp/clone"
local MODULE = "low"       -- buzz, punch, high albo low
local LEVEL_LABEL = "-60"   -- musi odpowiadac wybranemu plikowi noise
local DRY_RENDER = false

local POSITIONS = {
  { "min", 0.0 },
  { "mid", 0.5 },
  { "max", 1.0 },
}

local MODULES = {
  buzz = "Buzz",
  punch = "Punch",
  high = "High",
  low = "Low",
}

local function msg(s)
  reaper.ShowConsoleMsg(tostring(s) .. "\n")
end

local track = reaper.GetSelectedTrack(0, 0)
if not track then
  msg("Zaznacz sciezke z szumem.")
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

MODULE = MODULE:lower()
local tested_parameter = MODULES[MODULE]
if not tested_parameter then
  msg("BLAD: MODULE musi byc jednym z: buzz, punch, high, low.")
  return
end

local fx = find_fx()
if not fx then
  msg("Nie znaleziono FX zawierajacego nazwe 'sansamp'.")
  return
end

local function build_param_map()
  local map = {}
  for p = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
    local _, name = reaper.TrackFX_GetParamName(track, fx, p, "")
    map[name:lower()] = p
  end
  return map
end

local params = build_param_map()
local function set_parameter(name, value)
  local index = params[name:lower()]
  if index == nil then
    msg("BLAD: brak parametru '" .. name .. "' w klonie.")
    return false
  end
  reaper.TrackFX_SetParamNormalized(track, fx, index, value)
  return true
end

local function set_clone_controls(module_value)
  -- Neutralne ustawienia toru; tylko badany modul zmienia sie w petli.
  local controls = {
    Input = 0.5,       -- 0 dB dla zakresu -12..12 dB
    Output = 2.0 / 3.0, -- 0 dB dla zakresu -24..12 dB
    Gain = 0.5,
    Buzz = 0.5,
    Punch = 0.5,
    High = 0.5,
    Low = 0.5,
    Drive = 0.0,
    Crunch = 0.0,
    Bypass = 0.0,
    Wet = 1.0,
    Delta = 0.0,
  }
  controls[tested_parameter] = module_value
  for name, value in pairs(controls) do
    if not set_parameter(name, value) then
      return false
    end
  end
  return true
end

local function render(pattern)
  reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", pattern, true)
  reaper.Main_OnCommand(42230, 0)
end

msg("Wybrany FX [" .. fx .. "] " .. fx_name(fx))
reaper.GetSetProjectInfo_String(0, "RENDER_FILE", OUTDIR, true)

if DRY_RENDER then
  reaper.TrackFX_SetEnabled(track, fx, false)
  render(string.format("clone_%s_dry_%s", MODULE, LEVEL_LABEL))
  reaper.TrackFX_SetEnabled(track, fx, true)
end

for _, position in ipairs(POSITIONS) do
  if not set_clone_controls(position[2]) then
    return
  end
  local pattern = string.format("clone_%s_%s_%s", MODULE, position[1], LEVEL_LABEL)
  msg(string.format("%s: %s=%.3f", pattern, tested_parameter, position[2]))
  render(pattern)
end

msg("Gotowe.")
