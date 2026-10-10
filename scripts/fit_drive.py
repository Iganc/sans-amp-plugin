#!/usr/bin/env python3
"""fit_drive.py - odpowiedź częstotliwościowa referencji (CRUNCH x DRIVE) vs model DriveStage.

Wejście: pliki <PREFIX>_<cmin|cmax>_<min|25|mid|75|max>_<poziom>.wav oraz <PREFIX>_dry_<poziom>.wav
(render_drive.lua). Szum jest losowy, więc porównujemy uśrednione widma (Welch), nie próbki.
  H(f) = sqrt( PSD_wet / PSD_dry )          (w dB)
Porównanie z modelem idzie po RÓŻNICACH względem (cmin, drive min), bo reszta toru
(GAIN, BUZZ, PUNCH, HIGH/LOW, LEVEL) jest w obu rendererach stała i się skraca.
Użycie:  python fit_drive.py [katalog] [prefix] [poziom]
"""
import sys, glob, os
import numpy as np
from scipy.signal import welch

try:
    import soundfile as sf
    def load(p): x, fs = sf.read(p, always_2d=True); return x, fs
except ImportError:
    from scipy.io import wavfile
    def load(p):
        fs, x = wavfile.read(p)
        if x.dtype.kind in "iu":                      # 16/24/32-bit PCM -> +-1
            x = x.astype(np.float64) / (np.iinfo(x.dtype).max + 1.0)
        else:
            x = x.astype(np.float64)
        return (x if x.ndim == 2 else x[:, None]), fs

DIR    = sys.argv[1] if len(sys.argv) > 1 else "/Users/igi/SansAmp"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "drive"
LEVEL  = sys.argv[3] if len(sys.argv) > 3 else "-90"
CTAGS = {"cmin": 0.0, "c25": 0.25, "cmid": 0.5, "c75": 0.75, "cmax": 1.0}
DTAGS = {"min": 0.0, "mid": 0.5, "max": 1.0}
FREQS = np.array([50, 100, 200, 400, 700, 1000, 1500, 2000, 3000,
                  3500, 4000, 5000, 6000, 7000, 8000, 10000, 12000, 15000], float)
from scipy.signal import welch, csd, correlate, correlation_lags

def align(x, y, maxlag=4096):
    n = min(len(x), len(y), 1 << 19)
    c = correlate(y[:n], x[:n], mode="full", method="fft")
    lags = correlation_lags(n, n)
    m = np.abs(lags) <= maxlag
    return lags[m][np.argmax(np.abs(c[m]))]       # >0: wet opóźniony względem dry

def h1_bands(dry_path, wet_path, centers, frac=1/6, nperseg=32768, maxlag=16384):
    xd, fs = load(dry_path); xw, _ = load(wet_path)
    x, y = xd.mean(axis=1), xw.mean(axis=1)
    n = min(len(x), len(y)); x, y = x[:n], y[:n]
    L = align(x, y, maxlag)
    if L > 0:   x, y = x[:n - L], y[L:]
    elif L < 0: x, y = x[-L:], y[:n + L]
    f, Sxx = welch(x, fs=fs, nperseg=nperseg)
    _, Syy = welch(y, fs=fs, nperseg=nperseg)
    _, Sxy = csd(x, y, fs=fs, nperseg=nperseg)
    coh_bin = np.abs(Sxy) ** 2 / (Sxx * Syy + 1e-300)
    H, coh = [], []
    for fc in centers:
        m = (f >= fc * 2 ** (-frac / 2)) & (f <= fc * 2 ** (frac / 2))
        H.append(20 * np.log10(np.abs(Sxy[m]).mean() / Sxx[m].mean()))
        coh.append(coh_bin[m].mean())
    return np.array(H), np.array(coh)

def psd(path):
    x, fs = load(path)
    f, p = welch(x, fs=fs, nperseg=16384, axis=0)
    return f, p.mean(axis=1)             # średnia po kanałach

def smooth_db(f, p, centers, frac=1/6):
    out = []
    for fc in centers:
        m = (f >= fc * 2 ** (-frac / 2)) & (f <= fc * 2 ** (frac / 2))
        out.append(10 * np.log10(p[m].mean()) if m.any() else np.nan)
    return np.array(out)

