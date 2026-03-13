"""Depreciation calculation routes for SGAF.

All endpoints require JWT authentication via @require_auth.
Monetary values use decimal.Decimal and are stored as TEXT (4 decimal places).
Period number computation follows NIIF Sección 17 (1-indexed, monthly).
"""

from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import delete, insert, select

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import depreciation_results, fixed_assets
from app.services.depreciation_engine import DepreciationEngine
from app.utils.decimal_utils import from_db_string, to_db_string

depreciation_bp = Blueprint("depreciation", __name__, url_prefix="/api/v1/depreciation")


def _validate_period(period_month, period_year):
    """Validate period_month and period_year values.

    Returns a list of error dicts (empty if valid).
    """
    errors = []
    if period_month is None:
        errors.append(
            {
                "error": "VALIDATION_ERROR",
                "message": "period_month is required",
                "field": "period_month",
            }
        )
    elif not isinstance(period_month, int) or not (1 <= period_month <= 12):
        errors.append(
            {
                "error": "VALIDATION_ERROR",
                "message": "period_month must be between 1 and 12",
                "field": "period_month",
            }
        )
    if period_year is None:
        errors.append(
            {
                "error": "VALIDATION_ERROR",
                "message": "period_year is required",
                "field": "period_year",
            }
        )
    elif not isinstance(period_year, int) or not (2000 <= period_year <= 2099):
        errors.append(
            {
                "error": "VALIDATION_ERROR",
                "message": "period_year must be between 2000 and 2099",
                "field": "period_year",
            }
        )
    return errors


def _compute_period_number(acquisition_date_str: str, period_month: int, period_year: int) -> int:
    """Return 1-indexed depreciation period number for a calendar period.

    Returns <= 0 if acquisition date is after the target period.
    """
    acq = date.fromisoformat(acquisition_date_str)
    return (period_year - acq.year) * 12 + (period_month - acq.month) + 1


def _compute_opening_book_value(row: dict) -> str:
    """Compute opening_book_value from stored row values.

    opening_book_value = book_value + depreciation_amount
    (equivalent to historical_cost - accumulated_depreciation_at_start_of_period)
    """
    book_value = from_db_string(row["book_value"])
    dep_amount = from_db_string(row["depreciation_amount"])
    return to_db_string(book_value + dep_amount)


def _row_to_result_dict(dep_row, asset_row) -> dict:
    """Build a result dict from a depreciation_results row + fixed_assets row."""
    result = dict(dep_row._mapping)
    # Enrich with asset fields
    result["code"] = asset_row["code"]
    result["description"] = asset_row["description"]
    result["depreciation_method"] = asset_row["depreciation_method"]
    # Compute opening_book_value (not stored in DB)
    result["opening_book_value"] = _compute_opening_book_value(result)
    return result


