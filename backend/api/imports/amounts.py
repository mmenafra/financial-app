"""Parse European/Chilean-style amount strings (e.g. 1.020,45 or 21,46) without a leading $."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_chilean_decimal(token: str) -> Decimal:
    """
    Parse amounts like '1.699.990', '6.713', '-403.521' (thousands=dot, decimal=comma) or
    with an optional $ prefix.
    """
    s = token.replace("$", "").strip().replace(" ", "")
    if not s:
        raise ValueError("Empty amount token.")
    negative = s.startswith("-")
    s = s[1:] if negative else s
    if not s:
        raise ValueError("Empty amount after sign.")
    if "," in s:
        int_part, frac = s.rsplit(",", 1)
        int_part = int_part.replace(".", "")
        normalized = f"{int_part}.{frac}"
    else:
        normalized = s.replace(".", "")
    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {token!r}") from exc
    return -value if negative else value
