# Reclaim Evaluation Report

> **Methodology:** Measured on 500 synthetic mandates. Recovery simulation uses the trained
> XGBoost classifier (with balanced sample weights), NPCI compliance engine, and
> category-specific recovery rates. Confidence intervals from 5 seeded train/test splits.

## Training Label Distribution

| Failure Category | Count | Share |
|---|---:|---:|
| NPCI_WINDOW_VIOLATION | 1201 | 25.8% |
| LOW_BALANCE | 315 | 6.8% |
| PORTABILITY_BREAKAGE | 880 | 18.9% |
| PRE_DEBIT_OPT_OUT | 209 | 4.5% |
| BANK_TECHNICAL_DECLINE | 1535 | 33.0% |
| PIN_REAUTH_REQUIRED | 516 | 11.1% |

## Classification Performance

- **F1 Macro:** 0.536
- **F1 Weighted:** 0.611

> Macro F1 reflects performance across all 6 categories equally. Weighted F1 is
> dominated by the majority class — both are reported for transparency.

### Per-Category Metrics (Test Set)

| Category | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| NPCI_WINDOW_VIOLATION | 1.00 | 1.00 | 1.00 | 241 |
| LOW_BALANCE | 0.46 | 0.87 | 0.60 | 63 |
| PORTABILITY_BREAKAGE | 0.37 | 0.26 | 0.30 | 176 |
| PRE_DEBIT_OPT_OUT | 0.17 | 0.12 | 0.14 | 42 |
| BANK_TECHNICAL_DECLINE | 0.60 | 0.50 | 0.55 | 307 |
| PIN_REAUTH_REQUIRED | 0.51 | 0.81 | 0.62 | 103 |

### Confusion Matrix (Test Set)

| Actual \ Predicted | BANK_TECHNICAL_DECLINE | LOW_BALANCE | NPCI_WINDOW_VIOLATION | PIN_REAUTH_REQUIRED | PORTABILITY_BREAKAGE | PRE_DEBIT_OPT_OUT |
|---|---|---|---|---|---|---|
| **BANK_TECHNICAL_DECLINE** | 154 | 25 | 0 | 54 | 64 | 10 |
| **LOW_BALANCE** | 5 | 55 | 0 | 2 | 1 | 0 |
| **NPCI_WINDOW_VIOLATION** | 0 | 0 | 241 | 0 | 0 | 0 |
| **PIN_REAUTH_REQUIRED** | 6 | 10 | 0 | 83 | 1 | 3 |
| **PORTABILITY_BREAKAGE** | 75 | 23 | 0 | 21 | 45 | 12 |
| **PRE_DEBIT_OPT_OUT** | 18 | 6 | 0 | 3 | 10 | 5 |

## Ablation Study Results

| Configuration | Recovery Rate | Revenue Recovered (₹) | False Nudge Rate |
|---|---|---|---|
| full_system | 56.8% (±1.5%) | ₹11,431,198 (±636,240) | 6.4% |
| no_classifier | 41.8% (±1.2%) | ₹9,022,183 (±437,190) | 6.7% |
| no_smart_retry | 41.9% (±1.8%) | ₹8,386,299 (±341,963) | 6.4% |
| no_nudge | 49.2% (±0.8%) | ₹9,496,797 (±358,325) | 0.0% |
| baseline | 25.0% (±1.0%) | ₹4,254,847 (±211,826) | 0.0% |

## Component Impact Analysis

- **Recovery Rate Lift vs Baseline:** +31.8%
- **ML Classifier Contribution:** +15.0%
- **Smart Retry Contribution:** +14.9%
- **Customer Nudge Contribution:** +7.6%

## Data Limitations

- Evaluation on synthetic data grounded in NPCI/RBI rules
- Recovery outcomes simulated with category-specific rates (deterministic, seeded)
- Minority classes (portability, opt-out) remain harder to classify than majority classes
- Real-world performance will vary with production merchant data