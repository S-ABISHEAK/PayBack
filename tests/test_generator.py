from data.generators.failure_generator import generate_dataset
from data.generators.split import stratified_split


def test_reproducible_with_same_seed():
    a = generate_dataset(n_cases=200, seed=7)
    b = generate_dataset(n_cases=200, seed=7)
    assert [c.model_dump_json() for c in a] == [c.model_dump_json() for c in b]


def test_different_seed_differs():
    a = generate_dataset(n_cases=200, seed=7)
    b = generate_dataset(n_cases=200, seed=8)
    assert [c.model_dump_json() for c in a] != [c.model_dump_json() for c in b]


def test_ground_truth_not_trivially_recoverable_from_observed_reason():
    """A given observed reason must map back to more than one true_cause in
    the generated data — otherwise the classifier task degenerates into a
    label lookup (the leakage risk flagged in the implementation plan)."""
    cases = generate_dataset(n_cases=1000, seed=1)
    reason_to_causes: dict[str, set[str]] = {}
    for c in cases:
        reason_to_causes.setdefault(c.observed.reason, set()).add(c.ground_truth.true_cause.value)
    ambiguous_reasons = [r for r, causes in reason_to_causes.items() if len(causes) > 1]
    assert len(ambiguous_reasons) >= 1


def test_split_partitions_all_cases_with_no_overlap():
    cases = generate_dataset(n_cases=300, seed=3)
    dev, holdout = stratified_split(cases, dev_frac=0.7, seed=3)
    dev_ids = {c.case_id for c in dev}
    holdout_ids = {c.case_id for c in holdout}
    assert dev_ids.isdisjoint(holdout_ids)
    assert dev_ids | holdout_ids == {c.case_id for c in cases}


def test_split_is_deterministic():
    cases = generate_dataset(n_cases=300, seed=3)
    dev1, holdout1 = stratified_split(cases, dev_frac=0.7, seed=3)
    dev2, holdout2 = stratified_split(cases, dev_frac=0.7, seed=3)
    assert [c.case_id for c in dev1] == [c.case_id for c in dev2]
    assert [c.case_id for c in holdout1] == [c.case_id for c in holdout2]
