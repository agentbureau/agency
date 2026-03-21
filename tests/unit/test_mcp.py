"""Tests for the Agency MCP server CLI module."""
import json
import os
import hashlib
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# helpers under test
# ---------------------------------------------------------------------------

from agency.cli.mcp import (
    _read_toml_config,
    _resolve_project_id,
    _maybe_inject_onboarding,
    _tool_agency_assign,
    _tool_agency_evaluator,
    _tool_agency_submit_evaluation,
    _tool_agency_get_task,
    _tool_agency_list_projects,
    _tool_agency_create_project,
    _tool_agency_status,
)

from agency.client import (
    _make_error,
    _classify_error,
)


# ---------------------------------------------------------------------------
# Envelope format
# ---------------------------------------------------------------------------


def test_error_envelope_format():
    err = _make_error("not_found", 404, "not found")
    assert err == {
        "status": "error", "error_type": "not_found", "code": 404,
        "message": "not found", "cause": None, "fix": None,
    }

    err_none = _make_error("transient", None, "connection refused")
    assert err_none == {
        "status": "error", "error_type": "transient", "code": None,
        "message": "connection refused", "cause": None, "fix": None,
    }

    err_with_cause = _make_error("transient", 503, "no primitives", cause="store empty", fix="run update")
    assert err_with_cause["cause"] == "store empty"
    assert err_with_cause["fix"] == "run update"
    assert err_with_cause["error_type"] == "transient"


def test_classify_error_status_codes():
    assert _classify_error(503) == "transient"
    assert _classify_error(401) == "auth"
    assert _classify_error(404) == "not_found"
    assert _classify_error(400) == "validation"
    assert _classify_error(422) == "validation"
    assert _classify_error(409) == "validation"
    assert _classify_error(500) == "permanent"


def test_classify_error_exceptions():
    import httpx as real_httpx
    assert _classify_error(None, exception=real_httpx.ConnectError("refused")) == "transient"
    assert _classify_error(None, exception=real_httpx.ReadTimeout("timeout")) == "transient"
    assert _classify_error(None, exception=ValueError("bad")) == "permanent"


# ---------------------------------------------------------------------------
# _resolve_project_id
# ---------------------------------------------------------------------------


def test_agency_assign_explicit_project_id_used_directly():
    """Explicit arg bypasses all lookups."""
    result = _resolve_project_id("proj-explicit")
    assert result == "proj-explicit"


def test_agency_assign_uses_env_var_first(monkeypatch):
    """AGENCY_PROJECT_ID env var takes precedence over toml (when no repo config)."""
    monkeypatch.setenv("AGENCY_PROJECT_ID", "proj-from-env")
    with patch("agency.cli.mcp._read_toml_config", return_value={"project": {"default_id": "proj-from-toml"}}), \
         patch("agency.cli.mcp._find_repo_config", return_value=None):
        result = _resolve_project_id(None)
    assert result == "proj-from-env"


def test_agency_assign_falls_back_to_toml(monkeypatch):
    """Falls back to agency.toml [project] default_id when no env var and no repo config."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={"project": {"default_id": "proj-from-toml"}}), \
         patch("agency.cli.mcp._find_repo_config", return_value=None):
        result = _resolve_project_id(None)
    assert result == "proj-from-toml"


def test_agency_assign_no_project_id_returns_error(monkeypatch):
    """_resolve_project_id returns None when no project configured anywhere."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={}), \
         patch("agency.cli.mcp._find_repo_config", return_value=None):
        result = _resolve_project_id(None)
    assert result is None


def test_resolve_project_id_rereads_toml_on_each_call(monkeypatch):
    """Never caches, reads fresh on every call."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config") as mock_read, \
         patch("agency.cli.mcp._find_repo_config", return_value=None):
        mock_read.return_value = {"project": {"default_id": "first"}}
        assert _resolve_project_id(None) == "first"

        mock_read.return_value = {"project": {"default_id": "second"}}
        assert _resolve_project_id(None) == "second"

        assert mock_read.call_count == 2


def test_resolve_project_id_checks_repo_config(monkeypatch, tmp_path):
    """v1.2.1: .agency-project file takes precedence over env var."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    config_file = tmp_path / ".agency-project"
    config_file.write_text("proj-from-repo-config")

    with patch("agency.cli.mcp._read_toml_config", return_value={}), \
         patch("agency.cli.mcp._find_repo_config", return_value=str(config_file)):
        result = _resolve_project_id(None)
    assert result == "proj-from-repo-config"


# ---------------------------------------------------------------------------
# _tool_agency_assign
# ---------------------------------------------------------------------------


