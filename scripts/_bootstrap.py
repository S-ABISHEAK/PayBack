"""Adds the repo root to sys.path so scripts/ can import src/, data/, evaluation/
as packages when invoked directly (`python scripts/foo.py`) instead of via `-m`.
Also loads .env from the repo root, if present, so RETRY_EXECUTOR/MODEL_BACKEND/
GROQ_API_KEY/etc. don't need to be exported manually every session.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")
