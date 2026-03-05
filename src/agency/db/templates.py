import sqlite3
from agency.utils.ids import new_template_id
from agency.utils.hashing import content_hash


def insert_template(
    conn: sqlite3.Connection,
    template_type: str,
    content: str,
    instance_id: str,
    client_id: str | None = None,
    project_id: str | None = None,
) -> str:
    tid = new_template_id(template_type)
    hash_ = content_hash(content)
    conn.execute(
        """INSERT INTO templates
           (id, template_type, content, content_hash, instance_id, client_id, project_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tid, template_type, content, hash_, instance_id, client_id, project_id),
    )
    conn.commit()
    return tid


def get_template(conn: sqlite3.Connection, template_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM templates WHERE id = ?", (template_id,)
    ).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM templates LIMIT 0").description]
    return dict(zip(cols, row))


def list_templates(
    conn: sqlite3.Connection,
    template_type: str | None = None,
    instance_id: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM templates WHERE 1=1"
    params: list = []
    if template_type:
        query += " AND template_type = ?"
        params.append(template_type)
    if instance_id:
        query += " AND instance_id = ?"
        params.append(instance_id)
    rows = conn.execute(query, params).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM templates LIMIT 0").description]
    return [dict(zip(cols, row)) for row in rows]
