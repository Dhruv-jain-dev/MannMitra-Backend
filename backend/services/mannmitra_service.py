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
try:
    GEMINI_TIMEOUT_MS = max(5_000, min(int(os.environ.get("GEMINI_TIMEOUT_MS", "75000")), 120_000))
except ValueError:
    GEMINI_TIMEOUT_MS = 75_000


class GeminiGenerationError(RuntimeError):
    """Safe, categorized Gemini failure without prompt or credential data."""

    def __init__(self, category: str, public_detail: str) -> None:
        super().__init__(public_detail)
        self.category = category
        self.public_detail = public_detail

_GENAI_AVAILABLE = False
_genai_client = None
_genai_types = None

try:
    from google import genai as _google_genai
    from google.genai import types as _google_genai_types

    if GEMINI_API_KEY:
        _genai_types = _google_genai_types
        _genai_client = _google_genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=_genai_types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
        )
        _GENAI_AVAILABLE = True
    else:
        logger.warning("No GEMINI_API_KEY / GOOGLE_API_KEY found in environment.")
except Exception as exc:  # noqa: BLE001
    logger.warning("google-genai unavailable (%s). AI generation will be unavailable.", type(exc).__name__)

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
    "textbook. Respond naturally to the student's message and let the "
    "conversation guide the style and length of your response. "

    "Use normal conversational paragraphs by default. When useful, "
    "you may use concise Markdown bullet points for clear suggestions or coping steps but within 20-30 words max, "
    "but do not force bullet points or a fixed structure on every response. "
    "Simple conversation, emotional sharing, reassurance, and casual updates "
    "should remain natural prose. Use numbered lists only when giving "
    "sequential steps, and use headings only when they genuinely improve "
    "clarity. "

    "If helpful context about a coping technique or campus resource is "
    "provided to you, weave it naturally into your own words as a friendly "
    "suggestion - never quote titles, filenames, or headers verbatim, and "
    "never say things like '[Source: ...]'. Keep responses grounded, human, "
    "and free of clinical jargon. Talk in non-repeating semi-casual patterns."
)


_EXPLICIT_MEMORY_PATTERNS = (
    r"\b(what|do|did|can)\b.*\b(i|we)\b.*\b(tell|say|discuss|mention|talk)\b.*\b(earlier|before|previous|last|yesterday)\b",
    r"\bwhat did\b.*\b(tell|say|discuss|mention|talk)\b.*\b(previously|earlier|before|previous|last|yesterday)\b",
    r"\b(do you )?(remember|recall)\b.*\b(earlier|before|previous|last|yesterday|chat)\b",
    r"\b(do you )?(remember|recall)\b.*\b(i|we)\b.*\b(tell|told|say|mention|discuss|talk)\b",
    r"\bwhat did we\b.*\b(discuss|talk|say|mention)\b",
    r"\bwhat did (i|we)\b.*\b(earlier|before|previous|last|yesterday)\b",
    r"\b(can you|could you)\b.*\b(remind|recap|summarize)\b.*\b(what|we|our)\b",
)


predict_speech_emotion = None
speech_analysis = None
speech_to_text = None
stress_interpretation = None
_SPEECH_ENGINE_AVAILABLE = False
_SPEECH_LOAD_ATTEMPTED = False


def _ensure_speech_engine() -> bool:
    """Load voice dependencies only when a voice turn is requested."""
    global _SPEECH_LOAD_ATTEMPTED, _SPEECH_ENGINE_AVAILABLE
    global predict_speech_emotion, speech_analysis, speech_to_text, stress_interpretation
    if _SPEECH_LOAD_ATTEMPTED:
        return _SPEECH_ENGINE_AVAILABLE
    _SPEECH_LOAD_ATTEMPTED = True
    try:
        import predict_speech_emotion as acoustic_module
        import speech_analysis as speech_analysis_module
        import speech_to_text as speech_to_text_module
        import stress_interpretation as stress_module
        predict_speech_emotion = acoustic_module
        speech_analysis = speech_analysis_module
        speech_to_text = speech_to_text_module
        stress_interpretation = stress_module
        _SPEECH_ENGINE_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Speech engine unavailable (%s); voice input will be disabled.", exc)
        _SPEECH_ENGINE_AVAILABLE = False
    return _SPEECH_ENGINE_AVAILABLE


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


def _gemini_error_category(error: Exception) -> str:
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    message = str(error).casefold()
    if status_code in {401, 403}:
        return "authentication"
    if status_code == 429 or "rate limit" in message or "quota" in message or "resource exhausted" in message:
        return "rate_limit"
    if "timeout" in message or "timed out" in message or "deadline" in message:
        return "timeout"
    return "service"


