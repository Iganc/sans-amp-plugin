#include "PluginProcessor.h"
#include <cmath>
#include <algorithm>

//==============================================================================
// Stałe i funkcje pomocnicze
//==============================================================================
namespace
{
    // k = Rf * 2 * Is  (100k * 5nA). Wartości zakładają diody w rodzaju 1N4148.
    // 0 dBFS = 1 V szczytowo - dobierz na słuch (razem z parametrem Input).
    constexpr float kInputVolts = 1.0f;
    constexpr float kPunchMakeup = 2.0f;

    // Stopień HIGH/LOW (U3b): pozycje wipera (od strony szyny) przy gałce = 0,5
    constexpr double kHighXMid = 0.37;
    constexpr double kLowXMid  = 0.5;

    // Stara wartość (-1,04 dB przy 1 kHz przy domyślnych gałkach) była dobrana pod tanh.
    // Po wstawieniu DriveStage trzeba skalibrować od nowa (pomiar przy -40 dBFS vs referencja).
    constexpr float kToneMakeup = 1.127f;

    // DriveStage zwraca wolty (do ok. +-4,7 V przy ścięciu); normalizujemy do +-1, jak wcześniej tanh.
    constexpr float kDriveNorm = 1.0f / 4.7f;

    // Post-LPF 4 kHz wyłączony na czas porównań z referencją (U10a/U10b już ścinają górę).
    constexpr bool kUsePostLp = false;

}

//==============================================================================
juce::AudioProcessorValueTreeState::ParameterLayout
SansAmpCloneAudioProcessor::createParameterLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    // Trim wejściowy (w oryginale go nie ma - poziom z interfejsu bywa dowolny)
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { preampParamID, 1 },
        "Input",
        juce::NormalisableRange<float> (-12.0f, 12.0f, 0.1f),
        0.0f,
        juce::AudioParameterFloatAttributes().withLabel ("dB")));

    // PRE-AMP / GAIN (U2a) - cyfrowy pot DS1267, 256 kroków
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { gainParamID, 1 },
        "Gain",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f),
        0.5f));

    // BUZZ (U2b) - cyfrowy pot DS1267, 256 kroków
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { buzzParamID, 1 },
        "Buzz",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f),
        0.5f));

    // PUNCH (U3a) - 256 kroków, środek (0,5) = płasko
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { punchParamID, 1 },
        "Punch",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f),
        0.5f));

    // CRUNCH (U9a)
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { crunchParamID, 1 },
        "Crunch",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f),
        0.5f));

    // DRIVE (U9b)
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { driveParamID, 1 },
        "Drive",
        juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f),
        0.5f));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { outputParamID, 1 },
        "Output",
        juce::NormalisableRange<float> (-24.0f, 12.0f, 0.1f),
        0.0f,
        juce::AudioParameterFloatAttributes().withLabel ("dB")));

    // HIGH / LOW (U3b)
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { highParamID, 1 }, "High",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f), 0.5f));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { lowParamID, 1 }, "Low",
        juce::NormalisableRange<float> (0.0f, 1.0f, 1.0f / 255.0f), 0.5f));

    return layout;
}

//==============================================================================
SansAmpCloneAudioProcessor::SansAmpCloneAudioProcessor()
#ifndef JucePlugin_PreferredChannelConfigurations
     : AudioProcessor (BusesProperties()
                     #if ! JucePlugin_IsMidiEffect
                      #if ! JucePlugin_IsSynth
                       .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
                      #endif
                       .withOutput ("Output", juce::AudioChannelSet::stereo(), true)
                     #endif
                       ),
       apvts (*this, nullptr, "STATE", createParameterLayout())
#else
     : apvts (*this, nullptr, "STATE", createParameterLayout())
#endif
{
    driveParam  = apvts.getRawParameterValue (driveParamID);
    preampParam = apvts.getRawParameterValue (preampParamID);
    outputParam = apvts.getRawParameterValue (outputParamID);
    gainParam   = apvts.getRawParameterValue (gainParamID);
    buzzParam   = apvts.getRawParameterValue (buzzParamID);
    punchParam  = apvts.getRawParameterValue (punchParamID);
    crunchParam = apvts.getRawParameterValue (crunchParamID);
    highParam   = apvts.getRawParameterValue (highParamID);
    lowParam    = apvts.getRawParameterValue (lowParamID);
}

SansAmpCloneAudioProcessor::~SansAmpCloneAudioProcessor()
{
}

//==============================================================================
const juce::String SansAmpCloneAudioProcessor::getName() const
{
    return JucePlugin_Name;
}

double SansAmpCloneAudioProcessor::getTailLengthSeconds() const
{
    return 0.0;
}

int SansAmpCloneAudioProcessor::getNumPrograms()
{
    return 1;
}

