"""
Dashboard API Routes
Provides metrics and data for the frontend dashboard
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime, timedelta
import json

from app.db import get_db
from app.db.models import Mandate, DebitAttempt, FailureEvent, RecoveryOutcome, AuditLog
from sqlalchemy import func


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """Get overall dashboard metrics"""
    try:
        # Total mandates
        total_mandates = db.query(Mandate).count()
        
        # Active mandates
        active_mandates = db.query(Mandate).filter(Mandate.status == "ACTIVE").count()
        
        # Total debit attempts
        total_attempts = db.query(DebitAttempt).count()
        
        # Successful attempts
        successful_attempts = db.query(DebitAttempt).filter(DebitAttempt.status == "SUCCESS").count()
        
        # Failed attempts
        failed_attempts = db.query(DebitAttempt).filter(DebitAttempt.status == "FAILED").count()
        
        # Recovery outcomes
        recovered = db.query(RecoveryOutcome).filter(RecoveryOutcome.state == "RECOVERED").count()
        exhausted = db.query(RecoveryOutcome).filter(RecoveryOutcome.state == "EXHAUSTED").count()
        
        # Calculate success rate
        success_rate = (successful_attempts / total_attempts * 100) if total_attempts > 0 else 0
        
        # Calculate recovery rate
        total_outcomes = db.query(RecoveryOutcome).count()
        recovery_rate = (recovered / total_outcomes * 100) if total_outcomes > 0 else 0

        return {
            "total_mandates": total_mandates,
            "active_mandates": active_mandates,
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": round(success_rate, 2),
            "recovered": recovered,
            "exhausted": exhausted,
            "recovery_rate": round(recovery_rate, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery-rate")
def get_recovery_rate_trend(days: int = 30, db: Session = Depends(get_db)):
    """Get recovery rate trend over time"""
    try:
        # For demo, return mock trend data
        # In production, this would query actual historical data
        trend_data = []
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=days - i)
            trend_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "recovery_rate": 70 + (i % 10)  # Mock data
            })

        return {
            "period_days": days,
            "trend": trend_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failure-breakdown")
def get_failure_breakdown(db: Session = Depends(get_db)):
    """Get failure category breakdown"""
    try:
        # Count failures by category
        failure_counts = db.query(FailureEvent.category, func.count(FailureEvent.id)).group_by(FailureEvent.category).all()
        
        breakdown = []
        for category, count in failure_counts:
            breakdown.append({
                "category": category,
                "count": count
            })

        return {
            "breakdown": breakdown
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bank-performance")
def get_bank_performance(db: Session = Depends(get_db)):
    """Get performance metrics by bank"""
    try:
        # Get bank success rates
        # For demo, return mock data
        bank_performance = [
            {"bank_code": "SBI", "success_rate": 95.2, "total_attempts": 1500},
            {"bank_code": "HDFC", "success_rate": 92.1, "total_attempts": 1200},
            {"bank_code": "ICICI", "success_rate": 90.5, "total_attempts": 1100},
            {"bank_code": "AXIS", "success_rate": 88.3, "total_attempts": 900},
            {"bank_code": "KOTAK", "success_rate": 87.1, "total_attempts": 850}
        ]

        return {
            "bank_performance": bank_performance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revenue-recovered")
def get_revenue_recovered(db: Session = Depends(get_db)):
    """Get total revenue recovered"""
    try:
        # Sum recovered amounts
        recovered_outcomes = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.state == "RECOVERED",
            RecoveryOutcome.final_amount_recovered.isnot(None)
        ).all()
        
        total_recovered = sum(outcome.final_amount_recovered for outcome in recovered_outcomes)

        return {
            "total_recovered": total_recovered,
            "currency": "INR",
            "recovered_transactions": len(recovered_outcomes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mandate/{mandate_id}/explain")
def get_mandate_explanation(mandate_id: str, db: Session = Depends(get_db)):
    """Get detailed explanation for a specific mandate"""
    try:
        mandate = db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise HTTPException(status_code=404, detail="Mandate not found")

        # Get recent debit attempts
        recent_attempts = db.query(DebitAttempt).filter(
            DebitAttempt.mandate_id == mandate_id
        ).order_by(DebitAttempt.scheduled_at.desc()).limit(5).all()

        # Get failure events
        failure_events = db.query(FailureEvent).join(DebitAttempt).filter(
            DebitAttempt.mandate_id == mandate_id
        ).all()

        # Get recovery outcome
        recovery_outcome = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.mandate_id == mandate_id
        ).first()

        return {
            "mandate": {
                "id": mandate.id,
                "customer_vpa": mandate.customer_vpa,
                "bank_code": mandate.bank_code,
                "psp_app": mandate.psp_app,
                "amount": mandate.amount,
                "status": mandate.status.value
            },
            "recent_attempts": [
                {
                    "id": attempt.id,
                    "scheduled_at": attempt.scheduled_at.isoformat(),
                    "status": attempt.status.value,
                    "attempt_number": attempt.attempt_number
                }
                for attempt in recent_attempts
            ],
            "failure_events": [
                {
                    "category": event.category.value,
                    "confidence": event.confidence,
                    "detected_at": event.detected_at.isoformat()
                }
                for event in failure_events
            ],
            "recovery_outcome": {
                "state": recovery_outcome.state.value if recovery_outcome else None,
                "recovery_attempts": recovery_outcome.recovery_attempts if recovery_outcome else 0,
                "final_amount_recovered": recovery_outcome.final_amount_recovered if recovery_outcome else None
            } if recovery_outcome else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log")
def get_audit_log(mandate_id: str = None, limit: int = 100, db: Session = Depends(get_db)):
    """Get audit log entries"""
    try:
        query = db.query(AuditLog)
        
        if mandate_id:
            query = query.filter(AuditLog.mandate_id == mandate_id)
        
        audit_entries = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

        return {
            "audit_log": [
                {
                    "id": entry.id,
                    "mandate_id": entry.mandate_id,
                    "event_type": entry.event_type,
                    "reason": entry.reason,
                    "actor": entry.actor,
                    "timestamp": entry.timestamp.isoformat(),
                    "compliant": entry.compliant,
                    "event_data": json.loads(entry.event_data) if entry.event_data else None
                }
                for entry in audit_entries
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exceptions")
def get_exception_list(db: Session = Depends(get_db)):
    """Get list of mandates that could not be recovered"""
    try:
        exhausted_outcomes = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.state == "EXHAUSTED"
        ).all()

        exceptions = []
        for outcome in exhausted_outcomes:
            mandate = db.query(Mandate).filter(Mandate.id == outcome.mandate_id).first()
            if mandate:
                exceptions.append({
                    "mandate_id": mandate.id,
                    "customer_vpa": mandate.customer_vpa,
                    "bank_code": mandate.bank_code,
                    "amount": mandate.amount,
                    "reason": outcome.final_outcome,
                    "recovery_attempts": outcome.recovery_attempts
                })

        return {
            "exceptions": exceptions,
            "total_exceptions": len(exceptions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail(str(e)))
