"""Cleared status and reconciliation (TASK-M006)."""

from datetime import date

import pytest
from sqlalchemy import func, select
from test_web import HX, PASSWORD, category_id, register

from zerobase.budget import build_budget, month_start
from zerobase.models import Account, Transaction, User
from zerobase.routers.reconcile import ADJUSTMENT_PAYEE
from zerobase.security import hash_password

TODAY = date.today()
MONTH = month_start(TODAY)


@pytest.fixture
def s(client, db):
    """Current (£1,000 opening), Mortgage (tracking, -£100,000), Card (-£200 owed)."""
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "1000"})
    client.post("/accounts", data={"name": "Mortgage", "opening_balance": "-100000"})
    client.post(
        "/accounts",
        data={"name": "Card", "kind": "credit_card", "on_budget": "1", "opening_balance": "-200"},
    )
    ids = {
        n: db.scalar(select(Account.id).where(Account.name == n))
        for n in ("Current", "Mortgage", "Card")
    }
    user_id = db.scalar(select(User.id))
    groceries = category_id(db, "Groceries")
    for payee, amount in (("Tesco", "25.00"), ("Shell", "40.00"), ("Boots", "5.00")):
        client.post(
            "/transactions",
            data={
                "account_id": ids["Current"],
                "when": TODAY.isoformat(),
                "payee": payee,
                "category_id": groceries,
                "outflow": amount,
            },
        )
    return {"ids": ids, "user_id": user_id, "groceries": groceries}


def txn(db, payee) -> Transaction:
    db.expire_all()
    return db.scalar(select(Transaction).where(Transaction.payee == payee))


def toggle(client, t, **kw):
    return client.post(f"/transactions/{t.id}/cleared", follow_redirects=False, **kw)


def rta(db, s) -> int:
    db.expire_all()
    return build_budget(db, s["user_id"], MONTH).ready_to_assign


def test_a_new_starting_balance_is_cleared_and_typed_in_rows_are_not(client, db, s):
    db.expire_all()
    starts = db.scalars(select(Transaction).where(Transaction.payee == "Starting balance")).all()
    assert len(starts) == 3 and {t.status for t in starts} == {"cleared"}
    assert txn(db, "Tesco").status == "uncleared"


def test_toggle_flips_cleared_and_back(client, db, s):
    tesco = txn(db, "Tesco")
    assert tesco.status == "uncleared"
    cell = toggle(client, tesco, headers=HX, data={"back": "q=Tesco"})
    assert cell.status_code == 200 and 'aria-pressed="true"' in cell.text
    assert f'id="status-{tesco.id}"' in cell.text and 'value="q=Tesco"' in cell.text
    assert txn(db, "Tesco").status == "cleared"
    no_js = toggle(client, tesco, data={"back": "q=Tesco"})
    assert no_js.headers["location"] == "/transactions?q=Tesco"
    assert txn(db, "Tesco").status == "uncleared"


def test_toggle_refuses_reconciled_and_other_users_rows(client, db, s):
    tesco = txn(db, "Tesco")
    tesco.status = "reconciled"
    db.commit()
    assert toggle(client, tesco).status_code == 400
    assert txn(db, "Tesco").status == "reconciled"

    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    theirs = Account(user_id=other.id, name="Theirs")
    db.add(theirs)
    db.flush()
    their_txn = Transaction(user_id=other.id, account_id=theirs.id, date=TODAY, amount=-1)
    db.add(their_txn)
    db.commit()
    assert toggle(client, their_txn).status_code == 404
    assert client.get(f"/accounts/{theirs.id}/reconcile").status_code == 404
    response = client.post(f"/accounts/{theirs.id}/reconcile", data={"bank_balance": "0"})
    assert response.status_code == 404


