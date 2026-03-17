"""Tests for the Agency CLI task commands."""
import json
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from agency.cli.task import (
    task_assign_command,
    task_evaluator_command,
    task_submit_command,
    task_get_command,
    _validate_uuid,
    _resolve_client_id,
    EXIT_SUCCESS,
    EXIT_CLIENT_ERROR,
    EXIT_APP_ERROR,
)


@pytest.fixture
def runner():
    return CliRunner()


def _parse_json_output(output: str) -> dict:
    """Parse the first JSON object from CLI output (stderr may follow on next lines)."""
    return json.loads(output.split("\n")[0])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_validate_uuid_valid():
    assert _validate_uuid("01926e4a-7c8e-7000-8000-000000000001", "test") == "01926e4a-7c8e-7000-8000-000000000001"


def test_validate_uuid_no_hyphens():
    result = _validate_uuid("01926e4a7c8e70008000000000000001", "test")
    assert result == "01926e4a-7c8e-7000-8000-000000000001"


def test_validate_uuid_invalid():
    assert _validate_uuid("not-a-uuid", "test") is None


def test_resolve_client_id_flag():
    assert _resolve_client_id("custom") == "custom"


def test_resolve_client_id_env(monkeypatch):
    monkeypatch.setenv("AGENCY_CLIENT_ID", "env-client")
    assert _resolve_client_id(None) == "env-client"


def test_resolve_client_id_default(monkeypatch):
    monkeypatch.delenv("AGENCY_CLIENT_ID", raising=False)
    assert _resolve_client_id(None) == "cli"


# ---------------------------------------------------------------------------
# task assign
# ---------------------------------------------------------------------------


def test_assign_no_task_input_exits_1(runner):
    result = runner.invoke(task_assign_command, [])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert output["status"] == "error"
    assert output["error_type"] == "validation"
    assert "Exactly one" in output["message"]


def test_assign_invalid_json_exits_1(runner):
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"):
        result = runner.invoke(task_assign_command, ["--tasks", "{bad json}"])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert output["error_type"] == "validation"
    assert "Invalid JSON" in output["message"]


def test_assign_not_array_exits_1(runner):
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"):
        result = runner.invoke(task_assign_command, ["--tasks", '{"not": "array"}'])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "array" in output["message"].lower()


def test_assign_empty_array_exits_1(runner):
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"):
        result = runner.invoke(task_assign_command, ["--tasks", "[]"])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "at least one" in output["message"].lower()


def test_assign_missing_field_exits_1(runner):
    tasks = json.dumps([{"external_id": "t1"}])
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"):
        result = runner.invoke(task_assign_command, ["--tasks", tasks])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "description" in output["message"]


def test_assign_success_returns_json(runner):
    tasks = json.dumps([{"external_id": "t1", "description": "test"}])
    mock_result = {
        "status": "ok",
        "task_ids": [{"external_id": "t1", "agency_task_id": "uuid-1", "agent_hash": "abc12345"}],
        "assignments": {"t1": {"agency_task_id": "uuid-1", "agent_hash": "abc12345"}},
        "agents": {"abc12345": {"rendered_prompt": "do stuff", "content_hash": "abc12345"}},
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"), \
         patch("agency.cli.task.client_assign", return_value=mock_result):
        result = runner.invoke(task_assign_command, ["--tasks", tasks])
    assert result.exit_code == EXIT_SUCCESS
    output = _parse_json_output(result.output)
    assert output["status"] == "ok"
    assert "task_ids" in output


def test_assign_table_format(runner):
    tasks = json.dumps([{"external_id": "t1", "description": "test"}])
    mock_result = {
        "status": "ok",
        "task_ids": [{"external_id": "t1", "agency_task_id": "uuid-1", "agent_hash": "abcdef1234567890"}],
        "assignments": {"t1": {"agency_task_id": "uuid-1", "agent_hash": "abcdef1234567890"}},
        "agents": {"abcdef1234567890": {"rendered_prompt": "x" * 100, "content_hash": "abcdef1234567890"}},
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task._resolve_project_id_cli", return_value="proj-1"), \
         patch("agency.cli.task.client_assign", return_value=mock_result):
        result = runner.invoke(task_assign_command, ["--tasks", tasks, "--format", "table"])
    assert result.exit_code == EXIT_SUCCESS
    assert "EXTERNAL_ID" in result.output
    assert "abcdef12" in result.output  # 8-char truncation


def test_assign_invalid_project_uuid(runner):
    tasks = json.dumps([{"external_id": "t1", "description": "test"}])
    result = runner.invoke(task_assign_command, [
        "--tasks", tasks, "--project-id", "not-a-uuid",
    ])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "UUID" in output["message"]


# ---------------------------------------------------------------------------
# task evaluator
# ---------------------------------------------------------------------------


def test_evaluator_success(runner):
    mock_result = {
        "status": "ok",
        "evaluator_prompt": "evaluate this",
        "callback_jwt": "jwt-here",
        "agency_task_id": "01926e4a-7c8e-7000-8000-000000000001",
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_get_evaluator", return_value=mock_result):
        result = runner.invoke(task_evaluator_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
        ])
    assert result.exit_code == EXIT_SUCCESS
    output = _parse_json_output(result.output)
    assert output["status"] == "ok"
    assert output["evaluator_prompt"] == "evaluate this"


def test_evaluator_invalid_uuid(runner):
    result = runner.invoke(task_evaluator_command, ["--task-id", "bad-uuid"])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "UUID" in output["message"]


def test_evaluator_save_jwt(runner, tmp_path):
    jwt_path = str(tmp_path / "jwt.txt")
    mock_result = {
        "status": "ok",
        "evaluator_prompt": "evaluate this",
        "callback_jwt": "my-jwt-token",
        "agency_task_id": "01926e4a-7c8e-7000-8000-000000000001",
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_get_evaluator", return_value=mock_result):
        result = runner.invoke(task_evaluator_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
            "--save-jwt", jwt_path,
        ])
    assert result.exit_code == EXIT_SUCCESS
    with open(jwt_path) as f:
        assert f.read() == "my-jwt-token"


# ---------------------------------------------------------------------------
# task submit
# ---------------------------------------------------------------------------


def test_submit_no_jwt_exits_1(runner):
    result = runner.invoke(task_submit_command, [
        "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
        "--output", "good",
    ])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "callback-jwt" in output["message"].lower()


def test_submit_no_output_exits_1(runner):
    result = runner.invoke(task_submit_command, [
        "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
        "--callback-jwt", "jwt",
    ])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "output" in output["message"].lower()


def test_submit_success(runner):
    mock_result = {"status": "ok", "content_hash": "abc123"}
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_submit_evaluation", return_value=mock_result):
        result = runner.invoke(task_submit_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
            "--callback-jwt", "jwt-token",
            "--output", "looks good",
        ])
    assert result.exit_code == EXIT_SUCCESS
    output = _parse_json_output(result.output)
    assert output["status"] == "ok"


def test_submit_jwt_from_file(runner, tmp_path):
    jwt_file = tmp_path / "jwt.txt"
    jwt_file.write_text("  my-jwt-token  \n")
    mock_result = {"status": "ok", "content_hash": "abc123"}
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_submit_evaluation") as mock_submit:
        mock_submit.return_value = mock_result
        result = runner.invoke(task_submit_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
            "--callback-jwt-file", str(jwt_file),
            "--output", "looks good",
        ])
    assert result.exit_code == EXIT_SUCCESS
    # Verify whitespace was stripped
    call_args = mock_submit.call_args
    assert call_args[0][3] == "my-jwt-token"


