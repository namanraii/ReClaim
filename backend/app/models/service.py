"""
Model loading service — singleton access to the trained failure classifier.
"""

from pathlib import Path
from typing import Optional

from .classifier import FailureClassifier

MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "failure_classifier.joblib"

_classifier: Optional[FailureClassifier] = None


def get_classifier() -> FailureClassifier:
    """Return a loaded FailureClassifier, training artifact required."""
    global _classifier
    if _classifier is None:
        _classifier = FailureClassifier(model_type="xgboost")
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Trained model not found at {MODEL_PATH}. "
                "Run: python -m scripts.train_classifier"
            )
        _classifier.load_model(str(MODEL_PATH))
    return _classifier


def is_model_available() -> bool:
    return MODEL_PATH.exists()


def reset_classifier() -> None:
    """Clear cached classifier (useful in tests)."""
    global _classifier
    _classifier = None
