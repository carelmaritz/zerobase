"""Money parsing and formatting. Amounts are integers in minor units (pence/cents)."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Anything at or above this (in major units) is rejected as a typo.
MAX_MAJOR = Decimal(10) ** 10

_NOISE = re.compile(r"[\s,£$€]")


def parse_money(text: str | None) -> int:
    """Parse user input such as '12.34', '1,234', '-5.5' or '£10' into minor units.

    Raises ValueError with a user-presentable message on bad input.
    """
    cleaned = _NOISE.sub("", text or "")
    if not cleaned:
        raise ValueError("Enter an amount.")
    try:
        value = Decimal(cleaned)
        if not value.is_finite():
            raise ValueError("That is not a valid amount.")
        if abs(value) >= MAX_MAJOR:
            raise ValueError("That amount is too large.")
        return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError("That is not a valid amount.") from None


def format_money(minor: int, symbol: str = "£") -> str:
    """Format minor units for display, e.g. -1234 -> '-£12.34'."""
    sign = "-" if minor < 0 else ""
    major, cents = divmod(abs(minor), 100)
    return f"{sign}{symbol}{major:,}.{cents:02d}"


def plain_money(minor: int) -> str:
    """Plain decimal string for form inputs, e.g. 1234 -> '12.34'."""
    sign = "-" if minor < 0 else ""
    major, cents = divmod(abs(minor), 100)
    return f"{sign}{major}.{cents:02d}"
