"""
Constraint-Aware Recovery Agent
Implements state machine for mandate recovery with Decision Intelligence & Token-Based Compliance Gate
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
from enum import Enum
import uuid
import json

from app.compliance import NPCIComplianceEngine, ComplianceApprovalToken
from app.models.hybrid_diagnostician import HybridDiagnostician, DiagnosticResult
from app.agents.recovery_planner import RecoveryPlanner, DecisionTrace, RecoveryActionType
from app.db.models import (
    Mandate, DebitAttempt, DebitStatus, FailureEvent, RecoveryOutcome, 
    RecoveryState, FailureCategory, AuditLog
)


class RecoveryAgent:
    """
    Constraint-Aware Recovery Agent that enforces NPCI rules deterministically
    while using Decision Intelligence (ERV) to choose the optimal recovery playbook.
    
    State Machine: FAILED → DIAGNOSED → RETRY_SCHEDULED → RETRYING → RECOVERED | EXHAUSTED | NEEDS_USER_ACTION
    """

    def __init__(self, db_session):
        self.db = db_session
        self.compliance_engine = NPCIComplianceEngine()
        self.diagnostician = HybridDiagnostician()
        self.planner = RecoveryPlanner()

    def process_failed_mandate(
        self,
        mandate_id: str,
        failure_category: Optional[FailureCategory] = None,
        confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Process a failed mandate through the Decision Intelligence pipeline & State Machine.
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        # Fetch recent debit attempts for history context
        attempts = (
            self.db.query(DebitAttempt)
            .filter(DebitAttempt.mandate_id == mandate_id)
            .order_by(DebitAttempt.scheduled_at.desc())
            .limit(6)
            .all()
        )
        latest_attempt = attempts[0] if attempts else None
        
        attempt_dict = {
            "scheduled_at": latest_attempt.scheduled_at.isoformat() if latest_attempt else datetime.utcnow().isoformat(),
            "attempt_number": latest_attempt.attempt_number if latest_attempt else 1,
            "response_code": latest_attempt.response_code if latest_attempt else "U51"
        }
        
        mandate_dict = {
            "id": mandate.id,
            "amount": mandate.amount,
            "bank_code": mandate.bank_code,
            "customer_vpa": mandate.customer_vpa,
            "psp_app": mandate.psp_app,
            "category": mandate.category,
            "frequency": mandate.frequency,
            "consent_for_outreach": mandate.consent_for_outreach,
            "pin_reauth_required": mandate.pin_reauth_required,
            "created_at": mandate.created_at.isoformat() if mandate.created_at else None,
            "last_successful_debit": mandate.last_successful_debit.isoformat() if mandate.last_successful_debit else None,
            "portability_cooldown_until": mandate.portability_cooldown_until.isoformat() if mandate.portability_cooldown_until else None
        }

        history_list = [
            {
                "attempt_number": a.attempt_number,
                "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else "",
                "status": a.status.value,
                "response_code": a.response_code,
                "response_message": a.response_message
            }
            for a in attempts
        ]

        # 1. Run Hybrid 3-Tier Diagnostician
        diagnosis: DiagnosticResult = self.diagnostician.diagnose_failure(
            mandate_dict=mandate_dict,
            attempt_dict=attempt_dict,
            attempts_history=history_list
        )

        from app.models.evidence import build_evidence_packet
        evidence = build_evidence_packet(mandate_dict, attempt_dict, history_list)

        # 2. Run Expected-Revenue Recovery Planner
        decision_trace: DecisionTrace = self.planner.plan_recovery(evidence, diagnosis)

        # 3. Get or create recovery outcome record
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

        # 4. State Machine Transitions with Compliance Gate Verification
        if not decision_trace.compliance_token.approved:
            # Hard Block: Compliance violation encountered
            return self._transition_to_exhausted(
                recovery_outcome,
                mandate,
                reason=f"Compliance Gate Rejection: {decision_trace.compliance_token.rejection_reason}",
                decision_trace=decision_trace
            )

        # Transition to DIAGNOSED
        recovery_outcome.state = RecoveryState.DIAGNOSED
        recovery_outcome.updated_at = datetime.utcnow()

        # Log Diagnostic & Plan Audit Event with Token Citation
        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="AI_DECISION_PLAN",
            event_data=decision_trace.dict(),
            reason=(
                f"Diagnosed as {diagnosis.failure_category} ({diagnosis.resolution_tier}). "
                f"Selected '{decision_trace.selected_action.value}' (ERV: ₹{decision_trace.expected_recovered_revenue:,.0f}). "
                f"Compliance Token: {decision_trace.compliance_token.decision_id} (APPROVED)."
            ),
            actor="RecoveryPlanner",
            compliant=decision_trace.compliance_token.approved,
            compliance_notes=f"Rules verified: {', '.join(decision_trace.compliance_token.rules_checked)}"
        )
        self.db.commit()

        # Schedule or Execute Action
        if decision_trace.selected_action in [
            RecoveryActionType.RETRY_OPTIMAL_WINDOW,
            RecoveryActionType.SALARY_ALIGNED_RETRY,
            RecoveryActionType.SALARY_RETRY_AND_NUDGE
        ]:
            recovery_outcome.state = RecoveryState.RETRY_SCHEDULED
            self.db.commit()
            return {
                "action": decision_trace.selected_action.value,
                "next_state": RecoveryState.RETRY_SCHEDULED.value,
                "decision_trace": decision_trace.dict(),
                "compliance_token": decision_trace.compliance_token.dict()
            }
        elif decision_trace.selected_action == RecoveryActionType.CUSTOMER_NUDGE:
            recovery_outcome.state = RecoveryState.NEEDS_USER_ACTION
            self.db.commit()
            return {
                "action": "customer_nudge_dispatched",
                "next_state": RecoveryState.NEEDS_USER_ACTION.value,
                "decision_trace": decision_trace.dict(),
                "compliance_token": decision_trace.compliance_token.dict()
            }
        elif decision_trace.selected_action == RecoveryActionType.HUMAN_ESCALATION:
            recovery_outcome.state = RecoveryState.NEEDS_USER_ACTION
            self.db.commit()
            return {
                "action": "human_escalation",
                "next_state": RecoveryState.NEEDS_USER_ACTION.value,
                "decision_trace": decision_trace.dict(),
                "compliance_token": decision_trace.compliance_token.dict()
            }
        else:
            return {
                "action": decision_trace.selected_action.value,
                "next_state": recovery_outcome.state.value,
                "decision_trace": decision_trace.dict(),
                "compliance_token": decision_trace.compliance_token.dict()
            }

    def _transition_to_exhausted(
        self,
        recovery_outcome: RecoveryOutcome,
        mandate: Mandate,
        reason: str,
        decision_trace: Optional[DecisionTrace] = None
    ) -> Dict[str, Any]:
        recovery_outcome.state = RecoveryState.EXHAUSTED
        recovery_outcome.final_outcome = reason
        recovery_outcome.updated_at = datetime.utcnow()

        self._log_audit_event(
            mandate_id=mandate.id,
            event_type="COMPLIANCE_BLOCK_STOP",
            event_data=decision_trace.dict() if decision_trace else {"reason": reason},
            reason=f"Stopping rule triggered: {reason}",
            actor="ComplianceGate",
            compliant=False,
            compliance_notes="Hard block enforced by policy engine"
        )
        self.db.commit()

        return {
            "action": "blocked_and_exhausted",
            "next_state": RecoveryState.EXHAUSTED.value,
            "reason": reason,
            "decision_trace": decision_trace.dict() if decision_trace else None
        }

    def _log_audit_event(
        self,
        mandate_id: str,
        event_type: str,
        event_data: Dict,
        reason: str,
        actor: str,
        compliant: bool = True,
        compliance_notes: Optional[str] = None
    ):
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type=event_type,
            event_data=json.dumps(event_data, default=str),
            reason=reason,
            actor=actor,
            timestamp=datetime.utcnow(),
            compliant=compliant,
            compliance_notes=compliance_notes
        )
        self.db.add(audit_log)
