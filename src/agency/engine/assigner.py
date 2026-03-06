import json
import sqlite3
from agency.db.primitives import find_similar
from agency.db.compositions import upsert_agent
from agency.db.templates import list_templates
from agency.engine.renderer import render_agent, load_default_template
from agency.utils.hashing import content_hash
from agency.utils.ids import new_uuid
from agency.utils.errors import PrimitiveStoreEmpty


def assign_agent(db: sqlite3.Connection, task_id: str, task: dict) -> dict:
    """
    Find or compose the best agent for a task.

    Strategy:
    1. Search role_components for relevant primitives
    2. Search desired_outcomes and trade_off_configs
    3. Upsert agent composition (deduped by content hash)
    4. Render agent prompt using default template
    """
    task_description = task.get("task_description", "")
    instance_id = task.get("instance_id", "default")
    client_id = task.get("client_id")
    project_id = task.get("project_id")

    # Find relevant role components
    role_results = find_similar(db, "role_components", task_description, limit=3)
    if not role_results:
        raise PrimitiveStoreEmpty("No role components in primitive store")
    role_component_ids = [r["id"] for r in role_results]
    role_component_texts = [r["description"] for r in role_results]

    # Find best desired outcome
    outcome_results = find_similar(db, "desired_outcomes", task_description, limit=1)
    desired_outcome = outcome_results[0]["description"] if outcome_results else "Complete the task effectively"
    desired_outcome_id = outcome_results[0]["id"] if outcome_results else None

    # Find best trade-off config
    tradeoff_results = find_similar(db, "trade_off_configs", task_description, limit=1)
    trade_off_config = tradeoff_results[0]["description"] if tradeoff_results else "Balance quality and speed"
    trade_off_config_id = tradeoff_results[0]["id"] if tradeoff_results else None

    # Upsert composition
    agent_id = upsert_agent(
        db,
        role_component_ids=role_component_ids,
        desired_outcome_id=desired_outcome_id,
        trade_off_config_id=trade_off_config_id,
        instance_id=instance_id,
        client_id=client_id,
        project_id=project_id,
    )

    # Select template
    templates = list_templates(db, template_type="task_agent", instance_id=instance_id)
    if templates:
        template_content = templates[0]["content"]
        template_id = templates[0]["id"]
    else:
        template_content = load_default_template("task_agent")
        template_id = "default"

    composition_hash = content_hash("".join(sorted(role_component_ids)))

    rendered = render_agent(
        template=template_content,
        agent_id=agent_id,
        content_hash=composition_hash,
        template_id=template_id,
        role_components=role_component_texts if role_component_texts else ["general task completion"],
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task_description,
        output_structure=task.get("output_structure", "structured"),
        output_format=task.get("output_format", "json"),
        clarification_behaviour=task.get("clarification_behaviour", "ask"),
    )

    # Compute mean embedding vector across all selected primitives
    all_embeddings = []
    for r in role_results + outcome_results + tradeoff_results:
        emb = r.get("embedding")
        if emb:
            vec = json.loads(emb) if isinstance(emb, str) else emb
            all_embeddings.append(vec)

    if all_embeddings:
        n = len(all_embeddings[0])
        mean_embedding = [sum(e[i] for e in all_embeddings) / len(all_embeddings) for i in range(n)]
    else:
        mean_embedding = []

    return {
        "agent_id": agent_id,
        "content_hash": composition_hash,
        "template_id": template_id,
        "rendered_prompt": rendered,
        "embedding_vector": mean_embedding,
        "primitive_ids": {
            "role_components": role_component_ids,
            "desired_outcomes": [desired_outcome_id] if desired_outcome_id else [],
            "trade_off_configs": [trade_off_config_id] if trade_off_config_id else [],
        },
    }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x ** 2 for x in a) ** 0.5
    mag_b = sum(x ** 2 for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def deduplicate_compositions(compositions: list, threshold: float = 0.90) -> list[list[int]]:
    assigned = [False] * len(compositions)
    clusters = []
    for i, comp in enumerate(compositions):
        if assigned[i]:
            continue
        cluster = [i]
        for j in range(i + 1, len(compositions)):
            if not assigned[j]:
                sim = cosine_similarity(comp.embedding, compositions[j].embedding)
                if sim >= threshold:
                    cluster.append(j)
                    assigned[j] = True
        clusters.append(cluster)
        assigned[i] = True
    return clusters


def assign_agents_batch(tasks: list, db, cfg: dict) -> dict:
    """Assign agents to a batch of tasks with cosine-similarity deduplication."""
    results = []
    for task in tasks:
        enriched = task.description
        if task.skills:
            enriched += " " + " ".join(task.skills)
        if task.deliverables:
            enriched += " " + " ".join(task.deliverables)
        result = assign_agent(db, task.external_id or enriched[:16], {"task_description": enriched})
        results.append(result)

    class Comp:
        def __init__(self, embedding):
            self.embedding = embedding

    comps = [Comp(r["embedding_vector"]) for r in results]
    clusters = deduplicate_compositions(comps)

    assignments = {}
    agents = {}

    for cluster in clusters:
        canonical_idx = cluster[0]
        canonical = results[canonical_idx]
        agent_hash = canonical["content_hash"]

        agents[agent_hash] = {
            "rendered_prompt": canonical["rendered_prompt"],
            "content_hash": canonical["content_hash"],
            "template_id": canonical["template_id"],
            "primitive_ids": canonical["primitive_ids"],
        }

        for idx in cluster:
            task = tasks[idx]
            ext_id = task.external_id or str(idx)
            assignments[ext_id] = {
                "agency_task_id": results[idx].get("task_id", ext_id),
                "agent_hash": agent_hash,
            }

    return {"assignments": assignments, "agents": agents}
