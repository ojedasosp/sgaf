"""Tests for authentication endpoints and require_auth middleware.

Tests POST /api/v1/auth/login and the require_auth decorator.
"""

import secrets

import bcrypt
import jwt
import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_credentials(test_engine, password: str = "testpass123") -> tuple[str, str]:
    """Insert a hashed password and jwt_secret into app_config row 1.

    Returns:
        (password, jwt_secret) — the raw password and the secret stored in DB.
    """
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config "
                "SET password_hash=:h, jwt_secret=:s, "
                "company_name='Test Corp', company_nit='123456' "
                "WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()
    return password, jwt_secret


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_success(self, test_client, test_engine):
        """Correct password returns 200 with a JWT token."""
        password, jwt_secret = _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": password})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert "token" in body["data"]
        token = body["data"]["token"]
        # Token must be a valid JWT signed with our secret
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        assert payload["sub"] == "1"
        assert "iat" in payload

    def test_login_wrong_password(self, test_client, test_engine):
        """Wrong password returns 401."""
        _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "wrongpassword"})
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "UNAUTHORIZED"

    def test_login_missing_password_field(self, test_client, test_engine):
        """Missing password field returns 400 VALIDATION_ERROR."""
        _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "password"

    def test_login_empty_password(self, test_client, test_engine):
        """Empty string password returns 400."""
        _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": ""})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"

    def test_login_no_body(self, test_client, test_engine):
        """No JSON body returns 400."""
        _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login")
        assert resp.status_code == 400

    def test_login_setup_not_complete(self, test_client):
        """Login fails with 401 when setup has not been completed (no password_hash)."""
        # Default test DB has empty password_hash from seed migration
        resp = test_client.post("/api/v1/auth/login", json={"password": "anything"})
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "UNAUTHORIZED"

    def test_login_response_is_json(self, test_client, test_engine):
        """Login endpoint always returns JSON content-type."""
        _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
        assert resp.content_type.startswith("application/json")

    def test_login_audit_log_written(self, test_client, test_engine):
        """Successful login writes an audit log entry."""
        password, _ = _setup_credentials(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": password})
        assert resp.status_code == 200
        with test_engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM audit_logs WHERE action='LOGIN' ORDER BY log_id DESC LIMIT 1")
            ).fetchone()
        assert row is not None
        assert row.entity_type == "config"
        assert row.entity_id == 1
        assert row.action == "LOGIN"


# ---------------------------------------------------------------------------
# require_auth middleware
# ---------------------------------------------------------------------------


@pytest.fixture
def protected_client(test_engine, monkeypatch):
    """Flask test client that includes a temporary protected route for middleware tests."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setenv("SGAF_DB_PATH", ":memory:")

    from app import create_app
    from app.middleware import clear_jwt_secret_cache, require_auth

    clear_jwt_secret_cache()
    flask_app = create_app()
    flask_app.config["TESTING"] = True

    # Register a minimal test-only route protected by require_auth
    @flask_app.get("/api/v1/test/protected")
    @require_auth
    def _protected():
        from flask import jsonify

        return jsonify({"data": {"ok": True}})

    with flask_app.test_client() as client:
        yield client


class TestRequireAuth:
    def test_no_authorization_header(self, protected_client):
        """Missing Authorization header returns 401."""
        resp = protected_client.get("/api/v1/test/protected")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "UNAUTHORIZED"

    def test_bearer_prefix_missing(self, protected_client):
        """Authorization header without 'Bearer ' prefix returns 401."""
        resp = protected_client.get(
            "/api/v1/test/protected", headers={"Authorization": "Token abc123"}
        )
        assert resp.status_code == 401

    def test_bearer_only_no_token(self, protected_client):
        """'Bearer' header with no following token returns 401."""
        resp = protected_client.get("/api/v1/test/protected", headers={"Authorization": "Bearer"})
        assert resp.status_code == 401

    def test_bearer_space_empty_token(self, protected_client, test_engine):
        """'Bearer ' with trailing space but empty token string returns 401."""
        _setup_credentials(test_engine)
        resp = protected_client.get("/api/v1/test/protected", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_invalid_token(self, protected_client):
        """Malformed JWT returns 401."""
        resp = protected_client.get(
            "/api/v1/test/protected", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert resp.status_code == 401

    def test_token_signed_with_wrong_secret(self, protected_client, test_engine):
        """Token signed with wrong secret returns 401."""
        _setup_credentials(test_engine)
        # Sign with a different secret
        bad_token = jwt.encode({"sub": "1"}, "wrong-secret", algorithm="HS256")
        resp = protected_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {bad_token}"}
        )
        assert resp.status_code == 401

    def test_valid_token_passes(self, protected_client, test_engine):
        """Valid JWT from login passes require_auth and returns 200."""
        password, jwt_secret = _setup_credentials(test_engine)
        token = jwt.encode({"sub": "1"}, jwt_secret, algorithm="HS256")
        resp = protected_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["ok"] is True

    def test_no_jwt_secret_in_db(self, protected_client):
        """When jwt_secret is not configured (setup incomplete), return 401."""
        # Default test DB has empty jwt_secret
        some_token = jwt.encode({"sub": "1"}, "any-secret", algorithm="HS256")
        resp = protected_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {some_token}"}
        )
        assert resp.status_code == 401

    def test_error_response_is_json(self, protected_client):
        """401 response is always JSON."""
        resp = protected_client.get("/api/v1/test/protected")
        assert resp.content_type.startswith("application/json")
