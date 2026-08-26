# PROJECT CONTEXT: Razorpay AI Buildathon — AI Subscription Payment Recovery Engine

> **Instructions for Claude Code:** This document is the complete ground-truth context for this build. Read it fully before entering plan mode. Use it to ask clarifying questions, produce a detailed technical implementation plan, and validate scope decisions — do not skip straight to code. Every architectural boundary in this document ("Explicit Scope Boundary" section) is intentional and should not be silently expanded during planning or implementation. If a proposed feature isn't listed here, flag it for discussion rather than adding it. Treat the phase order and priority tiers (P0/P1/P2) as binding unless explicitly renegotiated with the builder.

---

## 0. Who's building this and why this document exists

The builder (Sivaji / S Abisheak) has strong hands-on experience in training/fine-tuning LLMs from scratch and building agentic AI systems, solid but secondary skills in core ML, and is building this solo, using AI-assisted coding (Claude Code) as the primary implementation tool. This document exists so that AI-assisted planning and coding has full situational context — the competition, the stakes, the exact scope, and the reasoning behind every major decision — rather than generic project instructions.

---

## 1. The Hackathon — Full Context and "The Heat"

### What this actually is
The **Razorpay AI Buildathon** is a student-only **hiring program**, not a conventional hackathon with prizes. Razorpay is recruiting its next batch of **AI Builder Interns** purely on the strength of a working build — no resume screen, no aptitude test, no group discussion. This is explicitly meritocratic and build-first.

### Stakes
- **Offer:** ₹75,000/month stipend, candidate's choice of 6 or 12 months, **in-person in Bangalore starting September**
- **Primary target cohort:** 2027 graduating batch
- Selected candidates work directly with Razorpay's product and engineering teams on real AI-driven products

### Timeline (critical — verify against the live page for any updates)
- **Application deadline: September 5, 2026**
- As of this document's writing (Aug 26, 2026), that leaves **~10 days**
- Razorpay has not published a full public timeline beyond the application deadline — treat all downstream dates as soft until confirmed

### Selection process — 3 rounds
1. **Round 1 — Track Selection & Build:** Applicant picks one of 5 tracks and builds a working project **independently** (solo builds are explicitly normal and expected — this is not a disadvantage)
2. **Round 2 — Submission:** Public GitHub repository + 5-minute pitch video + architecture explanation
3. **Round 3 — Panel Interview:** Shortlisted builders go directly to a panel — no intermediate screening

### Explicit requirement: you must document a real failure
Candidates are expected to explain **what broke during development and how they recovered from it.** This is graded, not optional narrative color. A deliberate, architecture-grounded failure story must be planned and preserved with evidence — not invented after the fact.

### The heat — why this is more competitive than it looks
- No resume/CGPA screen means the applicant pool is filtered purely by willingness and ability to build — this tends to attract genuinely capable people, not just anyone with a good transcript.
- Razorpay is a serious, engineering-led fintech company (payments, banking, lending infrastructure for millions of merchants) — panelists will be real engineers, not generic recruiters, and will probe technical decisions, not just admire a demo.
- Every track description uses the same underlying language: *"honest metrics," "measured," "audit trail," "stopping rules," "no cherry-picking."* Razorpay is explicitly filtering out flashy-but-fake demos.
- Because AI-assisted coding tools are now widely available, **"I built something that runs" is now a commodity, not a differentiator.** Every competent applicant will ship *something* working. The real filter has moved up a level: correct scoping, domain accuracy, honest measurement, and panel defensibility — things AI coding tools don't do for you.
- Razorpay's own guidance confirms the winning philosophy directly: **a scoped-down but complete project beats an ambitious but half-finished one.**

### The universal judging pattern (applies regardless of track)
> A narrow, complete, honestly-measured system beats a broad, ambitious, half-working one.

This single principle should override any temptation to add scope during planning or implementation.

---

## 2. Track Selection

### The 5 tracks (for reference only — we are not building these)
1. AI Growth & Agentic Commerce — highest competition, highest hype, hardest to isolate a clean metric
2. AI Risk Manager — strong ML fit, lower competition, but underuses agentic/LLM strengths
3. **AI Revenue Recovery ← SELECTED**
4. AI Finance Controller — low competition but underuses LLM/agentic strengths, more of a data-engineering problem
5. Open Track — highest risk, no fixed rubric to aim at

