"""
AI Recovery Analyst
Contextual LLM Reasoning Engine for Ambiguous Payment Rail Failures
Produces structured diagnoses, evidence rationales, and recommended interventions.
"""

from typing import List, Optional, Dict, Any
import os
import json
from pydantic import BaseModel, Field
from app.models.evidence import EvidencePacket


class AIAnalystOutput(BaseModel):
    diagnosis: str
    confidence: float
    evidence: List[str]
    recommended_interventions: List[str]
    uncertainty: str  # "LOW", "MEDIUM", "HIGH"
    reasoning_summary: str
    model_used: str


class AIRecoveryAnalyst:
    """
    LLM-powered reasoning engine for ambiguous payment failure cases.
    Performs multi-signal synthesis across bank health, salary cycle, and retry history.
    """

    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    def analyze_evidence(self, evidence: EvidencePacket) -> AIAnalystOutput:
        """
        Synthesizes evidence packet to generate structured diagnosis and strategy.
        Uses live LLM if API key is present, otherwise executes high-fidelity analytical engine.
        """
        # Try live LLM provider if configured
        if self.openai_key:
            try:
                return self._call_openai(evidence)
            except Exception as e:
                print(f"[AIRecoveryAnalyst] OpenAI call failed: {e}, falling back to built-in analyst engine")

        return self._heuristic_analyst_reasoning(evidence)

    def _call_openai(self, evidence: EvidencePacket) -> AIAnalystOutput:
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        
        system_prompt = (
            "You are the Reclaim AI Revenue Recovery Analyst for UPI AutoPay recurring debits. "
            "Analyze the heterogeneous evidence packet and output ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "diagnosis": "BANK_TECHNICAL_DECLINE" | "LOW_BALANCE" | "PORTABILITY_BREAKAGE" | "PRE_DEBIT_OPT_OUT",\n'
            '  "confidence": float (0.0 to 1.0),\n'
            '  "evidence": ["bullet point 1", "bullet point 2", "bullet point 3"],\n'
            '  "recommended_interventions": ["RETRY_OPTIMAL_WINDOW", "SALARY_ALIGNED_RETRY", "CUSTOMER_NUDGE", "PORTABILITY_REFRESH", "HUMAN_ESCALATION"],\n'
            '  "uncertainty": "LOW" | "MEDIUM" | "HIGH",\n'
            '  "reasoning_summary": "string"\n'
            "}"
        )

        user_content = json.dumps(evidence.dict(), indent=2)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Evidence Packet:\n{user_content}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        data = json.loads(response.choices[0].message.content)
        data["model_used"] = "gpt-4o-mini"
        return AIAnalystOutput(**data)

    def _heuristic_analyst_reasoning(self, evidence: EvidencePacket) -> AIAnalystOutput:
        """
        Deterministic analytical reasoning engine mirroring expert fintech triage.
        Used as robust offline engine or fallback.
        """
        evidence_bullets = []
        interventions = []
        
        # 1. Evaluate Bank Health & Degradation Signals
        is_bank_outage = (
            evidence.bank_health.status in ["DEGRADED", "OUTAGE_ANOMALY"]
            or evidence.bank_health.anomaly_sigma >= 2.0
        )
        if is_bank_outage:
            evidence_bullets.append(
                f"Bank degradation detected: {evidence.bank_code} failure rate is "
                f"{evidence.bank_health.anomaly_sigma:.1f}σ above baseline ({evidence.bank_health.rolling_failure_rate_1h*100:.1f}% decline rate)."
            )

        # 2. Evaluate Month-End / Salary Cycle Low Balance Signals
        if evidence.is_month_end:
            evidence_bullets.append(
                f"Temporal timing: Debit scheduled on Day {evidence.day_of_month} (month-end liquidity dip zone)."
            )
        elif evidence.is_salary_window:
            evidence_bullets.append(
                f"Temporal timing: Day {evidence.day_of_month} falls inside national salary credit window (Days 1-7)."
            )

        # 3. Evaluate Portability & VPA Consistency
        if not evidence.vpa_bank_match:
            evidence_bullets.append(
                f"VPA Handle Inconsistency: VPA '{evidence.customer_vpa}' does not map to mandate issuing bank '{evidence.bank_code}'."
            )
        if evidence.in_portability_cooldown:
            evidence_bullets.append("Mandate has an active 90-day NPCI OC-223 portability cooldown event.")

        # 4. Evaluate Outreach Consent
        if not evidence.consent_for_outreach:
            evidence_bullets.append("Customer has revoked/declined outreach consent (DPDPA constraint).")

        # Multi-Signal Synthesis
        if is_bank_outage:
            diagnosis = "BANK_TECHNICAL_DECLINE"
            confidence = 0.86
            uncertainty = "LOW"
            interventions = ["RETRY_OPTIMAL_WINDOW"]
            summary = f"Root cause is active {evidence.bank_code} network degradation. Immediate retries will fail; schedule off-peak batch."
        elif not evidence.vpa_bank_match and evidence.in_portability_cooldown:
            diagnosis = "PORTABILITY_BREAKAGE"
            confidence = 0.82
            uncertainty = "LOW"
            interventions = ["PORTABILITY_REFRESH", "MANDATE_RE_REGISTRATION"]
            summary = "Mandate link broken due to PSP app migration. Verify interoperability status before retrying."
        elif evidence.is_month_end:
            diagnosis = "LOW_BALANCE"
            confidence = 0.84
            uncertainty = "LOW"
            if evidence.consent_for_outreach:
                interventions = ["SALARY_ALIGNED_RETRY", "CUSTOMER_NUDGE"]
            else:
                interventions = ["SALARY_ALIGNED_RETRY"]
            summary = f"Month-end liquidity constraint on Day {evidence.day_of_month}. Defer retry until salary credit window (Day 1-5)."
        elif not evidence.consent_for_outreach and any(code in ["U53", "U72"] for code in evidence.recent_failure_codes):
            diagnosis = "PRE_DEBIT_OPT_OUT"
            confidence = 0.78
            uncertainty = "MEDIUM"
            interventions = ["CUSTOMER_NUDGE", "HUMAN_ESCALATION"]
            summary = "Customer vetoed 24-hour pre-debit notification. Mandate active but current cycle blocked."
        else:
            diagnosis = "BANK_TECHNICAL_DECLINE"
            confidence = 0.71
            uncertainty = "MEDIUM"
            interventions = ["RETRY_OPTIMAL_WINDOW"]
            summary = "Transient bank switch decline without explicit outage. Safe for automated off-peak retry."

        if not evidence_bullets:
            evidence_bullets.append(f"Standard recurring debit for ₹{evidence.amount:,.0f} on {evidence.bank_code}.")
            evidence_bullets.append(f"Attempt #{evidence.attempt_number} with no concurrent outage flag.")

        return AIAnalystOutput(
            diagnosis=diagnosis,
            confidence=round(confidence, 2),
            evidence=evidence_bullets,
            recommended_interventions=interventions,
            uncertainty=uncertainty,
            reasoning_summary=summary,
            model_used="Reclaim-AI-Analyst (Built-in Reasoner)"
        )
