"""Checking and saving a transaction from the add/edit form, shared with schedules.

``validate_transaction`` turns the form into a :class:`ValidTransaction` (or an error);
``save_transaction`` applies one to a transaction, keeping a transfer's other leg in step.
Scheduled transactions (TASK-M002) store a ``ValidTransaction``'s fields and are entered
through ``save_transaction``.
"""

from dataclasses import dataclass
from datetime import date

from fastapi import Form
from sqlalchemy.orm import Session

from .deps import owned_account, owned_category
from .models import Transaction, User
from .money import parse_money


@dataclass
class TransactionForm:
    """The raw fields of the add and edit forms, as submitted."""

    account_id: int
    when: str
    payee: str = ""
    memo: str = ""
    category_id: str = ""
    outflow: str = ""
    inflow: str = ""
    transfer_account_id: str = ""

    def values(self) -> dict:
        """The submitted values, for re-showing the form after an error."""
        return {
            **vars(self),
            "category_id": _optional_id(self.category_id),
            "transfer_account_id": _optional_id(self.transfer_account_id),
        }


def _optional_id(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() else None


def transaction_form(
    account_id: int = Form(...),
    when: str = Form(...),
    payee: str = Form(""),
    memo: str = Form(""),
    category_id: str = Form(""),
    outflow: str = Form(""),
    inflow: str = Form(""),
    transfer_account_id: str = Form(""),
) -> TransactionForm:
    return TransactionForm(
        account_id, when, payee, memo, category_id, outflow, inflow, transfer_account_id
    )


@dataclass
class ValidTransaction:
    account_id: int
    category_id: int | None
    date: date
    payee: str
    memo: str
    amount: int
    # For a transfer: the other account, and the category of the leg there.
    transfer_account_id: int | None = None
    transfer_category_id: int | None = None


def validate_transaction(
    db: Session, user: User, form: TransactionForm, existing: Transaction | None = None
) -> ValidTransaction | str:
    """Check a submitted add or edit form. Returns the clean fields, or an error message.

    A foreign account or category ID raises a 404, as everywhere else. For a transfer, the
    amount is from this account's side; the other leg gets the opposite. A closed account
    is refused unless ``existing`` (the transaction being edited) already uses it.
    """
    account = owned_account(db, user, form.account_id)
    transfer = None
    if form.transfer_account_id.strip():
        try:
            transfer = owned_account(db, user, int(form.transfer_account_id))
        except ValueError:
            return "Choose a valid account to transfer to or from."
        if transfer.id == account.id:
            return "A transfer needs two different accounts."
    already_used, categories_used = set(), set()
    if existing is not None:
        already_used.add(existing.account_id)
        categories_used.add(existing.category_id)
        if existing.transfer is not None:
            already_used.add(existing.transfer.account_id)
            categories_used.add(existing.transfer.category_id)
    for each in (account, transfer):
        if each is not None and each.closed and each.id not in already_used:
            return f"{each.name} is closed. Reopen it on the Accounts page to add to it."
    try:
        when_date = date.fromisoformat(form.when)
    except ValueError:
        return "Enter a valid date."
    if not 1990 <= when_date.year <= 2100:
        return "The date must be between 1990 and 2100."

    if bool(form.outflow.strip()) == bool(form.inflow.strip()):
        return "Enter either an outflow or an inflow amount."
    try:
        amount = parse_money(form.inflow) if form.inflow.strip() else -parse_money(form.outflow)
    except ValueError as exc:
        return str(exc)
    if amount == 0:
        return "The amount cannot be zero."

    category_id = None
    if form.category_id.strip():
        try:
            category = owned_category(db, user, int(form.category_id))
        except ValueError:
            return "Choose a valid category."
        # Only a card's starting debt sits in its payment category; pay a card by transfer.
        if category.is_card_payment and category.id not in categories_used:
            return "To pay a credit card, record a transfer to it."
        category_id = category.id

    # Only a budget-account leg can have a category; for a transfer, only when the money
    # leaves or enters the budget, and then it must have one.
    transfer_category_id = None
    if transfer is None:
        if not account.on_budget:  # tracking accounts never touch envelopes
            category_id = None
    elif account.on_budget == transfer.on_budget:
        if category_id is not None:
            return (
                "Leave the category blank: a transfer between two budget accounts, or two "
                "tracking accounts, doesn't touch the envelopes."
            )
    elif category_id is None:
        return "Choose a category: this transfer moves money into or out of the budget."
    elif not account.on_budget:
        category_id, transfer_category_id = None, category_id

    return ValidTransaction(
        account_id=account.id,
        category_id=category_id,
        date=when_date,
        payee=form.payee.strip()[:100],
        memo=form.memo.strip()[:255],
        amount=amount,
        transfer_account_id=transfer.id if transfer else None,
        transfer_category_id=transfer_category_id,
    )


def save_transaction(
    db: Session, user_id: int, valid: ValidTransaction, transaction: Transaction
) -> None:
    """Apply checked fields to a new or existing transaction, keeping any other leg in step.

    Adding a transfer account creates the other leg; removing it deletes that leg. The
    caller commits, so both legs change together.
    """
    for field in ("account_id", "category_id", "date", "payee", "memo", "amount"):
        setattr(transaction, field, getattr(valid, field))
    other = db.get(Transaction, transaction.transfer_id) if transaction.transfer_id else None

    if valid.transfer_account_id is None:
        if other is not None:
            transaction.transfer_id = None
            db.delete(other)
        return

    if other is None:
        other = Transaction(user_id=user_id)
        db.add(other)
    other.account_id = valid.transfer_account_id
    other.category_id = valid.transfer_category_id
    other.date, other.payee, other.memo = valid.date, valid.payee, valid.memo
    other.amount = -valid.amount
    db.flush()  # both legs need IDs before they can point at each other
    transaction.transfer_id, other.transfer_id = other.id, transaction.id
