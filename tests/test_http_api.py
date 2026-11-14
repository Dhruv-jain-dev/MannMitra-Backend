from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.core.auth import AuthService
from backend.core.database import Database
from backend.models import SupportCase, User


class HttpApiSecurityTests(unittest.TestCase):
    """Run real loopback HTTP requests instead of Starlette TestClient."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.database_path = Path(cls.temp_dir.name) / "http-tests.db"
        cls.secret = "isolated-http-test-secret"
        cls.port = cls._free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.environment = os.environ.copy()
        cls.environment["CAMPUSPULSE_TEST_DATABASE_URL"] = f"sqlite:///{cls.database_path.as_posix()}"
        cls.environment["CAMPUSPULSE_TEST_JWT_SECRET"] = cls.secret
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "tests.http_test_app:app", "--host", "127.0.0.1", "--port", str(cls.port), "--log-level", "error"],
            cwd=Path(__file__).resolve().parents[1],
            env=cls.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls._wait_for_server()
        cls.database = Database(f"sqlite:///{cls.database_path.as_posix()}")
        with cls.database.session_factory() as session:
            session.add_all([
                User(id="student-1", role="student", department="Engineering"),
                User(id="student-2", role="student", department="Engineering"),
                User(id="counselor-1", role="counselor"),
                User(id="counselor-2", role="counselor"),
                User(id="admin-1", role="admin"),
            ])
            session.commit()
        cls.auth = AuthService(cls.secret, "mannmitra-api")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.dispose()
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=5)
        cls.temp_dir.cleanup()

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @classmethod
    def _wait_for_server(cls) -> None:
        deadline = time.time() + 8
        last_error = None
        while time.time() < deadline:
            try:
                status, _ = cls._raw_request("GET", "/health")
                if status == 200:
                    return
            except (OSError, URLError) as error:
                last_error = error
            time.sleep(0.1)
        raise RuntimeError(
            "isolated Uvicorn server did not start within 8 seconds; "
            f"loopback HTTP is unavailable in this environment ({last_error})"
        )

    @classmethod
    def _raw_request(cls, method: str, path: str, body: dict | None = None, headers: dict[str, str] | None = None):
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        request = Request(
            f"{cls.base_url}{path}",
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    @classmethod
    def _headers(cls, subject: str, expires: int = 3600) -> dict[str, str]:
        return {"Authorization": f"Bearer {cls.auth.create_access_token(subject, expires)}"}

    def request(self, method: str, path: str, body: dict | None = None, subject: str | None = None, expires: int = 3600):
        return self._raw_request(method, path, body, self._headers(subject, expires) if subject else None)

    def test_authentication_and_role_authorization(self) -> None:
        self.assertEqual(self._raw_request("GET", "/api/admin/dashboard")[0], 401)
        self.assertEqual(self.request("GET", "/api/admin/dashboard", subject="student-1")[0], 403)
        self.assertEqual(self.request("GET", "/api/admin/dashboard", subject="admin-1")[0], 200)
        self.assertEqual(self.request("GET", "/api/counselor/dashboard", subject="student-1")[0], 403)
        self.assertEqual(self.request("GET", "/api/counselor/dashboard", subject="counselor-1")[0], 200)
        self.assertEqual(self.request("GET", "/api/wellbeing/insights", subject="student-1")[0], 200)
        self.assertEqual(self.request("GET", "/api/wellbeing/insights", subject="admin-1")[0], 403)
        self.assertEqual(self.request("GET", "/api/admin/dashboard", subject="student-1", expires=-1)[0], 401)

    def test_checkin_crud_and_student_isolation(self) -> None:
        status, created = self.request("POST", "/api/wellbeing/check-in", {"mood": "stressed", "stress_level": 8, "notes": "private"}, "student-1")
        self.assertEqual(status, 201)
        self.assertEqual(self.request("GET", "/api/wellbeing/check-ins", subject="student-1")[1]["total"], 1)
        self.assertEqual(self.request("GET", "/api/wellbeing/check-ins", subject="student-2")[1]["total"], 0)
        insights = self.request("GET", "/api/wellbeing/insights", subject="student-1")[1]
        self.assertEqual(insights["check_in_count"], 1)
        self.assertEqual(self.request("POST", "/api/wellbeing/check-in", {"mood": "invalid", "stress_level": 8}, "student-1")[0], 422)
        self.assertNotIn("private", json.dumps(self.request("GET", "/api/admin/dashboard", subject="admin-1")[1]))
        self.assertIsNotNone(created["id"])

    def test_conversation_ownership(self) -> None:
        status, conversation = self.request("POST", "/api/conversations", {"title": "Private"}, "student-1")
        self.assertEqual(status, 201)
        conversation_id = conversation["id"]
        self.assertEqual(self.request("GET", "/api/conversations", subject="student-1")[0], 200)
        self.assertEqual(self.request("GET", f"/api/conversations/{conversation_id}/messages", subject="student-2")[0], 404)
        self.assertEqual(self.request("GET", f"/api/conversations/{conversation_id}/analytics", subject="student-2")[0], 404)

    def test_counselor_case_and_messaging_assignment_restrictions(self) -> None:
        status, case = self.request("POST", "/api/counselor/cases", {"student_id": "student-1", "summary": "Support case"}, "counselor-1")
        self.assertEqual(status, 201)
        case_id = case["id"]
        self.assertEqual(self.request("GET", "/api/counselor/cases", subject="counselor-2")[1], [])
        self.assertEqual(self.request("GET", f"/api/counselor/cases/{case_id}", subject="counselor-2")[0], 404)
        self.assertEqual(self.request("POST", "/api/counselor/cases", {"student_id": "student-1", "summary": "No"}, "student-1")[0], 403)

        status, message = self.request("POST", "/api/counselor/messages", {"counselor_id": "counselor-1", "content": "Need support"}, "student-1")
        self.assertEqual(status, 201)
        conversation_id = message["conversation_id"]
        self.assertEqual(self.request("GET", "/api/counselor/messages", subject="counselor-1")[0], 200)
        self.assertEqual(self.request("GET", "/api/counselor/messages", subject="counselor-2")[1]["items"], [])
        self.assertEqual(self.request("POST", "/api/counselor/messages", {"conversation_id": conversation_id, "content": "No access"}, "student-2")[0], 404)
        self.assertEqual(self.request("POST", "/api/counselor/messages", {"conversation_id": conversation_id, "content": "Reply"}, "counselor-1")[0], 201)


if __name__ == "__main__":
    unittest.main()
