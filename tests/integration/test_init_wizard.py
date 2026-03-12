import pytest
from click.testing import CliRunner
from agency.cli.init import init_command
from agency.config.toml import load_config


def _wizard_input() -> str:
    return "\n".join([
        "https://api.anthropic.com/v1",  # endpoint
        "claude-sonnet-4-6",             # model
        "sk-test-key",                   # api key
        "test@example.com",              # contact email
        "discretion",                    # oversight
        "smtp.example.com",              # smtp host
        "587",                           # smtp port
        "user@example.com",              # smtp username
        "smtppassword",                  # smtp password
        "user@example.com",              # sender address
        "127.0.0.1",                     # server host
        "8000",                          # server port
    ]) + "\n"


@pytest.fixture
def runner():
    return CliRunner()


def test_init_creates_config_and_keypair(tmp_path, runner):
    result = runner.invoke(init_command, catch_exceptions=False,
                           input=_wizard_input(),
                           env={"AGENCY_STATE_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / "agency.toml").exists()
    assert (tmp_path / "keys" / "agency.pem").exists()
    assert (tmp_path / "keys" / "agency.pub.pem").exists()


def test_init_writes_jwt_secret(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert "auth" in cfg
    assert len(cfg["auth"]["jwt_secret"]) == 64  # secrets.token_hex(32)


def test_init_writes_server_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["server"]["port"] == 8000


def test_init_writes_email_section(runner, tmp_path):
    runner.invoke(init_command, input=_wizard_input(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg = load_config(tmp_path / "agency.toml")
    assert cfg["email"]["smtp_host"] == "smtp.example.com"


def test_init_does_not_overwrite_existing_jwt_secret(runner, tmp_path):
    # First run
    runner.invoke(init_command, input=_wizard_input(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg1 = load_config(tmp_path / "agency.toml")
    secret1 = cfg1["auth"]["jwt_secret"]
    # Second run
    runner.invoke(init_command, input=_wizard_input(),
                  env={"AGENCY_STATE_DIR": str(tmp_path)})
    cfg2 = load_config(tmp_path / "agency.toml")
    assert cfg2["auth"]["jwt_secret"] == secret1
