"""Generate the synthetic evaluation dataset and freeze the dev/held-out split.

Usage: python scripts/generate_dataset.py --seed 42 --n-cases 800
"""

import argparse

import _bootstrap  # noqa: F401  (adds repo root to sys.path)

from data.generators.failure_generator import generate_dataset, save_jsonl, REPO_ROOT
from data.generators.split import stratified_split, save_ids

SAMPLES_DIR = REPO_ROOT / "data" / "samples"


def main(n_cases: int, seed: int, dev_frac: float) -> None:
    cases = generate_dataset(n_cases=n_cases, seed=seed)
    save_jsonl(cases, SAMPLES_DIR / "cases.jsonl")

    dev, holdout = stratified_split(cases, dev_frac=dev_frac, seed=seed)
    save_ids(dev, SAMPLES_DIR / "dev_case_ids.txt")
    save_ids(holdout, SAMPLES_DIR / "holdout_case_ids.txt")

    cause_counts = {}
    for c in cases:
        cause_counts[c.ground_truth.true_cause.value] = cause_counts.get(c.ground_truth.true_cause.value, 0) + 1

    print(f"Generated {len(cases)} cases (seed={seed}) -> {SAMPLES_DIR / 'cases.jsonl'}")
    print(f"Split: {len(dev)} dev / {len(holdout)} held-out (stratified by cause + amount bucket)")
    print("Ground-truth cause distribution:")
    for cause, count in sorted(cause_counts.items()):
        print(f"  {cause:32s} {count:4d} ({count / len(cases):.1%})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-cases", type=int, default=800)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-frac", type=float, default=0.7)
    args = parser.parse_args()
    main(n_cases=args.n_cases, seed=args.seed, dev_frac=args.dev_frac)
