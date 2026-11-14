"""SQLAlchemy persistence models for Phase 2 conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from backend.core.database import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'counselor', 'admin')", name="ck_users_role"),
        Index("ix_users_role", "role"),
        Index("ix_users_department", "department"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Existing MannMitra users remain valid as students through the database
    # default; role authorization will be enforced by the API layer later.
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="student", server_default="student")
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", foreign_keys="Conversation.user_id"
    )
    check_ins: Mapped[list["CheckIn"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    counselor_cases: Mapped[list["SupportCase"]] = relationship(
        back_populates="counselor", foreign_keys="SupportCase.counselor_id"
    )
    assigned_cases: Mapped[list["SupportCase"]] = relationship(
        back_populates="student", foreign_keys="SupportCase.student_id"
    )
    counselor_conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="counselor", foreign_keys="Conversation.counselor_id"
    )
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="counselor", foreign_keys="Intervention.counselor_id")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="counselor", foreign_keys="FollowUp.counselor_id")

    @validates("role")
    def validate_role(self, _: str, value: str) -> str:
        normalized = value.strip().lower() if isinstance(value, str) else value
        if normalized not in {"student", "counselor", "admin"}:
            raise ValueError("role must be student, counselor, or admin")
        return normalized

    @validates("department")
    def validate_department(self, _: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("department must be between 1 and 128 characters")
        return normalized


class CheckIn(Base):
    """A private, user-owned wellbeing check-in."""

    __tablename__ = "check_ins"
    __table_args__ = (
        CheckConstraint("mood IN ('great', 'okay', 'low', 'stressed')", name="ck_check_ins_mood"),
        CheckConstraint("stress_level BETWEEN 0 AND 10", name="ck_check_ins_stress_level"),
        CheckConstraint("notes IS NULL OR length(notes) <= 2000", name="ck_check_ins_notes_length"),
        Index("ix_check_ins_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mood: Mapped[str] = mapped_column(String(16), nullable=False)
    stress_level: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="check_ins")

    @validates("mood")
    def validate_mood(self, _: str, value: str) -> str:
        normalized = value.strip().lower() if isinstance(value, str) else value
        if normalized not in {"great", "okay", "low", "stressed"}:
            raise ValueError("mood must be great, okay, low, or stressed")
        return normalized

    @validates("stress_level")
    def validate_stress_level(self, _: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
            raise ValueError("stress_level must be an integer between 0 and 10")
        return value

    @validates("notes")
    def validate_notes(self, _: str, value: str | None) -> str | None:
        if value is not None and len(value) > 2000:
            raise ValueError("notes must be 2000 characters or fewer")
        return value


class SupportCase(Base):
    """Minimal counselor-owned assignment record; no conversation content."""

    __tablename__ = "support_cases"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'closed')", name="ck_support_cases_status"),
        CheckConstraint("priority IN ('stable', 'moderate', 'priority')", name="ck_support_cases_priority"),
        Index("ix_support_cases_counselor_status", "counselor_id", "status"),
        Index("ix_support_cases_student", "student_id"),
        Index("ix_support_cases_follow_up", "counselor_id", "next_follow_up"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    counselor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="moderate", server_default="moderate")
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    next_follow_up: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    counselor: Mapped[User] = relationship(
        back_populates="counselor_cases", foreign_keys=[counselor_id]
    )
    student: Mapped[User] = relationship(
        back_populates="assigned_cases", foreign_keys=[student_id]
    )
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="case", cascade="all, delete-orphan")

    @validates("status")
    def validate_status(self, _: str, value: str) -> str:
        normalized = value.strip().lower() if isinstance(value, str) else value
        if normalized not in {"open", "in_progress", "closed"}:
            raise ValueError("status must be open, in_progress, or closed")
        return normalized

    @validates("priority")
    def validate_priority(self, _: str, value: str) -> str:
        normalized = value.strip().lower() if isinstance(value, str) else value
        if normalized not in {"stable", "moderate", "priority"}:
            raise ValueError("priority must be stable, moderate, or priority")
        return normalized

    @validates("summary")
    def validate_summary(self, _: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError("summary is required and must be 200 characters or fewer")
        return value.strip()

    @validates("details")
    def validate_details(self, _: str, value: str | None) -> str | None:
        if value is not None and len(value) > 4000:
            raise ValueError("details must be 4000 characters or fewer")
        return value


class Intervention(Base):
    """A counselor-owned, purpose-limited support action for an assigned case."""

    __tablename__ = "interventions"
    __table_args__ = (
        CheckConstraint("status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_interventions_status"),
        Index("ix_interventions_counselor_status", "counselor_id", "status"),
        Index("ix_interventions_case", "case_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id", ondelete="CASCADE"), nullable=False)
    counselor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned", server_default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    case: Mapped[SupportCase] = relationship(back_populates="interventions")
    counselor: Mapped[User] = relationship(back_populates="interventions", foreign_keys=[counselor_id])
    student: Mapped[User] = relationship(foreign_keys=[student_id])


class FollowUp(Base):
    """A scheduled counselor action linked to an assigned support case."""

    __tablename__ = "followups"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_followups_status"),
        Index("ix_followups_counselor_status_due", "counselor_id", "status", "due_at"),
        Index("ix_followups_case", "case_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id", ondelete="CASCADE"), nullable=False)
    counselor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled", server_default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    case: Mapped[SupportCase] = relationship(back_populates="followups")
    counselor: Mapped[User] = relationship(back_populates="followups", foreign_keys=[counselor_id])
    student: Mapped[User] = relationship(foreign_keys=[student_id])

class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("kind IN ('mannmitra', 'counselor')", name="ck_conversations_kind"),
        Index("ix_conversations_counselor_kind", "counselor_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    counselor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="mannmitra", server_default="mannmitra")
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="conversations", foreign_keys=[user_id])
    counselor: Mapped[User | None] = relationship(back_populates="counselor_conversations", foreign_keys=[counselor_id])
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_request_id", name="uq_message_request_per_conversation"),
        UniqueConstraint("conversation_id", "position", name="uq_message_position_per_conversation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_to_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id"), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    analysis: Mapped["MessageAnalysis | None"] = relationship(back_populates="message", uselist=False)


class MessageAnalysis(Base):
    __tablename__ = "message_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), unique=True, nullable=False)
    emotion_label: Mapped[str] = mapped_column(String(64), nullable=False)
    emotion_score: Mapped[float] = mapped_column(Float, nullable=False)
    emotion_probabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    is_crisis: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stress_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rag_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rag_sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    message: Mapped[Message] = relationship(back_populates="analysis")
