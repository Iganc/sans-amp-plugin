#pragma once
#include <cmath>
#include <algorithm>

// Stopień tonów HIGH / LOW (U3b), odczyt i dopasowanie: fit_tone.py (model Baxandalla).
//
//   szyna <-C0(100n)- wejście
//   HIGH: szyna -Ch(10n)- Th [pot: Th --Rpa-- Wh --Rpb-- Bh] Bh -Ch(10n)- WYJŚCIE U3b,
//         Wh -Rhw-> IN-
//   LOW : szyna -Rl1(10K)- Tl [pot: Tl --Rpa||Cl-- Wl --Rpb||Cl-- Bl] Bl -Rl2(10K)- WYJŚCIE U3b,
//         Wl -Rlw(10K)-> IN-
//   sprzężenie: Rf(100K) || Cf(300p), IN- = masa wirtualna.
//
// Sieć ma 6 kondensatorów (do 6. rzędu), więc zamiast jednego wielomianu IIR (źle uwarunkowanego
// przy biegunach rzędu dziesiątek Hz) liczymy ją wprost: równania węzłowe (MNA), kondensatory
// jako modele towarzyszące reguły trapezów (to samo co transformata biliniowa w innych stopniach).
// Macierz 8x8 jest odwracana tylko wtedy, gdy zmieni się gałka HIGH/LOW lub sample rate,
// a w każdej próbce jest jedno mnożenie macierz x wektor.
//
// Znak: stopień odwraca fazę; podobnie jak w BUZZ/PUNCH inwersja jest pominięta (zwracamy -Vout).
struct ToneStage
{
    // Wartości elementów (HIGH: C ~10 nF, R wipera ~3k z dopasowania; LOW: 22 nF, 10k)
    double Ch  = 10e-9;
    double Cl  = 22e-9;
    double C0  = 100e-9;
    double Rhw = 3.0e3;     // niepewne (dopasowanie 2,4k..3,75k, schemat: do sprawdzenia)
    double Rl1 = 10e3;
    double Rl2 = 10e3;
    double Rlw = 10e3;
    double Rf  = 100e3;
    double Cf  = 300e-12;
    double Rp  = 100e3;

    // Pozycja wipera od strony szyny (0..1). Gałka 1 (max) = 0, gałka 0 (min) = 1.
    // Mapowanie gałka -> x patrz knobToX().
    void prepare (double sampleRate)
    {
        fs = sampleRate;
        reset();
        dirty = true;
        setPositions (xh, xl);
    }

    void reset()
    {
        for (int k = 0; k < 6; ++k) { vc[k] = 0.0; ic[k] = 0.0; }
    }

    void setPositions (double newXh, double newXl)
    {
        newXh = std::min (std::max (newXh, 1e-4), 1.0 - 1e-4);
        newXl = std::min (std::max (newXl, 1e-4), 1.0 - 1e-4);

        if (! dirty && newXh == xh && newXl == xl)
            return;

        xh = newXh;
        xl = newXl;
        dirty = false;
        rebuild();
    }

    float process (float in)
    {
        const double vin = in;

        double b[N];
        for (int i = 0; i < N; ++i) b[i] = 0.0;

        double ieq[6];
        for (int k = 0; k < 6; ++k)
            ieq[k] = g[k] * vc[k] + ic[k];

        // C0: źródło -> węzeł 0
        b[0] += g[0] * vin - ieq[0];
        // Ch1: 0 -> 1
        b[0] += ieq[1];  b[1] -= ieq[1];
        // Ch2: 2 -> wyjście (tylko wiersz 2)
        b[2] += ieq[2];
        // Cl1: 4 -> 6
        b[4] += ieq[3];  b[6] -= ieq[3];
        // Cl2: 6 -> 5
        b[6] += ieq[4];  b[5] -= ieq[4];
        // Cf: wyjście -> masa
        b[7] += ieq[5];

        double v[N];
        for (int i = 0; i < N; ++i)
        {
            double s = 0.0;
            for (int j = 0; j < N; ++j)
                s += inv[i][j] * b[j];
            v[i] = s;
        }

        // aktualizacja stanów kondensatorów: vc = Va - Vb, i = g*vc - ieq
        const double nvc[6] = { vin - v[0], v[0] - v[1], v[2] - v[7],
                                v[4] - v[6], v[6] - v[5], v[7] };
        for (int k = 0; k < 6; ++k)
        {
            vc[k] = nvc[k];
            ic[k] = g[k] * nvc[k] - ieq[k];
        }

        return (float) (-v[7]);
    }

