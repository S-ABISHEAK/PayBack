"""Loads .env before test collection — same pattern as scripts/_bootstrap.py
and frontend/server.py — so env-gated tests (e.g. test_razorpay_integration.py)
see real keys when present instead of always skipping."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
