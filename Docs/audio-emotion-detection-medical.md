# Audio Emotion Detection for Medical Consultations

## Overview

Detect emotions (anxious, distressed, calm, etc.) from audio in medical consultations using acoustic features, not text.

## Recommended Approach: Wav2Vec2 + Emotion Classification

**Why this works best:**
- Language-agnostic (works across Hindi, Tamil, Telugu, etc.)
- Trained on speech acoustics (pitch, tone, energy)
- Can detect stress/anxiety patterns in voice

## Step 1: Installation

```bash
pip install transformers torch torchaudio librosa numpy
```

## Step 2: Basic Emotion Detection

```python
import torch
import torchaudio
from transformers import Wav2Vec2Processor, Wav2Vec2ForSequenceClassification

# Load pre-trained emotion model
model_name = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
processor = Wav2Vec2Processor.from_pretrained(model_name)
model = Wav2Vec2ForSequenceClassification.from_pretrained(model_name)

def detect_emotion(audio_path):
    """Detect emotion from audio file"""
    # Load audio
    speech, sr = torchaudio.load(audio_path)
    
    # Resample to 16kHz if needed
    if sr != 16000:
        resampler = torchaudio.transforms.Resample(sr, 16000)
        speech = resampler(speech)
    
    # Process audio
    inputs = processor(speech.squeeze(), sampling_rate=16000, return_tensors="pt", padding=True)
    
    # Get predictions
    with torch.no_grad():
        logits = model(**inputs).logits
    
    # Get emotion scores
    predicted_ids = torch.argmax(logits, dim=-1)
    
    # Emotion labels (standard model)
    emotions = ['angry', 'calm', 'disgust', 'fearful', 'happy', 'neutral', 'sad', 'surprised']
    
    return emotions[predicted_ids.item()]

# Usage
emotion = detect_emotion("patient_audio.wav")
print(f"Detected emotion: {emotion}")
```

## Step 3: Map to Medical-Relevant Emotions

```python
def map_to_medical_emotions(emotion, audio_features=None):
    """Map generic emotions to medical context"""
    
    medical_mapping = {
        'angry': 'agitated',
        'calm': 'calm',
        'fearful': 'anxious',
        'sad': 'distressed',
        'neutral': 'neutral',
        'happy': 'comfortable',
        'disgust': 'uncomfortable',
        'surprised': 'startled'
    }
    
    return medical_mapping.get(emotion, emotion)

# Usage
medical_emotion = map_to_medical_emotions(emotion)
print(f"Medical emotion: {medical_emotion}")
```

## Step 4: Extract Acoustic Features for Better Detection

```python
import librosa
import numpy as np

def extract_voice_features(audio_path):
    """Extract acoustic features indicating stress/anxiety"""
    y, sr = librosa.load(audio_path, sr=16000)
    
    # Features that indicate anxiety/stress:
    
    # 1. Pitch variation (high variation = anxious)
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_mean = np.mean(pitches[pitches > 0])
    pitch_std = np.std(pitches[pitches > 0])
    
    # 2. Speaking rate (fast = anxious)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    
    # 3. Energy/Volume (low = depressed, high = agitated)
    rms = librosa.feature.rms(y=y)[0]
    energy_mean = np.mean(rms)
    
    # 4. Voice tremor (high zero-crossing rate = trembling)
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    tremor = np.mean(zcr)
    
    return {
        'pitch_mean': pitch_mean,
        'pitch_variation': pitch_std,
        'speaking_rate': tempo,
        'energy': energy_mean,
        'tremor': tremor
    }

def classify_medical_state(features):
    """Rule-based classification for medical emotional state"""
    
    # These thresholds need tuning based on your data
    if features['pitch_variation'] > 50 and features['speaking_rate'] > 120:
        return 'anxious'
    elif features['energy'] < 0.02 and features['speaking_rate'] < 80:
        return 'depressed'
    elif features['tremor'] > 0.15:
        return 'distressed'
    elif features['pitch_variation'] < 30 and features['energy'] > 0.03:
        return 'calm'
    else:
        return 'neutral'
```

## Step 5: Integrate with Pyannote + Gemini Pipeline

