"""Schema for a Hinglish escalation dialogue scenario.

A scenario's customer-side turns are scripted and fixed — the same script is
used regardless of which agent (prompted or, later, fine-tuned) generates the
agent-side turns, so base-vs-fine-tuned comparisons are apples-to-apples and
`ground_truth` stays well-defined without needing a live customer simulator.
This is a deliberate scope simplification for a 10-day build; see
evaluation/experiments/rubric_prompt.md for how it's scored.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class DialoguePersona(str, Enum):
    COOPERATIVE = "cooperative"
    EVASIVE = "evasive"
    CONFUSED = "confused"
    HOSTILE = "hostile"
    ALREADY_PAID = "already_paid"


class DialogueGroundTruth(BaseModel):
    has_promise: bool
    promised_amount_inr: Optional[float] = None
    promised_date_offset_days: Optional[int] = None


class DialogueScenario(BaseModel):
    scenario_id: str
    category: str  # successful_recovery | promise_to_pay | delayed_payment | refusal | uncertainty | clarification | already_paid
    persona: DialoguePersona
    case_id: Optional[str] = None
    customer_name: str
    amount_inr: float
    days_overdue: int
    opening_context: str  # situational context given to the agent, not the customer
    scripted_customer_turns: list[str]  # fixed customer lines, in order
    ground_truth: DialogueGroundTruth
