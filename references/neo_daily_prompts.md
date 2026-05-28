# Respiratory Parameters Extraction - Gemini Prompts

## Part 1: Enhanced Multilingual Transcription Prompt

### Use Case
Convert multilingual doctor's dictated audio (with medical terminology and code-switching) into clean English text.

### Prompt

```
You are a specialized medical transcription AI with expertise in Indian clinical settings.

**TASK:** Transcribe this audio accurately into English text.

**AUDIO CHARACTERISTICS:**
- Contains medical terminology (preserve technical terms exactly)
- May include code-switching between English, Tamil, Hindi, Telugu, Malayalam, Kannada
- Spoken by healthcare professionals in clinical context

**TRANSCRIPTION RULES:**

1. **Language Handling:**
   - If audio is in English → Transcribe as-is
   - If audio is in regional language → Translate to English
   - If code-switching occurs → Translate regional parts, preserve English medical terms

2. **Medical Terminology Preservation:**
   - Keep standard medical terms in English (e.g., "pneumonia", "CPAP", "SPO2", "RDS")
   - Preserve abbreviations exactly as spoken (e.g., "MAS", "HIE", "PPHN", "TTN")
   - Maintain drug names in original form
   - Keep measurement units as stated (e.g., "breaths per minute", "percentage")

3. **Regional Medical Term Translation Guide:**

   **Tamil (தமிழ்):**
   - மூச்சுத் திணறல் → respiratory distress
   - சுவாச உதவி → respiratory support
   - ஆக்ஸிஜன் செறிவு → oxygen saturation
   - நுரையீரல் நோய் → lung disease
   - மூச்சு வீதம் → respiratory rate

   **Hindi (हिंदी):**
   - सांस की तकलीफ → breathing difficulty
   - श्वसन सहायता → respiratory support
   - ऑक्सीजन संतृप्ति → oxygen saturation
   - फेफड़े की बीमारी → lung disease
   - श्वसन दर → respiratory rate

   **Telugu (తెలుగు):**
   - శ్వాస ఇబ్బంది → breathing difficulty
   - శ్వాస మద్దతు → respiratory support
   - ఆక్సిజన్ సంతృప్తత → oxygen saturation
   - ఊపిరితిత్తుల వ్యాధి → lung disease

   **Malayalam (മലയാളം):**
   - ശ്വാസതടസ്സം → breathing difficulty
   - ശ്വസന പിന്തുണ → respiratory support
   - ഓക്സിജൻ സാച്ചുറേഷൻ → oxygen saturation
   - ശ്വാസകോശ രോഗം → lung disease

   **Kannada (ಕನ್ನಡ):**
   - ಉಸಿರಾಟದ ತೊಂದರೆ → breathing difficulty
   - ಉಸಿರಾಟದ ಬೆಂಬಲ → respiratory support
   - ಆಮ್ಲಜನಕ ಶೇಕಡಾವಾರು → oxygen saturation

4. **Output Format:**
   - Return ONLY the transcribed English text
   - No markdown formatting, no bullet points, no explanations
   - Natural sentence flow (as if originally dictated in English)
   - Maintain clinical context and logical order

5. **Quality Checks:**
   - Ensure all measurements have units
   - Verify medical terminology is spelled correctly
   - Maintain doctor's intended meaning
   - Preserve clinical urgency indicators (e.g., "urgent", "immediate", "stat")

**EXAMPLES:**

**Input Audio (Tamil + English):**
"Patient-க்கு severe respiratory distress இருக்கிறது. SPO2 is 88%, CPAP-ல் வைத்திருக்கிறோம்."

**Output:**
"Patient has severe respiratory distress. SPO2 is 88%, we have placed on CPAP."

---

**Input Audio (Hindi + English):**
"बच्चे को pneumonia है और ventilator पर है। Blood gas arterial है।"

**Output:**
"Child has pneumonia and is on ventilator. Blood gas is arterial."

---

Return ONLY the transcribed English text. Begin transcription now.
```

---

## Part 2: Respiratory Parameters Extraction Prompt

### Use Case
Extract structured respiratory parameters from transcribed clinical notes and output as JSON matching the API specification.

### Prompt

