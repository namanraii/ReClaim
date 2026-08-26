"""
Classification API Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
import pandas as pd

from app.db import get_db
from app.models import get_classifier, is_model_available, FailureClassifier
from app.models.service import MODEL_PATH
from pydantic import BaseModel


router = APIRouter(prefix="/classification", tags=["classification"])


class ClassificationRequest(BaseModel):
    mandate_id: str
    bank_code: str
    psp_app: str
    amount: float
    scheduled_at: str
    attempt_number: int
    category: str = "subscription"
    pin_reauth_required: bool = False


class TrainRequest(BaseModel):
    data_file: str = ""
    model_type: str = "xgboost"


def _request_to_dataframe(request: ClassificationRequest) -> pd.DataFrame:
    return pd.DataFrame([{
        "mandate_id": request.mandate_id,
        "bank_code": request.bank_code,
        "psp_app": request.psp_app,
        "amount": request.amount,
        "scheduled_at": request.scheduled_at,
        "attempt_number": request.attempt_number,
        "category": request.category,
        "pin_reauth_required": request.pin_reauth_required,
        "created_at": request.scheduled_at,
    }])


def _format_shap(explanation: Dict) -> Dict[str, float]:
    importance = explanation.get("feature_importance", {})
    total = sum(importance.values()) or 1.0
    return {k: round(v / total, 3) for k, v in importance.items()}


@router.post("/predict")
def predict_failure(request: ClassificationRequest, db: Session = Depends(get_db)):
    """Predict failure category for a mandate attempt using the trained model."""
    if not is_model_available():
        raise HTTPException(
            status_code=503,
            detail="Classifier not trained. Run: python -m scripts.train_classifier",
        )
    try:
        classifier = get_classifier()
        df = _request_to_dataframe(request)
        predictions, confidence_scores = classifier.predict(df)
        predicted = predictions[0]
        confidence = float(confidence_scores[0].max())
        explanation = classifier.explain_prediction(df, index=0)

        return {
            "mandate_id": request.mandate_id,
            "predicted_category": predicted,
            "confidence": round(confidence, 3),
            "shap_explanation": _format_shap(explanation),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train")
def train_classifier(request: TrainRequest, db: Session = Depends(get_db)):
    """Train the failure classifier on synthetic data."""
    try:
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "scripts.train_classifier"],
            capture_output=True,
            text=True,
            cwd=str(MODEL_PATH.parent.parent),
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr)
        return {
            "message": "Classifier trained successfully",
            "model_type": request.model_type,
            "status": "completed",
            "model_path": str(MODEL_PATH),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{mandate_id}")
def explain_prediction(mandate_id: str, db: Session = Depends(get_db)):
    """Get SHAP explanation for the latest failure on a mandate."""
    from app.db.models import DebitAttempt, FailureEvent, Mandate

    if not is_model_available():
        raise HTTPException(status_code=503, detail="Classifier not trained.")

    mandate = db.query(Mandate).filter(Mandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    latest_attempt = (
        db.query(DebitAttempt)
        .filter(DebitAttempt.mandate_id == mandate_id, DebitAttempt.status == "FAILED")
        .order_by(DebitAttempt.scheduled_at.desc())
        .first()
    )
    if not latest_attempt:
        raise HTTPException(status_code=404, detail="No failed attempts found")

    df = pd.DataFrame([{
        "mandate_id": mandate_id,
        "bank_code": mandate.bank_code,
        "psp_app": mandate.psp_app,
        "amount": latest_attempt.amount,
        "scheduled_at": latest_attempt.scheduled_at.isoformat(),
        "attempt_number": latest_attempt.attempt_number,
        "category": mandate.category or "subscription",
        "pin_reauth_required": mandate.pin_reauth_required,
        "created_at": mandate.created_at.isoformat() if mandate.created_at else latest_attempt.scheduled_at.isoformat(),
    }])

    classifier = get_classifier()
    predictions, confidence_scores = classifier.predict(df)
    explanation = classifier.explain_prediction(df, index=0)

    return {
        "mandate_id": mandate_id,
        "predicted_category": predictions[0],
        "confidence": round(float(confidence_scores[0].max()), 3),
        "shap_values": explanation.get("feature_importance", {}),
        "base_value": explanation.get("base_value", 0.0),
        "feature_importance": explanation.get("feature_importance", {}),
    }