def test_agency_assign_returns_error_when_no_project(monkeypatch):
    """assign returns error envelope when project_id resolves to None."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={}), \
         patch("agency.cli.mcp._find_repo_config", return_value=None):
        result_str = _tool_agency_assign("http://localhost:8000", "tok", None, [{"name": "t1"}])
    result = json.loads(result_str)
    assert result["status"] == "error"
    assert result["error_type"] == "validation"
    assert result["code"] is None
    assert "project" in result["message"].lower()
    assert result["cause"] is not None
    assert result["fix"] is not None


def test_assign_response_has_next_step():
    """v1.2.1: agency_assign response includes next_step and agency_task_id_note."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "assignments": {"t1": {"agency_task_id": "uuid-1", "agent_hash": "hash-1"}},
        "agents": {"hash-1": {"rendered_prompt": "do stuff", "content_hash": "c1", "template_id": "t1", "primitive_ids": {}}},
    }
    with patch("agency.client._call_with_retry") as mock_retry, \
         patch("agency.cli.mcp._resolve_project_id", return_value="proj-1"):
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_assign("http://localhost:8000", "tok", "proj-1", [{"external_id": "t1", "description": "test"}]))

    assert result["status"] == "ok"
    assert "next_step" in result
    assert len(result["next_step"]) > 0
    assert "agency_task_id_note" in result["assignments"]["t1"]
    assert "task_ids" in result


# ---------------------------------------------------------------------------
# _tool_agency_evaluator
# ---------------------------------------------------------------------------


def test_evaluator_response_has_next_step_and_task_id():
    """v1.2.1: agency_evaluator response includes next_step and agency_task_id."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rendered_prompt": "evaluate this",
        "callback_jwt": "jwt-here",
        "evaluator_agent_id": "eval-1",
    }
    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_evaluator("http://localhost:8000", "tok", "task-123"))

    assert result["status"] == "ok"
    assert result["evaluator_prompt"] == "evaluate this"
    assert result["callback_jwt"] == "jwt-here"
    assert result["agency_task_id"] == "task-123"
    assert "next_step" in result
    assert "agency_submit_evaluation" in result["next_step"]


# ---------------------------------------------------------------------------
# _tool_agency_submit_evaluation
# ---------------------------------------------------------------------------


def test_submit_evaluation_passes_bytes_to_httpx():
    """httpx.post receives bytes via content=, not json=."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Hash body WITHOUT callback_jwt
    hash_body = json.dumps({"output": "looks good"}, ensure_ascii=False, separators=(',', ':')).encode("utf-8")
    expected_hash = hashlib.sha256(hash_body).hexdigest()
    mock_resp.json.return_value = {"content_hash": expected_hash}

    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-token", "looks good"
        )

    result = json.loads(result_str)
    assert result["status"] == "ok"
    assert result["content_hash"] == expected_hash
    assert "next_step" in result


def test_submit_evaluation_accepts_new_params():
    """v1.2.1: agency_submit_evaluation accepts score, task_completed, score_type."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "content_hash": "abc123"}

    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-tok", "looks good",
            score=85, task_completed=True, score_type="rubric",
        ))

    assert result["status"] == "ok"
    assert "next_step" in result


def test_submit_evaluation_returns_null_code_on_connect_error():
    """ConnectError → code=None in error envelope."""
    import httpx as real_httpx

    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.side_effect = real_httpx.ConnectError("Connection refused")
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-token", "output"
        )

    result = json.loads(result_str)
    assert result["status"] == "error"
    assert result["error_type"] == "transient"
    assert result["code"] is None


def test_call_with_retry_retries_once():
    """Connection errors get one retry after delay."""
    from agency.client import _call_with_retry
    import httpx as real_httpx

    mock_fn = MagicMock()
    mock_fn.side_effect = [real_httpx.ConnectError("refused"), MagicMock(status_code=200)]

    with patch("agency.client.time") as mock_time:
        result = _call_with_retry(mock_fn, "http://localhost:8000")

    assert mock_fn.call_count == 2
    mock_time.sleep.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# _tool_agency_get_task
# ---------------------------------------------------------------------------


def test_get_task_returns_state_and_next_step():
    """agency_get_task returns task state with context-sensitive next_step."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "agency_task_id": "task-123",
        "external_id": "t1",
        "project_id": "proj-1",
        "state": "assigned",
        "agent_hash": "abc123",
        "rendered_prompt": "do stuff",
        "rendering_warnings": [],
        "created_at": "2026-03-18T00:00:00Z",
        "evaluation": None,
    }
    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_get_task("http://localhost:8000", "tok", "task-123"))

    assert result["status"] == "ok"
    assert result["state"] == "assigned"
    assert "next_step" in result
    assert "evaluated" in result["next_step"].lower()


