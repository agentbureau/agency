import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.jwt import create_task_manager_jwt, create_evaluator_jwt

SECRET = "a-sufficiently-long-secret-for-testing-hmac"


@pytest.fixture
def client(tmp_path):
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    os.environ["AGENCY_JWT_SECRET"] = SECRET
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    del os.environ["AGENCY_STATE_DIR"]
    del os.environ["AGENCY_JWT_SECRET"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_task_and_get_agent(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")
    # Add primitives so assign_agent can compose an agent
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=_auth(token))
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=_auth(token))
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/agent", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"]
    assert "summarise this document" in data["rendered_prompt"]


def test_get_evaluator_has_callback_jwt(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=_auth(token))
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=_auth(token))
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}/evaluator", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["callback_jwt"]
    assert data["callback_jwt"] in data["rendered_prompt"]


def test_evaluation_callback_accepted(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")
    client.post("/primitives", json={
        "table": "role_components", "description": "summarise documents clearly",
        "instance_id": "inst-1"
    }, headers=_auth(token))
    resp = client.post("/tasks", json={
        "task_description": "summarise this document"
    }, headers=_auth(token))
    task_id = resp.json()["task_id"]

    eval_token = create_evaluator_jwt(SECRET, "inst-1", "client-1", "proj-1",
                                       task_id, expiry_seconds=3600)
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
                       json=report, headers=_auth(eval_token))
    assert resp.status_code == 202
