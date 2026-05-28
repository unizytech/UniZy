"""
Take-Up Likelihood Prediction Service

Predicts the likelihood (0-100) that a patient will accept and follow through
with each intervention based on:
- Clinical severity (from clinical_severity_assessments)
- Anxiety (post-consultation level + trajectory from patient_dropoff_risk)
- Financial concerns (from patient_dropoff_risk)
- Compliance likelihood (from patient_dropoff_risk)
- Fear/Distress emotions (from OTHER_EMOTIONS_DETECTED segment)

Category-specific weights allow REVENUE, RETENTION, and QUALITY interventions
to have different prediction formulas.

Author: Unizy Health
Version: 1.0.0
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration Loading
# ============================================================================

_config_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load take_up_prediction config from intervention_config.json."""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "references",
        "intervention_config.json"
    )

    try:
        with open(config_path, "r") as f:
            full_config = json.load(f)
            _config_cache = full_config.get("take_up_prediction", {})
            return _config_cache
    except Exception as e:
        logger.warning(f"[TAKE_UP] Failed to load config: {e}. Using defaults.")
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """Return default configuration if file not found."""
    return {
        "enabled": True,
        "category_weights": {
            "REVENUE": {"severity": 0.15, "anxiety": 0.20, "financial": 0.40, "compliance": 0.25},
            "RETENTION": {"severity": 0.15, "anxiety": 0.35, "financial": 0.15, "compliance": 0.35},
            "QUALITY": {"severity": 0.50, "anxiety": 0.10, "financial": 0.10, "compliance": 0.30}
        },
        "signal_mappings": {
            "severity": {"LOW": 30, "MEDIUM": 60, "HIGH": 90},
            "anxiety_post_level": {"None": 20, "Mild": 40, "Moderate": 65, "Severe": 90},
            "financial": {"none": 100, "mild": 70, "moderate": 40, "severe": 20},
            "compliance": {"high": 90, "moderate": 60, "low": 35, "very_low": 15}
        },
        "anxiety_calculation": {
            "post_level_weight": 0.60,
            "trajectory_weight": 0.40,
            "trajectory_modifiers": {"Improved": 20, "Stable": 0, "Worsened": -30}
        },
        "fear_distress_boost": {
            "enabled": True,
            "emotions": ["Fear", "Distress"],
            "severity_boosts": {"Mild": 10, "Moderate": 20, "Severe": 30},
            "categories": ["REVENUE", "RETENTION"]
        },
        "priority_adjustment": {
            "high_threshold": 70,
            "low_threshold": 40,
            "high_modifier": 1.15,
            "medium_modifier": 1.0,
            "low_modifier": 0.85,
            "min_score": 20,
            "max_score": 99
        },
        "rules": {}
    }


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TakeUpSignals:
    """Input signals for take-up prediction."""
    # From clinical_severity_assessments
    clinical_severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH

    # From patient_dropoff_risk (reused, not recalculated)
    anxiety_post_level: str = "None"  # None, Mild, Moderate, Severe
    anxiety_trajectory: str = "Stable"  # Improved, Stable, Worsened, Unable to determine
    financial_concern: str = "none"  # none, mild, moderate, severe
    compliance_likelihood: str = "moderate"  # high, moderate, low, very_low

    # From OTHER_EMOTIONS_DETECTED segment
    emotions_detected: List[Dict[str, str]] = field(default_factory=list)
    # Each emotion: {"emotion": "Fear", "severity": "Moderate"}


@dataclass
class TakeUpPrediction:
    """Result of take-up likelihood prediction."""
    take_up_likelihood: int  # 0-100
    signal_contributions: Dict[str, float]  # Breakdown by signal
    rules_applied: List[str]  # Names of rules that were applied
    priority_modifier: float  # Multiplier for priority_score
    fear_distress_boost_applied: int  # Additional boost from fear/distress


# ============================================================================
# Core Prediction Logic
# ============================================================================

