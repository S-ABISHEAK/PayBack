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
| Prompted Hinglish agent rubric score, qwen2.5:7b (42 scenarios) | **3.63/5²** |

¹ Self-consistency check on the rule-based extractor's own hand-authored vocabulary —
see [docs/build_log.md](docs/build_log.md#phase-4--promise-tracking--done), not
evidence of generalization.

² Both reported as-is. `qwen2.5:3b` scores genuinely low on zero-shot Hinglish; a
few-shot prompt barely moved it (1.75 → 1.79). Swapping to `qwen2.5:7b` (same prompt,
no fine-tuning) nearly doubled the score to 3.19 — clear evidence the 3B ceiling was
model capacity, not prompting. Lowering generation temperature (0.4) and adding a
bounded regenerate-on-degenerate-output retry (catches CJK-script corruption and
near-verbatim turn repeats — same validate-then-repair pattern as the promise
extractor) raised it further to **3.63/5**. `qwen2.5:7b` with these settings is now
the default (`OLLAMA_MODEL`) and the real baseline the (currently deferred)
fine-tuning experiment has to beat. See [docs/build_log.md](docs/build_log.md)
Phase 3.

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
        Evaluation + Dashboard ──────────────────  evaluation/, apps/dashboard/
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
prompted-baseline rubric score, a model-size ablation, and generation-quality tuning
on top of it. `qwen2.5:3b` scored **1.75/5 overall** zero-shot; a few-shot prompt only
nudged it to 1.79/5. Swapping to `qwen2.5:7b` (same prompt, no fine-tuning) scored
**3.19/5**, then lowering temperature to 0.4 and adding a bounded regenerate-on-
degenerate-output retry (catches CJK-script corruption and near-verbatim repeats)
raised it to **3.63/5** (3.74 tone / 3.81 task success / 3.36 code-switching) across
all 42 dialogue scenarios, judged by Groq's `qwen/qwen3.8-27b`. `qwen2.5:7b` with
these settings is now the default `OLLAMA_MODEL` and the real baseline **Phase 7**
(fine-tuning) has to beat, not 1.75/5. Phase 7 itself remains deferred for now. Full
history: [docs/build_log.md](docs/build_log.md).

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the keys you have — auto-loaded by every script
```

Environment variables (`.env` at the repo root is auto-loaded by every script and by
the dashboard — see `.env.example` for the template):
- `RETRY_EXECUTOR` — `stub` (default, deterministic offline) or `razorpay_test` (real
  test-mode API, needs the two keys below — implemented, untested pending them)
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` — required only when `RETRY_EXECUTOR=razorpay_test`
- `MODEL_BACKEND` — `stub` (default) or `prompted` (Ollama-backed, needs `ollama pull
  qwen2.5:7b` running locally — see `docs/build_log.md` Phase 3)
- `PROMISE_EXTRACTOR` — `rule_based` (default, no LLM needed) or `llm` (Ollama-backed)
- `GROQ_API_KEY` (or `LLM_JUDGE_API_KEY`) — needed only for
  `scripts/run_escalation_rubric_eval.py`; judge is Groq's `qwen/qwen3.8-27b`

## Repository shape

```
apps/dashboard/          Streamlit dashboard
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
streamlit run apps/dashboard/app.py
pytest tests/                                   # 69/69 passing
```

Every reported number above reproduces exactly from a clean state — verified by
wiping `data/recovery.db` and re-running the sequence above end to end.
