# Failure & Recovery Story

The source doc (§14) requires a genuine, evidence-backed account of something that
broke and how it was fixed — framed around the guardrail/validation layer catching a
failure, not around no failure occurring. Three real incidents happened during this
build, all found through the project's own testing discipline, not staged. This
document leads with the strongest one for the 5-minute pitch and records all three
for panel Q&A depth.

---

## Lead story: the reproducibility bug (Phase 4)

**What broke.** While building Phase 4 (promise tracking), a full system-eval run was
re-run to sanity-check a code change, and the headline recovery rate had moved —
64.25% → 65.48% → 61.05% — across three runs of the *exact same command*,
`python scripts/run_system_eval.py --seed 42`. Same seed. Different answer every time.

**Why.** `StubRetryExecutor`, `StubEscalationAgent`, and the naive baseline each held
one shared `random.Random(seed)` and consumed it sequentially while looping over a
list of cases. That list was built by iterating a `set[str]` of case IDs
(`load_ids()`). Python randomizes `set` iteration order for strings **per process**
(hash randomization, on by default) — so the *order* cases were processed in differed
between runs, and because the RNG was shared and sequential, a different order meant
every case after the first divergence got a different random draw than it "should"
have. "Same seed → same result" was true within a single process but silently false
across separate invocations of the identical command — exactly the property the
whole project's evaluation story depends on.

**How it was found.** Not a test — direct observation. Rerunning the same eval
command for a routine check and noticing the number moved. That prompted a targeted
repro:

```python
>>> {'case_00001','case_00042','case_00777','case_00099'}  # fresh Python process, run 1
['case_00777', 'case_00001', 'case_00042', 'case_00099']
>>> {'case_00001','case_00042','case_00777','case_00099'}  # fresh Python process, run 2
['case_00042', 'case_00099', 'case_00777', 'case_00001']
```

Same literal set, different order, different process. Root cause confirmed in
minutes once isolated.

**The fix.** Replaced shared sequential RNG state with `stable_rng(seed, case_id,
attempt_number)` (`data/generators/failure_generator.py`) — a deterministic RNG keyed
by stable identifiers instead of consumed from a shared stream, so every case's
outcome is now mathematically independent of processing order. Applied to the retry
executor, the escalation agent, and the naive baseline. Case lists loaded from a
`set` are also now sorted at every load site as defense in depth.

**How it's locked in, not just fixed once.** `tests/test_reproducibility.py`
processes the same cases forward and reversed and asserts identical per-case
outcomes — a test that would have caught the original bug, and will catch a
regression. Verified directly, too: three fresh-process runs of
`run_system_eval.py --seed 42` now produce byte-identical output.

**Why this is the strongest story to lead with.** It's not a contrived edge case —
it's the exact number the pitch's headline uplift claim depends on, caught by the
same "does this number look right" instinct a panelist would apply, fixed at the root
cause rather than patched around, and permanently guarded by a regression test. It
also directly answers the panel's own question, "how do you know your uplift isn't
cherry-picked" — with a concrete story of *checking*, not just a claim.

---

## Second story: the promise-extraction type-coercion bug (Phase 6)

**What broke — found by adversarial testing, before it could break anything real.**
`LLMPromiseExtractor._parse` (the structured-output extractor meant for once Ollama
is live) originally cast the model's JSON field with a naive `bool(data["has_promise"])`.
If a smaller/less careful model outputs `{"has_promise": "no", ...}` — a string,
not a JSON boolean, a common formatting slip — Python's truthy-string rule means
`bool("no")` evaluates to `True`. A customer's explicit refusal would have silently
become a recorded promise.

```python
>>> bool("no")
True
```

**How it was found.** Deliberate adversarial probing during Phase 6, before any live
LLM was even connected — asking "what's the worst plausible malformed output a small
model could produce, and does our parser handle it correctly, not just avoid
crashing?"

**The fix.** Replaced the naive cast with explicit `isinstance` type validation on
every field. A wrong-typed field now fails parsing outright and goes through the
*same* repair-retry-then-safe-fallback path as genuinely broken JSON, rather than
being silently miscoerced into a plausible-looking wrong answer.

**Locked in.** `tests/test_adversarial.py::
test_wrong_type_has_promise_string_no_does_not_become_true`, plus two related
wrong-type/truncated-JSON tests.

---

## Third story: the state-idempotency gap (Phase 6) — a finding deliberately not rushed

**What was found.** `process_case()` derives its attempt/contact counters fresh from
the case object on every call, rather than resuming from a persistent per-case state
store. The `cases` table planned in this project's own original tech-stack design was
never actually built — only the append-only `audit_events` table was. In today's
batch-evaluation architecture this is harmless: `run_system_eval.py` calls
`process_case()` exactly once per case per run. It would matter in a live system
exposed to webhook-triggered re-processing — a duplicate "payment failed" event for a
case already mid-retry would get its own independent `MAX_ATTEMPTS` budget instead of
resuming shared state.

**Why it wasn't hastily patched.** The obvious quick fix — "skip processing if this
case already has a `final_outcome` event in the audit trail" — would have broken a
property the whole project relies on: re-running `run_system_eval.py` after a code
change (which happened constantly across Phases 4-6) needs to *actually
re-evaluate* every case, not silently skip ones a previous run already resolved. A
correct fix needs the state read to be scoped to a single logical case lifecycle, not
"any historical audit event ever," which is exactly the `cases` state table gap.

**How it's handled instead.** Pinned with a named test —
`test_KNOWN_LIMITATION_repeated_process_case_invocation_is_not_state_idempotent` —
that documents the current behavior and will force a visible, deliberate change to
the test (not a silent regression) when the real fix lands. The concrete production
fix is written down in the docstring and in `docs/panel_questions.md`'s "path to
production" answer.

**Why this is worth mentioning even though it's unresolved.** It's honest evidence of
scope discipline — recognizing a real gap, understanding exactly why a shortcut fix
would be worse than the gap itself, and choosing to document rather than either
ignore it or over-engineer a fix under time pressure. That's the same judgment the
source doc explicitly asks for elsewhere ("a scoped-down but complete project beats
an ambitious but half-finished one").
