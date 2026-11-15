"""One-time, owner-controlled bootstrap of the first admin profile."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select

from backend.models import User
from backend.services.supabase_auth_admin import SupabaseAdminError, SupabaseAuthAdmin

logger = logging.getLogger("mannmitra.admin_bootstrap")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _masked_id(value: str) -> str:
    return f"{value[:4]}...{value[-4:]}"


class BootstrapError(RuntimeError):
    pass


def _identity_is_usable(identity: dict, target_id: str) -> None:
    if identity.get("id") != target_id:
        raise BootstrapError("Supabase Auth identity does not match the configured target")
    if not identity.get("email_confirmed_at"):
        raise BootstrapError("Supabase Auth identity is not email-confirmed")
    if identity.get("deleted_at"):
        raise BootstrapError("Supabase Auth identity is deleted")
    banned_until = identity.get("banned_until")
    if banned_until:
        try:
            if datetime.fromisoformat(banned_until.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                raise BootstrapError("Supabase Auth identity is currently banned")
        except ValueError as exc:
            raise BootstrapError("Supabase Auth identity has an invalid ban status") from exc


def bootstrap_first_admin(
    *,
    target_id: str,
    auth_admin: SupabaseAuthAdmin,
    session_factory: Callable,
) -> dict[str, str]:
    """Verify the configured Auth identity, then create exactly one admin profile."""
    if not _UUID_RE.fullmatch(target_id):
        raise BootstrapError("Bootstrap target must be a UUID")
    try:
        identity = auth_admin.get_user(target_id)
    except SupabaseAdminError as exc:
        raise BootstrapError("Configured bootstrap identity could not be verified") from exc
    _identity_is_usable(identity, target_id)

    with session_factory() as session:
        with session.begin():
            if session.scalar(select(func.count(User.id)).where(User.role == "admin")):
                raise BootstrapError("An administrator already exists; bootstrap is disabled")
            existing = session.get(User, target_id)
            if existing is not None:
                if existing.role != "admin":
                    raise BootstrapError("Target profile already exists with an incompatible role")
                raise BootstrapError("Target profile already exists; bootstrap is not repeatable")
            session.add(User(id=target_id, role="admin"))
    logger.info("admin_bootstrap_success target_id=%s", _masked_id(target_id))
    return {"id": target_id, "role": "admin"}
