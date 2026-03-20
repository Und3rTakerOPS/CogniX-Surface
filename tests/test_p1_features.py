# FIRMA ELIAD - NON MODIFICABILE
"""Tests for P1 features: pagination, webhook retry, filter presets, KPI timeline."""

import unittest
import time
from unittest.mock import patch, MagicMock

import pandas as pd
from fastapi.testclient import TestClient

import app.dashboard as d
from app.dashboard import app


def _inject_fake_results(n=5):
    """Inject fake analysis results into dashboard state."""
    users = ["alice", "bob", "carol", "dave", "eve"]
    texts = [
        "Urgent action required from IT",
        "This is a confidential request, trust me",
        "No rush, just checking in",
        "Your account suspended immediately!",
        "Dear friend, here is the file",
    ]
    # Extend for larger datasets
    fake = pd.DataFrame({
        "user": [users[i % len(users)] for i in range(n)],
        "text": [texts[i % len(texts)] for i in range(n)],
        "risk_score": [(0.1 + 0.8 * (i / max(n - 1, 1))) for i in range(n)],
        "risk_band": [
            "High" if (0.1 + 0.8 * (i / max(n - 1, 1))) >= 0.7
            else "Medium" if (0.1 + 0.8 * (i / max(n - 1, 1))) >= 0.4
            else "Low"
            for i in range(n)
        ],
        "top_risk_driver": ["urgency_score"] * n,
        "urgency_score": [0.5] * n,
        "trust_score": [0.3] * n,
        "fear_score": [0.1] * n,
    })
    d._results = fake
    d._featured_df = fake.copy()
    d._loaded_weights = dict(d.DEFAULT_WEIGHTS)
    d._results_version += 1
    d._results_cache.clear()


def _clear_state():
    d._results = pd.DataFrame()
    d._featured_df = pd.DataFrame()
    d._loaded_weights = {}
    d._results_cache.clear()
    d._results_cache_hits = 0
    d._results_cache_misses = 0
    d._triage_items.clear()
    d._triage_version = 0
    d._filter_presets.clear()
    d._kpi_timeline.clear()


# ── Pagination ─────────────────────────────────────────────────────────────────

