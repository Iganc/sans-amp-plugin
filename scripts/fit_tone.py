#!/usr/bin/env python3
"""
fit_tone.py - weryfikacja stopnia tonów HIGH / LOW (U3b) na podstawie pomiaru pluginu.

Topologia (wersja Baxandall; dolne konce potow ida na WYJSCIE opampa, nie na mase):
  szyna --C0(100n)-- zrodlo
  HIGH: szyna -10n-> [pot 100K: Th --Rpa-- W --Rpb-- Bh] , Bh -10n-> Vout , W -1K-> IN-
  LOW : szyna -10K-> [pot 100K: Tl --Rpa-- W --Rpb-- Bl] , Bl -10K-> Vout ,
        22n: Tl-W oraz W-Bl , W -10K-> IN-
  Oba wipery sumuja sie w IN- (masa wirtualna); sprzezenie: 100K || 300p.

Pomiar: ten sam bialy szum (niski poziom, DRIVE i CRUNCH na minimum), jedna galka zmieniana
(max / mid / min), druga zawsze w srodku. Renderuj osobno dla HIGH i LOW.
Domyslna mapa pozycji wipera odpowiada klonowi: HIGH ma xMid=0.37, LOW ma xMid=0.50.

Uzycie:
    python fit_tone.py high_max_-12.wav high_min_-12.wav --mid high_mid_-12.wav --pot high --plot
    python fit_tone.py low_max_-12.wav  low_min_-12.wav  --mid low_mid_-12.wav  --pot low  --plot
    (opcjonalnie --noise-a/--noise-b/--noise-m: rendery ciszy dla tych samych pozycji)
    python fit_tone.py --selftest

Wymaga fit_punch.py w tym samym folderze (korzysta z jego wczytywania i widm).
Skrypt probuje DWA kierunki galki i podaje, ktory pasuje lepiej.
"""
import argparse
import sys
import numpy as np
from scipy.optimize import least_squares

try:
    from fit_punch import measured_ratio, nearest_std
except ImportError:
    sys.exit("Brak fit_punch.py w tym folderze (potrzebny do wczytywania i widm).")

RP = 100e3
DEF = dict(Ch=10e-9, Cl=22e-9, C0=100e-9, Rhw=3.0e3, Rl1=10e3, Rl2=10e3, Rlw=10e3,
           Rf=100e3, Cf=300e-12)


def knob_to_x(pos, x_mid):
    """Mapa pozycji galki na x od strony szyny, zgodna z ToneStage::knobToX."""
    pos = min(max(pos, 0.0), 1.0)
    d0 = (x_mid - 1.0) / 0.5
    d1 = (0.0 - x_mid) / 0.5
    m1 = 2.0 * d0 * d1 / (d0 + d1) if d0 * d1 > 0.0 else 0.0
    m0 = 0.5 * (3.0 * d0 - d1)
    m2 = 0.5 * (3.0 * d1 - d0)
    if m0 * d0 <= 0.0:
        m0 = 0.0
    elif d0 * d1 <= 0.0 and abs(m0) > 3.0 * abs(d0):
        m0 = 3.0 * d0
    if m2 * d1 <= 0.0:
        m2 = 0.0
    elif d0 * d1 <= 0.0 and abs(m2) > 3.0 * abs(d1):
        m2 = 3.0 * d1

    h = 0.5
    first = pos < 0.5
    t = pos / h if first else (pos - 0.5) / h
    y0, y1 = ((1.0, x_mid) if first else (x_mid, 0.0))
    ma, mb = ((m0, m1) if first else (m1, m2))
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * y0
            + (t3 - 2 * t2 + t) * h * ma
            + (-2 * t3 + 3 * t2) * y1
            + (t3 - t2) * h * mb)


