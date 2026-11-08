"""Importing a bank statement (CSV or OFX) into an account (TASK-H006).

Upload, then (CSV only) choose the columns, then preview, then confirm. The file's text
travels in a hidden form field between the steps; every step parses it again, and confirm
checks everything again, so nothing is stored until then. See ``importer`` for the rules.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile

from .. import importer
from ..deps import current_user, get_db, owned_account
from ..importer import DATE_FORMATS, MATCH, MAX_BYTES, NEW, Existing, Mapping, Statement
from ..models import CLEARED, UNCLEARED, Account, ImportMapping, Transaction, User
from ..templating import render

router = APIRouter()

# The file's text is sent back in one form field. Decoding Windows-1252 can make it
# longer than the upload (a "£" becomes two bytes), so allow more than the 1 MB cap.
FORM_PART_LIMIT = 4 * MAX_BYTES
TOO_BIG = "That file is larger than 1 MB. Export a shorter date range and try again."


async def import_form(request: Request) -> AsyncIterator[FormData]:
    """The submitted form, or ``too_big`` if the body is clearly over the limit.

    Checked from Content-Length before reading anything, so a huge upload isn't spooled.
    The upload is closed once the request is done.
    """
    limit = MAX_BYTES if request.url.path.endswith("/import") else FORM_PART_LIMIT
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError:
        length = 0
    if length > limit + 64 * 1024:  # room for the multipart framing
        yield FormData([("too_big", "1")])
        return
    form = await request.form(max_files=1, max_fields=50_000, max_part_size=FORM_PART_LIMIT)
    try:
        yield form
    finally:
        await form.close()


def _closed_error(account: Account) -> str | None:
    if account.closed:
        return f"{account.name} is closed. Reopen it on the Accounts page to import into it."
    return None


def _saved(db: Session, account: Account) -> tuple[ImportMapping | None, dict]:
    row = db.scalar(select(ImportMapping).where(ImportMapping.account_id == account.id))
    try:
        return row, (json.loads(row.settings) if row else {})
    except ValueError:
        return row, {}


def _saved_mapping(settings: dict) -> Mapping | None:
    try:
        return Mapping(**settings["csv"]["mapping"])
    except (KeyError, TypeError):
        return None


def _upload_page(
    request: Request,
    user: User,
    account: Account,
    error: str | None = None,
    status: int = 200,
    done: dict | None = None,
):
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "error": error or _closed_error(account),
        "done": done,
        "max_mb": MAX_BYTES // (1024 * 1024),
    }
    return render(request, "import_upload.html", context, status_code=status)


def _map_page(
    request: Request,
    user: User,
    account: Account,
    content: str,
    mapping: Mapping,
    error: str | None = None,
    note: str | None = None,
    status: int = 200,
):
    table = importer.read_csv(content)
    width = max((len(r) for r in table[:50]), default=0)
    first = mapping.header_rows - 1
    header = table[first] if 0 <= first < len(table) else []
    columns = [
        (i, header[i] if i < len(header) and header[i] else f"Column {i + 1}") for i in range(width)
    ]
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "content": content,
        "mapping": mapping,
        "columns": columns,
        "sample": table[:8],
        "date_formats": DATE_FORMATS,
        "error": error,
        "note": note,
    }
    return render(request, "import_map.html", context, status_code=status)


def _existing(db: Session, account: Account, statement: Statement) -> list[Existing]:
    """The account's transactions a row could duplicate: every imported one (an ID can
    move date between exports), and anything near the file's dates (for matching).
    """
    dates = [r.date for r in statement.rows if r.date]
    condition = Transaction.import_id.is_not(None)
    if dates:
        low, high = (
            min(dates) - timedelta(days=importer.MATCH_DAYS),
            max(dates) + timedelta(days=importer.MATCH_DAYS),
        )
        condition = or_(condition, Transaction.date.between(low, high))
    query = select(
        Transaction.id, Transaction.date, Transaction.amount, Transaction.import_id
    ).where(Transaction.account_id == account.id, condition)
    return [Existing(*row) for row in db.execute(query)]


def _mapping_from(form: FormData) -> Mapping | None:
    """The mapping fields of a submitted form, unchecked; None if they aren't numbers."""

    def column(name: str) -> int | None:
        value = str(form.get(name, "")).strip()
        return int(value) if value else None

    try:
        date_col = column("date_col")
        if date_col is None:
            return None
        return Mapping(
            date_col=date_col,
            date_format=str(form.get("date_format", "")),
            payee_col=column("payee_col"),
            memo_col=column("memo_col"),
            amount_col=column("amount_col"),
            out_col=column("out_col"),
            in_col=column("in_col"),
            flip_sign=form.get("flip_sign") == "1",
            header_rows=column("header_rows") or 0,
        )
    except ValueError:
        return None


