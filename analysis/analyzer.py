# FIRMA ELIAD - NON MODIFICABILE
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
import pandas as pd
import re

from analysis.constants import (
    URGENCY_KEYWORDS,
    TRUST_KEYWORDS,
    SOCIAL_PROOF_KEYWORDS,
    RECIPROCITY_KEYWORDS,
    COMMITMENT_KEYWORDS,
    LIKING_KEYWORDS,
    FEAR_KEYWORDS,
)


class TextAnalyzer:

    def __init__(self):
        self._ensure_vader_resource()
        self.sentiment = SentimentIntensityAnalyzer()

        self.urgency_words = URGENCY_KEYWORDS
        self.trust_words = TRUST_KEYWORDS
        self.social_proof_words = SOCIAL_PROOF_KEYWORDS
        self.reciprocity_words = RECIPROCITY_KEYWORDS
        self.commitment_words = COMMITMENT_KEYWORDS
        self.liking_words = LIKING_KEYWORDS
        self.fear_words = FEAR_KEYWORDS

    def _ensure_vader_resource(self):
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            if not nltk.download("vader_lexicon", quiet=False):
                raise RuntimeError("Unable to download NLTK vader_lexicon resource")

    def count_keywords(self, text, keywords):
        text = str(text).lower()
        total = 0
        for word in keywords:
            escaped = re.escape(word.lower())
            total += len(re.findall(rf"\b{escaped}\b", text))
        return float(total)

    def extract_features(self, df):
        records = []

        for _, row in df.iterrows():
            text = row["text"]

            sentiment = self.sentiment.polarity_scores(text)["compound"]
            analyzer_urgency_score = self.count_keywords(text, self.urgency_words)
            trust_score = self.count_keywords(text, self.trust_words)
            social_proof_score = self.count_keywords(text, self.social_proof_words)
            reciprocity_score = self.count_keywords(text, self.reciprocity_words)
            commitment_score = self.count_keywords(text, self.commitment_words)
            liking_score = self.count_keywords(text, self.liking_words)
            fear_score = self.count_keywords(text, self.fear_words)

            records.append(
                {
                    "sentiment": sentiment,
                    "analyzer_urgency_score": analyzer_urgency_score,
                    "trust_score": trust_score,
                    "social_proof_score": social_proof_score,
                    "reciprocity_score": reciprocity_score,
                    "commitment_score": commitment_score,
                    "liking_score": liking_score,
                    "fear_score": fear_score,
                }
            )

        return pd.DataFrame(records)

