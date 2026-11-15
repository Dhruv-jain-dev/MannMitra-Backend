"""Local-only invariants for the pseudonymous support boundary."""

import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.database import Base
from backend.core.database import _propagate_jwt_subject
from backend.main import _anonymous_response, _new_anonymous_alias
from backend.models import AnonymousSupportConversation, AnonymousSupportMessage, User


class AnonymousSupportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add_all([User(id="student-1"), User(id="counselor-1", role="counselor")])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_aliases_are_random_and_unique(self):
        first = _new_anonymous_alias(self.session)
        second = _new_anonymous_alias(self.session)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^Mitra-[A-F0-9]{10}$")

    def test_student_identity_is_not_serialized(self):
        now = datetime.now(timezone.utc)
        conversation = AnonymousSupportConversation(
            student_user_id="student-1", anonymous_alias="Mitra-ABCDEF1234",
            category="emotional_support", consented_at=now, created_at=now, updated_at=now,
        )
        self.session.add(conversation)
        self.session.flush()
        self.session.add(AnonymousSupportMessage(
            conversation_id=conversation.id, position=1, sender_role="student", content="Hello"
        ))
        self.session.commit()
        output = _anonymous_response(self.session, conversation)
        self.assertEqual(output["anonymous_alias"], "Mitra-ABCDEF1234")
        self.assertNotIn("student_user_id", output)
        self.assertNotIn("counselor_id", output)
        self.assertEqual(output["messages"][0]["sender_role"], "student")

    def test_models_keep_counselor_assignment_private(self):
        columns = set(AnonymousSupportConversation.__table__.columns.keys())
        self.assertIn("student_user_id", columns)
        self.assertIn("assigned_counselor_id", columns)
        # These are storage fields only; the API response test above is the
        # boundary that prevents ordinary counselor disclosure.
        self.assertNotIn("student_user_id", _anonymous_response(self.session, AnonymousSupportConversation(
            student_user_id="student-1", anonymous_alias="Mitra-ABCDEF5678",
            category="other", consented_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )))

    def test_rls_contract_blocks_raw_audit_reads_and_identity_fields(self):
        source = (Path(__file__).resolve().parents[1] / "migrations_pg" / "versions" / "20261115_pg_02_anonymous_support.py").read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE anonymous_support_audit_events ENABLE ROW LEVEL SECURITY", source)
        self.assertNotIn("CREATE POLICY anon_support_audit_participant", source)
        self.assertIn("Only the authorized backend audit workflow", source)

    def test_rls_contract_binds_creation_and_messages_to_database_roles(self):
        source = (Path(__file__).resolve().parents[1] / "migrations_pg" / "versions" / "20261115_pg_02_anonymous_support.py").read_text(encoding="utf-8")
        self.assertIn("u.role = 'student'", source)
        self.assertIn("sender_role = 'student'", source)
        self.assertIn("sender_role = 'counselor'", source)
        self.assertIn("u.role = 'counselor'", source)
        self.assertNotIn("CREATE POLICY anon_support_messages_participant", source)

    def test_rls_contract_requires_assignment_for_private_records(self):
        source = (Path(__file__).resolve().parents[1] / "migrations_pg" / "versions" / "20261115_pg_02_anonymous_support.py").read_text(encoding="utf-8")
        for policy in ("anon_support_notes_counselor", "anon_support_followups_counselor"):
            start = source.index(f"CREATE POLICY {policy}")
            block = source[start:source.index('""")', start)]
            self.assertIn("c.assigned_counselor_id = current_setting", block)
            self.assertIn("u.role = 'counselor'", block)

    def test_identity_propagation_is_transaction_local_and_parameterized(self):
        class Dialect:
            name = "postgresql"

        class Connection:
            dialect = Dialect()

            def __init__(self):
                self.calls = []

            def execute(self, statement, parameters):
                self.calls.append((str(statement), parameters))

        class SessionLike:
            info = {"jwt_subject": "student-uuid"}

        connection = Connection()
        _propagate_jwt_subject(SessionLike(), None, connection)
        self.assertEqual(len(connection.calls), 1)
        statement, parameters = connection.calls[0]
        self.assertIn("set_config('request.jwt.claim.sub'", statement)
        self.assertIn("true", statement)
        self.assertEqual(parameters, {"subject": "student-uuid"})


if __name__ == "__main__":
    unittest.main()