def test_get_task_evaluation_pending_next_step():
    """agency_get_task with evaluation_pending state has correct next_step."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "agency_task_id": "task-123",
        "external_id": "t1",
        "project_id": "proj-1",
        "state": "evaluation_pending",
        "agent_hash": "abc123",
        "rendered_prompt": "do stuff",
        "rendering_warnings": [],
        "created_at": "2026-03-18T00:00:00Z",
        "evaluation": {"evaluation_status": "pending", "output": "good"},
    }
    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_get_task("http://localhost:8000", "tok", "task-123"))

    assert result["status"] == "ok"
    assert "pending" in result["next_step"].lower()


def test_get_task_404_returns_error():
    """agency_get_task returns structured error on 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not found"
    with patch("agency.client._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_get_task("http://localhost:8000", "tok", "bad-id"))

    assert result["status"] == "error"
    assert result["error_type"] == "not_found"
    assert result["code"] == 404


# ---------------------------------------------------------------------------
# _tool_agency_list_projects
# ---------------------------------------------------------------------------


def test_list_projects_tool_returns_projects():
    """agency_list_projects returns enriched project list with default_source."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "projects": [{"id": "p1", "name": "Test", "description": None, "created_at": "2026-01-01"}],
        "default_project_id": "p1",
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry, \
         patch("agency.cli.mcp._find_repo_config", return_value=None), \
         patch("agency.cli.mcp._read_toml_config", return_value={"project": {"default_id": "p1"}}):
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_list_projects("http://localhost:8000", "tok"))

    assert "projects" in result
    assert len(result["projects"]) == 1
    assert result["projects"][0]["is_default"] is True
    assert "next_step" in result
    assert "default_source" in result
    assert result["default_source"] == "toml_config"


def test_list_projects_tool_empty():
    """agency_list_projects with no projects returns empty list and create next_step."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "projects": [],
        "default_project_id": None,
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry, \
         patch("agency.cli.mcp._find_repo_config", return_value=None), \
         patch("agency.cli.mcp._read_toml_config", return_value={}):
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_list_projects("http://localhost:8000", "tok"))

    assert result["projects"] == []
    assert "create" in result["next_step"].lower()
    assert result["default_source"] == "none"


def test_list_projects_tool_connection_error():
    """agency_list_projects returns structured error on connection failure."""
    import httpx as real_httpx

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.side_effect = real_httpx.ConnectError("Connection refused")
        result = json.loads(_tool_agency_list_projects("http://localhost:8000", "tok"))

    assert result["status"] == "error"
    assert result["error_type"] == "transient"
    assert result["code"] is None


# ---------------------------------------------------------------------------
# _tool_agency_create_project
# ---------------------------------------------------------------------------


def test_create_project_tool_returns_project_id():
    """agency_create_project renames id to project_id and includes next_step."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": "new-uuid",
        "name": "New Project",
        "contact_email": None,
        "oversight_preference": "discretion",
        "error_notification_timeout": 1800,
        "attribution": True,
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_create_project(
            "http://localhost:8000", "tok", "New Project"))

    assert result["project_id"] == "new-uuid"
    assert result["name"] == "New Project"
    assert "next_step" in result
    assert "settings_applied" in result


def test_create_project_tool_empty_name_error():
    """agency_create_project returns error for empty name without calling API."""
    result = json.loads(_tool_agency_create_project(
        "http://localhost:8000", "tok", ""))

    assert result["status"] == "error"
    assert result["error_type"] == "validation"
    assert result["code"] == 400
    assert "name" in result["message"].lower()


def test_create_project_tool_duplicate_name():
    """agency_create_project returns 409 for duplicate project name."""
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.json.return_value = {
        "detail": {
            "error": "duplicate_name",
            "message": 'A project named "Existing" already exists.',
            "existing_project_id": "existing-uuid",
        }
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_create_project(
            "http://localhost:8000", "tok", "Existing"))

    assert result["status"] == "error"
    assert result["error_type"] == "validation"
    assert result["code"] == 409
    assert "Existing" in result["message"]


def test_create_project_tool_set_as_default(tmp_path, monkeypatch):
    """agency_create_project with set_as_default writes to agency.toml."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "default-uuid", "name": "Default Project"}

    toml_path = tmp_path / "agency.toml"
    toml_path.write_text("")

    with patch("agency.cli.mcp._call_with_retry") as mock_retry, \
         patch("agency.cli.mcp._get_config_file_path", return_value=str(toml_path)):
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_create_project(
            "http://localhost:8000", "tok", "Default Project", set_as_default=True))

    assert result["project_id"] == "default-uuid"
    assert result["is_default"] is True

    # Verify toml was written
    import tomllib
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    assert cfg["project"]["default_id"] == "default-uuid"


