"""Database models.

All money is stored as signed integers in minor units (pence/cents), never floats.
Every row belongs to a user, and every query filters on ``user_id``.
"""

import datetime as dt
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
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


CREDIT_CARD = "credit_card"  # Account.kind of a credit card: always a budget account

# Transaction.status: seen on a bank statement (cleared), and then confirmed against the
# bank's balance and locked (reconciled). See TASK-M006.
UNCLEARED, CLEARED, RECONCILED = "uncleared", "cleared", "reconciled"
STATUSES = (UNCLEARED, CLEARED, RECONCILED)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="checking")
    # Budget accounts feed the envelopes; tracking accounts are balance-only.
    on_budget: Mapped[bool] = mapped_column(Boolean, default=True)
    # Closed accounts (zero balance) drop out of the pickers and the main list, but their
    # history still counts.
    closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # When the cleared balance was last confirmed against the bank's. NULL: never.
    reconciled_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    @property
    def is_credit_card(self) -> bool:
        return self.kind == CREDIT_CARD


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(default=0)
    # "standard", or "card_payments": the one per-user system group for card payment
    # categories, which the category management routes leave alone.
    kind: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")


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
    # "standard" envelopes; "inflow": the one per-user "Inflow: Ready to Assign" category
    # (transactions in it are income; it is never shown in the budget or assigned to); or
    # "card_payment": a credit card's payment category, linked by ``account_id``.
    kind: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")
    # The card whose payment category this is. RESTRICT: the app deletes it with the card.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    # Hidden categories drop out of the budget's groups and the pickers but still count.
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    group: Mapped[CategoryGroup | None] = relationship()

    @property
    def is_inflow(self) -> bool:
        return self.kind == "inflow"

    @property
    def is_card_payment(self) -> bool:
        return self.kind == "card_payment"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "date"),
        # Imported rows carry an ID from the statement, so re-importing adds nothing twice.
        UniqueConstraint("account_id", "import_id", name="uq_transactions_account_import_id"),
        # One row per schedule and due date, so two requests can't enter it twice (M002).
        UniqueConstraint(
            "schedule_id", "scheduled_for", name="uq_transactions_schedule_occurrence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # RESTRICT: only an account with no transactions can be deleted.
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    # The inflow category means income (Ready to Assign). NULL means not categorised yet:
    # it counts nowhere in the budget and is flagged in the UI. RESTRICT: deleting a
    # category must move its transactions elsewhere first (``budget.merge_category``).
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
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
    # Set on imported transactions (and on hand-entered ones an import matched): see
    # ``importer``. NULL for anything typed in and never matched.
    import_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=UNCLEARED, server_default=UNCLEARED)
    # Entered from a schedule: which one, and the due date it was for. Only one leg of a
    # scheduled transfer carries them. SET NULL: deleting a schedule keeps what it entered
    # (the app also clears them, as SQLite doesn't enforce foreign keys here).
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_transactions.id", ondelete="SET NULL"), nullable=True
    )
    # dt.date: inside this class, "date" is the column above.
    scheduled_for: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

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


# Target.kind (TASK-M001): assign an amount every month; have a balance; or have a
# balance by a month (``Target.month``).
MONTHLY, BALANCE, BY_DATE = "monthly", "balance", "by_date"
TARGET_KINDS = (MONTHLY, BALANCE, BY_DATE)


class Target(Base):
    """A category's target (at most one per category). See ``budget.underfunded``.

    CASCADE: deleted with its category (the app also deletes it, as SQLite doesn't
    enforce foreign keys here).
    """

    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), unique=True
    )
    kind: Mapped[str] = mapped_column(String(12))
    amount: Mapped[int] = mapped_column(BigInteger)  # positive minor units
    # BY_DATE only: the month (the 1st) the balance should be reached by. NULL otherwise.
    month: Mapped[date | None] = mapped_column(Date, nullable=True)
    # BY_DATE only: the same month every year (an annual bill, TASK-M002).
    repeats: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class ScheduledTransaction(Base):
    """A transaction entered automatically when due (TASK-M002). See ``schedules``.

    The fields match a checked transaction form (``entry.ValidTransaction``): ``amount``
    is from ``account_id``'s side, and a transfer's budget-leg category is in
    ``category_id`` or ``transfer_category_id``. Accounts: CASCADE, but the app deletes
    schedules itself (SQLite). Categories: RESTRICT, as for transactions; merging moves
    them.
    """

    __tablename__ = "scheduled_transactions"
    __table_args__ = (Index("ix_scheduled_transactions_user_next_due", "user_id", "next_due"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    transfer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    transfer_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    payee: Mapped[str] = mapped_column(String(100), default="")
    memo: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[int] = mapped_column(BigInteger)  # signed minor units, never 0
    unit: Mapped[str] = mapped_column(String(8))  # schedules.UNITS
    interval: Mapped[int] = mapped_column(default=1)
    day: Mapped[int] = mapped_column()  # day of the month that monthly/yearly ones keep
    next_due: Mapped[date] = mapped_column(Date)
    # Yearly only: keep the budget-leg category's repeating target in step (TASK-M002).
    save_up: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    account: Mapped[Account] = relationship(foreign_keys=[account_id])
    transfer_account: Mapped[Account | None] = relationship(foreign_keys=[transfer_account_id])
    category: Mapped[Category | None] = relationship(foreign_keys=[category_id])
    transfer_category: Mapped[Category | None] = relationship(foreign_keys=[transfer_category_id])


class ImportMapping(Base):
    """An account's import settings from last time, so the next import needs no mapping.

    ``settings`` is JSON: the CSV ``mapping`` and ``header``, or the OFX
    ``account_number``. CASCADE: an account deleted with no transactions takes it along
    (the app also deletes it, as SQLite doesn't enforce foreign keys here).
    """

    __tablename__ = "import_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True
    )
    settings: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
