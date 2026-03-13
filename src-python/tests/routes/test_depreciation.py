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
    return result.lastrowid


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
        calculated_at_1 = resp1.get_json()["calculated_at"]

        resp2 = test_client.post("/api/v1/depreciation/", json=payload, headers=headers)
        assert resp2.status_code == 200
        calculated_at_2 = resp2.get_json()["calculated_at"]

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
    def test_all_monetary_fields_have_4_decimal_places(
        self, test_client, auth_token, test_engine
    ):
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
                assert _FOUR_DECIMAL_RE.match(value), (
                    f"Field '{field}' = '{value}' does not match 4-decimal pattern"
                )


# ---------------------------------------------------------------------------
# TestPerformance (AC3 - NFR2)
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_calculation_under_5_seconds_for_50_assets(
        self, test_client, auth_token, test_engine
    ):
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

    def test_get_results_under_5_seconds_for_50_assets(
        self, test_client, auth_token, test_engine
    ):
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
