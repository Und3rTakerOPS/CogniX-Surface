# FIRMA ELIAD - NON MODIFICABILE
"""Tests for triage, alerting/webhook, and weights API endpoints."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pandas as pd
from fastapi.testclient import TestClient

import app.dashboard as d
from app.dashboard import app


def _inject_fake_results():
    """Inject minimal fake results + triage items so endpoints can be tested
    without running the full NLP pipeline."""
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
    """Reset global state to empty."""
    d._results = pd.DataFrame()
    d._featured_df = pd.DataFrame()
    d._loaded_weights = {}
    d._results_cache.clear()
    d._results_cache_hits = 0
    d._results_cache_misses = 0
    d._triage_items.clear()
    d._triage_version = 0


# ── Triage API Tests ──────────────────────────────────────────────────────────

class TestTriageListEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_triage_list_returns_items(self):
        resp = self.client.post("/api/triage/list", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("summary", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreater(len(data["items"]), 0)

    def test_triage_list_filter_by_status(self):
        resp = self.client.post("/api/triage/list", json={"statuses": ["new"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["items"]:
            self.assertEqual(item["status"], "new")

    def test_triage_list_invalid_status_rejected(self):
        resp = self.client.post("/api/triage/list", json={"statuses": ["bogus"]})
        self.assertEqual(resp.status_code, 400)

    def test_triage_list_invalid_priority_rejected(self):
        resp = self.client.post("/api/triage/list", json={"priorities": ["P99"]})
        self.assertEqual(resp.status_code, 400)

    def test_triage_list_filter_by_priority(self):
        resp = self.client.post("/api/triage/list", json={"priorities": ["P1"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["items"]:
            self.assertEqual(item["priority"], "P1")

    def test_triage_list_text_search(self):
        resp = self.client.post("/api/triage/list", json={"text_query": "alice"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["items"]:
            self.assertTrue(
                "alice" in item.get("user", "").lower()
                or "alice" in item.get("text", "").lower()
            )

    def test_triage_summary_counts(self):
        resp = self.client.post("/api/triage/list", json={})
        data = resp.json()
        summary = data["summary"]
        self.assertIn("total", summary)
        self.assertIn("open", summary)
        self.assertIn("status_counts", summary)
        self.assertIn("priority_counts", summary)
        self.assertGreaterEqual(summary["total"], 0)


class TestTriageUpdateEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def _get_first_triage_id(self) -> str:
        resp = self.client.post("/api/triage/list", json={})
        items = resp.json()["items"]
        self.assertGreater(len(items), 0, "No triage items to test")
        return items[0]["id"]

    def test_update_status(self):
        item_id = self._get_first_triage_id()
        resp = self.client.patch(f"/api/triage/item/{item_id}", json={"status": "in_progress"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["item"]["status"], "in_progress")

    def test_update_assignee(self):
        item_id = self._get_first_triage_id()
        resp = self.client.patch(f"/api/triage/item/{item_id}", json={"assignee": "analyst1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["item"]["assignee"], "analyst1")

    def test_add_note(self):
        item_id = self._get_first_triage_id()
        resp = self.client.patch(f"/api/triage/item/{item_id}", json={"note": "Investigating phishing indicators"})
        self.assertEqual(resp.status_code, 200)
        notes = resp.json()["item"]["notes"]
        self.assertTrue(any("Investigating" in n["text"] for n in notes))

    def test_update_invalid_status_rejected(self):
        item_id = self._get_first_triage_id()
        resp = self.client.patch(f"/api/triage/item/{item_id}", json={"status": "invalid_status"})
        self.assertEqual(resp.status_code, 400)

    def test_update_nonexistent_item_returns_404(self):
        resp = self.client.patch("/api/triage/item/nonexistent_id_xyz", json={"status": "mitigated"})
        self.assertEqual(resp.status_code, 404)

    def test_update_records_activity(self):
        item_id = self._get_first_triage_id()
        self.client.patch(f"/api/triage/item/{item_id}", json={"status": "mitigated"})
        resp = self.client.patch(f"/api/triage/item/{item_id}", json={"note": "Closed after review"})
        activity = resp.json()["item"]["activity"]
        actions = [a["action"] for a in activity]
        self.assertIn("status", actions)
        self.assertIn("note", actions)


class TestTriageBootstrapEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_bootstrap_creates_items(self):
        d._triage_items.clear()
        resp = self.client.post("/api/triage/bootstrap", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["triage_candidates"], 0)
        self.assertGreater(data["triage_total"], 0)

    def test_bootstrap_before_run_returns_404(self):
        _clear_state()
        resp = self.client.post("/api/triage/bootstrap", json={})
        self.assertEqual(resp.status_code, 404)


# ── Weights API Tests ─────────────────────────────────────────────────────────

class TestWeightsGetEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_get_weights_returns_dict(self):
        resp = self.client.get("/api/weights")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("weights", data)
        self.assertIsInstance(data["weights"], dict)
        self.assertIn("is_custom", data)

    def test_get_weights_contains_known_keys(self):
        resp = self.client.get("/api/weights")
        weights = resp.json()["weights"]
        for key in ("urgency_score", "authority_score", "fear_score"):
            self.assertIn(key, weights)


class TestWeightsUpdateEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_update_weights_rescores(self):
        new_weights = dict(d.DEFAULT_WEIGHTS)
        new_weights["urgency_score"] = 0.50
        resp = self.client.post("/api/weights", json={"weights": new_weights})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["rescored"])
        self.assertAlmostEqual(data["weights"]["urgency_score"], 0.50)

    def test_update_weights_empty_rejected(self):
        resp = self.client.post("/api/weights", json={"weights": {}})
        self.assertEqual(resp.status_code, 400)

    def test_update_weights_unknown_key_rejected(self):
        resp = self.client.post("/api/weights", json={"weights": {"unknown_key": 0.5}})
        self.assertEqual(resp.status_code, 400)

    def test_update_weights_negative_value_rejected(self):
        bad = dict(d.DEFAULT_WEIGHTS)
        bad["urgency_score"] = -0.1
        resp = self.client.post("/api/weights", json={"weights": bad})
        self.assertEqual(resp.status_code, 400)

    def test_update_weights_zero_sum_rejected(self):
        zeros = {k: 0.0 for k in d.DEFAULT_WEIGHTS}
        resp = self.client.post("/api/weights", json={"weights": zeros})
        self.assertEqual(resp.status_code, 400)

    def test_update_weights_invalidates_cache(self):
        # Prime the cache
        self.client.post("/api/results", json={})
        self.assertGreater(len(d._results_cache), 0)
        # Update weights
        new_weights = dict(d.DEFAULT_WEIGHTS)
        new_weights["fear_score"] = 0.30
        self.client.post("/api/weights", json={"weights": new_weights})
        self.assertEqual(len(d._results_cache), 0)


# ── Alert/Webhook API Tests ──────────────────────────────────────────────────

class TestAlertWebhookEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_webhook_invalid_url_rejected(self):
        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "ftp://bad-protocol.com/hook",
            "event": "test",
        })
        self.assertEqual(resp.status_code, 400)

    def test_webhook_missing_url_rejected(self):
        resp = self.client.post("/api/alerts/webhook", json={
            "event": "test",
        })
        self.assertEqual(resp.status_code, 422)

    @patch("app.dashboard.urllib.request.urlopen")
    def test_webhook_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"ok":true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "https://example.com/hook",
            "event": "high_risk_alert",
            "payload": {"msg": "test"},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["target_status"], 200)

    @patch("app.dashboard.urllib.request.urlopen")
    def test_webhook_target_error_returns_502(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/hook",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        resp = self.client.post("/api/alerts/webhook", json={
            "webhook_url": "https://example.com/hook",
            "event": "test",
        })
        self.assertEqual(resp.status_code, 502)

    @patch("app.dashboard.urllib.request.urlopen")
    def test_webhook_hmac_header_sent_when_secret_set(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"ok":true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        original_secret = d.WEBHOOK_HMAC_SECRET
        try:
            d.WEBHOOK_HMAC_SECRET = "test-secret-key-123"
            self.client.post("/api/alerts/webhook", json={
                "webhook_url": "https://example.com/hook",
                "event": "test",
            })
            # Inspect the Request object passed to urlopen
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            sig_header = request_obj.get_header("X-cognix-signature")
            self.assertIsNotNone(sig_header, "HMAC signature header missing")
            self.assertTrue(sig_header.startswith("sha256="))
        finally:
            d.WEBHOOK_HMAC_SECRET = original_secret

    @patch("app.dashboard.urllib.request.urlopen")
    def test_webhook_no_hmac_when_secret_empty(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"ok":true}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        original_secret = d.WEBHOOK_HMAC_SECRET
        try:
            d.WEBHOOK_HMAC_SECRET = ""
            self.client.post("/api/alerts/webhook", json={
                "webhook_url": "https://example.com/hook",
                "event": "test",
            })
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            sig_header = request_obj.get_header("X-cognix-signature")
            self.assertIsNone(sig_header, "HMAC header should not be present when secret is empty")
        finally:
            d.WEBHOOK_HMAC_SECRET = original_secret


# ── LRU Cache Eviction Tests ─────────────────────────────────────────────────

class TestLRUCacheEviction(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _inject_fake_results()

    def tearDown(self):
        _clear_state()

    def test_cache_hit_moves_to_end(self):
        # Generate two cache entries
        self.client.post("/api/results", json={"min_risk": 0.0})
        self.client.post("/api/results", json={"min_risk": 0.5})
        keys = list(d._results_cache.keys())
        self.assertGreaterEqual(len(keys), 2)

        # Hit the first one again -> it should move to end
        first_key = keys[0]
        self.client.post("/api/results", json={"min_risk": 0.0})
        new_keys = list(d._results_cache.keys())
        self.assertEqual(new_keys[-1], first_key)

    def test_cache_respects_max_size(self):
        original_max = d.RESULTS_CACHE_MAX_SIZE
        try:
            d.RESULTS_CACHE_MAX_SIZE = 3
            d._results_cache.clear()
            for i in range(5):
                self.client.post("/api/results", json={"min_risk": round(i * 0.1, 2)})
            self.assertLessEqual(len(d._results_cache), 3)
        finally:
            d.RESULTS_CACHE_MAX_SIZE = original_max


if __name__ == "__main__":
    unittest.main()
