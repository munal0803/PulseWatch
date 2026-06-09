"""
Integration tests for the monitors REST API.

Each test talks to the real FastAPI app with a real Firestore emulator — no mocks.
Assertions query Firestore directly to verify the database state, not just the
HTTP response.
"""

from datetime import datetime, timezone


# ── POST /api/monitors ─────────────────────────────────────────────────────────

class TestCreateMonitor:
    def test_creates_document_in_firestore(self, client, db):
        res = client.post("/api/monitors", json={"url": "https://example.com", "name": "Test"})

        assert res.status_code == 201
        doc_id = res.json()["id"]

        doc = db.collection("monitors").document(doc_id).get()
        assert doc.exists
        data = doc.to_dict()
        assert data["url"] == "https://example.com/"
        assert data["name"] == "Test"
        assert data["lastStatus"] is None

    def test_response_contains_id_and_fields(self, client):
        res = client.post("/api/monitors", json={"url": "https://example.com", "name": "Site"})

        assert res.status_code == 201
        body = res.json()
        assert "id" in body
        assert body["lastStatus"] is None
        assert body["lastResponseTime"] is None
        assert body["lastCheckedAt"] is None

    def test_name_optional_defaults_empty(self, client, db):
        res = client.post("/api/monitors", json={"url": "https://example.com"})

        assert res.status_code == 201
        data = db.collection("monitors").document(res.json()["id"]).get().to_dict()
        assert data["name"] == ""

    def test_invalid_url_not_saved(self, client, db):
        res = client.post("/api/monitors", json={"url": "not-a-url"})

        assert res.status_code == 422
        monitors = list(db.collection("monitors").stream())
        assert len(monitors) == 0

    def test_created_at_is_set(self, client, db):
        res = client.post("/api/monitors", json={"url": "https://example.com"})

        data = db.collection("monitors").document(res.json()["id"]).get().to_dict()
        assert data["createdAt"] is not None


# ── GET /api/monitors ──────────────────────────────────────────────────────────

class TestListMonitors:
    def test_empty_returns_empty_list(self, client):
        res = client.get("/api/monitors")

        assert res.status_code == 200
        assert res.json() == []

    def test_returns_created_monitor(self, client):
        client.post("/api/monitors", json={"url": "https://example.com", "name": "A"})

        res = client.get("/api/monitors")

        assert res.status_code == 200
        monitors = res.json()
        assert len(monitors) == 1
        assert monitors[0]["url"] == "https://example.com/"
        assert monitors[0]["name"] == "A"

    def test_returns_all_monitors(self, client):
        for i in range(3):
            client.post("/api/monitors", json={"url": f"https://site{i}.com"})

        res = client.get("/api/monitors")

        assert len(res.json()) == 3

    def test_each_monitor_has_id(self, client):
        client.post("/api/monitors", json={"url": "https://example.com"})

        monitors = client.get("/api/monitors").json()

        assert all("id" in m for m in monitors)

    def test_reflects_real_time_addition(self, client, db):
        # Add directly to Firestore, then verify API picks it up
        db.collection("monitors").document("direct-id").set({
            "url": "https://direct.com",
            "name": "Direct",
            "createdAt": datetime.now(timezone.utc),
            "lastStatus": "up",
            "lastResponseTime": 50,
            "lastCheckedAt": datetime.now(timezone.utc),
        })

        monitors = client.get("/api/monitors").json()

        ids = [m["id"] for m in monitors]
        assert "direct-id" in ids


# ── GET /api/monitors/{id}/checks ─────────────────────────────────────────────

