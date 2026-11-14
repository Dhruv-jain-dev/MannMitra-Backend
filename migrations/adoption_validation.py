"""Read-only PostgreSQL catalog validation for Supabase adoption."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import inspect, text


class AdoptionValidationError(RuntimeError):
    """Raised when the live schema is not safe to adopt."""


APPLICATION_TABLES = frozenset(
    {
        "users",
        "conversations",
        "messages",
        "message_analyses",
        "check_ins",
        "support_cases",
        "interventions",
        "followups",
    }
)

EXPECTED_COLUMN_NAMES = {
    "users": {"id", "role", "department", "created_at"},
    "conversations": {"id", "user_id", "counselor_id", "kind", "title", "created_at", "updated_at"},
    "messages": {"id", "conversation_id", "position", "role", "content", "client_request_id", "generation_status", "read_at", "reply_to_message_id", "created_at"},
    "message_analyses": {"id", "message_id", "emotion_label", "emotion_score", "emotion_probabilities", "risk_score", "risk_tier", "is_crisis", "stress_score", "voice_metadata", "rag_used", "rag_sources", "created_at"},
    "check_ins": {"id", "user_id", "mood", "stress_level", "notes", "created_at"},
    "support_cases": {"id", "counselor_id", "student_id", "status", "priority", "summary", "details", "next_follow_up", "created_at", "updated_at"},
    "interventions": {"id", "case_id", "counselor_id", "student_id", "title", "details", "status", "created_at", "updated_at"},
    "followups": {"id", "case_id", "counselor_id", "student_id", "title", "due_at", "notes", "status", "created_at", "updated_at"},
}

EXPECTED_COLUMN_DEFINITIONS = {
    "users": {"id": ("character varying(128)", True), "role": ("character varying(16)", True), "department": ("character varying(128)", False), "created_at": ("timestamp with time zone", True)},
    "conversations": {"id": ("character varying(36)", True), "user_id": ("character varying(128)", True), "counselor_id": ("character varying(128)", False), "kind": ("character varying(16)", True), "title": ("character varying(200)", False), "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True)},
    "messages": {"id": ("character varying(36)", True), "conversation_id": ("character varying(36)", True), "position": ("integer", True), "role": ("character varying(16)", True), "content": ("text", True), "client_request_id": ("character varying(128)", False), "generation_status": ("character varying(16)", False), "read_at": ("timestamp with time zone", False), "reply_to_message_id": ("character varying(36)", False), "created_at": ("timestamp with time zone", True)},
    "message_analyses": {"id": ("character varying(36)", True), "message_id": ("character varying(36)", True), "emotion_label": ("character varying(64)", True), "emotion_score": ("double precision", True), "emotion_probabilities": ("json", True), "risk_score": ("double precision", True), "risk_tier": ("character varying(16)", True), "is_crisis": ("boolean", True), "stress_score": ("double precision", False), "voice_metadata": ("json", False), "rag_used": ("boolean", True), "rag_sources": ("json", True), "created_at": ("timestamp with time zone", True)},
    "check_ins": {"id": ("character varying(36)", True), "user_id": ("character varying(128)", True), "mood": ("character varying(16)", True), "stress_level": ("integer", True), "notes": ("character varying(2000)", False), "created_at": ("timestamp with time zone", True)},
    "support_cases": {"id": ("character varying(36)", True), "counselor_id": ("character varying(128)", True), "student_id": ("character varying(128)", True), "status": ("character varying(16)", True), "priority": ("character varying(16)", True), "summary": ("character varying(200)", True), "details": ("character varying(4000)", False), "next_follow_up": ("timestamp with time zone", False), "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True)},
    "interventions": {"id": ("character varying(36)", True), "case_id": ("character varying(36)", True), "counselor_id": ("character varying(128)", True), "student_id": ("character varying(128)", True), "title": ("character varying(200)", True), "details": ("character varying(4000)", False), "status": ("character varying(16)", True), "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True)},
    "followups": {"id": ("character varying(36)", True), "case_id": ("character varying(36)", True), "counselor_id": ("character varying(128)", True), "student_id": ("character varying(128)", True), "title": ("character varying(200)", True), "due_at": ("timestamp with time zone", True), "notes": ("character varying(2000)", False), "status": ("character varying(16)", True), "created_at": ("timestamp with time zone", True), "updated_at": ("timestamp with time zone", True)},
}

ADOPTION_COLUMNS = {
    "users": {"role", "department"},
    "conversations": {"counselor_id", "kind"},
    "messages": {"read_at"},
}

ADOPTION_INDEXES = frozenset(
    {
        "ix_users_role",
        "ix_users_department",
        "ix_conversations_counselor_id",
        "ix_conversations_counselor_kind",
        "ix_message_analyses_message_id",
    }
)


@dataclass(frozen=True)
class IndexSpec:
    table: str
    columns: tuple[str, ...]
    unique: bool = False
    access_method: str = "btree"
    predicate: str | None = None
    expressions: tuple[str, ...] = ()
    included_columns: tuple[str, ...] = ()
    indoption: tuple[int, ...] = ()


@dataclass(frozen=True)
class ConstraintSpec:
    table: str
    constraint_type: str
    columns: tuple[str, ...] = ()
    referenced_table: str | None = None
    referenced_columns: tuple[str, ...] = ()
    on_delete: str | None = None
    check_literals: frozenset[str] = frozenset()
    check_columns: tuple[str, ...] = ()
    required_definition_parts: tuple[str, ...] = ()
    forbidden_definition_parts: tuple[str, ...] = ()
    operator_counts: tuple[tuple[str, int], ...] = ()
    validated: bool = True
    deferrable: bool = False
    initially_deferred: bool = False


EXPECTED_INDEXES = {
    "ix_conversations_user_id": IndexSpec("conversations", ("user_id",)),
    "ix_messages_conversation_id": IndexSpec("messages", ("conversation_id",)),
    "ix_message_analyses_message_id": IndexSpec("message_analyses", ("message_id",)),
    "ix_users_role": IndexSpec("users", ("role",)),
    "ix_users_department": IndexSpec("users", ("department",)),
    "ix_check_ins_user_id": IndexSpec("check_ins", ("user_id",)),
    "ix_check_ins_user_created_at": IndexSpec("check_ins", ("user_id", "created_at")),
    "ix_support_cases_counselor_status": IndexSpec("support_cases", ("counselor_id", "status")),
    "ix_support_cases_student": IndexSpec("support_cases", ("student_id",)),
    "ix_support_cases_follow_up": IndexSpec("support_cases", ("counselor_id", "next_follow_up")),
    "ix_conversations_counselor_id": IndexSpec("conversations", ("counselor_id",)),
    "ix_conversations_counselor_kind": IndexSpec("conversations", ("counselor_id", "kind")),
    "ix_interventions_counselor_status": IndexSpec("interventions", ("counselor_id", "status")),
    "ix_interventions_case": IndexSpec("interventions", ("case_id",)),
    "ix_followups_counselor_status_due": IndexSpec("followups", ("counselor_id", "status", "due_at")),
    "ix_followups_case": IndexSpec("followups", ("case_id",)),
}

EXPECTED_CONSTRAINTS = {
    "ck_users_role": ConstraintSpec("users", "c", check_literals=frozenset({"student", "counselor", "admin"}), check_columns=("role",), forbidden_definition_parts=(" or ", " and ")),
    "ck_check_ins_mood": ConstraintSpec("check_ins", "c", check_literals=frozenset({"great", "okay", "low", "stressed"}), check_columns=("mood",), forbidden_definition_parts=(" or ", " and ")),
    "ck_check_ins_stress_level": ConstraintSpec("check_ins", "c", required_definition_parts=("stress_level", "0", "10", ">=", "<="), forbidden_definition_parts=(" or ",), operator_counts=(("and", 1),)),
    "ck_check_ins_notes_length": ConstraintSpec("check_ins", "c", required_definition_parts=("notes", "2000", "is null", "length"), operator_counts=(("or", 1),)),
    "ck_support_cases_status": ConstraintSpec("support_cases", "c", check_literals=frozenset({"open", "in_progress", "closed"}), check_columns=("status",), forbidden_definition_parts=(" or ", " and ")),
    "ck_support_cases_priority": ConstraintSpec("support_cases", "c", check_literals=frozenset({"stable", "moderate", "priority"}), check_columns=("priority",), forbidden_definition_parts=(" or ", " and ")),
    "ck_conversations_kind": ConstraintSpec("conversations", "c", check_literals=frozenset({"mannmitra", "counselor"}), check_columns=("kind",), forbidden_definition_parts=(" or ", " and ")),
    "ck_interventions_status": ConstraintSpec("interventions", "c", check_literals=frozenset({"planned", "in_progress", "completed", "cancelled"}), check_columns=("status",), forbidden_definition_parts=(" or ", " and ")),
    "ck_followups_status": ConstraintSpec("followups", "c", check_literals=frozenset({"scheduled", "completed", "cancelled"}), check_columns=("status",), forbidden_definition_parts=(" or ", " and ")),
    "fk_conversations_counselor_id_users": ConstraintSpec("conversations", "f", ("counselor_id",), "users", ("id",), "CASCADE"),
}

EXPECTED_FOREIGN_KEYS = {
    ("conversations", ("user_id",), "users", ("id",), "NO ACTION"),
    ("conversations", ("counselor_id",), "users", ("id",), "CASCADE"),
    ("messages", ("conversation_id",), "conversations", ("id",), "NO ACTION"),
    ("messages", ("reply_to_message_id",), "messages", ("id",), "NO ACTION"),
    ("message_analyses", ("message_id",), "messages", ("id",), "NO ACTION"),
    ("check_ins", ("user_id",), "users", ("id",), "CASCADE"),
    ("support_cases", ("counselor_id",), "users", ("id",), "CASCADE"),
    ("support_cases", ("student_id",), "users", ("id",), "CASCADE"),
    ("interventions", ("case_id",), "support_cases", ("id",), "CASCADE"),
    ("interventions", ("counselor_id",), "users", ("id",), "CASCADE"),
    ("interventions", ("student_id",), "users", ("id",), "CASCADE"),
    ("followups", ("case_id",), "support_cases", ("id",), "CASCADE"),
    ("followups", ("counselor_id",), "users", ("id",), "CASCADE"),
    ("followups", ("student_id",), "users", ("id",), "CASCADE"),
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def validate_index_metadata(name: str, actual: dict[str, Any], expected: IndexSpec) -> None:
    if actual.get("table") != expected.table:
        raise AdoptionValidationError(f"Index {name} targets {actual.get('table')!r}, expected {expected.table!r}")
    for key in ("unique", "access_method", "predicate", "expressions", "included_columns"):
        actual_value = actual.get(key)
        expected_value = getattr(expected, key)
        if key in {"predicate"}:
            if _norm(actual_value) != _norm(expected_value):
                raise AdoptionValidationError(f"Index {name} has incompatible {key}")
        elif tuple(actual_value or ()) != tuple(expected_value or ()) if isinstance(expected_value, tuple) else actual_value != expected_value:
            raise AdoptionValidationError(f"Index {name} has incompatible {key}")
    if tuple(actual.get("columns") or ()) != expected.columns:
        raise AdoptionValidationError(f"Index {name} has incompatible key columns")
    expected_options = expected.indoption or (0,) * len(expected.columns)
    if tuple(actual.get("indoption") or ()) != expected_options:
        raise AdoptionValidationError(f"Index {name} has incompatible ordering/null ordering")


def validate_constraint_metadata(name: str, actual: dict[str, Any], expected: ConstraintSpec) -> None:
    for key in ("table", "constraint_type", "columns", "referenced_table", "referenced_columns", "on_delete", "validated", "deferrable", "initially_deferred"):
        if expected.constraint_type == "c" and key == "columns":
            continue
        actual_value = actual.get(key)
        expected_value = getattr(expected, key)
        if key == "on_delete":
            if _norm(actual_value) != _norm(expected_value):
                raise AdoptionValidationError(f"Constraint {name} has incompatible delete action")
        elif tuple(actual_value or ()) != tuple(expected_value or ()) if isinstance(expected_value, tuple) else actual_value != expected_value:
            raise AdoptionValidationError(f"Constraint {name} has incompatible {key}")
    definition = _norm(actual.get("definition"))
    if expected.constraint_type == "c" and expected.check_columns:
        if tuple(actual.get("columns") or ()) != expected.check_columns:
            raise AdoptionValidationError(f"Constraint {name} has incompatible check columns")
    if expected.check_literals:
        literals = frozenset(re.findall(r"'([^']+)'", definition))
        if literals != expected.check_literals:
            raise AdoptionValidationError(f"Constraint {name} has incompatible check values")
    if any(_norm(column) not in definition for column in expected.check_columns):
        raise AdoptionValidationError(f"Constraint {name} has incompatible check columns")
    if any(_norm(part) not in definition for part in expected.required_definition_parts):
        raise AdoptionValidationError(f"Constraint {name} has incompatible definition")
    if any(re.search(rf"\b{re.escape(part.strip())}\b", definition) for part in expected.forbidden_definition_parts):
        raise AdoptionValidationError(f"Constraint {name} has incompatible extra clauses")
    for operator, expected_count in expected.operator_counts:
        if len(re.findall(rf"\b{re.escape(operator)}\b", definition)) != expected_count:
            raise AdoptionValidationError(f"Constraint {name} has incompatible boolean structure")


EXPECTED_PRIMARY_KEYS = {
    "users": ("id",), "conversations": ("id",), "messages": ("id",),
    "message_analyses": ("id",), "check_ins": ("id",), "support_cases": ("id",),
    "interventions": ("id",), "followups": ("id",),
}
EXPECTED_UNIQUES = {
    ("messages", ("conversation_id", "client_request_id")),
    ("messages", ("conversation_id", "position")),
    ("messages", ("reply_to_message_id",)),
    ("message_analyses", ("message_id",)),
}


def validate_baseline_snapshot(snapshot: dict[str, Any], *, allow_adoption_gaps: bool = False) -> None:
    tables = set(snapshot.get("tables", ()))
    missing_tables = APPLICATION_TABLES - tables
    if missing_tables:
        raise AdoptionValidationError(f"Missing required application tables: {sorted(missing_tables)}")

    missing_columns = []
    actual_columns = snapshot.get("columns", {})
    for table, expected_columns in EXPECTED_COLUMN_NAMES.items():
        allowed = ADOPTION_COLUMNS.get(table, set()) if allow_adoption_gaps else set()
        missing_columns.extend(f"{table}.{column}" for column in expected_columns - set(actual_columns.get(table, ())) - allowed)
    if missing_columns:
        raise AdoptionValidationError(f"Missing baseline columns: {sorted(missing_columns)}")
    if "column_details" in snapshot:
        for table, definitions in EXPECTED_COLUMN_DEFINITIONS.items():
            for column, (expected_type, expected_not_null) in definitions.items():
                actual = snapshot["column_details"].get(table, {}).get(column)
                if actual is None:
                    if allow_adoption_gaps and column in ADOPTION_COLUMNS.get(table, set()):
                        continue
                    raise AdoptionValidationError(f"Missing column definition for {table}.{column}")
                if actual["type"] != expected_type or bool(actual["not_null"]) != expected_not_null:
                    raise AdoptionValidationError(f"Incompatible column definition for {table}.{column}")

    missing_indexes = set(EXPECTED_INDEXES) - set(snapshot.get("indexes", {}))
    missing_constraints = set(EXPECTED_CONSTRAINTS) - set(snapshot.get("constraints", {}))
    if allow_adoption_gaps:
        allowed_constraints = {"ck_users_role", "ck_conversations_kind", "fk_conversations_counselor_id_users"}
        missing_indexes -= ADOPTION_INDEXES
        missing_constraints -= allowed_constraints
    if missing_indexes:
        raise AdoptionValidationError(f"Missing baseline indexes: {sorted(missing_indexes)}")
    if missing_constraints:
        raise AdoptionValidationError(f"Missing baseline constraints: {sorted(missing_constraints)}")

    for name, expected in EXPECTED_INDEXES.items():
        actual = snapshot.get("indexes", {}).get(name)
        if actual is not None:
            validate_index_metadata(name, actual, expected)
    for name, expected in EXPECTED_CONSTRAINTS.items():
        actual = snapshot.get("constraints", {}).get(name)
        if actual is not None:
            validate_constraint_metadata(name, actual, expected)

    actual_constraints = list(snapshot.get("constraints", {}).values())
    for table, columns in EXPECTED_PRIMARY_KEYS.items():
        if not any(c["table"] == table and c["constraint_type"] == "p" and tuple(c.get("columns") or ()) == columns for c in actual_constraints):
            raise AdoptionValidationError(f"Missing primary key on {table}({', '.join(columns)})")
    for table, columns in EXPECTED_UNIQUES:
        if not any(c["table"] == table and c["constraint_type"] == "u" and tuple(c.get("columns") or ()) == columns for c in actual_constraints):
            raise AdoptionValidationError(f"Missing unique constraint on {table}({', '.join(columns)})")

    if not allow_adoption_gaps:
        actual_fks = set(snapshot.get("foreign_keys", ()))
        missing_fks = EXPECTED_FOREIGN_KEYS - actual_fks
        if missing_fks:
            raise AdoptionValidationError(f"Missing baseline foreign keys: {sorted(missing_fks)}")
    else:
        actual_fks = set(snapshot.get("foreign_keys", ()))
        adoption_fk = ("conversations", ("counselor_id",), "users", ("id",), "CASCADE")
        missing_fks = EXPECTED_FOREIGN_KEYS - actual_fks - {adoption_fk}
        if missing_fks:
            raise AdoptionValidationError(f"Missing baseline foreign keys: {sorted(missing_fks)}")


def capture_schema(connection) -> dict[str, Any]:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names(schema="public"))
    columns = {
        table: {column["name"] for column in inspector.get_columns(table, schema="public")}
        for table in tables
    }
    column_details = {}
    for row in connection.execute(text(
        """
        SELECT c.relname AS table_name, a.attname AS column_name,
               format_type(a.atttypid, a.atttypmod) AS type_name,
               a.attnotnull AS not_null
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped
        """
    )):
        mapping = row._mapping
        column_details.setdefault(mapping["table_name"], {})[mapping["column_name"]] = {
            "type": mapping["type_name"], "not_null": bool(mapping["not_null"])
        }
    indexes: dict[str, dict[str, Any]] = {}
    for row in connection.execute(text(
        """
        SELECT c.relname AS name, t.relname AS table_name, am.amname AS access_method,
               i.indisunique, i.indnkeyatts, i.indnatts,
               pg_get_expr(i.indpred, i.indrelid) AS predicate,
               pg_get_expr(i.indexprs, i.indrelid) AS expressions,
               i.indoption::text AS indoption,
               ARRAY(SELECT pg_get_indexdef(i.indexrelid, s, true)
                     FROM generate_series(1, i.indnatts) AS s) AS definitions
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_am am ON am.oid = c.relam
        WHERE n.nspname = 'public'
        """
    )):
        mapping = row._mapping
        definitions = tuple(mapping["definitions"] or ())
        key_count = int(mapping["indnkeyatts"])
        indexes[mapping["name"]] = {
            "table": mapping["table_name"],
            "unique": bool(mapping["indisunique"]),
            "access_method": mapping["access_method"],
            "columns": definitions[:key_count],
            "included_columns": definitions[key_count:],
            "predicate": mapping["predicate"],
            "expressions": tuple(mapping["expressions"].split(",")) if mapping["expressions"] else (),
            "indoption": tuple(int(value) for value in re.findall(r"\d+", mapping["indoption"] or "")),
        }

    constraints: dict[str, dict[str, Any]] = {}
    foreign_keys: set[tuple[Any, ...]] = set()
    for row in connection.execute(text(
        """
        SELECT c.conname, t.relname AS table_name, c.contype,
               c.convalidated, c.condeferrable, c.condeferred,
               pg_get_constraintdef(c.oid, true) AS definition,
               rt.relname AS referenced_table,
               CASE c.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'a' THEN 'NO ACTION'
                    WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT' WHEN 'r' THEN 'RESTRICT' END AS on_delete,
               ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                     JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum ORDER BY k.ord) AS columns,
               ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
                     JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum ORDER BY k.ord) AS referenced_columns
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        LEFT JOIN pg_class rt ON rt.oid = c.confrelid
        WHERE n.nspname = 'public'
        """
    )):
        mapping = row._mapping
        actual = {
            "table": mapping["table_name"], "constraint_type": mapping["contype"],
            "columns": tuple(mapping["columns"] or ()), "referenced_table": mapping["referenced_table"],
            "referenced_columns": tuple(mapping["referenced_columns"] or ()), "on_delete": mapping["on_delete"],
            "validated": bool(mapping["convalidated"]), "deferrable": bool(mapping["condeferrable"]),
            "initially_deferred": bool(mapping["condeferred"]), "definition": mapping["definition"],
        }
        constraints[mapping["conname"]] = actual
        if mapping["contype"] == "f":
            foreign_keys.add((mapping["table_name"], tuple(mapping["columns"] or ()), mapping["referenced_table"], tuple(mapping["referenced_columns"] or ()), mapping["on_delete"]))

    return {"tables": tables, "columns": columns, "column_details": column_details, "indexes": indexes, "constraints": constraints, "foreign_keys": foreign_keys}
