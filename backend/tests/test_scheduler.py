"""Tests for scheduler.py — ping logic and lifecycle."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from scheduler import ping_url, ping_all_monitors, start_scheduler, stop_scheduler


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_httpx(status_code=200, side_effect=None):
    """Return a context-manager patch for scheduler.httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.status_code = status_code

    mock_client = AsyncMock()
    if side_effect:
        mock_client.get = AsyncMock(side_effect=side_effect)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)

    patcher = patch("scheduler.httpx.AsyncClient")

    def start():
        cls = patcher.start()
        cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        return patcher

    return start, mock_client, mock_response


def _make_monitor_doc(doc_id, url):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = {"url": url}
    return doc


# ── ping_url ───────────────────────────────────────────────────────────────────

class TestPingUrl:
    async def test_success_returns_up_with_status_code(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await ping_url("https://example.com")

        assert result["status"] == "up"
        assert result["statusCode"] == 200

    async def test_records_non_negative_response_time(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await ping_url("https://example.com")

        assert isinstance(result["responseTimeMs"], int)
        assert result["responseTimeMs"] >= 0

    async def test_timeout_propagates_exception(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(httpx.TimeoutException):
                await ping_url("https://example.com")

    async def test_uses_10_second_timeout(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await ping_url("https://example.com")

        cls.assert_called_once_with(timeout=10)

    async def test_non_200_status_still_returns_up(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await ping_url("https://example.com")

        assert result["status"] == "up"
        assert result["statusCode"] == 500


# ── ping_all_monitors ──────────────────────────────────────────────────────────

class TestPingAllMonitors:
    def test_empty_monitors_returns_early(self, mock_db):
        mock_db.collection.return_value.stream.return_value = iter([])

        ping_all_monitors()

        mock_db.collection.return_value.document.assert_not_called()

    def test_successful_ping_writes_up_check(self, mock_db):
        doc = _make_monitor_doc("m1", "https://example.com")
        mock_db.collection.return_value.stream.return_value = iter([doc])

        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        check_data = mock_ref.collection.return_value.add.call_args[0][0]
        assert check_data["status"] == "up"
        assert check_data["statusCode"] == 200
        assert check_data["responseTimeMs"] is not None

        update_data = mock_ref.update.call_args[0][0]
        assert update_data["lastStatus"] == "up"
        assert update_data["lastResponseTime"] is not None

    def test_failed_ping_writes_down_check(self, mock_db):
        doc = _make_monitor_doc("m1", "https://unreachable.local")
        mock_db.collection.return_value.stream.return_value = iter([doc])

        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        check_data = mock_ref.collection.return_value.add.call_args[0][0]
        assert check_data["status"] == "down"
        assert check_data["statusCode"] is None
        assert check_data["responseTimeMs"] is None

        update_data = mock_ref.update.call_args[0][0]
        assert update_data["lastStatus"] == "down"
        assert update_data["lastResponseTime"] is None

    def test_timeout_writes_down_check(self, mock_db):
        doc = _make_monitor_doc("m1", "https://slow.example")
        mock_db.collection.return_value.stream.return_value = iter([doc])
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        check_data = mock_ref.collection.return_value.add.call_args[0][0]
        assert check_data["status"] == "down"

    def test_multiple_monitors_all_pinged(self, mock_db):
        docs = [_make_monitor_doc(f"m{i}", f"https://site{i}.com") for i in range(3)]
        mock_db.collection.return_value.stream.return_value = iter(docs)
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        assert mock_ref.collection.return_value.add.call_count == 3
        assert mock_ref.update.call_count == 3

    def test_check_document_has_checked_at(self, mock_db):
        doc = _make_monitor_doc("m1", "https://example.com")
        mock_db.collection.return_value.stream.return_value = iter([doc])
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        check_data = mock_ref.collection.return_value.add.call_args[0][0]
        assert "checkedAt" in check_data
        assert check_data["checkedAt"] is not None

    def test_writes_to_checks_subcollection(self, mock_db):
        doc = _make_monitor_doc("m1", "https://example.com")
        mock_db.collection.return_value.stream.return_value = iter([doc])
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        mock_ref.collection.assert_called_with("checks")
        mock_ref.collection.return_value.add.assert_called_once()

    def test_monitor_with_no_url_is_skipped(self, mock_db):
        doc = MagicMock()
        doc.id = "m1"
        doc.to_dict.return_value = {}  # no "url" field
        mock_db.collection.return_value.stream.return_value = iter([doc])
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        ping_all_monitors()

        mock_ref.collection.return_value.add.assert_not_called()
        mock_ref.update.assert_not_called()

    def test_firestore_write_failure_does_not_crash(self, mock_db):
        doc = _make_monitor_doc("m1", "https://example.com")
        mock_db.collection.return_value.stream.return_value = iter([doc])

        mock_ref = MagicMock()
        mock_ref.collection.return_value.add.side_effect = Exception("Firestore unavailable")
        mock_db.collection.return_value.document.return_value = mock_ref

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()  # must not raise

    def test_firestore_fetch_failure_returns_early(self, mock_db):
        mock_db.collection.return_value.stream.side_effect = Exception("Firestore down")

        ping_all_monitors()  # must not raise

        mock_db.collection.return_value.document.assert_not_called()


# ── Scheduler lifecycle ────────────────────────────────────────────────────────

class TestSchedulerLifecycle:
    def test_start_adds_interval_job_with_replace_and_max_instances(self, mock_sched):
        start_scheduler()

        mock_sched.add_job.assert_called_once_with(
            ping_all_monitors,
            "interval",
            seconds=60,
            id="ping_monitors",
            replace_existing=True,
            max_instances=1,
        )

    def test_start_calls_start_when_not_running(self, mock_sched):
        mock_sched.running = False  # not yet started
        start_scheduler()

        mock_sched.start.assert_called_once()

    def test_start_skips_start_when_already_running(self, mock_sched):
        mock_sched.running = True  # already running (e.g. hot reload)
        start_scheduler()

        mock_sched.start.assert_not_called()

    def test_stop_shuts_down_when_running(self, mock_sched):
        mock_sched.running = True
        stop_scheduler()

        mock_sched.shutdown.assert_called_once_with(wait=False)

    def test_stop_skips_shutdown_when_not_running(self, mock_sched):
        mock_sched.running = False
        stop_scheduler()

        mock_sched.shutdown.assert_not_called()
