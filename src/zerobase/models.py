"""Database models.

All money is stored as signed integers in minor units (pence/cents), never floats.
Every row belongs to a user, and every query filters on ``user_id``.
"""

from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="checking")
    # Budget accounts feed the envelopes; tracking accounts are balance-only.
    on_budget: Mapped[bool] = mapped_column(Boolean, default=True)


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(default=0)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Only the built-in inflow category has no group.
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(default=0)
    # "standard" envelopes, or "inflow": the one per-user "Inflow: Ready to Assign" category.
    # Transactions in it are income; it is never shown in the budget or assigned to.
    kind: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")

    group: Mapped[CategoryGroup | None] = relationship()

    @property
    def is_inflow(self) -> bool:
        return self.kind == "inflow"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_user_date", "user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    # The inflow category means income (Ready to Assign). NULL means not categorised yet:
    # it counts nowhere in the budget and is flagged in the UI.
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date)
    payee: Mapped[str] = mapped_column(String(100), default="")
    memo: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[int] = mapped_column(BigInteger)  # signed minor units
    # A transfer is two transactions, one per account, each pointing at the other.
    # The app deletes both legs together; SET NULL only stops a stray delete leaving a
    # dangling ID.
    transfer_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    account: Mapped[Account] = relationship()
    category: Mapped[Category | None] = relationship()
    # Read-only: routers set transfer_id directly, since the two legs refer to each other.
    transfer: Mapped["Transaction | None"] = relationship(
        remote_side="Transaction.id", foreign_keys=[transfer_id], viewonly=True
    )

    @property
    def takes_category(self) -> bool:
        """Only a budget-account leg can have a category, and not if money stays in the budget.

        That is, not on a transfer between two budget accounts. Needs ``transfer`` loaded.
        """
        if not self.account.on_budget:
            return False
        return self.transfer is None or not self.transfer.account.on_budget


class Assignment(Base):
    """Money assigned to a category in a given month (``month`` is always the 1st)."""

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("category_id", "month", name="uq_assignment_cat_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    month: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
