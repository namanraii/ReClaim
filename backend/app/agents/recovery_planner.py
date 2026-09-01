"""
Recovery Opportunity Planner & Decision Engine
Evaluates candidate actions, computes Expected Recoverable Revenue (ERV - Heuristic Estimate),
evaluates counterfactuals, conditionally invokes Generative AI for nudges, and routes through the Compliance Gate.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
from pydantic import BaseModel, Field

from app.compliance import NPCIComplianceEngine, ComplianceApprovalToken
from app.models.hybrid_diagnostician import DiagnosticResult
from app.models.evidence import EvidencePacket
from app.agents.communication import CommunicationAgent


class RecoveryActionType(str, Enum):
    RETRY_OPTIMAL_WINDOW = "RETRY_OPTIMAL_WINDOW"
    SALARY_ALIGNED_RETRY = "SALARY_ALIGNED_RETRY"
    CUSTOMER_NUDGE = "CUSTOMER_NUDGE"
    SALARY_RETRY_AND_NUDGE = "SALARY_RETRY_AND_NUDGE"
    PORTABILITY_REFRESH = "PORTABILITY_REFRESH"
    MANDATE_RE_REGISTRATION = "MANDATE_RE_REGISTRATION"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    NO_ACTION_STOP = "NO_ACTION_STOP"


class ActionCandidateEvaluation(BaseModel):
    action: RecoveryActionType
    description: str
    recovery_probability: float  # P(R | a, C) - Estimated opportunity rate
    recoverable_amount: float
    friction_cost: float  # Friction / communication cost in ₹
    risk_cost: float  # Compliance / operational risk in ₹
    expected_revenue_value: float  # ERV (Heuristic Estimate in ₹)
    is_compliant: bool
    compliance_notes: str
    is_selected: bool = False


class DecisionTrace(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"RCM-{uuid.uuid4().hex[:8].upper()}")
    mandate_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    revenue_at_risk: float
    diagnosis: str
    confidence: float
    resolution_path: str
    is_abstained: bool = False
    evidence_points: List[str]
    candidate_evaluations: List[ActionCandidateEvaluation]
    selected_action: RecoveryActionType
    expected_recovered_revenue: float
    counterfactual_explanation: str
    generated_communication: Optional[Dict[str, Any]] = None
    compliance_token: ComplianceApprovalToken
    execution_status: str  # "SCHEDULED", "BLOCKED_BY_POLICY", "EXECUTED", "ESCALATED"


class RecoveryPlanner:
    """
    Decision Intelligence Engine for UPI AutoPay Recovery.
    Optimizes ERV(a) = P(R|a, C) * Amount - Friction(a) - Risk(a)
    Note: Probabilities are heuristic estimates derived from held-out recovery evaluation surfaces.
    """

    def __init__(self):
        self.compliance_engine = NPCIComplianceEngine()
        self.comm_agent = CommunicationAgent()

    def plan_recovery(
        self,
        evidence: EvidencePacket,
        diagnosis: DiagnosticResult,
        current_time: Optional[datetime] = None
    ) -> DecisionTrace:
        now = current_time or datetime.utcnow()
        amount = evidence.amount
        cat = diagnosis.failure_category
        consent = evidence.consent_for_outreach
        attempt = evidence.attempt_number

        candidates: List[ActionCandidateEvaluation] = []

        # ---------------------------------------------------------------------
        # 1. RETRY_OPTIMAL_WINDOW (Off-peak batch 02:30 AM - 08:00 AM)
        # ---------------------------------------------------------------------
        if cat in ["BANK_TECHNICAL_DECLINE", "NPCI_WINDOW_VIOLATION"]:
            p_opt = 0.74
        elif cat == "LOW_BALANCE":
            p_opt = 0.20 if evidence.is_month_end else 0.45
        else:
            p_opt = 0.35

        if evidence.bank_health.status == "OUTAGE_ANOMALY":
            p_opt = max(0.15, p_opt - 0.30)  # Lower during active bank outage

        f_opt = 5.0
        r_opt = 5.0
        erv_opt = max(0.0, (p_opt * amount) - f_opt - r_opt)

        next_off_peak = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        token_opt = self.compliance_engine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt + 1,
            mandate_amount=amount,
            scheduled_time=next_off_peak,
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.RETRY_OPTIMAL_WINDOW,
            description="Schedule automated debit in next off-peak execution window (02:30–08:00 AM)",
            recovery_probability=round(p_opt, 2),
            recoverable_amount=amount,
            friction_cost=f_opt,
            risk_cost=r_opt,
            expected_revenue_value=round(erv_opt, 2),
            is_compliant=token_opt.approved,
            compliance_notes=token_opt.rejection_reason or "Compliant with NPCI OC/215A off-peak window."
        ))

        # ---------------------------------------------------------------------
        # 2. SALARY_ALIGNED_RETRY (Deferred to Day 1-5 of month)
        # ---------------------------------------------------------------------
        p_sal = 0.88 if cat == "LOW_BALANCE" else 0.45
        f_sal = 15.0
        r_sal = 10.0
        erv_sal = max(0.0, (p_sal * amount) - f_sal - r_sal)

        if now.day >= 25:
            target_month = now.month + 1 if now.month < 12 else 1
            target_year = now.year if now.month < 12 else now.year + 1
            salary_date = datetime(target_year, target_month, 2, 4, 0)
        else:
            salary_date = now + timedelta(days=3)
            salary_date = salary_date.replace(hour=4, minute=0)

        token_sal = self.compliance_engine.issue_compliance_token(
            action_name="SALARY_ALIGNED_RETRY",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt + 1,
            mandate_amount=amount,
            scheduled_time=salary_date,
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.SALARY_ALIGNED_RETRY,
            description=f"Align retry with national salary credit window on {salary_date.strftime('%b %d')}",
            recovery_probability=round(p_sal, 2),
            recoverable_amount=amount,
            friction_cost=f_sal,
            risk_cost=r_sal,
            expected_revenue_value=round(erv_sal, 2),
            is_compliant=token_sal.approved,
            compliance_notes=token_sal.rejection_reason or "Compliant timing within allowed billing cycle."
        ))

        # ---------------------------------------------------------------------
        # 3. CUSTOMER_NUDGE (Consent-gated Hinglish WhatsApp/SMS)
        # ---------------------------------------------------------------------
        p_nudge = 0.72 if (consent and cat in ["PIN_REAUTH_REQUIRED", "PRE_DEBIT_OPT_OUT", "LOW_BALANCE"]) else 0.20
        f_nudge = 25.0
        r_nudge = 10.0 if consent else 500.0
        erv_nudge = max(0.0, (p_nudge * amount) - f_nudge - r_nudge)

        token_nudge = self.compliance_engine.issue_compliance_token(
            action_name="CUSTOMER_NUDGE",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt,
            mandate_amount=amount,
            scheduled_time=now + timedelta(hours=1),
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.CUSTOMER_NUDGE,
            description="Send bilingual contextual Hinglish nudge with direct UPI approval link",
            recovery_probability=round(p_nudge, 2),
            recoverable_amount=amount,
            friction_cost=f_nudge,
            risk_cost=r_nudge,
            expected_revenue_value=round(erv_nudge, 2),
            is_compliant=token_nudge.approved,
            compliance_notes=token_nudge.rejection_reason or "Compliant with DPDPA consent framework."
        ))

        # ---------------------------------------------------------------------
        # 4. SALARY_RETRY_AND_NUDGE (Combined Playbook)
        # ---------------------------------------------------------------------
        p_comb = 0.91 if (cat == "LOW_BALANCE" and consent) else 0.50
        f_comb = 35.0
        r_comb = 15.0
        erv_comb = max(0.0, (p_comb * amount) - f_comb - r_comb)

        token_comb = self.compliance_engine.issue_compliance_token(
            action_name="SALARY_RETRY_AND_NUDGE",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt + 1,
            mandate_amount=amount,
            scheduled_time=salary_date,
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.SALARY_RETRY_AND_NUDGE,
            description="Combined Strategy: Pre-salary nudge reminder + Day 2 salary batch debit",
            recovery_probability=round(p_comb, 2),
            recoverable_amount=amount,
            friction_cost=f_comb,
            risk_cost=r_comb,
            expected_revenue_value=round(erv_comb, 2),
            is_compliant=token_comb.approved,
            compliance_notes=token_comb.rejection_reason or "Compliant multi-channel strategy."
        ))

        # ---------------------------------------------------------------------
        # 5. PORTABILITY_REFRESH (NPCI OC-223 Interoperability Status)
        # ---------------------------------------------------------------------
        p_port = 0.85 if cat == "PORTABILITY_BREAKAGE" else 0.15
        f_port = 10.0
        r_port = 10.0
        erv_port = max(0.0, (p_port * amount) - f_port - r_port)

        token_port = self.compliance_engine.issue_compliance_token(
            action_name="PORTABILITY_REFRESH",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt,
            mandate_amount=amount,
            scheduled_time=now + timedelta(minutes=15),
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.PORTABILITY_REFRESH,
            description="Query NPCI OC-223 registry and refresh PSP routing handle without full re-registration",
            recovery_probability=round(p_port, 2),
            recoverable_amount=amount,
            friction_cost=f_port,
            risk_cost=r_port,
            expected_revenue_value=round(erv_port, 2),
            is_compliant=token_port.approved,
            compliance_notes=token_port.rejection_reason or "NPCI OC-223 interoperability verification."
        ))

        # ---------------------------------------------------------------------
        # 6. HUMAN_ESCALATION (VIP / High Uncertainty Exception Desk)
        # ---------------------------------------------------------------------
        p_esc = 0.40
        f_esc = 120.0
        r_esc = 0.0
        erv_esc = max(0.0, (p_esc * amount) - f_esc - r_esc)

        token_esc = self.compliance_engine.issue_compliance_token(
            action_name="HUMAN_ESCALATION",
            mandate_id=evidence.mandate_id,
            attempt_number=attempt,
            mandate_amount=amount,
            scheduled_time=now,
            mandate_category=evidence.category,
            consent_for_outreach=consent
        )
        candidates.append(ActionCandidateEvaluation(
            action=RecoveryActionType.HUMAN_ESCALATION,
            description="Escalate to merchant account manager for VIP exception review",
            recovery_probability=round(p_esc, 2),
            recoverable_amount=amount,
            friction_cost=f_esc,
            risk_cost=r_esc,
            expected_revenue_value=round(erv_esc, 2),
            is_compliant=token_esc.approved,
            compliance_notes=token_esc.rejection_reason or "Manual review escalation."
        ))

        # ---------------------------------------------------------------------
        # SELECTION LOGIC: Highest ERV among Compliant Candidates
        # ---------------------------------------------------------------------
        compliant_candidates = [c for c in candidates if c.is_compliant]

        if diagnosis.is_abstained:
            # When model abstained on high uncertainty, default to HUMAN_ESCALATION or safe off-peak retry
            selected_eval = next((c for c in candidates if c.action == RecoveryActionType.HUMAN_ESCALATION), candidates[-1])
            selected_eval.is_selected = True
            final_token = token_esc
            exec_status = "ESCALATED"
        elif not compliant_candidates:
            selected_eval = candidates[-1]  # HUMAN_ESCALATION fallback
            final_token = token_esc
            exec_status = "ESCALATED"
        else:
            compliant_candidates.sort(key=lambda x: x.expected_revenue_value, reverse=True)
            selected_eval = compliant_candidates[0]
            selected_eval.is_selected = True
            exec_status = "SCHEDULED"

            token_map = {
                RecoveryActionType.RETRY_OPTIMAL_WINDOW: token_opt,
                RecoveryActionType.SALARY_ALIGNED_RETRY: token_sal,
                RecoveryActionType.CUSTOMER_NUDGE: token_nudge,
                RecoveryActionType.SALARY_RETRY_AND_NUDGE: token_comb,
                RecoveryActionType.PORTABILITY_REFRESH: token_port,
                RecoveryActionType.HUMAN_ESCALATION: token_esc
            }
            final_token = token_map.get(selected_eval.action, token_opt)

        # ---------------------------------------------------------------------
        # CONDITIONAL GENERATIVE AI OUTREACH (Invoked ONLY if messaging needed)
        # ---------------------------------------------------------------------
        generated_comm = None
        if selected_eval.action in [
            RecoveryActionType.CUSTOMER_NUDGE,
            RecoveryActionType.SALARY_RETRY_AND_NUDGE
        ] or cat == "PIN_REAUTH_REQUIRED":
            generated_comm = self.comm_agent.generate_personalized_nudge(
                failure_category=cat,
                amount=amount,
                bank_code=evidence.bank_code,
                customer_vpa=evidence.customer_vpa,
                consent_for_outreach=consent
            )

        # Counterfactual explanation summary
        non_selected = [c for c in candidates if c.action != selected_eval.action]
        counterfactual_lines = [
            f"Selected '{selected_eval.action.value}' provides highest recovery opportunity score of ₹{selected_eval.expected_revenue_value:,.0f} "
            f"({selected_eval.recovery_probability*100:.0f}% estimated success)."
        ]
        for alt in non_selected[:3]:
            if not alt.is_compliant:
                counterfactual_lines.append(f"• Alternative '{alt.action.value}': ERV ₹{alt.expected_revenue_value:,.0f} — BLOCKED BY COMPLIANCE GATE ({alt.compliance_notes})")
            else:
                diff = selected_eval.expected_revenue_value - alt.expected_revenue_value
                counterfactual_lines.append(f"• Alternative '{alt.action.value}': ERV ₹{alt.expected_revenue_value:,.0f} (₹{diff:,.0f} lower ERV)")

        counterfactual_summary = "\n".join(counterfactual_lines)
        decision_id = f"RCM-{uuid.uuid4().hex[:8].upper()}"

        return DecisionTrace(
            decision_id=decision_id,
            mandate_id=evidence.mandate_id,
            timestamp=now.isoformat(),
            revenue_at_risk=amount,
            diagnosis=diagnosis.failure_category,
            confidence=diagnosis.confidence,
            resolution_path=diagnosis.resolution_path,
            is_abstained=diagnosis.is_abstained,
            evidence_points=diagnosis.evidence_points,
            candidate_evaluations=candidates,
            selected_action=selected_eval.action,
            expected_recovered_revenue=selected_eval.expected_revenue_value,
            counterfactual_explanation=counterfactual_summary,
            generated_communication=generated_comm,
            compliance_token=final_token,
            execution_status=exec_status
        )
