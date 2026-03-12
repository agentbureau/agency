import sqlite3
import os
import pytest
from click.testing import CliRunner
from agency.auth.keypair import generate_keypair, load_private_key
from agency.db.migrations import run_migrations
from agency.db.tokens import get_token, list_tokens, insert_token
from agency.cli.token import token_group


@pytest.fixture
def setup(tmp_path):
    db_path = str(tmp_path / "agency.db")
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    conn.close()
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    priv = str(keys_dir / "agency.ed25519.pem")
    pub = str(keys_dir / "agency.ed25519.pub.pem")
    generate_keypair(priv, pub)
    return CliRunner(), db_path, priv, str(tmp_path)


def test_token_create_writes_to_issued_tokens(setup, monkeypatch):
    runner, db_path, priv_path, state_dir = setup
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    with open(os.path.join(state_dir, "agency.toml"), "w") as f:
        f.write('[server]\nhost = "127.0.0.1"\nport = 8000\n')
        f.write('instance_id = "inst-test-1"\n')
    result = runner.invoke(token_group, ["create", "--client-id", "test-client"])
    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    tokens = list_tokens(conn)
    assert len(tokens) == 1
    assert tokens[0]["client_id"] == "test-client"
    assert tokens[0]["revoked"] == 0


def test_token_list_shows_tokens(setup, monkeypatch):
    runner, db_path, priv_path, state_dir = setup
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    conn = sqlite3.connect(db_path)
    insert_token(conn, "jti-abc123de", "mcp", None)
    conn.close()
    result = runner.invoke(token_group, ["list"])
    assert result.exit_code == 0
    assert "mcp" in result.output
    assert "jti-abc1" in result.output  # first 8 chars


def test_token_revoke_requires_confirmation(setup, monkeypatch):
    runner, db_path, priv_path, state_dir = setup
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    conn = sqlite3.connect(db_path)
    insert_token(conn, "jti-1", "mcp", None)
    conn.close()
    # Wrong confirmation
    result = runner.invoke(token_group, ["revoke", "--client-id", "mcp"], input="no\n")
    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    assert get_token(conn, "jti-1")["revoked"] == 0
    # Correct confirmation
    result = runner.invoke(token_group, ["revoke", "--client-id", "mcp"],
                           input="yes, cancel every token on this instance\n")
    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    assert get_token(conn, "jti-1")["revoked"] == 1


def test_token_create_fails_without_database(monkeypatch, tmp_path):
    fresh_state = tmp_path / "fresh_state"
    fresh_state.mkdir()
    keys_dir = fresh_state / "keys"
    keys_dir.mkdir()
    generate_keypair(str(keys_dir / "agency.ed25519.pem"), str(keys_dir / "agency.ed25519.pub.pem"))
    sqlite3.connect(str(fresh_state / "agency.db")).close()
    with open(str(fresh_state / "agency.toml"), "w") as f:
        f.write('instance_id = "inst-1"\n[server]\nhost = "127.0.0.1"\nport = 8000\n')
    monkeypatch.setenv("AGENCY_STATE_DIR", str(fresh_state))
    runner = CliRunner()
    result = runner.invoke(token_group, ["create", "--client-id", "test"])
    assert result.exit_code != 0 or "database not initialised" in result.output.lower()
    assert "agency serve" in result.output


def test_token_create_with_expires_in(setup, monkeypatch):
    import jwt as pyjwt
    runner, db_path, priv_path, state_dir = setup
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    with open(os.path.join(state_dir, "agency.toml"), "w") as f:
        f.write('[server]\nhost = "127.0.0.1"\nport = 8000\ninstance_id = "inst-test-1"\n')
    result = runner.invoke(token_group, ["create", "--client-id", "test-client", "--expires-in", "3600"])
    assert result.exit_code == 0
    token_str = result.output.strip()
    payload = pyjwt.decode(token_str, options={"verify_signature": False})
    assert "exp" in payload
    assert payload["exp"] - payload["iat"] == 3600
    conn = sqlite3.connect(db_path)
    tokens = list_tokens(conn)
    assert tokens[0]["expires_at"] is not None


def test_token_revoke_prints_cancellation_message(setup, monkeypatch):
    runner, db_path, priv_path, state_dir = setup
    monkeypatch.setenv("AGENCY_STATE_DIR", state_dir)
    conn = sqlite3.connect(db_path)
    insert_token(conn, "jti-x", "mcp", None)
    conn.close()
    result = runner.invoke(token_group, ["revoke", "--client-id", "mcp"], input="nope\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output or "No tokens were revoked" in result.output
