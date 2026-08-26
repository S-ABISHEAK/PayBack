"""Two-stage probabilistic synthetic case generator.

Stage 1: sample a hidden `ground_truth.true_cause` from a prior, plus
per-case synthetic recovery-model parameters (retry/escalation success
probabilities) — used only for eval metrics and outcome simulation, never
exposed to the diagnosis classifier.

Stage 2: sample `observed` and `context` fields from a class-conditional
distribution with deliberate overlap across causes, so diagnosis is a real
inference task rather than a label lookup:
  - many-to-one decline-code mapping (configs/recovery_rules/failure_taxonomy.yaml)
  - ~12% of cases get their observed reason resampled independent of true cause
  - customer-history / instrument-age fields are randomly dropped
  - proxy signals (amount, day-of-month, retry pattern) correlate with but
    don't determine the cause

Reproducible: same seed -> identical dataset.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml

from data.schemas.case_schema import (
    ErrorSource,
    ErrorStep,
    FailureCause,
    GroundTruth,
    ObservedError,
    PaymentCase,
    PaymentContext,
    SubscriptionState,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs" / "recovery_rules"


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name) as f:
        return yaml.safe_load(f)


TAXONOMY = _load_yaml("failure_taxonomy.yaml")
RETRY_WINDOWS = _load_yaml("retry_windows.yaml")

MAX_ATTEMPTS: int = RETRY_WINDOWS["retry_cadence"]["max_retries_before_halted"]["value"]

# Prior over ground-truth causes.
CAUSE_PRIOR: dict[FailureCause, float] = {
    FailureCause.INSUFFICIENT_FUNDS: 0.28,
    FailureCause.TEMPORARY_BANK_SIDE_FAILURE: 0.22,
    FailureCause.MANDATE_LIMIT_RELATED: 0.12,
    FailureCause.EXPIRED_INVALID_INSTRUMENT: 0.15,
    FailureCause.CUSTOMER_DECLINED_INTENTIONAL: 0.10,
    FailureCause.UNKNOWN_AMBIGUOUS: 0.13,
}

# Synthetic recovery-model parameters per cause: (mean_untargeted_retry,
# mean_targeted_retry, escalation_recoverable, mean_escalation_success).
# Illustrative modeling choices for this simulation — encode the intuition
# that untargeted retry works best for transient bank-side issues and worst
# for instrument/consent problems, while diagnosis-aware timing + escalation
# recovers meaningfully more. This gap is what the system's uplift over the
# naive baseline is measuring.
RECOVERY_PARAMS: dict[FailureCause, dict] = {
    FailureCause.INSUFFICIENT_FUNDS: dict(untargeted=0.15, targeted=0.55, esc_recoverable=True, esc_prob=0.35),
    FailureCause.TEMPORARY_BANK_SIDE_FAILURE: dict(untargeted=0.45, targeted=0.75, esc_recoverable=True, esc_prob=0.50),
    FailureCause.MANDATE_LIMIT_RELATED: dict(untargeted=0.05, targeted=0.20, esc_recoverable=True, esc_prob=0.40),
    FailureCause.EXPIRED_INVALID_INSTRUMENT: dict(untargeted=0.02, targeted=0.05, esc_recoverable=True, esc_prob=0.45),
    FailureCause.CUSTOMER_DECLINED_INTENTIONAL: dict(untargeted=0.03, targeted=0.05, esc_recoverable=True, esc_prob=0.15),
    FailureCause.UNKNOWN_AMBIGUOUS: dict(untargeted=0.15, targeted=0.25, esc_recoverable=True, esc_prob=0.20),
}

# Repeated attempts on the same case are not i.i.d. draws from the base
# probability — a case that already failed once is evidence it's a harder
# instance within its cause bucket, so each subsequent attempt (whether
# retry or escalation contact) is discounted relative to the one before it.
# Applied identically by the naive baseline and the system's retry channel,
# and by the system's escalation channel, so it changes the absolute
# recovery numbers without advantaging either side of the comparison.
RETRY_DECAY_FACTOR = 0.55
ESCALATION_DECAY_FACTOR = 0.55


def stable_rng(*key_parts) -> random.Random:
    """Deterministic RNG keyed by arbitrary parts (e.g. seed, case_id, attempt
    number), instead of a single shared `random.Random(seed)` consumed
    sequentially across a case list. That shared-sequential pattern silently
    breaks "same seed -> same result" reproducibility whenever the case
    processing order isn't guaranteed stable — e.g. Python's `set` iteration
    order for str keys varies per-process (hash randomization), and dev/held-out
    case IDs are loaded as a `set`. Keying the RNG per-item instead makes each
    case's outcome independent of processing order entirely."""
    return random.Random(":".join(str(p) for p in key_parts))


def decayed_prob(base_prob: float, n_prior_attempts: int, decay_factor: float) -> float:
    return base_prob * (decay_factor**n_prior_attempts)


AMOUNT_TIERS = [199, 299, 499, 999, 1499, 1999, 2999, 4999, 9999]

NOISE_RESAMPLE_PROB = 0.12
FIELD_DROPOUT_PROB = 0.20
HALTED_STATE_PROB = 0.04
ESCALATION_OPT_OUT_PROB = 0.05


