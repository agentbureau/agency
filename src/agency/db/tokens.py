import sqlite3
from datetime import datetime
from typing import Optional


def insert_token(
    conn: sqlite3.Connection,
    jti: str,
    client_id: str,
    expires_at: Optional[str],
) -> None:
    """Insert a new token into the issued_tokens table.

    Args:
        conn: SQLite connection
        jti: JWT ID (unique identifier)
        client_id: Client ID associated with the token
        expires_at: ISO 8601 expiration timestamp (or None for no expiration)
    """
    conn.execute(
        "INSERT INTO issued_tokens (jti, client_id, expires_at) VALUES (?, ?, ?)",
        (jti, client_id, expires_at),
    )
    conn.commit()


def get_token(conn: sqlite3.Connection, jti: str) -> Optional[dict]:
    """Retrieve a token by JTI.

    Args:
        conn: SQLite connection
        jti: JWT ID to look up

    Returns:
        Dictionary with token data, or None if not found.
        Uses cursor.description for column names (no row_factory).
    """
    cursor = conn.execute(
        "SELECT jti, client_id, created_at, expires_at, revoked, revoked_at FROM issued_tokens WHERE jti = ?",
        (jti,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, row))


def list_tokens(conn: sqlite3.Connection) -> list[dict]:
    """List all tokens, ordered by most recent first.

    Args:
        conn: SQLite connection

    Returns:
        List of dictionaries, ordered by created_at DESC.
        Uses cursor.description for column names (no row_factory).
    """
    cursor = conn.execute(
        "SELECT jti, client_id, created_at, expires_at, revoked, revoked_at FROM issued_tokens ORDER BY created_at DESC"
    )
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def revoke_tokens_by_client_id(conn: sqlite3.Connection, client_id: str) -> int:
    """Revoke all tokens for a given client.

    Args:
        conn: SQLite connection
        client_id: Client ID whose tokens should be revoked

    Returns:
        Number of tokens revoked.
    """
    # First, count how many tokens will be revoked
    cursor = conn.execute(
        "SELECT COUNT(*) FROM issued_tokens WHERE client_id = ? AND revoked = 0",
        (client_id,),
    )
    count = cursor.fetchone()[0]

    # Revoke all non-revoked tokens for this client
    conn.execute(
        "UPDATE issued_tokens SET revoked = 1, revoked_at = ? WHERE client_id = ? AND revoked = 0",
        (datetime.now().isoformat(), client_id),
    )
    conn.commit()

    return count


def token_table_exists(conn: sqlite3.Connection) -> bool:
    """Check if the issued_tokens table exists.

    Args:
        conn: SQLite connection

    Returns:
        True if the table exists, False otherwise.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='issued_tokens'"
    )
    return cursor.fetchone() is not None
