import json
import sqlite3
from agency.utils.ids import new_uuid
from agency.utils.hashing import content_hash
from agency.utils.embedding import embed, cosine_similarity
from agency.engine.permissions import DEFAULT_PERMISSION

PRIMITIVE_TABLES = ("role_components", "desired_outcomes", "trade_off_configs")


def insert_primitive(
    conn: sqlite3.Connection,
    table: str,
    description: str,
    instance_id: str,
    client_id: str | None = None,
    project_id: str | None = None,
) -> str:
    assert table in PRIMITIVE_TABLES
    pid = new_uuid()
    hash_ = content_hash(description)
    vec = embed(description)
    conn.execute(
        f"""INSERT INTO {table}
            (id, description, content_hash, instance_id, client_id, project_id, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pid, description, hash_, instance_id, client_id, project_id, json.dumps(vec)),
    )
    conn.commit()
    return pid


def get_primitive(conn: sqlite3.Connection, table: str, pid: str) -> dict | None:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (pid,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    return dict(zip(cols, row))


def find_similar(
    conn: sqlite3.Connection,
    table: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Brute-force cosine similarity search."""
    query_vec = embed(query)
    rows = conn.execute(f"SELECT id, description, embedding FROM {table}").fetchall()
    scored = []
    for row in rows:
        pid, desc, emb_json = row
        if emb_json:
            vec = json.loads(emb_json)
            scored.append((cosine_similarity(query_vec, vec), pid, desc))
    scored.sort(reverse=True)
    return [{"id": pid, "description": desc, "score": score}
            for score, pid, desc in scored[:limit]]