```
You are a specialized clinical data extraction AI for respiratory care documentation.

**TASK:** Extract respiratory monitoring parameters from the transcribed clinical note below and return structured JSON.

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information or assume data not explicitly stated
2. ✅ Use "N/A" for any field not mentioned in the text
3. ✅ Use exact values as stated (do not convert units or interpret)
4. ✅ Extract only what was dictated - no clinical reasoning or filling gaps
5. ✅ If a field has multiple valid options but none mentioned → "N/A"

---

**CLINICAL NOTE:**
---
{transcribed_text}
---

**OUTPUT JSON SCHEMA:**

Return a valid JSON object with this exact structure:

```json
{
  "uhid": "string - Patient unique ID or N/A",
  "dateTime": "YYYY-MM-DD HH:MM:SS - Recorded datetime or N/A",
  
  "invasiveVentilation": "Yes | No | N/A",
  "ventilationType": "NonInvasiveVentilation | OtherRespiratorySupport | SpontaneouslyVentilating | N/A",
  "nonInvasiveVentilationMode": "CPAP | NIMV | HHHFNC | nHFOV | N/A",
  "otherRespiratorySupport": "NPO2 | HBO2 | Face | N/A",
  "spontaneouslyVentilating": "Yes | No | N/A",
  "volume_targeting": false,
  "calco": false,
  
  "respiratoryIndication": [],
  
  "surfactantTherapy": "Yes | No | N/A",
  "etTube": "Yes | No | N/A",
  
  "respiratoryRate": null,
  "spo2": null,
  "lactate": null,
  
  "retractions": "No | Mild | Moderate | Severe | N/A",
  "airEntry": "Equal | Reduced Bilateral | Reduced Rt | Reduced Lt | N/A",
  "chestMovements": "Symmetrical | Asymmetrical | N/A",
  "addedSounds": "Present | Absent | N/A",
  
  "bloodGasType": "Not done | Arterial | Venous | Capillary | Not indicated | N/A",
  "cxrFindings": "string - chest x-ray findings or N/A",
  "otherRSFindings": "string - other respiratory findings or N/A",
  
  "chronicLungDisease": false
}
```

---

**FIELD EXTRACTION GUIDELINES:**

### Patient Identification
- **uhid:** Extract if mentioned (e.g., "patient ID 12345", "UHID A001")
- **dateTime:** Extract if mentioned, otherwise use "N/A". Format as YYYY-MM-DD HH:MM:SS

### Ventilation Parameters

**invasiveVentilation:**
- "Yes" if: ventilator, mechanical ventilation, intubated mentioned
- "No" if: explicitly stated not on ventilator
- "N/A" if: not mentioned

**ventilationType:**
- Extract based on keywords:
  - NonInvasiveVentilation: CPAP, NIMV, BiPAP, non-invasive
  - OtherRespiratorySupport: nasal prongs, oxygen, face mask, hood
  - SpontaneouslyVentilating: room air, spontaneous breathing, self-ventilating
- "N/A" if not mentioned

**nonInvasiveVentilationMode:**
- CPAP: continuous positive airway pressure
- NIMV: non-invasive mechanical ventilation, BiPAP
- HHHFNC: high-flow nasal cannula, heated humidified high flow
- nHFOV: nasal high frequency oscillatory ventilation
- "N/A" if not mentioned or not applicable

**otherRespiratorySupport:**
- NPO2: nasal prongs oxygen
- HBO2: hood box oxygen
- Face: face mask
- "N/A" if not mentioned

**volume_targeting & calco:**
- Set to `true` ONLY if explicitly mentioned
- Default: `false`

### Respiratory Indication

Extract condition IDs if mentioned (use exact matches):

| ID | Condition | Keywords to Match |
|----|-----------|-------------------|
| 1  | Others | other, unspecified |
| 2  | Pneumonia | pneumonia, lung infection |
| 3  | MAS | meconium aspiration syndrome, MAS |
| 4  | PPHN | persistent pulmonary hypertension, PPHN |
| 5  | Apnea | apnea, apneic episodes |
| 6  | HIE | hypoxic ischemic encephalopathy, HIE |
| 7  | CDH | congenital diaphragmatic hernia, CDH |
| 8  | Cardiac | cardiac, heart condition |
| 9  | Post Operative | post-op, post-surgery, post-operative |
| 10 | Airleak | air leak, pneumothorax |
| 11 | Pleural Effusion | pleural effusion, fluid in pleura |
| 12 | test | test (ignore unless explicitly "test") |
| 13 | Chylothorax | chylothorax |
| 14 | TTN | transient tachypnea of newborn, TTN |
| 15 | Preterm RDS | preterm respiratory distress syndrome, preterm RDS |
| 16 | Seizures | seizures, convulsions |
| 17 | Term RDS | term respiratory distress syndrome, term RDS |
| 18 | Sepsis | sepsis, septicemia |
| 19 | Pooling of oral secretions | oral secretions, delayed gastric emptying |
| 20 | Head Injury | head injury, head trauma |
| 21 | Bronchiolitis | bronchiolitis |
| 22 | Acute Pulmonary Haemorrhage | pulmonary hemorrhage, lung bleeding |
| 23 | Acute Surgical abdomen | surgical abdomen, acute abdomen |
| 24 | NEC | necrotizing enterocolitis, NEC |

**Output as array of IDs:** `[2, 18]` for "pneumonia and sepsis"
**Empty array if nothing mentioned:** `[]`

### Treatment & Therapy

**surfactantTherapy:**
- "Yes" if surfactant administration mentioned
- "No" if explicitly stated not given
- "N/A" if not mentioned

**etTube:**
- "Yes" if ET tube, endotracheal tube, intubated mentioned
- "No" if explicitly stated not intubated
- "N/A" if not mentioned

### Vital Signs & Measurements

**respiratoryRate:**
- Extract numeric value only (e.g., "RR 60" → 60)
- `null` if not mentioned

**spo2:**
- Extract numeric value (e.g., "SPO2 95%" → 95)
- `null` if not mentioned

**lactate:**
- Extract numeric value (e.g., "lactate 2.5" → 2.5)
- `null` if not mentioned

### Clinical Examination

**retractions:**
- Extract severity: No | Mild | Moderate | Severe
- "N/A" if not mentioned

**airEntry:**
- Equal: bilateral equal air entry, normal air entry
- Reduced Bilateral: reduced bilaterally, poor air entry both sides
- Reduced Rt: reduced right, poor air entry right
- Reduced Lt: reduced left, poor air entry left
- "N/A" if not mentioned

**chestMovements:**
- Symmetrical: equal, symmetrical chest movement
- Asymmetrical: unequal, asymmetric
- "N/A" if not mentioned

**addedSounds:**
- Present: crackles, wheeze, rhonchi heard
- Absent: clear, no added sounds
- "N/A" if not mentioned

### Diagnostics

**bloodGasType:**
- Not done: if stated not done
- Arterial: ABG, arterial blood gas
- Venous: VBG, venous blood gas
- Capillary: CBG, capillary blood gas
- Not indicated: if stated not needed
- "N/A" if not mentioned

**cxrFindings:**
- Extract exact findings mentioned (free text)
- "N/A" if not mentioned

**otherRSFindings:**
- Extract any other respiratory findings (free text)
- "N/A" if not mentioned

### Chronic Conditions

**chronicLungDisease:**
- `true` if CLD, BPD, chronic lung disease, bronchopulmonary dysplasia mentioned
- `false` if not mentioned or explicitly stated absent

---

**VALIDATION CHECKS BEFORE RETURNING:**

✅ All string fields with options use EXACT values from schema (case-sensitive)
✅ Numeric fields are actual numbers or `null`, never strings
✅ Boolean fields are `true` or `false`, never strings
✅ respiratoryIndication is an array of integers `[]` or `[2, 5]`
✅ "N/A" is used consistently for unmention string fields
✅ No fields are missing from output JSON

---

**COMMON EXTRACTION ERRORS TO AVOID:**

❌ Don't fabricate clinical information and don't use "No" for absence of information - use "N/A"
❌ Don't convert "95%" to string "95%" - use numeric 95
❌ Don't use partial matches for enum fields (e.g., "reduced" → must specify Rt/Lt/Bilateral)
❌ Don't assume defaults - volume_targeting and calco stay `false` unless mentioned
❌ Don't add fields not in schema
❌ Don't use undefined enum values (only use values listed in schema)

---

**OUTPUT FORMAT:**

Return ONLY the JSON object. No markdown code blocks, no explanations, no additional text.

Begin extraction now.
```

