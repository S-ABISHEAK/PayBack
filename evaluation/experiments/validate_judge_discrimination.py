"""Adversarial validity check for the rubric judge itself, not the agent.

The escalation-agent rubric score only means something if the judge actually
penalizes bad output rather than rubber-stamping anything fluent-looking. This
takes 4 real, already-scored transcripts from the groq_prompted run (near-
perfect originals) and deliberately corrupts each with one distinct, concrete
failure mode a real agent could produce, then rescores the corrupted version
with the exact same judge/rubric used everywhere else in this project. If
scores drop hard on the corrupted versions, the judge is discriminating
real quality, not noise — which is what the 4.63/5 headline number depends on.

Corruption types, one per scenario:
  - wrong_amount_and_date: agent confirms a DIFFERENT amount/date than the
    customer actually said (violates the explicit accuracy rule in
    SYSTEM_PROMPT; also contradicts scenario.ground_truth, which task_success
    is scored against).
  - fabricated_promise: agent falsely claims a payment promise on a scenario
    where the customer explicitly refused and asked to cancel.
  - broken_grammar: agent's final reply replaced with garbled, ungrammatical
    Hinglish word-salad.
  - rude_tone: agent's final reply replaced with pushy/threatening language,
    directly violating the explicit tone rule.

Usage: python scripts/validate_judge_discrimination.py
Writes evaluation/reports/judge_discrimination_check.json.
"""

from __future__ import annotations

import copy
import json
import os

from data.generators.failure_generator import REPO_ROOT
from data.generators.hinglish_dialogue_generator import load_jsonl
from evaluation.experiments.run_escalation_rubric_eval import GROQ_BASE_URL, _score_transcript

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"
GROQ_REPORT_PATH = REPORTS_DIR / "escalation_rubric_report.groq_prompted.json"

JUDGE_MODEL = "openai/gpt-oss-120b"  # same judge groq_prompted uses — must stay stronger than qwen3.8-27b

CORRUPTIONS = {
    "dlg_promise_to_pay_002": (
        "wrong_amount_and_date",
        (
            "Bilkul, main aapke is commitment ko note kar raha hoon ki aap 15 din mein "
            "Rs. 500 ka payment kar denge. Koi tension nahi, jab tak aap bata nahi dete "
            "main koi aur attempt nahi karunga."
        ),
    ),
    "dlg_refusal_000": (
        "fabricated_promise",
        (
            "Bahut badhiya, mujhe khushi hai ki aap kal Rs. 298.25 ka payment kar denge "
            "jaisa aapne promise kiya. Main isko note kar raha hoon."
        ),
    ),
    "dlg_successful_recovery_001": (
        "broken_grammar",
        (
            "hoon samajh ka bilkul confirm karta rahaa — shaam Rs. 291.79 ka aaj tak payment "
            "aap complete denge kar main isko note kar lta hun agar kuch change ho batiyega."
        ),
    ),
    "dlg_delayed_payment_003": (
        "rude_tone",
        (
            "Agar aap ABHI payment nahi karte hain to hum aapki service turant band kar "
            "denge aur aapke against legal action lenge. Turant paisa bhejo, koi excuse "
            "nahi chalega."
        ),
    ),
}


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_JUDGE_API_KEY")
    if not api_key:
        raise SystemExit("No GROQ_API_KEY (or LLM_JUDGE_API_KEY) set in the environment.")
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    groq_report = json.loads(GROQ_REPORT_PATH.read_text())
    original_by_id = {s["scenario_id"]: s for s in groq_report["per_scenario"]}
    scenarios_by_id = {s.scenario_id: s for s in load_jsonl(SAMPLES_DIR / "dialogue_scenarios.jsonl")}

    results = []
    for scenario_id, (corruption_type, corrupted_text) in CORRUPTIONS.items():
        original = original_by_id[scenario_id]
        scenario = scenarios_by_id[scenario_id]

        corrupted_transcript = copy.deepcopy(original["transcript"])
        corrupted_transcript[-1]["text"] = corrupted_text

        corrupted_scores = _score_transcript(client, JUDGE_MODEL, corrupted_transcript, scenario)

        result = {
            "scenario_id": scenario_id,
            "corruption_type": corruption_type,
            "original_scores": original["scores"],
            "corrupted_transcript_last_turn": corrupted_text,
            "corrupted_scores": corrupted_scores,
        }
        results.append(result)
        print(f"\n=== {scenario_id} ({corruption_type}) ===")
        print(f"  original:  {original['scores']}")
        print(f"  corrupted: {corrupted_scores}")

    def _overall(scores: dict) -> float:
        return (scores["tone_naturalness"] + scores["task_success"] + scores["code_switch_quality"]) / 3

    deltas = [_overall(r["original_scores"]) - _overall(r["corrupted_scores"]) for r in results]
    mean_drop = sum(deltas) / len(deltas)

    report = {
        "judge_model": JUDGE_MODEL,
        "n_corruption_cases": len(results),
        "mean_overall_score_drop": mean_drop,
        "per_case_score_drop": deltas,
        "cases": results,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "judge_discrimination_check.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nMean overall-score drop on corrupted transcripts: {mean_drop:.2f} (out of a 1-5 scale)")
    print(f"Report written to {REPORTS_DIR / 'judge_discrimination_check.json'}")


if __name__ == "__main__":
    main()
