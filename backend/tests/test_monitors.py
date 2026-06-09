"""Tests for routers/monitors.py — all four REST endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    doc.exists = True
    return doc


def _now():
    return datetime.now(timezone.utc)


# ── POST /api/monitors ─────────────────────────────────────────────────────────

class TestCreateMonitor:
    def test_valid_url_returns_201(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.id = "abc123"
        mock_db.collection.return_value.document.return_value = mock_ref

        res = client.post("/api/monitors", json={"url": "https://example.com", "name": "My Site"})

        assert res.status_code == 201
        body = res.json()
        assert body["id"] == "abc123"
        assert body["url"] == "https://example.com/"
        assert body["name"] == "My Site"
        assert body["lastStatus"] is None
        assert body["lastResponseTime"] is None
        assert body["lastCheckedAt"] is None

    def test_creates_firestore_document(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.id = "xyz"
        mock_db.collection.return_value.document.return_value = mock_ref

        client.post("/api/monitors", json={"url": "https://example.com"})

        mock_ref.set.assert_called_once()
        saved = mock_ref.set.call_args[0][0]
        assert saved["url"] == "https://example.com/"
        assert saved["lastStatus"] is None

    def test_name_is_optional_defaults_empty(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.id = "id1"
        mock_db.collection.return_value.document.return_value = mock_ref

        res = client.post("/api/monitors", json={"url": "https://example.com"})

        assert res.status_code == 201
        assert res.json()["name"] == ""

    def test_invalid_url_returns_422(self, client):
        res = client.post("/api/monitors", json={"url": "not-a-url"})
        assert res.status_code == 422

    def test_missing_url_field_returns_422(self, client):
        res = client.post("/api/monitors", json={"name": "No URL"})
        assert res.status_code == 422

    def test_empty_url_returns_422(self, client):
        res = client.post("/api/monitors", json={"url": "", "name": "Empty"})
        assert res.status_code == 422

    def test_url_without_scheme_returns_422(self, client):
        res = client.post("/api/monitors", json={"url": "example.com"})
        assert res.status_code == 422


# ── GET /api/monitors ──────────────────────────────────────────────────────────

class TestListMonitors:
    def test_empty_collection_returns_empty_list(self, client, mock_db):
        mock_db.collection.return_value.stream.return_value = iter([])

        res = client.get("/api/monitors")

        assert res.status_code == 200
        assert res.json() == []

    def test_returns_all_monitors(self, client, mock_db):
        now = _now()
        docs = [
            _make_doc("id1", {"url": "https://a.com", "name": "A", "lastStatus": "up",
                               "lastResponseTime": 100, "lastCheckedAt": now}),
            _make_doc("id2", {"url": "https://b.com", "name": "B", "lastStatus": "down",
                               "lastResponseTime": None, "lastCheckedAt": now}),
        ]
        mock_db.collection.return_value.stream.return_value = iter(docs)

        res = client.get("/api/monitors")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["id"] == "id1"
        assert data[0]["lastStatus"] == "up"
        assert data[0]["lastResponseTime"] == 100
        assert data[1]["id"] == "id2"
        assert data[1]["lastStatus"] == "down"

    def test_null_last_checked_serialises_as_none(self, client, mock_db):
        doc = _make_doc("id1", {"url": "https://a.com", "name": "", "lastStatus": None,
                                 "lastResponseTime": None, "lastCheckedAt": None})
        mock_db.collection.return_value.stream.return_value = iter([doc])

        res = client.get("/api/monitors")

        assert res.status_code == 200
        assert res.json()[0]["lastCheckedAt"] is None

    def test_last_checked_serialised_as_iso_string(self, client, mock_db):
        now = _now()
        doc = _make_doc("id1", {"url": "https://a.com", "name": "", "lastStatus": "up",
                                 "lastResponseTime": 50, "lastCheckedAt": now})
        mock_db.collection.return_value.stream.return_value = iter([doc])

        res = client.get("/api/monitors")

        checked = res.json()[0]["lastCheckedAt"]
        assert isinstance(checked, str)
        assert "T" in checked  # ISO-8601 format


# ── GET /api/monitors/{id}/checks ─────────────────────────────────────────────

class TestGetChecks:
    def _setup_existing_monitor(self, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        mock_db.collection.return_value.document.return_value = mock_ref
        return mock_ref

    def test_monitor_not_found_returns_404(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = False
        mock_db.collection.return_value.document.return_value = mock_ref

        res = client.get("/api/monitors/ghost/checks")

        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

    def test_returns_checks_in_order(self, client, mock_db):
        now = _now()
        mock_ref = self._setup_existing_monitor(mock_db)
        check = _make_doc("chk1", {"status": "up", "statusCode": 200,
                                    "responseTimeMs": 80, "checkedAt": now})
        (mock_ref.collection.return_value
                 .order_by.return_value
                 .limit.return_value
                 .stream.return_value) = iter([check])

        res = client.get("/api/monitors/m1/checks")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["id"] == "chk1"
        assert data[0]["status"] == "up"
        assert data[0]["statusCode"] == 200
        assert data[0]["responseTimeMs"] == 80

    def test_empty_checks_returns_empty_list(self, client, mock_db):
        mock_ref = self._setup_existing_monitor(mock_db)
        (mock_ref.collection.return_value
                 .order_by.return_value
                 .limit.return_value
                 .stream.return_value) = iter([])

        res = client.get("/api/monitors/m1/checks")

        assert res.status_code == 200
        assert res.json() == []

    def test_null_checked_at_serialised_as_none(self, client, mock_db):
        mock_ref = self._setup_existing_monitor(mock_db)
        check = _make_doc("chk2", {"status": "down", "statusCode": None,
                                    "responseTimeMs": None, "checkedAt": None})
        (mock_ref.collection.return_value
                 .order_by.return_value
                 .limit.return_value
                 .stream.return_value) = iter([check])

        res = client.get("/api/monitors/m1/checks")

        assert res.json()[0]["checkedAt"] is None

    def test_queries_descending_with_limit_20(self, client, mock_db):
        mock_ref = self._setup_existing_monitor(mock_db)
        (mock_ref.collection.return_value
                 .order_by.return_value
                 .limit.return_value
                 .stream.return_value) = iter([])

        client.get("/api/monitors/m1/checks")

        mock_ref.collection.return_value.order_by.assert_called_once_with(
            "checkedAt", direction="DESCENDING"
        )
        mock_ref.collection.return_value.order_by.return_value.limit.assert_called_once_with(20)


# ── DELETE /api/monitors/{id} ──────────────────────────────────────────────────
# The delete now uses batched writes (db.batch()) with a limit(100) loop.
# Mock setup: limit().stream() returns checks on the first call, then [] to end the loop.

def _setup_delete_mock(mock_db, mock_ref, checks):
    """Wire mock_ref so the batch-delete loop sees checks once then stops."""
    mock_ref.collection.return_value.limit.return_value.stream.side_effect = [
        iter(checks),
        iter([]),
    ]
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch
    mock_db.collection.return_value.document.return_value = mock_ref
    return mock_batch


class TestDeleteMonitor:
    def test_deletes_monitor_and_checks(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        checks = [MagicMock(), MagicMock()]
        mock_batch = _setup_delete_mock(mock_db, mock_ref, checks)

        res = client.delete("/api/monitors/m1")

        assert res.status_code == 204
        for chk in checks:
            mock_batch.delete.assert_any_call(chk.reference)
        mock_batch.commit.assert_called_once()
        mock_ref.delete.assert_called_once()

    def test_monitor_not_found_returns_404(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = False
        mock_db.collection.return_value.document.return_value = mock_ref

        res = client.delete("/api/monitors/ghost")

        assert res.status_code == 404

    def test_deletes_all_checks_via_batch(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        checks = [MagicMock() for _ in range(5)]
        mock_batch = _setup_delete_mock(mock_db, mock_ref, checks)

        client.delete("/api/monitors/m1")

        assert mock_batch.delete.call_count == 5
        mock_ref.delete.assert_called_once()

    def test_no_checks_still_deletes_monitor(self, client, mock_db):
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        mock_ref.collection.return_value.limit.return_value.stream.return_value = iter([])
        mock_db.collection.return_value.document.return_value = mock_ref

        res = client.delete("/api/monitors/m1")

        assert res.status_code == 204
        mock_ref.delete.assert_called_once()
