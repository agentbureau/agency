"""Shared HTTP client for Agency API.

Provides base URL resolution, token resolution, error classification,
and four main API functions used by both MCP tools and CLI commands:
  - assign
  - get_evaluator
  - submit_evaluation
  - get_task
"""
import glob as globmod
import hashlib
import json
import os
import sys
import time
import tomllib
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_RETRY_DELAY = 2  # seconds
DEFAULT_TIMEOUT = 30
API_VERSION_HEADER = "X-Agency-API-Version"
API_VERSION = "1"


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _classify_error(status_code: Optional[int], exception=None) -> str:
    """Single authority for error_type strings."""
    if exception is not None:
        if isinstance(exception, httpx.ConnectError):
            return "transient"
        if isinstance(exception, httpx.TimeoutException):
            return "transient"
        return "permanent"
    if status_code == 503:
        return "transient"
    if status_code == 401:
        return "auth"
    if status_code == 404:
        return "not_found"
    if status_code in (400, 422, 409):
        return "validation"
    return "permanent"


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _make_error(
    error_type: str,
    code: Optional[int],
    message: str,
    cause: Optional[str] = None,
    fix: Optional[str] = None,
) -> dict:
    return {
        "status": "error",
        "error_type": error_type,
        "code": code,
        "message": message,
        "cause": cause,
        "fix": fix,
    }


def _assign_success(task_ids: list, assignments: dict, agents: dict, **extra) -> dict:
    result = {
        "status": "ok",
        "task_ids": task_ids,
        "assignments": assignments,
        "agents": agents,
    }
    result.update(extra)
    return result


def _evaluator_success(
    evaluator_prompt: str, callback_jwt: str, agency_task_id: str
) -> dict:
    return {
        "status": "ok",
        "evaluator_prompt": evaluator_prompt,
        "callback_jwt": callback_jwt,
        "agency_task_id": agency_task_id,
    }


def _submit_success(content_hash: str, hash_mismatch: bool = False) -> dict:
    d: dict = {"status": "ok", "content_hash": content_hash}
    if hash_mismatch:
        d["hash_mismatch"] = True
    return d


def _get_task_success(
    agency_task_id: str,
    external_id: Optional[str],
    project_id: Optional[str],
    state: Optional[str],
    agent_hash: Optional[str],
    rendered_prompt: Optional[str],
    rendering_warnings: Optional[list],
    created_at: Optional[str],
    evaluation: Optional[dict],
) -> dict:
    return {
        "status": "ok",
        "agency_task_id": agency_task_id,
        "external_id": external_id,
        "project_id": project_id,
        "state": state,
        "agent_hash": agent_hash,
        "rendered_prompt": rendered_prompt,
        "rendering_warnings": rendering_warnings,
        "created_at": created_at,
        "evaluation": evaluation,
    }


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


def _call_with_retry(fn, *args, **kwargs):
    """Call fn, retry once after MCP_RETRY_DELAY on ConnectError only."""
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError:
        time.sleep(MCP_RETRY_DELAY)
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _get_config_file_path() -> str:
    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    return os.path.join(state_dir, "agency.toml")


def _read_toml_config() -> dict:
    path = _get_config_file_path()
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def resolve_base_url() -> str:
    """Derive Agency server base URL.

    Reads AGENCY_STATE_DIR env (default ~/.agency) → agency.toml → [server]
    host/port. Falls back to http://127.0.0.1:8000.
    """
    cfg = _read_toml_config()
    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = cfg.get("server", {}).get("port", 8000)
    return f"http://{host}:{port}"


def resolve_token(client_id: str) -> str:
    """Resolve bearer token for the given client_id.

    Resolution order:
      - If client_id is "mcp" and AGENCY_TOKEN_FILE env var is set → read that path
      - Otherwise → read ~/.agency-{client_id}-token

    Raises FileNotFoundError if the token file is missing (with a helpful message
    listing available client IDs). This is the only function in this module that raises.

    Prints a warning to stderr if the token file has group/world-readable permissions.
    """
    if client_id == "mcp" and os.environ.get("AGENCY_TOKEN_FILE"):
        path = os.environ["AGENCY_TOKEN_FILE"]
    else:
        path = os.path.expanduser(f"~/.agency-{client_id}-token")

    try:
        with open(path) as f:
            token = f.read().strip()
    except FileNotFoundError:
        # List available client IDs from token files on disk
        pattern = os.path.expanduser("~/.agency-*-token")
        available = globmod.glob(pattern)
        client_ids = []
        for p in available:
            basename = os.path.basename(p)
            # strip leading ".agency-" and trailing "-token"
            inner = basename[len(".agency-"):-len("-token")]
            if inner:
                client_ids.append(inner)
        if client_ids:
            hint = f"Available client IDs: {', '.join(sorted(client_ids))}"
        else:
            hint = (
                f"No token files found. Run: agency token create "
                f"--client-id {client_id} > {path}"
            )
        raise FileNotFoundError(
            f"Token file not found at {path}. {hint}"
        )

    # Warn on permissive file permissions
    try:
        mode = os.stat(path).st_mode & 0o077
        if mode != 0:
            print(
                f"Warning: token file {path} has group/world-readable permissions "
                f"(mode {oct(mode)}). Run: chmod 600 {path}",
                file=sys.stderr,
            )
    except Exception:
        pass

    return token


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


