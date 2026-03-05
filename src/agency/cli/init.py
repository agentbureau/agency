import os
import click
from pathlib import Path
from agency.config.toml import write_config, default_config
from agency.auth.keypair import generate_keypair
from agency.utils.ids import new_uuid


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


@click.command("init")
def init_command():
    """Run the Agency setup wizard."""
    state_dir = _state_dir()

    click.echo("\n" + "=" * 60)
    click.echo("  Agency v1 — Setup Wizard")
    click.echo("=" * 60)
    click.echo("""
Before continuing, make sure you have:
  • An LLM API key (Anthropic, OpenAI, or compatible)
  • A contact email address for error notifications

Agency stores all state in:
  """ + str(state_dir) + """

No data is sent anywhere except to the LLM endpoint you configure.
""")

    click.echo("Step 1: LLM configuration")
    llm_endpoint = click.prompt("LLM endpoint URL",
                                default="https://api.anthropic.com/v1")
    llm_model = click.prompt("Model name", default="claude-sonnet-4-6")
    llm_api_key = click.prompt("API key", hide_input=True)

    click.echo("\nStep 2: Contact and oversight")
    contact_email = click.prompt("Contact email for error notifications")
    oversight_preference = click.prompt(
        "Oversight preference",
        type=click.Choice(["discretion", "always", "never"]),
        default="discretion",
    )
    error_notification_timeout = click.prompt(
        "Error notification timeout (seconds)", default=300, type=int
    )

    click.echo("\nStep 3: Home pool registration")
    register = click.confirm(
        "Register with home pool? (optional, can be done later)", default=False
    )

    instance_id = new_uuid()
    cfg = default_config(instance_id)
    cfg.update({
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "contact_email": contact_email,
        "oversight_preference": oversight_preference,
        "error_notification_timeout": error_notification_timeout,
    })
    cfg["home_pool"]["registered"] = register

    keys_dir = state_dir / "keys"
    generate_keypair(keys_dir)
    write_config(cfg, state_dir / "agency.toml")

    click.echo(f"\n✓ Config written to {state_dir / 'agency.toml'}")
    click.echo(f"✓ Keypair generated in {keys_dir}")
    click.echo(f"✓ Instance ID: {instance_id}")
    click.echo("\nRun `agency serve` to start the service.\n")
