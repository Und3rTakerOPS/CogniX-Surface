# FIRMA ELIAD - NON MODIFICABILE
"""Tests for hardening features: SQLite persistence, API Key auth, input sanitization, Docker config."""

import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestSQLitePersistence(unittest.TestCase):
    """Verify that the database module correctly round-trips data."""

    def setUp(self):
        import app.database as db
        self._original_db_path = db._db_path
        self._original_local = db._local
        db._local = __import__('threading').local()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def tearDown(self):
        import app.database as db
        db._db_path = self._original_db_path
        db._local = self._original_local
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_triage_item_roundtrip(self):
        from app.database import init_db, save_triage_item, load_triage_items
        init_db(self.db_path)
        save_triage_item("item-1", {"status": "new", "user": "alice"})
        items = load_triage_items()
        self.assertIn("item-1", items)
        self.assertEqual(items["item-1"]["status"], "new")

    def test_triage_bulk_save_and_load(self):
        from app.database import init_db, save_triage_items_bulk, load_triage_items
        init_db(self.db_path)
        bulk = {
            "a": {"status": "new", "score": 0.9},
            "b": {"status": "in_progress", "score": 0.5},
        }
        save_triage_items_bulk(bulk)
        loaded = load_triage_items()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded["b"]["status"], "in_progress")

    def test_triage_delete(self):
        from app.database import init_db, save_triage_item, delete_triage_item, load_triage_items
        init_db(self.db_path)
        save_triage_item("del-me", {"status": "new"})
        delete_triage_item("del-me")
        self.assertNotIn("del-me", load_triage_items())

    def test_filter_preset_roundtrip(self):
        from app.database import init_db, save_filter_preset, load_filter_presets
        init_db(self.db_path)
        preset = {"name": "test", "min_risk": 0.5, "max_risk": 1.0}
        save_filter_preset("test", preset)
        presets = load_filter_presets()
        self.assertIn("test", presets)
        self.assertAlmostEqual(presets["test"]["min_risk"], 0.5)

    def test_filter_preset_delete(self):
        from app.database import init_db, save_filter_preset, delete_filter_preset, load_filter_presets
        init_db(self.db_path)
        save_filter_preset("gone", {"name": "gone"})
        ok = delete_filter_preset("gone")
        self.assertTrue(ok)
        self.assertNotIn("gone", load_filter_presets())

    def test_kpi_snapshot_roundtrip(self):
        from app.database import init_db, save_kpi_snapshot, load_kpi_timeline
        init_db(self.db_path)
        snap = {"timestamp": "2025-01-01T00:00:00Z", "avg_risk": 0.42}
        save_kpi_snapshot(snap)
        timeline = load_kpi_timeline(10)
        self.assertEqual(len(timeline), 1)
        self.assertAlmostEqual(timeline[0]["avg_risk"], 0.42)

    def test_kpi_trim(self):
        from app.database import init_db, save_kpi_snapshot, load_kpi_timeline, trim_kpi_timeline
        init_db(self.db_path)
        for i in range(5):
            save_kpi_snapshot({"i": i})
        trim_kpi_timeline(3)
        self.assertEqual(len(load_kpi_timeline(10)), 3)

    def test_audit_entry(self):
        from app.database import init_db, save_audit_entry, load_audit_log
        init_db(self.db_path)
        save_audit_entry("test_action", "some details")
        log = load_audit_log(10)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "test_action")


