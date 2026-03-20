# FIRMA ELIAD - NON MODIFICABILE
"""Edge-case tests â€” Unicode, emoji, very long text, special characters,
negative weights, NaN features, embedding cache, compiled regex."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.analyzer import TextAnalyzer
from analysis.feature_engineering import FeatureEngineer
from analysis.nlp_engine import NLPEngine
from ingestion.loader import DataLoader
from model.risk_engine import RiskEngine, DEFAULT_WEIGHTS


# â”€â”€ Loader edge cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestLoaderEdgeCases(unittest.TestCase):

    def test_unicode_characters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "uni.txt"
            path.write_text("ç”¨æˆ·;è¿™æ˜¯ä¸­æ–‡æ–‡æœ¬\nãƒ¦ãƒ¼ã‚¶ãƒ¼;æ—¥æœ¬èªžãƒ†ã‚¹ãƒˆ\n", encoding="utf-8")
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 2)

    def test_emoji_in_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "emoji.txt"
            path.write_text("alice;Hello ðŸŽ‰ðŸ”¥ urgent request!\nbob;All good ðŸ‘\n", encoding="utf-8")
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 2)
            self.assertIn("ðŸŽ‰", df.iloc[0]["text"])

    def test_very_long_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "long.txt"
            long_text = "a" * 50_000
            path.write_text(f"alice;{long_text}\n", encoding="utf-8")
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 1)
            self.assertEqual(len(df.iloc[0]["text"]), 50_000)

    def test_semicolon_in_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "semi.txt"
            path.write_text("alice;text with; extra; semicolons\n", encoding="utf-8")
            df = DataLoader(str(path)).load()
            self.assertEqual(len(df), 1)


# â”€â”€ Analyzer edge cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestAnalyzerEdgeCases(unittest.TestCase):

    def setUp(self):
        self.analyzer = TextAnalyzer()

    def test_empty_string_keyword_count(self):
        score = self.analyzer.count_keywords("", self.analyzer.urgency_words)
        self.assertEqual(score, 0.0)

    def test_very_short_text(self):
        df = pd.DataFrame({"user": ["a"], "text": ["hi"]})
        result = self.analyzer.extract_features(df)
        self.assertEqual(len(result), 1)
        # All keyword-based scores should be zero for a two-char text
        for col in ["analyzer_urgency_score", "trust_score", "fear_score"]:
            self.assertEqual(float(result[col].iloc[0]), 0.0)

    def test_repeated_keywords(self):
        text = "urgent urgent urgent ASAP ASAP"
        score = self.analyzer.count_keywords(text, self.analyzer.urgency_words)
        self.assertEqual(score, 5.0)  # 3 Ã— urgent + 2 Ã— ASAP

    def test_special_characters_no_crash(self):
        df = pd.DataFrame({"user": ["x"], "text": ["$100 off! <script>alert('xss')</script> \\n\\t"]})
        result = self.analyzer.extract_features(df)
        self.assertEqual(len(result), 1)

    def test_numeric_only_text(self):
        df = pd.DataFrame({"user": ["x"], "text": ["123456789"]})
        result = self.analyzer.extract_features(df)
        self.assertEqual(len(result), 1)


# â”€â”€ Feature Engineering edge cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestFeatureEngineerEdgeCases(unittest.TestCase):

    def test_single_row_normalization(self):
        """When only 1 row, text_length_signal should be 0 (min == max)."""
        df = pd.DataFrame({"user": ["a"], "text": ["some text"]})
        fe = FeatureEngineer()
        embeddings = np.random.randn(1, 384)
        result = fe.build_features(df, embeddings)
        self.assertEqual(float(result["text_length_signal"].iloc[0]), 0.0)

    def test_compiled_regex_matching(self):
        """Verify compiled regex still detects keywords correctly."""
        df = pd.DataFrame({"user": ["a"], "text": ["URGENT asap now"]})
        fe = FeatureEngineer()
        embeddings = np.random.randn(1, 384)
        result = fe.build_features(df, embeddings)
        self.assertGreaterEqual(float(result["urgency_score"].iloc[0]), 3.0)


# â”€â”€ NLP Engine edge cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestNLPEngineEdgeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = NLPEngine()

    def test_emoji_text_encoding(self):
        embs = self.engine.encode(["Hello ðŸŽ‰ðŸ”¥ world"])
        self.assertEqual(embs.shape[0], 1)
        self.assertTrue(np.all(np.isfinite(embs)))

    def test_very_short_text_encoding(self):
        embs = self.engine.encode(["a"])
        self.assertEqual(embs.shape[0], 1)

    def test_very_long_text_encoding(self):
        long_text = "word " * 5000
        embs = self.engine.encode([long_text])
        self.assertEqual(embs.shape[0], 1)
        self.assertTrue(np.all(np.isfinite(embs)))

    def test_cache_returns_same_result(self):
        """Encoding the same text twice should use cache and return identical results."""
        text = "This is a cache test sentence."
        embs1 = self.engine.encode([text])
        embs2 = self.engine.encode([text])
        np.testing.assert_array_equal(embs1, embs2)

    def test_mixed_cached_and_new(self):
        """Mix of cached and new texts should work correctly."""
        texts_a = ["cache hit text", "new text alpha"]
        embs_a = self.engine.encode(texts_a)
        texts_b = ["cache hit text", "new text beta"]
        embs_b = self.engine.encode(texts_b)
        # First embedding (same text) should be identical
        np.testing.assert_array_equal(embs_a[0], embs_b[0])
        # Second embedding (different text) should differ
        self.assertFalse(np.array_equal(embs_a[1], embs_b[1]))


# â”€â”€ Risk Engine edge cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestRiskEngineEdgeCases(unittest.TestCase):

    def test_negative_weights_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "neg.json"
            bad_weights = DEFAULT_WEIGHTS.copy()
            bad_weights["urgency_score"] = -0.5
            path.write_text(json.dumps(bad_weights), encoding="utf-8")
            with self.assertRaises(ValueError):
                RiskEngine(weights_path=str(path))

    def test_inf_weight_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inf.json"
            bad_weights = DEFAULT_WEIGHTS.copy()
            bad_weights["urgency_score"] = float("inf")
            path.write_text(json.dumps(bad_weights), encoding="utf-8")
            with self.assertRaises(ValueError):
                RiskEngine(weights_path=str(path))

    def test_very_high_feature_values(self):
        """Features with very high counts should still produce scores in [0, 1]."""
        df = pd.DataFrame({k: [1000.0] for k in DEFAULT_WEIGHTS})
        engine = RiskEngine()
        result = engine.calculate(df)
        self.assertTrue(result["risk_score"].between(0.0, 1.0).all())

    def test_scores_bounded(self):
        """All output risk scores must be within [0, 1]."""
        np.random.seed(42)
        df = pd.DataFrame({k: np.random.rand(50) * 10 for k in DEFAULT_WEIGHTS})
        engine = RiskEngine()
        result = engine.calculate(df)
        self.assertTrue(result["risk_score"].between(0.0, 1.0).all())


if __name__ == "__main__":
    unittest.main()

