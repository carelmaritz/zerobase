"""Envelope-budget calculations.

The model follows the zero-based / YNAB approach:

* Income is a budget-account transaction in the built-in **Inflow: Ready to Assign**
  category. It flows into **Ready to Assign** (a negative one reduces it). A transaction
  with no category isn't counted anywhere until it is categorised.
* You **assign** money to categories month by month.
* **Activity** is what you spent (negative) or got back (positive) in a category that month.
* **Available** = what rolled over from last month + assigned + activity.
* A positive balance rolls into the next month. A negative one (overspending) does not:
  it is cleared back to zero and instead reduces Ready to Assign from the next month on.
* Ready to Assign = all income to date - all money assigned to date - past overspending.

A **hidden** category still counts in all of this; it is just listed apart from its group.

Credit cards (the YNAB model; worked examples in ``TASKS/TASK-H005.md``):

* Each card has a **payment category**. Card spending in a category that has the money
  moves that much into the card's payment category, set aside to pay the bill. A refund
  on the card moves it back out.
* Within a category and month, cash spending is funded first, then card spending, card by
  card in account order. Funding uses month totals, so assigning more later in the month
  funds earlier card spending.
* Card spending the category can't fund is **credit overspending**: the category still
  resets to zero next month, but Ready to Assign is not reduced. It is debt with nothing
  set aside, and shows as "needed" on the payment category.
* A transfer between a budget account and a card is a payment: it is activity in the
  card's payment category. A payment category that goes negative is cash overspending.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from .models import (
    BALANCE,
    CREDIT_CARD,
    MONTHLY,
    UNCLEARED,
    Account,
    Assignment,
    Category,
    CategoryGroup,
    ScheduledTransaction,
    Target,
    Transaction,
)


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
    cash_overspent: int = 0
    credit_overspent: int = 0
    needed: int = 0
    target: Target | None = None
    underfunded: int = 0  # more to assign this month to meet the target
    target_due: date | None = None  # a by-month target's due month, seen from this month


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
    uncategorised_outflow: int  # negative
    uncategorised_inflow: int
    hidden: list[CategoryLine] = field(default_factory=list)

    @property
    def underfunded(self) -> int:
        """Underfunded in the categories shown: what "Assign all" would fund."""
        return sum(line.underfunded for block in self.groups for line in block.lines)

    def fundable(self) -> list[CategoryLine]:
        """Visible lines with a target to fund, in budget order."""
        return [line for block in self.groups for line in block.lines if line.underfunded]


@dataclass
class Ledger:
    """What the budget maths needs from the database, as plain sums keyed by month (the 1st).

    ``cash`` and ``card`` are activity in standard categories: ``card`` is what happened on
    a credit card, keyed by (category, month, card account); ``cash`` is everything else.
    ``payments`` is payment-category activity from transfers, keyed by (card, month).
    """

    income: dict[date, int] = field(default_factory=dict)
    assigned: dict[tuple[int, date], int] = field(default_factory=dict)
    cash: dict[tuple[int, date], int] = field(default_factory=dict)
    card: dict[tuple[int, date, int], int] = field(default_factory=dict)
    payments: dict[tuple[int, date], int] = field(default_factory=dict)
    payment_categories: dict[int, int] = field(default_factory=dict)  # card -> category
    card_balances: dict[int, int] = field(default_factory=dict)  # at the end of the month

    def months(self) -> list[date]:
        return [
            *(m for _, m in self.assigned),
            *(m for _, m in self.cash),
            *(m for _, m, _ in self.card),
            *(m for _, m in self.payments),
            *self.income,
        ]


@dataclass
class Figures:
    """One category's numbers for the month shown."""

    assigned: int = 0
    activity: int = 0
    available: int = 0
    cash_overspent: int = 0
    credit_overspent: int = 0
    needed: int = 0  # payment categories only: debt not yet set aside


@dataclass
class _Month:
    available: int
    cash_overspent: int
    credit_overspent: int
    funded: dict[int, int]  # card -> moved into its payment category (negative: moved out)