### Why Track 03 was selected
| Factor | Reasoning |
|---|---|
| Skill fit | Builder's strongest skills are LLM fine-tuning and agentic orchestration. This track's "detect → diagnose → decide → act" shape is inherently agentic, and its escalation step has a genuine, defensible reason to fine-tune a model (Hinglish dialogue) — unlike tracks where fine-tuning would be a bolt-on. |
| Competition | Moderate — lower than the "sexy" Growth & Agentic Commerce track (likely flooded with shallow prompt-wrapper agents), higher differentiation ceiling than Finance Controller. |
| Hard-to-fake substance | Domain correctness (UPI Autopay/e-NACH retry rules, decline-code taxonomies, compliant escalation) can't be shortcut by AI-assisted coding — you have to actually get the domain right. This is exactly the rigor Razorpay says it filters for. |
| Metric story | "₹ recovered out of ₹ at risk," retry-only vs. escalation-required split, and promise-honor rate are all clean, panel-friendly numbers. |

---

## 3. Official Problem Statement (Track 03, verbatim intent)

**Title:** Find revenue that's slipping away and win it back

**Description:** Build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow — from payment failures and checkout abandonment to overdue receivables.

**Why now:** Revenue loss rarely happens in one clean step. A payment degrades, a checkout gets abandoned, a subscription fails, or an invoice goes overdue. AI can now close the loop from detecting the problem to diagnosing it, choosing the right intervention, and recovering the money.

**Example directions listed by Razorpay:**
- Payment degradation → root cause → recovery action
- Checkout drop-off recovery
- Failed-subscription recovery
- B2B receivables chaser
- Mandate retry sequencer
- Hinglish voice recovery
- Promise-to-pay tracker

**The bar (explicit grading criteria):** Don't just identify the problem. Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail.

---

## 4. Product Definition

**Recommended product: AI Subscription Payment Recovery Engine**

**Core thesis:** Build one complete, measurable revenue-recovery loop rather than a broad payment-recovery platform.

The system detects failed recurring payments, diagnoses the failure, selects a bounded recovery action through a deterministic policy engine, attempts recovery, escalates unresolved cases to a Hinglish AI agent, extracts payment promises, and measures recovered revenue against a baseline.

The project is intentionally **narrow in product surface but deep in engineering, evaluation, safety, and evidence.**

### The central loop
```
DETECT → DIAGNOSE → DECIDE → RECOVER → ESCALATE → UNDERSTAND → FOLLOW UP → AUDIT → MEASURE
```

### The central business question
How much additional revenue can we recover from the same at-risk payment population compared with a simple baseline, while maintaining zero or near-zero guardrail violations?

### The central engineering principle
**Probabilistic AI for language and diagnosis; deterministic policy for financial actions; comprehensive evaluation for proof.**

---

## 5. Explicit Scope Boundary

### In Scope
- Failed recurring/subscription payment recovery
- Synthetic payment-failure dataset with realistic customer/payment context
- Failure taxonomy and root-cause diagnosis
- Deterministic recovery-policy engine
- Bounded retry execution — **using Razorpay's actual test-mode Payments/Subscriptions API** wherever the workflow touches a real action (this is a deliberate addition: simulate what the API can't give you — historical failure corpus, escalation conversations — but wire real retry execution to the real test-mode API to visibly demonstrate building on Razorpay's own rails, not a fully self-contained simulation)
- Hinglish customer escalation through chat (text-based; voice explicitly excluded, see below)
- Promise-to-pay extraction and follow-up tracking
- Guardrails and hard stopping rules
- Immutable-style audit trail for every decision and action
- Baseline-vs-system evaluation over a synthetic batch (**target size: 500–1,000 cases** — enough for statistically meaningful recovery-rate and slice analysis without becoming a data-generation time sink; do not scale toward 10,000 cases, it does not improve the story and costs disproportionate time)
- Dashboard showing live cases and aggregate recovery metrics

