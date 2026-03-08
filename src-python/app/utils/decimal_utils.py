"""Decimal ↔ SQLite TEXT conversion utilities.

Financial values are stored in SQLite as TEXT with 4 decimal places minimum.
Never use float at any layer — always Decimal.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

FOUR_PLACES = Decimal("0.0001")


def to_db_string(value: Decimal) -> str:
    """Format a Decimal to a 4-decimal-place TEXT string for SQLite storage.

    Raises TypeError if value is not a Decimal (e.g., float or int passed directly).
    """
    if not isinstance(value, Decimal):
        raise TypeError(
            f"Expected decimal.Decimal, got {type(value).__name__}. "
            "Never pass float to financial storage functions."
        )
    return str(value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP))


def from_db_string(value: str) -> Decimal:
    """Parse a TEXT value from SQLite to Decimal.

    Raises ValueError on empty string or non-numeric input.
    """
    if not value or not value.strip():
        raise ValueError("Cannot convert empty string to Decimal")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot convert '{value}' to Decimal: {exc}") from exc
    if result.is_nan() or result.is_infinite():
        raise ValueError(
            f"Cannot convert '{value}' to Decimal: NaN and Infinity are not valid financial values"
        )
    return result
