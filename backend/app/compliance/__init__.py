"""
NPCI Compliance Engine
Enforces UPI AutoPay execution rules and constraints
"""

from datetime import datetime, time, timedelta
from typing import Tuple, Optional
from enum import Enum


class ComplianceViolationType(str, Enum):
    PEAK_HOUR_VIOLATION = "PEAK_HOUR_VIOLATION"
    RETRY_LIMIT_EXCEEDED = "RETRY_LIMIT_EXCEEDED"
    INSUFFICIENT_COOLDOWN = "INSUFFICIENT_COOLDOWN"
    PORTABILITY_COOLDOWN_VIOLATION = "PORTABILITY_COOLDOWN_VIOLATION"
    PIN_REAUTH_REQUIRED = "PIN_REAUTH_REQUIRED"


class NPCIComplianceEngine:
    """
    Enforces NPCI UPI AutoPay compliance rules based on:
    - NPCI circular OC/215A/2025-26 (May 21, 2025; enforced Aug 1, 2025)
    - NPCI OC-223 (Oct 7, 2025; compliance deadline Dec 31, 2025)
    - RBI 2026 e-mandate Master Directions
    """

    # Peak hours when mandate execution is blocked (NPCI OC/215A)
    PEAK_HOURS = [
        (time(10, 0), time(13, 0)),   # 10 AM – 1 PM
        (time(17, 0), time(21, 30))   # 5 PM – 9:30 PM
    ]

    # Maximum retry attempts per mandate per cycle (1 original + 3 retries)
    MAX_RETRY_ATTEMPTS = 4

    # Minimum cooldown between status checks (3 per 2 hours, ≥90s apart)
    STATUS_CHECK_COOLDOWN_SECONDS = 90

    # Portability cooldown (once per 90 days)
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
        Returns False if time falls within peak hours.
        """
        check_time = scheduled_time.time()
        day_of_week = scheduled_time.weekday()

        # Skip weekends (some banks don't process on weekends)
        if day_of_week >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Check if time falls within any peak hour block
        for start, end in NPCIComplianceEngine.PEAK_HOURS:
            if start <= check_time <= end:
                return False

        return True

    @staticmethod
    def get_next_valid_execution_window(from_time: datetime) -> Tuple[datetime, datetime]:
        """
        Get the next valid execution window after from_time.
        Returns (window_start, window_end) tuple.
        """
        current = from_time

        # Find next non-peak, non-weekend slot
        while True:
            # Skip to next day if weekend
            if current.weekday() >= 5:
                current = current.replace(hour=0, minute=0, second=0, microsecond=0)
                current = current + timedelta(days=1)
                continue

            # Check if current time is in peak hours
            check_time = current.time()
            in_peak_hours = False
            for start, end in NPCIComplianceEngine.PEAK_HOURS:
                if start <= check_time <= end:
                    in_peak_hours = True
                    break

            if in_peak_hours:
                # Move to end of current peak hour block
                for start, end in NPCIComplianceEngine.PEAK_HOURS:
                    if start <= check_time <= end:
                        current = current.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
                        break
            else:
                # Found valid window
                window_end = current.replace(hour=23, minute=59, second=59)
                return current, window_end

            # Move forward if still in peak hours
            current = current + timedelta(minutes=1)

    @staticmethod
    def can_attempt_retry(current_attempt: int, max_attempts: int = MAX_RETRY_ATTEMPTS) -> bool:
        """
        Check if retry attempt is within NPCI limits.
        """
        return current_attempt <= max_attempts

    @staticmethod
    def requires_pin_reauth(amount: float, category: Optional[str] = None) -> bool:
        """
        Check if debit requires PIN re-authentication based on amount and category.
        Uses RBI 2026 e-mandate thresholds.
        """
        if category in NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_CATEGORIES:
            return amount > NPCIComplianceEngine.PIN_REAUTH_EXCEPTION_THRESHOLD
        return amount > NPCIComplianceEngine.PIN_REAUTH_DEFAULT_THRESHOLD

    @staticmethod
    def is_within_portability_cooldown(
        last_port_date: Optional[datetime],
        current_date: datetime
    ) -> bool:
        """
        Check if mandate is within 90-day portability cooldown.
        Returns True if cooldown is active (porting not allowed).
        """
        if last_port_date is None:
            return False

        days_since_port = (current_date - last_port_date).days
        return days_since_port < NPCIComplianceEngine.PORTABILITY_COOLDOWN_DAYS

    @staticmethod
    def can_check_status(last_check_time: Optional[datetime], current_time: datetime) -> bool:
        """
        Check if status check complies with NPCI throttling rules.
        Maximum 3 checks per 2 hours, with ≥90s between checks.
        """
        if last_check_time is None:
            return True

        seconds_since_last_check = (current_time - last_check_time).total_seconds()
        return seconds_since_last_check >= NPCIComplianceEngine.STATUS_CHECK_COOLDOWN_SECONDS

    @staticmethod
    def validate_retry_schedule(
        scheduled_time: datetime,
        attempt_number: int,
        mandate_amount: float,
        mandate_category: Optional[str] = None,
        last_port_date: Optional[datetime] = None
    ) -> Tuple[bool, list[ComplianceViolationType]]:
        """
        Comprehensive validation of a retry schedule against all NPCI rules.
        Returns (is_compliant, list_of_violations).
        """
        violations = []

        # Check execution window
        if not NPCIComplianceEngine.is_within_execution_window(scheduled_time):
            violations.append(ComplianceViolationType.PEAK_HOUR_VIOLATION)

        # Check retry limit
        if not NPCIComplianceEngine.can_attempt_retry(attempt_number):
            violations.append(ComplianceViolationType.RETRY_LIMIT_EXCEEDED)

        # Check PIN re-auth requirement
        if NPCIComplianceEngine.requires_pin_reauth(mandate_amount, mandate_category):
            violations.append(ComplianceViolationType.PIN_REAUTH_REQUIRED)

        # Check portability cooldown
        if NPCIComplianceEngine.is_within_portability_cooldown(last_port_date, scheduled_time):
            violations.append(ComplianceViolationType.PORTABILITY_COOLDOWN_VIOLATION)

        return len(violations) == 0, violations



