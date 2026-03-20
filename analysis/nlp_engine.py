# FIRMA ELIAD - NON MODIFICABILE
import hashlib
import logging
import numpy as np
from sentence_transformers import SentenceTransformer

from analysis.constants import DEFAULT_EMBEDDING_BATCH_SIZE, DEFAULT_EMBEDDING_MODEL


class _HFPositionIdsNoiseFilter(logging.Filter):
    """Hide only the known harmless transformers warning about position_ids."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "embeddings.position_ids" in msg and "UNEXPECTED" in msg:
            return False
        if "embeddings.position_ids" in msg and "were not used when initializing" in msg:
            return False
        return True


logging.getLogger("transformers.modeling_utils").addFilter(_HFPositionIdsNoiseFilter())
logging.getLogger("sentence_transformers").addFilter(_HFPositionIdsNoiseFilter())


class NLPEngine:

    def __init__(self, model_name=DEFAULT_EMBEDDING_MODEL):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._cache: dict[str, np.ndarray] = {}

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def encode(self, texts, batch_size=DEFAULT_EMBEDDING_BATCH_SIZE):
        if not texts:
            raise ValueError("Cannot encode an empty list of texts")

        # Separate cached vs. new texts
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, t in enumerate(texts):
            h = self._hash_text(t)
            if h in self._cache:
                results[i] = self._cache[h]
            else:
                uncached_indices.append(i)
                uncached_texts.append(t)

        if uncached_texts:
            new_embeddings = self.model.encode(
                uncached_texts,
                convert_to_tensor=False,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=batch_size,
            )
            new_embeddings = np.asarray(new_embeddings, dtype=float)
            if not np.all(np.isfinite(new_embeddings)):
                raise RuntimeError("Embedding output contains NaN or Inf values")

            for j, idx in enumerate(uncached_indices):
                self._cache[self._hash_text(texts[idx])] = new_embeddings[j]
                results[idx] = new_embeddings[j]

        embeddings = np.array(results, dtype=float)
        return embeddings

