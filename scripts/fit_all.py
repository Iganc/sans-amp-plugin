import numpy as np
from scipy.optimize import least_squares

FREQS = np.array([50, 100, 200, 400, 700, 1000, 1500, 2000, 3000,
                  3500, 4000, 5000, 6000, 7000, 8000, 10000, 12000, 15000], float)
DATA = {
 0.125: [0.8,2.0,3.1,3.6,3.7,3.7,3.7,3.7,3.6,3.5,3.4,3.2,2.9,2.7,2.4,1.9,1.4,0.8],
 0.25:  [1.4,3.5,5.8,7.0,7.4,7.5,7.5,7.4,7.2,7.1,7.0,6.7,6.3,5.9,5.4,4.5,3.6,2.3],
 0.375: [1.6,4.1,7.5,10.0,10.9,11.2,11.2,11.2,11.0,10.9,10.7,10.3,9.9,9.4,8.8,7.7,6.4,4.5],
 0.5:   [1.5,4.1,8.1,12.0,13.9,14.6,14.9,15.0,14.8,14.7,14.5,14.1,13.6,13.1,12.5,11.2,9.7,7.3],
 0.625: [1.4,3.9,8.1,12.9,16.1,17.4,18.4,18.7,18.7,18.6,18.4,18.0,17.5,16.9,16.3,14.9,13.3,10.7],
 0.75:  [1.3,3.7,8.0,13.2,17.2,19.4,21.2,22.0,22.5,22.5,22.4,22.0,21.5,20.9,20.2,18.7,17.1,14.3],
 0.875: [1.3,3.7,7.9,13.3,17.8,20.5,23.2,24.7,26.0,26.2,26.2,26.0,25.6,25.0,24.3,22.8,21.1,18.2],
 1.0:   [1.3,3.8,8.1,13.6,18.2,21.2,24.4,26.5,28.8,29.4,29.8,30.0,29.7,29.2,28.6,27.0,25.2,22.2],
}

def par(p, k):
    z0, z1, b1, b2, b3, c1, c2 = p
    fz = np.exp(z0 + z1 * k)
    fp = fz * np.exp(b1 * k + b2 * k**2 + b3 * k**3)
    c = max(c1 * k + c2 * k**2, 1e-6)
    return fz, fp, 1000.0 / c

def H_db(f, p, k):
    fz, fp, fh = par(p, k)
    s = 1j * f
    return 20 * np.log10(np.abs((1 + s / fz) / ((1 + s / fp) * (1 + s / fh) ** 2)))

def resid(p):
    return np.concatenate([H_db(FREQS, p, k) - np.array(v) for k, v in DATA.items()])

p0 = [np.log(75.0), 0.2, 3.0, 1.0, 0.0, 0.1, 0.0]
r = least_squares(resid, p0)
p = r.x
print("parametry:", np.array2string(p, precision=5))
print("RMS ogółem: %.3f dB\n" % np.sqrt(np.mean(r.fun ** 2)))
for k, v in DATA.items():
    e = H_db(FREQS, p, k) - np.array(v)
    fz, fp, fh = par(p, k)
    print(f"k={k:5.3f}  fz={fz:5.1f} fp={fp:7.1f} fh={fh:7.0f}  "
          f"RMS={np.sqrt(np.mean(e**2)):.2f}  max={np.abs(e).max():.2f} dB")
print("\nC++:")
print("constexpr double kZ0=%.6f, kZ1=%.6f, kB1=%.6f, kB2=%.6f, kB3=%.6f, kC1=%.6f, kC2=%.6f;" % tuple(p))

from scipy.interpolate import PchipInterpolator

K = np.array([0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0])
KD = np.array(sorted(DATA))                      # 8 pozycji z danymi (bez 0)
LAM = 0.05                                       # kara za nieregularność

def par(p, k):
    lz, lp, lh = p[:9], p[9:18], p[18:27]        # log fz, log fp, log fh w węzłach
    fz = np.exp(PchipInterpolator(K, lz)(k))
    fp = np.exp(PchipInterpolator(K, lp)(k))
    fh = np.exp(PchipInterpolator(K, lh)(k))
    return fz, fp, fh

def H_db(f, p, k):
    fz, fp, fh = par(p, k)
    s = 1j * f
    return 20 * np.log10(np.abs((1 + s / fz) / ((1 + s / fp) * (1 + s / fh) ** 2)))

def resid(p):
    r = [H_db(FREQS, p, k) - np.array(DATA[k]) for k in KD]
    smooth = [LAM * np.diff(p[i:i + 9], 2) for i in (0, 9, 18)]
    return np.concatenate(r + smooth)

p0 = np.concatenate([np.full(9, np.log(80.0)),
                     np.log(np.maximum(75 * np.exp(3.9 * K * 1.0) , 75.0)),
                     np.log(np.linspace(20000, 9000, 9))])
r = least_squares(resid, p0)
p = r.x
fz, fp, fh = par(p, K)
print("k      fz      fp      fh")
for i, k in enumerate(K):
    print(f"{k:5.3f} {fz[i]:7.1f} {fp[i]:8.1f} {fh[i]:8.0f}")
for k in KD:
    e = H_db(FREQS, p, k) - np.array(DATA[k])
    print(f"k={k:5.3f} RMS={np.sqrt(np.mean(e**2)):.2f} max={np.abs(e).max():.2f} dB")