"""Statement imports: an import ID on transactions, and saved import settings per account.

Adds ``transactions.import_id`` (unique per account; NULL for typed-in transactions) and
the ``import_mappings`` table. Downgrading drops both; imported transactions stay, as
ordinary ones.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-07 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("import_id", sa.String(255), nullable=True))
        batch_op.create_unique_constraint(
            "uq_transactions_account_import_id", ["account_id", "import_id"]
        )
    op.create_table(
        "import_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_import_mappings_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_import_mappings_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_mappings"),
        sa.UniqueConstraint("account_id", name="uq_import_mappings_account_id"),
    )
    op.create_index("ix_import_mappings_user_id", "import_mappings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_import_mappings_user_id", table_name="import_mappings")
    op.drop_table("import_mappings")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint("uq_transactions_account_import_id", type_="unique")
        batch_op.drop_column("import_id")
