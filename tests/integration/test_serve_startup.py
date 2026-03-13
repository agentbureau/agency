import pytest
from fastapi.testclient import TestClient
from agency.config.toml import write_config
from agency.utils.ids import new_uuid


def _write_minimal_config(tmp_path) -> None:
    cfg = {
        "instance_id": new_uuid(),
        "llm_endpoint": "https://api.anthropic.com/v1",
        "llm_model": "claude-sonnet-4-6",
        "llm_api_key": "sk-test",
        "contact_email": "test@example.com",
        "oversight_preference": "discretion",
        "server": {"host": "127.0.0.1", "port": 8000},
        "email": {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "u",
            "smtp_password": "p",
            "sender_address": "u@example.com",
        },
    }
    write_config(cfg, tmp_path / "agency.toml")


def _setup_keypair(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir(exist_ok=True)
    from agency.auth.keypair import generate_keypair
    generate_keypair(
        str(keys_dir / "agency.ed25519.pem"),
        str(keys_dir / "agency.ed25519.pub.pem"),
    )


def test_serve_startup_runs_migrations(tmp_path, monkeypatch):
    """App startup runs migrations and /health returns ok."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    assert (tmp_path / "agency.db").exists()


def test_serve_startup_loads_public_key_when_present(tmp_path, monkeypatch):
    """When key files exist, public_key is loaded into app.state."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _setup_keypair(tmp_path)
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        assert app.state.public_key is not None
        assert app.state.private_key is not None


def test_serve_startup_fails_if_public_key_missing(tmp_path, monkeypatch):
    """Startup aborts with RuntimeError if Ed25519 public key file is absent."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    from agency.api.app import create_app
    with pytest.raises(Exception, match="[Pp]ublic key|agency init"):
        app = create_app()
        with TestClient(app):
            pass
