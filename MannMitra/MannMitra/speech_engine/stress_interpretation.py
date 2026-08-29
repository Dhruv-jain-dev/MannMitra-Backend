"""Transparent, non-clinical heuristic for interpreting emotion probabilities."""

from __future__ import annotations

from typing import Mapping

EMOTIONS = ("angry", "calm", "disgust", "fearful", "happy", "sad", "surprised")

# Keep all policy choices in this configuration block. Values are signed
# contributions to a raw stress tendency; calm and happy reduce it.
SCORING_CONFIG = {
    "weights": {
        "angry": 0.35,
        "fearful": 0.30,
        "sad": 0.20,
        "disgust": 0.15,
        "surprised": 0.05,
        "calm": -0.30,
        "happy": -0.20,
    },
    "raw_min": -0.50,
    # Maximum positive tendency available from the configured weights.
    "raw_max": 0.35,
    "meaningful_contribution": 0.10,
    "moderate_threshold": 34.0,
    "high_threshold": 67.0,
}


def assess_stress(probabilities: Mapping[str, float]) -> dict[str, object]:
    """Convert seven emotion probabilities into an interpretable assessment.

    This is a configurable heuristic, not a clinical instrument or diagnosis;
    one prediction should never be treated as definitive evidence of stress.
    """
    missing = set(EMOTIONS) - set(probabilities)
    extra = set(probabilities) - set(EMOTIONS)
    if missing or extra:
        raise ValueError(f"Expected exactly {EMOTIONS}; missing={sorted(missing)}, extra={sorted(extra)}")

    values = {emotion: float(probabilities[emotion]) for emotion in EMOTIONS}
    if any(value < 0.0 or value > 1.0 for value in values.values()):
        raise ValueError("Emotion probabilities must be between 0 and 1")
    if abs(sum(values.values()) - 1.0) > 1e-3:
        raise ValueError("Emotion probabilities must sum to approximately 1")

    weights = SCORING_CONFIG["weights"]
    contributions = {emotion: values[emotion] * weights[emotion] for emotion in EMOTIONS}
    raw_score = sum(contributions.values())

    span = SCORING_CONFIG["raw_max"] - SCORING_CONFIG["raw_min"]
    stress_score = max(0.0, min(100.0, (raw_score - SCORING_CONFIG["raw_min"]) / span * 100.0))

    if stress_score >= SCORING_CONFIG["high_threshold"]:
        stress_level = "high"
    elif stress_score >= SCORING_CONFIG["moderate_threshold"]:
        stress_level = "moderate"
    else:
        stress_level = "low"

    meaningful = SCORING_CONFIG["meaningful_contribution"]
    contributing = [emotion for emotion in EMOTIONS if abs(contributions[emotion]) >= meaningful]
    upward = [emotion for emotion in contributing if contributions[emotion] > 0]
    downward = [emotion for emotion in contributing if contributions[emotion] < 0]

    explanation_parts = [f"The heuristic stress score is {stress_score:.1f}/100 ({stress_level})."]
    if upward:
        explanation_parts.append("Higher-stress contributions: " + ", ".join(upward) + ".")
    if downward:
        explanation_parts.append("Lower-stress contributions: " + ", ".join(downward) + ".")
    explanation_parts.append("This is an emotion-probability heuristic, not a medical or mental-health diagnosis.")

    return {
        "stress_score": round(stress_score, 2),
        "stress_level": stress_level,
        "contributing_emotions": contributing,
        "explanation": " ".join(explanation_parts),
    }
