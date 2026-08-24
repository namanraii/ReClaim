# Reclaim — UPI AutoPay Mandate Failure Recovery Engine
### Full Project Plan for Razorpay AI Builder Internship 2026 — Track 3: AI Revenue Recovery

---

## 1. Positioning Statement (the one-liner you lead every doc/pitch with)

> "Every month, thousands of UPI AutoPay mandates fail silently for reasons that have nothing to do with fraud — expired mandates, low balance at debit time, bank-side timeouts, PIN re-auth friction. Merchants lose recurring revenue and never know why. Reclaim predicts these failures before they happen, recovers what's recoverable, and gives merchants a reason breakdown they've never had before."

Keep this sentence identical everywhere: form answer, README, pitch video opening line. Consistency signals a considered product, not a hackathon fling.

---

## 2. The Problem (Project Objectives field)

**What it solves:**
UPI AutoPay powers a huge share of Indian recurring payments (SIPs, insurance premiums, OTT/subscriptions, EMIs, utility bills). Unlike card-based recurring billing (well-studied globally — Stripe/Chargebee publish extensively on it), UPI AutoPay mandate failures are:
- India-specific, so there's almost no public tooling or research on them
- Structurally different from "fraud declines" — they're operational/timing failures, not risk failures
- Invisible to merchants: gateways report "mandate execution failed" with a generic code, no reason breakdown, no prediction, no recovery action

**Failure categories to model:**
1. Mandate expired / nearing expiry
2. Insufficient balance at the scheduled auto-debit window (usually early morning batch runs)
3. Bank-side technical decline (NPCI/issuer timeout, server downtime)
4. UPI PIN re-authentication required (mandate above ₹15k triggers this per NPCI rules)
5. PSP-app-specific latency (GPay/PhonePe/Paytm approval-flow differences)
6. Customer-side revocation or app uninstall/reinstall breaking the mandate link

**Objective statement (paste-ready):**
"Reclaim is an agentic recovery system for UPI AutoPay mandate failures. It classifies why a recurring debit failed, predicts failures before the debit attempt using historical bank/user patterns, recommends the optimal retry window per bank, and only notifies customers when a nudge will genuinely help — recovering revenue merchants currently lose without ever knowing why."

---

## 3. System Architecture

**Layer 1 — Data & Classification Engine**
- Gradient-boosted classifier (XGBoost/LightGBM) categorizing each failed mandate execution into the 6 categories above
- Features: bank code, PSP app, mandate age, debit amount vs. typical account balance proxy, time-of-day/batch window, historical success rate for that bank+amount-band, days since last successful debit
- This is a direct evolution of your Financial Fraud Detection System's classification pipeline — same skill, inverted objective (predict recoverability, not risk)

