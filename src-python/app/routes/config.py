"""Config routes — setup wizard and company configuration endpoints.

Unauthenticated endpoints (no require_auth):
  GET  /api/v1/config/setup-status
  POST /api/v1/config/setup

Authenticated endpoints (require_auth):
  GET  /api/v1/config/company
  PUT  /api/v1/config/company
  POST /api/v1/config/change-password
"""

import json
import secrets
from datetime import datetime, timezone

import bcrypt
from flask import Blueprint, jsonify, request
from sqlalchemy import select, update

from app.database import get_db
from app.middleware import require_auth
from app.models.tables import app_config
from app.utils.audit_logger import AuditLogger

config_bp = Blueprint("config", __name__, url_prefix="/api/v1/config")
_audit_logger = AuditLogger()


def _get_config_row(conn):
    """Return the single app_config row (id=1). Always exists after migrations."""
    return conn.execute(select(app_config).where(app_config.c.config_id == 1)).fetchone()


@config_bp.get("/setup-status")
def get_setup_status():
    """Return whether first-launch setup has been completed.

    Setup is considered complete when password_hash is non-empty.
    """
    with get_db() as conn:
        row = _get_config_row(conn)
    setup_complete = bool(row and row.password_hash)
    return jsonify({"data": {"setup_complete": setup_complete}})


@config_bp.post("/setup")
def post_setup():
    """Save company info and password from the first-launch wizard.

    Validates inputs, bcrypt-hashes the password, generates a JWT secret,
    and updates app_config row 1 atomically.
    """
    # Guard: reject re-setup if setup already completed
    with get_db() as conn:
        existing = _get_config_row(conn)
    if existing and existing.password_hash:
        return (
            jsonify(
                {
                    "error": "SETUP_ALREADY_COMPLETE",
                    "message": "Setup has already been completed",
                }
            ),
            409,
        )

    body = request.get_json(silent=True) or {}
    company_name = (body.get("company_name") or "").strip()
    company_nit = (body.get("company_nit") or "").strip()
    password = body.get("password") or ""
    password_confirm = body.get("password_confirm") or ""
    logo_path = body.get("logo_path")  # optional, may be None

    # Validate inputs
    if not company_name:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "Company name is required",
                    "field": "company_name",
                }
            ),
            400,
        )
    if not company_nit:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "NIT is required",
                    "field": "company_nit",
                }
            ),
            400,
        )
    if not company_nit.isdigit():
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "NIT must contain only numbers",
                    "field": "company_nit",
                }
            ),
            400,
        )
    if len(password) < 8:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "Password must be at least 8 characters",
                    "field": "password",
                }
            ),
            400,
        )
    if password != password_confirm:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "Passwords do not match",
                    "field": "password_confirm",
                }
            ),
            400,
        )

    # Hash password and generate JWT secret
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    jwt_secret = secrets.token_hex(32)  # 64-char hex string
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stmt = (
        update(app_config)
        .where(app_config.c.config_id == 1)
        .values(
            company_name=company_name,
            company_nit=company_nit,
            password_hash=password_hash,
            jwt_secret=jwt_secret,
            logo_path=logo_path,
            updated_at=now,
        )
    )
    with get_db() as conn:
        conn.execute(stmt)
        conn.commit()

    _audit_logger.log_change(
        entity_type="config",
        entity_id=1,
        action="CREATE",
        actor="system",
    )
    return jsonify({"data": {"ok": True}})


@config_bp.get("/company")
@require_auth
def get_company():
    """Return current company configuration (name, NIT, logo path).

    Returns 200 with company_name, company_nit, logo_path.
    """
    with get_db() as conn:
        row = _get_config_row(conn)
    return jsonify({
        "data": {
            "company_name": row.company_name if row else "",
            "company_nit": row.company_nit if row else "",
            "logo_path": row.logo_path if row else None,
        }
    })


