"""Acoustic speech-emotion inference (Wav2Vec2) with graceful degradation.

This module loads a fine-tuned Wav2Vec2 audio-classification checkpoint
(seven RAVDESS-style labels: angry, calm, disgust, fearful, happy, sad,
surprised) and turns a WAV/MP3 recording into a probability distribution
over those labels.

If no fine-tuned weights are available locally (``models/<...>/best``) and
no ``HUGGINGFACE_MODEL_ID`` is configured, ``predict_emotion`` raises
``AcousticModelUnavailable`` so the caller can fall back to a
transcript-only (Whisper + GoEmotions) emotion estimate instead of crashing
the whole voice pipeline.
"""

from __future__ import annotations

import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Union

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mannmitra.speech_engine.predict_speech_emotion")

TARGET_SAMPLE_RATE = 16000

EMOTIONS = ("angry", "calm", "disgust", "fearful", "happy", "sad", "surprised")

# Default local checkpoint location, relative to this file's directory.
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "models" / "ravdess_wav2vec2_finetuned" / "best"
MODEL_DIR = Path(os.environ.get("MM_ACOUSTIC_MODEL_DIR", str(_DEFAULT_MODEL_DIR)))
HUGGINGFACE_MODEL_ID = os.environ.get("HUGGINGFACE_MODEL_ID", "").strip()


class AcousticModelUnavailable(RuntimeError):
    """Raised when no acoustic (fine-tuned Wav2Vec2) weights can be loaded."""


