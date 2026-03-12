import pytest
from click.testing import CliRunner
from agency.cli.init import init_command
from agency.config.toml import load_config


def _wizard_input_claude_code() -> str:
    """Input for claude-code backend (no endpoint/api_key prompts)."""
    return "\n".join([
        "claude-code",          # backend
        "claude-sonnet-4-6",    # model
        "test@example.com",     # contact email
        "discretion",           # oversight
        "1800",                 # error_notification_timeout
        "",                     # smtp host (skip)
        "127.0.0.1",            # server host
        "8000",                 # server port
    ]) + "\n"


def _wizard_input_api() -> str:
    """Input for api backend (with endpoint/api_key prompts)."""
    return "\n".join([
        "api",                              # backend
        "claude-sonnet-4-6",               # model
        "https://api.anthropic.com/v1",    # endpoint
        "sk-test-key",                     # api key
        "test@example.com",                # contact email
        "discretion",                      # oversight
        "1800",                            # error_notification_timeout
        "",                                # smtp host (skip)
        "127.0.0.1",                       # server host
        "8000",                            # server port
    ]) + "\n"


@pytest.fixture
def runner():
    return CliRunner()


def test_init_creates_config_and_keypair(tmp_path, runner):
    result = runner.invoke(init_command, catch_exceptions=False,
                           input=_wizard_input_claude_code(),
                           env={"AGENCY_STATE_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / "agency.toml").exists()
    assert (tmp_path / "keys" / "agency.ed25519.pem").exists()
    assert (tmp_path / "keys" / "agency.ed25519.pub.pem").exists()


def test_init_writes_llm_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_claude_code(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert "llm" in cfg
    assert cfg["llm"]["backend"] == "claude-code"
    assert cfg["llm"]["model"] == "claude-sonnet-4-6"


def test_init_writes_server_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_claude_code(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["server"]["port"] == 8000


def test_init_writes_notifications_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input_claude_code(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["notifications"]["contact_email"] == "test@example.com"
    assert cfg["notifications"]["oversight_preference"] == "discretion"


def test_init_no_jwt_secret_in_config(runner, tmp_path):
    """v1.2.0: jwt_secret must not appear in config (EdDSA keypair used instead)."""
    runner.invoke(init_command, input=_wizard_input_claude_code(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert "auth" not in cfg
    assert "jwt_secret" not in cfg
