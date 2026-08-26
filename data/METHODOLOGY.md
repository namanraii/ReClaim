# Synthetic Data Methodology for Reclaim

## Overview
This document describes the methodology used to generate synthetic UPI AutoPay mandate data for the Reclaim project. All generation rules are grounded in actual NPCI and RBI regulations, with specific sources cited.

## Data Generation Rules and Sources

### 1. NPCI Execution Window Rules
**Source:** NPCI Circular OC/215A/2025-26 (May 21, 2025; enforced August 1, 2025)

**Rules Implemented:**
- **Peak Hour Blackout:** Mandate execution is blocked during:
  - 10:00 AM – 1:00 PM
  - 5:00 PM – 9:30 PM
- **Weekend Restriction:** Many banks do not process mandate debits on weekends (Saturday/Sunday)
- **Optimal Processing Window:** Early morning batch processing (2:00 AM – 8:00 AM) modeled as highest success probability

**Implementation in Synthetic Data:**
- ~60% of scheduled times fall in early morning (2–8 AM) — highest success probability
- ~25% fall in NPCI peak hours (10 AM–1 PM, 5 PM–9 PM) — generates `NPCI_WINDOW_VIOLATION` labels
- ~15% fall in other off-peak slots (8–10 AM, 1–5 PM, after 9:30 PM)
- Peak hour attempts have 30% lower success probability
- Weekend scheduling is avoided in the generator

### 2. NPCI Retry Limits
**Source:** NPCI Circular OC/215A/2025-26

**Rules Implemented:**
- **Maximum Attempts:** 4 total attempts per mandate per cycle (1 original + 3 retries)
- **Status Check Throttling:** Maximum 3 status checks per 2 hours, with minimum 90 seconds between checks
- **TPS Limits:** Transaction processing throttled during peak hours

**Implementation in Synthetic Data:**
- Each mandate generates maximum 4 debit attempts per cycle
- Retry attempts have decreasing success probability (70%, 50%, 30%)
- Idempotency keys generated for each attempt to prevent double-debit

### 3. PIN Re-authentication Thresholds
**Source:** RBI 2026 E-mandate Master Directions

**Rules Implemented:**
- **Default Threshold:** ₹15,000 requires per-debit AFA (Additional Factor Authentication)
- **Exception Threshold:** ₹1,00,000 for:
  - Insurance premiums
  - Mutual fund SIPs
  - Credit card bills
- **Below Threshold:** No PIN re-auth required

**Implementation in Synthetic Data:**
- Mandates are categorized (insurance, mutual_fund_sip, credit_card_bill, subscription, utility, emi)
- Amounts generated between ₹100 – ₹50,000
- PIN re-auth requirement calculated based on amount and category
- PIN re-auth failures modeled as a distinct failure category

### 4. Mandate Portability Rules
**Source:** NPCI Circular OC-223 (October 7, 2025; compliance deadline December 31, 2025)

**Rules Implemented:**
- **Portability Limit:** One port per 90 days per mandate
- **Central Portal:** upihelp.npci.org.in for portability management
- **UPI PIN Required:** Every mandate action requires UPI PIN authentication
- **Link Breakage:** Merchant-side links can silently break on port

**Implementation in Synthetic Data:**
- Portability cooldown tracked per mandate (90 days)
- Portability breakage modeled as random failure event (5% probability)
- Portability validation in compliance engine

### 5. Pre-debit Notification Requirements
**Source:** RBI 2026 E-mandate Master Directions

**Rules Implemented:**
- **Notification Window:** Minimum 24 hours before scheduled debit
- **Opt-out Option:** Customer must be able to opt-out within 24-hour window
- **Delivery Failure:** If notification doesn't land (uninstalled app, inactive VPA), bank may reject debit
- **Veto Effect:** Customer opt-out vetoes debit but mandate survives