int SansAmpCloneAudioProcessor::getCurrentProgram()
{
    return 0;
}

void SansAmpCloneAudioProcessor::setCurrentProgram (int) {}

const juce::String SansAmpCloneAudioProcessor::getProgramName (int)
{
    return {};
}

void SansAmpCloneAudioProcessor::changeProgramName (int, const juce::String&) {}

//==============================================================================
void SansAmpCloneAudioProcessor::prepareToPlay (double sampleRate, int /*samplesPerBlock*/)
{
    smoothedDrive.reset (sampleRate, 0.05);
    smoothedDrive.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, driveParam->load()));

    smoothedPreamp.reset (sampleRate, 0.05);
    smoothedPreamp.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (preampParam->load()));

    smoothedOutput.reset (sampleRate, 0.05);
    smoothedOutput.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));

    smoothedGain.reset (sampleRate, 0.05);
    smoothedGain.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, gainParam->load()));

    smoothedBuzz.reset (sampleRate, 0.05);
    smoothedBuzz.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, buzzParam->load()));

    smoothedPunch.reset (sampleRate, 0.05);
    smoothedPunch.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, punchParam->load()));

    smoothedCrunch.reset (sampleRate, 0.05);
    smoothedCrunch.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, crunchParam->load()));

    smoothedHigh.reset (sampleRate, 0.05);
    smoothedHigh.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, highParam->load()));
    smoothedLow.reset (sampleRate, 0.05);
    smoothedLow.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, lowParam->load()));

    const auto fs = (float) sampleRate;
    const auto twoPi = juce::MathConstants<float>::twoPi;

    // Filtr wygładzający za stopniem DRIVE (świadomy wybór brzmieniowy, ~4 kHz; patrz kUsePostLp)
    alphaPost = 1.0f - std::exp (-twoPi * 4000.0f / fs);

    // DC blocker ~8 Hz (nie podcina basu)
    dcR = 1.0f - twoPi * 8.0f / fs;

    lastGain = smoothedGain.getCurrentValue();
    gainStage.prepare (sampleRate);
    gainStage.setGain (lastGain);

    lastBuzz = smoothedBuzz.getCurrentValue();
    buzzStage.prepare (sampleRate);
    buzzStage.setBuzz (lastBuzz);

    lastPunch = smoothedPunch.getCurrentValue();
    punchStage.prepare (sampleRate);
    punchStage.setPunch (lastPunch);

    toneStage.prepare (sampleRate);
    lastHigh = smoothedHigh.getCurrentValue();
    lastLow  = smoothedLow.getCurrentValue();
    toneStage.setPositions (ToneStage::knobToX (lastHigh, kHighXMid),
                            ToneStage::knobToX (lastLow,  kLowXMid));

    driveStage.prepare (sampleRate);
    driveStage.setKnobs (smoothedCrunch.getCurrentValue(), smoothedDrive.getCurrentValue());

    postLpState    = 0.0f;
    dcBlockerState = 0.0f;
    prevInputDC    = 0.0f;
}

void SansAmpCloneAudioProcessor::releaseResources()
{
}

#ifndef JucePlugin_PreferredChannelConfigurations
bool SansAmpCloneAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
  #if JucePlugin_IsMidiEffect
    juce::ignoreUnused (layouts);
    return true;
  #else
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::mono()
     && layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;

   #if ! JucePlugin_IsSynth
    if (layouts.getMainOutputChannelSet() != layouts.getMainInputChannelSet())
        return false;
   #endif

    return true;
  #endif
}
#endif

//==============================================================================
// Uwaga: trim wejściowy (Input, z dB na liniowe) jest nakładany w processBlock,
// tutaj dostajemy już sygnał po tej gałce. Współczynniki stopni GAIN, BUZZ i PUNCH
// też są aktualizowane w processBlock, tuż przed wywołaniem tej funkcji.
float SansAmpCloneAudioProcessor::processSampleDSP (float in, float drive, float crunch)
{
    // 1. STOPIEŃ PRE-AMP / GAIN (U2a, diody D3/D4 w pętli sprzężenia)
    // 1b. STOPIEŃ BUZZ (U2b): filtr z sieci T -> diody D5/D6 -> LPF od 300pF
    // (inwersja fazy obu stopni pominięta - nie ma znaczenia przed miksem z dry)
    // 1c. STOPIEŃ PUNCH (U3a): filtr 3. rzędu (C1, C2, Cf) -> diody D7/D8.
    // 300pF jest już w transmitancji, więc osobnego LPF za diodami nie ma.
    const float vPunchIn = buzzStage.process (gainStage.process (in * kInputVolts));
    const float punchOut = punchStage.process (vPunchIn);

    // 2. CRUNCH + DRIVE (U9a, U9b, U10a, U10b) wg schematu (domysł - sekcja zalana żywicą).
    // Wejście i wyjście DriveStage w woltach.
    driveStage.setKnobs (crunch, drive);
    const float vPunch   = punchOut / kPunchMakeup;
    const float driveOut = driveStage.process (vPunch) * kDriveNorm;

    // 2b. STOPIEŃ TONÓW HIGH/LOW (U3b)
    const float toneOut = toneStage.process (driveOut) * kToneMakeup;

    // 3. POST-FILTERING (opcjonalny, patrz kUsePostLp)
    float shaped = toneOut;
    if (kUsePostLp)
    {
        postLpState += alphaPost * (toneOut - postLpState);
        shaped = postLpState;
    }

    // 4. DC BLOCKER (~8 Hz)
    const float y = shaped - prevInputDC + dcR * dcBlockerState;
    prevInputDC = shaped;
    dcBlockerState = y;

    return y;
}

void SansAmpCloneAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    const int numSamples = buffer.getNumSamples();
    const int numInputs  = getTotalNumInputChannels();
    const int numOutputs = getTotalNumOutputChannels();

    if (numOutputs == 0 || buffer.getNumChannels() == 0 || numSamples == 0)
        return;

    for (int i = numInputs; i < numOutputs; ++i)
        buffer.clear (i, 0, numSamples);

    smoothedDrive.setTargetValue  (juce::jlimit (0.0f, 1.0f, driveParam->load()));
    smoothedPreamp.setTargetValue (juce::Decibels::decibelsToGain (preampParam->load()));
    smoothedOutput.setTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));
    smoothedGain.setTargetValue   (juce::jlimit (0.0f, 1.0f, gainParam->load()));
    smoothedBuzz.setTargetValue   (juce::jlimit (0.0f, 1.0f, buzzParam->load()));
    smoothedPunch.setTargetValue  (juce::jlimit (0.0f, 1.0f, punchParam->load()));
    smoothedCrunch.setTargetValue (juce::jlimit (0.0f, 1.0f, crunchParam->load()));
    smoothedHigh.setTargetValue   (juce::jlimit (0.0f, 1.0f, highParam->load()));
    smoothedLow.setTargetValue    (juce::jlimit (0.0f, 1.0f, lowParam->load()));

    auto* left  = buffer.getWritePointer (0);
    auto* right = (buffer.getNumChannels() > 1) ? buffer.getWritePointer (1) : nullptr;

    for (int i = 0; i < numSamples; ++i)
    {
        const float in = (right != nullptr) ? 0.5f * (left[i] + right[i]) : left[i];

        // Każdy SmoothedValue odczytywany dokładnie raz na próbkę
        const float drive   = smoothedDrive.getNextValue();
        const float preGain = smoothedPreamp.getNextValue();
        const float outGain = smoothedOutput.getNextValue();
        const float gain    = smoothedGain.getNextValue();
        const float buzz    = smoothedBuzz.getNextValue();
        const float punch   = smoothedPunch.getNextValue();
        const float crunch  = smoothedCrunch.getNextValue();
        const float high    = smoothedHigh.getNextValue();
        const float low     = smoothedLow.getNextValue();

        if (high != lastHigh || low != lastLow)
        {
            toneStage.setPositions (ToneStage::knobToX (high, kHighXMid),
                                    ToneStage::knobToX (low,  kLowXMid));
            lastHigh = high;  lastLow = low;
        }

        // Przeliczenie sieci T tylko gdy gałka się ruszyła
        if (gain  != lastGain)  { gainStage.setGain (gain);   lastGain  = gain; }
        if (buzz != lastBuzz)  { buzzStage.setBuzz (buzz);   lastBuzz = buzz; }
        if (punch != lastPunch) { punchStage.setPunch (punch); lastPunch = punch; }

        // Trim wejściowy (Input)
        float processed = in * preGain;

        // Przetwarzanie przez kaskadę DSP
        processed = processSampleDSP (processed, drive, crunch);

        // Regulacja głośności wyjściowej (Output)
        processed *= outGain;

        left[i] = processed;
        if (right != nullptr)
            right[i] = processed;
    }
}

//==============================================================================
bool SansAmpCloneAudioProcessor::hasEditor() const
{
    return true;
}

juce::AudioProcessorEditor* SansAmpCloneAudioProcessor::createEditor()
{
    return new juce::GenericAudioProcessorEditor (*this);
}

//==============================================================================
void SansAmpCloneAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void SansAmpCloneAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

bool SansAmpCloneAudioProcessor::acceptsMidi() const   { return false; }
bool SansAmpCloneAudioProcessor::producesMidi() const  { return false; }
bool SansAmpCloneAudioProcessor::isMidiEffect() const  { return false; }

//==============================================================================
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new SansAmpCloneAudioProcessor();
}