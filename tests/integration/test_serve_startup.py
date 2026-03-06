import pytest
from fastapi.testclient import TestClient
from agency.config.toml import write_config
from agency.utils.ids import new_uuid


def _write_minimal_config(tmp_path, jwt_secret: str) -> None:
    cfg = {
        "instance_id": new_uuid(),
        "llm_endpoint": "https://api.anthropic.com/v1",
        "llm_model": "claude-sonnet-4-6",
        "llm_api_key": "sk-test",
        "contact_email": "test@example.com",
        "oversight_preference": "discretion",
        "auth": {"jwt_secret": jwt_secret},
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


def test_serve_startup_runs_migrations(tmp_path, monkeypatch):
    """App startup runs migrations and /health returns ok."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "")
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    assert (tmp_path / "agency.db").exists()


def test_serve_stores_jwt_secret_in_app_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _write_minimal_config(tmp_path, jwt_secret="mysecret")
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        assert app.state.jwt_secret == "mysecret"


def test_serve_uses_env_var_over_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENCY_JWT_SECRET", "env-secret")
    _write_minimal_config(tmp_path, jwt_secret="toml-secret")
    from agency.api.app import create_app
    app = create_app()
    with TestClient(app) as c:
        assert app.state.jwt_secret == "env-secret"
