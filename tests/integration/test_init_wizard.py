import pytest
from click.testing import CliRunner
from agency.cli.init import init_command
from agency.config.toml import load_config


def _wizard_input_api() -> str:
    """Input for API backend through the new two-phase wizard (Phase 1 only)."""
    return "\n".join([
        "",                     # press enter to begin
        "2",                    # select API backend
        "claude-sonnet-4-6",    # model
        "sk-test-key",          # api key
        "test@example.com",     # contact email
        "",                     # default timeout (1800)
        "1",                    # discretion
        "n",                    # no smtp
        "n",                    # no MCP registration
        "n",                    # don't continue to phase 2
    ]) + "\n"


@pytest.fixture
def runner():
    return CliRunner()


def test_init_creates_config_and_keypair(tmp_path, runner):
    result = runner.invoke(init_command, catch_exceptions=False,
                           input=_wizard_input_api(),
                           env={"AGENCY_STATE_DIR": str(tmp_path),
                                "HOME": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / "agency.toml").exists()
    assert (tmp_path / "keys" / "agency.ed25519.pem").exists()
    assert (tmp_path / "keys" / "agency.ed25519.pub.pem").exists()


def test_init_writes_llm_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_api(),
                  env={"AGENCY_STATE_DIR": str(tmp_path),
                       "HOME": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert "llm" in cfg
    assert cfg["llm"]["backend"] == "api"
    assert cfg["llm"]["model"] == "claude-sonnet-4-6"


def test_init_writes_server_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_api(),
                  env={"AGENCY_STATE_DIR": str(tmp_path),
                       "HOME": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["server"]["port"] == 8000


def test_init_writes_notifications_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_api(),
                  env={"AGENCY_STATE_DIR": str(tmp_path),
                       "HOME": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["notifications"]["contact_email"] == "test@example.com"
    assert cfg["notifications"]["oversight_preference"] == "discretion"


def test_init_no_jwt_secret_in_config(runner, tmp_path):
    """v1.2.0: jwt_secret must not appear in config (EdDSA keypair used instead)."""
    runner.invoke(init_command, input=_wizard_input_api(),
                  env={"AGENCY_STATE_DIR": str(tmp_path),
                       "HOME": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert "auth" not in cfg
    assert "jwt_secret" not in cfg
