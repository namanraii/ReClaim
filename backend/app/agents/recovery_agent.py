"""
Constraint-Aware Recovery Agent
Implements state machine for mandate recovery with NPCI compliance enforcement
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum
import uuid

from app.compliance import NPCIComplianceEngine, ComplianceViolationType
from app.db.models import (
    Mandate, DebitAttempt, FailureEvent, RecoveryOutcome, 
    RecoveryState, FailureCategory
)


class RecoveryAgent:
    """
    Constraint-Aware Recovery Agent that enforces NPCI rules deterministically
    while using ML to prioritize compliant retry slots.
    
    State Machine: FAILED → DIAGNOSED → RETRY_SCHEDULED → RETRYING → RECOVERED | EXHAUSTED | NEEDS_USER_ACTION
    """

    def __init__(self, db_session):
        """
        Initialize recovery agent
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self.compliance_engine = NPCIComplianceEngine()

    def process_failed_mandate(self, mandate_id: str, failure_category: FailureCategory,
                              confidence: float) -> Dict:
        """
        Process a failed mandate through the recovery state machine
        
        Args:
            mandate_id: ID of the failed mandate
            failure_category: Classified failure category
            confidence: Classification confidence score
            
        Returns:
            Dictionary with recovery action and next state
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        # Get or create recovery outcome
        recovery_outcome = self.db.query(RecoveryOutcome).filter(
            RecoveryOutcome.mandate_id == mandate_id
        ).first()
        
        if not recovery_outcome:
            recovery_outcome = RecoveryOutcome(
                id=str(uuid.uuid4()),
                mandate_id=mandate_id,
                state=RecoveryState.FAILED,
                recovery_attempts=0
            )
            self.db.add(recovery_outcome)

        # State machine transitions
        if recovery_outcome.state == RecoveryState.FAILED:
            return self._transition_to_diagnosed(recovery_outcome, mandate, failure_category, confidence)
        
        elif recovery_outcome.state == RecoveryState.DIAGNOSED:
            return self._transition_to_retry_scheduled(recovery_outcome, mandate, failure_category)
        
        elif recovery_outcome.state == RecoveryState.RETRY_SCHEDULED:
            return self._transition_to_retrying(recovery_outcome, mandate)
        
        elif recovery_outcome.state == RecoveryState.RETRYING:
            return self._evaluate_retry_result(recovery_outcome, mandate)
        
        elif recovery_outcome.state in [RecoveryState.RECOVERED, RecoveryState.EXHAUSTED, 
                                        RecoveryState.NEEDS_USER_ACTION]:
            return {"action": "no_action", "reason": f"Terminal state: {recovery_outcome.state}"}
        
        else:
            return {"action": "error", "reason": f"Unknown state: {recovery_outcome.state}"}

    def _transition_to_diagnosed(self, recovery_outcome: RecoveryOutcome, mandate: Mandate,
                               failure_category: FailureCategory, confidence: float) -> Dict:
        """Transition from FAILED to DIAGNOSED state"""
        recovery_outcome.state = RecoveryState.DIAGNOSED
        recovery_outcome.updated_at = datetime.utcnow()
        
        # Log audit entry
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="CLASSIFICATION",
            event_data={"category": failure_category.value, "confidence": confidence},
            reason=f"Root cause classified as {failure_category.value} with {confidence:.2f} confidence",
            actor="RecoveryAgent"
        )
        
        self.db.commit()
        
        return {
            "action": "diagnosed",
            "next_state": RecoveryState.DIAGNOSED,
            "failure_category": failure_category.value,
            "confidence": confidence
        }

    def _transition_to_retry_scheduled(self, recovery_outcome: RecoveryOutcome, mandate: Mandate,
                                      failure_category: FailureCategory) -> Dict:
        """Transition from DIAGNOSED to RETRY_SCHEDULED state"""
        
        # Check if we've exhausted retry attempts
        if recovery_outcome.recovery_attempts >= self.compliance_engine.MAX_RETRY_ATTEMPTS:
            return self._transition_to_exhausted(recovery_outcome, mandate, "Max retry attempts reached")

        # Get next compliant retry window
        retry_window = self._get_next_compliant_retry_window(mandate, recovery_outcome.recovery_attempts + 1)
        
        if not retry_window:
            return self._transition_to_exhausted(recovery_outcome, mandate, "No compliant retry window available")

        window_start, window_end, complies, violations = retry_window

        if not complies:
            return self._transition_to_exhausted(recovery_outcome, mandate, f"Compliance violations: {violations}")

        recovery_outcome.state = RecoveryState.RETRY_SCHEDULED
        recovery_outcome.updated_at = datetime.utcnow()
        
        # Log audit entry
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="RETRY_SCHEDULED",
            event_data={
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "attempt_number": recovery_outcome.recovery_attempts + 1
            },
            reason=f"Retry scheduled for {window_start} (compliant with NPCI rules)",
            actor="RecoveryAgent",
            compliant=True
        )
        
        self.db.commit()
        
        return {
            "action": "retry_scheduled",
            "next_state": RecoveryState.RETRY_SCHEDULED,
            "retry_window_start": window_start.isoformat(),
            "retry_window_end": window_end.isoformat(),
            "attempt_number": recovery_outcome.recovery_attempts + 1
        }

    def _transition_to_retrying(self, recovery_outcome: RecoveryOutcome, mandate: Mandate) -> Dict:
        """Transition from RETRY_SCHEDULED to RETRYING state"""
        recovery_outcome.state = RecoveryState.RETRYING
        recovery_outcome.recovery_attempts += 1
        recovery_outcome.updated_at = datetime.utcnow()
        
        # Log audit entry
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="RETRYING",
            event_data={"attempt_number": recovery_outcome.recovery_attempts},
            reason=f"Executing retry attempt {recovery_outcome.recovery_attempts}",
            actor="RecoveryAgent"
        )
        
        self.db.commit()
        
        return {
            "action": "retrying",
            "next_state": RecoveryState.RETRYING,
            "attempt_number": recovery_outcome.recovery_attempts
        }

    def _evaluate_retry_result(self, recovery_outcome: RecoveryOutcome, mandate: Mandate) -> Dict:
        """Evaluate result of retry attempt and transition to appropriate state"""
        
        # In a real system, this would check the actual debit result
        # For now, we'll simulate based on failure category
        
        # If retry was successful (simulated)
        if self._simulate_retry_success(mandate):
            return self._transition_to_recovered(recovery_outcome, mandate)
        
        # If retry failed but more attempts available
        if recovery_outcome.recovery_attempts < self.compliance_engine.MAX_RETRY_ATTEMPTS:
            recovery_outcome.state = RecoveryState.DIAGNOSED  # Go back for re-evaluation
            recovery_outcome.updated_at = datetime.utcnow()
            self.db.commit()
            
            return {
                "action": "retry_failed",
                "next_state": RecoveryState.DIAGNOSED,
                "reason": "Retry failed, re-evaluating"
            }
        
        # Exhausted all attempts
        return self._transition_to_exhausted(recovery_outcome, mandate, "All retry attempts exhausted")

    def _transition_to_recovered(self, recovery_outcome: RecoveryOutcome, mandate: Mandate) -> Dict:
        """Transition to RECOVERED state"""
        recovery_outcome.state = RecoveryState.RECOVERED
        recovery_outcome.final_amount_recovered = mandate.amount
        recovery_outcome.final_outcome = "Recovery successful"
        recovery_outcome.updated_at = datetime.utcnow()
        
        # Log audit entry
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="RECOVERED",
            event_data={"amount_recovered": mandate.amount},
            reason=f"Successfully recovered ₹{mandate.amount}",
            actor="RecoveryAgent"
        )
        
        self.db.commit()
        
        return {
            "action": "recovered",
            "next_state": RecoveryState.RECOVERED,
            "amount_recovered": mandate.amount
        }

    def _transition_to_exhausted(self, recovery_outcome: RecoveryOutcome, mandate: Mandate, 
                                reason: str) -> Dict:
        """Transition to EXHAUSTED state (stopping rule)"""
        recovery_outcome.state = RecoveryState.EXHAUSTED
        recovery_outcome.final_outcome = reason
        recovery_outcome.updated_at = datetime.utcnow()
        
        # Log audit entry
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="STOP",
            event_data={"reason": reason},
            reason=f"Stopping rule triggered: {reason}",
            actor="RecoveryAgent"
        )
        
        self.db.commit()
        
        return {
            "action": "exhausted",
            "next_state": RecoveryState.EXHAUSTED,
            "reason": reason
        }

    def _get_next_compliant_retry_window(self, mandate: Mandate, attempt_number: int) -> Optional[Tuple]:
        """
        Get next compliant retry window based on NPCI rules
        
        Returns:
            Tuple of (window_start, window_end, is_compliant, violations) or None
        """
        from_time = datetime.utcnow() + timedelta(minutes=5)  # Minimum 5 minutes from now
        
        # Get next valid execution window
        window_start, window_end = self.compliance_engine.get_next_valid_execution_window(from_time)
        
        # Validate against all NPCI rules
        is_compliant, violations = self.compliance_engine.validate_retry_schedule(
            scheduled_time=window_start,
            attempt_number=attempt_number,
            mandate_amount=mandate.amount,
            mandate_category=None,  # Would need to be stored in mandate
            last_port_date=mandate.portability_cooldown_until
        )
        
        return (window_start, window_end, is_compliant, violations)

    def _simulate_retry_success(self, mandate: Mandate) -> bool:
        """
        Simulate retry success (in real system, this would check actual debit result)
        This is a placeholder for demonstration
        """
        import random
        # Simulate 60% success rate for retries
        return random.random() < 0.6

    def _log_audit_event(self, mandate_id: str, event_type: str, event_data: Dict,
                        reason: str, actor: str, compliant: bool = True, 
                        compliance_notes: Optional[str] = None):
        """Log event to audit trail"""
        from app.db.models import AuditLog
        import json
        
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type=event_type,
            event_data=json.dumps(event_data),
            reason=reason,
            actor=actor,
            timestamp=datetime.utcnow(),
            compliant=compliant,
            compliance_notes=compliance_notes
        )
        
        self.db.add(audit_log)


if __name__ == "__main__":
    print("Recovery Agent Module")
    print("This agent implements the constraint-aware recovery state machine with NPCI compliance enforcement.")