class TestGetChecks:
    def test_new_monitor_has_no_checks(self, client):
        res = client.post("/api/monitors", json={"url": "https://example.com"})
        monitor_id = res.json()["id"]

        checks = client.get(f"/api/monitors/{monitor_id}/checks").json()

        assert checks == []

    def test_returns_checks_added_to_firestore(self, client, db, make_monitor):
        ref = make_monitor()
        now = datetime.now(timezone.utc)
        ref.collection("checks").add({
            "status": "up",
            "statusCode": 200,
            "responseTimeMs": 80,
            "checkedAt": now,
        })

        res = client.get(f"/api/monitors/{ref.id}/checks")

        assert res.status_code == 200
        checks = res.json()
        assert len(checks) == 1
        assert checks[0]["status"] == "up"
        assert checks[0]["statusCode"] == 200
        assert checks[0]["responseTimeMs"] == 80

    def test_returns_at_most_20_checks(self, client, db, make_monitor):
        ref = make_monitor()
        for i in range(25):
            ref.collection("checks").add({
                "status": "up",
                "statusCode": 200,
                "responseTimeMs": i,
                "checkedAt": datetime.now(timezone.utc),
            })

        checks = client.get(f"/api/monitors/{ref.id}/checks").json()

        assert len(checks) == 20

    def test_nonexistent_monitor_returns_404(self, client):
        res = client.get("/api/monitors/does-not-exist/checks")

        assert res.status_code == 404

    def test_checks_ordered_descending(self, client, db, make_monitor):
        from datetime import timedelta
        ref = make_monitor()
        base = datetime.now(timezone.utc)
        for i in range(3):
            ref.collection("checks").add({
                "status": "up",
                "statusCode": 200,
                "responseTimeMs": i * 10,
                "checkedAt": base + timedelta(seconds=i),
            })

        checks = client.get(f"/api/monitors/{ref.id}/checks").json()

        # Most recent first — largest responseTimeMs last was added last
        assert len(checks) == 3
        times = [c["checkedAt"] for c in checks]
        assert times == sorted(times, reverse=True)


# ── DELETE /api/monitors/{id} ──────────────────────────────────────────────────

class TestDeleteMonitor:
    def test_removes_monitor_from_firestore(self, client, db):
        res = client.post("/api/monitors", json={"url": "https://example.com"})
        monitor_id = res.json()["id"]

        client.delete(f"/api/monitors/{monitor_id}")

        assert not db.collection("monitors").document(monitor_id).get().exists

    def test_returns_204(self, client):
        res = client.post("/api/monitors", json={"url": "https://example.com"})
        monitor_id = res.json()["id"]

        delete_res = client.delete(f"/api/monitors/{monitor_id}")

        assert delete_res.status_code == 204

    def test_removes_associated_checks(self, client, db, make_monitor):
        ref = make_monitor()
        for _ in range(3):
            ref.collection("checks").add({
                "status": "up", "statusCode": 200,
                "responseTimeMs": 50, "checkedAt": datetime.now(timezone.utc),
            })

        client.delete(f"/api/monitors/{ref.id}")

        remaining = list(db.collection("monitors").document(ref.id).collection("checks").stream())
        assert len(remaining) == 0

    def test_monitor_gone_from_list_after_delete(self, client):
        res = client.post("/api/monitors", json={"url": "https://example.com"})
        monitor_id = res.json()["id"]

        client.delete(f"/api/monitors/{monitor_id}")

        monitors = client.get("/api/monitors").json()
        assert all(m["id"] != monitor_id for m in monitors)

    def test_nonexistent_monitor_returns_404(self, client):
        res = client.delete("/api/monitors/ghost-id")

        assert res.status_code == 404

    def test_delete_does_not_affect_other_monitors(self, client):
        id_a = client.post("/api/monitors", json={"url": "https://a.com"}).json()["id"]
        id_b = client.post("/api/monitors", json={"url": "https://b.com"}).json()["id"]

        client.delete(f"/api/monitors/{id_a}")

        monitors = client.get("/api/monitors").json()
        ids = [m["id"] for m in monitors]
        assert id_a not in ids
        assert id_b in ids


# ── End-to-end flows ───────────────────────────────────────────────────────────

class TestEndToEndFlows:
    def test_create_list_delete_cycle(self, client):
        # Create
        res = client.post("/api/monitors", json={"url": "https://example.com", "name": "Flow"})
        assert res.status_code == 201
        monitor_id = res.json()["id"]

        # Verify in list
        monitors = client.get("/api/monitors").json()
        assert any(m["id"] == monitor_id for m in monitors)

        # Delete
        assert client.delete(f"/api/monitors/{monitor_id}").status_code == 204

        # Verify gone
        monitors = client.get("/api/monitors").json()
        assert all(m["id"] != monitor_id for m in monitors)

    def test_checks_visible_via_api_after_firestore_write(self, client, db, make_monitor):
        ref = make_monitor(url="https://example.com", name="Checked")
        ref.collection("checks").add({
            "status": "down", "statusCode": None,
            "responseTimeMs": None, "checkedAt": datetime.now(timezone.utc),
        })

        checks = client.get(f"/api/monitors/{ref.id}/checks").json()

        assert len(checks) == 1
        assert checks[0]["status"] == "down"
        assert checks[0]["statusCode"] is None
