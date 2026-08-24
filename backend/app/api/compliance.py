"""
Compliance API Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime

from app.db import get_db
from app.compliance import NPCIComplianceEngine, ComplianceViolationType
from pydantic import BaseModel


router = APIRouter(prefix="/compliance", tags=["compliance"])


class ComplianceCheckRequest(BaseModel):
    scheduled_time: str
    attempt_number: int
    mandate_amount: float
    mandate_category: str = None
    last_port_date: str = None


class ExecutionWindowRequest(BaseModel):
    from_time: str


@router.post("/validate")
def validate_retry_schedule(request: ComplianceCheckRequest, db: Session = Depends(get_db)):
    """Validate a retry schedule against NPCI rules"""
    try:
        scheduled_time = datetime.fromisoformat(request.scheduled_time)
        last_port_date = datetime.fromisoformat(request.last_port_date) if request.last_port_date else None

        is_compliant, violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=request.attempt_number,
            mandate_amount=request.mandate_amount,
            mandate_category=request.mandate_category,
            last_port_date=last_port_date
        )

        return {
            "is_compliant": is_compliant,
            "violations": [v.value for v in violations],
            "scheduled_time": request.scheduled_time,
            "attempt_number": request.attempt_number
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution-window")
def get_execution_window(request: ExecutionWindowRequest, db: Session = Depends(get_db)):
    """Get next valid execution window"""
    try:
        from_time = datetime.fromisoformat(request.from_time)
        window_start, window_end = NPCIComplianceEngine.get_next_valid_execution_window(from_time)

        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "from_time": request.from_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
def get_compliance_rules(db: Session = Depends(get_db)):
    """Get NPCI compliance rules"""
    return {
        "peak_hours": [
            {"start": "10:00", "end": "13:00"},
            {"start": "17:00", "end": "21:30"}
        ],
        "max_retry_attempts": NPCIComplianceEngine.MAX_RETRY_ATTEMPTS,
        "status_check_cooldown_seconds": NPCIComplianceEngine.STATUS_CHECK_COOLDOWN_SECONDS,
        "portability_cooldown_days": NPCIComplianceEngine.PORTABILITY_COOLDOWN_DAYS,
        "pin_reauth_default_threshold": NPCIComplianceEngine.PIN_REAUTH_DEFAULT_THRESHOLD,
        "pin_reauth_exception_threshold": NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_THRESHOLD,
        "pin_reauth_exception_categories": NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_CATEGORIES
    }


@router.post("/pin-reauth")
def check_pin_reauth(amount: float, category: str = None, db: Session = Depends(get_db)):
    """Check if debit requires PIN re-authentication"""
    requires_reauth = NPCIComplianceEngine.requires_pin_reauth(amount, category)

    return {
        "amount": amount,
        "category": category,
        "requires_pin_reauth": requires_reauth,
        "threshold_used": NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_THRESHOLD if category in NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_CATEGORIES else NPCIComplianceEngine.PIN_REAUTH_DEFAULT_THRESHOLD
    }


@router.post("/portability-cooldown")
def check_portability_cooldown(last_port_date: str, current_date: str = None, db: Session = Depends(get_db)):
    """Check if mandate is within portability cooldown"""
    try:
        last_port = datetime.fromisoformat(last_port_date)
        current = datetime.fromisoformat(current_date) if current_date else datetime.utcnow()

        in_cooldown = NPCIComplianceEngine.is_within_portability_cooldown(last_port, current)

        return {
            "last_port_date": last_port_date,
            "current_date": current.isoformat(),
            "in_cooldown": in_cooldown,
            "cooldown_days": NPCIComplianceEngine.PORTABILITY_COOLDOWN_DAYS
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
