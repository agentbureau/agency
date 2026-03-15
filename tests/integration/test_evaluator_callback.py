import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.keypair import generate_keypair


@pytest.fixture
def client(tmp_path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        from agency.auth.keypair import load_private_key
        from agency.auth.jwt import create_jwt
        from agency.utils.ids import generate_uuid_v7
        private_key = load_private_key(str(keys_dir / "agency.ed25519.pem"))
        jti = generate_uuid_v7()
        app.state.db.execute(
            "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)", (jti, "test-client")
        )
        app.state.db.commit()
        token = create_jwt(private_key, "test-inst", "test-client", jti)
        c.headers.update({"Authorization": f"Bearer {token}"})
        c.app_state = app.state
        yield c
    del os.environ["AGENCY_STATE_DIR"]


def test_create_task_and_get_agent(client):
    # Add primitives so assign_agent can compose an agent
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    })
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    })
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"]
    assert "summarise this document" in data["rendered_prompt"]


def test_get_evaluator_has_callback_jwt(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    })
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    })
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/evaluator")
    assert resp.status_code == 200
    data = resp.json()
    assert "callback_jwt" in data
    assert "rendered_prompt" in data


def test_evaluation_callback_accepted(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    })
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    })
    task_id = resp.json()["task_id"]

    report = {
        "output": "The agent completed the task well.",
        "task_id": task_id,
        "evaluator_agent_id": "evt-abc",
        "evaluator_agent_content_hash": "hash123",
        "task_completed": True,
        "score_type": "percentage",
        "score": 85.0,
        "time_taken_seconds": 30.0,
        "estimated_tokens": 500,
        "task_agent": {"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
        "evaluator_agent": {"model_provider": "anthropic", "model_name": "claude-sonnet-4-6"},
    }
    resp = client.post(f"/tasks/{task_id}/evaluation", json=report)
    assert resp.status_code == 200
