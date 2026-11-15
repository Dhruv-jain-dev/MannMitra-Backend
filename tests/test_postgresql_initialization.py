from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.models import Base


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "migrations_pg" / "versions" / "20261114_pg_00_initial.py"
PASSWORD_MIGRATION_PATH = ROOT / "migrations_pg" / "versions" / "20261115_pg_01_password_change.py"
ANONYMOUS_MIGRATION_PATH = ROOT / "migrations_pg" / "versions" / "20261115_pg_02_anonymous_support.py"


def migration_module():
    spec = importlib.util.spec_from_file_location("pg_initial_test_module", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load PostgreSQL initializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def password_migration_module():
    spec = importlib.util.spec_from_file_location("pg_password_change_test_module", PASSWORD_MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load password-change migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def anonymous_migration_module():
    spec = importlib.util.spec_from_file_location("pg_anonymous_support_test_module", ANONYMOUS_MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load anonymous-support migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PostgreSQLInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration_module().upgrade()
                password_migration_module().upgrade()
                anonymous_migration_module().upgrade()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_initializer_has_no_batch_rebuilds(self) -> None:
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("batch_alter_table", source)
        self.assertNotIn('recreate="always"', source)

    def test_complete_schema_contains_all_eight_tables(self) -> None:
        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            {"users", "conversations", "messages", "message_analyses", "check_ins", "support_cases", "interventions", "followups", "anonymous_support_conversations", "anonymous_support_messages", "anonymous_support_notes", "anonymous_support_followups", "anonymous_support_audit_events"},
        )

    def test_model_to_migration_column_parity(self) -> None:
        inspector = inspect(self.engine)
        for table_name, table in Base.metadata.tables.items():
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            self.assertEqual(actual, {column.name for column in table.columns}, table_name)

    def test_foreign_keys_and_delete_actions(self) -> None:
        inspector = inspect(self.engine)
        expected = {
            ("conversations", "counselor_id", "users", "CASCADE"), ("check_ins", "user_id", "users", "CASCADE"),
            ("support_cases", "counselor_id", "users", "CASCADE"), ("support_cases", "student_id", "users", "CASCADE"),
            ("interventions", "case_id", "support_cases", "CASCADE"), ("interventions", "counselor_id", "users", "CASCADE"),
            ("interventions", "student_id", "users", "CASCADE"), ("followups", "case_id", "support_cases", "CASCADE"),
            ("followups", "counselor_id", "users", "CASCADE"), ("followups", "student_id", "users", "CASCADE"),
            ("anonymous_support_conversations", "student_user_id", "users", "CASCADE"), ("anonymous_support_conversations", "assigned_counselor_id", "users", "SET NULL"),
            ("anonymous_support_messages", "conversation_id", "anonymous_support_conversations", "CASCADE"),
            ("anonymous_support_notes", "conversation_id", "anonymous_support_conversations", "CASCADE"), ("anonymous_support_notes", "counselor_id", "users", "CASCADE"),
            ("anonymous_support_followups", "conversation_id", "anonymous_support_conversations", "CASCADE"), ("anonymous_support_followups", "counselor_id", "users", "CASCADE"),
            ("anonymous_support_audit_events", "conversation_id", "anonymous_support_conversations", "CASCADE"), ("anonymous_support_audit_events", "actor_user_id", "users", "CASCADE"),
        }
        actual = set()
        for table_name in ("conversations", "check_ins", "support_cases", "interventions", "followups", "anonymous_support_conversations", "anonymous_support_messages", "anonymous_support_notes", "anonymous_support_followups", "anonymous_support_audit_events"):
            for foreign_key in inspector.get_foreign_keys(table_name):
                actual.add((table_name, foreign_key["constrained_columns"][0], foreign_key["referred_table"], (foreign_key.get("options") or {}).get("ondelete")))
        self.assertTrue(expected.issubset(actual))

    def test_indexes_and_unique_constraints(self) -> None:
        inspector = inspect(self.engine)
        expected_indexes = {
            "ix_users_role", "ix_users_department", "ix_conversations_user_id", "ix_conversations_counselor_id",
            "ix_conversations_counselor_kind", "ix_messages_conversation_id", "ix_message_analyses_message_id",
            "ix_check_ins_user_id", "ix_check_ins_user_created_at", "ix_support_cases_counselor_status",
            "ix_support_cases_student", "ix_support_cases_follow_up", "ix_interventions_counselor_status",
            "ix_interventions_case", "ix_followups_counselor_status_due", "ix_followups_case",
        }
        actual_indexes = {index["name"] for table_name in inspector.get_table_names() for index in inspector.get_indexes(table_name)}
        self.assertTrue(expected_indexes.issubset(actual_indexes))
        unique_names = {constraint["name"] for table_name in ("messages", "message_analyses") for constraint in inspector.get_unique_constraints(table_name)}
        self.assertTrue({"uq_message_request_per_conversation", "uq_message_position_per_conversation", "uq_messages_reply_to_message_id"}.issubset(unique_names))

    def test_roles_and_student_default(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, created_at) VALUES ('u1', CURRENT_TIMESTAMP)"))
            role = connection.execute(text("SELECT role FROM users WHERE id='u1'")).scalar_one()
        self.assertEqual(role, "student")

    def test_reply_to_allows_nulls_and_rejects_duplicate_non_null(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, created_at) VALUES ('u1', CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO conversations (id, user_id, created_at, updated_at) VALUES ('c1', 'u1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            statement = text("INSERT INTO messages (id, conversation_id, position, role, content, created_at) VALUES (:id, 'c1', :position, 'user', 'x', CURRENT_TIMESTAMP)")
            connection.execute(statement, {"id": "m1", "position": 1})
            connection.execute(statement, {"id": "m2", "position": 2})
            connection.execute(text("UPDATE messages SET reply_to_message_id='m1' WHERE id='m2'"))
            connection.execute(statement, {"id": "m3", "position": 3})
            with self.assertRaises(IntegrityError):
                connection.execute(text("UPDATE messages SET reply_to_message_id='m1' WHERE id='m3'"))


class PostgreSQLGraphTests(unittest.TestCase):
    def test_graph_has_one_head_and_excludes_adoption(self) -> None:
        scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic-pg.ini")))
        self.assertEqual(scripts.get_heads(), ["20261115_pg_02_anonymous_support"])
        with self.assertRaises(CommandError):
            scripts.get_revision("20261112_06")

    def test_backend_selects_postgresql_graph(self) -> None:
        source = (ROOT / "backend" / "core" / "database.py").read_text(encoding="utf-8")
        self.assertIn('config_name = "alembic-pg.ini" if is_postgresql else "alembic.ini"', source)
        self.assertIn('target_revision = revision if is_postgresql or revision != "head" else "20261110_05"', source)


if __name__ == "__main__":
    unittest.main()
