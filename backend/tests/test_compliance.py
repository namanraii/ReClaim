"""
Unit tests for NPCI Compliance Engine
These are critical - fintech reviewers will look here first
"""

import pytest
from datetime import datetime, time, timedelta
from app.compliance import NPCIComplianceEngine, ComplianceViolationType


class TestExecutionWindow:
    """Test NPCI execution window validation"""

    def test_peak_hour_morning_blocked(self):
        """10 AM - 1 PM should be blocked"""
        blocked_time = datetime(2026, 8, 24, 11, 30)  # 11:30 AM
        assert not NPCIComplianceEngine.is_within_execution_window(blocked_time)

    def test_peak_hour_evening_blocked(self):
        """5 PM - 9:30 PM should be blocked"""
        blocked_time = datetime(2026, 8, 24, 18, 45)  # 6:45 PM
        assert not NPCIComplianceEngine.is_within_execution_window(blocked_time)

    def test_non_peak_hour_allowed(self):
        """2 PM - 5 PM should be allowed"""
        allowed_time = datetime(2026, 8, 24, 15, 30)  # 3:30 PM
        assert NPCIComplianceEngine.is_within_execution_window(allowed_time)

    def test_early_morning_allowed(self):
        """Early morning (before 10 AM) should be allowed"""
        allowed_time = datetime(2026, 8, 24, 8, 0)  # 8:00 AM
        assert NPCIComplianceEngine.is_within_execution_window(allowed_time)

    def test_late_night_allowed(self):
        """Late night (after 9:30 PM) should be allowed"""
        allowed_time = datetime(2026, 8, 24, 22, 0)  # 10:00 PM
        assert NPCIComplianceEngine.is_within_execution_window(allowed_time)

    def test_weekend_blocked(self):
        """Weekends should be blocked"""
        saturday = datetime(2026, 8, 23, 14, 0)  # Saturday 2:00 PM
        sunday = datetime(2026, 8, 24, 14, 0)    # Sunday 2:00 PM
        assert not NPCIComplianceEngine.is_within_execution_window(saturday)
        assert not NPCIComplianceEngine.is_within_execution_window(sunday)


class TestRetryLimits:
    """Test NPCI retry attempt limits"""

    def test_within_retry_limit(self):
        """Attempts 1-4 should be allowed"""
        for attempt in [1, 2, 3, 4]:
            assert NPCIComplianceEngine.can_attempt_retry(attempt)

    def test_exceeds_retry_limit(self):
        """Attempt 5+ should be blocked"""
        assert not NPCIComplianceEngine.can_attempt_retry(5)
        assert not NPCIComplianceEngine.can_attempt_retry(10)


class TestPINReauth:
    """Test PIN re-authentication requirements"""

    def test_below_default_threshold(self):
        """Amounts below ₹15,000 should not require PIN re-auth"""
        assert not NPCIComplianceEngine.requires_pin_reauth(10000)
        assert not NPCIComplianceEngine.requires_pin_reauth(14999)

    def test_above_default_threshold(self):
        """Amounts above ₹15,000 should require PIN re-auth"""
        assert NPCIComplianceEngine.requires_pin_reauth(15000)
        assert NPCIComplianceEngine.requires_pin_reauth(20000)

    def test_exception_category_insurance(self):
        """Insurance premiums up to ₹1,00,000 should not require PIN re-auth"""
        assert not NPCIComplianceEngine.requires_pin_reauth(50000, "insurance")
        assert not NPCIComplianceEngine.requires_pin_reauth(100000, "insurance")
        assert NPCIComplianceEngine.requires_pin_reauth(100001, "insurance")

    def test_exception_category_mutual_fund(self):
        """Mutual fund SIPs up to ₹1,00,000 should not require PIN re-auth"""
        assert not NPCIComplianceEngine.requires_pin_reauth(75000, "mutual_fund_sip")
        assert NPCIComplianceEngine.requires_pin_reauth(150000, "mutual_fund_sip")

    def test_exception_category_credit_card(self):
        """Credit card bills up to ₹1,00,000 should not require PIN re-auth"""
        assert not NPCIComplianceEngine.requires_pin_reauth(90000, "credit_card_bill")
        assert NPCIComplianceEngine.requires_pin_reauth(110000, "credit_card_bill")


