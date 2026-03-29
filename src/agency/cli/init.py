"""agency init — two-phase setup wizard for Agency v1.2.3."""
import json
import os
import pathlib
import shutil as _shutil
import sqlite3
import subprocess
import sys
import time

import click
import httpx
import tomllib
import tomli_w

from agency.auth.keypair import generate_keypair, load_private_key
from agency.auth.jwt import create_jwt
from agency.utils.ids import generate_uuid_v7
from agency.config.toml import load_config
from agency.db.migrations import run_migrations, is_schema_current
from agency.db.tokens import insert_token, revoke_tokens_by_client_id, token_table_exists

from agency.cli.wizard_ui import (
    status as wiz_status,
    helper,
    prompt as wiz_prompt,
    prompt_bool,
    prompt_choice,
    SETTING_HELP,
)
from agency.cli.terminal import (  # v1.2.4 Issue 20 — terminal typography helpers
    status as _term_status,
    helper as _term_helper,
    success as _term_success,
    error as _term_error,
)

# Backward-compatible alias — existing tests import this from init.py
FIELD_EXPLAINERS = {
    "contact_email": SETTING_HELP["contact_email"],
    "oversight_preference": SETTING_HELP["oversight_preference"],
    "attribution": SETTING_HELP["attribution"],
}


WELCOME_BANNER = """
======================================================================
                         Agency  v1.2.3
======================================================================

Hello and welcome to Agency — your engine for building and
evolving AI agent teams.

This setup wizard will take you through the installation and
commissioning process for Agency.

Agency was designed to be installed with pipx:
  pipx install agency-engine

If you installed with pip into a virtualenv, the `agency` command is only
available while that venv is active. If you encounter "command not found"
errors later, this is the most likely cause.

--- What to expect -----------------------------------------------------

The wizard has 2 phases and 12 steps.

  Phase 1 of 2 — Configuration  (5 steps, no server required)

    Step 1.1   Generate instance credentials          automatic
    Step 1.2   Configure server settings              automatic
    Step 1.3   Configure LLM connection               * your input required
    Step 1.4   Configure notifications                * your input required
    Step 1.5   Configure output defaults              * your input required

  Phase 2 of 2 — Initialisation  (7 steps, runs the server briefly)

    Step 2.1   Initialise database                    automatic
    Step 2.2   Download embedding model               automatic
    Step 2.3   Install starter primitives             automatic
    Step 2.4   Create your first project              * your input required
    Step 2.5   Create integration tokens              automatic
    Step 2.6   Register with Claude Code              * your input required
    Step 2.7   Install Claude Code skill              automatic

  * = requires your input or confirmation

------------------------------------------------------------------------
"""


def _phase1_complete(cfg: dict, state_dir: str) -> bool:
    """Return True if all Phase 1 completion conditions are met."""
    keys_dir = os.path.join(state_dir, "keys")
    return (
        "instance_id" in cfg
        and os.path.exists(os.path.join(keys_dir, "agency.ed25519.pem"))
        and os.path.exists(os.path.join(keys_dir, "agency.ed25519.pub.pem"))
        and "server" in cfg
        and "llm" in cfg
        and "notifications" in cfg
        and "output" in cfg
    )


def _step_header(phase: int, step: int, total_steps: int):
    click.echo(
        f"\n[ Phase {phase} of 2: "
        f"{'Configuration' if phase == 1 else 'Initialisation'} ]  "
        f"[ Step {step} of {total_steps} ]"
    )
    click.echo("-" * 49)


