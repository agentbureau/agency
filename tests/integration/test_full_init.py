"""
Task 39: Full agency init integration test.
End-to-end: run agency init, verify config + keypair + DB initialized.
"""
import os
import sqlite3
import pytest
from click.testing import CliRunner
from agency.cli.init import init_command


def test_full_init_end_to_end(tmp_path):
    runner = CliRunner()
    result = runner.invoke(init_command, catch_exceptions=False, input="\n".join([
        "https://api.anthropic.com/v1",
        "claude-sonnet-4-6",
        "sk-ant-test",
        "admin@example.com",
        "discretion",
        "300",
        "n",
    ]) + "\n", env={"AGENCY_STATE_DIR": str(tmp_path)})

    assert result.exit_code == 0, result.output

    # Config written
    assert (tmp_path / "agency.toml").exists()
    from agency.config.toml import read_config
    cfg = read_config(tmp_path / "agency.toml")
    assert cfg["llm_endpoint"] == "https://api.anthropic.com/v1"
    assert cfg["contact_email"] == "admin@example.com"
    assert cfg["instance_id"]  # UUID generated

    # Keypair present
    assert (tmp_path / "keys" / "agency.ed25519").exists()
    assert (tmp_path / "keys" / "agency.ed25519.pub").exists()


def test_init_then_serve_initialises_db(tmp_path):
    """After init, starting the server should create and migrate the DB."""
    runner = CliRunner()
    runner.invoke(init_command, catch_exceptions=False, input="\n".join([
        "https://api.anthropic.com/v1",
        "claude-sonnet-4-6",
        "sk-ant-test",
        "admin@example.com",
        "discretion",
        "300",
        "n",
    ]) + "\n", env={"AGENCY_STATE_DIR": str(tmp_path)})

    os.environ["AGENCY_STATE_DIR"] = str(tmp_path)
    try:
        from fastapi.testclient import TestClient
        from agency.api.app import create_app
        app = create_app()
        with TestClient(app):
            pass
        db = sqlite3.connect(tmp_path / "agency.db")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "role_components" in tables
        assert "agents" in tables
    finally:
        del os.environ["AGENCY_STATE_DIR"]
