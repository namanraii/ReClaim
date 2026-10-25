"""
Unit tests for the bank health & anomaly signals engine (app/signals/bank_health.py).

These pin down the scoring rules the evidence builder and AI analyst rely on:
baseline lookup, the late-night batch-window factor, simulated shocks, the
failure-rate cap, and the HEALTHY / DEGRADED / OUTAGE_ANOMALY thresholds.
"""

from datetime import datetime

import pytest

from app.signals.bank_health import (
    BANK_BASELINE_RATES,
    BankHealthEngine,
    clear_simulated_bank_shocks,
    set_simulated_bank_shock,
)

MIDDAY = datetime(2026, 1, 15, 12, 0)
LATE_NIGHT = datetime(2026, 1, 15, 2, 0)


@pytest.fixture(autouse=True)
def _reset_shocks():
    clear_simulated_bank_shocks()
    yield
    clear_simulated_bank_shocks()


def test_known_bank_at_midday_is_healthy_at_baseline():
    report = BankHealthEngine.get_bank_health("HDFC", MIDDAY)
    assert report.status == "HEALTHY"
    assert report.baseline_failure_rate == BANK_BASELINE_RATES["HDFC"]
    assert report.rolling_failure_rate_1h == BANK_BASELINE_RATES["HDFC"]
    assert report.anomaly_sigma == 0.0
    assert report.health_score == round(1.0 - BANK_BASELINE_RATES["HDFC"] * 4.0, 2)
    assert report.active_incidents == []
    assert report.timestamp == MIDDAY.isoformat()


def test_bank_code_is_case_insensitive():
    report = BankHealthEngine.get_bank_health("sbi", MIDDAY)
    assert report.bank_code == "SBI"
    assert report.baseline_failure_rate == BANK_BASELINE_RATES["SBI"]


def test_unknown_bank_falls_back_to_default_baseline():
    report = BankHealthEngine.get_bank_health("NEWBANK", MIDDAY)
    assert report.baseline_failure_rate == 0.06
    assert report.status == "HEALTHY"


def test_late_night_batch_window_raises_failure_rate():
    day = BankHealthEngine.get_bank_health("HDFC", MIDDAY)
    night = BankHealthEngine.get_bank_health("HDFC", LATE_NIGHT)
    assert night.rolling_failure_rate_1h == round(BANK_BASELINE_RATES["HDFC"] * 1.3, 4)
    assert night.anomaly_sigma > day.anomaly_sigma
    # 1.3x on HDFC's baseline is ~2.1 sigma: elevated, but not an outage.
    assert night.status == "DEGRADED"
    assert len(night.active_incidents) == 1


def test_simulated_shock_triggers_outage_anomaly():
    set_simulated_bank_shock("ICICI", 3.0)
    report = BankHealthEngine.get_bank_health("ICICI", MIDDAY)
    assert report.status == "OUTAGE_ANOMALY"
    assert report.anomaly_sigma >= 3.0
    assert report.health_score < BankHealthEngine.get_bank_health("HDFC", MIDDAY).health_score
    assert "ICICI" in report.active_incidents[0]


def test_extreme_shock_is_capped_and_health_floored():
    set_simulated_bank_shock("PNB", 100.0)
    report = BankHealthEngine.get_bank_health("PNB", MIDDAY)
    assert report.rolling_failure_rate_1h == 0.95
    assert report.health_score == 0.05


def test_clearing_shocks_restores_baseline():
    set_simulated_bank_shock("AXIS", 5.0)
    assert BankHealthEngine.get_bank_health("AXIS", MIDDAY).status == "OUTAGE_ANOMALY"
    clear_simulated_bank_shocks()
    assert BankHealthEngine.get_bank_health("AXIS", MIDDAY).status == "HEALTHY"


def test_get_all_bank_healths_covers_every_partner_bank():
    reports = BankHealthEngine.get_all_bank_healths()
    assert [r.bank_code for r in reports] == list(BANK_BASELINE_RATES.keys())
    assert all(0.05 <= r.health_score <= 1.0 for r in reports)
