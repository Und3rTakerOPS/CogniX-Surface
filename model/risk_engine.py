# FIRMA ELIAD - NON MODIFICABILE
import json
from pathlib import Path

import numpy as np


DEFAULT_WEIGHTS = {
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


class RiskEngine:

    def __init__(self, weights_path=None):
        self.weights = self._load_weights(weights_path)

    def _load_weights(self, weights_path):
        if weights_path is None:
            return DEFAULT_WEIGHTS.copy()

        path = Path(weights_path)
        if not path.exists():
            raise FileNotFoundError(f"Risk weights file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)

        missing = [k for k in DEFAULT_WEIGHTS if k not in loaded]
        if missing:
            raise ValueError(f"Risk weights file missing keys: {missing}")

        weights = {k: float(v) for k, v in loaded.items()}
        invalid = [k for k, v in weights.items() if v < 0 or not np.isfinite(v)]
        if invalid:
            raise ValueError(f"Risk weights must be non-negative finite numbers. Invalid keys: {invalid}")

        return weights

    def _to_unit_interval(self, values, feature_name):
        values = np.asarray(values, dtype=float)
        values = np.clip(values, 0.0, None)

        count_like = {
            "urgency_score",
            "authority_score",
            "trust_score",
            "social_proof_score",
            "reciprocity_score",
            "commitment_score",
            "liking_score",
            "fear_score",
        }

        if feature_name in count_like:
            return 1.0 - np.exp(-values)

        return np.clip(values, 0.0, 1.0)

    def _normalize_absolute(self, weighted_sum):
        """Normalize to [0, 1] by dividing by the theoretical maximum
        (sum of weights), making scores comparable across different runs."""
        total_weight = float(sum(self.weights.values()))
        if total_weight <= 0.0:
            return np.zeros_like(weighted_sum, dtype=float)

        return np.clip(weighted_sum / total_weight, 0.0, 1.0)

    def calculate(self, df, include_explanations=True):
        out = df.copy()

        for feature in self.weights:
            if feature not in out.columns:
                out[feature] = 0.0

        weighted_sum = np.zeros(len(out), dtype=float)

        for feature, weight in self.weights.items():
            contrib_col = f"contrib_{feature}"
            normalized_feature = self._to_unit_interval(out[feature].to_numpy(), feature)
            out[contrib_col] = normalized_feature * float(weight)
            weighted_sum += out[contrib_col].to_numpy()

        out["risk_raw"] = weighted_sum
        out["risk_score"] = self._normalize_absolute(out["risk_raw"].to_numpy())

        if include_explanations:
            contribution_columns = [f"contrib_{name}" for name in self.weights]
            out["top_risk_driver"] = (
                out[contribution_columns].idxmax(axis=1).str.replace("contrib_", "", regex=False)
            )

        return out.sort_values(by="risk_score", ascending=False).reset_index(drop=True)