@depreciation_bp.post("/")
@require_auth
def calculate_depreciation():
    """POST /api/v1/depreciation/ — Trigger depreciation calculation for a period.

    Body: {"period_month": int, "period_year": int}
    Returns 200 with {"data": [...], "total": N, "period_month": M, "period_year": Y,
    "calculated_at": "..."}
    Returns 200 with empty data + message if no active assets exist (AC6).
    Returns 400 on invalid period params.
    """
    data = request.get_json(silent=True) or {}

    period_month = data.get("period_month")
    period_year = data.get("period_year")

    errors = _validate_period(period_month, period_year)
    if errors:
        return (
            jsonify(
                {
                    "error": errors[0]["error"],
                    "message": errors[0]["message"],
                    "field": errors[0]["field"],
                }
            ),
            400,
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    engine = DepreciationEngine()

    with get_db() as conn:
        # Query all active assets
        active_assets = conn.execute(
            select(fixed_assets).where(fixed_assets.c.status == "active")
        ).fetchall()

        if not active_assets:
            return (
                jsonify(
                    {
                        "data": [],
                        "total": 0,
                        "period_month": period_month,
                        "period_year": period_year,
                        "message": "No hay activos activos para calcular en este período.",
                    }
                ),
                200,
            )

        # Delete existing results for this period (replace semantics — AC5)
        conn.execute(
            delete(depreciation_results).where(
                depreciation_results.c.period_month == period_month,
                depreciation_results.c.period_year == period_year,
            )
        )

        results = []
        for asset in active_assets:
            asset_dict = dict(asset._mapping)
            period_number = _compute_period_number(
                asset_dict["acquisition_date"], period_month, period_year
            )

            # Skip assets not yet active or fully depreciated in this period
            if period_number < 1 or period_number > asset_dict["useful_life_months"]:
                continue

            calc = engine.calculate_period(
                historical_cost=from_db_string(asset_dict["historical_cost"]),
                salvage_value=from_db_string(asset_dict["salvage_value"]),
                useful_life_months=int(asset_dict["useful_life_months"]),
                method=asset_dict["depreciation_method"],
                period_number=period_number,
            )

            stmt = insert(depreciation_results).values(
                asset_id=asset_dict["asset_id"],
                period_month=period_month,
                period_year=period_year,
                depreciation_amount=to_db_string(calc["monthly_charge"]),
                accumulated_depreciation=to_db_string(calc["accumulated_depreciation"]),
                book_value=to_db_string(calc["net_book_value"]),
                calculated_at=now,
            )
            insert_result = conn.execute(stmt)
            result_id = insert_result.lastrowid

            row = {
                "result_id": result_id,
                "asset_id": asset_dict["asset_id"],
                "code": asset_dict["code"],
                "description": asset_dict["description"],
                "depreciation_method": asset_dict["depreciation_method"],
                "period_month": period_month,
                "period_year": period_year,
                "depreciation_amount": to_db_string(calc["monthly_charge"]),
                "accumulated_depreciation": to_db_string(calc["accumulated_depreciation"]),
                "book_value": to_db_string(calc["net_book_value"]),
                "calculated_at": now,
            }
            # opening_book_value = book_value + depreciation_amount
            book_val = calc["net_book_value"]
            monthly = calc["monthly_charge"]
            row["opening_book_value"] = to_db_string(book_val + monthly)
            results.append(row)

        conn.commit()

    if not results:
        return (
            jsonify(
                {
                    "data": [],
                    "total": 0,
                    "period_month": period_month,
                    "period_year": period_year,
                    "message": "No hay activos activos para calcular en este período.",
                }
            ),
            200,
        )

    return (
        jsonify(
            {
                "data": results,
                "total": len(results),
                "period_month": period_month,
                "period_year": period_year,
                "calculated_at": now,
            }
        ),
        200,
    )


@depreciation_bp.get("/")
@require_auth
def get_depreciation_results():
    """GET /api/v1/depreciation/ — Retrieve stored depreciation results for a period.

    Query params: period_month, period_year
    Returns 200 with {"data": [...], "total": N, "period_month": M, "period_year": Y}
    Returns empty data if no results exist for that period.
    Returns 400 on invalid params.
    """
    try:
        period_month_raw = request.args.get("period_month")
        period_year_raw = request.args.get("period_year")
        period_month = int(period_month_raw) if period_month_raw is not None else None
        period_year = int(period_year_raw) if period_year_raw is not None else None
    except (ValueError, TypeError):
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "period_month and period_year must be integers",
                    "field": "period_month",
                }
            ),
            400,
        )

    errors = _validate_period(period_month, period_year)
    if errors:
        return (
            jsonify(
                {
                    "error": errors[0]["error"],
                    "message": errors[0]["message"],
                    "field": errors[0]["field"],
                }
            ),
            400,
        )

    with get_db() as conn:
        rows = conn.execute(
            select(depreciation_results, fixed_assets)
            .join(
                fixed_assets,
                depreciation_results.c.asset_id == fixed_assets.c.asset_id,
            )
            .where(
                depreciation_results.c.period_month == period_month,
                depreciation_results.c.period_year == period_year,
            )
        ).fetchall()

        if not rows:
            return (
                jsonify(
                    {
                        "data": [],
                        "total": 0,
                        "period_month": period_month,
                        "period_year": period_year,
                    }
                ),
                200,
            )

        # Build results from joined rows (no N+1 queries)
        results = []
        calculated_at = None
        for row in rows:
            row_dict = dict(row._mapping)
            result_dict = {
                "result_id": row_dict["result_id"],
                "asset_id": row_dict["asset_id"],
                "code": row_dict["code"],
                "description": row_dict["description"],
                "depreciation_method": row_dict["depreciation_method"],
                "period_month": row_dict["period_month"],
                "period_year": row_dict["period_year"],
                "depreciation_amount": row_dict["depreciation_amount"],
                "accumulated_depreciation": row_dict["accumulated_depreciation"],
                "book_value": row_dict["book_value"],
                "calculated_at": row_dict["calculated_at"],
            }
            # Compute opening_book_value from stored values
            book_val = from_db_string(row_dict["book_value"])
            dep_amount = from_db_string(row_dict["depreciation_amount"])
            result_dict["opening_book_value"] = to_db_string(book_val + dep_amount)
            results.append(result_dict)
            if calculated_at is None:
                calculated_at = row_dict["calculated_at"]

    return (
        jsonify(
            {
                "data": results,
                "total": len(results),
                "period_month": period_month,
                "period_year": period_year,
                "calculated_at": calculated_at,
            }
        ),
        200,
    )
