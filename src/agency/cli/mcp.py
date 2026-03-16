"""Agency MCP server — stdio transport for Claude Code.

Exposes tools for the assign → execute → evaluate loop:
  - agency_assign: compose agents for tasks, return prompts
  - agency_evaluator: get evaluator prompt + callback JWT
  - agency_submit_evaluation: submit evaluation with structured metadata

Discovery and status tools:
  - agency_list_projects: list all projects with default identification
  - agency_create_project: create a new project
  - agency_status: instance status, task progress, primitive health
"""
import asyncio
import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Optional

import click
import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_RETRY_DELAY = 2  # seconds
MCP_SERVER_NAME = "agency"
PER_REPO_CONFIG_FILE = ".agency-project"
AGENCY_TASK_ID_NOTE = (
    "Use this agency_task_id (not your external_id) when calling "
    "agency_evaluator and agency_submit_evaluation."
)
NEXT_STEP_ASSIGN = (
    "You must now execute each task yourself. For each task: "
    "(1) read the rendered_prompt from the agents map using the agent_hash; "
    "(2) adopt that prompt as your operating instructions; "
    "(3) do the work. When all tasks are complete, call agency_evaluator "
    "with each task's agency_task_id to get the evaluation prompt."
)
NEXT_STEP_EVALUATOR = (
    "Evaluate the output you produced for this task by following the "
    "evaluator_prompt instructions. Then call agency_submit_evaluation with: "
    "agency_task_id, callback_jwt, output (your evaluation text), and "
    "optionally score, task_completed, and score_type."
)
NEXT_STEP_SUBMIT = (
    "Evaluation recorded. The content_hash confirms what Agency received. "
    "The assign-execute-evaluate loop for this task is complete."
)
NEXT_STEP_LIST_PROJECTS = (
    "Pass a project_id to agency_assign, or omit it to use the default project."
)
NEXT_STEP_LIST_PROJECTS_EMPTY = (
    "Create a project first with agency_create_project or: agency project create"
)
NEXT_STEP_CREATE_PROJECT = (
    "This project is now available for task assignment. Pass project_id to "
    "agency_assign, or use it as the default by including set_as_default: true."
)
NEXT_STEP_STATUS_ASSIGNED = (
    "{n} tasks are assigned but not yet evaluated. Execute them using the "
    "rendered_prompt from agency_assign, then call agency_evaluator for each."
)
NEXT_STEP_STATUS_DEFAULT = (
    "To assign tasks, call agency_assign. To check on a specific task's "
    "evaluation, call agency_evaluator with the agency_task_id."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_toml_config() -> dict:
    """Read agency.toml from AGENCY_STATE_DIR. Returns empty dict on error."""
    import tomllib

    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    path = os.path.join(state_dir, "agency.toml")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _get_config_file_path() -> str:
    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    return os.path.join(state_dir, "agency.toml")


def _find_repo_config() -> Optional[str]:
    """Search CWD and parents for .agency-project file. Returns file path or None."""
    cwd = pathlib.Path.cwd()
    for directory in [cwd] + list(cwd.parents):
        candidate = directory / PER_REPO_CONFIG_FILE
        if candidate.exists():
            return str(candidate)
    return None


def _resolve_project_id(project_id: Optional[str]) -> Optional[str]:
    """Priority: 1. explicit arg, 2. .agency-project, 3. AGENCY_PROJECT_ID env,
    4. agency.toml [project] default_id, 5. None."""
    if project_id is not None:
        return project_id
    repo_config = _find_repo_config()
    if repo_config:
        try:
            with open(repo_config) as f:
                val = f.read().strip()
            if val:
                return val
        except Exception:
            pass
    env_val = os.environ.get("AGENCY_PROJECT_ID")
    if env_val:
        return env_val
    cfg = _read_toml_config()
    return cfg.get("project", {}).get("default_id")


def _read_mcp_token() -> str:
    """Read bearer token from AGENCY_TOKEN_FILE (default: ~/.agency-mcp-token).
    Exits with code 1 if the file is missing or empty."""
    token_file = os.environ.get(
        "AGENCY_TOKEN_FILE", os.path.expanduser("~/.agency-mcp-token")
    )
    try:
        with open(token_file) as f:
            token = f.read().strip()
    except FileNotFoundError:
        token = ""
    if not token:
        print(
            f"Error: token file not found at {token_file}. "
            f"Run 'agency token create --client-id mcp > {token_file}' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def _get_agency_url() -> str:
    """Derive Agency server URL from agency.toml [server] host/port."""
    cfg = _read_toml_config()
    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = cfg.get("server", {}).get("port", 8000)
    return f"http://{host}:{port}"


def _check_health(base_url: str) -> bool:
    """GET /health, return True if 200."""
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _make_error(code: Optional[int], message: str, cause: Optional[str] = None, fix: Optional[str] = None) -> dict:
    return {"status": "error", "code": code, "message": message, "cause": cause, "fix": fix}


def _call_with_retry(fn, *args, **kwargs):
    """Call fn, retry once after MCP_RETRY_DELAY on connection error."""
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError:
        time.sleep(MCP_RETRY_DELAY)
        return fn(*args, **kwargs)


def _connection_error(base_url: str) -> str:
    cfg_file = _get_config_file_path()
    return json.dumps(_make_error(
        None,
        f"Cannot reach Agency server at {base_url}.",
        cause="The server is not running, or is running on a different host/port.",
        fix=f"Start the server: agency serve. Verify: curl {base_url}/health. Config: {cfg_file}",
    ))


def _make_success(**kwargs) -> dict:
    return {"status": "ok", **kwargs}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _tool_agency_assign(
    base_url: str, token: str, project_id: Optional[str], tasks: list
) -> str:
    """POST /projects/{id}/assign — compose agents for tasks."""
    resolved = _resolve_project_id(project_id)
    if resolved is None:
        return json.dumps(_make_error(
            None,
            "No project ID provided.",
            cause=(
                "No project_id argument, no .agency-project file, "
                "no AGENCY_PROJECT_ID env var, and no default_id in agency.toml."
            ),
            fix=(
                "Pass project_id, create .agency-project in your repo root, "
                "set AGENCY_PROJECT_ID, or configure [project] default_id in agency.toml."
            ),
        ))
    if not tasks:
        return json.dumps(_make_error(
            400,
            "The tasks array is empty.",
            cause="No task objects provided in the tasks parameter.",
            fix="Provide at least one task with external_id and description.",
        ))
    try:
        resp = _call_with_retry(
            httpx.post,
            f"{base_url}/projects/{resolved}/assign",
            json={"tasks": tasks},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            for _ext_id, assignment in data.get("assignments", {}).items():
                assignment["agency_task_id_note"] = AGENCY_TASK_ID_NOTE
            data["next_step"] = NEXT_STEP_ASSIGN
            return json.dumps(data)
        if resp.status_code == 503:
            return json.dumps(_make_error(
                503,
                "Agency has no primitives loaded.",
                cause="The primitive store is empty — agent composition requires at least one primitive.",
                fix="Run: agency primitives update",
            ))
        if resp.status_code == 404:
            return json.dumps(_make_error(
                404,
                f"Project ID not found: {resolved}.",
                cause="No project with this ID exists in the database.",
                fix="List available projects with agency_list_projects or check agency.toml [project] default_id.",
            ))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _tool_agency_evaluator(
    base_url: str, token: str, agency_task_id: str
) -> str:
    """GET /tasks/{id}/evaluator — get evaluator prompt and callback JWT."""
    try:
        resp = _call_with_retry(
            httpx.get,
            f"{base_url}/tasks/{agency_task_id}/evaluator",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return json.dumps({
                "evaluator_prompt": data["rendered_prompt"],
                "callback_jwt": data["callback_jwt"],
                "agency_task_id": agency_task_id,
                "next_step": NEXT_STEP_EVALUATOR,
            })
        if resp.status_code == 404:
            return json.dumps(_make_error(
                404,
                f"Task not found for agency_task_id: {agency_task_id}.",
                cause=(
                    "The ID does not match any task. Most common mistake: "
                    "passing your external_id instead of the agency_task_id "
                    "returned by agency_assign."
                ),
                fix="Check the agency_assign response — use the agency_task_id field, not external_id.",
            ))
        if resp.status_code == 422:
            return json.dumps(_make_error(
                422,
                f"No evaluator assigned for task {agency_task_id}.",
                cause="The agent composition for this task did not include an evaluator component.",
                fix=(
                    "This task cannot be evaluated through Agency. "
                    "Proceed without evaluation, or re-assign with a different task description."
                ),
            ))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _tool_agency_submit_evaluation(
    base_url: str,
    token: str,
    agency_task_id: str,
    callback_jwt: str,
    output: str,
    score: Optional[int] = None,
    task_completed: Optional[bool] = None,
    score_type: Optional[str] = None,
) -> str:
    """POST /tasks/{id}/evaluation — submit evaluation with dual JWT auth."""
    # Hash body WITHOUT callback_jwt (server hashes without it)
    hash_body: dict = {"output": output}
    if score is not None:
        hash_body["score"] = score
    if task_completed is not None:
        hash_body["task_completed"] = task_completed
    if score_type is not None:
        hash_body["score_type"] = score_type
    hash_bytes = json.dumps(hash_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    local_hash = hashlib.sha256(hash_bytes).hexdigest()

    # Send body WITH callback_jwt for server-side extraction
    send_body = {**hash_body, "callback_jwt": callback_jwt}
    body_bytes = json.dumps(send_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    try:
        resp = _call_with_retry(
            httpx.post,
            f"{base_url}/tasks/{agency_task_id}/evaluation",
            content=body_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            server_data = resp.json()
            return json.dumps({
                "status": "accepted",
                "content_hash": server_data.get("content_hash", local_hash),
                "next_step": NEXT_STEP_SUBMIT,
            })
        if resp.status_code == 404:
            return json.dumps(_make_error(
                404,
                f"Task not found for agency_task_id: {agency_task_id}.",
                cause="The ID does not match any task. Most common mistake: passing external_id instead of agency_task_id.",
                fix="Check the agency_assign response — use the agency_task_id field.",
            ))
        if resp.status_code == 401:
            return json.dumps(_make_error(
                401,
                "Callback JWT is invalid, expired, or already used.",
                cause=(
                    "Each callback_jwt from agency_evaluator is single-use. "
                    "This JWT may have expired (24h TTL) or been consumed by a prior submission."
                ),
                fix="Call agency_evaluator with agency_task_id to get a new callback_jwt, then call agency_submit_evaluation again.",
            ))
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail", {})
                msg = detail.get("message", resp.text) if isinstance(detail, dict) else resp.text
            except Exception:
                msg = resp.text
            return json.dumps(_make_error(422, msg))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _detect_default_source() -> str:
    """Determine how the default project ID is currently resolved."""
    repo_config = _find_repo_config()
    if repo_config:
        try:
            with open(repo_config) as f:
                val = f.read().strip()
            if val:
                return "repo_config"
        except Exception:
            pass
    if os.environ.get("AGENCY_PROJECT_ID"):
        return "env_var"
    cfg = _read_toml_config()
    if cfg.get("project", {}).get("default_id"):
        return "toml_config"
    return "none"


def _tool_agency_list_projects(base_url: str, token: str) -> str:
    """GET /projects — list all projects with default identification."""
    try:
        resp = _call_with_retry(
            httpx.get,
            f"{base_url}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            projects = data.get("projects", [])
            default_id = data.get("default_project_id")
            default_source = _detect_default_source()

            enriched = []
            for p in projects:
                enriched.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "is_default": p.get("id") == default_id,
                    "created_at": p.get("created_at", ""),
                })

            if not projects:
                next_step = NEXT_STEP_LIST_PROJECTS_EMPTY
            else:
                next_step = NEXT_STEP_LIST_PROJECTS

            return json.dumps({
                "projects": enriched,
                "default_project_id": default_id,
                "default_source": default_source,
                "next_step": next_step,
            })
        if resp.status_code == 401:
            return json.dumps(_make_error(
                401,
                "Authentication failed.",
                cause="Invalid or revoked token.",
                fix=f"Regenerate: agency token create --client-id mcp > {os.path.expanduser('~/.agency-mcp-token')}",
            ))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _write_toml_default_id(project_id: str) -> None:
    """Update agency.toml [project] default_id."""
    import tomllib
    import tomli_w

    config_path = _get_config_file_path()
    try:
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        cfg = {}

    if "project" not in cfg:
        cfg["project"] = {}
    cfg["project"]["default_id"] = project_id

    with open(config_path, "wb") as f:
        tomli_w.dump(cfg, f)


def _tool_agency_create_project(
    base_url: str,
    token: str,
    name: str,
    description: Optional[str] = None,
    contact_email: Optional[str] = None,
    oversight_preference: Optional[str] = None,
    error_notification_timeout: Optional[int] = None,
    attribution: Optional[bool] = None,
    set_as_default: bool = False,
) -> str:
    """POST /projects — create a new project."""
    if not name or not name.strip():
        return json.dumps(_make_error(
            400,
            "Project name is required.",
            cause="The name parameter is missing or empty.",
            fix="Pass a non-empty name string to agency_create_project.",
        ))

    body: dict = {"name": name.strip()}
    if description is not None:
        body["description"] = description
    if contact_email is not None:
        body["contact_email"] = contact_email
    if oversight_preference is not None:
        body["oversight_preference"] = oversight_preference
    if error_notification_timeout is not None:
        body["error_notification_timeout"] = error_notification_timeout
    if attribution is not None:
        body["attribution"] = attribution

    try:
        resp = _call_with_retry(
            httpx.post,
            f"{base_url}/projects",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            project_id = data.get("id")

            if set_as_default and project_id:
                try:
                    _write_toml_default_id(project_id)
                except Exception:
                    pass  # Non-fatal; project was still created

            # Build settings_applied from response data
            settings_applied = {}
            for field in ("contact_email", "oversight_preference",
                          "error_notification_timeout", "attribution"):
                val = data.get(field)
                if val is not None:
                    source = "explicit" if field in body else "inherited"
                    settings_applied[field] = {"value": val, "source": source}

            return json.dumps({
                "project_id": project_id,
                "name": data.get("name"),
                "is_default": set_as_default,
                "settings_applied": settings_applied,
                "next_step": NEXT_STEP_CREATE_PROJECT,
            })
        if resp.status_code == 409:
            try:
                detail = resp.json().get("detail", {})
                existing_id = detail.get("existing_project_id", "") if isinstance(detail, dict) else ""
                proj_name = name.strip()
            except Exception:
                existing_id = ""
                proj_name = name.strip()
            return json.dumps(_make_error(
                409,
                f'A project named "{proj_name}" already exists (id: {existing_id}).',
                cause="Project names must be unique (case-insensitive).",
                fix="Use a different name, or pass the existing project's id to agency_assign.",
            ))
        if resp.status_code == 400:
            try:
                detail = resp.json().get("detail", {})
                msg = detail.get("message", resp.text) if isinstance(detail, dict) else resp.text
            except Exception:
                msg = resp.text
            return json.dumps(_make_error(400, msg))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _tool_agency_status(
    base_url: str, token: str, project_id: Optional[str] = None
) -> str:
    """GET /status — instance status with task progress and primitive health."""
    url = f"{base_url}/status"
    if project_id:
        url = f"{url}?project_id={project_id}"
    try:
        resp = _call_with_retry(
            httpx.get,
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()

            # Count assigned tasks across all projects
            assigned_count = 0
            for proj in data.get("projects", []):
                ts = proj.get("task_summary", {})
                assigned_count += ts.get("assigned", 0)

            if assigned_count > 0:
                next_step = NEXT_STEP_STATUS_ASSIGNED.format(n=assigned_count)
            else:
                next_step = NEXT_STEP_STATUS_DEFAULT

            data["next_step"] = next_step
            return json.dumps(data)
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.ConnectError:
        return _connection_error(base_url)
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


async def _run_mcp_server():
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types

    base_url = _get_agency_url()
    token = _read_mcp_token()

    if not _check_health(base_url):
        print(
            f"Agency server not responding at {base_url}. Start it with: agency serve",
            file=sys.stderr,
        )
        # Continue startup — server may come up later

    server = Server(MCP_SERVER_NAME)

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="agency_assign",
                description=(
                    "Compose AI agents for a set of tasks and return their prompts. "
                    "Agency is a prompt composer — it does NOT execute tasks. You (the "
                    "requester) must execute each task yourself using the returned "
                    "rendered_prompt as your operating instructions. After execution, "
                    "call agency_evaluator for each task to get the evaluation prompt. "
                    "Full caller protocol: https://github.com/agentbureau/agency/blob/"
                    "main/docs/integrations/caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": (
                                "Project ID (optional). Falls back to: "
                                ".agency-project > AGENCY_PROJECT_ID env var > "
                                "agency.toml [project] default_id."
                            ),
                        },
                        "tasks": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "external_id": {
                                        "type": "string",
                                        "description": "Your identifier for this task. Used as a key in the response.",
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "What the task requires. Agency uses this to select primitives and compose the agent.",
                                    },
                                    "skills": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional skill tags to influence primitive selection.",
                                    },
                                    "deliverables": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional list of expected outputs.",
                                    },
                                },
                                "required": ["external_id", "description"],
                            },
                            "description": "List of task objects to assign",
                        },
                    },
                    "required": ["tasks"],
                },
            ),
            types.Tool(
                name="agency_evaluator",
                description=(
                    "Get the evaluator prompt and callback JWT for a completed task. "
                    "Agency does NOT track execution state — there is no 'execution "
                    "pipeline' or completion precondition. Pass the agency_task_id "
                    "returned by agency_assign (not your own external_id). After "
                    "receiving the evaluator prompt, evaluate your own output against "
                    "its criteria, then call agency_submit_evaluation with the result. "
                    "See caller protocol: https://github.com/agentbureau/agency/blob/"
                    "main/docs/integrations/caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agency_task_id": {
                            "type": "string",
                            "description": (
                                "The agency_task_id returned by agency_assign for this task. "
                                "Do not pass your own external_id."
                            ),
                        },
                    },
                    "required": ["agency_task_id"],
                },
            ),
            types.Tool(
                name="agency_submit_evaluation",
                description=(
                    "Submit your evaluation of a completed task. Pass the agency_task_id "
                    "and callback_jwt from agency_evaluator, plus your evaluation output "
                    "text. Optionally include score (0-100), task_completed (true/false), "
                    "and score_type to record structured assessment. The callback JWT "
                    "carries all agent metadata — you do not need to supply it. See "
                    "caller protocol: https://github.com/agentbureau/agency/blob/main/"
                    "docs/integrations/caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agency_task_id": {
                            "type": "string",
                            "description": "The agency_task_id returned by agency_assign for this task.",
                        },
                        "callback_jwt": {
                            "type": "string",
                            "description": "The callback_jwt returned by agency_evaluator. Single-use; expires after 24 hours.",
                        },
                        "output": {
                            "type": "string",
                            "description": "Your evaluation text, written by following the evaluator_prompt instructions.",
                        },
                        "score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Optional numeric score (0-100).",
                        },
                        "task_completed": {
                            "type": "boolean",
                            "description": "Optional: whether the task was fully completed.",
                        },
                        "score_type": {
                            "type": "string",
                            "enum": ["binary", "rubric", "likert", "percentage"],
                            "description": "Optional: how the score should be interpreted.",
                        },
                    },
                    "required": ["agency_task_id", "callback_jwt", "output"],
                },
            ),
            types.Tool(
                name="agency_list_projects",
                description=(
                    "List all projects in this Agency instance. Returns project IDs, "
                    "names, and which project is the current default. Use this to "
                    "discover available projects before calling agency_assign. See "
                    "caller protocol: https://github.com/agentbureau/agency/blob/"
                    "main/docs/integrations/caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="agency_create_project",
                description=(
                    "Create a new Agency project. Only the project name is required; "
                    "all other settings inherit from instance defaults if omitted. "
                    "Returns the new project ID. See caller protocol: https://github.com/"
                    "agentbureau/agency/blob/main/docs/integrations/caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 255,
                            "description": "Project name (required).",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional project description.",
                        },
                        "contact_email": {
                            "type": "string",
                            "description": "Optional contact email included in agent prompts.",
                        },
                        "oversight_preference": {
                            "type": "string",
                            "enum": ["discretion", "review"],
                            "description": "How closely to review agent work.",
                        },
                        "error_notification_timeout": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "Optional error notification timeout in seconds.",
                        },
                        "attribution": {
                            "type": "boolean",
                            "description": "Whether agent output includes an attribution line.",
                        },
                        "set_as_default": {
                            "type": "boolean",
                            "description": "Set this project as the default in agency.toml.",
                        },
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="agency_status",
                description=(
                    "Get Agency instance status: projects, active tasks, task progress, "
                    "and primitive store health. Use this to check what is happening in "
                    "Agency and whether tasks are pending evaluation. See caller protocol: "
                    "https://github.com/agentbureau/agency/blob/main/docs/integrations/"
                    "caller-protocol.md"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Filter to a single project (optional).",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "agency_assign":
            result = _tool_agency_assign(
                base_url,
                token,
                arguments.get("project_id"),
                arguments["tasks"],
            )
        elif name == "agency_evaluator":
            result = _tool_agency_evaluator(
                base_url, token, arguments["agency_task_id"]
            )
        elif name == "agency_submit_evaluation":
            result = _tool_agency_submit_evaluation(
                base_url,
                token,
                arguments["agency_task_id"],
                arguments["callback_jwt"],
                arguments["output"],
                score=arguments.get("score"),
                task_completed=arguments.get("task_completed"),
                score_type=arguments.get("score_type"),
            )
        elif name == "agency_list_projects":
            result = _tool_agency_list_projects(base_url, token)
        elif name == "agency_create_project":
            result = _tool_agency_create_project(
                base_url,
                token,
                arguments["name"],
                description=arguments.get("description"),
                contact_email=arguments.get("contact_email"),
                oversight_preference=arguments.get("oversight_preference"),
                error_notification_timeout=arguments.get("error_notification_timeout"),
                attribution=arguments.get("attribution"),
                set_as_default=arguments.get("set_as_default", False),
            )
        elif name == "agency_status":
            result = _tool_agency_status(
                base_url, token, project_id=arguments.get("project_id")
            )
        else:
            result = json.dumps(_make_error(None, f"Unknown tool: {name}"))

        return [types.TextContent(type="text", text=result)]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


@click.command("mcp")
def mcp_command():
    """Start the Agency MCP server (stdio transport for Claude Code)."""
    asyncio.run(_run_mcp_server())
