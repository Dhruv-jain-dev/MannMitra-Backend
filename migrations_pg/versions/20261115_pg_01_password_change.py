"""Track mandatory first-login password changes for temporary accounts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261115_pg_01_password_change"
down_revision: Union[str, Sequence[str], None] = "20261114_pg_00_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("password_change_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_change_requested_at")
    op.drop_column("users", "must_change_password")
