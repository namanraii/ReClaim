# Reclaim Evaluation Report

> **Methodology:** Measured on 500 synthetic mandates. Recovery simulation uses the trained
> XGBoost classifier, NPCI compliance engine, and category-specific recovery rates.
> Confidence intervals from 5 seeded train/test splits.

## Classification Performance

- **F1 Macro:** 0.287
- **F1 Weighted:** 0.677

## Ablation Study Results

| Configuration | Recovery Rate | Revenue Recovered (₹) | False Nudge Rate |
|---|---|---|---|
| full_system | 58.9% (±0.8%) | ₹9,862,974 (±333,347) | 9.4% |
| no_classifier | 48.4% (±1.4%) | ₹8,963,516 (±352,176) | 12.9% |
| no_smart_retry | 44.2% (±0.9%) | ₹7,145,316 (±245,980) | 9.4% |
| no_nudge | 51.4% (±0.5%) | ₹7,881,189 (±221,588) | 0.0% |
| baseline | 30.4% (±1.0%) | ₹4,882,348 (±137,819) | 0.0% |

## Component Impact Analysis

- **Recovery Rate Lift vs Baseline:** +28.4%
- **ML Classifier Contribution:** +10.4%
- **Smart Retry Contribution:** +14.6%
- **Customer Nudge Contribution:** +7.5%

## Data Limitations

- Evaluation on synthetic data grounded in NPCI/RBI rules
- Recovery outcomes simulated with category-specific rates (deterministic, seeded)
- Real-world performance will vary with production merchant data