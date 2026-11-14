from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.core.auth import AuthenticatedUser, require_admin
from backend.core.config import Settings
from backend.core.database import Database
from backend.main import (
    AssignmentRequest,
    ProvisionUserRequest,
    RoleUpdateRequest,
    create_app,
)
from backend.models import SupportCase, User


class AdminManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "admin.db"
        self.database = Database(f"sqlite:///{db_path.as_posix()}")
        self.database.create_all()
        self.app = create_app(
            Settings(
                app_name="admin management tests",
                environment="test",
                database_url=f"sqlite:///{db_path.as_posix()}",
                auth_jwt_secret="test-secret",
            ),
            service_factory=lambda: object(),
        )
        self.app.state.database = self.database
        with self.database.session_factory() as session:
            session.add_all([
                User(id="admin-1", role="admin"),
                User(id="student-1", role="student", department="Engineering"),
                User(id="counselor-1", role="counselor"),
            ])
            session.add(SupportCase(
                id="case-1",
                counselor_id="counselor-1",
                student_id="student-1",
                summary="Initial review",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            session.commit()
        self.request = SimpleNamespace(app=self.app)
        self.admin = AuthenticatedUser(id="admin-1", role="admin")

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp_dir.cleanup()

    def endpoint(self, path: str, method: str):
        return next(route.endpoint for route in self.app.routes if route.path == path and method in route.methods)

    def test_admin_routes_require_admin_dependency(self) -> None:
        protected = {
            "/api/admin/users",
            "/api/admin/users/{user_id}",
            "/api/admin/users/provision",
            "/api/admin/users/{user_id}/role",
            "/api/admin/cases",
            "/api/admin/cases/{case_id}/assignment",
            "/api/admin/interventions",
            "/api/admin/followups",
        }
        for route in self.app.routes:
            if route.path in protected:
                self.assertIn(require_admin, [dependency.call for dependency in route.dependant.dependencies])

    def test_user_listing_pagination_and_profile_provisioning(self) -> None:
        list_users = self.endpoint("/api/admin/users", "GET")
        page = list_users(self.request, page=1, page_size=2, role=None, user=self.admin)
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 2)

        provision = self.endpoint("/api/admin/users/provision", "POST")
        result = provision(
            ProvisionUserRequest(id="counselor-2", role="counselor", department="Arts"),
            self.request,
            self.admin,
        )
        self.assertEqual(result["role"], "counselor")
        with self.database.session_factory() as session:
            self.assertEqual(session.get(User, "counselor-2").role, "counselor")

    def test_role_change_and_self_demotion_protection(self) -> None:
        update_role = self.endpoint("/api/admin/users/{user_id}/role", "PATCH")
        result = update_role("student-1", RoleUpdateRequest(role="counselor"), self.request, self.admin)
        self.assertEqual(result["role"], "counselor")
        with self.assertRaisesRegex(Exception, "cannot demote themselves"):
            update_role("admin-1", RoleUpdateRequest(role="student"), self.request, self.admin)

    def test_case_assignment_validates_counselor_and_supports_reassignment(self) -> None:
        provision = self.endpoint("/api/admin/users/provision", "POST")
        provision(ProvisionUserRequest(id="counselor-2", role="counselor"), self.request, self.admin)
        assign = self.endpoint("/api/admin/cases/{case_id}/assignment", "PATCH")
        result = assign("case-1", AssignmentRequest(counselor_id="counselor-2"), self.request, self.admin)
        self.assertEqual(result["counselor_id"], "counselor-2")

    def test_monitoring_endpoints_return_paginated_real_rows(self) -> None:
        cases = self.endpoint("/api/admin/cases", "GET")
        interventions = self.endpoint("/api/admin/interventions", "GET")
        followups = self.endpoint("/api/admin/followups", "GET")
        self.assertEqual(cases(self.request, page=1, page_size=10, case_status=None, counselor_id=None, student_id=None, user=self.admin)["total"], 1)
        self.assertEqual(interventions(self.request, page=1, page_size=10, counselor_id=None, student_id=None, user=self.admin)["total"], 0)
        self.assertEqual(followups(self.request, page=1, page_size=10, followup_status=None, counselor_id=None, student_id=None, user=self.admin)["total"], 0)


if __name__ == "__main__":
    unittest.main()
