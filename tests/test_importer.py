"""Reading statement files, and deciding what importing them would do (TASK-H006).

The files below are made up in common UK layouts; they aren't copied from any bank.
"""

from datetime import date

import pytest

from zerobase.importer import (
    ERROR,
    IMPORTED,
    MATCH,
    NEW,
    Existing,
    Mapping,
    classify,
    decode,
    guess_date_format,
    guess_mapping,
    is_ofx,
    parse_amount,
    parse_csv,
    parse_ofx,
    read_csv,
)

SIGNED = """Date,Description,Reference,Amount,Balance
05/11/2026,Tesco,Card 1234,-12.34,987.66
05/11/2026,Coffee Shop,,-3.00,984.66
05/11/2026,Coffee Shop,,-3.00,981.66
06/11/2026,Employer Ltd,Salary,"1,234.56","2,216.22"
"""

IN_OUT = """Transaction Date,Transaction Description,Paid out,Paid in,Balance
01 Nov 2026,DIRECT DEBIT GAS CO,45.00,,955.00
02 Nov 2026,TRANSFER FROM SAVINGS,,100.00,1055.00
"""


def signed_mapping(**changes) -> Mapping:
    base = dict(date_col=0, date_format="dd/mm/yyyy", payee_col=1, memo_col=2, amount_col=3)
    return Mapping(**{**base, **changes})


# --- CSV -------------------------------------------------------------------------------


def test_signed_amount_column():
    statement = parse_csv(SIGNED, signed_mapping())
    assert statement.header == ["Date", "Description", "Reference", "Amount", "Balance"]
    tesco, coffee1, coffee2, salary = statement.rows
    assert (tesco.date, tesco.payee, tesco.memo, tesco.amount) == (
        date(2026, 11, 5),
        "Tesco",
        "Card 1234",
        -1234,
    )
    assert salary.amount == 123456
    assert all(r.error is None for r in statement.rows)
    # Two identical coffees on one day are both kept, with different IDs.
    assert (coffee1.import_id, coffee2.import_id) == (
        "2026-11-05:-300:1",
        "2026-11-05:-300:2",
    )
    assert tesco.line == 2


def test_separate_out_and_in_columns_and_month_names():
    mapping = Mapping(date_col=0, date_format="dd mon yyyy", payee_col=1, out_col=2, in_col=3)
    gas, savings = parse_csv(IN_OUT, mapping).rows
    assert (gas.date, gas.amount) == (date(2026, 11, 1), -4500)
    assert (savings.payee, savings.amount) == ("TRANSFER FROM SAVINGS", 10000)


def test_out_column_already_negative_is_still_spending():
    text = "Date,Name,Out,In\n01/11/2026,Shop,-5.00,\n"
    mapping = Mapping(date_col=0, date_format="dd/mm/yyyy", payee_col=1, out_col=2, in_col=3)
    assert parse_csv(text, mapping).rows[0].amount == -500


def test_flip_sign():
    text = "Date,Name,Amount\n01/11/2026,Card spend,12.00\n02/11/2026,Payment,-50.00\n"
    mapping = Mapping(
        date_col=0, date_format="dd/mm/yyyy", payee_col=1, amount_col=2, flip_sign=True
    )
    spend, payment = parse_csv(text, mapping).rows
    assert (spend.amount, payment.amount) == (-1200, 5000)


@pytest.mark.parametrize(
    "text, pence",
    [
        ("-12.34", -1234),
        ("12.34", 1234),
        ("+5", 500),
        ("12.34 DR", -1234),
        ("12.34DR", -1234),
        ("12.34 CR", 1234),
        ("(12.34)", -1234),
        ("£1,234.56", 123456),
        ("1 234.56", 123456),
    ],
)
def test_amount_formats(text, pence):
    assert parse_amount(text) == pence


@pytest.mark.parametrize(
    "value, fmt, expected",
    [
        ("31/01/2026", "dd/mm/yyyy", date(2026, 1, 31)),
        ("2026-01-31", "yyyy-mm-dd", date(2026, 1, 31)),
        ("01/02/2026", "dd/mm/yyyy", date(2026, 2, 1)),
        ("01/02/2026", "mm/dd/yyyy", date(2026, 1, 2)),
        ("31/01/26", "dd/mm/yy", date(2026, 1, 31)),
        ("31-01-2026", "dd-mm-yyyy", date(2026, 1, 31)),
    ],
)
def test_date_formats(value, fmt, expected):
    text = f"Date,Amount\n{value},1.00\n"
    row = parse_csv(text, Mapping(date_col=0, date_format=fmt, amount_col=1)).rows[0]
    assert row.date == expected


def test_date_format_guess_prefers_uk_and_rules_out_impossible_days():
    assert guess_date_format(["01/02/2026", "03/04/2026"]) == "dd/mm/yyyy"
    assert guess_date_format(["01/31/2026"]) == "mm/dd/yyyy"
    assert guess_date_format(["2026-01-31"]) == "yyyy-mm-dd"
    assert guess_date_format(["01 Nov 2026"]) == "dd mon yyyy"
    assert guess_date_format(["soon"]) is None


