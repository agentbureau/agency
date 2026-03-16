"""CLI commands for `agency project` subgroup."""

import json as _json
import os
import sqlite3
import sys

import click
import httpx
import tomllib
import tomli_w
from pathlib import Path

from agency.db.migrations import is_schema_current
from agency.db.projects import create_project
from agency.config.toml import load_config


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def run_project_create_wizard(
    state_dir: str, conn: sqlite3.Connection, toml_path: str
) -> str:
    """Interactive wizard that creates a project. Returns the new project UUID.

    Reusable — called by both ``project_create_command`` and ``agency init``.
    """
    # Load instance defaults from agency.toml
    cfg = load_config(toml_path)
    notifications = cfg.get("notifications", {})
    output = cfg.get("output", {})

    inst_email = notifications.get("contact_email", "")
    inst_oversight = notifications.get("oversight_preference", "discretion")
    inst_timeout = notifications.get("error_notification_timeout", 1800)
    inst_attribution = output.get("attribution", True)

    click.echo("\nCreate a new Agency project.\n")

    # --- Project name (required) ---
    name = click.prompt("Project name")

    # --- Inheritable fields (empty = inherit = NULL) ---
    click.echo(
        "\nThe following settings inherit from your instance defaults.\n"
        "Press enter to accept each default, or type a new value."
    )

    raw_email = click.prompt(
        f"  Contact email [{inst_email}]", default="", show_default=False
    )
    contact_email = raw_email.strip() or None

    raw_oversight = click.prompt(
        f"  Oversight preference [{inst_oversight}]", default="", show_default=False
    )
    oversight_preference = raw_oversight.strip() or None
    if oversight_preference and oversight_preference not in (
        "discretion",
        "review",
    ):
        click.echo(
            f"  Warning: '{oversight_preference}' is not a standard value "
            "(discretion/review). Storing as-is."
        )

    raw_timeout = click.prompt(
        f"  Error notification timeout (seconds) [{inst_timeout}]",
        default="",
        show_default=False,
    )
    error_notification_timeout = int(raw_timeout) if raw_timeout.strip() else None

    raw_attr = click.prompt(
        f"  Attribution [{'on' if inst_attribution else 'off'}]",
        default="",
        show_default=False,
    )
    if raw_attr.strip().lower() in ("true", "1", "yes"):
        attribution = 1
    elif raw_attr.strip().lower() in ("false", "0", "no"):
        attribution = 0
    elif raw_attr.strip() == "":
        attribution = None
    else:
        click.echo(f"  Unrecognised value '{raw_attr}'; treating as inherit.")
        attribution = None

    # --- Optional LLM override ---
    llm_section = cfg.get("llm", {})
    inst_backend = llm_section.get("backend", "claude-code")
    inst_model = llm_section.get("model", "")

    llm_provider = None
    llm_model = None
    llm_api_key = None
    if click.confirm("\nOverride LLM settings for this project?", default=False):
        if inst_backend == "claude-code":
            raw_provider = click.prompt(
                f"  LLM provider [claude-code]", default="", show_default=False
            )
            llm_provider = raw_provider.strip() or None
            raw_model = click.prompt(
                f"  Model [{inst_model}]", default="", show_default=False
            )
            llm_model = raw_model.strip() or None
            if llm_provider and llm_provider not in ("claude-code",):
                raw_key = click.prompt("  API key", default="", show_default=False)
                llm_api_key = raw_key.strip() or None
        else:
            raw_provider = click.prompt(
                f"  LLM provider [{inst_backend}]", default="", show_default=False
            )
            if raw_provider.strip() == "claude-code":
                click.echo(
                    "  Error: claude-code is an instance-level backend only; "
                    "not valid at project level."
                )
                raise SystemExit(1)
            llm_provider = raw_provider.strip() or None
            raw_model = click.prompt(
                f"  Model [{inst_model}]", default="", show_default=False
            )
            llm_model = raw_model.strip() or None
            raw_key = click.prompt(
                "  API key (leave blank to inherit instance key)",
                default="",
                show_default=False,
            )
            llm_api_key = raw_key.strip() or None

    # --- Insert into DB ---
    project_id = create_project(
        conn,
        name=name,
        client_id=None,
        description=None,
        admin_email=None,
        contact_email=contact_email,
        oversight_preference=oversight_preference,
        error_notification_timeout=error_notification_timeout,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        attribution=attribution,
    )

    click.echo(f"\nProject created: {name}")
    click.echo(f"  ID: {project_id}")

    # --- Optionally set as default project ---
    if click.confirm("\nSet as default project for this Agency instance?", default=False):
        _set_default_project_in_toml(toml_path, project_id)
        click.echo(f"  Default project set to {project_id} in agency.toml")

    return project_id


def _set_default_project_in_toml(toml_path: str, project_id: str) -> None:
    """Add or update [project] default_id in agency.toml."""
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    cfg.setdefault("project", {})["default_id"] = project_id

    with open(toml_path, "wb") as f:
        tomli_w.dump(cfg, f)


def _get_server_url() -> str:
    """Derive Agency server URL from agency.toml [server] host/port."""
    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    path = os.path.join(state_dir, "agency.toml")
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        cfg = {}
    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = cfg.get("server", {}).get("port", 8000)
    return f"http://{host}:{port}"