# --------------------------------------------------------------------------
# Audio loading / feature extraction
# --------------------------------------------------------------------------
def _load_audio(path: Union[str, Path], target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Load an audio file as mono float32 samples resampled to ``target_sr``.

    Tries ``soundfile`` first (fast, no ffmpeg dependency, covers WAV/FLAC).
    Falls back to ``librosa`` (via audioread/ffmpeg) for compressed formats
    such as MP3 that ``soundfile`` cannot decode.
    """
    path = Path(path)
    waveform: np.ndarray
    sample_rate: int

    try:
        import soundfile as sf

        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        waveform = np.mean(data, axis=1, dtype=np.float32)
    except Exception:  # noqa: BLE001 - fall back to librosa for e.g. mp3
        try:
            import librosa

            waveform, sample_rate = librosa.load(str(path), sr=None, mono=True)
            waveform = waveform.astype(np.float32, copy=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Could not read audio file {path}: {exc}") from exc

    if waveform.size == 0:
        return waveform.astype(np.float32, copy=False)

    if sample_rate != target_sr:
        waveform = _resample(waveform, sample_rate, target_sr)

    return waveform.astype(np.float32, copy=False)


def _resample(waveform: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr or waveform.size == 0:
        return waveform
    try:
        from scipy.signal import resample as _scipy_resample

        n_target = max(1, int(round(len(waveform) * target_sr / float(orig_sr))))
        return _scipy_resample(waveform, n_target).astype(np.float32, copy=False)
    except Exception:  # noqa: BLE001 - last-resort linear interpolation
        n_target = max(1, int(round(len(waveform) * target_sr / float(orig_sr))))
        x_old = np.linspace(0.0, 1.0, num=len(waveform), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_target, endpoint=False)
        return np.interp(x_new, x_old, waveform).astype(np.float32, copy=False)


def audio_quality_metrics(waveform: np.ndarray) -> Dict[str, float]:
    """RMS / peak amplitude / non-silence flags used for reliability weighting."""
    if waveform.size == 0:
        return {"rms": 0.0, "peak": 0.0, "non_silent": False}
    rms = float(np.sqrt(np.mean(np.square(waveform), dtype=np.float64)))
    peak = float(np.max(np.abs(waveform)))
    return {"rms": rms, "peak": peak, "non_silent": bool(rms >= 0.003 and peak >= 0.01)}


# --------------------------------------------------------------------------
# Model loading (lazy, cached, and gracefully optional)
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_model():
    """Load the processor + Wav2Vec2 audio-classification model.

    Preference order: HUGGINGFACE_MODEL_ID (if set) -> local MODEL_DIR.
    Raises AcousticModelUnavailable if neither source is usable, including
    when the required ML libraries (torch / transformers) aren't installed.
    """
    source = HUGGINGFACE_MODEL_ID if HUGGINGFACE_MODEL_ID else str(MODEL_DIR)
    if not HUGGINGFACE_MODEL_ID and not MODEL_DIR.is_dir():
        raise AcousticModelUnavailable(
            f"No fine-tuned acoustic weights found at '{MODEL_DIR}' and HUGGINGFACE_MODEL_ID is unset."
        )

    try:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    except Exception as exc:  # noqa: BLE001
        raise AcousticModelUnavailable(f"torch/transformers unavailable: {exc}") from exc

    try:
        feature_extractor = AutoFeatureExtractor.from_pretrained(source)
        model = AutoModelForAudioClassification.from_pretrained(source, torch_dtype=torch.float32)
        model.to("cpu").eval()
    except Exception as exc:  # noqa: BLE001
        raise AcousticModelUnavailable(f"Failed to load acoustic model from '{source}': {exc}") from exc

    # Resolve the label order the checkpoint actually uses, falling back to
    # the canonical EMOTIONS order if the config doesn't specify one.
    id2label = getattr(model.config, "id2label", None)
    if id2label and len(id2label) == len(EMOTIONS):
        label_order = [id2label[i].lower() for i in sorted(id2label, key=int)] if all(
            str(i).isdigit() for i in id2label
        ) else [id2label[i].lower() for i in id2label]
    else:
        label_order = list(EMOTIONS)

    return feature_extractor, model, label_order


# --------------------------------------------------------------------------
# Public inference API
# --------------------------------------------------------------------------
def predict_emotion(audio_path: Union[str, Path]) -> Dict[str, object]:
    """Run acoustic emotion inference on a WAV/MP3 file.

    Returns a dict with ``probabilities`` (7-way softmax over EMOTIONS),
    ``duration_seconds``, and ``audio_quality``. Raises
    ``AcousticModelUnavailable`` if no usable fine-tuned checkpoint exists,
    so callers can fall back to a transcript-only emotion estimate.
    """
    path = Path(audio_path)
    waveform = _load_audio(path, TARGET_SAMPLE_RATE)
    if waveform.size == 0:
        raise ValueError("Audio file is empty or unreadable.")

    duration_seconds = float(len(waveform)) / float(TARGET_SAMPLE_RATE)
    quality = audio_quality_metrics(waveform)

    # Raises AcousticModelUnavailable (including for a missing torch/
    # transformers install) before we ever touch `torch` directly below.
    feature_extractor, model, label_order = _load_model()
    import torch

    inputs = feature_extractor(waveform, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.nn.functional.softmax(logits, dim=-1).squeeze(0).cpu().numpy()

    raw_probabilities = {label_order[i]: float(probs[i]) for i in range(len(label_order))}
    # Re-key defensively onto the canonical EMOTIONS set (covers checkpoints
    # whose config label spelling/casing differs slightly).
    probabilities = {emotion: raw_probabilities.get(emotion, 0.0) for emotion in EMOTIONS}
    total = sum(probabilities.values())
    if total > 0:
        probabilities = {k: v / total for k, v in probabilities.items()}
    else:
        probabilities = {emotion: 1.0 / len(EMOTIONS) for emotion in EMOTIONS}

    return {
        "probabilities": probabilities,
        "duration_seconds": round(duration_seconds, 4),
        "audio_quality": quality,
        "model_source": HUGGINGFACE_MODEL_ID or str(MODEL_DIR),
    }


def acoustic_model_available() -> bool:
    """Cheap availability check without raising, used by UI status badges."""
    if HUGGINGFACE_MODEL_ID:
        return True
    return MODEL_DIR.is_dir() and any(MODEL_DIR.iterdir())


# --------------------------------------------------------------------------
# Manual smoke test
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python predict_speech_emotion.py <path/to/audio.wav>")
        raise SystemExit(1)

    try:
        result = predict_emotion(sys.argv[1])
        print(result)
    except AcousticModelUnavailable as exc:
        print(f"Acoustic model unavailable: {exc}")
