"""Wave 0 round-trip integration tests.

These tests would have caught both bug 17a and 17b.
They exercise the full API path through FastAPI TestClient.
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app
from agency.auth.keypair import generate_keypair, load_private_key
from agency.auth.jwt import create_jwt
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive
from agency.utils.ids import generate_uuid_v7


def _setup_env(tmp_path, monkeypatch):
    """Set up a complete Agency test environment."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))

    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )

    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    for desc in [
        "write clear and concise code",
        "review code for quality issues",
        "design system architecture",
        "test software thoroughly",
        "document technical decisions",
    ]:
        insert_primitive(conn, "role_components", description=desc, instance_id="inst-1")
    insert_primitive(conn, "desired_outcomes",
                     description="produce working, well-tested software",
                     instance_id="inst-1")
    insert_primitive(conn, "trade_off_configs",
                     description="quality and correctness over speed",
                     instance_id="inst-1")
    conn.close()


def _make_auth(tmp_path, app):
    """Create a valid auth header. Must be called inside TestClient context."""
    private_key = load_private_key(str(tmp_path / "keys" / "agency.ed25519.pem"))
    jti = generate_uuid_v7()
    app.state.db.execute(
        "INSERT INTO issued_tokens (jti, client_id) VALUES (?, ?)",
        (jti, "test-client"),
    )
    app.state.db.commit()
    token = create_jwt(private_key, "test-inst", "test-client", jti)
    return {"Authorization": f"Bearer {token}"}


def test_batch_assign_then_get_task_shows_composition(tmp_path, monkeypatch):
    """§1.1 AC: batch assign -> get_task -> composition linked, non-null agent_hash."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)

        r = c.post("/projects", json={"name": "roundtrip-test"}, headers=auth)
        assert r.status_code == 201
        pid = r.json()["project_id"]

        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "rt1", "description": "write a sorting algorithm"},
            {"external_id": "rt2", "description": "design a REST API"},
        ]}, headers=auth)
        assert r.status_code == 200
        body = r.json()

        for ext_id in ("rt1", "rt2"):
            assignment = body["assignments"][ext_id]
            assert "agent_id" in assignment
            assert len(assignment["agent_id"]) == 36, "agent_id must be UUID"
            assert "agency_task_id" in assignment

        for ext_id in ("rt1", "rt2"):
            task_id = body["assignments"][ext_id]["agency_task_id"]
            r = c.get(f"/tasks/{task_id}", headers=auth)
            assert r.status_code == 200
            task = r.json()
            assert task["agent_hash"] is not None, "agent_hash should not be null"
            assert len(task["agent_hash"]) == 64, "agent_hash should be SHA-256"
            assert task["rendered_prompt"] != "", "rendered_prompt should not be empty"
            assert task["state"] == "assigned"


def test_batch_assign_fk_type_verification(tmp_path, monkeypatch):
    """§1.1 AC: tasks.agent_composition_id is a valid UUID present in agents.id."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)

        r = c.post("/projects", json={"name": "fk-test"}, headers=auth)
        pid = r.json()["project_id"]

        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "fk1", "description": "test FK integrity"},
        ]}, headers=auth)
        assert r.status_code == 200
        task_id = r.json()["assignments"]["fk1"]["agency_task_id"]

        conn = app.state.db
        row = conn.execute(
            "SELECT agent_composition_id FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        composition_id = row[0]

        assert len(composition_id) == 36, \
            f"agent_composition_id should be UUID (36), got {len(composition_id)}"

        agent = conn.execute(
            "SELECT id FROM agents WHERE id = ?",
            (composition_id,),
        ).fetchone()
        assert agent is not None, "agent_composition_id must reference a real agent"


def test_submit_evaluation_then_get_task_shows_received(tmp_path, monkeypatch):
    """§1.2 AC: submit evaluation -> get_task -> state = evaluation_received."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)

        r = c.post("/projects", json={"name": "eval-test"}, headers=auth)
        pid = r.json()["project_id"]

        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "ev1", "description": "evaluate this code"},
        ]}, headers=auth)
        task_id = r.json()["assignments"]["ev1"]["agency_task_id"]

        r = c.get(f"/tasks/{task_id}/evaluator", headers=auth)
        assert r.status_code == 200
        callback_jwt = r.json()["callback_jwt"]

        r = c.post(f"/tasks/{task_id}/evaluation", json={
            "output": "Code looks good, well-structured",
            "score": 85,
            "score_type": "percentage",
            "task_completed": True,
            "callback_jwt": callback_jwt,
        }, headers=auth)
        assert r.status_code == 200

        r = c.get(f"/tasks/{task_id}", headers=auth)
        assert r.status_code == 200
        assert r.json()["state"] == "evaluation_received", \
            "State should be evaluation_received after submission"

        eval_data = r.json()["evaluation"]
        assert eval_data is not None
        assert eval_data["evaluation_status"] == "confirmed"
        assert eval_data["score"] == 85


def test_deduplication_shares_composition(tmp_path, monkeypatch):
    """§1.1 AC: 2 tasks that dedup to same agent share the same UUID in agents.id."""
    _setup_env(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)

        r = c.post("/projects", json={"name": "dedup-test"}, headers=auth)
        pid = r.json()["project_id"]

        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "d1", "description": "write unit tests"},
            {"external_id": "d2", "description": "write unit tests"},
        ]}, headers=auth)
        assert r.status_code == 200
        body = r.json()

        id1 = body["assignments"]["d1"]["agent_id"]
        id2 = body["assignments"]["d2"]["agent_id"]
        assert id1 == id2, "Identical tasks should share the same agent_id"

        conn = app.state.db
        for ext_id in ("d1", "d2"):
            task_id = body["assignments"][ext_id]["agency_task_id"]
            row = conn.execute(
                "SELECT agent_composition_id FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            assert row[0] == id1, "Both tasks should have same agent_composition_id"
