"""
Emotion Intervention Definitions and Helpers

This module provides intervention definitions and helper functions for emotion analysis.
With the simplified combined-only emotion mode, the model performs text+audio analysis
in a single call and outputs unified segments directly with mismatch detection.

Legacy congruence analysis functions have been removed - the combined mode handles
mismatch detection internally.

Author: Claude Code
Date: 2025-12-04
Updated: 2026-01-10 (Simplified to combined-only mode)
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Standardized Vocabulary Maps
# ============================================================================
# These maps normalize values from emotion analysis to ensure consistent scoring.

# Mapping for normalizing anxiety levels
# Standard values: None, Mild, Moderate, Severe
ANXIETY_LEVEL_MAP = {
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}

# Mapping for trajectory comparison
# Standard values: Improved, Stable, Worsened
TRAJECTORY_MAP = {
    "improved": 1,
    "stable": 0,
    "worsened": -1,
}

# Mapping for compliance likelihood
# Standard values: High, Moderate, Low, Very Low
COMPLIANCE_LIKELIHOOD_MAP = {
    "high": 4,
    "moderate": 3,
    "low": 2,
    "very low": 1,
}

# Mapping for severity levels (financial concerns, emotions, anxiety)
# Standard values: None, Mild, Moderate, Severe
SEVERITY_MAP = {
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}

# Mapping for doctor communication styles
# Positive styles score higher, negative styles score lower
DOCTOR_STYLE_MAP = {
    # Positive styles (score 3-4)
    "empathetic": 4,
    "collaborative": 3,
    # Neutral styles (score 2)
    "clinical": 2,
    "authoritative": 2,
    # Negative styles (score 0-1)
    "rushed": 1,
    "dismissive": 0,
    "detached": 0,
    "evasive": 0,
}

# Negative doctor styles list for easy checking
NEGATIVE_DOCTOR_STYLES = {"rushed", "dismissive", "detached", "evasive"}

# Negative emotions that may require intervention
NEGATIVE_EMOTIONS = {"Fear", "Anger", "Sadness", "Distress"}


# ============================================================================
# Intervention Configuration
# ============================================================================

# Priority levels with scores (higher = more urgent)
PRIORITY_CRITICAL = 100
PRIORITY_HIGH = 75
PRIORITY_MEDIUM = 50
PRIORITY_LOW = 25

# Intervention definitions
INTERVENTIONS = {
    "URGENT_MENTAL_HEALTH": {
        "name": "Mental health referral suggested",
        "priority": "CRITICAL",
        "priority_score": PRIORITY_CRITICAL,
    },
    "DOCTOR_FOLLOWUP": {
        "name": "Direct doctor follow-up with patient recommended",
        "priority": "HIGH",
        "priority_score": PRIORITY_HIGH,
    },
    "SECOND_OPINION": {
        "name": "Second opinion may benefit patient",
        "priority": "HIGH",
        "priority_score": PRIORITY_HIGH,
    },
    "FINANCIAL_COUNSELING": {
        "name": "Financial counseling recommended",
        "priority": "MEDIUM",
        "priority_score": PRIORITY_MEDIUM,
    },
    "TREATMENT_ADHERENCE_SUPPORT": {
        "name": "Treatment adherence follow-up needed",
        "priority": "MEDIUM",
        "priority_score": PRIORITY_MEDIUM,
    },
    "EMOTIONAL_SUPPORT": {
        "name": "Emotional support and anxiety management recommended",
        "priority": "MEDIUM",
        "priority_score": PRIORITY_MEDIUM,
    },
    "CARE_COORDINATOR": {
        "name": "Care coordinator assignment recommended",
        "priority": "MEDIUM",
        "priority_score": PRIORITY_MEDIUM,
    },
    "PATIENT_FEEDBACK": {
        "name": "Collect patient feedback on consultation experience",
        "priority": "LOW",
        "priority_score": PRIORITY_LOW,
    },
    "TELEHEALTH_OPTION": {
        "name": "Telehealth option recommended for follow-up",
        "priority": "LOW",
        "priority_score": PRIORITY_LOW,
    },
    "FAMILY_INVOLVEMENT": {
        "name": "Family or caregiver involvement suggested",
        "priority": "LOW",
        "priority_score": PRIORITY_LOW,
    },
}

# Threshold for triggering interventions (>= this level)
INTERVENTION_THRESHOLD = 2  # Corresponds to "Moderate" in SEVERITY_MAP


# ============================================================================
# Helper Functions
# ============================================================================

def clean_likelihood_value(likelihood: str) -> str:
    """
    Clean likelihood value by removing percentage suffix.
    Converts "Very Low (0-19%)" to "Very Low", etc.
    """
    if not likelihood:
        return likelihood
    import re
    cleaned = re.sub(r'\s*\(\d+-?\d*%?\)', '', likelihood).strip()
    return cleaned


def get_nested_value(data: Dict, path: str, default: Any = None) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "ANXIETY_PRE_CONSULTATION.level")
        default: Default value if path not found

    Returns:
        Value at path or default
    """
    keys = path.split(".")
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]

    return current if current is not None else default


