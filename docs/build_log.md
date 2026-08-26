# Build Log

Detailed phase-by-phase development history — what was built, what was found, what's
still open. This is the working log; [README.md](../README.md) has the clean
architecture/setup summary a first-time reader wants, and
[failure_story.md](failure_story.md) has the polished write-up of the real incidents
found here. Implementation plan: `~/.claude/plans/analyse-the-full-md-greedy-boole.md`
(the plan this build followed phase by phase).

## Phase 0 — Research & rules — done

Repo scaffold, config skeleton, and researched `configs/recovery_rules/*.yaml`
(failure taxonomy, retry-rail rules, test-mode execution mapping — every unconfirmed
rule explicitly labeled `ASSUMPTION:`) are in place. Open, non-blocking: Razorpay
test-mode account/keys and an LLM-judge API key are still needed (see README Setup)
before Phase 2 integration tests and Phase 3 rubric scoring respectively.

## Phase 1 — Evaluation environment — done

Synthetic case generator, schema, stratified dev/held-out split (frozen), naive
baseline, and the §11 metrics engine are all working end-to-end and covered by
`pytest tests/`. An 800-case dataset is generated (242 held-out). Dashboard skeleton
(Streamlit) shows the case table and baseline metrics. (The baseline's own
recovery-rate number was superseded in Phase 2, then again in Phase 4 — see below.)

## Phase 2 — Core recovery loop — done

Full P0 recovery loop (detection, diagnosis, deterministic policy, guardrails,
retry/escalation execution, audit trail, orchestration) built, wired end to end, and
tested. A single case replays end-to-end via `python scripts/replay_case.py
<case_id>` or the dashboard's Case detail tab. (Headline recovery-rate numbers from
this phase were superseded in Phase 4 by a reproducibility bug fix — the original
64.25%/+41.35% figures were never actually reproducible; don't quote them.)

## Phase 3 — Hinglish escalation agent — code complete, live run still pending

Hinglish dialogue scenario dataset (42 scenarios, 7 categories), locked rubric prompt
(`evaluation/experiments/rubric_prompt.md`), and `PromptedEscalationAgent`
(`MODEL_BACKEND=prompted`, Ollama-backed) are all built and wired into the dashboard.
**Not yet done:** a real conversation has never actually run.

Open, blocking Phase 3 completion (not blocking anything else):
- Ollama isn't installed and needs the user's sudo password:
  ```
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5:3b
  ```
- An `LLM_JUDGE_API_KEY` (or `ANTHROPIC_API_KEY`) in the environment — the judge must
  be materially stronger than the 3B agent under test.

Also open, non-blocking: Razorpay test-mode keys (real retry executor is implemented
but untested pending them). User acknowledged both open items and asked to proceed
with the rest of the build regardless — Ollama/judge-key setup is deferred to later.

## Phase 4 — Promise tracking — done