### Explicitly Out of Scope
- B2B receivables collection
- Checkout-abandonment recovery
- Voice as a core feature (chat-only; voice would add a whole STT/TTS failure surface for no strategic gain, since the fine-tuned Hinglish model already gets to shine in text)
- A multi-rail payment platform covering every payment method
- Fraud detection as a separate product
- Large multi-agent architecture for its own sake — prefer a simple, explicit state machine over a heavy agent framework, so state transitions stay inspectable and replayable
- RAG/vector databases unless a concrete requirement appears
- Real-money charging or unsafe production payment actions — everything runs in test mode

These exclusions are deliberate and protect completion quality. Do not silently reintroduce them.

---

## 6. Detailed System Flow

1. **Detect** — Scan a stream/batch of recurring payment attempts and identify payments that are failed or at risk.
2. **Diagnose** — Map payment failure information and customer/payment context to a normalized root-cause category.
3. **Decide** — A deterministic policy engine evaluates cause, retry count, timing, customer state, and configured limits to select retry, escalation, clarification, or stop.
4. **Recover Automatically** — Execute a bounded retry via Razorpay's test-mode API. **Never allow the LLM to directly authorize a financial action** — the policy engine decides; the LLM may only inform diagnosis or conversation.
5. **Escalate** — For unresolved eligible cases, hand off to a Hinglish customer-recovery agent (fine-tuned small open-source LLM).
6. **Understand** — Extract intent, payment willingness, promised amount/date, and confidence from the conversation.
7. **Follow Up** — Track eligible promises and evaluate whether the promised payment is fulfilled.
8. **Stop and Audit** — Enforce maximum retries/contact attempts and record every state transition, decision, model output, policy result, and action.
9. **Measure** — Aggregate ₹ at risk, ₹ recovered, recovery rate, retry-only recovery, escalation-assisted recovery, promise metrics, and guardrail violations.

---

## 7. Architecture

```
Payment Event Stream / Synthetic Batch
              ↓
       Detection Module
              ↓
      Root-Cause Classifier
              ↓
       Case State Store
              ↓
      Deterministic Policy Engine
          ↙      ↓       ↘
       Retry   Escalate   Stop
        ↓         ↓
Retry Executor   Hinglish Agent
(Razorpay test-  ↓
 mode API)   Promise Extractor
                  ↓
              Follow-up Tracker
          ↘       ↓       ↙
             Guardrail Layer
                  ↓
              Audit Logger
                  ↓
        Evaluation + Dashboard
```

**Preferred implementation pattern:** a simple, explicit state machine/orchestrator rather than a heavy agent framework.

---

## 8. AI Strategy — Where AI Belongs (and Where It Deliberately Doesn't)

### A. Root-Cause Diagnosis
Lightweight ML/structured classifier mapping failure code + context → normalized diagnosis category. Evaluate this independently (its own accuracy metric).

### B. Hinglish Recovery Agent
Small open-source LLM (Llama or Qwen) with LoRA/PEFT fine-tuning — **only if a baseline comparison demonstrates fine-tuning improves the target behaviors.** Handles natural code-switched dialogue, tone, intent recognition, and recovery conversation.

**Evaluation methodology (defined up front, before running any comparison):** score base-model vs. fine-tuned model on a held-out dialogue set using a fixed 3-criterion rubric — (1) tone naturalness, (2) task success (did a valid promise get correctly extracted from the conversation), (3) code-switch quality — each scored 1–5 by a strong LLM-as-judge with a fixed prompt template reused across every eval run. Do not rely on perplexity alone; it's weak evidence for a generative dialogue task. Lock this rubric before running the comparison so the final "fine-tuning improved X" claim is defensible under panel questioning.

### C. Promise-to-Pay Extraction
Structured extraction (exists a promise? amount? date? confidence?) via a small fine-tuned model or constrained structured output. Evaluate with precision/recall/F1.

### D. Policy Engine — Deliberately NOT AI
Do **not** fine-tune or delegate financial authorization to an LLM. Payment actions must be controlled by explicit, auditable rules. The LLM may provide diagnosis or conversational output; the policy engine decides whether an action is allowed.

