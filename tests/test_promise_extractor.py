import pytest

from src.promise.extractor import (
    LLMPromiseExtractor,
    RuleBasedPromiseExtractor,
    get_promise_extractor,
)


def _customer_transcript(*lines: str) -> list[dict]:
    return [{"role": "customer", "text": line} for line in lines]


def test_clear_promise_with_amount_and_date_detected():
    extractor = RuleBasedPromiseExtractor()
    result = extractor.extract(
        _customer_transcript("Haan bilkul, main aaj shaam tak 500 rupees pay kar dunga, promise."),
        fallback_amount_inr=500,
    )
    assert result.has_promise is True
    assert result.promised_amount_inr == 500
    assert result.promised_date_offset_days == 0
    assert result.confidence > 0.5


def test_promise_without_explicit_amount_falls_back_to_case_amount():
    extractor = RuleBasedPromiseExtractor()
    result = extractor.extract(
        _customer_transcript("Jald hi kar dunga, is hafte ke andar dekh lete hain."),
        fallback_amount_inr=999.0,
    )
    assert result.has_promise is True
    assert result.promised_amount_inr == 999.0
    assert result.promised_date_offset_days == 7


def test_refusal_is_not_a_promise():
    extractor = RuleBasedPromiseExtractor()
    result = extractor.extract(
        _customer_transcript("Jo karna hai kar lijiye, main payment nahi karunga, bas."),
        fallback_amount_inr=500,
    )
    assert result.has_promise is False
    assert result.promised_amount_inr is None


def test_uncertain_language_overrides_a_stray_promise_word():
    """'kar doon' alone looks like a promise phrase, but 'baad mein dekhta
    hoon' right after it makes the whole statement non-committal — the
    extractor must not fire on the isolated keyword."""
    extractor = RuleBasedPromiseExtractor()
    result = extractor.extract(
        _customer_transcript("Shayad kar doon, lekin abhi kuch promise nahi kar sakta, baad mein dekhta hoon."),
        fallback_amount_inr=500,
    )
    assert result.has_promise is False


def test_get_promise_extractor_default_is_rule_based():
    extractor = get_promise_extractor()
    assert isinstance(extractor, RuleBasedPromiseExtractor)


def test_get_promise_extractor_llm(monkeypatch):
    monkeypatch.setenv("PROMISE_EXTRACTOR", "llm")
    extractor = get_promise_extractor()
    assert isinstance(extractor, LLMPromiseExtractor)


def test_get_promise_extractor_unknown_raises(monkeypatch):
    monkeypatch.setenv("PROMISE_EXTRACTOR", "bogus")
    with pytest.raises(ValueError):
        get_promise_extractor()


def test_llm_extractor_raises_actionable_error_when_ollama_unreachable():
    extractor = LLMPromiseExtractor(base_url="http://localhost:1")
    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        extractor.extract(_customer_transcript("kuch bhi"), fallback_amount_inr=500)


def test_llm_extractor_falls_back_safely_on_repeated_malformed_output(monkeypatch):
    """Deliberate-failure-story surface: two malformed responses in a row
    must resolve to a safe, zero-confidence default, never a crash or a
    silently-wrong extraction."""
    extractor = LLMPromiseExtractor()
    monkeypatch.setattr(extractor, "_call", lambda prompt: "this is not json")
    result = extractor.extract(_customer_transcript("kuch bhi"), fallback_amount_inr=500)
    assert result.has_promise is False
    assert result.confidence == 0.0
