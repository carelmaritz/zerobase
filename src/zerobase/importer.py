"""Reading bank statement files (CSV and OFX) into rows ready to import (TASK-H006).

Pure functions: no database, no web. The import routes decode the upload, parse it with a
mapping (CSV) or as-is (OFX), then compare the rows with the account's transactions using
``classify``. Amounts are pence, parsed with ``money.parse_money``; never floats.

Every row gets an ``import_id``, unique within its account, so a re-imported or
overlapping file adds nothing twice:
- OFX: ``ofx:<FITID>``, the bank's own ID for the transaction.
- CSV (and OFX rows without a FITID): ``<date>:<amount>:<n>``, where ``n`` counts repeats
  of that date and amount within the file, so two identical coffees on one day are
  ``:1`` and ``:2`` (YNAB's approach).
"""

from __future__ import annotations

import csv
import html
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from .money import parse_money

MAX_BYTES = 1024 * 1024  # Starlette refuses larger form fields, and the text rides in one

# Offered in the mapping form, in this order; the guess prefers the earlier ones, so an
# ambiguous 01/02/2026 reads as 1 February (UK).
DATE_FORMATS = {
    "dd/mm/yyyy": "%d/%m/%Y",
    "dd/mm/yy": "%d/%m/%y",
    "yyyy-mm-dd": "%Y-%m-%d",
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd mon yyyy": "%d %b %Y",
    "mm/dd/yyyy": "%m/%d/%Y",
}

OFX_PREFIX = "ofx:"
IMPORT_ID_LENGTH = 255  # the column's size; OFX allows a FITID up to 255 characters


@dataclass(frozen=True)
class Mapping:
    """How to read a CSV. Columns are 0-based positions; ``None`` means not used.

    The amount is either one signed column (``amount_col``) or separate ``out_col`` and
    ``in_col``. ``flip_sign`` reverses the result, for banks that show spending as positive.
    """

    date_col: int
    date_format: str
    payee_col: int | None = None
    memo_col: int | None = None
    amount_col: int | None = None
    out_col: int | None = None
    in_col: int | None = None
    flip_sign: bool = False
    header_rows: int = 1

    def columns(self) -> list[int]:
        cols = (self.date_col, self.payee_col, self.memo_col, self.amount_col)
        return [c for c in (*cols, self.out_col, self.in_col) if c is not None]

    def problem(self) -> str | None:
        """Why this mapping can't be used, or None."""
        if self.date_format not in DATE_FORMATS:
            return "Choose a date format."
        if (self.amount_col is None) == (self.out_col is None and self.in_col is None):
            return "Choose either an amount column, or money out and money in columns."
        if self.amount_col is None and (self.out_col is None or self.in_col is None):
            return "Choose both a money out and a money in column."
        columns = self.columns()
        if len(columns) != len(set(columns)):
            return "Each column can only be used once."
        if min(columns) < 0 or not 0 <= self.header_rows <= 20:
            return "That mapping isn't valid."
        return None


@dataclass
class Row:
    """One statement line. ``error`` is set (and the rest may be blank) if it can't be read."""

    line: int  # 1-based line in the file, for messages
    date: date | None = None
    payee: str = ""
    memo: str = ""
    amount: int | None = None
    import_id: str | None = None
    error: str | None = None


@dataclass
class Statement:
    rows: list[Row]
    header: list[str] = field(default_factory=list)  # CSV only
    account_number: str | None = None  # OFX only