def _parse(content: str, form: FormData) -> tuple[Statement | None, Mapping | None, str | None]:
    """The statement and the mapping used, or (None, the mapping to show again, the error)."""
    if importer.is_ofx(content):
        return importer.parse_ofx(content), None, None
    mapping = _mapping_from(form)
    error = "That mapping isn't valid." if mapping is None else mapping.problem()
    if error:
        return None, mapping or importer.guess_mapping(importer.read_csv(content)), error
    return importer.parse_csv(content, mapping), mapping, None


def _preview_page(
    request: Request,
    db: Session,
    user: User,
    account: Account,
    content: str,
    statement: Statement,
    mapping: Mapping | None,
):
    verdicts = importer.classify(statement.rows, _existing(db, account, statement))
    readable = [v.row for v in verdicts if v.status != importer.ERROR]
    _, settings = _saved(db, account)
    saved_number = settings.get("ofx", {}).get("account_number")
    matched = {v.match_id for v in verdicts if v.match_id}
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "content": content,
        "mapping": mapping,
        "verdicts": verdicts,
        "matches": {
            t.id: t for t in db.scalars(select(Transaction).where(Transaction.id.in_(matched)))
        },
        "counts": {
            s: sum(v.status == s for v in verdicts)
            for s in (NEW, importer.IMPORTED, MATCH, importer.ERROR)
        },
        "first": min((r.date for r in readable), default=None),
        "last": max((r.date for r in readable), default=None),
        "new_in": sum(v.row.amount for v in verdicts if v.status == NEW and v.row.amount > 0),
        "new_out": sum(v.row.amount for v in verdicts if v.status == NEW and v.row.amount < 0),
        "wrong_account": (
            statement.account_number and saved_number and statement.account_number != saved_number
        ),
        "account_number": statement.account_number,
        "saved_number": saved_number,
    }
    return render(request, "import_preview.html", context)


