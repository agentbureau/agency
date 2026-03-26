TASK_AGENT_TEMPLATE = """\
## Agent
ID: {agent_id} | Composition: {content_hash} | Template: {template_id}

## Role
{role_components}

## What success looks like
{desired_outcome}

## Trade-offs
{trade_off_config}

## Your task
{task_description}

## Output
Structure: {output_structure} | Format: {output_format}

## If task is unclear
{clarification_behaviour}
"""

EVALUATOR_TEMPLATE = TASK_AGENT_TEMPLATE + """
## Callback
Submit your evaluation report to this endpoint using this token:
{callback_jwt}
"""

_TEMPLATES = {
    "task_agent": TASK_AGENT_TEMPLATE,
    "evaluator": EVALUATOR_TEMPLATE,
}


def load_default_template(template_type: str) -> str:
    if template_type not in _TEMPLATES:
        raise ValueError(f"Unknown template type: {template_type}")
    return _TEMPLATES[template_type]


def _format_role_components(role_components: list[str]) -> str:
    return "\n".join(f"- {rc}" for rc in role_components)


def render_agent(
    template: str,
    agent_id: str,
    content_hash: str,
    template_id: str,
    role_components: list[str],
    desired_outcome: str,
    trade_off_config: str,
    task_description: str,
    output_structure: str,
    output_format: str,
    clarification_behaviour: str,
) -> str:
    return template.format(
        agent_id=agent_id,
        content_hash=content_hash,
        template_id=template_id,
        role_components=_format_role_components(role_components),
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task_description,
        output_structure=output_structure,
        output_format=output_format,
        clarification_behaviour=clarification_behaviour,
    )


def reconstruct_rendered_prompt(db, task_id: str) -> dict:
    """Re-render an agent prompt from stored composition for GET /tasks/{task_id}.

    Returns {'rendered_prompt': str, 'rendering_warnings': list[str]}.
    """
    import json
    from agency.db.tasks import get_task
    from agency.db.compositions import get_agent
    from agency.db.templates import get_template

    task = get_task(db, task_id)
    if task is None:
        return {"rendered_prompt": "", "rendering_warnings": ["Task not found"]}

    agent_id = task.get("agent_composition_id")
    if agent_id is None:
        return {"rendered_prompt": "", "rendering_warnings": ["No agent composition assigned"]}

    agent = get_agent(db, agent_id)
    if agent is None:
        return {"rendered_prompt": "", "rendering_warnings": ["Agent composition not found"]}

    warnings = []

    # Load role components
    role_component_ids = json.loads(agent.get("role_component_ids", "[]"))
    role_component_texts = []
    for rc_id in role_component_ids:
        row = db.execute(
            "SELECT description FROM role_components WHERE id = ?", (rc_id,)
        ).fetchone()
        if row:
            role_component_texts.append(row[0])
        else:
            role_component_texts.append(f"[primitive deleted: {rc_id}]")
            warnings.append(f"Role component deleted: {rc_id}")

    # Load desired outcome
    do_id = agent.get("desired_outcome_id")
    if do_id:
        row = db.execute(
            "SELECT description FROM desired_outcomes WHERE id = ?", (do_id,)
        ).fetchone()
        desired_outcome = row[0] if row else f"[primitive deleted: {do_id}]"
        if not row:
            warnings.append(f"Desired outcome deleted: {do_id}")
    else:
        desired_outcome = "Complete the task effectively"

    # Load trade-off config
    to_id = agent.get("trade_off_config_id")
    if to_id:
        row = db.execute(
            "SELECT description FROM trade_off_configs WHERE id = ?", (to_id,)
        ).fetchone()
        trade_off_config = row[0] if row else f"[primitive deleted: {to_id}]"
        if not row:
            warnings.append(f"Trade-off config deleted: {to_id}")
    else:
        trade_off_config = "Balance quality and speed"

    # Load template
    template_id = agent.get("template_id", "default")
    tmpl = get_template(db, template_id) if template_id != "default" else None
    if tmpl:
        template_content = tmpl["content"]
    else:
        template_content = load_default_template("task_agent")

    rendered = render_agent(
        template=template_content,
        agent_id=agent_id,
        content_hash=agent["content_hash"],
        template_id=template_id,
        role_components=role_component_texts if role_component_texts else ["general task completion"],
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task.get("description", ""),
        output_structure=task.get("output_structure", "structured"),
        output_format=task.get("output_format", "markdown"),
        clarification_behaviour=task.get("clarification_behaviour", "ask"),
    )

    return {"rendered_prompt": rendered, "rendering_warnings": warnings}


def render_evaluator(
    template: str,
    agent_id: str,
    content_hash: str,
    template_id: str,
    role_components: list[str],
    desired_outcome: str,
    trade_off_config: str,
    task_description: str,
    output_structure: str,
    output_format: str,
    clarification_behaviour: str,
    callback_jwt: str,
) -> str:
    return template.format(
        agent_id=agent_id,
        content_hash=content_hash,
        template_id=template_id,
        role_components=_format_role_components(role_components),
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task_description,
        output_structure=output_structure,
        output_format=output_format,
        clarification_behaviour=clarification_behaviour,
        callback_jwt=callback_jwt,
    )
