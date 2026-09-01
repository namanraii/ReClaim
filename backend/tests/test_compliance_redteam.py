"""
Adversarial Compliance Red-Team Test Suite
Simulates illegal retry attempts, parameter spoofing, and boundary violations.
Verifies that 100% of illegal execution requests are hard-blocked by the Policy Enforcement Gate.
"""

import pytest
from datetime import datetime, timedelta
from app.compliance import NPCIComplianceEngine, ComplianceViolationType, ComplianceApprovalToken


class TestAdversarialComplianceGate:

    def test_peak_hour_morning_hard_block(self):
        """Simulate retry attempt at 11:15 AM (Morning Peak Hour)"""
        peak_time = datetime(2026, 9, 2, 11, 15)
        token: ComplianceApprovalToken = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_NOW",
            mandate_id="mandate-adv-001",
            attempt_number=2,
            mandate_amount=2500.0,
            scheduled_time=peak_time,
            mandate_category="subscription"
        )
        assert not token.approved
        assert "NPCI_OC_215A_PEAK_HOURS" in token.violations
        assert token.rejection_reason is not None

    def test_peak_hour_evening_hard_block(self):
        """Simulate retry attempt at 19:30 PM (Evening Peak Hour)"""
        peak_time = datetime(2026, 9, 2, 19, 30)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_NOW",
            mandate_id="mandate-adv-002",
            attempt_number=2,
            mandate_amount=1500.0,
            scheduled_time=peak_time
        )
        assert not token.approved
        assert "NPCI_OC_215A_PEAK_HOURS" in token.violations

    def test_attempt_cap_fifth_retry_spoofing(self):
        """Attempt to execute a 5th retry attempt (violates Max 4 attempts)"""
        valid_time = datetime(2026, 9, 2, 3, 0)  # Off-peak 3 AM
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-003",
            attempt_number=5,  # 5th attempt!
            mandate_amount=1000.0,
            scheduled_time=valid_time
        )
        assert not token.approved
        assert "NPCI_OC_215A_RETRY_LIMIT" in token.violations

    def test_large_value_without_pin_reauth(self):
        """Attempt automated debit of ₹25,000 without PIN authorization"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-004",
            attempt_number=2,
            mandate_amount=25000.0,  # > ₹15,000 default threshold
            scheduled_time=valid_time,
            mandate_category="subscription"
        )
        assert not token.approved
        assert "RBI_EMANDATE_2026_PIN_AUTH" in token.violations

    def test_insurance_exception_threshold_allowed(self):
        """Insurance premium ₹75,000 debit allowed under RBI ₹1L exception rule"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-005",
            attempt_number=2,
            mandate_amount=75000.0,  # Below ₹1,00,000 for insurance
            scheduled_time=valid_time,
            mandate_category="insurance"
        )
        assert token.approved
        assert len(token.violations) == 0

    def test_insurance_over_threshold_blocked(self):
        """Insurance premium ₹1,25,000 debit blocked (exceeds ₹1L exception limit)"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-006",
            attempt_number=2,
            mandate_amount=125000.0,  # Exceeds ₹1,00,000
            scheduled_time=valid_time,
            mandate_category="insurance"
        )
        assert not token.approved
        assert "RBI_EMANDATE_2026_PIN_AUTH" in token.violations

    def test_portability_cooldown_enforcement(self):
        """Mandate ported 20 days ago (inside 90-day cooldown)"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        last_port = datetime(2026, 8, 15)  # 18 days prior
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-007",
            attempt_number=2,
            mandate_amount=1200.0,
            scheduled_time=valid_time,
            last_port_date=last_port
        )
        assert not token.approved
        assert "NPCI_OC_223_PORTABILITY" in token.violations

    def test_dpdpa_consent_missing_outreach_block(self):
        """Attempt customer nudge when consent_for_outreach is False"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="CUSTOMER_NUDGE",
            mandate_id="mandate-adv-008",
            attempt_number=2,
            mandate_amount=1200.0,
            scheduled_time=valid_time,
            consent_for_outreach=False  # NO CONSENT
        )
        assert not token.approved
        assert "DPDPA_OUTREACH_CONSENT_MISSING" in token.violations

    def test_token_format_and_citations(self):
        """Verifies ComplianceApprovalToken structure and circular citations"""
        valid_time = datetime(2026, 9, 2, 3, 0)
        token = NPCIComplianceEngine.issue_compliance_token(
            action_name="RETRY_OPTIMAL_WINDOW",
            mandate_id="mandate-adv-009",
            attempt_number=2,
            mandate_amount=1200.0,
            scheduled_time=valid_time
        )
        assert token.decision_id.startswith("CMP-")
        assert token.approved
        assert len(token.citations) >= 4
        # Verify specific circular reference is present
        assert any(c["circular"] == "NPCI/2025-26/OC/215A" for c in token.citations)
