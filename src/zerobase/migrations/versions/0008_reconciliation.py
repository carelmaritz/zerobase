"""Cleared status and reconciliation.

Adds ``transactions.status`` (``uncleared``, ``cleared`` or ``reconciled``; existing rows
start uncleared) and ``accounts.reconciled_on`` (the date an account was last reconciled).
Downgrading drops both; the transactions themselves are unchanged.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-08 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(12), nullable=False, server_default="uncleared")
        )
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(sa.Column("reconciled_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("reconciled_on")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("status")
