import os
import click
from pathlib import Path
from agency.config.toml import read_config, write_config, ConfigError


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


@click.command("register")
@click.option("--endpoint", required=True, help="Home pool endpoint URL")
def register_command(endpoint: str):
    """Register this Agency instance with a home pool."""
    state_dir = _state_dir()
    cfg_path = state_dir / "agency.toml"

    try:
        cfg = read_config(cfg_path)
    except ConfigError as e:
        click.echo(f"Error reading config: {e}", err=True)
        raise SystemExit(1)

    cfg["home_pool"]["registered"] = True
    cfg["home_pool"]["enabled"] = True
    cfg["home_pool"]["endpoint"] = endpoint
    write_config(cfg, cfg_path)

    click.echo(f"✓ Registered with home pool at {endpoint}")
    click.echo("  Restart `agency serve` to activate.")
