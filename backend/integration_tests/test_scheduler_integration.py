"""
Integration tests for the scheduler's ping logic against the Firestore emulator.

HTTP calls are still mocked (we test Firestore writes, not network connectivity).
Scheduler background jobs are not started — ping_all_monitors() is called manually.
"""

from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from scheduler import ping_all_monitors


# ── Helpers ────────────────────────────────────────────────────────────────────

def _http_mock(status_code=200, error=None):
    """Context manager that patches httpx so ping_url doesn't make real requests."""
    mock_response = MagicMock()
    mock_response.status_code = status_code

    mock_client = AsyncMock()
    if error:
        mock_client.get = AsyncMock(side_effect=error)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)

    patcher = patch("scheduler.httpx.AsyncClient")

    class _Ctx:
        def __enter__(self):
            cls = patcher.start()
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            return cls

        def __exit__(self, *args):
            patcher.stop()

    return _Ctx()


# ── ping_all_monitors → Firestore writes ───────────────────────────────────────

class TestPingWritesToFirestore:
    def test_creates_check_document(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()

        checks = list(ref.collection("checks").stream())
        assert len(checks) == 1

    def test_up_check_has_correct_fields(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()

        check = list(ref.collection("checks").stream())[0].to_dict()
        assert check["status"] == "up"
        assert check["statusCode"] == 200
        assert isinstance(check["responseTimeMs"], int)
        assert check["responseTimeMs"] >= 0
        assert check["checkedAt"] is not None

    def test_down_check_on_connection_error(self, db, make_monitor):
        import httpx
        ref = make_monitor()

        with _http_mock(error=httpx.ConnectError("refused")):
            ping_all_monitors()

        check = list(ref.collection("checks").stream())[0].to_dict()
        assert check["status"] == "down"
        assert check["statusCode"] is None
        assert check["responseTimeMs"] is None
        assert check["checkedAt"] is not None

    def test_down_check_on_timeout(self, db, make_monitor):
        import httpx
        ref = make_monitor()

        with _http_mock(error=httpx.TimeoutException("timeout")):
            ping_all_monitors()

        check = list(ref.collection("checks").stream())[0].to_dict()
        assert check["status"] == "down"

    def test_non_200_still_writes_up(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=500):
            ping_all_monitors()

        check = list(ref.collection("checks").stream())[0].to_dict()
        assert check["status"] == "up"
        assert check["statusCode"] == 500


# ── Monitor document is updated after ping ─────────────────────────────────────

class TestMonitorDocumentUpdate:
    def test_last_status_updated_to_up(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()

        updated = ref.get().to_dict()
        assert updated["lastStatus"] == "up"

    def test_last_status_updated_to_down(self, db, make_monitor):
        import httpx
        ref = make_monitor()

        with _http_mock(error=httpx.ConnectError("refused")):
            ping_all_monitors()

        updated = ref.get().to_dict()
        assert updated["lastStatus"] == "down"

    def test_last_response_time_set_on_up(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()

        updated = ref.get().to_dict()
        assert updated["lastResponseTime"] is not None
        assert updated["lastResponseTime"] >= 0

    def test_last_response_time_null_on_down(self, db, make_monitor):
        import httpx
        ref = make_monitor()

        with _http_mock(error=httpx.ConnectError("refused")):
            ping_all_monitors()

        updated = ref.get().to_dict()
        assert updated["lastResponseTime"] is None

    def test_last_checked_at_updated(self, db, make_monitor):
        ref = make_monitor()
        assert ref.get().to_dict()["lastCheckedAt"] is None

        with _http_mock(status_code=200):
            ping_all_monitors()

        updated = ref.get().to_dict()
        assert updated["lastCheckedAt"] is not None


# ── Multiple monitors ──────────────────────────────────────────────────────────

class TestMultipleMonitors:
    def test_all_monitors_get_a_check(self, db, make_monitor):
        refs = [make_monitor(url=f"https://site{i}.com") for i in range(3)]

        with _http_mock(status_code=200):
            ping_all_monitors()

        for ref in refs:
            checks = list(ref.collection("checks").stream())
            assert len(checks) == 1, f"Expected 1 check for {ref.id}"

    def test_all_monitors_updated(self, db, make_monitor):
        refs = [make_monitor(url=f"https://site{i}.com") for i in range(3)]

        with _http_mock(status_code=200):
            ping_all_monitors()

        for ref in refs:
            assert ref.get().to_dict()["lastStatus"] == "up"

    def test_mixed_up_and_down(self, db, make_monitor):
        import httpx
        good = make_monitor(url="https://good.com")
        bad = make_monitor(url="https://bad.com")

        call_count = 0

        async def _smart_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "bad" in url:
                raise httpx.ConnectError("refused")
            resp = MagicMock()
            resp.status_code = 200
            return resp

        mock_client = AsyncMock()
        mock_client.get = _smart_get

        with patch("scheduler.httpx.AsyncClient") as cls:
            cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            cls.return_value.__aexit__ = AsyncMock(return_value=False)
            ping_all_monitors()

        assert good.get().to_dict()["lastStatus"] == "up"
        assert bad.get().to_dict()["lastStatus"] == "down"


# ── Edge cases ─────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_no_monitors_does_nothing(self, db):
        with _http_mock(status_code=200):
            ping_all_monitors()  # should not raise

        assert list(db.collection("monitors").stream()) == []

    def test_second_ping_adds_second_check(self, db, make_monitor):
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()
            ping_all_monitors()

        checks = list(ref.collection("checks").stream())
        assert len(checks) == 2

    def test_status_flips_from_up_to_down(self, db, make_monitor):
        import httpx
        ref = make_monitor()

        with _http_mock(status_code=200):
            ping_all_monitors()
        assert ref.get().to_dict()["lastStatus"] == "up"

        with _http_mock(error=httpx.ConnectError("refused")):
            ping_all_monitors()
        assert ref.get().to_dict()["lastStatus"] == "down"
