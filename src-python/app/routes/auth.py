"""Authentication routes for SGAF.

POST /api/v1/auth/login  — verifies bcrypt password, issues JWT (unauthenticated endpoint).
"""

from datetime import datetime, timezone

import bcrypt
import jwt
from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.database import get_db
from app.models.tables import app_config
from app.utils.audit_logger import AuditLogger

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
_audit_logger = AuditLogger()


@auth_bp.post("/login")
def login():
    """Verify password and return a signed JWT.

    Request body: {"password": "<plaintext>"}

    Returns:
        200: {"data": {"token": "<jwt>"}}
        400: password field missing or empty
        401: password incorrect or setup not complete
    """
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return (
            jsonify(
                {
                    "error": "VALIDATION_ERROR",
                    "message": "Password is required",
                    "field": "password",
                }
            ),
            400,
        )

    with get_db() as conn:
        row = conn.execute(select(app_config).where(app_config.c.config_id == 1)).fetchone()

    if not row or not row.password_hash or not row.jwt_secret:
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode(), row.password_hash.encode()):
        return jsonify({"error": "UNAUTHORIZED", "message": "Invalid credentials"}), 401

    token = jwt.encode(
        {"sub": "1", "iat": int(datetime.now(timezone.utc).timestamp())},
        row.jwt_secret,
        algorithm="HS256",
    )

    try:
        _audit_logger.log_change(
            entity_type="config",
            entity_id=1,
            action="LOGIN",
            actor="system",
        )
    except Exception:
        # Audit failure must not block a successful login
        pass

    return jsonify({"data": {"token": token}})