def predict_take_up_likelihood(
    signals: TakeUpSignals,
    category: str,
    config: Optional[Dict[str, Any]] = None
) -> TakeUpPrediction:
    """
    Calculate take-up likelihood for an intervention.

    Args:
        signals: Input signals from existing assessments
        category: Intervention category (REVENUE, RETENTION, QUALITY)
        config: Optional config override (defaults to intervention_config.json)

    Returns:
        TakeUpPrediction with likelihood, breakdown, and priority modifier
    """
    config = config or _load_config()

    if not config.get("enabled", True):
        # Return neutral prediction if disabled
        return TakeUpPrediction(
            take_up_likelihood=50,
            signal_contributions={},
            rules_applied=["prediction_disabled"],
            priority_modifier=1.0,
            fear_distress_boost_applied=0
        )

    # Get category-specific weights
    category_weights = config.get("category_weights", {}).get(category, {})
    if not category_weights:
        # Fall back to RETENTION weights as default
        category_weights = config.get("category_weights", {}).get("RETENTION", {
            "severity": 0.15, "anxiety": 0.35, "financial": 0.15, "compliance": 0.35
        })

    signal_mappings = config.get("signal_mappings", {})

    # =========================================================================
    # Step 1: Map signals to scores
    # =========================================================================

    # Severity score
    severity_map = signal_mappings.get("severity", {"LOW": 30, "MEDIUM": 60, "HIGH": 90})
    severity_score = severity_map.get(signals.clinical_severity.upper(), 60)

    # Anxiety combined score (60% post-level + 40% trajectory modifier)
    anxiety_score = _calculate_anxiety_score(
        signals.anxiety_post_level,
        signals.anxiety_trajectory,
        config
    )

    # Financial score (inverted: high concern = low score for take-up)
    financial_map = signal_mappings.get("financial", {"none": 100, "mild": 70, "moderate": 40, "severe": 20})
    financial_score = financial_map.get(signals.financial_concern.lower(), 70)

    # Compliance score
    compliance_map = signal_mappings.get("compliance", {"high": 90, "moderate": 60, "low": 35, "very_low": 15})
    compliance_score = compliance_map.get(signals.compliance_likelihood.lower(), 60)

    # =========================================================================
    # Step 2: Apply category-specific weights
    # =========================================================================

    severity_weight = category_weights.get("severity", 0.25)
    anxiety_weight = category_weights.get("anxiety", 0.25)
    financial_weight = category_weights.get("financial", 0.25)
    compliance_weight = category_weights.get("compliance", 0.25)

    # Calculate weighted base score
    weighted_severity = severity_score * severity_weight
    weighted_anxiety = anxiety_score * anxiety_weight
    weighted_financial = financial_score * financial_weight
    weighted_compliance = compliance_score * compliance_weight

    base_likelihood = weighted_severity + weighted_anxiety + weighted_financial + weighted_compliance

    signal_contributions = {
        "severity": round(weighted_severity, 2),
        "anxiety": round(weighted_anxiety, 2),
        "financial": round(weighted_financial, 2),
        "compliance": round(weighted_compliance, 2),
        "base_total": round(base_likelihood, 2)
    }

    # =========================================================================
    # Step 3: Apply fear/distress boost
    # =========================================================================

    fear_distress_boost = 0
    fear_distress_config = config.get("fear_distress_boost", {})

    if fear_distress_config.get("enabled", True) and category in fear_distress_config.get("categories", ["REVENUE", "RETENTION"]):
        target_emotions = fear_distress_config.get("emotions", ["Fear", "Distress"])
        severity_boosts = fear_distress_config.get("severity_boosts", {"Mild": 10, "Moderate": 20, "Severe": 30})

        for emotion_data in signals.emotions_detected:
            emotion_name = emotion_data.get("emotion", "")
            emotion_severity = emotion_data.get("severity", "")

            if emotion_name in target_emotions:
                boost = severity_boosts.get(emotion_severity, 0)
                if boost > fear_distress_boost:
                    fear_distress_boost = boost

    likelihood_after_boost = base_likelihood + fear_distress_boost
    signal_contributions["fear_distress_boost"] = fear_distress_boost

    # =========================================================================
    # Step 4: Apply override rules
    # =========================================================================

    adjusted_likelihood, rules_applied = _apply_prediction_rules(
        likelihood_after_boost,
        signals,
        category,
        config.get("rules", {})
    )

    # =========================================================================
    # Step 5: Clamp to 0-100 and calculate priority modifier
    # =========================================================================

    final_likelihood = max(0, min(100, int(round(adjusted_likelihood))))

    priority_modifier = _calculate_priority_modifier(final_likelihood, config)

    return TakeUpPrediction(
        take_up_likelihood=final_likelihood,
        signal_contributions=signal_contributions,
        rules_applied=rules_applied,
        priority_modifier=priority_modifier,
        fear_distress_boost_applied=fear_distress_boost
    )


