"""Deterministic dev/held-out split, stratified by (true_cause, amount_bucket).

Stratifying by ground-truth cause only balances the split across strata — it
does not leak `true_cause` into the classifier's features (see case_schema.py
and failure_generator.py for the ground_truth/observed separation). Intended
to be written once and frozen: scripts/generate_dataset.py persists the
resulting id lists, and nothing downstream re-splits.
"""

from __future__ import annotations

import random
from pathlib import Path

from data.schemas.case_schema import PaymentCase


def amount_bucket(amount_inr: float) -> str:
    if amount_inr < 500:
        return "low"
    if amount_inr < 2000:
        return "mid"
    return "high"


def stratified_split(
    cases: list[PaymentCase], dev_frac: float = 0.7, seed: int = 42
) -> tuple[list[PaymentCase], list[PaymentCase]]:
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[PaymentCase]] = {}
    for case in cases:
        key = (case.ground_truth.true_cause.value, amount_bucket(case.context.amount_inr))
        strata.setdefault(key, []).append(case)

    dev: list[PaymentCase] = []
    holdout: list[PaymentCase] = []
    for group in strata.values():
        shuffled = group[:]
        rng.shuffle(shuffled)
        split_at = round(len(shuffled) * dev_frac)
        dev.extend(shuffled[:split_at])
        holdout.extend(shuffled[split_at:])

    return dev, holdout


def save_ids(cases: list[PaymentCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(c.case_id for c in cases) + "\n")


def load_ids(path: Path) -> set[str]:
    with open(path) as f:
        return {line.strip() for line in f if line.strip()}
