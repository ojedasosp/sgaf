"""Tests for photo management endpoints (Hoja de Vida del Activo feature).

Covers:
    GET  /api/v1/photos/?asset_id=<id>
    POST /api/v1/photos/
    DELETE /api/v1/photos/<photo_id>
    PATCH  /api/v1/photos/<photo_id>/primary
"""

import secrets

import bcrypt
import pytest
from sqlalchemy import insert, text

from app.middleware import clear_jwt_secret_cache
from app.models.tables import fixed_assets, maintenance_events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    clear_jwt_secret_cache()
    yield
    clear_jwt_secret_cache()


def _setup_auth(test_engine, password: str = "testpass123") -> str:
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    jwt_secret = secrets.token_hex(32)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_config SET password_hash=:h, jwt_secret=:s "
                "WHERE config_id=1"
            ),
            {"h": pwd_hash, "s": jwt_secret},
        )
        conn.commit()
    return jwt_secret


@pytest.fixture
def auth_token(test_client, test_engine):
    _setup_auth(test_engine)
    resp = test_client.post("/api/v1/auth/login", json={"password": "testpass123"})
    assert resp.status_code == 200
    return resp.get_json()["data"]["token"]


@pytest.fixture
def asset_id(test_engine):
    """Insert a minimal active asset and return its ID."""
    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="PHOTO-001",
                description="Asset for photo tests",
                historical_cost="5000.0000",
                salvage_value="0.0000",
                useful_life_months=60,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    return result.inserted_primary_key[0]


@pytest.fixture
def photo_file(tmp_path):
    """Create a minimal valid JPEG file for upload tests."""
    p = tmp_path / "test_photo.jpg"
    # Minimal 1x1 JPEG bytes (valid enough for file existence checks)
    p.write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )
    return str(p)


@pytest.fixture
def test_client_with_tmp(test_engine, monkeypatch, tmp_path):
    """Test client that redirects photo storage to tmp_path."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setenv("SGAF_DB_PATH", str(tmp_path / "sgaf.db"))

    from app import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_photos_empty(test_client_with_tmp, test_engine, tmp_path, monkeypatch):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="EMPTY-001",
                description="Asset no photos",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    resp = test_client_with_tmp.get(
        f"/api/v1/photos/?asset_id={aid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"] == []


def test_upload_photo_first_becomes_primary(test_client_with_tmp, test_engine, tmp_path, photo_file):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="UP-001",
                description="Upload test asset",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    resp = test_client_with_tmp.post(
        "/api/v1/photos/",
        json={"asset_id": aid, "file_path": photo_file},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["is_primary"] == 1
    assert data["asset_id"] == aid


def test_upload_second_photo_not_primary(test_client_with_tmp, test_engine, tmp_path):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="UP-002",
                description="Two photos asset",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    # Create two temp files
    f1 = tmp_path / "photo1.jpg"
    f2 = tmp_path / "photo2.jpg"
    f1.write_bytes(b"\xff\xd8\xff\xd9")
    f2.write_bytes(b"\xff\xd8\xff\xd9")

    resp1 = test_client_with_tmp.post(
        "/api/v1/photos/",
        json={"asset_id": aid, "file_path": str(f1)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201

    resp2 = test_client_with_tmp.post(
        "/api/v1/photos/",
        json={"asset_id": aid, "file_path": str(f2)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 201
    assert resp2.get_json()["data"]["is_primary"] == 0


def test_set_primary(test_client_with_tmp, test_engine, tmp_path):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="PRI-001",
                description="Set primary test",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    f1 = tmp_path / "pri1.jpg"
    f2 = tmp_path / "pri2.jpg"
    f1.write_bytes(b"\xff\xd8\xff\xd9")
    f2.write_bytes(b"\xff\xd8\xff\xd9")

    r1 = test_client_with_tmp.post("/api/v1/photos/", json={"asset_id": aid, "file_path": str(f1)}, headers={"Authorization": f"Bearer {token}"})
    r2 = test_client_with_tmp.post("/api/v1/photos/", json={"asset_id": aid, "file_path": str(f2)}, headers={"Authorization": f"Bearer {token}"})
    photo2_id = r2.get_json()["data"]["photo_id"]

    resp = test_client_with_tmp.patch(
        f"/api/v1/photos/{photo2_id}/primary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["is_primary"] == 1

    # First photo should now be non-primary
    list_resp = test_client_with_tmp.get(
        f"/api/v1/photos/?asset_id={aid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    photos = list_resp.get_json()["data"]
    photo1 = next(p for p in photos if p["photo_id"] != photo2_id)
    assert photo1["is_primary"] == 0


def test_delete_primary_reassigns(test_client_with_tmp, test_engine, tmp_path):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="DEL-001",
                description="Delete primary test",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    f1 = tmp_path / "del1.jpg"
    f2 = tmp_path / "del2.jpg"
    f1.write_bytes(b"\xff\xd8\xff\xd9")
    f2.write_bytes(b"\xff\xd8\xff\xd9")

    r1 = test_client_with_tmp.post("/api/v1/photos/", json={"asset_id": aid, "file_path": str(f1)}, headers={"Authorization": f"Bearer {token}"})
    r2 = test_client_with_tmp.post("/api/v1/photos/", json={"asset_id": aid, "file_path": str(f2)}, headers={"Authorization": f"Bearer {token}"})
    photo1_id = r1.get_json()["data"]["photo_id"]
    photo2_id = r2.get_json()["data"]["photo_id"]

    # Delete the primary (first photo)
    resp = test_client_with_tmp.delete(
        f"/api/v1/photos/{photo1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # The second photo should now be primary
    list_resp = test_client_with_tmp.get(
        f"/api/v1/photos/?asset_id={aid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    photos = list_resp.get_json()["data"]
    assert len(photos) == 1
    assert photos[0]["photo_id"] == photo2_id
    assert photos[0]["is_primary"] == 1


def test_upload_invalid_path(test_client_with_tmp, test_engine):
    _setup_auth(test_engine)
    resp = test_client_with_tmp.post("/api/v1/auth/login", json={"password": "testpass123"})
    token = resp.get_json()["data"]["token"]

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="INV-001",
                description="Invalid path test",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    resp = test_client_with_tmp.post(
        "/api/v1/photos/",
        json={"asset_id": aid, "file_path": "/nonexistent/path/photo.jpg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "VALIDATION_ERROR"


def test_photos_require_auth(test_client_with_tmp, test_engine):
    _setup_auth(test_engine)

    with test_engine.connect() as conn:
        result = conn.execute(
            insert(fixed_assets).values(
                code="AUTH-001",
                description="Auth test asset",
                historical_cost="1000.0000",
                salvage_value="0.0000",
                useful_life_months=12,
                acquisition_date="2024-01-01",
                category="Equipos",
                depreciation_method="straight_line",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )
        )
        conn.commit()
    aid = result.inserted_primary_key[0]

    assert test_client_with_tmp.get(f"/api/v1/photos/?asset_id={aid}").status_code == 401
    assert test_client_with_tmp.post("/api/v1/photos/", json={"asset_id": aid, "file_path": "/tmp/x.jpg"}).status_code == 401
    assert test_client_with_tmp.delete("/api/v1/photos/1").status_code == 401
    assert test_client_with_tmp.patch("/api/v1/photos/1/primary").status_code == 401
