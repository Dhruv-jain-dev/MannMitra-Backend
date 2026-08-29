"""Combine transcript sentiment cues with the existing acoustic prediction."""

from __future__ import annotations

import math
from typing import Mapping

from stress_interpretation import EMOTIONS, assess_stress

TEXT_CUES = {
    "angry": {"angry", "furious", "rage", "hate", "mad", "annoyed"},
    "fearful": {"afraid", "scared", "fear", "worried", "worry", "panic", "unsafe"},
    "sad": {"sad", "unhappy", "cry", "crying", "lonely", "upset", "hurt", "hopeless"},
    "disgust": {"disgusting", "disgusted", "gross"},
    "happy": {"happy", "great", "good", "joy", "excited", "love", "wonderful"},
    "calm": {"calm", "relaxed", "peaceful", "fine", "okay", "safe"},
}

MAX_ACOUSTIC_WEIGHT = 0.30
MIN_ACOUSTIC_WEIGHT = 0.05


def _acoustic_reliability(probabilities: Mapping[str, float], audio_quality: Mapping[str, float] | None) -> float:
    peak = max(probabilities.values())
    concentration = max(0.0, min(1.0, (peak - 1 / len(EMOTIONS)) / (1 - 1 / len(EMOTIONS))))
    entropy = -sum(p * math.log(max(p, 1e-12)) for p in probabilities.values()) / math.log(len(EMOTIONS))

    quality = 1.0
    if audio_quality is not None:
        rms = float(audio_quality.get("rms", 0.0))
        peak_amplitude = float(audio_quality.get("peak", 0.0))
        quality = max(0.0, min(1.0, min(rms / 0.01, peak_amplitude / 0.05)))
        if not audio_quality.get("non_silent", True):
            quality = 0.0

    return round(max(0.0, min(1.0, 0.65 * concentration + 0.35 * quality * (1.0 - entropy))), 4)


def text_emotion_probabilities(text: str) -> dict[str, float] | None:
    """Return text probabilities; empty text means transcription is unavailable."""
    if not text.strip():
        return None

    tokens = {token.strip(".,!?;:'\"()[]{}").lower() for token in text.split()}
    scores = {emotion: float(sum(token in cues for token in tokens)) for emotion, cues in TEXT_CUES.items()}

    # A valid transcript without explicit affect words is semantically neutral,
    # rather than allowing a biased acoustic sad output to dominate.
    probabilities = {
        "angry": 0.08,
        "calm": 0.35,
        "disgust": 0.08,
        "fearful": 0.08,
        "happy": 0.20,
        "sad": 0.08,
        "surprised": 0.13,
    }
    total = sum(scores.values())
    for emotion, score in scores.items():
        if total:
            probabilities[emotion] += 0.80 * score / total

    normalizer = sum(probabilities.values())
    return {emotion: value / normalizer for emotion, value in probabilities.items()}


def combine_emotion_results(
    acoustic_result: Mapping[str, object],
    transcript: str | None,
    audio_quality: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Blend reliable transcript cues with acoustic probabilities."""
    acoustic = {
        emotion: float(acoustic_result["probabilities"][emotion])  # type: ignore[index]
        for emotion in EMOTIONS
    }
    acoustic_confidence = max(acoustic.values())
    acoustic_reliability = _acoustic_reliability(acoustic, audio_quality)

    text_probabilities = text_emotion_probabilities(transcript or "")

    if text_probabilities is None:
        combined = acoustic
        source = "acoustic signal only; no clear emotion cue was found in the transcript"
        acoustic_weight = 1.0
        text_reliability = 0.0
        reliable = acoustic_reliability >= 0.35
    else:
        # Conversational microphone audio can trigger a biased acoustic class,
        # so transcript evidence receives the larger share whenever available.
        tokens = {token.strip(".,!?;:'\\\"()[]{}").lower() for token in (transcript or "").split()}
        has_explicit_cue = any(token in cues for token in tokens for cues in TEXT_CUES.values())
        text_reliability = 1.0 if has_explicit_cue else 0.45

        acoustic_weight = MIN_ACOUSTIC_WEIGHT + (MAX_ACOUSTIC_WEIGHT - MIN_ACOUSTIC_WEIGHT) * acoustic_reliability
        if has_explicit_cue and max(text_probabilities, key=text_probabilities.get) != max(acoustic, key=acoustic.get):
            acoustic_weight *= 0.5
        acoustic_weight = max(MIN_ACOUSTIC_WEIGHT, min(MAX_ACOUSTIC_WEIGHT, acoustic_weight))
        text_weight = 1.0 - acoustic_weight

        combined = {
            emotion: acoustic_weight * acoustic[emotion] + text_weight * text_probabilities[emotion]
            for emotion in EMOTIONS
        }
        source = "acoustic and transcript emotion cues"
        tokens = {token.strip(".,!?;:'\\\"()[]{}").lower() for token in (transcript or "").split()}
        has_explicit_cue = any(token in cues for token in tokens for cues in TEXT_CUES.values())
        reliable = has_explicit_cue or acoustic_reliability >= 0.35

    predicted = max(EMOTIONS, key=combined.get) if reliable else None
    stress = assess_stress(combined)
    stress["explanation"] = f"Based on {source}. {stress['explanation']}"

    return {
        "transcript": transcript,
        "emotion": predicted,
        "confidence": (
            combined[predicted] * (text_reliability * (1.0 - acoustic_weight) + acoustic_reliability * acoustic_weight)
            if predicted is not None
            else 0.0
        ),
        "confidence_type": "reliability-adjusted fused score (not calibrated)",
        "probabilities": combined,
        "fusion": {
            "text_weight": round(1.0 - (acoustic_weight if text_probabilities is not None else 0.0), 4)
            if text_probabilities is not None
            else 0.0,
            "acoustic_weight": round(acoustic_weight, 4) if text_probabilities is not None else 1.0,
            "acoustic_confidence": round(max(acoustic.values()), 4),
            "acoustic_reliability": acoustic_reliability,
            "audio_quality": dict(audio_quality or {}),
            "signals_reliable": reliable,
            "text_probabilities": text_probabilities,
            "combined_probabilities": combined,
        },
        "stress_assessment": stress,
    }
