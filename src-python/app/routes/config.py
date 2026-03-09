"""Config routes — setup wizard and company configuration endpoints.

Endpoints in this blueprint are unauthenticated: they are used during first-launch
setup before any JWT is issued. Story 1.4 adds the require_auth decorator to all
other blueprints.
"""

import secrets
from datetime import datetime, timezone

import bcrypt
from flask import Blueprint, jsonify, request
from sqlalchemy import select, update

from app.database import get_db
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
