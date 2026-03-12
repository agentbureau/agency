import os
import pytest
import tomli_w
from fastapi.testclient import TestClient
from agency.auth.keypair import generate_keypair


@pytest.fixture
def state_dir(tmp_path):
    """Create a minimal Agency state directory for startup tests."""
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )
    cfg = {
        "instance_id": "test-inst",
        "server": {"host": "127.0.0.1", "port": 8000},
        "llm": {"backend": "claude-code", "model": "claude-sonnet-4-6"},
        "notifications": {"contact_email": "a@b.com", "oversight_preference": "discretion",
                          "error_notification_timeout": 1800},
        "output": {"attribution": True},
    }
    with open(str(tmp_path / "agency.toml"), "wb") as f:
        tomli_w.dump(cfg, f)
    return str(tmp_path)


def test_health_endpoint_returns_ok(state_dir, monkeypatch):
    """GET /health returns {"status": "ok"} without auth (exempt route)."""
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_startup_enables_wal_mode(state_dir, monkeypatch):
    """agency serve lifespan enables WAL mode on the SQLite connection."""
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app):
        # After startup, query WAL mode on the shared connection
        conn = app.state.db
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


def test_startup_fails_if_public_key_missing(tmp_path, monkeypatch):
    """Startup aborts with clear error if Ed25519 public key file is absent."""
    # State dir with no key files
    cfg = {
        "instance_id": "test-inst",
        "server": {"host": "127.0.0.1", "port": 8000},
        "llm": {"backend": "claude-code", "model": "claude-sonnet-4-6"},
        "notifications": {"contact_email": "a@b.com", "oversight_preference": "discretion",
                          "error_notification_timeout": 1800},
        "output": {"attribution": True},
    }
    with open(str(tmp_path / "agency.toml"), "wb") as f:
        tomli_w.dump(cfg, f)
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    from agency.api.app import create_app
    with pytest.raises(Exception, match="[Pp]ublic key|agency init"):
        app = create_app()
        with TestClient(app):
            pass
