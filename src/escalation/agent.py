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
import re
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
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

Examples (yeh grammar aur tone ka target hai — apne replies isi style mein likhiye,
inko copy mat kariye, sirf pattern follow kariye):

Example 1 —
Customer: "Sorry yaar, mera card expire ho gaya tha, isliye payment fail hua."
Aapka reply: "Koi baat nahi, ye kaafi common hai. Aap apna updated card details \
add kar denge to agla payment automatically process ho jaayega. Kab tak update \
kar payenge aap?"

Example 2 —
Customer: "Haan main 3 din mein pay kar dunga, abhi thoda cash flow tight hai."
Aapka reply: "Bilkul samajh sakta hoon. To confirm kar raha hoon — aap 3 din mein \
payment complete kar denge. Main isko note kar leta hoon, agar kuch change ho to \
zaroor bataiyega."

Example 3 —
Customer: "Mujhe ye subscription cancel karni hai, mujhe zaroorat nahi hai ab."
Aapka reply: "Samajh gaya, aapki marzi hai. Main is request ko note kar raha hoon \
taaki koi aur payment attempt na ho. Agar future mein zaroorat pade to aap kabhi \
bhi dobara subscribe kar sakte hain."
"""


DEFAULT_TEMPERATURE = 0.4  # lower than Ollama's default — trades phrasing variety for grammatical stability
RETRY_TEMPERATURE = 0.8  # deliberately different sampling for the one regenerate-on-degenerate-output retry

_CJK_PATTERN = re.compile(r"[一-鿿぀-ヿ가-힯]")
_NEAR_DUPLICATE_RATIO = 0.9


def _is_degenerate(text: str, prior_agent_texts: list[str]) -> bool:
    """Catches concrete failure modes seen in rubric-judge notes on real runs:
    a reply corrupting into CJK-script text, and a reply that's a near-verbatim
    repeat of an earlier turn in the same conversation."""
    if _CJK_PATTERN.search(text):
        return True
    return any(SequenceMatcher(None, text, prior).ratio() > _NEAR_DUPLICATE_RATIO for prior in prior_agent_texts)


class _ConversationalEscalationAgent(EscalationAgent):
    """Shared scenario-driving logic for any prompted (not fine-tuned) Hinglish
    agent — subclasses only need to implement `_call`, which sends
    `SYSTEM_PROMPT` + the running message list to whatever backend they wrap
    and returns the raw reply text. Since there's no real customer to converse
    with in this synthetic system, escalate() drives the customer side from a
    scripted dialogue scenario (data/generators/hinglish_dialogue_generator.py)
    selected deterministically from observable case signals (case_id,
    attempt_number) — never from ground_truth, matching every other model
    component in this system. The same scenario mechanism, run over the full
    scenario set rather than one case, is what
    evaluation/experiments/run_escalation_rubric_eval.py scores against the
    locked rubric.
    """

    def _call(self, messages: list[dict], temperature: float = DEFAULT_TEMPERATURE) -> str:
        raise NotImplementedError

    def _generate_reply(self, messages: list[dict], prior_agent_texts: list[str]) -> str:
        """One bounded regenerate-on-degenerate-output retry — same
        validate-then-repair philosophy as LLMPromiseExtractor, applied here
        to catch the CJK-corruption and verbatim-repeat failure modes the
        rubric judge actually flagged on real runs."""
        reply = self._call(messages)
        if _is_degenerate(reply, prior_agent_texts):
            reply = self._call(messages, temperature=RETRY_TEMPERATURE)
        return reply

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
        opening = self._generate_reply(messages, [])
        messages.append({"role": "assistant", "content": opening})
        transcript.append({"role": "agent", "text": opening})
        agent_texts = [opening]

        for customer_line in scenario.scripted_customer_turns:
            messages.append({"role": "user", "content": customer_line})
            transcript.append({"role": "customer", "text": customer_line})
            reply = self._generate_reply(messages, agent_texts)
            messages.append({"role": "assistant", "content": reply})
            transcript.append({"role": "agent", "text": reply})
            agent_texts.append(reply)

        return transcript

    def escalate(self, case: PaymentCase, attempt_number: int = 1) -> EscalationOutcome:
        scenario = self._select_scenario(case, attempt_number)
        transcript = self.run_scenario(scenario)
        return EscalationOutcome(
            resolved=scenario.ground_truth.has_promise,
            promise_made=scenario.ground_truth.has_promise,
            conversation=transcript,
        )


class PromptedEscalationAgent(_ConversationalEscalationAgent):
    """Backed by a local Ollama model (default qwen2.5:7b)."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self._base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")

    def _call(self, messages: list[dict], temperature: float = DEFAULT_TEMPERATURE) -> str:
        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=180,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self._base_url}. Is it running? "
                f"Try `ollama serve` and `ollama pull {self._model}`."
            ) from e
        return resp.json()["message"]["content"].strip()


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# 512 is a generous cap for a 2-3 sentence Hinglish reply, well inside every
# candidate Groq model's max_completion_tokens (16384 for qwen3.8-27b, 65536
# for gpt-oss-120b/20b — verified live via GET /v1/models). Context window is
# 131k tokens on all of them; a full multi-turn scenario transcript here is
# under 2k tokens, so context length is never the limiting factor.
GROQ_AGENT_MAX_TOKENS = 512


class GroqEscalationAgent(_ConversationalEscalationAgent):
    """Prompted Hinglish agent backed by a much larger model hosted on Groq
    (default qwen/qwen3.8-27b, 27B) instead of a local Ollama model — tests
    whether raw scale alone closes the gap seen at 3B/7B, with no fine-tuning
    and no local compute. NOTE: evaluation/experiments/run_escalation_rubric_eval.py
    must use a judge materially stronger than whichever Groq model this wraps
    (e.g. openai/gpt-oss-120b when the agent is qwen/qwen3.8-27b) — it is not
    safe to reuse the same model as both agent and judge.
    """

    def __init__(self, model: str | None = None):
        self._model = model or os.environ.get("GROQ_AGENT_MODEL", "qwen/qwen3.8-27b")
        api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_JUDGE_API_KEY")
        if not api_key:
            raise SystemExit(
                "No GROQ_API_KEY (or LLM_JUDGE_API_KEY) set — required for MODEL_BACKEND=groq_prompted."
            )
        import openai

        self._client = openai.OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    def _call(self, messages: list[dict], temperature: float = DEFAULT_TEMPERATURE) -> str:
        content = self._call_once(messages, temperature)
        if not content:
            # Empty completion is a real, observed transient Groq failure mode
            # (hit once during development) — one bounded retry before giving up.
            content = self._call_once(messages, temperature)
        if not content:
            raise RuntimeError(f"Groq model {self._model!r} returned an empty completion twice in a row.")
        return content.strip()

    def _call_once(self, messages: list[dict], temperature: float) -> str | None:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            max_tokens=GROQ_AGENT_MAX_TOKENS,
            messages=messages,
        )
        return response.choices[0].message.content


def get_escalation_agent(seed: int = 42) -> EscalationAgent:
    backend = os.environ.get("MODEL_BACKEND", "stub")
    if backend == "stub":
        return StubEscalationAgent(seed=seed)
    if backend == "prompted":
        return PromptedEscalationAgent()
    if backend == "groq_prompted":
        return GroqEscalationAgent()
    raise NotImplementedError(
        f"MODEL_BACKEND={backend!r} is not available yet "
        "(only 'stub', 'prompted', and 'groq_prompted' exist so far)."
    )
