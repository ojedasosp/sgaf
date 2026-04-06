"""Maintenance event routes for SGAF.

All endpoints require JWT authentication via @require_auth.
Monetary values (actual_cost) use decimal.Decimal stored as TEXT.
Audit trail is written via AuditLogger — never with direct INSERT to audit_logs.

Asset status transitions:
  - CREATE maintenance event: asset status active → in_maintenance (atomic)
  - COMPLETE maintenance event: asset status in_maintenance → active (atomic)
"""

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import insert, select

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import app_config, fixed_assets, maintenance_events
from app.utils.audit_logger import AuditLogger
from app.utils.decimal_utils import to_db_string
from app.validators.maintenance_validator import (
    validate_maintenance_complete,
    validate_maintenance_create,
)

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/api/v1/maintenance")
_audit_logger = AuditLogger()


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a JSON-serialisable dict."""
    return dict(row._mapping)


def _get_actor() -> str:
    """Read company_name from app_config row 1 for use as audit actor."""
    with get_db() as conn:
        row = conn.execute(
            select(app_config.c.company_name).where(app_config.c.config_id == 1)
        ).fetchone()
    return (row.company_name or "system").strip() if row else "system"


@maintenance_bp.post("/")
@require_auth
def create_maintenance_event():
    """POST /api/v1/maintenance/ — Register a new maintenance event for an active asset.

    Body: {asset_id, entry_date, event_type?, description?, vendor?,
           estimated_delivery_date?}

    Returns 201 with the created maintenance event on success.
    Returns 400 for validation errors.
    Returns 404 if asset not found.
    Returns 409 if asset is not active (in_maintenance or retired).
    """
    data = request.get_json(silent=True) or {}

    errors = validate_maintenance_create(data)
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

    asset_id = int(data["asset_id"])
    entry_date = str(data["entry_date"]).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Optional fields — normalize to None if empty/absent
    event_type = str(data["event_type"]).strip().lower() if data.get("event_type") else None
    description = str(data.get("description", "")).strip()
    vendor = str(data["vendor"]).strip() if data.get("vendor") else None
    estimated_delivery_date = (
        str(data["estimated_delivery_date"]).strip()
        if data.get("estimated_delivery_date")
        else None
    )
    actual_delivery_date = (
        str(data["actual_delivery_date"]).strip() if data.get("actual_delivery_date") else None
    )
    actual_cost_raw = data.get("actual_cost")
    actual_cost = (
        to_db_string(Decimal(str(actual_cost_raw).strip()))
        if actual_cost_raw and str(actual_cost_raw).strip()
        else None
    )
    received_by = str(data["received_by"]).strip() if data.get("received_by") else None
    closing_observation = (
        str(data["closing_observation"]).strip() if data.get("closing_observation") else None
    )
    with get_db() as conn:
        # Verify asset exists
        asset_row = conn.execute(
            select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        if asset_row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        asset = _row_to_dict(asset_row)

        # Verify asset is active
        if asset["status"] != "active":
            return (
                jsonify(
                    {
                        "error": "CONFLICT",
                        "message": "El activo no está disponible para mantenimiento",
                    }
                ),
                409,
            )

        # ATOMIC: insert event as completed directly (no intermediate in_maintenance state)
        stmt = insert(maintenance_events).values(
            asset_id=asset_id,
            description=description,
            start_date=entry_date,
            event_type=event_type,
            vendor=vendor,
            estimated_delivery_date=estimated_delivery_date,
            actual_delivery_date=actual_delivery_date,
            actual_cost=actual_cost,
            received_by=received_by,
            closing_observation=closing_observation,
            status="completed",
            created_at=now,
            updated_at=now,
        )
        result = conn.execute(stmt)
        new_event_id = result.lastrowid

        event_row = conn.execute(
            select(maintenance_events).where(maintenance_events.c.event_id == new_event_id)
        ).fetchone()
        conn.commit()

    # Audit AFTER commit — only the event creation; asset status does not change
    _audit_logger.log_change(
        entity_type="maintenance_event",
        entity_id=new_event_id,
        action="CREATE",
        actor="system",
    )

    return jsonify({"data": _row_to_dict(event_row)}), 201


@maintenance_bp.get("/")
@require_auth
def list_maintenance_events():
    """GET /api/v1/maintenance/ — List maintenance events.

    Optional query param: ?asset_id=<int> to filter by asset.
    Returns 200 with {"data": [...], "total": N}.
    """
    asset_id_param = request.args.get("asset_id")

    with get_db() as conn:
        stmt = select(maintenance_events).order_by(maintenance_events.c.created_at.desc())
        if asset_id_param is not None:
            try:
                asset_id = int(asset_id_param)
            except (ValueError, TypeError):
                return (
                    jsonify({"error": "VALIDATION_ERROR", "message": "asset_id must be an integer"}),
                    400,
                )
            stmt = stmt.where(maintenance_events.c.asset_id == asset_id)

        rows = conn.execute(stmt).fetchall()

    events = [_row_to_dict(row) for row in rows]
    return jsonify({"data": events, "total": len(events)}), 200


@maintenance_bp.patch("/<int:event_id>")
@require_auth
def complete_maintenance_event(event_id: int):
    """PATCH /api/v1/maintenance/<event_id> — Update or complete a maintenance event.

    Body: {status: "completed", actual_delivery_date?, actual_cost?,
           received_by?, closing_observation?}

    Returns 200 with the updated event on success.
    Returns 400 for validation errors.
    Returns 404 if event not found.
    Returns 409 if event is already completed.
    """
    data = request.get_json(silent=True) or {}

    errors = validate_maintenance_complete(data)
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
        event_row = conn.execute(
            select(maintenance_events).where(maintenance_events.c.event_id == event_id)
        ).fetchone()
        if event_row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Maintenance event not found"}), 404

        event = _row_to_dict(event_row)

        if event["status"] == "completed":
            return (
                jsonify(
                    {
                        "error": "CONFLICT",
                        "message": "El evento de mantenimiento ya fue completado",
                    }
                ),
                409,
            )

        asset_id = event["asset_id"]

        # Build update values
        update_values: dict = {"status": "completed", "updated_at": now}

        actual_delivery = data.get("actual_delivery_date")
        if actual_delivery is not None and str(actual_delivery).strip():
            update_values["actual_delivery_date"] = str(actual_delivery).strip()

        actual_cost_raw = data.get("actual_cost")
        if actual_cost_raw is not None and str(actual_cost_raw).strip():
            update_values["actual_cost"] = to_db_string(Decimal(str(actual_cost_raw).strip()))

        received_by_raw = data.get("received_by")
        if received_by_raw is not None and str(received_by_raw).strip():
            update_values["received_by"] = str(received_by_raw).strip()

        closing_obs_raw = data.get("closing_observation")
        if closing_obs_raw is not None and str(closing_obs_raw).strip():
            update_values["closing_observation"] = str(closing_obs_raw).strip()

        # ATOMIC: update event + restore asset status (only if asset is still in_maintenance)
        conn.execute(
            maintenance_events.update()
            .where(maintenance_events.c.event_id == event_id)
            .values(**update_values)
        )
        asset_row = conn.execute(
            select(fixed_assets.c.status).where(fixed_assets.c.asset_id == asset_id)
        ).scalar()
        if asset_row == "in_maintenance":
            conn.execute(
                fixed_assets.update()
                .where(fixed_assets.c.asset_id == asset_id)
                .values(status="active", updated_at=now)
            )

        updated_row = conn.execute(
            select(maintenance_events).where(maintenance_events.c.event_id == event_id)
        ).fetchone()
        asset_was_in_maintenance = asset_row == "in_maintenance"
        conn.commit()

    # Audit AFTER commit
    # maintenance_event entries use actor="system"; asset status entries use company_name
    actor = _get_actor()
    _audit_logger.log_change(
        entity_type="maintenance_event",
        entity_id=event_id,
        action="UPDATE",
        field="status",
        old_value="open",
        new_value="completed",
        actor="system",
    )
    if asset_was_in_maintenance:
        _audit_logger.log_change(
            entity_type="asset",
            entity_id=asset_id,
            action="UPDATE",
            field="status",
            old_value="in_maintenance",
            new_value="active",
            actor=actor,
        )

    return jsonify({"data": _row_to_dict(updated_row)}), 200
