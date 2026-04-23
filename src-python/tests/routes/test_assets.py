"""Tests for POST /api/v1/assets/ and GET /api/v1/assets/ endpoints.

Covers:
  POST: success (201), audit log written, decimal precision, all validation
        error cases (400), duplicate code (409), unauthenticated (401).
  GET:  success (200), empty list, multiple assets, decimal precision in
        response, ordering, unauthenticated (401).
  POST /<id>/retire: success (200), audit entry, conflict cases (409), 404, 400, 401.
  DELETE /<id>: success (204), history protection (409), 404, 401.
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, select, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import (
    audit_logs,
    depreciation_results,
    fixed_assets,
    maintenance_events,
)

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

    def test_useful_life_zero_with_method_none_returns_201(
        self, test_client, auth_token, valid_payload
    ):
        """POST with useful_life_months=0 and depreciation_method='none' is valid (H1 fix)."""
        payload = {
            **valid_payload,
            "useful_life_months": 0,
            "depreciation_method": "none",
            "salvage_value": "0",  # TERRENOS have no salvage
        }
        resp = _post_asset(test_client, payload, auth_token)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["depreciation_method"] == "none"
        assert data["useful_life_months"] == 0

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
    return result.inserted_primary_key[0]


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
        """Each asset in the list has all expected fields including import fields (Story 8.5)."""
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
            # Import fields — migration 009, Story 8.5
            "imported_accumulated_depreciation",
            "additions_improvements",
            "accounting_code",
            "cost_center",
            "supplier",
            "invoice_number",
            "location",
            "characteristics",
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


# ---------------------------------------------------------------------------
# GET /api/v1/assets/<asset_id> helpers
# ---------------------------------------------------------------------------


def _get_asset(test_client, asset_id: int, token: str):
    """Helper: GET /api/v1/assets/<asset_id> with auth header."""
    return test_client.get(
        f"/api/v1/assets/{asset_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


def _patch_asset(test_client, asset_id: int, payload: dict, token: str):
    """Helper: PATCH /api/v1/assets/<asset_id> with auth header."""
    return test_client.patch(
        f"/api/v1/assets/{asset_id}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assets/<asset_id> — get single asset (Task 6)
# ---------------------------------------------------------------------------


class TestGetAsset:
    def test_returns_200_with_full_asset(self, test_client, auth_token, test_engine):
        """Returns 200 with full asset dict when asset exists (AC1)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _get_asset(test_client, asset_id, auth_token)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        asset = body["data"]
        assert asset["asset_id"] == asset_id
        assert asset["code"] == "LAP-001"
        assert asset["historical_cost"] == "1200.0000"
        assert asset["salvage_value"] == "120.0000"

    def test_returns_all_expected_fields(self, test_client, auth_token, test_engine):
        """Response data contains all asset fields including import fields (Story 8.5)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _get_asset(test_client, asset_id, auth_token)
        asset = resp.get_json()["data"]
        for key in [
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
            # Import fields — migration 009, Story 8.5
            "imported_accumulated_depreciation",
            "additions_improvements",
            "accounting_code",
            "cost_center",
            "supplier",
            "invoice_number",
            "location",
            "characteristics",
        ]:
            assert key in asset, f"Missing field: {key}"

    def test_returns_404_for_nonexistent_asset(self, test_client, auth_token):
        """Returns 404 when asset_id does not exist."""
        resp = _get_asset(test_client, 9999, auth_token)
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"

    def test_returns_401_when_unauthenticated(self, test_client, test_engine):
        """Returns 401 when no auth header is provided."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = test_client.get(f"/api/v1/assets/{asset_id}")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# PATCH /api/v1/assets/<asset_id> — partial update (Task 7)
# ---------------------------------------------------------------------------


