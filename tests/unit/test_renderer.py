from agency.engine.renderer import render_agent, render_evaluator, load_default_template


def test_rendered_agent_contains_role_components():
    output = render_agent(
        template=load_default_template("task_agent"),
        agent_id="agt-123",
        content_hash="abc",
        template_id="agt-tpl-001",
        role_components=["evaluate quality", "assign grades"],
        desired_outcome="produce a grade for each task",
        trade_off_config="rigour over speed",
        task_description="grade this submission",
        output_structure="structured",
        output_format="json",
        clarification_behaviour="ask",
    )
    assert "evaluate quality" in output
    assert "agt-123" in output


def test_evaluator_template_contains_callback_jwt():
    output = render_evaluator(
        template=load_default_template("evaluator"),
        agent_id="evt-123",
        content_hash="def",
        template_id="evt-tpl-001",
        role_components=["grade task output"],
        desired_outcome="return structured evaluation report",
        trade_off_config="rigour over speed",
        task_description="evaluate this task",
        output_structure="structured",
        output_format="json",
        clarification_behaviour="ask",
        callback_jwt="eyJhbG...",
    )
    assert "eyJhbG..." in output
    assert "evt-123" in output
