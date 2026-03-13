"""Depreciation Engine — NIIF Sección 17 methods.

Pure calculation service. Zero database interaction, zero Flask imports.
All financial arithmetic uses decimal.Decimal — never float.

Three methods supported:
    straight_line     — equal monthly charge across all periods
    sum_of_digits     — declining charge weighted by remaining-life digit
    declining_balance — charge as fixed % of opening net book value (floored at salvage)

Contract guarantee: identical inputs always produce bit-identical outputs (deterministic).
"""

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 28

FOUR_PLACES = Decimal("0.0001")
VALID_METHODS = frozenset({"straight_line", "sum_of_digits", "declining_balance"})


class DepreciationEngine:
    """Calculates per-period depreciation for fixed assets using three NIIF methods.

    All monetary inputs and outputs are decimal.Decimal quantized to 4 decimal places
    (ROUND_HALF_UP).  Results are fully deterministic: identical inputs always produce
    bit-identical outputs.  No internal state — each call is independent.
    """

    def calculate_period(
        self,
        historical_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        method: str,
        period_number: int,
    ) -> dict:
        """Calculate depreciation for one period in an asset's depreciation schedule.

        Args:
            historical_cost: Acquisition cost as Decimal (must be > 0).
            salvage_value:   Residual value as Decimal (0 ≤ salvage_value ≤ historical_cost).
            useful_life_months: Total months in the asset's useful life (must be ≥ 1).
            method:          "straight_line" | "sum_of_digits" | "declining_balance"
            period_number:   1-indexed period in the asset's schedule (1 = first month).

        Returns:
            {
                "monthly_charge":          Decimal,  # depreciation charge for this period
                "accumulated_depreciation": Decimal,  # total charged period 1..period_number
                "net_book_value":           Decimal,  # historical_cost - accumulated
            }
            All values quantized to 4 decimal places using ROUND_HALF_UP.

        Raises:
            TypeError:  if historical_cost or salvage_value are not Decimal.
            ValueError: if any numeric input is outside its valid range.
        """
        # Defensive: ensure precision is correct even if external code modified the context
        getcontext().prec = 28

        self._validate(historical_cost, salvage_value, useful_life_months, method, period_number)

        depreciable_base = historical_cost - salvage_value
        if depreciable_base == Decimal("0"):
            hc4 = historical_cost.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            zero = Decimal("0.0000")
            return {"monthly_charge": zero, "accumulated_depreciation": zero, "net_book_value": hc4}

        if method == "straight_line":
            return self._straight_line(
                historical_cost, depreciable_base, useful_life_months, period_number
            )
        if method == "sum_of_digits":
            return self._sum_of_digits(
                historical_cost, depreciable_base, useful_life_months, period_number
            )
        # declining_balance
        return self._declining_balance(
            historical_cost, salvage_value, depreciable_base, useful_life_months, period_number
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Private: method implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _straight_line(
        self,
        historical_cost: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Equal monthly charge across all periods.

        Final period uses a residual adjustment to guarantee the sum of all charges
        equals depreciable_base exactly (handles accumulated rounding drift).
        """
        base_charge = (depreciable_base / Decimal(useful_life_months)).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )

        if period_number < useful_life_months:
            monthly_charge = base_charge
            accumulated = (base_charge * Decimal(period_number)).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            # Final period: residual ensures sum(all charges) == depreciable_base
            accumulated_prev = (base_charge * Decimal(useful_life_months - 1)).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            monthly_charge = (depreciable_base - accumulated_prev).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            accumulated = depreciable_base.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

        net_book_value = (historical_cost - accumulated).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _sum_of_digits(
        self,
        historical_cost: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Declining charge proportional to the remaining-life digit weight.

        Formula: charge_k = (digit_k / total_sum_of_digits) * depreciable_base
        where digit_k = n - k + 1  (highest in period 1, lowest in period n).

        Final period uses a residual adjustment to guarantee the sum of all charges
        equals depreciable_base exactly.
        """
        n = useful_life_months
        total_sod = Decimal(n * (n + 1)) / Decimal(2)

        def _charge(k: int) -> Decimal:
            return (Decimal(n - k + 1) / total_sod * depreciable_base).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )

        if period_number < useful_life_months:
            monthly_charge = _charge(period_number)
            charges_sum = sum((_charge(k) for k in range(1, period_number + 1)), Decimal("0"))
            accumulated = charges_sum.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        else:
            # Final period: residual ensures sum(all charges) == depreciable_base
            prev_sum = sum((_charge(k) for k in range(1, useful_life_months)), Decimal("0"))
            accumulated_prev = prev_sum.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            monthly_charge = (depreciable_base - accumulated_prev).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            accumulated = depreciable_base.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

        net_book_value = (historical_cost - accumulated).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _declining_balance(
        self,
        historical_cost: Decimal,
        salvage_value: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Declining balance: charge = opening_nbv × rate, floored at salvage.

        Rate is computed to reach salvage_value at end of useful life:
            R = 1 - (salvage / cost)^(1/n)

        Edge case — salvage_value == 0: the standard formula yields R=1 (100% in period 1).
        Uses double-declining rate instead: R = 2/n.

        Floor adjustment: whenever the theoretical charge would push NBV below salvage,
        the charge is capped at (opening_nbv - salvage_value).  In the final period the
        charge is set to the exact residual so the sum equals depreciable_base precisely.
        """
        rate = self._declining_balance_rate(historical_cost, salvage_value, useful_life_months)

        nbv = historical_cost
        charges: list[Decimal] = []

        for i in range(1, period_number + 1):
            opening_nbv = nbv
            max_charge = opening_nbv - salvage_value

            if max_charge <= Decimal("0"):
                charge = Decimal("0.0000")
            elif i == useful_life_months:
                # Final period: residual to guarantee sum(all charges) == depreciable_base
                prev_total = sum(charges, Decimal("0"))
                residual = depreciable_base - prev_total
                charge = max(residual, Decimal("0")).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            else:
                theoretical = (opening_nbv * rate).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
                charge = min(theoretical, max_charge).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

            charges.append(charge)
            nbv = (opening_nbv - charge).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

        monthly_charge = charges[period_number - 1]

        if period_number == useful_life_months:
            accumulated = depreciable_base.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            net_book_value = salvage_value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        else:
            accumulated = sum(charges, Decimal("0")).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            net_book_value = (historical_cost - accumulated).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )

        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _declining_balance_rate(
        self,
        historical_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
    ) -> Decimal:
        """Compute the declining balance depreciation rate.

        Standard formula: R = 1 - (salvage / cost)^(1/n)
        This rate causes opening_nbv × (1-R)^n = salvage_value in continuous math;
        the iterative floor adjustment handles discrete rounding at the final period.

        Edge case — salvage_value == 0: standard formula yields R=1 (all cost in period 1).
        Uses double-declining balance as the practical fallback: R = 2/n.
        """
        if salvage_value == Decimal("0"):
            return Decimal("2") / Decimal(useful_life_months)
        return Decimal("1") - (salvage_value / historical_cost) ** (
            Decimal("1") / Decimal(useful_life_months)
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Private: input validation
    # ──────────────────────────────────────────────────────────────────────────

    def _validate(
        self,
        historical_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        method: str,
        period_number: int,
    ) -> None:
        if not isinstance(historical_cost, Decimal):
            raise TypeError(
                f"historical_cost must be Decimal, got {type(historical_cost).__name__}"
            )
        if not isinstance(salvage_value, Decimal):
            raise TypeError(f"salvage_value must be Decimal, got {type(salvage_value).__name__}")
        if not isinstance(useful_life_months, int) or isinstance(useful_life_months, bool):
            raise TypeError(
                f"useful_life_months must be int, got {type(useful_life_months).__name__}"
            )
        if not isinstance(period_number, int) or isinstance(period_number, bool):
            raise TypeError(f"period_number must be int, got {type(period_number).__name__}")
        if historical_cost <= Decimal("0"):
            raise ValueError(f"historical_cost must be positive, got {historical_cost}")
        if salvage_value < Decimal("0"):
            raise ValueError(f"salvage_value must be >= 0, got {salvage_value}")
        if salvage_value > historical_cost:
            raise ValueError(
                f"salvage_value ({salvage_value}) cannot exceed historical_cost ({historical_cost})"
            )
        if useful_life_months < 1:
            raise ValueError(f"useful_life_months must be >= 1, got {useful_life_months}")
        if period_number < 1 or period_number > useful_life_months:
            raise ValueError(
                f"period_number must be in [1..{useful_life_months}], got {period_number}"
            )
        if method not in VALID_METHODS:
            raise ValueError(f"method must be one of {sorted(VALID_METHODS)}, got '{method}'")
