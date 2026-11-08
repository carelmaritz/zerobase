"""Reconciling an account against the bank's balance (TASK-M006).

The user enters what the bank says. If it equals the cleared balance (cleared plus
reconciled transactions), every cleared transaction becomes reconciled. If not, the
difference can be booked as one "Reconciliation balance adjustment", like YNAB: in
Inflow: Ready to Assign on a budget account, with no category on a tracking account.
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..budget import inflow_category
from ..deps import current_user, get_db, owned_account
from ..models import CLEARED, RECONCILED, UNCLEARED, Account, Transaction, User
from ..money import parse_money, plain_money
from ..templating import render

router = APIRouter()

ADJUSTMENT_PAYEE = "Reconciliation balance adjustment"


def _sum(db: Session, account: Account, *statuses: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account.id, Transaction.status.in_(statuses)
        )
    )
    return int(total)


def _page(
    request: Request,
    db: Session,
    user: User,
    account: Account,
    *,
    bank: str = "",
    difference: int | None = None,
    error: str | None = None,
    status: int = 200,
):
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "cleared": _sum(db, account, CLEARED, RECONCILED),
        "uncleared": _sum(db, account, UNCLEARED),
        "to_reconcile": db.scalar(
            select(func.count()).where(
                Transaction.account_id == account.id, Transaction.status == CLEARED
            )
        ),
        "bank": bank,
        "difference": difference,
        "error": error,
    }
    return render(request, "reconcile.html", context, status_code=status)


@router.get("/accounts/{account_id}/reconcile", response_class=HTMLResponse)
def reconcile_page(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _page(request, db, user, owned_account(db, user, account_id))


@router.post("/accounts/{account_id}/reconcile")
def reconcile(
    request: Request,
    account_id: int,
    bank_balance: str = Form(""),
    adjust: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    account = owned_account(db, user, account_id)
    try:
        bank = parse_money(bank_balance)
    except ValueError as exc:
        return _page(request, db, user, account, bank=bank_balance, error=str(exc), status=400)

    # Worked out afresh on every post, so posting the adjustment twice adds it only once:
    # the second time there is no difference left.
    difference = bank - _sum(db, account, CLEARED, RECONCILED)
    if difference and adjust != "1":
        return _page(request, db, user, account, bank=plain_money(bank), difference=difference)
    if difference:
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=inflow_category(db, user.id).id if account.on_budget else None,
                date=date.today(),
                payee=ADJUSTMENT_PAYEE,
                amount=difference,
                status=RECONCILED,
            )
        )
    db.execute(
        update(Transaction)
        .where(Transaction.account_id == account.id, Transaction.status == CLEARED)
        .values(status=RECONCILED)
    )
    account.reconciled_on = date.today()
    db.commit()
    return RedirectResponse(f"/accounts/{account.id}/reconcile?done=1", status_code=303)
