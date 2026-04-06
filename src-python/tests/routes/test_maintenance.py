"""Tests for maintenance event endpoints.

Covers:
  POST /api/v1/maintenance/: success (201), audit log written (event only — no asset status change),
       closure fields persisted, validation errors (400), asset not found (404),
       asset not active (409), 401.
  GET /api/v1/maintenance/: success (200), filter by asset_id, empty list, 401.
  PATCH /api/v1/maintenance/<id>: success (200), audit log written, asset status restored,
        already completed (409), not found (404), validation errors (400), 401.
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, select, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import audit_logs, fixed_assets, maintenance_events

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    clear_jwt_secret_cache()
    yield
    clear_jwt_secret_cache()


def _setup_auth(test_engine, password: str = "testpass123") -> None:
    """Insert credentials into app_config."""
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s, "
                "company_name='TestCo' WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()


@pytest.fixture
def auth_token(test_client, test_engine):
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


@pytest.fixture
def active_asset(test_client, auth_token):
    """Create and return an active asset via the API."""
    payload = {
        "code": "LAP-001",
        "description": "Test Laptop",
        "historical_cost": "1200.00",
        "salvage_value": "120.00",
        "useful_life_months": 60,
        "acquisition_date": "2026-01-01",
        "category": "Equipos",
        "depreciation_method": "straight_line",
    }
    resp = test_client.post(
        "/api/v1/assets/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 201
    return resp.get_json()["data"]


def _post_maintenance(test_client, payload: dict, token: str):
    return test_client.post(
        "/api/v1/maintenance/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _valid_create_payload(asset_id: int) -> dict:
    return {
        "asset_id": asset_id,
        "entry_date": "2026-03-16",
        "event_type": "correctivo",
        "description": "Falla en pantalla",
        "vendor": "TechService S.A.",
        "estimated_delivery_date": "2026-03-20",
    }


# ---------------------------------------------------------------------------
# TestMaintenanceCreate
# ---------------------------------------------------------------------------


class TestMaintenanceCreate:
    def test_create_maintenance_event_returns_201(self, test_client, auth_token, active_asset):
        payload = _valid_create_payload(active_asset["asset_id"])
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["asset_id"] == active_asset["asset_id"]
        assert data["status"] == "completed"
        assert data["start_date"] == "2026-03-16"
        assert data["event_type"] == "correctivo"
        assert data["vendor"] == "TechService S.A."
        assert data["event_id"] is not None

    def test_create_does_not_change_asset_status(
        self, test_client, auth_token, active_asset
    ):
        payload = _valid_create_payload(active_asset["asset_id"])
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201

        asset_resp = test_client.get(
            f"/api/v1/assets/{active_asset['asset_id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert asset_resp.status_code == 200
        assert asset_resp.get_json()["data"]["status"] == "active"

    def test_create_writes_audit_log_for_event(
        self, test_client, auth_token, active_asset, test_engine
    ):
        payload = _valid_create_payload(active_asset["asset_id"])
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201
        event_id = resp.get_json()["data"]["event_id"]

        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "maintenance_event")
                    & (audit_logs.c.entity_id == event_id)
                    & (audit_logs.c.action == "CREATE")
                )
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].actor == "system"

    def test_create_does_not_write_asset_status_audit_log(
        self, test_client, auth_token, active_asset, test_engine
    ):
        payload = _valid_create_payload(active_asset["asset_id"])
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201

        with test_engine.connect() as conn:
            rows = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "asset")
                    & (audit_logs.c.entity_id == active_asset["asset_id"])
                    & (audit_logs.c.action == "UPDATE")
                    & (audit_logs.c.field == "status")
                )
            ).fetchall()
        assert len(rows) == 0

    def test_create_with_closure_fields_persisted(self, test_client, auth_token, active_asset):
        payload = {
            "asset_id": active_asset["asset_id"],
            "entry_date": "2026-03-16",
            "description": "Reparación de pantalla",
            "actual_delivery_date": "2026-03-19",
            "actual_cost": "140.00",
            "received_by": "Juan Pérez",
            "closing_observation": "Reparación exitosa",
        }
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "completed"
        assert data["actual_delivery_date"] == "2026-03-19"
        assert data["actual_cost"] == "140.0000"
        assert data["received_by"] == "Juan Pérez"
        assert data["closing_observation"] == "Reparación exitosa"

    def test_create_allows_multiple_events_for_same_asset(
        self, test_client, auth_token, active_asset
    ):
        """Asset stays active after each POST so multiple events can be created."""
        payload = _valid_create_payload(active_asset["asset_id"])
        resp1 = _post_maintenance(test_client, payload, auth_token)
        assert resp1.status_code == 201

        resp2 = _post_maintenance(test_client, payload, auth_token)
        assert resp2.status_code == 201

    def test_create_requires_entry_date(self, test_client, auth_token, active_asset):
        payload = {"asset_id": active_asset["asset_id"], "description": "Sin fecha"}
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "entry_date"

    def test_create_returns_400_for_invalid_entry_date_format(
        self, test_client, auth_token, active_asset
    ):
        """Validator rejects dates that are non-empty but not YYYY-MM-DD."""
        for bad_date in ("16/03/2026", "2026-13-01", "not-a-date", "20260316"):
            payload = {"asset_id": active_asset["asset_id"], "entry_date": bad_date}
            resp = _post_maintenance(test_client, payload, auth_token)
            assert resp.status_code == 400, f"Expected 400 for entry_date={bad_date!r}"
            body = resp.get_json()
            assert body["error"] == "VALIDATION_ERROR"
            assert body["field"] == "entry_date"

    def test_create_returns_400_for_invalid_actual_cost(
        self, test_client, auth_token, active_asset
    ):
        payload = {
            "asset_id": active_asset["asset_id"],
            "entry_date": "2026-03-16",
            "actual_cost": "not-a-number",
        }
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "actual_cost"

    def test_create_returns_400_for_invalid_actual_delivery_date(
        self, test_client, auth_token, active_asset
    ):
        payload = {
            "asset_id": active_asset["asset_id"],
            "entry_date": "2026-03-16",
            "actual_delivery_date": "not-a-date",
        }
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "VALIDATION_ERROR"
        assert body["field"] == "actual_delivery_date"

    def test_create_returns_404_for_unknown_asset(self, test_client, auth_token):
        payload = {"asset_id": 99999, "entry_date": "2026-03-16"}
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 404

    def test_create_returns_409_if_asset_retired(
        self, test_client, auth_token, active_asset
    ):
        # Retire the asset first
        retire_resp = test_client.post(
            f"/api/v1/assets/{active_asset['asset_id']}/retire",
            json={"retirement_date": "2026-03-15"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert retire_resp.status_code == 200

        payload = {"asset_id": active_asset["asset_id"], "entry_date": "2026-03-16"}
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 409

    def test_create_requires_auth(self, test_client, active_asset):
        payload = _valid_create_payload(active_asset["asset_id"])
        resp = test_client.post("/api/v1/maintenance/", json=payload)
        assert resp.status_code == 401

    def test_create_ignores_estimated_cost_field(self, test_client, auth_token, active_asset):
        """estimated_cost is silently ignored after Sprint Change 2026-03-20."""
        payload = {
            "asset_id": active_asset["asset_id"],
            "entry_date": "2026-03-20",
            "estimated_cost": "150.00",
        }
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert "estimated_cost" not in data

    def test_create_with_minimal_payload(self, test_client, auth_token, active_asset):
        """Only asset_id and entry_date are required."""
        payload = {"asset_id": active_asset["asset_id"], "entry_date": "2026-03-16"}
        resp = _post_maintenance(test_client, payload, auth_token)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "completed"
        assert data["event_type"] is None
        assert data["vendor"] is None
        assert data["actual_cost"] is None
        assert data["received_by"] is None
        assert data["closing_observation"] is None


# ---------------------------------------------------------------------------
# TestMaintenanceComplete
# ---------------------------------------------------------------------------


class TestMaintenanceComplete:
    @pytest.fixture
    def open_event(self, test_engine, active_asset):
        """Insert an open maintenance event directly into the DB.

        POST no longer creates open events, so we insert via DB for PATCH tests.
        """
        now = "2026-03-16T10:00:00Z"
        with test_engine.connect() as conn:
            result = conn.execute(
                insert(maintenance_events).values(
                    asset_id=active_asset["asset_id"],
                    description="Test maintenance",
                    start_date="2026-03-16",
                    status="open",
                    created_at=now,
                    updated_at=now,
                )
            )
            conn.commit()
            event_id = result.lastrowid
        return {"event_id": event_id, "asset_id": active_asset["asset_id"]}

    def test_complete_event_returns_200(self, test_client, auth_token, open_event):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={
                "status": "completed",
                "actual_delivery_date": "2026-03-19",
                "actual_cost": "140.00",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "completed"
        assert data["actual_delivery_date"] == "2026-03-19"
        assert data["actual_cost"] == "140.0000"

    def test_complete_sets_asset_status_to_active(
        self, test_client, auth_token, open_event, active_asset, test_engine
    ):
        # Manually set asset to in_maintenance to simulate legacy state
        with test_engine.connect() as conn:
            conn.execute(
                fixed_assets.update()
                .where(fixed_assets.c.asset_id == active_asset["asset_id"])
                .values(status="in_maintenance")
            )
            conn.commit()

        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200

        asset_resp = test_client.get(
            f"/api/v1/assets/{active_asset['asset_id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert asset_resp.status_code == 200
        assert asset_resp.get_json()["data"]["status"] == "active"

    def test_complete_writes_audit_log(
        self, test_client, auth_token, open_event, active_asset, test_engine
    ):
        test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        with test_engine.connect() as conn:
            event_audit = conn.execute(
                select(audit_logs).where(
                    (audit_logs.c.entity_type == "maintenance_event")
                    & (audit_logs.c.entity_id == open_event["event_id"])
                    & (audit_logs.c.action == "UPDATE")
                    & (audit_logs.c.field == "status")
                    & (audit_logs.c.new_value == "completed")
                )
            ).fetchall()
            assert len(event_audit) == 1
            assert event_audit[0].actor == "system"

    def test_complete_returns_409_if_already_completed(
        self, test_client, auth_token, open_event
    ):
        resp1 = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp1.status_code == 200

        resp2 = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp2.status_code == 409
        assert resp2.get_json()["error"] == "CONFLICT"

    def test_complete_returns_404_for_unknown_event(self, test_client, auth_token):
        resp = test_client.patch(
            "/api/v1/maintenance/99999",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 404

    def test_complete_returns_400_for_invalid_status(
        self, test_client, auth_token, open_event
    ):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "invalid_status"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "VALIDATION_ERROR"

    def test_complete_requires_auth(self, test_client, open_event):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
        )
        assert resp.status_code == 401

    def test_complete_with_received_by_persisted(self, test_client, auth_token, open_event):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed", "received_by": "Juan Pérez"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["received_by"] == "Juan Pérez"

    def test_complete_with_closing_observation_persisted(self, test_client, auth_token, open_event):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed", "closing_observation": "Reparación exitosa"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["closing_observation"] == "Reparación exitosa"

    def test_complete_without_closure_fields_succeeds(self, test_client, auth_token, open_event):
        resp = test_client.patch(
            f"/api/v1/maintenance/{open_event['event_id']}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["received_by"] is None
        assert data["closing_observation"] is None


# ---------------------------------------------------------------------------
# TestMaintenanceList
# ---------------------------------------------------------------------------


class TestMaintenanceList:
    def test_list_by_asset_id_returns_events(
        self, test_client, auth_token, active_asset
    ):
        # Create two events — asset stays active after each POST so no PATCH needed
        payload = _valid_create_payload(active_asset["asset_id"])
        r1 = _post_maintenance(test_client, payload, auth_token)
        assert r1.status_code == 201

        r2 = _post_maintenance(test_client, payload, auth_token)
        assert r2.status_code == 201

        resp = test_client.get(
            f"/api/v1/maintenance/?asset_id={active_asset['asset_id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 2
        assert len(body["data"]) == 2
        for event in body["data"]:
            assert event["asset_id"] == active_asset["asset_id"]

    def test_list_empty_when_no_events(self, test_client, auth_token, active_asset):
        resp = test_client.get(
            f"/api/v1/maintenance/?asset_id={active_asset['asset_id']}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 0
        assert body["data"] == []

    def test_list_without_filter_returns_all(
        self, test_client, auth_token, active_asset
    ):
        payload = _valid_create_payload(active_asset["asset_id"])
        _post_maintenance(test_client, payload, auth_token)

        resp = test_client.get(
            "/api/v1/maintenance/",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["total"] >= 1

    def test_list_requires_auth(self, test_client):
        resp = test_client.get("/api/v1/maintenance/")
        assert resp.status_code == 401

    def test_list_returns_400_for_invalid_asset_id(self, test_client, auth_token):
        resp = test_client.get(
            "/api/v1/maintenance/?asset_id=not_an_int",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 400