def test_balances_split_cleared_and_uncleared(client, db, s):
    toggle(client, txn(db, "Tesco"))
    accounts = client.get("/accounts").text
    row = accounts.split(">Current</a>")[1].split("</tr>")[0]
    # Cleared: 1,000 - 25 = 975; uncleared: Shell and Boots, -45; balance 930.
    cells = [c.split("</td>")[0] for c in row.split('<td class="r">')[1:]]
    assert cells == ["£975.00", "-£45.00", "£930.00"]
    page = client.get(f"/transactions?account_id={s['ids']['Current']}").text
    assert "Cleared <strong>£975.00</strong>" in page
    assert "Uncleared <strong>-£45.00</strong>" in page
    assert "Balance <strong>£930.00</strong>" in page


def test_reconcile_when_the_balance_matches(client, db, s):
    current = s["ids"]["Current"]
    toggle(client, txn(db, "Tesco"))
    before = rta(db, s)
    response = client.post(
        f"/accounts/{current}/reconcile", data={"bank_balance": "975"}, follow_redirects=False
    )
    assert response.headers["location"] == f"/accounts/{current}/reconcile?done=1"
    assert "matches the bank" in client.get(response.headers["location"]).text
    db.expire_all()
    statuses = {
        t.payee: t.status
        for t in db.scalars(select(Transaction).where(Transaction.account_id == current))
    }
    assert statuses == {
        "Starting balance": "reconciled",
        "Tesco": "reconciled",
        "Shell": "uncleared",
        "Boots": "uncleared",
    }
    assert db.get(Account, current).reconciled_on == TODAY
    assert txn(db, ADJUSTMENT_PAYEE) is None and rta(db, s) == before


@pytest.mark.parametrize("bank, difference", [("1000", 2500), ("950", -2500)])
def test_a_difference_is_shown_then_adjusted_once(client, db, s, bank, difference):
    current = s["ids"]["Current"]
    toggle(client, txn(db, "Tesco"))  # cleared balance £975
    before = rta(db, s)

    shown = client.post(f"/accounts/{current}/reconcile", data={"bank_balance": bank})
    assert shown.status_code == 200 and "It doesn't match" in shown.text
    assert txn(db, ADJUSTMENT_PAYEE) is None and txn(db, "Tesco").status == "cleared"

    for _ in range(2):  # posting twice adds it once: the second time nothing is left over
        client.post(f"/accounts/{current}/reconcile", data={"bank_balance": bank, "adjust": "1"})
    adjustments = db.scalars(select(Transaction).where(Transaction.payee == ADJUSTMENT_PAYEE)).all()
    assert [(a.amount, a.status, a.date) for a in adjustments] == [
        (difference, "reconciled", TODAY)
    ]
    assert adjustments[0].category_id is not None and adjustments[0].category.is_inflow
    assert rta(db, s) == before + difference  # into or out of Ready to Assign, like YNAB
    assert txn(db, "Tesco").status == "reconciled" and txn(db, "Shell").status == "uncleared"


def test_reconcile_a_tracking_account_adds_no_category(client, db, s):
    mortgage = s["ids"]["Mortgage"]
    before = rta(db, s)
    client.post(f"/accounts/{mortgage}/reconcile", data={"bank_balance": "-99000", "adjust": "1"})
    adjustment = txn(db, ADJUSTMENT_PAYEE)
    assert (adjustment.amount, adjustment.category_id) == (100_000_00 - 99_000_00, None)
    assert rta(db, s) == before


def test_reconcile_a_card_books_the_difference_in_ready_to_assign(client, db, s):
    card = s["ids"]["Card"]
    before = rta(db, s)
    # The bank says £210 is owed, not £200: £10 more debt, £10 less to assign.
    client.post(f"/accounts/{card}/reconcile", data={"bank_balance": "-210", "adjust": "1"})
    adjustment = txn(db, ADJUSTMENT_PAYEE)
    assert adjustment.amount == -1000 and adjustment.category.is_inflow
    assert rta(db, s) == before - 1000
    db.expire_all()
    assert (
        db.scalar(
            select(func.count()).where(
                Transaction.account_id == card, Transaction.status != "reconciled"
            )
        )
        == 0
    )