def tone_H(f, xh, xl, Ch=DEF['Ch'], Cl=DEF['Cl'], Rhw=DEF['Rhw'], Rlw=DEF['Rlw'],
           C0=DEF['C0'], Rl1=DEF['Rl1'], Rl2=DEF['Rl2'], Rf=DEF['Rf'], Cf=DEF['Cf']):
    """Zespolona odpowiedz stopnia (maly sygnal) = Vout / Vin.
    xh, xl = polozenie wipera od strony szyny (0..1)."""
    f = np.atleast_1d(np.asarray(f, dtype=float))
    s = 2j * np.pi * f
    n = len(f)
    xh = min(max(xh, 1e-4), 1 - 1e-4)
    xl = min(max(xl, 1e-4), 1 - 1e-4)

    # wezly: 0 szyna, 1 Th, 2 Bh, 3 Wh, 4 Tl, 5 Bl, 6 Wl, 7 Vout ; IN- = masa wirtualna
    Y = np.zeros((n, 8, 8), complex)
    b = np.zeros((n, 8), complex)

    def stamp(a, c, y):
        """Admitancja y miedzy wezlami a i c (c=None -> do masy)."""
        Y[:, a, a] += y
        if c is not None:
            Y[:, c, c] += y
            Y[:, a, c] -= y
            Y[:, c, a] -= y

    def to_out(a, y):
        """Galaz z wezla a do wyjscia opampa (wiersz 7 jest rownaniem opampa, nie ruszamy go)."""
        Y[:, a, a] += y
        Y[:, a, 7] -= y

    one = np.ones(n, complex)

    # zrodlo Vin = 1 przez C0 do szyny
    yc0 = s * C0
    Y[:, 0, 0] += yc0
    b[:, 0] += yc0

    # HIGH
    stamp(0, 1, s * Ch)
    stamp(1, 3, one / (xh * RP))
    stamp(3, 2, one / ((1 - xh) * RP))
    to_out(2, s * Ch)
    stamp(3, None, one / Rhw)

    # LOW
    stamp(0, 4, one / Rl1)
    stamp(4, 6, one / (xl * RP) + s * Cl)
    stamp(6, 5, one / ((1 - xl) * RP) + s * Cl)
    to_out(5, one / Rl2)
    stamp(6, None, one / Rlw)

    # KCL w IN-: prady z obu wiperow + sprzezenie = 0 (opamp ustala Vout)
    Y[:, 7, 3] += 1.0 / Rhw
    Y[:, 7, 6] += 1.0 / Rlw
    Y[:, 7, 7] += 1.0 / Rf + s * Cf

    V = np.linalg.solve(Y, b[..., None])[..., 0]
    return V[:, 7]


def ratio_db(f, pot, xa, xb, cap, rw):
    """Stosunek odpowiedzi (dB) miedzy pozycjami xa i xb galki 'pot'; druga galka w srodku."""
    def one(x):
        if pot == 'high':
            return tone_H(f, x, 0.5, Ch=cap, Rhw=rw)
        return tone_H(f, 0.5, x, Cl=cap, Rlw=rw)
    return 20 * np.log10(np.abs(one(xa)) / np.abs(one(xb)))


def fit(sets, pot, free_r):
    c0 = DEF['Ch'] if pot == 'high' else DEF['Cl']
    r0 = DEF['Rhw'] if pot == 'high' else DEF['Rlw']

    def resid(p):
        cap = 10 ** p[0]
        rw = 10 ** p[1] if free_r else r0
        return np.concatenate([ratio_db(f, pot, xa, xb, cap, rw) - r for f, r, xa, xb in sets])

    best = None
    for g in np.linspace(np.log10(c0 / 4), np.log10(c0 * 4), 7):
        p0 = [g, np.log10(r0)]
        lo = [-10.5, np.log10(r0) - 1.0]
        hi = [-6.5, np.log10(r0) + 1.0]
        if not free_r:
            lo[1], hi[1] = np.log10(r0) - 1e-9, np.log10(r0) + 1e-9
        sol = least_squares(resid, p0, bounds=(lo, hi))
        if best is None or sol.cost < best.cost:
            best = sol
    cap = 10 ** best.x[0]
    rw = 10 ** best.x[1] if free_r else r0
    return cap, rw, float(np.sqrt(np.mean(best.fun ** 2)))