@config_bp.put("/company")
@require_auth
def update_company():
    """Update company information (name, NIT, logo).

    Validates inputs, updates app_config row 1, writes audit log.
    Returns 200 on success.
    Returns 400 for validation errors.
    """
    body = request.get_json(silent=True) or {}
    company_name = (body.get("company_name") or "").strip()
    company_nit = (body.get("company_nit") or "").strip()
    logo_path = body.get("logo_path")  # optional, may be None

    if not company_name:
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "Company name is required",
                "field": "company_name",
            }),
            400,
        )
    if not company_nit:
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "NIT is required",
                "field": "company_nit",
            }),
            400,
        )
    if not company_nit.isdigit():
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "NIT must contain only numbers",
                "field": "company_nit",
            }),
            400,
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stmt = (
        update(app_config)
        .where(app_config.c.config_id == 1)
        .values(company_name=company_name, company_nit=company_nit, logo_path=logo_path, updated_at=now)
    )
    with get_db() as conn:
        actor_row = _get_config_row(conn)
        actor = (actor_row.company_name or "system").strip() if actor_row else "system"
        conn.execute(stmt)
        conn.commit()

    _audit_logger.log_change(
        entity_type="config",
        entity_id=1,
        action="UPDATE",
        field="company_info",
        actor=actor,
    )
    return jsonify({"data": {"ok": True}})


@config_bp.post("/change-password")
@require_auth
def change_password():
    """Change the application access password.

    Verifies current password, stores new bcrypt hash. JWT secret is NOT
    rotated — the current session token remains valid after the change.
    Returns 200 on success.
    Returns 400 for validation errors or wrong current password.
    """
    body = request.get_json(silent=True) or {}
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""
    new_password_confirm = body.get("new_password_confirm") or ""

    if not current_password:
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "Current password is required",
                "field": "current_password",
            }),
            400,
        )
    if len(new_password) < 8:
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "New password must be at least 8 characters",
                "field": "new_password",
            }),
            400,
        )
    if new_password != new_password_confirm:
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "Passwords do not match",
                "field": "new_password_confirm",
            }),
            400,
        )

    with get_db() as conn:
        row = _get_config_row(conn)

    if not row or not row.password_hash:
        return (
            jsonify({"error": "UNAUTHORIZED", "message": "Invalid or missing token"}),
            401,
        )

    if not bcrypt.checkpw(current_password.encode("utf-8"), row.password_hash.encode("utf-8")):
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "La contraseña actual es incorrecta",
                "field": "current_password",
            }),
            400,
        )

    new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    actor = (row.company_name or "system").strip()

    stmt = (
        update(app_config)
        .where(app_config.c.config_id == 1)
        .values(password_hash=new_hash, updated_at=now)
    )
    with get_db() as conn:
        conn.execute(stmt)
        conn.commit()

    _audit_logger.log_change(
        entity_type="config",
        entity_id=1,
        action="UPDATE",
        field="password",
        actor=actor,
    )
    return jsonify({"data": {"ok": True}})


@config_bp.get("/categories")
@require_auth
def get_categories():
    """Return list of configured asset categories.

    Returns 200 with categories array.
    """
    with get_db() as conn:
        row = _get_config_row(conn)
    raw = row.asset_categories if row and row.asset_categories else "[]"
    try:
        categories = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        categories = []
    return jsonify({"data": {"categories": categories}})


@config_bp.put("/categories")
@require_auth
def update_categories():
    """Replace the full list of asset categories.

    Validates that payload is a non-null array of non-empty strings.
    Returns 200 on success.
    Returns 400 for validation errors.
    """
    body = request.get_json(silent=True) or {}
    categories = body.get("categories")

    if not isinstance(categories, list):
        return (
            jsonify({
                "error": "VALIDATION_ERROR",
                "message": "categories must be an array",
                "field": "categories",
            }),
            400,
        )

    cleaned = []
    for item in categories:
        if not isinstance(item, str) or not item.strip():
            return (
                jsonify({
                    "error": "VALIDATION_ERROR",
                    "message": "Each category must be a non-empty string",
                    "field": "categories",
                }),
                400,
            )
        cleaned.append(item.strip())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stmt = (
        update(app_config)
        .where(app_config.c.config_id == 1)
        .values(asset_categories=json.dumps(cleaned), updated_at=now)
    )
    with get_db() as conn:
        actor_row = _get_config_row(conn)
        actor = (actor_row.company_name or "system").strip() if actor_row else "system"
        conn.execute(stmt)
        conn.commit()

    _audit_logger.log_change(
        entity_type="config",
        entity_id=1,
        action="UPDATE",
        field="asset_categories",
        actor=actor,
    )
    return jsonify({"data": {"ok": True}})