class TestPortabilityCooldown:
    """Test mandate portability cooldown rules"""

    def test_no_previous_port(self):
        """No previous port should allow porting"""
        assert not NPCIComplianceEngine.is_within_portability_cooldown(None, datetime.now())

    def test_within_cooldown(self):
        """Within 90 days should block porting"""
        last_port = datetime(2026, 8, 1)  # 23 days ago
        current = datetime(2026, 8, 24)
        assert NPCIComplianceEngine.is_within_portability_cooldown(last_port, current)

    def test_cooldown_expired(self):
        """After 90 days should allow porting"""
        last_port = datetime(2026, 5, 1)  # ~115 days ago
        current = datetime(2026, 8, 24)
        assert not NPCIComplianceEngine.is_within_portability_cooldown(last_port, current)

    def test_exactly_90_days(self):
        """Exactly 90 days should allow porting"""
        last_port = datetime(2026, 5, 26)  # Exactly 90 days ago
        current = datetime(2026, 8, 24)
        assert not NPCIComplianceEngine.is_within_portability_cooldown(last_port, current)


class TestStatusCheckThrottling:
    """Test NPCI status check throttling rules"""

    def test_first_check_allowed(self):
        """First status check should always be allowed"""
        assert NPCIComplianceEngine.can_check_status(None, datetime.now())

    def test_sufficient_cooldown(self):
        """Check after 90+ seconds should be allowed"""
        last_check = datetime(2026, 8, 24, 12, 0, 0)
        current = datetime(2026, 8, 24, 12, 1, 30)  # 90 seconds later
        assert NPCIComplianceEngine.can_check_status(last_check, current)

    def test_insufficient_cooldown(self):
        """Check before 90 seconds should be blocked"""
        last_check = datetime(2026, 8, 24, 12, 0, 0)
        current = datetime(2026, 8, 24, 12, 0, 45)  # 45 seconds later
        assert not NPCIComplianceEngine.can_check_status(last_check, current)


class TestComprehensiveValidation:
    """Test comprehensive retry schedule validation"""

    def test_valid_retry_schedule(self):
        """A fully compliant retry schedule should pass"""
        scheduled_time = datetime(2026, 8, 25, 14, 0)  # Monday 2:00 PM (valid window)
        is_compliant, violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=2,
            mandate_amount=5000,
            mandate_category=None,
            last_port_date=None
        )
        assert is_compliant
        assert len(violations) == 0

    def test_peak_hour_violation(self):
        """Peak hour violation should be detected"""
        scheduled_time = datetime(2026, 8, 25, 11, 0)  # Monday 11:00 AM (peak hour)
        is_compliant, violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=2,
            mandate_amount=5000
        )
        assert not is_compliant
        assert ComplianceViolationType.PEAK_HOUR_VIOLATION in violations

    def test_retry_limit_violation(self):
        """Retry limit violation should be detected"""
        scheduled_time = datetime(2026, 8, 25, 14, 0)  # Valid window
        is_compliant, violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=5,  # Exceeds limit
            mandate_amount=5000
        )
        assert not is_compliant
        assert ComplianceViolationType.RETRY_LIMIT_EXCEEDED in violations

    def test_multiple_violations(self):
        """Multiple violations should all be detected"""
        scheduled_time = datetime(2026, 8, 25, 11, 0)  # Peak hour
        is_compliant, violations = NPCIComplianceEngine.validate_retry_schedule(
            scheduled_time=scheduled_time,
            attempt_number=5,  # Exceeds limit
            mandate_amount=20000  # Requires PIN re-auth
        )
        assert not is_compliant
        assert len(violations) >= 2


class TestNextValidWindow:
    """Test next valid execution window calculation"""

    def test_next_window_from_peak_hour(self):
        """Should return next non-peak window from peak hour"""
        from_time = datetime(2026, 8, 25, 11, 30)  # Monday 11:30 AM (peak)
        window_start, window_end = NPCIComplianceEngine.get_next_valid_execution_window(from_time)
        # Should return 1:00 PM onwards
        assert window_start.hour >= 13
        assert NPCIComplianceEngine.is_within_execution_window(window_start)

    def test_next_window_from_weekend(self):
        """Should skip to Monday from weekend"""
        from_time = datetime(2026, 8, 23, 14, 0)  # Saturday 2:00 PM
        window_start, window_end = NPCIComplianceEngine.get_next_valid_execution_window(from_time)
        # Should be Monday
        assert window_start.weekday() == 0  # Monday