class TestPagination(unittest.TestCase):

    def setUp(self):
        _clear_state()
        _inject_fake_results(50)
        self.client = TestClient(app)

    def tearDown(self):
        _clear_state()

    def test_default_pagination_returns_all(self):
        """Default offset=0, limit=100 returns all 50 rows."""
        resp = self.client.post("/api/results", json={"top_n": 50})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pagination", data)
        p = data["pagination"]
        self.assertEqual(p["offset"], 0)
        self.assertEqual(p["returned"], 50)
        self.assertFalse(p["has_more"])

    def test_pagination_limit(self):
        """Limit=10 returns only 10 messages."""
        resp = self.client.post("/api/results", json={"top_n": 50, "limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        p = data["pagination"]
        self.assertEqual(p["returned"], 10)
        self.assertEqual(p["total_filtered"], 50)
        self.assertTrue(p["has_more"])

    def test_pagination_offset(self):
        """Offset=40 with 50 results returns last 10."""
        resp = self.client.post("/api/results", json={"top_n": 50, "offset": 40, "limit": 100})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        p = data["pagination"]
        self.assertEqual(p["returned"], 10)
        self.assertEqual(p["offset"], 40)
        self.assertFalse(p["has_more"])

    def test_pagination_offset_beyond_results(self):
        """Offset beyond results returns 0 messages."""
        resp = self.client.post("/api/results", json={"top_n": 50, "offset": 100, "limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        p = data["pagination"]
        self.assertEqual(p["returned"], 0)
        self.assertTrue(p["offset"] >= p["total_filtered"])

    def test_pagination_metadata_in_response(self):
        """Pagination metadata is always present."""
        resp = self.client.post("/api/results", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pagination", data)
        for key in ("offset", "limit", "total_filtered", "returned", "has_more"):
            self.assertIn(key, data["pagination"])


# ── Webhook Retry ──────────────────────────────────────────────────────────────

class TestWebhookRetry(unittest.TestCase):

    def setUp(self):
        _clear_state()
        _inject_fake_results()
        self.client = TestClient(app)

    def tearDown(self):
        _clear_state()

    @patch("app.dashboard.time.sleep")
    @patch("app.dashboard.urllib.request.urlopen")
    def test_retry_on_server_error(self, mock_urlopen, mock_sleep):
        """Retries on 500 errors, then succeeds on 3rd attempt."""
        error_resp = MagicMock()
        error_resp.code = 500
        error_resp.fp = True
        error_resp.read.return_value = b"server error"

        success_resp = MagicMock()
        success_resp.__enter__ = MagicMock(return_value=success_resp)
        success_resp.__exit__ = MagicMock(return_value=False)
        success_resp.getcode.return_value = 200
        success_resp.read.return_value = b'{"ok":true}'

        from urllib.error import HTTPError
        mock_urlopen.side_effect = [
            HTTPError("http://test.local/hook", 500, "Internal Server Error", {}, MagicMock(read=lambda x: b"err")),
            HTTPError("http://test.local/hook", 500, "Internal Server Error", {}, MagicMock(read=lambda x: b"err")),
            success_resp,
        ]

        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "http://test.local/hook",
            "event": "test_retry",
            "payload": {"msg": "test"},
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("app.dashboard.time.sleep")
    @patch("app.dashboard.urllib.request.urlopen")
    def test_no_retry_on_4xx(self, mock_urlopen, mock_sleep):
        """4xx errors should not be retried."""
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://test.local/hook", 400, "Bad Request", {},
            MagicMock(read=lambda x: b"bad request")
        )

        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "http://test.local/hook",
            "event": "test_no_retry",
            "payload": {},
        })
        self.assertEqual(resp.status_code, 502)
        mock_sleep.assert_not_called()

    @patch("app.dashboard.time.sleep")
    @patch("app.dashboard.urllib.request.urlopen")
    def test_all_retries_exhausted(self, mock_urlopen, mock_sleep):
        """After 3 failed attempts, returns 502."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "http://test.local/hook",
            "event": "test_exhaust",
            "payload": {},
        })
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(mock_sleep.call_count, 2)  # sleeps between retries


# ── Filter Presets Server-Side ─────────────────────────────────────────────────

class TestFilterPresets(unittest.TestCase):

    def setUp(self):
        _clear_state()
        self.client = TestClient(app)

    def tearDown(self):
        _clear_state()

    def test_list_presets_empty(self):
        resp = self.client.get("/api/filter-presets")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["presets"], [])

    def test_create_preset(self):
        resp = self.client.post("/api/filter-presets", json={
            "name": "High Risk Only",
            "min_risk": 0.7,
            "max_risk": 1.0,
            "bands": ["High"],
        })
        self.assertEqual(resp.status_code, 200)
        preset = resp.json()["preset"]
        self.assertEqual(preset["name"], "High Risk Only")
        self.assertEqual(preset["min_risk"], 0.7)
        self.assertIn("created_at", preset)

    def test_list_after_create(self):
        self.client.post("/api/filter-presets", json={"name": "P1"})
        self.client.post("/api/filter-presets", json={"name": "P2"})
        resp = self.client.get("/api/filter-presets")
        names = [p["name"] for p in resp.json()["presets"]]
        self.assertIn("P1", names)
        self.assertIn("P2", names)

    def test_delete_preset(self):
        self.client.post("/api/filter-presets", json={"name": "ToDelete"})
        resp = self.client.delete("/api/filter-presets/ToDelete")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], "ToDelete")
        # Verify gone
        resp2 = self.client.get("/api/filter-presets")
        names = [p["name"] for p in resp2.json()["presets"]]
        self.assertNotIn("ToDelete", names)

    def test_delete_nonexistent_preset(self):
        resp = self.client.delete("/api/filter-presets/NoSuchPreset")
        self.assertEqual(resp.status_code, 404)

    def test_create_empty_name_rejected(self):
        resp = self.client.post("/api/filter-presets", json={"name": ""})
        self.assertEqual(resp.status_code, 422)

    def test_overwrite_same_name(self):
        """Creating a preset with same name overwrites it."""
        self.client.post("/api/filter-presets", json={"name": "Dup", "min_risk": 0.1})
        self.client.post("/api/filter-presets", json={"name": "Dup", "min_risk": 0.9})
        resp = self.client.get("/api/filter-presets")
        presets = resp.json()["presets"]
        dup = [p for p in presets if p["name"] == "Dup"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0]["min_risk"], 0.9)


# ── KPI Timeline ──────────────────────────────────────────────────────────────

class TestKpiTimeline(unittest.TestCase):

    def setUp(self):
        _clear_state()
        self.client = TestClient(app)

    def tearDown(self):
        _clear_state()

    def test_empty_timeline(self):
        resp = self.client.get("/api/kpi-timeline")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["snapshots"], [])
        self.assertEqual(data["count"], 0)

    def test_snapshot_after_manual_save(self):
        """Manually saving a snapshot populates the timeline."""
        _inject_fake_results(10)
        d._save_kpi_snapshot(d._results, 150)
        resp = self.client.get("/api/kpi-timeline")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        snap = data["snapshots"][0]
        self.assertEqual(snap["messages"], 10)
        self.assertIn("avg_risk", snap)
        self.assertIn("timestamp", snap)
        self.assertEqual(snap["duration_ms"], 150)

    def test_multiple_snapshots(self):
        """Multiple snapshots are accumulated."""
        for i in range(5):
            _inject_fake_results(10 + i)
            d._save_kpi_snapshot(d._results, 100 + i * 10)
        resp = self.client.get("/api/kpi-timeline")
        data = resp.json()
        self.assertEqual(data["count"], 5)
        # Verify ordered (first has fewer messages)
        msgs = [s["messages"] for s in data["snapshots"]]
        self.assertEqual(msgs, [10, 11, 12, 13, 14])

    def test_timeline_max_limit(self):
        """Timeline respects the max snapshot limit."""
        old_max = d.KPI_TIMELINE_MAX_SNAPSHOTS
        d.KPI_TIMELINE_MAX_SNAPSHOTS = 3
        try:
            for i in range(5):
                _inject_fake_results(10)
                d._save_kpi_snapshot(d._results, 100)
            resp = self.client.get("/api/kpi-timeline")
            data = resp.json()
            self.assertEqual(data["count"], 3)
        finally:
            d.KPI_TIMELINE_MAX_SNAPSHOTS = old_max

    def test_snapshot_fields(self):
        """Snapshot contains all expected KPI fields."""
        _inject_fake_results(20)
        d._save_kpi_snapshot(d._results, 200)
        resp = self.client.get("/api/kpi-timeline")
        snap = resp.json()["snapshots"][0]
        expected_keys = {
            "timestamp", "run_version", "duration_ms", "messages", "users",
            "avg_risk", "max_risk", "median_risk", "high", "medium", "low", "high_pct"
        }
        self.assertTrue(expected_keys.issubset(set(snap.keys())))


if __name__ == "__main__":
    unittest.main()