```
LLM / ML proposal
       ↓
confidence + structured result
       ↓
Deterministic policy checks
       ↓
Allowed action
       ↓
Executor
```

---

## 9. Synthetic Data and Evaluation Environment

Build a reproducible synthetic evaluation environment, seeded for reproducibility. **Target scale: 500–1,000 failed/at-risk recurring-payment cases** (sufficient for meaningful aggregate recovery numbers and slice analysis; do not over-invest in volume).

### Payment dataset dimensions
- Payment amount and currency
- Failure code/category
- Attempt count and previous outcomes
- Time since previous attempt
- Subscription/customer state
- Customer payment history
- Eligibility for retry
- Synthetic ground-truth recovery potential
- Escalation eligibility
- Final payment outcome

### Failure taxonomy
- Insufficient funds
- Temporary bank-side failure
- Mandate/limit-related failure
- Expired/invalid payment instrument (where applicable to the simulated rail)
- Customer-declined/intentional non-payment
- Unknown/ambiguous failure
- Other categories supported by the chosen simulation rules

### Critical rule: research before inventing
The final taxonomy and payment-rail retry rules (UPI Autopay/e-NACH windows and limits) must be grounded in **primary documentation** before implementation, timeboxed to **1 day maximum** (Phase 0). Do not invent real-world compliance limits merely to make the demo work.

**Mitigation for ambiguous/unconfirmed rules:** anywhere a specific retry-rail rule cannot be confirmed from a primary source within the timebox, mark it explicitly in the rules config as `ASSUMPTION: <one-line justification>`. An honestly labeled assumption is fine; an unlabeled guess presented as fact is the failure mode to avoid — it's exactly the kind of thing that breaks trust with a technical panelist.

### Hinglish dialogue data sourcing
No ready-made "collections call transcript" dataset exists publicly. Plan:
1. Use an existing large-scale synthetic Hinglish everyday-conversation dataset as a **style/fluency base** (natural code-switching patterns)
2. Generate a **domain-specific layer** on top: collections-scenario conversations, varied personas, escalation tones — synthesized specifically for this use case
3. Label promise-to-pay ground truth alongside this same generation pass

---

## 10. Baseline vs. Our System

Include at least one deliberately simple baseline — a **naive retry strategy** (retry eligible failed payments on one fixed rule, no diagnosis-aware adaptation).

```
Synthetic batch
      ↓
 ┌───────────────┬─────────────────┐
 │               │                 │
Baseline       Our System
 │               │
 ↓               ↓
Recovery       Recovery
Metrics        Metrics
 └───────────────┴─────────────────┘
              ↓
      Statistical / aggregate
           comparison
```

Both systems must run on the exact same held-out evaluation population. No cherry-picking.

---

## 11. Metrics

| Metric | Meaning | Target interpretation |
|---|---|---|
| ₹ at risk | Total monetary value of eligible failed/at-risk payments | Defines the evaluation opportunity |
| ₹ recovered | Money successfully recovered | Primary business outcome |
| Recovery rate | ₹ recovered / ₹ at risk | Headline percentage |
| Baseline uplift | Our recovery rate minus baseline recovery rate | Measures system value |
| Retry-only recovery | Revenue recovered without escalation | Measures automated recovery |
| Escalation-assisted recovery | Revenue recovered after AI escalation | Measures AI contribution |
| Promise precision/recall/F1 | Quality of promise extraction | Measures NLP reliability |
| Guardrail violations | Invalid retries/contact actions | Target zero |
| Average attempts per recovered payment | Recovery efficiency | Flags excessive-retry patterns |
| Escalation rate | Fraction of cases escalated | Shows operational load |
| Audit completeness | Fraction of actions with required trace fields | Shows observability/defensibility |

---

## 12. Evaluation Design

1. Generate the complete synthetic dataset with deterministic seeds (reproducible)
2. Split into development/training and held-out evaluation populations
3. Train/tune models without leaking held-out information
4. Run the naive baseline on the held-out population
5. Run the complete recovery engine on the exact same population
6. Record every action and outcome
7. Compute monetary and model-quality metrics
8. Perform slice analysis by failure category, amount bucket, attempt count, customer context
9. Include adversarial/edge cases and policy-boundary cases
10. Publish the final evaluation methodology and results — not only the best run

