"""
Dashboard API Routes — real aggregates from the database.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import json

from app.db import get_db
from app.db.models import (
    Mandate, MandateStatus, DebitAttempt, DebitStatus, FailureEvent,
    RecoveryOutcome, RecoveryState, AuditLog,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """Get overall dashboard metrics from live data."""
    try:
        total_mandates = db.query(Mandate).count()
        active_mandates = db.query(Mandate).filter(Mandate.status == MandateStatus.ACTIVE).count()
        total_attempts = db.query(DebitAttempt).count()
        successful = db.query(DebitAttempt).filter(DebitAttempt.status == DebitStatus.SUCCESS).count()
        failed = db.query(DebitAttempt).filter(DebitAttempt.status == DebitStatus.FAILED).count()
        recovered = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.state == RecoveryState.RECOVERED
        ).count()
        exhausted = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.state == RecoveryState.EXHAUSTED
        ).count()
        total_outcomes = recovered + exhausted
        recovery_rate = round(recovered / total_outcomes * 100, 1) if total_outcomes else 0.0
        success_rate = round(successful / total_attempts * 100, 1) if total_attempts else 0.0

        return {
            "total_mandates": total_mandates,
            "active_mandates": active_mandates,
            "total_attempts": total_attempts,
            "successful_attempts": successful,
            "failed_attempts": failed,
            "success_rate": success_rate,
            "recovered": recovered,
            "exhausted": exhausted,
            "recovery_rate": recovery_rate,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery-rate")
def get_recovery_rate_trend(days: int = 30, db: Session = Depends(get_db)):
    """Get recovery rate trend from recovery outcomes."""
    try:
        trend_data = []
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=days - i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            recovered = db.query(RecoveryOutcome).filter(
                RecoveryOutcome.state == RecoveryState.RECOVERED,
                RecoveryOutcome.updated_at >= day_start,
                RecoveryOutcome.updated_at < day_end,
            ).count()
            total = db.query(RecoveryOutcome).filter(
                RecoveryOutcome.updated_at >= day_start,
                RecoveryOutcome.updated_at < day_end,
            ).count()
            rate = round(recovered / total * 100, 1) if total else 0.0
            trend_data.append({"date": day_start.strftime("%Y-%m-%d"), "recovery_rate": rate})

        return {"period_days": days, "trend": trend_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failure-breakdown")
def get_failure_breakdown(db: Session = Depends(get_db)):
    """Get failure category breakdown from failure events."""
    try:
        rows = (
            db.query(FailureEvent.category, func.count(FailureEvent.id))
            .group_by(FailureEvent.category)
            .all()
        )
        breakdown = [{"category": cat.value, "count": count} for cat, count in rows]
        return {"breakdown": breakdown}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bank-performance")
def get_bank_performance(db: Session = Depends(get_db)):
    """Get performance metrics by bank from debit attempts."""
    try:
        banks = db.query(Mandate.bank_code).distinct().all()
        bank_performance = []
        for (bank_code,) in banks:
            mandate_ids = [m.id for m in db.query(Mandate.id).filter(Mandate.bank_code == bank_code).all()]
            if not mandate_ids:
                continue
            total = db.query(DebitAttempt).filter(DebitAttempt.mandate_id.in_(mandate_ids)).count()
            success = db.query(DebitAttempt).filter(
                DebitAttempt.mandate_id.in_(mandate_ids),
                DebitAttempt.status == DebitStatus.SUCCESS,
            ).count()
            rate = round(success / total * 100, 1) if total else 0.0
            bank_performance.append({
                "bank_code": bank_code,
                "success_rate": rate,
                "total_attempts": total,
            })
        bank_performance.sort(key=lambda x: x["success_rate"], reverse=True)
        return {"bank_performance": bank_performance[:10]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revenue-recovered")
def get_revenue_recovered(db: Session = Depends(get_db)):
    """Get total revenue recovered from recovery outcomes."""
    try:
        total = db.query(func.sum(RecoveryOutcome.final_amount_recovered)).filter(
            RecoveryOutcome.state == RecoveryState.RECOVERED
        ).scalar() or 0.0
        count = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.state == RecoveryState.RECOVERED
        ).count()
        return {
            "total_recovered": round(float(total), 2),
            "currency": "INR",
            "recovered_transactions": count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mandate/{mandate_id}/explain")
def get_mandate_explanation(mandate_id: str, db: Session = Depends(get_db)):
    """Get detailed explanation for a specific mandate."""
    try:
        mandate = db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise HTTPException(status_code=404, detail="Mandate not found")

        attempts = (
            db.query(DebitAttempt)
            .filter(DebitAttempt.mandate_id == mandate_id)
            .order_by(DebitAttempt.scheduled_at.desc())
            .limit(5)
            .all()
        )
        failure_events = []
        for attempt in attempts:
            for fe in attempt.failure_events:
                shap = {}
                if fe.shap_explanation:
                    try:
                        shap = json.loads(fe.shap_explanation.replace("'", '"'))
                    except (json.JSONDecodeError, TypeError):
                        shap = {"raw": fe.shap_explanation}
                failure_events.append({
                    "category": fe.category.value,
                    "confidence": fe.confidence,
                    "detected_at": fe.detected_at.isoformat() if fe.detected_at else None,
                    "shap_explanation": shap,
                })

        recovery = db.query(RecoveryOutcome).filter(
            RecoveryOutcome.mandate_id == mandate_id
        ).first()

        return {
            "mandate": {
                "id": mandate.id,
                "customer_vpa": mandate.customer_vpa,
                "bank_code": mandate.bank_code,
                "psp_app": mandate.psp_app,
                "amount": mandate.amount,
                "status": mandate.status.value,
            },
            "recent_attempts": [
                {
                    "id": a.id,
                    "scheduled_at": a.scheduled_at.isoformat(),
                    "status": a.status.value,
                    "attempt_number": a.attempt_number,
                }
                for a in attempts
            ],
            "failure_events": failure_events,
            "recovery_outcome": {
                "state": recovery.state.value if recovery else "FAILED",
                "recovery_attempts": recovery.recovery_attempts if recovery else 0,
                "final_amount_recovered": recovery.final_amount_recovered if recovery else None,
            } if recovery else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log")
def get_audit_log(mandate_id: str = None, limit: int = 100, db: Session = Depends(get_db)):
    """Get audit log entries from the database."""
    try:
        query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
        if mandate_id:
            query = query.filter(AuditLog.mandate_id == mandate_id)
        entries = query.limit(limit).all()
        return {
            "audit_log": [
                {
                    "id": e.id,
                    "mandate_id": e.mandate_id,
                    "event_type": e.event_type,
                    "reason": e.reason,
                    "actor": e.actor,
                    "timestamp": e.timestamp.isoformat(),
                    "compliant": e.compliant,
                    "event_data": json.loads(e.event_data) if e.event_data else {},
                }
                for e in entries
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exceptions")
def get_exception_list(db: Session = Depends(get_db)):
    """Get mandates that could not be recovered."""
    try:
        exhausted = (
            db.query(RecoveryOutcome, Mandate)
            .join(Mandate, RecoveryOutcome.mandate_id == Mandate.id)
            .filter(RecoveryOutcome.state == RecoveryState.EXHAUSTED)
            .limit(50)
            .all()
        )
        exceptions = [
            {
                "mandate_id": m.id,
                "customer_vpa": m.customer_vpa,
                "bank_code": m.bank_code,
                "amount": m.amount,
                "reason": ro.final_outcome or "Recovery exhausted",
                "recovery_attempts": ro.recovery_attempts,
            }
            for ro, m in exhausted
        ]
        return {"exceptions": exceptions, "total_exceptions": len(exceptions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
