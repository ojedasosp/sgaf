"""Tests for the /api/v1/health endpoint (AC2)."""

import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_returns_200(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_returns_json_status_ok(client):
    response = client.get("/api/v1/health")
    data = response.get_json()
    assert data == {"status": "ok"}


def test_health_content_type_is_json(client):
    response = client.get("/api/v1/health")
    assert "application/json" in response.content_type


def test_404_returns_json_not_html(client):
    """All Flask errors must return JSON — never HTML (architecture rule)."""
    response = client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    data = response.get_json()
    assert data is not None
    assert "error" in data


def test_method_not_allowed_returns_json(client):
    """POST to GET-only endpoint returns JSON error, not HTML."""
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    data = response.get_json()
    assert data is not None
    assert "error" in data
