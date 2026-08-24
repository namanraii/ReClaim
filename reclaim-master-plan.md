# Reclaim — Master Plan (Research-Verified)
### Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery

---

## 0. What the official Buildathon page actually says (verified against razorpay.com/buildathon)

Track 3, verbatim:

> "Build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow: from payment failures and checkout abandonment to overdue receivables."
>
> **Example directions:** Payment degradation → root cause → recovery action · Checkout drop-off recovery · Failed-subscription recovery · B2B receivables chaser · **Mandate retry sequencer** · Hinglish voice recovery · Promise-to-pay tracker
>
> **The bar:** "Don't just identify the problem. Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail."

Two things follow from this:
1. **"Mandate retry sequencer" and "Promise-to-pay tracker" are literal examples Razorpay gave you.** Expect other applicants to pick them. Differentiation comes from execution depth and the specific sub-angle (root-cause explainability + compliance correctness), not from idea novelty.
2. **"The bar" is your literal checklist** — measured money recovered across a batch, compliant escalation, stopping rules, audit trail. Every design decision below maps to one of those four phrases. (Note: third-party listings mention "Problem Taste"/"Build Quality" criteria, but these do not appear on the official page — treat "the bar" text as the only authoritative evaluation contract.)

---

## 1. What Razorpay already ships (verified — address head-on, never get caught by it)

