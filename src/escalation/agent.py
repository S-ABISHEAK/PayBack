"""Escalation agent interface, selected via MODEL_BACKEND env var — same
interface-swap pattern as src/retry/executor.py.

Phase 2: stub only (StubEscalationAgent), deterministic and offline, so the
core loop is fully testable before any conversational agent exists. Phase 3
adds PromptedEscalationAgent (MODEL_BACKEND=prompted) and, if it earns its
keep against the locked rubric, a fine-tuned one (MODEL_BACKEND=finetuned) —
both implementing the same `escalate()` signature, added to this module
rather than a parallel structure.
"""

from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod
from typing import Optional

import requests
from pydantic import BaseModel

from data.generators.failure_generator import ESCALATION_DECAY_FACTOR, decayed_prob, stable_rng
from data.generators.hinglish_dialogue_generator import TEMPLATES, instantiate_scenario
from data.schemas.case_schema import PaymentCase
from data.schemas.dialogue_schema import DialogueScenario


class EscalationOutcome(BaseModel):
    resolved: bool
    promise_made: bool = False
    conversation: Optional[list[dict]] = None


class EscalationAgent(ABC):
    @abstractmethod
    def escalate(self, case: PaymentCase, attempt_number: int = 1) -> EscalationOutcome: ...


class StubEscalationAgent(EscalationAgent):
    """Deterministic, seeded from ground_truth.escalation_success_prob (decayed
    across repeated contact attempts on the same case) — placeholder until
    Phase 3 wires a real Hinglish conversation agent that produces this
    outcome from an actual dialogue + promise extraction.

    Each call gets its own RNG keyed by (seed, case_id, attempt_number),
    not a shared sequential `random.Random(seed)` — see
    data.generators.failure_generator.stable_rng for why that matters."""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def escalate(self, case: PaymentCase, attempt_number: int = 1) -> EscalationOutcome:
        prob = decayed_prob(
            case.ground_truth.escalation_success_prob,
            n_prior_attempts=attempt_number - 1,
            decay_factor=ESCALATION_DECAY_FACTOR,
        )
        rng = stable_rng(self._seed, case.case_id, attempt_number)
        resolved = rng.random() < prob
        return EscalationOutcome(resolved=resolved, promise_made=resolved, conversation=None)


SYSTEM_PROMPT = """\
Aap khud ek professional AI payment recovery agent hain jo abhi customer se seedha \
(directly) baat kar rahe hain unke failed subscription payment ke baare mein.

IMPORTANT — aapko khud customer ko message BHEJNA hai, na ki kisi aur ko advice \
dena ki kya likhna chahiye. Sirf apna actual message likhiye — koi explanation, \
preamble, ya "here's how you could phrase it" jaisa kuch mat likhiye. Bas seedha \
customer ko bheja jaane wala message likhiye, first person mein, jaise aap khud \
bol rahe hain.

Language: Hinglish mein likhiye — Hindi aur English ka natural mix, jaise ek real \
bilingual Indian collections agent WhatsApp par likhta hai (e.g. "Sir, aapka \
payment 3 din pehle fail ho gaya tha"). Pure English mein mat likhiye.

Tone: polite, respectful, professional — kabhi threatening ya pushy mat lagiye.

Accuracy: customer ne jo bhi amount ya date bola hai, usi ko EXACTLY repeat/confirm \
kariye — apni taraf se koi naya number ya date mat banaiye ya badliye.

Rules:
- Kabhi bhi khud se koi discount, waiver, ya deadline extension promise mat kariye \
— aap sirf sun sakte hain aur confirm kar sakte hain jo customer khud bolta hai.
- Agar customer koi payment promise karta hai (amount aur/ya date ke saath), to use \
clearly acknowledge aur confirm kariye, EXACT wahi amount aur date jo customer ne \
bola, taaki wo easily samjha ja sake.
- Agar customer refuse karta hai ya uncertain hai, to politely samjhaiye aur ek \
reasonable next step suggest kariye — force mat kariye.
- Agar customer confused lagta hai, to situation ko clearly explain kariye.
- Har message short rakhiye (2-3 sentences).
"""


class PromptedEscalationAgent(EscalationAgent):
    """Prompted (not fine-tuned) Hinglish agent, backed by a local Ollama model.
    Since there's no real customer to converse with in this synthetic system,
    escalate() drives the customer side from a scripted dialogue scenario
    (data/generators/hinglish_dialogue_generator.py) selected deterministically
    from observable case signals (case_id, attempt_number) — never from
    ground_truth, matching every other model component in this system. The
    same scenario mechanism, run over the full scenario set rather than one
    case, is what evaluation/experiments/run_escalation_rubric_eval.py scores
    against the locked rubric.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        self._base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")

    def _call(self, messages: list[dict]) -> str:
        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": False},
                timeout=180,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self._base_url}. Is it running? "
                f"Try `ollama serve` and `ollama pull {self._model}`."
            ) from e
        return resp.json()["message"]["content"].strip()

    def _select_scenario(self, case: PaymentCase, attempt_number: int) -> DialogueScenario:
        rng = random.Random(f"{case.case_id}:{attempt_number}")
        template = rng.choice(TEMPLATES)
        return instantiate_scenario(template, f"live_{case.case_id}_{attempt_number}", rng)

    def run_scenario(self, scenario: DialogueScenario) -> list[dict]:
        """Runs one scenario end to end and returns the transcript — used both
        by escalate() (one case) and the rubric eval script (the full set)."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        transcript: list[dict] = []

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Case context: {scenario.opening_context} "
                    "Ab customer ko apna pehla message bhejiye (seedha, jaise aap khud likh rahe hain)."
                ),
            }
        )
        opening = self._call(messages)
        messages.append({"role": "assistant", "content": opening})
        transcript.append({"role": "agent", "text": opening})

        for customer_line in scenario.scripted_customer_turns:
            messages.append({"role": "user", "content": customer_line})
            transcript.append({"role": "customer", "text": customer_line})
            reply = self._call(messages)
            messages.append({"role": "assistant", "content": reply})
            transcript.append({"role": "agent", "text": reply})

        return transcript

    def escalate(self, case: PaymentCase, attempt_number: int = 1) -> EscalationOutcome:
        scenario = self._select_scenario(case, attempt_number)
        transcript = self.run_scenario(scenario)
        return EscalationOutcome(
            resolved=scenario.ground_truth.has_promise,
            promise_made=scenario.ground_truth.has_promise,
            conversation=transcript,
        )


def get_escalation_agent(seed: int = 42) -> EscalationAgent:
    backend = os.environ.get("MODEL_BACKEND", "stub")
    if backend == "stub":
        return StubEscalationAgent(seed=seed)
    if backend == "prompted":
        return PromptedEscalationAgent()
    raise NotImplementedError(
        f"MODEL_BACKEND={backend!r} is not available yet (only 'stub' and 'prompted' exist so far)."
    )
