"""
Emotion Transformer Module

Transforms emotion segments from source formats (AUDIO_*, COMBINED_*) to unified format
for consistent storage and UI display.

Supported modes:
- Combined mode: text + audio in single call (primary mode)
- Audio-only mode: for skip_transcription (direct audio extraction without transcript)

Unified segment codes (stored in extraction_segments table):
- ANXIETY_POST_CONSULTATION
- FINANCIAL_CONCERNS
- OTHER_EMOTIONS_DETECTED
- TREATMENT_COMPLIANCE_LIKELIHOOD
- DOCTOR_COMMUNICATION_STYLE
- INTERACTION_DYNAMICS
- CONGRUENCE_SUMMARY (combined mode only - requires text+audio comparison)

Each unified segment includes a 'source' field indicating origin:
- "combined": From multimodal extraction (text + audio)
- "audio_only": From audio-only extraction (skip_transcription mode)

Author: Claude Code
Date: 2025-12-26
Updated: 2026-01-11 (Restored audio-only mode for skip_transcription)
Updated: 2026-01-11 (Enhanced AUDIO_* schema support with arrays and additional fields)
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Unified segment codes
UNIFIED_EMOTION_SEGMENT_CODES = [
    "ANXIETY_POST_CONSULTATION",
    "FINANCIAL_CONCERNS",
    "OTHER_EMOTIONS_DETECTED",
    "TREATMENT_COMPLIANCE_LIKELIHOOD",
    "DOCTOR_COMMUNICATION_STYLE",
    "INTERACTION_DYNAMICS",
    "CONGRUENCE_SUMMARY"
]

# Severity level to numeric score mapping
SEVERITY_SCORE_MAP = {
    "none": 0.0,
    "mild": 0.33,
    "moderate": 0.66,
    "severe": 1.0
}


def _calculate_score(level: Optional[str]) -> float:
    """Convert severity level string to numeric score (0.0-1.0)."""
    if not level:
        return 0.0
    return SEVERITY_SCORE_MAP.get(level.lower().strip(), 0.0)


def _calculate_compliance_score(likelihood: Optional[str]) -> float:
    """Convert compliance likelihood to numeric score."""
    if not likelihood:
        return 0.5

    likelihood_map = {
        "high": 0.9,
        "moderate": 0.6,
        "low": 0.3,
        "very low": 0.1
    }
    return likelihood_map.get(likelihood.lower().strip(), 0.5)


# =============================================================================
# AUDIO TO UNIFIED TRANSFORMATION (For skip_transcription mode)
# =============================================================================

def transform_audio_to_unified(audio_emotions: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform AUDIO_* segments to unified format.

    Used for skip_transcription mode where only audio-based emotion extraction runs.

    Mapping:
    - AUDIO_PATIENT_ANXIETY -> ANXIETY_POST_CONSULTATION
    - AUDIO_FINANCIAL_CONCERNS -> FINANCIAL_CONCERNS
    - AUDIO_OTHER_EMOTIONS -> OTHER_EMOTIONS_DETECTED
    - AUDIO_COMPLIANCE_INDICATORS -> TREATMENT_COMPLIANCE_LIKELIHOOD
    - AUDIO_DOCTOR_STYLE -> DOCTOR_COMMUNICATION_STYLE
    - AUDIO_INTERACTION_DYNAMICS -> INTERACTION_DYNAMICS

    Note: CONGRUENCE_SUMMARY is not generated in audio-only mode (requires text+audio comparison).

    Args:
        audio_emotions: Dict with AUDIO_* segment codes as keys

    Returns:
        Dict with unified segment codes as keys, all with source="audio_only" and mismatch=None
    """
    logger.info("[EMOTION_TRANSFORMER] Transforming audio emotions to unified format")

    unified = {}

    # 1. ANXIETY_POST_CONSULTATION (from AUDIO_PATIENT_ANXIETY)
    # Enhanced schema has pre_consultation/post_consultation nested objects
    audio_anxiety = audio_emotions.get("AUDIO_PATIENT_ANXIETY", {})
    if audio_anxiety:
        # Handle both old schema (initial_anxiety_level) and new schema (pre_consultation)
        pre_data = audio_anxiety.get("pre_consultation", {})
        post_data = audio_anxiety.get("post_consultation", {})

        # Fall back to old schema fields if new structure not present
        pre_level = pre_data.get("level") if pre_data else audio_anxiety.get("initial_anxiety_level")
        post_level = post_data.get("level") if post_data else audio_anxiety.get("final_anxiety_level")
        pre_indicators = pre_data.get("indicators", []) if pre_data else []
        post_indicators = post_data.get("indicators", []) if post_data else []
        pre_rationale = pre_data.get("rationale") if pre_data else audio_anxiety.get("rationale")
        post_rationale = post_data.get("rationale") if post_data else audio_anxiety.get("rationale")

        trajectory = audio_anxiety.get("trajectory") or audio_anxiety.get("anxiety_trajectory")
        trajectory_rationale = audio_anxiety.get("trajectory_rationale", "")

        unified["ANXIETY_POST_CONSULTATION"] = {
            "pre_consultation": {
                "level": pre_level,
                "source": "audio_only",
                "mismatch": None,  # No text comparison in audio-only mode
                "rationale": pre_rationale,
                "text_level": None,
                "audio_level": pre_level,
                "indicators": pre_indicators,
                "combined_score": _calculate_score(pre_level)
            },
            "post_consultation": {
                "level": post_level,
                "source": "audio_only",
                "mismatch": None,
                "rationale": post_rationale,
                "text_level": None,
                "audio_level": post_level,
                "indicators": post_indicators,
                "combined_score": _calculate_score(post_level)
            },
            "trajectory": {
                "trajectory": trajectory,
                "text_change": None,
                "audio_trajectory": trajectory,
                "rationale": trajectory_rationale,
                "mismatch": None
            },
            "source": "audio_only",
            "mismatch": None,
            "confidence": audio_anxiety.get("confidence") or "Medium",
            "indicators": pre_indicators + post_indicators,  # Combined indicators
            "timestamp_end": None
        }

    # 2. FINANCIAL_CONCERNS (from AUDIO_FINANCIAL_CONCERNS)
    # Enhanced schema has concerns_present, specific_concerns array
    audio_financial = audio_emotions.get("AUDIO_FINANCIAL_CONCERNS", {})
    if audio_financial:
        severity = audio_financial.get("severity")
        rationale = audio_financial.get("rationale")

        # Use concerns_present from schema if available, otherwise derive from severity
        concerns_present = audio_financial.get("concerns_present")
        if concerns_present is None:
            concerns_present = severity and severity.lower() not in ["none", ""]

        # Get specific_concerns from enhanced schema
        specific_concerns = audio_financial.get("specific_concerns", [])

        # Transform specific_concerns to unified format (add source field)
        unified_concerns = []
        for concern in specific_concerns:
            unified_concerns.append({
                "concern_type": concern.get("concern_type"),
                "evidence": concern.get("voice_evidence"),
                "source": "audio",
                "impact_on_compliance": concern.get("severity")
            })

        unified["FINANCIAL_CONCERNS"] = {
            "concerns_present": concerns_present,
            "severity": severity,
            "specific_concerns": unified_concerns,
            "alternative_treatment_requested": audio_financial.get("alternative_requested_voice_cue", False),
            "source": "audio_only",
            "mismatch": None,
            "text_severity": None,
            "audio_severity": severity,
            "combined_score": _calculate_score(severity),
            "rationale": rationale,
            "confidence": audio_financial.get("confidence") or "Medium",
            "notes": rationale
        }

    # 3. OTHER_EMOTIONS_DETECTED (from AUDIO_OTHER_EMOTIONS)
    # Enhanced schema has emotions_detected array with severity and clinical_significance
    audio_other = audio_emotions.get("AUDIO_OTHER_EMOTIONS", {})
    if audio_other:
        dominant = audio_other.get("dominant_emotion")
        trajectory = audio_other.get("emotional_trajectory")
        rationale = audio_other.get("rationale")
        critical_flags = audio_other.get("critical_flags", [])

        # Get emotions_detected from enhanced schema
        emotions_detected_raw = audio_other.get("emotions_detected", [])

        # Transform to unified format (add audio_evidence -> evidence)
        emotions_detected = []
        for em in emotions_detected_raw:
            emotions_detected.append({
                "emotion": em.get("emotion"),
                "severity": em.get("severity"),
                "text_evidence": [],  # No text in audio-only mode
                "audio_evidence": em.get("voice_evidence"),
                "clinical_significance": em.get("clinical_significance")
            })

        # If no emotions_detected array but we have dominant, create one
        if not emotions_detected and dominant and dominant.lower() != "none":
            emotions_detected = [{
                "emotion": dominant,
                "severity": "Moderate",
                "text_evidence": [],
                "audio_evidence": rationale,
                "clinical_significance": "Medium"
            }]

        unified["OTHER_EMOTIONS_DETECTED"] = {
            "emotions_detected": emotions_detected,
            "dominant_emotion": dominant,
            "source": "audio_only",
            "mismatch": None,
            "text_emotions": None,
            "audio_dominant": dominant,
            "rationale": rationale,
            "confidence": audio_other.get("confidence") or "Medium",
            "notes": rationale,
            "emotional_trajectory": trajectory,
            "critical_flags": critical_flags
        }

    # 4. TREATMENT_COMPLIANCE_LIKELIHOOD (from AUDIO_COMPLIANCE_INDICATORS)
    # Enhanced schema has positive_factors, negative_factors, key_barriers arrays
    audio_compliance = audio_emotions.get("AUDIO_COMPLIANCE_INDICATORS", {})
    if audio_compliance:
        likelihood = audio_compliance.get("likelihood")
        rationale = audio_compliance.get("rationale")

        # Get arrays from enhanced schema
        positive_factors = audio_compliance.get("positive_factors", [])
        negative_factors = audio_compliance.get("negative_factors", [])
        key_barriers_raw = audio_compliance.get("key_barriers", [])

        # Transform key_barriers to unified format
        key_barriers = []
        for barrier in key_barriers_raw:
            key_barriers.append({
                "barrier_type": barrier.get("barrier_type"),
                "severity": barrier.get("severity"),
                "evidence": barrier.get("voice_evidence"),
                "source": "audio"
            })

        unified["TREATMENT_COMPLIANCE_LIKELIHOOD"] = {
            "likelihood": likelihood,
            "positive_factors": positive_factors,
            "negative_factors": negative_factors,
            "key_barriers": key_barriers,
            "recommendations": [],  # Recommendations not generated in audio-only
            "confidence": audio_compliance.get("confidence") or "Medium",
            "source": "audio_only",
            "mismatch": None,
            "text_likelihood": None,
            "audio_likelihood": likelihood,
            "combined_score": _calculate_compliance_score(likelihood),
            "rationale": rationale,
            "notes": rationale
        }

    # 5. DOCTOR_COMMUNICATION_STYLE (from AUDIO_DOCTOR_STYLE)
    # Enhanced schema has empathy_indicators, communication_strengths, areas_for_improvement arrays
    audio_doctor = audio_emotions.get("AUDIO_DOCTOR_STYLE", {})
    if audio_doctor:
        primary_style = audio_doctor.get("primary_style")
        secondary_style = audio_doctor.get("secondary_style")
        voice_warmth = audio_doctor.get("voice_warmth")
        tone_consistency = audio_doctor.get("tone_consistency")
        rationale = audio_doctor.get("rationale")

        # Get arrays and additional fields from enhanced schema
        empathy_indicators = audio_doctor.get("empathy_indicators", [])
        communication_strengths = audio_doctor.get("communication_strengths", [])
        areas_for_improvement = audio_doctor.get("areas_for_improvement", [])
        patient_anxiety_impact = audio_doctor.get("patient_anxiety_impact")
        clarity_rating = audio_doctor.get("clarity_rating")

        unified["DOCTOR_COMMUNICATION_STYLE"] = {
            "primary_style": primary_style,
            "secondary_style": secondary_style,
            "empathy_indicators": empathy_indicators,
            "communication_strengths": communication_strengths,
            "areas_for_improvement": areas_for_improvement,
            "patient_anxiety_impact": patient_anxiety_impact,
            "clarity_rating": clarity_rating,
            "source": "audio_only",
            "mismatch": None,
            "text_style": None,
            "audio_style": primary_style,
            "voice_warmth": voice_warmth,
            "tone_consistency": tone_consistency,
            "rationale": rationale,
            "confidence": audio_doctor.get("confidence") or "Medium",
            "notes": rationale
        }

    # 6. INTERACTION_DYNAMICS (from AUDIO_INTERACTION_DYNAMICS)
    # Enhanced schema has rapport_quality and interaction_indicators array
    audio_interaction = audio_emotions.get("AUDIO_INTERACTION_DYNAMICS", {})
    if audio_interaction:
        interaction_indicators = audio_interaction.get("interaction_indicators", [])

        unified["INTERACTION_DYNAMICS"] = {
            "turn_taking_balance": audio_interaction.get("turn_taking_balance"),
            "conversation_flow": audio_interaction.get("conversation_flow"),
            "mutual_engagement": audio_interaction.get("mutual_engagement"),
            "rapport_quality": audio_interaction.get("rapport_quality"),
            "interaction_indicators": interaction_indicators,
            "source": "audio_only",
            "mismatch": None,
            "text_turn_pattern": None,
            "audio_turn_pattern": audio_interaction.get("turn_taking_balance"),
            "text_flow": None,
            "audio_flow": audio_interaction.get("conversation_flow"),
            "text_engagement": None,
            "audio_engagement": audio_interaction.get("mutual_engagement"),
            "rationale": audio_interaction.get("rationale"),
            "confidence": audio_interaction.get("confidence", "Medium"),
            "notes": audio_interaction.get("notes")
        }

    # Note: CONGRUENCE_SUMMARY is NOT generated in audio-only mode
    # (requires both text+audio for mismatch comparison)

    logger.info(f"[EMOTION_TRANSFORMER] Transformed {len(unified)} audio emotion segments to unified format")
    return unified