def _poll_health(base_url: str, timeout_secs: int = 15, interval: float = 0.5) -> bool:
    """Poll GET /health every interval seconds for up to timeout_secs. Returns True if successful."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    return False


def _write_toml(cfg: dict, path: str):
    with open(path, "wb") as f:
        tomli_w.dump(cfg, f)


def _is_flag_provided(ctx: click.Context, param_name: str) -> bool:
    """Return True if the flag was explicitly passed on the command line."""
    source = ctx.get_parameter_source(param_name)
    return source == click.core.ParameterSource.COMMANDLINE


def _any_flag_provided(ctx: click.Context) -> bool:
    """Return True if any flag was explicitly passed on the command line."""
    for param in ctx.command.params:
        if _is_flag_provided(ctx, param.name):
            return True
    return False


@click.command("init")
@click.option("--backend", default="claude-code", help="LLM backend (claude-code, api, other)")
@click.option("--model", default="claude-sonnet-4-6", help="LLM model name")
@click.option("--endpoint", default="", help="LLM API endpoint")
@click.option("--api-key", default="", help="LLM API key")
@click.option("--email", default="", help="Contact email (empty = skip)")
@click.option("--timeout", default=1800, type=int, help="Error notification timeout in seconds")
@click.option("--oversight", default="discretion", help="Oversight preference (discretion or review)")
@click.option("--attribution", default="on", help="Attribution (on or off)")
@click.option("--project-name", default=None, help="First project name (skip if omitted)")
@click.option("--set-default/--no-set-default", default=True, help="Set created project as default")
@click.option("--register-mcp/--no-register-mcp", default=True, help="Register in ~/.claude.json")
@click.option("--skip-primitives/--no-skip-primitives", default=False, help="Skip primitive download")
@click.option("--smtp-host", default=None, help="SMTP host")
@click.option("--smtp-port", default=587, type=int, help="SMTP port")
@click.option("--smtp-username", default=None, help="SMTP username")
@click.option("--smtp-password", default=None, help="SMTP password")
@click.pass_context
def init_command(ctx, backend, model, endpoint, api_key, email, timeout,
                 oversight, attribution, project_name, set_default,
                 register_mcp, skip_primitives, smtp_host, smtp_port,
                 smtp_username, smtp_password):
    """Set up Agency — full two-phase installation wizard."""
    non_interactive = _any_flag_provided(ctx)

    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(os.path.join(state_dir, "keys"), exist_ok=True)
    toml_path = os.path.join(state_dir, "agency.toml")

    # Load existing config if present
    cfg = {}
    if os.path.exists(toml_path):
        try:
            with open(toml_path, "rb") as f:
                cfg = tomllib.load(f)
        except Exception:
            cfg = {}

    # Re-entry behaviour
    if _phase1_complete(cfg, state_dir):
        wiz_status("Configuration found. Resuming from Phase 2.")
        try:
            _run_phase2(state_dir, toml_path, cfg, ctx, non_interactive,
                        project_name, set_default, register_mcp, skip_primitives)
        except KeyboardInterrupt:
            click.echo(
                "\n^C\nInterrupted. Run 'agency init' to resume "
                "-- completed steps will be skipped."
            )
        return

    # Show welcome banner for first run (interactive only)
    if not non_interactive:
        click.echo(WELCOME_BANNER)
        click.prompt("Press enter to begin, or Ctrl+C to exit", default="", show_default=False)

    # Phase 1
    try:
        cfg = _run_phase1(state_dir, toml_path, cfg, ctx, non_interactive,
                          backend, model, endpoint, api_key, email, timeout,
                          oversight, attribution, smtp_host, smtp_port,
                          smtp_username, smtp_password)
    except KeyboardInterrupt:
        click.echo("\n^C\nInterrupted. Run 'agency init' to resume.")
        return

    # Phase 1 exit prompt
    if not non_interactive:
        click.echo("\n" + "=" * 64)
        if not prompt_bool("Phase 1 complete. Continue to Phase 2 now?", default=True):
            click.echo("""
Setup is not yet complete.

Run 'agency init' again to finish Phase 2, which will:
  - Start the Agency server and initialise the database
  - Download the embedding model (~80MB)
  - Install the starter primitive set
  - Create your first project
  - Create API tokens for your integrations
  - Register with Claude Code
  - Install Claude Code skill (if Claude Code is present)

