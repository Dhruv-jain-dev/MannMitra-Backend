"""
app.py
======
MANNMITRA - Unified multimodal (text + voice) student mental-health triage
Streamlit application.

Orchestrates:
  - risk_analysis.RiskAnalyzer      (GoEmotions sentiment + regex crisis guardrails
                                      + multi-turn distress compounding)
  - rag_engine.RAGEngine            (persistent ChromaDB knowledge retrieval)
  - speech_engine.*                 (Whisper STT + acoustic/transcript fused
                                      emotion + non-clinical stress scoring)
  - Google GenAI (gemini-1.5-flash / gemini-2.5-flash)

into a single empathetic peer-listener chat experience with a live triage
sidebar, dual text/voice input, and hard crisis guardrails.
"""

from __future__ import annotations

import os
import sys
import hashlib
import logging
import tempfile
import importlib
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, List, Optional

import streamlit as st
from dotenv import load_dotenv

from risk_analysis import RiskAnalyzer, EmotionResult, RiskAssessment
from rag_engine import RAGEngine, RAGContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mannmitra.app")

# --------------------------------------------------------------------------
# Environment loading / API-key harmonization
# --------------------------------------------------------------------------
# Loaded once, without clobbering any variables already set by the host
# environment (e.g. a deployment platform's own secret injection).
load_dotenv(override=False)


def _harmonize_gemini_key() -> str:
    """Resolve GEMINI_API_KEY from either GEMINI_API_KEY or GOOGLE_API_KEY.

    google-genai's own credential discovery also inspects GOOGLE_API_KEY, so
    if both variables happen to be set the SDK can emit a "multiple
    credentials found" warning. We resolve to a single canonical value and
    remove the alias so only one source of truth remains in the environment.
    """
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
        os.environ.pop("GOOGLE_API_KEY", None)
    return key


GEMINI_API_KEY = _harmonize_gemini_key()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
    _GENAI_AVAILABLE = False

# BLOCK_NONE across all four harm categories so ordinary student expressions
# of stress, fatigue, self-criticism, or frustration are never filtered by
# the safety layer before RiskAnalyzer/RAGEngine ever see them.
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
    "students. You are NOT a therapist and never diagnose. Respond in 2-3 "
    "concise, natural sentences, in a caring, non-clinical, conversational "
    "tone - like a supportive friend, not a textbook. Validate the "
    "student's feelings before offering any gentle suggestion. If helpful "
    "context about a coping technique or campus resource is provided to "
    "you, weave it naturally into your own words as a friendly suggestion "
    "- never quote titles, filenames, or headers verbatim, and never say "
    "things like '[Source: ...]'. Keep responses grounded, human, and "
    "free of clinical jargon. Talk in non-repeating semi-casual patterns."
)

TIER_BADGES = {"GREEN": "🟢 GREEN", "YELLOW": "🟡 YELLOW", "RED": "🔴 RED"}

# --------------------------------------------------------------------------
# Dynamic module resolution for ./speech_engine
# --------------------------------------------------------------------------
# We resolve the speech engine at *runtime* via importlib rather than a
# static `import speech_engine.x`, because editors/type-checkers (Pylance)
# that don't have this project's root on their analysis path otherwise flag
# a spurious `reportMissingImports`. Adding the real directory to sys.path
# and importing dynamically works correctly at runtime regardless of the
# editor's configured project root.
APP_DIR = Path(__file__).resolve().parent
SPEECH_ENGINE_DIR = APP_DIR / "speech_engine"

if TYPE_CHECKING:  # pragma: no cover - type-checking only, never executed
    from speech_engine import (  # noqa: F401
        predict_speech_emotion as _predict_speech_emotion_typing,
        speech_analysis as _speech_analysis_typing,
        speech_to_text as _speech_to_text_typing,
        stress_interpretation as _stress_interpretation_typing,
    )


def _load_speech_module(module_name: str) -> ModuleType:
    if str(SPEECH_ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(SPEECH_ENGINE_DIR))
    return importlib.import_module(module_name)


_SPEECH_ENGINE_AVAILABLE = False
speech_to_text = None
speech_analysis = None
stress_interpretation = None
predict_speech_emotion = None

try:
    speech_to_text = _load_speech_module("speech_to_text")
    speech_analysis = _load_speech_module("speech_analysis")
    stress_interpretation = _load_speech_module("stress_interpretation")
    predict_speech_emotion = _load_speech_module("predict_speech_emotion")
    _SPEECH_ENGINE_AVAILABLE = True
    logger.info("Speech engine loaded from %s.", SPEECH_ENGINE_DIR)
except Exception as exc:  # noqa: BLE001
    logger.warning("Speech engine unavailable (%s); voice input will be disabled.", exc)
    _SPEECH_ENGINE_AVAILABLE = False

