"""Tests for POST /api/v1/assets/ and GET /api/v1/assets/ endpoints.

Covers:
  POST: success (201), audit log written, decimal precision, all validation
        error cases (400), duplicate code (409), unauthenticated (401).
  GET:  success (200), empty list, multiple assets, decimal precision in
        response, ordering, unauthenticated (401).
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, select, text

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
    """Insert credentials into app_config and return a valid JWT token."""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s, "
                "company_name='Test', company_nit='123' WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()
    # Obtain token via login endpoint (mirrors production flow)
    return jwt_secret


@pytest.fixture
def auth_token(test_client, test_engine):
    """Set up valid credentials and return a Bearer token string."""
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


@pytest.fixture
def valid_payload():
    """A fully valid asset creation payload."""
    return {
        "code": "LAP-001",
        "description": "HP Laptop 14 pulgadas",
        "historical_cost": "1200.00",
        "salvage_value": "120.00",
        "useful_life_months": 60,
        "acquisition_date": "2026-03-01",
        "category": "Equipos de Cómputo",
        "depreciation_method": "straight_line",
    }


def _post_asset(test_client, payload: dict, token: str):
    """Helper: POST to /api/v1/assets/ with auth header."""
    return test_client.post(
        "/api/v1/assets/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


class TestCreateAssetSuccess:
    def test_returns_201(self, test_client, auth_token, valid_payload):
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.status_code == 201

    def test_response_shape(self, test_client, auth_token, valid_payload):
        resp = _post_asset(test_client, valid_payload, auth_token)
        body = resp.get_json()
        assert "data" in body
        asset = body["data"]
        assert asset["code"] == "LAP-001"
        assert asset["description"] == "HP Laptop 14 pulgadas"
        assert asset["category"] == "Equipos de Cómputo"
        assert asset["depreciation_method"] == "straight_line"
        assert asset["useful_life_months"] == 60
        assert asset["acquisition_date"] == "2026-03-01"
        assert "asset_id" in asset
        assert "created_at" in asset
        assert "updated_at" in asset

    def test_status_is_always_active(self, test_client, auth_token, valid_payload):
        """Server sets status=active regardless of any status in the payload."""
        payload = {**valid_payload, "status": "retired"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 201
        assert resp.get_json()["data"]["status"] == "active"

    def test_historical_cost_stored_as_4_decimal_text(self, test_client, auth_token, valid_payload):
        """historical_cost must be stored as a TEXT string with 4 decimal places (AC4)."""
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.status_code == 201
        asset = resp.get_json()["data"]
        # Value returned as TEXT with 4 decimal places
        assert asset["historical_cost"] == "1200.0000"

    def test_salvage_value_stored_as_4_decimal_text(self, test_client, auth_token, valid_payload):
        """salvage_value must be stored as a TEXT string with 4 decimal places (AC4)."""
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.status_code == 201
        asset = resp.get_json()["data"]
        assert asset["salvage_value"] == "120.0000"

    def test_retirement_date_is_null_on_create(self, test_client, auth_token, valid_payload):
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.get_json()["data"]["retirement_date"] is None

    def test_asset_persisted_in_db(self, test_client, auth_token, valid_payload, test_engine):
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.status_code == 201
        asset_id = resp.get_json()["data"]["asset_id"]
        with test_engine.connect() as conn:
            row = conn.execute(
                select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
            ).fetchone()
        assert row is not None
        assert row.code == "LAP-001"
        assert row.status == "active"

    def test_all_three_depreciation_methods_accepted(self, test_client, auth_token, valid_payload):
        """AC5 — all three depreciation methods must be accepted."""
        for i, method in enumerate(["straight_line", "sum_of_digits", "declining_balance"]):
            payload = {
                **valid_payload,
                "code": f"ASSET-{i:03d}",
                "depreciation_method": method,
            }
            resp = _post_asset(test_client, payload, auth_token)
            assert resp.status_code == 201, f"Method {method} was rejected: {resp.get_json()}"
            assert resp.get_json()["data"]["depreciation_method"] == method


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_log_created_on_success(
        self, test_client, auth_token, valid_payload, test_engine
    ):
        """AC3 — successful creation writes a CREATE entry to audit_logs."""
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert resp.status_code == 201
        asset_id = resp.get_json()["data"]["asset_id"]

        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_type == "asset",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.action == "CREATE",
                )
            ).fetchone()

        assert log is not None
        assert log.actor == "system"
        assert log.action == "CREATE"
        assert log.entity_type == "asset"
        assert log.entity_id == asset_id
        # CREATE entries have no field/old_value
        assert log.field is None
        assert log.old_value is None


# ---------------------------------------------------------------------------
# Validation errors (400)
# ---------------------------------------------------------------------------


class TestValidationErrors:
    @pytest.mark.parametrize(
        "missing_field",
        [
            "code",
            "description",
            "category",
            "historical_cost",
            "salvage_value",
            "useful_life_months",
            "acquisition_date",
            "depreciation_method",
        ],
    )
    def test_missing_required_field_returns_400(
        self, test_client, auth_token, valid_payload, missing_field
    ):
        """AC2 — each required field missing returns 400 VALIDATION_ERROR."""
        payload = {k: v for k, v in valid_payload.items() if k != missing_field}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"

    def test_historical_cost_zero_returns_400(self, test_client, auth_token, valid_payload):
        """historical_cost = 0 must be rejected."""
        payload = {**valid_payload, "historical_cost": "0"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"
        assert resp.get_json()["field"] == "historical_cost"

    def test_historical_cost_negative_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "historical_cost": "-500"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "historical_cost"

    def test_salvage_value_equals_historical_cost_returns_400(
        self, test_client, auth_token, valid_payload
    ):
        """salvage_value == historical_cost must be rejected (must be < historical_cost)."""
        payload = {**valid_payload, "salvage_value": valid_payload["historical_cost"]}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "salvage_value"

    def test_salvage_value_greater_than_historical_cost_returns_400(
        self, test_client, auth_token, valid_payload
    ):
        payload = {**valid_payload, "salvage_value": "9999.00"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "salvage_value"

    def test_salvage_value_negative_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "salvage_value": "-1"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "salvage_value"

    def test_useful_life_zero_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "useful_life_months": 0}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "useful_life_months"

    def test_useful_life_negative_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "useful_life_months": -12}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "useful_life_months"

    def test_invalid_depreciation_method_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "depreciation_method": "units_of_production"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "depreciation_method"

    def test_invalid_acquisition_date_format_returns_400(
        self, test_client, auth_token, valid_payload
    ):
        payload = {**valid_payload, "acquisition_date": "01/03/2026"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "acquisition_date"

    def test_non_numeric_historical_cost_returns_400(self, test_client, auth_token, valid_payload):
        payload = {**valid_payload, "historical_cost": "not-a-number"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "historical_cost"

    def test_salvage_value_zero_is_valid(self, test_client, auth_token, valid_payload):
        """salvage_value = 0 is valid (fully depreciable asset)."""
        payload = {**valid_payload, "salvage_value": "0"}
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 201
        assert resp.get_json()["data"]["salvage_value"] == "0.0000"

    def test_error_response_contains_field(self, test_client, auth_token, valid_payload):
        """Validation error response must include 'field' key for frontend inline errors."""
        payload = {**valid_payload, "historical_cost": "-1"}
        resp = _post_asset(test_client, payload, auth_token)
        body = resp.get_json()
        assert "field" in body
        assert "message" in body
        assert "error" in body

    def test_error_response_contains_details_array(self, test_client, auth_token):
        """Validation error response includes 'details' with all field errors."""
        payload = {}  # all fields missing
        resp = _post_asset(test_client, payload, auth_token)
        body = resp.get_json()
        assert resp.status_code == 400
        assert "details" in body
        assert isinstance(body["details"], list)
        assert len(body["details"]) >= 8  # all required fields


# ---------------------------------------------------------------------------
# Conflict (409)
# ---------------------------------------------------------------------------


class TestDuplicateCode:
    def test_duplicate_code_returns_409(self, test_client, auth_token, valid_payload):
        """Duplicate asset code must return 409 CONFLICT."""
        # First creation succeeds
        resp1 = _post_asset(test_client, valid_payload, auth_token)
        assert resp1.status_code == 201

        # Second creation with same code fails
        resp2 = _post_asset(test_client, valid_payload, auth_token)
        assert resp2.status_code == 409
        body = resp2.get_json()
        assert body["error"] == "CONFLICT"

    def test_duplicate_code_error_message_includes_code(
        self, test_client, auth_token, valid_payload
    ):
        _post_asset(test_client, valid_payload, auth_token)
        resp = _post_asset(test_client, valid_payload, auth_token)
        assert "LAP-001" in resp.get_json()["message"]

    def test_different_code_after_duplicate_succeeds(self, test_client, auth_token, valid_payload):
        """Different code must succeed even after a duplicate is rejected."""
        _post_asset(test_client, valid_payload, auth_token)
        payload2 = {**valid_payload, "code": "LAP-002"}
        resp = _post_asset(test_client, payload2, auth_token)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Authentication (401)
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_missing_auth_header_returns_401(self, test_client, valid_payload):
        resp = test_client.post("/api/v1/assets/", json=valid_payload)
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "UNAUTHORIZED"

    def test_invalid_token_returns_401(self, test_client, valid_payload):
        resp = test_client.post(
            "/api/v1/assets/",
            json=valid_payload,
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_response_is_json(self, test_client, valid_payload):
        resp = test_client.post("/api/v1/assets/", json=valid_payload)
        assert resp.content_type.startswith("application/json")


# ---------------------------------------------------------------------------
# GET /api/v1/assets/ helpers
# ---------------------------------------------------------------------------


def _insert_asset(conn, code: str = "LAP-001", **overrides) -> int:
    """Insert a fixed asset directly into DB and return asset_id."""
    defaults = {
        "code": code,
        "description": "Test Asset",
        "historical_cost": "1200.0000",
        "salvage_value": "120.0000",
        "useful_life_months": 60,
        "acquisition_date": "2026-03-01",
        "category": "Equipos de Cómputo",
        "depreciation_method": "straight_line",
        "status": "active",
        "retirement_date": None,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
    }
    defaults.update(overrides)
    result = conn.execute(insert(fixed_assets).values(**defaults))
    conn.commit()
    return result.lastrowid


def _get_assets(test_client, token: str):
    """Helper: GET /api/v1/assets/ with auth header."""
    return test_client.get(
        "/api/v1/assets/",
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assets/ — list assets (Task 2, AC: 1)
# ---------------------------------------------------------------------------


class TestListAssets:
    def test_empty_list_returns_200_with_empty_data(self, test_client, auth_token):
        """Empty database returns 200 with data=[] and total=0."""
        resp = _get_assets(test_client, auth_token)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_returns_all_registered_assets(self, test_client, auth_token, test_engine):
        """All inserted assets appear in the list."""
        with test_engine.connect() as conn:
            _insert_asset(conn, code="LAP-001")
            _insert_asset(conn, code="MON-001")
        resp = _get_assets(test_client, auth_token)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 2
        codes = {a["code"] for a in body["data"]}
        assert codes == {"LAP-001", "MON-001"}

    def test_response_shape_contains_all_fields(self, test_client, auth_token, test_engine):
        """Each asset in the list has all expected fields."""
        with test_engine.connect() as conn:
            _insert_asset(conn, code="LAP-001")
        resp = _get_assets(test_client, auth_token)
        asset = resp.get_json()["data"][0]
        expected_keys = {
            "asset_id",
            "code",
            "description",
            "historical_cost",
            "salvage_value",
            "useful_life_months",
            "acquisition_date",
            "category",
            "depreciation_method",
            "status",
            "retirement_date",
            "created_at",
            "updated_at",
        }
        assert expected_keys.issubset(set(asset.keys()))

    def test_monetary_fields_returned_as_text_strings(self, test_client, auth_token, test_engine):
        """historical_cost and salvage_value must be TEXT strings, never float (NFR12)."""
        with test_engine.connect() as conn:
            _insert_asset(
                conn, code="LAP-001", historical_cost="1200.0000", salvage_value="120.0000"
            )
        resp = _get_assets(test_client, auth_token)
        asset = resp.get_json()["data"][0]
        # Must be a string, not a number
        assert isinstance(asset["historical_cost"], str)
        assert isinstance(asset["salvage_value"], str)
        assert asset["historical_cost"] == "1200.0000"
        assert asset["salvage_value"] == "120.0000"

    def test_default_ordering_is_acquisition_date_descending(
        self, test_client, auth_token, test_engine
    ):
        """Assets must be returned ordered by acquisition_date descending (most recent first)."""
        with test_engine.connect() as conn:
            _insert_asset(conn, code="OLD-001", acquisition_date="2024-01-01")
            _insert_asset(conn, code="NEW-001", acquisition_date="2026-03-01")
            _insert_asset(conn, code="MID-001", acquisition_date="2025-06-15")
        resp = _get_assets(test_client, auth_token)
        data = resp.get_json()["data"]
        dates = [a["acquisition_date"] for a in data]
        assert dates == sorted(dates, reverse=True)
        assert data[0]["code"] == "NEW-001"

    def test_unauthenticated_request_returns_401(self, test_client):
        """GET without auth header must return 401."""
        resp = test_client.get("/api/v1/assets/")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "UNAUTHORIZED"

    def test_response_is_json(self, test_client, auth_token):
        resp = _get_assets(test_client, auth_token)
        assert resp.content_type.startswith("application/json")
