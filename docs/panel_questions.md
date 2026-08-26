# Panel Question Answers

Answers to the questions named in [CLAUDE_CODE_PROJECT_CONTEXT.md](../CLAUDE_CODE_PROJECT_CONTEXT.md)
§19, written from the actual build — not aspirational. Numbers are from the frozen
held-out evaluation run (`evaluation/reports/`, 242 held-out cases, seed 42,
reproduced end-to-end 2026-08-26). Status: Phases 0-6 and 8 complete; Phase 7
(fine-tuning experiment) is not yet run — pending local Ollama/LLM-judge setup — so
this document is explicit about what is and isn't tested yet.

## Why did you choose Revenue Recovery instead of another track?

Best fit between the builder's strongest skills (LLM fine-tuning, agentic
orchestration) and a track shape that's inherently agentic (detect → diagnose →
decide → act), with a genuine, defensible reason to fine-tune (Hinglish
code-switched dialogue) rather than a bolt-on. Domain correctness here (decline-code
taxonomies, compliant retry rules) can't be shortcut by AI-assisted coding, which
matches exactly what the judging language says it filters for.

## Why subscription recovery rather than trying to cover all revenue leakage?

The project's own strategic position: a narrow, complete, honestly-measured system
beats a broad, ambitious, half-working one. Covering checkout abandonment, B2B
receivables, and subscription recovery all at once would have diluted engineering
depth across three surfaces instead of one — the guardrails, the evaluation harness,
and the audit trail are the actual differentiators, and they need one loop to be
deep, not three loops to be shallow.

## Why is the policy engine deterministic?

Because financial actions must be auditable and predictable in a way a probabilistic
model's output isn't. `src/policy/engine.py` is a pure function — no model calls, no
I/O, no randomness — that only ever consumes a diagnosis model's output as a
*structured advisory signal* (predicted cause + confidence), never as authorization.
We proved this holds even under failure: `tests/test_adversarial.py::
test_guardrail_catches_buggy_policy_proposing_retry_after_exhaustion` wires in a
deliberately broken policy function that always proposes RETRY regardless of attempt
count, and shows the independent guardrail layer still rejects it and the retry
executor is never actually called.

## Where exactly does the LLM add value?

Three places, all advisory, never authorizing:
1. **Diagnosis classifier** (actually a lightweight ML classifier, not an LLM) —
   root-cause signal + confidence, feeding the policy engine.
2. **Hinglish escalation agent** (`src/escalation/agent.py`) — natural code-switched
   conversation once retry is exhausted or unlikely to help.
3. **Promise extraction** — structured extraction of has-promise/amount/date from a
   conversation transcript.

## Why fine-tune instead of prompt engineering — and how did you prove it was worth it?

Not yet answerable with a result — **and that's stated honestly, not glossed over.**
The system is deliberately built and fully evaluated on a *prompted* agent first
(Phase 3), with fine-tuning scoped as an isolated, later experiment (Phase 7) that
must beat the prompted baseline on a locked 3-criterion rubric (tone naturalness,
task success, code-switch quality — `evaluation/experiments/rubric_prompt.md`,
written before any comparison runs) to be kept at all. If it doesn't win, the
prompted version ships and that's reported as the finding — per the source doc's own
guidance, "we tested it and prompting was equally good" is a legitimate engineering
conclusion, not a failure to hide. Phase 7 is currently blocked on local Ollama setup.

## How did you generate the synthetic data?

