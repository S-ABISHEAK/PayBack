import os

import pytest

from src.escalation.agent import PromptedEscalationAgent, StubEscalationAgent, _is_degenerate, get_escalation_agent
from tests.factories import make_case


def test_get_escalation_agent_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("MODEL_BACKEND", raising=False)
    agent = get_escalation_agent(seed=1)
    assert isinstance(agent, StubEscalationAgent)


def test_get_escalation_agent_prompted_returns_prompted_instance(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "prompted")
    agent = get_escalation_agent(seed=1)
    assert isinstance(agent, PromptedEscalationAgent)


def test_get_escalation_agent_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "not_a_real_backend")
    with pytest.raises(NotImplementedError):
        get_escalation_agent(seed=1)


def test_scenario_selection_is_deterministic_per_case_and_attempt():
    agent = PromptedEscalationAgent()
    case = make_case("case_x", seed=9)
    s1 = agent._select_scenario(case, attempt_number=1)
    s2 = agent._select_scenario(case, attempt_number=1)
    assert s1.model_dump_json() == s2.model_dump_json()


def test_scenario_selection_varies_by_attempt_number():
    agent = PromptedEscalationAgent()
    case = make_case("case_y", seed=9)
    scenarios = {agent._select_scenario(case, attempt_number=n).category for n in range(1, 6)}
    assert len(scenarios) >= 2  # not every attempt lands on the same category


def test_call_raises_actionable_error_when_ollama_unreachable():
    agent = PromptedEscalationAgent(base_url="http://localhost:1")  # nothing listens here
    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        agent._call([{"role": "user", "content": "hi"}])


def test_is_degenerate_flags_cjk_script_corruption():
    assert _is_degenerate("Sir aapka payment 你好世界 fail ho gaya", prior_agent_texts=[])


def test_is_degenerate_flags_near_verbatim_repeat_of_prior_turn():
    prior = "Sir, aapka payment 3 din pehle fail ho gaya tha, kya aap update kar sakte hain?"
    near_dupe = "Sir, aapka payment 3 din pehle fail ho gaya tha, kya aap update kar sakte ho?"
    assert _is_degenerate(near_dupe, prior_agent_texts=[prior])


def test_is_degenerate_allows_normal_distinct_hinglish_reply():
    prior = "Sir, aapka payment 3 din pehle fail ho gaya tha."
    reply = "Koi baat nahi, aap jab bhi ready ho update kar dijiye, main yahin hoon."
    assert not _is_degenerate(reply, prior_agent_texts=[prior])
