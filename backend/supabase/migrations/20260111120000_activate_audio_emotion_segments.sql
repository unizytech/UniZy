-- Migration: Activate and enhance AUDIO_* segments for audio-only emotion analysis
-- These segments enable emotion extraction directly from audio (no transcript required)
-- Used when skip_transcription mode is enabled
--
-- This migration:
-- 1. Activates all AUDIO_* segments
-- 2. Enhances prompts and schemas to be richer (closer to COMBINED_* output)
-- 3. Adds missing arrays and fields that can be derived from audio-only analysis
--
-- NOTE: Audio-only segments cannot have mismatch detection (no text to compare)
-- The Python transformer adds source="audio_only" and mismatch=null to outputs

-- ============================================================================
-- 1. AUDIO_PATIENT_ANXIETY - Enhanced with indicators array and pre/post structure
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Patient Voice Anxiety Analysis (Audio-Only)

Assess patient anxiety levels based ONLY on voice characteristics throughout the consultation.

## Severity Levels (use exactly):
- **None**: Calm, steady voice, normal pace, relaxed breathing
- **Mild**: Slight tension, occasional hesitation, minor pitch variations
- **Moderate**: Noticeable voice changes, frequent pace shifts, audible stress
- **Severe**: Significant tremor, voice breaks, extreme pace changes, distress sounds

## Key Voice Indicators to Detect:
- Voice tremor or shakiness
- Pitch variations (higher pitch = stress)
- Speech rate changes (rushed = anxiety, slowed = processing/depression)
- Breath patterns (shallow, sighing, catching breath, gasping)
- Voice breaks or emotional catches
- Filler words increase ("um", "uh")
- Vocal tension or strain
- Volume changes (quieting = withdrawal, louder = agitation)

## Pre-Consultation Assessment (first 2-3 minutes):
Assess initial anxiety from voice at consultation start.
Note specific voice indicators heard.

## Post-Consultation Assessment (last 2-3 minutes):
Assess final anxiety from voice at consultation end.
Compare to initial state.

## Trajectory Assessment:
- **Improved**: Voice became calmer, steadier, more relaxed
- **Stable**: Voice quality remained about the same
- **Worsened**: Voice showed increased stress, tension, or distress