A two-stage probabilistic generator (`data/generators/failure_generator.py`): stage
one samples a hidden `ground_truth.true_cause` from a prior plus synthetic
recovery-probability parameters (eval-only, never a model input); stage two draws
*observed* fields (Razorpay's real error taxonomy, primary-sourced) from a
class-conditional distribution with deliberate overlap — a many-to-one decline-code
mapping, 12% independent reason resampling, 20% field dropout — so the diagnosis task
is genuine inference, not a label lookup.

## How did you prevent data leakage between training and evaluation?

Structural, not procedural: the schema hard-splits `ground_truth.*` from
`observed.*`/`context.*` so `true_cause` cannot accidentally become a classifier
feature. The dev/held-out split is stratified once and frozen to
`data/samples/{dev,holdout}_case_ids.txt`; the diagnosis classifier is fit only on
dev and evaluated only on held-out. A dedicated test
(`test_ground_truth_not_trivially_recoverable_from_observed_reason`) confirms the
observed-reason-to-cause mapping is genuinely ambiguous, not a giveaway — and the
81.8% held-out accuracy (not a suspicious 99%+) is itself evidence the mitigation
worked.

## What is the baseline, and how do you know your uplift isn't cherry-picked?

The baseline retries every eligible case blindly, on one fixed rule, with the *same*
multi-attempt budget as the system (up to `MAX_ATTEMPTS`) — deliberately, so the
comparison isolates diagnosis-aware routing and the escalation channel rather than
being an artifact of the system simply getting more tries. Both runs use the exact
same held-out population. We found and fixed a real reproducibility bug during this
work (see [failure_story.md](failure_story.md)) specifically because the first
headline uplift number looked too good and turned out not to be reproducible across
reruns — the corrected, now-verified-reproducible numbers are **baseline 17.46%,
system 57.06%, uplift +39.60%**. Slice analysis
(`evaluation/reports/slice_analysis_report.json`) is the strongest anti-cherry-picking
evidence: uplift ranges from **+2.1%** on `customer_declined_intentional` (honestly
near-unrecoverable regardless of strategy) to **+56.5%** on `insufficient_funds` — a
single flat number would have hidden this.

## What happens when the model is wrong?

Two independent confidence gates: the policy engine's own business threshold
(confidence < 0.35 → route to CLARIFY instead of acting) and the guardrail layer's
hard safety floor (confidence < 0.15 → force-override to CLARIFY regardless of what
proposed the action). For promise extraction, malformed or wrong-typed model output
is never silently miscoerced into a plausible-looking answer — it's validated
strictly and falls through a repair-retry-then-safe-fallback path
(`confidence=0.0, has_promise=False`) if the model can't produce valid structured
output twice in a row.

## What prevents infinite retries?

`MAX_ATTEMPTS` (4) and `MAX_CONTACT_ATTEMPTS` (3), enforced by
`src/guardrails/guardrails.py` — a layer that independently re-derives the
allowed/not-allowed decision from the raw case and counters every time, regardless of
what the policy engine (or, later, an LLM) proposed. The state machine also has an
absolute `MAX_CYCLES` safety cap as defense in depth beyond the counters themselves,
so a bug that somehow bypassed both guardrail checks would still be bounded.

## What happens when the model conflicts with the policy engine?

The model has no authority to conflict with in the first place — its output is only
ever a structured advisory (predicted cause, confidence), never an action. If the
*policy engine itself* were buggy and proposed an out-of-bounds action, the guardrail
layer catches it independently and downstream execution never happens — proven
end-to-end, not just asserted, by
`test_guardrail_catches_buggy_policy_proposing_retry_after_exhaustion`.

## What broke during development, and how did you recover from it?

Three real, found-not-staged incidents — full writeup in
[failure_story.md](failure_story.md):
1. A reproducibility bug (shared sequential RNG + Python's per-process `set`
   iteration randomization silently broke "same seed → same result").
2. A type-coercion bug in the promise extractor (`bool("no")` is `True` in Python —
   a small-model formatting slip would have silently flipped a refusal into a
   promise).
3. A known, deliberately-not-hastily-fixed state-idempotency gap, pinned by a named
   test rather than patched in a way that would have broken the project's
   re-run-for-updated-numbers workflow.

## How would this move from simulation to production?

- Wire `RETRY_EXECUTOR=razorpay_test` for real (implemented, untested pending
  account keys — a config flip, not a rewrite, by design).
- Build the `cases` persistent state table named in the original design but not yet
  built, closing the state-idempotency gap found in Phase 6.
- Replace the rule-based promise extractor placeholder with the already-implemented
  `LLMPromiseExtractor` once Ollama is live.
- Real two-way customer conversation instead of the scripted-customer-turn design
  used for reproducible base-vs-fine-tuned comparison.
- Real elapsed-time follow-up tracking instead of the synthetic probabilistic model.
- Guardrail-violation-rate monitoring/alerting in production, not just a batch-eval
  counter.

## Which retry-rail rules were confirmed vs. assumed, and why?

From `configs/recovery_rules/*.yaml`, researched in the Phase 0 timebox:
**Confirmed primary** (fetched directly from Razorpay's/RBI's own docs): Subscription
states/webhooks, the test-card/UPI table, and RBI's e-mandate AFA thresholds
(pre-debit notice ≥24h, ₹15,000 AFA-free threshold). **Explicitly labeled ASSUMPTION**:
NPCI UPI Autopay's "4 total attempts, non-peak hours only" rule — NPCI's own PDF
returned HTTP 403 on direct fetch, so this is corroborated across several independent
secondary sources but was not read from the primary document itself. A handful of
observed-reason-to-test-card mappings (e.g. `incorrect_cvv`, `card_expired`) also
carry an `ASSUMPTION:` label with a documented fallback, since no distinct test card
was confirmed for them.
