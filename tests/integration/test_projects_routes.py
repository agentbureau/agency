import sqlite3
import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app
from agency.auth.keypair import generate_keypair
from agency.db.migrations import run_migrations
from agency.db.primitives import insert_primitive


def _setup_keypair(tmp_path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir(exist_ok=True)
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )


def _make_auth(tmp_path, app):
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
    return {"Authorization": f"Bearer {token}"}


def test_create_project_persists_across_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    app1 = create_app()
    with TestClient(app1) as c1:
        auth = _make_auth(tmp_path, app1)
        r = c1.post("/projects", json={"name": "myproject"}, headers=auth)
        assert r.status_code == 201
        pid = r.json()["project_id"]

    app2 = create_app()
    with TestClient(app2) as c2:
        auth2 = _make_auth(tmp_path, app2)
        r = c2.get(f"/projects/{pid}", headers=auth2)
        assert r.status_code == 200
        assert r.json()["name"] == "myproject"


def test_get_project_404_if_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.get("/projects/nonexistent", headers=auth)
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
    _setup_keypair(tmp_path)
    _seed_primitives(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/projects", json={"name": "proj"}, headers=auth)
        pid = r.json()["project_id"]
        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"external_id": "t1", "description": "do a thing"},
        ]}, headers=auth)
        assert r.status_code == 200
        body = r.json()
        assert "t1" in body["assignments"]
        assert len(body["agents"]) >= 1


def test_batch_assign_404_if_project_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/projects/nonexistent/assign", json={"tasks": []}, headers=auth)
        assert r.status_code == 404


def test_batch_assign_503_if_no_primitives(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        auth = _make_auth(tmp_path, app)
        r = c.post("/projects", json={"name": "proj"}, headers=auth)
        pid = r.json()["project_id"]
        r = c.post(f"/projects/{pid}/assign", json={"tasks": [
            {"description": "do a thing"},
        ]}, headers=auth)
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "primitive_store_empty"
