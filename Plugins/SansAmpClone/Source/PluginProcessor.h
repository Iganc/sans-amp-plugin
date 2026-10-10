#pragma once
#include <JuceHeader.h>
#include <atomic>
#include "GainStage.h"
#include "BuzzStage.h"
#include "PunchStage.h"
#include "ToneStage.h"        
#include "DriveStage.h"     

class SansAmpCloneAudioProcessor : public juce::AudioProcessor
{
public:
    SansAmpCloneAudioProcessor();
    ~SansAmpCloneAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

   #ifndef JucePlugin_PreferredChannelConfigurations
    bool isBusesLayoutSupported (const juce::AudioProcessor::BusesLayout& layouts) const override;
   #endif

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override;

    const juce::String getName() const override;

    bool acceptsMidi() const override;
    bool producesMidi() const override;
    bool isMidiEffect() const override;
    double getTailLengthSeconds() const override;

    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int index, const juce::String& newName) override;

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    static constexpr const char* driveParamID   = "drive";
    static constexpr const char* preampParamID  = "preamp";   // w UI: "Input" (trim w dB)
    static constexpr const char* outputParamID  = "output";
    static constexpr const char* gainParamID    = "gain";     // PRE-AMP / GAIN (U2a)
    static constexpr const char* buzzParamID    = "buzz";     // BUZZ (U2b)
    static constexpr const char* crunchParamID = "crunch";

    juce::AudioProcessorValueTreeState apvts;

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    std::atomic<float>* driveParam  = nullptr;
    std::atomic<float>* preampParam = nullptr;
    std::atomic<float>* outputParam = nullptr;
    std::atomic<float>* gainParam   = nullptr;
    std::atomic<float>* buzzParam   = nullptr;

    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedDrive;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedPreamp;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedOutput;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedGain;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedBuzz;

    // Stany filtrów i procesora DSP
    float postLpState    = 0.0f;
    float dcBlockerState = 0.0f;
    float prevInputDC    = 0.0f;
    float alphaPost = 0.0f, dcR = 0.0f;
    // Stopień GAIN (U2a): wzmocnienie liniowe i k' diod, przeliczane gdy gałka się rusza
    float lastGain = -1.0f;
    GainStage gainStage;

    float  lastBuzz  = -1.0f;
    BuzzStage buzzStage;

    static constexpr const char* punchParamID = "punch";

    std::atomic<float>* punchParam = nullptr;
    juce::SmoothedValue<float> smoothedPunch;
    float lastPunch = 0.5f;
    PunchStage punchStage;

    static constexpr const char* highParamID = "high";
    static constexpr const char* lowParamID  = "low";

    std::atomic<float>* highParam = nullptr;
    std::atomic<float>* lowParam  = nullptr;
    juce::SmoothedValue<float> smoothedHigh, smoothedLow;
    float lastHigh = -1.0f, lastLow = -1.0f;
    ToneStage toneStage;

    std::atomic<float>* crunchParam = nullptr;
    juce::SmoothedValue<float> smoothedCrunch;
    DriveStage driveStage;

    // zmieniona sygnatura:
    float processSampleDSP (float in, float drive, float crunch);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SansAmpCloneAudioProcessor)
};