def build_sets(args, flip):
    xmid = args.x_mid
    xof = (lambda p: 1.0 - knob_to_x(p, xmid)) if flip else (lambda p: knob_to_x(p, xmid))
    sets = []
    f, r, _ = measured_ratio(args.fileA, args.mid, args.fmin, args.fmax, args.skip,
                             args.noise_a, args.noise_m, args.min_snr)
    sets.append((f, r, xof(args.pos_a), xof(args.pos_m)))
    f, r, _ = measured_ratio(args.fileB, args.mid, args.fmin, args.fmax, args.skip,
                             args.noise_b, args.noise_m, args.min_snr)
    sets.append((f, r, xof(args.pos_b), xof(args.pos_m)))
    return sets


def diagnostics(sets, names, pot, cap, rw):
    print(f"\nDIAGNOSTYKA (C = {cap*1e9:.1f} nF, R wipera = {rw:.0f} ohm):")
    for (f, r, xa, xb), nm in zip(sets, names):
        m = ratio_db(f, pot, xa, xb, cap, rw)
        res = r - m
        print(f"  {nm}: RMS {np.sqrt(np.mean(res**2)):.2f} dB")
        for lo, hi in [(30, 150), (150, 600), (600, 2500), (2500, 10000)]:
            mk = (f >= lo) & (f < hi)
            if mk.any():
                print(f"      {lo:5d}-{hi:5d} Hz: pomiar sr. {np.mean(r[mk]):+6.1f} dB, model sr. {np.mean(m[mk]):+6.1f} dB, "
                      f"blad sr. {np.mean(res[mk]):+.2f} dB, RMS {np.sqrt(np.mean(res[mk]**2)):.2f}")
    print("  Jak czytac: blad ponizej ok. 1 dB = zgodnosc. Blad skupiony w jednym pasmie = zly element w tej czesci")
    print("  sieci (np. kondensator wlasciwy dla gory/dolu). Blad w calym pasmie = poziom albo rezystory.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fileA', nargs='?', help='nagranie z galka MAX')
    ap.add_argument('fileB', nargs='?', help='nagranie z galka MIN')
    ap.add_argument('--mid', help='nagranie z galka w srodku (odniesienie)')
    ap.add_argument('--pot', choices=['high', 'low'], help='ktora galka byla zmieniana')
    ap.add_argument('--pos-a', type=float, default=1.0)
    ap.add_argument('--pos-b', type=float, default=0.0)
    ap.add_argument('--pos-m', type=float, default=0.5)
    ap.add_argument('--fmin', type=float, default=30.0)
    ap.add_argument('--fmax', type=float, default=10000.0)
    ap.add_argument('--skip', type=float, default=1.0)
    ap.add_argument('--noise-a'); ap.add_argument('--noise-b'); ap.add_argument('--noise-m')
    ap.add_argument('--min-snr', type=float, default=10.0)
    ap.add_argument('--x-mid', type=float,
                    help='srodek mapy wipera x od strony szyny (domyslnie 0.37 dla HIGH, 0.50 dla LOW)')
    ap.add_argument('--rhw', type=float, default=3.0e3,
                    help='rezystancja wipera HIGH w ohmach (domyslnie 3000, zgodnie z ToneStage)')
    ap.add_argument('--free-r', action='store_true', help='dopasuj tez rezystor wipera (1K dla HIGH, 10K dla LOW)')
    ap.add_argument('--plot', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not (args.fileA and args.fileB and args.mid and args.pot):
        ap.error("podaj fileA (max), fileB (min), --mid i --pot high|low (albo --selftest)")

    if args.x_mid is None:
        args.x_mid = 0.37 if args.pot == 'high' else 0.5
    if not 0.0 < args.x_mid < 1.0:
        ap.error("--x-mid musi byc w zakresie 0..1")
    if args.rhw <= 0.0:
        ap.error("--rhw musi byc dodatnie")
    DEF['Rhw'] = args.rhw

    pot = args.pot
    res = {}
    for flip, label in [(False, "pos 1 = wiper przy SZYNIE (mapa ToneStage, xMid={:.2f})".format(args.x_mid)),
                        (True, "pos 1 = wiper przy MASIE (odwrocona mapa, xMid={:.2f})".format(args.x_mid))]:
        sets = build_sets(args, flip)
        if any(len(s[0]) < 10 for s in sets):
            sys.exit("Za malo pasm z wystarczajacym SNR - podnies poziom sygnalu.")
        cap, rw, rms = fit(sets, pot, free_r=False)
        capr, rwr, rmsr = fit(sets, pot, free_r=True)
        print(f"\n=== Odwzorowanie kierunku: {label} ===")
        print(f"  C = {cap*1e9:6.2f} nF (seria: {nearest_std(cap)*1e9:g} nF), R wipera = {rw:.0f} (ze schematu), blad RMS {rms:.2f} dB")
        print(f"  C = {capr*1e9:6.2f} nF, R wipera = {rwr:.0f} (dopasowany),            blad RMS {rmsr:.2f} dB")
        res[flip] = (rms, cap, rw, sets, rmsr, capr, rwr)

    flip = min(res, key=lambda k: res[k][0])
    rms, cap, rw, sets, rmsr, capr, rwr = res[flip]
    other = res[not flip][0]
    print("\n" + "=" * 60)
    print(f"Lepsze odwzorowanie: {'odwrocona mapa (pos 1 = wiper przy masie)' if flip else 'mapa ToneStage (pos 1 = wiper przy szynie)'}"
          f"  (RMS {rms:.2f} dB vs {other:.2f} dB{' - roznica mala, kierunek NIEPEWNY' if abs(other-rms) < 0.5 else ''})")
    diagnostics(sets, ['max/mid', 'min/mid'], pot, cap, rw)

    if args.plot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            print("Brak matplotlib - pomijam wykres.")
            return
        fig, ax = plt.subplots(figsize=(8, 5))
        for (f, r, xa, xb), nm, col in zip(sets, ['max/mid', 'min/mid'], ['C0', 'C1']):
            ax.semilogx(f, r, '.', color=col, ms=4, label=f'pomiar {nm}')
            ax.semilogx(f, ratio_db(f, pot, xa, xb, cap, rw), '-', color=col, lw=2, label=f'model {nm}')
        ax.set_xlabel('Hz'); ax.set_ylabel('dB'); ax.grid(True, which='both', alpha=0.3)
        ax.legend(); ax.set_title(f'{pot.upper()}: pomiar vs model')
        out = f'tone_{pot}_fit.png'
        fig.tight_layout(); fig.savefig(out, dpi=130)
        print(f"Zapisano {out}")


def selftest():
    rng = np.random.default_rng(2)
    f = np.geomspace(30, 10000, 90)
    for pot, trueC in (('high', 15e-9), ('low', 33e-9)):
        sets = []
        for xa in (0.0, 1.0):
            r = ratio_db(f, pot, xa, 0.5, trueC, DEF['Rhw'] if pot == 'high' else DEF['Rlw']) + rng.normal(0, 0.3, len(f))
            sets.append((f, r, xa, 0.5))
        cap, rw, rms = fit(sets, pot, free_r=False)
        print(f"{pot}: prawda {trueC*1e9:.0f} nF -> dopasowano {cap*1e9:.1f} nF (RMS {rms:.2f} dB)")


if __name__ == '__main__':
    main()