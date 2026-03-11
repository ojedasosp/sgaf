"""Asset management routes for SGAF.

All endpoints require JWT authentication via @require_auth.
Monetary values use decimal.Decimal and are stored as TEXT (4 decimal places).
Audit trail is written via AuditLogger — never with direct INSERT to audit_logs.
"""

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import insert, select

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import fixed_assets
from app.utils.audit_logger import AuditLogger
from app.utils.decimal_utils import to_db_string
from app.validators.asset_validator import validate_asset_create

assets_bp = Blueprint("assets", __name__, url_prefix="/api/v1/assets")
_audit_logger = AuditLogger()


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a JSON-serialisable dict."""
    return dict(row._mapping)


@assets_bp.get("/")
@require_auth
def list_assets():
    """GET /api/v1/assets/ — List all fixed assets ordered by acquisition_date descending.

    Returns 200 with {"data": [...], "total": N}.
    No query params — filtering is done client-side via TanStack Table (≤500 assets per NFR4).
    """
    with get_db() as conn:
        result = conn.execute(select(fixed_assets).order_by(fixed_assets.c.acquisition_date.desc()))
        rows = result.fetchall()

    assets = [_row_to_dict(row) for row in rows]
    return jsonify({"data": assets, "total": len(assets)}), 200


@assets_bp.post("/")
@require_auth
def create_asset():
    """POST /api/v1/assets/ — Register a new fixed asset.

    Returns 201 with the created asset on success.
    Returns 400 for validation errors.
    Returns 409 for duplicate asset code.
    """
    data = request.get_json(silent=True) or {}

    errors = validate_asset_create(data)
    if errors:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": errors[0]["message"],
                    "field": errors[0]["field"],
                    "details": errors,
                }
            ),
            400,
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db() as conn:
        # Duplicate code check
        existing = conn.execute(
            select(fixed_assets.c.asset_id).where(fixed_assets.c.code == str(data["code"]).strip())
        ).fetchone()
        if existing:
            return (
                jsonify(
                    {
                        "error": "CONFLICT",
                        "message": f"Asset code '{data['code']}' already exists",
                    }
                ),
                409,
            )

        # Insert
        stmt = insert(fixed_assets).values(
            code=str(data["code"]).strip(),
            description=str(data["description"]).strip(),
            historical_cost=to_db_string(Decimal(str(data["historical_cost"]))),
            salvage_value=to_db_string(Decimal(str(data["salvage_value"]))),
            useful_life_months=int(data["useful_life_months"]),
            acquisition_date=str(data["acquisition_date"]),
            category=str(data["category"]).strip(),
            depreciation_method=str(data["depreciation_method"]),
            status="active",
            created_at=now,
            updated_at=now,
        )
        result = conn.execute(stmt)
        new_id = result.lastrowid

        row = conn.execute(select(fixed_assets).where(fixed_assets.c.asset_id == new_id)).fetchone()
        conn.commit()

    _audit_logger.log_change(
        entity_type="asset",
        entity_id=new_id,
        action="CREATE",
        actor="system",
    )

    return jsonify({"data": _row_to_dict(row)}), 201
