import json
import sqlite3
from agency.utils.ids import new_uuid
from agency.utils.hashing import content_hash


def upsert_agent(
    conn: sqlite3.Connection,
    role_component_ids: list[str],
    desired_outcome_id: str | None,
    trade_off_config_id: str | None,
    instance_id: str,
    client_id: str | None = None,
    project_id: str | None = None,
    template_id: str = "default",
) -> str:
    hash_ = content_hash(json.dumps(sorted(role_component_ids)))
    existing = conn.execute(
        "SELECT id FROM agents WHERE content_hash = ?", (hash_,)
    ).fetchone()
    if existing:
        return existing[0]
    aid = new_uuid()
    conn.execute(
        """INSERT INTO agents
           (id, role_component_ids, desired_outcome_id, trade_off_config_id,
            content_hash, instance_id, client_id, project_id, template_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, json.dumps(role_component_ids), desired_outcome_id,
         trade_off_config_id, hash_, instance_id, client_id, project_id,
         template_id),
    )
    conn.commit()
    return aid


def get_agent(conn: sqlite3.Connection, agent_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM agents LIMIT 0").description]
    return dict(zip(cols, row))


def list_agents(
    conn: sqlite3.Connection,
    instance_id: str | None = None,
    client_id: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM agents WHERE 1=1"
    params: list = []
    if instance_id:
        query += " AND instance_id = ?"
        params.append(instance_id)
    if client_id:
        query += " AND client_id = ?"
        params.append(client_id)
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    rows = conn.execute(query, params).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM agents LIMIT 0").description]
    return [dict(zip(cols, row)) for row in rows]
