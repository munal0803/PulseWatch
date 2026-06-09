"""Tests for main.py — health endpoint and app startup behaviour."""

from main import app


def test_health_returns_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_unknown_route_is_404(client):
    res = client.get("/does-not-exist")
    assert res.status_code == 404


def test_scheduler_started_on_app_startup(mock_sched, client):
    # client fixture triggers the lifespan, which calls start_scheduler()
    assert mock_sched.add_job.called
    assert mock_sched.start.called


def test_scheduler_stopped_on_app_shutdown(mock_sched):
    # Simulate a running scheduler so stop_scheduler() calls shutdown()
    mock_sched.running = True
    from fastapi.testclient import TestClient

    with TestClient(app) as _:
        pass  # lifespan starts and stops here

    assert mock_sched.shutdown.called


def test_cors_header_present_on_simple_request(client):
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("access-control-allow-origin") == "*"


def test_firestore_error_returns_503(client):
    from unittest.mock import patch
    from google.api_core.exceptions import ServiceUnavailable

    with patch("routers.monitors.db") as mock_db:
        mock_db.collection.return_value.stream.side_effect = ServiceUnavailable("Firestore down")
        res = client.get("/api/monitors")

    assert res.status_code == 503
    assert "unavailable" in res.json()["detail"].lower()


def test_firestore_permission_denied_returns_503(client):
    from unittest.mock import patch
    from google.api_core.exceptions import PermissionDenied

    with patch("routers.monitors.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = PermissionDenied("denied")
        res = client.get("/api/monitors/abc/checks")

    assert res.status_code == 503
