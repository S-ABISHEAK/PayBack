"""Append-only audit trail. Deliberately exposes no update/delete method —
that omission, not a database constraint, is what earns "immutable-style
audit trail": every decision, model output, policy result, and action is
INSERT-only, in order, per case."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.audit.db import audit_events_table


class AuditLogger:
    def __init__(self, engine: Engine):
        self._engine = engine

    def log_event(self, case_id: str, event_type: str, payload: dict) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                audit_events_table.insert().values(
                    case_id=case_id,
                    event_type=event_type,
                    payload_json=json.dumps(payload, default=str),
                    created_at=datetime.now(timezone.utc),
                )
            )

    def get_events(self, case_id: str) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(audit_events_table)
                .where(audit_events_table.c.case_id == case_id)
                .order_by(audit_events_table.c.id)
            ).fetchall()
        return [
            {
                "id": row.id,
                "case_id": row.case_id,
                "event_type": row.event_type,
                "payload": json.loads(row.payload_json),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
