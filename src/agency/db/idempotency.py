import sqlite3


def is_duplicate(conn: sqlite3.Connection, jwt_id: str, task_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM consumed_jwts WHERE jwt_id = ? AND task_id = ?",
        (jwt_id, task_id)
    ).fetchone()
    return row is not None


def record_jwt(conn: sqlite3.Connection, jwt_id: str, task_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO consumed_jwts (jwt_id, task_id) VALUES (?, ?)",
        (jwt_id, task_id)
    )
    conn.commit()
