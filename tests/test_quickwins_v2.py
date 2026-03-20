# FIRMA ELIAD - NON MODIFICABILE
"""Tests for quick-wins v2: CORS, Swagger docs, bulk triage, rate limiting."""

import unittest

import pandas as pd
from fastapi.testclient import TestClient

import app.dashboard as d
from app.dashboard import app


def _inject_fake_results():
    fake = pd.DataFrame({
        "user": ["alice", "bob", "carol", "dave", "eve"],
        "text": [
            "Urgent action required from IT",
            "This is a confidential request, trust me",
            "No rush, just checking in",
            "Your account suspended immediately!",
            "Dear friend, here is the file",
        ],
        "risk_score": [0.92, 0.75, 0.20, 0.88, 0.45],
        "risk_band": ["High", "High", "Low", "High", "Medium"],
        "top_risk_driver": [
            "urgency_score", "trust_score", "liking_score",
            "fear_score", "reciprocity_score",
        ],
        "urgency_score": [0.9, 0.3, 0.0, 0.8, 0.1],
        "trust_score": [0.2, 0.8, 0.1, 0.1, 0.3],
        "fear_score": [0.1, 0.0, 0.0, 0.9, 0.0],
    })
    d._results = fake
    d._featured_df = fake.copy()
    d._loaded_weights = dict(d.DEFAULT_WEIGHTS)
    d._results_version += 1
    d._results_cache.clear()
    d._triage_items.clear()
    d._triage_version = 0
    d._sync_triage_from_results(fake)


def _clear_state():
    d._results = pd.DataFrame()
    d._featured_df = pd.DataFrame()
    d._loaded_weights = {}
    d._results_cache.clear()
    d._results_cache_hits = 0
    d._results_cache_misses = 0
    d._triage_items.clear()
    d._triage_version = 0


# ── Swagger / OpenAPI ──────────────────────────────────────────────────────────

class TestSwaggerDocs(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_docs_endpoint_returns_html(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))

    def test_redoc_endpoint_returns_html(self):
        resp = self.client.get("/redoc")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))

    def test_openapi_json_has_tags(self):
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        paths = data.get("paths", {})
        # Verify /api/run has tags
        run_path = paths.get("/api/run", {})
        post_op = run_path.get("post", {})
        self.assertIn("Pipeline", post_op.get("tags", []))

    def test_openapi_description_present(self):
        resp = self.client.get("/openapi.json")
        data = resp.json()
        info = data.get("info", {})
        self.assertIn("social engineering", info.get("description", "").lower())


# ── CORS ───────────────────────────────────────────────────────────────────────

class TestCORSMiddleware(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_cors_preflight_returns_allow_origin(self):
        resp = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://external-app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")

    def test_cors_get_includes_allow_origin(self):
        resp = self.client.get(
            "/api/health",
            headers={"Origin": "http://external-app.example.com"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")


# ── Bulk Triage ────────────────────────────────────────────────────────────────

class TestBulkTriageEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def _get_all_triage_ids(self):
        resp = self.client.post("/api/triage/list", json={})
        return [item["id"] for item in resp.json()["items"]]

    def test_bulk_update_status(self):
        ids = self._get_all_triage_ids()
        self.assertGreaterEqual(len(ids), 2)
        target = ids[:2]
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": target,
            "status": "mitigated",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["updated"], 2)
        self.assertEqual(data["not_found"], [])

        # Verify items were actually updated
        resp2 = self.client.post("/api/triage/list", json={"statuses": ["mitigated"]})
        mitigated_ids = {item["id"] for item in resp2.json()["items"]}
        for tid in target:
            self.assertIn(tid, mitigated_ids)

    def test_bulk_update_assignee(self):
        ids = self._get_all_triage_ids()
        target = ids[:3]
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": target,
            "assignee": "analyst_team_A",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated"], 3)

    def test_bulk_update_with_note(self):
        ids = self._get_all_triage_ids()
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": [ids[0]],
            "status": "in_progress",
            "note": "Bulk investigation started",
        })
        self.assertEqual(resp.status_code, 200)

    def test_bulk_update_invalid_status_rejected(self):
        ids = self._get_all_triage_ids()
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": ids[:1],
            "status": "invalid_bulk_status",
        })
        self.assertEqual(resp.status_code, 400)

    def test_bulk_update_nonexistent_ids_reported(self):
        ids = self._get_all_triage_ids()
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": [ids[0], "nonexistent_xyz_123"],
            "status": "mitigated",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["updated"], 1)
        self.assertIn("nonexistent_xyz_123", data["not_found"])

    def test_bulk_update_empty_ids_rejected(self):
        resp = self.client.post("/api/triage/bulk-update", json={
            "item_ids": [],
            "status": "mitigated",
        })
        self.assertEqual(resp.status_code, 422)

    def test_bulk_update_records_activity(self):
        ids = self._get_all_triage_ids()
        self.client.post("/api/triage/bulk-update", json={
            "item_ids": [ids[0]],
            "status": "in_progress",
        })
        # Check via single item endpoint
        resp = self.client.post("/api/triage/list", json={})
        item = next(i for i in resp.json()["items"] if i["id"] == ids[0])
        actions = [a["action"] for a in item.get("activity", [])]
        self.assertIn("status", actions)


# ── Rate Limiter Config ───────────────────────────────────────────────────────

class TestRateLimiterConfig(unittest.TestCase):

    def test_limiter_attached_to_app(self):
        self.assertTrue(hasattr(app.state, "limiter"))

    def test_rate_limit_exceeded_handler_registered(self):
        handlers = app.exception_handlers
        from slowapi.errors import RateLimitExceeded
        self.assertIn(RateLimitExceeded, handlers)


if __name__ == "__main__":
    unittest.main()
