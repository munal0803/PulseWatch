"""
Global test setup.

sys.modules patching MUST happen before any app code is imported so that
firebase_admin and apscheduler module-level initialisation uses mocks.
"""

import sys
from unittest.mock import MagicMock

# ── Firebase ───────────────────────────────────────────────────────────────────
_mock_db = MagicMock()
_mock_firestore = MagicMock()
_mock_firestore.client.return_value = _mock_db

_mock_fa = MagicMock()
_mock_fa.credentials = MagicMock()
_mock_fa.firestore = _mock_firestore
_mock_fa.initialize_app = MagicMock()

sys.modules["firebase_admin"] = _mock_fa
sys.modules["firebase_admin.credentials"] = _mock_fa.credentials
sys.modules["firebase_admin.firestore"] = _mock_firestore

# ── APScheduler ────────────────────────────────────────────────────────────────
_mock_sched_instance = MagicMock()
_mock_apscheduler_bg = MagicMock()
_mock_apscheduler_bg.BackgroundScheduler = MagicMock(return_value=_mock_sched_instance)

sys.modules["apscheduler"] = MagicMock()
sys.modules["apscheduler.schedulers"] = MagicMock()
sys.modules["apscheduler.schedulers.background"] = _mock_apscheduler_bg

# ── App (safe to import now) ───────────────────────────────────────────────────
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset shared mocks between every test."""
    _mock_db.reset_mock()
    _mock_sched_instance.reset_mock()
    # scheduler.running must be False so start_scheduler() calls .start()
    _mock_sched_instance.running = False
    yield


@pytest.fixture
def mock_db():
    return _mock_db


@pytest.fixture
def mock_sched():
    return _mock_sched_instance


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
