import os
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
    click.echo("  Agency v1.2.0 — Setup Wizard")
    click.echo("=" * 60)
    click.echo(f"""
Agency stores all state in:
  {state_dir}
""")

    click.echo("Step 1: LLM configuration")
    llm_backend = click.prompt("LLM backend", type=click.Choice(["claude-code", "api"]), default="claude-code")
    llm_model = click.prompt("Model name", default="claude-sonnet-4-6")
    llm_endpoint = ""
    llm_api_key = ""
    if llm_backend == "api":
        llm_endpoint = click.prompt("LLM endpoint URL", default="https://api.anthropic.com/v1")
        llm_api_key = click.prompt("API key", hide_input=True)

    click.echo("\nStep 2: Contact and oversight")
    contact_email = click.prompt("Contact email for error notifications")
    oversight_preference = click.prompt(
        "Oversight preference",
        type=click.Choice(["discretion", "always", "never"]),
        default="discretion",
    )
    error_notification_timeout = click.prompt(
        "Error notification timeout (seconds)", default=1800, type=int
    )

    click.echo("\nStep 3: Email notifications (SMTP) — leave blank to skip")
    smtp_host = click.prompt("SMTP host", default="")
    smtp_section = None
    if smtp_host:
        smtp_port = click.prompt("SMTP port", default=587, type=int)
        smtp_username = click.prompt("SMTP username")
        smtp_password = click.prompt("SMTP password", hide_input=True)
        smtp_from_address = click.prompt("From address", default=smtp_username)
        smtp_section = {
            "host": smtp_host,
            "port": smtp_port,
            "username": smtp_username,
            "password": smtp_password,
            "from_address": smtp_from_address,
        }

    click.echo("\nStep 4: Server settings")
    host = click.prompt("Server host", default="127.0.0.1")
    port = click.prompt("Server port", default=8000, type=int)

    instance_id = new_uuid()
    cfg = default_config(instance_id)
    cfg["llm"].update({
        "backend": llm_backend,
        "model": llm_model,
        "endpoint": llm_endpoint,
        "api_key": llm_api_key,
    })
    cfg["notifications"].update({
        "contact_email": contact_email,
        "oversight_preference": oversight_preference,
        "error_notification_timeout": error_notification_timeout,
    })
    cfg["server"]["host"] = host
    cfg["server"]["port"] = port
    if smtp_section:
        cfg["smtp"] = smtp_section

    keys_dir = state_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = str(keys_dir / "agency.ed25519.pem")
    public_key_path = str(keys_dir / "agency.ed25519.pub.pem")
    generate_keypair(private_key_path, public_key_path)

    cfg_path = state_dir / "agency.toml"
    write_config(cfg, cfg_path)

    click.echo(f"\n✓ Config written to {cfg_path}")
    click.echo(f"✓ Keypair generated in {keys_dir}")
    click.echo(f"✓ Instance ID: {instance_id}")
    click.echo("\nRun `agency serve` to start the service.\n")
