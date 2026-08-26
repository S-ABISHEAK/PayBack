"""Numeric guardrail limits, sourced from configs/recovery_rules/retry_windows.yaml
— the single source of truth both the policy engine and the guardrail
enforcement layer read from."""

from configs.loader import load_recovery_rules

_retry_windows = load_recovery_rules("retry_windows.yaml")

MAX_ATTEMPTS: int = _retry_windows["retry_cadence"]["max_retries_before_halted"]["value"]
MAX_CONTACT_ATTEMPTS: int = _retry_windows["contact_attempt_limits"]["max_contact_attempts"]

# Business threshold the policy engine uses to route to CLARIFY under normal
# operation (distinct from the hard safety floor below).
LOW_CONFIDENCE_THRESHOLD: float = 0.35

# Hard safety floor: guardrails.enforce() force-overrides to CLARIFY below
# this regardless of what proposed the action, independent of the policy
# engine's own (higher) business threshold.
LOW_CONFIDENCE_FLOOR: float = 0.15
