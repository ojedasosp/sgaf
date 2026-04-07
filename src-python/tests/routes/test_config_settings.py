"""Tests for authenticated config endpoints (Story 6.1).

Covers:
  GET  /api/v1/config/company   — fetch company info
  PUT  /api/v1/config/company   — update company info
  POST /api/v1/config/change-password — change access password
"""

import json
import secrets

import bcrypt
import pytest
from sqlalchemy import select, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import app_config, audit_logs


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    """Reset the jwt_secret cache between tests to prevent cross-test bleed."""
    clear_jwt_secret_cache()
    yield
    clear_jwt_secret_cache()


def _setup_auth(test_engine, password: str = "testpass123") -> None:
    """Insert valid credentials into app_config so the auth layer works."""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s, "
                "company_name='Empresa Test S.A.S', company_nit='9001234560' "
                "WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()


@pytest.fixture
def auth_token(test_client, test_engine):
    """Set up valid credentials and return a Bearer token string."""
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


def _get_config(test_engine):
    """Read app_config row 1 directly."""
    with test_engine.connect() as conn:
        return conn.execute(select(app_config).where(app_config.c.config_id == 1)).fetchone()


# ---------------------------------------------------------------------------
# GET /api/v1/config/company
# ---------------------------------------------------------------------------


class TestGetCompany:
    def test_get_company_returns_200(self, test_client, auth_token):
        """Returns company_name, company_nit, logo_path."""
        resp = test_client.get(
            "/api/v1/config/company",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["company_name"] == "Empresa Test S.A.S"
        assert data["company_nit"] == "9001234560"
        assert data["logo_path"] is None

    def test_get_company_returns_logo_path_when_set(self, test_client, test_engine, auth_token):
        """logo_path is returned when stored."""
        with test_engine.connect() as conn:
            conn.execute(
                text("UPDATE app_config SET logo_path='/home/user/logo.png' WHERE config_id=1")
            )
            conn.commit()
        resp = test_client.get(
            "/api/v1/config/company",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["logo_path"] == "/home/user/logo.png"

    def test_get_company_requires_auth(self, test_client):
        """No token → 401."""
        resp = test_client.get("/api/v1/config/company")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/v1/config/company
# ---------------------------------------------------------------------------


class TestUpdateCompany:
    def test_update_company_success(self, test_client, test_engine, auth_token):
        """Valid payload → 200, DB updated."""
        payload = {
            "company_name": "Nueva Empresa S.A.",
            "company_nit": "8009876543",
            "logo_path": "/path/to/logo.png",
        }
        resp = test_client.put(
            "/api/v1/config/company",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"data": {"ok": True}}

        row = _get_config(test_engine)
        assert row.company_name == "Nueva Empresa S.A."
        assert row.company_nit == "8009876543"
        assert row.logo_path == "/path/to/logo.png"

    def test_update_company_logo_path_optional(self, test_client, test_engine, auth_token):
        """logo_path=None clears the stored logo."""
        payload = {"company_name": "Empresa X", "company_nit": "1234567890", "logo_path": None}
        resp = test_client.put(
            "/api/v1/config/company",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert _get_config(test_engine).logo_path is None

    def test_update_company_missing_name(self, test_client, auth_token):
        """Empty company_name → 400 VALIDATION_ERROR on company_name."""
        resp = test_client.put(
            "/api/v1/config/company",
            json={"company_name": "", "company_nit": "9001234560"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_name"

    def test_update_company_missing_nit(self, test_client, auth_token):
        """Empty company_nit → 400 VALIDATION_ERROR on company_nit."""
        resp = test_client.put(
            "/api/v1/config/company",
            json={"company_name": "Empresa X", "company_nit": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_nit"

    def test_update_company_nit_non_numeric(self, test_client, auth_token):
        """Non-numeric NIT → 400 VALIDATION_ERROR on company_nit."""
        resp = test_client.put(
            "/api/v1/config/company",
            json={"company_name": "Empresa X", "company_nit": "900-123-456"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "company_nit"

    def test_update_company_writes_audit_log(self, test_client, test_engine, auth_token):
        """Successful update writes a CONFIG UPDATE audit entry."""
        test_client.put(
            "/api/v1/config/company",
            json={"company_name": "Auditada S.A.", "company_nit": "1111111111"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "config")
                    & (audit_logs.c.action == "UPDATE")
                    & (audit_logs.c.field == "company_info")
                )
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].entity_id == 1

    def test_update_company_requires_auth(self, test_client):
        """No token → 401."""
        resp = test_client.put(
            "/api/v1/config/company",
            json={"company_name": "X", "company_nit": "123"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/config/change-password
# ---------------------------------------------------------------------------


class TestChangePassword:
    def test_change_password_success(self, test_client, test_engine, auth_token):
        """Correct current password + matching new passwords → 200, hash updated."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"data": {"ok": True}}

        row = _get_config(test_engine)
        assert bcrypt.checkpw(b"NewSecure99", row.password_hash.encode())

    def test_change_password_wrong_current(self, test_client, auth_token):
        """Wrong current password → 400 VALIDATION_ERROR on current_password."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "wrongpassword",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "current_password"

    def test_change_password_mismatch(self, test_client, auth_token):
        """new_password != new_password_confirm → 400 on new_password_confirm."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "NewSecure99",
                "new_password_confirm": "DifferentPass",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "new_password_confirm"

    def test_change_password_too_short(self, test_client, auth_token):
        """New password < 8 chars → 400 on new_password."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "short",
                "new_password_confirm": "short",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "new_password"

    def test_change_password_missing_current(self, test_client, auth_token):
        """Empty current_password → 400 on current_password."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "current_password"

    def test_change_password_writes_audit_log(self, test_client, test_engine, auth_token):
        """Successful change writes a CONFIG UPDATE audit entry on field=password."""
        test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "config")
                    & (audit_logs.c.action == "UPDATE")
                    & (audit_logs.c.field == "password")
                )
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].entity_id == 1

    def test_change_password_jwt_still_valid_after_change(self, test_client, auth_token):
        """The current session token remains valid after a password change."""
        test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        # Token should still work for subsequent requests
        resp = test_client.get(
            "/api/v1/config/company",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

    def test_change_password_requires_auth(self, test_client):
        """No token → 401."""
        resp = test_client.post(
            "/api/v1/config/change-password",
            json={
                "current_password": "testpass123",
                "new_password": "NewSecure99",
                "new_password_confirm": "NewSecure99",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/config/categories
# ---------------------------------------------------------------------------


class TestGetCategories:
    def test_get_categories_returns_default_list(self, test_client, auth_token):
        """Returns the 4 default categories seeded by migration 008."""
        resp = test_client.get(
            "/api/v1/config/categories",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert isinstance(data["categories"], list)
        assert "Equipos de Cómputo" in data["categories"]

    def test_get_categories_returns_empty_when_none_set(self, test_client, test_engine, auth_token):
        """Returns empty array when asset_categories is '[]'."""
        with test_engine.connect() as conn:
            conn.execute(
                text("UPDATE app_config SET asset_categories='[]' WHERE config_id=1")
            )
            conn.commit()
        resp = test_client.get(
            "/api/v1/config/categories",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["categories"] == []

    def test_get_categories_requires_auth(self, test_client):
        """No token → 401."""
        resp = test_client.get("/api/v1/config/categories")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/v1/config/categories
# ---------------------------------------------------------------------------


class TestUpdateCategories:
    def test_update_categories_success(self, test_client, test_engine, auth_token):
        """Valid list → 200, DB updated."""
        payload = {"categories": ["Equipos", "Muebles"]}
        resp = test_client.put(
            "/api/v1/config/categories",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"data": {"ok": True}}

        with test_engine.connect() as conn:
            row = conn.execute(
                select(app_config).where(app_config.c.config_id == 1)
            ).fetchone()
        saved = json.loads(row.asset_categories)
        assert saved == ["Equipos", "Muebles"]

    def test_update_categories_empty_list_allowed(self, test_client, auth_token):
        """Empty array is valid — clears the list."""
        resp = test_client.put(
            "/api/v1/config/categories",
            json={"categories": []},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

    def test_update_categories_invalid_not_array(self, test_client, auth_token):
        """Non-array payload → 400 VALIDATION_ERROR."""
        resp = test_client.put(
            "/api/v1/config/categories",
            json={"categories": "Equipos"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "categories"

    def test_update_categories_invalid_empty_string(self, test_client, auth_token):
        """Array with empty string → 400 VALIDATION_ERROR."""
        resp = test_client.put(
            "/api/v1/config/categories",
            json={"categories": ["Equipos", ""]},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["field"] == "categories"

    def test_update_categories_trims_whitespace(self, test_client, test_engine, auth_token):
        """Category strings are trimmed before saving."""
        resp = test_client.put(
            "/api/v1/config/categories",
            json={"categories": ["  Equipos  ", "Muebles"]},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        with test_engine.connect() as conn:
            row = conn.execute(
                select(app_config).where(app_config.c.config_id == 1)
            ).fetchone()
        saved = json.loads(row.asset_categories)
        assert saved == ["Equipos", "Muebles"]

    def test_update_categories_writes_audit_log(self, test_client, test_engine, auth_token):
        """Successful PUT writes a CONFIG UPDATE audit entry on field=asset_categories."""
        test_client.put(
            "/api/v1/config/categories",
            json={"categories": ["Equipos"]},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "config")
                    & (audit_logs.c.action == "UPDATE")
                    & (audit_logs.c.field == "asset_categories")
                )
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].entity_id == 1

    def test_update_categories_requires_auth(self, test_client):
        """No token → 401."""
        resp = test_client.put(
            "/api/v1/config/categories",
            json={"categories": ["Equipos"]},
        )
        assert resp.status_code == 401
