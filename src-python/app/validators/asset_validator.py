"""Validation logic for asset registration and mutation endpoints.

validate_asset_create() returns a list of error dicts.
An empty list means validation passed.
Each error dict has the shape: {"field": str, "message": str}
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_VALID_METHODS = {"straight_line", "sum_of_digits", "declining_balance", "none"}


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


def validate_asset_update(data: dict[str, Any]) -> list[dict[str, str]]:
    """Validate payload for PATCH /api/v1/assets/<asset_id>.

    Only validates keys that are present in data — all fields are optional.
    Returns a list of field-level errors. Empty list means valid.
    Monetary cross-field validation (salvage < historical_cost) is skipped
    for partial updates since we may not have both values in the payload.
    """
    errors: list[dict[str, str]] = []

    # --- code (if present) ---
    if "code" in data:
        code = data["code"]
        if not code or not str(code).strip():
            errors.append({"field": "code", "message": "Asset code is required"})

    # --- description (if present) ---
    if "description" in data:
        description = data["description"]
        if not description or not str(description).strip():
            errors.append({"field": "description", "message": "Description is required"})

    # --- category (if present) ---
    if "category" in data:
        category = data["category"]
        if not category or not str(category).strip():
            errors.append({"field": "category", "message": "Category is required"})

    # --- historical_cost (if present) ---
    if "historical_cost" in data:
        historical_cost_str = data["historical_cost"]
        if historical_cost_str is None or str(historical_cost_str).strip() == "":
            errors.append({"field": "historical_cost", "message": "Historical cost is required"})
        else:
            try:
                hc = Decimal(str(historical_cost_str))
                if hc.is_nan() or hc.is_infinite():
                    raise InvalidOperation
                if hc <= Decimal("0"):
                    errors.append(
                        {
                            "field": "historical_cost",
                            "message": "Historical cost must be greater than 0",
                        }
                    )
            except InvalidOperation:
                errors.append(
                    {
                        "field": "historical_cost",
                        "message": "Historical cost must be a valid number",
                    }
                )

    # --- salvage_value (if present) ---
    if "salvage_value" in data:
        salvage_value_str = data["salvage_value"]
        if salvage_value_str is None or str(salvage_value_str).strip() == "":
            errors.append({"field": "salvage_value", "message": "Salvage value is required"})
        else:
            try:
                sv = Decimal(str(salvage_value_str))
                if sv.is_nan() or sv.is_infinite():
                    raise InvalidOperation
                if sv < Decimal("0"):
                    errors.append(
                        {
                            "field": "salvage_value",
                            "message": "Salvage value must be zero or greater",
                        }
                    )
                elif "historical_cost" in data:
                    # Cross-field check: only when both are present in the same payload
                    try:
                        hc = Decimal(str(data["historical_cost"]))
                        if not hc.is_nan() and not hc.is_infinite() and sv >= hc:
                            errors.append(
                                {
                                    "field": "salvage_value",
                                    "message": "Salvage value must be less than historical cost",
                                }
                            )
                    except InvalidOperation:
                        pass  # historical_cost error already reported above
            except InvalidOperation:
                errors.append(
                    {
                        "field": "salvage_value",
                        "message": "Salvage value must be a valid number",
                    }
                )

    # --- useful_life_months (if present) ---
    if "useful_life_months" in data:
        useful_life = data["useful_life_months"]
        if useful_life is None or str(useful_life).strip() == "":
            errors.append({"field": "useful_life_months", "message": "Useful life is required"})
        else:
            try:
                useful_life_int = int(useful_life)
                if useful_life_int < 0:
                    errors.append(
                        {
                            "field": "useful_life_months",
                            "message": "Useful life must be zero or greater",
                        }
                    )
                elif useful_life_int == 0:
                    # 0 is only valid for TERRENOS (depreciation_method="none")
                    method_in_payload = str(data.get("depreciation_method", "")).strip()
                    if method_in_payload != "none":
                        errors.append(
                            {
                                "field": "useful_life_months",
                                "message": (
                                    "Useful life must be greater than 0 "
                                    "for this depreciation method"
                                ),
                            }
                        )
            except (ValueError, TypeError):
                errors.append(
                    {
                        "field": "useful_life_months",
                        "message": "Useful life must be a valid integer",
                    }
                )

    # --- acquisition_date (if present) ---
    if "acquisition_date" in data:
        acquisition_date = data["acquisition_date"]
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

    # --- depreciation_method (if present) ---
    if "depreciation_method" in data:
        method = data["depreciation_method"]
        if not method or not str(method).strip():
            errors.append(
                {"field": "depreciation_method", "message": "Depreciation method is required"}
            )
        elif str(method) not in _VALID_METHODS:
            errors.append(
                {"field": "depreciation_method", "message": "Invalid depreciation method"}
            )

    # --- imported_accumulated_depreciation (if present, Story 8.5) ---
    if "imported_accumulated_depreciation" in data:
        val = data["imported_accumulated_depreciation"]
        if val is not None and str(val).strip() != "":
            try:
                iad = Decimal(str(val))
                if iad.is_nan() or iad.is_infinite():
                    raise InvalidOperation
                if iad < Decimal("0"):
                    errors.append(
                        {
                            "field": "imported_accumulated_depreciation",
                            "message": "Imported accumulated depreciation must be zero or greater",
                        }
                    )
            except InvalidOperation:
                errors.append(
                    {
                        "field": "imported_accumulated_depreciation",
                        "message": "Imported accumulated depreciation must be a valid number",
                    }
                )

    # --- additions_improvements (if present, Story 8.5) ---
    if "additions_improvements" in data:
        val = data["additions_improvements"]
        if val is not None and str(val).strip() != "":
            try:
                ai = Decimal(str(val))
                if ai.is_nan() or ai.is_infinite():
                    raise InvalidOperation
                if ai < Decimal("0"):
                    errors.append(
                        {
                            "field": "additions_improvements",
                            "message": "Additions and improvements must be zero or greater",
                        }
                    )
            except InvalidOperation:
                errors.append(
                    {
                        "field": "additions_improvements",
                        "message": "Additions and improvements must be a valid number",
                    }
                )

    # --- Cross-field: imported_accumulated_depreciation <= effective_cost (Story 8.5) ---
    # Only when both historical_cost and imported_accumulated_depreciation are in the payload
    # and have no prior errors.
    iad_present = (
        "imported_accumulated_depreciation" in data
        and data.get("imported_accumulated_depreciation") not in (None, "", "0", "0.0", "0.0000")
        and not any(e["field"] == "imported_accumulated_depreciation" for e in errors)
    )
    hc_present = "historical_cost" in data and not any(
        e["field"] == "historical_cost" for e in errors
    )
    ai_present = "additions_improvements" in data and not any(
        e["field"] == "additions_improvements" for e in errors
    )
    if iad_present and hc_present:
        try:
            iad = Decimal(str(data["imported_accumulated_depreciation"]))
            hc = Decimal(str(data["historical_cost"]))
            ai_val = data.get("additions_improvements")
            ai = (
                Decimal(str(ai_val))
                if ai_present and ai_val
                else Decimal("0")
            )
            effective_cost = hc + ai
            if iad > effective_cost:
                errors.append(
                    {
                        "field": "imported_accumulated_depreciation",
                        "message": (
                            "Imported accumulated depreciation cannot exceed "
                            "effective cost (historical_cost + additions_improvements)"
                        ),
                    }
                )
        except (InvalidOperation, Exception):
            pass  # Individual field errors already reported above

    return errors


def validate_retirement_date(data: dict[str, Any]) -> list[dict[str, str]]:
    """Validate retirement_date field for the retire endpoint.

    Returns [] if valid, or list of {"field": str, "message": str} dicts on error.
    """
    errors: list[dict[str, str]] = []

    if "retirement_date" not in data or data["retirement_date"] is None:
        errors.append({"field": "retirement_date", "message": "retirement_date is required"})
        return errors

    try:
        datetime.strptime(str(data["retirement_date"]), "%Y-%m-%d")
    except ValueError:
        errors.append(
            {
                "field": "retirement_date",
                "message": "retirement_date must be a valid date in YYYY-MM-DD format",
            }
        )

    return errors
