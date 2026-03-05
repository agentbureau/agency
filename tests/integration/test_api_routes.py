"""Integration tests for Phase 7 API routes (Tasks 29-33)."""
import io
import os
import pytest
from fastapi.testclient import TestClient
from agency.auth.jwt import create_task_manager_jwt

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


@pytest.fixture
def auth(client):
    token = create_task_manager_jwt(SECRET, "client-1", "inst-1", scope="task")
    return {"Authorization": f"Bearer {token}"}


# Task 29: Projects API
def test_create_and_get_project(client, auth):
    resp = client.post("/projects", json={"name": "Test Project", "client_id": "c-1"},
                       headers=auth)
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    resp = client.get(f"/projects/{project_id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Project"


def test_get_nonexistent_project_404(client, auth):
    resp = client.get("/projects/nonexistent", headers=auth)
    assert resp.status_code == 404


# Task 30: Tasks API (extended)
def test_create_task_missing_task_404_for_agent(client, auth):
    resp = client.get("/tasks/nonexistent/agent", headers=auth)
    assert resp.status_code == 404


# Task 31: Primitive ingestion API
def test_create_primitive(client, auth):
    resp = client.post("/primitives", json={
        "table": "role_components",
        "description": "evaluate output quality",
        "instance_id": "inst-1",
    }, headers=auth)
    assert resp.status_code == 201
    assert resp.json()["id"]


def test_create_primitive_invalid_table(client, auth):
    resp = client.post("/primitives", json={
        "table": "bad_table",
        "description": "test",
        "instance_id": "inst-1",
    }, headers=auth)
    assert resp.status_code == 400


def test_import_primitives_csv(client, auth):
    csv_content = "description,client_id\nevaluate quality,c-1\nassess accuracy,c-1\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 2
    assert resp.json()["skipped"] == 0


def test_import_csv_deduplicates(client, auth):
    csv_content = "description\nevaluate quality\nevaluate quality\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1
    assert resp.json()["skipped"] == 1


def test_list_primitives(client, auth):
    client.post("/primitives", json={
        "table": "role_components", "description": "test primitive", "instance_id": "inst-1"
    }, headers=auth)
    resp = client.get("/primitives/role_components", headers=auth)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_delete_primitive(client, auth):
    resp = client.post("/primitives", json={
        "table": "role_components", "description": "to be deleted", "instance_id": "inst-1"
    }, headers=auth)
    pid = resp.json()["id"]
    resp = client.delete(f"/primitives/role_components/{pid}", headers=auth)
    assert resp.status_code == 204


# Task 32: Evolution oversight API
def test_evolution_proposal_perturbation(client, auth):
    # First create a primitive and agent
    client.post("/primitives", json={
        "table": "role_components", "description": "evaluate quality", "instance_id": "inst-1"
    }, headers=auth)
    client.post("/primitives", json={
        "table": "role_components", "description": "assess accuracy", "instance_id": "inst-1"
    }, headers=auth)

    task_resp = client.post("/tasks", json={"task_description": "grade this"}, headers=auth)
    task_id = task_resp.json()["task_id"]
    agent_resp = client.get(f"/tasks/{task_id}/agent", headers=auth)
    agent_id = agent_resp.json()["agent_id"]

    resp = client.post("/evolution/proposals", json={
        "agent_id": agent_id,
        "task_description": "grade this",
        "strategy": "perturbation",
        "n_variants": 2,
    }, headers=auth)
    assert resp.status_code == 201
    assert "variant_agent_ids" in resp.json()


def test_list_proposals(client, auth):
    resp = client.get("/evolution/proposals", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
