"""
Recovery API Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Optional
from datetime import datetime

from app.db import get_db
from app.db.models import FailureCategory
from app.agents import RecoveryAgent, PortabilityGuardAgent, PromiseToPayTracker
from pydantic import BaseModel


router = APIRouter(prefix="/recovery", tags=["recovery"])


class RecoveryRequest(BaseModel):
    mandate_id: str
    failure_category: Optional[FailureCategory] = None
    confidence: Optional[float] = None


class PortabilityCheckRequest(BaseModel):
    mandate_id: str


class PromiseRequest(BaseModel):
    mandate_id: str
    promised_amount: float
    promised_date: datetime


@router.post("/process")
def process_failed_mandate(request: RecoveryRequest, db: Session = Depends(get_db)):
    """Process a failed mandate through the recovery state machine"""
    try:
        recovery_agent = RecoveryAgent(db)
        result = recovery_agent.process_failed_mandate(
            mandate_id=request.mandate_id,
            failure_category=request.failure_category,
            confidence=request.confidence
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portability/check")
def check_portability(request: PortabilityCheckRequest, db: Session = Depends(get_db)):
    """Check mandate portability status"""
    try:
        portability_agent = PortabilityGuardAgent(db)
        result = portability_agent.check_portability_status(request.mandate_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portability/record")
def record_portability(mandate_id: str, new_psp_app: str, db: Session = Depends(get_db)):
    """Record a portability event"""
    try:
        portability_agent = PortabilityGuardAgent(db)
        result = portability_agent.record_portability_event(mandate_id, new_psp_app)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promise/initiate")
def initiate_promise_tracking(mandate_id: str, db: Session = Depends(get_db)):
    """Initiate promise-to-pay tracking"""
    try:
        promise_tracker = PromiseToPayTracker(db)
        result = promise_tracker.initiate_promise_tracking(mandate_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promise/record")
def record_promise(request: PromiseRequest, db: Session = Depends(get_db)):
    """Record customer's promise to pay"""
    try:
        promise_tracker = PromiseToPayTracker(db)
        result = promise_tracker.record_promise(
            mandate_id=request.mandate_id,
            promised_amount=request.promised_amount,
            promised_date=request.promised_date
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promise/checkback")
def check_back_promise(mandate_id: str, db: Session = Depends(get_db)):
    """Perform check-back on promised payment"""
    try:
        promise_tracker = PromiseToPayTracker(db)
        result = promise_tracker.check_back(mandate_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/promise/status/{mandate_id}")
def get_promise_status(mandate_id: str, db: Session = Depends(get_db)):
    """Get promise-to-pay status for a mandate"""
    try:
        promise_tracker = PromiseToPayTracker(db)
        result = promise_tracker.get_promise_status(mandate_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promise/nudge")
def send_nudge(mandate_id: str, db: Session = Depends(get_db)):
    """Send nudge to customer about upcoming payment"""
    try:
        promise_tracker = PromiseToPayTracker(db)
        result = promise_tracker.send_nudge(mandate_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
