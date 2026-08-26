# 5-Minute Pitch Outline

Following the structure in [CLAUDE_CODE_PROJECT_CONTEXT.md](../CLAUDE_CODE_PROJECT_CONTEXT.md)
§20 — one measurable story, not a component tour. Numbers are from the frozen
held-out run (242 cases, seed 42). **Practice this out loud before assuming it's
fine** — the source doc is explicit that a simpler project pitched with total clarity
beats a superior one pitched badly.

Target: ~30 seconds per beat, 10 beats, 5 minutes. Adjust down if Phase 7
(fine-tuning) isn't done by recording time — beats 5/9 are the ones to compress or
cut, not beats 1/4/8/9(guardrail).

1. **The problem.** Failed recurring payments are recoverable revenue, not lost
   revenue — if you diagnose *why* it failed and respond appropriately instead of
   blindly retrying. Show the number: ₹703,003 at risk in this held-out batch alone.

2. **One failed payment, live.** Pick a case from the dashboard's Case detail tab.
   Show its failure: amount, observed reason, subscription state. This is the
   concrete anchor the rest of the pitch hangs off.

3. **Diagnosis + why the policy chooses what it chooses.** Show the diagnosis
   classifier's predicted cause and confidence, then the policy decision and its
   plain-English reason string (`src/policy/engine.py` — read a line or two of the
   actual deterministic rule live, it's short and legible). Land the point: this
   decision came from a rule you can read, not a model's opaque judgment call.

4. **An automatic recovery case.** Show a case that recovered via retry alone —
   `retry_only_recovered_inr = ₹239,798` across the batch.

5. **An unresolved case handed to the Hinglish agent.** *(If Phase 7/Ollama landed
   before pitch day: a live conversation from the dashboard. If not: acknowledge
   directly — "the escalation agent is built and wired, but live model inference
   needs local infra I set up after this recording; here's the architecture and the
   scripted-scenario test harness that proves the wiring.")* Escalation recovered
   ₹161,359 of the batch's total — revenue retry alone could never have touched.

6. **A promise extracted from the conversation.** Show the extractor's output
   (has_promise / amount / date / confidence) on the case from beat 5, or on a
   dialogue-scenario example if live inference isn't available.

7. **The audit trail and guardrail protection.** Scroll the case's full audit
   timeline — every decision, every action, nothing missing. Then say the guardrail
   line directly: *"even if the policy engine itself had a bug, we proved the
   guardrail layer independently catches an out-of-bounds action before it executes
   — the retry executor is never called."* This is the single most important
   sentence in the pitch; don't rush it.

8. **The held-out batch result.** ₹703,003 at risk → baseline recovers **17.46%**,
   system recovers **57.06%**, **uplift +39.60%**. Immediately follow with the slice
   breakdown, don't let the headline number stand alone: *"+2.1% on cases that are
   genuinely near-unrecoverable, +56.5% on the cases diagnosis-aware routing
   actually helps — that spread is the evidence this isn't a cherry-picked number."*

9. **The engineered failure and the fallback that caught it.** Lead with the
   type-coercion bug (`docs/failure_story.md`): *"a naive JSON parse would have
   silently turned a customer's explicit refusal into a recorded promise — we found
   it by adversarial testing before it ever touched a real conversation, and fixed
   it so malformed model output can never become a silently-wrong answer."* If there's
   time, add the guardrail-catches-a-broken-policy-engine test as the second beat —
   *the system was designed so a model failure couldn't silently cause an unsafe
   action, not that failures never happen.*

10. **Production close.** One sentence: *"This runs on Razorpay's own test-mode
    rails today, and moving to production is a config flip for the retry executor,
    not a rewrite — the interface was built for that from day one."* End on the
    thesis: recover more revenue without uncontrolled retries or opaque decisions.

## Things to have ready but not lead with

- If asked about fine-tuning before it's done: state plainly that the system is
  fully built and evaluated on a prompted agent, fine-tuning is scoped as an
  isolated later experiment against a locked rubric, and "prompting was equally
  good" is an explicitly valid outcome per the project's own methodology — not
  something to be defensive about.
- The state-idempotency gap (`docs/failure_story.md` third story) — good material
  if asked "how would this move to production," bad material to volunteer unprompted
  since it reads as unfinished if introduced without the context of *why* it wasn't
  rushed.
