#!/usr/bin/env python3
"""
fit_buzz.py - odczytanie C1 = C2 stopnia BUZZ (i sprawdzenie rezystorow) z pomiaru pluginu.

Pomiar: ten sam bialy szum (niski poziom, zeby diody nie przewodzily) przepuszczony przez
plugin dwa razy, zmieniasz TYLKO jedna galke (BUZZ max / BUZZ min). Reszta toru jest liniowa
i skraca sie w stosunku widm - zostaje odpowiedz samego stopnia.

Uzycie:
    python fit_buzz.py buzz_max.wav buzz_min.wav --plot
    python fit_buzz.py gain_max.wav gain_min.wav --mode gain

Jesli plugin dodaje wlasny szum (zalezny od galki), wyrenderuj tez CISZE (bez wejscia) dla obu pozycji
galki i podaj: --noise-a silence_max.wav --noise-b silence_min.wav (szum zostanie odjety).

Opcje:
    --pos-a / --pos-b   pozycja galki w pierwszym / drugim pliku (0..1, domyslnie 1 i 0)
    --fmin / --fmax     zakres dopasowania w Hz (domyslnie 40..10000)
    --skip              ile sekund od poczatku odrzucic (stan przejsciowy), domyslnie 1.0

Wymaga: numpy, scipy (opcjonalnie soundfile i matplotlib).
"""
import argparse
import sys
import numpy as np
from scipy.signal import welch
from scipy.optimize import minimize_scalar, least_squares

# ---------------------------------------------------------------------------
# Uklad (wartosci ze schematu - zmien, jesli pomiar pokaze cos innego)
# ---------------------------------------------------------------------------
BUZZ_R1 = BUZZ_R2 = BUZZ_R3 = 10e3     # wejscie, wyjscie->pot, wiper->IN-
BUZZ_RPOT = 100e3
BUZZ_RF = 100e3

GAIN_R1, GAIN_R2, GAIN_R3 = 1e3, 47e3, 1e3
GAIN_RPOT = 100e3
GAIN_RF = 100e3

STD_CAPS = [1e-9, 1.5e-9, 2.2e-9, 3.3e-9, 4.7e-9, 6.8e-9, 10e-9, 15e-9, 22e-9,
            33e-9, 47e-9, 68e-9, 100e-9]


def buzz_H(f, buzz, C):
    """Zespolona odpowiedz stopnia BUZZ (maly sygnal, bez Cf). buzz=1: wiper przy wejsciu."""
    s = 2j * np.pi * np.asarray(f, dtype=float)
    x = 1.0 - buzz
    Rpa, Rpb = x * BUZZ_RPOT, (1.0 - x) * BUZZ_RPOT
    Na = (BUZZ_R1 + Rpa) + s * BUZZ_R1 * Rpa * C
    Da = 1.0 + s * Rpa * C
    Nb = (BUZZ_R2 + Rpb) + s * BUZZ_R2 * Rpb * C
    Db = 1.0 + s * Rpb * C
    num = BUZZ_RF * Nb * Da
    den = (BUZZ_RF + BUZZ_R3) * Na * Db + Na * Nb + BUZZ_R3 * Nb * Da
    return num / den


def gain_G(gain):
    """Wzmocnienie liniowe stopnia GAIN (bez kondensatorow)."""
    x = 1.0 - gain
    Ra = GAIN_R1 + x * GAIN_RPOT
    Rb = GAIN_R2 + (1.0 - x) * GAIN_RPOT
    D = 1.0 + GAIN_R3 / Ra + GAIN_R3 / Rb
    g = 1.0 / Rb + D / GAIN_RF
    return 1.0 / (Ra * g)


def ratio_db_model(f, C, pa, pb):
    return 20 * np.log10(np.abs(buzz_H(f, pa, C)) / np.abs(buzz_H(f, pb, C)))


# ---------------------------------------------------------------------------
# Wczytanie i widma
# ---------------------------------------------------------------------------
def load(path):
    try:
        import soundfile as sf
        x, fs = sf.read(path, always_2d=True)
    except ImportError:
        from scipy.io import wavfile
        fs, x = wavfile.read(path)
        if x.dtype.kind == 'i':
            x = x / float(np.iinfo(x.dtype).max + 1)
        elif x.dtype.kind == 'u':
            x = (x.astype(float) - 128.0) / 128.0
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            x = x[:, None]
    return x.mean(axis=1), fs


