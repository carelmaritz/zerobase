"""Category management: hidden categories, and no silent uncategorising on delete.

Adds ``categories.hidden``. ``transactions.category_id`` changes from ON DELETE SET NULL
to RESTRICT, so the database refuses to delete a category that still has transactions;
the app moves them to another category first. Downgrading restores SET NULL and drops
the flag (hidden categories become visible again).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_transactions_category_id_categories"


def _set_category_fk(ondelete: str) -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_NAME, "categories", ["category_id"], ["id"], ondelete=ondelete
        )


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(
            sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    _set_category_fk("RESTRICT")


def downgrade() -> None:
    _set_category_fk("SET NULL")
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("hidden")