- **Agent Studio** (built on Anthropic's Claude Agent SDK) has a live **Subscription Recovery** agent: *"Analyzes failed subscription payments, apply smarter retry logic, and trigger targeted customer nudges."* It already calls at-risk subscribers in English/Hindi.
- **Intelligent Retry Mechanism**: recovers **8% more debit collections** over baseline via real-time payment intelligence (Razorpay's own published figure).
- **Autopay Interoperability**: routes mandate executions across gateways/acquirers, recovering **up to 5%** more debits.
- **Intelligent Revenue-Protect**: full-lifecycle layer (registration → debit → churn signals) with branded WhatsApp recovery links.
- Voice: **Gnani.ai** partnership (agentic voice collections via Razorpay's MCP server), **Sarvam AI** (Hindi/Hinglish voice agents), **ElevenLabs** (35k+ outbound Hinglish calls, ~28% connection rate).

**Razorpay's own published funnel numbers (cite these back to them — no one can dispute the source):**
- ~30% of subscribers drop off **before mandate registration completes**
- ~20% of subsequent debits **fail** (insufficient balance, bank downtime, cancelled mandates)
- ~18% of active subscribers **cancel mandates**, often impulsively
- 120% growth in mandate setups in 2025; **1.27B mandates** by Nov 2025

**Guardrail vocabulary to mirror (from Razorpay's Agent Studio principles blog):** merchant-set boundaries, validated actions, logged audit trail, DPDPA consent frameworks, SOC 2 / PCI DSS inheritance. Naming your layers with *their* vocabulary signals you already think like their team.

**What this means:** a solo project cannot out-build their production voice/retry stack, and shouldn't try. The contribution is the layer they don't publicly show: **per-category root-cause explainability a merchant can act on**, **compliance-correct retry scheduling**, and the **portability failure mode** (Section 3). Say this explicitly in the README.

---

## 2. Positioning (verbatim for form + pitch)

> "Reclaim diagnoses *why* a UPI AutoPay mandate failed — not just that it did — and runs a compliant, auditable recovery workflow that respects NPCI's execution-window and retry-count rules, with a stopping rule that halts outreach once a mandate is unrecoverable. It sits on top of retry engines like Razorpay's own, adding the root-cause layer that turns 'recovered ₹X' into 'and here's why, and here's what to change' — e.g., *your Tuesday-morning SBI batch fails 40% more often; move it to Thursday.*"

---

## 3. Failure modes to model (grounded and verified)

1. **NPCI execution-window violations / exhausted retries** — mandates execute only in non-peak hours (peak = 10 AM–1 PM, 5 PM–9:30 PM blocked), **max 4 total attempts (1 original + 3 retries) per mandate per cycle**, at moderated TPS. Status checks throttled (3 per 2 hours, ≥90s apart). Source: NPCI circular OC/215A/2025-26 (May 21, 2025; enforced Aug 1, 2025).
2. **Low balance at debit window** — the headline stat: **20M+ AutoPay mandates revoked monthly** because balances fall short, and **~74% of business declines at India's top-50 banks are insufficient-funds / non-technical** (Business Standard, Sept 7, 2025).
3. **Mandate portability breakage** — a mandate can be ported across UPI apps only **once per 90 days**, every mandate action requires UPI PIN (NPCI OC-223, Oct 7, 2025; compliance deadline Dec 31, 2025; central portal upihelp.npci.org.in). A merchant-side link can silently break on port — absent from all public Razorpay retry/interop material. **Your genuinely novel contribution.**
4. **Pre-debit notification opt-out / delivery failure (CORE, not optional)** — RBI's consolidated 2026 e-mandate Master Directions require a ≥24h pre-debit notification with an opt-out option. If the notification doesn't land (uninstalled app, inactive VPA), the bank can reject the debit; if the customer blocks in the 24h window, the debit is vetoed but the mandate survives. Cheapest category to model (binary event), and it's what makes the health agent genuinely *predictive* rather than reactive — your main differentiation from retry-after-failure products.
5. **Bank-side technical decline** — NPCI/issuer timeouts, server downtime (UPI saw multiple outages in 2025, the stated reason for OC/215A).
6. **PIN re-auth required** — debits above **₹15,000** need per-debit AFA, **except insurance premiums, mutual fund SIPs, and credit card bills up to ₹1,00,000** (get this exception exactly right in METHODOLOGY.md).

---

## 4. Architecture (mapped to "the bar")

**Layer 1 — Root Cause Classifier**
XGBoost/LightGBM over the 6 categories above. SHAP values back every prediction — this is what makes it "root cause," not just "failure." **Probabilities calibrated** (isotonic regression) with a reliability curve in the eval report — the nudge threshold is meaningless without calibration.

**Layer 2 — Constraint-Aware Recovery Agent** *(= "compliant escalation, stopping rules")*
- NPCI rules enforced **in deterministic, unit-tested code**: retries only inside non-peak windows, hard cap of 4 attempts/cycle, idempotency keys on every execution so a retry can never double-debit — impossible to violate even if the model "wants" to. ML only ranks *which* compliant slots to use; it never decides *whether* the rules apply.
- Explicit state machine: `FAILED → DIAGNOSED → RETRY_SCHEDULED → RETRYING → RECOVERED | EXHAUSTED | NEEDS_USER_ACTION`.
- `PortabilityGuardAgent`: detects port-event signatures before wasting a retry on a broken link.
- **Stopping rule:** after N diagnosis-informed retries, or a portability-break without re-registration, the agent stops and logs `EXHAUSTED — needs manual merchant action`. Never infinite-retries.

**Layer 3 — Recovery Communication (scoped honestly)**
Slot-filled Hinglish templates (amount/date/merchant are code-injected slots — the LLM can never hallucinate them), LLM for tone polish only. DPDPA consent note: outreach only where consent exists. No voice infra — that's Gnani/ElevenLabs territory; the README says so explicitly.

**Layer 4 — Promise-to-Pay Tracker** *(a named official example direction — cheap to build, direct bar-credit)*
State machine: nudged → customer promises top-up by date X → single check-back → recovered, or escalated to manual follow-up.

**Layer 5 — Audit Trail & Dashboard** *(= "audit trail" + "measured money recovered")*
Every decision (classification, retry, nudge, stop) logged with reason to a Postgres `audit_log` table — merchant-reviewable, mirroring Razorpay's own guardrail language. Dashboard: recovery rate, ₹ recovered per batch, root-cause breakdown by bank/PSP, per-transaction explain-panel (SHAP → LLM verbalization), and the **honest exception list** — mandates the system could not resolve, with reasons.

---

## 5. Dataset & Evaluation

- Synthetic generator grounded in the exact verified rules: non-peak execution windows, 4-attempt cap, ₹15k/₹1L thresholds, 90-day port cooldown, pre-debit opt-out events, month-start vs month-end balance cycles, bank-specific success-rate variance, early-morning batch clustering. Document every rule and its source in `data/METHODOLOGY.md`.
- Report per the bar, literally: batch recovery rate (state batch size — 500+ synthetic mandates), ₹ recovered vs naive same-time retry baseline, false-nudge rate (notification-fatigue budget), and the honest exception list.
- **Ablation table + seeded runs with confidence intervals**: no-classifier / no-smart-retry / no-nudge vs full system. One ablation table beats three dashboard screenshots.
- Benchmark against Razorpay's published 8% (Intelligent Retry) and 5% (Interop) — frame as complementary, never claim to "beat" production systems on synthetic data.
- State plainly that data is simulated. Honesty here is a differentiator, not a weakness.

---

## 6. Repo Structure

```
reclaim/
├── README.md                 # positioning + architecture diagram + demo GIF + eval numbers up top
├── docker-compose.yml        # one-command demo: Postgres + backend + seeded data
├── backend/
│   ├── app/
│   │   ├── models/           # classifier training + inference + calibration
│   │   ├── agents/           # recovery agent, PortabilityGuardAgent, promise-to-pay tracker
│   │   ├── compliance/       # NPCI window/cap enforcement, idempotency, state machine
│   │   ├── db/               # SQLAlchemy: mandates, debit_attempts, failure_events,
│   │   │                     #   retry_recommendations, recovery_outcomes, audit_log
│   │   └── api/              # FastAPI routes
│   ├── tests/                # unit tests for compliance logic FIRST (fintech reviewers look here)
│   └── requirements.txt      # pinned
├── frontend/                 # dashboard (React/Vite, or lighter if time-constrained)
├── data/
│   ├── synthetic_generation.py
│   └── METHODOLOGY.md        # every rule + its NPCI/RBI source
├── notebooks/                # EDA + model eval, with plots
├── docs/
│   ├── architecture.png      # must visually show the deterministic/ML/LLM boundary
│   └── evaluation_report.md
└── demo/
    └── pitch_script.md
```

**Non-negotiables:** `docker-compose up` gives a reviewer a running seeded demo; compliance logic has unit tests; LICENSE present; deps pinned.

---

## 7. Build Timeline (6 weeks)

| Week | Focus |
|---|---|
| 1 | Repo skeleton + CI, Postgres schema, NPCI compliance engine + unit tests, synthetic generator v1, METHODOLOGY.md |
| 2 | Classifier training + calibration + SHAP, evaluation harness (seeded, ablations) |
| 3 | Recovery agent (window/cap enforcement, stopping rule), PortabilityGuardAgent, promise-to-pay tracker |
| 4 | FastAPI wiring + dashboard (recovery metrics, explain-panel, exception list) |
| 5 | Comms layer (Hinglish templates + LLM tone polish), docker-compose one-command demo, evaluation report |
| 6 | README polish, architecture diagram, demo GIF, 5-min pitch video, submission |

**Cut-line if behind:** dashboard polish first, promise-to-pay tracker second — never the compliance logic, audit trail, or evaluation honesty (those are the bar).

---

## 8. Form Answers (paste-ready)

**Project Name:** "Reclaim: Agentic UPI AutoPay Mandate Recovery Engine"

**Project Objectives:** Use the Section 2 positioning statement.

**Build Challenges & Technical Sketch:**
"UPI AutoPay failure data isn't public, so we grounded a synthetic dataset in NPCI's actual execution-window rules (peak-hour blackout, 4-attempt cap — OC/215A/2025-26) and RBI's 2026 e-mandate framework (₹15k/₹1L AFA thresholds, 24h pre-debit opt-out), documented in `data/METHODOLOGY.md`. The harder challenge was making retry scheduling *compliance-correct*, not just smart — the agent can never retry outside NPCI's permitted windows or beyond the attempt cap, so that logic is deterministic and unit-tested, with ML only ranking which compliant slots to prioritize. We also model a failure mode absent from public tooling: mandate portability breakage under NPCI's OC-223 framework. [Add 1–2 sentences on a real bug/tradeoff you hit — do not submit without this.]"

**GitHub URL / Pitch Video:** fill once live.

---

## 9. Pitch Video Script (5 min)

- **0:00–0:30** — Positioning statement verbatim. Stats: 20M mandates revoked monthly on low balance; ~74% of top-50-bank declines are non-technical (Business Standard). Razorpay's own funnel: ~20% of debits fail.
- **0:30–1:30** — Dashboard: a failed mandate → explain-panel → classified root cause with SHAP reasoning.
- **1:30–2:30** — Recovery flow: compliant retry slot chosen within NPCI windows, attempt cap visible, audit log entry shown live.
- **2:30–3:30** — Before/after numbers: ₹ recovered per batch vs naive baseline + ablation table. Say the ₹ number out loud.
- **3:30–4:15** — Architecture slide: deterministic compliance / ML classification / LLM communication boundary. Acknowledge Agent Studio and Intelligent Retry by name — "this is the layer underneath their 8%."
- **4:15–5:00** — Close: payment success rate is Razorpay's core metric; Reclaim is the explainable, compliance-correct root-cause layer for UPI AutoPay specifically.

---

## 10. Internal checklist (never say out loud)

- ✅ Maps to the *first* official example direction, with two more (mandate retry sequencer, promise-to-pay tracker) as mechanics underneath
- ✅ Built literally against "the bar": measured recovery, compliant escalation, stopping rules, audit trail
- ✅ Acknowledges Razorpay's existing stack openly; positions as the layer they don't show
- ✅ One genuinely undocumented failure mode (portability) as the novel contribution
- ✅ Regulatory claims all sourced and precise (incl. the ₹1L exception and the 90-day port cooldown)
- ✅ Honest simulated evaluation with ablations, CIs, and an exception list
- ✅ Razorpay's own funnel stats and guardrail vocabulary used throughout