def _beta_around(rng: random.Random, mean: float, kappa: float = 12.0) -> float:
    """Sample from a Beta distribution centered near `mean`, bounded to (0, 1)."""
    mean = min(max(mean, 1e-3), 1 - 1e-3)
    alpha, beta = mean * kappa, (1 - mean) * kappa
    return min(max(rng.betavariate(alpha, beta), 0.0), 1.0)


def _sample_amount(rng: random.Random) -> float:
    base = rng.choice(AMOUNT_TIERS)
    jitter = rng.gauss(0, base * 0.03)
    return round(max(base + jitter, 1.0), 2)


def _all_reasons() -> list[str]:
    return [
        entry["reason"]
        for entries in TAXONOMY["observed_error_taxonomy"].values()
        for entry in entries
    ]


def _reason_to_code(reason: str) -> str:
    for code, entries in TAXONOMY["observed_error_taxonomy"].items():
        if any(e["reason"] == reason for e in entries):
            return code
    return "BAD_REQUEST_ERROR"


def _sample_observed_reason(rng: random.Random, true_cause: FailureCause) -> str:
    if rng.random() < NOISE_RESAMPLE_PROB:
        return rng.choice(_all_reasons())
    plausible = TAXONOMY["generator_mapping"][true_cause.value]["plausible_reasons"]
    return rng.choice(plausible)


def _maybe_drop(rng: random.Random, value):
    return None if rng.random() < FIELD_DROPOUT_PROB else value


def generate_case(case_id: str, rng: random.Random) -> PaymentCase:
    causes, weights = zip(*CAUSE_PRIOR.items())
    true_cause: FailureCause = rng.choices(causes, weights=weights, k=1)[0]
    params = RECOVERY_PARAMS[true_cause]

    ground_truth = GroundTruth(
        true_cause=true_cause,
        retry_success_prob_untargeted=_beta_around(rng, params["untargeted"]),
        retry_success_prob_targeted=_beta_around(rng, params["targeted"]),
        escalation_recoverable=params["esc_recoverable"],
        escalation_success_prob=_beta_around(rng, params["esc_prob"]),
    )

    reason = _sample_observed_reason(rng, true_cause)
    observed = ObservedError(
        code=_reason_to_code(reason),
        reason=reason,
        source=rng.choice(list(ErrorSource)),
        step=rng.choice(list(ErrorStep)),
    )

    attempt_count = rng.choices([0, 1, 2, 3], weights=[0.45, 0.30, 0.15, 0.10], k=1)[0]
    is_halted = rng.random() < HALTED_STATE_PROB
    if is_halted:
        attempt_count = MAX_ATTEMPTS
        subscription_state = SubscriptionState.HALTED
    else:
        subscription_state = SubscriptionState.PENDING if attempt_count > 0 else SubscriptionState.ACTIVE

    # Proxy signal, not a direct tell: insufficient-funds cases skew toward
    # late-in-month days (pre-payday), but plenty of overlap with other causes.
    if true_cause == FailureCause.INSUFFICIENT_FUNDS and rng.random() < 0.6:
        day_of_month = rng.randint(20, 28)
    else:
        day_of_month = rng.randint(1, 28)

    # Proxy signal: expired/invalid-instrument cases skew toward older instruments.
    if true_cause == FailureCause.EXPIRED_INVALID_INSTRUMENT:
        instrument_age_days = rng.randint(500, 1400)
    else:
        instrument_age_days = rng.randint(15, 900)

    history_mean = 0.35 if true_cause == FailureCause.CUSTOMER_DECLINED_INTENTIONAL else 0.6
    context = PaymentContext(
        subscription_id=f"sub_{case_id}",
        customer_id=f"cust_{case_id}",
        amount_inr=_sample_amount(rng),
        subscription_state=subscription_state,
        attempt_count=attempt_count,
        previous_outcomes=["failed"] * attempt_count,
        time_since_previous_attempt_hours=(
            None if attempt_count == 0 else round(rng.expovariate(1 / 30), 1)
        ),
        customer_payment_history_score=_maybe_drop(rng, round(_beta_around(rng, history_mean), 3)),
        instrument_age_days=_maybe_drop(rng, instrument_age_days),
        day_of_month=day_of_month,
        is_retry_eligible=(attempt_count < MAX_ATTEMPTS and subscription_state != SubscriptionState.HALTED),
        is_escalation_eligible=(rng.random() > ESCALATION_OPT_OUT_PROB),
    )

    return PaymentCase(case_id=case_id, ground_truth=ground_truth, observed=observed, context=context)


def generate_dataset(n_cases: int, seed: int) -> list[PaymentCase]:
    rng = random.Random(seed)
    return [generate_case(f"case_{i:05d}", rng) for i in range(n_cases)]


def save_jsonl(cases: list[PaymentCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for case in cases:
            f.write(case.model_dump_json() + "\n")


def load_jsonl(path: Path) -> list[PaymentCase]:
    with open(path) as f:
        return [PaymentCase.model_validate(json.loads(line)) for line in f if line.strip()]
