# FIRMA ELIAD - NON MODIFICABILE
"""Integration test: exercises the full pipeline end-to-end."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ingestion.loader import DataLoader
from analysis.nlp_engine import NLPEngine
from analysis.analyzer import TextAnalyzer
from analysis.feature_engineering import FeatureEngineer
from model.risk_engine import RiskEngine


SAMPLE_DATASET = (
    "alice;Urgent action required from IT, send credentials ASAP\n"
    "bob;This is a confidential and official request, trust me\n"
    "carol;No rush, just checking in to say hello\n"
    "dave;Your account suspended immediately! Legal action pending\n"
    "eve;Dear friend, as promised here is the file you requested\n"
)

SAMPLE_WEIGHTS = {
    "urgency_score": 0.18,
    "authority_score": 0.15,
    "semantic_signal": 0.12,
    "text_length_signal": 0.08,
    "sentiment_risk_signal": 0.08,
    "trust_score": 0.06,
    "social_proof_score": 0.10,
    "reciprocity_score": 0.08,
    "commitment_score": 0.07,
    "liking_score": 0.04,
    "fear_score": 0.04,
}


class TestIntegrationPipeline(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmpdir = self._tmpdir.name

        self.dataset_path = Path(tmpdir) / "data.txt"
        self.dataset_path.write_text(SAMPLE_DATASET, encoding="utf-8")

        self.weights_path = Path(tmpdir) / "weights.json"
        self.weights_path.write_text(json.dumps(SAMPLE_WEIGHTS), encoding="utf-8")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_full_pipeline_produces_valid_output(self):
        # 1. Ingest
        df = DataLoader(str(self.dataset_path)).load()
        self.assertEqual(len(df), 5)

        # 2. NLP
        nlp = NLPEngine()
        embeddings = nlp.encode(df["text"].tolist())
        self.assertEqual(embeddings.shape[0], 5)

        # 3. Analyzer
        analyzer = TextAnalyzer()
        analyzer_features = analyzer.extract_features(df)
        self.assertEqual(len(analyzer_features), 5)

        # 4. Feature engineering
        fe = FeatureEngineer()
        featured = fe.build_features(df, embeddings, analyzer_features=analyzer_features)
        self.assertIn("urgency_score", featured.columns)
        self.assertIn("semantic_signal", featured.columns)
        self.assertIn("sentiment_risk_signal", featured.columns)

        # 5. Risk scoring
        engine = RiskEngine(weights_path=str(self.weights_path))
        results = engine.calculate(featured, include_explanations=True)

        self.assertIn("risk_score", results.columns)
        self.assertIn("top_risk_driver", results.columns)
        self.assertTrue(results["risk_score"].between(0.0, 1.0).all())
        self.assertEqual(len(results), 5)

        # The most urgent/fear message should rank highest
        top_user = results.iloc[0]["user"]
        self.assertIn(top_user, ["alice", "dave"])

    def test_pipeline_scores_are_deterministic(self):
        df = DataLoader(str(self.dataset_path)).load()
        nlp = NLPEngine()

        # Run twice
        emb1 = nlp.encode(df["text"].tolist())
        emb2 = nlp.encode(df["text"].tolist())

        analyzer = TextAnalyzer()
        af1 = analyzer.extract_features(df)
        af2 = analyzer.extract_features(df)

        fe = FeatureEngineer()
        feat1 = fe.build_features(df, emb1, analyzer_features=af1)
        feat2 = fe.build_features(df, emb2, analyzer_features=af2)

        engine = RiskEngine(weights_path=str(self.weights_path))
        r1 = engine.calculate(feat1)
        r2 = engine.calculate(feat2)

        np.testing.assert_array_almost_equal(
            r1["risk_score"].to_numpy(),
            r2["risk_score"].to_numpy(),
            decimal=6,
        )


if __name__ == "__main__":
    unittest.main()

