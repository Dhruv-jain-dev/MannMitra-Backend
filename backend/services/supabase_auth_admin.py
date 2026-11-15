"""Small server-only client for the Supabase Auth admin endpoints."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SupabaseAdminError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _safe_http_error(exc: HTTPError, operation: str) -> SupabaseAdminError:
    """Convert Auth errors to safe diagnostics without returning response bodies."""
    try:
        document = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        document = {}
    code = document.get("code") or document.get("error_code") if isinstance(document, dict) else None
    if exc.code in {401, 403}:
        message = "Supabase Auth Admin authorization was rejected"
    elif exc.code == 404:
        message = "Supabase Auth Admin endpoint was not found"
    elif exc.code == 409:
        message = "Supabase Auth rejected a duplicate identity"
    elif exc.code == 429:
        message = "Supabase Auth rate limit was exceeded"
    elif 400 <= exc.code < 500:
        message = f"Supabase Auth rejected the {operation} request"
    else:
        message = f"Supabase Auth {operation} request failed"
    return SupabaseAdminError(message, status_code=exc.code, code=code if isinstance(code, str) else None)


def _decode_identity(data: object) -> dict:
    user = data.get("user", data) if isinstance(data, dict) else data
    if not isinstance(user, dict) or not isinstance(user.get("id"), str):
        raise SupabaseAdminError("Supabase Auth returned an invalid identity")
    return user


class SupabaseAuthAdmin:
    def __init__(self, base_url: str, service_role_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_role_key = service_role_key

    def invite_user(self, email: str) -> dict:
        request = Request(
            f"{self.base_url}/auth/v1/invite",
            data=json.dumps({"email": email}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.service_role_key}",
                "apikey": self.service_role_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _safe_http_error(exc, "invitation") from exc
        except (URLError, ValueError) as exc:
            raise SupabaseAdminError("Supabase Auth invitation request failed") from exc
        return _decode_identity(data)

    def create_user(self, email: str, password: str) -> dict:
        request = Request(
            f"{self.base_url}/auth/v1/admin/users",
            data=json.dumps({"email": email, "password": password, "email_confirm": True}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.service_role_key}",
                "apikey": self.service_role_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _safe_http_error(exc, "temporary-password account creation") from exc
        except (URLError, ValueError) as exc:
            raise SupabaseAdminError("Supabase Auth account creation request failed") from exc
        return _decode_identity(data)

    def list_users(self) -> list[dict]:
        request = Request(
            f"{self.base_url}/auth/v1/admin/users?per_page=100&page=1",
            headers={"Authorization": f"Bearer {self.service_role_key}", "apikey": self.service_role_key, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _safe_http_error(exc, "user lookup") from exc
        except (URLError, ValueError) as exc:
            raise SupabaseAdminError("Supabase Auth user lookup request failed") from exc
        users = data.get("users") if isinstance(data, dict) else None
        if not isinstance(users, list) or not all(isinstance(user, dict) for user in users):
            raise SupabaseAdminError("Supabase Auth returned an invalid user list")
        return users

    def find_user_by_email(self, email: str) -> dict | None:
        normalized = email.strip().casefold()
        return next((user for user in self.list_users() if isinstance(user.get("email"), str) and user["email"].casefold() == normalized), None)

    def get_user(self, user_id: str) -> dict:
        request = Request(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {self.service_role_key}", "apikey": self.service_role_key, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _safe_http_error(exc, "identity lookup") from exc
        except (URLError, ValueError) as exc:
            raise SupabaseAdminError("Supabase Auth identity lookup failed") from exc
        return _decode_identity(data)

    def delete_user(self, user_id: str) -> None:
        request = Request(
            f"{self.base_url}/auth/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {self.service_role_key}", "apikey": self.service_role_key, "Accept": "application/json"},
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=10):
                return
        except HTTPError as exc:
            raise _safe_http_error(exc, "temporary-password rollback") from exc
        except URLError as exc:
            raise SupabaseAdminError("Supabase Auth rollback request failed") from exc
