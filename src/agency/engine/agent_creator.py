"""
Task 28: Agent creator — adjacent search mode.

Searches for primitives adjacent (semantically similar) to an existing agent's
components, then composes a new agent from the best adjacent set.
"""
import json
import sqlite3
from agency.db.primitives import find_similar
from agency.db.compositions import upsert_agent, get_agent


def create_adjacent_agent(
    db: sqlite3.Connection,
    source_agent_id: str,
    instance_id: str,
    similarity_threshold: float = 0.5,
) -> str | None:
    """
    Find role components adjacent to the source agent's components,
    compose and return a new agent ID.

    Returns None if no sufficiently different adjacent agents can be formed.
    """
    agent = get_agent(db, source_agent_id)
    if not agent:
        return None

    role_ids: list[str] = json.loads(agent["role_component_ids"] or "[]")
    if not role_ids:
        return None

    # For each existing role component, find the next-best alternative
    adjacent_ids = []
    for rid in role_ids:
        row = db.execute(
            "SELECT description FROM role_components WHERE id = ?", (rid,)
        ).fetchone()
        if not row:
            adjacent_ids.append(rid)
            continue

        desc = row[0]
        candidates = [
            r for r in find_similar(db, "role_components", desc, limit=5)
            if r["id"] != rid and r["similarity"] >= similarity_threshold
        ]
        if candidates:
            adjacent_ids.append(candidates[0]["id"])
        else:
            adjacent_ids.append(rid)  # keep original if no adjacent found

    # If adjacent set is identical to source, no new agent
    if sorted(adjacent_ids) == sorted(role_ids):
        return None

    return upsert_agent(
        db,
        role_component_ids=adjacent_ids,
        desired_outcome_id=agent.get("desired_outcome_id"),
        trade_off_config_id=agent.get("trade_off_config_id"),
        instance_id=instance_id,
    )
