# AI Subscription Payment Recovery Engine

Built for the Razorpay AI Buildathon (Track 03 — AI Revenue Recovery). Detects failed
recurring/subscription payments, diagnoses root cause, routes the decision through a
**deterministic policy engine** (never an LLM), executes bounded retries against
Razorpay's test-mode API, escalates unresolved cases to a Hinglish AI agent, extracts
payment promises, tracks follow-up, and measures recovered revenue against a naive
baseline — with a full audit trail and hard guardrails.

Full scope and rationale: [CLAUDE_CODE_PROJECT_CONTEXT.md](CLAUDE_CODE_PROJECT_CONTEXT.md).
Panel Q&A: [docs/panel_questions.md](docs/panel_questions.md). Failure story:
[docs/failure_story.md](docs/failure_story.md). Pitch outline:
[docs/pitch_outline.md](docs/pitch_outline.md). Detailed build history:
[docs/build_log.md](docs/build_log.md).

## Results (frozen held-out run, 242 cases, seed 42)

| | |
|---|---|
| ₹ at risk | 703,003 |
| Baseline recovery rate | 17.46% |
| System recovery rate | **57.06%** |
| **Uplift** | **+39.60%** |
| Retry-only / escalation-assisted | ₹239,798 / ₹161,359 |
| Guardrail violations | **0** |
| Diagnosis classifier accuracy (held-out) | 81.8% |
| Promise extraction P/R/F1 | 100%¹ |
| Prompted Hinglish agent rubric score, qwen2.5:3b (42 scenarios) | 1.75/5² |
| Prompted Hinglish agent rubric score, qwen2.5:7b, local tuned (42 scenarios) | 3.63/5² |
| Prompted Hinglish agent rubric score, qwen3.8-27b via Groq (42 scenarios, n=3 runs) | **4.63 ± 0.06/5²** |

¹ Self-consistency check on the rule-based extractor's own hand-authored vocabulary —
see [docs/build_log.md](docs/build_log.md#phase-4--promise-tracking--done), not
evidence of generalization.

² All reported as-is, no fine-tuning involved in any of them. `qwen2.5:3b` scores
genuinely low on zero-shot Hinglish; a few-shot prompt barely moved it (1.75 → 1.79).
Swapping to `qwen2.5:7b` (same prompt, still local) nearly doubled it to 3.19;
lowering generation temperature (0.4) and adding a bounded regenerate-on-degenerate-
output retry (catches CJK-script corruption and near-verbatim turn repeats — same
validate-then-repair pattern as the promise extractor) raised it to 3.63. Finally,
routing the same agent through a much larger model hosted on Groq (`qwen/qwen3.8-27b`,
`MODEL_BACKEND=groq_prompted`, judged by an even bigger `openai/gpt-oss-120b` to keep
the judge-stronger-than-agent invariant) reached **4.63 ± 0.06/5 (mean of 3 runs)** —
near the rubric's ceiling, and confirmed stable rather than a lucky single draw. A
separate adversarial check confirmed the judge itself discriminates real quality
(2.17-point mean score drop on deliberately corrupted transcripts, each corruption
hitting the specific criterion it violated). `qwen2.5:7b` (local) stays the default
`OLLAMA_MODEL`; the Groq backend is
an explicit trade-off (customer conversation data leaves the local machine for a
third-party API) documented, not silently defaulted to. See
[docs/build_log.md](docs/build_log.md) Phase 3.

Both baseline and system run over the identical held-out population with the same
multi-attempt budget — the baseline just never escalates. Slice analysis shows uplift
isn't uniform: **+2.1%** on `customer_declined_intentional` (honestly
near-unrecoverable) vs. **+56.5%** on `insufficient_funds` — see
`evaluation/reports/slice_analysis_report.json`.

## Architecture

```
Payment Event Stream / Synthetic Batch
              ↓
       Detection Module ─────────────────────── src/detection/
              ↓
      Root-Cause Classifier ─────────────────── src/diagnosis/  (advisory only)
              ↓
       Deterministic Policy Engine ─────────────  src/policy/    (pure function, no model calls)
          ↙      ↓       ↘
       Retry   Escalate   Stop
        ↓         ↓
  Retry Executor  Hinglish Agent ───────────────  src/retry/, src/escalation/
  (Razorpay        ↓
   test-mode API) Promise Extractor ────────────  src/promise/
                    ↓
                Follow-up Tracker
          ↘       ↓       ↙
             Guardrail Layer ───────────────────  src/guardrails/  (independent re-check)
                  ↓
              Audit Logger ─────────────────────  src/audit/  (append-only, no update/delete)
                  ↓
        Evaluation + Dashboard ──────────────────  evaluation/, frontend/
```