**Layer 2 — Agentic Orchestration** (your named multi-agent pattern, reused deliberately)
- `MandateHealthAgent` — monitors mandates approaching expiry or showing balance-risk signals *before* the debit attempt (time-series forecasting, same instinct as your Algorithmic Trading Engine's LSTM work)
- `RetryWindowAgent` — recommends next-best retry time per bank using historical hour-by-hour success curves (deterministic logic on top of the data, not just an LLM guess — this matters for judges who probe "is this really agentic or just GPT wrapper")
- `RecoveryCommsAgent` — drafts the customer nudge ("renew mandate," "low balance alert") only above a confidence threshold, to avoid notification fatigue — a real merchant complaint you should explicitly cite as a design constraint
- `OpsCommanderAgent`-style orchestrator — routes a failed mandate through the right specialist agent, logs the decision path (important for the "explainability" story below)

**Layer 3 — Data Persistence**
- PostgreSQL schema: `mandates`, `debit_attempts`, `failure_events`, `retry_recommendations`, `recovery_outcomes` — mirrors the analytics discipline you already built into the Algorithmic Trading Engine's persistence layer
- This lets you compute real before/after recovery-rate metrics instead of hand-waving a number

**Layer 4 — Merchant Dashboard**
- FastAPI backend + React/Vite frontend (your standard stack)
- Views: recovery-rate over time, failure-reason breakdown by bank/PSP app, revenue recovered (₹), a "why did this fail" explain-panel per transaction (this is your differentiation moment — most competing projects won't have real explainability, just a black-box prediction)

**Explicit design principle to state in your docs (judges look for this):**
"Deterministic logic for scheduling/retry-timing math, ML for failure classification, LLM only for merchant-facing explanation and customer nudges — never for the decision that involves money." This mirrors the ArenaPulse principle you already used, and it directly answers "why not just prompt an LLM for everything," which is exactly what a senior reviewer will probe.

---

## 4. Dataset Strategy (this is where you separate from AI-generated lookalikes)

Nobody else will bother doing this properly — most submissions will hand-wave "we used a dataset." Do the following:
1. Pull NPCI's public UPI AutoPay documentation and RBI circulars on recurring mandate rules (mandate expiry rules, ₹15k PIN re-auth threshold, e-mandate execution windows) — ground your synthetic data generation in these real rules, not guesses
2. Build a synthetic dataset with realistic distributions: batch debit attempts clustered in early-morning windows, bank-specific success-rate variance, seasonal balance patterns (month-start vs. month-end)
3. Write a short methodology note (half a page) explaining exactly how the synthetic data was generated and why it's realistic — this alone puts you ahead of 80% of submissions, because most people won't document their data honestly
4. Report your evaluation with real numbers: classifier accuracy/F1 per failure category, recovery-rate lift (baseline retry-blind vs. Reclaim's smart retry), and be honest about it being simulated — don't oversell "real merchant data" you don't have

---

## 5. Evaluation Metrics (what your dashboard should actually show)

- **Classification accuracy** per failure category (weighted F1, since categories will be imbalanced)
- **Recovery rate lift**: % of failed mandates successfully recovered with smart retry vs. naive same-time retry
- **Revenue recovered (₹)**: the headline number for your pitch
- **False-nudge rate**: how often `RecoveryCommsAgent` would have sent an unnecessary notification — proves you thought about notification fatigue, not just recovery rate

---

## 6. GitHub Repository Structure

```
reclaim/
├── README.md                 # positioning statement + architecture diagram + demo GIF
├── backend/
│   ├── app/
│   │   ├── models/           # classifier training + inference
│   │   ├── agents/           # MandateHealthAgent, RetryWindowAgent, RecoveryCommsAgent
│   │   ├── db/                # SQLAlchemy models: mandates, debit_attempts, failure_events
│   │   └── api/               # FastAPI routes
│   └── requirements.txt
├── frontend/                  # React/Vite dashboard
├── data/
│   ├── synthetic_generation.py
│   └── METHODOLOGY.md         # how synthetic data was built + NPCI/RBI grounding
├── notebooks/                 # EDA + model evaluation, with plots
├── docs/
│   ├── architecture.png
│   └── evaluation_report.md
└── demo/
    └── pitch_script.md
```

**README must include:** positioning statement (Section 1), architecture diagram, a 15-second demo GIF of the dashboard, and your evaluation numbers up top — reviewers skim READMEs in under a minute.

---

## 7. Build Timeline (realistic, so this doesn't collapse into a rushed weekend hack)

| Week | Focus |
|---|---|
| 1 | NPCI/RBI research, synthetic data generator, PostgreSQL schema |
| 2 | Classifier training + evaluation, MandateHealthAgent (forecasting) |
| 3 | RetryWindowAgent + RecoveryCommsAgent, FastAPI backend wiring |
| 4 | React dashboard (recovery metrics, explain-panel) |
| 5 | Polish, evaluation report, README, architecture diagram |
| 6 | Record 5-min pitch video, final GitHub cleanup, form submission |

---

## 8. Form Answers (paste-ready drafts)

**Project Name / Title:**
"Reclaim: Agentic UPI AutoPay Mandate Recovery Engine"

**Project Objectives:**
Use the "Objective statement" from Section 2.

**Build Challenges & Technical Sketch:**
"The core challenge is that UPI AutoPay failure data isn't publicly available, so we grounded a synthetic dataset in real NPCI mandate-execution rules and RBI recurring-payment circulars (documented in `data/METHODOLOGY.md`). Technically, the hardest part was separating what should be deterministic (retry-timing math, based on historical bank success curves) from what should be ML (failure classification) from what should be LLM-driven (customer-facing explanations) — we deliberately kept money-affecting decisions out of the LLM's hands and reserved it for communication only. [Add 1-2 sentences on a specific bug/tradeoff you actually hit while building.]"

**GitHub Repository URL:** *(fill once repo is live and README is polished)*

**5-min Pitch Video Link:** *(script below)*

---

## 9. Pitch Video Script Skeleton (5 minutes)

- **0:00–0:30** — Open with the positioning statement verbatim. Show one real stat (X% of UPI AutoPay mandates fail for non-fraud reasons).
- **0:30–1:30** — Show the dashboard: a failed mandate, click into the explain-panel, show the classified reason.
- **1:30–2:30** — Show the recovery flow: RetryWindowAgent's recommendation, why that time was chosen (historical bank success curve chart).
- **2:30–3:30** — Show the before/after recovery-rate numbers. This is your money moment — say the ₹ recovered number out loud.
- **3:30–4:15** — One architecture slide: deterministic vs. ML vs. LLM boundaries. This is what separates you from "just an LLM wrapper" submissions.
- **4:15–5:00** — Close by tying back to Razorpay specifically: "Payment success rate is core to Razorpay's business — Reclaim is a direct lever on that metric for UPI AutoPay merchants specifically."

---

## 10. Why This Stands Out (keep this as your internal checklist, don't say it out loud in the pitch)

- ✅ Narrow, India-specific, under-documented problem (not googleable in 5 minutes)
- ✅ Grounded in real NPCI/RBI rules, not just vibes
- ✅ Explicit deterministic/ML/LLM boundary — answers the "is this really agentic" question before it's asked
- ✅ Real (simulated but honestly documented) evaluation numbers, not just a working demo
- ✅ Directly tied to Razorpay's actual business metric (payment success rate)
- ✅ Builds on your existing proven skills (fraud classification, time-series forecasting, multi-agent orchestration) rather than starting from zero — you can move fast and go deep instead of spreading thin
