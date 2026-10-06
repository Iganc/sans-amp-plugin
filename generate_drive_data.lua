local retval, track_num, fx_index, param_index = reaper.GetLastTouchedFX()

if not retval then
    reaper.ShowMessageBox("Najpierw rusz gałką Drive, a potem uruchom ten skrypt!", "Błąd", 0)
    return
end

local track = reaper.GetTrack(0, track_num - 1)
local _, param_name = reaper.TrackFX_GetParamName(track, fx_index, param_index)

local confirm = reaper.ShowMessageBox("Czy automatyzujemy parametr: " .. param_name .. "?", "Potwierdzenie", 4)
if confirm == 7 then return end

local item = reaper.GetTrackMediaItem(track, 0)
if not item then
    reaper.ShowMessageBox("Brak pliku na ścieżce!", "Błąd", 0)
    return
end

-- Pobieramy oryginalną długość pliku (np. ~3 minuty)
local original_length = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")

-- Włączamy pętlenie pliku i mnożymy go 11 razy (11 kroków: 0% do 100% co 10%)
local num_steps = 11
reaper.SetMediaItemInfo_Value(item, "B_LOOPSRC", 1)
reaper.SetMediaItemInfo_Value(item, "D_LENGTH", original_length * num_steps)

local env = reaper.GetFXEnvelope(track, fx_index, param_index, true)
local project_path = reaper.GetProjectPath("")
if project_path == "" then
    reaper.ShowMessageBox("Najpierw zapisz projekt REAPERa na dysku!", "Błąd", 0)
    return
end

local csv_path = project_path .. "/drive_param.csv"
local file = io.open(csv_path, "w")
file:write("time,drive_value\n")

-- Rysowanie 11 płaskich bloków
for i = 0, num_steps - 1 do
    local time = i * original_length
    local value = i / (num_steps - 1) -- generuje 0.0, 0.1, 0.2 ... 1.0
    
    -- Wstawienie punktu schodkowego (shape = 1 to kwadrat/schodek)
    reaper.InsertEnvelopePoint(env, time, value, 1, 0, false, true)
    file:write(string.format("%.3f,%.3f\n", time, value))
end

-- Zamknięcie ostatniego bloku, żeby obwiednia nie opadła
reaper.InsertEnvelopePoint(env, original_length * num_steps, 1.0, 1, 0, false, true)

reaper.Envelope_SortPoints(env)
reaper.UpdateArrange()
io.close(file)

reaper.ShowMessageBox("Rozciągnięto audio i wygenerowano 11 poziomów Drive.\nPlik CSV: " .. csv_path, "Gotowe", 0)