## Required Output:
- pre_consultation: {level, indicators[], rationale, confidence}
- post_consultation: {level, indicators[], rationale, confidence}
- trajectory: Improved/Stable/Worsened
- trajectory_rationale: Explanation of voice change from start to end
- confidence: Overall confidence in voice-based assessment (Low, Medium, High)',

    schema_definition_json = '{
        "type": "object",
        "required": ["pre_consultation", "post_consultation", "trajectory", "confidence"],
        "properties": {
            "pre_consultation": {
                "type": "object",
                "required": ["level", "confidence"],
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["None", "Mild", "Moderate", "Severe"],
                        "description": "Anxiety level from voice at consultation start"
                    },
                    "indicators": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific voice indicators detected (e.g., voice tremor, rapid speech)"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Explanation of voice evidence for this level"
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High"]
                    }
                }
            },
            "post_consultation": {
                "type": "object",
                "required": ["level", "confidence"],
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["None", "Mild", "Moderate", "Severe"],
                        "description": "Anxiety level from voice at consultation end"
                    },
                    "indicators": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific voice indicators detected"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Explanation of voice evidence for this level"
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High"]
                    }
                }
            },
            "trajectory": {
                "type": "string",
                "enum": ["Improved", "Stable", "Worsened"],
                "description": "How anxiety changed from start to end based on voice"
            },
            "trajectory_rationale": {
                "type": "string",
                "description": "Explanation of voice change trajectory"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Overall confidence in voice-based assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_PATIENT_ANXIETY';

-- ============================================================================
-- 2. AUDIO_FINANCIAL_CONCERNS - Enhanced with concerns_present and specific_concerns
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Financial Concern Voice Indicators (Audio-Only)

Detect financial anxiety through voice prosody when cost, payment, or treatment topics arise.

## Severity Levels (use exactly):
- **None**: No voice change when financial topics discussed
- **Mild**: Subtle hesitation or slight pitch change on cost mentions
- **Moderate**: Clear voice stress indicators, noticeable pauses, filler words increase
- **Severe**: Significant voice changes, audible distress, avoidance patterns, voice breaking

## Key Voice Indicators to Detect:
- Pitch elevation when cost mentioned
- Hesitation/pause before responding to cost questions
- Increased filler words ("um", "uh") during payment discussions
- Voice tension or quieting when finances arise
- Avoidance (trailing off, changing subject)
- Sighing when medication/test prices mentioned
- Voice cracking on cost-related questions
- Rushed speech to move past financial topics

## Specific Concerns to Identify (from voice stress timing):
- **Treatment cost**: Voice stress when treatment options discussed
- **Medication cost**: Voice stress at prescription mentions
- **Test/investigation cost**: Voice stress when tests recommended
- **Follow-up cost**: Voice stress at follow-up scheduling
- **General financial**: Overall financial anxiety throughout

## Required Output:
- concerns_present: Boolean - were any financial voice stress indicators detected?
- severity: Overall severity from voice (None, Mild, Moderate, Severe)
- specific_concerns: Array of concern objects with type and voice evidence
- alternative_requested_voice_cue: Did voice suggest interest in cheaper options?
- rationale: Explanation of voice evidence
- confidence: Low/Medium/High',

    schema_definition_json = '{
        "type": "object",
        "required": ["concerns_present", "severity", "confidence"],
        "properties": {
            "concerns_present": {
                "type": "boolean",
                "description": "Were any financial voice stress indicators detected?"
            },
            "severity": {
                "type": "string",
                "enum": ["None", "Mild", "Moderate", "Severe"],
                "description": "Overall severity of financial concern from voice"
            },
            "specific_concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "concern_type": {
                            "type": "string",
                            "description": "Type: Treatment cost, Medication cost, Test cost, Follow-up cost, General financial"
                        },
                        "voice_evidence": {
                            "type": "string",
                            "description": "Specific voice indicator (e.g., pitch elevated when medication price mentioned)"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["Mild", "Moderate", "Severe"]
                        }
                    }
                },
                "description": "Specific financial concerns detected from voice timing"
            },
            "alternative_requested_voice_cue": {
                "type": "boolean",
                "description": "Did voice patterns suggest interest in cheaper alternatives?"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_FINANCIAL_CONCERNS';

-- ============================================================================
-- 3. AUDIO_COMPLIANCE_INDICATORS - Enhanced with factors arrays and barriers
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Treatment Compliance Voice Indicators (Audio-Only)

Assess treatment compliance likelihood from voice confidence and engagement patterns.

## Likelihood Levels (use exactly):
- **High**: Confident voice, immediate agreement, engaged tone, enthusiastic responses
- **Moderate**: Some hesitation but generally positive, occasional uncertain tone
- **Low**: Frequent hesitation, flat responses, voice stress when discussing treatment
- **Very Low**: Consistent reluctance signals, disengagement, audible resistance

## Positive Voice Factors (indicating likely compliance):
- Firm, confident agreement voice
- Immediate acknowledgment (no delay)
- Engaged, responsive tone
- Voice energy when discussing treatment plan
- Questions asked with interested tone
- Affirming sounds ("mm-hmm", "yes") with conviction

## Negative Voice Factors (indicating compliance barriers):
- Hesitant agreement voice
- Delayed responses before accepting
- Flat/monotone when discussing treatment
- Voice trailing off when plan mentioned
- Sighing at medication/follow-up mentions
- Non-committal sounds
- Voice stress at specific treatment aspects

## Barrier Detection (from voice patterns):
- **Financial**: Voice stress at cost mentions
- **Understanding**: Confused tone, hesitation before responses
- **Motivation**: Flat, disengaged voice throughout
- **Fear/Anxiety**: Tremor or stress when discussing treatment specifics
- **Practical/Logistical**: Hesitation at scheduling, timing mentions

## Required Output:
- likelihood: Overall compliance likelihood (High, Moderate, Low, Very Low)
- positive_factors: Array of voice factors supporting compliance
- negative_factors: Array of voice factors indicating barriers
- key_barriers: Array with barrier type, severity, and voice evidence
- rationale: Explanation of voice-based assessment
- confidence: Low/Medium/High',

    schema_definition_json = '{
        "type": "object",
        "required": ["likelihood", "positive_factors", "negative_factors", "confidence"],
        "properties": {
            "likelihood": {
                "type": "string",
                "enum": ["High", "Moderate", "Low", "Very Low"],
                "description": "Overall treatment compliance likelihood from voice"
            },
            "positive_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Voice factors supporting compliance (e.g., confident agreement, engaged tone)"
            },
            "negative_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Voice factors indicating barriers (e.g., hesitant responses, flat tone)"
            },
            "key_barriers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "barrier_type": {
                            "type": "string",
                            "description": "Financial, Understanding, Motivation, Fear/Anxiety, Practical/Logistical"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["Minor", "Moderate", "Major"]
                        },
                        "voice_evidence": {
                            "type": "string",
                            "description": "Specific voice evidence for this barrier"
                        }
                    }
                },
                "description": "Key barriers detected from voice patterns"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of voice evidence supporting this assessment"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_COMPLIANCE_INDICATORS';

