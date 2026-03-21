"""agency client setup — update instance-level settings."""
import json
import os
import sqlite3
import sys
import click
import tomllib
import tomli_w

from agency.config.toml import load_config


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


@click.command("setup")
@click.option("--backend", default=None, help="LLM backend (claude-code, api, other)")
@click.option("--model", default=None, help="LLM model name")
@click.option("--email", default=None, help="Contact email")
@click.option("--timeout", default=None, type=int, help="Error notification timeout in seconds")
@click.option("--oversight", default=None, help="Oversight preference (discretion or review)")
@click.option("--attribution", default=None, help="Attribution (on or off)")
@click.option("--host", default=None, help="Server host")
@click.option("--port", default=None, type=int, help="Server port")
@click.option("--smtp-host", default=None, help="SMTP host")
@click.option("--smtp-port", default=None, type=int, help="SMTP port")
@click.option("--smtp-user", default=None, help="SMTP username")
@click.option("--smtp-pass", default=None, help="SMTP password")
@click.option("--smtp-from", default=None, help="SMTP from address")
@click.pass_context
def client_setup_command(ctx, backend, model, email, timeout, oversight,
                         attribution, host, port, smtp_host, smtp_port,
                         smtp_user, smtp_pass, smtp_from):
    """Review and update Agency instance settings."""
    state_dir = os.environ.get("AGENCY_STATE_DIR", os.path.expanduser("~/.agency"))
    toml_path = os.path.join(state_dir, "agency.toml")

    if not os.path.exists(toml_path):
        click.echo("Error: No Agency config found. Run 'agency init' first.")
        raise SystemExit(1)

    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    non_interactive = _any_flag_provided(ctx)

    # Gather current values
    llm = cfg.get("llm", {})
    notif = cfg.get("notifications", {})
    smtp = cfg.get("smtp", {})
    output_cfg = cfg.get("output", {})
    server = cfg.get("server", {})

    original_backend = llm.get("backend", "claude-code")
    original_api_key = llm.get("api_key", "")

    if non_interactive:
        # Non-interactive: apply only the flags that were explicitly provided,
        # keep current values for everything else.
        new_backend = backend if _is_flag_provided(ctx, "backend") else original_backend
        new_model = model if _is_flag_provided(ctx, "model") else llm.get("model", "")
        new_email = email if _is_flag_provided(ctx, "email") else notif.get("contact_email", "")
        new_timeout = timeout if _is_flag_provided(ctx, "timeout") else notif.get("error_notification_timeout", 1800)
        new_oversight = oversight if _is_flag_provided(ctx, "oversight") else notif.get("oversight_preference", "discretion")

        if _is_flag_provided(ctx, "attribution"):
            new_attribution = attribution.lower() not in ("off", "false", "0", "no")
        else:
            new_attribution = output_cfg.get("attribution", True)

        new_host = host if _is_flag_provided(ctx, "host") else server.get("host", "127.0.0.1")
        new_port = port if _is_flag_provided(ctx, "port") else server.get("port", 8000)

        new_smtp_host = smtp_host if _is_flag_provided(ctx, "smtp_host") else smtp.get("host", "")
        new_smtp_port = smtp_port if _is_flag_provided(ctx, "smtp_port") else smtp.get("port", 587)
        new_smtp_user = smtp_user if _is_flag_provided(ctx, "smtp_user") else smtp.get("username", "")
        new_smtp_pass = smtp_pass if _is_flag_provided(ctx, "smtp_pass") else smtp.get("password", "")
        new_smtp_from = smtp_from if _is_flag_provided(ctx, "smtp_from") else smtp.get("from_address", "")
    else:
        click.echo("\n[ Client Setup — Update Mode ]")
        click.echo("Press enter to keep the current value, or type a new value.\n")

        # LLM settings
        new_backend = click.prompt(f"LLM backend [{original_backend}]", default="", show_default=False) or original_backend
        new_model = click.prompt(f"Model [{llm.get('model', '')}]", default="", show_default=False) or llm.get("model", "")

        # Notification settings
        new_email = click.prompt(f"Contact email [{notif.get('contact_email', '')}]", default="", show_default=False) or notif.get("contact_email", "")
        new_timeout = click.prompt(f"Error notification timeout [{notif.get('error_notification_timeout', 1800)}]", default="", show_default=False)
        new_timeout = int(new_timeout) if new_timeout else notif.get("error_notification_timeout", 1800)
        new_oversight = click.prompt(f"Oversight preference [{notif.get('oversight_preference', 'discretion')}]", default="", show_default=False) or notif.get("oversight_preference", "discretion")

        # SMTP settings
        new_smtp_host = click.prompt(f"SMTP host [{smtp.get('host', '')}]", default="", show_default=False) or smtp.get("host", "")
        new_smtp_port = click.prompt(f"SMTP port [{smtp.get('port', 587)}]", default="", show_default=False)
        new_smtp_port = int(new_smtp_port) if new_smtp_port else smtp.get("port", 587)
        new_smtp_user = click.prompt(f"SMTP username [{smtp.get('username', '')}]", default="", show_default=False) or smtp.get("username", "")
        new_smtp_pass = click.prompt(f"SMTP password [{'*' * 8 if smtp.get('password') else ''}]", default="", show_default=False, hide_input=True) or smtp.get("password", "")
        new_smtp_from = click.prompt(f"SMTP from address [{smtp.get('from_address', '')}]", default="", show_default=False) or smtp.get("from_address", "")

        # Attribution
        attr_current = "on" if output_cfg.get("attribution", True) else "off"
        new_attr_raw = click.prompt(f"Attribution [{attr_current}]", default="", show_default=False) or attr_current
        new_attribution = new_attr_raw.lower() not in ("off", "false", "0", "no")

        # Server settings
        original_host = server.get("host", "127.0.0.1")
        original_port = server.get("port", 8000)
        new_host = click.prompt(f"Server host [{original_host}]", default="", show_default=False) or original_host
        new_port_raw = click.prompt(f"Server port [{original_port}]", default="", show_default=False)
        new_port = int(new_port_raw) if new_port_raw else original_port

        # Keypair rotation (interactive only)
        keys_dir = os.path.join(state_dir, "keys")
        priv_key_path = os.path.join(keys_dir, "agency.ed25519.pem")
        if os.path.exists(priv_key_path):
            import time
            mtime = os.path.getmtime(priv_key_path)
            key_date = time.strftime("%Y-%m-%d", time.localtime(mtime))
            rotate_raw = click.prompt(
                f"Signing keypair: agency.ed25519.pem (generated {key_date}) [rotate? y/n]",
                default="n", show_default=False
            )
            if rotate_raw.lower() == "y":
                click.echo("\nWarning: rotating the signing keypair immediately invalidates ALL existing")
                click.echo("tokens. Every integration (MCP, Superpowers, Workgraph) will stop")
                click.echo("working until new tokens are created.")
                click.echo("\nAgency serve must be restarted after this change.")
                confirm = click.prompt("\nTo confirm, type: yes, invalidate all tokens")
                if confirm == "yes, invalidate all tokens":
                    _rotate_keypair(state_dir)
                else:
                    click.echo("Cancelled. Keypair unchanged.")

    # Handle attribution change
    attr_changed = new_attribution != output_cfg.get("attribution", True)
    if attr_changed and not non_interactive:
        click.echo("\nNote: changing attribution affects how agents are rendered.")
        if click.confirm("Clear the composition cache?", default=True):
            db_path = os.path.join(state_dir, "agency.db")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM agents WHERE project_id IN (SELECT id FROM projects WHERE attribution IS NULL)")
                conn.commit()
                conn.close()
                click.echo("Composition cache cleared.")

    # Server change reminder
    original_host_val = server.get("host", "127.0.0.1")
    original_port_val = server.get("port", 8000)
    if new_host != original_host_val or new_port != original_port_val:
        click.echo("\nNote: restart agency serve for the new address to take effect.")

    # Write updated config
    cfg["llm"] = {"backend": new_backend, "model": new_model,
                   "endpoint": llm.get("endpoint", ""), "api_key": llm.get("api_key", "")}
    cfg["notifications"] = {"contact_email": new_email, "error_notification_timeout": new_timeout,
                             "oversight_preference": new_oversight}
    cfg["output"] = {"attribution": new_attribution}
    cfg["server"] = {"host": new_host, "port": new_port}
    if new_smtp_host:
        cfg["smtp"] = {"host": new_smtp_host, "port": new_smtp_port,
                       "username": new_smtp_user, "password": new_smtp_pass,
                       "from_address": new_smtp_from or new_smtp_user}

    with open(toml_path, "wb") as f:
        tomli_w.dump(cfg, f)

    click.echo(f"\nSettings updated. Changes written to {toml_path}.")


def _rotate_keypair(state_dir: str):
    """Rotate Ed25519 keypair and revoke all tokens."""
    from agency.auth.keypair import generate_keypair
    priv = os.path.join(state_dir, "keys", "agency.ed25519.pem")
    pub = os.path.join(state_dir, "keys", "agency.ed25519.pub.pem")
    generate_keypair(priv, pub)
    # Revoke all tokens
    db_path = os.path.join(state_dir, "agency.db")
    if os.path.exists(db_path):
        from agency.db.tokens import revoke_tokens_by_client_id
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT DISTINCT client_id FROM issued_tokens WHERE revoked = 0")
        for row in cursor.fetchall():
            revoke_tokens_by_client_id(conn, row[0])
        conn.close()
    click.echo("Keypair rotated. All existing tokens have been revoked.")
    click.echo("  Restart agency serve, then recreate tokens:")
    click.echo("  agency token create --client-id mcp > ~/.agency-mcp-token")
    click.echo("  agency token create --client-id superpowers > ~/.agency-superpowers-token")
    click.echo("  agency token create --client-id workgraph > ~/.agency-workgraph-token")