_ACOUSTIC_MODEL_AVAILABLE = False
if _SPEECH_ENGINE_AVAILABLE and predict_speech_emotion is not None:
    try:
        _ACOUSTIC_MODEL_AVAILABLE = bool(predict_speech_emotion.acoustic_model_available())
    except Exception:  # noqa: BLE001
        _ACOUSTIC_MODEL_AVAILABLE = False

# --------------------------------------------------------------------------
# Cached singletons
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading risk analyzer...")
def get_risk_analyzer() -> RiskAnalyzer:
    return RiskAnalyzer()


@st.cache_resource(show_spinner="Loading knowledge base...")
def get_rag_engine() -> RAGEngine:
    return RAGEngine()


# --------------------------------------------------------------------------
# LLM call
# --------------------------------------------------------------------------
def generate_reply(user_text: str, chat_history: List[dict], rag_context: RAGContext) -> str:
    if not _GENAI_AVAILABLE or _genai_client is None:
        return (
            "I hear you, and I'm really glad you shared that with me. "
            "Thanks for opening up - want to tell me a bit more about what's "
            "been going on?"
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
        "Respond as MannMitra in 2-3 sentences:"
    )

    try:
        config_kwargs = {"system_instruction": SYSTEM_PROMPT}
        if _SAFETY_SETTINGS is not None:
            config_kwargs["safety_settings"] = _SAFETY_SETTINGS
        response = _genai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=_genai_types.GenerateContentConfig(**config_kwargs) if _genai_types else None,
        )
        text = (response.text or "").strip()
        return text if text else "I'm here with you - can you tell me a little more?"
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini generation failed: %s", exc)
        return (
            "I'm here and listening, even though I'm having a little trouble "
            "finding the right words right now. Can you tell me more about "
            "how you're feeling?"
        )