-- ============================================================================
-- 4. AUDIO_DOCTOR_STYLE - Enhanced with empathy_indicators, strengths, impact
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Doctor Voice Communication Style (Audio-Only)

Analyze doctor''s communication style based ONLY on voice characteristics.

## Primary Style Categories (use exactly):

**Positive Styles:**
- **Empathetic**: Soft tone, slower pace, voice matching patient distress, warm delivery, gentle modulation
- **Collaborative**: Questioning tone, pauses for patient input, encouraging responses, inclusive voice

**Neutral Styles:**
- **Clinical**: Neutral tone, efficient pace, information-focused, professional, matter-of-fact
- **Authoritative**: Confident tone, directive delivery, clear instructions (can be reassuring)

**Negative Styles:**
- **Rushed**: Fast pace, incomplete sentences, talks over patient, impatient sounds
- **Dismissive**: Sighs at concerns, condescending tone, talks over patient, minimizing voice
- **Detached**: Cold/mechanical tone, no warmth, emotionally unavailable, robotic delivery
- **Evasive**: Hesitant answers, vague tone, avoids direct responses, uncertain delivery

## Voice Warmth Levels:
- **Cold**: Flat, emotionless, distant
- **Neutral**: Professional, neither warm nor cold
- **Warm**: Friendly, approachable, caring undertones
- **Very Warm**: Highly empathetic, nurturing, deeply caring voice

## Key Voice Indicators to Assess:
- Tone consistency throughout consultation
- Voice softening when patient shows distress
- Pace appropriateness for patient comprehension
- Reassurance delivery effectiveness
- Active listening sounds ("mm-hmm", "I see")
- Interruption patterns
- Response timing (immediate vs delayed acknowledgment)

## Empathy Indicators (voice-based):
- Voice softening at patient distress
- Pace slowing for complex explanations
- Warm acknowledgment sounds
- Patient tone matching
- Supportive interjections

## Impact Assessment:
How did doctor''s voice affect patient anxiety? (Reduced/No effect/Increased)

