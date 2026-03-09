"""Tests for config setup endpoints (Story 1.3).

Covers:
- GET /api/v1/config/setup-status (incomplete and complete)
- POST /api/v1/config/setup (success, validation failures, idempotency)
"""

import bcrypt
from sqlalchemy import select

from app.models.tables import app_config, audit_logs


def _get_config(test_engine):
    """Helper to read app_config row 1 directly from the test engine."""
    with test_engine.connect() as conn:
        return conn.execute(select(app_config).where(app_config.c.config_id == 1)).fetchone()


VALID_SETUP_PAYLOAD = {
    "company_name": "Empresa de Prueba S.A.S",
    "company_nit": "9001234560",
    "password": "SecurePass1",
    "password_confirm": "SecurePass1",
}


class TestSetupStatus:
    def test_setup_status_incomplete(self, test_client):
        """Fresh DB → setup_complete is False (password_hash is empty from seed)."""
        resp = test_client.get("/api/v1/config/setup-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["setup_complete"] is False

    def test_setup_status_complete(self, test_client):
        """After setup → setup_complete is True."""
        test_client.post(
            "/api/v1/config/setup",
            json=VALID_SETUP_PAYLOAD,
        )
        resp = test_client.get("/api/v1/config/setup-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["setup_complete"] is True


class TestSetupPost:
    def test_setup_success(self, test_client, test_engine):
        """Valid inputs → 200, password_hash is bcrypt, jwt_secret is 64-char hex."""
        resp = test_client.post("/api/v1/config/setup", json=VALID_SETUP_PAYLOAD)
        assert resp.status_code == 200
        assert resp.get_json() == {"data": {"ok": True}}

        # Verify DB state
        row = _get_config(test_engine)
        assert row.company_name == "Empresa de Prueba S.A.S"
        assert row.company_nit == "9001234560"
        # password_hash must be a valid bcrypt hash
        assert bcrypt.checkpw(
            VALID_SETUP_PAYLOAD["password"].encode("utf-8"),
            row.password_hash.encode("utf-8"),
        )
        # jwt_secret is a 64-char hex string
        assert len(row.jwt_secret) == 64
        assert all(c in "0123456789abcdef" for c in row.jwt_secret)

    def test_setup_with_logo_path(self, test_client, test_engine):
        """Logo path is stored when provided."""
        payload = {**VALID_SETUP_PAYLOAD, "logo_path": "/home/user/logo.png"}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 200
        row = _get_config(test_engine)
        assert row.logo_path == "/home/user/logo.png"

    def test_setup_without_logo_path(self, test_client, test_engine):
        """Setup succeeds without logo (optional field)."""
        resp = test_client.post("/api/v1/config/setup", json=VALID_SETUP_PAYLOAD)
        assert resp.status_code == 200
        row = _get_config(test_engine)
        assert row.logo_path is None

    def test_setup_missing_company_name(self, test_client):
        """Empty company_name → 400 VALIDATION_ERROR on company_name."""
        payload = {**VALID_SETUP_PAYLOAD, "company_name": ""}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_name"

    def test_setup_missing_nit(self, test_client):
        """Empty company_nit → 400 VALIDATION_ERROR on company_nit."""
        payload = {**VALID_SETUP_PAYLOAD, "company_nit": ""}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_nit"

    def test_setup_nit_non_numeric(self, test_client):
        """NIT with letters → 400 VALIDATION_ERROR on company_nit."""
        payload = {**VALID_SETUP_PAYLOAD, "company_nit": "900-123-456"}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_nit"

    def test_setup_password_too_short(self, test_client):
        """Password < 8 chars → 400 VALIDATION_ERROR on password."""
        payload = {**VALID_SETUP_PAYLOAD, "password": "short", "password_confirm": "short"}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "password"

    def test_setup_password_mismatch(self, test_client):
        """Confirmation doesn't match → 400 VALIDATION_ERROR on password_confirm."""
        payload = {**VALID_SETUP_PAYLOAD, "password_confirm": "DifferentPass1"}
        resp = test_client.post("/api/v1/config/setup", json=payload)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "password_confirm"

    def test_setup_creates_audit_log(self, test_client, test_engine):
        """Setup creates an audit log entry with entity_type=config, action=CREATE."""
        test_client.post("/api/v1/config/setup", json=VALID_SETUP_PAYLOAD)
        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(audit_logs.c.entity_type == "config")
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].entity_id == 1
        assert rows[0].action == "CREATE"
        assert rows[0].actor == "system"

    def test_setup_rejected_after_completion(self, test_client):
        """Second setup attempt → 409 SETUP_ALREADY_COMPLETE."""
        test_client.post("/api/v1/config/setup", json=VALID_SETUP_PAYLOAD)
        second_payload = {
            "company_name": "Segunda Empresa",
            "company_nit": "8005678901",
            "password": "OtherPass99",
            "password_confirm": "OtherPass99",
        }
        resp = test_client.post("/api/v1/config/setup", json=second_payload)
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"] == "SETUP_ALREADY_COMPLETE"
