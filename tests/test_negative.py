# FIRMA ELIAD - NON MODIFICABILE
"""Negative / edge-case tests for loader and risk engine."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from ingestion.loader import DataLoader
from model.risk_engine import RiskEngine


class TestLoaderNegative(unittest.TestCase):

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            DataLoader("/nonexistent/path.txt").load()

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.txt"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                DataLoader(str(path)).load()

    def test_only_empty_rows_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "blanks.txt"
            path.write_text(" ; \n;\n\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                DataLoader(str(path)).load()

    def test_latin1_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "latin1.txt"
            content = "alice;r\xe9sum\xe9 review urgent\n"
            path.write_bytes(content.encode("latin-1"))
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 1)
            self.assertIn("sum", df.iloc[0]["text"])

    def test_whitespace_only_user_dropped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ws.txt"
            path.write_text("   ;some text\nalice;hello\n", encoding="utf-8")
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0]["user"], "alice")


class TestRiskEngineNegative(unittest.TestCase):

    def test_missing_weights_key_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad_weights.json"
            path.write_text('{"urgency_score": 0.5}', encoding="utf-8")
            with self.assertRaises(ValueError):
                RiskEngine(weights_path=str(path))

    def test_weights_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            RiskEngine(weights_path="/nonexistent/weights.json")

    def test_missing_feature_columns_default_to_zero(self):
        df = pd.DataFrame({
            "urgency_score": [1.0],
            "authority_score": [0.5],
        })
        engine = RiskEngine()
        result = engine.calculate(df)
        self.assertIn("risk_score", result.columns)
        self.assertTrue(result["risk_score"].between(0.0, 1.0).all())

    def test_all_zero_features(self):
        df = pd.DataFrame({k: [0.0] for k in [
            "urgency_score", "authority_score", "semantic_signal",
            "text_length_signal", "sentiment_risk_signal", "trust_score",
            "social_proof_score", "reciprocity_score", "commitment_score",
            "liking_score", "fear_score",
        ]})
        engine = RiskEngine()
        result = engine.calculate(df)
        self.assertAlmostEqual(float(result["risk_score"].iloc[0]), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()

