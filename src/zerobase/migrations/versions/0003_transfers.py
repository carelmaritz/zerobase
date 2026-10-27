"""Transfers between accounts.

A transfer is two transactions, one in each account, linked by ``transfer_id`` pointing
at the other leg. Downgrading drops the link and leaves the legs as plain transactions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("transfer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_transactions_transfer_id_transactions"),
            "transactions",
            ["transfer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_transactions_transfer_id"), ["transfer_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_transactions_transfer_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_transactions_transfer_id_transactions"), type_="foreignkey"
        )
        batch_op.drop_column("transfer_id")
