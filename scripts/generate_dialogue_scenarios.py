"""Generate the Hinglish escalation dialogue scenario set.

Usage: python scripts/generate_dialogue_scenarios.py --seed 42 --n-per-category 6
"""

import argparse

import _bootstrap  # noqa: F401

from data.generators.failure_generator import REPO_ROOT
from data.generators.hinglish_dialogue_generator import generate_dialogue_scenarios, save_jsonl

SAMPLES_DIR = REPO_ROOT / "data" / "samples"


def main(n_per_category: int, seed: int) -> None:
    scenarios = generate_dialogue_scenarios(n_per_category=n_per_category, seed=seed)
    save_jsonl(scenarios, SAMPLES_DIR / "dialogue_scenarios.jsonl")

    by_category = {}
    for s in scenarios:
        by_category[s.category] = by_category.get(s.category, 0) + 1

    print(f"Generated {len(scenarios)} dialogue scenarios (seed={seed}) -> "
          f"{SAMPLES_DIR / 'dialogue_scenarios.jsonl'}")
    for cat, count in sorted(by_category.items()):
        print(f"  {cat:22s} {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-category", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(n_per_category=args.n_per_category, seed=args.seed)
