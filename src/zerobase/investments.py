"""Investment accounts: coin symbols and amounts held (TASK-M007)."""

import re
from decimal import Decimal, InvalidOperation

MAX_PLACES = 18  # ETH is divisible to 18 decimal places
MAX_WHOLE_DIGITS = 20
_SYMBOL = re.compile(r"[A-Z0-9]{1,10}")


def parse_symbol(text: str | None) -> str | None:
    """A coin's trading symbol, in capitals, or None when left blank.

    Raises ValueError with a user-presentable message on bad input.
    """
    cleaned = (text or "").strip().upper()
    if not cleaned:
        return None
    if not _SYMBOL.fullmatch(cleaned):
        raise ValueError("Coin: use the trading symbol, up to 10 letters or digits (e.g. BTC).")
    return cleaned


def parse_quantity(text: str | None) -> Decimal | None:
    """An amount held, exactly as entered (commas allowed), or None when left blank.

    Raises ValueError with a user-presentable message on bad input.
    """
    cleaned = (text or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("Amount held: that isn't a number.") from None
    if not value.is_finite():
        raise ValueError("Amount held: that isn't a number.")
    if value < 0:
        raise ValueError("Amount held can't be negative.")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_PLACES:
        raise ValueError(f"Amount held: at most {MAX_PLACES} decimal places.")
    if value >= Decimal(10) ** MAX_WHOLE_DIGITS:
        raise ValueError("Amount held: that's too large.")
    value = abs(value)  # no "-0"
    # Drop trailing zeros (0.2500 -> 0.25) without switching to exponent form.
    return Decimal(format(value.normalize(), "f")) if value else Decimal(0)
