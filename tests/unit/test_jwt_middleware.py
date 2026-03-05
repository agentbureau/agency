import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.jwt import create_task_manager_jwt

SECRET = "a-test-secret-that-is-long-enough-for-hmac"


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


def test_health_unprotected(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_protected_route_without_token_returns_401(client):
    resp = client.get("/tasks/some-id/agent")
    assert resp.status_code == 401


def test_protected_route_with_valid_token(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")
    resp = client.get("/tasks/some-id/agent",
                      headers={"Authorization": f"Bearer {token}"})
    # 404 is fine — route exists but task doesn't; proves middleware passed
    assert resp.status_code in (200, 404)


def test_expired_token_returns_401(client):
    token = create_task_manager_jwt.__wrapped__ if hasattr(
        create_task_manager_jwt, "__wrapped__") else None
    from agency.auth.jwt import create_evaluator_jwt
    token = create_evaluator_jwt(SECRET, "inst-1", "client-1", "proj-1",
                                  "task-1", expiry_seconds=-1)
    resp = client.get("/tasks/some-id/agent",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
