import os
import secrets
import click
from pathlib import Path
from agency.config.toml import write_config, load_config, default_config, ConfigError
from agency.auth.keypair import generate_keypair
from agency.utils.ids import new_uuid


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


@click.command("init")
def init_command():
    """Run the Agency setup wizard."""
    state_dir = _state_dir()

    click.echo("\n" + "=" * 60)
    click.echo("  Agency v1.1.0 — Setup Wizard")
    click.echo("=" * 60)
    click.echo(f"""
Agency stores all state in:
  {state_dir}
""")

    click.echo("Step 1: LLM configuration")
    llm_endpoint = click.prompt("LLM endpoint URL", default="https://api.anthropic.com/v1")
    llm_model = click.prompt("Model name", default="claude-sonnet-4-6")
    llm_api_key = click.prompt("API key", hide_input=True)

    click.echo("\nStep 2: Contact and oversight")
    contact_email = click.prompt("Contact email for error notifications")
    oversight_preference = click.prompt(
        "Oversight preference",
        type=click.Choice(["discretion", "always", "never"]),
        default="discretion",
    )

    click.echo("\nStep 3: Email notifications (SMTP)")
    smtp_host = click.prompt("SMTP host")
    smtp_port = click.prompt("SMTP port", default=587, type=int)
    smtp_username = click.prompt("SMTP username")
    smtp_password = click.prompt("SMTP password", hide_input=True)
    sender_address = click.prompt("Sender address", default=smtp_username)

    click.echo("\nStep 4: Server settings")
    host = click.prompt("Server host", default="127.0.0.1")
    port = click.prompt("Server port", default=8000, type=int)

    # Check for existing config to preserve jwt_secret
    cfg_path = state_dir / "agency.toml"
    existing_secret = None
    if cfg_path.exists():
        try:
            existing = load_config(cfg_path)
            existing_secret = existing.get("auth", {}).get("jwt_secret")
        except ConfigError:
            pass

    instance_id = new_uuid()
    cfg = default_config(instance_id)
    cfg.update({
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "contact_email": contact_email,
        "oversight_preference": oversight_preference,
    })
    cfg["auth"]["jwt_secret"] = existing_secret or secrets.token_hex(32)
    cfg["server"]["host"] = host
    cfg["server"]["port"] = port
    cfg["email"].update({
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "sender_address": sender_address,
    })

    keys_dir = state_dir / "keys"
    generate_keypair(keys_dir)
    write_config(cfg, cfg_path)

    click.echo(f"\n✓ Config written to {cfg_path}")
    click.echo(f"✓ Keypair generated in {keys_dir}")
    click.echo(f"✓ Instance ID: {instance_id}")
    click.echo("\nRun `agency serve` to start the service.\n")
