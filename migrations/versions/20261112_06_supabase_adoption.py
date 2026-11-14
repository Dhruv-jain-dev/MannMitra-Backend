"""Adopt the existing Supabase schema without recreating application tables.

Revision ID: 20261112_06
Revises: 20261110_05
"""

from typing import Sequence, Union

from alembic import op
from migrations.adoption_validation import capture_schema, validate_baseline_snapshot


revision: str = "20261112_06"
down_revision: Union[str, Sequence[str], None] = "20261110_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _required_tables_sql() -> str:
    return """
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'users', 'conversations', 'messages', 'message_analyses',
        'check_ins', 'support_cases', 'interventions', 'followups'
    ] LOOP
        IF to_regclass('public.' || table_name) IS NULL THEN
            RAISE EXCEPTION 'Required existing table public.% is missing; adoption is aborted', table_name;
        END IF;
    END LOOP;
END
$$;
"""


def _column_sql(
    table: str,
    column: str,
    add_definition: str,
    expected_type: str,
    expected_not_null: bool,
    expected_default_fragment: str | None = None,
) -> str:
    expected_not_null_sql = "true" if expected_not_null else "false"
    escaped_add_definition = add_definition.replace("'", "''")
    default_check = ""
    if expected_default_fragment:
        default_check = f"""
        IF position('{expected_default_fragment.lower()}' IN lower(actual_default)) = 0 THEN
            RAISE EXCEPTION 'Existing public.{table}.{column} has an incompatible default: %', actual_default;
        END IF;
"""
    return f"""
DO $$
DECLARE
    actual_type text;
    actual_not_null boolean;
    actual_default text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_attribute
        WHERE attrelid = to_regclass('public.{table}')
          AND attname = '{column}'
          AND attnum > 0
          AND NOT attisdropped
    ) THEN
        EXECUTE 'ALTER TABLE public.{table} ADD COLUMN {escaped_add_definition}';
    ELSE
        SELECT format_type(a.atttypid, a.atttypmod),
               a.attnotnull,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '')
        INTO actual_type, actual_not_null, actual_default
        FROM pg_attribute AS a
        LEFT JOIN pg_attrdef AS d
          ON d.adrelid = a.attrelid
         AND d.adnum = a.attnum
        WHERE a.attrelid = to_regclass('public.{table}')
          AND a.attname = '{column}'
          AND a.attnum > 0
          AND NOT a.attisdropped;

        IF actual_type <> '{expected_type}'
           OR actual_not_null IS DISTINCT FROM {expected_not_null_sql} THEN
            RAISE EXCEPTION 'Existing public.{table}.{column} has an incompatible definition: type %, not_null %', actual_type, actual_not_null;
        END IF;
{default_check}    END IF;
END
$$;
"""


def _constraint_sql(table: str, name: str, constraint_type: str, fragments: tuple[str, ...], ddl: str) -> str:
    fragment_checks = " AND ".join(
        f"position('{fragment.lower()}' IN lower(actual_definition)) > 0" for fragment in fragments
    )
    return f"""
DO $$
DECLARE
    actual_type "char";
    actual_definition text;
BEGIN
    SELECT c.contype, pg_get_constraintdef(c.oid)
    INTO actual_type, actual_definition
    FROM pg_constraint AS c
    WHERE c.conrelid = to_regclass('public.{table}')
      AND c.conname = '{name}';

    IF actual_type IS NULL THEN
        EXECUTE '{ddl}';
    ELSIF actual_type <> '{constraint_type}'
       OR NOT ({fragment_checks}) THEN
        RAISE EXCEPTION 'Existing constraint public.{table}.{name} does not match the adoption definition: %', actual_definition;
    END IF;
END
$$;
"""


def _index_sql(table: str, name: str, columns: tuple[str, ...]) -> str:
    expected_columns = "(" + ", ".join(columns) + ")"
    return f"""
DO $$
DECLARE
    actual_definition text;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid)
    INTO actual_definition
    FROM pg_index AS i
    JOIN pg_class AS c ON c.oid = i.indexrelid
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = '{name}';

    IF actual_definition IS NULL THEN
        EXECUTE 'CREATE INDEX {name} ON public.{table} {expected_columns}';
    ELSIF position('public.{table}' IN lower(actual_definition)) = 0
       OR position('{expected_columns}' IN lower(actual_definition)) = 0 THEN
        RAISE EXCEPTION 'Existing index public.{name} does not match the adoption definition: %', actual_definition;
    END IF;
END
$$;
"""


def _offline_mode() -> bool:
    return bool(op.get_context().as_sql)


def upgrade() -> None:
    connection = op.get_bind()
    if not _offline_mode():
        validate_baseline_snapshot(capture_schema(connection), allow_adoption_gaps=True)

    op.execute(_required_tables_sql())

    # The six existing users receive student through this server default.
    # Counselor/admin provisioning remains an authorized backend operation.
    op.execute(_column_sql("users", "role", '"role" varchar(16) NOT NULL DEFAULT \'student\'', "character varying(16)", True, "student"))
    op.execute(_column_sql("users", "department", '"department" varchar(128)', "character varying(128)", False))
    op.execute(_column_sql("conversations", "counselor_id", '"counselor_id" varchar(128)', "character varying(128)", False))
    op.execute(_column_sql("conversations", "kind", '"kind" varchar(16) NOT NULL DEFAULT \'mannmitra\'', "character varying(16)", True, "mannmitra"))
    op.execute(_column_sql("messages", "read_at", '"read_at" timestamp with time zone', "timestamp with time zone", False))

    op.execute(_constraint_sql(
        "users", "ck_users_role", "c", ("role", "student", "counselor", "admin"),
        "ALTER TABLE public.users ADD CONSTRAINT ck_users_role CHECK (role IN (''student'', ''counselor'', ''admin''))",
    ))
    op.execute(_constraint_sql(
        "conversations", "ck_conversations_kind", "c", ("kind", "mannmitra", "counselor"),
        "ALTER TABLE public.conversations ADD CONSTRAINT ck_conversations_kind CHECK (kind IN (''mannmitra'', ''counselor''))",
    ))
    op.execute(_constraint_sql(
        "conversations", "fk_conversations_counselor_id_users", "f",
        ("foreign key", "counselor_id", "users", "on delete cascade"),
        "ALTER TABLE public.conversations ADD CONSTRAINT fk_conversations_counselor_id_users "
        "FOREIGN KEY (counselor_id) REFERENCES public.users(id) ON DELETE CASCADE",
    ))

    op.execute(_index_sql("users", "ix_users_role", ("role",)))
    op.execute(_index_sql("users", "ix_users_department", ("department",)))
    op.execute(_index_sql("conversations", "ix_conversations_counselor_id", ("counselor_id",)))
    op.execute(_index_sql("conversations", "ix_conversations_counselor_kind", ("counselor_id", "kind")))
    op.execute(_index_sql("message_analyses", "ix_message_analyses_message_id", ("message_id",)))

    if not _offline_mode():
        validate_baseline_snapshot(capture_schema(connection), allow_adoption_gaps=False)


def downgrade() -> None:
    raise RuntimeError("20261112_06_supabase_adoption is forward-only and has no destructive downgrade")
