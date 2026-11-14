"""Add persistent counselor interventions and follow-ups.

Revision ID: 20261109_04
Revises: 20261109_03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261109_04"
down_revision: Union[str, Sequence[str], None] = "20261109_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.drop_index("ix_followups_case", table_name="followups")
    op.drop_index("ix_followups_counselor_status_due", table_name="followups")
    op.drop_table("followups")
    op.drop_index("ix_interventions_case", table_name="interventions")
    op.drop_index("ix_interventions_counselor_status", table_name="interventions")
    op.drop_table("interventions")
