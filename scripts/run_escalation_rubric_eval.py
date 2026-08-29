import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

from evaluation.experiments.run_escalation_rubric_eval import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="prompted")
    parser.add_argument("--scenarios", default=None, help="Path to a scenarios .jsonl file (default: the frozen dialogue_scenarios.jsonl)")
    args = parser.parse_args()
    main(backend=args.backend, scenarios_path=Path(args.scenarios) if args.scenarios else None)
