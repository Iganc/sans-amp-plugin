#!/usr/bin/env python3
"""
fit_punch.py - weryfikacja stopnia PUNCH (U3a) i odczytanie C1, C2 z pomiaru pluginu.

Topologia (odczyt ze szkicu av500, ideal op-amp):
    B --100K--------------------------------> IN-          (stala sciezka)
    B --1K--> T --[pot 100K]--> Bt --1K--> OUT
              |  22n (C1) rownolegle do calego pota  |
    wiper W --22n (C2)--> IN-
    sprzezenie: 100K || 300p (diody pomijamy - maly sygnal)

Wynik to korektor srodka pasma (ok. 700 Hz): skrajne pozycje = boost / ciecie, srodek = plasko.

Pomiar: ten sam bialy szum, NISKI poziom (diody D7/D8 nie moga przewodzic - przy boostcie
+25 dB ograniczaja juz od okolo 0.6 V na wyjsciu U3a), plugin renderowany 3 razy, zmieniasz
TYLKO galke PUNCH: max, srodek, min. Zalecane: wszystkie trzy, bo srodek jest plaski i sluzy
jako odniesienie (A/M i B/M to wprost odpowiedz stopnia). Same A i B wystarczy, ale ciecie
-28 dB bedzie tonac w szumie wlasnym pluginu.

Uzycie:
    python fit_punch.py punch_max.wav punch_min.wav --mid punch_mid.wav --plot
    python fit_punch.py punch_max.wav punch_min.wav --mid punch_mid.wav \
        --noise-a sil_max.wav --noise-b sil_min.wav --noise-m sil_mid.wav
    python fit_punch.py --selftest

Skrypt probuje DWA odwzorowania kierunku galki (pozycja 1 = wiper przy wejsciu albo przy wyjsciu)
i podaje, ktore pasuje lepiej - to odpowiada na pytanie o kierunek obrotu.

Wymaga: numpy, scipy (opcjonalnie soundfile i matplotlib).
"""
import argparse
import sys
import numpy as np
from scipy.signal import welch
from scipy.optimize import least_squares

# ---------------------------------------------------------------------------
# Uklad (wartosci z odczytu schematu - zmien, jesli pomiar pokaze cos innego)
# ---------------------------------------------------------------------------
P_R = 100e3        # pot
P_RA = 1e3         # B -> gorny koniec pota
P_RB = 1e3         # dolny koniec pota -> wyjscie
P_R1 = 100e3       # B -> IN- (stala)
P_RF = 100e3
P_CF = 300e-12
C_NOM = 22e-9

STD_CAPS = [1e-9, 1.5e-9, 2.2e-9, 3.3e-9, 4.7e-9, 6.8e-9, 10e-9, 15e-9, 22e-9,
            33e-9, 47e-9, 68e-9, 100e-9]


def punch_H(f, x, C1=C_NOM, C2=C_NOM):
    """Zespolona odpowiedz PUNCH (maly sygnal). x = polozenie wipera od strony wejscia (0..1):
    x=0 wiper przy gornym koncu (od 1K z wejscia), x=1 przy dolnym (od 1K do wyjscia)."""
    f = np.atleast_1d(np.asarray(f, dtype=float))
    s = 2j * np.pi * f
    x = float(np.clip(x, 1e-4, 1 - 1e-4))
    g1 = 1.0 / (x * P_R)
    g2 = 1.0 / ((1.0 - x) * P_R)
    ga, gb = 1.0 / P_RA, 1.0 / P_RB
    yf = 1.0 / P_RF + s * P_CF
    n = len(f)
    A = np.zeros((n, 4, 4), complex)
    b = np.zeros((n, 4), complex)
    # niewiadome: T, Bt, W, Vout ; Vin = 1 ; IN- = 0 (idealny op-amp)
    A[:, 0, 0] = ga + g1 + s * C1; A[:, 0, 1] = -s * C1; A[:, 0, 2] = -g1; b[:, 0] = ga
    A[:, 1, 0] = -s * C1; A[:, 1, 1] = g2 + s * C1 + gb; A[:, 1, 2] = -g2; A[:, 1, 3] = -gb
    A[:, 2, 0] = -g1; A[:, 2, 1] = -g2; A[:, 2, 2] = g1 + g2 + s * C2
    A[:, 3, 2] = s * C2; A[:, 3, 3] = yf; b[:, 3] = -1.0 / P_R1
    return np.linalg.solve(A, b[..., None])[:, 3, 0]


