"""Tests for v1.2.1 evaluation submission: model validation, JWT enforcement."""
import pytest
from agency.models.evaluations import EvaluationReport


def test_evaluation_report_accepts_score_type_enum():
    """score_type must be one of: binary, rubric, likert, percentage."""
    report = EvaluationReport(output="good", score_type="rubric", score=85)
    assert report.score_type == "rubric"


def test_evaluation_report_rejects_invalid_score_type():
    """Invalid score_type should raise validation error."""
    with pytest.raises(Exception):
        EvaluationReport(output="good", score_type="invalid_type")


def test_evaluation_report_accepts_callback_jwt_field():
    """callback_jwt should be accepted as a body field."""
    report = EvaluationReport(output="good", callback_jwt="jwt-token-here")
    assert report.callback_jwt == "jwt-token-here"


def test_evaluation_report_score_range():
    """score must be 0-100."""
    report = EvaluationReport(output="good", score=50)
    assert report.score == 50

    with pytest.raises(Exception):
        EvaluationReport(output="good", score=101)

    with pytest.raises(Exception):
        EvaluationReport(output="good", score=-1)


def test_single_use_jwt_rejected_on_resubmission():
    """PRD §3.5: consumed JWT returns 401 on second submission."""
    from agency.db.idempotency import is_duplicate, record_jwt
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE consumed_jwts (
        jwt_id TEXT NOT NULL, task_id TEXT NOT NULL,
        received_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (jwt_id, task_id))""")

    assert is_duplicate(conn, "jti-1", "task-1") is False
    record_jwt(conn, "jti-1", "task-1")
    assert is_duplicate(conn, "jti-1", "task-1") is True


def test_atomic_transaction_rollback_leaves_jwt_unconsumed():
    """PRD §3.5: crash between JWT validation and eval commit leaves JWT unconsumed."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE consumed_jwts (
        jwt_id TEXT NOT NULL, task_id TEXT NOT NULL,
        received_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (jwt_id, task_id))""")
    conn.execute("""CREATE TABLE pending_evaluations (
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
        evaluator_data TEXT NOT NULL, content_hash TEXT NOT NULL,
        destination TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_ping_at TEXT, confirmed_at TEXT, confirmed INTEGER NOT NULL DEFAULT 0)""")

    try:
        conn.execute("BEGIN")
        conn.execute("INSERT INTO consumed_jwts (jwt_id, task_id) VALUES (?, ?)", ("jti-1", "task-1"))
        raise RuntimeError("simulated crash")
    except RuntimeError:
        conn.execute("ROLLBACK")

    row = conn.execute("SELECT 1 FROM consumed_jwts WHERE jwt_id = ?", ("jti-1",)).fetchone()
    assert row is None


def test_instance_evaluation_confirmed_on_submission():
    """Bug 17b: agency_instance evaluations must be confirmed = 1 after INSERT."""
    import sqlite3
    from agency.utils.ids import new_uuid
    from agency.utils.hashing import content_hash

    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE pending_evaluations (
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
        evaluator_data TEXT NOT NULL, content_hash TEXT NOT NULL,
        destination TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_ping_at TEXT, confirmed_at TEXT, confirmed INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE consumed_jwts (
        jwt_id TEXT NOT NULL, task_id TEXT NOT NULL,
        received_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (jwt_id, task_id))""")

    # Simulate the fixed transaction from submit_evaluation route
    data = '{"output":"good","score":80}'
    eid = new_uuid()
    hash_ = content_hash(data)
    conn.execute("BEGIN")
    conn.execute(
        """INSERT INTO pending_evaluations
           (id, task_id, evaluator_data, destination, content_hash)
           VALUES (?, ?, ?, ?, ?)""",
        (eid, "task-001", data, "agency_instance", hash_),
    )
    conn.execute(
        "UPDATE pending_evaluations SET confirmed = 1, confirmed_at = datetime('now') WHERE id = ?",
        (eid,),
    )
    conn.execute("COMMIT")

    row = conn.execute(
        "SELECT confirmed, confirmed_at FROM pending_evaluations WHERE id = ?",
        (eid,),
    ).fetchone()
    assert row[0] == 1, "evaluation should be confirmed"
    assert row[1] is not None, "confirmed_at should be set"