## Required Output:
- primary_style: Dominant voice-based communication style
- secondary_style: Secondary style if applicable
- voice_warmth: Cold/Neutral/Warm/Very Warm
- tone_consistency: How consistent was the tone throughout
- empathy_indicators: Array of empathetic voice behaviors detected
- communication_strengths: Array of positive voice communication aspects
- areas_for_improvement: Array of voice communication weaknesses
- patient_anxiety_impact: Did doctor''s voice Reduce/No effect/Increase patient anxiety?
- clarity_rating: How clear was voice delivery (Excellent/Good/Fair/Poor)
- rationale: Explanation of voice evidence
- confidence: Low/Medium/High',

    schema_definition_json = '{
        "type": "object",
        "required": ["primary_style", "voice_warmth", "patient_anxiety_impact", "confidence"],
        "properties": {
            "primary_style": {
                "type": "string",
                "enum": ["Empathetic", "Collaborative", "Clinical", "Authoritative", "Rushed", "Dismissive", "Detached", "Evasive"],
                "description": "Dominant voice-based communication style"
            },
            "secondary_style": {
                "type": "string",
                "enum": ["Empathetic", "Collaborative", "Clinical", "Authoritative", "Rushed", "Dismissive", "Detached", "Evasive"],
                "description": "Secondary style if applicable"
            },
            "voice_warmth": {
                "type": "string",
                "enum": ["Cold", "Neutral", "Warm", "Very Warm"],
                "description": "Overall warmth in voice"
            },
            "tone_consistency": {
                "type": "string",
                "enum": ["Highly consistent", "Mostly consistent", "Variable", "Inconsistent"],
                "description": "How consistent was the tone throughout consultation"
            },
            "empathy_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Empathetic voice behaviors (e.g., voice softened at patient distress)"
            },
            "communication_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Positive voice communication aspects"
            },
            "areas_for_improvement": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Voice communication areas that could improve"
            },
            "patient_anxiety_impact": {
                "type": "string",
                "enum": ["Reduced", "No effect", "Increased"],
                "description": "How doctor voice affected patient anxiety"
            },
            "clarity_rating": {
                "type": "string",
                "enum": ["Excellent", "Good", "Fair", "Poor"],
                "description": "Clarity of voice delivery"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of voice evidence"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in voice-based assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_DOCTOR_STYLE';

-- ============================================================================
-- 5. AUDIO_INTERACTION_DYNAMICS - Enhanced with rapport_quality
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Voice Interaction Dynamics (Audio-Only)

Assess doctor-patient interaction quality from voice dynamics and turn-taking patterns.

## Turn-Taking Balance:
- **Doctor-dominated**: Doctor speaks significantly more, limited patient voice time
- **Balanced**: Appropriate back-and-forth, both voices heard proportionally
- **Patient-dominated**: Patient speaks most (may indicate anxiety or doctor passivity)

## Conversation Flow:
- **Natural**: Smooth transitions, appropriate pauses, comfortable rhythm
- **Mostly natural**: Minor hesitations but generally flows well
- **Somewhat stilted**: Noticeable awkward pauses or interruptions
- **Stilted**: Frequent interruptions, long awkward silences, uncomfortable

## Mutual Engagement:
- **High**: Both voices actively engaged, responsive sounds, good back-and-forth
- **Medium**: Adequate engagement with some disengagement moments
- **Low**: One or both parties seem disengaged, perfunctory responses

## Voice Interaction Indicators:
- Overlapping speech patterns (interruptions)
- Pause length between speakers
- Natural vs forced transitions
- Response latency (how quickly each responds)
- Acknowledgment sounds frequency
- Energy matching between speakers
- Voice mirroring (matching pace/tone)

## Rapport Quality:
- **Excellent**: Strong voice connection, natural flow, mutual responsiveness
- **Good**: Positive interaction, minor friction points
- **Fair**: Functional but lacking warmth or connection
- **Poor**: Disconnected, uncomfortable, or conflictual voice patterns

## Required Output:
- turn_taking_balance: Doctor-dominated/Balanced/Patient-dominated
- conversation_flow: Natural/Mostly natural/Somewhat stilted/Stilted
- mutual_engagement: High/Medium/Low
- rapport_quality: Excellent/Good/Fair/Poor
- interaction_indicators: Array of specific voice interaction patterns observed
- rationale: Explanation of interaction patterns observed
- confidence: Low/Medium/High',

    schema_definition_json = '{
        "type": "object",
        "required": ["turn_taking_balance", "conversation_flow", "mutual_engagement", "rapport_quality", "confidence"],
        "properties": {
            "turn_taking_balance": {
                "type": "string",
                "enum": ["Doctor-dominated", "Balanced", "Patient-dominated"],
                "description": "Balance assessment of who dominated the conversation"
            },
            "conversation_flow": {
                "type": "string",
                "enum": ["Natural", "Mostly natural", "Somewhat stilted", "Stilted"],
                "description": "Overall conversation flow quality"
            },
            "mutual_engagement": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": "Level of mutual engagement between doctor and patient"
            },
            "rapport_quality": {
                "type": "string",
                "enum": ["Excellent", "Good", "Fair", "Poor"],
                "description": "Overall doctor-patient rapport quality from voice"
            },
            "interaction_indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific voice interaction patterns (e.g., natural turn-taking, minimal interruptions)"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of interaction patterns observed"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_INTERACTION_DYNAMICS';

-- ============================================================================
-- 6. AUDIO_OTHER_EMOTIONS - Enhanced with emotions_detected array
-- ============================================================================
UPDATE segment_definitions
SET
    prompt_section_text = '### Other Emotions Voice Detection (Audio-Only)

Detect medically relevant emotions beyond anxiety through voice prosody.

## Emotion Categories (use exactly):

| Emotion | Voice Indicators |
|---------|------------------|
| **Fear** | Voice tremor, higher pitch, rushed speech, breath catching |
| **Anger** | Increased volume, faster pace, clipped responses, tension |
| **Sadness** | Flat affect, slower pace, soft/quiet voice, sighing, monotone |
| **Relief** | Audible exhale, voice softening, pace normalization, lighter tone |
| **Distress** | Voice cracking, irregular breathing, pitch instability, crying sounds |
| **Hope** | Voice brightening, increased energy, upward inflection |
| **Frustration** | Sighing, exasperated tone, clipped words, tension |
| **Resignation** | Flat, defeated tone, low energy, trailing off |
| **None** | Neutral prosody throughout, no dominant emotion |

## For Each Emotion Detected:
- Identify the specific emotion
- Assess severity: Mild, Moderate, or Severe
- Note voice evidence (specific indicators heard)
- Rate clinical significance: High, Medium, or Low

## Clinical Significance Guide:
- **High**: Emotion likely to impact treatment decisions or adherence
- **Medium**: Notable but manageable, worth documenting
- **Low**: Minor, unlikely to affect care

## CRITICAL: Flag any voice indicators of suicidal ideation or severe distress

## Emotional Trajectory:
Compare voice at start vs end:
- **Improved**: Emotional state improved (e.g., fear -> relief)
- **Stable**: Emotional state remained similar
- **Worsened**: Emotional state deteriorated

## Required Output:
- emotions_detected: Array of emotion objects with emotion/severity/voice_evidence/clinical_significance
- dominant_emotion: Most prominent emotion from voice
- emotional_trajectory: Improved/Stable/Worsened
- critical_flags: Array of any critical concerns (suicidal ideation, severe distress)
- rationale: Explanation of voice evidence
- confidence: Low/Medium/High',

    schema_definition_json = '{
        "type": "object",
        "required": ["emotions_detected", "dominant_emotion", "emotional_trajectory", "confidence"],
        "properties": {
            "emotions_detected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["emotion", "severity", "clinical_significance"],
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "enum": ["Fear", "Anger", "Sadness", "Relief", "Distress", "Hope", "Frustration", "Resignation", "None"],
                            "description": "The detected emotion"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["Mild", "Moderate", "Severe"],
                            "description": "Severity of the emotion"
                        },
                        "voice_evidence": {
                            "type": "string",
                            "description": "Specific voice indicators (e.g., flat affect, sighing, voice tremor)"
                        },
                        "clinical_significance": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low"],
                            "description": "Clinical significance of this emotion"
                        }
                    }
                },
                "description": "All emotions detected from voice"
            },
            "dominant_emotion": {
                "type": "string",
                "enum": ["Fear", "Anger", "Sadness", "Relief", "Distress", "Hope", "Frustration", "Resignation", "None"],
                "description": "Most prominent emotion from voice"
            },
            "emotional_trajectory": {
                "type": "string",
                "enum": ["Improved", "Stable", "Worsened"],
                "description": "How emotions changed from start to end"
            },
            "critical_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Critical concerns like suicidal ideation or severe distress"
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of voice evidence"
            },
            "confidence": {
                "type": "string",
                "enum": ["Low", "Medium", "High"],
                "description": "Confidence in assessment"
            }
        }
    }'::jsonb
WHERE segment_code = 'AUDIO_OTHER_EMOTIONS';

-- ============================================================================
-- 7. Activate all AUDIO_* segments
-- ============================================================================
UPDATE segment_definitions
SET is_active = TRUE
WHERE segment_code IN (
    'AUDIO_PATIENT_ANXIETY',
    'AUDIO_FINANCIAL_CONCERNS',
    'AUDIO_COMPLIANCE_INDICATORS',
    'AUDIO_DOCTOR_STYLE',
    'AUDIO_INTERACTION_DYNAMICS',
    'AUDIO_OTHER_EMOTIONS'
);

-- ============================================================================
-- 8. Log the changes
-- ============================================================================
DO $$
DECLARE
    activated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO activated_count
    FROM segment_definitions
    WHERE segment_code LIKE 'AUDIO_%' AND is_active = TRUE;

    RAISE NOTICE 'Enhanced and activated % AUDIO_* segments for audio-only emotion analysis', activated_count;
    RAISE NOTICE 'Segments now have richer schemas with arrays and additional fields';
    RAISE NOTICE 'Run template reassembly after applying this migration';
END $$;