**The one rule that matters most:** the diagnosis classifier and the escalation
agent only ever produce *structured advisory signals* (a predicted cause + confidence,
a conversation). Only `src/policy/engine.py` — a pure function with no model calls —
decides an action, and `src/guardrails/guardrails.py` independently re-validates that
decision from scratch before it can execute, regardless of what proposed it. Proven,
not just asserted: `tests/test_adversarial.py::
test_guardrail_catches_buggy_policy_proposing_retry_after_exhaustion` wires in a
deliberately broken policy engine and confirms the retry executor is still never
called.

Explicit state machine, not a heavy multi-agent framework — every state transition is
inspectable and replayable (`python scripts/replay_case.py <case_id>`).

## Status

**Phases 0–6 and 8 are done. Phase 3 is now fully complete**, including the
prompted-baseline rubric score and a full progression of no-fine-tuning experiments:
`qwen2.5:3b` scored **1.75/5** zero-shot (few-shot: 1.79/5); `qwen2.5:7b` (local,
same prompt) scored **3.19/5**, then **3.63/5** after temperature tuning (0.4) and a
bounded regenerate-on-degenerate-output retry; routing the agent through a much
larger model on Groq (`qwen/qwen3.8-27b`, `MODEL_BACKEND=groq_prompted`, judged by
`openai/gpt-oss-120b` to keep the judge stronger than the agent) reached **4.63/5**
— near the rubric's ceiling. `qwen2.5:7b` (local) is still the default `OLLAMA_MODEL`;
the Groq backend is available but is an explicit local-vs-hosted trade-off, not a
silent default. **4.63/5 is now the real bar Phase 7** (fine-tuning) would have to
clear to be worth keeping. Phase 7 itself remains deferred for now. Full history:
[docs/build_log.md](docs/build_log.md).

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the keys you have — auto-loaded by every script
```

Environment variables (`.env` at the repo root is auto-loaded by every script and by
the dashboard — see `.env.example` for the template):
- `RETRY_EXECUTOR` — `stub` (default, deterministic offline) or `razorpay_test` (real
  test-mode API, needs the two keys below — verified end-to-end against Razorpay's
  real test-mode API, see `docs/build_log.md` Phase 0/2)
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` — required only when `RETRY_EXECUTOR=razorpay_test`
- `MODEL_BACKEND` — `stub` (default), `prompted` (Ollama-backed, needs `ollama pull
  qwen2.5:7b` running locally), or `groq_prompted` (routes the agent itself through
  Groq, default `qwen/qwen3.8-27b`, override with `GROQ_AGENT_MODEL` — needs
  `GROQ_API_KEY`; sends conversation data to a third-party API, see
  `docs/build_log.md` Phase 3 for the trade-off)
- `PROMISE_EXTRACTOR` — `rule_based` (default, no LLM needed) or `llm` (Ollama-backed)
- `GROQ_API_KEY` (or `LLM_JUDGE_API_KEY`) — needed only for
  `scripts/run_escalation_rubric_eval.py`; judge is Groq's `qwen/qwen3.8-27b`

## Repository shape

```
frontend/                FastAPI server + vanilla HTML/CSS/JS dashboard (server.py, loaders.py, static/)
src/                      detection, diagnosis, policy, retry, escalation, promise, guardrails, audit, orchestration
data/                     generators, schemas, samples (frozen dataset — tracked, not gitignored)
models/                   diagnosis (tracked), hinglish (Phase 7, not yet built)
evaluation/               baselines, metrics, experiments, reports (tracked — this is the submission evidence)
configs/recovery_rules/   failure taxonomy, retry-rail rules (ASSUMPTION: labels where unconfirmed)
tests/
scripts/
docs/                     panel_questions.md, failure_story.md, pitch_outline.md, build_log.md
```

## Running

```
python scripts/generate_dataset.py --seed 42
python scripts/train_diagnosis_classifier.py
python scripts/run_baseline_eval.py
python scripts/run_system_eval.py
python scripts/run_slice_analysis.py           # needs both eval runs above first
python scripts/replay_case.py <case_id>
python scripts/generate_dialogue_scenarios.py --seed 42
python scripts/evaluate_promise_extraction.py  # rule_based backend, no Ollama needed
python scripts/run_escalation_rubric_eval.py   # needs Ollama + GROQ_API_KEY
python scripts/run_escalation_rubric_eval.py --backend groq_prompted  # needs GROQ_API_KEY only
python scripts/verify_razorpay_integration.py  # needs RAZORPAY_KEY_ID/SECRET, hits the real test-mode API
python -m uvicorn frontend.server:app --reload  # dashboard at http://127.0.0.1:8000
pytest tests/                                   # 76/76 passing
```

Every reported number above reproduces exactly from a clean state — verified by
wiping `data/recovery.db` and re-running the sequence above end to end.