def _gemini_public_detail(category: str) -> str:
    return {
        "authentication": "AI service authentication failed. Please contact support.",
        "rate_limit": "AI service capacity is temporarily exhausted. Please try again shortly.",
        "timeout": "AI generation took too long. Your message was saved; please try again.",
        "service": "AI generation is temporarily unavailable. Your message was saved; please try again.",
        "not_configured": "AI generation is not configured.",
    }.get(category, "AI generation is temporarily unavailable. Please try again.")


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

    @staticmethod
    def is_explicit_memory_request(text: str) -> bool:
        import re

        normalized = " ".join(text.casefold().split())
        return any(re.search(pattern, normalized) for pattern in _EXPLICIT_MEMORY_PATTERNS)

    @staticmethod
    def _memory_terms(text: str) -> set[str]:
        import re

        ignored = {
            "about", "again", "ask", "before", "can", "could", "did", "discuss", "earlier",
            "from", "have", "help", "here", "how", "into", "just", "last", "me", "need",
            "previous", "recall", "remember", "say", "should", "talk", "tell", "that", "this",
            "told", "want", "what", "with", "would", "yesterday", "you", "your", "previously",
            "chat", "conversation", "history", "memory", "our", "remind", "recap", "summarize",
        }
        terms = set(re.findall(r"[a-z0-9]+", text.casefold()))
        return {term[:-1] if len(term) > 4 and term.endswith("s") else term for term in terms if len(term) > 2 and term not in ignored}

    def select_previous_memory(self, query: str, candidates: List[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank bounded user-owned candidates, prioritizing explicit recall requests."""
        if not candidates:
            return []
        query_terms = self._memory_terms(query)
        explicit = self.is_explicit_memory_request(query)
        ranked: list[tuple[float, Any, dict[str, Any]]] = []
        for candidate in candidates:
            lexical_overlap = len(query_terms & self._memory_terms(candidate["content"]))
            if lexical_overlap:
                ranked.append((float(lexical_overlap), candidate["created_at"], candidate))
        if ranked:
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [item[2] for item in ranked[:2]]

        # Topic-specific recall can still be relevant when wording differs
        # from the original message, so try semantic ranking before falling
        # back to the most recent prior message.
        try:
            similarities = self.rag_engine.semantic_similarities(
                query, [item["content"] for item in candidates[:24]]
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Previous-chat semantic ranking unavailable (%s).", exc)
            similarities = []
        semantic = [(score, candidates[index]) for index, score in enumerate(similarities) if score >= 0.42]
        semantic.sort(key=lambda item: (item[0], item[1]["created_at"]), reverse=True)
        if semantic:
            return [item[1] for item in semantic[:2]]
        if explicit and not query_terms:
            # An explicit history question without a recoverable topic refers
            # to the most recent prior chat, whose surrounding context is
            # bounded and fetched separately by the repository.
            return [candidates[0]]
        return []

    def generate_reply(
        self,
        user_text: str,
        chat_history: List[dict],
        rag_context: RAGContext,
        previous_memory: Optional[List[dict]] = None,
        memory_lookup_attempted: bool = False,
    ) -> str:
        """The existing single-call Gemini response path for eligible turns."""
        if not self.gemini_available:
            raise GeminiGenerationError("not_configured", "AI generation is not configured")

        context_note = ""
        if rag_context.is_used and rag_context.retrieved_documents:
            chunks = [chunk.strip() for chunk in rag_context.retrieved_documents[:2] if chunk and chunk.strip()]
            if chunks:
                joined = "\n\n".join(
                    f"[Support chunk {index}]\n{chunk}" for index, chunk in enumerate(chunks, start=1)
                )
                context_note = (
                    "\n\n--- Retrieved support context (not conversation history) ---\n"
                    "Use this reference material only when it is relevant to the student's current message. "
                    "If it is not relevant, ignore it. Paraphrase it naturally; do not quote filenames or headers. "
                    "Do not turn it into a diagnosis, medical claim, or guaranteed outcome.\n"
                    f"{joined}\n"
                    "--- End retrieved support context ---"
                )

        convo_lines = []
        for turn in chat_history[0:]:
            role = "Student" if turn["role"] == "user" else "MannMitra"
            convo_lines.append(f"{role}: {turn['content']}")
        convo_text = "\n".join(convo_lines)
        memory_note = ""
        if previous_memory:
            memory_lines = []
            for turn in previous_memory:
                role = "Student" if turn.get("role") == "user" else "MannMitra"
                memory_lines.append(f"{role} (earlier chat): {turn['content']}")
            memory_note = (
                "\n\nRelevant previous-chat memory (separate from support documents; "
                "use only when it helps answer the student's message):\n"
                + "\n".join(memory_lines)
            )

        prompt = (
            f"Conversation history (what has been said in this chat):\n{convo_text or '(none)'}"
            f"{memory_note}{context_note}\n\n"
            f"Current student's message:\n{user_text}\n\n"
            "Keep the response non-clinical and supportive. Use retrieved support context only when it helps; "
            "never invent medical or psychological claims.\n\n"
            "Respond naturally as MannMitra:"
        )

        try:
            config = None
            if _genai_types is not None:
                config = _genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    max_output_tokens=180,
                    safety_settings=_SAFETY_SETTINGS if _SAFETY_SETTINGS else None,
                )

            response = _genai_client.models.generate_content(  # type: ignore[union-attr]
                model=self.gemini_model,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            reply = text if text else "I'm here with you - can you tell me a little more?"
            if memory_lookup_attempted and not previous_memory:
                return "I couldn't find matching information in your previous conversations.\n\n" + reply
            return reply
        except Exception as exc:  # noqa: BLE001
            category = _gemini_error_category(exc)
            logger.warning("Gemini generation failed category=%s model=%s", category, self.gemini_model)
            raise GeminiGenerationError(category, _gemini_public_detail(category)) from exc


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
        self.speech_engine_available = _ensure_speech_engine()
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
        previous_memory: Optional[List[dict]] = None,
        memory_lookup_attempted: bool = False,
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
            reply = self.generate_reply(user_text, history, rag_context, previous_memory, memory_lookup_attempted)
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
