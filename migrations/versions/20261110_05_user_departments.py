"""Add optional user department for aggregate analytics.

Revision ID: 20261110_05
Revises: 20261109_04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261110_05"
down_revision: Union[str, Sequence[str], None] = "20261109_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("department", sa.String(length=128), nullable=True))
    op.create_index("ix_users_department", "users", ["department"])


def downgrade() -> None:
    op.drop_index("ix_users_department", table_name="users")
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.drop_column("department")
