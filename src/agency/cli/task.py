"""CLI task commands for Agency v1.2.3.

agency task assign   — compose agents for tasks
agency task evaluator — get evaluator prompt + callback JWT
agency task submit   — submit evaluation
agency task get      — retrieve task state
"""
import json
import sys
import uuid as _uuid
from typing import Optional

import click

from agency.client import (
    resolve_base_url,
    resolve_token,
    assign as client_assign,
    get_evaluator as client_get_evaluator,
    submit_evaluation as client_submit_evaluation,
    get_task as client_get_task,
    _make_error,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
EXIT_CLIENT_ERROR = 1
EXIT_SERVER_ERROR = 2
EXIT_APP_ERROR = 3

TABLE_HASH_DISPLAY_LEN = 8

# Map error_type to exit code
_EXIT_CODE_MAP_PRE_HTTP = {
    "auth": EXIT_CLIENT_ERROR,
    "validation": EXIT_CLIENT_ERROR,
    "permanent": EXIT_CLIENT_ERROR,
}
_EXIT_CODE_MAP_HTTP = {
    "transient": EXIT_SERVER_ERROR,
    "auth": EXIT_APP_ERROR,
    "not_found": EXIT_APP_ERROR,
    "validation": EXIT_APP_ERROR,
    "permanent": EXIT_APP_ERROR,
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_client_id(client_id: Optional[str]) -> str:
    """--client-id flag > AGENCY_CLIENT_ID env > 'cli'."""
    import os
    if client_id:
        return client_id
    return os.environ.get("AGENCY_CLIENT_ID", "cli")


def _validate_uuid(value: str, label: str) -> str:
    """Validate and normalise a UUID string. Returns lowercase hyphenated form."""
    try:
        return str(_uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def _make_cli_error(error_type: str, code, message: str, cause=None, fix=None) -> dict:
    """Convenience wrapper for pre-HTTP errors."""
    return _make_error(error_type=error_type, code=code, message=message, cause=cause, fix=fix)


def _exit_code_for_result(result: dict, pre_http: bool = False) -> int:
    """Determine CLI exit code from a result dict."""
    if result.get("status") == "ok":
        return EXIT_SUCCESS
    error_type = result.get("error_type", "permanent")
    if pre_http:
        return _EXIT_CODE_MAP_PRE_HTTP.get(error_type, EXIT_CLIENT_ERROR)
    return _EXIT_CODE_MAP_HTTP.get(error_type, EXIT_APP_ERROR)


def _output_result(result: dict, fmt: str, no_guidance: bool, quiet: bool,
                   table_fn=None) -> int:
    """Write result to stdout/stderr. Returns exit code."""
    exit_code = _exit_code_for_result(result)

    if result.get("status") == "ok" and no_guidance:
        result.pop("next_step", None)

    if fmt == "table" and result.get("status") == "ok" and table_fn:
        table_fn(result)
    else:
        click.echo(json.dumps(result, indent=None, ensure_ascii=False))

    if result.get("status") == "error" and not quiet:
        click.echo(result.get("message", "Error"), err=True)

    return exit_code


def _resolve_project_id_cli(project_id: Optional[str]) -> Optional[str]:
    """Project ID resolution for CLI (uses actual CWD)."""
    from agency.cli.mcp import _resolve_project_id
    return _resolve_project_id(project_id)


def _get_token_and_url(client_id: str, quiet: bool):
    """Resolve token and base URL. Returns (token, base_url) or exits."""
    try:
        token = resolve_token(client_id)
    except FileNotFoundError as e:
        result = _make_cli_error("auth", None, str(e))
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(str(e), err=True)
        sys.exit(EXIT_CLIENT_ERROR)
    base_url = resolve_base_url()
    return token, base_url


# ---------------------------------------------------------------------------
# Table formatters
# ---------------------------------------------------------------------------


def _table_assign(result: dict) -> None:
    """EXTERNAL_ID  AGENCY_TASK_ID  AGENT_HASH  PROMPT_LEN"""
    header = f"{'EXTERNAL_ID':<20} {'AGENCY_TASK_ID':<38} {'AGENT_HASH':<10} {'PROMPT_LEN':>10}"
    click.echo(header)
    for tid in result.get("task_ids", []):
        ext_id = tid.get("external_id", "")[:20]
        agency_id = tid.get("agency_task_id", "")
        agent_hash = tid.get("agent_hash", "")[:TABLE_HASH_DISPLAY_LEN]
        # Get prompt length from agents map
        agents = result.get("agents", {})
        full_hash = tid.get("agent_hash", "")
        prompt_len = len(agents.get(full_hash, {}).get("rendered_prompt", ""))
        click.echo(f"{ext_id:<20} {agency_id:<38} {agent_hash:<10} {prompt_len:>10}")


def _table_evaluator(result: dict, save_jwt: Optional[str]) -> None:
    """Print evaluator_prompt as plain text; JWT to stderr."""
    click.echo(result.get("evaluator_prompt", ""))
    if save_jwt:
        click.echo(f"JWT saved to: {save_jwt}", err=True)
    else:
        click.echo(f"Callback JWT: {result.get('callback_jwt', '')}", err=True)


def _table_submit(result: dict) -> None:
    hash_val = result.get("content_hash", "")
    verified = "no" if result.get("hash_mismatch") else "yes"
    click.echo(f"Evaluation submitted. Content hash: {hash_val}. Hash verified: {verified}.")


def _table_get(result: dict) -> None:
    """AGENCY_TASK_ID  EXTERNAL_ID  STATE  AGENT_HASH  CREATED_AT"""
    header = f"{'AGENCY_TASK_ID':<38} {'EXTERNAL_ID':<20} {'STATE':<22} {'AGENT_HASH':<10} {'CREATED_AT'}"
    click.echo(header)
    agency_id = result.get("agency_task_id", "")
    ext_id = (result.get("external_id") or "")[:20]
    state = result.get("state", "")
    agent_hash = (result.get("agent_hash") or "")[:TABLE_HASH_DISPLAY_LEN]
    created = result.get("created_at", "")
    click.echo(f"{agency_id:<38} {ext_id:<20} {state:<22} {agent_hash:<10} {created}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.command("assign")
@click.option("--project-id", default=None, help="Project ID (UUID). Falls back to resolution hierarchy.")
@click.option("--tasks", "tasks_inline", default=None, help="Inline JSON array of task objects.")
@click.option("--tasks-file", default=None, type=click.Path(), help="Path to JSON file containing task array.")
@click.option("--tasks-stdin", is_flag=True, default=False, help="Read task JSON from stdin.")
@click.option("--client-id", default=None, help="Client identity for token resolution.")
@click.option("--timeout", default=30, type=int, help="HTTP timeout in seconds.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "table"]), help="Output format.")
@click.option("--no-guidance", is_flag=True, default=False, help="Strip next_step from JSON output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress stderr diagnostics.")
def task_assign_command(project_id, tasks_inline, tasks_file, tasks_stdin,
                        client_id, timeout, fmt, no_guidance, quiet):
    """Compose agents for a set of tasks."""
    client_id = _resolve_client_id(client_id)

    # Mutual exclusivity check
    sources = sum(1 for x in [tasks_inline, tasks_file, tasks_stdin] if x)
    if sources != 1:
        result = _make_cli_error(
            "validation", None,
            "Exactly one of --tasks, --tasks-file, or --tasks-stdin is required.",
        )
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    # Read task JSON
    raw = None
    if tasks_inline:
        raw = tasks_inline
    elif tasks_file:
        try:
            with open(tasks_file, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            result = _make_cli_error("validation", None, f"File not found: {tasks_file}")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
        except UnicodeDecodeError as e:
            result = _make_cli_error("validation", None,
                                     f"Cannot read {tasks_file}: invalid UTF-8 at byte offset {e.start}.")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
    elif tasks_stdin:
        if sys.stdin.isatty():
            result = _make_cli_error("validation", None, "--tasks-stdin requires piped input.")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
        raw = sys.stdin.read()

    # Parse and validate JSON
    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError as e:
        result = _make_cli_error("validation", None,
                                 f"Invalid JSON: {e.msg} at position {e.pos}.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    if not isinstance(tasks, list):
        result = _make_cli_error("validation", None,
                                 f"Tasks must be a JSON array. Got: {type(tasks).__name__}.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    if not tasks:
        result = _make_cli_error("validation", None,
                                 "Tasks array must contain at least one task.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    for i, t in enumerate(tasks):
        for field in ("external_id", "description"):
            if field not in t:
                result = _make_cli_error("validation", None,
                                         f"Task at index {i} missing required field: {field}.")
                click.echo(json.dumps(result, ensure_ascii=False))
                if not quiet:
                    click.echo(result["message"], err=True)
                sys.exit(EXIT_CLIENT_ERROR)

    # Resolve project ID
    if project_id:
        normalised = _validate_uuid(project_id, "project ID")
        if normalised is None:
            result = _make_cli_error("validation", None,
                                     "Invalid project ID format: must be a valid UUID.")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
        project_id = normalised

    resolved_project = _resolve_project_id_cli(project_id)
    if resolved_project is None:
        result = _make_cli_error("validation", None,
                                 "No project ID specified and no default configured.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    token, base_url = _get_token_and_url(client_id, quiet)
    api_result = client_assign(base_url, token, resolved_project, tasks, timeout=timeout)

    if api_result.get("status") == "ok":
        api_result["next_step"] = (
            "Execute each task using its rendered_prompt, then call "
            "agency task evaluator for each."
        )

    exit_code = _output_result(
        api_result, fmt, no_guidance, quiet,
        table_fn=_table_assign,
    )
    sys.exit(exit_code)


@click.command("evaluator")
@click.option("--task-id", required=True, help="The agency_task_id from the assign response.")
@click.option("--save-jwt", default=None, type=click.Path(), help="Write callback JWT to this file.")
@click.option("--client-id", default=None, help="Client identity for token resolution.")
@click.option("--timeout", default=30, type=int, help="HTTP timeout in seconds.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "table"]), help="Output format.")
@click.option("--no-guidance", is_flag=True, default=False, help="Strip next_step from JSON output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress stderr diagnostics.")
def task_evaluator_command(task_id, save_jwt, client_id, timeout, fmt, no_guidance, quiet):
    """Get evaluator prompt and callback JWT for a task."""
    client_id = _resolve_client_id(client_id)

    normalised = _validate_uuid(task_id, "task ID")
    if normalised is None:
        result = _make_cli_error("validation", None,
                                 "Invalid task ID format: must be a valid UUID.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)
    task_id = normalised

    token, base_url = _get_token_and_url(client_id, quiet)
    api_result = client_get_evaluator(base_url, token, task_id, timeout=timeout)

    if api_result.get("status") == "ok":
        api_result["next_step"] = (
            f"Evaluate the output using the evaluator_prompt, then call "
            f"agency task submit with --task-id {task_id}."
        )

    # Handle --save-jwt
    jwt_write_failed = False
    if save_jwt and api_result.get("status") == "ok":
        try:
            with open(save_jwt, "w", encoding="utf-8") as f:
                f.write(api_result.get("callback_jwt", ""))
        except IsADirectoryError:
            if not quiet:
                click.echo(f"Cannot write JWT: {save_jwt} is a directory.", err=True)
            jwt_write_failed = True
        except PermissionError:
            if not quiet:
                click.echo(f"Cannot write JWT: permission denied for {save_jwt}.", err=True)
            jwt_write_failed = True
        except FileNotFoundError:
            if not quiet:
                click.echo("Cannot write JWT: directory does not exist.", err=True)
            jwt_write_failed = True
        except OSError as e:
            if not quiet:
                click.echo(f"Cannot write JWT: {e}.", err=True)
            jwt_write_failed = True

    if fmt == "table" and api_result.get("status") == "ok":
        _table_evaluator(api_result, save_jwt if not jwt_write_failed else None)
    else:
        if no_guidance and api_result.get("status") == "ok":
            api_result.pop("next_step", None)
        click.echo(json.dumps(api_result, indent=None, ensure_ascii=False))

    if api_result.get("status") == "error" and not quiet:
        click.echo(api_result.get("message", "Error"), err=True)

    if jwt_write_failed:
        sys.exit(EXIT_CLIENT_ERROR)

    sys.exit(_exit_code_for_result(api_result))


@click.command("submit")
@click.option("--task-id", required=True, help="The agency_task_id.")
@click.option("--callback-jwt", default=None, help="Inline callback JWT.")
@click.option("--callback-jwt-file", default=None, type=click.Path(), help="Path to JWT file.")
@click.option("--output", "output_inline", default=None, help="Inline evaluation text.")
@click.option("--output-file", default=None, type=click.Path(), help="Path to evaluation text file.")
@click.option("--output-stdin", is_flag=True, default=False, help="Read evaluation from stdin.")
@click.option("--score", default=None, type=int, help="Evaluation score (0-100).")
@click.option("--task-completed", default=None, type=bool, help="Whether the task was completed.")
@click.option("--score-type", default=None,
              type=click.Choice(["binary", "rubric", "likert", "percentage"]),
              help="How the score should be interpreted.")
@click.option("--client-id", default=None, help="Client identity for token resolution.")
@click.option("--timeout", default=30, type=int, help="HTTP timeout in seconds.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "table"]), help="Output format.")
@click.option("--no-guidance", is_flag=True, default=False, help="Strip next_step from JSON output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress stderr diagnostics.")
def task_submit_command(task_id, callback_jwt, callback_jwt_file, output_inline,
                        output_file, output_stdin, score, task_completed, score_type,
                        client_id, timeout, fmt, no_guidance, quiet):
    """Submit an evaluation for a task."""
    client_id = _resolve_client_id(client_id)

    normalised = _validate_uuid(task_id, "task ID")
    if normalised is None:
        result = _make_cli_error("validation", None,
                                 "Invalid task ID format: must be a valid UUID.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)
    task_id = normalised

    # Validate score range
    if score is not None and (score < 0 or score > 100):
        result = _make_cli_error("validation", None, "Score must be between 0 and 100.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    # JWT resolution
    jwt_sources = sum(1 for x in [callback_jwt, callback_jwt_file] if x)
    if jwt_sources != 1:
        result = _make_cli_error("validation", None,
                                 "Exactly one of --callback-jwt or --callback-jwt-file is required.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    if callback_jwt_file:
        try:
            with open(callback_jwt_file, encoding="utf-8") as f:
                callback_jwt = f.read().strip()
        except FileNotFoundError:
            result = _make_cli_error("validation", None, f"File not found: {callback_jwt_file}")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)

    # Output resolution
    output_sources = sum(1 for x in [output_inline, output_file, output_stdin] if x)
    if output_sources != 1:
        result = _make_cli_error("validation", None,
                                 "Exactly one of --output, --output-file, or --output-stdin is required.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)

    output_text = None
    if output_inline:
        output_text = output_inline
    elif output_file:
        try:
            with open(output_file, encoding="utf-8") as f:
                output_text = f.read()
        except FileNotFoundError:
            result = _make_cli_error("validation", None, f"File not found: {output_file}")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
        except UnicodeDecodeError as e:
            result = _make_cli_error("validation", None,
                                     f"Cannot read {output_file}: invalid UTF-8 at byte offset {e.start}.")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
    elif output_stdin:
        if sys.stdin.isatty():
            result = _make_cli_error("validation", None, "--output-stdin requires piped input.")
            click.echo(json.dumps(result, ensure_ascii=False))
            if not quiet:
                click.echo(result["message"], err=True)
            sys.exit(EXIT_CLIENT_ERROR)
        output_text = sys.stdin.read()

    token, base_url = _get_token_and_url(client_id, quiet)
    api_result = client_submit_evaluation(
        base_url, token, task_id, callback_jwt, output_text,
        score=score, task_completed=task_completed, score_type=score_type,
        timeout=timeout,
    )

    if api_result.get("status") == "ok":
        api_result["next_step"] = (
            "Evaluation submitted. The agent composition will be updated based on this feedback."
        )
        # Warn on hash mismatch
        if api_result.get("hash_mismatch") and not quiet:
            click.echo("Warning: content hash mismatch between client and server.", err=True)

    exit_code = _output_result(
        api_result, fmt, no_guidance, quiet,
        table_fn=_table_submit,
    )
    sys.exit(exit_code)


@click.command("get")
@click.option("--task-id", required=True, help="The agency_task_id.")
@click.option("--client-id", default=None, help="Client identity for token resolution.")
@click.option("--timeout", default=30, type=int, help="HTTP timeout in seconds.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "table"]), help="Output format.")
@click.option("--no-guidance", is_flag=True, default=False, help="Strip next_step from JSON output.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress stderr diagnostics.")
def task_get_command(task_id, client_id, timeout, fmt, no_guidance, quiet):
    """Get the current state of a task."""
    client_id = _resolve_client_id(client_id)

    normalised = _validate_uuid(task_id, "task ID")
    if normalised is None:
        result = _make_cli_error("validation", None,
                                 "Invalid task ID format: must be a valid UUID.")
        click.echo(json.dumps(result, ensure_ascii=False))
        if not quiet:
            click.echo(result["message"], err=True)
        sys.exit(EXIT_CLIENT_ERROR)
    task_id = normalised

    token, base_url = _get_token_and_url(client_id, quiet)
    api_result = client_get_task(base_url, token, task_id, timeout=timeout)

    if api_result.get("status") == "ok":
        state = api_result.get("state", "assigned")
        next_steps = {
            "assigned": "This task has an agent composition but has not been evaluated yet.",
            "evaluation_pending": "Evaluation has been submitted and is pending confirmation. No further action needed.",
            "evaluation_received": "This task has been evaluated. No further action needed.",
        }
        api_result["next_step"] = next_steps.get(state, "Task state unknown.")

    exit_code = _output_result(
        api_result, fmt, no_guidance, quiet,
        table_fn=_table_get,
    )
    sys.exit(exit_code)
