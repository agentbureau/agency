"""
Evolver: two mutation strategies for generating agent variants.

Task 25: random_perturbation — swap role components with similar ones from store
Task 26: llm_variation — use LLM to suggest a modified role component description
Task 27: select_best_variant — run N variants, pick highest-scored
"""
import json
import random
import sqlite3
from agency.db.primitives import find_similar, insert_primitive
from agency.db.compositions import upsert_agent, get_agent
from agency.engine.assigner import assign_agent
from agency.utils.hashing import content_hash


# ---------------------------------------------------------------------------
# Task 25: Random perturbation mutation
# ---------------------------------------------------------------------------

def random_perturbation(
    db: sqlite3.Connection,
    agent_id: str,
    instance_id: str,
    n_variants: int = 3,
) -> list[str]:
    """
    Produce n_variants new agent IDs by randomly swapping one role component
    with a semantically similar alternative from the store.

    Returns list of variant agent_ids (may include original if no alternatives exist).
    """
    agent = get_agent(db, agent_id)
    if not agent:
        return [agent_id] * n_variants

    role_ids: list[str] = json.loads(agent["role_component_ids"] or "[]")
    variants = []

    for _ in range(n_variants):
        if not role_ids:
            variants.append(agent_id)
            continue

        swap_idx = random.randrange(len(role_ids))
        swap_id = role_ids[swap_idx]

        # Get description of the component being swapped
        row = db.execute(
            "SELECT description FROM role_components WHERE id = ?", (swap_id,)
        ).fetchone()
        if not row:
            variants.append(agent_id)
            continue

        desc = row[0]
        # Find similar alternatives (exclude the current one)
        candidates = [
            r for r in find_similar(db, "role_components", desc, limit=5)
            if r["id"] != swap_id
        ]
        if not candidates:
            variants.append(agent_id)
            continue

        replacement_id = candidates[0]["id"]
        new_role_ids = role_ids[:swap_idx] + [replacement_id] + role_ids[swap_idx + 1:]

        variant_id = upsert_agent(
            db,
            role_component_ids=new_role_ids,
            desired_outcome_id=agent.get("desired_outcome_id"),
            trade_off_config_id=agent.get("trade_off_config_id"),
            instance_id=instance_id,
        )
        variants.append(variant_id)

    return variants


# ---------------------------------------------------------------------------
# Task 26: LLM-prompted variation mutation
# ---------------------------------------------------------------------------

async def llm_variation(
    db: sqlite3.Connection,
    agent_id: str,
    task_description: str,
    instance_id: str,
    llm_client,
) -> str:
    """
    Ask the LLM to suggest an improved role component for this task context,
    insert it into the store, compose a new agent, and return its ID.
    """
    agent = get_agent(db, agent_id)
    if not agent:
        return agent_id

    role_ids: list[str] = json.loads(agent["role_component_ids"] or "[]")
    if not role_ids:
        return agent_id

    # Fetch current role descriptions
    role_descs = []
    for rid in role_ids:
        row = db.execute(
            "SELECT description FROM role_components WHERE id = ?", (rid,)
        ).fetchone()
        if row:
            role_descs.append(row[0])

    prompt = (
        f"Task: {task_description}\n\n"
        f"Current role components:\n" +
        "\n".join(f"- {d}" for d in role_descs) +
        "\n\nSuggest ONE improved role component description (one sentence, no preamble):"
    )

    new_desc = await llm_client.complete(prompt)
    new_desc = new_desc.strip()

    # Check if this description already exists
    existing = find_similar(db, "role_components", new_desc, limit=1)
    if existing and existing[0]["similarity"] > 0.97:
        new_rc_id = existing[0]["id"]
    else:
        new_rc_id = insert_primitive(
            db, "role_components", description=new_desc, instance_id=instance_id
        )

    new_role_ids = role_ids[:-1] + [new_rc_id]  # replace last component

    variant_id = upsert_agent(
        db,
        role_component_ids=new_role_ids,
        desired_outcome_id=agent.get("desired_outcome_id"),
        trade_off_config_id=agent.get("trade_off_config_id"),
        instance_id=instance_id,
    )
    return variant_id


# ---------------------------------------------------------------------------
# Task 27: Select best variant
# ---------------------------------------------------------------------------

def select_best_variant(
    variant_scores: list[tuple[str, float]],
) -> str:
    """
    Given [(agent_id, score), ...], return the agent_id with the highest score.
    Falls back to first entry if all scores are equal or list is empty.
    """
    if not variant_scores:
        raise ValueError("No variants to select from")
    return max(variant_scores, key=lambda x: x[1])[0]
