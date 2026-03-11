"""Validation logic for asset registration and mutation endpoints.

validate_asset_create() returns a list of error dicts.
An empty list means validation passed.
Each error dict has the shape: {"field": str, "message": str}
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

_VALID_METHODS = {"straight_line", "sum_of_digits", "declining_balance"}


def validate_asset_create(data: dict[str, Any]) -> list[dict[str, str]]:
    """Validate payload for POST /api/v1/assets/.

    Returns a list of field-level errors. Empty list means valid.
    Checks are performed in field order so the first error is always
    the most prominent one in the response.
    """
    errors: list[dict[str, str]] = []

    # --- code ---
    code = data.get("code")
    if not code or not str(code).strip():
        errors.append({"field": "code", "message": "Asset code is required"})

    # --- description ---
    description = data.get("description")
    if not description or not str(description).strip():
        errors.append({"field": "description", "message": "Description is required"})

    # --- category ---
    category = data.get("category")
    if not category or not str(category).strip():
        errors.append({"field": "category", "message": "Category is required"})

    # --- historical_cost ---
    historical_cost_str = data.get("historical_cost")
    historical_cost: Decimal | None = None
    if historical_cost_str is None or str(historical_cost_str).strip() == "":
        errors.append({"field": "historical_cost", "message": "Historical cost is required"})
    else:
        try:
            historical_cost = Decimal(str(historical_cost_str))
            if historical_cost.is_nan() or historical_cost.is_infinite():
                raise InvalidOperation
            if historical_cost <= Decimal("0"):
                errors.append(
                    {
                        "field": "historical_cost",
                        "message": "Historical cost must be greater than 0",
                    }
                )
                historical_cost = None  # prevent cross-field check
        except InvalidOperation:
            errors.append(
                {
                    "field": "historical_cost",
                    "message": "Historical cost must be a valid number",
                }
            )
            historical_cost = None

    # --- salvage_value ---
    salvage_value_str = data.get("salvage_value")
    salvage_value: Decimal | None = None
    if salvage_value_str is None or str(salvage_value_str).strip() == "":
        errors.append({"field": "salvage_value", "message": "Salvage value is required"})
    else:
        try:
            salvage_value = Decimal(str(salvage_value_str))
            if salvage_value.is_nan() or salvage_value.is_infinite():
                raise InvalidOperation
            if salvage_value < Decimal("0"):
                errors.append(
                    {
                        "field": "salvage_value",
                        "message": "Salvage value must be zero or greater",
                    }
                )
                salvage_value = None
            elif historical_cost is not None and salvage_value >= historical_cost:
                errors.append(
                    {
                        "field": "salvage_value",
                        "message": "Salvage value must be less than historical cost",
                    }
                )
        except InvalidOperation:
            errors.append(
                {
                    "field": "salvage_value",
                    "message": "Salvage value must be a valid number",
                }
            )

    # --- useful_life_months ---
    useful_life = data.get("useful_life_months")
    if useful_life is None or str(useful_life).strip() == "":
        errors.append(
            {
                "field": "useful_life_months",
                "message": "Useful life is required",
            }
        )
    else:
        try:
            useful_life_int = int(useful_life)
            if useful_life_int <= 0:
                errors.append(
                    {
                        "field": "useful_life_months",
                        "message": "Useful life must be greater than 0",
                    }
                )
        except (ValueError, TypeError):
            errors.append(
                {
                    "field": "useful_life_months",
                    "message": "Useful life must be a valid integer",
                }
            )

    # --- acquisition_date ---
    acquisition_date = data.get("acquisition_date")
    if not acquisition_date or not str(acquisition_date).strip():
        errors.append({"field": "acquisition_date", "message": "Acquisition date is required"})
    else:
        try:
            date.fromisoformat(str(acquisition_date))
        except ValueError:
            errors.append(
                {
                    "field": "acquisition_date",
                    "message": "Acquisition date must be a valid date (YYYY-MM-DD)",
                }
            )

    # --- depreciation_method ---
    method = data.get("depreciation_method")
    if not method or not str(method).strip():
        errors.append(
            {
                "field": "depreciation_method",
                "message": "Depreciation method is required",
            }
        )
    elif str(method) not in _VALID_METHODS:
        errors.append(
            {
                "field": "depreciation_method",
                "message": "Invalid depreciation method",
            }
        )

    return errors
