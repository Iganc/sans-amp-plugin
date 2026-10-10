#pragma once

#include "DiodeModel.h"
#include <cmath>

struct GainStage
{
    void prepare (double sampleRate)
    {
        alpha = 1.0f - std::exp (-(2.0f * 3.14159265358979323846f) * 21000.0f
                                 / (float) sampleRate);
        reset();
    }

    void reset() { lpState = 0.0f; }

    void setGain (float newGain)
    {
        constexpr double R1 = 1e3, R2 = 47e3, R3 = 1e3;
        constexpr double Rpot = 100e3, Rf = 100e3;
        constexpr double Is2 = diode::kDiodeK / Rf;

        const double x  = 1.0 - (double) newGain;
        const double Ra = R1 + x * Rpot;
        const double Rb = R2 + (1.0 - x) * Rpot;
        const double D  = 1.0 + R3 / Ra + R3 / Rb;
        const double g  = 1.0 / Rb + D / Rf;

        stageGain = (float) (1.0 / (Ra * g));
        diodeK    = (float) (D * Is2 / g);
    }

    float process (float input)
    {
        constexpr float kMakeup = 2.0f;
        const float shaped = diode::feedback (input * stageGain, diodeK) * kMakeup;
        lpState += alpha * (shaped - lpState);
        return lpState / kMakeup;
    }

private:
    float stageGain = 1.0f;
    float diodeK = diode::kDiodeK;
    float alpha = 0.0f;
    float lpState = 0.0f;
};
