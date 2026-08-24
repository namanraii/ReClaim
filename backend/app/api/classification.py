"""
Classification API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session
from typing import Dict, List
import pandas as pd
import io

from app.db import get_db
from app.models import FailureClassifier, ProbabilityCalibrator
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
    data_file: str  # Path to training data CSV
    model_type: str = "xgboost"


@router.post("/predict")
def predict_failure(request: ClassificationRequest, db: Session = Depends(get_db)):
    """Predict failure category for a mandate attempt"""
    try:
        # Load trained model (in production, this would be cached)
        classifier = FailureClassifier(model_type="xgboost")
        
        # For demo, we'll return a mock prediction
        # In production, load the trained model and make real predictions
        return {
            "mandate_id": request.mandate_id,
            "predicted_category": "LOW_BALANCE",
            "confidence": 0.85,
            "shap_explanation": {
                "day_of_month": 0.4,
                "amount": 0.3,
                "bank_code": 0.2
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train")
def train_classifier(request: TrainRequest, db: Session = Depends(get_db)):
    """Train the failure classifier"""
    try:
        # Load training data
        # In production, this would load from the specified file
        classifier = FailureClassifier(model_type=request.model_type)
        
        # Mock training for demo
        return {
            "message": "Classifier training initiated",
            "model_type": request.model_type,
            "status": "training"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calibrate")
def calibrate_probabilities(db: Session = Depends(get_db)):
    """Calibrate classifier probabilities"""
    try:
        calibrator = ProbabilityCalibrator(method="isotonic")
        
        # Mock calibration for demo
        return {
            "message": "Probability calibration initiated",
            "method": "isotonic",
            "status": "calibrating"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{mandate_id}")
def explain_prediction(mandate_id: str, db: Session = Depends(get_db)):
    """Get SHAP explanation for a prediction"""
    try:
        # Mock explanation for demo
        return {
            "mandate_id": mandate_id,
            "predicted_category": "LOW_BALANCE",
            "confidence": 0.85,
            "shap_values": {
                "day_of_month": 0.4,
                "amount": 0.3,
                "bank_code": 0.2,
                "hour_of_day": 0.1
            },
            "base_value": 0.2,
            "feature_importance": {
                "day_of_month": 0.4,
                "amount": 0.3,
                "bank_code": 0.2,
                "hour_of_day": 0.1
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
