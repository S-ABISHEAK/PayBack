"""FastAPI app for the Revenue Recovery Engine dashboard.

Thin routing layer only — all file/DB reading lives in ``frontend.loaders``.
Serves a custom HTML/CSS/JS frontend from ``frontend/static`` and a small JSON
API on top of the same in-process code the batch scripts use, so the live
"run an escalation conversation" button makes a real server-side Ollama/Groq
call (full parity with what the old Streamlit app could do).

Run from the repo root:

    python -m uvicorn frontend.server:app --reload   # http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

# Populate MODEL_BACKEND / GROQ_API_KEY / OLLAMA_MODEL / RAZORPAY_* before any
# handler reads os.environ, and make file paths cwd-independent.
load_dotenv(REPO_ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Literal

from frontend.loaders import build_case_detail, build_overview, load_cases
from src.escalation.agent import select_live_scenario

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Revenue Recovery Engine — dashboard")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# In-memory, per-server-process cache of the most recent live action per
# case (an escalation conversation OR a real Razorpay test-mode retry) — NOT
# persisted to disk, NOT written back to
# evaluation/reports/system_case_results.jsonl. That frozen file is what the
# reproducible headline uplift number depends on and must never be mutated by
# a demo click; this cache exists purely so the dashboard can (a) show a live
# run's own outcome next to the frozen one instead of just discarding it, and
# (b) restore the transcript/retry result when you navigate away from a case
# and back, rather than silently losing it. Each entry carries "kind":
# "escalation" | "retry" so the frontend knows how to render it. Resets on
# server restart, by design.
_LIVE_RESULTS: dict[str, dict] = {}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/overview")
def api_overview():
    backend = os.environ.get("MODEL_BACKEND", "stub")
    try:
        overview = build_overview(current_model_backend=backend)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    # Overlay any live-demo outcomes onto the pipeline table rows — clearly
    # tagged (live_demo: true) rather than silently replacing the frozen
    # value, so the two are never confused.
    for row in overview["cases"]:
        live = _LIVE_RESULTS.get(row["case_id"])
        if live:
            row["recovered"] = live["resolved"]
            row["recovery_channel"] = live["recovery_channel"]
            row["live_demo"] = True
    return overview


@app.get("/api/case/{case_id}")
def api_case(case_id: str):
    try:
        detail = build_case_detail(case_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown case_id {case_id!r}")
    # Restores a previous live conversation or retry (if any) so switching
    # cases and coming back doesn't lose it — see _LIVE_RESULTS above.
    detail["live_result"] = _LIVE_RESULTS.get(case_id)
    return detail


class EscalateRequest(BaseModel):
    backend: Literal["prompted", "groq_prompted"] = "prompted"


@app.post("/api/case/{case_id}/escalate")
def api_escalate(case_id: str, req: EscalateRequest):
    # Confirm the case exists before spending a model call on it.
    try:
        detail = build_case_detail(case_id)
        case = load_cases()[case_id]
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown case_id {case_id!r}")

    # select_live_scenario uses this case's real amount_inr, not a synthetic
    # one — see its docstring for the bug this replaced (a live conversation
    # about case X's failure would show an unrelated random amount).
    scenario = select_live_scenario(case, attempt_number=1)

    try:
        if req.backend == "groq_prompted":
            from src.escalation.agent import GroqEscalationAgent

            agent = GroqEscalationAgent()
        else:
            from src.escalation.agent import PromptedEscalationAgent

            agent = PromptedEscalationAgent()
        transcript = agent.run_scenario(scenario)
    except (RuntimeError, SystemExit) as e:
        # PromptedEscalationAgent raises RuntimeError when Ollama is unreachable;
        # GroqEscalationAgent.__init__ raises SystemExit (not a subclass of
        # Exception!) when GROQ_API_KEY is missing.
        raise HTTPException(status_code=502, detail=str(e) or e.__class__.__name__)
    except Exception as e:  # e.g. a Groq HTTP timeout — a live demo must never hard-500
        raise HTTPException(status_code=502, detail=f"{e.__class__.__name__}: {e}")

    # Same outcome logic _ConversationalEscalationAgent.escalate() uses
    # (resolved = a promise was made) — the frozen `recovered`/`channel`/
    # `guardrail_violations` fields in the pipeline table come ONLY from
    # evaluation/reports/system_case_results.jsonl (the batch eval run, using
    # the deterministic stub executor, over held-out cases only) and are
    # deliberately never mutated by a live demo click — this is that live
    # run's own outcome, surfaced here instead, not written back to the
    # frozen report.
    resolved = scenario.ground_truth.has_promise
    result = {
        "kind": "escalation",
        "scenario_category": scenario.category,
        "ground_truth": {
            "has_promise": scenario.ground_truth.has_promise,
            "promised_amount_inr": scenario.ground_truth.promised_amount_inr,
            "promised_date_offset_days": scenario.ground_truth.promised_date_offset_days,
        },
        "transcript": transcript,
        "backend_used": req.backend,
        "model": getattr(agent, "_model", None),
        "resolved": resolved,
        "recovery_channel": "escalation" if resolved else None,
    }
    _LIVE_RESULTS[case_id] = result
    return result


@app.post("/api/case/{case_id}/retry")
def api_retry(case_id: str):
    """Runs one real retry attempt against Razorpay's actual test-mode API
    (RazorpayTestModeRetryExecutor — a real Order is created; the
    success/failure outcome is drawn from the same synthetic probability
    model the stub executor uses, since a full checkout flow is out of scope
    for a batch/demo evaluator — see src/retry/executor.py's own docstring).
    This is the live counterpart to scripts/verify_razorpay_integration.py's
    one-off subsample check — a single case, on demand, from the dashboard."""
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=502,
            detail="RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — required to run a real retry.",
        )
    try:
        case = load_cases()[case_id]
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown case_id {case_id!r}")

    from src.retry.executor import RazorpayTestModeRetryExecutor

    try:
        executor = RazorpayTestModeRetryExecutor(key_id=key_id, key_secret=key_secret)
        retry_result = executor.execute_retry(case, attempt_number=case.context.attempt_count + 1)
    except Exception as e:  # a live demo must never hard-500 on a network/API hiccup
        raise HTTPException(status_code=502, detail=f"{e.__class__.__name__}: {e}")

    result = {
        "kind": "retry",
        "resolved": retry_result.success,
        "recovery_channel": "retry" if retry_result.success else None,
        "razorpay_order_id": retry_result.razorpay_order_id,
        "reason": retry_result.reason,
    }
    _LIVE_RESULTS[case_id] = result
    return result