**Implementation in Synthetic Data:**
- Pre-debit opt-out modeled as distinct failure category (8% probability)
- Consent for outreach tracked per mandate (90% consent rate)
- Opt-out events modeled as binary (customer blocks or doesn't block)

### 6. Bank-specific Performance Variance
**Source:** Industry observation and Business Standard reporting (September 7, 2025)

**Rules Implemented:**
- **Bank Success Rates:** Different banks have different baseline success rates
- **Top-50 Bank Declines:** ~74% are non-technical (insufficient funds, not fraud)
- **Technical Issues:** Bank-side timeouts, server downtime modeled

**Implementation in Synthetic Data:**
- 10 major Indian banks modeled with success rate multipliers (0.78 – 0.95)
- Bank technical decline modeled as failure category (default for unclassified failures)
- Bank code included as feature for classification

### 7. Temporal Patterns
**Source:** Industry best practices and observed patterns

**Rules Implemented:**
- **Month-end Balance Issues:** Higher failure rates at month-end (days 25-30) due to low balances
- **Salary Credit Patterns:** Higher success rates at month-start (days 1-5)
- **Batch Processing:** Early morning clustering of debit attempts

**Implementation in Synthetic Data:**
- 15% success reduction for month-end attempts
- Scheduled times weighted toward early morning (2-8 AM)
- Day-of-month included as feature

### 8. Mandate Lifecycle
**Source:** NPCI UPI AutoPay guidelines

**Rules Implemented:**
- **Mandate Duration:** 1-2 years typical lifespan
- **Mandate Expiry:** Mandates can expire or be revoked
- **Cancellation Rate:** ~18% of active subscribers cancel mandates (Razorpay published figure)

**Implementation in Synthetic Data:**
- Mandate expiry dates set 1-2 years from creation
- Status tracking (ACTIVE, EXPIRED, REVOKED, PAUSED)
- Last successful debit tracked for health assessment

## Distribution Assumptions

### Amount Distribution
- 30% weighted toward common subscription amounts (₹99, ₹199, ₹299, ₹499, ₹999, ₹1499, ₹1999, ₹4999, ₹9999)
- 70% uniform distribution between ₹100 – ₹50,000
- Ensures realistic mix of low-value subscriptions and high-value payments

### Frequency Distribution
- Daily: 25%
- Weekly: 20%
- Monthly: 40%
- Quarterly: 15%

### PSP App Distribution
- GPay: 35%
- PhonePe: 30%
- Paytm: 20%
- BHIM: 10%
- AmazonPay: 5%

### Bank Distribution
- Uniform distribution across 10 major Indian banks
- Ensures bank-specific patterns can be learned

## Failure Category Distribution (Synthetic)

Based on the implemented rules, synthetic failure distribution:
- NPCI Window Violation: ~20%
- Low Balance: ~25%
- Bank Technical Decline: ~30%
- PIN Re-auth Required: ~10%
- Pre-debit Opt-out: ~8%
- Portability Breakage: ~5%

## Feature Engineering

### Classification Features
1. **Bank Code:** Categorical (10 banks)
2. **PSP App:** Categorical (5 apps)
3. **Amount:** Numerical (₹100 – ₹50,000)
4. **Time of Day:** Hour (0-23)
5. **Day of Week:** Monday-Sunday (0-6)
6. **Day of Month:** 1-31
7. **Attempt Number:** 1-4
8. **Mandate Age:** Days since creation
9. **Category:** Categorical (6 categories)
10. **Historical Success Rate:** Per bank + amount band
11. **PIN Re-auth Required:** Boolean
12. **Days Since Last Success:** Numerical

## Limitations and Assumptions

### What is Synthetic
- All customer VPA addresses are fictional
- Bank success rate multipliers are estimates based on industry observation
- Failure category probabilities are modeled based on rule implementation, not real data
- SHAP explanations are mock values (real system would use actual model SHAP values)

### What is Grounded in Real Rules
- NPCI execution window constraints (exact hours from OC/215A)
- Retry attempt limits (exactly 4 per cycle)
- PIN re-auth thresholds (exact ₹15k/₹1L from RBI 2026)
- Portability cooldown (exactly 90 days from OC-223)
- Pre-debit notification requirements (24-hour window from RBI 2026)

### Classifier Evaluation Caveats

**NPCI_WINDOW_VIOLATION F1 = 1.00 (not data leakage):**  
`NPCI_WINDOW_VIOLATION` is deterministically defined by the execution-hour rule in the synthetic generator — any peak-hour attempt (10–13h, 17–21h) is labeled this way by construction, and no other category is ever scheduled in those hours. Perfect separability on this category reflects the label rule, not classifier skill. The meaningful test of model performance is the other five categories, where labels are not purely time-derived. This is acknowledged explicitly to preempt confusion with data leakage.

**PRE_DEBIT_OPT_OUT separability:**  
`PRE_DEBIT_OPT_OUT` remains the hardest category to separate from `BANK_TECHNICAL_DECLINE` given the available features. The primary separating signal (`consent_for_outreach`) is present as a feature, but in a real system the decisive signal would be an explicit `notification_delivery_failed` flag from the PSP or bank. Without that, some irreducible confusion between these two categories is expected. This is a known limitation of the synthetic data approach.

## Validation Against Real-world Statistics

### Razorpay Published Funnel Numbers (Source: Razorpay)
- ~30% of subscribers drop off before mandate registration completes
- ~20% of subsequent debits fail
- ~18% of active subscribers cancel mandates
- 120% growth in mandate setups in 2025
- 1.27B mandates by November 2025

### Synthetic Data Alignment
- Overall success rate: ~80% (matches 20% failure rate)
- Failure category distribution aligned with observed patterns
- Mandate cancellation modeled via status changes

## Usage in Model Training

This synthetic dataset is used to:
1. Train the XGBoost/LightGBM failure classifier
2. Evaluate SHAP explainability
3. Test compliance engine rules
4. Benchmark recovery agent performance
5. Generate evaluation metrics with ablations

## Acknowledgments

This synthetic data generation is explicitly documented as simulated. Real UPI AutoPay failure data is not publicly available, and this synthetic approach allows us to:
- Build and test the complete system architecture
- Demonstrate compliance with NPCI/RBI rules
- Show explainability via SHAP values
- Evaluate recovery agent performance with ablations
- Provide honest, transparent methodology

All regulatory claims are sourced to specific NPCI/RBI circulars and can be verified against official documentation.
