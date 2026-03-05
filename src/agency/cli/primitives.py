import click


@click.group("primitives")
def primitives_command():
    """Manage Agency primitives."""


@primitives_command.command("list")
@click.option("--table", default="role_components",
              type=click.Choice(["role_components", "desired_outcomes", "trade_off_configs"]))
def list_primitives(table: str):
    """List stored primitives."""
    import os, sqlite3
    from pathlib import Path
    from agency.db.migrations import run_migrations
    from agency.db.primitives import get_primitive

    state_dir = Path(os.environ.get("AGENCY_STATE_DIR", Path.home() / ".agency"))
    conn = sqlite3.connect(state_dir / "agency.db")
    run_migrations(conn)
    rows = conn.execute(f"SELECT id, description FROM {table}").fetchall()
    if not rows:
        click.echo(f"No {table} found.")
        return
    for rid, desc in rows:
        click.echo(f"  {rid}  {desc[:80]}")
