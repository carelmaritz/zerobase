"""Category targets.

Adds the ``targets`` table: at most one per category (monthly amount, target balance, or
target balance by a month). Downgrading drops it; nothing else refers to it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_targets_category_id_categories",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_targets_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_targets"),
        sa.UniqueConstraint("category_id", name="uq_targets_category_id"),
    )
    op.create_index("ix_targets_user_id", "targets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_targets_user_id", table_name="targets")
    op.drop_table("targets")