def assign(
    base_url: str,
    token: str,
    project_id: str,
    tasks: list,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST /projects/{project_id}/assign — compose agents for tasks.

    Returns dict with status "ok" and task_ids/assignments/agents on success,
    or status "error" on failure.
    """
    url = f"{base_url}/projects/{project_id}/assign"
    headers = {
        "Authorization": f"Bearer {token}",
        API_VERSION_HEADER: API_VERSION,
    }
    try:
        resp = _call_with_retry(
            httpx.post,
            url,
            json={"tasks": tasks},
            headers=headers,
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            task_ids = [
                {
                    "external_id": ext_id,
                    "agency_task_id": assignment["agency_task_id"],
                    "agent_hash": assignment["agent_hash"],
                }
                for ext_id, assignment in data.get("assignments", {}).items()
            ]
            extra = {k: v for k, v in data.items()
                     if k not in ("assignments", "agents")}
            return _assign_success(
                task_ids=task_ids,
                assignments=data.get("assignments", {}),
                agents=data.get("agents", {}),
                **extra,
            )
        if resp.status_code == 503:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message="Agency has no primitives loaded.",
                cause="The primitive store is empty — agent composition requires at least one primitive.",
                fix="Run: agency primitives update",
            )
        if resp.status_code == 404:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=f"Project ID not found: {project_id}.",
                cause="No project with this ID exists in the database.",
                fix="List available projects with agency_list_projects or check agency.toml [project] default_id.",
            )
        return _make_error(
            error_type=_classify_error(resp.status_code),
            code=resp.status_code,
            message=resp.text,
        )
    except httpx.ConnectError as e:
        cfg_file = _get_config_file_path()
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Cannot reach Agency server at {base_url}.",
            cause="The server is not running, or is running on a different host/port.",
            fix=f"Start the server: agency serve. Verify: curl {base_url}/health. Config: {cfg_file}",
        )
    except httpx.TimeoutException as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Request timed out after {timeout}s.",
            cause="The server did not respond within the timeout period.",
            fix="Retry, or increase the timeout: --timeout 60",
        )
    except Exception as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=str(e),
            cause=None,
            fix=None,
        )


def get_evaluator(
    base_url: str,
    token: str,
    task_id: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """GET /tasks/{task_id}/evaluator — get evaluator prompt and callback JWT.

    Returns dict with status "ok" on success, or status "error" on failure.
    """
    url = f"{base_url}/tasks/{task_id}/evaluator"
    headers = {
        "Authorization": f"Bearer {token}",
        API_VERSION_HEADER: API_VERSION,
    }
    try:
        resp = _call_with_retry(
            httpx.get,
            url,
            headers=headers,
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            return _evaluator_success(
                evaluator_prompt=data["rendered_prompt"],
                callback_jwt=data["callback_jwt"],
                agency_task_id=task_id,
            )
        if resp.status_code == 404:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=f"Task not found for agency_task_id: {task_id}.",
                cause=(
                    "The ID does not match any task. Most common mistake: "
                    "passing your external_id instead of the agency_task_id "
                    "returned by agency_assign."
                ),
                fix="Check the agency_assign response — use the agency_task_id field, not external_id.",
            )
        if resp.status_code == 422:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=f"No evaluator assigned for task {task_id}.",
                cause="The agent composition for this task did not include an evaluator component.",
                fix=(
                    "This task cannot be evaluated through Agency. "
                    "Proceed without evaluation, or re-assign with a different task description."
                ),
            )
        return _make_error(
            error_type=_classify_error(resp.status_code),
            code=resp.status_code,
            message=resp.text,
        )
    except httpx.ConnectError as e:
        cfg_file = _get_config_file_path()
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Cannot reach Agency server at {base_url}.",
            cause="The server is not running, or is running on a different host/port.",
            fix=f"Start the server: agency serve. Verify: curl {base_url}/health. Config: {cfg_file}",
        )
    except httpx.TimeoutException as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Request timed out after {timeout}s.",
            cause="The server did not respond within the timeout period.",
            fix="Retry, or increase the timeout: --timeout 60",
        )
    except Exception as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=str(e),
            cause=None,
            fix=None,
        )


def submit_evaluation(
    base_url: str,
    token: str,
    task_id: str,
    callback_jwt: str,
    output: str,
    score: Optional[int] = None,
    task_completed: Optional[bool] = None,
    score_type: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST /tasks/{task_id}/evaluation — submit evaluation with structured metadata.

    Computes content hash per §1.1.4 spec: hash body = output + optional fields,
    json-serialised with ensure_ascii=False and compact separators, utf-8 encoded,
    sha256 hexdigest. Sends body with callback_jwt appended (as bytes via content=).

    Returns dict with status "ok" on success, or status "error" on failure.
    Hash mismatch between local and server is flagged in the success response.
    """
    # Build hash body (WITHOUT callback_jwt — server hashes without it)
    hash_body: dict = {"output": output}
    if score is not None:
        hash_body["score"] = score
    if task_completed is not None:
        hash_body["task_completed"] = task_completed
    if score_type is not None:
        hash_body["score_type"] = score_type

    hash_bytes = json.dumps(
        hash_body, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    local_hash = hashlib.sha256(hash_bytes).hexdigest()

    # Send body WITH callback_jwt for server-side extraction
    send_body = {**hash_body, "callback_jwt": callback_jwt}
    body_bytes = json.dumps(
        send_body, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    url = f"{base_url}/tasks/{task_id}/evaluation"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        API_VERSION_HEADER: API_VERSION,
    }
    try:
        resp = _call_with_retry(
            httpx.post,
            url,
            content=body_bytes,
            headers=headers,
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            server_data = resp.json()
            server_hash = server_data.get("content_hash", local_hash)
            hash_mismatch = server_hash != local_hash
            return _submit_success(
                content_hash=server_hash,
                hash_mismatch=hash_mismatch,
            )
        if resp.status_code == 404:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=f"Task not found for agency_task_id: {task_id}.",
                cause="The ID does not match any task. Most common mistake: passing external_id instead of agency_task_id.",
                fix="Check the agency_assign response — use the agency_task_id field.",
            )
        if resp.status_code == 401:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message="Callback JWT is invalid, expired, or already used.",
                cause=(
                    "Each callback_jwt from agency_evaluator is single-use. "
                    "This JWT may have expired (24h TTL) or been consumed by a prior submission."
                ),
                fix="Call agency_evaluator with agency_task_id to get a new callback_jwt, then call agency_submit_evaluation again.",
            )
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail", {})
                msg = detail.get("message", resp.text) if isinstance(detail, dict) else resp.text
            except Exception:
                msg = resp.text
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=msg,
            )
        return _make_error(
            error_type=_classify_error(resp.status_code),
            code=resp.status_code,
            message=resp.text,
        )
    except httpx.ConnectError as e:
        cfg_file = _get_config_file_path()
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Cannot reach Agency server at {base_url}.",
            cause="The server is not running, or is running on a different host/port.",
            fix=f"Start the server: agency serve. Verify: curl {base_url}/health. Config: {cfg_file}",
        )
    except httpx.TimeoutException as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Request timed out after {timeout}s.",
            cause="The server did not respond within the timeout period.",
            fix="Retry, or increase the timeout: --timeout 60",
        )
    except Exception as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=str(e),
            cause=None,
            fix=None,
        )


