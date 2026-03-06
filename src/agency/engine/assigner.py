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

    return {
        "agent_id": agent_id,
        "content_hash": composition_hash,
        "template_id": template_id,
        "rendered_prompt": rendered,
    }
