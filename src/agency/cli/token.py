import os
import time
import sqlite3
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import click

from agency.auth.keypair import load_private_key
from agency.auth.jwt import create_jwt
from agency.db.tokens import (
    insert_token,
    list_tokens,
    revoke_tokens_by_client_id,
    token_table_exists,
)


def _state_dir() -> Path:
    return Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))


def _new_jti() -> str:
    """Generate a UUID v7-style unique JTI using uuid module.

    Python's uuid module does not have uuid7 until 3.14, so we generate a
    time-ordered unique identifier using uuid4 prefixed with a timestamp hex.
    This gives unique, time-ordered JTIs that are safe as JWT IDs.
    """
    import uuid
    # Use uuid4 for randomness; prepend ms timestamp for rough ordering
    ts_hex = format(int(time.time() * 1000), "013x")
    rand_part = uuid.uuid4().hex[13:]
    raw = ts_hex + rand_part  # 32 hex chars
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


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
    state_dir = _state_dir()
    cfg_path = state_dir / "agency.toml"

    if not cfg_path.exists():
        raise click.ClickException(f"Config file not found: {cfg_path}. Run 'agency init' first.")

    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)

    instance_id = cfg.get("instance_id", "") or cfg.get("server", {}).get("instance_id", "")
    if not instance_id:
        raise click.ClickException("No instance_id found in config. Run 'agency init' first.")

    # Load private key
    priv_key_path = state_dir / "keys" / "agency.ed25519.pem"
    if not priv_key_path.exists():
        raise click.ClickException(
            f"Private key not found at {priv_key_path}. Run 'agency init' first."
        )
    private_key = load_private_key(str(priv_key_path))

    # Check database is initialised
    db_path = state_dir / "agency.db"
    conn = sqlite3.connect(str(db_path))
    try:
        if not token_table_exists(conn):
            raise click.ClickException(
                "Database not initialised. Run 'agency serve' to initialise the database."
            )

        jti = _new_jti()
        exp: int | None = None
        expires_at: str | None = None

        if expires_in is not None:
            exp = int(time.time()) + expires_in
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()

        token = create_jwt(private_key, instance_id, client_id, jti, exp=exp)
        insert_token(conn, jti, client_id, expires_at)
    finally:
        conn.close()

    # Print only the token — nothing else so it's pipeable
    click.echo(token)


@token_group.command("list")
def token_list():
    """List all issued tokens."""
    state_dir = _state_dir()
    db_path = state_dir / "agency.db"
    conn = sqlite3.connect(str(db_path))
    try:
        if not token_table_exists(conn):
            raise click.ClickException(
                "Database not initialised. Run 'agency serve' to initialise the database."
            )
        tokens = list_tokens(conn)
    finally:
        conn.close()

    if not tokens:
        click.echo("No tokens found.")
        return

    # Column widths
    col_client = max(len("CLIENT_ID"), max(len(t["client_id"] or "") for t in tokens))
    col_created = max(len("CREATED_AT"), max(len(str(t["created_at"] or "")) for t in tokens))
    col_expires = max(len("EXPIRES_AT"), max(len(str(t["expires_at"] or "—")) for t in tokens))
    col_revoked = len("REVOKED")
    col_jti = max(len("JTI"), 12)  # 8 chars + "..."

    header = (
        f"{'CLIENT_ID':<{col_client}}  "
        f"{'CREATED_AT':<{col_created}}  "
        f"{'EXPIRES_AT':<{col_expires}}  "
        f"{'REVOKED':<{col_revoked}}  "
        f"{'JTI'}"
    )
    click.echo(header)
    click.echo("-" * len(header))

    for t in tokens:
        jti_short = (t["jti"] or "")[:8] + "..."
        expires = t["expires_at"] or "—"
        revoked_str = "yes" if t["revoked"] else "no"
        row = (
            f"{(t['client_id'] or ''):<{col_client}}  "
            f"{str(t['created_at'] or ''):<{col_created}}  "
            f"{expires:<{col_expires}}  "
            f"{revoked_str:<{col_revoked}}  "
            f"{jti_short}"
        )
        click.echo(row)


@token_group.command("revoke")
@click.option("--client-id", required=True, help="Client ID whose tokens should be revoked")
def token_revoke(client_id: str):
    """Revoke all tokens for a client. Requires exact confirmation."""
    click.echo(
        f"This will revoke ALL tokens for client '{client_id}' on this instance.\n"
        "To confirm, type exactly: yes, cancel every token on this instance"
    )
    confirmation = click.prompt("Confirmation")

    if confirmation != "yes, cancel every token on this instance":
        click.echo("Cancelled. No tokens were revoked.")
        return

    state_dir = _state_dir()
    db_path = state_dir / "agency.db"
    conn = sqlite3.connect(str(db_path))
    try:
        if not token_table_exists(conn):
            raise click.ClickException(
                "Database not initialised. Run 'agency serve' to initialise the database."
            )
        count = revoke_tokens_by_client_id(conn, client_id)
    finally:
        conn.close()

    if count == 0:
        click.echo(f"No active tokens found for client '{client_id}'.")
    else:
        click.echo(f"Revoked {count} token(s) for client '{client_id}'.")
