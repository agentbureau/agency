from agency.models.tasks import BatchTaskRequest, BatchAssignRequest, BatchAssignResponse


def test_batch_task_request_requires_description():
    t = BatchTaskRequest(description="do something")
    assert t.external_id is None
    assert t.skills == []
    assert t.deliverables == []


def test_batch_assign_response_shape():
    resp = BatchAssignResponse(
        assignments={"task-1": {"agency_task_id": "uuid", "agent_hash": "abc"}},
        agents={"abc": {
            "rendered_prompt": "You are...",
            "content_hash": "abc",
            "template_id": "default",
            "primitive_ids": {"role_components": [], "desired_outcomes": [], "trade_off_configs": []},
        }}
    )
    assert resp.assignments["task-1"]["agent_hash"] == "abc"