def ratio_db_model(f, xa, xb, C1, C2):
    return 20 * np.log10(np.abs(punch_H(f, xa, C1, C2)) / np.abs(punch_H(f, xb, C1, C2)))


# ---------------------------------------------------------------------------
# Wczytanie i widma (jak w fit_buzz.py)
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
    """Stosunek widm A/B w dB (moc). Z plikami szumu odejmuje szum wlasny pluginu
    i odrzuca pasma o SNR < min_snr."""
    a, fsa = load(fileA)
    b, fsb = load(fileB)
    if fsa != fsb:
        sys.exit(f"Rozne czestotliwosci probkowania: {fsa} vs {fsb}")
    fmax = min(fmax, 0.45 * fsa)
    edges = np.geomspace(fmin, fmax, nbins + 1)
    pa = band_powers(a, fsa, edges, skip)
    pb = band_powers(b, fsa, edges, skip)
    good = np.ones(len(pa), dtype=bool)
    info = {'dropped': 0}
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
        pa = pa - qa
        pb = pb - qb
    centers = np.sqrt(edges[:-1] * edges[1:])
    ok = np.isfinite(pa) & np.isfinite(pb) & (pa > 0) & (pb > 0) & good
    info['dropped'] = int(len(pa) - ok.sum())
    return centers[ok], 10 * np.log10(pa[ok] / pb[ok]), info


def nearest_std(C):
    return min(STD_CAPS, key=lambda c: abs(np.log(c / C)))


# ---------------------------------------------------------------------------
# Dopasowanie
# ---------------------------------------------------------------------------
def fit(datasets, tied):
    """datasets: lista (f, r_dB, xa, xb). Zwraca (C1, C2, rms)."""
    def model(p):
        C1 = 10 ** p[0]
        C2 = C1 if tied else 10 ** p[1]
        return np.concatenate([ratio_db_model(f, xa, xb, C1, C2) - r
                               for f, r, xa, xb in datasets])

    best = None
    for g in np.linspace(np.log10(3e-9), np.log10(150e-9), 9):      # wiele startow
        p0 = [g] if tied else [g, g]
        lo, hi = ([-9.7] * len(p0)), ([-6.5] * len(p0))
        sol = least_squares(model, p0, bounds=(lo, hi))
        if best is None or sol.cost < best.cost:
            best = sol
    C1 = 10 ** best.x[0]
    C2 = C1 if tied else 10 ** best.x[1]
    rms = float(np.sqrt(np.mean(best.fun ** 2)))
    return C1, C2, rms


def build_datasets(args, flip):
    """flip=False: x = 1 - pos ; flip=True: x = pos."""
    xof = (lambda p: p) if flip else (lambda p: 1.0 - p)
    sets = []
    if args.mid:
        f, r, _ = measured_ratio(args.fileA, args.mid, args.fmin, args.fmax, args.skip,
                                 args.noise_a, args.noise_m, args.min_snr)
        sets.append((f, r, xof(args.pos_a), xof(args.pos_m)))
        f, r, _ = measured_ratio(args.fileB, args.mid, args.fmin, args.fmax, args.skip,
                                 args.noise_b, args.noise_m, args.min_snr)
        sets.append((f, r, xof(args.pos_b), xof(args.pos_m)))
    else:
        f, r, _ = measured_ratio(args.fileA, args.fileB, args.fmin, args.fmax, args.skip,
                                 args.noise_a, args.noise_b, args.min_snr)
        sets.append((f, r, xof(args.pos_a), xof(args.pos_b)))
    return sets