def _calculate_anxiety_score(
    post_level: str,
    trajectory: str,
    config: Dict[str, Any]
) -> float:
    """
    Calculate combined anxiety score per requirements:
    - 60% post-consultation level
    - 40% trajectory modifier

    Higher anxiety = higher take-up (patient seeking help)
    """
    anxiety_config = config.get("anxiety_calculation", {})
    signal_mappings = config.get("signal_mappings", {})

    # Get post-level score
    post_level_map = signal_mappings.get("anxiety_post_level", {
        "None": 20, "Mild": 40, "Moderate": 65, "Severe": 90
    })
    post_score = post_level_map.get(post_level, 40)

    # Get trajectory modifier
    trajectory_modifiers = anxiety_config.get("trajectory_modifiers", {
        "Improved": 20, "Stable": 0, "Worsened": -30, "Unable to determine": 0
    })
    trajectory_mod = trajectory_modifiers.get(trajectory, 0)

    # Weights
    post_weight = anxiety_config.get("post_level_weight", 0.60)
    traj_weight = anxiety_config.get("trajectory_weight", 0.40)

    # Combined score
    # Note: trajectory modifier adjusts the final score, not weighted separately
    # e.g., if post=90 (Severe) and trajectory=Worsened (-30), we get:
    # (90 * 0.6) + (90 * 0.4) + (-30 * 0.4) = 54 + 36 - 12 = 78
    combined = (post_score * post_weight) + (post_score * traj_weight) + (trajectory_mod * traj_weight)

    # Clamp to 0-100
    return max(0, min(100, combined))


def _apply_prediction_rules(
    base_likelihood: float,
    signals: TakeUpSignals,
    category: str,
    rules_config: Dict[str, Any]
) -> Tuple[float, List[str]]:
    """
    Apply specific rules that override weighted calculation.
    Returns adjusted likelihood and list of rules applied.
    """
    adjusted = base_likelihood
    rules_applied = []

    # Rule 1: HIGH severity + HIGH anxiety boost
    rule1 = rules_config.get("high_severity_high_anxiety_boost", {})
    if rule1.get("enabled", False) and category in rule1.get("categories", []):
        conditions = rule1.get("conditions", {})
        severity_match = signals.clinical_severity.upper() == conditions.get("severity", "").upper()
        anxiety_levels = conditions.get("anxiety_post_level", [])
        anxiety_match = signals.anxiety_post_level in anxiety_levels

        if severity_match and anxiety_match:
            boost = rule1.get("boost", 20)
            adjusted += boost
            rules_applied.append(f"high_severity_high_anxiety_boost(+{boost})")

    # Rule 2: LOW severity + HIGH financial penalty
    rule2 = rules_config.get("low_severity_high_financial_penalty", {})
    if rule2.get("enabled", False) and category in rule2.get("categories", []):
        conditions = rule2.get("conditions", {})
        severity_match = signals.clinical_severity.upper() == conditions.get("severity", "").upper()
        financial_levels = conditions.get("financial", [])
        financial_match = signals.financial_concern.lower() in [f.lower() for f in financial_levels]

        if severity_match and financial_match:
            penalty = rule2.get("penalty", 30)
            adjusted -= penalty
            rules_applied.append(f"low_severity_high_financial_penalty(-{penalty})")

    # Rule 3: HIGH fear/distress boost
    rule3 = rules_config.get("high_fear_distress_boost", {})
    if rule3.get("enabled", False) and category in rule3.get("categories", []):
        conditions = rule3.get("conditions", {})
        emotion_conditions = conditions.get("emotions", {})

        for emotion_data in signals.emotions_detected:
            emotion_name = emotion_data.get("emotion", "")
            emotion_severity = emotion_data.get("severity", "")

            if emotion_name in emotion_conditions:
                target_severities = emotion_conditions[emotion_name]
                if emotion_severity in target_severities:
                    boost = rule3.get("boost", 15)
                    adjusted += boost
                    rules_applied.append(f"high_fear_distress_boost(+{boost})")
                    break  # Only apply once

    # Rule 4: Very low compliance penalty
    rule4 = rules_config.get("very_low_compliance_penalty", {})
    if rule4.get("enabled", False) and category in rule4.get("categories", []):
        conditions = rule4.get("conditions", {})
        if signals.compliance_likelihood.lower() == conditions.get("compliance", "").lower():
            penalty = rule4.get("penalty", 20)
            adjusted -= penalty
            rules_applied.append(f"very_low_compliance_penalty(-{penalty})")

    return adjusted, rules_applied