def _roll_month(carry: int, assigned: int, cash: int, cards: dict[int, int]) -> _Month:
    """One category, one month. ``cards`` is net activity per card (negative: spending)."""
    refunds = {card: v for card, v in cards.items() if v > 0}
    spending = sorted((card, -v) for card, v in cards.items() if v < 0)
    base = carry + assigned + cash + sum(refunds.values())  # left after cash spending
    funded = {card: -v for card, v in refunds.items()}
    remaining = base
    for card, spent in spending:
        funded[card] = min(spent, max(0, remaining))
        remaining -= spent
    available = remaining
    overspent = max(0, -available)
    cash_overspent = min(overspent, max(0, -base))
    return _Month(available, cash_overspent, overspent - cash_overspent, funded)


def compute_budget(
    ledger: Ledger, category_ids: list[int], month: date
) -> tuple[dict[int, Figures], int]:
    """Every category's figures for ``month``, and Ready to Assign.

    ``category_ids`` are the standard categories; payment categories come from the ledger.
    Only data up to the end of ``month`` should be in the ledger.
    """
    months = []
    cursor = min([month, *ledger.months()])
    while cursor <= month:
        months.append(cursor)
        cursor = add_months(cursor, 1)

    cards_by_category: dict[tuple[int, date], dict[int, int]] = {}
    for (category_id, m, card), amount in ledger.card.items():
        cards_by_category.setdefault((category_id, m), {})[card] = amount

    figures: dict[int, Figures] = {}
    cash_overspent_before = 0
    funded: dict[tuple[int, date], int] = {}  # (card, month) -> moved to its payment category

    def roll(category_id: int, inflows: dict[date, int], cards: dict[date, dict[int, int]]):
        nonlocal cash_overspent_before
        carry = 0
        for m in months:
            assigned = ledger.assigned.get((category_id, m), 0)
            result = _roll_month(carry, assigned, inflows.get(m, 0), cards.get(m, {}))
            for card, amount in result.funded.items():
                funded[(card, m)] = funded.get((card, m), 0) + amount
            if m < month:
                cash_overspent_before += result.cash_overspent
                carry = max(0, result.available)
                continue
            activity = inflows.get(m, 0) + sum(cards.get(m, {}).values())
            figures[category_id] = Figures(
                assigned,
                activity,
                result.available,
                result.cash_overspent,
                result.credit_overspent,
            )

    for category_id in category_ids:
        roll(
            category_id,
            {m: ledger.cash.get((category_id, m), 0) for m in months},
            {m: cards_by_category.get((category_id, m), {}) for m in months},
        )
    # Payment categories last: what flows into them depends on every other category.
    for card, category_id in ledger.payment_categories.items():
        flows = {m: funded.get((card, m), 0) + ledger.payments.get((card, m), 0) for m in months}
        roll(category_id, flows, {})
        line = figures[category_id]
        debt = -ledger.card_balances.get(card, 0)
        line.needed = max(0, debt - max(0, line.available))

    ready = sum(ledger.income.values()) - sum(ledger.assigned.values()) - cash_overspent_before
    return figures, ready


def target_due(by: date, month: date, repeats: bool) -> date:
    """The month a by-month target is due, seen from ``month``.

    A repeating (yearly) target is due in its month of the year: the first one on or after
    ``month``, but never before ``by`` itself.
    """
    if not repeats or by >= month:
        return by
    due = date(month.year, by.month, 1)
    return due if due >= month else date(month.year + 1, by.month, 1)


