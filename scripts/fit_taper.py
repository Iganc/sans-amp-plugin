#!/usr/bin/env python3
"""
fit_taper.py - wyznaczanie taperu galki HIGH (x(pos)) z kilku pozycji galki.

Uzywa modelu z fit_tone.py (Baxandall). Dane: rendery HIGH dla pozycji 1.0 (max), 0.0 (min),
0.25, 0.75 oraz mid (odniesienie, pozycja galki 0.5). Wszystkie na tym samym poziomie.

x = polozenie wipera od strony szyny (0..1); max galki = x 0, min galki = x 1.

Tryby dopasowania (C i R wipera dopasowywane razem z taperem, albo R stale):
  free  - x dla mid, 25% i 75% sa wolnymi parametrami (bez zalozen o ksztalcie taperu)
  pow1  - x = 1 - pos**k
  pow2  - x = (1 - pos)**k

Uzycie:
    python fit_taper.py --prefix high --level -40
(szuka plikow high_max_-40.wav, high_min_-40.wav, high_25_-40.wav, high_75_-40.wav, high_mid_-40.wav)
"""
import argparse
import sys
import numpy as np
from scipy.optimize import least_squares

try:
    from fit_tone import ratio_db
    from fit_punch import measured_ratio
except ImportError:
    sys.exit("Potrzebne fit_tone.py i fit_punch.py w tym samym folderze.")


def load_sets(args):
    name = lambda tag: f"{args.prefix}_{tag}_{args.level}.wav"
    mid = name('mid')
    items = [('max', 1.0), ('min', 0.0), ('25', 0.25), ('75', 0.75)]
    sets = []
    for tag, pos in items:
        f, r, _ = measured_ratio(name(tag), mid, args.fmin, args.fmax, args.skip,
                                 None, None, args.min_snr)
        if len(f) < 10:
            sys.exit(f"Za malo pasm z dobrym SNR dla {name(tag)}.")
        sets.append((tag, f, r, pos))
    return sets


def make_taper(mode, tail, free_pos):
    """Zwraca funkcje pos -> x. tail = parametry taperu."""
    if mode == 'free':
        table = {0.0: 1.0, 1.0: 0.0}
        for p, x in zip(free_pos, tail):
            table[p] = x
        return lambda pos: table[pos]
    k = tail[0]
    if mode == 'pow1':
        return lambda pos: 1.0 - pos ** k
    return lambda pos: (1.0 - pos) ** k


def fit_mode(sets, pos_m, mode, rw_fixed):
    free_pos = sorted({pos_m} | {s[3] for s in sets if s[3] not in (0.0, 1.0)})
    if mode == 'free':
        n_tail, tail_lo, tail_hi = len(free_pos), [0.02] * len(free_pos), [0.98] * len(free_pos)
        starts_tail = [[1 - p for p in free_pos], [0.5] * len(free_pos), [0.7 - 0.4 * p for p in free_pos]]
    else:
        n_tail, tail_lo, tail_hi = 1, [0.2], [5.0]
        starts_tail = [[0.5], [1.0], [2.0]]

    def unpack(p):
        cap = 10 ** p[0]
        rw = 10 ** p[1] if rw_fixed is None else rw_fixed
        return cap, rw, make_taper(mode, p[2:], free_pos)

    def resid(p):
        cap, rw, xf = unpack(p)
        xm = xf(pos_m)
        return np.concatenate([ratio_db(f, 'high', xf(pos), xm, cap, rw) - r
                               for _, f, r, pos in sets])

    best = None
    for logc in (-8.3, -8.0, -7.7):
        for tail0 in starts_tail:
            p0 = [logc, np.log10(rw_fixed) if rw_fixed else 3.5] + tail0
            lo = [-10.0, np.log10(rw_fixed) - 1e-9 if rw_fixed else 2.5] + tail_lo
            hi = [-6.5, np.log10(rw_fixed) + 1e-9 if rw_fixed else 4.7] + tail_hi
            try:
                sol = least_squares(resid, p0, bounds=(lo, hi))
            except Exception:
                continue
            if best is None or sol.cost < best.cost:
                best = sol
    cap, rw, xf = unpack(best.x)
    rms = float(np.sqrt(np.mean(best.fun ** 2)))
    return cap, rw, xf, rms, best.x[2:], free_pos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prefix', default='high')
    ap.add_argument('--level', default='-40')
    ap.add_argument('--pos-m', type=float, default=0.5, help='pozycja galki dla pliku mid')
    ap.add_argument('--fmin', type=float, default=30.0)
    ap.add_argument('--fmax', type=float, default=10000.0)
    ap.add_argument('--skip', type=float, default=1.0)
    ap.add_argument('--min-snr', type=float, default=10.0)
    args = ap.parse_args()

    sets = load_sets(args)
    results = []
    print("tryb   R wipera        C [nF]   RMS [dB]   taper")
    for rw_fixed in (None, 1e3, 3.3e3, 3.9e3, 4.7e3):
        for mode in ('free', 'pow1', 'pow2'):
            cap, rw, xf, rms, tail, free_pos = fit_mode(sets, args.pos_m, mode, rw_fixed)
            if mode == 'free':
                desc = ", ".join(f"x({p:.2f})={x:.3f}" for p, x in zip(free_pos, tail))
            else:
                desc = f"k={tail[0]:.2f}"
            rtxt = f"{rw:7.0f}" + (" (fit)" if rw_fixed is None else "      ")
            print(f"{mode:5s}  {rtxt}  {cap*1e9:7.2f}   {rms:7.2f}    {desc}")
            results.append((rms, mode, rw_fixed, cap, rw, xf))

    rms, mode, rw_fixed, cap, rw, xf = min(results, key=lambda t: t[0])
    print(f"\nNajlepszy: tryb {mode}, R wipera {rw:.0f}, C {cap*1e9:.2f} nF, RMS {rms:.2f} dB")
    print("Mapowanie galka -> x (od szyny):")
    for pos in (0.0, 0.25, args.pos_m, 0.75, 1.0):
        print(f"  pos {pos:4.2f} -> x = {xf(pos):.3f}")
    print("\nBlad na zestaw (dB RMS), najlepszy model:")
    xm = xf(args.pos_m)
    for tag, f, r, pos in sets:
        e = ratio_db(f, 'high', xf(pos), xm, cap, rw) - r
        print(f"  {tag:>4s}/mid: {np.sqrt(np.mean(e**2)):.2f}")


if __name__ == '__main__':
    main()