# =============================================================================
# COMBINED TO UNIFIED TRANSFORMATION
# =============================================================================

def transform_combined_to_unified(combined_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transform COMBINED_* segments from multimodal extraction to unified format.

    Mapping:
    - COMBINED_ANXIETY -> ANXIETY_POST_CONSULTATION
    - COMBINED_FINANCIAL_CONCERNS -> FINANCIAL_CONCERNS
    - COMBINED_OTHER_EMOTIONS -> OTHER_EMOTIONS_DETECTED
    - COMBINED_COMPLIANCE -> TREATMENT_COMPLIANCE_LIKELIHOOD
    - COMBINED_DOCTOR_STYLE -> DOCTOR_COMMUNICATION_STYLE

    Note: With simplified emotion architecture, the extract_combined_emotions()
    function in gemini_service.py already returns unified segments directly.
    This function is kept for any edge case transformations or validation.

    Args:
        combined_segments: List of combined segment dicts from multimodal extraction

    Returns:
        Dict with unified segment codes as keys
    """
    logger.info("[EMOTION_TRANSFORMER] Transforming combined segments to unified format")

    # Build lookup by segment_code
    segment_map = {}
    for seg in combined_segments:
        code = seg.get("segment_code", "")
        segment_map[code] = seg

    unified = {}

    # 1. ANXIETY_POST_CONSULTATION (from COMBINED_ANXIETY)
    combined_anxiety = segment_map.get("COMBINED_ANXIETY", {})
    if combined_anxiety:
        unified["ANXIETY_POST_CONSULTATION"] = {
            "pre_consultation": combined_anxiety.get("pre_consultation", {}),
            "post_consultation": combined_anxiety.get("post_consultation", {}),
            "trajectory": combined_anxiety.get("trajectory", {}),
            "source": "combined",
            "mismatch": combined_anxiety.get("pre_consultation", {}).get("mismatch", False) or
                       combined_anxiety.get("post_consultation", {}).get("mismatch", False),
            "confidence": combined_anxiety.get("confidence", "Medium"),
            "indicators": [],
            "timestamp_end": None
        }

    # 2. FINANCIAL_CONCERNS (from COMBINED_FINANCIAL_CONCERNS)
    combined_financial = segment_map.get("COMBINED_FINANCIAL_CONCERNS", {})
    if combined_financial:
        unified["FINANCIAL_CONCERNS"] = {
            "concerns_present": combined_financial.get("concerns_present", False),
            "severity": combined_financial.get("severity"),
            "specific_concerns": combined_financial.get("specific_concerns", []),
            "alternative_treatment_requested": combined_financial.get("alternative_treatment_requested", False),
            "source": "combined",
            "mismatch": combined_financial.get("mismatch", False),
            "text_severity": combined_financial.get("text_severity"),
            "audio_severity": combined_financial.get("audio_severity"),
            "combined_score": combined_financial.get("combined_score", 0),
            "rationale": combined_financial.get("rationale"),
            "confidence": combined_financial.get("confidence", "Medium"),
            "notes": combined_financial.get("notes")
        }

    # 3. OTHER_EMOTIONS_DETECTED (from COMBINED_OTHER_EMOTIONS)
    combined_emotions = segment_map.get("COMBINED_OTHER_EMOTIONS", {})
    if combined_emotions:
        unified["OTHER_EMOTIONS_DETECTED"] = {
            "emotions_detected": combined_emotions.get("emotions_detected", []),
            "dominant_emotion": combined_emotions.get("dominant_emotion"),
            "source": "combined",
            "mismatch": combined_emotions.get("mismatch", False),
            "text_emotions": combined_emotions.get("text_emotions"),
            "audio_dominant": combined_emotions.get("audio_dominant"),
            "rationale": combined_emotions.get("rationale"),
            "confidence": combined_emotions.get("confidence", "Medium"),
            "notes": combined_emotions.get("notes"),
            "emotional_trajectory": combined_emotions.get("emotional_trajectory"),
            "critical_flags": combined_emotions.get("critical_flags", [])
        }

    # 4. TREATMENT_COMPLIANCE_LIKELIHOOD (from COMBINED_COMPLIANCE)
    combined_compliance = segment_map.get("COMBINED_COMPLIANCE", {})
    if combined_compliance:
        unified["TREATMENT_COMPLIANCE_LIKELIHOOD"] = {
            "likelihood": combined_compliance.get("likelihood"),
            "positive_factors": combined_compliance.get("positive_factors", []),
            "negative_factors": combined_compliance.get("negative_factors", []),
            "key_barriers": combined_compliance.get("key_barriers", []),
            "recommendations": combined_compliance.get("recommendations", []),
            "confidence": combined_compliance.get("confidence", "Medium"),
            "source": "combined",
            "mismatch": combined_compliance.get("mismatch", False),
            "text_likelihood": combined_compliance.get("text_likelihood"),
            "audio_likelihood": combined_compliance.get("audio_likelihood"),
            "combined_score": combined_compliance.get("combined_score", 0),
            "rationale": combined_compliance.get("rationale"),
            "notes": combined_compliance.get("notes")
        }

    # 5. DOCTOR_COMMUNICATION_STYLE (from COMBINED_DOCTOR_STYLE)
    combined_doctor = segment_map.get("COMBINED_DOCTOR_STYLE", {})
    if combined_doctor:
        unified["DOCTOR_COMMUNICATION_STYLE"] = {
            "primary_style": combined_doctor.get("primary_style"),
            "secondary_style": combined_doctor.get("secondary_style"),
            "empathy_indicators": combined_doctor.get("empathy_indicators", []),
            "communication_strengths": combined_doctor.get("communication_strengths", []),
            "areas_for_improvement": combined_doctor.get("areas_for_improvement", []),
            "patient_anxiety_impact": combined_doctor.get("patient_anxiety_impact"),
            "clarity_rating": combined_doctor.get("clarity_rating"),
            "source": "combined",
            "mismatch": combined_doctor.get("mismatch", False),
            "text_style": combined_doctor.get("text_style"),
            "audio_style": combined_doctor.get("audio_style"),
            "voice_warmth": combined_doctor.get("voice_warmth"),
            "tone_consistency": combined_doctor.get("tone_consistency"),
            "rationale": combined_doctor.get("rationale"),
            "confidence": combined_doctor.get("confidence", "Medium"),
            "notes": combined_doctor.get("notes")
        }

    # 6. INTERACTION_DYNAMICS (from COMBINED_INTERACTION_DYNAMICS) - New in Jan 2026
    combined_interaction = segment_map.get("COMBINED_INTERACTION_DYNAMICS", {})
    if combined_interaction:
        unified["INTERACTION_DYNAMICS"] = {
            "turn_taking_balance": combined_interaction.get("turn_taking_balance"),
            "conversation_flow": combined_interaction.get("conversation_flow"),
            "mutual_engagement": combined_interaction.get("mutual_engagement"),
            "rapport_quality": combined_interaction.get("rapport_quality"),
            "interaction_indicators": combined_interaction.get("interaction_indicators", []),
            "source": "combined",
            "mismatch": combined_interaction.get("mismatch", False),
            "text_turn_pattern": combined_interaction.get("text_turn_pattern"),
            "audio_turn_pattern": combined_interaction.get("audio_turn_pattern"),
            "text_flow": combined_interaction.get("text_flow"),
            "audio_flow": combined_interaction.get("audio_flow"),
            "text_engagement": combined_interaction.get("text_engagement"),
            "audio_engagement": combined_interaction.get("audio_engagement"),
            "rationale": combined_interaction.get("rationale"),
            "confidence": combined_interaction.get("confidence", "Medium"),
            "notes": combined_interaction.get("notes")
        }

    # 7. CONGRUENCE_SUMMARY (from COMBINED_CONGRUENCE_SUMMARY) - New in Jan 2026
    # Replaces the old EMOTION_CONGRUENCE_ANALYSIS segment
    combined_congruence = segment_map.get("COMBINED_CONGRUENCE_SUMMARY", {})
    if combined_congruence:
        unified["CONGRUENCE_SUMMARY"] = {
            # Keep congruence_score for backward compatibility with consultation_insights_prompts.py
            "congruence_score": combined_congruence.get("overall_congruence_score"),
            "overall_congruence_score": combined_congruence.get("overall_congruence_score"),
            "congruence_level": combined_congruence.get("congruence_level"),
            "total_mismatches": combined_congruence.get("total_mismatches", 0),
            "mismatch_summary": combined_congruence.get("mismatch_summary"),
            "incongruent_moments": combined_congruence.get("incongruent_moments", []),
            "clinical_recommendations": combined_congruence.get("clinical_recommendations", []),
            "intervention_priority": combined_congruence.get("intervention_priority"),
            "key_findings": combined_congruence.get("key_findings", []),
            "areas_of_concern": combined_congruence.get("areas_of_concern", []),
            "source": "combined",
            "confidence": combined_congruence.get("confidence", "Medium")
        }

    logger.info(f"[EMOTION_TRANSFORMER] Transformed {len(unified)} combined segments to unified format")
    return unified


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "UNIFIED_EMOTION_SEGMENT_CODES",
    "SEVERITY_SCORE_MAP",
    "transform_audio_to_unified",
    "transform_combined_to_unified",
    "_calculate_score",
    "_calculate_compliance_score",
]
