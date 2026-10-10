#pragma once

#include "DiodeModel.h"
#include <algorithm>

struct PunchIir
{
    double b0 = 1, b1 = 0, b2 = 0, b3 = 0, a1 = 0, a2 = 0, a3 = 0;
    double z1 = 0, z2 = 0, z3 = 0;

    void reset() { z1 = z2 = z3 = 0; }

    float process (float x) noexcept
    {
        const double y = b0 * (double) x + z1;
        z1 = b1 * (double) x - a1 * y + z2;
        z2 = b2 * (double) x - a2 * y + z3;
        z3 = b3 * (double) x - a3 * y;
        return (float) y;
    }
};

struct PunchStage
{
    void prepare (double sampleRate)
    {
        bilinearC = 2.0 * sampleRate;
        reset();
    }

    void reset() { filter.reset(); }

    void setPunch (float newPunch)
    {
        const double x = 1.0 - (double) std::clamp (newPunch, 0.0f, 1.0f);
        const double Rpa = x * Rpot;
        const double Rpb = (1.0 - x) * Rpot;
        const double Rp  = Rpa + Rpb;
        const double RaRb = Ra + Rb;

        const double n0 = Rf * (RaRb + Rp);
        const double n1 = Rf * (C1 * RaRb * Rp
                              + C2 * (R1 * Rb + R1 * Rpb + Ra * Rb + Ra * Rpb
                                      + Rb * Rpa + Rpa * Rpb));
        const double n2 = C1 * C2 * Rf * ((R1 + Ra) * Rb * Rp + RaRb * Rpa * Rpb);

        const double d0 = R1 * (RaRb + Rp);
        const double d1 = R1 * (C1 * RaRb * Rp
                              + C2 * (Ra * Rb + Ra * Rf + Ra * Rpb + Rb * Rpa
                                      + Rf * Rpa + Rpa * Rpb)
                              + Cf * Rf * (RaRb + Rp));
        const double d2 = R1 * (C1 * C2 * (Ra * Rb * Rp + Ra * Rf * Rp + RaRb * Rpa * Rpb)
                              + C1 * Cf * Rf * RaRb * Rp
                              + C2 * Cf * (Ra * Rb * Rf + Ra * Rf * Rpb + Rb * Rf * Rpa
                                           + Rf * Rpa * Rpb));
        const double d3 = C1 * C2 * Cf * R1 * Rf * (Ra * Rb * Rp + RaRb * Rpa * Rpb);

        const double numerator[4] = { n0, n1, n2, 0.0 };
        const double denominator[4] = { d0, d1, d2, d3 };

        static constexpr double transform[4][4] = {
            { 1.0,  3.0,  3.0,  1.0 },
            { 1.0,  1.0, -1.0, -1.0 },
            { 1.0, -1.0, -1.0,  1.0 },
            { 1.0, -3.0,  3.0, -1.0 }
        };

        double b[4] = {}, a[4] = {};
        double cPower = 1.0;
        for (int k = 0; k < 4; ++k)
        {
            for (int j = 0; j < 4; ++j)
            {
                b[j] += numerator[k] * cPower * transform[k][j];
                a[j] += denominator[k] * cPower * transform[k][j];
            }
            cPower *= bilinearC;
        }

        const double inv = 1.0 / a[0];
        filter.b0 = b[0] * inv; filter.b1 = b[1] * inv;
        filter.b2 = b[2] * inv; filter.b3 = b[3] * inv;
        filter.a1 = a[1] * inv; filter.a2 = a[2] * inv; filter.a3 = a[3] * inv;
    }

    float process (float input)
    {
        return diode::feedback (filter.process (input), kDiodeK) * kMakeup;
    }

private:
    static constexpr double R1 = 100e3, Ra = 1e3, Rb = 1e3;
    static constexpr double Rpot = 100e3, Rf = 100e3;
    static constexpr double C1 = 22e-9, C2 = 22e-9, Cf = 300e-12;
    static constexpr float kMakeup = 2.0f;
    static constexpr float kDiodeK = diode::kDiodeK * 0.505f;

    double bilinearC = 96000.0;
    PunchIir filter;
};
