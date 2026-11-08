"""Importing statements through the app: upload, map, preview, confirm (TASK-H006)."""

import json
from datetime import date

import pytest
from sqlalchemy import select
from test_importer import IN_OUT, OFX_SGML, SIGNED
from test_web import PASSWORD, register

from zerobase.importer import MAX_BYTES
from zerobase.models import Account, ImportMapping, Transaction, User
from zerobase.security import hash_password

SIGNED_MAP = {
    "date_col": "0",
    "date_format": "dd/mm/yyyy",
    "payee_col": "1",
    "memo_col": "2",
    "amount_col": "3",
    "out_col": "",
    "in_col": "",
    "header_rows": "1",
}


@pytest.fixture
def account(client, db):
    register(client)
    client.post("/accounts", data={"name": "Current", "kind": "checking", "on_budget": "1"})
    return db.scalar(select(Account).where(Account.name == "Current"))


def upload(client, account, text, name="statement.csv", encoding="utf-8"):
    return client.post(
        f"/accounts/{account.id}/import",
        files={"file": (name, text.encode(encoding), "text/csv")},
    )


def preview(client, account, text, mapping=SIGNED_MAP):
    return client.post(
        f"/accounts/{account.id}/import/preview", data={"content": text, **(mapping or {})}
    )


def confirm(client, account, text, add, mapping=SIGNED_MAP):
    response = client.post(
        f"/accounts/{account.id}/import/confirm",
        data={"content": text, "add": [str(n) for n in add], **(mapping or {})},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def imported(db, account):
    db.expire_all()
    return db.scalars(
        select(Transaction)
        .where(Transaction.account_id == account.id, Transaction.import_id.is_not(None))
        .order_by(Transaction.id)
    ).all()


def test_first_csv_import_asks_for_the_columns_with_a_guess(client, db, account):
    page = upload(client, account, SIGNED).text
    assert "Which column is which?" in page
    assert '<option value="3" selected>Amount</option>' in page
    assert '<option value="dd/mm/yyyy" selected>' in page
    assert db.scalar(select(Transaction.id).where(Transaction.import_id.is_not(None))) is None


def test_preview_then_import_a_signed_amount_file(client, db, account):
    page = preview(client, account, SIGNED).text
    assert "4 new" in page and "2026-11-05 to 2026-11-06" in page
    assert "£18.34 out, £1,234.56 in" in page
    location = confirm(client, account, SIGNED, add=[2, 3, 4, 5])
    assert location == f"/accounts/{account.id}/import?added=4&matched=0&skipped=0"
    assert "Imported 4 transactions" in client.get(location).text

    rows = imported(db, account)
    assert [(t.payee, t.amount, t.category_id) for t in rows] == [
        ("Tesco", -1234, None),
        ("Coffee Shop", -300, None),
        ("Coffee Shop", -300, None),
        ("Employer Ltd", 123456, None),
    ]
    assert rows[0].date == date(2026, 11, 5) and rows[0].memo == "Card 1234"
    # They count as uncategorised, so the budget page warns about them.
    assert "4 uncategorised transactions" in client.get("/budget").text


def test_separate_in_and_out_columns(client, db, account):
    mapping = {
        **SIGNED_MAP,
        "date_format": "dd mon yyyy",
        "memo_col": "",
        "amount_col": "",
        "out_col": "2",
        "in_col": "3",
    }
    confirm(client, account, IN_OUT, add=[2, 3], mapping=mapping)
    assert [t.amount for t in imported(db, account)] == [-4500, 10000]


def test_unticked_rows_are_left_out(client, db, account):
    location = confirm(client, account, SIGNED, add=[2])
    assert location.endswith("added=1&matched=0&skipped=3")
    assert len(imported(db, account)) == 1


def test_reimporting_adds_nothing_and_an_overlap_adds_only_new_rows(client, db, account):
    first_part = SIGNED.split("05/11/2026,Coffee Shop")[0]
    confirm(client, account, first_part, add=[2])
    page = preview(client, account, SIGNED).text
    assert "3 new" in page and "1 imported before" in page
    # Even if a tampered form ticks the old row, it isn't added twice.
    confirm(client, account, SIGNED, add=[2, 3, 4, 5])
    assert len(imported(db, account)) == 4
    confirm(client, account, SIGNED, add=[2, 3, 4, 5])
    assert len(imported(db, account)) == 4


def test_the_mapping_is_remembered_and_a_changed_header_asks_again(client, db, account):
    confirm(client, account, SIGNED, add=[])
    saved = json.loads(db.scalar(select(ImportMapping.settings)))
    assert saved["csv"]["header"][0] == "Date" and saved["csv"]["mapping"]["amount_col"] == 3

    page = upload(client, account, SIGNED).text
    assert "preview" in page and "4 new" in page  # straight to the preview

    changed = SIGNED.replace("Reference", "Ref")
    page = upload(client, account, changed).text
    assert "Which column is which?" in page and "don&#39;t match the last import" in page
    assert "guessed again" in page


def test_a_changed_layout_is_guessed_afresh_not_given_the_old_columns(client, db, account):
    # Out/in columns saved from one layout, then a file with one signed amount column:
    # the old "money in" column doesn't exist in the new file (found on CT 161).
    mapping = {
        **SIGNED_MAP,
        "date_format": "dd mon yyyy",
        "memo_col": "",
        "amount_col": "",
        "out_col": "2",
        "in_col": "3",
    }
    confirm(client, account, IN_OUT, add=[], mapping=mapping)
    page = upload(client, account, SIGNED).text
    assert "guessed again" in page
    amount = page.split('name="amount_col"')[1].split("</select>")[0]
    money_out = page.split('name="out_col"')[1].split("</select>")[0]
    assert '<option value="3" selected>' in amount
    assert '<option value="" selected>' in money_out


def test_hand_entered_transactions_are_matched_not_doubled(client, db, account):
    client.post(
        "/transactions",
        data={"account_id": account.id, "when": "2026-11-04", "payee": "Tesco", "outflow": "12.34"},
    )
    typed = db.scalar(select(Transaction).where(Transaction.payee == "Tesco"))
    page = preview(client, account, SIGNED).text
    assert "1 matching transactions you already entered" in page
    assert "Matches 2026-11-04 Tesco" in page

    location = confirm(client, account, SIGNED, add=[3, 4, 5])  # Tesco left as a match
    assert "added=3&matched=1" in location
    db.expire_all()
    assert db.get(Transaction, typed.id).import_id == "2026-11-05:-1234:1"
    assert db.scalar(select(Transaction.id).where(Transaction.payee == "Tesco").offset(1)) is None
    # The next import skips it as already imported.
    assert "4 imported before" in preview(client, account, SIGNED).text


def test_a_match_can_be_imported_as_new_instead(client, db, account):
    client.post(
        "/transactions",
        data={"account_id": account.id, "when": "2026-11-05", "payee": "Tesco", "outflow": "12.34"},
    )
    confirm(client, account, SIGNED, add=[2])
    tescos = db.scalars(select(Transaction).where(Transaction.payee == "Tesco")).all()
    assert len(tescos) == 2 and {t.import_id for t in tescos} == {None, "2026-11-05:-1234:1"}


def test_ofx_import_goes_straight_to_the_preview_and_reimports_add_nothing(client, db, account):
    page = upload(client, account, OFX_SGML, name="statement.ofx", encoding="cp1252").text
    assert "3 new" in page and "TESCO STORES" in page and "M&amp;S REFUND" in page
    content = OFX_SGML  # what the browser sends back
    confirm(client, account, content, add=[1, 2, 3], mapping=None)
    rows = imported(db, account)
    assert [t.import_id for t in rows] == [
        "ofx:202611050001",
        "ofx:202611060001",
        "2026-11-06:-300:1",
    ]
    saved = json.loads(db.scalar(select(ImportMapping.settings)))
    assert saved == {"ofx": {"account_number": "12345678"}}

    assert "3 imported before" in upload(client, account, OFX_SGML, name="s.ofx").text
    other = OFX_SGML.replace("<ACCTID>12345678", "<ACCTID>99999999")
    assert "This file is for account 99999999" in upload(client, account, other, name="s.ofx").text


def test_csv_then_ofx_for_the_same_transactions_are_matched(client, db, account):
    confirm(client, account, SIGNED, add=[2])  # Tesco by CSV
    page = upload(client, account, OFX_SGML, name="s.ofx").text
    assert "1 matching transactions you already entered" in page


def test_bad_rows_are_shown_and_cannot_be_imported(client, db, account):
    text = SIGNED + "31/02/2026,Nope,,-1.00\n"
    page = preview(client, account, text).text
    assert "1 that can't be read" in page and "isn&#39;t a date" in page
    confirm(client, account, text, add=[2, 3, 4, 5, 6])
    assert len(imported(db, account)) == 4


def test_a_bad_mapping_is_sent_back_with_the_reason(client, account):
    mapping = {**SIGNED_MAP, "amount_col": "", "out_col": "3", "in_col": "1"}
    response = preview(client, account, SIGNED, mapping)
    assert response.status_code == 400
    assert "Each column can only be used once." in response.text
    # The choices made are shown again, not replaced by the guess.
    out_select = response.text.split('name="out_col"')[1].split("</select>")[0]
    assert '<option value="3" selected>' in out_select


def test_files_over_the_limit_and_empty_files_are_refused(client, db, account):
    big = "Date,Amount\n" + "01/11/2026,1.00\n" * (MAX_BYTES // 15)
    response = upload(client, account, big)
    assert response.status_code in (400, 413) and "larger than 1 MB" in response.text
    response = upload(client, account, "")
    assert response.status_code == 400


def test_page_content_is_escaped(client, account):
    text = "Date,Description,Reference,Amount\n05/11/2026,<script>x</script>,,-1.00\n"
    page = preview(client, account, text).text
    assert "<script>x</script>" not in page and "&lt;script&gt;x&lt;/script&gt;" in page


def test_closed_and_foreign_accounts_are_refused(client, db, account):
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    secret = Account(user_id=other.id, name="Secret")
    db.add(secret)
    db.commit()
    assert client.get(f"/accounts/{secret.id}/import").status_code == 404
    assert upload(client, secret, SIGNED).status_code == 404
    assert preview(client, secret, SIGNED).status_code == 404
    response = client.post(
        f"/accounts/{secret.id}/import/confirm", data={"content": SIGNED, **SIGNED_MAP}
    )
    assert response.status_code == 404

    empty = Account(user_id=account.user_id, name="Old", closed=True)
    db.add(empty)
    db.commit()
    assert "Old is closed" in client.get(f"/accounts/{empty.id}/import").text
    response = client.post(
        f"/accounts/{empty.id}/import/confirm", data={"content": SIGNED, **SIGNED_MAP}
    )
    assert response.status_code == 400
    assert db.scalar(select(Transaction.id).where(Transaction.account_id == empty.id)) is None


def test_deleting_an_empty_account_deletes_its_import_settings(client, db, account):
    client.post("/accounts", data={"name": "Spare", "kind": "checking", "on_budget": "1"})
    spare = db.scalar(select(Account).where(Account.name == "Spare"))
    confirm(client, spare, SIGNED, add=[])
    assert db.scalar(select(ImportMapping.id)) is not None
    client.post(f"/accounts/{spare.id}/delete")
    db.expire_all()
    assert db.scalar(select(ImportMapping.id)) is None


def test_import_links(client, account):
    assert f'href="/accounts/{account.id}/import"' in client.get("/accounts").text
    assert "Import a statement" in client.get(f"/accounts/{account.id}/edit").text


CARD_STATEMENT = """Date,Description,Amount
03/11/2026,TRAINLINE,-20.00
04/11/2026,PAYMENT RECEIVED THANK YOU,50.00
"""
CURRENT_STATEMENT = """Date,Description,Amount
05/11/2026,VISA PAYMENT,-50.00
"""
SHORT_MAP = {**SIGNED_MAP, "memo_col": "", "amount_col": "2"}


def test_a_card_payment_becomes_a_transfer_and_the_bank_side_is_then_matched(client, db, account):
    client.post("/accounts", data={"name": "Visa", "kind": "credit_card"})
    visa = db.scalar(select(Account).where(Account.name == "Visa"))
    confirm(client, visa, CARD_STATEMENT, add=[2, 3], mapping=SHORT_MAP)
    page = client.get("/budget").text
    assert "2 uncategorised transactions" in page

    payment = db.scalar(select(Transaction).where(Transaction.amount == 5000))
    response = client.post(
        f"/transactions/{payment.id}/edit",
        data={
            "account_id": visa.id,
            "transfer_account_id": account.id,
            "when": "2026-11-04",
            "payee": "PAYMENT RECEIVED THANK YOU",
            "inflow": "50",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.expire_all()
    bank_leg = db.get(Transaction, db.get(Transaction, payment.id).transfer_id)
    assert (bank_leg.account_id, bank_leg.amount, bank_leg.import_id) == (account.id, -5000, None)

    page = preview(client, account, CURRENT_STATEMENT, SHORT_MAP).text
    assert "1 matching transactions you already entered" in page
    location = confirm(client, account, CURRENT_STATEMENT, add=[], mapping=SHORT_MAP)
    assert "added=0&matched=1" in location
    db.expire_all()
    assert db.get(Transaction, bank_leg.id).import_id == "2026-11-05:-5000:1"
