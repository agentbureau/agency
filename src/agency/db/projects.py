import sqlite3
from agency.utils.ids import new_uuid


def create_project(
    conn: sqlite3.Connection,
    name: str,
    client_id: str | None,
    description: str | None,
    admin_email: str | None,
    *,
    contact_email: str | None = None,
    oversight_preference: str | None = None,
    error_notification_timeout: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    attribution: int | None = None,
) -> str:
    pid = new_uuid()
    conn.execute(
        """INSERT INTO projects
           (id, name, client_id, description, admin_email,
            contact_email, oversight_preference, error_notification_timeout,
            llm_provider, llm_model, llm_api_key, attribution)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid, name, client_id, description, admin_email,
            contact_email, oversight_preference, error_notification_timeout,
            llm_provider, llm_model, llm_api_key, attribution,
        ),
    )
    conn.commit()
    return pid


def list_projects(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    if not rows:
        return []
    cols = [d[0] for d in conn.execute("SELECT * FROM projects LIMIT 0").description]
    return [dict(zip(cols, row)) for row in rows]


def get_project(conn: sqlite3.Connection, project_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM projects LIMIT 0").description]
    return dict(zip(cols, row))