def _get_token() -> str:
    """Read bearer token from AGENCY_TOKEN_FILE (default: ~/.agency-mcp-token)."""
    token_file = os.environ.get(
        "AGENCY_TOKEN_FILE", os.path.expanduser("~/.agency-mcp-token")
    )
    try:
        with open(token_file) as f:
            token = f.read().strip()
    except FileNotFoundError:
        token = ""
    if not token:
        click.echo(
            f"Error: token file not found at {token_file}. "
            f"Run 'agency token create --client-id mcp > {token_file}' first.",
            err=True,
        )
        raise SystemExit(1)
    return token


@click.command("create")
@click.option("--name", default=None, help="Project name (non-interactive mode).")
@click.option("--description", default=None, help="Project description.")
@click.option("--contact-email", default=None, help="Contact email.")
@click.option("--oversight", default=None, help="Oversight preference (discretion/review).")
@click.option("--error-timeout", default=None, type=int, help="Error notification timeout in seconds.")
@click.option("--attribution", default=None, type=bool, help="Enable attribution.")
@click.option("--set-default", is_flag=True, default=False, help="Set as default project.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format.")
def project_create_command(name, description, contact_email, oversight, error_timeout, attribution, set_default, fmt):
    """Create a new Agency project.

    When --name is provided, runs non-interactively via the API server.
    When --name is omitted, runs the interactive wizard.
    """
    if name is not None:
        # Non-interactive mode: call API
        _project_create_api(name, description, contact_email, oversight, error_timeout, attribution, set_default, fmt)
    else:
        # Interactive wizard (original behaviour)
        _project_create_interactive()


def _project_create_api(name, description, contact_email, oversight, error_timeout, attribution, set_default, fmt):
    """Non-interactive project creation via POST /projects."""
    base_url = _get_server_url()
    token = _get_token()

    payload = {"name": name}
    if description is not None:
        payload["description"] = description
    if contact_email is not None:
        payload["contact_email"] = contact_email
    if oversight is not None:
        payload["oversight_preference"] = oversight
    if error_timeout is not None:
        payload["error_notification_timeout"] = error_timeout
    if attribution is not None:
        payload["attribution"] = attribution

    try:
        resp = httpx.post(
            f"{base_url}/projects",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.ConnectError:
        click.echo(
            f"Cannot reach Agency server at {base_url}. Start it with: agency serve",
            err=True,
        )
        raise SystemExit(1)

    if resp.status_code not in (200, 201):
        click.echo(f"Error: {resp.text}", err=True)
        raise SystemExit(1)

    project = resp.json()

    if set_default:
        toml_path = os.path.join(
            os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency")),
            "agency.toml",
        )
        _set_default_project_in_toml(toml_path, project["id"])

    if fmt == "json":
        click.echo(_json.dumps(project, indent=2))
    else:
        click.echo(f"Project created: {project.get('name', name)}")
        click.echo(f"  ID: {project['id']}")
        if set_default:
            click.echo(f"  Set as default project in agency.toml")


def _project_create_interactive():
    """Original interactive wizard path."""
    state_dir = _state_dir()
    db_path = str(state_dir / "agency.db")
    toml_path = str(state_dir / "agency.toml")

    if not is_schema_current(db_path):
        click.echo(
            "Error: Agency database not found or schema not current. "
            "Run 'agency serve' at least once first.",
            err=True,
        )
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        run_project_create_wizard(str(state_dir), conn, toml_path)
    finally:
        conn.close()


@click.command("list")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format.")
def project_list_command(fmt):
    """List all Agency projects."""
    base_url = _get_server_url()
    token = _get_token()

    try:
        resp = httpx.get(
            f"{base_url}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.ConnectError:
        click.echo(
            f"Cannot reach Agency server at {base_url}. Start it with: agency serve",
            err=True,
        )
        raise SystemExit(1)

    if resp.status_code != 200:
        click.echo(f"Error: {resp.text}", err=True)
        raise SystemExit(1)

    data = resp.json()
    projects = data.get("projects", [])
    default_id = data.get("default_project_id")

    if not projects:
        click.echo("No projects found.")
        return

    if fmt == "json":
        out = {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "is_default": p["id"] == default_id,
                    "created_at": p.get("created_at", ""),
                }
                for p in projects
            ],
            "default_project_id": default_id,
        }
        click.echo(_json.dumps(out, indent=2))
    else:
        click.echo(f"{'ID':<38} {'NAME':<20} {'DEFAULT':<10} {'CREATED'}")
        for p in projects:
            marker = "*" if p["id"] == default_id else ""
            click.echo(
                f"{p['id']:<38} {p['name']:<20} {marker:<10} {p.get('created_at', '')}"
            )


@click.command("pin")
@click.option("--project-id", default=None, help="Project UUID to pin.")
def project_pin_command(project_id):
    """Pin a project to .agency-project in the current directory."""
    if not project_id:
        click.echo("Error: --project-id is required.", err=True)
        raise SystemExit(1)

    base_url = _get_server_url()
    token = _get_token()

    # Validate project exists via API
    try:
        resp = httpx.get(
            f"{base_url}/projects/{project_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.ConnectError:
        click.echo(
            f"Cannot reach Agency server at {base_url}. Start it with: agency serve",
            err=True,
        )
        raise SystemExit(1)

    if resp.status_code != 200:
        click.echo(
            f"Error: project {project_id} not found on server.",
            err=True,
        )
        raise SystemExit(1)

    project = resp.json()
    pin_path = os.path.join(os.getcwd(), ".agency-project")
    with open(pin_path, "w") as f:
        f.write(project_id + "\n")

    project_name = project.get("name", project_id)
    click.echo(f"Pinned project \"{project_name}\" ({project_id}) to {pin_path}")
