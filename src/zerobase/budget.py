"""Envelope-budget calculations.

The model follows the zero-based / YNAB approach:

* Income is a transaction with no category and a positive amount in a budget account.
  It flows into **Ready to Assign**.
* You **assign** money to categories month by month.
* **Activity** is what you spent (negative) or got back (positive) in a category that month.
* **Available** = what rolled over from last month + assigned + activity.
* A positive balance rolls into the next month. A negative one (overspending) does not:
  it is cleared back to zero and instead reduces Ready to Assign from the next month on.
* Ready to Assign = all income to date - all money assigned to date - past overspending.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Account, Assignment, Category, CategoryGroup, Transaction


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    year, month0 = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(year, month0 + 1, 1)


def parse_month(value: str | None, default: date) -> date:
    """Parse 'YYYY-MM' into the first of that month, falling back to ``default``."""
    try:
        year, month = (value or "").split("-")
        parsed = date(int(year), int(month), 1)
    except ValueError:
        return default
    return parsed if 1990 <= parsed.year <= 2100 else default


@dataclass
class CategoryLine:
    category: Category
    assigned: int = 0
    activity: int = 0
    available: int = 0


@dataclass
class GroupBlock:
    group: CategoryGroup
    lines: list[CategoryLine] = field(default_factory=list)

    @property
    def assigned(self) -> int:
        return sum(line.assigned for line in self.lines)

    @property
    def activity(self) -> int:
        return sum(line.activity for line in self.lines)

    @property
    def available(self) -> int:
        return sum(line.available for line in self.lines)


@dataclass
class BudgetView:
    month: date
    groups: list[GroupBlock]
    ready_to_assign: int
    income_this_month: int
    uncategorised_count: int
    uncategorised_total: int


def _year_month(year: float, month: float) -> date:
    return date(int(year), int(month), 1)


def build_budget(db: Session, user_id: int, month: date) -> BudgetView:
    month = month_start(month)
    next_month = add_months(month, 1)

    groups = db.scalars(
        select(CategoryGroup)
        .where(CategoryGroup.user_id == user_id)
        .order_by(CategoryGroup.sort_order, CategoryGroup.id)
    ).all()
    categories = db.scalars(
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.sort_order, Category.id)
    ).all()

    assigned: dict[tuple[int, date], int] = {}
    for category_id, m, amount in db.execute(
        select(Assignment.category_id, Assignment.month, Assignment.amount).where(
            Assignment.user_id == user_id, Assignment.month <= month
        )
    ):
        assigned[(category_id, m)] = amount

    year = func.extract("year", Transaction.date)
    mon = func.extract("month", Transaction.date)

    def monthly_totals(*conditions):
        """Sum of on-budget transactions per (category, month), up to the selected month."""
        return db.execute(
            select(Transaction.category_id, year, mon, func.sum(Transaction.amount))
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.user_id == user_id,
                Account.on_budget.is_(True),
                Transaction.date < next_month,
                *conditions,
            )
            .group_by(Transaction.category_id, year, mon)
        )

    activity: dict[tuple[int, date], int] = {}
    for category_id, y, m, total in monthly_totals(Transaction.category_id.is_not(None)):
        activity[(category_id, _year_month(y, m))] = int(total)

    # Income is an inflow with no category. Only positive amounts count: uncategorised
    # outflows are reported separately below instead of silently shrinking income.
    income: dict[date, int] = {}
    for _, y, m, total in monthly_totals(Transaction.category_id.is_(None), Transaction.amount > 0):
        income[_year_month(y, m)] = int(total)

    # Uncategorised outflows would otherwise vanish from the maths, so surface them.
    uncat_count, uncat_total = db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0))
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.user_id == user_id,
            Account.on_budget.is_(True),
            Transaction.category_id.is_(None),
            Transaction.amount < 0,
            Transaction.date < next_month,
        )
    ).one()

    seen_months = [m for (_, m) in assigned] + [m for (_, m) in activity] + list(income)
    earliest = min([month, *seen_months])

    blocks = {g.id: GroupBlock(g) for g in groups}
    overspent_before = 0
    for category in categories:
        carry = 0
        cursor = earliest
        while cursor < month:
            available = (
                carry
                + assigned.get((category.id, cursor), 0)
                + activity.get((category.id, cursor), 0)
            )
            if available < 0:
                overspent_before += -available
                carry = 0
            else:
                carry = available
            cursor = add_months(cursor, 1)
        this_assigned = assigned.get((category.id, month), 0)
        this_activity = activity.get((category.id, month), 0)
        blocks[category.group_id].lines.append(
            CategoryLine(
                category, this_assigned, this_activity, carry + this_assigned + this_activity
            )
        )

    total_income = sum(income.values())
    total_assigned = sum(assigned.values())
    return BudgetView(
        month=month,
        groups=list(blocks.values()),
        ready_to_assign=total_income - total_assigned - overspent_before,
        income_this_month=income.get(month, 0),
        uncategorised_count=int(uncat_count),
        uncategorised_total=int(uncat_total),
    )


def account_balances(db: Session, user_id: int) -> list[tuple[Account, int]]:
    accounts = db.scalars(
        select(Account).where(Account.user_id == user_id).order_by(Account.id)
    ).all()
    totals = dict(
        db.execute(
            select(Transaction.account_id, func.sum(Transaction.amount))
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.account_id)
        ).all()
    )
    return [(a, int(totals.get(a.id, 0))) for a in accounts]


DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Bills": ["Rent / Mortgage", "Utilities", "Phone & Internet", "Subscriptions", "Insurance"],
    "Needs": ["Groceries", "Transport", "Health"],
    "Wants": ["Dining out", "Entertainment", "Clothing"],
    "Savings goals": ["Emergency fund", "Holidays"],
}


def seed_default_categories(db: Session, user_id: int) -> None:
    order = 0
    for group_order, (group_name, names) in enumerate(DEFAULT_CATEGORIES.items()):
        group = CategoryGroup(user_id=user_id, name=group_name, sort_order=group_order)
        db.add(group)
        db.flush()
        for name in names:
            db.add(Category(user_id=user_id, group_id=group.id, name=name, sort_order=order))
            order += 1
