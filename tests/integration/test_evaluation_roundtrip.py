"""
Task 40: Full evaluator callback round-trip.
Submit task → get agent + evaluator → simulate callback → verify idempotency.
"""
import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.keypair import generate_keypair, load_public_key
from agency.auth.jwt import verify_jwt
from agency.db.idempotency import is_duplicate, record_jwt


@pytest.fixture
def client(tmp_path):
    # Set up keys so JWT signing works end-to-end
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    priv_path = str(keys_dir / "agency.ed25519.pem")
    pub_path = str(keys_dir / "agency.ed25519.pub.pem")
    generate_keypair(priv_path, pub_path)

    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        c.app_state = app.state
        yield c
    del os.environ["AGENCY_STATE_DIR"]


def _auth_header(client) -> dict:
    """Routes bypass auth checks when public key is set but no Bearer token is given.
    Since all routes are protected, pass a header so middleware runs but still
    passes (middleware only rejects if public_key is set AND token is invalid).
    With a public key present, we need a valid token for protected routes.
    Use a workaround: pass no auth header — but we have a key set, so we need one.
    Instead, use the evaluator jwt from the response for callback, and no-auth for setup.
    """
    return {}


def test_full_roundtrip(client, tmp_path):
    # With public key configured, auth IS enforced — use create_jwt for test tokens
    from agency.auth.keypair import load_private_key
    from agency.auth.jwt import create_jwt
    from agency.utils.ids import generate_uuid_v7
    import sqlite3
    from agency.db.migrations import run_migrations

    keys_dir = tmp_path / "keys"
    priv_path = str(keys_dir / "agency.ed25519.pem")
    pub_path = str(keys_dir / "agency.ed25519.pub.pem")
    private_key = load_private_key(priv_path)
    public_key = load_public_key(pub_path)

    # Insert a token into issued_tokens for auth
    conn = client.app_state.db
    jti = generate_uuid_v7()
    conn.execute("INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)", (jti, "client-1"))
    conn.commit()

    token = create_jwt(private_key, "inst-1", "client-1", jti)
    auth = {"Authorization": f"Bearer {token}"}

    # Add primitives required for agent assignment
    client.post("/primitives", json={
        "table": "role_components", "description": "write clear summaries",
        "instance_id": "inst-1"
    }, headers=auth)

    # 1. Create task
    resp = client.post("/tasks", json={"task_description": "write a summary"},
                       headers=auth)
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    # 2. Get agent
    resp = client.get(f"/tasks/{task_id}/agent", headers=auth)
    assert resp.status_code == 200
    agent_data = resp.json()
    assert agent_data["agent_id"]

    # 3. Get evaluator + callback JWT
    resp = client.get(f"/tasks/{task_id}/evaluator", headers=auth)
    assert resp.status_code == 200
    eval_data = resp.json()
    callback_jwt = eval_data["callback_jwt"]
    assert callback_jwt
    assert callback_jwt in eval_data["rendered_prompt"]

    # 4. Verify callback JWT contains task_id
    payload = verify_jwt(callback_jwt, public_key)
    assert payload["task_id"] == task_id

    # 5. Submit evaluation callback (callback JWT has no jti, so no revocation check)
    report = {
        "output": "The agent completed the task effectively with good quality.",
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
                       json=report, headers={"Authorization": f"Bearer {callback_jwt}"})
    assert resp.status_code == 200


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
