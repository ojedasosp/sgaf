"""Tests for GET /api/v1/audit/ — read-only audit log endpoint.

Covers:
  GET: success (200), empty list, filtering by entity_type + entity_id,
       reverse-chronological ordering, missing params (400), unauthenticated (401).
  Immutability: POST/PUT/PATCH/DELETE return 405.
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import audit_logs, fixed_assets

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    """Reset the jwt_secret cache between tests to prevent cross-test bleed."""
    clear_jwt_secret_cache()
    yield
    clear_jwt_secret_cache()


def _setup_auth(test_engine, password: str = "testpass123") -> str:
    """Insert credentials into app_config and return a valid JWT secret."""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s, "
                "company_name='TestCo', company_nit='123' WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()
    return jwt_secret


@pytest.fixture
def auth_token(test_client, test_engine):
    """Set up valid credentials and return a Bearer token string."""
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


def _insert_audit_entry(conn, entity_id: int, action: str = "CREATE", **overrides) -> None:
    """Insert an audit log entry directly into DB."""
    defaults = {
        "timestamp": "2026-03-10T10:00:00Z",
        "actor": "TestCo",
        "entity_type": "asset",
        "entity_id": entity_id,
        "action": action,
        "field": None,
        "old_value": None,
        "new_value": None,
    }
    defaults.update(overrides)
    conn.execute(insert(audit_logs).values(**defaults))
    conn.commit()


def _insert_asset(conn, code: str = "LAP-001") -> int:
    """Insert a minimal fixed asset directly into DB and return asset_id."""
    result = conn.execute(
        insert(fixed_assets).values(
            code=code,
            description="Test Asset",
            historical_cost="1200.0000",
            salvage_value="120.0000",
            useful_life_months=60,
            acquisition_date="2026-03-01",
            category="Equipos de Cómputo",
            depreciation_method="straight_line",
            status="active",
            created_at="2026-03-01T00:00:00Z",
            updated_at="2026-03-01T00:00:00Z",
        )
    )
    conn.commit()
    return result.lastrowid


def _get_audit(test_client, token: str, entity_type: str = "asset", entity_id: int = 1):
    """Helper: GET /api/v1/audit/ with query params and auth header."""
    return test_client.get(
        f"/api/v1/audit/?entity_type={entity_type}&entity_id={entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/audit/ — success cases
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    def test_returns_audit_entries_for_asset(self, test_client, auth_token, test_engine):
        """Returns 200 with audit entries for the given entity (AC5)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn)
            _insert_audit_entry(conn, asset_id, action="CREATE")
        resp = _get_audit(test_client, auth_token, entity_type="asset", entity_id=asset_id)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert "total" in body
        assert body["total"] == 1
        assert body["data"][0]["action"] == "CREATE"
        assert body["data"][0]["entity_id"] == asset_id

    def test_returns_empty_list_when_no_entries(self, test_client, auth_token, test_engine):
        """Returns empty list when no audit entries exist for the given entity."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn)
        resp = _get_audit(test_client, auth_token, entity_type="asset", entity_id=asset_id)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_returns_entries_in_reverse_chronological_order(
        self, test_client, auth_token, test_engine
    ):
        """Entries are ordered by timestamp DESC — most recent first (AC5)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn)
            _insert_audit_entry(conn, asset_id, action="CREATE", timestamp="2026-03-09T10:00:00Z")
            _insert_audit_entry(
                conn,
                asset_id,
                action="UPDATE",
                timestamp="2026-03-10T15:00:00Z",
                field="description",
                old_value="Old",
                new_value="New",
            )
            _insert_audit_entry(
                conn,
                asset_id,
                action="UPDATE",
                timestamp="2026-03-11T08:00:00Z",
                field="category",
                old_value="A",
                new_value="B",
            )
        resp = _get_audit(test_client, auth_token, entity_type="asset", entity_id=asset_id)
        data = resp.get_json()["data"]
        assert len(data) == 3
        timestamps = [e["timestamp"] for e in data]
        assert timestamps == sorted(timestamps, reverse=True)
        assert data[0]["timestamp"] == "2026-03-11T08:00:00Z"

    def test_filters_by_entity_id_only_returns_matching(self, test_client, auth_token, test_engine):
        """Only returns entries for the specified entity_id, not other assets."""
        with test_engine.connect() as conn:
            asset_id_1 = _insert_asset(conn, code="LAP-001")
            asset_id_2 = _insert_asset(conn, code="LAP-002")
            _insert_audit_entry(conn, asset_id_1, action="CREATE")
            _insert_audit_entry(conn, asset_id_2, action="CREATE")
        resp = _get_audit(test_client, auth_token, entity_type="asset", entity_id=asset_id_1)
        data = resp.get_json()["data"]
        assert len(data) == 1
        assert data[0]["entity_id"] == asset_id_1

    def test_response_entry_has_all_fields(self, test_client, auth_token, test_engine):
        """Each audit entry in the response contains all expected fields."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn)
            _insert_audit_entry(
                conn,
                asset_id,
                action="UPDATE",
                field="description",
                old_value="Old",
                new_value="New",
                timestamp="2026-03-10T12:00:00Z",
            )
        resp = _get_audit(test_client, auth_token, entity_type="asset", entity_id=asset_id)
        entry = resp.get_json()["data"][0]
        for key in [
            "log_id",
            "timestamp",
            "actor",
            "entity_type",
            "entity_id",
            "action",
            "field",
            "old_value",
            "new_value",
        ]:
            assert key in entry, f"Missing field in audit entry: {key}"


# ---------------------------------------------------------------------------
# GET /api/v1/audit/ — error cases
# ---------------------------------------------------------------------------


class TestGetAuditLogErrors:
    def test_missing_entity_type_returns_400(self, test_client, auth_token):
        """Missing entity_type query param returns 400."""
        resp = test_client.get(
            "/api/v1/audit/?entity_id=1",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_missing_entity_id_returns_400(self, test_client, auth_token):
        """Missing entity_id query param returns 400."""
        resp = test_client.get(
            "/api/v1/audit/?entity_type=asset",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_non_integer_entity_id_returns_400(self, test_client, auth_token):
        """Non-integer entity_id returns 400."""
        resp = test_client.get(
            "/api/v1/audit/?entity_type=asset&entity_id=abc",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_unauthenticated_returns_401(self, test_client):
        """GET without auth header returns 401."""
        resp = test_client.get("/api/v1/audit/?entity_type=asset&entity_id=1")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Immutability — no write operations allowed (NFR11)
# ---------------------------------------------------------------------------


class TestAuditImmutability:
    def test_post_returns_405(self, test_client, auth_token):
        """POST on /api/v1/audit/ is not allowed (405)."""
        resp = test_client.post(
            "/api/v1/audit/",
            json={"action": "CREATE"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 405

    def test_put_returns_405(self, test_client, auth_token):
        """PUT on /api/v1/audit/ is not allowed (405)."""
        resp = test_client.put(
            "/api/v1/audit/",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 405

    def test_patch_returns_405(self, test_client, auth_token):
        """PATCH on /api/v1/audit/ is not allowed (405)."""
        resp = test_client.patch(
            "/api/v1/audit/",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 405

    def test_delete_returns_405(self, test_client, auth_token):
        """DELETE on /api/v1/audit/ is not allowed (405)."""
        resp = test_client.delete(
            "/api/v1/audit/",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 405
