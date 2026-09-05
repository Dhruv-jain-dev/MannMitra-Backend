"""Conversation persistence and idempotent turn storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Literal

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from backend.models import Conversation, Message, MessageAnalysis, User
from backend.services.mannmitra_service import TurnResult


@dataclass
class TurnClaim:
    status: Literal["claimed", "completed", "in_progress"]
    user_message: Message
    assistant_message: Message | None = None


class ConversationRepository:
    """Synchronous repository used by the synchronous Phase 2 API routes."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _next_position(session: Session, conversation_id: str) -> int:
        current = session.scalar(
            select(func.max(Message.position)).where(Message.conversation_id == conversation_id)
        )
        # Reserve the following position for the corresponding assistant reply.
        return int(current or 0) + 2

    @staticmethod
    def _get_or_create_user(session: Session, user_id: str) -> User:
        user = session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            session.add(user)
            session.flush()
        return user

    def create_conversation(self, user_id: str, title: str | None = None) -> Conversation:
        with self._session() as session:
            self._get_or_create_user(session, user_id)
            conversation = Conversation(user_id=user_id, title=title)
            session.add(conversation)
            session.commit()
            return conversation

    @staticmethod
    def _is_generic_title(title: str | None) -> bool:
        return not title or title.strip().casefold() in {
            "mannmitra conversation", "untitled conversation", "wellbeing check-in",
            "exam stress & planning", "sleep problems", "relationship concerns",
            "today's anxiety", "feeling overwhelmed", "college work stress", "family concerns",
        }

    @staticmethod
    def _conversation_title(text: str) -> str | None:
        """Create a concise, non-sensitive local title without another model request."""
        words = re.findall(r"[a-zA-Z0-9]+", text.casefold())
        stop_words = {"a", "about", "am", "an", "and", "are", "at", "be", "because", "can", "could", "do", "for", "from", "had", "have", "how", "i", "im", "in", "is", "it", "me", "my", "next", "of", "on", "really", "should", "that", "the", "to", "want", "week", "with", "you"}
        terms = [word for word in words if len(word) > 1 and word not in stop_words]
        term_set = set(terms)
        if len(terms) < 2:
            return None
        if term_set & {"argument", "disagreement", "conflict"} and term_set & {"roommate", "friend", "partner", "family"}:
            subject = next(word for word in terms if word in {"roommate", "friend", "partner", "family"})
            return f"{subject.title()} Conflict"
        if term_set & {"talk", "speak", "approach"} and term_set & {"professor", "teacher", "lecturer", "advisor"}:
            person = next(word for word in terms if word in {"professor", "teacher", "lecturer", "advisor"})
            return f"Talking to {person.title()}"
        if "sleep" in term_set and term_set & {"improve", "improving", "schedule", "better"}:
            return "Improving Sleep Schedule"
        if term_set & {"exam", "exams", "test", "tests"}:
            subject = next((word for word in terms if word in {"maths", "math", "mathematics", "physics", "chemistry", "biology"}), None)
            stress = next((word for word in terms if word in {"stress", "stressed", "worried", "anxious", "anxiety"}), None)
            subject_label = {"math": "Maths", "mathematics": "Maths"}.get(subject or "", subject.title() if subject else "")
            pieces = ([subject_label] if subject_label else []) + ["Exam"] + (["Stress"] if stress else [])
            return " ".join(pieces)
        title_terms = terms[:4]
        return " ".join(word.title() for word in title_terms)

    def _backfill_generic_titles(self, session: Session, user_id: str) -> None:
        conversations = list(
            session.scalars(select(Conversation).where(Conversation.user_id == user_id))
        )
        changed = False
        for conversation in conversations:
            if not self._is_generic_title(conversation.title):
                continue
            first_message = session.scalar(
                select(Message.content)
                .where(Message.conversation_id == conversation.id, Message.role == "user", Message.content != "")
                .order_by(Message.position)
                .limit(1)
            )
            title = self._conversation_title(first_message) if first_message else None
            if title:
                conversation.title = title
                changed = True
        if changed:
            session.commit()

    def set_title_from_message(self, user_id: str, conversation_id: str, text: str) -> None:
        """Title a new or legacy generic conversation once from its first useful turn."""
        with self._session() as session:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            title = self._conversation_title(text)
            if conversation is not None and title and self._is_generic_title(conversation.title):
                conversation.title = title
                session.commit()

    def list_conversations(self, user_id: str) -> list[Conversation]:
        with self._session() as session:
            self._backfill_generic_titles(session, user_id)
            return list(
                session.scalars(
                    select(Conversation)
                    .where(Conversation.user_id == user_id)
                    .order_by(desc(Conversation.updated_at), desc(Conversation.created_at))
                )
            )

    def get_conversation(self, user_id: str, conversation_id: str) -> Conversation | None:
        with self._session() as session:
            return session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )

    def get_messages(self, user_id: str, conversation_id: str) -> list[Message] | None:
        if self.get_conversation(user_id, conversation_id) is None:
            return None
        with self._session() as session:
            return list(
                session.scalars(
                    select(Message)
                    .options(selectinload(Message.analysis))
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.position)
                )
            )

    def claim_user_turn(
        self,
        user_id: str,
        conversation_id: str,
        text: str,
        request_id: str,
    ) -> TurnClaim:
        """Persist and claim exactly one user turn for a client request ID."""
        with self._session() as session:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                ).with_for_update()
            )
            if conversation is None:
                raise LookupError("Conversation not found")

            message = Message(
                conversation_id=conversation_id,
                position=self._next_position(session, conversation_id),
                role="user",
                content=text,
                client_request_id=request_id,
                generation_status="processing",
            )
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            try:
                session.commit()
                return TurnClaim(status="claimed", user_message=message)
            except IntegrityError:
                session.rollback()

            existing = session.scalar(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.client_request_id == request_id,
                )
            )
            if existing is None:
                raise RuntimeError("Could not resolve the duplicate request")
            if existing.content != text:
                raise ValueError("request_id was already used with different text")
            if existing.generation_status == "completed":
                assistant = session.scalar(
                    select(Message).where(Message.reply_to_message_id == existing.id)
                )
                return TurnClaim(status="completed", user_message=existing, assistant_message=assistant)

            if existing.generation_status == "failed":
                updated = session.execute(
                    update(Message)
                    .where(Message.id == existing.id, Message.generation_status == "failed")
                    .values(generation_status="processing")
                )
                session.commit()
                if updated.rowcount:
                    session.refresh(existing)
                    return TurnClaim(status="claimed", user_message=existing)
            return TurnClaim(status="in_progress", user_message=existing)

    def claim_voice_turn(self, user_id: str, conversation_id: str, request_id: str) -> TurnClaim:
        """Claim a voice upload before transcription so retries do not rerun models."""
        with self._session() as session:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                ).with_for_update()
            )
            if conversation is None:
                raise LookupError("Conversation not found")

            message = Message(
                conversation_id=conversation_id,
                position=self._next_position(session, conversation_id),
                role="user",
                content="",
                client_request_id=request_id,
                generation_status="processing",
            )
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            try:
                session.commit()
                return TurnClaim(status="claimed", user_message=message)
            except IntegrityError:
                session.rollback()

            existing = session.scalar(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.client_request_id == request_id,
                )
            )
            if existing is None:
                raise RuntimeError("Could not resolve the duplicate request")
            if existing.generation_status == "completed":
                assistant = session.scalar(select(Message).where(Message.reply_to_message_id == existing.id))
                return TurnClaim(status="completed", user_message=existing, assistant_message=assistant)
            if existing.generation_status == "failed":
                updated = session.execute(
                    update(Message)
                    .where(Message.id == existing.id, Message.generation_status == "failed")
                    .values(generation_status="processing")
                )
                session.commit()
                if updated.rowcount:
                    session.refresh(existing)
                    return TurnClaim(status="claimed", user_message=existing)
            return TurnClaim(status="in_progress", user_message=existing)

    def update_user_message_content(self, user_message_id: str, content: str) -> None:
        with self._session() as session:
            message = session.get(Message, user_message_id)
            if message is None:
                raise LookupError("User message not found")
            message.content = content
            session.commit()

    def recent_context(self, conversation_id: str, limit: int = 6) -> list[dict[str, str]]:
        with self._session() as session:
            messages = list(
                session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(desc(Message.position))
                    .limit(limit)
                )
            )
            messages.reverse()
            return [{"role": message.role, "content": message.content} for message in messages]

    @staticmethod
    def _memory_terms(text: str) -> set[str]:
        ignored = {"about", "again", "earlier", "from", "have", "here", "into", "just", "that", "this", "told", "what", "with", "would", "your"}
        terms = set(re.findall(r"[a-z0-9]+", text.casefold()))
        return {term[:-1] if len(term) > 4 and term.endswith("s") else term for term in terms if len(term) > 2 and term not in ignored}

    def previous_memory_candidates(
        self,
        user_id: str,
        conversation_id: str,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Fetch recent, user-owned prior messages for service-side relevance ranking."""
        with self._session() as session:
            candidates = list(
                session.execute(
                    select(Message.conversation_id, Message.position, Message.content, Message.created_at)
                    .join(Conversation, Message.conversation_id == Conversation.id)
                    .where(
                        Conversation.user_id == user_id,
                        Conversation.id != conversation_id,
                        Message.role == "user",
                        Message.content != "",
                    )
                    .order_by(desc(Message.created_at))
                    .limit(limit)
                )
            )
        return [
            {"conversation_id": item.conversation_id, "position": item.position, "content": item.content, "created_at": item.created_at}
            for item in candidates
        ]

    def surrounding_previous_context(
        self,
        user_id: str,
        anchors: list[dict[str, Any]],
        radius: int = 2,
        max_characters: int = 1100,
    ) -> list[dict[str, str]]:
        """Return bounded turns around selected prior messages, still scoped to one user."""
        selected: list[dict[str, str]] = []
        used_characters = 0
        seen: set[tuple[str, int]] = set()
        with self._session() as session:
            for anchor in anchors:
                messages = list(
                    session.execute(
                        select(Message.position, Message.role, Message.content)
                        .join(Conversation, Message.conversation_id == Conversation.id)
                        .where(
                            Conversation.user_id == user_id,
                            Conversation.id == anchor["conversation_id"],
                            Message.position.between(anchor["position"] - radius, anchor["position"] + radius),
                        )
                        .order_by(Message.position)
                    )
                )
                for message in messages:
                    key = (anchor["conversation_id"], message.position)
                    clipped = message.content[: max_characters - used_characters].strip()
                    if key in seen or not clipped:
                        continue
                    seen.add(key)
                    selected.append({"role": message.role, "content": clipped})
                    used_characters += len(clipped)
                    if used_characters >= max_characters:
                        return selected
        return selected

    def conversation_analytics(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        """Expose only already-persisted Streamlit-equivalent analytics values."""
        if self.get_conversation(user_id, conversation_id) is None:
            return None
        with self._session() as session:
            analyses = list(
                session.scalars(
                    select(MessageAnalysis)
                    .join(Message, MessageAnalysis.message_id == Message.id)
                    .where(Message.conversation_id == conversation_id, Message.role == "user")
                    .order_by(Message.position)
                )
            )
            if not analyses:
                return {
                    "latest": None,
                    "risk_history": [],
                    "latest_voice": None,
                }
            latest = analyses[-1]
            latest_voice = next((item.voice_metadata for item in reversed(analyses) if item.voice_metadata), None)
            return {
                "latest": {
                    "risk": {
                        "score": latest.risk_score,
                        "tier": latest.risk_tier,
                        "is_crisis": latest.is_crisis,
                    },
                    "emotion": {
                        "label": latest.emotion_label,
                        "score": latest.emotion_score,
                        "probabilities": latest.emotion_probabilities,
                    },
                    "rag": {"is_used": latest.rag_used, "sources": latest.rag_sources},
                },
                "risk_history": [float(item.risk_score) for item in analyses],
                "latest_voice": latest_voice,
            }

    def risk_history(self, conversation_id: str) -> list[float]:
        with self._session() as session:
            scores = session.scalars(
                select(MessageAnalysis.risk_score)
                .join(Message, MessageAnalysis.message_id == Message.id)
                .where(Message.conversation_id == conversation_id, Message.role == "user")
                .order_by(Message.position)
            )
            return [float(score) for score in scores]

    def complete_turn(self, user_message_id: str, result: TurnResult) -> Message:
        with self._session() as session:
            user_message = session.get(Message, user_message_id)
            if user_message is None:
                raise LookupError("User message not found")
            assistant = Message(
                conversation_id=user_message.conversation_id,
                position=user_message.position + 1,
                role="assistant",
                content=result.assistant_response,
                reply_to_message_id=user_message.id,
            )
            voice = result.voice_diagnostics or None
            stress_score = None
            if voice and isinstance(voice.get("acoustic_stress"), (int, float)):
                stress_score = float(voice["acoustic_stress"])
            analysis = MessageAnalysis(
                message_id=user_message.id,
                emotion_label=result.emotion.label,
                emotion_score=float(result.emotion.score),
                emotion_probabilities={
                    label: float(score) for label, score in result.emotion.all_emotions.items()
                },
                risk_score=float(result.assessment.score),
                risk_tier=result.assessment.tier,
                is_crisis=result.assessment.is_crisis,
                stress_score=stress_score,
                voice_metadata=voice,
                rag_used=result.rag_context.is_used,
                rag_sources=list(result.rag_context.sources),
            )
            user_message.generation_status = "completed"
            conversation = session.get(Conversation, user_message.conversation_id)
            if conversation is not None:
                conversation.updated_at = datetime.now(timezone.utc)
            session.add_all([assistant, analysis])
            session.commit()
            return assistant

    def mark_turn_failed(self, user_message_id: str) -> None:
        with self._session() as session:
            message = session.get(Message, user_message_id)
            if message is not None and message.generation_status == "processing":
                message.generation_status = "failed"
                session.commit()

    def completed_turn_payload(self, user_message_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            user_message = session.get(Message, user_message_id)
            if user_message is None:
                return None
            assistant = session.scalar(
                select(Message).where(Message.reply_to_message_id == user_message.id)
            )
            analysis = session.scalar(
                select(MessageAnalysis).where(MessageAnalysis.message_id == user_message.id)
            )
            if assistant is None or analysis is None:
                return None
            return self._payload(user_message, assistant, analysis)

    @staticmethod
    def _payload(user_message: Message, assistant: Message, analysis: MessageAnalysis) -> dict[str, Any]:
        return {
            "conversation_id": user_message.conversation_id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant.id,
            "assistant_response": assistant.content,
            "emotion": {
                "label": analysis.emotion_label,
                "score": analysis.emotion_score,
                "probabilities": analysis.emotion_probabilities,
            },
            "risk": {
                "score": analysis.risk_score,
                "tier": analysis.risk_tier,
                "is_crisis": analysis.is_crisis,
            },
            "voice": analysis.voice_metadata,
            "rag": {"is_used": analysis.rag_used, "sources": analysis.rag_sources},
        }


def conversation_to_dict(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def message_to_dict(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
        "generation_status": message.generation_status,
        "analysis": analysis_to_dict(message.analysis) if message.analysis is not None else None,
    }


def analysis_to_dict(analysis: MessageAnalysis) -> dict[str, Any]:
    return {
        "emotion": {
            "label": analysis.emotion_label,
            "score": analysis.emotion_score,
            "probabilities": analysis.emotion_probabilities,
        },
        "risk": {
            "score": analysis.risk_score,
            "tier": analysis.risk_tier,
            "is_crisis": analysis.is_crisis,
        },
        "stress_score": analysis.stress_score,
        "voice": analysis.voice_metadata,
        "rag": {"is_used": analysis.rag_used, "sources": analysis.rag_sources},
    }
