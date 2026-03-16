import sqlite3
from agency.db.primitives import find_similar
from agency.db.compositions import upsert_agent
from agency.db.templates import list_templates
from agency.engine.renderer import render_evaluator, load_default_template
from agency.auth.jwt import create_evaluator_jwt
from agency.utils.hashing import content_hash
from agency.utils.ids import new_uuid


def build_evaluator(
    db: sqlite3.Connection,
    task_id: str,
    task: dict,
    private_key,
    instance_id: str,
) -> dict:
    """
    Build an evaluator agent for a task.

    Strategy:
    1. Search for evaluation-focused role components
    2. Compose evaluator agent
    3. Create callback JWT baked into the prompt
    4. Render evaluator prompt
    """
    task_description = task.get("task_description", "")
    client_id = task.get("client_id")
    project_id = task.get("project_id")

    eval_query = f"evaluate and assess: {task_description}"

    role_results = find_similar(db, "role_components", eval_query, limit=2)
    role_component_ids = [r["id"] for r in role_results]
    role_component_texts = [r["description"] for r in role_results]

    outcome_results = find_similar(db, "desired_outcomes", eval_query, limit=1)
    desired_outcome = outcome_results[0]["description"] if outcome_results else "Produce a structured evaluation report"
    desired_outcome_id = outcome_results[0]["id"] if outcome_results else None

    tradeoff_results = find_similar(db, "trade_off_configs", eval_query, limit=1)
    trade_off_config = tradeoff_results[0]["description"] if tradeoff_results else "Rigour over speed"
    trade_off_config_id = tradeoff_results[0]["id"] if tradeoff_results else None

    evaluator_agent_id = upsert_agent(
        db,
        role_component_ids=role_component_ids,
        desired_outcome_id=desired_outcome_id,
        trade_off_config_id=trade_off_config_id,
        instance_id=instance_id,
        client_id=client_id,
        project_id=project_id,
    )

    composition_hash = content_hash("eval:" + "".join(sorted(role_component_ids)))

    # Look up task agent composition for JWT metadata
    from agency.db.tasks import get_task as _get_task
    from agency.db.compositions import get_agent
    import json as _json

    task_record = _get_task(db, task_id)
    task_agent_composition_id = task_record.get("agent_composition_id", "") if task_record else ""

    task_agent_content_hash = ""
    task_agent_primitive_ids = {}
    if task_agent_composition_id:
        task_agent = get_agent(db, task_agent_composition_id)
        if task_agent:
            task_agent_content_hash = task_agent.get("content_hash", "")
            rc_ids = _json.loads(task_agent.get("role_component_ids", "[]"))
            task_agent_primitive_ids = {
                "role_components": rc_ids,
                "desired_outcomes": [task_agent.get("desired_outcome_id")] if task_agent.get("desired_outcome_id") else [],
                "trade_off_configs": [task_agent.get("trade_off_config_id")] if task_agent.get("trade_off_config_id") else [],
            }

    if private_key is not None:
        callback_jwt = create_evaluator_jwt(
            private_key,
            instance_id=instance_id,
            client_id=client_id or "",
            project_id=project_id or "",
            task_id=task_id,
            agent_composition_id=task_agent_composition_id,
            agent_content_hash=task_agent_content_hash,
            evaluator_agent_id=evaluator_agent_id,
            evaluator_content_hash=composition_hash,
            task_agent_primitive_ids=task_agent_primitive_ids,
        )
    else:
        callback_jwt = ""

    templates = list_templates(db, template_type="evaluator", instance_id=instance_id)
    if templates:
        template_content = templates[0]["content"]
        template_id = templates[0]["id"]
    else:
        template_content = load_default_template("evaluator")
        template_id = "default"

    rendered = render_evaluator(
        template=template_content,
        agent_id=evaluator_agent_id,
        content_hash=composition_hash,
        template_id=template_id,
        role_components=role_component_texts if role_component_texts else ["evaluate task output"],
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task_description,
        output_structure=task.get("output_structure", "structured"),
        output_format=task.get("output_format", "json"),
        clarification_behaviour=task.get("clarification_behaviour", "ask"),
        callback_jwt=callback_jwt,
    )

    return {
        "evaluator_agent_id": evaluator_agent_id,
        "content_hash": composition_hash,
        "template_id": template_id,
        "rendered_prompt": rendered,
        "callback_jwt": callback_jwt,
    }