# --------------------------------------------------------------------------
# Voice processing pipeline
# --------------------------------------------------------------------------
def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def process_voice_input(audio_bytes: bytes, suffix: str = ".wav") -> dict:
    """Transcribe + analyze a recorded/uploaded audio clip.

    Returns a dict with:
      transcript: str | None
      transcript_warning: str | None
      duration: float | None
      acoustic_stress: float | None   (0-100 heuristic, if available)
      vocal_tone: str                 (predicted emotion label, or 'unknown')
      acoustic_available: bool        (whether the fine-tuned acoustic model ran)
      fusion_source: str              (how the emotion estimate was derived)
    """
    result = {
        "transcript": None,
        "transcript_warning": None,
        "duration": None,
        "acoustic_stress": None,
        "vocal_tone": "unknown",
        "acoustic_available": False,
        "fusion_source": "unavailable",
    }

    if not _SPEECH_ENGINE_AVAILABLE:
        result["transcript_warning"] = "Speech engine is not installed; voice input is unavailable."
        return result

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = Path(tmp_file.name)

        # --- 1. Whisper transcription (always attempted) -------------------
        try:
            transcript = speech_to_text.transcribe_audio(tmp_path)
            result["transcript"] = transcript
        except speech_to_text.TranscriptionError as exc:
            transcript = None
            result["transcript_warning"] = str(exc)

        # --- 2. Acoustic emotion (best-effort, graceful fallback) ---------
        acoustic_result = None
        try:
            acoustic_result = predict_speech_emotion.predict_emotion(tmp_path)
            result["duration"] = acoustic_result.get("duration_seconds")
        except predict_speech_emotion.AcousticModelUnavailable as exc:
            logger.info("Acoustic model unavailable (%s); falling back to transcript-only cues.", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Acoustic inference failed (%s); falling back to transcript-only cues.", exc)

        if result["duration"] is None:
            # Even without the acoustic model, report clip duration for the UI.
            try:
                waveform = predict_speech_emotion._load_audio(tmp_path, predict_speech_emotion.TARGET_SAMPLE_RATE)
                result["duration"] = round(
                    float(len(waveform)) / float(predict_speech_emotion.TARGET_SAMPLE_RATE), 4
                )
            except Exception:  # noqa: BLE001
                result["duration"] = None

        # --- 3. Fuse acoustic + transcript, or fall back to transcript-only -
        if acoustic_result is not None:
            audio_quality = acoustic_result.get("audio_quality")
            fused = speech_analysis.combine_emotion_results(acoustic_result, transcript, audio_quality=audio_quality)
            stress = fused.get("stress_assessment", {})
            result["acoustic_stress"] = stress.get("stress_score")
            result["vocal_tone"] = str(fused.get("emotion") or "unclear")
            result["acoustic_available"] = True
            result["fusion_source"] = "acoustic + transcript (Wav2Vec2 + Whisper)"
        elif transcript:
            text_probs = speech_analysis.text_emotion_probabilities(transcript)
            if text_probs:
                stress = stress_interpretation.assess_stress(text_probs)
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


# --------------------------------------------------------------------------
# Streamlit page setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="MannMitra", page_icon="🧠", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role","content","tier","emotion","rag_used","voice"}
if "history_scores" not in st.session_state:
    st.session_state.history_scores = []
if "last_assessment" not in st.session_state:
    st.session_state.last_assessment = None
if "last_emotion" not in st.session_state:
    st.session_state.last_emotion = None
if "last_rag" not in st.session_state:
    st.session_state.last_rag = None
if "last_voice" not in st.session_state:
    st.session_state.last_voice = None
if "_last_audio_hash" not in st.session_state:
    st.session_state._last_audio_hash = None

analyzer = get_risk_analyzer()
rag_engine = get_rag_engine()

# --------------------------------------------------------------------------
# Sidebar - live analytics
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🧠 MannMitra")
    st.caption("Live wellbeing analytics")

    st.subheader("System Status")
    if _GENAI_AVAILABLE:
        st.success("🟢 Gemini Connected")
    else:
        st.warning("🔴 Gemini Disconnected (static fallback active)")

    if _SPEECH_ENGINE_AVAILABLE:
        if _ACOUSTIC_MODEL_AVAILABLE:
            st.success("🟢 Speech engine ready (acoustic + Whisper)")
        else:
            st.info("🟡 Speech engine ready (Whisper only - no fine-tuned acoustic weights)")
    else:
        st.warning("🔴 Speech engine unavailable (voice input disabled)")

    st.divider()
    st.subheader("Triage Status")
    if st.session_state.last_assessment is not None:
        tier = st.session_state.last_assessment.tier
        score = st.session_state.last_assessment.score
    else:
        tier, score = "GREEN", 0.0
    st.markdown(f"### {TIER_BADGES[tier]}")
    st.progress(min(1.0, max(0.0, score)))
    st.caption(f"Composite Distress Score: {score:.2f}")

    st.subheader("Emotion Breakdown")
    if st.session_state.last_emotion is not None and st.session_state.last_emotion.all_emotions:
        top_emotions = sorted(
            st.session_state.last_emotion.all_emotions.items(), key=lambda kv: kv[1], reverse=True
        )[:5]
        for label, prob in top_emotions:
            st.write(f"**{label}**")
            st.progress(min(1.0, max(0.0, float(prob))))
    else:
        st.caption("No emotion data yet - send a message to begin.")

    if st.session_state.last_voice is not None:
        st.subheader("🎙️ Last Voice Signal")
        v = st.session_state.last_voice
        st.caption(f"Vocal tone: **{v.get('vocal_tone', 'unknown')}**")
        if v.get("acoustic_stress") is not None:
            st.progress(min(1.0, max(0.0, float(v["acoustic_stress"]) / 100.0)))
            st.caption(f"Acoustic stress score: {v['acoustic_stress']:.1f} / 100")

    st.subheader("Knowledge Retrieval (RAG)")
    if st.session_state.last_rag is not None and st.session_state.last_rag.is_used:
        sources = ", ".join(sorted(set(st.session_state.last_rag.sources)))
        st.success(f"✓ Injected: {sources}")
    else:
        st.info("Standby - no relevant resource retrieved.")

    st.divider()
    st.subheader("📞 Verified Helplines (India)")
    st.markdown(
        "- **Tele-MANAS**: `14416` (24/7, free)\n"
        "- **KIRAN**: `1800-599-0019` (24/7, toll-free)"
    )
    st.caption(
        "If you or someone you know is in immediate danger, please contact "
        "local emergency services or go to the nearest hospital."
    )

# --------------------------------------------------------------------------
# Main chat area
# --------------------------------------------------------------------------
st.header("Chat with MannMitra")
st.caption("A private space to talk things through. This is peer support, not a substitute for professional care.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        voice = msg.get("voice")
        if msg["role"] == "user" and voice:
            with st.expander("🎙️ Acoustic & Speech Diagnostics"):
                st.write(f"**Duration:** {voice.get('duration', 'n/a')} s")
                acoustic_stress = voice.get("acoustic_stress")
                st.write(f"**Acoustic stress score:** {f'{acoustic_stress:.1f} / 100' if acoustic_stress is not None else 'n/a'}")
                st.write(f"**Detected vocal tone:** {voice.get('vocal_tone', 'unknown')}")
                st.caption(voice.get("fusion_source", ""))
                if voice.get("transcript_warning"):
                    st.caption(f"⚠️ {voice['transcript_warning']}")
        if msg["role"] == "assistant" and "tier" in msg:
            st.caption(
                f"Tier: {msg['tier']} · Emotion: {msg.get('emotion', 'n/a')} · "
                f"Knowledge Injected: {'Yes' if msg.get('rag_used') else 'No'}"
            )


def handle_user_turn(user_text: str, voice_diagnostics: Optional[dict] = None) -> None:
    """Shared pipeline for both text and voice turns, guaranteeing full
    behavioral parity: identical risk assessment, RAG gating, and crisis
    guardrails regardless of input modality."""
    st.session_state.messages.append(
        {"role": "user", "content": user_text, "voice": voice_diagnostics}
    )
    with st.chat_message("user"):
        st.markdown(user_text)
        if voice_diagnostics:
            with st.expander("🎙️ Acoustic & Speech Diagnostics"):
                st.write(f"**Duration:** {voice_diagnostics.get('duration', 'n/a')} s")
                acoustic_stress = voice_diagnostics.get("acoustic_stress")
                st.write(
                    "**Acoustic stress score:** "
                    f"{f'{acoustic_stress:.1f} / 100' if acoustic_stress is not None else 'n/a'}"
                )
                st.write(f"**Detected vocal tone:** {voice_diagnostics.get('vocal_tone', 'unknown')}")
                st.caption(voice_diagnostics.get("fusion_source", ""))
                if voice_diagnostics.get("transcript_warning"):
                    st.caption(f"⚠️ {voice_diagnostics['transcript_warning']}")

    emotion, assessment = analyzer.assess_risk(user_text, st.session_state.history_scores)
    st.session_state.history_scores.append(assessment.score)
    st.session_state.last_assessment = assessment
    st.session_state.last_emotion = emotion
    if voice_diagnostics:
        st.session_state.last_voice = voice_diagnostics

    if assessment.is_crisis:
        # Tier 0 - deterministic bypass: never call the LLM for crisis turns.
        rag_context = RAGContext(is_used=False)
        reply = RiskAnalyzer.get_crisis_response()
    else:
        rag_context = rag_engine.retrieve(user_text, assessment.score)
        history_for_llm = st.session_state.messages
        reply = generate_reply(user_text, history_for_llm, rag_context)
    st.session_state.last_rag = rag_context

    with st.chat_message("assistant"):
        st.markdown(reply)
        st.caption(
            f"Tier: {assessment.tier} · Emotion: {emotion.label} · "
            f"Knowledge Injected: {'Yes' if rag_context.is_used else 'No'}"
        )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": reply,
            "tier": assessment.tier,
            "emotion": emotion.label,
            "rag_used": rag_context.is_used,
        }
    )
    st.rerun()


