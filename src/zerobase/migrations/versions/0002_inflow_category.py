"""Explicit "Inflow: Ready to Assign" category.

Income used to be any on-budget transaction with no category and a positive amount. Each
user now gets one built-in inflow category, and that income moves into it, so Ready to
Assign is unchanged.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

users = sa.table("users", sa.column("id", sa.Integer))
accounts = sa.table("accounts", sa.column("id", sa.Integer), sa.column("on_budget", sa.Boolean))
categories = sa.table(
    "categories",
    sa.column("id", sa.Integer),
    sa.column("user_id", sa.Integer),
    sa.column("group_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("sort_order", sa.Integer),
    sa.column("kind", sa.String),
)
transactions = sa.table(
    "transactions",
    sa.column("user_id", sa.Integer),
    sa.column("account_id", sa.Integer),
    sa.column("category_id", sa.Integer),
    sa.column("amount", sa.BigInteger),
)


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=20), server_default="standard", nullable=False)
        )
        batch_op.alter_column("group_id", existing_type=sa.Integer(), nullable=True)

    op.execute(
        categories.insert().from_select(
            ["user_id", "group_id", "name", "sort_order", "kind"],
            sa.select(
                users.c.id,
                sa.null(),
                sa.literal("Ready to Assign"),
                sa.literal(0),
                sa.literal("inflow"),
            ),
        )
    )
    inflow_id = (
        sa.select(categories.c.id)
        .where(categories.c.user_id == transactions.c.user_id, categories.c.kind == "inflow")
        .scalar_subquery()
    )
    on_budget_accounts = sa.select(accounts.c.id).where(accounts.c.on_budget.is_(True))
    op.execute(
        transactions.update()
        .where(
            transactions.c.category_id.is_(None),
            transactions.c.amount > 0,
            transactions.c.account_id.in_(on_budget_accounts),
        )
        .values(category_id=inflow_id)
    )


def downgrade() -> None:
    inflow_ids = sa.select(categories.c.id).where(categories.c.kind == "inflow")
    op.execute(
        transactions.update()
        .where(transactions.c.category_id.in_(inflow_ids))
        .values(category_id=None)
    )
    op.execute(categories.delete().where(categories.c.kind == "inflow"))
    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column("group_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("kind")
