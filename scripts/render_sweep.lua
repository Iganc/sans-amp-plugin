-- render_drive.lua  (REAPER, ReaScript Lua)
-- Zmiana względem render_sweep.lua: pętla po DRIVE x poziom wejściowy, parametry nieobecne
-- w hoście (CRUNCH, HIGH, LOW, LEVEL) są tylko ostrzeżeniem, a nie błędem.
--
-- PRZED UŻYCIEM:
--   1. Ścieżka z białym szumem (item) o poziomie BASE_DB i wtyczką referencyjną w FX.
--   2. Zaznacz TĘ ścieżkę.
--   3. W oknie Render ustaw raz: źródło, zakres (czas itemu), WAV 24-bit, sample rate.
--   4. W GUI wtyczki ustaw RĘCZNIE gałki niewidoczne dla hosta: CRUNCH, HIGH, LOW, LEVEL
--      i zapisz ich pozycje w PREFIX (np. drive_cmin / drive_cmax).
--   5. LIST_ONLY = true, uruchom, sprawdź nazwy parametrów i wartości raw, popraw FIXED,
--      potem LIST_ONLY = false.
--
-- Wyniki: <OUTDIR>/<PREFIX>_<tag>_<poziom>.wav oraz <PREFIX>_log.txt z ustawieniami.

local FX_NAME_MATCH = "sansamp"      -- fragment nazwy wtyczki referencyjnej
local LIST_ONLY     = true

local OUTDIR  = "/Users/igi/SansAmp"
local PREFIX  = "drive_cmin"         -- zmień ręcznie przy zmianie CRUNCH w GUI (np. drive_cmax)

local BASE_DB = -40                  -- poziom szumu w itemie (dBFS RMS) przy głośności itemu = 0 dB
local LEVELS  = { -40 }              -- np. { -40, -30, -20, -12, -6 }; nazwa pliku = ten poziom

local DRIVE_PARAM = "DRIVE"
local DRIVE_POS = {
  { "min", 0.0 }, { "25", 0.25 }, { "mid", 0.5 }, { "75", 0.75 }, { "max", 1.0 },
}

-- Stałe ustawienia gałek widocznych dla hosta (nazwa -> pozycja 0..1, jak na liście parametrów).
-- Bypass: raw 1.0 = "bypassed", więc musi być 0. Sprawdź też Wet/Delta i Output/Input na LIST_ONLY.
local FIXED = { GAIN = 0.5, BUZZ = 0.5, PUNCH = 0.5, BYPASS = 0.0, WET = 1.0, DELTA = 0.0 }

local function msg(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end

local track = reaper.GetSelectedTrack(0, 0)
if not track then msg("Zaznacz ścieżkę z wtyczką."); return end

local fx
for i = 0, reaper.TrackFX_GetCount(track) - 1 do
  local _, name = reaper.TrackFX_GetFXName(track, i, "")
  if name:lower():find(FX_NAME_MATCH, 1, true) then fx = i; break end
end
if not fx then msg("Nie znaleziono wtyczki zawierającej '" .. FX_NAME_MATCH .. "'."); return end

local params = {}
for p = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
  local _, pn = reaper.TrackFX_GetParamName(track, fx, p, "")
  params[pn:lower()] = p
end

if LIST_ONLY then
  msg("Parametry wtyczki:")
  for p = 0, reaper.TrackFX_GetNumParams(track, fx) - 1 do
    local _, pn = reaper.TrackFX_GetParamName(track, fx, p, "")
    local v = reaper.TrackFX_GetParamNormalized(track, fx, p)
    local _, shown = reaper.TrackFX_GetFormattedParamValue(track, fx, p, "")
    msg(string.format("  [%d] %s  raw=%.3f  (%s)", p, pn, v, shown))
  end
  return
end

local drive_p = params[DRIVE_PARAM:lower()]
if not drive_p then msg("Nie znaleziono parametru '" .. DRIVE_PARAM .. "'."); return end

local item = reaper.GetTrackMediaItem(track, 0)
if not item then msg("Na zaznaczonej ścieżce nie ma itemu."); return end
local orig_item_vol = reaper.GetMediaItemInfo_Value(item, "D_VOL")

local log = io.open(OUTDIR .. "/" .. PREFIX .. "_log.txt", "w")
local function logline(s) if log then log:write(s .. "\n") end end

-- stałe parametry
for name, val in pairs(FIXED) do
  local p = params[name:lower()]
  if p then
    reaper.TrackFX_SetParamNormalized(track, fx, p, val)
    local _, shown = reaper.TrackFX_GetFormattedParamValue(track, fx, p, "")
    logline(string.format("FIXED %s = %.3f (%s)", name, val, shown))
  else
    msg("UWAGA: parametr '" .. name .. "' nie jest widoczny dla hosta - pomijam.")
    logline("FIXED " .. name .. " - brak w hoście")
  end
end

reaper.GetSetProjectInfo_String(0, "RENDER_FILE", OUTDIR, true)

for _, level in ipairs(LEVELS) do
  -- poziom wejścia: głośność itemu (fader ścieżki jest za FX, więc się nie nadaje)
  local gain = 10 ^ ((level - BASE_DB) / 20)
  reaper.SetMediaItemInfo_Value(item, "D_VOL", orig_item_vol * gain)
  reaper.UpdateArrange()

  for _, d in ipairs(DRIVE_POS) do
    local tag, pos = d[1], d[2]
    reaper.TrackFX_SetParamNormalized(track, fx, drive_p, pos)
    local got = reaper.TrackFX_GetParamNormalized(track, fx, drive_p)
    local _, shown = reaper.TrackFX_GetFormattedParamValue(track, fx, drive_p, "")

    local pattern = string.format("%s_%s_%d", PREFIX, tag, level)
    reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", pattern, true)
    local line = string.format("%s: %s raw=%.3f (%s), item %+.1f dB", pattern, DRIVE_PARAM, got, shown, level - BASE_DB)
    msg(line); logline(line)

    -- 42230 = File: Render project, using the most recent render settings, auto-close render dialog
    reaper.Main_OnCommand(42230, 0)
  end
end

reaper.SetMediaItemInfo_Value(item, "D_VOL", orig_item_vol)
reaper.UpdateArrange()
if log then log:close() end
msg("Gotowe.")