class TestUpdateAsset:
    def test_partial_update_single_field_returns_200(self, test_client, auth_token, test_engine):
        """Partial update of description returns 200 with updated asset (AC2, AC3)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client, asset_id, {"description": "HP Laptop 15 pulgadas"}, auth_token
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["description"] == "HP Laptop 15 pulgadas"
        assert body["data"]["code"] == "LAP-001"  # Unchanged

    def test_partial_update_writes_one_audit_entry_per_field(
        self, test_client, auth_token, test_engine
    ):
        """Each changed field produces exactly one audit entry (AC3)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _patch_asset(
            test_client,
            asset_id,
            {"description": "HP Laptop 15 pulgadas", "category": "Tecnología"},
            auth_token,
        )
        with test_engine.connect() as conn:
            logs = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_type == "asset",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.action == "UPDATE",
                )
            ).fetchall()
        assert len(logs) == 2
        fields_logged = {log.field for log in logs}
        assert fields_logged == {"description", "category"}

    def test_noop_update_returns_200_with_zero_audit_entries(
        self, test_client, auth_token, test_engine
    ):
        """Submitting same values produces no audit entries (AC3 — unchanged fields skipped)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        # Submit the exact same description that's already in the DB
        resp = _patch_asset(test_client, asset_id, {"description": "Test Asset"}, auth_token)
        assert resp.status_code == 200
        with test_engine.connect() as conn:
            logs = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "UPDATE",
                    audit_logs.c.entity_id == asset_id,
                )
            ).fetchall()
        assert len(logs) == 0

    def test_monetary_field_audit_stores_text_representation(
        self, test_client, auth_token, test_engine
    ):
        """Audit entry for monetary field change stores TEXT representation (AC4)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", historical_cost="1200.0000")
        _patch_asset(test_client, asset_id, {"historical_cost": "1500"}, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "UPDATE",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.field == "historical_cost",
                )
            ).fetchone()
        assert log is not None
        assert log.old_value == "1200.0000"
        assert log.new_value == "1500.0000"

    def test_multi_field_update_produces_correct_audit_count(
        self, test_client, auth_token, test_engine
    ):
        """Three changed fields produce exactly 3 audit entries (AC3)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _patch_asset(
            test_client,
            asset_id,
            {"description": "New Desc", "category": "Nueva Cat", "useful_life_months": 48},
            auth_token,
        )
        with test_engine.connect() as conn:
            logs = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "UPDATE",
                    audit_logs.c.entity_id == asset_id,
                )
            ).fetchall()
        assert len(logs) == 3

    def test_code_conflict_returns_409(self, test_client, auth_token, test_engine):
        """Changing code to an existing code returns 409 CONFLICT."""
        with test_engine.connect() as conn:
            _insert_asset(conn, code="LAP-001")
            asset_id_2 = _insert_asset(conn, code="LAP-002")
        resp = _patch_asset(test_client, asset_id_2, {"code": "LAP-001"}, auth_token)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CONFLICT"

    def test_validation_error_returns_400(self, test_client, auth_token, test_engine):
        """Invalid field value returns 400 VALIDATION_ERROR."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(test_client, asset_id, {"historical_cost": "-999"}, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"
        assert resp.get_json()["field"] == "historical_cost"

    def test_nonexistent_asset_returns_404(self, test_client, auth_token):
        """PATCH on non-existent asset_id returns 404."""
        resp = _patch_asset(test_client, 9999, {"description": "Does not exist"}, auth_token)
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"

    def test_unauthenticated_returns_401(self, test_client, test_engine):
        """PATCH without auth header returns 401."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = test_client.patch(f"/api/v1/assets/{asset_id}", json={"description": "x"})
        assert resp.status_code == 401

    def test_actor_in_audit_entry_is_company_name(self, test_client, auth_token, test_engine):
        """Audit entry actor equals company_name from app_config (AC3)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _patch_asset(test_client, asset_id, {"description": "Updated"}, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "UPDATE",
                    audit_logs.c.entity_id == asset_id,
                )
            ).fetchone()
        # _setup_auth sets company_name='Test'
        assert log is not None
        assert log.actor == "Test"

    def test_empty_payload_returns_400(self, test_client, auth_token, test_engine):
        """Empty or non-editable-field payload returns 400."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(test_client, asset_id, {}, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_patch_with_salvage_gte_historical_cost_returns_400(
        self, test_client, auth_token, test_engine
    ):
        """Supplying both monetary fields where salvage >= historical returns 400."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client,
            asset_id,
            {"historical_cost": "100", "salvage_value": "200"},
            auth_token,
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"
        assert resp.get_json()["field"] == "salvage_value"

    def test_updated_at_changes_after_update(self, test_client, auth_token, test_engine):
        """updated_at timestamp is refreshed after a successful edit."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", updated_at="2026-01-01T00:00:00Z")
        resp = _patch_asset(test_client, asset_id, {"description": "Changed"}, auth_token)
        assert resp.status_code == 200
        new_updated_at = resp.get_json()["data"]["updated_at"]
        assert new_updated_at != "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# PATCH /api/v1/assets/<asset_id> — import fields (Story 8.5)
# ---------------------------------------------------------------------------


class TestPatchImportFields:
    """Tests for PATCH with import fields introduced in Story 8.5."""

    def test_patch_text_import_fields_updates_and_audits(
        self, test_client, auth_token, test_engine
    ):
        """PATCH with text import fields persists values and writes one audit entry each."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        payload = {
            "accounting_code": "1524",
            "cost_center": "CC-01",
            "supplier": "Proveedor SA",
            "invoice_number": "FAC-001",
            "location": "Oficina 201",
            "characteristics": "Portatil 15",
        }
        resp = _patch_asset(test_client, asset_id, payload, auth_token)
        assert resp.status_code == 200
        asset = resp.get_json()["data"]
        assert asset["accounting_code"] == "1524"
        assert asset["cost_center"] == "CC-01"
        assert asset["supplier"] == "Proveedor SA"
        assert asset["invoice_number"] == "FAC-001"
        assert asset["location"] == "Oficina 201"
        assert asset["characteristics"] == "Portatil 15"
        # Verify audit entries — one per changed field
        with test_engine.connect() as conn:
            logs = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_type == "asset",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.action == "UPDATE",
                )
            ).fetchall()
        audit_fields = {log.field for log in logs}
        for field in payload:
            assert field in audit_fields, f"No audit entry for field: {field}"

    def test_patch_imported_accumulated_depreciation_stored_as_d3(
        self, test_client, auth_token, test_engine
    ):
        """imported_accumulated_depreciation is stored as D3 TEXT (4 decimal places)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", historical_cost="100000.0000")
        resp = _patch_asset(
            test_client, asset_id, {"imported_accumulated_depreciation": "50000"}, auth_token
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["imported_accumulated_depreciation"] == "50000.0000"

    def test_patch_additions_improvements_stored_as_d3(
        self, test_client, auth_token, test_engine
    ):
        """additions_improvements is stored as D3 TEXT (4 decimal places)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client, asset_id, {"additions_improvements": "10000.5"}, auth_token
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["additions_improvements"] == "10000.5000"

    def test_patch_import_field_empty_string_clears_value(
        self, test_client, auth_token, test_engine
    ):
        """Sending empty string for a text import field stores NULL in DB."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", accounting_code="OLD")
        resp = _patch_asset(test_client, asset_id, {"accounting_code": ""}, auth_token)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["accounting_code"] is None

    def test_patch_import_field_none_clears_value(
        self, test_client, auth_token, test_engine
    ):
        """Sending null for a monetary import field stores NULL in DB."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn, code="LAP-001", imported_accumulated_depreciation="5000.0000"
            )
        resp = _patch_asset(
            test_client, asset_id, {"imported_accumulated_depreciation": None}, auth_token
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["imported_accumulated_depreciation"] is None

    def test_patch_cross_field_iad_exceeds_effective_cost_returns_400(
        self, test_client, auth_token, test_engine
    ):
        """Cross-field validation rejects imported_accumulated_depreciation > effective_cost."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client,
            asset_id,
            {
                "historical_cost": "100000",
                "salvage_value": "0",
                "imported_accumulated_depreciation": "200000",
                "additions_improvements": "0",
            },
            auth_token,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "imported_accumulated_depreciation"

    def test_patch_iad_negative_rejected(self, test_client, auth_token, test_engine):
        """Negative imported_accumulated_depreciation is rejected with 400."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client, asset_id, {"imported_accumulated_depreciation": "-100"}, auth_token
        )
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "imported_accumulated_depreciation"

    def test_patch_additions_negative_rejected(self, test_client, auth_token, test_engine):
        """Negative additions_improvements is rejected with 400."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client, asset_id, {"additions_improvements": "-50"}, auth_token
        )
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "additions_improvements"

    def test_patch_no_regression_original_fields(self, test_client, auth_token, test_engine):
        """Original 8 PATCH fields still work identically after Story 8.5 changes (AC9)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client, asset_id, {"description": "Nueva descripción"}, auth_token
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["description"] == "Nueva descripción"

    def test_patch_terrenos_method_none_accepted(self, test_client, auth_token, test_engine):
        """PATCH with depreciation_method='none' and useful_life_months=0 is accepted (AC7)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="TERRENO-001")
        resp = _patch_asset(
            test_client,
            asset_id,
            {"depreciation_method": "none", "useful_life_months": 0},
            auth_token,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["depreciation_method"] == "none"
        assert data["useful_life_months"] == 0

    def test_patch_useful_life_zero_without_none_method_rejected(
        self, test_client, auth_token, test_engine
    ):
        """useful_life_months=0 is rejected when method is not 'none'."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _patch_asset(
            test_client,
            asset_id,
            {"useful_life_months": 0, "depreciation_method": "straight_line"},
            auth_token,
        )
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "useful_life_months"

    def test_patch_import_fields_audit_new_value(self, test_client, auth_token, test_engine):
        """Audit log new_value for monetary import field reflects D3 representation."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", historical_cost="100000.0000")
        _patch_asset(
            test_client, asset_id, {"imported_accumulated_depreciation": "25000"}, auth_token
        )
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.field == "imported_accumulated_depreciation",
                )
            ).fetchone()
        assert log is not None
        assert log.new_value == "25000.0000"
        assert log.old_value == ""  # was NULL — stored as empty string in audit

    def test_patch_terrenos_useful_life_zero_without_method_in_payload_accepted(
        self, test_client, auth_token, test_engine
    ):
        """PATCH with useful_life_months=0 alone (no method) is accepted for existing TERRENOS.

        The validator cannot know the current DB method when it is absent from the
        payload — it defers. Frontend always sends method, but direct API callers
        should not be incorrectly rejected (M2 fix).
        """
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="TERRENO-002",
                depreciation_method="none",
                useful_life_months=0,
            )
        resp = _patch_asset(
            test_client, asset_id, {"useful_life_months": 0}, auth_token
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["useful_life_months"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/assets/<asset_id>/retire helpers
# ---------------------------------------------------------------------------


def _retire_asset(test_client, asset_id: int, payload: dict, token: str):
    """Helper: POST to /api/v1/assets/<asset_id>/retire with auth header."""
    return test_client.post(
        f"/api/v1/assets/{asset_id}/retire",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _delete_asset(test_client, asset_id: int, token: str):
    """Helper: DELETE /api/v1/assets/<asset_id> with auth header."""
    return test_client.delete(
        f"/api/v1/assets/{asset_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# POST /api/v1/assets/<asset_id>/retire — retire asset (Tasks 4 & 5)
# ---------------------------------------------------------------------------


class TestRetireAsset:
    def test_returns_200_with_retired_asset(self, test_client, auth_token, test_engine):
        """Retiring an active asset returns 200 with status=retired and retirement_date set."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 200
        asset = resp.get_json()["data"]
        assert asset["status"] == "retired"
        assert asset["retirement_date"] == "2026-03-15"
        assert asset["updated_at"] != "2026-03-01T00:00:00Z"

    def test_updated_at_changes_after_retire(self, test_client, auth_token, test_engine):
        """updated_at is refreshed after retirement."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", updated_at="2026-01-01T00:00:00Z")
        resp = _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["updated_at"] != "2026-01-01T00:00:00Z"

    def test_retire_audit_entry_created(self, test_client, auth_token, test_engine):
        """RETIRE action is written to audit_logs with new_value=retirement_date (AC1)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_type == "asset",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.action == "RETIRE",
                )
            ).fetchone()
        assert log is not None
        assert log.action == "RETIRE"
        assert log.new_value == "2026-03-15"
        assert log.field is None
        assert log.old_value is None

    def test_retire_audit_actor_is_company_name(self, test_client, auth_token, test_engine):
        """Audit actor equals company_name from app_config (trimmed) (AC1)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "RETIRE",
                    audit_logs.c.entity_id == asset_id,
                )
            ).fetchone()
        # _setup_auth sets company_name='Test'
        assert log is not None
        assert log.actor == "Test"

    def test_returns_409_when_already_retired(self, test_client, auth_token, test_engine):
        """Retiring an already-retired asset returns 409 CONFLICT (AC3)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", status="retired")
        resp = _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CONFLICT"

    def test_returns_409_when_in_maintenance(self, test_client, auth_token, test_engine):
        """Retiring an in_maintenance asset returns 409 with maintenance message (AC4)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001", status="in_maintenance")
        resp = _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["error"] == "CONFLICT"
        assert "mantenimiento" in body["message"]

    def test_returns_409_when_has_open_maintenance_event(
        self, test_client, auth_token, test_engine
    ):
        """Retiring an active asset with open maintenance event returns 409 (AC4)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
            conn.execute(
                insert(maintenance_events).values(
                    asset_id=asset_id,
                    description="Open event",
                    start_date="2026-03-01",
                    status="open",
                    created_at="2026-03-01T00:00:00Z",
                    updated_at="2026-03-01T00:00:00Z",
                )
            )
            conn.commit()
        resp = _retire_asset(test_client, asset_id, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 409
        assert "mantenimiento" in resp.get_json()["message"]

    def test_returns_404_when_asset_not_found(self, test_client, auth_token):
        """Retiring a non-existent asset_id returns 404."""
        resp = _retire_asset(test_client, 9999, {"retirement_date": "2026-03-15"}, auth_token)
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"

    def test_returns_400_when_retirement_date_missing(self, test_client, auth_token, test_engine):
        """Missing retirement_date body returns 400 VALIDATION_ERROR."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _retire_asset(test_client, asset_id, {}, auth_token)
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"
        assert resp.get_json()["field"] == "retirement_date"

    def test_returns_400_when_retirement_date_invalid_format(
        self, test_client, auth_token, test_engine
    ):
        """Invalid retirement_date format returns 400 VALIDATION_ERROR."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        for bad_date in ["2026/03/12", "not-a-date", "12-03-2026"]:
            resp = _retire_asset(test_client, asset_id, {"retirement_date": bad_date}, auth_token)
            assert resp.status_code == 400, f"Expected 400 for date: {bad_date}"
            assert resp.get_json()["field"] == "retirement_date"

    def test_returns_401_when_unauthenticated(self, test_client, test_engine):
        """Retire without auth header returns 401."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = test_client.post(
            f"/api/v1/assets/{asset_id}/retire", json={"retirement_date": "2026-03-15"}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/assets/<asset_id> — delete asset (Task 5)
# ---------------------------------------------------------------------------


class TestDeleteAsset:
    def test_returns_204_and_asset_deleted(self, test_client, auth_token, test_engine):
        """Deleting an asset with no history returns 204 (empty body) and removes from DB (AC6)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = _delete_asset(test_client, asset_id, auth_token)
        assert resp.status_code == 204
        assert resp.data == b""
        # Verify asset is gone from DB
        with test_engine.connect() as conn:
            row = conn.execute(
                select(fixed_assets).where(fixed_assets.c.asset_id == asset_id)
            ).fetchone()
        assert row is None

    def test_deleted_asset_returns_404_on_get(self, test_client, auth_token, test_engine):
        """After deletion, GET on the same asset_id returns 404."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _delete_asset(test_client, asset_id, auth_token)
        resp = test_client.get(
            f"/api/v1/assets/{asset_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    def test_returns_409_when_has_depreciation_history(self, test_client, auth_token, test_engine):
        """Deleting an asset with depreciation_results returns 409 CONFLICT (AC5)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
            conn.execute(
                insert(depreciation_results).values(
                    asset_id=asset_id,
                    period_month=3,
                    period_year=2026,
                    depreciation_amount="18.0000",
                    accumulated_depreciation="18.0000",
                    book_value="1182.0000",
                    calculated_at="2026-03-01T00:00:00Z",
                )
            )
            conn.commit()
        resp = _delete_asset(test_client, asset_id, auth_token)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CONFLICT"

    def test_returns_409_when_has_maintenance_history(self, test_client, auth_token, test_engine):
        """Deleting an asset with maintenance_events returns 409 CONFLICT (AC5)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
            conn.execute(
                insert(maintenance_events).values(
                    asset_id=asset_id,
                    description="Some maintenance",
                    start_date="2026-03-01",
                    status="closed",
                    created_at="2026-03-01T00:00:00Z",
                    updated_at="2026-03-01T00:00:00Z",
                )
            )
            conn.commit()
        resp = _delete_asset(test_client, asset_id, auth_token)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CONFLICT"

    def test_returns_404_when_asset_not_found(self, test_client, auth_token):
        """Deleting a non-existent asset returns 404."""
        resp = _delete_asset(test_client, 9999, auth_token)
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "NOT_FOUND"

    def test_delete_audit_entry_written(self, test_client, auth_token, test_engine):
        """Deleting a clean asset writes a DELETE entry to audit_logs (architecture mandate)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _delete_asset(test_client, asset_id, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.entity_type == "asset",
                    audit_logs.c.entity_id == asset_id,
                    audit_logs.c.action == "DELETE",
                )
            ).fetchone()
        assert log is not None
        assert log.action == "DELETE"
        assert log.field is None
        assert log.old_value is None
        assert log.new_value is None

    def test_delete_audit_actor_is_company_name(self, test_client, auth_token, test_engine):
        """DELETE audit entry actor equals company_name from app_config (trimmed)."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        _delete_asset(test_client, asset_id, auth_token)
        with test_engine.connect() as conn:
            log = conn.execute(
                select(audit_logs).where(
                    audit_logs.c.action == "DELETE",
                    audit_logs.c.entity_id == asset_id,
                )
            ).fetchone()
        # _setup_auth sets company_name='Test'
        assert log is not None
        assert log.actor == "Test"

    def test_returns_401_when_unauthenticated(self, test_client, test_engine):
        """DELETE without auth header returns 401."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="LAP-001")
        resp = test_client.delete(f"/api/v1/assets/{asset_id}")
        assert resp.status_code == 401
