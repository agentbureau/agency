import json
import os
import sqlite3
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from agency.cli.init import init_command


def _make_state_dir(tmp_path):
    state = tmp_path / ".agency"
    state.mkdir()
    (state / "keys").mkdir()
    return str(state)


def test_init_phase1_runs_without_error(tmp_path, monkeypatch):
    """Phase 1 completes with minimal input (API backend, not claude-code)."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    inputs = "\n".join([
        "",           # press enter to begin
        "2",          # select API backend
        "claude-sonnet-4-6",
        "sk-test-key",
        "test@example.com",
        "",           # default timeout
        "1",          # discretion
        "n",          # no smtp
        "n",          # no MCP registration
        "n",          # don't continue to phase 2
        "",
    ])
    result = runner.invoke(init_command, input=inputs)
    assert os.path.exists(os.path.join(state_dir, "agency.toml")), result.output


def test_init_creates_keypair(tmp_path, monkeypatch):
    """Phase 1 Step 1.1 creates Ed25519 keypair PEM files."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    inputs = "\n".join(["", "2", "claude-sonnet-4-6", "sk-key", "test@example.com",
                        "", "1", "n", "n", "n", ""])
    runner.invoke(init_command, input=inputs)
    assert os.path.exists(os.path.join(state_dir, "keys", "agency.ed25519.pem"))
    assert os.path.exists(os.path.join(state_dir, "keys", "agency.ed25519.pub.pem"))


def test_init_skips_completed_steps_on_rerun(tmp_path, monkeypatch):
    """Running agency init twice skips already-completed Phase 1 steps."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    inputs = "\n".join(["", "2", "claude-sonnet-4-6", "sk-key", "test@example.com",
                        "", "1", "n", "n", "n", ""])
    runner.invoke(init_command, input=inputs)
    # Second run — should detect phase 1 complete
    result2 = runner.invoke(init_command, input="n\n")
    assert "already configured" in result2.output.lower() or "skipping" in result2.output.lower() or "resuming" in result2.output.lower()


def test_init_mcp_registration_writes_absolute_token_path(tmp_path, monkeypatch):
    """AGENCY_TOKEN_FILE must be absolute, no ~ literal."""
    from agency.cli.init import _merge_mcp_registration
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_json = str(tmp_path / ".claude.json")
    with patch("agency.cli.init._resolve_agency_binary", return_value="/usr/local/bin/agency"):
        _merge_mcp_registration(claude_json)
    with open(claude_json) as f:
        data = json.load(f)
    token_path = data["mcpServers"]["agency"]["env"]["AGENCY_TOKEN_FILE"]
    assert token_path.startswith("/")
    assert "~" not in token_path


def test_init_mcp_registration_writes_absolute_binary_path(tmp_path, monkeypatch):
    """MCP registration writes an absolute path for the agency command, not bare 'agency'."""
    from agency.cli.init import _merge_mcp_registration
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_json = str(tmp_path / ".claude.json")
    with patch("agency.cli.init._resolve_agency_binary", return_value="/home/user/.local/bin/agency"):
        _merge_mcp_registration(claude_json)
    with open(claude_json) as f:
        data = json.load(f)
    command = data["mcpServers"]["agency"]["command"]
    assert command == "/home/user/.local/bin/agency"
    assert command.startswith("/")


def test_init_mcp_registration_aborts_if_binary_not_found(tmp_path, monkeypatch, capsys):
    """MCP registration aborts with actionable error when agency binary cannot be found."""
    from agency.cli.init import _merge_mcp_registration
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_json = str(tmp_path / ".claude.json")
    with patch("agency.cli.init._resolve_agency_binary", return_value=None):
        _merge_mcp_registration(claude_json)
    assert not os.path.exists(claude_json)


def test_resolve_agency_binary_uses_which(monkeypatch):
    """_resolve_agency_binary prefers shutil.which result."""
    from agency.cli.init import _resolve_agency_binary
    with patch("agency.cli.init._shutil.which", return_value="/opt/bin/agency"):
        result = _resolve_agency_binary()
    assert result is not None
    assert "/opt/bin/agency" in result or "agency" in result


def test_resolve_agency_binary_fallback_pipx(tmp_path, monkeypatch):
    """_resolve_agency_binary falls back to ~/.local/bin/agency."""
    from agency.cli.init import _resolve_agency_binary
    monkeypatch.setenv("HOME", str(tmp_path))
    pipx_bin = tmp_path / ".local" / "bin"
    pipx_bin.mkdir(parents=True)
    agency_bin = pipx_bin / "agency"
    agency_bin.write_text("#!/bin/sh\n")
    agency_bin.chmod(0o755)
    with patch("agency.cli.init._shutil.which", return_value=None):
        result = _resolve_agency_binary()
    assert result is not None
    assert "agency" in result


def test_welcome_banner_contains_pipx_preamble():
    """Welcome banner includes pipx install recommendation."""
    from agency.cli.init import WELCOME_BANNER
    assert "pipx install agency-engine" in WELCOME_BANNER
    assert "command not found" in WELCOME_BANNER


def test_field_explainers_has_required_keys():
    """FIELD_EXPLAINERS dict contains all required field explainers."""
    from agency.cli.init import FIELD_EXPLAINERS
    assert "contact_email" in FIELD_EXPLAINERS
    assert "oversight_preference" in FIELD_EXPLAINERS
    assert "attribution" in FIELD_EXPLAINERS


def test_init_phase1_shows_field_explainers(tmp_path, monkeypatch):
    """Phase 1 output contains field explainer arrows."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    inputs = "\n".join([
        "",           # press enter to begin
        "2",          # select API backend
        "claude-sonnet-4-6",
        "sk-test-key",
        "test@example.com",
        "",           # default timeout
        "1",          # discretion
        "n",          # no smtp
        "n",          # no MCP registration
        "n",          # don't continue to phase 2
        "",
    ])
    result = runner.invoke(init_command, input=inputs)
    from agency.cli.init import FIELD_EXPLAINERS
    # helper() indents each line by 4 spaces, so check first line of each explainer
    for key in ("contact_email", "oversight_preference", "attribution"):
        first_line = FIELD_EXPLAINERS[key].splitlines()[0]
        assert first_line in result.output, f"Missing explainer for {key}"


