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


def _deduplicate_name(conn: sqlite3.Connection, table: str, name: str) -> str:
    """Append -N suffix if name already exists in table. Uses MAX to avoid collisions after deletions."""
    escaped_name = name.replace("%", "\\%").replace("_", "\\_")
    rows = conn.execute(
        f"SELECT name FROM {table} WHERE name = ? OR name LIKE ? ESCAPE '\\'",
        (name, f"{escaped_name}-%")
    ).fetchall()
    if not rows:
        return name
    max_suffix = 1
    for (existing_name,) in rows:
        if existing_name == name:
            continue
        suffix = existing_name[len(name) + 1:]  # after "name-"
        try:
            max_suffix = max(max_suffix, int(suffix))
        except ValueError:
            pass
    return f"{name}-{max_suffix + 1}" if rows else name


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
    parent_ids: str | None = None,
    generation: int = 0,
    created_by: str = "human",
    reframing_potential: float | None = None,
) -> str:
    assert table in PRIMITIVE_TABLES
    if not scope or scope not in _VALID_SCOPES:
        scope = "task"
    pid = new_uuid()
    hash_ = content_hash(description)
    vec = embed(description)
    if not name:
        name = description[:80]
    name = _deduplicate_name(conn, table, name)
    conn.execute(
        f"""INSERT INTO {table}
            (id, name, description, content_hash, quality, domain_specificity, domain,
             origin_instance_id, parent_content_hash,
             instance_id, client_id, project_id, embedding, scope,
             parent_ids, generation, created_by, reframing_potential)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, name, description, hash_, quality, domain_specificity, domain,
         origin_instance_id, parent_content_hash,
         instance_id, client_id, project_id, json.dumps(vec), scope,
         parent_ids, generation, created_by, reframing_potential),
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
    keyword_filter: list[str] | None = None,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Brute-force cosine similarity search, filtered by scope.

    keyword_filter: when provided, pre-filters to rows whose description
        contains at least one keyword (OR-ed). AND-ed with scope.
    exclude_ids: when provided, excludes rows with these IDs.
    """
    if keyword_filter and scope and scope.startswith("meta:"):
        raise ValueError("keyword_filter is not supported for metaprimitive scopes — "
                         "metaprimitive descriptions do not contain task-type keywords")

    query_vec = embed(query)

    # Build SQL dynamically
    conditions = []
    params: list = []

    if scope is not None:
        conditions.append("scope = ?")
        params.append(scope)

    if keyword_filter:
        kw_clauses = " OR ".join(["LOWER(description) LIKE ?" for _ in keyword_filter])
        conditions.append(f"({kw_clauses})")
        params.extend(f"%{kw}%" for kw in keyword_filter)

    if exclude_ids:
        placeholders = ", ".join("?" for _ in exclude_ids)
        conditions.append(f"id NOT IN ({placeholders})")
        params.extend(exclude_ids)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT id, name, description, embedding FROM {table}{where}"
    rows = conn.execute(sql, params).fetchall()

    scored = []
    for row in rows:
        pid, name, desc, emb_json = row
        if emb_json:
            vec = json.loads(emb_json)
            scored.append((cosine_similarity(query_vec, vec), pid, name, desc, vec))
    scored.sort(reverse=True)
    return [{"id": pid, "name": name, "description": desc, "similarity": sim, "embedding": vec}
            for sim, pid, name, desc, vec in scored[:limit]]
