import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app


def test_create_task_persists_across_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    app1 = create_app()
    with TestClient(app1) as c1:
        r = c1.post("/tasks", json={"task_description": "write tests"})
        assert r.status_code == 201
        tid = r.json()["task_id"]

    app2 = create_app()
    with TestClient(app2) as c2:
        r = c2.get(f"/tasks/{tid}/agent")
        assert r.status_code != 404  # task survived restart


def test_get_agent_returns_404_if_task_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    with TestClient(create_app()) as c:
        r = c.get("/tasks/nonexistent/agent")
        assert r.status_code == 404
