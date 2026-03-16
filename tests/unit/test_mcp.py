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
    """AGENCY_PROJECT_ID env var takes precedence over toml."""
    monkeypatch.setenv("AGENCY_PROJECT_ID", "proj-from-env")
    with patch("agency.cli.mcp._read_toml_config", return_value={"project": {"default_id": "proj-from-toml"}}):
        result = _resolve_project_id(None)
    assert result == "proj-from-env"


def test_agency_assign_falls_back_to_toml(monkeypatch):
    """Falls back to agency.toml [project] default_id when no env var."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={"project": {"default_id": "proj-from-toml"}}):
        result = _resolve_project_id(None)
    assert result == "proj-from-toml"


def test_agency_assign_no_project_id_returns_error(monkeypatch):
    """_resolve_project_id returns None when no project configured anywhere."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={}):
        result = _resolve_project_id(None)
    assert result is None


def test_resolve_project_id_rereads_toml_on_each_call(monkeypatch):
    """Never caches, reads fresh on every call."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config") as mock_read:
        mock_read.return_value = {"project": {"default_id": "first"}}
        assert _resolve_project_id(None) == "first"

        mock_read.return_value = {"project": {"default_id": "second"}}
        assert _resolve_project_id(None) == "second"

        assert mock_read.call_count == 2


# ---------------------------------------------------------------------------
# _tool_agency_assign
# ---------------------------------------------------------------------------


def test_agency_assign_returns_error_when_no_project(monkeypatch):
    """assign returns error envelope when project_id resolves to None."""
    monkeypatch.delenv("AGENCY_PROJECT_ID", raising=False)
    with patch("agency.cli.mcp._read_toml_config", return_value={}):
        result_str = _tool_agency_assign("http://localhost:8000", "tok", None, [{"name": "t1"}])
    result = json.loads(result_str)
    assert result["status"] == "error"
    assert result["code"] is None
    assert "project" in result["message"].lower()


# ---------------------------------------------------------------------------
# _tool_agency_submit_evaluation — bytes, not json
# ---------------------------------------------------------------------------


def test_submit_evaluation_passes_bytes_to_httpx():
    """httpx.post receives bytes via content=, not json=."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    body_bytes = json.dumps({"output": "looks good"}, ensure_ascii=False, separators=(',', ':')).encode("utf-8")
    expected_hash = hashlib.sha256(body_bytes).hexdigest()
    mock_resp.json.return_value = {"content_hash": expected_hash}

    with patch("agency.cli.mcp.httpx") as mock_httpx:
        mock_httpx.post.return_value = mock_resp
        mock_httpx.HTTPError = Exception  # so except clause works
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "task-123", "jwt-token", "looks good"
        )

    # Verify content= was used (bytes), not json=
    call_kwargs = mock_httpx.post.call_args
    assert "content" in call_kwargs.kwargs or (len(call_kwargs.args) > 1 and isinstance(call_kwargs.args[1], bytes))
    # Specifically, json= should NOT be in kwargs
    assert "json" not in (call_kwargs.kwargs or {})

    result = json.loads(result_str)
    assert result["status"] == "ok"
    assert result["content_hash"] == expected_hash


def test_submit_evaluation_returns_null_code_on_connect_error():
    """ConnectError → code=None in error envelope."""
    import httpx as real_httpx

    with patch("agency.cli.mcp.httpx") as mock_httpx:
        mock_httpx.HTTPError = real_httpx.HTTPError
        mock_httpx.post.side_effect = real_httpx.ConnectError("Connection refused")
        result_str = _tool_agency_submit_evaluation(
            "http://localhost:8000", "task-123", "jwt-token", "output"
        )

    result = json.loads(result_str)
    assert result["status"] == "error"
    assert result["code"] is None
    assert "refused" in result["message"].lower() or "connect" in result["message"].lower()
