"""MCP layer end-to-end tests — Issue 2.

These tests exercise the full assign → evaluate → submit flow by calling MCP
tool handler functions directly. httpx calls inside the handlers are intercepted
and forwarded to the FastAPI TestClient, giving true end-to-end coverage of:

  MCP handler → client.py → httpx (mocked) → TestClient → API routes → DB

No real running server required. The TestClient wraps the real ASGI app with a
real SQLite DB and seeded primitives, exactly as in production.
"""
import json
import hashlib
from unittest.mock import patch, MagicMock

import pytest
import httpx

from agency.cli.mcp import (
    _tool_agency_assign,
    _tool_agency_evaluator,
    _tool_agency_submit_evaluation,
    _tool_agency_get_task,
    _tool_agency_status,
)


# ---------------------------------------------------------------------------
# Transport adapter: route httpx calls through FastAPI TestClient
# ---------------------------------------------------------------------------


class TestClientTransport(httpx.BaseTransport):
    """httpx transport that forwards requests to a FastAPI TestClient.

    Converts httpx.Request → requests.Request (via TestClient), then wraps
    the response back into an httpx.Response so client.py is unaware.
    """

    def __init__(self, test_client):
        self._client = test_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        url = str(request.url)
        # Strip the scheme+host — TestClient only needs the path+query
        path_url = request.url.path
        if request.url.query:
            path_url = f"{path_url}?{request.url.query}"

        headers = dict(request.headers)
        # httpx sends lowercase header names; requests also handles these
        content = request.content

        tc_resp = self._client.request(
            method=method,
            url=path_url,
            content=content,
            headers=headers,
        )
        return httpx.Response(
            status_code=tc_resp.status_code,
            headers=dict(tc_resp.headers),
            content=tc_resp.content,
        )


def _make_httpx_client(test_client) -> httpx.Client:
    """Return a real httpx.Client that routes through the TestClient."""
    transport = TestClientTransport(test_client)
    return httpx.Client(transport=transport, base_url="http://testserver")


