"""SQLAlchemy persistence models for Phase 2 conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="conversations")
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
