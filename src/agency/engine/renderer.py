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
