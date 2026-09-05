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
  - Google GenAI (gemini-3.5-flash-lite)

into a single empathetic peer-listener chat experience with a live triage
sidebar, dual text/voice input, and hard crisis guardrails.
"""

from __future__ import annotations

import logging
from typing import Optional

import streamlit as st

from backend.services.mannmitra_service import MannMitraService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mannmitra.app")

TIER_BADGES = {"GREEN": "🟢 GREEN", "YELLOW": "🟡 YELLOW", "RED": "🔴 RED"}

# --------------------------------------------------------------------------
# Cached backend service
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading risk analyzer...")
def get_mannmitra_service() -> MannMitraService:
    return MannMitraService()


# --------------------------------------------------------------------------
# Streamlit page setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="MannMitra", page_icon="🧠", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
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

mannmitra_service = get_mannmitra_service()

# --------------------------------------------------------------------------
# Sidebar - live analytics
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🧠 MannMitra")
    st.caption("Live wellbeing analytics")

    st.subheader("System Status")
    if mannmitra_service.gemini_available:
        st.success(f"🟢 Connected: {mannmitra_service.gemini_model}")
    else:
        st.warning("🔴 Gemini Disconnected (static fallback active)")

    if mannmitra_service.speech_engine_available:
        if mannmitra_service.acoustic_model_available:
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

    turn_result = mannmitra_service.process_turn(
        user_text,
        chat_history=st.session_state.messages,
        history_scores=st.session_state.history_scores,
        voice_diagnostics=voice_diagnostics,
    )
    reply = turn_result.assistant_response
    emotion = turn_result.emotion
    assessment = turn_result.assessment
    rag_context = turn_result.rag_context
    st.session_state.history_scores.append(assessment.score)
    st.session_state.last_assessment = assessment
    st.session_state.last_emotion = emotion
    if voice_diagnostics:
        st.session_state.last_voice = voice_diagnostics
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
if mannmitra_service.speech_engine_available:
    with st.expander("🎤 Voice message (record or upload)"):
        col_rec, col_upload = st.columns(2)

        with col_rec:
            recorded_audio = st.audio_input("Record your voice")

        with col_upload:
            uploaded_audio = st.file_uploader(
                "...or upload a .wav / .mp3 file", type=["wav", "mp3"], key="voice_uploader"
            )

        audio_source = recorded_audio or uploaded_audio
        send_voice = st.button("Send voice message", type="primary", disabled=audio_source is None)

        if send_voice and audio_source is not None:
            audio_bytes = audio_source.getvalue()
            audio_hash = mannmitra_service.hash_audio(audio_bytes)
            if audio_bytes and audio_hash != st.session_state._last_audio_hash:
                st.session_state._last_audio_hash = audio_hash
                suffix = ".mp3" if getattr(audio_source, "name", "").lower().endswith(".mp3") else ".wav"
                with st.spinner("Transcribing and analyzing your voice message..."):
                    diagnostics = mannmitra_service.process_voice_input(audio_bytes, suffix=suffix)

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