@router.get("/accounts/{account_id}/import", response_class=HTMLResponse)
def upload_form(
    request: Request,
    account_id: int,
    added: int | None = None,
    matched: int = 0,
    skipped: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    account = owned_account(db, user, account_id)
    done = None if added is None else {"added": added, "matched": matched, "skipped": skipped}
    return _upload_page(request, user, account, done=done)


@router.post("/accounts/{account_id}/import")
def upload(
    request: Request,
    account_id: int,
    form: FormData = Depends(import_form),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Read the file, then go to the mapping step (CSV) or straight to the preview."""
    account = owned_account(db, user, account_id)
    if error := _closed_error(account):
        return _upload_page(request, user, account, error, 400)
    if form.get("too_big"):
        return _upload_page(request, user, account, TOO_BIG, 413)
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return _upload_page(request, user, account, "Choose a file to import.", 400)
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return _upload_page(request, user, account, TOO_BIG, 400)
    content = importer.decode(data)
    if not content.strip():
        return _upload_page(request, user, account, "That file is empty.", 400)

    if importer.is_ofx(content):
        return _preview_page(request, db, user, account, content, importer.parse_ofx(content), None)

    table = importer.read_csv(content)
    _, settings = _saved(db, account)
    saved = _saved_mapping(settings)
    if saved is not None:
        first = saved.header_rows - 1
        header = table[first] if 0 <= first < len(table) else []
        if header == settings["csv"].get("header"):
            statement = importer.parse_csv(content, saved)
            return _preview_page(request, db, user, account, content, statement, saved)
        # Guess afresh: the saved columns may not even exist in this layout.
        note = (
            "This file's columns don't match the last import into this account, so they "
            "have been guessed again. Check the mapping."
        )
        return _map_page(request, user, account, content, importer.guess_mapping(table), note=note)
    return _map_page(request, user, account, content, importer.guess_mapping(table))


@router.post("/accounts/{account_id}/import/map")
def change_mapping(
    request: Request,
    account_id: int,
    form: FormData = Depends(import_form),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Back from the preview to the mapping step, keeping the choices made."""
    account = owned_account(db, user, account_id)
    content = str(form.get("content", ""))
    mapping = _mapping_from(form) or importer.guess_mapping(importer.read_csv(content))
    return _map_page(request, user, account, content, mapping)


@router.post("/accounts/{account_id}/import/preview")
def preview(
    request: Request,
    account_id: int,
    form: FormData = Depends(import_form),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    account = owned_account(db, user, account_id)
    if error := _closed_error(account):
        return _upload_page(request, user, account, error, 400)
    if form.get("too_big"):
        return _upload_page(request, user, account, TOO_BIG, 413)
    content = str(form.get("content", ""))
    statement, mapping, error = _parse(content, form)
    if error:
        return _map_page(request, user, account, content, mapping, error=error, status=400)
    return _preview_page(request, db, user, account, content, statement, mapping)


@router.post("/accounts/{account_id}/import/confirm")
def confirm(
    request: Request,
    account_id: int,
    form: FormData = Depends(import_form),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Add the ticked rows and stamp the matched ones, in one commit; save the settings.

    ``add`` lists the file lines to add as new transactions: new rows are ticked by
    default, matched rows only if the user chose "import as new". A matched row left
    unticked gives its ID to the existing transaction (if that has none yet), so the
    next import skips it too. Rows already imported, and error rows, are never added.
    """
    account = owned_account(db, user, account_id)
    if error := _closed_error(account):
        return _upload_page(request, user, account, error, 400)
    if form.get("too_big"):
        return _upload_page(request, user, account, TOO_BIG, 413)
    content = str(form.get("content", ""))
    statement, mapping, error = _parse(content, form)
    if error:
        return _map_page(request, user, account, content, mapping, error=error, status=400)
    chosen = {int(v) for v in form.getlist("add") if str(v).isdigit()}

    added = matched = 0
    for verdict in importer.classify(statement.rows, _existing(db, account, statement)):
        row = verdict.row
        if verdict.status in (NEW, MATCH) and row.line in chosen:
            db.add(
                Transaction(
                    user_id=user.id,
                    account_id=account.id,
                    date=row.date,
                    payee=row.payee,
                    memo=row.memo,
                    amount=row.amount,
                    import_id=row.import_id,
                    status=CLEARED,  # the bank says it happened
                )
            )
            added += 1
        elif verdict.status == MATCH:
            existing = db.get(Transaction, verdict.match_id)
            if existing.import_id is None:
                existing.import_id = row.import_id
            if existing.status == UNCLEARED:  # a reconciled one stays reconciled
                existing.status = CLEARED
            matched += 1
    skipped = len(statement.rows) - added - matched

    saved, settings = _saved(db, account)
    if mapping is not None:
        first = mapping.header_rows - 1
        table = importer.read_csv(content)
        header = table[first] if 0 <= first < len(table) else []
        settings["csv"] = {"mapping": asdict(mapping), "header": header}
    elif statement.account_number:
        settings["ofx"] = {"account_number": statement.account_number}
    if saved is None:
        saved = ImportMapping(user_id=user.id, account_id=account.id)
        db.add(saved)
    saved.settings = json.dumps(settings)
    saved.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:  # the same rows were imported meanwhile, e.g. from another tab
        db.rollback()
        error = (
            "Some of these rows were imported meanwhile. Upload the file again to see what's left."
        )
        return _upload_page(request, user, account, error, 409)
    return RedirectResponse(
        f"/accounts/{account.id}/import?added={added}&matched={matched}&skipped={skipped}",
        status_code=303,
    )
