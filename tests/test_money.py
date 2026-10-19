import pytest

from zerobase.money import format_money, parse_money, plain_money


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12.34", 1234),
        ("12", 1200),
        ("0.5", 50),
        (".5", 50),
        ("-5.5", -550),
        ("£1,234.56", 123456),
        ("  $ 10 ", 1000),
        ("0.005", 1),  # rounds half up
        ("0.004", 0),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize(
    "text", ["", "   ", "abc", "1.2.3", "NaN", "Infinity", "1e999999", "1" + "0" * 12]
)
def test_parse_money_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_money(text)


def test_parse_money_none():
    with pytest.raises(ValueError):
        parse_money(None)


def test_format_money():
    assert format_money(0) == "£0.00"
    assert format_money(1234) == "£12.34"
    assert format_money(-5) == "-£0.05"
    assert format_money(123456789, "$") == "$1,234,567.89"


def test_plain_money_round_trips():
    for minor in (0, 5, 100, -250, 123456):
        assert parse_money(plain_money(minor)) == minor