def peak_info(xv, C1, C2):
    ff = np.geomspace(40, 10000, 600)
    m = 20 * np.log10(np.abs(punch_H(ff, xv, C1, C2)))
    i = int(np.argmax(np.abs(m)))
    return m[i], ff[i]


def report(sets, label, flip, C1t, C1f, C2f, rms_t, rms_f):
    xof = (lambda p: p) if flip else (lambda p: 1.0 - p)
    print(f"\n=== Odwzorowanie kierunku: {label} ===")
    print(f"  C1 = C2 (wspolne):  {C1t*1e9:6.2f} nF (seria: {nearest_std(C1t)*1e9:g} nF), blad RMS {rms_t:.2f} dB")
    print(f"  C1, C2 osobno:      C1 = {C1f*1e9:6.2f} nF, C2 = {C2f*1e9:6.2f} nF,        blad RMS {rms_f:.2f} dB")
    return xof


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fileA', nargs='?', help='nagranie z PUNCH max')
    ap.add_argument('fileB', nargs='?', help='nagranie z PUNCH min')
    ap.add_argument('--mid', help='nagranie z PUNCH w srodku (odniesienie, zalecane)')
    ap.add_argument('--pos-a', type=float, default=1.0)
    ap.add_argument('--pos-b', type=float, default=0.0)
    ap.add_argument('--pos-m', type=float, default=0.5)
    ap.add_argument('--fmin', type=float, default=40.0)
    ap.add_argument('--fmax', type=float, default=10000.0)
    ap.add_argument('--skip', type=float, default=1.0)
    ap.add_argument('--noise-a', help='render CISZY z PUNCH w pozycji A')
    ap.add_argument('--noise-b', help='render CISZY z PUNCH w pozycji B')
    ap.add_argument('--noise-m', help='render CISZY z PUNCH w pozycji srodkowej')
    ap.add_argument('--min-snr', type=float, default=10.0)
    ap.add_argument('--plot', action='store_true')
    ap.add_argument('--selftest', action='store_true', help='test na danych syntetycznych')
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.fileA or not args.fileB:
        ap.error("podaj fileA (max) i fileB (min), albo uzyj --selftest")

    results = {}
    for flip, label in [(False, "pos 1 = wiper przy WEJSCIU (x = 1 - pos)"),
                        (True, "pos 1 = wiper przy WYJSCIU  (x = pos)")]:
        sets = build_datasets(args, flip)
        if any(len(s[0]) < 10 for s in sets):
            sys.exit("Za malo pasm z wystarczajacym SNR - podnies poziom sygnalu.")
        C1t, _, rms_t = fit(sets, tied=True)
        C1f, C2f, rms_f = fit(sets, tied=False)
        xof = report(sets, label, flip, C1t, C1f, C2f, rms_t, rms_f)
        results[flip] = (rms_t, C1t, C1f, C2f, sets, xof)

    flip = min(results, key=lambda k: results[k][0])
    rms_t, C1t, C1f, C2f, sets, xof = results[flip]
    other = results[not flip][0]
    print("\n" + "=" * 60)
    print(f"Lepsze odwzorowanie: {'x = pos (pos 1 = wiper przy wyjsciu)' if flip else 'x = 1 - pos (pos 1 = wiper przy wejsciu)'}")
    print(f"  (RMS {rms_t:.2f} dB vs {other:.2f} dB dla drugiego"
          f"{' - roznica mala, kierunek NIEPEWNY' if abs(other - rms_t) < 0.5 else ''})")
    for name, p in [('max', args.pos_a), ('mid', args.pos_m), ('min', args.pos_b)]:
        pk, fk = peak_info(xof(p), C1t, C1t)
        print(f"  Model PUNCH {name}: szczyt {pk:+.1f} dB przy {fk:.0f} Hz")
    print("\nJak czytac: blad RMS ponizej ok. 1 dB = model pasuje (topologia i rezystory OK).")
    print("Duzy blad w obu odwzorowaniach = zly odczyt rezystorow/topologii, albo diody ograniczaja")
    print("(zmniejsz poziom wejscia). Maksimum pomierzone powinno byc ok. +25 dB, minimum ok. -28 dB")
    print("wzgledem srodka, przy 600-800 Hz.")

    diagnostics(sets, ['max/mid', 'min/mid'] if args.mid else ['max/min'], C1t)

    if args.plot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            print("Brak matplotlib - pomijam wykres.")
            return
        fig, ax = plt.subplots(figsize=(8, 5))
        for (f, r, xa, xb), nm, col in zip(sets, ['max/mid', 'min/mid'] if args.mid else ['max/min'], ['C0', 'C1']):
            ax.semilogx(f, r, '.', color=col, ms=4, label=f'pomiar {nm}')
            ax.semilogx(f, ratio_db_model(f, xa, xb, C1t, C1t), '-', color=col, lw=2,
                        label=f'model {nm} ({C1t*1e9:.1f}n)')
        ax.set_xlabel('Hz'); ax.set_ylabel('dB'); ax.grid(True, which='both', alpha=0.3)
        ax.legend(); ax.set_title('PUNCH: pomiar vs model')
        fig.tight_layout(); fig.savefig('punch_fit.png', dpi=130)
        print("Zapisano punch_fit.png")