---

## Part 3: Python Implementation Example

### Complete Extraction Pipeline

```python
import google.generativeai as genai
import json
import os
from typing import Dict, Optional
from datetime import datetime

class RespiratoryParameterExtractor:
    """Extract respiratory parameters from multilingual audio using Gemini"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini model"""
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=api_key)
        
        # Model for transcription (audio input)
        self.transcription_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",  # Fast for audio
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 2048,
            }
        )
        
        # Model for extraction (text input)
        self.extraction_model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",  # Accurate for structured extraction
            generation_config={
                "temperature": 0.0,  # Zero temp for consistency
                "response_mime_type": "application/json",
                "max_output_tokens": 4096,
            }
        )
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """
        Transcribe multilingual medical audio to English text
        
        Args:
            audio_file_path: Path to audio file (mp3, wav, etc.)
            
        Returns:
            Transcribed English text
        """
        
        # Upload audio file
        audio_file = genai.upload_file(audio_file_path)
        
        # Transcription prompt (from Part 1)
        prompt = """You are a specialized medical transcription AI with expertise in Indian clinical settings.

**TASK:** Transcribe this audio accurately into English text.

[Use full prompt from Part 1 above]

Return ONLY the transcribed English text. Begin transcription now."""
        
        # Generate transcription
        response = self.transcription_model.generate_content([audio_file, prompt])
        
        return response.text.strip()
    
    def extract_parameters(self, transcribed_text: str) -> Dict:
        """
        Extract respiratory parameters from transcribed text
        
        Args:
            transcribed_text: English clinical note text
            
        Returns:
            Dictionary with respiratory parameters
        """
        
        # Extraction prompt (from Part 2)
        prompt = f"""You are a specialized clinical data extraction AI for respiratory care documentation.

**TASK:** Extract respiratory monitoring parameters from the transcribed clinical note below and return structured JSON.

**CRITICAL RULES:**
1. ❌ NEVER fabricate clinical information or assume data not explicitly stated
2. ✅ Use "N/A" for any field not mentioned in the text
[Use full prompt from Part 2 above]

**CLINICAL NOTE:**
---
{transcribed_text}
---

Begin extraction now."""
        
        # Generate extraction
        response = self.extraction_model.generate_content(prompt)
        
        # Parse JSON
        try:
            parameters = json.loads(response.text)
            return parameters
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Raw response: {response.text}")
            raise
    
    def process_audio_to_json(self, audio_file_path: str) -> Dict:
        """
        Complete pipeline: audio → transcription → extraction → JSON
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Respiratory parameters as JSON
        """
        
        print("Step 1: Transcribing audio...")
        transcribed_text = self.transcribe_audio(audio_file_path)
        print(f"Transcription: {transcribed_text[:200]}...")
        
        print("\nStep 2: Extracting parameters...")
        parameters = self.extract_parameters(transcribed_text)
        
        print("\nExtraction complete!")
        return parameters
    
    def process_text_to_json(self, clinical_note: str) -> Dict:
        """
        Direct extraction from already-transcribed text
        
        Args:
            clinical_note: Transcribed clinical note text
            
        Returns:
            Respiratory parameters as JSON
        """
        
        print("Extracting parameters from text...")
        parameters = self.extract_parameters(clinical_note)
        
        print("Extraction complete!")
        return parameters


# Usage Example 1: From Audio File
if __name__ == "__main__":
    extractor = RespiratoryParameterExtractor()
    
    # Process audio file
    audio_path = "/path/to/respiratory_assessment.mp3"
    result = extractor.process_audio_to_json(audio_path)
    
    print(json.dumps(result, indent=2))
    
    # Save to file
    with open("respiratory_params.json", "w") as f:
        json.dump(result, f, indent=2)


# Usage Example 2: From Transcribed Text
if __name__ == "__main__":
    extractor = RespiratoryParameterExtractor()
    
    # Already transcribed text
    clinical_note = """
    Patient UHID A12345 assessed at 2025-01-15 10:30:00.
    Severe respiratory distress noted. Patient is on CPAP with FiO2 40%.
    SPO2 is 88%, respiratory rate 65 breaths per minute.
    Moderate retractions present. Air entry reduced bilaterally.
    Chest movements symmetrical. Added sounds present - bilateral crackles.
    Arterial blood gas done. CXR shows bilateral infiltrates suggestive of pneumonia.
    Patient has preterm RDS and sepsis. Surfactant therapy given.
    ET tube in place. No chronic lung disease.
    """
    
    result = extractor.process_text_to_json(clinical_note)
    
    print(json.dumps(result, indent=2))
```

