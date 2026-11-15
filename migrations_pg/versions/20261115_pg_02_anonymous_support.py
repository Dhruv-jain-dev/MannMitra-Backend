"""Add isolated pseudonymous student-to-counselor support."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261115_pg_02_anonymous_support"
down_revision: Union[str, Sequence[str], None] = "20261115_pg_01_password_change"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anonymous_support_conversations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("student_user_id", sa.String(128), nullable=False),
        sa.Column("assigned_counselor_id", sa.String(128), nullable=True),
        sa.Column("anonymous_alias", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("urgency", sa.String(16), server_default="moderate", nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("category IN ('emotional_support', 'academic', 'safety', 'other')", name="ck_anon_support_category"),
        sa.CheckConstraint("urgency IN ('stable', 'moderate', 'urgent')", name="ck_anon_support_urgency"),
        sa.CheckConstraint("status IN ('pending', 'active', 'closed')", name="ck_anon_support_status"),
        sa.ForeignKeyConstraint(["student_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_counselor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anonymous_alias", name="uq_anon_support_alias"),
    )
    op.create_index("ix_anon_support_student_status", "anonymous_support_conversations", ["student_user_id", "status"])
    op.create_index("ix_anon_support_counselor_status", "anonymous_support_conversations", ["assigned_counselor_id", "status"])
    op.create_index("ix_anon_support_status_created", "anonymous_support_conversations", ["status", "created_at"])

    op.create_table(
        "anonymous_support_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sender_role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["anonymous_support_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "position", name="uq_anon_support_message_position"),
    )
    op.create_index("ix_anon_support_messages_conversation", "anonymous_support_messages", ["conversation_id", "position"])

    op.create_table(
        "anonymous_support_notes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("counselor_id", sa.String(128), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["anonymous_support_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anon_support_notes_conversation", "anonymous_support_notes", ["conversation_id", "created_at"])

    op.create_table(
        "anonymous_support_followups",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("counselor_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="scheduled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_anon_support_followup_status"),
        sa.ForeignKeyConstraint(["conversation_id"], ["anonymous_support_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anon_support_followups_counselor_due", "anonymous_support_followups", ["counselor_id", "status", "due_at"])

    op.create_table(
        "anonymous_support_audit_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["anonymous_support_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anon_support_audit_conversation_created", "anonymous_support_audit_events", ["conversation_id", "created_at"])

    # These policies are for Supabase/PostgREST contexts that provide the
    # standard request.jwt.claim.sub setting. The backend still performs the
    # authoritative checks because its custom JWT is not auth.uid().
    # SQLite compatibility tests exercise the table DDL only.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE anonymous_support_conversations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE anonymous_support_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE anonymous_support_notes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE anonymous_support_followups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE anonymous_support_audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY anon_support_conversation_read ON anonymous_support_conversations
        FOR SELECT USING (student_user_id = current_setting('request.jwt.claim.sub', true)
            OR assigned_counselor_id = current_setting('request.jwt.claim.sub', true))""")
    op.execute("""CREATE POLICY anon_support_conversation_student_create ON anonymous_support_conversations
        FOR INSERT WITH CHECK (student_user_id = current_setting('request.jwt.claim.sub', true)
            AND assigned_counselor_id IS NULL
            AND EXISTS (SELECT 1 FROM users u
                WHERE u.id = current_setting('request.jwt.claim.sub', true)
                AND u.role = 'student'))""")
    op.execute("""CREATE POLICY anon_support_conversation_counselor_manage ON anonymous_support_conversations
        FOR UPDATE USING (
            assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
            OR (assigned_counselor_id IS NULL AND status = 'pending'
                AND EXISTS (SELECT 1 FROM users u WHERE u.id = current_setting('request.jwt.claim.sub', true) AND u.role = 'counselor')))
        WITH CHECK (assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
            AND EXISTS (SELECT 1 FROM users u WHERE u.id = current_setting('request.jwt.claim.sub', true) AND u.role = 'counselor'))""")
    op.execute("""CREATE POLICY anon_support_messages_read ON anonymous_support_messages
        FOR SELECT USING (EXISTS (SELECT 1 FROM anonymous_support_conversations c
            WHERE c.id = conversation_id AND (c.student_user_id = current_setting('request.jwt.claim.sub', true)
                OR c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true))))""")
    op.execute("""CREATE POLICY anon_support_messages_student_insert ON anonymous_support_messages
        FOR INSERT WITH CHECK (sender_role = 'student' AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
            JOIN users u ON u.id = c.student_user_id
            WHERE c.id = conversation_id
                AND c.student_user_id = current_setting('request.jwt.claim.sub', true)
                AND u.role = 'student'))""")
    op.execute("""CREATE POLICY anon_support_messages_counselor_insert ON anonymous_support_messages
        FOR INSERT WITH CHECK (sender_role = 'counselor' AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
            JOIN users u ON u.id = c.assigned_counselor_id
            WHERE c.id = conversation_id
                AND c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
                AND u.role = 'counselor'))""")
    op.execute("""CREATE POLICY anon_support_notes_counselor ON anonymous_support_notes
        USING (counselor_id = current_setting('request.jwt.claim.sub', true)
            AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
                JOIN users u ON u.id = c.assigned_counselor_id
                WHERE c.id = conversation_id
                    AND c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
                    AND u.role = 'counselor'))
        WITH CHECK (counselor_id = current_setting('request.jwt.claim.sub', true)
            AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
                JOIN users u ON u.id = c.assigned_counselor_id
                WHERE c.id = conversation_id
                    AND c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
                    AND u.role = 'counselor'))""")
    op.execute("""CREATE POLICY anon_support_followups_counselor ON anonymous_support_followups
        USING (counselor_id = current_setting('request.jwt.claim.sub', true)
            AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
                JOIN users u ON u.id = c.assigned_counselor_id
                WHERE c.id = conversation_id
                    AND c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
                    AND u.role = 'counselor'))
        WITH CHECK (counselor_id = current_setting('request.jwt.claim.sub', true)
            AND EXISTS (SELECT 1 FROM anonymous_support_conversations c
                JOIN users u ON u.id = c.assigned_counselor_id
                WHERE c.id = conversation_id
                    AND c.assigned_counselor_id = current_setting('request.jwt.claim.sub', true)
                    AND u.role = 'counselor'))""")
    # No policy is created for anonymous_support_audit_events. With RLS
    # enabled this is intentional default-deny for browser/PostgREST roles.
    # Only the authorized backend audit workflow may access raw actor IDs.


def downgrade() -> None:
    for table in ("anonymous_support_audit_events", "anonymous_support_followups", "anonymous_support_notes", "anonymous_support_messages", "anonymous_support_conversations"):
        op.drop_table(table)
