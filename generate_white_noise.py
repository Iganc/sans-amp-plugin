import numpy as np, soundfile as sf
fs, dur, level_db = 48000, 60, -90
rng = np.random.default_rng(1234)          # ten sam seed co przy -40
x = rng.standard_normal(fs * dur)
x = np.clip(x, -3.5, 3.5)
x *= 10 ** (level_db / 20) / np.sqrt(np.mean(x ** 2))
print("generateds")
sf.write("noise_-90.wav", x, fs, subtype="FLOAT")