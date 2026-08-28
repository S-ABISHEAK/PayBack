"""Dashboard: case pipeline table, system-vs-baseline comparison, and a
single-case detail/audit-timeline view — a case must be traceable from
failure to final outcome on one screen (spec §15).
"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from data.generators.failure_generator import load_jsonl
from data.generators.split import load_ids
from evaluation.metrics.compute import load_case_results
from src.audit.db import get_engine
from src.audit.logger import AuditLogger

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"

st.set_page_config(page_title="Revenue Recovery Engine", layout="wide")
st.title("AI Subscription Payment Recovery Engine")

cases_path = SAMPLES_DIR / "cases.jsonl"
if not cases_path.exists():
    st.warning("No dataset found yet. Run `python scripts/generate_dataset.py` first.")
    st.stop()

cases = load_jsonl(cases_path)
cases_by_id = {c.case_id: c for c in cases}
holdout_ids = load_ids(SAMPLES_DIR / "holdout_case_ids.txt") if (SAMPLES_DIR / "holdout_case_ids.txt").exists() else set()

system_results_path = REPORTS_DIR / "system_case_results.jsonl"
system_results_by_id = (
    {r.case_id: r for r in load_case_results(system_results_path)} if system_results_path.exists() else {}
)

rows = [
    {
        "case_id": c.case_id,
        "amount_inr": c.context.amount_inr,
        "subscription_state": c.context.subscription_state.value,
        "attempt_count": c.context.attempt_count,
        "observed_reason": c.observed.reason,
        "is_retry_eligible": c.context.is_retry_eligible,
        "is_escalation_eligible": c.context.is_escalation_eligible,
        "split": "held-out" if c.case_id in holdout_ids else "dev",
        # ground_truth shown here only because this is a build-time debugging
        # view over the generator's own output, not a diagnosis-model input.
        "true_cause (ground truth)": c.ground_truth.true_cause.value,
        "recovered": system_results_by_id[c.case_id].recovered if c.case_id in system_results_by_id else None,
        "recovery_channel": (
            system_results_by_id[c.case_id].recovery_channel if c.case_id in system_results_by_id else None
        ),
        "guardrail_violations": (
            system_results_by_id[c.case_id].guardrail_violations if c.case_id in system_results_by_id else None
        ),
    }
    for c in cases
]
df = pd.DataFrame(rows)

tab_overview, tab_case = st.tabs(["Overview & comparison", "Case detail"])

with tab_overview:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total cases", len(df))
    col2.metric("Held-out cases", int((df["split"] == "held-out").sum()))
    col3.metric("Total ₹ (all cases)", f"{df['amount_inr'].sum():,.0f}")

    st.subheader("Case pipeline")
    fc1, fc2 = st.columns(2)
    split_filter = fc1.selectbox("Split", ["all", "dev", "held-out"])
    outcome_filter = fc2.selectbox(
        "Outcome (system, held-out only)",
        ["all", "unrecovered", "recovered", "guardrail violation"],
        help="Use this to jump straight to failure cases for replay — e.g. 'unrecovered' "
             "or 'guardrail violation' — then look them up in the Case detail tab.",
    )
    view = df if split_filter == "all" else df[df["split"] == split_filter]
    if outcome_filter == "unrecovered":
        view = view[view["recovered"] == False]  # noqa: E712 (pandas needs the literal, not `is False`)
    elif outcome_filter == "recovered":
        view = view[view["recovered"] == True]  # noqa: E712
    elif outcome_filter == "guardrail violation":
        view = view[view["guardrail_violations"].fillna(0) > 0]
    st.dataframe(view, use_container_width=True, height=300)
    if system_results_by_id:
        st.caption(f"{len(system_results_by_id)} cases have system results loaded from "
                   f"`{system_results_path.name}` — run `python scripts/run_system_eval.py` to refresh.")
    else:
        st.caption("No system results loaded yet — run `python scripts/run_system_eval.py` to populate "
                   "the recovered/channel/guardrail_violations columns.")

    st.subheader("Baseline vs. system (held-out)")
    baseline_path = REPORTS_DIR / "baseline_report.json"
    system_path = REPORTS_DIR / "system_report.json"
    if baseline_path.exists() and system_path.exists():
        baseline = json.loads(baseline_path.read_text())
        system = json.loads(system_path.read_text())
        uplift = system["recovery_rate"] - baseline["recovery_rate"]

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("₹ at risk", f"{system['rupees_at_risk']:,.0f}")
        b2.metric("Baseline recovery rate", f"{baseline['recovery_rate']:.1%}")
        b3.metric("System recovery rate", f"{system['recovery_rate']:.1%}")
        b4.metric("Uplift", f"{uplift:+.1%}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Retry-only ₹ (system)", f"{system['retry_only_recovered_inr']:,.0f}")
        c2.metric("Escalation-assisted ₹ (system)", f"{system['escalation_assisted_recovered_inr']:,.0f}")
        c3.metric("Escalation rate", f"{system['escalation_rate']:.1%}")
        c4.metric("Guardrail violations", system["guardrail_violations"])

        st.caption(
            "Both runs use the same held-out population and the same multi-attempt budget "
            "(MAX_ATTEMPTS retries); the baseline never escalates. Attempt-outcome probabilities "
            "decay with repeated tries on the same case, applied identically to both runs, so "
            "the comparison isolates diagnosis-aware routing + the escalation channel, not attempt count."
        )
    else:
        st.info("Run `python scripts/run_baseline_eval.py` and `python scripts/run_system_eval.py` to populate this.")

    st.subheader("Slice analysis")
    st.caption(
        "Recovery rate and uplift broken down by failure category, amount bucket, and "
        "attempt count (spec §12) — the headline uplift number alone can hide where the "
        "system actually helps vs. where a case is genuinely hard to recover regardless."
    )
    slice_path = REPORTS_DIR / "slice_analysis_report.json"
    if slice_path.exists():
        slice_report = json.loads(slice_path.read_text())
        dim_labels = {
            "failure_category": "By failure category (ground truth)",
            "amount_bucket": "By amount bucket",
            "attempt_count": "By attempt count at detection",
        }
        for dim_name, label in dim_labels.items():
            st.write(f"**{label}**")
            slice_df = pd.DataFrame(
                [
                    {
                        "slice": slice_value,
                        "n_cases": m["n_cases"],
                        "baseline_recovery_rate": m["baseline_recovery_rate"],
                        "system_recovery_rate": m["system_recovery_rate"],
                        "uplift": m["uplift"],
                    }
                    for slice_value, m in slice_report[dim_name].items()
                ]
            ).set_index("slice")
            st.dataframe(
                slice_df.style.format(
                    {"baseline_recovery_rate": "{:.1%}", "system_recovery_rate": "{:.1%}", "uplift": "{:+.1%}"}
                ),
                use_container_width=True,
            )
    else:
        st.info("Run `python scripts/run_slice_analysis.py` to populate this (needs both eval runs first).")

    st.subheader("Promise extraction (independent eval)")
    promise_report_path = REPORTS_DIR / "promise_extraction_report.json"
    if promise_report_path.exists():
        promise_report = json.loads(promise_report_path.read_text())
        p1, p2, p3 = st.columns(3)
        p1.metric("Precision", f"{promise_report['precision']:.1%}")
        p2.metric("Recall", f"{promise_report['recall']:.1%}")
        p3.metric("F1", f"{promise_report['f1']:.1%}")
        if promise_report["backend"] == "rule_based":
            st.warning(
                "⚠️ This score is evaluated on the same hand-authored Hinglish vocabulary the "
                "rule-based extractor's keyword rules were built from (data/generators/"
                "hinglish_dialogue_generator.py) — it's a sanity check that the rules are internally "
                "consistent, NOT evidence of generalization to free-form or agent-generated text. "
                "The real robustness test is the LLM-based extractor (src/promise/extractor.py:"
                "LLMPromiseExtractor), which is implemented but blocked pending Ollama."
            )
    else:
        st.info("Run `python scripts/evaluate_promise_extraction.py` to populate this.")

with tab_case:
    st.subheader("Single-case trace")
    case_id = st.selectbox("Case", sorted(cases_by_id.keys()))
    case = cases_by_id[case_id]

    d1, d2, d3 = st.columns(3)
    d1.metric("Amount (₹)", f"{case.context.amount_inr:,.2f}")
    d2.metric("Subscription state", case.context.subscription_state.value)
    d3.metric("Attempt count", case.context.attempt_count)

    if case_id in system_results_by_id:
        r = system_results_by_id[case_id]
        outcome_label = "✅ Recovered" if r.recovered else "❌ Not recovered"
        channel_label = f" via {r.recovery_channel}" if r.recovery_channel else ""
        gv_label = f" · ⚠️ {r.guardrail_violations} guardrail violation(s)" if r.guardrail_violations else ""
        st.markdown(f"**System outcome:** {outcome_label}{channel_label}{gv_label}")
    else:
        st.caption("No system result for this case yet — run `python scripts/run_system_eval.py`.")

    st.write(f"**Observed failure:** `{case.observed.code.value}` / `{case.observed.reason}` "
             f"(source={case.observed.source.value}, step={case.observed.step.value})")
    st.write(f"**Ground truth cause (hidden from the system):** `{case.ground_truth.true_cause.value}`")

    db_path = REPO_ROOT / "data" / "recovery.db"
    if not db_path.exists():
        st.info("No audit trail yet. Run `python scripts/run_system_eval.py` or `python scripts/replay_case.py "
                 f"{case_id}` first.")
    else:
        logger = AuditLogger(get_engine(db_path))
        events = logger.get_events(case_id)
        if not events:
            st.info(f"No audit events for {case_id} yet — run `python scripts/replay_case.py {case_id}`.")
        else:
            st.write(f"**Audit timeline** ({len(events)} events — a case may appear multiple times "
                     "if evaluated across several runs; nothing is ever overwritten):")
            for e in events:
                st.text(f"[{e['created_at']}] {e['event_type']:<18} {e['payload']}")

            promise_events = [e for e in events if e["event_type"] == "promise_extraction"]
            if promise_events:
                st.write("**Extracted promise (most recent):**")
                st.json(promise_events[-1]["payload"])

    st.divider()
    st.subheader("Escalation conversation (live, prompted agent)")
    st.caption(
        "Runs a real Ollama-backed conversation for this case (Phase 3's prompted "
        "escalation agent). The customer side is scripted from a dialogue scenario "
        "selected deterministically from this case_id + attempt number — see "
        "src/escalation/agent.py for why."
    )
    if st.button("Run live escalation conversation", key=f"escalate_{case_id}"):
        from src.escalation.agent import PromptedEscalationAgent

        try:
            agent = PromptedEscalationAgent()
            scenario = agent._select_scenario(case, attempt_number=1)
            with st.spinner(f"Talking to {agent._model} via Ollama..."):
                transcript = agent.run_scenario(scenario)
            st.write(f"**Scenario category:** `{scenario.category}` — "
                     f"ground truth: has_promise={scenario.ground_truth.has_promise}, "
                     f"amount={scenario.ground_truth.promised_amount_inr}, "
                     f"date_offset_days={scenario.ground_truth.promised_date_offset_days}")
            for turn in transcript:
                speaker = "🤖 Agent" if turn["role"] == "agent" else "🧑 Customer"
                st.markdown(f"**{speaker}:** {turn['text']}")
        except RuntimeError as e:
            st.error(str(e))
