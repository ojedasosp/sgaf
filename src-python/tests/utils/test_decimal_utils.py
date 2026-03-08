"""Tests for decimal_utils — financial precision layer."""

from decimal import Decimal

import pytest

from app.utils.decimal_utils import from_db_string, to_db_string


class TestToDbString:
    def test_round_number(self):
        assert to_db_string(Decimal("1200")) == "1200.0000"

    def test_already_four_decimals(self):
        assert to_db_string(Decimal("1200.5000")) == "1200.5000"

    def test_fewer_than_four_decimals_padded(self):
        assert to_db_string(Decimal("1200.5")) == "1200.5000"

    def test_rounds_at_fifth_decimal(self):
        # 1.00005 rounds up to 1.0001 with ROUND_HALF_UP
        assert to_db_string(Decimal("1.00005")) == "1.0001"

    def test_zero(self):
        assert to_db_string(Decimal("0")) == "0.0000"

    def test_large_value(self):
        assert to_db_string(Decimal("999999999.9999")) == "999999999.9999"

    def test_rejects_float(self):
        with pytest.raises(TypeError, match="Expected decimal.Decimal"):
            to_db_string(1200.5)  # type: ignore[arg-type]

    def test_rejects_int(self):
        with pytest.raises(TypeError, match="Expected decimal.Decimal"):
            to_db_string(1200)  # type: ignore[arg-type]

    def test_rejects_string(self):
        with pytest.raises(TypeError, match="Expected decimal.Decimal"):
            to_db_string("1200.5")  # type: ignore[arg-type]


class TestFromDbString:
    def test_four_decimal_string(self):
        result = from_db_string("1200.5000")
        assert result == Decimal("1200.5000")
        assert isinstance(result, Decimal)

    def test_integer_string(self):
        result = from_db_string("1200")
        assert result == Decimal("1200")

    def test_zero_string(self):
        result = from_db_string("0.0000")
        assert result == Decimal("0.0000")

    def test_round_trip_precision(self):
        original = Decimal("1200.1234")
        stored = to_db_string(original)
        recovered = from_db_string(stored)
        assert recovered == original

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="empty string"):
            from_db_string("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="empty string"):
            from_db_string("   ")

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            from_db_string("not-a-number")

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            from_db_string("NaN")

    def test_rejects_infinity(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            from_db_string("Infinity")

    def test_rejects_neg_infinity(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            from_db_string("-Infinity")
