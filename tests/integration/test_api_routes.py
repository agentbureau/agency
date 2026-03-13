"""Integration tests for Phase 7 API routes (Tasks 29-33)."""
import io
import os
import pytest
from fastapi.testclient import TestClient


def _setup_keypair(tmp_path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir(exist_ok=True)
    from agency.auth.keypair import generate_keypair
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )


@pytest.fixture
def client(tmp_path):
    _setup_keypair(tmp_path)
    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        from agency.auth.keypair import load_private_key
        from agency.auth.jwt import create_jwt
        from agency.utils.ids import generate_uuid_v7
        private_key = load_private_key(str(tmp_path / "keys" / "agency.ed25519.pem"))
        jti = generate_uuid_v7()
        app.state.db.execute(
            "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)", (jti, "test-client")
        )
        app.state.db.commit()
        token = create_jwt(private_key, "test-inst", "test-client", jti)
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c
    del os.environ["AGENCY_STATE_DIR"]


# Task 29: Projects API
def test_create_and_get_project(client):
    resp = client.post("/projects", json={"name": "Test Project", "client_id": "c-1"})
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    resp = client.get(f"/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Project"


def test_get_nonexistent_project_404(client):
    resp = client.get("/projects/nonexistent")
    assert resp.status_code == 404


# Task 30: Tasks API (extended)
def test_create_task_missing_task_404_for_agent(client):
    resp = client.get("/tasks/nonexistent/agent")
    assert resp.status_code == 404


# Task 31: Primitive ingestion API
def test_create_primitive(client):
    resp = client.post("/primitives", json={
        "table": "role_components",
        "description": "evaluate output quality",
        "instance_id": "inst-1",
    })
    assert resp.status_code == 201
    assert resp.json()["id"]


def test_create_primitive_invalid_table(client):
    resp = client.post("/primitives", json={
        "table": "bad_table",
        "description": "test",
        "instance_id": "inst-1",
    })
    assert resp.status_code == 400


def test_import_primitives_csv(client):
    csv_content = "description,client_id\nevaluate quality,c-1\nassess accuracy,c-1\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 2
    assert resp.json()["skipped"] == 0


def test_import_csv_deduplicates(client):
    csv_content = "description\nevaluate quality\nevaluate quality\n"
    resp = client.post(
        "/primitives/import?table=role_components&instance_id=inst-1",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1
    assert resp.json()["skipped"] == 1


def test_list_primitives(client):
    client.post("/primitives", json={
        "table": "role_components", "description": "test primitive", "instance_id": "inst-1"
    })
    resp = client.get("/primitives/role_components")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_delete_primitive(client):
    resp = client.post("/primitives", json={
        "table": "role_components", "description": "to be deleted", "instance_id": "inst-1"
    })
    pid = resp.json()["id"]
    resp = client.delete(f"/primitives/role_components/{pid}")
    assert resp.status_code == 204


# Task 32: Evolution oversight API
def test_evolution_proposal_perturbation(client):
    # First create a primitive and agent
    client.post("/primitives", json={
        "table": "role_components", "description": "evaluate quality", "instance_id": "inst-1"
    })
    client.post("/primitives", json={
        "table": "role_components", "description": "assess accuracy", "instance_id": "inst-1"
    })

    task_resp = client.post("/tasks", json={"task_description": "grade this"})
    task_id = task_resp.json()["task_id"]
    agent_resp = client.get(f"/tasks/{task_id}/agent")
    agent_id = agent_resp.json()["agent_id"]

    resp = client.post("/evolution/proposals", json={
        "agent_id": agent_id,
        "task_description": "grade this",
        "strategy": "perturbation",
        "n_variants": 2,
    })
    assert resp.status_code == 201
    assert "variant_agent_ids" in resp.json()


def test_list_proposals(client):
    resp = client.get("/evolution/proposals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