Promise extraction (`src/promise/extractor.py`: rule-based, real and tested today,
no LLM needed; plus an LLM-backed extractor implemented but blocked on Ollama like
Phase 3's agent) + follow-up tracking (`src/promise/tracker.py`), wired into the
orchestrator and the dashboard. Promise extraction scores 100% P/R/F1 on the
42-scenario set — flagged clearly as a self-consistency check (the rule-based
extractor's keywords were authored against the exact same templates that generate the
scenarios), not evidence of generalization.

**A real reproducibility bug was found and fixed this phase.** `StubRetryExecutor`,
`StubEscalationAgent`, and the naive baseline each shared one sequential
`random.Random(seed)` across a case list built by iterating a `set[str]` of case
IDs — Python randomizes `set` iteration order for strings per process, so "same seed
→ same result" was silently false across separate runs of the identical command
(caught by noticing the headline recovery rate drift between reruns: 69% → 65% →
61%...). Fixed with a per-item-keyed RNG (`stable_rng(seed, case_id,
attempt_number)`), verified reproducible across repeated fresh-process runs, and
locked in with `tests/test_reproducibility.py`. Full write-up:
[failure_story.md](failure_story.md).

**Corrected, now-actually-reproducible canonical numbers:** baseline **17.46%**
recovery, system **57.06%** recovery, **uplift +39.60%** (₹239,798 retry-only +
₹161,359 escalation-assisted of ₹401,156 recovered out of ₹703,003 at risk), 0
guardrail violations, diagnosis classifier **81.8%** held-out accuracy. 56/56 tests
passing at end of phase.

## Phase 5 — Dashboard & demo polish — done

Slice analysis (`evaluation/experiments/run_slice_analysis.py`, spec §12 step 8)
breaks recovery rate and uplift down by failure category, amount bucket, and attempt
count instead of hiding behind one headline number: uplift ranges from **+2.1%** on
`customer_declined_intentional` (honestly near-unrecoverable regardless of strategy)
up to **+56.5%** on `insufficient_funds` and **+56.4%** on `mandate_limit_related`
(where diagnosis-aware routing to escalation clearly earns its keep). Baseline/system
eval scripts now also save per-case results
(`evaluation/reports/{baseline,system}_case_results.jsonl`), which feed both the
slice analysis and an enriched dashboard case table (recovered/channel/guardrail
columns, plus an outcome filter for failure-case replay). Case detail tab now leads
with a one-line system-outcome summary before the full audit trail. 59/59 tests
passing at end of phase.

## Phase 6 — Adversarial testing — done

`tests/test_adversarial.py` — 10 deliberate boundary/malformed-input tests. Two real
findings surfaced, not staged ones — full write-up in
[failure_story.md](failure_story.md):

1. **Fixed a genuine bug** in `LLMPromiseExtractor`: a naive `bool(...)` cast on the
   model's JSON output would silently flip `{"has_promise": "no"}` (a string) to
   `True`, since a non-empty string is truthy in Python. Fixed with strict
   `isinstance` validation per field.
2. **Identified, and deliberately did not paper over, a state-management gap:**
   `process_case()` derives its attempt counters fresh from the case object every
   call rather than resuming from a persistent per-case state store (the `cases`
   table the original tech-stack plan called for was never actually built). Harmless
   today; would matter under live webhook-triggered re-processing. Pinned with a
   named test rather than patched in a way that would have broken the
   re-run-for-updated-numbers workflow.

Also verified end-to-end (not just at the guardrail-function level) that a state
machine wired to a deliberately broken policy engine still never calls the retry
executor and correctly audit-logs the violation. Confirmed the legitimate held-out
batch still produces 0 guardrail violations and unchanged headline numbers after all
Phase 6 changes. 69/69 tests passing at end of phase.

## Phase 7 — Fine-tuning experiment — not started

Deferred by the user pending Ollama/local-compute setup. Scoped as an isolated,
additive experiment (LoRA/QLoRA on Colab, scored against the Phase 3 prompted
baseline using the locked rubric) — see the implementation plan for the full design.
The system is fully built, evaluated, and adversarially tested on the prompted agent
without it, so nothing else is blocked on this.

## Phase 8 — Submission hardening — done for the current state (will need a final touch-up once Phase 7 resolves)

Full clean regeneration of the dataset, diagnosis model, and all evaluation reports
from a fresh `data/recovery.db`, confirming every headline number above reproduces
exactly. Repo cleanup: `.gitignore` corrected so evaluation reports and the frozen
dataset are tracked (they're submission evidence, not build artifacts — only the
accumulating audit `.db` stays ignored, since it regenerates in seconds and the
JSON/JSONL reports already capture its evidence in reviewable form). Added
`docs/panel_questions.md`, `docs/failure_story.md`, `docs/pitch_outline.md`, and this
build log; restructured `README.md` to lead with architecture and results rather than
a phase-by-phase diary. 69/69 tests passing.

**Not yet done, honestly:** Phase 7 (fine-tuning) hasn't run, so `MODEL_BACKEND` is
still `stub` in the frozen reports and the escalation-rubric report doesn't exist yet.
This hardening pass covers everything that doesn't depend on it; a final pass after
Phase 7 (or a decision to ship without it) should re-freeze the reports and update
the pitch outline's beat 5/9 accordingly.
