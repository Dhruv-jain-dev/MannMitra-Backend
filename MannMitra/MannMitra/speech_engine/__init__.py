"""MannMitra speech engine: Whisper STT + fused acoustic/transcript emotion.

This package is intentionally import-light at the top level: heavy
transformer/torch imports happen lazily inside the individual modules the
first time a model is actually needed, so simply importing ``speech_engine``
(e.g. to check availability) stays fast and side-effect free.
"""

__all__ = [
    "speech_to_text",
    "speech_analysis",
    "stress_interpretation",
    "predict_speech_emotion",
]
