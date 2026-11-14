import unittest
from unittest.mock import patch

import migrations.adopt_supabase as adoption
from migrations.adoption_validation import (
    APPLICATION_TABLES,
    EXPECTED_COLUMN_NAMES,
    EXPECTED_CONSTRAINTS,
    EXPECTED_FOREIGN_KEYS,
    EXPECTED_INDEXES,
    AdoptionValidationError,
    validate_baseline_snapshot,
    validate_constraint_metadata,
    validate_index_metadata,
)


def _complete_snapshot() -> dict:
    indexes = {
        name: {
            "table": spec.table,
            "unique": spec.unique,
            "access_method": spec.access_method,
            "columns": spec.columns,
            "included_columns": spec.included_columns,
            "predicate": spec.predicate,
            "expressions": spec.expressions,
            "indoption": spec.indoption or (0,) * len(spec.columns),
        }
        for name, spec in EXPECTED_INDEXES.items()
    }
    constraints = {}
    for name, spec in EXPECTED_CONSTRAINTS.items():
        if spec.constraint_type == "f":
            definition = "FOREIGN KEY (counselor_id) REFERENCES users(id) ON DELETE CASCADE"
        else:
            values = ", ".join(repr(value) for value in sorted(spec.check_literals))
            definition = f"CHECK ({spec.check_columns[0] if spec.check_columns else 'value'} IN ({values}))"
            definition += " " + " ".join(spec.required_definition_parts)
            definition += " " + " ".join(operator for operator, _ in spec.operator_counts)
        constraints[name] = {
            "table": spec.table,
            "constraint_type": spec.constraint_type,
            "columns": spec.check_columns if spec.constraint_type == "c" else spec.columns,
            "referenced_table": spec.referenced_table,
            "referenced_columns": spec.referenced_columns,
            "on_delete": spec.on_delete,
            "validated": spec.validated,
            "deferrable": spec.deferrable,
            "initially_deferred": spec.initially_deferred,
            "definition": definition,
        }
    for table in ("users", "conversations", "messages", "message_analyses", "check_ins", "support_cases", "interventions", "followups"):
        constraints[f"{table}_pkey"] = {
            "table": table, "constraint_type": "p", "columns": ("id",),
            "referenced_table": None, "referenced_columns": (), "on_delete": None,
            "validated": True, "deferrable": False, "initially_deferred": False,
            "definition": "PRIMARY KEY (id)",
        }
    for name, table, columns in (
        ("uq_request", "messages", ("conversation_id", "client_request_id")),
        ("uq_position", "messages", ("conversation_id", "position")),
        ("uq_reply", "messages", ("reply_to_message_id",)),
        ("uq_analysis", "message_analyses", ("message_id",)),
    ):
        constraints[name] = {
            "table": table, "constraint_type": "u", "columns": columns,
            "referenced_table": None, "referenced_columns": (), "on_delete": None,
            "validated": True, "deferrable": False, "initially_deferred": False,
            "definition": f"UNIQUE ({', '.join(columns)})",
        }
    return {
        "tables": set(APPLICATION_TABLES),
        "columns": {table: set(columns) for table, columns in EXPECTED_COLUMN_NAMES.items()},
        "indexes": indexes,
        "constraints": constraints,
        "foreign_keys": set(EXPECTED_FOREIGN_KEYS),
    }


def _adoption_gap_snapshot() -> dict:
    snapshot = _complete_snapshot()
    for table, columns in {"users": {"role", "department"}, "conversations": {"counselor_id", "kind"}, "messages": {"read_at"}}.items():
        snapshot["columns"][table] -= columns
    for name in ("ix_users_role", "ix_users_department", "ix_conversations_counselor_id", "ix_conversations_counselor_kind", "ix_message_analyses_message_id"):
        snapshot["indexes"].pop(name)
    snapshot["constraints"].pop("ck_users_role")
    snapshot["constraints"].pop("ck_conversations_kind")
    snapshot["constraints"].pop("fk_conversations_counselor_id_users")
    snapshot["foreign_keys"].remove(("conversations", ("counselor_id",), "users", ("id",), "CASCADE"))
    return snapshot


