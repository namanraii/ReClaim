"""
Mandate API Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import uuid

from app.db import get_db
from app.db.models import Mandate, MandateStatus
from pydantic import BaseModel


router = APIRouter(prefix="/mandates", tags=["mandates"])


class MandateCreate(BaseModel):
    customer_vpa: str
    merchant_id: str
    bank_code: str
    psp_app: str
    amount: float
    frequency: str
    category: str = "subscription"
    consent_for_outreach: bool = True


class MandateResponse(BaseModel):
    id: str
    customer_vpa: str
    merchant_id: str
    bank_code: str
    psp_app: str
    amount: float
    frequency: str
    status: str
    created_at: datetime
    expires_at: datetime
    pin_reauth_required: bool
    consent_for_outreach: bool

    class Config:
        from_attributes = True


@router.post("/", response_model=MandateResponse)
def create_mandate(mandate: MandateCreate, db: Session = Depends(get_db)):
    """Create a new mandate"""
    # Check PIN re-auth requirement
    from app.compliance import NPCIComplianceEngine
    pin_reauth_required = NPCIComplianceEngine.requires_pin_reauth(mandate.amount, mandate.category)

    new_mandate = Mandate(
        id=str(uuid.uuid4()),
        customer_vpa=mandate.customer_vpa,
        merchant_id=mandate.merchant_id,
        bank_code=mandate.bank_code,
        psp_app=mandate.psp_app,
        amount=mandate.amount,
        frequency=mandate.frequency,
        status=MandateStatus.ACTIVE,
        pin_reauth_required=pin_reauth_required,
        consent_for_outreach=mandate.consent_for_outreach,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow()  # Will be set properly in production
    )

    db.add(new_mandate)
    db.commit()
    db.refresh(new_mandate)

    return new_mandate


@router.get("/", response_model=List[MandateResponse])
def list_mandates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all mandates"""
    mandates = db.query(Mandate).offset(skip).limit(limit).all()
    return mandates


@router.get("/{mandate_id}", response_model=MandateResponse)
def get_mandate(mandate_id: str, db: Session = Depends(get_db)):
    """Get a specific mandate"""
    mandate = db.query(Mandate).filter(Mandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return mandate


@router.put("/{mandate_id}/status")
def update_mandate_status(mandate_id: str, status: MandateStatus, db: Session = Depends(get_db)):
    """Update mandate status"""
    mandate = db.query(Mandate).filter(Mandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    mandate.status = status
    db.commit()

    return {"message": "Status updated successfully", "status": status.value}