def get_task(
    base_url: str,
    token: str,
    task_id: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """GET /tasks/{task_id} — retrieve full task record.

    Returns dict with status "ok" on success, or status "error" on failure.
    """
    url = f"{base_url}/tasks/{task_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        API_VERSION_HEADER: API_VERSION,
    }
    try:
        resp = _call_with_retry(
            httpx.get,
            url,
            headers=headers,
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            return _get_task_success(
                agency_task_id=task_id,
                external_id=data.get("external_id"),
                project_id=data.get("project_id"),
                state=data.get("state"),
                agent_hash=data.get("agent_hash"),
                rendered_prompt=data.get("rendered_prompt"),
                rendering_warnings=data.get("rendering_warnings"),
                created_at=data.get("created_at"),
                evaluation=data.get("evaluation"),
            )
        if resp.status_code == 404:
            return _make_error(
                error_type=_classify_error(resp.status_code),
                code=resp.status_code,
                message=f"Task not found for agency_task_id: {task_id}.",
                cause="The ID does not match any task.",
                fix="Check the agency_task_id from the agency_assign response.",
            )
        return _make_error(
            error_type=_classify_error(resp.status_code),
            code=resp.status_code,
            message=resp.text,
        )
    except httpx.ConnectError as e:
        cfg_file = _get_config_file_path()
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Cannot reach Agency server at {base_url}.",
            cause="The server is not running, or is running on a different host/port.",
            fix=f"Start the server: agency serve. Verify: curl {base_url}/health. Config: {cfg_file}",
        )
    except httpx.TimeoutException as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=f"Request timed out after {timeout}s.",
            cause="The server did not respond within the timeout period.",
            fix="Retry, or increase the timeout: --timeout 60",
        )
    except Exception as e:
        return _make_error(
            error_type=_classify_error(None, exception=e),
            code=None,
            message=str(e),
            cause=None,
            fix=None,
        )
