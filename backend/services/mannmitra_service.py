"""Non-UI orchestration for the existing MannMitra pipeline.

This module deliberately delegates all analysis, retrieval, speech, and
generation behavior to the existing project modules. It creates no persistent
state; callers provide the current conversation context and risk history.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

from rag_engine import RAGContext, RAGEngine
from risk_analysis import EmotionResult, RiskAnalyzer, RiskAssessment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mannmitra.service")

load_dotenv(override=False)


def _harmonize_gemini_key() -> str:
    """Preserve the existing Gemini environment-variable compatibility."""
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
        os.environ.pop("GOOGLE_API_KEY", None)
    return key


GEMINI_API_KEY = _harmonize_gemini_key()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

_GENAI_AVAILABLE = False
_genai_client = None
_genai_types = None

try:
    from google import genai as _google_genai
    from google.genai import types as _google_genai_types

    if GEMINI_API_KEY:
        _genai_client = _google_genai.Client(api_key=GEMINI_API_KEY)
        _genai_types = _google_genai_types
        _GENAI_AVAILABLE = True
    else:
        logger.warning("No GEMINI_API_KEY / GOOGLE_API_KEY found in environment.")
except Exception as exc:  # noqa: BLE001
    logger.warning("google-genai unavailable (%s). LLM responses will use a static fallback.", exc)

_SAFETY_SETTINGS = None
if _genai_types is not None:
    _SAFETY_SETTINGS = [
        _genai_types.SafetySetting(
            category=_genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=_genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        _genai_types.SafetySetting(
            category=_genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=_genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        _genai_types.SafetySetting(
            category=_genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=_genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        _genai_types.SafetySetting(
            category=_genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=_genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]

SYSTEM_PROMPT = (
    "You are MannMitra, a warm, empathetic peer listener for Indian college "
    "students. You are NOT a therapist and never diagnose. Use a caring, "
    "non-clinical, conversational tone - like a supportive friend, not a "
    "textbook. Format each reply primarily as concise Markdown bullet points, "
    "with a brief supportive lead-in when it feels natural. Keep each point "
    "clear and complete rather than fragmenting every sentence. Avoid long "
    "paragraph blocks. Use a numbered list when giving sequential steps, and "
    "use headings only when they genuinely improve clarity. Validate the "
    "student's feelings before offering any gentle suggestion. If helpful "
    "context about a coping technique or campus resource is provided to "
    "you, weave it naturally into your own words as a friendly suggestion "
    "- never quote titles, filenames, or headers verbatim, and never say "
    "things like '[Source: ...]'. Keep responses grounded, human, and "
    "free of clinical jargon. Talk in non-repeating semi-casual patterns."
)


try:
    import predict_speech_emotion
    import speech_analysis
    import speech_to_text
    import stress_interpretation

    _SPEECH_ENGINE_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    logger.warning("Speech engine unavailable (%s); voice input will be disabled.", exc)
    predict_speech_emotion = None
    speech_analysis = None
    speech_to_text = None
    stress_interpretation = None
    _SPEECH_ENGINE_AVAILABLE = False


@dataclass
class TurnResult:
    assistant_response: str
    emotion: EmotionResult
    assessment: RiskAssessment
    rag_context: RAGContext
    voice_diagnostics: Optional[dict[str, Any]] = None
    latency_ms: Optional[dict[str, float]] = None

    def to_public_dict(self) -> dict[str, Any]:
        """Return current, client-safe output without prompts or secrets."""
        emotion_probabilities = {
            label: float(score) for label, score in self.emotion.all_emotions.items()
        }
        voice = self.voice_diagnostics or None
        return {
            "assistant_response": self.assistant_response,
            "emotion": {
                "label": self.emotion.label,
                "score": float(self.emotion.score),
                "probabilities": emotion_probabilities,
            },
            "risk": {
                "score": float(self.assessment.score),
                "tier": self.assessment.tier,
                "is_crisis": self.assessment.is_crisis,
            },
            "voice": voice,
            "rag": {
                "is_used": self.rag_context.is_used,
                "sources": list(self.rag_context.sources),
            },
        }


class MannMitraService:
    """Reusable owner of the current single-process MannMitra resources."""

    def __init__(self) -> None:
        self.risk_analyzer = RiskAnalyzer()
        self.rag_engine = RAGEngine()
        self.gemini_available = _GENAI_AVAILABLE and _genai_client is not None
        self.gemini_model = GEMINI_MODEL
        self.speech_engine_available = _SPEECH_ENGINE_AVAILABLE
        self.acoustic_model_available = False
        if self.speech_engine_available and predict_speech_emotion is not None:
            try:
                self.acoustic_model_available = bool(predict_speech_emotion.acoustic_model_available())
            except Exception:  # noqa: BLE001
                self.acoustic_model_available = False

    @staticmethod
    def hash_audio(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def generate_reply(self, user_text: str, chat_history: List[dict], rag_context: RAGContext) -> str:
        """The existing single-call Gemini response path for eligible turns."""
        if not self.gemini_available:
            return (
                "I'm really glad you shared that.\n\n"
                "- Thanks for opening up - you don't have to hold it all by yourself.\n"
                "- Want to tell me a little more about what's been going on?"
            )

        context_note = ""
        if rag_context.is_used and rag_context.retrieved_documents:
            joined = "\n\n".join(rag_context.retrieved_documents[:2])
            context_note = (
                "\n\nHelpful background you may draw on (do not quote directly, "
                f"paraphrase naturally):\n{joined}"
            )

        convo_lines = []
        for turn in chat_history[-6:]:
            role = "Student" if turn["role"] == "user" else "MannMitra"
            convo_lines.append(f"{role}: {turn['content']}")
        convo_text = "\n".join(convo_lines)

        prompt = (
            f"Recent conversation:\n{convo_text}\n\n"
            f"Student's latest message: {user_text}"
            f"{context_note}\n\n"
            "Respond as MannMitra using the requested concise, primarily bullet-point format:"
        )

        try:
            config = None
            if _genai_types is not None:
                config = _genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.6,
                    max_output_tokens=300,
                    safety_settings=_SAFETY_SETTINGS if _SAFETY_SETTINGS else None,
                )

            response = _genai_client.models.generate_content(  # type: ignore[union-attr]
                model=self.gemini_model,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            return text if text else "I'm here with you - can you tell me a little more?"
        except Exception as exc:  # noqa: BLE001
            logger.error("Gemini generation failed: %s", exc)
            return (
                "I'm here and listening.\n\n"
                "- I'm having a little trouble finding the right words right now.\n"
                "- Can you tell me more about how you're feeling?"
            )

    def process_voice_input(self, audio_bytes: bytes, suffix: str = ".wav") -> dict[str, Any]:
        """Existing Whisper/acoustic/fusion path, extracted without algorithm changes."""
        result: dict[str, Any] = {
            "transcript": None,
            "transcript_warning": None,
            "duration": None,
            "acoustic_stress": None,
            "vocal_tone": "unknown",
            "acoustic_available": False,
            "fusion_source": "unavailable",
        }
        if not self.speech_engine_available:
            result["transcript_warning"] = "Speech engine is not installed; voice input is unavailable."
            return result

        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = Path(tmp_file.name)

            try:
                transcript = speech_to_text.transcribe_audio(tmp_path)  # type: ignore[union-attr]
                result["transcript"] = transcript
            except speech_to_text.TranscriptionError as exc:  # type: ignore[union-attr]
                transcript = None
                result["transcript_warning"] = str(exc)

            acoustic_result = None
            try:
                acoustic_result = predict_speech_emotion.predict_emotion(tmp_path)  # type: ignore[union-attr]
                result["duration"] = acoustic_result.get("duration_seconds")
            except predict_speech_emotion.AcousticModelUnavailable as exc:  # type: ignore[union-attr]
                logger.info("Acoustic model unavailable (%s); falling back to transcript cues.", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Acoustic inference failed (%s); falling back to transcript cues.", exc)

            if result["duration"] is None:
                try:
                    waveform = predict_speech_emotion._load_audio(  # type: ignore[union-attr]
                        tmp_path, predict_speech_emotion.TARGET_SAMPLE_RATE  # type: ignore[union-attr]
                    )
                    result["duration"] = round(
                        float(len(waveform)) / float(predict_speech_emotion.TARGET_SAMPLE_RATE), 4  # type: ignore[union-attr]
                    )
                except Exception:  # noqa: BLE001
                    result["duration"] = None

            if acoustic_result is not None:
                audio_quality = acoustic_result.get("audio_quality")
                fused = speech_analysis.combine_emotion_results(  # type: ignore[union-attr]
                    acoustic_result, transcript, audio_quality=audio_quality
                )
                stress = fused.get("stress_assessment", {})
                result["acoustic_stress"] = stress.get("stress_score")
                result["vocal_tone"] = str(fused.get("emotion") or "unclear")
                result["acoustic_available"] = True
                result["fusion_source"] = "acoustic + transcript (Wav2Vec2 + Whisper)"
            elif transcript:
                text_probs = speech_analysis.text_emotion_probabilities(transcript)  # type: ignore[union-attr]
                if text_probs:
                    stress = stress_interpretation.assess_stress(text_probs)  # type: ignore[union-attr]
                    result["acoustic_stress"] = stress.get("stress_score")
                    result["vocal_tone"] = max(text_probs, key=text_probs.get)
                result["acoustic_available"] = False
                result["fusion_source"] = "transcript-only (no fine-tuned acoustic weights found)"
            else:
                result["acoustic_available"] = False
                result["fusion_source"] = "no usable signal (transcription and acoustic model both unavailable)"
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        return result

    def process_turn(
        self,
        user_text: str,
        chat_history: Optional[List[dict]] = None,
        history_scores: Optional[List[float]] = None,
        voice_diagnostics: Optional[dict[str, Any]] = None,
    ) -> TurnResult:
        """Run the current text triage/RAG/Gemini sequence without UI state."""
        history = chat_history or []
        scores = history_scores or []
        analysis_started = time.perf_counter()
        emotion, assessment = self.risk_analyzer.assess_risk(user_text, scores)
        analysis_ms = (time.perf_counter() - analysis_started) * 1000

        if assessment.is_crisis:
            rag_context = RAGContext(is_used=False)
            reply = RiskAnalyzer.get_crisis_response()
            rag_ms = 0.0
            gemini_ms = 0.0
        else:
            rag_started = time.perf_counter()
            rag_context = self.rag_engine.retrieve(user_text, assessment.score)
            rag_ms = (time.perf_counter() - rag_started) * 1000
            gemini_started = time.perf_counter()
            reply = self.generate_reply(user_text, history, rag_context)
            gemini_ms = (time.perf_counter() - gemini_started) * 1000

        return TurnResult(
            assistant_response=reply,
            emotion=emotion,
            assessment=assessment,
            rag_context=rag_context,
            voice_diagnostics=voice_diagnostics,
            latency_ms={
                "text_analysis_ms": analysis_ms,
                "rag_retrieval_ms": rag_ms,
                "gemini_generation_ms": gemini_ms,
            },
        )

    def process_voice_turn(
        self,
        audio_bytes: bytes,
        suffix: str = ".wav",
        chat_history: Optional[List[dict]] = None,
        history_scores: Optional[List[float]] = None,
    ) -> tuple[Optional[TurnResult], dict[str, Any]]:
        """Run the existing voice path, then the shared transcript turn path."""
        diagnostics = self.process_voice_input(audio_bytes, suffix=suffix)
        transcript = diagnostics.get("transcript")
        if not transcript:
            return None, diagnostics
        transcript_history = list(chat_history or [])
        transcript_history.append({"role": "user", "content": transcript})
        return self.process_turn(
            transcript,
            chat_history=transcript_history,
            history_scores=history_scores,
            voice_diagnostics=diagnostics,
        ), diagnostics
