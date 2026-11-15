from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.bootstrap_admin import CONFIRMATION, main
from backend.core.database import Database
from backend.models import User
from backend.services.admin_bootstrap import BootstrapError, bootstrap_first_admin


class FakeAuthAdmin:
    def __init__(self, identity=None, error=None):
        self.identity = identity
        self.error = error

    def get_user(self, user_id):
        if self.error:
            raise self.error
        return self.identity


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(f"sqlite:///{(Path(self.temp_dir.name) / 'bootstrap.db').as_posix()}")
        self.database.create_all()
        self.target = str(uuid4())
        self.identity = {"id": self.target, "email_confirmed_at": "2026-11-15T00:00:00Z", "deleted_at": None, "banned_until": None}

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp_dir.cleanup()

    def bootstrap(self, identity=None):
        return bootstrap_first_admin(
            target_id=self.target,
            auth_admin=FakeAuthAdmin(identity if identity is not None else self.identity),
            session_factory=self.database.session_factory,
        )

    def test_successful_bootstrap_creates_admin_profile(self) -> None:
        self.assertEqual(self.bootstrap(), {"id": self.target, "role": "admin"})
        with self.database.session_factory() as session:
            self.assertEqual(session.get(User, self.target).role, "admin")

    def test_unknown_or_unconfirmed_identity_is_rejected(self) -> None:
        with self.assertRaises(BootstrapError):
            self.bootstrap({"id": str(uuid4()), "email_confirmed_at": "2026-11-15T00:00:00Z"})
        with self.assertRaises(BootstrapError):
            self.bootstrap({"id": self.target, "email_confirmed_at": None})

    def test_existing_admin_and_incompatible_profile_are_rejected(self) -> None:
        with self.database.session_factory() as session:
            session.add(User(id="existing-admin", role="admin")); session.commit()
        with self.assertRaises(BootstrapError):
            self.bootstrap()

        with self.database.session_factory() as session:
            session.query(User).delete(); session.add(User(id=self.target, role="student")); session.commit()
        with self.assertRaises(BootstrapError):
            self.bootstrap()

    def test_duplicate_execution_is_rejected_safely(self) -> None:
        self.bootstrap()
        with self.assertRaises(BootstrapError):
            self.bootstrap()

    def test_cli_rejects_missing_or_wrong_confirmation_before_setup(self) -> None:
        with self.assertRaises(SystemExit):
            main([])
        with self.assertRaises(SystemExit):
            main(["--confirm", "wrong-token"])

    def test_confirmation_constant_is_explicit(self) -> None:
        self.assertEqual(CONFIRMATION, "BOOTSTRAP-FIRST-ADMIN-20261115")


if __name__ == "__main__":
    unittest.main()
