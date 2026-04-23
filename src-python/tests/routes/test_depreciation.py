"""Tests for POST /api/v1/depreciation/ and GET /api/v1/depreciation/ endpoints.

Covers:
  POST: success (200), 2 assets, response shape, decimal precision,
        no active assets (200 with message), replace semantics (AC5),
        validation errors (400), unauthenticated (401).
  GET:  results match POST, empty period (200, data=[]).
  Decimal precision: all monetary strings match 4-decimal-place pattern.
"""

import re
import secrets
import time

import bcrypt
import pytest
from sqlalchemy import insert, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import fixed_assets

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
    return jwt_secret


@pytest.fixture
def auth_token(test_client, test_engine):
    """Set up valid credentials and return a Bearer token string."""
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


_NOW = "2025-01-15"
_ASSET_COUNTER = {"n": 0}


def _insert_asset(conn, **overrides):
    """Insert a minimal valid active asset; returns the inserted asset_id."""
    _ASSET_COUNTER["n"] += 1
    n = _ASSET_COUNTER["n"]
    defaults = {
        "code": f"TST-{n:03d}",
        "description": f"Test Asset {n}",
        "historical_cost": "12000.0000",
        "salvage_value": "0.0000",
        "useful_life_months": 60,
        "acquisition_date": "2024-01-01",
        "category": "Equipos",
        "depreciation_method": "straight_line",
        "status": "active",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    result = conn.execute(insert(fixed_assets).values(**defaults))
    conn.commit()
    return result.inserted_primary_key[0]


# ---------------------------------------------------------------------------
# TestCalculatePeriodSuccess (AC2, AC3, AC4)
# ---------------------------------------------------------------------------


class TestCalculatePeriodSuccess:
    def test_returns_200(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn)
            _insert_asset(conn)
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

    def test_response_shape(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="SHP-001")
            _insert_asset(conn, code="SHP-002")
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        body = resp.get_json()
        assert "data" in body
        assert "total" in body
        assert "period_month" in body
        assert "period_year" in body
        assert "calculated_at" in body
        assert body["period_month"] == 3
        assert body["period_year"] == 2025

    def test_total_equals_asset_count(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="TOT-001")
            _insert_asset(conn, code="TOT-002")
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        body = resp.get_json()
        assert body["total"] == 2
        assert len(body["data"]) == 2

    def test_row_contains_required_fields(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="ROW-001")
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        row = resp.get_json()["data"][0]
        for field in (
            "result_id",
            "asset_id",
            "code",
            "description",
            "depreciation_method",
            "opening_book_value",
            "depreciation_amount",
            "accumulated_depreciation",
            "book_value",
            "period_month",
            "period_year",
            "calculated_at",
        ):
            assert field in row, f"Missing field: {field}"

    def test_correct_straight_line_charge(self, test_client, auth_token, test_engine):
        """12000 / 60 months = 200.0000 per month (straight_line, no salvage)."""
        with test_engine.connect() as conn:
            _insert_asset(
                conn,
                code="SL-001",
                historical_cost="12000.0000",
                salvage_value="0.0000",
                useful_life_months=60,
                depreciation_method="straight_line",
                acquisition_date="2024-01-01",
            )
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        row = resp.get_json()["data"][0]
        assert row["depreciation_amount"] == "200.0000"


# ---------------------------------------------------------------------------
# TestCalculateNoActiveAssets (AC6)
# ---------------------------------------------------------------------------


class TestCalculateNoActiveAssets:
    def test_returns_200(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

    def test_data_is_empty(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        body = resp.get_json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_message_present(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        body = resp.get_json()
        assert "message" in body
        assert body["message"] == "No hay activos activos para calcular en este período."


# ---------------------------------------------------------------------------
# TestCalculateReplace (AC5)
# ---------------------------------------------------------------------------


class TestCalculateReplace:
    def test_recalculation_replaces_results(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="REP-001", acquisition_date="2024-01-01")

        payload = {"period_month": 6, "period_year": 2025}
        headers = {"Authorization": f"Bearer {auth_token}"}

        resp1 = test_client.post("/api/v1/depreciation/", json=payload, headers=headers)
        assert resp1.status_code == 200

        resp2 = test_client.post("/api/v1/depreciation/", json=payload, headers=headers)
        assert resp2.status_code == 200

        # Second GET should return only 1 row (no duplicates)
        resp_get = test_client.get(
            "/api/v1/depreciation/?period_month=6&period_year=2025",
            headers=headers,
        )
        body = resp_get.get_json()
        assert body["total"] == 1, f"Expected 1 row after replace, got {body['total']}"

    def test_no_duplicate_rows_in_db(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="DUP-001", acquisition_date="2024-01-01")

        payload = {"period_month": 7, "period_year": 2025}
        headers = {"Authorization": f"Bearer {auth_token}"}

        test_client.post("/api/v1/depreciation/", json=payload, headers=headers)
        test_client.post("/api/v1/depreciation/", json=payload, headers=headers)

        resp = test_client.get(
            "/api/v1/depreciation/?period_month=7&period_year=2025",
            headers=headers,
        )
        assert resp.get_json()["total"] == 1


# ---------------------------------------------------------------------------
# TestCalculateValidation (AC2)
# ---------------------------------------------------------------------------


class TestCalculateValidation:
    def test_invalid_period_month_13(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 13, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_invalid_period_month_0(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 0, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400

    def test_invalid_period_year_low(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 1999},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400

    def test_invalid_period_year_high(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 2100},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400

    def test_missing_period_month(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400

    def test_missing_period_year(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400

    def test_validation_error_field_key_present(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 13, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        body = resp.get_json()
        assert "field" in body


# ---------------------------------------------------------------------------
# TestGetResults (AC3, AC4)
# ---------------------------------------------------------------------------


class TestGetResults:
    def test_get_matches_post_values(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(
                conn,
                code="GET-001",
                historical_cost="12000.0000",
                salvage_value="0.0000",
                useful_life_months=60,
                depreciation_method="straight_line",
                acquisition_date="2024-01-01",
            )
        headers = {"Authorization": f"Bearer {auth_token}"}
        post_resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        post_row = post_resp.get_json()["data"][0]

        get_resp = test_client.get(
            "/api/v1/depreciation/?period_month=3&period_year=2025",
            headers=headers,
        )
        get_row = get_resp.get_json()["data"][0]

        assert post_row["depreciation_amount"] == get_row["depreciation_amount"]
        assert post_row["accumulated_depreciation"] == get_row["accumulated_depreciation"]
        assert post_row["book_value"] == get_row["book_value"]
        assert post_row["opening_book_value"] == get_row["opening_book_value"]

    def test_get_returns_200(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="GR-001", acquisition_date="2024-01-01")
        headers = {"Authorization": f"Bearer {auth_token}"}
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 4, "period_year": 2025},
            headers=headers,
        )
        resp = test_client.get(
            "/api/v1/depreciation/?period_month=4&period_year=2025",
            headers=headers,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestGetEmptyPeriod
# ---------------------------------------------------------------------------


class TestGetEmptyPeriod:
    def test_returns_200_with_empty_data(self, test_client, auth_token):
        resp = test_client.get(
            "/api/v1/depreciation/?period_month=1&period_year=2099",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_get_validates_params(self, test_client, auth_token):
        resp = test_client.get(
            "/api/v1/depreciation/?period_month=13&period_year=2025",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestAuthentication (AC2)
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_post_without_token_returns_401(self, test_client):
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
        )
        assert resp.status_code == 401

    def test_get_without_token_returns_401(self, test_client):
        resp = test_client.get(
            "/api/v1/depreciation/?period_month=3&period_year=2025",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestDecimalPrecision (AC4)
# ---------------------------------------------------------------------------

_FOUR_DECIMAL_RE = re.compile(r"^\d+\.\d{4}$")


class TestDecimalPrecision:
    def test_all_monetary_fields_have_4_decimal_places(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(
                conn,
                code="DEC-001",
                historical_cost="10000.0000",
                salvage_value="1000.0000",
                useful_life_months=48,
                depreciation_method="straight_line",
                acquisition_date="2024-01-01",
            )
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 6, "period_year": 2025},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        for row in resp.get_json()["data"]:
            for field in (
                "opening_book_value",
                "depreciation_amount",
                "accumulated_depreciation",
                "book_value",
            ):
                value = row[field]
                assert _FOUR_DECIMAL_RE.match(
                    value
                ), f"Field '{field}' = '{value}' does not match 4-decimal pattern"


# ---------------------------------------------------------------------------
# TestPerformance (AC3 - NFR2)
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_calculation_under_5_seconds_for_50_assets(self, test_client, auth_token, test_engine):
        """AC3 (NFR2): Calculate depreciation for 50 active assets in < 5 seconds."""
        with test_engine.connect() as conn:
            for i in range(50):
                _insert_asset(
                    conn,
                    code=f"PERF-{i:03d}",
                    acquisition_date="2024-01-01",
                    historical_cost="10000.0000",
                    salvage_value="0.0000",
                    useful_life_months=60,
                    depreciation_method="straight_line",
                )

        headers = {"Authorization": f"Bearer {auth_token}"}
        start = time.time()
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 6, "period_year": 2025},
            headers=headers,
        )
        elapsed = time.time() - start

        assert resp.status_code == 200
        assert resp.get_json()["total"] == 50
        assert elapsed < 5.0, f"Calculation took {elapsed:.2f}s, expected < 5.0s"

    def test_get_results_under_5_seconds_for_50_assets(self, test_client, auth_token, test_engine):
        """AC3: GET results for 50 assets in < 5 seconds (test JOIN optimization)."""
        with test_engine.connect() as conn:
            for i in range(50):
                _insert_asset(
                    conn,
                    code=f"GET-{i:03d}",
                    acquisition_date="2024-01-01",
                    historical_cost="10000.0000",
                    salvage_value="0.0000",
                    useful_life_months=60,
                    depreciation_method="straight_line",
                )

        headers = {"Authorization": f"Bearer {auth_token}"}
        # First POST to populate results
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 7, "period_year": 2025},
            headers=headers,
        )

        # Then GET and measure performance
        start = time.time()
        resp = test_client.get(
            "/api/v1/depreciation/?period_month=7&period_year=2025",
            headers=headers,
        )
        elapsed = time.time() - start

        assert resp.status_code == 200
        assert resp.get_json()["total"] == 50
        assert elapsed < 5.0, f"GET took {elapsed:.2f}s, expected < 5.0s"


# ---------------------------------------------------------------------------
# TestGetAssetHistory (AC2, AC3, Story 3.3)
# ---------------------------------------------------------------------------


class TestGetAssetHistory:
    def test_returns_200_with_history(self, test_client, auth_token, test_engine):
        """GET /assets/<id> returns 200 with depreciation rows after a POST calculation."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="HST-001", acquisition_date="2024-01-01")

        headers = {"Authorization": f"Bearer {auth_token}"}
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1
        assert body["asset_id"] == asset_id
        assert len(body["data"]) == 1

    def test_row_contains_required_fields(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="HST-002", acquisition_date="2024-01-01")

        headers = {"Authorization": f"Bearer {auth_token}"}
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers=headers,
        )
        row = resp.get_json()["data"][0]
        for field in (
            "result_id",
            "asset_id",
            "period_month",
            "period_year",
            "opening_book_value",
            "depreciation_amount",
            "accumulated_depreciation",
            "book_value",
            "calculated_at",
        ):
            assert field in row, f"Missing field: {field}"

    def test_matches_post_monetary_values(self, test_client, auth_token, test_engine):
        """Values from GET /assets/<id> must match the POST calculation output."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="HST-003",
                historical_cost="12000.0000",
                salvage_value="0.0000",
                useful_life_months=60,
                depreciation_method="straight_line",
                acquisition_date="2024-01-01",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        post_resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        post_row = post_resp.get_json()["data"][0]

        get_resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers=headers,
        )
        get_row = get_resp.get_json()["data"][0]

        assert get_row["depreciation_amount"] == post_row["depreciation_amount"]
        assert get_row["accumulated_depreciation"] == post_row["accumulated_depreciation"]
        assert get_row["book_value"] == post_row["book_value"]
        assert get_row["opening_book_value"] == post_row["opening_book_value"]


class TestGetAssetHistoryMultiplePeriods:
    def test_multiple_periods_ordered_chronologically(self, test_client, auth_token, test_engine):
        """POST for 2 periods; asset history returns both, oldest first."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="MUL-001", acquisition_date="2024-01-01")

        headers = {"Authorization": f"Bearer {auth_token}"}
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 2, "period_year": 2025},
            headers=headers,
        )
        test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )

        resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers=headers,
        )
        body = resp.get_json()
        assert body["total"] == 2
        rows = body["data"]
        # Chronological order: Feb before March
        assert rows[0]["period_month"] == 2
        assert rows[1]["period_month"] == 3


class TestGetAssetHistoryEmpty:
    def test_returns_200_with_empty_data_for_asset_without_history(
        self, test_client, auth_token, test_engine
    ):
        """Asset exists but has no depreciation — returns 200 with empty data."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="EMP-001", acquisition_date="2024-01-01")

        resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["total"] == 0
        assert body["asset_id"] == asset_id


class TestGetAssetHistoryNotFound:
    def test_returns_404_for_nonexistent_asset(self, test_client, auth_token):
        """Non-existent asset_id → 404 NOT_FOUND."""
        resp = test_client.get(
            "/api/v1/depreciation/assets/99999",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["error"] == "NOT_FOUND"


class TestGetAssetHistoryAuth:
    def test_requires_authentication(self, test_client, test_engine):
        """GET /assets/<id> without token → 401."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="AUTH-001", acquisition_date="2024-01-01")

        resp = test_client.get(f"/api/v1/depreciation/assets/{asset_id}")
        assert resp.status_code == 401


class TestGetAssetHistoryImmutability:
    def test_replace_semantics_preserved_in_asset_history(
        self, test_client, auth_token, test_engine
    ):
        """POST same period twice (replace); asset history shows only 1 row for that period."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="IMM-001", acquisition_date="2024-01-01")

        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"period_month": 5, "period_year": 2025}
        test_client.post("/api/v1/depreciation/", json=payload, headers=headers)
        test_client.post("/api/v1/depreciation/", json=payload, headers=headers)

        resp = test_client.get(
            f"/api/v1/depreciation/assets/{asset_id}",
            headers=headers,
        )
        assert resp.get_json()["total"] == 1


# ---------------------------------------------------------------------------
# TestTerrenosDepreciation (AC6 — H1 fix)
# ---------------------------------------------------------------------------


class TestTerrenosDepreciation:
    """AC6: TERRENOS (method='none', useful_life_months=0) produce zero depreciation rows."""

    def test_terrenos_produces_zero_depreciation_row(self, test_client, auth_token, test_engine):
        """TERRENOS asset is included in the period with all-zero monetary amounts."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="TER-001",
                description="Terreno Planta Norte",
                historical_cost="500000.0000",
                salvage_value="0.0000",
                depreciation_method="none",
                useful_life_months=0,
                acquisition_date="2024-01-01",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1

        row = body["data"][0]
        assert row["asset_id"] == asset_id
        assert row["depreciation_amount"] == "0.0000"
        assert row["accumulated_depreciation"] == "0.0000"
        assert row["book_value"] == "500000.0000"

    def test_terrenos_included_many_periods_after_acquisition(
        self, test_client, auth_token, test_engine
    ):
        """TERRENOS is not bounded by useful_life — it appears in every period after acquisition."""
        with test_engine.connect() as conn:
            _insert_asset(
                conn,
                code="TER-002",
                historical_cost="200000.0000",
                salvage_value="0.0000",
                depreciation_method="none",
                useful_life_months=0,
                acquisition_date="2020-01-01",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        # Period far beyond any "useful life" boundary — should still appear
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 12, "period_year": 2030},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1
        row = body["data"][0]
        assert row["depreciation_amount"] == "0.0000"
        assert row["book_value"] == "200000.0000"

    def test_terrenos_not_included_before_acquisition(
        self, test_client, auth_token, test_engine
    ):
        """TERRENOS is skipped if the period predates its acquisition date."""
        with test_engine.connect() as conn:
            _insert_asset(
                conn,
                code="TER-003",
                historical_cost="300000.0000",
                salvage_value="0.0000",
                depreciation_method="none",
                useful_life_months=0,
                acquisition_date="2025-06-01",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        # Period before acquisition
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 1, "period_year": 2025},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# TestImportedAssetDepreciation (AC7 — H2 fix)
# ---------------------------------------------------------------------------


class TestImportedAssetDepreciation:
    """AC7: Assets with imported_accumulated_depreciation and additions_improvements
    produce correctly offset accumulated_depreciation and book_value in the trigger."""

    def test_imported_accumulated_depreciation_offsets_result(
        self, test_client, auth_token, test_engine
    ):
        """imported_accumulated_depreciation shifts accumulated and book_value without
        changing the monthly_charge (monthly depreciation amount)."""
        # Straight-line asset: cost=120000, salvage=0, life=120 months
        # monthly_charge = 120000/120 = 1000.0000
        # Period 1: accumulated_from_engine = 1000.0000
        # With imported_accumulated = 60000: total_accumulated = 61000.0000
        # book_value = 120000 - 61000 = 59000.0000
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="IMP-001",
                historical_cost="120000.0000",
                salvage_value="0.0000",
                useful_life_months=120,
                depreciation_method="straight_line",
                acquisition_date="2025-03-01",
                imported_accumulated_depreciation="60000.0000",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},  # period_number=1
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1

        row = body["data"][0]
        assert row["asset_id"] == asset_id
        assert row["depreciation_amount"] == "1000.0000"          # monthly_charge unchanged
        assert row["accumulated_depreciation"] == "61000.0000"    # 60000 + 1000
        assert row["book_value"] == "59000.0000"                  # 120000 - 61000

    def test_additions_improvements_extend_depreciable_base(
        self, test_client, auth_token, test_engine
    ):
        """additions_improvements increase the effective_cost and monthly_charge."""
        # Straight-line: cost=100000, additions=20000 → effective=120000, salvage=0, life=120
        # monthly_charge = 120000/120 = 1000.0000
        # Period 1: accumulated=1000.0000, book_value=119000.0000
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="IMP-002",
                historical_cost="100000.0000",
                salvage_value="0.0000",
                useful_life_months=120,
                depreciation_method="straight_line",
                acquisition_date="2025-03-01",
                additions_improvements="20000.0000",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1

        row = body["data"][0]
        assert row["asset_id"] == asset_id
        assert row["depreciation_amount"] == "1000.0000"    # based on effective_cost 120000
        assert row["accumulated_depreciation"] == "1000.0000"
        assert row["book_value"] == "119000.0000"           # 120000 - 1000

    def test_both_imported_fields_combined(self, test_client, auth_token, test_engine):
        """Both imported_accumulated and additions_improvements work correctly together."""
        # effective_cost = 100000 + 20000 = 120000, life=120, salvage=0
        # monthly_charge = 1000.0000
        # Period 1: engine accumulated = 1000; with import offset = 60000 + 1000 = 61000
        # book_value = 120000 - 61000 = 59000
        with test_engine.connect() as conn:
            asset_id = _insert_asset(
                conn,
                code="IMP-003",
                historical_cost="100000.0000",
                salvage_value="0.0000",
                useful_life_months=120,
                depreciation_method="straight_line",
                acquisition_date="2025-03-01",
                additions_improvements="20000.0000",
                imported_accumulated_depreciation="60000.0000",
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        resp = test_client.post(
            "/api/v1/depreciation/",
            json={"period_month": 3, "period_year": 2025},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1

        row = body["data"][0]
        assert row["asset_id"] == asset_id
        assert row["depreciation_amount"] == "1000.0000"
        assert row["accumulated_depreciation"] == "61000.0000"
        assert row["book_value"] == "59000.0000"
