"""FastAPI application and Phase 2 SQLite-backed conversation routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import Settings, get_settings
from backend.core.database import Database
from backend.core.auth import AuthService, AuthenticatedUser
from backend.repositories.conversations import ConversationRepository, conversation_to_dict, message_to_dict
from backend.services.mannmitra_service import MannMitraService

logger = logging.getLogger("mannmitra.api")
_AUDIO_CONTENT_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3"}
_AUDIO_SUFFIXES = {".wav", ".mp3"}


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


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


def create_app(
    app_settings: Settings | None = None,
    service_factory: Callable[[], MannMitraService] = MannMitraService,
) -> FastAPI:
    """Build an app with one service and one SQLite engine per process."""
    resolved_settings = app_settings or get_settings()
    database = Database(resolved_settings.database_url)
    repository = ConversationRepository(database.session_factory)
    auth_service = AuthService(resolved_settings.auth_jwt_secret, resolved_settings.auth_jwt_issuer)
    bearer_scheme = HTTPBearer(auto_error=False)

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> AuthenticatedUser:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return auth_service.verify_access_token(credentials.credentials)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        app.state.database = database
        app.state.conversation_repository = repository
        app.state.mannmitra_service = service_factory()
        app.state.auth_service = auth_service
        try:
            yield
        finally:
            database.dispose()

    api = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)

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

    @api.post("/api/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
    def create_conversation(
        payload: CreateConversationRequest,
        request: Request,
        user: AuthenticatedUser = Depends(current_user),
    ) -> dict[str, Any]:
        repo: ConversationRepository = request.app.state.conversation_repository
        return conversation_to_dict(repo.create_conversation(user.id, payload.title))

    @api.get("/api/conversations", response_model=list[ConversationResponse])
    def list_conversations(request: Request, user: AuthenticatedUser = Depends(current_user)):
        repo: ConversationRepository = request.app.state.conversation_repository
        return [conversation_to_dict(item) for item in repo.list_conversations(user.id)]

    @api.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
    def get_conversation_messages(
        conversation_id: str,
        request: Request,
        user: AuthenticatedUser = Depends(current_user),
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
        user: AuthenticatedUser = Depends(current_user),
    ) -> dict[str, Any]:
        repo: ConversationRepository = request.app.state.conversation_repository
        analytics = repo.conversation_analytics(user.id, conversation_id)
        if analytics is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return analytics

    @api.post("/api/mannmitra/text", response_model=TextTurnResponse)
    def process_text_turn(
        payload: TextTurnRequest,
        request: Request,
        user: AuthenticatedUser = Depends(current_user),
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
            context_risk_history_ms = (time.perf_counter() - context_started) * 1000
            result = service.process_turn(
                payload.text,
                chat_history=chat_history,
                history_scores=history_scores,
            )
            persistence_started = time.perf_counter()
            repo.complete_turn(claim.user_message.id, result)
        except Exception as exc:
            repo.mark_turn_failed(claim.user_message.id)
            logger.error("Text turn processing failed: %s", exc)
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
        user: AuthenticatedUser = Depends(current_user),
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
            result = service.process_turn(
                transcript,
                chat_history=repo.recent_context(conversation_id),
                history_scores=repo.risk_history(conversation_id),
                voice_diagnostics=diagnostics,
            )
            repo.complete_turn(claim.user_message.id, result)
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