---

## 13. Safety and Guardrails

- Maximum retry count
- Minimum/maximum retry timing windows per the (researched or explicitly-labeled-assumption) rail rules
- Maximum contact attempts
- No repeated escalation after a hard stop
- No action taken when required information is missing
- Confidence thresholds and fallback behavior for uncertain model predictions
- Policy engine always overrides model suggestions
- All financial actions are simulated/test-mode only
- Every state transition is auditable
- Odd-hour/contact restrictions represented as explicit configuration where relevant

The safety layer is core product value, not an accessory — this is one of the things Razorpay's own judging language emphasizes most.

---

## 14. Deliberate Failure-and-Recovery Story

Razorpay requires candidates to explain what broke and how they recovered. Create a genuine engineering failure during development and preserve the evidence (logs, before/after, the actual fix).

**Recommended failure scenarios (pick one that actually happens, or engineer one deliberately):**
- A Hinglish phrase is incorrectly classified as a payment promise
- The LLM proposes `RETRY_NOW` when the deterministic policy has already exhausted allowed attempts
- A model returns malformed structured output
- A retry executor receives a duplicate request
- A low-confidence diagnosis causes an incorrect recovery branch

**The strongest story is not "the model never failed."** It's that the system was designed so a model failure could not silently cause an unsafe financial action. Frame the narrative around the guardrail catching the failure, not around the failure being avoided entirely.

---

## 15. Dashboard / Demo

Build alongside the core phases, not at the end — it needs to be ready for the pitch video.

- Live case pipeline
- Current payment state
- Failure diagnosis
- Policy decision and reason
- Retry history
- Escalation conversation
- Extracted promise
- Audit timeline
- Aggregate ₹ at-risk and ₹ recovered
- Baseline vs. system comparison
- Guardrail violation counter
- Failure-case replay

**A single payment must be traceable from failure to final outcome on one screen.**

---

## 16. Fine-Tuning Plan

Fine-tuning is justified only where it provides measurable value — this is a hypothesis to test, not a foregone conclusion.

1. Create a small, high-quality collections-specific Hinglish dataset
2. Cover: successful recovery, refusal, uncertainty, promise-to-pay, delayed payment, clarification
3. Establish a prompted/base-model baseline first
4. Fine-tune with LoRA/PEFT on a small open-source model (Llama or Qwen)
5. Evaluate base vs. fine-tuned using the fixed rubric defined in Section 8B — **do this before declaring fine-tuning a win**
6. Keep the fine-tuned model only if the measured improvement justifies its complexity
7. Record training configuration, dataset version, evaluation split, and results

If fine-tuning does *not* show a measurable improvement, that is itself a valid, sophisticated finding to present — "we tested it and prompting was equally good, so we used the simpler approach" is a legitimate engineering judgment story, not a failure to hide.

---

## 17. Build Phases

| Phase | Scope |
|---|---|
| **Phase 0 — Research & rules** | Finalize failure taxonomy, retry policy assumptions, primary-source references. **Hard timebox: 1 day.** |
| **Phase 1 — Evaluation environment** | Synthetic generator (500–1,000 cases), ground truth, baseline, metrics, replayable experiments |
| **Phase 2 — Core recovery loop** | Detection, diagnosis, deterministic policy, bounded retry (wired to Razorpay test-mode API), state machine, audit logging |
| **Phase 3 — Hinglish escalation** | Dialogue dataset, baseline prompting, fine-tuning experiment (with rubric-based eval), agent, safety constraints |
| **Phase 4 — Promise tracking** | Structured promise extraction, follow-up state transitions |
| **Phase 5 — Dashboard & demo** | Live case state, audit trail, metrics, baseline comparison |
| **Phase 6 — Adversarial testing** | Model failures, policy conflicts, malformed outputs, duplicate actions, edge cases, stopping rules |
| **Phase 7 — Submission hardening** | Freeze experiments, clean repository, document architecture, record failure story, prepare 5-minute pitch |

