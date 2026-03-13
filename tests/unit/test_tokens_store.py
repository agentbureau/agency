import sqlite3
import time
import pytest
from agency.db.migrations import run_migrations
from agency.db.tokens import insert_token, get_token, list_tokens, revoke_tokens_by_client_id, token_table_exists

@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "test.db"))
    run_migrations(c)
    return c

def test_insert_and_get_token(conn):
    insert_token(conn, jti="jti-1", client_id="mcp", expires_at=None)
    row = get_token(conn, "jti-1")
    assert row["jti"] == "jti-1"
    assert row["client_id"] == "mcp"
    assert row["revoked"] == 0
    assert row["expires_at"] is None

def test_insert_token_with_expiry(conn):
    insert_token(conn, jti="jti-2", client_id="sp", expires_at="2026-12-31T00:00:00")
    row = get_token(conn, "jti-2")
    assert row["expires_at"] == "2026-12-31T00:00:00"

def test_list_tokens_most_recent_first(conn):
    insert_token(conn, jti="jti-a", client_id="mcp", expires_at=None)
    time.sleep(1.1)  # Ensure different timestamps (datetime('now') has 1-second precision)
    insert_token(conn, jti="jti-b", client_id="mcp", expires_at=None)
    tokens = list_tokens(conn)
    assert tokens[0]["jti"] == "jti-b"
    assert tokens[1]["jti"] == "jti-a"

def test_revoke_tokens_by_client_id(conn):
    insert_token(conn, jti="jti-1", client_id="mcp", expires_at=None)
    insert_token(conn, jti="jti-2", client_id="mcp", expires_at=None)
    insert_token(conn, jti="jti-3", client_id="sp", expires_at=None)
    count = revoke_tokens_by_client_id(conn, "mcp")
    assert count == 2
    assert get_token(conn, "jti-1")["revoked"] == 1
    assert get_token(conn, "jti-2")["revoked"] == 1
    assert get_token(conn, "jti-3")["revoked"] == 0

def test_token_table_exists_true(conn):
    assert token_table_exists(conn) is True

def test_token_table_exists_false(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "empty.db"))
    assert token_table_exists(conn) is False
