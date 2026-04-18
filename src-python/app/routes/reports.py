"""PDF report generation routes for SGAF.

All endpoints require JWT authentication via @require_auth.
Returns PDF bytes with Content-Type: application/pdf.

Endpoints:
    POST /api/v1/reports/generate — generate one of three NIIF report types.
"""

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, make_response, request
from sqlalchemy import select, update

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import app_config, depreciation_results, fixed_assets
from app.services.depreciation_engine import DepreciationEngine
from app.services.pdf_generator import PDFGenerator
from app.utils.decimal_utils import from_db_string

reports_bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")

_VALID_REPORT_TYPES = frozenset({"per_asset", "monthly_summary", "asset_register"})


def _get_company_config(conn) -> dict:
    """Fetch company config fields needed for PDF header."""
    row = conn.execute(
        select(
            app_config.c.company_name,
            app_config.c.company_nit,
            app_config.c.logo_path,
        ).where(app_config.c.config_id == 1)
    ).fetchone()
    if row is None:
        return {"company_name": "", "company_nit": "", "logo_path": None}
    return {
        "company_name": row.company_name or "",
        "company_nit": row.company_nit or "",
        "logo_path": row.logo_path,  # nullable — PDFGenerator handles None
    }


def _validate_period(period_month, period_year) -> list:
    """Return a list of validation error dicts (empty if valid)."""
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
                "message": "period_month must be an integer between 1 and 12",
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
    elif not isinstance(period_year, int) or not (2000 <= period_year <= 2150):
        errors.append(
            {
                "error": "VALIDATION_ERROR",
                "message": "period_year must be an integer between 2000 and 2150",
                "field": "period_year",
            }
        )
    return errors


def _build_per_asset_pdf(conn, asset_id: int, period_month: int, period_year: int, company_config: dict) -> bytes:
    """Fetch asset, compute full schedule, and generate per-asset PDF.

    Raises:
        ValueError: if asset_id does not exist.
    """
    row = conn.execute(
        select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
    ).fetchone()
    if row is None:
        raise ValueError(f"Asset {asset_id} not found")

    asset = dict(row._mapping)
    historical_cost = from_db_string(asset["historical_cost"])
    salvage_value = from_db_string(asset["salvage_value"])
    useful_life = asset["useful_life_months"]
    asset_method = asset["depreciation_method"]

    additions = (
        from_db_string(asset["additions_improvements"])
        if asset.get("additions_improvements")
        else None
    )
    starting_accumulated = (
        from_db_string(asset["imported_accumulated_depreciation"])
        if asset.get("imported_accumulated_depreciation")
        else None
    )

    engine = DepreciationEngine()
    schedule = []
    # TERRENOS (method="none", useful_life=0) produce an empty schedule — no depreciation periods.
    for period_num in range(1, useful_life + 1):
        result = engine.calculate_period(
            historical_cost=historical_cost,
            salvage_value=salvage_value,
            useful_life_months=useful_life,
            method=asset_method,
            period_number=period_num,
            additions_improvements=additions,
            imported_accumulated_depreciation=starting_accumulated,
        )
        schedule.append(
            {
                "period_number": period_num,
                "monthly_charge": result["monthly_charge"],
                "accumulated_depreciation": result["accumulated_depreciation"],
                "net_book_value": result["net_book_value"],
            }
        )

    # Use effective_cost as the cost displayed in the PDF header so it matches the
    # depreciation schedule (which is calculated on historical_cost + additions).
    effective_cost_for_pdf = (
        historical_cost + additions if additions is not None else historical_cost
    )

    asset_dict = {
        "code": asset["code"],
        "description": asset["description"],
        "category": asset["category"],
        "depreciation_method": asset_method,
        "historical_cost": effective_cost_for_pdf,
        "salvage_value": salvage_value,
        "useful_life_months": useful_life,
    }

    return PDFGenerator().generate_report(
        "per_asset",
        company_config=company_config,
        asset=asset_dict,
        schedule=schedule,
        period_month=period_month,
        period_year=period_year,
    )


def _build_monthly_summary_pdf(conn, period_month: int, period_year: int, company_config: dict) -> bytes:
    """Fetch depreciation results for the period and generate monthly summary PDF."""
    stmt = (
        select(
            depreciation_results.c.depreciation_amount,
            depreciation_results.c.calculated_at,
            fixed_assets.c.code,
            fixed_assets.c.description,
        )
        .join(
            fixed_assets,
            depreciation_results.c.asset_id == fixed_assets.c.asset_id,
        )
        .where(depreciation_results.c.period_month == period_month)
        .where(depreciation_results.c.period_year == period_year)
        .order_by(fixed_assets.c.code)
    )
    rows = conn.execute(stmt).fetchall()

    assets_results = [
        {
            "code": r.code,
            "description": r.description,
            "depreciation_amount": from_db_string(r.depreciation_amount),  # Always Decimal
            "calculated_at": r.calculated_at,
        }
        for r in rows
    ]

    return PDFGenerator().generate_report(
        "monthly_summary",
        company_config=company_config,
        assets_results=assets_results,
        period_month=period_month,
        period_year=period_year,
    )