def test_poll_health_uses_half_second_interval():
    """_poll_health polls every 0.5s."""
    from agency.cli.init import _poll_health
    import httpx
    sleep_calls = []
    time_seq = [0.0] + [i * 0.5 for i in range(31)]
    time_iter = iter(time_seq)
    with patch("time.time", side_effect=lambda: next(time_iter)):
        with patch("time.sleep", side_effect=lambda d: sleep_calls.append(d)):
            with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
                result = _poll_health("http://localhost:8000", timeout_secs=15, interval=0.5)
    assert result is False
    assert all(d == 0.5 for d in sleep_calls)
    assert len(sleep_calls) == 30


def test_step_create_tokens_recovery_when_file_missing(tmp_path, monkeypatch):
    """Recovery: DB row exists but token file missing -> revoke and recreate."""
    from agency.db.migrations import run_migrations
    from agency.db.tokens import insert_token
    from agency.cli.init import _step_create_integration_tokens
    monkeypatch.setenv("HOME", str(tmp_path))
    state_dir = str(tmp_path / "state")
    os.makedirs(os.path.join(state_dir, "keys"))
    db_path = os.path.join(state_dir, "agency.db")
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    insert_token(conn, jti="old-jti-mcp", client_id="mcp", expires_at=None)
    conn.commit()
    conn.close()
    toml_path = os.path.join(state_dir, "agency.toml")
    with open(toml_path, "w") as f:
        f.write('instance_id = "inst-1"\n[server]\nhost = "127.0.0.1"\nport = 8000\n')
    mcp_token_path = os.path.join(str(tmp_path), ".agency-mcp-token")
    assert not os.path.exists(mcp_token_path)
    with patch("agency.cli.init.load_private_key", return_value=MagicMock()):
        with patch("agency.cli.init.create_jwt", return_value="fresh-jwt-token"):
            skipped, failed = [], []
            _step_create_integration_tokens(db_path, state_dir, toml_path, skipped, failed)
    conn = sqlite3.connect(db_path)
    old_row = conn.execute("SELECT revoked FROM issued_tokens WHERE jti = 'old-jti-mcp'").fetchone()
    conn.close()
    assert old_row is not None and old_row[0] == 1
    assert not failed


def test_init_non_interactive_with_all_flags(tmp_path, monkeypatch):
    """agency init with all flags completes without any interactive prompts."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    with patch("agency.cli.init._run_phase2"):
        result = runner.invoke(init_command, [
            "--backend", "api",
            "--model", "claude-sonnet-4-6",
            "--endpoint", "https://api.anthropic.com/v1",
            "--api-key", "sk-test",
            "--email", "test@example.com",
            "--timeout", "900",
            "--oversight", "review",
            "--attribution", "off",
            "--skip-primitives",
            "--no-register-mcp",
        ])
    # No input provided — if it prompted, CliRunner would fail or hang
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    # Verify config was written
    import tomllib as _tomllib
    toml_path = os.path.join(state_dir, "agency.toml")
    assert os.path.exists(toml_path)
    with open(toml_path, "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg["llm"]["backend"] == "api"
    assert cfg["llm"]["api_key"] == "sk-test"
    assert cfg["notifications"]["contact_email"] == "test@example.com"
    assert cfg["notifications"]["error_notification_timeout"] == 900
    assert cfg["notifications"]["oversight_preference"] == "review"
    assert cfg["output"]["attribution"] is False


def test_init_non_interactive_partial_flags(tmp_path, monkeypatch):
    """agency init with partial flags uses provided values without prompting for them."""
    state_dir = _make_state_dir(tmp_path)
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    with patch("agency.cli.init._run_phase2"):
        result = runner.invoke(init_command, [
            "--backend", "claude-code",
            "--email", "partial@example.com",
            "--skip-primitives",
            "--no-register-mcp",
        ])
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    import tomllib as _tomllib
    toml_path = os.path.join(state_dir, "agency.toml")
    with open(toml_path, "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg["notifications"]["contact_email"] == "partial@example.com"
    # Default values should still be applied
    assert cfg["notifications"]["oversight_preference"] == "discretion"
    assert cfg["output"]["attribution"] is True
