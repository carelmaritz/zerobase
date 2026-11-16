"""Investment accounts (TASK-M007).

Adds ``accounts.symbol`` (a crypto account's coin, e.g. BTC) and ``accounts.quantity``
(the amount held, stored as exact decimal text). The new account kinds need no schema
change. Downgrading drops both columns; the accounts themselves are unchanged.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-13 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(sa.Column("symbol", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("quantity", sa.String(48), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("quantity")
        batch_op.drop_column("symbol")
