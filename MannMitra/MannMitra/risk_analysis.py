"""
risk_analysis.py
=================
MANNMITRA - Sentiment Analysis, Crisis Pattern Matching, and Multi-Turn
Risk Triage for the student wellbeing companion.

This module is self-contained and can be imported by rag_engine.py / app.py
or run standalone for a quick smoke test.
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mannmitra.risk_analysis")

# --------------------------------------------------------------------------
# Optional transformer backend (SamLowe/roberta-base-go_emotions)
# --------------------------------------------------------------------------
_HF_AVAILABLE = False
_hf_pipeline = None

try:
    from transformers import pipeline as _hf_pipeline_factory

    _HF_TOKEN = os.getenv("HF_TOKEN")

    def _load_hf_pipeline():
        kwargs = {
            "task": "text-classification",
            "model": "SamLowe/roberta-base-go_emotions",
            "top_k": None,  # return scores for all 28 classes
        }
        if _HF_TOKEN:
            kwargs["token"] = _HF_TOKEN
        return _hf_pipeline_factory(**kwargs)

    _hf_pipeline = _load_hf_pipeline()
    _HF_AVAILABLE = True
    logger.info("Loaded SamLowe/roberta-base-go_emotions transformer pipeline.")
except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a fallback path
    logger.warning("Transformer pipeline unavailable (%s). Falling back to lexicon scorer.", exc)
    _HF_AVAILABLE = False
    _hf_pipeline = None

# --------------------------------------------------------------------------
# GoEmotions 28-class taxonomy, grouped by distress polarity
# --------------------------------------------------------------------------
GOEMOTIONS_LABELS = [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
    "joy", "love", "nervousness", "optimism", "pride", "realization",
    "relief", "remorse", "sadness", "surprise", "neutral",
]

# Weight each emotion contributes to a 0-1 "distress" composite.
NEGATIVE_EMOTION_WEIGHTS: Dict[str, float] = {
    "grief": 0.95,
    "remorse": 0.75,
    "sadness": 0.75,
    "fear": 0.75,
    "nervousness": 0.65,
    "disappointment": 0.55,
    "disgust": 0.55,
    "anger": 0.55,
    "annoyance": 0.45,
    "embarrassment": 0.45,
    "confusion": 0.35,
    "disapproval": 0.30,
}

POSITIVE_EMOTION_LABELS = {
    "admiration", "amusement", "approval", "caring", "curiosity", "desire",
    "excitement", "gratitude", "joy", "love", "optimism", "pride", "realization",
    "relief", "surprise",
}

# --------------------------------------------------------------------------
# Offline lexicon fallback (used if the transformer cannot be loaded)
# --------------------------------------------------------------------------
_LEXICON: Dict[str, Tuple[str, float]] = {
    # word: (closest go_emotions label, distress weight)
    "sad": ("sadness", 0.6), "depressed": ("sadness", 0.75), "hopeless": ("grief", 0.85),
    "worthless": ("grief", 0.85), "lonely": ("sadness", 0.6), "alone": ("sadness", 0.55),
    "tired": ("nervousness", 0.35), "exhausted": ("nervousness", 0.5), "stressed": ("nervousness", 0.55),
    "anxious": ("nervousness", 0.65), "panic": ("fear", 0.7), "scared": ("fear", 0.65),
    "afraid": ("fear", 0.6), "angry": ("anger", 0.55), "furious": ("anger", 0.65),
    "frustrated": ("annoyance", 0.5), "numb": ("grief", 0.7), "empty": ("grief", 0.7),
    "cry": ("sadness", 0.6), "crying": ("sadness", 0.65), "worried": ("nervousness", 0.5),
    "overwhelmed": ("nervousness", 0.6), "trapped": ("fear", 0.75), "failing": ("disappointment", 0.5),
    "happy": ("joy", 0.0), "good": ("approval", 0.0), "fine": ("neutral", 0.0),
    "okay": ("neutral", 0.0), "great": ("joy", 0.0), "excited": ("excitement", 0.0),
    "grateful": ("gratitude", 0.0), "relieved": ("relief", 0.0), "hopeful": ("optimism", 0.0),
}


@dataclass
class EmotionResult:
    label: str
    score: float  # confidence of top label (0-1)
    all_emotions: Dict[str, float] = field(default_factory=dict)  # every class -> prob
    backend: str = "transformer"  # "transformer" | "lexicon"


@dataclass
class RiskAssessment:
    tier: str  # "GREEN" | "YELLOW" | "RED"
    score: float  # composite distress score 0-1
    matched_patterns: List[str] = field(default_factory=list)
    is_crisis: bool = False
    crisis_response: Optional[str] = None
    helplines: Dict[str, str] = field(
        default_factory=lambda: {"Tele-MANAS": "14416", "KIRAN": "1800-599-0019"}
    )


class RiskAnalyzer:
    """Sentiment + deterministic crisis triage over student chat turns."""

    # ---- Tier thresholds -------------------------------------------------
    GREEN_MAX = 0.39
    YELLOW_MAX = 0.74

    # ---- Tier 0: crisis bypass -------------------------------------------
    # Typo-tolerant / word-omission-tolerant patterns. Each pattern is a
    # regex fragment; whitespace between key tokens is flexible (\s+ / \s*)
    # and common contractions/typos are tolerated via optional groups.
    CRISIS_PATTERNS: List[str] = [
        r"\bdon'?t\s+(?:want\s+)?to\s+be\s+here\b",
        r"\bdon'?t\s+want\s+to\s+(?:live|exist|be\s+alive)\b",
        r"\bkill(?:ing)?\s+my\s?self\b",
        r"\bsuicid(?:e|al)\b",
        r"\bend(?:ing)?\s+it\s+all\b",
        r"\bend\s+my\s+life\b",
        r"\btake\s+my\s+(?:own\s+)?life\b",
        r"\bwant\s+to\s+die\b",
        r"\bwish\s+i\s+w(?:as|ere)\s+dead\b",
        r"\bbetter\s+off\s+dead\b",
        r"\bno\s+reason\s+to\s+live\b",
        r"\bcan'?t\s+go\s+on\s+(?:living|anymore)\b",
        r"\bself\s?-?\s?harm\b",
        r"\bhurt(?:ing)?\s+my\s?self\b",
        r"\bcut(?:ting)?\s+my\s?self\b",
        r"\bplan(?:ning)?\s+to\s+(?:die|end\s+it)\b",
        r"\bgoodbye\s+forever\b",
        r"\bnot\s+(?:gonna|going\s+to)\s+be\s+(?:here|around)\s+(?:much\s+longer|anymore)\b",
    ]

    # ---- Tier 1: severe distress boosters (+0.55) -------------------------
    SEVERE_PATTERNS: List[str] = [
        r"\bl(?:o+|oo+)sing\s+control\b",
        r"\bno\s+way\s+out\b",
        r"\bcan'?t\s+take\s+this\s+any\s?more\b",
        r"\bcant\s+take\s+this\s+any\s?more\b",
        r"\bemotionally\s+(?:dead|numb)\b",
        r"\bcompletely\s+trapped\b",
    ]

    # ---- Tier 2: moderate distress boosters (+0.30) ------------------------
    MODERATE_PATTERNS: List[str] = [
        r"\bhaven'?t\s+slept\b",
        r"\binsomnia\b",
        r"\bskip(?:ping|ped)\s+meals\b",
        r"\bfail(?:ing|ed)\s+exams?\b",
        r"\bpanic\s+attacks?\b",
        r"\bchest\s+(?:feels?\s+)?tight\b",
        r"\bisolated\b",
    ]

    CRISIS_RESPONSE_TEXT = (
        "I'm really glad you told me this, and I want you to know you don't have to "
        "carry it alone right now. What you're feeling matters, and immediate support "
        "is available.\n\n"
        "**Please reach out right now:**\n"
        "- 📞 **Tele-MANAS**: 14416 (24/7, free, confidential)\n"
        "- 📞 **KIRAN Mental Health Helpline**: 1800-599-0019 (24/7, toll-free)\n\n"
        "If you are in immediate physical danger, please contact local emergency "
        "services or go to the nearest hospital. You matter, and there are people "
        "trained to help you through this moment."
    )

    def __init__(self) -> None:
        self._crisis_re = [re.compile(p, re.IGNORECASE) for p in self.CRISIS_PATTERNS]
        self._severe_re = [re.compile(p, re.IGNORECASE) for p in self.SEVERE_PATTERNS]
        self._moderate_re = [re.compile(p, re.IGNORECASE) for p in self.MODERATE_PATTERNS]

    # ------------------------------------------------------------------
    # Emotion detection
    # ------------------------------------------------------------------
    def analyze_emotion(self, text: str) -> EmotionResult:
        text = (text or "").strip()
        if not text:
            return EmotionResult(label="neutral", score=1.0, all_emotions={"neutral": 1.0}, backend="lexicon")

        if _HF_AVAILABLE and _hf_pipeline is not None:
            try:
                raw = _hf_pipeline(text)
                # top_k=None returns [[{label, score}, ...]]
                items = raw[0] if raw and isinstance(raw[0], list) else raw
                all_emotions = {item["label"]: float(item["score"]) for item in items}
                top = max(all_emotions.items(), key=lambda kv: kv[1])
                return EmotionResult(label=top[0], score=top[1], all_emotions=all_emotions, backend="transformer")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Transformer inference failed (%s); using lexicon fallback for this turn.", exc)

        return self._lexicon_fallback(text)

    def _lexicon_fallback(self, text: str) -> EmotionResult:
        lowered = text.lower()
        tokens = re.findall(r"[a-z']+", lowered)
        found: Dict[str, float] = {}
        for tok in tokens:
            if tok in _LEXICON:
                label, weight = _LEXICON[tok]
                found[label] = max(found.get(label, 0.0), weight)

        if not found:
            return EmotionResult(label="neutral", score=0.1, all_emotions={"neutral": 0.1}, backend="lexicon")

        top = max(found.items(), key=lambda kv: kv[1])
        # For the lexicon backend, `score` IS the pre-tuned distress weight
        # for the matched word (not a classifier confidence), so downstream
        # scoring should use it directly rather than re-weighting by label.
        return EmotionResult(label=top[0], score=top[1], all_emotions=found, backend="lexicon")

    # ------------------------------------------------------------------
    # Composite distress score from an EmotionResult
    # ------------------------------------------------------------------
    def _emotion_distress_score(self, emotion: EmotionResult) -> float:
        if emotion.label in POSITIVE_EMOTION_LABELS:
            return 0.05
        if emotion.backend == "lexicon":
            # The lexicon fallback already returns a pre-tuned distress
            # weight for the matched word - use it directly.
            return round(min(1.0, emotion.score), 4)
        if emotion.label == "neutral":
            return 0.1
        weight = NEGATIVE_EMOTION_WEIGHTS.get(emotion.label, 0.4)
        # scale the emotion's base distress weight by model confidence,
        # keeping a floor so a confident-but-not-extreme reading still counts
        return round(min(1.0, weight * (0.5 + 0.5 * emotion.score)), 4)

    @staticmethod
    def determine_tier(score: float) -> str:
        if score >= 0.75:
            return "RED"
        if score >= 0.40:
            return "YELLOW"
        return "GREEN"

    # ------------------------------------------------------------------
    # Full risk assessment
    # ------------------------------------------------------------------
    def assess_risk(
        self,
        current_text: str,
        history_scores: Optional[List[float]] = None,
    ) -> Tuple[EmotionResult, RiskAssessment]:
        history_scores = history_scores or []
        text = current_text or ""
        emotion = self.analyze_emotion(text)
        matched_patterns: List[str] = []

        # --- Tier 0: deterministic crisis bypass ---------------------------
        for rx in self._crisis_re:
            if rx.search(text):
                matched_patterns.append(rx.pattern)
                assessment = RiskAssessment(
                    tier="RED",
                    score=1.0,
                    matched_patterns=matched_patterns,
                    is_crisis=True,
                    crisis_response=self.CRISIS_RESPONSE_TEXT,
                )
                return emotion, assessment

        # --- Base score from sentiment --------------------------------------
        score = self._emotion_distress_score(emotion)

        # --- Regex-based boosters -------------------------------------------
        for rx in self._severe_re:
            if rx.search(text):
                matched_patterns.append(rx.pattern)
                score += 0.55
        for rx in self._moderate_re:
            if rx.search(text):
                matched_patterns.append(rx.pattern)
                score += 0.30
        score = min(1.0, score)

        # --- Multi-turn, non-dilution logic ---------------------------------
        # Rule 1: an acute current turn (>=0.50) is never averaged down by
        # calmer past turns - the current turn's severity is a floor.
        # Rule 2: consecutive distressed turns (>=0.35) compound upward,
        # rather than being smoothed away by an average.
        consecutive_distress = 0
        for past in reversed(history_scores):
            if past >= 0.35:
                consecutive_distress += 1
            else:
                break
        if consecutive_distress > 0:
            compound_boost = 0.15 * consecutive_distress
            score = min(1.0, score + compound_boost)

        if score >= 0.50:
            # Acute floor: never let history pull an acute turn down.
            floor = min(1.0, score)
            score = max(score, floor)
        elif history_scores:
            # For mild/ambiguous current turns only, allow gentle smoothing
            # with recent history (does not apply once score already >=0.50).
            recent = history_scores[-3:]
            avg_recent = sum(recent) / len(recent)
            score = max(score, 0.6 * score + 0.4 * avg_recent) if avg_recent > score else score

        score = round(min(1.0, max(0.0, score)), 4)
        tier = self.determine_tier(score)

        assessment = RiskAssessment(
            tier=tier,
            score=score,
            matched_patterns=matched_patterns,
            is_crisis=False,
            crisis_response=None,
        )
        return emotion, assessment

    # Convenience alias per spec
    def assess(
        self, current_text: str, history_scores: Optional[List[float]] = None
    ) -> Tuple[EmotionResult, RiskAssessment]:
        return self.assess_risk(current_text, history_scores)

    @staticmethod
    def get_crisis_response() -> str:
        return RiskAnalyzer.CRISIS_RESPONSE_TEXT


# --------------------------------------------------------------------------
# Manual smoke test
# --------------------------------------------------------------------------
if __name__ == "__main__":
    analyzer = RiskAnalyzer()
    samples = [
        "I'm a bit tired after classes today",
        "I haven't slept in three days and I'm skipping meals, I feel so isolated",
        "I don't want to be here anymore",
        "honestly I just feel completely trapped and like there's no way out",
    ]
    history: List[float] = []
    for s in samples:
        emo, risk = analyzer.assess_risk(s, history)
        history.append(risk.score)
        print(f"[{risk.tier:6}] score={risk.score:.2f} emotion={emo.label:12} text={s!r}")
        if risk.is_crisis:
            print("        -> CRISIS RESPONSE TRIGGERED")
