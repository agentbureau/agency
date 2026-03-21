import os
from unittest.mock import patch
from click.testing import CliRunner
from agency.cli.setup import client_setup_command


def test_client_setup_requires_existing_config(tmp_path, monkeypatch):
    """agency client setup exits with error if agency.toml not found."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(client_setup_command)
    assert result.exit_code != 0
    assert "agency init" in result.output


def test_client_setup_shows_current_values(tmp_path, monkeypatch):
    """agency client setup displays current config values."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    toml_content = (
        'instance_id = "inst-1"\n'
        '[server]\nhost = "127.0.0.1"\nport = 8000\n'
        '[llm]\nbackend = "claude-code"\nmodel = "claude-sonnet-4-6"\n'
        '[notifications]\ncontact_email = "a@b.com"\n'
        'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
        '[output]\nattribution = true\n'
    )
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(toml_content)

    runner = CliRunner()
    result = runner.invoke(client_setup_command, input="\n" * 20)
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "a@b.com" in result.output
    assert "Settings updated" in result.output


_SETUP_TOML = (
    'instance_id = "test"\n'
    '[server]\nhost = "127.0.0.1"\nport = 8000\n'
    '[llm]\nbackend = "claude-code"\nmodel = "x"\nendpoint = ""\napi_key = ""\n'
    '[notifications]\ncontact_email = "a@b.com"\n'
    'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
    '[output]\nattribution = true\n'
)
# 13 prompts before rotate: backend, model, email, timeout, oversight,
# smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, attribution,
# server_host, server_port
_PROMPTS_BEFORE_ROTATE = "\n" * 13


def test_keypair_rotation_requires_exact_confirmation_string(tmp_path, monkeypatch):
    """Wrong confirmation string cancels keypair rotation."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "agency.ed25519.pem").write_bytes(b"fake-key")
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(_SETUP_TOML)

    runner = CliRunner()
    result = runner.invoke(
        client_setup_command,
        input=_PROMPTS_BEFORE_ROTATE + "y\nyes\n",
    )
    assert "Cancelled" in result.output or "Keypair unchanged" in result.output


def test_keypair_rotation_proceeds_with_exact_confirmation_string(tmp_path, monkeypatch):
    """Exact string 'yes, invalidate all tokens' triggers _rotate_keypair."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "agency.ed25519.pem").write_bytes(b"fake-key")
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(_SETUP_TOML)

    with patch("agency.cli.setup._rotate_keypair") as mock_rotate:
        runner = CliRunner()
        result = runner.invoke(
            client_setup_command,
            input=_PROMPTS_BEFORE_ROTATE + "y\nyes, invalidate all tokens\n",
        )
    mock_rotate.assert_called_once()
    assert "Cancelled" not in result.output


def test_client_setup_non_interactive_updates_only_provided_flags(tmp_path, monkeypatch):
    """agency client setup with flags updates only those settings, no prompts."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    toml_content = (
        'instance_id = "inst-1"\n'
        '[server]\nhost = "127.0.0.1"\nport = 8000\n'
        '[llm]\nbackend = "claude-code"\nmodel = "claude-sonnet-4-6"\nendpoint = ""\napi_key = ""\n'
        '[notifications]\ncontact_email = "old@example.com"\n'
        'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
        '[output]\nattribution = true\n'
    )
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(toml_content)

    runner = CliRunner()
    # Provide only --oversight and --email; no stdin input
    result = runner.invoke(client_setup_command, [
        "--oversight", "review",
        "--email", "new@example.com",
    ])
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "Settings updated" in result.output

    import tomllib as _tomllib
    with open(str(tmp_path / "agency.toml"), "rb") as f:
        cfg = _tomllib.load(f)
    # Updated values
    assert cfg["notifications"]["oversight_preference"] == "review"
    assert cfg["notifications"]["contact_email"] == "new@example.com"
    # Preserved values
    assert cfg["llm"]["backend"] == "claude-code"
    assert cfg["notifications"]["error_notification_timeout"] == 1800
    assert cfg["output"]["attribution"] is True
    assert cfg["server"]["host"] == "127.0.0.1"


def test_client_setup_non_interactive_all_flags(tmp_path, monkeypatch):
    """agency client setup with all flags completes without any prompts."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    toml_content = (
        'instance_id = "inst-1"\n'
        '[server]\nhost = "127.0.0.1"\nport = 8000\n'
        '[llm]\nbackend = "claude-code"\nmodel = "claude-sonnet-4-6"\nendpoint = ""\napi_key = ""\n'
        '[notifications]\ncontact_email = "old@example.com"\n'
        'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
        '[output]\nattribution = true\n'
    )
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(toml_content)

    runner = CliRunner()
    result = runner.invoke(client_setup_command, [
        "--backend", "api",
        "--model", "claude-opus-4-6",
        "--email", "all@example.com",
        "--timeout", "600",
        "--oversight", "review",
        "--attribution", "off",
        "--host", "0.0.0.0",
        "--port", "9000",
    ])
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "Settings updated" in result.output

    import tomllib as _tomllib
    with open(str(tmp_path / "agency.toml"), "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg["llm"]["backend"] == "api"
    assert cfg["llm"]["model"] == "claude-opus-4-6"
    assert cfg["notifications"]["contact_email"] == "all@example.com"
    assert cfg["notifications"]["error_notification_timeout"] == 600
    assert cfg["notifications"]["oversight_preference"] == "review"
    assert cfg["output"]["attribution"] is False
    assert cfg["server"]["host"] == "0.0.0.0"
    assert cfg["server"]["port"] == 9000


def test_client_setup_no_flags_enters_interactive_mode(tmp_path, monkeypatch):
    """Running agency client setup with no flags shows prompts (interactive mode)."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    toml_content = (
        'instance_id = "inst-1"\n'
        '[server]\nhost = "127.0.0.1"\nport = 8000\n'
        '[llm]\nbackend = "claude-code"\nmodel = "claude-sonnet-4-6"\nendpoint = ""\napi_key = ""\n'
        '[notifications]\ncontact_email = "a@b.com"\n'
        'oversight_preference = "discretion"\nerror_notification_timeout = 1800\n'
        '[output]\nattribution = true\n'
    )
    with open(str(tmp_path / "agency.toml"), "w") as f:
        f.write(toml_content)

    runner = CliRunner()
    result = runner.invoke(client_setup_command, input="\n" * 20)
    assert result.exit_code == 0
    assert "Client Setup" in result.output
    assert "Press enter" in result.output
