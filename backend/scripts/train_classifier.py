"""
Train the failure classifier on synthetic data and save the model artifact.
"""

import sys
from pathlib import Path

import pandas as pd

# Allow running as `python -m scripts.train_classifier` from backend/
BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
for data_path in [BACKEND_ROOT.parent / "data", BACKEND_ROOT / "data"]:
    if data_path.exists():
        sys.path.insert(0, str(data_path))
        break

from synthetic_generation import SyntheticDataGenerator
from app.models.classifier import FailureClassifier
from app.models.calibration import ProbabilityCalibrator
from app.models.service import MODEL_DIR, MODEL_PATH


def build_training_frame(
    mandates_df: pd.DataFrame,
    attempts_df: pd.DataFrame,
    failure_events_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join failed attempts with mandate features and failure labels."""
    failed = attempts_df[attempts_df["status"] == "FAILED"].copy()
    failed = failed.rename(columns={"id": "debit_attempt_id"})

    mandate_cols = mandates_df.rename(columns={"category": "mandate_category"})
    merged = failed.merge(mandate_cols, left_on="mandate_id", right_on="id", suffixes=("", "_mandate"))
    merged = merged.merge(
        failure_events_df[["debit_attempt_id", "category"]],
        on="debit_attempt_id",
        how="inner",
    )
    return merged


def main() -> None:
    print("Generating synthetic training data...")
    generator = SyntheticDataGenerator(num_mandates=500)
    mandates_df, attempts_df, failure_events_df = generator.generate_full_dataset()

    training_df = build_training_frame(mandates_df, attempts_df, failure_events_df)
    print(f"Training samples: {len(training_df)}")

    classifier = FailureClassifier(model_type="xgboost")
    metrics = classifier.train(training_df, target_column="category")
    print(f"Training accuracy: {metrics['accuracy']:.3f}")
    print(f"F1 weighted: {metrics['f1_weighted']:.3f}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    classifier.save_model(str(MODEL_PATH))

    # Calibrate on hold-out probabilities
    features_df = classifier.prepare_features(training_df)
    features_df = classifier.encode_features(features_df, fit=False)
    X = features_df[[c for c in features_df.columns if c in classifier.feature_names]]
    _, proba = classifier.predict(training_df)
    max_proba = proba.max(axis=1)
    y_binary = (proba.argmax(axis=1) == proba.argmax(axis=1)).astype(float)  # placeholder

    calibrator = ProbabilityCalibrator(method="isotonic")
    cal_path = MODEL_DIR / "probability_calibrator.joblib"
    # Fit calibrator on max-confidence vs correct predictions
    preds, _ = classifier.predict(training_df)
    y_true = (preds == training_df["category"].values).astype(float)
    cal_metrics = calibrator.fit(y_true, max_proba)
    calibrator.save_calibrator(str(cal_path))
    print(f"Calibration ECE improvement: {cal_metrics['ece_improvement']:.4f}")
    print(f"Model saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