def decode(data: bytes) -> str:
    """UTF-8 (with or without a BOM), else Windows-1252, the usual home of a UK '£'."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def is_ofx(text: str) -> bool:
    head = text.lstrip()[:2000].upper()
    return head.startswith("OFXHEADER") or "<OFX>" in head


def _in_range(when: date) -> bool:
    return 1990 <= when.year <= 2100  # as for typed transactions


def parse_date(value: str, date_format: str) -> date | None:
    try:
        when = datetime.strptime(value.strip(), DATE_FORMATS[date_format]).date()
    except (KeyError, ValueError):
        return None
    return when if _in_range(when) else None


_DR_CR = re.compile(r"^(.*?)\s*(DR|CR)\.?$", re.IGNORECASE)


def parse_amount(value: str) -> int:
    """A statement amount in pence: '-12.34', '12.34 DR', '12.34 CR', '(12.34)', '+5'.

    Raises ValueError with a message fit for the preview.
    """
    text = value.strip()
    negative = False
    match = _DR_CR.match(text)
    if match:
        text, negative = match[1], match[2].upper() == "DR"
    if text.startswith("(") and text.endswith(")"):
        text, negative = text[1:-1], True
    amount = parse_money(text)
    return -abs(amount) if negative else amount


def read_csv(text: str) -> list[list[str]]:
    """All rows, cells stripped. The delimiter is whichever of , ; or tab the first line
    uses most (commas on a tie), which is steadier than ``csv.Sniffer`` on short files.
    """
    first = text.lstrip().split("\n", 1)[0]
    delimiter = max(",;\t", key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[cell.strip() for cell in row] for row in reader]


def guess_date_format(values: list[str]) -> str | None:
    """The first format that reads every non-blank value, or None."""
    values = [v for v in values if v.strip()]
    for name in DATE_FORMATS:
        if values and all(parse_date(v, name) for v in values):
            return name
    return None


_HEADER_WORDS = {
    "date": ("date", "posted", "transaction date"),
    "payee": ("payee", "description", "name", "merchant", "counter party", "details"),
    "memo": ("memo", "reference", "notes", "note", "narrative"),
    "amount": ("amount", "value"),
    "out": ("paid out", "money out", "debit", "out", "withdrawal", "spent"),
    "in": ("paid in", "money in", "credit", "in", "deposit", "received"),
}


def guess_mapping(rows: list[list[str]]) -> Mapping:
    """A starting point for the mapping form, from the first row's header names.

    Exact names win over names that merely contain a word, so "Balance" isn't an amount.
    The user confirms or corrects it, so a poor guess costs a few clicks.
    """
    header = [h.lower() for h in rows[0]] if rows else []
    taken: set[int] = set()

    def find(role: str) -> int | None:
        words = _HEADER_WORDS[role]
        for exact in (True, False):
            for i, name in enumerate(header):
                if i in taken or "balance" in name:
                    continue
                if any(name == w if exact else re.search(rf"\b{w}\b", name) for w in words):
                    taken.add(i)
                    return i
        return None

    date_col = find("date")
    # Money out/in columns first: "Debit Amount" and "Credit Amount" (Lloyds, Halifax)
    # contain the word "amount" but are a pair, not one signed column.
    out_col, in_col = find("out"), find("in")
    amount_col = None
    if out_col is None or in_col is None:
        taken.discard(out_col)
        taken.discard(in_col)
        out_col = in_col = None
        amount_col = find("amount")
    payee_col, memo_col = find("payee"), find("memo")
    date_col = 0 if date_col is None else date_col
    samples = [r[date_col] for r in rows[1:21] if len(r) > date_col]
    return Mapping(
        date_col=date_col,
        date_format=guess_date_format(samples) or "dd/mm/yyyy",
        payee_col=payee_col,
        memo_col=memo_col,
        amount_col=amount_col,
        out_col=out_col,
        in_col=in_col,
    )


def _cell(row: list[str], col: int | None) -> str:
    return row[col] if col is not None else ""


def _csv_amount(row: list[str], mapping: Mapping) -> int:
    if mapping.amount_col is not None:
        amount = parse_amount(row[mapping.amount_col])
    else:
        out, into = row[mapping.out_col].strip(), row[mapping.in_col].strip()
        if bool(out) == bool(into):
            raise ValueError("Expected an amount in exactly one of money out and money in.")
        amount = -abs(parse_amount(out)) if out else abs(parse_amount(into))
    return -amount if mapping.flip_sign else amount


def parse_csv(text: str, mapping: Mapping) -> Statement:
    """Rows after the header, each parsed or carrying the reason it couldn't be."""
    table = read_csv(text)
    header = table[mapping.header_rows - 1] if 0 < mapping.header_rows <= len(table) else []
    needed = max(mapping.columns()) + 1
    rows = []
    for line, cells in enumerate(table[mapping.header_rows :], start=mapping.header_rows + 1):
        if not any(cells):
            continue  # blank line
        row = Row(line=line)
        rows.append(row)
        if len(cells) < needed:
            row.error = f"This row has {len(cells)} columns; the mapping needs {needed}."
            continue
        row.payee = _cell(cells, mapping.payee_col)[:100]
        row.memo = _cell(cells, mapping.memo_col)[:255]
        row.date = parse_date(cells[mapping.date_col], mapping.date_format)
        if row.date is None:
            value, wanted = cells[mapping.date_col], mapping.date_format
            row.error = f"“{value}” isn't a date in the format {wanted}."
            continue
        try:
            row.amount = _csv_amount(cells, mapping)
        except ValueError as exc:
            row.error = f"Amount: {exc}"
            continue
        if row.amount == 0:
            row.error = "The amount is zero."
    _number_rows(rows)
    return Statement(rows=rows, header=header)


