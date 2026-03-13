"""Read-only audit log endpoint for SGAF.

The audit log is append-only and immutable at every layer.
No POST/PUT/PATCH/DELETE operations are exposed — GET only (NFR11).
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import audit_logs

audit_bp = Blueprint("audit", __name__, url_prefix="/api/v1/audit")


@audit_bp.get("/")
@require_auth
def get_audit_log():
    """GET /api/v1/audit/?entity_type=asset&entity_id=1 — Fetch audit entries for an entity.

    Query parameters (both required):
        entity_type: str — e.g. "asset"
        entity_id:   int — primary key of the entity

    Returns 200 with {"data": [...], "total": N} ordered by timestamp DESC.
    Returns 400 if required query params are missing or entity_id is not an integer.
    Returns 401 if not authenticated.
    """
    entity_type = request.args.get("entity_type")
    entity_id_raw = request.args.get("entity_id")

    if not entity_type or not entity_id_raw:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "entity_type and entity_id query parameters are required",
                }
            ),
            400,
        )

    try:
        entity_id = int(entity_id_raw)
    except (ValueError, TypeError):
        return (
            jsonify({"error": "VALIDATION_ERROR", "message": "entity_id must be an integer"}),
            400,
        )

    with get_db() as conn:
        result = conn.execute(
            select(audit_logs)
            .where(audit_logs.c.entity_type == entity_type)
            .where(audit_logs.c.entity_id == entity_id)
            .order_by(audit_logs.c.timestamp.desc())
        )
        rows = result.fetchall()

    entries = [dict(row._mapping) for row in rows]
    return jsonify({"data": entries, "total": len(entries)}), 200