When you are ready, run: agency init
""")
            return

    # Phase 2
    try:
        _run_phase2(state_dir, toml_path, cfg, ctx, non_interactive,
                    project_name, set_default, register_mcp, skip_primitives)
    except KeyboardInterrupt:
        click.echo(
            "\n^C\nInterrupted. Run 'agency init' to resume "
            "-- completed steps will be skipped."
        )


# -- Phase 1 steps -------------------------------------------------------


def _run_phase1(state_dir: str, toml_path: str, cfg: dict,
                ctx: click.Context, non_interactive: bool,
                backend: str, model: str, endpoint: str, api_key: str,
                email: str, timeout: int, oversight: str, attribution: str,
                smtp_host, smtp_port, smtp_username, smtp_password) -> dict:
    """Run all 5 Phase 1 steps. Returns updated config dict."""
    keys_dir = os.path.join(state_dir, "keys")

    # Step 1.1 -- Generate instance credentials
    _step_header(1, 1, 5)
    helper(SETTING_HELP["instance_credentials"])
    has_creds = (
        "instance_id" in cfg
        and os.path.exists(os.path.join(keys_dir, "agency.ed25519.pem"))
    )
    if has_creds:
        wiz_status("Instance credentials already configured. Skipping.")
    else:
        cfg["instance_id"] = generate_uuid_v7()
        generate_keypair(
            os.path.join(keys_dir, "agency.ed25519.pem"),
            os.path.join(keys_dir, "agency.ed25519.pub.pem"),
        )
        _write_toml(cfg, toml_path)
        wiz_status("Instance ID generated")
        wiz_status(f"Signing keypair written to {keys_dir}/")

    # Step 1.2 -- Configure server settings
    _step_header(1, 2, 5)
    helper(SETTING_HELP["server_settings"])
    if "server" in cfg:
        host = cfg["server"].get("host", "127.0.0.1")
        port = cfg["server"].get("port", 8000)
        wiz_status(f"Server config already set ({host}:{port}). Skipping.")
    else:
        cfg["server"] = {"host": "127.0.0.1", "port": 8000}
        _write_toml(cfg, toml_path)
        wiz_status("Server config written (host: 127.0.0.1, port: 8000)")

    if "assigner" not in cfg:
        cfg["assigner"] = {"strategy": "embedding"}
        _write_toml(cfg, toml_path)
        wiz_status("Assigner config written (strategy: embedding)")

    # Step 1.3 -- Configure LLM connection
    _step_header(1, 3, 5)
    helper(SETTING_HELP["llm_backend"])
    if "llm" in cfg:
        wiz_status(
            f"LLM connection already configured "
            f"({cfg['llm'].get('backend', '?')}). Skipping."
        )
    elif non_interactive and _is_flag_provided(ctx, "backend"):
        cfg = _step_configure_llm_noninteractive(cfg, toml_path, backend, model, endpoint, api_key)
    else:
        cfg = _step_configure_llm(cfg, toml_path)

    # Step 1.4 -- Configure notifications
    _step_header(1, 4, 5)
    if "notifications" in cfg:
        wiz_status("Notifications already configured. Skipping.")
    elif non_interactive:
        cfg = _step_configure_notifications_noninteractive(
            cfg, toml_path, email, timeout, oversight,
            smtp_host, smtp_port, smtp_username, smtp_password,
        )
    else:
        cfg = _step_configure_notifications(cfg, toml_path)

    # Step 1.5 -- Configure output defaults
    _step_header(1, 5, 5)
    helper(SETTING_HELP["attribution"])
    if "output" in cfg:
        attr = "on" if cfg["output"].get("attribution", True) else "off"
        wiz_status(f"Output config already set (attribution: {attr}). Skipping.")
    elif non_interactive:
        if _is_flag_provided(ctx, "attribution"):
            attr_val = attribution.lower() != "off"
        else:
            attr_val = True  # default: attribution on
        cfg["output"] = {"attribution": attr_val}
        _write_toml(cfg, toml_path)
        wiz_status(f"Attribution {'enabled' if attr_val else 'disabled'}")
    else:
        attr_val = prompt_bool("Enable attribution?", default=True)
        cfg["output"] = {"attribution": attr_val}
        _write_toml(cfg, toml_path)
        wiz_status(f"Attribution {'enabled' if attr_val else 'disabled'}")

    return cfg


def _step_configure_llm(cfg: dict, toml_path: str) -> dict:
    choice = prompt_choice(
        "LLM backend",
        ["Use Claude Code (your existing subscription)",
         "Use Anthropic API directly",
         "Use another provider or local model"],
        "Use Claude Code (your existing subscription)",
    )

    if choice.startswith("Use Claude Code"):
        try:
            result = subprocess.run(
                ["claude", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and "not logged in" not in result.stdout.lower():
                cfg["llm"] = {
                    "backend": "claude-code",
                    "model": "claude-sonnet-4-6",
                    "endpoint": "",
                    "api_key": "",
                }
                _write_toml(cfg, toml_path)
                wiz_status('LLM backend set to "claude-code" (model: claude-sonnet-4-6)')
            else:
                wiz_status("claude is installed but not authenticated", success=False)
                click.echo("       Run: claude auth")
                click.echo("       Then re-run agency init.")
                raise SystemExit(1)
        except FileNotFoundError:
            wiz_status("claude CLI not found", success=False)
            click.echo("       Install Claude Code first, or select option 2 or 3.")
            click.echo("       Then re-run agency init.")
            raise SystemExit(1)
    elif choice.startswith("Use Anthropic API"):
        mdl = wiz_prompt("Model", default="claude-sonnet-4-6")
        ak = wiz_prompt("API key", hide_input=True)
        cfg["llm"] = {
            "backend": "api",
            "model": mdl,
            "endpoint": "https://api.anthropic.com/v1",
            "api_key": ak,
        }
        _write_toml(cfg, toml_path)
        wiz_status('LLM backend set to "api"')
    else:
        ep = wiz_prompt("Endpoint URL")
        mdl = wiz_prompt("Model name")
        ak = wiz_prompt("API key", hide_input=True)
        cfg["llm"] = {
            "backend": "other",
            "model": mdl,
            "endpoint": ep,
            "api_key": ak,
        }
        _write_toml(cfg, toml_path)
        wiz_status('LLM backend set to "other"')

    return cfg


def _step_configure_llm_noninteractive(cfg: dict, toml_path: str,
                                        backend: str, model: str,
                                        endpoint: str, api_key: str) -> dict:
    if backend == "claude-code":
        cfg["llm"] = {
            "backend": "claude-code",
            "model": model,
            "endpoint": "",
            "api_key": "",
        }
    elif backend == "api":
        cfg["llm"] = {
            "backend": "api",
            "model": model,
            "endpoint": endpoint or "https://api.anthropic.com/v1",
            "api_key": api_key,
        }
    else:
        cfg["llm"] = {
            "backend": backend,
            "model": model,
            "endpoint": endpoint,
            "api_key": api_key,
        }
    _write_toml(cfg, toml_path)
    wiz_status(f'LLM backend set to "{backend}" (model: {model})')
    return cfg


def _step_configure_notifications(cfg: dict, toml_path: str) -> dict:
    helper(SETTING_HELP["contact_email"])
    contact_email = wiz_prompt("Contact email", default="")

    helper(SETTING_HELP["error_notification_timeout"])
    while True:
        timeout_raw = wiz_prompt(
            "Error notification timeout in seconds", default="1800"
        )
        try:
            timeout_val = int(timeout_raw)
            break
        except ValueError:
            click.echo(f"  Please enter a number (seconds). Got: '{timeout_raw}'")

    helper(SETTING_HELP["oversight_preference"])
    oversight = prompt_choice(
        "Oversight preference",
        ["discretion", "review"],
        "discretion",
    )

    cfg["notifications"] = {
        "contact_email": contact_email,
        "error_notification_timeout": timeout_val,
        "oversight_preference": oversight,
    }
    _write_toml(cfg, toml_path)
    wiz_status(f'Contact email set to "{contact_email}"')
    wiz_status(f"Error notification timeout set to {timeout_val} seconds")
    wiz_status(f'Oversight preference set to "{oversight}"')

    helper(SETTING_HELP["smtp"])
    if prompt_bool("Configure SMTP to enable email sending?", default=False):
        smtp_host = wiz_prompt("SMTP host")
        smtp_port = int(wiz_prompt("SMTP port", default="587"))
        smtp_user = wiz_prompt("SMTP username")
        smtp_pass = wiz_prompt("SMTP password", hide_input=True)
        cfg["smtp"] = {
            "host": smtp_host,
            "port": smtp_port,
            "username": smtp_user,
            "password": smtp_pass,
            "from_address": smtp_user,
        }
        _write_toml(cfg, toml_path)
        wiz_status("SMTP configured")
    else:
        wiz_status("SMTP skipped — errors will be logged locally")

    return cfg


def _step_configure_notifications_noninteractive(
    cfg: dict, toml_path: str,
    email: str, timeout: int, oversight: str,
    smtp_host, smtp_port, smtp_username, smtp_password,
) -> dict:
    cfg["notifications"] = {
        "contact_email": email,
        "error_notification_timeout": timeout,
        "oversight_preference": oversight,
    }
    _write_toml(cfg, toml_path)
    wiz_status(f'Contact email set to "{email}"')
    wiz_status(f"Error notification timeout set to {timeout} seconds")
    wiz_status(f'Oversight preference set to "{oversight}"')

    if smtp_host is not None:
        cfg["smtp"] = {
            "host": smtp_host,
            "port": smtp_port,
            "username": smtp_username or "",
            "password": smtp_password or "",
            "from_address": smtp_username or "",
        }
        _write_toml(cfg, toml_path)
        wiz_status("SMTP configured")
    else:
        wiz_status("SMTP skipped — errors will be logged locally")

    return cfg


def _resolve_agency_binary() -> str | None:
    """Resolve the absolute path to the agency binary.

    Resolution order:
    1. Sibling of current Python executable (same venv/pipx env)
    2. ~/.local/bin/agency (pipx default)
    3. {sys.prefix}/bin/agency (current venv)
    4. shutil.which fallback (PATH search)
    """
    # 1. Same installation as the running process
    exe_dir = pathlib.Path(sys.executable).resolve().parent
    sibling = exe_dir / "agency"
    if sibling.is_file() and sibling.stat().st_mode & 0o111:
        return str(sibling)

    # 2. pipx default location
    pipx_path = pathlib.Path.home() / ".local" / "bin" / "agency"
    if pipx_path.is_file() and pipx_path.stat().st_mode & 0o111:
        return str(pipx_path.resolve())

    # 3. Current venv
    venv_path = pathlib.Path(sys.prefix) / "bin" / "agency"
    if os.path.isfile(venv_path) and os.access(venv_path, os.X_OK):
        return str(pathlib.Path(venv_path).resolve())

    # 4. PATH fallback
    found = _shutil.which("agency")
    if found:
        return str(pathlib.Path(found).resolve())

    return None


def _merge_mcp_registration(claude_json: str):
    """Merge Agency MCP entry into ~/.claude.json (back up first)."""
    agency_bin = _resolve_agency_binary()
    if agency_bin is None:
        wiz_status(
            "Could not find the agency binary. Ensure agency-engine is installed "
            "(pipx install agency-engine). Then re-run: agency init",
            success=False,
        )
        return

    token_path = os.path.expanduser("~/.agency-mcp-token")
    entry = {
        "command": agency_bin,
        "args": ["mcp"],
        "env": {"AGENCY_TOKEN_FILE": token_path},
    }

    if os.path.exists(claude_json):
        try:
            _shutil.copy2(claude_json, claude_json + ".bak")
            with open(claude_json) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            wiz_status(
                "~/.claude.json is not valid JSON. Back up and fix the file, "
                "then re-run agency init.",
                success=False,
            )
            return
    else:
        data = {}

    data.setdefault("mcpServers", {})["agency"] = entry
    with open(claude_json, "w") as f:
        json.dump(data, f, indent=2)

    claude_json_abs = str(pathlib.Path(claude_json).resolve())
    wiz_status(f"MCP server registered in {claude_json_abs}")


# -- Phase 2 steps -------------------------------------------------------


def _run_phase2(state_dir: str, toml_path: str, cfg: dict,
                ctx: click.Context, non_interactive: bool,
                project_name, set_default, register_mcp, skip_primitives):
    """Run all 7 Phase 2 steps.

    Step ordering: MCP registration (2.6) is AFTER token creation (2.5).
    """
    db_path = os.path.join(state_dir, "agency.db")
    skipped = []
    failed = []

    # Step 2.1 -- Initialise database
    _step_header(2, 1, 7)
    helper(SETTING_HELP["database_init"])
    if is_schema_current(db_path):
        wiz_status("Database already initialised. Skipping.")
    else:
        try:
            _step_init_database(state_dir, cfg)
        except Exception as e:
            failed.append(f"Database initialisation: {e}")

    # Step 2.2 -- Download embedding model
    _step_header(2, 2, 7)
    helper(SETTING_HELP["embedding_model"])
    if _embedding_model_cached():
        wiz_status("Embedding model already downloaded. Skipping.")
    else:
        try:
            _step_download_embedding_model()
        except Exception as e:
            failed.append(f"Embedding model download: {e}")

    # Step 2.3 -- Install starter primitives (auto-download on first install)
    _step_header(2, 3, 7)
    if skip_primitives:
        wiz_status("Primitive download skipped (--skip-primitives)")
        skipped.append("Primitive installation   ->  agency primitives update")
    else:
        try:
            conn = sqlite3.connect(db_path)
            run_migrations(conn)
            prim_count = conn.execute("SELECT COUNT(*) FROM role_components").fetchone()[0]
            conn.close()
        except Exception as e:
            failed.append(f"Primitive check: {e}")
            prim_count = -1
        if prim_count > 0:
            wiz_status(
                f"Primitives already installed ({prim_count} role components). Skipping."
            )
        elif prim_count == 0:
            # First install: auto-download without prompting
            try:
                _step_install_primitives(db_path, cfg.get("instance_id", ""))
            except Exception as e:
                failed.append(f"Primitive installation: {e}")
        # prim_count == -1 means check failed; already recorded in failed list

    # Step 2.4 -- Create first project
    _step_header(2, 4, 7)
    helper(SETTING_HELP["project_name"])
    helper(
        "Inherited settings (oversight, attribution, notifications) come from\n"
        "agency.toml and apply to all projects unless overridden per-project.\n"
        "You can override them later with: agency project create --help"
    )
    proj_configured = _project_already_configured(toml_path, db_path)
    if proj_configured:
        wiz_status("Default project already configured. Skipping.")
    elif non_interactive and project_name is not None:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            from agency.cli.project import run_project_create_wizard

            run_project_create_wizard(state_dir, conn, toml_path,
                                      project_name=project_name,
                                      set_default=set_default)
            conn.close()
        except Exception as e:
            failed.append(f"Project creation: {e}")
            skipped.append("Default project          ->  agency project create")
    elif non_interactive and project_name is None:
        wiz_status("No --project-name provided. Skipping project creation.")
        skipped.append("Default project          ->  agency project create")
    else:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            from agency.cli.project import run_project_create_wizard

            run_project_create_wizard(state_dir, conn, toml_path)
            conn.close()
        except Exception as e:
            failed.append(f"Project creation: {e}")
            skipped.append("Default project          ->  agency project create")

    # Step 2.5 -- Create integration tokens
    _step_header(2, 5, 7)
    helper(SETTING_HELP["integration_tokens"])
    _step_create_integration_tokens(db_path, state_dir, toml_path, skipped, failed)

    # Step 2.6 -- Register with Claude Code (AFTER token creation)
    _step_header(2, 6, 7)
    helper(SETTING_HELP["register_mcp"])
    claude_json = os.path.expanduser("~/.claude.json")
    already_registered = False
    if os.path.exists(claude_json):
        try:
            with open(claude_json) as f:
                cj = json.load(f)
            already_registered = "agency" in cj.get("mcpServers", {})
        except Exception:
            pass
    if already_registered:
        wiz_status("Agency already registered in ~/.claude.json. Skipping.")
    elif non_interactive:
        if register_mcp:
            _merge_mcp_registration(claude_json)
        else:
            wiz_status("MCP registration skipped (--no-register-mcp)")
    else:
        if prompt_bool("Register Agency as an MCP server in Claude Code?", default=True):
            _merge_mcp_registration(claude_json)
        else:
            click.echo(
                "\nTo register manually, add the following to ~/.claude.json mcpServers:"
            )
            click.echo(
                '  "agency": {"command": "agency", "args": ["mcp"], '
                '"env": {"AGENCY_TOKEN_FILE": "~/.agency-mcp-token"}}'
            )

    # Step 2.7 -- Install Claude Code skill
    _step_header(2, 7, 7)
    claude_dir = os.path.expanduser("~/.claude")
    if not os.path.isdir(claude_dir):
        os.makedirs(claude_dir, exist_ok=True)
    if True:
        try:
            from agency.cli.skills import _install_skill, BUNDLED_SKILLS

            skills_dir = os.path.join(claude_dir, "skills")
            os.makedirs(skills_dir, exist_ok=True)
            for skill_name in BUNDLED_SKILLS:
                install_status = _install_skill(skill_name, skills_dir)
                if install_status == "already_current":
                    wiz_status("Claude Code skill already current. Skipping.")
                else:
                    wiz_status(f"Claude Code skill installed ({skill_name})")
        except Exception as e:
            wiz_status(
                f"Could not write to ~/.claude/skills/ ({e}). "
                "Install manually: agency skills install",
                success=False,
            )

    # Phase 2 completion
    click.echo("\n" + "=" * 64)
    if failed:
        click.echo("\nSetup finished with errors.\n\nFailed:")
        for f in failed:
            click.echo(f"  - {f}")
        click.echo(
            "\nFix the errors above, then run 'agency init' to retry."
            "\nCompleted steps will be skipped automatically."
        )
    elif skipped:
        click.echo("\nSetup complete with skipped steps.\n\nSkipped:")
        for s in skipped:
            click.echo(f"  - {s}")
        click.echo(
            "\nTo get started with Agency, inside Claude Code use the skill /agency-getting-started."
        )
    else:
        click.echo(
            "\nSetup complete. Agency is ready to use.\n\n"
            "To get started with Agency, inside Claude Code use the skill /agency-getting-started."
        )
    helper("Run the agency-getting-started skill for a guided walkthrough: /agency-getting-started")


# -- Phase 2 step helpers -------------------------------------------------


def _step_init_database(state_dir: str, cfg: dict):
    server = cfg.get("server", {})
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8000)
    base_url = f"http://{host}:{port}"

    wiz_status("Starting server...")
    proc = subprocess.Popen(
        ["agency", "serve"],
        env={**os.environ, "AGENCY_STATE_DIR": state_dir},
    )
    if not _poll_health(base_url, timeout_secs=15):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise RuntimeError("Server started but did not become ready in time.")
    wiz_status("Schema ready")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    wiz_status("Server stopped")


def _embedding_model_cached() -> bool:
    """Return True if all-MiniLM-L6-v2 is present in local sentence-transformers cache."""
    try:
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(cache_dir):
            return any("all-MiniLM-L6-v2" in d for d in os.listdir(cache_dir))
        return False
    except Exception:
        return False


def _step_download_embedding_model():
    wiz_status("Downloading embedding model (all-MiniLM-L6-v2, ~80MB)...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("all-MiniLM-L6-v2")
    wiz_status("Embedding model downloaded")


def _step_install_primitives(db_path: str, instance_id: str):
    from agency.cli.primitives import STARTER_CSV_URL, _fetch_csv, install_from_csv

    wiz_status("Downloading starter primitives from GitHub...")
    try:
        rows = _fetch_csv(STARTER_CSV_URL)
    except Exception as e:
        wiz_status(f"Could not reach GitHub: {e}", success=False)
        click.echo("Install later: agency primitives update")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    inserted, skip_count = install_from_csv(rows, conn, instance_id)
    conn.close()
    wiz_status(f"{inserted} starter primitives installed")


def _project_already_configured(toml_path: str, db_path: str) -> bool:
    try:
        with open(toml_path, "rb") as f:
            cfg = tomllib.load(f)
        default_id = cfg.get("project", {}).get("default_id")
        if not default_id:
            return False
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (default_id,)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _step_create_integration_tokens(
    db_path: str,
    state_dir: str,
    toml_path: str,
    skipped: list,
    failed: list,
):
    """Multi-select token creation for MCP, Superpowers, Workgraph.

    Per-integration logic:
    - DB row exists + token file exists (non-revoked): skip -- already set up.
    - DB row exists but token file missing: revoke old tokens for this client_id,
      then create a new token and write the file (recovery path).
    - No DB row: create new token and write the file.
    """
    integrations = [
        ("MCP (Claude Code)", "mcp", os.path.expanduser("~/.agency-mcp-token")),
        ("CLI", "cli", os.path.expanduser("~/.agency-cli-token")),
        ("Superpowers", "superpowers", os.path.expanduser("~/.agency-superpowers-token")),
        ("Workgraph", "workgraph", os.path.expanduser("~/.agency-workgraph-token")),
    ]

    try:
        with open(toml_path, "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        cfg = {}
    instance_id = cfg.get("instance_id", "")

    conn = sqlite3.connect(db_path)
    if not token_table_exists(conn):
        failed.append("Token creation -- database not initialised")
        conn.close()
        return

    priv_key_path = os.path.join(state_dir, "keys", "agency.ed25519.pem")
    private_key = load_private_key(priv_key_path)

    for name, client_id, token_path in integrations:
        # Check for existing non-revoked token rows for this client
        cursor = conn.execute(
            "SELECT jti FROM issued_tokens WHERE client_id = ? AND revoked = 0",
            (client_id,),
        )
        existing_rows = cursor.fetchall()
        file_exists = False
        if os.path.isfile(token_path):
            with open(token_path) as fh:
                file_exists = bool(fh.read().strip())

        if existing_rows and file_exists:
            wiz_status(f"{name} token already set up. Skipping.")
            continue

        if existing_rows and not file_exists:
            # Recovery: token file was lost -- revoke all existing tokens for this client
            conn.execute(
                "UPDATE issued_tokens SET revoked = 1 WHERE client_id = ? AND revoked = 0",
                (client_id,),
            )
            conn.commit()
            wiz_status(f"{name} token file missing — recovering...")

        # Create a new token (fresh install or recovery)
        try:
            jti = generate_uuid_v7()
            token = create_jwt(private_key, instance_id, client_id, jti)
            insert_token(conn, jti=jti, client_id=client_id, expires_at=None)
            with open(token_path, "w") as f:
                f.write(token)
            wiz_status(f"{name} token created")
        except Exception as e:
            failed.append(f"{name} token: {e}")

    conn.close()
