"""
Promise-to-Pay Tracker
Tracks customer promises to pay and follows up accordingly
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid

from app.db.models import Mandate, PromiseToPay, PromiseToPayStatus, AuditLog


class PromiseToPayTracker:
    """
    Tracks customer promises to pay and manages follow-up schedule.
    State machine: PENDING → PROMISED → CHECKED_BACK → RECOVERED | ESCALATED
    """

    def __init__(self, db_session):
        """
        Initialize promise-to-pay tracker
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def initiate_promise_tracking(self, mandate_id: str) -> Dict:
        """
        Initiate promise-to-pay tracking for a mandate
        
        Args:
            mandate_id: ID of the mandate to track
            
        Returns:
            Dictionary with tracking status
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        # Check if already tracking
        existing = self.db.query(PromiseToPay).filter(
            PromiseToPay.mandate_id == mandate_id
        ).first()
        
        if existing:
            return {
                "action": "already_tracking",
                "mandate_id": mandate_id,
                "current_status": existing.status.value
            }

        # Create new promise-to-pay record
        promise = PromiseToPay(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            status=PromiseToPayStatus.PENDING,
            created_at=datetime.utcnow()
        )
        
        self.db.add(promise)
        self.db.commit()

        # Log audit event
        self._log_audit_event(
            mandate_id=mandate_id,
            event_type="PROMISE_TRACKING_INITIATED",
            event_data={"promise_id": promise.id},
            reason="Promise-to-pay tracking initiated",
            actor="PromiseToPayTracker"
        )

        return {
            "action": "tracking_initiated",
            "mandate_id": mandate_id,
            "promise_id": promise.id,
            "status": PromiseToPayStatus.PENDING.value
        }

    def record_promise(self, mandate_id: str, promised_amount: float, 
                      promised_date: datetime) -> Dict:
        """
        Record customer's promise to pay
        
        Args:
            mandate_id: ID of the mandate
            promised_amount: Amount customer promised to pay
            promised_date: Date customer promised to pay by
            
        Returns:
            Dictionary with recorded promise details
        """
        promise = self.db.query(PromiseToPay).filter(
            PromiseToPay.mandate_id == mandate_id
        ).first()
        
        if not promise:
            raise ValueError(f"No active promise tracking for mandate {mandate_id}")

        # Update promise record
        promise.status = PromiseToPayStatus.PROMISED
        promise.promised_amount = promised_amount
        promise.promised_date = promised_date
        promise.updated_at = datetime.utcnow()

        # Schedule check-back for promised date
        promise.check_back_scheduled_at = promised_date + timedelta(days=1)  # Check back day after promised date

        self.db.commit()

        # Log audit event
        self._log_audit_event(
            mandate_id=mandate_id,
            event_type="PROMISE_RECORDED",
            event_data={
                "promised_amount": promised_amount,
                "promised_date": promised_date.isoformat(),
                "check_back_scheduled": promise.check_back_scheduled_at.isoformat()
            },
            reason=f"Customer promised to pay ₹{promised_amount} by {promised_date}",
            actor="PromiseToPayTracker"
        )

        return {
            "action": "promise_recorded",
            "mandate_id": mandate_id,
            "promised_amount": promised_amount,
            "promised_date": promised_date.isoformat(),
            "check_back_scheduled": promise.check_back_scheduled_at.isoformat()
        }

    def check_back(self, mandate_id: str) -> Dict:
        """
        Perform check-back on promised payment
        
        Args:
            mandate_id: ID of the mandate to check
            
        Returns:
            Dictionary with check-back result
        """
        promise = self.db.query(PromiseToPay).filter(
            PromiseToPay.mandate_id == mandate_id
        ).first()
        
        if not promise:
            raise ValueError(f"No active promise tracking for mandate {mandate_id}")

        if promise.status != PromiseToPayStatus.PROMISED:
            return {
                "action": "invalid_state",
                "mandate_id": mandate_id,
                "current_status": promise.status.value,
                "reason": "Can only check back on PROMISED status"
            }

        # Check if payment was made (simulated)
        payment_made = self._check_payment_status(mandate_id, promise.promised_amount)

        promise.status = PromiseToPayStatus.CHECKED_BACK
        promise.check_back_completed_at = datetime.utcnow()
        promise.updated_at = datetime.utcnow()

        if payment_made:
            promise.status = PromiseToPayStatus.RECOVERED
            self._log_audit_event(
                mandate_id=mandate_id,
                event_type="PAYMENT_RECOVERED",
                event_data={"amount": promise.promised_amount},
                reason=f"Customer successfully paid promised amount ₹{promise.promised_amount}",
                actor="PromiseToPayTracker"
            )
            result = "recovered"
        else:
            promise.status = PromiseToPayStatus.ESCALATED
            self._log_audit_event(
                mandate_id=mandate_id,
                event_type="ESCALATED",
                event_data={"promised_amount": promise.promised_amount},
                reason=f"Customer failed to pay promised amount ₹{promise.promised_amount}. Escalating to manual follow-up.",
                actor="PromiseToPayTracker"
            )
            result = "escalated"

        self.db.commit()

        return {
            "action": "check_back_completed",
            "mandate_id": mandate_id,
            "payment_made": payment_made,
            "result": result,
            "promised_amount": promise.promised_amount
        }

    def send_nudge(self, mandate_id: str) -> Dict:
        """
        Send nudge to customer about upcoming payment
        
        Args:
            mandate_id: ID of the mandate
            
        Returns:
            Dictionary with nudge details
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        if not mandate.consent_for_outreach:
            return {
                "action": "nudge_skipped",
                "mandate_id": mandate_id,
                "reason": "No consent for outreach"
            }

        promise = self.db.query(PromiseToPay).filter(
            PromiseToPay.mandate_id == mandate_id
        ).first()
        
        if not promise:
            return {
                "action": "nudge_skipped",
                "mandate_id": mandate_id,
                "reason": "No active promise tracking"
            }

        # Record nudge sent
        promise.nudge_sent_at = datetime.utcnow()
        promise.updated_at = datetime.utcnow()

        self.db.commit()

        # Log audit event
        self._log_audit_event(
            mandate_id=mandate_id,
            event_type="NUDGE_SENT",
            event_data={"nudge_sent_at": promise.nudge_sent_at.isoformat()},
            reason="Payment reminder nudge sent to customer",
            actor="PromiseToPayTracker"
        )

        return {
            "action": "nudge_sent",
            "mandate_id": mandate_id,
            "nudge_sent_at": promise.nudge_sent_at.isoformat()
        }

    def get_promise_status(self, mandate_id: str) -> Dict:
        """
        Get current promise-to-pay status for a mandate
        
        Args:
            mandate_id: ID of the mandate
            
        Returns:
            Dictionary with current status
        """
        promise = self.db.query(PromiseToPay).filter(
            PromiseToPay.mandate_id == mandate_id
        ).first()
        
        if not promise:
            return {
                "mandate_id": mandate_id,
                "tracking": False,
                "status": None
            }

        return {
            "mandate_id": mandate_id,
            "tracking": True,
            "status": promise.status.value,
            "promised_amount": promise.promised_amount,
            "promised_date": promise.promised_date.isoformat() if promise.promised_date else None,
            "nudge_sent_at": promise.nudge_sent_at.isoformat() if promise.nudge_sent_at else None,
            "check_back_scheduled_at": promise.check_back_scheduled_at.isoformat() if promise.check_back_scheduled_at else None,
            "check_back_completed_at": promise.check_back_completed_at.isoformat() if promise.check_back_completed_at else None
        }

    def _check_payment_status(self, mandate_id: str, expected_amount: float) -> bool:
        """
        Check if payment was made (simulated)
        
        Args:
            mandate_id: ID of the mandate
            expected_amount: Expected payment amount
            
        Returns:
            True if payment was made, False otherwise
        """
        # In real system, would check actual payment records
        # For simulation, use random
        import random
        return random.random() < 0.7  # 70% chance customer kept promise

    def _log_audit_event(self, mandate_id: str, event_type: str, event_data: Dict,
                       reason: str, actor: str):
        """Log event to audit trail"""
        import json
        
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type=event_type,
            event_data=json.dumps(event_data),
            reason=reason,
            actor=actor,
            timestamp=datetime.utcnow(),
            compliant=True
        )
        
        self.db.add(audit_log)


if __name__ == "__main__":
    print("Promise-to-Pay Tracker Module")
    print("This agent tracks customer promises to pay and manages follow-up schedule.")