def underfunded(
    kind: str,
    amount: int,
    by: date | None,
    month: date,
    assigned: int,
    available: int,
    *,
    repeats: bool = False,
    activity: int = 0,
) -> int:
    """How much more to assign to a category in ``month`` to meet its target.

    ``assigned`` is this month's assignment, ``activity`` its activity and ``available``
    the Available at the end of the month. Worked examples are in TASKS/TASK-M001.md and,
    for repeating targets, TASKS/TASK-M002.md.
    """
    if kind == MONTHLY:  # set aside the amount every month
        return max(0, amount - assigned)
    if kind == BALANCE:
        return max(0, amount - available)
    # BY_DATE: what's left before this month's assigning, spread over the months to go.
    # A repeating target counts from before this month's spending too, so paying the bill
    # in its month doesn't make it look underfunded again.
    assert by is not None
    due = target_due(by, month, repeats)
    start = available - assigned - (activity if repeats else 0)
    months_left = max(1, (due.year - month.year) * 12 + due.month - month.month + 1)
    share = -(-max(0, amount - start) // months_left)  # rounded up to the penny
    return max(0, share - assigned)


def _year_month(year: float, month: float) -> date:
    return date(int(year), int(month), 1)


def build_budget(
    db: Session, user_id: int, month: date, *, merge: tuple[int, int] | None = None
) -> BudgetView:
    """The budget for ``month``.

    ``merge=(source_id, target_id)`` previews :func:`merge_category` without writing:
    the source's assignments and activity are counted as the target's.
    """
    month = month_start(month)
    source_id, target_id = merge or (None, None)

    def remap(category_id: int) -> int:
        return target_id if category_id == source_id else category_id

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
    inflow_ids = {c.id for c in categories if c.is_inflow}
    # A payment category's own transactions are a card's starting debt, not activity.
    payment_ids = {c.id for c in categories if c.is_card_payment}
    categories = [c for c in categories if not c.is_inflow and c.id != source_id]

    ledger = Ledger(
        payment_categories={c.account_id: c.id for c in categories if c.is_card_payment}
    )
    assigned = ledger.assigned
    for category_id, m, amount in db.execute(
        select(Assignment.category_id, Assignment.month, Assignment.amount).where(
            Assignment.user_id == user_id, Assignment.month <= month
        )
    ):
        key = (remap(category_id), m)
        assigned[key] = assigned.get(key, 0) + amount

    year = func.extract("year", Transaction.date)
    mon = func.extract("month", Transaction.date)

    is_card = Account.kind == CREDIT_CARD
    for category_id, y, m, account_id, card, total in db.execute(
        select(
            Transaction.category_id, year, mon, Account.id, is_card, func.sum(Transaction.amount)
        )
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.user_id == user_id,
            Account.on_budget.is_(True),
            Transaction.date < next_month,
            Transaction.category_id.is_not(None),
        )
        .group_by(Transaction.category_id, year, mon, Account.id, is_card)
    ):
        when, total = _year_month(y, m), int(total)
        if category_id in inflow_ids:
            ledger.income[when] = ledger.income.get(when, 0) + total
        elif category_id in payment_ids:
            continue
        elif card:
            key3 = (remap(category_id), when, account_id)
            ledger.card[key3] = ledger.card.get(key3, 0) + total
        else:
            key = (remap(category_id), when)
            ledger.cash[key] = ledger.cash.get(key, 0) + total

    # Card payments: a transfer between a card and another budget account. The card side's
    # amount comes out of the payment category (a £100 payment arrives as +£100).
    payment_leg = aliased(Transaction)
    paying_account = aliased(Account)
    for account_id, y, m, total in db.execute(
        select(Transaction.account_id, year, mon, func.sum(Transaction.amount))
        .join(Account, Account.id == Transaction.account_id)
        .join(payment_leg, payment_leg.id == Transaction.transfer_id)
        .join(paying_account, paying_account.id == payment_leg.account_id)
        .where(
            Transaction.user_id == user_id,
            is_card,
            paying_account.on_budget.is_(True),
            Transaction.date < next_month,
        )
        .group_by(Transaction.account_id, year, mon)
    ):
        ledger.payments[(account_id, _year_month(y, m))] = -int(total)

    ledger.card_balances = {
        account_id: int(total)
        for account_id, total in db.execute(
            select(Transaction.account_id, func.sum(Transaction.amount))
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.user_id == user_id, is_card, Transaction.date < next_month)
            .group_by(Transaction.account_id)
        )
    }

    # Uncategorised transactions would otherwise vanish from the maths, so surface them.
    # A transfer leg to another budget account needs no category, so it isn't flagged.
    other_leg = aliased(Transaction)
    other_account = aliased(Account)
    uncat_count, uncat_outflow, uncat_inflow = db.execute(
        select(
            func.count(Transaction.id),
            func.coalesce(func.sum(case((Transaction.amount < 0, Transaction.amount))), 0),
            func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount))), 0),
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(other_leg, other_leg.id == Transaction.transfer_id)
        .outerjoin(other_account, other_account.id == other_leg.account_id)
        .where(
            Transaction.user_id == user_id,
            Account.on_budget.is_(True),
            Transaction.category_id.is_(None),
            Transaction.date < next_month,
            or_(other_account.id.is_(None), other_account.on_budget.is_(False)),
        )
    ).one()

    standard_ids = [c.id for c in categories if not c.is_card_payment]
    figures, ready_to_assign = compute_budget(ledger, standard_ids, month)
    targets = {
        t.category_id: t
        for t in db.scalars(select(Target).where(Target.user_id == user_id))
        if t.category_id != source_id
    }
    blocks = {g.id: GroupBlock(g) for g in groups}
    hidden: list[CategoryLine] = []
    for category in categories:
        f = figures[category.id]
        line = CategoryLine(
            category,
            f.assigned,
            f.activity,
            f.available,
            f.cash_overspent,
            f.credit_overspent,
            f.needed,
        )
        target = targets.get(category.id)
        if target is not None and category.kind == "standard":
            line.target = target
            line.underfunded = underfunded(
                target.kind,
                target.amount,
                target.month,
                month,
                f.assigned,
                f.available,
                repeats=target.repeats,
                activity=f.activity,
            )
            if target.month is not None:
                line.target_due = target_due(target.month, month, target.repeats)
        (hidden if category.hidden else blocks[category.group_id].lines).append(line)

    return BudgetView(
        month=month,
        groups=list(blocks.values()),
        ready_to_assign=ready_to_assign,
        income_this_month=ledger.income.get(month, 0),
        uncategorised_count=int(uncat_count),
        uncategorised_outflow=int(uncat_outflow),
        uncategorised_inflow=int(uncat_inflow),
        hidden=hidden,
    )


