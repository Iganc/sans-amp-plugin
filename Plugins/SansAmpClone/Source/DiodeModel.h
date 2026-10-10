#pragma once

#include <algorithm>
#include <cmath>

namespace diode
{
    constexpr float kDiodeK = 5.0e-4f;

    inline float feedback (float xLin, float k = kDiodeK)
    {
        constexpr float Vt = 0.045f;

        const float a = std::abs (xLin);
        float y = std::min (a, Vt * std::asinh (a / k));

        for (int i = 0; i < 3; ++i)
        {
            const float e  = std::exp (y / Vt);
            const float ei = 1.0f / e;
            const float s  = 0.5f * (e - ei);
            const float c  = 0.5f * (e + ei);
            y -= (y + k * s - a) / (1.0f + k * c / Vt);
        }

        return std::copysign (y, xLin);
    }
}
