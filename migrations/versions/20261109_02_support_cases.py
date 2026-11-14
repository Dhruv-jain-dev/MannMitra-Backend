"""Add counselor-owned support cases.

Revision ID: 20261109_02
Revises: 20261109_01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261109_02"
down_revision: Union[str, Sequence[str], None] = "20261109_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_support_cases_follow_up", table_name="support_cases")
    op.drop_index("ix_support_cases_student", table_name="support_cases")
    op.drop_index("ix_support_cases_counselor_status", table_name="support_cases")
    op.drop_table("support_cases")
