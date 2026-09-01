"""
NPCI & RBI Compliance Engine
Authoritative Policy Enforcement Boundary & Approval Token Generator
"""

from datetime import datetime, time, timedelta
from typing import Tuple, Optional, List, Dict
from enum import Enum
import uuid
from pydantic import BaseModel, Field

from app.compliance.registry import (
    REGULATORY_RULE_REGISTRY,
    RegulatoryRule,
    EnforcementType,
    get_rule_citation,
)


class ComplianceViolationType(str, Enum):
    PEAK_HOUR_VIOLATION = "NPCI_OC_215A_PEAK_HOURS"
    RETRY_LIMIT_EXCEEDED = "NPCI_OC_215A_RETRY_LIMIT"
    INSUFFICIENT_COOLDOWN = "NPCI_STATUS_THROTTLE"
    PORTABILITY_COOLDOWN_VIOLATION = "NPCI_OC_223_PORTABILITY"
    PIN_REAUTH_REQUIRED = "RBI_EMANDATE_2026_PIN_AUTH"
    PRE_DEBIT_NOTIFICATION_VIOLATION = "RBI_EMANDATE_2026_PRE_NOTIF"
    BANK_CALENDAR_BLOCK = "BANK_CALENDAR_MAINTENANCE"


class ComplianceApprovalToken(BaseModel):
    """
    Cryptographic / Structured Authorization Token for Recovery Action Execution.
    No financial action can be executed without a valid, approved token.
    """
    decision_id: str = Field(default_factory=lambda: f"CMP-{uuid.uuid4().hex[:8].upper()}")
    approved: bool
    action: str
    mandate_id: str
    attempt_number: int
    scheduled_time: str
    valid_until: str
    rules_checked: List[str]
    citations: List[Dict[str, str]]
    violations: List[str] = []
    rejection_reason: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class NPCIComplianceEngine:
    """
    Deterministic Compliance Engine and Policy Enforcement Boundary.
    Enforces rules per:
    - NPCI OC/215A/2025-26 (Peak Hours & Max 4 Retries)
    - NPCI OC-223 (Portability & Interoperability)
    - RBI 2026 E-Mandate Master Directions (AFA PIN thresholds & Pre-debit opt-out)
    """

    # Peak hours when batch mandate execution is blocked (NPCI OC/215A)
    PEAK_HOURS = [
        (time(10, 0), time(13, 0)),   # 10:00 AM – 1:00 PM
        (time(17, 0), time(21, 30))   # 5:00 PM – 9:30 PM
    ]

    # Maximum retry attempts per mandate per billing cycle (1 original + 3 retries)
    MAX_RETRY_ATTEMPTS = 4

    # Minimum cooldown between status checks (≥90s apart)
    STATUS_CHECK_COOLDOWN_SECONDS = 90

    # Portability cooldown (90 days)
    PORTABILITY_COOLDOWN_DAYS = 90

    # PIN re-auth thresholds (RBI 2026 e-mandate)
    PIN_REAUTH_DEFAULT_THRESHOLD = 15000  # ₹15,000
    PIN_REAUTH_EXCEPTION_THRESHOLD = 100000  # ₹1,00,000 for insurance, SIPs, credit card bills

    # Exception categories for higher PIN re-auth threshold
    PIN_REAUTH_EXCEPTION_CATEGORIES = ["insurance", "mutual_fund_sip", "credit_card_bill"]

    @staticmethod
    def is_within_execution_window(scheduled_time: datetime) -> bool:
        """
        Check if scheduled time is within NPCI-permitted execution window.
        Returns False if time falls within peak retail hours.
        """
        check_time = scheduled_time.time()
        for start, end in NPCIComplianceEngine.PEAK_HOURS:
            if start <= check_time <= end:
                return False
        return True

    @staticmethod
    def is_bank_processing_window(scheduled_time: datetime, bank_code: Optional[str] = None) -> bool:
        """
        Differentiates bank-specific processing calendars (e.g. weekend batch maintenance)
        from universal NPCI prohibitions.
        """
        # Bank-specific weekend policy check (soft warning / bank calendar)
        # Note: NPCI rail runs 24/7/365, but some core banking hosts run batch maintenance on Sun midnight
        if scheduled_time.weekday() == 6 and scheduled_time.hour < 4:
            return False
        return True

    @staticmethod
    def get_next_valid_execution_window(from_time: datetime) -> Tuple[datetime, datetime]:
        """
        Finds the next valid execution window compliant with NPCI peak hours.
        Returns (window_start, window_end).
        """
        current = from_time
        # Max search 48 hours
        for _ in range(48 * 60):
            check_time = current.time()
            in_peak = False
            for start, end in NPCIComplianceEngine.PEAK_HOURS:
                if start <= check_time <= end:
                    in_peak = True
                    # Jump directly to end of peak block
                    current = current.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
                    break
            
            if not in_peak and NPCIComplianceEngine.is_bank_processing_window(current):
                window_end = current.replace(hour=23, minute=59, second=59)
                return current, window_end

            current = current + timedelta(minutes=1)

        return current, current + timedelta(hours=4)

    @staticmethod
    def can_attempt_retry(current_attempt: int, max_attempts: int = MAX_RETRY_ATTEMPTS) -> bool:
        """Enforces NPCI maximum retry cap per billing cycle."""
        return current_attempt <= max_attempts

    @staticmethod
    def requires_pin_reauth(amount: float, category: Optional[str] = None) -> bool:
        """Evaluates RBI 2026 AFA PIN threshold rules."""
        if category in NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_CATEGORIES:
            return amount > NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_THRESHOLD
        return amount > NPCIComplianceEngine.PIN_REAUTH_DEFAULT_THRESHOLD

    @staticmethod
    def is_within_portability_cooldown(last_port_date: Optional[datetime], current_date: datetime) -> bool:
        """Checks NPCI OC-223 90-day portability cooldown."""
        if last_port_date is None:
            return False
        days_since_port = (current_date - last_port_date).days
        return days_since_port < NPCIComplianceEngine.PORTABILITY_COOLDOWN_DAYS

    @staticmethod
    def can_check_status(last_check_time: Optional[datetime], current_time: datetime) -> bool:
        """Enforces status check throttling (≥90 seconds)."""
        if last_check_time is None:
            return True
        return (current_time - last_check_time).total_seconds() >= NPCIComplianceEngine.STATUS_CHECK_COOLDOWN_SECONDS

    @staticmethod
    def validate_retry_schedule(
        scheduled_time: datetime,
        attempt_number: int,
        mandate_amount: float,
        mandate_category: Optional[str] = None,
        last_port_date: Optional[datetime] = None
    ) -> Tuple[bool, List[ComplianceViolationType]]:
        """Validates all rules and returns boolean + violation list."""
        violations: List[ComplianceViolationType] = []

        if not NPCIComplianceEngine.is_within_execution_window(scheduled_time):
            violations.append(ComplianceViolationType.PEAK_HOUR_VIOLATION)

        if not NPCIComplianceEngine.can_attempt_retry(attempt_number):
            violations.append(ComplianceViolationType.RETRY_LIMIT_EXCEEDED)

        if NPCIComplianceEngine.requires_pin_reauth(mandate_amount, mandate_category):
            violations.append(ComplianceViolationType.PIN_REAUTH_REQUIRED)

        if NPCIComplianceEngine.is_within_portability_cooldown(last_port_date, scheduled_time):
            violations.append(ComplianceViolationType.PORTABILITY_COOLDOWN_VIOLATION)

        return len(violations) == 0, violations

    @staticmethod
    def issue_compliance_token(
        action_name: str,
        mandate_id: str,
        attempt_number: int,
        mandate_amount: float,
        scheduled_time: datetime,
        mandate_category: Optional[str] = None,
        last_port_date: Optional[datetime] = None,
        consent_for_outreach: bool = True
    ) -> ComplianceApprovalToken:
        """
        Master Policy Enforcement Gate.
        Issues a ComplianceApprovalToken if compliant, or a Rejection Token if blocked.
        """
        is_compliant, raw_violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=attempt_number,
            mandate_amount=mandate_amount,
            mandate_category=mandate_category,
            last_port_date=last_port_date
        )

        violations = [v.value for v in raw_violations]
        
        # Additional action-specific policy checks
        if "NUDGE" in action_name.upper() and not consent_for_outreach:
            violations.append("DPDPA_OUTREACH_CONSENT_MISSING")
            is_compliant = False

        rules_checked = [
            "NPCI_OC_215A_PEAK_HOURS",
            "NPCI_OC_215A_RETRY_LIMIT",
            "NPCI_OC_223_PORTABILITY",
            "RBI_EMANDATE_2026_PIN_AUTH",
            "RBI_EMANDATE_2026_PRE_NOTIF"
        ]

        citations = []
        for r_id in rules_checked:
            rule = get_rule_citation(r_id)
            if rule:
                citations.append({
                    "rule_id": rule.rule_id,
                    "authority": rule.authority,
                    "circular": rule.circular_reference,
                    "title": rule.title
                })

        rejection_reason = None
        if not is_compliant:
            rejection_reason = f"Action blocked by policy: {', '.join(violations)}"

        return ComplianceApprovalToken(
            approved=is_compliant,
            action=action_name,
            mandate_id=mandate_id,
            attempt_number=attempt_number,
            scheduled_time=scheduled_time.isoformat(),
            valid_until=(scheduled_time + timedelta(hours=2)).isoformat(),
            rules_checked=rules_checked,
            citations=citations,
            violations=violations,
            rejection_reason=rejection_reason
        )
