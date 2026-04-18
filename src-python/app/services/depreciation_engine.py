"""Depreciation Engine — NIIF Sección 17 methods.

Pure calculation service. Zero database interaction, zero Flask imports.
All financial arithmetic uses decimal.Decimal — never float.

Four methods supported:
    straight_line     — equal monthly charge across all periods
    sum_of_digits     — declining charge weighted by remaining-life digit
    declining_balance — charge as fixed % of opening net book value (floored at salvage)
    none              — land assets (TERRENOS): zero depreciation every period,
                        book_value = historical_cost

Legacy / imported asset support (optional keyword args on calculate_period):
    additions_improvements              — capitalized improvements added to the depreciable base
    imported_accumulated_depreciation   — accumulated depreciation at the time of import; offsets
                                          the reported accumulated_depreciation and net_book_value
                                          without altering the per-period charge amount.

Contract guarantee: identical inputs always produce bit-identical outputs (deterministic).
"""

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 28

FOUR_PLACES = Decimal("0.0001")
VALID_METHODS = frozenset({"straight_line", "sum_of_digits", "declining_balance", "none"})


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
        *,
        additions_improvements: Decimal | None = None,
        imported_accumulated_depreciation: Decimal | None = None,
    ) -> dict:
        """Calculate depreciation for one period in an asset's depreciation schedule.

        Args:
            historical_cost: Acquisition cost as Decimal (must be > 0).
            salvage_value:   Residual value as Decimal (0 ≤ salvage_value ≤ historical_cost).
            useful_life_months: Total months in the asset's useful life (must be ≥ 1).
            method:          "straight_line" | "sum_of_digits" | "declining_balance" | "none"
            period_number:   1-indexed period in the asset's schedule (1 = first month).
            additions_improvements: Capitalized improvements as Decimal (optional, default 0).
                Adds to the depreciable base: effective_cost = historical_cost + additions.
                Also used as the opening NBV for declining_balance and as the cost basis for
                the declining_balance rate formula.
            imported_accumulated_depreciation: Accumulated depreciation at import time as Decimal
                (optional, default 0).  Offsets the reported accumulated_depreciation and
                net_book_value without altering the per-period monthly_charge.

        Returns:
            {
                "monthly_charge":          Decimal,  # depreciation charge for this period
                "accumulated_depreciation": Decimal,  # total from period 1..N (+ import offset)
                "net_book_value":           Decimal,  # effective_cost - accumulated_depreciation
            }
            All values quantized to 4 decimal places using ROUND_HALF_UP.

        Raises:
            TypeError:  if any monetary input is not Decimal (including optional params).
            ValueError: if any numeric input is outside its valid range, including
                        salvage_value > effective_cost (historical_cost + additions).

        Note: method="none" (TERRENOS / land) exits before validation — useful_life_months=0
        and any period_number are accepted and always return zero depreciation.
        """
        # Type-check optional import fields (D3: all financial values must be Decimal)
        if additions_improvements is not None and not isinstance(additions_improvements, Decimal):
            raise TypeError(
                f"additions_improvements must be Decimal, "
                f"got {type(additions_improvements).__name__}"
            )
        if imported_accumulated_depreciation is not None and not isinstance(
            imported_accumulated_depreciation, Decimal
        ):
            raise TypeError(
                f"imported_accumulated_depreciation must be Decimal, "
                f"got {type(imported_accumulated_depreciation).__name__}"
            )

        # Normalize optional import fields
        additions = additions_improvements if additions_improvements is not None else Decimal("0")
        starting_accumulated = (
            imported_accumulated_depreciation
            if imported_accumulated_depreciation is not None
            else Decimal("0")
        )

        # Early exit for TERRENOS: no depreciation, book_value = historical_cost always.
        # Must precede _validate so that useful_life_months=0 does not raise.
        if method == "none":
            hc4 = historical_cost.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            zero = Decimal("0.0000")
            return {"monthly_charge": zero, "accumulated_depreciation": zero, "net_book_value": hc4}

        # Defensive: ensure precision is correct even if external code modified the context
        getcontext().prec = 28

        # Run core validation (type checks, ranges — salvage upper bound intentionally omitted
        # here; checked below against effective_cost to support additions_improvements).
        self._validate(historical_cost, salvage_value, useful_life_months, method, period_number)

        # effective_cost includes capitalized improvements (NIIF: additions capitalize into base)
        effective_cost = historical_cost + additions

        # Salvage upper-bound check: must not exceed the full cost base including improvements.
        # When no improvements are present effective_cost == historical_cost, so the message
        # uses the familiar term to keep the existing error contract intact.
        if salvage_value > effective_cost:
            cost_label = "historical_cost" if additions == Decimal("0") else "effective_cost"
            raise ValueError(
                f"salvage_value ({salvage_value}) cannot exceed {cost_label} ({effective_cost})"
            )

        depreciable_base = effective_cost - salvage_value

        if depreciable_base == Decimal("0"):
            ec4 = effective_cost.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            zero = Decimal("0.0000")
            if starting_accumulated != Decimal("0"):
                total_acc = starting_accumulated.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
                nbv = (effective_cost - total_acc).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
                return {
                    "monthly_charge": zero,
                    "accumulated_depreciation": total_acc,
                    "net_book_value": nbv,
                }
            return {"monthly_charge": zero, "accumulated_depreciation": zero, "net_book_value": ec4}

        if method == "straight_line":
            result = self._straight_line(
                effective_cost, depreciable_base, useful_life_months, period_number
            )
        elif method == "sum_of_digits":
            result = self._sum_of_digits(
                effective_cost, depreciable_base, useful_life_months, period_number
            )
        else:
            # declining_balance: rate and opening NBV both use effective_cost
            result = self._declining_balance(
                effective_cost, salvage_value, depreciable_base, useful_life_months, period_number
            )

        # Apply imported_accumulated_depreciation offset to accumulated and book_value.
        # The monthly_charge for this period is unchanged — it reflects the normal schedule.
        if starting_accumulated != Decimal("0"):
            total_acc = (starting_accumulated + result["accumulated_depreciation"]).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            nbv = (effective_cost - total_acc).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            return {
                "monthly_charge": result["monthly_charge"],
                "accumulated_depreciation": total_acc,
                "net_book_value": nbv,
            }

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Private: method implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _straight_line(
        self,
        effective_cost: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Equal monthly charge across all periods.

        Final period uses a residual adjustment to guarantee the sum of all charges
        equals depreciable_base exactly (handles accumulated rounding drift).

        effective_cost = historical_cost + additions_improvements (may equal historical_cost
        when no improvements exist).
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

        net_book_value = (effective_cost - accumulated).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _sum_of_digits(
        self,
        effective_cost: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Declining charge proportional to the remaining-life digit weight.

        Formula: charge_k = (digit_k / total_sum_of_digits) * depreciable_base
        where digit_k = n - k + 1  (highest in period 1, lowest in period n).

        Final period uses a residual adjustment to guarantee the sum of all charges
        equals depreciable_base exactly.

        effective_cost = historical_cost + additions_improvements (may equal historical_cost
        when no improvements exist).
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

        net_book_value = (effective_cost - accumulated).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _declining_balance(
        self,
        effective_cost: Decimal,
        salvage_value: Decimal,
        depreciable_base: Decimal,
        useful_life_months: int,
        period_number: int,
    ) -> dict:
        """Declining balance: charge = opening_nbv × rate, floored at salvage.

        Rate is computed to reach salvage_value at end of useful life:
            R = 1 - (salvage / effective_cost)^(1/n)

        effective_cost = historical_cost + additions_improvements. The rate and the opening
        NBV both use effective_cost because additions capitalize into the asset's cost base
        under NIIF Sección 17.

        Edge case — salvage_value == 0: the standard formula yields R=1 (100% in period 1).
        Uses double-declining rate instead: R = 2/n.

        Floor adjustment: whenever the theoretical charge would push NBV below salvage,
        the charge is capped at (opening_nbv - salvage_value).  In the final period the
        charge is set to the exact residual so the sum equals depreciable_base precisely.
        """
        rate = self._declining_balance_rate(effective_cost, salvage_value, useful_life_months)

        nbv = effective_cost
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
            net_book_value = (effective_cost - accumulated).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )

        return {
            "monthly_charge": monthly_charge,
            "accumulated_depreciation": accumulated,
            "net_book_value": net_book_value,
        }

    def _declining_balance_rate(
        self,
        effective_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
    ) -> Decimal:
        """Compute the declining balance depreciation rate.

        Standard formula: R = 1 - (salvage / effective_cost)^(1/n)
        effective_cost = historical_cost + additions_improvements.
        This rate causes opening_nbv × (1-R)^n = salvage_value in continuous math;
        the iterative floor adjustment handles discrete rounding at the final period.

        Edge case — salvage_value == 0: standard formula yields R=1 (all cost in period 1).
        Uses double-declining balance as the practical fallback: R = 2/n.
        """
        if salvage_value == Decimal("0"):
            return Decimal("2") / Decimal(useful_life_months)
        return Decimal("1") - (salvage_value / effective_cost) ** (
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
        # Note: salvage_value upper-bound check (against effective_cost) is performed in
        # calculate_period after computing effective_cost = historical_cost + additions.
        if useful_life_months < 1:
            raise ValueError(f"useful_life_months must be >= 1, got {useful_life_months}")
        if period_number < 1 or period_number > useful_life_months:
            raise ValueError(
                f"period_number must be in [1..{useful_life_months}], got {period_number}"
            )
        if method not in VALID_METHODS:
            raise ValueError(f"method must be one of {sorted(VALID_METHODS)}, got '{method}'")
