"""
Evidence Aggregator for Mandate Recovery Diagnosis
Assembles heterogeneous signals across customer history, bank health, error codes, and calendar.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.signals.bank_health import BankHealthEngine, BankHealthReport


class DebitAttemptSummary(BaseModel):
    attempt_number: int
    scheduled_at: str
    status: str
    response_code: Optional[str] = None
    response_message: Optional[str] = None


class EvidencePacket(BaseModel):
    mandate_id: str
    amount: float
    bank_code: str
    customer_vpa: str
    psp_app: str
    category: str
    frequency: str
    consent_for_outreach: bool
    pin_reauth_required: bool
    
    # Timing & Calendar
    scheduled_at: str
    hour_of_day: int
    day_of_month: int
    day_of_week: int
    is_month_end: bool
    is_salary_window: bool
    
    # Bank & Network Signals
    bank_health: BankHealthReport
    vpa_bank_match: bool
    in_portability_cooldown: bool
    
    # Historical Performance
    attempt_number: int
    attempts_history: List[DebitAttemptSummary] = []
    days_since_last_success: int
    mandate_age_days: int
    recent_failure_codes: List[str] = []
    
    # Context summary string for LLM reasoning
    summary_text: str = ""


VPA_BANK_MAP = {
    "okhdfc": "HDFC",
    "okicici": "ICICI",
    "oksbi": "SBI",
    "okaxis": "AXIS",
    "okkotak": "KOTAK",
    "okpnb": "PNB",
    "okbob": "BOB",
}


def build_evidence_packet(
    mandate_dict: Dict[str, Any],
    attempt_dict: Dict[str, Any],
    attempts_history_list: Optional[List[Dict[str, Any]]] = None,
    reference_time: Optional[datetime] = None
) -> EvidencePacket:
    """
    Constructs a structured evidence packet from mandate and attempt records.
    """
    scheduled_dt = reference_time or (
        datetime.fromisoformat(attempt_dict["scheduled_at"])
        if isinstance(attempt_dict.get("scheduled_at"), str)
        else attempt_dict.get("scheduled_at") or datetime.utcnow()
    )

    amount = float(mandate_dict.get("amount", 0.0))
    bank_code = mandate_dict.get("bank_code", "SBI").upper()
    customer_vpa = mandate_dict.get("customer_vpa", "")
    handle = customer_vpa.split("@")[-1].lower() if "@" in customer_vpa else ""
    expected_bank = VPA_BANK_MAP.get(handle)
    vpa_bank_match = (expected_bank == bank_code) if expected_bank else True

    day = scheduled_dt.day
    hour = scheduled_dt.hour
    is_month_end = day >= 25 or day <= 1
    is_salary_window = 1 <= day <= 7

    bank_health = BankHealthEngine.get_bank_health(bank_code, scheduled_dt)

    created_at = mandate_dict.get("created_at")
    if isinstance(created_at, str):
        created_dt = datetime.fromisoformat(created_at)
    elif isinstance(created_at, datetime):
        created_dt = created_at
    else:
        created_dt = scheduled_dt
    mandate_age_days = max(1, (scheduled_dt - created_dt).days)

    last_success = mandate_dict.get("last_successful_debit")
    if isinstance(last_success, str):
        last_success_dt = datetime.fromisoformat(last_success)
        days_since_last_success = max(0, (scheduled_dt - last_success_dt).days)
    elif isinstance(last_success, datetime):
        days_since_last_success = max(0, (scheduled_dt - last_success).days)
    else:
        days_since_last_success = 30

    history_summaries = []
    recent_codes = []
    if attempts_history_list:
        for att in attempts_history_list[-6:]:
            s_at = att.get("scheduled_at")
            s_at_str = s_at.isoformat() if isinstance(s_at, datetime) else str(s_at)
            code = att.get("response_code")
            if code:
                recent_codes.append(code)
            history_summaries.append(DebitAttemptSummary(
                attempt_number=int(att.get("attempt_number", 1)),
                scheduled_at=s_at_str,
                status=str(att.get("status", "FAILED")),
                response_code=code,
                response_message=att.get("response_message")
            ))

    port_cooldown = mandate_dict.get("portability_cooldown_until")
    in_port_cooldown = False
    if port_cooldown:
        if isinstance(port_cooldown, str):
            in_port_cooldown = datetime.fromisoformat(port_cooldown) > scheduled_dt
        elif isinstance(port_cooldown, datetime):
            in_port_cooldown = port_cooldown > scheduled_dt

    summary_text = (
        f"Mandate {mandate_dict.get('id', 'N/A')} for ₹{amount:,.0f} ({mandate_dict.get('category', 'sub')}) "
        f"on {bank_code} via {mandate_dict.get('psp_app', 'UPI')}. Attempt #{attempt_dict.get('attempt_number', 1)} "
        f"at {hour:02d}:00 on Day {day}. Bank health is {bank_health.status} ({bank_health.health_score*100:.0f}%, "
        f"{bank_health.anomaly_sigma:.1f}σ anomaly). History: {len(history_summaries)} past attempts."
    )

    return EvidencePacket(
        mandate_id=str(mandate_dict.get("id", "")),
        amount=amount,
        bank_code=bank_code,
        customer_vpa=customer_vpa,
        psp_app=str(mandate_dict.get("psp_app", "UPI")),
        category=str(mandate_dict.get("category", "subscription")),
        frequency=str(mandate_dict.get("frequency", "monthly")),
        consent_for_outreach=bool(mandate_dict.get("consent_for_outreach", True)),
        pin_reauth_required=bool(mandate_dict.get("pin_reauth_required", False)),
        scheduled_at=scheduled_dt.isoformat(),
        hour_of_day=hour,
        day_of_month=day,
        day_of_week=scheduled_dt.weekday(),
        is_month_end=is_month_end,
        is_salary_window=is_salary_window,
        bank_health=bank_health,
        vpa_bank_match=vpa_bank_match,
        in_portability_cooldown=in_port_cooldown,
        attempt_number=int(attempt_dict.get("attempt_number", 1)),
        attempts_history=history_summaries,
        days_since_last_success=days_since_last_success,
        mandate_age_days=mandate_age_days,
        recent_failure_codes=recent_codes,
        summary_text=summary_text
    )
