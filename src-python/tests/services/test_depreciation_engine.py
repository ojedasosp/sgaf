"""Tests for DepreciationEngine — NIIF Sección 17 three-method depreciation service.

Pure unit tests: no database fixtures, no Flask client required.
All test inputs use decimal.Decimal — float inputs are tested only in validation tests.

Reference inputs from AC:
    historical_cost = 10000, salvage_value = 1000, useful_life_months = 60
    depreciable_base = 9000
"""

import random
from decimal import Decimal

import pytest

from app.services.depreciation_engine import DepreciationEngine

# ──────────────────────────────────────────────────────────────────────────────
# Reference inputs (AC-mandated)
# ──────────────────────────────────────────────────────────────────────────────
COST = Decimal("10000")
SALVAGE = Decimal("1000")
LIFE = 60
DEPRECIABLE_BASE = Decimal("9000.0000")


@pytest.fixture
def engine() -> DepreciationEngine:
    return DepreciationEngine()


def full_schedule(eng: DepreciationEngine, cost, salvage, life, method) -> list[dict]:
    """Return list of calculate_period results for all periods 1..life."""
    return [eng.calculate_period(cost, salvage, life, method, p) for p in range(1, life + 1)]


# ──────────────────────────────────────────────────────────────────────────────
class TestStraightLine:
    """AC-2: straight_line reference values and schedule properties."""

    def test_period_1_reference(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", 1)
        assert result["monthly_charge"] == Decimal("150.0000")
        assert result["accumulated_depreciation"] == Decimal("150.0000")
        assert result["net_book_value"] == Decimal("9850.0000")

    def test_period_30_midpoint(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", 30)
        assert result["monthly_charge"] == Decimal("150.0000")
        assert result["accumulated_depreciation"] == Decimal("4500.0000")
        assert result["net_book_value"] == Decimal("5500.0000")

    def test_period_60_closes_at_salvage(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", LIFE)
        assert result["net_book_value"] == Decimal("1000.0000")
        assert result["accumulated_depreciation"] == Decimal("9000.0000")

    def test_full_schedule_sums_to_depreciable_base(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "straight_line")
        total = sum((r["monthly_charge"] for r in schedule), Decimal("0"))
        assert total == DEPRECIABLE_BASE

    def test_return_types_are_decimal(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", 1)
        for key in ("monthly_charge", "accumulated_depreciation", "net_book_value"):
            assert isinstance(result[key], Decimal), f"{key} must be Decimal, not float"

    def test_no_float_in_any_period(self, engine):
        for p in range(1, LIFE + 1):
            result = engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", p)
            for key, val in result.items():
                assert isinstance(
                    val, Decimal
                ), f"Period {p} {key}: expected Decimal, got {type(val)}"

    def test_non_exact_division_rounding_drift(self, engine):
        """M2: Values that don't divide evenly must still sum to depreciable base."""
        cost, salvage, life = Decimal("10001"), Decimal("1000"), 60
        dep_base = Decimal("9001.0000")
        schedule = full_schedule(engine, cost, salvage, life, "straight_line")
        total = sum((r["monthly_charge"] for r in schedule), Decimal("0"))
        assert total == dep_base
        assert schedule[-1]["net_book_value"] == Decimal("1000.0000")


# ──────────────────────────────────────────────────────────────────────────────
class TestSumOfDigits:
    """AC-3: sum_of_digits ordering and schedule sum properties."""

    def test_period_1_is_highest_charge(self, engine):
        r1 = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", 1)
        r2 = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", 2)
        assert r1["monthly_charge"] > r2["monthly_charge"]

    def test_period_60_is_lowest_charge(self, engine):
        r59 = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", 59)
        r60 = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", LIFE)
        assert r60["monthly_charge"] < r59["monthly_charge"]

    def test_charges_are_monotonically_decreasing(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "sum_of_digits")
        charges = [r["monthly_charge"] for r in schedule]
        # Each charge must be <= the previous (monotone non-increasing; final may equal prev)
        for i in range(1, len(charges)):
            assert (
                charges[i] <= charges[i - 1]
            ), f"Period {i+1} charge {charges[i]} > period {i} charge {charges[i-1]}"

    def test_full_schedule_sums_to_depreciable_base(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "sum_of_digits")
        total = sum((r["monthly_charge"] for r in schedule), Decimal("0"))
        assert total == DEPRECIABLE_BASE

    def test_period_60_nbv_equals_salvage(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", LIFE)
        assert result["net_book_value"] == Decimal("1000.0000")
        assert result["accumulated_depreciation"] == Decimal("9000.0000")

    def test_return_types_are_decimal(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", 1)
        for key in ("monthly_charge", "accumulated_depreciation", "net_book_value"):
            assert isinstance(result[key], Decimal), f"{key} must be Decimal, not float"

    def test_all_values_quantized_to_4_places(self, engine):
        """M4: Every return value must have exactly 4 decimal places."""
        for p in range(1, LIFE + 1):
            result = engine.calculate_period(COST, SALVAGE, LIFE, "sum_of_digits", p)
            for key, val in result.items():
                assert val == val.quantize(
                    Decimal("0.0001")
                ), f"Period {p} {key}: {val} not quantized to 4 places"


# ──────────────────────────────────────────────────────────────────────────────
class TestDecliningBalance:
    """AC-4: declining_balance floor guarantee and schedule sum properties."""

    def test_nbv_never_below_salvage_all_periods(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "declining_balance")
        for i, result in enumerate(schedule, start=1):
            assert result["net_book_value"] >= Decimal(
                "1000.0000"
            ), f"Period {i}: net_book_value {result['net_book_value']} < salvage 1000.0000"

    def test_period_60_closes_at_salvage(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "declining_balance", LIFE)
        assert result["net_book_value"] == Decimal("1000.0000")
        assert result["accumulated_depreciation"] == Decimal("9000.0000")

    def test_full_schedule_sums_to_depreciable_base(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "declining_balance")
        total = sum((r["monthly_charge"] for r in schedule), Decimal("0"))
        assert total == DEPRECIABLE_BASE

    def test_charges_are_non_negative_all_periods(self, engine):
        schedule = full_schedule(engine, COST, SALVAGE, LIFE, "declining_balance")
        for i, result in enumerate(schedule, start=1):
            assert result["monthly_charge"] >= Decimal(
                "0"
            ), f"Period {i}: negative monthly_charge {result['monthly_charge']}"

    def test_return_types_are_decimal(self, engine):
        result = engine.calculate_period(COST, SALVAGE, LIFE, "declining_balance", 1)
        for key in ("monthly_charge", "accumulated_depreciation", "net_book_value"):
            assert isinstance(result[key], Decimal), f"{key} must be Decimal, not float"

    def test_all_values_quantized_to_4_places(self, engine):
        """M4: Every return value must have exactly 4 decimal places."""
        for p in range(1, LIFE + 1):
            result = engine.calculate_period(COST, SALVAGE, LIFE, "declining_balance", p)
            for key, val in result.items():
                assert val == val.quantize(
                    Decimal("0.0001")
                ), f"Period {p} {key}: {val} not quantized to 4 places"

    def test_salvage_zero_uses_double_declining_rate(self, engine):
        """M3: When salvage=0, rate should be 2/n (double-declining), not 1."""
        cost, life = Decimal("10000"), 60
        result = engine.calculate_period(cost, Decimal("0"), life, "declining_balance", 1)
        # Double-declining rate = 2/60 ≈ 0.0333...; first charge = 10000 * 2/60 ≈ 333.3333
        expected_first_charge = (cost * Decimal("2") / Decimal(life)).quantize(Decimal("0.0001"))
        assert result["monthly_charge"] == expected_first_charge, (
            f"Expected first charge {expected_first_charge} with double-declining rate, "
            f"got {result['monthly_charge']}"
        )


# ──────────────────────────────────────────────────────────────────────────────
class TestBoundaryCases:
    """AC-6 boundary inputs: salvage=0 and life=1 month for all methods."""

    @pytest.mark.parametrize("method", ["straight_line", "sum_of_digits", "declining_balance"])
    def test_salvage_zero_full_schedule_sums_to_cost(self, engine, method):
        """When salvage=0 total depreciation must equal historical_cost."""
        cost, salvage, life = Decimal("10000"), Decimal("0"), 60
        schedule = full_schedule(engine, cost, salvage, life, method)
        total = sum((r["monthly_charge"] for r in schedule), Decimal("0"))
        assert total == Decimal("10000.0000"), f"{method}: expected total 10000.0000, got {total}"

    @pytest.mark.parametrize("method", ["straight_line", "sum_of_digits", "declining_balance"])
    def test_salvage_zero_nbv_zero_at_end(self, engine, method):
        """Final period NBV must be 0.0000 when salvage_value=0."""
        result = engine.calculate_period(Decimal("10000"), Decimal("0"), 60, method, 60)
        assert result["net_book_value"] == Decimal(
            "0.0000"
        ), f"{method}: final NBV should be 0.0000, got {result['net_book_value']}"

    @pytest.mark.parametrize("method", ["straight_line", "sum_of_digits", "declining_balance"])
    def test_life_1_month_fully_depreciates(self, engine, method):
        """With life=1 month a single period must depreciate the full depreciable base."""
        cost, salvage = Decimal("5000"), Decimal("1000")
        result = engine.calculate_period(cost, salvage, 1, method, 1)
        assert result["monthly_charge"] == Decimal(
            "4000.0000"
        ), f"{method}: expected charge 4000.0000, got {result['monthly_charge']}"
        assert result["accumulated_depreciation"] == Decimal("4000.0000")
        assert result["net_book_value"] == Decimal("1000.0000")

    @pytest.mark.parametrize("method", ["straight_line", "sum_of_digits", "declining_balance"])
    def test_cost_equals_salvage_zero_depreciation(self, engine, method):
        """When cost == salvage, depreciable base is 0 — all charges must be 0."""
        result = engine.calculate_period(Decimal("5000"), Decimal("5000"), 12, method, 1)
        assert result["monthly_charge"] == Decimal("0.0000")
        assert result["accumulated_depreciation"] == Decimal("0.0000")
        assert result["net_book_value"] == Decimal("5000.0000")

    @pytest.mark.parametrize("method", ["straight_line", "sum_of_digits", "declining_balance"])
    def test_salvage_zero_nbv_never_negative(self, engine, method):
        """NBV must never go below zero when salvage_value=0."""
        schedule = full_schedule(engine, Decimal("10000"), Decimal("0"), 60, method)
        for i, result in enumerate(schedule, start=1):
            assert result["net_book_value"] >= Decimal(
                "0"
            ), f"{method} period {i}: NBV {result['net_book_value']} < 0"


# ──────────────────────────────────────────────────────────────────────────────
class TestDeterminism:
    """AC-5: identical inputs must produce bit-identical outputs on every call."""

    def test_100_calls_straight_line_produce_identical_results(self, engine):
        params = (COST, SALVAGE, LIFE, "straight_line", 30)
        first = engine.calculate_period(*params)
        for _ in range(99):
            assert engine.calculate_period(*params) == first

    def test_100_calls_sum_of_digits_produce_identical_results(self, engine):
        params = (COST, SALVAGE, LIFE, "sum_of_digits", 1)
        first = engine.calculate_period(*params)
        for _ in range(99):
            assert engine.calculate_period(*params) == first

    def test_100_calls_declining_balance_produce_identical_results(self, engine):
        params = (COST, SALVAGE, LIFE, "declining_balance", 59)
        first = engine.calculate_period(*params)
        for _ in range(99):
            assert engine.calculate_period(*params) == first

    def test_all_methods_deterministic_across_random_call_order(self, engine):
        inputs = [
            (COST, SALVAGE, LIFE, "straight_line", 1),
            (COST, SALVAGE, LIFE, "sum_of_digits", 30),
            (COST, SALVAGE, LIFE, "declining_balance", 59),
        ]
        first_results = [engine.calculate_period(*inp) for inp in inputs]
        rng = random.Random(42)
        for _ in range(50):
            shuffled = inputs.copy()
            rng.shuffle(shuffled)
            for inp in shuffled:
                idx = inputs.index(inp)
                assert (
                    engine.calculate_period(*inp) == first_results[idx]
                ), f"Non-deterministic result for {inp[3]} period {inp[4]}"


# ──────────────────────────────────────────────────────────────────────────────
class TestValidation:
    """Input validation raises correct exception types and messages."""

    def test_float_historical_cost_raises_type_error(self, engine):
        with pytest.raises(TypeError, match="historical_cost must be Decimal"):
            engine.calculate_period(10000.0, SALVAGE, LIFE, "straight_line", 1)

    def test_float_salvage_value_raises_type_error(self, engine):
        with pytest.raises(TypeError, match="salvage_value must be Decimal"):
            engine.calculate_period(COST, 1000.0, LIFE, "straight_line", 1)

    def test_int_historical_cost_raises_type_error(self, engine):
        with pytest.raises(TypeError, match="historical_cost must be Decimal"):
            engine.calculate_period(10000, SALVAGE, LIFE, "straight_line", 1)

    def test_invalid_method_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="method must be one of"):
            engine.calculate_period(COST, SALVAGE, LIFE, "sinking_fund", 1)

    def test_period_above_life_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="period_number must be in"):
            engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", LIFE + 1)

    def test_period_zero_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="period_number must be in"):
            engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", 0)

    def test_salvage_exceeds_cost_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="cannot exceed historical_cost"):
            engine.calculate_period(Decimal("1000"), Decimal("2000"), 12, "straight_line", 1)

    def test_zero_historical_cost_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="historical_cost must be positive"):
            engine.calculate_period(Decimal("0"), Decimal("0"), 12, "straight_line", 1)

    def test_negative_salvage_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="salvage_value must be >= 0"):
            engine.calculate_period(COST, Decimal("-1"), LIFE, "straight_line", 1)

    def test_zero_useful_life_raises_value_error(self, engine):
        with pytest.raises(ValueError, match="useful_life_months must be >= 1"):
            engine.calculate_period(COST, SALVAGE, 0, "straight_line", 1)

    def test_bool_period_number_raises_type_error(self, engine):
        # bool is a subclass of int — must be explicitly rejected
        with pytest.raises(TypeError, match="period_number must be int"):
            engine.calculate_period(COST, SALVAGE, LIFE, "straight_line", True)

    def test_bool_useful_life_raises_type_error(self, engine):
        """L1: bool useful_life_months must also be rejected."""
        with pytest.raises(TypeError, match="useful_life_months must be int"):
            engine.calculate_period(COST, SALVAGE, True, "straight_line", 1)