# How far ahead :func:`assign_cap` looks. Far-future rows (a mistyped year) only slow it.
CAP_HORIZON_MONTHS = 24


def assign_cap(db: Session, user_id: int, month: date) -> int:
    """The most that can be assigned in ``month`` without any Ready to Assign going below 0.

    An assignment in ``month`` lowers Ready to Assign in every later month too, so this is
    the lowest Ready to Assign from ``month`` to the last month with assignments or
    transactions (plus one: overspending reaches Ready to Assign the month after).
    """
    month = month_start(month)
    latest = [
        db.scalar(select(func.max(Assignment.month)).where(Assignment.user_id == user_id)),
        db.scalar(select(func.max(Transaction.date)).where(Transaction.user_id == user_id)),
    ]
    last = max([month, *(add_months(month_start(d), 1) for d in latest if d is not None)])
    last = min(last, add_months(month, CAP_HORIZON_MONTHS))
    cap = None
    cursor = month
    while cursor <= last:
        ready = build_budget(db, user_id, cursor).ready_to_assign
        cap = ready if cap is None else min(cap, ready)
        cursor = add_months(cursor, 1)
    return max(0, cap or 0)


def fund(db: Session, user_id: int, month: date, lines: list[CategoryLine]) -> list[CategoryLine]:
    """Assign each line's underfunded amount in ``month``, in order, within :func:`assign_cap`.

    Returns the lines that couldn't be fully funded. Flushes; the caller commits.
    """
    month = month_start(month)
    left = assign_cap(db, user_id, month)
    short = []
    for line in lines:
        amount = min(line.underfunded, left)
        if amount < line.underfunded:
            short.append(line)
        if amount <= 0:
            continue
        left -= amount
        existing = db.scalar(
            select(Assignment).where(
                Assignment.category_id == line.category.id, Assignment.month == month
            )
        )
        if existing is None:
            db.add(
                Assignment(
                    user_id=user_id, category_id=line.category.id, month=month, amount=amount
                )
            )
        elif existing.amount + amount == 0:  # as the assign route does: no zero assignments
            db.delete(existing)
        else:
            existing.amount += amount
    db.flush()
    return short


def category_in_use(db: Session, category: Category) -> bool:
    """Whether any transaction, assignment or schedule refers to the category."""
    checks = [
        select(Transaction.id).where(Transaction.category_id == category.id),
        select(Assignment.id).where(Assignment.category_id == category.id),
        select(ScheduledTransaction.id).where(
            or_(
                ScheduledTransaction.category_id == category.id,
                ScheduledTransaction.transfer_category_id == category.id,
            )
        ),
    ]
    return any(db.scalar(check.limit(1)) is not None for check in checks)