# --------------------------------------------------------------------------
# Voice input (recorder + file-upload fallback)
# --------------------------------------------------------------------------
if _SPEECH_ENGINE_AVAILABLE:
    with st.expander("🎤 Voice message (record or upload)"):
        col_rec, col_upload = st.columns(2)

        with col_rec:
            # Deliberately no `sample_rate=` / other rigid kwargs here: forcing
            # a specific capture sample rate is what triggers browser WebRTC
            # capture errors on some devices. We resample ourselves downstream.
            recorded_audio = st.audio_input("Record your voice")

        with col_upload:
            uploaded_audio = st.file_uploader(
                "...or upload a .wav / .mp3 file", type=["wav", "mp3"], key="voice_uploader"
            )

        audio_source = recorded_audio or uploaded_audio
        send_voice = st.button("Send voice message", type="primary", disabled=audio_source is None)

        if send_voice and audio_source is not None:
            audio_bytes = audio_source.getvalue()
            audio_hash = _hash_bytes(audio_bytes)
            if audio_bytes and audio_hash != st.session_state._last_audio_hash:
                st.session_state._last_audio_hash = audio_hash
                suffix = ".mp3" if getattr(audio_source, "name", "").lower().endswith(".mp3") else ".wav"
                with st.spinner("Transcribing and analyzing your voice message..."):
                    diagnostics = process_voice_input(audio_bytes, suffix=suffix)

                transcript = diagnostics.get("transcript")
                if transcript:
                    handle_user_turn(transcript, voice_diagnostics=diagnostics)
                else:
                    st.error(
                        diagnostics.get("transcript_warning")
                        or "Could not transcribe that recording. Please try again."
                    )
            elif not audio_bytes:
                st.error("That recording looks empty. Please try again.")
else:
    st.caption("🔇 Voice input is unavailable in this environment (speech_engine failed to load).")

# --------------------------------------------------------------------------
# Text input
# --------------------------------------------------------------------------
user_input = st.chat_input("Share what's on your mind...")
if user_input:
    handle_user_turn(user_input, voice_diagnostics=None)
