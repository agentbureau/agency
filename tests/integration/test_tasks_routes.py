import pytest
from fastapi.testclient import TestClient
from agency.api.app import create_app
from agency.auth.keypair import generate_keypair


def _setup_keypair_and_token(tmp_path, app):
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


def test_create_task_persists_across_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )
    app1 = create_app()
    with TestClient(app1) as c1:
        auth = _setup_keypair_and_token(tmp_path, app1)
        r = c1.post("/tasks", json={"task_description": "write tests"}, headers=auth)
        assert r.status_code == 201
        tid = r.json()["task_id"]

    app2 = create_app()
    with TestClient(app2) as c2:
        auth2 = _setup_keypair_and_token(tmp_path, app2)
        r = c2.get(f"/tasks/{tid}/agent", headers=auth2)
        assert r.status_code != 404  # task survived restart


def test_get_agent_returns_404_if_task_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )
    app = create_app()
    with TestClient(app) as c:
        auth = _setup_keypair_and_token(tmp_path, app)
        r = c.get("/tasks/nonexistent/agent", headers=auth)
        assert r.status_code == 404
