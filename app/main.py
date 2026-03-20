# FIRMA ELIAD - NON MODIFICABILE
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger
from ingestion.loader import DataLoader
from analysis.nlp_engine import NLPEngine
from analysis.analyzer import TextAnalyzer
from analysis.feature_engineering import FeatureEngineer
from model.risk_engine import RiskEngine
from visualization.report import show_report

logger = setup_logger()
DEFAULT_DATASET = PROJECT_ROOT / "datacommunications.txt.txt"
DEFAULT_WEIGHTS = PROJECT_ROOT / "config" / "risk_weights.json"


def parse_args():
    parser = argparse.ArgumentParser(description="CogniX Surface")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to semicolon-separated dataset with 'user;text' rows.",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=DEFAULT_WEIGHTS,
        help="Path to risk weights JSON file.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of rows to show in CLI report.",
    )
    return parser.parse_args()


def run_pipeline(dataset_path: Path, weights_path: Path):
    logger.info("Loading dataset")
    loader = DataLoader(str(dataset_path))
    df = loader.load()

    logger.info("Running NLP engine")
    nlp = NLPEngine()
    embeddings = nlp.encode(df["text"].tolist())

    logger.info("Extracting analyzer features")
    analyzer = TextAnalyzer()
    analyzer_features = analyzer.extract_features(df)

    logger.info("Extracting engineered features")
    fe = FeatureEngineer()
    featured = fe.build_features(df, embeddings, analyzer_features=analyzer_features)

    logger.info("Calculating risk")
    risk_engine = RiskEngine(weights_path=str(weights_path))
    return risk_engine.calculate(featured, include_explanations=True)


def main():
    args = parse_args()
    results = run_pipeline(args.dataset, args.weights)
    show_report(results.head(max(1, args.top)))


if __name__ == "__main__":
    main()