```python
def complete_medical_analysis(audio_path, language="hi"):
    """Complete pipeline: Diarization + Transcription + Emotion"""
    
    # Step 1: Diarization (from previous guide)
    diarization = pipeline(audio_path)
    segments = extract_speaker_segments(audio_path, diarization)
    
    results = []
    for segment in segments:
        # Save segment temporarily
        temp_file = "temp_segment.wav"
        segment['audio'].export(temp_file, format="wav")
        
        # Step 2: Transcription
        transcription = transcribe_with_gemini(segment['audio'], language)
        
        # Step 3: Emotion detection
        emotion = detect_emotion(temp_file)
        medical_emotion = map_to_medical_emotions(emotion)
        
        # Step 4: Acoustic features
        features = extract_voice_features(temp_file)
        acoustic_state = classify_medical_state(features)
        
        results.append({
            'speaker': segment['speaker'],
            'start_time': segment['start'],
            'end_time': segment['end'],
            'text': transcription,
            'emotion': medical_emotion,
            'acoustic_state': acoustic_state,
            'voice_features': features
        })
    
    return results

# Usage
results = complete_medical_analysis("consultation.wav", language="ta")

# Print formatted output
for r in results:
    print(f"\n[{r['speaker']}] ({r['start_time']:.1f}s - {r['end_time']:.1f}s)")
    print(f"Emotion: {r['emotion']} | State: {r['acoustic_state']}")
    print(f"Text: {r['text']}")
    print(f"Voice: Pitch={r['voice_features']['pitch_mean']:.1f}Hz, Rate={r['voice_features']['speaking_rate']:.1f}bpm")
```

## Step 6: Alternative - OpenSMILE (Research-Grade)

```bash
# Install OpenSMILE
pip install opensmile
```

```python
import opensmile

def analyze_with_opensmile(audio_path):
    """Extract comprehensive acoustic features"""
    
    smile = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.Functionals,
    )
    
    # Extract 88 acoustic features
    features = smile.process_file(audio_path)
    
    # Key features for medical emotion:
    # - F0semitoneFrom27.5Hz_sma3nz_amean (pitch)
    # - loudness_sma3_amean (volume)
    # - jitterLocal_sma3nz_amean (voice quality)
    
    return features

# Usage with ML classifier
from sklearn.ensemble import RandomForestClassifier

# You would need labeled medical audio data to train this
# classifier = RandomForestClassifier()
# classifier.fit(training_features, training_labels)
```

## Output Format Example

```
[SPEAKER_00] (0.0s - 15.3s)
Emotion: anxious | State: anxious
Text: டாக்டர், எனக்கு மிகவும் பயமாக இருக்கிறது
Voice: Pitch=210.3Hz, Rate=135.2bpm

[SPEAKER_01] (15.5s - 28.7s)
Emotion: calm | State: calm
Text: கவலை படாதீர்கள், எல்லாம் சரியாகிவிடும்
Voice: Pitch=165.8Hz, Rate=95.5bpm
```

## Medical Emotion Categories

**Patient States to Track:**
- `anxious` - High pitch variation, fast speech, trembling voice
- `distressed` - High energy, agitated speech patterns
- `depressed` - Low energy, slow speech, monotone
- `calm` - Stable pitch, moderate pace
- `neutral` - Baseline state
- `pain` - Sudden pitch changes, groaning sounds
- `comfortable` - Relaxed speech patterns

## Performance Tips

- **Segment length**: Analyze 3-5 second segments for best accuracy
- **Background noise**: Preprocess audio to remove noise
- **Multiple emotions**: Average emotion scores over conversation
- **Context matters**: Patient emotions change during consultation
- **GPU usage**: Use GPU for faster processing with `model.to('cuda')`

## Validation for Medical Use

- **Test on your actual consultation data** - Pre-trained models may need fine-tuning
- **Get clinician feedback** - Validate emotion labels with healthcare professionals
- **Track patterns** - Emotion changes over consultation duration are significant
- **Privacy**: Ensure emotion data is handled as medical information

## Advanced: Fine-tune for Your Data

```python
# If you have labeled medical audio data
from transformers import Trainer, TrainingArguments

# Prepare your dataset
# dataset = prepare_medical_audio_dataset()

training_args = TrainingArguments(
    output_dir="./medical-emotion-model",
    num_train_epochs=10,
    per_device_train_batch_size=8,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
)

# trainer.train()
```

## Common Issues

- **Low accuracy on Indian languages**: Pre-trained models are often English-focused
- **Solution**: Fine-tune on your consultation data or use acoustic features
- **Background noise**: Medical settings have equipment noise
- **Solution**: Use noise reduction preprocessing
- **Multiple speakers overlapping**: Affects emotion detection
- **Solution**: Ensure clean diarization first (from Pyannote)
