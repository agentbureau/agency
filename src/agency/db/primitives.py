import json
import sqlite3
from agency.utils.ids import new_uuid
from agency.utils.hashing import content_hash
from agency.utils.embedding import embed, cosine_similarity
from agency.engine.permissions import DEFAULT_PERMISSION

PRIMITIVE_TABLES = ("role_components", "desired_outcomes", "trade_off_configs")


AGENTBUREAU_INSTANCE_ID = "00000000-0000-7000-8000-000000000001"

TYPE_TO_TABLE = {
    "role_component": "role_components",
    "desired_outcome": "desired_outcomes",
    "trade_off_config": "trade_off_configs",
}

_VALID_SCOPES = frozenset({
    "task", "meta:assigner", "meta:evaluator", "meta:evolver", "meta:agent_creator"
})


def insert_primitive(
    conn: sqlite3.Connection,
    table: str,
    description: str,
    instance_id: str,
    name: str = "",
    client_id: str | None = None,
    project_id: str | None = None,
    quality: int = 100,
    domain_specificity: int = 0,
    domain: str = "[]",
    origin_instance_id: str = AGENTBUREAU_INSTANCE_ID,
    parent_content_hash: str | None = None,
    scope: str = "task",
) -> str:
    assert table in PRIMITIVE_TABLES
    if scope not in _VALID_SCOPES:
        raise ValueError(
            f"Invalid scope '{scope}'. "
            f"Allowed values: {', '.join(sorted(_VALID_SCOPES))}"
        )
    pid = new_uuid()
    hash_ = content_hash(description)
    vec = embed(description)
    if not name:
        name = description[:80]
    conn.execute(
        f"""INSERT INTO {table}
            (id, name, description, content_hash, quality, domain_specificity, domain,
             origin_instance_id, parent_content_hash,
             instance_id, client_id, project_id, embedding, scope)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, name, description, hash_, quality, domain_specificity, domain,
         origin_instance_id, parent_content_hash,
         instance_id, client_id, project_id, json.dumps(vec), scope),
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
    scope: str | None = "task",
) -> list[dict]:
    """Brute-force cosine similarity search, filtered by scope."""
    query_vec = embed(query)
    if scope is not None:
        rows = conn.execute(
            f"SELECT id, name, description, embedding FROM {table} WHERE scope = ?",
            (scope,)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id, name, description, embedding FROM {table}"
        ).fetchall()
    scored = []
    for row in rows:
        pid, name, desc, emb_json = row
        if emb_json:
            vec = json.loads(emb_json)
            scored.append((cosine_similarity(query_vec, vec), pid, name, desc, vec))
    scored.sort(reverse=True)
    return [{"id": pid, "name": name, "description": desc, "similarity": sim, "embedding": vec}
            for sim, pid, name, desc, vec in scored[:limit]]