def diagnostics(sets, names, C):
    """Rozbicie bledu: RMS na zestaw, zmierzony vs modelowy szczyt, blad sredni w pasmach."""
    print("\nDIAGNOSTYKA (model ze wspolnym C = %.1f nF):" % (C * 1e9))
    for (f, r, xa, xb), nm in zip(sets, names):
        m = ratio_db_model(f, xa, xb, C, C)
        res = r - m
        im, ik = int(np.argmax(np.abs(r))), int(np.argmax(np.abs(m)))
        print(f"  {nm}: RMS {np.sqrt(np.mean(res**2)):.2f} dB | szczyt pomiar {r[im]:+.1f} dB @ {f[im]:.0f} Hz"
              f" | model {m[ik]:+.1f} dB @ {f[ik]:.0f} Hz")
        for lo, hi in [(40, 200), (200, 2000), (2000, 10000)]:
            mk = (f >= lo) & (f < hi)
            if mk.any():
                print(f"      {lo:5d}-{hi:5d} Hz: blad sredni {np.mean(res[mk]):+.2f} dB (pomiar - model), "
                      f"RMS {np.sqrt(np.mean(res[mk]**2)):.2f}, pasm {mk.sum()}")
    print("  Wskazowka: pomiar < model na szczycie boostu = ograniczanie diodami (zmniejsz poziom);")
    print("  duzy blad tylko przy cieciu = szum wlasny (uzyj plikow ciszy); blad rowny w calym pasmie = poziom/rezystory.")


def selftest():
    rng = np.random.default_rng(1)
    f = np.geomspace(40, 10000, 80)
    for trueC in (22e-9, 33e-9):
        xs = {'a': 0.0, 'b': 1.0, 'm': 0.5}          # x = 1 - pos, pos = 1 / 0 / 0.5
        sets = []
        for k in ('a', 'b'):
            r = ratio_db_model(f, xs[k], xs['m'], trueC, trueC) + rng.normal(0, 0.3, len(f))
            sets.append((f, r, xs[k], xs['m']))
        C1, C2, rms = fit(sets, tied=True)
        C1f, C2f, rmsf = fit(sets, tied=False)
        print(f"prawda {trueC*1e9:.0f} nF -> wspolne {C1*1e9:.1f} nF (RMS {rms:.2f}), "
              f"osobno {C1f*1e9:.1f}/{C2f*1e9:.1f} nF (RMS {rmsf:.2f})")


if __name__ == '__main__':
    main()