import argparse

import _bootstrap  # noqa: F401

from evaluation.experiments.run_escalation_rubric_eval import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="prompted")
    args = parser.parse_args()
    main(backend=args.backend)
