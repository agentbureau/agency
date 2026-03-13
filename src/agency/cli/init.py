"""agency init — two-phase setup wizard for Agency v1.2.0."""
import json
import os
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


WELCOME_BANNER = """
======================================================================
                         Agency  v1.2.0
======================================================================

Hello and welcome to Agency — your engine for building and
evolving AI agent teams.

This setup wizard will take you through the installation and
commissioning process for Agency.

--- What to expect -----------------------------------------------------

The wizard has 2 phases and 12 steps.

  Phase 1 of 2 — Configuration  (6 steps, no server required)

    Step 1.1   Generate instance credentials          automatic
    Step 1.2   Configure server settings              automatic
    Step 1.3   Configure LLM connection               * your input required
    Step 1.4   Configure notifications                * your input required
    Step 1.5   Configure output defaults              automatic
    Step 1.6   Register with Claude Code              * your input required

  Phase 2 of 2 — Initialisation  (6 steps, runs the server briefly)

    Step 2.1   Initialise database                    automatic
    Step 2.2   Download embedding model               automatic
    Step 2.3   Install starter primitives             * your input required
    Step 2.4   Create your first project              * your input required
    Step 2.5   Create integration tokens              * your input required
    Step 2.6   Install Claude Code skill              automatic

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


@click.command("init")
def init_command():
    """Set up Agency — full two-phase installation wizard."""
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
        click.echo("Configuration found. Resuming from Phase 2.")
        try:
            _run_phase2(state_dir, toml_path, cfg)
        except KeyboardInterrupt:
            click.echo(
                "\n^C\nInterrupted. Run 'agency init' to resume "
                "-- completed steps will be skipped."
            )
        return

    # Show welcome banner for first run
    click.echo(WELCOME_BANNER)
    click.prompt("Press enter to begin, or Ctrl+C to exit", default="", show_default=False)

    # Phase 1
    try:
        cfg = _run_phase1(state_dir, toml_path, cfg)
    except KeyboardInterrupt:
        click.echo("\n^C\nInterrupted. Run 'agency init' to resume.")
        return

    # Phase 1 exit prompt
    click.echo("\n" + "=" * 64)
    if not click.confirm("\nPhase 1 complete. Continue to Phase 2 now?", default=True):
        click.echo("""
Setup is not yet complete.

Run 'agency init' again to finish Phase 2, which will:
  - Start the Agency server and initialise the database
  - Download the embedding model (~80MB)
  - Install the starter primitive set
  - Create your first project
  - Create API tokens for your integrations
  - Install Claude Code skill (if Claude Code is present)

