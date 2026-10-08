#include "PluginProcessor.h"

//==============================================================================
juce::AudioProcessorValueTreeState::ParameterLayout
SansAmpCloneAudioProcessor::createParameterLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { driveParamID, 1 },
        "Drive",
        juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f),
        0.5f));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { preampParamID, 1 },
        "Preamp",
        juce::NormalisableRange<float> (-12.0f, 12.0f, 0.1f),
        0.0f,
        juce::AudioParameterFloatAttributes().withLabel ("dB")));

    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { outputParamID, 1 },
        "Output",
        juce::NormalisableRange<float> (-24.0f, 12.0f, 0.1f),
        0.0f,
        juce::AudioParameterFloatAttributes().withLabel ("dB")));

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

    try
    {
        juce::String jsonString = juce::String::createStringFromData (
            BinaryData::sansamp_weights_json,
            BinaryData::sansamp_weights_jsonSize);

        auto parsedJson = nlohmann::json::parse (jsonString.toStdString());
        model.parseJson (parsedJson);
        modelLoaded = true;
    }
    catch (const std::exception& e)
    {
        modelLoaded = false;
        DBG ("SansAmpClone: nie udalo sie wczytac modelu: " << e.what());
    }
    catch (...)
    {
        modelLoaded = false;
        DBG ("SansAmpClone: nie udalo sie wczytac modelu (nieznany blad)");
    }
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
    if (std::abs (sampleRate - 48000.0) > 1.0)
        DBG ("SansAmpClone: OSTRZEZENIE - model trenowany na 48 kHz, host pracuje na "
             << sampleRate << " Hz. Brzmienie bedzie sie roznic.");

    smoothedDrive.reset (sampleRate, 0.05); // 50 ms
    smoothedDrive.setCurrentAndTargetValue (juce::jlimit (0.0f, 1.0f, driveParam->load()));

    smoothedPreamp.reset (sampleRate, 0.05);
    smoothedPreamp.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (preampParam->load()));

    smoothedOutput.reset (sampleRate, 0.05);
    smoothedOutput.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));

    model.reset();
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

void SansAmpCloneAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    const int numSamples = buffer.getNumSamples();
    const int numInputs  = getTotalNumInputChannels();
    const int numOutputs = getTotalNumOutputChannels();

    // Zabezpieczenie: brak kanalow lub pusty blok
    if (numOutputs == 0 || buffer.getNumChannels() == 0 || numSamples == 0)
        return;

    for (int i = numInputs; i < numOutputs; ++i)
        buffer.clear (i, 0, numSamples);

    // Jesli model sie nie wczytal: przepuszczamy dzwiek bez zmian
    if (! modelLoaded)
        return;

    smoothedDrive.setTargetValue (juce::jlimit (0.0f, 1.0f, driveParam->load()));
    smoothedPreamp.setTargetValue (juce::Decibels::decibelsToGain (preampParam->load()));
    smoothedOutput.setTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));

    auto* left  = buffer.getWritePointer (0);
    auto* right = (buffer.getNumChannels() > 1) ? buffer.getWritePointer (1) : nullptr;

    for (int i = 0; i < numSamples; ++i)
    {
        // Wejscie mono: srednia L i R (przy ścieżce mono w Reaperze oba kanaly sa takie same)
        const float in = (right != nullptr) ? 0.5f * (left[i] + right[i]) : left[i];
        const float drive    = smoothedDrive.getNextValue();
        const float preGain  = smoothedPreamp.getNextValue();
        const float outGain  = smoothedOutput.getNextValue();

        const float inputs[2] = { in * preGain, drive };
        float out = model.forward (inputs);

        if (! std::isfinite (out))
        {
            out = 0.0f;
            model.reset();
        }

        out *= outGain;

        left[i] = out;
        if (right != nullptr)
            right[i] = out;
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