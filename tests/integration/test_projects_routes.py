import sqlite3
import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive


def test_create_project_persists_across_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    app1 = create_app()
    with TestClient(app1) as c1:
        r = c1.post("/projects", json={"name": "myproject"})
        assert r.status_code == 201
        pid = r.json()["project_id"]

    app2 = create_app()
    with TestClient(app2) as c2:
        r = c2.get(f"/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["name"] == "myproject"


def test_get_project_404_if_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/projects/nonexistent")
        assert r.status_code == 404


def _seed_primitives(tmp_path):
    """Seed a real DB at tmp_path/agency.db with primitives for assign tests."""
    db_path = tmp_path / "agency.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    insert_primitive(conn, "role_components",
                     description="complete tasks systematically", instance_id="inst-1")
    conn.close()


def test_batch_assign_returns_packet(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    _seed_primitives(tmp_path)
    with TestClient(create_app()) as c:
        r = c.post("/projects", json={"name": "proj"})
        pid = r.json()["project_id"]
        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "t1", "description": "do a thing"},
        ]})
        assert r.status_code == 200
        body = r.json()
        assert "t1" in body["assignments"]
        assert len(body["agents"]) >= 1


def test_batch_assign_404_if_project_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    with TestClient(create_app()) as c:
        r = c.post("/projects/nonexistent/assign", json={"tasks": []})
        assert r.status_code == 404


def test_batch_assign_503_if_no_primitives(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    with TestClient(create_app()) as c:
        r = c.post("/projects", json={"name": "proj"})
        pid = r.json()["project_id"]
        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"description": "do a thing"},
        ]})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "primitive_store_empty"
