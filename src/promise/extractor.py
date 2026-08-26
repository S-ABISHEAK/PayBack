"""Promise-to-pay extraction interface (spec §8C): exists a promise? amount?
date? confidence?

Two implementations, same interface-swap pattern as src/retry/executor.py
and src/escalation/agent.py:
  - RuleBasedPromiseExtractor: deterministic keyword/regex extraction over
    the customer's turns, no LLM call — real, testable, evaluable today
    without Ollama. Built against the same Hinglish vocabulary used in
    data/generators/hinglish_dialogue_generator.py's templates, so it will
    generalize less well to free-form text than a real LLM would — that
    trade-off is deliberate and disclosed, not hidden.
  - LLMPromiseExtractor: constrained structured-output prompting against the
    same local Ollama model used for escalation (spec §8C explicitly allows
    "a small fine-tuned model or constrained structured output" — this is
    the latter, reusing the model already served in Phase 3 rather than a
    second fine-tuning cycle). Validates the JSON response and retries once
    with a repair prompt before falling back to a safe confidence=0 default
    — that fallback path is the second deliberate-failure-story surface
    named in the implementation plan. Implemented now, untestable until
    Ollama is available (same status as RazorpayTestModeRetryExecutor).
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

import requests
from pydantic import BaseModel


class PromiseExtraction(BaseModel):
    has_promise: bool
    promised_amount_inr: Optional[float] = None
    promised_date_offset_days: Optional[int] = None
    confidence: float


class PromiseExtractor(ABC):
    @abstractmethod
    def extract(self, transcript: list[dict], fallback_amount_inr: float) -> PromiseExtraction: ...


# Hand-authored against the exact idiom used in
# data/generators/hinglish_dialogue_generator.py's templates.
PROMISE_PHRASES = ["kar dunga", "kar doon", "bhej dunga", "de dunga", "pay kar dunga", "zaroor"]
REFUSAL_PHRASES = ["nahi karunga", "pay nahi karunga", "cancel kar do", "refuse"]
UNCERTAIN_PHRASES = ["pata nahi", "shayad", "dekhna padega", "nahi kar sakta", "baad mein dekhta"]

# Longest-phrase-first so "do din" doesn't shadow a longer match, etc.
DAY_WORDS = [
    ("hafte", 7),
    ("week", 7),
    ("paanch din", 5),
    ("char din", 4),
    ("teen din", 3),
    ("do din", 2),
    ("kal", 1),
    ("aaj", 0),
]

AMOUNT_RE = re.compile(
    r"(?:rs\.?|rupees|₹)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rs\.?|rupees|₹)",
    re.IGNORECASE,
)


class RuleBasedPromiseExtractor(PromiseExtractor):
    def extract(self, transcript: list[dict], fallback_amount_inr: float) -> PromiseExtraction:
        customer_text = " ".join(t["text"] for t in transcript if t["role"] == "customer").lower()

        has_refusal = any(p in customer_text for p in REFUSAL_PHRASES)
        has_uncertain = any(p in customer_text for p in UNCERTAIN_PHRASES)
        has_promise_phrase = any(p in customer_text for p in PROMISE_PHRASES)
        has_promise = has_promise_phrase and not has_refusal and not has_uncertain

        amount = None
        date_offset = None
        confidence = 0.3  # neither a clear promise nor a clear refusal/uncertainty — genuinely ambiguous

        if has_promise:
            match = AMOUNT_RE.search(customer_text)
            amount = float((match.group(1) or match.group(2)).replace(",", "")) if match else fallback_amount_inr
            date_offset = next((offset for phrase, offset in DAY_WORDS if phrase in customer_text), None)
            confidence = 0.85 if (match or date_offset is not None) else 0.6
        elif has_refusal or has_uncertain:
            confidence = 0.8

        return PromiseExtraction(
            has_promise=has_promise,
            promised_amount_inr=amount,
            promised_date_offset_days=date_offset,
            confidence=confidence,
        )


EXTRACTION_SYSTEM_PROMPT = """You extract payment-promise information from a Hinglish payment \
collections conversation transcript. Look only at the CUSTOMER's turns. Respond with ONLY a JSON \
object, no other text: \
{"has_promise": <bool>, "promised_amount_inr": <number or null>, "promised_date_offset_days": <integer or null>, "confidence": <0-1 float>}"""


class LLMPromiseExtractor(PromiseExtractor):
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        self._base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")

    def _call(self, prompt: str) -> str:
        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "format": "json",
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self._base_url}. Is it running? "
                f"Try `ollama serve` and `ollama pull {self._model}`."
            ) from e
        return resp.json()["message"]["content"]

    @staticmethod
    def _parse(raw: str) -> Optional[PromiseExtraction]:
        """Strict type validation, not just JSON-parseability: a model that
        outputs {"has_promise": "no", ...} (a string, not a JSON bool) would
        silently become has_promise=True under a naive `bool(...)` cast,
        since "no" is a non-empty string — found via adversarial testing
        (Phase 6). Wrong-typed fields are treated the same as malformed
        JSON: they fail parsing and go through the same repair/fallback path,
        rather than being silently miscoerced into a plausible-looking value."""
        try:
            data = json.loads(raw)
            has_promise = data["has_promise"]
            if not isinstance(has_promise, bool):
                return None
            amount = data.get("promised_amount_inr")
            if amount is not None and not isinstance(amount, (int, float)):
                return None
            date_offset = data.get("promised_date_offset_days")
            if date_offset is not None and not isinstance(date_offset, int):
                return None
            confidence = data.get("confidence", 0.5)
            if not isinstance(confidence, (int, float)):
                return None
            return PromiseExtraction(
                has_promise=has_promise,
                promised_amount_inr=amount,
                promised_date_offset_days=date_offset,
                confidence=float(confidence),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def extract(self, transcript: list[dict], fallback_amount_inr: float) -> PromiseExtraction:
        transcript_text = "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
        prompt = f"Transcript:\n\n{transcript_text}\n\nExtract the promise information."

        raw = self._call(prompt)
        result = self._parse(raw)
        if result is not None:
            return result

        # Repair attempt: one retry with the malformed output named explicitly.
        repair_prompt = f"{prompt}\n\nYour previous response was not valid JSON: {raw!r}. Respond with ONLY valid JSON."
        result = self._parse(self._call(repair_prompt))
        if result is not None:
            return result

        # Safe fallback: malformed output twice in a row must never become a
        # silent wrong action — surface it as zero-confidence, no promise.
        return PromiseExtraction(has_promise=False, confidence=0.0)


def get_promise_extractor() -> PromiseExtractor:
    backend = os.environ.get("PROMISE_EXTRACTOR", "rule_based")
    if backend == "rule_based":
        return RuleBasedPromiseExtractor()
    if backend == "llm":
        return LLMPromiseExtractor()
    raise ValueError(f"Unknown PROMISE_EXTRACTOR backend: {backend!r} (expected 'rule_based' or 'llm')")
