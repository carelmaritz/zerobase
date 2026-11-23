"""Mark starting balances (TASK-M003).

Adds ``transactions.is_starting``, so reports can keep starting balances out of income
whatever their payee says. Existing rows are matched by the payee the app gave them, unless
they are a transfer or in an ordinary category. Downgrading drops the column only.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("is_starting", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        sa.text(
            "UPDATE transactions SET is_starting = :yes WHERE payee = 'Starting balance' "
            "AND transfer_id IS NULL AND schedule_id IS NULL AND (category_id IS NULL OR "
            "category_id IN (SELECT id FROM categories WHERE kind <> 'standard'))"
        ).bindparams(sa.bindparam("yes", True, sa.Boolean()))
    )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("is_starting")
