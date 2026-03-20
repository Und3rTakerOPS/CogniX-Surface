# FIRMA ELIAD - NON MODIFICABILE
import re

import numpy as np

from analysis.constants import (
    URGENCY_RE,
    AUTHORITY_RE,
    SOCIAL_PROOF_RE,
    RECIPROCITY_RE,
    COMMITMENT_RE,
    LIKING_RE,
    FEAR_RE,
)


class FeatureEngineer:

    def _normalize_series(self, series):
        min_val = float(series.min())
        max_val = float(series.max())

        if max_val == min_val:
            return series * 0.0

        return (series - min_val) / (max_val - min_val)

    @staticmethod
    def _count_compiled(text: str, pattern: re.Pattern) -> int:
        return len(pattern.findall(text))

    def build_features(self, df, embeddings, analyzer_features=None):
        out = df.copy()

        out["text_length"] = out["text"].apply(len)
        out["text_length_signal"] = self._normalize_series(out["text_length"].astype(float))

        out["urgency_score"] = out["text"].apply(lambda t: self._count_compiled(t, URGENCY_RE))
        out["authority_score"] = out["text"].apply(lambda t: self._count_compiled(t, AUTHORITY_RE))
        out["social_proof_score"] = out["text"].apply(lambda t: self._count_compiled(t, SOCIAL_PROOF_RE))
        out["reciprocity_score"] = out["text"].apply(lambda t: self._count_compiled(t, RECIPROCITY_RE))
        out["commitment_score"] = out["text"].apply(lambda t: self._count_compiled(t, COMMITMENT_RE))
        out["liking_score"] = out["text"].apply(lambda t: self._count_compiled(t, LIKING_RE))
        out["fear_score"] = out["text"].apply(lambda t: self._count_compiled(t, FEAR_RE))

        # Semantic signal: ratio of L1 norm to theoretical max for L2-normalized embeddings.
        emb_array = np.asarray(embeddings, dtype=float)
        emb_l1 = np.linalg.norm(emb_array, ord=1, axis=1)
        emb_dim = float(emb_array.shape[1]) if emb_array.ndim == 2 and emb_array.shape[1] > 0 else 1.0
        out["semantic_signal"] = np.clip(emb_l1 / np.sqrt(emb_dim), 0.0, 1.0)

        if analyzer_features is not None and not analyzer_features.empty:
            aligned = analyzer_features.reset_index(drop=True)

            out["sentiment"] = aligned["sentiment"].astype(float)
            out["sentiment_risk_signal"] = np.abs(out["sentiment"])
            out["trust_score"] = aligned["trust_score"].astype(float)
            out["analyzer_urgency_score"] = aligned["analyzer_urgency_score"].astype(float)

            # Use the maximum between regex and analyzer counts (not a sum)
            # to avoid inflating scores when both sources detect the same signal.
            for col in ["social_proof_score", "reciprocity_score", "commitment_score",
                        "liking_score", "fear_score"]:
                out[col] = np.maximum(out[col].to_numpy(dtype=float),
                                      aligned[col].to_numpy(dtype=float))

            out["urgency_score"] = out[["urgency_score", "analyzer_urgency_score"]].max(axis=1)
        else:
            out["sentiment"] = 0.0
            out["sentiment_risk_signal"] = 0.0
            out["trust_score"] = 0.0

        return out

