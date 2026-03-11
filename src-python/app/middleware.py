"""JWT authentication middleware for SGAF.

require_auth is the ONLY permitted way to protect Flask endpoints.
Apply as a decorator on any route that requires a valid session token.

Unauthenticated endpoints (no decorator needed):
  GET  /api/v1/health
  GET  /api/v1/config/setup-status
  POST /api/v1/config/setup
  POST /api/v1/auth/login
"""

from functools import wraps

import jwt
from flask import jsonify, request
from sqlalchemy import select

from app.database import get_db
from app.models.tables import app_config

# Module-level cache for jwt_secret — loaded once, valid for process lifetime.
# The secret is set during first-launch wizard and never changes afterward.
_cached_jwt_secret: str | None = None


def _get_jwt_secret() -> str | None:
    """Return cached jwt_secret, loading from DB on first call."""
    global _cached_jwt_secret
    if _cached_jwt_secret is not None:
        return _cached_jwt_secret
    with get_db() as conn:
        row = conn.execute(select(app_config).where(app_config.c.config_id == 1)).fetchone()
    if row and row.jwt_secret:
        _cached_jwt_secret = row.jwt_secret
    return _cached_jwt_secret


def clear_jwt_secret_cache() -> None:
    """Reset the cached jwt_secret. Used by tests."""
    global _cached_jwt_secret
    _cached_jwt_secret = None


def require_auth(f):
    """Decorator that validates the Authorization: Bearer <token> header.

    Returns 401 if:
    - Header is missing or not in "Bearer <token>" format
    - jwt_secret is not set in app_config (setup not complete)
    - Token signature is invalid, expired, or malformed

    On success: calls and returns the decorated function unchanged.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return (
                jsonify({"error": "UNAUTHORIZED", "message": "Invalid or missing token"}),
                401,
            )
        token = auth_header[7:]  # strip "Bearer "

        try:
            secret = _get_jwt_secret()
            if not secret:
                return (
                    jsonify({"error": "UNAUTHORIZED", "message": "Invalid or missing token"}),
                    401,
                )
            jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return (
                jsonify({"error": "UNAUTHORIZED", "message": "Invalid or missing token"}),
                401,
            )

        return f(*args, **kwargs)

    return decorated
