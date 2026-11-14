"""Add counselor conversation participants and message read status.

Revision ID: 20261109_03
Revises: 20261109_02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261109_03"
down_revision: Union[str, Sequence[str], None] = "20261109_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("counselor_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("kind", sa.String(length=16), server_default="mannmitra", nullable=False))
        batch_op.create_foreign_key("fk_conversations_counselor_id_users", "users", ["counselor_id"], ["id"], ondelete="CASCADE")
        batch_op.create_check_constraint("ck_conversations_kind", "kind IN ('mannmitra', 'counselor')")
    op.create_index("ix_conversations_counselor_id", "conversations", ["counselor_id"])
    op.create_index("ix_conversations_counselor_kind", "conversations", ["counselor_id", "kind"])

    with op.batch_alter_table("messages", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages", recreate="always") as batch_op:
        batch_op.drop_column("read_at")
    op.drop_index("ix_conversations_counselor_kind", table_name="conversations")
    op.drop_index("ix_conversations_counselor_id", table_name="conversations")
    with op.batch_alter_table("conversations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_conversations_kind", type_="check")
        batch_op.drop_constraint("fk_conversations_counselor_id_users", type_="foreignkey")
        batch_op.drop_column("kind")
        batch_op.drop_column("counselor_id")
