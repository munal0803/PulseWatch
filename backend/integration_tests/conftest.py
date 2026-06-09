"""
Integration test setup.

Requires the Firebase Firestore emulator to be running:
  firebase emulators:start --only firestore --project demo-uptime

All tests are automatically skipped if the emulator is not reachable.
No sys.modules patching here — real firebase-admin and real Firestore are used.
APScheduler is replaced with a MagicMock so background jobs don't fire during tests.
"""

import os
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8080")

import abc
import pytest
import requests
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import firestore as fs
from google.auth.credentials import AnonymousCredentials


# ── Custom credential that satisfies firebase-admin without real keys ──────────

class _EmulatorCredential(firebase_admin.credentials.Base):
    """Passes AnonymousCredentials to the underlying gRPC channel.
    The Firestore emulator ignores auth, so no real token is needed."""

    def get_credential(self):
        return AnonymousCredentials()


# ── Firebase init (once per process) ──────────────────────────────────────────

if not firebase_admin._apps:
    firebase_admin.initialize_app(
        credential=_EmulatorCredential(),
        options={"projectId": "demo-uptime"},
    )

_db = fs.client()


# ── Patch app modules to use emulator db BEFORE importing the FastAPI app ─────

import firebase_client
firebase_client.db = _db

import scheduler as sched_module
sched_module.db = _db
sched_module.scheduler = MagicMock()  # prevent real APScheduler from starting

import routers.monitors as monitors_module
monitors_module.db = _db

from fastapi.testclient import TestClient
from main import app


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clear_firestore():
    """Delete every monitor and its checks subcollection."""
    for m in _db.collection("monitors").stream():
        for c in m.reference.collection("checks").stream():
            c.reference.delete()
        m.reference.delete()


def _make_monitor(db, url="https://example.com", name="Test"):
    ref = db.collection("monitors").document()
    ref.set({
        "url": url,
        "name": name,
        "createdAt": datetime.now(timezone.utc),
        "lastStatus": None,
        "lastResponseTime": None,
        "lastCheckedAt": None,
    })
    return ref


# ── Session-scoped emulator guard ──────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def require_emulator():
    """Skip the entire session if the Firestore emulator is not running."""
    try:
        requests.get("http://localhost:8080", timeout=2)
    except Exception:
        pytest.skip(
            "Firestore emulator not running.\n"
            "Start it with:\n"
            "  firebase emulators:start --only firestore --project demo-uptime"
        )


# ── Per-test Firestore cleanup ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    _clear_firestore()
    yield
    _clear_firestore()


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    return _db


@pytest.fixture
def make_monitor(db):
    """Factory: create a monitor document directly in Firestore."""
    def _factory(url="https://example.com", name="Test"):
        return _make_monitor(db, url=url, name=name)
    return _factory


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
