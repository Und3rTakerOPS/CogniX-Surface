# FIRMA ELIAD - NON MODIFICABILE
import unittest

import numpy as np
import pandas as pd

from analysis.feature_engineering import FeatureEngineer


class TestFeatureEngineering(unittest.TestCase):

    def test_build_features_creates_expected_columns(self):
        df = pd.DataFrame(
            {
                "user": ["alice", "bob"],
                "text": ["Urgent action from IT", "No rush, maybe tomorrow"],
            }
        )
        embeddings = np.array([[0.1, 0.2], [0.4, 0.5]])
        analyzer_df = pd.DataFrame(
            {
                "sentiment": [0.5, -0.2],
                "analyzer_urgency_score": [1, 0],
                "trust_score": [1, 0],
                "social_proof_score": [1, 0],
                "reciprocity_score": [0, 1],
                "commitment_score": [0, 0],
                "liking_score": [0, 0],
                "fear_score": [0, 0],
            }
        )

        out = FeatureEngineer().build_features(df, embeddings, analyzer_features=analyzer_df)

        self.assertIn("text_length_signal", out.columns)
        self.assertIn("semantic_signal", out.columns)
        self.assertIn("sentiment_risk_signal", out.columns)
        self.assertIn("social_proof_score", out.columns)
        self.assertIn("reciprocity_score", out.columns)
        self.assertGreaterEqual(float(out["urgency_score"].iloc[0]), 1.0)
        self.assertTrue(out["semantic_signal"].between(0.0, 1.0).all())


if __name__ == "__main__":
    unittest.main()

