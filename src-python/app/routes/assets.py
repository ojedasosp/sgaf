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
from app.models.tables import app_config, depreciation_results, fixed_assets, maintenance_events
from app.utils.audit_logger import AuditLogger
from app.utils.decimal_utils import to_db_string
from app.validators.asset_validator import (
    validate_asset_create,
    validate_asset_update,
    validate_retirement_date,
)

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
        new_id = result.inserted_primary_key[0]

        row = conn.execute(select(fixed_assets).where(fixed_assets.c.asset_id == new_id)).fetchone()
        conn.commit()

    _audit_logger.log_change(
        entity_type="asset",
        entity_id=new_id,
        action="CREATE",
        actor="system",
    )

    return jsonify({"data": _row_to_dict(row)}), 201


@assets_bp.get("/<int:asset_id>")
@require_auth
def get_asset(asset_id: int):
    """GET /api/v1/assets/<asset_id> — Retrieve a single asset by ID.

    Returns 200 with {"data": <asset>} on success.
    Returns 404 if asset does not exist.
    """
    with get_db() as conn:
        row = conn.execute(
            select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
    if row is None:
        return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404
    return jsonify({"data": _row_to_dict(row)}), 200


_EDITABLE_FIELDS = frozenset(
    {
        # Original editable fields
        "code",
        "description",
        "category",
        "historical_cost",
        "salvage_value",
        "useful_life_months",
        "acquisition_date",
        "depreciation_method",
        # Import fields (Story 8.5)
        "imported_accumulated_depreciation",
        "additions_improvements",
        "accounting_code",
        "cost_center",
        "supplier",
        "invoice_number",
        "location",
        "characteristics",
    }
)

_NULLABLE_MONETARY_IMPORT_FIELDS = frozenset(
    {"imported_accumulated_depreciation", "additions_improvements"}
)
_NULLABLE_TEXT_IMPORT_FIELDS = frozenset(
    {"accounting_code", "cost_center", "supplier", "invoice_number", "location", "characteristics"}
)


@assets_bp.patch("/<int:asset_id>")
@require_auth
def update_asset(asset_id: int):
    """PATCH /api/v1/assets/<asset_id> — Partial update of an asset's editable fields.

    Accepts original 8 fields plus 8 import fields added in Story 8.5.
    Only fields present in the request body are validated and updated.
    AuditLogger records one entry per changed field (fields with no change are skipped).
    actor = company_name from app_config (trimmed).
    Returns 200 with the updated asset on success.
    Returns 400 if no editable fields provided or validation fails.
    Returns 404 if asset does not exist.
    Returns 409 if code conflicts with an existing asset.
    """
    data = request.get_json(silent=True) or {}
    submitted = {k: v for k, v in data.items() if k in _EDITABLE_FIELDS}

    if not submitted:
        return (
            jsonify({"error": "VALIDATION_ERROR", "message": "No editable fields provided"}),
            400,
        )

    errors = validate_asset_update(submitted)
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

    with get_db() as conn:
        row = conn.execute(
            select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        if row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        current = _row_to_dict(row)

        # Duplicate code check when code is being changed
        if "code" in submitted and str(submitted["code"]).strip() != current["code"]:
            conflict = conn.execute(
                select(fixed_assets.c.asset_id).where(
                    fixed_assets.c.code == str(submitted["code"]).strip()
                )
            ).fetchone()
            if conflict:
                return (
                    jsonify(
                        {
                            "error": "CONFLICT",
                            "message": f"Asset code '{submitted['code']}' already exists",
                        }
                    ),
                    409,
                )

        # Build diff — only fields whose values actually changed
        updates: dict = {}
        changes: list[tuple[str, str, str]] = []  # (field, old_str, new_str)

        for field, new_val in submitted.items():
            if field in ("historical_cost", "salvage_value"):
                new_str = to_db_string(Decimal(str(new_val)))
                old_str = current[field]
                if new_str != old_str:
                    updates[field] = new_str
                    changes.append((field, old_str, new_str))
            elif field == "useful_life_months":
                new_int = int(new_val)
                old_int = current[field]
                if new_int != old_int:
                    updates[field] = new_int
                    changes.append((field, str(old_int), str(new_int)))
            elif field == "code":
                new_str = str(new_val).strip()
                old_str = current[field]
                if new_str != old_str:
                    updates[field] = new_str
                    changes.append((field, old_str, new_str))
            elif field in _NULLABLE_MONETARY_IMPORT_FIELDS:
                # Nullable monetary — store as D3 TEXT or NULL
                if new_val is None or str(new_val).strip() == "":
                    new_stored: str | None = None
                else:
                    new_stored = to_db_string(Decimal(str(new_val)))
                old_stored: str | None = current.get(field)
                if new_stored != old_stored:
                    updates[field] = new_stored
                    changes.append((field, old_stored or "", new_stored or ""))
            elif field in _NULLABLE_TEXT_IMPORT_FIELDS:
                # Nullable text — store as stripped string or NULL
                new_stored = str(new_val).strip() if new_val and str(new_val).strip() else None
                old_stored = current.get(field)
                if new_stored != old_stored:
                    updates[field] = new_stored
                    changes.append((field, old_stored or "", new_stored or ""))
            else:
                new_str = str(new_val).strip() if field != "acquisition_date" else str(new_val)
                old_str = current[field]
                if new_str != old_str:
                    updates[field] = new_str
                    changes.append((field, old_str, new_str))

        if updates:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            updates["updated_at"] = now
            conn.execute(
                fixed_assets.update().where(fixed_assets.c.asset_id == asset_id).values(**updates)
            )
            updated_row = conn.execute(
                select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
            ).fetchone()
            conn.commit()
        else:
            updated_row = row  # No changes — return current state

    # Read actor from app_config after committing asset update
    with get_db() as conn:
        config_row = conn.execute(
            select(app_config.c.company_name).where(app_config.c.config_id == 1)
        ).fetchone()
    actor = (config_row.company_name or "system").strip() if config_row else "system"

    # Write one audit entry per changed field
    for field, old_val, new_val in changes:
        _audit_logger.log_change(
            entity_type="asset",
            entity_id=asset_id,
            action="UPDATE",
            field=field,
            old_value=old_val,
            new_value=new_val,
            actor=actor,
        )

    return jsonify({"data": _row_to_dict(updated_row)}), 200


@assets_bp.post("/<int:asset_id>/retire")
@require_auth
def retire_asset(asset_id: int):
    """POST /api/v1/assets/<asset_id>/retire — Retire an active asset.

    Body: {"retirement_date": "YYYY-MM-DD"}
    Returns 200 with updated asset on success.
    Returns 400 if retirement_date missing or invalid.
    Returns 404 if asset not found.
    Returns 409 if asset already retired or has open maintenance event.
    """
    data = request.get_json(silent=True) or {}

    errors = validate_retirement_date(data)
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

    retirement_date = str(data["retirement_date"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db() as conn:
        row = conn.execute(
            select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        if row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        current = _row_to_dict(row)

        if current["status"] == "retired":
            return jsonify({"error": "CONFLICT", "message": "Asset is already retired"}), 409

        # Check for open maintenance events (covers in_maintenance status and edge cases)
        open_event = conn.execute(
            select(maintenance_events.c.event_id)
            .where(maintenance_events.c.asset_id == asset_id)
            .where(maintenance_events.c.status == "open")
        ).fetchone()
        if current["status"] == "in_maintenance" or open_event:
            return (
                jsonify(
                    {
                        "error": "CONFLICT",
                        "message": (
                            "El activo tiene un evento de mantenimiento abierto. "
                            "Ciérralo antes de dar de baja."
                        ),
                    }
                ),
                409,
            )

        conn.execute(
            fixed_assets.update()
            .where(fixed_assets.c.asset_id == asset_id)
            .values(status="retired", retirement_date=retirement_date, updated_at=now)
        )
        updated_row = conn.execute(
            select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        conn.commit()

    # Read actor AFTER committing — same pattern as update_asset
    with get_db() as conn:
        config_row = conn.execute(
            select(app_config.c.company_name).where(app_config.c.config_id == 1)
        ).fetchone()
    actor = (config_row.company_name or "system").strip() if config_row else "system"

    _audit_logger.log_change(
        entity_type="asset",
        entity_id=asset_id,
        action="RETIRE",
        new_value=retirement_date,
        actor=actor,
    )

    return jsonify({"data": _row_to_dict(updated_row)}), 200


@assets_bp.delete("/<int:asset_id>")
@require_auth
def delete_asset(asset_id: int):
    """DELETE /api/v1/assets/<asset_id> — Physically delete an asset with no history.

    Returns 204 on success.
    Returns 404 if asset not found.
    Returns 409 if asset has depreciation_results or maintenance_events (FR6).
    """
    with get_db() as conn:
        row = conn.execute(
            select(fixed_assets.c.asset_id).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        if row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        # Protect assets with history (FR6)
        has_depreciation = conn.execute(
            select(depreciation_results.c.result_id).where(
                depreciation_results.c.asset_id == asset_id
            )
        ).fetchone()
        _history_conflict = (
            jsonify(
                {
                    "error": "CONFLICT",
                    "message": "No se puede eliminar el activo porque tiene historial asociado.",
                }
            ),
            409,
        )

        if has_depreciation:
            return _history_conflict

        has_maintenance = conn.execute(
            select(maintenance_events.c.event_id).where(maintenance_events.c.asset_id == asset_id)
        ).fetchone()
        if has_maintenance:
            return _history_conflict

        conn.execute(fixed_assets.delete().where(fixed_assets.c.asset_id == asset_id))
        conn.commit()

    # Read actor AFTER committing — same pattern as retire_asset
    with get_db() as conn:
        config_row = conn.execute(
            select(app_config.c.company_name).where(app_config.c.config_id == 1)
        ).fetchone()
    actor = (config_row.company_name or "system").strip() if config_row else "system"

    _audit_logger.log_change(
        entity_type="asset",
        entity_id=asset_id,
        action="DELETE",
        actor=actor,
    )

    return "", 204