def _build_asset_register_pdf(conn, company_config: dict) -> bytes:
    """Fetch all non-retired assets with latest depreciation and generate register PDF."""
    asset_rows = conn.execute(
        select(fixed_assets)
        .where(fixed_assets.c.status != "retired")
        .order_by(fixed_assets.c.category, fixed_assets.c.code)
    ).fetchall()

    assets = []
    for row in asset_rows:
        # Get latest accumulated_depreciation for this asset (if any results exist)
        dep_row = conn.execute(
            select(depreciation_results.c.accumulated_depreciation)
            .where(depreciation_results.c.asset_id == row.asset_id)
            .order_by(
                depreciation_results.c.period_year.desc(),
                depreciation_results.c.period_month.desc(),
            )
            .limit(1)
        ).fetchone()

        historical_cost = from_db_string(row.historical_cost)
        accumulated = (
            from_db_string(dep_row.accumulated_depreciation)
            if dep_row
            else Decimal("0")
        )
        net_book_value = historical_cost - accumulated

        assets.append(
            {
                "code": row.code,
                "description": row.description,
                "category": row.category,
                "historical_cost": historical_cost,
                "accumulated_depreciation": accumulated,
                "net_book_value": net_book_value,
            }
        )

    return PDFGenerator().generate_report(
        "asset_register",
        company_config=company_config,
        assets=assets,
    )


@reports_bp.post("/generate")
@require_auth
def generate_report():
    """Generate a NIIF-compliant PDF report.

    Request body (JSON):
        report_type: "per_asset" | "monthly_summary" | "asset_register"
        asset_id:    int (required for per_asset only)
        period_month: int 1–12 (required for per_asset and monthly_summary)
        period_year:  int 2000–2099 (required for per_asset and monthly_summary)

    Response 200: application/pdf bytes
    Response 400: JSON validation error
    Response 404: JSON not found (per_asset with unknown asset_id)
    """
    body = request.get_json(silent=True) or {}

    report_type = body.get("report_type")
    if report_type not in _VALID_REPORT_TYPES:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": (
                        f"report_type must be one of: {', '.join(sorted(_VALID_REPORT_TYPES))}"
                    ),
                    "field": "report_type",
                }
            ),
            400,
        )

    period_month = body.get("period_month")
    period_year = body.get("period_year")
    asset_id = body.get("asset_id")

    with get_db() as conn:
        company_config = _get_company_config(conn)

        if report_type == "per_asset":
            # Validate asset_id
            if asset_id is None:
                return (
                    jsonify(
                        {
                            "error": "VALIDATION_ERROR",
                            "message": "asset_id is required for per_asset report",
                            "field": "asset_id",
                        }
                    ),
                    400,
                )
            if not isinstance(asset_id, int) or asset_id <= 0:
                return (
                    jsonify(
                        {
                            "error": "VALIDATION_ERROR",
                            "message": "asset_id must be a positive integer",
                            "field": "asset_id",
                        }
                    ),
                    400,
                )
            # Validate period
            period_errors = _validate_period(period_month, period_year)
            if period_errors:
                return jsonify(period_errors[0]), 400

            try:
                pdf_bytes = _build_per_asset_pdf(conn, asset_id, period_month, period_year, company_config)
            except ValueError as e:
                return (
                    jsonify(
                        {
                            "error": "NOT_FOUND",
                            "message": str(e),
                        }
                    ),
                    404,
                )

        elif report_type == "monthly_summary":
            period_errors = _validate_period(period_month, period_year)
            if period_errors:
                return jsonify(period_errors[0]), 400

            pdf_bytes = _build_monthly_summary_pdf(conn, period_month, period_year, company_config)

            # Track PDF generation timestamp for Dashboard status row (AC3, AC7)
            generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                update(app_config)
                .where(app_config.c.config_id == 1)
                .values(
                    last_monthly_pdf_generated_at=generated_at,
                    last_monthly_pdf_period_month=period_month,
                    last_monthly_pdf_period_year=period_year,
                )
            )
            conn.commit()

        else:  # asset_register — no period or asset_id required
            pdf_bytes = _build_asset_register_pdf(conn, company_config)

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    if report_type == "asset_register":
        filename = "registro_activos_fijos.pdf"
    else:
        filename = f"reporte_{report_type}_{period_year}-{period_month:02d}.pdf"
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return response, 200


@reports_bp.get("/status")
@require_auth
def get_report_status():
    """GET /api/v1/reports/status — PDF generation status for a period.

    Query params:
        period_month: int 1–12
        period_year:  int 2000–2150

    Response 200:
        {"data": {"monthly_summary_generated_at": "<ISO8601>" | null}}
    Response 400: JSON validation error
    """
    try:
        period_month_raw = request.args.get("period_month")
        period_year_raw = request.args.get("period_year")
        if period_month_raw is None or period_year_raw is None:
            return (
                jsonify(
                    {
                        "error": "VALIDATION_ERROR",
                        "message": "period_month and period_year are required",
                        "field": "period_month" if period_month_raw is None else "period_year",
                    }
                ),
                400,
            )
        period_month = int(period_month_raw)
        period_year = int(period_year_raw)
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

    period_errors = _validate_period(period_month, period_year)
    if period_errors:
        return jsonify(period_errors[0]), 400

    with get_db() as conn:
        row = conn.execute(
            select(
                app_config.c.last_monthly_pdf_generated_at,
                app_config.c.last_monthly_pdf_period_month,
                app_config.c.last_monthly_pdf_period_year,
            ).where(app_config.c.config_id == 1)
        ).fetchone()

    if (
        row is not None
        and row.last_monthly_pdf_generated_at is not None
        and row.last_monthly_pdf_period_month == period_month
        and row.last_monthly_pdf_period_year == period_year
    ):
        generated_at = row.last_monthly_pdf_generated_at
    else:
        generated_at = None

    return jsonify({"data": {"monthly_summary_generated_at": generated_at}}), 200
