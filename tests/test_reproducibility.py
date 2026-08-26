"""Regression tests for a real bug found during Phase 4: StubRetryExecutor,
StubEscalationAgent, and run_naive_baseline used to share one sequential
random.Random(seed) across a case list, which made results silently depend
on case processing order — and case lists are frequently built by iterating
a `set` of case_ids, whose order varies per Python process (hash
randomization). "Same seed -> same result" was not actually true across
separate script invocations. Fixed via stable_rng() keying each draw by
(seed, case_id, attempt_number) instead of shared sequential state — these
tests process the same cases in two different orders and assert identical
per-case outcomes, which would have caught the original bug.
"""

from data.generators.failure_generator import generate_dataset
from evaluation.baselines.naive_retry import run_naive_baseline
from src.escalation.agent import StubEscalationAgent
from src.retry.executor import StubRetryExecutor
from tests.factories import make_case


def test_naive_baseline_order_independent():
    cases = generate_dataset(n_cases=40, seed=3)
    forward = run_naive_baseline(cases, seed=42)
    backward = run_naive_baseline(list(reversed(cases)), seed=42)

    forward_by_id = {r.case_id: r for r in forward}
    backward_by_id = {r.case_id: r for r in backward}
    for case_id in forward_by_id:
        assert forward_by_id[case_id].recovered == backward_by_id[case_id].recovered
        assert forward_by_id[case_id].attempts_used == backward_by_id[case_id].attempts_used


def test_stub_retry_executor_order_independent():
    cases = [make_case(f"case_{i}", seed=i) for i in range(20)]
    executor_a = StubRetryExecutor(seed=42)
    executor_b = StubRetryExecutor(seed=42)

    results_forward = [executor_a.execute_retry(c, attempt_number=1) for c in cases]
    results_backward = [executor_b.execute_retry(c, attempt_number=1) for c in reversed(cases)]

    forward_by_id = dict(zip([c.case_id for c in cases], results_forward))
    backward_by_id = dict(zip([c.case_id for c in reversed(cases)], results_backward))
    for case_id in forward_by_id:
        assert forward_by_id[case_id].success == backward_by_id[case_id].success


def test_stub_escalation_agent_order_independent():
    cases = [make_case(f"case_{i}", seed=i) for i in range(20)]
    agent_a = StubEscalationAgent(seed=42)
    agent_b = StubEscalationAgent(seed=42)

    forward = {c.case_id: agent_a.escalate(c, attempt_number=1).resolved for c in cases}
    backward = {c.case_id: agent_b.escalate(c, attempt_number=1).resolved for c in reversed(cases)}
    assert forward == backward


def test_set_iteration_order_is_not_relied_on_for_reproducibility():
    """Directly simulates the original failure mode: build the same case
    list via two different (valid) orderings of a set of ids and confirm
    the baseline's aggregate outcome is identical either way."""
    cases = generate_dataset(n_cases=30, seed=9)
    by_id = {c.case_id: c for c in cases}

    order_a = [by_id[cid] for cid in sorted(by_id.keys())]
    order_b = [by_id[cid] for cid in sorted(by_id.keys(), reverse=True)]

    result_a = run_naive_baseline(order_a, seed=42)
    result_b = run_naive_baseline(order_b, seed=42)

    recovered_a = {r.case_id for r in result_a if r.recovered}
    recovered_b = {r.case_id for r in result_b if r.recovered}
    assert recovered_a == recovered_b
