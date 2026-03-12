import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    del os.environ["AGENCY_STATE_DIR"]


# No auth header needed — no public key in tmp_path, so middleware bypasses auth
AUTH = {}


def test_create_task_and_get_agent(client):
    # Add primitives so assign_agent can compose an agent
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=AUTH)
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=AUTH)
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/agent", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"]
    assert "summarise this document" in data["rendered_prompt"]


def test_get_evaluator_has_callback_jwt(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=AUTH)
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=AUTH)
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/evaluator", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    # callback_jwt is empty string when no private key is configured
    assert "callback_jwt" in data
    assert "rendered_prompt" in data


def test_evaluation_callback_accepted(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=AUTH)
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=AUTH)
    task_id = resp.json()["task_id"]

    report = {
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
    resp = client.post(f"/tasks/{task_id}/evaluation",
                       json=report, headers=AUTH)
    assert resp.status_code == 202
