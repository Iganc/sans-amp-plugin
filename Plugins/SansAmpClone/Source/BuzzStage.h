#pragma once

#include "DiodeModel.h"
#include <algorithm>
#include <cmath>

struct BuzzBiquad
{
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
    double z1 = 0.0, z2 = 0.0;

    float process (float x)
    {
        const double xd = x;
        const double y = b0 * xd + z1;
        z1 = b1 * xd - a1 * y + z2;
        z2 = b2 * xd - a2 * y;
        return (float) y;
    }

    void reset() { z1 = z2 = 0.0; }
};

struct BuzzStage
{
    void prepare (double sampleRate)
    {
        bilinearC = 2.0 * sampleRate;
        alpha = 1.0f - std::exp (-(2.0f * 3.14159265358979323846f) * 20000.0f
                                 / (float) sampleRate);
        reset();
    }

    void reset()
    {
        filter.reset();
        lpState = 0.0f;
    }

    void setBuzz (float newBuzz)
    {
        const double x = 1.0 - (double) std::clamp (newBuzz, 0.0f, 1.0f);
        const double Rpa = x * Rpot;
        const double Rpb = (1.0 - x) * Rpot;

        const double na[2] = { R1 + Rpa, R1 * Rpa * Cpot };
        const double da[2] = { 1.0, Rpa * Cpot };
        const double nb[2] = { R2 + Rpb, R2 * Rpb * Cpot };
        const double db[2] = { 1.0, Rpb * Cpot };

        double nbda[3], nadb[3], nanb[3], num[3], den[3];
        multiply (nb, da, nbda);
        multiply (na, db, nadb);
        multiply (na, nb, nanb);

        for (int i = 0; i < 3; ++i)
        {
            num[i] = Rf * nbda[i];
            den[i] = (Rf + R3) * nadb[i] + nanb[i] + R3 * nbda[i];
        }

        const double c = bilinearC;
        const double c2 = c * c;
        const double a0 = den[0] + den[1] * c + den[2] * c2;

        filter.b0 = (num[0] + num[1] * c + num[2] * c2) / a0;
        filter.b1 = 2.0 * (num[0] - num[2] * c2) / a0;
        filter.b2 = (num[0] - num[1] * c + num[2] * c2) / a0;
        filter.a1 = 2.0 * (den[0] - den[2] * c2) / a0;
        filter.a2 = (den[0] - den[1] * c + den[2] * c2) / a0;
    }

    float process (float input)
    {
        constexpr float kMakeup = 2.0f;
        const float buzzOut = diode::feedback (filter.process (input)) * kMakeup;
        lpState += alpha * (buzzOut - lpState);
        return lpState / kMakeup;
    }

private:
    static constexpr double R1 = 10e3, R2 = 10e3, R3 = 10e3;
    static constexpr double Rpot = 100e3, Rf = 100e3, Cpot = 22e-9;

    double bilinearC = 96000.0;
    float alpha = 0.0f, lpState = 0.0f;
    BuzzBiquad filter;

    static void multiply (const double* p, const double* q, double* result)
    {
        result[0] = p[0] * q[0];
        result[1] = p[0] * q[1] + p[1] * q[0];
        result[2] = p[1] * q[1];
    }
};
