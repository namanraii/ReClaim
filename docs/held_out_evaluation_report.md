# Reclaim 2.0 Held-Out Batch Evaluation Report
> **Evaluation Dataset:** 2,000 held-out mandates (19371 failed debit attempts) evaluated under intentional distribution shifts (bank outage shocks, ticket size surges, and month-end salary clustering).
> *Methodology note: Simulated evaluation on held-out synthetic data under explicit regulatory and payment rail constraints.*

---

## 🏆 Headline Track 03 Metrics

| Primary Outcome Metric | Reclaim (Decision Engine) | Naive Retry Baseline | Net Incremental Gain |
|---|---|---|---|
| **Total Revenue Recovered (₹)** | **₹188,551,122.00** | ₹117,690,447.00 | **+₹70,860,675.00 (+60.2% Uplift)** |
| **Compliance Violation Rate** | **0.0% (Zero Violations)** | 25.7% (4,977 violations) | **100% Policy Enforced** |

---

## 📊 Supporting Decision Intelligence Metrics

| Metric | Reclaim | Naive Baseline | Performance Note |
|---|---|---|---|
| **Recovery Rate (%)** | **44.8%** | 26.7% | **+18.1% Absolute Lift** |
| **Wrong-Action Rate (%)** | **5.4%** | 42.6% | **Substantial error reduction** |
| **AI Abstention Rate (%)** | **3.8%** | 0.0% | **Safe deferral on high uncertainty** |
| **Unnecessary Contact Rate (%)** | **80.6%** | N/A | **DPDPA consent-gated outreach** |
| **Total Retry Attempts** | **3,035** | 19,371 | **Fewer wasted attempts** |

---

## 🔬 Distribution Shift Stress Tests

1. **Bank Outage Anomaly:** SBI & PNB failure rate scaled 3.2σ above baseline. Reclaim automatically avoided immediate re-attempts on degraded rails, routing into batch execution windows once health normalized.
2. **High-Ticket PIN Re-Auth:** ₹15k–₹1L thresholds enforced without attempting illegal automated blind debits.
3. **Salary Timing Alignment:** Month-end liquidity failures scheduled for national salary credit windows, driving low-balance recovery to 89%.
