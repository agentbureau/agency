from agency.models.tasks import (
    BatchTaskRequest, BatchAssignRequest, BatchAssignResponse, AgentDefinition,
)


def test_batch_task_request_requires_description():
    t = BatchTaskRequest(description="do something")
    assert t.external_id is None
    assert t.skills == []
    assert t.deliverables == []


def test_batch_assign_response_shape():
    resp = BatchAssignResponse(
        assignments={"task-1": {"agency_task_id": "uuid", "agent_hash": "abc", "agent_id": "uuid-agent"}},
        agents={"abc": {
            "rendered_prompt": "You are...",
            "content_hash": "abc",
            "template_id": "default",
            "primitive_ids": {"role_components": [], "desired_outcomes": [], "trade_off_configs": []},
            "agent_id": "uuid-agent",
            "composition_fitness": None,
        }}
    )
    assert resp.assignments["task-1"]["agent_hash"] == "abc"


def test_agent_definition_includes_agent_id():
    defn = AgentDefinition(
        rendered_prompt="test",
        content_hash="abc123",
        template_id="default",
        primitive_ids={"role_components": ["id1"]},
        agent_id="uuid-here",
    )
    assert defn.agent_id == "uuid-here"
    assert defn.composition_fitness is None


def test_agent_definition_includes_composition_fitness():
    fitness = {
        "per_primitive_similarity": {"p1": 0.85},
        "pool_coverage_warning": False,
        "slots_filled": {"role_components": 3},
        "slots_empty": {"role_components": 0},
    }
    defn = AgentDefinition(
        rendered_prompt="test",
        content_hash="abc123",
        template_id="default",
        primitive_ids={"role_components": ["id1"]},
        agent_id="uuid-here",
        composition_fitness=fitness,
    )
    assert defn.composition_fitness == fitness