---

## Part 4: Testing Checklist

### Transcription Testing

✅ Test with English-only audio
✅ Test with Tamil + English code-switching
✅ Test with Hindi + English code-switching
✅ Test with heavy medical terminology
✅ Test with poor audio quality
✅ Verify medical terms are preserved correctly
✅ Verify regional terms are translated accurately

### Extraction Testing

✅ Test with all fields present
✅ Test with minimal fields (most should be N/A)
✅ Test with numeric values (respiratoryRate, spo2, lactate)
✅ Test with multiple respiratory indications
✅ Test with enum fields (ventilationType, retractions, etc.)
✅ Verify JSON is valid and matches schema exactly
✅ Test with edge cases (e.g., "not done" vs "N/A")

### Integration Testing

✅ Process 10+ real audio samples end-to-end
✅ Validate JSON against API schema
✅ Test with Supabase insertion
✅ Verify no data loss in pipeline
✅ Check latency (audio → JSON should be <30 seconds)

---

## Part 5: Cost Estimates

### Gemini Pricing (as of 2025)

**Transcription (Gemini 1.5 Flash):**
- Audio input: ~$0.10 per minute
- Average 2-minute respiratory assessment: $0.20

**Extraction (Gemini 1.5 Pro):**
- Input: ~500 tokens (transcribed text)
- Output: ~800 tokens (JSON)
- Cost: ~$0.005 per extraction

