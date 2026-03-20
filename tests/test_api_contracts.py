# FIRMA ELIAD - NON MODIFICABILE
"""API contract tests for the FastAPI dashboard endpoints."""

import unittest

from fastapi.testclient import TestClient

from app.dashboard import app


class TestHealthEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("has_results", data)
        self.assertIn("result_count", data)

    def test_index_returns_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])


class TestResultsBeforeRun(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_results_before_run_returns_404(self):
        import app.dashboard as d
        import pandas as pd
        original = d._results
        d._results = pd.DataFrame()
        try:
            resp = self.client.post("/api/results", json={})
            self.assertEqual(resp.status_code, 404)
        finally:
            d._results = original

    def test_export_csv_before_run_returns_404(self):
        import app.dashboard as d
        import pandas as pd
        original = d._results
        d._results = pd.DataFrame()
        try:
            resp = self.client.get("/api/export/csv")
            self.assertEqual(resp.status_code, 404)
        finally:
            d._results = original

    def test_export_users_before_run_returns_404(self):
        import app.dashboard as d
        import pandas as pd
        original = d._results
        d._results = pd.DataFrame()
        try:
            resp = self.client.get("/api/export/users")
            self.assertEqual(resp.status_code, 404)
        finally:
            d._results = original

    def test_user_detail_before_run_returns_404(self):
        import app.dashboard as d
        import pandas as pd
        original = d._results
        d._results = pd.DataFrame()
        try:
            resp = self.client.get("/api/user/alice")
            self.assertEqual(resp.status_code, 404)
        finally:
            d._results = original


class TestRunEndpointValidation(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_run_invalid_dataset_path(self):
        resp = self.client.post("/api/run", json={"dataset_path": "/nonexistent/data.csv"})
        self.assertEqual(resp.status_code, 400)

    def test_run_invalid_weights_path(self):
        resp = self.client.post("/api/run", json={"weights_path": "/nonexistent/w.json"})
        self.assertEqual(resp.status_code, 400)


class TestFilterParamsValidation(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_min_risk_rejected(self):
        resp = self.client.post("/api/results", json={"min_risk": -0.5})
        self.assertEqual(resp.status_code, 422)

    def test_invalid_max_risk_rejected(self):
        resp = self.client.post("/api/results", json={"max_risk": 1.5})
        self.assertEqual(resp.status_code, 422)

    def test_invalid_top_n_rejected(self):
        resp = self.client.post("/api/results", json={"top_n": 0})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()

