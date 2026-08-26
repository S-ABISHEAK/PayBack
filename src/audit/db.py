"""Shared SQLite schema: `cases` (mutable current state, for replay) and
`audit_events` (append-only — see src/audit/logger.py, which is the only
module allowed to write to it and exposes no update/delete)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "recovery.db"

metadata = MetaData()

cases_table = Table(
    "cases",
    metadata,
    Column("case_id", String, primary_key=True),
    Column("state_json", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

audit_events_table = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", String, nullable=False, index=True),
    Column("event_type", String, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def get_engine(db_path: Path | str = DEFAULT_DB_PATH) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    metadata.create_all(engine)
    return engine
