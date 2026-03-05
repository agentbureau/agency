"""
Task 40: Full evaluator callback round-trip.
Submit task → get agent + evaluator → simulate callback → verify idempotency.
"""
import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.jwt import create_task_manager_jwt, verify_jwt
from agency.db.idempotency import is_duplicate, record_jwt

SECRET = "a-sufficiently-long-secret-for-roundtrip-test"


@pytest.fixture
def client(tmp_path):
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    os.environ["AGENCY_JWT_SECRET"] = SECRET
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        c.app_state = app.state
        yield c
    del os.environ["AGENCY_STATE_DIR"]
    del os.environ["AGENCY_JWT_SECRET"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_full_roundtrip(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")

    # 1. Create task
    resp = client.post("/tasks", json={"task_description": "write a summary"},
                       headers=_auth(token))
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    # 2. Get agent
    resp = client.get(f"/tasks/{task_id}/agent", headers=_auth(token))
    assert resp.status_code == 200
    agent_data = resp.json()
    assert agent_data["agent_id"]

    # 3. Get evaluator + callback JWT
    resp = client.get(f"/tasks/{task_id}/evaluator", headers=_auth(token))
    assert resp.status_code == 200
    eval_data = resp.json()
    callback_jwt = eval_data["callback_jwt"]
    assert callback_jwt in eval_data["rendered_prompt"]

    # 4. Verify callback JWT contains task_id
    payload = verify_jwt(SECRET, callback_jwt)
    assert payload["task_id"] == task_id

    # 5. Submit evaluation callback
    report = {
        "task_id": task_id,
        "evaluator_agent_id": eval_data["evaluator_agent_id"],
        "evaluator_agent_content_hash": eval_data["content_hash"],
        "task_completed": True,
        "score_type": "percentage",
        "score": 88.0,
        "time_taken_seconds": 25.0,
        "estimated_tokens": 400,
        "task_agent": {"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
        "evaluator_agent": {"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
    }
    resp = client.post(f"/tasks/{task_id}/evaluation",
                       json=report, headers=_auth(callback_jwt))
    assert resp.status_code == 202


def test_idempotency_duplicate_jwt_rejected(tmp_path):
    """Same JWT + task_id combination must be rejected as duplicate."""
    import sqlite3
    from agency.db.migrations import run_migrations
    conn = sqlite3.connect(tmp_path / "test.db")
    run_migrations(conn)

    assert not is_duplicate(conn, "jwt-abc", "task-xyz")
    record_jwt(conn, "jwt-abc", "task-xyz")
    assert is_duplicate(conn, "jwt-abc", "task-xyz")
    # Different task with same JWT is not a duplicate
    assert not is_duplicate(conn, "jwt-abc", "task-other")
