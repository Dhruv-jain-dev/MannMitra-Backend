"""FastAPI application and Supabase PostgreSQL-backed conversation routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from datetime import date, timedelta
import logging
import asyncio
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, select

from backend.core.config import Settings, get_settings
from backend.core.database import Database
from backend.core.auth import AuthService, AuthenticatedUser, get_current_user, get_verified_subject, require_active_user, require_admin, require_counselor, require_student
from backend.models import (
    AnonymousSupportAuditEvent,
    AnonymousSupportConversation,
    AnonymousSupportFollowUp,
    AnonymousSupportMessage,
    AnonymousSupportNote,
    CheckIn,
    Conversation,
    FollowUp,
    Intervention,
    Message,
    SupportCase,
    User,
)
from backend.repositories.conversations import ConversationRepository, conversation_to_dict, message_to_dict
from backend.services.mannmitra_service import GeminiGenerationError, MannMitraService
from backend.services.supabase_auth_admin import SupabaseAdminError, SupabaseAuthAdmin

logger = logging.getLogger("mannmitra.api")
_AUDIO_CONTENT_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3"}
_AUDIO_SUFFIXES = {".wav", ".mp3"}


def check_in_to_dict(check_in: CheckIn) -> dict[str, Any]:
    return {
        "id": check_in.id,
        "mood": check_in.mood,
        "stress_level": check_in.stress_level,
        "notes": check_in.notes,
        "created_at": check_in.created_at,
    }


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class DevelopmentTokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: str
    role: str
    must_change_password: bool = False


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str | None
    created_at: Any
    updated_at: Any


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: Any
    generation_status: str | None
    analysis: dict[str, Any] | None


class TextTurnRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=36)
    request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=10000)


class TextTurnResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    assistant_response: str
    emotion: dict[str, Any]
    risk: dict[str, Any]
    voice: dict[str, Any] | None
    rag: dict[str, Any]


class ConversationAnalyticsResponse(BaseModel):
    latest: dict[str, Any] | None
    risk_history: list[float]
    latest_voice: dict[str, Any] | None


class CheckInRequest(BaseModel):
    mood: Literal["great", "okay", "low", "stressed"]
    stress_level: int = Field(ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)


class CheckInResponse(BaseModel):
    id: str
    mood: str
    stress_level: int
    notes: str | None
    created_at: Any


class CheckInHistoryResponse(BaseModel):
    items: list[CheckInResponse]
    page: int
    page_size: int
    total: int


class InsightsResponse(BaseModel):
    check_in_count: int
    average_stress: float | None
    mood_distribution: dict[str, int]
    recent_trends: list[dict[str, Any]]


CaseStatus = Literal["open", "in_progress", "closed"]
CasePriority = Literal["stable", "moderate", "priority"]
InterventionStatus = Literal["planned", "in_progress", "completed", "cancelled"]
FollowUpStatus = Literal["scheduled", "completed", "cancelled"]


class CreateCaseRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)
    priority: CasePriority = "moderate"
    next_follow_up: datetime | None = None


class UpdateCaseRequest(BaseModel):
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)
    next_follow_up: datetime | None = None


class CaseResponse(BaseModel):
    id: str
    student_id: str
    status: str
    priority: str
    summary: str
    details: str | None
    next_follow_up: Any
    created_at: Any
    updated_at: Any
    latest_check_in: dict[str, Any] | None


class CaseDetailResponse(CaseResponse):
    check_ins: list[CheckInResponse]


class CounselorStudentResponse(BaseModel):
    id: str
    department: str | None
    created_at: Any
    latest_check_in: dict[str, Any] | None
    open_case_count: int


class CounselorStudentDetailResponse(CounselorStudentResponse):
    check_ins: list[CheckInResponse]
    cases: list[CaseResponse]


class CounselorProfileResponse(BaseModel):
    id: str
    role: str
    department: str | None
    created_at: Any


class CounselorDashboardResponse(BaseModel):
    assigned_cases: list[CaseResponse]
    open_case_count: int
    upcoming_followups: list[CaseResponse]


class AdminDashboardResponse(BaseModel):
    student_count: int
    active_student_count: int
    check_in_count: int
    average_stress: float | None
    mood_distribution: dict[str, int]
    wellbeing_distribution: dict[str, int]
    data_window_days: int


class DepartmentAggregateResponse(BaseModel):
    department: str
    student_count: int
    participating_students: int | None
    check_in_count: int | None
    average_stress: float | None
    mood_distribution: dict[str, int] | None
    wellbeing_distribution: dict[str, int] | None
    trend: list[dict[str, Any]] | None
    suppressed: bool


class AdminDepartmentsResponse(BaseModel):
    items: list[DepartmentAggregateResponse]
    minimum_group_size: int


class AdminAnalyticsResponse(AdminDashboardResponse):
    start_date: date | None
    end_date: date | None


AdminRole = Literal["student", "counselor", "admin"]
ProvisionedRole = Literal["student", "counselor", "admin"]


class AdminUserResponse(BaseModel):
    id: str
    role: AdminRole
    department: str | None
    created_at: Any
    must_change_password: bool = False


class AdminUsersResponse(BaseModel):
    items: list[AdminUserResponse]
    page: int
    page_size: int
    total: int


class ProvisionUserRequest(BaseModel):
    """Provision an Auth identity and its matching application profile."""

    id: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    role: ProvisionedRole
    department: str | None = Field(default=None, min_length=1, max_length=128)
    method: Literal["invite", "temporary_password"] = "invite"
    password: str | None = Field(default=None, max_length=128)
    password_confirmation: str | None = Field(default=None, max_length=128)


class RoleUpdateRequest(BaseModel):
    role: AdminRole


class AssignmentRequest(BaseModel):
    counselor_id: str = Field(min_length=1, max_length=128)


class AdminCaseResponse(CaseResponse):
    counselor_id: str


class AdminCasesResponse(BaseModel):
    items: list[AdminCaseResponse]
    page: int
    page_size: int
    total: int


class AdminInterventionsResponse(BaseModel):
    items: list[InterventionResponse]
    page: int
    page_size: int
    total: int


class AdminFollowUpsResponse(BaseModel):
    items: list[FollowUpResponse]
    page: int
    page_size: int
    total: int


class CreateInterventionRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)


class UpdateInterventionRequest(BaseModel):
    status: InterventionStatus


class InterventionResponse(BaseModel):
    id: str
    case_id: str
    student_id: str
    title: str
    details: str | None
    status: str
    created_at: Any
    updated_at: Any


class CreateFollowUpRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    notes: str | None = Field(default=None, max_length=2000)


class UpdateFollowUpRequest(BaseModel):
    status: FollowUpStatus
    due_at: datetime | None = None


class FollowUpResponse(BaseModel):
    id: str
    case_id: str
    student_id: str
    title: str
    due_at: Any
    notes: str | None
    status: str
    created_at: Any
    updated_at: Any


class CounselorMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    conversation_id: str | None = Field(default=None, max_length=36)
    counselor_id: str | None = Field(default=None, max_length=128)
    student_id: str | None = Field(default=None, max_length=128)


class CounselorMessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_role: str
    content: str
    created_at: Any
    read_at: Any


class CounselorThreadResponse(BaseModel):
    id: str
    student_id: str
    counselor_id: str
    messages: list[CounselorMessageResponse]
    unread_count: int
    updated_at: Any


class CounselorThreadsResponse(BaseModel):
    items: list[CounselorThreadResponse]


class CounselorContactResponse(BaseModel):
    id: str
    role: str


class ReadMessagesResponse(BaseModel):
    conversation_id: str
    marked_read: int


AnonymousCategory = Literal["emotional_support", "academic", "safety", "other"]
AnonymousUrgency = Literal["stable", "moderate", "urgent"]
AnonymousStatus = Literal["pending", "active", "closed"]
AnonymousFollowUpStatus = Literal["scheduled", "completed", "cancelled"]


class AnonymousConversationCreateRequest(BaseModel):
    category: AnonymousCategory
    urgency: AnonymousUrgency = "moderate"
    consent: bool


class AnonymousMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class AnonymousStatusRequest(BaseModel):
    status: AnonymousStatus


class AnonymousNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AnonymousFollowUpRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime


class AnonymousConversationSummary(BaseModel):
    id: str
    anonymous_alias: str
    category: str
    urgency: str
    status: str
    created_at: Any
    updated_at: Any
    closed_at: Any


class AnonymousMessageResponse(BaseModel):
    id: str
    sender_role: Literal["student", "counselor"]
    content: str
    created_at: Any
    read_at: Any


class AnonymousConversationResponse(AnonymousConversationSummary):
    messages: list[AnonymousMessageResponse]
    followups: list[AnonymousFollowUpResponse] = Field(default_factory=list)


class AnonymousNoteResponse(BaseModel):
    id: str
    content: str
    created_at: Any
    updated_at: Any


class AnonymousFollowUpResponse(BaseModel):
    id: str
    title: str
    due_at: Any
    status: str


class AnonymousCounselorConversationResponse(AnonymousConversationResponse):
    notes: list[AnonymousNoteResponse]
    followups: list[AnonymousFollowUpResponse]


def support_case_to_dict(case: SupportCase, latest_check_in: CheckIn | None = None) -> dict[str, Any]:
    return {
        "id": case.id,
        "student_id": case.student_id,
        "status": case.status,
        "priority": case.priority,
        "summary": case.summary,
        "details": case.details,
        "next_follow_up": case.next_follow_up,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "latest_check_in": check_in_to_dict(latest_check_in) if latest_check_in is not None else None,
    }


def admin_case_to_dict(case: SupportCase, latest_check_in: CheckIn | None = None) -> dict[str, Any]:
    return {**support_case_to_dict(case, latest_check_in), "counselor_id": case.counselor_id}


def intervention_to_dict(item: Intervention) -> dict[str, Any]:
    return {"id": item.id, "case_id": item.case_id, "student_id": item.student_id, "title": item.title,
            "details": item.details, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at}


def followup_to_dict(item: FollowUp) -> dict[str, Any]:
    return {"id": item.id, "case_id": item.case_id, "student_id": item.student_id, "title": item.title,
            "due_at": item.due_at, "notes": item.notes, "status": item.status,
            "created_at": item.created_at, "updated_at": item.updated_at}


def _analytics_window(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date cannot be after end_date")
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc) if start_date else None
    end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) if end_date else None
    return start, end


def _wellbeing_bucket(stress: int) -> str:
    return "stable" if stress <= 3 else "moderate" if stress <= 6 else "priority"


def _aggregate_checkins(session, start: datetime | None = None, end: datetime | None = None) -> dict[str, Any]:
    query = select(CheckIn.mood, CheckIn.stress_level).join(User, User.id == CheckIn.user_id).where(User.role == "student")
    if start is not None:
        query = query.where(CheckIn.created_at >= start)
    if end is not None:
        query = query.where(CheckIn.created_at < end)
    rows = list(session.execute(query))
    moods = {key: 0 for key in ("great", "okay", "low", "stressed")}
    wellbeing = {key: 0 for key in ("stable", "moderate", "priority")}
    for mood, stress in rows:
        moods[mood] = moods.get(mood, 0) + 1
        wellbeing[_wellbeing_bucket(stress)] += 1
    return {"check_in_count": len(rows), "average_stress": round(sum(row.stress_level for row in rows) / len(rows), 2) if rows else None,
            "mood_distribution": moods, "wellbeing_distribution": wellbeing}


def _department_aggregates(session, start: datetime | None, end: datetime | None, minimum_group_size: int = 5) -> list[dict[str, Any]]:
    students = list(session.scalars(select(User).where(User.role == "student")))
    grouped: dict[str, dict[str, Any]] = {}
    for student in students:
        name = student.department or "Unspecified"
        grouped.setdefault(name, {"students": set(), "checkins": []})["students"].add(student.id)
    query = select(CheckIn.user_id, CheckIn.mood, CheckIn.stress_level, CheckIn.created_at).where(CheckIn.user_id.in_([student.id for student in students] or ["__none__"]))
    if start is not None:
        query = query.where(CheckIn.created_at >= start)
    if end is not None:
        query = query.where(CheckIn.created_at < end)
    department_by_student = {student.id: student.department or "Unspecified" for student in students}
    for user_id, mood, stress, created_at in session.execute(query):
        grouped[department_by_student[user_id]]["checkins"].append((user_id, mood, stress, created_at))
    result = []
    for name in sorted(grouped):
        data = grouped[name]; student_count = len(data["students"]); checkins = data["checkins"]
        if student_count < minimum_group_size:
            result.append({"department": name, "student_count": student_count, "participating_students": None, "check_in_count": None,
                           "average_stress": None, "mood_distribution": None, "wellbeing_distribution": None, "trend": None, "suppressed": True})
            continue
        moods = {key: 0 for key in ("great", "okay", "low", "stressed")}; wellbeing = {key: 0 for key in ("stable", "moderate", "priority")}
        for _, mood, stress, _ in checkins:
            moods[mood] += 1; wellbeing[_wellbeing_bucket(stress)] += 1
        by_day: dict[str, list[int]] = {}
        for _, _, stress, created_at in checkins:
            by_day.setdefault(created_at.date().isoformat(), []).append(stress)
        trend = [{"date": day, "check_in_count": len(values), "average_stress": round(sum(values) / len(values), 2)} for day, values in sorted(by_day.items())]
        result.append({"department": name, "student_count": student_count, "participating_students": len({student_id for student_id, _, _, _ in checkins}),
                       "check_in_count": len(checkins), "average_stress": round(sum(stress for _, _, stress, _ in checkins) / len(checkins), 2) if checkins else None,
                       "mood_distribution": moods, "wellbeing_distribution": wellbeing, "trend": trend, "suppressed": False})
    return result


def latest_check_in_for(session, student_id: str) -> CheckIn | None:
    return session.scalar(
        select(CheckIn)
        .where(CheckIn.user_id == student_id)
        .order_by(CheckIn.created_at.desc())
        .limit(1)
    )


def counselor_message_to_dict(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_role": message.role,
        "content": message.content,
        "created_at": message.created_at,
        "read_at": message.read_at,
    }


def counselor_thread_to_dict(session, conversation: Conversation, viewer_role: str) -> dict[str, Any]:
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.position)
            .limit(200)
        )
    )
    unread_count = sum(1 for message in messages if message.role != viewer_role and message.read_at is None)
    return {
        "id": conversation.id,
        "student_id": conversation.user_id,
        "counselor_id": conversation.counselor_id,
        "messages": [counselor_message_to_dict(message) for message in messages],
        "unread_count": unread_count,
        "updated_at": conversation.updated_at,
    }


def _assert_message_role(user: AuthenticatedUser) -> None:
    if user.role not in {"student", "counselor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student or counselor role is required")


def _assert_assigned(session, student_id: str, counselor_id: str) -> None:
    assignment = session.scalar(
        select(SupportCase.id).where(
            SupportCase.student_id == student_id,
            SupportCase.counselor_id == counselor_id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student-counselor assignment is required")


def _find_assigned_thread(session, student_id: str, counselor_id: str) -> Conversation | None:
    _assert_assigned(session, student_id, counselor_id)
    return session.scalar(
        select(Conversation).where(
            Conversation.user_id == student_id,
            Conversation.counselor_id == counselor_id,
            Conversation.kind == "counselor",
        )
    )


def _counselor_case(session, case_id: str, counselor_id: str) -> SupportCase:
    case = session.scalar(select(SupportCase).where(SupportCase.id == case_id, SupportCase.counselor_id == counselor_id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _anonymous_message_dict(message: AnonymousSupportMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "sender_role": message.sender_role,
        "content": message.content,
        "created_at": message.created_at,
        "read_at": message.read_at,
    }


def _anonymous_summary(conversation: AnonymousSupportConversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "anonymous_alias": conversation.anonymous_alias,
        "category": conversation.category,
        "urgency": conversation.urgency,
        "status": conversation.status,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "closed_at": conversation.closed_at,
    }


def _anonymous_response(session, conversation: AnonymousSupportConversation, include_private: bool = False) -> dict[str, Any]:
    result = {
        **_anonymous_summary(conversation),
        "messages": [
            _anonymous_message_dict(item)
            for item in session.scalars(
                select(AnonymousSupportMessage)
                .where(AnonymousSupportMessage.conversation_id == conversation.id)
                .order_by(AnonymousSupportMessage.position)
                .limit(500)
            )
        ],
        "followups": [
            {"id": item.id, "title": item.title, "due_at": item.due_at, "status": item.status}
            for item in session.scalars(
                select(AnonymousSupportFollowUp)
                .where(AnonymousSupportFollowUp.conversation_id == conversation.id)
                .order_by(AnonymousSupportFollowUp.due_at.asc())
            )
        ],
    }
    if include_private:
        result["notes"] = [
            {"id": item.id, "content": item.content, "created_at": item.created_at, "updated_at": item.updated_at}
            for item in session.scalars(
                select(AnonymousSupportNote)
                .where(AnonymousSupportNote.conversation_id == conversation.id)
                .order_by(AnonymousSupportNote.created_at.desc())
            )
        ]
        result["followups"] = [
            {"id": item.id, "title": item.title, "due_at": item.due_at, "status": item.status}
            for item in session.scalars(
                select(AnonymousSupportFollowUp)
                .where(AnonymousSupportFollowUp.conversation_id == conversation.id)
                .order_by(AnonymousSupportFollowUp.due_at.asc())
            )
        ]
    return result


def _new_anonymous_alias(session) -> str:
    for _ in range(10):
        candidate = f"Mitra-{secrets.token_hex(5).upper()}"
        if session.scalar(select(AnonymousSupportConversation.id).where(AnonymousSupportConversation.anonymous_alias == candidate)) is None:
            return candidate
    raise HTTPException(status_code=503, detail="Unable to allocate a private support alias")


def _anonymous_student_conversation(session, conversation_id: str, student_id: str) -> AnonymousSupportConversation:
    conversation = session.scalar(
        select(AnonymousSupportConversation).where(
            AnonymousSupportConversation.id == conversation_id,
            AnonymousSupportConversation.student_user_id == student_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Anonymous support conversation not found")
    return conversation


def _anonymous_counselor_conversation(session, conversation_id: str, counselor_id: str) -> AnonymousSupportConversation:
    conversation = session.scalar(
        select(AnonymousSupportConversation).where(
            AnonymousSupportConversation.id == conversation_id,
            AnonymousSupportConversation.assigned_counselor_id == counselor_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Anonymous support conversation not found")
    return conversation


def _anonymous_counselor_viewable_conversation(session, conversation_id: str, counselor_id: str) -> AnonymousSupportConversation:
    conversation = session.scalar(
        select(AnonymousSupportConversation).where(
            AnonymousSupportConversation.id == conversation_id,
            (AnonymousSupportConversation.assigned_counselor_id == counselor_id)
            | ((AnonymousSupportConversation.assigned_counselor_id.is_(None)) & (AnonymousSupportConversation.status == "pending")),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Anonymous support conversation not found")
    return conversation


def create_app(
    app_settings: Settings | None = None,
    service_factory: Callable[[], MannMitraService] = MannMitraService,
) -> FastAPI:
    """Build an app with one service and one PostgreSQL engine per process."""
    resolved_settings = app_settings or get_settings()
    database = Database(resolved_settings.database_url)
    repository = ConversationRepository(database.session_factory)
    environment_name = resolved_settings.environment.lower()
    supabase_issuer = resolved_settings.supabase_jwt_issuer or (
        f"{resolved_settings.supabase_url.rstrip('/')}/auth/v1" if resolved_settings.supabase_url else resolved_settings.auth_jwt_issuer
    )
    auth_service = AuthService(
        resolved_settings.auth_jwt_secret,
        supabase_issuer,
        supabase_url=resolved_settings.supabase_url,
        jwks_url=resolved_settings.supabase_jwks_url,
        audience=resolved_settings.supabase_jwt_audience,
        supabase_jwt_secret=resolved_settings.supabase_jwt_secret,
        allow_legacy_tokens=(environment_name in {"development", "dev", "test"} and not resolved_settings.supabase_url),
    )
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Shared PostgreSQL databases must be initialized only through the
        # reviewed Alembic chain. Keep metadata creation available for the
        # isolated SQLite test fixtures without allowing API startup to
        # bypass migrations in Supabase.
        if database.engine.url.get_backend_name() == "sqlite":
            database.create_all()
        app.state.database = database
        app.state.conversation_repository = repository
        app.state.mannmitra_service = service_factory()
        app.state.mannmitra_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mannmitra-ai")
        app.state.auth_service = auth_service
        app.state.environment = environment_name
        try:
            yield
        finally:
            app.state.mannmitra_executor.shutdown(wait=True, cancel_futures=True)
            database.dispose()

    api = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    if resolved_settings.environment.lower() in {"development", "dev", "test"}:
        api.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:5317",
                "http://localhost:5318",
                "http://localhost:5319",
                "http://127.0.0.1:5317",
                "http://127.0.0.1:5318",
                "http://127.0.0.1:5319",
            ],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @api.middleware("http")
    async def log_text_turn_latency(request: Request, call_next):
        """Log end-to-end timings for completed text turns without changing responses."""
        if request.url.path != "/api/mannmitra/text" or request.method != "POST":
            return await call_next(request)

        request.state.mannmitra_request_started = time.perf_counter()
        response = await call_next(request)
        timings = getattr(request.state, "mannmitra_latency_ms", None)
        if timings is not None:
            timings["total_request_ms"] = (time.perf_counter() - request.state.mannmitra_request_started) * 1000
            logger.info(
                "text_turn_latency request_id=%s request_parsing_ms=%.2f "
                "text_analysis_ms=%.2f context_risk_history_ms=%.2f "
                "rag_retrieval_ms=%.2f gemini_generation_ms=%.2f "
                "response_database_persistence_ms=%.2f total_request_ms=%.2f",
                timings["request_id"],
                timings["request_parsing_ms"],
                timings["text_analysis_ms"],
                timings["context_risk_history_ms"],
                timings["rag_retrieval_ms"],
                timings["gemini_generation_ms"],
                timings["response_database_persistence_ms"],
                timings["total_request_ms"],
            )
        return response

    @api.exception_handler(SQLAlchemyError)
    async def database_error_handler(_: Request, error: SQLAlchemyError) -> JSONResponse:
        logger.error("Database operation failed: %s", error)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "Storage is temporarily unavailable"})

    @api.get("/health")
    def health() -> dict[str, str]:
        """Health-only endpoint: no generation or ML inference occurs here."""
        return {"status": "ok", "service": "mannmitra-backend"}

    @api.get("/api/admin/dashboard", response_model=AdminDashboardResponse)
    def admin_dashboard(request: Request, user: AuthenticatedUser = Depends(require_admin)) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            now = datetime.now(timezone.utc)
            student_count = session.scalar(select(func.count(User.id)).where(User.role == "student")) or 0
            active_student_count = session.scalar(select(func.count(func.distinct(CheckIn.user_id))).join(User, User.id == CheckIn.user_id).where(User.role == "student", CheckIn.created_at >= now - timedelta(days=30))) or 0
            aggregate = _aggregate_checkins(session)
            return {"student_count": int(student_count), "active_student_count": int(active_student_count), "data_window_days": 30, **aggregate}

    @api.get("/api/admin/departments", response_model=AdminDepartmentsResponse)
    def admin_departments(request: Request, start_date: date | None = Query(default=None), end_date: date | None = Query(default=None), user: AuthenticatedUser = Depends(require_admin)) -> dict[str, Any]:
        start, end = _analytics_window(start_date, end_date)
        with request.app.state.database.session_factory() as session:
            return {"items": _department_aggregates(session, start, end), "minimum_group_size": 5}

    @api.get("/api/admin/analytics", response_model=AdminAnalyticsResponse)
    def admin_analytics(request: Request, start_date: date | None = Query(default=None), end_date: date | None = Query(default=None), user: AuthenticatedUser = Depends(require_admin)) -> dict[str, Any]:
        start, end = _analytics_window(start_date, end_date)
        with request.app.state.database.session_factory() as session:
            aggregate = _aggregate_checkins(session, start, end)
            student_count = session.scalar(select(func.count(User.id)).where(User.role == "student")) or 0
            active_query = select(func.count(func.distinct(CheckIn.user_id))).join(User, User.id == CheckIn.user_id).where(User.role == "student")
            if start is not None:
                active_query = active_query.where(CheckIn.created_at >= start)
            if end is not None:
                active_query = active_query.where(CheckIn.created_at < end)
            active_student_count = session.scalar(active_query) or 0
            return {"student_count": int(student_count), "active_student_count": int(active_student_count), "data_window_days": (end_date - start_date).days + 1 if start_date and end_date else 0, "start_date": start_date, "end_date": end_date, **aggregate}

    @api.get("/api/admin/users", response_model=AdminUsersResponse)
    def admin_users(
        request: Request,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=50, ge=1, le=100),
        role: AdminRole | None = Query(default=None),
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        """List application profiles; authentication secrets are never returned."""
        with request.app.state.database.session_factory() as session:
            base = select(User)
            count_query = select(func.count(User.id))
            if role is not None:
                base = base.where(User.role == role)
                count_query = count_query.where(User.role == role)
            total = int(session.scalar(count_query) or 0)
            users = list(session.scalars(base.order_by(User.created_at.desc(), User.id).offset((page - 1) * page_size).limit(page_size)))
            return {
                "items": [
                    {"id": item.id, "role": item.role, "department": item.department, "created_at": item.created_at, "must_change_password": item.must_change_password}
                    for item in users
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
            }

    @api.get("/api/admin/users/{user_id}", response_model=AdminUserResponse)
    def admin_user_detail(
        user_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            target = session.get(User, user_id)
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            return {"id": target.id, "role": target.role, "department": target.department, "created_at": target.created_at, "must_change_password": target.must_change_password}

    @api.post("/api/admin/users/provision", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
    def provision_admin_user(
        payload: ProvisionUserRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        """Create only an app profile for a separately provisioned IdP identity."""
        if payload.id == user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An administrator cannot provision their own role")
        normalized_email = payload.email.strip().lower() if payload.email else None
        if normalized_email is not None and ("@" not in normalized_email or any(character.isspace() for character in normalized_email)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid email address is required")
        normalized_department = payload.department.strip() if payload.department is not None else None
        if payload.department is not None and not normalized_department:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Department cannot be blank")
        if payload.method == "temporary_password":
            password = payload.password or ""
            if password != (payload.password_confirmation or ""):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Temporary password and confirmation do not match")
            if len(password) < 12 or not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password) or not re.search(r"[^A-Za-z0-9]", password):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Temporary password must be at least 12 characters and include uppercase, lowercase, number and symbol")
        elif payload.password or payload.password_confirmation:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords are only accepted for temporary-password provisioning")
        identity_id = payload.id
        created_identity = False
        local_identity_registry = getattr(request.app.state, "local_test_identity_registry", None)
        local_identity_created = False
        must_change_password = payload.method == "temporary_password"
        if environment_name in {"development", "dev", "test"} and local_identity_registry is not None:
            # This branch exists only on the explicitly isolated local HTTP
            # harness. Production never receives this registry and therefore
            # cannot accept synthetic identities as Supabase identities.
            if identity_id:
                local_identity = local_identity_registry.get(identity_id)
                if local_identity is None:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Local test identity is not registered")
                if normalized_email and local_identity["email"] != normalized_email:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email and local identity refer to different accounts")
            else:
                if not normalized_email:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required for local test provisioning")
                if any(item["email"] == normalized_email for item in local_identity_registry.values()):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A local test identity already exists for this email")
                identity_id = str(uuid4())
                local_identity_registry[identity_id] = {"email": normalized_email}
                local_identity_created = True
                created_identity = True
        elif resolved_settings.supabase_url or resolved_settings.supabase_service_role_key:
            if not resolved_settings.supabase_url or not resolved_settings.supabase_service_role_key:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Supabase Auth provisioning is not configured")
            if not normalized_email:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required for Supabase Auth provisioning")
            auth_admin = SupabaseAuthAdmin(resolved_settings.supabase_url, resolved_settings.supabase_service_role_key)
            try:
                existing_identity = auth_admin.find_user_by_email(normalized_email)
                if existing_identity is not None:
                    existing_id = existing_identity.get("id")
                    if not isinstance(existing_id, str):
                        raise SupabaseAdminError("Supabase Auth returned an invalid existing identity")
                    if payload.method == "temporary_password":
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Supabase Auth identity already exists for this email; no password was changed")
                    if identity_id is None:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Supabase Auth identity already exists for this email; provide its existing Auth UUID")
                    if existing_id != identity_id:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email and Auth UUID refer to different identities")
                    identity = existing_identity
                else:
                    if payload.method == "temporary_password":
                        identity = auth_admin.create_user(normalized_email, payload.password or "")
                    else:
                        identity = auth_admin.invite_user(normalized_email)
                    created_identity = True
            except SupabaseAdminError as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
            invited_id = identity.get("id")
            if not isinstance(invited_id, str) or (identity_id is not None and invited_id != identity_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Supabase identity did not match the requested profile")
            identity_id = invited_id
        elif environment_name not in {"development", "dev", "test"}:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Supabase Auth provisioning is not configured")
        if not identity_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A verified identity id is required")
        try:
            with request.app.state.database.session_factory() as session:
                with session.begin():
                    target = session.get(User, identity_id)
                    if target is not None:
                        if target.role != payload.role:
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User profile already exists with a different role")
                        result = {"id": target.id, "role": target.role, "department": target.department, "created_at": target.created_at, "must_change_password": target.must_change_password}
                    else:
                        target = User(id=identity_id, role=payload.role, department=normalized_department, must_change_password=must_change_password,
                                      password_change_requested_at=datetime.now(timezone.utc) if must_change_password else None)
                        session.add(target)
                        session.flush()
                        result = {"id": target.id, "role": target.role, "department": target.department, "created_at": target.created_at, "must_change_password": target.must_change_password}
                return result
        except SQLAlchemyError as exc:
            logger.error("auth_profile_persistence_failed identity=%s", identity_id[:8] + "..." )
            if local_identity_created:
                local_identity_registry.pop(identity_id, None)
            if created_identity:
                if local_identity_created:
                    logger.error("local_identity_compensation_failed identity=%s", identity_id[:8] + "...")
                else:
                    try:
                        auth_admin.delete_user(identity_id)
                    except SupabaseAdminError:
                        logger.error("auth_profile_compensation_failed identity=%s", identity_id[:8] + "...")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth identity was verified but the application profile could not be saved; retry with the existing Auth UUID") from exc

    @api.patch("/api/admin/users/{user_id}/role", response_model=AdminUserResponse)
    def update_admin_user_role(
        user_id: str,
        payload: RoleUpdateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        if user_id == user.id and payload.role != "admin":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An administrator cannot demote themselves")
        with request.app.state.database.session_factory() as session:
            target = session.get(User, user_id)
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            target.role = payload.role
            session.commit()
            session.refresh(target)
            return {"id": target.id, "role": target.role, "department": target.department, "created_at": target.created_at, "must_change_password": target.must_change_password}

    @api.get("/api/admin/cases", response_model=AdminCasesResponse)
    def admin_cases(
        request: Request,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=50, ge=1, le=100),
        case_status: CaseStatus | None = Query(default=None, alias="status"),
        counselor_id: str | None = Query(default=None, max_length=128),
        student_id: str | None = Query(default=None, max_length=128),
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            filters = []
            if case_status is not None:
                filters.append(SupportCase.status == case_status)
            if counselor_id is not None:
                filters.append(SupportCase.counselor_id == counselor_id)
            if student_id is not None:
                filters.append(SupportCase.student_id == student_id)
            total = int(session.scalar(select(func.count(SupportCase.id)).where(*filters)) or 0)
            cases = list(session.scalars(select(SupportCase).where(*filters).order_by(SupportCase.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)))
            return {"items": [admin_case_to_dict(item, latest_check_in_for(session, item.student_id)) for item in cases], "page": page, "page_size": page_size, "total": total}

    @api.patch("/api/admin/cases/{case_id}/assignment", response_model=AdminCaseResponse)
    def assign_admin_case(
        case_id: str,
        payload: AssignmentRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            case = session.get(SupportCase, case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            counselor = session.get(User, payload.counselor_id)
            if counselor is None or counselor.role != "counselor":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A counselor profile is required")
            case.counselor_id = counselor.id
            case.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(case)
            return admin_case_to_dict(case, latest_check_in_for(session, case.student_id))

    @api.get("/api/admin/interventions", response_model=AdminInterventionsResponse)
    def admin_interventions(
        request: Request,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=50, ge=1, le=100),
        counselor_id: str | None = Query(default=None, max_length=128),
        student_id: str | None = Query(default=None, max_length=128),
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            filters = []
            if counselor_id is not None:
                filters.append(Intervention.counselor_id == counselor_id)
            if student_id is not None:
                filters.append(Intervention.student_id == student_id)
            total = int(session.scalar(select(func.count(Intervention.id)).where(*filters)) or 0)
            items = list(session.scalars(select(Intervention).where(*filters).order_by(Intervention.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)))
            return {"items": [intervention_to_dict(item) for item in items], "page": page, "page_size": page_size, "total": total}

    @api.get("/api/admin/followups", response_model=AdminFollowUpsResponse)
    def admin_followups(
        request: Request,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=50, ge=1, le=100),
        followup_status: FollowUpStatus | None = Query(default=None, alias="status"),
        counselor_id: str | None = Query(default=None, max_length=128),
        student_id: str | None = Query(default=None, max_length=128),
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            filters = []
            if followup_status is not None:
                filters.append(FollowUp.status == followup_status)
            if counselor_id is not None:
                filters.append(FollowUp.counselor_id == counselor_id)
            if student_id is not None:
                filters.append(FollowUp.student_id == student_id)
            total = int(session.scalar(select(func.count(FollowUp.id)).where(*filters)) or 0)
            items = list(session.scalars(select(FollowUp).where(*filters).order_by(FollowUp.due_at.asc()).offset((page - 1) * page_size).limit(page_size)))
            return {"items": [followup_to_dict(item) for item in items], "page": page, "page_size": page_size, "total": total}

    @api.post("/api/auth/dev-token", response_model=TokenResponse)
    def create_development_token(payload: DevelopmentTokenRequest) -> dict[str, str]:
        """Issue a local-only JWT until a production identity provider is connected."""
        if resolved_settings.environment.lower() not in {"development", "dev", "test"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return {"access_token": auth_service.create_access_token(payload.subject), "token_type": "bearer"}

    @api.get("/api/auth/me", response_model=CurrentUserResponse)
    def current_user(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
        if user.role not in {"student", "counselor", "admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User role is invalid")
        return {"id": user.id, "role": user.role, "must_change_password": user.must_change_password}

    @api.post("/api/auth/password-changed", response_model=CurrentUserResponse)
    def confirm_password_changed(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            profile = session.get(User, user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application profile was not found")
            if not profile.must_change_password:
                return {"id": profile.id, "role": profile.role, "must_change_password": False}
            if not resolved_settings.supabase_url or not resolved_settings.supabase_service_role_key or not profile.password_change_requested_at:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Password change verification is not configured")
            try:
                identity = SupabaseAuthAdmin(resolved_settings.supabase_url, resolved_settings.supabase_service_role_key).get_user(user.id)
                updated_at = identity.get("updated_at")
                updated_at_value = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if isinstance(updated_at, str) else None
            except (SupabaseAdminError, ValueError, AttributeError) as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Password change could not be verified") from exc
            requested_at = profile.password_change_requested_at
            if requested_at.tzinfo is None:
                requested_at = requested_at.replace(tzinfo=timezone.utc)
            if updated_at_value is None or updated_at_value <= requested_at:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Set a new password before continuing")
            profile.must_change_password = False
            profile.password_change_requested_at = None
            session.commit()
            return {"id": profile.id, "role": profile.role, "must_change_password": False}

    @api.post("/api/auth/profile", response_model=CurrentUserResponse, status_code=status.HTTP_201_CREATED)
    def synchronize_student_profile(
        request: Request,
        subject: AuthenticatedUser = Depends(get_verified_subject),
    ) -> dict[str, str]:
        """Create the default student profile for a verified Supabase identity."""
        with request.app.state.database.session_factory() as session:
            existing = session.get(User, subject.id)
            if existing is not None:
                return {"id": existing.id, "role": existing.role}
            profile = User(id=subject.id, role="student")
            session.add(profile)
            session.commit()
            return {"id": profile.id, "role": profile.role}

    @api.post("/api/wellbeing/check-in", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
    def create_check_in(
        payload: CheckInRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            check_in = CheckIn(
                user_id=user.id,
                mood=payload.mood,
                stress_level=payload.stress_level,
                notes=payload.notes,
            )
            session.add(check_in)
            session.commit()
            session.refresh(check_in)
            return check_in_to_dict(check_in)

    @api.get("/api/wellbeing/check-ins", response_model=CheckInHistoryResponse)
    def list_check_ins(
        request: Request,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        from sqlalchemy import func, select

        with request.app.state.database.session_factory() as session:
            total = session.scalar(
                select(func.count(CheckIn.id)).where(CheckIn.user_id == user.id)
            ) or 0
            items = list(
                session.scalars(
                    select(CheckIn)
                    .where(CheckIn.user_id == user.id)
                    .order_by(CheckIn.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return {
                "items": [check_in_to_dict(item) for item in items],
                "page": page,
                "page_size": page_size,
                "total": int(total),
            }

    @api.get("/api/wellbeing/insights", response_model=InsightsResponse)
    def get_wellbeing_insights(
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        from sqlalchemy import func, select

        with request.app.state.database.session_factory() as session:
            count, average_stress = session.execute(
                select(func.count(CheckIn.id), func.avg(CheckIn.stress_level)).where(CheckIn.user_id == user.id)
            ).one()
            mood_rows = session.execute(
                select(CheckIn.mood, func.count(CheckIn.id))
                .where(CheckIn.user_id == user.id)
                .group_by(CheckIn.mood)
            )
            mood_distribution = {mood: int(total) for mood, total in mood_rows}
            recent = list(
                session.scalars(
                    select(CheckIn)
                    .where(CheckIn.user_id == user.id)
                    .order_by(CheckIn.created_at.desc())
                    .limit(7)
                )
            )
            recent.reverse()
            return {
                "check_in_count": int(count or 0),
                "average_stress": round(float(average_stress), 2) if average_stress is not None else None,
                "mood_distribution": mood_distribution,
                "recent_trends": [
                    {
                        "date": item.created_at,
                        "mood": item.mood,
                        "stress_level": item.stress_level,
                    }
                    for item in recent
                ],
            }

    @api.get("/api/counselor/profile", response_model=CounselorProfileResponse)
    def counselor_profile(
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            profile = session.get(User, user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counselor profile not found")
            return {"id": profile.id, "role": profile.role, "department": profile.department, "created_at": profile.created_at}

    @api.get("/api/counselor/students", response_model=list[CounselorStudentResponse])
    def list_counselor_students(
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> list[dict[str, Any]]:
        with request.app.state.database.session_factory() as session:
            students = list(
                session.scalars(
                    select(User)
                    .join(SupportCase, SupportCase.student_id == User.id)
                    .where(SupportCase.counselor_id == user.id, User.role == "student")
                    .distinct()
                    .order_by(User.created_at.desc())
                )
            )
            result = []
            for student in students:
                latest_check_in = latest_check_in_for(session, student.id)
                result.append({
                    "id": student.id,
                    "department": student.department,
                    "created_at": student.created_at,
                    "latest_check_in": check_in_to_dict(latest_check_in) if latest_check_in else None,
                    "open_case_count": int(session.scalar(select(func.count(SupportCase.id)).where(
                        SupportCase.student_id == student.id,
                        SupportCase.counselor_id == user.id,
                        SupportCase.status != "closed",
                    )) or 0),
                })
            return result

    @api.get("/api/counselor/students/{student_id}", response_model=CounselorStudentDetailResponse)
    def get_counselor_student(
        student_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            student = session.scalar(select(User).where(User.id == student_id, User.role == "student"))
            if student is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
            assigned_case_exists = session.scalar(select(SupportCase.id).where(
                SupportCase.student_id == student_id, SupportCase.counselor_id == user.id
            ))
            if assigned_case_exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not assigned to this counselor")
            check_ins = list(session.scalars(
                select(CheckIn).where(CheckIn.user_id == student_id).order_by(CheckIn.created_at.desc()).limit(20)
            ))
            cases = list(session.scalars(
                select(SupportCase).where(
                    SupportCase.student_id == student_id, SupportCase.counselor_id == user.id
                ).order_by(SupportCase.updated_at.desc())
            ))
            return {
                "id": student.id,
                "department": student.department,
                "created_at": student.created_at,
                "latest_check_in": check_in_to_dict(check_ins[0]) if check_ins else None,
                "open_case_count": sum(1 for case in cases if case.status != "closed"),
                "check_ins": [check_in_to_dict(item) for item in check_ins],
                "cases": [support_case_to_dict(case, check_ins[0] if check_ins else None) for case in cases],
            }

    @api.get("/api/counselor/dashboard", response_model=CounselorDashboardResponse)
    def counselor_dashboard(
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            cases = list(
                session.scalars(
                    select(SupportCase)
                    .where(SupportCase.counselor_id == user.id)
                    .order_by(SupportCase.updated_at.desc())
                )
            )
            open_cases = [case for case in cases if case.status != "closed"]
            upcoming = list(
                session.scalars(
                    select(SupportCase)
                    .where(
                        SupportCase.counselor_id == user.id,
                        SupportCase.status != "closed",
                        SupportCase.next_follow_up.is_not(None),
                        SupportCase.next_follow_up >= datetime.now(timezone.utc),
                    )
                    .order_by(SupportCase.next_follow_up.asc())
                    .limit(10)
                )
            )
            return {
                "assigned_cases": [support_case_to_dict(case, latest_check_in_for(session, case.student_id)) for case in cases],
                "open_case_count": len(open_cases),
                "upcoming_followups": [support_case_to_dict(case, latest_check_in_for(session, case.student_id)) for case in upcoming],
            }

    @api.get("/api/counselor/cases", response_model=list[CaseResponse])
    def list_counselor_cases(
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> list[dict[str, Any]]:
        with request.app.state.database.session_factory() as session:
            cases = list(
                session.scalars(
                    select(SupportCase)
                    .where(SupportCase.counselor_id == user.id)
                    .order_by(SupportCase.updated_at.desc())
                )
            )
            return [support_case_to_dict(case, latest_check_in_for(session, case.student_id)) for case in cases]

    @api.get("/api/counselor/cases/{case_id}", response_model=CaseDetailResponse)
    def get_counselor_case(
        case_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            case = session.scalar(
                select(SupportCase).where(SupportCase.id == case_id, SupportCase.counselor_id == user.id)
            )
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            check_ins = list(
                session.scalars(
                    select(CheckIn)
                    .where(CheckIn.user_id == case.student_id)
                    .order_by(CheckIn.created_at.desc())
                    .limit(20)
                )
            )
            result = support_case_to_dict(case, check_ins[0] if check_ins else None)
            result["check_ins"] = [check_in_to_dict(item) for item in check_ins]
            return result

    @api.post("/api/counselor/cases", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
    def create_counselor_case(
        payload: CreateCaseRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            student = session.get(User, payload.student_id)
            if student is None or student.role != "student":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned student not found")
            case = SupportCase(
                counselor_id=user.id,
                student_id=student.id,
                summary=payload.summary,
                details=payload.details,
                priority=payload.priority,
                next_follow_up=payload.next_follow_up,
            )
            session.add(case)
            session.commit()
            session.refresh(case)
            return support_case_to_dict(case)

    @api.patch("/api/counselor/cases/{case_id}", response_model=CaseResponse)
    def update_counselor_case(
        case_id: str,
        payload: UpdateCaseRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            case = session.scalar(
                select(SupportCase).where(SupportCase.id == case_id, SupportCase.counselor_id == user.id)
            )
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            for field, value in payload.dict(exclude_unset=True).items():
                setattr(case, field, value)
            case.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(case)
            return support_case_to_dict(case, latest_check_in_for(session, case.student_id))

    @api.get("/api/counselor/interventions", response_model=list[InterventionResponse])
    def list_interventions(request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> list[dict[str, Any]]:
        with request.app.state.database.session_factory() as session:
            items = session.scalars(select(Intervention).where(Intervention.counselor_id == user.id).order_by(Intervention.updated_at.desc()))
            return [intervention_to_dict(item) for item in items]

    @api.post("/api/counselor/interventions", response_model=InterventionResponse, status_code=status.HTTP_201_CREATED)
    def create_intervention(payload: CreateInterventionRequest, request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            case = _counselor_case(session, payload.case_id, user.id)
            item = Intervention(case_id=case.id, counselor_id=user.id, student_id=case.student_id,
                                title=payload.title.strip(), details=payload.details)
            session.add(item); session.commit(); session.refresh(item)
            return intervention_to_dict(item)

    @api.patch("/api/counselor/interventions/{intervention_id}", response_model=InterventionResponse)
    def update_intervention(intervention_id: str, payload: UpdateInterventionRequest, request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            item = session.scalar(select(Intervention).where(Intervention.id == intervention_id, Intervention.counselor_id == user.id))
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intervention not found")
            item.status = payload.status; item.updated_at = datetime.now(timezone.utc)
            session.commit(); session.refresh(item)
            return intervention_to_dict(item)

    @api.get("/api/counselor/followups", response_model=list[FollowUpResponse])
    def list_followups(request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> list[dict[str, Any]]:
        with request.app.state.database.session_factory() as session:
            items = session.scalars(select(FollowUp).where(FollowUp.counselor_id == user.id).order_by(FollowUp.due_at.asc()))
            return [followup_to_dict(item) for item in items]

    @api.post("/api/counselor/followups", response_model=FollowUpResponse, status_code=status.HTTP_201_CREATED)
    def create_followup(payload: CreateFollowUpRequest, request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            case = _counselor_case(session, payload.case_id, user.id)
            item = FollowUp(case_id=case.id, counselor_id=user.id, student_id=case.student_id,
                            title=payload.title.strip(), due_at=payload.due_at, notes=payload.notes)
            session.add(item); session.commit(); session.refresh(item)
            return followup_to_dict(item)

    @api.patch("/api/counselor/followups/{followup_id}", response_model=FollowUpResponse)
    def update_followup(followup_id: str, payload: UpdateFollowUpRequest, request: Request, user: AuthenticatedUser = Depends(require_counselor)) -> dict[str, Any]:
        with request.app.state.database.session_factory() as session:
            item = session.scalar(select(FollowUp).where(FollowUp.id == followup_id, FollowUp.counselor_id == user.id))
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
            item.status = payload.status
            if payload.due_at is not None:
                item.due_at = payload.due_at
            item.updated_at = datetime.now(timezone.utc)
            session.commit(); session.refresh(item)
            return followup_to_dict(item)

    @api.get("/api/counselor/contacts", response_model=list[CounselorContactResponse])
    def list_counselor_contacts(
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> list[dict[str, str]]:
        with request.app.state.database.session_factory() as session:
            counselors = session.scalars(
                select(User)
                .join(SupportCase, SupportCase.counselor_id == User.id)
                .where(SupportCase.student_id == user.id, User.role == "counselor")
                .distinct()
                .order_by(User.id)
            )
            return [{"id": counselor.id, "role": counselor.role} for counselor in counselors]

    @api.get("/api/counselor/messages", response_model=CounselorThreadsResponse)
    def list_counselor_messages(
        request: Request,
        user: AuthenticatedUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        _assert_message_role(user)
        with request.app.state.database.session_factory() as session:
            query = select(Conversation).where(Conversation.kind == "counselor")
            query = query.where(
                Conversation.user_id == user.id if user.role == "student" else Conversation.counselor_id == user.id
            )
            conversations = list(session.scalars(query.order_by(Conversation.updated_at.desc())))
            return {
                "items": [counselor_thread_to_dict(session, conversation, user.role) for conversation in conversations]
            }

    @api.post("/api/counselor/messages", response_model=CounselorMessageResponse, status_code=status.HTTP_201_CREATED)
    def send_counselor_message(
        payload: CounselorMessageRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        _assert_message_role(user)
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message content cannot be blank")

        with request.app.state.database.session_factory() as session:
            conversation = None
            if user.role == "student":
                if payload.conversation_id:
                    conversation = session.scalar(
                        select(Conversation).where(
                            Conversation.id == payload.conversation_id,
                            Conversation.user_id == user.id,
                            Conversation.kind == "counselor",
                        )
                    )
                    if conversation is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
                    if payload.counselor_id and conversation.counselor_id != payload.counselor_id:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conversation recipient mismatch")
                    _assert_assigned(session, user.id, conversation.counselor_id)
                else:
                    if not payload.counselor_id:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="counselor_id is required")
                    counselor = session.get(User, payload.counselor_id)
                    if counselor is None or counselor.role != "counselor":
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counselor not found")
                    conversation = _find_assigned_thread(session, user.id, counselor.id)
                    if conversation is None:
                        conversation = Conversation(
                            user_id=user.id,
                            counselor_id=counselor.id,
                            kind="counselor",
                            title="Counselor support",
                        )
                        session.add(conversation)
                        session.flush()
            else:
                if payload.conversation_id:
                    conversation = session.scalar(
                        select(Conversation).where(
                            Conversation.id == payload.conversation_id,
                            Conversation.counselor_id == user.id,
                            Conversation.kind == "counselor",
                        )
                    )
                    if conversation is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
                    _assert_assigned(session, conversation.user_id, user.id)
                else:
                    if not payload.student_id:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="student_id is required")
                    student = session.get(User, payload.student_id)
                    if student is None or student.role != "student":
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
                    conversation = _find_assigned_thread(session, student.id, user.id)
                    if conversation is None:
                        conversation = Conversation(
                            user_id=student.id,
                            counselor_id=user.id,
                            kind="counselor",
                            title="Counselor support",
                        )
                        session.add(conversation)
                        session.flush()

            position = session.scalar(
                select(func.max(Message.position)).where(Message.conversation_id == conversation.id)
            ) or 0
            message = Message(
                conversation_id=conversation.id,
                position=int(position) + 1,
                role=user.role,
                content=content,
                read_at=datetime.now(timezone.utc),
            )
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            session.commit()
            session.refresh(message)
            return counselor_message_to_dict(message)

    @api.post("/api/counselor/messages/{conversation_id}/read", response_model=ReadMessagesResponse)
    def mark_counselor_messages_read(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_active_user),
    ) -> dict[str, Any]:
        _assert_message_role(user)
        with request.app.state.database.session_factory() as session:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.kind == "counselor",
                    Conversation.user_id == user.id if user.role == "student" else Conversation.counselor_id == user.id,
                )
            )
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            other_role = "counselor" if user.role == "student" else "student"
            now = datetime.now(timezone.utc)
            marked = session.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.role == other_role,
                Message.read_at.is_(None),
            ).update({Message.read_at: now}, synchronize_session=False)
            session.commit()
            return {"conversation_id": conversation_id, "marked_read": int(marked or 0)}

    # Anonymous support intentionally uses separate tables and serializers.
    # No endpoint in this section returns student_user_id or counselor ids.
    @api.post("/api/anonymous-support/conversations", response_model=AnonymousConversationSummary, status_code=status.HTTP_201_CREATED)
    def create_anonymous_support_conversation(
        payload: AnonymousConversationCreateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        if not payload.consent:
            raise HTTPException(status_code=422, detail="Explicit support consent is required")
        now = datetime.now(timezone.utc)
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = AnonymousSupportConversation(
                student_user_id=user.id,
                anonymous_alias=_new_anonymous_alias(session),
                category=payload.category,
                urgency=payload.urgency,
                consented_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return _anonymous_summary(conversation)

    @api.get("/api/anonymous-support/conversations", response_model=list[AnonymousConversationSummary])
    def list_anonymous_support_conversations(
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> list[dict[str, Any]]:
        with request.app.state.database.session_for_identity(user.id) as session:
            return [
                _anonymous_summary(item)
                for item in session.scalars(
                    select(AnonymousSupportConversation)
                    .where(AnonymousSupportConversation.student_user_id == user.id)
                    .order_by(AnonymousSupportConversation.updated_at.desc())
                )
            ]

    @api.get("/api/anonymous-support/conversations/{conversation_id}", response_model=AnonymousConversationResponse)
    def get_anonymous_support_conversation(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            return _anonymous_response(session, _anonymous_student_conversation(session, conversation_id, user.id))

    @api.post("/api/anonymous-support/conversations/{conversation_id}/messages", response_model=AnonymousMessageResponse, status_code=status.HTTP_201_CREATED)
    def send_anonymous_student_message(
        conversation_id: str,
        payload: AnonymousMessageRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_student_conversation(session, conversation_id, user.id)
            if conversation.status == "closed":
                raise HTTPException(status_code=409, detail="This support conversation is closed")
            position = session.scalar(select(func.max(AnonymousSupportMessage.position)).where(AnonymousSupportMessage.conversation_id == conversation.id)) or 0
            message = AnonymousSupportMessage(conversation_id=conversation.id, position=int(position) + 1, sender_role="student", content=payload.content.strip())
            conversation.status = "active" if conversation.assigned_counselor_id else conversation.status
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            session.commit()
            session.refresh(message)
            return _anonymous_message_dict(message)

    @api.post("/api/anonymous-support/conversations/{conversation_id}/close", response_model=AnonymousConversationSummary)
    def close_anonymous_support_conversation(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_student_conversation(session, conversation_id, user.id)
            conversation.status = "closed"
            conversation.closed_at = datetime.now(timezone.utc)
            conversation.updated_at = conversation.closed_at
            session.commit()
            session.refresh(conversation)
            return _anonymous_summary(conversation)

    @api.get("/api/counselor/anonymous-support", response_model=list[AnonymousConversationSummary])
    def list_anonymous_counselor_inbox(
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> list[dict[str, Any]]:
        with request.app.state.database.session_for_identity(user.id) as session:
            items = session.scalars(
                select(AnonymousSupportConversation)
                .where((AnonymousSupportConversation.assigned_counselor_id == user.id) | (AnonymousSupportConversation.assigned_counselor_id.is_(None)))
                .where(AnonymousSupportConversation.status != "closed")
                .order_by(AnonymousSupportConversation.created_at.asc())
            )
            return [_anonymous_summary(item) for item in items]

    @api.post("/api/counselor/anonymous-support/{conversation_id}/accept", response_model=AnonymousConversationSummary)
    def accept_anonymous_counselor_request(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = session.scalar(
                select(AnonymousSupportConversation)
                .where(AnonymousSupportConversation.id == conversation_id)
                .with_for_update()
            )
            if conversation is None or conversation.status == "closed":
                raise HTTPException(status_code=404, detail="Anonymous support request not found")
            if conversation.assigned_counselor_id not in (None, user.id):
                raise HTTPException(status_code=403, detail="This request is assigned to another counselor")
            conversation.assigned_counselor_id = user.id
            conversation.status = "active"
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(AnonymousSupportAuditEvent(conversation_id=conversation.id, actor_user_id=user.id, event_type="counselor_accepted"))
            session.commit()
            session.refresh(conversation)
            return _anonymous_summary(conversation)

    @api.get("/api/counselor/anonymous-support/{conversation_id}", response_model=AnonymousCounselorConversationResponse)
    def get_anonymous_counselor_conversation(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            return _anonymous_response(session, _anonymous_counselor_viewable_conversation(session, conversation_id, user.id), include_private=True)

    @api.post("/api/counselor/anonymous-support/{conversation_id}/messages", response_model=AnonymousMessageResponse, status_code=status.HTTP_201_CREATED)
    def send_anonymous_counselor_message(
        conversation_id: str,
        payload: AnonymousMessageRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_counselor_conversation(session, conversation_id, user.id)
            if conversation.status == "closed":
                raise HTTPException(status_code=409, detail="This support conversation is closed")
            position = session.scalar(select(func.max(AnonymousSupportMessage.position)).where(AnonymousSupportMessage.conversation_id == conversation.id)) or 0
            message = AnonymousSupportMessage(conversation_id=conversation.id, position=int(position) + 1, sender_role="counselor", content=payload.content.strip())
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            session.commit()
            session.refresh(message)
            return _anonymous_message_dict(message)

    @api.patch("/api/counselor/anonymous-support/{conversation_id}", response_model=AnonymousConversationSummary)
    def update_anonymous_counselor_status(
        conversation_id: str,
        payload: AnonymousStatusRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_counselor_conversation(session, conversation_id, user.id)
            conversation.status = payload.status
            conversation.closed_at = datetime.now(timezone.utc) if payload.status == "closed" else None
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(AnonymousSupportAuditEvent(conversation_id=conversation.id, actor_user_id=user.id, event_type=f"status_{payload.status}"))
            session.commit()
            session.refresh(conversation)
            return _anonymous_summary(conversation)

    @api.post("/api/counselor/anonymous-support/{conversation_id}/notes", response_model=AnonymousNoteResponse, status_code=status.HTTP_201_CREATED)
    def add_anonymous_counselor_note(
        conversation_id: str,
        payload: AnonymousNoteRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_counselor_conversation(session, conversation_id, user.id)
            note = AnonymousSupportNote(conversation_id=conversation.id, counselor_id=user.id, content=payload.content.strip())
            session.add(note)
            session.add(AnonymousSupportAuditEvent(conversation_id=conversation.id, actor_user_id=user.id, event_type="private_note_created"))
            session.commit()
            session.refresh(note)
            return {"id": note.id, "content": note.content, "created_at": note.created_at, "updated_at": note.updated_at}

    @api.post("/api/counselor/anonymous-support/{conversation_id}/followups", response_model=AnonymousFollowUpResponse, status_code=status.HTTP_201_CREATED)
    def create_anonymous_followup(
        conversation_id: str,
        payload: AnonymousFollowUpRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_counselor),
    ) -> dict[str, Any]:
        with request.app.state.database.session_for_identity(user.id) as session:
            conversation = _anonymous_counselor_conversation(session, conversation_id, user.id)
            followup = AnonymousSupportFollowUp(conversation_id=conversation.id, counselor_id=user.id, title=payload.title.strip(), due_at=payload.due_at)
            session.add(followup)
            session.add(AnonymousSupportAuditEvent(conversation_id=conversation.id, actor_user_id=user.id, event_type="followup_created"))
            session.commit()
            session.refresh(followup)
            return {"id": followup.id, "title": followup.title, "due_at": followup.due_at, "status": followup.status}

    @api.post("/api/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
    def create_conversation(
        payload: CreateConversationRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        repo: ConversationRepository = request.app.state.conversation_repository
        return conversation_to_dict(repo.create_conversation(user.id, payload.title))

    @api.get("/api/conversations", response_model=list[ConversationResponse])
    def list_conversations(request: Request, user: AuthenticatedUser = Depends(require_student)):
        repo: ConversationRepository = request.app.state.conversation_repository
        return [conversation_to_dict(item) for item in repo.list_conversations(user.id)]

    @api.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
    def get_conversation_messages(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> list[dict[str, Any]]:
        repo: ConversationRepository = request.app.state.conversation_repository
        messages = repo.get_messages(user.id, conversation_id)
        if messages is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return [message_to_dict(message) for message in messages]

    @api.get("/api/conversations/{conversation_id}/analytics", response_model=ConversationAnalyticsResponse)
    def get_conversation_analytics(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        repo: ConversationRepository = request.app.state.conversation_repository
        analytics = repo.conversation_analytics(user.id, conversation_id)
        if analytics is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return analytics

    @api.post("/api/mannmitra/text", response_model=TextTurnResponse)
    async def process_text_turn(
        payload: TextTurnRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        """Persist one turn, process it once, then persist its reply and analysis."""
        repo: ConversationRepository = request.app.state.conversation_repository
        service: MannMitraService = request.app.state.mannmitra_service
        request_started = getattr(request.state, "mannmitra_request_started", time.perf_counter())
        request_parsing_ms = (time.perf_counter() - request_started) * 1000
        persistence_started = time.perf_counter()
        try:
            claim = repo.claim_user_turn(
                user_id=user.id,
                conversation_id=payload.conversation_id,
                text=payload.text,
                request_id=payload.request_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        persistence_ms = (time.perf_counter() - persistence_started) * 1000

        if claim.status == "completed":
            stored = repo.completed_turn_payload(claim.user_message.id)
            if stored is not None:
                return stored
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn completion is still being finalized")
        if claim.status == "in_progress":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A matching request is already processing")

        try:
            context_started = time.perf_counter()
            chat_history = repo.recent_context(payload.conversation_id)
            history_scores = repo.risk_history(payload.conversation_id)
            memory_lookup_attempted = service.is_explicit_memory_request(payload.text)
            memory_anchors = service.select_previous_memory(
                payload.text,
                repo.previous_memory_candidates(user.id, payload.conversation_id),
            )
            previous_memory = repo.surrounding_previous_context(user.id, memory_anchors)
            context_risk_history_ms = (time.perf_counter() - context_started) * 1000
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                request.app.state.mannmitra_executor,
                lambda: service.process_turn(
                    payload.text,
                    chat_history=chat_history,
                    history_scores=history_scores,
                    previous_memory=previous_memory,
                    memory_lookup_attempted=memory_lookup_attempted,
                ),
            )
            persistence_started = time.perf_counter()
            repo.complete_turn(claim.user_message.id, result)
            repo.set_title_from_message(user.id, payload.conversation_id, payload.text)
        except GeminiGenerationError as exc:
            repo.mark_turn_failed(claim.user_message.id)
            logger.warning("MannMitra AI failure category=%s request_id=%s", exc.category, payload.request_id)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.public_detail) from exc
        except Exception as exc:
            repo.mark_turn_failed(claim.user_message.id)
            logger.error("Text turn processing failed type=%s request_id=%s", type(exc).__name__, payload.request_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MannMitra is temporarily unavailable",
            ) from exc

        stored = repo.completed_turn_payload(claim.user_message.id)
        persistence_ms += (time.perf_counter() - persistence_started) * 1000
        if stored is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Turn persistence failed")
        service_timings = result.latency_ms or {}
        request.state.mannmitra_latency_ms = {
            "request_id": payload.request_id,
            "request_parsing_ms": request_parsing_ms,
            "text_analysis_ms": service_timings.get("text_analysis_ms", 0.0),
            "context_risk_history_ms": context_risk_history_ms,
            "rag_retrieval_ms": service_timings.get("rag_retrieval_ms", 0.0),
            "gemini_generation_ms": service_timings.get("gemini_generation_ms", 0.0),
            "response_database_persistence_ms": persistence_ms,
        }
        return stored

    @api.post("/api/mannmitra/voice", response_model=TextTurnResponse)
    def process_voice_turn(
        request: Request,
        conversation_id: str = Form(min_length=1, max_length=36),
        request_id: str = Form(min_length=1, max_length=128),
        audio: UploadFile = File(...),
        user: AuthenticatedUser = Depends(require_student),
    ) -> dict[str, Any]:
        """Process one supported audio upload through the existing voice pipeline."""
        try:
            suffix = Path(audio.filename or "").suffix.lower()
            if suffix not in _AUDIO_SUFFIXES or audio.content_type not in _AUDIO_CONTENT_TYPES:
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only WAV and MP3 audio uploads are supported")
            audio_bytes = audio.file.read(resolved_settings.max_audio_upload_bytes + 1)
            if not audio_bytes:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Audio upload is empty")
            if len(audio_bytes) > resolved_settings.max_audio_upload_bytes:
                raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Audio upload is too large")
        finally:
            audio.file.close()

        repo: ConversationRepository = request.app.state.conversation_repository
        service: MannMitraService = request.app.state.mannmitra_service
        try:
            claim = repo.claim_voice_turn(user.id, conversation_id, request_id)
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        if claim.status == "completed":
            stored = repo.completed_turn_payload(claim.user_message.id)
            if stored is not None:
                return stored
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn completion is still being finalized")
        if claim.status == "in_progress":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A matching request is already processing")

        try:
            diagnostics = service.process_voice_input(audio_bytes, suffix=suffix)
            transcript = diagnostics.get("transcript")
            if not transcript:
                repo.update_user_message_content(claim.user_message.id, "[Voice message: transcription unavailable]")
                repo.mark_turn_failed(claim.user_message.id)
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Audio could not be transcribed")
            repo.update_user_message_content(claim.user_message.id, transcript)
            memory_lookup_attempted = service.is_explicit_memory_request(transcript)
            memory_anchors = service.select_previous_memory(
                transcript,
                repo.previous_memory_candidates(user.id, conversation_id),
            )
            result = service.process_turn(
                transcript,
                chat_history=repo.recent_context(conversation_id),
                history_scores=repo.risk_history(conversation_id),
                voice_diagnostics=diagnostics,
                previous_memory=repo.surrounding_previous_context(user.id, memory_anchors),
                memory_lookup_attempted=memory_lookup_attempted,
            )
            repo.complete_turn(claim.user_message.id, result)
            repo.set_title_from_message(user.id, conversation_id, transcript)
        except HTTPException:
            raise
        except Exception as exc:
            repo.mark_turn_failed(claim.user_message.id)
            logger.error("Voice turn processing failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MannMitra is temporarily unavailable",
            ) from exc
        stored = repo.completed_turn_payload(claim.user_message.id)
        if stored is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Turn persistence failed")
        return stored

    return api


app = create_app()
