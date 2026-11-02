"""Account management: closed accounts, and no silent loss of transactions on delete.

Adds ``accounts.closed``. ``transactions.account_id`` changes from ON DELETE CASCADE to
RESTRICT, so the database refuses to delete an account that still has transactions; the
app only deletes empty accounts. Downgrading restores CASCADE and drops the flag (closed
accounts become open again).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_transactions_account_id_accounts"


def _set_account_fk(ondelete: str) -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(FK_NAME, "accounts", ["account_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    _set_account_fk("RESTRICT")


def downgrade() -> None:
    _set_account_fk("CASCADE")
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("closed")
