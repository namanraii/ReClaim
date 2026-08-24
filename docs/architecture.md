# Reclaim Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RECLAIM ARCHITECTURE                              │
│                   UPI AutoPay Mandate Recovery Engine                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           LAYER 1: DATA INFRASTRUCTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Mandates   │  │ Debit Attempts│  │ Failure Events│  │ Recovery     │   │
│  │   (Postgres) │  │  (Postgres)  │  │  (Postgres)  │  │ Outcomes     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │   Audit Log  │  │ Promise to   │  │ Retry        │                      │
│  │  (Postgres)  │  │   Pay        │  │ Recommendations                     │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LAYER 2: DETERMINISTIC COMPLIANCE ENGINE                 │
│                      (100% Rule-Based, No ML)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   NPCI Compliance Engine                               │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │ • Execution Window Validation (10AM-1PM, 5PM-9:30PM blocked)    │  │  │
│  │  │ • Retry Limit Enforcement (max 4 attempts per cycle)           │  │  │
│  │  │ • PIN Re-auth Thresholds (₹15k default, ₹1L exceptions)       │  │  │
│  │  │ • Portability Cooldown (90 days per NPCI OC-223)               │  │  │
│  │  │ • Status Check Throttling (90s minimum between checks)         │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   State Machine                                      │  │
│  │  FAILED → DIAGNOSED → RETRY_SCHEDULED → RETRYING →                  │  │
│  │  RECOVERED | EXHAUSTED | NEEDS_USER_ACTION                          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   Idempotency Manager                                 │  │
│  │  • Unique keys per attempt to prevent double-debit                   │  │
│  │  • Atomic transaction guarantees                                     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LAYER 3: ML CLASSIFICATION LAYER                         │
│              (XGBoost/LightGBM + SHAP Explainability)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   Failure Classifier                                  │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │ INPUT: Bank code, PSP app, amount, timing, history             │  │  │
│  │  │ OUTPUT: Failure category + confidence score                    │  │  │
│  │  │ MODEL: XGBoost (100 estimators, max depth 6)                  │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   SHAP Explainability                                │  │
│  │  • Feature importance per prediction                                │  │
│  │  • Local explanations for merchant actionability                     │  │
│  │  • Global model interpretability                                    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   Probability Calibration                              │  │
│  │  • Isotonic regression for reliable confidence scores                 │  │
│  │  • Reduces Expected Calibration Error (ECE)                         │  │
│  │  • Enables accurate nudge thresholding                             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  FAILURE CATEGORIES:                                                        │
│  1. NPCI_WINDOW_VIOLATION  2. LOW_BALANCE      3. PORTABILITY_BREAKAGE    │
│  4. PRE_DEBIT_OPT_OUT     5. BANK_TECHNICAL  6. PIN_REAUTH_REQUIRED      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 4: AGENTIC ORCHESTRATION                             │
│              (Multi-Agent System with Compliance Guardrails)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────┐  ┌──────────────────────────┐                │
│  │   RecoveryAgent          │  │   PortabilityGuardAgent  │                │
│  │  • State machine         │  │  • Portability detection  │                │
│  │  • Retry scheduling      │  │  • Cooldown enforcement   │                │
│  │  • Stopping rules        │  │  • Link breakage detection│                │
│  └──────────────────────────┘  └──────────────────────────┘                │
│                                                                             │
│  ┌──────────────────────────┐  ┌──────────────────────────┐                │
│  │   PromiseToPayTracker    │  │   ComplianceMonitor      │                │
│  │  • Promise tracking      │  │  • Rule validation       │                │
│  │  • Check-back scheduling │  │  • Violation detection    │                │
│  │  • Escalation logic      │  │  • Audit enforcement      │                │
│  └──────────────────────────┘  └──────────────────────────┘                │
│                                                                             │
│  CONSTRAINT: ML only prioritizes compliant slots. Never decides IF rules    │
│  apply. Compliance is deterministic and enforced before ML runs.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 5: COMMUNICATION & INTERFACE                        │
│              (LLM for Tone Polish Only - Never Money Decisions)             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   Communication Agent                                │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Hinglish Templates (Slot-Filled)                              │  │  │
│  │  │ • Low balance alerts                                           │  │  │
│  │  │ • PIN re-auth reminders                                        │  │  │
│  │  │ • Promise-to-pay reminders                                     │  │  │
│  │  │ • Recovery confirmations                                       │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │ LLM Tone Polish (Optional)                                     │  │  │
│  │  │ • Natural language refinement                                  │  │  │
│  │  │ • Tone adjustment (polite/urgent/friendly)                     │  │  │
│  │  │ • NEVER hallucinates amounts/dates (slot-filled)              │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   FastAPI Backend                                    │  │
│  │  • REST API for all operations                                     │  │
│  │  • Real-time classification endpoint                               │  │
│  │  • Recovery orchestration API                                     │  │
│  │  • Dashboard metrics API                                          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                   React Dashboard                                    │  │
│  │  • Recovery rate visualization                                     │  │
│  │  • Failure category breakdown                                      │  │
│  │  • Per-mandate explain panel (SHAP)                                │  │
│  │  • Exception list and audit trail                                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Architectural Principles

### 1. Deterministic/ML/LLM Boundary

**DETERMINISTIC (Layer 2):**
- NPCI compliance rules are 100% rule-based
- State machine transitions are deterministic
- Retry limits and windows are hard constraints
- ML cannot override compliance rules

**ML (Layer 3):**
- Only classifies failure root causes
- Provides SHAP explanations for transparency
- Ranks compliant retry slots (doesn't decide compliance)
- Probabilities calibrated for reliable thresholding

**LLM (Layer 5):**
- Only polishes tone of pre-written templates
- Never makes money-affecting decisions
- Never hallucinates amounts/dates (slot-filled)
- Optional fallback to base templates

### 2. Safety Guarantees

- **Idempotency:** Every retry has unique key to prevent double-debit
- **Stopping Rules:** Exhausted mandates never retried indefinitely
- **Compliance First:** Rules enforced before ML runs
- **Audit Trail:** Every decision logged with reason and compliance status

### 3. Data Flow

1. **Failure Detected** → Compliance Engine validates
2. **ML Classifier** → Determines root cause with SHAP
3. **Recovery Agent** → Schedules compliant retry (deterministic window)
4. **Communication Agent** → Sends nudge if confidence > threshold
5. **Promise Tracker** → Follows up if customer promises payment
6. **Audit Log** → Records every decision for compliance review

### 4. Technology Stack

**Backend:**
- FastAPI (REST API)
- SQLAlchemy (ORM)
- PostgreSQL (Database)
- XGBoost/LightGBM (Classification)
- SHAP (Explainability)

**Frontend:**
- React + Vite
- Recharts (Visualization)
- Axios (API client)

**Infrastructure:**
- Docker Compose (One-command demo)
- PostgreSQL (Database)
- Unit tests (Compliance logic first)

## Compliance Sources

All deterministic rules are sourced to specific regulations:

- **NPCI OC/215A/2025-26:** Execution windows, retry limits, status check throttling
- **NPCI OC-223:** Portability rules (90-day cooldown)
- **RBI 2026 E-mandate:** PIN re-auth thresholds, pre-debit notification

See `data/METHODOLOGY.md` for complete regulatory sourcing.
