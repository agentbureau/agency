from agency.config.hierarchy import resolve

def test_project_value_wins_when_set():
    assert resolve("project@example.com", "instance@example.com") == "project@example.com"

def test_instance_value_used_when_project_none():
    assert resolve(None, "instance@example.com") == "instance@example.com"

def test_project_value_false_wins_over_instance_true():
    assert resolve(0, True) == 0

def test_project_value_zero_wins_over_instance_positive():
    assert resolve(0, 300) == 0

def test_project_value_empty_string_wins():
    assert resolve("", "instance-value") == ""

def test_project_value_none_uses_instance_none():
    assert resolve(None, None) is None

def test_project_false_wins_over_instance_true():
    assert resolve(False, True) is False