    // Mapowanie pozycji gałki (0..1) na x (od szyny): monotoniczny sześcian Hermite'a przez
    // trzy punkty (0 -> 1, 0,5 -> xMid, 1 -> 0), Fritsch-Carlson. xMid = 0,5 daje linię prostą.
    static double knobToX (double p, double xMid)
    {
        p = std::min (std::max (p, 0.0), 1.0);
        const double d0 = (xMid - 1.0) / 0.5;      // nachylenie 1. odcinka
        const double d1 = (0.0 - xMid) / 0.5;      // nachylenie 2. odcinka

        double m1 = (d0 * d1 > 0.0) ? 2.0 * d0 * d1 / (d0 + d1) : 0.0;
        double m0 = 0.5 * (3.0 * d0 - d1);
        double m2 = 0.5 * (3.0 * d1 - d0);
        if (m0 * d0 <= 0.0) m0 = 0.0; else if (d0 * d1 <= 0.0 && std::abs (m0) > 3.0 * std::abs (d0)) m0 = 3.0 * d0;
        if (m2 * d1 <= 0.0) m2 = 0.0; else if (d0 * d1 <= 0.0 && std::abs (m2) > 3.0 * std::abs (d1)) m2 = 3.0 * d1;

        const double h = 0.5;
        const bool first = p < 0.5;
        const double t  = first ? p / h : (p - 0.5) / h;
        const double y0 = first ? 1.0 : xMid;
        const double y1 = first ? xMid : 0.0;
        const double ma = first ? m0 : m1;
        const double mb = first ? m1 : m2;

        const double t2 = t * t, t3 = t2 * t;
        return (2 * t3 - 3 * t2 + 1) * y0 + (t3 - 2 * t2 + t) * h * ma
             + (-2 * t3 + 3 * t2) * y1 + (t3 - t2) * h * mb;
    }

private:
    static constexpr int N = 8;   // węzły: 0 szyna, 1 Th, 2 Bh, 3 Wh, 4 Tl, 5 Bl, 6 Wl, 7 Vout

    double fs = 48000.0;
    double xh = 0.37, xl = 0.5;
    bool   dirty = true;

    double g[6]  = {};            // przewodności towarzyszące kondensatorów
    double vc[6] = {}, ic[6] = {};
    double inv[N][N] = {};

    void rebuild()
    {
        const double caps[6] = { C0, Ch, Ch, Cl, Cl, Cf };
        for (int k = 0; k < 6; ++k)
            g[k] = 2.0 * caps[k] * fs;

        double Y[N][N] = {};

        auto res = [&] (int a, int c, double y)          // rezystor a - c (c < 0: do masy)
        {
            Y[a][a] += y;
            if (c >= 0) { Y[c][c] += y; Y[a][c] -= y; Y[c][a] -= y; }
        };
        auto toOut = [&] (int a, double y)                 // gałąź do wyjścia opampa (tylko wiersz a)
        {
            Y[a][a] += y;
            Y[a][7] -= y;
        };

        res (1, 3, 1.0 / (xh * Rp));
        res (3, 2, 1.0 / ((1.0 - xh) * Rp));
        res (3, -1, 1.0 / Rhw);
        res (0, 4, 1.0 / Rl1);
        res (4, 6, 1.0 / (xl * Rp));
        res (6, 5, 1.0 / ((1.0 - xl) * Rp));
        toOut (5, 1.0 / Rl2);
        res (6, -1, 1.0 / Rlw);

        // kondensatory (przewodności towarzyszące)
        Y[0][0] += g[0];                                             // C0: źródło -> 0
        res (0, 1, g[1]);                                            // Ch1: 0 - 1
        toOut (2, g[2]);                                             // Ch2: 2 -> wyjście
        res (4, 6, g[3]);                                            // Cl1: 4 - 6
        res (6, 5, g[4]);                                            // Cl2: 6 - 5

        // wiersz 7: KCL w IN- (prądy z obu wiperów + sprzężenie = 0)
        Y[7][3] += 1.0 / Rhw;
        Y[7][6] += 1.0 / Rlw;
        Y[7][7] += 1.0 / Rf + g[5];                                  // Rf || Cf

        invert (Y);
    }

    void invert (double A[N][N])
    {
        double M[N][2 * N];
        for (int i = 0; i < N; ++i)
            for (int j = 0; j < N; ++j)
            {
                M[i][j] = A[i][j];
                M[i][N + j] = (i == j) ? 1.0 : 0.0;
            }

        for (int c = 0; c < N; ++c)
        {
            int piv = c;
            for (int r = c + 1; r < N; ++r)
                if (std::abs (M[r][c]) > std::abs (M[piv][c])) piv = r;

            if (piv != c)
                for (int j = 0; j < 2 * N; ++j) std::swap (M[c][j], M[piv][j]);

            const double d = 1.0 / M[c][c];
            for (int j = 0; j < 2 * N; ++j) M[c][j] *= d;

            for (int r = 0; r < N; ++r)
            {
                if (r == c) continue;
                const double f = M[r][c];
                if (f != 0.0)
                    for (int j = 0; j < 2 * N; ++j) M[r][j] -= f * M[c][j];
            }
        }

        for (int i = 0; i < N; ++i)
            for (int j = 0; j < N; ++j)
                inv[i][j] = M[i][N + j];
    }
};