def band_powers(x, fs, edges, skip):
    x = x[int(skip * fs):]
    nper = 1 << 15
    if len(x) < 4 * nper:
        print(f"UWAGA: nagranie krotkie ({len(x)/fs:.1f} s) - wynik bedzie szumny, "
              f"zrob dluzsze (30 s+).", file=sys.stderr)
        nper = max(1024, 1 << int(np.log2(max(len(x) // 4, 1024))))
    f, p = welch(x, fs=fs, window='hann', nperseg=nper, noverlap=nper // 2)
    out = np.full(len(edges) - 1, np.nan)
    for i in range(len(edges) - 1):
        m = (f >= edges[i]) & (f < edges[i + 1])
        if m.any():
            out[i] = p[m].mean()
    return out


def measured_ratio(fileA, fileB, fmin, fmax, skip, noiseA=None, noiseB=None,
                   min_snr=10.0, nbins=100):
    """Stosunek widm A/B w dB. Z plikami szumu wlasnego pluginu (render ciszy dla
    tych samych ustawien) odejmuje jego moc i odrzuca pasma o SNR < min_snr."""
    a, fsa = load(fileA)
    b, fsb = load(fileB)
    if fsa != fsb:
        sys.exit(f"Rozne czestotliwosci probkowania: {fsa} vs {fsb}")
    fmax = min(fmax, 0.45 * fsa)
    edges = np.geomspace(fmin, fmax, nbins + 1)
    pa = band_powers(a, fsa, edges, skip)
    pb = band_powers(b, fsa, edges, skip)
    good = np.ones(len(pa), dtype=bool)
    info = {'dropped': 0, 'snr_lo': None, 'snr_hi': None}
    if noiseA and noiseB:
        na, fsn = load(noiseA)
        nb, fsn2 = load(noiseB)
        if fsn != fsa or fsn2 != fsa:
            sys.exit("Pliki szumu maja inna czestotliwosc probkowania niz nagrania")
        qa = band_powers(na, fsa, edges, skip)
        qb = band_powers(nb, fsa, edges, skip)
        with np.errstate(divide='ignore', invalid='ignore'):
            snr_a = 10 * np.log10(pa / qa)
            snr_b = 10 * np.log10(pb / qb)
        good = (snr_a >= min_snr) & (snr_b >= min_snr)
        info['snr_lo'] = (float(np.nanmin([snr_a[:10].mean(), snr_b[:10].mean()])))
        info['snr_hi'] = (float(np.nanmin([snr_a[-10:].mean(), snr_b[-10:].mean()])))
        pa = pa - qa
        pb = pb - qb
    centers = np.sqrt(edges[:-1] * edges[1:])
    ok = np.isfinite(pa) & np.isfinite(pb) & (pa > 0) & (pb > 0) & good
    info['dropped'] = int(len(pa) - ok.sum())
    return centers[ok], 10 * np.log10(pa[ok] / pb[ok]), info    # stosunek mocy = |H_a|^2/|H_b|^2


def mean_in(f, y, lo, hi):
    m = (f >= lo) & (f <= hi)
    return float(np.mean(y[m])) if m.any() else float('nan')


def nearest_std(C):
    return min(STD_CAPS, key=lambda c: abs(np.log(c / C)))


# ---------------------------------------------------------------------------
# Tryby
# ---------------------------------------------------------------------------
def run_buzz(args):
    f, r, info = measured_ratio(args.fileA, args.fileB, args.fmin, args.fmax, args.skip,
                                args.noise_a, args.noise_b, args.min_snr)
    pa, pb = args.pos_a, args.pos_b
    if len(f) < 10:
        sys.exit("Za malo pasm z wystarczajacym SNR - podnies poziom sygnalu.")

    # (a) pozycje zalozone, dopasowanie samego C
    def cost(logC):
        return np.sqrt(np.mean((ratio_db_model(f, 10 ** logC, pa, pb) - r) ** 2))

    grid = np.linspace(np.log10(0.5e-9), np.log10(500e-9), 200)
    g0 = grid[np.argmin([cost(g) for g in grid])]
    res = minimize_scalar(cost, bounds=(g0 - 0.1, g0 + 0.1), method='bounded')
    C_a, rms_a = 10 ** res.x, res.fun

    # (b) C + pozycje galek
    def resid(p):
        return ratio_db_model(f, 10 ** p[0], p[1], p[2]) - r

    sol = least_squares(resid, [np.log10(C_a), pa, pb],
                        bounds=([-9.7, 0.0, 0.0], [-6.3, 1.0, 1.0]))
    C_b, pa_b, pb_b = 10 ** sol.x[0], sol.x[1], sol.x[2]
    rms_b = np.sqrt(np.mean(sol.fun ** 2))

    lf_meas = mean_in(f, r, args.fmin, args.fmin * 2.5)
    hf_meas = mean_in(f, r, 5000, args.fmax)
    mlow = (f >= args.fmin) & (f <= args.fmin * 2.5)
    lf_model = float(np.mean(ratio_db_model(f[mlow], C_a, pa, pb))) if mlow.any() else float('nan')
    fmt = lambda v: 'brak wiarygodnych pasm' if not np.isfinite(v) else f"{v:+.1f} dB"

    print(f"\nZakres: {f[0]:.0f}..{f[-1]:.0f} Hz, {len(f)} pasm")
    print(f"Stosunek na dole, {args.fmin:.0f}-{args.fmin*2.5:.0f} Hz (zmierzony / model z dopasowanym C): "
          f"{fmt(lf_meas)} / {fmt(lf_model)}")
    print("  (plateau dla krancow pota to +32.9 dB, ale przy duzym C osiaga sie je dopiero nizej niz fmin)")
    print(f"Stosunek na gorze, 5-{args.fmax/1000:.0f} kHz (zmierzony): {fmt(hf_meas)}   (oczekiwane ok. 0 dB)")
    if args.noise_a and args.noise_b:
        print(f"Szum wlasny pluginu odjety. Odrzucono {info['dropped']} pasm z SNR < {args.min_snr:.0f} dB; "
              f"SNR na dole/gorze: {info['snr_lo']:.0f} / {info['snr_hi']:.0f} dB")
    if lf_meas > 33.5 or abs(hf_meas) > 3.0:
        print("\n!!! PODEJRZANE: stosunek na dole > 33 dB albo na gorze daleko od 0 dB. W modelu tego nie da sie")
        print("    uzyskac zadnym C - na wyjsciu jest cos poza sygnalem (szum wlasny pluginu przy zbyt cichym wejsciu,")
        print("    albo nieliniowosc przy zbyt glosnym). Podnies poziom albo uzyj --noise-a/--noise-b (render ciszy).")
    print(f"\n(a) pozycje zalozone:   C = {C_a*1e9:6.2f} nF  (najblizsza seria: {nearest_std(C_a)*1e9:g} nF),  "
          f"blad RMS {rms_a:.2f} dB")
    print(f"(b) pozycje swobodne:   C = {C_b*1e9:6.2f} nF,  buzz_A = {pa_b:.2f}, buzz_B = {pb_b:.2f},  "
          f"blad RMS {rms_b:.2f} dB")
    print("\nJak czytac: blad RMS ponizej ok. 1 dB = model pasuje. Jesli (a) ma duzy blad, a (b) maly,")
    print("galki pluginu nie siegaja koncow pota. Jesli oba duze - sprawdz poziom (liniowosc) albo")
    print("rezystory (poziom na dole inny niz +32.9 dB przy skrajnych pozycjach).")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            print("Brak matplotlib - pomijam wykres.")
            return
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.semilogx(f, r, 'k.', ms=4, label='pomiar')
        for C, st in [(4.7e-9, ':'), (10e-9, '--'), (22e-9, '-.')]:
            ax.semilogx(f, ratio_db_model(f, C, pa, pb), st, label=f'model {C*1e9:g}n')
        ax.semilogx(f, ratio_db_model(f, C_a, pa, pb), 'r-', lw=2, label=f'dopasowanie {C_a*1e9:.1f}n')
        ax.set_xlabel('Hz'); ax.set_ylabel('dB (A/B)'); ax.grid(True, which='both', alpha=0.3)
        ax.legend(); ax.set_title('Stosunek odpowiedzi BUZZ')
        fig.tight_layout(); fig.savefig('buzz_fit.png', dpi=130)
        print("Zapisano buzz_fit.png")


def run_gain(args):
    f, r, info = measured_ratio(args.fileA, args.fileB, args.fmin, args.fmax, args.skip,
                                args.noise_a, args.noise_b, args.min_snr)
    expected = 20 * np.log10(gain_G(args.pos_a) / gain_G(args.pos_b))
    band = (f >= 100) & (f <= 5000)
    print(f"\nStosunek GAIN {args.pos_a:.2f} / {args.pos_b:.2f}:")
    print(f"  zmierzony (100 Hz - 5 kHz): srednia {np.mean(r[band]):+.1f} dB, "
          f"rozrzut {np.ptp(r[band]):.1f} dB (powinien byc plaski)")
    print(f"  model (1K / 1K / 47K):      {expected:+.1f} dB")
    print("Roznica w poziomie = ktorys z rezystorow 1K/47K wyglada inaczej. "
          "Nieplaski ksztalt = w torze sa kondensatory (albo nieliniowosc).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fileA', help='nagranie z galka w pozycji A (np. BUZZ max)')
    ap.add_argument('fileB', help='nagranie z galka w pozycji B (np. BUZZ min)')
    ap.add_argument('--mode', choices=['buzz', 'gain'], default='buzz')
    ap.add_argument('--pos-a', type=float, default=1.0)
    ap.add_argument('--pos-b', type=float, default=0.0)
    ap.add_argument('--fmin', type=float, default=40.0)
    ap.add_argument('--fmax', type=float, default=10000.0)
    ap.add_argument('--skip', type=float, default=1.0)
    ap.add_argument('--noise-a', help='render CISZY (bez wejscia) z galka w pozycji A - do odjecia szumu wlasnego')
    ap.add_argument('--noise-b', help='render CISZY z galka w pozycji B')
    ap.add_argument('--min-snr', type=float, default=10.0, help='minimalny SNR pasma w dB (z plikami szumu)')
    ap.add_argument('--plot', action='store_true')
    args = ap.parse_args()
    (run_buzz if args.mode == 'buzz' else run_gain)(args)


if __name__ == '__main__':
    main()