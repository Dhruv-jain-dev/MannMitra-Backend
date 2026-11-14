"""Small server-only client for the Supabase Auth admin endpoints."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SupabaseAdminError(RuntimeError):
    pass


class SupabaseAuthAdmin:
    def __init__(self, base_url: str, service_role_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_role_key = service_role_key

    def invite_user(self, email: str) -> dict:
        request = Request(
            f"{self.base_url}/auth/v1/admin/invite",
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
        except (HTTPError, URLError, ValueError) as exc:
            raise SupabaseAdminError("Supabase Auth invitation failed") from exc
        user = data.get("user", data)
        if not isinstance(user, dict) or not isinstance(user.get("id"), str):
            raise SupabaseAdminError("Supabase Auth returned an invalid identity")
        return user
