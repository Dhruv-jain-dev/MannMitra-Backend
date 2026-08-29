"""CPU-friendly speech-to-text adapter for microphone / uploaded recordings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Union

import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

from predict_speech_emotion import TARGET_SAMPLE_RATE, _load_audio

MODEL_NAME = os.environ.get("MM_STT_MODEL", "openai/whisper-tiny.en")


class TranscriptionError(RuntimeError):
    """Raised when speech cannot be transcribed."""


@lru_cache(maxsize=1)
def _load_transcriber():
    try:
        processor = AutoProcessor.from_pretrained(MODEL_NAME)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
        model.to("cpu").eval()
    except Exception as error:
        raise TranscriptionError(
            "Speech transcription is unavailable. Please check the local model or network connection."
        ) from error
    return processor, model


def transcribe_audio(audio_path: Union[str, Path]) -> str:
    """Transcribe a WAV/MP3 file using Whisper Tiny on CPU."""
    path = Path(audio_path)
    try:
        waveform = _load_audio(path, TARGET_SAMPLE_RATE)
        if waveform.size == 0:
            raise ValueError("audio is empty")

        processor, model = _load_transcriber()
        inputs = processor(waveform, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=128)
        text = processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
    except TranscriptionError:
        raise
    except Exception as error:
        raise TranscriptionError(
            "The recording could not be transcribed. Please speak clearly and try again."
        ) from error

    if not text:
        raise TranscriptionError("No intelligible speech was detected. Please try recording again.")

    return text
