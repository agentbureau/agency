from agency.utils.ids import new_uuid, new_template_id


def test_uuid_is_string():
    assert isinstance(new_uuid(), str)


def test_uuids_are_unique():
    assert new_uuid() != new_uuid()


def test_task_agent_template_id_prefix():
    assert new_template_id("task_agent").startswith("agt-")


def test_evaluator_template_id_prefix():
    assert new_template_id("evaluator").startswith("evt-")
