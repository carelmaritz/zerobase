"""Scheduled transactions, and yearly repeating targets.

Adds the ``scheduled_transactions`` table; ``transactions.schedule_id`` and
``scheduled_for`` (unique together: one row per schedule and due date); and
``targets.repeats``. Downgrading drops them; entered transactions stay, as ordinary ones.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("transfer_account_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("transfer_category_id", sa.Integer(), nullable=True),
        sa.Column("payee", sa.String(100), nullable=False),
        sa.Column("memo", sa.String(255), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("next_due", sa.Date(), nullable=False),
        sa.Column("save_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_scheduled_transactions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_scheduled_transactions_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_account_id"],
            ["accounts.id"],
            name="fk_scheduled_transactions_transfer_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_scheduled_transactions_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_category_id"],
            ["categories.id"],
            name="fk_scheduled_transactions_transfer_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_transactions"),
    )
    op.create_index(
        "ix_scheduled_transactions_user_next_due",
        "scheduled_transactions",
        ["user_id", "next_due"],
    )
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("schedule_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("scheduled_for", sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transactions_schedule_id_scheduled_transactions",
            "scheduled_transactions",
            ["schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_transactions_schedule_occurrence", ["schedule_id", "scheduled_for"]
        )
    with op.batch_alter_table("targets") as batch_op:
        batch_op.add_column(
            sa.Column("repeats", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("targets") as batch_op:
        batch_op.drop_column("repeats")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("uq_transactions_schedule_occurrence", type_="unique")
        batch_op.drop_constraint(
            "fk_transactions_schedule_id_scheduled_transactions", type_="foreignkey"
        )
        batch_op.drop_column("scheduled_for")
        batch_op.drop_column("schedule_id")
    op.drop_index("ix_scheduled_transactions_user_next_due", table_name="scheduled_transactions")
    op.drop_table("scheduled_transactions")
