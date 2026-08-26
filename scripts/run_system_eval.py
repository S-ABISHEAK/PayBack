import argparse

import _bootstrap  # noqa: F401

from evaluation.experiments.run_system_eval import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(seed=args.seed)
