"""
Compliance API Routes
Authoritative Policy Enforcement and Regulatory Rule Registry Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.db import get_db
from app.compliance import NPCIComplianceEngine, ComplianceViolationType, ComplianceApprovalToken
from app.compliance.registry import REGULATORY_RULE_REGISTRY, list_all_rules


router = APIRouter(prefix="/compliance", tags=["compliance"])


class ComplianceCheckRequest(BaseModel):
    scheduled_time: str
    attempt_number: int
    mandate_amount: float
    mandate_category: Optional[str] = None
    last_port_date: Optional[str] = None


class ComplianceTokenRequest(BaseModel):
    action_name: str
    mandate_id: str
    attempt_number: int
    mandate_amount: float
    scheduled_time: str
    mandate_category: Optional[str] = None
    last_port_date: Optional[str] = None
    consent_for_outreach: bool = True


class ExecutionWindowRequest(BaseModel):
    from_time: str


@router.get("/registry")
def get_regulatory_rule_registry():
    """Returns the complete authoritative Regulatory Rule Registry with circular citations"""
    return {"rules": [r.dict() for r in list_all_rules()]}


@router.post("/token", response_model=ComplianceApprovalToken)
def issue_compliance_token(request: ComplianceTokenRequest):
    """
    Issues a cryptographically verifiable / structured ComplianceApprovalToken.
    Requires action parameters and validates across all NPCI & RBI rules.
    """
    try:
        scheduled_time = datetime.fromisoformat(request.scheduled_time)
        last_port_date = datetime.fromisoformat(request.last_port_date) if request.last_port_date else None

        token = NPCIComplianceEngine.issue_compliance_token(
            action_name=request.action_name,
            mandate_id=request.mandate_id,
            attempt_number=request.attempt_number,
            mandate_amount=request.mandate_amount,
            scheduled_time=scheduled_time,
            mandate_category=request.mandate_category,
            last_port_date=last_port_date,
            consent_for_outreach=request.consent_for_outreach
        )
        return token
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """Get legacy rule summary"""
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
