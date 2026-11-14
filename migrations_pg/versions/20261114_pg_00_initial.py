"""Create the clean PostgreSQL MannMitra/CampusPulse schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261114_pg_00_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("postgresql_fresh",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="student", nullable=False),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('student', 'counselor', 'admin')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_department", "users", ["department"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("counselor_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), server_default="mannmitra", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('mannmitra', 'counselor')", name="ck_conversations_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["counselor_id"], ["users.id"], name="fk_conversations_counselor_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_counselor_id", "conversations", ["counselor_id"])
    op.create_index("ix_conversations_counselor_kind", "conversations", ["counselor_id", "kind"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=True),
        sa.Column("generation_status", sa.String(length=16), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_to_message_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["reply_to_message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "client_request_id", name="uq_message_request_per_conversation"),
        sa.UniqueConstraint("conversation_id", "position", name="uq_message_position_per_conversation"),
        sa.UniqueConstraint("reply_to_message_id", name="uq_messages_reply_to_message_id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "message_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("emotion_label", sa.String(length=64), nullable=False),
        sa.Column("emotion_score", sa.Float(), nullable=False),
        sa.Column("emotion_probabilities", sa.JSON(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("is_crisis", sa.Boolean(), nullable=False),
        sa.Column("stress_score", sa.Float(), nullable=True),
        sa.Column("voice_metadata", sa.JSON(), nullable=True),
        sa.Column("rag_used", sa.Boolean(), nullable=False),
        sa.Column("rag_sources", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_message_analyses_message_id", "message_analyses", ["message_id"])

    op.create_table(
        "check_ins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("mood", sa.String(length=16), nullable=False),
        sa.Column("stress_level", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mood IN ('great', 'okay', 'low', 'stressed')", name="ck_check_ins_mood"),
        sa.CheckConstraint("stress_level BETWEEN 0 AND 10", name="ck_check_ins_stress_level"),
        sa.CheckConstraint("notes IS NULL OR length(notes) <= 2000", name="ck_check_ins_notes_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_ins_user_id", "check_ins", ["user_id"])
    op.create_index("ix_check_ins_user_created_at", "check_ins", ["user_id", "created_at"])

    op.create_table(
        "support_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counselor_id", sa.String(length=128), nullable=False),
        sa.Column("student_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("priority", sa.String(length=16), server_default="moderate", nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column("details", sa.String(length=4000), nullable=True),
        sa.Column("next_follow_up", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'closed')", name="ck_support_cases_status"),
        sa.CheckConstraint("priority IN ('stable', 'moderate', 'priority')", name="ck_support_cases_priority"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_cases_counselor_status", "support_cases", ["counselor_id", "status"])
    op.create_index("ix_support_cases_student", "support_cases", ["student_id"])
    op.create_index("ix_support_cases_follow_up", "support_cases", ["counselor_id", "next_follow_up"])

    op.create_table(
        "interventions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("counselor_id", sa.String(length=128), nullable=False),
        sa.Column("student_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.String(length=4000), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="planned", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_interventions_status"),
        sa.ForeignKeyConstraint(["case_id"], ["support_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interventions_counselor_status", "interventions", ["counselor_id", "status"])
    op.create_index("ix_interventions_case", "interventions", ["case_id"])

    op.create_table(
        "followups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("counselor_id", sa.String(length=128), nullable=False),
        sa.Column("student_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="scheduled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_followups_status"),
        sa.ForeignKeyConstraint(["case_id"], ["support_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_followups_counselor_status_due", "followups", ["counselor_id", "status", "due_at"])
    op.create_index("ix_followups_case", "followups", ["case_id"])


def downgrade() -> None:
    op.drop_table("followups")
    op.drop_table("interventions")
    op.drop_table("support_cases")
    op.drop_table("check_ins")
    op.drop_table("message_analyses")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