def test_a_bad_bank_balance_is_refused(client, db, s):
    response = client.post(
        f"/accounts/{s['ids']['Current']}/reconcile", data={"bank_balance": "abc"}
    )
    assert response.status_code == 400 and "not a valid amount" in response.text


def _edit_data(t, **changes):
    return {
        "account_id": t.account_id,
        "when": t.date.isoformat(),
        "payee": t.payee,
        "memo": t.memo,
        "category_id": t.category_id or "",
        "outflow": f"{-t.amount / 100:.2f}" if t.amount < 0 else "",
        "inflow": f"{t.amount / 100:.2f}" if t.amount > 0 else "",
        **changes,
    }


def test_editing_or_deleting_a_reconciled_row_needs_the_tick(client, db, s):
    tesco = txn(db, "Tesco")
    tesco.status = "reconciled"
    db.commit()

    page = client.get(f"/transactions?account_id={s['ids']['Current']}").text
    row = page.split(f'id="status-{tesco.id}"')[1].split("</tr>")[0]
    assert "🔒" in page and f"/transactions/{tesco.id}/delete" not in row
    form = client.get(f"/transactions/{tesco.id}/edit").text
    assert "Yes, change a reconciled transaction" in form and "Yes, delete a reconciled" in form

    refused = client.post(f"/transactions/{tesco.id}/edit", data=_edit_data(tesco, outflow="30"))
    assert refused.status_code == 400 and "reconciled" in refused.text
    assert 'value="30"' in refused.text  # what was typed is kept
    assert txn(db, "Tesco").amount == -2500
    refused = client.post(f"/transactions/{tesco.id}/delete")
    assert refused.status_code == 400 and txn(db, "Tesco") is not None

    changed = client.post(
        f"/transactions/{tesco.id}/edit",
        data=_edit_data(tesco, outflow="30", confirm_reconciled="1"),
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert (txn(db, "Tesco").amount, txn(db, "Tesco").status) == (-3000, "reconciled")

    undone = client.post(
        f"/transactions/{tesco.id}/edit",
        data=_edit_data(txn(db, "Tesco"), status="cleared", confirm_reconciled="1"),
    )
    assert undone.status_code == 200 and txn(db, "Tesco").status == "cleared"

    tesco = txn(db, "Tesco")
    tesco.status = "reconciled"
    db.commit()
    deleted = client.post(
        f"/transactions/{tesco.id}/delete", data={"confirm_reconciled": "1"}, follow_redirects=False
    )
    assert deleted.status_code == 303 and txn(db, "Tesco") is None


def test_the_category_of_a_reconciled_row_changes_without_the_tick(client, db, s):
    tesco = txn(db, "Tesco")
    tesco.status = "reconciled"
    db.commit()
    transport = category_id(db, "Transport")
    response = client.post(
        f"/transactions/{tesco.id}/category", data={"category_id": transport}, headers=HX
    )
    assert response.status_code == 204 and txn(db, "Tesco").category_id == transport


def test_a_transfer_with_a_reconciled_side_is_locked_from_both_sides(client, db, s):
    client.post(
        "/transactions",
        data={
            "account_id": s["ids"]["Current"],
            "when": TODAY.isoformat(),
            "payee": "Overpay",
            "transfer_account_id": s["ids"]["Mortgage"],
            "outflow": "100",
            "category_id": s["groceries"],
        },
    )
    db.expire_all()
    current_leg = db.scalar(
        select(Transaction).where(
            Transaction.payee == "Overpay", Transaction.account_id == s["ids"]["Current"]
        )
    )
    mortgage_leg = db.get(Transaction, current_leg.transfer_id)
    mortgage_leg.status = "reconciled"
    db.commit()
    assert current_leg.status == "uncleared"  # each side has its own status

    refused = client.post(f"/transactions/{current_leg.id}/delete")
    assert refused.status_code == 400 and "other side of the transfer" in refused.text
    assert db.get(Transaction, mortgage_leg.id) is not None
