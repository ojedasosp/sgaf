"""Tests for the /api/v1/health endpoint (AC2)."""

from app import create_app


def test_health_returns_200(test_client):
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_returns_json_status_ok(test_client):
    response = test_client.get("/api/v1/health")
    data = response.get_json()
    assert data == {"status": "ok"}


def test_health_content_type_is_json(test_client):
    response = test_client.get("/api/v1/health")
    assert "application/json" in response.content_type


def test_404_returns_json_not_html(test_client):
    """All Flask errors must return JSON — never HTML (architecture rule)."""
    response = test_client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    data = response.get_json()
    assert data is not None
    assert "error" in data


def test_method_not_allowed_returns_json(test_client):
    """POST to GET-only endpoint returns JSON error, not HTML."""
    response = test_client.post("/api/v1/health")
    assert response.status_code == 405
    data = response.get_json()
    assert data is not None
    assert "error" in data


def test_app_factory_works(test_engine, monkeypatch):
    """Verify app factory creates Flask app successfully with DB configured."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setenv("SGAF_DB_PATH", ":memory:")

    flask_app = create_app()
    assert flask_app is not None
    assert flask_app.config["TESTING"] is False
