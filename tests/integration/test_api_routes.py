"""Integration tests for Phase 7 API routes (Tasks 29-33)."""
import io
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


# Task 29: Projects API
def test_create_and_get_project(client):
    resp = client.post("/projects", json={"name": "Test Project", "client_id": "c-1"},
                       headers=AUTH)
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    resp = client.get(f"/projects/{project_id}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Project"


def test_get_nonexistent_project_404(client):
    resp = client.get("/projects/nonexistent", headers=AUTH)
    assert resp.status_code == 404


# Task 30: Tasks API (extended)
def test_create_task_missing_task_404_for_agent(client):
    resp = client.get("/tasks/nonexistent/agent", headers=AUTH)
    assert resp.status_code == 404


# Task 31: Primitive ingestion API
def test_create_primitive(client):
    resp = client.post("/primitives", json={
        "table": "role_components",
        "description": "evaluate output quality",
        "instance_id": "inst-1",
    }, headers=AUTH)
    assert resp.status_code == 201
    assert resp.json()["id"]


def test_create_primitive_invalid_table(client):
    resp = client.post("/primitives", json={
        "table": "bad_table",
        "description": "test",
        "instance_id": "inst-1",
    }, headers=AUTH)
    assert resp.status_code == 400


def test_import_primitives_csv(client):
    csv_content = "description,client_id\nevaluate quality,c-1\nassess accuracy,c-1\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 2
    assert resp.json()["skipped"] == 0


def test_import_csv_deduplicates(client):
    csv_content = "description\nevaluate quality\nevaluate quality\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1
    assert resp.json()["skipped"] == 1


def test_list_primitives(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "test primitive", "instance_id": "inst-1"
    }, headers=AUTH)
    resp = client.get("/primitives/role_components", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_delete_primitive(client):
    resp = client.post("/primitives", json={
        "table": "role_components", "description": "to be deleted", "instance_id": "inst-1"
    }, headers=AUTH)
    pid = resp.json()["id"]
    resp = client.delete(f"/primitives/role_components/{pid}", headers=AUTH)
    assert resp.status_code == 204


# Task 32: Evolution oversight API
def test_evolution_proposal_perturbation(client):
    # First create a primitive and agent
    client.post("/primitives", json={
        "table": "role_components", "description": "evaluate quality", "instance_id": "inst-1"
    }, headers=AUTH)
    client.post("/primitives", json={
        "table": "role_components", "description": "assess accuracy", "instance_id": "inst-1"
    }, headers=AUTH)

    task_resp = client.post("/tasks", json={"task_description": "grade this"}, headers=AUTH)
    task_id = task_resp.json()["task_id"]
    agent_resp = client.get(f"/tasks/{task_id}/agent", headers=AUTH)
    agent_id = agent_resp.json()["agent_id"]

    resp = client.post("/evolution/proposals", json={
        "agent_id": agent_id,
        "task_description": "grade this",
        "strategy": "perturbation",
        "n_variants": 2,
    }, headers=AUTH)
    assert resp.status_code == 201
    assert "variant_agent_ids" in resp.json()


def test_list_proposals(client):
    resp = client.get("/evolution/proposals", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