### Prioritization under time pressure (~10 days)
| Priority | Must ship | Stretch |
|---|---|---|
| **P0** | Synthetic evaluation + baseline + core recovery state machine + policy + audit + ₹ metrics | Better simulator realism |
| **P1** | Hinglish escalation agent + held-out evaluation | Fine-tuned model improvements over base |
| **P2** | Promise extraction + tracking | — (voice is permanently out of scope, not just deprioritized) |

**If time collapses, stop at P0.** A rigorous P0 alone is a defensible, complete submission. Never sacrifice the evaluation system (Section 12) to add a feature — the eval rigor is the primary differentiator and is the part most likely to get silently cut under time pressure. Protect it deliberately.

---

## 18. Repository Shape

```
razorpay-recovery/
├── apps/
│   └── dashboard/
├── src/
│   ├── detection/
│   ├── diagnosis/
│   ├── policy/
│   ├── retry/
│   ├── escalation/
│   ├── promise/
│   ├── guardrails/
│   ├── audit/
│   └── orchestration/
├── data/
│   ├── generators/
│   ├── schemas/
│   └── samples/
├── models/
│   ├── diagnosis/
│   └── hinglish/
├── evaluation/
│   ├── baselines/
│   ├── metrics/
│   ├── experiments/
│   └── reports/
├── configs/
│   └── recovery_rules/   ← includes ASSUMPTION: labels where rail rules are unconfirmed
├── tests/
├── scripts/
├── docs/
├── README.md
└── requirements.txt
```

---

## 19. Panel Questions We Must Be Able to Answer

- Why did you choose Revenue Recovery instead of another track?
- Why subscription recovery rather than trying to cover all revenue leakage?
- Why is the policy engine deterministic?
- Where exactly does the LLM add value?
- Why fine-tune instead of prompt engineering — and how did you prove it was worth it?
- How did you generate the synthetic data?
- How did you prevent data leakage between training and evaluation?
- What is the baseline, and how do you know your uplift isn't cherry-picked?
- What happens when the model is wrong?
- What prevents infinite retries?
- What happens when the model conflicts with the policy engine?
- What broke during development, and how did you recover from it?
- How would this move from simulation to production?
- Which retry-rail rules were confirmed vs. assumed, and why?

---

## 20. Winning Submission Story (5-Minute Pitch Structure)

Do not tour every component. Tell one measurable story:

1. State the revenue leakage problem: failed recurring payments create recoverable at-risk revenue
2. Show one failed payment moving through the system
3. Show diagnosis and why the policy chooses a particular action
4. Show an automatic recovery case
5. Show an unresolved case handed to the Hinglish agent
6. Show a promise extracted from the conversation
7. Show the audit trail and guardrail protection
8. Show the held-out batch result: ₹ at risk, baseline ₹ recovered, our ₹ recovered, uplift
9. Show the deliberately engineered failure and the fallback that prevented unsafe action
10. Close with the production value proposition: recover more revenue without uncontrolled retries or opaque decisions

**Practice this out loud before assuming it's fine.** A technically superior project pitched badly loses to a simpler project pitched with total clarity.

---

## 21. Non-Negotiable Definition of Done

- A complete end-to-end case can be replayed from failed payment to final outcome
- The system works on the full synthetic evaluation batch, not only hand-crafted examples
- A baseline exists and runs on the same held-out population
- ₹ recovered and ₹ at risk are computed automatically
- AI components have independent evaluation
- Financial actions are protected by deterministic guardrails
- Every action has an audit record
- At least one real development failure is documented with its recovery
- The dashboard demonstrates both individual cases and aggregate evidence
- The repository is clean enough for an engineer to clone, run, inspect, and understand

---

## 22. Final Strategic Position

Do not make the project larger. Make this one loop exceptionally deep.

The project should look small when described in one sentence and sophisticated when opened in the repository.

**The winning submission is not the one with the most AI. It is the one that most convincingly demonstrates that AI can recover measurable revenue inside a controlled, auditable financial workflow.**

---

*Source basis: strategic analysis developed collaboratively across hackathon research, track/sub-direction analysis, and the builder's own master project-scope document, consolidated here as a single ground-truth context file. Verify all official track requirements, deadlines, and judging expectations against Razorpay's live Buildathon page before final submission — program details can change.*
