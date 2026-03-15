"""Agency MCP server — stdio transport for Claude Code.

Exposes three tools:
  - agency_assign: assign tasks to AI agents
  - agency_evaluator: get evaluator prompt + callback JWT
  - agency_submit_evaluation: submit evaluation with content hash verification
"""
import asyncio
import hashlib
import json
import os
import sys
from typing import Optional

import click
import httpx


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


def _resolve_project_id(project_id: Optional[str]) -> Optional[str]:
    """Priority: 1. explicit arg, 2. AGENCY_PROJECT_ID env var,
    3. agency.toml [project] default_id, 4. None."""
    if project_id is not None:
        return project_id
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


def _make_error(code: Optional[int], message: str) -> dict:
    return {"status": "error", "code": code, "message": message}


def _make_success(**kwargs) -> dict:
    return {"status": "ok", **kwargs}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _tool_agency_assign(
    base_url: str, token: str, project_id: Optional[str], tasks: list
) -> str:
    """POST /projects/{id}/assign with Bearer token. Returns JSON envelope string."""
    resolved = _resolve_project_id(project_id)
    if resolved is None:
        return json.dumps(
            _make_error(
                None,
                "No project ID: pass project_id, set AGENCY_PROJECT_ID, "
                "or configure [project] default_id in agency.toml",
            )
        )
    try:
        resp = httpx.post(
            f"{base_url}/projects/{resolved}/assign",
            json={"tasks": tasks},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            return json.dumps(_make_success(assignment=resp.json()))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _tool_agency_evaluator(
    base_url: str, token: str, agency_task_id: str
) -> str:
    """GET /tasks/{id}/evaluator with Bearer token."""
    try:
        resp = httpx.get(
            f"{base_url}/tasks/{agency_task_id}/evaluator",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return json.dumps(
                _make_success(
                    evaluator_prompt=data["rendered_prompt"],
                    callback_jwt=data["callback_jwt"],
                )
            )
        if resp.status_code == 404:
            return json.dumps(_make_error(404, "task not found"))
        if resp.status_code == 422:
            return json.dumps(_make_error(422, "task has no evaluator assigned"))
        return json.dumps(_make_error(resp.status_code, resp.text))
    except httpx.HTTPError as e:
        return json.dumps(_make_error(None, str(e)))


def _tool_agency_submit_evaluation(
    base_url: str, agency_task_id: str, callback_jwt: str, output: str
) -> str:
    """POST /tasks/{id}/evaluation.

    CRITICAL: serialize body_bytes ONCE and reuse for both HTTP body and
    local hash — prevents hash mismatch from double serialization.
    """
    body_bytes = json.dumps(
        {"output": output}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    local_hash = hashlib.sha256(body_bytes).hexdigest()

    try:
        resp = httpx.post(
            f"{base_url}/tasks/{agency_task_id}/evaluation",
            content=body_bytes,
            headers={
                "Authorization": f"Bearer {callback_jwt}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            server_hash = resp.json().get("content_hash")
            if server_hash != local_hash:
                return json.dumps(
                    _make_error(
                        None,
                        f"Content hash mismatch: local={local_hash} server={server_hash}",
                    )
                )
            return json.dumps(_make_success(content_hash=local_hash))
        return json.dumps(_make_error(resp.status_code, resp.text))
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
            f"Error: Agency server not reachable at {base_url}. "
            "Run 'agency serve' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    server = Server("agency")

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="agency_assign",
                description="Assign tasks to AI agents via the Agency server.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID (optional — defaults to AGENCY_PROJECT_ID env or agency.toml)",
                        },
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "external_id": {"type": "string"},
                                    "description": {"type": "string"},
                                    "skills": {"type": "array", "items": {"type": "string"}},
                                    "deliverables": {"type": "array", "items": {"type": "string"}},
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
                description="Get the evaluator prompt and callback JWT for a completed task.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agency_task_id": {
                            "type": "string",
                            "description": "The Agency task ID to get evaluator info for",
                        },
                    },
                    "required": ["agency_task_id"],
                },
            ),
            types.Tool(
                name="agency_submit_evaluation",
                description="Submit evaluation output for a task, with content hash verification.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agency_task_id": {
                            "type": "string",
                            "description": "The Agency task ID",
                        },
                        "callback_jwt": {
                            "type": "string",
                            "description": "The callback JWT from agency_evaluator",
                        },
                        "output": {
                            "type": "string",
                            "description": "The evaluation output text",
                        },
                    },
                    "required": ["agency_task_id", "callback_jwt", "output"],
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
                arguments["agency_task_id"],
                arguments["callback_jwt"],
                arguments["output"],
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