class AdoptionValidationTests(unittest.TestCase):
    def test_incompatible_index_definition_is_rejected(self) -> None:
        actual = _complete_snapshot()["indexes"]["ix_users_role"] | {"unique": True}
        with self.assertRaises(AdoptionValidationError):
            validate_index_metadata("ix_users_role", actual, EXPECTED_INDEXES["ix_users_role"])

    def test_incompatible_constraint_definition_is_rejected(self) -> None:
        actual = _complete_snapshot()["constraints"]["fk_conversations_counselor_id_users"] | {"on_delete": "NO ACTION"}
        with self.assertRaises(AdoptionValidationError):
            validate_constraint_metadata("fk_conversations_counselor_id_users", actual, EXPECTED_CONSTRAINTS["fk_conversations_counselor_id_users"])

    def test_single_column_check_constraint_is_validated(self) -> None:
        expected = EXPECTED_CONSTRAINTS["ck_check_ins_mood"]
        actual = {
            "table": "check_ins", "constraint_type": "c", "columns": ("mood",),
            "referenced_table": None, "referenced_columns": (), "on_delete": None,
            "validated": True, "deferrable": False, "initially_deferred": False,
            "definition": "CHECK (mood::text = ANY (ARRAY['great'::character varying, 'okay'::character varying, 'low'::character varying, 'stressed'::character varying]::text[]))",
        }
        validate_constraint_metadata("ck_check_ins_mood", actual, expected)

    def test_multi_column_check_constraint_is_validated(self) -> None:
        from migrations.adoption_validation import ConstraintSpec

        expected = ConstraintSpec("example", "c", columns=("start_at", "end_at"), check_columns=("start_at", "end_at"), required_definition_parts=("start_at", "end_at", "<=",))
        actual = {
            "table": "example", "constraint_type": "c", "columns": ("start_at", "end_at"),
            "referenced_table": None, "referenced_columns": (), "on_delete": None,
            "validated": True, "deferrable": False, "initially_deferred": False,
            "definition": "CHECK (start_at <= end_at)",
        }
        validate_constraint_metadata("ck_example_range", actual, expected)

    def test_incomplete_baseline_is_rejected(self) -> None:
        snapshot = _adoption_gap_snapshot()
        snapshot["indexes"].pop("ix_support_cases_student")
        with self.assertRaises(AdoptionValidationError):
            validate_baseline_snapshot(snapshot, allow_adoption_gaps=True)

    def test_known_adoption_gaps_are_allowed_preflight(self) -> None:
        validate_baseline_snapshot(_adoption_gap_snapshot(), allow_adoption_gaps=True)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self, version_exists=False):
        self.version_exists = version_exists
        self.calls = []

    def execute(self, statement):
        sql = str(statement)
        self.calls.append(sql)
        if "to_regclass('public.alembic_version')" in sql:
            return _Result(self.version_exists)
        if "SELECT version_num FROM public.alembic_version" in sql:
            return _Result(adoption.BASELINE_REVISION)
        if "SELECT version_num FROM alembic_version" in sql:
            return _Result(adoption.ADOPTION_REVISION)
        return _Result(None)


class _Engine:
    def __init__(self, connection):
        self.connection = connection
        self.committed = False
        self.rolled_back = False

    def begin(self):
        engine = self

        class Transaction:
            def __enter__(self):
                return engine.connection

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    engine.committed = True
                else:
                    engine.rolled_back = True
                return False

        return Transaction()

    def dispose(self):
        pass


class AdoptionRunnerTests(unittest.TestCase):
    def test_direct_call_requires_exact_confirmation(self) -> None:
        with patch.object(adoption, "create_engine", side_effect=AssertionError("engine must not be created")):
            with self.assertRaises(ValueError):
                adoption.adopt("WRONG")

    def test_existing_alembic_version_is_rejected(self) -> None:
        connection = _Connection(version_exists=True)
        engine = _Engine(connection)
        with patch.object(adoption, "get_database_url", return_value="postgresql://redacted"), patch.object(adoption, "create_engine", return_value=engine):
            with self.assertRaises(RuntimeError):
                adoption.adopt(adoption.CONFIRMATION)
        self.assertFalse(engine.committed)
        self.assertTrue(engine.rolled_back)

    def test_successful_adoption_uses_one_connection_and_commits(self) -> None:
        connection = _Connection(version_exists=False)
        engine = _Engine(connection)
        calls = []

        def stamp(config, revision):
            calls.append(("stamp", revision, config.attributes["connection"]))

        def upgrade(config, revision):
            calls.append(("upgrade", revision, config.attributes["connection"]))

        with patch.object(adoption, "get_database_url", return_value="postgresql://redacted"), patch.object(adoption, "create_engine", return_value=engine), patch.object(adoption.command, "stamp", side_effect=stamp), patch.object(adoption.command, "upgrade", side_effect=upgrade), patch.object(adoption, "capture_schema", return_value=_complete_snapshot()), patch.object(adoption, "validate_baseline_snapshot"):
            adoption.adopt(adoption.CONFIRMATION)
        self.assertTrue(engine.committed)
        self.assertFalse(engine.rolled_back)
        self.assertIs(calls[0][2], calls[1][2])

    def test_failure_rolls_back_adoption_transaction(self) -> None:
        connection = _Connection(version_exists=False)
        engine = _Engine(connection)

        with patch.object(adoption, "get_database_url", return_value="postgresql://redacted"), patch.object(adoption, "create_engine", return_value=engine), patch.object(adoption.command, "stamp"), patch.object(adoption.command, "upgrade", side_effect=RuntimeError("simulated failure")), patch.object(adoption, "capture_schema", return_value=_complete_snapshot()), patch.object(adoption, "validate_baseline_snapshot"):
            with self.assertRaises(RuntimeError):
                adoption.adopt(adoption.CONFIRMATION)
        self.assertFalse(engine.committed)
        self.assertTrue(engine.rolled_back)


if __name__ == "__main__":
    unittest.main()
