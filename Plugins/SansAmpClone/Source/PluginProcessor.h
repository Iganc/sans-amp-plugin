#pragma once
#include <JuceHeader.h>
#include <RTNeural/RTNeural.h>
#include <atomic>

class SansAmpCloneAudioProcessor  : public juce::AudioProcessor
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

    // Metody MIDI bez override (jak w Twojej wersji)
    bool acceptsMidi() const;
    bool producesMidi() const;
    bool isMidiEffect() const;
    double getTailLengthSeconds() const override;

    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int index, const juce::String& newName) override;

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    // ID parametru - po ustaleniu nie zmieniaj
    static constexpr const char* driveParamID   = "drive";
    static constexpr const char* preampParamID  = "preamp";
    static constexpr const char* outputParamID  = "output";

    juce::AudioProcessorValueTreeState apvts;

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    RTNeural::ModelT<float, 2, 1,
        RTNeural::LSTMLayerT<float, 2, 64>,
        RTNeural::DenseT<float, 64, 1>> model;

    std::atomic<float>* driveParam  = nullptr;
    std::atomic<float>* preampParam = nullptr; // dB
    std::atomic<float>* outputParam = nullptr; // dB

    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedDrive;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedPreamp; // gain liniowy
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear> smoothedOutput; // gain liniowy

    bool modelLoaded = false;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SansAmpCloneAudioProcessor)
};