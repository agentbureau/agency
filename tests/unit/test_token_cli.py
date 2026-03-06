import pytest
from click.testing import CliRunner
from agency.cli.token import token_group
from agency.config.toml import write_config
from agency.utils.ids import new_uuid


def _write_config_with_secret(tmp_path, secret: str) -> None:
    cfg = {
        "instance_id": new_uuid(),
        "llm_endpoint": "https://api.anthropic.com/v1",
        "llm_model": "claude-sonnet-4-6",
        "llm_api_key": "sk-test",
        "contact_email": "test@example.com",
        "oversight_preference": "discretion",
        "auth": {"jwt_secret": secret},
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


@pytest.fixture
def runner():
    return CliRunner()


def test_token_create_prints_jwt(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    _write_config_with_secret(tmp_path, "testsecret" * 7)
    result = runner.invoke(token_group, ["create", "--client-id", "superpowers"])
    assert result.exit_code == 0, result.output
    token = result.output.strip()
    assert len(token) > 20


def test_token_create_with_expiry(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    secret = "testsecret" * 7
    _write_config_with_secret(tmp_path, secret)
    result = runner.invoke(token_group, ["create", "--client-id", "workgraph",
                                          "--expires-in", "3600"])
    assert result.exit_code == 0, result.output
    import jwt as pyjwt
    payload = pyjwt.decode(result.output.strip(), secret, algorithms=["HS256"])
    assert "exp" in payload
