"""Add CampusPulse roles and private student check-ins.

Revision ID: 20261109_01
Revises: 20261109_00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261109_01"
down_revision: Union[str, Sequence[str], None] = "20261109_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode keeps this migration compatible with SQLite, whose ALTER
    # TABLE support cannot add/drop named constraints directly.
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(length=16), server_default="student", nullable=False))
        batch_op.create_check_constraint("ck_users_role", "role IN ('student', 'counselor', 'admin')")
    op.create_index("ix_users_role", "users", ["role"])

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


def downgrade() -> None:
    op.drop_index("ix_check_ins_user_created_at", table_name="check_ins")
    op.drop_index("ix_check_ins_user_id", table_name="check_ins")
    op.drop_table("check_ins")
    op.drop_index("ix_users_role", table_name="users")
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.drop_column("role")
