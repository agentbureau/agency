import sqlite3
from agency.utils.ids import new_uuid
from agency.utils.hashing import content_hash


def enqueue_evaluation(
    conn: sqlite3.Connection,
    evaluator_data: str,
    task_id: str,
    destination: str = "agency_instance",
) -> str:
    eid = new_uuid()
    hash_ = content_hash(evaluator_data)
    conn.execute(
        """INSERT INTO pending_evaluations
           (id, task_id, evaluator_data, destination, content_hash)
           VALUES (?, ?, ?, ?, ?)""",
        (eid, task_id, evaluator_data, destination, hash_),
    )
    conn.commit()
    return eid


def get_pending_evaluations(
    conn: sqlite3.Connection,
    destination: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM pending_evaluations WHERE confirmed = 0"
    params: list = []
    if destination:
        query += " AND destination = ?"
        params.append(destination)
    rows = conn.execute(query, params).fetchall()
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM pending_evaluations LIMIT 0"
    ).description]
    return [dict(zip(cols, row)) for row in rows]


def confirm_evaluation(conn: sqlite3.Connection, evaluation_id: str) -> None:
    conn.execute(
        """UPDATE pending_evaluations
           SET confirmed = 1, confirmed_at = datetime('now')
           WHERE id = ?""",
        (evaluation_id,),
    )
    conn.commit()


def ping_evaluation(conn: sqlite3.Connection, evaluation_id: str) -> None:
    conn.execute(
        """UPDATE pending_evaluations
           SET last_ping_at = datetime('now')
           WHERE id = ?""",
        (evaluation_id,),
    )
    conn.commit()
