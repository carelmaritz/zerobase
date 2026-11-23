"""Spending, income and net-worth figures over a range of months (TASK-M003).

The rules, agreed with Carel (worked out in ``TASKS/TASK-M003.md``):

* **Income** is what is in the inflow category, except starting balances.
* **Spending** is activity in standard categories, so a refund reduces it.
* A transfer between budget accounts is neither. A categorised transfer to or from a tracking
  account is neither too: it is reported as **moved** to tracking accounts.
* An uncategorised transaction counts nowhere, as in the budget; it is only counted.
* **Net worth** is every account's balance at each month end (today, in the current month).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from .budget import add_months
from .models import INVESTMENT_KINDS, PROPERTY, Account, Category, CategoryGroup, Transaction

MAX_MONTHS = 120


@dataclass(frozen=True)
class MonthRange:
    start: date  # the 1st of the first month
    end: date  # the 1st of the last month

    @classmethod
    def build(cls, start: date | None, end: date | None, today: date) -> MonthRange:
        """The last 12 months by default. Never past this month, at most MAX_MONTHS long."""
        current = today.replace(day=1)
        end = min(end or current, current)
        start = min(start or add_months(end, -11), current)
        if start > end:
            start, end = end, start
        return cls(max(start, add_months(end, 1 - MAX_MONTHS)), end)

    @property
    def months(self) -> list[date]:
        out, cursor = [], self.start
        while cursor <= self.end:
            out.append(cursor)
            cursor = add_months(cursor, 1)
        return out

    @property
    def last_day(self) -> date:
        return add_months(self.end, 1) - timedelta(days=1)


@dataclass
class CategorySpending:
    name: str
    amounts: list[int]  # one per month; positive is spending

    @property
    def total(self) -> int:
        return sum(self.amounts)


@dataclass
class GroupSpending:
    name: str
    categories: list[CategorySpending] = field(default_factory=list)

    @property
    def amounts(self) -> list[int]:
        return [sum(column) for column in zip(*(c.amounts for c in self.categories), strict=True)]

    @property
    def total(self) -> int:
        return sum(c.total for c in self.categories)


@dataclass
class CashFlow:
    income: list[int]  # one per month, as are spending and moved
    spending: list[int]
    moved: list[int]  # positive: out of the budget, into tracking accounts
    groups: list[GroupSpending]
    uncategorised_count: int
    uncategorised_in: int
    uncategorised_out: int  # negative

    @property
    def net(self) -> list[int]:
        return [i - s for i, s in zip(self.income, self.spending, strict=True)]


def _year_month():
    return func.extract("year", Transaction.date), func.extract("month", Transaction.date)


def cash_flow(db: Session, user_id: int, months: MonthRange) -> CashFlow:
    index = {m: i for i, m in enumerate(months.months)}
    count = len(index)
    income, moved = [0] * count, [0] * count
    amounts: dict[int, list[int]] = {}
    other_leg, other_account = aliased(Transaction), aliased(Account)
    in_range = (
        Transaction.user_id == user_id,
        Account.on_budget.is_(True),
        Transaction.date >= months.start,
        Transaction.date <= months.last_day,
        # A transfer inside the budget is neither income nor spending.
        or_(other_account.id.is_(None), other_account.on_budget.is_(False)),
    )

    def joined(query):
        return (
            query.join(Account, Account.id == Transaction.account_id)
            .outerjoin(other_leg, other_leg.id == Transaction.transfer_id)
            .outerjoin(other_account, other_account.id == other_leg.account_id)
        )

    year, month = _year_month()
    to_tracking = other_account.id.is_not(None)
    rows = db.execute(
        joined(
            select(
                Transaction.category_id,
                Category.kind,
                year,
                month,
                to_tracking,
                func.sum(Transaction.amount),
            )
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            *in_range,
            # Edited into a transfer, it is no longer a starting balance.
            or_(Transaction.is_starting.is_(False), to_tracking),
        )
        .group_by(Transaction.category_id, Category.kind, year, month, to_tracking)
    )
    for category_id, kind, y, m, tracking, total in rows:
        i, total = index[date(int(y), int(m), 1)], int(total)
        if tracking:
            moved[i] -= total
        elif kind == "inflow":
            income[i] += total
        elif kind == "standard":  # a payment category's own rows are a card's starting debt
            amounts.setdefault(category_id, [0] * count)[i] -= total

    uncategorised = db.execute(
        joined(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount))), 0),
                func.coalesce(func.sum(case((Transaction.amount < 0, Transaction.amount))), 0),
            )
        ).where(*in_range, Transaction.category_id.is_(None))
    ).one()

    groups: dict[int, GroupSpending] = {}
    for category, group in db.execute(
        select(Category, CategoryGroup)
        .join(CategoryGroup, CategoryGroup.id == Category.group_id)
        .where(Category.user_id == user_id)
        .order_by(CategoryGroup.sort_order, CategoryGroup.id, Category.sort_order, Category.id)
    ):
        if any(amounts.get(category.id, ())):
            block = groups.setdefault(group.id, GroupSpending(group.name))
            block.categories.append(CategorySpending(category.name, amounts[category.id]))
    spending = [sum(g.amounts[i] for g in groups.values()) for i in range(count)]
    count_, in_, out = (int(v) for v in uncategorised)
    return CashFlow(income, spending, moved, list(groups.values()), count_, in_, out)


@dataclass
class NetWorth:
    """One entry per month in each list. Debt is zero or negative."""

    cash: list[int]
    investments: list[int]
    property: list[int]
    debt: list[int]

    @property
    def total(self) -> list[int]:
        columns = zip(self.cash, self.investments, self.property, self.debt, strict=True)
        return [sum(column) for column in columns]


def net_worth(db: Session, user_id: int, months: MonthRange, today: date) -> NetWorth:
    """Any balance below zero is debt; the rest go by the account's kind."""
    cutoff = min(months.last_day, today)
    year, month = _year_month()
    changes: dict[int, dict[date, int]] = {}
    kinds: dict[int, str] = {}
    for account_id, kind, y, m, total in db.execute(
        select(Account.id, Account.kind, year, month, func.sum(Transaction.amount))
        .join(Account, Account.id == Transaction.account_id)
        .where(and_(Transaction.user_id == user_id, Transaction.date <= cutoff))
        .group_by(Account.id, Account.kind, year, month)
    ):
        kinds[account_id] = kind
        changes.setdefault(account_id, {})[date(int(y), int(m), 1)] = int(total)

    count = len(months.months)
    worth = NetWorth([0] * count, [0] * count, [0] * count, [0] * count)
    for account_id, by_month in changes.items():
        kind = kinds[account_id]
        balance = sum(v for m, v in by_month.items() if m < months.start)
        for i, m in enumerate(months.months):
            balance += by_month.get(m, 0)
            if balance < 0:
                worth.debt[i] += balance
            elif kind in INVESTMENT_KINDS:
                worth.investments[i] += balance
            elif kind == PROPERTY:
                worth.property[i] += balance
            else:
                worth.cash[i] += balance
    return worth
