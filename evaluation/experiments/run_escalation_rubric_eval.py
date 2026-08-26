"""Runs the prompted (or fine-tuned, later) Hinglish escalation agent over the
full dialogue scenario set and scores each transcript against the LOCKED
rubric (evaluation/experiments/rubric_prompt.md) using a materially stronger
LLM judge. Writes evaluation/reports/escalation_rubric_report.json.

Requires:
  - Ollama running locally with the configured model pulled (OLLAMA_MODEL,
    default qwen2.5:3b) — see src/escalation/agent.py.
  - An LLM_JUDGE_API_KEY (Anthropic API key) in the environment.

Usage: python scripts/run_escalation_rubric_eval.py [--backend prompted]
"""

from __future__ import annotations

import argparse
import json
import os
import re

from data.generators.failure_generator import REPO_ROOT
from data.generators.hinglish_dialogue_generator import load_jsonl
from src.escalation.agent import PromptedEscalationAgent

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"
RUBRIC_PATH = REPO_ROOT / "evaluation" / "experiments" / "rubric_prompt.md"

JUDGE_MODEL = "claude-sonnet-5"  # materially stronger than the 3B agent under test


def _load_rubric_system_prompt() -> str:
    """Extracts the locked system prompt from rubric_prompt.md's first fenced
    code block, rather than duplicating it here — the markdown file is the
    single source of truth for what "locked" actually means."""
    text = RUBRIC_PATH.read_text()
    blocks = re.findall(r"```\n(.*?)\n```", text, re.DOTALL)
    if not blocks:
        raise ValueError(f"Could not find a fenced code block in {RUBRIC_PATH}")
    return blocks[0].strip()


def _transcript_text(transcript: list[dict]) -> str:
    return "\n".join(f"{turn['role']}: {turn['text']}" for turn in transcript)


def _score_transcript(client, transcript: list[dict], scenario) -> dict:
    user_message = (
        f"Transcript (agent = AI recovery agent, customer = scripted/simulated customer):\n\n"
        f"{_transcript_text(transcript)}\n\n"
        f"Scenario ground truth (for scoring task_success only — the agent did not see this):\n"
        f"has_promise={scenario.ground_truth.has_promise}, "
        f"promised_amount={scenario.ground_truth.promised_amount_inr}, "
        f"promised_date_offset_days={scenario.ground_truth.promised_date_offset_days}\n\n"
        f"Score this transcript per the system prompt's 3 criteria."
    )
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=300,
        system=_load_rubric_system_prompt(),
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Judge did not return parseable JSON: {text!r}")
    return json.loads(match.group(0))


def main(backend: str = "prompted") -> None:
    if backend != "prompted":
        raise NotImplementedError("Only 'prompted' is available until Phase 7 adds a fine-tuned backend.")

    api_key = os.environ.get("LLM_JUDGE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "No LLM_JUDGE_API_KEY (or ANTHROPIC_API_KEY) set in the environment. "
            "The rubric judge must be a materially stronger model than the agent under test — "
            "set this before running the rubric eval."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    scenarios_path = SAMPLES_DIR / "dialogue_scenarios.jsonl"
    if not scenarios_path.exists():
        raise SystemExit("No dialogue scenarios found. Run scripts/generate_dialogue_scenarios.py first.")
    scenarios = load_jsonl(scenarios_path)

    agent = PromptedEscalationAgent()

    per_scenario = []
    for scenario in scenarios:
        transcript = agent.run_scenario(scenario)
        scores = _score_transcript(client, transcript, scenario)
        per_scenario.append(
            {
                "scenario_id": scenario.scenario_id,
                "category": scenario.category,
                "transcript": transcript,
                "scores": scores,
            }
        )
        print(f"  {scenario.scenario_id:32s} {scores}")

    n = len(per_scenario)
    means = {
        crit: sum(s["scores"][crit] for s in per_scenario) / n
        for crit in ("tone_naturalness", "task_success", "code_switch_quality")
    }
    means["overall"] = sum(means.values()) / len(means)

    report = {
        "backend": backend,
        "model": os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"),
        "judge_model": JUDGE_MODEL,
        "n_scenarios": n,
        "mean_scores": means,
        "per_scenario": per_scenario,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "escalation_rubric_report.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nMean scores over {n} scenarios: {means}")
    print(f"Report written to {REPORTS_DIR / 'escalation_rubric_report.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="prompted")
    args = parser.parse_args()
    main(backend=args.backend)
