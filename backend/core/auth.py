"""Minimal HS256 JWT verification for API user identity."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str


class AuthService:
    """Verifies signed bearer tokens without storing or exposing token secrets."""

    def __init__(self, secret: str | None, issuer: str) -> None:
        self._secret = secret.encode("utf-8") if secret else None
        self._issuer = issuer

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        if not self._secret:
            raise self._unauthorized("Authentication is not configured")
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            header = json.loads(_base64url_decode(encoded_header))
            payload: dict[str, Any] = json.loads(_base64url_decode(encoded_payload))
            if header.get("alg") != "HS256" or header.get("typ") != "JWT":
                raise ValueError("Unsupported token header")
            expected = hmac.new(
                self._secret,
                f"{encoded_header}.{encoded_payload}".encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(_base64url_encode(expected), encoded_signature):
                raise ValueError("Invalid token signature")
            subject = payload.get("sub")
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError("Missing token subject")
            if payload.get("iss") != self._issuer:
                raise ValueError("Invalid token issuer")
            if not isinstance(payload.get("exp"), (int, float)) or payload["exp"] <= time.time():
                raise ValueError("Expired token")
            return AuthenticatedUser(id=subject)
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
            raise self._unauthorized("Invalid or expired access token") from exc

    def create_access_token(self, subject: str, expires_in_seconds: int = 3600) -> str:
        """Build a signed token for tests and the development-only token route."""
        if not self._secret:
            raise RuntimeError("Authentication is not configured")
        header = _base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _base64url_encode(
            json.dumps(
                {"sub": subject, "iss": self._issuer, "exp": int(time.time()) + expires_in_seconds},
                separators=(",", ":"),
            ).encode()
        )
        signature = _base64url_encode(
            hmac.new(self._secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
        )
        return f"{header}.{payload}.{signature}"

    @staticmethod
    def _unauthorized(detail: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
