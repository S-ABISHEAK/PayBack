"""Runs the prompted (or fine-tuned, later) Hinglish escalation agent over the
full dialogue scenario set and scores each transcript against the LOCKED
rubric (evaluation/experiments/rubric_prompt.md) using a materially stronger
LLM judge. Writes evaluation/reports/escalation_rubric_report.json (backend
"prompted") or escalation_rubric_report.<backend>.json otherwise.

Two backends, each with its own judge so "materially stronger than the agent"
(spec §9) always holds — see JUDGE_MODEL_BY_BACKEND:
  - "prompted" (default): local Ollama model (OLLAMA_MODEL, default
    qwen2.5:7b) — see src/escalation/agent.py:PromptedEscalationAgent. Judge:
    Groq's qwen/qwen3.8-27b (27B, materially stronger than the local model).
  - "groq_prompted": a much larger model hosted on Groq itself
    (GROQ_AGENT_MODEL, default qwen/qwen3.8-27b, 27B) — see
    src/escalation/agent.py:GroqEscalationAgent. Judge: Groq's
    openai/gpt-oss-120b (120B) — do not reuse qwen3.8-27b as judge here, it's
    now the model under test.

Requires a GROQ_API_KEY (or LLM_JUDGE_API_KEY) in the environment either way
(judge always runs on Groq; the "groq_prompted" backend additionally uses it
for the agent itself). Note: qwen/qwen3.8-27b is listed as a Groq "preview"
model — fine for evaluation use, but it could be swapped/discontinued
upstream without notice; openai/gpt-oss-120b is the documented fallback.

Usage: python scripts/run_escalation_rubric_eval.py [--backend prompted|groq_prompted]
"""

from __future__ import annotations

import argparse
import json
import os
import re

from data.generators.failure_generator import REPO_ROOT
from data.generators.hinglish_dialogue_generator import load_jsonl
from src.escalation.agent import GroqEscalationAgent, PromptedEscalationAgent

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"
RUBRIC_PATH = REPO_ROOT / "evaluation" / "experiments" / "rubric_prompt.md"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Judge must always be materially stronger than the agent under test (spec §9)
# — keyed by backend since "prompted" (local Ollama, small) and "groq_prompted"
# (already a large Groq model) need different judges to keep that true.
JUDGE_MODEL_BY_BACKEND = {
    "prompted": "qwen/qwen3.8-27b",  # 27B vs. the ~3-7B local Ollama agent
    "groq_prompted": "openai/gpt-oss-120b",  # 120B vs. the 27B Groq agent — must stay bigger than GroqEscalationAgent's model
}


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


def _score_transcript(client, judge_model: str, transcript: list[dict], scenario) -> dict:
    user_message = (
        f"Transcript (agent = AI recovery agent, customer = scripted/simulated customer):\n\n"
        f"{_transcript_text(transcript)}\n\n"
        f"Scenario ground truth (for scoring task_success only — the agent did not see this):\n"
        f"has_promise={scenario.ground_truth.has_promise}, "
        f"promised_amount={scenario.ground_truth.promised_amount_inr}, "
        f"promised_date_offset_days={scenario.ground_truth.promised_date_offset_days}\n\n"
        f"Score this transcript per the system prompt's 3 criteria."
    )
    messages = [
        {"role": "system", "content": _load_rubric_system_prompt()},
        {"role": "user", "content": user_message},
    ]

    def _call() -> str:
        # Both judge models are hybrid reasoning models — hidden reasoning
        # tokens count against max_tokens and can silently truncate/empty the
        # visible JSON if left uncapped (observed directly: gpt-oss-120b spent
        # 143/186 tokens on reasoning on a trivial prompt). reasoning_effort=
        # "low" plus a generous max_tokens keeps the visible completion safe.
        response = client.chat.completions.create(
            model=judge_model,
            max_tokens=1200,
            reasoning_effort="low",
            messages=messages,
        )
        return (response.choices[0].message.content or "").strip()

    # One bounded retry on an empty completion — a real, observed transient
    # Groq failure mode (hit once during development mid-run), not a code bug.
    text = _call() or _call()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Judge did not return parseable JSON: {text!r}")
    return json.loads(match.group(0))


def main(backend: str = "prompted", scenarios_path=None) -> None:
    if backend not in JUDGE_MODEL_BY_BACKEND:
        raise NotImplementedError(
            f"backend={backend!r} not supported — choose one of {sorted(JUDGE_MODEL_BY_BACKEND)}."
        )
    judge_model = JUDGE_MODEL_BY_BACKEND[backend]

    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_JUDGE_API_KEY")
    if not api_key:
        raise SystemExit(
            "No GROQ_API_KEY (or LLM_JUDGE_API_KEY) set in the environment. "
            "The rubric judge must be a materially stronger model than the agent under test — "
            "set this before running the rubric eval."
        )
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    scenarios_path = scenarios_path or (SAMPLES_DIR / "dialogue_scenarios.jsonl")
    if not scenarios_path.exists():
        raise SystemExit(f"No dialogue scenarios found at {scenarios_path}.")
    scenarios = load_jsonl(scenarios_path)

    agent = GroqEscalationAgent() if backend == "groq_prompted" else PromptedEscalationAgent()

    per_scenario = []
    for scenario in scenarios:
        transcript = agent.run_scenario(scenario)
        scores = _score_transcript(client, judge_model, transcript, scenario)
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
        "model": agent._model,
        "judge_model": judge_model,
        "scenarios_path": str(scenarios_path),
        "n_scenarios": n,
        "mean_scores": means,
        "per_scenario": per_scenario,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    scenario_stem = scenarios_path.stem  # e.g. "dialogue_scenarios" or "dialogue_scenarios_hard"
    if scenario_stem == "dialogue_scenarios":
        report_name = "escalation_rubric_report.json" if backend == "prompted" else f"escalation_rubric_report.{backend}.json"
    else:
        suffix = scenario_stem.removeprefix("dialogue_scenarios_")
        report_name = f"escalation_rubric_report.{backend}.{suffix}.json"
    with open(REPORTS_DIR / report_name, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nMean scores over {n} scenarios: {means}")
    print(f"Report written to {REPORTS_DIR / report_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="prompted", choices=sorted(JUDGE_MODEL_BY_BACKEND))
    parser.add_argument("--scenarios", default=None, help="Path to a scenarios .jsonl file (default: the frozen dialogue_scenarios.jsonl)")
    args = parser.parse_args()
    from pathlib import Path

    main(backend=args.backend, scenarios_path=Path(args.scenarios) if args.scenarios else None)