def test_submit_score_out_of_range(runner):
    result = runner.invoke(task_submit_command, [
        "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
        "--callback-jwt", "jwt",
        "--output", "good",
        "--score", "101",
    ])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "0 and 100" in output["message"]


# ---------------------------------------------------------------------------
# task get
# ---------------------------------------------------------------------------


def test_get_success(runner):
    mock_result = {
        "status": "ok",
        "agency_task_id": "01926e4a-7c8e-7000-8000-000000000001",
        "external_id": "t1",
        "project_id": "proj-1",
        "state": "assigned",
        "agent_hash": "abcdef1234567890",
        "rendered_prompt": "do stuff",
        "rendering_warnings": [],
        "created_at": "2026-03-18T00:00:00Z",
        "evaluation": None,
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_get_task", return_value=mock_result):
        result = runner.invoke(task_get_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
        ])
    assert result.exit_code == EXIT_SUCCESS
    output = _parse_json_output(result.output)
    assert output["status"] == "ok"
    assert output["state"] == "assigned"
    assert "next_step" in output


def test_get_no_guidance_strips_next_step(runner):
    mock_result = {
        "status": "ok",
        "agency_task_id": "01926e4a-7c8e-7000-8000-000000000001",
        "external_id": "t1",
        "project_id": "proj-1",
        "state": "assigned",
        "agent_hash": "abcdef1234567890",
        "rendered_prompt": "do stuff",
        "rendering_warnings": [],
        "created_at": "2026-03-18T00:00:00Z",
        "evaluation": None,
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_get_task", return_value=mock_result):
        result = runner.invoke(task_get_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
            "--no-guidance",
        ])
    assert result.exit_code == EXIT_SUCCESS
    output = _parse_json_output(result.output)
    assert "next_step" not in output


def test_get_table_format(runner):
    mock_result = {
        "status": "ok",
        "agency_task_id": "01926e4a-7c8e-7000-8000-000000000001",
        "external_id": "t1",
        "project_id": "proj-1",
        "state": "evaluation_pending",
        "agent_hash": "abcdef1234567890",
        "rendered_prompt": "do stuff",
        "rendering_warnings": [],
        "created_at": "2026-03-18T00:00:00Z",
        "evaluation": None,
    }
    with patch("agency.cli.task.resolve_token", return_value="tok"), \
         patch("agency.cli.task.resolve_base_url", return_value="http://localhost:8000"), \
         patch("agency.cli.task.client_get_task", return_value=mock_result):
        result = runner.invoke(task_get_command, [
            "--task-id", "01926e4a-7c8e-7000-8000-000000000001",
            "--format", "table",
        ])
    assert result.exit_code == EXIT_SUCCESS
    assert "AGENCY_TASK_ID" in result.output
    assert "evaluation_pending" in result.output
    assert "abcdef12" in result.output  # 8-char hash


def test_get_invalid_uuid(runner):
    result = runner.invoke(task_get_command, ["--task-id", "not-uuid"])
    assert result.exit_code == EXIT_CLIENT_ERROR
    output = _parse_json_output(result.output)
    assert "UUID" in output["message"]