def check_severity_threshold(value: str, threshold: int = INTERVENTION_THRESHOLD) -> bool:
    """Check if a severity/level value meets the threshold (Moderate or higher)."""
    if not value:
        return False
    normalized = value.lower().strip()
    score = SEVERITY_MAP.get(normalized, ANXIETY_LEVEL_MAP.get(normalized, -1))
    return score >= threshold


def check_compliance_at_risk(value: str) -> bool:
    """Check if compliance likelihood is Low or Very Low."""
    if not value:
        return False
    normalized = value.lower().strip()
    score = COMPLIANCE_LIKELIHOOD_MAP.get(normalized, 99)
    return score <= 2  # Low (2) or Very Low (1)


def check_negative_doctor_style(value: str) -> bool:
    """Check if doctor style is one of the negative styles."""
    if not value:
        return False
    return value.lower().strip() in NEGATIVE_DOCTOR_STYLES


def check_negative_emotion(emotions: List[str]) -> bool:
    """Check if any emotion in the list is a negative emotion."""
    if not emotions:
        return False
    for emotion in emotions:
        if emotion in NEGATIVE_EMOTIONS:
            return True
    return False


def normalize_anxiety_level(level: str) -> int:
    """Normalize anxiety level string to numeric value (0-3)."""
    if not level:
        return 0
    return ANXIETY_LEVEL_MAP.get(level.lower().strip(), 0)


def normalize_severity(severity: str) -> int:
    """Normalize severity level string to numeric value (0-3)."""
    if not severity:
        return 0
    return SEVERITY_MAP.get(severity.lower().strip(), 0)


def normalize_compliance(likelihood: str) -> int:
    """Normalize compliance likelihood string to numeric value (1-4)."""
    if not likelihood:
        return 3  # Default to moderate
    cleaned = clean_likelihood_value(likelihood)
    return COMPLIANCE_LIKELIHOOD_MAP.get(cleaned.lower().strip(), 3)


# ============================================================================
# Intervention Generation for Combined Mode
# ============================================================================

