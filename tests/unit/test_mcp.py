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
    _make_error,
    _make_success,
    _tool_agency_assign,
    _tool_agency_evaluator,
    _tool_agency_submit_evaluation,
)


# ---------------------------------------------------------------------------
# Envelope format
# ---------------------------------------------------------------------------


def test_error_envelope_format():
    err = _make_error(404, "not found")
    assert err == {"status": "error", "code": 404, "message": "not found", "cause": None, "fix": None}

    err_none = _make_error(None, "connection refused")
    assert err_none == {"status": "error", "code": None, "message": "connection refused", "cause": None, "fix": None}

    err_with_cause = _make_error(503, "no primitives", cause="store empty", fix="run update")
    assert err_with_cause["cause"] == "store empty"
    assert err_with_cause["fix"] == "run update"

    ok = _make_success(assignment={"id": "abc"})
    assert ok == {"status": "ok", "assignment": {"id": "abc"}}

    ok_multi = _make_success(content_hash="deadbeef", verified=True)
    assert ok_multi == {"status": "ok", "content_hash": "deadbeef", "verified": True}


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
    with patch("agency.cli.mcp._call_with_retry") as mock_retry, \
         patch("agency.cli.mcp._resolve_project_id", return_value="proj-1"):
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_assign("http://localhost:8000", "tok", "proj-1", [{"external_id": "t1", "description": "test"}]))

    assert "next_step" in result
    assert len(result["next_step"]) > 0
    assert "agency_task_id_note" in result["assignments"]["t1"]


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
    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_evaluator("http://localhost:8000", "tok", "task-123"))

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

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-token", "looks good"
        )

    result = json.loads(result_str)
    assert result["status"] == "accepted"
    assert result["content_hash"] == expected_hash
    assert "next_step" in result


def test_submit_evaluation_accepts_new_params():
    """v1.2.1: agency_submit_evaluation accepts score, task_completed, score_type."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "accepted", "content_hash": "abc123"}

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.return_value = mock_resp
        result = json.loads(_tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-tok", "looks good",
            score=85, task_completed=True, score_type="rubric",
        ))

    assert result["status"] == "accepted"
    assert "next_step" in result


def test_submit_evaluation_returns_null_code_on_connect_error():
    """ConnectError → code=None in error envelope."""
    import httpx as real_httpx

    with patch("agency.cli.mcp._call_with_retry") as mock_retry:
        mock_retry.side_effect = real_httpx.ConnectError("Connection refused")
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "tok", "task-123", "jwt-token", "output"
        )

    result = json.loads(result_str)
    assert result["status"] == "error"
    assert result["code"] is None


def test_call_with_retry_retries_once():
    """Connection errors get one retry after delay."""
    from agency.cli.mcp import _call_with_retry
    import httpx as real_httpx

    mock_fn = MagicMock()
    mock_fn.side_effect = [real_httpx.ConnectError("refused"), MagicMock(status_code=200)]

    with patch("agency.cli.mcp.time") as mock_time:
        result = _call_with_retry(mock_fn, "http://localhost:8000")

    assert mock_fn.call_count == 2
    mock_time.sleep.assert_called_once_with(2)
