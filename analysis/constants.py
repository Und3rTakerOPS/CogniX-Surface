# FIRMA ELIAD - NON MODIFICABILE
"""Shared keyword lists and regex patterns for cognitive attack signal detection.

Both TextAnalyzer and FeatureEngineer import from here to avoid duplication.
"""

# ---------------------------------------------------------------------------
# Keyword lists (used by TextAnalyzer for word-boundary counting)
# ---------------------------------------------------------------------------

URGENCY_KEYWORDS = [
    "urgent",
    "immediately",
    "asap",
    "important",
    "now",
    "quick",
]

TRUST_KEYWORDS = [
    "trust",
    "confidential",
    "secure",
    "official",
    "verified",
]

SOCIAL_PROOF_KEYWORDS = [
    "everyone",
    "everybody",
    "all colleagues",
    "team already",
    "already approved",
    "already done",
]

RECIPROCITY_KEYWORDS = [
    "favor",
    "in return",
    "i helped you",
    "return the favor",
    "ricambia",
    "per favore",
]

COMMITMENT_KEYWORDS = [
    "as promised",
    "as agreed",
    "as discussed",
    "you said",
    "come concordato",
    "come promesso",
]

LIKING_KEYWORDS = [
    "dear friend",
    "dear colleague",
    "you are the best",
    "appreciate you",
    "caro amico",
    "ti stimo",
]

FEAR_KEYWORDS = [
    "account suspended",
    "account blocked",
    "legal action",
    "penalty",
    "breach",
    "sospeso",
    "bloccato",
]

# ---------------------------------------------------------------------------
# Regex patterns (used by FeatureEngineer for vectorised pandas str.count)
# ---------------------------------------------------------------------------

import re as _re

URGENCY_REGEX = r"\burgent\b|\basap\b|\bnow\b|\bimmediately\b"

AUTHORITY_REGEX = r"\bmanager\b|\bdirector\b|\badmin\b|\bit\b"

SOCIAL_PROOF_REGEX = (
    r"\beveryone\b|\beverybody\b|\ball\s+colleagues\b"
    r"|\balready\s+approved\b|\balready\s+done\b|\btutti\b"
)

RECIPROCITY_REGEX = (
    r"\bfavor\b|\bin\s+return\b|\breturn\s+the\s+favor\b"
    r"|\bi\s+helped\s+you\b|\bricambia\b|\bper\s+favore\b"
)

COMMITMENT_REGEX = (
    r"\bas\s+promised\b|\bas\s+agreed\b|\bas\s+discussed\b"
    r"|\byou\s+said\b|\bcome\s+concordato\b|\bcome\s+promesso\b"
)

LIKING_REGEX = (
    r"\bdear\s+friend\b|\bdear\s+colleague\b|\byou\s+are\s+the\s+best\b"
    r"|\bappreciate\s+you\b|\bcaro\s+amico\b|\bti\s+stimo\b"
)

FEAR_REGEX = (
    r"\baccount\s+suspended\b|\baccount\s+blocked\b|\blegal\s+action\b"
    r"|\bpenalty\b|\bbreach\b|\bsospeso\b|\bbloccato\b"
)

# Pre-compiled versions for faster repeated matching
URGENCY_RE = _re.compile(URGENCY_REGEX, _re.IGNORECASE)
AUTHORITY_RE = _re.compile(AUTHORITY_REGEX, _re.IGNORECASE)
SOCIAL_PROOF_RE = _re.compile(SOCIAL_PROOF_REGEX, _re.IGNORECASE)
RECIPROCITY_RE = _re.compile(RECIPROCITY_REGEX, _re.IGNORECASE)
COMMITMENT_RE = _re.compile(COMMITMENT_REGEX, _re.IGNORECASE)
LIKING_RE = _re.compile(LIKING_REGEX, _re.IGNORECASE)
FEAR_RE = _re.compile(FEAR_REGEX, _re.IGNORECASE)

# ---------------------------------------------------------------------------
# Dashboard / scoring thresholds
# ---------------------------------------------------------------------------

RISK_BAND_BINS = [0.0, 0.4, 0.7, 1.01]
RISK_BAND_LABELS = ["Low", "Medium", "High"]

# Colorblind-friendly palette (ColorBrewer Safe)
RISK_BAND_COLORS = {
    "Low": "#377eb8",     # blue
    "Medium": "#ff7f00",  # orange
    "High": "#e41a1c",    # red
}

# Default NLP model
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_BATCH_SIZE = 64

