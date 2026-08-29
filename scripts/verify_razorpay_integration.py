import argparse

import _bootstrap  # noqa: F401

from evaluation.experiments.verify_razorpay_integration import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(n_cases=args.n_cases, seed=args.seed)
