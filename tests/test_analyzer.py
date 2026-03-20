# FIRMA ELIAD - NON MODIFICABILE
import unittest

import pandas as pd

from analysis.analyzer import TextAnalyzer


class TestTextAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = TextAnalyzer()

    def test_count_keywords_finds_exact_words(self):
        text = "This is urgent, we need it now"
        score = self.analyzer.count_keywords(text, self.analyzer.urgency_words)
        self.assertGreaterEqual(score, 2.0)  # "urgent" + "now"

    def test_count_keywords_no_match(self):
        text = "Everything is fine, no rush at all"
        score = self.analyzer.count_keywords(text, self.analyzer.fear_words)
        self.assertEqual(score, 0.0)

    def test_count_keywords_multiword_phrases(self):
        text = "Your account suspended immediately, legal action pending"
        score = self.analyzer.count_keywords(text, self.analyzer.fear_words)
        self.assertGreaterEqual(score, 2.0)  # "account suspended" + "legal action"

    def test_count_keywords_case_insensitive(self):
        text = "URGENT request from MANAGER"
        score = self.analyzer.count_keywords(text, self.analyzer.urgency_words)
        self.assertGreaterEqual(score, 1.0)

    def test_count_keywords_italian_terms(self):
        text = "Il tuo account Ã¨ sospeso e bloccato"
        score = self.analyzer.count_keywords(text, self.analyzer.fear_words)
        self.assertGreaterEqual(score, 2.0)  # "sospeso" + "bloccato"

    def test_extract_features_returns_all_columns(self):
        df = pd.DataFrame({
            "user": ["alice", "bob"],
            "text": [
                "Urgent: your account suspended, trust me",
                "Dear friend, as promised here is the file",
            ],
        })
        features = self.analyzer.extract_features(df)

        expected_columns = [
            "sentiment",
            "analyzer_urgency_score",
            "trust_score",
            "social_proof_score",
            "reciprocity_score",
            "commitment_score",
            "liking_score",
            "fear_score",
        ]
        for col in expected_columns:
            self.assertIn(col, features.columns)

        self.assertEqual(len(features), 2)

    def test_extract_features_detects_urgency(self):
        df = pd.DataFrame({
            "user": ["alice"],
            "text": ["This is urgent, do it now immediately"],
        })
        features = self.analyzer.extract_features(df)
        self.assertGreaterEqual(features["analyzer_urgency_score"].iloc[0], 2.0)

    def test_extract_features_detects_trust(self):
        df = pd.DataFrame({
            "user": ["alice"],
            "text": ["This is confidential and official information"],
        })
        features = self.analyzer.extract_features(df)
        self.assertGreaterEqual(features["trust_score"].iloc[0], 2.0)

    def test_extract_features_detects_fear(self):
        df = pd.DataFrame({
            "user": ["alice"],
            "text": ["Your account suspended, legal action will follow with penalty"],
        })
        features = self.analyzer.extract_features(df)
        self.assertGreaterEqual(features["fear_score"].iloc[0], 2.0)


if __name__ == "__main__":
    unittest.main()

