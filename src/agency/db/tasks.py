import sqlite3
from agency.utils.ids import new_uuid


def create_task(
    conn: sqlite3.Connection,
    description: str,
    external_id: str | None = None,
    project_id: str | None = None,
    output_format: str | None = None,
    output_structure: str | None = None,
    clarification_behaviour: str | None = None,
    client_id: str | None = None,
) -> str:
    tid = new_uuid()
    conn.execute(
        """INSERT INTO tasks
           (id, external_id, project_id, description, output_format,
            output_structure, clarification_behaviour, client_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tid, external_id, project_id, description, output_format,
         output_structure, clarification_behaviour, client_id),
    )
    conn.commit()
    return tid


def get_task(conn: sqlite3.Connection, task_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM tasks LIMIT 0").description]
    return dict(zip(cols, row))


def set_task_composition(conn: sqlite3.Connection, task_id: str, composition_id: str) -> None:
    conn.execute(
        "UPDATE tasks SET agent_composition_id = ? WHERE id = ?",
        (composition_id, task_id),
    )
    conn.commit()