def merge_category(db: Session, source: Category, target: Category) -> None:
    """Move the source's transactions, assignments, schedules and target to ``target``.

    Then delete the source.

    Assignments in the same month are summed (one assignment per category and month).
    Totals are unchanged, but past overspending can be: an overspent source merged into
    a target with a surplus that month is no longer overspent, so Ready to Assign rises.
    :func:`build_budget` with ``merge`` previews that. Flushes; the caller commits.
    """
    assert source.user_id == target.user_id and source.id != target.id
    for model, column in [
        (Transaction, "category_id"),
        (ScheduledTransaction, "category_id"),
        (ScheduledTransaction, "transfer_category_id"),
    ]:
        db.execute(
            update(model)
            .where(getattr(model, column) == source.id)
            .values({column: target.id})
            .execution_options(synchronize_session="fetch")
        )
    existing = {
        a.month: a
        for a in db.scalars(select(Assignment).where(Assignment.category_id == target.id))
    }
    moving_assignments = db.scalars(
        select(Assignment).where(Assignment.category_id == source.id)
    ).all()
    for moving in moving_assignments:
        kept = existing.get(moving.month)
        if kept is None:
            moving.category_id = target.id
            continue
        kept.amount += moving.amount
        db.delete(moving)
        if kept.amount == 0:  # as the assign route does: no zero assignments
            db.delete(kept)
    # One target per category: the target's own wins, else it takes the source's.
    moving_target = db.scalar(select(Target).where(Target.category_id == source.id))
    if moving_target is not None:
        if db.scalar(select(Target.id).where(Target.category_id == target.id)) is None:
            moving_target.category_id = target.id
        else:
            db.delete(moving_target)
    db.flush()  # assignments and target off the source before it goes
    db.delete(source)
    db.flush()


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


def cleared_balances(db: Session, user_id: int) -> dict[int, int]:
    """Per account, the sum of cleared and reconciled transactions (what the bank shows).

    The uncleared part is the account's balance minus this.
    """
    return {
        account_id: int(total)
        for account_id, total in db.execute(
            select(Transaction.account_id, func.sum(Transaction.amount))
            .where(Transaction.user_id == user_id, Transaction.status != UNCLEARED)
            .group_by(Transaction.account_id)
        )
    }


DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Bills": ["Rent / Mortgage", "Utilities", "Phone & Internet", "Subscriptions", "Insurance"],
    "Needs": ["Groceries", "Transport", "Health"],
    "Wants": ["Dining out", "Entertainment", "Clothing"],
    "Savings goals": ["Emergency fund", "Holidays"],
}


def inflow_category(db: Session, user_id: int) -> Category:
    """The user's built-in income category, created if it is somehow missing."""
    category = db.scalar(
        select(Category)
        .where(Category.user_id == user_id, Category.kind == "inflow")
        .order_by(Category.id)
        .limit(1)
    )
    if category is None:
        category = Category(user_id=user_id, group_id=None, name="Ready to Assign", kind="inflow")
        db.add(category)
        db.flush()
    return category


CARD_PAYMENTS_GROUP = "Credit Card Payments"


def card_payments_group(db: Session, user_id: int) -> CategoryGroup:
    """The user's system group for card payment categories, created first in the budget."""
    group = db.scalar(
        select(CategoryGroup).where(
            CategoryGroup.user_id == user_id, CategoryGroup.kind == "card_payments"
        )
    )
    if group is None:
        first = db.scalar(
            select(func.min(CategoryGroup.sort_order)).where(CategoryGroup.user_id == user_id)
        )
        group = CategoryGroup(
            user_id=user_id,
            name=CARD_PAYMENTS_GROUP,
            kind="card_payments",
            sort_order=(first or 0) - 1,
        )
        db.add(group)
        db.flush()
    return group


def add_payment_category(db: Session, card: Account) -> Category:
    """Create a card's payment category, named after the card. Flushes; the caller commits."""
    group = card_payments_group(db, card.user_id)
    position = db.scalar(
        select(func.coalesce(func.max(Category.sort_order), -1) + 1).where(
            Category.group_id == group.id
        )
    )
    category = Category(
        user_id=card.user_id,
        group_id=group.id,
        name=card.name[:60],
        sort_order=position,
        kind="card_payment",
        account_id=card.id,
    )
    db.add(category)
    db.flush()
    return category


def seed_default_categories(db: Session, user_id: int) -> None:
    inflow_category(db, user_id)
    order = 0
    for group_order, (group_name, names) in enumerate(DEFAULT_CATEGORIES.items()):
        group = CategoryGroup(user_id=user_id, name=group_name, sort_order=group_order)
        db.add(group)
        db.flush()
        for name in names:
            db.add(Category(user_id=user_id, group_id=group.id, name=name, sort_order=order))
            order += 1
