"""
Hybrid Diagnostician
Stage 1: Deterministic Regulatory & Constraint Rules (100% Precision)
Stage 2: Calibrated Tabular ML (XGBoost) + Real SHAP Explainability
Stage 3: Selective Abstention Policy for Low-Confidence Cases & Inference Failures
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.compliance import NPCIComplianceEngine
from app.models.evidence import EvidencePacket, build_evidence_packet
from app.models.service import get_classifier, is_model_available


class DiagnosticResult(BaseModel):
    mandate_id: str
    failure_category: str
    confidence: float
    resolution_path: str  # "DETERMINISTIC_RULE", "CALIBRATED_XGBOOST", "ABSTAIN_DEFERRED", "ML_INFERENCE_ERROR_ABSTAIN"
    evidence_points: List[str]
    rationale: str
    recommended_interventions: List[str]
    is_abstained: bool = False
    raw_error_code: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# Standard UPI AutoPay Error Codes per Failure Mode
CATEGORY_ERROR_CODE_MAP = {
    "NPCI_WINDOW_VIOLATION": "U91_PEAK_HOUR",
    "PIN_REAUTH_REQUIRED": "U33_PIN_REQUIRED",
    "PORTABILITY_BREAKAGE": "U71_PORTABILITY",
    "LOW_BALANCE": "U51_LOW_BALANCE",
    "PRE_DEBIT_OPT_OUT": "U53_OPT_OUT",
    "BANK_TECHNICAL_DECLINE": "U52_TECHNICAL",
}


class HybridDiagnostician:
    """
    Two-Stage Diagnostic Engine with Selective Abstention.
    Principle:
    - Deterministic rules for known constraints (100% precision).
    - Calibrated XGBoost for tabular probabilistic diagnosis.
    - Explicit abstention when uncertainty is high (conf < 0.52) or on inference error.
    - No LLMs used for tabular numeric classification.
    """

    def __init__(self):
        self.compliance_engine = NPCIComplianceEngine()

    def diagnose_failure(
        self,
        mandate_dict: Dict[str, Any],
        attempt_dict: Dict[str, Any],
        attempts_history: Optional[List[Dict[str, Any]]] = None,
        reference_time: Optional[datetime] = None
    ) -> DiagnosticResult:
        evidence = build_evidence_packet(mandate_dict, attempt_dict, attempts_history, reference_time)
        scheduled_dt = datetime.fromisoformat(evidence.scheduled_at)

        # ---------------------------------------------------------
        # STAGE 1: DETERMINISTIC RULES (100% Precision by Design)
        # ---------------------------------------------------------

        # Rule 1: NPCI Peak Hour Violation
        if not self.compliance_engine.is_within_execution_window(scheduled_dt):
            return DiagnosticResult(
                mandate_id=evidence.mandate_id,
                failure_category="NPCI_WINDOW_VIOLATION",
                confidence=1.00,
                resolution_path="DETERMINISTIC_RULE",
                evidence_points=[
                    f"Execution scheduled at {evidence.hour_of_day:02d}:00, falling inside restricted peak hours (10:00-13:00 / 17:00-21:30).",
                    "Deterministic rejection by NPCI OC/215A timing rule."
                ],
                rationale="NPCI restricted peak hour execution window blackout enforced.",
                recommended_interventions=["RETRY_OPTIMAL_WINDOW"],
                raw_error_code=CATEGORY_ERROR_CODE_MAP["NPCI_WINDOW_VIOLATION"]
            )

        # Rule 2: RBI PIN Re-Authentication Threshold
        if self.compliance_engine.requires_pin_reauth(evidence.amount, evidence.category):
            threshold = (
                self.compliance_engine.PIN_REAUTH_EXCEPTION_THRESHOLD
                if evidence.category in self.compliance_engine.PIN_REAUTH_EXCEPTION_CATEGORIES
                else self.compliance_engine.PIN_REAUTH_DEFAULT_THRESHOLD
            )
            return DiagnosticResult(
                mandate_id=evidence.mandate_id,
                failure_category="PIN_REAUTH_REQUIRED",
                confidence=1.00,
                resolution_path="DETERMINISTIC_RULE",
                evidence_points=[
                    f"Mandate amount ₹{evidence.amount:,.0f} exceeds RBI 2026 AFA threshold of ₹{threshold:,.0f} for {evidence.category}.",
                    "Customer must interactively authorize via UPI PIN before debit can execute."
                ],
                rationale="RBI 2026 E-Mandate AFA PIN authorization threshold exceeded.",
                recommended_interventions=["CUSTOMER_NUDGE", "HUMAN_ESCALATION"],
                raw_error_code=CATEGORY_ERROR_CODE_MAP["PIN_REAUTH_REQUIRED"]
            )

        # Rule 3: Portability Breakage / App Migration Mismatch
        if evidence.portability_mismatch_detected or evidence.in_portability_cooldown:
            port_confidence = 0.95 if (evidence.portability_mismatch_detected and evidence.in_portability_cooldown) else 0.85
            evidence_points = []
            if evidence.portability_mismatch_detected:
                evidence_points.append(
                    f"VPA/PSP routing discrepancy: VPA '{evidence.customer_vpa}' does not map to issuing bank '{evidence.bank_code}' or registered app '{evidence.psp_app}'."
                )
            if evidence.in_portability_cooldown:
                evidence_points.append("Mandate has active NPCI OC-223 90-day portability cooldown record.")

            return DiagnosticResult(
                mandate_id=evidence.mandate_id,
                failure_category="PORTABILITY_BREAKAGE",
                confidence=port_confidence,
                resolution_path="DETERMINISTIC_RULE",
                evidence_points=evidence_points,
                rationale="Mandate ported to new PSP app; routing handle requires refresh.",
                recommended_interventions=["PORTABILITY_REFRESH", "MANDATE_RE_REGISTRATION"],
                raw_error_code=CATEGORY_ERROR_CODE_MAP["PORTABILITY_BREAKAGE"]
            )

        # ---------------------------------------------------------
        # STAGE 2: CALIBRATED TABULAR ML (XGBoost Classifier + Real SHAP)
        # ---------------------------------------------------------
        ml_prediction = None
        ml_confidence = 0.0
        shap_evidence = []
        ml_error = None

        if is_model_available():
            try:
                classifier = get_classifier()
                import pandas as pd
                df_input = {
                    "mandate_id": [evidence.mandate_id],
                    "bank_code": [evidence.bank_code],
                    "psp_app": [evidence.psp_app],
                    "amount": [evidence.amount],
                    "scheduled_at": [evidence.scheduled_at],
                    "attempt_number": [evidence.attempt_number],
                    "category": [evidence.category],
                    "pin_reauth_required": [evidence.pin_reauth_required],
                    "created_at": [evidence.scheduled_at],
                    "consent_for_outreach": [evidence.consent_for_outreach],
                }
                pred_df = pd.DataFrame(df_input)
                preds, probs = classifier.predict(pred_df)
                ml_prediction = preds[0]
                ml_confidence = float(max(probs[0]))

                # Real SHAP top feature contribution toward predicted class (signed, not max-across-classes)
                try:
                    shap_res = classifier.explain_prediction(pred_df, index=0)
                    fi = shap_res.get("feature_importance", {})
                    # Sort by signed value descending: largest positive = strongest push toward predicted class
                    top_features = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:2]
                    for feat, impact in top_features:
                        direction = "toward" if impact > 0 else "against"
                        shap_evidence.append(
                            f"SHAP ({shap_res.get('predicted_class_label', ml_prediction)}): "
                            f"'{feat}' pushed {direction} this diagnosis (value: {impact:+.3f})."
                        )
                except Exception as shap_err:
                    print(f"[HybridDiagnostician] SHAP inspection failed: {shap_err}")

            except Exception as e:
                ml_error = str(e)
                print(f"[HybridDiagnostician] ML inference exception: {e}")

        # If inference failed or model is missing -> Safe Abstention (never confident misdiagnosis)
        if ml_prediction is None or ml_error is not None:
            return DiagnosticResult(
                mandate_id=evidence.mandate_id,
                failure_category="BANK_TECHNICAL_DECLINE",
                confidence=0.40,
                resolution_path="ML_INFERENCE_ERROR_ABSTAIN",
                is_abstained=True,
                evidence_points=[
                    f"ML inference unavailable or threw exception ({ml_error or 'model artifact missing'}).",
                    "Safety policy triggered: Zero autonomous execution on inference failure."
                ],
                rationale="Inference exception safety abstention: Request routed to exception queue.",
                recommended_interventions=["HUMAN_ESCALATION", "RETRY_OPTIMAL_WINDOW"],
                raw_error_code="U51_UNKNOWN"
            )

        # ---------------------------------------------------------
        # STAGE 3: SELECTIVE ABSTENTION POLICY
        # ---------------------------------------------------------
        # If model confidence is low (< 0.52), abstain from autonomous execution
        if ml_confidence < 0.52:
            return DiagnosticResult(
                mandate_id=evidence.mandate_id,
                failure_category=ml_prediction,
                confidence=round(ml_confidence, 2),
                resolution_path="ABSTAIN_DEFERRED",
                is_abstained=True,
                evidence_points=[
                    f"Calibrated ML confidence ({ml_confidence*100:.1f}%) is below automation safety threshold (52%).",
                    "High signal ambiguity across technical decline and liquidity features."
                ],
                rationale="Uncertainty boundary triggered: Automated recovery deferred to prevent false intervention.",
                recommended_interventions=["HUMAN_ESCALATION", "RETRY_OPTIMAL_WINDOW"],
                raw_error_code=CATEGORY_ERROR_CODE_MAP.get(ml_prediction, "U51_AMBIGUOUS")
            )

        evidence_list = [
            f"Calibrated XGBoost model assigned {ml_prediction} with {ml_confidence*100:.1f}% probability.",
            f"Temporal context: Day {evidence.day_of_month}, Hour {evidence.hour_of_day}, Bank {evidence.bank_code}."
        ] + shap_evidence

        return DiagnosticResult(
            mandate_id=evidence.mandate_id,
            failure_category=ml_prediction,
            confidence=round(ml_confidence, 2),
            resolution_path="CALIBRATED_XGBOOST",
            is_abstained=False,
            evidence_points=evidence_list,
            rationale=f"Probabilistic classification via calibrated tabular XGBoost ({ml_confidence*100:.1f}% confidence).",
            recommended_interventions=[
                "SALARY_ALIGNED_RETRY" if ml_prediction == "LOW_BALANCE" else "RETRY_OPTIMAL_WINDOW"
            ],
            raw_error_code=CATEGORY_ERROR_CODE_MAP.get(ml_prediction, "U52_TECHNICAL")
        )
