"""Credit cards: payment categories linked to their card, and a system group for them.

Adds ``categories.account_id`` (set only on a card's payment category, whose ``kind`` is
``card_payment``) and ``category_groups.kind`` (``standard``, or ``card_payments`` for the
one system group per user). A card is an account with ``kind = 'credit_card'``; that needs
no schema change. Downgrading drops both columns; it doesn't remove payment categories or
cards, which would then look like ordinary categories and accounts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("category_groups") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(20), nullable=False, server_default="standard")
        )
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint("uq_categories_account_id", ["account_id"])
        batch_op.create_foreign_key(
            "fk_categories_account_id_accounts",
            "accounts",
            ["account_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_constraint("fk_categories_account_id_accounts", type_="foreignkey")
        batch_op.drop_constraint("uq_categories_account_id", type_="unique")
        batch_op.drop_column("account_id")
    with op.batch_alter_table("category_groups") as batch_op:
        batch_op.drop_column("kind")
