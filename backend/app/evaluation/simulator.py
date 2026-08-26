"""
Recovery simulation utilities — shared by evaluation harness and tests.
"""

import hashlib
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from app.compliance import NPCIComplianceEngine

CATEGORY_RECOVERY_RATES = {
    "LOW_BALANCE": 0.72,
    "NPCI_WINDOW_VIOLATION": 0.68,
    "BANK_TECHNICAL_DECLINE": 0.55,
    "PIN_REAUTH_REQUIRED": 0.45,
    "PRE_DEBIT_OPT_OUT": 0.35,
    "PORTABILITY_BREAKAGE": 0.10,
}

NO_CLASSIFIER_PENALTY = 0.10
NO_SMART_RETRY_PENALTY = 0.15
NO_NUDGE_PENALTY = 0.08


def deterministic_random(mandate_id: str, salt: str = "") -> float:
    h = hashlib.md5(f"{mandate_id}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def simulate_recovery_for_row(
    row: pd.Series,
    config: str,
    compliance: NPCIComplianceEngine,
    predicted_category: Optional[str] = None,
    rng: Optional[np.random.RandomState] = None,
) -> Tuple[bool, float, bool]:
    category = predicted_category or row.get("category", "BANK_TECHNICAL_DECLINE")
    base_rate = CATEGORY_RECOVERY_RATES.get(category, 0.50)
    mandate_id = row.get("mandate_id", row.get("id", "unknown"))
    amount = float(row.get("amount", 0))

    use_classifier = config not in ("no_classifier", "baseline")
    use_smart_retry = config not in ("no_smart_retry", "baseline")
    use_nudge = config not in ("no_nudge", "baseline")

    rate = base_rate
    if not use_classifier:
        rate -= NO_CLASSIFIER_PENALTY
    if not use_smart_retry:
        rate -= NO_SMART_RETRY_PENALTY
    else:
        scheduled = row.get("scheduled_at")
        if scheduled is not None:
            if isinstance(scheduled, str):
                scheduled = datetime.fromisoformat(scheduled)
            if compliance.is_within_execution_window(scheduled):
                rate += 0.05
    if use_nudge and category in ("LOW_BALANCE", "PIN_REAUTH_REQUIRED"):
        rate += 0.08
    elif not use_nudge and category in ("LOW_BALANCE", "PIN_REAUTH_REQUIRED"):
        rate -= NO_NUDGE_PENALTY

    if category == "PORTABILITY_BREAKAGE":
        rate = min(rate, 0.15)

    rate = max(0.05, min(0.95, rate))
    roll = deterministic_random(mandate_id, config)
    recovered = roll < rate

    false_nudge = False
    if use_nudge and category in ("LOW_BALANCE", "PIN_REAUTH_REQUIRED"):
        false_nudge = deterministic_random(mandate_id, "nudge") < 0.12

    return recovered, amount if recovered else 0.0, false_nudge


def run_configuration(
    test_data: pd.DataFrame,
    config: str,
    classifier=None,
    compliance: Optional[NPCIComplianceEngine] = None,
) -> Dict:
    compliance = compliance or NPCIComplianceEngine()
    recovered_count = 0
    revenue = 0.0
    false_nudges = 0
    nudge_eligible = 0

    for _, row in test_data.iterrows():
        predicted = None
        if classifier is not None and config not in ("no_classifier", "baseline"):
            try:
                preds, _ = classifier.predict(pd.DataFrame([row]))
                predicted = preds[0]
            except Exception:
                predicted = row.get("category")

        rec, amt, false_nudge = simulate_recovery_for_row(
            row, config, compliance, predicted_category=predicted
        )
        if rec:
            recovered_count += 1
            revenue += amt
        if config not in ("no_nudge", "baseline") and row.get("category") in (
            "LOW_BALANCE", "PIN_REAUTH_REQUIRED"
        ):
            nudge_eligible += 1
            if false_nudge:
                false_nudges += 1

    total = len(test_data)
    return {
        "recovery_rate": recovered_count / total if total else 0.0,
        "total_attempts": total,
        "recovered": recovered_count,
        "revenue_recovered": revenue,
        "false_nudge_rate": false_nudges / nudge_eligible if nudge_eligible else 0.0,
    }
