"""Supabase JWT verification and database-backed role authorization."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.request import Request as UrlRequest, urlopen

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.models import User

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
_ASYMMETRIC_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"}


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    role: str | None = None
    must_change_password: bool = False


class AuthService:
    """Verify Supabase tokens; local HS256 tokens are explicitly test-only."""

    def __init__(self, secret: str | None, issuer: str, *, supabase_url: str | None = None,
                 jwks_url: str | None = None, audience: str = "authenticated",
                 supabase_jwt_secret: str | None = None, allow_legacy_tokens: bool = True) -> None:
        self._legacy_secret = secret.encode("utf-8") if secret else None
        self._legacy_issuer = issuer
        self._issuer = issuer
        self._audience = audience
        self._supabase_jwt_secret = supabase_jwt_secret
        self._jwks_url = jwks_url or (f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json" if supabase_url else None)
        self._allow_legacy_tokens = allow_legacy_tokens
        self._keys: dict[str, dict[str, Any]] = {}
        self._keys_loaded_at = 0.0
        self._keys_lock = threading.Lock()

    @staticmethod
    def _unauthorized(detail: str) -> HTTPException:
        return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})

    def _load_jwks(self) -> dict[str, dict[str, Any]]:
        if not self._jwks_url:
            raise ValueError("Supabase JWKS URL is not configured")
        if self._keys and time.monotonic() - self._keys_loaded_at < 300:
            return self._keys
        with self._keys_lock:
            if self._keys and time.monotonic() - self._keys_loaded_at < 300:
                return self._keys
            with urlopen(UrlRequest(self._jwks_url, headers={"Accept": "application/json"}), timeout=5) as response:
                document = json.loads(response.read().decode("utf-8"))
            keys = document.get("keys")
            if not isinstance(keys, list):
                raise ValueError("Supabase JWKS response is invalid")
            parsed = {item["kid"]: item for item in keys if isinstance(item, dict) and isinstance(item.get("kid"), str)}
            if not parsed:
                raise ValueError("Supabase JWKS contains no usable keys")
            self._keys, self._keys_loaded_at = parsed, time.monotonic()
            return self._keys

    def _verify_supabase_token(self, token: str) -> AuthenticatedUser:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm not in _ASYMMETRIC_ALGORITHMS and algorithm != "HS256":
            raise ValueError("Unsupported JWT algorithm")
        if algorithm == "HS256":
            if not self._supabase_jwt_secret:
                raise ValueError("HS256 Supabase verification is not configured")
            key: Any = self._supabase_jwt_secret
        else:
            jwk = self._load_jwks().get(header.get("kid"))
            if jwk is None or jwk.get("alg", algorithm) != algorithm:
                raise ValueError("JWT signing key is unavailable or incompatible")
            key = jwt.algorithms.get_default_algorithms()[algorithm].from_jwk(json.dumps(jwk))
        claims = jwt.decode(token, key, algorithms=[algorithm], audience=self._audience, issuer=self._issuer,
                            options={"require": ["sub", "exp", "iat", "iss", "aud"]})
        subject = claims.get("sub")
        if not isinstance(subject, str) or not _UUID_RE.fullmatch(subject):
            raise ValueError("JWT subject is not a Supabase Auth UUID")
        return AuthenticatedUser(id=subject)

    def _verify_legacy_test_token(self, token: str) -> AuthenticatedUser:
        if not self._allow_legacy_tokens or not self._legacy_secret:
            raise ValueError("Legacy authentication is disabled")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed legacy token")
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        header, payload = json.loads(decode(parts[0])), json.loads(decode(parts[1]))
        expected = base64.urlsafe_b64encode(hmac.new(self._legacy_secret, f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode("ascii")
        if header.get("alg") != "HS256" or header.get("typ") != "JWT" or not hmac.compare_digest(expected, parts[2]):
            raise ValueError("Invalid legacy token")
        if payload.get("iss") != self._legacy_issuer or not isinstance(payload.get("sub"), str) or payload.get("exp", 0) <= time.time():
            raise ValueError("Invalid legacy token claims")
        return AuthenticatedUser(id=payload["sub"])

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        try:
            return self._verify_supabase_token(token) if (self._jwks_url or self._supabase_jwt_secret) else self._verify_legacy_test_token(token)
        except Exception as exc:
            raise self._unauthorized("Invalid or expired access token") from exc

    def create_access_token(self, subject: str, expires_in_seconds: int = 3600) -> str:
        if not self._allow_legacy_tokens or not self._legacy_secret:
            raise RuntimeError("Local token creation is disabled")
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        header = encode(b'{"alg":"HS256","typ":"JWT"}')
        payload = encode(json.dumps({"sub": subject, "iss": self._legacy_issuer, "exp": int(time.time()) + expires_in_seconds}, separators=(",", ":")).encode())
        signature = encode(hmac.new(self._legacy_secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest())
        return f"{header}.{payload}.{signature}"


_bearer_scheme = HTTPBearer(auto_error=False)


def get_verified_subject(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> AuthenticatedUser:
    if credentials is None:
        raise AuthService._unauthorized("Bearer authentication is required")
    return request.app.state.auth_service.verify_access_token(credentials.credentials)


def get_current_user(request: Request, subject: AuthenticatedUser = Depends(get_verified_subject)) -> AuthenticatedUser:
    with request.app.state.database.session_for_identity(subject.id) as session:
        user = session.get(User, subject.id)
        if user is None:
            if request.app.state.environment not in {"development", "dev", "test"}:
                raise AuthService._unauthorized("Authenticated user was not found")
            user = User(id=subject.id, role="student")
            session.add(user)
            session.commit()
        if user.role not in {"student", "counselor", "admin"}:
            raise HTTPException(status_code=403, detail="User role is invalid")
        return AuthenticatedUser(id=user.id, role=user.role, must_change_password=user.must_change_password)


def _require_role(required_role: str):
    def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.must_change_password:
            raise HTTPException(status_code=403, detail="Password change is required before accessing this resource")
        if user.role != required_role:
            raise HTTPException(status_code=403, detail=f"{required_role.capitalize()} role is required")
        return user
    return dependency


def require_active_user(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Password change is required before accessing this resource")
    return user


require_student = _require_role("student")
require_counselor = _require_role("counselor")
require_admin = _require_role("admin")
