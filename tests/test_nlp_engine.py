# FIRMA ELIAD - NON MODIFICABILE
"""Tests for NLPEngine: encoding, validation, batch processing."""

import unittest

import numpy as np

from analysis.nlp_engine import NLPEngine


class TestNLPEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = NLPEngine()

    def test_encode_returns_numpy_array(self):
        result = self.engine.encode(["hello world"])
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.ndim, 2)

    def test_encode_correct_shape(self):
        texts = ["first text", "second text", "third text"]
        result = self.engine.encode(texts)
        self.assertEqual(result.shape[0], 3)
        self.assertGreater(result.shape[1], 0)

    def test_encode_embeddings_are_normalized(self):
        result = self.engine.encode(["The quick brown fox"])
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_encode_empty_raises_error(self):
        with self.assertRaises(ValueError):
            self.engine.encode([])

    def test_encode_embeddings_are_finite(self):
        result = self.engine.encode(["test embedding"])
        self.assertTrue(np.all(np.isfinite(result)))

    def test_encode_with_custom_batch_size(self):
        texts = [f"text number {i}" for i in range(20)]
        result = self.engine.encode(texts, batch_size=4)
        self.assertEqual(result.shape[0], 20)

    def test_configurable_model_name(self):
        engine = NLPEngine(model_name="all-MiniLM-L6-v2")
        self.assertEqual(engine.model_name, "all-MiniLM-L6-v2")


if __name__ == "__main__":
    unittest.main()

