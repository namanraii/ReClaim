"""
Portability Guard Agent
Detects mandate portability events to prevent wasted retry attempts on broken links
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import json

from app.compliance import NPCIComplianceEngine
from app.db.models import Mandate, DebitAttempt, DebitStatus, FailureEvent, FailureCategory, AuditLog

# VPA handle suffix → expected bank code
VPA_BANK_MAP = {
    "okhdfc": "HDFC",
    "okicici": "ICICI",
    "oksbi": "SBI",
    "okaxis": "AXIS",
    "okkotak": "KOTAK",
    "okpnb": "PNB",
    "okbob": "BOB",
}


class PortabilityGuardAgent:
    """
    Detects mandate portability breakage events based on NPCI OC-223 framework.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.compliance_engine = NPCIComplianceEngine()

    def check_portability_status(self, mandate_id: str) -> Dict:
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        current_time = datetime.utcnow()
        in_cooldown = self.compliance_engine.is_within_portability_cooldown(
            mandate.portability_cooldown_until, current_time
        )
        risk_signals = self._detect_portability_risk_signals(mandate)
        risk_level = self._calculate_risk_level(in_cooldown, risk_signals)
        recommendation = self._generate_recommendation(risk_level, in_cooldown, mandate)
        self._log_portability_check(mandate_id, risk_level, in_cooldown, risk_signals)

        return {
            "mandate_id": mandate_id,
            "in_cooldown": in_cooldown,
            "cooldown_end": mandate.portability_cooldown_until.isoformat() if mandate.portability_cooldown_until else None,
            "risk_level": risk_level,
            "risk_signals": risk_signals,
            "recommendation": recommendation,
        }

    def _get_recent_failures(self, mandate_id: str, limit: int = 5) -> List[FailureEvent]:
        attempts = (
            self.db.query(DebitAttempt)
            .filter(DebitAttempt.mandate_id == mandate_id, DebitAttempt.status == DebitStatus.FAILED)
            .order_by(DebitAttempt.scheduled_at.desc())
            .limit(limit)
            .all()
        )
        events = []
        for attempt in attempts:
            events.extend(attempt.failure_events)
        return events

    def _check_failure_pattern_change(self, mandate: Mandate) -> bool:
        """Detect sudden category shift in recent failures vs earlier pattern."""
        events = self._get_recent_failures(mandate.id, limit=6)
        if len(events) < 3:
            return False
        recent_cats = {e.category for e in events[:2]}
        older_cats = {e.category for e in events[2:]}
        # Sudden shift to portability or bank decline after stable low-balance pattern
        if FailureCategory.PORTABILITY_BREAKAGE in recent_cats and FailureCategory.PORTABILITY_BREAKAGE not in older_cats:
            return True
        if recent_cats != older_cats and FailureCategory.BANK_TECHNICAL_DECLINE in recent_cats:
            return True
        return False

    def _check_vpa_consistency(self, mandate: Mandate) -> bool:
        """Flag when VPA bank handle doesn't match mandate bank_code."""
        vpa = mandate.customer_vpa.lower()
        handle = vpa.split("@")[-1] if "@" in vpa else ""
        expected_bank = VPA_BANK_MAP.get(handle)
        if expected_bank and expected_bank != mandate.bank_code:
            return True
        return False

    def _check_app_usage_change(self, mandate: Mandate) -> bool:
        """Detect portability via recent PORTABILITY_BREAKAGE failures or audit events."""
        events = self._get_recent_failures(mandate.id, limit=3)
        if any(e.category == FailureCategory.PORTABILITY_BREAKAGE for e in events):
            return True
        recent_port_event = (
            self.db.query(AuditLog)
            .filter(
                AuditLog.mandate_id == mandate.id,
                AuditLog.event_type == "PORTABILITY_EVENT",
            )
            .order_by(AuditLog.timestamp.desc())
            .first()
        )
        if recent_port_event:
            event_time = recent_port_event.timestamp
            if (datetime.utcnow() - event_time).days < 30:
                return True
        return False

    def _detect_portability_risk_signals(self, mandate: Mandate) -> Dict:
        signals = {
            "pattern_change": self._check_failure_pattern_change(mandate),
            "vpa_inconsistency": self._check_vpa_consistency(mandate),
            "app_usage_change": self._check_app_usage_change(mandate),
        }
        if mandate.portability_cooldown_until:
            days_until_expiry = (mandate.portability_cooldown_until - datetime.utcnow()).days
            signals["cooldown_expiry_approaching"] = days_until_expiry < 7
        else:
            signals["cooldown_expiry_approaching"] = False
        return signals

    def _calculate_risk_level(self, in_cooldown: bool, risk_signals: Dict) -> str:
        high_risk_signals = sum(1 for signal in risk_signals.values() if signal)
        if high_risk_signals >= 2:
            return "HIGH"
        elif high_risk_signals == 1:
            return "MEDIUM"
        return "LOW"

    def _generate_recommendation(self, risk_level: str, in_cooldown: bool, mandate: Mandate) -> str:
        if risk_level == "HIGH":
            return "PORTABILITY_RISK_DETECTED: Do not retry. Mandate may have been ported. Recommend customer re-registration."
        elif risk_level == "MEDIUM":
            if in_cooldown:
                return "MONITOR: Mandate in cooldown. Monitor for additional signals before retry."
            return "CAUTION: Some risk signals detected. Proceed with retry but monitor closely."
        if in_cooldown:
            return "PROCEED: Mandate in cooldown (protection period). Safe to retry."
        return "PROCEED: Low portability risk. Safe to retry."

    def _log_portability_check(self, mandate_id: str, risk_level: str,
                              in_cooldown: bool, risk_signals: Dict):
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type="PORTABILITY_CHECK",
            event_data=json.dumps({
                "risk_level": risk_level,
                "in_cooldown": in_cooldown,
                "risk_signals": risk_signals,
            }),
            reason=f"Portability check completed. Risk level: {risk_level}",
            actor="PortabilityGuardAgent",
            timestamp=datetime.utcnow(),
            compliant=True,
        )
        self.db.add(audit_log)
        self.db.commit()

    def record_portability_event(self, mandate_id: str, new_psp_app: str) -> Dict:
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        current_time = datetime.utcnow()
        cooldown_end = current_time + timedelta(days=self.compliance_engine.PORTABILITY_COOLDOWN_DAYS)
        mandate.portability_cooldown_until = cooldown_end
        mandate.psp_app = new_psp_app
        self._log_portability_event(mandate_id, new_psp_app, cooldown_end)
        self.db.commit()

        return {
            "mandate_id": mandate_id,
            "new_psp_app": new_psp_app,
            "cooldown_until": cooldown_end.isoformat(),
            "event_recorded": True,
        }

    def _log_portability_event(self, mandate_id: str, new_psp_app: str, cooldown_end: datetime):
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type="PORTABILITY_EVENT",
            event_data=json.dumps({
                "new_psp_app": new_psp_app,
                "cooldown_end": cooldown_end.isoformat(),
            }),
            reason=f"Mandate ported to {new_psp_app}. Cooldown until {cooldown_end}",
            actor="PortabilityGuardAgent",
            timestamp=datetime.utcnow(),
            compliant=True,
            compliance_notes="NPCI OC-223: 90-day portability cooldown enforced",
        )
        self.db.add(audit_log)
