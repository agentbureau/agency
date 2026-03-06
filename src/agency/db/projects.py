import sqlite3
from agency.utils.ids import new_uuid


def create_project(
    conn: sqlite3.Connection,
    name: str,
    client_id: str | None,
    description: str | None,
    admin_email: str | None,
) -> str:
    pid = new_uuid()
    conn.execute(
        """INSERT INTO projects (id, name, client_id, description, admin_email)
           VALUES (?, ?, ?, ?, ?)""",
        (pid, name, client_id, description, admin_email),
    )
    conn.commit()
    return pid


def get_project(conn: sqlite3.Connection, project_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM projects LIMIT 0").description]
    return dict(zip(cols, row))