# ---------------------------------------------------------------- model DriveStage (małosygnałowy)
def model_db(f, crunch, drive, shunt=True):
    s = 2j * np.pi * f
    Rf, Cf, Rg0, Rpot, Cc = 330e3, 220e-12, 3.3e3, 100e3, 10e-9
    Rs, Rsh, Cin = 10e3, 100e3, 10e-9
    Rth = Rs * Rsh / (Rs + Rsh)
    h = Rsh / (Rs + Rsh) / (1 + s * Rth * Cin)
    Rg = Rg0 + (1 - crunch) * Rpot                                   # U9a
    pf, pg = 1 + s * Rf * Cf, 1 + s * Rg * Cc
    h = h * (pf * pg + s * Rf * Cc) / (pf * pg)
    h = h * (s * 100e3 * 47e-9) / (1 + s * 100e3 * 47e-9)            # HPF 47n/100K
    Rg = Rg0 + (1 - drive) * Rpot                                    # U9b
    h = h * (1 + Rf / Rg + s * Rf * Cf) / (1 + s * Rf * Cf)
    R1 = R2 = 22e3; C2, C4, R3, C3 = 10e-9, 560e-12, 10e3, 47e-9     # U10a
    Ys = s * C3 / (1 + s * R3 * C3) if shunt else 0
    br = (1 + s * R2 * C4) * (1 / R1 + 1 / R2 + s * C2 + Ys) - s * C2 - 1 / R2
    h = h * (1 / R1 / br)
    R, C2, C4 = 33e3, 2.2e-9, 1e-9                                   # U10b
    h = h / (1 + s * 2 * R * C4 + s ** 2 * R * R * C2 * C4)
    return 20 * np.log10(np.abs(h))

from scipy.optimize import least_squares


# ---------------------------------------------------------------- modele półki (dB)
def shelf_db(f, fz, fp):
    return 20 * np.log10(np.abs((1 + 1j * f / fz) / (1 + 1j * f / fp)))


def shelf2_db(f, fz, fp, fh):                 # + jeden biegun górny
    return shelf_db(f, fz, fp) - 10 * np.log10(1 + (f / fh) ** 2)


def shelf2o_db(f, fz, fp, fh, q):             # + biegun górny 2. rzędu (rezonans q)
    s = 1j * f
    num = 1 + s / fz
    den = (1 + s / fp) * (1 + s / (q * fh) + (s / fh) ** 2)
    return 20 * np.log10(np.abs(num / den))


