"""Tests for PDF report endpoints (Story 4.1 + Story 4.2).

Covers:
    POST /api/v1/reports/generate:
    - monthly_summary: 200 + application/pdf with seeded depreciation data
    - asset_register: 200 + application/pdf with seeded assets
    - per_asset: 200 + application/pdf with seeded asset + depreciation trigger
    - invalid report_type: 400 VALIDATION_ERROR
    - per_asset missing asset_id: 400 VALIDATION_ERROR
    - per_asset unknown asset_id: 404 NOT_FOUND
    - unauthenticated: 401 UNAUTHORIZED
    - monthly_summary tracks PDF generation in app_config
    - per_asset does NOT track PDF generation

    GET /api/v1/reports/status:
    - returns null when no PDF generated
    - returns timestamp after monthly_summary generation
    - returns null for a different period
    - requires auth
    - validates period_month
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, select, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import app_config, depreciation_results, fixed_assets

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
    """Insert credentials into app_config and return the jwt_secret."""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s, "
                "company_name='Empresa Prueba SA', company_nit='900111222-3' "
                "WHERE config_id=1"
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


_ASSET_COUNTER = {"n": 0}


def _insert_asset(conn, **overrides) -> int:
    """Insert a minimal valid active asset and return its asset_id."""
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


def _insert_depreciation_result(conn, asset_id: int, period_month: int, period_year: int) -> None:
    """Insert a minimal depreciation result row for testing."""
    conn.execute(
        insert(depreciation_results).values(
            asset_id=asset_id,
            period_month=period_month,
            period_year=period_year,
            depreciation_amount="200.0000",
            accumulated_depreciation="200.0000",
            book_value="11800.0000",
            calculated_at="2026-03-05T14:30:00Z",
        )
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Test: asset_register (no period required)
# ---------------------------------------------------------------------------


class TestAssetRegister:
    def test_returns_pdf(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="AR-001")
            _insert_asset(conn, code="AR-002")

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "asset_register"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type
        assert "Content-Disposition" in resp.headers
        assert "filename=" in resp.headers["Content-Disposition"]
        assert "registro_activos_fijos.pdf" in resp.headers["Content-Disposition"]

    def test_pdf_is_valid_bytes(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            _insert_asset(conn, code="AR-003")

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "asset_register"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.data.startswith(b"%PDF")

    def test_no_assets_still_returns_pdf(self, test_client, auth_token):
        """Empty asset list should produce a valid (but empty-table) PDF."""
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "asset_register"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.data.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Test: monthly_summary
# ---------------------------------------------------------------------------


class TestMonthlySummary:
    def test_returns_pdf_with_depreciation_data(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            asset_id_1 = _insert_asset(conn, code="MS-001")
            asset_id_2 = _insert_asset(conn, code="MS-002")
            _insert_depreciation_result(conn, asset_id_1, 3, 2026)
            _insert_depreciation_result(conn, asset_id_2, 3, 2026)

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2026},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type
        assert resp.data.startswith(b"%PDF")
        assert "Content-Disposition" in resp.headers
        assert "reporte_monthly_summary_2026-03.pdf" in resp.headers["Content-Disposition"]

    def test_empty_period_still_returns_pdf(self, test_client, auth_token):
        """Period with no calculated depreciation should return a valid PDF."""
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 1, "period_year": 2020},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.data.startswith(b"%PDF")

    def test_missing_period_month_returns_400(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_year": 2026},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "period_month"

    def test_missing_period_year_returns_400(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "period_year"


# ---------------------------------------------------------------------------
# Test: per_asset
# ---------------------------------------------------------------------------


class TestPerAsset:
    def test_returns_pdf(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="PA-001")

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "per_asset",
                "asset_id": asset_id,
                "period_month": 3,
                "period_year": 2026,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type
        assert resp.data.startswith(b"%PDF")
        assert "Content-Disposition" in resp.headers
        assert "reporte_per_asset_2026-03.pdf" in resp.headers["Content-Disposition"]

    def test_missing_asset_id_returns_400(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "per_asset",
                "period_month": 3,
                "period_year": 2026,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "asset_id"

    def test_unknown_asset_id_returns_404(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "per_asset",
                "asset_id": 99999,
                "period_month": 3,
                "period_year": 2026,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["error"] == "NOT_FOUND"

    def test_missing_period_month_returns_400(self, test_client, auth_token, test_engine):
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="PA-002")

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "per_asset",
                "asset_id": asset_id,
                "period_year": 2026,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Test: validation and auth
# ---------------------------------------------------------------------------


class TestValidationAndAuth:
    def test_invalid_report_type_returns_400(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "unknown"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "report_type"

    def test_missing_report_type_returns_400(self, test_client, auth_token):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"

    def test_unauthenticated_returns_401(self, test_client):
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "asset_register"},
        )
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "UNAUTHORIZED"

    def test_invalid_token_returns_401(self, test_client, test_engine):
        _setup_auth(test_engine)
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "asset_register"},
            headers={"Authorization": "Bearer invalidtoken123"},
        )
        assert resp.status_code == 401

    def test_extended_period_year_range_2150(self, test_client, auth_token):
        """Period year up to 2150 should be valid (20+ year asset useful life)."""
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2150},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.data.startswith(b"%PDF")

    def test_period_year_beyond_range_returns_400(self, test_client, auth_token):
        """Period year > 2150 should be rejected."""
        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2151},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "period_year"


# ---------------------------------------------------------------------------
# Test: monthly_summary PDF tracking (Story 4.2, AC3, AC7)
# ---------------------------------------------------------------------------


class TestPdfTracking:
    def test_monthly_summary_generate_updates_pdf_tracking(
        self, test_client, auth_token, test_engine
    ):
        """After POST /generate with monthly_summary, app_config tracks the timestamp."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="TRK-001")
            _insert_depreciation_result(conn, asset_id, 3, 2026)

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2026},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

        with test_engine.connect() as conn:
            row = conn.execute(
                select(
                    app_config.c.last_monthly_pdf_generated_at,
                    app_config.c.last_monthly_pdf_period_month,
                    app_config.c.last_monthly_pdf_period_year,
                ).where(app_config.c.config_id == 1)
            ).fetchone()

        assert row.last_monthly_pdf_generated_at is not None
        assert row.last_monthly_pdf_period_month == 3
        assert row.last_monthly_pdf_period_year == 2026

    def test_per_asset_generate_does_not_update_pdf_tracking(
        self, test_client, auth_token, test_engine
    ):
        """After POST /generate with per_asset, app_config PDF columns remain NULL."""
        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="TRK-002")

        resp = test_client.post(
            "/api/v1/reports/generate",
            json={
                "report_type": "per_asset",
                "asset_id": asset_id,
                "period_month": 3,
                "period_year": 2026,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

        with test_engine.connect() as conn:
            row = conn.execute(
                select(app_config.c.last_monthly_pdf_generated_at).where(
                    app_config.c.config_id == 1
                )
            ).fetchone()

        assert row.last_monthly_pdf_generated_at is None


# ---------------------------------------------------------------------------
# Test: GET /api/v1/reports/status (Story 4.2, AC7)
# ---------------------------------------------------------------------------


class TestReportStatus:
    def test_get_report_status_returns_null_when_no_pdf_generated(
        self, test_client, test_engine
    ):
        """Fresh DB: GET /reports/status returns null for monthly_summary_generated_at."""
        _setup_auth(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
        token = resp.get_json()["data"]["token"]

        resp = test_client.get(
            "/api/v1/reports/status?period_month=3&period_year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["monthly_summary_generated_at"] is None

    def test_get_report_status_returns_timestamp_after_generation(
        self, test_client, test_engine
    ):
        """After generating monthly_summary PDF, status returns the timestamp."""
        _setup_auth(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
        token = resp.get_json()["data"]["token"]

        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="STS-001")
            _insert_depreciation_result(conn, asset_id, 3, 2026)

        # Generate the PDF first
        gen_resp = test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2026},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert gen_resp.status_code == 200

        # Now check the status
        resp = test_client.get(
            "/api/v1/reports/status?period_month=3&period_year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["monthly_summary_generated_at"] is not None
        assert "T" in body["data"]["monthly_summary_generated_at"]  # ISO8601

    def test_get_report_status_returns_null_for_different_period(
        self, test_client, test_engine
    ):
        """Generated for March 2026 but querying April 2026 returns null."""
        _setup_auth(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
        token = resp.get_json()["data"]["token"]

        with test_engine.connect() as conn:
            asset_id = _insert_asset(conn, code="STS-002")
            _insert_depreciation_result(conn, asset_id, 3, 2026)

        # Generate for March 2026
        test_client.post(
            "/api/v1/reports/generate",
            json={"report_type": "monthly_summary", "period_month": 3, "period_year": 2026},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Query for April 2026 — should return null
        resp = test_client.get(
            "/api/v1/reports/status?period_month=4&period_year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["monthly_summary_generated_at"] is None

    def test_get_report_status_requires_auth(self, test_client):
        """GET /reports/status returns 401 without JWT."""
        resp = test_client.get(
            "/api/v1/reports/status?period_month=3&period_year=2026",
        )
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "UNAUTHORIZED"

    def test_get_report_status_validates_period_month(self, test_client, test_engine):
        """GET /reports/status returns 400 for invalid month."""
        _setup_auth(test_engine)
        resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
        token = resp.get_json()["data"]["token"]

        resp = test_client.get(
            "/api/v1/reports/status?period_month=13&period_year=2026",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "period_month"