class TestAPIKeyAuth(unittest.TestCase):
    """Verify API key enforcement on protected endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_protected_endpoint_rejects_without_key(self):
        """When COGNIX_API_KEY is set, requests without key get 401."""
        import app.dashboard as d
        original = d.COGNIX_API_KEY
        d.COGNIX_API_KEY = "test-secret-key-12345"
        try:
            resp = self.client.post("/api/weights", json={"weights": {}})
            self.assertEqual(resp.status_code, 401)
        finally:
            d.COGNIX_API_KEY = original

    def test_protected_endpoint_accepts_valid_key(self):
        """When COGNIX_API_KEY is set, requests with correct key pass auth."""
        import app.dashboard as d
        original_key = d.COGNIX_API_KEY
        original_results = d._results
        d.COGNIX_API_KEY = "test-secret-key-12345"
        try:
            # weights endpoint needs results to be non-empty for a 200,
            # but auth check happens before, so 400 (bad weights) means auth passed
            resp = self.client.post(
                "/api/weights",
                json={"weights": {}},
                headers={"X-API-Key": "test-secret-key-12345"},
            )
            # Auth passed — we should not get 401
            self.assertNotEqual(resp.status_code, 401)
        finally:
            d.COGNIX_API_KEY = original_key
            d._results = original_results

    def test_protected_endpoint_rejects_bad_key(self):
        import app.dashboard as d
        original = d.COGNIX_API_KEY
        d.COGNIX_API_KEY = "test-secret-key-12345"
        try:
            resp = self.client.post(
                "/api/weights",
                json={"weights": {}},
                headers={"X-API-Key": "wrong-key"},
            )
            self.assertEqual(resp.status_code, 401)
        finally:
            d.COGNIX_API_KEY = original

    def test_no_key_configured_allows_all(self):
        """When COGNIX_API_KEY is empty (dev mode), no auth required."""
        import app.dashboard as d
        from unittest.mock import patch
        original = d.COGNIX_API_KEY
        original_presets = d._filter_presets.copy()
        d.COGNIX_API_KEY = ""
        try:
            with patch("app.dashboard._db_save_preset"):
                resp = self.client.post("/api/filter-presets", json={
                    "name": "auth-test-preset",
                    "min_risk": 0.5,
                })
            self.assertNotEqual(resp.status_code, 401)
        finally:
            d.COGNIX_API_KEY = original
            d._filter_presets = original_presets


class TestInputSanitization(unittest.TestCase):
    """Verify XSS sanitization of user-supplied text fields."""

    def test_sanitize_helper_escapes_html(self):
        from app.dashboard import _sanitize
        dangerous = '<script>alert("xss")</script>'
        safe = _sanitize(dangerous)
        self.assertNotIn("<script>", safe)
        self.assertIn("&lt;script&gt;", safe)

    def test_sanitize_preserves_normal_text(self):
        from app.dashboard import _sanitize
        normal = "Hello, this is a normal note."
        self.assertEqual(_sanitize(normal), normal)

    def test_triage_note_is_sanitized(self):
        """Notes injected via triage update should be HTML-escaped."""
        import app.dashboard as d
        from unittest.mock import patch
        original_items = d._triage_items
        original_key = d.COGNIX_API_KEY
        d.COGNIX_API_KEY = ""
        d._triage_items = {
            "test-xss": {
                "id": "test-xss",
                "user": "attacker",
                "text": "test message",
                "risk_score": 0.95,
                "risk_band": "High",
                "top_driver": "Urgency",
                "status": "new",
                "assignee": "",
                "notes": [],
                "activity": [],
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
                "present_in_latest_run": True,
            }
        }
        try:
            client = TestClient(app)
            with patch("app.dashboard._db_save_triage_item"):
                resp = client.patch("/api/triage/item/test-xss", json={
                    "note": '<img src=x onerror=alert(1)>',
                })
            self.assertEqual(resp.status_code, 200)
            item = resp.json()["item"]
            last_note = item["notes"][-1]["text"]
            self.assertNotIn("<img", last_note)
            self.assertIn("&lt;img", last_note)
        finally:
            d._triage_items = original_items
            d.COGNIX_API_KEY = original_key

    def test_preset_name_is_sanitized(self):
        """Preset names should be HTML-escaped."""
        import app.dashboard as d
        from unittest.mock import patch
        original_presets = d._filter_presets.copy()
        original_key = d.COGNIX_API_KEY
        d.COGNIX_API_KEY = ""
        try:
            client = TestClient(app)
            with patch("app.dashboard._db_save_preset"):
                resp = client.post("/api/filter-presets", json={
                    "name": '<b>bold</b>',
                    "min_risk": 0.0,
                })
            self.assertEqual(resp.status_code, 200)
            preset = resp.json()["preset"]
            self.assertNotIn("<b>", preset["name"])
            self.assertIn("&lt;b&gt;", preset["name"])
        finally:
            d._filter_presets = original_presets
            d.COGNIX_API_KEY = original_key

    def test_text_query_max_length_enforced(self):
        """FilterParams.text_query rejects strings > 512 chars."""
        import app.dashboard as d
        import pandas as pd
        original_results = d._results
        d._results = pd.DataFrame({"risk_score": [0.5], "risk_band": ["Medium"], "user": ["x"], "text": ["y"]})
        try:
            client = TestClient(app)
            resp = client.post("/api/results", json={"text_query": "a" * 600})
            self.assertEqual(resp.status_code, 422)
        finally:
            d._results = original_results


class TestDockerConfig(unittest.TestCase):
    """Validate Dockerfile and docker-compose.yml exist and contain key directives."""

    def test_dockerfile_exists(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        self.assertTrue((project / "Dockerfile").is_file())

    def test_dockerfile_has_expose(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        content = (project / "Dockerfile").read_text()
        self.assertIn("EXPOSE 8000", content)
        self.assertIn("uvicorn", content)
        self.assertIn("CMD", content)

    def test_docker_compose_exists(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        self.assertTrue((project / "docker-compose.yml").is_file())

    def test_docker_compose_has_service(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        content = (project / "docker-compose.yml").read_text()
        self.assertIn("cognix", content)
        self.assertIn("8000:8000", content)

    def test_dockerignore_exists(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        self.assertTrue((project / ".dockerignore").is_file())


class TestEnvConfig(unittest.TestCase):
    """Validate .env / .env.example and python-dotenv integration."""

    def test_env_example_exists(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        self.assertTrue((project / ".env.example").is_file())

    def test_env_example_has_all_keys(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        content = (project / ".env.example").read_text()
        for key in ["COGNIX_API_KEY", "COGNIX_DB_PATH", "COGNIX_CORS_ORIGINS", "COGNIX_RATE_LIMIT"]:
            self.assertIn(key, content)

    def test_requirements_has_dotenv(self):
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        content = (project / "requirements.txt").read_text()
        self.assertIn("python-dotenv", content)


# Ensure `app` is importable at module level for TestClient
from app.dashboard import app

if __name__ == "__main__":
    unittest.main()
