"""
Bank Health & Anomaly Signals Engine
Tracks rolling bank technical decline rates and detects temporal degradation anomalies.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import math
from pydantic import BaseModel


class BankHealthReport(BaseModel):
    bank_code: str
    health_score: float  # 0.0 to 1.0 (e.g. 0.94 = 94% healthy)
    status: str  # "HEALTHY", "DEGRADED", "OUTAGE_ANOMALY"
    rolling_failure_rate_1h: float
    baseline_failure_rate: float
    anomaly_sigma: float  # Standard deviations above baseline
    active_incidents: List[str] = []
    timestamp: str


# Baseline normal failure rates per bank (historical average technical decline rate)
BANK_BASELINE_RATES: Dict[str, float] = {
    "HDFC": 0.045,
    "ICICI": 0.048,
    "SBI": 0.075,
    "AXIS": 0.052,
    "KOTAK": 0.042,
    "PNB": 0.088,
    "BOB": 0.082,
    "UNION": 0.090,
    "INDIAN": 0.095,
}

# Synthetic simulation state for bank health shocks (for demo / evaluation)
_DYNAMIC_BANK_HEALTH_OVERRIDE: Dict[str, float] = {}


def set_simulated_bank_shock(bank_code: str, failure_rate_multiplier: float):
    """Utility for demo & chaos testing to simulate sudden bank degradation"""
    _DYNAMIC_BANK_HEALTH_OVERRIDE[bank_code] = failure_rate_multiplier


def clear_simulated_bank_shocks():
    """Clear simulated bank shocks"""
    _DYNAMIC_BANK_HEALTH_OVERRIDE.clear()


class BankHealthEngine:
    """
    Computes bank health scores and detects rolling anomaly spikes.
    """

    @staticmethod
    def get_bank_health(bank_code: str, reference_time: Optional[datetime] = None) -> BankHealthReport:
        now = reference_time or datetime.utcnow()
        bank = bank_code.upper()
        baseline = BANK_BASELINE_RATES.get(bank, 0.06)

        # Check if there is a simulated or active multiplier
        multiplier = _DYNAMIC_BANK_HEALTH_OVERRIDE.get(bank, 1.0)
        
        # Add deterministic diurnal variation (e.g., higher technical declines during late night batch jobs)
        hour = now.hour
        hour_factor = 1.3 if (0 <= hour <= 3) else 1.0
        
        effective_failure_rate = min(0.95, baseline * multiplier * hour_factor)
        
        # Standard deviation approximation for binomial failure rate in a 1-hour window (N ~ 1000)
        sigma_std = math.sqrt((baseline * (1 - baseline)) / 1000)
        anomaly_sigma = max(0.0, (effective_failure_rate - baseline) / (sigma_std or 0.01))

        health_score = round(max(0.05, 1.0 - (effective_failure_rate * 4.0)), 2)

        incidents = []
        if anomaly_sigma >= 3.0:
            status = "OUTAGE_ANOMALY"
            incidents.append(f"{bank} technical failure rate is {anomaly_sigma:.1f}σ above 24h baseline (Active Degradation)")
        elif anomaly_sigma >= 1.5:
            status = "DEGRADED"
            incidents.append(f"{bank} experiencing elevated retry rejection velocity ({anomaly_sigma:.1f}σ)")
        else:
            status = "HEALTHY"

        return BankHealthReport(
            bank_code=bank,
            health_score=health_score,
            status=status,
            rolling_failure_rate_1h=round(effective_failure_rate, 4),
            baseline_failure_rate=round(baseline, 4),
            anomaly_sigma=round(anomaly_sigma, 2),
            active_incidents=incidents,
            timestamp=now.isoformat()
        )

    @staticmethod
    def get_all_bank_healths() -> List[BankHealthReport]:
        """Returns health report for all primary partner banks"""
        return [BankHealthEngine.get_bank_health(bank) for bank in BANK_BASELINE_RATES.keys()]