def generate_recommended_interventions(
    unified_segments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate intervention recommendations based on unified emotion segments.

    This function analyzes combined emotion segments (with text_level, audio_level,
    mismatch detection) and generates appropriate interventions.

    Args:
        unified_segments: Dict with unified emotion segment codes as keys
            (ANXIETY_POST_CONSULTATION, FINANCIAL_CONCERNS, etc.)

    Returns:
        Dict with intervention recommendations
    """
    logger.info("[INTERVENTIONS] Generating recommendations from unified segments")

    triggered = []

    # 1. Check anxiety levels (pre and post consultation)
    anxiety_data = unified_segments.get("ANXIETY_POST_CONSULTATION", {})
    pre_level = get_nested_value(anxiety_data, "pre_consultation.level", "none")
    post_level = get_nested_value(anxiety_data, "post_consultation.level", "none")
    anxiety_mismatch = anxiety_data.get("mismatch", False)

    # Check for severe anxiety
    if check_severity_threshold(pre_level, 3) or check_severity_threshold(post_level, 3):
        triggered.append({
            "code": "URGENT_MENTAL_HEALTH",
            **INTERVENTIONS["URGENT_MENTAL_HEALTH"],
            "reason": f"Severe anxiety detected (pre: {pre_level}, post: {post_level})",
            "source_segments": ["ANXIETY_POST_CONSULTATION"],
        })

    # Check for moderate anxiety with mismatch (may indicate hidden distress)
    if anxiety_mismatch and (check_severity_threshold(pre_level, 2) or check_severity_threshold(post_level, 2)):
        triggered.append({
            "code": "EMOTIONAL_SUPPORT",
            **INTERVENTIONS["EMOTIONAL_SUPPORT"],
            "reason": "Text-audio mismatch detected with moderate+ anxiety - patient may be masking distress",
            "source_segments": ["ANXIETY_POST_CONSULTATION"],
        })

    # Check for worsening trajectory
    trajectory = get_nested_value(anxiety_data, "trajectory.trajectory", "stable")
    if trajectory and trajectory.lower() == "worsened":
        triggered.append({
            "code": "DOCTOR_FOLLOWUP",
            **INTERVENTIONS["DOCTOR_FOLLOWUP"],
            "reason": "Anxiety worsened during consultation",
            "source_segments": ["ANXIETY_POST_CONSULTATION"],
        })

    # 2. Check financial concerns
    financial_data = unified_segments.get("FINANCIAL_CONCERNS", {})
    financial_severity = financial_data.get("severity", "none")
    financial_mismatch = financial_data.get("mismatch", False)

    if check_severity_threshold(financial_severity, 2):
        triggered.append({
            "code": "FINANCIAL_COUNSELING",
            **INTERVENTIONS["FINANCIAL_COUNSELING"],
            "reason": f"Financial concern severity: {financial_severity}",
            "source_segments": ["FINANCIAL_CONCERNS"],
        })

    # Hidden financial stress (mismatch where audio reveals more)
    if financial_mismatch:
        audio_severity = financial_data.get("audio_severity", "none")
        if normalize_severity(audio_severity) > normalize_severity(financial_data.get("text_severity", "none")):
            triggered.append({
                "code": "CARE_COORDINATOR",
                **INTERVENTIONS["CARE_COORDINATOR"],
                "reason": "Audio reveals financial stress not expressed in words",
                "source_segments": ["FINANCIAL_CONCERNS"],
            })

    # 3. Check treatment compliance
    compliance_data = unified_segments.get("TREATMENT_COMPLIANCE_LIKELIHOOD", {})
    compliance_likelihood = compliance_data.get("likelihood", "moderate")
    compliance_mismatch = compliance_data.get("mismatch", False)

    if check_compliance_at_risk(compliance_likelihood):
        triggered.append({
            "code": "TREATMENT_ADHERENCE_SUPPORT",
            **INTERVENTIONS["TREATMENT_ADHERENCE_SUPPORT"],
            "reason": f"Low compliance likelihood: {compliance_likelihood}",
            "source_segments": ["TREATMENT_COMPLIANCE_LIKELIHOOD"],
        })

    # Mismatch in compliance (verbal agreement but voice shows hesitation)
    if compliance_mismatch:
        audio_likelihood = compliance_data.get("audio_likelihood", "moderate")
        if normalize_compliance(audio_likelihood) < normalize_compliance(compliance_data.get("text_likelihood", "moderate")):
            triggered.append({
                "code": "DOCTOR_FOLLOWUP",
                **INTERVENTIONS["DOCTOR_FOLLOWUP"],
                "reason": "Voice hesitation suggests lower compliance than verbally expressed",
                "source_segments": ["TREATMENT_COMPLIANCE_LIKELIHOOD"],
            })

    # 4. Check other emotions
    other_emotions = unified_segments.get("OTHER_EMOTIONS_DETECTED", {})
    emotions_list = other_emotions.get("emotions_detected", [])
    dominant = other_emotions.get("dominant_emotion", "")
    emotions_mismatch = other_emotions.get("mismatch", False)

    if check_negative_emotion(emotions_list) or dominant in NEGATIVE_EMOTIONS:
        triggered.append({
            "code": "EMOTIONAL_SUPPORT",
            **INTERVENTIONS["EMOTIONAL_SUPPORT"],
            "reason": f"Negative emotions detected: {', '.join(emotions_list) if emotions_list else dominant}",
            "source_segments": ["OTHER_EMOTIONS_DETECTED"],
        })

    # 5. Check doctor communication style
    doctor_style = unified_segments.get("DOCTOR_COMMUNICATION_STYLE", {})
    primary_style = doctor_style.get("primary_style", "")
    style_mismatch = doctor_style.get("mismatch", False)

    if check_negative_doctor_style(primary_style):
        triggered.append({
            "code": "PATIENT_FEEDBACK",
            **INTERVENTIONS["PATIENT_FEEDBACK"],
            "reason": f"Doctor communication style flagged: {primary_style}",
            "source_segments": ["DOCTOR_COMMUNICATION_STYLE"],
        })

    # Sort by priority score (highest first)
    triggered.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    # Deduplicate by code (keep first/highest priority occurrence)
    seen_codes = set()
    unique_triggered = []
    for intervention in triggered:
        if intervention["code"] not in seen_codes:
            seen_codes.add(intervention["code"])
            unique_triggered.append(intervention)

    # Count by priority
    critical_count = sum(1 for i in unique_triggered if i.get("priority") == "CRITICAL")
    high_count = sum(1 for i in unique_triggered if i.get("priority") == "HIGH")
    medium_count = sum(1 for i in unique_triggered if i.get("priority") == "MEDIUM")
    low_count = sum(1 for i in unique_triggered if i.get("priority") == "LOW")

    logger.info(
        f"[INTERVENTIONS] Generated {len(unique_triggered)} interventions "
        f"(CRITICAL={critical_count}, HIGH={high_count}, MEDIUM={medium_count}, LOW={low_count})"
    )

    return {
        "source": "combined",
        "total_triggered": len(unique_triggered),
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "all_triggered": [
            {"code": i["code"], "name": i["name"], "priority": i["priority"], "reason": i.get("reason", "")}
            for i in unique_triggered
        ]
    }


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Constants
    "INTERVENTIONS",
    "INTERVENTION_THRESHOLD",
    "ANXIETY_LEVEL_MAP",
    "SEVERITY_MAP",
    "COMPLIANCE_LIKELIHOOD_MAP",
    "NEGATIVE_EMOTIONS",
    "NEGATIVE_DOCTOR_STYLES",
    # Helper functions
    "get_nested_value",
    "clean_likelihood_value",
    "check_severity_threshold",
    "check_compliance_at_risk",
    "check_negative_doctor_style",
    "check_negative_emotion",
    "normalize_anxiety_level",
    "normalize_severity",
    "normalize_compliance",
    # Main function
    "generate_recommended_interventions",
]
