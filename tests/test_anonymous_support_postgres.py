"""Real PostgreSQL RLS tests for anonymous support.

This suite is opt-in and accepts only a loopback PostgreSQL URL. It never
reads DATABASE_URL, so it cannot accidentally target Supabase.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


ROOT = Path(__file__).resolve().parents[1]
LOCAL_URL_ENV = "LOCAL_ANONYMOUS_SUPPORT_POSTGRES_URL"


def local_url() -> str | None:
    value = os.environ.get(LOCAL_URL_ENV)
    if not value:
        return None
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"{LOCAL_URL_ENV} must use a loopback host")
    if "supabase" in host or "pooler" in host:
        raise RuntimeError(f"{LOCAL_URL_ENV} cannot target Supabase or a pooler")
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise RuntimeError(f"{LOCAL_URL_ENV} must be PostgreSQL")
    return value


@unittest.skipUnless(os.environ.get(LOCAL_URL_ENV), f"Set {LOCAL_URL_ENV} to run the isolated PostgreSQL suite")
class AnonymousSupportPostgresRlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = local_url()
        cls.engine = create_engine(cls.url, pool_size=1, max_overflow=0, pool_pre_ping=True)
        config = Config(str(ROOT / "alembic-pg.ini"))
        old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = cls.url
        try:
            command.upgrade(config, "head")
        finally:
            if old_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_url
        cls._prepare_local_role_and_data()

    @classmethod
    def tearDownClass(cls):
        try:
            config = Config(str(ROOT / "alembic-pg.ini"))
            old_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = cls.url
            try:
                command.downgrade(config, "base")
            finally:
                if old_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = old_url
            with cls.engine.begin() as connection:
                connection.execute(text("DROP ROLE IF EXISTS anon_support_rls_test"))
        finally:
            cls.engine.dispose()

    @classmethod
    def _prepare_local_role_and_data(cls):
        with cls.engine.begin() as connection:
            connection.execute(text("DROP ROLE IF EXISTS anon_support_rls_test"))
            connection.execute(text("CREATE ROLE anon_support_rls_test NOLOGIN"))
            connection.execute(text("GRANT USAGE ON SCHEMA public TO anon_support_rls_test"))
            for table in ("users", "anonymous_support_conversations", "anonymous_support_messages", "anonymous_support_notes", "anonymous_support_followups", "anonymous_support_audit_events"):
                connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO anon_support_rls_test"))
            connection.execute(text("""
                INSERT INTO users (id, role, created_at) VALUES
                ('student-a', 'student', CURRENT_TIMESTAMP),
                ('student-b', 'student', CURRENT_TIMESTAMP),
                ('counselor-a', 'counselor', CURRENT_TIMESTAMP),
                ('counselor-b', 'counselor', CURRENT_TIMESTAMP),
                ('admin-a', 'admin', CURRENT_TIMESTAMP)
            """))
            connection.execute(text("""
                INSERT INTO anonymous_support_conversations
                (id, student_user_id, assigned_counselor_id, anonymous_alias, category, urgency, status, consented_at, created_at, updated_at)
                VALUES
                ('conversation-a', 'student-a', 'counselor-a', 'Mitra-AAAA000001', 'other', 'moderate', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('conversation-b', 'student-b', 'counselor-b', 'Mitra-BBBB000002', 'other', 'moderate', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            connection.execute(text("""
                INSERT INTO anonymous_support_notes (id, conversation_id, counselor_id, content, created_at, updated_at)
                VALUES ('note-a', 'conversation-a', 'counselor-a', 'private', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            connection.execute(text("""
                INSERT INTO anonymous_support_followups (id, conversation_id, counselor_id, title, due_at, created_at, updated_at)
                VALUES ('followup-a', 'conversation-a', 'counselor-a', 'check in', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            connection.execute(text("""
                INSERT INTO anonymous_support_audit_events (id, conversation_id, actor_user_id, event_type, created_at)
                VALUES ('audit-a', 'conversation-a', 'counselor-a', 'accepted', CURRENT_TIMESTAMP)
            """))

    def _run_as(self, subject: str, statement: str, parameters=None):
        with self.engine.connect() as connection:
            connection.execute(text("SET ROLE anon_support_rls_test"))
            connection.commit()
            try:
                with connection.begin():
                    connection.execute(text("SELECT set_config('request.jwt.claim.sub', :subject, true)"), {"subject": subject})
                    result = connection.execute(text(statement), parameters or {})
                    return result.scalar_one_or_none() if statement.lstrip().upper().startswith("SELECT") else None
            finally:
                # SET ROLE is session-scoped, unlike the transaction-local
                # JWT claim. Reset it before returning the connection to the pool.
                connection.execute(text("RESET ROLE"))
                connection.commit()

    def test_rls_identity_and_ownership_matrix(self):
        self.assertEqual(self._run_as("student-a", "SELECT count(*) FROM anonymous_support_conversations"), 1)
        self.assertEqual(self._run_as("student-a", "SELECT count(*) FROM anonymous_support_conversations WHERE id='conversation-b'"), 0)
        self.assertEqual(self._run_as("counselor-a", "SELECT count(*) FROM anonymous_support_conversations"), 1)
        self.assertEqual(self._run_as("counselor-b", "SELECT count(*) FROM anonymous_support_conversations WHERE id='conversation-a'"), 0)
        self.assertEqual(self._run_as("counselor-b", "SELECT count(*) FROM anonymous_support_notes"), 0)
        self.assertEqual(self._run_as("counselor-b", "SELECT count(*) FROM anonymous_support_followups"), 0)

    def test_rls_rejects_forged_writes_and_raw_audit_reads(self):
        with self.assertRaises(DBAPIError):
            self._run_as("student-a", """INSERT INTO anonymous_support_conversations
                (id, student_user_id, anonymous_alias, category, consented_at, created_at, updated_at)
                VALUES ('bad-counselor', 'counselor-a', 'Mitra-BAD000000', 'other', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""")
        with self.assertRaises(DBAPIError):
            self._run_as("student-a", """INSERT INTO anonymous_support_messages
                (id, conversation_id, position, sender_role, content, created_at)
                VALUES ('forged-student', 'conversation-a', 1, 'counselor', 'forged', CURRENT_TIMESTAMP)""")
        with self.assertRaises(DBAPIError):
            self._run_as("counselor-b", """INSERT INTO anonymous_support_messages
                (id, conversation_id, position, sender_role, content, created_at)
                VALUES ('forged-counselor', 'conversation-a', 2, 'student', 'forged', CURRENT_TIMESTAMP)""")
        with self.assertRaises(DBAPIError):
            self._run_as("student-a", "SELECT actor_user_id FROM anonymous_support_audit_events")
        with self.assertRaises(DBAPIError):
            self._run_as("counselor-b", "DELETE FROM anonymous_support_notes WHERE id='note-a'")
        with self.assertRaises(DBAPIError):
            self._run_as("student-a", "UPDATE anonymous_support_conversations SET status='closed' WHERE id='conversation-a'")

    def test_transaction_local_claim_does_not_leak_through_pool(self):
        with self.engine.connect() as connection:
            connection.execute(text("SELECT set_config('request.jwt.claim.sub', 'student-a', true)"))
            connection.commit()
        with self.engine.connect() as connection:
            value = connection.execute(text("SELECT current_setting('request.jwt.claim.sub', true)")).scalar_one()
            self.assertEqual(value, "")


if __name__ == "__main__":
    unittest.main()
