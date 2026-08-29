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


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/overview")
def api_overview():
    backend = os.environ.get("MODEL_BACKEND", "stub")
    try:
        return build_overview(current_model_backend=backend)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/case/{case_id}")
def api_case(case_id: str):
    try:
        detail = build_case_detail(case_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown case_id {case_id!r}")
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

    return {
        "scenario_category": scenario.category,
        "ground_truth": {
            "has_promise": scenario.ground_truth.has_promise,
            "promised_amount_inr": scenario.ground_truth.promised_amount_inr,
            "promised_date_offset_days": scenario.ground_truth.promised_date_offset_days,
        },
        "transcript": transcript,
        "backend_used": req.backend,
        "model": getattr(agent, "_model", None),
    }