def test_create_project_tool_connection_error():
    """agency_create_project returns structured error on connection failure."""
    import httpx as real_httpx

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.side_effect = real_httpx.ConnectError("Connection refused")
        result = json.loads(_tool_agency_create_project(
            "http://localhost:8000", "tok", "Test"))

    assert result["status"] == "error"
    assert result["error_type"] == "transient"
    assert result["code"] is None


# ---------------------------------------------------------------------------
# _tool_agency_status
# ---------------------------------------------------------------------------


def test_status_tool_returns_instance_info():
    """agency_status returns instance info with context-sensitive next_step."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instance_id": "inst-1",
        "server_version": "1.2.1",
        "uptime_seconds": 100,
        "projects": [],
        "primitive_counts": {},
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_status("http://localhost:8000", "tok"))

    assert "instance_id" in result
    assert result["instance_id"] == "inst-1"
    assert "next_step" in result
    assert "agency_assign" in result["next_step"]


def test_status_tool_assigned_tasks_next_step():
    """agency_status next_step mentions assigned task count when tasks exist."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instance_id": "inst-1",
        "server_version": "1.2.1",
        "uptime_seconds": 100,
        "projects": [
            {
                "id": "p1",
                "name": "Test",
                "is_default": True,
                "task_summary": {"total": 5, "assigned": 3, "evaluation_pending": 1, "evaluation_received": 1},
                "active_tasks": [],
            }
        ],
        "primitive_counts": {},
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_status("http://localhost:8000", "tok"))

    assert "3 tasks are assigned" in result["next_step"]
    assert "agency_evaluator" in result["next_step"]


def test_status_tool_with_project_id_filter():
    """agency_status passes project_id as query param."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instance_id": "inst-1",
        "server_version": "1.2.1",
        "uptime_seconds": 100,
        "projects": [],
        "primitive_counts": {},
    }
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        _tool_agency_status("http://localhost:8000", "tok", project_id="p1")

    # Verify the URL includes the project_id query param
    call_args = mock_retry.call_args
    url_arg = call_args[0][1]
    assert "project_id=p1" in url_arg


def test_status_tool_connection_error():
    """agency_status returns structured error on connection failure."""
    import httpx as real_httpx

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.side_effect = real_httpx.ConnectError("Connection refused")
        result = json.loads(_tool_agency_status("http://localhost:8000", "tok"))

    assert result["status"] == "error"
    assert result["error_type"] == "transient"
    assert result["code"] is None


# ---------------------------------------------------------------------------
# _maybe_inject_onboarding
# ---------------------------------------------------------------------------


def test_onboarding_fires_when_no_marker(tmp_path, monkeypatch):
    """Onboarding field injected when marker file does not exist."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    marker = tmp_path / ".onboarded"
    assert not marker.exists()

    result_json = json.dumps({"status": "ok", "data": "hello"})
    output = _maybe_inject_onboarding(result_json)
    parsed = json.loads(output)

    assert "first_run_onboarding" in parsed
    assert parsed["first_run_onboarding"]["skill_name"] == "agency-getting-started"
    assert "message" in parsed["first_run_onboarding"]
    assert "skip_instruction" in parsed["first_run_onboarding"]
    # Marker file should now exist
    assert marker.exists()


def test_onboarding_does_not_fire_when_marker_exists(tmp_path, monkeypatch):
    """Onboarding field omitted when marker file already exists."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    marker = tmp_path / ".onboarded"
    marker.touch()

    result_json = json.dumps({"status": "ok", "data": "hello"})
    output = _maybe_inject_onboarding(result_json)
    parsed = json.loads(output)

    assert "first_run_onboarding" not in parsed


def test_onboarding_creates_marker_only_once(tmp_path, monkeypatch):
    """Second call after first injection does not inject again."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))

    result_json = json.dumps({"status": "ok"})

    # First call — should inject and create marker
    output1 = json.loads(_maybe_inject_onboarding(result_json))
    assert "first_run_onboarding" in output1

    # Second call — marker exists, should not inject
    output2 = json.loads(_maybe_inject_onboarding(result_json))
    assert "first_run_onboarding" not in output2


def test_onboarding_preserves_original_on_bad_json(tmp_path, monkeypatch):
    """Invalid JSON input is returned unchanged."""
    monkeypatch.setenv("AGENCY_STATE_DIR", str(tmp_path))
    bad_json = "not valid json {"
    output = _maybe_inject_onboarding(bad_json)
    assert output == bad_json