def _number_rows(rows: list[Row]) -> None:
    """Give readable rows without an ID a date-amount-occurrence one."""
    seen: Counter[tuple[date, int]] = Counter()
    for row in rows:
        if row.error is None and row.import_id is None:
            seen[(row.date, row.amount)] += 1
            row.import_id = f"{row.date.isoformat()}:{row.amount}:{seen[(row.date, row.amount)]}"


# OFX 1.x is SGML: aggregates like <STMTTRN> are closed, but leaf values often aren't
# ("<TRNAMT>-12.34" then a newline). OFX 2.x is XML. Reading a leaf as "<TAG>" up to the
# next "<" or line end handles both.
_TRANSACTION = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)
_LEAF = re.compile(r"<([A-Z0-9.]+)>([^<\r\n]*)", re.IGNORECASE)
_ACCOUNT = re.compile(
    r"<(?:BANKACCTFROM|CCACCTFROM)>.*?<ACCTID>([^<\r\n]*)", re.IGNORECASE | re.DOTALL
)


def _leaves(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for tag, value in _LEAF.findall(block):
        values.setdefault(tag.upper(), html.unescape(value.strip()))
    return values


def _ofx_amount(value: str) -> int:
    if "," in value and "." not in value:
        value = value.replace(",", ".")  # some banks write a decimal comma
    return parse_amount(value)


def parse_ofx(text: str) -> Statement:
    """The statement's transactions, and the account number it is for."""
    account = _ACCOUNT.search(text)
    rows: list[Row] = []
    fitids: set[str] = set()
    for number, match in enumerate(_TRANSACTION.finditer(text), start=1):
        values = _leaves(match[1])
        row = Row(line=number)
        rows.append(row)
        name, memo = values.get("NAME", ""), values.get("MEMO", "")
        row.payee, row.memo = (name or memo)[:100], (memo if name else "")[:255]
        posted = values.get("DTPOSTED", "")
        try:
            row.date = datetime.strptime(posted[:8], "%Y%m%d").date()
        except ValueError:
            row.date = None
        if row.date is None or not _in_range(row.date):
            row.date, row.error = None, f"“{posted}” isn't a valid date."
            continue
        try:
            row.amount = _ofx_amount(values.get("TRNAMT", ""))
        except ValueError as exc:
            row.error = f"Amount: {exc}"
            continue
        if row.amount == 0:
            row.error = "The amount is zero."
            continue
        fitid = values.get("FITID", "")
        if fitid:
            if fitid in fitids:
                row.error = "This transaction's ID appears twice in the file."
                continue
            fitids.add(fitid)
            row.import_id = f"{OFX_PREFIX}{fitid}"[:IMPORT_ID_LENGTH]
    _number_rows(rows)
    return Statement(rows=rows, account_number=account[1].strip() if account else None)


# --- Comparing with the account's transactions ---------------------------------------

NEW, IMPORTED, MATCH, ERROR = "new", "imported", "match", "error"
MATCH_DAYS = 3


@dataclass(frozen=True)
class Existing:
    """What ``classify`` needs to know about a transaction already in the account."""

    id: int
    date: date
    amount: int
    import_id: str | None


@dataclass
class Verdict:
    row: Row
    status: str  # NEW, IMPORTED, MATCH or ERROR
    match_id: int | None = None  # the existing transaction, for MATCH


def _is_ofx_id(import_id: str) -> bool:
    return import_id.startswith(OFX_PREFIX)


def classify(rows: list[Row], existing: list[Existing]) -> list[Verdict]:
    """Decide what importing each row would do.

    - IMPORTED: its ``import_id`` is already in the account; it's skipped.
    - MATCH: probably the same as a transaction entered by hand (no ``import_id``), or
      imported from the other format (CSV and OFX IDs never match each other): same
      amount, dates at most ``MATCH_DAYS`` apart. Each one is matched at most once, to the
      closest date (then the lowest ID).
    - NEW: neither; it would be added.
    """
    known = {e.import_id for e in existing if e.import_id}
    used: set[int] = set()
    verdicts = []
    for row in rows:
        if row.error:
            verdicts.append(Verdict(row, ERROR))
            continue
        if row.import_id in known:
            verdicts.append(Verdict(row, IMPORTED))
            continue
        candidates = [
            e
            for e in existing
            if e.id not in used
            and e.amount == row.amount
            and abs((e.date - row.date).days) <= MATCH_DAYS
            and (e.import_id is None or _is_ofx_id(e.import_id) != _is_ofx_id(row.import_id))
        ]
        if candidates:
            best = min(candidates, key=lambda e: (abs((e.date - row.date).days), e.id))
            used.add(best.id)
            verdicts.append(Verdict(row, MATCH, best.id))
        else:
            verdicts.append(Verdict(row, NEW))
    return verdicts