def _calculate_priority_modifier(
    take_up_likelihood: int,
    config: Dict[str, Any]
) -> float:
    """
    Calculate priority_score modifier based on take_up_likelihood.

    HIGH take-up (>=70): boost priority by 15%
    MEDIUM take-up (40-69): no change
    LOW take-up (<40): reduce priority by 15%
    """
    priority_config = config.get("priority_adjustment", {})

    high_threshold = priority_config.get("high_threshold", 70)
    low_threshold = priority_config.get("low_threshold", 40)

    high_modifier = priority_config.get("high_modifier", 1.15)
    medium_modifier = priority_config.get("medium_modifier", 1.0)
    low_modifier = priority_config.get("low_modifier", 0.85)

    if take_up_likelihood >= high_threshold:
        return high_modifier
    elif take_up_likelihood < low_threshold:
        return low_modifier
    else:
        return medium_modifier


def adjust_priority_score(
    base_priority_score: int,
    take_up_likelihood: int,
    config: Optional[Dict[str, Any]] = None
) -> int:
    """
    Adjust priority_score based on take_up_likelihood.
    Uses multiplicative modifier with bounds.

    Args:
        base_priority_score: Original priority score (0-100)
        take_up_likelihood: Predicted take-up likelihood (0-100)
        config: Optional config override

    Returns:
        Adjusted priority score (bounded by min_score and max_score)
    """
    config = config or _load_config()
    priority_config = config.get("priority_adjustment", {})

    modifier = _calculate_priority_modifier(take_up_likelihood, config)

    adjusted = int(round(base_priority_score * modifier))

    # Apply bounds
    min_score = priority_config.get("min_score", 20)
    max_score = priority_config.get("max_score", 99)

    return max(min_score, min(max_score, adjusted))


# ============================================================================
# Helper Functions for Building Signals
# ============================================================================

def build_signals_from_assessments(
    clinical_severity: Optional[Dict[str, Any]] = None,
    dropoff_risk: Optional[Dict[str, Any]] = None,
    other_emotions_segment: Optional[Dict[str, Any]] = None
) -> TakeUpSignals:
    """
    Build TakeUpSignals from existing assessment data.

    Args:
        clinical_severity: Data from clinical_severity_assessments table
        dropoff_risk: Data from patient_dropoff_risk table
        other_emotions_segment: Data from OTHER_EMOTIONS_DETECTED segment

    Returns:
        TakeUpSignals ready for prediction
    """
    clinical_severity = clinical_severity or {}
    dropoff_risk = dropoff_risk or {}
    other_emotions_segment = other_emotions_segment or {}

    # Extract severity level
    severity_level = clinical_severity.get("severity_level", "MEDIUM")
    if severity_level not in ["LOW", "MEDIUM", "HIGH"]:
        severity_level = "MEDIUM"

    # Extract anxiety data from dropoff_risk
    anxiety_post = dropoff_risk.get("anxiety_post_level", "None")
    anxiety_trajectory = dropoff_risk.get("anxiety_trajectory", "Stable")

    # Extract financial concern
    # Check is_financial_risk boolean first, then try to get severity
    financial_concern = "none"
    if dropoff_risk.get("is_financial_risk", False):
        # Map to severity based on reasons count or use default
        reasons = dropoff_risk.get("financial_risk_reasons", [])
        if len(reasons) >= 3:
            financial_concern = "severe"
        elif len(reasons) >= 2:
            financial_concern = "moderate"
        elif len(reasons) >= 1:
            financial_concern = "mild"

    # Extract compliance likelihood
    compliance = dropoff_risk.get("compliance_likelihood", "moderate")
    if compliance not in ["high", "moderate", "low", "very_low"]:
        compliance = "moderate"

    # Extract emotions
    emotions_detected = []
    raw_emotions = other_emotions_segment.get("emotions_detected", [])
    for emotion in raw_emotions:
        if isinstance(emotion, dict):
            emotion_name = emotion.get("emotion", "")
            emotion_severity = emotion.get("severity", "")
            if emotion_name and emotion_severity:
                emotions_detected.append({
                    "emotion": emotion_name,
                    "severity": emotion_severity
                })

    return TakeUpSignals(
        clinical_severity=severity_level,
        anxiety_post_level=anxiety_post,
        anxiety_trajectory=anxiety_trajectory,
        financial_concern=financial_concern,
        compliance_likelihood=compliance,
        emotions_detected=emotions_detected
    )


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "TakeUpSignals",
    "TakeUpPrediction",
    "predict_take_up_likelihood",
    "adjust_priority_score",
    "build_signals_from_assessments",
]
