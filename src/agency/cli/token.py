import os
import uuid
import time
import click
from pathlib import Path
from agency.config.toml import load_config, ConfigError


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


@click.group("token")
def token_group():
    """Manage Agency authentication tokens."""
    pass


@token_group.command("create")
@click.option("--client-id", required=True, help="Identifier for the token client")
@click.option("--expires-in", default=None, type=int,
              help="Token lifetime in seconds (default: no expiry)")
def token_create(client_id: str, expires_in: int | None):
    """Create a new authentication token and print it to stdout."""
    cfg_path = _state_dir() / "agency.toml"
    try:
        cfg = load_config(cfg_path)
    except ConfigError as e:
        raise click.ClickException(str(e))

    secret = cfg.get("auth", {}).get("jwt_secret", "")
    if not secret:
        raise click.ClickException("No JWT secret found. Run 'agency init' first.")

    instance_id = cfg.get("instance_id", "")

    import jwt as pyjwt
    payload = {
        "jti": str(uuid.uuid4()),
        "client_id": client_id,
        "instance_id": instance_id,
        "scope": "task",
        "iat": int(time.time()),
    }
    if expires_in is not None:
        payload["exp"] = int(time.time()) + expires_in

    token = pyjwt.encode(payload, secret, algorithm="HS256")
    click.echo(token)
