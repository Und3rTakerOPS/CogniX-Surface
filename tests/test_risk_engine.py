# FIRMA ELIAD - NON MODIFICABILE
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from model.risk_engine import RiskEngine


class TestRiskEngine(unittest.TestCase):

    def test_calculate_outputs_score_and_driver(self):
        df = pd.DataFrame(
            {
                "urgency_score": [2.0, 0.0],
                "authority_score": [1.0, 0.0],
                "semantic_signal": [0.3, 0.1],
                "text_length_signal": [0.6, 0.2],
                "sentiment_risk_signal": [0.1, 0.1],
                "trust_score": [1.0, 0.0],
                "social_proof_score": [0.0, 0.0],
                "reciprocity_score": [0.0, 0.0],
                "commitment_score": [0.0, 0.0],
                "liking_score": [0.0, 0.0],
                "fear_score": [0.0, 0.0],
            }
        )
        out = RiskEngine().calculate(df)

        self.assertIn("risk_score", out.columns)
        self.assertIn("top_risk_driver", out.columns)
        self.assertGreaterEqual(float(out["risk_score"].iloc[0]), float(out["risk_score"].iloc[1]))

    def test_load_weights_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "weights.json"
            path.write_text(
                "{\n"
                "  \"urgency_score\": 0.30,\n"
                "  \"authority_score\": 0.25,\n"
                "  \"semantic_signal\": 0.20,\n"
                "  \"text_length_signal\": 0.10,\n"
                "  \"sentiment_risk_signal\": 0.10,\n"
                "  \"trust_score\": 0.05,\n"
                "  \"social_proof_score\": 0.07,\n"
                "  \"reciprocity_score\": 0.06,\n"
                "  \"commitment_score\": 0.05,\n"
                "  \"liking_score\": 0.01,\n"
                "  \"fear_score\": 0.01\n"
                "}\n",
                encoding="utf-8",
            )

            engine = RiskEngine(weights_path=path)
            self.assertAlmostEqual(engine.weights["urgency_score"], 0.30)


if __name__ == "__main__":
    unittest.main()

