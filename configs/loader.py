"""Shared YAML loader for configs/recovery_rules/*. Used by src/ modules that
need the researched taxonomy/rail-rule constants (data/generators/failure_generator.py
has its own copy of this, predating this shared module — not worth the churn
to consolidate a 3-line function into already-tested Phase 1 code)."""

from __future__ import annotations

from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent / "recovery_rules"


def load_recovery_rules(filename: str) -> dict:
    with open(RULES_DIR / filename) as f:
        return yaml.safe_load(f)
