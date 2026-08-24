"""
Portability Guard Agent
Detects mandate portability events to prevent wasted retry attempts on broken links
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid

from app.compliance import NPCIComplianceEngine
from app.db.models import Mandate, AuditLog


class PortabilityGuardAgent:
    """
    Detects mandate portability breakage events based on NPCI OC-223 framework.
    A mandate can be ported across UPI apps only once per 90 days.
    This agent detects port-event signatures before wasting retries on broken links.
    """

    def __init__(self, db_session):
        """
        Initialize portability guard agent
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self.compliance_engine = NPCIComplianceEngine()

    def check_portability_status(self, mandate_id: str) -> Dict:
        """
        Check if a mandate is at risk of portability breakage
        
        Args:
            mandate_id: ID of the mandate to check
            
        Returns:
            Dictionary with portability status and recommendations
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        current_time = datetime.utcnow()
        
        # Check if mandate is within portability cooldown
        in_cooldown = self.compliance_engine.is_within_portability_cooldown(
            mandate.portability_cooldown_until, current_time
        )

        # Check for portability risk indicators
        risk_signals = self._detect_portability_risk_signals(mandate)

        # Determine overall risk level
        risk_level = self._calculate_risk_level(in_cooldown, risk_signals)

        # Generate recommendation
        recommendation = self._generate_recommendation(risk_level, in_cooldown, mandate)

        # Log audit event
        self._log_portability_check(mandate_id, risk_level, in_cooldown, risk_signals)

        return {
            "mandate_id": mandate_id,
            "in_cooldown": in_cooldown,
            "cooldown_end": mandate.portability_cooldown_until.isoformat() if mandate.portability_cooldown_until else None,
            "risk_level": risk_level,
            "risk_signals": risk_signals,
            "recommendation": recommendation
        }

    def _detect_portability_risk_signals(self, mandate: Mandate) -> Dict:
        """
        Detect signals that may indicate portability has occurred or is at risk
        
        Args:
            mandate: Mandate object to check
            
        Returns:
            Dictionary of detected risk signals
        """
        signals = {}

        # Signal 1: Recent failure pattern changes
        # (In real system, would check if failure pattern changed suddenly)
        signals["pattern_change"] = self._check_failure_pattern_change(mandate)

        # Signal 2: VPA inconsistency
        # (In real system, would check if VPA routing changed)
        signals["vpa_inconsistency"] = self._check_vpa_consistency(mandate)

        # Signal 3: App usage pattern change
        # (In real system, would check if PSP app usage changed)
        signals["app_usage_change"] = self._check_app_usage_change(mandate)

        # Signal 4: Cooldown expiry approaching
        if mandate.portability_cooldown_until:
            days_until_expiry = (mandate.portability_cooldown_until - datetime.utcnow()).days
            signals["cooldown_expiry_approaching"] = days_until_expiry < 7
        else:
            signals["cooldown_expiry_approaching"] = False

        return signals

    def _check_failure_pattern_change(self, mandate: Mandate) -> bool:
        """
        Check if failure pattern has changed recently
        Placeholder for actual implementation
        """
        # In real system, would analyze recent debit attempts
        # For now, return False as placeholder
        return False

    def _check_vpa_consistency(self, mandate: Mandate) -> bool:
        """
        Check if VPA routing is consistent
        Placeholder for actual implementation
        """
        # In real system, would check VPA routing records
        # For now, return False as placeholder
        return False

    def _check_app_usage_change(self, mandate: Mandate) -> bool:
        """
        Check if PSP app usage pattern has changed
        Placeholder for actual implementation
        """
        # In real system, would check recent app usage
        # For now, return False as placeholder
        return False

    def _calculate_risk_level(self, in_cooldown: bool, risk_signals: Dict) -> str:
        """
        Calculate overall portability risk level
        
        Args:
            in_cooldown: Whether mandate is in portability cooldown
            risk_signals: Dictionary of detected risk signals
            
        Returns:
            Risk level: "LOW", "MEDIUM", "HIGH"
        """
        high_risk_signals = sum(1 for signal in risk_signals.values() if signal)
        
        if high_risk_signals >= 2:
            return "HIGH"
        elif high_risk_signals == 1:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_recommendation(self, risk_level: str, in_cooldown: bool, mandate: Mandate) -> str:
        """
        Generate recommendation based on risk assessment
        
        Args:
            risk_level: Calculated risk level
            in_cooldown: Whether mandate is in cooldown
            mandate: Mandate object
            
        Returns:
            Recommendation string
        """
        if risk_level == "HIGH":
            return "PORTABILITY_RISK_DETECTED: Do not retry. Mandate may have been ported. Recommend customer re-registration."
        elif risk_level == "MEDIUM":
            if in_cooldown:
                return "MONITOR: Mandate in cooldown. Monitor for additional signals before retry."
            else:
                return "CAUTION: Some risk signals detected. Proceed with retry but monitor closely."
        else:  # LOW
            if in_cooldown:
                return "PROCEED: Mandate in cooldown (protection period). Safe to retry."
            else:
                return "PROCEED: Low portability risk. Safe to retry."

    def _log_portability_check(self, mandate_id: str, risk_level: str, 
                              in_cooldown: bool, risk_signals: Dict):
        """Log portability check to audit trail"""
        import json
        
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type="PORTABILITY_CHECK",
            event_data=json.dumps({
                "risk_level": risk_level,
                "in_cooldown": in_cooldown,
                "risk_signals": risk_signals
            }),
            reason=f"Portability check completed. Risk level: {risk_level}",
            actor="PortabilityGuardAgent",
            timestamp=datetime.utcnow(),
            compliant=True
        )
        
        self.db.add(audit_log)

    def record_portability_event(self, mandate_id: str, new_psp_app: str) -> Dict:
        """
        Record a portability event when a mandate is ported
        
        Args:
            mandate_id: ID of the ported mandate
            new_psp_app: New PSP app after porting
            
        Returns:
            Dictionary with recorded event details
        """
        mandate = self.db.query(Mandate).filter(Mandate.id == mandate_id).first()
        if not mandate:
            raise ValueError(f"Mandate {mandate_id} not found")

        # Update mandate with new portability cooldown
        current_time = datetime.utcnow()
        cooldown_end = current_time + timedelta(days=self.compliance_engine.PORTABILITY_COOLDOWN_DAYS)
        
        mandate.portability_cooldown_until = cooldown_end
        mandate.psp_app = new_psp_app

        # Log audit event
        self._log_portability_event(mandate_id, new_psp_app, cooldown_end)

        self.db.commit()

        return {
            "mandate_id": mandate_id,
            "new_psp_app": new_psp_app,
            "cooldown_until": cooldown_end.isoformat(),
            "event_recorded": True
        }

    def _log_portability_event(self, mandate_id: str, new_psp_app: str, cooldown_end: datetime):
        """Log portability event to audit trail"""
        import json
        
        audit_log = AuditLog(
            id=str(uuid.uuid4()),
            mandate_id=mandate_id,
            event_type="PORTABILITY_EVENT",
            event_data=json.dumps({
                "new_psp_app": new_psp_app,
                "cooldown_end": cooldown_end.isoformat()
            }),
            reason=f"Mandate ported to {new_psp_app}. Cooldown until {cooldown_end}",
            actor="PortabilityGuardAgent",
            timestamp=datetime.utcnow(),
            compliant=True,
            compliance_notes="NPCI OC-223: 90-day portability cooldown enforced"
        )
        
        self.db.add(audit_log)


if __name__ == "__main__":
    print("Portability Guard Agent Module")
    print("This agent detects mandate portability events to prevent wasted retry attempts on broken links.")