def test_bad_rows_are_reported_not_dropped():
    text = (
        "Date,Name,Amount\n"
        "31/02/2026,Bad date,-1.00\n"
        "01/11/2026,Bad amount,lots\n"
        "01/11/2026,Zero,0.00\n"
        "01/11/2026\n"
        "\n"
        "02/11/2026,Fine,-2.00\n"
    )
    rows = parse_csv(
        text, Mapping(date_col=0, date_format="dd/mm/yyyy", payee_col=1, amount_col=2)
    ).rows
    errors = [(r.line, r.error) for r in rows]
    assert errors[0] == (2, "“31/02/2026” isn't a date in the format dd/mm/yyyy.")
    assert errors[1][0] == 3 and errors[1][1].startswith("Amount:")
    assert errors[2] == (4, "The amount is zero.")
    assert errors[3] == (5, "This row has 1 columns; the mapping needs 3.")
    assert errors[4] == (7, None)  # the blank line 6 is skipped silently
    assert [r.import_id for r in rows] == [None, None, None, None, "2026-11-02:-200:1"]


def test_both_or_neither_in_and_out_is_an_error():
    text = "Date,Out,In\n01/11/2026,1.00,2.00\n01/11/2026,,\n"
    mapping = Mapping(date_col=0, date_format="dd/mm/yyyy", out_col=1, in_col=2)
    assert all("exactly one" in r.error for r in parse_csv(text, mapping).rows)


def test_empty_file_and_header_only():
    assert parse_csv("", signed_mapping()).rows == []
    statement = parse_csv("Date,Description,Reference,Amount\n", signed_mapping())
    assert statement.rows == [] and statement.header[0] == "Date"


def test_long_text_is_cut_to_the_column_sizes():
    text = f"Date,Name,Memo,Amount\n01/11/2026,{'p' * 150},{'m' * 300},1.00\n"
    row = parse_csv(text, signed_mapping()).rows[0]
    assert (len(row.payee), len(row.memo)) == (100, 255)


def test_semicolons_and_tabs():
    for sep in (";", "\t"):
        text = (
            sep.join(["Date", "Name", "Amount"]) + "\n" + sep.join(["01/11/2026", "A, B", "-1.50"])
        )
        assert read_csv(text)[1] == ["01/11/2026", "A, B", "-1.50"]


def test_decode_utf8_bom_and_windows_1252():
    assert decode("﻿Date,Amount\n".encode()) == "Date,Amount\n"
    assert decode("Coffee £3".encode("cp1252")) == "Coffee £3"
    assert decode("Café £3".encode()) == "Café £3"


def test_guess_mapping_from_headers():
    mapping = guess_mapping(read_csv(SIGNED))
    assert mapping == Mapping(
        date_col=0, date_format="dd/mm/yyyy", payee_col=1, memo_col=2, amount_col=3
    )
    mapping = guess_mapping(read_csv(IN_OUT))
    assert (mapping.date_col, mapping.payee_col, mapping.out_col, mapping.in_col) == (0, 1, 2, 3)
    assert mapping.amount_col is None and mapping.date_format == "dd mon yyyy"
    assert mapping.problem() is None


def test_guess_mapping_reads_debit_and_credit_amount_as_a_pair():
    # Lloyds and Halifax: both columns contain "amount", but they're money out and in.
    text = (
        "Transaction Date,Transaction Type,Sort Code,Account Number,"
        "Transaction Description,Debit Amount,Credit Amount,Balance\n"
        "07/11/2026,DEB,'30-00-00,12345678,TESCO STORES,12.34,,987.66\n"
        "06/11/2026,FPI,'30-00-00,12345678,EMPLOYER LTD,,1000.00,1000.00\n"
    )
    mapping = guess_mapping(read_csv(text))
    assert (mapping.date_col, mapping.payee_col, mapping.out_col, mapping.in_col) == (0, 4, 5, 6)
    assert mapping.amount_col is None and mapping.problem() is None
    amounts = [row.amount for row in parse_csv(text, mapping).rows]
    assert amounts == [-1234, 100000]


def test_mapping_problems():
    assert signed_mapping().problem() is None
    assert signed_mapping(date_format="whenever").problem() == "Choose a date format."
    assert "either" in signed_mapping(out_col=4, in_col=5).problem()
    assert "both" in signed_mapping(amount_col=None, out_col=4).problem()
    assert "once" in signed_mapping(payee_col=0).problem()


# --- OFX -------------------------------------------------------------------------------

OFX_SGML = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252

<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20261107</SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STMTRS>
<CURDEF>GBP
<BANKACCTFROM>
<BANKID>601234
<ACCTID>12345678
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20261101
<DTEND>20261107
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261105120000.000[0:GMT]
<TRNAMT>-12.34
<FITID>202611050001
<NAME>TESCO STORES
<MEMO>CARD 1234
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20261106
<TRNAMT>1234.56
<FITID>202611060001
<NAME>M&amp;S REFUND
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261106
<TRNAMT>-3,00
<MEMO>COFFEE £
</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""

