"""
Regulatory Rule Registry for UPI AutoPay
Authoritative source-backed citations for all compliance constraints
"""

from typing import Dict, List, Optional
from pydantic import BaseModel
from enum import Enum


class EnforcementType(str, Enum):
    HARD_BLOCK = "HARD_BLOCK"  # Execution strictly prohibited
    SOFT_WARNING = "SOFT_WARNING"  # Allowed with caution / logging
    CONDITIONAL = "CONDITIONAL"  # Requires specific authorization (e.g., PIN re-auth)


class RegulatoryRule(BaseModel):
    rule_id: str
    authority: str
    circular_reference: str
    effective_date: str
    title: str
    description: str
    enforcement: EnforcementType
    parameter_spec: Dict[str, str]


REGULATORY_RULE_REGISTRY: Dict[str, RegulatoryRule] = {
    "NPCI_OC_215A_PEAK_HOURS": RegulatoryRule(
        rule_id="NPCI_OC_215A_PEAK_HOURS",
        authority="NPCI",
        circular_reference="NPCI/2025-26/OC/215A",
        effective_date="2025-08-01",
        title="UPI AutoPay Peak Hour Execution Window Blackout",
        description=(
            "Mandate batch executions are prohibited during peak retail UPI transaction hours "
            "(10:00 AM - 1:00 PM and 5:00 PM - 9:30 PM) to protect real-time settlement rails."
        ),
        enforcement=EnforcementType.HARD_BLOCK,
        parameter_spec={"blocked_morning": "10:00-13:00", "blocked_evening": "17:00-21:30"}
    ),
    "NPCI_OC_215A_RETRY_LIMIT": RegulatoryRule(
        rule_id="NPCI_OC_215A_RETRY_LIMIT",
        authority="NPCI",
        circular_reference="NPCI/2025-26/OC/215A",
        effective_date="2025-08-01",
        title="Maximum Debit Retry Cap Per Cycle",
        description=(
            "A maximum of 4 debit attempts (1 original + 3 retries) are permitted per mandate "
            "billing cycle. Subsequent retry attempts must be halted to prevent customer harassment and fees."
        ),
        enforcement=EnforcementType.HARD_BLOCK,
        parameter_spec={"max_attempts": "4"}
    ),
    "NPCI_OC_223_PORTABILITY": RegulatoryRule(
        rule_id="NPCI_OC_223_PORTABILITY",
        authority="NPCI",
        circular_reference="NPCI/2025-26/OC-223",
        effective_date="2025-10-07",
        title="UPI AutoPay Interoperability & Portability Framework",
        description=(
            "Users can view and port AutoPay mandates across UPI apps. For ported mandates, "
            "interoperability status must be refreshed; a 90-day cooldown applies to re-porting."
        ),
        enforcement=EnforcementType.CONDITIONAL,
        parameter_spec={"portability_cooldown_days": "90"}
    ),
    "RBI_EMANDATE_2026_PIN_AUTH": RegulatoryRule(
        rule_id="RBI_EMANDATE_2026_PIN_AUTH",
        authority="RBI",
        circular_reference="RBI/2025-26/DPSS.CO.PD.No.123/02.14.003",
        effective_date="2026-01-01",
        title="AFA Additional Factor Authentication Thresholds",
        description=(
            "Debits exceeding ₹15,000 require explicit per-debit UPI PIN authentication. "
            "Exception threshold of ₹1,00,000 applies to Insurance premiums, Mutual Fund SIPs, and Credit Card bills."
        ),
        enforcement=EnforcementType.CONDITIONAL,
        parameter_spec={"default_threshold": "15000", "exception_threshold": "100000"}
    ),
    "RBI_EMANDATE_2026_PRE_NOTIF": RegulatoryRule(
        rule_id="RBI_EMANDATE_2026_PRE_NOTIF",
        authority="RBI",
        circular_reference="RBI/2025-26/DPSS.CO.PD.No.123/02.14.003",
        effective_date="2026-01-01",
        title="24-Hour Pre-Debit Notification and Opt-Out Window",
        description=(
            "Merchants/PSPs must send pre-debit notifications at least 24 hours prior to execution. "
            "Customer opt-outs veto the specific debit cycle without revoking the underlying mandate."
        ),
        enforcement=EnforcementType.HARD_BLOCK,
        parameter_spec={"min_pre_notification_hours": "24"}
    ),
    "NPCI_STATUS_THROTTLE": RegulatoryRule(
        rule_id="NPCI_STATUS_THROTTLE",
        authority="NPCI",
        circular_reference="NPCI/UPI/2024-25/CIRC-89",
        effective_date="2024-06-01",
        title="Mandate Status Check Throttling",
        description=(
            "Status checks on pending debit transactions must be spaced at least 90 seconds apart, "
            "with a maximum of 3 checks per 2-hour window."
        ),
        enforcement=EnforcementType.HARD_BLOCK,
        parameter_spec={"min_interval_seconds": "90", "max_checks_per_2h": "3"}
    ),
    "BANK_CALENDAR_MAINTENANCE": RegulatoryRule(
        rule_id="BANK_CALENDAR_MAINTENANCE",
        authority="BANK_CALENDAR",
        circular_reference="BANK-POLICY-SCHEDULED-DOWNTIME",
        effective_date="2026-01-01",
        title="Bank-Specific Processing Windows and Scheduled Maintenance",
        description=(
            "Differentiates bank-specific core banking maintenance windows from universal NPCI prohibitions."
        ),
        enforcement=EnforcementType.SOFT_WARNING,
        parameter_spec={"processing_calendar": "bank_specific"}
    )
}


def get_rule_citation(rule_id: str) -> Optional[RegulatoryRule]:
    """Retrieve full regulatory citation for a rule ID"""
    return REGULATORY_RULE_REGISTRY.get(rule_id)


def list_all_rules() -> List[RegulatoryRule]:
    """List all registered regulatory rules"""
    return list(REGULATORY_RULE_REGISTRY.values())
