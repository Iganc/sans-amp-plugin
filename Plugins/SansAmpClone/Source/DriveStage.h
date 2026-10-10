#pragma once
#include <cmath>
#include <algorithm>

// DRIVE / CRUNCH - model z pomiarow referencji (H1, koherencja 1.00).
//   DRIVE : plaskie wzmocnienie 32 dB * galka (pomiar -90 dBFS, niezalezne od CRUNCH)
//   CRUNCH: H(s) = (1 + s/wz) / ((1 + s/wp)(1 + s/wh)^2), parametry z tabeli (9 wezlow),
//           interpolacja liniowa w log(f). Blad dopasowania <= 0.35 dB (analog).
// TODO: baseline (stala czesc toru), prawdziwa nieliniowosc, dyskretyzacja (2x oversampling).
namespace drive
{
    constexpr double kDriveRangeDb = 32.0;
    constexpr double kClip = 0.17;      // TODO: tymczasowe, rzad wielkosci z szumu (jednostki probki)

    // wezly CRUNCH: 0, .125, .25, .375, .5, .625, .75, .875, 1
    // wezel 0 = plasko (fz = fp, fh wysoko), reszta z Fit "fit_all.py"
    constexpr int    kN = 9;
    constexpr double kFz[kN] = { 77.6, 73.3,  69.3,  71.8,  77.1,  82.4,  86.1,   87.0,   84.8 };
    constexpr double kFp[kN] = { 77.6, 111.9, 164.9, 268.6, 457.5, 788.0, 1370.0, 2455.4, 6950.0 };
    constexpr double kFh[kN] = { 40000.0, 22412.0, 15981.0, 13509.0, 12295.0, 11527.0, 10757.0, 9859.0, 6976.0 };

    inline double interpLog (const double* t, double k)
    {
        const double x = std::min (std::max (k, 0.0), 1.0) * (kN - 1);
        const int i = std::min ((int) x, kN - 2);
        const double fr = x - i;
        return std::exp ((1.0 - fr) * std::log (t[i]) + fr * std::log (t[i + 1]));
    }

    struct Poly   // c[0] + c[1] s + c[2] s^2 + c[3] s^3
    {
        double c[4] = { 0, 0, 0, 0 };
        Poly() = default;
        Poly (double a, double b = 0, double c2 = 0, double c3 = 0) { c[0] = a; c[1] = b; c[2] = c2; c[3] = c3; }
        Poly operator* (const Poly& o) const
        {
            Poly r;
            for (int i = 0; i < 4; ++i)
                for (int j = 0; i + j < 4; ++j)
                    r.c[i + j] += c[i] * o.c[j];
            return r;
        }
    };

    // Filtr do 3. rzedu, DF2T
    struct Iir
    {
        double b[4] = { 1, 0, 0, 0 }, a[4] = { 1, 0, 0, 0 }, z[3] = { 0, 0, 0 };

        void reset() { z[0] = z[1] = z[2] = 0.0; }

        // s = c (1 - u)/(1 + u), u = z^-1; mnozymy przez (1+u)^3
        void set (const Poly& N, const Poly& D, double c)
        {
            static constexpr double M[4][4] = { { 1,  3,  3,  1 }, { 1,  1, -1, -1 },
                                                { 1, -1, -1,  1 }, { 1, -3,  3, -1 } };
            double B[4] = {}, A[4] = {}, ck = 1.0;
            for (int k = 0; k < 4; ++k)
            {
                for (int j = 0; j < 4; ++j) { B[j] += N.c[k] * ck * M[k][j]; A[j] += D.c[k] * ck * M[k][j]; }
                ck *= c;
            }
            const double inv = 1.0 / A[0];
            for (int j = 0; j < 4; ++j) { b[j] = B[j] * inv; a[j] = A[j] * inv; }
        }

        double process (double x)
        {
            const double y = b[0] * x + z[0];
            z[0] = b[1] * x - a[1] * y + z[1];
            z[1] = b[2] * x - a[2] * y + z[2];
            z[2] = b[3] * x - a[3] * y;
            return y;
        }
    };

    // Tymczasowy gladki limiter: x / (1 + |x/T|^4)^(1/4)
    inline double softClip (double x)
    {
        const double r = x * (1.0 / kClip);
        const double u = r * r;
        return x / std::sqrt (std::sqrt (1.0 + u * u));
    }
}

struct DriveStage
{
    // sampleRate = czestotliwosc, przy ktorej DZIALA ten blok (przy oversamplingu: fs * ratio)
    void prepare (double sampleRate)
    {
        fs = sampleRate;
        c = 2.0 * fs;
        smooth = 1.0 - std::exp (-1.0 / (0.005 * fs));    // ~5 ms
        crunchF.reset();
        gain = targetGain;
        dirty = true;
        setKnobs (crunch, driveKnob);
    }

    // galki 0..1
    void setKnobs (double newCrunch, double newDrive)
    {
        newCrunch = std::min (std::max (newCrunch, 0.0), 1.0);
        newDrive  = std::min (std::max (newDrive,  0.0), 1.0);
        targetGain = std::pow (10.0, drive::kDriveRangeDb * newDrive / 20.0);
        driveKnob = newDrive;
        if (! dirty && newCrunch == crunch) return;
        crunch = newCrunch; dirty = false;
        rebuildCrunch();
    }

    // wejscie i wyjscie w jednostkach probki (1.0 = 0 dBFS)
    float process (float in)
    {
        gain += smooth * (targetGain - gain);
        double x = crunchF.process (in);
        x *= gain;
        x = drive::softClip (x);          // TODO: zastapic po pomiarach nieliniowosci
        return (float) x;                 // TODO: baseline (korektor + stromy filtr) za tym blokiem
    }

private:
    double fs = 48000.0, c = 96000.0, crunch = 0.5, driveKnob = 0.5;
    double gain = 1.0, targetGain = 1.0, smooth = 0.01;
    bool dirty = true;
    drive::Iir crunchF;

    void rebuildCrunch()
    {
        using drive::Poly;
        if (crunch < 1e-4)                                   // 0% = plasko (bypass)
        {
            crunchF.set (Poly (1.0), Poly (1.0), c);
            return;
        }
        const double twoPi = 6.283185307179586;
        const double fz = drive::interpLog (drive::kFz, crunch);
        const double fp = drive::interpLog (drive::kFp, crunch);
        const double fh = std::min (drive::interpLog (drive::kFh, crunch), 0.45 * fs);

        const Poly N  (1.0, 1.0 / (twoPi * fz));
        const Poly Dp (1.0, 1.0 / (twoPi * fp));
        const Poly Dh (1.0, 1.0 / (twoPi * fh));
        crunchF.set (N, Dp * Dh * Dh, c);
    }
};