OFX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>
<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS>
<CCACCTFROM><ACCTID>XXXX9876</ACCTID></CCACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261103</DTPOSTED><TRNAMT>-20.00</TRNAMT><FITID>A1</FITID><PAYEE><NAME>TRAINLINE</NAME></PAYEE></STMTTRN>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>notadate</DTPOSTED><TRNAMT>-1.00</TRNAMT><FITID>A2</FITID></STMTTRN>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261104</DTPOSTED><TRNAMT>-1.00</TRNAMT><FITID>A1</FITID></STMTTRN>
</BANKTRANLIST>
</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>
"""


def test_ofx_1_sgml():
    assert is_ofx(OFX_SGML) and not is_ofx(SIGNED)
    statement = parse_ofx(decode(OFX_SGML.encode("cp1252")))
    assert statement.account_number == "12345678"
    tesco, refund, coffee = statement.rows
    assert (tesco.date, tesco.amount, tesco.payee, tesco.memo, tesco.import_id) == (
        date(2026, 11, 5),
        -1234,
        "TESCO STORES",
        "CARD 1234",
        "ofx:202611050001",
    )
    assert (refund.payee, refund.amount) == ("M&S REFUND", 123456)
    # No NAME: the memo becomes the payee. No FITID: a date-amount-occurrence ID.
    assert (coffee.payee, coffee.memo, coffee.amount) == ("COFFEE £", "", -300)
    assert coffee.import_id == "2026-11-06:-300:1"


def test_ofx_2_xml_with_bad_rows():
    assert is_ofx(OFX_XML)
    statement = parse_ofx(OFX_XML)
    assert statement.account_number == "XXXX9876"
    train, bad_date, repeat = statement.rows
    assert (train.payee, train.amount, train.import_id) == ("TRAINLINE", -2000, "ofx:A1")
    assert bad_date.error == "“notadate” isn't a valid date."
    assert repeat.error == "This transaction's ID appears twice in the file."


def test_ofx_without_transactions():
    statement = parse_ofx("OFXHEADER:100\n\n<OFX><BANKTRANLIST></BANKTRANLIST></OFX>")
    assert statement.rows == [] and statement.account_number is None


# --- Duplicates and matches ------------------------------------------------------------


def rows_of(text=SIGNED):
    return parse_csv(text, signed_mapping()).rows


def test_reimporting_finds_every_row_already_imported():
    rows = rows_of()
    existing = [Existing(i, r.date, r.amount, r.import_id) for i, r in enumerate(rows, 1)]
    assert [v.status for v in classify(rows_of(), existing)] == [IMPORTED] * 4


def test_an_overlapping_file_adds_only_new_rows():
    first = rows_of(SIGNED.split("05/11/2026,Coffee Shop")[0])  # header + Tesco
    existing = [Existing(1, first[0].date, first[0].amount, first[0].import_id)]
    statuses = [v.status for v in classify(rows_of(), existing)]
    assert statuses == [IMPORTED, NEW, NEW, NEW]


def test_a_second_identical_coffee_is_new_when_one_was_imported():
    one = rows_of()[1]
    existing = [Existing(1, one.date, one.amount, one.import_id)]
    statuses = [v.status for v in classify(rows_of(), existing)]
    assert statuses == [NEW, IMPORTED, NEW, NEW]


def test_hand_entered_transactions_are_matched_to_the_closest_date():
    rows = rows_of()  # Tesco -12.34 on 5 Nov
    existing = [
        Existing(10, date(2026, 11, 8), -1234, None),  # 3 days: in range
        Existing(11, date(2026, 11, 4), -1234, None),  # 1 day: closer
        Existing(12, date(2026, 11, 1), -1234, None),  # 4 days: too far
    ]
    tesco = classify(rows, existing)[0]
    assert (tesco.status, tesco.match_id) == (MATCH, 11)


def test_each_hand_entered_transaction_matches_at_most_once():
    existing = [Existing(20, date(2026, 11, 5), -300, None)]
    verdicts = classify(rows_of(), existing)
    assert [(v.status, v.match_id) for v in verdicts[1:3]] == [(MATCH, 20), (NEW, None)]


def test_rows_imported_in_the_other_format_are_matched_not_doubled():
    csv_imported = Existing(30, date(2026, 11, 5), -1234, "2026-11-05:-1234:1")
    ofx_rows = parse_ofx(OFX_SGML).rows
    assert classify(ofx_rows[:1], [csv_imported])[0].match_id == 30

    ofx_imported = Existing(31, date(2026, 11, 5), -1234, "ofx:202611050001")
    assert classify(rows_of(), [ofx_imported])[0].match_id == 31
    # Same format, different ID: a different transaction, not a match.
    other_csv = Existing(32, date(2026, 11, 4), -1234, "2026-11-04:-1234:1")
    assert classify(rows_of(), [other_csv])[0].status == NEW


def test_error_rows_stay_errors():
    rows = parse_csv(
        "Date,Amount\nnope,1.00\n", Mapping(date_col=0, date_format="dd/mm/yyyy", amount_col=1)
    ).rows
    assert classify(rows, [])[0].status == ERROR
