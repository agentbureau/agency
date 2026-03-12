"""CLI wizard for `agency project create`."""

import os
import sqlite3

import click
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


@click.command("create")
def project_create_command():
    """Create a new Agency project via interactive wizard."""
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
