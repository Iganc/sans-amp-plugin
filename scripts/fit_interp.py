import sys, os
import numpy as np
from scipy.signal import bilinear, freqz
import fit_drive as fd
from fit_drive import h1_bands, FREQS, shelf2o_db, DIR, PREFIX, LEVEL

# parametry z Fit 3: gałka -> (fz, fp, fh, Q); 0% to założenie (płasko)
KNOB = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
PAR = np.array([
    [75.0,   75.0,  20000.0, 0.5],
    [70.0,  168.1,  20000.0, 0.41],
    [76.4,  449.0,  11715.3, 0.53],
    [85.3, 1309.3,  10279.6, 0.55],
    [84.8, 4905.6,   8114.6, 0.54]])

def params(k):
    return tuple(np.exp([np.interp(k, KNOB, np.log(PAR[:, i])) for i in range(4)]))

TEST = {"c125": 0.125, "c375": 0.375, "c625": 0.625, "c875": 0.875}

def main():
    dry = os.path.join(DIR, f"{PREFIX}_dry_{LEVEL}.wav")
    base_p = os.path.join(DIR, f"{PREFIX}_cmin_min_{LEVEL}.wav")
    base, _ = h1_bands(dry, base_p, FREQS)
    print("Interpolacja vs pomiar [dB] (błąd = pomiar - model):")
    print("  f [Hz]    " + " ".join(f"{x:6.0f}" for x in FREQS))
    for tag, k in TEST.items():
        p = os.path.join(DIR, f"{PREFIX}_{tag}_min_{LEVEL}.wav")
        if not os.path.exists(p):
            print(f"  brak {p}"); continue
        h, coh = h1_bands(dry, p, FREQS)
        meas = h - base
        model = shelf2o_db(FREQS, *params(k))
        err = meas - model
        print(f"[{tag:>4}] pom  " + " ".join(f"{x:6.1f}" for x in meas))
        print(f"       mod  " + " ".join(f"{x:6.1f}" for x in model))
        print(f"       błąd " + " ".join(f"{x:6.2f}" for x in err)
              + f"   RMS {np.sqrt(np.mean(err**2)):.2f}  max {np.abs(err).max():.2f}  coh min {coh.min():.2f}")

    print("\nDyskretyzacja (bilinear bez prewarpu) vs analog, 50 Hz-15 kHz:")
    for k in [0.25, 0.5, 0.75, 1.0]:
        fz, fp, fh, q = params(k)
        wz, wp, wh = 2*np.pi*fz, 2*np.pi*fp, 2*np.pi*fh
        num = [1/wz, 1.0]
        den = np.polymul([1/wp, 1.0], [1/wh**2, 1/(q*wh), 1.0])
        for fs in (44100, 48000, 96000):
            b, a = bilinear(num, den, fs)
            _, hd = freqz(b, a, worN=2*np.pi*FREQS/fs)
            err = 20*np.log10(np.abs(hd)) - shelf2o_db(FREQS, fz, fp, fh, q)
            print(f"  crunch {k:4.2f} fs {fs:6d}: max|e| = {np.abs(err).max():5.2f} dB "
                  f"(przy {FREQS[np.abs(err).argmax()]:.0f} Hz)")

main()