def _patch_httpx(test_client):
    """Context manager: patch httpx.get/post/put/delete to use TestClientTransport."""
    tc = _make_httpx_client(test_client)

    def _get(url, **kwargs):
        return tc.get(url, **kwargs)

    def _post(url, **kwargs):
        return tc.post(url, **kwargs)

    def _put(url, **kwargs):
        return tc.put(url, **kwargs)

    def _delete(url, **kwargs):
        return tc.delete(url, **kwargs)

    return (
        patch("httpx.get", side_effect=_get),
        patch("httpx.post", side_effect=_post),
        patch("httpx.put", side_effect=_put),
        patch("httpx.delete", side_effect=_delete),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(test_token: str) -> dict:
    from agency.client import API_VERSION_HEADER, API_VERSION
    return {
        "Authorization": f"Bearer {test_token}",
        API_VERSION_HEADER: API_VERSION,
    }


def _do_assign(test_app, test_token, test_project_id, tasks):
    """Call _tool_agency_assign with httpx routed through TestClient."""
    base_url = "http://testserver"
    patches = _patch_httpx(test_app["client"])
    with patches[0], patches[1], patches[2], patches[3]:
        result_str = _tool_agency_assign(
            base_url, test_token, test_project_id, tasks
        )
    return json.loads(result_str)


def _do_evaluator(test_app, test_token, agency_task_id):
    base_url = "http://testserver"
    patches = _patch_httpx(test_app["client"])
    with patches[0], patches[1], patches[2], patches[3]:
        result_str = _tool_agency_evaluator(base_url, test_token, agency_task_id)
    return json.loads(result_str)


def _do_get_task(test_app, test_token, agency_task_id):
    base_url = "http://testserver"
    patches = _patch_httpx(test_app["client"])
    with patches[0], patches[1], patches[2], patches[3]:
        result_str = _tool_agency_get_task(base_url, test_token, agency_task_id)
    return json.loads(result_str)


def _do_submit(test_app, test_token, agency_task_id, callback_jwt, output,
               score=None, task_completed=None, score_type=None):
    base_url = "http://testserver"
    patches = _patch_httpx(test_app["client"])
    with patches[0], patches[1], patches[2], patches[3]:
        result_str = _tool_agency_submit_evaluation(
            base_url, test_token, agency_task_id, callback_jwt, output,
            score=score, task_completed=task_completed, score_type=score_type,
        )
    return json.loads(result_str)


def _do_status(test_app, test_token, project_id=None):
    base_url = "http://testserver"
    patches = _patch_httpx(test_app["client"])
    with patches[0], patches[1], patches[2], patches[3]:
        result_str = _tool_agency_status(base_url, test_token, project_id=project_id)
    return json.loads(result_str)


# ---------------------------------------------------------------------------
# Test 1: assign via MCP handler returns rendered_prompt
# ---------------------------------------------------------------------------


def test_mcp_assign_returns_rendered_prompt(test_app, test_token, test_project_id):
    """assign via MCP handler → response includes rendered_prompt in agents map."""
    result = _do_assign(test_app, test_token, test_project_id, [
        {"external_id": "e2e-t1", "description": "analyse data and produce a summary report"},
    ])

    assert result["status"] == "ok", f"Unexpected error: {result}"
    assert "assignments" in result
    assert "e2e-t1" in result["assignments"]

    assignment = result["assignments"]["e2e-t1"]
    assert "agency_task_id" in assignment
    assert "agent_hash" in assignment

    agents = result.get("agents", {})
    agent_hash = assignment["agent_hash"]
    assert agent_hash in agents, "agent_hash from assignment must index into agents map"

    agent_def = agents[agent_hash]
    assert "rendered_prompt" in agent_def
    assert len(agent_def["rendered_prompt"]) > 0, "rendered_prompt must not be empty"

    # MCP-specific annotations
    assert "agency_task_id_note" in assignment
    assert "next_step" in result


# ---------------------------------------------------------------------------
# Test 2: status without project_id returns compact format (no active_tasks)
# ---------------------------------------------------------------------------


def test_mcp_status_compact_summary(test_app, test_token, test_project_id):
    """status without project_id strips active_tasks from each project (compact format)."""
    # First assign a task so there is something to show
    _do_assign(test_app, test_token, test_project_id, [
        {"external_id": "status-t1", "description": "review code quality"},
    ])

    result = _do_status(test_app, test_token)  # no project_id — compact mode

    assert result.get("status") != "error", f"Status call failed: {result}"
    assert "next_step" in result

    # Compact mode: active_tasks should be stripped from all projects
    for proj in result.get("projects", []):
        assert "active_tasks" not in proj, (
            f"active_tasks should be absent in compact status; "
            f"found in project {proj.get('id')}"
        )


# ---------------------------------------------------------------------------
# Test 3: evaluator returns both rendered_prompt and evaluator_prompt fields
# ---------------------------------------------------------------------------


def test_mcp_evaluator_returns_both_prompt_fields(test_app, test_token, test_project_id):
    """evaluator response has both rendered_prompt (canonical) and evaluator_prompt (Issue 9 alias).

    client.py maps the API's rendered_prompt to the evaluator_prompt key. The API
    route (EvaluatorResponse model) also exposes evaluator_prompt as a computed alias.
    This test confirms both fields are accessible in the round-trip.
    """
    # Assign first
    assign_result = _do_assign(test_app, test_token, test_project_id, [
        {"external_id": "eval-t1", "description": "evaluate code review output for completeness"},
    ])
    assert assign_result["status"] == "ok"
    agency_task_id = assign_result["assignments"]["eval-t1"]["agency_task_id"]

    # Get evaluator via MCP handler
    eval_result = _do_evaluator(test_app, test_token, agency_task_id)

    assert eval_result["status"] == "ok", f"Evaluator failed: {eval_result}"

    # client.py maps rendered_prompt → evaluator_prompt in _evaluator_success()
    assert "evaluator_prompt" in eval_result, "evaluator_prompt field must be present"
    assert len(eval_result["evaluator_prompt"]) > 0

    # The callback JWT must also be present
    assert "callback_jwt" in eval_result
    assert len(eval_result["callback_jwt"]) > 0

    # agency_task_id echoed back
    assert eval_result["agency_task_id"] == agency_task_id

    # The MCP handler adds next_step
    assert "next_step" in eval_result
    assert "agency_submit_evaluation" in eval_result["next_step"]

    # Verify the underlying API response also carries rendered_prompt as an alias:
    # call /tasks/{id}/evaluator directly and confirm both fields in API response
    auth = _auth_headers(test_token)
    direct_resp = test_app["client"].get(
        f"/tasks/{agency_task_id}/evaluator", headers=auth
    )
    assert direct_resp.status_code == 200
    api_data = direct_resp.json()
    assert "rendered_prompt" in api_data
    assert "evaluator_prompt" in api_data  # computed_field alias on EvaluatorResponse
    assert api_data["rendered_prompt"] == api_data["evaluator_prompt"]


# ---------------------------------------------------------------------------
# Test 4: get_task returns state field
# ---------------------------------------------------------------------------


def test_mcp_get_task_returns_state(test_app, test_token, test_project_id):
    """get_task returns state field set to 'assigned' immediately after assign."""
    assign_result = _do_assign(test_app, test_token, test_project_id, [
        {"external_id": "gt-t1", "description": "write unit tests for a sorting algorithm"},
    ])
    assert assign_result["status"] == "ok"
    agency_task_id = assign_result["assignments"]["gt-t1"]["agency_task_id"]

    get_result = _do_get_task(test_app, test_token, agency_task_id)

    assert get_result["status"] == "ok", f"get_task failed: {get_result}"
    assert "state" in get_result
    assert get_result["state"] == "assigned"
    assert get_result["agency_task_id"] == agency_task_id
    assert "rendered_prompt" in get_result
    assert len(get_result["rendered_prompt"]) > 0
    assert "next_step" in get_result
    # next_step for assigned state should mention evaluation
    assert "evaluated" in get_result["next_step"].lower() or "evaluator" in get_result["next_step"].lower()


# ---------------------------------------------------------------------------
# Test 5: submit evaluation returns ok status
# ---------------------------------------------------------------------------


def test_mcp_submit_evaluation(test_app, test_token, test_project_id):
    """Full loop: assign → evaluator → submit returns ok with content_hash."""
    # Step 1: assign
    assign_result = _do_assign(test_app, test_token, test_project_id, [
        {"external_id": "sub-t1", "description": "review a technical document for accuracy"},
    ])
    assert assign_result["status"] == "ok"
    agency_task_id = assign_result["assignments"]["sub-t1"]["agency_task_id"]

    # Step 2: get evaluator prompt + callback JWT
    eval_result = _do_evaluator(test_app, test_token, agency_task_id)
    assert eval_result["status"] == "ok"
    callback_jwt = eval_result["callback_jwt"]

    # Step 3: submit evaluation
    output = "The document is accurate and well-structured. No factual errors found."
    submit_result = _do_submit(
        test_app, test_token, agency_task_id, callback_jwt, output,
        score=90, task_completed=True, score_type="percentage",
    )

    assert submit_result["status"] == "ok", f"Submit failed: {submit_result}"
    assert "content_hash" in submit_result
    assert len(submit_result["content_hash"]) == 64  # sha256 hex

    # MCP-specific annotation
    assert "next_step" in submit_result

    # Step 4: confirm state is evaluation_received via get_task
    get_result = _do_get_task(test_app, test_token, agency_task_id)
    assert get_result["status"] == "ok"
    assert get_result["state"] == "evaluation_received"


# ---------------------------------------------------------------------------
# Test 6: assign with empty tasks returns structured error (validation, no HTTP call)
# ---------------------------------------------------------------------------


def test_mcp_assign_empty_tasks_returns_validation_error(
    test_app, test_token, test_project_id
):
    """assign with empty tasks array returns structured validation error before HTTP."""
    result = _do_assign(test_app, test_token, test_project_id, [])

    assert result["status"] == "error"
    assert result["error_type"] == "validation"
    assert result["code"] == 400
    assert "tasks" in result["message"].lower() or "empty" in result["message"].lower()
    assert result["cause"] is not None
    assert result["fix"] is not None


# ---------------------------------------------------------------------------
# Test 7: get_task for unknown ID returns not_found error
# ---------------------------------------------------------------------------


def test_mcp_get_task_unknown_id_returns_not_found(test_app, test_token):
    """get_task with an unknown agency_task_id returns a structured not_found error."""
    result = _do_get_task(test_app, test_token, "00000000-0000-0000-0000-000000000000")

    assert result["status"] == "error"
    assert result["error_type"] == "not_found"
    assert result["code"] == 404