def main():
    dry_path = os.path.join(DIR, f"{PREFIX}_dry_{LEVEL}.wav")
    if not os.path.exists(dry_path):
        sys.exit(f"Brak {dry_path} - uruchom render_drive.lua z DRY_RENDER = true.")

    xd, _ = load(dry_path); xd = xd.mean(axis=1)
    print(f"dry: RMS {20*np.log10(np.sqrt(np.mean(xd**2))):.1f} dBFS, "
          f"szczyt {20*np.log10(np.abs(xd).max()):.1f} dBFS")

    meas, coh = {}, {}
    for c in CTAGS:
        for d in DTAGS:
            p = os.path.join(DIR, f"{PREFIX}_{c}_{d}_{LEVEL}.wav")
            if os.path.exists(p):
                meas[(c, d)], coh[(c, d)] = h1_bands(dry_path, p, FREQS)
    if ("cmin", "min") not in meas:
        sys.exit("Brak renderu bazowego cmin/min.")

    c0 = coh[("cmin", "min")]
    print("Koherencja baseline:", " ".join(f"{x:5.2f}" for x in c0))
    if np.nanmedian(c0[:10]) < 0.9:
        print("!!! Koherencja baseline < 0.9: dry i wet to prawdopodobnie RÓŻNE realizacje szumu.\n")

    base = meas[("cmin", "min")]
    print(f"Poziom {LEVEL} dBFS. Bezwzględne wzmocnienie referencji (cmin, drive min) [dB]:")
    print("  f [Hz]  " + " ".join(f"{x:7.0f}" for x in FREQS))
    print("  H       " + " ".join(f"{x:7.1f}" for x in base))
    print(f"  Przy 1 kHz: {base[list(FREQS).index(1000)]:+.2f} dB\n")

    order = sorted(meas.items(), key=lambda kv: (CTAGS[kv[0][0]], DTAGS[kv[0][1]]))
    print("Różnice względem (cmin, drive min) [dB]:")
    for (c, d), h in order:
        if (c, d) == ("cmin", "min"):
            continue
        dm = np.where(coh[(c, d)] >= 0.9, h - base, np.nan)
        print(f"[{c:>4} {d:>3}] pomiar " + " ".join(f"{x:6.1f}" for x in dm))
        print(f"{'':11}koher. " + " ".join(f"{x:6.2f}" for x in coh[(c, d)]))

    # ---- Fit 1: półka, 50 Hz-4 kHz
    sel = FREQS <= 4000
    fit1 = {}
    print("\nFit 1: półka (zero fz, biegun fp), 50 Hz-4 kHz:")
    for c in CTAGS:
        if c == "cmin":
            continue
        h = meas[(c, "min")] - base
        r = least_squares(lambda p: shelf_db(FREQS[sel], *np.exp(p)) - h[sel],
                          np.log([85.0, 1000.0]))
        fz, fp = np.exp(r.x)
        fit1[c] = (fz, fp)
        print(f"  {c:>5}: fz={fz:6.1f}  fp={fp:7.1f}  plateau={20*np.log10(fp/fz):5.1f} dB  "
              f"RMS={np.sqrt(np.mean(r.fun**2)):.2f} dB")

    # ---- Fit 2: półka + biegun górny
    print("\nFit 2: półka + biegun górny fh, pełne pasmo:")
    for c in CTAGS:
        if c == "cmin":
            continue
        h = meas[(c, "min")] - base
        r = least_squares(lambda p: shelf2_db(FREQS, *np.exp(p)) - h,
                          np.log([85.0, 1000.0, 8000.0]))
        fz, fp, fh = np.exp(r.x)
        print(f"  {c:>5}: fz={fz:6.1f}  fp={fp:7.1f}  fh={fh:7.1f}  "
              f"RMS={np.sqrt(np.mean(r.fun**2)):.2f} dB")

    # ---- Fit 3: półka + biegun górny 2. rzędu (fz, fp, fh, q)
    print("\nFit 3: półka + biegun górny 2. rzędu (fh, Q), pełne pasmo:")
    lo = np.log([20.0, 50.0, 1000.0, 0.3])
    hi = np.log([500.0, 20000.0, 20000.0, 5.0])
    fit3 = {}
    for c in CTAGS:
        if c == "cmin":
            continue
        h = meas[(c, "min")] - base
        x0 = np.log([fit1[c][0], min(max(fit1[c][1], 60.0), 19000.0), 8000.0, 0.7])
        r = least_squares(lambda p: shelf2o_db(FREQS, *np.exp(p)) - h,
                          x0, bounds=(lo, hi))
        fz, fp, fh, q = np.exp(r.x)
        fit3[c] = (fz, fp, fh, q)
        print(f"  {c:>5}: fz={fz:6.1f}  fp={fp:7.1f}  fh={fh:7.1f}  Q={q:4.2f}  "
              f"RMS={np.sqrt(np.mean(r.fun**2)):.2f} dB  max|e|={np.abs(r.fun).max():.2f} dB")

    # ---- Unit OFF vs dry
    uoff = os.path.join(DIR, f"{PREFIX}_cmax_unit_off_{LEVEL}.wav")
    if os.path.exists(uoff):
        Hu, cu = h1_bands(dry_path, uoff, FREQS)
        print("\nUnit OFF vs dry (powinno być 0 dB, koherencja 1.00):")
        print("  H       " + " ".join(f"{x:7.2f}" for x in Hu))
        print("  koher.  " + " ".join(f"{x:7.2f}" for x in cu))

    print("\nResiduum interakcji = H(c,d) - H(c,min) - H(cmin,d) + H(cmin,min) [dB], 0 = czysta suma w dB:")
    for (c, d), h in order:
        if c == "cmin" or d == "min" or (c, "min") not in meas or ("cmin", d) not in meas:
            continue
        res = h - meas[(c, "min")] - meas[("cmin", d)] + base
        res = np.where(coh[(c, d)] >= 0.9, res, np.nan)
        print(f"[{c:>4} {d:>3}] " + " ".join(f"{x:6.2f}" for x in res))

    # ---- wykres (pomiar = punkty, Fit 3 = linia przerywana)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5.5))
        ff = np.geomspace(FREQS[0], FREQS[-1], 300)
        for (c, d), h in order:
            line, = ax.semilogx(FREQS, np.where(coh[(c, d)] >= 0.9, h - base, np.nan),
                                "o", label=f"{c} {d}")
            if c in fit3:
                ax.semilogx(ff, shelf2o_db(ff, *fit3[c]), "--", color=line.get_color(), lw=1)
        ax.set_xlabel("Hz"); ax.set_ylabel("dB względem cmin/drive min")
        ax.grid(True, which="both", alpha=.3); ax.legend()
        out = os.path.join(DIR, f"{PREFIX}_fit_{LEVEL}.png")
        fig.savefig(out, dpi=120); print("\nWykres:", out)
    except ImportError:
        pass


if __name__ == "__main__":
    main()