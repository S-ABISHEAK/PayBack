import argparse

import _bootstrap  # noqa: F401

from evaluation.experiments.evaluate_promise_extraction import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["rule_based", "llm"], default="rule_based")
    args = parser.parse_args()
    main(backend=args.backend)