**Total per assessment: ~$0.205**

**Monthly volume estimates:**
- 100 assessments/day = 3,000/month
- Monthly cost: ~$615

### Cost Optimization

**Option 1: Use Flash for both (faster, cheaper)**
- Transcription: Flash (same)
- Extraction: Flash instead of Pro
- Cost reduction: ~50% ($0.10 per assessment)
- Trade-off: Slightly lower extraction accuracy

**Option 2: Batch processing**
- Process multiple assessments in parallel
- Reduces API overhead
- Can process 10 assessments in ~45 seconds

---

## Part 6: Error Handling

### Common Issues & Solutions

**Issue 1: JSON parsing fails**
- **Cause:** Gemini occasionally adds markdown
- **Solution:** Strip ```json and ``` from response

```python
def clean_json_response(text: str) -> str:
    """Remove markdown formatting from JSON response"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
```

**Issue 2: Audio file too large**
- **Cause:** Gemini has 20MB file size limit
- **Solution:** Compress audio before upload

```python
from pydub import AudioSegment

def compress_audio(input_path: str, output_path: str):
    """Compress audio to reduce file size"""
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_frame_rate(16000)  # Downsample
    audio = audio.set_channels(1)  # Mono
    audio.export(output_path, format="mp3", bitrate="64k")
```

**Issue 3: Multilingual transcription errors**
- **Cause:** Heavy code-switching confuses model
- **Solution:** Pre-process to detect dominant language

```python
def detect_language(audio_path: str) -> str:
    """Detect primary language in audio"""
    # Use first 10 seconds for detection
    # Implementation depends on your language detection library
    pass
```

---

## Part 7: Integration with Existing System

### Add to Your Current Flow

```python
# In your existing consultation processing
from respiratory_extractor import RespiratoryParameterExtractor

def process_respiratory_assessment(audio_file_path: str, conversation_id: str):
    """Process respiratory assessment and save to Supabase"""
    
    # Initialize extractor
    extractor = RespiratoryParameterExtractor()
    
    # Extract parameters
    parameters = extractor.process_audio_to_json(audio_file_path)
    
    # Add conversation reference
    parameters["conversation_id"] = conversation_id
    parameters["extracted_at"] = datetime.now().isoformat()
    
    # Save to Supabase
    from supabase import create_client
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    
    response = supabase.table("respiratory_parameters").insert(parameters).execute()
    
    return response
```

---

## Notes

- **Transcription prompt** handles multilingual audio → English text
- **Extraction prompt** enforces strict extraction (no fabrication of information)
- **Pipeline** can process audio end-to-end or work with pre-transcribed text
- **Cost-effective** at ~$0.20 per assessment
- **Integrates** with your existing Supabase + React Native stack
- **Accurate** with medical terminology across Indian languages