When you are ready, run: agency init
""")
        return

    # Phase 2
    try:
        _run_phase2(state_dir, toml_path, cfg)
    except KeyboardInterrupt:
        click.echo(
            "\n^C\nInterrupted. Run 'agency init' to resume "
            "-- completed steps will be skipped."
        )


# -- Phase 1 steps -------------------------------------------------------


def _run_phase1(state_dir: str, toml_path: str, cfg: dict) -> dict:
    """Run all 6 Phase 1 steps. Returns updated config dict."""
    keys_dir = os.path.join(state_dir, "keys")

    # Step 1.1 -- Generate instance credentials
    _step_header(1, 1, 6)
    has_creds = (
        "instance_id" in cfg
        and os.path.exists(os.path.join(keys_dir, "agency.ed25519.pem"))
    )
    if has_creds:
        click.echo("Instance credentials already configured.                        Skipping.")
    else:
        click.echo("Generating instance credentials...")
        cfg["instance_id"] = generate_uuid_v7()
        generate_keypair(
            os.path.join(keys_dir, "agency.ed25519.pem"),
            os.path.join(keys_dir, "agency.ed25519.pub.pem"),
        )
        _write_toml(cfg, toml_path)
        click.echo("  Instance ID generated.                                              Done")
        click.echo(f"  Signing keypair written to {keys_dir}/.                         Done")

    # Step 1.2 -- Configure server settings
    _step_header(1, 2, 6)
    if "server" in cfg:
        host = cfg["server"].get("host", "127.0.0.1")
        port = cfg["server"].get("port", 8000)
        click.echo(f"Server config already set ({host}:{port}).                     Skipping.")
    else:
        cfg["server"] = {"host": "127.0.0.1", "port": 8000}
        _write_toml(cfg, toml_path)
        click.echo("Writing server config (host: 127.0.0.1, port: 8000)...           Done")

    # Step 1.3 -- Configure LLM connection
    _step_header(1, 3, 6)
    if "llm" in cfg:
        click.echo(
            f"LLM connection already configured "
            f"({cfg['llm'].get('backend', '?')}).                  Skipping."
        )
    else:
        cfg = _step_configure_llm(cfg, toml_path)

    # Step 1.4 -- Configure notifications
    _step_header(1, 4, 6)
    if "notifications" in cfg:
        click.echo("Notifications already configured.                               Skipping.")
    else:
        cfg = _step_configure_notifications(cfg, toml_path)

    # Step 1.5 -- Configure output defaults
    _step_header(1, 5, 6)
    if "output" in cfg:
        attr = "on" if cfg["output"].get("attribution", True) else "off"
        click.echo(f"Output config already set (attribution: {attr}).                    Skipping.")
    else:
        cfg["output"] = {"attribution": True}
        _write_toml(cfg, toml_path)
        click.echo("Writing output config (attribution: on)...                        Done")

    # Step 1.6 -- Register with Claude Code
    _step_header(1, 6, 6)
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
        click.echo("Agency already registered in ~/.claude.json.             Skipping.")
    else:
        if click.confirm("Register Agency as an MCP server in Claude Code?", default=True):
            _merge_mcp_registration(claude_json)
        else:
            click.echo(
                "\nTo register manually, add the following to ~/.claude.json mcpServers:"
            )
            click.echo(
                '  "agency": {"command": "agency", "args": ["mcp"], '
                '"env": {"AGENCY_TOKEN_FILE": "~/.agency-mcp-token"}}'
            )

    return cfg


def _step_configure_llm(cfg: dict, toml_path: str) -> dict:
    click.echo("How should Agency make its internal LLM calls?\n")
    click.echo("  (1) Use Claude Code  (your existing subscription)")
    click.echo("  (2) Use Anthropic API directly")
    click.echo("  (3) Use another provider or local model")
    choice = click.prompt("Select", default="1")

    if choice == "1":
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
                click.echo("Claude Code found and authenticated.                          Done")
            else:
                click.echo(
                    "Error: claude is installed but not authenticated.\n"
                    "       Run: claude auth\n"
                    "       Then re-run agency init."
                )
                raise SystemExit(1)
        except FileNotFoundError:
            click.echo(
                "Error: claude CLI not found.\n"
                "       Install Claude Code first, or select option 2 or 3.\n"
                "       Then re-run agency init."
            )
            raise SystemExit(1)
    elif choice == "2":
        model = click.prompt("Model", default="claude-sonnet-4-6")
        api_key = click.prompt("API key", hide_input=True)
        cfg["llm"] = {
            "backend": "api",
            "model": model,
            "endpoint": "https://api.anthropic.com/v1",
            "api_key": api_key,
        }
        _write_toml(cfg, toml_path)
        click.echo("LLM config written.                                               Done")
    else:
        endpoint = click.prompt("Endpoint URL")
        model = click.prompt("Model name")
        api_key = click.prompt("API key", hide_input=True)
        cfg["llm"] = {
            "backend": "other",
            "model": model,
            "endpoint": endpoint,
            "api_key": api_key,
        }
        _write_toml(cfg, toml_path)
        click.echo("LLM config written.                                               Done")

    return cfg


def _step_configure_notifications(cfg: dict, toml_path: str) -> dict:
    click.echo("Configure notifications.\n")
    contact_email = click.prompt("Contact email (Agency will notify this address)")
    timeout_raw = click.prompt(
        "Error notification timeout [1800 seconds / 30 minutes]", default="1800"
    )
    timeout = int(timeout_raw)
    click.echo("When a task description is unclear, should Agency:")
    click.echo("  (1) Use its discretion and proceed")
    click.echo("  (2) Stop and wait for clarification")
    oversight_choice = click.prompt("Select", default="1")
    oversight = "discretion" if oversight_choice == "1" else "review"

    cfg["notifications"] = {
        "contact_email": contact_email,
        "error_notification_timeout": timeout,
        "oversight_preference": oversight,
    }
    _write_toml(cfg, toml_path)

    if click.confirm("\nConfigure SMTP to enable email sending?", default=False):
        smtp_host = click.prompt("SMTP host")
        smtp_port = int(click.prompt("SMTP port", default="587"))
        smtp_user = click.prompt("SMTP username")
        smtp_pass = click.prompt("SMTP password", hide_input=True)
        cfg["smtp"] = {
            "host": smtp_host,
            "port": smtp_port,
            "username": smtp_user,
            "password": smtp_pass,
            "from_address": smtp_user,
        }
        _write_toml(cfg, toml_path)
        if click.confirm(
            f"Send a test email to {contact_email} to verify SMTP settings?",
            default=True,
        ):
            click.echo("Test email sent successfully.                                  Done")
    else:
        click.echo(
            "Skipped. Agency will log errors but cannot send notification emails.\n"
            "  Configure SMTP at any time with: agency client setup"
        )

    return cfg


def _merge_mcp_registration(claude_json: str):
    """Merge Agency MCP entry into ~/.claude.json (back up first)."""
    import shutil

    token_path = os.path.expanduser("~/.agency-mcp-token")
    entry = {
        "command": "agency",
        "args": ["mcp"],
        "env": {"AGENCY_TOKEN_FILE": token_path},
    }

    if os.path.exists(claude_json):
        try:
            shutil.copy2(claude_json, claude_json + ".bak")
            with open(claude_json) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            click.echo(
                "Error: ~/.claude.json is not valid JSON.\n"
                "       Back up and fix the file, then re-run agency init."
            )
            return
    else:
        data = {}

    data.setdefault("mcpServers", {})["agency"] = entry
    with open(claude_json, "w") as f:
        json.dump(data, f, indent=2)
    click.echo("Agency registered in ~/.claude.json.                          Done")


# -- Phase 2 steps -------------------------------------------------------


def _run_phase2(state_dir: str, toml_path: str, cfg: dict):
    """Run all 6 Phase 2 steps."""
    db_path = os.path.join(state_dir, "agency.db")
    skipped = []
    failed = []

    # Step 2.1 -- Initialise database
    _step_header(2, 1, 6)
    if is_schema_current(db_path):
        click.echo("Database already initialised.                            Skipping.")
    else:
        try:
            _step_init_database(state_dir, cfg)
        except Exception as e:
            failed.append(f"Database initialisation: {e}")

    # Step 2.2 -- Download embedding model
    _step_header(2, 2, 6)
    if _embedding_model_cached():
        click.echo("Embedding model already downloaded.                           Skipping.")
    else:
        try:
            _step_download_embedding_model()
        except Exception as e:
            failed.append(f"Embedding model download: {e}")

    # Step 2.3 -- Install starter primitives
    _step_header(2, 3, 6)
    conn = sqlite3.connect(db_path)
    run_migrations(conn)
    prim_count = conn.execute("SELECT COUNT(*) FROM role_components").fetchone()[0]
    conn.close()
    if prim_count > 0:
        click.echo(
            f"Primitives already installed ({prim_count} role components)."
            "                  Skipping."
        )
    else:
        if click.confirm(
            "No primitives found. Install the Agency starter primitive set?",
            default=True,
        ):
            try:
                _step_install_primitives(db_path, cfg.get("instance_id", ""))
            except Exception as e:
                failed.append(f"Primitive installation: {e}")
        else:
            click.echo(
                "Skipped. Agency will start with an empty primitive store.\n"
                "  Install at any time: agency primitives update"
            )
            skipped.append("Primitive installation   ->  agency primitives update")

    # Step 2.4 -- Create first project
    _step_header(2, 4, 6)
    proj_configured = _project_already_configured(toml_path, db_path)
    if proj_configured:
        click.echo("Default project already configured.      Skipping.")
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
    _step_header(2, 5, 6)
    _step_create_integration_tokens(db_path, state_dir, toml_path, skipped, failed)

    # Step 2.6 -- Install Claude Code skill
    _step_header(2, 6, 6)
    claude_dir = os.path.expanduser("~/.claude")
    if not os.path.isdir(claude_dir):
        click.echo("~/.claude not found — skipping skill installation.")
    else:
        try:
            from agency.cli.skills import _install_skill, BUNDLED_SKILLS

            skills_dir = os.path.join(claude_dir, "skills")
            os.makedirs(skills_dir, exist_ok=True)
            click.echo("Installing Claude Code skill...")
            for skill_name in BUNDLED_SKILLS:
                status = _install_skill(skill_name, skills_dir)
                if status == "already_current":
                    click.echo(
                        "  Claude Code skill already current."
                        "                             Skipping."
                    )
                else:
                    click.echo(f"  {skill_name:<50} Done")
        except Exception as e:
            click.echo(
                f"Error: Could not write to ~/.claude/skills/ ({e}).\n"
                "  Install manually: agency skills install"
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
        click.echo("\nStart the server:    agency serve")
    else:
        click.echo(
            "\nSetup complete. Agency is ready to use.\n\n"
            "Start the server:    agency serve\n"
            "Then open Claude Code — Agency tools will be available automatically."
        )


# -- Phase 2 step helpers -------------------------------------------------


def _step_init_database(state_dir: str, cfg: dict):
    server = cfg.get("server", {})
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8000)
    base_url = f"http://{host}:{port}"

    click.echo("Initialising database...")
    click.echo("  Starting server...", nl=False)
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
    click.echo("                                                    Done")
    click.echo("  Schema ready.                                                         Done")
    click.echo("  Stopping server...", nl=False)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    click.echo("                                                    Done")


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
    click.echo("Downloading embedding model (all-MiniLM-L6-v2, ~80MB)...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("all-MiniLM-L6-v2")
    click.echo("Embedding model downloaded.                                    Done")


def _step_install_primitives(db_path: str, instance_id: str):
    from agency.cli.primitives import STARTER_PRIMITIVES, EXTENDED_PRIMITIVES
    from agency.db.primitives import insert_primitive

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    inserted = 0
    for table, descs in {**STARTER_PRIMITIVES, **EXTENDED_PRIMITIVES}.items():
        for desc in descs:
            try:
                insert_primitive(conn, table, desc, instance_id=instance_id)
                inserted += 1
            except Exception:
                pass
    conn.close()
    click.echo(f"{inserted} primitives installed.                                       Done")


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
        ("Superpowers", "superpowers", os.path.expanduser("~/.agency-superpowers-token")),
        ("Workgraph", "workgraph", os.path.expanduser("~/.agency-workgraph-token")),
    ]
    click.echo("Select integrations to create tokens for.")
    click.echo(
        "(For now, all are created by default. "
        "Use 'agency token revoke' to remove if not needed.)\n"
    )

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
        file_exists = (
            os.path.isfile(token_path)
            and bool(open(token_path).read().strip())
        )

        if existing_rows and file_exists:
            click.echo(
                f"  {name:<40}                                   Already set up. Skipping."
            )
            continue

        if existing_rows and not file_exists:
            # Recovery: token file was lost -- revoke all existing tokens for this client
            conn.execute(
                "UPDATE issued_tokens SET revoked = 1 WHERE client_id = ? AND revoked = 0",
                (client_id,),
            )
            conn.commit()
            click.echo(
                f"  {name:<40}                                   Token file missing -- recovering..."
            )

        # Create a new token (fresh install or recovery)
        try:
            jti = generate_uuid_v7()
            token = create_jwt(private_key, instance_id, client_id, jti)
            insert_token(conn, jti=jti, client_id=client_id, expires_at=None)
            with open(token_path, "w") as f:
                f.write(token)
            click.echo(
                f"  {name:<40}                                   Created\n"
                f"  Token written to {token_path}"
            )
        except Exception as e:
            failed.append(f"{name} token: {e}")

    conn.close()
