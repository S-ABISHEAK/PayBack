from src.audit.db import get_engine
from src.audit.logger import AuditLogger


def _fresh_logger(tmp_path):
    engine = get_engine(tmp_path / "test_audit.db")
    return AuditLogger(engine)


def test_log_and_retrieve_events_in_order(tmp_path):
    logger = _fresh_logger(tmp_path)
    logger.log_event("case_1", "detected", {"eligible": True})
    logger.log_event("case_1", "diagnosis", {"predicted_cause": "insufficient_funds", "confidence": 0.7})
    logger.log_event("case_1", "final_outcome", {"recovered": True})

    events = logger.get_events("case_1")
    assert [e["event_type"] for e in events] == ["detected", "diagnosis", "final_outcome"]
    assert events[1]["payload"]["confidence"] == 0.7


def test_events_scoped_per_case(tmp_path):
    logger = _fresh_logger(tmp_path)
    logger.log_event("case_1", "detected", {})
    logger.log_event("case_2", "detected", {})
    assert len(logger.get_events("case_1")) == 1
    assert len(logger.get_events("case_2")) == 1


def test_no_update_or_delete_methods_exposed():
    """Immutability is enforced by the absence of these methods, not a DB
    constraint — this test locks that design decision in place."""
    assert not hasattr(AuditLogger, "update_event")
    assert not hasattr(AuditLogger, "delete_event")
